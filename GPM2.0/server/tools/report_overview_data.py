"""Read-only, JSON-safe overview contract v1. Paths are physical; hrefs are relative
to the overview. See docs/server-report-viewmodel-contract-20261124.md. Never use
a directory's mtime as provenance or serialize a raw LGZ event/native recipe.
"""

from collections import Counter
from datetime import datetime, timezone
import csv
from pathlib import Path
import re

from report_inventory import SHA, file_href, obj, physical, pickup, tree
from report_gap_story import baseline_lengths, checked_json, gap_evidence, native_views
from report_lgz_data import collect, counts, safe_name
from server_report_io import layout_descriptor
from render_server_report import REPORT_PREVIEW_ROWS
from render_refinement_report import PAGE_SIZE, gap_anchor
from run_orchestration import sha256_file
from workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES

BATCH = re.compile("[a-f0-9]{32}")
OUTCOMES = ("closed", "partial", "unfilled", "rejected")


def _safe_float(value, *, positive_only=False):
    if value in (None, ""):
        return None
    try:
        v = float(value)
        if v != v or v in (float("inf"), float("-inf")):
            return None
        if positive_only and v <= 0:
            return None
        if not positive_only and v < 0:
            return None
        return v
    except (ValueError, TypeError):
        return None


def _manual_tool_timing(root, batch_dir):
    """Aggregate per-tool elapsed_seconds / peak_rss_mb from verified manual job receipts."""
    jobs_dir = batch_dir / "02_jobs"
    if not jobs_dir.is_dir() or jobs_dir.is_symlink():
        return {}
    agg = {}
    for receipt_name in ("completion.json", "failure.json"):
        for path in sorted(jobs_dir.rglob(receipt_name)):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                rel = path.relative_to(root).as_posix()
                data = obj(root, rel)
            except (OSError, ValueError, KeyError, TypeError):
                continue
            trec = data.get("timing")
            if not isinstance(trec, dict):
                continue
            row = data.get("row") if isinstance(data.get("row"), dict) else {}
            tool = row.get("tool") or data.get("tool")
            if not safe_name(tool):
                continue
            sec = _safe_float(trec.get("elapsed_seconds"))
            rss = _safe_float(trec.get("peak_rss_mb"), positive_only=True)
            st = trec.get("started_at") if isinstance(trec.get("started_at"), str) else None
            en = trec.get("ended_at") if isinstance(trec.get("ended_at"), str) else None
            slot = agg.setdefault(tool, {"tool": tool, "elapsed_seconds": 0.0, "peak_rss_mb": None,
                                         "started_at": None, "ended_at": None, "attempt_count": 0})
            slot["attempt_count"] += 1
            if sec is None:
                slot["elapsed_seconds"] = None
            elif slot["elapsed_seconds"] is not None:
                slot["elapsed_seconds"] = round(slot["elapsed_seconds"] + sec, 3)
            if rss is not None:
                slot["peak_rss_mb"] = max(slot["peak_rss_mb"] or 0.0, rss)
            if st and (slot["started_at"] is None or st < slot["started_at"]):
                slot["started_at"] = st
            if en and (slot["ended_at"] is None or en > slot["ended_at"]):
                slot["ended_at"] = en
    return agg


