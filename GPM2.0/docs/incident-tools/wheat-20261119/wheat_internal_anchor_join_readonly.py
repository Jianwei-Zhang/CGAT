"""Frozen-1A counterfactual: actual internal-anchor joins on previously empty edges.

No mapper or production patch. Existing nonempty edge choices are untouched.
New cuts still use original qualified pair blocks, continuous supported anchors,
reference consistency, source overlap and exact global duplicate gates.
"""
import argparse,inspect,json,pickle,subprocess,textwrap,gzip
from hashlib import sha256
from pathlib import Path
from time import monotonic
from unittest.mock import patch
from lgz_core import q0_paths as paths
from wheat_single_group_replay_readonly import need,search_variant,footprint
from wheat_selection_checkpoint import encode,decode
from wheat_reference_funnel_readonly import write,digest


def join_variant():
    original=paths.PathGraph.joins;source=textwrap.dedent(inspect.getsource(original));needle='if blocks and (reaches_both := _end_spanning_evidence(blocks, left.interval.length)):'
    need(source.count(needle)==1,'different frozen join implementation');source=source.replace(needle,'if blocks:\n        reaches_both = {evidence_id for _, evidence_id in blocks}')
    ns=dict(vars(paths));exec(compile(source,'<isolated-internal-anchor-join>','exec'),ns);relaxed=ns['joins']
    def proposal(self,left,right):
        key=left,right
        if key in self._diagnostic_internal_checked:return self._joins[key]
        old=original(self,left,right)
        if old:return old
        self._diagnostic_internal_checked.add(key);self._joins.pop(key,None)
        return relaxed(self,left,right)
    return original,proposal,sha256(source.encode()).hexdigest()


def run(owner):
    blocked=json.loads((owner/'blockers.json').read_text());raw=(owner/'frozen-1A-graph.pickle').read_bytes();need(sha256(raw).hexdigest()==blocked['graph_pickle_sha256'],'graph changed');graph=pickle.loads(raw);baseline=decode(json.loads((owner/'baseline-path.json').read_text()));need(json.loads(json.dumps(footprint(baseline,graph.placements)))==blocked['baseline_metrics'],'baseline changed');strict,proposal,code=join_variant();results={}
    for mode in ('baseline_search','reference_first_search'):
        graph._joins.clear();graph._diagnostic_internal_checked=set();fn,search_pin=search_variant('baseline' if mode=='baseline_search' else 'reference_first');start=monotonic();messages=[]
        with patch.object(paths.PathGraph,'joins',proposal):
            need(graph._score_candidate(baseline.nodes,baseline.joins)==baseline,'original winner no longer legal')
            def log(s):messages.append(s);print(mode,s,flush=True)
            result=fn(graph,progress=log).path;need(result is not None,'no counterfactual path');represented,duplicates,_=graph.coverage.assess((s.source,s.interval) for s in result.slices);need(not duplicates and represented==result.score[0],'exact coverage/duplicate gate failed')
            new=[]
            for j in result.joins:
                key=j.left_id,j.right_id;cached=graph._joins.pop(key,None);original_choices=strict(graph,*key);graph._joins[key]=cached
                if j not in original_choices:
                    need(not original_choices and j.kind=='sequence_overlap','modified a formerly nonempty edge')
                    left,right=graph.placements[j.left_id],graph.placements[j.right_id];new.append({'left':j.left_id,'right':j.right_id,'left_source':[left.source.dataset,left.source.contig],'right_source':[right.source.dataset,right.source.contig],'left_orientation':left.orientation,'right_orientation':right.orientation,'left_local_cut':j.left_end,'right_local_cut':j.right_start,'evidence_ids':list(j.evidence_ids)})
            met=footprint(result,graph.placements);met['net_reference_bp_vs_frozen']=met['reference_union_bp']-blocked['baseline_metrics']['reference_union_bp'];met['net_source_bp_vs_frozen']=met['source_bp']-blocked['baseline_metrics']['source_bp'];file=owner/('internal-anchor-'+mode+'-path.json.gz')
            with gzip.open(file,'wt',compresslevel=1) as f:json.dump(encode(result),f)
            results[mode]={'metrics':met,'seconds':monotonic()-start,'logs':messages,'search_function_sha256':search_pin,'full_coverage_gate_passed':True,'original_winner_still_legal':True,'new_internal_anchor_joins':new,'path_file':file.name,'path_sha256':digest(file)}
        print('INTERNAL_ANCHOR_VARIANT_DONE',mode,json.dumps(met),'new_joins',len(new),flush=True);write(owner/'internal-anchor-progress.json',results)
    report={'schema':'wheat_1A_internal_anchor_join_counterfactual_v1','baseline_metrics':blocked['baseline_metrics'],'graph_sha256':blocked['graph_pickle_sha256'],'join_function_sha256':code,'results':results,'mapper_calls':0,'formal_workspace_modified':False,'limitations':['Scientific counterfactual only; no production gate removed or formal workflow started.','Only formerly empty edge choices may gain internally anchored sequence-overlap joins; original nonempty choices remain unchanged.','All joins use actual qualified pair evidence and the original contiguous-anchor cut calculation; no reference-only overlap cut is fabricated.','Original exact duplicate/coverage gates pass, but this is not independent biological or subgenome truth validation.','Search budget remains 20000; cache reuse means timings are not an unbiased speed benchmark.','Reference-first mode additionally changes proposal order and is reported separately.']}
    write(owner/'internal-anchor-counterfactual.json',report);print('INTERNAL_ANCHOR_DONE',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('owner',type=Path);a=p.parse_args();need(a.owner.name.startswith('q0-local-chain-') and a.owner.stat().st_mode&0o077==0,'private owner required')
    with patch.object(subprocess,'Popen',side_effect=RuntimeError('external process forbidden')):run(a.owner.resolve())
