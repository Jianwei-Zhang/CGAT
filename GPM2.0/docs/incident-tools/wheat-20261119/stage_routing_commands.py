"""Stage four pending cross overrides outside the live wheat workspace.

Run only from the isolated routing-resume-staged directory on SSH 180. Does not
submit jobs, alter native commands or stop the currently running 6A leaf.
"""
import dataclasses
import json
from pathlib import Path
import shlex
import shutil
import sys

ROOT = Path.home() / "cgat-reads-debug/jm19-compare-614589f-20261118"
WORK = ROOT / "gpm_server"
HERE = Path(__file__).resolve().parent
VALIDATED = ROOT / "long-query-router-validation-v2-20261119"


def main():
    if HERE != ROOT / "routing-resume-staged-20261119" or (HERE / "routing-plan.json").exists():
        raise RuntimeError("use the isolated initial staging directory; do not overwrite a plan")
    sys.path.insert(0, str(VALIDATED))
    from long_query_cross_router import load_runtime, Policy
    contract, catalog, raw_copy = load_runtime(WORK / ".prepare_lib/tools")
    from paf_anchor_comparison import compare
    from seed_filter_pilot import measure
    files = {"router": VALIDATED / "long_query_cross_router.py",
             "positions": Path(compare.__code__.co_filename), "coverage": Path(measure.__code__.co_filename),
             "contract": Path(contract.__file__), "catalog": Path(catalog.__file__),
             "copy": Path(raw_copy.__file__), "store": Path(raw_copy.wa.__file__),
             "resume": Path(raw_copy.pr.__file__)}
    report = json.loads((VALIDATED / "real-calibration.json").read_text())
    if report.get("status") != "calibration_complete_not_adopted":
        raise RuntimeError("missing isolated validation result")
    if {k:contract.sha256_file(v) for k,v in files.items()} != report["dependencies"]:
        raise RuntimeError("validated router dependencies changed")
    router_names = list(files)
    files.update(entry=HERE / "resume_with_cross_router.py", support=HERE / "routing_resume_support.py",
                 base_entry=ROOT / "memory-exclusive-20261119/resume.py",
                 admission=ROOT / "memory-exclusive-20261119/memory_admission.py")
    dependencies = {k:{"path":str(v.resolve()),"sha256":contract.sha256_file(v)} for k,v in files.items()}
    tool=Path(shutil.which("minimap2")).resolve()
    if contract.sha256_file(tool) != report["tool_sha256"]:
        raise RuntimeError("mapping tool differs from validation")
    plan={"schema":"incident_q0_routing_v1", "workspace":str(WORK), "preset":"asm10",
          "policy":json.loads(json.dumps(dataclasses.asdict(Policy()))),
          "router_dependency_names":router_names,"dependencies":dependencies,"overrides":[]}
    if plan["policy"] != report["policy"]:
        raise RuntimeError("internal routing policy differs from validation")
    expected={row["path"]:row for row in json.loads(
        (ROOT / "memory-resume-20261118/assign.before.json").read_text())["outputs"]}
    for chromosome in ("1D", "4D", "5D", "6D"):
        rel=f"runs/chr_{chromosome}/JM19_flye_ABD_vs_JM19_hifiasm/command.sh"
        native=WORK/rel
        marker=ROOT/"memory-resume-20261118/cross-leaf-checkpoints"/(contract.fingerprint(rel)+".json")
        if marker.exists():
            raise RuntimeError("native leaf completed since review; exclude it before staging: "+rel)
        if contract.file_identity(native,relative_to=WORK) != expected[rel]:
            raise RuntimeError("native command is not assignment-bound: "+rel)
        target=native.parent.parent/"datasets/JM19_flye_ABD.fa"
        query=native.parent.parent/"datasets/JM19_hifiasm.fa"
        checks="\n".join(row["sha256"]+"  "+row["path"] for row in dependencies.values())
        checks+="\n"+report["tool_sha256"]+"  "+str(tool)
        command=["python3","-B",str(files["router"]),"--target",str(target),"--query",str(query),
                 "--output",str(native.parent/"result.paf"),"--receipt",str(native.parent/"routing-receipt.json"),
                 "--cache",str(HERE/"router-caches"/chromosome),"--runtime-tools",str(WORK/".prepare_lib/tools"),
                 "--minimap2",str(tool),"--preset","asm10"]
        script=HERE/("route-"+chromosome+".sh")
        text=("#!/usr/bin/env bash\nset -euo pipefail\ncd "+shlex.quote(str(native.parent))+"\n"
              "sha256sum -c <<'ROUTING_FROZEN_DEPENDENCIES'\n"+checks+"\nROUTING_FROZEN_DEPENDENCIES\n"
              "backup="+shlex.quote(str(HERE/"attempt-logs"/chromosome))+"/$(date +%Y%m%dT%H%M%S)-$$\n"
              "mkdir -p \"$backup\"\n"
              "for file in stdout.log stderr.log result.paf routing-receipt.json; do\n"
              "  if [[ -f \"$file\" ]]; then cp -p -- \"$file\" \"$backup/$file\"; fi\ndone\n"
              "exec "+shlex.join(command)+" --threads \"${GPM_TASK_THREADS:?missing task thread grant}\" > stdout.log 2> stderr.log\n")
        with script.open("x") as handle: handle.write(text)
        script.chmod(0o755)
        plan["overrides"].append({"unit_id":"q0_chr:"+chromosome,"native_command":rel,
          "native_command_sha256":expected[rel]["sha256"],"script":contract.file_identity(script),
          "receipt":str(native.parent/"routing-receipt.json")})
    contract.atomic_write_json(HERE/"routing-plan.json",plan)
    print("STAGED_ONLY",json.dumps({"overrides":len(plan["overrides"]),"main_workspace_modified":False}))


if __name__ == "__main__":
    main()
