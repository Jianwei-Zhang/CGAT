"""Large-reference partial discovery: exact local lookup, bounded mapper work.

Search contexts/covered-base subtraction are explicit recall tradeoffs, not
claims of lossless whole-source alignment. Unroutable source parts retain the
native full-context fallback; no partial mapper output is accepted.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import itertools
from pathlib import Path
import shutil
import tempfile
import uuid

from .common import sha256_file, stable_id
from .q0_catalog import ObservedSourcePairs, partial_source_intervals
from .q0_query_windows import WindowPolicy, TargetWindow, plan_query_windows
from .q0_reference_index import ReferenceIndex, _signature
from .q0_regional_mapping import MAX_TARGET_BASES, prepare_regional_mapping
from .q0_regional_execution import ParentRequest, RegionalExecutor
from .q0_sources import Interval, Q0EvidenceError

REGIONAL_POLICY = {
    "version": 1, "reference_bases_at_least": 5_000_000_000, "preset": "asm10",
    "core_bases": 100_000, "query_context_bases": 10_000,
    "minimum_uncovered_bases": 100, "anchor_context_bases": 1_000_000,
    "reference_context_bases": 10_000, "target_context_bases": 10_000,
    "maximum_target_bases": MAX_TARGET_BASES,
    "covered_cross_bases": "subtract_complete_identity_ge_0.95_paired_ge_100",
    "unroutable": "native_full_source_all_anchors",
    "later_candidate_chr": "regional_execution_with_exact_legacy_query_selection",
    "whole_source_equivalence": False,
}


def enabled(reference_lengths, preset):
    return preset == REGIONAL_POLICY["preset"] and sum(reference_lengths.values()) >= REGIONAL_POLICY["reference_bases_at_least"]


class LocalReferenceCache:
    """Durable sealed DB, queried from a byte-identical compute-local copy.

    The durable receipt is not evidence. Every open verifies the DB bytes,
    catalog bindings and original PAF content. Failed/incomplete caches are
    preserved under an invalid suffix; never adopted as a sealed success.
    """
    def __init__(self, root, reference_inputs):
        self.root = Path(root).resolve(strict=True)
        self.reference_inputs = sorted(reference_inputs, key=lambda row: row["path"])
        self.scratch = tempfile.TemporaryDirectory(prefix="cgat-q0-reference-", dir="/tmp" if Path("/tmp").is_dir() else None)
        self.path = Path(self.scratch.name)/"reference.sqlite"
        self.paf_directory = Path(self.scratch.name)/"pafs"; self.paf_directory.mkdir()
        self.directory = None
        self.cached = False

    def __enter__(self): return self
    def __exit__(self, *args): self.close()

    def factory(self, parts, refs):
        from .q0_preparation import artifact_path, json_file
        self.binding = ReferenceIndex.bindings(parts, refs)
        key = stable_id("reference-index", {"binding": self.binding, "inputs": self.reference_inputs})
        relative = f"grt/evidence/q0_prepare/indexes/{key}"
        # Reject symlink components even if they happen to resolve inside root.
        current = self.root
        for component in Path(relative).parts:
            current /= component
            if current.is_symlink(): raise Q0EvidenceError("linked private reference index is forbidden")
        self.directory = artifact_path(self.root, relative)
        if self.directory.exists():
            try:
                receipt = json_file(self.directory/"success.json")
                db = self.directory/"reference.sqlite"
                if db.is_symlink(): raise Q0EvidenceError("linked sealed index is forbidden")
                if (receipt.get("status") != "success" or receipt.get("key") != key
                        or receipt.get("inputs") != self.reference_inputs
                        or receipt.get("size") != db.stat().st_size):
                    raise Q0EvidenceError("sealed reference cache identity differs")
                before = _signature(db)
                shutil.copyfile(db, self.path)
                if (sha256_file(self.path) != receipt["sha256"] or _signature(db) != before):
                    raise Q0EvidenceError("sealed reference index changed during copy")
                index = ReferenceIndex.open(self.path, self.root, parts, refs, local_paf_directory=self.paf_directory)
                self.cached = True
                return index
            except (OSError, ValueError, KeyError, TypeError):
                # Preserve the rejected original; only discard our private copy.
                self.directory.rename(self.directory.with_name(self.directory.name+".invalid-"+uuid.uuid4().hex))
                self.path.unlink(missing_ok=True)
        return ReferenceIndex.create(self.path, self.root, parts, refs)

    def publish(self):
        from .q0_preparation import atomic_write_json
        if self.cached: return
        if self.directory is None: raise Q0EvidenceError("reference index was not constructed")
        # build_catalog seals and closes the connection before this call.
        import sqlite3
        with sqlite3.connect(self.path.as_uri()+"?mode=ro", uri=True) as check:
            if check.execute("SELECT value FROM metadata WHERE name='sealed'").fetchone() != ("true",):
                raise Q0EvidenceError("cannot publish an unsealed reference index")
        check.close()
        key = self.directory.name
        digest = sha256_file(self.path)
        staged = self.directory.with_name(key+".staging-"+uuid.uuid4().hex)
        staged.mkdir(parents=True)
        shutil.copyfile(self.path, staged/"reference.sqlite")
        if sha256_file(staged/"reference.sqlite") != digest:
            raise Q0EvidenceError("reference cache publication changed DB bytes")
        atomic_write_json(staged/"success.json", {"status": "success", "key": key,
                          "inputs": self.reference_inputs, "sha256": digest, "size": self.path.stat().st_size})
        staged.rename(self.directory)

    def close(self): self.scratch.cleanup()


def observe_part_hits(catalog, hits, observed):
    """Record BOTH source sides, even when candidate discovery skips a row."""
    for hit in hits:
        if isinstance(observed, ObservedSourcePairs):
            query, target = catalog.parts[hit.query_name], catalog.parts[hit.target_name]
            observed.observe_alignment(hit, query.source, target.source,
                                       query_offset=query.interval.start, target_offset=target.interval.start)
        yield hit


def plan_parent(catalog, index, windows):
    """Plan a parent's exact targets before selecting native fallback."""
    planned = []
    for query in windows:
        regions = index.regions(query.segment_id, Interval(query.start,query.end),
                                anchor_context=1_000_000, reference_context=10_000)
        rows = index.targets(regions, context=10_000, exclude=[query.segment_id])
        bases = sum(i.length for values in rows.values() for i in values)
        if not rows or bases > MAX_TARGET_BASES:
            return [], "no_reference_targets" if not rows else "regional_target_budget"
        targets = [TargetWindow(key,catalog.parts[key].interval.length,i.start,i.end)
                   for key,values in rows.items() for i in values]
        planned.append((query, targets))
    return planned, None


