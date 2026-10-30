#!/usr/bin/env python3
"""Read-only positive/negative checks over an ACTUAL completed recovery fixture.

Maintainer-only, PLAN ONLY by default. No mapping, fixture generation, compiler,
job, source mutation or customer configuration. Mock reports are not accepted as
replacement scientific execution evidence; run this on retained native controls.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path

import native_chain_state as nst
import recovery_publication as rp
import selective_reference_alignment as sr
import windowed_alignment as wa


def variants(original):
    def mutate(name,change):
        result=deepcopy(original);change(result);return name,result
    def leaf(report):
        return next(row for part in report["parts"] for row in part["attempts"] if "recovery" in row)
    return [
        mutate("masked_original_abort",lambda r:r["original_native"]["execution"].update(returncode=0)),
        mutate("failed_partial_reuse",lambda r:r.update(partial_PAF_reused=True)),
        mutate("unfinished_part",lambda r:r["parts"][0].update(status="running")),
        mutate("reordered_root_queries",lambda r:r["parts"][0]["attempts"][0]["queries"].reverse()),
        mutate("missing_tree_branch",lambda r:r["parts"][0]["attempts"].pop()),
        mutate("missing_empty_query_cell",lambda r:r["combination"]["rows_by_query"].pop(next(q for q,n in r["combination"]["rows_by_query"].items() if n==0))),
        mutate("group_abort_reused_for_singleton",lambda r:leaf(r).update(reused_original_assertion=True)),
        mutate("asserting_leaf_called_native_success",lambda r:leaf(r).update(status="native_success")),
        mutate("changed_proof_hash",lambda r:leaf(r)["recovery"].update(publication_proof_sha256="0"*64)),
        mutate("foreign_global_query_identity",lambda r:r["query"].update(sha256="0"*64)),
        mutate("changed_index_catalog",lambda r:r.update(index_catalog_sha256="0"*64)),
        mutate("missing_private_cell_replacement",lambda r:r["native_evaluation_combination"]["evaluated_replacements"].pop()),
        mutate("changed_private_assembly",lambda r:r["native_evaluation"].update(sha256="0"*64)),
        mutate("unsupported_private_cell_counts",lambda r:r["native_evaluation_combination"].update(native_cells=0)),
    ]


def experiment(args):
    root=args.result_dir.resolve();out=args.out.resolve()
    if out.exists() or not out.parent.is_dir() or root==out or root in out.parents or out in root.parents:
        raise wa.ExperimentError("publication controls need a fresh output outside the retained fixture")
    path=root/"selective-reference.json"
    if path.stat().st_size>nst.MAX_STATE_BYTES:
        raise wa.ExperimentError("fixture report exceeds metadata budget")
    original=json.loads(path.read_bytes())
    before={p.relative_to(root).as_posix():wa.fingerprint(p) for p in root.rglob("*") if p.is_file()}
    bundle=nst.validate_bundle(args.native_state_bundle)
    out.mkdir(mode=0o700)
    result={"status":"running","scope":"read_only_real_fixture_publication_contract_not_customer_acceptance",
        "fixture_report_sha256":wa.sha256(path),"validator_sha256":wa.sha256(Path(rp.__file__)),
        "harness_sha256":wa.sha256(Path(__file__)),"helper":bundle,"negative_controls":[],
        "commands_started":False,"fixture_modified":False,"production_ready":False}
    try:
        result["positive"]=rp.admit(original,root,bundle=bundle,row_validator=sr.validate_row)
        for name,report in variants(original):
            try:
                rp.admit(report,root,bundle=bundle,row_validator=sr.validate_row)
            except wa.ExperimentError as exc:
                result["negative_controls"].append({"case":name,"refused":True,"reason":str(exc)})
            else:
                raise wa.ExperimentError("publication accepted an invalid control: "+name)
        after={p.relative_to(root).as_posix():wa.fingerprint(p) for p in root.rglob("*") if p.is_file()}
        if before!=after:
            raise wa.ExperimentError("retained recovery fixture changed during read-only controls")
        result.update(status="all_publication_contract_controls_passed",negative_count=len(result["negative_controls"]))
    except BaseException as exc:
        result.update(status="refused_or_failed",error=repr(exc));raise
    finally:
        wa.write_json(out/"publication-controls.json",result)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--native-state-bundle",type=Path,default=None)
    parser.add_argument("--execute",action="store_true")
    args=parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status":"plan_only","no_files_or_commands_started":True,"production_ready":False}))
        return 0
    result=experiment(args)
    print(json.dumps({"status":result["status"],"negative_count":result["negative_count"],"fixture_modified":False}))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
