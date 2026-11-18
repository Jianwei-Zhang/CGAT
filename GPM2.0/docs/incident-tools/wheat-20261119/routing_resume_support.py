"""Incident-only explicit q0 execution overrides; no native command rewriting.

The caller must hold the existing workspace lock. Completed native leaves are
excluded from the fixed routing plan. Both leaf and outer checkpoints bind
actual routed scripts and dependencies; ordinary reference/assignment inputs
and their checkpoints remain unchanged. Not wired into the default runner.
"""
from __future__ import annotations
import dataclasses
import json
from pathlib import Path


class OverrideError(RuntimeError):
    pass


class RoutingBindings:
    def __init__(self, work, plan_path, contract):
        self.work = Path(work).resolve(strict=True)
        self.path = Path(plan_path).resolve(strict=True)
        self.contract = contract
        self.plan_hash = contract.sha256_file(self.path)
        self.plan = json.loads(self.path.read_text())
        if (self.plan.get("schema") != "incident_q0_routing_v1"
                or self.plan.get("workspace") != str(self.work)):
            raise OverrideError("routing plan belongs to another workspace or schema")
        self.rows = {}
        for row in self.plan["overrides"]:
            rel = row["native_command"]
            path = self.work / rel
            parts = Path(rel).parts
            if (len(parts) != 4 or parts[0] != "runs" or not parts[1].startswith("chr_")
                    or parts[3] != "command.sh" or "_vs_" not in parts[2]
                    or parts[2].endswith("_vs_self") or ".." in parts
                    or path.is_symlink() or not path.resolve().is_relative_to(self.work)
                    or row["unit_id"] != "q0_chr:" + parts[1][4:] or rel in self.rows):
                raise OverrideError("only unique q0 cross leaves may be overridden")
            script = Path(row["script"]["path"])
            if not script.is_absolute() or script.is_symlink() or script.resolve().is_relative_to(self.work):
                raise OverrideError("override script must be isolated outside the workspace")
            receipt = Path(row["receipt"])
            if receipt != path.parent / "routing-receipt.json":
                raise OverrideError("unexpected routed leaf receipt path")
            self.rows[rel] = row
        if not self.rows:
            raise OverrideError("empty routing override plan")
        self.verify()

    def verify(self):
        if self.contract.sha256_file(self.path) != self.plan_hash:
            raise OverrideError("routing plan changed")
        for row in self.rows.values():
            if self.contract.sha256_file(self.work / row["native_command"]) != row["native_command_sha256"]:
                raise OverrideError("original command changed")
            if self.contract.file_identity(Path(row["script"]["path"])) != row["script"]:
                raise OverrideError("execution override changed")
        for row in self.plan["dependencies"].values():
            if self.contract.sha256_file(Path(row["path"])) != row["sha256"]:
                raise OverrideError("execution dependency changed")

    def relative(self, task):
        try:
            return task.command.relative_to(self.work).as_posix()
        except ValueError:
            return None

    def proof(self, rel):
        self.verify()
        return {"schema": self.plan["schema"], "override": self.rows[rel],
                "dependencies": self.plan["dependencies"], "policy": self.plan["policy"],
                "preset": self.plan["preset"]}

    def bind_inputs(self, task, original):
        rel = self.relative(task)
        if rel not in self.rows:
            return original
        if task.unit_id != self.rows[rel]["unit_id"]:
            raise OverrideError("routed task has a different execution unit")
        return {**original, "execution_override": self.proof(rel)}

    def bind_prepared(self, prepared):
        if prepared is None:
            return None
        rows = [rel for rel, row in self.rows.items() if row["unit_id"] == prepared.unit_id]
        if not rows:
            return prepared
        if prepared.kind != "q0_chromosome_alignments":
            raise OverrideError("routing cannot change reference, assignment or self-only checkpoints")
        payload = {**prepared.input_payload,
                   "incident_execution_overrides": [self.proof(rel) for rel in sorted(rows)]}
        return dataclasses.replace(prepared, input_payload=payload,
                                   input_fingerprint=self.contract.fingerprint(payload))

    def receipt_identity(self, task, inputs):
        rel = self.relative(task)
        if rel not in self.rows:
            return None
        self.verify()
        row = self.rows[rel]
        path = Path(row["receipt"])
        if path.is_symlink():
            raise OverrideError("linked routed receipt")
        receipt = json.loads(path.read_text())
        files = inputs["files"]
        deps = {k: v["sha256"] for k, v in self.plan["dependencies"].items()
                if k in self.plan["router_dependency_names"]}
        expected = {"status": "complete", "scope": "q0_cross_only", "whole_records_preserved": True,
                    "target_sha256": files[1]["sha256"], "query_sha256": files[2]["sha256"],
                    "tool_sha256": inputs["tool"]["sha256"], "preset": self.plan["preset"],
                    "dependencies": deps, "policy": self.plan["policy"],
                    "router_sha256": deps["router"], "metrics_sha256": deps["positions"]}
        if any(receipt.get(k) != v for k, v in expected.items()):
            raise OverrideError("routed receipt does not match the executed request")
        output = task.command.parent / "result.paf"
        self.contract.validate_paf(output, require_cigar=True)
        actual = self.contract.file_identity(output)
        if any(actual[k] != receipt["output"].get(k) for k in ("size", "sha256")):
            raise OverrideError("routed PAF differs from its committed receipt")
        return self.contract.file_identity(path, relative_to=self.work)

    def dispatch(self, original):
        def run(tasks, budget, children, cancel_signal, on_start, on_line, on_finish,
                environment, *, dispatch=None):
            self.verify()
            replacements, originals = [], {}
            for task in tasks:
                rel = self.relative(task)
                if rel in self.rows:
                    if task.unit_id != self.rows[rel]["unit_id"]:
                        raise OverrideError("routed task unit changed")
                    replacement = dataclasses.replace(task, command=Path(self.rows[rel]["script"]["path"]))
                else:
                    replacement = task
                replacements.append(replacement)
                originals[id(replacement)] = task
            def start(task, threads):
                native = originals[id(task)]
                on_start(native, threads)
                if task is not native:
                    on_line(native, "ROUTE_EXECUTION_OVERRIDE native=" + str(native.command)
                            + " executed=" + str(task.command))
            def finish(task, code, cancelling):
                self.verify()
                return on_finish(originals[id(task)], code, cancelling)
            return original(replacements, budget, children, cancel_signal,
                            start,
                            lambda task, line: on_line(originals[id(task)], line), finish,
                            environment, dispatch=dispatch)
        return run


