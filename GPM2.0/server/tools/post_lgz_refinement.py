#!/usr/bin/env python3
"""Public post-LGZ refinement worker, using the existing runner lock/budget."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import sys

from workspace_layout import TOOL_DIRECTORIES, WorkspaceLayout
from run_orchestration import atomic_write_json, sha256_file
from run_resources import execution_threads, update_resources
from refinement_config import (resolve, save_request, load_request, preflight, json_file, validate_config, CONFIG)
from refinement_tools import fingerprint
from refinement_recipes import select_tools, select_reads
from refinement_batch import execute_batch, publish_batch, check_seal, baseline_seal
from refinement_commit import current_publication, recover_publication, targets
from refinement_delivery import validate_delivery
from job_final_catalog import publish_catalog, validate_catalog
from project_auto_patch import publish_auto_patch, validate_auto_patch
from refine_report import automatic_overview_digest
from refinement_overview import render_overview
from refinement_jobs_index import write_automatic_index
from lgz_final import publish_baseline, validate_baseline


class Terminated(KeyboardInterrupt):
    def __init__(self, number):
        self.signal_number = number
        super().__init__(f"received signal {number}")


class ParentLock:
    """A verified live parent owns the real lock; this view cannot steal it."""
    for_migration = False
    def __init__(self, root, run_id):
        from run_all_runner import process_is_alive
        self.server_dir = Path(root).resolve()
        self.state_dir = WorkspaceLayout.detect(root).path(".run_all")
        self.owner = self._existing_owner()
        self._is_alive = process_is_alive
        if (self.owner.get("run_id") != run_id or self.owner.get("pid") != os.getppid()
                or self.owner.get("hostname") != socket.gethostname() or self.owner.get("workspace") != str(self.server_dir) or not self.acquired):
            raise ValueError("refinement worker requires its live runner parent's workspace lock")
    def _existing_owner(self):
        return json_file(self.state_dir / "lock/owner.json")
    @property
    def acquired(self):
        return (self.owner == self._existing_owner()
                and self._is_alive(self.owner["pid"], self.owner.get("process_start", "")))


def overview_members(layout, batch):
    files = ["06_report/report.html"]
    if not layout.project_delivery or batch["tools"]:
        files.extend(f"06_report/03_comparison/{batch['batch_id']}/{name}" for name in
                     ("comparison.json", "original_gaps.json", "gap_comparison.tsv"))
    return files


def final_result_lines(tool, paths, provenance, *, fasta=None, project_delivery=False):
    """Do not label a successful zero-admission run as an applied refinement."""
    accepted = provenance["accepted_edit_count"]
    counts = provenance["counts"]
    outcome = (f"[REFINEMENT OUTCOME] {tool}: status={provenance['status']} "
               f"accepted_edits={accepted} closed={counts['closed']} partial={counts['partial']} "
               f"unfilled={counts['unfilled']} rejected={counts['rejected']}")
    label = "REFINED FINAL" if accepted else "UNCHANGED AFTER REFINEMENT; ZERO ACCEPTED EDITS"
    return [outcome, f"[{label}] {tool}: {fasta if fasta is not None else paths['final'] / 'assembly.fa'}",
            f"[FINAL PATH] {tool}: {paths['final'] / 'final_path.json'}",
            *([] if project_delivery else [f"[APP DELIVERY] {tool}: {paths['delivery']}"])]


def run(root, lock, request):
    from lgz_contract import validate_contract
    from lgz_core.contract.validation_pass import can_reuse_validation, refinement_channel
    root = Path(root).resolve()
    layout = WorkspaceLayout.detect(root)
    if layout.version != 2:
        raise ValueError("post-LGZ refinement requires explicit legacy workspace migration")
    # Existing scientific proof is checked, not rewritten to the new engine.
    channel = refinement_channel() if isinstance(lock, ParentLock) and lock.acquired else None
    started = time.monotonic()
    reused = bool(channel and can_reuse_validation(channel, root, request["run_id"]))
    if not reused:
        validate_contract(root)
    validated = time.monotonic()
    print(f"[REFINE CHECK] LGZ evidence: {'same-run reuse' if reused else 'full validation'} "
          f"in {validated - started:.2f}s", flush=True)
    publish_baseline(root, lock)
    print(f"[REFINE CHECK] LGZ baseline ready in {time.monotonic() - validated:.2f}s", flush=True)
    for tool in (TOOL_DIRECTORIES if layout.result_prefix else request["selected"]):
        pointer = layout.path(f".runtime/refinement/publication/{tool}.json")
        if pointer.exists() and json_file(pointer).get("status") == "publishing":
            recover_publication(root, lock, tool, validate_delivery)
    if layout.result_prefix and request["selected"]:
        # The LGZ genome is available even while optional native tools are running.
        publish_catalog(root, lock, request["run_id"], {t: {"status": "pending"} for t in request["selected"]})
    options = {}
    with layout.path("metadata/prepare_options.tsv").open(newline="", encoding="utf-8") as stream:
        options = {row["key"]: row["value"] for row in csv.DictReader(stream, delimiter="\t")}
    budget = execution_threads(int(options.get("threads", "1")), root=root)
    cpu = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count() or 1
    budget = min(budget, cpu)
    try:
        batch_result = execute_batch(root, request["groups"], budget, tools=request["tools"])
        batch_result = publish_batch(root, lock, batch_result)
    except (Exception, KeyboardInterrupt) as error:
        if layout.result_prefix:
            status = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
            try:
                publish_catalog(root, lock, request["run_id"], {t: {"status": status} for t in request["selected"]})
            except (OSError, ValueError, KeyError) as catalog_error:
                print(f"[GENOME RESULTS] cannot record {status} attempt: {catalog_error}", file=sys.stderr)
        raise
    batch = batch_result["batch"]
    if not batch.get("baseline_inputs"):
        batch["baseline_inputs"] = baseline_seal(root)
    if not batch.get("overview"):
        batch["overview"] = render_overview(root, batch, batch_result["staged_results"])
        atomic_write_json(layout.path(f".runtime/refinement/batches/{batch['batch_id']}.json"), batch)
    overview_paths = overview_members(layout,batch)
    receipt = {"schema": "cgat.refinement-invocation", "schema_version": 1, "run_id": request["run_id"],
               "request_sha256": fingerprint(request), "batch_id": batch["batch_id"], "exit_code": batch_result["exit_code"],
               "batch_sha256": sha256_file(layout.path(f".runtime/refinement/batches/{batch['batch_id']}.json")),
               "overview_files": {name: (automatic_overview_digest if name == "06_report/report.html" else sha256_file)(layout.path(name))
                                  for name in overview_paths}}
    if layout.result_prefix:
        receipt["final_catalog_sha256"] = publish_catalog(root, lock, request["run_id"], batch["tools"])
        receipt["auto_patch_sha256"] = publish_auto_patch(root, lock)
    completion_path = layout.path(f".runtime/refinement/completions/{request['run_id']}.json")
    atomic_write_json(completion_path, receipt)
    try:
        index = write_automatic_index(layout, completion_path)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"[REFINEMENT JOB INDEX] unavailable: {error}", file=sys.stderr, flush=True)
    else:
        if index is not None:
            print(f"[REFINEMENT JOB INDEX] {index}", flush=True)
    print(f"[REFINEMENT] status={batch['status']} exit_code={batch_result['exit_code']} threads={budget}", flush=True)
    for tool, row in batch["tools"].items():
        if row["status"] == "published":
            paths = targets(layout, tool)
            provenance = batch_result["staged_results"][tool]["provenance"]
            fasta = layout.path(f"05_final/{layout.result_prefix}.{tool}.fa") if layout.result_prefix else None
            for line in final_result_lines(tool, paths, provenance, fasta=fasta, project_delivery=layout.project_delivery):
                print(line, flush=True)
    baseline = layout.path(f"05_final/{layout.result_prefix}.lgz.fa" if layout.result_prefix else "05_final/00_lgz/assembly.fa")
    print(f"[LGZ BASELINE, NOT REFINED] {baseline}", flush=True)
    if layout.result_prefix:
        print(f"[GENOME RESULTS] {layout.path('05_final/results.tsv')}", flush=True)
    print(f"[REPORT] {layout.path('06_report/report.html')}", flush=True)
    return batch_result["exit_code"]


def validate_completion(root, run_id):
    try:
        layout = WorkspaceLayout.detect(root)
        request = load_request(root, run_id)
        receipt = json_file(layout.path(f".runtime/refinement/completions/{run_id}.json"))
        if (receipt.get("schema") != "cgat.refinement-invocation" or receipt.get("schema_version") != 1
                or receipt.get("run_id") != run_id or receipt.get("request_sha256") != fingerprint(request)
                or receipt.get("exit_code") != 0):
            return False, "refinement completion does not bind this successful invocation"
        batch_file = layout.path(f".runtime/refinement/batches/{receipt['batch_id']}.json")
        if sha256_file(batch_file) != receipt["batch_sha256"]:
            return False, "refinement batch changed after completion"
        batch = json_file(batch_file)
        if (batch.get("schema") != "cgat.refinement-batch" or batch.get("schema_version") != 1
                or batch.get("batch_id") != receipt["batch_id"] or batch["exit_code"] != 0
                or set(batch["tools"]) != set(request["selected"])):
            return False, "refinement batch is incomplete"
        overview_paths = set(overview_members(layout,batch))
        if (set(receipt.get("overview_files", {})) != overview_paths
                or any(layout.path(name).is_symlink() or
                       (automatic_overview_digest if name == "06_report/report.html" else sha256_file)(layout.path(name)) != digest
                       for name, digest in receipt["overview_files"].items())):
            return False, "refinement overview/comparison report changed or is incomplete"
        if layout.result_prefix:
            validate_catalog(layout, receipt.get("final_catalog_sha256"))
            validate_auto_patch(layout, receipt["auto_patch_sha256"])
        if not validate_baseline(root):
            return False, "explicit LGZ baseline publication changed or is incomplete"
        check_seal(batch.get("baseline_inputs", {}))
        check_seal(batch.get("reads_inputs", {}))
        for tool, row in batch["tools"].items():
            publication = current_publication(root, tool)
            if row["status"] != "published" or not publication or publication["run_id"] != row["run_id"]:
                return False, "refinement final/report/App delivery is not committed for this invocation"
        return True, "refinement batch and all requested publications are complete"
    except (OSError, ValueError, KeyError, TypeError) as error:
        return False, str(error)


def run_child_group(command, *, environment, cwd=None, output=None, rusage_out=None):
    """Keep the workspace lock until the worker and its native group stop.

    Direct invocations use the same verified parent/worker boundary as run_all.
    SIGTERM reaches native grandchildren too; a stubborn tool is killed before
    the caller may release the workspace lock.
    """
    child = None
    received = None
    deadline = None
    previous = {}

    def forward(number, _frame):
        nonlocal received, deadline
        if received is None:
            received = number
            deadline = time.monotonic() + 5
        if child is not None:
            try:
                os.killpg(child.pid, number)
            except ProcessLookupError:
                pass

    try:
        for number in (signal.SIGINT, signal.SIGTERM):
            previous[number] = signal.signal(number, forward)
        child = subprocess.Popen(command, env=environment, cwd=cwd, stdout=output,
                                 stderr=subprocess.STDOUT if output is not None else None,
                                 start_new_session=True)
        if received is not None:
            forward(received, None)
        while True:
            if hasattr(os, "wait4"):
                try:
                    pid, status_bits, rusage = os.wait4(child.pid, os.WNOHANG)
                except InterruptedError:
                    continue
                except ChildProcessError:
                    code = child.wait()
                    return 128 + received if received is not None else (128 - code if code < 0 else code)
                if pid:
                    code = -os.WTERMSIG(status_bits) if os.WIFSIGNALED(status_bits) else os.WEXITSTATUS(status_bits)
                    child.returncode = code
                    rss = getattr(rusage, "ru_maxrss", 0) or 0
                    if rusage_out is not None and rss > 0:
                        is_darwin = hasattr(os, "uname") and os.uname().sysname == "Darwin"
                        rusage_out["peak_rss_mb"] = round(rss / (1024.0 * 1024.0) if is_darwin else rss / 1024.0, 2)
                    return 128 + received if received is not None else (128 - code if code < 0 else code)
                if deadline is not None and time.monotonic() >= deadline:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                time.sleep(0.05)
            else:
                try:
                    code = child.wait(timeout=0.1)
                    return 128 + received if received is not None else (128 - code if code < 0 else code)
                except subprocess.TimeoutExpired:
                    if deadline is not None and time.monotonic() >= deadline:
                        try:
                            os.killpg(child.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
    finally:
        if child is not None:
            if child.poll() is None:
                forward(signal.SIGTERM, None)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
            if received is not None:
                # The worker can exit while an uncooperative native grandchild
                # remains in the group. Do not unlock while it can still write.
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        for number, handler in previous.items():
            signal.signal(number, handler)


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-dir", required=True, type=Path)
    parser.add_argument("--hifi", nargs="+", action="extend", default=None)
    parser.add_argument("--ont", nargs="+", action="extend", default=None)
    parser.add_argument("--gapfill-tools")
    parser.add_argument("--threads", type=int)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check-environment", action="store_true")
    mode.add_argument("--configure-prepare", action="store_true")
    mode.add_argument("--runner-owned", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main():
    args = arguments()
    root = args.server_dir.resolve()
    supplied = {"--" + kind: [[str(Path(path).resolve())] for path in getattr(args, kind)]
                for kind in ("hifi", "ont") if getattr(args, kind) is not None}
    if args.gapfill_tools is not None:
        supplied["--gapfill-tools"] = [[args.gapfill_tools]]
    try:
        if args.check_environment:
            groups = {kind: [row[0] for row in supplied.get("--" + kind, [])] for kind in ("hifi", "ont")}
            tools = select_tools(args.gapfill_tools, has_reads=any(groups.values()))
            if any(groups.values()):
                select_reads("degap", groups)
            preflight({"groups": groups, "selected": tools})
            return 0
        if args.configure_prepare:
            stable, _ = resolve(root, supplied)
            # prepare.sh stores a configuration, not an invocation; explicit
            # none here remains disabled until the next explicit tool choice.
            if args.gapfill_tools == "none":
                stable["tools"] = "none"
            validate_config(stable)
            atomic_write_json(WorkspaceLayout.detect(root).path(CONFIG), stable)
            return 0
        from run_all_runner import WorkspaceLock, new_run_id
        run_id = os.environ.get("GPM_REPORT_RUN_ID") if args.runner_owned else new_run_id()
        if args.runner_owned and (not run_id or supplied or args.threads is not None):
            raise ValueError("runner-owned refinement uses only its recorded invocation settings")
        lock = ParentLock(root, run_id) if args.runner_owned else WorkspaceLock(root, run_id)
        if not args.runner_owned:
            lock.acquire()
        previous = {}
        try:
            if not args.runner_owned:
                _, candidate = resolve(root, supplied)
                if candidate is None:
                    raise ValueError("legacy workspaces require explicit numbered-layout migration")
                preflight(candidate)
            if args.threads is not None:
                if args.threads < 1:
                    raise ValueError("--threads must be positive")
                update_resources(root, {"--threads": [[str(args.threads)]]}, run_id)
            request = load_request(root, run_id) if args.runner_owned else save_request(root, supplied, run_id)
            if request is None:
                raise ValueError("legacy workspaces require explicit numbered-layout migration")
            if not args.runner_owned:
                code = run_child_group(
                    [sys.executable, "-B", str(Path(__file__).resolve()), "--server-dir", str(root), "--runner-owned"],
                    environment={**os.environ, "GPM_REPORT_RUN_ID": run_id},
                )
                if WorkspaceLayout.detect(root).project_delivery:
                    # Aggregate nonzero may still have published some tools. Do not update the
                    # pair for an interrupted attempt without its completion receipt.
                    completion = WorkspaceLayout.detect(root).path(f".runtime/refinement/completions/{run_id}.json")
                    if completion.is_file():
                        from project_delivery_publish import publish_current
                        for file in publish_current(root,lock):
                            print(f"[PROJECT APP DELIVERY] {file['path']}", flush=True)
                        from refinement_jobs_index import refresh_after_delivery
                        refresh_after_delivery(root, run_id, lock)
                return code
            for number in (signal.SIGINT, signal.SIGTERM):
                previous[number] = signal.signal(number, lambda n, _frame: (_ for _ in ()).throw(Terminated(n)))
            return run(root, lock, request)
        finally:
            for number, handler in previous.items():
                signal.signal(number, handler)
            if not args.runner_owned:
                lock.release()
    except KeyboardInterrupt as error:
        return 128 + getattr(error, "signal_number", signal.SIGINT)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("ERROR: " + str(error), file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
