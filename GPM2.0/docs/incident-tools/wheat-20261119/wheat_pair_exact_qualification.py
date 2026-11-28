"""Read-only real-source admission equivalence: 2064cb4c vs engineering candidate.

No mapper, no formal workspace writes. Both engines read the very same sealed
input. Reference PAF row numbers and complete cross-chromosome hits are retained.
Only source membership is bounded; this is not whole-wheat biological acceptance.
"""
import argparse
from collections import Counter, defaultdict
from dataclasses import fields, is_dataclass
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import pickle
import subprocess
from time import monotonic

BASELINE = "2064cb4cfd51b5c886f60af19f020caf0b18950f"
LOOK = "2e09b9ff5c849f4d4a83c177c46a4586c29d84b1407666dab8087615ad8c1c89"
SNAP = "2c8bd6a23eb339f71f16ab0a1e68f74562546532733ae98d3deae3d6609b1f3d"


def need(ok, reason):
    if not ok: raise ValueError(reason)


def digest(path):
    h=sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(4<<20),b""): h.update(block)
    return h.hexdigest()


def write(path, value):
    with path.open("x",encoding="utf-8") as f:
        json.dump(value,f,sort_keys=True,separators=(",",":"));f.write("\n")


def checked(path, pin):
    need(digest(path)==pin,"changed input: "+str(path))
    return json.loads(path.read_text())


def prepare(base, owner):
    from lgz_core.q0_sources import SourceKey, split_source
    from lgz_core.q0_admission import EvidenceInput
    from lgz_core.q0_retained_hits import _checked_line, retained_names, retained_geometry_cache
    from lgz_core.q0_catalog import evidence_ref
    began=monotonic()
    snapshot=checked(base/"q0-latest-fork-20261123-1435/control/snapshot.json",SNAP)
    work=Path(snapshot["source"]); files={r["path"]:r for r in snapshot["files"]}
    rawlookup=checked(base/"q0-source-part-lookup-20261121-1600/source-part-lookup.json",LOOK)
    lookup={SourceKey(r["dataset"],r["contig"]):r for r in rawlookup.values()}
    cache=base/"q0-top-chain-locus-20261127.CTotPSFG/loop-selected-links.pickle"
    seal=json.loads(cache.with_suffix(".json").read_text())
    need(digest(cache)==seal["sha256"],"sealed pair cache changed")
    with cache.open("rb") as f: links=pickle.load(f)
    root=SourceKey("JM19_hifiasm","ptg000020l")
    counts=Counter()
    for link in links:
        if link.query_source==root: counts[link.target_source]+=1
        if link.target_source==root: counts[link.query_source]+=1
    counts.pop(root,None)
    # Prefer multiply localized short neighbors, while retaining full sequence
    # and ALL reference hits/competition of every chosen source.
    ranks={}
    screens=base/"q0-continuity-20261126.RAbGvNba/screened-reference-anchors.jsonl.gz"
    receipt=json.loads((screens.parent/"continuity-admission.json").read_text())
    need(digest(screens)==receipt["outputs"][screens.name]["sha256"],"screened inventory changed")
    with gzip.open(screens,"rt") as f:
        for raw in f:
            r=json.loads(raw);key=SourceKey(*r["source"])
            if key in counts and 10000 <= lookup[key]["length"] <= 5_000_000:
                ranks[key]=(len(r["groups"])<2,-len(r["groups"]),lookup[key]["length"],key)
    chosen={root,*sorted(ranks,key=ranks.get)[:64]}
    need(len(chosen)>=33,"insufficient real neighbor subset")
    links=tuple(l for l in links if l.query_source in chosen and l.target_source in chosen)
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
    for link in links: evidence[link.hit.evidence_id]=evidence_ref(link.hit)
    for edge in edges: evidence[edge.adjacency_id]={"kind":"input_assembly_adjacency","source":edge.source.contig}
    for path,expected in before.items():
        st=Path(path).stat();need((st.st_size,st.st_mtime_ns,st.st_ctime_ns)==expected,"FASTA changed during snapshot")
    binding={"baseline_revision":BASELINE,"snapshot_sha256":SNAP,"lookup_sha256":LOOK,"pair_cache_sha256":seal["sha256"],
             "sources":[[s.dataset,s.contig,len(sequences[s]),lookup[s]["sequence_sha256"]] for s in sorted(chosen)],
             "source_bp":sum(map(len,sequences.values())),"parts":len(parts),"pair_links":len(links),
             "reference_hits":sum(map(len,reference_hits.values())),"mapper_calls":0,"formal_workspace_modified":False}
    data=EvidenceInput(sequences,parts,lengths,dict(reference_hits),links,tuple(edges),evidence,
                       sha256(json.dumps(binding,sort_keys=True).encode()).hexdigest())
    with (owner/"subset.pickle").open("xb") as f:pickle.dump(data,f,protocol=5)
    binding["input_sha256"]=digest(owner/"subset.pickle")
    write(owner/"subset.json",binding);print("SUBSET_READY",json.dumps(binding),flush=True)


