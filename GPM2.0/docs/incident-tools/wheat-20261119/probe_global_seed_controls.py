"""Check whole-query -m2000 against an already complete native global target.

The large native baseline is NEVER rerun. Two same-family full-source controls
are selected deterministically from its existing >=10kb high-identity cross
hits. Query byte ranges avoid a second complete PAF scan. Diagnostic only:
its results are not main-workspace seed evidence or a full accuracy guarantee.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import time


def signature(path):
    s=path.stat();return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns


def sha(path):
    before=signature(path);h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    if signature(path)!=before:raise ValueError('input changed while hashing')
    return h.hexdigest()


def add_frames(frames,hit,minimum,Interval):
    if hit.matches/hit.block_length<.95:return
    blocks=[b for b in hit.aligned_blocks() if b.operation!='X']
    if sum(b.query.length for b in blocks)<minimum:return
    for b in blocks:
        offset=b.target.start-b.query.start if hit.strand=='+' else b.target.end+b.query.start
        frames[(hit.target_name,hit.strand,offset)].append(Interval(b.query.start,b.query.end))


def retention(baseline,candidate,merge):
    total=retained=0
    for key,values in baseline.items():
        left=merge(values);right=merge(candidate.get(key,()));total+=sum(x.length for x in left)
        i=j=0
        while i<len(left) and j<len(right):
            retained+=max(0,min(left[i].end,right[j].end)-max(left[i].start,right[j].start))
            if left[i].end<=right[j].end:i+=1
            else:j+=1
    return {'baseline_paired_coordinate_bp':total,'retained_paired_coordinate_bp':retained,
            'retention':retained/total if total else None}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','package-dir','lookup-dir','first-supplement','weak-plan'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--threads',type=int,default=12)
    a=p.parse_args();started=time.monotonic();work=a.workspace.resolve(strict=True)
    if resource.getrlimit(resource.RLIMIT_AS)!=(104*1024**3,104*1024**3):raise ValueError('fresh-process guard is absent')
    sys.path[:0]=[str(a.package_dir),str(work/'.prepare_lib/tools')]
    from lgz_core.common import executable_identity,read_fasta,write_fasta
    from lgz_core.q0_alignments import parse_paf_line,read_paf
    from lgz_core.q0_sources import Interval,merged_intervals
    from lgz_core.q0_regional_mapping import BASE_FLAGS
    from lgz_core.q0_preparation import atomic_write_json
    code={str(p):sha(p) for p in (a.package_dir/'lgz_core').glob('*.py')}
    receipt=json.loads(a.first_supplement.read_text());spec=receipt['spec']
    if receipt.get('status')!='success' or spec.get('schema')!='lgz_q0_mapping_v1' or spec.get('preset')!='asm10' or spec.get('alignment_flags')!=BASE_FLAGS:raise ValueError('baseline is not the complete native profile')
    if sha(a.first_supplement)!='994bfaa20bd68d035bedb7d8abacf616d826ebbb0bdc9c2cdc0b1e13b561245e':raise ValueError('native baseline receipt changed')
    lookup=json.loads((a.lookup_dir/'source-part-lookup.json').read_text())
    if sha(a.lookup_dir/'source-part-lookup.json')!=json.loads((a.lookup_dir/'receipt.json').read_text())['lookup_sha256']:raise ValueError('lookup changed')
    weak=json.loads(a.weak_plan.read_text())['request']['query_ids'];families={lookup[k]['dataset'] for k in weak}
    task=a.first_supplement.parent;query=task/'query.fa';target=task/'target.fa';baseline=task/'result.paf'
    expected={Path(row['path']).name:row for row in receipt['outputs']}
    before={str(path):signature(path) for path in (query,target,baseline,a.first_supplement)}
    for path in (query,target):
        if sha(path)!=expected[path.name]['sha256']:raise ValueError('complete native input differs')
    sequences=dict(read_fasta(query))
    if set(sequences)!=set(spec['query_ids']):raise ValueError('native query inventory differs')
    for key,sequence in sequences.items():
        if len(sequence)!=lookup[key]['length'] or hashlib.sha256(sequence.encode()).hexdigest()!=lookup[key]['sequence_sha256']:raise ValueError('query source content differs')
    long_scores=defaultdict(int);ranges=defaultdict(list);offset=0;digest=hashlib.sha256();last=None
    with baseline.open('rb') as stream:
        for number,raw in enumerate(stream,1):
            start=offset;offset+=len(raw);digest.update(raw)
            if not raw.strip() or raw.startswith(b'#'):last=None;continue
            fields=raw.split(b'\t',12)
            if len(fields)<12:raise ValueError('native PAF is malformed')
            key=fields[0].decode();other=fields[5].decode()
            if key not in sequences or other not in lookup:raise ValueError('native baseline name differs')
            if last==key and ranges[key][-1][0]+ranges[key][-1][1]==start:
                ranges[key][-1][1]+=len(raw);ranges[key][-1][3]+=1
            else:ranges[key].append([start,len(raw),number,1])
            last=key
            if (lookup[key]['dataset'] in families and lookup[other]['dataset']!=lookup[key]['dataset']
                    and int(fields[3])-int(fields[2])>=10000 and int(fields[9])/int(fields[10])>=.95):
                hit=parse_paf_line(raw.decode(),artifact=str(baseline),line_number=number)
                paired=sum(n for n,op in hit.cigar if op in 'M=')
                if paired>=10000:long_scores[key]+=paired
    if digest.hexdigest()!=expected['result.paf']['sha256'] or signature(baseline)!=before[str(baseline)]:raise ValueError('native result changed')
    eligible=sorted(long_scores,key=lambda k:(len(sequences[k]),k))
    if len(eligible)<2:
        atomic_write_json(Path('summary.json'),{'status':'insufficient_completed_same_family_controls','eligible':len(eligible),'mapper_executed':False})
        raise ValueError('two same-family native long-cross controls are required')
    controls=[eligible[(len(eligible)-1)//2],eligible[-1]]
    atomic_write_json(Path('baseline-query-index.json'),{'baseline_identity':expected['result.paf'],'controls':controls,'ranges':{k:ranges[k] for k in controls},'eligible_controls':len(eligible)})
    old={k:{threshold:defaultdict(list) for threshold in (100,10000)} for k in controls}
    with baseline.open('rb') as stream:
        for key in controls:
            for start,size,line,count in ranges[key]:
                stream.seek(start)
                for i in range(count):
                    hit=parse_paf_line(stream.readline().decode(),artifact=str(baseline),line_number=line+i)
                    if hit.query_name!=key:raise ValueError('indexed baseline query differs')
                    if lookup[hit.target_name]['dataset']!=lookup[key]['dataset']:
                        for threshold in old[key]:add_frames(old[key][threshold],hit,threshold,Interval)
                if stream.tell()!=start+size:raise ValueError('indexed baseline extent differs')
    tool=executable_identity('minimap2')
    if tool!=spec['tool']:raise ValueError('controlled mapper differs')
    query_path=Path('controls.fa').resolve();output=Path('result.paf.tmp').resolve()
    write_fasta(query_path,[(key,sequences[key]) for key in controls]);query_sha=sha(query_path)
    argv=[tool['resolved'],'-c','-x','asm10',*BASE_FLAGS,'-m','2000','-t',str(a.threads),str(target),str(query_path)]
    atomic_write_json(Path('command.json'),{'argv':argv,'tool':tool,'controls':controls,'query_sha256':query_sha,
        'target_identity':expected['target.fa'],'native_baseline':expected['result.paf'],'minimum_chain_score':2000,'production_modified':False})
    print(json.dumps({'phase':'global_control_mapping','controls':controls,'query_bases':[len(sequences[k]) for k in controls],'seconds':time.monotonic()-started}),flush=True)
    begin=time.monotonic()
    with output.open('wb') as out,Path('mapper.stderr.log').open('wb') as err:
        result=subprocess.run(argv,stdout=out,stderr=err)
    if result.returncode:raise ValueError('global candidate mapper failed; partial output is not evidence')
    new={key:defaultdict(list) for key in controls};rows=0
    for hit in read_paf(output,query_lengths={key:len(sequences[key]) for key in controls},target_lengths={key:lookup[key]['length'] for key in spec['target_ids']}):
        rows+=1
        if lookup[hit.target_name]['dataset']!=lookup[hit.query_name]['dataset']:add_frames(new[hit.query_name],hit,100,Interval)
    if sha(query_path)!=query_sha or any(signature(Path(path))!=old_signature for path,old_signature in before.items()):raise ValueError('controlled input changed')
    if sha(Path(tool['resolved']))!=tool['sha256'] or any(sha(Path(path))!=value for path,value in code.items()):raise ValueError('controlled code changed')
    reports=[{'query':key,'dataset':lookup[key]['dataset'],'query_bases':len(sequences[key]),'retention':{str(t):retention(old[key][t],new[key],merged_intervals) for t in (100,10000)}} for key in controls]
    passed=all(row['retention']['10000']['retention']==1 for row in reports)
    output.replace(Path('result.paf'))
    report={'status':'global_seed_controls_complete','minimum_chain_score':2000,'controls':reports,'all_long_control_coordinates_retained':passed,
            'mapping_seconds':time.monotonic()-begin,'seconds':time.monotonic()-started,'paf_rows':rows,'result_sha256':sha(Path('result.paf')),
            'production_modified':False,'weak_seed_61_tested':False,'whole_dataset_accuracy_proven':False,'code_sha256':code}
    atomic_write_json(Path('summary.json'),report);print(json.dumps({k:v for k,v in report.items() if k!='code_sha256'}),flush=True)


if __name__=='__main__':main()
