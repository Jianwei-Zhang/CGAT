#!/usr/bin/env python3
"""Independent, read-only audit of exported final ordinary-engine evidence.

No production imports, mapper execution or FASTA/MMI assumptions from file sizes.
Large original inputs/indices are not exported; their bytes are protected by the
frozen job's guards, NOT independently rehashed by this local artifact auditor.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import statistics

MODES=('native-mmi','server-original-parts')
CASES=('default-parts','real-parts')
OP=re.compile(r'([1-9][0-9]*)([MIDNSHP=X])')
PART=re.compile(r'loaded/built the index for ([0-9]+) target sequence\(s\)')
MAPPED=re.compile(r'\[M::worker_pipeline::[^\]]+\] mapped ([0-9]+) sequences')
MID=re.compile(r'\[M::mm_mapopt_update::[^\]]+\] mid_occ = ([0-9]+)')
FINAL=re.compile(r'Real time: ([0-9.]+) sec; CPU: ([0-9.]+) sec; Peak RSS: ([0-9.]+) GB')


def require(value,message):
    if not value:raise ValueError(message)


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024**2):digest.update(block)
    return digest.hexdigest()


def read(path):
    require(path.is_file() and not path.is_symlink(),'missing/linked JSON evidence: '+str(path))
    require(path.stat().st_size<=64*1024**2,'oversized JSON evidence')
    return json.loads(path.read_text())


def owned(local,origin,remote):
    path=PurePosixPath(remote)
    require(path.is_absolute() and '..' not in path.parts,'invalid original evidence ownership')
    relative=path.relative_to(PurePosixPath(origin))
    candidate=local.joinpath(*relative.parts)
    require(local.resolve() in candidate.resolve().parents and not candidate.is_symlink(),'evidence escaped exported case')
    return candidate


def batches(records,size):
    result=[];bases=count=0
    for row in records:
        bases+=row['length'];count+=1
        if bases>=size:result.append(count);bases=count=0
    if count:result.append(count)
    return result


def paf(path,query,targets,membership):
    total=0;previous=(-1,-1);qids={name:i for i,name in enumerate(query)}
    with path.open() as stream:
        for raw in stream:
            require(raw.endswith('\n'),'incomplete PAF line')
            f=raw.rstrip('\n').split('\t');require(len(f)>=12,'PAF missing columns')
            ql,qs,qe,tl,ts,te,match,block,mq=map(int,[f[1],f[2],f[3],f[6],f[7],f[8],*f[9:12]])
            require(f[0] in query and f[5] in targets and ql==query[f[0]] and tl==targets[f[5]]
                and 0<=qs<qe<=ql and 0<=ts<te<=tl and f[4] in ('+','-')
                and 0<=match<=block and 0<=mq<=255,'PAF source/span/strand/MAPQ differs')
            order=(membership[f[5]],qids[f[0]])
            require(order>=previous,'original part/query output order changed');previous=order
            cigars=[v[5:] for v in f[12:] if v.startswith('cg:Z:')]
            require(len(cigars)==1,'missing/duplicate native CIGAR')
            cigar=cigars[0];end=q=t=0
            for value in OP.finditer(cigar):
                require(value.start()==end,'unparsed native CIGAR')
                end=value.end();length=int(value[1]);op=value[2]
                q+=length if op in 'MI=X' else 0;t+=length if op in 'MDN=X' else 0
            require(end==len(cigar) and end>0 and q==qe-qs and t==te-ts,'CIGAR/native span consumption differs')
            total+=1
    return total


def native_log(path,expected,records,size):
    text=path.read_text()
    require('qoff == r->qe - r->qs && toff == r->re - r->rs' not in text,'native assertion in successful evidence')
    groups=[]
    for line in text.splitlines():
        if match:=PART.search(line):groups.append({'targets':int(match[1]),'batches':[]})
        if match:=MAPPED.search(line):
            require(bool(groups),'mapped queries before target context');groups[-1]['batches'].append(int(match[1]))
    require([v['targets'] for v in groups]==[len(v['records']) for v in expected]
        and all(v['batches']==batches(records,size) for v in groups),'native log omitted original records or batches')
    mids=list(map(int,MID.findall(text)))
    require(len(mids)==len(expected) and len(set(mids))==1 and all(0<v<=2147483647 for v in mids),'original shared threshold missing or changed')
    finals=FINAL.findall(text);require(len(finals)==1,'native run did not finish exactly once')
    wall,cpu,rss=map(float,finals[0]);require(wall>0 and cpu>=0 and rss>=0,'invalid native resource summary')
    return mids[0],cpu,rss


def leaf(local,origin,receipt,report,targets,query,index_parts,part_id,threads,mid):
    execution=receipt['execution'];command=execution['command']
    output=PurePosixPath(receipt['path']);directory=output.parent
    require(output.name=='native.complete.paf' and receipt['status']=='native_success'
        and receipt['paf_usable'] is True and receipt['partial_PAF_reused'] is False
        and receipt['automatic_parameter_retry'] is False,'failed/partial native output was reused')
    at=lambda name:owned(local,origin,str(directory/name))
    require(read(at('native-attempt.json'))==receipt and read(at('native.execution.json'))==execution
        and read(at('native.command.json'))==command and execution['returncode']==0
        and 'interrupted' not in execution,'native command/receipt/execution differs')
    flags=['-K',str(report['batch_bases'])]
    fraction=report['minimap_filter']
    if part_id is not None and part_id>0:flags+=['-f',str(mid)]
    elif fraction is not None:flags+=['-f',fraction.rstrip('0')]
    target=str(PurePosixPath(origin)/'target.original.mmi') if part_id is None else index_parts[part_id]['path']
    expected=[report['tool']['path'],'-c','-x','asm10',*flags,'-t',str(threads),'-o',str(directory/'native.partial.paf'),target,report['sources']['query']['source']]
    require(command==expected,'actual native input/flags/output/thread grant differs')
    stderr=at('native.stderr');require(sha(stderr)==receipt['stderr_sha256'],'native stderr changed')
    current,cpu,rss=native_log(stderr,index_parts if part_id is None else [index_parts[part_id]],report['sources']['query']['records'],report['batch_bases'])
    require(mid is None or current==mid,'native actual first-part threshold differs')
    path=at('native.complete.paf');require(sha(path)==receipt['paf_sha256'],'native PAF bytes changed')
    membership={r['name']:p['part_index'] for p in index_parts for r in p['records']}
    selected=targets if part_id is None else {r['name']:r['length'] for r in index_parts[part_id]['records']}
    count=paf(path,query,selected,membership)
    return path,current,cpu,rss,count


def schedule(group,threads,budget):
    require(group['kind']=='original_index_parts_v1' and group['schema']==1
        and group['status']=='ordinary_parts_success','not a complete fresh original-part group')
    admission=group['admission'];shares=admission['thread_shares'];cap=admission['worker_address_space_bytes']
    require(admission['enabled'] is True and admission['slots']==2 and type(cap) is int and cap>0 and sum(shares)==threads
        and all(type(n) is int and n>0 for n in shares) and len(shares)==2
        and admission['group_budget_bytes']==budget
        and 2*cap+admission['controller_reserve_bytes']<=budget,'parallel CPU/memory grant oversubscribed')
    active={};seen=[];done=set();inherited=False;stamp=-1
    for event in group['events']:
        require(event['after_seconds']>=stamp,'schedule time reversed');stamp=event['after_seconds']
        kind=event['event'];i=event.get('part_index')
        if kind=='start':
            require(i==len(seen) and (i==0 or inherited) and i not in active
                and event['threads'] in shares and event['mid_occ']==(None if i==0 else group['mid_occ']), 'invalid repeated/foreign early part start')
            active[i]=event['threads'];seen.append(i);require(sum(active.values())<=threads,'concurrent CPU budget exceeded')
        elif kind=='inherit_first_part_mid_occ':
            require(not inherited and 0 in active and event['mid_occ']==group['mid_occ'],'threshold not from actual first mapper')
            inherited=True
        elif kind=='complete':
            require(i in active and i not in done,'foreign/repeated part completion');del active[i];done.add(i)
        else:raise ValueError('unknown execution schedule event')
    require(inherited and not active and done=={0,1},'incomplete source/query execution matrix')
    return cap


def case(root):
    v=read(root/'benchmark.json');require(v['status']=='complete_equal' and v['exact_ordered_paf_equal'] is True,'experiment incomplete')
    source=v['sources'];records=source['query']['records'];ref=source['reference']['records'];parts=v['index']['parts']
    require(len(parts)==2 and [p['part_index'] for p in parts]==[0,1]
        and [r for p in parts for r in p['records']]==ref,'original target/index membership changed')
    copies=v['query_copies'];original=source['original_query']['records']
    require(type(copies) is int and copies>0 and bool(original) and bool(ref)
        and len({r['name'] for r in ref})==len(ref)
        and all(type(r['length']) is int and r['length']>0 for r in original+ref), 'invalid original whole-record catalogs')
    expected=original if copies==1 else [{'name':f'copy{i:04d}|'+r['name'],'length':r['length']} for i in range(copies) for r in original]
    require(records==expected and len({r['name'] for r in records})==len(records),'derived whole-record order/membership changed')
    require(source['query']['total_bases']==sum(r['length'] for r in records)
        and source['query']['total_bases']==copies*source['original_query']['total_bases'],'derived base count changed')
    require(v['original_default_index_policy'] is (v['TEST_ONLY_index_bases'] is None),'index policy label differs')
    query={r['name']:r['length'] for r in records};targets={r['name']:r['length'] for r in ref}
    membership={r['name']:p['part_index'] for p in parts for r in p['records']}
    origin=str(PurePosixPath(v['common_index_build']['command'][v['common_index_build']['command'].index('-d')+1]).parent)
    require(v['automatic_memory_discovery_tested'] is False and v['explicit_maintainer_memory_allowance'] is True,'experiment allowance label differs')
    answer=None;mid=None;counts=[]
    for run in v['runs']:
        local=owned(root,origin,str(PurePosixPath(run['output_path']).parent))
        require(read(local/'trial.json')==run,'trial descriptor changed')
        require(run['status']=='complete' and run['mode'] in MODES and run['automatic_retry'] is False,'invalid trial or retry')
        combined=run['combination'];matrix=len(parts)*len(records)
        require(combined['all_cells_completed'] is True and combined['original_cells']==combined['native_cells']==matrix
            and combined['recovered_cells']==combined['no_candidate_cells']==0,'original native query/part cells omitted')
        body=run['native'];leaves=[]
        if run['mode']=='native-mmi':
            require(run['baseline_address_space_bytes']+run['baseline_controller_reserve_bytes']<=v['memory_mib']*1024**2,'baseline group exceeds test allowance')
            leaves=[leaf(root,origin,body,v,targets,query,parts,None,v['threads'],mid)]
        else:
            require(read(local/'native/ordinary-parts.json')==body,'group descriptor changed')
            cap=schedule(body,v['threads'],v['memory_mib']*1024**2)
            require([p['part_index'] for p in body['parts']]==[0,1] and body['queries']==records,'part completion lost original query context')
            for item in body['parts']:
                receipt_path=owned(root,origin,str(PurePosixPath(item['native']['path']).parent/'native-attempt.json'))
                require(sha(receipt_path)==item['receipt_sha256'],'native leaf descriptor bytes changed')
                require(item['memory_bytes']==cap==item['native']['execution']['address_space_limit_bytes']
                    and item['threads']==item['native']['execution']['assigned_threads'],'actual child resource limit differs')
                leaves.append(leaf(root,origin,item['native'],v,targets,query,parts,item['part_index'],item['threads'],body['mid_occ']))
        require(len({p[1] for p in leaves})==1 and (mid is None or mid==leaves[0][1]),'leaf or cross-route thresholds differ');mid=leaves[0][1]
        final=owned(root,origin,run['output_path']);ordered=hashlib.sha256()
        for path,*_ in leaves:
            with path.open('rb') as stream:
                while block:=stream.read(1024**2):ordered.update(block)
        value=sha(final);require(value==run['paf_sha256']==ordered.hexdigest(),'output/native bytes or original order changed')
        rows=paf(final,query,targets,membership);require(rows>0 and rows==run['paf_rows']==sum(p[-1] for p in leaves),'PAF rows lost or duplicated')
        require(answer is None or value==answer,'complete native and candidate answers differ');answer=value;counts.append(rows)
        pieces=sum(run[k] for k in ('mapping_with_production_receipts_seconds','merge_seconds','independent_output_audit_seconds'))
        require(abs(pieces-run['execution_stage_seconds'])<1e-4 and pieces>0,'execution cost excluded a phase')
        require(abs(sum(p[2] for p in leaves)-run['native_cpu_seconds'])<0.02,'native CPU summary differs')
    require(len(v['runs'])==4 and [(r['repeat'],r['mode']) for r in v['runs']]==[(0,MODES[0]),(0,MODES[1]),(1,MODES[1]),(1,MODES[0])],'forward/reverse complete comparison missing')
    medians={mode:statistics.median(r['execution_stage_seconds'] for r in v['runs'] if r['mode']==mode) for mode in MODES}
    speed=medians[MODES[0]]/medians[MODES[1]];change=100*(1-medians[MODES[1]]/medians[MODES[0]])
    require(v['summary']['execution_stage_median_seconds']==medians
        and math.isclose(speed,v['summary']['speedup']) and math.isclose(change,v['summary']['wall_reduction_percent'],abs_tol=1e-8),'reported stage medians or benefit differ')
    return {'status':'independently_reparsed_complete_evidence','paf_sha256':answer,'paf_rows':counts,
        'native_mmi_stage_median_seconds':medians[MODES[0]],'production_parts_stage_median_seconds':medians[MODES[1]],
        'speedup':speed,'wall_reduction_percent':change,'query_records':len(records),'query_bases':source['query']['total_bases'],
        'original_default_index_policy':v['original_default_index_policy'],'common_preparation_seconds_not_credited':v['common_preparation_seconds'],
        'FASTA_MMI_not_exported_or_independently_rehashed':True,'full_CGAT_workflow':False}


def checksum_manifest(root, name):
    path=PurePosixPath(name)
    require(not path.is_absolute() and '..' not in path.parts, 'invalid checksum manifest path')
    entries={}
    for line in (root/name).read_text().splitlines():
        wanted,relative=line.split('  ',1);path=PurePosixPath(relative)
        require(not path.is_absolute() and '..' not in path.parts and re.fullmatch('[0-9a-f]{64}',wanted), 'invalid frozen source checksum entry')
        file=root.joinpath(*path.parts)
        require(relative not in entries and file.is_file() and not file.is_symlink()
            and root.resolve() in file.resolve().parents, 'duplicate, missing or escaped checksum entry')
        require(sha(file)==wanted, 'frozen source/export bytes changed: '+relative)
        entries[relative]=wanted
    require(bool(entries), 'empty evidence checksum manifest')
    return entries


def frozen_source(root, expected_profile):
    source=read(root/'SOURCE.json')
    require(source['runtime_profile_sha256']==expected_profile, 'unexpected frozen runtime source')
    entries=checksum_manifest(root, 'SHA256SUMS')
    require(entries.get('source.tar')==source['source_archive_sha256'], 'submitted Git source archive changed')
    runtime=root/'source/GPM2.0/server/tools/long_cigar_recovery'
    files=read(runtime/'branch-runtime.json')['files_sha256']
    value=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    require(value==expected_profile, 'runtime profile differs')
    for name,wanted in files.items():
        require(Path(name).name==name and not (runtime/name).is_symlink()
            and sha(runtime/name)==wanted, 'frozen runtime bytes changed')
    return source


def allocation(root, threads, budget):
    records=read(root/'allocation.json')
    require(len(records)==1 and len(records[0]['resource_grants'])==1, 'ambiguous scheduler allocation')
    grant=records[0]['resource_grants'][0]
    require(grant['resReq']['cpu']==grant['resAlloc']['cpu']==threads, 'requested and allocated CPU differ')
    memory={k:grant[k]['mem'] for k in ('resReq','resAlloc','resLimit')}
    require(all(type(n) is int and n>0 for n in memory.values())
        and budget<=min(memory.values())*1000000, 'test allowance exceeds conservative scheduler MB budget')
    return {'job_id':records[0]['jobId'], 'allocated_cpus':threads,
        'requested_memory_MB':memory['resReq'], 'allocated_memory_MB':memory['resAlloc'],
        'reported_memory_limit_MB':memory['resLimit'],
        'explicit_mapper_group_budget_bytes':budget,
        'automatic_memory_discovery_exercised':False}


def check_merge_runs(root, trial, old_files, new_files):
    profiles={mode:hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        for mode,files in (('old',old_files),('new',new_files))}
    expected_files={'old':old_files,'new':new_files}
    samples={'old':[],'new':[]};hosts=set();rows=[]
    for name in ('00-old','00-new','01-new','01-old'):
        mode=name.split('-')[1];directory=root/name;report=read(directory/'replay.json')
        seconds=report['merge_seconds'];cpu=report['self_cpu_seconds']
        require(report['status']=='complete_equal' and report['runtime_profile']==profiles[mode]
            and report['runtime_files_sha256']==expected_files[mode], 'replay used foreign runtime or failed')
        require(report['mapping_started'] is False and report['automatic_retry'] is False
            and report['original_evidence_modified'] is False
            and report['original_source_data_and_MMI_not_reprocessed'] is True, 'replay restarted mapping or changed its input')
        require(report['combination']==trial['combination']
            and read(directory/'input-native-receipt.json')==trial['native'], 'original native receipt or complete cell matrix changed')
        require(report['paf_sha256']==trial['paf_sha256']==sha(directory/'complete.paf')
            and report['paf_rows']==trial['paf_rows'] and report['paf_bytes']==trial['paf_bytes']
            and (directory/'complete.paf').stat().st_size==trial['paf_bytes'], 'replay changed full native PAF bytes, order or counts')
        require(type(seconds) in (float,int) and math.isfinite(seconds) and seconds>0
            and type(cpu) in (float,int) and math.isfinite(cpu) and 0<=cpu<=2*seconds+1, 'invalid replay timing or CPU accounting')
        require(report['timing_scope']=='CellMerger_init_add_native_finish_including_internal_validation_not_full_CGAT', 'replay excluded production assembly validation')
        require(isinstance(report['host'],str) and bool(report['host']), 'missing replay host identity')
        hosts.add(report['host']);samples[mode].append(seconds)
        rows.append({'trial':name,'merge_seconds':seconds,'self_cpu_seconds':cpu})
    require(len(hosts)==1 and all(len(v)==2 for v in samples.values()), 'replay used different nodes or incomplete reverse repeats')
    medians={k:statistics.median(v) for k,v in samples.items()}
    return {'status':'independently_reparsed_byte_equal_replays', 'host':next(iter(hosts)),
        'trials':rows,'merge_median_seconds':medians,'speedup':medians['old']/medians['new'],
        'wall_reduction_percent':100*(1-medians['new']/medians['old']),
        'candidate_faster_in_this_control':medians['new']<medians['old'],
        'paf_sha256':trial['paf_sha256'],'paf_rows':trial['paf_rows'],
        'mapping_started':False,'full_CGAT_workflow':False,
        'not_a_combined_speedup_with_separate_64_CPU_mapping_control':True}


def merge_replay(root, original, expected_profile):
    source=frozen_source(root,expected_profile);checksum_manifest(root,'evidence.SHA256SUMS')
    terminal=read(root/'terminal-status.json')
    require(terminal['state']=='SUCCEEDED' and (root/'job.exit').read_text().strip()=='0', 'merge replay job not successful')
    require(len(terminal['resource_grants'])==1, 'ambiguous replay resource grant')
    grant=terminal['resource_grants'][0]
    require(grant['resReq']['cpu']==grant['resAlloc']['cpu']==2
        and 8*1024**3<=min(grant[k]['mem'] for k in ('resReq','resAlloc','resLimit'))*1000000, 'replay test allocation differs')
    trial=read(original/'real-parts/r00-native-mmi/trial.json')
    runtime='source/GPM2.0/server/tools/long_cigar_recovery/branch-runtime.json'
    old_files=read(original/runtime)['files_sha256'];new_files=read(root/runtime)['files_sha256']
    require(set(old_files)==set(new_files)
        and {k for k in old_files if old_files[k]!=new_files[k]}=={'native_first.py','proactive_resume.py'}, 'unreviewed source change in merge comparison')
    result=check_merge_runs(root,trial,old_files,new_files)
    result.update(job_id=terminal['job_id'],source_revision=source['source_git_revision'],
        runtime_profile=expected_profile,allocated_cpus=2,process_address_space_upper_bound_bytes=8*1024**3)
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--expected-profile',required=True)
    p.add_argument('--case',choices=CASES,action='append',help='Audit only completed cases; default requires both. Does not mark the other case complete.')
    p.add_argument('--evidence-checksums',help='Optional relative checksum manifest for the exported artifacts, in addition to frozen source checksums.')
    p.add_argument('--merge-replay-root',type=Path,help='Also audit completed old/new CellMerger replays against the original native result.')
    p.add_argument('--expected-merge-profile')
    args=p.parse_args(argv)
    require(bool(args.merge_replay_root)==bool(args.expected_merge_profile), 'merge replay root and expected profile required together')
    root=args.root.resolve();source=frozen_source(root,args.expected_profile)
    if args.evidence_checksums:checksum_manifest(root,args.evidence_checksums)
    selected=args.case or list(CASES)
    require(len(set(selected))==len(selected), 'duplicate selected evidence case')
    reports={name:read(root/name/'benchmark.json') for name in selected}
    limits={(v['threads'],v['memory_mib']*1024**2) for v in reports.values()}
    require(len(limits)==1, 'cases used different CPU or test memory grants')
    result={'schema':1,'source_revision':source['source_git_revision'],'runtime_profile':args.expected_profile,
        'scheduler':allocation(root,*next(iter(limits))),
        'cases':{name:case(root/name) for name in selected},
        'both_cases_audited':set(selected)==set(CASES),
        'scope':'existing_MMI_ordinary_execution_not_full_CGAT_or_pure_ordinary_preprocessing',
        'automatic_memory_discovery_exercised':False,'customer_wheat_acceptance':False}
    if args.merge_replay_root:
        require('real-parts' in selected, 'original real-parts evidence must be audited before its replay')
        result['merge_replay']=merge_replay(args.merge_replay_root.resolve(),root,args.expected_merge_profile)
    print(json.dumps(result,sort_keys=True,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
