"""Build/reuse an exact PAF-record index and compare against completed plans."""
import argparse
import csv
import hashlib
import faulthandler
import shutil
import tempfile
import json
from pathlib import Path
import sys
import time


def main():
    faulthandler.dump_traceback_later(120, repeat=True)
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--local-paf-cache", action="store_true")
    p.add_argument("--local-index-cache", action="store_true", help="copy the sealed DB to compute-local scratch, verify identical bytes")
    p.add_argument("--workspace",type=Path,required=True);p.add_argument("--package-dir",type=Path,required=True)
    p.add_argument("--lookup-dir",type=Path,required=True);p.add_argument("--reference-summary",type=Path,required=True)
    p.add_argument("--control-plan-dir",type=Path,required=True);p.add_argument("--residual-plan-dir",type=Path,required=True)
    p.add_argument("--reuse-built",type=Path)
    a=p.parse_args();started=time.monotonic();root=a.workspace.resolve(strict=True);sys.path.insert(0,str(a.package_dir.resolve(strict=True)))
    from lgz_core.q0_sources import SourceKey,SourceSegment,Interval,subtract_intervals
    from lgz_core.q0_alignments import read_paf
    from lgz_core.q0_reference_index import ReferenceIndex
    from lgz_core.common import stable_id
    inputs={}
    def read(path):
        raw=path.read_bytes();inputs[str(path)]=hashlib.sha256(raw).hexdigest();return raw
    def load(path):return json.loads(read(path))
    for path in sorted((a.package_dir/"lgz_core").glob("*.py")):read(path)
    lookup=load(a.lookup_dir/"source-part-lookup.json");proof=load(a.lookup_dir/"receipt.json")
    if inputs[str(a.lookup_dir/"source-part-lookup.json")]!=proof["lookup_sha256"]:raise ValueError("lookup changed")
    parts={};lengths_by_dataset={}
    for key,row in lookup.items():
        source=SourceKey(row["dataset"],row["contig"]);length=row["length"];sha=row["sequence_sha256"]
        if stable_id("q0-source-part",[source.dataset,source.contig,0,length,sha])!=key:raise ValueError("not a full-source part")
        parts[key]=SourceSegment(key,source,Interval(0,length),sha,0,"record_start","record_end")
        lengths_by_dataset.setdefault(source.dataset,{})[source.contig]=length
    reference=list(csv.DictReader(read(root/"metadata/reference.tsv").decode().splitlines(),delimiter="\t"))
    if len(reference)!=1:raise ValueError("one reference required")
    refs={f[0]:int(f[1]) for f in (line.split("\t") for line in read(root/reference[0]["fai_relpath"]).decode().splitlines())}
    expected={r["dataset"]:r["reference_paf_sha256"] for r in load(a.reference_summary)["datasets"]}
    if a.reuse_built:
        built=load(a.reuse_built/"index-built.json");db=a.reuse_built/"reference.sqlite"
        digest=hashlib.sha256()
        with db.open("rb") as stream:
            for block in iter(lambda:stream.read(1024*1024),b""):digest.update(block)
        if digest.hexdigest()!=built["index_sha256"]:raise ValueError("sealed index changed")
        index=None
    else:
        db=Path("reference.sqlite").resolve();index=ReferenceIndex.create(db,root,parts,refs)
        for dataset in expected:
            rel=f"runs/{dataset}_vs_ref/result.paf";index.register_artifact(rel);rows=0
            for hit in read_paf(root/rel,query_lengths=lengths_by_dataset[dataset],target_lengths=refs,artifact=rel,
                    record_observer=lambda hit,off,size,dataset=dataset:index.observe_record(dataset,hit,off,size)):
                rows+=1
                if rows%500000==0:print(json.dumps(dict(dataset=dataset,rows=rows,seconds=time.monotonic()-started)),flush=True)
        built=index.seal();index.close()
        for dataset,sha in expected.items():
            if built["reference_inputs"][f"runs/{dataset}_vs_ref/result.paf"]["sha256"]!=sha:raise ValueError("reference input differs from prior diagnostic")
        digest=hashlib.sha256()
        with db.open("rb") as f:
            for block in iter(lambda:f.read(1024*1024),b""):digest.update(block)
        built={**built,"status":"sealed_reference_index_built","index_sha256":digest.hexdigest(),"index_size":db.stat().st_size,"build_seconds":time.monotonic()-started,"producer_inputs":inputs.copy()}
        Path("index-built.json").write_text(json.dumps(built,indent=2)+"\n");print(json.dumps(built),flush=True)
        index=None
    for dataset,sha in expected.items():
        if built["reference_inputs"][f"runs/{dataset}_vs_ref/result.paf"]["sha256"]!=sha:raise ValueError("reference input differs from prior diagnostic")
    scratch=None
    if a.local_index_cache:
        scratch=tempfile.TemporaryDirectory(prefix="cgat-reference-index-")
        local=Path(scratch.name)/"reference.sqlite"
        print(json.dumps(dict(phase="copy_sealed_db",source=str(db),target=str(local))),flush=True)
        shutil.copyfile(db,local)
        digest=hashlib.sha256()
        with local.open("rb") as stream:
            for block in iter(lambda:stream.read(1024*1024),b""):digest.update(block)
        if digest.hexdigest()!=built["index_sha256"]:raise ValueError("scratch DB bytes differ")
        db=local
    print(json.dumps(dict(phase="open_sealed_index",seconds=time.monotonic()-started)),flush=True)
    paf_scratch=tempfile.TemporaryDirectory(prefix="cgat-reference-pafs-",dir="/tmp") if a.local_paf_cache else None
    index=ReferenceIndex.open(db,root,parts,refs,local_paf_directory=paf_scratch.name if paf_scratch else None)
    print(json.dumps(dict(phase="index_opened",seconds=time.monotonic()-started)),flush=True)
    reports=[];all_equal=True
    for label,directory in [("control",a.control_plan_dir),("residual",a.residual_plan_dir)]:
        plans=load(directory/"local-target-plan.json");scope=load(directory/"summary.json");policy=scope.get("policy",{})
        rows=[];newplans=[]
        for plan,window in zip(plans,scope["windows"]):
            begin=time.monotonic();qid=plan["query_id"]
            regions=index.regions(qid,Interval(*plan["query_interval"]),anchor_context=policy.get("anchor_context_bases",0),reference_context=policy.get("reference_context_bases",10000))
            print(json.dumps(dict(phase="regions",core=window["core_start"],seconds=time.monotonic()-begin)),flush=True)
            targets=index.targets(regions,context=10000,exclude=[qid])
            print(json.dumps(dict(phase="targets",core=window["core_start"],seconds=time.monotonic()-begin)),flush=True)
            rendered_regions={key:[[i.start,i.end] for i in values] for key,values in regions.items()}
            rendered_targets={key:[[i.start,i.end] for i in values] for key,values in targets.items()}
            equal=rendered_targets==plan["target_intervals"] and rendered_regions==plan["reference_regions"];all_equal &= equal
            missing=sum(i.length for key,intervals in plan["target_intervals"].items() for lo,hi in intervals for i in subtract_intervals(Interval(lo,hi),targets.get(key,())))
            rows.append(dict(core_start=window["core_start"],target_bp=sum(i.length for values in targets.values() for i in values),lookup_seconds=time.monotonic()-begin,exact_plan_equal=equal,omitted_bp=missing,reference_query=index.last_query_report))
            newplans.append(dict(query_id=qid,query_interval=plan["query_interval"],reference_regions=rendered_regions,target_intervals=rendered_targets))
        sub=Path(label);sub.mkdir();(sub/"local-target-plan.json").write_text(json.dumps(newplans)+"\n")
        (sub/"comparison.json").write_text(json.dumps(rows,indent=2)+"\n");reports.append(dict(scope=label,windows=rows))
    index.verify_inputs();index.close()
    if scratch is not None:scratch.cleanup()
    if paf_scratch is not None:paf_scratch.cleanup()
    faulthandler.cancel_dump_traceback_later()
    for path,sha in inputs.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError("metadata/code changed")
    report=dict(status="exact_reference_index_verified" if all_equal else "exact_reference_index_mismatch",comparisons=reports,index_built=built,inputs=inputs,seconds=time.monotonic()-started,production_modified=False,scientific_acceptance=False)
    Path("summary.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report),flush=True)
    if not all_equal:raise ValueError("index does not reproduce validated exact plans")


if __name__=="__main__":main()
