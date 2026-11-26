"""Step 2: distinguish guiding alignments, admitted sequence and intermediate coordinates."""
import json
from collections import defaultdict
from pathlib import PurePosixPath

from lgz_core.common import stable_id
from lgz_core.stage_alignment import member_source_interval
from report_inventory import obj, physical
from report_q0_tracks import label
from report_repair_story import repair_stage, sealed_rows
from run_orchestration import file_signature, sha256_file
from workspace_layout import WorkspaceLayout


def _bound(layout, rel, seals, expected):
    if not rel or not expected or expected not in (seals.get(rel), seals.get(layout.relative(rel))):
        raise ValueError("unbound structural artifact")
    path = physical(layout.root, layout.relative(rel))
    before = file_signature(path)
    if sha256_file(path) != expected:
        raise ValueError("changed structural artifact")
    return path, before


def _picks(layout, seals, rows_by_id, members, base, number, out):
    plans = defaultdict(list)
    for row in sealed_rows(layout, f"{base}/refill_round{number}_candidates.tsv", seals):
        eid = row["event_id"]
        if eid not in rows_by_id or row["outcome"] != "accepted" or row["validation_passed"] != "true":
            continue
        event, evidence = rows_by_id[eid]
        src, member = event.get("source"), members.get(row["member_id"])
        if (not src or not member or row["chr"] != event["chr"] or stable_id("ev-step2-refill" if number == 1 else "ev-step2-refill-round2", row["candidate_id"],22) != evidence["evidence_id"]
                or (row["source_dataset"],row["source_contig"],int(row["source_start"]),int(row["source_end"]),row["orientation"])
                != (src["dataset"],src["contig"],src["start"],src["end"],src["orientation"])):
            continue
        params = json.loads(evidence["parameters_json"]); raw = evidence["raw_artifact_relpath"]
        proj = params["flank_projection_relpath"]
        if not all(str(p).startswith(f"{base}/refill/round{number}/") for p in (raw,proj)) or PurePosixPath(raw).parent != PurePosixPath(proj).parent:
            continue
        plans[(raw,evidence["raw_artifact_sha256"],proj,params["flank_projection_sha256"],event["chr"])].append((row,member))
    for (raw,digest,proj,pdigest,chrom), candidates in plans.items():
        pp, signature = _bound(layout,proj,seals,pdigest)
        with pp.open() as f: projection=json.load(f)
        if (file_signature(pp)!=signature or projection.get("chr")!=chrom or projection.get("schema_version")!="grt_refill_flank_projection_v1"):
            continue
        target,signature=_bound(layout,raw,seals,digest)
        wanted={int(row[k]) for row,_ in candidates for k in ("left_line","right_line")}
        lines={}
        with target.open() as f:
            for i,line in enumerate(f,1):
                if i in wanted: lines[i]=line.rstrip().split("\t")
        if file_signature(target)!=signature:
            raise ValueError("refill PAF changed")
        for row,member in candidates:
            pair=[]
            for key,side in (("left_line","L"),("right_line","R")):
                fields=lines.get(int(row[key]),[])
                if len(fields)<12 or fields[0]!="flank__{}__{}".format(row["object_id"],side) or fields[5]!=member["fasta_record_name"]:
                    break
                window=projection["queries"][fields[0]]; start,end=int(window["q_start"])-1,int(window["q_end"])
                qlen,qa,qb,mlen,ma,mb=map(int,[fields[i] for i in (1,2,3,6,7,8)])
                if (not 0<=start<end<=projection["q_length"] or end-start!=qlen or not 0<=qa<qb<=qlen or not 0<=ma<mb<=mlen
                        or mlen!=int(member["source_end"])-int(member["source_start"])+1 or fields[4] not in ("+","-")):
                    break
                sa,sb=member_source_interval(member,ma+1,mb)
                pair.append({"q":[start+qa,start+qb],"source":[sa-1,sb],"strand":"+" if member["orientation"]==fields[4] else "-"})
            if len(pair)==2:
                out[row["event_id"]]={"round":number,"before":[int(row["target_start"])-1,int(row["target_end"])],"anchors":pair}


