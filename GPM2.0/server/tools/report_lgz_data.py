"""Allow-listed LGZ projection: never forward commands, original argv, native payloads or audit events."""

from collections import Counter, defaultdict
import json
import re

from report_repair_story import repair_stage, output_layout
from report_structural_story import structural_stage
from report_terminal_story import terminal_scene
from report_q0_tracks import bound_tracks, references, snapshot_tracks
from report_inventory import file_href, obj, physical
from server_report_io import SCHEMA, timing_summary
from render_server_report import REPORT_PREVIEW_ROWS

STATS = ("length_bp", "sequence_count", "n50_bp", "n_bp", "gap_bp", "gap_count")


def _extract_version_tracks(facts, stage_id):
    """Extract allow-listed 0-based half-open chromosome segment tracks per q-version."""
    tab = (facts.get("tables") or {}).get("q_segments")
    if not isinstance(tab, dict):
        return {}
    rows = tab.get("rows")
    if not isinstance(rows, list) or not rows:
        return {}
    grouped = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if not isinstance(row, dict):
            continue
        qv = row.get("q_version")
        chrom = row.get("chr")
        if not isinstance(qv, str) or not re.fullmatch(r"q[0-4]", qv) or not safe_name(chrom):
            continue
        try:
            q_start = int(row["q_start"])
            q_end = int(row["q_end"])
        except (KeyError, TypeError, ValueError):
            continue
        if q_start < 1 or q_end < q_start:
            continue
        raw_kind = str(row.get("segment_kind") or "source")
        kind = "gap" if "gap" in raw_kind else "source"
        is_patch = "patch" in raw_kind
        if not is_patch and kind != "gap":
            ev_raw = row.get("evidence_ids_json")
            if isinstance(ev_raw, str) and ev_raw:
                try:
                    ev_ids = json.loads(ev_raw)
                except ValueError:
                    ev_ids = []
            elif isinstance(ev_raw, list):
                ev_ids = ev_raw
            else:
                ev_ids = []
            if any(
                isinstance(e, str)
                and (e.startswith("ev-step") or "refill" in e or "patch" in e or "telomere" in e)
                for e in ev_ids
            ):
                is_patch = True
        src = row.get("dataset_name")
        grouped[qv][chrom].append(
            dict(
                start=q_start - 1,
                end=q_end,
                kind=kind,
                source=src if safe_name(src) else None,
                patch=is_patch,
            )
        )
    result = {}
    for qv, by_chr in grouped.items():
        chroms = {}
        for chrom, segs in by_chr.items():
            segs.sort(key=lambda s: (s["start"], s["end"]))
            length_bp = max((s["end"] for s in segs), default=0)
            gap_count = sum(1 for s in segs if s["kind"] == "gap")
            patch_count = sum(1 for s in segs if s["patch"])
            chroms[chrom] = dict(
                length_bp=length_bp,
                segment_count=len(segs),
                gap_count=gap_count,
                patch_count=patch_count,
                truncated=len(segs) > REPORT_PREVIEW_ROWS,
                segments=segs[:REPORT_PREVIEW_ROWS],
            )
        result[qv] = dict(version=qv, stage_id=stage_id, chromosomes=chroms)
    return result


def counts(value, keys=None):
    return {
        k: v
        for k, v in (value or {}).items()
        if type(v) is int and v >= 0 and (keys is None and safe_name(k) or keys is not None and k in keys)
    }


def safe_name(s):
    return isinstance(s, str) and 0 < len(s) <= 255 and not any(c in s for c in "/\\\r\n\t")


def stats(value):
    return counts(value, STATS) if isinstance(value, dict) else {}


