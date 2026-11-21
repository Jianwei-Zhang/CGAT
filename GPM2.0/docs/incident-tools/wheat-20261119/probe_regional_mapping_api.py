"""Run the real regional receipt/cache API on six previously measured windows.

Only selected original sources are loaded and content-verified. This is an
isolated integration probe, not a main-workspace ready manifest or final result.
"""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys
import time
from unittest import mock


def fetch(path,row):
    length,offset,bases,width=row
    with path.open("rb") as f:
        f.seek(offset);raw=f.read((length-1)//bases*width+(length-1)%bases+1)
    sequence=raw.replace(b"\n",b"").replace(b"\r",b"").upper()
    if len(sequence)!=length:raise ValueError("source FAI length differs")
    return sequence.decode("ascii")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace",type=Path,required=True);p.add_argument("--package-dir",type=Path,required=True)
    p.add_argument("--lookup-dir",type=Path,required=True);p.add_argument("--control-plan-dir",type=Path,required=True)
    p.add_argument("--residual-plan-dir",type=Path,required=True);p.add_argument("--minimap2",required=True)
    p.add_argument("--cross-summary",type=Path,required=True)
    a=p.parse_args();started=time.monotonic();work=a.workspace.resolve(strict=True)
    sys.path[:0]=[str(a.package_dir.resolve(strict=True)),str(work/".prepare_lib/tools")]
    from lgz_core.common import executable_identity,stable_id
    from lgz_core.q0_catalog import CandidateCatalog
    from lgz_core.q0_sources import SourceKey,split_source,Interval,merged_intervals
    from lgz_core.q0_query_windows import QueryWindow,TargetWindow
    from lgz_core import q0_preparation  # Fail fast before loading selected source DNA.
    from lgz_core.q0_regional_mapping import prepare_regional_mapping,verify_regional_task
    from lgz_core.q0_alignments import read_paf,parse_paf_line
    inputs={}
    def read(path):
        raw=path.read_bytes();inputs[str(path)]=hashlib.sha256(raw).hexdigest();return raw
    def load(path):return json.loads(read(path))
    for path in sorted((a.package_dir/"lgz_core").glob("*.py")):read(path)
    lookup=load(a.lookup_dir/"source-part-lookup.json");proof=load(a.lookup_dir/"receipt.json")
    if inputs[str(a.lookup_dir/"source-part-lookup.json")]!=proof["lookup_sha256"]:raise ValueError("lookup changed")
    cases=[];selected=set()
    for role,directory in [("control",a.control_plan_dir),("residual",a.residual_plan_dir)]:
        plans=load(directory/"local-target-plan.json");scope=load(directory/"summary.json")
        for plan,window in zip(plans,scope["windows"]):
            cases.append((role,plan,window));selected.add(plan["query_id"]);selected.update(plan["target_intervals"])
    total=sum(lookup[key]["length"] for key in selected)
    if total>20_000_000_000:raise ValueError("selected-source memory budget exceeded")
    dataset_rows=list(csv.DictReader(read(work/"metadata/datasets.tsv").decode().splitlines(),delimiter="\t"))
    paths={row["dataset_name"]:work/row["fasta_relpath"] for row in dataset_rows};fai={}
    signature=lambda p:(lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns))(p.stat())
    before={str(path):signature(path) for path in paths.values()}
    for row in dataset_rows:
        fai[row["dataset_name"]]={f[0]:tuple(map(int,f[1:5])) for f in (line.split("\t") for line in read(work/row["fai_relpath"]).decode().splitlines())}
    sources={};parts={};verified=[]
    for count,pid in enumerate(sorted(selected,key=lambda key:(lookup[key]["dataset"],fai[lookup[key]["dataset"]][lookup[key]["contig"]][1])),1):
        row=lookup[pid];key=SourceKey(row["dataset"],row["contig"])
        seq=fetch(paths[key.dataset],fai[key.dataset][key.contig]);index=split_source(key,seq)
        if len(index.segments)!=1 or index.segments[0].segment_id!=pid or index.segments[0].sequence_sha256!=row["sequence_sha256"]:raise ValueError("selected source DNA differs from canonical part")
        sources[key]=seq;parts[pid]=index.segments[0];verified.append([pid,len(seq),row["sequence_sha256"]])
        if count%100==0:print(json.dumps(dict(phase="source_verification",records=count,seconds=time.monotonic()-started)),flush=True)
    catalog=CandidateCatalog({"candidates":[]},sources,parts)
    catalog._regional_verified_parts={key:(sources[part.source],part.interval,part.sequence_sha256) for key,part in parts.items()}
    root=Path("artifacts").resolve();root.mkdir();tool=executable_identity(a.minimap2)
    if tool["sha256"]!="cb7e8f228d516fe4632a2250d09d1635ddd7aa95588c9fd5442d1dbe6e9a20a3":raise ValueError("unexpected mapper")
    reference=list(csv.DictReader(read(work/"metadata/reference.tsv").decode().splitlines(),delimiter="\t"))
    reference_bases=sum(int(line.split("\t")[1]) for line in read(work/reference[0]["fai_relpath"]).decode().splitlines())
    def add_frames(frames,hit,target_id,core):
        if hit.matches/hit.block_length<.95:return
        rows=[]
        for block in hit.aligned_blocks():
            if block.operation=="X":continue
            overlap=block.query.intersection(Interval(*core))
            if overlap is not None:
                diagonal=block.target.start-block.query.start if hit.strand=="+" else block.target.start+block.query.end
                rows.append(((target_id,hit.strand,diagonal),overlap))
        if sum(i.length for _,i in rows)>=100:
            for key,interval in rows:frames[key].append(interval)
    def overlap_size(left,right):
        a,b=merged_intervals(left),merged_intervals(right);i=j=total=0
        while i<len(a) and j<len(b):
            overlap=a[i].intersection(b[j]);total+=overlap.length if overlap else 0
            if a[i].end<=b[j].end:i+=1
            else:j+=1
        return total
    baseline=[defaultdict(list) for _ in cases];by_name={(row["dataset"],row["contig"]):key for key,row in lookup.items()}
    cross=load(a.cross_summary);expected={r["path"]:r["sha256"] for r in cross["scans"] if r["path"].startswith("runs/")}
    query_source=parts[cases[0][1]["query_id"]].source
    for descriptor in sorted((work/"runs").glob("chr_*/q0_alignment_inputs.json")):
        for row in load(descriptor)["alignments"]:
            if row["query_dataset"]!=query_source.dataset or row["target_dataset"]==query_source.dataset:continue
            digest=hashlib.sha256()
            with (work/row["paf"]).open("rb") as stream:
                for number,raw in enumerate(stream,1):
                    digest.update(raw)
                    if raw.split(b"\t",1)[0]!=query_source.contig.encode():continue
                    hit=parse_paf_line(raw.decode(),artifact=row["paf"],line_number=number)
                    target=by_name[row["target_dataset"],hit.target_name]
                    for i,(_,plan,window) in enumerate(cases):
                        core=(window["core_start"],window.get("core_end",window["core_start"]+100000))
                        add_frames(baseline[i],hit,target,core)
            if digest.hexdigest()!=expected[row["paf"]]:raise ValueError("complete original cross evidence changed")
    reports=[];tasks=[];queries=[];targets_by_case=[]
    for case_number,(role,plan,window) in enumerate(cases):
        qid=plan["query_id"];core=(window["core_start"],window.get("core_end",window["core_start"]+100000))
        query=QueryWindow(qid,parts[qid].interval.length,*plan["query_interval"],(core,))
        targets=[TargetWindow(pid,parts[pid].interval.length,start,end) for pid,intervals in plan["target_intervals"].items() for start,end in intervals]
        begin=time.monotonic();task=prepare_regional_mapping(root,catalog,query,targets,tool,reference_bases=reference_bases,threads=2)
        receipt=verify_regional_task(root,task,members=parts);decision=json.loads((root/receipt["spec"]["decision"]["path"]).read_text())
        covered=defaultdict(list);frames=defaultdict(list);rows=0
        for hit in read_paf(root/task["paf"],query_lengths={qid:parts[qid].interval.length},target_lengths={pid:parts[pid].interval.length for pid in task["target_ids"]}):
            rows+=1;add_frames(frames,hit,hit.target_name,core)
            if hit.matches/hit.block_length<.95:continue
            blocks=[overlap for block in hit.aligned_blocks() if block.operation!="X" and (overlap:=block.query.intersection(Interval(*core))) is not None]
            if sum(i.length for i in blocks)<100:continue
            covered["cross" if parts[qid].source.dataset!=parts[hit.target_name].source.dataset else "within"].extend(blocks)
        baseline_bp=sum(i.length for intervals in baseline[case_number].values() for i in merged_intervals(intervals))
        retained_bp=sum(overlap_size(intervals,frames.get(key,())) for key,intervals in baseline[case_number].items())
        if role=="control" and (not baseline_bp or retained_bp!=baseline_bp):raise ValueError("complete original cross control coordinates lost")
        report=dict(role=role,core_start=core[0],completed_cross_exact_paired_bp=baseline_bp,retained_exact_paired_bp=retained_bp,total_api_seconds=time.monotonic()-begin,selected_flags=decision["additional_flags"],decision_reason=decision["reason"],projected_rows=rows,
                    cross_core_covered_bp=sum(i.length for i in merged_intervals(covered["cross"])),within_core_covered_bp=sum(i.length for i in merged_intervals(covered["within"])),task=task)
        reports.append(report);tasks.append(task);queries.append(query);targets_by_case.append(targets);print(json.dumps({k:v for k,v in report.items() if k not in ("task","sites","inputs")}),flush=True)
    original=verify_regional_task(root,tasks[0]);q=queries[0]
    changed=QueryWindow(q.segment_id,q.segment_length,q.start,q.end,((q.cores[0][0]+100,q.cores[0][1]-100),))
    with mock.patch("subprocess.Popen",side_effect=AssertionError("core-only repair must reuse complete raw mapping")):
        reused=prepare_regional_mapping(root,catalog,changed,targets_by_case[0],tool,reference_bases=reference_bases,threads=2)
    updated=verify_regional_task(root,reused)
    if original["spec"]["raw_receipt"]!=updated["spec"]["raw_receipt"]:raise ValueError("raw result was not reused")
    for path,old in before.items():
        if signature(Path(path))!=old:raise ValueError("original source FASTA changed")
    for path,sha in inputs.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError("input metadata/code changed")
    report=dict(status="regional_mapping_api_probe_complete",selected_original_sources=len(selected),selected_source_bases=total,verified_source_inventory=stable_id("verified-sources",sorted(verified)),
                sites=reports,core_only_repair_reused_raw=True,window_fastas_remaining=len(list(root.rglob("query.fa")))+len(list(root.rglob("target.fa"))),
                original_source_content_verified=True,whole_dataset_content_revalidated=False,seconds=time.monotonic()-started,inputs=inputs,production_modified=False,scientific_acceptance=False)
    Path("summary.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps({k:v for k,v in report.items() if k not in ("task","sites","inputs")}),flush=True)


if __name__=="__main__":main()
