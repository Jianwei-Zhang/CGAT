"""Explicit incident-only self seed profile; never edit assignment-bound inputs.

This execution layer requires a separately staged immutable profile and the
normal owning controller/workspace lock. It is NOT wired into run_all. Selected
whole-record batches get new keys and receipts. Native batches keep their keys;
the controller must invoke profile-aware merging after ANY batch of the group.
"""
import argparse
import copy
import importlib
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile

import full_self_seed_pilot as pilot

SCHEMA = "incident_self_seed_profile_v1"
POLICY = {"scope": "q0_self_single_whole_record", "minimum_query_bases": 100_000_000,
          "seed_fraction": "0.001", "mapper_timeout_seconds": None,
          "native_flags_unchanged": True}
OUTPUTS = ("raw.paf", "result.paf", "stderr.log")
RECEIPT = "self-profile-receipt.json"


def identity(value):
    import hashlib
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def effective_manifest(native, selected, profile_sha):
    if native.get("version") != 1 or not native.get("batches") or selected != sorted(set(selected)):
        raise ValueError("invalid self profile batch selection")
    result = copy.deepcopy(native)
    for index in selected:
        if type(index) is not int or not 0 <= index < len(native["batches"]):
            raise ValueError("invalid profile batch index")
        batch = native["batches"][index]
        if len(batch["entries"]) != 1 or batch["entries"][0]["length"] < POLICY["minimum_query_bases"]:
            raise ValueError("only single whole long queries may use the self seed profile")
        result["batches"][index]["key"] = identity({"schema": SCHEMA, "profile_sha256": profile_sha,
                                                      "native_key": batch["key"], "batch_index": index})
    return result


def index_key(manifest):
    return identity({"tool": manifest["identities"]["tool"], "target": manifest["identities"]["target"],
                     "preset": manifest["preset"], "index_limit": "8G"})


def mapping_command(manifest, batch, tool, index, policy=None):
    policy = POLICY if policy is None else policy
    return [str(tool), "-c", "-x", manifest["preset"], "-X", "--no-hash-name",
            "-m", str(manifest["min_chain_score"]), "-n", str(manifest["minimizers"]),
            "-t", "1", "-f", policy["seed_fraction"], str(index), batch["query"]]


