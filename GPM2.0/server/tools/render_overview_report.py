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
        esc,
        status_badge,
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
        esc,
        status_badge,
        workbench_page,
    )


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
        reason_line = "；".join(esc(r) for r in reasons[:3]) if reasons else bi("请在工作区查看 logs/run_all.log。", "See logs/run_all.log in the workspace.")
        stopped=[r.get('unit') or r.get('stage_id') or r.get('unit_id') for r in lgz.get('timing',{}).get('units',[]) if r.get('status') in ('failed','interrupted')]
        if any(stopped):reason_line+=' · '+', '.join(esc(x) for x in stopped if x)
        if lgz.get('href'):reason_line+=f' · <a href="{esc(lgz["href"])}">'+bi('过程诊断','Stage diagnostics')+'</a>'
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
    ]

    if meta['mode']=='manual_only':
        sidebar=[('manual-refinement','08','手动精修','Manual refinement')]
        body=_run_notices(vm)
    else:
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
            + (DIALOG if vm["refinement_summary"]["tools"] or any(vm["lgz_summary"].get(k) for k in ("step1_scene", "step2_scene", "terminal_scene")) else "")
        )

    html=workbench_page(
        f"{ws_name} · 组装结果",
        f"{ws_name} · Assembly Report",
        '<style>@media (max-width:1024px){.wb-shell{grid-template-columns:minmax(0,1fr)}.wb-sidebar{min-width:0}}</style>'+body,
        subtitle_html=" · ".join(sub_parts),
        badge_html_str=status_badge(status),
        sidebar_items=sidebar,
        page_title_plain=f"{ws_name} · CGAT",
    )
    batches=vm['manual_summary']['batches']
    if batches:
        from refine_report import _with_manual_section
        from render_manual_story import manual_card
        html=_with_manual_section(html,manual_card(batches,html))
    return html