def manual_batches(layout, verify_content=False):
    from refine_report import INDEX_SCHEMA, REPORT_SCHEMA, _batch_dir, manual_patch_path
    from report_manual_story import collect_manual_story

    root = layout.root
    index = "06_report/manual_refinement.json"
    if not file_href(root, index):
        return []
    data = obj(root, index)
    if data.get("schema") != INDEX_SCHEMA or not isinstance(data.get("batches"), list):
        raise ValueError("invalid manual index")
    batches = []
    for row in data["batches"]:
        batch = row["batch_sha256"]
        status = row["report_status"]
        if not SHA.fullmatch(batch) or status not in ("pending_app_import", "no_patch"):
            raise ValueError("invalid manual batch")
        home = _batch_dir(layout, batch).relative_to(root).as_posix() + "/03_report"
        patch = manual_patch_path(layout, batch).relative_to(root).as_posix()
        digest = None
        summary = {}
        reads = []
        if file_href(root, home + "/summary.json"):
            summary = obj(root, home + "/summary.json")
            if summary.get("batch_sha256") != batch or summary.get("report_schema") != REPORT_SCHEMA:
                raise ValueError("manual summary identity changed")
            if summary.get("delivery") == patch and SHA.fullmatch(summary.get("delivery_sha256") or ""):
                digest = summary["delivery_sha256"]
            reads = [
                dict(technology=r["technology"], sha256=r["sha256"])
                for group in summary.get("reads", {}).values()
                for r in group
                if r.get("technology") in ("hifi", "ont") and SHA.fullmatch(r.get("sha256") or "")
            ]
        owner_rel = str(Path(home).parent / "manual-delivery.json")
        owner = obj(root, owner_rel) if file_href(root, owner_rel) else {}
        owned = bool(
            digest
            and owner.get("batch") == batch
            and (
                owner.get("state") == "committed"
                and owner.get("relative") == patch
                and owner.get("sha256") == digest
                or owner.get("schema") == "cgat.manual-genome-publication.v1"
                and owner.get("files", {}).get("patch") == digest
            )
        )
        result_counts = Counter(r["status"] for r in row["results"] if safe_name(r.get("status")))
        bdir = _batch_dir(layout, batch)
        tool_timing = _manual_tool_timing(root, bdir)
        batches.append(
            dict(
                batch_sha256=batch,
                report_status=status,
                completed_at=row.get("completed_at"),
                result_counts=dict(result_counts),
                tool_timing=tool_timing,
                story=collect_manual_story(layout,batch,bdir,summary,owner,owned,verify_content),
                report_href=file_href(root, home + "/report.html"),
                summary_relpath=home + "/summary.json",
                patch_relpath=patch,
                delivery_sha256=digest,
                publication_verified=owned,
                reads=reads,
            )
        )
    return batches


def current_completion(layout, run=None, *, recover=False):
    """Choose by overview content, never by mtime. Standalone refinement has a different run ID."""
    from refine_report import automatic_overview_digest

    root = layout.root
    overview = "06_report/report.html"
    if not file_href(root, overview):
        return None
    expected = automatic_overview_digest(physical(root, overview))
    idx = (
        "04_refinement/automatic" if layout.project_delivery else "08_refinement_jobs/01_automatic"
    ) + "/index.json"
    candidates = []
    if file_href(root, idx):
        index = obj(root, idx)
        relative = index.get("completion", "")
        if index.get("schema") != "cgat.refinement-jobs-index.v1" or not re.fullmatch(
            r"\.runtime/refinement/completions/[\w.-]+\.json", relative
        ):
            raise ValueError("invalid completion index")
        candidates.append(relative)
    if safe_name(run):
        candidates.append(f".runtime/refinement/completions/{run}.json")
    seen = set()

    def matches(rel):
        if rel in seen or not file_href(root, rel):
            return False
        seen.add(rel)
        receipt = obj(root, rel)
        before = receipt.get("overview_files", {}).get(overview)
        if before == expected:
            return True
        intent = f".runtime/refinement/overview-refresh/{Path(rel).stem}.json"
        if recover and file_href(root, intent):
            plan = obj(root, intent)
            return (
                before == plan.get("before")
                and expected == plan.get("after")
                and receipt.get("batch_sha256") == plan.get("batch_sha256")
            )
        return False

    for rel in candidates:
        if matches(rel):
            return rel
    home = physical(root, ".runtime/refinement/completions")
    others = [p.relative_to(root).as_posix() for p in home.glob("*.json")]
    matched = [rel for rel in others if matches(rel)]
    if len(matched) == 1:
        return matched[0]
    if others:
        raise ValueError("no unique completion binds the current overview")
    return None


