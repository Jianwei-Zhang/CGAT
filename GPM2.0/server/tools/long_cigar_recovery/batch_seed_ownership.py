"""One bounded native CN pass for ALL retained original chains of one query.

Source groups are matched by complete original geometry/count, never last PAF
row or window cm/s1. Native count cuts use ORIGINAL anchor endpoints, including
bad-end/ignored anchors. Exact-path support identifies fragment candidates; local
split evidence remains mandatory. No coverage or whole-query DP certificate.
"""
from __future__ import annotations

from bisect import bisect_right
import hashlib
import math
import os
from pathlib import Path
import stat
import time

import stream_seed_trace as st
import trace_memory as tm
from windowed_alignment import ExperimentError


def _prefix(row):
    qs,_ = st.oriented_query_interval(row)
    return row["target"],row["strand"],qs,row["target_start"]


def _signature(row):
    qs,qe = st.oriented_query_interval(row)
    return row["target"],row["strand"],qs,qe,row["target_start"],row["target_end"],row["minimizers"]


def collect(path,plans,*,query_name,query_length,target_lengths,expected_sha256,budget=None):
    budget = budget or st.TraceBudget()
    budget.validate()
    if not isinstance(plans,dict) or len(plans)>100000:
        raise ExperimentError("native anchor plans exceed supported size")
    signatures,by_prefix,prepared = {},{},{}
    for key,plan in plans.items():
        coarse,fragments = plan["coarse"],plan["fragments"]
        if (coarse["query"] != query_name or coarse["query_length"] != query_length
                or not fragments or len(fragments)>100000 or _signature(coarse) in signatures):
            raise ExperimentError("missing/ambiguous original chain or unsupported fragment count")
        signatures[_signature(coarse)] = key
        ordered = sorted(fragments,key=lambda r:(r["target_start"],r["target_end"],r["id"]))
        if any(any(row[k] != coarse[k] for k in ("query","query_length","target","target_length","strand")) for row in ordered):
            raise ExperimentError("fragment plan mixes original query/target/strand identities")
        starts,prefix_max,maximum = [],[],0
        for row in ordered:
            starts.append(row["target_start"])
            maximum = max(maximum,row["target_end"])
            prefix_max.append(maximum)
        exact = []
        for row in ordered:
            q,_ = st.oriented_query_interval(row)
            t = row["target_start"]
            runs = []
            for n,op in row["ops"]:
                if op == "=":
                    if runs and runs[-1][1] == q and runs[-1][2] == t-q:
                        runs[-1] = (runs[-1][0],q+n,t-q)
                    else:
                        runs.append((q,q+n,t-q))
                q += n if op in "=XI" else 0
                t += n if op in "=XD" else 0
            exact.append({"starts":[a for a,_,_ in runs],"runs":runs})
        prepared[key] = {"rows":ordered,"starts":starts,"prefix_max":prefix_max,"exact":exact,
                         "qintervals":[st.oriented_query_interval(r) for r in ordered],
                         "boundaries":sorted([(r["target_start"],i,"starts_count") for i,r in enumerate(ordered)]+
                                             [(r["target_end"],i,"ends_count") for i,r in enumerate(ordered)])}
        by_prefix.setdefault(_prefix(coarse),[]).append(key)
    if any(len(keys)>128 for keys in by_prefix.values()):
        raise ExperimentError("ambiguous original chain-prefix fanout exceeds supported size")
    memory = tm.process_plan(budget.process_memory_bytes,budget.read_buffer_bytes)
    started = time.monotonic()
    digest = hashlib.sha256()
    found = {}
    current = None
    seen = done = False
    byte_count = line_count = seed_count = group_count = 0

    def finish():
        if current is None:
            return
        t,q,span = current["first"]
        lt,lq,_ = current["last"]
        signature = (*current["pair"],q+1-span,lq+1,t+1-span,lt+1,current["count"])
        key = signatures.get(signature)
        if key is None:
            return
        if key in found:
            raise ExperimentError("multiple native CN groups match one original chain")
        ownership = current["owners"].get(key)
        if ownership is None or current["non_monotonic"]:
            raise ExperimentError("original native chain is not a monotonic source partition")
        plan = prepared[key]
        selected = [i for i,n in enumerate(ownership["exact_counts"]) if n]
        if not selected or len(selected)>64:
            raise ExperimentError("native anchor partition lacks supported recovered paths")
        rows = [plan["rows"][i] for i in selected]
        if any(a["target_start"]>b["target_start"] or st.oriented_query_interval(a)[0]>st.oriented_query_interval(b)[0]
               for a,b in zip(rows,rows[1:])):
            raise ExperimentError("seed-supported fragments are not in native collinear chain order")
        # mm_split_reg cuts at the last ORIGINAL anchor endpoint before the
        # aligned head end; cnt/score retain bad-end/ignored anchors as well.
        # Requiring every original seed inside final DP rectangles would lose
        # those native counts and incorrectly reject ordinary trimming.
        ends = [ownership["ends_count"][i] if ownership["ends_count"][i] is not None else current["count"] for i in selected]
        cuts = [0,*ends[:-1],current["count"]]
        counts = [b-a for a,b in zip(cuts,cuts[1:])]
        if any(n<=0 for n in counts) or sum(counts)!=current["count"]:
            raise ExperimentError("shared/ambiguous recovered paths do not form native sequential target-end cuts")
        first_before = ownership["starts_count"][selected[0]]
        found[key] = {"chain_id":current["id"],"fragment_ids":[r["id"] for r in rows],
                      "anchor_counts":counts,"original_anchor_count":current["count"],
                      "exact_path_anchor_counts":[ownership["exact_counts"][i] for i in selected],
                      "source_anchors_before_first_path":current["count"] if first_before is None else first_before,
                      "source_anchors_after_last_path":current["count"]-ends[-1],
                      "anchors_without_exact_path_support":ownership["unsupported"],
                      "target_end_cut_counts":ends[:-1],"partition_model":"native_original_anchor_target_end_cuts",
                      "unseeded_fragment_ids":[r["id"] for r,n in zip(plan["rows"],ownership["exact_counts"]) if not n]}

    fd = os.open(path,os.O_RDONLY|os.O_NONBLOCK)
    with os.fdopen(fd,"rb",buffering=memory["selected_buffer_bytes"]) as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size>budget.max_bytes:
            raise ExperimentError("native anchor trace must be a bounded regular file")
        while raw := source.readline(budget.max_line_bytes+1):
            byte_count += len(raw); line_count += 1
            if (byte_count>budget.max_bytes or line_count>budget.max_lines or len(raw)>budget.max_line_bytes
                    or not raw.endswith(b"\n") or time.monotonic()-started>budget.timeout_seconds):
                raise ExperimentError("native anchor trace incomplete or exceeds processing limits")
            digest.update(raw)
            if not raw.startswith((b"QR\t",b"QT\t",b"CN\t")):
                if raw.startswith((b"QR",b"QT",b"CN")):
                    raise ExperimentError("malformed native anchor trace marker")
                continue
            try:
                fields = raw.decode("ascii").rstrip("\n").split("\t")
                if fields[0] == "QR":
                    if seen or fields != ["QR",query_name,"0",str(query_length)]:
                        raise ExperimentError("native anchor query scope mismatch")
                    seen = True
                    continue
                if fields[0] == "QT":
                    if (not seen or done or len(fields)!=4 or fields[1:3] != [query_name,"0"]
                            or not math.isfinite(float(fields[3])) or float(fields[3])<0):
                        raise ExperimentError("native anchor query-end scope mismatch")
                    done = True
                    continue
                if len(fields)!=8 or not seen or done:
                    raise ExperimentError("native anchor row outside complete query scope")
                cid,target,t,strand,q,span,delta = int(fields[1]),fields[2],int(fields[3]),fields[4],int(fields[5]),int(fields[6]),int(fields[7])
            except (ValueError,UnicodeError) as exc:
                raise ExperimentError("invalid native anchor trace field") from exc
            if (not 0<=cid<=2147483647 or strand not in ("+","-") or target not in target_lengths
                    or not 1<=span<=255 or min(t,q)<span-1 or t>=target_lengths[target] or q>=query_length):
                raise ExperimentError("invalid original native seed coordinates")
            if current is None or current["id"] != cid:
                if current is not None and cid <= current["id"]:
                    raise ExperimentError("native CN groups are not contiguous/increasing")
                finish()
                keys = by_prefix.get((target,strand,q+1-span,t+1-span),[])
                current = {"id":cid,"pair":(target,strand),"first":(t,q,span),"last":None,"count":0,
                           "non_monotonic":False,"owners":{key:{"exact_counts":[0]*len(prepared[key]["rows"]),
                               "starts_count":[None]*len(prepared[key]["rows"]),"ends_count":[None]*len(prepared[key]["rows"]),
                               "next_boundary":0,"unsupported":0} for key in keys}}
                group_count += 1
            if current["pair"] != (target,strand):
                raise ExperimentError("native chain changes target/strand inside one CN group")
            if current["last"] and (t<=current["last"][0] or q<=current["last"][1]):
                current["non_monotonic"] = True
            current["last"] = (t,q,span)
            current["count"] += 1
            seed_count += 1
            for key,owner in current["owners"].items():
                plan = prepared[key]
                boundaries = plan["boundaries"]
                while owner["next_boundary"]<len(boundaries) and boundaries[owner["next_boundary"]][0]<=t:
                    _,i,kind = boundaries[owner["next_boundary"]]
                    owner[kind][i] = current["count"]-1
                    owner["next_boundary"] += 1
                at = bisect_right(plan["starts"],t+1-span)-1
                supported = False
                while at>=0 and plan["prefix_max"][at]>=t+1:
                    row = plan["rows"][at]
                    qs,qe = plan["qintervals"][at]
                    if row["target_end"]>=t+1 and qs<=q+1-span and q<qe:
                        evidence = plan["exact"][at]
                        run = bisect_right(evidence["starts"],q+1-span)-1
                        if run>=0 and q<evidence["runs"][run][1] and t-q==evidence["runs"][run][2]:
                            owner["exact_counts"][at] += 1
                            supported = True
                    at -= 1
                if not supported:
                    owner["unsupported"] += 1
        finish()
        if (st.stat_identity(before) != st.stat_identity(os.fstat(source.fileno()))
                or st.stat_identity(before) != st.stat_identity(Path(path).stat()) or byte_count!=before.st_size):
            raise ExperimentError("native anchor trace changed during ownership scan")
    if not seen or not done or digest.hexdigest()!=expected_sha256 or set(found)!=set(plans):
        raise ExperimentError("native trace identity/query-end/original-chain ownership is incomplete")
    return {"chains":found,"trace_sha256":digest.hexdigest(),"bytes":byte_count,"lines":line_count,
            "seed_rows":seed_count,"chain_groups":group_count,"memory_plan":memory,
            "source_scans":1,"native_dp_split_events_certified":False,"production_ready":False}
