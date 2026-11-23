"""Measure first threshold demand on frozen, previously materialized wheat window contexts.

An exact census of this inventory, not an estimate for unmaterialized windows, final Q0 or mapper time.
No DNA/PAF, mapping, live checkpoint edits, or new window planning.
"""
import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re
from struct import Struct

from lgz_core.common import stable_id
from lgz_core.q0_sources import SourceKey
from lgz_core.q0_threshold_acceptance import decode
from lgz_core.q0_preparation import supplement_policy

SNAP = '2c8bd6a23eb339f71f16ab0a1e68f74562546532733ae98d3deae3d6609b1f3d'
LOOK = '2e09b9ff5c849f4d4a83c177c46a4586c29d84b1407666dab8087615ad8c1c89'
GEOM = Struct('>III')  # lookup rank, original-source start and exclusive end (whole-source parts only)
HEAD = Struct('>12s12sI')  # context and query IDs (96-bit stable IDs), number of windows including query
MAGIC = b'CGAT-Q0-AXES-1\n'


def require(ok, why):
    if not ok:
        raise ValueError(why)


def bounded(path, limit, digest=None):
    require(path.resolve(strict=True) == path, 'not an original regular-file path')
    with path.open('rb') as f:
        data = f.read(limit + 1)
    require(len(data) <= limit and (digest is None or sha256(data).hexdigest() == digest), 'oversize or unbound input: '+str(path))
    return data


def write(path, doc):
    with path.open('x') as f:
        json.dump(doc, f, sort_keys=True, indent=2); f.write('\n')


def bind(snapshot, lookup):
    s = json.loads(bounded(snapshot, 256*1024, SNAP)); source = Path(s['source']); rows = json.loads(bounded(lookup, 32<<20, LOOK))
    index = {}; lengths = {}; ordered = []
    for rank, (part, row) in enumerate(sorted(rows.items())):
        key = SourceKey(row['dataset'], row['contig']); n = row['length']; digest = row['sequence_sha256']
        require(type(n) is int and 0 < n < 2**32 and part == stable_id('q0-source-part', [key.dataset,key.contig,0,n,digest]) and key not in lengths, 'lookup not unique whole-source coordinates')
        lengths[key] = n; ordered.append(key); index[part] = (rank, n, digest)
    # The frozen producer's two assembly FAI files must agree with the lookup, not just with one another.
    inv = {}
    for r in s['files']:
        match = re.fullmatch(r'data/datasets/([^/]+)\.fa\.fai', r['path'])
        if match:
            raw = bounded(source/r['path'], 16<<20, r['sha256']); require(len(raw)==r['size'], 'FAI size')
            for line in raw.decode().splitlines():
                name, length, *_ = line.split('\t'); key = SourceKey(match[1], name)
                require(key not in inv, 'duplicate original input source'); inv[key] = int(length)
    require(inv == lengths, 'lookup differs from original fork inputs')
    return s, source, index, ordered, lengths


