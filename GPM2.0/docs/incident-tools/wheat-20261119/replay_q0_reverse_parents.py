"""Counterfactual parent planning on one immutable, completed natural panel.

The shortlist only sees base reference and cross-assembly alignments. Archived
regional input geometry is an oracle for evaluating it, never planner input.
No mapper, production files, or evidence manifests are written by this probe.
"""
import argparse
from bisect import bisect_right
from collections import defaultdict
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from lgz_core import q0_preparation as prep, q0_admission as admission
from lgz_core.q0_frontier_scope import (UnsearchedWindows, audit_selected_scope,
                                        decision_frontier, selected_proof_frontier, window_touches_frontier)
from lgz_core.q0_sources import Interval, Q0EvidenceError, merged_intervals
from probe_q0_decision_frontier import compare, projected_task, subset_input


class Ranges:
    def __init__(self, spans):
        self.spans = merged_intervals(spans)
        self.ends = tuple(s.end for s in self.spans)

    def touches(self, span):
        i = bisect_right(self.ends, span.start)
        return i < len(self.spans) and self.spans[i].start < span.end


def shortlist(base, demand, *, target_context=10_000, reference_context=10_000):
    """Keep whole source parents, using conservative envelopes only as routing hints.

    The target may be the only side touching demand. On that side expand by
    the original target context. On the query side use the per-chromosome hull
    of reference hits (not just their union): partial routing can bridge flanks.
    Neither a coarse envelope nor a hit in this index is positive join evidence.
    """
    parts = base.parts
    if not demand:
        return set(parts), {'abstain': 'no_demand'}
    demands = {s: Ranges(spans) for s, spans in demand.items()}
    direct, unresolved, linked, ref_hits = set(), set(), set(), set()
    bands = defaultdict(list)
    for source, spans in demand.items():
        length = len(base.sources[source])
        for span in spans:
            if span.end > length:
                raise Q0EvidenceError('unbound question coordinates')
            expanded = Interval(max(0, span.start-target_context), min(length, span.end+target_context))
            found = False
            for hit in base.reference_hits.get(source, ()):
                if expanded.intersection(hit.query):
                    found = True
                    bands[hit.target_name].append(hit.target)
            # A question without reference support cannot rule out competitors.
            if not found:
                return set(parts), {'abstain': 'unanchored_question'}
    corridors = {chrom: Ranges(rows) for chrom, rows in bands.items()}
    partners = defaultdict(list)
    for link in base.pair_links:
        hit = link.hit
        q = Interval(hit.query.start+link.query_offset, hit.query.end+link.query_offset)
        t = Interval(hit.target.start+link.target_offset, hit.target.end+link.target_offset)
        for src, region, peer, locus in ((link.query_source,q,link.target_source,t),
                                         (link.target_source,t,link.query_source,q)):
            if src in demands and demands[src].touches(region):
                partners[peer].append(locus)
    partners = {s: Ranges(v) for s,v in partners.items()}
    for key, part in parts.items():
        s, region = part.source, part.interval
        if s in demands and demands[s].touches(region):
            direct.add(key)
        if s in partners and partners[s].touches(region):
            linked.add(key)
        bounds = {}
        for hit in base.reference_hits.get(s, ()):
            if hit.query.intersection(region):
                chrom = hit.target_name
                lo, hi = bounds.get(chrom, (hit.target.start, hit.target.end))
                bounds[chrom] = min(lo, hit.target.start), max(hi, hit.target.end)
        if not bounds:
            unresolved.add(key)
        for chrom, (lo,hi) in bounds.items():
            if chrom in corridors and corridors[chrom].touches(Interval(max(0,lo-reference_context),
                    min(base.reference_lengths[chrom],hi+reference_context))):
                ref_hits.add(key)
    return direct | unresolved | linked | ref_hits, {'direct':len(direct), 'base_pair_neighbors':len(linked),
            'reference_competitors':len(ref_hits), 'unanchored_parents_retained':len(unresolved)}


def load_panel(root, panel, ready):
    if {r['path']:r['sha256'] for r in ready['inputs']} != panel['artifacts'] or 'decision_frontier' in ready['policy']:
        raise ValueError('not the frozen full evidence for this panel')
    ref = root/'reference-lengths.json'
    if [row['fasta_relpath'] for row in prep.table(root, 'metadata/reference.tsv', ('fasta_relpath',))] != [ref.name]:
        raise ValueError('invalid panel reference adapter')
    lengths = json.loads(ref.read_text()); fasta = admission.read_fasta
    if not lengths or any(type(n) is not int or not 0 < n <= 2**34 for n in lengths.values()):
        raise ValueError('invalid reference lengths')
    with patch.object(admission, 'read_fasta', lambda path: list((k,range(n)) for k,n in lengths.items())
                      if path == ref else fasta(path)):
        return admission.load_evidence_input(root)


