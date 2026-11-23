import gc, hashlib, json, statistics, time
from pathlib import Path
from collections import Counter, defaultdict
from q0_fused_reader_candidate import names, parsed, prefix, cached_geometry
from probe_q0_threshold_heap import catalog, stamp
from lgz_core.q0_alignments import parse_paf_line
from lgz_core.q0_retained_hits import RetainedHit
from lgz_core.q0_sources import Q0EvidenceError

def old(line,r,k,qn,tn):
    hit=parse_paf_line(line,artifact=r,line_number=k)
    try:q,qsize=qn[hit.query_name]; t,tsize=tn[hit.target_name]
    except KeyError as exc:raise Q0EvidenceError('unknown name') from exc
    if (hit.query_length,hit.target_length)!=(qsize,tsize):raise Q0EvidenceError('drifting inventory')
    return RetainedHit.from_validated(hit,q,t)

def run(work,snapshot,out,*,installed=False):
    make_names, decode_row, cache = names, parsed, cached_geometry
    if installed:
        from lgz_core.q0_retained_hits import _retained_line, retained_geometry_cache, retained_names
        make_names, cache = retained_names, retained_geometry_cache()
        def decode_row(line,artifact,n,pre,qn,tn):
            return _retained_line(line,artifact,n,pre,qn,tn,cache)
    raw=snapshot.read_bytes(); assert hashlib.sha256(raw).hexdigest()=='2c8bd6a23eb339f71f16ab0a1e68f74562546532733ae98d3deae3d6609b1f3d'; snap=json.loads(raw); assert Path(snap['source'])==work and not out.exists() and not out.is_relative_to(work)
    ids,items,meta,_=catalog(work); identities={f['path']:f for f in snap['files']}; assert all(identities[k]['sha256']==v for k,v in meta.items()); tables={ds:make_names(v) for ds,v in ids.items()}; assert len(items)==68
    sets=[]; groups=defaultdict(Counter); chunk=512*1024; hh=hashlib.sha256(); declared={p['paf']:(p['kind'],p['query_dataset'],p['target_dataset']) for p in snap['alignments']}
    for kind,q,t,r in items:
        if kind!='ref':assert declared[r]==(kind,q,t)
        p=work/r; before=stamp(p); assert before[2]==identities[r]['size']; lines=[]; n=0
        with p.open('rb') as f:
            for num in range(1,1000000):
                b=f.readline(chunk-n+1)
                if not b or n+len(b)>chunk:break
                hh.update(b);n+=len(b)
                if b.strip() and not b.startswith(b'#'):lines.append((num,b.decode('utf-8')))
        assert stamp(p)==before; pre=prefix(r); sets.append((kind,r,pre,tables[q],tables[t],lines)); groups[kind]['rows']+=len(lines);groups[kind]['bytes']+=n;groups[kind]['files']+=1
    # Complete dataclass comparison outside timed paths: includes coordinates, order/tags/cigar encoding, both identities.
    for kind,r,pre,qn,tn,lines in sets:
        for k,line in lines:
            a=old(line,r,k,qn,tn); b=decode_row(line,r,k,pre,qn,tn)
            if a!=b:raise ValueError('diagnostic disagrees at '+r+':'+str(k))
    timings=[]
    for fast in (False,True,True,False):
        cache.cache_clear();gc.collect(); spent=Counter(); before=time.perf_counter()
        for kind,r,pre,qn,tn,lines in sets:
            tick=time.perf_counter()
            if fast:
                for k,line in lines:last=decode_row(line,r,k,pre,qn,tn)
            else:
                for k,line in lines:last=old(line,r,k,qn,tn)
            spent[kind]+=time.perf_counter()-tick
        timings.append({'candidate':fast,'seconds':time.perf_counter()-before,'by_kind_seconds':spent,'small_cigar_cache':cache.cache_info()._asdict()}); print('ARM',timings[-1],flush=True)
    result={'schema':'wheat_threshold_parser_bounded_ab_v1','tested_reader':'production_threshold_draft' if installed else 'experimental','samples':'first complete records in at most 512 KiB per natural input, original artifact and line number; not random; I/O and selector not timed','files':len(sets),'snapshot_sha256':hashlib.sha256(raw).hexdigest(),'sample_payload_sha256':hh.hexdigest(),'groups':groups,'timings':timings,'exact_retained_rows_compared':sum(v['rows'] for v in groups.values()),'seconds_ratio_old_over_candidate':statistics.median(v['seconds'] for v in timings if not v['candidate'])/statistics.median(v['seconds'] for v in timings if v['candidate']),'mapper_calls':0,'production_modified':False}
    with out.open('x') as f:json.dump(result,f,sort_keys=True,indent=2);f.write('\n')
    print('RESULT',json.dumps(result))
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--installed',action='store_true')
    for name in ('work','snapshot','output'):p.add_argument(name,type=Path)
    a=p.parse_args();run(a.work.resolve(),a.snapshot.resolve(),a.output.resolve(),installed=a.installed)
