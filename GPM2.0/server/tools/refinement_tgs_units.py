"""Pinned TGS build-4 native minimap2/Racon command recovery.

The original shell loops, candidate selection and integration still execute.
Only sealed command streams are replayed; native done tags are never restored.
"""
from __future__ import annotations

import os
import hashlib
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time
import uuid

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from workspace_layout import automatic_dir, native_request_root
    from refinement_native_units import owned, file_fact, seal, checked_json, helper_hashes, RECEIPT, REQUEST, SUMMARY, SCHEMA, validate_paf
    from refinement_tools import fingerprint
    from post_lgz_degap import digest, stat_key, atomic_json
    from refinement_path import PathError
    from workspace_migration import sync_directories
except ModuleNotFoundError:
    from .workspace_layout import automatic_dir, native_request_root
    from .refinement_native_units import owned, file_fact, seal, checked_json, helper_hashes, RECEIPT, REQUEST, SUMMARY, SCHEMA, validate_paf
    from .refinement_tools import fingerprint
    from .post_lgz_degap import digest, stat_key, atomic_json
    from .refinement_path import PathError
    from .workspace_migration import sync_directories

SOURCE_SHA = "456eda7c039cf602204796c6e5a86739127bcb414dafe589994636c663ececf8"
PATCH_ID = "cgat.tgs.native-command-units.v1"
OWNER = "native_owner.json"


def option(command, name, default=None):
    if command.count(name) > 1:
        raise PathError("duplicate TGS native argument " + name)
    return command[command.index(name)+1] if name in command else default


def phases(command):
    if "--ne" in command:
        return [("minimap2", "fill.paf")]
    if "--racon" not in command or "--pilon" in command:
        raise PathError("TGS recovery supports the pinned native Racon recipe")
    chunks, rounds = int(option(command, "--chunk", "3")), int(option(command, "--r_round", "1"))
    if min(chunks, rounds) < 1:
        raise PathError("invalid TGS native chunk/round count")
    return [("minimap2", "sub.paf")] + [row for r in range(rounds) for i in range(chunks)
            for row in (("minimap2", f"{r}.{i}.paf"), ("racon", f"ont.{r}.{i}.racon.fasta"))] + [("minimap2", "fill.paf")]


def generated_files(request):
    jobs = Path(request["jobs"])
    python, source = request["python"], Path(request["command"][1])
    module = str(Path(__file__).resolve())
    files = {}
    for kind in ("minimap2", "racon"):
        words = [python,"-I","-B",module,"--request",str(jobs/REQUEST),"--program",kind,"--"]
        files["native_commands/"+kind] = ("#!/bin/sh\nexec "+shlex.join(words)+' "$@"\n').encode()
    payload = source.read_bytes()
    if digest(source) != SOURCE_SHA:
        raise PathError("TGS driver differs from pinned bioconda build 4")
    old = b"HOOM_DIR=`dirname $0`"
    anchor = b'print_info "Checking basic args & env end."'
    if payload.count(old) != 1 or payload.count(anchor) != 1:
        raise PathError("TGS instrumentation boundaries changed")
    payload = payload.replace(old, ("HOOM_DIR="+shlex.quote(str(source.parent))).encode())
    overrides = "\nMiniMap2="+shlex.quote(str(jobs/"native_commands/minimap2"))+"\nRACON="+shlex.quote(str(jobs/"native_commands/racon"))+"\n"
    files["native_driver.sh"] = payload.replace(anchor, anchor+overrides.encode())
    return files


def launch(root, invocation, paths, record, native_binding):
    jobs = paths["02_jobs"]
    phases(invocation.command)
    if "--ne" not in invocation.command and option(invocation.command,"--racon") != str(Path(invocation.command[1]).parent/"racon"):
        raise PathError("TGS native correction must use its verified managed Racon")
    snapshots = {}
    for role, sha in native_binding["native_inputs"].items():
        path = role
        for name in ("01_inputs","02_jobs","03_native"):
            if role == "@"+name or role.startswith("@"+name+"/"):
                path = str(paths[name])+role[len(name)+1:]
                break
        path = Path(path).resolve()
        snapshots[str(path)] = {"sha256":sha,"identity":list(stat_key(path))}
    helpers = helper_hashes("tgsgapcloser")
    request = {"schema":"cgat.native-refinement-launch","schema_version":1,"root":str(root),"tool":"tgsgapcloser",
               "run_id":record["run_id"],"command":list(invocation.command),"cwd":str(invocation.cwd),"jobs":str(jobs),
               "python":str(Path(invocation.command[1]).parent/"python"),"input_snapshots":snapshots,
               "helpers":helpers,"source_sha256":SOURCE_SHA,"driver_patch":PATCH_ID,
               "session":{"native_binding":native_binding,"threads":record["threads"],"helpers":helpers}}
    files = generated_files(request)
    request["driver_files"] = {name:hashlib.sha256(payload).hexdigest() for name,payload in files.items()}
    for name,payload in files.items():
        path = owned(root,jobs/name); path.parent.mkdir(parents=True,exist_ok=True)
        with path.open("xb") as stream:
            stream.write(payload)
        path.chmod(0o755)
    request["driver_command"] = [invocation.command[0],str(jobs/"native_driver.sh"),*invocation.command[2:]]
    seal(jobs/REQUEST,request)
    return (request["python"],"-I","-B",str(Path(__file__).resolve()),"--request",str(jobs/REQUEST)), jobs/REQUEST


