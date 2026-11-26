"""Bilingual offline HTML rendering and evidence helpers for telomere target search.

Aligns TelSeeker per-task and global reports with the single-ended large-pool
telomere search schema (`telomere-target-search-v1`), using Python standard
library only and sharing ReportStyle presentation tokens.
"""

from collections import Counter
import csv
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

try:
    from ReportStyle import esc
except ImportError:
    from .ReportStyle import esc


REASON_INFO: Dict[str, Tuple[str, str, str, str, str]] = {
    "connected": (
        "ok",
        "Connected",
        "已连接",
        "Best deterministically ranked eligible candidate met minimum independent read corroboration.",
        "按确定性排序最优的合格候选达到了最小独立 read 佐证要求。",
    ),
    "insufficient_read_support": (
        "warn",
        "Insufficient read support",
        "支持 read 不足",
        "Eligible alignment(s) passed anchor and boundary checks, but none reached minimum independent read-ID corroboration.",
        "存在通过非重复锚点与边界检查的合格比对，但均未达到最小独立 read ID 佐证阈值。",
    ),
    "no_eligible_alignment": (
        "warn",
        "No eligible alignment",
        "无合格比对",
        "Seed index retrieved candidate records, but none passed batched MUMmer length, identity, terminal-boundary, non-repeat anchor, or projection filters.",
        "种子索引检索到了候选记录，但在批量 MUMmer 长度、一致性、末端边界、非重复锚点或边界投影过滤后无合格候选。",
    ),
    "no_sampled_nonrepeat_anchor": (
        "muted",
        "No sampled non-repeat anchor",
        "无采样非重复锚点命中",
        "No record in the telomeric pool matched any locally unique, complex query 21-mer anchor seed.",
        "端粒目标池中没有任何记录匹配到查询序列的局部唯一非重复 21-mer 锚点种子。",
    ),
}

REJECTION_LABELS: Dict[str, Tuple[str, str]] = {
    "inverted_alignment": ("Inverted alignment", "反向比对"),
    "short_alignment": ("Short alignment", "比对过短"),
    "low_identity": ("Low identity", "一致性偏低"),
    "nonterminal_alignment": ("Non-terminal alignment", "非末端比对"),
    "insufficient_nonrepeat_anchor": ("Insufficient non-repeat anchor", "非重复锚点不足"),
    "unprojectable_boundary": ("Unprojectable boundary", "边界不可投影"),
    "ambiguous_boundary_projection": ("Ambiguous boundary projection", "边界投影歧义"),
}

SUPPORT_STATUS_LABELS: Dict[str, Tuple[str, str, str]] = {
    "supported": ("ok", "Supported (lower bound met)", "已获佐证（达到下界）"),
    "insufficient_support": ("warn", "Insufficient support", "佐证不足"),
}

CANDIDATE_STATUS_LABELS: Dict[str, Tuple[str, str]] = {
    "supported": ("Supported", "已获佐证"),
    "insufficient_support": ("Insufficient support", "佐证不足"),
    "ranked_below_winner": ("Ranked below winner", "排序低于胜出者"),
    "alignment_rejected": ("Alignment rejected", "比对被拒绝"),
}

EVIDENCE_FILE_SPECS: Tuple[Tuple[str, str, str, str], ...] = (
    ("diagnostics", "connection-diagnostics.json", "Diagnostics JSON", "诊断 JSON"),
    ("support", "connection-support.json", "Support JSON", "佐证 JSON"),
    ("candidates", "candidates.tsv", "Candidates TSV", "候选 TSV"),
    ("receipt", "telomere-check.json", "Check Receipt", "检查凭证"),
)

MAX_INLINE_SUPPORT_ROWS = 40
MAX_INLINE_SUPPORT_IDS = 5


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _opt_int(mapping: Any, key: str) -> Optional[int]:
    if not isinstance(mapping, dict) or key not in mapping:
        return None
    val = mapping[key]
    return val if _is_int(val) else None


