"""Three-group cached inversion-preserving trial; private outputs, no mapper."""
import argparse,ast,gc,gzip,json,pickle,subprocess,multiprocessing as mp
from collections import Counter,defaultdict
from pathlib import Path
from time import monotonic
from unittest.mock import patch
from lgz_core import q0_admission as adm,q0_paths as paths
from lgz_core.q0_sources import SourceKey,SourceSegment,Interval
from wheat_inversion_preserving_readonly import candidates,merge_frozen
from wheat_selection_checkpoint import encode,decode
from wheat_reference_funnel_readonly import digest,write
from wheat_local_chain_selection_readonly import checked_pickle,reference_spine
from wheat_continuity_gap_rescue_readonly import load_rows,need
from wheat_continuity_path_refinement_readonly import metrics,refs
from wheat_top_chain_locus_loop_readonly import save_path,mapped_incumbent
from wheat_continuous_dominant_admission_readonly import old_routes,risk
from wheat_top_chain_cross_readonly import cross_source_overlaps
from wheat_sparse_pair_graph_readonly import sparse_constructor
from wheat_indexed_anchor_support_readonly import AnchorSupportIndex,indexed_native
from wheat_locus_guard_readonly import replace_coverage
from wheat_group_evidence_readonly import load_links
import wheat_continuous_dominant_admission_readonly as original

GROUPS=("1A","3B","3D")
LOOKUP={}


def task(args):
    group,row=args;src=SourceKey(*row["source"])
    keys=[k for k,aa,hh in row["groups"] if k[0]==group and adm._size(Interval(a[0],a[1]) for a in aa)>=100000]
    if not keys:return None
    part_id,meta=LOOKUP[src]
    need(row["length"]==meta["length"] and row["sequence_sha256"]==meta["sequence_sha256"],"cached source identity changed")
    groups={};high={}
    for k,aa,hh in row["groups"]:
        groups[tuple(k)]=tuple(adm.ReferenceAnchor(Interval(a,b),Interval(c,d),e) for a,b,c,d,e in aa)
        high[tuple(k)]=tuple(Interval(a,b) for a,b in hh)
    part=SourceSegment(part_id,src,Interval(0,row["length"]),row["sequence_sha256"],0,"start","end")
    ps,audit=candidates(part,groups,high,group)
    return [encode(p) for p in ps],{"source":row["source"],**audit}


def stage_compatible(saved, current, owner):
    """Only the documented replay-wrapper repair may reuse this completed stage."""
    if saved == current:
        return True
    if {k:v for k,v in saved.items() if k != "runner_sha256"} != {k:v for k,v in current.items() if k != "runner_sha256"}:
        return False
    previous = owner / "wheat_inversion_cached_loop.43136988.py"
    if not previous.exists() or digest(previous) != saved["runner_sha256"]:
        return False
    def task_ast(file):
        tree = ast.parse(file.read_text())
        return ast.dump(next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "task"))
    return task_ast(previous) == task_ast(Path(__file__))


