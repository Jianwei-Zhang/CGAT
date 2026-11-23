"""LR iteration-processing checkpoints around the pinned native shell blocks.

Preprocessing/initial index and native early-stop logic still run fresh. Only
complete iteration FASTA/info outputs are restored; no orphan tree is adopted.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid

if __name__ == "__main__":
    sys.path.insert(0,str(Path(__file__).resolve().parent))
try:
    from workspace_layout import automatic_dir, native_request_root
    from refinement_native_units import owned,file_fact,seal,checked_json,helper_hashes,RECEIPT,REQUEST,SUMMARY,SCHEMA
    from refinement_tools import fingerprint
    from post_lgz_degap import digest,stat_key,atomic_json
    from refinement_path import PathError
    from workspace_migration import sync_directories
except ModuleNotFoundError:
    from .workspace_layout import automatic_dir, native_request_root
    from .refinement_native_units import owned,file_fact,seal,checked_json,helper_hashes,RECEIPT,REQUEST,SUMMARY,SCHEMA
    from .refinement_tools import fingerprint
    from .post_lgz_degap import digest,stat_key,atomic_json
    from .refinement_path import PathError
    from .workspace_migration import sync_directories

OWNER = "native_owner.json"
SNAPSHOTS = "native_epoch_inputs.json"
PATCH_ID = "cgat.lr.iteration-processing-units.v1"
OUTPUTS = ("gapclosed.fasta","info_filter2")


def option(command,name):
    args = command[5:]  # the earlier bash -o pipefail is not the native -o.
    if args.count(name) != 1:
        raise PathError("LR native argument missing/duplicated: "+name)
    return args[args.index(name)+1]


def process_identity(pid):
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")",1)[1].split()
    if fields[0] == "Z":
        raise PathError("LR native controller is no longer live")
    return fields[19]


def gate(request,iteration,body):
    prefix = shlex.join([request["python"],"-I","-B",str(Path(__file__).resolve()),"--request",str(Path(request["jobs"])/REQUEST)])
    def callback(action):
        return prefix+" --action "+action+" --iteration "+iteration
    return ("cgat_lr_state=0\n"+callback("restore")+" || cgat_lr_state=$?\n"+
            'if [ "$cgat_lr_state" -gt 1 ]; then exit 1; fi\n'+
            'if [ "$cgat_lr_state" -eq 1 ]; then\n'+body+"\n"+callback("commit")+"\nfi\n")


def generated_driver(request):
    source = Path(request["command"][4])
    if digest(source) != request["source_sha256"]:
        raise PathError("LR source differs from its lock-verified discovery patch")
    text = source.read_text()
    first_start = text.index("      for  FILE in $output/tmp/x*")
    first_end = text.index("#### iteration estimate")
    next_start = text.index("  perl $program/find_sequnce_file.pl")
    last = "  perl $program/form_sequence.pl $output/iteration-$j/tmp/info_filter2 $output/LR.fasta $output/iteration-$i/gapclosed.fasta >$output/iteration-$j/gapclosed.fasta\n"
    if text.count(last) != 1:
        raise PathError("LR iteration boundary differs from the pinned driver")
    next_end = text.index(last)+len(last)
    text = text[:next_start]+gate(request,'"$j"',text[next_start:next_end])+text[next_end:]
    text = text[:first_start]+gate(request,"1",text[first_start:first_end])+text[first_end:]
    # Preserve concurrency, but native bare wait must not hide child errors.
    coverage = "perl $program/coverage_calculator.pl $FILE $FILE.coverage &"
    if text.count(coverage) != 2:
        raise PathError("LR background coverage sites differ from their pin")
    text = text.replace(coverage,coverage+'\ncgat_lr_pending+=("$!")')
    finder = "perl $program/gap_finder.pl $contigs >$output/iteration-1/tmp/gap.location & perl"
    if text.count(finder) != 1:
        raise PathError("LR background gap finder differs from its pin")
    text = text.replace(finder,'perl $program/gap_finder.pl $contigs >$output/iteration-1/tmp/gap.location &\ncgat_lr_pending+=("$!")\nperl')
    text,count = re.subn(r"(?m)^(\s*)wait\s*$",r"\1cgat_lr_wait",text)
    if count != 4:
        raise PathError("LR wait boundaries differ from the pinned script")
    helper = ("declare -a cgat_lr_pending=()\n"+
              "cgat_lr_wait() { local p rc=0; for p in \"${cgat_lr_pending[@]}\"; do "+
              'if wait "$p"; then :; else rc=$?; fi; done; cgat_lr_pending=(); return "$rc"; }\n')
    return (text.splitlines(keepends=True)[0]+helper+"".join(text.splitlines(keepends=True)[1:])).encode()


def launch(root,invocation,paths,record,native_binding):
    if list(invocation.command[1:4]) != ["-e","-o","pipefail"]:
        raise PathError("LR recovery requires its pinned fail-fast shell recipe")
    helpers = helper_hashes("lrgapcloser")
    request = {"schema":"cgat.native-refinement-launch","schema_version":1,"tool":"lrgapcloser","root":str(root),
               "run_id":record["run_id"],"jobs":str(paths["02_jobs"]),"cwd":str(invocation.cwd),"command":list(invocation.command),
               "python":str(Path(invocation.environment["CGAT_LR_PROGRAM_DIR"])/"python"),"helpers":helpers,
               "source_sha256":invocation.recipe["driver_patch"]["after_sha256"],"driver_patch":PATCH_ID,
               "session":{"native_binding":native_binding,"threads":record["threads"],"helpers":helpers}}
    names = native_binding.get("chromosome_names")
    if names:
        request["chromosomes"] = sorted(names.values())
    else:
        try:
            from refinement_native_checkpoint import fasta_facts
        except ModuleNotFoundError:
            from .refinement_native_checkpoint import fasta_facts
        request["chromosomes"] = sorted(fasta_facts(Path(option(invocation.command,"-i")),None)[1])
    payload = generated_driver(request)
    driver = paths["02_jobs"]/"native_recovery_driver.sh"
    with driver.open("xb") as stream: stream.write(payload)
    request["driver_sha256"] = hashlib.sha256(payload).hexdigest()
    request["driver_command"] = [*invocation.command[:4],str(driver),*invocation.command[5:]]
    seal(paths["02_jobs"]/REQUEST,request)
    return (request["python"],"-I","-B",str(Path(__file__).resolve()),"--request",str(paths["02_jobs"]/REQUEST)),paths["02_jobs"]/REQUEST


class LrUnits:
    def __init__(self,request,*,create=False):
        self.request,self.root,self.run_id = request,Path(request["root"]).resolve(),request["run_id"]
        if not re.fullmatch(r"[0-9a-f]{32}",self.run_id): raise PathError("invalid LR unit owner")
        self.jobs = owned(self.root,automatic_dir(self.root, 'lrgapcloser') / "02_jobs"/self.run_id)
        self.native = owned(self.root,automatic_dir(self.root, 'lrgapcloser') / "03_native"/self.run_id)
        self.output = owned(self.root,self.native/"output")
        if Path(option(request["command"],"-o")) != self.output:
            raise PathError("LR native output is not the owned fresh attempt")
        self.directory = owned(self.root,self.jobs/"native_units")
        self.pending = owned(self.root,self.jobs/"native_pending")
        if create:
            self.directory.mkdir(exist_ok=False); self.pending.mkdir(exist_ok=False)
            self.write_summary(None)

    def write_summary(self,code):
        rows = []
        for receipt in self.directory.glob("*/"+RECEIPT):
            if re.fullmatch(r"[0-9a-f]{64}",receipt.parent.name):
                value = checked_json(self.root,receipt)
                rows.append({"key":value["key"],"unit":value["binding"]["unit"],"result":value["result"],"origin":value["origin"],
                             "reused":value["origin"] is not None,"receipt":receipt.relative_to(self.root).as_posix(),"receipt_sha256":digest(receipt)})
        rows.sort(key=lambda row:row["unit"]["iteration"])
        value = {"schema":"cgat.native-refinement-substeps","schema_version":1,"tool":"lrgapcloser","run_id":self.run_id,
                 "session":self.request["session"],"native_command":self.request["command"],"units":rows,
                 "native_returncode":code,"status":"running" if code is None else "finished"}
        atomic_json(self.jobs/SUMMARY,{**value,"payload_sha256":fingerprint(value)})

    def live_owner(self):
        owner = checked_json(self.root,self.jobs/OWNER)
        if (owner.get("status") != "running" or owner.get("run_id") != self.run_id
                or owner.get("request_sha256") != digest(self.jobs/REQUEST) or owner.get("start") != process_identity(owner["pid"])):
            raise PathError("LR unit lost its live native attempt")
        return owner

    def input_data(self,number):
        owner = self.live_owner()
        cache = self.jobs/SNAPSHOTS
        snapshots = checked_json(self.root,cache) if cache.exists() else {"run_id":self.run_id,"owner_start":owner["start"],"files":{}}
        if snapshots.get("run_id") != self.run_id or snapshots.get("owner_start") != owner["start"]:
            raise PathError("LR input snapshots belong to another native epoch")
        genome = self.output/"genome_uc.fasta" if number==1 else self.output/f"iteration-{number-1}/gapclosed.fasta"
        inputs = {"genome":genome,"reads":self.output/"LR.fasta","read_lengths":self.output/"LR_length"}
        tags = sorted((self.output/"tmp").glob("x*"))
        if len(tags) != int(option(self.request["command"],"-n")):
            raise PathError("LR prepared tag partition closure is incomplete")
        inputs.update({"tags/"+path.name:path for path in tags})
        if number==1:
            for suffix in ("amb","ann","bwt","pac","sa"):
                inputs["index/"+suffix] = self.output/("iteration-1/db/genome."+suffix)
        else:
            for name in ("gap.location","genome.id"):
                inputs["prelude/"+name] = self.output/f"iteration-{number}/tmp"/name
        facts,identities = {},{}
        for role,path in inputs.items():
            path = owned(self.root,path)
            identity = stat_key(path)
            saved = snapshots["files"].get(str(path))
            if saved and saved["identity"] == list(identity):
                fact = saved["fact"]
            else:
                fact,identity = file_fact(path)
                snapshots["files"][str(path)] = {"identity":list(identity),"fact":fact}
            facts[role],identities[str(path)] = fact,list(identity)
        seal(cache,snapshots)
        unit = {"kind":"lr.iteration","iteration":number,"scope":"mapping_filter_reconstruction"}
        return {"session":self.request["session"],"unit":unit,"inputs":facts},identities

    def outputs(self,number):
        directory = self.output/f"iteration-{number}"
        return {"gapclosed.fasta":owned(self.root,directory/"gapclosed.fasta"),
                "info_filter2":owned(self.root,directory/"tmp/info_filter2")}

    def find(self,key,binding):
        for receipt in sorted(self.jobs.parent.glob("*/native_units/"+key+"/"+RECEIPT)):
            try:
                owner = receipt.parents[2].name
                if owner==self.run_id or not re.fullmatch(r"[0-9a-f]{32}",owner): continue
                value = checked_json(self.root,receipt)
                if (value.get("schema") != SCHEMA or value.get("schema_version") != 1 or value.get("status") != "completed"
                        or value.get("tool") != "lrgapcloser" or value.get("run_id") != owner or value.get("key") != key
                        or value.get("binding") != binding or value.get("origin") is not None or value.get("execution",{}).get("computed") is not True):
                    continue
                validate_bundle(self.root,receipt,value,self.request["chromosomes"])
                return receipt,value
            except (OSError,ValueError,KeyError,TypeError,AttributeError): continue
        return None

    def restore(self,number):
        for path in self.outputs(number).values():
            if path.exists() or path.is_symlink(): raise PathError("LR iteration already has unsealed output")
        binding,identities = self.input_data(number)
        key,started = fingerprint(binding),time.monotonic()
        begin = {"binding":binding,"identities":identities,"started":started,"event":"iteration_processing_started"}
        path = self.pending/f"iteration-{number}.json"
        if path.exists() or path.is_symlink(): raise PathError("LR processing stage was entered twice")
        seal(path,begin)
        cached = self.find(key,binding)
        if cached is None: return 1
        receipt,producer = cached
        for name,destination in self.outputs(number).items():
            shutil.copyfile(receipt.parent/name,destination)
            if digest(destination) != producer["artifacts"][name]: raise PathError("LR replayed output differs from its producer")
        self.publish(number,begin,producer= cached)
        print(f"[CGAT LR ITERATION REUSED] iteration={number}",flush=True)
        return 0

    def commit(self,number):
        begin = checked_json(self.root,self.pending/f"iteration-{number}.json")
        self.publish(number,begin)
        print(f"[CGAT LR ITERATION COMPLETE] iteration={number}",flush=True)
        return 0

    def publish(self,number,begin,*,producer=None):
        binding,identities = self.input_data(number)
        if binding != begin["binding"] or identities != begin["identities"]:
            raise PathError("LR processing stage consumed changing inputs")
        key = fingerprint(binding)
        temporary = self.directory/("incomplete-"+key+"-"+uuid.uuid4().hex); temporary.mkdir()
        result = output_result(self.outputs(number),self.request["chromosomes"])
        artifacts,origin = {},None
        for name,path in self.outputs(number).items():
            fact,before = file_fact(path)
            try: os.link(path,temporary/name)
            except OSError: shutil.copyfile(path,temporary/name)
            if digest(temporary/name) != fact["sha256"] or stat_key(path)[:4] != before[:4]:
                raise PathError("LR iteration output changed while sealing")
            artifacts[name] = fact["sha256"]
        if producer:
            receipt,previous = producer
            shutil.copyfile(receipt,temporary/"producer.json")
            if checked_json(self.root,temporary/"producer.json") != previous or previous["result"] != result:
                raise PathError("LR original producer changed during replay")
            origin = {"run_id":previous["run_id"],"receipt":receipt.relative_to(self.root).as_posix(),
                      "receipt_sha256":digest(temporary/"producer.json")}
            artifacts["producer.json"] = origin["receipt_sha256"]
        value = {"schema":SCHEMA,"schema_version":1,"status":"completed","tool":"lrgapcloser","run_id":self.run_id,
                 "key":key,"binding":binding,"origin":origin,"result":result,"artifacts":artifacts,
                 "execution":{"computed":producer is None,"returncode":0,"seconds":time.monotonic()-begin["started"],
                              "producer_seconds":producer[1]["execution"]["seconds"] if producer else None}}
        validate_bundle(self.root,temporary/RECEIPT,value,self.request["chromosomes"],receipt_required=False)
        for name in artifacts:
            with (temporary/name).open("rb") as stream: os.fsync(stream.fileno())
        seal(temporary/RECEIPT,value)
        final = self.directory/key
        if final.exists() or final.is_symlink(): raise PathError("LR iteration completed twice")
        os.rename(temporary,final); sync_directories(self.directory)


def output_result(files,names):
    try:
        from refinement_native_checkpoint import fasta_facts
    except ModuleNotFoundError:
        from .refinement_native_checkpoint import fasta_facts
    _,records,_ = fasta_facts(files["gapclosed.fasta"],names)
    with files["info_filter2"].open() as stream: rows = sum(bool(line.strip()) for line in stream)
    return {"outcome":"completed_iteration","assembly":records,"info_rows":rows,"info_sha256":digest(files["info_filter2"])}


def validate_bundle(root,receipt,value,names,*,receipt_required=True):
    expected = set(OUTPUTS)|({"producer.json"} if value["origin"] else set())
    if set(value["artifacts"]) != expected or value["execution"].get("returncode") != 0:
        raise PathError("LR terminal iteration artifact/exit closure is incomplete")
    files = []
    for name,sha in value["artifacts"].items():
        path = owned(root,receipt.parent/name)
        if digest(path) != sha: raise PathError("LR unit artifact changed")
        files.append(path)
    if output_result({name:receipt.parent/name for name in OUTPUTS},names) != value["result"]:
        raise PathError("LR unit output no longer reproduces its result")
    if value["origin"]:
        origin = value["origin"]; previous = checked_json(root,receipt.parent/"producer.json")
        if not re.fullmatch(r"[0-9a-f]{32}",origin["run_id"]): raise PathError("invalid LR native producer")
        expected_origin = automatic_dir(root, 'lrgapcloser') / "02_jobs"/origin["run_id"]/"native_units"/value["key"]/RECEIPT
        if (origin["receipt"] != expected_origin.relative_to(root).as_posix() or origin["receipt_sha256"] != value["artifacts"]["producer.json"]
                or previous.get("schema") != SCHEMA or previous.get("schema_version") != 1 or previous.get("status") != "completed"
                or previous.get("tool") != "lrgapcloser" or previous.get("run_id") != origin["run_id"] or previous.get("key") != value["key"]
                or previous.get("binding") != value["binding"] or previous.get("result") != value["result"] or previous.get("origin") is not None
                or previous.get("execution",{}).get("computed") is not True or previous["execution"].get("returncode") != 0
                or previous.get("artifacts") != {name:sha for name,sha in value["artifacts"].items() if name != "producer.json"}):
            raise PathError("LR original producer is not the completed iteration")
    return files+([receipt] if receipt_required else [])


def capture_units(root,run_id,code,*,required=False):
    jobs = automatic_dir(root, 'lrgapcloser') / "02_jobs"/run_id
    if not (jobs/SUMMARY).exists() and not required: return []
    summary,request = checked_json(root,jobs/SUMMARY),checked_json(root,jobs/REQUEST)
    if (summary.get("schema") != "cgat.native-refinement-substeps" or summary.get("schema_version") != 1
            or summary.get("status") != "finished" or summary.get("tool") != "lrgapcloser" or summary.get("run_id") != run_id
            or type(summary.get("native_returncode")) is not int or summary["native_returncode"] != code
            or summary["session"] != request["session"] or summary["native_command"] != request["command"]
            or request.get("tool") != "lrgapcloser" or request.get("run_id") != run_id):
        raise PathError("LR iteration summary does not close its native producer")
    owner = checked_json(root,jobs/OWNER)
    if (owner.get("status") != "finished" or owner.get("run_id") != run_id or owner.get("returncode") != code
            or owner.get("request_sha256") != digest(jobs/REQUEST)):
        raise PathError("LR native owner has not finished")
    files = [jobs/SUMMARY,jobs/REQUEST,jobs/OWNER,jobs/SNAPSHOTS]
    for path,sha in ((jobs/"native_recovery_driver.sh",request["driver_sha256"]),(Path(request["command"][4]),request["source_sha256"])):
        path = owned(root,path)
        if digest(path) != sha: raise PathError("LR private driver changed")
        files.append(path)
    output = automatic_dir(root, 'lrgapcloser') / "03_native"/run_id/"output"
    iterations = sorted(int(path.parent.name.split("-")[1]) for path in output.glob("iteration-*/gapclosed.fasta"))
    if iterations != list(range(1,len(iterations)+1)) or len(iterations) > int(option(request["command"],"-r")):
        raise PathError("LR iteration output closure is not contiguous")
    actual,seen = [],set()
    for row in summary["units"]:
        key = row["key"]
        if not re.fullmatch(r"[0-9a-f]{64}",key) or key in seen: raise PathError("invalid/duplicated LR unit key")
        seen.add(key)
        receipt = owned(root,jobs/"native_units"/key/RECEIPT); value = checked_json(root,receipt)
        if (value.get("schema") != SCHEMA or value.get("schema_version") != 1 or value.get("status") != "completed"
                or value.get("tool") != "lrgapcloser" or value.get("run_id") != run_id or value.get("key") != key
                or row["receipt"] != receipt.relative_to(root).as_posix() or row["receipt_sha256"] != digest(receipt)
                or fingerprint(value["binding"]) != key or value["binding"]["session"] != request["session"]
                or row["unit"] != value["binding"]["unit"] or row["result"] != value["result"] or row["origin"] != value["origin"]
                or type(row["reused"]) is not bool or row["reused"] != bool(value["origin"])
                or value["execution"]["computed"] is not (not row["reused"])):
            raise PathError("LR iteration unit closure changed")
        unit = row["unit"]
        if unit.get("kind") != "lr.iteration" or unit.get("scope") != "mapping_filter_reconstruction" or type(unit["iteration"]) is not int:
            raise PathError("LR unit has an unknown consumer")
        number = unit["iteration"]; actual.append(number)
        files += validate_bundle(root,receipt,value,request["chromosomes"])
        consumed = {"gapclosed.fasta":output/f"iteration-{number}/gapclosed.fasta","info_filter2":output/f"iteration-{number}/tmp/info_filter2"}
        for name,path in consumed.items():
            path = owned(root,path)
            if digest(path) != value["artifacts"][name]: raise PathError("LR consumed iteration output changed")
            files.append(path)
    if actual != iterations or not actual: raise PathError("LR units do not cover every completed iteration")
    return list(dict.fromkeys(files))


def main():
    args = sys.argv[1:]
    if len(args)<2 or args[0] != "--request": raise PathError("LR wrapper requires its sealed request")
    request_path = Path(args[1]).absolute(); root = native_request_root(request_path)
    request = checked_json(root,request_path)
    if (request.get("schema") != "cgat.native-refinement-launch" or request.get("tool") != "lrgapcloser"
            or request.get("root") != str(root) or request.get("run_id") != request_path.parent.name
            or request.get("jobs") != str(request_path.parent) or request.get("cwd") != str(Path.cwd())
            or request.get("helpers") != helper_hashes("lrgapcloser") or request["session"]["helpers"] != request["helpers"]
            or request_path != automatic_dir(root, 'lrgapcloser') / "02_jobs"/request["run_id"]/REQUEST):
        raise PathError("LR launcher does not match its owned attempt")
    if len(args)>2:
        if len(args)!=6 or args[2] != "--action" or args[3] not in {"restore","commit"} or args[4] != "--iteration":
            raise PathError("unsupported LR iteration action")
        number = int(args[5])
        if not 1 <= number <= int(option(request["command"],"-r")): raise PathError("LR iteration is out of recipe range")
        store = LrUnits(request)
        return store.restore(number) if args[3]=="restore" else store.commit(number)
    store = LrUnits(request,create=True)
    if store.output.exists() or store.output.is_symlink(): raise PathError("LR native output must be fresh")
    if (store.jobs/"native_recovery_driver.sh").read_bytes() != generated_driver(request):
        raise PathError("LR owned driver is not the declared source-only instrumentation")
    owner = {"schema":"cgat.native-iteration-owner","run_id":store.run_id,"pid":os.getpid(),"start":process_identity(os.getpid()),
             "request_sha256":digest(request_path),"status":"running"}
    seal(store.jobs/OWNER,owner)
    code = 1
    try: code = subprocess.run(request["driver_command"]).returncode
    finally:
        seal(store.jobs/OWNER,{**owner,"status":"finished","returncode":code})
        store.write_summary(code)
    return code


if __name__ == "__main__":
    try: sys.exit(main())
    except Exception as error:
        print("CGAT LR recovery error: "+str(error),file=sys.stderr)
        sys.exit(2)