def assignment_groups(table, reference_order, complete=None):
    """Preserve the complete run-bound membership; a ctg name is scoped to its assembly."""
    if not isinstance(table, dict) or table.get("available") is not True or not isinstance(table.get("rows"), list):
        return None
    preview = table["rows"]
    count = table.get("row_count", len(preview))
    if table.get("preview_only") or count != len(preview):
        if not isinstance(complete, dict):
            return None
        members = ((ds, ctg, chrom) for chrom, datasets in complete.items() for ds, names in datasets.items() for ctg in names)
    else:
        members = ((r["dataset_name"], r["seq_name"], r["assigned_chr_name"]) for r in preview)
    groups = {chrom: {} for chrom in reference_order}
    owners = defaultdict(set)
    seen = 0
    for dataset, ctg, chrom in members:
        seen += 1
        if not all(safe_name(name) for name in (dataset, ctg, chrom)):
            raise ValueError("invalid assignment identifier")
        targets = owners[dataset, ctg]
        if chrom in targets:
            raise ValueError("duplicate chromosome assignment")
        targets.add(chrom)
        groups.setdefault(chrom, {}).setdefault(dataset, []).append(ctg)
    if seen != count or any(r["assigned_chr_name"] not in owners.get((r["dataset_name"], r["seq_name"]), ()) for r in preview):
        raise ValueError("assignment membership does not match the snapshot")
    return [{"chr": chrom, "member_count": sum(map(len, sources.values())),
             "sources": [{"dataset": ds, "members": [{"name": ctg, "multi": len(owners[ds, ctg]) > 1}
                                                       for ctg in names]} for ds, names in sources.items()]}
            for chrom, sources in groups.items()]


def recorded_coverage(package):
    rows = package.get("rows", []) if isinstance(package, dict) else []
    if len(rows) == 1 and isinstance(rows[0], dict):
        try:
            value = float(rows[0]["chr_assignment_min_coverage_percent"])
        except (KeyError, ValueError, TypeError):
            return None
        if 0 <= value <= 100:
            return value
    return None


def chromosome_rows(final):
    annotations = final.get("annotations", {})
    tel, cen = defaultdict(dict), defaultdict(list)
    for r in annotations.get("telomere", {}).get("terminal_rows", []):
        if safe_name(r.get("terminal")) and safe_name(r.get("final_status")):
            tel[r["chr"]][r["terminal"]] = r["final_status"]
    for r in annotations.get("centromere", {}).get("markers", []):
        cen[r["chr"]].append(counts(r, ("q4_start", "q4_end")))
    final_stats = final.get("sequence_versions", {}).get(final.get("final_q_version", "q4")) or {}
    seqs = {r["sequence"]: r for r in final_stats.get("sequences", [])}
    rows = []
    for r in final.get("final_path", {}).get("chromosomes", []):
        name = r["chr"]
        start = 0
        sources = Counter()
        kinds = Counter()
        segments = []
        if not safe_name(name):
            raise ValueError("invalid chromosome")
        for seg in r.get("segments", []):
            length = seg["length"]
            kind = seg.get("kind", "source")
            source = (seg.get("source") or {}).get("dataset")
            if type(length) != int or length < 0 or not safe_name(kind):
                raise ValueError("invalid segment")
            if safe_name(source):
                sources[source] += length
            kinds[kind] += 1
            if len(segments) < REPORT_PREVIEW_ROWS:
                segments.append(
                    dict(
                        start=start,
                        end=start + length,
                        kind=kind,
                        source=source if safe_name(source) else None,
                        patch=bool(seg.get("event_id")),
                    )
                )
            start += length
        rows.append(
            dict(
                chromosome=name,
                length_bp=r.get("q4_length", start),
                segment_count=sum(kinds.values()),
                segments=segments,
                segment_kinds=dict(kinds),
                source_bp=dict(sources),
                telomeres=tel[name],
                centromere_marker_count=len(cen[name]),
                centromere_markers=cen[name][:REPORT_PREVIEW_ROWS],
                remaining_gap_count=seqs.get(name, {}).get("gap_count"),
            )
        )
    return rows