def read_current_batch(layout, run=None):
    """Read and validate the bound batch and comparison files."""
    root = layout.root
    completion = current_completion(layout, run)
    if not completion:
        return None
    c = obj(root, completion)
    batch = c["batch_id"]
    if (
        not BATCH.fullmatch(batch)
        or c.get("schema") != "cgat.refinement-invocation"
        or c.get("schema_version") != 1
        or Path(completion).stem != c.get("run_id")
    ):
        raise ValueError("invalid completion identity")
    rel = f".runtime/refinement/batches/{batch}.json"
    path = physical(root, rel)
    if sha256_file(path) != c.get("batch_sha256"):
        raise ValueError("unbound batch")
    data = obj(root, rel)
    if (
        data.get("batch_id") != batch
        or data.get("schema") != "cgat.refinement-batch"
        or data.get("schema_version") != 1
    ):
        raise ValueError("invalid batch identity")
    base = f"06_report/03_comparison/{batch}"
    if data["tools"] or not layout.project_delivery:
        for name in ("comparison.json", "original_gaps.json", "gap_comparison.tsv"):
            rel = f"{base}/{name}"
            if sha256_file(physical(root, rel)) != c["overview_files"].get(rel):
                raise ValueError("unbound comparison")
    return data


def matrix(layout, base, tools, expected, story_rows=None):
    rel = base + "/gap_comparison.tsv"
    rows = []
    chrom = {}
    n = 0
    seen = set()
    with physical(layout.root, rel).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        if reader.fieldnames[:4] != ["gap_id", "chromosome", "start", "end"] or sorted(
            reader.fieldnames[4:]
        ) != sorted(tools):
            raise ValueError("comparison columns changed")
        for r in reader:
            name = r["chromosome"]
            gap = r["gap_id"]
            start, end = int(r["start"]), int(r["end"])
            if None in r or not safe_name(name) or not safe_name(gap) or start < 0 or start >= end or gap in seen:
                raise ValueError("invalid original gap")
            seen.add(gap)
            n += 1
            values = {}
            c = chrom.setdefault(name, {"chromosome": name, "original_gap_count": 0, "tools": {}})
            c["original_gap_count"] += 1
            for t in tools:
                state = r[t]
                values[t] = state
                if state not in OUTCOMES and not re.fullmatch(r"tool_[a-z_]+", state or ""):
                    raise ValueError("unknown gap decision")
                counter = c["tools"].setdefault(
                    t, dict.fromkeys((*OUTCOMES, "not_evaluated", "original_gap_count"), 0)
                )
                counter[state if state in OUTCOMES else "not_evaluated"] += 1
                counter["original_gap_count"] += 1
            item = dict(gap_id=gap, chromosome=name, start=start, end=end, tools=values)
            if story_rows is not None:
                story_rows.append(item)
            if n <= REPORT_PREVIEW_ROWS:
                rows.append(item)
    if n != expected:
        raise ValueError("comparison does not contain the complete original denominator")
    return list(chrom.values()), dict(
        rows=rows,
        total_gap_count=n,
        preview_count=len(rows),
        truncated=n > len(rows),
        full_tsv_href=file_href(layout.root, rel),
        source=rel,
        coordinate_system="lgz_0_based_half_open",
    )


def sanitized_reason(text):
    # Fail closed for free text containing absolute paths (including spaces).
    if not isinstance(text, str):
        return None
    return (
        "See workspace diagnostics (paths omitted)"
        if re.search(r'(?:^|[\s=:"\'])/(?![ >])|[A-Za-z]:[\\/]', text)
        else text[:500]
    )


