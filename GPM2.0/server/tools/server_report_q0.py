"""Bounded report projection of the published q0 decision artifact.

Called only at a successful stage boundary. The complete search and evidence
remain in the immutable Server artifacts, not copied into portable HTML.
"""
from collections import Counter, defaultdict
from pathlib import Path

try:
    from server_report_io import digest, read_json, read_tsv
    from render_server_report import REPORT_PREVIEW_ROWS
    from lgz_core.common import Q_SEGMENT_FIELDS
    from lgz_core.q0_publication import FREEZE, FREEZE_SCHEMA, SELECTION, SELECTION_SCHEMA, row_hash
except ModuleNotFoundError:
    from .server_report_io import digest, read_json, read_tsv
    from .render_server_report import REPORT_PREVIEW_ROWS
    from .lgz_core.common import Q_SEGMENT_FIELDS
    from .lgz_core.q0_publication import FREEZE, FREEZE_SCHEMA, SELECTION, SELECTION_SCHEMA, row_hash

MODE = "evidence_guided_multi_source"


def is_evidence_guided(root: Path) -> bool:
    rows = read_tsv(root / "metadata/package.tsv")
    return bool(rows and rows[0].get("schema_version") == "3")


def bounded_table(rows):
    return {"available": True, "source": SELECTION, "row_count": len(rows),
            "preview_only": len(rows) > REPORT_PREVIEW_ROWS, "rows": rows[:REPORT_PREVIEW_ROWS]}


