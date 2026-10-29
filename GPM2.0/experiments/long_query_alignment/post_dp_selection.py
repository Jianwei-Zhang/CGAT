"""Pinned v2.31 post-skeleton parent/secondary selection, NOT PAF recovery.

Port of hit.c::mm_hit_sort/mm_set_parent/mm_select_sub for the Server asm10
single-segment, ordinary-reference case. Upstream MIT notice is retained in
MINIMAP2_LICENSE.txt. This module never invokes or modifies minimap2.

IMPORTANT: NativePostDpState describes FULL-QUERY state AFTER the skeleton's
filters and optional mm_update_dp_max, BEFORE mm_hit_sort. Window PAF AS/ms/cm,
preliminary PAF s1, and locally inferred ordering are NOT substitutes. Earlier
subsc/n_sub/dp_max2 values are explicit because upstream does not reset them all.
The raw all-chain window pool is not an accepted input conversion.

This is a branch implementation awaiting execution/oracle validation. It neither
produces PAF nor reconstructs DP, pre-DP state, scores or MAPQ. The guided path's
coverage/corridor refusal controls remain unchanged.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import struct

from windowed_alignment import ExperimentError


UPSTREAM = {
    "version": "2.31-r1302",
    "align.c_sha256": "8abb12d446f372afe11a511bf0fc12da47ed077600543851d4b6ad6282a51389",
    "hit.c_sha256": "157c06aa2c40c1684985465bac64f57b2da5c84657d12483bc77ee5a35279fac",
    "ksort.h_sha256": "2ed9cf5fc6bcae55ee961df7222fe1ef0ea8f5dc93156990f5ab0c277e0026e0",
    "misc.c_sha256": "c4cb4bc5cf4048220417b6b3c1be9bf46902a945abe3879ab507e61e12b642ef",
    "map.c_sha256": "e86014fdb4c8443f0c73ab1e81f8d71e25b94878de5ecbc436865c315362b6e5",
    "minimap.h_sha256": "fe070ea30df31df5b8991eaf5680838ec2a345017f8ac0e5851aa430e491b0dc",
    "mmpriv.h_sha256": "6032156ee4bd0e0511a755fc9fcd56b8e010834b2fc774c89066b05d20248c7e",
    "options.c_sha256": "8ffd0235798712c87c8126f54503a75066153d37691cc48f9cd6ec618920bd9e",
}
INT_MAX = 2**31 - 1
MAX_CANDIDATES = 100_000
# Pinned asm10 defaults; these are NOT additional customer configuration.
MASK_LEVEL = 0.5
MASK_LEN = INT_MAX
PRI_RATIO = 0.8
MIN_DIFF = 19 * 2
BEST_N = 50
SUB_DIFF = 1 * 2 + 9


def f32(value):
    """Round EACH float operation used in native parent/ratio comparisons."""
    return struct.unpack("<f", struct.pack("<f", value))[0]


@dataclass(frozen=True)
class NativePostDpState:
    # No defaults: missing original metadata must not silently become zero.
    key: str
    query_start: int
    query_end: int
    target_id: int                 # Original MMI part-local rid, not lexical ID.
    target_start: int
    target_end: int
    reverse: bool
    chain_score: int               # mm_reg1_t::score after original-seed splits.
    original_chain_score: int      # score0, NOT fragment score or DP score.
    anchor_count: int              # cnt from original whole-query anchors.
    matches: int                   # Native mlen, not an AS-derived substitute.
    block_length: int              # Native blen (ambiguous positions excluded).
    dp_max: int                    # AFTER skeleton's optional global correction.
    previous_subscore: int         # subsc carried over from pre-DP state.
    previous_subcount: int         # n_sub carried over from pre-DP state.
    previous_dp_max2: int          # p->dp_max2 before post-DP parent selection.
    native_hash: int               # Original r.hash, NOT hash(query/window ID).

    def validate(self, query_length):
        if type(self.key) is not str or not self.key or len(self.key) > 4096:
            raise ExperimentError("candidate requires a bounded original-state identity")
        for name in ("query_start", "query_end", "target_id", "target_start", "target_end",
                     "chain_score", "original_chain_score", "anchor_count", "matches", "block_length",
                     "dp_max", "previous_subscore", "previous_subcount", "previous_dp_max2"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= INT_MAX:
                raise ExperimentError(f"native {name} must be an explicit nonnegative int32")
        if type(self.native_hash) is not int or not 0 <= self.native_hash < 2**32:
            raise ExperimentError("original native hash must be an explicit uint32")
        if type(self.reverse) is not bool:
            raise ExperimentError("original native strand must be an explicit bool")
        if not (self.query_start < self.query_end <= query_length
                and self.target_start < self.target_end):
            raise ExperimentError("native candidate coordinates exceed supported sequence bounds")
        if self.chain_score > INT_MAX - MIN_DIFF:
            raise ExperimentError("native score plus secondary tolerance would overflow int32")
        if not 0 < self.original_chain_score or self.matches > self.block_length:
            raise ExperimentError("invalid original chain score or native match/block length")
        # Input phase is deliberately AFTER mm_filter_regs. No silent repair of
        # a raw -P PAF or unsupported inversion/seg_split/alt-reference record.
        if self.anchor_count < 3 or self.matches < 40 or self.dp_max < 200:
            raise ExperimentError("candidate is not filtered asm10 post-skeleton state")


@dataclass(frozen=True)
class SelectedCandidate:
    state: NativePostDpState
    id: int
    parent: int
    subscore: int
    subcount: int
    dp_max2: int
    sam_primary: bool


def _initial(state, number):
    return SelectedCandidate(state, number, number, state.previous_subscore,
                             state.previous_subcount, state.previous_dp_max2, False)


def _native_sort(states):
    """Port ksort.h radix order, including ties in pools larger than 64.

    A Python stable sort is NOT equivalent: native radix partitioning is
    in-place and unstable for large buckets, followed by a reverse copy.
    Hash ties occur naturally when a whole-query chain is split by DP.
    """
    rows = [((r.dp_max << 32) | r.native_hash, r) for r in states]

    def insertion(start, end):
        for i in range(start + 1, end):
            if rows[i][0] < rows[i - 1][0]:
                item, j = rows[i], i
                while j > start and item[0] < rows[j - 1][0]:
                    rows[j] = rows[j - 1]
                    j -= 1
                rows[j] = item

    def radix(start, end, shift):
        counts = [0] * 256
        for i in range(start, end):
            counts[(rows[i][0] >> shift) & 255] += 1
        starts, ends, cursor = [], [], start
        for count in counts:
            starts.append(cursor)
            cursor += count
            ends.append(cursor)
        positions = list(starts)
        for bucket in range(256):
            while positions[bucket] != ends[bucket]:
                item = rows[positions[bucket]]
                destination = (item[0] >> shift) & 255
                if destination != bucket:
                    while destination != bucket:
                        displaced = rows[positions[destination]]
                        rows[positions[destination]] = item
                        positions[destination] += 1
                        item = displaced
                        destination = (item[0] >> shift) & 255
                    rows[positions[bucket]] = item
                positions[bucket] += 1
        if shift:
            for left, right in zip(starts, ends):
                if right - left > 64:
                    radix(left, right, max(0, shift - 8))
                elif right - left > 1:
                    insertion(left, right)

    if len(rows) <= 64:
        insertion(0, len(rows))
    else:
        radix(0, len(rows), 56)
    return [row for _, row in reversed(rows)]


def _uncovered(start, end, primaries):
    """Union coverage over ALL existing primaries, not only a proposed parent."""
    intervals = sorted((max(start, r.state.query_start), min(end, r.state.query_end))
                       for r in primaries if r.state.query_start < end and start < r.state.query_end)
    cursor, uncovered = start, 0
    for left, right in intervals:
        uncovered += max(0, left - cursor)
        cursor = max(cursor, right)
    return uncovered + max(0, end - cursor)


def _set_parent(records):
    if not records:
        return records
    primary_ids = [0]
    for i in range(1, len(records)):
        row = records[i]
        si, ei = row.state.query_start, row.state.query_end
        uncovered = _uncovered(si, ei, [records[j] for j in primary_ids])
        parent_id = None
        for j in primary_ids:
            parent = records[j]
            sj, ej = parent.state.query_start, parent.state.query_end
            overlap = min(ei, ej) - max(si, sj)
            if overlap <= 0:
                continue
            small, large = sorted((ei - si, ej - sj))
            # C promotes int to float BEFORE division; Python's ol / int before
            # f32 rounding differs when genomic coordinates exceed 2**24.
            overlap_fraction = f32(f32(overlap) / f32(small))
            uncovered_fraction = f32(f32(uncovered) / f32(large))
            if (f32(overlap_fraction - uncovered_fraction) > f32(MASK_LEVEL)
                    and uncovered <= MASK_LEN):
                parent_id = parent.parent
                count_sub = row.state.anchor_count >= parent.state.anchor_count
                dp_max2 = parent.dp_max2
                # Native excludes SAME rid/rs/re AND ol==min, NOT exact PAF
                # query geometry and NOT a same-strand condition.
                different_dp_hit = (parent.state.target_id != row.state.target_id
                    or parent.state.target_start != row.state.target_start
                    or parent.state.target_end != row.state.target_end or overlap != small)
                if different_dp_hit:
                    dp_max2 = max(dp_max2, row.state.dp_max)
                    if parent.state.dp_max - row.state.dp_max <= SUB_DIFF:
                        count_sub = True
                subcount = parent.subcount + int(count_sub)
                if subcount > INT_MAX:
                    raise ExperimentError("native secondary count would exceed int32")
                records[j] = replace(parent, subscore=max(parent.subscore, row.state.chain_score),
                                     subcount=subcount, dp_max2=dp_max2)
                break
        if parent_id is None:
            # The FIRST primary retains its prior n_sub; later new primaries
            # reset n_sub only. Neither subsc nor dp_max2 is globally zeroed.
            records[i] = replace(row, parent=i, subcount=0)
            primary_ids.append(i)
        else:
            records[i] = replace(row, parent=parent_id)
    return records


def replay_post_dp_selection(states, *, query_length):
    """Reproduce only native hit-sort + post-DP parent/best_n selection.

    Accepted input is complete caller-supplied native state for ONE original
    query and ONE original index part, in original pre-sort order. The caller
    must still prove producer success, source identities, candidate completeness
    and the provenance of EVERY field. This function does not certify those.
    No guessed AS threshold, no window-local selection and no new MAPQ values.
    """
    if type(query_length) is not int or not 1 <= query_length <= INT_MAX:
        raise ExperimentError("selection requires one original int32 query length")
    if not isinstance(states, (list, tuple)) or len(states) > MAX_CANDIDATES:
        raise ExperimentError("native candidate pool exceeds bounded supported size")
    if any(type(row) is not NativePostDpState for row in states):
        raise ExperimentError("selection requires full native state, not PAF dictionaries")
    for row in states:
        row.validate(query_length)
    if len({row.key for row in states}) != len(states):
        raise ExperimentError("duplicate native candidate identity")
    ordered = _native_sort(states)
    records = _set_parent([_initial(row, i) for i, row in enumerate(ordered)])
    kept, decisions, secondary_count = [], [], 0
    for row in records:
        parent = records[row.parent]
        if row.id == row.parent:
            reason, retain = "primary", True
        elif ((f32(row.state.chain_score) >= f32(f32(parent.state.chain_score) * f32(PRI_RATIO))
               or row.state.chain_score + MIN_DIFF >= parent.state.chain_score)
              and secondary_count < BEST_N):
            # mm_select_sub's duplicate check also does NOT compare strand.
            duplicate = all(getattr(row.state, key) == getattr(parent.state, key)
                for key in ("query_start", "query_end", "target_id", "target_start", "target_end"))
            retain, reason = not duplicate, "identical_hit" if duplicate else "retained_secondary"
            secondary_count += int(retain)
        else:
            retain = False
            reason = "secondary_limit" if secondary_count >= BEST_N else "chain_score_ratio_and_difference"
        decisions.append({"candidate": row.state.key, "parent": parent.state.key,
                          "retained": retain, "reason": reason,
                          "chain_score": row.state.chain_score,
                          "parent_chain_score": parent.state.chain_score})
        if retain:
            kept.append(row)
    # Same parent/id synchronization and first-primary convention as sync_regs
    # / set_sam_pri, with no new selection or MAPQ claims.
    ids = {row.id: i for i, row in enumerate(kept)}
    first_primary = True
    output = []
    for row in kept:
        primary = row.id == row.parent
        output.append(replace(row, id=ids[row.id], parent=ids[row.parent],
                              sam_primary=primary and first_primary))
        if primary:
            first_primary = False
    return {"schema": 1, "upstream": dict(UPSTREAM), "query_length": query_length,
            "input_candidates": len(states), "retained_candidates": [asdict(row) for row in output],
            "decisions": decisions, "secondary_count": secondary_count,
            "phase": "post_skeleton_hit_sort_parent_secondary_selection",
            "post_dp_selection_implemented": True, "execution_validated": False,
            "candidate_completeness_certified": False, "input_provenance_certified": False,
            "mapq_reconstructed": False, "production_ready": False, "customer_validated": False}
