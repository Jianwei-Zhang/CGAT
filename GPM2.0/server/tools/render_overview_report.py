"""Offline report: source inputs and chromosome groups precede the assembly and delivery views."""
from __future__ import annotations

try:
    from render_final_story import final_card
    from render_gap_story import gap_card
    from render_terminal_story import terminal_card
    from render_repair_story import repair_card, DIALOG
    from render_path_story import input_card, assignment_card, q0_card
    from render_refinement_report import (
        bi,
        callout,
        copy_btn,
        disclosure,
        esc,
        fmt_bytes,
        link,
        status_badge,
        table,
        workbench_page,
    )
except ModuleNotFoundError:
    from .render_final_story import final_card
    from .render_gap_story import gap_card
    from .render_terminal_story import terminal_card
    from .render_repair_story import repair_card, DIALOG
    from .render_path_story import input_card, assignment_card, q0_card
    from .render_refinement_report import (
        bi,
        callout,
        copy_btn,
        disclosure,
        esc,
        fmt_bytes,
        link,
        status_badge,
        table,
        workbench_page,
    )


def _anchor(href, label_html, *, raw=True):
    if not href:
        return ""
    inner = label_html if raw else esc(label_html)
    return f'<a class="link-pill" href="{esc(href)}">{inner}</a>'


def _pickup_label(key):
    if not key:
        return bi("产物", "Artifact")
    fixed = {
        "genome_catalog": ("组装版本目录 (results.tsv)", "Assembly catalog (results.tsv)"),
        "catalog": ("组装版本目录 (results.tsv)", "Assembly catalog (results.tsv)"),
        "lgz": ("LGZ 基线（非精修结果）FASTA", "LGZ baseline FASTA (non-refined)"),
        "lgz_fasta": ("LGZ 基线（非精修结果）FASTA", "LGZ baseline FASTA (non-refined)"),
        "full": ("CGAT App 完整包 (Full)", "CGAT App Full package"),
        "full_package": ("CGAT App 完整包 (Full)", "CGAT App Full package"),
        "light": ("CGAT App 轻量包 (Light)", "CGAT App Light package"),
        "light_package": ("CGAT App 轻量包 (Light)", "CGAT App Light package"),
        "auto": ("自动精修补丁包", "Automatic refinement patch"),
        "auto_patch": ("自动精修补丁包", "Automatic refinement patch"),
        "manual": ("手动精修补丁包", "Manual refinement patch"),
        "manual_patch": ("手动精修补丁包", "Manual refinement patch"),
        "runner_log": ("运行主日志 (run_all.log)", "Main run log (run_all.log)"),
        "run_all_log": ("运行主日志 (run_all.log)", "Main run log (run_all.log)"),
        "run_status": ("阶段状态表 (status.tsv)", "Stage status table (status.tsv)"),
        "status_tsv": ("阶段状态表 (status.tsv)", "Stage status table (status.tsv)"),
    }
    if key in fixed:
        return bi(*fixed[key])
    if key in ("degap", "tgsgapcloser", "quartet", "lrgapcloser"):
        return bi(f"{key} 精修 FASTA", f"{key} refined FASTA")
    if ":" in key:
        prefix, tool = key.split(":", 1)
        if prefix == "tool_fasta":
            return bi(f"{tool} 精修 FASTA", f"{tool} refined FASTA")
        if prefix == "tool_full":
            return bi(f"{tool} App 完整包 (Full)", f"{tool} Full App package")
        if prefix == "tool_light":
            return bi(f"{tool} App 轻量包 (Light)", f"{tool} Light App package")
    return esc(key)


