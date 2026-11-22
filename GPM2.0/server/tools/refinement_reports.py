"""Portable, static refinement reports built from content-bound staged results.

A report is not a publication receipt. It records the complete LGZ gap denominator
and labels staged, native and accepted results separately. No external JS, reads
FASTA, native genome or workstation-only hyperlink is needed to view the report.
"""
from __future__ import annotations

from collections import defaultdict, Counter
from bisect import bisect_right
import csv
import hashlib
from html import escape
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import quote

try:
    from workspace_layout import TOOL_DIRECTORIES, WorkspaceLayout
    from run_orchestration import sha256_file as digest, atomic_write_json as atomic_json
    from refinement_tools import fingerprint
except ModuleNotFoundError:
    from .workspace_layout import TOOL_DIRECTORIES, WorkspaceLayout
    from .run_orchestration import sha256_file as digest, atomic_write_json as atomic_json
    from .refinement_tools import fingerprint

SCHEMA = "cgat.refinement-report"
PAGE_SIZE = 200
MAX_ASSET = 20 * 1024 * 1024
MAX_ASSETS_TOTAL = 200 * 1024 * 1024
TEXT_ENDINGS = (".json", ".log", ".tsv", ".paf", ".txt", ".agp", ".detail", ".gap_fill_detail", "_scaff_infos", ".name_map", "/info_filter2")
CSS = "body{font:16px system-ui;max-width:1200px;margin:2em auto;padding:0 1em;color:#17212b}table{border-collapse:collapse;width:100%;margin:1em 0}th,td{border:1px solid #ccd3db;padding:.5em;text-align:left;vertical-align:top}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:1em}a{color:#175ba0}code{overflow-wrap:anywhere}.note{border-left:4px solid #a66d00;padding:.8em;background:#fff6df}summary{cursor:pointer}small{color:#52606d}"


class ReportError(ValueError):
    pass


def safe_file(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative or Path(relative).is_absolute() or any(p in {".", ".."} for p in relative.split("/")):
        raise ReportError("report artifact is not a safe relative file")
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()) or any(p.is_symlink() for p in (path, *path.parents) if p != root and root in p.parents):
        raise ReportError("report artifact traverses a symlink or leaves its root")
    if not path.is_file():
        raise ReportError("report artifact is missing: " + relative)
    return path


def stat_key(path):
    value = path.stat()
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def read_bound(path, expected, *, limit=None):
    before = stat_key(path)
    if limit is not None and path.stat().st_size > limit:
        raise ReportError("report JSON exceeds supported metadata bound")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected or stat_key(path) != before:
        raise ReportError("report input changed: " + str(path))
    return data


def json_text(value):
    return escape(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def link(relative, label):
    return '<a href="' + quote(relative, safe="/#-_.") + '">' + escape(str(label)) + '</a>'


def page(title, body):
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + escape(title) + '</title><style>' + CSS + '</style><body><h1>' + escape(title) + '</h1>' + body + '</body></html>\n'


def table(headers, rows):
    return '<table><thead><tr>' + ''.join('<th>' + escape(h) + '</th>' for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + str(cell) + '</td>' for cell in row) + '</tr>' for row in rows) + '</tbody></table>'


def gap_anchor(gap_id):
    return "gap-" + hashlib.sha256(gap_id.encode()).hexdigest()[:24]