def alternatives(construction):
    # Compare biological path geometry, not IDs which can differ by evidence row.
    return {chrom: { (tuple((x.source,x.interval,x.orientation) for x in p.slices),
                      tuple(j.kind for j in p.joins)) for p in result.alternatives }
            for chrom,result in construction.paths.items()}


def has_unsearched_context(arm, selection):
    """The frozen verifier predates the typed omission exception; fail closed."""
    try:
        audit_selected_scope(arm, selection.admission, selection.paths)
    except Q0EvidenceError as exc:
        if str(exc) not in {
            f'q0 scoped {kind} has unsearched competing context; rerun with full supplemental evidence'
            for kind in ('placement', 'pair evidence')
        }:
            raise
        return True
    return False


def replay(root, panel):
    ready = prep.load_verified_evidence(root)
    data = load_panel(root,panel,ready); base = subset_input(data,set())
    base = replace(base,pair_links=tuple(l for l in base.pair_links if l.query_source.dataset != l.target_source.dataset))
    first = admission.select_q0_paths(base); demand = decision_frontier(first)
    # Freeze the first independent prediction BEFORE touching window descriptors.
    parents, reasons = shortlist(base,demand)
    outputs = {r['path']:r for r in ready['outputs']}
    windows, native = {}, set()
    for task in data.catalog['supplementary_alignments']:
        paf = task['paf']
        if paf in windows or paf in native:
            raise ValueError('duplicate task')
        if task['kind'] != 'regional_discovery':
            native.add(paf); continue
        rel = task['receipt']
        if prep.identity(root,rel) != outputs[rel]:
            raise ValueError('unbound projection receipt')
        spec = prep.json_file(prep.artifact_path(root,rel))['spec']
        projected_task(task,spec,data.parts,{})  # validate original axes/inventory
        windows[paf] = SimpleNamespace(**spec['query']), tuple(SimpleNamespace(**r) for r in spec['targets'])
    kept = set(); phases = []; guard = 'unresolved'; false_negatives = set(); considered = set()
    for i in range(3):
        oracle, offered = set(), set()
        for paf,(q,ts) in windows.items():
            if q.segment_id in parents:
                offered.add(paf)
            if window_touches_frontier(q,ts,data.parts,demand):
                oracle.add(paf)
        missed = oracle-offered-kept; false_negatives.update(missed); considered.update(offered)
        kept |= (oracle & offered)
        phases.append({'round':i,'demand_sources':len(demand or {}), 'eligible_parents':len(parents),
            'reasons':reasons,'offered_archived_windows':len(offered),'forward_required':len(oracle),
            'missed_required':len(missed),'retained_cumulative':len(kept)})
        omitted = UnsearchedWindows()
        for paf,(q,ts) in windows.items():
            if paf not in kept:
                omitted.observe(q,ts,data.parts)
        arm = subset_input(data, kept|native)
        arm = replace(arm,catalog={'supplement_scope':{'unsearched_part_intervals':omitted.record()}})
        selection = admission.select_q0_paths(arm)
        if not any(x.path for x in selection.paths.values()):
            guard='no_path'; break
        if not has_unsearched_context(arm, selection):
            guard = 'passed'
            break
        if not demand or i == 2:
            break
        proof = selected_proof_frontier(arm, selection.admission, selection.paths)
        updated = {s: merged_intervals((*demand.get(s, ()), *proof.get(s, ()))) for s in demand.keys() | proof.keys()}
        if updated == demand:
            break
        demand = updated
        parents, reasons = shortlist(base, demand)
    report={'schema':'q0_reverse_parent_replay_v1','panel':panel['panel'],'ready':data.ready_manifest_identity,
            'regional_parents':len({q.segment_id for q,_ in windows.values()}),'regional_windows':len(windows),
            'native_retained':len(native),'rounds':phases,'missed_forward_required':len(false_negatives),
            'never_needed_forward_parent_planning_windows':len(windows)-len(considered),
            'guard':guard,'new_mapper_executions':0,'fixed_archived_task_graph':True}
    if guard=='passed':
        full=admission.construct_q0(data); selected=admission.construct_q0(arm)
        report['comparison']=compare(full,selected)
        a,b=alternatives(full),alternatives(selected)
        report['alternative_paths']={c:{'full':len(a[c]),'selected':len(b[c]),'lost':len(a[c]-b[c]),
            'new':len(b[c]-a[c])} for c in a}
    if prep.load_verified_evidence(root)!=ready: raise ValueError('source changed during replay')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path);p.add_argument('panel',type=Path);p.add_argument('out',type=Path)
    p.add_argument('--panel-sha',required=True); args=p.parse_args()
    root=args.root.resolve(strict=True); raw=args.panel.read_bytes()
    if (args.out.resolve().is_relative_to(root) or args.out.exists() or sha256(raw).hexdigest()!=args.panel_sha):
        raise SystemExit('panel identity or isolated output path invalid')
    result=replay(root,json.loads(raw))
    with args.out.open('x') as f: json.dump(result,f,sort_keys=True,indent=2);f.write('\n')
