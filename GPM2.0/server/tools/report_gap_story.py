"""Original LGZ gap → per-publication evidence, not a merged best-tool path.

Only project interval pairs that have the same owner. Do not expose raw recipes,
read paths or candidate sequences, or treat a missing native report as no hit.
"""
from collections import defaultdict
import hashlib
import json
import re

from report_inventory import file_href, physical
from report_q0_tracks import label
from run_orchestration import sha256_file


PRIORITY = ("degap", "lrgapcloser", "tgsgapcloser", "quartet")
NAMES = dict(zip(PRIORITY, ("DEGAP", "LR_Gapcloser", "TGS-GapCloser", "quarTeT")))


def checked_json(layout, folder, name, files):
    raw = physical(layout.root, f"{folder}/{name}").read_bytes()
    if hashlib.sha256(raw).hexdigest() != files.get(name):
        raise ValueError(f"committed {name} changed")
    return json.loads(raw)


def native_views(layout, folder, summary, files, ids):
    """Only DEGAP has a native visual; placeholders have no verified wrapper."""
    by_source, by_name, jobs, global_href = {}, {}, defaultdict(list), None
    if summary.get("tool") != "degap":
        return {}, None
    for view in (summary.get("native_visualization") or {}).get("views", []):
        wrapper, display = view.get("wrapper_path"), view.get("display_path")
        if not wrapper or not display or not re.fullmatch(r"native_visualization/view-[a-f0-9]{20}\.html", wrapper):
            continue
        name = view["name"]
        if display != "native_visualization/pages/" + label(name):
            continue
        if not all(f in files and file_href(layout.root, f"{folder}/{f}") and sha256_file(physical(layout.root, f"{folder}/{f}")) == files[f] for f in (wrapper, display)):
            continue
        href = file_href(layout.root, f"{folder}/{wrapper}")
        by_name[name] = href
        for source in view.get("sources", []):
            if isinstance(source.get("source_path"), str):
                by_source[source["source_path"]] = href
        if name == "Global.report.html":
            global_href = href
    for job in summary.get("native_jobs", []):
        name = job.get("job_name")
        if not isinstance(name, str) or not re.fullmatch(r"[^/\\\x00-\x1f]{1,255}", name):
            continue
        href = by_source.get(job.get("visualization_html")) or by_name.get(name + ".html")
        if not href or href == global_href:
            continue
        for gid in job.get("original_gap_ids", []):
            if gid in ids and {"name": name, "href": href} not in jobs[gid]:
                jobs[gid].append({"name": name, "href": href})
    return dict(jobs), global_href


def span(value, *, empty=False):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("missing refinement interval")
    a, b = value
    if type(a) is not int or type(b) is not int or a < 0 or b < a or (not empty and a == b):
        raise ValueError("invalid refinement interval")
    return [a, b]


def source(r):
    if r is None:
        return None
    a, b = span([r["start"]-1, r["end"]])  # native source coordinates are 1-based inclusive
    if r["orientation"] not in ("+", "-"):
        raise ValueError("invalid source orientation")
    return {"name": label(r["contig"]), "dataset": label(r["dataset"]), "strand": r["orientation"], "span": [a,b]}


