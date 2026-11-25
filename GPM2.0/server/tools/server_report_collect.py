"""Collect facts at stage boundaries; rendering never reads the workspace."""
from __future__ import annotations

try:
    from workspace_layout import workspace_join
except ModuleNotFoundError:
    from .workspace_layout import workspace_join


from collections import Counter, defaultdict
import csv
import hashlib
from pathlib import Path

try:
    from run_orchestration import LGZ_PREPARE_IDS
    from delivery_archive import delivery_path, delivery_staging_path
    from server_report_io import SCHEMA, digest, fasta_stats, local_path, read_events, read_json, read_tsv, write_json
except ModuleNotFoundError:  # Imported as server.tools.server_report_collect.
    from .run_orchestration import LGZ_PREPARE_IDS
    from .delivery_archive import delivery_path, delivery_staging_path
    from .server_report_io import SCHEMA, digest, fasta_stats, local_path, read_events, read_json, read_tsv, write_json

try:
    from render_server_report import REPORT_PREVIEW_ROWS
except ModuleNotFoundError:
    from .render_server_report import REPORT_PREVIEW_ROWS

try:
    from run_orchestration import file_signature, fingerprint
except ModuleNotFoundError:
    from .run_orchestration import file_signature, fingerprint

_LEGACY_STATISTICS_ALGORITHM = "fasta-length-n50-n-gap100-v1"
STATISTICS_ALGORITHM = _LEGACY_STATISTICS_ALGORITHM
try:
    from server_report_q0 import MODE as Q0_MODE, collect_q0_decisions, is_evidence_guided
except ModuleNotFoundError:
    from .server_report_q0 import MODE as Q0_MODE, collect_q0_decisions, is_evidence_guided

LGZ_STAGES = {
    "step1": "grt/evidence/step1",
    "step1_round1": "grt/evidence/step1/round1",
    "step1_filter": "grt/evidence/step1/filter",
    "step1_round2": "grt/evidence/step1/round2",
    "step2": "grt/evidence/step2",
    "step3": "grt/evidence/step3",
    "step4_telomere": "grt/evidence/step4_telomere",
}


def _read_statistics_cache(path: Path):
    if path.is_symlink():
        return None
    try:
        return read_json(path)
    except (OSError, ValueError):
        return None  # Derived cache corruption is a miss, not valid evidence.


def _statistics_match(value, sha256: str) -> bool:
    keys = ("length_bp", "n_bp", "gap_count", "gap_bp")
    if (not isinstance(value, dict) or value.get("sha256") != sha256
            or value.get("gap_definition") != "maximal consecutive N/n runs of at least 100 bp"
            or not isinstance(value.get("sequences"), list)
            or any(type(value.get(k)) is not int or value[k] < 0 for k in (*keys, "sequence_count", "n50_bp"))
            or value["sequence_count"] != len(value["sequences"])):
        return False
    rows = value["sequences"]
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("sequence"), str)
                or any(type(row.get(k)) is not int or row[k] < 0 for k in keys)
                or not row["gap_count"] * 100 <= row["gap_bp"] <= row["n_bp"] <= row["length_bp"]):
            return False
    if any(value[k] != sum(row[k] for row in rows) for k in keys):
        return False
    cumulative = n50 = 0
    for length in sorted((row["length_bp"] for row in rows), reverse=True):
        cumulative += length
        if cumulative * 2 >= value["length_bp"]:
            n50 = length
            break
    return value["n50_bp"] == n50