def run(base,owner,workers):
    global LOOKUP
    began=monotonic();source=base/"q0-continuity-20261126.RAbGvNba";cross=base/"q0-top-chain-cross-20261127.XLaIRQyk"
    indexed=base/"q0-continuity-indexed-20261126.CgydRhOS";phase1=base/"q0-top-chain-locus-20261127.CTotPSFG"
    old=old_routes(source/"old-grt-q-segments.tsv")
    lookup=original.frozen.checked(base/"q0-source-part-lookup-20261121-1600/source-part-lookup.json",original.frozen.LOOK)
    LOOKUP={SourceKey(v["dataset"],v["contig"]):(k,v) for k,v in lookup.items()}
    cross_report=json.loads((cross/"cross-validation.json").read_text())
    need(digest(cross/"cross-validation.json")=="70efc3daf077fab950cbb2977b011130072aa3396feb44a074b2297ef8fec2ea","cross report changed")
    inputs={g:(source/"screened-reference-anchors.jsonl.gz" if g=="1A" else cross/(g+"-screened-anchors.jsonl.gz")) for g in GROUPS}
    identity={"policy_sha256":digest(Path(__file__).with_name("wheat_inversion_preserving_readonly.py")),"runner_sha256":digest(Path(__file__)),"screened_inputs":{g:{"path":str(f),"sha256":digest(f)} for g,f in inputs.items()},"reference_padding_bp":100000}
    need(identity["screened_inputs"]["1A"]["sha256"]==json.loads((source/"continuity-admission.json").read_text())["outputs"][inputs["1A"].name]["sha256"],"1A cache changed")
    # Cross screened rows were produced by the completed immutable cross job;
    # bind actual content on first use, rather than pretending a previous seal exists.
    write(owner/"input-binding.json",identity)
    all_admission={};results={};selected={};allps={};oldpaths=None
    for group in GROUPS:
        stamp=monotonic();receipt=owner/(group+"-admission.json");output=owner/(group+"-placements.jsonl.gz")
        if receipt.exists():
            saved=json.loads(receipt.read_text());need(stage_compatible(saved["identity"],identity,owner),"admission identity changed");need(digest(output)==saved["placements_sha256"],"admission output changed");new=load_rows(output)
        else:
            def tasks():
                with gzip.open(inputs[group],"rt") as f:
                    for line in f:yield group,json.loads(line)
            new=[];audits=[];count=0;last=monotonic()
            with mp.get_context("fork").Pool(workers) as pool:
                for result in pool.imap_unordered(task,tasks(),chunksize=4):
                    count+=1
                    if result:
                        ps,audit=result;new.extend(decode(p) for p in ps);audits.append(audit)
                    if monotonic()-last>30:print("INVERSION_ADMISSION_PROGRESS",group,count,len(new),round(monotonic()-stamp,1),flush=True);last=monotonic()
            new.sort(key=lambda p:(p.source,p.interval,p.orientation,p.placement_id))
            with gzip.open(output,"wt") as f:
                for p in new:f.write(json.dumps(encode(p))+"\n")
            saved={"identity":identity,"placements_sha256":digest(output),"placements":len(new),"reference_bp":adm._size(a.reference for p in new for a in p.reference_blocks),"sources_processed":count,"source_audit":sorted(audits,key=lambda x:x["source"]),"elapsed_s":monotonic()-stamp}
            write(receipt,saved)
        all_admission[group]={k:v for k,v in saved.items() if k!="source_audit"}
        print("INVERSION_ADMISSION_DONE",group,len(new),saved["reference_bp"],flush=True)
        # Native baseline remains frozen; the trial candidate pool is new.
        if group=="1A":
            seal=json.loads((indexed/"continuous-graph.json").read_text());baseline_graph=checked_pickle(indexed/"continuous-graph.pickle",seal["sha256"])
            old_result=json.loads((indexed/"continuity-final-selection.json").read_text())["results"]["validated_initial_backbone"]
            pathfile=indexed/old_result["path_file"];need(digest(pathfile)==old_result["path_sha256"],"1A baseline changed")
            with gzip.open(pathfile,"rt") as f:baseline=decode(json.load(f))
            frozen=load_rows(source/"frozen-placements.jsonl.gz")
            cache_owner=phase1;cache_name="loop-selected-links"
        else:
            seal=json.loads((cross/(group+"-frozen-graph.json")).read_text());baseline_graph=checked_pickle(cross/(group+"-frozen-graph.pickle"),seal["sha256"])
            # Read the frozen path checkpoint through its existing content verifier.
            from compare_wheat_local_only_paths import load_arm
            if oldpaths is None:
                _,_,_,oldpaths,_=load_arm(base/"q0-whole-local-maps.soHq9Z6J","d23a49af479b6c9b81916518e8034d4044ea31b5c97229c5d0ce1624138fc9d4","whole-wheat-local-supplement-v1")
            baseline=oldpaths[group];frozen=list(baseline_graph.placements.values());cache_owner=cross;cache_name="cross-links"
        replay=baseline_graph._score_candidate(baseline.nodes,baseline.joins)
        need(replay and replay.slices==baseline.slices and replay.score==baseline.score,"frozen physical path not reproduced")
        ps,removed=merge_frozen(frozen,new);allps[group]=ps
        graphfile=owner/(group+"-native-graph.pickle")
        if graphfile.with_suffix(".json").exists():
            gs=json.loads(graphfile.with_suffix(".json").read_text())
            need(stage_compatible(gs["identity"],identity,owner),"native graph scientific identity changed")
            need(gs["placements_sha256"]==digest(output) and gs["frozen_graph_sha256"]==seal["sha256"],"native graph input changed")
            graph=checked_pickle(graphfile,gs["sha256"])
            need({p.placement_id:p for p in ps}==graph.placements,"native graph placement contents changed")
            print("INVERSION_NATIVE_GRAPH_REUSED",group,gs["sha256"],flush=True)
        else:
            sources={p.source for p in ps};cache_seal=json.loads((cache_owner/(cache_name+".json")).read_text())
            available={SourceKey(*s) for s in cache_seal["binding"]["sources"]}
            missing=sources-available
            print("INVERSION_PAIR_CACHE_SCOPE",group,"sources",len(sources),"missing",len(missing),flush=True)
            if missing:
                # Existing completed evidence only, not a scientific/evidence subset.
                links=load_links(base,owner,sources,group_label=group)
            else:
                links=checked_pickle(cache_owner/(cache_name+".pickle"),cache_seal["sha256"])
                links=[v for v in links if v.query_source in sources and v.target_source in sources]
            stats=Counter();ctor,_,_=sparse_constructor(stats)
            with patch.object(paths.PathGraph,"__init__",ctor):
                graph=paths.PathGraph(ps,links,(),paths.PathPolicy(),first_request=True,progress=lambda s:print("INVERSION_GRAPH",group,s,flush=True))
            del links;gc.collect()
            # Persist only native graph, never the dynamic diagnostic coverage class.
            graphfile=owner/(group+"-native-graph.pickle")
            with graphfile.open("wb") as f:pickle.dump(graph,f,protocol=5)
            write(graphfile.with_suffix(".json"),{"sha256":digest(graphfile),"identity":identity,"placements_sha256":digest(output),"frozen_graph_sha256":seal["sha256"],"pair_cache_sha256":cache_seal["sha256"] if not missing else None,"missing_pair_cache_sources":sorted([s.dataset,s.contig] for s in missing)})
        guard=replace_coverage(graph,100000,progress=lambda s:print("INVERSION_LOCUS",group,s,flush=True))
        spine,diag=reference_spine(graph)
        missing_incumbent_nodes=sorted(set(baseline.nodes)-set(graph.placements))
        incumbent=None if missing_incumbent_nodes else mapped_incumbent(graph,baseline)
        valid=[p for p in (spine,incumbent) if p and p.score>=baseline.score and adm._size(refs(p,graph))>=adm._size(refs(baseline,baseline_graph))]
        need(valid,"no valid candidate meeting frozen score/reference lower bounds")
        winner=min(valid,key=graph.rank);selected[group]=winner
        row=save_path(owner,group+"-inversion-100kb",winner,graph,old,baseline,baseline_graph)
        row.update(guard=guard,spine_diagnostics=diag,frozen_metrics=metrics(replay,baseline_graph),admission_reference_bp=adm._size(a.reference for p in ps for a in p.reference_blocks),admitted_placements=len(ps),opposite_frozen_candidates_removed=removed,incumbent_replayable=incumbent is not None,missing_incumbent_nodes=missing_incumbent_nodes,elapsed_s=monotonic()-stamp)
        results[group]=row
        write(owner/"inversion-progress.json",{"results":results,"mapper_calls":0})
        print("INVERSION_GROUP_DONE",group,json.dumps(row["metrics"]),"conflicts",row["risk"]["conflict_flags"],flush=True)
        del graph,baseline_graph,frozen,ps;gc.collect()
    overlaps=cross_source_overlaps(selected)
    admission_conflicts={}
    for g,ps in allps.items():
        flags=[]
        for p in ps:
            _,ss=risk(p,old)
            for category,ivs in ss.items():
                if category!="same_group_same_orientation" and ivs:flags.append({"placement_id":p.placement_id,"source":[p.source.dataset,p.source.contig],"category":category,"source_bp":adm._size(ivs)})
        admission_conflicts[g]=flags
    passed=not overlaps and not any(admission_conflicts.values()) and all(not r["risk"]["conflict_flags"] and not r["reference_order_flags"] and r["guard"]["union_audit"]["rejected_large_map_unions"]==0 for r in results.values())
    write(owner/"inversion-validation.json",{"schema":"wheat_inversion_preserving_three_group_v1","identity":identity,"admission":all_admission,"results":results,"admission_conflicts":admission_conflicts,"cross_group_source_conflicts":overlaps,"three_group_policy_checks_passed":passed,"mapper_calls":0,"formal_workspace_modified":False,"formal_q0_lgz":"HOLD","elapsed_s":monotonic()-began})
    print("INVERSION_VALIDATION_DONE",passed,round(monotonic()-began,1),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("base",type=Path);p.add_argument("owner",type=Path);p.add_argument("--workers",type=int,default=4);a=p.parse_args()
    need(a.owner.resolve().parent==a.base.resolve() and a.owner.stat().st_mode&0o077==0,"private sibling owner required")
    with patch.object(subprocess,"Popen",side_effect=RuntimeError("external programs and mapper forbidden")),indexed_native(AnchorSupportIndex()):run(a.base,a.owner,a.workers)
