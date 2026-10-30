"""Presentation-only progress output. Never used for checkpoints or report facts."""
from __future__ import annotations

import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# Strip terminal controls at the input boundary, before persistent logs/report JSON.
_ANSI = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]")
_STATUS = re.compile(r"\[(START|PROGRESS|RUNNING|CACHED|DONE|WARN|WARNING|ERROR|FAILED|INTERRUPTED|STALE|SUCCESS|CACHE_HIT|SKIP_VALID|RESUME)\]")
_COLORS = {"START": "36", "PROGRESS": "36", "RUNNING": "36", "RESUME": "36",
           "CACHED": "34", "CACHE_HIT": "34", "SKIP_VALID": "34",
           "DONE": "32", "SUCCESS": "32", "WARN": "33", "WARNING": "33", "STALE": "33",
           "ERROR": "31", "FAILED": "31", "INTERRUPTED": "31"}
_IMPORTANT = re.compile(r"\b(?:warn(?:ing)?|error|failed|fatal|exception|traceback)\b", re.I)
_METRICS = re.compile(r"^(?:LGZ|GRT) \S+(?: \S+)? (?:artifact|execution) metrics:")
_DONE = re.compile(r"^(?:LGZ|GRT) (step[23]) MUMmer (\S+): (computed|cache hit)$")
_EXECUTION = re.compile(r"^(?:LGZ|GRT) (step[23]) execution: .*\bchromosomes=(\d+)\b")
_CACHE = re.compile(r"^((?:LGZ|GRT) \S+ cache hit:) .+$")
_PARTITION = re.compile(
    r"^(?:LGZ|GRT) step[23] (?:MUMmer|screen) \S+ \d+/\d+: "
    r"(?:START|(?:SUCCESS|CACHE_HIT) \([\d.]+s\))$"
)
_PARTITION_CONFIG = re.compile(
    r"^(?:LGZ|GRT) step[23] MUMmer \S+: \d+/\d+ partitions, "
    r"workers=\d+, nucmer_threads=\d+, thread_budget=\d+$"
)


def plain(text: str) -> str:
    return _ANSI.sub("", text).replace("\r", "")


def use_color(mode: str, stream=None) -> bool:
    if mode != "auto":
        return mode == "always"
    stream = sys.stdout if stream is None else stream
    return ("NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"
            and bool(getattr(stream, "isatty", lambda: False)()))


def colorize(text: str, enabled: bool) -> str:
    text = plain(text)
    if not enabled:
        return text
    return _STATUS.sub(lambda m: f"\x1b[{_COLORS[m[1]]}m{m[0]}\x1b[0m", text)