def pack_context(name, spec, index):
    require(spec['schema']=='lgz_q0_regional_context_v1' and spec['fasta_format']=='wrap80_v1' and spec['preset']=='asm10' and stable_id('q0-regional-context',spec)==name, 'context changed or foreign policy')
    q = spec['query']; targets = spec['targets']; require(targets, 'empty target context'); body = bytearray(); seen = set()
    for w in (q,*targets):
        part = w['segment_id']; rank,n,_ = index[part]; a,b = w['start'],w['end']; require(n==w['segment_length'] and type(a) is int and type(b) is int and 0<=a<b<=n, 'source bounds changed')
        seen.add(part); body.extend(GEOM.pack(rank,a,b))
    require(spec['members']==[[p,index[p][2]] for p in sorted(seen)], 'context/source DNA binding differs')
    geom = {k:q[k] for k in ('segment_id','segment_length','start','end')}; qid = stable_id('q0-query-window', geom); require(qid==q['window_id'], 'query ID/geometry mismatch')
    return HEAD.pack(bytes.fromhex(name.rsplit('-',1)[1]),bytes.fromhex(qid.rsplit('-',1)[1]),len(body)//GEOM.size) + body


def build(snapshot, lookup, out):
    s,source,index,_,_ = bind(snapshot,lookup); reg = source/'grt/evidence/q0_prepare/regional'
    require(not out.is_relative_to(source) and reg.resolve(strict=True)==reg, 'unsafe census workspace'); out.mkdir(mode=0o700)
    names=sorted(p.name for p in reg.iterdir() if re.fullmatch(r'q0-regional-context-[0-9a-f]{24}',p.name)); require(names, 'no materialized contexts')
    write(out/'listed.json',names); total=size=missing=0; packed=sha256(); records=sha256(); axes=out/'axes.bin.gz'
    with gzip.open(axes,'xb',compresslevel=1) as archive:
        archive.write(MAGIC); packed.update(MAGIC)
        for name in names:
            path = reg/name/'context.json'
            if not path.exists(): missing+=1; continue  # listed while a parent may still be publishing
            raw = bounded(path,64<<20); size+=len(raw); context=json.loads(raw); block=pack_context(name,context['spec'],index)
            records.update(name.encode()+b'\0'+sha256(raw).digest()); archive.write(block); packed.update(block); total+=1
            if total%2000==0: print('INDEXED',total,'/',len(names),flush=True)
    require(total>0,'no published contexts'); note={'schema':'existing_wheat_window_axes_v1','snapshot':SNAP,'lookup':LOOK,'source':str(source),'initial_names':len(names),'listed_sha256':sha256((out/'listed.json').read_bytes()).hexdigest(),'count':total,'absent_at_read':missing,'context_metadata_bytes':size,'input_records_sha256':records.hexdigest(),'uncompressed_sha256':packed.hexdigest(),'packed_gzip_bytes':axes.stat().st_size}
    write(out/'axes-receipt.json',note); print('READY',json.dumps(note),flush=True)


def measure(stream, shoulders):
    """Return exact two-axis categories. None means full fallback, not an empty request."""
    h=sha256(); magic=stream.read(len(MAGIC)); require(magic==MAGIC,'wrong axes format'); h.update(magic); hist=Counter(); contexts=set(); queries={}
    while head:=stream.read(HEAD.size):
        require(len(head)==HEAD.size,'truncated context'); ctx,qid,n=HEAD.unpack(head); require(ctx not in contexts and 1<n<=2_000_000,'duplicate context or invalid axis count'); contexts.add(ctx)
        data=stream.read(n*GEOM.size); require(len(data)==n*GEOM.size,'truncated geometry'); h.update(head); h.update(data); q=t=False
        for i,(rank,start,end) in enumerate(GEOM.iter_unpack(data)):
            if shoulders is not None and any(start<b and a<end for a,b in shoulders.get(rank,())):
                if i==0: q=True
                else: t=True; break
        tag='full_fallback' if shoulders is None else ('both' if q and t else 'query_only' if q else 'target_only' if t else 'omitted'); hist[tag]+=1; queries[qid]=queries.get(qid,False) or tag!='omitted'
    return {'contexts':len(contexts),'retained_contexts':len(contexts)-hist['omitted'],'omitted_contexts':hist['omitted'],'axes_breakdown':dict(hist),'distinct_query_windows':len(queries),'queries_omitted_across_all_observed_target_sets':sum(not keep for keep in queries.values())},h.hexdigest()


def compare(snapshot,lookup,out):
    s,src,_,ordered,lengths=bind(snapshot,lookup); raw=bounded(snapshot.parent/'global-first-request.json',64<<20); request=json.loads(raw); receipt=json.loads(bounded(out/'axes-receipt.json',1<<20))
    require(receipt['schema']=='existing_wheat_window_axes_v1' and receipt['snapshot']==SNAP and receipt['lookup']==LOOK and receipt['source']==str(src),'wrong inventory')
    require(request['schema']=='wheat_threshold_global_first_request_v1' and request['revision']==s['revision'] and request['snapshot_sha256']==SNAP and request['threshold_contract']==supplement_policy('positive_threshold')['decision_frontier'] and request['published_q0'] is False and request['mapper_calls']==0 and type(request['has_path']) is bool,'wrong first demand or runtime contract')
    frontier=decode(request['request'],lengths); shoulders=None if frontier is None else {i:[(v.start,v.end) for v in frontier[key]] for i,key in enumerate(ordered) if key in frontier}
    with gzip.open(out/'axes.bin.gz','rb') as stream: counts,fingerprint=measure(stream,shoulders)
    require(fingerprint==receipt['uncompressed_sha256'] and counts['contexts']==receipt['count'],'incorrect packed inventory')
    result={'schema':'existing_wheat_context_first_request_count_v1','snapshot':SNAP,'request_sha256':sha256(raw).hexdigest(),'inventory_sha256':fingerprint,'has_path':request['has_path'],'mode':('full_fallback' if frontier is None else 'localized' if frontier else 'base_only' if request['has_path'] else 'no_supported_backbone'),'counts':counts,'limits':'Only previously materialized complete contexts, not the remaining or final number of whole-wheat partial/candidate/repair tasks or mapper launches. A no-backbone result is not a successful zero-mapping Q0.'}; write(out/'first-request-count.json',result); print(json.dumps(result),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('mode',choices=['build','compare']); parser.add_argument('snapshot',type=Path); parser.add_argument('lookup',type=Path); parser.add_argument('output',type=Path); args=parser.parse_args(); (build if args.mode=='build' else compare)(args.snapshot.absolute(),args.lookup.absolute(),args.output.absolute())
