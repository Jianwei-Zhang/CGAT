#!/usr/bin/env python3

"""Execute the generated Server plan with live logging and workspace locking."""

from __future__ import annotations

try:
    from workspace_layout import workspace_join
except ModuleNotFoundError:
    from .workspace_layout import workspace_join


from delivery_archive import delivery_path, delivery_staging_path

import argparse
import csv
import errno
import json
import os
import shutil
import signal
import socket
import subprocess
import threading
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from run_progress import ProgressDisplay, plain
from workspace_layout import WorkspaceLayout, workspace_path
from run_resources import execution_threads, read_resources, resource_environment
from minimap2_diagnostics import (CIGAR_ASSERTION_CODE, CIGAR_ASSERTION_HINT,
                                  changed_log_hint, cigar_assertion_hint, log_identity, runtime_snapshot)
from run_outer_checkpoints import OuterCheckpointManager, PreparedOuterCheckpoint
from run_orchestration import OrchestrationContractError, atomic_write_json
from server_report import ReportSession, finalize_delivery_archives_from_staging
from alignment_tasks import AdaptiveDispatcher, AlignmentTask, dispatch_environment, load_tasks, run_tasks


PLAN_FIELDS = ["unit_id", "command_relpath", "detail_log_relpath"]
STATUS_FIELDS = [
    "unit_id",
    "phase_index",
    "phase_total",
    "state",
    "attempt",
    "started_at",
    "ended_at",
    "elapsed_seconds",
    "exit_code",
    "detail_log_relpath",
]
LGZ_CACHE_MARKERS = {
    "grt_prepare": ("LGZ prepare inputs are current:",),
    "grt_step1": ("LGZ step1 cache hit:",),
    "grt_step2": ("LGZ step2 cache hit:",),
    "grt_step12": ("LGZ step1 cache hit:", "LGZ step2 cache hit:"),
    "grt_step3": ("LGZ step3 cache hit:",),
}

STAGE_CACHE_MARKERS = {**LGZ_CACHE_MARKERS, "degap_gapfill": ("DEGAP gapfill cache hit:",)}

class RunnerError(RuntimeError):
    """Raised for an invalid plan, lock, or execution state."""


@dataclass(frozen=True)
class PlanUnit:
    unit_id: str
    command_relpath: str
    detail_log_relpath: str


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _checkpoint_timing(started: float, inputs_checked: float) -> str:
    # Cached stages still have zero command time; report validation separately.
    return (f"checkpoint_prepare={inputs_checked - started:.3f}s "
            f"checkpoint_validate={time.monotonic() - inputs_checked:.3f}s")


def process_start_identity(pid: int) -> str:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
        return fields[21] if len(fields) > 21 else ""
    except (OSError, UnicodeError):
        return ""


def process_is_alive(pid: int, expected_start: str) -> bool:
    if pid < 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    if expected_start:
        actual_start = process_start_identity(pid)
        return bool(actual_start and actual_start == expected_start)
    return True


def validate_relative_path(value: str, label: str) -> str:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise RunnerError(f"invalid {label}: {value!r}")
    return path.as_posix()


def load_plan(server_dir: Path) -> list[PlanUnit]:
    layout = WorkspaceLayout.detect(server_dir)
    plan_path = layout.path(".run_all/plan.tsv")
    if not plan_path.is_file():
        raise RunnerError(f"execution plan is missing: {plan_path}")
    try:
        with plan_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if list(reader.fieldnames or []) != PLAN_FIELDS:
                raise RunnerError(
                    f"invalid execution plan header: expected {PLAN_FIELDS}, got {reader.fieldnames}"
                )
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise RunnerError(f"cannot read execution plan {plan_path}: {exc}") from exc
    if not rows:
        raise RunnerError("execution plan contains no units")

    units: list[PlanUnit] = []
    seen: set[str] = set()
    for row in rows:
        unit_id = row.get("unit_id", "")
        if not unit_id or any(character in unit_id for character in "\t\r\n"):
            raise RunnerError(f"invalid execution unit ID: {unit_id!r}")
        if unit_id in seen:
            raise RunnerError(f"duplicate execution unit ID: {unit_id}")
        seen.add(unit_id)
        command_relpath = validate_relative_path(
            row.get("command_relpath", ""), f"command path for {unit_id}"
        )
        detail_relpath = validate_relative_path(
            row.get("detail_log_relpath", ""), f"detail log path for {unit_id}"
        )
        command_relpath = layout.relative(command_relpath)
        detail_relpath = layout.relative(detail_relpath)
        command_path = layout.path(command_relpath)
        if not command_path.is_file():
            raise RunnerError(f"command script for {unit_id} is missing: {command_path}")
        units.append(PlanUnit(unit_id, command_relpath, detail_relpath))
    return units


