"""Reference spine and local common-anchor cuts with a validated incumbent.

Only replaces the one/two joins incident to a proposal; never enumerates the
Cartesian product of every edge in a chromosome. Existing joins remain legal.
All accepted proposals pass the native whole-path source/coverage/duplicate gate.
"""
import argparse, gzip, inspect, json, pickle, subprocess, textwrap
from bisect import bisect_left
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
from itertools import product
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
from unittest.mock import patch
from lgz_core import q0_paths as paths
from lgz_core.q0_sources import Interval, SourceKey, merged_intervals
from wheat_selection_checkpoint import encode, decode
from wheat_local_chain_selection_readonly import reference_spine, checked_pickle, link_identity
from wheat_sparse_pair_graph_readonly import sparse_constructor
from wheat_selected_path_risk_audit import footprint, minus
from wheat_continuous_dominant_admission_readonly import old_routes, risk
from wheat_local_chain_primitives import clipped
from wheat_reference_funnel_readonly import digest, write


def need(ok,why):
    if not ok:raise ValueError(why)


def refs(path, graph):
    # Path identity includes nodes and exact joins. Keep a bounded exact memo;
    # repeated incumbent comparisons must not rescan a 220 Mb contig's anchors.
    cache=graph.__dict__.setdefault('_diagnostic_ref_footprints',{})
    key=path.path_id
    if key not in cache:
        value=merged_intervals(a.reference for s in path.slices
                               for a in clipped(graph.placements[s.placement_id].reference_blocks,
                                                s.interval,s.orientation))
        if len(cache)>=256:cache.pop(next(iter(cache)))
        cache[key]=value
    return cache[key]


def metrics(path, graph):
    result=footprint(path, graph.placements)
    result['max_slice_bp']=max((s.interval.length for s in path.slices),default=0)
    lengths=sorted((s.interval.length for s in path.slices),reverse=True)
    total=sum(lengths);passed=0
    for value in lengths:
        passed+=value
        if passed*2>=total:result['slice_N50_bp']=value;break
    return result


@contextmanager
def common_anchor_joins(graph):
    native=paths.PathGraph.joins
    source=textwrap.dedent(inspect.getsource(native))
    needle='if blocks and (reaches_both := _end_spanning_evidence(blocks, left.interval.length)):'
    need(source.count(needle)==1,'different frozen join gate')
    source=source.replace(needle,'if blocks:\n        reaches_both = {evidence_id for _, evidence_id in blocks}')
    namespace=dict(vars(paths));exec(compile(source,'<isolated-common-anchor-cuts>','exec'),namespace)
    relaxed=namespace['joins'];strict={};expanded=set()
    graph._joins.clear()
    def joins(self,left,right):
        need(self is graph,'wrong diagnostic graph')
        key=left,right
        if key in expanded:return self._joins[key]
        old=native(self,left,right);strict[key]=old
        self._joins.pop(key,None)
        additional=tuple(j for j in relaxed(self,left,right) if j.kind=='sequence_overlap' and j not in old)
        # Retain every original exact Join object, including original evidence
        # identities. New choices cannot crowd the incumbent out of an edge cap.
        self._joins[key]=old+additional;expanded.add(key)
        return self._joins[key]
    with patch.object(paths.PathGraph,'joins',joins):
        yield strict,sha256(source.encode()).hexdigest()


def monotone_better(candidate, incumbent, graph):
    if candidate is None or candidate.score < incumbent.score:
        return False
    if graph.rank(candidate) >= graph.rank(incumbent):
        return False
    return sum(i.length for i in refs(candidate,graph)) >= sum(i.length for i in refs(incumbent,graph))


def splice_choices(graph,current,node,start,stop):
    """Fixed outside cuts; at most two incident-edge choice dimensions."""
    need(0<=start<=stop<=len(current.nodes),'invalid splice')
    nodes=current.nodes[:start]+(node,)+current.nodes[stop:]
    if len(set(nodes))!=len(nodes):return
    left=graph.joins(current.nodes[start-1],node) if start else (None,)
    right=graph.joins(node,current.nodes[stop]) if stop<len(current.nodes) else (None,)
    prefix=current.joins[:max(0,start-1)];suffix=current.joins[stop:]
    for a,b in product(left,right):
        joins=prefix+tuple(j for j in (a,b) if j is not None)+suffix
        yield graph._score_candidate(nodes,joins)


