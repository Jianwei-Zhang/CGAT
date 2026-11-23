"""Freeze authentic completed inputs for a separate wheat Q0 run, then build its global first request.

Never copy a live runner/lock or run source launch scripts. Copy only hash-bound scientific
inputs to private node scratch; no hard links, external symlinks, or writes to either original
run. This stage is not a canonical Q0 publication. Its receipt distinguishes full fallback,
no paths, and localized demand. Retain it for subsequent verified mapping and publication.
"""
import argparse
import csv
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sys
import time


def require(ok, message):
    if not ok: raise ValueError(message)


def sha(data): return hashlib.sha256(data).hexdigest()


def member(root, name):
    rel=Path(name)
    require(isinstance(name,str) and name==rel.as_posix() and not rel.is_absolute() and '..' not in rel.parts and '\\' not in name, 'invalid relative member')
    path=root/rel
    require(path.resolve()==path and path.is_relative_to(root), 'linked or escaped fork member')
    return path


def write(path, doc):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f: json.dump(doc,f,sort_keys=True,indent=2);f.write('\n')


def stamp(p):
    s=p.stat(); return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns


def small(path, limit=8*1024**2):
    a=stamp(path)
    with path.open('rb') as f:data=f.read(limit+1)
    require(len(data)==a[2]<=limit and stamp(path)==a,'unstable/oversize fork metadata')
    return data


