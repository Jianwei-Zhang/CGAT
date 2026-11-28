"""Rebuild ONE frozen chromosome graph and compare diagnostic search variants.

Reads completed PAFs, projects existing raw results into an isolated directory,
never invokes mapper or modifies the formal workspace. Baseline winner must
match every frozen path field before candidate results may be reported.
"""
import argparse
from collections import defaultdict
from dataclasses import asdict
from hashlib import sha256
import inspect
import json
from pathlib import Path
import tempfile
from time import monotonic
from unittest.mock import patch
import refresh_whole_wheat_cached_demand as producer
from census_wheat_q0_fork import bind
from compare_wheat_local_only_paths import load_arm
from wheat_selection_checkpoint import decode,encode
from lgz_core import q0_paths as paths, q0_regional_mapping as mapping
from lgz_core.q0_sources import SourceKey,Interval,merged_intervals
from lgz_core.q0_query_windows import QueryWindow
from lgz_core.q0_retained_hits import _checked_line,retained_names,retained_geometry_cache
from lgz_core.common import canonical_json,sha256_file

SUMMARY='d23a49af479b6c9b81916518e8034d4044ea31b5c97229c5d0ce1624138fc9d4'


def need(ok,why):
    if not ok:raise ValueError(why)


def read_selected(root,rel,identity,qn,tn,qs,ts,links,geometry):
    file=root/rel;before=producer.prep.file_signature(file);h=sha256();size=0;n=0;prefix=('['+canonical_json(rel)+',').encode('ascii')
    with file.open('rb') as stream:
        for number,raw in enumerate(stream,1):
            h.update(raw);size+=len(raw)
            if raw.startswith(b'#') or not raw.strip():continue
            f=raw.split(b'\t',6)
            if f[0].decode() not in qs or f[5].decode() not in ts:continue
            line=raw.decode('utf-8');hit=_checked_line(line,file,rel,number,prefix,qn,tn,geometry)
            links.append(paths.PairLink(hit,qs[hit.query_name],ts[hit.target_name]));n+=1
    need(h.hexdigest()==identity['sha256'] and size==identity['size'] and before==producer.prep.file_signature(file),'changed PAF '+rel)
    return n


def search_variant(mode):
    source=inspect.getsource(paths._search_paths)
    if mode!='baseline':
        source=source.replace('        positions = set()','        positions = set()\n        preferred = []',1)
        needle='            positions.update(i for i in (insertion - 1, insertion, insertion + 1) if 0 <= i <= len(seed.nodes))'
        need(source.count(needle)==1,'different seed function')
        source=source.replace(needle,'            preferred = [i for i in (insertion, insertion - 1, insertion + 1) if 0 <= i <= len(seed.nodes)]\n'+needle)
        source=source.replace('        ordered_positions = sorted(positions)','        ordered_positions = preferred + sorted(positions - set(preferred))',1)
    if mode=='reference_first_balanced_budget':
        # Fixed total 20k. Reserve local work rather than globally enlarging the
        # search. Spread insertion budget over beam members and candidate nodes;
        # original score, joins, coverage, orientation and duplicate gates remain.
        source=source.replace('    stopped = set()','    stopped = set()\n    phase_limit = max(1, policy.maximum_evaluations // 2)',1)
        source=source.replace('        if evaluations >= policy.maximum_evaluations or (quota is not None and evaluations >= quota):',
            '        if evaluations >= policy.maximum_evaluations or evaluations >= phase_limit or (quota is not None and evaluations >= quota):',1)
        source=source.replace('    initial = seed','    phase_limit = min(policy.maximum_evaluations, evaluations + len(ordered))\n    initial = seed',1)
        source=source.replace('        next_paths = {p.path_id: p for p in beam}',
            '        round_start = evaluations\n        round_limit = min(policy.maximum_evaluations, evaluations + max(1, (policy.maximum_evaluations - evaluations) // 2)) if rounds == 1 else policy.maximum_evaluations\n        next_paths = {p.path_id: p for p in beam}',1)
        source=source.replace('        for current in beam:',
            '        for beam_i, current in enumerate(beam):\n            beam_end = evaluations + max(1, (round_limit - evaluations) // max(1,len(beam)-beam_i))\n            phase_limit = min(beam_end, evaluations + max(1,(beam_end-evaluations)//10))',1)
        source=source.replace('            for node in ordered:\n                if node in current.nodes:\n                    continue',
            '            pending_nodes = [node for node in ordered if node not in current.nodes]\n            for candidate_i, node in enumerate(pending_nodes):\n                phase_limit = min(beam_end, evaluations + max(1,(beam_end-evaluations)//max(1,len(pending_nodes)-candidate_i)))',1)
        # Preserve original candidate ordering, but no useless evaluation loops
        # beyond that candidate budget. This is not removal of validity gates.
        source=source.replace('                        if "maximum_evaluations" in stopped:\n                            break',
            '                        if "maximum_evaluations" in stopped or evaluations >= phase_limit:\n                            break')
        source=source.replace('                    if "maximum_evaluations" in stopped:\n                        break',
            '                    if "maximum_evaluations" in stopped or evaluations >= phase_limit:\n                        break')
    ns=dict(vars(paths));exec(compile(source,'<diagnostic-'+mode+'>','exec'),ns)
    return ns['_search_paths'],sha256(source.encode()).hexdigest()


