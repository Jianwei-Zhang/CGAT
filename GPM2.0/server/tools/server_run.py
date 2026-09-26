#!/usr/bin/env python3
"""Prepare once, then run/resume the existing Server execution plan under one lock."""
from __future__ import annotations

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

ALIASES = {"-o": "--out", "--output": "--out", "-t": "--threads", "-s": "--score", "-m": "--max-fill"}
SINGLE_OPTIONS = {
    "--out", "--threads", "--score", "--aligner", "--archive-format",
    "--minimap-preset", "--blastn-task", "--blastn-evalue", "--blastn-dust", "--winnowmap-preset",
    "--winnowmap-kmer", "--winnowmap-repeat-fraction", "--cen", "--cen-min-len",
    "--cen-min-identity", "--reads", "--reads-qc", "--grt-qc-memory-gb",
    "--grt-kmer-size", "--max-fill",
}
PATH_OPTIONS = {"--ref", "--ds", "--reads", "--cen"}


def parse_options(argv: list[str], cwd: Path) -> dict[str, list[list[str]]]:
    options: dict[str, list[list[str]]] = {}
    index = 0
    while index < len(argv):
        key = ALIASES.get(argv[index], argv[index])
        count = 0 if key == "--skip-self" else 2 if key == "--tel" else 1
        if key in {"--ref", "--ds"}:
            if index + 2 < len(argv) and not argv[index + 2].startswith("-"):
                count = 2
        elif key not in SINGLE_OPTIONS and key not in {"--skip-self", "--tel"}:
            raise RunnerError(f"Unknown argument: {key}")
        values = argv[index + 1:index + count + 1]
        if len(values) != count or any(value.startswith("--") for value in values):
            raise RunnerError(f"{key} requires a value; see run.sh --help")
        if key in PATH_OPTIONS or key == "--out":
            values[-1] = str((cwd / values[-1]).resolve())
        if key == "--max-fill" and not re.fullmatch(r"[1-9][0-9]*", values[0]):
            raise RunnerError("--max-fill must be a positive integer")
        if key in {"--ds", "--reads", "--tel"}:
            options.setdefault(key, []).append(values)
        else:
            options[key] = [values]
        index += count + 1
    return options


def input_identities(options: dict) -> dict:
    identities = {}
    for key in PATH_OPTIONS:
        for values in options.get(key, []):
            path = Path(values[-1])
            stat = path.stat()
            identities[str(path)] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    return identities


def check_resume_options(requested: dict, saved: dict, identities: dict) -> None:
    for key, value in requested.items():
        if key in {"--out", "--max-fill"}:
            continue
        if value != saved.get(key):
            raise RunnerError(f"{key} differs from the prepared workspace. Use a new -o directory for changed inputs/settings.")
    for path, identity in input_identities({k: v for k, v in requested.items() if k in PATH_OPTIONS}).items():
        if identities.get(path) != identity:
            raise RunnerError(f"Input changed since preparation: {path}. Use a new -o directory.")


def update_fill_limit(root: Path, limit: str) -> None:
    script = root / "run_grt_step23.sh"
    runtime = root / ".prepare_lib/tools/grt_step23.py"
    if "--max-fill" not in runtime.read_text(encoding="utf-8"):
        raise RunnerError("This workspace runtime predates --max-fill; update its Server runtime before changing the limit.")
    lines = script.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("python3 "):
            continue
        words = shlex.split(line)
        if not any(Path(word).name == "grt_step23.py" for word in words):
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
    raise RunnerError(f"Cannot locate Step3 command in {script}")


def prepare_workspace(script: Path, argv: list[str], root: Path) -> int:
    # Forward scheduler cancellation to preparation as well as the compute stages.
    log_path = root / "logs/prepare.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[PREPARE] workspace={root} log={log_path}", flush=True)
    log = log_path.open("a", encoding="utf-8")
    owner = json.loads((root / ".run_all/lock/owner.json").read_text())
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
              "Change only the Step3 refill limit: bash server/run.sh -o <workspace> --max-fill 2000000")
        return result.returncode
    options = parse_options(argv, Path.cwd())
    root = Path(options.get("--out", [[str(Path.cwd() / "gpm_server")]])[-1][0])
    manifest_path = root / ".run_all/launch.json"
    run_id = new_run_id()
    lock = WorkspaceLock(root, run_id)
    try:
        lock.acquire()
        saved = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
        ready = saved.get("prepared", False) if saved else (root / "run_all.sh").is_file()
        if saved:
            check_resume_options(options, saved["options"], saved["inputs"])
        elif ready and any(key not in {"--out", "--max-fill"} for key in options):
            raise RunnerError("Resume this existing workspace with run.sh -o <workspace>; its original launch settings were not recorded by run.sh.")
        if not ready:
            if saved is None and ("--ref" not in options or "--ds" not in options):
                raise RunnerError("A new workspace requires --ref and --ds; see run.sh --help")
            if saved is None:
                if any(path.name != ".run_all" for path in root.iterdir()):
                    raise RunnerError(f"Output directory is not an empty or prepared Server workspace: {root}")
                # Store absolute input paths so preparation can also resume from another cwd.
                absolute_argv = [item for key, groups in options.items() for values in groups for item in [key, *values]]
                if "--out" not in options:
                    absolute_argv += ["--out", str(root)]
                saved = {"schema_version": 1, "prepared": False, "argv": absolute_argv,
                         "options": options, "inputs": input_identities(options)}
                atomic_write_json(manifest_path, saved)
            status = prepare_workspace(server_source / "prepare.sh", saved["argv"], root)
            if status:
                return status
            load_plan(root)
            saved["prepared"] = True
            atomic_write_json(manifest_path, saved)
        if "--max-fill" in options:
            limit = options["--max-fill"][-1][0]
            update_fill_limit(root, limit)
            if saved:
                saved["effective_max_fill"] = int(limit)
                atomic_write_json(manifest_path, saved)
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
