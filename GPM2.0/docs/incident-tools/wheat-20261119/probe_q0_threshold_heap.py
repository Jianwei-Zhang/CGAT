"""Read-only, byte-bounded whole-inventory sampling of the threshold planner's retained PAF heap.

Linux diagnostic only. No production task, selector, mapper, or Q0 receipt is generated. Byte
strata do not form a representative sample of records that exceed a slab. Never certify a
whole-run memory bound, scientifically reusable evidence IDs, or a cutover on this result.
"""
import argparse
from collections import Counter, defaultdict
import csv
import gc
import hashlib
import json
import multiprocessing as mp
from pathlib import Path
import resource
import socket
import sys
import time

from lgz_core.q0_alignments import parse_paf_line
from lgz_core.q0_paths import PairLink
from lgz_core.q0_sources import SourceKey

SLAB = 256 * 1024
STRATA = 4


def stamp(p):
    s = p.stat()
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def slabs(size, width=SLAB):
    """Disjoint slices, including both ends. Small PAFs are read once, not four times."""
    if size <= width * STRATA:
        return [(0, size)] if size else []
    return [(i * (size-width) // (STRATA-1), width) for i in range(STRATA)]


def lines(data, *, aligned, at_end):
    # Pure LF/CRLF native PAF. Drop an unknown leading/trailing fragment, never parse it.
    if not aligned:
        n = data.find(b'\n')
        if n < 0:
            return
        data = data[n+1:]
    start = 0
    while start < len(data):
        n = data.find(b'\n', start)
        if n < 0:
            if at_end:
                yield data[start:]
            return
        yield data[start:n+1]
        start = n+1


def catalog(root):
    meta = {}; ids = {}; inputs = []; dna = {}
    def path(rel):
        p = root / rel
        if Path(rel).is_absolute() or '..' in Path(rel).parts or not p.resolve(strict=True).is_relative_to(root):
            raise ValueError('unexpected diagnostic input path: '+str(rel))
        return p
    def read(rel):
        p=path(rel); data=p.read_bytes(); meta[rel]=hashlib.sha256(data).hexdigest(); return data.decode()
    def table(rel): return list(csv.DictReader(read(rel).splitlines(),delimiter='\t'))
    def fai(key,rel):
        rows=[line.split('\t') for line in read(rel).splitlines()]; ids[key]={r[0]:int(r[1]) for r in rows}
        if len(ids[key])!=len(rows) or not rows: raise ValueError('invalid FAI')
        dna[key]=sum(ids[key].values())
    refs=table('metadata/reference.tsv'); ds=table('metadata/datasets.tsv'); names={r['dataset_name'] for r in ds}
    if len(refs)!=1 or len(names)!=len(ds) or not ds: raise ValueError('invalid source metadata')
    fai(None,refs[0]['fai_relpath'])
    for r in ds:
        name=r['dataset_name']; fai(name,r['fai_relpath']); inputs.append(('ref',name,None,f'runs/{name}_vs_ref/result.paf'))
    for chrom in ids[None]:
        desc=json.loads(read(f'runs/chr_{chrom}/q0_alignment_inputs.json'))
        if desc['version']!=1 or desc['chromosome']!=chrom: raise ValueError('invalid chromosome metadata')
        for row in desc['alignments']:
            q,t=row['query_dataset'],row['target_dataset']; kind='self' if q==t else 'cross'; rel=row['paf']
            if q not in names or t not in names or kind!=row['kind'] or not rel.startswith(f'runs/chr_{chrom}/'):
                raise ValueError('unexpected alignment metadata')
            inputs.append((kind,q,t,rel))
    if len(set(x[3] for x in inputs))!=len(inputs): raise ValueError('duplicate PAF')
    for *_,r in inputs: path(r)
    return ids,inputs,meta,{'reference':dna.pop(None),'sources':dna}


def private_bytes():
    with Path('/proc/self/smaps_rollup').open() as f:
        return 1024*sum(int(l.split()[1]) for l in f if l.startswith(('Private_Dirty:','Private_Clean:')))


def arm(args):
    kind,root,items,ids,*mode = args
    packed = bool(mode and mode[0])
    if packed:
        from lgz_core.q0_retained_hits import RetainedHit
        keys = {(d,n):SourceKey(d,n) for d,names in ids.items() if d is not None for n in names}
        ref_names = {n:n for n in ids.get(None,{})}
    hits=[]; by_source=defaultdict(list); families=Counter(); rows=[]; gc.collect(); before=private_bytes(); start=time.monotonic()
    for k,q,t,r in items:
        if k!=kind: continue
        p=root/r; sig=stamp(p); st=Counter(); h=hashlib.sha256(); size=sig[2]; ranges=slabs(size)
        with p.open('rb',buffering=0) as f:
            for i,(off,length) in enumerate(ranges):
                f.seek(max(0,off-1)); aligned=not off or f.read(1)==b'\n'; raw=f.read(length)
                if len(raw)!=length: raise ValueError('short slab')
                h.update(raw); st['sample_bytes']+=length
                for n,record in enumerate(lines(raw,aligned=aligned,at_end=off+length==size),1):
                    if not record.strip() or record.startswith(b'#'): continue
                    hit=parse_paf_line(record.decode(),artifact=f'HEAP-SAMPLE/{r}/slab-{i}',line_number=n)
                    if ids[q].get(hit.query_name)!=hit.query_length or ids[t].get(hit.target_name)!=hit.target_length:
                        raise ValueError('sampled lengths differ')
                    if packed:
                        a=keys[q,hit.query_name]; b=None if kind=='ref' else keys[t,hit.target_name]
                        held=RetainedHit.from_validated(hit,a.contig,b.contig if b else ref_names[hit.target_name])
                        if (held.cigar!=hit.cigar or held.tags!=hit.tags or held.evidence_id!=hit.evidence_id
                                or held.record_sha256!=hit.record_sha256):raise ValueError('retained representation changed')
                    else:
                        a=SourceKey(q,hit.query_name); b=None if kind=='ref' else SourceKey(t,hit.target_name);held=hit
                    if kind=='ref': by_source[a].append(held)
                    else: hits.append(PairLink(held,a,b))
                    st.update(records=1,parsed_bytes=len(record),cigar_ops=len(hit.cigar),same_source_records=int(q==t and hit.query_name==hit.target_name))
        if stamp(p)!=sig: raise ValueError('PAF changed during sample')
        families.update(st); rows.append({'paf':r,'size':size,'sample_sha256':h.hexdigest(),'ranges':ranges,**st})
    gc.collect(); used=private_bytes()-before
    return {'kind':kind,'retained_private_delta_bytes':used,'rows_kept':len(hits)+sum(map(len,by_source.values())),
            'process_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,'wall_seconds':time.monotonic()-start,
            'total_paf_bytes':sum(r['size'] for r in rows),'totals':dict(families),'files':rows}


def run(root,output,packed=False):
    root=root.resolve(strict=True); output=output.resolve()
    if output.is_relative_to(root) or output.exists(): raise ValueError('output must be new and external')
    ids,inputs,meta,dna=catalog(root); stamps={r:stamp(root/r) for *_,r in inputs}
    with mp.get_context('spawn').Pool(1,maxtasksperchild=1) as pool:
        results=pool.map(arm,[(k,root,inputs,ids,packed) for k in ('ref','self','cross')],chunksize=1)
    if any(stamp(root/r)!=s for r,s in stamps.items()) or catalog(root)[2]!=meta: raise ValueError('inventory changed')
    doc={'schema':'q0_threshold_retained_heap_bounded_v1','representation': 'packed_with_row_parity' if packed else 'original','host':socket.gethostname(),'python':sys.version,'metadata_sha256':meta,
         'input_dna_bases':dna,'groups':results,'slab_bytes':SLAB,'strata':STRATA,'mapper_started':False,'whole_scan':False,
         'scope':'Only retained base PAF hits/links, not source DNA, catalog, graph, admission, checkpoints, or final evidence registry. Long lines crossing slab edges underrepresented. Partial byte hashes, not content identities of whole inputs.'}
    with output.open('x') as f: json.dump(doc,f,sort_keys=True,indent=2); f.write('\n')
    for r in results: print(r['kind'],r['totals'],r['retained_private_delta_bytes'],r['process_peak_rss_bytes'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('workspace',type=Path); p.add_argument('output',type=Path)
    p.add_argument('--packed',action='store_true'); a=p.parse_args(); run(a.workspace,a.output,a.packed)
