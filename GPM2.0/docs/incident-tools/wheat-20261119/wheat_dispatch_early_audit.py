"""Overlap *the same* raw audit with target planning. No second producer for an output directory."""
from concurrent.futures import ProcessPoolExecutor, as_completed
import ctypes
import errno
from hashlib import sha256
import os
from pathlib import Path
import sys
from wheat_dispatch_audit import KNOWN, check, get, init, put, require


def handoff(stage, dest):
    # Both directories share the same filesystem. Never merge or overwrite an
    # active consumer directory, including in the instant before its first write.
    ren = ctypes.CDLL(None,use_errno=True).renameat2
    ren.argtypes = [ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
    if ren(-100,os.fsencode(stage),-100,os.fsencode(dest),1)==0:return True
    code=ctypes.get_errno()
    if code in (errno.EEXIST,errno.ENOTEMPTY):return False
    raise OSError(code,os.strerror(code))


def main(base,run,work,lanes,limit):
    upstream=run/'expand/result'; dest=run/'audit-expanded'; stage=work/'stage'; stage.mkdir()
    # Caller and later auditor use byte-identical implementations and unpack the same bound runtime.
    for name in ('wheat_dispatch_audit','wheat_dispatch_scope','census_wheat_q0_fork','pilot_exact_group_windows','pilot_exact_group_inventory'):
        p=name+'.py';require((work/p).read_bytes()==(dest/p).read_bytes(),'audit implementation differs: '+p)
    known=get(run/'result/known.json',KNOWN); queue=get(run/'result/pending.json.gz',known['pending_sha256']); rb=get(run/'result/issues.json.gz',known['issues'])['reference_bases']; tasks=[]
    if (dest/'result').exists():raise ValueError('stock audit owns output already')
    for sealpath in sorted(upstream.glob('planned-*.json.seal'))[:limit]:
        path=sealpath.with_suffix('.gz'); i=int(path.name.split('-')[1].split('.')[0]); chunk=queue[32*i:32*(i+1)]; seal=get(sealpath)
        require(seal['input']==[KNOWN,known['pending_sha256'],i,chunk[0][0],len(chunk)],'foreign input checkpoint')
        tasks.append((path,stage/path.name,seal['sha256']))
    require(tasks,'no committed planner shards');print('EARLY_SHARDS',len(tasks),'windows',sum(len(queue[32*int(p.name[8:12]):32*(int(p.name[8:12])+1)]) for p,_,_ in tasks),flush=True)
    with ProcessPoolExecutor(max_workers=lanes,initializer=init,initargs=(base,rb)) as pool:
        results={}; total=0
        for f in as_completed([pool.submit(check,t) for t in tasks]):
            key,meta=f.result();results[key]=meta;total+=meta['rows']
            if len(results)%100==0:print('EARLY_RAW_VERIFIED',total,flush=True)
    require(len(results)==len(tasks),'incomplete isolated shard set');digest=put(work/'completed-shards.json',results)
    published=handoff(stage,dest/'result')
    print('EARLY_AUDIT',total,'published=',published,put(work/'handoff.json',dict(known_manifest=KNOWN,completed_shards=digest,windows=total,stock_adopted_directory=published,mapper_starts=0)),flush=True)


if __name__=='__main__':main(*(Path(x) for x in sys.argv[1:4]),*(int(x) for x in sys.argv[4:]))
