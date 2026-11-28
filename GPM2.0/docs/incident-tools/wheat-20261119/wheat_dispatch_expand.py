"""Rebuild only missing target frames; no FASTA window generation or mapper calls."""
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from hashlib import sha256
from multiprocessing import get_context
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

from check_wheat_inverse_targets import reference
from census_wheat_q0_fork import pack_context, require
from lgz_core import q0_regional_execution as execution, q0_regional_mapping as mapping
from lgz_core.common import stable_id
from lgz_core.q0_query_windows import QueryWindow, TargetWindow
from lgz_core.q0_sources import Interval
from wheat_dispatch_scope import Shoulders, get, inputs, put

KNOWN = 'f2a2c95745193581ec0144a90ba77c3fd82153c7856baba59bc65c324f673b54'
TOOL = 'cb7e8f228d516fe4632a2250d09d1635ddd7aa95588c9fd5442d1dbe6e9a20a3'


def initialize(snapshot, parts, issues, tool):
    global PARTS, RANK, QUESTIONS, MAPPER
    execution._initialize_reader(snapshot)
    PARTS, RANK, QUESTIONS, MAPPER = parts, {v[0]:p for p,v in parts.items()}, Shoulders(issues), tool


def frames(rows):
    index = execution._WORKER_INDEX
    index.verify_inputs()
    output = []
    for qid, rank, a, b in rows:
        key = RANK[rank]; n = PARTS[key][1]
        regions = index.regions(key, Interval(a,b), anchor_context=1_000_000, reference_context=10_000)
        values = index.targets(regions, context=10_000, exclude=[key]); left, right = set(), set()
        QUESTIONS.collect((rank,a,b), left); bases = 0
        for p, intervals in values.items():
            for iv in intervals:
                bases += iv.length
                QUESTIONS.collect((PARTS[p][0],iv.start,iv.end), right)
        ctx = axis = reason = None
        if not values or bases > mapping.MAX_TARGET_BASES:
            reason = 'no_reference_targets' if not values else 'regional_target_budget'
        else:
            q = QueryWindow(key,n,a,b,((a,b),)); require(q.window_id == qid, 'wrong frozen query')
            targets = sorted((TargetWindow(p,PARTS[p][1],i.start,i.end) for p,ivs in values.items() for i in ivs),key=lambda t:t.window_id)
            spec = dict(schema=mapping.CONTEXT_SCHEMA, query=mapping._window_context(q), targets=[mapping._window_context(t) for t in targets],
                        members=[[p, PARTS[p][2]] for p in sorted({key,*values})], tool=MAPPER, preset='asm10', fasta_format='wrap80_v1')
            ctx = stable_id('q0-regional-context', spec); axis = sha256(pack_context(ctx,spec,PARTS)).hexdigest()
        output.append([qid,rank,a,b,ctx,axis,sorted(left),sorted(right),reason])
    index.verify_inputs(); return output


def main(base, run, workers):
    old = run/'result'; out=run/'expand'/'result'; out.mkdir(exist_ok=True)
    known=get(old/'known.json',KNOWN); issues=get(old/'issues.json.gz',known['issues'])['issues']; todo=get(old/'pending.json.gz',known['pending_sha256'])
    snap,root,parts,order,lens=inputs(base); tool=mapping._ops().executable_identity('minimap2'); require(tool['sha256']==TOOL, 'mapper drift')
    name, stamp = next(iter(known['shards'].items())); first=get(old/name,stamp); control=first[:3]
    chunk=32; chunks=[todo[i:i+chunk] for i in range(0,len(todo),chunk)]; inventory={}; done=0
    with TemporaryDirectory(prefix='wheat-plan-') as tmp, reference(snap,root,parts,order,lens,Path(tmp)) as index, ProcessPoolExecutor(max_workers=workers,mp_context=get_context('spawn'),initializer=initialize,initargs=(index.reader_snapshot(),parts,issues,tool)) as pool:
        require(pool.submit(frames,[r[:4] for r in control]).result()==control,'frozen frame controls differ')
        print('TARGET_FRAMES_VERIFIED',len(control),'REMAINING',len(todo),flush=True)
        queue = {}; jobs = iter(enumerate(chunks))
        while True:
            while len(queue) < workers*2:
                pair=next(jobs,None)
                if pair is None: break
                i, batch=pair; name=f'planned-{i:04d}.json.gz'; path=out/name; seal=path.with_suffix('.seal'); identity=[KNOWN,known['pending_sha256'],i,batch[0][0],len(batch)]
                if seal.is_file():
                    meta=get(seal); require(meta['input']==identity and [r[:4] for r in get(path,meta['sha256'])]==batch,'invalid checkpoint'); inventory[name]=meta['sha256']; done+=len(batch); continue
                require(not path.exists(),'unsealed shard requires review'); queue[pool.submit(frames,batch)]=(name,path,seal,identity,batch)
            if not queue: break
            finished,_=wait(queue,return_when=FIRST_COMPLETED)
            for future in finished:
                name,path,seal,identity,batch=queue.pop(future); result=future.result();require([r[:4] for r in result]==batch,'output membership mismatch')
                digest=put(path,result); put(seal,dict(input=identity,sha256=digest));inventory[name]=digest; done+=len(batch)
                if len(inventory)%20==0: print('TARGET_FRAMES_BOUND',done,'/',len(todo),flush=True)
    require(done==len(todo)==known['pending_count'] and tool==mapping._ops().executable_identity('minimap2'),'incomplete plan or tool changed')
    print('ALL_TARGET_FRAMES',done,put(out/'complete.json',dict(parent=KNOWN,shards=inventory,controls=len(control),windows=done)),flush=True)


if __name__=='__main__': main(Path(sys.argv[1]),Path(sys.argv[2]),int(sys.argv[3]))
