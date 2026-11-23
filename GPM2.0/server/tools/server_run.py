#!/usr/bin/env python3
"""Prepare once, then run/resume the existing Server execution plan under one lock."""
from __future__ import annotations

try:
    from workspace_layout import workspace_join, WorkspaceLayout, initialize_workspace
except ModuleNotFoundError:
    from .workspace_layout import workspace_join, WorkspaceLayout, initialize_workspace


import json
import os
import re
import shlex
import signal
import subprocess
import sys
from pathlib import Path

from run_all_runner import Runner, RunnerError, WorkspaceLock, load_plan, new_run_id
from run_orchestration import OrchestrationContractError, atomic_write_json
from run_resources import RESOURCE_OPTIONS, update_resources
from long_cigar_recovery.minimap_options import batch_size, seed_fraction
from refinement_config import OPTIONS as REFINEMENT_OPTIONS, save_request, ensure_plan, resolve as resolve_refinement, preflight as refinement_preflight

ALIASES = {
    "-o": "--out", "--output": "--out", "-t": "--threads",
    "-s": "--score", "-m": "--max-fill",
    "-K": "--minimap-batch", "-f": "--minimap-filter",
    "-sm": "--self-m", "-sn": "--self-n",
    "--lgz-qc-memory-gb": "--grt-qc-memory-gb",
    "--lgz-kmer-size": "--grt-kmer-size",
    "--lgz-execution-profile": "--grt-execution-profile",
    "--lgz-step2-mummer-scope": "--grt-step2-mummer-scope",
}
SINGLE_OPTIONS = {
    "--out", "--threads", "--score", "--archive-format", "--gapfill-tools",
    "--minimap-preset", "--minimap-batch", "--minimap-filter", "--cen", "--cen-min-len",
    "--cen-min-identity", "--reads", "--reads-type", "--reads-qc", "--grt-qc-memory-gb",
    "--grt-kmer-size", "--max-fill", "--self-m", "--self-n",
    "--grt-execution-profile", "--grt-step2-mummer-scope", "--q0-supplement-scope",
}
TYPED_READ_OPTIONS = {"--hifi", "--ont"}
PATH_OPTIONS = {"--ref", "--ds", "--reads", "--cen"} | TYPED_READ_OPTIONS
LGZ_PATH_OPTIONS = PATH_OPTIONS - TYPED_READ_OPTIONS


def parse_options(argv: list[str], cwd: Path) -> dict[str, list[list[str]]]:
    options: dict[str, list[list[str]]] = {}
    index = 0
    while index < len(argv):
        key = ALIASES.get(argv[index], argv[index])
        count = 0 if key == "--skip-self" else 2 if key == "--tel" else 1
        if key in TYPED_READ_OPTIONS:
            count = 0
            while index + count + 1 < len(argv) and not argv[index + count + 1].startswith("-"):
                count += 1
            if not count:
                raise RunnerError(f"{key} requires at least one reads file")
        elif key in {"--ref", "--ds"}:
            if index + 2 < len(argv) and not argv[index + 2].startswith("-"):
                count = 2
        elif key not in SINGLE_OPTIONS and key not in {"--skip-self", "--tel"}:
            raise RunnerError(f"Unknown argument: {key}")
        values = argv[index + 1:index + count + 1]
        if len(values) != count or any(value.startswith("--") for value in values):
            raise RunnerError(f"{key} requires a value; see run.sh --help")
        if key in TYPED_READ_OPTIONS:
            values = [str((cwd / value).resolve()) for value in values]
        elif key in PATH_OPTIONS or key == "--out":
            values[-1] = str((cwd / values[-1]).resolve())
        if key in ({"--max-fill", "--self-m", "--self-n", *RESOURCE_OPTIONS} - {"--minimap-batch"}) and not re.fullmatch(r"[1-9][0-9]*", values[0]):
            raise RunnerError(f"{key} must be a positive integer")
        if key in {"--minimap-batch", "--minimap-filter"}:
            try:
                values[0] = (batch_size if key == "--minimap-batch" else seed_fraction)(values[0])
            except ValueError as exc:
                raise RunnerError(str(exc)) from exc
        allowed = {"--reads-type": {"hifi", "ont"}, "--grt-execution-profile": {"baseline", "optimized"},
                   "--grt-step2-mummer-scope": {"full", "gap-screen"},
                   "--q0-supplement-scope": {"auto", "full", "decision_frontier_repair", "positive_threshold"}}
        if key in allowed and values[0] not in allowed[key]:
            raise RunnerError(f"Invalid {key}: {values[0]}")
        if key in TYPED_READ_OPTIONS:
            # Canonicalize grouped and repeated flags identically for resume.
            options.setdefault(key, []).extend([value] for value in values)
        elif key in {"--ds", "--reads", "--tel"}:
            options.setdefault(key, []).append(values)
        else:
            options[key] = [values]
        index += count + 1
    return options


