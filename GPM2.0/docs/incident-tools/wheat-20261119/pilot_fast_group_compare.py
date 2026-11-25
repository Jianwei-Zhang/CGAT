"""Read-only independent geometry comparison. Reference spans are support proxies, not truth."""
from collections import defaultdict
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys

from lgz_core.q0_alignments import parse_paf_line
from lgz_core.q0_sources import Interval, merged_intervals
from pilot_fast_group_run import GROUP, need, sealed, write


def intersect_bp(xs,ys):
    i=j=n=0
    while i<len(xs) and j<len(ys):
        a,b=xs[i],ys[j];n+=max(0,min(a.end,b.end)-max(a.start,b.start));i+=a.end<=b.end;j+=b.end<=a.end
    return n


def verify_arm(root,arm,candidate="BC"):
    folder=root/('A' if arm=='A' else candidate); result=folder/'result'
    pins={name:h for h,name in (line.split() for line in (folder/'results.sha256').read_text().splitlines())}
    metrics=sealed(result/(arm+'.json'),pins['result/'+arm+'.json']);layout=sealed(result/(arm+'.layout.json'),pins['result/'+arm+'.layout.json'])
    raw_hash=sha256()
    with (result/(arm+'.fa.gz')).open('rb') as src:
        for block in iter(lambda:src.read(1<<20),b''):raw_hash.update(block)
    need(raw_hash.hexdigest()==pins['result/'+arm+'.fa.gz'],'FASTA archive digest')
    hashes=[]; total=ns=0; h=None
    with gzip.open(result/(arm+'.fa.gz'),'rb') as fa:
        for line in fa:
            if line.startswith(b'>'):
                if h is not None: hashes.append(h.hexdigest())
                h=sha256();need(line.strip()==f'>{GROUP}_{len(hashes)+1}'.encode(),'FASTA record identity');continue
            dna=line.strip();h.update(dna);total+=len(dna);ns+=dna.upper().count(b'N')
    if h is not None:hashes.append(h.hexdigest())
    m=metrics['metrics'];need(hashes==m['record_hashes']==[r['sha256'] for r in layout] and total==m['sequence_bp'] and ns==m['sequence_n_bp'],'FASTA / layout mismatch')
    axis=defaultdict(list); joins=set(); ordered=[]
    for r in layout:
        v=r['slices']; need(len(v)==len(r['joins'])+1,'invalid layout')
        for d,c,a,b,o in v:
            axis[d,c,o].append(Interval(a,b)); ordered.append((d,c,o))
        for l,j,t in zip(v,r['joins'],v[1:]):
            need(j[0]!='input_assembly_gap','this particular frozen input has no original gaps; general comparison needs gap-source occupancy')
            joins.add((tuple(l[:2]),l[4],l[3] if l[4]=='+' else l[2],tuple(t[:2]),t[4],t[2] if t[4]=='+' else t[3],j[0]))
    occ={s:merged_intervals(v) for s,v in axis.items()}
    need(sum(x.length for v in occ.values() for x in v)==m['source_bp_used'],'slice occupancy mismatch')
    return metrics,occ,joins,ordered


def ref_coverage(root,arms):
    snapshot=sealed(root/'q0-latest-fork-20261123-1435/control/snapshot.json','2c8bd6a23eb339f71f16ab0a1e68f74562546532733ae98d3deae3d6609b1f3d'); source=Path(snapshot['source']); spans={a:[] for a in arms}
    targets={s[:2] for _,occ,_,_ in arms.values() for s in occ}; nfiles=0
    for row in snapshot['files']:
        rel=row['path']
        if not rel.startswith('runs/') or not rel.endswith('_vs_ref/result.paf'): continue
        ds=rel.split('/')[1][:-len('_vs_ref')]; nfiles+=1; h=sha256(); nb=0
        with (source/rel).open('rb') as f:
            for num,line in enumerate(f,1):
                h.update(line);nb+=len(line);fields=line.split(b'\t',12)
                if len(fields)<12 or fields[5]!=GROUP.encode():continue
                key=ds,fields[0].decode(); mq=int(fields[11]);
                if key not in targets or not 20<=mq<255 or int(fields[9])<.90*int(fields[10]):continue
                hit=parse_paf_line(line.decode(),artifact=rel,line_number=num); k=(*key,hit.strand)
                selected={a:occ[k] for a,(_,occ,_,_) in arms.items() if k in occ}
                if not selected:continue
                per={a:[] for a in selected}
                for block in hit.aligned_blocks():
                    if block.operation=='X':continue
                    for a,ivs in selected.items():
                        for i in ivs:
                            v=block.query.intersection(i)
                            if v is not None:
                                left=block.target.start+(v.start-block.query.start if hit.strand=='+' else block.query.end-v.end)
                                per[a].append(Interval(left,left+v.length))
                for a,v in per.items():spans[a].extend(merged_intervals(v))
        need(nb==row['size'] and h.hexdigest()==row['sha256'],'reference PAF identity')
    need(nfiles==2,'expected both frozen reference PAFs');return {a:merged_intervals(x) for a,x in spans.items()}


def compare(arms,ref,x,y):
    m,o,j,order=arms[x]; n,p,k,other=arms[y]; same=sum(intersect_bp(v,p.get(s,())) for s,v in o.items());opp=sum(intersect_bp(v,p.get((*s[:2],'-' if s[2]=='+' else '+'),())) for s,v in o.items()); common=intersect_bp(ref[x],ref[y]);size=lambda v:sum(i.length for i in v)
    # Relative order only for single-occurrence shared, same-strand sources. A split is not a certified junction.
    shared={s for s in set(order)&set(other) if order.count(s)==other.count(s)==1};ids={s:i for i,s in enumerate(other) if s in shared}; ranks=[ids[s] for s in order if s in shared]
    return dict(same_source_same_strand_bp=same,same_source_opposite_strand_bp=opp,source_bp_only_in_first=m['metrics']['source_bp_used']-same-opp,
                source_bp_only_in_second=n['metrics']['source_bp_used']-same-opp,common_join_geometry=len(j&k),first_only_joins=len(j-k),second_only_joins=len(k-j),
                reference_supported_bp_only_in_first=size(ref[x])-common,reference_supported_bp_only_in_second=size(ref[y])-common,
                shared_unique_oriented_sources=len(ranks),order_inversions=sum(a>b for i,a in enumerate(ranks) for b in ranks[i+1:]))


def main(root,candidate='BC'):
    need(candidate in ('BC','BC-local'),'unregistered pilot arm')
    arms={a:verify_arm(root,a,candidate) for a in 'ABC'};ref=ref_coverage(root.parent,arms);report={}
    for a,(v,*_) in arms.items():
        report[a]={k:w for k,w in v['metrics'].items() if k!='record_hashes'};report[a].update(from_input_s=v['from_input_s'],input_load_s=v['load_s'],mapper_calls=v['mapper_calls'],reference_supported_bp=sum(x.length for x in ref[a]))
    write(root/('comparison.json' if candidate=='BC' else 'comparison-local.json'),dict(arms=report,comparisons={x+'_'+y:compare(arms,ref,x,y) for x,y in [('A','B'),('A','C'),('B','C')]},
        limits='One group. A is frozen initial-evidence sequence, not truth or final repaired Q0. Reference metric uses initial high-MAPQ same-strand paired blocks, not independent validation. Unused bases are not donor eligibility.'))

if __name__=='__main__':main(Path(sys.argv[1]).resolve(strict=True),*sys.argv[2:])