def native_diagnostics(root, tool, run_id, execution):
    """Only known native diagnostic entrypoints; never recursive reads copying."""
    code = TOOL_DIRECTORIES[tool]
    base = Path("04_refinement") / code
    origin = execution.get("native_origin")
    native_run = origin["run_id"] if origin else run_id
    native = base / "03_native" / native_run
    if origin and (not re.fullmatch(r"[0-9a-f]{32}", native_run) or origin.get("native_root") != native.as_posix()
                   or origin.get("receipt") != (base / "02_jobs" / native_run / "native_complete.json").as_posix()):
        raise ReportError("native origin does not identify this tool's owned completion")
    selected = dict(execution.get("artifacts", {}))
    if origin:
        receipt = safe_file(root, origin["receipt"])
        value = json.loads(read_bound(receipt, origin["receipt_sha256"], limit=128 * 1024 * 1024))
        checksum = value.pop("payload_sha256")
        if (checksum != fingerprint(value) or value.get("schema") != "cgat.native-refinement-completion"
                or value.get("schema_version") != 1 or value.get("status") != "completed"
                or value.get("run_id") != native_run or value.get("tool") != tool):
            raise ReportError("native origin completion receipt is invalid")
        for relative, sha in value["result"]["artifacts"].items():
            if relative in selected and selected[relative] != sha:
                raise ReportError("native origin artifact binding changed")
            selected[relative] = sha
        selected[origin["receipt"]] = origin["receipt_sha256"]
    def select(relative):
        file = safe_file(root, relative)
        sha = digest(file)
        if relative in selected and selected[relative] != sha:
            raise ReportError("native evidence changed before report generation: " + relative)
        selected[relative] = sha
        return file, sha
    log = (base / "02_jobs" / native_run / "native.log").as_posix()
    if (root / log).is_file():
        selected.setdefault(log, digest(safe_file(root, log)))
    jobs, native_gaps = [], []
    if tool == "degap":
        gap_report = (native / "03.gap_filling/gap_filling_results.json").as_posix()
        if gap_report in selected:
            native_gaps = json.loads(read_bound(safe_file(root, gap_report), selected[gap_report], limit=128 * 1024 * 1024)).get("gaps", [])
        config = (native / "03.gap_filling/job_manager_config.json").as_posix()
        if (root / config).exists():
            file, sha = select(config)
            payload = json.loads(read_bound(file, sha, limit=MAX_ASSET))
            selected[config] = sha
            for item in payload.get("jobs", []):
                if not item.get("job_dir"):
                    jobs.append({"job_name": item.get("job_name"), "chromosome": item.get("chromosome"),
                                 "native_gap_id": item.get("gap_id"), "direction": item.get("direction"),
                                 "artifacts": [], "diagnostics_availability": "not_recorded"})
                    continue
                job_dir = Path(item["job_dir"])
                if not job_dir.is_absolute():
                    job_dir = root / native / job_dir
                if not job_dir.resolve().is_relative_to((root / native).resolve()):
                    raise ReportError("native job diagnostics leave their attempt")
                files = []
                for name in ("run.stdout.log", "run.stderr.log", "process.log"):
                    file = job_dir / name
                    if file.exists() or file.is_symlink():
                        relative = file.relative_to(root).as_posix()
                        select(relative)
                        files.append(relative)
                jobs.append({"job_name": item.get("job_name"), "chromosome": item.get("chromosome"),
                             "native_gap_id": item.get("gap_id"), "direction": item.get("direction"),
                             "artifacts": files})
        for name in ("autogapfiller_summary.json", "05.visualization/gap_filling_report.html"):
            relative = (native / name).as_posix()
            if (root / relative).exists():
                select(relative)
    if tool == "degap":
        summary_path = (native / "autogapfiller_summary.json").as_posix()
        if summary_path in selected:
            summary = json.loads(read_bound(safe_file(root, summary_path), selected[summary_path], limit=128 * 1024 * 1024))
            results = summary.get("steps", {}).get("step3", {}).get("result", {})
            executions = {row["job_name"]: row for field in ("completed_jobs", "failed_jobs", "skipped_jobs") for row in results.get(field, [])}
            for job in jobs:
                job["execution_result"] = executions.get(job["job_name"], {"status": "not_recorded"})
    return selected, jobs, native_gaps


def asset_plan(root, artifacts):
    rows, total = [], 0
    for relative, expected in sorted(artifacts.items()):
        path = safe_file(root, relative)
        size = path.stat().st_size
        # HTML is retained as escaped source text, not active code with upstream
        # CDN references. The main CGAT report is fully static and offline.
        text = relative.endswith(TEXT_ENDINGS) or relative.endswith(".html")
        include = text and size <= MAX_ASSET and total + size <= MAX_ASSETS_TOTAL
        row = {"workspace_path": relative, "sha256": expected, "size_bytes": size,
               "availability": "embedded" if include else "server_only_size_limit" if text else
                               "server_only_native_script" if relative.endswith(".sh") else "server_only_sequence_or_binary"}
        if include:
            total += size
            row["report_path"] = "assets/" + hashlib.sha256(relative.encode()).hexdigest()[:20] + ".txt"
            row["view"] = "original_html_source" if relative.endswith(".html") else "native_text"
        rows.append(row)
    return rows