def duration(seconds: float) -> str:
    if seconds < 0.1:
        return "<0.1s"
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{int(seconds // 60)}m {int(seconds % 60)}s"


class ProgressDisplay:
    def __init__(self, path: Path, positions: dict[str, str], *, style="compact", color="auto",
                 stream=None, clock=time.monotonic, now=None, interval=5.0, heartbeat=60.0):
        self.path, self.positions, self.style = path, positions, style
        self.stream = sys.stdout if stream is None else stream
        self.colored = use_color(color, self.stream)
        self.clock = clock
        self.now = now or (lambda: datetime.now().astimezone())
        self.interval, self.heartbeat = interval, heartbeat
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.active: dict[str, dict] = {}
        self.groups: dict[tuple[str, str], dict] = {}
        self.cached: set[str] = set()
        self.date = None
        self.handle = None
        self.thread = None

    def __enter__(self):
        self.handle = self.path.open("a", encoding="utf-8", buffering=1)
        self.thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join()
        self.handle.close()

    def _heartbeat_loop(self):
        while not self.stop.wait(1.0):
            self.tick()

    def _write(self, text: str):
        text = plain(text)
        if self.handle is not None:
            self.handle.write(text + "\n")
        if self.style == "compact":
            print(colorize(text, self.colored), file=self.stream, flush=True)

    def raw(self, text: str):
        with self.lock:
            if self.style == "detailed":
                print(colorize(text, self.colored), file=self.stream, flush=True)

    def summary(self, text: str):
        with self.lock:
            self._write(text)
            self.raw(text)

    def header(self, run_id: str, mode: str, workspace: Path, threads: str):
        with self.lock:
            now = self.now()
            self._write(f"===== GPM Server | {mode.upper()} | run={run_id} =====")
            self._write(f"Date: {now.isoformat(timespec='seconds')}")
            self._write(f"Workspace: {workspace} | threads={threads}")
            self._write("Details: logs/run_all.log | Progress: logs/progress.log")
            self.date = now.date()

    def _line(self, tag: str, unit: str, message: str):
        now = self.now()
        if now.date() != self.date:
            self._write(f"Date: {now.isoformat(timespec='seconds')}")
            self.date = now.date()
        position = self.positions.get(unit, "--/--")
        self._write(f"{now:%H:%M:%S} [{position}] [{tag}] [{unit}] {message}".rstrip())
        if unit in self.active:
            self.active[unit]["last"] = self.clock()

    def event(self, event: str, unit: str, message: str):
        with self.lock:
            message = plain(message)
            now = self.clock()
            if event == "START":
                self.active[unit] = {"started": now, "last": now}
                self.cached.discard(unit)
                self.groups = {key: group for key, group in self.groups.items() if key[0] != unit}
            if event in {"SUCCESS", "FAILED", "INTERRUPTED"}:
                for (owner, stage), group in self.groups.items():
                    if owner == unit:
                        self._progress(unit, stage, group, force=True)
                self.active.pop(unit, None)
            if event == "CACHE_HIT":
                self.cached.add(unit)
                return  # The immediately following SUCCESS includes the cache result.
            if event in {"TASK_START", "TASK_END"} and not _IMPORTANT.search(message):
                if "exit_code=" not in message or "exit_code=0 " in message:
                    return
            tag = {"SKIP_VALID": "CACHED", "SUCCESS": "DONE"}.get(event, event)
            if event == "SKIP_VALID":
                message = "validated outputs reused"
            elif event == "START":
                attempt = re.search(r"\battempt=(\d+)", message)
                message = f"attempt={attempt[1]}" if attempt else ""
            elif event == "SUCCESS" and unit != "run_all":
                elapsed = re.search(r"\belapsed=([\d.]+)s", message)
                message = duration(float(elapsed[1])) if elapsed else message
                if unit in self.cached:
                    message = "cached · " + message
            self._line(tag, unit, message)

    def _progress(self, unit: str, stage: str, group: dict, *, force=False):
        count = len(group["done"])
        if count == group["shown"]:
            return
        total = group["total"]
        if not force and group["shown"] and count != total and self.clock() - group["at"] < self.interval:
            return
        denominator = f"/{total}" if total is not None else ""
        reused = sum(value == "cache hit" for value in group["done"].values())
        self._line("PROGRESS", unit, f"{stage} MUMmer · {count}{denominator} chromosomes · "
                   f"computed={count - reused} cached={reused}")
        group["shown"], group["at"] = count, self.clock()

    def child(self, unit: str, text: str):
        with self.lock:
            text = plain(text)
            # Warnings/errors always win over metric suppression. Unknown output is kept,
            # including multiline traceback continuations and tool diagnostics.
            if _IMPORTANT.search(text):
                tag = "WARN" if re.search(r"\bwarn(?:ing)?\b", text, re.I) else "ERROR"
                self._line(tag, unit, text)
                return
            if _METRICS.match(text) or _PARTITION.fullmatch(text) or _PARTITION_CONFIG.fullmatch(text):
                return
            match = _EXECUTION.match(text)
            if match:
                self.groups[(unit, match[1])] = {"total": int(match[2]), "done": {}, "shown": 0, "at": 0.0}
            match = _DONE.match(text)
            if match:
                group = self.groups.setdefault((unit, match[1]), {"total": None, "done": {}, "shown": 0, "at": 0.0})
                group["done"][match[2]] = match[3]
                self._progress(unit, match[1], group)
                return
            text = _CACHE.sub(r"\1 reused", text)
            # Stage already appears in the prefix, but preserve distinct substage names.
            if unit.startswith("grt_"):
                for name in ("LGZ", "GRT"):
                    prefix = name + " " + unit[4:] + " "
                    if text.startswith(prefix):
                        text = text[len(prefix):]
                        break
            if text:
                self._line("INFO", unit, text)

    def tick(self):
        with self.lock:
            for (unit, stage), group in self.groups.items():
                if unit in self.active:
                    self._progress(unit, stage, group)
            for unit, timing in self.active.items():
                if self.clock() - timing["last"] >= self.heartbeat:
                    self._line("RUNNING", unit, f"still running · elapsed {duration(self.clock() - timing['started'])}")
