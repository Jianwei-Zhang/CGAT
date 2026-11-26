"""Reuse the frozen one-group evidence loader with an explicit source set.

Copied verbatim loader body from the verified 1A replay. No mapper and no new
raw alignment; row identity/order is preserved before graph construction.
"""
from collections import defaultdict
from pathlib import Path
from time import monotonic
import tempfile
from unittest.mock import patch
from wheat_single_group_replay_readonly import (producer,bind,mapping,retained_geometry_cache,
    retained_names,read_selected,need,sha256_file)


def load_links(base,owner,sources):
    began=monotonic();group='1A';main=base/'q0-whole-local-maps.soHq9Z6J'
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
    return links
