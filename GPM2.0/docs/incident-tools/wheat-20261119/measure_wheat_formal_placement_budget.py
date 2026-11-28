"""Real 4D 1-vs-8 admission, one ordinary graph. A read-only pre-supplement control, not a Q0 publication."""
from dataclasses import asdict
from hashlib import sha256
import json,multiprocessing as mp,os,platform,re,threading
from pathlib import Path
from time import monotonic
from unittest.mock import patch
from lgz_core import q0_admission as adm,q0_preparation as prep,q0_regional_mapping as mapping
from lgz_core.common import sha256_file
from lgz_core.q0_paths import reconstruct
from lgz_core.q0_threshold_acceptance import record
from lgz_core.q0_threshold_questions import questions
from pilot_fast_group_run import load

REF='2916252571014e63f9fbfd47e898d82027ab651df7eec8af5edd52e0be73c442'
SCI='97b691e496c4b01319d83cda9ee055b14b4efd6c17dc377d34adb082f8287223'
REV='4cbd93ba18c0c0502f5049ea6968a79ffbb60cf9'

def require(ok,msg):
    if not ok:raise RuntimeError(msg)

def digest(v):return sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def geom(v):return [[asdict(k),[asdict(iv) for iv in spans]] for k,spans in sorted(v.items())]

def put(path,v):
    with path.open('x') as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n')

def arm(data,meta,n,out):
    raw=adm.admit_placements;obs={'screen_worker_parts':0,'pair_rounds':{}};started=0
    def emit(msg):
        if msg.startswith('placement index pair evidence') and ': started' in msg:
            obs['pre_pair_index_s']=round(monotonic()-started,3)
        if msg.startswith('reference screen complete:'):
            obs['screen_worker_parts']=int(msg.rsplit('=',1)[1])
        m=re.match(r'placement pair work round=(\d+): owner_parts=(\d+) worker_parts=(\d+)',msg)
        if m: obs['pair_rounds'][m[1]]=[int(m[2]),int(m[3])]
        print('FORMAL_4D',n,msg,flush=True)
    def timed(*args,**opts):
        nonlocal started
        require(opts['screen_threads']==n and 'admission_s' not in obs,'wrong budget or repeated admission')
        started=monotonic();a=raw(*args,**opts);obs['admission_s']=round(monotonic()-started,3);return a
    # Separate fork siblings start from the same read-only heap; stage/decode only once.
    if n==1:
        a=timed(data,screen_threads=1,screen_progress=emit);full=None
    else:
        with patch.object(adm,'admit_placements',side_effect=timed):
            full=adm.select_q0_paths(data,screen_threads=n,progress=emit)
        a=full.admission
    hashes=dict(records=digest(a.records),placements=digest([asdict(p) for p in a.placements]),
                unplaced=digest(a.unplaced_segment_ids),ambiguous=digest(geom(a.ambiguous_intervals)))
    result=dict(threads=n,metrics=obs,admission_fields=hashes,policy=asdict(a.policy))
    if full is not None:
        need,_=questions(data,full,meta['assign']);s=dict(hashes,paths={k:digest(v.record()) for k,v in sorted(full.paths.items())},
            occupied=digest(geom(full.occupied)),request=digest(record(need)),has_path=any(v.path for v in full.paths.values()),
            sequences={k:sha256(reconstruct(v.path,data.sources).encode()).hexdigest() for k,v in full.paths.items() if v.path})
        result.update(scientific=s,chromosome_path_records=len(full.paths))
    put(out/f'arm-{n}.json',result);print('ADMISSION_SAVED',n,obs['admission_s'],flush=True)

def main(stage,base,out):
    historical=base/'q0-request-ready.44e274a7/qualification/candidate.json';require(sha256_file(historical)==REF,'different historical control');science=json.loads(historical.read_bytes())['scientific'];require(digest(science)==SCI,'wrong scientific reference')
    require(not list(out.glob('arm-*.json')) and not (out/'result.json').exists(),'existing control output')
    with (patch.object(prep,'_supplement',side_effect=AssertionError('native mapping forbidden')),
          patch.object(mapping,'_execute',side_effect=AssertionError('regional mapping forbidden'))):
        start=monotonic();data,meta=load(stage,base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json');load_s=monotonic()-start
        require(len(data.parts)==766 and len(data.pair_links)==1212752 and not data.original_adjacencies,'foreign 4D input');require(threading.active_count()==1,'input owner still multithreaded')
        print('FROZEN_4D_LOADED',len(data.parts),len(data.pair_links),round(load_s,3),flush=True)
        for n in (1,8):
            p=mp.get_context('fork').Process(target=arm,args=(data,meta,n,out));p.start();p.join();require(p.exitcode==0,f'arm {n} failed: {p.exitcode}')
    a,b=(json.loads((out/f'arm-{n}.json').read_text()) for n in (1,8))
    require(a['admission_fields']==b['admission_fields'] and a['policy']==b['policy'],'serial and parallel admissions differ')
    require(b['scientific']==science and b['chromosome_path_records']==22,'ordinary full selector differs from frozen 4D science')
    require(b['metrics']['screen_worker_parts']>0 and sum(v[1] for v in b['metrics']['pair_rounds'].values())>0,'parallel arm did not exercise both worker paths')
    result=dict(schema='wheat_4d_formal_placement_budget_v1',revision=REV,selector=adm.selector_identity(),python=platform.python_version(),host=platform.node(),
                evidence_inputs=dict(parts=766,source_bp=meta['bp'],pair_rows=len(data.pair_links),load_s=round(load_s,3)),
                arm_sha256={str(n):sha256_file(out/f'arm-{n}.json') for n in (1,8)},serial=a['metrics'],parallel=b['metrics'],matched_formal_fields=sorted(science),
                historical=REF,scientific=SCI,admission_fields=a['admission_fields'],mapper_starts=0,published_q0=False,
                scope='Frozen pre-supplement wheat 4D. Single-node same-input serial vs 8-thread placement only. Cold sibling processes; file staging/PAF decoding once, graph/ranking once outside the placement timing. Not a full wheat or production publication timing.')
    put(out/'result.json',result);print('FORMAL_4D_BUDGET_MATCH',a['metrics']['admission_s'],b['metrics']['admission_s'],SCI,flush=True)

if __name__=='__main__':
    import sys
    main(*(Path(p).resolve() for p in sys.argv[1:]))
