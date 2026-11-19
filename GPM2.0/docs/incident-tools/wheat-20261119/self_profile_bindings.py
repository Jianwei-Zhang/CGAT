"""Compose isolated self execution with existing native/cross orchestration.

No native commands/manifests are rewritten. Reuse completed batches without
launching their native helper (and its repeated index/merge scans). Merge once
per operation before the last original finish callback, even if it is native.
The owning caller must hold the normal workspace lock.
"""
import dataclasses
import json
from pathlib import Path
import shutil

from self_seed_profile import Profile, RECEIPT, OUTPUTS

SCHEMA = "incident_self_dispatch_v1"


class SelfBindings:
    def __init__(self, work, path, contract):
        self.work = Path(work).resolve(strict=True)
        self.path = Path(path).resolve(strict=True)
        self.contract = contract
        self.sha = contract.sha256_file(self.path)
        self.plan = json.loads(self.path.read_text())
        if self.plan.get("schema") != SCHEMA or self.plan.get("workspace") != str(self.work):
            raise ValueError("self dispatch plan belongs to another workspace/schema")
        if self.path.is_relative_to(self.work) or not self.plan.get("operations"):
            raise ValueError("self dispatch requires an isolated nonempty plan")
        dependency = self.plan.get("dependencies", {}).get("support", {})
        if Path(dependency.get("path", "")).resolve() != Path(__file__).resolve():
            raise ValueError("self dispatch support module is not bound")
        self.profiles, self.tasks, self.rows = {}, {}, {}
        for row in self.plan["operations"]:
            profile = Profile(row["profile"]["path"])
            rel = profile.source.parent.relative_to(self.work).as_posix()
            parts = Path(rel).parts
            if (profile.work != self.work or rel != row["operation"] or rel in self.profiles
                    or len(parts) != 3 or parts[0] != "runs" or not parts[1].startswith("chr_")
                    or row["unit_id"] != "q0_chr:" + parts[1][4:]):
                raise ValueError("unexpected or duplicate self operation")
            if set(row["scripts"]) != {str(i) for i in profile.selected}:
                raise ValueError("self execution script inventory differs from profile")
            if set(row["native_commands"]) != {str(i) for i in range(len(profile.native["batches"]))}:
                raise ValueError("native self command inventory is incomplete")
            task_file = self.work / "runs" / parts[1] / "q0_alignment_tasks.json"
            if row["task_manifest"]["path"] != str(task_file):
                raise ValueError("self task manifest path differs")
            planned = {task["command"] for task in json.loads(task_file.read_text())["tasks"]}
            for i, batch in enumerate(profile.native["batches"]):
                command = (Path(batch["directory"]) / "command.sh").relative_to(self.work).as_posix()
                if command not in planned or command in self.tasks:
                    raise ValueError("self batch is not a unique planned q0 task")
                self.tasks[command] = (rel, i)
            for script in row["scripts"].values():
                p = Path(script["path"])
                if not p.is_absolute() or p.is_symlink() or p.resolve().is_relative_to(self.work):
                    raise ValueError("self override script must be isolated")
            self.profiles[rel], self.rows[rel] = profile, row
        self.verify(full=True)

    def verify(self, *, full=False, operations=None):
        if self.contract.sha256_file(self.path) != self.sha:
            raise ValueError("self dispatch plan changed")
        for row in self.plan["dependencies"].values():
            if self.contract.sha256_file(Path(row["path"])) != row["sha256"]:
                raise ValueError("self dispatch dependency changed")
        for rel in (self.profiles if operations is None else operations):
            profile = self.profiles[rel]
            row = self.rows[rel]
            profile.verify()
            if self.contract.sha256_file(profile.path) != row["profile"]["sha256"]:
                raise ValueError("self profile identity changed")
            task_manifest = row["task_manifest"]
            if self.contract.sha256_file(Path(task_manifest["path"])) != task_manifest["sha256"]:
                raise ValueError("q0 self task manifest changed")
            if full:
                for i, batch in enumerate(profile.native["batches"]):
                    path = Path(batch["directory"]) / "command.sh"
                    if self.contract.file_identity(path, relative_to=self.work) != row["native_commands"][str(i)]:
                        raise ValueError("native self command changed")
            for script in row["scripts"].values():
                if self.contract.file_identity(Path(script["path"])) != script:
                    raise ValueError("self override script changed")

    def operations_for(self, unit_id):
        return sorted(rel for rel, row in self.rows.items() if row["unit_id"] == unit_id)

    def bind_prepared(self, prepared):
        if prepared is None:
            return None
        operations = self.operations_for(prepared.unit_id)
        if not operations:
            return prepared
        self.verify(full=True, operations=operations)
        if prepared.kind != "q0_chromosome_alignments":
            raise ValueError("self profile can bind only q0 chromosome checkpoints")
        proof = {"schema": SCHEMA, "operations": [self.rows[rel] for rel in operations],
                 "dependencies": self.plan["dependencies"]}
        payload = {**prepared.input_payload, "incident_self_execution": proof}
        return dataclasses.replace(prepared, input_payload=payload,
                                   input_fingerprint=self.contract.fingerprint(payload))

    def output_identities(self, unit_id):
        result = []
        for rel in self.operations_for(unit_id):
            profile = self.profiles[rel]
            marker = profile.source.parent / "self_batch_result.json"
            info = json.loads(marker.read_text())
            if (info.get("manifest_sha256") != profile.merge_manifest_sha
                    or info.get("batches") != len(profile.manifest["batches"])
                    or info.get("result_sha256") != self.contract.sha256_file(Path(profile.manifest["output"]))):
                raise ValueError("merged self output is not certified by this profile")
            result.append(self.contract.file_identity(marker, relative_to=self.work))
            for i in profile.selected:
                directory = Path(profile.manifest["batches"][i]["directory"])
                if not profile.validate_batch(i):
                    raise ValueError("self profile batch does not verify at outer commit")
                result.extend(self.contract.file_identity(directory / name, relative_to=self.work)
                              for name in (RECEIPT, "complete.json"))
        return result

    def verify_cached_sources(self, profile, index):
        """Verify source identities, not a dispensable derived index, on reuse."""
        manifest = profile.native
        batch = manifest["batches"][index]
        tool = Path(shutil.which("minimap2") or "").resolve()
        expected = {batch["query"]: batch["query_sha256"], str(tool): manifest["identities"]["tool"]}
        expected.update({manifest[field]: manifest["identities"][field] for field in ("target", "name_map", "restore")})
        if any(self.contract.sha256_file(Path(path)) != sha for path, sha in expected.items()):
            raise ValueError("completed self batch source/tool changed")

    def dispatch(self, original):
        def run(tasks, budget, children, cancel_signal, on_start, on_line, on_finish,
                environment, *, dispatch=None):
            self.verify(full=True)
            owned, groups = {}, {}
            for task in tasks:
                try:
                    key = task.command.relative_to(self.work).as_posix()
                except ValueError:
                    continue
                if key in self.tasks:
                    rel, i = self.tasks[key]
                    if task.unit_id != self.rows[rel]["unit_id"]:
                        raise ValueError("self task has a different execution unit")
                    owned[id(task)] = (rel, i)
                    groups.setdefault(rel, []).append(task)
            remaining = {}
            for rel, group in groups.items():
                if len(group) != len(self.profiles[rel].native["batches"]) or len({t.command for t in group}) != len(group):
                    raise ValueError("self dispatch received only part of an operation")
                remaining[rel] = len(group)

            def finish(task, code, cancelling):
                if id(task) in owned and code == 0 and not cancelling:
                    rel, _i = owned[id(task)]
                    remaining[rel] -= 1
                    if remaining[rel] == 0:
                        if not self.profiles[rel].merge():
                            raise ValueError("self operation finished without a complete verified merge")
                on_finish(task, code, cancelling)

            pending, restored, cached = [], {}, []
            for task in tasks:
                if id(task) not in owned:
                    pending.append(task); restored[id(task)] = task
                    continue
                rel, i = owned[id(task)]
                profile = self.profiles[rel]
                batch = profile.manifest["batches"][i]
                if (Path(batch["directory"]) / "complete.json").exists():
                    self.verify_cached_sources(profile, i)
                    if not profile.validate_batch(i):
                        raise ValueError("existing self batch conflicts with plan; preserve and refresh")
                    cached.append(task)
                    continue
                replacement = (dataclasses.replace(task, command=Path(self.rows[rel]["scripts"][str(i)]["path"]))
                               if i in profile.selected else task)
                pending.append(replacement); restored[id(replacement)] = task
            for task in cached:
                on_start(task, 1)
                on_line(task, "SELF_BATCH_REUSED verified source/output identities; no mapper or repeated index scan")
                finish(task, 0, False)
            def start(task, threads):
                native = restored[id(task)]
                on_start(native, threads)
                if native is not task:
                    on_line(native, "SELF_EXECUTION_OVERRIDE native=" + str(native.command) + " executed=" + str(task.command))
            def done(task, code, cancelling):
                native = restored[id(task)]
                if id(native) in owned:
                    self.verify(operations=[owned[id(native)][0]])
                return finish(native, code, cancelling)
            return original(pending, budget, children, cancel_signal, start,
                            lambda task, line: on_line(restored[id(task)], line), done,
                            environment, dispatch=dispatch)
        return run


