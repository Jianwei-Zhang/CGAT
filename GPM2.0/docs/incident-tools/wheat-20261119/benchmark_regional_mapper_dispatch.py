"""Bounded native-only FIFO / completed-slot ABBA control on completed wheat.

Rebuild only selected window FASTAs, requiring their complete byte identities to
match original context receipts BEFORE any native work. No complete source DNA
load, input/profile change, production cache write or main-task restart. Each
native stdout must byte-match the original complete PAF. Does not measure full
planning/chaining/catalog consumption or the production owner's large DNA heap.
"""
import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
import math
from pathlib import Path
import socket
import sys
import time

TRACE_SHA = 'e74626d25d32da75377c79092f275f77501ccb3e340dcca100aedd3ec8b387be'
LOOKUP_SHA = '2e09b9ff5c849f4d4a83c177c46a4586c29d84b1407666dab8087615ad8c1c89'
GIB = 1024**3


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def read_json(path, maximum=64*1024**2):
    path=Path(path)
    if path.is_symlink() or path.stat().st_size>maximum:raise ValueError('unbounded/linked diagnostic input')
    return json.loads(path.read_text())


def within(root,relative):
    p=Path(relative)
    if p.is_absolute() or '..' in p.parts:raise ValueError('invalid relative input')
    path=(root/p).resolve(strict=True)
    if not path.is_relative_to(root):raise ValueError('input escapes workspace')
    return path


def replay(durations,workers,mode):
    if type(workers) is not int or workers<1 or mode not in ('ordered','completed'):
        raise ValueError('invalid replay budget/mode')
    values=list(durations)
    if not values or any(type(x) not in (int,float) or not math.isfinite(x) or x<0 for x in values):
        raise ValueError('invalid native service times')
    pending={};now=0.0
    for ordinal,duration in enumerate(values):
        if len(pending)>=workers:
            key=next(iter(pending)) if mode=='ordered' else min(pending,key=lambda k:(pending[k],k))
            now=max(now,pending.pop(key))
        pending[ordinal]=now+duration
    return max([now,*pending.values()])