def input_identities(options: dict) -> dict:
    identities = {}
    for key in LGZ_PATH_OPTIONS:
        for values in options.get(key, []):
            path = Path(values[-1])
            stat = path.stat()
            identities[str(path)] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    return identities


def check_resume_options(requested: dict, saved: dict, identities: dict) -> None:
    for key, value in requested.items():
        if key in {"--out", "--max-fill", *RESOURCE_OPTIONS, *REFINEMENT_OPTIONS}:
            continue
        prepared = saved.get(key, [["full"]] if key == "--q0-supplement-scope" else None)
        if value != prepared:
            raise RunnerError(f"{key} differs from the prepared workspace. Use a new -o directory for changed inputs/settings.")
    for path, identity in input_identities({k: v for k, v in requested.items() if k in LGZ_PATH_OPTIONS}).items():
        if identities.get(path) != identity:
            raise RunnerError(f"Input changed since preparation: {path}. Use a new -o directory.")


def update_fill_limit(root: Path, limit: str) -> None:
    script, runtime_name = next(
        ((workspace_join(root, filename), module) for filename, module in (
            ("run_lgz_step2.sh", "lgz_step2.py"),
            ("run_grt_step2.sh", "grt_step2.py"),
            ("run_grt_step12.sh", "grt_step12.py"),
        ) if (workspace_join(root, filename)).is_file()),
        (workspace_join(root, "run_lgz_step2.sh"), "lgz_step2.py"),
    )
    runtime = workspace_join(root, ".prepare_lib/tools", runtime_name)
    if not script.is_file() or not runtime.is_file():
        raise RunnerError("This workspace has no staged LGZ Step2 runtime; update its Server runtime before changing the limit.")
    # A legacy script can call the compatibility facade after a code-only update.
    candidates = [runtime]
    if runtime_name == "grt_step2.py":
        candidates.append(runtime.with_name("lgz_step2.py"))
    if not any(path.is_file() and "--max-fill" in path.read_text(encoding="utf-8") for path in candidates):
        raise RunnerError("This workspace runtime predates --max-fill; update its Server runtime before changing the limit.")
    lines = script.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("python3 "):
            continue
        words = shlex.split(line)
        if not any(Path(word).name == runtime_name for word in words):
            continue
        if "--max-fill" in words:
            position = words.index("--max-fill") + 1
            if words[position] == limit:
                return
            words[position] = limit
        else:
            words += ["--max-fill", limit]
        lines[index] = shlex.join(words)
        temporary = script.with_suffix(".sh.tmp")
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        temporary.chmod(script.stat().st_mode)
        os.replace(temporary, script)
        return
    raise RunnerError(f"Cannot locate Step2 command in {script}")


def prepare_workspace(script: Path, argv: list[str], root: Path) -> int:
    # Forward scheduler cancellation to preparation as well as the compute stages.
    log_path = workspace_join(root, "logs/prepare.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[PREPARE] workspace={root} log={log_path}", flush=True)
    log = log_path.open("a", encoding="utf-8")
    owner = json.loads((workspace_join(root, ".run_all/lock/owner.json")).read_text())
    environment = {**os.environ, "GPM_SERVER_PREPARE_RUN_ID": owner["run_id"]}
    child = subprocess.Popen(["bash", str(script), *argv], start_new_session=True,
                             env=environment, stdout=log, stderr=subprocess.STDOUT)
    received = []
    def forward(number, _frame):
        received.append(number)
        try:
            os.killpg(child.pid, number)
        except ProcessLookupError:
            pass
    previous = {number: signal.signal(number, forward) for number in (signal.SIGINT, signal.SIGTERM)}
    try:
        result = child.wait()
        if result and log_path.exists():
            print("".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)[-30:]), file=sys.stderr)
        return 128 + received[0] if received else (128 - result if result < 0 else result)
    finally:
        log.close()
        for number, handler in previous.items():
            signal.signal(number, handler)