def collect(layout):
    base = layout.relative("report")
    root = layout.root
    errors = []
    reference_order = []
    ref_tracks = {}
    out = dict(
        status=None,
        run_id=None,
        ended_at=None,
        href=file_href(root, base + "/report.html"),
        diagnostics=errors,
        inputs={"reference": [], "assemblies": [], "typed_reads": [], "annotations": {}},
        assignment={"min_coverage_percent": None, "groups": None},
        funnel={},
        q0={},
        q0_scene=None,
        step1_scene=None,
        step2_scene=None,
        terminal_scene=None,
        stage_paths={},
        sequence_versions={},
        version_tracks={},
        stage_events={},
        outcome={},
        chromosomes=[],
        timing=timing_summary(layout, []),
    )

    def load(rel, run_id=None):
        value = obj(root, base + "/" + rel)
        if (
            value.get("schema_version") != SCHEMA
            or not safe_name(value.get("run_id"))
            or run_id
            and value["run_id"] != run_id
        ):
            raise ValueError("schema_or_run_mismatch")
        return value

    failures = (ValueError, TypeError, OSError, KeyError, AttributeError, IndexError)
    try:
        m = load("manifest.json")
        if not safe_name(m.get("status")) or not isinstance(m.get("errors", []), list):
            raise ValueError("invalid manifest")
        run = m["run_id"]
        out.update(status=m["status"], run_id=run, ended_at=m.get("ended_at"))
    except failures:
        errors.append("manifest.json: missing_or_invalid")
        return out
    try:
        inp = load("inputs.json", run)
        f = inp["facts"]
        datasets = f.get("datasets", [])
        for d in datasets:
            if not safe_name(d["name"]) or not safe_name(d["role"]):
                raise ValueError("invalid dataset")
            out["inputs"]["reference" if d["role"] == "reference" else "assemblies"].append(
                dict(name=d["name"], role=d["role"], stats=stats(d.get("stats")))
            )
            if d["role"] == "reference":
                try:
                    ref_tracks.update(references(d.get("stats") or {}))
                except failures:
                    errors.append("reference: invalid_track_statistics")
                reference_order.extend(row["sequence"] for row in (d.get("stats") or {}).get("sequences", [])
                                       if isinstance(row, dict) and safe_name(row.get("sequence")))
        out["assignment"]["min_coverage_percent"] = recorded_coverage(f.get("package"))
        typed = f.get("typed_reads")
        if typed is None:
            groups = Counter(
                s["option"][2:]
                for s in inp.get("sources", [])
                if s.get("option") in ("--ont", "--hifi", "--reads")
            )
            typed = [dict(technology=k, file_count=v) for k, v in groups.items()]
        out["inputs"]["typed_reads"] = [
            dict(technology=r["technology"], file_count=r["file_count"])
            for r in typed
            if r.get("technology") in ("ont", "hifi", "reads") and type(r.get("file_count")) is int
        ]
        for k in ("telomere_rules", "centromere_reference"):
            t = f.get(k, {})
            out["inputs"]["annotations"][k] = dict(
                configured=t.get("available"), row_count=t.get("row_count", len(t.get("rows", [])))
            )
        assemblies = out["inputs"]["assemblies"]
        ns = [a["stats"].get("sequence_count") for a in assemblies]
        out["funnel"]["input_contigs"] = sum(ns) if ns and None not in ns else None
    except failures:
        errors.append("inputs.json: missing_or_invalid")
    records = []
    aligned = {}
    q0 = {}
    donor_summary = {}
    q0_stats = {}
    q0_table = None

    def versions(facts):
        nonlocal q0_stats
        for k, v in facts.get("sequence_versions", {}).items():
            if re.fullmatch(r"q[0-4]", k) and v:
                out["sequence_versions"][k] = stats(v)
                if k == "q0":
                    q0_stats = v

    try:
        units = m["steps"]
        directory = physical(root, base + "/steps")
        stages = [str(p.relative_to(directory.parent)) for p in sorted(directory.glob("grt-*.json"))]
        if not isinstance(units, list) or len(set(units)) != len(units):
            raise ValueError("invalid units")
    except failures:
        units, stages = [], []
        errors.append("steps: invalid_list")
    unit_names = set(units)
    for rel in [*units, *stages]:
        try:
            if not re.fullmatch(r"steps/(?:\d+|grt-[\w-]+)\.json", rel):
                raise ValueError("invalid path")
            rec = load(rel, run)
            unit = rec["stage_id"]
            facts = rec.get("facts", {})
            summ = facts.get("summary", {})
            if not safe_name(unit):
                raise ValueError("invalid unit")
            if rel in unit_names:
                if not isinstance(rec.get("runtime", {}), dict) or not safe_name(rec.get("status")):
                    raise ValueError("invalid execution")
                records.append(
                    {
                        k: rec[k]
                        for k in (
                            "stage_id",
                            "status",
                            "runtime",
                            "execution",
                            "not_executed_reason",
                            "failure_reason",
                        )
                        if k in rec
                    }
                )
            if rec.get("status") != "success":
                continue
            versions(facts)
            if unit in ("step1", "step2", "step3") and rel in stages:
                version = {"step1":"q1", "step2":"q2", "step3":"q3"}[unit]
                try:
                    path = output_layout(facts, version)
                    if path:
                        out["stage_paths"][version] = path
                except failures:
                    errors.append(f"{unit}: incomplete_output_path")
            if unit == "step3" and rel in stages:
                try:
                    out["terminal_scene"] = terminal_scene(facts)
                except failures:
                    errors.append("step3: invalid_terminal_evidence")
            if unit == "step2" and rel in stages:
                try:
                    out["step2_scene"] = structural_stage(facts)
                except failures:
                    errors.append("step2: invalid_structural_evidence")
            if unit == "step1" and rel in stages:
                try:
                    out["step1_scene"] = repair_stage(facts)
                except failures:
                    errors.append("step1: invalid_event_coordinates")
            extracted_tracks = _extract_version_tracks(facts, unit)
            if extracted_tracks:
                out["version_tracks"].update(extracted_tracks)
            if unit.startswith("ref:") and type(summ.get("aligned_query_count")) is int:
                aligned[unit[4:]] = summ["aligned_query_count"]
            if unit == "assign" and facts.get("tables", {}).get("assignments", {}).get("available") is not False:
                out["funnel"].update(counts(summ, ("assigned_unique_contigs", "unassigned_contigs")))
                out["assignment"]["groups"] = assignment_groups(
                    facts.get("tables", {}).get("assignments"), reference_order, facts.get("assignment_members"))
            if q0_table is None and unit in ("grt_prepare", "lgz_prepare"):
                q0_table = facts.get("tables", {}).get("q_segments")
            q0 = facts.get("q0_construction") or q0
            for key in ("donor_sets", "donor_members"):
                tab = facts.get("tables", {}).get(key, {})
                if tab.get("available"):
                    donor_summary[key] = tab.get("row_count", len(tab.get("rows", [])))
            if rel in stages:
                out["stage_events"][unit] = {
                    "event_count": summ.get("event_count"),
                    "by_status": counts(summ.get("by_status")),
                    "by_action": counts(summ.get("by_action")),
                }
        except failures:
            errors.append(
                (rel if isinstance(rel, str) and re.fullmatch(r"steps/[\w-]+\.json", rel) else "steps")
                + ": missing_or_invalid"
            )
    out["timing"] = timing_summary(layout, records)
    out["donor_freeze"] = donor_summary
    out["failure_reasons"] = [
        "See LGZ process report" if not isinstance(msg, str) or "/" in msg or "\\" in msg else msg[:500]
        for msg in m.get("errors", [])[:10]
    ]
    out["funnel"]["reference_aligned_contigs"] = (
        sum(aligned.values())
        if aligned and set(aligned) == {d["name"] for d in out["inputs"]["assemblies"]}
        else None
    )
    try:
        final = load("final_summary.json", run)
        versions(final)
        out["final_fasta_sha256"] = (final.get("sequence_versions", {}).get(final.get("final_q_version")) or {}).get("sha256")
        q0 = final.get("q0_construction") or q0
        out["chromosomes"] = chromosome_rows(final)
        out["outcome"] = counts(final.get("outcome_summary"))
        for k in ("process_summary", "final_event_summary"):
            ev = final.get(k) or {}
            out[k] = dict(
                event_count=ev.get("event_count"),
                by_status=counts(ev.get("by_status")),
                by_action=counts(ev.get("by_action")),
            )
    except failures:
        errors.append("final_summary.json: missing_or_invalid")
    try:
        out["q0"] = counts(q0.get("summary"))
        sources = defaultdict(int)
        tab = q0.get("tables", {}).get("q0_source_composition", {})
        for row in tab.get("rows", []):
            if safe_name(row.get("dataset_name")):
                sources[row["dataset_name"]] += row["source_bp"]
        out["q0"].update(
            source_bp=counts(q0.get("source_bp_by_dataset", sources)),
            source_rows_truncated="source_bp_by_dataset" not in q0 and bool(tab.get("preview_only")),
        )
    except failures:
        errors.append("q0: invalid_summary")
    try:
        out["q0_scene"] = bound_tracks(layout, q0, ref_tracks, q0_stats)
        if out["q0_scene"] is None:
            out["q0_scene"] = snapshot_tracks(q0_table, ref_tracks, q0_stats)
        if out["q0_scene"] is not None:
            out["q0_scene_sha256"] = q0_stats.get("sha256")
    except failures:
        errors.append("q0 selection: missing_or_invalid_tracks")
    out["reference_tracks"] = ref_tracks
    return out
