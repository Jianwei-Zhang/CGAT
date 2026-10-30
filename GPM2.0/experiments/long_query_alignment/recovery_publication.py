"""Internal publication contract for supported original-state CIGAR recovery.

No customer flag/configuration. A completed original-chain bridge and paired
native API selection are mandatory; unknown-confidence experimental PAF is NEVER
published. This contract does not assert arbitrary whole-query DP/AS equality.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
import stat

import native_chain_state as nst
import native_evaluation as ne
import native_first as nf
import windowed_alignment as wa

POLICY = "original-chain-native-selection-v1"
PROOF = "publication-proof.json"
MAX_PROOF_BYTES = 1024*1024


def require(condition,message):
    if not condition:
        raise wa.ExperimentError("recovery publication refused: "+message)


def regular_under(path,root):
    path,root = Path(path),Path(root).resolve()
    require(not path.is_symlink() and path.is_file(),"missing or linked evidence file")
    resolved = path.resolve()
    require(root in resolved.parents and stat.S_ISREG(resolved.stat().st_mode),"evidence escaped its private recovery scope")
    return resolved


def read_json(path,root,*,max_bytes=MAX_PROOF_BYTES,expected_type=dict):
    path = regular_under(path,root)
    with path.open("rb") as source:
        raw = source.read(max_bytes+1)
    require(len(raw)<=max_bytes,"oversized publication metadata")
    value = json.loads(raw)
    require(type(value) is expected_type,"publication metadata has the wrong container type")
    return value



def protocol_line(lines):
    try:
        return next(lines)[0]
    except StopIteration as exc:
        raise wa.ExperimentError("recovery publication refused: truncated native protocol") from exc


def bind_native_rows(pair,selection,directory,part,query_length):
    """Bind retained PAF metadata to actual native input AND stdout, not MAPQ labels."""
    selected = selection["selected"]
    indices = [row["input_index"] for row in selected]
    require(len(indices)==len(set(indices)),"native selector duplicated an input state")
    wanted,states = set(indices),{}
    with (directory/"selection.input.tsv").open("rb") as source:
        lines = iter(nst._lines(source))
        header = protocol_line(lines).split()
        require(len(header)==4 and header[0]=="CGAT_POST_DP_V1" and header[1]==str(query_length),
                "native selector query context differs")
        repetitive,count = [nst._number(text) for text in header[2:]]
        require(0<=repetitive<=query_length and 1<=count<=100000 and all(0<=i<count for i in indices),"native input count/scope differs")
        for i in range(count):
            values = [nst._number(text,high=2**32-1) for text in protocol_line(lines).split()]
            require(len(values)==18 and values[0]==i,"native input state is incomplete or reordered")
            if i in wanted:
                states[i] = values
        require(protocol_line(lines)==f"END {count}" and next(lines,None) is None,"native input is truncated or has extra rows")
    with (directory/"selection.stdout").open("rb") as source:
        lines = iter(nst._lines(source))
        expected = ["S","cgat-post-dp","1","2.31-r1302","asm10",str(query_length),str(repetitive),str(count),str(len(selected))]
        require(protocol_line(lines).split("\t")==expected,"native selector stdout header differs")
        for row in selected:
            values = [row[k] for k in ("input_index","id","parent","subscore","subcount","dp_max2","mapq")]
            expected = ["R",*[str(v) for v in values],str(int(row["sam_primary"]))]
            require(protocol_line(lines).split("\t")==expected,"private decisions differ from actual native stdout")
        require(protocol_line(lines)==f"END\t{len(selected)}" and next(lines,None) is None,"native stdout is incomplete")
    with Path(pair["path"]).open("rb") as source:
        for selected_row in selected:
            raw = source.readline(ne.MAX_LINE+1)
            fields,tags = ne._fields(raw)
            values = states[selected_row["input_index"]]
            target_id = values[3]
            require(0<=target_id<len(part["records"]),"native target identity is out of range")
            target = part["records"][target_id]
            core = [str(query_length),str(values[1]),str(values[2]),"-" if values[6] else "+",target["name"],
                    str(target["length"]),str(values[4]),str(values[5]),str(values[10]),str(values[11]),str(selected_row["mapq"])]
            require(fields[1:12]==core,"published path/MAPQ differs from selected native input state")
            key = re.fullmatch(r"chain-([1-9][0-9]*)-fragment-([0-9]+)",selected_row["key"])
            require(key is not None,"native decision lacks its original chain identity")
            primary = selected_row["id"]==selected_row["parent"]
            expected_tags = {"zg":"zg:i:"+key[1],"cm":f"cm:i:{values[9]}","s1":f"s1:i:{values[7]}",
                             "ms":f"ms:i:{values[13]}","rl":f"rl:i:{repetitive}","tp":"tp:A:P" if primary else "tp:A:S"}
            require(all(tags.get(k)==v for k,v in expected_tags.items()),"published native chain/score/parent metadata differs")
            require(tags.get("s2")==f"s2:i:{selected_row['subscore']}" if primary else "s2" not in tags,
                    "published native subscore differs")
        require(not source.read(1),"private native view has extra unselected candidates")


def verify_attempt(path,root,status,*,tool,target,query,mid_occ=None):
    require(status in ("native_success","target_assertion"),"not a usable native completion or exact assertion")
    path = regular_under(path,root)
    receipt = read_json(path,root)
    execution = receipt.get("execution",{})
    require(type(execution) is dict and type(execution.get("returncode")) is int,"invalid native execution receipt")
    parsed = nf.inspect_stderr(path.parent/"native.stderr")
    require(receipt.get("status")==status and nf.classify(execution,parsed)==status
            and receipt.get("partial_PAF_reused") is False
            and receipt.get("paf_usable") is (status=="native_success")
            and receipt.get("stderr_sha256")==wa.sha256(path.parent/"native.stderr"),"native completion/abort/log evidence differs")
    command = execution.get("command",[])
    inherited = ["-f",str(mid_occ)] if mid_occ is not None else []
    require(type(command) is list and len(command)==10+len(inherited) and command[:4]==[tool,"-c","-x","asm10"]
            and command[4:4+len(inherited)]==inherited,"native flags/preset/tool changed")
    rest = command[4+len(inherited):]
    require(rest[0]=="-t" and str(rest[1]).isdigit() and int(rest[1])>=1 and rest[2:]==[
        "-o",str(path.parent/"native.partial.paf"),str(target),str(query)],"native input/output command changed")
    require(read_json(path.parent/"native.execution.json",root)==execution
            and read_json(path.parent/"native.command.json",root,expected_type=list)==command,"native command/execution files disagree")
    expected_path = path.parent/("native.complete.paf" if status=="native_success" else "native.partial.paf")
    require(receipt.get("path")==str(expected_path),"native output ownership differs")
    if status=="native_success":
        require(wa.sha256(regular_under(expected_path,root))==receipt.get("paf_sha256"),"native-complete bytes changed")
    return receipt


def capture_leaf(name,part,root,result,witness,pair,*,query_sha256,reference_sha256,bundle):
    """Record bounded facts from the JUST completed in-process native bridge.

    The large guidance object is already held by its producer; do not reload
    an entire arbitrary-size report at publication. Hash its actual artifacts
    and keep a small completion receipt. No failed PAF body is read or reused.
    """
    root = Path(root).resolve()
    abi = bundle.get("runtime_abi") or {}
    require(abi.get("legacy_2_17_checked") is True,"companion lacks a checked portable build")
    original = result.get("native_chain_state",{})
    recovered = result.get("native_recovery",{})
    states,queries = original.get("queries",[]),recovered.get("queries",[])
    require(result.get("status")=="validated_experimental_guidance" and result.get("original_inputs_unchanged") is True,
            "bridge did not complete on unchanged sources")
    require(result.get("index_sha256")==part["sha256"] and result["target"]["sha256"]==reference_sha256
            and result["tool"]["sha256"]==part["tool_sha256"],"bridge source/tool/index identity differs")
    require(original.get("native_pre_dp_state_acquired") is True and original.get("external_chain_paf_equal") is True
            and original.get("helper",{}).get("sha256")==bundle["sha256"],"original native state was not independently bound")
    require(len(states)==len(queries)==1 and states[0]["query"]==queries[0]["query"]==name
            and states[0]["records"]==queries[0]["source_chains"]>=1,
            "not every original source chain was accounted for")
    require(recovered.get("status")=="native_selected_experimental_unknown_confidence"
            and recovered.get("raw_overlap_consistency_checked") is True
            and recovered.get("public_confidence_withheld") is True
            and recovered.get("mapq_computed_for_private_evaluation") is True
            and recovered.get("selection",{}).get("native_decisions_applied") is True,
            "native seam/selection completion is missing")
    selected = queries[0]
    require(1<=selected["selected"]<=selected["second_filter_passed"]<=selected["first_filter_passed"]<=selected["recovered_fragments"]
            and selected["recovered_fragments"]>=selected["source_chains"] and selected["selected"]==pair["rows"],
            "native candidate accounting is incomplete")
    overflow = witness.get("first_overflow_witness",{})
    require(witness.get("status")=="recovered_path_supports_long_CIGAR_hypothesis" and witness.get("query")==name
            and witness.get("scope")=="original-chain-supported_pre_filter_paths"
            and overflow.get("operation") in ("M","D") and type(overflow.get("logical_length")) is int
            and overflow["logical_length"]>wa.LIMIT and bool(overflow.get("original_chain_rows")),
            "no original-chain-supported overflowing operation")
    require(pair["part_index"]==part["part_index"] and pair["query"]==name
            and pair.get("ordered_candidate_path_equal") is True
            and recovered["native_evaluated_sha256"]==pair["sha256"]
            and result["output_sha256"]==pair["public_sha256"],"paired paths lost native producer binding")
    files = {}
    def capture(path,expected=None):
        path = regular_under(path,root)
        before = wa.fingerprint(path)
        digest = wa.sha256(path)
        require(wa.fingerprint(path)==before,"evidence changed while hashing")
        require(expected is None or digest==expected,"native evidence changed before receipt capture")
        files[path.relative_to(root).as_posix()] = digest
    for path in (root/"guidance.json",root/"native-recovery/native-recovery.json",root/"long-operation-witness.json",
                 root/"native-recovery/anchors-000000.json"):
        capture(path)
    capture(Path(original["path"]),original["sha256"])
    capture(Path(states[0]["directory"])/"native-state.stderr",states[0]["trace_sha256"])
    capture(root/"native-recovery/recovered-states-000000.jsonl",selected["recovered_states_sha256"])
    receipt_path = Path(selected["native_selection_receipt"])
    receipt = read_json(receipt_path,root,max_bytes=nst.MAX_STATE_BYTES)
    require(receipt.get("parent_replay_equal") is True and receipt.get("native_selection_evaluated") is True
            and receipt.get("mapq_computed_from_supplied_state") is True
            and receipt.get("helper",{}).get("sha256")==bundle["sha256"]
            and len(receipt.get("selected",[]))==pair["rows"],"native selector completion is missing")
    directory = receipt_path.parent
    execution = read_json(directory/"selection.execution.json",root)
    command = [bundle["path"],"--select",str(directory/"selection.input.tsv")]
    require(execution.get("returncode")==0 and "interrupted" not in execution and execution.get("command")==command,
            "native selector execution is incomplete or changed")
    require(read_json(directory/"selection.command.json",root,expected_type=list)==command,"native selector command receipt differs")
    bind_native_rows(pair,receipt,directory,part,recovered["selection"]["queries"][name]["length"])
    capture(receipt_path)
    capture(directory/"selection.execution.json")
    capture(directory/"selection.command.json")
    capture(directory/"selection.input.tsv",receipt["input_sha256"])
    capture(directory/"selection.stdout",receipt["output_sha256"])
    return {"schema":1,"policy":POLICY,"query":name,"part_index":part["part_index"],
        "query_length":recovered["selection"]["queries"][name]["length"],
        "global_query_sha256":query_sha256,"reference_sha256":reference_sha256,"index_sha256":part["sha256"],
        "tool_sha256":part["tool_sha256"],"helper_sha256":bundle["sha256"],"helper_manifest_sha256":bundle["manifest_sha256"],
        "source_chains":states[0]["records"],"recovered_fragments":selected["recovered_fragments"],
        "selected_rows":pair["rows"],"paired_paths":pair,"evidence_files_sha256":files,
        "whole_query_dp_equivalence_certified":False,"AS_reconstructed":False,
        "confidence_model":"native_API_on_original-chain-supported_recovered_states"}


def check_leaf(recovery,root,part,report,bundle,row_validator):
    root = Path(root).resolve()
    proof_path = regular_under(recovery["publication_proof_path"],root)
    require(wa.sha256(proof_path)==recovery["publication_proof_sha256"],"completion receipt changed")
    proof = read_json(proof_path,root)
    require(proof.get("schema")==1 and proof.get("policy")==POLICY and proof.get("query")==recovery["query"]
            and proof.get("part_index")==part["part_index"]
            and proof.get("global_query_sha256")==report["query"]["sha256"]
            and proof.get("reference_sha256")==report["reference"]["sha256"]
            and proof.get("tool_sha256")==report["tool"]["sha256"]
            and proof.get("index_sha256")==part["sha256"]
            and proof.get("helper_sha256")==bundle["sha256"]
            and proof.get("helper_manifest_sha256")==bundle["manifest_sha256"],"completion receipt belongs to another run/source/helper")
    files = proof.get("evidence_files_sha256")
    require(type(files) is dict and 10<=len(files)<=32,"incomplete completion evidence inventory")
    required = {"guidance.json","long-operation-witness.json","native-recovery/native-recovery.json",
        "native-recovery/anchors-000000.json","native-recovery/recovered-states-000000.jsonl",
        "native-chains/query-000000/native-state.stderr",
        *["native-recovery/query-000000/selection."+suffix for suffix in
          ("receipt.json","execution.json","command.json","input.tsv","stdout")]}
    require(required<=files.keys() and len([name for name in files if name.startswith("native-chains/") and name.endswith(".jsonl")])==1,
            "required original-state/native-decision evidence was omitted")
    for name,digest in files.items():
        path = regular_under(root/name,root)
        require(path.relative_to(root).as_posix()==name and wa.sha256(path)==digest,"completion evidence changed")
    pair = proof["paired_paths"]
    require(pair==recovery["native_evaluation_pair"] and pair["rows"]==recovery["rows"]==proof["selected_rows"],
            "completion paths/candidate count changed")
    for key in ("public_path","path"):
        regular_under(pair[key],root)
    targets = {r["name"]:{"length":r["length"]} for r in part["records"]}
    name = proof["query"]
    validator = lambda raw:row_validator(raw,{name:{"length":proof["query_length"]}},targets,{name},"risk")
    checked = ne.validate_pair(pair["public_path"],pair["path"],public_sha256=pair["public_sha256"],
                               evaluated_sha256=pair["sha256"],validator=validator)
    require(checked["rows"]==pair["rows"] and checked["rows"]>0,"recovered candidate set is empty or changed")
    selector = root/"native-recovery/query-000000"
    decision = read_json(selector/"selection.receipt.json",root,max_bytes=nst.MAX_STATE_BYTES)
    require(decision.get("native_selection_evaluated") is True and decision.get("parent_replay_equal") is True
            and decision.get("helper",{}).get("sha256")==bundle["sha256"]
            and decision.get("helper",{}).get("manifest_sha256")==bundle["manifest_sha256"],"private metadata lost native producer identity")
    bind_native_rows(pair,decision,selector,part,proof["query_length"])
    return proof


def admit(report,root,*,bundle,row_validator):
    """Require every original part/query cell and every real asserting leaf."""
    root = Path(root).resolve()
    public,private = report.get("combination",{}),report.get("native_evaluation_combination",{})
    require(report.get("routing_mode")=="exact_assertion_whole_record_isolation"
            and report.get("original_native",{}).get("status")=="target_assertion"
            and report.get("length_is_not_a_recovery_trigger") is True
            and report.get("native_row_bytes_preserved") is True
            and report.get("partial_PAF_reused") is False and report.get("original_inputs_unchanged") is True,
            "not a completed exact-assertion recovery")
    original = verify_attempt(root/"original-native/native-attempt.json",root,"target_assertion",
        tool=report["tool"]["path"],target=report["reference"]["source"],query=report["query"]["source"])
    require(original==report["original_native"],"original native receipt changed")
    catalog_path = regular_under(root/"index-context.json",root)
    require(wa.sha256(catalog_path)==report["index_catalog_sha256"],"index catalog changed")
    # Catalog membership is bounded by the original FASTA record limits, not by
    # native PAF optional-body size. This is not a new normal-path PAF parser.
    catalog = json.loads(catalog_path.read_bytes())
    parts = catalog["parts"]
    names = list(public.get("rows_by_query",{}))
    require(bool(names) and len(parts)==report.get("index_part_count")==len(report.get("parts",[])),"original cells/parts are missing")
    total = len(names)*len(parts)
    for view in (public,private):
        require(view.get("all_cells_completed") is True and view.get("original_cells")==total
                and view.get("native_cells",-1)+view.get("recovered_cells",-1)==total
                and view.get("native_row_bytes_preserved") is True and view.get("partial_PAF_reused") is False,
                "incomplete native/recovered cell assembly")
    require(public["native_cells"]==private["native_cells"] and public["recovered_cells"]==private["recovered_cells"]
            ==report.get("recovered_query_part_cells") and public["recovered_cells"]>0
            and public["rows_by_query"]==private["rows_by_query"] and public["sources"]==private["sources"],
            "public/native-evaluated complete cell sets differ")
    proofs,pairs,expected_sources = [],{},[]
    for context,isolated in zip(parts,report["parts"]):
        part_index = context["part_index"]
        attempts = isolated.get("attempts",[])
        require(isolated.get("status")=="all_groups_completed" and isolated.get("part_index")==part_index
                and 1<=len(attempts)<=2*len(names)-1 and attempts[0]["queries"]==names,"incomplete original-part isolation tree")
        completed = set()
        leaves = 0
        for number,row in enumerate(attempts):
            group = row["queries"]
            require(row.get("group")==number and len(group)==len(set(group)) and set(group)<=set(names),"foreign/duplicate isolation node")
            require(row.get("source",{}).get("queries")==group and row["source"].get("raw_records_preserved") is True,
                    "isolation source group changed")
            reused = row.get("reused_original_assertion") is True
            require(not reused or number==0 and part_index==0 and len(group)>1,"original abort reused outside the first root")
            receipt = verify_attempt(row["attempt_receipt"],root,row["status"],tool=report["tool"]["path"],
                target=report["reference"]["source"] if reused else context["path"],query=row["source"]["path"],
                mid_occ=None if reused else context["mid_occ"])
            if row["status"]=="target_assertion" and len(group)>1:
                children = [r["queries"] for r in attempts if r["parent_group"]==number]
                cut = len(group)//2
                require(children==[group[:cut],group[cut:]],"asserting group was skipped instead of split")
                continue
            require(row["status"] in ("native_success","target_assertion") and not completed.intersection(group),"invalid/overlapping completed cells")
            completed.update(group)
            if row["status"]=="target_assertion":
                require(len(group)==1 and not row.get("reused_original_assertion"),"original group assertion was reused for a singleton")
                receipt_path = regular_under(row["attempt_receipt"],root)
                recovery = row["recovery"]
                leaf_root = receipt_path.parent.parent/"recovery"
                proof = check_leaf(recovery,leaf_root,context,report,bundle,row_validator)
                require(proof["query"]==group[0],"singleton recovery query changed")
                key = (part_index,group[0]);require(key not in pairs,"duplicate recovered cell")
                pairs[key] = proof["paired_paths"];proofs.append(proof);leaves+=1
                expected_sources.append({"path":proof["paired_paths"]["public_path"],"sha256":proof["paired_paths"]["public_sha256"],
                    "route":"recovered","queries":group,"parts":[part_index]})
            else:
                expected_sources.append({"path":receipt["path"],"sha256":receipt["paf_sha256"],
                    "route":"native","queries":group,"parts":[part_index]})
        require(completed==set(names) and leaves==isolated["assertion_leaves"],"original query cells were skipped")
    require(public["sources"]==expected_sources,"assembly sources are not exactly the completed native/recovered leaves")
    replacements = private.get("evaluated_replacements",[])
    require(len(proofs)==public["recovered_cells"] and len(replacements)==len(pairs)
            and { (r["part_index"],r["query"]):r for r in replacements }==pairs,"private assembly lost a recovered cell binding")
    for name,digest in (("reference.candidate.experimental.paf",report["output_sha256"]),
                        ("reference.native-evaluated.experimental.paf",report["native_evaluation"]["sha256"])):
        require(wa.sha256(regular_under(root/name,root))==digest,"complete assembled output changed")
    output = root/"reference.native-evaluated.experimental.paf"
    return {"schema":1,"policy":POLICY,"status":"supported_recovery_admitted","path":str(output),
        "sha256":report["native_evaluation"]["sha256"],"original_cells":total,"recovered_cells":len(proofs),
        "recovered_unknown_confidence_published":False,"native_confidence_model":"native_API_on_original-chain-supported_recovered_states",
        "whole_query_dp_equivalence_certified":False,"AS_reconstructed":False,
        "customer_root_cause_confirmed":False,"leaf_proofs_sha256":[wa.sha256(Path(r["publication_proof_path"]))
            for p in report["parts"] for r in [a["recovery"] for a in p["attempts"] if "recovery" in a]]}