def summarize(provenance, final, remaining, jobs, native_gaps):
    if final.get("baseline") != provenance.get("baseline") or final.get("recipe_sha256") != provenance["execution"]["recipe_sha256"]:
        raise ReportError("report Final Path/provenance binding disagrees")
    outcomes = provenance["gap_outcomes"]
    original = {row["gap_id"]: row for row in final["original_gaps"]}
    if len(original) != len(final["original_gaps"]) or len(outcomes) != len(original) or {g["gap_id"] for g in outcomes} != set(original):
        raise ReportError("report omitted or duplicated an original LGZ gap")
    counts = {name: sum(row["status"] == name for row in outcomes) for name in ("closed", "partial", "unfilled", "rejected")}
    if (counts != provenance["counts"] or sum(counts.values()) != len(outcomes)
            or provenance.get("original_gap_count") != len(outcomes)
            or provenance.get("accepted_edit_count") != len(final["edits"])):
        raise ReportError("report counts disagree with the complete original-gap denominator")
    for row in outcomes:
        if any(row[key] != original[row["gap_id"]][key] for key in ("chromosome", "start", "end")):
            raise ReportError("report original gap coordinates changed")
    gap_lookup = defaultdict(list)
    for gap in original.values():
        gap_lookup[gap["chromosome"]].append(gap)
    for rows in gap_lookup.values():
        rows.sort(key=lambda row: row["start"])
    ends = {name: [row["end"] for row in rows] for name, rows in gap_lookup.items()}
    native_by_original = defaultdict(list)
    native_to_original = {}
    for row in native_gaps:
        name, start, end = row.get("chromosome"), row.get("gap_start"), row.get("gap_end")
        if name not in gap_lookup or type(start) is not int or type(end) is not int or end < start:
            continue
        matching = []
        for index in range(bisect_right(ends[name], start), len(gap_lookup[name])):
            gap = gap_lookup[name][index]
            if gap["start"] > end:
                break
            matching.append(gap["gap_id"])
            native_by_original[gap["gap_id"]].append(row)
        native_to_original[(name, str(row.get("gap_id")))] = matching
    for job in jobs:
        job["original_gap_ids"] = native_to_original.get((job["chromosome"], str(job["native_gap_id"])), [])
    n_bases = defaultdict(int)
    for row in remaining:
        n_bases[row["chromosome"]] += int(row["end"]) - int(row["start"])
    comparison = []
    native = provenance["execution"].get("native_assembly", {})
    for row in final["chromosomes"]:
        observed = native.get(row["chr"])
        comparison.append({"chromosome": row["chr"], "accepted_length": row["length"],
                           "accepted_n_bases": n_bases[row["chr"]], "accepted_sha256": row["sha256"],
                           "native": observed, "native_equals_accepted": observed["sha256"] == row["sha256"] if observed else None})
    return {"schema": SCHEMA, "schema_version": 1, "tool": provenance["tool"], "run_id": provenance["run_id"],
            "publication_state": "not_asserted_by_report", "outcome": provenance["status"],
            "baseline": final["baseline"], "original_gap_count": len(outcomes), "counts": counts,
            "accepted_edit_count": provenance["accepted_edit_count"], "remaining_gap_count": len(remaining),
            "chromosomes": comparison, "execution": provenance["execution"], "native_jobs": jobs, "native_gaps_by_original": dict(native_by_original),
            "coordinate_system": "0-based half-open placement; 1-based inclusive sources",
            "biological_accuracy_validated": False, "automatic_best_tool": None}


