"""One isolated whole-record self candidate; never publish a native checkpoint.

The running native batch is the sole baseline. Preserve its full query, cached
index, names, -X, --no-hash-name, thresholds and thread count. Change only -f.
This driver does NOT compare/admit results: self evidence needs an all-hit,
self-specific comparison after the native batch has successfully committed.
Run via the scheduler, since source/index verification reads complete files.
"""
import argparse
import hashlib
import importlib
import json
import signal
import subprocess
import sys
import time
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def identities(paths):
    result = {}
    for path in paths:
        before = path.stat()
        sha = digest(path)
        after = path.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("source changed while hashing: " + str(path))
        result[str(path)] = {"sha256": sha, "size": after.st_size}
    return result


def candidate_command(manifest, batch, native):
    if manifest.get("version") != 1 or len(batch["entries"]) != 1:
        raise ValueError("pilot requires a v1 single whole-record batch")
    expected = [native[0], "-c", "-x", manifest["preset"], "-X", "--no-hash-name",
                "-m", str(manifest["min_chain_score"]), "-n", str(manifest["minimizers"]),
                "-t", "1", str(Path(manifest["cache"]) / "target.mmi"), batch["query"]]
    if native != expected:
        raise ValueError("native command differs from the full-record self contract")
    return native[:-2] + ["-f", "0.005"] + native[-2:]


def require_isolated(work, output):
    work, output = work.resolve(strict=True), output.resolve()
    if output == work or work in output.parents or output in work.parents:
        raise ValueError("pilot output must be separate from the analysis workspace")
    if output.exists():
        raise ValueError("refusing an existing pilot output directory")


def run_child(command, raw, stderr, timeout, stdin=None):
    start = time.monotonic()
    with raw.open("wb") as out, stderr.open("wb") as err:
        proc = subprocess.Popen(command, stdout=out, stderr=err, stdin=stdin)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            code = 124
        except BaseException:
            proc.kill()
            proc.wait()
            raise
    return {"returncode": code, "wall_seconds": time.monotonic() - start}


def verify_completion(stderr, query_count):
    import re
    text = stderr.read_text(errors="replace")
    counts = re.findall(r"\[M::worker_pipeline[^\]]*\] mapped (\d+) sequences", text)
    if sum(map(int, counts)) != query_count or "Real time:" not in text:
        raise ValueError("candidate does not prove full query traversal and normal completion")


def execute(work, manifest_path, batch_index, native_path, output, helper_sha):
    require_isolated(work, output)
    manifest_path.resolve(strict=True).relative_to(work.resolve(strict=True))
    manifest = json.loads(manifest_path.read_text())
    if not 0 <= batch_index < len(manifest["batches"]):
        raise ValueError("invalid batch index")
    batch = manifest["batches"][batch_index]
    directory = Path(batch["directory"])
    native_path.resolve(strict=True).relative_to(directory.resolve(strict=True))
    native = json.loads(native_path.read_text())
    command = candidate_command(manifest, batch, native)
    tools = work / ".prepare_lib/tools"
    helper_path = tools / "self_alignment_batches.py"
    if digest(helper_path) != helper_sha:
        raise ValueError("unexpected frozen self helper")
    sys.path.insert(0, str(tools))
    helper = importlib.import_module("self_alignment_batches")
    contract = importlib.import_module("run_orchestration")
    if Path(helper.__file__).resolve() != helper_path.resolve():
        raise ValueError("wrong self helper imported")
    cache = Path(manifest["cache"])
    index_key = helper.identity({"tool": manifest["identities"]["tool"],
        "target": manifest["identities"]["target"], "preset": manifest["preset"], "index_limit": "8G"})
    index_proof = json.loads((cache / "complete.json").read_text())
    if index_proof["key"] != index_key or set(index_proof["outputs"]) != {"target.mmi", "index.stderr.log"}:
        raise ValueError("invalid original cached-index proof")
    paths = [manifest_path, native_path, Path(native[0]), Path(batch["query"]),
             Path(manifest["name_map"]), Path(manifest["restore"]), helper_path,
             tools / "minimap2_diagnostics.py", Path(contract.__file__),
             cache / "complete.json", cache / "target.mmi", cache / "index.stderr.log"]
    before = identities(paths)
    if (json.loads(manifest_path.read_text()) != manifest
            or json.loads(native_path.read_text()) != native
            or json.loads((cache / "complete.json").read_text()) != index_proof):
        raise ValueError("source metadata changed during preparation")
    checks = [(Path(native[0]), manifest["identities"]["tool"]),
              (Path(batch["query"]), batch["query_sha256"]),
              (Path(manifest["name_map"]), manifest["identities"]["name_map"]),
              (Path(manifest["restore"]), manifest["identities"]["restore"]),
              (helper_path, helper_sha)]
    checks += [(cache / name, sha) for name, sha in index_proof["outputs"].items()]
    if any(before[str(path)]["sha256"] != sha for path, sha in checks):
        raise ValueError("pilot source/index identity mismatch")
    queries = helper.fasta_lengths(Path(batch["query"]))
    if list(queries.items()) != [(entry["name"], entry["length"]) for entry in batch["entries"]]:
        raise ValueError("whole query names/lengths/order changed")
    output.mkdir()
    report = {"scope": "one_complete_self_query_candidate_only", "inputs": before,
        "driver_sha256": digest(Path(__file__)),
        "native_command": native, "command": command, "native_batch_key": batch["key"],
        "candidate_adopted": False, "analysis_workspace_modified": False,
        "native_comparison": "pending_verified_native_commit_and_all_hit_self_comparison",
        "target_fasta_sha256_basis": "recorded_index_source_identity_not_fresh_target_fasta_read",
        "source_target_sha256": manifest["identities"]["target"], "status": "running"}
    helper.atomic_json(output / "pilot.json", report)
    try:
        report["mapping"] = run_child(command, output / "raw.paf", output / "stderr.log", 1800)
        if report["mapping"]["returncode"] != 0:
            raise ValueError("candidate mapping failed or reached its 1800-second limit")
        verify_completion(output / "stderr.log", len(queries))
        helper.validate_raw(output / "raw.paf", queries, manifest["target_lengths"])
        contract.validate_paf(output / "raw.paf", require_cigar=True)
        with (output / "raw.paf").open("rb") as raw:
            restore = run_child([sys.executable, manifest["restore"], manifest["name_map"]],
                output / "result.paf", output / "restore.stderr.log", 300, stdin=raw)
        if restore["returncode"]:
            raise ValueError("isolated name restoration failed")
        contract.validate_paf(output / "result.paf", require_cigar=True)
        if before != identities(paths):
            raise ValueError("source/index changed during candidate execution")
        report["outputs"] = identities([output / name for name in
            ("raw.paf", "result.paf", "stderr.log", "restore.stderr.log")])
        report["status"] = "candidate_complete_not_compared_not_adopted"
    except BaseException as error:
        report.update(status="failed_or_interrupted_not_adopted", error=str(error))
        raise
    finally:
        helper.atomic_json(output / "pilot.json", report)
    print(json.dumps(report, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("work", "manifest", "native-command", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--batch-index", type=int, required=True)
    parser.add_argument("--helper-sha256", required=True)
    args = parser.parse_args()
    def stop(signum, _frame):
        raise KeyboardInterrupt("signal " + str(signum))
    signal.signal(signal.SIGTERM, stop)
    execute(args.work, args.manifest, args.batch_index, args.native_command, args.output, args.helper_sha256)


if __name__ == "__main__":
    main()
