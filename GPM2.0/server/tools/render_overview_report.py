"""Offline report: source inputs and chromosome groups precede the assembly and delivery views."""
from __future__ import annotations

import re

try:
    from render_final_story import final_card
    from render_gap_story import gap_card
    from render_overview_summary import overview_summary_card
    from render_terminal_story import terminal_card
    from render_repair_story import repair_card, DIALOG
    from render_path_story import input_card, assignment_card, q0_card
    from render_refinement_report import (
        bi,
        callout,
        esc,
        workbench_page,
    )
except ModuleNotFoundError:
    from .render_final_story import final_card
    from .render_gap_story import gap_card
    from .render_overview_summary import overview_summary_card
    from .render_terminal_story import terminal_card
    from .render_repair_story import repair_card, DIALOG
    from .render_path_story import input_card, assignment_card, q0_card
    from .render_refinement_report import (
        bi,
        callout,
        esc,
        workbench_page,
    )


def _format_header_time(raw: str) -> str:
    if not raw:
        return ""
    text = raw.strip()
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$", text)
    if m:
        date_part, hm_part, tz_part = m.groups()
        if tz_part in ("Z", "+00:00", "-00:00", "+0000"):
            disp = f"{date_part} {hm_part} UTC"
        elif tz_part:
            disp = f"{date_part} {hm_part} {tz_part}"
        else:
            disp = f"{date_part} {hm_part}"
    else:
        disp = text
    return f'<time class="cgat-time" datetime="{esc(text)}" title="{esc(text)}">{esc(disp)}</time>'


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
    gen_at = meta.get("generated_at") or ""

    if meta['mode']=='manual_only':
        body=_run_notices(vm)
    else:
        lgz = vm["lgz_summary"]
        body = (
            _run_notices(vm)
            + overview_summary_card(vm)
            + input_card(lgz["inputs"])
            + assignment_card(
                lgz.get("assignment", {}),
                ref_tracks=lgz.get("reference_tracks"),
                assemblies=lgz.get("inputs", {}).get("assemblies"),
                funnel=lgz.get("funnel"),
            )
            + q0_card(lgz)
            + repair_card(lgz)
            + repair_card(lgz, structural=True)
            + terminal_card(lgz)
            + gap_card(vm)
            + final_card(vm)
            + DIALOG
        )

    brand_icon = (
        '<span class="cgat-brand-icon" aria-hidden="true">'
        '<svg width="22" height="22" viewBox="0 0 8 8" fill="none">'
        '<path fill="var(--logo-navy)" d="M4 0 5 1 4 2 3 1Z"/>'
        '<path fill="var(--logo-red)" d="M0 2h2l1 1 1-1 1 1 1-1h2L5 5 4 4 3 5Z"/>'
        '<path fill="var(--logo-navy)" d="M3 5 4 6 3 7 2 6Z"/>'
        '<path fill="var(--logo-navy)" d="M5 5 6 6 5 7 4 6Z"/>'
        '<path fill="var(--logo-navy)" d="M3 7 4 8H2Z"/>'
        '<path fill="var(--logo-navy)" d="M5 7 6 8H4Z"/>'
        '</svg></span>'
    )
    title_html = (
        '<span class="cgat-heading-prefix">'
        '<span class="t-zh">CGAT Server 报告：</span>'
        '<span class="t-en">CGAT Server Report: </span>'
        '</span>'
        f'<span class="cgat-heading-project" title="{esc(ws_name)}">{esc(ws_name)}</span>'
    )
    html = workbench_page(
        f"CGAT Server 报告：{ws_name}",
        f"CGAT Server Report: {ws_name}",
        body,
        title_html=title_html,
        brand_html=brand_icon,
        brand_sep=False,
        header_time_html=_format_header_time(gen_at),
        header_time_raw=True,
        sidebar_items=None,
        page_title_plain=f"CGAT Server 报告：{ws_name}",
    )
    batches=vm['manual_summary']['batches']
    if batches:
        from refine_report import _with_manual_section
        from render_manual_story import manual_card
        html=_with_manual_section(html,manual_card(batches,html))
    return html
