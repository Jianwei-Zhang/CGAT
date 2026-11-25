"""Same-input native versus verified raw reuse on preselected historical 4D windows."""
from bisect import bisect_right
from collections import Counter, defaultdict
import csv
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic

from census_wheat_q0_fork import GEOM, HEAD, MAGIC, bind, bounded, pack_context, require, write
from lgz_core.common import sha256_file, stable_id, write_fasta
from lgz_core.q0_alignments import read_paf
from lgz_core import q0_regional_mapping as mapping
from lgz_core.q0_sources import SourceKey
from lgz_core.q0_threshold_acceptance import decode

REQUEST="1a51ebcfef103cb8c986ca7e98cb11eb7e86f6d68f9100d057fc3446e9698ec5"
AXES="7c93bb87545a40a561ac09a88260cc043a297f1236a6d5875c837d4d17542c31"
TOOL="cb7e8f228d516fe4632a2250d09d1635ddd7aa95588c9fd5442d1dbe6e9a20a3"


def select(archive, ranks, demand, *, limit=2):
    # First two contexts in each group, before inspecting receipts or times. The two categories exclude one another.
    def hit(v):
        r,a,b=v
        if r not in demand:return False
        starts,ends=demand[r]; i=bisect_right(ends,a);return i<len(starts) and starts[i]<b
    counts=Counter(); chosen=defaultdict(list); digest=sha256(); ids=set(); last=b""
    with gzip.open(archive,"rb") as f:
        magic=f.read(len(MAGIC));require(magic==MAGIC,"wrong census");digest.update(magic)
        while head:=f.read(HEAD.size):
            ctx,qid,size=HEAD.unpack(head); require(ctx>last and qid not in ids and 1<size<=2_000_000,"wrong inventory order or duplicate query");last=ctx;ids.add(qid)
            data=f.read(GEOM.size*size);require(len(data)==GEOM.size*size,"short context");digest.update(head);digest.update(data)
            rows=GEOM.iter_unpack(data); query=next(rows)
            if query[0] not in ranks:continue
            category="query" if hit(query) else "target_only" if any(hit(v) for v in rows) else "neither"
            counts[category]+=1
            if category!="neither" and (limit is None or len(chosen[category])<limit):
                chosen[category].append(("q0-regional-context-"+ctx.hex(),sha256(head+data).hexdigest()))
    require(len(ids)==23845 and digest.hexdigest()==AXES,"source census changed")
    return dict(counts),dict(chosen)


