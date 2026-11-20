"""Resource-only adapter around the authentic frozen native self-batch helper.

No science flags, batch keys, source manifests or original commands are edited.
The helper soft AS limit is 2 GiB (hard 16 GiB to permit a child raise); its one
synchronous mapper child is limited to 16 GiB, restoration to 2 GiB. The frozen
helper does not change resource limits or spawn concurrent children. Admission
must reserve 18 GiB per lane, plus controller headroom; RLIMIT_AS is not a cgroup.
This module alone does not change dispatcher admission or the active workflow.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys

SCHEMA = "incident_guarded_native_batch_v1"
RECEIPT = "native-resource-receipt.json"
GIB = 1024**3
POLICY = {"helper_soft_as_bytes":2*GIB, "helper_hard_as_bytes":16*GIB,
          "mapper_as_bytes":16*GIB, "restore_as_bytes":2*GIB,
          "reservation_bytes":18*GIB, "maximum_query_bases":20_000_000,
          "maximum_target_bases":1_000_000_000, "maximum_threads":8}


def digest(path):
    path = Path(path); before = path.stat(); h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""): h.update(block)
    after = path.stat()
    signature = lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    if signature(before) != signature(after): raise ValueError("file changed while hashing")
    return h.hexdigest()


def checked(row):
    path = Path(row["path"])
    if not path.is_absolute() or path.is_symlink() or digest(path) != row["sha256"]:
        raise ValueError("unbound or changed native resource input: " + str(path))
    return path


def set_child_limit(limit):
    resource.setrlimit(resource.RLIMIT_CORE, (0,0))
    resource.setrlimit(resource.RLIMIT_AS, (limit,limit))
    if resource.getrlimit(resource.RLIMIT_AS) != (limit,limit):
        raise ValueError("child address-space limit did not take effect")


class ScopedSubprocess:
    """Only replaces the loaded helper module attribute, not global subprocess."""
    CalledProcessError = subprocess.CalledProcessError
    DEVNULL = subprocess.DEVNULL

    def __init__(self, mapper, restore, name_map):
        self.mapper = Path(mapper).resolve()
        self.restore = str(restore); self.name_map = str(name_map)
        self.events = []

    def run(self, command, **kwargs):
        if (not isinstance(command,(list,tuple)) or not command
                or kwargs.get("shell") or "preexec_fn" in kwargs
                or kwargs.get("start_new_session")):
            raise ValueError("unexpected native child execution contract")
        command = [str(x) for x in command]
        if Path(command[0]).resolve() == self.mapper:
            if "-d" in command: kind = "index"
            elif "-c" in command: kind = "mapping"
            else: raise ValueError("unknown mapper invocation")
            limit = POLICY["mapper_as_bytes"]
        elif (Path(command[0]).resolve() == Path(sys.executable).resolve()
              and command[1:] == [self.restore,self.name_map]):
            kind = "restore"; limit = POLICY["restore_as_bytes"]
        else: raise ValueError("unexpected executable in native helper")
        # The standalone helper is single-threaded. Limits are changed only in
        # its forked child; the parent's 2-GiB soft limit remains unchanged.
        result = subprocess.run(command, preexec_fn=lambda:set_child_limit(limit), **kwargs)
        self.events.append({"kind":kind,"as_limit_bytes":limit,"returncode":result.returncode})
        return result


def load(name, path):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def validate_spec(spec):
    if spec.get("schema") != SCHEMA or spec.get("policy") != POLICY:
        raise ValueError("unrecognized native resource contract")
    runtime = spec["runtime"]
    for row in runtime.values(): checked(row)
    if checked(runtime["adapter"]).resolve() != Path(__file__).resolve():
        raise ValueError("native adapter implementation is not bound")
    manifest_path = checked(spec["manifest"])
    m = json.loads(manifest_path.read_text()); i = spec["batch_index"]
    if type(i) is not int or i < 0 or i >= len(m["batches"]):
        raise ValueError("invalid native batch index")
    b = m["batches"][i]
    if (m.get("version") != 1 or b["key"] != spec["native_key"] or not b["entries"]
            or any(type(e["length"]) is not int or e["length"] <= 0 for e in b["entries"])
            or sum(e["length"] for e in b["entries"]) > POLICY["maximum_query_bases"]
            or not m["target_lengths"] or any(v <= 0 for v in m["target_lengths"].values())
            or sum(m["target_lengths"].values()) > POLICY["maximum_target_bases"]):
        raise ValueError("native batch lies outside the measured resource envelope")
    if (str(checked(runtime["restore"])) != m["restore"]
            or runtime["restore"]["sha256"] != m["identities"]["restore"]
            or runtime["mapper"]["sha256"] != m["identities"]["tool"]
            or Path(shutil.which("minimap2") or "").resolve() != Path(runtime["mapper"]["path"]).resolve()):
        raise ValueError("native tool selection changed")
    if "native_command" in spec: checked(spec["native_command"])
    threads = int(os.environ.get("GPM_TASK_THREADS","1"))
    if not 1 <= threads <= POLICY["maximum_threads"]:
        raise ValueError("invalid native thread grant")
    if (Path(b["directory"])/"self-profile-receipt.json").exists():
        raise ValueError("approximate output cannot be executed as native")
    return manifest_path,m,b,threads


def execute(spec_path):
    if not sys.platform.startswith("linux"):
        raise ValueError("Linux resource enforcement is required")
    spec_path = Path(spec_path).resolve(strict=True); before = digest(spec_path)
    spec = json.loads(spec_path.read_text()); mp,m,b,threads = validate_spec(spec)
    runtime = spec["runtime"]
    old = sys.modules.get("minimap2_diagnostics")
    if old is not None and Path(old.__file__).resolve() != checked(runtime["diagnostics"]).resolve():
        raise ValueError("another diagnostics module is already loaded")
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.modules["minimap2_diagnostics"] = load("minimap2_diagnostics",checked(runtime["diagnostics"]))
    helper = load("bound_frozen_native_helper",checked(runtime["helper"]))
    proxy = ScopedSubprocess(runtime["mapper"]["path"],m["restore"],m["name_map"])
    helper.subprocess = proxy
    _soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    if hard != resource.RLIM_INFINITY and hard < POLICY["helper_hard_as_bytes"]:
        raise ValueError("inherited native memory hard limit is too small")
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_AS,(POLICY["helper_soft_as_bytes"],POLICY["helper_hard_as_bytes"]))
    if resource.getrlimit(resource.RLIMIT_AS) != (POLICY["helper_soft_as_bytes"],POLICY["helper_hard_as_bytes"]):
        raise ValueError("helper address-space limits did not take effect")
    print("NATIVE_RESOURCE_LIMIT",json.dumps({"policy":POLICY,"threads":threads,"spec_sha256":before}),flush=True)
    helper.run_batch(mp,spec["batch_index"])
    validate_spec(spec)
    if digest(spec_path) != before: raise ValueError("native resource specification changed")
    complete_path = Path(b["directory"])/"complete.json"
    marker = json.loads(complete_path.read_text())
    if marker.get("key") != b["key"] or set(marker.get("outputs",{})) != {"raw.paf","result.paf","stderr.log"}:
        raise ValueError("native helper did not publish the expected successful batch")
    mappings = [e for e in proxy.events if e["kind"] == "mapping"]
    if not mappings:
        print("NATIVE_RESOURCE_CACHE_ONLY no new mapper receipt",flush=True)
        return None
    if len(mappings) != 1 or any(e["returncode"] != 0 for e in proxy.events):
        raise ValueError("unexpected native execution history")
    receipt = {"schema":SCHEMA,"status":"complete","native_key":b["key"],
               "spec_sha256":before,"manifest":spec["manifest"],"runtime":runtime,"policy":POLICY,
               "thread_grant":threads,"children":proxy.events,"complete_marker_sha256":digest(complete_path),
               "outputs":marker["outputs"],"scientific_parameters_changed":False,
               "helper_maxrss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    target = Path(b["directory"])/RECEIPT
    temporary = target.with_name(target.name+".tmp-"+str(os.getpid()))
    try:
        with temporary.open("x") as f:
            json.dump(receipt,f,indent=2); f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.link(temporary,target)  # Never overwrite a prior resource receipt.
    finally:
        temporary.unlink(missing_ok=True)
    print("NATIVE_RESOURCE_COMMITTED",json.dumps({"receipt":str(target),"native_key":b["key"]}),flush=True)
    return receipt


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--spec",type=Path,required=True)
    execute(p.parse_args().spec)