def stream_file(kind, name):
    return "stderr.log" if name == "stderr" else "stdout.paf" if kind == "minimap2" else "stdout.fasta"


def process_identity(pid):
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")",1)[1].split()
    if fields[0] == "Z":
        raise PathError("TGS native owner is no longer live")
    return fields[19]


class TgsUnits:
    def __init__(self, request, *, create=False):
        self.request, self.root = request, Path(request["root"]).resolve()
        self.run_id = request["run_id"]
        if not re.fullmatch(r"[0-9a-f]{32}",self.run_id):
            raise PathError("invalid TGS unit owner")
        self.jobs = owned(self.root,automatic_dir(self.root, 'tgsgapcloser') / "02_jobs"/self.run_id)
        self.native = owned(self.root,automatic_dir(self.root, 'tgsgapcloser') / "03_native"/self.run_id)
        self.directory = owned(self.root,self.jobs/"native_units")
        if create:
            self.directory.mkdir(exist_ok=False)
            self.write_summary(None)

    def write_summary(self, code):
        units = []
        for receipt in self.directory.glob("*/"+RECEIPT):
            if re.fullmatch(r"[0-9a-f]{64}",receipt.parent.name):
                value = checked_json(self.root,receipt)
                units.append({"key":value["key"],"receipt":receipt.relative_to(self.root).as_posix(),"receipt_sha256":digest(receipt),
                              "unit":value["binding"]["unit"],"result":value["result"],"origin":value["origin"],
                              "reused":value["origin"] is not None})
        order = [(kind,Path(option(self.request["command"],"--output")).name+"."+name) for kind,name in phases(self.request["command"])]
        units.sort(key=lambda row:order.index((row["unit"]["program"],row["unit"]["stdout"])))
        value = {"schema":"cgat.native-refinement-substeps","schema_version":1,"tool":"tgsgapcloser","run_id":self.run_id,
                 "session":self.request["session"],"native_command":self.request["command"],"units":units,
                 "native_returncode":code,"status":"running" if code is None else "finished"}
        atomic_json(self.jobs/SUMMARY,{**value,"payload_sha256":fingerprint(value)})

    def live_owner(self):
        owner = checked_json(self.root,self.jobs/OWNER)
        if (owner.get("status") != "running" or owner.get("run_id") != self.run_id
                or owner.get("request_sha256") != digest(self.jobs/REQUEST) or owner.get("start") != process_identity(owner["pid"])):
            raise PathError("TGS command lost its live attempt input snapshot")

    def input_fact(self, value):
        path = Path(value).absolute()
        if path.is_symlink() and not path.resolve().is_relative_to(self.native):
            raise PathError("TGS generated input alias leaves the native attempt")
        path = path.resolve()
        saved = self.request["input_snapshots"].get(str(path))
        if saved is not None:
            identity = stat_key(path)
            if list(identity) != saved["identity"]:
                raise PathError("TGS live outer input snapshot changed")
            return path,{"sha256":saved["sha256"],"bytes":identity[2]},identity
        fact,identity = file_fact(path)
        return path,fact,identity

    def find(self, key, binding):
        for receipt in sorted(self.jobs.parent.glob("*/native_units/"+key+"/"+RECEIPT)):
            try:
                owner = receipt.parents[2].name
                if owner == self.run_id or not re.fullmatch(r"[0-9a-f]{32}",owner):
                    continue
                value = checked_json(self.root,receipt)
                if (value.get("schema") != SCHEMA or value.get("schema_version") != 1 or value.get("status") != "completed"
                        or value.get("tool") != "tgsgapcloser" or value.get("run_id") != owner or value.get("key") != key
                        or value.get("binding") != binding or value.get("origin") is not None or value.get("execution",{}).get("computed") is not True):
                    continue
                validate_bundle(self.root,receipt,value)
                return receipt,value
            except (OSError,ValueError,KeyError,TypeError,AttributeError):
                continue
        return None

    def run(self, kind, argv):
        self.live_owner()
        streams = {}
        for fd,name in ((1,"stdout"),(2,"stderr")):
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise PathError("TGS command streams must target owned native files")
            path = owned(self.root,Path(os.readlink(f"/proc/self/fd/{fd}")))
            if path.parent != self.native or os.fstat(fd).st_size or os.lseek(fd,0,os.SEEK_CUR):
                raise PathError("TGS command output is not a fresh native stream")
            streams[name] = path
        prefix = Path(option(self.request["command"],"--output")).name
        stage = (kind,streams["stdout"].name)
        if stage not in [(k,prefix+"."+suffix) for k,suffix in phases(self.request["command"])]:
            raise PathError("unexpected TGS native command phase")
        expected_threads = str(self.request["session"]["threads"])
        if argv.count("-t") != 1 or option(argv,"-t") != expected_threads:
            raise PathError("TGS command changed the native thread budget")
        real = Path(self.request["command"][1]).parent/kind
        count = 2 if kind == "minimap2" else 3
        if len(argv) < count:
            raise PathError("TGS command lacks its native input files")
        facts,identities = {},{}
        for number,value in enumerate(argv[-count:]):
            path,fact,identity = self.input_fact(value)
            facts[str(number)],identities[path] = fact,identity
        program_fact,program_identity = file_fact(real)
        identities[real] = program_identity
        normalized = []
        for value in argv:
            for path,role in ((self.native,"@native"),(automatic_dir(self.root, 'tgsgapcloser') / "01_inputs"/self.run_id,"@inputs")):
                if value == str(path) or value.startswith(str(path)+"/"):
                    value = role+value[len(str(path)):]; break
            normalized.append(value)
        unit = {"kind":"tgs.command","program":kind,"argv":normalized,"binary":str(real),
                "binary_sha256":program_fact["sha256"],"stdout":streams["stdout"].name,"stderr":streams["stderr"].name}
        binding = {"session":self.request["session"],"unit":unit,"inputs":facts}
        key = fingerprint(binding)
        temporary = self.directory/("incomplete-"+key+"-"+uuid.uuid4().hex); temporary.mkdir()
        seal(temporary/"attempt.json",{"binding":binding,"event":"native_command_started"})
        cached,origin,started = self.find(key,binding),None,time.monotonic()
        if cached is None:
            process = subprocess.run([str(real),*argv])
            if process.returncode:
                seal(temporary/"failure.json",{"returncode":process.returncode,"command":[str(real),*argv]})
                return process.returncode
        else:
            receipt,producer = cached
            shutil.copyfile(receipt,temporary/"producer.json")
            if checked_json(self.root,temporary/"producer.json") != producer:
                raise PathError("TGS unit producer changed while restoring")
            for fd,name in ((1,"stdout"),(2,"stderr")):
                with (receipt.parent/stream_file(kind,name)).open("rb") as source, os.fdopen(os.dup(fd),"wb") as destination:
                    shutil.copyfileobj(source,destination)
            origin = {"run_id":producer["run_id"],"receipt":receipt.relative_to(self.root).as_posix(),
                      "receipt_sha256":digest(temporary/"producer.json")}
        self.live_owner()
        if any(stat_key(path) != identity for path,identity in identities.items()):
            raise PathError("TGS native command consumed a changing input")
        result = persisted_stream_result(kind, streams["stdout"])
        artifacts = {}
        for name in ("stdout", "stderr"):
            fact,before = file_fact(streams[name])
            if cached is not None and fact["sha256"] != producer["artifacts"][stream_file(kind,name)]:
                raise PathError("TGS replayed stream differs from original producer")
            try:
                os.link(streams[name],temporary/stream_file(kind,name))
            except OSError:
                shutil.copyfile(streams[name],temporary/stream_file(kind,name))
            if digest(temporary/stream_file(kind,name)) != fact["sha256"] or stat_key(streams[name])[:4] != before[:4]:
                raise PathError("TGS command stream changed while sealing")
            artifacts[stream_file(kind,name)] = fact["sha256"]
        if origin:
            artifacts["producer.json"] = origin["receipt_sha256"]
        value = {"schema":SCHEMA,"schema_version":1,"status":"completed","tool":"tgsgapcloser","run_id":self.run_id,
                 "key":key,"binding":binding,"origin":origin,"artifacts":artifacts,"result":result,
                 "execution":{"computed":origin is None,"returncode":0,"seconds":time.monotonic()-started}}
        validate_bundle(self.root,temporary/RECEIPT,value,receipt_required=False)
        seal(temporary/RECEIPT,value)
        final = self.directory/key
        if final.exists() or final.is_symlink():
            raise PathError("TGS command phase executed twice")
        os.rename(temporary,final); sync_directories(self.directory)
        return 0


