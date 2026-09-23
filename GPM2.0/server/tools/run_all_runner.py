#!/usr/bin/env python3

"""Execute the generated Server plan with live logging and workspace locking."""

from __future__ import annotations

from delivery_archive import delivery_path

import argparse
import csv
import errno
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from run_outer_checkpoints import OuterCheckpointManager, PreparedOuterCheckpoint
from run_orchestration import OrchestrationContractError, atomic_write_json
from server_report import ReportSession, embed_report_in_delivery_archives
from alignment_tasks import AlignmentTask, load_tasks, run_tasks


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
GRT_CACHE_MARKERS = {
    "grt_prepare": ("GRT prepare inputs are current:",),
    "grt_step1": (
        "GRT step1_round1 cache hit:",
        "GRT step1_filter cache hit:",
        "GRT step1_round2 cache hit:",
    ),
    "grt_step23": ("GRT step2 cache hit:", "GRT step3 cache hit:"),
    "grt_telomere_finalize": ("GRT step4_telomere cache hit:",),
}


class RunnerError(RuntimeError):
    """Raised for an invalid plan, lock, or execution state."""


@dataclass(frozen=True)
class PlanUnit:
    unit_id: str
    command_relpath: str
    detail_log_relpath: str


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


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
    plan_path = server_dir / ".run_all/plan.tsv"
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
        command_path = server_dir / command_relpath
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
    def __init__(self, server_dir: Path, run_id: str):
        self.server_dir = server_dir
        self.state_dir = server_dir / ".run_all"
        self.lock_dir = self.state_dir / "lock"
        self.run_id = run_id
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
    def __init__(self, server_dir: Path, units: list[PlanUnit], run_id: str):
        self.server_dir = server_dir
        self.units = units
        self.run_id = run_id
        self.logs_dir = server_dir / "logs"
        self.log_path = self.logs_dir / "run_all.log"
        self.status_path = self.logs_dir / "status.tsv"
        self.status_rows: list[dict[str, str]] = []
        self.log_handle = None
        self.active_child: subprocess.Popen[str] | None = None
        self.active_children: dict[int, subprocess.Popen] = {}
        self.received_signal: int | None = None
        self.outer_checkpoints = OuterCheckpointManager(server_dir)
        self.child_cache_markers: set[str] = set()
        self.report: ReportSession | None = None

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
        line = (
            f"{timestamp()} [run={self.run_id}] [{position}] "
            f"[{event}] [{unit_id}] {message}"
        )
        print(line, flush=True)
        assert self.log_handle is not None
        self.log_handle.write(line + "\n")
        self.log_handle.flush()

        if self.report is not None:
            self.report.event(event, unit, message, self._row(unit) if unit else None)

    def _stream_child(self, unit: PlanUnit, child: subprocess.Popen[str]) -> None:
        assert child.stdout is not None
        for raw_line in child.stdout:
            self._child_line(unit, raw_line.rstrip("\r\n"))

    def _child_line(self, unit: PlanUnit, line: str) -> None:
        assert self.log_handle is not None
        if self.report is not None:
            self.report.child_output(line, unit.unit_id)
        for marker in GRT_CACHE_MARKERS.get(unit.unit_id, ()):
            if line.startswith(marker):
                self.child_cache_markers.add(marker)
        rendered = f"{timestamp()} [run={self.run_id}] [CHILD] [{unit.unit_id}] {line}"
        print(rendered, flush=True)
        self.log_handle.write(rendered + "\n")
        self.log_handle.flush()

    def _handle_signal(self, signal_number: int, _frame: object) -> None:
        if self.received_signal is None:
            self.received_signal = signal_number
        child = self.active_child
        if child is not None and child.poll() is None:
            try:
                os.killpg(child.pid, signal_number)
            except ProcessLookupError:
                pass
        for child in list(self.active_children.values()):
            try:
                os.killpg(child.pid, signal_number)
            except ProcessLookupError:
                pass

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
            checkpoint = self.outer_checkpoints.prepare(unit.unit_id, unit.command_relpath)
            assert checkpoint is not None
            valid, reason = self.outer_checkpoints.validate(checkpoint)
            if valid:
                row.update(state="success", ended_at=timestamp(), elapsed_seconds="0.000", exit_code="0")
                atomic_write_status(self.status_path, self.status_rows)
                self._event("SKIP_VALID", unit, f"elapsed=0.000s checkpoint={checkpoint.path.relative_to(self.server_dir)} {reason}")
                continue
            if checkpoint.path.is_file():
                row["state"] = "stale"
                self._event("STALE", unit, f"{reason}; rerunning")
            unit_tasks = load_tasks(self.server_dir, unit.unit_id, unit.command_relpath)
            assert unit_tasks is not None
            if not unit_tasks:
                unit_tasks = [AlignmentTask(unit.unit_id, self.server_dir / unit.command_relpath, 1)]
            prepared[unit.unit_id] = checkpoint
            remaining[unit.unit_id] = len(unit_tasks)
            tasks.extend(unit_tasks)
        if not tasks:
            return 0
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

        def finish(task, code, cancelling):
            unit = by_id[task.unit_id]
            row = self._row(unit)
            remaining[task.unit_id] -= 1
            self._event("TASK_END", unit, f"exit_code={code} command={task.command.relative_to(self.server_dir)}")
            if row["state"] in {"failed", "interrupted"}:
                return
            if code:
                state = "interrupted" if cancelling or self.received_signal else "failed"
                row.update(state=state, ended_at=timestamp(), exit_code=str(code),
                           elapsed_seconds=f"{time.monotonic() - started[task.unit_id]:.3f}")
                atomic_write_status(self.status_path, self.status_rows)
                self._event(state.upper(), unit, f"exit_code={code} command={task.command.relative_to(self.server_dir)} detail={unit.detail_log_relpath}")
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
                {**os.environ, "GPM_REPORT_RUN_ID": self.run_id},
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
        if unit_id in GRT_CACHE_MARKERS:
            return self.outer_checkpoints.validate_grt_unit(unit_id)
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
            print(line, flush=True)
            self.log_handle.write(line + "\n")
        self.log_handle.flush()

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        size = float(size_bytes)
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if size < 1024 or unit == "TiB":
                return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        raise AssertionError("unreachable")

    def _delivery_archives(self) -> list[Path]:
        unit_ids = {unit.unit_id for unit in self.units}
        if not {"package_full", "package_light"}.issubset(unit_ids):
            return []
        return [delivery_path(self.server_dir, kind) for kind in ("full", "light")]

    def _emit_success_summary(self, artifacts: list[dict[str, object]]) -> None:
        by_name = {str(artifact["file"]): artifact for artifact in artifacts}
        full = by_name[delivery_path(self.server_dir, "full").name]
        light = by_name[delivery_path(self.server_dir, "light").name]
        self._emit_summary(
            [
                "",
                "GPM Server workflow completed successfully.",
                "",
                "Final delivery packages:",
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
                "Local report:",
                f"  {self.server_dir / 'report/report.html'}",
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
                f"Diagnostic report: {self.server_dir / 'report/report.html'}",
                f"Rerun: bash {self.server_dir / 'run_all.sh'}",
                "No delivery package is declared final for this run.",
            ]
        )
        self._emit_summary(lines)

    def run(self) -> int:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        prior = load_prior_status(self.status_path)
        self.status_rows, abandoned = initial_status_rows(self.units, prior)
        atomic_write_status(self.status_path, self.status_rows)
        mode = "resume" if prior or self.log_path.exists() else "fresh"
        self.report = ReportSession(self.server_dir, self.units, self.run_id)
        threads = "unknown"
        completed = False
        options_path = self.server_dir / "metadata/prepare_options.tsv"
        if options_path.is_file():
            try:
                with options_path.open(newline="", encoding="utf-8") as handle:
                    options = {
                        row["key"]: row["value"]
                        for row in csv.DictReader(handle, delimiter="\t")
                    }
                threads = options.get("threads", "unknown")
            except (OSError, UnicodeError, csv.Error, KeyError):
                pass

        with self.log_path.open("a", encoding="utf-8", buffering=1) as log_handle:
            self.log_handle = log_handle
            separator = (
                f"===== RUN {self.run_id} {mode.upper()} "
                f"workspace={self.server_dir} threads={threads} units={len(self.units)} ====="
            )
            print(separator, flush=True)
            log_handle.write(separator + "\n")
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
                    kind = unit.unit_id.split(":", 1)[0]
                    if kind in {"ref", "chr"} and load_tasks(self.server_dir, unit.unit_id, unit.command_relpath) is not None:
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
                            f"rerun='bash {self.server_dir / 'run_all.sh'}'",
                        )
                        return 2

                    if prepared is not None:
                        valid, reason = self.outer_checkpoints.validate(prepared)
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
                                f"{prepared.path.relative_to(self.server_dir)} {reason}",
                            )
                            continue
                        if prepared.path.is_file():
                            row["state"] = "stale"
                            atomic_write_status(self.status_path, self.status_rows)
                            self._event(
                                "STALE",
                                unit,
                                f"checkpoint={prepared.path.relative_to(self.server_dir)} {reason}; rerunning",
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
                    child = subprocess.Popen(
                        ["bash", str(self.server_dir / unit.command_relpath)],
                        cwd=self.server_dir,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        bufsize=1,
                        start_new_session=True,
                        env={**os.environ, "GPM_REPORT_RUN_ID": self.run_id,
                             "GPM_REPORT_UNIT_ID": unit.unit_id},
                    )
                    self.active_child = child
                    if self.received_signal is not None and child.poll() is None:
                        try:
                            os.killpg(child.pid, self.received_signal)
                        except ProcessLookupError:
                            pass
                    self._stream_child(unit, child)
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
                            f"detail={unit.detail_log_relpath} rerun='bash {self.server_dir / 'run_all.sh'}'",
                        )
                        return 128 + self.received_signal
                    if exit_code != 0:
                        row["state"] = "failed"
                        atomic_write_status(self.status_path, self.status_rows)
                        self._event(
                            "FAILED",
                            unit,
                            f"exit_code={exit_code} detail={unit.detail_log_relpath} "
                            f"rerun='bash {self.server_dir / 'run_all.sh'}'",
                        )
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
                            f"rerun='bash {self.server_dir / 'run_all.sh'}'",
                        )
                        return 2
                    cache_markers = GRT_CACHE_MARKERS.get(unit.unit_id, ())
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
                                f"rerun='bash {self.server_dir / 'run_all.sh'}'",
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
                self._event("SUCCESS", None, "pipeline completed")
                completed = True
                return 0
            finally:
                error = sys.exc_info()[1]
                self.active_child = None
                for signal_number, handler in previous_handlers.items():
                    signal.signal(signal_number, handler)
                self.report.finish(str(error) if error else None)
                archives = self._delivery_archives()
                if completed and archives:
                    try:
                        artifacts = embed_report_in_delivery_archives(self.server_dir, archives)
                    except Exception as exc:
                        message = f"failed to embed the final report in delivery archives: {exc}"
                        self.report.delivery_failure(message)
                        self._emit_incomplete_summary()
                        self.log_handle = None
                        raise RunnerError(message) from exc
                    self._emit_success_summary(artifacts)
                elif completed:
                    self._emit_summary(
                        [
                            "",
                            "GPM Server workflow completed successfully.",
                            "No delivery package units are present in this execution plan.",
                            f"Local report: {self.server_dir / 'report/report.html'}",
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server_dir = args.server_dir.resolve()
    if not server_dir.is_dir():
        print(f"ERROR: Server workspace is missing: {server_dir}", file=sys.stderr)
        return 2
    run_id = new_run_id()
    lock = WorkspaceLock(server_dir, run_id)
    try:
        units = load_plan(server_dir)
        lock.acquire()
        return Runner(server_dir, units, run_id).run()
    except (OSError, ValueError, RunnerError, OrchestrationContractError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