def render_site(directory, summary, provenance, final, assets):
    rows = summary["chromosomes"]
    body = '<p class="note">Native/admission result report — final delivery requires a separate publication receipt. / 原生与接纳结果报告；最终交付须有独立发布回执。</p>'
    body += '<p>All original LGZ gaps remain in the denominator. Fewer gaps are not proof of accuracy; no best tool is selected. / 保留全部原始缺口，不以缺口更少判定更准确。</p>'
    body += '<p>Coordinates: 0-based half-open. / 坐标采用 0-based 半开区间。</p>'
    body += '<h2>Outcome / 结果</h2><pre>' + json_text({k: summary[k] for k in ("outcome", "original_gap_count", "counts", "accepted_edit_count", "remaining_gap_count")}) + '</pre>'
    body += '<h2>Native versus accepted / 原生与接纳结果</h2>' + table(
        ["Chromosome", "Native length / N", "Accepted length / N", "Same sequence"],
        [(escape(r["chromosome"]), escape(str((r["native"]["length"], r["native"]["n_bases"]))) if r["native"] else "Not produced / 未产生",
          escape(str((r["accepted_length"], r["accepted_n_bases"]))), escape(str(r["native_equals_accepted"]))) for r in rows])
    execution = summary["execution"]
    if execution.get("native_reused"):
        body += '<p class="note">Verified native evidence was reused; the producer did not run in this attempt. CGAT admission and reconstruction ran again. / 本次复用已验证的原生证据，没有重跑工具；CGAT 重新执行接纳与来源重建。</p>'
    body += '<h2>Inputs, recipe and resources / 输入、配方与资源</h2><pre>' + json_text({
        "tool": summary["tool"], "run_id": summary["run_id"], "threads": execution.get("threads"),
        "timing": execution.get("timing", "not recorded"), "peak_rss": "not measured",
        "native_executed_this_attempt": execution.get("native_executed"), "native_reused": execution.get("native_reused", False),
        "native_origin": execution.get("native_origin"), "requested_threads": execution.get("requested_threads", execution.get("threads")),
        "recipe": execution.get("recipe"),
        "command": execution.get("command")}) + '</pre>'
    measured = summary.get("source_evidence")
    if measured is not None:
        sources = measured["sources"]
        body += '<h2>Accepted-source measurements / 精修来源测量</h2><pre>' + json_text({
            "patch_source_placements": len(sources), "reference_status": dict(Counter(row["ref_alignment_status"] for row in sources)),
            "final_annotation_rows": measured["final_annotation_rows"], "policy": measured["annotation_policy"],
            "coordinate_domain": measured["coordinate_domain"]}) + '</pre>'
        body += '<p>Context placement is not a homology claim. Clipped source marks are coordinate projections, not a complete final-genome rescan. / 显示上下文不是同源证据；切片注释是坐标映射，不冒充完整终版基因组重扫描。</p>'
        if sources:
            pages = [sources[i:i + PAGE_SIZE] for i in range(0, len(sources), PAGE_SIZE)]
            body += '<p>' + link("sources-0001.html", "All measured source placements / 全部来源测量") + '</p>'
            for number, rows in enumerate(pages, 1):
                navigation = link("report.html", "Overview / 总览")
                if number > 1:
                    navigation += ' · ' + link(f"sources-{number - 1:04}.html", "Previous / 上一页")
                if number < len(pages):
                    navigation += ' · ' + link(f"sources-{number + 1:04}.html", "Next / 下一页")
                content = navigation + table(["Source dataset", "Contig", "Chromosome", "Length", "Reference measurement", "Hits: this chr / all", "Annotations"], [
                    (escape(row["dataset"]), escape(row["contig"]), escape(row["chromosome"]), escape(str(row["length"])),
                     escape(row["ref_alignment_status"]), escape(f'{row["hits_on_chromosome"]} / {row["reference_hits"]}'),
                     escape(json.dumps(row["annotations"], ensure_ascii=False))) for row in rows])
                (directory / f"sources-{number:04}.html").write_text(page("Accepted-source measurements / 精修来源测量", content), encoding="utf-8")
        files = [row for row in assets if "/01_source_evidence/" in row["workspace_path"] and "/04_projection/" in row["workspace_path"]]
        body += table(["Coordinate/summary artifact", "Availability"], [
            (link(row["report_path"], Path(row["workspace_path"]).name) if row.get("report_path") else escape(Path(row["workspace_path"]).name),
             escape(row["availability"])) for row in files])
    edits = {row["edit_id"]: row for row in final["edits"]}
    rejected = defaultdict(list)
    for row in provenance["rejected_candidates"]:
        for gap_id in row.get("gap_ids", []):
            rejected[gap_id].append(row)
    gaps = provenance["gap_outcomes"]
    jobs_by_gap = defaultdict(list)
    for job in summary["native_jobs"]:
        for gap_id in job["original_gap_ids"]:
            jobs_by_gap[gap_id].append(job)
    links = []
    (directory / "gaps").mkdir()
    for offset in range(0, len(gaps), PAGE_SIZE):
        number = offset // PAGE_SIZE + 1
        relative = f"gaps/{number:06d}.html"
        links.append(link(relative, f"{offset + 1}–{min(offset + PAGE_SIZE, len(gaps))}"))
        content = '<p>' + link("../report.html", "Tool report / 工具报告") + ' · ' + link("../native.html", "Native jobs, reports and logs / 原生任务、报告与日志") + '</p>'
        for gap in gaps[offset:offset + PAGE_SIZE]:
            gid = gap["gap_id"]
            content += '<section id="' + gap_anchor(gid) + '"><h2>' + escape(gid) + '</h2><pre>' + json_text(gap) + '</pre>'
            content += '<h3>Native jobs / 原生任务</h3><p>' + (' · '.join(link("../native.html#" + gap_anchor(str(job["job_name"])), job["job_name"]) for job in jobs_by_gap[gid]) or link("../native.html", "Genome-level native job / 整体原生任务")) + '</p>'
            content += '<pre>' + json_text(summary["native_gaps_by_original"].get(gid, [])) + '</pre>'
            content += '<h3>Accepted changes / 接纳修改</h3><pre>' + json_text([edits[name] for name in gap["edit_ids"]]) + '</pre>'
            content += '<h3>Not accepted / 未接纳</h3><pre>' + json_text(rejected[gid]) + '</pre></section>'
        (directory / relative).write_text(page("Original gaps / 原始缺口", content), encoding="utf-8")
    body += '<h2>Original gap → job → decision / 原始缺口 → 任务 → 接纳</h2><p>' + (' · '.join(links) if links else 'No original gaps / 无原始缺口') + '</p>'
    body += '<h2>Unattributed rejected candidates / 无法归属原始缺口的未接纳候选</h2><pre>' + json_text([row for row in provenance["rejected_candidates"] if not row.get("gap_ids")]) + '</pre>'
    body += '<p>' + link("native.html", "Native job reports and logs / 原生 job 报告与日志") + ' · ' + link("summary.json", "Machine-readable summary") + ' · ' + link("final_path.json", "Accepted sourced Final Path") + '</p>'
    native_body = '<p>' + link("report.html", "Tool report / 工具报告") + '</p><p>Original diagnostics are retained verbatim as text. HTML source is not executed; external CDN scripts are not fetched. Large sequences remain Server-only, with their hashes shown. / 原始诊断以原文保留；不执行原生 HTML 的外部脚本，也不复制大 reads 或整条原生基因组。</p>'
    lookup = {row["workspace_path"]: row for row in assets}
    for job in summary["native_jobs"]:
        native_body += '<h2 id="' + gap_anchor(str(job["job_name"])) + '">' + escape(str(job["job_name"])) + '</h2><pre>' + json_text(job) + '</pre><p>'
        native_body += ' · '.join(link(lookup[name]["report_path"], Path(name).name) for name in job["artifacts"] if "report_path" in lookup[name]) + '</p>'
    native_body += table(["Native artifact", "Availability", "SHA-256"], [(
        link(row["report_path"], row["workspace_path"]) if "report_path" in row else escape(row["workspace_path"]),
        escape(row["availability"]), '<code>' + escape(row["sha256"]) + '</code>') for row in assets])
    (directory / "native.html").write_text(page("Native reports / 原生报告", native_body), encoding="utf-8")
    (directory / "report.html").write_text(page(summary["tool"] + " refinement / 精修", body), encoding="utf-8")