def refinement(layout, batch):
    from refinement_commit import current_publication

    root = layout.root
    out = dict(
        tools=[],
        by_chromosome=[],
        original_loci=[],
        baseline_lengths={},
        comparison_href=None,
        best_tool=None,
        biological_accuracy_validated=False,
        gap_matrix=dict(
            total_gap_count=None,
            preview_count=0,
            truncated=False,
            rows=[],
            full_tsv_href=None,
            source=None,
            coordinate_system="lgz_0_based_half_open",
        ),
    )
    if not batch or layout.project_delivery and not batch["tools"]:
        return out
    bid = batch["batch_id"]
    tools = batch["tools"]
    if not BATCH.fullmatch(bid) or set(tools) - TOOL_DIRECTORIES.keys():
        raise ValueError("invalid comparison batch")
    base = f"06_report/03_comparison/{bid}"
    data = obj(root, base + "/comparison.json")
    if (
        data.get("schema") != "cgat.refinement-comparison"
        or data.get("schema_version") != 1
        or data["batch_id"] != bid
        or data["batch_status"] != batch["status"]
        or sorted(r["tool"] for r in data["tools"]) != sorted(tools)
    ):
        raise ValueError("comparison identity mismatch")
    out["comparison_href"] = file_href(root, base + "/comparison.json")
    if data["baseline_valid"] and data["original_gap_count"] is not None:
        out["by_chromosome"], out["gap_matrix"] = matrix(layout, base, tools, data["original_gap_count"], out["original_loci"])
    for r in data["tools"]:
        tool = r["tool"]
        rec = tools[tool]
        code = TOOL_DIRECTORIES[tool]
        run = rec.get("run_id")
        status = rec["status"]
        pub = False
        links = {}
        diag = None
        if status == "published" and batch["status"] != "invalidated":
            journal = current_publication(root, tool, verify=False)
            if (
                journal
                and journal["run_id"] == run
                and journal["transaction"]
                == rec.get("publication_transaction")
                == r.get("publication_transaction")
            ):
                folder = f"06_report/02_refinement/{code}"
                sha = journal["areas"]["report"]["new"]["files"]["manifest.json"]
                pub = (
                    sha == rec.get("report", {}).get("manifest_sha256")
                    and file_href(root, folder + "/manifest.json")
                    and sha256_file(root / folder / "manifest.json") == sha
                    and file_href(root, folder + "/report.html")
                    and sha256_file(root / folder / "report.html")
                    == journal["areas"]["report"]["new"]["files"].get("report.html")
                    and file_href(root, layout.relative("07_delivery/" + code + "/delivery.json"))
                    and sha256_file(layout.path("07_delivery/" + code + "/delivery.json"))
                    == journal["areas"]["delivery"]["new"]["files"].get("delivery.json")
                )
            if pub:
                diag = file_href(root, folder + "/report.html")
                for k in ("assembly.fa", "final_path.json", "provenance.json"):
                    links[k] = file_href(root, layout.relative("05_final/" + code + "/" + k))
                delivery = obj(root, layout.relative("07_delivery/" + code + "/delivery.json"))
                if layout.project_delivery:
                    from project_delivery_publish import tool_links

                    for k, v in tool_links(layout, tool, run, delivery["light_manifest"]).items():
                        links[k] = file_href(root, v)
                else:
                    for k in ("full", "light"):
                        links[k] = file_href(root, "07_delivery/" + code + "/" + delivery["archives"][k]["file"])
            else:
                status = "publication_unverified"
        if not diag and status != "publication_unverified" and (rec.get("report") or {}).get("report"):
            p = Path(rec["report"]["report"])
            if p.is_relative_to(root) and p.name == "report.html":
                path = p.relative_to(root).as_posix()
                manifest = str(Path(path).with_name("manifest.json"))
                if (
                    file_href(root, manifest)
                    and file_href(root, path)
                    and sha256_file(root / manifest) == rec["report"].get("manifest_sha256")
                    and sha256_file(root / path) == obj(root, manifest).get("files", {}).get("report.html")
                ):
                    diag = file_href(root, path)
        if not diag and run and safe_name(run):
            diag = file_href(root, layout.relative(f"04_refinement/{code}/02_jobs/{run}/native.log"))
        extra = {}
        execution = {}
        gap_links = {}
        native_global_href = None
        decisions, job_views, global_view = {}, {}, None
        if pub:
            summary_rel = folder + "/summary.json"
            if (
                sha256_file(physical(root, summary_rel))
                != obj(root, folder + "/manifest.json")["files"]["summary.json"]
            ):
                raise ValueError("published tool summary changed")
            summary = obj(root, summary_rel)
            if summary.get("tool") != tool or summary.get("run_id") != run:
                raise ValueError("tool summary identity changed")
            if data["baseline_valid"] and data["original_gap_count"] is not None:
                final_dir = layout.relative(f"05_final/{code}")
                files = journal["areas"]["final"]["new"]["files"]
                prov = checked_json(layout, final_dir, "provenance.json", files)
                final = checked_json(layout, final_dir, "final_path.json", files)
                if (prov.get("tool"), prov.get("run_id")) != (tool, run):
                    raise ValueError("committed tool evidence has different identity")
                for chrom, size in baseline_lengths(final).items():
                    if out['baseline_lengths'].setdefault(chrom,size)!=size:
                        raise ValueError('published tools do not share original chromosome lengths')
                decisions = gap_evidence(out["original_loci"], tool, prov, final)
                job_views, global_view = native_views(layout, folder, summary,
                    journal["areas"]["report"]["new"]["files"], decisions)
            execution = summary.get("execution", {})
            extra = counts(summary, ("retained_flank_count", "accepted_edit_count", "remaining_gap_count"))
            preview_ids = {row["gap_id"] for row in out["gap_matrix"]["rows"]}
            nv = summary.get("native_visualization") or {}
            view_by_source = {}
            view_by_name = {}
            for view in nv.get("views") or []:
                if not isinstance(view, dict):
                    continue
                wp = view.get("wrapper_path")
                if not isinstance(wp, str) or not wp:
                    continue
                vhref = file_href(root, folder + "/" + wp)
                if not vhref:
                    continue
                vname = view.get("name")
                if isinstance(vname, str) and vname:
                    view_by_name[vname] = vhref
                    if vname == "Global.report.html":
                        native_global_href = vhref
                for src_item in view.get("sources") or []:
                    if isinstance(src_item, dict) and isinstance(src_item.get("source_path"), str):
                        view_by_source[src_item["source_path"]] = vhref
            for job in summary.get("native_jobs") or []:
                if not isinstance(job, dict):
                    continue
                jname = job.get("job_name")
                vhref = view_by_source.get(job.get("visualization_html")) or (
                    view_by_name.get(f"{jname}.html") if isinstance(jname, str) else None
                )
                if not vhref:
                    continue
                for gid in job.get("original_gap_ids") or []:
                    if safe_name(gid) and (not preview_ids or gid in preview_ids):
                        entry = dict(href=vhref, kind="native_job")
                        if safe_name(jname):
                            entry["job_name"] = jname
                        if isinstance(job.get("native_gap_id"), int):
                            entry["native_gap_id"] = job["native_gap_id"]
                        gap_links[gid] = entry
            for idx, row in enumerate(out["gap_matrix"]["rows"]):
                gid = row["gap_id"]
                if gid in gap_links:
                    continue
                page_no = idx // PAGE_SIZE + 1
                page_href = file_href(root, f"{folder}/gaps/{page_no:06d}.html")
                if page_href:
                    gap_links[gid] = dict(href=page_href, anchor=gap_anchor(gid), kind="gap_card")
        raw_t = execution.get("timing") if isinstance(execution.get("timing"), dict) else {}
        origin = execution.get("native_origin") if isinstance(execution.get("native_origin"), dict) else {}
        tool_elapsed = _safe_float(
            raw_t.get("before_publication_seconds")
            if raw_t.get("before_publication_seconds") is not None else
            (raw_t.get("native_seconds") if raw_t.get("native_seconds") is not None else origin.get("native_seconds"))
        )
        tool_native_sec = _safe_float(
            raw_t.get("native_seconds") if raw_t.get("native_seconds") is not None else origin.get("native_seconds")
        )
        tool_rss = _safe_float(
            raw_t.get("peak_rss_mb") if raw_t.get("peak_rss_mb") is not None else origin.get("peak_rss_mb"),
            positive_only=True,
        )
        tool_started = (raw_t.get("started_at") if isinstance(raw_t.get("started_at"), str) else None) or (
            origin.get("started_at") if isinstance(origin.get("started_at"), str) else None
        )
        tool_ended = (raw_t.get("admission_finished_at") if isinstance(raw_t.get("admission_finished_at"), str) else None) or (
            origin.get("ended_at") if isinstance(origin.get("ended_at"), str) else None
        )
        tool_timing = (
            dict(elapsed_seconds=tool_elapsed, native_seconds=tool_native_sec,
                 peak_rss_mb=tool_rss, started_at=tool_started, ended_at=tool_ended)
            if any(v is not None for v in (tool_elapsed, tool_native_sec, tool_rss, tool_started, tool_ended))
            else None
        )
        out["tools"].append(
            dict(
                **extra,
                tool=tool,
                status="invalidated" if batch["status"] == "invalidated" else status,
                run_id=run,
                result_reused=bool(r.get("result_reused")),
                native_reused=bool(r.get("native_reused")),
                native_executed=execution.get("native_executed", r.get("native_executed")),
                native_status=execution.get("native_status", r.get("native_status")),
                phase=rec.get("phase"),
                timing=tool_timing,
                counts=counts(r["counts"], OUTCOMES) if r.get("counts") is not None else None,
                reason=sanitized_reason(rec.get("error")),
                publication_verified=bool(pub),
                report_href=diag,
                native_global_href=native_global_href,
                gap_links=gap_links,
                gap_decisions=decisions,
                degap_jobs_by_gap=job_views,
                degap_global_href=global_view,
                links=links,
            )
        )
    return out


