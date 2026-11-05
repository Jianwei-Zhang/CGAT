"""Bounded whole-query mapping against already validated ORIGINAL MMI parts.

Not a new index builder, resource detector or failure-retry strategy. An explicit
per-reference GROUP budget is required; unknown/shared node memory never admits
parallel work. Native child receipts stay native; the group has a distinct
receipt with real commands and a complete part/query matrix, not a fictional
full-index command or an extra aggregate PAF copy.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import os
from pathlib import Path
import resource
import re
import signal
import subprocess
import time

import minimap_options as mo
import native_first as nf
import trace_memory as tm
import windowed_alignment as wa

KIND = "original_index_parts_v1"
RECEIPT = "ordinary-parts.json"
GIB = 1024**3
MAPPED = re.compile(rb"\[M::worker_pipeline::[^\]]+\] mapped ([0-9]+) sequences\s*$")


def plan(args, parts, records):
    budget = getattr(args, "ordinary_group_memory_bytes", None)
    base = {"enabled": False, "scope": "explicit_per_reference_group_only",
            "node_or_shared_job_memory_used": False, "extra_index_build": False,
            "extra_threshold_probe_mapping": False, "automatic_retry": False}
    if len(parts) < 2:
        return {**base, "reason": "single_original_index_part"}
    if type(args.threads) is not int or args.threads < 2:
        return {**base, "reason": "insufficient_assigned_threads"}
    if budget is None:
        return {**base, "reason": "exclusive_reference_group_budget_unknown"}
    if type(budget) is not int or budget <= 0:
        raise wa.ExperimentError("invalid explicit ordinary reference-group memory budget")
    # Real query work must amortize scheduler/part validation overhead. This is
    # an admission floor, NOT a performance guarantee or a seed/DP RAM estimate.
    batch = mo.batch_size(getattr(args, "minimap_batch", None) or "500M")
    unit = {"K": 1000, "M": 1000000, "G": 1000000000}
    bases = int(batch[:-1]) * unit[batch[-1]] if batch[-1] in unit else int(batch)
    if sum(r["length"] for r in records) < 2 * bases:
        return {**base, "reason": "too_little_query_work_to_amortize_parallel_setup"}
    reserve = max(GIB, tm.current_virtual_bytes() + 64 * 1024**2)
    slots = min(2, len(parts))
    shares = [args.threads // slots + (i < args.threads % slots) for i in range(slots)]
    cap = (budget - reserve) // slots
    finite = [v for v in resource.getrlimit(resource.RLIMIT_AS) if v != resource.RLIM_INFINITY]
    if finite:
        cap = min(cap, *finite)
    if cap < GIB or any(2 * (p["end"] - p["start"]) > cap for p in parts):
        return {**base, "reason": "insufficient_budget_for_original_parts", "group_budget_bytes": budget}
    return {**base, "enabled": True, "reason": "original_parts_and_explicit_exclusive_budget",
            "group_budget_bytes": budget, "controller_reserve_bytes": reserve,
            "slots": slots, "thread_shares": shares, "worker_address_space_bytes": cap,
            "address_space_caps_are_not_physical_memory_reservations": True}


def contexts(parts):
    result = [{k: p[k] for k in ("part_index", "path", "sha256", "records")} for p in parts]
    names = [r["name"] for p in result for r in p["records"]]
    if [p["part_index"] for p in result] != list(range(len(result))) or len(names) != len(set(names)):
        raise wa.ExperimentError("original part order/membership is incomplete or duplicated")
    return result


def group_inputs(mm, query, parts):
    return {"tool": {"path": str(mm), "sha256": wa.verified_sha256(Path(mm))},
            "query": {"path": str(query), "sha256": wa.verified_sha256(Path(query))},
            "index_parts": contexts(parts)}


class ThresholdReader:
    """Consume new complete stderr lines only; never use a partial integer."""
    def __init__(self, path):
        self.path, self.offset, self.pending = Path(path), 0, b""

    def poll(self):
        with self.path.open("rb") as stream:
            stream.seek(self.offset)
            block = stream.read(65536)
            self.offset += len(block)
        lines = (self.pending + block).split(b"\n")
        self.pending = lines.pop()
        if len(self.pending) > nf.MAX_LOG_LINE:
            raise wa.ExperimentError("first-part threshold log exceeds bounded metadata")
        for line in lines:
            match = nf.MID_OCC.search(line + b"\n")
            if match:
                if len(match[1]) > 10 or not 1 <= int(match[1]) <= wa.INT32_MAX:
                    raise wa.ExperimentError("invalid actual first-part minimizer threshold")
                return int(match[1])
        return None


def _terminate(children):
    for child in children:
        try:
            os.killpg(child["process"].pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 5
    for child in children:
        try:
            child["process"].wait(timeout=max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child["process"].pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child["process"].wait()


def _finish(child):
    directory = child["directory"]
    execution = {"command": child["command"], "returncode": child["process"].returncode,
                 "seconds": round(time.monotonic() - child["started"], 3),
                 "assigned_threads": child["threads"], "address_space_limit_bytes": child["memory_bytes"]}
    wa.write_json(directory / "native.execution.json", execution)
    log = nf.inspect_stderr(directory / "native.stderr")
    status = nf.classify(execution, log)
    output = directory / "native.partial.paf"
    if status == "native_success":
        if not output.is_file() or output.is_symlink():
            raise wa.ExperimentError("original-part mapper success without a regular requested PAF")
        output.rename(directory / "native.complete.paf")
        output = directory / "native.complete.paf"
    receipt = {"status": status, "execution": execution, **log, "path": str(output),
               "paf_sha256": wa.sha256(output) if output.is_file() else None,
               "paf_usable": status == "native_success", "partial_PAF_reused": False,
               "stderr_sha256": wa.sha256(directory / "native.stderr"), "automatic_parameter_retry": False}
    wa.write_json(directory / "native-attempt.json", receipt)
    if status != "native_success":
        raise wa.ExperimentError("original-part native mapping failed; no retry or partial PAF reuse")
    return {"part_index": child["part_index"], "threads": child["threads"],
            "memory_bytes": child["memory_bytes"], "native": receipt,
            "receipt_sha256": wa.sha256(directory / "native-attempt.json")}


def attempt(mm, parts, query, root, args, records, admission):
    """Run all original parts exactly once; no full-index trial or extra PAF merge."""
    root = Path(root).resolve()
    current = plan(args, parts, records)
    if (not admission.get("enabled") or not current.get("enabled")
            or any(admission.get(k) != current.get(k) for k in ("group_budget_bytes", "slots", "thread_shares"))
            or admission.get("controller_reserve_bytes", 0) < current["controller_reserve_bytes"]
            or admission.get("worker_address_space_bytes", 0) > current["worker_address_space_bytes"]):
        raise wa.ExperimentError("original-part parallel execution has no current admitted group budget")
    root.mkdir(parents=True, exist_ok=False)
    binding = group_inputs(mm, query, parts)
    query_identity = nf.source_identity(Path(query))
    tool_identity = nf.source_identity(Path(mm))
    for part in parts:
        if wa.verified_sha256(Path(part["path"])) != part["sha256"]:
            raise wa.ExperimentError("original index part changed before mapping")
    report = {"schema": 1, "kind": KIND, "status": "running", **binding, "parts": [],
              "queries": records, "filter": getattr(args, "minimap_filter", None), "assigned_threads": args.threads,
              "admission": admission, "events": [], "automatic_retry": False,
              "extra_index_build": False, "extra_threshold_probe_mapping": False,
              "aggregate_native_command_fabricated": False, "extra_aggregate_PAF_copy": False}
    active, children, complete, next_part, mid, reader = {}, [], {}, 0, None, None
    started = time.monotonic()
    old_handler = signal.getsignal(signal.SIGTERM)
    def cancelled(signum, frame):
        raise InterruptedError("original-part group interrupted")
    signal.signal(signal.SIGTERM, cancelled)
    try:
        with ExitStack() as files:
            def launch(slot):
                nonlocal next_part, reader
                part = parts[next_part]
                directory = root / f"part-{next_part:04d}"
                directory.mkdir()
                output = directory / "native.partial.paf"
                threads = admission["thread_shares"][slot]
                options = argparse.Namespace(**vars(args)); options.threads = threads
                command = [mm, "-c", "-x", "asm10", *mo.native_flags(options, mid_occ=None if next_part == 0 else mid),
                           "-t", str(threads), "-o", str(output), part["path"], str(query)]
                cap = admission["worker_address_space_bytes"]
                def limits():
                    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
                    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
                wa.write_json(directory / "native.command.json", command)
                stdout = files.enter_context((directory / "native.stdout").open("xb"))
                stderr = files.enter_context((directory / "native.stderr").open("xb"))
                process = subprocess.Popen(command, stdout=stdout, stderr=stderr,
                    start_new_session=True, preexec_fn=limits)
                child = {"process": process, "command": command, "directory": directory,
                         "started": time.monotonic(), "threads": threads, "memory_bytes": cap,
                         "part_index": next_part}
                children.append(child); active[slot] = child
                report["events"].append({"event": "start", "part_index": next_part, "threads": threads,
                    "mid_occ": None if next_part == 0 else mid, "after_seconds": time.monotonic() - started})
                if next_part == 0:
                    reader = ThresholdReader(directory / "native.stderr")
                next_part += 1
            launch(0)
            while active:
                if mid is None:
                    mid = reader.poll()
                    if mid is not None:
                        report["events"].append({"event": "inherit_first_part_mid_occ", "mid_occ": mid,
                                                "after_seconds": time.monotonic() - started})
                for slot, child in list(active.items()):
                    if child["process"].poll() is not None:
                        complete[child["part_index"]] = _finish(child)
                        report["events"].append({"event": "complete", "part_index": child["part_index"],
                                                "after_seconds": time.monotonic() - started})
                        del active[slot]
                    elif args.timeout is not None and time.monotonic() - child["started"] > args.timeout:
                        raise subprocess.TimeoutExpired(child["command"], args.timeout)
                if mid is not None:
                    for slot in range(admission["slots"]):
                        if slot not in active and next_part < len(parts):
                            launch(slot)
                elif not active:
                    raise wa.ExperimentError("first part completed without a complete threshold line")
                time.sleep(0.05)
            if len(complete) != len(parts) or mid is None:
                raise wa.ExperimentError("original-part query matrix did not complete")
            if (not nf.identity_unchanged(Path(query), query_identity)
                    or not nf.identity_unchanged(Path(mm), tool_identity)):
                raise wa.ExperimentError("ordinary query/tool changed while original parts were mapping")
            report.update(status="ordinary_parts_success", mid_occ=mid,
                          parts=[complete[i] for i in range(len(parts))],
                          seconds=round(time.monotonic() - started, 3))
            wa.write_json(root / RECEIPT, report)
            checked = verify(root, mm, query, parts, records, fraction=report["filter"])
            return checked
    except BaseException as error:
        report.update(status="failed_no_retry", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        _terminate([c for c in children if c["part_index"] not in complete])
        signal.signal(signal.SIGTERM, old_handler)
        report.setdefault("seconds", round(time.monotonic() - started, 3))
        # Receipt bytes returned to callers must match the final persisted bytes.
        wa.write_json(root / RECEIPT, report)


def verify(root, mm, query, parts, records, *, fraction=None):
    """Independent re-open of real native commands, outputs, source and schedule."""
    import recovery_publication as rp
    root = Path(root)
    report = rp.read_json(root / RECEIPT, root)
    require = rp.require
    require(report.get("schema") == 1 and report.get("kind") == KIND
            and report.get("status") == "ordinary_parts_success", "incomplete original-part group")
    require(all(report.get(k) is False for k in ("automatic_retry", "extra_index_build",
        "extra_threshold_probe_mapping", "aggregate_native_command_fabricated", "extra_aggregate_PAF_copy")),
        "group introduced a trial, retry or fabricated aggregate command")
    require(all(report.get(k) == v for k,v in group_inputs(mm, query, parts).items())
            and report.get("queries") == records and report.get("filter") == fraction,
            "original-part source/tool/query/partition/filter binding differs")
    mid = report.get("mid_occ")
    require(type(mid) is int and 1 <= mid <= wa.INT32_MAX, "invalid actual shared threshold")
    admission = report.get("admission", {})
    slots, shares = admission.get("slots"), admission.get("thread_shares", [])
    require(admission.get("enabled") is True and admission.get("scope") == "explicit_per_reference_group_only"
        and type(slots) is int and slots == min(2, len(parts)) and type(shares) is list and len(shares) == slots
        and all(type(n) is int and n > 0 for n in shares)
        and type(report.get("assigned_threads")) is int and sum(shares) == report["assigned_threads"]
        and abs(shares[0] - shares[-1]) <= 1, "invalid partition CPU admission")
    budget, reserve, cap = (admission.get(k) for k in ("group_budget_bytes", "controller_reserve_bytes", "worker_address_space_bytes"))
    require(all(type(n) is int and n > 0 for n in (budget,reserve,cap)) and reserve >= GIB
        and slots * cap + reserve <= budget, "partition group memory budget oversubscribed")
    leaves = report.get("parts", [])
    require(len(leaves) == len(parts) and [p.get("part_index") for p in leaves] == list(range(len(parts))),
            "original part completion missing, duplicated or reordered")
    seen, active, started, finished, inherited = set(), {}, {}, set(), False
    first_completed = False
    previous = -1.0
    for event in report.get("events", []):
        stamp = event.get("after_seconds")
        require(type(stamp) in (int,float) and stamp >= previous, "partition schedule time/order changed")
        previous = stamp
        kind, i = event.get("event"), event.get("part_index")
        if kind == "inherit_first_part_mid_occ":
            require(not inherited and 0 in seen and not first_completed and event.get("mid_occ") == mid, "threshold did not come from actual part zero")
            inherited = True
        elif kind == "start":
            require(type(i) is int and i == len(seen) and i < len(parts) and (i == 0 or inherited), "part launched before original threshold or twice")
            require(event.get("mid_occ") == (None if i == 0 else mid), "part start has inconsistent threshold")
            n = event.get("threads")
            require(type(n) is int and n in shares and len(active) < slots, "part launch grant exceeds available slots")
            seen.add(i); active[i] = n; started[i] = n
            require(sum(active.values()) <= sum(shares), "partition schedule exceeds granted thread budget")
        elif kind == "complete":
            require(i in active and i not in finished, "foreign/repeated partition completion")
            del active[i]; finished.add(i)
            if i == 0:
                first_completed = True
        else:
            require(False, "unknown partition execution event")
    require(not active and finished == set(range(len(parts))) and inherited, "incomplete part schedule")
    for i, (part, leaf) in enumerate(zip(parts, leaves)):
        require(wa.verified_sha256(Path(part["path"])) == part["sha256"], "original MMI bytes changed")
        directory = root / f"part-{i:04d}"
        require(not directory.is_symlink() and root.resolve() in directory.resolve().parents,
                "native part directory escaped group ownership")
        receipt = rp.verify_attempt(directory / "native-attempt.json", root, "native_success",
            tool=mm, target=part["path"], query=query, fraction=fraction if i == 0 else None,
            mid_occ=None if i == 0 else mid)
        require(Path(receipt["path"]).resolve().parent == directory.resolve(), "native PAF escaped original part directory")
        require(receipt == leaf.get("native") and wa.verified_sha256(directory / "native-attempt.json") == leaf.get("receipt_sha256"), "native part receipt changed")
        execution = receipt["execution"]
        tail = mo.command_tail(execution["command"], mm, fraction=fraction if i == 0 else None, mid_occ=None if i == 0 else mid)
        require(int(tail[1]) == leaf.get("threads") == started[i] == execution.get("assigned_threads")
            and leaf.get("memory_bytes") == execution.get("address_space_limit_bytes") == cap,
            "actual child CPU/address-space grant differs from group plan")
        require(receipt.get("index_metadata_complete") is True and receipt.get("threshold_metadata_complete") is True
            and receipt.get("index_sequence_counts") == [len(part["records"])]
            and receipt.get("mid_occ_updates") == [mid], "native part/index/threshold metadata differs")
        mapped, batches = 0, 0
        with (directory / "native.stderr").open("rb") as stream:
            while line := stream.readline(nf.MAX_LOG_LINE + 1):
                require(len(line) <= nf.MAX_LOG_LINE and line.endswith(b"\n"),
                        "native part batch log is incomplete or oversized")
                match = MAPPED.search(line)
                if match:
                    require(len(match[1]) <= 10, "native part batch count is oversized")
                    mapped += int(match[1]); batches += 1
        require(batches > 0 and mapped == len(records),
                "native part did not map the complete ordinary query group")
    return report