def build_tool_report(root, result):
    root = Path(root).resolve()
    tool, run_id = result["tool"], result["run_id"]
    layout = WorkspaceLayout.detect(root)
    if layout.version != 2 or tool not in TOOL_DIRECTORIES or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ReportError("invalid refinement report workspace/tool/run")
    staging = Path(result["staging"]).resolve()
    if not staging.is_relative_to(root):
        raise ReportError("staged result is outside its workspace")
    provenance_path = safe_file(root, (staging / "provenance.json").relative_to(root).as_posix())
    marker_path = safe_file(root, f"04_refinement/{TOOL_DIRECTORIES[tool]}/02_jobs/{run_id}/invocation.json")
    marker = json.loads(marker_path.read_text())
    sha = marker.get("provenance_sha256")
    provenance = json.loads(read_bound(provenance_path, sha))
    if (marker.get("status") not in {"staged", "published"} or marker.get("tool") != tool or marker.get("run_id") != run_id
            or provenance.get("tool") != tool or provenance.get("run_id") != run_id
            or provenance.get("schema") != "cgat.refinement-publication" or provenance.get("schema_version") != 1):
        raise ReportError("native attempt has no completed content-bound result")
    for name, expected in provenance["artifacts"].items():
        path = safe_file(staging, name)
        if digest(path) != expected:
            raise ReportError("staged report artifact changed: " + name)
    final_bytes = read_bound(staging / "final_path.json", provenance["artifacts"]["final_path.json"])
    final = json.loads(final_bytes)
    with (staging / "remaining_gaps.tsv").open(newline="", encoding="utf-8") as stream:
        remaining = list(csv.DictReader(stream, delimiter="\t"))
    artifacts, jobs, native_gaps = native_diagnostics(root, tool, run_id, provenance["execution"])
    assets = asset_plan(root, artifacts)
    source_binding, source_summary = {}, None
    if result.get("source_evidence"):
        try:
            from refinement_source_evidence import load, verify_inputs, RECEIPT
        except ModuleNotFoundError:
            from .refinement_source_evidence import load, verify_inputs, RECEIPT
        evidence = result["source_evidence"]
        directory = Path(evidence["directory"])
        receipt_path = safe_file(directory, RECEIPT)
        receipt = load(directory)
        if digest(receipt_path) != evidence["receipt_sha256"] or receipt["recipe"]["provenance_sha256"] != sha:
            raise ReportError("source measurements do not bind the reported accepted result")
        verify_inputs(receipt["recipe"])
        source_binding = {"source_evidence_receipt_sha256": evidence["receipt_sha256"],
                          "source_evidence_generation_sha256": receipt["generation_sha256"]}
        artifacts[receipt_path.relative_to(root).as_posix()] = evidence["receipt_sha256"]
        for row in receipt["payload"]:
            artifacts[safe_file(directory, row["file"]).relative_to(root).as_posix()] = row["sha256"]
        source_summary = json.loads(safe_file(directory, "04_projection/summary.json").read_text())
        source_summary["generation_sha256"] = receipt["generation_sha256"]
        assets = asset_plan(root, artifacts)
    summary = summarize(provenance, final, remaining, jobs, native_gaps)
    summary["artifacts"] = assets
    if source_summary is not None:
        summary["source_evidence"] = source_summary
    binding = {"provenance_sha256": sha, "generator_sha256": digest(Path(__file__)), "assets": assets, **source_binding}
    identity = fingerprint(binding)
    home = layout.path(f"04_refinement/{TOOL_DIRECTORIES[tool]}/05_report/{run_id}")
    destination = home / ("site-" + identity[:20])
    if destination.exists():
        receipt = json.loads(safe_file(destination, "manifest.json").read_text())
        if receipt.get("binding") != binding or not all(digest(safe_file(destination, name)) == expected for name, expected in receipt["files"].items()):
            raise ReportError("existing portable report was modified")
        return {"directory": str(destination), "report": str(destination / "report.html"), "manifest_sha256": digest(destination / "manifest.json")}
    home.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".report-build-", dir=home))
    try:
        (temporary / "assets").mkdir()
        for row in assets:
            if "report_path" not in row:
                continue
            data = read_bound(safe_file(root, row["workspace_path"]), row["sha256"], limit=MAX_ASSET)
            (temporary / row["report_path"]).write_bytes(data)
        (temporary / "final_path.json").write_bytes(final_bytes)
        atomic_json(temporary / "summary.json", summary)
        render_site(temporary, summary, provenance, final, assets)
        atomic_json(temporary / "manifest.json", {"schema": SCHEMA, "schema_version": 1, "binding": binding,
                    "files": {p.relative_to(temporary).as_posix(): digest(p) for p in sorted(temporary.rglob("*")) if p.is_file()}})
        if digest(provenance_path) != sha:
            raise ReportError("result changed during report generation")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {"directory": str(destination), "report": str(destination / "report.html"), "manifest_sha256": digest(destination / "manifest.json")}