def _tree_role_label(role_key):
    mapping = {
        "inputs": ("输入参考、组装与测序数据", "Reference, assemblies & reads"),
        "alignment": ("参考比对与归属产物", "Reference alignments"),
        "lgz": ("LGZ 构图与迭代步骤", "LGZ q0 & iterative steps"),
        "refinement": ("自动精修原生运行与接纳", "Refinement runs & admission"),
        "final": ("最终发布 FASTA 与目录", "Final published FASTAs"),
        "report": ("离线可视化报告目录", "Offline HTML reports"),
        "delivery": ("CGAT App 交付压缩包", "CGAT App delivery archives"),
        "runtime": ("运行态元数据与校验指针（勿整删）", "Runtime receipts (do not delete)"),
        "library": ("工作区固定版工具库", "Pinned workspace tools"),
        "jobs": ("精修任务索引目录", "Refinement jobs index"),
        "reference": ("参考基因组", "Reference"),
        "assembly_inputs": ("待拼装输入组装", "Input assemblies"),
        "read_inputs": ("测序 Reads 指针", "Read pointers"),
        "q0": ("q0 初始构图", "q0 draft"),
        "lgz_step1": ("Step 1 补丁验证", "Step 1"),
        "lgz_step2": ("Step 2 结构修正与填补", "Step 2"),
        "lgz_step3": ("Step 3 端粒处理与终稿", "Step 3"),
        "lgz_evidence": ("LGZ 证据文件", "LGZ evidence"),
        "automatic_jobs": ("自动精修任务", "Automatic jobs"),
        "manual_jobs": ("手动精修任务", "Manual jobs"),
        "publication_details": ("发布详情", "Publication details"),
        "lgz_report": ("LGZ 过程报告", "LGZ report"),
        "tool_reports": ("工具精修报告", "Tool reports"),
        "gap_comparison": ("跨工具缺口对照", "Gap comparison"),
        "runtime_cache": ("可清理缓存", "Cache"),
        "checkpoints": ("断点校验", "Checkpoints"),
    }
    pair = mapping.get(role_key)
    return bi(*pair) if pair else esc(role_key or "")


def _run_notices(vm):
    meta = vm["meta"]
    lgz = vm["lgz_summary"]
    tools = vm["refinement_summary"]["tools"]
    unconst = lgz.get("q0", {}).get("not_constructed_chromosomes") or 0
    # Failure / interrupt / manual-only banner if applicable
    top_alert = ""
    if meta["mode"] == "manual_only":
        top_alert = callout(
            bi("尚无自动总报告，以下仅展示当前工作区的手动精修批次与产物。", "No automatic overview report yet; showing manual refinement batches only."),
            tone="info",
        )
    elif meta["mode"] == "lgz_failed" or meta["batch_status"] in ("failed", "interrupted", "invalidated"):
        reasons = lgz.get("failure_reasons") or [t["reason"] for t in tools if t.get("reason")]
        reason_line = "；".join(esc(r) for r in reasons[:3]) if reasons else bi("请展开底部诊断查看日志。", "See folded diagnostics for logs.")
        title = bi("本次运行未完成，未声明最终交付产物", "Run did not complete; no final delivery declared")
        if meta["batch_status"] == "invalidated":
            title = bi("当前精修批次已失效", "Current refinement batch is invalidated")
        top_alert = callout(reason_line, tone="err", title=title, title_raw=True)

    warn_unconst = (
        callout(
            bi(
                f"q0 中有 {unconst:,} 条参考染色体未构建，以下仅展示已输出序列。",
                f"{unconst:,} reference chromosome(s) not constructed in q0.",
            ),
            tone="warn",
        )
        if unconst > 0
        else ""
    )

    return top_alert + warn_unconst


def _render_tree_node(node):
    exists = bool(node.get("exists"))
    status = "present" if exists else "missing"
    badge = status_badge(status)
    children = node.get("children") or []
    body_items = []
    for ch in children[:50]:
        ch_path = ch.get("path", "")
        ch_role = _tree_role_label(ch.get("role_key"))
        ch_extra = ""
        if ch.get("file_count"):
            ch_extra += f' <small class="muted">({ch["file_count"]:,} files)</small>'
        sub_list = ""
        if ch.get("children"):
            sub_items = [
                f'<li><code>{esc(sc.get("path", ""))}</code></li>'
                for sc in ch["children"][:30]
            ]
            sub_list = f'<ul class="tree-sublist">{"".join(sub_items)}</ul>'
        body_items.append(
            f'<li class="tree-child"><div class="tree-child-head"><span><code>{esc(ch_path)}</code>'
            + (f' <span class="muted">— {ch_role}</span>' if ch_role else "")
            + f'{ch_extra}</span>{copy_btn(ch_path)}</div>{sub_list}</li>'
        )
    if len(children) > 50:
        body_items.append(f'<li class="tree-child muted">{bi("（仅预览前 50 项）", "(Preview capped at 50 items)")}</li>')
    body_html = f'<div class="tree-body"><ul class="tree-children">{"".join(body_items)}</ul></div>' if body_items else ""
    cnt_tag = f'<span>{node["file_count"]:,} files</span>' if node.get("file_count") else ""
    return (
        '<details class="tree-node">'
        '<summary><span class="tree-node-main"><span class="tree-caret">▸</span>'
        f'<span class="tree-path">{esc(node.get("path", ""))}</span>'
        f'<span class="tree-role">{_tree_role_label(node.get("role_key"))}</span></span>'
        f'<span class="tree-node-right">{cnt_tag}{badge}</span></summary>'
        f'{body_html}</details>'
    )


