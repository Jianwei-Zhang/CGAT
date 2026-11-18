"""Export a portable, output-bound audit for completed incident-routed leaves.

Not the initial-reference alignment policy schema and not whole-workflow QC.
Source FASTA identities are explicitly recorded from completed checkpoints;
current PAF/log/receipt bytes and executed-code bindings are verified here.
Run on a compute node after all planned routed leaves have committed.
"""
import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from routing_resume_support import RoutingBindings, OverrideError


def compact_decisions(receipt, contract):
    decisions = receipt["decisions"]
    names = [row["query"] for row in decisions]
    if (len(names) != len(set(names)) or len(names) != receipt["query_count"]
            or set(names) != set(receipt["effective_sources"])
            or any(type(row["length"]) is not int or row["length"] <= 0 for row in decisions)
            or sum(row["length"] for row in decisions) != receipt["query_bases"]):
        raise OverrideError("routing record inventory is incomplete")
    groups = {row["cache_key"]: row for row in receipt["group_evidence"]}
    if len(groups) != len(receipt["group_evidence"]):
        raise OverrideError("ambiguous routing group evidence")
    approximate, details = 0, []
    for row in decisions:
        fraction = row.get("effective_filter", row["filter"])
        source = groups.get(receipt["effective_sources"][row["query"]], {})
        identity = source.get("identity", {})
        if (source.get("status") != "success" or type(source.get("exit_code")) is not int or source.get("exit_code") != 0
                or source.get("cache_key") != contract.fingerprint(identity)
                or identity.get("phase") != "whole_records"
                or identity.get("filter") != fraction
                or identity.get("queries", {}).get(row["query"]) != row["length"]
                or identity.get("preset") != receipt["preset"]
                or identity.get("target_sha256") != receipt["target_sha256"]
                or identity.get("tool_sha256") != receipt["tool_sha256"]):
            raise OverrideError("effective record source is not a matching complete whole mapping")
        approximate += fraction is not None
        if fraction is not None or row["length"] >= receipt["policy"]["long_bases"]:
            item = {"query":row["query"], "length":row["length"], "effective_filter":fraction,
                    "reason":row["reason"], "calibration_scope":row.get("calibration_scope"),
                    "global_agreement_guaranteed":False}
            for key in ("fallback_reason", "candidate_coverage"):
                if key in row: item[key] = row[key]
            # Do not export private absolute attempt paths from failure text.
            item["calibration_cases"] = [
                {k:case[k] for k in ("filter", "passed", "positions", "metrics") if k in case}
                for case in row.get("cases", [])]
            details.append(item)
    return {"query_count":len(names), "query_bases":receipt["query_bases"],
            "approximate_record_count":approximate, "ordinary_record_count":len(names)-approximate,
            "long_or_approximate_records":details}


def build_audit(bindings, marker_directory, contract):
    bindings.verify()
    rows = []
    for rel, override in sorted(bindings.rows.items()):
        marker_path = Path(marker_directory) / (contract.fingerprint(rel) + ".json")
        marker = json.loads(marker_path.read_text())
        if marker.get("status") != "success" or marker.get("command") != rel:
            raise OverrideError("routed leaf is not committed")
        if marker["inputs"].get("execution_override") != bindings.proof(rel):
            raise OverrideError("leaf does not bind the actual execution override")
        task = SimpleNamespace(command=bindings.work/rel, unit_id=override["unit_id"])
        receipt_identity = bindings.receipt_identity(task, marker["inputs"])
        expected = []
        for name in ("result.paf", "stderr.log", "stdout.log"):
            path = task.command.parent/name
            if path.is_symlink(): raise OverrideError("linked routed output")
            expected.append(contract.file_identity(path, relative_to=bindings.work))
        expected.append(receipt_identity)
        if marker["outputs"] != expected:
            raise OverrideError("routed leaf output manifest changed")
        receipt = json.loads(Path(override["receipt"]).read_text())
        summary = compact_decisions(receipt, contract)
        lengths = {row["query"]:row["length"] for row in receipt["decisions"]}
        with (task.command.parent/"result.paf").open() as handle:
            for line in handle:
                fields = line.split("\t")
                if fields[0] not in lengths or int(fields[1]) != lengths[fields[0]]:
                    raise OverrideError("final PAF query inventory differs from the receipt")
        files = marker["inputs"]["files"]
        rows.append({"unit_id":override["unit_id"],
            "result_paf":expected[0], "routing_receipt_sha256":receipt_identity["sha256"],
            "native_command_sha256":override["native_command_sha256"],
            "executed_script_sha256":override["script"]["sha256"],
            "source_fasta_identity_basis":"recorded_completed_checkpoint_not_rehashed_by_exporter",
            "target":{"sha256":files[1]["sha256"]}, "query":{"sha256":files[2]["sha256"]}, "tool_sha256":receipt["tool_sha256"],
            "preset":receipt["preset"], "policy":receipt["policy"],
            "implementation_sha256":receipt["dependencies"], "records":summary})
    bindings.verify()
    return {"schema":"cgat_incident_q0_cross_provenance_v1",
        "scope":"planned_routed_q0_cross_leaves_only",
        "complete_within_scope":True, "certifies_whole_workflow":False,
        "initial_reference_policy":False, "self_alignment_policy":False,
        "accuracy_claim":"window calibration is not a whole-query accuracy guarantee",
        "plan_sha256":bindings.plan_hash, "alignment_count":len(rows), "alignments":rows}


def publish(report, output, contract):
    output = Path(output)
    if output.is_symlink(): raise OverrideError("linked audit output")
    if output.exists():
        if json.loads(output.read_text()) != report:
            raise OverrideError("preserve previous audit; its evidence differs")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    contract.atomic_write_json(output, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True); work=root/"gpm_server"
    sys.path.insert(0, str(work/".prepare_lib/tools"))
    import run_orchestration as contract
    bindings=RoutingBindings(work,root/"routing-resume-staged-20261119/routing-plan.json",contract)
    report=build_audit(bindings,root/"memory-resume-20261118/cross-leaf-checkpoints",contract)
    output=root/"comparison-audit/q0-routing-provenance.json"
    if output.parent.is_symlink() or output.resolve().is_relative_to(work.resolve()):
        raise OverrideError("audit destination must not alias the analysis workspace")
    publish(report,output,contract)
    print("Q0_ROUTING_AUDIT", json.dumps({"path":str(output),"sha256":contract.sha256_file(output),
                                       "alignments":report["alignment_count"]}))


if __name__ == "__main__":
    main()
