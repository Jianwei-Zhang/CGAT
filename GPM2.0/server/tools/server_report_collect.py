"""Collect facts at stage boundaries; rendering never reads the workspace."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
from pathlib import Path

from server_report_io import SCHEMA, digest, fasta_stats, local_path, read_events, read_json, read_tsv, write_json

GRT_STAGES = {
    "step1_round1": "grt/evidence/step1/round1",
    "step1_filter": "grt/evidence/step1/filter",
    "step1_round2": "grt/evidence/step1/round2",
    "step2": "grt/evidence/step2",
    "step3": "grt/evidence/step3",
    "step4_telomere": "grt/evidence/step4_telomere",
}


def sequence_stats(root: Path, path: Path) -> dict | None:
    if not path.is_file():
        return None
    stat = path.stat()
    key = hashlib.sha256(f"{path.relative_to(root)}:{stat.st_size}:{stat.st_mtime_ns}:{stat.st_ctime_ns}".encode()).hexdigest()
    cached = root / "report/statistics" / f"{key}.json"
    value = read_json(cached)
    if value is None:
        value = fasta_stats(path)
        write_json(cached, value)
    return value


def table(root: Path, relative: str) -> dict:
    path = local_path(root, relative)
    return {"source": relative, "available": path.is_file(), "rows": read_tsv(path)}


def options(root: Path) -> dict:
    return {row["key"]: row["value"] for row in read_tsv(root / "metadata/prepare_options.tsv")}


def inputs(root: Path) -> dict:
    datasets = read_tsv(root / "metadata/datasets.tsv")
    reference = read_tsv(root / "metadata/reference.tsv")
    rows = []
    for index, entry in enumerate([*reference, *datasets]):
        is_reference = "reference_name" in entry
        role = "reference" if is_reference else ("primary" if index == len(reference) else "support")
        path = local_path(root, entry["fasta_relpath"])
        rows.append({"name": entry.get("reference_name", entry.get("dataset_name")),
                     "role": role, "file": entry["fasta_relpath"], "stats": sequence_stats(root, path)})
    return {"datasets": rows, "parameters": options(root),
            "telomere_rules": table(root, "tel/rules.tsv"),
            "centromere_reference": table(root, "cen/reference.tsv"),
            "package": table(root, "metadata/package.tsv")}


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
    unassigned = []
    for dataset in input_data.get("datasets", []):
        if dataset["role"] == "reference":
            continue
        for sequence in (dataset.get("stats") or {}).get("sequences", []):
            if sequence["sequence"] not in assigned[dataset["name"]]:
                unassigned.append({"dataset_name": dataset["name"], **sequence,
                                   "reason": "no_assignment_passing_filters_and_coverage_threshold"})
    return {"summary": {"assignment_rows": len(assignments["rows"]),
                        "assigned_unique_contigs": sum(map(len, assigned.values())),
                        "unassigned_contigs": len(unassigned)},
            "tables": {"assignments": assignments,
                       "track_order": table(root, "metadata/track_member_orders.tsv"),
                       "unassigned": {"available": assignments["available"], "rows": unassigned}},
            "notes": ["归属行数与唯一 contig 数分别统计；同一 contig 可有多条归属记录。",
                      "未分配表示未通过当前比对过滤和覆盖阈值，不能直接解释为污染序列。"]}


def collect_grt_inputs(root: Path) -> dict:
    recipe = read_tsv(root / "metadata/grt_recipe.tsv")
    qc_enabled = bool(recipe and recipe[0].get("reads_qc_enabled") == "true")
    return {"summary": {"reads_qc": "measured" if qc_enabled else "not_enabled"},
            "parameters": read_json(root / "grt/checkpoints/donor_freeze.json", {}).get("fingerprint_payload"),
            "sequence_versions": {"q0": sequence_stats(root, root / "grt/q/q0.fa")},
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


def collect_grt_result(root: Path, result: dict) -> dict:
    stage = result["stage"]
    evidence_dir = GRT_STAGES.get(stage)
    tables = {}
    if evidence_dir:
        for path in sorted((root / evidence_dir).glob("*.tsv")):
            tables[path.stem] = table(root, path.relative_to(root).as_posix())
    versions = {key: sequence_stats(root, root / f"grt/q/{key}.fa")
                for key in (result["q_input_version"], result["q_output_version"])}
    notes = ["这里保留本阶段发布时的事件；最终保留情况见最终结果。"]
    if stage.startswith("step1_") and result.get("q_input_sha256") == result.get("q_output_sha256"):
        notes.append("本阶段序列未改变；外部 contig 模式下的填补／过滤延后到结构修正后的优化填补。")
    return {"summary": event_summary(result.get("events", [])),
            "parameters": read_json(root / f"grt/checkpoints/{stage}.json", {}).get("fingerprint_payload"),
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
    final["event_reconciliation"] = reconciliation
    final["process_summary"] = event_summary(list(process.values()))
    final["final_event_summary"] = event_summary(final.get("events", [])) if final else None
    final["notes"] = ["过程中的接受数不可相加作为最终修复数；最终状态以最终路径及协调后的事件为准。",
                      "gap 定义为连续至少 100 个 N；N 碱基数单独统计。",
                      "原始主组装 → q0 表示初始构建；q0 → q4 表示 GRT 处理。N50 增加本身不证明质量改善。"]
    return final


def capture_final(root: Path) -> dict:
    final_path = read_json(root / "metadata/grt_final_path.json", {})
    q_rows = read_tsv(root / "metadata/grt_q_segments.tsv")
    contribution = Counter()
    connectors = Counter()
    for version in {row["q_version"] for row in q_rows} & {"q0", "q4"}:
        connectors[version] = 0
    for row in q_rows:
        if row.get("q_version") not in {"q0", "q4"}:
            continue
        if row.get("segment_kind") == "gap":
            connectors[row["q_version"]] += 1
        elif row.get("q_version") == "q4":
            contribution[row.get("dataset_name", "unknown")] += int(row["q_end"]) - int(row["q_start"]) + 1
    return {"available": bool(final_path), "final_path": final_path,
            "events": read_events(root / "metadata/grt_events.jsonl"),
            "sequence_versions": {"q4": sequence_stats(root, root / "grt/q/q4.fa")},
            "source_contribution_bp": dict(contribution),
            "explicit_connector_segments": dict(connectors)}


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
                "outputs": [{"file": relative, "sha256": digest(root / relative) if stats["available"] else None}]}
    if unit_id == "assign":
        return collect_assignment(root, input_data)
    if unit_id == "grt_prepare":
        return collect_grt_inputs(root)
    if unit_id.startswith("chr:"):
        relative = f"runs/chr_{unit_id.split(':', 1)[1]}"
        paths = sorted(local_path(root, relative).glob("*/result.paf"))
        annotation_tables = {}
        for kind in ("tel", "cen"):
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
        return {"summary": read_json(root / "metadata/grt_contract_summary.json", {}),
                "tables": {"used_contigs": table(root, "metadata/grt_used_contigs.tsv"),
                           "evidence": table(root, "metadata/grt_evidence_registry.tsv"),
                           "tools": table(root, "metadata/grt_tool_versions.tsv")}}
    if unit_id in {"package_full", "package_light"}:
        name = root.name + (".zip" if unit_id == "package_full" else ".no_fasta.zip")
        path = root.parent / name
        return {"summary": {"archive": name, "available": path.is_file()}, "outputs": [
            {"file": name, "size_bytes": path.stat().st_size, "sha256": digest(path)}
        ] if path.is_file() else []}
    return {"summary": {}, "notes": ["执行情况见本阶段状态；GRT 子阶段记录单独列出。"]}