def _render_result_files_and_diagnostics(vm):
    meta = vm["meta"]
    lgz = vm["lgz_summary"]
    ref = vm["refinement_summary"]
    rp = vm["result_paths"]
    pickup_rows = rp["quick_pickup"]
    tree_nodes = rp["directory_tree"]
    maint = rp.get("maintenance") or {}
    manual_batches = vm["manual_summary"]["batches"]

    is_detached = bool(pickup_rows) and all(r.get("href") is None for r in pickup_rows)
    detached_note = (
        f'<p class="muted" style="margin-bottom:.5rem">{bi("独立便携副本说明：工作区外链已省略，请复制路径回原工作区取件。", "Detached portable copy: workspace hyperlinks omitted; copy paths to fetch files.")}</p>'
        if is_detached else ""
    )

    # Active deliverables table (strictly clean pickup)
    active_rows = []
    detail_rows = []
    for r in pickup_rows:
        st = r.get("status", "missing")
        path = r.get("relpath") or ""
        lbl_html = _pickup_label(r.get("label_key") or r.get("label"))
        if r.get("category") in ("log", "logs") or r.get("label_key") in ("runner_log", "run_status", "run_all_log", "status_tsv"):
            if path:
                detail_rows.append((lbl_html, r))
            continue
        if path and st in ("published", "observed", "present", "pending_app_import", "no_patch"):
            acts = []
            if r.get("href"):
                acts.append(link(r["href"], bi("打开", "Open"), raw=True))
            acts.append(copy_btn(path))
            active_rows.append((
                lbl_html,
                f'<code>{esc(path)}</code>',
                status_badge(st),
                f'<span class="action-inline">{"".join(acts)}</span>',
            ))
        if path:
            detail_rows.append((lbl_html, r))

    pickup_table = table(
        [bi("产物", "Artifact"), bi("工作区路径", "Workspace Path"), bi("状态", "Status"), bi("操作", "Action")],
        active_rows,
        empty=bi("当前暂无已发布的交付产物。", "No published deliverables yet."),
    )

    # Manual refinement section if present
    manual_html = ""
    if manual_batches:
        m_rows = []
        for b in manual_batches:
            b_href = link(b["report_href"], bi("批次报告", "Batch report"), raw=True) if b.get("report_href") else '<span class="muted">—</span>'
            cnts = " · ".join(f"{esc(k)} {v}" for k, v in (b.get("result_counts") or {}).items()) or "—"
            m_rows.append((
                f'<code>{esc(b["batch_sha256"][:12])}</code>',
                status_badge(b["report_status"]),
                cnts,
                f'<code>{esc(b.get("patch_relpath", ""))}</code>',
                b_href,
            ))
        manual_html = (
            f'<h3>{bi("手动精修批次", "Manual Refinement Batches")}</h3>'
            + table([bi("批次", "Batch"), bi("状态", "Status"), bi("结果", "Results"), bi("补丁路径", "Patch"), bi("报告", "Report")], m_rows)
        )

    # Fold 1: Workspace directory tree & maintenance
    cmd_box = ""
    if maint.get("preview_command"):
        cmd = maint["preview_command"]
        cmd_box = (
            f'<div class="cmd-box"><span><small class="muted">{bi("空间清理预览（dry-run）：", "Cleanup preview (dry-run):")}</small> '
            f'<code>{esc(cmd)}</code></span>{copy_btn(cmd, zh="复制命令", en="Copy cmd")}</div>'
        )
    tree_inner = (
        f'<p class="muted">{bi("请勿整删 .runtime/（保留发布指针与校验记录）；可安全清理中间缓存。", "Do not delete .runtime/ (holds publication pointers & receipts).")}</p>'
        + cmd_box
        + '<div id="ws-tree" data-tree-root="1">'
        '<div class="tree-controls">'
        f'<span class="muted">{bi("工作区结构（默认折叠）", "Workspace tree (collapsed)")}</span>'
        '<span class="action-inline">'
        f'<button type="button" class="ctrl-btn" data-tree-action="expand">{bi("展开", "Expand")}</button>'
        f'<button type="button" class="ctrl-btn" data-tree-action="collapse">{bi("收起", "Collapse")}</button>'
        '</span></div>'
        f'<div class="tree-list">{"".join(_render_tree_node(n) for n in tree_nodes)}</div></div>'
    )
    tree_fold = disclosure(bi("工作区目录结构与维护", "Workspace Directory & Maintenance"), tree_inner)

    tools = ref.get("tools") or []

    # Fold 4: Advanced diagnostics, checksums/logs & compatibility sub-reports
    compat_links = []
    if lgz.get("href"):
        compat_links.append(_anchor(lgz["href"], bi("LGZ 完整过程报告", "LGZ Full Process Report")))
    for t in tools:
        tname = t["tool"]
        if t.get("report_href"):
            lbl = bi(f"{tname} 工具汇总与日志", f"{tname} tool summary") if t.get("publication_verified") else bi(f"{tname} 工作区诊断", f"{tname} Attempt diagnostics (workspace)")
            compat_links.append(_anchor(t["report_href"], lbl))

    d_rows = []
    for lbl_html, r in detail_rows:
        st = r.get("status", "missing")
        path = r.get("relpath") or ""
        sha = r.get("sha256_short") or (r.get("sha256")[:12] if r.get("sha256") else None)
        d_rows.append((
            lbl_html,
            f'<code>{esc(path)}</code>',
            status_badge(st),
            f'<span class="num">{esc(fmt_bytes(r.get("size_bytes")))}</span>',
            f'<code>{esc(sha)}</code>' if sha else '<span class="muted">—</span>',
        ))
    diag_inner = (
        (f'<p class="muted">{bi("底层过程与工具汇总报告（高级排障）：", "Underlying process & tool reports (advanced troubleshooting):")}</p><div class="link-row">{"".join(compat_links)}</div>' if compat_links else "")
        + (
            f'<h3>{bi("产物大小、校验值与运行日志", "Artifact Sizes, Checksums & Logs")}</h3>'
            + table([bi("项目", "Item"), bi("路径", "Path"), bi("状态", "Status"), bi("大小", "Size"), "SHA256"], d_rows)
            if d_rows else ""
        )
    )
    diag_fold = disclosure(bi("高级诊断、校验值与底层过程报告", "Advanced Diagnostics, Checksums & Sub-Reports"), diag_inner)

    return (
        '<section id="result-files" class="panel">'
        f'<div class="panel-head"><h2>{bi("结果取件", "Result Pickup")}</h2></div>'
        + detached_note
        + pickup_table
        + manual_html
        + '</section>'
        + '<section id="diagnostics-fold" class="panel">'
        + tree_fold
        + diag_fold
        + '</section>'
    )