def canonical(value):
    """Lossless fields, including dataclass keys (asdict cannot encode them)."""
    if is_dataclass(value):
        return {"$type":type(value).__name__,"fields":[[f.name,canonical(getattr(value,f.name))] for f in fields(value)]}
    if isinstance(value,dict):
        return {"$mapping":[[canonical(k),canonical(v)] for k,v in value.items()]}
    if isinstance(value,(tuple,list)):
        return {"$type":type(value).__name__,"items":[canonical(v) for v in value]}
    if isinstance(value,(set,frozenset)):
        return {"$type":type(value).__name__,"items":sorted((canonical(v) for v in value),key=lambda x:json.dumps(x,sort_keys=True))}
    need(value is None or type(value) in (str,int,float,bool),"unencoded admission field: "+str(type(value)))
    return value


def replay(owner, label):
    from lgz_core import q0_admission as adm
    binding=json.loads((owner/"subset.json").read_text())
    need(digest(owner/"subset.pickle")==binding["input_sha256"],"subset changed")
    with (owner/"subset.pickle").open("rb") as f:data=pickle.load(f)
    # Neither replay may invoke any executable; resource proof is captured by
    # the batch wrapper before entering this guard.
    def forbidden(*a,**k): raise RuntimeError("qualification must not start mapper or other subprocess")
    # multiprocessing spawn needs Python subprocess internals, not Popen.
    subprocess.Popen=forbidden
    logs=[]
    def log(s):logs.append(s);print(label,s,flush=True)
    began=monotonic();result=adm.admit_placements(data,screen_threads=32,screen_progress=log)
    elapsed=monotonic()-began
    payload=json.dumps(canonical(result),sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
    with gzip.open(owner/(label+"-admission.json.gz"),"wb") as f:f.write(payload)
    report={"schema":"wheat_pair_engineering_replay_v1","input_sha256":binding["input_sha256"],
            "selector_identity":adm.selector_identity(),"output_sha256":sha256(payload).hexdigest(),
            "output_bytes":len(payload),"elapsed_s":elapsed,"placements":len(result.placements),
            "records":len(result.records),"logs":logs,"mapper_calls":0,"formal_workspace_modified":False}
    write(owner/(label+".json"),report);print("REPLAY_DONE",json.dumps({k:v for k,v in report.items() if k!="logs"}),flush=True)


def compare(owner):
    old=json.loads((owner/"baseline.json").read_text());new=json.loads((owner/"candidate.json").read_text())
    with gzip.open(owner/"baseline-admission.json.gz","rb") as f:a=f.read()
    with gzip.open(owner/"candidate-admission.json.gz","rb") as f:b=f.read()
    need(sha256(a).hexdigest()==old["output_sha256"] and sha256(b).hexdigest()==new["output_sha256"],"output receipt mismatch")
    need(old["selector_identity"]=="q0-selector-4eec44d14ec5dd92e2543f64","baseline is not the original 2064cb4c selector")
    need(old["input_sha256"]==json.loads((owner/"subset.json").read_text())["input_sha256"],"baseline is not this sealed subset")
    same=a==b
    # Byte equality of canonical JSON is stronger than merely equal metrics.
    report={"schema":"wheat_pair_engineering_qualification_v1","baseline_revision":BASELINE,
            "input_sha256":old["input_sha256"],"field_exact_equal":same,
            "baseline_output_sha256":old["output_sha256"],"candidate_output_sha256":new["output_sha256"],
            "baseline_seconds":old["elapsed_s"],"candidate_seconds":new["elapsed_s"],
            "speedup":old["elapsed_s"]/new["elapsed_s"],"candidate_selector_identity":new["selector_identity"],
            "candidate_tools_sha256":digest(owner/"candidate-tools.tgz"),"baseline_tools_sha256":digest(owner/"baseline-tools.tgz"),
            "mapper_calls":0,"formal_workspace_modified":False}
    need(old["input_sha256"]==new["input_sha256"],"different replay inputs")
    worker_lines=[s for s in new["logs"] if s.startswith("placement pair work round=") and "worker_parts=" in s and "worker_parts=0 " not in s]
    report["real_worker_dispatch_verified"]=bool(worker_lines)
    write(owner/"qualification.json",report);print("QUALIFICATION",json.dumps(report),flush=True)
    need(same,"admission field mismatch: HOLD")
    need(worker_lines,"real subset did not exercise workers: HOLD")


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("mode",choices=["prepare","baseline","candidate","compare"])
    parser.add_argument("owner",type=Path);args=parser.parse_args()
    if args.mode=="prepare":prepare(args.owner.parent,args.owner)
    elif args.mode=="compare":compare(args.owner)
    else:replay(args.owner,args.mode)