def checkpoint_class(base_class, bindings, native_inputs, assignment):
    """Extend identities without weakening the original end-of-q0 recheck.

The frozen base commit constructs a literal OuterCheckpointManager, so simply
subclassing prepare would always fail its end-of-q0 guard. Reconstruct a fresh
base manager and bind the same explicit override BEFORE comparing fingerprints;
write one atomic success checkpoint only after both output and input checks.
"""
    from types import SimpleNamespace
    import run_outer_checkpoints as outer
    class RoutingCheckpoints(base_class):
        def prepare(self, unit_id, command_relpath):
            return bindings.bind_prepared(super().prepare(unit_id, command_relpath))
        def _output_identities(self, prepared):
            rows = super()._output_identities(prepared)
            for rel, row in bindings.rows.items():
                if row["unit_id"] == prepared.unit_id:
                    task = SimpleNamespace(command=bindings.work / rel, unit_id=row["unit_id"])
                    rows.append(bindings.receipt_identity(task, native_inputs(task, assignment)))
            return rows
        def commit(self, prepared):
            if not any(row["unit_id"] == prepared.unit_id for row in bindings.rows.values()):
                return super().commit(prepared)
            outputs = self._output_identities(prepared)
            fresh = base_class(self.server_dir).prepare(
                prepared.unit_id, prepared.input_payload["command_relpath"])
            fresh = bindings.bind_prepared(fresh)
            if (fresh is None or fresh.input_fingerprint != prepared.input_fingerprint
                    or bindings.contract.fingerprint(prepared.input_payload) != prepared.input_fingerprint):
                raise OverrideError("routed q0 inputs changed during execution")
            checkpoint = {"workflow": outer.WORKFLOW,
                "checkpoint_schema_version": outer.CHECKPOINT_SCHEMA_VERSION,
                "execution_engine_version": outer.EXECUTION_ENGINE_VERSION,
                "unit_id": prepared.unit_id, "kind": prepared.kind, "status": "success",
                "input_fingerprint": prepared.input_fingerprint,
                "input_payload": prepared.input_payload, "outputs": outputs}
            bindings.contract.atomic_write_json(prepared.path, checkpoint)
            return prepared.path
    return RoutingCheckpoints