def window_dna(f, index, w):
    n,offset,bases,width=index; a,b=w["start"],w["end"]
    require(n==w["segment_length"] and 0<=a<b<=n and 0<bases<=width,"FAI frame changed")
    pos=lambda i:offset+(i//bases)*width+i%bases
    f.seek(pos(a)); dna=f.read(pos(b-1)+1-pos(a)).replace(b"\n",b"").replace(b"\r",b"").upper();require(len(dna)==b-a,"incomplete FASTA interval");return dna.decode("ascii")


def replay(root,lookup,order,files,fai,name,axis_hash,tmp):
    rel="grt/evidence/q0_prepare/regional/"+name; directory=root/rel; context=directory/"context.json"
    raw=bounded(context,64<<20); spec=json.loads(raw)["spec"]
    require(sha256(pack_context(name,spec,lookup)).hexdigest()==axis_hash,"stored context differs from frozen query or targets")
    receipts=sorted(directory.glob("q0-regional-raw-*/success.json"))
    # Missing or multiple profiles are a miss/ambiguous, never an excuse to pick another window.
    if len(receipts)!=1:return dict(context=name,status="no_unique_complete_raw",receipt_count=len(receipts))
    tool=spec["tool"]; binary=Path(tool["resolved"]); require(tool["sha256"]==TOOL and sha256_file(binary)==TOOL,"wrong mapper")
    query=spec["query"]; targets=spec["targets"]
    require(targets==sorted(targets,key=lambda v:v["window_id"]),"target order changed")
    def records(windows):
        for w in windows:
            s=order[lookup[w["segment_id"]][0]]
            yield w["window_id"],window_dna(files[s.dataset],fai[s],w)
    inputs=json.loads(raw)["inputs"]; start=monotonic()
    for filename,windows in [("query.fa",[query]),("target.fa",targets)]:
        write_fasta(tmp/filename,records(windows)); row,=[v for v in inputs if v["path"]==rel+"/"+filename]
        require((tmp/filename).stat().st_size==row["size"] and sha256_file(tmp/filename)==row["sha256"],"reconstructed mapper FASTA differs")
    fasta_s=monotonic()-start
    start=monotonic(); receipt=receipts[0]; document=json.loads(bounded(receipt,2<<20)); rs=document["spec"]; rd=receipt.parent; rr=rd.relative_to(root).as_posix(); rawp=rd/"result.paf"
    flags=rs["flags"]; require(rs==dict(schema="lgz_q0_regional_raw_v1",context=dict(path=rel+"/context.json",sha256=sha256(raw).hexdigest(),size=len(raw)),flags=flags) and flags in (["-c",*mapping.BASE_FLAGS],["-c",*mapping.BASE_FLAGS,"-m","2000"]) and rd.name==stable_id("q0-regional-raw",rs),"raw identity/flags changed")
    mapping._read_receipt(root,rr+"/success.json",spec=rs,required={rr+"/"+n for n in ("result.paf","guard.py","command.json")})
    cmd=json.loads((rd/"command.json").read_bytes()); av=cmd["argv"]; require(av[-4]=="-t" and av[-3] in ("1","2","3","4") and av==[str(binary),"-c","-x","asm10",*flags[1:],"-t",av[-3],str(directory/"target.fa"),str(directory/"query.fa")],"unexpected native command or paths")
    guard=Path(mapping.__file__).with_name("q0_mapper_guard.py"); cap=cmd["address_space_bytes"]
    require(cap==4*1024**3 and sha256_file(guard)==cmd["guard_sha256"]==sha256_file(rd/"guard.py"),"mapper guard or memory budget drift")
    rows=sum(1 for _ in read_paf(rawp,query_lengths={query["window_id"]:query["end"]-query["start"]},target_lengths={t["window_id"]:t["end"]-t["start"] for t in targets})); expected=next(r["sha256"] for r in document["outputs"] if r["path"]==rr+"/result.paf"); warm=monotonic()-start
    start=monotonic()
    with (tmp/"raw.paf").open("xb") as out,(tmp/"mapper.log").open("xb") as err:
        subprocess.run([sys.executable,str(guard),"--address-space-bytes",str(cap),"--",*av[:-2],str(tmp/"target.fa"),str(tmp/"query.fa")],stdout=out,stderr=err,check=True)
    cold=monotonic()-start;require(sha256_file(tmp/"raw.paf")==expected and sha256_file(binary)==TOOL,"native replay not byte-identical")
    return dict(context=name,status="matched",target_windows=len(targets),query_bp=query["end"]-query["start"],target_bp=sum(t["end"]-t["start"] for t in targets),flags=flags,raw_rows=rows,raw_sha256=expected,threads=int(av[-3]),raw_receipt_sha256=sha256_file(receipt),fasta_materialize_and_hash_s=fasta_s,cold_native_s=cold,warm_verify_and_decode_s=warm,cold_exact_mapper_calls=1,warm_exact_mapper_calls=0)


def main(base,out):
    snap,root,lookup,order,lengths=bind(base/"q0-latest-fork-20261123-1435/control/snapshot.json",base/"q0-source-part-lookup-20261121-1600/source-part-lookup.json")
    pins={r["path"]:r["sha256"] for r in snap["files"]}
    def table(name):return list(csv.DictReader(io.StringIO(bounded(root/name,64<<20,pins[name]).decode()),delimiter="\t"))
    members={SourceKey(r["dataset_name"],r["seq_name"]) for r in table("metadata/chr_assignments.tsv") if r["assigned_chr_name"]=="4D"}; require(len(members)==766 and sum(lengths[s] for s in members)==1074672025,"wrong group")
    demand=decode(json.loads(bounded(base/"q0-request-ready.44e274a7/qualification/4d-first-request.json",4<<20,REQUEST)),lengths);require(len(demand)==181 and set(demand)<=members,"wrong frozen 4D first demand")
    idx={i:(tuple(v.start for v in demand[s]),tuple(v.end for v in demand[s])) for i,s in enumerate(order) if s in demand}
    counts,picks=select(base/"q0-fork-window-census-20261123-1505/census/axes.bin.gz",{i for i,s in enumerate(order) if s in members},idx)
    write(out/"selection.json",dict(counts=counts,picks=picks));print("PICKS",counts,picks,flush=True)
    from contextlib import ExitStack
    results=[]
    with ExitStack() as stack:
        files={};fai={}
        for d in table("metadata/datasets.tsv"):
            path=d["fai_relpath"];ds=d["dataset_name"];files[ds]=stack.enter_context((root/d["fasta_relpath"]).open("rb"))
            for line in bounded(root/path,16<<20,pins[path]).decode().splitlines():
                contig,n,off,bases,width,*_=line.split("\t");fai[SourceKey(ds,contig)]=tuple(map(int,(n,off,bases,width)))
        for category,cases in picks.items():
            for name,stamp in cases:
                with TemporaryDirectory(prefix="4d-native-") as work: row=replay(root,lookup,order,files,fai,name,stamp,Path(work))
                results.append(dict(category=category,**row));print("WINDOW",results[-1],flush=True)
    write(out/"windows.json",dict(group="4D",known_inventory=23845,group_query_context_counts=counts,first_request_sha256=REQUEST,axes_sha256=AXES,results=results,scope="Preselected 4D-query contexts with a frozen historical target inventory. Same complete inputs and original flags. Raw exact stage only; unit timings exclude shared staging and coarse chaining. Existing verified cache capability, not incremental cold savings or final Q0."))


if __name__=="__main__":main(*map(Path,sys.argv[1:]))
