"""Read-only raw/chain receipt audit, independent of production dispatch. Never call minimap2 to map."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from hashlib import sha256
from pathlib import Path
import json
import sys
from time import monotonic
from census_wheat_q0_fork import require
from pilot_exact_group_inventory import audit, m, TOOL
from wheat_dispatch_scope import get, inputs, put

KNOWN='f2a2c95745193581ec0144a90ba77c3fd82153c7856baba59bc65c324f673b54'


def init(base,ref_bases):
    global ROOT, LOOKUP, IDENT, REF
    _,ROOT,LOOKUP,_,_=inputs(base); IDENT=m._ops().executable_identity('minimap2'); REF=ref_bases
    require(IDENT['sha256']==TOOL,'wrong regional tool')


def probe(row):
    q,rank,start,end,ctx,stamp,left,right,fallback=row
    if fallback:return {'status':'individual_native_fallback'}
    if not(left or right):return {'status':'geometrically_omitted'}
    rel=ROOT/'grt/evidence/q0_prepare/regional'/ctx
    if not (rel/'context.json').is_file():
        return {'status':'incomplete_context_review' if rel.exists() else 'no_stored_context'}
    try:
        result=audit(ROOT,LOOKUP,IDENT,REF,'query' if left else 'target_only',ctx,stamp,locators=True,derive_missing_decision=True)
        if result['status']=='missing_chain' and not any(rel.glob('q0-regional-raw-*/success.json')):
            result['status']='missing_chain_and_raw'
        return result
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return dict(status='cache_needs_review',error=f'{type(exc).__name__}: {exc}')


def check(job):
    src,dst,stamp=job; rows=get(src,stamp); seal=dst.with_suffix('.seal'); start=monotonic()
    if seal.is_file():
        prev=get(seal); require(prev['input']==stamp,'input changed'); results=get(dst,prev['sha256']); require(len(results)==len(rows),'incomplete resume'); return dst.name,prev
    results=[[r[0],probe(r)] for r in rows]; counts=Counter(v['status'] for q,v in results)
    digest=put(dst,results); meta=dict(input=stamp,sha256=digest,rows=len(rows),statuses=counts,seconds=round(monotonic()-start,2));put(seal,meta)
    return dst.name,meta


def main(base,run,mode,workers):
    known=get(run/'result/known.json',KNOWN); ref=get(run/'result/issues.json.gz',known['issues'])['reference_bases'];require(mode in ('known','expanded'),'invalid mode')
    if mode=='known':source=run/'result'; manifest=known['shards']
    else:
        source=run/'expand/result'; expanded=get(source/'complete.json');require(expanded['parent']==KNOWN and expanded['windows']==known['pending_count'],'unbound expanded inventory');manifest=expanded['shards']
    out=run/('audit-'+mode)/'result';out.mkdir(exist_ok=True); stored={}; counts=Counter(); done=0
    with ProcessPoolExecutor(max_workers=workers,initializer=init,initargs=(base,ref)) as pool:
        futures=[pool.submit(check,(source/key,out/key,stamp)) for key,stamp in manifest.items()]
        for future in as_completed(futures):
            name,meta=future.result();counts.update(meta['statuses']);stored[name]=meta['sha256'];done+=meta['rows']
            if len(stored)%5==0 or len(stored)==len(futures):print('RAW_AUDIT',mode,done,dict(counts),flush=True)
    print('RAW_AUDIT_READY',put(out/'complete.json',dict(phase=mode,scope=KNOWN,shards=stored,windows=done,counts=counts,mapping_processes_launched=0)),flush=True)


if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3],int(sys.argv[4]))
