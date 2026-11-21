"""Read-only regional-target feasibility, not a production mapping policy.

For fixed query windows, retain all >=0.90 identity reference M/= geometry,
including unavailable MAPQ and alternative chromosomes. Size actual target
source intervals, not whole contigs. No DNA is read and no PAF is fabricated.
"""
import argparse
from bisect import bisect_right
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import time
from measure_existing_cross_coverage import paired_geometry
from partial_coverage_sizing import merged


def project(block, strand, lo, hi, from_query=False):
    qs, qe, ts, te = block
    start, end = (qs, qe) if from_query else (ts, te)
    a, b = max(lo, start), min(hi, end)
    if a >= b:
        return None
    if from_query:
        return [ts+a-qs, ts+b-qs] if strand == "+" else [ts+qe-b, ts+qe-a]
    return [qs+a-ts, qs+b-ts] if strand == "+" else [qe-(b-ts), qe-(a-ts)]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--lookup-dir", type=Path, required=True)
    p.add_argument("--reference-summary", type=Path, required=True)
    p.add_argument("--query-dataset", required=True)
    p.add_argument("--query-contig", required=True)
    p.add_argument("--starts", default="0,145000000,289000000")
    p.add_argument("--core-bases", type=int, default=100000)
    p.add_argument("--context-bases", type=int, default=10000)
    a = p.parse_args(); started = time.monotonic()
    if a.core_bases < 1 or a.context_bases < 0:
        raise ValueError("invalid window policy")
    metadata = {}
    def load(path):
        raw = path.read_bytes(); metadata[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    lookup = load(a.lookup_dir/"source-part-lookup.json")
    proof = load(a.lookup_dir/"receipt.json")
    if metadata[str(a.lookup_dir/"source-part-lookup.json")] != proof["lookup_sha256"]:
        raise ValueError("lookup changed")
    parts = {(v["dataset"],v["contig"]): (key,v) for key,v in lookup.items()}
    qkey = (a.query_dataset,a.query_contig); qid, qrow = parts[qkey]
    starts = [int(s) for s in a.starts.split(",")]
    if len(starts) != len(set(starts)) or any(not 0 <= s < qrow["length"] for s in starts):
        raise ValueError("invalid core starts")
    windows = {str(s): [max(0,s-a.context_bases),min(qrow["length"],s+a.core_bases+a.context_bases)] for s in starts}
    expected = {r["dataset"]:r["reference_paf_sha256"] for r in load(a.reference_summary)["datasets"]}
    scans = []
    def scan(dataset, wanted_name=None):
        path = a.workspace/f"runs/{dataset}_vs_ref/result.paf"
        before=path.stat();digest=hashlib.sha256();total=0;selected=0
        with path.open("rb") as stream:
            for raw in stream:
                digest.update(raw)
                if not raw.strip() or raw.startswith(b"#"):continue
                total += 1
                f=raw.decode("ascii").rstrip("\r\n").split("\t")
                if wanted_name is not None and f[0] != wanted_name:continue
                if int(f[1]) != parts[(dataset,f[0])][1]["length"]:raise ValueError("source length drift")
                if int(f[10]) < 1:raise ValueError("invalid span")
                # Diagnostic routing only. Entire unchanged PAF SHA binds even
                # unselected rows; this is not a replacement for strict admission.
                if int(f[9])/int(f[10]) < .90:continue
                selected+=1
                yield f
        after=path.stat()
        fence=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if fence(before)!=fence(after) or digest.hexdigest()!=expected[dataset]:raise ValueError("reference evidence changed")
        scans.append(dict(dataset=dataset,rows=total,selected=selected,sha256=digest.hexdigest()))
    regions={key:defaultdict(list) for key in windows};reference_lengths={}
    for f in scan(a.query_dataset,a.query_contig):
        chr=f[5];reference_lengths[chr]=int(f[6]);blocks=paired_geometry(f)
        for key,(lo,hi) in windows.items():
            if int(f[2])>=hi or int(f[3])<=lo:continue
            for block in blocks:
                r=project(block,f[4],lo,hi,True)
                if r:regions[key][chr].append([max(0,r[0]-a.context_bases),min(int(f[6]),r[1]+a.context_bases)])
    for key in regions:
        regions[key]={chr:merged(rows) for chr,rows in regions[key].items()}
    region_ends={key:{chr:[e for s,e in rows] for chr,rows in by_chr.items()} for key,by_chr in regions.items()}
    target={key:defaultdict(list) for key in windows}
    for dataset in expected:
        for f in scan(dataset):
            skey=dataset,f[0]
            if skey==qkey:continue  # no original contig against itself
            chr=f[5];lo,hi=int(f[7]),int(f[8]);overlaps={}
            for key,by_chr in regions.items():
                if chr not in by_chr:continue
                rows=by_chr[chr];index=bisect_right(region_ends[key][chr],lo);selected=[]
                while index<len(rows) and rows[index][0]<hi:
                    selected.append(rows[index]);index+=1
                if selected:overlaps[key]=selected
            if not overlaps:continue
            blocks=paired_geometry(f);part_id,row=parts[skey]
            for key,selected in overlaps.items():
                for block in blocks:
                    for lo,hi in selected:
                        r=project(block,f[4],lo,hi)
                        if r:target[key][part_id].append([max(0,r[0]-a.context_bases),min(row["length"],r[1]+a.context_bases)])
                # Bounded amortized compaction; never throw away disjoint spans.
                if len(target[key][part_id])>=2048:target[key][part_id]=merged(target[key][part_id])
    summary=[];plans=[]
    for key,by_part in target.items():
        by_part={pid:merged(rows) for pid,rows in by_part.items()}
        total=sum(e-s for rows in by_part.values() for s,e in rows)
        summary.append(dict(core_start=int(key),query_interval=windows[key],reference_region_bp=sum(e-s for rows in regions[key].values() for s,e in rows),
            reference_chromosomes=sorted(regions[key]),target_source_count=len(by_part),target_interval_count=sum(len(rows) for rows in by_part.values()),target_bp=total,
            target_whole_source_bp=sum(lookup[pid]["length"] for pid in by_part)))
        plans.append(dict(query_id=qid,query_interval=windows[key],reference_regions=regions[key],target_intervals=by_part))
    for path,sha in metadata.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError("metadata changed")
    Path("local-target-plan.json").write_text(json.dumps(plans)+"\n")
    report=dict(status="read_only_local_target_scope",windows=summary,scans=scans,metadata_sha256=metadata,
                seconds=time.monotonic()-started,scientific_acceptance=False,production_policy_changed=False,
                limitations="matched-site feasibility only, not unresolved-gap fallback, not global-target sensitivity equivalence; geometry includes ambiguous MAPQ")
    Path("summary.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report),flush=True)


if __name__=="__main__":main()