def capture_step2_evidence(root, result):
    layout=WorkspaceLayout.detect(root); base="grt/evidence/step2"
    ck=obj(root,layout.relative("grt/checkpoints/step2.json")); fp=ck["fingerprint_payload"]
    if (ck.get("stage")!="step2" or ck.get("status")!="success" or ck["input_fingerprint"]!=result["input_fingerprint"]
            or fp["q_source_sha256"]!=result["q_input_sha256"] or fp["donor_target_sha256"]!=result["target_sha256"]):
        return {}
    frozen=obj(root,layout.relative("metadata/grt_q0_freeze.json"))["artifacts"]; donor=label(result["donor_set_id"])
    if frozen.get(f"grt/donors/{donor}.fa")!=result["target_sha256"]: return {}
    members={m["member_id"]:m for m in sealed_rows(layout,"metadata/grt_donor_members.tsv",frozen) if m["donor_set_id"]==donor}
    events={e["event_id"]:e for e in result["events"] if e["status"] in ("accepted","superseded")}
    evidence={r["evidence_id"]:r for r in result["evidence_rows"] if r["q_source_sha256"]==result["q_input_sha256"]}
    by_id={}
    for eid,e in events.items():
        matches=[evidence[k] for k in e.get("evidence_ids",[]) if k in evidence and evidence[k]["coordinate_system"]=="paf_0_based_half_open"]
        if len(matches)==1 and e["action"]=="refill": by_id[eid]=(e,matches[0])
    seals=ck["output_hashes"]; out={}
    for number in (1,2):
        if by_id: _picks(layout,seals,by_id,members,base,number,out)
    # Guide alignments illustrate the decision; they are never rendered as the adopted donor.
    wants=defaultdict(list)
    for r in sealed_rows(layout,base+"/correction_candidates.tsv",seals):
        eid=r["event_id"]; m=members.get(r["member_id"])
        if (eid not in events or not m or r["outcome"]!="accepted" or events[eid]["chr"]!=r["chr"] or r["validation_passed"]!="true"
                or (r["source_dataset"],r["source_contig"])!=(m["dataset_name"],m["contig_name"])): continue
        for line in {r["left_line"],r["right_line"]}:
            if line.isdigit(): wants[(r["chr"],r["member_id"],line)].append(eid)
    if wants:
        for r in sealed_rows(layout,base+"/mummer/alignments.tsv",seals):
            ids=wants.get((r["chr"],r["member_id"],r["line_number"]))
            if not ids: continue
            m=members[r["member_id"]]; q1,q2,rs,re=map(int,(r["query_start"],r["query_end"],r["ref_start"],r["ref_end"]))
            if m["fasta_record_name"]!=r["ref_record"] or min(q1,q2,rs,re)<1 or max(rs,re)>int(m["source_end"])-int(m["source_start"])+1: continue
            a,b=member_source_interval(m,min(rs,re),max(rs,re)); forward=((q1<=q2)==(rs<=re))==(m["orientation"]=="+")
            for eid in ids:
                info=out.setdefault(eid,{"guide":{"dataset":label(m["dataset_name"]),"name":label(m["contig_name"])},"anchors":[]})
                info["anchors"].append({"q":[min(q1,q2)-1,max(q1,q2)],"source":[a-1,b],"strand":"+" if forward else "-"})
    return out


def _range(value):
    a,b=value
    if not (type(a) is int and type(b) is int and 1 <= a <= b): raise ValueError("invalid intermediate component interval")
    return [a-1,b]


def _detail(e, witnesses):
    edit=e.get("edit") or {}; junction=e.get("junction") or {}; kind=edit.get("replacement_kind")
    info={"action":label(e["action"]),"reason":label(e["reason"]),"before":[e["q_before"]["start"]-1,e["q_before"]["end"]]}
    if edit.get("operation")=="retain_components":
        info.update(kind="filter", kept=[_range(r) for r in edit.get("kept_intervals",[])],
                    removed=[_range(r) for r in edit.get("removed_intervals",[])],
                    protected=[_range(r) for r in (edit.get("q0_protection") or {}).get("retained_components",[])],
                    applied=e["status"]=="accepted")
    elif junction.get("direct_overlap_bp") and junction.get("support_sequence_inserted") is False:
        n=junction["direct_overlap_bp"]
        if type(n) is not int or n<=0: raise ValueError("invalid direct overlap")
        info.update(kind="overlap",bp=n, sides=[label(junction[k]["contig"]) for k in ("left_source","right_source")])
    elif kind=="none":
        info.update(kind="remove", side=junction.get("dominated_side") if junction.get("dominated_side") in ("left","right") else None)
    elif kind=="gap":
        n=edit["replacement_length"]
        if type(n) is not int or n<=0: raise ValueError("invalid connector")
        info.update(kind="gap",bp=n)
    elif kind=="source" and e.get("source"):
        src=e["source"]; a,b=_range([src["start"],src["end"]]); strand=src["orientation"]
        if strand not in ("+","-"): raise ValueError("invalid donor strand")
        info.update(kind="refill",source={"dataset":label(src["dataset"]),"name":label(src["contig"]),"start":a,"end":b,"strand":strand})
    else:
        info.update(kind="other")
    w=witnesses.get(e["event_id"]) or {}; info["anchors"]=[]
    if w.get("round") in (1,2) and info["kind"]=="refill":
        info["round"]=w["round"]; info["local_before"]=_range([w["before"][0]+1,w["before"][1]])
    elif w.get("guide"):
        info["guide"]={k:label(w["guide"][k]) for k in ("dataset","name")}
    for a in w.get("anchors",[]):
        if a["strand"] not in ("+","-"): raise ValueError("invalid anchor")
        q,src=a["q"],a["source"]
        info["anchors"].append({"q":_range([q[0]+1,q[1]]),"source":_range([src[0]+1,src[1]]),"strand":a["strand"]})
    return info


def structural_stage(facts):
    rows=repair_stage(facts,"step2","q1","q2")
    if rows is None: return None
    raw=facts["result"]["events"]; index={e["event_id"]:e for e in raw}; witnesses=facts.get("step2_evidence",{})
    if len(raw)!=len(index): raise ValueError("duplicate step2 event identity")
    parents=defaultdict(list)
    for e in raw:
        end=e.get("superseded_by_event_id")
        if e.get("status")=="superseded" and end in index and index[end]["chr"]==e["chr"]:
            parents[end].append(e["event_id"])
    for r in rows:
        r["inspections"]=[]
        for e in r["events"]:
            source=index[e["id"]]; seen=set(); order=[]
            def visit(key):
                if key in seen: raise ValueError("cyclic superseded lineage")
                seen.add(key)
                for predecessor in parents[key]: visit(predecessor)
                order.append(_detail(index[key],witnesses))
            visit(e["id"]); e["history"]=order
            # Some boundary decisions carry a guide source. A guide is not adopted sequence.
            e["source"]=order[-1].get("source"); e["anchors"]=[]
            e["whole_chr"]=source.get("q_after_projection")=="whole_chromosome_filter" or order[-1]["kind"]=="filter"
        for e in raw:
            if e["chr"]==r["chr"] and e["status"]!="accepted" and e["action"]=="filter_component":
                d=_detail(e,{})
                if d.get("protected") or (d.get("removed") and e["status"]=="rejected"):
                    r["inspections"].append(d)
    return rows