def build_failure_report(root, tool, run_id, error, *, phase="native"):
    """Explain failed/preflight attempts without inventing any final assembly."""
    root = Path(root).resolve()
    layout = WorkspaceLayout.detect(root)
    if layout.version != 2 or tool not in TOOL_DIRECTORIES or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ReportError("invalid failed-attempt report identity")
    code = TOOL_DIRECTORIES[tool]
    artifacts = {}
    for name in ("invocation.json", "native_jobs.json", "native.log"):
        relative = f"04_refinement/{code}/02_jobs/{run_id}/{name}"
        if (root / relative).exists():
            artifacts[relative] = digest(safe_file(root, relative))
    diagnostics_error = None
    execution = {}
    try:
        invocation_relative = f"04_refinement/{code}/02_jobs/{run_id}/invocation.json"
        if invocation_relative in artifacts:
            execution = json.loads(read_bound(safe_file(root, invocation_relative), artifacts[invocation_relative], limit=MAX_ASSET))
        artifacts, jobs, _ = native_diagnostics(root, tool, run_id, {**execution, "artifacts": artifacts})
    except (OSError, ValueError, KeyError, TypeError) as diagnostic:
        jobs = []
        diagnostics_error = str(diagnostic)
    source_diagnostics = getattr(error, "source_evidence_diagnostics", None)
    if phase == "source_evidence" and source_diagnostics is not None:
        try:
            directory = Path(source_diagnostics)
            parent = layout.path(f"04_refinement/{code}/04_accepted/{run_id}/01_source_evidence")
            if directory.parent != parent or re.fullmatch(r"failed-[0-9a-f]{20}-[0-9a-f]{32}", directory.name) is None:
                raise ReportError("source failure diagnostics are outside this attempt")
            relative = (directory / "failure.json").relative_to(root).as_posix()
            failure = json.loads(safe_file(root, relative).read_text())
            if (failure.get("schema") != "cgat.refinement-source-evidence-failure" or failure.get("schema_version") != 1
                    or failure.get("status") not in {"failed", "interrupted"} or failure.get("recipe", {}).get("tool") != tool
                    or failure.get("recipe", {}).get("run_id") != run_id):
                raise ReportError("source failure diagnostics do not bind this attempt")
            artifacts[relative] = digest(safe_file(root, relative))
            for name, sha in failure["files"].items():
                if name.endswith(TEXT_ENDINGS):
                    relative = (directory / name).relative_to(root).as_posix()
                    if digest(safe_file(root, relative)) != sha:
                        raise ReportError("source failure diagnostic changed")
                    artifacts[relative] = sha
        except (OSError, ValueError, KeyError, TypeError) as diagnostic:
            diagnostics_error = (diagnostics_error + "; " if diagnostics_error else "") + str(diagnostic)
    assets = asset_plan(root, artifacts)
    summary = {"schema": "cgat.refinement-failure-report", "schema_version": 1, "tool": tool, "run_id": run_id,
               "status": "failed", "phase": phase, "error": str(error), "native_jobs": jobs,
               "diagnostics_error": diagnostics_error, "source_diagnostics": str(source_diagnostics) if source_diagnostics else None,
               "final_available": False, "artifacts": assets,
               "native_status": execution.get("native_status"), "native_reused": execution.get("native_reused", False),
               "native_origin": execution.get("native_origin")}
    binding = {"summary": summary, "generator_sha256": digest(Path(__file__))}
    destination = layout.path(f"04_refinement/{code}/05_report/{run_id}/failure-{fingerprint(binding)[:20]}")
    if destination.exists():
        manifest = json.loads(safe_file(destination, "manifest.json").read_text())
        if manifest.get("binding") != binding or not all(digest(safe_file(destination, name)) == sha for name, sha in manifest["files"].items()):
            raise ReportError("failed-attempt report was modified")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".failure-report-", dir=destination.parent))
        try:
            (temporary / "assets").mkdir()
            for row in assets:
                if "report_path" in row:
                    (temporary / row["report_path"]).write_bytes(read_bound(safe_file(root, row["workspace_path"]), row["sha256"], limit=MAX_ASSET))
            atomic_json(temporary / "summary.json", summary)
            body = '<p class="note">This attempt failed. No final result is declared; earlier successful files remain historical. / 本次任务失败，不声明最终结果；先前成功文件仍是历史结果。</p><pre>' + json_text(summary) + '</pre>'
            body += table(["Native/source diagnostic", "Availability"], [(link(row["report_path"], row["workspace_path"]) if "report_path" in row else escape(row["workspace_path"]), escape(row["availability"])) for row in assets])
            (temporary / "report.html").write_text(page(tool + " failed attempt / 失败任务", body), encoding="utf-8")
            atomic_json(temporary / "manifest.json", {"schema": summary["schema"], "schema_version": 1, "binding": binding,
                        "files": {path.relative_to(temporary).as_posix(): digest(path) for path in temporary.rglob("*") if path.is_file()}})
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    return {"directory": str(destination), "report": str(destination / "report.html"), "manifest_sha256": digest(destination / "manifest.json")}