def execute(argv: list[str], server_source: Path) -> int:
    if "--help" in argv or "-h" in argv:
        result = subprocess.run(["bash", str(server_source / "prepare.sh"), "--help"], capture_output=True, text=True)
        print(result.stdout.replace("server/prepare.sh", "server/run.sh"))
        print("run.sh prepares once and automatically executes the full workflow.\n"
              "Resume: rerun the same command, or bash server/run.sh -o <workspace>.\n"
              "Resume with a new thread budget: bash server/run.sh -o <workspace> --threads 64\n"
              "Change only the Step2 refill limit: bash server/run.sh -o <workspace> --max-fill 2000000\n"
              "Append refinement: bash server/run.sh -o <workspace> --hifi reads.fq.gz [--ont ont.fq.gz]\n"
              "Select tools: --gapfill-tools degap,tgsgapcloser,quartet,lrgapcloser; none disables this run")
        return result.returncode
    options = parse_options(argv, Path.cwd())
    root = Path(options.get("--out", [[str(Path.cwd() / "gpm_server")]])[-1][0])
    if not root.exists() or not any(root.iterdir()):
        if "--ref" not in options or "--ds" not in options:
            raise RunnerError("A new workspace requires --ref and --ds; see run.sh --help")
        initialize_workspace(root, prepared_runtime=".lib")
    manifest_path = workspace_join(root, ".run_all/launch.json")
    run_id = new_run_id()
    lock = WorkspaceLock(root, run_id)
    try:
        lock.acquire()
        saved = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
        ready = saved.get("prepared", False) if saved else (workspace_join(root, "run_all.sh")).is_file()
        if saved:
            check_resume_options(options, saved["options"], saved["inputs"])
        elif ready and any(key not in {"--out", "--max-fill", *RESOURCE_OPTIONS, *REFINEMENT_OPTIONS} for key in options):
            raise RunnerError("Resume this existing workspace with run.sh -o <workspace>; its original launch settings were not recorded by run.sh.")
        _, refinement_request = resolve_refinement(root, options, saved_reads=saved["options"] if saved else None)
        refinement_preflight(refinement_request)
        # Persist downstream settings before preparation/handoff so an interrupted
        # first launch can resume with only -o, without losing its supplied reads.
        save_request(root, options, run_id, saved_reads=saved["options"] if saved else None)
        from migrated_lgz import verified_baseline
        frozen = verified_baseline(root) if ready else None
        if frozen is not None and "--max-fill" in options:
            raise RunnerError("Migrated LGZ is frozen under its original engine; use a new workspace to change LGZ science.")
        if ready and frozen is None and any(unit.unit_id.startswith("ref:") for unit in load_plan(root)):
            sys.path.insert(0, str(server_source / "tools/long_cigar_recovery"))
            from resume_reference import handoff
            from run_outer_checkpoints import OuterCheckpointManager
            handoff_report = handoff(root, server_source, run_id, load_plan(root), OuterCheckpointManager(root))
            print("[REFERENCE HANDOFF] " + json.dumps(handoff_report, ensure_ascii=True), flush=True)
        if not ready:
            if saved is None and ("--ref" not in options or "--ds" not in options):
                raise RunnerError("A new workspace requires --ref and --ds; see run.sh --help")
            if saved is None:
                if any(path.name != (".runtime" if WorkspaceLayout.detect(root).version == 2 else ".run_all") for path in root.iterdir()):
                    raise RunnerError(f"Output directory is not an empty or prepared Server workspace: {root}")
                # Store absolute input paths so preparation can also resume from another cwd.
                options.setdefault("--q0-supplement-scope", [["auto"]])
                absolute_argv = [item for key, groups in options.items() if key not in REFINEMENT_OPTIONS for values in groups for item in [key, *values]]
                if "--out" not in options:
                    absolute_argv += ["--out", str(root)]
                saved = {"schema_version": 1, "prepared": False, "argv": absolute_argv,
                         "options": {key: value for key, value in options.items() if key not in REFINEMENT_OPTIONS}, "inputs": input_identities(options)}
                atomic_write_json(manifest_path, saved)
            prepare_argv = saved["argv"]
            # Pre-auto launches did not record the implicit full search. An
            # interrupted preparation still belongs to that original scope.
            if "--q0-supplement-scope" not in saved["options"]:
                prepare_argv = [*prepare_argv, "--q0-supplement-scope", "full"]
            status = prepare_workspace(server_source / "prepare.sh", prepare_argv, root)
            if status:
                return status
            load_plan(root)
            saved["prepared"] = True
            atomic_write_json(manifest_path, saved)
        update_resources(root, options, run_id)
        if "--max-fill" in options:
            limit = options["--max-fill"][-1][0]
            update_fill_limit(root, limit)
            if saved:
                saved["effective_max_fill"] = int(limit)
                atomic_write_json(manifest_path, saved)
        save_request(root, options, run_id, saved_reads=saved["options"] if saved else None)
        ensure_plan(root)
        units = load_plan(root)
        return Runner(root, units, run_id).run()
    finally:
        lock.release()


def main() -> int:
    try:
        return execute(sys.argv[1:], Path(__file__).resolve().parents[1])
    except (OSError, ValueError, KeyError, RunnerError, OrchestrationContractError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