def persisted_stream_result(kind, path):
    # The child has exited, but a parallel filesystem can still have pending
    # stream metadata. Flush inherited output descriptors before the first
    # read/identity check, not after parsing or hashing the redirected files.
    for fd in (1, 2):
        os.fsync(fd)
    return stream_result(kind, path)


def stream_result(kind, path):
    if kind == "minimap2":
        return validate_paf(path,allow_empty=True,require_cigar=False)
    if kind != "racon":
        raise PathError("unsupported TGS native command")
    if path.stat().st_size == 0:
        return {"outcome":"empty_correction","records":{}}
    try:
        from refinement_native_checkpoint import fasta_facts
    except ModuleNotFoundError:
        from .refinement_native_checkpoint import fasta_facts
    _,records,_ = fasta_facts(path,None)
    return {"outcome":"corrected_fasta","records":records}


def validate_bundle(root, receipt, value, *, receipt_required=True):
    kind = value["binding"]["unit"]["program"]
    expected = {stream_file(kind,name) for name in ("stdout","stderr")} | ({"producer.json"} if value["origin"] else set())
    if set(value["artifacts"]) != expected or value["execution"].get("returncode") != 0:
        raise PathError("TGS command output inventory/exit proof is incomplete")
    files = []
    for name,sha in value["artifacts"].items():
        path = owned(root,receipt.parent/name)
        if digest(path) != sha:
            raise PathError("TGS unit artifact changed")
        files.append(path)
    if stream_result(value["binding"]["unit"]["program"],receipt.parent/stream_file(kind,"stdout")) != value["result"]:
        raise PathError("TGS stream does not reproduce the terminal unit")
    if value["origin"]:
        origin = value["origin"]
        producer = checked_json(root,receipt.parent/"producer.json")
        expected_origin = automatic_dir(root, 'tgsgapcloser') / "02_jobs"/origin["run_id"]/"native_units"/value["key"]/RECEIPT
        if (not re.fullmatch(r"[0-9a-f]{32}",origin["run_id"]) or origin["receipt"] != expected_origin.relative_to(root).as_posix()
                or origin["receipt_sha256"] != value["artifacts"]["producer.json"]
                or producer.get("schema") != SCHEMA or producer.get("schema_version") != 1 or producer.get("status") != "completed"
                or producer.get("tool") != "tgsgapcloser" or producer.get("run_id") != origin["run_id"]
                or producer.get("key") != value["key"] or producer.get("binding") != value["binding"]
                or producer.get("result") != value["result"] or producer.get("origin") is not None
                or producer.get("execution",{}).get("computed") is not True or producer["execution"].get("returncode") != 0
                or producer.get("artifacts") != {k:v for k,v in value["artifacts"].items() if k != "producer.json"}):
            raise PathError("TGS original producer is not the completed command")
    return files+([receipt] if receipt_required else [])