def window_bytes(path,fai,start,end):
    length,offset,bases,width=fai
    if (any(type(x) is not int for x in (*fai,start,end)) or not 0<=start<end<=length
            or not 0<bases<=width or offset<0 or end-start>100_000_000):
        raise ValueError('invalid bounded source window')
    first=offset+(start//bases)*width+start%bases
    last=offset+((end-1)//bases)*width+(end-1)%bases+1
    with path.open('rb') as f:f.seek(first);raw=f.read(last-first)
    seq=raw.replace(b'\r',b'').replace(b'\n',b'').upper()
    if len(seq)!=end-start:raise ValueError('FAI/window content length changed')
    return seq.decode('ascii')


def dispatch(cases,run,workers,mode):
    if type(workers) is not int or workers<1 or mode not in ('ordered','completed'):
        raise ValueError('invalid native dispatch budget/mode')
    from lgz_core.q0_regional_execution import completed_result
    pending={};results=[];completion_order=[]
    def consume():
        if mode=='ordered':
            future=next(iter(pending));ordinal=pending.pop(future);value=future.result()
        else:ordinal,value=completed_result(pending)
        completion_order.append(ordinal);results.append((ordinal,value))
    with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='q0-native-control') as pool:
        for ordinal,case in enumerate(cases):
            if len(pending)>=workers:consume()
            pending[pool.submit(run,ordinal,case)]=ordinal
        while pending:consume()
    return [value for _,value in sorted(results)],completion_order


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','package-dir','trace','lookup','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--cases',type=int,default=64);p.add_argument('--workers',type=int,default=7)
    p.add_argument('--threads',type=int,default=16)
    a=p.parse_args();started=time.monotonic()
    if not 32<=a.cases<=64 or a.workers!=7 or a.threads!=16:raise ValueError('uncalibrated bounded native control')
    work=a.workspace.resolve(strict=True);out=a.output.resolve();package=a.package_dir.resolve(strict=True)
    if out.is_relative_to(work) or work.is_relative_to(out):raise ValueError('diagnostic output overlaps primary workspace')
    out.mkdir(exist_ok=False)
    sys.path.insert(0,str(package))
    from lgz_core.common import write_fasta
    from lgz_core.q0_regional_mapping import _execute
    from lgz_core.q0_regional_execution import allocation_memory_limit,choose_budget
    from lgz_core.q0_query_windows import QueryWindow,TargetWindow
    memory=allocation_memory_limit(a.threads)
    if memory!=160*GIB:raise ValueError('control requires current 16CPU/160GiB proof')
    budget=choose_budget(a.threads,memory,0)
    if budget.mapper_workers!=a.workers or budget.mapper_threads!=2:raise ValueError('control differs from production resource split')
    if digest(a.trace)!=TRACE_SHA or digest(a.lookup)!=LOOKUP_SHA:raise ValueError('frozen metadata changed')
    trace=read_json(a.trace);lookup=read_json(a.lookup)
    raw={row['raw_receipt']:row for row in trace['raw_markers']}
    if len(raw)!=len(trace['raw_markers']) or not 64<=len(raw)<=10000:raise ValueError('duplicate/unbounded raw cohort')
    rows=[row for row in trace['new_projects'] if row['raw'] in raw]
    if len({row['raw'] for row in rows})!=len(rows):raise ValueError('ambiguous raw/projection join')
    rows.sort(key=lambda r:(r['query']['segment_id'],r['query']['cores'][0][0],r['query']['start'],r['query']['end']))
    offset=None
    for i in range(len(rows)-a.cases+1):
        if all(0<raw[r['raw']]['real_seconds']<=45 for r in rows[i:i+a.cases]):offset=i;break
    if offset is None:raise ValueError('no bounded contiguous native cohort')
    chosen=rows[offset:offset+a.cases]
    signature=lambda path:(lambda st:(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns))(path.stat())
    tables=list(csv.DictReader(within(work,'metadata/datasets.tsv').read_text().splitlines(),delimiter='\t'))
    paths={r['dataset_name']:within(work,r['fasta_relpath']) for r in tables}
    before={str(path):signature(path) for path in paths.values()}
    indices={r['dataset_name']:{f[0]:tuple(map(int,f[1:5])) for f in
        (line.split('\t') for line in within(work,r['fai_relpath']).read_text().splitlines())} for r in tables}
    cases=[];input_bytes=0
    for project in chosen:
        rawrow=raw[project['raw']];rp=within(work,project['raw'])
        if digest(rp)!=rawrow['raw_receipt_sha256']:raise ValueError('complete raw receipt changed')
        receipt=read_json(rp,2*1024**2)
        if receipt['status']!='success':raise ValueError('raw not complete')
        context_path=within(work,receipt['spec']['context']['path'])
        if digest(context_path)!=receipt['spec']['context']['sha256']:raise ValueError('context changed')
        context=read_json(context_path,2*1024**2);spec=context['spec'];rel=str(context_path.parent.relative_to(work))
        for key,sha in spec['members']:
            if lookup[key]['sequence_sha256']!=sha:raise ValueError('source member identity changed')
        input_bytes+=sum(row['size'] for row in context['inputs'])
        if input_bytes>2*GIB:raise ValueError('bounded input reconstruction exceeds 2GiB')
        query=QueryWindow(**{k:tuple(map(tuple,v)) if k=='cores' else v for k,v in project['query'].items() if k!='window_id'})
        targets=[TargetWindow(**{k:v for k,v in w.items() if k!='window_id'}) for w in spec['targets']]
        windows=[query,*targets]
        if any(w.window_id!=r['window_id'] for w,r in zip(windows,[spec['query'],*spec['targets']])):
            raise ValueError('window header identity changed')
        def records(values):
            for window in values:
                row=lookup[window.segment_id];ds=row['dataset'];contig=row['contig']
                if row['length']!=window.segment_length:raise ValueError('source frame changed')
                yield window.window_id,window_bytes(paths[ds],indices[ds][contig],window.start,window.end)
        for name,values in (('query',[query]),('target',sorted(targets,key=lambda w:w.window_id))):
            path=out/rel/(name+'.fa');write_fasta(path,records(values))
            expected=next(r for r in context['inputs'] if r['path']==rel+'/'+name+'.fa')
            if path.stat().st_size!=expected['size'] or digest(path)!=expected['sha256']:
                raise ValueError('rebuilt complete window FASTA differs from original: '+str(path))
        olddir=rp.parent;command_path=olddir/'command.json';expected_command=next(r for r in receipt['outputs'] if r['path'].endswith('/command.json'))
        if digest(command_path)!=expected_command['sha256']:raise ValueError('original native command changed')
        command=read_json(command_path,2*1024**2);argv=command['argv'];tool=spec['tool']
        expected_paths=[str(work/rel/'target.fa'),str(work/rel/'query.fa')]
        if (argv[-2:]!=expected_paths or argv[0]!=tool['resolved'] or argv[argv.index('-t')+1]!='2'
                or command['address_space_bytes']!=4*GIB or digest(Path(tool['resolved']))!=tool['sha256']):
            raise ValueError('uncalibrated or changed original native command')
        paf=next(r for r in receipt['outputs'] if r['path'].endswith('/result.paf'))
        if digest(within(work,paf['path']))!=paf['sha256']:raise ValueError('original complete raw PAF changed')
        cases.append({'context':context,'relative':rel,'query':query,'targets':targets,'tool':tool,
                      'argv':[*argv[:-2],str(out/rel/'target.fa'),str(out/rel/'query.fa')],
                      'paf_sha256':paf['sha256'],'receipt_sha256':rawrow['raw_receipt_sha256'],
                      'raw_receipt':project['raw'],'historical_real_seconds':rawrow['real_seconds']})
    if before!={str(path):signature(path) for path in paths.values()}:raise ValueError('source changed during bounded reconstruction')
    print(json.dumps({'phase':'inputs_verified','cases':len(cases),'source_window_fasta_bytes':input_bytes,'seconds':time.monotonic()-started}),flush=True)
    phases=[]
    for phase,mode in enumerate(('ordered','completed','completed','ordered')):
        begin=time.monotonic();directory=out/('phase-'+str(phase)+'-'+mode);directory.mkdir()
        def run(ordinal,case):
            dest=directory/str(ordinal);dest.mkdir();t=time.monotonic()
            # No catalog DNA access is permitted: every generated FASTA exists
            # and _execute checks its complete identity before/after execution.
            _execute(out,dest,case['context'],case['relative'],None,case['query'],case['targets'],case['argv'],case['tool'],4*GIB)
            paf=dest/'result.paf.tmp';sha=digest(paf)
            if sha!=case['paf_sha256']:raise ValueError('native stdout differs from original complete raw evidence')
            paf.rename(dest/'result.paf')
            return {'ordinal':ordinal,'seconds':time.monotonic()-t,'sha256':sha}
        results,order=dispatch(cases,run,a.workers,mode)
        elapsed=time.monotonic()-begin
        phases.append({'phase':phase,'dispatch':mode,'seconds':elapsed,'completion_order':order,'results':results})
        print(json.dumps({'phase':phase,'dispatch':mode,'cases':len(results),'seconds':elapsed,'all_native_stdout_equal_original':True}),flush=True)
    if before!={str(path):signature(path) for path in paths.values()}:raise ValueError('original sources changed during native control')
    durations=[r['real_seconds'] for r in raw.values()]
    ordered=sum(p['seconds'] for p in phases if p['dispatch']=='ordered')
    completed=sum(p['seconds'] for p in phases if p['dispatch']=='completed')
    report={'status':'native_mapper_dispatch_abba_equal_original_stdout','hostname':socket.gethostname(),
        'sample_cases':len(cases),'selection_offset_in_completed_new_raw_cohort':offset,
        'selection':'first contiguous 64-case completed raw cohort with each historical native real <=45s',
        'input_fasta_bytes':input_bytes,'threads':a.threads,'mapper_workers':a.workers,'mapper_threads':2,
        'address_space_bytes_per_mapper':4*GIB,'allocation_memory_bytes':memory,'phases':phases,
        'ordered_over_completed':ordered/completed,'wall_time_reduction_fraction':1-completed/ordered,
        'complete_raw_stdout_equal_original':True,'main_workspace_modified':False,'main_restarted':False,
        'source_dna_loaded_whole':False,'native_mapper_executed':True,
        'raw_only_all_ready_replay_NOT_measurement':{'completed_raw_cohort':len(durations),
            'workers14_ordered_seconds':replay([raw[r['raw']]['real_seconds'] for r in rows],14,'ordered'),
            'workers14_completed_seconds':replay([raw[r['raw']]['real_seconds'] for r in rows],14,'completed')},
        'trace_sha256':TRACE_SHA,'lookup_sha256':LOOKUP_SHA,
        'cases':[{'raw_receipt':c['raw_receipt'],'receipt_sha256':c['receipt_sha256'],'paf_sha256':c['paf_sha256'],
                  'historical_real_seconds':c['historical_real_seconds']} for c in cases],
        'seconds':time.monotonic()-started,
        'limitations':['native exact-CIGAR step only: excludes planning/chaining/catalog, partial native outputs not sampled',
            'completed bounded cohort is not all remaining work and excludes worst >45s raw long-tail cases',
            'control owner has no whole-DNA heap; not full production process-launch cost or whole-wheat speedup',
            'ABBA reduces but does not eliminate hardware/cache/shared-node noise'],
        'restart_roi_proven':False,'full_wheat_completed':False}
    (out.parent/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('status','ordered_over_completed','wall_time_reduction_fraction','seconds')}),flush=True)


if __name__=='__main__':main()
