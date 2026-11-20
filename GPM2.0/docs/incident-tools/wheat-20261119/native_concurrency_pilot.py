"""Compute-node-only bounded native replay; never adopts outputs into a run.

Uses completed native batches and the frozen helper with unchanged mapping
flags. Thread grants remain unchanged unless explicit resource-only rebudgeting
is requested and both output PAFs still compare byte-for-byte. Four lanes use the original guard; up to sixteen require the
explicit native split-limit adapter, within a maximum 32-thread budget. All writable manifest paths and index copies are isolated. The
32-GiB per-process AS guard covers each helper and its sequential mapper/restore
child; it is not a cgroup or an aggregate RSS limit. Trial timeout is not a
production policy. This pilot does not deploy a dispatcher or certify all inputs.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import time

LANES = 4
THREADS = 8
AS_BYTES = 32 * 1024**3
OUTPUTS = ("raw.paf", "result.paf", "stderr.log")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def require(path, expected):
    if digest(path) != expected:
        raise ValueError("source/output identity changed: " + str(path))


def record(path):
    return {"path": str(path), "sha256": digest(path)}


def isolated_manifest(manifest, batch_index, case, cache):
    result = copy.deepcopy(manifest)
    batch = copy.deepcopy(result["batches"][batch_index])
    batch["directory"] = str(case / "batch")
    result["batches"] = [batch]
    result["cache"] = str(cache)
    result["output"] = str(case / "isolated-self.paf")
    return result


def verify_outputs(directory, key):
    marker = json.loads((directory / "complete.json").read_text())
    if marker["key"] != key or set(marker["outputs"]) != set(OUTPUTS):
        raise ValueError("not a complete native batch")
    for name in OUTPUTS:
        require(directory / name, marker["outputs"][name])
    return marker


def expected_command(manifest, batch, tool, threads=THREADS):
    return [str(tool), "-c", "-x", manifest["preset"], "-X", "--no-hash-name",
            "-m", str(manifest["min_chain_score"]), "-n", str(manifest["minimizers"]),
            "-t", str(threads), str(Path(manifest["cache"]) / "target.mmi"), batch["query"]]


def check_bounds(manifest, batch, threads=THREADS):
    if (manifest.get("version") != 1 or not batch["entries"]
            or sum(x["length"] for x in batch["entries"]) > 20_000_000
            or sum(manifest["target_lengths"].values()) > 1_000_000_000
            or any(x["length"] <= 0 for x in batch["entries"])
            or type(threads) is not int or not 1 <= threads <= THREADS
            or len(batch["entries"]) < threads):
        raise ValueError("outside the bounded eight-thread native replay scope")


def execute(config_path, output, timeout):
    driver_record = record(Path(__file__).resolve())
    config_record = record(config_path)
    config = json.loads(config_path.read_text())
    work = Path(config["workspace"]).resolve(strict=True)
    output = output.resolve()
    if output == work or work in output.parents or output in work.parents:
        raise ValueError("pilot outputs must be disjoint from the analysis workspace")
    lanes = config.get("lanes",LANES)
    adapter_record = config["runtime"].get("native_adapter")
    if (type(lanes) is not int or not 1 <= lanes <= 16 or len(config["cases"]) != lanes
            or (not adapter_record and lanes != LANES) or not 0 < timeout <= 3600):
        raise ValueError("unsupported lane count or trial timeout")
    cpu_budget = config.get("cpu_budget",32)
    if type(cpu_budget) is not int or not 1 <= cpu_budget <= 32:
        raise ValueError("pilot CPU budget must fit the 32-CPU job")
    grants = [c.get("threads",THREADS) for c in config["cases"]]
    if (any(type(n) is not int or not 1 <= n <= THREADS for n in grants)
            or sum(grants) > cpu_budget):
        raise ValueError("pilot thread grants exceed the CPU budget")
    baseline_grants = [c.get("baseline_threads",n) for c,n in zip(config["cases"],grants)]
    if any(type(n) is not int or not 1 <= n <= THREADS for n in baseline_grants):
        raise ValueError("invalid baseline thread grant")
    changed_threads = baseline_grants != grants
    if changed_threads and (config.get("allow_thread_rebudget") is not True or not adapter_record):
        raise ValueError("thread rebudgeting requires an explicit split-guard pilot")
    if len({(c["manifest"]["path"], c["batch_index"]) for c in config["cases"]}) != lanes:
        raise ValueError("duplicate replay batch")
    for r in config["runtime"].values():
        require(r["path"], r["sha256"])
    helper = Path(config["runtime"]["helper"]["path"])
    guard = Path(config["runtime"]["guard"]["path"])
    tool = Path(config["runtime"]["tool"]["path"])
    if Path(shutil.which("minimap2") or "").resolve() != tool.resolve():
        raise ValueError("PATH does not select the frozen mapper")
    output.mkdir(exist_ok=False)
    started = time.monotonic()
    prepared, verified = [], set()
    def once(path, sha):
        key = (str(path), sha)
        if key not in verified:
            require(path, sha); verified.add(key)
    for n, spec in enumerate(config["cases"]):
        source = Path(spec["manifest"]["path"])
        if not source.resolve().is_relative_to(work):
            raise ValueError("source manifest is outside the requested workspace")
        require(source, spec["manifest"]["sha256"])
        m = json.loads(source.read_text()); b = m["batches"][spec["batch_index"]]
        threads = spec.get("threads",THREADS)
        baseline_threads = spec.get("baseline_threads",threads)
        check_bounds(m, b, threads)
        check_bounds(m, b, baseline_threads)
        baseline = Path(b["directory"])
        if (baseline / "self-profile-receipt.json").exists():
            raise ValueError("fast-profile result is not a native baseline")
        require(baseline / "complete.json", spec["complete_sha256"])
        original = verify_outputs(baseline, b["key"])
        require(spec["command"]["path"], spec["command"]["sha256"])
        if json.loads(Path(spec["command"]["path"]).read_text()) != expected_command(m, b, tool, baseline_threads):
            raise ValueError("baseline command differs from the declared original parameters")
        for key in ("target", "name_map", "restore"):
            once(m[key], m["identities"][key])
        once(tool, m["identities"]["tool"])
        once(b["query"], b["query_sha256"])
        original_cache = Path(m["cache"])
        cm = json.loads((original_cache / "complete.json").read_text())
        expected = identity({"tool":m["identities"]["tool"], "target":m["identities"]["target"],
                             "preset":m["preset"], "index_limit":"8G"})
        if cm["key"] != expected or set(cm["outputs"]) != {"target.mmi", "index.stderr.log"}:
            raise ValueError("index provenance does not match native inputs")
        cache = output / "indices" / expected
        if not cache.exists():
            cache.mkdir(parents=True)
            for name, sha in cm["outputs"].items():
                once(original_cache / name, sha)
                shutil.copyfile(original_cache / name, cache / name)
                require(cache / name, sha)
            (cache / "complete.json").write_text(json.dumps(cm))
        case = output / ("case-" + str(n)); case.mkdir()
        manifest = isolated_manifest(m, spec["batch_index"], case, cache)
        mp = case / "manifest.json"; mp.write_text(json.dumps(manifest))
        command = [sys.executable, "-B", str(helper), "--manifest", str(mp), "--batch-index", "0"]
        if adapter_record:
            import native_batch_guard as adapter
            if Path(adapter.__file__).resolve() != Path(adapter_record["path"]).resolve():
                raise ValueError("pilot imported an unbound native adapter")
            native_spec = {"schema":adapter.SCHEMA,"policy":adapter.POLICY,
                "manifest":record(mp),"batch_index":0,"native_key":b["key"],
                "runtime":{"adapter":adapter_record,"helper":config["runtime"]["helper"],
                    "mapper":config["runtime"]["tool"],"diagnostics":config["runtime"]["minimap_diagnostics"],
                    "restore":record(m["restore"])}}
            native_path = case / "native-resource.json"
            native_path.write_text(json.dumps(native_spec,indent=2))
            command = [sys.executable,"-B",str(adapter_record["path"]),"--spec",str(native_path)]
        script = case / "command.sh"
        script.write_text("#!/bin/bash\nset -euo pipefail\nexec " + shlex.join(command) + "\n")
        prepared.append({"case":case, "source":spec, "baseline":original, "key":b["key"],
                         "script":record(script), "manifest":record(mp), "threads":threads})
    env = dict(os.environ, GPM_TASK_THREADS=str(THREADS), OMP_NUM_THREADS=str(THREADS),
               OPENBLAS_NUM_THREADS=str(THREADS), PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(helper.parent))
    children, handles = [], []
    mapping_started = time.monotonic()
    try:
        for item in prepared:
            log = (item["case"] / "launcher.log").open("wb"); handles.append(log)
            cmd = [sys.executable, "-B", str(guard), "--script", item["script"]["path"],
                   "--sha256", item["script"]["sha256"], "--limit-bytes", str(AS_BYTES)]
            children.append(subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                                             env={**env,"GPM_TASK_THREADS":str(item["threads"]),"OMP_NUM_THREADS":str(item["threads"]),
                                                  "OPENBLAS_NUM_THREADS":str(item["threads"])}, start_new_session=True))
        print(json.dumps({"event":"GUARDED_NATIVE_LANES_STARTED", "pids":[p.pid for p in children],
                          "lanes":lanes,"thread_grants":grants, "outer_as_bytes_each_process":AS_BYTES}), flush=True)
        while any(p.poll() is None for p in children):
            if any(p.poll() not in (None, 0) for p in children):
                raise RuntimeError("native replay failed; inspect retained lane logs")
            if time.monotonic() - mapping_started > timeout:
                raise TimeoutError("isolated pilot budget exceeded; main tasks were not changed")
            time.sleep(1)
        if any(p.returncode != 0 for p in children):
            raise RuntimeError("native replay failed")
    finally:
        for child in children:
            if child.poll() is None:
                try: os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError: pass
        for child in children:
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try: os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                child.wait()
        for log in handles: log.close()
    execution_seconds = time.monotonic() - mapping_started
    result = []
    for item in prepared:
        case = item["case"]
        marker = verify_outputs(case / "batch", item["key"])
        require(Path(item["source"]["manifest"]["path"]), item["source"]["manifest"]["sha256"])
        m = json.loads(Path(item["source"]["manifest"]["path"]).read_text())
        b = m["batches"][item["source"]["batch_index"]]
        require(Path(b["directory"]) / "complete.json", item["source"]["complete_sha256"])
        baseline = verify_outputs(Path(b["directory"]), item["key"])
        same = {name:marker["outputs"][name] == baseline["outputs"][name] for name in ("raw.paf", "result.paf")}
        if not all(same.values()):
            raise ValueError("native replay output differs; not approved for production")
        require(case / "isolated-self.paf", marker["outputs"]["result.paf"])
        guard_rows = [json.loads(line.split(" ",1)[1]) for line in (case / "launcher.log").read_text().splitlines()
                      if line.startswith("SELF_RESOURCE_GUARD ")]
        if len(guard_rows) != 1 or guard_rows[0]["limit_bytes"] != AS_BYTES:
            raise ValueError("missing actual native address-space guard receipt")
        resource_receipt = None
        if adapter_record:
            resource_receipt = json.loads((case / "batch" / adapter.RECEIPT).read_text())
            if (resource_receipt["policy"] != adapter.POLICY or resource_receipt["native_key"] != item["key"]
                    or resource_receipt["outputs"] != marker["outputs"]
                    or resource_receipt["thread_grant"] != item["threads"]
                    or resource_receipt["runtime"]["adapter"] != adapter_record):
                raise ValueError("native split-limit execution receipt differs")
        result.append({"source":item["source"], "identical":same, "outputs":marker["outputs"],
                       "guard":guard_rows[0],"native_resource_receipt":resource_receipt})
    for path, sha in verified: require(path, sha)
    require(config_path, config_record["sha256"])
    require(driver_record["path"], driver_record["sha256"])
    for r in config["runtime"].values(): require(r["path"], r["sha256"])
    report = {"status":("guarded_native_replays_byte_identical" if adapter_record else "four_native_replays_byte_identical"), "scope":"completed bounded native batches only; not production deployment or whole-run speedup",
              "config":config_record, "implementation":driver_record, "lanes":lanes, "thread_grants":grants,
              "baseline_thread_grants":baseline_grants,"thread_counts_changed":changed_threads,
              "native_resource_policy":adapter.POLICY if adapter_record else None,
              "execution_seconds":execution_seconds, "total_seconds":time.monotonic()-started,
              "as_limit_bytes_per_process":AS_BYTES, "main_workspace_modified":False, "cases":result}
    (output / "pilot.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report),flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    execute(args.config.resolve(strict=True), args.output, args.timeout)
