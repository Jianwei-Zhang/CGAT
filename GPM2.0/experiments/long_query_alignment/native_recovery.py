"""Experimental bridge: original chains + owned paths -> native selection.

Replaces the legacy blanket canonical-coverage condition only when the native
ledger, complete original target-end count accounting and local split observations
are available. This is NOT a certificate of whole-query DP equivalence. Public
experimental output still withholds MAPQ/native score claims; a separate private
native-evaluated PAF is for explicit maintainer oracle/downstream validation.
"""
from __future__ import annotations

from dataclasses import asdict,replace
import json
from pathlib import Path

import batch_seed_ownership as bo
import native_chain_state as nst
import native_selection as ns
import post_dp_selection as ps
import sequential_split_witness as sw
import stream_seed_trace as st
import whole_query_scores as ws
import windowed_alignment as wa


def _json_rows(path,max_line=nst.MAX_LINE_BYTES):
    with path.open("rb") as source:
        while raw := source.readline(max_line+1):
            if len(raw)>max_line or not raw.endswith(b"\n"):
                raise wa.ExperimentError("native recovery ledger has incomplete/oversized record")
            row = json.loads(raw)
            if type(row) is not dict:
                raise wa.ExperimentError("native recovery ledger record is not an object")
            yield row


def _load_original(receipt,chains,query,target,context):
    path = Path(receipt["path"])
    if (wa.sha256(path)!=receipt["sha256"] or receipt["index_sha256"]!=context["sha256"]
            or not receipt.get("external_chain_paf_equal")):
        raise wa.ExperimentError("original-state ledger is not bound to this original index/coarse pass")
    by_row = {c.row:c for c in chains}
    originals,queries = {},{}
    for row in _json_rows(path):
        if row.get("kind") == "original_chain":
            chain = by_row.get(row.get("chain_row"))
            if chain is None or chain.row in originals:
                raise wa.ExperimentError("native chain ledger has duplicate/foreign original rows")
            actual = (row["query"],row["query_start"],row["query_end"],row["target"],row["target_start"],row["target_end"],
                      "-" if row["reverse"] else "+",row["chain_score"],row["anchor_count"])
            expected = (chain.query,chain.qs,chain.qe,chain.target,chain.ts,chain.te,chain.strand,chain.score,chain.minimizers)
            if actual!=expected or context["records"][row["target_id"]]["name"]!=chain.target:
                raise wa.ExperimentError("original chain state differs from independent coarse candidate")
            if any(row[name] for name in ("split","inv","seg_split","split_inv","is_alt","is_spliced")):
                raise wa.ExperimentError("unsupported pre-DP inversion/segment/alt/splice state")
            originals[chain.row] = row
        elif row.get("kind") == "query_receipt":
            name = row.get("query")
            if (name not in query.records or name in queries or row["query_length"]!=query.records[name]["length"]
                    or row["query_source_sha256"]!=query.identity["sha256"]
                    or row["reference_sha256"]!=target.identity["sha256"] or row["index_sha256"]!=context["sha256"]
                    or row["helper"]["sha256"]!=receipt["helper"]["sha256"]):
                raise wa.ExperimentError("native query-state receipt is foreign or duplicated")
            queries[name] = row
        else:
            raise wa.ExperimentError("unknown original-state ledger record")
    if set(originals)!=set(by_row) or set(queries)!=set(query.records):
        raise wa.ExperimentError("native recovery lacks original candidate/query state")
    directories = {r["query"]:Path(r["directory"]) for r in receipt["queries"]}
    if set(directories)!=set(queries):
        raise wa.ExperimentError("native anchor directories do not cover original queries")
    for name,directory in directories.items():
        if directory.resolve().parent!=path.parent.resolve():
            raise wa.ExperimentError("native anchor path escaped its acquisition directory")
    return originals,queries,directories


def _fragment(hit,identifier):
    return {"id":identifier,"query":hit.query,"query_length":hit.qlen,"query_start":hit.qs,"query_end":hit.qe,
            "strand":hit.strand,"target":hit.target,"target_length":hit.tlen,"target_start":hit.ts,"target_end":hit.te,"ops":hit.ops}