def collect_q0_decisions(root: Path):
    if not is_evidence_guided(root):
        return None
    envelope = read_json(root / SELECTION)
    frozen = read_json(root / FREEZE)
    if (not isinstance(envelope, dict) or envelope.get("schema") != SELECTION_SCHEMA
            or not isinstance(frozen, dict) or frozen.get("schema") != FREEZE_SCHEMA):
        raise ValueError("q0 report requires the published selection and freeze; no legacy fallback")
    selection_hash = digest(root / SELECTION)
    q0_hash = digest(root / "grt/q/q0.fa")
    rows = [row for row in read_tsv(root / "metadata/grt_q_segments.tsv") if row["q_version"] == "q0"]
    if (selection_hash != frozen["selection_sha256"] or selection_hash != frozen["artifacts"][SELECTION]
            or q0_hash != frozen["artifacts"]["grt/q/q0.fa"]
            or row_hash(rows, Q_SEGMENT_FIELDS) != frozen["q0_rows_sha256"]):
        raise ValueError("q0 report selection/source mapping differs from the published freeze")
    construction = envelope["construction"]
    if construction.get("schema") != "lgz_q0_construction_v1":
        raise ValueError("unsupported q0 construction report schema")
    contributions = defaultdict(Counter)
    contigs = defaultdict(set)
    for row in rows:
        if row["segment_kind"] == "source":
            key = (row["chr"], row["dataset_name"])
            contributions[key]["source_bp"] += int(row["source_end"]) - int(row["source_start"]) + 1
            contributions[key]["source_piece_count"] += 1
            contigs[key].add(row["contig_name"])
    sources = [{"chr": chr_name, "dataset_name": dataset, **counts,
                "source_contig_count": len(contigs[(chr_name, dataset)])}
               for (chr_name, dataset), counts in sorted(contributions.items())]
    chromosome_rows, joins, reference_ranges, source_ranges, searches = [], [], [], [], []
    joins_by_kind = Counter()
    n_by_kind = Counter()
    for chromosome in construction["chromosomes"]:
        name = chromosome["chromosome"]
        search = construction["searches"][name]
        path = search["path"]  # Missing is corrupt; explicit null means not built.
        if (chromosome["status"] not in {"partial_path", "not_constructed"}
                or (path is None) != (chromosome["status"] == "not_constructed")):
            raise ValueError("q0 chromosome status disagrees with selected path")
        source_bp = {dataset: values["source_bp"] for (chr_name, dataset), values in contributions.items() if chr_name == name}
        reference_missing = chromosome.get("reference_unrepresented")
        chromosome_rows.append({"chr": name, "status": chromosome["status"],
            "source_bp_by_dataset": source_bp,
            "input_gap_joins": chromosome.get("input_gap_joins") if path else None,
            "unknown_joins": chromosome.get("unknown_joins") if path else None,
            "reference_unrepresented_bp": sum(i["end"] - i["start"] for i in reference_missing) if reference_missing is not None else None})
        for interval in reference_missing or []:
            reference_ranges.append({"chr": name, **interval, "coordinate_system": "ref_0_based_half_open"})
        if path is not None:
            for join in path["joins"]:
                kind = join["kind"]
                if kind not in {"input_assembly_gap", "reference_unknown", "sequence_overlap"}:
                    raise ValueError(f"unsupported q0 join kind in report: {kind}")
                joins_by_kind[kind] += 1
                n_by_kind[kind] += join["n_bp"]
                joins.append({"chr": name, "join_id": join["join_id"], "kind": kind,
                    "n_bp": join["n_bp"], "source": join.get("gap_source"),
                    "source_interval": join.get("gap_interval"), "coordinate_system": "source_0_based_half_open",
                    "evidence_ids": join["evidence_ids"]})
            for source, intervals in path["missing"]:
                for interval in intervals:
                    source_ranges.append({"chr": name, **source, **interval, "coordinate_system": "source_0_based_half_open"})
        diagnostics = search["diagnostics"]
        searches.append({"chr": name, "evaluations": diagnostics.get("evaluations"),
            "rounds": diagnostics.get("rounds"), "stop_reasons": diagnostics.get("stop_reasons"),
            "pruning_record_counts": {key: len(diagnostics.get(key, [])) for key in
                                      ("beam_pruning", "edge_pruning", "seed_position_pruning")},
            "search_operation_counts": dict(Counter(row["operation"] for row in search["decisions"])),
            "global_optimality_claimed": diagnostics.get("global_optimality_claimed", False)})
    unused = [{**row["source"], **interval, "coordinate_system": "source_0_based_half_open"}
              for row in construction["unselected_source_intervals"] for interval in row["intervals"]]
    admission = [{**{field: row.get(field) for field in ("segment_id", "placement_id", "status", "reason")},
                  "ambiguous_interval_count": len(row.get("ambiguous_intervals", [])),
                  "evidence_count": len(row.get("evidence_ids", []))} for row in construction["admission"]]
    summary = {"unplaced_component_count": len(construction["unplaced_segment_ids"]),
        "selected_chromosomes": sum(row["status"] != "not_constructed" for row in chromosome_rows),
        "not_constructed_chromosomes": sum(row["status"] == "not_constructed" for row in chromosome_rows),
        "selected_datasets": len({row["dataset_name"] for row in sources}),
        "selected_source_bp": sum(row["source_bp"] for row in sources),
        "input_gap_joins": joins_by_kind["input_assembly_gap"], "input_gap_n_bp": n_by_kind["input_assembly_gap"],
        "unknown_joins": joins_by_kind["reference_unknown"], "unknown_join_n_bp": n_by_kind["reference_unknown"],
        "sequence_overlap_joins": joins_by_kind["sequence_overlap"], "qc": construction["qc"]}
    return {"mode": MODE, "source": SELECTION, "source_sha256": selection_hash, "q0_sha256": q0_hash,
        "summary": summary, "policy": construction["path_policy"],
        "tables": {name: bounded_table(value) for name, value in {
            "q0_chromosomes": chromosome_rows, "q0_source_composition": sources, "q0_retained_joins": joins,
            "q0_reference_unrepresented": reference_ranges, "q0_source_unrepresented": source_ranges,
            "q0_search": searches, "q0_unused_source_intervals": unused,
            "q0_candidate_admission": admission}.items()},
        "notes": ["多组装候选 → q0：所有 ds 提供候选来源，项目 primary_dataset 不作为选择优先级。",
                  "partial_path 只表示已有可用路径，不等同于完整染色体；not_constructed 表示未构建。",
                  "输入原有 N 连接与新增未知连接分别统计；保留的 overlap 连接有序列证据，不是补齐缺失序列的计数。",
                  "参考未被选中锚点覆盖的范围不等于生物学缺失，也不等于已经插入 N 的 gap。坐标为 0-based half-open。",
                  "未选区间包括冗余和未通过筛选的来源，不等于生物学缺失，也不等于供体可用区间；新增序列仍受 QC 与当前占用授权约束。",
                  "准入记录和搜索操作数是决策过程记录，不等于最终采用的 contig 数、连接数或真实修补次数；有界搜索不承诺全局最优。"]}
