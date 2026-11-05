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
import ordinary_resource_grant as org
import native_first as nf
import trace_memory as tm
import windowed_alignment as wa

KIND = "original_index_parts_v1"
RECEIPT = "ordinary-parts.json"
ROUND_KIND = "original_index_part_round_v1"
MAX_ROUNDS = 128
GIB = 1024**3
MAPPED = re.compile(rb"\[M::worker_pipeline::[^\]]+\] mapped ([0-9]+) sequences\s*$")


def _address_caps(args):
    limits = [v for v in resource.getrlimit(resource.RLIMIT_AS) if v != resource.RLIM_INFINITY]
    configured = getattr(args, "memory_gib", 0)
    if type(configured) is not int or configured < 0:
        raise wa.ExperimentError("invalid configured native mapper memory limit")
    if configured:
        limits.append(configured * GIB)
    return limits


def plan(args, parts, records):
    base = {"enabled": False, "scope": "explicit_per_reference_group_only",
            "node_or_shared_job_memory_used": False, "extra_index_build": False,
            "extra_threshold_probe_mapping": False, "automatic_retry": False,
            "resource_grant": getattr(args, "ordinary_resource_grant", None)}
    if len(parts) < 2:
        return {**base, "reason": "single_original_index_part"}
    if type(args.threads) is not int or args.threads < 2:
        return {**base, "reason": "insufficient_assigned_threads"}
    budget = org.resolve(args)
    base["resource_grant"] = getattr(args, "ordinary_resource_grant", None)
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
    finite = _address_caps(args)
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