def checkpoint_class(base_class, bindings):
    """base_class may already include the immutable cross-routing adapter."""
    import run_outer_checkpoints as outer
    class SelfCheckpoints(base_class):
        def prepare(self, unit_id, command_relpath):
            return bindings.bind_prepared(super().prepare(unit_id, command_relpath))
        def _output_identities(self, prepared):
            return super()._output_identities(prepared) + bindings.output_identities(prepared.unit_id)
        def commit(self, prepared):
            if not bindings.operations_for(prepared.unit_id):
                return super().commit(prepared)
            outputs = self._output_identities(prepared)
            fresh = base_class(self.server_dir).prepare(prepared.unit_id, prepared.input_payload["command_relpath"])
            fresh = bindings.bind_prepared(fresh)
            if (fresh is None or fresh.input_fingerprint != prepared.input_fingerprint
                    or bindings.contract.fingerprint(prepared.input_payload) != prepared.input_fingerprint):
                raise ValueError("self/cross q0 inputs changed during execution")
            record = {"workflow": outer.WORKFLOW, "checkpoint_schema_version": outer.CHECKPOINT_SCHEMA_VERSION,
                "execution_engine_version": outer.EXECUTION_ENGINE_VERSION, "unit_id": prepared.unit_id,
                "kind": prepared.kind, "status": "success", "input_fingerprint": prepared.input_fingerprint,
                "input_payload": prepared.input_payload, "outputs": outputs}
            bindings.contract.atomic_write_json(prepared.path, record)
            return prepared.path
    return SelfCheckpoints
