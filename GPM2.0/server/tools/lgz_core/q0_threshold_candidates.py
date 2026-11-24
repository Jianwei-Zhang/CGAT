"""Whole native candidate maps under the readless, non-exhaustive threshold contract."""
from bisect import bisect_left
from dataclasses import replace

from . import q0_preparation as prep
from .q0_admission import select_q0_paths
from .q0_paths import PairLink
from .q0_retained_hits import RetainedHit
from .q0_sources import Q0EvidenceError
from .q0_threshold_questions import questions


class DecisionState:
    """Private planning state, never evidence for publication. The normal reader audits anew."""
    def __init__(self, data, need, assignments):
        self.data, self.need, self.assignments = data, need, assignments
        self.seen = set()

    def observe(self, root, tasks):
        links = []
        parts = self.data.parts
        for task in tasks:
            paf = task["paf"]
            if paf in self.seen:
                continue
            q, t = ({k: parts[k].interval.length for k in task[n]} for n in ("query_ids", "target_ids"))
            for hit in prep.read_paf(prep.artifact_path(root, paf), query_lengths=q, target_lengths=t, artifact=paf):
                qp, tp = parts[hit.query_name], parts[hit.target_name]
                hit = RetainedHit.from_validated(hit, qp.segment_id, tp.segment_id)
                links.append(PairLink(hit, qp.source, tp.source, qp.interval.start, tp.interval.start))
            self.seen.add(paf)
        if links:
            self.data = replace(self.data, pair_links=self.data.pair_links + tuple(links))
            selection = select_q0_paths(self.data)
            self.need, _ = questions(self.data, selection, self.assignments)
            if not any(row.path is not None for row in selection.paths.values()):
                self.need = None  # An indeterminate selection cannot stop a competitor.


def axes(request):
    return tuple(request["query_ids"]), tuple(request["target_ids"])


def dispatch(root, catalog, requests, earlier, state, run):
    """One wave at a time. A cold and a warm workspace see the same evidence in planner order."""
    groups = {}
    for request in requests:
        groups.setdefault(axes(request), []).append(request)
    if not groups:
        return [], []
    # Earlier whole-native discoveries used this very mapper, preset and ordinary flags.
    # Preserve their logical aliases without searching or counting their axes as omitted.
    ready = {axes(t): t for t in earlier if axes(t) in groups}
    members = {k: frozenset(k[0]).union(k[1]) for k in groups}
    sources = {k: {catalog.parts[i].source for i in ids} for k, ids in members.items()}
    chromosomes = {k: {r["chromosome"] for r in rows} for k, rows in groups.items()}
    pending = [k for k in groups if k not in ready]
    if pending:
        state.observe(root, earlier)
    while pending:
        wave, occupied_sources, occupied_chrs = [], set(), set()
        open_ids = None
        if state.need is not None:
            # Source-local intervals are canonical, merged and sorted by questions().
            # Check each shared part once, not every shoulder against every candidate.
            starts = {s: tuple(v.start for v in vs) for s, vs in state.need.items()}
            open_ids = set()
            for i in {i for k in pending for i in members[k]}:
                p = catalog.parts[i]
                j = bisect_left(starts.get(p.source, ()), p.interval.end) - 1
                if j >= 0 and state.need[p.source][j].end > p.interval.start:
                    open_ids.add(i)
        for k in pending:
            if open_ids is not None and members[k].isdisjoint(open_ids):
                continue
            if sources[k].isdisjoint(occupied_sources) and chromosomes[k].isdisjoint(occupied_chrs):
                wave.append(k)
            # Even a waiting competitor keeps its place relative to later competitors.
            occupied_sources.update(sources[k])
            occupied_chrs.update(chromosomes[k])
        if not wave:
            break
        done = run([groups[k][0] for k in wave])
        if [axes(t) for t in done] != wave:
            raise Q0EvidenceError("threshold candidate wave lost a mapping or changed its axes")
        ready.update(zip(wave, done))
        pending = [k for k in pending if k not in ready]
        if pending:
            state.observe(root, done)
    kept = [{**ready[axes(r)], "kind": r["kind"], "request": r} for r in requests if axes(r) in ready]
    skipped = [r for r in requests if axes(r) not in ready]
    return kept, skipped


def omission_axes(skipped, sizes):
    ids = sorted({k for r in skipped for axis in axes(r) for k in axis})
    return [[k, [[0, sizes[k]]]] for k in ids]


def verify_stops(catalog, report):
    """No anonymous omissions, missing target axes, invented empty PAFs or skipped/executed aliases."""
    skipped = report.get("native_candidate_stops")
    if (not isinstance(skipped, list) or not skipped or report.get("requested") != "positive_threshold"
            or report.get("effective") != "decision_frontier" or "regional_partial_discovery" in catalog
            or "regional_candidate_discovery" in catalog):
        raise Q0EvidenceError("invalid native threshold stop scope")
    sizes = {s["segment_id"]: s["interval"]["end"]-s["interval"]["start"] for s in catalog["segments"]}
    seen = {t["request"]["chromosome"] for t in catalog["supplementary_alignments"] if t["kind"] == "candidate_chr"}
    executed = {axes(t) for t in catalog["supplementary_alignments"]}
    chromosome_targets = {}
    for row in catalog["candidates"]:
        chromosome_targets.setdefault(row["chromosome"], set()).add(row["segment_id"])
    for r in skipped:
        if (not isinstance(r, dict) or set(r) != {"kind", "chromosome", "query_ids", "target_ids"}
                or r["kind"] != "candidate_chr" or not isinstance(r["chromosome"], str) or not r["chromosome"]
                or r["chromosome"] in seen or any(not isinstance(r[n], list) or not r[n]
                    or any(not isinstance(k, str) or k not in sizes for k in r[n]) or sorted(set(r[n])) != r[n]
                    for n in ("query_ids", "target_ids"))
                or not set(r["query_ids"]).issubset(r["target_ids"])
                or set(r["target_ids"]) != chromosome_targets.get(r["chromosome"]) or axes(r) in executed):
            raise Q0EvidenceError("invalid or already executed native threshold competitor")
        seen.add(r["chromosome"])
    if report.get("unsearched_part_intervals") != omission_axes(skipped, sizes):
        raise Q0EvidenceError("native threshold stop differs from omitted query/target axes")
    return len(skipped)
