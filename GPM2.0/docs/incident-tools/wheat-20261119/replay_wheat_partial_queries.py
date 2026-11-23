"""Reconstruct the complete *query* side before applying the threshold; never plan away a target."""
from bisect import bisect_right
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

from bound_regional_scope_from_native_receipts import EXPECTED
from census_wheat_q0_fork import bind, bounded, GEOM, HEAD, LOOK, MAGIC, SNAP, require, write
from fork_wheat_q0 import copy_bound, member
from lgz_core.common import stable_id
from lgz_core.q0_alignments import read_paf_observations
from lgz_core.q0_catalog import ObservedSourcePairs
from lgz_core.q0_query_windows import WindowPolicy, plan_query_windows
from lgz_core.q0_sources import Interval, SourceKey, merged_intervals, subtract_intervals

HIST='03b79fc96cc80ccfa8a6560be2141efd4126afd73d21ad1021c944508a04d171'
SCANS='f9119227f6882704f23aea1b28d76ab6b2b0fa536bebc7c40d4682e531f063cd'
FIRST='q0-map-8024dde83cbf20e7ffa6d8ee'
AXES='7c93bb87545a40a561ac09a88260cc043a297f1236a6d5875c837d4d17542c31'
POLICY=WindowPolicy(trigger_query_bases=1,trigger_longest_bases=1,core_bases=100000,context_bases=10000,minimum_uncovered_bases=100)


def residual(holes, coverage):
    """Only subtract actual covered bases; a discarded short residual cannot grow on later subtraction."""
    coverage=tuple(coverage); ends=[v.end for v in coverage]; result=[]
    for hole in holes:
        i=bisect_right(ends,hole.start); j=i
        while j<len(coverage) and coverage[j].start<hole.end: j+=1
        result.extend(v for v in subtract_intervals(hole,coverage[i:j]) if v.length>=POLICY.minimum_uncovered_bases)
    return tuple(result)


def intersect_census(stream, planned, digest):
    h=hashlib.sha256(); magic=stream.read(len(MAGIC)); require(magic==MAGIC,'wrong frozen census'); h.update(magic)
    seen=set(); represented=set(); outside=set(); counts=Counter()
    while head:=stream.read(HEAD.size):
        require(len(head)==HEAD.size,'truncated context'); ctx,qid,n=HEAD.unpack(head)
        require(ctx not in seen and 1<n<=2_000_000,'bad or duplicate context'); seen.add(ctx)
        data=stream.read(GEOM.size*n); require(len(data)==GEOM.size*n,'truncated geometry'); h.update(head); h.update(data)
        geom=GEOM.unpack_from(data)
        if qid in planned:
            require(planned[qid]==geom,'same query ID has different geometry'); represented.add(qid); counts['matching_contexts']+=1
        else: outside.add(qid); counts['other_contexts']+=1
    require(h.hexdigest()==digest,'wrong census bytes'); return {**counts,'contexts':len(seen),'planned_queries_with_observed_target_sets':len(represented),'planned_queries_without_observed_target_sets':len(planned)-len(represented),'distinct_other_queries':len(outside)}