def project_edit(e, known):
    # Old summaries can enumerate edits but omit the underlying geometry.
    if not all(k in e for k in ("chromosome", "start", "end", "output_start", "output_end", "replacement")):
        return None
    ids = e["gap_ids"]
    before = span([e["start"], e["end"]]); after = span([e["output_start"], e["output_end"]], empty=True)
    if not ids or any(g not in known or known[g]["chromosome"] != e["chromosome"] or
                      not (before[0] < known[g]["end"] and known[g]["start"] < before[1]) for g in ids):
        raise ValueError("refinement edit not at named original gaps")
    src = source(e["replacement"]); length = after[1]-after[0]
    if (src["span"][1]-src["span"][0] if src else 0) != length:
        raise ValueError("replacement/output length mismatch")
    evidence = e.get("evidence") or {}; anchors = []
    # The flank anchors and native_interval must refer to the same native sequence.
    native = evidence.get("native_interval")
    native = span(native, empty=True) if native is not None else None
    for f in evidence.get("flank_decisions", []):
        anchor = f.get("anchor")
        if anchor and native is not None and evidence.get("method") == "validated_native_trace":
            a,b = span(anchor["baseline_interval"]),span(anchor["native_interval"])
            if a[1]-a[0] != b[1]-b[0]: raise ValueError("invalid flank anchor")
            anchors.append([a,b])
    # Native trace pieces of kind baseline were sequence-verified by the adapter.
    # Use only the adjacent part of the retained piece, not an inferred alignment.
    original = evidence.get("original_native_window")
    trace = evidence.get("native_trace") or {}
    if evidence.get("method") == "validated_native_trace" and native is not None and original is not None:
        x, y = span(original[:2], empty=True); u, v = span(original[2:], empty=True)
        for side in ("left_anchor", "right_anchor"):
            row = trace.get(side)
            if not row or row.get("kind") != "baseline": continue
            start, length = row.get("start"), row.get("length")
            if type(start) is not int or type(length) is not int or start < 0 or length <= 0: continue
            width = min(200, length)
            if side == "left_anchor" and start+length == x and u >= width:
                pair = [[x-width, x], [u-width, u]]
            elif side == "right_anchor" and start == y:
                pair = [[y, y+width], [v, v+width]]
            else: continue
            if pair not in anchors: anchors.append(pair)
    return dict(id=label(e["edit_id"]), gap_ids=list(ids), before=before, after=after, source=src,
                native=native, anchors=anchors)


def gap_evidence(rows, tool, prov, final):
    known = {r["gap_id"]: r for r in rows}
    def identity(r): return r["gap_id"], r["chromosome"], r["start"], r["end"]
    if any(sorted(map(identity, rows)) != sorted(map(identity, items)) for items in (prov["gap_outcomes"], final["original_gaps"])):
        raise ValueError("tool publication differs from frozen gap denominator")
    if prov.get("baseline") != final.get("baseline") or final.get("tool", tool) != tool:
        raise ValueError("inconsistent tool baseline")
    edits = {e["edit_id"]:e for e in final["edits"]}; rejected = defaultdict(list)
    for r in [*prov.get("rejected_candidates", []), *prov.get("execution", {}).get("withheld_candidates", [])]:
        for gid in r.get("gap_ids", []):
            if gid in known: rejected[gid].append(r)
    out = {}
    for g in prov["gap_outcomes"]:
        gid = g["gap_id"]; state = g["status"]
        if state != known[gid]["tools"][tool]: raise ValueError("comparison/publication outcome mismatch")
        if state not in ("closed", "partial", "unfilled", "rejected"): raise ValueError("unknown tool outcome")
        admitted = []
        for eid in g["edit_ids"]:
            e = edits[eid]
            if gid not in e["gap_ids"]: raise ValueError("edit belongs to a different gap")
            projected = project_edit(e, known)
            if projected: admitted.append(projected)
        if admitted and state in ("unfilled", "rejected"): raise ValueError("retained gap has admitted edit")
        candidates = []
        for r in rejected[gid]:
            proposals = r.get("edits") or [r]
            for proposal in proposals:
                before = proposal.get("baseline_interval")
                candidates.append(dict(before=span(before, empty=True) if before is not None else None,
                                       source=source(proposal.get("replacement")),
                                       reason=next((v for v in (r.get("detail"), r.get("reason")) if v in REASONS), None),
                                       gap_ids=[k for k in r.get("gap_ids", []) if k in known]))
        residual = g.get("candidate_residual_n_bp")
        if residual is not None and (type(residual) is not int or residual < 0): raise ValueError("invalid residual N count")
        out[gid] = dict(state="retained" if state in ("unfilled", "rejected") else state,
                        edits=admitted, candidates=candidates, residual_n_bp=residual,
                        incomplete=g.get("reason") == "incomplete_gap_kept_original")
    return out


REASONS = {"incomplete_gap_kept_original", "native_change_not_bound_to_an_original_gap", "projected_gap_unchanged",
           "native_anchor_absent", "native_anchor_not_unique", "gap_and_flank_cannot_be_separated"}
