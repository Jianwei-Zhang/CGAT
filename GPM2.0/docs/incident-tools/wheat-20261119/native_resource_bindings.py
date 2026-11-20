"""Explicit resource-only wrapper around authentic scientific SelfBindings.

Completed native batches stay on the original verified reuse path. Only pending
eligible commands are replaced, and callbacks are restored to the original task
objects before the scientific layer merges/commits. Readers use the same receipt
validation. This module is not an installed context or a production cutover.
"""
import dataclasses
import json
from pathlib import Path
import shlex

import native_batch_guard as guard


def wrapper_text(adapter, spec):
    return "#!/bin/bash\nset -euo pipefail\nexec python3 -B " + shlex.quote(str(adapter)) + " --spec " + shlex.quote(str(spec)) + "\n"


def eligible(profile):
    m = profile.native
    if not 0 < sum(m["target_lengths"].values()) <= guard.POLICY["maximum_target_bases"]:
        return set()
    return {str(i) for i,b in enumerate(m["batches"])
            if i not in profile.selected and b["entries"]
            and all(type(e["length"]) is int and e["length"] > 0 for e in b["entries"])
            and sum(e["length"] for e in b["entries"]) <= guard.POLICY["maximum_query_bases"]}


class NativeBindings:
    def __init__(self, original):
        self.original = original
        self._specs = {}
        self.native_tasks = {}
        self.verify_native_resources()
        for rel, row in self.rows.items():
            for key in row["native_scripts"]:
                i = int(key)
                command = Path(self.profiles[rel].native["batches"][i]["directory"]) / "command.sh"
                if command in self.native_tasks:
                    raise ValueError("duplicate native resource command")
                self.native_tasks[command] = (rel, i)

    def __getattr__(self, name):
        return getattr(self.original, name)

    def record(self, path):
        path = Path(path)
        return {"path":str(path), "sha256":self.contract.sha256_file(path)}

    def expected_spec(self, rel, i):
        profile = self.profiles[rel]; m = profile.native; row = self.rows[rel]
        command = Path(m["batches"][i]["directory"]) / "command.sh"
        return {"schema":guard.SCHEMA,"policy":guard.POLICY,
                "manifest":self.record(profile.source),"batch_index":i,
                "native_key":m["batches"][i]["key"],
                "native_command":{"path":str(command),"sha256":row["native_commands"][str(i)]["sha256"]},
                "runtime":{**self.plan["native_runtime"],"adapter":self.plan["dependencies"]["native_guard"],
                           "restore":self.record(m["restore"])}}

    def checked(self, record, *, isolated=False):
        path = Path(record["path"])
        if (not path.is_absolute() or path.is_symlink() or not path.is_file()
                or self.contract.sha256_file(path) != record["sha256"]
                or (isolated and path.resolve().is_relative_to(self.work))):
            raise ValueError("changed or unsafe native resource artifact: " + str(path))
        return path

    def verify_native_resources(self, *, operations=None):
        for role, source in (("native_support", __file__), ("native_guard", guard.__file__)):
            if self.checked(self.plan["dependencies"][role]).resolve() != Path(source).resolve():
                raise ValueError("native resource module is not bound: " + role)
        runtime = self.plan["native_runtime"]
        if set(runtime) != {"helper", "diagnostics", "mapper"}:
            raise ValueError("native runtime inventory differs")
        for role, filename in (("helper","self_alignment_batches.py"),
                               ("diagnostics","minimap2_diagnostics.py")):
            if self.checked(runtime[role]).resolve() != (self.work/".prepare_lib/tools"/filename).resolve():
                raise ValueError("native resource helper is not the frozen workspace helper")
        self.checked(runtime["mapper"])
        paths = set()
        for rel in (self.rows if operations is None else operations):
            row = self.rows[rel]; profile = self.profiles[rel]
            if runtime["mapper"]["sha256"] != profile.native["identities"]["tool"]:
                raise ValueError("native resource mapper differs from the scientific manifest")
            keys = eligible(profile)
            if set(row.get("native_scripts",{})) != keys or set(row.get("native_specs",{})) != keys:
                raise ValueError("native resource inventory differs from eligible native batches")
            for key in sorted(keys, key=int):
                script = self.checked(row["native_scripts"][key], isolated=True)
                spec_path = self.checked(row["native_specs"][key], isolated=True)
                if script in paths or spec_path in paths or script == spec_path:
                    raise ValueError("duplicate native wrapper or specification")
                paths.update((script,spec_path))
                token = (str(spec_path), row["native_specs"][key]["sha256"])
                if token not in self._specs:
                    self._specs[token] = json.loads(spec_path.read_text())
                spec = self._specs[token]
                if spec != self.expected_spec(rel,int(key)):
                    raise ValueError("native resource spec changes source, key, tool or parameters")
                if script.read_text() != wrapper_text(spec["runtime"]["adapter"]["path"],spec_path):
                    raise ValueError("native wrapper is not the canonical guarded invocation")

    def verify(self, *, full=False, operations=None):
        self.original.verify(full=full, operations=operations)
        self.verify_native_resources(operations=operations)

    def bind_prepared(self, prepared):
        if prepared is not None:
            self.verify_native_resources(operations=self.operations_for(prepared.unit_id))
        return self.original.bind_prepared(prepared)

    def receipt(self, rel, i, *, required=False, threads=None):
        profile = self.profiles[rel]; b = profile.native["batches"][i]
        path = Path(b["directory"]) / guard.RECEIPT
        if not path.exists():
            if required: raise ValueError("new guarded native execution has no resource receipt")
            return None  # Verified historical cache, never claimed as guarded.
        self.verify_native_resources(operations=[rel])
        spec = self.expected_spec(rel,i)
        marker_path = path.parent / "complete.json"
        info = json.loads(path.read_text()); marker = json.loads(marker_path.read_text())
        grant = info.get("thread_grant")
        children = info.get("children",[])
        mapping = {"kind":"mapping","as_limit_bytes":guard.POLICY["mapper_as_bytes"],"returncode":0}
        restore = {"kind":"restore","as_limit_bytes":guard.POLICY["restore_as_bytes"],"returncode":0}
        index = {"kind":"index","as_limit_bytes":guard.POLICY["mapper_as_bytes"],"returncode":0}
        if (info.get("schema") != guard.SCHEMA or info.get("status") != "complete"
                or info.get("native_key") != b["key"] or marker.get("key") != b["key"]
                or info.get("policy") != guard.POLICY or info.get("runtime") != spec["runtime"]
                or info.get("manifest") != spec["manifest"]
                or info.get("spec_sha256") != self.rows[rel]["native_specs"][str(i)]["sha256"]
                or info.get("complete_marker_sha256") != self.contract.sha256_file(marker_path)
                or info.get("outputs") != marker.get("outputs")
                or info.get("scientific_parameters_changed") is not False
                or type(grant) is not int or not 1 <= grant <= guard.POLICY["maximum_threads"]
                or (threads is not None and grant != threads)
                or children not in ([mapping,restore],[index,mapping,restore])
                or not profile.validate_batch(i)):
            raise ValueError("native resource receipt differs from verified execution/output")
        return path

    def output_identities(self, unit_id):
        result = self.original.output_identities(unit_id)
        for rel in self.operations_for(unit_id):
            for key in self.rows[rel]["native_scripts"]:
                path = self.receipt(rel,int(key))
                if path is not None:
                    result.append(self.contract.file_identity(path, relative_to=self.work))
        return result

    def dispatch(self, original_runner):
        def guarded(tasks, budget, children, cancel_signal, on_start, on_line, on_finish,
                    environment, *, dispatch=None):
            mapped = []; originals = {}; owned = {}; grants = {}
            for task in tasks:
                pair = self.native_tasks.get(task.command)
                replacement = task
                if pair is not None:
                    rel,i = pair
                    replacement = dataclasses.replace(task,command=Path(self.rows[rel]["native_scripts"][str(i)]["path"]))
                    owned[id(replacement)] = pair
                mapped.append(replacement); originals[id(replacement)] = task
            def start(task, threads):
                native = originals[id(task)]
                if id(task) in owned:
                    rel,i=owned[id(task)]
                    self.verify_native_resources(operations=[rel])
                    if not 1 <= threads <= guard.POLICY["maximum_threads"]:
                        raise ValueError("invalid native resource thread grant")
                    grants[id(task)] = threads
                on_start(native,threads)
                if task is not native:
                    on_line(native,"NATIVE_RESOURCE_OVERRIDE native="+str(native.command)+" executed="+str(task.command))
            def finish(task, code, cancelling):
                if id(task) in owned and code == 0 and not cancelling:
                    rel,i=owned[id(task)]
                    if id(task) not in grants: raise ValueError("native resource task finished without start")
                    self.receipt(rel,i,required=True,threads=grants[id(task)])
                return on_finish(originals[id(task)],code,cancelling)
            return original_runner(mapped,budget,children,cancel_signal,start,
                lambda task,line:on_line(originals[id(task)],line),finish,environment,dispatch=dispatch)
        scientific = self.original.dispatch(guarded)
        def run(*args, **kwargs):
            self.verify_native_resources()
            return scientific(*args, **kwargs)
        return run
