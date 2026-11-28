"""Reproduce the real cross-chromosome seed proposals on their original DNA/PAFs."""
from collections import defaultdict
from hashlib import sha256
import itertools, json, sys
from pathlib import Path
from time import monotonic
from wheat_pair_exact_qualification import SNAP, LOOK, checked, digest, need
from lgz_core import q0_admission as adm
from lgz_core.q0_sources import SourceKey, split_source
from lgz_core.q0_retained_hits import _checked_line, retained_names, retained_geometry_cache
from lgz_core.q0_catalog import evidence_ref


def run(mode, owner):
    began=monotonic(); base=owner.parent
    audit=[json.loads(l) for l in (owner/'pairs.txt').read_text().splitlines() if l.startswith('{')]
    chosen={SourceKey(*pair['source']) for pair in audit}
    snapshot=checked(base/'q0-latest-fork-20261123-1435/control/snapshot.json', SNAP)
    work=Path(snapshot['source']);files={r['path']:r for r in snapshot['files']}
    rawlookup=checked(base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json', LOOK)
    lookup={SourceKey(r['dataset'],r['contig']):r for r in rawlookup.values()}
    sequences={};before={};reference_hits=defaultdict(list);evidence={};parts={};edges=[]
    references=work/"data/reference/IWGSC.fa.fai"
    need(digest(references)==files[str(references.relative_to(work))]["sha256"],"reference FAI changed")
    lengths={r.split("\t")[0]:int(r.split("\t")[1]) for r in references.read_text().splitlines()}
    for dataset in sorted({s.dataset for s in chosen}):
        fasta=work/("data/datasets/"+dataset+".fa");fai=Path(str(fasta)+".fai")
        need(digest(fai)==files[str(fai.relative_to(work))]["sha256"],"source FAI changed")
        st=fasta.stat();before[str(fasta)]=(st.st_size,st.st_mtime_ns,st.st_ctime_ns)
        need(st.st_size==files[str(fasta.relative_to(work))]["size"],"source FASTA size changed")
        wanted={s.contig:s for s in chosen if s.dataset==dataset}
        with fasta.open("rb") as stream:
            for row in fai.read_text().splitlines():
                name,n,offset,bases,width,*_=row.split("\t")
                if name not in wanted: continue
                n,offset,bases,width=map(int,(n,offset,bases,width));key=wanted[name]
                count=((n-1)//bases)*width+(n-1)%bases+1
                stream.seek(offset);text=stream.read(count).replace(b"\n",b"").replace(b"\r",b"").decode("ascii").upper()
                need(len(text)==n and sha256(text.encode()).hexdigest()==lookup[key]["sequence_sha256"],"source DNA changed")
                sequences[key]=text;index=split_source(key,text)
                parts.update((p.segment_id,p) for p in index.segments);edges.extend(index.adjacencies)
        relative="runs/"+dataset+"_vs_ref/result.paf";paf=work/relative
        queries=retained_names({s.contig:len(sequences[s]) for s in chosen if s.dataset==dataset})
        targets=retained_names(lengths);geometry=retained_geometry_cache()
        prefix=b"["+json.dumps(relative,separators=(",",":"),ensure_ascii=True).encode()+b",";h=sha256()
        with paf.open("rb") as f:
            for number,raw in enumerate(f,1):
                h.update(raw)
                if raw.split(b"\t",1)[0].decode("utf-8") not in wanted: continue
                hit=_checked_line(raw.decode("utf-8"),paf,relative,number,prefix,queries,targets,geometry)
                if hit is not None:
                    reference_hits[SourceKey(dataset,hit.query_name)].append(hit);evidence[hit.evidence_id]=evidence_ref(hit)
        need(h.hexdigest()==files[relative]["sha256"],"reference PAF changed")
        print("SUBSET_REFERENCE_LOADED",dataset,len(evidence),round(monotonic()-began,2),flush=True)
    data=adm.EvidenceInput(sequences,parts,lengths,dict(reference_hits),(),tuple(edges),evidence,SNAP)
    result=adm.admit_placements(data); actual=set()
    for a,b in itertools.combinations(result.placements,2):
        if a.source==b.source and a.chromosome!=b.chromosome and a.interval.intersection(b.interval):
            actual.add(tuple(sorted((a.placement_id,b.placement_id))))
    expected={tuple(sorted((p['left']['id'],p['right']['id']))) for p in audit}
    need(actual==(expected if mode=='baseline' else set()),'raw reference replay does not reproduce expected conflicts')
    if mode=='fixed':
        for pair in audit:
            a,b=pair['left'],pair['right']; src=SourceKey(*pair['source'])
            if max(a['refhull'][0],b['refhull'][0])<min(a['refhull'][1],b['refhull'][1]):
                need(not any(p.source==src for p in result.placements),'conflicting hulls not unresolved')
            else:
                for arm in (a,b):
                    need(any(p.source==src and p.chromosome==arm['chr'] and
                             [min(x.source.start for x in p.reference_blocks),max(x.source.end for x in p.reference_blocks)]==arm['refhull']
                             for p in result.placements),'lost supported arm')
    print(json.dumps(dict(mode=mode,selector=adm.selector_identity(),sources=len(chosen),pairs=len(actual),
                          placement_count=len(result.placements),reference_hits=sum(map(len,reference_hits.values())),mapper_calls=0)),flush=True)

if __name__=='__main__':
    mode=sys.argv[1]; need(mode in ('baseline','fixed'),'mode');run(mode,Path.cwd())
