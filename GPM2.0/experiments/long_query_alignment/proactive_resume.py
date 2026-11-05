"""Private, same-reference-task checkpoints; never a user configuration surface.

Only an adapter holding its task lock may select/reopen an attempt. Identity
changes select a fresh attempt. Cached successful commands/cells are rechecked;
partial outputs are archived, not reused or deleted. No in-call mapper retry.
"""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import uuid

import minimap_index_context as mic
import native_first as nf
import ordinary_partition_alignment as opa
import proactive_reference_plan as pp
import recovery_publication as rp
import windowed_alignment as wa

STATE = "proactive-resume-state.json"
LOCATOR = ".long-cigar-resume.json"
MAX_STATE = 64 * 1024**2
# Frozen full source profile from the reviewed pre-fix recovery runtime. Only
# ordinary native completions, never old recovered cells, may cross this fix.
_REVIEWED_LEGACY_RUNTIME = "85a120a387487e29a71b4e74d8b2ea100b0c2f4cfcf146c6b5558919473cdecd"
_REVIEWED_METADATA_RUNTIME = "c9d6e29d620ecd80d48ebd496d811569961a7e6f9a495646d7f46b8584ea686d"
_REVIEWED_PARAMETER_RUNTIME = "c83a96b95826d2d58055ac551456124e9acbc0d0331287a633f28f3902e3d560"



def read_json(path, *, limit=MAX_STATE):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise wa.ExperimentError("invalid/oversized private resume metadata")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise wa.ExperimentError("private resume metadata grew beyond its budget")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise wa.ExperimentError("private resume metadata must be an object")
    return value


def adapter_key(args, runtime):
    executable = shutil.which("minimap2")
    tool = nf.source_identity(Path(executable).resolve()) if executable else None
    key = {"schema": 1, "runtime_sha256": runtime["sha256"], "threads": args.threads,
            "preset": args.preset, "target": {"path": str(args.target.resolve()), **wa.fingerprint(args.target.resolve())},
            "query": {"path": str(args.query.resolve()), **wa.fingerprint(args.query.resolve())}, "tool": tool}
    if getattr(args, "minimap_filter", None) is not None:
        key["minimap_filter"] = args.minimap_filter
    return key


def _same_identity_except_ctime(left, right):
    return (isinstance(left, dict) and isinstance(right, dict)
            and set(left) == set(right) and "ctime_ns" in left
            and {k:v for k,v in left.items() if k != "ctime_ns"}
                == {k:v for k,v in right.items() if k != "ctime_ns"})


