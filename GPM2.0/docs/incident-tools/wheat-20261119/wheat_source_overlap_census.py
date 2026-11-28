"""Stream the frozen admission + completed path prefix, without loading DNA or running a mapper."""
import argparse
from collections import defaultdict
from hashlib import sha256
import itertools
import json
from pathlib import Path
from time import monotonic


def need(ok, msg):
    if not ok: raise ValueError(msg)


def records(path, binding, group, previous):
    with path.open('rb') as f:
        header=f.readline(); digest=sha256(header); n=0
        need(json.loads(header)==['wheat_first_request_checkpoint_v1',binding,path.name,group,previous[0]],'wrong header or prefix')
        for line in f:
            obj=json.loads(line)
            if isinstance(obj,list):
                need(obj==['end',n,digest.hexdigest()] and not f.read(1),'wrong checkpoint trailer')
                previous[0]=obj[-1];return
            digest.update(line);n+=1;yield obj
        raise ValueError('truncated checkpoint')


def census(folder, evidence, prefix, kit, project=False):
    from lgz_core.q0_sources import Interval
    from lgz_core.q0_collinear import exclusive_carriers
    began=monotonic();rows=defaultdict(list); selected={}; chain=[''];binding=None
    with (folder/'admission.jsonl').open('rb') as f: binding=json.loads(f.readline())[1]
    need(binding[-3:]==[kit,evidence,32] and binding[0]=='whole-wheat-local-supplement-v1','wrong run')
    for obj in records(folder/'admission.jsonl',binding,None,chain):
        pid,sid,source,iv,strand,chrom,_,_,_,blocks,_,kind=obj['Placement']
        anchors=[b['ReferenceAnchor'][0]['Interval'] for b in blocks];hull=None
        if anchors:hull=[min(b[0] for b in anchors),max(b[1] for b in anchors)]
        rows[tuple(source['SourceKey'])].append(dict(id=pid,part=sid,interval=iv['Interval'],chr=chrom,strand=strand,kind=kind,refhull=hull))
    for i,group in enumerate(prefix,1):
        for obj in records(folder/('group-%03d.jsonl'%i),binding,group,chain):
            path=obj['RequestPathResult'][0]
            if path:
                chrom,_,_,slices,_=path['_ScoredPath'];need(chrom==group,'wrong group')
                for s in slices:pid,_,iv,_=s['Slice'];selected[pid]=iv['Interval']
    def cross(a,b):return a['chr']!=b['chr'] and max(a['interval'][0],b['interval'][0])<min(a['interval'][1],b['interval'][1])
    pairs=[]; proposed=0;changed=set(); repaired_rows=0
    for source,items in rows.items():
        by_part=defaultdict(list)
        for p in items:by_part[p['part']].append(p)
        for a,b in itertools.combinations(items,2):
            if not cross(a,b):continue
            def side(p):return dict(**p,selected=selected.get(p['id']),group_saved=p['chr'] in prefix,
                reason='continuous_collinear_chain' if p['kind']=='continuous_reference' else None)
            pairs.append(dict(source=source,left=side(a),right=side(b),overlap=[max(a['interval'][0],b['interval'][0]),min(a['interval'][1],b['interval'][1])]))
        if project:
            fixed=[]
            for group in by_part.values():
                carriers=[p for p in group if p['kind']=='continuous_reference'];fixed.extend(p for p in group if p not in carriers)
                bounds=exclusive_carriers([(p['chr'],Interval(*p['interval']),Interval(*p['refhull'])) for p in carriers])
                for p,bound in zip(carriers,bounds):
                    if bound is None or p['interval']!=[bound.start,bound.end]:changed.add(p['chr'])
                    if bound is not None:fixed.append(dict(p,interval=[bound.start,bound.end]))
            proposed+=sum(cross(a,b) for a,b in itertools.combinations(fixed,2));repaired_rows+=len(fixed)
    return dict(placement_count=sum(map(len,rows.values())),groups_in_admission=sorted({p['chr'] for ps in rows.values() for p in ps}),
                checked_path_prefix=prefix,source_overlap_pairs=pairs,reason_note='inferred from producer branch; first-request checkpoint has no reason field',
                projection=None if not project else dict(scope='only fixed carrier boundaries on frozen placements; not a fresh admission',
                overlaps=proposed,rows=repaired_rows,changed_chromosomes=sorted(changed)),elapsed_s=round(monotonic()-began,1))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('folder',type=Path);ap.add_argument('evidence');ap.add_argument('kit');ap.add_argument('prefix',nargs='+');ap.add_argument('--project',action='store_true');opt=ap.parse_args()
    print(json.dumps(census(opt.folder,opt.evidence,opt.prefix,opt.kit,opt.project),indent=2))
