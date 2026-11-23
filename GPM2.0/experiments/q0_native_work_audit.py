"""Read-only audit of completed whole-map Q0 work. Run against a trusted matching runtime."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys


def summarize(catalog, construction, outputs):
    placements = {p["placement_id"]: p for p in construction["placements"]}
    selected, alternatives = set(), set()
    for search in construction["searches"].values():
        for path, used in [(search["path"], selected), *((p, alternatives) for p in search["alternatives"])]:
            if path is None:
                continue
            for part in path["slices"]:
                used.update(placements[part["placement_id"]]["evidence_ids"])
            for join in path["joins"]:
                used.update(join["evidence_ids"])
    cited = defaultdict(Counter)
    for eid, evidence in construction["evidence"].items():
        artifact = evidence.get("artifact")
        if artifact:
            role = "selected" if eid in selected else "alternative_only" if eid in alternatives else "other_decision"
            cited[artifact][role] += 1
    maps, contexts = {}, defaultdict(Counter)
    for task in catalog["supplementary_alignments"]:
        if task["kind"] == "regional_discovery":
            continue  # Projected windows are not whole query/target contexts.
        key, paf = task["task_id"], task["paf"]
        if key not in maps:
            maps[key] = {"logical_uses": [], "paf_sha256": outputs[paf]["sha256"],
                         "paf_bytes": outputs[paf]["size"], "cited_rows": dict(cited[paf])}
            # Weak-seed uses a distinct mapper profile; never pool those query contexts.
            if task["kind"] == "candidate_chr" or task["kind"] in ("partial_source_discovery", "unplaced_discovery"):
                for q in task["query_ids"]:
                    contexts[q][tuple(task["target_ids"])] += 1
        maps[key]["logical_uses"].append([task["kind"], task["request"].get("chromosome")])
    scope = catalog.get("supplement_scope", {})
    return {"scope": scope.get("effective", "full"), "acceptance": construction.get("supplement_acceptance"),
            "completed_native_requests": sum(len(m["logical_uses"]) for m in maps.values()),
            "distinct_completed_native_maps": len(maps), "completed_maps": maps,
            "skipped_native_candidate_requests": scope.get("native_candidate_stops", []),
            "ordinary_whole_queries_repeated_with_identical_targets": sum(n-1 for c in contexts.values() for n in c.values()),
            "ordinary_whole_queries_used_with_different_targets": sum(len(c)>1 for c in contexts.values()),
            "regional_task_records": sum(t["kind"] == "regional_discovery" for t in catalog["supplementary_alignments"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--tools", type=Path, default=Path(__file__).resolve().parents[1]/"server/tools",
                        help="trusted producer revision server/tools (never auto-import from workspaces)")
    args=parser.parse_args(); root=args.workspace.resolve(); sys.path.insert(0,str(args.tools.resolve()))
    from lgz_core import q0_preparation as prep, q0_publication as pub
    from lgz_core.common import sha256_file, stable_id
    m=prep.load_verified_evidence(root); freeze=pub.validate_prepared_q0(root)
    p=lambda rel:prep.artifact_path(root,rel)
    cat=prep.json_file(p(m["catalog"])); construction=prep.json_file(p(pub.SELECTION))["construction"]
    if (construction["ready_manifest_identity"]!=stable_id("q0-ready-evidence",m)
            or sha256_file(p(pub.SELECTION))!=freeze["selection_sha256"]):
        raise ValueError("selection and ready manifest are from different generations")
    result=summarize(cat,construction,{r["path"]:r for r in m["outputs"]})
    if prep.load_verified_evidence(root) != m or sha256_file(p(pub.SELECTION)) != freeze["selection_sha256"]:
        raise ValueError("ready or selection generation changed during audit")
    result.update(builder=m["builder"], input_fingerprint=m["input_fingerprint"], selection_sha256=freeze["selection_sha256"])
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
