"""Bounded native-window cells for automatic LARGE initial-reference tasks.

Separate from whole-query native-confidence recovery. Every =/X base is checked;
projected rows retain original coordinates, unknown MAPQ, no inherited scores.
Successful mapper/ownership substages are sealed BEFORE the next expensive step.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import re
import signal
import time

import minimap_index_context as mic
import proactive_resume as pr
import proactive_publication as pub
import selective_reference_alignment as sr
import windowed_alignment as wa

POLICY = "bounded_native_window_projection_v1"
MIN_REFERENCE_BASES = 5_000_000_000
CORE_BASES = 5_000_000
CONTEXT_BASES = 100_000
MAP_SECONDS = 900
CELL_SECONDS = 2700
MAX_PAF_BYTES = 64 * 1024**2
MANIFEST = "approximate-cell.json"


@contextmanager
def deadline(seconds):
    """Keep parent cancellation and never extend an existing alarm deadline."""
    if not math.isfinite(seconds) or seconds <= 0:
        raise wa.ExperimentError("positive finite cell deadline required")
    previous = signal.getsignal(signal.SIGALRM)
    remaining, interval = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()
    def expired(number, frame):
        # run_command catches KeyboardInterrupt and terminates/waits its process
        # group. A custom Exception here would abandon a live mapper.
        raise KeyboardInterrupt("bounded approximate cell wall budget exhausted")
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, min(seconds, remaining) if remaining else seconds)
    failed = False
    try:
        yield
    except BaseException:
        failed = True
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        elapsed = time.monotonic() - started
        if remaining > elapsed:
            signal.setitimer(signal.ITIMER_REAL, remaining - elapsed, interval)
        elif remaining and not failed:
            raise KeyboardInterrupt("parent wall budget exhausted during approximate cell")


def eligible(target, *, enabled):
    return enabled and sum(row["length"] for row in target.records.values()) >= MIN_REFERENCE_BASES


def identity(name, length, query_sha256, reference_sha256, tool, part):
    return {"policy": POLICY, "query": name, "query_length": length,
            "query_sha256": query_sha256, "reference_sha256": reference_sha256,
            "tool_sha256": tool["sha256"], "index_sha256": part["sha256"],
            "part_index": part["part_index"], "mid_occ": part["mid_occ"],
            "core_bases": CORE_BASES, "context_bases": CONTEXT_BASES,
            "preset": "asm10", "candidate_policy": "native_window_selection"}


def _regular(path, root):
    from recovery_publication import regular_under
    return regular_under(path, root)


def _hash(path, root):
    return wa.verified_sha256(_regular(path, root))


def _raw_proof(root, state, expected, tool, part):
    if state.get("identity") != expected or state.get("schema") != 1:
        raise wa.ExperimentError("approximate cell source/policy identity changed")
    raw = state["raw"]
    threads = raw["threads"]
    if type(threads) is not int or threads < 1:
        raise wa.ExperimentError("invalid completed mapper thread grant")
    windows = wa.make_windows({expected["query"]: {"length": expected["query_length"]}}, CORE_BASES, CONTEXT_BASES)
    if pr.read_json(root / "windows.json") != {"windows": [asdict(w) for w in windows]}:
        raise wa.ExperimentError("complete window plan changed")
    for file, key in (("raw.windows.paf", "sha256"), ("windows.fa", "windows_sha256"),
                      ("windows.json", "manifest_sha256"), ("map.stderr", "stderr_sha256")):
        if _hash(root / file, root) != raw[key]:
            raise wa.ExperimentError("completed approximate mapper evidence changed: " + file)
    command = [tool["path"], "-c", "--eqx", "-x", "asm10", "-f", str(part["mid_occ"]),
               "-t", str(threads), "-o", str(root / "raw.windows.paf"), part["path"], str(root / "windows.fa")]
    execution = pub.completed_command(root, "map", root, command)
    if execution != raw["execution"]:
        raise wa.ExperimentError("completed approximate execution changed")
    log = (root / "map.stderr").read_text()
    loads = re.findall(r"loaded/built the index for ([0-9]+) target sequence", log)
    batches = re.findall(r"\[M::worker_pipeline::[^\]]+\] mapped ([0-9]+) sequences", log)
    if loads != [str(len(part["records"]))] or sum(map(int, batches)) != len(windows):
        raise wa.ExperimentError("approximate mapper omitted an original part/window batch")
    if (wa.verified_sha256(Path(part["path"])) != expected["index_sha256"]
            or wa.verified_sha256(Path(tool["path"])) != expected["tool_sha256"]):
        raise wa.ExperimentError("approximate mapper/index content changed")
    return windows


def validate_row(raw, name, length, part):
    fields = raw.rstrip(b"\r\n").split(b"\t")
    sr.validate_row(raw, {name: {"length": length}},
                    {r["name"]: {"length": r["length"]} for r in part["records"]}, {name}, "risk")
    if any(tag.startswith(b"cm:") for tag in fields[12:]):
        raise wa.ExperimentError("projected row inherited a chaining count")


def verify(root, expected, tool, part):
    root = Path(root)
    if root.is_symlink() or root.parent.is_symlink():
        raise wa.ExperimentError("linked approximate cell directory")
    root = root.resolve()
    state = pr.read_json(root / MANIFEST)
    if state.get("status") != "complete_base_checked_projection":
        raise wa.ExperimentError("approximate cell is not complete")
    _raw_proof(root, state, expected, tool, part)
    checker = wa.sha256(Path(wa.__file__))
    if state["owned"].get("checker_sha256") != checker or state["stitched"].get("checker_sha256") != checker:
        raise wa.ExperimentError("base-check source changed; reconstruct from completed raw mapping")
    if (state["owned"].get("raw_sha256") != state["raw"]["sha256"]
            or state["stitched"].get("owned_sha256") != state["owned"]["sha256"]):
        raise wa.ExperimentError("postprocessing lost its completed source binding")
    for stage, paf, proof in (("owned", "owned.paf", "ownership.jsonl"),
                               ("stitched", "stitched.paf", "stitch.jsonl")):
        if (_hash(root / paf, root) != state[stage]["sha256"]
                or _hash(root / proof, root) != state[stage]["proof_sha256"]):
            raise wa.ExperimentError("completed approximate transformation changed")
    rows = 0
    with (root / "stitched.paf").open("rb") as stream:
        for line in stream:
            validate_row(line, expected["query"], expected["query_length"], part)
            rows += 1
    if rows != state["stitched"]["rows"]:
        raise wa.ExperimentError("complete approximate row count changed")
    return {"query": expected["query"], "part_index": part["part_index"], "kind": POLICY,
            "status": state["status"], "directory": str(root), "path": str(root / "stitched.paf"),
            "sha256": state["stitched"]["sha256"], "receipt_sha256": _hash(root / MANIFEST, root),
            "identity": expected, "rows": rows, "native_confidence_reconstructed": False}


def run(root, query, target, tool, part, args, *, tool_transition=None):
    index_tool_sha256 = tool["sha256"]
    if tool_transition is not None:
        import ordinary_tool_transition as ott
        checked = ott.verify_transition(tool_transition)
        if (tool["path"] != checked["execution"]["path"]
                or tool["sha256"] != checked["execution"]["sha256"]):
            raise wa.ExperimentError("native-window execution tool differs from reviewed transition")
        # Validate the original builder, not a forged new builder on old bytes.
        index_tool_sha256 = checked["origin"]["sha256"]
    root = Path(root)
    if root.is_symlink() or root.parent.is_symlink():
        raise wa.ExperimentError("linked approximate cell directory")
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if len(query.records) != 1:
        raise wa.ExperimentError("approximate cell requires ONE complete original query")
    name = next(iter(query.records)); length = query.records[name]["length"]
    expected = identity(name, length, query.identity["sha256"], target.identity["sha256"], tool, part)
    state = pr.read_json(root / MANIFEST) if (root / MANIFEST).exists() else {"schema": 1, "identity": expected}
    if state["identity"] != expected:
        raise wa.ExperimentError("existing approximate cell belongs to another input/policy")
    started = time.monotonic(); reused = {"mapping": False, "ownership": False, "stitching": False}
    cap = min(36, args.memory_gib) if args.memory_gib else 36
    checker = wa.sha256(Path(wa.__file__))
    def save():wa.write_json(root / MANIFEST, state)
    try:
        with deadline(CELL_SECONDS):
            mic.validate_part_context(part, reference_sha256=target.identity["sha256"],
                tool_sha256=index_tool_sha256, preset="asm10", target_records=target.records)
            if "raw" in state:
                windows = _raw_proof(root, state, expected, tool, part); reused["mapping"] = True
            else:
                for n in ("windows.json", "windows.fa", "raw.windows.paf", "map.command.json",
                          "map.execution.json", "map.stdout", "map.stderr"):
                    pr.archive_partial(root / n)
                windows = wa.make_windows(query.records, CORE_BASES, CONTEXT_BASES)
                wa.write_json(root / "windows.json", {"windows": [asdict(w) for w in windows]})
                wa.write_windows(root / "windows.fa", query, windows)
                windows_sha = _hash(root / "windows.fa", root)
                manifest_sha = _hash(root / "windows.json", root)
                command = [tool["path"], "-c", "--eqx", "-x", "asm10", "-f", str(part["mid_occ"]),
                    "-t", str(args.threads), "-o", str(root / "raw.windows.paf"), part["path"], str(root / "windows.fa")]
                execution = wa.run_command(command, root, "map", min(MAP_SECONDS, args.timeout) if args.timeout else MAP_SECONDS,
                    cap, max_file_bytes=MAX_PAF_BYTES)
                raw_proof = {"threads": args.threads, "execution": execution,
                    "sha256": _hash(root / "raw.windows.paf", root), "windows_sha256": windows_sha,
                    "manifest_sha256": manifest_sha, "stderr_sha256": _hash(root / "map.stderr", root)}
                _raw_proof(root, {**state, "raw": raw_proof}, expected, tool, part)
                if not query.unchanged() or not target.unchanged():
                    raise wa.ExperimentError("source changed during native window mapping")
                state["raw"] = raw_proof
                state["status"] = "mapping_complete"; save()
            # A changed checker invalidates only derived postprocessing, never a
            # verified mapper substage. Archive old outputs instead of deleting.
            if state.get("owned", {}).get("checker_sha256") not in (None, checker):
                state.pop("owned", None); state.pop("stitched", None)
            if "owned" not in state:
                for n in ("owned.paf", "owned.paf.partial", "ownership.jsonl"):
                    pr.archive_partial(root / n)
                coverage = wa.recover(root / "raw.windows.paf", root / "owned.paf", root / "ownership.jsonl",
                    windows, query, target, allow_empty_original_part=True)
                state["owned"] = {"sha256": _hash(root / "owned.paf", root), "proof_sha256": _hash(root / "ownership.jsonl", root),
                                  "checker_sha256": checker, "raw_sha256": state["raw"]["sha256"], "coverage": coverage}
                state["status"] = "ownership_complete"; save()
            else:
                if (state["owned"].get("raw_sha256") != state["raw"]["sha256"]
                        or _hash(root / "owned.paf", root) != state["owned"]["sha256"]
                        or _hash(root / "ownership.jsonl", root) != state["owned"]["proof_sha256"]):
                    raise wa.ExperimentError("completed ownership evidence changed")
                reused["ownership"] = True
            if "stitched" not in state:
                for n in ("stitched.paf", "stitched.paf.partial", "stitch.jsonl"):
                    pr.archive_partial(root / n)
                result = wa.stitch_owned(root / "owned.paf", root / "stitched.paf", root / "stitch.jsonl",
                    windows, query, target, allow_empty_original_part=True)
                rows = 0
                with (root / "stitched.paf").open("rb") as stream:
                    for line in stream:
                        validate_row(line, name, length, part); rows += 1
                state["stitched"] = {"sha256": _hash(root / "stitched.paf", root),
                    "proof_sha256": _hash(root / "stitch.jsonl", root), "checker_sha256": checker,
                    "owned_sha256": state["owned"]["sha256"], "rows": rows, "stitching": result}
            else:
                if (state["stitched"].get("owned_sha256") != state["owned"]["sha256"]
                        or _hash(root / "stitched.paf", root) != state["stitched"]["sha256"]
                        or _hash(root / "stitch.jsonl", root) != state["stitched"]["proof_sha256"]):
                    raise wa.ExperimentError("completed stitching evidence changed")
                reused["stitching"] = True
            if not query.unchanged() or not target.unchanged():
                raise wa.ExperimentError("original sequences changed during approximate processing")
            _raw_proof(root, state, expected, tool, part)
            state.update(status="complete_base_checked_projection", native_confidence_reconstructed=False)
            state.pop("error", None)
    except BaseException as exc:
        state.update(status="failed_with_completed_substages_retained", error=type(exc).__name__ + ": " + str(exc))
        raise
    finally:
        state["last_invocation"] = {"elapsed_seconds": time.monotonic() - started, "reused": reused,
                                  "cell_budget_seconds": CELL_SECONDS, "mapper_budget_seconds": MAP_SECONDS,
                                  "mapper_address_space_gib": cap}
        save()
    return verify(root, expected, tool, part)


def screen_group(root, name, length, sources, *, assignment_coverage=0.60):
    """Combine ALL original parts of one query before checking assignment risk."""
    import adaptive_screening as policy
    root = Path(root)
    path = root / "complete-projection.paf"
    marker = root / "projection-source.json"
    expected = [{"path": str(Path(p)), "sha256": digest} for p, digest in sources]
    if any(wa.verified_sha256(Path(r["path"])) != r["sha256"] for r in expected):
        raise wa.ExperimentError("complete query source changed before screening")
    previous = pr.read_json(marker) if marker.exists() else None
    if previous and previous.get("sources") == expected:
        if _hash(path, root) != previous["sha256"]:
            raise wa.ExperimentError("complete query projection changed")
    else:
        pr.archive_partial(path); pr.archive_partial(marker)
        with path.open("xb") as output:
            for row in expected:
                digest = hashlib.sha256()
                with Path(row["path"]).open("rb") as stream:
                    while block := stream.read(wa.CHUNK):
                        output.write(block); digest.update(block)
                if digest.hexdigest() != row["sha256"]:
                    raise wa.ExperimentError("query source changed while composing screening input")
        previous = {"sources": expected, "sha256": wa.sha256(path)}
        wa.write_json(marker, previous)
    profile = policy.coverage_profile(path, [{"name": name, "length": length}])
    result = policy.screen_candidate_projection(profile, policy.assignment_limits(assignment_coverage))
    return {"query": name, "path": str(path), **previous, "profile": profile,
            "screening": result, "approved": all(r["action"] == "no_obvious_assignment_risk" for r in result["queries"]),
            "native_baseline_compared": False, "native_confidence_reconstructed": False}


REVIEW_SECONDS = 600
TOTAL_REVIEW_SECONDS = 1200


def native_review(root, group, index, tool, args, *, seconds):
    """One bounded authoritative whole-record native review, never partial reuse."""
    import argparse
    import native_first as nf
    import recovery_publication as rp
    root = Path(root)
    marker = root / "quality-review.json"
    native = root / "native-quality-review"
    expected = {"policy": POLICY, "query_sha256": group["sha256"], "index_sha256": index["sha256"],
                "tool_sha256": tool["sha256"], "filter": getattr(args, "minimap_filter", None)}
    state = pr.read_json(marker) if marker.exists() else {"identity": expected, "status": "not_started"}
    if state.get("identity") != expected:
        raise wa.ExperimentError("native review source/policy changed")
    if state["status"] == "failed":
        raise wa.ExperimentError("bounded native quality review already failed; partial PAF is not publishable")
    if state["status"] != "complete":
        if seconds <= 0:
            raise wa.ExperimentError("automatic quality review budget exhausted")
        pr.archive_partial(native)
        state["status"] = "running"; wa.write_json(marker, state)
        try:
            options = argparse.Namespace(**vars(args))
            options.timeout = min(REVIEW_SECONDS, seconds, args.timeout or REVIEW_SECONDS)
            options.memory_gib = min(36, args.memory_gib) if args.memory_gib else 36
            options.max_output_bytes = MAX_PAF_BYTES
            with deadline(options.timeout + 10):
                receipt = nf.attempt(tool["path"], Path(index["path"]), Path(group["path"]), native, options)
            if receipt["status"] != "native_success":
                raise wa.ExperimentError("bounded native quality review did not complete; approximate candidate retained")
            state.update(status="complete", receipt_sha256=wa.sha256(native / "native-attempt.json"))
        except BaseException as exc:
            state.update(status="failed", error=type(exc).__name__ + ": " + str(exc)); raise
        finally:
            wa.write_json(marker, state)
    return verify_review(root, group, index, tool, args)


def verify_review(root, group, index, tool, args):
    import recovery_publication as rp
    root = Path(root); native = root / "native-quality-review"
    state = pr.read_json(root / "quality-review.json")
    expected = {"policy": POLICY, "query_sha256": group["sha256"], "index_sha256": index["sha256"],
                "tool_sha256": tool["sha256"], "filter": getattr(args, "minimap_filter", None)}
    if (state.get("status") != "complete" or state.get("identity") != expected
            or wa.verified_sha256(Path(group["path"])) != group["sha256"]
            or wa.verified_sha256(Path(index["path"])) != index["sha256"]
            or wa.verified_sha256(Path(tool["path"])) != tool["sha256"]
            or _hash(native / "native-attempt.json", root) != state["receipt_sha256"]):
        raise wa.ExperimentError("completed native review identity/evidence changed")
    receipt = rp.verify_attempt(native / "native-attempt.json", root, "native_success", tool=tool["path"],
        target=Path(index["path"]), query=Path(group["path"]), fraction=getattr(args, "minimap_filter", None))
    if receipt["index_sequence_counts"] != [len(p["records"]) for p in index["parts"]]:
        raise wa.ExperimentError("native review omitted original reference parts")
    batches = re.findall(r"\[M::worker_pipeline::[^\]]+\] mapped ([0-9]+) sequences", (native / "native.stderr").read_text())
    if sum(map(int, batches)) != len(index["parts"]):
        raise wa.ExperimentError("native review omitted complete query traversal")
    return {"query": group["queries"][0], "directory": str(root), "native": receipt,
            "receipt_sha256": _hash(root / "quality-review.json", root), "identity": expected}