def freeze(work, log, run_id, output, revision):
    root=work.resolve(strict=True); out=output.resolve(); require(not out.exists() and not out.is_relative_to(root) and re.fullmatch('[a-f0-9]{40}',revision),'invalid control directory/revision')
    owner=json.loads(small(member(root,'.run_all/lock/owner.json'))); require(owner['run_id']==run_id and Path(owner['workspace'])==root,'unexpected producer generation')
    plan=small(member(root,'.run_all/plan.tsv')); units=[]
    for r in csv.DictReader(plan.decode().splitlines(),delimiter='\t'):
        if r['unit_id']=='q0_evidence': break
        units.append(r['unit_id'])
    require(len(units)==len(set(units))==25 and units.count('assign')==1 and sum(k.startswith('ref:') for k in units)==2 and sum(k.startswith('q0_chr:') for k in units)==22,'unexpected original 25-unit topology')
    events={};prefix='[run='+run_id+']';rx=re.compile(r'\[SKIP_VALID\] \[([^\]]+)\] .*?checkpoint=(\.run_all/checkpoints/[\w.-]+\.json) checkpoint and outputs are valid\s*$')
    with log.open() as f:
        for line in f:
            if prefix not in line:continue
            m=rx.search(line)
            if m and m[1] in units:
                require(m[1] not in events,'ambiguous producer reuse event');events[m[1]]=(m[2],line.rstrip())
    require(set(events)==set(units),'producer did not validate all initial units')
    catalogue={}; accepted=[]; raw_evidence={}; by_unit={}
    for unit in units:
        name,line=events[unit]; data=small(member(root,name)); receipt=json.loads(data); payload=receipt['input_payload']; fingerprint=sha(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())
        require(receipt['status']=='success' and receipt['unit_id']==payload['unit_id']==unit and receipt['input_fingerprint']==fingerprint,'bad original checkpoint: '+unit)
        for row in [*payload['inputs'],*receipt['outputs']]:
            n=row['path']; require(set(row)>={'path','size','sha256'} and type(row['size'])==int and row['size']>=0 and re.fullmatch('[0-9a-f]{64}',row['sha256']), 'invalid original content identity')
            got={k:row[k] for k in ('path','sha256','size')};require(catalogue.setdefault(n,got)==got,'original units disagree on bytes: '+n)
        by_unit[unit]={r['path'] for r in receipt['outputs']};accepted.append({'unit':unit,'checkpoint':name,'sha256':sha(data),'validated_log_line':line});raw_evidence[name]=data
    def metadata(rel):
        data=small(member(root,rel)); require(sha(data)==catalogue[rel]['sha256'],'metadata no longer matches producer: '+rel);return data
    def table(rel):return list(csv.DictReader(metadata(rel).decode().splitlines(),delimiter='\t'))
    files={'metadata/datasets.tsv','metadata/reference.tsv','metadata/package.tsv','metadata/prepare_options.tsv','metadata/chr_assignments.tsv','metadata/track_member_orders.tsv'}
    ds=table('metadata/datasets.tsv');refs=table('metadata/reference.tsv'); require(len(refs)==1 and len(ds)==2 and table('metadata/package.tsv')[0]['reads_qc_enabled']=='false','unsupported input package')
    for d in (*ds,*refs):files.update((d['fasta_relpath'],d['fai_relpath']))
    for d in ds:
        name=d['dataset_name'];p=f'runs/{name}_vs_ref/result.paf';require(p in by_unit['ref:'+name],'reference PAF not a producer output');files.update((p,f'runs/{name}_vs_ref/tool_version.txt'))
    refs_fai=metadata(refs[0]['fai_relpath']); chromosomes=[l.split('\t')[0] for l in refs_fai.decode().splitlines()]; desc=[]
    require({'q0_chr:'+c for c in chromosomes}==set(u for u in units if u.startswith('q0_chr:')),'chromosomes differ from checkpoints')
    grouped={}
    for a in table('metadata/chr_assignments.tsv'):grouped.setdefault(a['assigned_chr_name'],{}).setdefault(a['dataset_name'],set()).add(a['seq_name'])
    for c in chromosomes:
        rel=f'runs/chr_{c}/q0_alignment_inputs.json';descriptor=json.loads(metadata(rel));require(descriptor['version']==1 and descriptor['chromosome']==c,'wrong matrix descriptor');files.add(rel)
        groups=grouped.get(c,{}); names=sorted(groups);expected={(l,r) for i,l in enumerate(names) for r in names[i:] if r!=l or len(groups[l])>1}; actual=set()
        for row in descriptor['alignments']:
            l,r=row['target_dataset'],row['query_dataset'];stem=f'{l}_vs_self' if l==r else f'{l}_vs_{r}';pf=row['paf'];require((l,r) not in actual and pf==f'runs/chr_{c}/{stem}/result.paf' and pf in by_unit['q0_chr:'+c],'unbound matrix or wrong direction');actual.add((l,r));files.add(pf);desc.append({**row,'chromosome':c})
        require(actual==expected,'incomplete initial matrix: '+c)
    require(all(k in catalogue for k in files),'unbound fork scientific input');total=sum(catalogue[n]['size'] for n in files);require(total<70*1024**3,'fork staging input exceeds approved bound')
    provenance='metadata/incident_q0_routing_reader.json';decl=small(member(root,provenance));require(sha(decl)=='62268b1ced607c65edf4074df21141a34ed4de46236b8272a632bab2339e61d2','original reader declaration changed')
    out.mkdir(mode=0o700);pr=out/'producer';pr.mkdir();(pr/'reader.json').write_bytes(decl);(pr/'plan.tsv').write_bytes(plan)
    for name,buf in raw_evidence.items():(pr/Path(name).name).write_bytes(buf)
    manifest={'schema':'wheat_threshold_fork_initial_snapshot_v1','source':str(root),'source_run':run_id,'source_owner':owner,'revision':revision,'profile':'positive_threshold','producer_checkpoints':accepted,'producer_reader_sha256':sha(decl),'source_plan_sha256':sha(plan),'alignments':sorted(desc,key=lambda x:x['paf']),'files':[catalogue[n] for n in sorted(files)],'total_bytes':total}
    write(out/'snapshot.json',manifest); print('FROZEN',len(files),total,'bytes',len(accepted),'completed units',sha(small(out/'snapshot.json')),flush=True)


