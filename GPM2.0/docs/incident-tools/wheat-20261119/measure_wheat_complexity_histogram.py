"""Same-process, interleaved comparison on pinned existing wheat query FASTA. No mapping."""
from pathlib import Path
from hashlib import sha256
from time import perf_counter
from types import FunctionType
from statistics import median
import inspect,json,platform,socket,sys
from lgz_core import q0_admission as a
from lgz_core.common import read_fasta,sha256_file,stable_id
from lgz_core.q0_sources import Interval

def check(ok,msg):
    if not ok: raise ValueError(msg)

def run(root):
    kid='q0-map-8024dde83cbf20e7ffa6d8ee'; task=root/'grt/evidence/q0_prepare/tasks'/kid; rc=task/'success.json'
    check(sha256_file(rc)=='994bfaa20bd68d035bedb7d8abacf616d826ebbb0bdc9c2cdc0b1e13b561245e','foreign receipt')
    rec=json.loads(rc.read_bytes());spec=rec['spec'];check(rec['status']=='success' and stable_id('q0-map',spec)==kid,'wrong matrix')
    rel='grt/evidence/q0_prepare/tasks/'+kid+'/query.fa'; ident,=(v for v in rec['outputs'] if v['path']==rel);fa=root/rel
    check(fa.stat().st_size==ident['size'] and sha256_file(fa)==ident['sha256'],'changed query FASTA'); seqs=read_fasta(fa); members=dict(spec['members'])
    check(sorted(k for k,_ in seqs)==sorted(spec['query_ids']) and len(seqs)==150 and all(sha256(s.encode('ascii')).hexdigest()==members[k] for k,s in seqs),'source axes or sequence differ')
    candidate=Path('candidate.py').read_text(); funcs=vars(a).copy();exec(compile(candidate,'candidate.py','exec'),funcs); new=FunctionType(a._complex_intervals.__code__,funcs); old=a._complex_intervals; policy=a.AdmissionPolicy()
    spans=[(seq,Interval(offset,len(seq))) for k,seq in seqs for offset in (0,37) if len(seq)>offset]; methods={'old':old,'new':new}
    calc=lambda f:tuple(f(s,iv,policy) for s,iv in spans);expected=calc(old);check(calc(new)==expected,'warmup axes differ');timings={'old':[],'new':[]}
    for order in [('old','new'),('new','old'),('new','old'),('old','new')]:
        for tag in order:
            start=perf_counter();result=calc(methods[tag]);seconds=perf_counter()-start;check(result==expected,'accepted runs differ');timings[tag].append(round(seconds,6));del result
    data=dict(schema='wheat_complexity_histogram_control_v1',receipt=sha256_file(rc),fasta=ident['sha256'],node=socket.gethostname(),python=platform.python_version(),old_predicate=sha256(inspect.getsource(a._passes_complexity).encode()).hexdigest(),candidate=sha256(candidate.encode()).hexdigest(),sequences=len(seqs),source_bp=sum(map(lambda v:len(v[1]),seqs)),grids=len(spans),grid_offsets=[0,37],windows=sum((iv.length+99)//100 for _,iv in spans),passing_intervals=sum(map(len,expected)),interval_sha256=sha256(json.dumps([[(i.start,i.end) for i in row] for row in expected],separators=(',',':')).encode()).hexdigest(),timings_s=timings,median_s={k:median(v) for k,v in timings.items()},scope='Single-core local complexity kernel only; unchanged default grid and thresholds. Two overlapping grids of 150 real query sources, not independent samples or whole-run timing.')
    with Path('result.json').open('x') as f:json.dump(data,f,indent=2,sort_keys=True);f.write('\n')
    print('HISTOGRAM_INTERVALS_CHECKED',data['passing_intervals'],data['interval_sha256'],data['median_s'],flush=True)

if __name__=='__main__':run(Path(sys.argv[1]))