def atomic_write_status(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=STATUS_FIELDS,
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_prior_status(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if list(reader.fieldnames or []) != STATUS_FIELDS:
                return {}
            return {
                row["unit_id"]: row
                for row in reader
                if row.get("unit_id") and row.get("attempt", "").isdigit()
            }
    except (OSError, UnicodeError, csv.Error):
        return {}


def initial_status_rows(
    units: list[PlanUnit], prior: dict[str, dict[str, str]]
) -> tuple[list[dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    abandoned: list[str] = []
    total = len(units)
    now = timestamp()
    for index, unit in enumerate(units, start=1):
        previous = prior.get(unit.unit_id, {})
        previous_state = previous.get("state", "")
        state = "interrupted" if previous_state == "running" else "pending"
        if state == "interrupted":
            abandoned.append(unit.unit_id)
        rows.append(
            {
                "unit_id": unit.unit_id,
                "phase_index": str(index),
                "phase_total": str(total),
                "state": state,
                "attempt": previous.get("attempt", "0"),
                "started_at": previous.get("started_at", "") if state == "interrupted" else "",
                "ended_at": now if state == "interrupted" else "",
                "elapsed_seconds": previous.get("elapsed_seconds", "") if state == "interrupted" else "",
                "exit_code": previous.get("exit_code", "") if state == "interrupted" else "",
                "detail_log_relpath": unit.detail_log_relpath,
            }
        )
    return rows, abandoned


class WorkspaceLock:
    def __init__(self, server_dir: Path, run_id: str, *, for_migration: bool = False):
        self.server_dir = server_dir
        # Recovery must acquire the legacy lock even while ordinary launches
        # are blocked by an unfinished migration journal.
        self.state_dir = (server_dir / ".run_all" if for_migration
                          else workspace_path(server_dir, ".run_all"))
        self.lock_dir = self.state_dir / "lock"
        self.run_id = run_id
        self.for_migration = for_migration
        self.owner = {
            "workspace": str(server_dir),
            "hostname": socket.gethostname(),
            "pid": os.getpid(),
            "process_start": process_start_identity(os.getpid()),
            "run_id": run_id,
            "acquired_at": timestamp(),
        }
        self.acquired = False

    def _existing_owner(self) -> dict[str, object]:
        try:
            value = json.loads((self.lock_dir / "owner.json").read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}

    def _owner_is_active(self, owner: dict[str, object]) -> bool:
        # A migration cannot infer cross-node inactivity from a missing/broken
        # owner record or an unexpected workspace identity.
        if self.for_migration and (not owner or owner.get("workspace") != str(self.server_dir)
                                   or not owner.get("hostname")
                                   or type(owner.get("pid")) is not int or owner["pid"] < 1
                                   or (owner.get("process_start") and
                                       (not isinstance(owner["process_start"], str)
                                        or not owner["process_start"].isdigit()))):
            return True
        if owner.get("workspace") != str(self.server_dir):
            return False
        if owner.get("hostname") != socket.gethostname():
            return True
        try:
            pid = int(owner.get("pid", 0))
        except (TypeError, ValueError):
            return False
        return process_is_alive(pid, str(owner.get("process_start", "")))

    def acquire(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        for _ in range(4):
            # POSIX rename may replace an empty directory. During migration an
            # ownerless lock is uncertain, not permission to steal that lock.
            if self.for_migration and (self.lock_dir.exists() or self.lock_dir.is_symlink()):
                owner = self._existing_owner()
                if self.lock_dir.is_symlink() or self._owner_is_active(owner):
                    raise RunnerError("workspace is already running or migration lock ownership is unknown")
            temporary = Path(
                tempfile.mkdtemp(prefix=".lock.", dir=self.state_dir)
            )
            try:
                atomic_write_json(temporary / "owner.json", self.owner)
                try:
                    temporary.rename(self.lock_dir)
                    self.acquired = True
                    return
                except OSError as exc:
                    if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                        raise
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)

            owner = self._existing_owner()
            if self._owner_is_active(owner):
                raise RunnerError(
                    "workspace is already running: "
                    f"run_id={owner.get('run_id', 'unknown')} "
                    f"host={owner.get('hostname', 'unknown')} "
                    f"pid={owner.get('pid', 'unknown')}"
                )
            stale = self.state_dir / f".stale-lock.{uuid.uuid4().hex}"
            try:
                self.lock_dir.rename(stale)
            except FileNotFoundError:
                continue
            shutil.rmtree(stale, ignore_errors=True)
        raise RunnerError(f"could not acquire workspace lock: {self.lock_dir}")

    def release(self) -> None:
        if not self.acquired:
            return
        owner = self._existing_owner()
        if owner.get("run_id") != self.run_id:
            return
        stale = self.state_dir / f".released-lock.{uuid.uuid4().hex}"
        try:
            self.lock_dir.rename(stale)
        except FileNotFoundError:
            self.acquired = False
            return
        shutil.rmtree(stale, ignore_errors=True)
        self.acquired = False


class Runner:
    def __init__(self, server_dir: Path, units: list[PlanUnit], run_id: str, *, log_style="compact", color="auto"):
        self.server_dir = server_dir
        self.units = units
        self.run_id = run_id
        self.logs_dir = workspace_join(server_dir, "logs")
        self.log_path = self.logs_dir / "run_all.log"
        self.status_path = self.logs_dir / "status.tsv"
        self.status_rows: list[dict[str, str]] = []
        self.log_handle = None
        self.progress = ProgressDisplay(
            self.logs_dir / "progress.log",
            {unit.unit_id: f"{index:02d}/{len(units):02d}" for index, unit in enumerate(units, 1)},
            style=log_style, color=color,
        )
        self.active_child: subprocess.Popen[str] | None = None
        self.active_children: dict[int, subprocess.Popen] = {}
        self.received_signal: int | None = None
        self.outer_checkpoints = OuterCheckpointManager(server_dir)
        self.child_cache_markers: set[str] = set()
        self.report: ReportSession | None = None
        self.minimap2_failure_hints: dict[str, str] = {}
        self.child_environment = resource_environment(server_dir)
        self.refinement_exit_code = 0
        self.refinement_child = None
        self.refinement_stop_timer = None

    def _event(self, event: str, unit: PlanUnit | None, message: str) -> None:
        if unit is None:
            position = "-/-"
            unit_id = "run_all"
        else:
            index = next(
                index for index, candidate in enumerate(self.units, start=1) if candidate == unit
            )
            position = f"{index}/{len(self.units)}"
            unit_id = unit.unit_id
        message = plain(message)
        line = (
            f"{timestamp()} [run={self.run_id}] [{position}] "
            f"[{event}] [{unit_id}] {message}"
        )
        self.progress.raw(line)
        assert self.log_handle is not None
        self.log_handle.write(line + "\n")
        self.log_handle.flush()

        if self.report is not None:
            self.report.event(event, unit, message, self._row(unit) if unit else None)
        self.progress.event(event, unit_id, message)

    def _stream_child(self, unit: PlanUnit, child: subprocess.Popen[str]) -> None:
        assert child.stdout is not None
        for raw_line in child.stdout:
            self._child_line(unit, raw_line.rstrip("\r\n"))

    def _child_line(self, unit: PlanUnit, line: str) -> None:
        line = plain(line)
        hint = cigar_assertion_hint(line)
        if hint or CIGAR_ASSERTION_CODE in line:
            self.minimap2_failure_hints[unit.unit_id] = hint or CIGAR_ASSERTION_HINT
        assert self.log_handle is not None
        if self.report is not None:
            self.report.child_output(line, unit.unit_id)
        # Old embedded workspace tools can still emit the former public name.
        cache_line = "LGZ " + line[4:] if line.startswith("GRT ") else line
        for marker in STAGE_CACHE_MARKERS.get(unit.unit_id, ()):
            if cache_line.startswith(marker):
                self.child_cache_markers.add(marker)
        rendered = f"{timestamp()} [run={self.run_id}] [CHILD] [{unit.unit_id}] {line}"
        self.progress.raw(rendered)
        self.log_handle.write(rendered + "\n")
        self.log_handle.flush()
        self.progress.child(unit.unit_id, line)

    def _failure_logs(self, unit: PlanUnit, command: Path) -> dict:
        # Never attribute another parallel unit's assertion from the shared run log.
        paths = {command.parent / "stderr.log", workspace_join(self.server_dir, unit.detail_log_relpath)}
        return {path: log_identity(path) for path in paths if path.resolve() != self.log_path.resolve()}

    def _failure_hint(self, unit: PlanUnit, logs: dict) -> str:
        hint = self.minimap2_failure_hints.get(unit.unit_id, "")
        if not hint:
            hint = next((hint for path, before in logs.items()
                         if (hint := changed_log_hint(path, before))), "")
        return f"; {hint}" if hint else ""

    def _handle_signal(self, signal_number: int, _frame: object) -> None:
        if self.received_signal is None:
            self.received_signal = signal_number
        child = self.active_child
        if child is not None and child.poll() is None:
            try:
                os.killpg(child.pid, signal_number)
            except ProcessLookupError:
                pass
        if self.refinement_child is not None and self.refinement_stop_timer is None:
            # Native tools can ignore TERM or keep inherited pipes open after
            # their worker exits. Bound cancellation without releasing the lock.
            self.refinement_stop_timer = threading.Timer(5, self._kill_refinement_group, (self.refinement_child.pid,))
            self.refinement_stop_timer.daemon = True
            self.refinement_stop_timer.start()
        for child in list(self.active_children.values()):
            try:
                os.killpg(child.pid, signal_number)
            except ProcessLookupError:
                pass

    @staticmethod
    def _kill_refinement_group(pid):
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def _finish_refinement_group(self):
        if self.received_signal is not None and self.refinement_child is not None:
            self._kill_refinement_group(self.refinement_child.pid)
        if self.refinement_stop_timer is not None:
            self.refinement_stop_timer.cancel()
            self.refinement_stop_timer = None
        self.refinement_child = None

    def _run_alignment_group(self, units: list[PlanUnit], threads: int) -> int:
        """Run independent leaf commands; publish checkpoints per original unit."""
        cpu_count = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)
        budget = max(1, min(threads, cpu_count))
        by_id = {unit.unit_id: unit for unit in units}
        prepared = {}
        remaining = {}
        started = {}
        tasks = []
        for unit in units:
            row = self._row(unit)
            check_started = time.monotonic()
            checkpoint = self.outer_checkpoints.prepare(unit.unit_id, unit.command_relpath)
            assert checkpoint is not None
            inputs_checked = time.monotonic()
            valid, reason = self.outer_checkpoints.validate(checkpoint)
            check_times = _checkpoint_timing(check_started, inputs_checked)
            if valid:
                row.update(state="success", ended_at=timestamp(), elapsed_seconds="0.000", exit_code="0")
                atomic_write_status(self.status_path, self.status_rows)
                self._event(
                    "SKIP_VALID", unit,
                    f"elapsed=0.000s checkpoint={checkpoint.path.relative_to(self.server_dir)} {reason}; {check_times}",
                )
                continue
            if checkpoint.path.is_file():
                row["state"] = "stale"
                self._event("STALE", unit, f"{reason}; rerunning; {check_times}")
            unit_tasks = load_tasks(self.server_dir, unit.unit_id, unit.command_relpath)
            assert unit_tasks is not None
            if not unit_tasks:
                unit_tasks = [AlignmentTask(unit.unit_id, workspace_join(self.server_dir, unit.command_relpath), 1)]
            prepared[unit.unit_id] = checkpoint
            remaining[unit.unit_id] = len(unit_tasks)
            tasks.extend(unit_tasks)
        if not tasks:
            return 0
        dispatcher = AdaptiveDispatcher() if any(
            task.largest_fraction is not None for task in tasks
        ) else None
        allocations = {}
        self._event("PARALLEL", None, f"alignment_tasks={len(tasks)} thread_budget={budget}")

        def start(task, allocation):
            unit = by_id[task.unit_id]
            row = self._row(unit)
            if task.unit_id not in started:
                started[task.unit_id] = time.monotonic()
                row.update(state="running", attempt=str(int(row["attempt"] or "0") + 1),
                           started_at=timestamp(), ended_at="", elapsed_seconds="", exit_code="")
                atomic_write_status(self.status_path, self.status_rows)
                self._event("START", unit, f"attempt={row['attempt']} command={unit.command_relpath}")
            self._event("TASK_START", unit, f"threads={allocation} command={task.command.relative_to(self.server_dir)}")
            allocations[task.command] = (allocation, time.monotonic(), self._failure_logs(unit, task.command))

        def finish(task, code, cancelling):
            unit = by_id[task.unit_id]
            row = self._row(unit)
            remaining[task.unit_id] -= 1
            allocation, task_started, failure_logs = allocations.pop(task.command)
            if code == 0 and dispatcher is not None:
                dispatcher.complete(task, allocation, time.monotonic() - task_started)
            self._event("TASK_END", unit, f"exit_code={code} command={task.command.relative_to(self.server_dir)}")
            if row["state"] in {"failed", "interrupted"}:
                return
            if code:
                state = "interrupted" if cancelling or self.received_signal else "failed"
                row.update(state=state, ended_at=timestamp(), exit_code=str(code),
                           elapsed_seconds=f"{time.monotonic() - started[task.unit_id]:.3f}")
                atomic_write_status(self.status_path, self.status_rows)
                self._event(state.upper(), unit, f"exit_code={code} command={task.command.relative_to(self.server_dir)} detail={unit.detail_log_relpath}"
                            + (self._failure_hint(unit, failure_logs) if state == "failed" else ""))
            elif remaining[task.unit_id] == 0:
                try:
                    checkpoint = self.outer_checkpoints.commit(prepared[task.unit_id])
                except (OSError, OrchestrationContractError) as exc:
                    row.update(state="failed", ended_at=timestamp(), exit_code="2")
                    atomic_write_status(self.status_path, self.status_rows)
                    self._event("FAILED", unit, f"output validation/checkpoint failed: {exc}")
                    raise
                row.update(state="success", ended_at=timestamp(), exit_code="0",
                           elapsed_seconds=f"{time.monotonic() - started[task.unit_id]:.3f}")
                atomic_write_status(self.status_path, self.status_rows)
                self._event("SUCCESS", unit, f"elapsed={row['elapsed_seconds']}s checkpoint={checkpoint.relative_to(self.server_dir)}")

        code = 2
        try:
            code = run_tasks(
                tasks, budget, self.active_children, lambda: self.received_signal,
                start, lambda task, line: self._child_line(by_id[task.unit_id], line), finish,
                {**self.child_environment, "GPM_REPORT_RUN_ID": self.run_id},
                dispatch=dispatcher,
            )
        finally:
            if code:
                for unit in units:
                    row = self._row(unit)
                    if row["state"] == "running":
                        row.update(state="interrupted", ended_at=timestamp(), exit_code=str(code),
                                   elapsed_seconds=f"{time.monotonic() - started[unit.unit_id]:.3f}")
                        atomic_write_status(self.status_path, self.status_rows)
                        self._event("INTERRUPTED", unit, "alignment group stopped before all tasks completed")
        return code

    def _row(self, unit: PlanUnit) -> dict[str, str]:
        return next(row for row in self.status_rows if row["unit_id"] == unit.unit_id)

    def _terminal_validation(self, unit_id: str) -> tuple[bool, str]:
        if unit_id == "refinement":
            from post_lgz_refinement import validate_completion
            return validate_completion(self.server_dir, self.run_id)
        if unit_id == "degap_gapfill":
            from post_lgz_degap import validate_result
            return validate_result(self.server_dir)
        if unit_id in LGZ_CACHE_MARKERS:
            return self.outer_checkpoints.validate_lgz_unit(unit_id)
        if unit_id == "finalize_evidence":
            return self.outer_checkpoints.validate_evidence()
        if unit_id == "package_full":
            return self.outer_checkpoints.validate_package("full")
        if unit_id == "package_light":
            return self.outer_checkpoints.validate_package("light")
        return True, "no terminal validation required"

    def _emit_summary(self, lines: list[str]) -> None:
        assert self.log_handle is not None
        for line in lines:
            self.progress.summary(line)
            self.log_handle.write(plain(line) + "\n")
        self.log_handle.flush()

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        size = float(size_bytes)
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if size < 1024 or unit == "TiB":
                return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        raise AssertionError("unreachable")

    def _delivery_stagings(self) -> list[tuple[Path, Path]]:
        unit_ids = {unit.unit_id for unit in self.units}
        if not {"package_full", "package_light"}.issubset(unit_ids):
            return []
        return [
            (delivery_path(self.server_dir, kind), delivery_staging_path(self.server_dir, kind))
            for kind in ("full", "light")
        ]

    def _emit_success_summary(self, artifacts: list[dict[str, object]]) -> None:
        by_name = {str(artifact["file"]): artifact for artifact in artifacts}
        full = by_name[delivery_path(self.server_dir, "full").name]
        light = by_name[delivery_path(self.server_dir, "light").name]
        has_refinement = any(unit.unit_id == "refinement" for unit in self.units)
        self._emit_summary(
            [
                "",
                ("LGZ baseline delivery completed; refinement did not fully succeed." if self.refinement_exit_code else "GPM Server workflow completed successfully."),
                "",
                ("LGZ baseline App packages (not refined):" if has_refinement else "Final delivery packages:"),
                "  1. Full package (FASTA + report):",
                f"     {full['path']}",
                f"     Size: {self._format_size(int(full['size_bytes']))}",
                f"     SHA-256: {full['sha256']}",
                "     Use: complete App import and FASTA export.",
                "",
                "  2. Light package (report included, FASTA omitted):",
                f"     {light['path']}",
                f"     Size: {self._format_size(int(light['size_bytes']))}",
                f"     SHA-256: {light['sha256']}",
                "     Use: App import and browsing; FASTA export is unavailable.",
                "",
                ("Local LGZ process report:" if has_refinement else "Local report:"),
                f"  {workspace_join(self.server_dir, 'report/report.html')}",
                *(["Overall/refinement report (per-tool refined FASTA, Final Path and full/light App packages):",
                   str(self.server_dir / "06_report/report.html")] if (self.server_dir / "06_report/report.html").is_file() else []),
            ]
        )

    def _emit_incomplete_summary(self) -> None:
        failed = next(
            (row["unit_id"] for row in self.status_rows if row["state"] in {"failed", "interrupted"}),
            None,
        )
        lines = ["", "GPM Server workflow did not complete successfully."]
        if failed:
            lines.append(f"Failure stage: {failed}")
        lines.extend(
            [
                f"Diagnostic report: {workspace_join(self.server_dir, 'report/report.html')}",
                f"Rerun: bash {workspace_join(self.server_dir, 'run_all.sh')}",
                "No delivery package is declared final for this run.",
            ]
        )
        self._emit_summary(lines)

    def run(self) -> int:
        from migrated_lgz import verified_baseline
        frozen = verified_baseline(self.server_dir)
        frozen_units = {row["unit_id"] for row in frozen["prefix"]} if frozen else set()
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        prior = load_prior_status(self.status_path)
        self.status_rows, abandoned = initial_status_rows(self.units, prior)
        atomic_write_status(self.status_path, self.status_rows)
        mode = "resume" if prior or self.log_path.exists() else "fresh"
        self.report = ReportSession(self.server_dir, self.units, self.run_id)
        threads = "unknown"
        options = {}
        completed = False
        options_path = workspace_join(self.server_dir, "metadata/prepare_options.tsv")
        if options_path.is_file():
            try:
                with options_path.open(newline="", encoding="utf-8") as handle:
                    options = {
                        row["key"]: row["value"]
                        for row in csv.DictReader(handle, delimiter="\t")
                    }
                threads = options.get("threads", "unknown")
                if threads != "unknown":
                    threads = str(execution_threads(int(threads), root=self.server_dir))
            except (OSError, UnicodeError, csv.Error, KeyError):
                pass

        with self.log_path.open("a", encoding="utf-8", buffering=1) as log_handle, self.progress:
            self.log_handle = log_handle
            separator = (
                f"===== RUN {self.run_id} {mode.upper()} "
                f"workspace={self.server_dir} threads={threads} units={len(self.units)} ====="
            )
            self.progress.raw(separator)
            self.progress.header(self.run_id, mode, self.server_dir, threads)
            log_handle.write(separator + "\n")
            resources = read_resources(self.server_dir)
            if resources["effective"]:
                self._event("RESOURCES", None, json.dumps(resources, sort_keys=True))
            if mode == "resume":
                self._event("RESUME", None, "rechecking the prepared execution plan")
            for unit_id in abandoned:
                unit = next(item for item in self.units if item.unit_id == unit_id)
                self._event("INTERRUPTED", unit, "recovered abandoned running state")

            previous_handlers = {
                signal_number: signal.getsignal(signal_number)
                for signal_number in (signal.SIGINT, signal.SIGTERM)
            }
            for signal_number in previous_handlers:
                signal.signal(signal_number, self._handle_signal)
            try:
                if frozen is None and (options.get("alignment_engine") == "minimap2" or options.get("grt_minimap2")):
                    snapshot_path = workspace_join(self.server_dir, ".run_all/diagnostics", self.run_id, "minimap2_runtime.json")
                    try:
                        snapshot = runtime_snapshot(self.server_dir, options)
                        snapshot.update(run_id=self.run_id, recorded_at=timestamp())
                        atomic_write_json(snapshot_path, snapshot)
                        long_records = sum(item.get("over_cigar_operation_limit", 0) for item in snapshot["inputs"])
                        self._event("PREFLIGHT", None,
                                    f"minimap2 evidence={snapshot_path.relative_to(self.server_dir)} "
                                    f"long_records={long_records} (risk indicator only; parameters unchanged)")
                    except (OSError, ValueError) as exc:
                        self._event("PREFLIGHT", None, f"minimap2 evidence unavailable: {exc}; parameters unchanged")
                handled: set[str] = set()
                for unit_index, unit in enumerate(self.units):
                    if unit.unit_id in handled:
                        continue
                    if self.received_signal is not None:
                        self._event(
                            "INTERRUPTED",
                            None,
                            f"received signal {self.received_signal} between units",
                        )
                        return 128 + self.received_signal
                    if unit.unit_id in frozen_units:
                        row = self._row(unit)
                        row.update(state="success", ended_at=timestamp(), elapsed_seconds="0.000", exit_code="0")
                        atomic_write_status(self.status_path, self.status_rows)
                        self._event("SKIP_MIGRATED_LGZ", unit,
                                    "elapsed=0.000s validated original-engine frozen LGZ; no new-engine checkpoint created")
                        continue
                    kind = unit.unit_id.split(":", 1)[0]
                    if kind in {"ref", "q0_chr", "chr"} and load_tasks(self.server_dir, unit.unit_id, unit.command_relpath) is not None:
                        group = []
                        for candidate in self.units[unit_index:]:
                            if candidate.unit_id.split(":", 1)[0] != kind or load_tasks(self.server_dir, candidate.unit_id, candidate.command_relpath) is None:
                                break
                            group.append(candidate)
                        result = self._run_alignment_group(group, int(threads))
                        handled.update(candidate.unit_id for candidate in group)
                        if result:
                            return result
                        continue
                    row = self._row(unit)
                    prepared: PreparedOuterCheckpoint | None = None
                    check_started = time.monotonic()
                    try:
                        prepared = self.outer_checkpoints.prepare(
                            unit.unit_id, unit.command_relpath
                        )
                    except OrchestrationContractError as exc:
                        row.update(
                            {
                                "state": "failed",
                                "attempt": str(int(row["attempt"] or "0") + 1),
                                "started_at": timestamp(),
                                "ended_at": timestamp(),
                                "elapsed_seconds": "0.000",
                                "exit_code": "2",
                            }
                        )
                        atomic_write_status(self.status_path, self.status_rows)
                        self._event(
                            "FAILED",
                            unit,
                            f"exit_code=2 checkpoint preparation failed: {exc} "
                            f"detail={unit.detail_log_relpath} "
                            f"rerun='bash {workspace_join(self.server_dir, 'run_all.sh')}'",
                        )
                        return 2

                    if prepared is not None:
                        inputs_checked = time.monotonic()
                        valid, reason = self.outer_checkpoints.validate(prepared)
                        check_times = _checkpoint_timing(check_started, inputs_checked)
                        if valid:
                            row.update(
                                {
                                    "state": "success",
                                    "ended_at": timestamp(),
                                    "elapsed_seconds": "0.000",
                                    "exit_code": "0",
                                }
                            )
                            atomic_write_status(self.status_path, self.status_rows)
                            self._event(
                                "SKIP_VALID",
                                unit,
                                f"elapsed=0.000s checkpoint="
                                f"{prepared.path.relative_to(self.server_dir)} {reason}; {check_times}",
                            )
                            continue
                        if prepared.path.is_file():
                            row["state"] = "stale"
                            atomic_write_status(self.status_path, self.status_rows)
                            self._event(
                                "STALE",
                                unit,
                                f"checkpoint={prepared.path.relative_to(self.server_dir)} {reason}; "
                                f"rerunning; {check_times}",
                            )

                    attempt = int(row["attempt"] or "0") + 1
                    started_at = timestamp()
                    started_monotonic = datetime.now(timezone.utc)
                    row.update(
                        {
                            "state": "running",
                            "attempt": str(attempt),
                            "started_at": started_at,
                            "ended_at": "",
                            "elapsed_seconds": "",
                            "exit_code": "",
                        }
                    )
                    atomic_write_status(self.status_path, self.status_rows)
                    self._event("START", unit, f"attempt={attempt} command={unit.command_relpath}")
                    self.child_cache_markers.clear()
                    failure_logs = self._failure_logs(unit, workspace_join(self.server_dir, unit.command_relpath))
                    child = subprocess.Popen(
                        ["bash", str(workspace_join(self.server_dir, unit.command_relpath))],
                        cwd=self.server_dir,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        bufsize=1,
                        start_new_session=True,
                        env={**dispatch_environment(
                                {**self.child_environment, "GPM_REPORT_RUN_ID": self.run_id},
                                AlignmentTask(unit.unit_id, workspace_join(self.server_dir, unit.command_relpath),
                                              int(threads) if threads != "unknown" else 1),
                                int(threads) if threads != "unknown" else 1, exclusive=True),
                             "GPM_REPORT_UNIT_ID": unit.unit_id,
                             **({"GPM_TASK_THREADS": str(threads)} if threads != "unknown" else {})},
                    )
                    self.active_child = child
                    self.refinement_child = child if unit.unit_id == "refinement" else None
                    if self.received_signal is not None:
                        self._handle_signal(self.received_signal, None)
                    self._stream_child(unit, child)
                    self._finish_refinement_group()
                    child_return_code = child.wait()
                    exit_code = (
                        128 - child_return_code
                        if child_return_code < 0
                        else child_return_code
                    )
                    self.active_child = None
                    elapsed = (datetime.now(timezone.utc) - started_monotonic).total_seconds()
                    row.update(
                        {
                            "ended_at": timestamp(),
                            "elapsed_seconds": f"{elapsed:.3f}",
                            "exit_code": str(exit_code),
                        }
                    )
                    if self.received_signal is not None:
                        row["state"] = "interrupted"
                        atomic_write_status(self.status_path, self.status_rows)
                        self._event(
                            "INTERRUPTED",
                            unit,
                            f"signal={self.received_signal} exit_code={exit_code} "
                            f"detail={unit.detail_log_relpath} rerun='bash {workspace_join(self.server_dir, 'run_all.sh')}'",
                        )
                        return 128 + self.received_signal
                    if exit_code != 0:
                        row["state"] = "failed"
                        atomic_write_status(self.status_path, self.status_rows)
                        self._event(
                            "FAILED",
                            unit,
                            f"exit_code={exit_code} detail={unit.detail_log_relpath} "
                            f"rerun='bash {workspace_join(self.server_dir, 'run_all.sh')}'"
                            + self._failure_hint(unit, failure_logs),
                        )
                        if unit.unit_id == "refinement":
                            self.refinement_exit_code = exit_code
                            continue
                        return exit_code
                    try:
                        valid, reason = self._terminal_validation(unit.unit_id)
                    except (OSError, OrchestrationContractError) as exc:
                        valid, reason = False, str(exc)
                    if not valid:
                        row["state"] = "failed"
                        row["exit_code"] = "2"
                        atomic_write_status(self.status_path, self.status_rows)
                        self._event(
                            "FAILED",
                            unit,
                            f"exit_code=2 terminal validation failed: {reason} "
                            f"detail={unit.detail_log_relpath} "
                            f"rerun='bash {workspace_join(self.server_dir, 'run_all.sh')}'",
                        )
                        if unit.unit_id == "refinement":
                            self.refinement_exit_code = 2
                            continue
                        return 2
                    cache_markers = STAGE_CACHE_MARKERS.get(unit.unit_id, ())
                    if cache_markers and self.child_cache_markers == set(cache_markers):
                        self._event("CACHE_HIT", unit, f"elapsed={elapsed:.3f}s {reason}")
                    if prepared is not None:
                        try:
                            checkpoint_path = self.outer_checkpoints.commit(prepared)
                        except (OSError, OrchestrationContractError) as exc:
                            row["state"] = "failed"
                            row["exit_code"] = "2"
                            atomic_write_status(self.status_path, self.status_rows)
                            self._event(
                                "FAILED",
                                unit,
                                f"exit_code=2 output validation/checkpoint failed: {exc} "
                                f"detail={unit.detail_log_relpath} "
                                f"rerun='bash {workspace_join(self.server_dir, 'run_all.sh')}'",
                            )
                            return 2
                        row["state"] = "success"
                        atomic_write_status(self.status_path, self.status_rows)
                        self._event(
                            "SUCCESS",
                            unit,
                            f"elapsed={elapsed:.3f}s checkpoint={checkpoint_path.relative_to(self.server_dir)}",
                        )
                        continue
                    row["state"] = "success"
                    atomic_write_status(self.status_path, self.status_rows)
                    self._event("SUCCESS", unit, f"elapsed={elapsed:.3f}s")
                self._event("FAILED" if self.refinement_exit_code else "SUCCESS", None,
                            "LGZ complete; refinement has failures" if self.refinement_exit_code else "pipeline completed")
                completed = True
                return self.refinement_exit_code
            finally:
                error = sys.exc_info()[1]
                self._finish_refinement_group()
                self.active_child = None
                for signal_number, handler in previous_handlers.items():
                    signal.signal(signal_number, handler)
                self.report.finish(str(error) if error else None)
                deliveries = self._delivery_stagings()
                if completed and deliveries:
                    try:
                        artifacts = finalize_delivery_archives_from_staging(
                            self.server_dir, deliveries
                        )
                    except Exception as exc:
                        message = f"failed to build final delivery archives: {exc}"
                        self.report.delivery_failure(message)
                        self._emit_incomplete_summary()
                        self.log_handle = None
                        raise RunnerError(message) from exc
                    self._emit_success_summary(artifacts)
                elif completed:
                    self._emit_summary(
                        [
                            "",
                            ("LGZ baseline delivery completed; refinement did not fully succeed." if self.refinement_exit_code else "GPM Server workflow completed successfully."),
                            "No delivery package units are present in this execution plan.",
                            f"Local report: {workspace_join(self.server_dir, 'report/report.html')}",
                        ]
                    )
                else:
                    self._emit_incomplete_summary()
                self.log_handle = None


def new_run_id() -> str:
    prefix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the prepared GPM2.0 Server workflow")
    parser.add_argument("--server-dir", required=True, type=Path)
    parser.add_argument("--log-style", choices=("compact", "detailed"), default="compact")
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto")
    parser.add_argument("--hifi", nargs="+", action="extend")
    parser.add_argument("--ont", nargs="+", action="extend")
    parser.add_argument("--gapfill-tools")
    parser.add_argument("--threads", "-t", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server_dir = args.server_dir.resolve()
    if not server_dir.is_dir():
        print(f"ERROR: Server workspace is missing: {server_dir}", file=sys.stderr)
        return 2
    run_id = new_run_id()
    try:
        lock = WorkspaceLock(server_dir, run_id)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    try:
        lock.acquire()
        from refinement_config import save_request, ensure_plan, resolve, preflight
        supplied = {"--" + kind: [[str(Path(path).resolve())] for path in getattr(args, kind)]
                    for kind in ("hifi", "ont") if getattr(args, kind) is not None}
        if args.gapfill_tools is not None:
            supplied["--gapfill-tools"] = [[args.gapfill_tools]]
        _, request = resolve(server_dir, supplied)
        preflight(request)
        if args.threads is not None:
            if args.threads < 1:
                raise RunnerError("--threads must be positive")
            from run_resources import update_resources
            update_resources(server_dir, {"--threads": [[str(args.threads)]]}, run_id)
        save_request(server_dir, supplied, run_id)
        ensure_plan(server_dir)
        units = load_plan(server_dir)
        runtime = workspace_join(server_dir, ".prepare_lib/tools/long_cigar_recovery")
        from migrated_lgz import verified_baseline
        if runtime.is_dir() and verified_baseline(server_dir) is None and any(unit.unit_id.startswith("ref:") for unit in units):
            # run.sh uses its own locked handoff; direct run_all.sh reaches this
            # entry instead. Do not perform the handoff twice in Runner.run().
            sys.path.insert(0, str(runtime))
            from resume_reference import handoff
            report = handoff(server_dir, workspace_join(server_dir, ".prepare_lib"), run_id, units, OuterCheckpointManager(server_dir))
            print("[REFERENCE HANDOFF] " + json.dumps(report, ensure_ascii=True), flush=True)
        return Runner(server_dir, units, run_id, log_style=args.log_style, color=args.color).run()
    except (OSError, ValueError, RunnerError, OrchestrationContractError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    finally:
        lock.release()



# Compatibility constants; persisted values remain unchanged.
GRT_CACHE_MARKERS = LGZ_CACHE_MARKERS

if __name__ == "__main__":
    raise SystemExit(main())