class Profile:
    def __init__(self, path):
        self.path = Path(path).resolve(strict=True)
        self.sha = pilot.digest(self.path)
        self.spec = json.loads(self.path.read_text())
        self.policy = self.spec.get("policy", {})
        if (self.spec.get("schema") != SCHEMA or self.policy.get("seed_fraction") not in ("0.001", "0.005")
                or self.policy != {**POLICY, "seed_fraction": self.policy.get("seed_fraction")}):
            raise ValueError("unsupported self execution profile")
        self.work = Path(self.spec["workspace"]).resolve(strict=True)
        if self.path == self.work or self.work in self.path.parents:
            raise ValueError("self profile must be isolated outside the workspace")
        self.source = Path(self.spec["native_manifest"]["path"]).resolve(strict=True)
        self.source.relative_to(self.work)
        if self.source.name != "self_batch_manifest.json" or not self.source.parent.name.endswith("_vs_self"):
            raise ValueError("not a self operation manifest")
        self.verify()
        self.native = json.loads(self.source.read_text())
        lengths = self.native["target_lengths"]
        if not lengths or any(type(n) is not int or n < 1 for n in lengths.values()) or sum(lengths.values()) >= 8_000_000_000:
            raise ValueError("invalid or multipart target in self profile")
        self.selected = self.spec["selected_batches"]
        self.manifest = effective_manifest(self.native, self.selected, self.sha)
        op = self.source.parent
        for field, expected in (("output", op / "result.paf"), ("name_map", op / "self_name_map.tsv"),
                                ("restore", op / "restore_self_paf.py")):
            if Path(self.native[field]).resolve() != expected.resolve():
                raise ValueError("self operation path differs: " + field)
        for i, batch in enumerate(self.native["batches"]):
            directory = op / "batches" / ("batch-%05d" % i)
            if Path(batch["directory"]).resolve() != directory.resolve() or Path(batch["query"]).resolve() != (directory / "query.fa").resolve():
                raise ValueError("self batch directory/query differs")
        for field in ("target", "query", "cache"):
            Path(self.native[field]).resolve().relative_to(op)
        helper_path = self.work / ".prepare_lib/tools/self_alignment_batches.py"
        if Path(self.spec["dependencies"]["helper"]["path"]).resolve() != helper_path.resolve():
            raise ValueError("profile does not bind workspace helper")
        sys.path.insert(0, str(helper_path.parent))
        self.helper = importlib.import_module("self_alignment_batches")
        self.contract = importlib.import_module("run_orchestration")
        if Path(self.helper.__file__).resolve() != helper_path.resolve():
            raise ValueError("wrong self helper imported")
        if Path(self.contract.__file__).resolve() != Path(self.spec["dependencies"]["contract"]["path"]).resolve():
            raise ValueError("wrong PAF contract imported")

    def verify(self):
        digest = self.contract.sha256_file if hasattr(self, "contract") else pilot.digest
        if digest(self.path) != self.sha:
            raise ValueError("self profile changed")
        if set(self.spec["dependencies"]) != {"runtime", "helper", "contract", "pilot"}:
            raise ValueError("unexpected self profile dependency inventory")
        rows = {"manifest": self.spec["native_manifest"], **self.spec["dependencies"]}
        if Path(rows["runtime"]["path"]).resolve() != Path(__file__).resolve() or Path(rows["pilot"]["path"]).resolve() != Path(pilot.__file__).resolve():
            raise ValueError("unbound self executor")
        for row in rows.values():
            if digest(Path(row["path"])) != row["sha256"]:
                raise ValueError("self profile source/dependency changed: " + row["path"])

    def validate_batch(self, index):
        batch = self.manifest["batches"][index]
        directory = Path(batch["directory"])
        try:
            marker = json.loads((directory / "complete.json").read_text())
            if (marker.get("key") != batch["key"] or set(marker.get("outputs", {})) != set(OUTPUTS)
                    or any(self.contract.sha256_file(directory / name) != marker["outputs"][name] for name in OUTPUTS)):
                return False
        except (OSError, ValueError, KeyError, TypeError, self.contract.OrchestrationContractError):
            return False
        if index not in self.selected:
            return True
        try:
            receipt = json.loads((directory / RECEIPT).read_text())
            marker = json.loads((directory / "complete.json").read_text())
            expected = {"schema": SCHEMA, "profile_sha256": self.sha,
                        "native_key": self.native["batches"][index]["key"], "key": batch["key"],
                        "batch_index": index, "status": "complete", "policy": self.policy}
            if any(receipt.get(k) != v for k, v in expected.items()) or receipt.get("outputs") != marker["outputs"]:
                return False
            tool = Path(receipt["command"][0])
            if receipt["command"] != mapping_command(self.native, batch, tool, Path(self.native["cache"]) / "target.mmi", self.policy):
                return False
            if receipt.get("tool_sha256") != self.native["identities"]["tool"]:
                return False
            original = self.native["batches"][index]
            required = {original["query"]: original["query_sha256"],
                        self.native["name_map"]: self.native["identities"]["name_map"],
                        self.native["restore"]: self.native["identities"]["restore"],
                        str(tool): self.native["identities"]["tool"]}
            if any(receipt.get("inputs", {}).get(p, {}).get("sha256") != sha for p, sha in required.items()):
                return False
            index_path = str(Path(self.native["cache"]) / "target.mmi")
            if set(receipt.get("inputs", {})) != set(required) | {index_path}:
                return False
            proof = receipt.get("index_proof", {})
            if (proof.get("key") != index_key(self.native)
                    or set(proof.get("outputs", {})) != {"target.mmi", "index.stderr.log"}
                    or receipt["inputs"][index_path].get("sha256") != proof["outputs"]["target.mmi"]):
                return False
            if receipt.get("mapping", {}).get("returncode") != 0:
                return False
            pilot.verify_completion(directory / "stderr.log", 1)
            planned_adoption = self.spec.get("adoptions", {}).get(str(index))
            adopted = receipt.get("adoption")
            if planned_adoption is None:
                if adopted is not None:
                    return False
            elif (not isinstance(adopted, dict) or adopted.get("report") != planned_adoption
                  or adopted.get("mapping_rerun") is not False
                  or adopted.get("mapping") != receipt["mapping"]):
                return False
            self.contract.validate_paf(directory / "result.paf", require_cigar=True)
            return True
        except (OSError, ValueError, KeyError, TypeError, IndexError):
            return False

    @property
    def merge_manifest_path(self):
        # A native-only group preserves its original merge identity as well as
        # all batch keys; do not recopy an already merged native PAF.
        return self.path if self.selected else self.source

    @property
    def merge_manifest_sha(self):
        return self.sha if self.selected else self.spec["native_manifest"]["sha256"]

    def merge(self):
        self.verify()
        # Presence gate avoids rehashing a completed prefix after every batch.
        if any(not (Path(b["directory"]) / "complete.json").is_file() for b in self.manifest["batches"]):
            return False
        if not all(self.validate_batch(i) for i in range(len(self.manifest["batches"]))):
            raise ValueError("self profile batch receipt/output mismatch before merge")
        merged = self.helper.merge_if_complete(self.merge_manifest_path, self.manifest)
        self.verify()
        return merged


