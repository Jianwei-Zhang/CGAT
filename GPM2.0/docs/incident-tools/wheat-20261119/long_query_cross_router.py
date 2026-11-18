"""Incident-scoped, whole-record q0 cross mapper; not wired into production.

Only >=100 Mb queries are eligible for bounded sensitivity calibration. Other
records retain ordinary Minimap2 options. Probes are never final evidence.
All caches bind actual inputs/tool/options and complete validated outputs.
Existing reference-alignment controllers/receipts are deliberately NOT reused.
"""
from __future__ import annotations
import argparse
import contextlib
import dataclasses
import fcntl
import hashlib
import heapq
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import uuid

from paf_anchor_comparison import compare
from seed_filter_pilot import measure


class RoutingError(RuntimeError):
    pass


class MappingFailed(RoutingError):
    pass


@dataclasses.dataclass(frozen=True)
class Policy:
    version: str = "q0-cross-whole-record-v1"
    long_bases: int = 100_000_000
    minimum_target_bases: int = 100_000_000
    maximum_target_bases: int = 1_000_000_000
    probe_window_bases: int = 5_000_000
    probe_seconds: int = 300
    anchor_step: int = 10_000
    minimum_anchors: int = 1000
    maximum_position_loss: float = .002
    maximum_coverage_loss: float = .001
    minimum_full_query_coverage: float = .90
    filters: tuple[float, ...] = (.005, .001)

    def checked(self):
        if (self.long_bases < 3 * self.probe_window_bases or self.probe_window_bases < 1
                or self.minimum_target_bases < 1 or self.maximum_target_bases < self.minimum_target_bases
                or min(self.probe_seconds, self.anchor_step, self.minimum_anchors) < 1
                or not 0 <= self.maximum_position_loss < 1
                or not 0 <= self.maximum_coverage_loss < 1
                or not 0 < self.minimum_full_query_coverage <= 1
                or not self.filters or any(not 0 < f < 1 for f in self.filters)):
            raise RoutingError("invalid internal routing policy")
        return self


def load_runtime(tools):
    tools = Path(tools).resolve(strict=True)
    library = tools / "long_cigar_recovery"
    for path in (tools / "run_orchestration.py", library / "proactive_reference_plan.py"):
        if not path.is_file():
            raise RoutingError(f"missing frozen runtime dependency: {path}")
    sys.path[:0] = [str(tools), str(library)]
    import run_orchestration as contract
    import proactive_reference_plan as catalog
    import automatic_ordinary_pilot as raw_copy
    return contract, catalog, raw_copy


def acceptable(baseline_metrics, candidate_metrics, comparison, policy):
    n = comparison["baseline_anchor_count"]
    covered = baseline_metrics["primary_query_covered_bases"]
    if n < policy.minimum_anchors or covered < 1:
        return False
    loss = 1 - comparison["baseline_anchors_supported_within_100bp"] / n
    common_candidate = comparison["candidate_anchor_count"] - comparison["extra_candidate_anchors"]
    novel_existing = max(0, comparison["candidate_anchors_with_extra_positions_beyond_100bp"]
                         - comparison["extra_candidate_anchors"])
    coverage_loss = max(0, covered - candidate_metrics["primary_query_covered_bases"]) / covered
    return (loss <= policy.maximum_position_loss
            and common_candidate > 0
            and novel_existing / common_candidate <= policy.maximum_position_loss
            and coverage_loss <= policy.maximum_coverage_loss)