def prepare_partial(root, catalog, index, observed, tool, *, reference_lengths, preset, threads, skip_self=False, complete_tasks=(), required_target_ids=None):
    """Return complete regional tasks and a declared full-native fallback set.

    With a verified allocation bound, fresh metadata-only planners share the
    run CPU/memory budget with <=2-thread/4GiB mappers. Unknown memory keeps
    serial lookup and <=4 mappers. Native fallback never overlaps this pool.
    """
    if not isinstance(observed, ObservedSourcePairs):
        raise Q0EvidenceError("regional work selection requires complete cross coverage")
    if type(threads) is not int or threads < 1:
        raise Q0EvidenceError("regional thread budget must be a positive integer")
    native_scopes = None
    if complete_tasks:
        from .q0_regional_candidates import CompletedNativeScopes
        native_scopes = CompletedNativeScopes(root,catalog,index,complete_tasks,tool,preset)
        required_mask = native_scopes.mask(required_target_ids if required_target_ids is not None else catalog.parts)
    holes = partial_source_intervals(catalog, minimum_uncovered_bp=100, observed=observed)
    policy = WindowPolicy(core_bases=100_000, context_bases=10_000,
                          trigger_query_bases=1, trigger_longest_bases=1, minimum_uncovered_bases=100)
    windows = plan_query_windows({key: part.interval.length for key, part in catalog.parts.items()}, holes, policy=policy) or ()
    execution = RegionalExecutor(index, threads)
    mapper_threads = execution.budget.mapper_threads; workers = execution.budget.mapper_workers
    tasks, fallback, pending = [], set(), []
    report = {"policy": dict(REGIONAL_POLICY), "window_policy": asdict(policy), "planned_windows": len(windows),
              "residual_source_parts": len(holes), "parents_satisfied_by_complete_native_matrices": 0, "parents_satisfied_by_scoped_approximate_matrices": 0,
              "approximate_scope_task_ids":native_scopes.approximate_scope_task_ids if native_scopes else [], "residual_bases": sum(i.length for values in holes.values() for i in values),
              "mapper_threads": mapper_threads, "maximum_workers": workers,
              "address_space_bytes_per_mapper": 4*1024**3, "fallback_sources": []}
    def consume():
        future = pending.pop(0)
        task = future.result()
        tasks.append(task)
        if len(tasks)%100 == 0:
            print(f"LGZ q0 regional progress: completed={len(tasks)} planned={len(windows)} fallback_sources={len(fallback)}", flush=True)
    def requests():
        for segment_id, group in itertools.groupby(windows, key=lambda w: w.segment_id):
            if native_scopes is not None and native_scopes.remaining_targets(segment_id,required_mask) == 0:
                native_only=native_scopes.remaining_targets(segment_id,required_mask,include_approximate=False)==0
                field=('parents_satisfied_by_complete_native_matrices' if native_only else 'parents_satisfied_by_scoped_approximate_matrices')
                report[field] += 1
                continue  # Tested relationships, not an invented coverage/placement assertion.
            yield ParentRequest("partial", segment_id, tuple(group))
    with execution, ThreadPoolExecutor(max_workers=workers, thread_name_prefix="q0-region") as pool:
        for request, (planned, _, reason) in execution.ordered(requests()):
            segment_id = request.segment_id
            if reason is not None:
                fallback.add(segment_id); report["fallback_sources"].append({"segment_id":segment_id,"reason":reason})
                continue
            for query, targets in planned:
                if skip_self and any(catalog.parts[t.segment_id].source.dataset == catalog.parts[query.segment_id].source.dataset for t in targets):
                    raise Q0EvidenceError("--skip-self conflicts with required regional supplementary comparisons")
                if len(pending) >= workers: consume()
                pending.append(pool.submit(prepare_regional_mapping, root,catalog,query,targets,tool,
                                           reference_bases=sum(reference_lengths.values()),preset=preset,threads=mapper_threads))
                if threads == 1: consume()  # Owner planning cannot overlap the one granted mapper CPU.
        while pending: consume()
    report.update(execution.report)
    report["completed_regional_tasks"] = len(tasks)
    return tasks, sorted(fallback), report
