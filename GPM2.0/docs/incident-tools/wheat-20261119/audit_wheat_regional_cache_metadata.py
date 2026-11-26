"""Bounded read-only cache eligibility audit. Never read PAF/FASTA payloads or run a mapper.

This checks CURRENT metadata/size availability for the SAME historical requests,
not future-request hit rate or full content validation. Formal readers retain
those checks. Distinguish raw reuse from inexpensive projection regeneration.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import hashlib
import json
from pathlib import Path
import time

AUDITS={'known':'7c33ccedc2c24c2cb18c54f5e6c5c25ca220bfdeb45d13f455e085ad3a2d56ff',
        'expanded':'4a12d60b9ad40dead8ab5e750688f012a4625a78d138efbb18aed30b99629a8f'}


def sha(raw):return hashlib.sha256(raw).hexdigest()

def read_json(path,expected=None,maximum=16<<20):
    before=path.stat()
    if path.is_symlink() or not path.is_file() or before.st_size>maximum:
        raise ValueError('unsafe/oversized metadata '+str(path))
    raw=path.read_bytes()
    after=path.stat()
    if (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
        raise ValueError('metadata changed '+str(path))
    if expected is not None and sha(raw)!=expected:raise ValueError('metadata identity changed '+str(path))
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)


def member(root,name):
    rel=Path(name)
    if rel.is_absolute() or '..' in rel.parts:raise ValueError('unsafe recorded path')
    path=root/rel
    path.resolve().relative_to(root)
    return path


def audit_one(root,row):
    q,entry=row
    if entry.get('status')!='verified':return None
    raw=entry['raw_paf']; rr=entry['raw_receipt']; context=entry['context_file']
    result={'query':q,'raw_bytes':raw['size'],'status':'metadata_eligible'}
    try:
        for record in (raw,context):
            path=member(root,record['path'])
            if path.is_symlink() or not path.is_file() or path.stat().st_size!=record['size']:
                raise ValueError('missing or resized '+record['path'])
        receipt=read_json(member(root,rr['path']),rr['sha256'])
        spec=receipt['spec']
        if receipt.get('status')!='success' or spec['context']!=context or spec['flags']!=entry['flags'] or raw not in receipt['outputs']:
            raise ValueError('raw success/spec differs')
        # Small command/guard files only; explicitly never hash the PAF here.
        for out in receipt['outputs']:
            if out['path']==raw['path']:continue
            path=member(root,out['path'])
            if path.is_symlink() or not path.is_file() or path.stat().st_size!=out['size'] or out['size']>1<<20:
                raise ValueError('missing or oversized raw metadata')
            if sha(path.read_bytes())!=out['sha256']:raise ValueError('raw command/guard changed')
        for field in ('decision_file','chaining_receipt'):
            record=entry.get(field)
            if record is not None:read_json(member(root,record['path']),record['sha256'])
    except (OSError,ValueError,KeyError,TypeError) as error:
        result.update(status='metadata_miss',reason=str(error))
    return result


def audit_shard(root,path,pin,deadline,already):
    rows=read_json(path,pin);results=[]
    for row in rows:
        if row[0] in already:continue
        if time.monotonic()>=deadline:break
        value=audit_one(root,row)
        if value is not None:results.append(value)
    return results


def run(base,output,seconds=240,threads=8,resume=None):
    began=time.monotonic();deadline=began+seconds
    root=(base/'gpm_server').resolve();audit_root=base/'q0-whole-dispatch-20261125.9Icl9fR7'
    jobs=[]
    for kind,pin in AUDITS.items():
        folder=audit_root/('audit-'+kind)/'result';index=read_json(folder/'complete.json',pin)
        jobs.extend((folder/name,digest) for name,digest in sorted(index['shards'].items()))
    runtime=root/'.prepare_lib/tools/lgz_core'
    identities={name:sha((runtime/name).read_bytes()) for name in ('q0_alignments.py','q0_query_windows.py','q0_regional_mapping.py')}
    auditor=sha(Path(__file__).read_bytes())
    counts=Counter();seen=set();byte_counts=Counter();misses=[]
    if resume is not None:
        prior=read_json(resume,maximum=16<<20)
        if (prior.get('runtime_sha256')!=identities or prior.get('auditor_sha256')!=auditor
                or prior.get('source_root')!=str(root) or not isinstance(prior.get('checked_queries'),list)):
            raise ValueError('incompatible metadata-audit continuation')
        seen=set(prior['checked_queries'])
        if len(seen)!=prior['checked_requests']:raise ValueError('incomplete audit continuation')
        counts.update(prior['counts']);byte_counts.update(prior['raw_bytes_by_status']);misses=prior['misses']
    already=frozenset(seen)
    with ThreadPoolExecutor(max_workers=threads) as pool:
        pending=[pool.submit(audit_shard,root,path,pin,deadline,already) for path,pin in jobs]
        for future in as_completed(pending):
            for row in future.result():
                if row['query'] in seen:raise ValueError('duplicate historical request')
                seen.add(row['query']);counts[row['status']]+=1;byte_counts[row['status']]+=row['raw_bytes']
                if row['status']!='metadata_eligible':misses.append(row)
            print('CACHE_METADATA_PROGRESS',len(seen),dict(counts),round(time.monotonic()-began,1),flush=True)
    total=59278;finished=len(seen)==total
    if identities!={name:sha((runtime/name).read_bytes()) for name in identities}:
        raise ValueError('runtime changed during metadata audit')
    report={'schema':'wheat_regional_metadata_eligibility_v1','completed':finished,'expected_requests':total,
            'checked_requests':len(seen),'checked_queries':sorted(seen),'source_root':str(root),'auditor_sha256':auditor,'unexamined_requests':total-len(seen),'counts':dict(counts),'raw_bytes_by_status':dict(byte_counts),
            'metadata_eligible_fraction_of_all':counts['metadata_eligible']/total,
            'elapsed_s':round(time.monotonic()-began,2),'runtime_sha256':identities,'misses':misses,
            'mapper_starts':0,'paf_or_fasta_payloads_read':False,'raw_content_hashes_verified':False,
            'new_request_hit_rate_proven':False,'historical_projection_mode':{'projection_only':59278},
            'scope':'Same historical requests: actual success/command/guard metadata checked; PAF and context sizes only. Not proof of new-request keys, full payload integrity, or projected-cache hits.'}
    if output.exists():raise ValueError('refuse to overwrite an earlier audit')
    with output.open('x') as f:json.dump(report,f,sort_keys=True,indent=2);f.write('\n')
    print('CACHE_METADATA_RESULT',json.dumps({k:v for k,v in report.items() if k not in ('misses','checked_queries')}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('base',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--seconds',type=int,default=240);p.add_argument('--threads',type=int,default=8)
    p.add_argument('--resume',type=Path)
    a=p.parse_args();run(a.base,a.output,a.seconds,a.threads,a.resume)