def footprint(path,placements):
    refs=[]
    for sl in path.slices:
        p=placements[sl.placement_id]
        for a in p.reference_blocks:
            iv=sl.interval.intersection(a.source)
            if iv is None:continue
            start=a.reference.start+iv.start-a.source.start if sl.orientation=='+' else a.reference.start+a.source.end-iv.end
            refs.append(Interval(start,start+iv.length))
    return {'source_bp':sum(s.interval.length for s in path.slices),'reference_union_bp':sum(i.length for i in merged_intervals(refs)),
            'slices':len(path.slices),'gap_count':sum(j.n_bp>0 for j in path.joins),'gap_placeholder_bp':sum(j.n_bp for j in path.joins),'score':path.score}


def run(base,owner,group):
    began=monotonic();main=base/'q0-whole-local-maps.soHq9Z6J';summary,_,record,oldpaths,_=load_arm(main,SUMMARY,'whole-wheat-local-supplement-v1')
    admitted=[]
    with (main/'selection/admission.jsonl').open('rb') as stream:
        stream.readline()
        for raw in stream:
            row=json.loads(raw)
            if isinstance(row,list):break
            p=decode(row)
            if p.chromosome==group:
                need(record[group][p.placement_id]==sha256(raw).hexdigest(),'changed admission');admitted.append(p)
    sources={p.source for p in admitted};print('GROUP_ADMISSION_BOUND',group,len(admitted),len(sources),flush=True)
    snap,ROOT,PARTS,order,lens=bind(base/'q0-latest-fork-20261123-1435/control/snapshot.json',base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json')
    ids=sorted(PARTS);members={ids[i]:s for i,s in enumerate(order)};selected_parts={k for k,s in members.items() if s in sources};selected_ranks={PARTS[k][0] for k in selected_parts}
    byname={r['path']:r for r in snap['files']};links=[];geometry=retained_geometry_cache();fullnames={ds:retained_names({s.contig:n for s,n in lens.items() if s.dataset==ds}) for ds in {s.dataset for s in lens}}
    selected_names={ds:{s.contig:s for s in sources if s.dataset==ds} for ds in fullnames}
    for i,row in enumerate(snap['alignments'],1):
        q,t,rel=row['query_dataset'],row['target_dataset'],row['paf']
        read_selected(ROOT,rel,byname[rel],fullnames[q],fullnames[t],selected_names[q],selected_names[t],links,geometry)
        if i%8==0:print('BASE_MATRIX_SCANNED',i,len(links),round(monotonic()-began,1),flush=True)
    native_order=[producer.replay.FIRST]
    with (base/'q0-child-loader-cutover-20261122-180258/resume_43017096.out').open() as stream:
        for line in stream:
            if 'weak seed: completed=' in line and '[run='+snap['source_run']+']' in line:
                tid=line.split('weak seed: completed=',1)[1].split()[0]
                if tid not in native_order:native_order.append(tid)
    need(set(native_order)==set(producer.EXPECTED),'native order changed')
    allnames={k:(k,PARTS[k][1]) for k in ids};wanted={k:members[k] for k in selected_parts}
    for tid in native_order:
        leaf='grt/evidence/q0_prepare/tasks/'+tid;rc=producer.get(ROOT/(leaf+'/success.json'),producer.EXPECTED[tid]);spec=rc['spec'];ident=next(v for v in rc['outputs'] if v['path']==leaf+'/result.paf')
        read_selected(ROOT,ident['path'],ident,{k:allnames[k] for k in spec['query_ids']},{k:allnames[k] for k in spec['target_ids']},wanted,wanted,links,geometry)
    print('NATIVE_MATRIX_SCANNED',len(links),round(monotonic()-began,1),flush=True)
    # Reconstruct the exact historical core records using the existing no-mapper
    # replay, then project ONLY requests whose query source belongs to this group.
    windows={};actual=producer.replay.plan_query_windows
    def capture(*a,**kw):
        w=actual(*a,**kw)
        if len(w)==61000:windows.update((q.window_id,q) for q in w)
        return w
    with tempfile.TemporaryDirectory(dir=owner) as tmp:
        with patch.object(producer.replay,'plan_query_windows',capture):producer.replay.replay(base,Path(tmp)/'cores')
    need(len(windows)==61000,'window plan missing');producer.WINDOWS=windows;producer.PARTS=PARTS;producer.ROOT=ROOT
    producer.STAGE=owner/'projected';producer.STAGE.mkdir(exist_ok=True);producer.MEMBERS={p:(n,h) for p,(_,n,h) in PARTS.items()}
    producer.PROJECTOR=sha256_file(Path(mapping.__file__).with_name('q0_query_windows.py'));producer.VALIDATOR=sha256_file(Path(mapping.__file__).with_name('q0_alignments.py'))
    inventory=base/'q0-whole-dispatch-20261125.9Icl9fR7';selected={}
    for mode,planpath,pin in [('known',inventory/'result/known.json',producer.KNOWN),('expanded',inventory/'expand/result/complete.json',producer.EXPAND)]:
        plan=producer.get(planpath,pin);auditroot=inventory/('audit-'+mode)/'result';audit=producer.get(auditroot/'complete.json',producer.AUDITS[mode])
        for name,pin in plan['shards'].items():
            rows=producer.get(planpath.parent/name,pin)
            if not any(r[1] in selected_ranks for r in rows):continue
            audited=dict(producer.get(auditroot/name,audit['shards'][name]))
            for row in rows:
                q,rank,lo,hi,ctx,stamp,left,right,reason=row;e=audited[q]
                if rank not in selected_ranks or e['status']!='verified':continue
                need((windows[q].start,windows[q].end)==(lo,hi),'window changed')
                context=producer.checked_leaf(e['context_file'])['spec'];producer.TOOL=context['tool']
                need(producer.TOOL['sha256']=='cb7e8f228d516fe4632a2250d09d1635ddd7aa95588c9fd5442d1dbe6e9a20a3','foreign raw mapper')
                if not any(t['segment_id'] in selected_parts for t in context['targets']):continue
                result=producer.project_one(q,stamp,e);_,tid,r,targets,digest,method=result
                selected[q]=(tid,r,targets,digest)
            print('REGIONAL_METADATA_SHARD',mode,name,'selected',len(selected),flush=True)
    # Preserve original per-window order, including the 15 later local batches.
    local=Path((main/'local-mapping-owner').read_text().strip());mapping_report=producer.get(local/'result.json',producer.LOCAL_WINDOW_RESULT);extras=defaultdict(list)
    for i,pin in enumerate(mapping_report['receipts'],1):
        row=producer.get(local/('batch-%02d.json'%i),pin);task=row['task']
        if not set(task['query_ids'])&selected_parts or not set(task['target_ids'])&selected_parts:continue
        ident={'sha256':row['projected_sha256'],'size':row['projected_bytes']}
        extras[row['query']].append((task,ident))
    for q in windows:
        if q in selected:
            tid,r,target_ranks,pin=selected[q];rel='grt/evidence/q0_prepare/regional/projects/'+tid+'/result.paf';file=producer.STAGE/rel
            read_selected(producer.STAGE,rel,{'sha256':pin,'size':file.stat().st_size},{ids[r]:allnames[ids[r]]},{ids[t]:allnames[ids[t]] for t in target_ranks},wanted,wanted,links,geometry)
        for task,ident in extras.get(q,()):
            read_selected(local/'workspace',task['paf'],ident,{k:allnames[k] for k in task['query_ids']},{k:allnames[k] for k in task['target_ids']},wanted,wanted,links,geometry)
    print('GROUP_GRAPH_INPUTS_READY',group,len(links),'projected_tasks',len(selected),round(monotonic()-began,1),flush=True)
    graph=paths.PathGraph(admitted,links,(),paths.PathPolicy(),first_request=True,progress=lambda s:print('GRAPH',s,flush=True));results={};byid={p.placement_id:p for p in admitted}
    for mode in ('baseline','reference_first','reference_first_balanced_budget'):
        graph._joins.clear();fn,code=search_variant(mode);start=monotonic();messages=[]
        def log(s):messages.append(s);print(mode,s,flush=True)
        result=fn(graph,progress=log);need(result.path is not None,'empty variant')
        if mode=='baseline':need(result.path==oldpaths[group],'baseline mismatch; stop before candidate variants')
        represented,duplicate,missing=graph.coverage.assess((s.source,s.interval) for s in result.path.slices)
        need(not duplicate and represented==result.path.score[0],'final exact coverage gate mismatch')
        results[mode]={'seconds':round(monotonic()-start,3),'function_sha256':code,'metrics':footprint(result.path,byid),'logs':messages,'full_coverage_gate_passed':True,'path':encode(result)}
        (owner/(mode+'.json')).write_text(json.dumps(results[mode],indent=2)+'\n')
    report={'schema':'wheat_one_group_search_replay_v1','group':group,'summary':SUMMARY,'baseline_full_path_equal':True,'admitted':len(admitted),'pair_links':len(links),'results':results,'mapper_calls':0,'formal_workspace_modified':False,
            'scope':'One frozen group, same admitted evidence and scientific gates, total evaluation cap unchanged at 20000. Variant speed is not an unbiased benchmark due to reused graph caches. No whole-wheat or formal acceptance claim.'}
    (owner/'replay.json').write_text(json.dumps(report,indent=2)+'\n');print('REPLAY_DONE',json.dumps({k:v['metrics'] for k,v in results.items()}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('owner',type=Path);p.add_argument('--group',default='1A');a=p.parse_args()
    need(a.owner.resolve().parent==a.base.resolve() and a.owner.name.startswith('q0-two-funnels-'),'bad owner')
    import subprocess
    with patch.object(subprocess,'Popen',side_effect=RuntimeError('external commands forbidden in read-only replay')):
        run(a.base.resolve(),a.owner.resolve(),a.group)
