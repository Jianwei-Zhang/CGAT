"""Build the production-candidate disk index without loading whole genomes.

Only metadata/PAFs are read, on a compute node. This is a routing feasibility
artifact, never a main-workspace checkpoint or a biological admission result.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from measure_existing_cross_coverage import paired_geometry


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace",type=Path,required=True)
    p.add_argument("--lookup-dir",type=Path,required=True)
    p.add_argument("--reference-summary",type=Path,required=True)
    p.add_argument("--index-module",type=Path,required=True)
    p.add_argument("--control-plan-dir",type=Path,required=True)
    p.add_argument("--residual-plan-dir",type=Path,required=True)
    a=p.parse_args();started=time.monotonic();root=a.workspace.resolve(strict=True)
    sys.path.insert(0,str(root/".prepare_lib/tools"))
    from lgz_core.q0_sources import SourceSegment, SourceKey, Interval, subtract_intervals
    from lgz_core.common import stable_id
    name="lgz_core.q0_regional_index_probe"
    spec=importlib.util.spec_from_file_location(name,a.index_module);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    inputs={}
    def read(path):
        raw=path.read_bytes();inputs[str(path)]=hashlib.sha256(raw).hexdigest();return raw
    def load(path):return json.loads(read(path))
    read(a.index_module)
    lookup=load(a.lookup_dir/"source-part-lookup.json");proof=load(a.lookup_dir/"receipt.json")
    if inputs[str(a.lookup_dir/"source-part-lookup.json")]!=proof["lookup_sha256"]:raise ValueError("lookup changed")
    parts={};names={}
    for key,row in lookup.items():
        source=SourceKey(row["dataset"],row["contig"]);length=row["length"];sha=row["sequence_sha256"]
        if stable_id("q0-source-part",[source.dataset,source.contig,0,length,sha])!=key:raise ValueError("not a canonical full-source part")
        parts[key]=SourceSegment(key,source,Interval(0,length),sha,0,"record_start","record_end");names[source.dataset,source.contig]=key
    reference=list(csv.DictReader(read(root/"metadata/reference.tsv").decode().splitlines(),delimiter="\t"))
    if len(reference)!=1:raise ValueError("one reference required")
    ref_fai=root/(reference[0]["fasta_relpath"]+".fai")
    lengths={f[0]:int(f[1]) for f in (line.split("\t") for line in read(ref_fai).decode().splitlines())}
    expected={r["dataset"]:r["reference_paf_sha256"] for r in load(a.reference_summary)["datasets"]}
    index=module.RegionalIndex.create(Path("regional.sqlite"),parts,lengths)
    counts=[]
    for dataset in expected:
        path=root/f"runs/{dataset}_vs_ref/result.paf";before=path.stat();digest=hashlib.sha256();rows=0;qualified=0
        with path.open("rb") as stream:
            for raw in stream:
                digest.update(raw)
                if not raw.strip() or raw.startswith(b"#"):continue
                rows+=1;f=raw.decode("ascii").rstrip("\r\n").split("\t")
                part=parts[names[dataset,f[0]]]
                if int(f[1])!=part.interval.length or int(f[6])!=lengths[f[5]]:raise ValueError("PAF lengths changed")
                if int(f[10])<1:raise ValueError("invalid span")
                if int(f[9])/int(f[10])>=.90:
                    for qs,qe,ts,te in paired_geometry(f):index.observe(part.segment_id,f[5],Interval(qs,qe),Interval(ts,te),f[4])
                    qualified+=1
                if rows%500000==0:print(json.dumps(dict(dataset=dataset,rows=rows,seconds=time.monotonic()-started)),flush=True)
        after=path.stat();fence=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if digest.hexdigest()!=expected[dataset] or fence(before)!=fence(after):raise ValueError("reference PAF changed")
        counts.append(dict(dataset=dataset,rows=rows,qualified=qualified,sha256=digest.hexdigest()))
    build=index.seal();index.close();index=module.RegionalIndex.open(Path("regional.sqlite"),parts,lengths)
    reports=[]
    for label,directory in [("control",a.control_plan_dir),("residual",a.residual_plan_dir)]:
        plans=load(directory/"local-target-plan.json");scope=load(directory/"summary.json")
        policy=scope.get("policy",{});context=policy.get("anchor_context_bases",0);ref_context=policy.get("reference_context_bases",10000)
        newplans=[];newwindows=[]
        for plan,old_window in zip(plans,scope["windows"]):
            qid=plan["query_id"];query=Interval(*plan["query_interval"])
            regions=index.regions(qid,query,anchor_context=context,reference_context=ref_context,bridge_bases=0)
            targets=index.targets(regions,context=10000,exclude=[qid]);missing=0
            for key,intervals in plan["target_intervals"].items():
                for interval in intervals:missing+=sum(i.length for i in subtract_intervals(Interval(*interval),targets.get(key,())))
            newplans.append(dict(query_id=qid,query_interval=plan["query_interval"],reference_regions={k:[[i.start,i.end] for i in v] for k,v in regions.items()},target_intervals={k:[[i.start,i.end] for i in v] for k,v in targets.items()}))
            newwindows.append(dict(core_start=old_window["core_start"],core_end=old_window.get("core_end",old_window["core_start"]+100000),query_interval=plan["query_interval"],target_bp=sum(i.length for rows in targets.values() for i in rows),target_source_count=len(targets),target_interval_count=sum(len(v) for v in targets.values()),exact_plan_target_bp_omitted=missing))
        sub=Path(label);sub.mkdir();(sub/"local-target-plan.json").write_text(json.dumps(newplans)+"\n")
        report={**scope,"windows":newwindows,"index_schema":module.SCHEMA,"index_cell_bases":module.DEFAULT_CELL_BASES,"index_module_sha256":inputs[str(a.index_module)],"index_routing_only":True}
        (sub/"summary.json").write_text(json.dumps(report,indent=2)+"\n");reports.append(dict(scope=label,windows=newwindows))
    index.close()
    for path,sha in inputs.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError("input metadata changed")
    dbsha=hashlib.sha256(Path("regional.sqlite").read_bytes()).hexdigest()
    report=dict(status="regional_index_probe_complete",build=build,reference_scans=counts,scope=reports,inputs=inputs,index_sha256=dbsha,index_size=Path("regional.sqlite").stat().st_size,seconds=time.monotonic()-started,production_modified=False,scientific_acceptance=False)
    Path("summary.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report),flush=True)


if __name__=="__main__":main()