def sequence_stats(root: Path, path: Path, *, gap_positions=False) -> dict | None:
    if not path.is_file():
        return None
    before = file_signature(path)
    relative = path.relative_to(root).as_posix()
    # This always establishes actual content in the current process, even when
    # persistent metadata agrees. It can reuse an earlier checkpoint hash read.
    current_sha = digest(path)
    algorithm = STATISTICS_ALGORITHM + ("+gap-intervals-v1" if gap_positions else "")
    key = hashlib.sha256((("reference-gap-intervals:" if gap_positions else "") + relative).encode()).hexdigest()
    cache = workspace_join(root, ".run_all/report-statistics", f"{key}.json")
    if cache.parent.is_symlink() or not cache.parent.resolve().is_relative_to(root.resolve()):
        raise ValueError("report statistics cache escapes its workspace")
    saved = _read_statistics_cache(cache)
    source = {"path": relative, "sha256": current_sha}
    value = None
    if (isinstance(saved, dict) and saved.get("schema") == 1
            and saved.get("algorithm") == algorithm
            and saved.get("source") == source
            and _statistics_match(saved.get("stats"), current_sha)
            and saved.get("stats_sha256") == fingerprint(saved["stats"])):
        value = saved["stats"]
    if value is None and saved is None and algorithm == _LEGACY_STATISTICS_ALGORITHM:
        # Adopt only the previous known statistics contract and verify its
        # content binding. Archived reports stay immutable. This avoids one
        # last full re-scan when first installing the persistent-cache fix.
        st = path.stat()
        legacy_key = hashlib.sha256(f"{path.relative_to(root)}:{st.st_size}:{st.st_mtime_ns}:{st.st_ctime_ns}".encode()).hexdigest()
        candidates = [workspace_join(root, "report/statistics", f"{legacy_key}.json")]
        candidates += sorted((workspace_join(root, ".report_history")).glob(f"*/statistics/{legacy_key}.json"), reverse=True)[:8]
        for candidate in candidates:
            if not candidate.resolve().is_relative_to(root.resolve()):
                continue
            old = _read_statistics_cache(candidate)
            if _statistics_match(old, current_sha):
                value = old
                break
    if value is None:
        value = fasta_stats(path, gap_positions=True) if gap_positions else fasta_stats(path)
    if file_signature(path) != before or not _statistics_match(value, current_sha):
        raise ValueError(f"FASTA changed during report statistics: {path}")
    record = {"schema": 1, "algorithm": algorithm, "source": source,
              "stats_sha256": fingerprint(value), "stats": value}
    if saved != record:
        write_json(cache, record)
    return value


def table(root: Path, relative: str, *, row_limit: int | None = None) -> dict:
    path = local_path(root, relative)
    if row_limit is None:
        return {"source": relative, "available": path.is_file(), "rows": read_tsv(path)}
    rows, count = [], 0
    if path.is_file():
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                count += 1
                if len(rows) < row_limit:
                    rows.append(row)
    return {"source": relative, "available": path.is_file(), "rows": rows,
            "row_count": count, "preview_only": count > len(rows)}


def options(root: Path) -> dict:
    return {row["key"]: row["value"] for row in read_tsv(workspace_join(root, "metadata/prepare_options.tsv"))}


def inputs(root: Path) -> dict:
    datasets = read_tsv(workspace_join(root, "metadata/datasets.tsv"))
    reference = read_tsv(workspace_join(root, "metadata/reference.tsv"))
    rows = []
    modern_q0 = is_evidence_guided(root)
    for index, entry in enumerate([*reference, *datasets]):
        is_reference = "reference_name" in entry
        role = "reference" if is_reference else ("assembly_candidate" if modern_q0 else ("primary" if index == len(reference) else "support"))
        path = local_path(root, entry["fasta_relpath"])
        rows.append({"name": entry.get("reference_name", entry.get("dataset_name")),
                     "role": role, "file": entry["fasta_relpath"], "stats": sequence_stats(root, path, gap_positions=is_reference)})
    package = table(root, "metadata/package.tsv")
    current = any(row.get("schema_version") == "4" for row in package["rows"])
    return {"datasets": rows, "q0_mode": Q0_MODE if modern_q0 else "legacy_primary",
            "final_q_version": "q3" if current else "q4",
            "parameters": options(root),
            "telomere_rules": table(root, "tel/rules.tsv"),
            "centromere_reference": table(root, "cen/reference.tsv"),
            "annotation_library_snapshot": read_json(workspace_join(root, "metadata/annotation_library_snapshot.json"), {}),
            "package": package}


def paf_summary(path: Path) -> dict:
    """Union query intervals; do not confuse overlapping alignments with coverage."""
    if not path.is_file():
        return {"available": False, "alignment_count": None}
    intervals = defaultdict(list)
    lengths = {}
    count = 0
    with path.open(encoding="utf-8") as handle:
        for raw in handle:
            if not raw.strip() or raw.startswith("#"):
                continue
            fields = raw.rstrip().split("\t")
            if len(fields) < 12:
                raise ValueError(f"invalid PAF in report source: {path}")
            count += 1
            lengths[fields[0]] = int(fields[1])
            intervals[fields[0]].append((int(fields[2]), int(fields[3])))
    queries = []
    for name, spans in sorted(intervals.items()):
        covered = 0
        left = right = 0
        for start, end in sorted(spans):
            if start > right:
                covered += right - left
                left, right = start, end
            else:
                right = max(right, end)
        covered += right - left
        queries.append({"sequence": name, "length_bp": lengths[name],
                        "aligned_bp": covered,
                        "coverage_percent": round(100 * covered / max(lengths[name], 1), 3)})
    return {"available": True, "alignment_count": count,
            "aligned_query_count": len(queries), "queries": queries}


