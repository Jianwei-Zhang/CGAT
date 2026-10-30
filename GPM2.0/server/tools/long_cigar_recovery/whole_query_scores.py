"""Conditional full-path asm10 statistics/rank scores; not native-state recovery.

Port the score/statistic calculations in pinned v2.31 align.c over a FINAL,
base-checked recovered path, without encoding that path in 28-bit CIGAR words.
The upstream notices are in MINIMAP2_LICENSE.txt. No minimap2 tool is modified.

The path must already represent the accepted, normalized native base alignment.
Computing its score DOES NOT prove that whole-query minimap2 would choose it.
In particular this is not DP, Z-drop, inversion rescue, chain parent metadata,
AS reconstruction, MAPQ or a certificate of candidate completeness.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import struct

import post_dp_selection as ps
import windowed_alignment as wa

MAX_OPERATIONS = 1_000_000
MAX_PAF_LINE = 32 * 1024**2
_CANONICAL_OR_N = re.compile(rb"[ACGT]+|N+")


def native_log2(value):
    """Pinned mmpriv.h::mg_log2, NOT Python/math.log2.

    Every operation follows the source binary32 expression (no FMA). Final
    native-oracle validation is still required for the pinned producer build.
    """
    x = ps.f32(value)
    if not math.isfinite(x) or x < 2.0:
        raise wa.ExperimentError("native gap log requires a finite float >= 2")
    bits = struct.unpack("<I", struct.pack("<f", x))[0]
    exponent = ps.f32(((bits >> 23) & 255) - 128)
    mantissa_bits = (bits & ~(255 << 23)) + (127 << 23)
    mantissa = struct.unpack("<f", struct.pack("<I", mantissa_bits))[0]
    polynomial = ps.f32(ps.f32(ps.f32(-0.34484843) * mantissa) + ps.f32(2.02466578))
    polynomial = ps.f32(ps.f32(polynomial * mantissa) - ps.f32(0.67487759))
    return ps.f32(exponent + polynomial)


def logical_operations(operations):
    """Coalesce textual chunks of ONE logical operation, using Python ints.

    A 270 Mb match may be written as adjacent <=28-bit = items; those are not
    separate events. Likewise a gap crossing an ownership boundary is charged
    once, not once per window or serialized chunk. Never re-encode a long run.
    """
    pending = None
    for size, op in operations:
        if type(size) is not int or not 1 <= size <= wa.LIMIT or op not in ("=","X","I","D"):
            raise wa.ExperimentError("unsupported recovered path operation")
        if pending is not None and op == pending[1]:
            pending = (pending[0] + size, op)
        else:
            if pending is not None:
                yield pending
            pending = (size, op)
    if pending is not None:
        yield pending


@dataclass(frozen=True)
class PathScore:
    key: str
    query: str
    target: str
    strand: str
    query_length: int
    query_start: int
    query_end: int
    target_start: int
    target_end: int
    matches: int
    block_length: int
    ambiguous: int
    gap_bases: int
    gap_openings: int
    gap_lengths: tuple[int, ...]
    mismatches_including_ambiguity: int
    event_identity: float
    dp_max0: int
    path_sha256: str
    query_sha256: str
    target_sha256: str
    index_sha256: str | None


def score_path(hit, query, target, *, key, index_sha256=None):
    """Bounded sequence scan: native mlen/blen/nn, ms=dp_max0, gap events.

    Scores come only from original bases + the accepted =XID path, not any PAF
    AS/ms/cm/s1/MAPQ. Original inputs and producer identity must still be checked
    by the enclosing experiment. Sequence working memory is O(CHUNK); gap summaries are O(number of gaps).
    """
    if index_sha256 is not None and (type(index_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}",index_sha256) is None):
        raise wa.ExperimentError("invalid original index-part hash for path score")
    if type(key) is not str or not key or len(key) > 4096:
        raise wa.ExperimentError("path score requires a bounded candidate identity")
    if (hit.query not in query.records or hit.target not in target.records
            or hit.qlen != query.records[hit.query]["length"]
            or hit.tlen != target.records[hit.target]["length"]
            or not 0 < hit.qlen <= wa.INT32_MAX or not 0 < hit.tlen <= wa.INT32_MAX
            or not 0 <= hit.qs < hit.qe <= hit.qlen
            or not 0 <= hit.ts < hit.te <= hit.tlen or hit.strand not in ("+", "-")):
        raise wa.ExperimentError("path score identity or coordinates disagree with original inputs")
    if not hit.ops or len(hit.ops) > MAX_OPERATIONS:
        raise wa.ExperimentError("recovered path exceeds the bounded operation count")
    # mm_update_extra receives an already fixed CIGAR. Do not silently trim a
    # leading gap and then claim the old recovered coordinates were native.
    if hit.ops[0][1] in ("I","D"):
        raise wa.ExperimentError("native path scoring requires normalized, non-gap leading operation")
    matches = block = ambiguous = gap_bases = 0
    qoff, toff, current, maximum = 0, hit.ts, 0.0, 0.0
    gaps = []
    digest = hashlib.sha256()
    digest.update(json.dumps([hit.query,hit.qlen,hit.qs,hit.qe,hit.strand,
                              hit.target,hit.tlen,hit.ts,hit.te],separators=(",", ":")).encode("ascii"))
    for size, op in logical_operations(hit.ops):
        digest.update(f";{size}{op}".encode("ascii"))
        if op in "ID":
            gaps.append(size)
            gap_bases += size
            # asm10 q=16/e=2; charge the LOGICAL gap once, outside chunk loop.
            current = max(0.0, current - (16 + 2.0 * native_log2(1.0 + size)))
        for offset in range(0, size, wa.CHUNK):
            n = min(wa.CHUNK, size-offset)
            qb = tb = b""
            if op in wa.Q_OPS:
                if hit.strand == "+":
                    qb = query.fetch(hit.query,hit.qs+qoff+offset,hit.qs+qoff+offset+n).translate(wa.NT)
                else:
                    qb = query.fetch(hit.query,hit.qe-qoff-offset-n,hit.qe-qoff-offset).translate(wa.NT).translate(wa.RC)[::-1]
            if op in wa.T_OPS:
                tb = target.fetch(hit.target,toff+offset,toff+offset+n).translate(wa.NT)
            if op == "=":
                if qb != tb:
                    raise wa.ExperimentError("scored = operation disagrees with original bases")
                amb = qb.count(b"N")
                matches += n-amb
                if amb == 0:
                    current += n
                    maximum = max(maximum,current)
                elif amb == n:
                    current = max(0.0,current-n)
                else:
                    for run in _CANONICAL_OR_N.finditer(qb):
                        length = run.end()-run.start()
                        if qb[run.start()] == ord("N"):
                            current = max(0.0,current-length)
                        else:
                            current += length
                            maximum = max(maximum,current)
            elif op == "X":
                if any(a == b for a,b in zip(qb,tb)):
                    raise wa.ExperimentError("scored X operation disagrees with original bases")
                amb = qb.count(b"N")+tb.count(b"N")
                # Every value in this run is negative: aggregation preserves
                # the native zero reset and maximum, even with ambiguous bases.
                current = max(0.0,current-(9*(n-amb)+amb))
            else:
                amb = (qb if op == "I" else tb).count(b"N")
            block += n-amb
            ambiguous += amb
        qoff += size if op in wa.Q_OPS else 0
        toff += size if op in wa.T_OPS else 0
    if qoff != hit.qe-hit.qs or toff != hit.te:
        raise wa.ExperimentError("scored CIGAR does not consume the original query/target intervals")
    if (matches,block) != (hit.matches,hit.block):
        raise wa.ExperimentError("scored mlen/blen disagree with recovered PAF")
    if block > wa.INT32_MAX or gap_bases > wa.INT32_MAX or ambiguous >= 2**30:
        raise wa.ExperimentError("native statistic fields would overflow supported representation")
    mismatch_count = block+ambiguous-matches-gap_bases
    denominator = block+ambiguous-gap_bases+len(gaps)
    if mismatch_count < 0 or denominator <= 0 or block+ambiguous > wa.INT32_MAX:
        raise wa.ExperimentError("native event statistics exceed supported int32 arithmetic")
    dp_max0 = int(maximum+0.499)
    if not 0 <= dp_max0 <= wa.INT32_MAX:
        raise wa.ExperimentError("native local maximum exceeds int32 score range")
    return PathScore(key,hit.query,hit.target,hit.strand,hit.qlen,hit.qs,hit.qe,hit.ts,hit.te,
                     matches,block,ambiguous,gap_bases,len(gaps),tuple(gaps),mismatch_count,
                     matches/denominator,dp_max0,digest.hexdigest(),
                     query.identity["sha256"],target.identity["sha256"],index_sha256)


def replay_native_rank_adjustment(scores, *, query_length):
    """Only mm_update_dp_max over a supplied FIRST-FILTERED full-query set.

    Native min-count filtering and actual DP candidate discovery must occur
    BEFORE this boundary. Enforce mlen/dp_max minima, but do NOT invent anchors,
    filter a raw window pool or certify that the supplied set is complete.
    Input order is original post-DP order BEFORE hit-sort; the first equal
    maximum controls the event-identity reference, just as upstream does.
    """
    if type(query_length) is not int or not 1 <= query_length <= wa.INT32_MAX:
        raise wa.ExperimentError("ranking requires one original int32 query length")
    if not isinstance(scores,(list,tuple)) or len(scores) > ps.MAX_CANDIDATES:
        raise wa.ExperimentError("rank adjustment requires a bounded original candidate set")
    if any(type(row) is not PathScore for row in scores):
        raise wa.ExperimentError("rank adjustment requires checked full-path scores")
    if len({r.key for r in scores}) != len(scores):
        raise wa.ExperimentError("duplicate full-path candidate identity")
    if any(r.index_sha256 is None for r in scores):
        raise wa.ExperimentError("rank adjustment requires a bound original index part")
    identities = {(r.query,r.query_length,r.query_sha256,r.target_sha256,r.index_sha256) for r in scores}
    if len(identities) > 1 or any(r.query_length != query_length for r in scores):
        raise wa.ExperimentError("rank adjustment cannot mix original queries or source identities")
    if any(not (0 <= r.query_start < r.query_end <= query_length
                   and math.isfinite(r.event_identity) and 0 <= r.event_identity <= 1
                   and 0 <= r.mismatches_including_ambiguity <= wa.INT32_MAX
                   and len(r.gap_lengths) == r.gap_openings
                   and sum(r.gap_lengths) == r.gap_bases
                   and all(type(n) is int and n > 0 for n in r.gap_lengths)) for r in scores):
        raise wa.ExperimentError("invalid checked full-path rank statistics")
    if any(r.matches < 40 or r.dp_max0 < 200 for r in scores):
        raise wa.ExperimentError("rank input must already pass native first-filter match/DP thresholds")
    maximum = second = -1
    best = None
    for row in scores:
        if row.dp_max0 > maximum:
            second,maximum,best = maximum,row.dp_max0,row
        elif row.dp_max0 > second:
            second = row.dp_max0
    fraction = ps.f32(0.9)
    reason = "applied"
    if query_length < 500:
        reason = "query_shorter_than_rank_min_len"
    elif len(scores) < 2:
        reason = "fewer_than_two_candidates"
    elif best.query_end-best.query_start < query_length*fraction:
        reason = "best_path_below_query_coverage_threshold"
    elif second < maximum*fraction:
        reason = "runner_up_below_score_threshold"
    b2 = None
    if reason == "applied":
        divergence = max(1.0-best.event_identity,0.02)
        b2 = 0.5/divergence
        if b2 < 9:  # Pinned a=1, b=9; preserve the upstream fallback exactly.
            b2 = 1.0/9
    output = []
    for row in scores:
        dp_max = row.dp_max0
        if b2 is not None:
            gap_cost = 0.0
            for length in row.gap_lengths:
                gap_cost += b2+native_log2(1.0+length)
            raw = row.matches-b2*row.mismatches_including_ambiguity-gap_cost+0.499
            integer = int(raw)  # C truncation toward zero, THEN lower clamp.
            if not -2**31 <= integer <= wa.INT32_MAX:
                raise wa.ExperimentError("native corrected-score cast would overflow int32")
            dp_max = max(0,integer)
        output.append({"key":row.key,"dp_max0":row.dp_max0,"dp_max":dp_max,
                       "passes_second_dp_threshold":dp_max >= 200})
    return {"schema":1,"query_length":query_length,"rank_adjustment_applied":b2 is not None,
            "reason":reason,"index_sha256":scores[0].index_sha256 if scores else None,
            "best_path":best.key if best else None,"mismatch_gap_factor":b2,
            "scores":output,"candidate_completeness_certified":False,
            "original_anchor_count_certified":False,"production_ready":False,
            "mapq_reconstructed":False,"execution_validated":False}


def write_guided_path_scores(source, output, query, target, *, index_sha256):
    """Branch diagnostic integration: sidecar ONLY, no ranking or PAF edits.

    The guided candidate set is still provisional and may not have native
    original-anchor counts. Therefore do not invoke global rank adjustment here.
    """
    if output.exists() or output.resolve() == source.resolve():
        raise wa.ExperimentError("path scoring requires a fresh sidecar, not an overwrite")
    before_hash = wa.sha256(source)
    whole = {name:wa.Window(name,name,r["length"],0,r["length"],0,r["length"])
             for name,r in query.records.items()}
    pending = output.with_suffix(output.suffix+".pending")
    rows = 0
    with source.open("rb") as inp,pending.open("x") as out:
        while raw := inp.readline(MAX_PAF_LINE+1):
            if len(raw)>MAX_PAF_LINE or not raw.endswith(b"\n"):
                raise wa.ExperimentError("incomplete or oversized guided score input")
            rows += 1
            hit = wa.parse_hit(raw.decode("ascii"),whole,target.records)
            result = score_path(hit,query,target,key=f"guided-row-{rows}",index_sha256=index_sha256)
            out.write(json.dumps({"row":rows,**asdict(result)},separators=(",", ":"))+"\n")
    if not rows:
        raise wa.ExperimentError("empty guided PAF is not path-score recovery")
    if wa.sha256(source) != before_hash:
        raise wa.ExperimentError("guided PAF changed during conditional score recovery")
    pending.replace(output)
    return {"rows":rows,"path":str(output),"sha256":wa.sha256(output),"source_sha256":before_hash,
            "index_sha256":index_sha256,
            "scoring_implementation_sha256":wa.sha256(Path(__file__)),
            "selection_implementation_sha256":wa.sha256(Path(ps.__file__)),
            "upstream":dict(ps.UPSTREAM),"path_conditional_only":True,
            "global_rank_adjustment_applied":False,"candidate_completeness_certified":False,
            "original_anchor_count_certified":False,"AS_reconstructed":False,
            "mapq_reconstructed":False,"production_ready":False,"execution_validated":False}