def capture_units(root, run_id, code, *, required=False):
    jobs = automatic_dir(root, 'tgsgapcloser') / "02_jobs"/run_id
    if not (jobs/SUMMARY).exists() and not required:
        return []
    summary,request = checked_json(root,jobs/SUMMARY),checked_json(root,jobs/REQUEST)
    if (summary.get("schema") != "cgat.native-refinement-substeps" or summary.get("schema_version") != 1
            or summary.get("status") != "finished" or summary.get("tool") != "tgsgapcloser" or summary.get("run_id") != run_id
            or type(summary.get("native_returncode")) is not int or summary["native_returncode"] != code
            or summary["session"] != request["session"] or summary["native_command"] != request["command"]
            or request.get("tool") != "tgsgapcloser" or request.get("run_id") != run_id or request.get("source_sha256") != SOURCE_SHA):
        raise PathError("TGS native command summary does not close its producer")
    files = [jobs/SUMMARY,jobs/REQUEST,jobs/OWNER]
    owner = checked_json(root,jobs/OWNER)
    if owner.get("status") != "finished" or owner.get("run_id") != run_id or owner.get("returncode") != code or owner.get("request_sha256") != digest(jobs/REQUEST):
        raise PathError("TGS native owner did not finish")
    if set(request["driver_files"]) != {"native_driver.sh","native_commands/minimap2","native_commands/racon"}:
        raise PathError("TGS driver inventory is incomplete")
    for name,sha in request["driver_files"].items():
        if name not in {"native_driver.sh","native_commands/minimap2","native_commands/racon"}:
            raise PathError("TGS driver inventory has an unknown file")
        path = owned(root,jobs/name)
        if digest(path) != sha:
            raise PathError("TGS owned driver/wrapper changed")
        files.append(path)
    wanted = [(kind,Path(option(request["command"],"--output")).name+"."+suffix) for kind,suffix in phases(request["command"])]
    seen = []
    for row in summary["units"]:
        key = row["key"]
        if not re.fullmatch(r"[0-9a-f]{64}",key) or key in seen:
            raise PathError("TGS unit key is invalid/duplicated")
        seen.append(key)
        receipt = owned(root,jobs/"native_units"/key/RECEIPT)
        value = checked_json(root,receipt)
        if (value.get("schema") != SCHEMA or value.get("schema_version") != 1 or value.get("status") != "completed"
                or value.get("tool") != "tgsgapcloser" or value.get("run_id") != run_id or value.get("key") != key
                or row["receipt"] != receipt.relative_to(root).as_posix() or row["receipt_sha256"] != digest(receipt)
                or fingerprint(value["binding"]) != key or value["binding"]["session"] != request["session"]
                or row["unit"] != value["binding"]["unit"] or row["result"] != value["result"] or row["origin"] != value["origin"]
                or type(row["reused"]) is not bool or row["reused"] != bool(value["origin"])
                or value["execution"]["computed"] is not (not row["reused"])):
            raise PathError("TGS native command closure changed")
        if row["unit"].get("kind") != "tgs.command":
            raise PathError("TGS unit has an unknown consumer")
        files += validate_bundle(root,receipt,value)
    actual = [(row["unit"]["program"],row["unit"]["stdout"]) for row in summary["units"]]
    if actual != wanted:
        raise PathError("TGS native units do not cover every expected alignment/correction phase")
    return list(dict.fromkeys(files))


