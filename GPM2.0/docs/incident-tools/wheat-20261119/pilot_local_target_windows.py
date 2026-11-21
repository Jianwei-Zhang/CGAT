"""Isolated matched-site pilot with regional targets; never a production receipt."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import time
from measure_existing_cross_coverage import paired_geometry
from partial_coverage_sizing import merged
from measure_local_target_scope import require_residual_core


def fetch(path, fai, start, end):
    length, offset, bases, width = fai
    if not 0 <= start < end <= length or bases < 1 or width < bases:
        raise ValueError("invalid FAI/window")
    position = lambda p: offset + p//bases*width + p%bases
    with path.open("rb") as f:
        f.seek(position(start)); raw=f.read(position(end-1)+1-position(start))
    seq=raw.replace(b"\n",b"").replace(b"\r",b"").upper()
    if len(seq)!=end-start or set(seq)-set(b"ACGTRYSWKMBDHVN"):
        raise ValueError("window extraction differs from FAI/alphabet")
    return seq


def add_geometry(coverage, fields, target, qoffset, toffset, core, minimum_bp=100):
    blocks=paired_geometry(fields)  # validate even low-identity or empty-core rows
    if int(fields[9])/int(fields[10]) < .95:return
    rows=[]
    for qs,qe,ts,te in blocks:
        qs+=qoffset;qe+=qoffset;ts+=toffset
        a,b=max(qs,core[0]),min(qe,core[1])
        if a<b:
            diagonal=ts-qs if fields[4]=="+" else ts+qe
            rows.append(((target,fields[4],diagonal),[a,b]))
    if sum(b-a for _,(a,b) in rows)<minimum_bp:return
    for key,row in rows:coverage[key].append(row)


def size(rows):return sum(b-a for a,b in merged(rows))


def intersection(left,right):
    left,right=merged(left),merged(right);i=j=total=0
    while i<len(left) and j<len(right):
        a,b=left[i];c,d=right[j];total+=max(0,min(b,d)-max(a,c))
        if b<=d:i+=1
        else:j+=1
    return total


def mapper_command(tool, target, query, threads, secondary_cap=None, min_chain_score=None):
    flags=["-D", "--dual=yes", "--no-long-join"]
    if secondary_cap is None:flags.insert(1,"-P")
    elif secondary_cap == 100:flags.extend(["-p","0","-N",str(secondary_cap)])
    else:raise ValueError("unsupported isolated secondary profile")
    if min_chain_score is not None:
        if min_chain_score != 2000:raise ValueError("unsupported isolated chain-score profile")
        flags.extend(["-m",str(min_chain_score)])
    return [str(tool),"-c","-x","asm10",*flags,"-t",str(threads),str(target),str(query)]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace",type=Path,required=True)
    p.add_argument("--lookup-dir",type=Path,required=True)
    p.add_argument("--plan-dir",type=Path,required=True)
    p.add_argument("--cross-summary",type=Path,required=True)
    p.add_argument("--minimap2",type=Path,required=True)
    p.add_argument("--threads",type=int,default=2)
    p.add_argument("--secondary-cap",type=int,choices=[100])
    p.add_argument("--min-chain-score",type=int,choices=[2000])
    p.add_argument("--regional-baseline-dir",type=Path)
    a=p.parse_args();root=a.workspace.resolve(strict=True);out=Path.cwd().resolve()
    if out==root or root in out.parents or not 1<=a.threads<=8:raise ValueError("isolated output/budget required")
    metadata={}; source_stats={}
    def load(path):
        raw=path.read_bytes();metadata[str(path)]=hashlib.sha256(raw).hexdigest();return json.loads(raw)
    lookup=load(a.lookup_dir/"source-part-lookup.json");proof=load(a.lookup_dir/"receipt.json")
    if metadata[str(a.lookup_dir/"source-part-lookup.json")]!=proof["lookup_sha256"]:raise ValueError("lookup changed")
    plans=load(a.plan_dir/"local-target-plan.json");scope=load(a.plan_dir/"summary.json")
    cross=load(a.cross_summary);expected={r["path"]:r["sha256"] for r in cross["scans"] if r["path"].startswith("runs/")}
    if len(plans)!=3 or len(scope["windows"])!=3:raise ValueError("expected fixed three-site feasibility plan")
    datasets=list(csv.DictReader((root/"metadata/datasets.tsv").read_text().splitlines(),delimiter="\t"))
    source={};index={}
    for dataset in datasets:
        name=dataset["dataset_name"];source[name]=root/dataset["fasta_relpath"]
        source_stats[str(source[name])]=source[name].stat()
        fai=root/dataset["fai_relpath"];raw=fai.read_bytes();metadata[str(fai)]=hashlib.sha256(raw).hexdigest()
        index[name]={f[0]:tuple(map(int,f[1:5])) for f in (line.split("\t") for line in raw.decode().splitlines())}
    metadata[str(root/"metadata/datasets.tsv")]=hashlib.sha256((root/"metadata/datasets.tsv").read_bytes()).hexdigest()
    binary_sha=hashlib.sha256(a.minimap2.read_bytes()).hexdigest()
    if binary_sha!="cb7e8f228d516fe4632a2250d09d1635ddd7aa95588c9fd5442d1dbe6e9a20a3":raise ValueError("unexpected mapper")
    part_names={(v["dataset"],v["contig"]):key for key,v in lookup.items()}
    qid=plans[0]["query_id"];qrow=lookup[qid]
    if index[qrow["dataset"]][qrow["contig"]][0]!=qrow["length"]:raise ValueError("query length changed")
    is_residual=scope.get("query_scope")=="recorded_residual_core"
    if is_residual:
        residual_path=Path(scope["residual_file"]);residual=load(residual_path)
        if metadata[str(residual_path)]!=scope["metadata_sha256"][str(residual_path)]:raise ValueError("residual intervals changed")
        for window in scope["windows"]:
            require_residual_core(residual,qrow["dataset"],qrow["contig"],window["core_start"],window["core_end"])
    baseline=[defaultdict(list) for _ in plans];candidate=[defaultdict(list) for _ in plans]
    for descriptor in sorted((root/"runs").glob("chr_*/q0_alignment_inputs.json")):
        for row in load(descriptor)["alignments"]:
            if row["query_dataset"]!=qrow["dataset"] or row["target_dataset"]==qrow["dataset"]:continue
            path=root/row["paf"];digest=hashlib.sha256()
            with path.open("rb") as f:
                for raw in f:
                    digest.update(raw)
                    if not raw.strip() or raw.startswith(b"#"):continue
                    fields=raw.decode().rstrip("\r\n").split("\t")
                    if fields[0]!=qrow["contig"]:continue
                    target=part_names[(row["target_dataset"],fields[5])]
                    if int(fields[1])!=qrow["length"] or int(fields[6])!=lookup[target]["length"]:raise ValueError("cross source mismatch")
                    for i,window in enumerate(scope["windows"]):
                        core=(window["core_start"],window.get("core_end",min(qrow["length"],window["core_start"]+100000)))
                        add_geometry(baseline[i],fields,target,0,0,core)
            if digest.hexdigest()!=expected[row["paf"]]:raise ValueError("completed cross changed")
    regional_baseline=load(a.regional_baseline_dir/"summary.json") if a.regional_baseline_dir else None
    if regional_baseline and regional_baseline.get("status")!="isolated_regional_pilot_complete":raise ValueError("incomplete regional baseline")
    reports=[]
    for i,(plan,window) in enumerate(zip(plans,scope["windows"])):
        if plan["query_id"]!=qid or plan["query_interval"]!=window["query_interval"]:raise ValueError("plan mismatch")
        if not 0<window["target_bp"]<=100_000_000:raise ValueError("regional pilot size budget exceeded")
        d=out/f"site-{i}";d.mkdir();qstart,qend=plan["query_interval"]
        qseq=fetch(source[qrow["dataset"]],index[qrow["dataset"]][qrow["contig"]],qstart,qend)
        (d/"query.fa").write_bytes(b">query\n"+qseq+b"\n")
        targets={};window_sha={};total=0
        with (d/"target.fa").open("wb") as f:
            for pid,intervals in sorted(plan["target_intervals"].items()):
                row=lookup[pid]
                if pid==qid:raise ValueError("original self is not allowed")
                if index[row["dataset"]][row["contig"]][0]!=row["length"]:raise ValueError("source length changed")
                for start,end in intervals:
                    key=f"target-{len(targets)}";seq=fetch(source[row["dataset"]],index[row["dataset"]][row["contig"]],start,end)
                    targets[key]=(pid,start,end);window_sha[key]=hashlib.sha256(seq).hexdigest();total+=len(seq)
                    f.write(f">{key}\n".encode()+seq+b"\n")
        if total!=window["target_bp"]:raise ValueError("target size differs from planned geometry")
        command=mapper_command(a.minimap2,d/"target.fa",d/"query.fa",a.threads,a.secondary_cap,a.min_chain_score)
        (d/"inputs.json").write_text(json.dumps(dict(query=plan["query_interval"],query_sha256=hashlib.sha256(qseq).hexdigest(),targets=targets,target_sequence_sha256=window_sha,command=command,tool_sha256=binary_sha),indent=2)+"\n")
        def limit():resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
        started=time.monotonic()
        with (d/"result.paf.tmp").open("wb") as stdout,(d/"stderr.log").open("wb") as stderr:
            proc=subprocess.Popen(command,stdout=stdout,stderr=stderr,start_new_session=True,preexec_fn=limit)
            try:code=proc.wait(timeout=300)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                (d/"timeout.json").write_text(json.dumps(dict(pid=proc.pid,seconds=300,partial_result_accepted=False)))
                raise RuntimeError("isolated mapper budget expired")
        seconds=time.monotonic()-started
        if code:raise RuntimeError(f"mapper exit {code}")
        core=(window["core_start"],window.get("core_end",min(qrow["length"],window["core_start"]+100000)));rows=0
        with (d/"result.paf.tmp").open() as f:
            for line in f:
                fields=line.rstrip("\r\n").split("\t");pid,start,end=targets[fields[5]]
                if fields[0]!="query" or int(fields[1])!=qend-qstart or int(fields[6])!=end-start:raise ValueError("raw window PAF input mismatch")
                add_geometry(candidate[i],fields,pid,qstart,start,core);rows+=1
        (d/"result.paf.tmp").rename(d/"result.paf")
        old_bp=sum(size(v) for v in baseline[i].values())
        retained=sum(intersection(v,candidate[i].get(k,[])) for k,v in baseline[i].items())
        if is_residual and old_bp:raise ValueError("recorded residual core unexpectedly has completed cross coverage")
        if not is_residual and not old_bp:raise ValueError("no completed cross control for selected core")
        by_role={"cross":[],"within":[]}
        for (target, strand, diagonal), intervals in candidate[i].items():
            by_role["cross" if lookup[target]["dataset"]!=qrow["dataset"] else "within"].extend(intervals)
        report=dict(core_start=core[0],target_bp=total,mapper_seconds=seconds,raw_rows=rows,
                    completed_cross_exact_paired_bp=old_bp,retained_exact_paired_bp=retained,retention=retained/old_bp if old_bp else None,
                    query_scope="recorded_residual_core" if is_residual else "matched_site_control",
                    qualified_cross_core_covered_bp=size(by_role["cross"]),qualified_within_core_covered_bp=size(by_role["within"]),
                    raw_paf_sha256=hashlib.sha256((d/"result.paf").read_bytes()).hexdigest())
        if regional_baseline:
            old_dir=a.regional_baseline_dir/f"site-{i}"
            for name in ("query.fa","target.fa"):
                if hashlib.sha256((old_dir/name).read_bytes()).hexdigest()!=hashlib.sha256((d/name).read_bytes()).hexdigest():raise ValueError("regional baseline input differs")
            old_inputs=load(old_dir/"inputs.json")
            old_paf=old_dir/"result.paf";raw=old_paf.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=regional_baseline["sites"][i]["raw_paf_sha256"]:raise ValueError("regional baseline output changed")
            for minimum in (100,10000):
                old_coverage=defaultdict(list)
                for line in raw.decode().splitlines():
                    fields=line.split("\t");pid,start,end=old_inputs["targets"][fields[5]]
                    add_geometry(old_coverage,fields,pid,qstart,start,core,minimum_bp=minimum)
                old_pairs={k[:2] for k in old_coverage};new_pairs={k[:2] for k in candidate[i]}
                report[f"regional_baseline_min{minimum}"]=dict(exact_paired_bp=sum(size(v) for v in old_coverage.values()),
                    retained_exact_paired_bp=sum(intersection(v,candidate[i].get(k,[])) for k,v in old_coverage.items()),
                    source_strand_pairs=len(old_pairs),retained_source_strand_pairs=len(old_pairs&new_pairs))
        reports.append(report);print(json.dumps(report),flush=True)
    fence=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    for path,stat in source_stats.items():
        if fence(Path(path).stat())!=fence(stat):raise ValueError("source FASTA changed")
    for path,sha in metadata.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError("metadata changed")
    if hashlib.sha256(a.minimap2.read_bytes()).hexdigest()!=binary_sha:raise ValueError("mapper changed")
    report=dict(status="isolated_regional_pilot_complete",sites=reports,metadata_sha256=metadata,tool_sha256=binary_sha,
                main_modified=False,scientific_acceptance=False,source_whole_content_revalidated=False,secondary_cap=a.secondary_cap,min_chain_score=a.min_chain_score,
                limitations="three explicitly scoped cores; residual cores have no baseline retention ratio; new coverage is not uniqueness or final biological accuracy; not all global alternatives; raw window MAPQ not whole-source confidence")
    (out/"summary.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report),flush=True)


if __name__=="__main__":main()
