"""Offline report: source inputs and chromosome groups precede the assembly and delivery views."""
from __future__ import annotations

from collections import defaultdict

try:
    from render_terminal_story import terminal_card
    from render_repair_story import repair_card, DIALOG
    from render_path_story import input_card, assignment_card, q0_card
    from render_refinement_report import (
        badge_bi,
        bi,
        callout,
        copy_btn,
        disclosure,
        esc,
        fmt_bp,
        fmt_bp_short,
        fmt_bytes,
        fmt_int,
        link,
        status_badge,
        svg_stacked_bar,
        table,
        workbench_page,
    )
except ModuleNotFoundError:
    from .render_terminal_story import terminal_card
    from .render_repair_story import repair_card, DIALOG
    from .render_path_story import input_card, assignment_card, q0_card
    from .render_refinement_report import (
        badge_bi,
        bi,
        callout,
        copy_btn,
        disclosure,
        esc,
        fmt_bp,
        fmt_bp_short,
        fmt_bytes,
        fmt_int,
        link,
        status_badge,
        svg_stacked_bar,
        table,
        workbench_page,
    )


def _latest_lgz_version(seq_versions):
    for key in ("q4", "q3", "q2", "q1", "q0"):
        if seq_versions.get(key):
            return key, seq_versions[key]
    return None, {}


def _anchor(href, label_html, *, raw=True):
    if not href:
        return ""
    inner = label_html if raw else esc(label_html)
    return f'<a class="link-pill" href="{esc(href)}">{inner}</a>'


def _job_href(link_info):
    if not isinstance(link_info, dict) or not link_info.get("href"):
        return None
    href = link_info["href"]
    anchor = link_info.get("anchor")
    return f"{href}#{anchor}" if anchor else href


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


def _fmt_coord_short(pos):
    if pos is None:
        return "—"
    if pos >= 1_000_000:
        return f"{pos / 1_000_000:.2f}M"
    if pos >= 1_000:
        return f"{pos / 1_000:.1f}k"
    return f"{pos}bp"


def _gap_state_info(state):
    return {
        "closed": ("已闭合", "Closed", "is-closed", "ok"),
        "partial": ("部分闭合", "Partial", "is-partial", "info"),
        "unfilled": ("未填补", "Unfilled", "is-gap", "neutral"),
        "rejected": ("已拒绝", "Rejected", "is-rejected", "err"),
    }.get(state, (state or "未评估", state or "N/A", "is-gap", "neutral"))


def _overlay_refinement_segments(base_segments, length_bp, ref_gaps):
    """Overlay 0-based half-open refinement gaps onto LGZ base segments cleanly.

    - Overlapping LGZ gap segments inherit the refinement outcome & job link.
    - Refinement gaps inside source segments (e.g., <100 N intervals) split the source segment
      so every evaluated refinement gap is visible and directly clickable on the chromosome bar.
    """
    if not ref_gaps:
        return [dict(s) for s in base_segments]
    sorted_gaps = sorted(ref_gaps, key=lambda g: (g["start"], g["end"]))
    used = set()
    out = []

    for seg in base_segments:
        s0, s1 = seg["start"], seg["end"]
        overlapping = [
            (i, g)
            for i, g in enumerate(sorted_gaps)
            if i not in used and g["start"] < s1 and g["end"] > s0
        ]
        if not overlapping:
            out.append(dict(seg))
            continue
        if seg.get("kind") == "gap":
            idx, g = overlapping[0]
            used.add(idx)
            merged = dict(seg)
            merged["ref_gap"] = g
            out.append(merged)
            for idx2, g2 in overlapping[1:]:
                used.add(idx2)
                out.append(
                    dict(
                        start=g2["start"],
                        end=g2["end"],
                        kind="gap",
                        source=None,
                        patch=False,
                        ref_gap=g2,
                    )
                )
        else:
            cursor = s0
            for idx, g in overlapping:
                used.add(idx)
                gs = max(s0, g["start"])
                ge = min(s1, g["end"])
                if gs > cursor:
                    piece = dict(seg)
                    piece["start"] = cursor
                    piece["end"] = gs
                    out.append(piece)
                out.append(
                    dict(
                        start=gs,
                        end=max(gs + 1, ge),
                        kind="gap",
                        source=None,
                        patch=False,
                        ref_gap=g,
                    )
                )
                cursor = max(cursor, ge)
            if cursor < s1:
                tail = dict(seg)
                tail["start"] = cursor
                tail["end"] = s1
                out.append(tail)

    for i, g in enumerate(sorted_gaps):
        if i not in used:
            out.append(
                dict(
                    start=g["start"],
                    end=min(length_bp, g["end"]) if length_bp else g["end"],
                    kind="gap",
                    source=None,
                    patch=False,
                    ref_gap=g,
                )
            )
    out.sort(key=lambda s: (s["start"], s["end"]))
    return out


