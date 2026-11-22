#!/usr/bin/env python3
"""Isolated controller for content-reviewed, still-legacy LGZ continuation.

Only stdlib imports precede verification. Never import this workspace's engine
in the new Server interpreter, or mistake its observed version for provenance.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

sys.dont_write_bytecode = True


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def owned(root, relative):
    part = Path(relative)
    if not relative or part.is_absolute() or ".." in part.parts or "\\" in relative:
        raise ValueError("invalid legacy engine/artifact path: " + str(relative))
    path = root
    for component in part.parts:
        path = path / component
        if path.is_symlink():
            raise ValueError("legacy continuation requires regular owned files: " + str(path))
    return path


def verify_engine(root, engine):
    runtime = owned(root, ".prepare_lib")
    expected = engine["files_sha256"]
    for name, value in expected.items():
        path = owned(runtime, name)
        if not path.is_file() or digest(path) != value:
            raise ValueError("unsupported/changed historical engine file: " + name)
    for area in ("tools", "lib", "contracts"):
        for path in (runtime / area).rglob("*"):
            relative = path.relative_to(runtime).as_posix()
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            if path.is_symlink() or (path.is_file() and relative not in expected):
                raise ValueError("unreviewed historical engine file: " + relative)
    return runtime


def install_cache_fence(root, engine, event_file):
    """Observe original cache decisions; never manufacture cache success.

    Reviewed line barriers run *before* creation/invalidation after a miss.
    Existing q-stage cache misses are raised on the original function return.
    """
    runtime = root / ".prepare_lib"
    # -B prevents writes, not reads. Ignore unverified historical bytecode
    # without deleting it or writing a replacement cache during preview.
    sys.pycache_prefix = str(root / ".run_all" / ("unused-pycache-" + uuid.uuid4().hex))
    barriers = {(str(runtime / row["path"]), row["function"], row["line"]): row["receipt"]
                for row in engine["cache_miss_barriers"]}
    cache_source = str(runtime / "tools/lgz_core/stage_cache.py")

    def event(kind, receipt):
        with event_file.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": kind, "receipt": receipt, "pid": os.getpid()}, sort_keys=True) + "\n")

    def cache_return(frame, action, result):
        if action == "return":
            stage = frame.f_locals.get("stage")
            receipt = "grt/checkpoints/" + str(stage) + ".json"
            if (root / receipt).exists():
                if result is None:
                    event("REFUSED_COMPLETED_CACHE_MISS", receipt)
                    raise RuntimeError("legacy continuation refuses to invalidate completed stage: " + receipt)
                event("ORIGINAL_CACHE_VALID", receipt)
        return cache_return

    by_function = {}
    for (filename, function, line), receipt in barriers.items():
        by_function.setdefault((filename, function), {})[line] = receipt

    known_sources = {function: filename for filename, function in by_function}
    known_sources["checkpoint_result"] = cache_source
    resolved_names = {}

    def calls(frame, action, _result):
        # Do not trace every Python line in unfinished scientific work. Only
        # original cache returns, and the two reviewed completed-cache branches,
        # need local callbacks. Native algorithms run without line tracing.
        if action != "call":
            return None
        name, filename = frame.f_code.co_name, frame.f_code.co_filename
        expected = known_sources.get(name)
        if expected is None:
            return None
        # Prepared absolute paths can use an older root symlink/spelling. Bind
        # the code to the same verified file, not just an identical path string.
        if filename != expected:
            if filename not in resolved_names:
                try:
                    resolved_names[filename] = expected if os.path.samefile(filename, expected) else filename
                except OSError:
                    resolved_names[filename] = filename
            filename = resolved_names[filename]
        key = (filename, name)
        if key == (cache_source, "checkpoint_result"):
            frame.f_trace_lines = False
            return cache_return
        lines = by_function.get(key)
        if not lines or not any((root / receipt).exists() for receipt in lines.values()):
            return None
        def boundary(current, event_kind, _value):
            receipt = lines.get(current.f_lineno) if event_kind == "line" else None
            if receipt and (root / receipt).exists():
                event("REFUSED_COMPLETED_CACHE_MISS", receipt)
                raise RuntimeError("legacy continuation refuses to recompute completed work: " + receipt)
            return boundary
        return boundary

    sys.settrace(calls)


def engine_imports(root):
    # -I disables caller PYTHONPATH/user-site. Keep only installed stdlib/site
    # entries after replacing the new tool directory with the reviewed engine.
    sys.pycache_prefix = str(root / ".run_all" / ("unused-pycache-" + uuid.uuid4().hex))
    source = str(Path(__file__).resolve().parent)
    sys.path[:] = [str(root / ".prepare_lib/tools")] + [p for p in sys.path if p and p != source]
    import run_all_runner as old
    return old


def inspect(root, engine):
    verify_engine(root, engine)
    old = engine_imports(root)
    manager = old.OuterCheckpointManager(root)
    units = old.load_plan(root)
    ids = [unit.unit_id for unit in units]
    prefix = units[:ids.index("finalize_evidence") + 1]
    prior = old.load_prior_status(root / "logs/status.tsv")
    checked = []
    for unit in prefix:
        # prepare() may require future inputs. Inspect only claimed/persisted
        # outer checkpoints, not pending units whose prerequisites do not exist.
        slug = "".join(c if c.isalnum() else "-" for c in unit.unit_id)
        from run_orchestration import fingerprint
        checkpoint = root / ".run_all/checkpoints" / (slug[:48] + "." + fingerprint(unit.unit_id)[:16] + ".json")
        outer = unit.unit_id.startswith(("ref:", "chr:", "q0_chr:")) or unit.unit_id == "assign"
        claimed = prior.get(unit.unit_id, {}).get("state") == "success"
        if outer and (checkpoint.exists() or claimed):
            prepared = manager.prepare(unit.unit_id, unit.command_relpath)
            if prepared is None:
                raise ValueError("historical engine does not recognize completed outer unit: " + unit.unit_id)
            valid, reason = manager.validate(prepared)
            if not valid:
                raise ValueError("refuse to rerun completed outer unit " + unit.unit_id + ": " + reason)
            checked.append({"unit_id": unit.unit_id, "checkpoint": checkpoint.relative_to(root).as_posix(),
                            "sha256": digest(checkpoint), "validation": "original-input-output-validator"})
        elif claimed and unit.unit_id in old.LGZ_CACHE_MARKERS:
            valid, reason = manager.validate_lgz_unit(unit.unit_id)
            if not valid:
                raise ValueError("invalid completed LGZ unit " + unit.unit_id + ": " + reason)
        elif claimed and unit.unit_id == "q0_evidence" and not (root / "metadata/grt_q0_evidence.json").is_file():
            raise ValueError("completed q0 evidence has no receipt")
        elif claimed and unit.unit_id == "finalize_evidence":
            valid, reason = manager.validate_evidence()
            if not valid:
                raise ValueError("invalid completed evidence: " + reason)
    manifest = root / "metadata/grt_q0_evidence.json"
    if manifest.exists():
        from lgz_core.q0_preparation import load_verified_evidence
        load_verified_evidence(root)
        checked.append({"checkpoint": manifest.relative_to(root).as_posix(), "sha256": digest(manifest),
                        "validation": "original-q0-evidence-validator"})
    for checkpoint in sorted((root / "grt/checkpoints").glob("*.json")):
        value = json.loads(owned(root, checkpoint.relative_to(root).as_posix()).read_text())
        if (value.get("workflow") != "gpm_grt_precomputed_v2" or value.get("status") != "success"
                or value.get("stage") != checkpoint.stem or not value.get("input_fingerprint")
                or not isinstance(value.get("output_hashes"), dict) or not value["output_hashes"]):
            raise ValueError("unvalidated existing LGZ checkpoint: " + str(checkpoint))
        for relative, expected in value["output_hashes"].items():
            path = owned(root, relative)
            if not path.is_file() or digest(path) != expected:
                raise ValueError("completed LGZ output changed: " + relative)
        for relative in value.get("required_directories", []):
            if not owned(root, relative).is_dir():
                raise ValueError("completed LGZ required directory missing: " + relative)
        if value.get("result_relpath"):
            from lgz_core.stage_cache import checkpoint_result
            if checkpoint_result(root, checkpoint.stem, value["input_fingerprint"]) is None:
                raise ValueError("existing LGZ result differs from checkpoint: " + checkpoint.stem)
        checked.append({"checkpoint": checkpoint.relative_to(root).as_posix(), "sha256": digest(checkpoint),
                        "validation": "original-completed-output-check; native-input-cache-fence-at-dispatch"})
    return old, prefix, checked


def execute(root, request):
    engine = request["engine"]
    old, prefix, checked = inspect(root, engine)
    if request["mode"] == "inspect":
        print(json.dumps({"prefix": [unit.unit_id for unit in prefix], "checkpoints": checked}, sort_keys=True))
        return 0
    owner = json.loads((root / ".run_all/lock/owner.json").read_text())
    if (owner.get("pid") != os.getppid() or owner.get("run_id") != request["run_id"]
            or owner.get("workspace") != str(root) or owner.get("hostname") != __import__("socket").gethostname()
            or not old.process_is_alive(owner["pid"], owner.get("process_start", ""))):
        raise ValueError("original workspace lock is not owned by the live continuation controller")
    event_file = owned(root, request["events"])
    hook = owned(root, request["hook"])
    os.environ.update(PYTHONPATH=str(hook) + os.pathsep + str(root / ".prepare_lib/tools"),
                      PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
    install_cache_fence(root, engine, event_file)
    runner = old.Runner(root, prefix, request["run_id"], color="never")
    original_prepare = runner.outer_checkpoints.prepare
    original_validate = runner.outer_checkpoints.validate

    def prepare(unit_id, command):
        verify_engine(root, engine)
        # Never leave stale completed outer checkpoints to the old runner's
        # automatic recomputation branch, even if inputs drift during the run.
        prepared = original_prepare(unit_id, command)
        if prepared is not None and prepared.path.exists():
            valid, reason = original_validate(prepared)
            if not valid:
                raise old.OrchestrationContractError("completed outer work changed; no rerun: " + reason)
        return prepared

    runner.outer_checkpoints.prepare = prepare
    return runner.run()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        return execute(args.server_dir.resolve(), json.load(sys.stdin))
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        print("legacy LGZ continuation failed: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
