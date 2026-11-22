"""Full/targeted supplemental Q0 A/B on frozen natural JM19 contigs.

Uses the actual regional planner, mapper and Q0 selector. The laboratory
initial-input adapter carries the original reference lengths/coordinates and
frozen subset PAFs; it does not manufacture or edit any alignment. Keep every
arm isolated; never adopt these subset manifests into a production workspace.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import shutil
import time
from unittest.mock import patch

from benchmark_regional_mapper_dispatch import digest, within
from lgz_core import q0_admission as admission, q0_preparation as prep
from lgz_core.common import read_fasta, stable_id
from lgz_core.q0_alignments import read_paf
from lgz_core.q0_catalog import ObservedSourcePairs, evidence_ref
from lgz_core.q0_paths import PairLink
from lgz_core.q0_regional_execution import RegionalExecutor
from lgz_core.q0_sources import Interval, SourceKey, split_source
from probe_q0_decision_frontier import compare, decision_frontier, member_geometry, timed


def base_input(panel, manifest):
    datasets = prep.table(panel, "metadata/datasets.tsv", ("dataset_name", "fasta_relpath"))
    seqs = {r["dataset_name"]:dict(read_fasta(within(panel,r["fasta_relpath"]))) for r in datasets}
    sources = {SourceKey(d,k):v for d,seq in seqs.items() for k,v in seq.items()}
    lengths = {d:{k:len(v) for k,v in seq.items()} for d,seq in seqs.items()}
    refs = json.loads((panel/"reference-lengths.json").read_text())
    if not prep.regional_enabled(refs, "asm10"):
        raise ValueError("frozen reference coordinates must use the real regional size policy")
    assignments = prep.table(panel, "metadata/chr_assignments.tsv", ("dataset_name","seq_name","assigned_chr_name"))
    desc = json.loads((panel/"base-alignments.json").read_text())
    parts, edges = {}, []
    for key, seq in sorted(sources.items()):
        source = split_source(key, seq)
        parts.update((p.segment_id,p) for p in source.segments)
        edges.extend(source.adjacencies)
    evidence, ref_hits, links = {}, defaultdict(list), []
    for d, sizes in lengths.items():
        rel = f"runs/{d}_vs_ref/result.paf"
        for hit in read_paf(within(panel,rel), artifact=rel, query_lengths=sizes, target_lengths=refs):
            ref_hits[SourceKey(d,hit.query_name)].append(hit)
            evidence[hit.evidence_id]=evidence_ref(hit)
    for row in desc:
        rel, q, t = row["paf"],row["query_dataset"],row["target_dataset"]
        for hit in read_paf(within(panel,rel),artifact=rel,query_lengths=lengths[q],target_lengths=lengths[t]):
            links.append(PairLink(hit,SourceKey(q,hit.query_name),SourceKey(t,hit.target_name)))
            evidence[hit.evidence_id]=evidence_ref(hit)
    for edge in edges:
        evidence[edge.adjacency_id]={"kind":"input_assembly_adjacency", **asdict(edge)}
    data=admission.EvidenceInput(sources,parts,refs,dict(ref_hits),tuple(links),tuple(edges),evidence,
                                 stable_id("wheat-control",manifest["artifacts"]))
    return data, assignments, desc


def context_inventory(original, data, frontier=None):
    rows = {}
    counts = Counter()
    def completed(executor, requests):
        for ordinal, request, (planned,native,reason) in original(executor,requests):
            retained = []
            for query, targets in planned:
                qsrc, qi = member_geometry(query.record(), data.parts)
                tgts = tuple(member_geometry(t.record(), data.parts) for t in sorted(targets, key=lambda w: w.window_id))
                raw = (query.window_id,tuple(sorted(t.window_id for t in targets)))
                key = (raw,query.cores)
                keep = frontier is None or any(span.intersection(i) for source, span in ((qsrc,qi),*tgts)
                                               for i in frontier.get(source,()))
                if keep:
                    retained.append((query,targets))
                    counts["scheduled"]+=1
                else:
                    counts["omitted"]+=1
                old = rows.setdefault(key,(qsrc,qi,tgts,keep))
                if old != (qsrc,qi,tgts,keep):
                    raise ValueError("same raw context has inconsistent geometry or selection")
            yield ordinal,request,(retained,native,reason)
    return completed, rows, counts


def missing_competitor_contexts(data, construction, omitted):
    """Flag potential omissions affecting same-pair exact proofs; not truth labels.

    Conservative intersection on either source axis. Only covers known planned
    contexts and same-pair locus competition, not other-pair admission/coverage.
    Uses observed links only to define which proposed cuts need closure.
    """
    by_pair=defaultdict(list)
    for context_id,(q,qi,targets,_kept) in omitted.items():
        for t,ti in targets:
            key=tuple(sorted((q,t)))
            by_pair[key].append((context_id,q,qi,t,ti))
    by_id={x.hit.evidence_id:x for x in data.pair_links}
    cuts=0
    incomplete=set()
    for result in construction.paths.values():
        if result.path is None:
            continue
        for join in result.path.joins:
            if join.kind!="sequence_overlap":
                continue
            cuts+=1
            for eid in join.evidence_ids:
                link=by_id[eid]
                q,t=link.query_source,link.target_source
                spans=defaultdict(list)
                spans[q].append(Interval(link.hit.query.start+link.query_offset,link.hit.query.end+link.query_offset))
                spans[t].append(Interval(link.hit.target.start+link.target_offset,link.hit.target.end+link.target_offset))
                for context,s,si,u,ui in by_pair.get(tuple(sorted((q,t))),()):
                    if (any(si.intersection(p) for p in spans[s]) or any(ui.intersection(p) for p in spans[u])):
                        incomplete.add((join.join_id,context))
    return {"exact_joins":cuts,"joins_with_unsearched_same_pair_contexts":len({j for j,_ in incomplete}),
            "additional_projected_plans":len({c for _,c in incomplete}),
            "potential_additional_raw_contexts":len({c[0] for _,c in incomplete})}


def run_arm(root, panel, manifest, data, assignments, desc, mapper, threads, frontier):
    for name,sha in manifest["artifacts"].items():
        src=within(panel,name); dest=root/name
        dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(src,dest)
        if digest(dest)!=sha:
            raise ValueError("frozen natural input changed")
    def initial(request):
        if request!=root:
            raise ValueError("natural panel cannot initialize another workspace")
        known=ObservedSourcePairs({k:len(s) for k,s in data.sources.items()})
        for link in data.pair_links:
            known.observe_alignment(link.hit,link.query_source,link.target_source)
        return data.sources,data.reference_lengths,assignments,{"minimap_preset":"asm10"},sorted(manifest["artifacts"]),desc,known
    completed, plans, counts=context_inventory(RegionalExecutor.completed,data,frontier)
    start=time.monotonic()
    with patch.object(prep,"_initial_inputs",initial), patch.object(RegionalExecutor,"completed",completed):
        ready=prep.prepare_evidence(root,threads=threads,minimap2=mapper)
    prep_seconds=time.monotonic()-start
    def input_fasta(path):
        if path==root/"reference-lengths.json":
            return [(name,range(length)) for name,length in data.reference_lengths.items()]
        return read_fasta(path)
    start=time.monotonic()
    with patch.object(admission,"read_fasta",input_fasta):
        observed=admission.load_evidence_input(root)
    built, select_seconds=timed(observed,allow_no_path=True)
    return built,observed,plans,{
        "prepare_seconds":prep_seconds,"load_and_select_seconds":time.monotonic()-start,
        "select_seconds":select_seconds,"dispatch":dict(counts),"ready_catalog":ready["catalog"],
        "task_kinds":dict(Counter(r["kind"] for r in observed.catalog["supplementary_alignments"])),
        "unique_projection_plans":len(plans),"unique_raw_contexts":len({k[0] for k in plans}),"reference_loci_chromosomes":len({h.target_name for hits in data.reference_hits.values() for h in hits}),
        "sequence_sha256":{} if built is None else {k:sha256(v.encode("ascii")).hexdigest() for k,v in built.records.items()}}


def panel_run(panel, out, mapper, threads):
    manifest=json.loads((panel/"panel.json").read_text())
    if manifest["panel"]!=panel.name or out.exists() or out.is_relative_to(panel) or panel.is_relative_to(out):
        raise ValueError("mismatched panel or not isolated")
    for name,sha in manifest["artifacts"].items():
        if digest(within(panel,name))!=sha:
            raise ValueError("frozen panel manifest failed input validation")
    start=time.monotonic()
    base_data,assignments,desc=base_input(panel,manifest)
    base,base_seconds=timed(base_data,allow_no_path=True)
    elapsed=time.monotonic()-start
    frontier=None if base is None else decision_frontier(base,100_000)
    out.mkdir()
    report={"panel":manifest["panel"],"members":manifest["members"],"source_bases":manifest["source_bases"],
            "input":base_data.input_fingerprint,"base_load_select_seconds":elapsed,"base_select_seconds":base_seconds,
            "limitations":["selected natural contigs, both assemblies, all original reference placements for selected contigs",
                            "not full JM19 target/competitor universe or downstream LGZ acceptance",
                            "no production ready artifact or policy change"]}
    def run(mode,wanted):
        result=run_arm(out/mode,panel,manifest,base_data,assignments,desc,mapper,threads,wanted)
        print(f"{panel.name}: completed {mode}",flush=True)
        return result
    a,_,all_plans,report["full"]=run("full",None)
    report["without_supplement"]= "no_path" if base is None else (compare(a,base) if a else "full_no_path")
    if frontier is not None:
        b,bdata,scoped,report["targeted"]=run("targeted",frontier)
        report["targeted_vs_full"]="no_path" if b is None else (compare(a,b) if a else "full_no_path")
        if b is not None:
            omitted={key:r for key,r in scoped.items() if not r[-1]}
            not_rerouted={key:r for key,r in all_plans.items() if key not in scoped}
            report["runtime_known_competitor_audit"]=missing_competitor_contexts(bdata,b,omitted)
            report["oracle_competitor_audit"]=missing_competitor_contexts(bdata,b,{**omitted,**not_rerouted})
            report["full_contexts_not_proposed_in_targeted"]=len(not_rerouted)
    else:
        report["targeted"]="no_base_path_full_discovery_required"
    (out/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--mapper",required=True)
    p.add_argument("--threads",type=int,choices=(2,4,6),default=6)
    a=p.parse_args()
    panel_run(a.panel.resolve(strict=True),a.output.resolve(),a.mapper,a.threads)


if __name__=="__main__":
    main()