def collect_assignment(root: Path, input_data: dict) -> dict:
    assignments = table(root, "metadata/chr_assignments.tsv")
    assigned = defaultdict(set)
    for row in assignments["rows"]:
        assigned[row["dataset_name"]].add(row["seq_name"])
    # Full member identities are needed for the story, but not the full audit TSV.
    membership = {}
    if len(assignments["rows"]) > REPORT_PREVIEW_ROWS:
        for row in assignments["rows"]:
            membership.setdefault(row["assigned_chr_name"], {}).setdefault(row["dataset_name"], []).append(row["seq_name"])
    unassigned = []
    for dataset in input_data.get("datasets", []):
        if dataset["role"] == "reference":
            continue
        for sequence in (dataset.get("stats") or {}).get("sequences", []):
            if sequence["sequence"] not in assigned[dataset["name"]]:
                unassigned.append({"dataset_name": dataset["name"], **sequence,
                                   "reason": "no_assignment_passing_filters_and_coverage_threshold"})
    return {**({"assignment_members": membership} if membership else {}),
            "summary": {"assignment_rows": len(assignments["rows"]),
                        "assigned_unique_contigs": sum(map(len, assigned.values())),
                        "unassigned_contigs": len(unassigned)},
            "tables": {"assignments": assignments,
                       "track_order": table(root, "metadata/track_member_orders.tsv"),
                       "unassigned": {"available": assignments["available"], "rows": unassigned}},
            "notes": ["归属行数与唯一 contig 数分别统计；同一 contig 可有多条归属记录。",
                      "未分配表示未通过当前比对过滤和覆盖阈值，不能直接解释为污染序列。"]}


def collect_lgz_inputs(root: Path) -> dict:
    recipe = read_tsv(workspace_join(root, "metadata/grt_recipe.tsv"))
    qc_enabled = bool(recipe and recipe[0].get("reads_qc_enabled") == "true")
    q0_decisions = collect_q0_decisions(root)
    return {"summary": {"reads_qc": "measured" if qc_enabled else "not_enabled"},
            "q0_construction": q0_decisions,
            "parameters": read_json(workspace_join(root, "grt/checkpoints/donor_freeze.json"), {}).get("fingerprint_payload"),
            "sequence_versions": {"q0": sequence_stats(root, workspace_join(root, "grt/q/q0.fa"))},
            "tables": {name: table(root, f"metadata/{filename}.tsv") for name, filename in {
                "recipe": "grt_recipe", "quality": "grt_contig_quality",
                "selection": "grt_contig_roles", "donor_sets": "grt_donor_sets",
                "donor_members": "grt_donor_members", "q_segments": "grt_q_segments",
                "telomere_rules": "grt_telomere_rules", "tools": "grt_tool_versions",
            }.items()},
            "notes": ["reads QC 未启用时，质量值为未测量；q0 和供体构建仍会执行。",
                      "QV/CRAQ 是输入 contig 的评估；本报告不推断最终 q4 的质量提升。"]}


def event_summary(events: list[dict]) -> dict:
    return {"event_count": len(events),
            "by_status": dict(Counter(str(row.get("status", "unknown")) for row in events)),
            "by_action": dict(Counter(str(row.get("action", "unknown")) for row in events)),
            "by_reason": dict(Counter(str(row.get("reason", "unspecified")) for row in events))}