def copy_bound(source, target, row, rate=None):
    require(not target.exists(),'refuse to overwrite staged input');st=stamp(source);require(st[2]==row['size'],'source size changed');target.parent.mkdir(parents=True,exist_ok=True);tmp=target.with_name(target.name+'.partial');h=hashlib.sha256();n=0;start=time.monotonic()
    with source.open('rb') as i,tmp.open('xb') as o:
        while data:=i.read(4*1024**2):
            h.update(data);o.write(data);n+=len(data)
            if rate:
                wait=n/rate-(time.monotonic()-start)
                if wait>0:time.sleep(wait)
    require(n==row['size'] and h.hexdigest()==row['sha256'] and st==stamp(source),'source changed or SHA mismatch: '+row['path']);tmp.rename(target)


def draft_stage_plan(src, manifest):
    """The initial selector reads reference names/lengths, not reference DNA. Keep its parent identity."""
    rows = manifest['files']; by_name = {r['path']: r for r in rows}
    require(len(by_name) == len(rows) and sum(r['size'] for r in rows) == manifest['total_bytes'], 'inconsistent frozen inventory')
    table = 'metadata/reference.tsv'; data = small(member(src, table))
    require(len(data) == by_name[table]['size'] and sha(data) == by_name[table]['sha256'], 'reference declaration differs from snapshot')
    refs = list(csv.DictReader(data.decode().splitlines(), delimiter='\t'))
    require(len(refs) == 1, 'one frozen reference is required')
    rel, fai = refs[0]['fasta_relpath'], refs[0]['fai_relpath']
    require(Path(rel).parent == Path('data/reference') and fai == rel+'.fai' and fai in by_name and rel in by_name,
            'cannot isolate the reference FASTA from a bound FAI')
    require(member(src,rel).stat().st_size == by_name[rel]['size'], 'deferred reference missing or resized')
    # No claim of having freshly hashed these deferred bytes; formal Q0 must stage and hash them first.
    return [r for r in rows if r['path'] != rel], by_name[rel]


def draft_thread_options(reader, requested=None):
    """A fresh fork may use its explicit run budget; never guess from node size."""
    from run_resources import execution_threads, positive
    ceiling = None if requested is None else positive(requested, 'threads')
    budget = execution_threads(ceiling or 1)
    if ceiling is not None:
        budget = min(budget, ceiling)
    if hasattr(os, 'sched_getaffinity'):
        budget = min(budget, len(os.sched_getaffinity(0)))
    if budget == 1:
        return {}  # also preserves the original frozen selector's no-keyword call
    require('threads' in inspect.signature(reader).parameters,
            'frozen threshold runtime does not support parallel first requests; use one thread or a new fork')
    return {'threads':budget}


