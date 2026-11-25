"""Run-bound repair projections; never treat a donor interval itself as an alignment."""
import csv

from lgz_core.stage_alignment import member_source_interval
from report_inventory import SHA, obj, physical
from report_q0_tracks import label, snapshot_tracks
from run_orchestration import file_signature, sha256_file
from workspace_layout import WorkspaceLayout


def sealed_rows(layout, logical, seals):
    rel = layout.relative(logical)
    expected = seals.get(rel, seals.get(logical))
    path = physical(layout.root, rel)
    if not expected or not path.is_file():
        raise ValueError("missing repair evidence table")
    before = file_signature(path)
    if sha256_file(path) != expected:
        raise ValueError("repair evidence table is not sealed for this stage")
    with path.open(encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f, delimiter="\t")
    if file_signature(path) != before or sha256_file(path) != expected:
        raise ValueError("repair evidence table changed")


def capture_step1_anchors(root, result):
    """Resolve selected show-coords row numbers while their normalized coordinates are available."""
    edits = {r["event_id"]: r for r in result.get("events", []) if r.get("status") == "accepted" and r.get("source")}
    if not edits:
        return {}
    layout = WorkspaceLayout.detect(root)
    ck = obj(root, layout.relative("grt/checkpoints/step1.json"))
    fp = ck["fingerprint_payload"]
    if (ck.get("status") != "success" or ck.get("stage") != "step1" or ck["input_fingerprint"] != result["input_fingerprint"]
            or fp["q_source_sha256"] != result["q_input_sha256"] or fp["donor_target_sha256"] != result["target_sha256"]):
        return {}
    seals = ck["output_hashes"]
    picks = {}
    keys = set()
    for r in sealed_rows(layout, "grt/evidence/step1/candidates.tsv", seals):
        eid = r["event_id"]
        if eid not in edits or r.get("validation_passed") != "true" or r["outcome"] != "accepted":
            continue
        e = edits[eid]; src = e["source"]
        if (e["chr"] != r["chr"] or r["source_dataset"] != src["dataset"] or r["source_contig"] != src["contig"]
                or r["orientation"] != src["orientation"] or int(r["source_start"]) != src["start"] or int(r["source_end"]) != src["end"]
                or not r["left_line"].isdigit() or not r["right_line"].isdigit()):
            continue
        pair = [(r["chr"], r["member_id"], r[side]) for side in ("left_line", "right_line")]
        if eid in picks or pair[0] == pair[1]:
            raise ValueError("ambiguous accepted anchor pair")
        picks[eid] = pair
        keys.update(pair)
    if not picks:
        return {}
    donor_id = label(result["donor_set_id"])
    frozen = obj(root, layout.relative("metadata/grt_q0_freeze.json"))["artifacts"]
    if frozen.get(f"grt/donors/{donor_id}.fa") != result["target_sha256"]:
        return {}
    relevant = {k[1] for k in keys}
    members = {r["member_id"]: r for r in sealed_rows(layout, "metadata/grt_donor_members.tsv", frozen)
               if r["member_id"] in relevant and r["donor_set_id"] == donor_id}
    found = {}
    for r in sealed_rows(layout, "grt/evidence/step1/mummer/alignments.tsv", seals):
        key = (r["chr"], r["member_id"], r["line_number"])
        if key not in keys or key[1] not in members:
            continue
        m = members[key[1]]
        if key in found or m["fasta_record_name"] != r["ref_record"] or (m["dataset_name"],m["contig_name"]) != (r["source_dataset"],r["source_contig"]):
            raise ValueError("ambiguous donor anchor")
        qs, qe, ms, me = (int(r[k]) for k in ("query_start", "query_end", "ref_start", "ref_end"))
        if min(qs,qe,ms,me) < 1 or max(ms,me) > int(m["source_end"])-int(m["source_start"])+1 or m["orientation"] not in ("+", "-"):
            raise ValueError("invalid donor alignment")
        a,b = member_source_interval(m, min(ms,me), max(ms,me))
        forward = ((qs <= qe) == (ms <= me)) == (m["orientation"] == "+")
        found[key] = {"q": [min(qs,qe)-1,max(qs,qe)], "source": [a-1,b], "strand": "+" if forward else "-"}
    return {eid:[found[k] for k in pair] for eid,pair in picks.items() if all(k in found for k in pair)}