def collect_lgz_result(root: Path, result: dict) -> dict:
    stage = result["stage"]
    evidence_dir = LGZ_STAGES.get(stage)
    tables = {}
    if evidence_dir:
        for path in sorted((workspace_join(root, evidence_dir)).glob("*.tsv")):
            tables[path.stem] = table(root, path.relative_to(root).as_posix(), row_limit=REPORT_PREVIEW_ROWS)
    versions = {key: sequence_stats(root, workspace_join(root, f"grt/q/{key}.fa"))
                for key in (result["q_input_version"], result["q_output_version"])}
    notes = ["这里保留本阶段发布时的事件；最终保留情况见最终结果。"]
    if stage.startswith("step1_") and result.get("q_input_sha256") == result.get("q_output_sha256"):
        notes.append("本阶段序列未改变；外部 contig 模式下的填补／过滤延后到结构修正后的优化填补。")
    return {"summary": event_summary(result.get("events", [])),
            "parameters": read_json(workspace_join(root, f"grt/checkpoints/{stage}.json"), {}).get("fingerprint_payload"),
            "sequence_versions": versions, "result": result, "tables": tables, "notes": notes}


def final_summary(root: Path, report_root: Path) -> dict:
    """Use only results validated in this invocation, never old q4 after a failure."""
    final = read_json(report_root / "final_snapshot.json", {})
    manifest = read_json(report_root / "manifest.json")
    if final and (final.get("run_id") != manifest["run_id"] or final.get("schema_version") != SCHEMA):
        raise ValueError("final snapshot belongs to another invocation or schema")
    final.update(schema_version=SCHEMA, run_id=manifest["run_id"])
    process = {}
    for path in sorted((report_root / "steps").glob("grt-*.json")):
        for event in read_json(path, {}).get("facts", {}).get("result", {}).get("events", []):
            process[event["event_id"]] = event
    reconciled = {event["event_id"]: event for event in final.get("events", [])}
    segments = defaultdict(list)
    for chromosome in final.get("final_path", {}).get("chromosomes", []):
        for segment in chromosome.get("segments", []):
            for event_id in ([segment["event_id"]] if segment.get("event_id") else []):
                segments[event_id].append(segment.get("segment_id"))
    reconciliation = []
    for event_id, event in process.items():
        last = reconciled.get(event_id)
        reconciliation.append({"event_id": event_id, "stage": event.get("stage"),
            "chr": event.get("chr"), "action": event.get("action"),
            "process_status": event.get("status"), "process_reason": event.get("reason"),
            "final_status": last.get("status") if last else "not_finalized",
            "final_reason": last.get("reason") if last else "final_state_not_available",
            "final_path_segment_ids": segments.get(event_id, []),
            "final_event": last})
    # New q0 is a stage publication, not whatever an old workspace currently
    # contains after a failed prepare or a later file mutation.
    modern_q0 = (is_evidence_guided(root) or bool(final.get("q0_construction"))
                 or read_json(report_root / "inputs.json", {}).get("facts", {}).get("q0_mode") == Q0_MODE)
    final["q0_mode"] = Q0_MODE if modern_q0 else "legacy_primary"
    if modern_q0:
        q0 = final.get("sequence_versions", {}).get("q0")
        if q0 is None:
            for relative in manifest.get("steps", []):
                record = read_json(local_path(report_root, relative), {})
                if record.get("stage_id") in LGZ_PREPARE_IDS and record.get("status") == "success":
                    if record.get("run_id") != manifest["run_id"] or record.get("schema_version") != SCHEMA:
                        raise ValueError("q0 snapshot belongs to another invocation or schema")
                    facts = record.get("facts", {})
                    q0 = facts.get("sequence_versions", {}).get("q0")
                    final["q0_construction"] = facts.get("q0_construction")
    else:
        q0 = sequence_stats(root, workspace_join(root, "grt/q/q0.fa"))
    if q0:
        final.setdefault("sequence_versions", {})["q0"] = q0
    input_facts = read_json(report_root / "inputs.json", {}).get("facts", {})
    final_version = final.get("final_q_version", input_facts.get("final_q_version", "q4"))
    final["final_q_version"] = final_version
    q4 = final.get("sequence_versions", {}).get(final_version) or {}
    terminal_rows = final.get("annotations", {}).get("telomere", {}).get("terminal_rows", [])
    complete_statuses = {"already_present", "recovered"}
    complete_ends = sum(row.get("final_status") in complete_statuses for row in terminal_rows)
    expected_ends = 2 * q4.get("sequence_count", 0) if q4 else 0
    telomeres_complete = bool(expected_ends and len(terminal_rows) == expected_ends
                               and complete_ends == expected_ends)
    if not final.get("available") or not q4:
        t2t_status = "unavailable"
    elif len(terminal_rows) != expected_ends:
        t2t_status = "unknown"
    elif q4.get("gap_count") == 0 and q4.get("n_bp") == 0 and telomeres_complete:
        t2t_status = "achieved"
    else:
        t2t_status = "not_achieved"
    q0_gap_count = q0.get("gap_count") if q0 else None
    q4_gap_count = q4.get("gap_count") if q4 else None
    centromere_markers = final.get("annotations", {}).get("centromere", {}).get("markers", [])
    final["outcome_summary"] = {
        "total_length_bp": q4.get("length_bp") if q4 else None,
        "chromosome_count": q4.get("sequence_count") if q4 else None,
        "starting_gap_count": q0_gap_count,
        "gap_count_change": (q4_gap_count - q0_gap_count
                             if q0_gap_count is not None and q4_gap_count is not None else None),
        "closed_gap_count_semantics": "legacy_net_reduction_not_verified_gap_closure",
        "closed_gap_count": (max(0, q0_gap_count - q4_gap_count)
                             if q0_gap_count is not None and q4_gap_count is not None else None),
        "remaining_gap_count": q4_gap_count,
        "telomere_ends_complete": complete_ends if terminal_rows else None,
        "telomere_ends_total": expected_ends or None,
        "telomeres_complete": telomeres_complete if terminal_rows else None,
        "t2t_status": t2t_status,
        "t2t_scope": "emitted_sequences_only",
        "centromere_marker_count": len(centromere_markers),
        "centromere_chromosome_count": len({row.get("chr") for row in centromere_markers}),
    }
    final["event_reconciliation"] = reconciliation
    final["process_summary"] = event_summary(list(process.values()))
    final["final_event_summary"] = event_summary(final.get("events", [])) if final else None
    final["notes"] = ["过程中的接受数不可相加作为最终修复数；最终状态以最终路径及协调后的事件为准。",
                      "gap 定义为连续至少 100 个 N；N 碱基数单独统计。",
                      ("多组装候选 → q0 表示证据驱动的初始构建；q0 → Final Path 表示 LGZ 处理。"
                       if modern_q0 else "原始主组装 → q0 表示初始构建；q0 → Final Path 表示 LGZ 处理。") + "N50 增加本身不证明质量改善。",
                      "Gap 数净减少可能来自冗余连接删除、裁剪或序列替换，不等于真实缺失序列的闭合数量。",
                      "T2T 结构条件只针对本次已输出序列；不证明参考的所有染色体均已构建或无生物学缺失。"]
    return final