def _read_json_optional(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if path is None:
        return None
    try:
        if not path.is_file():
            return None
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _summarize_candidates_tsv(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if path is None:
        return None
    try:
        if not path.is_file():
            return None
        counts: Counter = Counter()
        total = 0
        with path.open("r", encoding="utf-8", errors="replace", newline="") as stream:
            reader = csv.DictReader(stream, delimiter="\t")
            if not reader.fieldnames:
                return None
            for row in reader:
                total += 1
                status = (row.get("status") or "").strip() or "unknown"
                counts[status] += 1
        return {"total_rows": total, "status_counts": dict(counts)}
    except Exception:
        return None


def safe_relative_href(target_path: Any, base_dir: Path) -> Optional[str]:
    """Return a safe relative POSIX URL path from base_dir to an existing file."""
    if not target_path or base_dir is None:
        return None
    try:
        target = Path(target_path)
        if not target.is_file():
            return None
        rel = os.path.relpath(str(target.resolve()), str(Path(base_dir).resolve()))
    except (OSError, ValueError):
        return None
    posix = rel.replace(os.sep, "/")
    if os.altsep:
        posix = posix.replace(os.altsep, "/")
    segments: List[str] = []
    for part in PurePosixPath(posix).parts:
        if part in ("", "."):
            continue
        if part == "/":
            return None
        # Quote ':' and all URI-special characters so filenames cannot become schemes.
        segments.append(quote(part, safe="-._~"))
    if not segments:
        return None
    href = "/".join(segments)
    if href.startswith("/") or ":" in segments[0]:
        return None
    return href


def load_check_evidence(
    check_dir: Optional[Path],
    *,
    embedded_diagnostics: Optional[Dict[str, Any]] = None,
    diagnostics_path: Optional[Any] = None,
) -> Dict[str, Any]:
    """Load optional per-check telomere target-search evidence from a check directory."""
    resolved_dir: Optional[Path] = None
    if check_dir is not None:
        resolved_dir = Path(check_dir)
    elif diagnostics_path:
        resolved_dir = Path(diagnostics_path).parent

    evidence_files: Dict[str, str] = {}
    if diagnostics_path:
        dp = Path(diagnostics_path)
        if dp.is_file():
            evidence_files["diagnostics"] = str(dp)

    if resolved_dir is not None and resolved_dir.is_dir():
        for key, filename, _en, _zh in EVIDENCE_FILE_SPECS:
            if key in evidence_files:
                continue
            candidate = resolved_dir / filename
            if candidate.is_file():
                evidence_files[key] = str(candidate)

    diagnostics: Optional[Dict[str, Any]] = None
    if isinstance(embedded_diagnostics, dict) and embedded_diagnostics:
        diagnostics = dict(embedded_diagnostics)
    elif "diagnostics" in evidence_files:
        diagnostics = _read_json_optional(Path(evidence_files["diagnostics"]))

    support = _read_json_optional(Path(evidence_files["support"])) if "support" in evidence_files else None
    candidates_summary = (
        _summarize_candidates_tsv(Path(evidence_files["candidates"]))
        if "candidates" in evidence_files
        else None
    )
    receipt = _read_json_optional(Path(evidence_files["receipt"])) if "receipt" in evidence_files else None
    receipt_connection = receipt.get("connection") if isinstance(receipt, dict) and isinstance(receipt.get("connection"), dict) else None

    return {
        "diagnostics": diagnostics,
        "support": support,
        "candidates_summary": candidates_summary,
        "evidence_files": evidence_files,
        "receipt_connection": receipt_connection,
    }


def summarize_chr_end_evidence(
    chr_end_dir: Path,
    report_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Build a concise per-end target-search evidence summary for the global report."""
    chr_end_dir = Path(chr_end_dir)
    checks: List[Tuple[str, Optional[int], Dict[str, Any], Optional[str]]] = []

    direct_ev = load_check_evidence(chr_end_dir / "direct.check")
    if isinstance(direct_ev["diagnostics"], dict):
        checks.append(("direct", 0, direct_ev["diagnostics"], direct_ev["evidence_files"].get("diagnostics")))

    ext_dir = chr_end_dir / "extension"
    tel_result = _read_json_optional(ext_dir / "telomere-result.json")
    seen_rounds = set()
    if isinstance(tel_result, dict) and isinstance(tel_result.get("rounds"), list):
        for row in tel_result["rounds"]:
            if not isinstance(row, dict):
                continue
            rnum = row.get("round")
            check_dir = None
            if row.get("target_evidence"):
                check_dir = Path(row["target_evidence"]).parent
            elif _is_int(rnum):
                check_dir = ext_dir / "attempts" / "0" / str(rnum) / "telomere" / "connection_check"
            ev = load_check_evidence(
                check_dir,
                embedded_diagnostics=row.get("target_search") if isinstance(row.get("target_search"), dict) else None,
                diagnostics_path=row.get("target_evidence"),
            )
            if isinstance(ev["diagnostics"], dict):
                seen_rounds.add(rnum)
                checks.append((
                    "extension",
                    rnum if _is_int(rnum) else None,
                    ev["diagnostics"],
                    ev["evidence_files"].get("diagnostics"),
                ))

    attempts_root = ext_dir / "attempts" / "0"
    if attempts_root.is_dir():
        attempt_dirs = []
        for child in attempts_root.iterdir():
            if child.is_dir() and child.name.isdigit():
                attempt_dirs.append((int(child.name), child))
        for rnum, child in sorted(attempt_dirs):
            if rnum in seen_rounds:
                continue
            ev = load_check_evidence(child / "telomere" / "connection_check")
            if isinstance(ev["diagnostics"], dict):
                checks.append(("extension", rnum, ev["diagnostics"], ev["evidence_files"].get("diagnostics")))

    if not checks:
        return {
            "available": False,
            "source": None,
            "round_num": None,
            "checks_with_diagnostics": 0,
            "reason": None,
            "pool_records": None,
            "indexed_records": None,
            "distinct_read_ids": None,
            "retrieved_records": None,
            "refined_records": None,
            "alignment_batches": None,
            "eligible_records": None,
            "support_count_lower_bound": None,
            "min_support": None,
            "selected_tail_bases": None,
            "junction_bases_tested": None,
            "winner_read_id": None,
            "diagnostics_href": None,
        }

    chosen = next((item for item in checks if item[2].get("reason") == "connected"), None)
    if chosen is None:
        ext_checks = [item for item in checks if item[0] == "extension"]
        chosen = ext_checks[-1] if ext_checks else checks[0]

    source, rnum, diag, diag_path = chosen
    policy = diag.get("policy") if isinstance(diag.get("policy"), dict) else {}
    return {
        "available": True,
        "source": source,
        "round_num": rnum,
        "checks_with_diagnostics": len(checks),
        "reason": diag.get("reason") if isinstance(diag.get("reason"), str) else None,
        "pool_records": _opt_int(diag, "pool_records"),
        "indexed_records": _opt_int(diag, "indexed_records"),
        "distinct_read_ids": _opt_int(diag, "distinct_read_ids"),
        "retrieved_records": _opt_int(diag, "retrieved_records"),
        "refined_records": _opt_int(diag, "refined_records"),
        "alignment_batches": _opt_int(diag, "alignment_batches"),
        "eligible_records": _opt_int(diag, "eligible_records"),
        "support_count_lower_bound": _opt_int(diag, "support_count_lower_bound"),
        "min_support": _opt_int(policy, "min_support"),
        "selected_tail_bases": _opt_int(diag, "selected_tail_bases"),
        "junction_bases_tested": _opt_int(diag, "junction_bases_tested"),
        "winner_read_id": diag.get("winner_read_id") if isinstance(diag.get("winner_read_id"), str) else None,
        "diagnostics_href": safe_relative_href(diag_path, report_dir) if (diag_path and report_dir) else None,
    }


def _bilingual(en: str, zh: str, tag: str = "span", cls: str = "") -> str:
    """Render a leaf bilingual element safe for innerHTML-based language switching."""
    en_text = esc(en)
    zh_text = esc(zh)
    # Double-escape attribute values because JS applies them via node.innerHTML.
    en_attr = esc(en_text)
    zh_attr = esc(zh_text)
    cls_attr = f' class="{esc(cls)}"' if cls else ""
    return f'<{tag}{cls_attr} data-i18n-en="{en_attr}" data-i18n-zh="{zh_attr}">{en_text}</{tag}>'


def _unavailable_html() -> str:
    return _bilingual("Unavailable", "不可用", cls="muted")


def _fmt_int_html(mapping: Any, key: str) -> str:
    val = _opt_int(mapping, key)
    if val is None:
        return _unavailable_html()
    return f'<span class="num">{val:,}</span>'


def _fmt_bp_html(mapping: Any, key: str) -> str:
    val = _opt_int(mapping, key)
    if val is None:
        return _unavailable_html()
    return f'<span class="num">{val:,} bp</span>'


def _fmt_bool_html(mapping: Any, key: str) -> str:
    if not isinstance(mapping, dict) or key not in mapping or not isinstance(mapping[key], bool):
        return _unavailable_html()
    return _bilingual("Yes", "是") if mapping[key] else _bilingual("No", "否")


def _fmt_candidate_cap_html(mapping: Any) -> str:
    if not isinstance(mapping, dict) or "candidate_cap" not in mapping:
        return _unavailable_html()
    val = mapping["candidate_cap"]
    if val is None:
        return _bilingual("None (no cap)", "无上限")
    if _is_int(val):
        return f'<span class="num">{val:,}</span>'
    return f"<code>{esc(val)}</code>"


def _reason_cell_html(reason: Any, *, not_checked: bool = False) -> str:
    if not_checked:
        return (
            '<span class="badge badge-muted">'
            + _bilingual("Not checked (no extension)", "未检查（无延伸）")
            + "</span>"
        )
    if not isinstance(reason, str) or not reason.strip():
        return (
            '<span class="badge badge-muted">'
            + _bilingual("Unavailable", "不可用")
            + "</span>"
        )
    code = reason.strip()
    info = REASON_INFO.get(code)
    if info:
        tone, en_label, zh_label, en_desc, _zh_desc = info
        return (
            f'<span class="badge badge-{tone}" title="{esc(en_desc)}">{_bilingual(en_label, zh_label)}</span>'
            f'<div class="tel-reason-code"><code>{esc(code)}</code></div>'
        )
    return f'<span class="badge badge-info"><code>{esc(code)}</code></span>'


def _support_cell_html(
    diag: Optional[Dict[str, Any]],
    fallback: Optional[Dict[str, Any]] = None,
) -> str:
    lb = _opt_int(diag, "support_count_lower_bound")
    if lb is None:
        lb = _opt_int(fallback, "support_count_lower_bound")

    read_ids: Optional[List[str]] = None
    if isinstance(diag, dict) and isinstance(diag.get("supporting_read_ids"), list):
        read_ids = [str(x) for x in diag["supporting_read_ids"]]
    elif isinstance(fallback, dict) and isinstance(fallback.get("supporting_read_ids"), list):
        read_ids = [str(x) for x in fallback["supporting_read_ids"]]

    checks = _opt_int(diag, "support_checks")
    winner = diag.get("winner_read_id") if isinstance(diag, dict) and isinstance(diag.get("winner_read_id"), str) else None

    if lb is None and checks is None and not read_ids and not winner:
        return _unavailable_html()

    parts: List[str] = []
    if lb is None:
        parts.append(f"<div>{_unavailable_html()}</div>")
    elif lb > 0:
        parts.append(
            f'<div><strong class="num">&ge; {lb:,}</strong> '
            + _bilingual("distinct read IDs (lower bound)", "个独立 read ID（下界）", cls="muted")
            + "</div>"
        )
    else:
        parts.append(
            '<div><span class="num">0</span> '
            + _bilingual("(lower bound; below min support)", "（下界；未达最小支持）", cls="muted")
            + "</div>"
        )

    if winner:
        parts.append(
            '<div class="tel-subline">'
            + _bilingual("Winner:", "胜出 read：", cls="muted")
            + f" <code>{esc(winner)}</code></div>"
        )

    if read_ids:
        shown = [f"<code>{esc(rid)}</code>" for rid in read_ids[:MAX_INLINE_SUPPORT_IDS]]
        extra = len(read_ids) - len(shown)
        extra_html = f' <span class="muted">+{extra:,}</span>' if extra > 0 else ""
        parts.append(
            '<div class="tel-subline">'
            + _bilingual("Support IDs:", "佐证 ID：", cls="muted")
            + " "
            + ", ".join(shown)
            + extra_html
            + "</div>"
        )

    if checks is not None:
        parts.append(
            '<div class="tel-subline">'
            + _bilingual("Support checks:", "佐证检查：", cls="muted")
            + f' <span class="num">{checks:,}</span></div>'
        )

    if isinstance(diag, dict):
        tail_html = _fmt_bp_html(diag, "selected_tail_bases")
        junc_html = _fmt_bp_html(diag, "junction_bases_tested")
        parts.append(
            '<div class="tel-subline">'
            + _bilingual("Tel-read tail:", "端粒 read 尾长：", cls="muted")
            + f" {tail_html} · "
            + _bilingual("Junction tested:", "实测接合区：", cls="muted")
            + f" {junc_html}</div>"
        )

    return "".join(parts)


def _rejections_cell_html(diag: Optional[Dict[str, Any]]) -> str:
    if not isinstance(diag, dict) or "rejection_counts" not in diag or not isinstance(diag["rejection_counts"], dict):
        return _unavailable_html()
    counts = diag["rejection_counts"]
    if not counts:
        return _bilingual("None (0)", "无（0）", cls="muted")
    items: List[Tuple[int, str, Any]] = []
    for key, val in counts.items():
        sort_num = val if _is_int(val) else 0
        items.append((-sort_num, str(key), val))
    chips: List[str] = []
    for _neg, key, val in sorted(items):
        val_html = f'<span class="num">{val:,}</span>' if _is_int(val) else esc(val)
        if key in REJECTION_LABELS:
            en_label, zh_label = REJECTION_LABELS[key]
            label_html = _bilingual(en_label, zh_label)
        else:
            label_html = f"<code>{esc(key)}</code>"
        chips.append(
            f'<span class="tel-chip" title="{esc(key)}">{label_html}: {val_html}</span>'
        )
    return f'<div class="tel-chip-list">{"".join(chips)}</div>'


def _evidence_links_html(evidence_files: Optional[Dict[str, Any]], output_dir: Path) -> str:
    if not isinstance(evidence_files, dict) or not evidence_files:
        return _unavailable_html()
    links: List[str] = []
    for key, _filename, en_label, zh_label in EVIDENCE_FILE_SPECS:
        href = safe_relative_href(evidence_files.get(key), output_dir)
        if href:
            links.append(
                f'<a class="tel-ev-link" href="{esc(href)}" target="_blank" rel="noopener">'
                + _bilingual(en_label, zh_label)
                + "</a>"
            )
    if not links:
        return _unavailable_html()
    return f'<div class="tel-ev-links">{"".join(links)}</div>'


def _render_policy_and_invariants_html(
    primary_diag: Optional[Dict[str, Any]],
    final_info: Optional[Dict[str, Any]] = None,
) -> str:
    if not isinstance(primary_diag, dict):
        return (
            '<div class="notice notice-neutral">'
            "<p>"
            + _bilingual(
                "Target-search diagnostics (telomere-target-search-v1) are unavailable for this task (legacy result or incomplete output). Missing counts, policy parameters, and corroboration metrics are reported as unavailable rather than zero or imputed success.",
                "此任务缺少目标检索诊断信息（telomere-target-search-v1，可能为旧版结果或不完整输出）。缺失的计数、策略参数与佐证指标均标注为不可用，不以 0 或推断成功替代。",
            )
            + "</p>"
            "</div>"
        )

    policy = primary_diag.get("policy") if isinstance(primary_diag.get("policy"), dict) else {}
    min_support_html = _fmt_int_html(policy, "min_support")
    anchor_seeds_html = _fmt_int_html(policy, "anchor_seeds")
    anchor_span_html = _fmt_int_html(policy, "anchor_span")
    support_bases_html = _fmt_int_html(policy, "support_bases")
    policy_summary_html = (
        f'{_bilingual("min", "最小")} {min_support_html} · '
        f'{anchor_seeds_html} {_bilingual("seeds", "种子")}/{anchor_span_html} bp · '
        f'+{support_bases_html} bp'
        if policy
        else _unavailable_html()
    )
    strategy = primary_diag.get("strategy")
    strategy_html = f"<code>{esc(strategy)}</code>" if isinstance(strategy, str) and strategy else _unavailable_html()
    chr_growth_html = _fmt_bp_html(final_info, "total_extension_length")
    tail_html = _fmt_bp_html(primary_diag, "selected_tail_bases")
    junction_html = _fmt_bp_html(primary_diag, "junction_bases_tested")
    batches_html = _fmt_int_html(primary_diag, "alignment_batches")

    return (
        '<details class="tel-details">'
        '<summary>'
        + _bilingual("Search Policy, Scope & Invariants", "检索策略、范围与口径说明")
        + '</summary>'
        '<div class="tel-details-body">'
        '<div class="tel-meta-grid">'
        f'<div class="tel-meta-item"><div class="tel-meta-label">{_bilingual("Search Strategy", "检索策略")}</div><div class="tel-meta-val">{strategy_html}</div></div>'
        f'<div class="tel-meta-item"><div class="tel-meta-label">{_bilingual("Candidate Cap", "候选上限")}</div><div class="tel-meta-val">{_fmt_candidate_cap_html(primary_diag)}</div></div>'
        f'<div class="tel-meta-item"><div class="tel-meta-label">{_bilingual("Alignment Batches", "比对批次数")}</div><div class="tel-meta-val">{batches_html}</div></div>'
        f'<div class="tel-meta-item"><div class="tel-meta-label">{_bilingual("Global Target Grouping", "全局目标分组")}</div><div class="tel-meta-val">{_fmt_bool_html(primary_diag, "global_grouping")}</div></div>'
        f'<div class="tel-meta-item"><div class="tel-meta-label">{_bilingual("Telomeric-Read Extension", "端粒 Read 延伸")}</div><div class="tel-meta-val">{_fmt_bool_html(primary_diag, "target_extension")}</div></div>'
        f'<div class="tel-meta-item"><div class="tel-meta-label">{_bilingual("Current Chr-Side Seq Retained (Final Join)", "最终拼接保留当前染色体侧序列")}</div><div class="tel-meta-val">{_fmt_bool_html(primary_diag, "chromosome_sequence_retained")}</div></div>'
        f'<div class="tel-meta-item"><div class="tel-meta-label">{_bilingual("Corroboration Policy", "佐证策略阈值")}</div><div class="tel-meta-val">{policy_summary_html}</div></div>'
        f'<div class="tel-meta-item"><div class="tel-meta-label">{_bilingual("Chr-Side Assembly Growth (Excl. Tel-Read Tail)", "染色体侧组装延伸（不含端粒 Read 尾）")}</div><div class="tel-meta-val">{chr_growth_html}</div></div>'
        f'<div class="tel-meta-item"><div class="tel-meta-label">{_bilingual("Selected Tel-Read Tail", "入选端粒 Read 尾长")}</div><div class="tel-meta-val">{tail_html}</div></div>'
        f'<div class="tel-meta-item"><div class="tel-meta-label">{_bilingual("Outward Junction Span Tested", "实测向外接合区跨度")}</div><div class="tel-meta-val">{junction_html}</div></div>'
        '</div>'
        '<div class="tel-scope-block">'
        '<p class="tel-scope-note">'
        + _bilingual(
            "Single-ended large-pool telomere search: one chromosome extension family queries a shared exact sampled-seed index (admissibility filter), validates ALL retrieved records across bounded-batch MUMmer comparisons (256 records / 8 MiB per batch; batching is not a candidate cap), and deterministically selects the best corroborated candidate (not first hit).",
            "单端大池端粒检索：单条染色体延伸家族使用共享精确采样种子索引（准入过滤），将全部检索命中的记录按有界批次（每批 256 条记录 / 8 MiB；分批并非候选上限）送入批量 MUMmer 验证，并按确定性排序选择最优获佐证候选（而非首个命中）。",
        )
        + '</p>'
        '<p class="tel-scope-note">'
        + _bilingual(
            "Corroboration scope & limits: read corroboration checks at least ",
            "佐证范围与局限：read 佐证仅检验至少 ",
        )
        + min_support_html
        + _bilingual(
            " distinct read IDs sharing a common non-repeat anchor (≥ ",
            " 个独立 read ID 在公共非重复锚点（≥ ",
        )
        + anchor_seeds_html
        + _bilingual(" seeds across ≥ ", " 个种子，跨度 ≥ ")
        + anchor_span_html
        + _bilingual(" bp) plus up to ", " bp）及接合点向外最多 ")
        + support_bases_html
        + _bilingual(
            " bp outward from the junction. Reported support counts are lower bounds (counting stops once minimum support is reached), not exact totals. It is NOT full-read polishing, NOT telomere-repeat-length consensus, and NOT guaranteed full-genome specificity.",
            " bp 处的一致性。报告的支持数仅为下界（达到最小支持即停止计数），不是精确总数；它并非全 read 抛光、并非端粒重复长度共识，也不保证全基因组唯一性。",
        )
        + '</p>'
        '<p class="tel-scope-note">'
        + _bilingual(
            "Final-join retention & length separation: chromosome_sequence_retained means the current chromosome-side sequence is retained at the FINAL JOIN — it does NOT guarantee that earlier extension/assembly rounds preserved the initial flank unchanged. Chromosome-side assembly growth (total_extension_length) excludes the final telomeric-read tail; selected tel-read tail length (selected_tail_bases) is reported separately from tested outward junction span (junction_bases_tested).",
            "最终拼接保留与长度区分：chromosome_sequence_retained 仅表示在最终拼接（FINAL JOIN）处保留当前染色体侧序列，并不保证此前各轮延伸/组装完整保留了初始侧翼序列。染色体侧组装延伸长度（total_extension_length）不含最终拼接的端粒 read 尾段；入选端粒 read 尾长（selected_tail_bases）与实测向外接合区跨度（junction_bases_tested）分别独立展示。",
        )
        + '</p>'
        '</div></div></details>'
    )


def _render_candidate_details_html(entries: List[Dict[str, Any]]) -> str:
    blocks: List[str] = []
    for entry in entries:
        diag = entry.get("diagnostics")
        support = entry.get("support")
        cand_summary = entry.get("candidates_summary")
        attempted = support.get("attempted") if isinstance(support, dict) and isinstance(support.get("attempted"), list) else []
        if not attempted and not cand_summary and not (isinstance(diag, dict) and diag.get("support_covers")):
            continue

        label_html = _bilingual(entry["label_en"], entry["label_zh"], tag="strong")
        sub_parts: List[str] = [f'<div class="tel-detail-block"><div class="tel-detail-head">{label_html}']

        if isinstance(diag, dict) and isinstance(diag.get("support_covers"), str):
            sub_parts.append(
                f' <span class="muted">·</span> '
                + _bilingual("Support covers:", "佐证覆盖范围：", cls="muted")
                + f' <code>{esc(diag["support_covers"])}</code>'
            )
        sub_parts.append("</div>")

        if isinstance(cand_summary, dict):
            total_rows = cand_summary.get("total_rows")
            sc = cand_summary.get("status_counts") if isinstance(cand_summary.get("status_counts"), dict) else {}
            chips = []
            for key, count in sorted(sc.items(), key=lambda kv: (-int(kv[1]) if _is_int(kv[1]) else 0, str(kv[0]))):
                if key in CANDIDATE_STATUS_LABELS:
                    lbl = _bilingual(CANDIDATE_STATUS_LABELS[key][0], CANDIDATE_STATUS_LABELS[key][1])
                else:
                    lbl = f"<code>{esc(key)}</code>"
                c_html = f'<span class="num">{count:,}</span>' if _is_int(count) else esc(count)
                chips.append(f'<span class="tel-chip">{lbl}: {c_html}</span>')
            total_html = f'<span class="num">{total_rows:,}</span>' if _is_int(total_rows) else _unavailable_html()
            sub_parts.append(
                '<div class="tel-detail-meta">'
                + _bilingual("Retrieved candidate outcomes (candidates.tsv):", "检索候选结果分布（candidates.tsv）：", cls="muted")
                + f" {total_html} "
                + f'<span class="tel-chip-list">{"".join(chips)}</span>'
                + "</div>"
            )

        if attempted:
            rows_html: List[str] = []
            for row in attempted[:MAX_INLINE_SUPPORT_ROWS]:
                if not isinstance(row, dict):
                    continue
                rid = row.get("read_id")
                num = row.get("number")
                status = row.get("status")
                s_ids = row.get("supporting_read_ids") if isinstance(row.get("supporting_read_ids"), list) else None
                if isinstance(status, str) and status in SUPPORT_STATUS_LABELS:
                    tone, en_s, zh_s = SUPPORT_STATUS_LABELS[status]
                    status_html = f'<span class="badge badge-{tone}">{_bilingual(en_s, zh_s)}</span>'
                elif status is not None:
                    status_html = f"<code>{esc(status)}</code>"
                else:
                    status_html = _unavailable_html()
                if s_ids is not None:
                    id_list = ", ".join(f"<code>{esc(x)}</code>" for x in s_ids[:MAX_INLINE_SUPPORT_IDS])
                    if len(s_ids) > MAX_INLINE_SUPPORT_IDS:
                        id_list += f' <span class="muted">+{len(s_ids) - MAX_INLINE_SUPPORT_IDS:,}</span>'
                    lb_text = (
                        f'<span class="num">&ge; {len(s_ids):,}</span> '
                        + _bilingual("(lower bound)", "（下界）", cls="muted")
                        + (f" · {id_list}" if id_list else "")
                    )
                else:
                    lb_text = _unavailable_html()
                rows_html.append(
                    "<tr>"
                    f"<td>{f'<code>{esc(rid)}</code>' if rid is not None else _unavailable_html()}</td>"
                    f'<td class="num">{f"{num:,}" if _is_int(num) else _unavailable_html()}</td>'
                    f"<td>{status_html}</td>"
                    f"<td>{lb_text}</td>"
                    "</tr>"
                )
            sub_parts.append(
                '<table class="table tel-subtable">'
                "<thead><tr>"
                f'<th>{_bilingual("Candidate Read", "候选 Read")}</th>'
                f'<th>{_bilingual("Record #", "记录编号")}</th>'
                f'<th>{_bilingual("Support Check Status", "佐证检查状态")}</th>'
                f'<th>{_bilingual("Supporting Read IDs (Lower Bound)", "支持 Read ID（下界）")}</th>'
                "</tr></thead>"
                f'<tbody>{"".join(rows_html)}</tbody>'
                "</table>"
            )
            if len(attempted) > MAX_INLINE_SUPPORT_ROWS:
                sub_parts.append(
                    '<p class="muted tel-truncated">'
                    + _bilingual(
                        f"Showing first {MAX_INLINE_SUPPORT_ROWS} of {len(attempted)} checked candidates; open Support JSON for full list.",
                        f"仅展示前 {MAX_INLINE_SUPPORT_ROWS} / {len(attempted)} 个已检查候选；完整列表请打开佐证 JSON。",
                    )
                    + "</p>"
                )

        sub_parts.append("</div>")
        blocks.append("".join(sub_parts))

    if not blocks:
        return ""
    return (
        '<details class="tel-details">'
        "<summary>"
        + _bilingual(
            "Candidate Support Checks & Outcome Breakdown",
            "候选佐证检查与结果分布详情",
        )
        + "</summary>"
        f'<div class="tel-details-body">{"".join(blocks)}</div>'
        "</details>"
    )


def render_target_search_section(data: Dict[str, Any], output_dir: Path) -> str:
    """Render the compact bilingual Telomere Target Search & Corroboration section."""
    output_dir = Path(output_dir)
    direct = data.get("direct_check") if isinstance(data.get("direct_check"), dict) else {}
    rounds = data.get("rounds") if isinstance(data.get("rounds"), list) else []

    entries: List[Dict[str, Any]] = []
    if direct:
        entries.append({
            "label_en": "Direct (Round 0)",
            "label_zh": "直接检查（第 0 轮）",
            "not_checked": False,
            "diagnostics": direct.get("target_search") if isinstance(direct.get("target_search"), dict) else None,
            "support": direct.get("support_evidence") if isinstance(direct.get("support_evidence"), dict) else None,
            "candidates_summary": direct.get("candidates_summary") if isinstance(direct.get("candidates_summary"), dict) else None,
            "evidence_files": direct.get("evidence_files") if isinstance(direct.get("evidence_files"), dict) else {},
            "fallback": direct,
        })

    for row in rounds:
        if not isinstance(row, dict):
            continue
        rnum = row.get("round", "?")
        diag = row.get("target_search") if isinstance(row.get("target_search"), dict) else None
        ev_files = row.get("evidence_files") if isinstance(row.get("evidence_files"), dict) else {}
        if not ev_files and row.get("target_evidence"):
            ev_files = {"diagnostics": row["target_evidence"]}
        not_checked = (
            row.get("extension_status") == "no_extension"
            and diag is None
            and not ev_files
            and not row.get("connection_found")
        )
        entries.append({
            "label_en": f"Round {rnum}",
            "label_zh": f"第 {rnum} 轮",
            "not_checked": not_checked,
            "diagnostics": diag,
            "support": row.get("support_evidence") if isinstance(row.get("support_evidence"), dict) else None,
            "candidates_summary": row.get("candidates_summary") if isinstance(row.get("candidates_summary"), dict) else None,
            "evidence_files": ev_files,
            "fallback": row,
        })

    available_diags = [e["diagnostics"] for e in entries if isinstance(e.get("diagnostics"), dict)]
    primary_diag = next((d for d in available_diags if d.get("reason") == "connected"), None)
    if primary_diag is None and available_diags:
        primary_diag = available_diags[-1]

    policy_html = _render_policy_and_invariants_html(
        primary_diag,
        final_info=data.get("final_info") if isinstance(data.get("final_info"), dict) else None,
    )

    if not entries:
        table_html = (
            '<div class="empty-state">'
            + _bilingual(
                "No direct or per-round telomere target-search checks were recorded.",
                "未记录直接检查或各轮次端粒目标检索信息。",
            )
            + "</div>"
        )
    else:
        rows_html: List[str] = []
        for entry in entries:
            diag = entry["diagnostics"]
            not_checked = entry["not_checked"]
            if not_checked:
                pool_cell = _bilingual("—", "—", cls="muted")
                anchor_cell = _bilingual("—", "—", cls="muted")
                aln_cell = _bilingual("—", "—", cls="muted")
                support_cell = _bilingual("—", "—", cls="muted")
                rej_cell = _bilingual("—", "—", cls="muted")
                ev_cell = _bilingual("—", "—", cls="muted")
            else:
                pool_cell = (
                    f'{_fmt_int_html(diag, "pool_records")} / '
                    f'{_fmt_int_html(diag, "indexed_records")} / '
                    f'{_fmt_int_html(diag, "distinct_read_ids")}'
                    if isinstance(diag, dict)
                    else _unavailable_html()
                )
                anchor_cell = (
                    f'{_fmt_int_html(diag, "query_anchor_keys")} &rarr; '
                    f'{_fmt_int_html(diag, "retrieved_records")} / '
                    f'{_fmt_int_html(diag, "refined_records")}'
                    if isinstance(diag, dict)
                    else _unavailable_html()
                )
                aln_cell = (
                    f'{_fmt_int_html(diag, "alignment_batches")} / '
                    f'{_fmt_int_html(diag, "alignment_blocks")} / '
                    f'{_fmt_int_html(diag, "eligible_records")}'
                    if isinstance(diag, dict)
                    else _unavailable_html()
                )
                support_cell = _support_cell_html(diag, entry["fallback"])
                rej_cell = _rejections_cell_html(diag)
                ev_cell = _evidence_links_html(entry["evidence_files"], output_dir)

            reason_cell = _reason_cell_html(
                diag.get("reason") if isinstance(diag, dict) else None,
                not_checked=not_checked,
            )
            row_cls = ' class="row-selected"' if (isinstance(diag, dict) and diag.get("reason") == "connected") else ""
            rows_html.append(
                f"<tr{row_cls}>"
                f'<td>{_bilingual(entry["label_en"], entry["label_zh"])}</td>'
                f"<td>{reason_cell}</td>"
                f"<td>{pool_cell}</td>"
                f"<td>{anchor_cell}</td>"
                f"<td>{aln_cell}</td>"
                f"<td>{support_cell}</td>"
                f"<td>{rej_cell}</td>"
                f"<td>{ev_cell}</td>"
                "</tr>"
            )
        table_html = (
            '<table class="table">'
            "<thead><tr>"
            f'<th>{_bilingual("Check", "检查阶段")}</th>'
            f'<th>{_bilingual("Decision", "判定结果")}</th>'
            f'<th>{_bilingual("Pool / Indexed / Distinct IDs", "池 / 索引 / 独立 ID")}</th>'
            f'<th>{_bilingual("Anchor Keys → Retrieved / Refined", "锚点键 → 检索 / 精排")}</th>'
            f'<th>{_bilingual("Batches / Blocks / Eligible", "批次 / 比对块 / 合格")}</th>'
            f'<th>{_bilingual("Support (Lower Bound)", "佐证（下界）")}</th>'
            f'<th>{_bilingual("Rejections", "拒绝原因")}</th>'
            f'<th>{_bilingual("Evidence Files", "证据文件")}</th>'
            "</tr></thead>"
            f'<tbody>{"".join(rows_html)}</tbody>'
            "</table>"
        )

    details_html = _render_candidate_details_html(entries)
    return (
        '<div class="section tel-evidence-section">'
        f'<div class="section-title">{_bilingual("Telomere Target Search & Corroboration Evidence", "端粒目标检索与佐证证据")}</div>'
        f"{table_html}"
        f"{details_html}"
        f"{policy_html}"
        "</div>"
    )


def telomere_report_css() -> str:
    """Return restrained CSS additions using existing ReportStyle custom properties."""
    return """
.tel-scope-block { margin-top: 8px; }
.tel-scope-note { margin: 4px 0 0; font-size: 0.8rem; color: var(--ink-muted); line-height: 1.5; }
.tel-meta-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 8px; margin: 0 0 8px 0; }
.tel-meta-item { border-left: 2px solid var(--border); padding: 4px 10px; min-width: 0; }
.tel-meta-label { font-size: 0.74rem; font-weight: 500; color: var(--ink-muted); margin-bottom: 2px; }
.tel-meta-val { font-size: 0.83rem; font-weight: 600; color: var(--ink); overflow-wrap: anywhere; }
.tel-reason-code { margin-top: 3px; font-size: 0.74rem; }
.tel-subline { margin-top: 2px; font-size: 0.77rem; color: var(--ink-secondary); }
.tel-chip-list { display: inline-flex; flex-wrap: wrap; gap: 4px; }
.tel-chip { display: inline-block; padding: 1px 6px; font-size: 0.74rem; background: var(--surface-subtle); border: 1px solid var(--border); border-radius: 3px; color: var(--ink-secondary); }
.tel-ev-links { display: flex; flex-wrap: wrap; gap: 5px; }
.tel-ev-link { display: inline-block; padding: 2px 7px; font-size: 0.77rem; background: var(--surface-subtle); border: 1px solid var(--border); border-radius: 3px; color: var(--accent); white-space: nowrap; }
.tel-ev-link:hover { background: var(--accent-soft); border-color: var(--accent-border); text-decoration: none; }
.tel-details { margin-top: 10px; border-top: 1px solid var(--border); }
.tel-details > summary { cursor: pointer; padding: 9px 0; font-size: 0.84rem; font-weight: 600; color: var(--ink-secondary); list-style-position: inside; }
.tel-details > summary:hover { color: var(--ink); }
.tel-details-body { padding: 4px 0 10px; display: grid; gap: 10px; }
.tel-detail-head { font-size: 0.84rem; margin-bottom: 5px; }
.tel-detail-meta { font-size: 0.8rem; margin-bottom: 6px; display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.tel-subtable { font-size: 0.81rem; }
.tel-truncated { font-size: 0.77rem; margin: 4px 0 0 0; }
"""