def render_overview(vm):
    meta = vm["meta"]
    ws_name = meta.get("workspace_name") or "CGAT Workspace"
    batch_id = meta.get("batch_id")
    status = meta.get("batch_status") or "unknown"
    gen_at = meta.get("generated_at") or ""

    sub_parts = []
    if batch_id:
        sub_parts.append(f'<span>Batch <code>{esc(batch_id[:12])}</code></span>')
    if gen_at:
        sub_parts.append(f'<span>{esc(gen_at)}</span>')

    sidebar = [
        ("inputs", "01", "输入数据", "Inputs"),
        ("chr-groups", "02", "染色体分组", "Chromosome groups"),
        ("alignment-q0", "03", "初始路径 q0", "Initial path q0"),
        ("first-repair", "04", "第一轮修补", "First repair"),
        ("structural-repair", "05", "结构修正", "Structural correction"),
        ("terminal-process", "", "端粒处理", "Telomeres"),
        *([("auto-refinement", "06", "自动精修", "Automatic refinement")] if vm["refinement_summary"]["tools"] else []),
        *([("final-path", "07" if vm["refinement_summary"]["tools"] else "06", "Final Path", "Final Path")] if meta["mode"] not in ("lgz_failed", "manual_only") else []),
        ("result-files", "", "结果取件", "Result Pickup"),
        ("diagnostics-fold", "", "诊断与明细", "Diagnostics"),
    ]

    body = (
        _run_notices(vm)
        + input_card(vm["lgz_summary"]["inputs"])
        + assignment_card(vm["lgz_summary"].get("assignment", {}))
        + q0_card(vm["lgz_summary"])
        + repair_card(vm["lgz_summary"])
        + repair_card(vm["lgz_summary"], structural=True)
        + terminal_card(vm["lgz_summary"])
        + gap_card(vm)
        + final_card(vm)
        + _render_result_files_and_diagnostics(vm)
        + (DIALOG if vm["refinement_summary"]["tools"] or any(vm["lgz_summary"].get(k) for k in ("step1_scene", "step2_scene", "terminal_scene")) else "")
    )

    return workbench_page(
        f"{ws_name} · 组装结果",
        f"{ws_name} · Assembly Report",
        body,
        subtitle_html=" · ".join(sub_parts),
        badge_html_str=status_badge(status),
        sidebar_items=sidebar,
        page_title_plain=f"{ws_name} · CGAT",
    )
