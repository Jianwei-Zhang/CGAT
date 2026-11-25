"""Terminal evidence: distinguish missing, verified-empty, rejected and accepted PAF evidence."""
from collections import defaultdict
import json
from math import isfinite

from report_inventory import SHA, obj
from report_q0_tracks import label
from report_repair_story import event_span, sealed_rows, stage_sizes
from report_structural_story import _bound
from run_orchestration import file_signature
from workspace_layout import WorkspaceLayout


def spans(raw, length):
    if raw is None: return None
    out=[]
    for a,b in raw:
        if type(a) is not int or type(b) is not int or not 0<=a<b<=length: raise ValueError("invalid repeat interval")
        out.append([a,b])
    return out


def _alignments(layout, seals, row, ev, size, policy, selected_line=None):
    if not ev: return None
    if (ev.get("coordinate_system")!="paf_0_based_half_open" or ev.get("target_chr")!=row["chr"]
            or (ev["source_dataset"],ev["source_contig"])!=(row["source_dataset"],row["source_contig"])):
        return None
    path,sig = _bound(layout, ev["raw_artifact_relpath"], seals, ev["raw_artifact_sha256"])
    length=int(row["extract_source_end"])-int(row["extract_source_start"])+1
    gate=json.loads(ev["parameters_json"]); gi,gb,gm=(gate[k] for k in ("min_identity","min_overlap","min_mapq"))
    if not (isinstance(gi,(float,int)) and isfinite(gi) and 0<=gi<=1 and type(gb) is int and gb>0 and type(gm) is int and gm>=0): return None
    lim=min(size,policy["alignment_query_window"]);offset=size-lim if row["terminal"]=="3prime" else 0
    hits=[]
    with path.open() as fh:
        for lineno,line in enumerate(fh,1):
            if not line.strip() or line.startswith("#"): continue
            f=line.rstrip().split("\t")
            if (len(f)<12 or f[0]!=row["candidate_id"] or int(f[1])!=length or int(f[6])!=lim
                    or f[5]!=row["chr"]+"__"+row["terminal"]+"__q2" or f[4] not in ("+","-")):
                raise ValueError("candidate PAF identity changed")
            a,b,x,y,m,n,mq=map(int,[f[i] for i in (2,3,7,8,9,10,11)])
            if not (0<=a<b<=length and 0<=x<y<=lim and 0<=m<=n and n>0 and 0<=mq<=255): raise ValueError("invalid PAF row")
            failures=[]
            if f[4]!="+":failures.append("strand")
            if b-a<gb:failures.append("overlap")
            if m/n<gi:failures.append("identity")
            if mq<gm:failures.append("mapq")
            hits.append({"extract":[a,b],"q2":[x+offset,y+offset],"strand":f[4],"mapq":mq,"identity":m/n,"failed":failures,"selected":lineno==selected_line})
    if file_signature(path)!=sig: raise ValueError("candidate PAF changed")
    return {"hits":hits,"gates":{"overlap":gb,"mapq":gm,"identity":gi}}


def capture_candidates(root,result, stats):
    layout=WorkspaceLayout.detect(root); ck=obj(root,layout.relative("grt/checkpoints/step3.json"));fp=ck["fingerprint_payload"]
    if ck["stage"]!="step3" or ck["input_fingerprint"]!=result["input_fingerprint"] or ck["status"]!="success" or fp["q2_sha256"]!=result["q_input_sha256"] or fp["tel_donor_sha256"]!=result["target_sha256"]: return None
    seals=ck["output_hashes"]; lengths=stage_sizes(stats); records=[]
    evidence={r["evidence_id"]:r for r in result["evidence_rows"] if r["q_source_sha256"]==result["q_input_sha256"]}
    for r in sealed_rows(layout,"grt/evidence/step3/candidates.tsv",seals):
        cid=label(r["candidate_id"]); chrom=label(r["chr"]); a,b=int(r["extract_source_start"])-1,int(r["extract_source_end"])
        if not 0<=a<b or r["orientation"] not in ("+","-") or r["terminal"] not in ("5prime","3prime"): raise ValueError("invalid terminal candidate")
        try:
            alignment=_alignments(layout,seals,r,evidence.get(r["minimap_evidence_id"]),lengths[chrom],fp["parameters"],result.get("report_selected_paf_lines",{}).get(cid))
        except (ValueError,OSError,KeyError,TypeError): alignment=None
        used=None
        if r["used_source_start"] and r["used_source_end"]:
            ua,ub=int(r["used_source_start"])-1,int(r["used_source_end"])
            if not a<=ua<ub<=b: raise ValueError("candidate cut outside extract")
            used=[ua-a,ub-a] if r["orientation"]=="+" else [b-ub,b-ua]
        records.append({"id":cid,"chr":chrom,"end":r["terminal"],"object":label(r["object_id"]),"rank":int(r["rank"]),
                        "dataset":label(r["source_dataset"]),"name":label(r["source_contig"]),"source":[a,b],"strand":r["orientation"],
                        "used":used,"alignment":alignment,"signals":spans(result.get("report_donor_signals",{}).get(cid),b-a),
                        "status":label(r["outcome"]),"reason":label(r["reason"]),"event":label(r["event_id"]) if r["event_id"] else None})
    return records


def _bounded_pair(raw, size=None):
    a, b = raw
    if type(a) is not int or type(b) is not int or not 0 <= a < b or size is not None and b > size:
        raise ValueError("invalid terminal interval")
    return [a, b]