def reuse_candidate(profile, index, command, inputs, attempt):
    row = profile.spec.get("adoptions", {}).get(str(index))
    if row is None:
        return None
    path = Path(row["path"]).resolve(strict=True)
    if profile.work == path or profile.work in path.parents or pilot.digest(path) != row["sha256"]:
        raise ValueError("changed or non-isolated whole candidate")
    source = json.loads(path.read_text())
    if (source.get("scope") != "one_complete_self_query_moderate_candidate_only"
            or source.get("status") != "moderate_candidate_complete_not_adopted"
            or source.get("candidate_adopted") is not False
            or source.get("analysis_workspace_modified") is not False
            or source.get("whole_records_preserved") is not True
            or source.get("mapping", {}).get("returncode") != 0
            or source.get("restoration", {}).get("returncode") != 0
            or source.get("seed_fraction") != profile.policy["seed_fraction"]
            or source.get("native_batch_key") != profile.native["batches"][index]["key"]
            or source.get("command") != command):
        raise ValueError("whole candidate does not match this explicit profile batch")
    if any(source["inputs"].get(p) != value for p, value in inputs.items()):
        raise ValueError("whole candidate query/tool/index/input identity differs")
    expected = source["outputs"]
    if set(expected) != {str(path.parent / name) for name in (*OUTPUTS, "restore.stderr.log")}:
        raise ValueError("whole candidate outputs belong to another directory")
    if pilot.identities([Path(p) for p in expected]) != expected:
        raise ValueError("whole candidate output changed")
    pilot.verify_completion(path.parent / "stderr.log", 1)
    for name in (*OUTPUTS, "restore.stderr.log"):
        shutil.copyfile(path.parent / name, attempt / name)
        if pilot.identities([attempt / name])[str(attempt / name)] != expected[str(path.parent / name)]:
            raise ValueError("whole candidate changed while copying")
    if pilot.digest(path) != row["sha256"]:
        raise ValueError("whole candidate report changed while copying")
    return {"report": row, "mapping": source["mapping"], "restoration": source["restoration"],
            "original_outputs": expected, "mapping_rerun": False}


