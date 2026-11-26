"""Reopen native graph caches and emitted paths; rebuild declared locus policy."""
import argparse,gzip,json,subprocess
from pathlib import Path
from unittest.mock import patch
from wheat_selection_checkpoint import decode
from wheat_reference_funnel_readonly import digest,write
from wheat_local_chain_selection_readonly import checked_pickle
from wheat_continuity_gap_rescue_readonly import need,reference_order_flags
from wheat_continuity_path_refinement_readonly import metrics,selected_risk
from wheat_continuous_dominant_admission_readonly import old_routes
from wheat_locus_guard_readonly import replace_coverage
from wheat_indexed_anchor_support_readonly import AnchorSupportIndex,indexed_native


def run(owner,source,admission):
    report=json.loads((owner/'top-chain-locus-closed-loop.json').read_text());old=old_routes(admission/'old-grt-q-segments.tsv');observed={};graphs={}
    for name,row in report['results'].items():
        if 'failed' in row:observed[name]={'failed':row['failed']};continue
        if name.startswith('same_admission_'):
            file=source/'continuous-graph.pickle';seal=json.loads((source/'continuous-graph.json').read_text())
        else:
            ratio=name.split('_')[1];file=owner/('native-chain-'+ratio+'-graph.pickle');seal=json.loads(file.with_suffix('.json').read_text())
        identity=(str(file),seal['sha256'])
        if identity not in graphs:
            fresh=checked_pickle(file,seal['sha256']);graphs[identity]=(fresh,fresh.coverage)
        graph,native_coverage=graphs[identity]
        graph.coverage=native_coverage
        if 'guard' in row:
            guard=replace_coverage(graph,row['guard']['reference_tolerance_bp'],progress=None)
            need(guard==row['guard'],'locus rebuild changed policy or decisions')
        file=owner/row['path_file'];need(digest(file)==row['path_sha256'],'emitted path changed')
        with gzip.open(file,'rt') as f:path=decode(json.load(f))
        need(graph._score_candidate(path.nodes,path.joins)==path,'actual path not legal in reconstructed graph')
        represented,dup,_=graph.coverage.assess((s.source,s.interval) for s in path.slices)
        need(not dup and represented==path.score[0],'full duplicate gate fails')
        met=json.loads(json.dumps(metrics(path,graph)));risk=selected_risk(path,graph,old);flags=reference_order_flags(path,graph)
        need(met==row['metrics'] and risk==row['risk'] and flags==row['reference_order_flags'],'saved metrics or conflict audit differ')
        observed[name]={'metrics':met,'risk':risk,'reference_order_flags':flags,'reopened_native_graph_and_path_verified':True}
        print('LOCUS_RESULT_REOPENED',name,json.dumps(met),flush=True)
    write(owner/'top-chain-locus-independent-audit.json',{'schema':'wheat_locus_loop_independent_audit_v1','loop_report_sha256':digest(owner/'top-chain-locus-closed-loop.json'),'results':observed,'mapper_calls':0,'formal_workspace_modified':False})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('owner',type=Path);p.add_argument('source',type=Path);p.add_argument('admission',type=Path);a=p.parse_args()
    with patch.object(subprocess,'Popen',side_effect=RuntimeError('external program forbidden')),indexed_native(AnchorSupportIndex()):run(a.owner,a.source,a.admission)
