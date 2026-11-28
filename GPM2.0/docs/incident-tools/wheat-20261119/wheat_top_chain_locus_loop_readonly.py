"""Cached 1A admission -> native/locus-aware graph -> exact reference spine.

Never calls mapper, writes a formal Q0, or performs fragmented local refinement.
The 85-slice incumbent is replayed in every graph, not force-registered.
"""
import argparse,gzip,json,pickle,subprocess
from collections import Counter,defaultdict
from pathlib import Path
from hashlib import sha256
from time import monotonic
from unittest.mock import patch
from lgz_core import q0_paths as paths
from lgz_core.q0_sources import SourceKey
from wheat_selection_checkpoint import encode,decode
from wheat_local_chain_selection_readonly import checked_pickle,reference_spine
from wheat_continuity_gap_rescue_readonly import need,load_rows,reference_order_flags
from wheat_continuity_path_refinement_readonly import metrics,refs,selected_risk
from wheat_continuous_dominant_admission_readonly import adm,old_routes
from wheat_sparse_pair_graph_readonly import sparse_constructor
from wheat_indexed_anchor_support_readonly import AnchorSupportIndex,indexed_native
from wheat_locus_guard_readonly import replace_coverage
from wheat_top_chain_admission_readonly import run as run_admission
from wheat_reference_funnel_readonly import digest,write
from wheat_selected_path_risk_audit import minus


def save_path(owner,name,path,graph,old,baseline,baseline_graph):
    need(path is not None,'empty selected path')
    need(graph._score_candidate(path.nodes,path.joins)==path,'selected path cannot replay')
    represented,dup,_=graph.coverage.assess((s.source,s.interval) for s in path.slices)
    need(not dup and represented==path.score[0],'full duplicate/coverage gate failed')
    file=owner/(name+'-path.json.gz')
    with gzip.open(file,'wt') as f:json.dump(encode(path),f)
    out={'metrics':metrics(path,graph),'risk':selected_risk(path,graph,old),
         'reference_order_flags':reference_order_flags(path,graph),
         'reference_gain_vs_baseline_bp':adm._size(minus(refs(path,graph),refs(baseline,baseline_graph))),
         'reference_loss_vs_baseline_bp':adm._size(minus(refs(baseline,baseline_graph),refs(path,graph))),
         'path_file':file.name,'path_sha256':digest(file),'native_score_and_duplicate_gate_passed':True,
         'incumbent_lower_bounds_passed':path.score>=baseline.score and adm._size(refs(path,graph))>=adm._size(refs(baseline,baseline_graph))}
    print('CLOSED_LOOP_PATH',name,json.dumps(out['metrics']),json.dumps(out['risk']),flush=True)
    return out


def mapped_incumbent(graph,baseline):
    joins=[]
    for j in baseline.joins:
        choices=graph.joins(j.left_id,j.right_id)
        geometry=lambda x:(x.kind,x.left_end,x.right_start,x.n_bp,x.original_adjacency_id)
        new=next((v for v in choices if geometry(v)==geometry(j)),None)
        if new is None:return None
        joins.append(new)
    path=graph._score_candidate(baseline.nodes,tuple(joins))
    if path is not None:need(path.slices==baseline.slices,'incumbent geometry changed')
    return path


