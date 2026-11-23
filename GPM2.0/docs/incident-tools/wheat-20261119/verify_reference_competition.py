"""Compare real masks and the entire first decision. No mapper, no Q0 publication, no live modifications."""
from collections import Counter, defaultdict
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import monotonic
from unittest.mock import patch

from compare_fused_draft_panels import arm
from fork_wheat_q0 import copy_bound, member
from lgz_core import q0_admission as new, q0_admission_old as old, q0_reference_competition as sweep
from lgz_core.q0_alignments import parse_paf_line
from lgz_core.q0_sources import merged_intervals, subtract_intervals
from probe_q0_threshold_heap import catalog

SNAP='2c8bd6a23eb339f71f16ab0a1e68f74562546532733ae98d3deae3d6609b1f3d'


def encode(x): return json.dumps(x,sort_keys=True,separators=(',',':')).encode()


def check(ok, why):
    if not ok:raise ValueError(why)


def panel(path,pin):
    results=[]; reference=new._reference_groups
    for fn in (old._reference_groups,reference):
        screen=sha256();elapsed=0;parts=anchors=ambiguous=0
        def capture(data,part,policy):
            nonlocal elapsed,parts,anchors,ambiguous
            start=monotonic(); g,high,mask=fn(data,part,policy);elapsed+=monotonic()-start;parts+=1
            record=[part.segment_id,[(k,[(a.source.start,a.source.end,a.reference.start,a.reference.end,a.evidence_id) for a in vs]) for k,vs in sorted(g.items())],sorted(high),[(i.start,i.end) for i in mask]];screen.update(encode(record)+b'\n');anchors+=sum(map(len,g.values()));ambiguous+=len(mask);return g,high,mask
        with patch.object(new,'_reference_groups',capture): r=arm(path,pin)
        d={'has_path':r['has_path'],'request':r['request']};results.append({'has_path':r['has_path'],'request_sha256':sha256(encode(d)).hexdigest(),'part_screens_sha256':screen.hexdigest(),'parts':parts,'anchors':anchors,'ambiguous_intervals':ambiguous,'reference_screen_seconds':elapsed,'draft_seconds':r['seconds']})
    for k in ('has_path','request_sha256','part_screens_sha256','parts','anchors','ambiguous_intervals'):check(results[0][k]==results[1][k],f'{path.name}: {k} differs')
    check(results[0]['parts']>0,'no reference screens');return {'panel':path.name,'pin':pin,'arms':results}


def old_masks(rows,margin):
    # Original loop from _reference_groups, including the projection on each overlap.
    index=old._ReferenceBlockCandidates(rows);unique=[];ambig=[]
    for b in rows:
        conflicts=[]
        for other,ov in index.intersecting(b.query):
            if other.identity+margin < b.identity:continue
            if b.chromosome!=other.chromosome or b.strand!=other.strand or old._project(b.query,b.target,b.strand,ov)!=old._project(other.query,other.target,other.strand,ov):conflicts.append(ov)
        ambig.extend(conflicts);unique.append(subtract_intervals(b.query,conflicts))
    return unique,merged_intervals(ambig)


def natural(base):
    snap=base/'q0-latest-fork-20261123-1435/control/snapshot.json'; raw=snap.read_bytes();check(sha256(raw).hexdigest()==SNAP,'wrong producer'); manifest=json.loads(raw); root=Path(manifest['source']);files={r['path']:r for r in manifest['files']}; lengths,_,meta,_=catalog(root);check(all(files[k]['sha256']==v for k,v in meta.items()),'wrong FAI or descriptors'); refs=sorted(k for k in files if k.startswith('runs/') and k.endswith('_vs_ref/result.paf'));check(len(refs)==2,'reference inventory'); groups=defaultdict(list); origins=Counter(); h=sha256()
    with TemporaryDirectory(dir='/tmp',prefix='ref-mask-') as tmp:
        for rel in refs:
            p=Path(tmp)/rel;copy_bound(member(root,rel),p,files[rel],96<<20);used=0;dataset=rel.split('/')[1][:-len('_vs_ref')]
            with p.open('rb') as f:
                for n,raw in enumerate(f,1):
                    if used+len(raw)>1024**2:break
                    used+=len(raw);h.update(raw)
                    if not raw.strip() or raw.startswith(b'#'):continue
                    hit=parse_paf_line(raw.decode(),artifact=rel,line_number=n);check(lengths[dataset].get(hit.query_name)==hit.query_length and lengths[None].get(hit.target_name)==hit.target_length,'source binding changed');score=hit.matches/hit.block_length
                    if score<.9:continue
                    for pair in hit.aligned_blocks():
                        if pair.operation!='X':groups[dataset,hit.query_name].append(old._RefBlock(pair.query,pair.target,hit.target_name,hit.strand,hit.evidence_id,score,hit.mapping_quality))
            origins[rel]=used
    # Equal-size contiguous *coordinate-sorted* slices preserve natural overlaps and sparse rows.
    # Select by input geometry only, not by verdict/timing. Limit the cost of the old comparator.
    chunks=[]
    for key,rows in sorted(groups.items()):
        ordered=sorted(rows,key=lambda b:b.query.start)
        for off in range(0,len(ordered),512):
            v=ordered[off:off+512]
            if len(v)<16:continue
            ix=sweep._ReferenceBlockCandidates(v);visits=sum(hi-lo for lo,hi in (ix.bounds(b.query) for b in v));chunks.append((visits/len(v),key,off,v))
    chunks.sort(key=lambda x:x[:3]);check(len(chunks)>=8,'not enough real blocks');ch=[chunks[i] for i in sorted(set([*range(min(4,len(chunks))),*(i*(len(chunks)-1)//7 for i in range(8)),*range(max(0,len(chunks)-8),len(chunks))]))];arms=[];expected=None
    for fn in (old_masks,sweep.reference_masks,sweep.reference_masks,old_masks):
        start=monotonic();result=[fn(v,.02) for _,_,_,v in ch];seconds=monotonic()-start
        if expected is None:expected=result
        else:check(result==expected,'per-block unique or union differs')
        arms.append({'shared_mask':fn is sweep.reference_masks,'seconds':seconds})
    stats=[{'source':key,'offset':off,'blocks':len(v),'candidate_visits_per_block':density} for density,key,off,v in ch];digest=sha256()
    for masks,union in expected:
        digest.update(encode([[[(i.start,i.end) for i in intervals] for intervals in masks],[(i.start,i.end) for i in union]]))
    return {'snapshot':SNAP,'reference_prefix_bytes':origins,'prefixes_sha256':h.hexdigest(),'verified_paf_sha256':{k:files[k]['sha256'] for k in refs},'sample_groups':stats,'exact_masks_sha256':digest.hexdigest(),'arms':arms,'limits':'First complete lines in <=1MiB of each reference PAF, deliberately including low and high overlap slices, not a random sample, complete Q0 or an ETA.'}

if __name__=='__main__':
    mode,base,out=sys.argv[1:4];base=Path(base).resolve();out=Path(out).absolute();check(not out.exists() and not out.is_relative_to(base/'gpm_server'),'unsafe output');report=natural(base) if mode=='natural' else panel((base/sys.argv[4]/'panels'/sys.argv[5]).resolve(),sys.argv[6]);
    with out.open('x') as f:json.dump(report,f,sort_keys=True,indent=2);f.write('\n')
    print(mode,out.name,report['arms'],flush=True)
