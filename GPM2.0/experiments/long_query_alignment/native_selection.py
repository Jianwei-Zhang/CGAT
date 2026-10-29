"""Native post-DP selection/MAPQ for already recovered, provenance-bound state.

No DP, CIGAR encoding, source patch, candidate discovery or producer replacement.
An original index/query/anchor/path ledger must precede this API. Returning a
native MAPQ on supplied metadata is NOT certification of whole-query DP equality.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import native_chain_state as nst
import post_dp_selection as ps
import windowed_alignment as wa


FIELDS = ("query_start","query_end","target_id","target_start","target_end","reverse",
          "chain_score","original_chain_score","anchor_count","matches","block_length",
          "dp_max","dp_max0","previous_subscore","previous_subcount","previous_dp_max2","native_hash")


def write_input(path,states,dp_max0,*,query_length,repetitive_length):
    if type(query_length) is not int or not 1 <= query_length <= wa.INT32_MAX:
        raise wa.ExperimentError("native selection query length is out of bounds")
    if type(repetitive_length) is not int or not 0 <= repetitive_length <= query_length:
        raise wa.ExperimentError("native selection requires original repetitive length")
    if not isinstance(states,(list,tuple)) or any(type(r) is not ps.NativePostDpState for r in states):
        raise wa.ExperimentError("native selection requires complete typed post-DP state")
    if (len(states)>ps.MAX_CANDIDATES or len({r.key for r in states}) != len(states)
            or type(dp_max0) is not dict or set(dp_max0) != {r.key for r in states}):
        raise wa.ExperimentError("native selection state/score identities are incomplete")
    for row in states:
        row.validate(query_length)
        if type(dp_max0[row.key]) is not int or not 0 <= dp_max0[row.key] <= wa.INT32_MAX:
            raise wa.ExperimentError("native selection requires full-path local maximum")
        if row.previous_subcount > wa.INT32_MAX-len(states):
            raise wa.ExperimentError("native competitor counter could overflow")
    if type(query_length) is not int or not 1 <= query_length <= wa.INT32_MAX:
        raise wa.ExperimentError("native selection query length is out of bounds")
    with path.open("x") as out:
        out.write(f"CGAT_POST_DP_V1 {query_length} {repetitive_length} {len(states)}\n")
        for i,row in enumerate(states):
            values = {**asdict(row),"dp_max0":dp_max0[row.key]}
            out.write(" ".join(str(int(v)) for v in [i,*[values[k] for k in FIELDS]])+"\n")
        out.write(f"END {len(states)}\n")


def parse_output(path,states,replay,*,query_length,repetitive_length):
    if path.stat().st_size > nst.MAX_STATE_BYTES:
        raise wa.ExperimentError("native selection output exceeds bounded protocol size")
    before = wa.fingerprint(path)
    with path.open("rb") as source:
        lines = iter(nst._lines(source))
        def take():
            try:
                return next(lines)[0].split("\t")
            except StopIteration as exc:
                raise wa.ExperimentError("incomplete native selection output") from exc
        expected = replay["retained_candidates"]
        header = take()
        if header != ["S","cgat-post-dp","1","2.31-r1302","asm10",str(query_length),
                      str(repetitive_length),str(len(states)),str(len(expected))]:
            raise wa.ExperimentError("native selection output header/context differs from parent replay")
        original_ids = {r.key:i for i,r in enumerate(states)}
        output = []
        for i,row in enumerate(expected):
            fields = take()
            if len(fields)!=9 or fields[0] != "R":
                raise wa.ExperimentError("native selection record missing original fields")
            values = [nst._number(text) for text in fields[1:]]
            index,identifier,parent,subscore,subcount,dp_max2,mapq,sam_primary = values
            wanted = (original_ids[row["state"]["key"]],row["id"],row["parent"],row["subscore"],
                      row["subcount"],row["dp_max2"],int(row["sam_primary"]))
            if tuple(values[:6]+[sam_primary]) != wanted or not 0 <= mapq <= 60:
                raise wa.ExperimentError("native parent/retention state differs from pinned independent replay")
            if parent != identifier and mapq != 0:
                raise wa.ExperimentError("native secondary candidate has nonzero MAPQ")
            output.append({"key":states[index].key,"input_index":index,"id":identifier,"parent":parent,
                           "subscore":subscore,"subcount":subcount,"dp_max2":dp_max2,
                           "mapq":mapq,"sam_primary":bool(sam_primary)})
        if take() != ["END",str(len(expected))] or next(lines,None) is not None:
            raise wa.ExperimentError("native selection footer/trailing data differs")
    if wa.fingerprint(path) != before:
        raise wa.ExperimentError("native selection output changed while parsing")
    return output


def evaluate(states,dp_max0,*,query_length,repetitive_length,bundle,root,timeout,memory_gib):
    verified = nst.validate_bundle(bundle)
    root.mkdir(parents=True,exist_ok=False)
    input_path = root/"selection.input.tsv"
    write_input(input_path,states,dp_max0,query_length=query_length,repetitive_length=repetitive_length)
    input_hash = wa.sha256(input_path)
    # Independent parent/sort/retention port, NOT a MAPQ approximation. Keep this
    # experimental cross-check while the native backend awaits final validation.
    replay = ps.replay_post_dp_selection(states,query_length=query_length)
    wa.run_command([verified["path"],"--select",str(input_path)],root,"selection",timeout,memory_gib,
                   max_file_bytes=nst.MAX_STATE_BYTES)
    selected = parse_output(root/"selection.stdout",states,replay,
                            query_length=query_length,repetitive_length=repetitive_length)
    if (wa.sha256(input_path) != input_hash or wa.sha256(Path(verified["path"])) != verified["sha256"]
            or wa.sha256(Path(verified["manifest_path"])) != verified["manifest_sha256"]):
        raise wa.ExperimentError("native selection input/helper/source receipt changed")
    report = {"selected":selected,"input_sha256":input_hash,"output_sha256":wa.sha256(root/"selection.stdout"),
              "helper":verified,"parent_replay_equal":True,"native_selection_evaluated":True,
              "mapq_computed_from_supplied_state":True,"whole_query_dp_equivalence_certified":False,
              "production_ready":False,"execution_validated":False,"customer_validated":False}
    wa.write_json(root/"selection.receipt.json",report)
    return report