def run_batch(profile, index):
    profile.verify()
    if index not in profile.selected:
        raise ValueError("ordinary batches must retain their original command")
    helper, manifest = profile.helper, profile.native
    batch = profile.manifest["batches"][index]
    directory = Path(batch["directory"])
    tool = Path(shutil.which("minimap2") or "").resolve()
    if not tool.is_file() or pilot.digest(tool) != manifest["identities"]["tool"]:
        raise ValueError("original Minimap2 changed")
    helper.require_identity(manifest, "name_map", Path(manifest["name_map"]))
    helper.require_identity(manifest, "restore", Path(manifest["restore"]))
    query = Path(batch["query"])
    if pilot.digest(query) != batch["query_sha256"]:
        raise ValueError("original complete query changed")
    queries = helper.fasta_lengths(query)
    if list(queries.items()) != [(e["name"], e["length"]) for e in batch["entries"]]:
        raise ValueError("whole query names/lengths/order changed")
    with helper.exclusive_lock(directory / "batch.lock"):
        if (directory / "complete.json").exists():
            if not profile.validate_batch(index):
                raise ValueError("preserve existing native/unknown batch; refresh profile rather than overwrite")
            print("SELF_PROFILE_CACHE_HIT", index, flush=True)
            return
        index_path = helper.ensure_index(manifest, tool, Path(manifest["target"]), Path(manifest["cache"]), 1)
        command = mapping_command(manifest, batch, tool, index_path, profile.policy)
        inputs = pilot.identities([query, tool, index_path, Path(manifest["name_map"]), Path(manifest["restore"])])
        index_proof = json.loads((Path(manifest["cache"]) / "complete.json").read_text())
        if (index_proof.get("key") != index_key(manifest)
                or set(index_proof.get("outputs", {})) != {"target.mmi", "index.stderr.log"}
                or index_proof["outputs"]["target.mmi"] != inputs[str(index_path)]["sha256"]):
            raise ValueError("validated cached index proof differs from actual index")
        attempt = Path(tempfile.mkdtemp(prefix="profile-attempt-", dir=directory))
        helper.atomic_json(attempt / "command.json", command)
        adoption = reuse_candidate(profile, index, command, inputs, attempt)
        mapping = (adoption["mapping"] if adoption is not None else
                   pilot.run_child(command, attempt / "raw.paf", attempt / "stderr.log", profile.policy["mapper_timeout_seconds"]))
        if mapping["returncode"]:
            raise ValueError("self profile mapper failed or timed out; attempt preserved")
        pilot.verify_completion(attempt / "stderr.log", 1)
        helper.validate_raw(attempt / "raw.paf", queries, manifest["target_lengths"])
        profile.contract.validate_paf(attempt / "raw.paf", require_cigar=True)
        if adoption is not None:
            restoration = adoption["restoration"]
        else:
            with (attempt / "raw.paf").open("rb") as raw:
                restoration = pilot.run_child([sys.executable, manifest["restore"], manifest["name_map"]],
                    attempt / "result.paf", attempt / "restore.stderr.log", 300, stdin=raw)
        if restoration["returncode"]:
            raise ValueError("self profile name restoration failed")
        names = dict(line.split("\t", 1) for line in Path(manifest["name_map"]).read_text().splitlines() if line)
        helper.validate_raw(attempt / "result.paf", {names[k]: v for k, v in queries.items()},
                            {names[k]: v for k, v in manifest["target_lengths"].items()})
        profile.contract.validate_paf(attempt / "result.paf", require_cigar=True)
        if pilot.identities([Path(p) for p in inputs]) != inputs:
            raise ValueError("self input/index changed during profile execution")
        profile.verify()
        # Invalidate only the derived merge marker under the original lock.
        with helper.exclusive_lock(Path(manifest["output"]).parent / ".self_batch_merge.lock"):
            (Path(manifest["output"]).parent / "self_batch_result.json").unlink(missing_ok=True)
        for name in OUTPUTS:
            os.replace(attempt / name, directory / name)
        receipt = {"schema": SCHEMA, "status": "complete", "profile_sha256": profile.sha,
            "native_key": manifest["batches"][index]["key"], "key": batch["key"], "batch_index": index,
            "policy": profile.policy, "command": command, "inputs": inputs, "mapping": mapping,
            "adoption": adoption, "index_proof": index_proof,
            "tool_sha256": manifest["identities"]["tool"],
            "outputs": {name: pilot.digest(directory / name) for name in OUTPUTS}}
        helper.atomic_json(directory / RECEIPT, receipt)
        helper.publish(directory, batch["key"], OUTPUTS)
        if not profile.validate_batch(index):
            raise ValueError("new self profile publication did not verify")
        print("SELF_PROFILE_COMMITTED", index, "key=" + batch["key"], flush=True)
    # Do not invoke native merging here. The owning controller handles merging
    # before its original finish callback, also when a native batch finishes last.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--batch-index", type=int, required=True)
    args = parser.parse_args()
    def stop(signum, _frame):
        raise KeyboardInterrupt("signal " + str(signum))
    signal.signal(signal.SIGTERM, stop)
    run_batch(Profile(args.profile), args.batch_index)


if __name__ == "__main__":
    main()
