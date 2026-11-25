"""Read-only 4D qualification. Recompute demand from original projected/part evidence; never launch a mapper."""
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import gzip
import json
import sys
from time import monotonic
from types import SimpleNamespace
from unittest.mock import patch

from census_wheat_q0_fork import bind,bounded,require,write,pack_context
from bound_regional_scope_from_native_receipts import EXPECTED
from pilot_exact_group_inventory import audit as verify_raw
import replay_wheat_partial_queries as replay
from lgz_core import q0_regional_mapping as mapping,q0_preparation as prep,q0_threshold_prepare as threshold,q0_threshold_questions as rule
from lgz_core.common import sha256_file,stable_id
from lgz_core.q0_catalog import CandidateCatalog
from lgz_core.q0_query_windows import TargetWindow
from lgz_core.q0_sources import Interval,split_source
from lgz_core.q0_native_frontier import FallbackGate,PHASES
from lgz_core.q0_threshold_acceptance import decode,record

LOC='c5ff44e8b0686d31381cc309483cdff0adfd2f401218b65aef6ccbf5cbfb4289'
BEFORE='1a51ebcfef103cb8c986ca7e98cb11eb7e86f6d68f9100d057fc3446e9698ec5'


def main(base,stage,out,mode="request"):
    old=base/'q0-request-ready.44e274a7/qualification';donor=base/'q0-fast4d-20261125.T0MmzPVx';start=monotonic()
    _,root,lookup,order,lengths=bind(base/'q0-latest-fork-20261123-1435/control/snapshot.json',base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json')
    loc=json.loads(bounded(donor/'locators/result/raw-locators.json',2<<20,LOC));require(loc['group']=='4D' and len(loc['contexts'])==447 and loc['request_sha256']==BEFORE,'wrong 4D window scope')
    meta=json.loads((stage/'group.json').read_bytes());seqs=prep._dataset_sequences(stage,meta['ds']);mids=set(seqs);parts={};edges=[]
    for k,seq in seqs.items():
        si=split_source(k,seq);edges.extend(si.adjacencies)
        for p in si.segments:parts[p.segment_id]=p
    require(len(seqs)==len(parts)==766 and sum(map(len,seqs.values()))==1074672025 and all(lookup[p][1:]==(v.interval.length,v.sequence_sha256) and order[lookup[p][0]]==v.source for p,v in parts.items()),'4D source identity or geometry changed')
    catalog=CandidateCatalog({'original_connections':[asdict(e) for e in edges]},seqs,parts)
    before=decode(json.loads(bounded(old/'4d-first-request.json',4<<20,BEFORE)),lengths);require(len(before)==181 and sum(map(len,before.values()))==300,'wrong initial demand')
    windows={}; plan=replay.plan_query_windows
    def capture(*args,**kwargs):
        v=plan(*args,**kwargs)
        if len(v)==61000: windows.update((q.window_id,q) for q in v if q.segment_id in parts)
        return v
    with patch.object(replay,'plan_query_windows',capture):replay.replay(base,stage/'historical-cores')
    archived=json.loads(bounded(base/'q0-fork-partial-queries-20261123-1556/plan/replay.json',1<<20,'9b7e12988d8fabe2fd360910d517a3e112e99da4b03578fe1ed9fdcff4d2a682'))
    require(json.loads((stage/'historical-cores/replay.json').read_bytes())['queries_uncompressed_sha256']==archived['queries_uncompressed_sha256'] and len(windows)==754,'wrong original plan including query cores'); print('VERIFIED_CORE_GEOMETRY',len(windows),flush=True)
    policy=Path(mapping.__file__).parent; projector=sha256_file(policy/'q0_query_windows.py');validator=sha256_file(policy/'q0_alignments.py');members={p:(v[1],v[2]) for p,v in lookup.items()};stats=Counter();tasks=[];evidence=[]
    def restrict(rel,qs,ts,identity,kind,private=None):
        # Physical rows outside this diagnostic group become empty lines to retain original artifact/line ID for every retained hit. This is not an adopted ready receipt.
        source=private if private is not None else root/rel
        valid=lambda: sha256_file(source)==identity['sha256'] if private is not None else prep.identity(root,rel)==identity
        require(identity['path']==rel and valid(),'changed PAF'); keepq=parts.keys() & set(qs);keept=parts.keys() & set(ts);keep=0;seen=0
        if keepq and keept:
            path=stage/rel;path.parent.mkdir(parents=True,exist_ok=True); qs_b={n.encode() for n in keepq};ts_b={n.encode() for n in keept}
            with source.open('rb') as src,path.open('xb') as dst:
                for line in src:
                    seen+=1;cols=line.split(b'\t',6)
                    if len(cols)>=6 and cols[0] in qs_b and cols[5] in ts_b:dst.write(line);keep+=1
                    else:dst.write(b'\n')
            require(valid(),'source PAF changed during projection')
            if keep:tasks.append(dict(paf=rel,query_ids=sorted(keepq),target_ids=sorted(keept)))
        evidence.append([rel,identity['sha256'],keep]);stats[kind+'_inventories']+=1;stats[kind+'_rows_retained']+=keep
    for tid,pin in sorted(EXPECTED.items()):
        leaf='grt/evidence/q0_prepare/tasks/'+tid;rc=json.loads(bounded(root/leaf/'success.json',32<<20,pin));sp=rc['spec'];require(rc['status']=='success' and stable_id('q0-map',sp)==tid and sp['tool']==loc['tool'] and sp['members']==[[p,lookup[p][2]] for p in sorted(set(sp['query_ids']+sp['target_ids']))],'wrong adopted native matrix')
        ident,=[v for v in rc['outputs'] if v['path']==leaf+'/result.paf'];restrict(ident['path'],sp['query_ids'],sp['target_ids'],ident,'native')
    for i,entry in enumerate(loc['contexts'],1):
        q=windows[entry['query']];ctx=entry['context_file'];body=json.loads(bounded(root/ctx['path'],64<<20,ctx['sha256']))['spec'];targets=[TargetWindow(t['segment_id'],t['segment_length'],t['start'],t['end']) for t in body['targets']];require(mapping._window_context(q)==body['query'] and sha256(pack_context(entry['context'],body,lookup)).hexdigest()==entry['axes_sha256'],'foreign raw geometry')
        spec=mapping._normal(dict(schema=mapping.PROJECTION_SCHEMA,raw_receipt=entry['raw_receipt'],context=ctx,decision=entry['decision_file'],query=q.record(),targets=[t.record() for t in targets],projector_sha256=projector,validator_sha256=validator));tid=stable_id('q0-regional-project',spec);leaf='grt/evidence/q0_prepare/regional/projects/'+tid
        task=dict(task_id=tid,kind='regional_discovery',paf=leaf+'/result.paf',receipt=leaf+'/success.json',query_ids=[q.segment_id],target_ids=sorted({t.segment_id for t in targets}))
        private=None
        if (root/task['receipt']).is_file():
            rc=mapping.verify_regional_task(root,task,members=members);require(rc['spec']==spec,'wrong projection or original core');ident,=[v for v in rc['outputs'] if v['path']==task['paf']];stats['projected_cache_hits']+=1
        else:
            # Same raw mapping, different/missing projection. Never borrow other cores; never call a mapper.
            proof=verify_raw(root,lookup,loc['tool'],sum(meta['refs'].values()),entry['category'],entry['context'],entry['axes_sha256'],locators=True)
            require(proof['status']=='verified' and all(proof[k]==entry[k] for k in ('context_file','decision_file','chaining_receipt','raw_receipt','raw_paf','flags','raw_rows')),'original exact PAF or decision has changed')
            source=proof['raw_paf']; require(prep.identity(root,source['path'])==source,'raw identity mismatch');private=stage/'private-original-core-projections'/tid/'result.paf';private.parent.mkdir(parents=True)
            with mapping.open_paf_text(root/source['path']) as inp,private.open('x',encoding='utf-8') as target:
                target.writelines(mapping._projected_lines(inp,q,targets,artifact=source['path'].rsplit('/',1)[0]+'/result.paf'))
            require(prep.identity(root,source['path'])==source,'raw changed during private projection');ident=dict(path=task['paf'],size=private.stat().st_size,sha256=sha256_file(private));stats['projection_only_from_raw']+=1
        restrict(task['paf'],task['query_ids'],task['target_ids'],ident,'regional',private)
        if i%100==0:print('VERIFIED_ORIGINAL_PROJECTS',i,dict(stats),flush=True)
    require(stats['regional_inventories']==447 and stats['native_inventories']==4 and stats['regional_rows_retained']>0,'no real regional evidence');print('CACHED_EVIDENCE_READY',dict(stats),'files with 4D rows',len(tasks),flush=True)
    require(mode in ('request','ordinary'),'invalid comparison arm')
    results=[]; original=rule.questions; documents=[]
    def capture_questions(data,selected,assignments,*args,**kwargs):
        answer,counts=original(data,selected,assignments,*args,**kwargs);results.append((answer,counts,len(data.pair_links)));return answer,counts
    def refresh(eligible):
        require(eligible==tasks,'gate lost a completed source')
        def capture(need,have,counts,issues):
            documents.append(dict(scope='4D within-group after existing supplementary PAFs',has_path=have,counts=counts,source_intervals=record(need),issues=issues))
        return threshold.initial_questions(stage,seqs,meta['refs'],meta['assign'],meta['matrices'],threads=8,existing_catalog=catalog,supplementary=eligible,on_updated_questions=capture)
    allparts={p:SimpleNamespace(source=order[r],interval=Interval(0,n)) for p,(r,n,_) in lookup.items()};req=dict(kind='partial_source_discovery',query_ids=sorted(['q0-source-part-865ba1fbce846067c7ffff38','q0-source-part-9bf9376cf15b64235817ff09']),target_ids=sorted(allparts));gate=FallbackGate(allparts,before,refresh);decisions=[]
    def observe(request,cache_only):
        require(request is req,'native matrix changed');decisions.append('cache_probe' if cache_only else 'would_run_original');return None if cache_only else {'diagnostic_only':True}
    from contextlib import ExitStack
    from lgz_core import q0_admission as adm
    from lgz_core.q0_paths import PairLink
    from lgz_core.q0_retained_hits import RetainedHit
    def ordinary_rows(root,parts,tasks,_,threads):
        # Independent ordinary decoder/part coordinates from the admission loader, not raw window coordinates.
        seen=set()
        for task in tasks:
            paf=task['paf']
            if paf in seen:continue
            seen.add(paf)
            for hit in prep.read_paf(prep.artifact_path(root,paf),query_lengths={k:parts[k].interval.length for k in task['query_ids']},target_lengths={k:parts[k].interval.length for k in task['target_ids']},artifact=paf):
                q,t=parts[hit.query_name],parts[hit.target_name]; yield PairLink(RetainedHit.from_validated(hit,q.segment_id,t.segment_id),q.source,t.source,q.interval.start,t.interval.start)
    with ExitStack() as stack:
        stack.enter_context(patch.object(rule,'questions',side_effect=capture_questions))
        if mode=='ordinary':
            stack.enter_context(patch.object(threshold,'_supplement_links',ordinary_rows))
            stack.enter_context(patch.object(adm,'select_request_paths',side_effect=adm.select_q0_paths))
        gate.dispatch(PHASES[0],[req],tasks,observe)
    require(len(documents)==1,'missing residual questions'); detail=out/'updated-questions.json.gz'
    with detail.open('xb') as dest:dest.write(gzip.compress(json.dumps(documents[0],sort_keys=True,separators=(',',':')).encode(),mtime=0))
    require(len(results)==1 and not (stage/prep.MANIFEST).exists(),'unexpected repeat or ready publication');after,counts,nrows=results[0]; require(nrows==1212752+sum(v[2] for v in evidence),'lost or duplicated supplemented pairing');summary=lambda v: None if v is None else dict(sources=len(v),intervals=sum(map(len,v.values())),bases=sum(iv.length for vs in v.values() for iv in vs))
    write(out/'result.json',dict(group='4D',selector=mode,questions_sha256=sha256_file(detail),members=len(seqs),base_pair_rows=1212752,updated_pair_rows=nrows,source_component_sha256=LOC,before_sha256=BEFORE,before=summary(before),after=summary(after),after_demand_digest=sha256(json.dumps(record(after),sort_keys=True).encode()).hexdigest(),updated_counts=counts,project_stats=dict(stats),consumed_files=len(tasks),inventory_digest=sha256(json.dumps(evidence,separators=(',',':')).encode()).hexdigest(),matrix_actions=decisions,mapper_starts=0,published_q0=False,elapsed_s=monotonic()-start,limits='Full frozen 4D member set, 4D-to-4D rows of the four original native matrices and 447 original 4D-query regional tasks only. Original query cores preserved. Not a whole-wheat residual, not other queries into 4D, not an actual native run or authority to skip outside this set.'))
    print('UPDATED_4D',dict(stats),summary(after),decisions,flush=True)


if __name__=='__main__':main(*map(Path,sys.argv[1:4]),*sys.argv[4:])