def run(base,source,admission,legacy,owner,ratios=("10","5")):
    began=monotonic()
    if (owner/'top-chain-admission.json').exists():
        report=json.loads((owner/'top-chain-admission.json').read_text())
        need(report['source_receipt_sha256']==digest(admission/'continuity-admission.json'),'admission generation differs')
        print('TOP_CHAIN_ADMISSION_REUSED',flush=True)
    else:report=run_admission(admission,owner)
    receipt=json.loads((source/'continuity-final-selection.json').read_text())
    graphseal=json.loads((source/'continuous-graph.json').read_text())
    baseline_graph=checked_pickle(source/'continuous-graph.pickle',graphseal['sha256'])
    item=receipt['results']['validated_initial_backbone'];file=source/item['path_file']
    need(digest(file)==item['path_sha256'],'baseline path changed')
    with gzip.open(file,'rt') as f:baseline=decode(json.load(f))
    need(len(baseline.slices)==85 and baseline_graph._score_candidate(baseline.nodes,baseline.joins)==baseline,'85-slice baseline not reproduced')
    old=old_routes(admission/'old-grt-q-segments.tsv')
    # Run locus repair on the identical old cohort first: separate its effect
    # from the larger admission cohort, and seal a pure-selection comparison.
    results={};graphs={}
    frozen_trial=checked_pickle(source/'continuous-graph.pickle',graphseal['sha256'])
    for padding in (1_000_000,100_000):
        graph=frozen_trial
        guard=replace_coverage(graph,padding,progress=lambda s:print('FROZEN_LOCUS_GRAPH',s,flush=True))
        replay=mapped_incumbent(graph,baseline);need(replay is not None,'locus-only change lost incumbent')
        spine,diag=reference_spine(graph)
        winner=spine if spine and spine.score>=baseline.score and adm._size(refs(spine,graph))>=adm._size(refs(baseline,baseline_graph)) else replay
        name='same_admission_locus_'+str(padding)
        results[name]=save_path(owner,name,winner,graph,old,baseline,baseline_graph)|{'guard':guard,'spine_diagnostics':diag}
        write(owner/'closed-loop-progress.json',{'results':results,'phase':'same_admission_locus'})
    # Admission candidates retain all old placements, deduplicating identical
    # physical/reference geometry rather than renaming the protected incumbent.
    original=list(baseline_graph.placements.values())
    def key(p):return (p.source,p.interval,p.orientation,p.chromosome,p.reference_blocks)
    known={key(p) for p in original};arms={};allsources=set()
    for ratio in ratios:
        f=owner/('top-chain-'+ratio+'-placements.jsonl.gz')
        need(digest(f)==report['outputs'][f.name],'top-chain placement cache differs')
        extra=[p for p in load_rows(f) if key(p) not in known]
        arms[ratio]=original+extra;allsources.update(p.source for p in arms[ratio])
    seal=json.loads((legacy/'expanded-links-regional.json').read_text())
    available={SourceKey(*v) for v in seal['binding']['sources']}
    need(allsources<=available,'sealed pair cache does not cover new admission; no cold fallback permitted')
    linkseal=owner/'loop-selected-links.json'
    binding={'evidence_seal_sha256':digest(legacy/'expanded-links-regional.json'),'admission_sha256':digest(owner/'top-chain-admission.json'),'sources':sorted([s.dataset,s.contig] for s in allsources)}
    if linkseal.exists():
        saved=json.loads(linkseal.read_text());need(saved['binding']==binding,'filtered cache binding differs')
        links=checked_pickle(owner/'loop-selected-links.pickle',saved['sha256'])
    else:
        print('LOOP_PAIR_CACHE_LOAD',seal['count'],flush=True)
        links=checked_pickle(legacy/'expanded-links-regional.pickle',seal['sha256'])
        links=[v for v in links if v.query_source in allsources and v.target_source in allsources]
        raw=pickle.dumps(links,protocol=5);(owner/'loop-selected-links.pickle').write_bytes(raw)
        write(linkseal,{'binding':binding,'sha256':sha256(raw).hexdigest(),'count':len(links)});del raw
    print('LOOP_SELECTED_LINKS_READY',len(links),flush=True)
    for ratio,placements in arms.items():
        variants_sources={p.source for p in placements}
        graphfile=owner/('native-chain-'+ratio+'-graph.pickle');sealfile=graphfile.with_suffix('.json')
        if sealfile.exists():
            gs=json.loads(sealfile.read_text());need(gs['binding']==binding,'graph binding differs')
            graph=checked_pickle(graphfile,gs['sha256'])
        else:
            stats=Counter();ctor,pin,sp=sparse_constructor(stats)
            with patch.object(paths.PathGraph,'__init__',ctor):
                graph=paths.PathGraph(placements,[l for l in links if l.query_source in variants_sources and l.target_source in variants_sources],(),baseline_graph.policy,first_request=True,progress=lambda s:print('TOP_CHAIN_NATIVE_GRAPH',ratio,s,flush=True))
            raw=pickle.dumps(graph,protocol=5);graphfile.write_bytes(raw)
            write(sealfile,{'binding':binding,'sha256':sha256(raw).hexdigest(),'pair_counts':dict(stats),'constructor_sha256':pin,'sparse_sha256':sp});del raw
        native_spine,diag=reference_spine(graph)
        if native_spine:
            name='chain_'+ratio+'_native_equivalence'
            results[name]=save_path(owner,name,native_spine,graph,old,baseline,baseline_graph)|{'spine_diagnostics':diag,'not_promoted_if_below_incumbent':True}
        for padding in (1_000_000,100_000):
            guard=replace_coverage(graph,padding,progress=lambda s:print('TOP_CHAIN_LOCUS_GRAPH',ratio,padding,s,flush=True))
            incumbent=mapped_incumbent(graph,baseline)
            spine,diag=reference_spine(graph)
            options=[p for p in (spine,incumbent) if p and p.score>=baseline.score and adm._size(refs(p,graph))>=adm._size(refs(baseline,baseline_graph))]
            if not options:
                results['chain_'+ratio+'_locus_'+str(padding)]={'failed':'no legal current-graph path meets preserved incumbent lower bounds','guard':guard};continue
            winner=min(options,key=graph.rank);name='chain_'+ratio+'_locus_'+str(padding)
            results[name]=save_path(owner,name,winner,graph,old,baseline,baseline_graph)|{'guard':guard,'spine_diagnostics':diag,'same_85_slice_geometry_replayable':incumbent is not None,'admission_reference_bp':report['variants'][ratio]['combined_reference_bp']}
            write(owner/'closed-loop-progress.json',{'results':results,'phase':name})
        with gzip.open(owner/('chain-'+ratio+'-all-placements.jsonl.gz'),'wt') as f:
            for p in placements:f.write(json.dumps(encode(p))+'\n')
    output={'schema':'wheat_top_chain_locus_1A_closed_loop_v1','results':results,'admission_variants':report['variants'],'baseline_graph_sha256':graphseal['sha256'],'admission_sha256':digest(owner/'top-chain-admission.json'),'filtered_pair_seal_sha256':digest(linkseal),'mapper_calls':0,'formal_workspace_modified':False,'fragment_refinement_run':False,'elapsed_s':monotonic()-began,
            'limitations':['Locus-aware equivalence is an isolated scientific policy trial, not lossless optimization.','Unknown loci remain unconstrained; greedy component-locus intersections can depend on native map order.','Reference domains use actual overlapping anchors when available and conservative placement envelopes otherwise.','Native same-source/orientation ambiguity exclusions remain unchanged.','Old-Q0 agreement is not independent biological truth.']}
    write(owner/'top-chain-locus-closed-loop.json',output)
    print('TOP_CHAIN_LOCUS_LOOP_DONE',round(monotonic()-began,1),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('source',type=Path);p.add_argument('admission',type=Path);p.add_argument('legacy',type=Path);p.add_argument('owner',type=Path);p.add_argument('--ratios',nargs='+',choices=('10','5'),default=['10','5']);a=p.parse_args()
    for own in (a.source,a.admission,a.legacy,a.owner):need(own.resolve().parent==a.base.resolve() and own.stat().st_mode&0o077==0,'private diagnostic owners required')
    with patch.object(subprocess,'Popen',side_effect=RuntimeError('external commands forbidden')),indexed_native(AnchorSupportIndex()):run(a.base,a.source,a.admission,a.legacy,a.owner,tuple(a.ratios))