def proposal_spans(graph,current,node):
    p=graph.placements[node]
    if not p.reference_intervals:return ()
    lo=min(i.start for i in p.reference_intervals);hi=max(i.end for i in p.reference_intervals)
    starts=[];overlap=[]
    for i,s in enumerate(current.slices):
        local=clipped(graph.placements[s.placement_id].reference_blocks,s.interval,s.orientation)
        if not local:continue
        a=min(v.reference.start for v in local);b=max(v.reference.end for v in local)
        starts.append((a,i))
        if a<hi and lo<b:overlap.append(i)
    starts.sort();pivot=bisect_left([a for a,_ in starts],lo)
    insertion=starts[pivot][1] if pivot<len(starts) else len(current.nodes)
    positions={max(0,insertion-1),insertion,min(len(current.nodes),insertion+1)}
    for i in overlap:positions.update((i,i+1))
    spans={(i,i) for i in positions}
    spans.update((i,i+1) for i in positions if i<len(current.nodes))
    if overlap:spans.add((min(overlap),max(overlap)+1))
    return tuple(sorted(spans,key=lambda s:(s[1]-s[0],abs(s[0]-insertion),s)))


def refine(graph,incumbent,progress=print,max_passes=4):
    need(graph._score_candidate(incumbent.nodes,incumbent.joins)==incumbent,'incumbent is not valid in candidate graph')
    initial=incumbent;events=[];calls=0;last=monotonic();stop_reason='diagnostic_pass_budget'
    ordered=sorted(graph.placements,key=lambda n:(-graph.placements[n].interval.length,graph.source_rank(n),n))
    for iteration in range(1,max_passes+1):
        before=incumbent
        for node in ordered:
            if node in incumbent.nodes:continue
            best=incumbent
            for start,stop in proposal_spans(graph,incumbent,node):
                for candidate in splice_choices(graph,incumbent,node,start,stop):
                    calls+=1
                    if monotone_better(candidate,best,graph):best=candidate
            if best is not incumbent:
                events.append({'pass':iteration,'kind':'reference_neighbor_splice','candidate':node,
                               'before':metrics(incumbent,graph),'after':metrics(best,graph)})
                incumbent=best
            if monotonic()-last>=30:
                progress('REFINE_PROGRESS '+json.dumps({'pass':iteration,'score_calls':calls,'accepted':len(events),'metrics':metrics(incumbent,graph)}));last=monotonic()
        for index in range(len(incumbent.joins)):
            old=incumbent.joins[index];best=incumbent
            for join in graph.joins(old.left_id,old.right_id):
                if join==old:continue
                calls+=1
                candidate=graph._score_candidate(incumbent.nodes,incumbent.joins[:index]+(join,)+incumbent.joins[index+1:])
                if monotone_better(candidate,best,graph):best=candidate
            if best is not incumbent:
                events.append({'pass':iteration,'kind':'single_common_anchor_cut',
                               'before':metrics(incumbent,graph),'after':metrics(best,graph)})
                incumbent=best
        progress('REFINE_PASS_DONE '+json.dumps({'pass':iteration,'score_calls':calls,'accepted':len(events),'metrics':metrics(incumbent,graph)}))
        if incumbent==before:
            stop_reason='fixed_point';break
    need(incumbent.score>=initial.score,'lost validated source-score lower bound')
    need(sum(i.length for i in refs(incumbent,graph))>=sum(i.length for i in refs(initial,graph)),'lost validated reference-length lower bound')
    return incumbent,{'score_calls':calls,'passes':iteration,'stop_reason':stop_reason,'events':events,
                      'global_optimum_claimed':False,'outside_cuts_preserved_per_proposal':True,
                      'whole_path_join_product_enumerated':False}


def selected_risk(path,graph,old):
    rrefs=defaultdict(list);sources=defaultdict(lambda:defaultdict(list));flags=[]
    for s in path.slices:
        p=graph.placements[s.placement_id]
        anchors=clipped(p.reference_blocks,s.interval,s.orientation)
        selected=SimpleNamespace(source=p.source,interval=s.interval,
                                 chromosome=p.chromosome,orientation=p.orientation,
                                 reference_blocks=anchors)
        rr,ss=risk(selected,old)
        for k,rows in rr.items():rrefs[k].extend(rows)
        for k,rows in ss.items():
            sources[k][s.source].extend(rows)
            if k!='same_group_same_orientation':
                flags.append({'source':[s.source.dataset,s.source.contig],'placement_id':s.placement_id,
                              'category':k,'source_bp':sum(v.length for v in merged_intervals(rows))})
    return {'reference_union_bp':{k:sum(v.length for v in merged_intervals(rows)) for k,rows in rrefs.items()},
            'source_union_bp':{k:sum(sum(v.length for v in merged_intervals(rows)) for rows in by_source.values()) for k,by_source in sources.items()},
            'conflict_flags':flags,'independent_biological_truth':False}