def _project_candidate(c, q2_length):
    # Stored snapshots can predate this renderer; do not pass arbitrary fields
    # (paths, raw FASTA or untyped numbers that might be rendered as markup).
    source = _bounded_pair(c["source"])
    size = source[1] - source[0]
    out = {k: label(c[k]) for k in ("id", "chr", "end", "object", "dataset", "name", "status", "reason")}
    if c["strand"] not in ("+", "-") or type(c["rank"]) is not int:
        raise ValueError("invalid candidate rank or orientation")
    out.update(source=source, strand=c["strand"], rank=c["rank"], event=label(c["event"]) if c.get("event") else None,
               signals=spans(c.get("signals"), size), used=_bounded_pair(c["used"], size) if c.get("used") else None,
               alignment=None)
    alignment = c.get("alignment")
    if alignment is not None:
        gates = alignment["gates"]
        mq, ov, ident = (gates[k] for k in ("mapq", "overlap", "identity"))
        if type(mq) is not int or not 0 <= mq <= 255 or type(ov) is not int or ov <= 0 or type(ident) not in (int, float) or not 0 <= ident <= 1:
            raise ValueError("invalid terminal gates")
        hits = []
        for h in alignment["hits"]:
            if (type(h["mapq"]) is not int or not 0 <= h["mapq"] <= 255 or type(h["identity"]) not in (int, float)
                    or not 0 <= h["identity"] <= 1 or h["strand"] not in ("+", "-")):
                raise ValueError("invalid terminal match")
            ext = _bounded_pair(h["extract"], size)
            failed = [name for name, failed in (("strand", h["strand"] != "+"), ("overlap", ext[1] - ext[0] < ov),
                                                 ("identity", h["identity"] < ident), ("mapq", h["mapq"] < mq)) if failed]
            hits.append(dict(extract=ext, q2=_bounded_pair(h["q2"], q2_length), strand=h["strand"], mapq=h["mapq"],
                             identity=h["identity"], failed=failed, selected=not failed and h.get("selected") is True))
        out["alignment"] = dict(gates=dict(mapq=mq, overlap=ov, identity=ident), hits=hits)
    return out


def terminal_scene(facts):
    src=facts.get("result",{}); stats=facts.get("sequence_versions",{})
    if (src.get("stage"),src.get("q_input_version"),src.get("q_output_version"))!=("step3","q2","q3"):return None
    pre,post=stats["q2"],stats["q3"];h0,h1=pre.get("sha256"),post.get("sha256")
    if not h0 or not h1 or not SHA.fullmatch(h0) or not SHA.fullmatch(h1) or (h0,h1)!=(src.get("q_input_sha256"),src.get("q_output_sha256")):return None
    lengths,outputs=stage_sizes(pre),stage_sizes(post)
    if lengths.keys()!=outputs.keys():return None
    terms=facts.get("terminal_inventory",src.get("terminal_rows",[]));counts=src.get("report_array_counts",{})
    if counts.get("terminal_rows",len(terms))!=len(terms):return None
    signals={(r["chr"],r["terminal"]):r for r in src.get("report_signals",[])}
    events={e["event_id"]:e for e in src.get("events",[])}; candidates=defaultdict(list)
    for c in facts.get("terminal_candidates") or []:
        projected = _project_candidate(c, lengths[c["chr"]])
        candidates[c["chr"], c["end"], c["object"]].append(projected)
    rows={c:{"chr":c,"length_bp":outputs[c],"sha256":h1,"ends":{}} for c in lengths}
    for t in terms:
        c,k=t["chr"],t["terminal"]; state=t["final_status"]
        if k not in ("5prime","3prime") or k in rows[c]["ends"]:raise ValueError("duplicate or invalid terminal")
        if state not in ("already_present","recovered","unresolved"):continue
        a,b=int(t["q2_start"])-1,int(t["q2_end"])
        if not 0<=a<b<=lengths[c] or (a!=0 if k=="5prime" else b!=lengths[c]):raise ValueError("invalid terminal inspection window")
        signal=signals.get((c,k),{}); chosen=None
        if state=="recovered":
            event=events[t["accepted_event_id"]]
            if (event["status"],event["chr"],event["object_id"],event["edit"]["terminal"])!=("accepted",c,t["object_id"],k): raise ValueError("terminal event identity changed")
            event_span(event["q_before"],"q2",h0,lengths[c]); span=event_span(event["q_after"],"q3",h1,outputs[c]); cut=event["edit"]["q2_cut_after"]
            source=event["source"];lo,hi=source["start"]-1,source["end"]
            if (not 0<=cut<=lengths[c] or source["orientation"] not in ("+","-") or not 0<=lo<hi or hi-lo!=span[1]-span[0]
                    or (span[0]!=0 if k=="5prime" else span[1]!=outputs[c])): raise ValueError("inconsistent terminal cut/source")
            chosen={"span":span,"cut":cut,"event":label(event["event_id"]),"dataset":label(source["dataset"]),"name":label(source["contig"]),"source":[lo,hi],"strand":source["orientation"]}
        count=int(t["candidate_count"]); cs=candidates[c,k,t["object_id"]]; complete=facts.get("terminal_candidates") is not None and count==len(cs)
        rows[c]["ends"][k]={"state":state,"reason":label(t["reason"]),"q2_length":lengths[c],"window":[a,b],"selected":chosen,
                    "count":count,"candidates":sorted(cs,key=lambda x:x["rank"]) if complete else None,
                    "q2_signals":spans(signal.get("q2"),lengths[c]),"q3_signals":spans(signal.get("q3"),outputs[c])}
    return list(rows.values())
