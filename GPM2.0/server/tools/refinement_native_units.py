"""Immutable native consumed-output units; never adopt an unsealed native tree.

The workspace orchestrator holds the exclusive lock. Each admission starts fresh;
only a format-checked output is restored, with an explicit original producer.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import time
from datetime import datetime, timezone
import uuid

try:
    from workspace_layout import automatic_dir, WorkspaceLayout, TOOL_DIRECTORIES
    from workspace_migration import durable_json, sync_directories
    from post_lgz_degap import digest, stat_key, atomic_json
    from refinement_tools import fingerprint
    from refinement_path import PathError
except ModuleNotFoundError:
    from .workspace_layout import automatic_dir, WorkspaceLayout, TOOL_DIRECTORIES
    from .workspace_migration import durable_json, sync_directories
    from .post_lgz_degap import digest, stat_key, atomic_json
    from .refinement_tools import fingerprint
    from .refinement_path import PathError

SCHEMA = "cgat.native-refinement-unit"
SUMMARY = "native_substeps.json"
REQUEST = "native_launch.json"
RECEIPT = "unit_complete.json"
HELPERS = ("refinement_native_units.py", "refinement_native_runner.py")


def helper_hashes(tool="quartet"):
    extra = {"degap": ("refinement_degap_units.py",), "tgsgapcloser": ("refinement_tgs_units.py",),
             "lrgapcloser": ("refinement_lr_units.py",)}
    names = HELPERS + extra.get(tool, ())
    return {name: digest(Path(__file__).with_name(name)) for name in names}


def owned(root, path):
    relative = Path(path).absolute().relative_to(root).as_posix()
    checked = WorkspaceLayout.detect(root).path(relative)
    if checked.is_symlink():
        raise PathError("native unit file must not be a symlink")
    return checked


def checked_json(root, path):
    path = owned(root, path)
    before = stat_key(path)
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise PathError("native unit receipt must be a JSON object")
    sha = value.pop("payload_sha256")
    if sha != fingerprint(value) or stat_key(path) != before:
        raise PathError("native unit receipt changed or is unsealed")
    return value


def seal(path, value):
    durable_json(path, {**value, "payload_sha256": fingerprint(value)})


def file_fact(path):
    path = Path(path)
    before = stat_key(path)
    sha = digest(path)
    if before != stat_key(path):
        raise PathError("native unit input changed while hashing")
    return {"sha256": sha, "bytes": before[2]}, before


def validate_paf(path, *, allow_empty, require_cigar=True):
    """Validate native output structure, not an invented accuracy assessment."""
    count = 0
    with Path(path).open() as stream:
        for line in stream:
            fields = line.rstrip("\n").split("\t")
            try:
                if len(fields) < 12 or not fields[0] or not fields[5] or fields[4] not in {"+", "-"}:
                    raise ValueError()
                qlen, a, b, tlen, x, y, matches, block, quality = (int(fields[i]) for i in (1, 2, 3, 6, 7, 8, 9, 10, 11))
                if not (0 <= a < b <= qlen and 0 <= x < y <= tlen and 0 <= matches <= block and block > 0 and 0 <= quality <= 255):
                    raise ValueError()
                cigars = [field[5:] for field in fields[12:] if field.startswith("cg:Z:")]
                if len(cigars) > 1 or (require_cigar and not cigars):
                    raise ValueError()
                if cigars:
                    parts = re.findall(r"([1-9][0-9]*)([MIDN=X])", cigars[0])
                    if "".join(n + op for n, op in parts) != cigars[0]:
                        raise ValueError()
                    if (sum(int(n) for n, op in parts if op in "MI=X") != b - a
                            or sum(int(n) for n, op in parts if op in "MDN=X") != y - x):
                        raise ValueError()
            except (ValueError, IndexError) as error:
                raise PathError("invalid completed native PAF") from error
            count += 1
    if not count and not allow_empty:
        raise PathError("empty alignment is not a completed native unit")
    return {"records": count, "outcome": "aligned" if count else "empty_alignment"}


class UnitStore:
    def __init__(self, root, tool, run_id, session, native_command):
        self.root, self.tool, self.run_id = Path(root).resolve(), tool, run_id
        if tool != "quartet" or not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise PathError("unsupported native partial-recovery consumer")
        self.base = automatic_dir(self.root, tool) / "02_jobs"
        self.jobs = owned(self.root, self.base / run_id)
        self.directory = owned(self.root, self.jobs / "native_units")
        self.directory.mkdir(exist_ok=False)
        self.session, self.native_command, self.units = session, native_command, []
        self.write_summary(None)

    def write_summary(self, code):
        value = {"schema": "cgat.native-refinement-substeps", "schema_version": 1,
                 "tool": self.tool, "run_id": self.run_id, "session": self.session,
                 "native_command": self.native_command, "native_returncode": code,
                 "units": self.units, "status": "running" if code is None else "finished"}
        atomic_json(self.jobs / SUMMARY, {**value, "payload_sha256": fingerprint(value)})

    def find(self, key, binding, validate):
        for receipt in sorted(self.base.glob("*/native_units/" + key + "/" + RECEIPT)):
            try:
                run_id = receipt.parents[2].name
                if run_id == self.run_id or not re.fullmatch(r"[0-9a-f]{32}", run_id):
                    continue
                value = checked_json(self.root, receipt)
                if (value.get("schema") != SCHEMA or value.get("schema_version") != 1
                        or value.get("status") != "completed" or value.get("origin") is not None
                        or not isinstance(value.get("execution"), dict) or value["execution"].get("computed") is not True
                        or value.get("tool") != self.tool or value.get("run_id") != run_id
                        or value.get("key") != key or value.get("binding") != binding
                        or set(value.get("artifacts", {})) != {"output.paf"}):
                    continue
                output = owned(self.root, receipt.parent / "output.paf")
                fact, _ = file_fact(output)
                if value["artifacts"]["output.paf"] != fact["sha256"] or validate(output) != value["result"]:
                    continue
                return receipt, value
            except (OSError, ValueError, TypeError, KeyError):
                continue
        return None

    def run(self, unit, inputs, execute, restore, validate):
        facts, identities = {}, {}
        for role, path in inputs.items():
            facts[role], identities[role] = file_fact(path)
        binding = {"session": self.session, "unit": unit, "inputs": facts}
        key = fingerprint(binding)
        if any(row["key"] == key for row in self.units):
            raise PathError("native unit executed twice in one attempt")
        temporary = self.directory / ("incomplete-" + key + "-" + uuid.uuid4().hex)
        temporary.mkdir()
        started, started_at = time.monotonic(), datetime.now(timezone.utc).isoformat()
        cached = self.find(key, binding, validate)
        origin = None
        if cached is None:
            output = owned(self.root, execute())
        else:
            receipt, previous = cached
            output = owned(self.root, receipt.parent / "output.paf")
            # Keep the exact original receipt, not a reference to mutable history.
            shutil.copyfile(receipt, temporary / "producer.json")
            if checked_json(self.root, temporary / "producer.json") != previous:
                raise PathError("native unit producer receipt changed during restore")
            origin = {"run_id": previous["run_id"], "receipt": receipt.relative_to(self.root).as_posix(),
                      "receipt_sha256": digest(temporary / "producer.json")}
        fact, output_identity = file_fact(output)
        result = validate(output)
        if stat_key(output) != output_identity:
            raise PathError("native unit output changed during validation")
        if cached is not None and (fact["sha256"] != previous["artifacts"]["output.paf"] or result != previous["result"]):
            raise PathError("native unit producer changed during restore")
        shutil.copyfile(output, temporary / "output.paf")
        if digest(temporary / "output.paf") != fact["sha256"] or stat_key(output) != output_identity:
            raise PathError("native unit output changed while sealing")
        if any(stat_key(Path(path)) != identities[role] for role, path in inputs.items()):
            raise PathError("native unit consumed input changed during execution")
        artifacts = {"output.paf": fact["sha256"]}
        if origin is not None:
            artifacts["producer.json"] = origin["receipt_sha256"]
            consumed = owned(self.root, restore(temporary / "output.paf"))
            if digest(consumed) != fact["sha256"]:
                raise PathError("restored native unit does not match sealed output")
        else:
            consumed = output
        value = {"schema": SCHEMA, "schema_version": 1, "status": "completed", "tool": self.tool,
                 "run_id": self.run_id, "key": key, "binding": binding,
                 "consumed_inputs": {role: str(path) for role, path in inputs.items()},
                 "consumed_output": consumed.relative_to(self.root).as_posix(),
                 "origin": origin, "artifacts": artifacts, "result": result,
                 "execution": {"started_at": started_at, "ended_at": datetime.now(timezone.utc).isoformat(),
                               "seconds": time.monotonic() - started, "computed": origin is None}}
        for name in artifacts:
            with (temporary / name).open("rb") as stream:
                os.fsync(stream.fileno())
        seal(temporary / RECEIPT, value)
        destination = self.directory / key
        if destination.exists() or destination.is_symlink():
            raise PathError("native unit destination already exists")
        os.rename(temporary, destination)
        sync_directories(self.directory)
        row = {"key": key, "receipt": (destination / RECEIPT).relative_to(self.root).as_posix(),
               "receipt_sha256": digest(destination / RECEIPT), "reused": origin is not None,
               "origin": origin, "unit": unit, "result": result}
        self.units.append(row)
        self.write_summary(None)
        print(f"[CGAT NATIVE UNIT {'REUSED' if origin else 'COMPLETE'}] {unit['suffix']} key={key}", flush=True)
        return consumed


def launch(root, invocation, paths, record, native_binding):
    """Disclose the wrapper separately; never modify the pinned invocation."""
    if invocation.tool == "lrgapcloser":
        try:
            from refinement_lr_units import launch as launch_lr
        except ModuleNotFoundError:
            from .refinement_lr_units import launch as launch_lr
        return launch_lr(root, invocation, paths, record, native_binding)
    if invocation.tool == "tgsgapcloser":
        try:
            from refinement_tgs_units import launch as launch_tgs
        except ModuleNotFoundError:
            from .refinement_tgs_units import launch as launch_tgs
        return launch_tgs(root, invocation, paths, record, native_binding)
    if invocation.tool not in {"quartet", "degap"}:
        return invocation.command, None
    helpers = helper_hashes(invocation.tool)
    script_index = 3 if invocation.tool == "quartet" else 2
    request = {"schema": "cgat.native-refinement-launch", "schema_version": 1,
               "root": str(root), "tool": invocation.tool, "run_id": record["run_id"],
               "command": list(invocation.command), "cwd": str(invocation.cwd), "helpers": helpers,
               "session": {"native_binding": native_binding, "threads": record["threads"], "helpers": helpers}}
    destination = paths["02_jobs"] / REQUEST
    seal(destination, request)
    command = (*invocation.command[:script_index], str(Path(__file__).with_name("refinement_native_runner.py")),
               "--request", str(destination), "--", *invocation.command[script_index:])
    return command, destination


def capture_units(root, tool, run_id, code, *, required=False):
    """All evidence is in the current producer; no external cache needed offline."""
    if tool == "lrgapcloser":
        try:
            from refinement_lr_units import capture_units as capture_lr
        except ModuleNotFoundError:
            from .refinement_lr_units import capture_units as capture_lr
        return capture_lr(root, run_id, code, required=required)
    if tool == "tgsgapcloser":
        try:
            from refinement_tgs_units import capture_units as capture_tgs
        except ModuleNotFoundError:
            from .refinement_tgs_units import capture_units as capture_tgs
        return capture_tgs(root, run_id, code, required=required)
    if tool == "degap":
        try:
            from refinement_degap_units import capture_units as capture_degap
        except ModuleNotFoundError:
            from .refinement_degap_units import capture_units as capture_degap
        return capture_degap(root, run_id, code, required=required)
    jobs = automatic_dir(root, tool) / "02_jobs" / run_id
    summary_path = jobs / SUMMARY
    if not summary_path.exists() and not summary_path.is_symlink() and not required:
        return []
    value = checked_json(root, summary_path)
    request = checked_json(root, jobs / REQUEST)
    if (value.get("schema") != "cgat.native-refinement-substeps" or value.get("schema_version") != 1
            or value.get("status") != "finished" or value.get("tool") != tool or value.get("run_id") != run_id
            or type(value.get("native_returncode")) is not int or value.get("native_returncode") != code
            or value.get("session") != request["session"]
            or value.get("native_command") != request["command"] or request.get("tool") != tool
            or request.get("run_id") != run_id):
        raise PathError("native substep summary does not close this producer")
    artifacts, seen = [summary_path, jobs / REQUEST], set()
    for row in value["units"]:
        key = row["key"]
        if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key) or key in seen:
            raise PathError("invalid or duplicated native unit key")
        seen.add(key)
        receipt = owned(root, jobs / "native_units" / key / RECEIPT)
        unit = checked_json(root, receipt)
        if (row["receipt"] != receipt.relative_to(root).as_posix() or row["receipt_sha256"] != digest(receipt)
                or unit.get("schema") != SCHEMA or unit.get("schema_version") != 1 or unit.get("status") != "completed"
                or unit.get("tool") != tool or unit.get("run_id") != run_id or unit.get("key") != key
                or fingerprint(unit["binding"]) != key or unit["binding"]["session"] != value["session"]
                or unit["binding"]["unit"] != row["unit"] or unit["result"] != row["result"]
                or unit["origin"] != row["origin"] or type(row["reused"]) is not bool
                or bool(unit["origin"]) != row["reused"] or unit["execution"]["computed"] is not (not row["reused"])):
            raise PathError("invalid native unit completion closure")
        consumer = row["unit"]
        if (consumer.get("kind") != "quartet.minimap" or consumer.get("prefix") != "quartet"
                or consumer.get("aligner") != "minimap2" or consumer.get("allow_empty") is not True
                or consumer.get("plot") is not False or consumer.get("overwrite") is not False
                or not isinstance(consumer.get("suffix"), str) or not consumer["suffix"].startswith("flank_map_")
                or Path(consumer["suffix"]).name != consumer["suffix"] or "\\" in consumer["suffix"]):
            raise PathError("native unit has an unsupported pinned consumer")
        expected = {"output.paf", "producer.json"} if row["reused"] else {"output.paf"}
        if set(unit["artifacts"]) != expected:
            raise PathError("native unit artifact inventory is incomplete")
        for name, sha in unit["artifacts"].items():
            path = owned(root, receipt.parent / name)
            if digest(path) != sha:
                raise PathError("native unit artifact changed")
            artifacts.append(path)
        if validate_paf(receipt.parent / "output.paf", allow_empty=row["unit"]["allow_empty"]) != unit["result"]:
            raise PathError("native unit output format changed")
        consumed = owned(root, Path(root) / unit["consumed_output"])
        native = automatic_dir(root, tool) / "03_native" / run_id
        if (consumed != native / "tmp" / ("quartet." + consumer["suffix"] + ".paf")
                or digest(consumed) != unit["artifacts"]["output.paf"]):
            raise PathError("native consumer no longer has the sealed unit output")
        if row["reused"]:
            producer = checked_json(root, receipt.parent / "producer.json")
            origin = unit["origin"]
            if not isinstance(origin.get("run_id"), str) or not re.fullmatch(r"[0-9a-f]{32}", origin["run_id"]):
                raise PathError("invalid native unit producer run")
            expected_origin = jobs.parent / origin["run_id"] / "native_units" / key / RECEIPT
            if (origin["receipt"] != expected_origin.relative_to(root).as_posix()
                    or origin["receipt_sha256"] != unit["artifacts"]["producer.json"]
                    or producer.get("schema") != SCHEMA or producer.get("schema_version") != 1
                    or producer.get("status") != "completed" or producer.get("tool") != tool or producer.get("key") != key
                    or not isinstance(producer.get("execution"), dict) or producer["execution"].get("computed") is not True
                    or producer.get("origin") is not None or producer.get("run_id") != origin["run_id"]
                    or producer.get("binding") != unit["binding"] or producer.get("result") != unit["result"]
                    or producer.get("artifacts") != {"output.paf": unit["artifacts"]["output.paf"]}):
                raise PathError("native unit original producer does not match")
        artifacts += [receipt, consumed]
    return list(dict.fromkeys(artifacts))