def build_overview_view_model(root, batch=None, *, mode=None, verify_content=False, generated_at=None):
    layout = WorkspaceLayout.detect(root)
    lgz = collect(layout)
    manual = manual_batches(layout, verify_content)
    if len(lgz["diagnostics"]) > 200:
        lgz["diagnostics"] = lgz["diagnostics"][:200]
    if batch is None and mode not in ("lgz_failed", "manual_only") and layout.version == 2:
        batch = read_current_batch(layout, lgz.get("run_id"))
    ref = refinement(layout, batch)
    if ref["gap_matrix"]["total_gap_count"] is not None:
        by_name = {r["chromosome"]: r for r in ref["by_chromosome"]}
        for c in lgz["chromosomes"]:
            by_name.setdefault(
                c["chromosome"],
                dict(
                    chromosome=c["chromosome"],
                    original_gap_count=0,
                    tools={
                        t["tool"]: dict.fromkeys((*OUTCOMES, "not_evaluated", "original_gap_count"), 0)
                        for t in ref["tools"]
                    },
                ),
            )
        ref["by_chromosome"] = list(by_name.values())
    status = (batch or {}).get("status") or lgz.get("status")
    detect_mode = mode is None
    if detect_mode:
        mode = (
            "full_pipeline"
            if batch and batch["tools"]
            else "lgz_failed"
            if status in ("failed", "interrupted")
            else "manual_only"
            if not batch and manual
            else "lgz_only"
        )
    exit_code = (batch or {}).get("exit_code")
    if mode == "lgz_failed":
        exit_code = next(
            (
                int(r["exit_code"])
                for r in lgz["timing"]["units"]
                if r["status"] in ("failed", "interrupted") and str(r.get("exit_code")).isdigit()
            ),
            None,
        )
    from report_final_story import final_versions
    pickups = pickup(layout, batch, manual, verify_content)
    finals = final_versions(layout, lgz, ref, batch, pickups, mode, verify_content)
    if detect_mode and mode=='manual_only' and lgz.get('final_fasta_sha256'):
        # Older LGZ-only runs have no automatic-refinement completion. Preserve
        # their verified baseline before appending 08, but never borrow stale q3.
        finals=final_versions(layout,lgz,ref,batch,pickups,'lgz_only',verify_content)
        if finals:mode='lgz_only'
    return dict(
        meta=dict(
            schema_version="cgat.report-overview.v1",
            workspace_name=layout.root.name,
            workspace_layout=layout_descriptor(layout),
            batch_id=(batch or {}).get("batch_id"),
            batch_status=status,
            exit_code=exit_code,
            generated_at=generated_at
            or (batch or {}).get("ended_at")
            or lgz["ended_at"]
            or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            mode=mode,
        ),
        lgz_summary=lgz,
        refinement_summary=ref,
        manual_summary=dict(batches=manual),
        final_versions=finals,
        result_paths=dict(
            quick_pickup=pickups,
            directory_tree=tree(layout),
            maintenance={
                "never_delete_runtime": True,
                "preview_command": "python -B .lib/tools/compact_refinement.py"
                if layout.project_delivery
                else None,
            },
        ),
    )