def _compatible_runtime(candidate, old_key, key, runtime, state):
    if old_key["runtime_sha256"] == key["runtime_sha256"]:
        return True
    if runtime is None:
        return False
    previous = read_json(candidate / "server-alignment.json").get("runtime", {})
    old_files, new_files = previous.get("files_sha256", {}), runtime.get("files_sha256", {})
    if (previous.get("sha256") != old_key["runtime_sha256"]
            or not old_files or set(new_files) - set(old_files) not in (set(), {"minimap_options.py"},
                {"ordinary_partition_alignment.py"}, {"minimap_options.py", "ordinary_partition_alignment.py"})
            or set(old_files) - set(new_files)
            or any(previous.get(k) != runtime.get(k) for k in
                   ("native_companion_sha256", "native_companion_platform", "recovered_output_admission"))):
        return False
    if old_files == new_files:
        # Non-mapping package/base metadata changed; payload checks still run.
        return True
    profile = hashlib.sha256(json.dumps(old_files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    current_profile = hashlib.sha256(json.dumps(new_files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    approved = (profile in {_REVIEWED_LEGACY_RUNTIME, _REVIEWED_METADATA_RUNTIME, _REVIEWED_PARAMETER_RUNTIME}
                and [profile, current_profile] in runtime.get("native_resume_source_profiles", []))
    if not approved:
        return False
    stages = state["stages"]
    if profile == _REVIEWED_LEGACY_RUNTIME:
        # The pre-metadata-fix runtime never receives recovered-cell admission.
        return ((set(stages) == {"groups", "ordinary"} or
                 all(n in stages for n in ("groups", "target-store", "index", "ordinary")))
                and not any(n.startswith("cell:") for n in stages))
    # Performance-only adapter changes retain the already-fixed recovery kernels.
    # Old native/cell payloads are STILL fully verified on reopen/publication.
    kernels = ("guided_alignment.py", "windowed_alignment.py", "native_chain_state.py",
               "native_recovery.py", "native_selection.py", "post_dp_selection.py",
               "whole_query_scores.py", "minimap_index_context.py")
    if any(old_files.get(name) != new_files.get(name) for name in kernels):
        return False
    return (set(stages) == {"groups", "ordinary"} or
            all(n in stages for n in ("groups", "target-store", "index"))
            and ("ordinary" in stages or "threshold" in stages))


def _transition_attempt(candidate, locator, previous, key, runtime):
    """Reviewed control migration; never change input/index/PAF bytes or commands."""
    old_key = previous.get("key")
    fields = {"schema", "runtime_sha256", "threads", "preset", "target", "query", "tool"}
    if "minimap_filter" in key:
        fields.add("minimap_filter")
    if (not isinstance(old_key, dict) or set(old_key) != fields or set(key) != fields
            or any(old_key[k] != key[k] for k in ("schema", "threads", "preset"))
            or old_key.get("minimap_filter") != key.get("minimap_filter")
            or any(not _same_identity_except_ctime(old_key[k], key[k]) for k in ("target", "query", "tool"))):
        return False
    state_path = candidate / "selective" / STATE
    state = read_json(state_path)
    if (state.get("schema") != 1 or state.get("key") != old_key
            or type(state.get("bound")) is not dict or type(state.get("stages")) is not dict):
        raise wa.ExperimentError("private resume state/locator disagree; preserving completed data")
    if not _compatible_runtime(candidate, old_key, key, runtime, state):
        return False
    verified = {}
    for role, bound in (("target", "reference"), ("query", "query")):
        expected = state["bound"].get(bound, {})
        path = Path(key[role]["path"])
        if (expected.get("source") != str(path.resolve())
                or not wa.identity_matches(path, expected, verify_content=True)):
            raise wa.ExperimentError("resume refused: original " + role + " content/identity changed; completed data preserved")
        verified[role] = {"source": str(path), "sha256": expected["sha256"]}
    if read_json(state_path) != state or read_json(locator) != previous:
        raise wa.ExperimentError("resume metadata changed during content verification")
    state["key"] = key
    state.setdefault("key_transitions", []).append({"previous_key": old_key,
        "verified_original_sources": verified,
        "reason": "content_verified_ctime_or_reviewed_validation_runtime",
        "payload_completion_checks_still_required": True})
    # Retain both old control receipts and roll back both if either write fails.
    state_backup = locator_backup = None
    try:
        state_backup = archive_partial(state_path)
        locator_backup = archive_partial(locator)
        wa.write_json(state_path, state)
        wa.write_json(locator, {"schema": 1, "key": key, "attempt": str(candidate)})
    except BaseException:
        if state_backup is not None:
            os.replace(state_backup, state_path)
        if locator_backup is not None:
            os.replace(locator_backup, locator)
        raise
    return True


def select_attempt(run_dir, key, *, runtime=None):
    """Same work only; metadata-only changes require original content proof."""
    run_dir = Path(run_dir).resolve()
    locator = run_dir / LOCATOR
    if locator.is_symlink():
        raise wa.ExperimentError("private resume locator is linked; preserving it without following")
    if locator.exists():
        value = read_json(locator, limit=1024**2)
        candidate = Path(value.get("attempt", ""))
        if (value.get("schema") == 1
                and candidate.is_absolute() and candidate.parent == run_dir
                and candidate.name.startswith(".long-cigar-attempt-") and not candidate.is_symlink()
                and candidate.is_dir() and (candidate / "selective" / STATE).is_file()):
            if value.get("key") == key or _transition_attempt(candidate, locator, value, key, runtime):
                return candidate, True
    attempt = Path(tempfile.mkdtemp(prefix=".long-cigar-attempt-", dir=run_dir))
    wa.write_json(locator, {"schema": 1, "key": key, "attempt": str(attempt)})
    return attempt, False


def archive_partial(path):
    """Keep failed/stale private evidence; never overwrite or consume it."""
    path = Path(path)
    if path.is_symlink():
        raise wa.ExperimentError("linked private resume artifact; refusing to follow it")
    if path.exists():
        saved = path.with_name(path.name + ".previous-" + uuid.uuid4().hex)
        path.rename(saved)
        return saved
    return None


class Checkpoint:
    def __init__(self, root, key):
        self.root, self.key = Path(root), key
        self.enabled = key is not None
        self.path = self.root / STATE
        self.data = {"schema": 1, "key": key, "bound": {}, "stages": {}}
        self.reused = {"input_groups": 0, "sequence_stores": 0, "index": 0, "ordinary_group": 0,
                       "threshold_metadata": 0, "long_cells": 0}
        if self.enabled and self.path.exists():
            self.data = read_json(self.path)
            if (self.data.get("schema") != 1 or self.data.get("key") != key
                    or type(self.data.get("bound")) is not dict or type(self.data.get("stages")) is not dict):
                raise wa.ExperimentError("private resume identity/schema changed")
        elif self.enabled:
            self.save()

    def save(self):
        if self.enabled:
            wa.write_json(self.path, self.data)

    def bind(self, name, value):
        if name in self.data["bound"] and self.data["bound"][name] != value:
            old = self.data["bound"][name]
            # These identities originate in an actual stable source scan/hash.
            if (name not in ("query", "reference", "tool") or not old.get("sha256")
                    or not _same_identity_except_ctime(old, value)):
                raise wa.ExperimentError("private resume input/tool/policy identity changed: " + name)
        self.data["bound"][name] = value
        self.save()

    def get(self, name):
        return self.data["stages"].get(name) if self.enabled else None

    def mark(self, name, value):
        if self.enabled:
            self.data["stages"][name] = value
            self.save()

    def groups(self, catalog, plan, *, prepared_workspace=None):
        old = self.get("groups")
        path = self.root / "inputs/groups.json"
        if old:
            if wa.sha256(rp.regular_under(path, self.root)) != old["sha256"]:
                raise wa.ExperimentError("cached input groups changed")
            groups = read_json(path)
            expected = ([plan["native_queries"]] if plan["native_queries"] else []) + [[n] for n in plan["long_queries"]]
            if (groups.get("status") != "complete_inputs_only" or groups.get("source_sha256") != catalog.source_sha256
                    or groups.get("all_original_records_accounted") is not True
                    or [g["queries"] for g in groups["groups"]] != expected):
                raise wa.ExperimentError("cached groups omit or alter original queries")
            for group in groups["groups"]:
                source = Path(group["path"])
                if group.get("original_input_reused"):
                    if source != Path(catalog.source) or group["sha256"] != catalog.source_sha256:
                        raise wa.ExperimentError("cached original input path/content changed")
                else:
                    rp.regular_under(source, self.root / "inputs")
                    if wa.verified_sha256(source) != group["sha256"]:
                        raise wa.ExperimentError("cached group bytes changed")
            catalog.require_unchanged()
            self.reused["input_groups"] += 1
            return groups
        archive_partial(self.root / "inputs")
        groups = pp.materialize(catalog, plan, self.root / "inputs", prepared_workspace=prepared_workspace)
        self.mark("groups", {"sha256": wa.sha256(path)})
        return groups

    def store(self, source, spool, stage):
        old = self.get(stage)
        spool = Path(spool)
        if old:
            if (Path(old["source"]["source"]) != Path(source).resolve()
                    or not wa.identity_matches(source, old["source"], verify_content=True)):
                raise wa.ExperimentError("cached sequence store source changed")
            rp.regular_under(spool, self.root)
            before = wa.fingerprint(spool)
            if wa.verified_sha256(spool) != old["sha256"] or wa.fingerprint(spool) != before:
                raise wa.ExperimentError("cached sequence spool changed")
            offset = 0
            records = old["records"]
            if not records:
                raise wa.ExperimentError("cached sequence store is empty")
            for name, row in records.items():
                if (not name or not isinstance(row, dict) or row.get("offset") != offset
                        or type(row.get("length")) is not int or not 0 < row["length"] <= wa.INT32_MAX):
                    raise wa.ExperimentError("cached sequence store record layout changed")
                offset += row["length"]
            if offset != before["size"]:
                raise wa.ExperimentError("cached sequence store extent changed")
            store = wa.FastaStore.__new__(wa.FastaStore)
            store.source, store.identity, store.records = Path(source).resolve(), old["source"], records
            store.spool, store.spool_identity, store.normalized_sha256 = spool.resolve(), before, old["sha256"]
            store.handle = spool.open("rb")
            try:
                store.check_binding(source)
            except BaseException:
                store.close()
                raise
            self.reused["sequence_stores"] += 1
            return store
        archive_partial(spool)
        store = wa.FastaStore(source, spool)
        try:
            self.mark(stage, {"source": store.identity, "sha256": store.normalized_sha256, "records": store.records})
        except BaseException:
            store.close()
            raise
        return store

    def index(self, target, tool_sha256):
        marker = self.get("index")
        if not marker:
            return None
        path = self.root / "index-base.json"
        if wa.sha256(rp.regular_under(path, self.root)) != marker["sha256"]:
            raise wa.ExperimentError("cached original index catalog changed")
        index = read_json(path)
        if (index["reference_sha256"] != target.identity["sha256"] or index["tool_sha256"] != tool_sha256
                or index["index_policy"] != "original_default_no_I_override"
                or wa.verified_sha256(rp.regular_under(self.root / "target.default.mmi", self.root)) != index["sha256"]):
            raise wa.ExperimentError("cached original index source/tool/policy changed")
        raw = mic.read_catalog(self.root / "target.default.mmi", target.records)
        if len(raw["parts"]) != len(index["parts"]):
            raise wa.ExperimentError("cached original index partition count changed")
        for expected, part in zip(raw["parts"], index["parts"]):
            if (any(part[k] != expected[k] for k in ("part_index", "records", "start", "end"))
                    or wa.verified_sha256(rp.regular_under(part["path"], self.root)) != part["sha256"]):
                raise wa.ExperimentError("cached original index part changed")
        self.reused["index"] += 1
        return index

    def save_index(self, index):
        wa.write_json(self.root / "index-base.json", index)
        self.mark("index", {"sha256": wa.sha256(self.root / "index-base.json")})

    def ordinary(self, mm, target, query, *, fraction=None, parts=None, records=None):
        marker = self.get("ordinary")
        if not marker:
            return None
        if marker.get("kind") == opa.KIND:
            if parts is None or records is None:
                raise wa.ExperimentError("partitioned ordinary completion has no original index/query context")
            path = self.root / "ordinary-native" / opa.RECEIPT
            receipt = opa.verify(path.parent, mm, query, parts, records, fraction=fraction)
        else:
            if marker.get("kind") is not None:
                raise wa.ExperimentError("unknown ordinary completion kind")
            path = self.root / "ordinary-native/native-attempt.json"
            receipt = rp.verify_attempt(path, self.root, "native_success",
                tool=mm, target=target, query=query, fraction=fraction)
        if wa.sha256(path) != marker["sha256"]:
            raise wa.ExperimentError("cached ordinary completion receipt changed")
        self.reused["ordinary_group"] += 1
        return receipt

    def save_ordinary(self, *, partitioned=False):
        name = opa.RECEIPT if partitioned else "native-attempt.json"
        marker = {"sha256": wa.sha256(self.root / "ordinary-native" / name)}
        if partitioned:
            marker["kind"] = opa.KIND
        self.mark("ordinary", marker)

    def cell(self, name, part_index):
        return self.get("cell:" + str(part_index) + ":" + name)

    def save_cell(self, row):
        self.mark("cell:" + str(row["part_index"]) + ":" + row["query"], row)