def replay(base, out):
    fork=base/'q0-latest-fork-20261123-1435/control'; lookup=base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json'
    snap,root,index,order,lengths=bind(fork/'snapshot.json',lookup); require(not out.exists() and not out.is_relative_to(root),'unsafe output'); out.mkdir(mode=0o700)
    old=base/'q0-existing-cross-coverage-20261121-v2'; scans=json.loads(bounded(old/'summary.json',1<<20,SCANS)); pinned={r['path']:r['sha256'] for r in snap['files']}
    native_dir='grt/evidence/q0_prepare/tasks/'; first_paf=native_dir+FIRST+'/result.paf'
    prior={r['path']:r['sha256'] for r in scans['scans']}; cross={r['paf'] for r in snap['alignments'] if r['kind']=='cross'}
    require(len(prior)==len(scans['scans'])==23 and set(prior)==cross|{first_paf} and all(prior[n]==pinned[n] for n in cross),'wrong historical input scope')
    strict=base/'q0-partial-coverage-diagnostic-20261121-1426/summary.json'; refs=json.loads(bounded(strict,1<<20,scans['input_metadata_sha256'][str(strict)]))['datasets']; require(len(refs)==2 and {f"runs/{d['dataset']}_vs_ref/result.paf":d['reference_paf_sha256'] for d in refs}=={n:h for n,h in pinned.items() if re.fullmatch('runs/[^/]+_vs_ref/result.paf',n)},'reference screen differs')
    holes={}; key_to_part={order[r[0]]:k for k,r in index.items()}; sizes={k:r[1] for k,r in index.items()}
    for row in json.loads(bounded(old/'residual-coverage.json',16<<20,HIST)):
        key=SourceKey(row['dataset'],row['contig']); part=key_to_part[key]; values=tuple(Interval(*v) for v in row['uncovered']); require(part not in holes and values and values==merged_intervals(values) and all(v.length>=100 for v in values) and values[-1].end<=row['length']==sizes[part],'invalid historical residual'); holes[part]=values
    old_count=len(plan_query_windows(sizes,holes,policy=POLICY)); require(old_count==61087,'wrong starting geometry')
    obs=ObservedSourcePairs(lengths); inputs={}
    with TemporaryDirectory(dir='/tmp') as tmp:
        for key,h in sorted(EXPECTED.items()):
            rel=native_dir+key+'/'; doc=json.loads(bounded(member(root,rel+'success.json'),32<<20,h)); spec=doc['spec']; members=set(spec['query_ids']+spec['target_ids']); require(doc['status']=='success' and spec['preset']=='asm10' and stable_id('q0-map',spec)==key and spec['members']==[[p,index[p][2]] for p in sorted(members)],'native scope mismatch'); rows=[r for r in doc['outputs'] if r['path']==rel+'result.paf']; require(len(rows)==1,'missing native PAF identity'); row=rows[0]
            inputs[key]={'receipt_sha256':h,'paf_sha256':row['sha256'],'alignment_flags':spec['alignment_flags']}
            if key==FIRST:
                require(prior[first_paf]==row['sha256'],'historical native PAF differs'); continue
            p=Path(tmp)/(key+'.paf'); copy_bound(member(root,row['path']),p,row); n=0
            for hit in read_paf_observations(p,artifact=row['path'],query_lengths={k:sizes[k] for k in spec['query_ids']},target_lengths={k:sizes[k] for k in spec['target_ids']}):
                obs.observe_alignment(hit,order[index[hit.query_name][0]],order[index[hit.target_name][0]]); n+=1
            inputs[key]['rows_replayed']=n
    added={k:tuple(v) for k,v in obs.cross_coverage.items()}; updated={p:residual(v,added[order[index[p][0]]]) if order[index[p][0]] in added else v for p,v in holes.items()}; windows=plan_query_windows(sizes,updated,policy=POLICY); q={}; geometry=hashlib.sha256()
    with gzip.open(out/'queries.tsv.gz','xt',encoding='ascii') as f:
        for w in windows:
            ident=bytes.fromhex(w.window_id.rsplit('-',1)[1]); rank=index[w.segment_id][0]; require(ident not in q,'duplicate query geometry'); q[ident]=(rank,w.start,w.end); line=f'{w.window_id}\t{rank}\t{w.start}\t{w.end}\n'; f.write(line); geometry.update(line.encode())
    census=base/'q0-fork-window-census-20261123-1505/census'; receipt=json.loads(bounded(census/'axes-receipt.json',1<<20)); require(receipt['snapshot']==SNAP and receipt['lookup']==LOOK and receipt['uncompressed_sha256']==AXES,'wrong axes identity')
    with gzip.open(census/'axes.bin.gz','rb') as stream: matches=intersect_census(stream,q,AXES)
    require(matches['contexts']==receipt['count'],'census count differs'); log=base/'q0-child-loader-cutover-20261122-180258/resume_43017096.out'; run=snap['source_run']; seeds=set(); planned=set()
    with log.open() as f:
        for line in f:
            if ('[run='+run+']') not in line or '[CHILD] [q0_evidence]' not in line: continue
            m=re.search(r'weak seed: completed=(q0-map-[a-f0-9]{24}) ',line); p=re.search(r'regional progress: completed=\d+ planned=(\d+) ',line)
            if m:seeds.add(m[1])
            if p:planned.add(int(p[1]))
    require(seeds==EXPECTED.keys()-{FIRST} and len(planned)==1,'live generation or plan changed')
    report={'schema':'reconstructed_wheat_partial_query_geometry_v1','snapshot':SNAP,'source_run':run,'archived_residual_sha256':HIST,'archived_scan_receipt_sha256':SCANS,'archived_query_count':old_count,'native_matrices':inputs,'replayed_query_count':len(q),'logged_plan_count':next(iter(planned)),'count_matches':planned=={len(q)},'queries_uncompressed_sha256':geometry.hexdigest(),'membership_in_frozen_census':matches,'census_axes_sha256':AXES,'limits':'Query-side replay, not a live dump of every context. No target inventory for unmaterialized queries, no inference that query-only misses are omitted, no mapper launches or final Q0.'}; write(out/'replay.json',report); print(json.dumps(report),flush=True)

if __name__=='__main__': replay(*(Path(x).resolve() for x in sys.argv[1:]))