def _run(mm, parts, query, root, args, records, admission, *, selected=None, inherited_mid=None, expected_mid=None):
    """One explicit execution round; never retry a failed child within it."""
    root = Path(root).resolve()
    resumed = selected is not None
    selected = list(range(len(parts))) if selected is None else selected
    current = _round_plan(args, parts, records, selected, resumed=resumed)
    if (not admission.get("enabled") or not current.get("enabled")
            or any(admission.get(k) != current.get(k) for k in
                   ("scope", "group_budget_bytes", "slots", "thread_shares"))
            or admission.get("controller_reserve_bytes", 0) < current.get("controller_reserve_bytes", 0)
            or ((admission.get("worker_address_space_bytes") is None) != (current.get("worker_address_space_bytes") is None))
            or (current.get("worker_address_space_bytes") is not None
                and admission.get("worker_address_space_bytes", 0) > current["worker_address_space_bytes"])):
        raise wa.ExperimentError("original-part parallel execution has no current admitted group budget")
    root.mkdir(parents=True, exist_ok=False)
    binding = group_inputs(mm, query, parts)
    query_identity = nf.source_identity(Path(query))
    tool_identity = nf.source_identity(Path(mm))
    for part in parts:
        if wa.verified_sha256(Path(part["path"])) != part["sha256"]:
            raise wa.ExperimentError("original index part changed before mapping")
    report = {"schema": 1, "kind": KIND if selected == list(range(len(parts))) else ROUND_KIND,
              "status": "running", **binding, "parts": [], "selected_parts": selected,
              "inherited_mid_occ": inherited_mid,
              "queries": records, "filter": getattr(args, "minimap_filter", None), "assigned_threads": args.threads,
              "admission": admission, "events": [], "automatic_retry": False,
              "extra_index_build": False, "extra_threshold_probe_mapping": False,
              "aggregate_native_command_fabricated": False, "extra_aggregate_PAF_copy": False}
    active, children, complete, position, mid, reader = {}, [], {}, 0, inherited_mid, None
    started = time.monotonic()
    old_handler = signal.getsignal(signal.SIGTERM)
    def cancelled(signum, frame):
        raise InterruptedError("original-part group interrupted")
    signal.signal(signal.SIGTERM, cancelled)
    try:
        with ExitStack() as files:
            def launch(slot):
                nonlocal position, reader
                index = selected[position]
                part = parts[index]
                directory = root / f"part-{index:04d}"
                directory.mkdir()
                output = directory / "native.partial.paf"
                threads = admission["thread_shares"][slot]
                options = argparse.Namespace(**vars(args)); options.threads = threads
                command = [mm, "-c", "-x", "asm10", *mo.native_flags(options, mid_occ=None if index == 0 else mid),
                           "-t", str(threads), "-o", str(output), part["path"], str(query)]
                cap = admission["worker_address_space_bytes"]
                def limits():
                    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
                    if cap is not None:
                        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
                wa.write_json(directory / "native.command.json", command)
                stdout = files.enter_context((directory / "native.stdout").open("xb"))
                stderr = files.enter_context((directory / "native.stderr").open("xb"))
                process = subprocess.Popen(command, stdout=stdout, stderr=stderr,
                    start_new_session=True, preexec_fn=limits)
                child = {"process": process, "command": command, "directory": directory,
                         "started": time.monotonic(), "threads": threads, "memory_bytes": cap,
                         "part_index": index}
                children.append(child); active[slot] = child
                report["events"].append({"event": "start", "part_index": index, "threads": threads,
                    "mid_occ": None if index == 0 else mid, "after_seconds": time.monotonic() - started})
                if index == 0:
                    reader = ThresholdReader(directory / "native.stderr")
                position += 1
            if inherited_mid is not None:
                report["events"].append({"event": "inherit_completed_part_mid_occ", "mid_occ": inherited_mid,
                                         "after_seconds": time.monotonic() - started})
            launch(0)
            while active:
                if mid is None:
                    mid = reader.poll()
                    if mid is not None:
                        if expected_mid is not None and mid != expected_mid:
                            raise wa.ExperimentError("resumed first-part threshold differs from completed native parts")
                        report["events"].append({"event": "inherit_first_part_mid_occ", "mid_occ": mid,
                                                "after_seconds": time.monotonic() - started})
                failure = None
                for slot, child in list(active.items()):
                    if child["process"].poll() is not None:
                        try:
                            complete[child["part_index"]] = _finish(child)
                            report["events"].append({"event": "complete", "part_index": child["part_index"],
                                                    "after_seconds": time.monotonic() - started})
                        except wa.ExperimentError as error:
                            failure = error
                        del active[slot]
                    elif args.timeout is not None and time.monotonic() - child["started"] > args.timeout:
                        failure = subprocess.TimeoutExpired(child["command"], args.timeout)
                if failure is not None:
                    raise failure
                if mid is not None:
                    for slot in range(admission["slots"]):
                        if slot not in active and position < len(selected):
                            launch(slot)
                elif not active:
                    raise wa.ExperimentError("first part completed without a complete threshold line")
                time.sleep(0.05)
            if len(complete) != len(selected) or mid is None:
                raise wa.ExperimentError("original-part query matrix did not complete")
            if (not nf.identity_unchanged(Path(query), query_identity)
                    or not nf.identity_unchanged(Path(mm), tool_identity)):
                raise wa.ExperimentError("ordinary query/tool changed while original parts were mapping")
            report.update(status="ordinary_parts_success", mid_occ=mid,
                          parts=[complete[i] for i in sorted(complete)],
                          seconds=round(time.monotonic() - started, 3))
            wa.write_json(root / RECEIPT, report)
            checked = _verify_round(root / RECEIPT, mm, query, parts, records,
                                    fraction=report["filter"], expected_mid=expected_mid)
            return checked
    except BaseException as error:
        report.update(status="failed_no_retry", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        # Preserve every independently completed sibling before cancelling live
        # work. A failed child must not discard a successful concurrent child.
        for child in children:
            if child["part_index"] not in complete and child["process"].poll() == 0:
                try:
                    complete[child["part_index"]] = _finish(child)
                    report["events"].append({"event": "complete", "part_index": child["part_index"],
                                            "after_seconds": time.monotonic() - started})
                except wa.ExperimentError:
                    pass
        _terminate([c for c in children if c["part_index"] not in complete])
        report["parts"] = [complete[i] for i in sorted(complete)]
        report["mid_occ"] = mid
        signal.signal(signal.SIGTERM, old_handler)
        report.setdefault("seconds", round(time.monotonic() - started, 3))
        # Receipt bytes returned to callers must match the final persisted bytes.
        wa.write_json(root / RECEIPT, report)


def _verify_round(path, mm, query, parts, records, *, fraction=None, partial=False, expected_mid=None):
    """Reopen one immutable execution round; failed PAFs are never consumed."""
    import recovery_publication as rp
    path = Path(path); root = path.parent
    report = rp.read_json(path, root)
    require = rp.require
    require(not root.is_symlink(), "linked original-part execution round")
    require(report.get("schema") == 1 and report.get("kind") in (KIND, ROUND_KIND)
            and report.get("status") in (("ordinary_parts_success", "failed_no_retry") if partial
                                        else ("ordinary_parts_success",)), "incomplete original-part group")
    selected = report.get("selected_parts", list(range(len(parts))))
    require(type(selected) is list and bool(selected) and all(type(i) is int and 0 <= i < len(parts) for i in selected)
            and selected == sorted(set(selected)), "invalid selected original-part round")
    require(all(report.get(k) is False for k in ("automatic_retry", "extra_index_build",
        "extra_threshold_probe_mapping", "aggregate_native_command_fabricated", "extra_aggregate_PAF_copy")),
        "group introduced a trial, retry or fabricated aggregate command")
    require(all(report.get(k) == v for k,v in group_inputs(mm, query, parts).items())
            and report.get("queries") == records and report.get("filter") == fraction,
            "original-part source/tool/query/partition/filter binding differs")
    mid = report.get("mid_occ")
    if partial and report["status"] == "failed_no_retry" and "mid_occ" not in report:
        values = [e.get("mid_occ") for e in report.get("events", []) if e.get("event") == "inherit_first_part_mid_occ"]
        require(len(values) <= 1, "legacy failed round has conflicting threshold events")
        if values:
            report["mid_occ"] = mid = values[0]
    require(mid is None and partial and not report.get("parts") or
            type(mid) is int and 1 <= mid <= wa.INT32_MAX, "invalid actual shared threshold")
    require(expected_mid is None or mid == expected_mid or mid is None,
            "execution round threshold differs from complete original parts")
    admission = report.get("admission", {})
    slots, shares = admission.get("slots"), admission.get("thread_shares", [])
    serial = admission.get("scope") == "serial_resume_only"
    require(admission.get("enabled") is True and (serial or admission.get("scope") == "explicit_per_reference_group_only")
        and type(slots) is int and (slots == 1 if serial else 1 <= slots <= min(2, len(selected)))
        and type(shares) is list and len(shares) == slots
        and all(type(n) is int and n > 0 for n in shares)
        and type(report.get("assigned_threads")) is int and sum(shares) == report["assigned_threads"]
        and abs(shares[0] - shares[-1]) <= 1, "invalid partition CPU admission")
    budget, reserve, cap = (admission.get(k) for k in ("group_budget_bytes", "controller_reserve_bytes", "worker_address_space_bytes"))
    require((serial and budget is None and (cap is None or type(cap) is int and cap > 0) and reserve == 0)
        or (all(type(n) is int and n > 0 for n in (budget,reserve,cap)) and reserve >= GIB
            and slots * cap + reserve <= budget), "partition group memory budget oversubscribed")
    leaves = report.get("parts", [])
    if partial and report["status"] == "failed_no_retry" and not leaves:
        # Older v1 failure receipts recorded completion events but omitted the
        # corresponding leaf array. Recover ONLY independently verified native
        # success receipts for those exact events, without editing old files.
        indices = sorted(e["part_index"] for e in report.get("events", []) if e.get("event") == "complete")
        for i in indices:
            require(type(i) is int and i in selected, "foreign legacy completion event")
            directory = root / f"part-{i:04d}"
            native = rp.verify_attempt(directory / "native-attempt.json", root, "native_success",
                tool=mm, target=parts[i]["path"], query=query,
                fraction=fraction if i == 0 else None, mid_occ=None if i == 0 else mid)
            leaves.append({"part_index": i, "threads": native["execution"].get("assigned_threads"),
                "memory_bytes": native["execution"].get("address_space_limit_bytes"), "native": native,
                "receipt_sha256": wa.verified_sha256(directory / "native-attempt.json")})
        report["parts"] = leaves
    completed = [p.get("part_index") for p in leaves]
    require(all(type(i) is int and i in selected for i in completed)
            and completed == sorted(set(completed))
            and (partial and report["status"] == "failed_no_retry" or completed == selected),
            "original part completion missing, duplicated or reordered")
    seen, active, started, finished, inherited = set(), {}, {}, set(), False
    first_completed = False
    inherited_value = report.get("inherited_mid_occ")
    require(inherited_value is None if 0 in selected else
            type(inherited_value) is int and inherited_value == expected_mid == mid,
            "subset round has no verified completed first-part context")
    previous = -1.0
    for event in report.get("events", []):
        stamp = event.get("after_seconds")
        require(type(stamp) in (int,float) and stamp >= previous, "partition schedule time/order changed")
        previous = stamp
        kind, i = event.get("event"), event.get("part_index")
        if kind == "inherit_completed_part_mid_occ":
            require(not inherited and not seen and 0 not in selected and event.get("mid_occ") == mid,
                    "inherited threshold was not from completed original parts")
            inherited = True
        elif kind == "inherit_first_part_mid_occ":
            require(not inherited and 0 in seen and not first_completed and event.get("mid_occ") == mid, "threshold did not come from actual part zero")
            inherited = True
        elif kind == "start":
            require(type(i) is int and len(seen) < len(selected) and i == selected[len(seen)]
                    and (i == 0 or inherited), "part launched before original threshold or twice")
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
    require(finished == set(completed) and (partial and report["status"] == "failed_no_retry"
            or not active and finished == set(selected) and inherited), "incomplete part schedule")
    for leaf in leaves:
        i = leaf["part_index"]; part = parts[i]
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


def _round_plan(args, parts, records, selected, *, resumed):
    if not resumed:
        return plan(args, parts, records)
    count = len(selected)
    budget = org.resolve(args)
    if type(args.threads) is not int or args.threads < 1 or not 1 <= count <= len(parts):
        raise wa.ExperimentError("invalid pending original-part execution resources")
    base = {"enabled": True, "scope": "explicit_per_reference_group_only",
            "node_or_shared_job_memory_used": False, "extra_index_build": False,
            "extra_threshold_probe_mapping": False, "automatic_retry": False,
            "resource_grant": getattr(args, "ordinary_resource_grant", None)}
    if budget is None:
        # An unknown grant never authorizes parallelism. Preserve completed
        # leaves and continue serially, no more concurrent mappers than native.
        return {**base, "scope": "serial_resume_only", "reason": "resume_without_parallel_memory_grant",
                "slots": 1, "thread_shares": [args.threads], "group_budget_bytes": None,
                "controller_reserve_bytes": 0,
                "worker_address_space_bytes": min(_address_caps(args), default=None)}
    if type(budget) is not int or budget <= 0:
        raise wa.ExperimentError("invalid explicit ordinary reference-group memory budget")
    reserve = max(GIB, tm.current_virtual_bytes() + 64 * 1024**2)
    finite = _address_caps(args)
    for slots in range(min(2, count, args.threads), 0, -1):
        cap = (budget - reserve) // slots
        if finite:
            cap = min(cap, *finite)
        if cap >= GIB and all(2 * (parts[i]["end"] - parts[i]["start"]) <= cap for i in selected):
            return {**base, "reason": "resume_original_parts_with_exclusive_budget", "slots": slots,
                    "thread_shares": [args.threads // slots + (i < args.threads % slots) for i in range(slots)],
                    "group_budget_bytes": budget, "controller_reserve_bytes": reserve,
                    "worker_address_space_bytes": cap,
                    "address_space_caps_are_not_physical_memory_reservations": True}
    raise wa.ExperimentError("remaining original parts exceed the current exclusive group budget")


def _rounds(root, report, mm, query, parts, records, fraction):
    """Revalidate immutable native leaves from every explicit execution round."""
    import recovery_publication as rp
    descriptors = report.get("source_rounds", [])
    rp.require(type(descriptors) is list and 1 <= len(descriptors) <= MAX_ROUNDS,
               "invalid original-part execution history")
    complete, mid = {}, None
    for i, descriptor in enumerate(descriptors):
        relative = "original-run.json" if i == 0 else f"resume-{i:04d}/{RECEIPT}"
        path = root / relative
        rp.require(descriptor == {"path": relative, "sha256": wa.verified_sha256(rp.regular_under(path, root))},
                   "original-part execution history changed or escaped ownership")
        current = _verify_round(path, mm, query, parts, records, fraction=fraction, partial=True, expected_mid=mid)
        pending = sorted(set(range(len(parts))) - set(complete))
        rp.require(current.get("selected_parts", list(range(len(parts)))) == pending,
                   "execution round remapped a completed part or omitted pending original parts")
        for leaf in current["parts"]:
            complete[leaf["part_index"]] = leaf
        if current["parts"]:
            mid = current["mid_occ"]
    return [complete[i] for i in sorted(complete)], mid


def _verify_group(root, report, mm, query, parts, records, fraction, *, partial):
    import recovery_publication as rp
    rp.require(report.get("schema") == 2 and report.get("kind") == KIND
        and report.get("status") in (("ordinary_parts_success", "failed_no_retry") if partial
                                    else ("ordinary_parts_success",)), "incomplete resumed original-part group")
    rp.require(all(report.get(k) == v for k, v in group_inputs(mm, query, parts).items())
        and report.get("queries") == records and report.get("filter") == fraction,
        "resumed original-part source/tool/query/filter binding differs")
    rp.require(all(report.get(k) is False for k in ("automatic_retry", "extra_index_build",
        "extra_threshold_probe_mapping", "aggregate_native_command_fabricated", "extra_aggregate_PAF_copy")),
        "resumed original-part group introduced retry, probes or fabricated commands")
    leaves, mid = _rounds(root, report, mm, query, parts, records, fraction)
    rp.require(report.get("parts") == leaves and report.get("mid_occ") == mid,
               "resumed native completion matrix or threshold differs")
    rp.require(partial and report["status"] == "failed_no_retry" or len(leaves) == len(parts),
               "resumed original-part completion matrix is incomplete")
    return report


def verify(root, mm, query, parts, records, *, fraction=None):
    """Reopen native evidence, including earlier rounds; never invent a command."""
    import recovery_publication as rp
    root = Path(root)
    rp.require(not root.is_symlink(), "linked original-part group directory")
    report = rp.read_json(root / RECEIPT, root)
    if report.get("schema") == 2:
        return _verify_group(root, report, mm, query, parts, records, fraction, partial=False)
    rp.require(report.get("kind") == KIND and report.get("selected_parts", list(range(len(parts)))) == list(range(len(parts))),
               "a subset execution round is not a complete original-part group")
    return _verify_round(root / RECEIPT, mm, query, parts, records, fraction=fraction)


def attempt(mm, parts, query, root, args, records, admission):
    """Fresh bounded dispatch or explicit resume of ONLY uncompleted parts.

    An earlier success is independently rechecked before any new process starts.
    Source evidence stays at its original immutable command/output paths; each
    subsequent round has a distinct directory, grant and actual command list.
    No failure triggers another round in this call.
    """
    import recovery_publication as rp
    root = Path(root)
    rp.require(not root.is_symlink(), "linked original-part resume directory")
    root = root.resolve()
    fraction = getattr(args, "minimap_filter", None)
    if not root.exists():
        return _run(mm, parts, query, root, args, records, admission)
    rp.require(not root.is_symlink(), "linked original-part resume directory")
    previous = rp.read_json(root / RECEIPT, root)
    if previous.get("status") == "ordinary_parts_success":
        return verify(root, mm, query, parts, records, fraction=fraction)
    if previous.get("schema") == 1:
        checked = _verify_round(root / RECEIPT, mm, query, parts, records, fraction=fraction, partial=True)
        original = root / "original-run.json"
        # Keep the exact earlier group receipt; never rewrite old commands,
        # paths, timestamps or native outputs to make it resemble a new run.
        raw = (root / RECEIPT).read_bytes()
        if original.exists():
            rp.require(rp.regular_under(original, root).read_bytes() == raw,
                       "existing original execution snapshot differs")
        else:
            with original.open("xb") as stream:
                stream.write(raw)
        report = {"schema": 2, "kind": KIND, "status": "failed_no_retry", **group_inputs(mm, query, parts),
                  "queries": records, "filter": fraction, "parts": checked["parts"],
                  "mid_occ": checked["mid_occ"] if checked["parts"] else None,
                  "source_rounds": [{"path": original.name, "sha256": wa.sha256(original)}],
                  "automatic_retry": False, "extra_index_build": False, "extra_threshold_probe_mapping": False,
                  "aggregate_native_command_fabricated": False, "extra_aggregate_PAF_copy": False}
    else:
        report = _verify_group(root, previous, mm, query, parts, records, fraction, partial=True)
    _verify_group(root, report, mm, query, parts, records, fraction, partial=True)
    wa.write_json(root / RECEIPT, report)
    leaves, mid = _rounds(root, report, mm, query, parts, records, fraction)
    pending = sorted(set(range(len(parts))) - {p["part_index"] for p in leaves})
    if not pending:
        report["status"] = "ordinary_parts_success"
        wa.write_json(root / RECEIPT, report)
        return verify(root, mm, query, parts, records, fraction=fraction)
    rp.require(len(report["source_rounds"]) < MAX_ROUNDS, "original-part explicit resume history limit reached")
    schedule = _round_plan(args, parts, records, pending, resumed=True)
    directory = root / f"resume-{len(report['source_rounds']):04d}"
    report["reused_part_indices"] = [p["part_index"] for p in leaves]
    error = None
    try:
        _run(mm, parts, query, directory, args, records, schedule, selected=pending,
             inherited_mid=mid if 0 not in pending else None, expected_mid=mid)
        report["status"] = "ordinary_parts_success"
        report.pop("error", None)
    except BaseException as exc:
        report["status"] = "failed_no_retry"
        report["error"] = f"{type(exc).__name__}: {exc}"
        error = exc
        raise
    finally:
        if (directory / RECEIPT).is_file():
            report["source_rounds"].append({"path": f"{directory.name}/{RECEIPT}",
                                             "sha256": wa.sha256(directory / RECEIPT)})
            try:
                report["parts"], report["mid_occ"] = _rounds(root, report, mm, query, parts, records, fraction)
            except BaseException as invalid:
                report["status"] = "failed_no_retry"
                report["error"] = f"{type(invalid).__name__}: {invalid}"
                wa.write_json(root / RECEIPT, report)
                if error is None:
                    raise
            wa.write_json(root / RECEIPT, report)
        else:
            # A resource admission/spawn error must preserve the verified old
            # round as a resumable group without pretending a child ran.
            wa.write_json(root / RECEIPT, report)
    return verify(root, mm, query, parts, records, fraction=fraction)