def stage_sizes(stats):
    return {label(r["sequence"]):r["length_bp"] for r in stats["sequences"] if type(r.get("length_bp")) is int and r["length_bp"] > 0}


def output_layout(facts, version):
    src = facts.get("result", {})
    stats = facts.get("sequence_versions", {}).get(version) or {}
    sha = stats.get("sha256")
    if not sha or not SHA.fullmatch(sha) or (version, sha) != (src.get("q_output_version"), src.get("q_output_sha256")):
        return None
    table = facts.get("tables", {}).get("q_segments", {})
    rows = facts.get("layout_rows", src.get("q_rows"))
    if isinstance(rows, list):
        count = src.get("report_array_counts", {}).get("q_rows", len(rows))
        table = {"available": True, "row_count": count, "rows": rows}
    tracks = snapshot_tracks(table, {}, stats, version=version)
    return {"sha256": sha, "tracks": tracks} if tracks is not None else None


def event_span(part, version, digest, size):
    if not isinstance(part, dict) or part.get("version") != version or part.get("sha256") != digest:
        raise ValueError("event coordinate space differs from stage")
    a, b = part["start"], part["end"]
    if type(a) is not int or type(b) is not int or not 0 <= a-1 <= b <= size:
        raise ValueError("event outside stage chromosome")
    return [a-1,b]


def repair_stage(facts, stage="step1", prior="q0", after="q1"):
    src = facts.get("result", {})
    versions = facts.get("sequence_versions", {})
    if src.get("stage") != stage or (src.get("q_input_version"),src.get("q_output_version")) != (prior,after):
        return None
    pre, post = versions[prior], versions[after]
    h0, h1 = src["q_input_sha256"], src["q_output_sha256"]
    if not SHA.fullmatch(h0) or not SHA.fullmatch(h1) or (h0,h1) != (pre.get("sha256"),post.get("sha256")):
        return None
    lengths, outputs = stage_sizes(pre), stage_sizes(post)
    events = src["events"]
    if lengths.keys() != outputs.keys() or len(events) != src.get("report_array_counts", {}).get("events",len(events)):
        return None
    records = {c: {"chr":c,"length_bp":n,"output_bp":outputs[c],"input_sha256":h0,"events":[]} for c,n in lengths.items()}
    by_id = set()
    for e in events:
        if e.get("status") != "accepted":
            continue
        chrom = e["chr"]; eid = label(e["event_id"])
        if eid in by_id or e["stage"] != stage:
            raise ValueError("duplicate or foreign repair event")
        by_id.add(eid)
        q = event_span(e["q_before"],prior,h0,lengths[chrom]); out = event_span(e["q_after"],after,h1,outputs[chrom])
        source = e.get("source"); donor = None
        if source:
            a,b = source["start"],source["end"]
            if type(a) is not int or type(b) is not int or not 1 <= a <= b or source["orientation"] not in ("+","-"):
                raise ValueError("invalid accepted donor")
            donor = {"dataset":label(source["dataset"]),"name":label(source["contig"]),"start":a-1,"end":b,"strand":source["orientation"]}
        anchors = []
        for r in (facts.get("step1_anchors") or {}).get(eid,[]):
            qspan, sspan = r["q"], r["source"]
            if not donor or not all(type(i) is int for i in (*qspan,*sspan)) or not (0<=qspan[0]<qspan[1]<=lengths[chrom] and 0<=sspan[0]<sspan[1]) or r["strand"] not in ("+","-"):
                raise ValueError("invalid repair evidence span")
            anchors.append({"q":qspan,"source":sspan,"strand":r["strand"]})
        action, reason = label(e["action"]), label(e["reason"])
        records[chrom]["events"].append({"id":eid,"before":q,"after":out,"action":action,"reason":reason,"source":donor,"anchors":anchors})
    for row in records.values():
        if not row["events"] and row["length_bp"] != row["output_bp"]:
            raise ValueError("changed sequence length without repair events")
    return list(records.values())