class Router:
    def __init__(self, target, query, tool, cache, tools, *, threads=1, preset="asm10", policy=Policy()):
        if threads < 1 or preset not in ("asm5", "asm10", "asm20"):
            raise RoutingError("positive thread budget and assembly preset required")
        self.contract, self.catalog_lib, self.raw_copy = load_runtime(tools)
        self.policy = policy.checked()
        self.threads, self.preset = threads, preset
        self.tool = Path(tool).resolve(strict=True)
        self.tool_hash = self.contract.sha256_file(self.tool)
        self.original_target, self.original_query = Path(target).absolute(), Path(query).absolute()
        self.target = self.catalog_lib.scan_query(Path(target))
        self.query = self.catalog_lib.scan_query(Path(query))
        self.target_lengths = {r.name: r.length for r in self.target.records}
        self.records = {r.name: r for r in self.query.records}
        self.order = {r.name: r.ordinal for r in self.query.records}
        if Path(cache).is_symlink():
            raise RoutingError("linked routing cache")
        self.cache = Path(cache).resolve()
        self.cache.mkdir(parents=True, exist_ok=True)
        self.prepared_queries = {Path(self.query.source): (self.query.source_sha256, {r.name: r.length for r in self.query.records}, "whole_records")}
        self.cancelled = False
        self.code = self.contract.sha256_file(Path(__file__))
        self.metric_code = self.contract.sha256_file(Path(compare.__code__.co_filename))
        files = {"router": Path(__file__), "positions": Path(compare.__code__.co_filename),
                 "coverage": Path(measure.__code__.co_filename), "contract": Path(self.contract.__file__),
                 "catalog": Path(self.catalog_lib.__file__), "copy": Path(self.raw_copy.__file__),
                 "store": Path(self.raw_copy.wa.__file__), "resume": Path(self.raw_copy.pr.__file__)}
        self.dependencies = {name: {"path": path.resolve(), "sha256": self.contract.sha256_file(path)}
                             for name, path in files.items()}
        self.dependency_hashes = {name: row["sha256"] for name, row in self.dependencies.items()}

    def stable(self, *, check_code=False):
        if self.cancelled:
            raise RoutingError("routing cancelled; no final evidence published")
        if (self.original_target.resolve(strict=True) != Path(self.target.source)
                or self.original_query.resolve(strict=True) != Path(self.query.source)):
            raise RoutingError("source path binding changed")
        self.target.require_unchanged()
        self.query.require_unchanged()
        # Python modules are loaded once. Check their source at admission and
        # publication, not repeatedly for every small cache lookup.
        if check_code and any(self.contract.sha256_file(row["path"]) != row["sha256"] for row in self.dependencies.values()):
            raise RoutingError("routing implementation changed during execution")
        if self.contract.sha256_file(self.tool) != self.tool_hash:
            raise RoutingError("mapping executable changed")

    @contextlib.contextmanager
    def signals(self):
        def cancel(signum, _frame):
            self.cancelled = True
            raise RoutingError(f"routing cancelled by signal {signum}")
        old = {s: signal.signal(s, cancel) for s in (signal.SIGTERM, signal.SIGINT)}
        try:
            yield
        finally:
            for s, handler in old.items():
                signal.signal(s, handler)

    def execute(self, command, directory, timeout):
        # Inherit the outer task's process group. subprocess.run kills/waits for
        # its native child on timeout or cancellation; do not detach a mapper.
        with (directory / "stdout.log").open("wb") as out, (directory / "stderr.log").open("wb") as err:
            try:
                proc = subprocess.run(command, stdout=out, stderr=err, timeout=timeout)
                return proc.returncode
            except subprocess.TimeoutExpired:
                return 124

    def validate_output(self, path, lengths):
        self.contract.validate_paf(path, require_cigar=True)
        with path.open() as handle:
            for line in handle:
                f = line.rstrip("\n").split("\t")
                if (len(f) < 12 or f[0] not in lengths or int(f[1]) != lengths[f[0]]
                        or f[5] not in self.target_lengths or int(f[6]) != self.target_lengths[f[5]]):
                    raise RoutingError("mapping contains an unexpected query/target identity")

    def mapping(self, query_path, names_lengths, fraction, *, phase, timeout=None, allow_multipart=False):
        query_path = Path(query_path).resolve(strict=True)
        self.stable()
        known = self.prepared_queries.get(query_path)
        if known is None or known[1] != names_lengths or known[2] != phase:
            raise RoutingError("query group was not derived from the complete original records")
        actual_hash = (self.query.source_sha256 if query_path == Path(self.query.source)
                       else self.raw_copy.wa.verified_sha256(query_path))
        if actual_hash != known[0]:
            raise RoutingError("derived query content changed")
        options = ["-c", "-x", self.preset] + (["-f", str(fraction)] if fraction is not None else [])
        identity = {"schema": 1, "phase": phase, "target_sha256": self.target.source_sha256,
                    "query_sha256": actual_hash, "tool_sha256": self.tool_hash,
                    "preset": self.preset, "filter": fraction, "queries": names_lengths,
                    "allow_multipart": allow_multipart}
        key = self.contract.fingerprint(identity)
        root = self.cache / "mappings" / key
        root.mkdir(parents=True, exist_ok=True)
        marker = root / "complete.json"
        self.stable()
        if marker.exists():
            saved = json.loads(marker.read_text())
            if (saved.get("identity") != identity or saved.get("status") != "success"
                    or type(saved.get("exit_code")) is not int or saved["exit_code"] != 0):
                raise RoutingError("completed mapping identity changed")
            command = saved["command"]
            semantic = command[1:-2]
            for flag in ("-t", "-o"):
                if semantic.count(flag) != 1:
                    raise RoutingError("mapping command proof changed")
                i = semantic.index(flag); del semantic[i:i+2]
            if semantic != options:
                raise RoutingError("cached mapping scientific options changed")
            outputs = saved["outputs"]
            if (len(outputs) != 3 or {Path(r["path"]).name for r in outputs}
                    != {"result.paf", "stdout.log", "stderr.log"}
                    or saved["paf"] not in {r["path"] for r in outputs if Path(r["path"]).name == "result.paf"}):
                raise RoutingError("incomplete mapping output proof")
            for row in outputs:
                path = root / row["path"]
                path.resolve().relative_to(root.resolve())
                if self.contract.file_identity(path, relative_to=root) != row:
                    raise RoutingError("completed mapping output changed")
            paf = root / saved["paf"]
            paf.resolve().relative_to(root.resolve())
            self.validate_output(paf, names_lengths)
            stderr_path = root / next(r["path"] for r in outputs if Path(r["path"]).name == "stderr.log")
            parts, occurrence = self.traversal(stderr_path.read_text(errors="replace"), names_lengths, allow_multipart)
            if saved.get("index_parts") != parts or saved.get("mid_occ") != occurrence:
                raise RoutingError("cached traversal proof changed")
            print(f"ROUTE_GROUP_REUSED phase={phase} filter={fraction} queries={len(names_lengths)}", flush=True)
            return {**saved, "path": str(paf), "cache_key": key}
        attempt = root / ("attempt-" + uuid.uuid4().hex)
        attempt.mkdir()
        paf = attempt / "result.paf"
        command = [str(self.tool), "-c", "-x", self.preset, "-t", str(self.threads)]
        if fraction is not None:
            command += ["-f", str(fraction)]
        command += ["-o", str(paf), self.target.source, str(query_path)]
        (attempt / "command.json").write_text(json.dumps(command, indent=2) + "\n")
        print(f"ROUTE_GROUP_START phase={phase} filter={fraction} queries={len(names_lengths)}", flush=True)
        code = self.execute(command, attempt, timeout)
        self.contract.atomic_write_json(attempt / "exit.json", {"returncode": code})
        self.stable()
        if code:
            print((attempt / "stderr.log").read_text(errors="replace")[-65536:], file=sys.stderr, flush=True)
            raise MappingFailed(f"native mapping failed code={code}; evidence={attempt}")
        self.validate_output(paf, names_lengths)
        text = (attempt / "stderr.log").read_text(errors="replace")
        parts, occurrence = self.traversal(text, names_lengths, allow_multipart)
        record = {"identity": identity, "status": "success", "exit_code": 0, "index_parts": parts, "paf": str(paf.relative_to(root)),
                  "command": command, "mid_occ": occurrence,
                  "outputs": [self.contract.file_identity(attempt / name, relative_to=root)
                              for name in ("result.paf", "stdout.log", "stderr.log")]}
        self.contract.atomic_write_json(marker, record)
        return {**record, "path": str(paf), "cache_key": key}

    def traversal(self, text, names_lengths, allow_multipart):
        parts = re.findall(r"loaded/built the index for (\d+) target sequence", text)
        mapped = sum(map(int, re.findall(r"mapped (\d+) sequences", text)))
        if (not parts or sum(map(int, parts)) != len(self.target_lengths)
                or mapped != len(names_lengths) * len(parts)):
            raise RoutingError("complete query traversal was not proved")
        if len(parts) != 1 and not allow_multipart:
            raise MappingFailed("multi-index calibration/routing unsupported; ordinary whole-query fallback required")
        occurrence = re.findall(r"mid_occ = (\d+)", text)
        return len(parts), int(occurrence[-1]) if occurrence else None

    def materialize(self, names):
        identity = {"source": self.query.source_sha256, "records": [dataclasses.asdict(self.records[n]) for n in names]}
        root = self.cache / "inputs" / self.contract.fingerprint(identity)
        root.mkdir(parents=True, exist_ok=True)
        path = root / "query.fa"
        proof = self.raw_copy.materialize(self.query, names, path)
        self.prepared_queries[path.resolve()] = (proof["sha256"], {n: self.records[n].length for n in names}, "whole_records")
        return path

    def probes(self, record):
        starts = (0, (record.length - self.policy.probe_window_bases) // 2,
                  record.length - self.policy.probe_window_bases)
        identity = {"source": self.query.source_sha256, "record": dataclasses.asdict(record),
                    "window": self.policy.probe_window_bases, "starts": list(starts), "schema": 1}
        root = self.cache / "probes" / self.contract.fingerprint(identity)
        root.mkdir(parents=True, exist_ok=True)
        path, marker = root / "probe.fa", root / "complete.json"
        lengths = {f"window_{i}": self.policy.probe_window_bases for i in range(3)}
        self.stable()
        if marker.exists():
            saved = json.loads(marker.read_text())
            if (saved["identity"] != identity
                    or self.contract.file_identity(path, relative_to=root) != saved["output"]):
                raise RoutingError("calibration input cache changed")
            self.prepared_queries[path.resolve()] = (saved["output"]["sha256"], lengths, "calibration")
            return path, lengths
        if self.query.encoding != "plain":
            raise RoutingError("proactive record probes require prepared plain FASTA")
        windows = [bytearray() for _ in starts]
        at_start, offset, remaining = True, 0, record.byte_end - record.byte_start
        digest = hashlib.sha256()
        with Path(self.query.source).open("rb") as handle:
            handle.seek(record.byte_start)
            while remaining:
                block = handle.readline(min(1024 * 1024, remaining))
                if not block:
                    raise RoutingError("source truncated while extracting calibration")
                remaining -= len(block); digest.update(block)
                header = at_start and block.startswith(b">")
                at_start = block.endswith(b"\n")
                if header:
                    continue
                sequence = block.rstrip(b"\r\n")
                for i, start in enumerate(starts):
                    lo, hi = max(offset, start), min(offset + len(sequence), start + self.policy.probe_window_bases)
                    if lo < hi:
                        windows[i].extend(sequence[lo-offset:hi-offset])
                offset += len(sequence)
        if (digest.hexdigest() != record.sha256 or offset != record.length
                or any(len(w) != self.policy.probe_window_bases for w in windows)):
            raise RoutingError("calibration extraction changed the original record")
        content = b"".join(f">window_{i}\n".encode() + w + b"\n" for i, w in enumerate(windows))
        temporary = path.with_name("probe.partial-" + uuid.uuid4().hex)
        temporary.write_bytes(content); self.stable(); temporary.replace(path)
        output = self.contract.file_identity(path, relative_to=root)
        self.contract.atomic_write_json(marker, {"identity": identity, "output": output})
        self.prepared_queries[path.resolve()] = (output["sha256"], lengths, "calibration")
        return path, lengths

    def calibrate(self, record):
        probe, lengths = self.probes(record)
        result = {"query": record.name, "length": record.length, "record_sha256": record.sha256,
                  "filter": None, "reason": "no_candidate_admitted", "cases": [],
                  "calibration_scope": "three_fixed_windows_only", "global_agreement_guaranteed": False}
        try:
            base = self.mapping(probe, lengths, None, phase="calibration", timeout=self.policy.probe_seconds)
            base_metrics, _ = measure(Path(base["path"]))
        except MappingFailed as error:
            self.stable()
            # A timed-out/failed pilot is not a complete source or a reason to
            # alter primary-work parameters. Preserve it and use ordinary mode.
            return {**result, "reason": "baseline_calibration_failed", "error": str(error)}
        for fraction in self.policy.filters:
            try:
                candidate = self.mapping(probe, lengths, fraction, phase="calibration", timeout=self.policy.probe_seconds)
                metrics, _ = measure(Path(candidate["path"]))
                positions = compare(Path(base["path"]), Path(candidate["path"]), self.policy.anchor_step)
                useful = (base["mid_occ"] is not None and candidate["mid_occ"] is not None
                          and candidate["mid_occ"] < base["mid_occ"])
                passed = useful and acceptable(base_metrics, metrics, positions, self.policy)
                result["cases"].append({"filter": fraction, "passed": passed, "baseline": base["cache_key"],
                    "candidate": candidate["cache_key"], "positions": positions, "metrics": metrics})
                if passed:
                    return {**result, "filter": fraction, "reason": "bounded_calibration_admitted"}
            except MappingFailed as error:
                self.stable()
                result["cases"].append({"filter": fraction, "passed": False, "error": str(error)})
        return result

    def merge(self, groups, chosen, destination):
        if set(chosen) != set(self.records):
            raise RoutingError("final routing omits original query records")
        for name, index in chosen.items():
            if not 0 <= index < len(groups) or name not in groups[index]["identity"]["queries"]:
                raise RoutingError("selected source did not process the original record")
        used = set(chosen.values())
        if len(used) == 1:
            index = next(iter(used))
            if set(groups[index]["identity"]["queries"]) == set(self.records):
                with Path(groups[index]["path"]).open("rb") as src, destination.open("xb") as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
                self.validate_output(destination, {r.name: r.length for r in self.query.records})
                return
        handles, heap, previous = [None] * len(groups), [], {}
        def advance(index):
            for line in handles[index]:
                name = line.split(b"\t", 1)[0].decode("ascii")
                if name not in self.order or self.order[name] < previous.get(index, -1):
                    raise RoutingError("native group output is not in original query order")
                previous[index] = self.order[name]
                if chosen[name] == index:
                    heapq.heappush(heap, (self.order[name], index, line))
                    return
        try:
            for index, group in enumerate(groups):
                if index in used:
                    handles[index] = Path(group["path"]).open("rb"); advance(index)
            with destination.open("xb") as out:
                while heap:
                    _ordinal, index, line = heapq.heappop(heap)
                    out.write(line); advance(index)
        finally:
            for handle in handles:
                if handle is not None:
                    handle.close()
        self.validate_output(destination, {r.name: r.length for r in self.query.records})

    def run(self, output, receipt):
        output, receipt = Path(output), Path(receipt)
        protected = {Path(self.target.source), Path(self.query.source), self.tool}
        if (output.resolve() in protected or receipt.resolve() in protected
                or output.resolve() == receipt.resolve() or output.is_symlink() or receipt.is_symlink()
                or output.resolve().is_relative_to(self.cache) or receipt.resolve().is_relative_to(self.cache)):
            raise RoutingError("output/receipt aliases a protected input or each other")
        output.parent.mkdir(parents=True, exist_ok=True)
        receipt.parent.mkdir(parents=True, exist_ok=True)
        with (self.cache / "router.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.stable(check_code=True)
            if receipt.is_file():
                saved = json.loads(receipt.read_text())
                wanted = {"preset": self.preset, "query_sha256": self.query.source_sha256,
                          "target_sha256": self.target.source_sha256, "tool_sha256": self.tool_hash,
                          "router_sha256": self.code, "metrics_sha256": self.metric_code,
                          "dependencies": self.dependency_hashes, "policy": json.loads(json.dumps(dataclasses.asdict(self.policy)))}
                if saved.get("status") != "complete" or any(saved.get(k) != v for k, v in wanted.items()):
                    raise RoutingError("final routing receipt belongs to another request")
                actual = self.contract.file_identity(output)
                if any(actual[k] != saved["output"][k] for k in ("size", "sha256")):
                    raise RoutingError("completed final routing output changed")
                self.validate_output(output, {r.name: r.length for r in self.query.records})
                self.stable(check_code=True)
                print("ROUTE_FINAL_REUSED verified final PAF; intermediate caches not required", flush=True)
                return saved
            target_size = sum(self.target_lengths.values())
            enabled = (self.policy.minimum_target_bases <= target_size <= self.policy.maximum_target_bases
                       and self.query.encoding == "plain")
            decisions = []
            for record in self.query.records:
                if enabled and record.length >= self.policy.long_bases:
                    decisions.append(self.calibrate(record))
                else:
                    decisions.append({"query": record.name, "length": record.length, "filter": None,
                                      "reason": "ordinary_query_or_target_size"})
            groups, chosen = [], {}
            exact = {d["query"] for d in decisions if d["filter"] is None}
            for fraction in self.policy.filters:
                names = [d["query"] for d in decisions if d["filter"] == fraction]
                if not names:
                    continue
                group = self.mapping(self.materialize(names), {n: self.records[n].length for n in names}, fraction, phase="whole_records")
                index = len(groups); groups.append(group)
                intervals = {}
                with Path(group["path"]).open() as handle:
                    for line in handle:
                        f = line.split("\t")
                        if "tp:A:P" in [v.strip() for v in f[12:]]:
                            intervals.setdefault(f[0], []).append((int(f[2]), int(f[3])))
                from seed_filter_pilot import covered
                for name in names:
                    coverage = covered({name: intervals.get(name, [])}) / self.records[name].length
                    if coverage < self.policy.minimum_full_query_coverage:
                        exact.add(name)
                        next(d for d in decisions if d["query"] == name).update(
                            effective_filter=None, fallback_reason="full_query_coverage_guard", candidate_coverage=coverage)
                    else:
                        chosen[name] = index
            names = [r.name for r in self.query.records if r.name in exact]
            if names:
                query_path = Path(self.query.source) if len(names) == len(self.records) else self.materialize(names)
                group = self.mapping(query_path, {n: self.records[n].length for n in names}, None, phase="whole_records", allow_multipart=(len(names) == len(self.records)))
                index = len(groups); groups.append(group)
                chosen.update({name: index for name in names})
            self.stable(check_code=True)
            temporary = output.with_name(output.name + ".partial-" + uuid.uuid4().hex)
            self.merge(groups, chosen, temporary)
            self.stable(check_code=True)
            if output.exists():
                output.rename(output.with_name(output.name + ".before-route-" + uuid.uuid4().hex))
            temporary.replace(output)
            result = {"status": "complete", "scope": "q0_cross_only", "whole_records_preserved": True,
                      "query_count": len(self.records), "query_bases": sum(r.length for r in self.query.records),
                      "query_sha256": self.query.source_sha256, "target_sha256": self.target.source_sha256,
                      "tool_sha256": self.tool_hash, "router_sha256": self.code, "metrics_sha256": self.metric_code,
                      "dependencies": self.dependency_hashes, "preset": self.preset,
                      "policy": json.loads(json.dumps(dataclasses.asdict(self.policy))), "threads": self.threads,
                      "decisions": decisions, "group_evidence": groups, "effective_sources": {name: groups[index]["cache_key"] for name, index in chosen.items()},
                      "output": self.contract.file_identity(output)}
            self.contract.atomic_write_json(receipt, result)
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("target", "query", "output", "receipt", "cache", "runtime-tools", "minimap2"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--threads", type=int, required=True)
    parser.add_argument("--preset", default="asm10")
    args = parser.parse_args()
    budget = int(os.environ.get("GPM_TASK_THREADS", args.threads))
    if args.threads > budget:
        parser.error("cannot exceed the outer task thread grant")
    router = Router(args.target, args.query, args.minimap2, args.cache, args.runtime_tools,
                    threads=args.threads, preset=args.preset)
    with router.signals():
        result = router.run(args.output, args.receipt)
    print("LONG_QUERY_ROUTING_COMPLETE", json.dumps({"queries": result["query_count"],
          "decisions": [{"query": d["query"], "filter": d.get("effective_filter", d["filter"])}
                        for d in result["decisions"]]}), flush=True)


if __name__ == "__main__":
    main()
