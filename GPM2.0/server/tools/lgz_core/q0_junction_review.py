"""One targeted look at alternatives to a supported slice beside an unproven join.

Reference co-location is only a routing hint. Never create a join or a placement
here: only verified, source-projected PAFs can go back to the ordinary selector.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass

from .q0_query_windows import QueryWindow, TargetWindow
from .q0_sources import Interval, Q0EvidenceError, merged_intervals
from .q0_threshold_questions import ends, facing_evidence, supported

REACH = 2000  # same shoulder as the unproven join request; not a whole contig search
_BIN = 16384  # index only, not a filter


def _starts(p, span, minimum):
    """Possible reference starts of a minimum-length run in ONE observed paired block."""
    runs = []
    for b in p.reference_blocks:
        lo = max(b.source.start, span.start); hi = min(b.source.end, span.end)
        if hi-lo < minimum:
            continue
        start = (b.reference.start + lo-b.source.start if p.orientation == '+' else
                 b.reference.end - (hi-b.source.start))
        runs.append(Interval(start, start+hi-lo-minimum+1))
    return merged_intervals(runs)


def covering_alternatives(sites, placements, excluded, minimum):
    """Index the two selected source ends separately. Never match a reference hull."""
    index = defaultdict(list)
    for pid, (p, s) in sites.items():
        sides = [_starts(p, side, minimum) for side in ends(s.interval, minimum)]
        if len(sides) != 2 or not all(sides):
            continue
        for side, rows in enumerate(sides):
            for r in rows:
                for b in range(r.start//_BIN, (r.end-1)//_BIN+1):
                    index[b].append((r.start, r.end, pid, 1 << side))
    if not index:
        return
    for rows in index.values(): rows.sort()
    for alt in placements:
        if alt.placement_id in excluded: continue
        hits = {}
        for r in _starts(alt, alt.interval, minimum):
            for b in range(r.start//_BIN, (r.end-1)//_BIN+1):
                for lo, hi, pid, bit in index.get(b, ()):
                    if lo >= r.end: break
                    if hi > r.start and sites[pid][0].source != alt.source:
                        hits[pid] = hits.get(pid, 0) | bit
        for pid, flags in hits.items():
            if flags == 3: yield pid, alt


def _shares(left, right):
    i = j = 0
    while i < len(left) and j < len(right):
        a, b = left[i], right[j]
        if a.intersection(b): return True
        i += a.end <= b.end; j += b.end <= a.end
    return False


def _face(p, left):
    n = p.interval.length
    return p.source_interval(Interval(max(0,n-REACH), n) if left else Interval(0,min(n,REACH)))


@dataclass(frozen=True, order=True)
class PairWindow:
    # Source-global forward coordinates until converted through the exact source-part frame.
    query: str
    query_span: Interval
    target: str
    target_span: Interval

    def windows(self, parts):
        def local(key, span):
            part = parts[key].interval
            if not part.contains(span): raise Q0EvidenceError('junction shoulder outside source part')
            return key, part.length, span.start-part.start, span.end-part.start
        q = local(self.query, self.query_span); t = local(self.target, self.target_span)
        return QueryWindow(*q, ((q[2], q[3]),)), TargetWindow(*t)


def possible_window(left, right, minimum):
    """Physical facing ends on both placements, sharing a contiguous reference run."""
    if left.source == right.source or left.chromosome != right.chromosome:
        return None
    a, b = _face(left, True), _face(right, False)
    if not _shares(_starts(left, a, minimum), _starts(right, b, minimum)):
        return None
    return PairWindow(left.segment_id, a, right.segment_id, b)


def _side(graph, left, right, joining_left, neighbor_slice, old_join, probe):
    """Cut bounds on the alternative for existing edges; otherwise an explicitly local probe."""
    if left.source == right.source: return (), None
    neighbor = left if joining_left else right
    keep = neighbor.local(neighbor_slice.interval)
    cuts = []
    for j in graph.joins(left.placement_id, right.placement_id):
        if old_join.kind == 'input_assembly_gap' and j.original_adjacency_id != old_join.original_adjacency_id:
            continue  # never replace a real input gap just because two references overlap
        if j.kind not in ('sequence_overlap', 'input_assembly_gap'): continue
        if joining_left and j.left_end > keep.start: cuts.append(j.right_start)
        if not joining_left and j.right_start < keep.end: cuts.append(j.left_end)
    if cuts or probe is None: return cuts, None
    # Known evidence rejected by the graph is not an invitation to bypass its ambiguity checks.
    links = graph.links.get(tuple(sorted((left.source, right.source))), ())
    if facing_evidence(left, right, links, graph.policy): return (), None
    return ([0] if joining_left else [left.interval.length]), probe


class Review:
    def __init__(self):
        self.proposals = []; self.counts = Counter()

    def observe(self, graph, path):
        if path is None: return
        ps = graph.placements; minimum = graph.policy.minimum_anchor_bp
        unresolved = set()
        for j in path.joins:
            if j.kind != 'reference_unknown': continue
            l, r = ps[j.left_id], ps[j.right_id]
            links = graph.links.get(tuple(sorted((l.source, r.source))), ())
            if not facing_evidence(l, r, links, graph.policy): unresolved.add(j.join_id)
        if not unresolved: return
        sites = {}; positions = {}
        for i,s in enumerate(path.slices):
            if not any(j.join_id in unresolved for j in path.joins[max(0,i-1):i+1]): continue
            p = ps[s.placement_id]; sides = ends(s.interval, minimum)
            anchors = merged_intervals(p.anchor_intervals)
            if (not sides or p.localization_kind not in ('reference','pairwise') or
                    not all(supported(side, anchors, minimum) for side in sides)): continue
            sites[p.placement_id] = (p,s); positions[p.placement_id] = i
        self.counts['supported_at_unproven_join'] += len(sites)
        for pid, alt in covering_alternatives(sites, ps.values(), set(path.nodes), minimum):
            self.counts['two_end_candidates'] += 1
            i = positions[pid]; incoming, outgoing = [0], [alt.interval.length]; a = b = None
            left = ps[path.nodes[i-1]] if i else None
            right = ps[path.nodes[i+1]] if i+1 < len(path.nodes) else None
            lp = possible_window(left, alt, minimum) if left and path.joins[i-1].join_id in unresolved else None
            rp = possible_window(alt, right, minimum) if right and path.joins[i].join_id in unresolved else None
            # No probe can be dispatched: avoid expensive graph/CIGAR checks on either side.
            if lp is None and rp is None: continue
            if left:
                s = path.slices[i-1]; j = path.joins[i-1]
                incoming,a = _side(graph,left,alt,True,s,j,lp)
            if not incoming: continue
            if right:
                s = path.slices[i+1]; j = path.joins[i]
                outgoing,b = _side(graph,alt,right,False,s,j,rp)
            if not outgoing or min(incoming) >= max(outgoing): continue
            if not (a or b):
                self.counts['both_flanks_already_supported'] += 1
                continue
            self.proposals.append((alt.source,alt.interval,tuple(k for k in (a,b) if k is not None)))

    def windows(self, selection):
        occupied = defaultdict(list)
        for result in selection.paths.values():
            path = result.path
            if path is None: continue
            for s in path.slices: occupied[s.source].append(s.interval)
            for j in path.joins:
                if j.gap_source is not None: occupied[j.gap_source].append(j.gap_interval)
        windows = set()
        for source,span,keys in self.proposals:
            if any(span.intersection(old) for old in occupied.get(source, ())): continue
            windows.update(keys)
        return sorted(windows)


def dispatch(review, selection, root, catalog, available, tool, preset, threads, reference_bases):
    from .q0_regional_mapping import prepare_regional_mapping, RegionalWorkLog
    plans=review.windows(selection);seen={t['paf'] for t in available};extra=[]
    print(f'LGZ q0 junction review: {dict(review.counts)} unique_local_pairs={len(plans)} '
          f'query_bp={sum(w.query_span.length for w in plans)} target_bp={sum(w.target_span.length for w in plans)}',flush=True)
    with RegionalWorkLog('threshold_junction_review') as work:
        for plan in plans:
            query,target=plan.windows(catalog.parts)
            task=work.run(prepare_regional_mapping,root,catalog,query,[target],tool,
                          reference_bases=reference_bases,preset=preset,threads=min(2,threads))
            if task['paf'] not in seen:
                extra.append(task);seen.add(task['paf'])
    return extra


def append_new_tasks(tasks, report, extra):
    """Only additional regional receipts count here, never ones already counted by a normal phase."""
    seen = {t['paf'] for t in tasks}
    added = []
    for t in extra:
        if t['paf'] in seen: continue
        tasks.append(t); added.append(t); seen.add(t['paf'])
    if added:
        report['junction_review_task_ids'] = [*report.get('junction_review_task_ids',()), *(t['task_id'] for t in added)]
    return added


def extra_count(catalog):
    report = catalog.get('supplement_scope', {})
    if 'junction_review_task_ids' not in report: return 0
    ids = report['junction_review_task_ids']; tasks = catalog['supplementary_alignments']
    if (report.get('effective') not in ('decision_frontier','full') or not isinstance(ids,list) or not ids or
            any(not isinstance(k,str) for k in ids) or len(ids)!=len(set(ids)) or
            ids != [t['task_id'] for t in tasks[-len(ids):]] or
            set(ids).intersection(t['task_id'] for t in tasks[:-len(ids)]) or
            any(t['kind']!='regional_discovery' or len(t['query_ids'])!=1 or len(t['target_ids'])!=1
                or t['query_ids']==t['target_ids'] for t in tasks[-len(ids):])):
        raise Q0EvidenceError('invalid junction review task inventory')
    return len(ids)


def extend_draft(root, receipt, catalog, extra):
    """Bind local evidence to a *private* generation before running the independent consumer."""
    from . import q0_preparation as prep
    from .common import stable_id
    tasks = list(catalog['supplementary_alignments']); scope = dict(catalog['supplement_scope'])
    added = append_new_tasks(tasks, scope, extra)
    if not added: return receipt
    payload = dict(catalog, supplementary_alignments=tasks, supplement_scope=scope)
    extra_count(payload)
    name = f"grt/evidence/q0_prepare/{stable_id('catalog',payload)}.json"
    prep.atomic_write_json(prep.workspace_artifact_path(root,name),payload)
    outputs = {r['path']:r for r in receipt['outputs'] if r['path']!=receipt['catalog']}
    for task in added:
        success = prep.artifact_path(root,task['receipt'])
        for r in [prep.identity(root,task['receipt']),*prep.json_file(success)['outputs']]:
            if outputs.setdefault(r['path'],r)!=r: raise Q0EvidenceError('junction review evidence dependency changed')
    outputs[name] = prep.identity(root,name)
    return dict(receipt,catalog=name,outputs=[outputs[k] for k in sorted(outputs)])


def verify_windows(spec):
    q = spec['query']; targets = spec['targets']
    if (len(targets)!=1 or q['cores']!=[[q['start'],q['end']]] or
            any(not 0 < t['end']-t['start'] <= REACH for t in (q,targets[0]))):
        raise Q0EvidenceError('junction review is not a bounded single-pair shoulder search')
