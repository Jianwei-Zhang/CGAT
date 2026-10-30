#!/usr/bin/env python3
"""Maintainer-only development package preparation; PLAN ONLY by default.

Copy a fresh Server tree and overlay initial-reference command generation there.
Never edits published Server sources, current workspaces, install/update scripts
or official Release assets. No compile, download, test, job or customer config.
A customer-validation artifact additionally requires a source-bound maintainer
acceptance receipt. This does not certify the unavailable customer FASTA.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path,PurePosixPath
import shutil
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True

import build_native_chain_state as build
import native_chain_state as nst
import server_alignment as adapter
import resume_reference as resume
import windowed_alignment as wa

REF_ANCHOR = '  write_alignment_command_script "${run_dir}/command.sh" "$run_dir" "$ref_fa" "$ds_fa" false\n'
COPY_ANCHOR = '  cp -R "$tools_src/grt_core" "$tools_dst/grt_core"\n'
REF_OVERLAY = r'''  if [[ "$MINIMAP_PRESET" == "asm10" ]]; then
    local runtime_threads="\"\${GPM_TASK_THREADS:-${THREADS}}\""
    {
      printf '#!/usr/bin/env bash\nset -euo pipefail\n'
      printf 'cd %s\n' "$(shell_quote "$run_dir")"
      printf '(minimap2 --version > tool_version.txt 2>&1 || printf %s > tool_version.txt)\n' "$(shell_quote $'unknown\n')"
      printf 'exec python3 %s --server-dir %s --run-dir %s --target %s --query %s --threads %s --preset asm10 --result result.paf > stdout.log 2> stderr.log\n' \
        "$(shell_quote "${WORK_ROOT}/.prepare_lib/tools/long_cigar_recovery/server_alignment.py")" \
        "$(shell_quote "$WORK_ROOT")" "$(shell_quote "$run_dir")" \
        "$(shell_quote "$ref_fa")" "$(shell_quote "$ds_fa")" "$runtime_threads"
    } > "${run_dir}/command.sh"
    make_executable_if_supported "${run_dir}/command.sh"
  fi
'''
COPY_OVERLAY = '  cp -R "$tools_src/long_cigar_recovery" "$tools_dst/long_cigar_recovery"\n'
EXCLUDE = {".git","__pycache__",".pytest_cache","tests","validation"}


def overlay_prepare(text):
    """Exactly the named initial-ref function/copy site; source drift refuses."""
    if "long_cigar_recovery/server_alignment.py" in text or COPY_OVERLAY in text:
        raise wa.ExperimentError("Server source already contains a branch overlay; do not stack development packages")
    if text.count(REF_ANCHOR)!=1 or text.count(COPY_ANCHOR)!=1:
        raise wa.ExperimentError("Server prepare generator changed; refusing a guessed branch overlay")
    anchor_at = text.index(REF_ANCHOR)
    function_at = text.rfind("write_ref_command_script() {\n",0,anchor_at)
    if function_at<0 or text.find("\n}\n",function_at)<anchor_at:
        raise wa.ExperimentError("reference hook no longer belongs to write_ref_command_script")
    copy_at = text.index(COPY_ANCHOR)
    copy_function = text.rfind("write_prepare_lib() {\n",0,copy_at)
    if copy_function<0 or text.find("\n}\n",copy_function)<copy_at:
        raise wa.ExperimentError("runtime hook no longer belongs to write_prepare_lib")
    return text.replace(REF_ANCHOR,REF_ANCHOR+REF_OVERLAY).replace(COPY_ANCHOR,COPY_ANCHOR+COPY_OVERLAY)


CHECKPOINT_ANCHOR = '        manifest = (self.server_dir / command_relpath).parent / "alignment_tasks.json"\n'
CHECKPOINT_OVERLAY = '        branch_runtime = self.server_dir / ".prepare_lib/tools/long_cigar_recovery"\n' + (
    '        if (branch_runtime.is_dir() and "long_cigar_recovery/server_alignment.py"\n'
    '                in (self.server_dir / command_relpath).read_text(encoding="utf-8")):\n'
    '            paths.extend(sorted(p for p in branch_runtime.rglob("*")\n'
    '                                if p.is_file() and "__pycache__" not in p.parts))\n'
)


def overlay_checkpoint(text):
    if ".prepare_lib/tools/long_cigar_recovery" in text:
        raise wa.ExperimentError("checkpoint source already contains branch runtime bindings")
    if text.count(CHECKPOINT_ANCHOR)!=1:
        raise wa.ExperimentError("reference checkpoint source changed; refusing a guessed runtime binding")
    at = text.index(CHECKPOINT_ANCHOR)
    previous = text.rfind("    def ",0,at)
    if not text[previous:].startswith("    def _reference_inputs("):
        raise wa.ExperimentError("runtime checkpoint hook no longer belongs to initial-reference inputs")
    return text.replace(CHECKPOINT_ANCHOR,CHECKPOINT_OVERLAY+CHECKPOINT_ANCHOR)


RUN_ANCHOR = '        if not ready:\n'
RUN_OVERLAY = (
    '        if ready:\n'
    '            sys.path.insert(0, str(server_source / "tools/long_cigar_recovery"))\n'
    '            from resume_reference import handoff\n'
    '            from run_outer_checkpoints import OuterCheckpointManager\n'
    '            handoff_report = handoff(root, server_source, run_id, load_plan(root), OuterCheckpointManager(root))\n'
    '            print("[REFERENCE HANDOFF] " + json.dumps(handoff_report, ensure_ascii=True), flush=True)\n'
)


def overlay_server_run(text):
    if "from resume_reference import handoff" in text or text.count(RUN_ANCHOR)!=1:
        raise wa.ExperimentError("Server resume entry changed or already overlaid; refusing guessed handoff")
    at = text.index(RUN_ANCHOR)
    function = text.rfind("def execute(",0,at)
    if function<0 or not function<text.find("        lock.acquire()",function)<at:
        raise wa.ExperimentError("reference handoff hook must follow actual workspace lock acquisition")
    return text.replace(RUN_ANCHOR,RUN_OVERLAY+RUN_ANCHOR)


def source_inventory(source):
    """Package tracked Server source, never broad-copy a customer data tree."""
    source = Path(source).resolve()
    # Git supplies repository-relative names; do not compare differently cased
    # absolute aliases of the shared Windows/WSL checkout.
    prefix = subprocess.check_output(["git","-C",str(source),"rev-parse","--show-prefix"],text=True).strip()
    if not prefix or not prefix.endswith("/"):
        raise wa.ExperimentError("branch package source must be the tracked Server subtree")
    raw = subprocess.check_output(["git","-C",str(source),"ls-files","--full-name","-z","--","."])
    names = []
    for data in raw.split(b"\0"):
        if not data:
            continue
        name = data.decode("utf-8")
        if not name.startswith(prefix):
            raise wa.ExperimentError("tracked Server inventory escaped the requested source subtree")
        name = name[len(prefix):]
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name:
            raise wa.ExperimentError("unsupported tracked Server inventory path")
        if not any(part in EXCLUDE for part in path.parts):
            names.append(name)
    if not names or len(names)!=len(set(names)):
        raise wa.ExperimentError("tracked Server inventory is empty/duplicated")
    revision = subprocess.check_output(["git","-C",str(source),"rev-parse","HEAD"],text=True).strip()
    return sorted(names),{"repository_revision":revision,"commit_is_baseline_only":True,
                          "worktree_source_bound_by_file_hashes":True}


# Immutable fc.. -> fe59b81 public GRT-to-LGZ presentation rename. Reviewed:
# help/progress/error text only; reference commands, locking and checkpoint
# schemas stay unchanged. Do NOT normalize arbitrary future text or source.
PRESENTATION_RECIPE_PAIRS = {
    "prepare.sh": ("76a6f4046a6fd5966fd9600305a0034b4a5d5d3be6fcf4b0dfd088f4cba67964",
                   "e9c005073c8ad297af893fe36f564cd6c80bf45a30d5ec29ecd7c930386f54cd"),
    "tools/server_run.py": ("6fad0772c02799ce6f49f45b7fe428623a9bd39b993f377575e02c1fe953ab6f",
                            "891828998f27b5cd8dfd67ec9d5a519725e3bfdb713e5e35e1e4d36474f1c07c"),
    "tools/run_outer_checkpoints.py": ("ccf52177a8e569c489a5458aa98f1e0e9841a7c06b9b6880f91c4810ce404eb0",
                                       "aa084b93655ce5073bd0c70ebc8150f5fe68dbd582576e4a0d8f0748d40301d9"),
}


def equivalent_recipe(name,old,current):
    return old==current or PRESENTATION_RECIPE_PAIRS.get(name)==(
        hashlib.sha256(old).hexdigest(),hashlib.sha256(current).hexdigest())


def resume_source_profile(source,revision):
    """Maintainer prebinds immutable old source; this is not customer config."""
    if type(revision) is not str or re.fullmatch(r"[0-9a-f]{40}",revision) is None:
        raise wa.ExperimentError("resume source profile requires a full immutable Git revision")
    repository = subprocess.check_output(["git","-C",str(source),"rev-parse","--show-toplevel"],text=True).strip()
    prefix = subprocess.check_output(["git","-C",str(source),"rev-parse","--show-prefix"],text=True).strip()
    resolved = subprocess.check_output(["git","-C",repository,"rev-parse",revision+"^{commit}"],text=True).strip()
    if resolved!=revision:
        raise wa.ExperimentError("resume source revision cannot be resolved exactly")
    def blob(name):
        return subprocess.check_output(["git","-C",repository,"show",revision+":"+prefix+name])
    # These define command ownership, the launch lock and checkpoint/manifest
    # contract. Only exact bytes or the hash-pinned presentation-only pair
    # above is accepted. Never infer semantic equivalence from renamed words.
    presentation_equivalence = []
    for name in ("prepare.sh","tools/server_run.py","tools/run_outer_checkpoints.py","tools/alignment_tasks.py"):
        old,current = blob(name),(source/name).read_bytes()
        if not equivalent_recipe(name,old,current):
            raise wa.ExperimentError(f"resume source profile has a different reference/launch/checkpoint recipe: {name}")
        if old!=current:
            presentation_equivalence.append(name)
    raw = subprocess.check_output(["git","-C",repository,"ls-tree","-r","--name-only","-z",revision,"--",prefix+"tools/"])
    hashes = {}
    for name in raw.decode("utf-8").split("\0"):
        if not name:
            continue
        if not name.startswith(prefix+"tools/"):
            raise wa.ExperimentError("resume source profile inventory escaped Server tools")
        relative = name[len(prefix):]
        if relative.endswith(".py") and not any(p in EXCLUDE for p in PurePosixPath(relative).parts):
            hashes[relative] = hashlib.sha256(blob(relative)).hexdigest()
    if not hashes:
        raise wa.ExperimentError("resume source profile contains no original Server tool modules")
    return {"revision":revision,"base_tools_files_sha256":hashes,
            "reference_launch_checkpoint_recipe_equal":True,
            "pinned_presentation_equivalence_files":presentation_equivalence}


def copy_regular_tree(source,destination,names):
    source,destination = Path(source).resolve(),Path(destination)
    destination.mkdir()
    receipt = {}
    for name in names:
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name:
            raise wa.ExperimentError("unsupported Server inventory member")
        path = source.joinpath(*relative.parts)
        if path.is_symlink() or not path.is_file() or any(p.is_symlink() for p in path.parents if p!=source and source in p.parents):
            raise wa.ExperimentError(f"Server inventory must contain original regular source files: {name}")
        target = destination.joinpath(*relative.parts)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,target)
        digest = wa.sha256(path)
        if wa.sha256(target)!=digest:
            raise wa.ExperimentError("Server source changed while copying the development tree")
        receipt[name] = digest
    return receipt


def verify_archive(archive,expected):
    seen = set()
    with tarfile.open(archive,"r|gz") as tar:
        for member in tar:
            if not member.name.startswith("GPM_Server/") or not member.isfile():
                raise wa.ExperimentError("development archive has a foreign or nonregular member")
            name = member.name.removeprefix("GPM_Server/")
            if name not in expected or name in seen:
                raise wa.ExperimentError("development archive has extra/duplicated source members")
            digest = hashlib.sha256()
            with tar.extractfile(member) as source:
                while raw := source.read(wa.CHUNK):
                    digest.update(raw)
            if digest.hexdigest()!=expected[name]:
                raise wa.ExperimentError("development archive content differs from packaged file identities")
            seen.add(name)
    if seen!=set(expected):
        raise wa.ExperimentError("development archive omits packaged source members")
    return {"verified_regular_files":len(seen),"member_hashes_equal":True}


VALIDATION_CHECKS = frozenset((
    "unit_suite", "native_contract", "grt_final_path", "long_identity", "default_multipart",
    "publication_controls", "legacy_runtime", "packaged_lifecycle", "packaged_full_workflow",
    "same_command_resume", "server_quality", "merge_compatibility", "app_import_export",
))


def validation_receipt(path,*,runtime_hashes,base_hashes,bundle):
    """Maintainer attestation of completed checks, bound to exact shipped inputs.

    Not a customer config or a cryptographic test runner. Individual raw receipt
    hashes remain auditable; labels alone never enable recovered PAF admission.
    """
    if path is None:
        return None
    path = Path(path)
    if (not path.is_file() or path.is_symlink() or path.stat().st_size>1024*1024):
        raise wa.ExperimentError("validation receipt must be a bounded regular JSON file")
    try:
        value = json.loads(path.read_bytes())
    except (ValueError,UnicodeError) as exc:
        raise wa.ExperimentError("invalid validation receipt JSON") from exc
    if (type(value) is not dict or value.get("schema")!=1
            or value.get("status")!="local_acceptance_passed_customer_validation_pending"
            or value.get("customer_original_data_validated") is not False
            or value.get("runtime_files_sha256")!=runtime_hashes
            or value.get("base_server_files_sha256")!=base_hashes
            or bundle.get("platform")!="linux-x86_64"
            or value.get("native_companion_sha256")!=bundle["sha256"]
            or value.get("native_companion_manifest_sha256")!=bundle["manifest_sha256"]
            or (bundle.get("runtime_abi") or {}).get("legacy_2_17_checked") is not True):
        raise wa.ExperimentError("validation receipt does not bind this exact runtime/Server/portable companion")
    checks = value.get("checks")
    if type(checks) is not dict or set(checks)!=VALIDATION_CHECKS:
        raise wa.ExperimentError("validation receipt omits required local acceptance checks")
    for name,row in checks.items():
        if (type(row) is not dict or row.get("passed") is not True
                or type(row.get("receipt_sha256")) is not str
                or adapter.HASH.fullmatch(row["receipt_sha256"]) is None):
            raise wa.ExperimentError("validation receipt has an incomplete check: "+name)
    return value


def prepare_package(args):
    output = args.out.resolve()
    source = args.server_source.resolve()
    runtime_source = Path(__file__).resolve().parent
    if output.exists() or args.out.is_symlink() or not output.parent.is_dir():
        raise wa.ExperimentError("branch package needs a fresh directory under an existing parent")
    protected_sources = [source,runtime_source]
    if args.native_state_bundle is not None:
        protected_sources.append(args.native_state_bundle.resolve())
    for protected in protected_sources:
        if output==protected or protected in output.parents or output in protected.parents:
            raise wa.ExperimentError("package output cannot overlap Server/runtime/companion sources")
    for parent in (output.parent,*output.parent.parents):
        if (parent/".prepare_lib").exists() or (parent/"run_all.sh").exists():
            raise wa.ExperimentError("development package must be outside prepared customer workspaces")
    for name in ("run.sh","prepare.sh","tools/server_run.py","tools/run_outer_checkpoints.py","lib/incremental_common.sh"):
        if not (source/name).is_file():
            raise wa.ExperimentError(f"Server source is missing: {name}")
    if args.native_state_bundle is None:
        raise wa.ExperimentError("maintainer must build the pinned companion before development packaging; never delegate this to the customer")
    bundle = nst.validate_bundle(args.native_state_bundle)
    native_files = {build.BINARY:bundle["sha256"],build.MANIFEST:bundle["manifest_sha256"],
                    **bundle.get("third_party_licenses_sha256",{})}
    inventory,source_revision = source_inventory(source)
    runtime_hashes = adapter.runtime_files(runtime_source)
    resume_profiles = [resume_source_profile(source,revision) for revision in getattr(args,"resume_source_revision",[])]
    prepare_original = (source/"prepare.sh").read_text()
    patched_prepare = overlay_prepare(prepare_original)
    patched_checkpoint = overlay_checkpoint((source/"tools/run_outer_checkpoints.py").read_text())
    patched_server_run = overlay_server_run((source/"tools/server_run.py").read_text())
    supported = (bundle.get("runtime_abi") or {}).get("legacy_2_17_checked") is True
    admission = adapter.pub.POLICY if supported else "closed_pending_final_acceptance"
    accepted = validation_receipt(getattr(args,"validation_receipt",None),runtime_hashes=runtime_hashes,
                                  base_hashes={name:wa.sha256(source/name) for name in inventory},bundle=bundle)
    output.mkdir(mode=0o700)
    report = {"schema":1,"status":"preparing_unvalidated_development_package","production_ready":False,
              "customer_deliverable":accepted is not None,"customer_validation_pending":True,"recovered_output_admission":admission,
              "official_release_modified":False,"original_sources_modified":False,"tests_executed":False,
              "compilation_performed":False,"customer_configuration_required":False,"native_companion":bundle,
              "package_builder_sha256":wa.sha256(Path(__file__)),"source_revision":source_revision}
    try:
        server = output/"GPM_Server"
        base_hashes = copy_regular_tree(source,server,inventory)
        runtime = server/"tools"/"long_cigar_recovery"
        runtime.mkdir()
        for name,expected in runtime_hashes.items():
            shutil.copy2(runtime_source/name,runtime/name)
            if wa.sha256(runtime/name)!=expected:
                raise wa.ExperimentError("branch runtime changed during development packaging")
        platform_dir = runtime/"native"/bundle["platform"]
        platform_dir.mkdir(parents=True)
        for name,expected in native_files.items():
            shutil.copy2(Path(bundle["manifest_path"]).parent/name,platform_dir/name)
            if wa.sha256(platform_dir/name)!=expected:
                raise wa.ExperimentError("prebuilt companion changed during development packaging")
        base_tools = {name:digest for name,digest in base_hashes.items()
                      if name.startswith("tools/") and name.endswith(".py")}
        wa.write_json(runtime/resume.BASE,{"schema":1,
            "source_profiles":[{"revision":"package_base","base_tools_files_sha256":base_tools,
                                "reference_launch_checkpoint_recipe_equal":True},*resume_profiles],
            "base_prepare_sha256":base_hashes["prepare.sh"],"source_revision":source_revision})
        runtime_receipt = {"schema":1,"status":"source_checked_recovery_runtime" if supported else "unvalidated_branch_runtime",
            "scope":"initial_reference_asm10_only",
            "files_sha256":runtime_hashes,"recovered_output_admission":admission,
            "native_companion_platform":bundle["platform"],"native_companion_sha256":bundle["sha256"],
            "handoff_base_sha256":wa.sha256(runtime/resume.BASE),
            "production_ready":False,"customer_configuration_required":False}
        wa.write_json(runtime/adapter.MANIFEST,runtime_receipt)
        (server/"prepare.sh").write_text(patched_prepare)
        (server/"tools/run_outer_checkpoints.py").write_text(patched_checkpoint)
        (server/"tools/server_run.py").write_text(patched_server_run)
        if (server/"SOURCE.json").exists():
            if (server/"SOURCE.base.json").exists():
                raise wa.ExperimentError("source already contains a saved baseline receipt; refusing to overwrite provenance")
            (server/"SOURCE.json").rename(server/"SOURCE.base.json")
        if accepted is not None:
            wa.write_json(server/"LOCAL_ACCEPTANCE.json",accepted)
        wa.write_json(server/"SOURCE.json",{"schema":1,"kind":"locally_validated_minimap2_recovery_candidate" if accepted else "unvalidated_minimap2_hypothesis_branch",
            "official_release":False,"production_ready":False,"customer_deliverable":accepted is not None,
            "local_acceptance_sha256":wa.sha256(server/"LOCAL_ACCEPTANCE.json") if accepted else None,
            "base_server_files_sha256":base_hashes,
            "source_revision":source_revision,
            "branch_runtime_sha256":wa.sha256(runtime/adapter.MANIFEST),
            "prepare_before_sha256":base_hashes["prepare.sh"],"prepare_after_sha256":wa.sha256(server/"prepare.sh"),
            "recovered_output_admission":admission})
        (server/"BRANCH_README.txt").write_text(
            ("LOCALLY VALIDATED RECOVERY CANDIDATE - CUSTOMER ORIGINAL-DATA VALIDATION PENDING\n" if accepted else
             "RECOVERY INTEGRATION CANDIDATE - CUSTOMER DELIVERY ACCEPTANCE STILL REQUIRED\n" if supported else
             "UNVALIDATED DEVELOPMENT PACKAGE - NOT A CUSTOMER REPAIR RELEASE\n")+
            "Existing run.sh interface is unchanged. Only initial-reference asm10 calls use the internal adapter.\n"
            "Native-complete output is published unchanged. " +
            ("Supported recovery requires complete original cells, actual singleton aborts, source-supported long-operation evidence,\n"
             "paired paths and metadata bound to actual native selector input/stdout. Unknown recovery MAPQ is never published.\n"
             if supported else
             "Recovery candidates remain private and exit nonzero; formal recovered output admission is CLOSED.\n")+
            "No user configuration, compiler, download or FASTA splitting is required.\n"
            "Extract into a separate installation directory; never overwrite the old installation or official Release.\n"
            "Use its run.sh with the original arguments. Known failed-workspace handoff is source-checked and transactional.\n"
            "Keep the old installation, workspace, logs and .run_all/long-cigar-handoff-* backups. No FASTA is deleted.\n"
            "Switching the installation alone does NOT undo an adapted workspace. For a pure old-code rollback,\n"
            "use the old installation with a new output directory; the original minimap2 limitation remains.\n"
        )
        if adapter.runtime_files(runtime)!=runtime_hashes or adapter.runtime_files(runtime_source)!=runtime_hashes:
            raise wa.ExperimentError("runtime source attribution changed while packaging")
        for name,digest in base_hashes.items():
            if wa.sha256(source/name)!=digest:
                raise wa.ExperimentError("original Server source changed while packaging")
        adapter.validate_runtime(runtime)
        packaged_files = {p.relative_to(server).as_posix():wa.sha256(p) for p in sorted(server.rglob("*")) if p.is_file()}
        archive = output/("CGAT-minimap2-recovery-candidate-linux-x86_64.tar.gz" if accepted else "CGAT-minimap2-branch-unvalidated.tar.gz")
        with tarfile.open(archive,"w:gz",format=tarfile.PAX_FORMAT) as tar:
            # Add named regular members only. No broad recursive traversal can
            # absorb a cache, new binary or concurrent unrecorded source file.
            for name in packaged_files:
                tar.add(server/name,arcname="GPM_Server/"+name,recursive=False)
        if any(wa.sha256(server/name)!=digest for name,digest in packaged_files.items()):
            raise wa.ExperimentError("packaged source tree changed while archiving")
        integrity = verify_archive(archive,packaged_files)
        report.update(status="locally_validated_customer_candidate_prepared" if accepted else "unvalidated_development_package_prepared",
                      local_acceptance_sha256=wa.sha256(server/"LOCAL_ACCEPTANCE.json") if accepted else None,archive=str(archive),archive_integrity=integrity,
                      archive_sha256=wa.sha256(archive),archive_bytes=archive.stat().st_size,
                      packaged_files_sha256=packaged_files,original_sources_unchanged=True)
    except BaseException as exc:
        report.update(status="refused_or_failed",error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        wa.write_json(output/"package-preparation.json",report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-source",type=Path,default=Path(__file__).resolve().parents[2]/"server")
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--native-state-bundle",type=Path,default=None)
    parser.add_argument("--resume-source-revision",action="append",default=[],
                        help="Maintainer-only immutable prior Server revision with the same original reference/launch/checkpoint recipe")
    parser.add_argument("--validation-receipt",type=Path,default=None,
                        help="Maintainer-only source-bound local acceptance attestation; never customer configuration")
    parser.add_argument("--execute",action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status":"plan_only","production_ready":False,"customer_deliverable":False,
            "server_source":str(args.server_source),"output":str(args.out),
            "native_companion_required_from_maintainer":True,"no_files_or_commands_started":True,
            "resume_source_revisions":args.resume_source_revision,
            "recovered_output_admission":"requires_portable_artifact_and_per_result_proof"},indent=2))
        return 0
    try:
        report = prepare_package(args)
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print(json.dumps({"status":"refused_or_failed","error":str(exc),"production_ready":False}))
        return 2
    print(json.dumps({"status":report["status"],"archive":report["archive"],"sha256":report["archive_sha256"],
                      "production_ready":False,"customer_deliverable":report["customer_deliverable"]},indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