def _positive_int(value) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _project_centromere_markers(root: Path, final_path: dict) -> list[dict]:
    """Project source-contig centromere hits onto final q4 chromosome coordinates."""
    hits = defaultdict(list)
    for path in sorted((workspace_join(root, "cen")).glob("chr_*/marks.tsv")):
        for row in read_tsv(path):
            hits[(row.get("dataset_name"), row.get("ctg_name"))].append(row)
    projected = []
    for chromosome in final_path.get("chromosomes", []):
        cursor = 1
        for segment in chromosome.get("segments", []):
            length = _positive_int(segment.get("length")) or 0
            source = segment.get("source") or {}
            source_start = _positive_int(source.get("start"))
            source_end = _positive_int(source.get("end"))
            if length and source_start and source_end:
                source_low, source_high = sorted((source_start, source_end))
                orientation = source.get("orientation") or segment.get("orientation") or "+"
                for hit in hits.get((source.get("dataset"), source.get("contig")), []):
                    hit_start = _positive_int(hit.get("ctg_start"))
                    hit_end = _positive_int(hit.get("ctg_end"))
                    if not hit_start or not hit_end:
                        continue
                    hit_low, hit_high = sorted((hit_start, hit_end))
                    overlap_start = max(source_low, hit_low)
                    overlap_end = min(source_high, hit_high)
                    if overlap_start > overlap_end:
                        continue
                    if orientation == "-":
                        q4_start = cursor + source_high - overlap_end
                        q4_end = cursor + source_high - overlap_start
                    else:
                        q4_start = cursor + overlap_start - source_low
                        q4_end = cursor + overlap_end - source_low
                    projected.append({
                        "chr": chromosome.get("chr"), "q4_start": q4_start, "q4_end": q4_end,
                        "dataset_name": hit.get("dataset_name"), "ctg_name": hit.get("ctg_name"),
                        "source_start": overlap_start, "source_end": overlap_end,
                        "identity": hit.get("identity"), "align_length": hit.get("align_length"),
                        "cen_id": hit.get("cen_id"), "query_name": hit.get("query_name"),
                        "provenance": hit.get("provenance", "[]"),
                    })
            cursor += length
    return projected


