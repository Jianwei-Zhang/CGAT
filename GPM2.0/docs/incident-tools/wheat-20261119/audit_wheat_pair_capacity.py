"""Sequence-capacity control on a predeclared stride of an archived whole-wheat RAW cohort.
No live mapping, full source reads, reconstruction or customer workspace writes.
"""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from time import monotonic

from lgz_core.q0_alignments import parse_paf_line

SUMMARY_SHA='8d774d0fd5ac8652f503375a75c997c8182852041d5fe052e3c6a88c66047901'


def checked(base, rel, digest, maximum):
    p=Path(rel)
    if p.is_absolute() or '..' in p.parts or (base/p).is_symlink(): raise ValueError('invalid archive path')
    p=(base/p).resolve(strict=True)
    if not p.is_relative_to(base) or p.stat().st_size>maximum: raise ValueError('input escapes bounded archive')
    with p.open('rb') as f: raw=f.read(maximum+1)
    if len(raw)>maximum or sha256(raw).hexdigest()!=digest: raise ValueError(f'archive identity differs: {p.name}')
    return raw


def fasta(raw):
    records={}; name=None; lines=[]
    for row in raw.splitlines():
        if row.startswith(b'>'):
            if name is not None: records[name]=b''.join(lines)
            name=row[1:].decode('ascii'); lines=[]
            if not name or name in records: raise ValueError('duplicate/missing FASTA ID')
        elif name and row: lines.append(row)
        else: raise ValueError('unexpected FASTA content')
    if name: records[name]=b''.join(lines)
    if not records or not all(records.values()): raise ValueError('empty FASTA')
    return records


def run(archive, work, binary):
    summary=json.loads(checked(archive,'summary.json',SUMMARY_SHA,1<<20)); cases=summary['cases']
    if len(cases)!=64 or not summary['complete_raw_stdout_equal_original']: raise ValueError('wrong frozen cohort')
    results=[]; total_bytes=0
    for i in range(0,64,8):  # fixed before looking at any pair of sequences or mapper output
        case=cases[i]; receipt=json.loads(checked(work,case['raw_receipt'],case['receipt_sha256'],2<<20))
        if receipt['status']!='success': raise ValueError('incomplete source result')
        c=receipt['spec']['context']; context=json.loads(checked(work,c['path'],c['sha256'],2<<20)); source={}
        for row in context['inputs']:
            rel=Path(row['path']); name=rel.name
            if name not in ('query.fa','target.fa') or name in source or rel.parent!=Path(c['path']).parent: raise ValueError('unexpected context member')
            total_bytes+=row['size']
            if total_bytes>512<<20: raise ValueError('stride exceeds frozen byte budget')
            raw=checked(archive,Path('artifacts')/rel,row['sha256'],min(row['size'],128<<20))
            if len(raw)!=row['size']: raise ValueError('input size mismatch')
            source[name]=fasta(raw)
        q=source['query.fa'];t=source['target.fa'];spec=context['spec']
        if (len(q)!=1 or {k:len(v) for k,v in q.items()}!={spec['query']['window_id']:spec['query']['end']-spec['query']['start']}
                or {k:len(v) for k,v in t.items()}!={w['window_id']:w['end']-w['start'] for w in spec['targets']}):raise ValueError('unbound context inventory')
        qid,sequence=next(iter(q.items())); start=monotonic()
        protocol=b''.join([b'Q\t'+sequence+b'\n',*(b'T\t'+s+b'\n' for s in t.values())]); out=subprocess.run([binary],input=protocol,stdout=subprocess.PIPE,timeout=180,check=True).stdout.decode('ascii').splitlines()
        elapsed=monotonic()-start
        if len(out)!=len(t) or set(out)-{'possible','uncertain','short','excluded'}: raise ValueError('invalid result stream')
        screen=dict(zip(t,out));high=set(); seen=set();false=0
        paf=checked(archive,Path('artifacts/phase-0-ordered')/str(i)/'result.paf',case['paf_sha256'],32<<20)
        if [x['sha256'] for x in receipt['outputs'] if Path(x['path']).name=='result.paf']!=[case['paf_sha256']]:raise ValueError('PAF not bound to the original raw')
        for n,line in enumerate(paf.decode('ascii').splitlines(),1):
            if not line or line.startswith('#'): continue
            h=parse_paf_line(line,artifact='raw',line_number=n)
            if h.query_name!=qid or h.query_length!=len(sequence) or h.target_length!=len(t[h.target_name]):raise ValueError('wrong PAF frame')
            seen.add(h.target_name)
            if 20*h.matches>=19*h.block_length and sum(k for k,op in h.cigar if op in 'M=')>=100:
                high.add(h.target_name);false+=int(screen[h.target_name] in ('short','excluded'))
        ex={k for k,v in screen.items() if v in ('excluded','short')}
        results.append({'ordinal':i,'targets':len(t),'screen':dict(Counter(out)), 'target_bp':sum(map(len,t.values())),
                        'excluded_target_bp':sum(len(t[k]) for k in ex),'eligible_observed_pairs':len(high),
                        'weak_observed_among_excluded':len(ex&seen),'false_exclusions_of_eligible_rows':false,
                        'complete_window_excludable_by_capacity':len(ex)==len(t),'historical_mapper_real_seconds':case['historical_real_seconds'],
                        'screen_seconds_including_transport':round(elapsed,4)})
        print('verified ordinal',i,'pairs',len(t),'excluded',len(ex),'false',false,flush=True)
    return {'schema':'frozen_wheat_raw_capacity_stride_v1','new_mapper_executions':0,'source_summary_sha256':SUMMARY_SHA,
            'scope':'ordinals 0,8,...,56 in historical contiguous <=45s 64-job cohort; not random or whole-wheat demand',
            'bound_fasta_bytes':total_bytes,'cases':results}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('archive','workspace','binary','output'):p.add_argument(n,type=Path)
    a=p.parse_args();archive=a.archive.resolve(strict=True);work=a.workspace.resolve(strict=True);out=a.output.resolve()
    if out.exists() or any(out.is_relative_to(d) for d in (work,archive)):raise ValueError('output overlaps source')
    r=run(archive,work,a.binary.resolve(strict=True))
    with out.open('x') as f:json.dump(r,f,sort_keys=True,indent=2);f.write('\n')