def run(base,owner,admission_owner,evidence_owner,legacy_owner):
    began=monotonic()
    replay=json.loads((admission_owner/'hull-replay.json').read_text());mode=replay['selected_mode']
    need(mode is not None and all(replay['strict_three_arms_reproduced'].values()),'no validated admission candidate')
    file=admission_owner/(mode+'-placements.jsonl.gz')
    need(digest(file)==replay['outputs'][file.name]['sha256'],'candidate admission changed')
    with gzip.open(file,'rt') as f:extra=[decode(json.loads(line)) for line in f]
    blocked=json.loads((legacy_owner/'blockers.json').read_text())
    oldgraph=checked_pickle(legacy_owner/'frozen-1A-graph.pickle',blocked['graph_pickle_sha256'])
    need(digest(legacy_owner/'baseline-path.json')=='fde9c9af2f8afd512c176c241759e4e50279fdd03a5f4bdd05492413f0bb2bb2','frozen baseline path identity changed')
    baseline=decode(json.loads((legacy_owner/'baseline-path.json').read_text()))
    need(oldgraph._score_candidate(baseline.nodes,baseline.joins)==baseline,'original frozen winner not reproduced')
    admitted=list(oldgraph.placements.values())+extra
    need(len({p.placement_id for p in admitted})==len(admitted),'placement collision')
    sources={p.source for p in admitted}
    cache_name=None
    for name in ('expanded-links-dominant90','expanded-links-regional'):
        seal=evidence_owner/(name+'.json')
        if not seal.exists():continue
        data=json.loads(seal.read_text());need(data['binding']['producer_tools_sha256']=='19cebdc7667d912f6d3ace4a59783d3e49fbb02e668ff5f5efbb50c618c27ad2','evidence producer mismatch');available={SourceKey(*v) for v in data['binding']['sources']}
        if sources<=available:cache_name=name;break
    need(cache_name is not None,'sealed evidence cohort does not cover chosen admission; do not substitute incomplete evidence')
    links=checked_pickle(evidence_owner/(cache_name+'.pickle'),data['sha256'])
    need(len(links)==data['count'],'cache count mismatch')
    links=[link for link in links if link.query_source in sources and link.target_source in sources]
    old_sources={p.source for p in oldgraph.placements.values()}
    old_pairs={k:[link_identity(v) for v in rows] for k,rows in oldgraph.links.items() if rows};new_pairs=defaultdict(list)
    for link in links:
        if link.query_source in old_sources and link.target_source in old_sources and link.hit.matches/link.hit.block_length>=oldgraph.policy.minimum_pair_identity:
            new_pairs[tuple(sorted((link.query_source,link.target_source)))].append(link_identity(link))
    need(old_pairs==dict(new_pairs),'baseline per-source-pair evidence lost or reordered')
    stats=Counter();constructor,original_pin,sparse_pin=sparse_constructor(stats)
    with patch.object(paths.PathGraph,'__init__',constructor):
        graph=paths.PathGraph(admitted,links,(),paths.PathPolicy(),first_request=True,
                              progress=lambda s:print('CONTINUOUS_GRAPH',s,flush=True))
    need(graph._score_candidate(baseline.nodes,baseline.joins)==baseline,'baseline fails augmented graph exact gate')
    raw=pickle.dumps(graph,protocol=5);(owner/'continuous-graph.pickle').write_bytes(raw)
    write(owner/'continuous-graph.json',{'sha256':sha256(raw).hexdigest(),'mode':mode,'candidate_receipt_sha256':digest(admission_owner/'hull-replay.json'),'evidence_seal_sha256':digest(evidence_owner/(cache_name+'.json'))})
    print('CONTINUOUS_GRAPH_READY',json.dumps(dict(stats)),flush=True)
    old_path=legacy_owner.parent/'q0-continuity-20261126.RAbGvNba'/'old-grt-q-segments.tsv'
    need(digest(old_path)=='cd9069e54e64cce94ba7d4790afd2c575d85ffc227722b04eca56bf6e04ea847','old comparator changed')
    old=old_routes(old_path)
    spine,spine_stats=reference_spine(graph)
    incumbent=spine if monotone_better(spine,baseline,graph) else baseline
    results={}
    def save(name,path):
        represented,duplicate,_=graph.coverage.assess((s.source,s.interval) for s in path.slices)
        need(not duplicate and represented==path.score[0],'final full coverage gate')
        destination=owner/(name+'-path.json.gz')
        with gzip.open(destination,'wt',compresslevel=1) as f:json.dump(encode(path),f)
        before=refs(baseline,graph);after=refs(path,graph)
        row={'metrics':metrics(path,graph),'risk':selected_risk(path,graph,old),
             'reference_gain_bp_vs_frozen':sum(v.length for v in minus(after,before)),
             'reference_loss_bp_vs_frozen':sum(v.length for v in minus(before,after)),
             'path_file':destination.name,'path_sha256':digest(destination),'full_exact_gate_passed':True}
        results[name]=row
        print('CONTINUOUS_PATH_SAVED',name,json.dumps(row['metrics']),flush=True)
    save('frozen_baseline',baseline)
    if spine is not None:save('reference_spine_proposal',spine)
    save('validated_initial_backbone',incumbent)
    with common_anchor_joins(graph) as (native_edges,join_pin):
        need(graph._score_candidate(incumbent.nodes,incumbent.joins)==incumbent,'join expansion lost incumbent')
        final,diagnostics=refine(graph,incumbent,progress=lambda s:print(s,flush=True))
        need(graph._score_candidate(final.nodes,final.joins)==final,'final path cannot be replayed')
        save('common_anchor_refined',final)
        new_edges=[{'left_id':j.left_id,'right_id':j.right_id,'left_cut':j.left_end,'right_cut':j.right_start,'evidence_ids':list(j.evidence_ids)}
                   for j in final.joins if j not in native_edges[j.left_id,j.right_id]]
        need(all(j.kind=='sequence_overlap' for j in final.joins if j not in native_edges[j.left_id,j.right_id]),'non-evidence novel join')
    # Capture placements so independent actual-slice audit needs no raw inputs.
    placement_file=owner/'selected-input-placements.jsonl.gz'
    with gzip.open(placement_file,'wt',compresslevel=1) as f:
        for p in admitted:f.write(json.dumps(encode(p),separators=(',',':'))+'\n')
    report={'schema':'wheat_continuity_1A_final_selection_v1','mode':mode,'group':'1A',
            'admission_reference_bp':replay['variants'][mode]['combined_reference_bp'],
            'admitted_placements':len(admitted),'pair_links':len(links),'results':results,
            'spine_diagnostics':spine_stats,'refinement_diagnostics':diagnostics,
            'new_common_anchor_joins':new_edges,'join_variant_sha256':join_pin,
            'sparse_constructor_original_sha256':original_pin,'sparse_constructor_ast_sha256':sparse_pin,
            'graph_pair_counts':dict(stats),'frozen_pair_evidence_order_preserved':True,
            'frozen_winner_valid_in_augmented_graph':True,'incumbent_score_lower_bound_preserved':True,
            'incumbent_reference_length_lower_bound_preserved':True,
            'selected_input_placements_sha256':digest(placement_file),
            'admission_receipt_sha256':digest(admission_owner/'hull-replay.json'),
            'evidence_seal_sha256':digest(evidence_owner/(cache_name+'.json')),
            'mapper_calls':0,'formal_workspace_modified':False,'elapsed_s':monotonic()-began,
            'limitations':['Only 1A; no formal whole-wheat acceptance.',
                           'Old Q0 conflicts are a comparator, not independent biological truth.',
                           'Local cut proposals retain outside joins and do not prove a global optimum.',
                           'A higher total reference length does not imply zero interval loss; gain/loss are both reported.']}
    write(owner/'continuity-final-selection.json',report)
    print('CONTINUITY_FINAL_SELECTION_DONE',json.dumps(results['common_anchor_refined']['metrics']),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('owner',type=Path);p.add_argument('admission_owner',type=Path);p.add_argument('evidence_owner',type=Path);p.add_argument('legacy_owner',type=Path);a=p.parse_args()
    for owner in (a.owner,a.admission_owner,a.evidence_owner,a.legacy_owner):
        need(owner.resolve().parent==a.base.resolve() and owner.stat().st_mode&0o077==0,'private diagnostic owners required')
    with patch.object(subprocess,'Popen',side_effect=RuntimeError('external command forbidden')):
        run(a.base.resolve(),a.owner.resolve(),a.admission_owner.resolve(),a.evidence_owner.resolve(),a.legacy_owner.resolve())