def final_annotations(root: Path, final_path: dict) -> dict:
    package = read_tsv(workspace_join(root, "metadata/package.tsv"))
    terminal_stage = "step3" if package and package[0].get("schema_version") == "4" else "step4_telomere"
    step4 = read_json(workspace_join(root, f"grt/evidence/{terminal_stage}/result.json"), {})
    telomere_rules = workspace_join(root, "tel/rules.tsv")
    centromere_reference = workspace_join(root, "cen/reference.tsv")
    return {
        "telomere": {
            "configured": telomere_rules.is_file(),
            "terminal_rows": step4.get("terminal_rows", []),
            "rules": read_tsv(workspace_join(root, "metadata/grt_telomere_rules.tsv")),
        },
        "centromere": {
            "configured": centromere_reference.is_file(),
            "markers": _project_centromere_markers(root, final_path),
        },
    }


def capture_final(root: Path) -> dict:
    final_path = read_json(workspace_join(root, "metadata/grt_final_path.json"), {})
    package = read_tsv(workspace_join(root, "metadata/package.tsv"))
    final_version = "q3" if package and package[0].get("schema_version") == "4" else "q4"
    q_rows = read_tsv(workspace_join(root, "metadata/grt_q_segments.tsv"))
    contribution = Counter()
    connectors = Counter()
    for version in {row["q_version"] for row in q_rows} & {"q0", final_version}:
        connectors[version] = 0
    for row in q_rows:
        if row.get("q_version") not in {"q0", final_version}:
            continue
        if row.get("segment_kind") == "gap":
            connectors[row["q_version"]] += 1
        elif row.get("q_version") == final_version:
            contribution[row.get("dataset_name", "unknown")] += int(row["q_end"]) - int(row["q_start"]) + 1
    return {"available": bool(final_path), "final_path": final_path, "final_q_version": final_version,
            "events": read_events(workspace_join(root, "metadata/grt_events.jsonl")),
            "sequence_versions": {"q0": sequence_stats(root, workspace_join(root, "grt/q/q0.fa")),
                                  final_version: sequence_stats(root, workspace_join(root, f"grt/q/{final_version}.fa"))},
            "q0_construction": collect_q0_decisions(root),
            "source_contribution_bp": dict(contribution),
            "explicit_connector_segments": dict(connectors),
            "annotations": final_annotations(root, final_path)}