def stage_and_draft(control, expected, workspace, rate_mib, threads=None):
    from lgz_core import q0_preparation as prep, q0_threshold_prepare as threshold
    from lgz_core.q0_threshold_acceptance import record
    options = draft_thread_options(threshold.initial_questions, threads)  # reject incompatible requests before staging
    ctrl=control.resolve(strict=True);snapshot=small(ctrl/'snapshot.json');require(sha(snapshot)==expected,'unbound fork manifest');s=json.loads(snapshot);root=workspace.resolve();src=Path(s['source']).resolve(strict=True)
    require(root.parent==Path('/tmp') and root.name.startswith('cgat-wheat-fork-') and not root.exists() and 0<rate_mib<=128,'fork requires a new, private node-local workspace');require(not ctrl.is_relative_to(src) and not src.is_relative_to(ctrl),'fork control overlaps source')
    staged, deferred = draft_stage_plan(src,s); planned=s['total_bytes']-deferred['size']
    require(shutil.disk_usage(root.parent).free>=planned+72*1024**3,'insufficient local disk reserve');root.mkdir(mode=0o700)
    write(ctrl/'started.json',{'source_run':s['source_run'],'snapshot_sha256':expected,'workspace':str(root),'hostname':socket.gethostname(),'pid':os.getpid(),'thread_budget':options.get('threads',1),'revision':s['revision'],'profile':s['profile'],'time':time.time()}); done=0;last=0
    for row in staged:
        copy_bound(member(src,row['path']),member(root,row['path']),row,rate_mib*1024**2);done+=row['size']
        if done-last>=1024**3:print('STAGED',done,'/',planned,flush=True);last=done
    # Retain the parent checkpoints as provenance, not as latest-runtime checkpoint successes.
    prov=root/'metadata/fork_parent';prov.mkdir()
    for c in s['producer_checkpoints']:
        p=Path(c['checkpoint']).name;v=small(ctrl/'producer'/p);require(sha(v)==c['sha256'],'changed parent receipt');(prov/p).write_bytes(v)
    for n,d in [('reader.json',s['producer_reader_sha256']),('plan.tsv',s['source_plan_sha256'])]:
        v=small(ctrl/'producer'/n);require(sha(v)==d,'changed parent declaration');(prov/n).write_bytes(v)
    (prov/'snapshot.json').write_bytes(snapshot)
    require(done == planned, 'staged draft input size differs')
    write(ctrl/'staged.json',{'schema':'wheat_fork_draft_staging_v2','complete_for':'first_request_only',
                              'snapshot_sha256':expected,'files':len(staged),'bytes':done,'deferred_for_formal_q0':[deferred],
                              'hostname':socket.gethostname(),'workspace':str(root),'time':time.time()})
    print('VERIFIED_DRAFT_INPUTS; REFERENCE_FASTA_DEFERRED; BEGIN_GLOBAL_THRESHOLD_DRAFT',flush=True)
    ds=prep.table(root,'metadata/datasets.tsv',('dataset_name','fasta_relpath'));seqs=prep._dataset_sequences(root,ds); ref=prep.table(root,'metadata/reference.tsv',('fai_relpath',))[0]; lengths={k:int(n) for k,n,*_ in (x.split('\t') for x in (root/ref['fai_relpath']).read_text().splitlines())}; assignments=prep.table(root,'metadata/chr_assignments.tsv',('dataset_name','seq_name','assigned_chr_name')); inventory={(s.dataset,s.contig):len(dna) for s,dna in seqs.items()}; require(all(a['assigned_chr_name'] in lengths and inventory.get((a['dataset_name'],a['seq_name']))==int(a['seq_length_bp']) for a in assignments),'assignment source or length differs')
    from unittest.mock import patch
    reader_name = "read_retained_paf" if hasattr(threshold, "read_retained_paf") else "read_paf"
    base_reader=getattr(threshold,reader_name)
    def observed(path,**kw):
        print('DRAFT_PAF_START',kw['artifact'],flush=True);n=0
        for hit in base_reader(path,**kw):n+=1;yield hit
        print('DRAFT_PAF_COMPLETE',kw['artifact'],n,flush=True)
    with patch.object(threshold,reader_name,observed):
        need,has_path=threshold.initial_questions(root,seqs,lengths,assignments,s['alignments'],**options)
    write(ctrl/'global-first-request.json',{'schema':'wheat_threshold_global_first_request_v1','snapshot_sha256':expected,'revision':s['revision'],'threshold_contract':prep.supplement_policy('positive_threshold')['decision_frontier'],'has_path':has_path,'request':record(need),'published_q0':False,'mapper_calls':0});print('GLOBAL_FIRST_REQUEST',None if need is None else len(need),'sources; has_path',has_path,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); subs=p.add_subparsers(dest='op',required=True);q=subs.add_parser('freeze');q.add_argument('workspace',type=Path);q.add_argument('log',type=Path);q.add_argument('run_id');q.add_argument('control',type=Path);q.add_argument('revision');q=subs.add_parser('run');q.add_argument('control',type=Path);q.add_argument('snapshot_sha');q.add_argument('workspace',type=Path);q.add_argument('--rate-mib',type=int,default=80)
    q.add_argument('--threads', type=int, help='fork CPU ceiling; honors GPM_RUN_THREADS, otherwise defaults to one when omitted')
    a=p.parse_args();freeze(a.workspace,a.log,a.run_id,a.control,a.revision) if a.op=='freeze' else stage_and_draft(a.control,a.snapshot_sha,a.workspace,a.rate_mib,a.threads)