def _render_track_bar(
    segments,
    *,
    length_bp,
    max_len,
    chr_name,
    ds_color_idx,
    telomeres=None,
    centromeres=None,
    mini=False,
    tool_name=None,
    segment_count=None,
    compact=False,
):
    clen = max(1, length_bp or 1)
    rel_w = max(10.0, 100.0 * clen / max(1, max_len))
    pieces = []
    drawn_bp = 0
    for s in segments:
        slen = max(1, (s.get("end") or 0) - (s.get("start") or 0))
        drawn_bp += slen
        rg = s.get("ref_gap")
        if rg is not None:
            st = rg.get("state")
            zh_st, en_st, cls_st, _ = _gap_state_info(st)
            jhref = rg.get("href")
            jname = rg.get("job_name") or rg.get("gap_id") or ""
            g_idx = rg.get("chr_index")
            g_tag = f"#{g_idx} " if g_idx else ""
            if compact:
                tip = f"{chr_name} {g_tag}{rg['start']:,}-{rg['end']:,} {zh_st}"
            else:
                tip = (
                    f"{chr_name} · {g_tag}{jname} · {rg['start']:,}–{rg['end']:,} ({rg['end'] - rg['start']:,} bp)"
                    f" · {tool_name or 'refinement'}: {zh_st}"
                    + (" · 点击打开 job 报告" if jhref else "")
                )
            style = f"flex-grow:{slen}"
            title_attr = "" if compact else f' title="{esc(tip)}"'
            if jhref:
                pieces.append(
                    f'<a class="ideo-seg ideo-gap-link {cls_st}" style="{style}"'
                    f' href="{esc(jhref)}" target="_blank" rel="noopener"{title_attr}></a>'
                )
            else:
                pieces.append(f'<i class="ideo-seg {cls_st}" style="{style}"{title_attr}></i>')
            continue

        kind = s.get("kind", "source")
        src = s.get("source") or ""
        is_patch = bool(s.get("patch")) or kind == "patch"
        if kind == "gap":
            cls, style = "ideo-seg is-gap", f"flex-grow:{slen}"
        elif is_patch:
            cls, style = "ideo-seg is-patch", f"flex-grow:{slen}"
        else:
            cls = f"ideo-seg ds-{ds_color_idx.get(src, 0) % 6}"
            style = f"flex-grow:{slen}"
        if compact and kind == "source" and not is_patch:
            pieces.append(f'<i class="{cls}" style="{style}"></i>')
        else:
            tip = (
                f"{chr_name} · {'LGZ 补丁' if is_patch else kind}"
                + (f" · {src}" if src else "")
                + f" · {s.get('start', 0):,}–{s.get('end', 0):,} ({slen:,} bp)"
            )
            pieces.append(f'<i class="{cls}" style="{style}" title="{esc(tip)}"></i>')

    if clen > drawn_bp and segment_count and segment_count > len(segments):
        pieces.append(f'<i class="ideo-seg" style="flex-grow:{clen - drawn_bp};background:var(--border-default)"></i>')

    markers = []
    if telomeres:
        for term, side in (("5prime", "left"), ("3prime", "right")):
            st = telomeres.get(term)
            if st is not None:
                ok = st in ("already_present", "recovered")
                markers.append(
                    f'<span class="ideo-cap {side} {"complete" if ok else "missing"}"'
                    f' title="{esc(chr_name)} {esc(term)}: {esc(st)}"></span>'
                )
    if centromeres:
        for m in centromeres[:200]:
            s1 = max(1, m.get("q4_start") or 1)
            e1 = min(clen, m.get("q4_end") or s1)
            left = 100.0 * (s1 - 1) / clen
            width = max(0.5, 100.0 * max(1, e1 - s1 + 1) / clen)
            markers.append(
                f'<span class="ideo-cen" style="left:{left:.3f}%;width:{width:.3f}%"'
                f' title="{esc(chr_name)} cen: {s1:,}–{e1:,} (1-based inclusive)"></span>'
            )

    mini_cls = " is-mini" if mini else ""
    return (
        f'<div class="ideo-track-barbox">'
        f'<div class="ideo-track{mini_cls}" style="width:{rel_w:.2f}%">'
        f'{"".join(pieces)}{"".join(markers)}'
        f'</div></div>'
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


def _render_pseudomolecule_evolution(vm):
    lgz = vm["lgz_summary"]
    ref = vm["refinement_summary"]
    chrs = lgz.get("chromosomes") or []
    version_tracks = lgz.get("version_tracks") or {}
    seq_vers = lgz.get("sequence_versions") or {}
    final_q, _ = _latest_lgz_version(seq_vers)
    tools = ref.get("tools") or []
    gap_rows = (ref.get("gap_matrix") or {}).get("rows") or []

    if not chrs:
        return (
            '<section id="pseudomolecule-evolution" class="panel">'
            '<div id="lgz-baseline"></div><div id="refinement-comparison"></div>'
            f'<div class="panel-head"><h2>{bi("假分子演化与精修", "Pseudomolecule Evolution")}</h2></div>'
            f'<p class="muted">{bi("尚无可绘制的染色体假分子数据。", "No chromosome pseudomolecules available.")}</p>'
            '</section>'
        )

    # Match input source colors even when an assembly contributes no sequence.
    inputs = [row["name"] for row in lgz["inputs"]["assemblies"]]
    observed = {ds for c in chrs for ds in (c.get("source_bp") or {}) if ds}
    ds_names = list(dict.fromkeys([*inputs, *sorted(observed.difference(inputs))]))
    ds_color_idx = {name: i for i, name in enumerate(ds_names)}
    max_len = max((c.get("length_bp") or 0 for c in chrs), default=1) or 1

    # Index refinement gaps per (tool, chromosome) with sequential per-chr numbering & direct job href
    eval_tools = [t for t in tools if isinstance(t.get("counts"), dict) and t["status"] != "invalidated"]
    tool_chr_gaps = {t["tool"]: defaultdict(list) for t in eval_tools}
    for row in gap_rows:
        cname = row["chromosome"]
        gid = row["gap_id"]
        for t in eval_tools:
            tname = t["tool"]
            st = (row.get("tools") or {}).get(tname)
            if not st:
                continue
            linfo = (t.get("gap_links") or {}).get(gid) or {}
            lst = tool_chr_gaps[tname][cname]
            lst.append(
                dict(
                    gap_id=gid,
                    start=row["start"],
                    end=row["end"],
                    state=st,
                    href=_job_href(linfo),
                    job_name=linfo.get("job_name"),
                    native_gap_id=linfo.get("native_gap_id"),
                    chr_index=len(lst) + 1,
                )
            )

    # Identify ordered LGZ evolutionary versions available in version_tracks
    ordered_qv = [qv for qv in ("q0", "q1", "q2", "q3", "q4") if qv in version_tracks]

    # Build stage tabs & deduplicated stage panels
    # Default view: first evaluated refinement tool overlay (or LGZ baseline if none)
    stage_tabs = []  # (btn_key, target_panel_key, label_html, sub_html)
    stage_panels = {}  # panel_key -> (panel_kind, payload)

    if eval_tools:
        for t in eval_tools:
            tname = t["tool"]
            pkey = f"tool:{tname}"
            cnt = t["counts"]
            cl = cnt.get("closed", 0)
            tot_t = sum(cnt.values())
            lbl = bi(f"精修终稿 ({tname})", f"Refined ({tname})") if len(eval_tools) == 1 else esc(tname)
            sub = bi(f"闭合 {cl}/{tot_t}", f"{cl}/{tot_t} closed")
            stage_tabs.append((pkey, pkey, lbl, sub))
            stage_panels[pkey] = ("tool", t)

    # LGZ step tabs (q0 -> q1 -> q2 -> q3), deduplicating identical segment panels
    prev_sig = None
    prev_panel_key = None
    prev_gaps = None
    for qv in ordered_qv:
        vt = version_tracks[qv]
        v_chrs = vt.get("chromosomes") or {}
        sig = tuple(
            (
                c["chromosome"],
                (v_chrs.get(c["chromosome"]) or {}).get("gap_count"),
                (v_chrs.get(c["chromosome"]) or {}).get("patch_count"),
                (v_chrs.get(c["chromosome"]) or {}).get("segment_count"),
            )
            for c in chrs
        )
        g_tot = (seq_vers.get(qv) or {}).get("gap_count")
        if g_tot is None:
            g_tot = sum((v_chrs.get(c["chromosome"]) or {}).get("gap_count", 0) for c in chrs)
        if qv == "q0":
            sub = f"{g_tot} Gap"
        elif prev_gaps is not None and g_tot != prev_gaps:
            sub = f"{g_tot - prev_gaps:+d} Gap"
        elif qv == final_q:
            tel_ok = sum(1 for c in chrs for st in (c.get("telomeres") or {}).values() if st in ("already_present", "recovered"))
            tel_all = sum(1 for c in chrs for _ in (c.get("telomeres") or {}).values())
            sub = bi(f"端粒 {tel_ok}/{len(chrs) * 2}", f"Tel {tel_ok}/{len(chrs) * 2}") if tel_all else bi("LGZ 终稿", "LGZ final")
        else:
            sub = bi("无变化", "same")
        if sig == prev_sig and prev_panel_key and qv != final_q:
            target_key = prev_panel_key
        else:
            target_key = f"lgz:{qv}"
            stage_panels[target_key] = ("lgz_version", qv)
            prev_sig = sig
            prev_panel_key = target_key
        prev_gaps = g_tot
        stage_tabs.append((f"lgz:{qv}", target_key, esc(qv), sub))

    if not ordered_qv:
        # Fallback when workspace lacks step q_segments (e.g., synthetic fixtures)
        pkey = "lgz:final"
        lgz_rem_tot = sum(c.get("remaining_gap_count") or 0 for c in chrs)
        stage_tabs.append((pkey, pkey, bi("LGZ 基线", "LGZ Baseline"), f"{lgz_rem_tot} Gap"))
        stage_panels[pkey] = ("lgz_final", None)

    active_btn = stage_tabs[0][0]
    active_panel = stage_tabs[0][1]
    compact_evo = len(gap_rows) > 60 or len(chrs) > 12

    def _build_chr_drawer(c):
        """Per-chromosome vertical evolution tracks (q0 -> changed LGZ step -> LGZ final -> tool(s)) + clickable gap chips."""
        cname = c["chromosome"]
        clen = max(1, c.get("length_bp") or 1)
        evo_rows = []
        last_sig = None
        q0_c_gaps = None

        for qv in ordered_qv:
            vc = (version_tracks[qv].get("chromosomes") or {}).get(cname)
            if not vc:
                continue
            v_segs = vc.get("segments") or []
            v_gaps = vc.get("gap_count", 0)
            v_patches = vc.get("patch_count", 0)
            v_len = vc.get("length_bp") or clen
            sig = (v_gaps, v_patches, vc.get("segment_count"))
            is_first = qv == ordered_qv[0]
            is_last = qv == ordered_qv[-1]
            if is_first:
                q0_c_gaps = v_gaps
            # Show q0, any step where segments/gaps/patches changed, and final q-version if telomeres exist
            if not is_first and sig == last_sig and not (is_last and c.get("telomeres")):
                continue
            last_sig = sig
            note_bits = []
            if v_patches:
                note_bits.append(f'<b>+{v_patches} {bi("补丁", "patch")}</b>')
            note_bits.append(f'{v_gaps} Gap')
            if not is_first and q0_c_gaps is not None and v_gaps < q0_c_gaps:
                note_bits.append(f'<b>({v_gaps - q0_c_gaps:+d})</b>')
            if is_last and c.get("telomeres"):
                tok = sum(1 for st in c["telomeres"].values() if st in ("already_present", "recovered"))
                note_bits.append(f'{bi("端粒", "Tel")} {tok}/2')
            bar = _render_track_bar(
                v_segs,
                length_bp=v_len,
                max_len=clen,
                chr_name=cname,
                ds_color_idx=ds_color_idx,
                telomeres=c.get("telomeres") if is_last else None,
                centromeres=c.get("centromere_markers") if is_last else None,
                mini=True,
                segment_count=vc.get("segment_count"),
                compact=compact_evo,
            )
            lbl_html = f'{esc(qv)} ({bi("终稿", "Final")})' if is_last and not is_first else esc(qv)
            evo_rows.append(
                f'<div class="chr-evo-row"><span class="chr-evo-lbl">{lbl_html}</span>{bar}'
                f'<span class="chr-evo-note">{" · ".join(note_bits)}</span></div>'
            )

        if not evo_rows and not compact_evo:
            bar = _render_track_bar(
                c.get("segments") or [],
                length_bp=clen,
                max_len=clen,
                chr_name=cname,
                ds_color_idx=ds_color_idx,
                telomeres=c.get("telomeres"),
                centromeres=c.get("centromere_markers"),
                mini=True,
                segment_count=c.get("segment_count"),
                compact=compact_evo,
            )
            lg_n = c.get("remaining_gap_count")
            evo_rows.append(
                f'<div class="chr-evo-row"><span class="chr-evo-lbl">LGZ</span>{bar}'
                f'<span class="chr-evo-note">{lg_n if lg_n is not None else "—"} Gap</span></div>'
            )

        # Refinement tool track(s) + clickable job chips (bounded in compact mode for large genomes)
        drawer_tools = eval_tools[:1] if compact_evo else eval_tools
        chip_groups = []
        for t in drawer_tools:
            tname = t["tool"]
            cgaps = tool_chr_gaps[tname].get(cname) or []
            if cgaps:
                if not compact_evo:
                    ov_segs = _overlay_refinement_segments(c.get("segments") or [], clen, cgaps)
                    cl_n = sum(1 for g in cgaps if g["state"] == "closed")
                    pa_n = sum(1 for g in cgaps if g["state"] == "partial")
                    rem_n = len(cgaps) - cl_n - pa_n
                    bar = _render_track_bar(
                        ov_segs,
                        length_bp=clen,
                        max_len=clen,
                        chr_name=cname,
                        ds_color_idx=ds_color_idx,
                        telomeres=c.get("telomeres"),
                        centromeres=c.get("centromere_markers"),
                        mini=True,
                        tool_name=tname,
                        segment_count=c.get("segment_count"),
                        compact=compact_evo,
                    )
                    note = (
                        (f'<b>{bi("闭合", "Closed")} {cl_n}/{len(cgaps)}</b>' if cl_n else f'{bi("闭合", "Closed")} 0/{len(cgaps)}')
                        + (f' · {bi("部分", "Partial")} {pa_n}' if pa_n else "")
                        + f' · {bi("剩余", "Rem")} {rem_n}'
                    )
                    evo_rows.append(
                        f'<div class="chr-evo-row"><span class="chr-evo-lbl">{esc(tname)}</span>{bar}'
                        f'<span class="chr-evo-note">{note}</span></div>'
                    )
                max_chips = 6 if compact_evo else len(cgaps)
                chips = []
                for g in cgaps[:max_chips]:
                    zh_st, en_st, cls_st, dot_cls = _gap_state_info(g["state"])
                    chip_cls = {
                        "closed": "is-closed",
                        "partial": "is-partial",
                        "rejected": "is-rejected",
                    }.get(g["state"], "is-unfilled")
                    pos_txt = _fmt_coord_short(g["start"])
                    g_lbl = f'#{g["chr_index"]}'
                    inner = (
                        f'<i class="dot {dot_cls}"></i><b>{g_lbl}</b>'
                        f'<span>{esc(pos_txt)}</span><span>{bi(zh_st, en_st)}</span>'
                    )
                    if g.get("href"):
                        tip_attr = "" if compact_evo else f' title="{esc(cname)} {g_lbl} ({g["start"]:,}–{g["end"]:,}) · {esc(tname)}: {zh_st}"'
                        chips.append(
                            f'<a class="gap-job-chip {chip_cls}" href="{esc(g["href"])}"'
                            f' target="_blank" rel="noopener"{tip_attr}>{inner}<span class="chip-arrow">↗</span></a>'
                        )
                    else:
                        chips.append(f'<span class="gap-job-chip {chip_cls}">{inner}</span>')
                if len(cgaps) > max_chips:
                    chips.append(f'<span class="muted">+{len(cgaps) - max_chips}</span>')
                chip_groups.append(
                    f'<div class="gap-chip-group"><span class="gap-chip-lbl">{esc(tname)} {bi("单 Gap 报告：", "Gap jobs:")}</span>{"".join(chips)}</div>'
                )

        src_parts = [f"{esc(k)}: {esc(fmt_bp_short(v))}" for k, v in sorted((c.get("source_bp") or {}).items(), key=lambda kv: -kv[1])]
        meta_line = (
            f'<div class="muted" style="margin-top:.35rem">{esc(fmt_bp(clen))} · {c.get("segment_count", 0):,} segs'
            + (f' · {" / ".join(src_parts)}' if src_parts else "")
            + '</div>'
        )
        return (
            '<div class="ideo-detail">'
            f'<div class="chr-evo-tracks">{"".join(evo_rows)}</div>'
            + "".join(chip_groups)
            + meta_line
            + '</div>'
        )

    # Pre-build chromosome drawers once (shared for active view; lightweight inline summary for other panels)
    chr_drawers = {c["chromosome"]: _build_chr_drawer(c) for c in chrs}

    # Build stage panels HTML
    panel_blocks = []
    for pkey, (pkind, payload) in stage_panels.items():
        rows_html = []
        has_patch = False
        has_gap = False
        has_closed = False
        has_partial = False
        has_rejected = False
        has_tel_ok = False
        has_tel_miss = False
        has_cen = False

        for c in chrs:
            cname = c["chromosome"]
            clen = max(1, c.get("length_bp") or 1)
            show_tel = True
            show_cen = True
            tname_for_bar = None

            if pkind == "tool":
                tname_for_bar = payload["tool"]
                cgaps = tool_chr_gaps[tname_for_bar].get(cname) or []
                segs = _overlay_refinement_segments(c.get("segments") or [], clen, cgaps)
                cl_n = sum(1 for g in cgaps if g["state"] == "closed")
                pa_n = sum(1 for g in cgaps if g["state"] == "partial")
                rem_n = len(cgaps) - cl_n - pa_n
                if not cgaps:
                    meta_txt = "0 gap"
                    meta_cls = "ideo-meta"
                elif cl_n > 0:
                    meta_txt = f"{len(cgaps)}→{rem_n} gap"
                    meta_cls = "ideo-meta has-gain"
                else:
                    meta_txt = f"{rem_n} gap"
                    meta_cls = "ideo-meta"
                seg_cnt = c.get("segment_count")
                bar_len = clen
            elif pkind == "lgz_version":
                qv = payload
                vc = (version_tracks[qv].get("chromosomes") or {}).get(cname)
                segs = (vc or {}).get("segments") or (c.get("segments") or [])
                bar_len = (vc or {}).get("length_bp") or clen
                seg_cnt = (vc or {}).get("segment_count") or c.get("segment_count")
                g_n = (vc or {}).get("gap_count")
                meta_txt = f"{g_n} gap" if isinstance(g_n, int) else "—"
                meta_cls = "ideo-meta"
                show_tel = qv == ordered_qv[-1]
                show_cen = qv == ordered_qv[-1]
            else:
                segs = c.get("segments") or []
                bar_len = clen
                seg_cnt = c.get("segment_count")
                g_n = c.get("remaining_gap_count")
                meta_txt = f"{g_n} gap" if isinstance(g_n, int) else "—"
                meta_cls = "ideo-meta"

            for s in segs:
                rg = s.get("ref_gap")
                if rg is not None:
                    st = rg.get("state")
                    if st == "closed":
                        has_closed = True
                    elif st == "partial":
                        has_partial = True
                    elif st == "rejected":
                        has_rejected = True
                    else:
                        has_gap = True
                elif s.get("kind") == "gap":
                    has_gap = True
                elif s.get("patch") or s.get("kind") == "patch":
                    has_patch = True
            if show_tel:
                for st in (c.get("telomeres") or {}).values():
                    if st in ("already_present", "recovered"):
                        has_tel_ok = True
                    else:
                        has_tel_miss = True
            if show_cen and c.get("centromere_marker_count"):
                has_cen = True

            bar_html = _render_track_bar(
                segs,
                length_bp=bar_len,
                max_len=max_len,
                chr_name=cname,
                ds_color_idx=ds_color_idx,
                telomeres=c.get("telomeres") if show_tel else None,
                centromeres=c.get("centromere_markers") if show_cen else None,
                tool_name=tname_for_bar,
                segment_count=seg_cnt,
                compact=compact_evo or pkey != active_panel,
            )
            drawer = chr_drawers[cname] if pkey == active_panel else (
                f'<div class="ideo-detail">{esc(fmt_bp(bar_len))} · {seg_cnt or len(segs):,} segs</div>'
            )
            rows_html.append(
                f'<details class="ideo-row"><summary>'
                f'<span class="ideo-name" title="{esc(cname)}">{esc(cname)}</span>'
                f'{bar_html}'
                f'<span class="{meta_cls}">{esc(meta_txt)}</span>'
                f'<span class="ideo-meta">{esc(fmt_bp_short(bar_len))}</span>'
                f'</summary>{drawer}</details>'
            )

        legend_items = [
            f'<span class="legend-item"><i class="swatch" style="background:var(--ds-{idx % 6})"></i>{esc(name)}</span>'
            for name, idx in ds_color_idx.items()
        ]
        if has_patch:
            legend_items.append('<span class="legend-item"><i class="swatch" style="background:var(--gen-patch)"></i>' + bi("LGZ 补丁", "LGZ patch") + '</span>')
        if has_closed:
            legend_items.append('<span class="legend-item"><i class="swatch is-closed"></i>' + bi("精修已闭合（可点击）", "Closed (clickable)") + '</span>')
        if has_partial:
            legend_items.append('<span class="legend-item"><i class="swatch is-partial"></i>' + bi("部分闭合（可点击）", "Partial (clickable)") + '</span>')
        if has_gap:
            legend_items.append('<span class="legend-item"><i class="swatch is-gap"></i>' + (bi("未闭合 Gap（可点击）", "Unfilled gap (clickable)") if pkind == "tool" else "Gap") + '</span>')
        if has_rejected:
            legend_items.append('<span class="legend-item"><i class="swatch is-rejected"></i>' + bi("已拒绝（可点击）", "Rejected (clickable)") + '</span>')
        if has_tel_ok:
            legend_items.append('<span class="legend-item"><i class="swatch is-tel"></i>' + bi("端粒完整", "Telomere") + '</span>')
        if has_tel_miss:
            legend_items.append('<span class="legend-item"><i class="swatch is-tel-miss"></i>' + bi("端粒缺失", "Missing tel") + '</span>')
        if has_cen:
            legend_items.append('<span class="legend-item"><i class="swatch is-cen"></i>' + bi("着丝粒候选", "Centromere") + '</span>')

        hidden_cls = "" if pkey == active_panel else " is-hidden"
        panel_blocks.append(
            f'<div class="stage-panel{hidden_cls}" data-stage-panel="{esc(pkey)}">'
            f'<div class="legend-row">{"".join(legend_items)}</div>'
            f'<div class="ideo-list">{"".join(rows_html)}</div>'
            '</div>'
        )

    tabs_html = ""
    if len(stage_tabs) > 1:
        btns = []
        for bkey, tkey, lbl, sub in stage_tabs:
            act = " is-active" if bkey == active_btn else ""
            sub_s = f" <small>{sub}</small>" if sub else ""
            btns.append(
                f'<button type="button" class="stage-tab{act}" data-stage-btn="{esc(bkey)}"'
                f' data-stage-target="{esc(tkey)}">{lbl}{sub_s}</button>'
            )
        tabs_html = f'<div class="stage-tabs" role="tablist" aria-label="Pseudomolecule stages">{"".join(btns)}</div>'

    hint_txt = (
        bi("点击假分子上的精修 Gap 色块或展开染色体下方标签，可直接在新标签页打开该 Gap 的 job 报告；点击染色体行可查看 q0 → 终稿 纵向演化。",
           "Click any refinement gap on a chromosome bar (or chips inside a row) to open its job HTML report; click a chromosome to inspect its q0 → final evolution.")
        if eval_tools
        else bi("点击染色体行可展开 q0 → 终稿 分段演化与来源构成（路径段 0-based 半开区间；着丝粒 1-based 闭区间）。",
                "Click a chromosome row to inspect its q0 → final evolution and source segments.")
    )

    return (
        '<section id="pseudomolecule-evolution" class="panel" data-evo-root="1">'
        '<div id="lgz-baseline"></div><div id="refinement-comparison"></div>'
        f'<div class="panel-head"><h2>{bi("假分子演化与精修", "Pseudomolecule Evolution")}</h2></div>'
        + tabs_html
        + "".join(panel_blocks)
        + f'<p class="muted" style="margin-top:.55rem">{hint_txt}</p>'
        + '</section>'
    )


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


def _matrix_cell_html(state):
    if state == "closed":
        return f'<span class="matrix-cell mc-closed">{bi("闭合", "Closed")}</span>'
    if state == "partial":
        return f'<span class="matrix-cell mc-partial">{bi("部分", "Partial")}</span>'
    if state == "unfilled":
        return f'<span class="matrix-cell mc-unfilled">{bi("未填补", "Unfilled")}</span>'
    if state == "rejected":
        return f'<span class="matrix-cell mc-rejected">{bi("拒绝", "Rejected")}</span>'
    return f'<span class="matrix-cell mc-na">{esc(state)}</span>'


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

    # Fold 3: Per-chromosome & per-gap filterable comparison matrix
    tools = ref.get("tools") or []
    tool_names = [t["tool"] for t in tools]
    by_chr = ref.get("by_chromosome") or []
    gap_matrix = ref.get("gap_matrix") or {}
    total_gaps = gap_matrix.get("total_gap_count")
    m_rows = gap_matrix.get("rows") or []
    matrix_fold = ""
    if (by_chr or m_rows) and tool_names:
        parts = []
        if by_chr:
            hm_rows = []
            for row in by_chr:
                cells = [f'<code>{esc(row["chromosome"])}</code>', f'<span class="num">{row["original_gap_count"]:,}</span>']
                for tn in tool_names:
                    tc = (row.get("tools") or {}).get(tn)
                    if not tc or row["original_gap_count"] == 0:
                        cells.append('<span class="muted">0</span>')
                        continue
                    cl, pa, un, rj, na = tc["closed"], tc["partial"], tc["unfilled"], tc["rejected"], tc["not_evaluated"]
                    orig = tc["original_gap_count"]
                    tip = f"{row['chromosome']} · {tn}: closed={cl}, partial={pa}, unfilled={un}, rejected={rj}, not_evaluated={na}"
                    mini = svg_stacked_bar(
                        [(cl, "var(--gen-closed)", ""), (pa, "var(--gen-partial)", ""), (un, "var(--gen-unfilled)", ""), (rj, "var(--gen-rejected)", ""), (na, "var(--gen-na)", "")],
                        width=92,
                        height=9,
                    )
                    lbl = bi("未评估", "N/A") if na == orig else f'<span class="num">{cl}/{orig}</span>'
                    cells.append(f'<div title="{esc(tip)}" style="display:flex;align-items:center;gap:.45rem">{mini}{lbl}</div>')
                hm_rows.append(cells)
            parts.append(
                f'<h3>{bi(f"按染色体聚合（全量 {len(by_chr)} 条染色体）", f"By-Chromosome Summary (all {len(by_chr)} chrs)")}</h3>'
                + table([bi("染色体", "Chr"), bi("原始缺口", "Orig"), *[esc(tn) for tn in tool_names]], hm_rows)
            )
        if m_rows:
            chrs_in_matrix = list(dict.fromkeys(r["chromosome"] for r in m_rows))
            chr_opts = '<option value="">全部 / All chrs</option>' + "".join(
                f'<option value="{esc(c)}">{esc(c)}</option>' for c in chrs_in_matrix
            )
            tool_link_maps = {t["tool"]: (t.get("gap_links") or {}) for t in tools}
            m_table_rows = []
            for r in m_rows:
                states = [r["tools"].get(tn, "tool_unknown") for tn in tool_names]
                tr_attr = f'data-chr="{esc(r["chromosome"])}" data-states="{esc(",".join(states))}"'
                glen = r["end"] - r["start"]
                t_cells = []
                for tn, st in zip(tool_names, states):
                    cell = _matrix_cell_html(st)
                    jh = _job_href(tool_link_maps.get(tn, {}).get(r["gap_id"])) if len(m_rows) <= 60 else None
                    if jh:
                        t_cells.append(f'<a href="{esc(jh)}" target="_blank" rel="noopener">{cell}</a>')
                    else:
                        t_cells.append(cell)
                m_table_rows.append(
                    (
                        tr_attr,
                        [
                            f'<code>{esc(r["gap_id"])}</code>',
                            f'<code>{esc(r["chromosome"])}</code>',
                            f'<span class="num">{r["start"]:,}–{r["end"]:,}</span> <small class="muted">({glen:,} bp)</small>',
                            *t_cells,
                        ],
                    )
                )
            prev_cnt = gap_matrix["preview_count"]
            trunc = (
                f'<p class="muted">{bi(f"仅预览前 {prev_cnt:,} / 共 {total_gaps:,} 行，完整数据见 gap_comparison.tsv。", f"Previewing {prev_cnt:,} of {total_gaps:,}; see gap_comparison.tsv.")}</p>'
                if gap_matrix.get("truncated") else ""
            )
            filter_bar = (
                '<div class="filter-bar">'
                f'<select data-matrix-chr="1" aria-label="Filter by chromosome">{chr_opts}</select>'
                '<div class="filter-chips">'
                '<button type="button" class="ctrl-btn is-active" data-matrix-chip="all">' + bi("全部", "All") + '</button>'
                '<button type="button" class="ctrl-btn" data-matrix-chip="closed">' + bi("含闭合", "Closed") + '</button>'
                '<button type="button" class="ctrl-btn" data-matrix-chip="rejected">' + bi("含拒绝", "Rejected") + '</button>'
                '<button type="button" class="ctrl-btn" data-matrix-chip="unfilled">' + bi("全未填补", "Unfilled") + '</button>'
                '</div>'
                '<input type="search" data-matrix-search="1" placeholder="搜索 Gap ID / 坐标..." aria-label="Search gap matrix">'
                f'<span class="muted num" data-matrix-count="1">{len(m_rows)} / {len(m_rows)}</span>'
                '</div>'
            )
            dl_links = "".join([
                _anchor(ref.get("comparison_href"), "comparison.json", raw=False),
                _anchor(gap_matrix.get("full_tsv_href"), "gap_comparison.tsv", raw=False),
            ])
            parts.append(
                f'<h3>{bi(f"逐 Gap × 工具矩阵（{len(m_rows):,}/{fmt_int(total_gaps)} · 点击状态直达 job 报告）", f"Per-Gap Matrix ({len(m_rows):,}/{fmt_int(total_gaps)} · click cell for job)")}</h3>'
                + '<div data-matrix-root="1" data-status-filter="all">' + trunc + filter_bar
                + table(["Gap ID", bi("染色体", "Chr"), bi("LGZ 坐标", "LGZ Coord"), *[esc(tn) for tn in tool_names]], m_table_rows)
                + (f'<div class="link-row">{dl_links}</div>' if dl_links else "")
                + '</div>'
            )
        matrix_fold = disclosure(
            bi(f"精修完整统计与逐 Gap 对照表（{fmt_int(total_gaps)} Gap）", f"Full Per-Chr & Per-Gap Comparison ({fmt_int(total_gaps)} gaps)"),
            "".join(parts),
        )

    # Fold 4: Advanced diagnostics, checksums/logs & compatibility sub-reports
    compat_links = []
    if lgz.get("href"):
        compat_links.append(_anchor(lgz["href"], bi("LGZ 完整过程报告", "LGZ Full Process Report")))
    for t in tools:
        tname = t["tool"]
        if t.get("report_href"):
            lbl = bi(f"{tname} 工具汇总与日志", f"{tname} tool summary") if t.get("publication_verified") else bi(f"{tname} 工作区诊断", f"{tname} Attempt diagnostics (workspace)")
            compat_links.append(_anchor(t["report_href"], lbl))
        if t.get("native_global_href"):
            compat_links.append(_anchor(t["native_global_href"], bi(f"{tname} 原生全局可视化", f"{tname} native global view")))

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
        + matrix_fold
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
        ("pseudomolecule-evolution", "", "假分子演化", "Evolution"),
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
        + _render_pseudomolecule_evolution(vm)
        + _render_result_files_and_diagnostics(vm)
        + (DIALOG if any(vm["lgz_summary"].get(k) for k in ("step1_scene", "step2_scene", "terminal_scene")) else "")
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