def collect_unit(root: Path, unit_id: str, input_data: dict) -> dict:
    if unit_id.startswith("ref:"):
        name = unit_id.split(":", 1)[1]
        relative = f"runs/{name}_vs_ref/result.paf"
        stats = paf_summary(local_path(root, relative))
        source = next((row for row in input_data.get("datasets", []) if row["name"] == name and row["role"] != "reference"), {})
        total = (source.get("stats") or {}).get("sequence_count")
        stats["unaligned_query_count"] = total - stats["aligned_query_count"] if total is not None and stats["available"] else None
        version = local_path(root, f"runs/{name}_vs_ref/tool_version.txt")
        return {"summary": {k: v for k, v in stats.items() if k != "queries"},
                "tables": {"coverage": {"available": stats["available"], "rows": stats.get("queries", [])}},
                "tool_version": version.read_text().strip() if version.is_file() else None,
                "outputs": [{"file": relative, "sha256": digest(workspace_join(root, relative)) if stats["available"] else None}]}
    if unit_id == "assign":
        return collect_assignment(root, input_data)
    if unit_id == "q0_evidence":
        manifest = read_json(workspace_join(root, "metadata/grt_q0_evidence.json"), {})
        relative = manifest.get("catalog")
        catalog = read_json(local_path(root, relative), {}) if relative else {}
        return {"summary": {"candidate_count": len(catalog.get("candidates", [])),
                             "unplaced_segment_count": len(catalog.get("unplaced_segment_ids", [])),
                             "supplementary_task_count": len(catalog.get("supplementary_alignments", []))},
                "notes": ["候选发现不等于路径接受；q0 尚未在此阶段构建。"]}
    if unit_id == "degap_gapfill":
        checkpoint = read_json(workspace_join(root, "degap/checkpoint.json"), {})
        report = read_json(workspace_join(root, "metadata/degap_gapfill.json"), {})
        artifacts = checkpoint.get("artifacts")
        if (not isinstance(artifacts, dict)
                or checkpoint.get("signature") != report.get("input_signature")
                or artifacts.get("metadata/degap_gapfill.json") !=
                (digest(workspace_join(root, "metadata/degap_gapfill.json")) if report else None)
                or not artifacts):
            return {"summary": {"available": False}, "notes": ["DEGAP 本次运行尚无已提交结果；不展示旧结果。"]}
        return {"summary": {key: report.get(key) for key in
                ("gap_count", "accepted_count", "unfilled_count", "reads_type", "lgz_unchanged")},
                "tables": {"gap_decisions": {"available": bool(report), "rows": report.get("decisions", [])}},
                "outputs": [{"file": report.get("output_fasta"), "sha256": report.get("output_sha256")}],
                "notes": ["仅补剩余内部 gap；独立输出，不修改 LGZ / App Final Path。双侧序列检查不等于独立生物学验证。"]}
    if unit_id in LGZ_PREPARE_IDS:
        return collect_lgz_inputs(root)
    if unit_id.startswith(("chr:", "q0_chr:")):
        relative = f"runs/chr_{unit_id.split(':', 1)[1]}"
        paths = sorted(local_path(root, relative).glob("*/result.paf"))
        q0_phase = unit_id.startswith("q0_chr:")
        split_phases = (local_path(root, relative) / "q0_alignment_tasks.json").is_file()
        if q0_phase or split_phases:
            paths = [path for path in paths
                     if (path.parent.name not in {"tel_scan", "cen_scan"}) == q0_phase]
        annotation_tables = {}
        for kind in (() if q0_phase else ("tel", "cen")):
            directory = local_path(root, f"{kind}/chr_{unit_id.split(':', 1)[1]}")
            for path in sorted(directory.glob("*.tsv")):
                annotation_tables[f"{kind} · {path.stem}"] = table(root, path.relative_to(root).as_posix())
        return {"summary": {"alignment_task_count": len(paths),
                            "self_alignment": "not_enabled" if options(root).get("skip_self") == "true" else "enabled"},
                "tables": {"alignments": {"available": True, "rows": [
                    {"task": path.parent.name, **{k: v for k, v in paf_summary(path).items() if k != "queries"}}
                    for path in paths]},
                    **annotation_tables}}
    if unit_id == "finalize_evidence":
        return {"summary": read_json(workspace_join(root, "metadata/grt_contract_summary.json"), {}),
                "tables": {"used_contigs": table(root, "metadata/grt_used_contigs.tsv"),
                           "evidence": table(root, "metadata/grt_evidence_registry.tsv", row_limit=REPORT_PREVIEW_ROWS),
                           "tools": table(root, "metadata/grt_tool_versions.tsv")}}
    if unit_id in {"package_full", "package_light"}:
        kind = "full" if unit_id == "package_full" else "light"
        path = delivery_path(root, kind)
        staging = delivery_staging_path(root, kind)
        files = [item for item in staging.rglob("*") if item.is_file()] if staging.is_dir() else []
        payload_size = sum(item.stat().st_size for item in files)
        return {
            "summary": {
                "archive": path.name,
                "staging_ready": staging.is_dir(),
                "payload_file_count": len(files),
                "payload_size_bytes": payload_size,
            },
            "outputs": [{"file": path.relative_to(root).as_posix() if path.is_relative_to(root) else path.name,
                         "mode": kind, "payload_size_bytes": payload_size,
                         "payload_file_count": len(files), "status": "payload_staged" if staging.is_dir() else "not_staged",
                         "size_bytes": None, "sha256": None, "publication_verified": False}],
            "notes": [
                "App payload staged; the finalized report and payload are compressed together once after pipeline success."
            ],
        }
    return {"summary": {}, "notes": ["执行情况见本阶段状态；LGZ 子阶段记录单独列出。"]}


# Compatibility aliases for existing Python consumers.
collect_grt_inputs = collect_lgz_inputs
collect_grt_result = collect_lgz_result


# Compatibility constants; persisted values remain unchanged.
GRT_STAGES = LGZ_STAGES
