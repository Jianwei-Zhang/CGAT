#!/usr/bin/env python3
"""Internal whole-record query batching trial, not enabled in production.

One complete target index per task; contiguous whole query batches; fail closed
on multipart indexes. Global CPU/memory admission, durable validated batch
checkpoints, original-order merge. No modification of input or retained runs.
"""
from __future__ import annotations
import argparse
import contextlib
import fcntl
import hashlib
import json
import math
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

FLAGS = ['-c', '-x', 'asm10', '-X', '--no-hash-name', '-m', '200', '-n', '100']
INDEX_FLAGS = ['-x', 'asm10', '-I', '8G']


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''): h.update(block)
    return h.hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def atomic_json(path, value):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    os.replace(temp,path)


@contextlib.contextmanager
def lock(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield


def records(path):
    header=None;chunks=[]
    with Path(path).open('rb') as f:
        for line in f:
            if line.startswith(b'>'):
                if header is not None: yield header,b''.join(chunks)
                header=line;chunks=[]
            else:
                if header is None: raise ValueError('Sequence before header')
                chunks.append(line)
    if header is not None: yield header,b''.join(chunks)


def plan_batches(source, destination, max_bases):
    """Preserve original headers/bytes/order; never split one contig."""
    destination.mkdir(parents=True,exist_ok=True)
    batches=[];seen=set();entries=[];bases=0;parts=[]
    def flush():
        nonlocal entries,bases,parts
        if not entries:return
        path=destination/f'query-{len(batches):05d}.fa';payload=b''.join(parts)
        if path.exists():
            if path.read_bytes()!=payload:raise ValueError('Existing batch differs')
        else:
            temp=path.with_suffix('.tmp');temp.write_bytes(payload);temp.replace(path)
        batches.append({'query':str(path),'sha256':sha(path),'entries':entries,'bases':bases})
        entries=[];bases=0;parts=[]
    for header,body in records(source):
        name=header[1:].split()[0].decode();length=sum(len(x.strip()) for x in body.splitlines())
        if name in seen or not length:raise ValueError('Duplicate/empty query record')
        seen.add(name)
        if entries and bases+length>max_bases:flush()
        entries.append({'name':name,'length':length});bases+=length;parts.extend((header,body))
        if bases>=max_bases:flush()
    flush()
    if not batches:raise ValueError('No queries')
    return batches


def valid(directory, key, filenames):
    try:
        record=json.loads((directory/'complete.json').read_text())
        return record['key']==key and set(record['outputs'])==set(filenames) and all(
            sha(directory/name)==record['outputs'][name] for name in filenames)
    except (OSError,ValueError,KeyError):return False


def publish(directory, key, filenames):
    atomic_json(directory/'complete.json',{'key':key,'outputs':{n:sha(directory/n) for n in filenames}})


def build_index(mm, target, out, key):
    filenames=['target.mmi','stderr.log']
    if valid(out,key,filenames):return True
    out.mkdir(parents=True,exist_ok=True)
    # Read-only full FASTA; keep original target record order/names and -I default.
    with (out/'stderr.log').open('wb') as err:
        subprocess.run([mm,*INDEX_FLAGS,'-t','2','-d',str(out/'target.mmi.tmp'),str(target)],stderr=err,stdout=subprocess.DEVNULL,check=True)
    text=(out/'stderr.log').read_text()
    if text.count('distinct minimizers:')!=1:
        raise ValueError('Multipart/unknown index rejected; no query-order concatenation allowed')
    os.replace(out/'target.mmi.tmp',out/'target.mmi')
    publish(out,key,filenames)
    return False


def validate_raw(path, entries, target_names):
    ranks={r['name']:i for i,r in enumerate(entries)};lengths={r['name']:r['length'] for r in entries}
    previous=-1
    with path.open() as f:
        for line in f:
            x=line.rstrip('\n').split('\t')
            if len(x)<12 or x[0] not in ranks or x[5] not in target_names:
                raise ValueError('Unexpected/incomplete raw PAF')
            if ranks[x[0]]<previous:raise ValueError('Unexpected query order/multipart mapping')
            previous=ranks[x[0]]
            if int(x[1])!=lengths[x[0]] or not 0<=int(x[2])<=int(x[3])<=int(x[1]):raise ValueError('Query coordinates')
            if int(x[6])!=target_names[x[5]] or not 0<=int(x[7])<=int(x[8])<=int(x[6]):raise ValueError('Target coordinates')
            if x[4] not in ('+','-') or not any(t.startswith('cg:Z:') for t in x[12:]):raise ValueError('Missing CIGAR/strand')
    # An empty file is valid only after process success; checkpoint includes all
    # query records, including those that emitted zero hits.


def worker(spec_path):
    spec=json.loads(spec_path.read_text());out=Path(spec['out']);out.mkdir(parents=True,exist_ok=True)
    names=['raw.paf','result.paf','minimap.stderr','resource.txt']
    with lock(out/'lock'):
        for field in ('query','index','tool','restore','name_map'):
            if sha(spec[field])!=spec[field+'_sha256']:raise ValueError('Changed '+field)
        if valid(out,spec['key'],names):print('BATCH_CACHE_HIT',out.name,flush=True);return
        for stale in (out/'complete.json',):
            if stale.exists():stale.rename(out/('invalid-complete-'+str(time.time_ns())+'.json'))
        tmp=Path(tempfile.mkdtemp(prefix='attempt-',dir=out))
        threads=int(os.environ.get('GPM_TASK_THREADS','1'))
        if not 1<=threads<=len(spec['entries']):raise ValueError('Invalid worker thread grant')
        command=['/usr/bin/time','-v','-o',str(tmp/'resource.txt'),spec['tool'],*FLAGS,'-t',str(threads),spec['index'],spec['query']]
        atomic_json(tmp/'command.json',command)
        with (tmp/'raw.paf').open('wb') as raw,(tmp/'minimap.stderr').open('wb') as err:
            subprocess.run(command,stdout=raw,stderr=err,check=True)
        if (tmp/'minimap.stderr').read_text().count('distinct minimizers:')!=1:
            raise ValueError('Mapping index part count changed')
        validate_raw(tmp/'raw.paf',spec['entries'],spec['target_names'])
        with (tmp/'raw.paf').open('rb') as raw,(tmp/'result.paf').open('wb') as paf:
            subprocess.run([sys.executable,spec['restore'],spec['name_map']],stdin=raw,stdout=paf,check=True)
        for name in names:os.replace(tmp/name,out/name)
        publish(out,spec['key'],names)
        print('BATCH_COMMITTED',out.name,'threads',threads,flush=True)


class Admission:
    def __init__(self,features,memory):self.features=features;self.memory=memory
    def __call__(self,pending,available,budget,active,slots):
        free=self.memory-sum(self.features[x['task'].unit_id]['memory'] for x in active)
        result=[]
        for t in sorted(pending,key=lambda x:self.features[x.unit_id]['work'],reverse=True):
            f=self.features[t.unit_id]
            # A skewed batch does not warrant reserving every available thread.
            n=min(t.max_threads,max(1,math.ceil(f['bases']/f['largest'])))
            if n>available or f['memory']>free:continue
            result.append((t,n));available-=n;free-=f['memory']
            if not available or len(result)>=slots:break
        return result


def run(args):
    sys.path.insert(0,str(args.tools))
    from alignment_tasks import AlignmentTask,run_tasks
    from self_alignment_experiments import paf_summary
    root=args.root.resolve();root.mkdir(parents=True,exist_ok=args.resume)
    with lock(root/'run.lock'):
        report_path=root/'report.json'
        old=json.loads(report_path.read_text()) if report_path.exists() else None
        if old and not args.resume:raise ValueError('Use explicit resume')
        tool=str(Path(shutil.which('minimap2')).resolve());tool_hash=sha(tool)
        case_paths=[args.workspace/'runs/chr_BSWB01000001.1/hifiasm_vs_self',args.workspace/'runs/chr_BSWB01000003.1/flye_vs_self']
        payload={'schema':1,'tool_sha256':tool_hash,'flags':FLAGS,'index_flags':INDEX_FLAGS,'batch_bases':args.batch_bases,
                 'worker_sha256':sha(Path(__file__)),'python':sys.version,'threads':args.threads,'memory_gb':args.memory_gb,'inputs':{}}
        for p in case_paths:payload['inputs'][str(p)]={n:sha(p/n) for n in ('self_target.fa','self_query.fa','self_name_map.tsv','restore_self_paf.py')}
        fingerprint=identity(payload)
        if old and old['fingerprint']!=fingerprint:raise ValueError('Inputs/tool/config changed; choose new root')
        report={'status':'RUNNING','fingerprint':fingerprint,'payload':payload,'cache_mode':'own-batch-resume' if args.resume else 'cold',
                'boundary':'Whole-record query batches, immutable complete single-part targets, original names/order/flags. No single-contig splitting. Retained original PAF baseline is read only; its timing is not same-node control. Index/planning, mapping and validation timed separately. No production default or public flags.', 'index':{},'batches':[],'completed':[]}
        def save():atomic_json(report_path,report)
        save();started=time.monotonic();tasks=[];features={};groups={};hits=0
        for source in case_paths:
            name=source.parent.name+'__'+source.name;dest=root/name;dest.mkdir(exist_ok=True)
            target=source/'self_target.fa';target_names={}
            for header,body in records(target):
                n=header[1:].split()[0].decode()
                if n in target_names:raise ValueError('Duplicate target')
                target_names[n]=sum(len(l.strip()) for l in body.splitlines())
            if sum(target_names.values())>=8_000_000_000:raise ValueError('Multipart target outside experiment')
            key=identity({'tool':tool_hash,'target':sha(target),'flags':INDEX_FLAGS})
            t=time.monotonic();hit=build_index(tool,target,dest/'index',key)
            index=dest/'index/target.mmi';ih=sha(index)
            report['index'][name]={'seconds':time.monotonic()-t,'cache_hit':hit,'sha256':ih}
            batches=plan_batches(source/'self_query.fa',dest/'queries',args.batch_bases);groups[name]=(source,dest,batches)
            for i,b in enumerate(batches):
                out=dest/f'batch-{i:05d}';spec={'out':str(out),'query':b['query'],'query_sha256':b['sha256'],'entries':b['entries'],
                    'index':str(index),'index_sha256':ih,'tool':tool,'tool_sha256':tool_hash,
                    'restore':str(source/'restore_self_paf.py'),'restore_sha256':sha(source/'restore_self_paf.py'),
                    'name_map':str(source/'self_name_map.tsv'),'name_map_sha256':sha(source/'self_name_map.tsv'),
                    'target_names':target_names,'worker_sha256':sha(Path(__file__))}
                spec['key']=identity(spec);out.mkdir(exist_ok=True);spec_path=out/'spec.json';atomic_json(spec_path,spec)
                bid=name+f':{i}';cached=valid(out,spec['key'],['raw.paf','result.paf','minimap.stderr','resource.txt'])
                report['batches'].append({'id':bid,'bases':b['bases'],'records':len(b['entries']),'cache_hit':cached})
                if cached:hits+=1;continue
                script=out/'command.sh';script.write_text('exec '+shlex.join([sys.executable,str(Path(__file__).resolve()),'--worker',str(spec_path)])+'\n')
                # Conservative peak estimate includes process-private index/mapping
                # buffers. Not an enforced RSS limit; scheduler remains final limit.
                memory=2*1024**3+index.stat().st_size*2+sum(target_names.values())*10+b['bases']*48
                if memory>args.memory_gb*1024**3:raise ValueError('One batch exceeds memory estimate budget')
                features[bid]={'memory':memory,'bases':b['bases'],'largest':max(e['length'] for e in b['entries']),'work':b['bases']*sum(target_names.values())}
                tasks.append(AlignmentTask(bid,script,min(args.threads,len(b['entries'])),features[bid]['work']))
        report['planning_index_seconds']=time.monotonic()-started;report['cache_hits']=hits;save()
        mapping=time.monotonic();running={};last=mapping;reserved=0;low=0
        def account():
            nonlocal last,reserved,low
            now=time.monotonic();n=sum(v['threads'] for v in running.values());reserved+=(now-last)*n
            if n<args.threads/2:low+=now-last
            last=now
        def begin(task,n):
            account();running[task.unit_id]={'threads':n,'start':time.monotonic()}
            print('START',task.unit_id,'threads',n,flush=True)
        def end(task,code,cancelled):
            account();v=running.pop(task.unit_id);report['completed'].append({'id':task.unit_id,'exit':code,'threads':v['threads'],'seconds':time.monotonic()-v['start'],'cancelled':cancelled});save()
            print('END',task.unit_id,'exit',code,flush=True)
        code=run_tasks(tasks,args.threads,{},lambda:15 if time.monotonic()-mapping>43200 else None,begin,lambda *_:None,end,os.environ.copy(),dispatch=Admission(features,args.memory_gb*1024**3))
        account();report['mapping_seconds']=time.monotonic()-mapping;report['reserved_core_seconds']=reserved;report['below_half_reserved_seconds']=low
        if code:report['status']='FAILED_OR_TIMEOUT';save();raise SystemExit(code)
        report['comparison']={}
        for name,(source,dest,batches) in groups.items():
            merged=dest/'result.paf';tmp=merged.with_suffix('.tmp')
            with tmp.open('wb') as f:
                for i,b in enumerate(batches):
                    out=dest/f'batch-{i:05d}';spec=json.loads((out/'spec.json').read_text())
                    if not valid(out,spec['key'],['raw.paf','result.paf','minimap.stderr','resource.txt']):raise ValueError('Batch not committed')
                    with (out/'result.paf').open('rb') as src:shutil.copyfileobj(src,f)
            tmp.replace(merged);summary=paf_summary(merged)
            if (source/'result.paf').is_file():
                baseline=paf_summary(source/'result.paf')
                report['comparison'][name]={'ordered_equal':summary['ordered_sha256']==baseline['ordered_sha256'],
                    'content_equal':all(summary[k]==baseline[k] for k in ('rows','unordered_digest_sum','unordered_digest_square_sum')),
                    'baseline':baseline,'batched':summary}
            else:report['comparison'][name]={'status':'BASELINE_PENDING','batched':summary}
        report['status']='PASS' if all(c.get('ordered_equal') for c in report['comparison'].values()) else 'REVIEW_REQUIRED'
        report['total_seconds']=time.monotonic()-started
        save();print('QUERY_BATCH_RESULT',report['status'],'cache_hits',hits,flush=True)
        if report['status']!='PASS':raise SystemExit(1)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--worker',type=Path)
    p.add_argument('--root',type=Path);p.add_argument('--workspace',type=Path);p.add_argument('--tools',type=Path)
    p.add_argument('--threads',type=int,default=16);p.add_argument('--memory-gb',type=int,default=96)
    p.add_argument('--batch-bases',type=int,default=20_000_000);p.add_argument('--resume',action='store_true');a=p.parse_args()
    if a.worker:worker(a.worker);return
    if not a.root or not a.workspace or not a.tools or min(a.threads,a.memory_gb,a.batch_bases)<1:p.error('Required paths and positive budgets')
    run(a)

if __name__=='__main__':main()