def _candidate(hit,chain):
    # Do not use a straight endpoint-derived diagonal corridor: cancelling
    # insertions/deletions can leave that band while retaining original anchors.
    # Only bound outer extension by pinned asm10 max_gap plus the non-HPC kmer;
    # full anchor/path evidence below decides ownership, not this prefilter.
    flank = 10000+19
    return ((hit.query,hit.target,hit.strand)==(chain.query,chain.target,chain.strand)
        and chain.qs-flank <= hit.qs < hit.qe <= chain.qe+flank
        and chain.ts-flank <= hit.ts < hit.te <= chain.te+flank
        and max(hit.qs,chain.qs)<min(hit.qe,chain.qe)
        and max(hit.ts,chain.ts)<min(hit.te,chain.te))


def _coarse(chain):
    return {"query":chain.query,"query_length":chain.qlen,"query_start":chain.qs,"query_end":chain.qe,
            "strand":chain.strand,"target":chain.target,"target_length":chain.tlen,"target_start":chain.ts,
            "target_end":chain.te,"minimizers":chain.minimizers}


def _same_shared_path(a,b):
    lo,hi = max(a.qs,b.qs),min(a.qe,b.qe)
    if lo>=hi:
        return False
    window = wa.Window(a.query,a.query,a.qlen,0,a.qlen,lo,hi)
    left,right = wa.clip_to_core(a,window),wa.clip_to_core(b,window)
    return (left is not None and right is not None and (left.qs,left.qe,left.ts,left.te,wa.join_operations(left.ops))
            ==(right.qs,right.qe,right.ts,right.te,wa.join_operations(right.ops)))


def _split_observations(raw,windows_path,hits,required,target,*,forbidden_heads=(),forbidden_tails=()):
    """Require each claimed split to be observed in TWO local native DP rows.

    Match target-forward endpoints, same original window, split head/tail flags
    and the shared actual CIGAR path. Merely finding a gap between windows is not
    an observed native split and cannot authorize score partitioning.
    """
    windows = {r["alias"]:wa.Window(**r) for r in json.loads(windows_path.read_text())}
    heads,tails = {},{}
    for identifier in {i for pair in required for i in pair}|set(forbidden_heads)|set(forbidden_tails):
        hit = hits[identifier]
        qs,qe = st.oriented_query_interval(_fragment(hit,identifier))
        pair = (hit.query,hit.target,hit.strand)
        heads.setdefault((*pair,hit.te,qe),[]).append(identifier)
        tails.setdefault((*pair,hit.ts,qs),[]).append(identifier)
    head_support,tail_support = {},{}
    with raw.open("rb") as source:
        number = 0
        while line := source.readline(ws.MAX_PAF_LINE+1):
            number += 1
            if len(line)>ws.MAX_PAF_LINE or not line.endswith(b"\n"):
                raise wa.ExperimentError("local split evidence has an incomplete/oversized PAF line")
            text = line.decode("ascii")
            all_tags = text.rstrip("\n").split("\t")[12:]
            if any(f in ("tp:A:I","tp:A:i") for f in all_tags):
                raise wa.ExperimentError("local native inversion rescue is not supported by this ordinary-chain bridge")
            tags = [f for f in all_tags if f.startswith("zd:")]
            if not tags:
                continue
            if len(tags)!=1 or tags[0] not in ("zd:i:1","zd:i:2","zd:i:3"):
                raise wa.ExperimentError("local native split flags are invalid")
            flags = int(tags[0][-1])
            mapped = wa.parse_hit(text,windows,target.records)
            window = windows[mapped.query]
            hit = wa.lift(mapped,window)
            qs,qe = st.oriented_query_interval(_fragment(hit,number))
            pair = (hit.query,hit.target,hit.strand)
            for enabled,candidates,support in ((flags&1,heads.get((*pair,hit.te,qe),[]),head_support),
                                                (flags&2,tails.get((*pair,hit.ts,qs),[]),tail_support)):
                if enabled:
                    for identifier in candidates:
                        if _same_shared_path(hit,hits[identifier]):
                            support.setdefault(identifier,{}).setdefault(window.alias,set()).add(number)
    if any(head_support.get(i) for i in forbidden_heads) or any(tail_support.get(i) for i in forbidden_tails):
        raise wa.ExperimentError("observed local native split has an unrepresented original-anchor head/tail")
    witnesses = []
    for left,right in sorted(required):
        head,tail = head_support.get(left,{}),tail_support.get(right,{})
        matched = []
        for alias in sorted(set(head)&set(tail)):
            if any(a!=b for a in head[alias] for b in tail[alias]):
                matched.append({"window":alias,"head_raw_rows":sorted(head[alias]),"tail_raw_rows":sorted(tail[alias])})
        if not matched:
            raise wa.ExperimentError("recovered discontinuity lacks an observed local native DP split boundary")
        witnesses.append({"left_fragment":left,"right_fragment":right,"observations":matched})
    return witnesses