def main():
    args = sys.argv[1:]
    if len(args) < 2 or args[0] != "--request":
        raise PathError("TGS wrapper requires its sealed request")
    request_path = Path(args[1]).absolute(); root = native_request_root(request_path)
    request = checked_json(root,request_path)
    if (request.get("schema") != "cgat.native-refinement-launch" or request.get("tool") != "tgsgapcloser"
            or request.get("run_id") != request_path.parent.name or request.get("root") != str(root)
            or request.get("helpers") != helper_hashes("tgsgapcloser") or request["session"]["helpers"] != request["helpers"]
            or request.get("jobs") != str(request_path.parent) or request.get("cwd") != str(Path.cwd())
            or request_path != automatic_dir(root, 'tgsgapcloser') / "02_jobs"/request["run_id"]/REQUEST):
        raise PathError("TGS native launcher does not match its owned attempt")
    if len(args) > 2:
        if len(args) < 5 or args[2] != "--program" or args[3] not in {"minimap2","racon"} or args[4] != "--":
            raise PathError("unsupported TGS wrapper command")
        return TgsUnits(request).run(args[3],args[5:])
    store = TgsUnits(request,create=True)
    for name,payload in generated_files(request).items():
        path = owned(root,store.jobs/name)
        if path.read_bytes() != payload:
            raise PathError("TGS materialized driver is not the declared source-only instrumentation")
    if list(store.native.glob("done_*tag")):
        raise PathError("TGS fresh attempt already has unsealed native done tags")
    owner = {"schema":"cgat.native-command-owner","run_id":store.run_id,"pid":os.getpid(),"start":process_identity(os.getpid()),
             "request_sha256":digest(request_path),"status":"running"}
    seal(store.jobs/OWNER,owner)
    code = 1
    try:
        code = subprocess.run(request["driver_command"]).returncode
    finally:
        seal(store.jobs/OWNER,{**owner,"status":"finished","returncode":code})
        store.write_summary(code)
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print("CGAT TGS recovery error: "+str(error),file=sys.stderr)
        sys.exit(2)
