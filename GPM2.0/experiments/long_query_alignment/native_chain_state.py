"""Acquire original pre-DP fields from a pinned, unmodified-library companion.

Internal hypothesis-branch code, not a customer command or minimap2 replacement.
The maintainer bundles the helper in advance; never compile/download at job time.
No state is guessed from CN coordinates or window PAF. Native metadata are bound
against the ORIGINAL whole-record/index-part chain PAF from the installed tool.
Acquisition is not post-DP reconstruction, MAPQ recovery or customer acceptance.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
import stat

import build_native_chain_state as build
import minimap_index_context as mic
import post_dp_selection as ps
import windowed_alignment as wa

MAX_STATE_BYTES = 256*1024**2
MAX_LINE_BYTES = 64*1024
MAX_TRACE_BYTES = 16*1024**3
FIELDS = ("order","id","parent","anchor_offset","anchor_count","chain_score","original_chain_score",
          "query_start","query_end","target_id","target_start","target_end","reverse","native_hash",
          "subscore","subcount","matches","block_length","chain_mapq","split","inv","sam_primary",
          "seg_split","split_inv","is_alt","strand_retained","is_spliced","divergence")
FLAGS = ("reverse","inv","sam_primary","seg_split","split_inv","is_alt","strand_retained","is_spliced")


def validate_bundle(directory=None):
    directory = Path(directory) if directory is not None else build.default_bundle()
    manifest = directory/build.MANIFEST
    if not manifest.is_file():
        raise wa.ExperimentError("branch artifact lacks its prebuilt native-state companion; maintainer must supply the bundle, not ask customer for configuration/compiler")
    with manifest.open("rb") as source:
        raw = source.read(1024**2+1)
    if len(raw)>1024**2:
        raise wa.ExperimentError("native-state companion receipt exceeds supported size")
    try:
        info = json.loads(raw)
    except (ValueError,UnicodeError) as exc:
        raise wa.ExperimentError("invalid native-state companion build receipt") from exc
    required = {"schema":1,"status":"built_unvalidated","protocol":1,"version":build.VERSION,
                "preset":"asm10","upstream_commit":build.UPSTREAM_COMMIT,"binary":build.BINARY,
                "platform":build.host_platform()}
    if type(info) is not dict or any(info.get(k) != v for k,v in required.items()):
        raise wa.ExperimentError("native-state companion version/source/platform receipt mismatch")
    sources = info.get("source_files_sha256",{})
    if type(sources) is not dict or any(sources.get(k.removesuffix("_sha256")) != v
            for k,v in ps.UPSTREAM.items() if k != "version"):
        raise wa.ExperimentError("native-state companion upstream-source binding mismatch")
    binary = directory/build.BINARY
    if (not binary.is_file() or binary.is_symlink() or not stat.S_ISREG(binary.stat().st_mode)
            or not os.access(binary,os.X_OK) or wa.sha256(binary) != info.get("binary_sha256")
            or wa.sha256(Path(__file__).with_suffix(".c")) != info.get("helper_source_sha256")):
        raise wa.ExperimentError("native-state companion missing, stale, non-executable or changed")
    licenses = info.get("third_party_licenses_sha256",{})
    if type(licenses) is not dict or set(licenses)-{"ZLIB_LICENSE_AND_HEADER.txt"}:
        raise wa.ExperimentError("native-state companion has unsupported third-party license files")
    for name,digest in licenses.items():
        path = directory/name
        if not path.is_file() or path.is_symlink() or wa.sha256(path)!=digest:
            raise wa.ExperimentError("native-state companion third-party license is missing or changed")
    return {"path":str(binary.resolve()),"sha256":info["binary_sha256"],"manifest_path":str(manifest.resolve()),
            "manifest_sha256":hashlib.sha256(raw).hexdigest(),"upstream_commit":build.UPSTREAM_COMMIT,
            "platform":info["platform"],"production_ready":False,"execution_validated":False,
            "third_party_licenses_sha256":licenses,"runtime_abi":info.get("runtime_abi")}


def _lines(handle):
    size = 0
    while raw := handle.readline(MAX_LINE_BYTES+1):
        size += len(raw)
        if size > MAX_STATE_BYTES or len(raw)>MAX_LINE_BYTES or not raw.endswith(b"\n") or b"\r" in raw:
            raise wa.ExperimentError("native-state protocol exceeds limits or has an incomplete line")
        try:
            yield raw[:-1].decode("ascii"),raw
        except UnicodeError as exc:
            raise wa.ExperimentError("native-state protocol must be ASCII") from exc


def _number(text,low=0,high=wa.INT32_MAX):
    try:
        value = int(text)
    except ValueError as exc:
        raise wa.ExperimentError("invalid native-state integer") from exc
    if str(value) != text or not low <= value <= high:
        raise wa.ExperimentError("native-state integer exceeds its source representation")
    return value


def parse_state(path, *, query_name, query_length, context, expected_paf):
    """Strict complete one-query protocol; capture, do not reset IDs/counters."""
    before = wa.fingerprint(path)
    if before["size"] > MAX_STATE_BYTES:
        raise wa.ExperimentError("native-state protocol file too large")
    with path.open("rb") as source:
        lines = iter(_lines(source))
        def take():
            try:
                return next(lines)
            except StopIteration as exc:
                raise wa.ExperimentError("incomplete native-state protocol") from exc
        first,_ = take()
        expected_header = ["H","cgat-chain-state","1",build.VERSION,"asm10",str(context["mid_occ"]),
                           str(context["part_index"]),"19","19"]
        if first.split("\t") != expected_header:
            raise wa.ExperimentError("native-state protocol header/context mismatch")
        targets = context["records"]
        for i,target in enumerate(targets):
            row,_ = take()
            if row.split("\t") != ["T",str(i),target["name"],str(target["length"])]:
                raise wa.ExperimentError("native-state target order/membership mismatch")
        row,_ = take()
        query = row.split("\t")
        if len(query) != 6 or query[:3] != ["Q",query_name,str(query_length)]:
            raise wa.ExperimentError("native-state original query identity mismatch")
        repetitive = _number(query[3],high=query_length)
        fragment_gap = _number(query[4])
        count = _number(query[5],high=ps.MAX_CANDIDATES)
        if len(expected_paf) != count:
            raise wa.ExperimentError("native-state chain count differs from installed minimap2")
        records = []
        for i in range(count):
            row,_ = take()
            values = row.split("\t")
            if len(values) != 1+len(FIELDS) or values[0] != "R":
                raise wa.ExperimentError("native-state record lacks required original fields")
            state = {}
            for field,text in zip(FIELDS,values[1:]):
                if field == "divergence":
                    try:
                        if re.fullmatch(r"-?0x[0-9a-f]+(?:\.[0-9a-f]+)?p[+-][0-9]+",text) is None:
                            raise ValueError("native divergence must retain its exact hexadecimal encoding")
                        value = float.fromhex(text)
                    except ValueError as exc:
                        raise wa.ExperimentError("invalid native divergence encoding") from exc
                    if not math.isfinite(value) or not -1 <= value <= 1:
                        raise wa.ExperimentError("invalid original native divergence")
                else:
                    value = _number(text,low=-1 if field == "parent" else 0,
                                    high=2**32-1 if field == "native_hash" else wa.INT32_MAX)
                state[field] = value
            if (state["order"] != i or any(state[f] not in (0,1) for f in FLAGS)
                    or state["split"] not in range(4) or state["chain_mapq"] > 255
                    or not 0 <= state["target_id"] < len(targets)
                    or not 0 <= state["query_start"] < state["query_end"] <= query_length
                    or not 0 <= state["target_start"] < state["target_end"] <= targets[state["target_id"]]["length"]
                    or state["matches"] > state["block_length"]):
                raise wa.ExperimentError("native-state record geometry/flags are invalid")
            paf,raw = take()
            if not paf.startswith("P\t") or raw[2:] != expected_paf[i]:
                raise wa.ExperimentError("native-state chain PAF differs from the installed minimap2; do not guess metadata")
            f = paf[2:].split("\t")
            primary = state["id"] == state["parent"]
            core = [query_name,str(query_length),str(state["query_start"]),str(state["query_end"]),
                    "-" if state["reverse"] else "+",targets[state["target_id"]]["name"],
                    str(targets[state["target_id"]]["length"]),str(state["target_start"]),str(state["target_end"]),
                    str(state["matches"]),str(state["block_length"]),str(state["chain_mapq"])]
            tags = {v.split(":",1)[0]:v for v in f[12:]}
            if (f[:12] != core or len(tags) != len(f)-12
                    or any(k in tags for k in ("AS","ms","cg"))
                    or tags.get("tp") != "tp:A:"+("P" if primary else "S")
                    or tags.get("s1") != f"s1:i:{state['chain_score']}"
                    or tags.get("cm") != f"cm:i:{state['anchor_count']}"
                    or tags.get("rl") != f"rl:i:{repetitive}"
                    or (primary and tags.get("s2") != f"s2:i:{state['subscore']}")):
                raise wa.ExperimentError("native-state record is inconsistent with its own native chain PAF")
            state.update(target=targets[state["target_id"]]["name"],
                         paf_sha256=hashlib.sha256(raw[2:]).hexdigest())
            records.append(state)
        footer,_ = take()
        if footer != f"END\t{count}" or next(lines,None) is not None:
            raise wa.ExperimentError("native-state footer/trailing data mismatch")
    if wa.fingerprint(path) != before:
        raise wa.ExperimentError("native-state protocol changed during parsing")
    ids = {r["id"] for r in records}
    if len(ids) != len(records) or any(r["parent"] not in ids for r in records):
        raise wa.ExperimentError("native-state original parent IDs are missing or duplicated")
    return {"query":query_name,"query_length":query_length,"repetitive_length":repetitive,
            "fragment_gap":fragment_gap,"records":records,"external_chain_paf_equal":True,
            "native_pre_dp_state_acquired":True,"post_dp_state_certified":False,
            "mapq_reconstructed":False,"production_ready":False,"execution_validated":False}


def trace_receipt(path,query_name,query_length):
    """Stream/hash and require complete query markers; NOT seed ownership proof."""
    before = wa.fingerprint(path)
    if before["size"] > MAX_TRACE_BYTES:
        raise wa.ExperimentError("native-state anchor trace exceeds file budget")
    digest = hashlib.sha256()
    seen = ended = False
    bytes_read = 0
    with path.open("rb") as source:
        while raw := source.readline(MAX_LINE_BYTES+1):
            if len(raw)>MAX_LINE_BYTES or not raw.endswith(b"\n"):
                raise wa.ExperimentError("incomplete or oversized native-state trace line")
            bytes_read += len(raw)
            if bytes_read > before["size"]:
                raise wa.ExperimentError("native-state trace grew during reading")
            digest.update(raw)
            if raw.startswith(b"QR\t"):
                if seen or raw != f"QR\t{query_name}\t0\t{query_length}\n".encode("ascii"):
                    raise wa.ExperimentError("native-state trace query mismatch")
                seen = True
            elif raw.startswith(b"QT\t"):
                fields = raw.decode("ascii").rstrip("\n").split("\t")
                try:
                    elapsed = float(fields[3]) if len(fields) == 4 else -1
                except ValueError as exc:
                    raise wa.ExperimentError("invalid native-state query-end marker") from exc
                if not seen or ended or fields[1:3] != [query_name,"0"] or not math.isfinite(elapsed) or elapsed < 0:
                    raise wa.ExperimentError("native-state trace query-end mismatch")
                ended = True
            elif raw.startswith(b"CN\t") and (not seen or ended):
                raise wa.ExperimentError("native-state seed trace outside original query scope")
    if not seen or not ended or bytes_read != before["size"] or wa.fingerprint(path) != before:
        raise wa.ExperimentError("native-state trace incomplete or changed")
    return {"sha256":digest.hexdigest(),"bytes":before["size"],"query_end_observed":True,
            "anchor_ownership_validated":False}


def collect(query,target,context,tool_sha256,bundle,expected_paf,root,*,timeout,memory_gib):
    """One original query at a time, existing task budget; no retry or skipping."""
    index = mic.validate_part_context(context,reference_sha256=target.identity["sha256"],
        tool_sha256=tool_sha256,preset="asm10",target_records=target.records)
    verified = validate_bundle(bundle)
    root.mkdir(parents=True,exist_ok=False)
    before = {"index":wa.fingerprint(index),"binary":wa.fingerprint(Path(verified["path"])),
              "spool":wa.fingerprint(Path(query.handle.name)),"paf_sha256":wa.sha256(expected_paf)}
    by_query = {name:[] for name in query.records}
    with expected_paf.open("rb") as inp:
        total = 0
        for number,(_,raw) in enumerate(_lines(inp),1):
            name = raw.split(b"\t",1)[0].decode("ascii")
            if name not in by_query or len(by_query[name]) >= ps.MAX_CANDIDATES:
                raise wa.ExperimentError("unexpected original query or excessive coarse candidates")
            total += 1
            if total > 1_000_000:
                raise wa.ExperimentError("coarse candidate ledger exceeds bounded supported rows")
            by_query[name].append((number,raw))
    ledger = root/"original-chain-state.pending.jsonl"
    query_reports = []
    with ledger.open("x") as out:
        for i,(name,record) in enumerate(query.records.items()):
            directory = root/f"query-{i:06d}"
            directory.mkdir(exist_ok=False)
            command = [verified["path"],str(index),str(context["mid_occ"]),str(context["part_index"]),
                       name,str(query.handle.name),str(record["offset"]),str(record["length"])]
            wa.run_command(command,directory,"native-state",timeout,memory_gib,max_file_bytes=MAX_TRACE_BYTES)
            state = parse_state(directory/"native-state.stdout",query_name=name,query_length=record["length"],
                                context=context,expected_paf=[raw for _,raw in by_query[name]])
            trace = trace_receipt(directory/"native-state.stderr",name,record["length"])
            digest = hashlib.sha256()
            for start in range(0,record["length"],wa.CHUNK):
                digest.update(query.fetch(name,start,min(record["length"],start+wa.CHUNK)))
            state.update(index_sha256=context["sha256"],original_part_index=context["part_index"],
                         query_source_sha256=query.identity["sha256"],reference_sha256=target.identity["sha256"],
                         query_sequence_sha256=digest.hexdigest(),trace=trace,
                         protocol_sha256=wa.sha256(directory/"native-state.stdout"),helper=verified)
            for row,(chain_row,_) in zip(state.pop("records"),by_query[name]):
                out.write(json.dumps({"kind":"original_chain","query":name,"chain_row":chain_row,**row},separators=(",", ":"))+"\n")
            out.write(json.dumps({"kind":"query_receipt",**state},separators=(",", ":"))+"\n")
            query_reports.append({"query":name,"records":len(by_query[name]),
                                  "directory":str(directory),"trace_sha256":trace["sha256"]})
    if (wa.fingerprint(index) != before["index"] or wa.sha256(index) != context["sha256"]
            or wa.fingerprint(Path(verified["path"])) != before["binary"]
            or wa.sha256(Path(verified["path"])) != verified["sha256"]
            or wa.fingerprint(Path(query.handle.name)) != before["spool"]
            or wa.sha256(expected_paf) != before["paf_sha256"] or not query.unchanged() or not target.unchanged()
            or wa.sha256(Path(verified["manifest_path"])) != verified["manifest_sha256"]):
        raise wa.ExperimentError("native-state input/index/tool/receipt changed during acquisition")
    final = root/"original-chain-state.jsonl"
    ledger.replace(final)
    return {"path":str(final),"sha256":wa.sha256(final),"queries":query_reports,
            "index_sha256":context["sha256"],"chain_paf_sha256":before["paf_sha256"],"helper":verified,
            "native_pre_dp_state_acquired":True,"external_chain_paf_equal":True,
            "post_dp_state_certified":False,"mapq_reconstructed":False,"production_ready":False,
            "execution_validated":False,"customer_validated":False}
