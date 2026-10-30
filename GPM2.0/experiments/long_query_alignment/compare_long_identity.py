#!/usr/bin/env python3
"""Persistent REAL >28-bit selective-entry control; PLAN ONLY by default.

Maintainer final validation only, never customer configuration/admission. Uses
unchanged pinned minimap2 and an ALREADY BUILT companion. No compiler/download,
job submission, production workspace edits or automatic parameter retries.
This source has NOT been executed during the implementation phase.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True

import compare_native_controls as control
import native_chain_state as nst
import native_evaluation as ne
import native_first as nf
import selective_reference_alignment as sr
import windowed_alignment as wa

LENGTH = 270_000_000
TARGET = "target"
ORDINARY, REVERSE, UNMAPPED, FORWARD = "z_ordinary", "reverse_long", "a_unmapped", "forward_long"
QUERY_ORDER = (ORDINARY,REVERSE,UNMAPPED,FORWARD)
LONG_NAMES = {REVERSE,FORWARD}
MAX_ROWS = 8
MAX_SMALL_FILE = 2*1024**2


def write_fixtures(root, *, length=LENGTH):
    """Bounded-memory deterministic writer; small lengths are for DEFERRED units.

    The executable validation path requires EXACTLY LENGTH, not a small substitute.
    Reverse complement is copied from the same original bytes in reverse chunks.
    """
    if type(length) is not int or length < 10:
        raise wa.ExperimentError("identity fixture needs at least ten bases")
    root.mkdir()
    reference,query,ordinary = root/"reference.fa",root/"mixed.fa",root/"ordinary.fa"
    alphabet = bytes(b"ACGT"[i&3] for i in range(256))
    header = b">"+TARGET.encode()+b"\n"
    with reference.open("xb") as out:
        out.write(header)
        for block,start in enumerate(range(0,length,wa.CHUNK)):
            count = min(wa.CHUNK,length-start)
            seed = b"CGAT-long-identity-v1:"+block.to_bytes(8,"big")
            out.write(hashlib.shake_256(seed).digest(count).translate(alphabet))
        out.write(b"\n")
    ordinary_start,ordinary_length = length//3,min(60_000,length//5)
    unmapped_length = 3000
    with reference.open("rb") as source,query.open("xb") as out,ordinary.open("xb") as normal:
        source.seek(len(header)+ordinary_start)
        body = source.read(ordinary_length)
        if len(body)!=ordinary_length:
            raise wa.ExperimentError("truncated generated reference")
        ordinary_record = b">"+ORDINARY.encode()+b"\n"+body+b"\n"
        empty_record = b">"+UNMAPPED.encode()+b"\n"+b"N"*unmapped_length+b"\n"
        out.write(ordinary_record)
        out.write(b">"+REVERSE.encode()+b"\n")
        end = length
        while end:
            start = max(0,end-wa.CHUNK)
            source.seek(len(header)+start)
            data = source.read(end-start)
            if len(data)!=end-start:
                raise wa.ExperimentError("truncated reverse-complement source")
            out.write(data.translate(wa.RC)[::-1])
            end = start
        out.write(b"\n"+empty_record+b">"+FORWARD.encode()+b"\n")
        source.seek(len(header))
        remaining = length
        while remaining:
            data = source.read(min(wa.CHUNK,remaining))
            if not data:
                raise wa.ExperimentError("truncated forward identity source")
            out.write(data); remaining -= len(data)
        out.write(b"\n")
        normal.write(ordinary_record+empty_record)
    return {"length":length,"target":str(reference),"query":str(query),"ordinary_query":str(ordinary),
        "ordinary_start":ordinary_start,"ordinary_length":ordinary_length,"unmapped_length":unmapped_length,
        "query_order":list(QUERY_ORDER),"source_sha256":{p.name:wa.sha256(p) for p in (reference,query,ordinary)},
        "scope":"deterministic_simple_identity_not_customer_data_or_general_DP_oracle"}


def small_bytes(path):
    with Path(path).open("rb") as source:
        data = source.read(MAX_SMALL_FILE+1)
    if len(data)>MAX_SMALL_FILE:
        raise wa.ExperimentError("ordinary native control unexpectedly exceeds its small-file bound")
    return data


def audit_attempt(path,expected_status):
    path = Path(path)
    receipt = json.loads(path.read_text())
    log = nf.inspect_stderr(path.parent/"native.stderr")
    execution = receipt["execution"]
    if (json.loads((path.parent/"native.execution.json").read_text())!=execution
            or json.loads((path.parent/"native.command.json").read_text())!=execution["command"]):
        raise wa.ExperimentError("native attempt receipt differs from its actual command/execution files")
    command = execution["command"]
    rest = command[4:]
    if rest[:1]==["-f"]:
        if len(rest)<2 or not rest[1].isdigit() or not 1<=int(rest[1])<=wa.INT32_MAX:
            raise wa.ExperimentError("native attempt has an invalid inherited threshold")
        rest = rest[2:]
    if (command[1:4]!=["-c","-x","asm10"] or len(rest)!=6
            or rest[0]!="-t" or not rest[1].isdigit() or int(rest[1])<1 or rest[2]!="-o"
            or Path(rest[3]).resolve()!=(path.parent/"native.partial.paf").resolve()):
        raise wa.ExperimentError("native attempt changed original -c asm10 parameters or skipped input")
    if (receipt["status"]!=expected_status or nf.classify(receipt["execution"],log)!=expected_status
            or receipt["stderr_sha256"]!=wa.sha256(path.parent/"native.stderr")
            or receipt.get("partial_PAF_reused") is not False):
        raise wa.ExperimentError("native attempt receipt does not match its actual exit/assertion/log")
    paf = Path(receipt["path"])
    if receipt["paf_sha256"] is not None and (not paf.is_file() or wa.sha256(paf)!=receipt["paf_sha256"]):
        raise wa.ExperimentError("native attempt PAF changed from its completed/failure receipt")
    if receipt.get("paf_usable")!=(expected_status=="native_success"):
        raise wa.ExperimentError("failed native partial output is being treated as usable")
    return receipt


def view_rows(path,fixture,*,private,ordinary_native):
    """Exact analytic identity geometry/path; NOT arbitrary whole-query DP proof."""
    length = fixture["length"]
    queries = {ORDINARY:{"length":fixture["ordinary_length"]},REVERSE:{"length":length},
               UNMAPPED:{"length":fixture["unmapped_length"]},FORWARD:{"length":length}}
    targets = {TARGET:{"length":length}}
    seen,normal,details = [],bytearray(),{}
    with Path(path).open("rb") as source:
        while raw := source.readline(sr.MAX_PAF_LINE+1):
            if len(seen)>=MAX_ROWS:
                raise wa.ExperimentError("unexpected extra candidate rows in the clean identity control")
            name = sr.validate_row(raw,queries,targets,set(QUERY_ORDER),"native")
            fields = raw.decode("ascii").rstrip("\n").split("\t")
            if name==UNMAPPED or name in seen:
                raise wa.ExperimentError("empty query emitted a row or identity candidate was duplicated")
            seen.append(name)
            if name==ORDINARY:
                size,start = fixture["ordinary_length"],fixture["ordinary_start"]
                expected = [name,str(size),"0",str(size),"+",TARGET,str(length),str(start),str(start+size),str(size),str(size)]
                if fields[:11]!=expected:
                    raise wa.ExperimentError("ordinary native identity geometry differs from its generated source interval")
                normal.extend(raw)
                continue
            strand = "-" if name==REVERSE else "+"
            expected = [name,str(length),"0",str(length),strand,TARGET,str(length),"0",str(length),
                        str(length),str(length),"60" if private else "255"]
            if fields[:12]!=expected:
                raise wa.ExperimentError("long identity geometry, strand, statistics or confidence differs from its analytic contract")
            tags = {}
            for field in fields[12:]:
                key = field.split(":",1)[0]
                if key in tags:
                    raise wa.ExperimentError("duplicate identity PAF tag")
                tags[key] = field
            cigar = tags.get("cg","")[5:]
            parts = [(int(m[1]),m[2]) for m in sr.CIGAR.finditer(cigar)]
            if (not parts or "".join(f"{n}{op}" for n,op in parts)!=cigar
                    or any(op!="=" or n>wa.LIMIT for n,op in parts) or sum(n for n,_ in parts)!=length
                    or tags.get("NM")!="NM:i:0" or tags.get("nn")!="nn:i:0" or "AS" in tags):
                raise wa.ExperimentError("long identity path is not a complete bounded-chunk exact match")
            if private:
                expected_tags = {"ms":f"ms:i:{length}","tp":"tp:A:P","rl":"rl:i:0"}
                if any(tags.get(k)!=v for k,v in expected_tags.items()):
                    raise wa.ExperimentError("private identity native metadata differs from its clean-path contract")
            elif any(key in tags for key in ("ms","cm","s1","s2","tp","rl","zd")):
                raise wa.ExperimentError("public long recovery unexpectedly promoted native confidence/metadata")
            details[name] = {"strand":strand,"logical_exact_match_bases":length,"encoded_items":len(parts),
                             "mapq":int(fields[11]),"CIGAR_logical_over_28bit":length>wa.LIMIT,
                             "row_sha256":hashlib.sha256(raw).hexdigest()}
    expected_order = [n for n in QUERY_ORDER if n!=UNMAPPED]
    if seen!=expected_order or bytes(normal)!=ordinary_native:
        raise wa.ExperimentError("original query ordering or byte-identical ordinary native output was not preserved")
    return {"ordered_queries":seen,"ordinary_bytes_preserved":True,"unmapped_rows":0,
            "long_identity_rows":details,"sha256":wa.sha256(Path(path))}


def audit_selective(report,root,fixture,bundle,ordinary_native):
    if fixture["length"]!=LENGTH or LENGTH<=wa.LIMIT:
        raise wa.ExperimentError("real long control cannot accept a shortened fixture")
    if (report.get("routing_mode")!="exact_assertion_whole_record_isolation"
            or report.get("index_policy")!="original_default_no_I_override" or report.get("index_part_count")!=1
            or report.get("recovered_query_part_cells")!=2 or report.get("partial_PAF_reused") is not False
            or report.get("original_inputs_unchanged") is not True or report.get("production_ready") is not False
            or report.get("native_evaluation",{}).get("native_confidence_promoted") is not False):
        raise wa.ExperimentError("actual selective-entry routing/withholding contract was not exercised")
    if (report.get("original_chain_state_helper",{}).get("sha256")!=bundle["sha256"]
            or report["original_chain_state_helper"].get("manifest_sha256")!=bundle["manifest_sha256"]):
        raise wa.ExperimentError("actual recovery did not use the required unchanged companion bundle")
    audit_attempt(root/"original-native/native-attempt.json","target_assertion")
    counts = {ORDINARY:1,REVERSE:1,UNMAPPED:0,FORWARD:1}
    for key in ("combination","native_evaluation_combination"):
        combined = report[key]
        if (combined.get("all_cells_completed") is not True or combined.get("original_cells")!=4
                or combined.get("native_cells")!=2 or combined.get("recovered_cells")!=2
                or combined.get("rows_by_query")!=counts or combined.get("partial_PAF_reused") is not False):
            raise wa.ExperimentError("native/empty/recovered query cells are missing, duplicated or skipped")
    if len(report["parts"])!=1 or report["parts"][0]["status"]!="all_groups_completed":
        raise wa.ExperimentError("real long control did not complete its original index part")
    recovered,native = {},{}
    for row in report["parts"][0]["attempts"]:
        receipt = audit_attempt(row["attempt_receipt"],row["status"])
        if len(row["queries"])!=1:
            if row["status"]!="target_assertion":
                raise wa.ExperimentError("mixed identity control did not exercise expected binary isolation")
            continue
        name = row["queries"][0]
        if name in LONG_NAMES:
            if row["status"]!="target_assertion" or name in recovered:
                raise wa.ExperimentError("long query was not actually an asserting singleton")
            recovery = row["recovery"]
            directory = Path(row["attempt_receipt"]).parent.parent/"recovery"
            witness_path = directory/"long-operation-witness.json"
            witness = json.loads(witness_path.read_text())
            if (wa.sha256(witness_path)!=recovery["long_operation_witness_sha256"]
                    or witness!=recovery["long_operation_witness"] or witness["query"]!=name
                    or witness["first_overflow_witness"]["operation"]!="M"
                    or witness["first_overflow_witness"]["logical_length"]!=LENGTH):
                raise wa.ExperimentError("actual recovery lacks its original-anchor-supported overlong-match witness")
            guidance_path = directory/"guidance.json"
            if wa.sha256(guidance_path)!=recovery["guidance_sha256"]:
                raise wa.ExperimentError("long recovery guidance evidence changed")
            guidance = json.loads(guidance_path.read_text())
            bridge = guidance["native_recovery"]
            if (guidance["native_chain_state"]["helper"]["sha256"]!=bundle["sha256"]
                    or bridge.get("raw_overlap_consistency_checked") is not True
                    or bridge.get("public_confidence_withheld") is not True
                    or not bridge["selection"].get("native_decisions_applied")):
                raise wa.ExperimentError("real long recovery did not execute seam evidence and native selection")
            pair = recovery["native_evaluation_pair"]
            checked = ne.validate_pair(pair["public_path"],pair["path"],public_sha256=pair["public_sha256"],
                evaluated_sha256=pair["sha256"],validator=lambda raw:sr.validate_row(raw,{name:{"length":LENGTH}},
                    {TARGET:{"length":LENGTH}},{name},"risk"))
            if checked["rows"]!=1:
                raise wa.ExperimentError("clean long identity did not retain exactly one paired path")
            recovered[name] = {"witness":witness,"paired_rows":checked["rows"],
                               "public_sha256":checked["public_sha256"],"private_sha256":checked["sha256"]}
        elif name in (ORDINARY,UNMAPPED):
            if row["status"]!="native_success" or name in native:
                raise wa.ExperimentError("ordinary/unmapped input was not completed natively")
            data = small_bytes(receipt["path"])
            if data!=(ordinary_native if name==ORDINARY else b""):
                raise wa.ExperimentError("native singleton bytes differ from the independent ordinary control")
            native[name] = {"status":"native_success","paf_sha256":receipt["paf_sha256"]}
        else:
            raise wa.ExperimentError("foreign query in real assertion isolation")
    if set(recovered)!=LONG_NAMES or set(native)!={ORDINARY,UNMAPPED}:
        raise wa.ExperimentError("both long strands and both ordinary/empty singleton controls are required")
    public = root/"reference.candidate.experimental.paf"
    private = Path(report["native_evaluation"]["path"])
    if wa.sha256(public)!=report["output_sha256"] or wa.sha256(private)!=report["native_evaluation"]["sha256"]:
        raise wa.ExperimentError("final selective outputs changed from their producer hashes")
    public_view = view_rows(public,fixture,private=False,ordinary_native=ordinary_native)
    private_view = view_rows(private,fixture,private=True,ordinary_native=ordinary_native)
    for name,source in recovered.items():
        if (public_view["long_identity_rows"][name]["row_sha256"]!=source["public_sha256"]
                or private_view["long_identity_rows"][name]["row_sha256"]!=source["private_sha256"]):
            raise wa.ExperimentError("merged long PAF bytes differ from their paired source cells")
    return {"recovered":recovered,"native":native,"public":public_view,"private":private_view,
        "helper_sha256":bundle["sha256"],"actual_assertion_recovery_executed":True,
        "both_long_strands_equal_simple_identity_contract":True,"native_ordinary_and_empty_cells_preserved":True}


def experiment(args):
    root = args.out.resolve()
    if not root.parent.is_dir() or root.exists() or args.out.is_symlink():
        raise wa.ExperimentError("real long control requires a fresh directory under an existing parent")
    if any((p/".prepare_lib").exists() or (p/"run_all.sh").exists() for p in (root.parent,*root.parent.parents)):
        raise wa.ExperimentError("real long control must remain outside prepared/customer workspaces")
    if args.threads<1 or args.timeout<1 or args.memory_gib<0 or LENGTH<=wa.LIMIT:
        raise wa.ExperimentError("invalid bounds or a shortened non-long control")
    mm = shutil.which(args.minimap2)
    if not mm:
        raise wa.ExperimentError("unchanged minimap2 is unavailable")
    mm = str(Path(mm).resolve())
    tool_hash = wa.sha256(Path(mm))
    if subprocess.check_output([mm,"--version"],text=True,timeout=10).strip()!="2.31-r1302":
        raise wa.ExperimentError("real long control requires unchanged pinned minimap2 2.31-r1302")
    bundle = nst.validate_bundle(args.native_state_bundle)
    before = {**control.sources(),Path(__file__).name:wa.sha256(Path(__file__))}
    def unchanged():
        now = {**control.sources(),Path(__file__).name:wa.sha256(Path(__file__))}
        if (now!=before or wa.sha256(Path(mm))!=tool_hash or wa.sha256(Path(bundle["path"]))!=bundle["sha256"]
                or wa.sha256(Path(bundle["manifest_path"]))!=bundle["manifest_sha256"]):
            raise wa.ExperimentError("real long control source/tool/helper changed; attribution invalidated")
    root.mkdir(mode=0o700)
    report = {"schema":1,"status":"running","production_ready":False,"customer_validated":False,
        "scope":"real_single_part_selective_simple_identity_not_general_DP_equivalence",
        "tool":{"path":mm,"sha256":tool_hash,"version":"2.31-r1302"},"helper":bundle,"sources_sha256":before,
        "actual_assertion_recovery_executed":False,"whole_query_dp_equivalence_certified":False,
        "default_multipart_context_executed":False,"grt_final_path_tested":False,"AS_compared":False,
        "native_confidence_promoted":False,"customer_run_sh_resume_tested":False}
    wa.write_json(root/"long-identity.json",report)
    with control.cancellation_guard() as cancelled:
        try:
            fixture = write_fixtures(root/"inputs")
            report["fixture"] = fixture
            wa.write_json(root/"long-identity.json",report)
            unchanged()
            options = argparse.Namespace(target=Path(fixture["target"]),query=Path(fixture["query"]),out=root/"selective",
                minimap2=mm,threads=args.threads,timeout=args.timeout,memory_gib=args.memory_gib,
                native_state_bundle=Path(bundle["manifest_path"]).parent)
            selective = sr.experiment(options)
            if cancelled["signal"] is not None:
                raise KeyboardInterrupt("real long control cancelled; do not start ordinary baseline")
            unchanged()
            if (selective.get("routing_mode")!="exact_assertion_whole_record_isolation"
                    or selective.get("index_part_count")!=1):
                raise wa.ExperimentError("actual long assertion/isolation did not occur; no ordinary baseline started")
            context = json.loads((options.out/"index-context.json").read_text())
            if (len(context["parts"])!=1 or context.get("index_policy")!="original_default_no_I_override"
                    or wa.sha256(options.out/"index-context.json")!=selective["index_catalog_sha256"]):
                raise wa.ExperimentError("real long control lost its single DEFAULT index context binding")
            part = context["parts"][0]
            if (part["records"]!=[{"name":TARGET,"length":LENGTH}]
                    or part["mid_occ"]!=selective["shared_mid_occ"]):
                raise wa.ExperimentError("real long control changed original target membership or shared threshold")
            index = Path(part["path"])
            if wa.sha256(index)!=part["sha256"]:
                raise wa.ExperimentError("original default index part changed before ordinary control")
            baseline = root/"ordinary.native.paf"
            baseline_execution = wa.run_command([mm,"-c","-x","asm10","-f",str(part["mid_occ"]),"-t","1","-o",str(baseline),
                str(index),fixture["ordinary_query"]],root,"ordinary-baseline",args.timeout,args.memory_gib)
            if cancelled["signal"] is not None:
                raise KeyboardInterrupt("real long ordinary baseline cancelled")
            if nf.classify(baseline_execution,nf.inspect_stderr(root/"ordinary-baseline.stderr"))!="native_success":
                raise wa.ExperimentError("independent ordinary control did not complete natively")
            ordinary = small_bytes(baseline)
            if not ordinary:
                raise wa.ExperimentError("independent ordinary control is unexpectedly empty")
            report["comparison"] = audit_selective(selective,options.out,fixture,bundle,ordinary)
            if (fixture["source_sha256"]!={p.name:wa.sha256(p) for p in (root/"inputs").iterdir()}
                    or wa.sha256(index)!=part["sha256"]):
                raise wa.ExperimentError("real long input/index bytes changed during comparison")
            unchanged()
            report.update(status="equal_on_simple_long_identity_contract_not_production_acceptance",
                          actual_assertion_recovery_executed=True,ordinary_baseline_sha256=wa.sha256(baseline),
                          selective_receipt_sha256=wa.sha256(options.out/"selective-reference.json"))
        except BaseException as exc:
            interrupted = isinstance(exc,KeyboardInterrupt) or cancelled["signal"] is not None
            report.update(status="interrupted" if interrupted else "refused_or_failed",error=f"{type(exc).__name__}: {exc}",
                          actual_assertion_recovery_executed=False)
            if interrupted and not isinstance(exc,KeyboardInterrupt):
                raise KeyboardInterrupt("real long control cancelled") from exc
            raise
        finally:
            wa.write_json(root/"long-identity.json",report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--minimap2",default="minimap2")
    parser.add_argument("--native-state-bundle",type=Path,default=None)
    parser.add_argument("--threads",type=int,default=2)
    parser.add_argument("--timeout",type=int,default=21600)
    parser.add_argument("--memory-gib",type=int,default=0)
    parser.add_argument("--execute",action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status":"plan_only","production_ready":False,"output":str(args.out),
            "long_query_bases_each":LENGTH,"long_strands":["+","-"],"native_controls":[ORDINARY,UNMAPPED],
            "query_order":list(QUERY_ORDER),"actual_assertion_recovery_executed":False,
            "prebuilt_pinned_companion_required":True,"no_files_or_programs_started":True,
            "note":"Later execution creates >810 MB of input plus retained indexes/spools/evidence; no shortened fixture option."},indent=2))
        return 0
    try:
        report = experiment(args)
    except KeyboardInterrupt:
        return 130
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print(json.dumps({"status":"refused_or_failed","error":str(exc),"production_ready":False}))
        return 2
    print(json.dumps({key:report[key] for key in ("status","actual_assertion_recovery_executed","production_ready")},indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
