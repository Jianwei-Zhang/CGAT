"""Isolated locus-aware equivalence; no production imports/call-site changes.

Native PAF qualification, same-source ambiguity and exact duplicate scoring stay.
A union of coverage atoms must retain a common feasible reference locus. Unknown
atoms carry no constraint, but cannot bridge two disjoint anchored components.
This diagnostic changes scientific equivalence policy, not just performance.
"""
import inspect,textwrap
from bisect import bisect_left,bisect_right
from collections import defaultdict,Counter
from hashlib import sha256
from lgz_core import q0_coverage as coverage
from lgz_core.q0_sources import Interval,merged_intervals
from wheat_sparse_pair_graph_readonly import placement_index,overlaps


def intersection(a,b):
    if a is None:return b
    if b is None:return a
    i=j=0;out=[]
    while i<len(a) and j<len(b):
        x=a[i].intersection(b[j])
        if x is not None:out.append(x)
        if a[i].end<=b[j].end:i+=1
        else:j+=1
    return merged_intervals(out)


class ReferenceDomains:
    def __init__(self,placements,tolerance=100_000):
        self.tolerance=tolerance;self.placements=defaultdict(list);self.anchors={};self.bounds={};self.stats=Counter()
        for p in placements:
            self.placements[p.source].append(p)
            self.bounds[p.placement_id]=(min((v.start for v in p.reference_intervals),default=0),max((v.end for v in p.reference_intervals),default=0))
            rows=sorted(p.reference_blocks,key=lambda a:(a.source.start,a.source.end,a.reference.start))
            far=0;ends=[]
            for a in rows:far=max(far,a.source.end);ends.append(far)
            self.anchors[p.placement_id]=(rows,tuple(a.source.start for a in rows),tuple(ends))
        self.index={s:placement_index(rows) for s,rows in self.placements.items()}
    def atom(self,source,interval):
        exact=[];fallback=[]
        for _,p in overlaps(self.index.get(source,([],[],[])),interval):
            rows,starts,ends=self.anchors[p.placement_id]
            for a in rows[bisect_right(ends,interval.start):bisect_left(starts,interval.end)]:
                ov=a.source.intersection(interval)
                if ov is None:continue
                # Compare the same coordinate in every equal-length atom:
                # its reference-forward START, not whichever internal bases
                # happen to have anchors (which differ across assemblies).
                start=(a.reference.start+interval.start-a.source.start if p.orientation=='+'
                       else a.reference.start+a.source.end-interval.end)
                exact.append(Interval(max(0,start-self.tolerance),max(0,start+self.tolerance)+1))
            if p.reference_intervals:
                lo,hi=self.bounds[p.placement_id]
                fallback.append(Interval(max(0,lo-interval.length-self.tolerance),hi+self.tolerance+1))
        # Actual overlapping anchors take priority over an unanchored envelope.
        if exact:
            feasible=(exact[0],)
            for iv in exact[1:]:feasible=intersection(feasible,(iv,))
            if not feasible:
                self.stats['inconsistent_anchor_frame_atoms']+=1
                return None  # Conflicting anchors cannot justify deleting homology.
            self.stats['actual_anchor_atoms']+=1
            return feasible
        if fallback:self.stats['envelope_only_atoms']+=1;return merged_intervals(fallback)
        self.stats['unknown_atoms']+=1;return None