def _paf(hit,score,*,chain_row,state,selected,split_flag,repetitive_length,with_native_metadata):
    fields = [hit.query,hit.qlen,hit.qs,hit.qe,hit.strand,hit.target,hit.tlen,hit.ts,hit.te,
              hit.matches,hit.block,selected["mapq"] if with_native_metadata else 255]
    tags = ["cg:Z:"+"".join(f"{n}{op}" for n,op in hit.ops),f"nn:i:{score.ambiguous}",
            f"NM:i:{hit.block-hit.matches+score.ambiguous}",f"zg:i:{chain_row}"]
    if with_native_metadata:
        tags += ["zp:Z:experimental-native-evaluated",f"cm:i:{state.anchor_count}",f"s1:i:{state.chain_score}",
                 f"ms:i:{score.dp_max0}",f"rl:i:{repetitive_length}","tp:A:"+("P" if selected["id"]==selected["parent"] else "S")]
        if selected["id"]==selected["parent"]:
            tags.append(f"s2:i:{selected['subscore']}")
        if split_flag:
            tags.append(f"zd:i:{split_flag}")
    else:
        tags.append("zp:Z:experimental-native-selected-unknown-confidence")
    return "\t".join(map(str,fields+tags))+"\n"


def recover(stitched,chains,output,*,query,target,context,native_receipt,bundle,chain_paf,window_root,
            window_report,root,timeout,memory_gib):
    root.mkdir(parents=True,exist_ok=False)
    if output.exists():
        raise wa.ExperimentError("native recovery requires fresh candidate output")
    inputs = {"stitched":(stitched,window_report["stitched_sha256"]),
              "raw":(window_root/"raw.windows.paf",window_report["raw_sha256"]),
              "windows":(window_root/"windows.json",window_report["windows_manifest_sha256"]),
              "window_fasta":(window_root/"windows.fa",window_report["windows_fasta_sha256"]),
              "ledger":(Path(native_receipt["path"]),native_receipt["sha256"]),
              "chain_paf":(chain_paf,native_receipt["chain_paf_sha256"]),
              "helper_binary":(Path(native_receipt["helper"]["path"]),native_receipt["helper"]["sha256"]),
              "helper_manifest":(Path(native_receipt["helper"]["manifest_path"]),native_receipt["helper"]["manifest_sha256"])}
    if any(wa.sha256(path)!=digest for path,digest in inputs.values()):
        raise wa.ExperimentError("native recovery evidence changed before bridge")
    report = {"status":"running","production_ready":False,"execution_validated":False,
              "customer_validated":False,"whole_query_dp_equivalence_certified":False}
    try:
        originals,query_states,directories = _load_original(native_receipt,chains,query,target,context)
        whole = {name:wa.Window(name,name,r["length"],0,r["length"],0,r["length"]) for name,r in query.records.items()}
        hits = {}
        with stitched.open("rb") as source:
            while line := source.readline(ws.MAX_PAF_LINE+1):
                if len(line)>ws.MAX_PAF_LINE or not line.endswith(b"\n"):
                    raise wa.ExperimentError("native recovery stitched input is incomplete/oversized")
                hit = wa.parse_hit(line.decode("ascii"),whole,target.records)
                if hit.mapq!=255 or any(f.startswith((b"AS:",b"ms:",b"s1:",b"s2:",b"tp:")) for f in line.rstrip().split(b"\t")[12:]):
                    raise wa.ExperimentError("native recovery may not inherit window scores/confidence")
                hits[len(hits)+1] = hit
        if not hits:
            raise wa.ExperimentError("empty recovered paths are not native recovery")
        assignments,required = {},set()
        forbidden_heads,forbidden_tails = set(),set()
        for name,record in query.records.items():
            plans = {}
            for chain in chains:
                if chain.query == name:
                    fragments = [_fragment(hit,i) for i,hit in hits.items() if _candidate(hit,chain)]
                    plans[chain.row] = {"coarse":_coarse(chain),"fragments":fragments}
            budget = st.TraceBudget(max_bytes=nst.MAX_TRACE_BYTES,max_lines=nst.MAX_TRACE_BYTES//8,
                                    timeout_seconds=max(120,timeout))
            proof = bo.collect(directories[name]/"native-state.stderr",plans,query_name=name,
                query_length=record["length"],target_lengths={n:r["length"] for n,r in target.records.items()},
                expected_sha256=query_states[name]["trace"]["sha256"],budget=budget)
            wa.write_json(root/f"anchors-{len(assignments):06d}.json",proof)
            assignments[name] = proof["chains"]
            for partition in proof["chains"].values():
                ids = partition["fragment_ids"]
                required.update(zip(ids,ids[1:]))
                if partition["source_anchors_after_last_path"]>=3:
                    forbidden_heads.add(ids[-1])
                if partition["source_anchors_before_first_path"]:
                    forbidden_tails.add(ids[0])
        report["local_split_observations"] = _split_observations(inputs["raw"][0],inputs["windows"][0],hits,required,target,
            forbidden_heads=forbidden_heads,forbidden_tails=forbidden_tails)
        score_cache = {}
        kept_count = 0
        query_coverage,target_coverage = {},{}
        evaluated_path = root/"native-evaluated.experimental.paf"
        evaluated_pending = root/"native-evaluated.pending.paf"
        pending = root/"selected.pending.paf"
        query_reports = []
        with pending.open("x") as public,evaluated_pending.open("x") as evaluated:
            for name,record in query.records.items():
                candidates = []
                for chain_row,partition in sorted(assignments[name].items(),key=lambda item:originals[item[0]]["order"]):
                    native = originals[chain_row]
                    counts,ids = partition["anchor_counts"],partition["fragment_ids"]
                    if len(ids)>1 and counts[-1]<3:
                        raise wa.ExperimentError("split tail lacks the native min_cnt required for an actual split")
                    accounting = sw.sequential_scores(native["chain_score"],counts) if len(ids)>1 else {
                        "reconstructed_chain_scores":[native["chain_score"]],"split_steps":[]}
                    for j,(identifier,count,chain_score) in enumerate(zip(ids,counts,accounting["reconstructed_chain_scores"])):
                        hit = hits[identifier]
                        if identifier not in score_cache:
                            score_cache[identifier] = ws.score_path(hit,query,target,key=str(identifier),index_sha256=context["sha256"])
                        score = replace(score_cache[identifier],key=f"chain-{chain_row}-fragment-{j}")
                        candidates.append({"hit":hit,"id":identifier,"chain_row":chain_row,"native":native,"count":count,
                            "chain_score":chain_score,"score":score,"split_flag":0 if len(ids)==1 else 1 if j==0 else 2 if j==len(ids)-1 else 3})
                state_path = root/f"recovered-states-{len(query_reports):06d}.jsonl"
                with state_path.open("x") as state_output:
                    for r in candidates:
                        reason = ("min_cnt" if r["count"]<3 else "min_matches" if r["score"].matches<40
                                  else "min_dp_max" if r["score"].dp_max0<200 else "first_filter_pass")
                        state_output.write(json.dumps({"chain_row":r["chain_row"],"fragment_id":r["id"],
                            "anchor_count":r["count"],"chain_score":r["chain_score"],"split_flag":r["split_flag"],
                            "score0":r["native"]["original_chain_score"],"native_hash":r["native"]["native_hash"],
                            "first_filter_status":reason,"path_score":asdict(r["score"])},separators=(",", ":"))+"\n")
                first = [r for r in candidates if r["count"]>=3 and r["score"].matches>=40 and r["score"].dp_max0>=200]
                ranking = ws.replay_native_rank_adjustment([r["score"] for r in first],query_length=record["length"])
                corrected = {r["key"]:r["dp_max"] for r in ranking["scores"]}
                final = [r for r in first if corrected[r["score"].key]>=200]
                # Pre-DP producer verified p==NULL. Each native mm_align1 /
                # split creates a fresh zeroed DP extra; dp_max2 is therefore
                # deterministically zero BEFORE post-DP parent assignment.
                states = [ps.NativePostDpState(key=r["score"].key,query_start=r["hit"].qs,query_end=r["hit"].qe,
                    target_id=r["native"]["target_id"],target_start=r["hit"].ts,target_end=r["hit"].te,reverse=r["hit"].strand=="-",
                    chain_score=r["chain_score"],original_chain_score=r["native"]["original_chain_score"],anchor_count=r["count"],
                    matches=r["score"].matches,block_length=r["score"].block_length,dp_max=corrected[r["score"].key],
                    previous_subscore=r["native"]["subscore"],previous_subcount=r["native"]["subcount"],previous_dp_max2=0,
                    native_hash=r["native"]["native_hash"]) for r in final]
                decision = ns.evaluate(states,{r["score"].key:r["score"].dp_max0 for r in final},query_length=record["length"],
                    repetitive_length=query_states[name]["repetitive_length"],bundle=bundle,root=root/f"query-{len(query_reports):06d}",
                    timeout=timeout,memory_gib=memory_gib)
                if decision["helper"]["sha256"]!=native_receipt["helper"]["sha256"]:
                    raise wa.ExperimentError("native selector differs from the original-state producer")
                by_key = {r["score"].key:(r,s) for r,s in zip(final,states)}
                for selected in decision["selected"]:
                    candidate,state = by_key[selected["key"]]
                    hit,score = candidate["hit"],candidate["score"]
                    kwargs = dict(chain_row=candidate["chain_row"],state=state,selected=selected,split_flag=candidate["split_flag"],
                                  repetitive_length=query_states[name]["repetitive_length"])
                    public.write(_paf(hit,score,with_native_metadata=False,**kwargs))
                    evaluated.write(_paf(hit,score,with_native_metadata=True,**kwargs))
                    kept_count += 1
                    query_coverage.setdefault(name,[]).append((hit.qs,hit.qe))
                    target_coverage.setdefault(hit.target,[]).append((hit.ts,hit.te))
                query_reports.append({"query":name,"source_chains":len(assignments[name]),"recovered_fragments":len(candidates),
                    "first_filter_passed":len(first),"second_filter_passed":len(final),"selected":len(decision["selected"]),
                    "ranking":ranking,"recovered_states_sha256":wa.sha256(state_path),"native_selection_receipt":str(root/f"query-{len(query_reports):06d}"/"selection.receipt.json")})
        if (not kept_count or any(wa.sha256(path)!=digest for path,digest in inputs.values())
                or not query.unchanged() or not target.unchanged()):
            raise wa.ExperimentError("no retained risk candidates or native recovery evidence changed")
        evaluated_pending.replace(evaluated_path)
        pending.replace(output)
        report.update(status="native_selected_experimental_unknown_confidence",candidate_rows=kept_count,
            output_sha256=wa.sha256(output),native_evaluated_paf=str(evaluated_path),native_evaluated_sha256=wa.sha256(evaluated_path),
            queries=query_reports,selection={"kept_rows":kept_count,"native_decisions_applied":True,
                "mapq":"unknown_255","dp_ranking_reconstructed":False,
                "queries":{n:{"length":r["length"],**wa.coverage(query_coverage.get(n,[]))} for n,r in query.records.items()},
                "targets":{n:{"length":r["length"],**wa.coverage(target_coverage.get(n,[]))} for n,r in target.records.items()}},
            mapq_computed_for_private_evaluation=True,public_confidence_withheld=True)
    except BaseException as exc:
        report.update(status="failed",error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        wa.write_json(root/"native-recovery.json",report)
    return report
