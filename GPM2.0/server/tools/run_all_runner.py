#!/usr/bin/env python3

"""Execute the generated Server plan with live logging and workspace locking."""

from __future__ import annotations

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
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from run_orchestration import OrchestrationContractError, atomic_write_json


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
        self.received_signal: int | None = None

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

    def _stream_child(self, unit: PlanUnit, child: subprocess.Popen[str]) -> None:
        assert child.stdout is not None
        assert self.log_handle is not None
        for raw_line in child.stdout:
            line = raw_line.rstrip("\r\n")
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

    def _row(self, unit: PlanUnit) -> dict[str, str]:
        return next(row for row in self.status_rows if row["unit_id"] == unit.unit_id)

    def run(self) -> int:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        prior = load_prior_status(self.status_path)
        self.status_rows, abandoned = initial_status_rows(self.units, prior)
        atomic_write_status(self.status_path, self.status_rows)
        mode = "resume" if prior or self.log_path.exists() else "fresh"
        threads = "unknown"
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
                for unit in self.units:
                    if self.received_signal is not None:
                        self._event(
                            "INTERRUPTED",
                            None,
                            f"received signal {self.received_signal} between units",
                        )
                        return 128 + self.received_signal
                    row = self._row(unit)
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
                    row["state"] = "success"
                    atomic_write_status(self.status_path, self.status_rows)
                    self._event("SUCCESS", unit, f"elapsed={elapsed:.3f}s")
                self._event("SUCCESS", None, "pipeline completed")
                return 0
            finally:
                self.active_child = None
                for signal_number, handler in previous_handlers.items():
                    signal.signal(signal_number, handler)
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
    except (OSError, RunnerError, OrchestrationContractError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
