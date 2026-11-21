"""Compare an explicit candidate policy with a completed native supplement.

No baseline remapping, no main workspace writes, no adoption of candidate output.
Coverage and pair retention are diagnostics, not an assembly accuracy verdict.
"""
from pathlib import Path
from collections import defaultdict
import argparse
import hashlib
import json
import os
import resource
import signal
import subprocess
import time
import partial_coverage_sizing as geometry


def signature(path):
    s=Path(path).stat();return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)


def sha(path):
    before=signature(path);h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    if before!=signature(path):raise ValueError('input changed while hashing')
    return h.hexdigest()


def emit(event,**values):
    print(json.dumps({'at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'event':event,**values}),flush=True)


def stats(path,qlengths,tlengths):
    before=signature(path);digest=hashlib.sha256();pairs=set();counts=0;qualified=0
    unions={};buffers=defaultdict(list)
    with Path(path).open('rb') as f:
        for raw in f:
            digest.update(raw)
            if not raw.strip():continue
            fields=raw.decode('ascii').rstrip('\r\n').split('\t');counts+=1
            if len(fields)<12:raise ValueError('short PAF row')
            q,t=fields[0],fields[5];ql,qs,qe=map(int,fields[1:4]);tl,ts,te=map(int,fields[6:9]);matches,span,mapq=map(int,fields[9:12]);strand=fields[4]
            if (qlengths.get(q)!=ql or tlengths.get(t)!=tl or not 0<=qs<qe<=ql or not 0<=ts<te<=tl
                    or strand not in ['+','-'] or span<1 or not 0<=matches<=min(span,qe-qs,te-ts) or not 0<=mapq<=255):
                raise ValueError('PAF inventory, bounds or statistics differ')
            cigars=[tag[5:] for tag in fields[12:] if tag.startswith('cg:Z:')]
            if len(cigars)!=1:raise ValueError('expected exactly one CIGAR')
            blocks,_=geometry.blocks(cigars[0],qs,qe,ts,te,strand,minimum=1)
            if matches/span>=.95 and sum(e-s for s,e in blocks)>=100:
                qualified+=1;pairs.add((q,t,strand));buffers[q].extend(blocks)
                if len(buffers[q])>=max(4096,len(unions.get(q,[]))):
                    unions[q]=geometry.merged(unions.get(q,[])+buffers[q]);buffers[q].clear()
            if counts%1000000==0:emit('comparing_paf',file=Path(path).name,rows=counts)
    for q in qlengths:unions[q]=geometry.merged(unions.get(q,[])+buffers[q])
    if before!=signature(path):raise ValueError('PAF changed during comparison')
    return {'sha256':digest.hexdigest(),'rows':counts,'qualified_rows':qualified,'pairs':pairs,'coverage':unions}


def overlap_bp(left,right):
    i=j=total=0
    while i<len(left) and j<len(right):
        total+=max(0,min(left[i][1],right[j][1])-max(left[i][0],right[j][0]))
        if left[i][1]<right[j][1]:i+=1
        else:j+=1
    return total



def candidate_command(native, *, result, threads, seed_fraction=None, secondary_cap=None):
    if (seed_fraction is None) == (secondary_cap is None):
        raise ValueError("choose exactly one diagnostic profile")
    if threads < 1 or any(flag in native for flag in ["-f", "-p", "-N", "--secondary=no"]):
        raise ValueError("unexpected native options or budget")
    argv = list(native)
    argv[argv.index("-t")+1] = str(threads)
    argv[argv.index("-o")+1] = str(result)
    if seed_fraction is not None:
        if seed_fraction not in ["0.001", "0.005"]: raise ValueError("unknown seed-filter diagnostic")
        argv[-2:-2] = ["-f", seed_fraction]
        profile = {"kind": "seed_filter", "fraction": seed_fraction}
    else:
        if secondary_cap not in [100, 1000] or argv.count("-P") != 1:
            raise ValueError("unsupported bounded-secondary diagnostic")
        argv.remove("-P")
        argv[-2:-2] = ["-p", "0", "-N", str(secondary_cap)]
        profile = {"kind": "bounded_secondary", "secondary_cap": secondary_cap, "minimum_score_ratio": 0,
                   "all_chain_retention_disabled": True}
    return argv, profile


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',type=Path,required=True);p.add_argument('--task',required=True)
    profile_group=p.add_mutually_exclusive_group(required=True)
    profile_group.add_argument('--seed-fraction',choices=['0.001','0.005'])
    profile_group.add_argument('--secondary-cap',type=int,choices=[100,1000])
    p.add_argument('--threads',type=int,default=8);p.add_argument('--seconds',type=int,default=1800)
    a=p.parse_args();work=a.workspace.resolve(strict=True);out=Path.cwd().resolve()
    if out==work or work in out.parents or Path(a.task).name!=a.task or a.threads<1 or a.seconds<1:
        raise ValueError('isolated pilot path and valid budgets required')
    task=work/'grt/evidence/q0_prepare/tasks'/a.task;receipt_path=task/'success.json';receipt_sha=sha(receipt_path)
    receipt=json.loads(receipt_path.read_text());command=json.loads((task/'command.json').read_text());spec=command['spec']
    if receipt.get('status')!='success' or receipt.get('spec')!=spec:raise ValueError('requires a successful native baseline')
    expected={row['path']:row for row in receipt['outputs']}
    names={'query.fa','target.fa','result.paf','command.json'}
    if len(expected)!=4 or {Path(k).name for k in expected}!=names:raise ValueError('baseline inventory differs')
    emit('validating_completed_baseline_inputs')
    for rel,row in expected.items():
        path=work/rel
        if path.parent!=task or path.stat().st_size!=row['size'] or sha(path)!=row['sha256']:
            raise ValueError('baseline output identity differs')
    mapper=Path(spec['tool']['resolved'])
    if sha(mapper)!=spec['tool']['sha256']:raise ValueError('mapper identity differs')
    for filename in ['query.fa','target.fa']:
        alias=out/('source-'+filename);alias.symlink_to(task/filename)
        subprocess.run(['samtools','faidx',str(alias)],check=True)
    def lengths(path):
        with path.open() as f:return {r[0]:int(r[1]) for r in (line.split('\t') for line in f)}
    qlengths=lengths(out/'source-query.fa.fai');tlengths=lengths(out/'source-target.fa.fai')
    if sorted(qlengths)!=spec['query_ids'] or sorted(tlengths)!=spec['target_ids']:raise ValueError('input member names differ')
    before={rel:signature(work/rel) for rel in expected}
    if (command['argv'][-2:]!=[str(task/'target.fa'),str(task/'query.fa')]
            or command['argv'][0]!=str(mapper)):raise ValueError('unexpected native command')
    argv,profile=candidate_command(command['argv'],result=out/'candidate.paf',threads=a.threads,
                                   seed_fraction=a.seed_fraction,secondary_cap=a.secondary_cap)
    plan={'schema':'wheat_supplement_candidate_diagnostic_v1','source_receipt_sha256':receipt_sha,
          'baseline_task':a.task,'argv':argv,'seed_fraction':a.seed_fraction,'candidate_profile':profile,
          'science_scope':'isolated sensitivity test only; mixed sources, not an authorized production cross profile',
          'main_modified':False,'scientific_acceptance':False,'source_spec':spec}
    (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    def limit():resource.setrlimit(resource.RLIMIT_AS,(64*1024**3,64*1024**3))
    emit('candidate_mapper_start',argv=argv,address_space_gib=64,diagnostic_budget_seconds=a.seconds)
    started=time.monotonic();u0=resource.getrusage(resource.RUSAGE_CHILDREN)
    with (out/'mapper.stderr').open('w') as err,(out/'mapper.stdout').open('w') as stdout:
        process=subprocess.Popen(argv,stdout=stdout,stderr=err,preexec_fn=limit,start_new_session=True)
        (out/'mapper.pid').write_text(str(process.pid)+'\n')
        try:code=process.wait(timeout=a.seconds)
        except subprocess.TimeoutExpired:
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
            (out/'pilot-timeout.json').write_text(json.dumps({'pid':process.pid,'seconds':a.seconds,'main_action':'none','partial_result_accepted':False})+'\n')
            raise RuntimeError('diagnostic candidate timed out; no result adopted')
    elapsed=time.monotonic()-started;u1=resource.getrusage(resource.RUSAGE_CHILDREN)
    if code:raise RuntimeError('candidate mapper failed: '+str(code))
    if any(signature(work/rel)!=sig for rel,sig in before.items()) or sha(receipt_path)!=receipt_sha or sha(mapper)!=spec['tool']['sha256']:
        raise ValueError('source or tool changed')
    emit('comparing_complete_results',mapper_seconds=elapsed)
    baseline=stats(task/'result.paf',qlengths,tlengths);candidate=stats(out/'candidate.paf',qlengths,tlengths)
    if baseline['sha256']!=expected[str((task/'result.paf').relative_to(work))]['sha256']:raise ValueError('baseline PAF changed')
    for filename in ['query.fa','target.fa','command.json']:
        rel=str((task/filename).relative_to(work))
        if sha(work/rel)!=expected[rel]['sha256']:raise ValueError('baseline input changed before reporting')
    per_query=[]
    for q in sorted(qlengths):
        old=baseline['coverage'][q];new=candidate['coverage'][q]
        per_query.append({'query':q,'native_paired_bp':sum(e-s for s,e in old),'candidate_paired_bp':sum(e-s for s,e in new),
                          'retained_native_paired_bp':overlap_bp(old,new)})
    report={'status':'completed_diagnostic_not_scientific_acceptance','seed_fraction':a.seed_fraction,'candidate_profile':profile,
        'mapper_seconds':elapsed,'mapper_cpu_seconds':u1.ru_utime+u1.ru_stime-u0.ru_utime-u0.ru_stime,
        'all_child_peak_rss_kib':u1.ru_maxrss,'source_receipt_sha256':receipt_sha,
        'metrics_definition':'M/= query coverage and ordered query,target,strand sets from hits with identity>=0.95 and >=100 paired bases; not final admission or accuracy',
        'native_rows':baseline['rows'],'candidate_rows':candidate['rows'],
        'native_qualified_pairs':len(baseline['pairs']),'candidate_qualified_pairs':len(candidate['pairs']),
        'retained_native_qualified_pairs':len(baseline['pairs']&candidate['pairs']),
        'native_sha256':baseline['sha256'],'candidate_sha256':candidate['sha256'],'per_query':per_query,
        'scientific_acceptance':False,'main_modified':False}
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');emit('completed',**{k:v for k,v in report.items() if k!='per_query'})


if __name__=='__main__':main()