def guarded_model(domains,audit):
    source=textwrap.dedent(inspect.getsource(coverage.CoverageModel.__init__))
    needle='    parent = list(range(len(self.atoms)))'
    assert source.count(needle)==1
    source=source.replace(needle,'    feasible = [diagnostic_domains.atom(s, iv) for s, iv in self.atoms]\n'+needle)
    needle='        if sizes[ra] < sizes[rb]:'
    assert source.count(needle)==1
    source=source.replace(needle,'''        common = diagnostic_intersection(feasible[ra], feasible[rb])
        if common == ():
            diagnostic_audit['rejected_unions'] += 1
            diagnostic_audit['rejected_atom_bp_sum'] += self.atoms[a][1].length
            diagnostic_audit['maximum_rejected_map_bp'] = max(diagnostic_audit['maximum_rejected_map_bp'], relation.left.length)
            diagnostic_audit['rejected_large_map_unions'] += relation.left.length > 100000
            return
        diagnostic_audit['accepted_unions'] += 1
'''+needle)
    needle='        parent[rb] = ra'
    source=source.replace(needle,'        feasible[ra] = common\n'+needle)
    ns=dict(vars(coverage));ns.update(diagnostic_domains=domains,diagnostic_audit=audit,diagnostic_intersection=intersection)
    exec(compile(source,'<reference-locus-guarded-coverage>','exec'),ns)
    class GuardedCoverage(coverage.CoverageModel):pass
    GuardedCoverage.__init__=ns['__init__']
    return GuardedCoverage,sha256(source.encode()).hexdigest()


def native_relations(graph,progress=None):
    cached=graph.__dict__.get('_diagnostic_native_relations')
    if cached is not None:return cached
    from lgz_core import q0_paths as paths
    from wheat_sparse_pair_graph_readonly import incident_pairs
    relations=[];seen=set();by_source=defaultdict(list)
    for p in graph.placements.values():by_source[p.source].append(p)
    for (a,b),links in list(graph.links.items()):
        if a==b:continue
        for left,right in incident_pairs(by_source[a],by_source[b],links):
            # Mirror the constructor: qualify against ALL original competitors,
            # THEN remove its native ambiguity IDs. Re-qualifying after deleting
            # competitors can accidentally admit previously nonunique blocks.
            for block,eid in paths.qualify_pair_blocks(left,right,links,graph.policy):
                if eid in graph.ambiguous_equivalence_ids:continue
                r=coverage.Equivalence(left.source,left.source_interval(block.left),right.source,right.source_interval(block.right),left.orientation!=right.orientation,eid)
                if r not in seen:relations.append(r);seen.add(r)
    proof=coverage.CoverageModel(graph.required,relations,maximum_boundaries=graph.policy.maximum_coverage_boundaries,
                                 compact_first=graph.first_request,progress=progress)
    if not (proof.atoms==graph.coverage.atoms and proof.units==graph.coverage.units and proof.ambiguous_evidence_ids==graph.coverage.ambiguous_evidence_ids):
        raise ValueError('native equivalence reconstruction differs; no locus policy may be applied')
    cached=(tuple(relations),{'atoms_equal':True,'units_equal':True,'ambiguity_ids_equal':True})
    graph._diagnostic_native_relations=cached
    return cached


def replace_coverage(graph,tolerance=100_000,progress=print):
    relations,proof=native_relations(graph,progress)
    domains=ReferenceDomains(graph.placements.values(),tolerance);audit=Counter()
    model,pin=guarded_model(domains,audit)
    graph.coverage=model(graph.required,relations,maximum_boundaries=graph.policy.maximum_coverage_boundaries,
                         compact_first=graph.first_request,progress=progress)
    if graph.coverage.ambiguous_evidence_ids:raise ValueError('locus guard introduced native ambiguity')
    return {'reference_tolerance_bp':tolerance,'relations':len(relations),'union_audit':dict(audit),
            'domain_audit':dict(domains.stats),'coverage_code_sha256':pin,
            'domain_code_sha256':sha256(inspect.getsource(ReferenceDomains).encode()).hexdigest(),
            'relation_builder_sha256':sha256(inspect.getsource(native_relations).encode()).hexdigest(),
            'native_equivalence_reconstruction_proof':proof,
            'native_pair_qualification_unchanged':True,'native_ambiguity_exclusions_preserved':True,
            'reference_constraint_intersection_propagates_through_unknown_atoms':True,
            'policy_change':True,'union_order':'native sorted coordinate map order'}
