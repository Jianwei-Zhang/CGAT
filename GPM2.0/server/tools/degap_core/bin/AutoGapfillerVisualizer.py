#!/usr/bin/env python3
"""
Visualizer - Step 5

生成 gap filling 结果的交互式 HTML 可视化报告。

功能：
1. 总览统计信息（总 gaps、填充率、BP 变化等）
2. 染色体视图（显示所有 gaps 的位置和填充状态）
3. Gap 详细信息（点击查看每个 gap 的详细报告）
4. 统计图表（填充类型分布、长度分布等）
5. 国际化支持（中英文切换）

输入：
- Gap filling 统计结果（gap_filling_results.json）
- Genome integration 结果（integration_config.json）
- Reads 统计信息（preprocessing_config.json）

输出：
- gap_filling_report.html：交互式可视化报告
"""

import json
import sys
from pathlib import Path
from datetime import datetime

try:
    from ReportStyle import degap_logo_html, esc, report_css
except ImportError:
    from .ReportStyle import degap_logo_html, esc, report_css


class GapFillingVisualizer:
    """生成 gap filling 结果的可视化报告"""

    def __init__(self, output_dir, pipeline_summary=None):
        """
        初始化 Visualizer

        Args:
            output_dir: 主输出目录
            pipeline_summary: 可选的流程运行摘要字典（用于在 Step 5 时直接读取耗时与参数）
        """
        self.main_output_dir = Path(output_dir)
        self.pipeline_summary = pipeline_summary if isinstance(pipeline_summary, dict) else None

        # 输出目录
        self.output_dir = self.main_output_dir / "05.visualization"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 读取配置文件
        self._load_configurations()
    
    def _load_configurations(self):
        """读取所有需要的配置文件"""
        # Gap filling 结果
        gap_filling_results_file = self.main_output_dir / "03.gap_filling" / "gap_filling_results.json"
        if not gap_filling_results_file.exists():
            raise FileNotFoundError(
                f"Gap filling results not found: {gap_filling_results_file}\n"
                f"Please run AutoGapfillerPart3.py first!"
            )

        with open(gap_filling_results_file, 'r') as f:
            self.gap_filling_results = json.load(f)

        # Genome integration 结果（可选）
        integration_config_file = self.main_output_dir / "04.genome_integration" / "integration_config.json"
        if integration_config_file.exists():
            with open(integration_config_file, 'r') as f:
                self.integration_config = json.load(f)
        else:
            self.integration_config = None
            print("  Note: Genome integration results not found, some statistics may be unavailable")

        # Reads 统计信息（可选）
        preprocessing_config_file = self.main_output_dir / "01.reads_preprocessor" / "preprocessing_config.json"
        if preprocessing_config_file.exists():
            with open(preprocessing_config_file, 'r') as f:
                self.preprocessing_config = json.load(f)
        else:
            self.preprocessing_config = None
            print("  Note: Reads preprocessing config not found, some information may be unavailable")

        # 流程运行统计摘要（可选：优先用构造函数传入的，其次读盘上 autogapfiller_summary.json）
        if self.pipeline_summary is None:
            summary_file = self.main_output_dir / "autogapfiller_summary.json"
            if summary_file.exists():
                try:
                    with open(summary_file, 'r') as f:
                        loaded = json.load(f)
                    if isinstance(loaded, dict):
                        self.pipeline_summary = loaded
                except Exception:
                    self.pipeline_summary = None
    
    def generate_report(self):
        """
        生成可视化报告

        Returns:
            dict: 包含报告路径的字典
        """
        print(f"\n{'='*60}")
        print(f"Gap Filling Visualization")
        print(f"{'='*60}\n")

        print("[1/4] Preparing data...")
        self._prepare_data()

        print("\n[2/4] Copying sub-task reports...")
        self._copy_subtask_reports()

        print("\n[3/4] Generating HTML report...")
        html_file = self._generate_html()

        print("\n[4/4] Saving report...")
        self._save_report(html_file)

        print(f"\n{'='*60}")
        print("Visualization completed successfully!")
        print(f"{'='*60}\n")

        return {
            'output_dir': str(self.output_dir),
            'html_report': str(self.output_dir / 'Global.report.html')
        }
    
    def _prepare_data(self):
        """准备可视化数据"""
        print("  Analyzing gap filling results...")

        # 统计信息
        summary = self.gap_filling_results.get('summary', {})
        print(f"    Total gaps: {summary.get('total_gaps', 0)}")
        print(f"    Filled gaps: {summary.get('filled_gaps', 0)}")
        print(f"    Fill rate: {summary.get('fill_rate', '0%')}")

        # 按染色体组织 gaps
        gaps_by_chrom = {}
        for gap in self.gap_filling_results.get('gaps', []):
            chrom = gap['chromosome']
            if chrom not in gaps_by_chrom:
                gaps_by_chrom[chrom] = {
                    'gaps': [],
                    'total': 0,
                    'filled': 0,
                    'unfilled': 0,
                    'length': 0  # 真实染色体长度
                }
            gaps_by_chrom[chrom]['gaps'].append(gap)
            gaps_by_chrom[chrom]['total'] += 1
            if gap['filled']:
                gaps_by_chrom[chrom]['filled'] += 1
            else:
                gaps_by_chrom[chrom]['unfilled'] += 1

        # 从 integration_config 读取真实的染色体长度
        if self.integration_config:
            chrom_stats = self.integration_config.get('stats', {}).get('chromosomes', {})
            for chrom, stats in chrom_stats.items():
                if chrom in gaps_by_chrom:
                    # 使用原始长度（填充前的长度）
                    gaps_by_chrom[chrom]['length'] = stats.get('original_length', 0)

        # 如果没有 integration_config，使用 gap_end 的最大值作为估算
        for chrom, data in gaps_by_chrom.items():
            if data['length'] == 0:
                max_pos = 0
                for gap in data['gaps']:
                    gap_end = gap.get('gap_end', 0)
                    if gap_end > max_pos:
                        max_pos = gap_end
                data['length'] = max_pos

        print(f"    Chromosomes: {len(gaps_by_chrom)}")

        self.gaps_by_chrom = gaps_by_chrom

        # 计算总 BP 变化
        self.total_bp_added = 0
        if self.integration_config:
            stats = self.integration_config.get('stats', {})
            self.total_bp_added = stats.get('total_bp_added', 0)

    def _copy_subtask_reports(self):
        """复制子任务的可视化报告到总报告目录"""
        import shutil

        gap_filling_dir = self.main_output_dir / "03.gap_filling"
        copied_count = 0

        for gap in self.gap_filling_results.get('gaps', []):
            chrom = gap.get('chromosome')
            gap_id = gap.get('gap_id')
            filled = gap.get('filled', False)
            fill_direction = gap.get('fill_direction', 'none')

            # New jobs have one shared report, including unclosed results.
            if gap.get('report_direction') == 'bidirectional' or fill_direction == 'bidirectional':
                flag_to_copy = 'bidirectional'
            elif filled and fill_direction in ['left', 'right']:
                # 成功填充：复制成功的方向
                flag_to_copy = fill_direction
            else:
                # 失败：固定复制 left
                flag_to_copy = 'left'

            # 源文件路径
            source_report = gap_filling_dir / f"{chrom}.{gap_id}.{flag_to_copy}" / "visualization_output" / "gapfiller_report.html"

            if flag_to_copy == 'bidirectional':
                source_report = gap_filling_dir / f"{chrom}.{gap_id}.bidirectional" / "family-report.html"

            # 目标文件路径
            target_report = self.output_dir / f"{chrom}.{gap_id}.{flag_to_copy}.html"

            # 复制文件
            if source_report.exists():
                try:
                    if flag_to_copy == 'bidirectional':
                        # Keep source artifacts in place, but rebase report links.
                        import re
                        import os
                        from html import escape, unescape
                        from urllib.parse import quote
                        def rebase(match):
                            source = source_report.parent / unescape(match.group(1))
                            relative = os.path.relpath(source, target_report.parent)
                            return 'href="' + escape(quote(relative, safe='/.'), quote=True) + '"'
                        target_report.write_text(re.sub(r'href="([^"]+)"', rebase, source_report.read_text()))
                    else:
                        shutil.copy2(source_report, target_report)
                    copied_count += 1
                    print(f"  Copied: {chrom}.{gap_id}.{flag_to_copy}.html")
                except Exception as e:
                    print(f"  Warning: Failed to copy {source_report}: {e}")
            else:
                print(f"  Warning: Source report not found: {source_report}")

        print(f"  Total sub-task reports copied: {copied_count}")

    def _generate_html(self):
        """生成 HTML 报告"""
        print("  Creating HTML structure...")

        # 生成完整的 HTML 报告
        html_content = self._create_full_html()

        return html_content

    def _infer_project_name(self):
        """Infer a clean human-readable project name for the report topbar."""
        import re
        explicit = self.gap_filling_results.get('project_name') if isinstance(self.gap_filling_results, dict) else None
        if explicit:
            return str(explicit).strip()

        def _from_path(raw):
            if not raw:
                return ""
            parts = Path(str(raw)).parts
            for marker in ("04_refinement", "03_lgz"):
                if marker in parts:
                    idx = parts.index(marker)
                    if idx > 0 and parts[idx - 1] not in ("/", "\\", "", "."):
                        return parts[idx - 1]
            return ""

        for cfg in (self.integration_config, self.preprocessing_config):
            if isinstance(cfg, dict):
                for key in ("output_dir", "original_genome", "filled_genome"):
                    found = _from_path(cfg.get(key))
                    if found:
                        return found

        main_dir = getattr(self, "main_output_dir", None)
        if main_dir:
            found = _from_path(main_dir)
            if found:
                return found
            name = Path(str(main_dir)).name
            if name and name not in ("native", "output", "out", "05.visualization", ".") and not re.fullmatch(r"[0-9a-f]{32}", name):
                return name

        if isinstance(self.integration_config, dict) and self.integration_config.get("original_genome"):
            return Path(str(self.integration_config["original_genome"])).stem
        return ""

    @staticmethod
    def _parse_duration_seconds(raw):
        """Parse timedelta strings like '0:34:54.293767' or '1 day, 2:03:04' into float seconds."""
        if isinstance(raw, (int, float)):
            return max(0.0, float(raw))
        if not isinstance(raw, str) or not raw.strip():
            return None
        import re
        s = raw.strip()
        days = 0
        m_day = re.match(r"^(\d+)\s+days?,\s*(.+)$", s)
        if m_day:
            days = int(m_day.group(1))
            s = m_day.group(2).strip()
        parts = s.split(":")
        if len(parts) != 3:
            return None
        try:
            return days * 86400.0 + int(parts[0]) * 3600.0 + int(parts[1]) * 60.0 + float(parts[2])
        except ValueError:
            return None

    def _build_slim_runtime(self):
        """Extract privacy-safe timing, resource, parameter, and per-job metrics (no server paths)."""
        ps = getattr(self, "pipeline_summary", None)
        if not isinstance(ps, dict):
            return {}
        steps_raw = ps.get("steps")
        if not isinstance(steps_raw, dict) or not steps_raw:
            return {}

        step_order = ("step1", "step2", "step3", "step4", "step5")
        steps = []
        jobs = []
        for sid in step_order:
            st = steps_raw.get(sid)
            if not isinstance(st, dict):
                continue
            sec = self._parse_duration_seconds(st.get("duration"))
            if sec is None and st.get("start_time") and st.get("end_time"):
                try:
                    t0 = datetime.fromisoformat(str(st["start_time"]))
                    t1 = datetime.fromisoformat(str(st["end_time"]))
                    sec = max(0.0, (t1 - t0).total_seconds())
                except ValueError:
                    sec = None
            rec = {
                "id": sid,
                "name": str(st.get("name") or sid),
                "status": str(st.get("status") or "completed"),
                "start_time": st.get("start_time"),
                "end_time": st.get("end_time"),
                "seconds": round(sec, 2) if sec is not None else None,
            }
            if isinstance(st.get("peak_rss_mb"), (int, float)):
                rec["peak_rss_mb"] = round(float(st["peak_rss_mb"]), 1)
            steps.append(rec)

            if sid == "step3" and isinstance(st.get("result"), dict):
                res3 = st["result"]
                for bucket in ("completed_jobs", "failed_jobs", "skipped_jobs"):
                    for j in res3.get(bucket) or []:
                        if not isinstance(j, dict) or not j.get("job_name"):
                            continue
                        jsec = j.get("elapsed_time")
                        jrec = {
                            "job_name": str(j["job_name"]),
                            "status": str(j.get("status") or ("success" if bucket == "completed_jobs" else "failed")),
                            "seconds": round(float(jsec), 2) if isinstance(jsec, (int, float)) else None,
                        }
                        if j.get("start_time"):
                            jrec["start_time"] = str(j["start_time"])
                        if j.get("end_time"):
                            jrec["end_time"] = str(j["end_time"])
                        if isinstance(j.get("peak_rss_mb"), (int, float)):
                            jrec["peak_rss_mb"] = round(float(j["peak_rss_mb"]), 1)
                        if j.get("error"):
                            jrec["error"] = str(j["error"]).splitlines()[0][:120]
                        jobs.append(jrec)

        total_sec = self._parse_duration_seconds(ps.get("total_duration"))
        if total_sec is None:
            valid = [s["seconds"] for s in steps if s.get("seconds") is not None]
            total_sec = sum(valid) if valid else None

        params_raw = ps.get("parameters") if isinstance(ps.get("parameters"), dict) else {}
        safe_param_keys = (
            "workers", "thread", "kmer_filter", "kmer_size", "kmer_num",
            "MaximumExtensionLength", "MaximumExtensionRound",
            "filterDepthHifi", "filterDepthOnt", "edge", "remove",
        )
        safe_params = {k: params_raw[k] for k in safe_param_keys if k in params_raw and params_raw[k] is not None}

        return {
            "version": str(ps.get("version") or "2.0"),
            "start_time": ps.get("start_time"),
            "end_time": ps.get("end_time"),
            "total_seconds": round(total_sec, 2) if total_sec is not None else None,
            "parameters": safe_params,
            "steps": steps,
            "jobs": jobs,
        }

    def _build_gap_ext_rounds(self):
        """Extract [left_rounds, right_rounds] per gap without altering slim gapsByChrom."""
        gaps = self.gap_filling_results.get("gaps", []) if isinstance(self.gap_filling_results, dict) else []
        out = {}
        for g in gaps:
            if not isinstance(g, dict):
                continue
            chrom = g.get("chromosome")
            gid = g.get("gap_id")
            if not chrom or gid is None:
                continue
            key = f"{chrom}:{gid}"
            lv = g.get("left_rounds")
            rv = g.get("right_rounds")
            if isinstance(lv, int) and isinstance(rv, int):
                out[key] = [lv, rv]
                continue
            cd = g.get("connection_diagnostics")
            if isinstance(cd, list) and cd:
                if g.get("filled"):
                    elig = [e for e in cd if isinstance(e, dict) and e.get("status") == "eligible"]
                    if elig:
                        rounds = g.get("rounds")
                        picked = None
                        if isinstance(rounds, int):
                            for e in elig:
                                elv = e.get("left_version")
                                erv = e.get("right_version")
                                if isinstance(elv, int) and isinstance(erv, int) and (elv + erv) == rounds:
                                    picked = (elv, erv)
                        if picked is None:
                            last = elig[-1]
                            elv, erv = last.get("left_version"), last.get("right_version")
                            if isinstance(elv, int) and isinstance(erv, int):
                                picked = (elv, erv)
                        if picked is not None:
                            out[key] = [picked[0], picked[1]]
                            continue
                l_vals = [e["left_version"] for e in cd if isinstance(e, dict) and isinstance(e.get("left_version"), int)]
                r_vals = [e["right_version"] for e in cd if isinstance(e, dict) and isinstance(e.get("right_version"), int)]
                if l_vals or r_vals:
                    out[key] = [max(l_vals, default=0), max(r_vals, default=0)]
                    continue
            # Legacy single-direction fallback
            rounds = g.get("rounds")
            fdir = str(g.get("fill_direction") or "").lower()
            if isinstance(rounds, int):
                if fdir == "left":
                    out[key] = [rounds, 0]
                elif fdir == "right":
                    out[key] = [0, rounds]
        return out

    def _build_gap_boundary_notes(self):
        """Extract compact flank status & anchor backoff metadata per gap (without altering gapsByChrom)."""
        gaps = self.gap_filling_results.get("gaps", []) if isinstance(self.gap_filling_results, dict) else []
        out = {}
        for g in gaps:
            if not isinstance(g, dict):
                continue
            chrom = g.get("chromosome")
            gid = g.get("gap_id")
            if not chrom or gid is None:
                continue
            info = {}
            j = g.get("junction")
            if isinstance(j, dict):
                flanks = j.get("flanks")
                if isinstance(flanks, dict):
                    st_map = {}
                    for side in ("L", "R", "left", "right"):
                        fd = flanks.get(side)
                        if isinstance(fd, dict) and fd.get("status"):
                            sk = "L" if side.upper().startswith("L") else "R"
                            st_map[sk] = str(fd["status"]).strip().lower()
                    if st_map:
                        info["flanks"] = st_map
                repairs = j.get("repairs")
                if isinstance(repairs, list) and repairs:
                    acc = sum(1 for r in repairs if isinstance(r, dict) and str(r.get("status", "")).lower() == "accepted")
                    ret = sum(1 for r in repairs if isinstance(r, dict) and str(r.get("status", "")).lower() == "retained")
                    prot = sum(1 for r in repairs if isinstance(r, dict) and str(r.get("status", "")).lower() == "protected")
                    info["arp"] = [acc, ret, prot]
            retries = g.get("anchor_retries")
            if retries is None and isinstance(j, dict):
                retries = j.get("anchor_retries")
            if isinstance(retries, list) and retries:
                info["backoff"] = len(retries)
            if info:
                out[f"{chrom}:{gid}"] = info
        return out

    def _create_full_html(self):
        """创建完整的 HTML 内容"""
        summary = self.gap_filling_results.get('summary', {})

        # 准备数据
        from JunctionReport import render_project_junctions
        def _gap_report_href(gap):
            chrom = gap.get('chromosome')
            gap_id = gap.get('gap_id')
            if not chrom or gap_id is None:
                return None
            fill_dir = gap.get('fill_direction', 'none')
            if gap.get('report_direction') == 'bidirectional' or fill_dir == 'bidirectional':
                flag = 'bidirectional'
            elif gap.get('filled') and fill_dir in ('left', 'right'):
                flag = fill_dir
            else:
                flag = 'left'
            return f"{chrom}.{gap_id}.{flag}.html"
        junction_html = render_project_junctions(
            {'events': self.gap_filling_results.get('gaps', [])},
            include_event_details=False,
            event_href_fn=_gap_report_href,
        )
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        header_time = current_time[:16]
        total_gaps = summary.get('total_gaps', 0)
        filled_gaps = summary.get('filled_gaps', 0)
        unfilled_gaps = summary.get('unfilled_gaps', max(0, total_gaps - filled_gaps))
        fill_rate = summary.get('fill_rate', '0%')
        ext_filled = summary.get('extension_filled', 0)
        direct_filled = summary.get('direct_connection_filled', 0)
        chrom_count = len(self.gaps_by_chrom)
        fill_pct = (filled_gaps / total_gaps * 100.0) if total_gaps else 0.0

        project_name = self._infer_project_name()

        total_bp_added = None
        if self.integration_config:
            stats = self.integration_config.get('stats', {})
            total_bp_added = getattr(self, 'total_bp_added', stats.get('total_bp_added', 0))

        # 准备 JavaScript 数据（仅保留前端渲染与坐标投影所需字段，避免把冗长碱基修订明细塞入总览脚本）
        slim_gaps_by_chrom = {}
        for chrom, cdata in self.gaps_by_chrom.items():
            slim_gaps = []
            for gap in cdata.get('gaps', []):
                item = {
                    k: gap[k]
                    for k in (
                        'chromosome', 'gap_id', 'gap_start', 'gap_end', 'gap_len',
                        'filled', 'fill_length', 'fill_type', 'fill_direction',
                        'report_direction', 'rounds', 'status',
                    )
                    if k in gap
                }
                if isinstance(gap.get('junction'), dict):
                    j = gap['junction']
                    slim_j = {
                        k: j[k]
                        for k in ('mode', 'gap_length', 'flank_length_delta', 'overlap_trim')
                        if k in j
                    }
                    if slim_j:
                        item['junction'] = slim_j
                slim_gaps.append(item)
            slim_gaps_by_chrom[chrom] = {
                'gaps': slim_gaps,
                'total': cdata.get('total', len(slim_gaps)),
                'filled': cdata.get('filled', 0),
                'unfilled': cdata.get('unfilled', 0),
                'length': cdata.get('length', 0),
            }
        slim_runtime = self._build_slim_runtime()
        gap_ext_rounds = self._build_gap_ext_rounds()
        gap_boundary_notes = self._build_gap_boundary_notes()
        js_summary = json.dumps(summary, separators=(',', ':'))
        js_gaps_by_chrom = json.dumps(slim_gaps_by_chrom, separators=(',', ':'), default=str)
        js_preprocessing_config = json.dumps(self.preprocessing_config if self.preprocessing_config else {}, separators=(',', ':'))
        js_integration_config = json.dumps(self.integration_config if self.integration_config else {}, separators=(',', ':'))
        js_runtime_summary = json.dumps(slim_runtime, separators=(',', ':'), default=str)
        js_gap_ext_rounds = json.dumps(gap_ext_rounds, separators=(',', ':'))
        js_gap_boundary_notes = json.dumps(gap_boundary_notes, separators=(',', ':'))

        extra_css = """
        .table-toggle-container {
            position: sticky;
            bottom: 0;
            width: 100%;
            display: flex;
            justify-content: flex-end;
            padding: 8px 10px;
            background: var(--surface-header);
            border-top: 1px solid var(--border);
        }

        .table-toggle-btn {
            background: var(--surface);
            color: var(--accent);
            border: 1px solid var(--accent-border);
            border-radius: var(--radius-sm);
            padding: 5px 12px;
            font-size: 0.8rem;
            font-weight: 600;
            cursor: pointer;
            transition: background-color 0.15s ease, border-color 0.15s ease;
        }

        .table-toggle-btn:hover {
            background: var(--accent-soft);
            border-color: var(--accent);
        }

        .chrom-filter-icon {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            margin-left: 6px;
            padding: 2px 5px;
            border: 1px solid transparent;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.72rem;
            color: var(--ink-muted);
            position: relative;
            user-select: none;
            vertical-align: middle;
        }

        .chrom-filter-icon:hover {
            color: var(--ink);
            background: var(--surface);
            border-color: var(--border-strong);
        }

        .chrom-filter-menu {
            display: none;
            position: absolute;
            top: calc(100% + 4px);
            left: 0;
            background: var(--surface);
            border: 1px solid var(--border-strong);
            border-radius: var(--radius-sm);
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.1);
            z-index: 1000;
            min-width: 160px;
            max-height: 280px;
            overflow-y: auto;
            text-align: left;
        }

        .chrom-filter-menu.show {
            display: block;
        }

        .chrom-filter-item {
            padding: 7px 12px;
            cursor: pointer;
            font-size: 0.84rem;
            font-weight: 400;
            color: var(--ink);
            border-bottom: 1px solid var(--border);
            white-space: nowrap;
        }

        .chrom-filter-item:last-child {
            border-bottom: none;
        }

        .chrom-filter-item:hover {
            background: var(--surface-subtle);
        }

        .chrom-filter-item.active {
            background: var(--accent-soft);
            color: var(--accent);
            font-weight: 600;
        }

        .success {
            color: var(--ok-ink);
            font-weight: 600;
        }

        .failed {
            color: var(--err-ink);
            font-weight: 600;
        }

        .chrom-selector {
            background-color: var(--surface);
            border: 1px solid var(--border-strong);
            color: var(--ink);
            padding: 6px 32px 6px 12px;
            border-radius: var(--radius-sm);
            font-size: 0.84rem;
            font-weight: 500;
            cursor: pointer;
            appearance: none;
            background-image: url('data:image/svg+xml;charset=US-ASCII,%3Csvg%20width%3D%2212%22%20height%3D%227%22%20viewBox%3D%220%200%2012%207%22%20fill%3D%22none%22%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%3E%3Cpath%20d%3D%22M1%201L6%206L11%201%22%20stroke%3D%22%23334155%22%20stroke-width%3D%221.6%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22/%3E%3C/svg%3E');
            background-repeat: no-repeat;
            background-position: right 10px center;
            min-width: 180px;
        }

        .chrom-selector:hover {
            border-color: var(--accent);
        }

        .track-control-bar {
            display: none;
            padding: 8px 14px;
            background: var(--surface-subtle);
            border-bottom: 1px solid var(--border-subtle);
        }

        .track-control-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px 14px;
            flex-wrap: wrap;
        }

        .track-ctrl-left, .track-ctrl-right {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }

        .track-ctrl-right {
            flex: 1 1 280px;
            justify-content: flex-end;
        }

        .track-chr-summary {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: var(--text-xs);
            color: var(--text-secondary);
            font-variant-numeric: tabular-nums;
        }

        .track-chr-summary b {
            font-family: var(--font-mono);
            font-size: var(--text-sm);
            color: var(--text-primary);
            font-weight: 650;
        }

        .track-control-label {
            font-weight: 500;
            font-size: var(--text-xs);
            color: var(--text-muted);
            white-space: nowrap;
        }

        .track-control-value {
            font-family: var(--font-mono);
            font-weight: 600;
            font-size: var(--text-xs);
            color: var(--text-primary);
            font-variant-numeric: tabular-nums;
            min-width: 112px;
            text-align: right;
            white-space: nowrap;
        }

        input[type="range"] {
            -webkit-appearance: none;
            appearance: none;
            height: 4px;
            background: var(--border-default);
            border-radius: 999px;
            width: 148px;
            max-width: 100%;
            cursor: pointer;
        }

        input[type="range"]::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 13px;
            height: 13px;
            background: var(--brand);
            border: 2px solid var(--surface-panel);
            border-radius: 50%;
            box-shadow: 0 0 0 1px var(--brand);
            cursor: pointer;
            transition: transform 0.1s ease;
        }

        input[type="range"]::-webkit-slider-thumb:hover {
            transform: scale(1.12);
        }

        input[type="range"]::-moz-range-thumb {
            width: 13px;
            height: 13px;
            background: var(--brand);
            border: 2px solid var(--surface-panel);
            border-radius: 50%;
            box-shadow: 0 0 0 1px var(--brand);
            cursor: pointer;
        }

        .ov-chr-row.is-empty-win .ov-seg.is-src {
            opacity: 0.45;
        }

        .ov-win-range {
            font-family: var(--font-mono);
            font-size: var(--text-xs);
            font-weight: 500;
            color: var(--text-secondary);
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
        }

        .ov-chr-row.is-empty-win .ov-win-range {
            color: var(--text-muted);
        }

        .ov-win-pills {
            display: inline-flex;
            align-items: center;
            gap: 3px;
            flex-shrink: 0;
        }

        .ov-win-pill {
            font-family: var(--font-mono);
            font-size: 10px;
            font-weight: 600;
            padding: 0 4px;
            border-radius: 3px;
            line-height: 1.45;
            white-space: nowrap;
        }

        .ov-win-pill.is-ok {
            background: var(--tone-ok-bg);
            color: var(--tone-ok-ink);
        }

        .ov-win-pill.is-err {
            background: var(--tone-err-bg);
            color: var(--tone-err-ink);
        }

        .ov-rail.is-multirow {
            height: 28px;
        }

        .ov-rail.is-multirow .ov-seg.is-src {
            top: 8px;
            height: 12px;
        }

        .ov-rail.is-multirow .ov-seg.is-patch,
        .ov-rail.is-multirow .ov-seg.is-gap {
            top: 6px;
            height: 16px;
        }

        .ov-seg-tag {
            position: absolute;
            left: 50%;
            transform: translateX(-50%);
            font-family: var(--font-mono);
            font-size: 9.5px;
            font-weight: 650;
            line-height: 1;
            padding: 1px 3px;
            border-radius: 2px;
            white-space: nowrap;
            pointer-events: none;
        }

        .ov-seg-tag.is-top { bottom: calc(100% + 1px); }
        .ov-seg-tag.is-bot { top: calc(100% + 1px); }
        .ov-seg.is-patch .ov-seg-tag { color: var(--tone-ok-ink); }
        .ov-seg.is-gap .ov-seg-tag { color: var(--tone-err-ink); }

        #chromVisualization {
            min-height: 76px;
        }

        .chrom-track {
            margin-bottom: 12px;
            padding: 10px 14px 12px;
            border-bottom: 1px solid var(--border-subtle);
        }

        .chrom-track:last-child {
            margin-bottom: 0;
            border-bottom: none;
        }

        .chrom-track-multirow {
            margin-bottom: 0;
            padding: 10px 14px 12px;
        }

        .chrom-track-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 10px;
            margin-bottom: 6px;
            flex-wrap: wrap;
        }

        .chrom-track-name {
            font-family: var(--font-mono);
            font-weight: 600;
            font-size: var(--text-sm);
            color: var(--text-primary);
            overflow-wrap: anywhere;
        }

        .chrom-track-length {
            font-size: var(--text-xs);
            color: var(--text-muted);
            font-variant-numeric: tabular-nums;
        }

        .chrom-track-bar-container {
            position: relative;
            height: 50px;
            padding: 17px 0;
        }

        .chrom-track-bar {
            position: relative;
            height: 12px;
            background: var(--ds-0);
            border-radius: 2px;
            opacity: 0.88;
        }

        .gap-marker {
            position: absolute;
            transform: translateX(-50%);
            cursor: pointer;
            text-decoration: none;
            display: block;
            z-index: 2;
        }

        .gap-marker:hover {
            text-decoration: none;
            z-index: 5;
        }

        .gap-marker.top {
            top: 0;
            height: 50%;
        }

        .gap-marker.bottom {
            top: 25%;
            height: 50%;
        }

        .gap-marker-line {
            width: 3px;
            height: 100%;
            margin: 0 auto;
            border-radius: 1.5px;
            transition: transform 0.12s ease;
        }

        .gap-marker:hover .gap-marker-line {
            transform: scaleX(1.5);
        }

        .gap-marker.has-width {
            transform: none;
        }

        .gap-marker.has-width .gap-marker-line {
            width: 100%;
            margin: 0;
        }

        .gap-marker.has-width .gap-marker-label {
            left: 50%;
            transform: translateX(-50%);
        }

        .gap-marker-line.filled {
            background: var(--gen-closed);
        }

        .gap-marker-line.unfilled {
            background: var(--gen-gap);
        }

        .gap-marker-label {
            position: absolute;
            left: 50%;
            transform: translateX(-50%);
            font-family: var(--font-mono);
            font-size: var(--text-xs);
            font-weight: 600;
            white-space: nowrap;
            cursor: pointer;
            padding: 0 3px;
            border-radius: 3px;
            line-height: 1.25;
        }

        .gap-marker-label.top {
            bottom: 100%;
            margin-bottom: 2px;
        }

        .gap-marker-label.bottom {
            top: 100%;
            margin-top: 2px;
        }

        .gap-marker-label.filled {
            color: var(--tone-ok-ink);
        }

        .gap-marker-label.unfilled {
            color: var(--tone-err-ink);
        }

        .gap-marker:hover .gap-marker-label.filled {
            background: var(--tone-ok-bg);
            text-decoration: underline;
        }

        .gap-marker:hover .gap-marker-label.unfilled {
            background: var(--tone-err-bg);
            text-decoration: underline;
        }

        .status-filter-group {
            display: inline-flex;
            align-items: center;
            background: var(--surface-muted);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-sm);
            padding: 2px;
            gap: 2px;
        }

        .status-filter-btn {
            background: transparent;
            border: 0;
            color: var(--text-muted);
            padding: 3px 10px;
            border-radius: 3px;
            font-family: var(--font-sans);
            font-size: var(--text-xs);
            font-weight: 500;
            cursor: pointer;
            transition: background-color 0.12s ease, color 0.12s ease;
        }

        .status-filter-btn:hover {
            color: var(--text-primary);
        }

        .status-filter-btn.active {
            background: var(--surface-panel);
            color: var(--brand);
            font-weight: 650;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
        }

        /* CGAT-Aligned Overview Subblocks, Tracks, Charts & Runtime Bar */
        .ov-head-meta {
            font-size: var(--text-sm);
            font-weight: 500;
            color: var(--text-muted);
            font-variant-numeric: tabular-nums;
        }

        .ov-subblock + .ov-subblock {
            margin-top: 1.05rem;
            padding-top: 0.95rem;
            border-top: 1px solid var(--border-subtle);
        }

        .ov-sub-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.5rem 1rem;
            flex-wrap: wrap;
            margin: 0 0 0.55rem;
        }

        .ov-sub-head h3 {
            margin: 0;
            font-size: var(--text-sub);
            font-weight: 600;
            color: var(--text-primary);
        }

        .ov-p1-bar {
            display: inline-flex;
            align-items: center;
            gap: 0.65rem;
            flex-wrap: wrap;
        }

        .ov-bar-sep {
            display: inline-block;
            width: 1px;
            height: 12px;
            background: var(--border-default);
        }

        .legend-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem 0.95rem;
            margin: 0;
            font-size: var(--text-xs);
            color: var(--text-muted);
            align-items: center;
        }

        .legend-item {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            white-space: nowrap;
        }

        .swatch {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 2px;
            flex-shrink: 0;
        }

        .swatch.is-orig-gap {
            background: repeating-linear-gradient(135deg, var(--gen-gap) 0 2px, var(--surface-panel) 2px 4.5px);
            border: 1px solid var(--gen-gap);
        }

        .ov-track-frame {
            position: relative;
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius);
            background: var(--surface-panel);
            overflow: hidden;
            padding-bottom: 2.3rem;
        }

        .ov-track-frame.is-single {
            padding-bottom: 0;
        }

        .ov-axis, .ov-chr-row {
            display: grid;
            grid-template-columns: 180px minmax(0, 1fr);
            align-items: center;
            gap: 0.75rem;
        }

        .ov-axis {
            padding: 0.42rem 0.85rem 0.36rem;
            background: var(--surface-subtle);
            border-bottom: 1px solid var(--border-subtle);
            color: var(--text-secondary);
            font-size: var(--text-xs);
            font-weight: 600;
        }

        .story-ruler {
            position: relative;
            display: flex;
            justify-content: space-between;
            font-weight: 500;
            color: var(--text-muted);
            font-size: var(--text-xs);
            font-variant-numeric: tabular-nums;
            padding-bottom: 4px;
        }

        .story-ruler span {
            position: relative;
            line-height: 1.1;
        }

        .story-ruler span::after {
            content: "";
            position: absolute;
            left: 50%;
            bottom: -5px;
            width: 1px;
            height: 4px;
            background: var(--border-strong);
        }

        .story-ruler span:first-child::after { left: 0; }
        .story-ruler span:last-child::after { left: auto; right: 0; }

        .ov-chr-row {
            padding: 0.42rem 0.85rem;
            min-height: 2.15rem;
            border-bottom: 1px solid var(--border-subtle);
            transition: background-color 0.1s ease;
        }

        .ov-chr-row:last-child { border-bottom: 0; }
        .ov-chr-row:hover { background: var(--surface-subtle); }

        .ov-chr-meta {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: 0.32rem;
            min-width: 0;
        }

        .ov-chr-name {
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
            background: transparent;
            border: 0;
            padding: 0;
            font-family: var(--font-mono);
            font-size: var(--text-sm);
            font-weight: 600;
            line-height: 1.25;
            color: var(--text-primary);
            cursor: pointer;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            text-align: left;
        }

        .ov-chr-name:hover {
            color: var(--accent);
            text-decoration: underline;
        }

        .ov-chr-stats {
            display: inline-flex;
            align-items: baseline;
            gap: 0.32rem;
            flex-shrink: 0;
            font-variant-numeric: tabular-nums;
        }

        .ov-chr-len {
            font-size: var(--text-xs);
            color: var(--text-muted);
        }

        .ov-chr-gap {
            font-family: var(--font-mono);
            font-size: var(--text-xs);
            font-weight: 600;
            line-height: 1.2;
            padding: 1px 5px;
            border-radius: 3px;
            background: var(--surface-muted);
            color: var(--text-secondary);
        }

        .ov-chr-gap.is-zero {
            background: var(--tone-ok-bg);
            color: var(--tone-ok-ink);
        }

        .ov-rail {
            position: relative;
            display: block;
            height: 20px;
            min-width: 0;
            background-image: linear-gradient(to right, var(--border-subtle) 1px, transparent 1px);
            background-size: 25% 100%;
        }

        .ov-seg {
            position: absolute;
            top: 4px;
            height: 12px;
            border-radius: 2px;
        }

        .ov-seg.is-src {
            min-width: 4px;
            background: var(--ds-0);
            box-shadow: inset 0 0 0 0.6px rgba(255, 255, 255, 0.32);
            z-index: 1;
        }

        .ov-seg.is-patch {
            min-width: 6px;
            top: 3px;
            height: 14px;
            background: var(--gen-closed);
            box-shadow: inset 0 0 0 0.8px rgba(255, 255, 255, 0.55), 0 0 0 0.8px var(--gen-closed);
            z-index: 3;
            cursor: pointer;
        }

        .ov-seg.is-gap {
            min-width: 6px;
            top: 3px;
            height: 14px;
            background: repeating-linear-gradient(135deg, var(--gen-gap) 0 1.8px, var(--surface-panel) 1.8px 3.6px);
            box-shadow: inset 0 0 0 1px var(--gen-gap);
            z-index: 3;
            cursor: pointer;
        }

        .ov-seg.is-patch::after, .ov-seg.is-gap::after {
            content: "";
            position: absolute;
            left: 50%;
            top: 50%;
            transform: translate(-50%, -50%);
            width: max(100%, 14px);
            height: max(100%, 20px);
        }

        .ov-seg.is-patch:hover, .ov-seg.is-gap:hover {
            filter: brightness(1.12);
            z-index: 5;
        }

        .story-foot {
            margin: 0.5rem 0 0;
            color: var(--text-muted);
            font-size: var(--text-xs);
            line-height: 1.45;
        }

        .chart-zoom-btn {
            position: absolute;
            right: 10px;
            bottom: 8px;
            z-index: 4;
            display: inline-flex;
            align-items: center;
            gap: 0.32rem;
            height: 26px;
            padding: 0 8px;
            border: 1px solid var(--border-default);
            border-radius: var(--radius-sm);
            background: var(--surface-panel);
            color: var(--text-secondary);
            font-family: var(--font-sans);
            font-size: var(--text-xs);
            font-weight: 500;
            line-height: 1;
            cursor: pointer;
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.07);
            transition: border-color 0.12s ease, background-color 0.12s ease, color 0.12s ease;
        }

        .chart-zoom-btn:hover {
            border-color: var(--brand);
            background: var(--brand-soft);
            color: var(--brand);
        }

        /* Two-Column CGAT Charts Grid */
        .ov-charts-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.8rem;
        }

        @media (max-width: 860px) {
            .ov-charts-grid {
                grid-template-columns: 1fr;
            }
        }

        .ov-chart-card {
            display: flex;
            flex-direction: column;
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius);
            background: var(--surface-subtle);
            padding: 0.68rem 0.85rem 0.58rem;
            min-width: 0;
        }

        .ov-chart-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.5rem;
            margin: 0 0 0.36rem;
            flex-wrap: wrap;
        }

        .ov-chart-head-r {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            flex-shrink: 0;
        }

        .ov-mini-seg {
            display: inline-flex;
            align-items: center;
            padding: 1px;
            gap: 1px;
            border-radius: 4px;
            background: var(--surface-muted);
            border: 1px solid var(--border-subtle);
        }

        .ov-mini-seg button {
            height: 19px;
            padding: 0 6px;
            border: 0;
            border-radius: 3px;
            background: transparent;
            color: var(--text-muted);
            font-family: var(--font-sans);
            font-size: 10.5px;
            font-weight: 500;
            cursor: pointer;
            line-height: 1;
            transition: background-color 0.12s ease, color 0.12s ease;
        }

        .ov-mini-seg button:hover:not(.is-active) {
            color: var(--text-primary);
        }

        .ov-mini-seg button.is-active {
            background: var(--surface-panel);
            color: var(--brand);
            font-weight: 650;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
        }

        .ov-chart-head h4 {
            margin: 0;
            font-size: var(--text-sub);
            font-weight: 600;
            color: var(--text-primary);
        }

        .ov-chart-meta {
            font-family: var(--font-mono);
            font-size: var(--text-xs);
            font-weight: 500;
            line-height: 1.2;
            color: var(--text-muted);
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
        }

        .ov-chart-meta.is-ok {
            color: var(--gen-closed);
            font-weight: 600;
        }

        .ov-svg {
            display: block;
            width: 100%;
            height: auto;
            flex: 1 1 auto;
            background: var(--surface-panel);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-sm);
            padding: 0.22rem;
        }

        .ov-svg-scroll {
            flex: 1 1 auto;
            max-height: 236px;
            overflow-y: auto;
            background: var(--surface-panel);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-sm);
            padding: 0.22rem;
        }

        .ov-svg-scroll .ov-svg {
            border: 0;
            padding: 0;
            background: transparent;
        }

        .ov-ax-txt { font-family: var(--font-mono); font-size: var(--svg-micro); font-weight: 500; fill: var(--text-muted); }
        .ov-ax-lbl { font-family: var(--font-mono); font-size: var(--svg-label); font-weight: 600; fill: var(--text-secondary); }
        .ov-val-txt { font-family: var(--font-mono); font-size: var(--svg-label); font-weight: 600; fill: var(--text-primary); }
        .ov-bar-bp { font-family: var(--font-mono); font-size: var(--svg-micro); font-weight: 500; fill: var(--text-muted); }
        .ov-leg-txt { font-family: var(--font-sans); font-size: var(--svg-micro); font-weight: 500; fill: var(--text-secondary); }
        .ov-bar-lbl { font-family: var(--font-mono); font-size: var(--svg-label); font-weight: 600; fill: var(--text-secondary); }
        .ov-bar-val { font-family: var(--font-mono); font-size: var(--svg-micro); font-weight: 600; fill: var(--text-secondary); }
        .ov-bar-val.is-win { fill: var(--gen-closed); }

        .ov-bar-row { cursor: pointer; }
        .ov-bar-row:hover .ov-row-bg { fill: var(--brand-soft); }
        .ov-bar-row:hover .ov-bar-lbl { fill: var(--accent); }

        /* CGAT Runtime Bar & Minimalist Modal */
        .ov-runtime-bar {
            width: 100%;
            display: flex;
            align-items: center;
            gap: 0.55rem 0.85rem;
            flex-wrap: wrap;
            margin-top: 0.85rem;
            padding: 0.5rem 0.78rem;
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius);
            background: var(--surface-subtle);
            font-family: var(--font-sans);
            font-size: var(--text-xs);
            color: var(--text-secondary);
            font-variant-numeric: tabular-nums;
            text-align: left;
            cursor: pointer;
            transition: border-color 0.12s ease, background-color 0.12s ease, box-shadow 0.12s ease;
        }

        .ov-runtime-bar:hover {
            border-color: var(--brand);
            background: var(--surface-panel);
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
        }

        .ov-rt-head {
            white-space: nowrap;
            color: var(--text-muted);
        }

        .ov-rt-head b {
            color: var(--text-primary);
            font-family: var(--font-mono);
            font-weight: 600;
        }

        .ov-rt-track {
            flex: 1 1 150px;
            min-width: 110px;
            display: flex;
            height: 7px;
            border-radius: 999px;
            overflow: hidden;
            background: var(--surface-muted);
            gap: 1px;
        }

        .ov-rt-seg {
            display: block;
            height: 100%;
        }

        .ov-rt-legend {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem 0.65rem;
            flex-wrap: wrap;
        }

        .ov-rt-item {
            display: inline-flex;
            align-items: center;
            gap: 0.26rem;
            white-space: nowrap;
        }

        .ov-rt-item b {
            font-family: var(--font-mono);
            font-weight: 600;
            color: var(--text-primary);
        }

        .ov-rt-dot {
            display: inline-block;
            width: 7px;
            height: 7px;
            border-radius: 2px;
            flex-shrink: 0;
        }

        .ov-rt-more {
            margin-left: auto;
            color: var(--accent);
            font-weight: 600;
            white-space: nowrap;
        }

        /* Shared CGAT Story Dialog (Runtime & Zoom Modals) */
        dialog.story-dialog {
            width: min(1020px, calc(100vw - 28px));
            max-height: calc(100vh - 36px);
            padding: 0;
            border: 1px solid var(--border-default);
            border-radius: var(--radius);
            background: var(--surface-panel);
            color: var(--text-primary);
            box-shadow: 0 20px 50px rgba(15, 23, 42, 0.24);
            overflow: hidden;
        }

        dialog.story-dialog::backdrop {
            background: rgba(15, 23, 42, 0.45);
            backdrop-filter: blur(2px);
        }

        .dlg-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding: 0.72rem 1.05rem;
            border-bottom: 1px solid var(--border-subtle);
            background: var(--surface-panel);
        }

        .dlg-head h3 {
            margin: 0;
            font-size: var(--text-card);
            font-weight: 650;
            color: var(--text-primary);
        }

        .dlg-close {
            width: 28px;
            height: 28px;
            border-radius: var(--radius-sm);
            border: 1px solid var(--border-subtle);
            background: var(--surface-subtle);
            color: var(--text-secondary);
            font-size: 1rem;
            line-height: 1;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }

        .dlg-close:hover {
            border-color: var(--border-default);
            background: var(--surface-hover);
            color: var(--text-primary);
        }

        .dlg-body {
            padding: 0.9rem 1.05rem 1.15rem;
            overflow-y: auto;
            max-height: calc(100vh - 96px);
        }

        .story-meta-strip {
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem 0.95rem;
            align-items: center;
            font-size: var(--text-sm);
            color: var(--text-secondary);
            font-variant-numeric: tabular-nums;
        }

        .story-meta-strip b {
            color: var(--text-primary);
            font-family: var(--font-mono);
            font-weight: 600;
        }

        .ov-rt-strip {
            margin: 0 0 0.75rem;
            padding: 0.45rem 0.68rem;
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-sm);
            background: var(--surface-subtle);
        }

        .ov-rt-params {
            margin: 0.78rem 0 0.45rem;
            font-size: var(--text-xs);
            color: var(--text-muted);
            font-variant-numeric: tabular-nums;
        }

        .ov-rt-table-wrap {
            overflow-x: auto;
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-sm);
            background: var(--surface-panel);
        }

        .ov-rt-table {
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
            font-size: var(--text-sm);
            text-align: left;
        }

        .ov-rt-table th, .ov-rt-table td {
            padding: 7px 12px;
            font-size: var(--text-sm);
            border-top: 0;
            border-bottom: 1px solid var(--border-subtle);
            vertical-align: middle;
        }

        .ov-rt-table thead th {
            font-size: var(--text-xs);
            font-weight: 600;
            color: var(--text-secondary);
            background: var(--surface-subtle);
            white-space: nowrap;
            border-bottom: 1px solid var(--border-subtle);
        }

        .ov-rt-table tbody th[scope="row"] {
            background: transparent;
            color: var(--text-primary);
            font-weight: 500;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .ov-rt-table tbody tr:hover > td,
        .ov-rt-table tbody tr:hover > th {
            background: var(--surface-subtle);
        }

        .ov-rt-table tbody tr:last-child > * {
            border-bottom: 0;
        }

        .ov-rt-table .col-unit { width: 32%; }
        .ov-rt-table .col-stage { width: 16%; white-space: nowrap; color: var(--text-secondary); }
        .ov-rt-table .col-num {
            width: 13%;
            text-align: right;
            white-space: nowrap;
            font-variant-numeric: tabular-nums;
        }
        .ov-rt-table .col-status {
            width: 13%;
            text-align: center;
            white-space: nowrap;
        }

        .rt-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.3rem;
            padding: 1px 7px;
            border-radius: 3px;
            font-size: var(--text-xs);
            font-weight: 500;
            line-height: 1.4;
            border: 1px solid transparent;
            white-space: nowrap;
        }

        .rt-badge.tone-ok {
            color: var(--tone-ok-ink);
            background: var(--tone-ok-bg);
            border-color: var(--tone-ok-line);
        }

        .rt-badge.tone-err {
            color: var(--tone-err-ink);
            background: var(--tone-err-bg);
            border-color: var(--tone-err-line);
        }

        .rt-badge.tone-info {
            color: var(--tone-info-ink);
            background: var(--tone-info-bg);
            border-color: var(--tone-info-line);
        }

        .rt-badge.tone-warn {
            color: var(--tone-warn-ink);
            background: var(--tone-warn-bg);
            border-color: var(--tone-warn-line);
        }

        /* Zoom Dialog Stage (aligned with CGAT) */
        .story-zoom-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            flex-wrap: wrap;
            margin-bottom: 0.65rem;
        }

        .story-zoom-ctrl {
            display: inline-flex;
            align-items: center;
            gap: 0.3rem;
            font-size: var(--text-sm);
        }

        .story-zoom-ctrl button {
            display: inline-grid;
            place-items: center;
            min-width: 28px;
            height: 28px;
            padding: 0 0.5rem;
            border: 1px solid var(--border-default);
            border-radius: var(--radius-sm);
            background: var(--surface-subtle);
            color: var(--text-primary);
            font: 600 var(--text-sm)/1 var(--font-mono);
            cursor: pointer;
        }

        .story-zoom-ctrl button:hover:not(:disabled) {
            border-color: var(--brand);
            background: var(--brand-soft);
            color: var(--brand);
        }

        .story-zoom-ctrl button:disabled {
            opacity: 0.42;
            cursor: not-allowed;
        }

        .story-zoom-pct {
            min-width: 44px;
            text-align: center;
            font: 600 var(--text-sm)/1 var(--font-mono);
            color: var(--text-secondary);
            font-variant-numeric: tabular-nums;
        }

        .story-zoom-stage {
            overflow: auto;
            max-height: 70vh;
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius);
            background: var(--surface-panel);
        }

        .story-zoom-stage.is-pannable { cursor: grab; }
        .story-zoom-stage.is-dragging { cursor: grabbing; user-select: none; }

        .story-zoom-stage .ov-track-inner {
            min-width: 100%;
            width: calc(100% * var(--chart-scale, 1));
        }

        .story-zoom-stage .ov-axis, .story-zoom-stage .ov-chr-row {
            grid-template-columns: 196px minmax(0, 1fr);
            gap: 0;
            padding: 0;
            align-items: stretch;
        }

        .story-zoom-stage .ov-axis {
            position: sticky;
            top: 0;
            z-index: 8;
        }

        .story-zoom-stage .ov-axis > :first-child {
            position: sticky;
            left: 0;
            z-index: 9;
            background: var(--surface-subtle);
            padding: 0.48rem 0.7rem 0.42rem 0.9rem;
            border-right: 1px solid var(--border-subtle);
            display: flex;
            align-items: center;
        }

        .story-zoom-stage .ov-axis .story-ruler {
            margin: 0.48rem 1rem 0.42rem 0.8rem;
        }

        .story-zoom-stage .ov-chr-meta {
            position: sticky;
            left: 0;
            z-index: 5;
            background: var(--surface-panel);
            padding: 0.5rem 0.7rem 0.5rem 0.9rem;
            border-right: 1px solid var(--border-subtle);
            align-items: center;
        }

        .story-zoom-stage .ov-chr-row:hover .ov-chr-meta {
            background: var(--surface-subtle);
        }

        .story-zoom-stage .ov-rail {
            margin: 0.42rem 1rem 0.42rem 0.8rem;
            height: 22px;
        }

        @media (max-width: 760px) {
            .ov-axis, .ov-chr-row {
                grid-template-columns: 124px minmax(0, 1fr);
                gap: 0.45rem;
                padding-left: 0.65rem;
                padding-right: 0.65rem;
            }
            .ov-bar-sep { display: none; }
        }

        .tooltip {
            position: absolute;
            background: #0f172a;
            color: #f8fafc;
            border: 1px solid #334155;
            padding: 9px 12px;
            border-radius: var(--radius-sm);
            font-size: 0.78rem;
            line-height: 1.5;
            pointer-events: none;
            z-index: 1000;
            display: none;
            max-width: 340px;
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.2);
        }

        .cell-subnote {
            display: block;
            font-size: 0.75rem;
            font-weight: 400;
            color: var(--ink-muted);
            margin-top: 2px;
        }

        .table-link {
            display: inline-flex;
            align-items: center;
            padding: 2px 9px;
            border-radius: 5px;
            border: 1px solid var(--accent-border);
            background: var(--accent-soft);
            color: var(--accent);
            font-size: var(--text-xs);
            font-weight: 600;
            white-space: nowrap;
            transition: background-color 0.12s ease, border-color 0.12s ease;
        }

        .table-link:hover {
            background: #dbeafe;
            border-color: var(--accent);
            text-decoration: none;
        }

        .fold-body > .jr-root { border: 0; margin: 0; box-shadow: none; }
        .fold-body > .jr-root > .section-header { display: none; }
        .fold-body > .jr-root > .section-body { padding: 4px 0 0; }
        .back-all-btn {
            background: var(--surface);
            color: var(--accent);
            border: 1px solid var(--accent-border);
            border-radius: var(--radius-sm);
            padding: 4px 10px;
            font-family: var(--font-sans);
            font-size: var(--text-xs);
            font-weight: 600;
            cursor: pointer;
            white-space: nowrap;
        }
        .back-all-btn:hover { background: var(--accent-soft); border-color: var(--accent); }
        .reads-bar { display: flex; flex-wrap: wrap; gap: 6px 18px; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); font-size: var(--text-xs); color: var(--ink-muted); }
        .reads-bar b { color: var(--ink); font-weight: 600; }
        table.hide-uniform-dir [data-col="dir"] { display: none; }
        """

        css = report_css(extra_css)
        junction_drawer_html = ""
        if junction_html:
            junction_drawer_html = f"""
            <details class="fold">
                <summary><span class="fold-title"><span class="lang-en">Junction &amp; Connection Diagnostics</span><span class="lang-zh">连接边界与诊断</span></span></summary>
                <div class="fold-body">{junction_html}</div>
            </details>"""

        brand_icon = degap_logo_html(24)
        title_proj_html = (
            f'<span class="degap-heading-project" title="{esc(project_name)}">{esc(project_name)}</span>'
            if project_name
            else '<span class="degap-heading-project"><span class="lang-en">Gap Filling</span><span class="lang-zh">缺口填补</span></span>'
        )
        net_bp_label = esc(self._format_bp(total_bp_added)) if total_bp_added is not None else ""

        html = f"""<!DOCTYPE html>
<html lang="en" data-lang="en" data-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DEGAP (AutoGapfiller) Report{f": {esc(project_name)}" if project_name else ""}</title>
    <style>
{css}
    </style>
</head>
<body>
    <!-- Sticky Single-Row Topbar (aligned with CGAT Server Report) -->
    <header class="degap-topbar">
        <div class="degap-topbar-inner">
            <div class="degap-topbar-left">
                {brand_icon}
                <h1>
                    <span class="degap-heading-prefix"><span class="lang-zh">DEGAP（AutoGapfiller）报告：</span><span class="lang-en">DEGAP (AutoGapfiller) Report: </span></span>
                    {title_proj_html}
                </h1>
            </div>
            <div class="degap-topbar-right">
                <time class="degap-time" datetime="{esc(current_time)}" title="{esc(current_time)}">{esc(header_time)}</time>
                <span class="hdr-sep" aria-hidden="true"></span>
                <div class="language-switcher" role="group" aria-label="Language Switcher">
                    <button type="button" class="language-btn" data-lang="zh" aria-pressed="false" onclick="switchLanguage('zh')">中文</button>
                    <button type="button" class="language-btn active" data-lang="en" aria-pressed="true" onclick="switchLanguage('en')">EN</button>
                </div>
                <button type="button" class="theme-btn" id="themeToggleBtn" data-theme-toggle="1" onclick="toggleTheme()" title="Switch to dark theme" aria-label="Switch to dark theme">
                    <svg class="ico-moon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>
                    <svg class="ico-sun" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2m-7.07-14.93 1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>
                </button>
            </div>
        </div>
    </header>

    <main class="container">
        <!-- Unnumbered Overview Card (aligned with CGAT: Tracks + 2 Key Charts + Runtime Strip) -->
        <section class="section" id="degap-overview">
            <div class="section-header">
                <h2><span class="lang-en">Overview</span><span class="lang-zh">总览</span></h2>
                <span class="ov-head-meta">
                    <span class="lang-zh">{chrom_count} 条含 Gap 染色体 · {esc(filled_gaps)} / {esc(total_gaps)} 已填补（{esc(fill_rate)}）{f" · 净变化 {net_bp_label}" if net_bp_label else ""}</span>
                    <span class="lang-en">{chrom_count} gap chrs · {esc(filled_gaps)} / {esc(total_gaps)} filled ({esc(fill_rate)}){f" · Net {net_bp_label}" if net_bp_label else ""}</span>
                </span>
            </div>
            <div class="section-body">
                <!-- Subblock 1: Chromosome Gap-Filling Tracks -->
                <div class="ov-subblock">
                    <div class="ov-sub-head">
                        <h3><span class="lang-zh">染色体分布</span><span class="lang-en">Chromosome Distribution</span></h3>
                        <div class="ov-p1-bar">
                            <div class="legend-row">
                                <span class="legend-item"><i class="swatch" style="background:var(--ds-0)"></i><span class="lang-zh">染色体序列</span><span class="lang-en">Sequence</span></span>
                                <span class="legend-item"><i class="swatch" style="background:var(--gen-closed)"></i><span class="lang-zh">已填补 Gap</span><span class="lang-en">Filled</span></span>
                                <span class="legend-item"><i class="swatch is-orig-gap"></i><span class="lang-zh">未填补 Gap</span><span class="lang-en">Unfilled</span></span>
                            </div>
                            <span class="ov-bar-sep" aria-hidden="true"></span>
                            <select id="chromSelect" class="chrom-selector" aria-label="Select chromosome" onchange="filterChromosome()">
                                <option value="all">All Chromosomes</option>
                            </select>
                        </div>
                    </div>
                    <div class="ov-track-frame" id="ovTrackFrame">
                        <div id="trackLengthControl" class="track-control-bar">
                            <div class="track-control-row">
                                <div class="track-ctrl-left">
                                    <button type="button" class="back-all-btn" onclick="resetAllChromosomes()"><span class="lang-en">← All</span><span class="lang-zh">← 返回全部</span></button>
                                    <span id="trackChrSummary" class="track-chr-summary"></span>
                                </div>
                                <div class="track-ctrl-right">
                                    <div class="ov-mini-seg" role="group" aria-label="Row presets">
                                        <button type="button" data-row-preset="1" onclick="setTrackRowPreset(1)"><span class="lang-zh">全长</span><span class="lang-en">1 row</span></button>
                                        <button type="button" data-row-preset="4" onclick="setTrackRowPreset(4)"><span class="lang-zh">4 行</span><span class="lang-en">4 rows</span></button>
                                        <button type="button" data-row-preset="8" onclick="setTrackRowPreset(8)"><span class="lang-zh">8 行</span><span class="lang-en">8 rows</span></button>
                                    </div>
                                    <label for="trackLengthSlider" class="track-control-label">
                                        <span class="lang-en">Window:</span>
                                        <span class="lang-zh">单行长度</span>
                                    </label>
                                    <input type="range" id="trackLengthSlider" min="100000" max="100000000" step="100000"
                                           oninput="updateTrackLength()">
                                    <span id="trackLengthValue" class="track-control-value">1.00 Mb</span>
                                </div>
                            </div>
                        </div>
                        <div id="chromVisualization">
                            <!-- Will be populated by JavaScript -->
                        </div>
                        <button type="button" class="chart-zoom-btn" id="ovTrackZoomBtn" onclick="openTrackZoom()" title="放大查看 / Enlarge view" aria-label="放大查看 / Enlarge view">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
                            <span><span class="lang-zh">放大</span><span class="lang-en">Zoom</span></span>
                        </button>
                    </div>
                    <p class="story-foot" id="chromCoordinateNote">
                        <span class="lang-en">Uses original assembly coordinate frame · click a gap to open details, click a chromosome name for multi-row view</span>
                        <span class="lang-zh">原始组装坐标系 · 点击 Gap 区块打开详情，点击染色体名展开多行视图</span>
                    </p>
                </div>

                <!-- Subblock 2: Two Focused Key Metrics Charts (aligned with CGAT) -->
                <div class="ov-subblock">
                    <div class="ov-sub-head">
                        <h3><span class="lang-zh">关键指标</span><span class="lang-en">Key Metrics</span></h3>
                    </div>
                    <div class="ov-charts-grid" role="group" aria-label="Key gap filling metrics">
                        <article class="ov-chart-card">
                            <div class="ov-chart-head">
                                <h4><span class="lang-zh">各染色体 Gap 数量与长度</span><span class="lang-en">Gap Count &amp; Length by Chr</span></h4>
                                <div class="ov-chart-head-r">
                                    <span class="ov-chart-meta is-ok" id="ovChromStatsMeta"></span>
                                    <div class="ov-mini-seg" role="group" aria-label="Chart layout">
                                        <button type="button" class="is-active" data-chr-mode="vertical" aria-pressed="true" onclick="setChromChartMode('vertical')"><span class="lang-zh">竖柱</span><span class="lang-en">Bars</span></button>
                                        <button type="button" data-chr-mode="horizontal" aria-pressed="false" onclick="setChromChartMode('horizontal')"><span class="lang-zh">横条</span><span class="lang-en">Rows</span></button>
                                    </div>
                                </div>
                            </div>
                            <div id="ovChromStatsChart"></div>
                        </article>
                        <article class="ov-chart-card">
                            <div class="ov-chart-head">
                                <h4><span class="lang-zh">各 Gap 填补情况（长度与 L/R 轮次）</span><span class="lang-en">Per-Gap Closure (Length &amp; L/R)</span></h4>
                                <span class="ov-chart-meta" id="ovGapDetailMeta"></span>
                            </div>
                            <div id="ovGapDetailChart"></div>
                        </article>
                    </div>

                    <!-- Subblock 3: Clickable Runtime Telemetry Strip (CGAT style) -->
                    <button type="button" class="ov-runtime-bar" id="ovRuntimeBar" style="display:none;" onclick="openRuntimeModal()" aria-label="Open runtime details"></button>
                </div>
            </div>
        </section>

        <!-- 01 Input Data Card -->
        <section class="section" id="degap-inputs" style="display:none;">
            <div class="section-header">
                <h2><span class="card-num">01</span><span class="lang-en">Input Data</span><span class="lang-zh">输入数据</span></h2>
            </div>
            <div class="section-body">
                <div class="dataset-scroll">
                    <table class="dataset-table" id="inputDataTable">
                        <thead>
                            <tr>
                                <th class="lang-en">Input</th>
                                <th class="lang-zh">输入项</th>
                                <th class="lang-en">Role</th>
                                <th class="lang-zh">角色</th>
                                <th class="lang-en">Scale</th>
                                <th class="lang-zh">规模</th>
                                <th class="lang-en">Length Stats</th>
                                <th class="lang-zh">长度统计</th>
                                <th class="lang-en">Summary</th>
                                <th class="lang-zh">摘要</th>
                            </tr>
                        </thead>
                        <tbody id="inputDataTableBody"></tbody>
                    </table>
                </div>
                <div id="readsInfoBar" class="input-aux-bar" style="display:none;"></div>
            </div>
        </section>

        <!-- 02 Gap Filling Tasks Card -->
        <section class="section" id="sec-tasks">
            <div class="section-header">
                <h2><span class="card-num">02</span><span class="lang-en">Gap Filling Tasks</span><span class="lang-zh">Gap 填补明细</span></h2>
                <div class="status-filter-group" role="group" aria-label="Filter gap status">
                    <button type="button" class="status-filter-btn active" data-status="all" onclick="filterTasksByStatus('all')"><span class="lang-en">All ({esc(total_gaps)})</span><span class="lang-zh">全部 ({esc(total_gaps)})</span></button>
                    <button type="button" class="status-filter-btn" data-status="filled" onclick="filterTasksByStatus('filled')"><span class="lang-en">Filled ({esc(filled_gaps)})</span><span class="lang-zh">已填补 ({esc(filled_gaps)})</span></button>
                    <button type="button" class="status-filter-btn" data-status="unfilled" onclick="filterTasksByStatus('unfilled')"><span class="lang-en">Unfilled ({esc(unfilled_gaps)})</span><span class="lang-zh">未填补 ({esc(unfilled_gaps)})</span></button>
                </div>
            </div>
            <div class="section-body">
                <div id="tasks-table-container" class="table-container-limited">
                    <table id="gapFillingTasksTable">
                        <thead>
                            <tr>
                                <th class="lang-en">
                                    Chromosome
                                    <span class="chrom-filter-icon" tabindex="0" role="button" aria-label="Filter chromosome" onclick="toggleFilterMenu('tasks', event)" onkeydown="if(event.key==='Enter'||event.key===' '){{event.preventDefault();toggleFilterMenu('tasks', event);}}">
                                        ▼
                                        <div id="tasks-chrom-filter" class="chrom-filter-menu"></div>
                                    </span>
                                </th>
                                <th class="lang-zh">
                                    染色体
                                    <span class="chrom-filter-icon" tabindex="0" role="button" aria-label="筛选染色体" onclick="toggleFilterMenu('tasks', event)" onkeydown="if(event.key==='Enter'||event.key===' '){{event.preventDefault();toggleFilterMenu('tasks', event);}}">
                                        ▼
                                        <div id="tasks-chrom-filter-zh" class="chrom-filter-menu"></div>
                                    </span>
                                </th>
                                <th class="lang-en">Gap ID</th>
                                <th class="lang-zh">Gap ID</th>
                                <th class="lang-en">Region</th>
                                <th class="lang-zh">原始区域</th>
                                <th class="lang-en">Filled</th>
                                <th class="lang-zh">状态</th>
                                <th data-col="dir" class="lang-en">Direction</th>
                                <th data-col="dir" class="lang-zh">方向/模式</th>
                                <th class="lang-en">Rounds</th>
                                <th class="lang-zh">轮次</th>
                                <th class="lang-en">Fill Length</th>
                                <th class="lang-zh">填补长度</th>
                                <th class="lang-en">Boundary / Backoff</th>
                                <th class="lang-zh">边界 / 回退</th>
                                <th class="lang-en">Details</th>
                                <th class="lang-zh">详情</th>
                            </tr>
                        </thead>
                        <tbody id="gapFillingTasksTableBody">
                            <!-- Will be populated by JavaScript -->
                        </tbody>
                    </table>
                    <div class="table-toggle-container">
                        <button type="button" id="tasks-toggle-btn" class="table-toggle-btn" onclick="toggleTableExpand('tasks')"><span class="lang-en">Expand</span><span class="lang-zh">展开</span></button>
                    </div>
                </div>

                <!-- Secondary Appendices Folded Under 02 (no redundant top-level 03 card) -->
                <div class="sec-appendices" style="margin-top:12px;border-top:1px solid var(--border-subtle);padding-top:4px;">
                    <details class="fold">
                        <summary><span class="fold-title"><span class="lang-en">Remaining Gaps (Final Coordinates)</span><span class="lang-zh">剩余未填补 Gap（终版坐标清单）</span> <span id="remainingCount" class="muted num"></span></span></summary>
                        <div class="fold-body">
                            <div id="final-table-container" class="table-container-limited">
                                <table id="finalGenomeTable">
                                    <thead>
                                        <tr>
                                            <th class="lang-en">
                                                Chromosome
                                                <span class="chrom-filter-icon" tabindex="0" role="button" aria-label="Filter chromosome" onclick="toggleFilterMenu('final', event)" onkeydown="if(event.key==='Enter'||event.key===' '){{event.preventDefault();toggleFilterMenu('final', event);}}">
                                                    ▼
                                                    <div id="final-chrom-filter" class="chrom-filter-menu"></div>
                                                </span>
                                            </th>
                                            <th class="lang-zh">
                                                染色体
                                                <span class="chrom-filter-icon" tabindex="0" role="button" aria-label="筛选染色体" onclick="toggleFilterMenu('final', event)" onkeydown="if(event.key==='Enter'||event.key===' '){{event.preventDefault();toggleFilterMenu('final', event);}}">
                                                    ▼
                                                    <div id="final-chrom-filter-zh" class="chrom-filter-menu"></div>
                                                </span>
                                            </th>
                                            <th class="lang-en">Gap ID</th>
                                            <th class="lang-zh">Gap ID</th>
                                            <th class="lang-en">Region</th>
                                            <th class="lang-zh">终版区域</th>
                                            <th class="lang-en">Details</th>
                                            <th class="lang-zh">详情</th>
                                        </tr>
                                    </thead>
                                    <tbody id="finalGenomeTableBody">
                                        <!-- Will be populated by JavaScript -->
                                    </tbody>
                                </table>
                                <div class="table-toggle-container">
                                    <button type="button" id="final-toggle-btn" class="table-toggle-btn" onclick="toggleTableExpand('final')"><span class="lang-en">Expand</span><span class="lang-zh">展开</span></button>
                                </div>
                            </div>
                        </div>
                    </details>

                    <details class="fold" hidden>
                        <summary><span class="fold-title"><span class="lang-en">Initial Gap Coordinates</span><span class="lang-zh">初始 Gap 坐标清单</span></span></summary>
                        <div class="fold-body">
                            <div id="initial-table-container" class="table-container-limited">
                                <table id="initialGenomeTable">
                                    <thead>
                                        <tr>
                                            <th class="lang-en">
                                                Chromosome
                                                <span class="chrom-filter-icon" tabindex="0" role="button" aria-label="Filter chromosome" onclick="toggleFilterMenu('initial', event)" onkeydown="if(event.key==='Enter'||event.key===' '){{event.preventDefault();toggleFilterMenu('initial', event);}}">
                                                    ▼
                                                    <div id="initial-chrom-filter" class="chrom-filter-menu"></div>
                                                </span>
                                            </th>
                                            <th class="lang-zh">
                                                染色体
                                                <span class="chrom-filter-icon" tabindex="0" role="button" aria-label="筛选染色体" onclick="toggleFilterMenu('initial', event)" onkeydown="if(event.key==='Enter'||event.key===' '){{event.preventDefault();toggleFilterMenu('initial', event);}}">
                                                    ▼
                                                    <div id="initial-chrom-filter-zh" class="chrom-filter-menu"></div>
                                                </span>
                                            </th>
                                            <th class="lang-en">Gap ID</th>
                                            <th class="lang-zh">Gap ID</th>
                                            <th class="lang-en">Region</th>
                                            <th class="lang-zh">区域</th>
                                        </tr>
                                    </thead>
                                    <tbody id="initialGenomeTableBody">
                                        <!-- Will be populated by JavaScript -->
                                    </tbody>
                                </table>
                                <div class="table-toggle-container">
                                    <button type="button" id="initial-toggle-btn" class="table-toggle-btn" onclick="toggleTableExpand('initial')"><span class="lang-en">Expand</span><span class="lang-zh">展开</span></button>
                                </div>
                            </div>
                        </div>
                    </details>{junction_drawer_html}
                </div>
            </div>
        </section>
        <footer class="report-footer">
            <p>DEGAP · AutoGapfiller</p>
        </footer>
    </main>

    <!-- Runtime Detail Modal (aligned with CGAT ov-runtime-modal) -->
    <dialog id="degapRuntimeDialog" class="story-dialog" aria-labelledby="rtDlgTitle">
        <div class="dlg-head">
            <h3 id="rtDlgTitle"><span class="lang-zh">运行耗时与资源详情</span><span class="lang-en">Runtime &amp; Resource Details</span></h3>
            <button type="button" class="dlg-close" onclick="closeRuntimeModal()" aria-label="Close">×</button>
        </div>
        <div class="dlg-body" id="rtDlgBody"></div>
    </dialog>

    <!-- Track Zoom Modal (aligned with CGAT chart zoom) -->
    <dialog id="degapZoomDialog" class="story-dialog" aria-labelledby="zoomDlgTitle">
        <div class="dlg-head">
            <h3 id="zoomDlgTitle"><span class="lang-zh">总览 · 染色体分布放大视图</span><span class="lang-en">Overview · Chromosome Track Zoom</span></h3>
            <button type="button" class="dlg-close" onclick="closeTrackZoom()" aria-label="Close">×</button>
        </div>
        <div class="dlg-body" id="zoomDlgBody"></div>
    </dialog>

    <!-- Tooltip -->
    <div class="tooltip" id="tooltip" role="tooltip"></div>

    <script>
        // Data from Python
        const summary = {js_summary};
        const gapsByChrom = {js_gaps_by_chrom};
        const preprocessingConfig = {js_preprocessing_config};
        const integrationConfig = {js_integration_config};
        const runtimeSummary = {js_runtime_summary};
        const gapExtRounds = {js_gap_ext_rounds};
        const gapBoundaryNotes = {js_gap_boundary_notes};

        // Current language & chart view state (default: EN + Light theme)
        let currentLang = 'en';
        let selectedTaskStatus = 'all';
        let chromChartMode = null; // null -> auto ('vertical' when <=10 chrs, else 'horizontal')

        function setChromChartMode(mode) {{
            chromChartMode = (mode === 'horizontal') ? 'horizontal' : 'vertical';
            document.querySelectorAll('[data-chr-mode]').forEach(btn => {{
                const active = btn.getAttribute('data-chr-mode') === chromChartMode;
                btn.classList.toggle('is-active', active);
                btn.setAttribute('aria-pressed', active ? 'true' : 'false');
            }});
            if (typeof renderOverviewCharts === 'function') {{
                renderOverviewCharts();
            }}
        }}

        function escapeHtml(value) {{
            return String(value ?? '')
                .replaceAll('&', '&amp;')
                .replaceAll('<', '&lt;')
                .replaceAll('>', '&gt;')
                .replaceAll('"', '&quot;')
                .replaceAll("'", '&#039;');
        }}

        function isDarkTheme() {{
            const root = document.documentElement;
            const cur = root && root.getAttribute ? root.getAttribute('data-theme') : null;
            return cur === 'dark';
        }}

        function syncThemeButton() {{
            const btn = document.getElementById('themeToggleBtn');
            if (!btn) return;
            const dark = isDarkTheme();
            const en = currentLang === 'en';
            const lbl = dark ? (en ? 'Switch to light theme' : '切换为浅色主题') : (en ? 'Switch to dark theme' : '切换为深色主题');
            btn.title = lbl;
            btn.setAttribute('aria-label', lbl);
            btn.setAttribute('aria-pressed', String(dark));
        }}

        function toggleTheme() {{
            const next = isDarkTheme() ? 'light' : 'dark';
            if (document.documentElement && document.documentElement.setAttribute) {{
                document.documentElement.setAttribute('data-theme', next);
            }}
            syncThemeButton();
        }}

        // Language switching
        function switchLanguage(lang) {{
            currentLang = lang;
            document.documentElement.setAttribute('lang', lang === 'zh' ? 'zh-CN' : 'en');
            document.documentElement.setAttribute('data-lang', lang === 'zh' ? 'zh' : 'en');

            // Update button states
            document.querySelectorAll('.language-btn').forEach(btn => {{
                const isActive = btn.getAttribute('data-lang') === lang;
                btn.classList.toggle('active', isActive);
                btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
            }});

            // Show/hide elements
            if (lang === 'en') {{
                document.querySelectorAll('.lang-en').forEach(el => el.style.display = '');
                document.querySelectorAll('.lang-zh').forEach(el => el.style.display = 'none');
            }} else {{
                document.querySelectorAll('.lang-en').forEach(el => el.style.display = 'none');
                document.querySelectorAll('.lang-zh').forEach(el => el.style.display = '');
            }}

            // Update data-i18n nodes in dynamic rows
            document.querySelectorAll('[data-i18n-en]').forEach(el => {{
                const val = el.getAttribute('data-i18n-' + lang);
                if (val !== null) {{
                    el.textContent = val;
                }}
            }});

            // Update chromosome selector default option
            const chromSelect = document.getElementById('chromSelect');
            if (chromSelect) {{
                const allOpt = chromSelect.querySelector('option[value="all"]');
                if (allOpt) {{
                    allOpt.textContent = lang === 'zh' ? '所有染色体' : 'All Chromosomes';
                }}
            }}

            syncThemeButton();

            // Refresh overview panels & open modal so SVG text matches active language
            if (typeof drawChromVisualization === 'function' && document.getElementById('chromVisualization')) {{
                const sel = document.getElementById('chromSelect');
                drawChromVisualization(sel ? sel.value : 'all');
            }}
            if (typeof renderOverviewCharts === 'function') {{
                renderOverviewCharts();
            }}
            const rtDlg = document.getElementById('degapRuntimeDialog');
            if (rtDlg && rtDlg.hasAttribute && rtDlg.hasAttribute('open') && typeof renderRuntimeModalContent === 'function') {{
                renderRuntimeModalContent();
            }}
        }}

        // Expand/Collapse table
        function toggleTableExpand(which) {{
            const containerMap = {{
                'initial': 'initial-table-container',
                'tasks': 'tasks-table-container',
                'final': 'final-table-container'
            }};

            const container = document.getElementById(containerMap[which]);
            const btn = document.getElementById(which + '-toggle-btn');
            const expanded = container.classList.toggle('expanded');

            btn.innerHTML = expanded
                ? '<span class="lang-en">Collapse</span><span class="lang-zh">收起</span>'
                : '<span class="lang-en">Expand</span><span class="lang-zh">展开</span>';
        }}

        // Numeric & coordinate projection helpers (pure functions)
        function toFiniteNumber(value) {{
            if (typeof value === 'number' && Number.isFinite(value)) {{
                return value;
            }}
            if (typeof value === 'string' && value.trim() !== '') {{
                const parsed = Number(value);
                if (Number.isFinite(parsed)) {{
                    return parsed;
                }}
            }}
            return null;
        }}

        function bilingualSpan(enHtml, zhHtml) {{
            return `<span class="lang-en">${{enHtml}}</span><span class="lang-zh">${{zhHtml}}</span>`;
        }}

        // Format number with commas
        function formatNumber(num) {{
            const parsed = toFiniteNumber(num);
            if (parsed === null) {{
                return '-';
            }}
            return String(parsed).replace(/\\B(?=(\\d{{3}})+(?!\\d))/g, ",");
        }}

        // Format BP (including Gb for large read sets)
        function formatBP(bp) {{
            const num = toFiniteNumber(bp);
            if (num === null) {{
                return '-';
            }}
            if (Math.abs(num) >= 1000000000) {{
                return (num / 1000000000).toFixed(2) + ' Gb';
            }} else if (Math.abs(num) >= 1000000) {{
                return (num / 1000000).toFixed(2) + ' Mb';
            }} else if (Math.abs(num) >= 1000) {{
                return (num / 1000).toFixed(2) + ' Kb';
            }} else {{
                return num + ' bp';
            }}
        }}

        function formatSignedBP(bp) {{
            const num = toFiniteNumber(bp);
            if (num === null) {{
                return '-';
            }}
            const formatted = formatBP(num);
            return num > 0 ? '+' + formatted : formatted;
        }}

        // Original 1-based inclusive gap span: finite gap.gap_len or (gap_end - gap_start + 1)
        function getOriginalGapLength(gap) {{
            const explicitLen = toFiniteNumber(gap && gap.gap_len);
            if (explicitLen !== null && explicitLen >= 0) {{
                return explicitLen;
            }}
            const start = toFiniteNumber(gap && gap.gap_start);
            const end = toFiniteNumber(gap && gap.gap_end);
            if (start !== null && end !== null && end >= start) {{
                return end - start + 1;
            }}
            return 0;
        }}

        // Bounded terminal flank delta (missing legacy junction means 0)
        function getFlankLengthDelta(gap) {{
            const delta = toFiniteNumber(gap && gap.junction && gap.junction.flank_length_delta);
            return delta !== null ? delta : 0;
        }}

        // Filled sequence length (0 and negative overlap are valid numbers, never falsy-skipped)
        function getFilledSequenceLength(gap) {{
            const direct = toFiniteNumber(gap && gap.fill_length);
            if (direct !== null) {{
                return direct;
            }}
            const junctionGapLen = toFiniteNumber(gap && gap.junction && gap.junction.gap_length);
            if (junctionGapLen !== null) {{
                return junctionGapLen;
            }}
            return null;
        }}

        // Downstream coordinate offset added by a filled gap
        function getFilledGapOffsetDelta(gap) {{
            if (!gap || !gap.filled) {{
                return 0;
            }}
            const originalGapLen = getOriginalGapLength(gap);
            const fillLength = getFilledSequenceLength(gap);
            const numericFillLen = fillLength !== null ? fillLength : 0;
            const flankDelta = getFlankLengthDelta(gap);
            return numericFillLen - originalGapLen + flankDelta;
        }}

        function compareGapIds(aId, bId) {{
            const aNum = toFiniteNumber(aId);
            const bNum = toFiniteNumber(bId);
            if (aNum !== null && bNum !== null && aNum !== bNum) {{
                return aNum - bNum;
            }}
            const aStr = String(aId ?? '');
            const bStr = String(bId ?? '');
            if (aStr < bStr) return -1;
            if (aStr > bStr) return 1;
            return 0;
        }}

        // Sort gaps by numeric genomic start, then end, then stable gap_id
        function compareGapsGenomic(a, b) {{
            const aStart = toFiniteNumber(a && a.gap_start);
            const bStart = toFiniteNumber(b && b.gap_start);
            if (aStart !== null && bStart !== null && aStart !== bStart) {{
                return aStart - bStart;
            }}
            if (aStart !== null && bStart === null) return -1;
            if (aStart === null && bStart !== null) return 1;
            const aEnd = toFiniteNumber(a && a.gap_end);
            const bEnd = toFiniteNumber(b && b.gap_end);
            if (aEnd !== null && bEnd !== null && aEnd !== bEnd) {{
                return aEnd - bEnd;
            }}
            return compareGapIds(a && a.gap_id, b && b.gap_id);
        }}

        // Project remaining unfilled gaps into final integrated coordinates
        function projectFinalUnfilledGaps(gaps) {{
            const sortedGaps = Array.isArray(gaps) ? [...gaps].sort(compareGapsGenomic) : [];
            let positionOffset = 0;
            const projected = [];
            sortedGaps.forEach(gap => {{
                if (!gap.filled) {{
                    const start = toFiniteNumber(gap.gap_start);
                    const end = toFiniteNumber(gap.gap_end);
                    const safeStart = start !== null ? start : 0;
                    const safeEnd = end !== null ? end : safeStart;
                    projected.push({{
                        gap,
                        originalStart: safeStart,
                        originalEnd: safeEnd,
                        originalLength: getOriginalGapLength(gap),
                        finalStart: safeStart + positionOffset,
                        finalEnd: safeEnd + positionOffset,
                        offset: positionOffset
                    }});
                }} else {{
                    positionOffset += getFilledGapOffsetDelta(gap);
                }}
            }});
            return projected;
        }}

        // Original assembly 0-based track placement (never uses final fill length as axis width)
        function getOriginalTrackPlacement(gap, rowStart = 0, rowEnd = null) {{
            const rawStart = toFiniteNumber(gap && gap.gap_start);
            const start0 = rawStart !== null ? Math.max(0, rawStart - 1) : 0;
            const span = getOriginalGapLength(gap);
            const end0 = start0 + span;
            if (rowEnd !== null) {{
                if (start0 < rowStart || start0 >= rowEnd) {{
                    return null;
                }}
                return {{
                    start0,
                    end0,
                    relativeStart: start0 - rowStart,
                    span,
                    clippedSpan: Math.min(span, Math.max(0, rowEnd - start0))
                }};
            }}
            return {{
                start0,
                end0,
                relativeStart: start0,
                span,
                clippedSpan: span
            }};
        }}

        function formatFillLengthCell(gap) {{
            if (!gap || !gap.filled) {{
                return {{ html: '-', className: 'num muted' }};
            }}
            const fillLen = getFilledSequenceLength(gap);
            const rawFlankDelta = toFiniteNumber(gap && gap.junction && gap.junction.flank_length_delta);
            const flankNote = (rawFlankDelta !== null && rawFlankDelta !== 0)
                ? `<span class="cell-subnote">${{bilingualSpan(
                    `Flank delta: ${{escapeHtml(formatSignedBP(rawFlankDelta))}}`,
                    `末端修订变化：${{escapeHtml(formatSignedBP(rawFlankDelta))}}`
                )}}</span>`
                : '';

            if (fillLen === null) {{
                return {{ html: '-' + flankNote, className: 'num muted' }};
            }}
            if (fillLen < 0) {{
                const trimText = escapeHtml(formatBP(Math.abs(fillLen)));
                const trimNote = `<span class="cell-subnote">${{bilingualSpan(
                    `Original-overlap trim (${{trimText}})`,
                    `原始重叠去重裁剪（${{trimText}}）`
                )}}</span>`;
                return {{
                    html: `${{escapeHtml(formatBP(fillLen))}}${{trimNote}}${{flankNote}}`,
                    className: 'num'
                }};
            }}
            return {{
                html: `${{escapeHtml(formatBP(fillLen))}}${{flankNote}}`,
                className: 'num success'
            }};
        }}

        function buildTooltipContent(gap, chrom) {{
            const originalSpan = getOriginalGapLength(gap);
            const fillLen = getFilledSequenceLength(gap);
            const rawFlankDelta = toFiniteNumber(gap && gap.junction && gap.junction.flank_length_delta);
            const posRange = `${{escapeHtml(formatNumber(gap && gap.gap_start))}} - ${{escapeHtml(formatNumber(gap && gap.gap_end))}}`;

            let content = `
                <strong>${{escapeHtml(chrom)}}.gap${{escapeHtml(gap && gap.gap_id)}}</strong><br>
                ${{bilingualSpan(
                    `Status: ${{gap && gap.filled ? 'Filled' : 'Unfilled'}}`,
                    `状态：${{gap && gap.filled ? '已填充' : '未填充'}}`
                )}}<br>
                ${{bilingualSpan(
                    `Original Position (1-based): ${{posRange}}`,
                    `原始坐标 (1-based)：${{posRange}}`
                )}}<br>
                ${{bilingualSpan(
                    `Original Gap Span: ${{escapeHtml(formatBP(originalSpan))}}`,
                    `原始 Gap 跨度：${{escapeHtml(formatBP(originalSpan))}}`
                )}}<br>
            `;

            if (gap && gap.filled) {{
                if (fillLen === null) {{
                    content += `${{bilingualSpan('Filled Sequence Length: -', '填补序列长度：-')}}<br>`;
                }} else if (fillLen < 0) {{
                    const trimAbs = escapeHtml(formatBP(Math.abs(fillLen)));
                    content += `${{bilingualSpan(
                        `Original-Overlap Trimming: ${{escapeHtml(formatBP(fillLen))}} (${{trimAbs}} trimmed)`,
                        `原始重叠去重裁剪：${{escapeHtml(formatBP(fillLen))}}（裁剪 ${{trimAbs}}）`
                    )}}<br>`;
                }} else {{
                    content += `${{bilingualSpan(
                        `Filled Sequence Length: ${{escapeHtml(formatBP(fillLen))}}`,
                        `填补序列长度：${{escapeHtml(formatBP(fillLen))}}`
                    )}}<br>`;
                }}

                if (rawFlankDelta !== null) {{
                    content += `${{bilingualSpan(
                        `Flank Length Delta: ${{escapeHtml(formatSignedBP(rawFlankDelta))}}`,
                        `末端修订净变化：${{escapeHtml(formatSignedBP(rawFlankDelta))}}`
                    )}}<br>`;
                }}

                if (gap.fill_type) {{
                    const typeZh = gap.fill_type === 'extension' ? '延伸闭合' : (gap.fill_type === 'direct_connection' ? '直接连接' : gap.fill_type);
                    content += bilingualSpan(
                        `Type: ${{escapeHtml(gap.fill_type)}}`,
                        `类型：${{escapeHtml(typeZh)}}`
                    ) + '<br>';
                }}
            }} else {{
                content += bilingualSpan('Filled Sequence Length: -', '填补序列长度：-') + '<br>';
            }}

            content += `<span style="color:#93c5fd;">${{bilingualSpan('Click to open detail ↗', '点击打开详情报告 ↗')}}</span>`;
            return content;
        }}

        // Populate 01 Input Data Card (genome + reads table + aux parameter tags)
        function populateReadsInfo() {{
            const card = document.getElementById('degap-inputs');
            const tbody = document.getElementById('inputDataTableBody');
            const bar = document.getElementById('readsInfoBar');
            if (!card || !tbody) return;

            const rows = [];
            const aux = [];
            const chromNames = Object.keys(gapsByChrom);
            let totalGapCount = 0;
            let totalGapSpan = 0;
            let hasBidirectional = false;
            chromNames.forEach(c => {{
                (gapsByChrom[c].gaps || []).forEach(g => {{
                    totalGapCount += 1;
                    totalGapSpan += getOriginalGapLength(g);
                    if (g.report_direction === 'bidirectional' || g.fill_direction === 'bidirectional') {{
                        hasBidirectional = true;
                    }}
                }});
            }});

            const intStats = (integrationConfig && integrationConfig.stats) || {{}};
            const origGenomePath = integrationConfig && integrationConfig.original_genome ? String(integrationConfig.original_genome) : '';
            const origGenomeName = origGenomePath ? origGenomePath.split(/[\\\\/]/).pop() : '';
            const totalChrs = toFiniteNumber(intStats.total_chromosomes);

            if (origGenomeName || totalGapCount > 0 || totalChrs !== null) {{
                const displayName = origGenomeName
                    ? `<span class="dataset-name">${{escapeHtml(origGenomeName)}}</span>`
                    : `<span class="dataset-name">${{bilingualSpan('Target Assembly', '待填补组装')}}</span>`;
                const chrScaleEn = totalChrs !== null
                    ? `${{formatNumber(totalChrs)}} chr (${{formatNumber(chromNames.length)}} with gaps)`
                    : `${{formatNumber(chromNames.length)}} chr with gaps`;
                const chrScaleZh = totalChrs !== null
                    ? `${{formatNumber(totalChrs)}} 条染色体（${{formatNumber(chromNames.length)}} 条含 Gap）`
                    : `${{formatNumber(chromNames.length)}} 条含 Gap 染色体`;
                const spanNote = totalGapSpan > 0
                    ? bilingualSpan(`${{formatNumber(totalGapCount)}} gaps · span ${{formatBP(totalGapSpan)}}`, `原始 Gap ${{formatNumber(totalGapCount)}} 个 · 总跨度 ${{formatBP(totalGapSpan)}}`)
                    : bilingualSpan(`${{formatNumber(totalGapCount)}} gaps`, `原始 Gap ${{formatNumber(totalGapCount)}} 个`);
                const intChroms = intStats.chromosomes || {{}};
                const knownLen = Object.values(intChroms).reduce((acc, s) => acc + (toFiniteNumber(s && s.original_length) || 0), 0);
                const lenCell = knownLen > 0
                    ? bilingualSpan(`Gap-chr total ${{formatBP(knownLen)}}`, `已填补染色体总长 ${{formatBP(knownLen)}}`)
                    : '<span class="muted">—</span>';
                rows.push(`
                    <tr>
                        <td>${{displayName}}</td>
                        <td><span class="dataset-role">${{bilingualSpan('Target Assembly', '待填补组装')}}</span></td>
                        <td class="num">${{bilingualSpan(chrScaleEn, chrScaleZh)}}</td>
                        <td class="num">${{lenCell}}</td>
                        <td class="num">${{spanNote}}</td>
                    </tr>
                `);
            }}

            const hasPre = preprocessingConfig && Object.keys(preprocessingConfig).length > 0;
            let resolvedSeed = toFiniteNumber(preprocessingConfig && preprocessingConfig.seed_length) || 0;
            if (hasPre) {{
                const hifiStats = preprocessingConfig.hifi_stats || {{}};
                const ontStats = preprocessingConfig.ont_stats || {{}};
                const addReadRow = (label, statsObj) => {{
                    if (!statsObj || Object.keys(statsObj).length === 0) return;
                    const cnt = toFiniteNumber(statsObj.Number ?? statsObj.NumSeqs);
                    const totalLen = toFiniteNumber(statsObj.TotalLength ?? statsObj.TolalLenth);
                    const meanLen = toFiniteNumber(statsObj.MeanLength);
                    const maxLen = toFiniteNumber(statsObj.MaxLength);
                    const seedL = toFiniteNumber(statsObj.SeedLength);
                    if (!resolvedSeed && seedL) resolvedSeed = seedL;
                    const lenPartsEn = [], lenPartsZh = [];
                    if (totalLen !== null) {{
                        lenPartsEn.push(`Total ${{formatBP(totalLen)}}`);
                        lenPartsZh.push(`总长 ${{formatBP(totalLen)}}`);
                    }}
                    if (meanLen !== null) {{
                        lenPartsEn.push(`Mean ${{formatBP(meanLen)}}`);
                        lenPartsZh.push(`均值 ${{formatBP(meanLen)}}`);
                    }}
                    if (maxLen !== null) {{
                        lenPartsEn.push(`Max ${{formatBP(maxLen)}}`);
                        lenPartsZh.push(`最长 ${{formatBP(maxLen)}}`);
                    }}
                    rows.push(`
                        <tr>
                            <td><span class="dataset-name">${{escapeHtml(label)}}</span></td>
                            <td><span class="dataset-role is-reads">${{bilingualSpan('Sequencing Reads', '测序读长')}}</span></td>
                            <td class="num">${{cnt !== null ? bilingualSpan(`${{formatNumber(cnt)}} reads`, `${{formatNumber(cnt)}} 条`) : '-'}}</td>
                            <td class="num">${{lenPartsEn.length ? bilingualSpan(lenPartsEn.join(' · '), lenPartsZh.join(' · ')) : '-'}}</td>
                            <td class="num muted">${{seedL ? bilingualSpan(`Seed ${{formatBP(seedL)}}`, `种子 ${{formatBP(seedL)}}`) : '—'}}</td>
                        </tr>
                    `);
                }};
                addReadRow('HiFi', hifiStats);
                addReadRow('ONT', ontStats);

                if (rows.length <= 1) {{
                    const dataType = preprocessingConfig.data_type ? String(preprocessingConfig.data_type) : '';
                    if (dataType) {{
                        const dt = dataType.toLowerCase() === 'hifi' ? 'HiFi' : (dataType.toLowerCase() === 'ont' ? 'ONT' : dataType.toUpperCase());
                        aux.push(`<span class="input-aux-tag">${{bilingualSpan('Reads Type', '数据类型')}} <b>${{escapeHtml(dt)}}</b></span>`);
                    }}
                    if (resolvedSeed > 0) {{
                        aux.push(`<span class="input-aux-tag">${{bilingualSpan('Seed Length', '种子长度')}} <b>${{escapeHtml(formatBP(resolvedSeed))}}</b></span>`);
                    }}
                }}
            }}
            if (hasBidirectional) {{
                aux.push(`<span class="input-aux-tag">${{bilingualSpan('Extension Mode', '延伸模式')}} <b>${{bilingualSpan('Bidirectional', '双向延伸')}}</b></span>`);
            }}

            if (rows.length === 0) {{
                card.style.display = 'none';
                return;
            }}
            tbody.innerHTML = rows.join('');
            card.style.display = '';
            if (bar) {{
                bar.innerHTML = aux.join('');
                bar.style.display = aux.length ? 'flex' : 'none';
            }}
        }}

        // Populate Initial Genome Table
        function populateInitialGenomeTable() {{
            const tbody = document.getElementById('initialGenomeTableBody');

            let html = '';
            let rowCount = 0;

            // Sort chromosomes
            const chromNames = Object.keys(gapsByChrom).sort();

            chromNames.forEach(chrom => {{
                const chromData = gapsByChrom[chrom];

                // Sort gaps by numeric genomic start then stable gap_id
                const sortedGaps = [...chromData.gaps].sort(compareGapsGenomic);

                sortedGaps.forEach(gap => {{
                    const region = `${{formatNumber(gap.gap_start)}} - ${{formatNumber(gap.gap_end)}}`;

                    html += `
                        <tr>
                            <td class="mono">${{escapeHtml(chrom)}}</td>
                            <td class="num">${{escapeHtml(gap.gap_id)}}</td>
                            <td class="num">${{escapeHtml(region)}}</td>
                        </tr>
                    `;
                    rowCount++;
                }});
            }});

            if (rowCount === 0) {{
                html = '<tr><td colspan="3" class="empty-state"><span class="lang-en">No initial gaps recorded</span><span class="lang-zh">暂无初始 Gap 记录</span></td></tr>';
            }}

            tbody.innerHTML = html;

            const container = document.getElementById('initial-table-container');
            const toggleContainer = document.querySelector('#initial-table-container .table-toggle-container');
            if (rowCount > 20) {{
                toggleContainer.style.display = 'flex';
            }} else {{
                container.classList.add('expanded');
                toggleContainer.style.display = 'none';
            }}
        }}

        function formatBoundaryBadge(chrom, gap) {{
            const note = gapBoundaryNotes && gapBoundaryNotes[`${{chrom}}:${{gap.gap_id}}`];
            if (!note) return '<span class="muted">—</span>';
            const pills = [];
            if (note.flanks) {{
                const lSt = note.flanks.L, rSt = note.flanks.R;
                const conflicts = [];
                const repaired = [];
                if (lSt === 'conflict') conflicts.push('L');
                if (rSt === 'conflict') conflicts.push('R');
                if (lSt === 'repaired') repaired.push('L');
                if (rSt === 'repaired') repaired.push('R');
                const arpTip = Array.isArray(note.arp) ? ` · A/R/P ${{note.arp.join('/')}}` : '';
                if (conflicts.length > 0) {{
                    const sideLbl = conflicts.join('/');
                    pills.push(`<span class="rt-badge tone-warn" title="Original flank retained${{escapeHtml(arpTip)}}">${{bilingualSpan(`${{sideLbl}} conflict`, `${{sideLbl}} 冲突保留`)}}</span>`);
                }} else if (repaired.length > 0) {{
                    const sideLbl = repaired.join('/');
                    pills.push(`<span class="rt-badge tone-info" title="Flank repaired${{escapeHtml(arpTip)}}">${{bilingualSpan(`${{sideLbl}} repaired`, `${{sideLbl}} 已修订`)}}</span>`);
                }} else if (lSt === 'preserved' || rSt === 'preserved') {{
                    pills.push(`<span class="rt-badge tone-ok" title="Flanks preserved${{escapeHtml(arpTip)}}">${{bilingualSpan('Preserved', '末端保持')}}</span>`);
                }}
            }}
            if (note.backoff && note.backoff > 0) {{
                pills.push(`<span class="rt-badge tone-warn">${{bilingualSpan(`Backoff ${{note.backoff}}×`, `回退 ${{note.backoff}} 次`)}}</span>`);
            }}
            return pills.length ? pills.join(' ') : '<span class="muted">—</span>';
        }}

        // Populate Gap Filling Tasks Table (includes projected final coords & boundary/backoff summary)
        function populateGapFillingTasksTable() {{
            const tbody = document.getElementById('gapFillingTasksTableBody');
            const table = document.getElementById('gapFillingTasksTable');

            let html = '';
            let rowCount = 0;
            const seenDirs = new Set();

            // Sort chromosomes
            const chromNames = Object.keys(gapsByChrom).sort();

            chromNames.forEach(chrom => {{
                const chromData = gapsByChrom[chrom];

                // Pre-compute projected final coordinates for unfilled gaps on this chromosome
                const projByGapId = {{}};
                projectFinalUnfilledGaps(chromData.gaps).forEach(item => {{
                    projByGapId[String(item.gap.gap_id)] = item;
                }});

                // Sort gaps by numeric genomic start then stable gap_id
                const sortedGaps = [...chromData.gaps].sort(compareGapsGenomic);

                sortedGaps.forEach(gap => {{
                    const region = `${{formatNumber(gap.gap_start)}} - ${{formatNumber(gap.gap_end)}}`;
                    const origSpan = getOriginalGapLength(gap);
                    let regionSub = origSpan > 0 ? `<span class="cell-subnote">${{escapeHtml(formatBP(origSpan))}}</span>` : '';
                    if (!gap.filled) {{
                        const proj = projByGapId[String(gap.gap_id)];
                        if (proj && proj.offset !== 0) {{
                            const finalRange = `${{formatNumber(proj.finalStart)}} - ${{formatNumber(proj.finalEnd)}}`;
                            regionSub += `<span class="cell-subnote">${{bilingualSpan(
                                `Final: ${{escapeHtml(finalRange)}} (${{escapeHtml(formatSignedBP(proj.offset))}})`,
                                `终版：${{escapeHtml(finalRange)}}（${{escapeHtml(formatSignedBP(proj.offset))}}）`
                            )}}</span>`;
                        }}
                    }}

                    // Merged status + connection type badge (CGAT .rt-badge tones)
                    let statusBadge;
                    if (gap.filled) {{
                        if (gap.fill_type === 'direct_connection') {{
                            statusBadge = '<span class="rt-badge tone-ok" data-i18n-en="Filled · Direct" data-i18n-zh="已填补 · 直连">已填补 · 直连</span>';
                        }} else if (gap.fill_type === 'extension') {{
                            statusBadge = '<span class="rt-badge tone-ok" data-i18n-en="Filled · Ext" data-i18n-zh="已填补 · 延伸">已填补 · 延伸</span>';
                        }} else {{
                            statusBadge = '<span class="rt-badge tone-ok" data-i18n-en="Filled" data-i18n-zh="已填补">已填补</span>';
                        }}
                    }} else {{
                        statusBadge = '<span class="rt-badge tone-err" data-i18n-en="Unfilled" data-i18n-zh="未填补">未填补</span>';
                    }}

                    // Direction column (auto-hidden when uniform across all gaps)
                    const displayFlag = gap.report_direction || gap.fill_direction || 'none';
                    seenDirs.add(displayFlag);

                    const lrTxt = typeof formatLRBadge === 'function' ? formatLRBadge(chrom, gap) : '';
                    const rounds = lrTxt || (gap.rounds !== undefined && gap.rounds !== null ? String(gap.rounds) : '-');

                    // Fill length - distinguish 0 bp, negative overlap trimming, and flank delta
                    const fillCell = formatFillLengthCell(gap);
                    const boundaryCell = formatBoundaryBadge(chrom, gap);

                    // Details - View link to sub-task report
                    const linkFlag = gap.report_direction || (gap.filled && gap.fill_direction ? gap.fill_direction : 'left');
                    const reportFile = `${{chrom}}.${{gap.gap_id}}.${{linkFlag}}.html`;
                    const details = `<a class="table-link" href="${{escapeHtml(reportFile)}}" target="_blank" rel="noopener" title="View details for ${{escapeHtml(chrom)}} Gap ${{escapeHtml(gap.gap_id)}}" data-i18n-en="View ↗" data-i18n-zh="查看 ↗">查看 ↗</a>`;

                    html += `
                        <tr data-filled="${{gap.filled ? 'filled' : 'unfilled'}}">
                            <td class="mono">${{escapeHtml(chrom)}}</td>
                            <td class="num">${{escapeHtml(gap.gap_id)}}</td>
                            <td class="num muted">${{escapeHtml(region)}}${{regionSub}}</td>
                            <td>${{statusBadge}}</td>
                            <td data-col="dir" class="mono">${{escapeHtml(displayFlag)}}</td>
                            <td class="num mono">${{escapeHtml(rounds)}}</td>
                            <td class="${{fillCell.className}}">${{fillCell.html}}</td>
                            <td>${{boundaryCell}}</td>
                            <td>${{details}}</td>
                        </tr>
                    `;
                    rowCount++;
                }});
            }});

            if (table) {{
                table.classList.toggle('hide-uniform-dir', rowCount > 0 && seenDirs.size <= 1);
            }}

            if (rowCount === 0) {{
                html = '<tr><td colspan="9" class="empty-state"><span class="lang-en">No gap filling tasks recorded</span><span class="lang-zh">暂无 Gap 填充任务记录</span></td></tr>';
            }}

            tbody.innerHTML = html;

            const container = document.getElementById('tasks-table-container');
            const toggleContainer = document.querySelector('#tasks-table-container .table-toggle-container');
            if (rowCount > 20) {{
                toggleContainer.style.display = 'flex';
            }} else {{
                container.classList.add('expanded');
                toggleContainer.style.display = 'none';
            }}
        }}

        // Populate Final Integrated Genome Table
        function populateFinalGenomeTable() {{
            const tbody = document.getElementById('finalGenomeTableBody');

            let html = '';
            let rowCount = 0;

            // Sort chromosomes
            const chromNames = Object.keys(gapsByChrom).sort();

            chromNames.forEach(chrom => {{
                const chromData = gapsByChrom[chrom];
                const projected = projectFinalUnfilledGaps(chromData.gaps);

                projected.forEach(item => {{
                    const region = `${{formatNumber(item.finalStart)}} - ${{formatNumber(item.finalEnd)}}`;
                    const g = item.gap;
                    const linkFlag = g.report_direction || (g.filled && g.fill_direction ? g.fill_direction : 'left');
                    const reportFile = `${{chrom}}.${{g.gap_id}}.${{linkFlag}}.html`;
                    const details = `<a class="table-link" href="${{escapeHtml(reportFile)}}" target="_blank" rel="noopener" data-i18n-en="View ↗" data-i18n-zh="查看 ↗">查看 ↗</a>`;

                    html += `
                        <tr>
                            <td class="mono">${{escapeHtml(chrom)}}</td>
                            <td class="num">${{escapeHtml(g.gap_id)}}</td>
                            <td class="num">${{escapeHtml(region)}}</td>
                            <td>${{details}}</td>
                        </tr>
                    `;
                    rowCount++;
                }});
            }});

            // If no unfilled gaps, show a message
            if (html === '') {{
                html = '<tr><td colspan="4" class="empty-state success"><span data-i18n-en="All gaps have been filled." data-i18n-zh="所有 Gap 已填补。">所有 Gap 已填补。</span></td></tr>';
            }}

            tbody.innerHTML = html;
            const remBadge = document.getElementById('remainingCount');
            if (remBadge) {{
                remBadge.textContent = `(${{rowCount}})`;
            }}

            const container = document.getElementById('final-table-container');
            const toggleContainer = document.querySelector('#final-table-container .table-toggle-container');
            if (rowCount > 20) {{
                toggleContainer.style.display = 'flex';
            }} else {{
                container.classList.add('expanded');
                toggleContainer.style.display = 'none';
            }}
        }}

        // Populate Chromosome Selector
        function populateChromSelector() {{
            const select = document.getElementById('chromSelect');
            let selectHtml = `<option value="all">${{currentLang === 'zh' ? '所有染色体' : 'All Chromosomes'}}</option>`;

            // Sort chromosomes
            const chromNames = Object.keys(gapsByChrom).sort();

            chromNames.forEach(chrom => {{
                selectHtml += `<option value="${{escapeHtml(chrom)}}">${{escapeHtml(chrom)}}</option>`;
            }});

            select.innerHTML = selectHtml;
        }}

        // Current track length & chromosome for multi-row view
        let currentTrackLength = 0;
        let currentSingleChrom = null;

        // Compute a smooth linear slider configuration (min, max, step) adapted to chromosome length
        function getLinearTrackSliderConfig(chromLength) {{
            const L = Math.max(1000, Math.floor(toFiniteNumber(chromLength) || 1000));
            const rawMin = Math.max(10000, Math.floor(L / 12));
            const minVal = Math.min(L, rawMin);
            const span = Math.max(0, L - minVal);
            // ~100 crisp linear increments rounded to a clean 1/2/5×10^k unit
            let step = 1000;
            if (span > 0) {{
                const rawStep = span / 100;
                const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
                const norm = rawStep / mag;
                step = Math.max(1000, Math.round((norm <= 1.5 ? 1 : (norm <= 3.5 ? 2 : (norm <= 7.5 ? 5 : 10))) * mag));
                if (step > span) step = Math.max(1, Math.floor(span / 4) || 1);
            }}
            const alignedMin = Math.min(L, Math.max(step, Math.floor(minVal / step) * step));
            // Align max UP to the step grid so dragging slider to the right end always reaches full length (1 single row)
            const alignedMax = span > 0 ? (alignedMin + Math.ceil((L - alignedMin) / step) * step) : L;
            return {{ min: alignedMin, max: Math.max(L, alignedMax), step, chromLength: L }};
        }}

        function syncRowPresetButtons(chromLength, trackLength) {{
            const numRows = trackLength > 0 ? Math.ceil(chromLength / trackLength) : 1;
            document.querySelectorAll('[data-row-preset]').forEach(btn => {{
                const targetRows = parseInt(btn.getAttribute('data-row-preset'), 10);
                const isAct = targetRows === numRows;
                btn.classList.toggle('is-active', isAct);
                btn.setAttribute('aria-pressed', isAct ? 'true' : 'false');
            }});
        }}

        function setTrackRowPreset(targetRows) {{
            const sel = document.getElementById('chromSelect');
            const chrom = sel ? sel.value : null;
            if (!chrom || chrom === 'all' || !gapsByChrom[chrom]) return;
            const L = gapsByChrom[chrom].length || 1;
            const slider = document.getElementById('trackLengthSlider');
            const len = targetRows <= 1 ? L : Math.max(1, Math.ceil(L / targetRows));
            currentTrackLength = Math.min(L, len);
            if (slider) {{
                slider.value = targetRows <= 1 ? String(slider.max || L) : String(currentTrackLength);
            }}
            updateTrackLengthDisplay(currentTrackLength, L);
            drawChromVisualization(chrom);
        }}

        // Draw Chromosome Visualization (CGAT-aligned overview track frame in both 'all' and single-chr multi-row modes)
        function drawChromVisualization(selectedChrom = 'all') {{
            const container = document.getElementById('chromVisualization');
            if (!container) return;
            container.innerHTML = '';

            const chromNames = selectedChrom === 'all'
                ? Object.keys(gapsByChrom).sort()
                : [selectedChrom];

            const trackFrame = document.getElementById('ovTrackFrame');
            const zoomBtn = document.getElementById('ovTrackZoomBtn');

            if (chromNames.length === 0) {{
                if (trackFrame) trackFrame.classList.add('is-single');
                if (zoomBtn) zoomBtn.style.display = 'none';
                container.innerHTML = '<div class="empty-state" style="padding:18px;"><span class="lang-en">No chromosomes to display</span><span class="lang-zh">暂无可显示的染色体</span></div>';
                return;
            }}

            // Show/hide track length control
            const trackLengthControl = document.getElementById('trackLengthControl');
            const isSingle = selectedChrom !== 'all' && !!gapsByChrom[selectedChrom];
            if (isSingle) {{
                if (trackLengthControl) trackLengthControl.style.display = 'block';
                if (trackFrame) trackFrame.classList.add('is-single');
                if (zoomBtn) zoomBtn.style.display = 'none';
                const chromData = gapsByChrom[selectedChrom];
                const chromLength = chromData.length || 1;
                const switchedChrom = currentSingleChrom !== selectedChrom;
                currentSingleChrom = selectedChrom;

                // Update inline chromosome summary badge
                const sumEl = document.getElementById('trackChrSummary');
                if (sumEl) {{
                    const fCnt = chromData.filled || 0;
                    const tCnt = chromData.total || 0;
                    const rCnt = Math.max(0, tCnt - fCnt);
                    const tone = rCnt === 0 ? 'tone-ok' : (fCnt > 0 ? 'tone-info' : 'tone-err');
                    const statusTxt = currentLang === 'zh'
                        ? `${{fCnt}}/${{tCnt}} 已填补 · 剩 ${{rCnt}}G`
                        : `${{fCnt}}/${{tCnt}} filled · ${{rCnt}}G left`;
                    sumEl.innerHTML = `<b>${{escapeHtml(selectedChrom)}}</b><span>${{escapeHtml(formatBP(chromLength))}}</span><span class="rt-badge ${{tone}}">${{escapeHtml(statusTxt)}}</span>`;
                }}

                const cfg = getLinearTrackSliderConfig(chromLength);
                const slider = document.getElementById('trackLengthSlider');
                if (slider) {{
                    slider.min = String(cfg.min);
                    slider.max = String(cfg.max);
                    slider.step = String(cfg.step);
                    if (switchedChrom || currentTrackLength < cfg.min || currentTrackLength > chromLength) {{
                        // Default to a clean 4-row layout aligned to linear slider step
                        const ideal = Math.ceil(chromLength / 4);
                        const snapped = Math.min(chromLength, Math.max(cfg.min, Math.round(ideal / cfg.step) * cfg.step));
                        currentTrackLength = snapped || chromLength;
                    }}
                    slider.value = currentTrackLength >= chromLength ? String(cfg.max) : String(currentTrackLength);
                    updateTrackLengthDisplay(currentTrackLength, chromLength);
                }} else if (switchedChrom || currentTrackLength <= 0 || currentTrackLength > chromLength) {{
                    currentTrackLength = Math.max(1, Math.ceil(chromLength / 4));
                }}
            }} else {{
                if (trackLengthControl) trackLengthControl.style.display = 'none';
                if (trackFrame) trackFrame.classList.remove('is-single');
                if (zoomBtn) zoomBtn.style.display = '';
                currentTrackLength = 0;
                currentSingleChrom = null;
            }}

            let maxChromLength = 0;
            chromNames.forEach(chrom => {{
                const chromData = gapsByChrom[chrom];
                if (!chromData) return;
                if (chromData.length > maxChromLength) maxChromLength = chromData.length;
            }});

            if (isSingle && currentTrackLength > 0) {{
                const chromData = gapsByChrom[selectedChrom];
                drawMultiRowChromosome(selectedChrom, chromData, chromData.length, currentTrackLength, container);
                return;
            }}

            // CGAT-style unified track frame: sticky ruler axis + one proportional rail per chromosome
            const inner = document.createElement('div');
            inner.className = 'ov-track-inner';
            const axisMax = maxChromLength || 1;
            const axisRow = document.createElement('div');
            axisRow.className = 'ov-axis';
            const axisLbl = document.createElement('span');
            axisLbl.textContent = currentLang === 'zh' ? '染色体' : 'Chromosome';
            const ruler = document.createElement('span');
            ruler.className = 'story-ruler';
            [0, 0.25, 0.5, 0.75, 1].forEach(frac => {{
                const sp = document.createElement('span');
                sp.textContent = frac === 0 ? '0 bp' : formatBP(Math.round(axisMax * frac));
                ruler.appendChild(sp);
            }});
            axisRow.appendChild(axisLbl);
            axisRow.appendChild(ruler);
            inner.appendChild(axisRow);

            const listDiv = document.createElement('div');
            listDiv.className = 'ov-track-list';
            chromNames.forEach(chrom => {{
                const chromData = gapsByChrom[chrom];
                if (!chromData) return;
                drawSingleRowChromosome(chrom, chromData, chromData.length, axisMax, listDiv);
            }});
            inner.appendChild(listDiv);
            container.appendChild(inner);
        }}

        // Draw single row chromosome in CGAT overview track style
        function drawSingleRowChromosome(chrom, chromData, chromLength, maxChromLength, container) {{
            const row = document.createElement('div');
            row.className = 'ov-chr-row';

            const filledCnt = chromData.filled || 0;
            const totalCnt = chromData.total || 0;
            const remainCnt = Math.max(0, totalCnt - filledCnt);

            const meta = document.createElement('span');
            meta.className = 'ov-chr-meta';

            const nameBtn = document.createElement('button');
            nameBtn.type = 'button';
            nameBtn.className = 'ov-chr-name';
            nameBtn.textContent = chrom;
            nameBtn.title = currentLang === 'zh' ? `${{chrom}}（点击展开多行视图）` : `${{chrom}} (click for multi-row view)`;
            nameBtn.addEventListener('click', () => {{
                const sel = document.getElementById('chromSelect');
                if (sel) {{
                    sel.value = chrom;
                    filterChromosome();
                }}
            }});

            const stats = document.createElement('span');
            stats.className = 'ov-chr-stats';
            const lenEl = document.createElement('small');
            lenEl.className = 'ov-chr-len';
            lenEl.textContent = formatBP(chromLength);
            const gapBadge = document.createElement('small');
            gapBadge.className = 'ov-chr-gap' + (remainCnt === 0 ? ' is-zero' : '');
            gapBadge.textContent = `${{remainCnt}}G`;
            gapBadge.title = currentLang === 'zh'
                ? `已填补 ${{filledCnt}} / ${{totalCnt}}，剩余 ${{remainCnt}} 个 Gap`
                : `${{filledCnt}} / ${{totalCnt}} filled, ${{remainCnt}} remaining`;
            stats.appendChild(lenEl);
            stats.appendChild(gapBadge);

            meta.appendChild(nameBtn);
            meta.appendChild(stats);
            row.appendChild(meta);

            const rail = document.createElement('span');
            rail.className = 'ov-rail';

            const barWidthPct = (chromLength / maxChromLength) * 100;
            const srcSeg = document.createElement('span');
            srcSeg.className = 'ov-seg is-src';
            srcSeg.style.left = '0%';
            srcSeg.style.width = barWidthPct.toFixed(4) + '%';
            rail.appendChild(srcSeg);

            const sortedGaps = [...chromData.gaps].sort(compareGapsGenomic);
            sortedGaps.forEach(gap => {{
                const placement = getOriginalTrackPlacement(gap);
                const linkFlag = gap.report_direction || (gap.filled && gap.fill_direction ? gap.fill_direction : 'left');
                const reportFile = `${{chrom}}.${{gap.gap_id}}.${{linkFlag}}.html`;
                const seg = document.createElement('a');
                seg.className = 'ov-seg ' + (gap.filled ? 'is-patch' : 'is-gap');
                seg.href = reportFile;
                seg.target = '_blank';
                seg.rel = 'noopener';
                const leftPct = Math.min(Math.max(placement.relativeStart, 0), maxChromLength) / maxChromLength * 100;
                const widthPct = Math.max(0, placement.span / maxChromLength * 100);
                seg.style.left = leftPct.toFixed(4) + '%';
                seg.style.width = widthPct.toFixed(4) + '%';
                seg.setAttribute('aria-label', `${{chrom}} Gap ${{gap.gap_id}}: ${{gap.filled ? 'Filled' : 'Unfilled'}}`);
                seg.addEventListener('mouseenter', (e) => showTooltip(e, gap, chrom));
                seg.addEventListener('mouseleave', hideTooltip);
                rail.appendChild(seg);
            }});

            row.appendChild(rail);
            container.appendChild(row);
        }}

        // CGAT-style Zoom & Pan Modal for Chromosome Distribution Track
        function openTrackZoom() {{
            const dlg = document.getElementById('degapZoomDialog');
            const body = document.getElementById('zoomDlgBody');
            const src = document.getElementById('chromVisualization');
            if (!dlg || !body || !src) return;

            const isZh = currentLang === 'zh';
            body.innerHTML = '';
            const bar = document.createElement('div');
            bar.className = 'story-zoom-bar';
            bar.innerHTML = `<div class="legend-row">`
                + `<span class="legend-item"><i class="swatch" style="background:var(--ds-0)"></i>${{isZh ? '染色体序列' : 'Sequence'}}</span>`
                + `<span class="legend-item"><i class="swatch" style="background:var(--gen-closed)"></i>${{isZh ? '已填补 Gap' : 'Filled'}}</span>`
                + `<span class="legend-item"><i class="swatch is-orig-gap"></i>${{isZh ? '未填补 Gap' : 'Unfilled'}}</span>`
                + `</div>`;

            const steps = [1, 1.5, 2, 3, 4];
            let idx = 0;
            const ctrl = document.createElement('div');
            ctrl.className = 'story-zoom-ctrl';
            const outBtn = document.createElement('button'); outBtn.type = 'button'; outBtn.textContent = '−';
            const pctEl = document.createElement('span'); pctEl.className = 'story-zoom-pct'; pctEl.textContent = '100%';
            const inBtn = document.createElement('button'); inBtn.type = 'button'; inBtn.textContent = '+';
            const rstBtn = document.createElement('button'); rstBtn.type = 'button'; rstBtn.textContent = isZh ? '重置' : 'Reset';
            ctrl.append(outBtn, pctEl, inBtn, rstBtn);
            bar.appendChild(ctrl);

            const stage = document.createElement('div');
            stage.className = 'story-zoom-stage';
            const clone = src.cloneNode(true);
            clone.removeAttribute('id');
            stage.appendChild(clone);

            const applyZoom = () => {{
                const s = steps[idx];
                const inner = clone.querySelector('.ov-track-inner');
                if (inner) inner.style.setProperty('--chart-scale', String(s));
                pctEl.textContent = Math.round(s * 100) + '%';
                outBtn.disabled = idx <= 0;
                inBtn.disabled = idx >= steps.length - 1;
                rstBtn.disabled = idx === 0;
                stage.classList.toggle('is-pannable', s > 1);
            }};
            outBtn.addEventListener('click', () => {{ if (idx > 0) {{ idx--; applyZoom(); }} }});
            inBtn.addEventListener('click', () => {{ if (idx < steps.length - 1) {{ idx++; applyZoom(); }} }});
            rstBtn.addEventListener('click', () => {{ idx = 0; applyZoom(); stage.scrollLeft = 0; }});

            let drag = null;
            stage.addEventListener('mousedown', (e) => {{
                if (e.button !== 0 || steps[idx] <= 1 || e.target.closest('button,a')) return;
                drag = {{ x: e.clientX, y: e.clientY, sl: stage.scrollLeft, st: stage.scrollTop }};
                stage.classList.add('is-dragging');
            }});
            stage.addEventListener('mousemove', (e) => {{
                if (!drag) return;
                stage.scrollLeft = drag.sl - (e.clientX - drag.x);
                stage.scrollTop = drag.st - (e.clientY - drag.y);
            }});
            const endDrag = () => {{ if (drag) {{ drag = null; stage.classList.remove('is-dragging'); }} }};
            stage.addEventListener('mouseup', endDrag);
            stage.addEventListener('mouseleave', endDrag);

            applyZoom();
            body.append(bar, stage);
            if (typeof dlg.showModal === 'function') {{
                if (!dlg.open) dlg.showModal();
            }} else {{
                dlg.setAttribute('open', '');
            }}
        }}

        function closeTrackZoom() {{
            const dlg = document.getElementById('degapZoomDialog');
            if (!dlg) return;
            if (typeof dlg.close === 'function' && dlg.open) {{
                dlg.close();
            }} else {{
                dlg.removeAttribute('open');
            }}
        }}

        // Draw multi-row chromosome in unified CGAT track frame style (shared ruler + window rows + aligned gap blocks)
        function drawMultiRowChromosome(chrom, chromData, chromLength, trackLength, container) {{
            const axisLen = Math.max(1, trackLength);
            const numRows = Math.ceil(chromLength / axisLen);
            const sortedGaps = [...chromData.gaps].sort(compareGapsGenomic);
            const isZh = currentLang === 'zh';

            const inner = document.createElement('div');
            inner.className = 'ov-track-inner is-multirow';

            // Shared relative ruler header
            const axisRow = document.createElement('div');
            axisRow.className = 'ov-axis';
            const axisLbl = document.createElement('span');
            axisLbl.textContent = isZh ? '坐标区间（原始）' : 'Window (orig)';
            const ruler = document.createElement('span');
            ruler.className = 'story-ruler';
            [0, 0.25, 0.5, 0.75, 1].forEach(frac => {{
                const sp = document.createElement('span');
                sp.textContent = frac === 0 ? '+0' : '+' + formatBP(Math.round(axisLen * frac));
                ruler.appendChild(sp);
            }});
            axisRow.appendChild(axisLbl);
            axisRow.appendChild(ruler);
            inner.appendChild(axisRow);

            const listDiv = document.createElement('div');
            listDiv.className = 'ov-track-list';

            for (let row = 0; row < numRows; row++) {{
                const rowStart = row * axisLen;
                const rowEnd = Math.min((row + 1) * axisLen, chromLength);
                const rowLength = rowEnd - rowStart;

                const rowGaps = [];
                sortedGaps.forEach(gap => {{
                    const placement = getOriginalTrackPlacement(gap, rowStart, rowEnd);
                    if (placement !== null) rowGaps.push({{ gap, placement }});
                }});

                const rowEl = document.createElement('div');
                rowEl.className = 'ov-chr-row' + (rowGaps.length === 0 ? ' is-empty-win' : '');

                const meta = document.createElement('span');
                meta.className = 'ov-chr-meta';
                const rangeSpan = document.createElement('span');
                rangeSpan.className = 'ov-win-range';
                rangeSpan.textContent = `${{formatBP(rowStart)}} – ${{formatBP(rowEnd)}}`;

                const pills = document.createElement('span');
                pills.className = 'ov-win-pills';
                if (rowGaps.length === 0) {{
                    const dash = document.createElement('span');
                    dash.className = 'muted';
                    dash.textContent = '—';
                    pills.appendChild(dash);
                }} else {{
                    const fRow = rowGaps.filter(x => x.gap.filled).length;
                    const uRow = rowGaps.length - fRow;
                    if (fRow > 0) {{
                        const p = document.createElement('span');
                        p.className = 'ov-win-pill is-ok';
                        p.textContent = isZh ? `${{fRow}}填` : `${{fRow}}✓`;
                        pills.appendChild(p);
                    }}
                    if (uRow > 0) {{
                        const p = document.createElement('span');
                        p.className = 'ov-win-pill is-err';
                        p.textContent = isZh ? `${{uRow}}剩` : `${{uRow}}G`;
                        pills.appendChild(p);
                    }}
                }}
                meta.appendChild(rangeSpan);
                meta.appendChild(pills);
                rowEl.appendChild(meta);

                const rail = document.createElement('span');
                rail.className = 'ov-rail is-multirow';

                const srcSeg = document.createElement('span');
                srcSeg.className = 'ov-seg is-src';
                srcSeg.style.left = '0%';
                srcSeg.style.width = (rowLength / axisLen * 100).toFixed(4) + '%';
                rail.appendChild(srcSeg);

                let lastPct = -100;
                let flip = false;
                rowGaps.forEach(({{ gap, placement }}) => {{
                    const leftPct = Math.min(Math.max(placement.relativeStart, 0), axisLen) / axisLen * 100;
                    const widthPct = Math.max(0, placement.clippedSpan / axisLen * 100);
                    if (leftPct - lastPct < 5.5) flip = !flip;
                    else flip = false;
                    lastPct = leftPct;

                    const linkFlag = gap.report_direction || (gap.filled && gap.fill_direction ? gap.fill_direction : 'left');
                    const reportFile = `${{chrom}}.${{gap.gap_id}}.${{linkFlag}}.html`;
                    const seg = document.createElement('a');
                    seg.className = 'ov-seg ' + (gap.filled ? 'is-patch' : 'is-gap');
                    seg.href = reportFile;
                    seg.target = '_blank';
                    seg.rel = 'noopener';
                    seg.style.left = leftPct.toFixed(4) + '%';
                    seg.style.width = widthPct.toFixed(4) + '%';
                    seg.setAttribute('aria-label', `${{chrom}} Gap ${{gap.gap_id}}: ${{gap.filled ? 'Filled' : 'Unfilled'}}`);

                    const tag = document.createElement('span');
                    tag.className = 'ov-seg-tag ' + (flip ? 'is-bot' : 'is-top');
                    tag.textContent = `#${{gap.gap_id}}`;
                    seg.appendChild(tag);

                    seg.addEventListener('mouseenter', (e) => showTooltip(e, gap, chrom));
                    seg.addEventListener('mouseleave', hideTooltip);
                    rail.appendChild(seg);
                }});

                rowEl.appendChild(rail);
                listDiv.appendChild(rowEl);
            }}

            inner.appendChild(listDiv);
            container.appendChild(inner);
        }}

        // Add clickable gap marker to a bar container in original assembly coordinates
        function addGapMarker(barContainerDiv, gap, index, chromLength, chrom, placement = null, useVariableWidth = false, barWidthPercent = 100) {{
            const isTop = index % 2 === 0;
            const resolved = placement || getOriginalTrackPlacement(gap);
            const linkFlag = gap.report_direction || (gap.filled && gap.fill_direction ? gap.fill_direction : 'left');
            const reportFile = `${{chrom}}.${{gap.gap_id}}.${{linkFlag}}.html`;

            const markerDiv = document.createElement('a');
            markerDiv.className = `gap-marker ${{isTop ? 'top' : 'bottom'}}`;
            markerDiv.href = reportFile;
            markerDiv.target = '_blank';
            markerDiv.rel = 'noopener';
            markerDiv.setAttribute('title', `${{chrom}} Gap ${{gap.gap_id}}: ${{gap.filled ? 'Filled' : 'Unfilled'}}`);

            // 0-based position on the original assembly axis
            const axisLen = chromLength > 0 ? chromLength : 1;
            const gapPosition = resolved.relativeStart;

            if (useVariableWidth) {{
                // Multi-row view: always display original gap span on the original-length axis
                const gapDisplayLength = resolved.clippedSpan;
                const gapWidthPercent = (gapDisplayLength / axisLen * 100);
                const minWidthPercent = 0.1; // Minimum 0.1% width to ensure visibility
                const finalWidthPercent = Math.max(gapWidthPercent, minWidthPercent);

                markerDiv.classList.add('has-width');
                markerDiv.style.left = (gapPosition / axisLen * 100).toFixed(4) + '%';
                markerDiv.style.width = finalWidthPercent.toFixed(4) + '%';
            }} else {{
                // Single-row view: draw gap at 0-based original start relative to bar width
                const clampedPos = Math.min(Math.max(gapPosition, 0), axisLen);
                const gapPositionInBar = (clampedPos / axisLen * 100);
                const finalPosition = gapPositionInBar * barWidthPercent / 100;
                markerDiv.style.left = finalPosition.toFixed(4) + '%';
            }}

            // Line (extends from track to label direction)
            const lineDiv = document.createElement('div');
            lineDiv.className = `gap-marker-line ${{gap.filled ? 'filled' : 'unfilled'}}`;
            markerDiv.appendChild(lineDiv);

            // Label (alternate top/bottom, outside the track)
            const labelDiv = document.createElement('div');
            labelDiv.className = `gap-marker-label ${{isTop ? 'top' : 'bottom'}} ${{gap.filled ? 'filled' : 'unfilled'}}`;
            labelDiv.textContent = `${{gap.gap_id}}`;
            markerDiv.appendChild(labelDiv);

            // Tooltip on hover
            markerDiv.addEventListener('mouseenter', (e) => {{
                showTooltip(e, gap, chrom);
            }});
            markerDiv.addEventListener('mouseleave', hideTooltip);

            barContainerDiv.appendChild(markerDiv);
        }}

        // Update track length display (with synced row count & presets)
        function updateTrackLengthDisplay(length, chromLength = null) {{
            const valueSpan = document.getElementById('trackLengthValue');
            if (!valueSpan) return;
            const L = chromLength || (currentSingleChrom && gapsByChrom[currentSingleChrom] ? gapsByChrom[currentSingleChrom].length : null);
            if (L && length > 0) {{
                const rows = Math.ceil(L / length);
                valueSpan.textContent = currentLang === 'zh'
                    ? `${{formatBP(length)}} · ${{rows}} 行`
                    : `${{formatBP(length)}} · ${{rows}}r`;
                syncRowPresetButtons(L, length);
            }} else {{
                valueSpan.textContent = formatBP(length);
            }}
        }}

        // Update track length from linear slider (clamps alignedMax to exact chromosome length for 1-row view)
        function updateTrackLength() {{
            const slider = document.getElementById('trackLengthSlider');
            const select = document.getElementById('chromSelect');
            if (!slider || !select) return;
            const selectedChrom = select.value;
            const L = gapsByChrom[selectedChrom] ? gapsByChrom[selectedChrom].length : null;
            const rawVal = Math.max(1, parseInt(slider.value, 10));
            currentTrackLength = (L && rawVal >= L) ? L : rawVal;
            updateTrackLengthDisplay(currentTrackLength, L);
            drawChromVisualization(selectedChrom);
        }}

        // Show tooltip clamped inside viewport
        function showTooltip(event, gap, chrom) {{
            const tooltip = document.getElementById('tooltip');
            tooltip.innerHTML = buildTooltipContent(gap, chrom);
            tooltip.style.display = 'block';
            const pad = 12;
            const tipW = tooltip.offsetWidth || 260;
            const tipH = tooltip.offsetHeight || 120;
            const maxX = window.scrollX + window.innerWidth - tipW - pad;
            const maxY = window.scrollY + window.innerHeight - tipH - pad;
            const left = Math.max(window.scrollX + pad, Math.min(event.pageX + 12, maxX));
            const top = Math.max(window.scrollY + pad, Math.min(event.pageY + 12, maxY));
            tooltip.style.left = left + 'px';
            tooltip.style.top = top + 'px';
        }}

        // Hide tooltip
        function hideTooltip() {{
            document.getElementById('tooltip').style.display = 'none';
        }}

        // Filter chromosome
        function filterChromosome() {{
            const select = document.getElementById('chromSelect');
            const selectedChrom = select.value;
            drawChromVisualization(selectedChrom);
        }}

        function resetAllChromosomes() {{
            const select = document.getElementById('chromSelect');
            if (select) {{
                select.value = 'all';
            }}
            drawChromVisualization('all');
        }}

        // Chromosome filter functions
        let currentFilterTable = null;
        const selectedChroms = {{
            initial: 'all',
            tasks: 'all',
            final: 'all'
        }};

        function buildFilterMenu(container, tableType, allLabel, chromNames) {{
            container.innerHTML = '';
            const allItem = document.createElement('div');
            allItem.className = 'chrom-filter-item active';
            allItem.textContent = allLabel;
            allItem.addEventListener('click', (e) => {{
                e.stopPropagation();
                selectChrom(tableType, 'all');
            }});
            container.appendChild(allItem);

            chromNames.forEach(chrom => {{
                const item = document.createElement('div');
                item.className = 'chrom-filter-item';
                item.textContent = chrom;
                item.addEventListener('click', (e) => {{
                    e.stopPropagation();
                    selectChrom(tableType, chrom);
                }});
                container.appendChild(item);
            }});
        }}

        function initChromFilters() {{
            const chromNames = Object.keys(gapsByChrom).sort();

            // Initialize filters for all three tables
            ['initial', 'tasks', 'final'].forEach(tableType => {{
                const containerEn = document.getElementById(`${{tableType}}-chrom-filter`);
                const containerZh = document.getElementById(`${{tableType}}-chrom-filter-zh`);
                buildFilterMenu(containerEn, tableType, 'All', chromNames);
                buildFilterMenu(containerZh, tableType, '全部', chromNames);
            }});
        }}

        function toggleFilterMenu(tableType, event) {{
            event.stopPropagation();

            // Close all other menus
            document.querySelectorAll('.chrom-filter-menu').forEach(menu => {{
                if (!menu.id.includes(tableType)) {{
                    menu.classList.remove('show');
                }}
            }});

            // Toggle current menu
            const menuEn = document.getElementById(`${{tableType}}-chrom-filter`);
            const menuZh = document.getElementById(`${{tableType}}-chrom-filter-zh`);

            menuEn.classList.toggle('show');
            menuZh.classList.toggle('show');

            currentFilterTable = menuEn.classList.contains('show') ? tableType : null;
        }}

        function selectChrom(tableType, selectedChrom) {{
            selectedChroms[tableType] = selectedChrom;

            // Update active state
            const menuEn = document.getElementById(`${{tableType}}-chrom-filter`);
            const menuZh = document.getElementById(`${{tableType}}-chrom-filter-zh`);

            [menuEn, menuZh].forEach(menu => {{
                menu.querySelectorAll('.chrom-filter-item').forEach(item => {{
                    item.classList.remove('active');
                }});
            }});

            // Set active on selected items
            const items = document.querySelectorAll(`#${{tableType}}-chrom-filter .chrom-filter-item, #${{tableType}}-chrom-filter-zh .chrom-filter-item`);
            items.forEach(item => {{
                const text = item.textContent.trim();
                if ((selectedChrom === 'all' && (text === 'All' || text === '全部')) || text === selectedChrom) {{
                    item.classList.add('active');
                }}
            }});

            // Filter table
            filterTableByChrom(tableType, selectedChrom);

            // Close menu
            menuEn.classList.remove('show');
            menuZh.classList.remove('show');
        }}

        function filterTasksByStatus(status) {{
            selectedTaskStatus = status;
            document.querySelectorAll('.status-filter-btn').forEach(btn => {{
                btn.classList.toggle('active', btn.getAttribute('data-status') === status);
            }});
            filterTableByChrom('tasks', selectedChroms.tasks);
        }}

        function filterTableByChrom(tableType, selectedChrom) {{
            const tableId = tableType === 'initial' ? 'initialGenomeTable' :
                           tableType === 'tasks' ? 'gapFillingTasksTable' :
                           'finalGenomeTable';

            const tbody = document.getElementById(tableId + 'Body');
            const rows = tbody.querySelectorAll('tr');

            rows.forEach(row => {{
                const chromCell = row.cells[0];
                if (chromCell) {{
                    const chromName = chromCell.textContent.trim();
                    const chromMatch = (selectedChrom === 'all' || chromName === selectedChrom);
                    const statusMatch = (tableType !== 'tasks' || selectedTaskStatus === 'all' || row.getAttribute('data-filled') === selectedTaskStatus);
                    row.style.display = (chromMatch && statusMatch) ? '' : 'none';
                }}
            }});
        }}

        // Close filter menu when clicking outside
        document.addEventListener('click', (event) => {{
            if (!event.target.closest('.chrom-filter-icon')) {{
                document.querySelectorAll('.chrom-filter-menu').forEach(menu => {{
                    menu.classList.remove('show');
                }});
                currentFilterTable = null;
            }}
        }});

        // Runtime & compact formatting helpers
        function formatDuration(sec) {{
            const s = toFiniteNumber(sec);
            if (s === null || s < 0) return '-';
            if (s < 60) return s.toFixed(1) + 's';
            if (s < 3600) return (s / 60).toFixed(1) + 'm';
            const h = Math.floor(s / 3600);
            const m = Math.round((s - h * 3600) / 60);
            return m > 0 ? `${{h}}h ${{m}}m` : `${{h}}h`;
        }}

        function formatCompactBP(bp) {{
            const n = toFiniteNumber(bp);
            if (n === null || n <= 0) return '0';
            if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
            if (n >= 10000) return Math.round(n / 1000) + 'k';
            if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
            return String(Math.round(n));
        }}

        function formatLRBadge(chrom, gap) {{
            const key = `${{chrom}}:${{gap.gap_id}}`;
            const pair = gapExtRounds && gapExtRounds[key];
            if (Array.isArray(pair) && pair.length === 2) {{
                return `${{pair[0]}}L+${{pair[1]}}R`;
            }}
            const r = toFiniteNumber(gap && gap.rounds);
            return r !== null ? `${{r}}R` : '';
        }}

        function getStepMeta(stepId, fallbackName, lang) {{
            const isZh = lang === 'zh';
            const table = {{
                step1: {{ label: isZh ? 'Reads 预处理' : 'Reads Prep', short: isZh ? '预处理' : 'Prep', color: 'var(--ds-0)' }},
                step2: {{ label: isZh ? 'Gap 检测' : 'Gap Detect', short: isZh ? '检测' : 'Detect', color: 'var(--ds-5)' }},
                step3: {{ label: isZh ? '双向延伸填补' : 'Gap Filling', short: isZh ? '填补' : 'Fill', color: 'var(--gen-closed)' }},
                step4: {{ label: isZh ? '基因组整合' : 'Integration', short: isZh ? '整合' : 'Integrate', color: 'var(--ds-1)' }},
                step5: {{ label: isZh ? '报告可视化' : 'Report', short: isZh ? '报告' : 'Report', color: 'var(--border-strong)' }},
            }};
            return table[stepId] || {{ label: fallbackName || stepId, short: fallbackName || stepId, color: 'var(--border-strong)' }};
        }}

        function formatMemoryMB(mb) {{
            const v = toFiniteNumber(mb);
            if (v === null || v <= 0) return '-';
            return v >= 1024 ? (v / 1024).toFixed(2) + ' GB' : v.toFixed(0) + ' MB';
        }}

        // Render Overview Key Metrics (2 CGAT-aligned panels) + Runtime Strip
        function renderOverviewCharts() {{
            const chrBox = document.getElementById('ovChromStatsChart');
            const gapBox = document.getElementById('ovGapDetailChart');
            const chrMeta = document.getElementById('ovChromStatsMeta');
            const gapMeta = document.getElementById('ovGapDetailMeta');
            const rtBar = document.getElementById('ovRuntimeBar');
            if (!chrBox || !gapBox) return;

            const isZh = currentLang === 'zh';
            const chromNames = Object.keys(gapsByChrom).sort();
            const totalGaps = toFiniteNumber(summary && summary.total_gaps) || 0;
            const filledGaps = toFiniteNumber(summary && summary.filled_gaps) || 0;
            const unfilledGaps = Math.max(0, totalGaps - filledGaps);

            // ---- Left Panel: Per-Chromosome Gap Count & Length (B: Grouped Vertical Bars [default] / A: Dual Horizontal Bars) ----
            if (chrMeta) {{
                chrMeta.textContent = isZh
                    ? `${{totalGaps}} → ${{unfilledGaps}} · 已填补 ${{filledGaps}}`
                    : `${{totalGaps}} → ${{unfilledGaps}} · ${{filledGaps}} filled`;
            }}

            if (chromNames.length === 0) {{
                chrBox.innerHTML = `<div class="empty-state" style="padding:18px;">${{bilingualSpan('No gap-bearing chromosomes', '暂无含 Gap 染色体')}}</div>`;
            }} else {{
                const allSeries = chromNames.map(c => {{
                    const gs = gapsByChrom[c].gaps || [];
                    let totalSpan = 0, filledSpan = 0;
                    gs.forEach(g => {{
                        const sp = getOriginalGapLength(g);
                        totalSpan += sp;
                        if (g.filled) filledSpan += sp;
                    }});
                    return {{
                        name: c,
                        total: gapsByChrom[c].total || gs.length,
                        filled: gapsByChrom[c].filled || 0,
                        remain: gapsByChrom[c].unfilled !== undefined ? gapsByChrom[c].unfilled : Math.max(0, (gapsByChrom[c].total || gs.length) - (gapsByChrom[c].filled || 0)),
                        totalSpan,
                        filledSpan,
                        clickable: true,
                    }};
                }});

                const activeMode = chromChartMode || (allSeries.length <= 10 ? 'vertical' : 'horizontal');
                document.querySelectorAll('[data-chr-mode]').forEach(btn => {{
                    const isAct = btn.getAttribute('data-chr-mode') === activeMode;
                    btn.classList.toggle('is-active', isAct);
                    btn.setAttribute('aria-pressed', isAct ? 'true' : 'false');
                }});

                if (activeMode === 'vertical') {{
                    // Mode B: Grouped Vertical Bars (Count bar + Length bar per chr; muted base = total, green = filled)
                    let series = allSeries;
                    if (series.length > 9) {{
                        series = [...allSeries].sort((a, b) => b.total - a.total || a.name.localeCompare(b.name));
                        const top = series.slice(0, 8);
                        const rest = series.slice(8);
                        top.push({{
                            name: isZh ? `其他(${{rest.length}})` : `+${{rest.length}}`,
                            total: rest.reduce((s, r) => s + r.total, 0),
                            filled: rest.reduce((s, r) => s + r.filled, 0),
                            remain: rest.reduce((s, r) => s + r.remain, 0),
                            totalSpan: rest.reduce((s, r) => s + r.totalSpan, 0),
                            filledSpan: rest.reduce((s, r) => s + r.filledSpan, 0),
                            clickable: false,
                        }});
                        series = top;
                    }}

                    const svgW = 460, svgH = 196;
                    const padL = 32, padR = 40, plotTop = 38, plotBot = 166;
                    const plotW = svgW - padL - padR, plotH = plotBot - plotTop;
                    const maxCntRaw = Math.max(1, ...series.map(d => d.total));
                    const yMaxCnt = maxCntRaw <= 4 ? Math.max(4, maxCntRaw) : Math.ceil(maxCntRaw / 2) * 2;
                    const maxSpanRaw = Math.max(1, ...series.map(d => d.totalSpan));
                    const spanPow = Math.pow(10, Math.floor(Math.log10(maxSpanRaw)));
                    const yMaxSpan = Math.ceil(maxSpanRaw / (spanPow * 0.5)) * (spanPow * 0.5);

                    const slotW = plotW / series.length;
                    const pairGap = 5;
                    const barW = Math.min(24, Math.max(10, (slotW * 0.62 - pairGap) / 2));
                    const yCnt = v => plotBot - (v / yMaxCnt) * plotH;
                    const yLen = bp => plotBot - (bp / yMaxSpan) * plotH;

                    let svg = `<g transform="translate(86,12)">`
                        + `<rect x="0" y="-6.5" width="7" height="7" rx="1.5" fill="var(--surface-muted)" stroke="var(--border-default)"/>`
                        + `<text x="10" y="0" class="ov-leg-txt">${{isZh ? 'Gap 数量（左柱）' : 'Gap count (L)'}}</text>`
                        + `<rect x="108" y="-6.5" width="7" height="7" rx="1.5" fill="var(--brand-soft)" stroke="var(--accent-border)"/>`
                        + `<text x="118" y="0" class="ov-leg-txt">${{isZh ? 'Gap 长度（右柱）' : 'Gap length (R)'}}</text>`
                        + `<rect x="216" y="-6.5" width="7" height="7" rx="1.5" fill="var(--gen-closed)"/>`
                        + `<text x="226" y="0" class="ov-leg-txt">${{isZh ? '已填补' : 'Filled'}}</text>`
                        + `</g>`
                        + `<text x="${{padL - 4}}" y="26" text-anchor="end" class="ov-ax-txt">${{isZh ? '个数' : 'Count'}}</text>`
                        + `<text x="${{svgW - padR + 4}}" y="26" text-anchor="start" class="ov-ax-txt">${{isZh ? '长度' : 'Length'}}</text>`;

                    // Gridlines + Left Y (Count) + Right Y (Length)
                    const ticks = 4;
                    for (let i = 0; i <= ticks; i++) {{
                        const frac = i / ticks;
                        const y = plotBot - frac * plotH;
                        const dash = i === 0 ? '' : ' stroke-dasharray="2.5 3"';
                        const cTick = Math.round(yMaxCnt * frac);
                        const lTick = i === 0 ? '0' : formatCompactBP(yMaxSpan * frac);
                        svg += `<line x1="${{padL}}" y1="${{y.toFixed(1)}}" x2="${{svgW - padR}}" y2="${{y.toFixed(1)}}" stroke="var(--border-subtle)"${{dash}}/>`
                            + `<text x="${{padL - 6}}" y="${{(y + 3).toFixed(1)}}" text-anchor="end" class="ov-ax-txt">${{cTick}}</text>`
                            + `<text x="${{svgW - padR + 6}}" y="${{(y + 3).toFixed(1)}}" text-anchor="start" class="ov-ax-txt">${{escapeHtml(lTick)}}</text>`;
                    }}

                    series.forEach((d, idx) => {{
                        const cx = padL + slotW * (idx + 0.5);
                        const lx = cx - pairGap / 2 - barW;
                        const rx = cx + pairGap / 2;

                        const cTotH = Math.max(2, plotBot - yCnt(d.total));
                        const cFilH = d.filled > 0 ? Math.max(3, plotBot - yCnt(d.filled)) : 0;
                        const lTotH = d.totalSpan > 0 ? Math.max(3, plotBot - yLen(d.totalSpan)) : 0;
                        const lFilH = d.filledSpan > 0 ? Math.max(3, plotBot - yLen(d.filledSpan)) : 0;

                        const shortChr = d.name.length > 11 ? d.name.slice(0, 10) + '…' : d.name;
                        const tip = isZh
                            ? `${{d.name}} — 数量：已填补 ${{d.filled}} / 总 ${{d.total}}（剩 ${{d.remain}}）；长度：已填补 ${{formatBP(d.filledSpan)}} / 总 ${{formatBP(d.totalSpan)}}`
                            : `${{d.name}} — Count: ${{d.filled}} / ${{d.total}} filled (${{d.remain}} left); Length: ${{formatBP(d.filledSpan)}} / ${{formatBP(d.totalSpan)}}`;
                        const gAttr = d.clickable ? ` class="ov-bar-row" data-ov-chrom="${{escapeHtml(d.name)}}"` : '';

                        svg += `<g${{gAttr}}><title>${{escapeHtml(tip)}}</title>`
                            + `<rect class="ov-row-bg" x="${{(cx - slotW * 0.44).toFixed(1)}}" y="${{plotTop - 10}}" width="${{(slotW * 0.88).toFixed(1)}}" height="${{plotH + 34}}" rx="4" fill="transparent"/>`
                            // Left bar: Count (base = total, green = filled)
                            + `<rect x="${{lx.toFixed(1)}}" y="${{(plotBot - cTotH).toFixed(1)}}" width="${{barW.toFixed(1)}}" height="${{cTotH.toFixed(1)}}" rx="2" fill="var(--surface-muted)" stroke="var(--border-default)"/>`
                            + (cFilH > 0 ? `<rect x="${{lx.toFixed(1)}}" y="${{(plotBot - cFilH).toFixed(1)}}" width="${{barW.toFixed(1)}}" height="${{cFilH.toFixed(1)}}" rx="2" fill="var(--gen-closed)" opacity="0.9"/>` : '')
                            + `<text x="${{(lx + barW / 2).toFixed(1)}}" y="${{(plotBot - cTotH - 4).toFixed(1)}}" text-anchor="middle" class="ov-bar-val${{d.filled > 0 ? ' is-win' : ''}}">${{d.filled}}/${{d.total}}</text>`
                            // Right bar: Length (base = total span, green = filled span)
                            + `<rect x="${{rx.toFixed(1)}}" y="${{(plotBot - lTotH).toFixed(1)}}" width="${{barW.toFixed(1)}}" height="${{lTotH.toFixed(1)}}" rx="2" fill="var(--brand-soft)" stroke="var(--accent-border)"/>`
                            + (lFilH > 0 ? `<rect x="${{rx.toFixed(1)}}" y="${{(plotBot - lFilH).toFixed(1)}}" width="${{barW.toFixed(1)}}" height="${{lFilH.toFixed(1)}}" rx="2" fill="var(--gen-closed)" opacity="0.9"/>` : '')
                            + `<text x="${{(rx + barW / 2).toFixed(1)}}" y="${{(plotBot - lTotH - 4).toFixed(1)}}" text-anchor="middle" class="ov-bar-val">${{escapeHtml(formatCompactBP(d.totalSpan))}}</text>`
                            // Chr name
                            + `<text x="${{cx.toFixed(1)}}" y="${{(plotBot + 16).toFixed(1)}}" text-anchor="middle" class="ov-ax-lbl">${{escapeHtml(shortChr)}}</text>`
                            + `</g>`;
                    }});

                    chrBox.innerHTML = `<svg class="ov-svg" viewBox="0 0 ${{svgW}} ${{svgH}}" role="img" aria-label="Gap count and length by chromosome (grouped bars)">${{svg}}</svg>`;
                }} else {{
                    // Mode A: Dual-Column Horizontal Bars (Count column + Length column per chr; muted base = total, green = filled)
                    const maxCnt = Math.max(1, ...allSeries.map(d => d.total));
                    const maxSpan = Math.max(1, ...allSeries.map(d => d.totalSpan));
                    const rowH = allSeries.length <= 6 ? 26 : 21;
                    const headH = 22;
                    const svgW = 460;
                    const svgH = headH + allSeries.length * rowH + 8;
                    const cBarX = 104, cBarW = 108, cValX = 218;
                    const lBarX = 264, lBarW = 112, lValX = 382;

                    let svg = `<g font-size="8.5" font-family="var(--font-sans)" fill="var(--text-muted)">`
                        + `<text x="96" y="13" text-anchor="end" class="ov-leg-txt">${{isZh ? '染色体' : 'Chr'}}</text>`
                        + `<text x="${{cBarX}}" y="13" class="ov-leg-txt">${{isZh ? 'Gap 数量（绿=已填补）' : 'Count (green=filled)'}}</text>`
                        + `<text x="${{lBarX}}" y="13" class="ov-leg-txt">${{isZh ? 'Gap 长度（绿=已填补）' : 'Length (green=filled)'}}</text>`
                        + `<line x1="6" y1="18" x2="454" y2="18" stroke="var(--border-subtle)"/>`
                        + `</g>`;

                    allSeries.forEach((d, idx) => {{
                        const y = headH + idx * rowH;
                        const cy = y + rowH / 2 + 3;
                        const barY = y + (rowH - 10) / 2;
                        const cTotW = Math.max(4, (d.total / maxCnt) * cBarW);
                        const cFilW = d.filled > 0 ? Math.max(3, (d.filled / maxCnt) * cBarW) : 0;
                        const lTotW = d.totalSpan > 0 ? Math.max(4, (d.totalSpan / maxSpan) * lBarW) : 0;
                        const lFilW = d.filledSpan > 0 ? Math.max(3, (d.filledSpan / maxSpan) * lBarW) : 0;
                        const shortChr = d.name.length > 11 ? d.name.slice(0, 10) + '…' : d.name;
                        const lenValTxt = d.filledSpan > 0
                            ? `${{formatCompactBP(d.filledSpan)}}/${{formatCompactBP(d.totalSpan)}}`
                            : `0/${{formatCompactBP(d.totalSpan)}}`;
                        const tip = isZh
                            ? `${{d.name}} — 数量：已填补 ${{d.filled}} / 总 ${{d.total}}（剩 ${{d.remain}}）；长度：已填补 ${{formatBP(d.filledSpan)}} / 总 ${{formatBP(d.totalSpan)}}`
                            : `${{d.name}} — Count: ${{d.filled}} / ${{d.total}} filled (${{d.remain}} left); Length: ${{formatBP(d.filledSpan)}} / ${{formatBP(d.totalSpan)}}`;
                        svg += `<g class="ov-bar-row" data-ov-chrom="${{escapeHtml(d.name)}}"><title>${{escapeHtml(tip)}}</title>`
                            + `<rect class="ov-row-bg" x="2" y="${{y + 1}}" width="456" height="${{rowH - 2}}" rx="3" fill="transparent"/>`
                            + `<text class="ov-bar-lbl" x="96" y="${{cy.toFixed(1)}}" text-anchor="end">${{escapeHtml(shortChr)}}</text>`
                            // Count bar
                            + `<rect x="${{cBarX}}" y="${{barY.toFixed(1)}}" width="${{cTotW.toFixed(1)}}" height="10" rx="2" fill="var(--surface-muted)" stroke="var(--border-default)"/>`
                            + (cFilW > 0 ? `<rect x="${{cBarX}}" y="${{barY.toFixed(1)}}" width="${{cFilW.toFixed(1)}}" height="10" rx="2" fill="var(--gen-closed)" opacity="0.9"/>` : '')
                            + `<text class="ov-bar-val${{d.filled > 0 ? ' is-win' : ''}}" x="${{cValX}}" y="${{cy.toFixed(1)}}">${{d.filled}}/${{d.total}}</text>`
                            // Length bar
                            + `<rect x="${{lBarX}}" y="${{barY.toFixed(1)}}" width="${{lTotW.toFixed(1)}}" height="10" rx="2" fill="var(--brand-soft)" stroke="var(--accent-border)"/>`
                            + (lFilW > 0 ? `<rect x="${{lBarX}}" y="${{barY.toFixed(1)}}" width="${{lFilW.toFixed(1)}}" height="10" rx="2" fill="var(--gen-closed)" opacity="0.9"/>` : '')
                            + `<text class="ov-bar-val${{d.filledSpan > 0 ? ' is-win' : ''}}" x="${{lValX}}" y="${{cy.toFixed(1)}}">${{escapeHtml(lenValTxt)}}</text>`
                            + `</g>`;
                    }});

                    const svgHtml = `<svg class="ov-svg" viewBox="0 0 ${{svgW}} ${{svgH}}" role="img" aria-label="Gap count and length by chromosome (dual horizontal bars)">${{svg}}</svg>`;
                    chrBox.innerHTML = allSeries.length > 8 ? `<div class="ov-svg-scroll">${{svgHtml}}</div>` : svgHtml;
                }}

                chrBox.querySelectorAll('[data-ov-chrom]').forEach(el => {{
                    el.addEventListener('click', () => {{
                        const target = el.getAttribute('data-ov-chrom');
                        const sel = document.getElementById('chromSelect');
                        if (sel && target) {{
                            sel.value = target;
                            filterChromosome();
                        }}
                    }});
                }});
            }}

            // ---- Right Panel: Per-Gap Closure (Length + X*L + Y*R) ----
            const allGaps = [];
            chromNames.forEach(c => {{
                (gapsByChrom[c].gaps || []).forEach(g => {{
                    const origSpan = getOriginalGapLength(g);
                    const fl = g.filled ? getFilledSequenceLength(g) : null;
                    const displayLen = g.filled ? (fl !== null ? Math.max(0, fl) : origSpan) : origSpan;
                    const linkFlag = g.report_direction || (g.fill_direction && g.fill_direction !== 'none' ? g.fill_direction : 'left');
                    allGaps.push({{
                        chrom: c,
                        gapId: g.gap_id,
                        filled: !!g.filled,
                        origSpan,
                        rawFill: fl,
                        displayLen,
                        lr: formatLRBadge(c, g),
                        href: `${{c}}.${{g.gap_id}}.${{linkFlag}}.html`,
                    }});
                }});
            }});

            const filledRows = allGaps.filter(g => g.filled).sort((a, b) => b.displayLen - a.displayLen);
            const openRows = allGaps.filter(g => !g.filled).sort((a, b) => b.displayLen - a.displayLen);
            const orderedGaps = [...filledRows, ...openRows];

            if (gapMeta) {{
                gapMeta.textContent = isZh
                    ? `${{filledRows.length}} 闭合 · ${{openRows.length}} 未闭合`
                    : `${{filledRows.length}} closed · ${{openRows.length}} open`;
            }}

            if (orderedGaps.length === 0) {{
                gapBox.innerHTML = `<div class="empty-state" style="padding:18px;">${{bilingualSpan('No gaps recorded', '暂无 Gap 记录')}}</div>`;
            }} else {{
                const positiveLens = orderedGaps.map(g => g.displayLen).filter(v => v > 0);
                const minLen = positiveLens.length ? Math.min(...positiveLens) : 1;
                const maxLen = positiveLens.length ? Math.max(...positiveLens) : 1;
                const useLog = maxLen / Math.max(1, minLen) > 15;
                const scaleLen = v => {{
                    if (v <= 0) return 0;
                    if (!useLog) return v / maxLen;
                    return Math.log10(v + 50) / Math.log10(maxLen + 50);
                }};

                const rowH = 19, headH = 20, gapSep = (filledRows.length > 0 && openRows.length > 0) ? 7 : 0;
                const svgW = 460, barX = 112, barMaxW = 206, valX = 326;
                const svgH = headH + orderedGaps.length * rowH + gapSep + 6;

                let parts = `<g transform="translate(8,12)">`
                    + `<rect x="0" y="-6.5" width="7" height="7" rx="1.5" fill="var(--gen-closed)"/>`
                    + `<text x="10" y="0" class="ov-leg-txt">${{isZh ? '已填补（填补长度 · L+R 轮次）' : 'Filled (fill len · L+R)'}}</text>`
                    + `<rect x="172" y="-6.5" width="7" height="7" rx="1.5" fill="var(--surface-muted)" stroke="var(--gen-gap)"/>`
                    + `<text x="182" y="0" class="ov-leg-txt">${{isZh ? '未填补（原始跨度）' : 'Unfilled (orig span)'}}</text>`
                    + (useLog ? `<text x="444" y="0" text-anchor="end" class="ov-bar-bp">${{isZh ? '对数尺度' : 'log scale'}}</text>` : '')
                    + `</g>`;

                orderedGaps.forEach((it, idx) => {{
                    const afterSplit = (filledRows.length > 0 && idx >= filledRows.length) ? gapSep : 0;
                    const y = headH + idx * rowH + afterSplit;
                    if (gapSep > 0 && idx === filledRows.length) {{
                        parts += `<line x1="8" y1="${{(y - 3.5).toFixed(1)}}" x2="452" y2="${{(y - 3.5).toFixed(1)}}" stroke="var(--border-subtle)" stroke-dasharray="3 3"/>`;
                    }}
                    const w = it.displayLen > 0 ? Math.max(4, scaleLen(it.displayLen) * barMaxW) : 2;
                    const lbl = `${{it.chrom.length > 11 ? it.chrom.slice(0, 10) + '…' : it.chrom}}:#${{it.gapId}}`;
                    const lenStr = formatBP(it.filled && it.rawFill !== null ? it.rawFill : it.displayLen);
                    const rightTxt = it.lr ? `${{lenStr}} · ${{it.lr}}` : lenStr;
                    const tip = it.filled
                        ? (isZh ? `${{it.chrom}} Gap ${{it.gapId}}（已填补）：填补 ${{lenStr}}（原跨度 ${{formatBP(it.origSpan)}}）· ${{it.lr}}` : `${{it.chrom}} Gap ${{it.gapId}} (Filled): ${{lenStr}} (orig ${{formatBP(it.origSpan)}}) · ${{it.lr}}`)
                        : (isZh ? `${{it.chrom}} Gap ${{it.gapId}}（未填补）：原始跨度 ${{formatBP(it.origSpan)}} · 尝试 ${{it.lr}}` : `${{it.chrom}} Gap ${{it.gapId}} (Unfilled): orig ${{formatBP(it.origSpan)}} · tried ${{it.lr}}`);
                    const barRect = it.filled
                        ? `<rect x="${{barX}}" y="${{y + 4}}" width="${{w.toFixed(1)}}" height="9" rx="2" fill="var(--gen-closed)" opacity="0.9"/>`
                        : `<rect x="${{barX}}" y="${{y + 4}}" width="${{w.toFixed(1)}}" height="9" rx="2" fill="var(--tone-err-bg)" stroke="var(--gen-gap)" stroke-width="0.9" stroke-dasharray="2.5 1.5"/>`;
                    parts += `<a href="${{escapeHtml(it.href)}}" target="_blank" rel="noopener"><g class="ov-bar-row">`
                        + `<title>${{escapeHtml(tip)}}</title>`
                        + `<rect class="ov-row-bg" x="2" y="${{y}}" width="456" height="${{rowH - 1}}" rx="3" fill="transparent"/>`
                        + `<text class="ov-bar-lbl" x="${{barX - 8}}" y="${{y + 12}}" text-anchor="end">${{escapeHtml(lbl)}}</text>`
                        + `<rect x="${{barX}}" y="${{y + 4}}" width="${{barMaxW}}" height="9" rx="2" fill="var(--surface-muted)"/>`
                        + barRect
                        + `<text class="ov-bar-val${{it.filled ? ' is-win' : ''}}" x="${{valX}}" y="${{y + 12}}">${{escapeHtml(rightTxt)}}</text>`
                        + `</g></a>`;
                }});
                const svgHtml = `<svg class="ov-svg" viewBox="0 0 ${{svgW}} ${{svgH}}" role="img" aria-label="Per-gap closure length and L/R rounds">${{parts}}</svg>`;
                gapBox.innerHTML = orderedGaps.length > 9 ? `<div class="ov-svg-scroll">${{svgHtml}}</div>` : svgHtml;
            }}

            // ---- Subblock 3: CGAT-style Clickable Runtime Bar ----
            if (rtBar) {{
                const rtSteps = (runtimeSummary && Array.isArray(runtimeSummary.steps)) ? runtimeSummary.steps : [];
                if (rtSteps.length > 0) {{
                    const totalSec = toFiniteNumber(runtimeSummary.total_seconds)
                        || rtSteps.reduce((acc, s) => acc + (toFiniteNumber(s.seconds) || 0), 0);
                    const segTotal = Math.max(0.01, rtSteps.reduce((acc, s) => acc + (toFiniteNumber(s.seconds) || 0), 0));
                    const segsHtml = rtSteps.map(s => {{
                        const meta = getStepMeta(s.id, s.name, currentLang);
                        const sec = toFiniteNumber(s.seconds) || 0;
                        const share = sec / segTotal * 100;
                        return `<span class="ov-rt-seg" style="width:${{Math.max(1.2, share).toFixed(2)}}%;background:${{meta.color}};" title="${{escapeHtml(meta.label)}}: ${{escapeHtml(formatDuration(sec))}} (${{share.toFixed(1)}}%)"></span>`;
                    }}).join('');
                    const legHtml = rtSteps.filter(s => (toFiniteNumber(s.seconds) || 0) >= 0.5 || s.id !== 'step5').map(s => {{
                        const meta = getStepMeta(s.id, s.name, currentLang);
                        const sec = toFiniteNumber(s.seconds) || 0;
                        return `<span class="ov-rt-item"><i class="ov-rt-dot" style="background:${{meta.color}}"></i>${{escapeHtml(meta.short)}} <b>${{escapeHtml(formatDuration(sec))}}</b></span>`;
                    }}).join('');
                    rtBar.innerHTML = `<span class="ov-rt-head">${{isZh ? '运行耗时' : 'Runtime'}} <b>${{escapeHtml(formatDuration(totalSec))}}</b></span>`
                        + `<span class="ov-rt-track" aria-hidden="true">${{segsHtml}}</span>`
                        + `<span class="ov-rt-legend">${{legHtml}}</span>`
                        + `<span class="ov-rt-more">${{isZh ? '详情 ↗' : 'Details ↗'}}</span>`;
                    rtBar.style.display = 'flex';
                }} else {{
                    rtBar.style.display = 'none';
                }}
            }}
        }}

        // Build CGAT-Aligned 3-Block Runtime & Resource Modal (with per-gap timeline subdivision)
        function renderRuntimeModalContent() {{
            const body = document.getElementById('rtDlgBody');
            if (!body || !runtimeSummary || !Array.isArray(runtimeSummary.steps)) return;

            const isZh = currentLang === 'zh';
            const steps = runtimeSummary.steps;
            const jobs = Array.isArray(runtimeSummary.jobs) ? runtimeSummary.jobs : [];
            const params = runtimeSummary.parameters || {{}};
            const totalSec = toFiniteNumber(runtimeSummary.total_seconds)
                || steps.reduce((acc, s) => acc + (toFiniteNumber(s.seconds) || 0), 0);

            const gapByJob = {{}};
            Object.keys(gapsByChrom).forEach(c => {{
                (gapsByChrom[c].gaps || []).forEach(g => {{
                    const flag = g.report_direction || (g.fill_direction && g.fill_direction !== 'none' ? g.fill_direction : 'left');
                    const key = `${{c}}.${{g.gap_id}}.${{flag}}`;
                    gapByJob[key] = {{ chrom: c, gapId: g.gap_id, filled: !!g.filled, href: `${{key}}.html` }};
                }});
            }});

            // Build unified unit list: Step 1, Step 2, individual Gap jobs (expanding Step 3), Step 4, Step 5
            const units = [];
            const tOrigin = runtimeSummary.start_time ? Date.parse(runtimeSummary.start_time) : NaN;
            const tFinal = runtimeSummary.end_time ? Date.parse(runtimeSummary.end_time) : NaN;
            let seqEstimated = false;

            steps.forEach(s => {{
                const meta = getStepMeta(s.id, s.name, currentLang);
                const s0 = s.start_time ? Date.parse(s.start_time) : NaN;
                const s1 = s.end_time ? Date.parse(s.end_time) : NaN;
                if (s.id === 'step3' && jobs.length > 0) {{
                    const hasAllJobTimes = jobs.every(j => j.start_time && j.end_time && Number.isFinite(Date.parse(j.start_time)) && Number.isFinite(Date.parse(j.end_time)));
                    const sumJobSec = Math.max(0.01, jobs.reduce((acc, j) => acc + (toFiniteNumber(j.seconds) || 0), 0));
                    const isSequential = (toFiniteNumber(params.workers) || 1) === 1;
                    const step3SpanMs = (Number.isFinite(s0) && Number.isFinite(s1) && s1 > s0) ? (s1 - s0) : (sumJobSec * 1000);
                    let cursorMs = Number.isFinite(s0) ? s0 : tOrigin;
                    if (!hasAllJobTimes && isSequential) seqEstimated = true;

                    jobs.forEach(j => {{
                        const jsec = toFiniteNumber(j.seconds) || 0;
                        const info = gapByJob[j.job_name];
                        const isClosed = info ? info.filled : (j.status === 'success');
                        const shortName = j.job_name.replace(/\\.(bidirectional|left|right)$/, '');
                        let j0 = NaN, j1 = NaN;
                        if (hasAllJobTimes) {{
                            j0 = Date.parse(j.start_time);
                            j1 = Date.parse(j.end_time);
                        }} else if (isSequential && Number.isFinite(cursorMs)) {{
                            const durMs = (jsec / sumJobSec) * step3SpanMs;
                            j0 = cursorMs;
                            j1 = cursorMs + durMs;
                            cursorMs = j1;
                        }} else if (Number.isFinite(s0) && Number.isFinite(s1)) {{
                            j0 = s0;
                            j1 = s1;
                        }}
                        units.push({{
                            id: j.job_name,
                            label: shortName,
                            stage: meta.short,
                            kind: 'gap',
                            status: isClosed ? (isZh ? '已闭合' : 'Closed') : (j.status === 'error' || j.status === 'timeout' ? (isZh ? '异常' : 'Error') : (isZh ? '未闭合' : 'Unfilled')),
                            tone: isClosed ? 'tone-ok' : 'tone-err',
                            ok: isClosed,
                            seconds: jsec,
                            startMs: j0,
                            endMs: j1,
                            color: isClosed ? 'var(--gen-closed)' : 'var(--gen-gap)',
                            href: info ? info.href : null,
                            peakRssMb: toFiniteNumber(j.peak_rss_mb),
                        }});
                    }});
                }} else {{
                    const stRaw = String(s.status || 'completed').toLowerCase();
                    const stOk = stRaw === 'completed' || stRaw === 'success';
                    units.push({{
                        id: s.id,
                        label: meta.label,
                        stage: meta.short,
                        kind: 'step',
                        status: stOk ? (isZh ? '完成' : 'Done') : (isZh ? '异常' : stRaw),
                        tone: stOk ? 'tone-info' : 'tone-err',
                        ok: stOk,
                        seconds: toFiniteNumber(s.seconds) || 0,
                        startMs: s0,
                        endMs: s1,
                        color: meta.color,
                        href: null,
                        peakRssMb: toFiniteNumber(s.peak_rss_mb),
                    }});
                }}
            }});

            const sumUnitSec = Math.max(0.01, units.reduce((acc, u) => acc + u.seconds, 0));
            const maxUnitSec = Math.max(0.1, ...units.map(u => u.seconds));
            const rssVals = units.map(u => u.peakRssMb).filter(v => v !== null && v > 0);
            const peakRss = rssVals.length > 0 ? Math.max(...rssVals) : null;

            // Block 1: Single-line CGAT Summary Strip (replaces bulky KPI cards)
            const memTxt = peakRss !== null
                ? `<span>${{isZh ? '峰值内存' : 'Peak RSS'}} <b style="color:var(--gen-closed)">${{escapeHtml(formatMemoryMB(peakRss))}}</b></span>`
                : `<span class="muted">${{isZh ? '内存：未采集（新运行自动记录）' : 'Memory: not recorded (captured on new runs)'}}</span>`;
            const stripHtml = `<div class="story-meta-strip ov-rt-strip">`
                + `<span>${{isZh ? '总运行耗时' : 'Total wall time'}} <b>${{escapeHtml(formatDuration(totalSec))}}</b></span>`
                + `<span>${{isZh ? '并发' : 'Parallelism'}} <b>${{escapeHtml(params.thread ?? '-')}} ${{isZh ? '线程' : 'T'}} × ${{escapeHtml(params.workers ?? '-')}} worker</b></span>`
                + `<span>${{isZh ? `单元 ${{units.length}}（${{jobs.length}} Gap 任务）` : `${{units.length}} units (${{jobs.length}} gap jobs)`}}</span>`
                + memTxt
                + `</div>`;

            // Block 2: Two-column CGAT Charts Grid (Unified Unit Durations + Per-Gap Timeline Gantt)
            const rowH = 19, svgW = 460;
            const dSvgH = units.length * rowH + 14;
            let durParts = '';
            units.forEach((u, idx) => {{
                const y = 6 + idx * rowH;
                const pct = (u.seconds / sumUnitSec * 100).toFixed(1);
                const bw = Math.max(3, (u.seconds / maxUnitSec) * 212);
                const shortLbl = u.label.length > 14 ? u.label.slice(0, 13) + '…' : u.label;
                const rowG = `<g class="ov-bar-row"><title>${{escapeHtml(u.label)}}: ${{escapeHtml(formatDuration(u.seconds))}} (${{pct}}%)</title>`
                    + `<rect class="ov-row-bg" x="2" y="${{y}}" width="456" height="${{rowH - 1}}" rx="3" fill="transparent"/>`
                    + `<text class="ov-bar-lbl" x="116" y="${{y + 12.5}}" text-anchor="end">${{escapeHtml(shortLbl)}}</text>`
                    + `<rect x="124" y="${{y + 4.5}}" width="212" height="9" rx="2" fill="var(--surface-muted)"/>`
                    + `<rect x="124" y="${{y + 4.5}}" width="${{bw.toFixed(1)}}" height="9" rx="2" fill="${{u.color}}" opacity="0.9"/>`
                    + `<text class="ov-bar-val" x="342" y="${{y + 12.5}}">${{escapeHtml(formatDuration(u.seconds))}} · ${{pct}}%</text>`
                    + `</g>`;
                durParts += u.href ? `<a href="${{escapeHtml(u.href)}}" target="_blank" rel="noopener">${{rowG}}</a>` : rowG;
            }});
            const durCard = `<article class="ov-chart-card"><div class="ov-chart-head"><h4>${{isZh ? '任务耗时分布' : 'Unit Durations'}}</h4><span class="ov-chart-meta">${{isZh ? '绿=闭合 · 红=未闭合' : 'Green=closed · Red=open'}}</span></div><div class="ov-svg-scroll" style="max-height:340px;"><svg class="ov-svg" viewBox="0 0 ${{svgW}} ${{dSvgH}}" role="img" aria-label="Unit duration breakdown">${{durParts}}</svg></div></article>`;

            // Right: Per-Gap Execution Timeline Gantt
            const spanMs = (Number.isFinite(tOrigin) && Number.isFinite(tFinal) && tFinal > tOrigin) ? (tFinal - tOrigin) : (totalSec * 1000);
            const gSvgH = units.length * rowH + 26;
            const trackX = 124, trackW = 318;
            let gParts = `<line x1="${{trackX}}" y1="4" x2="${{trackX}}" y2="${{units.length * rowH + 8}}" stroke="var(--border-subtle)"/>`
                + `<line x1="${{trackX + trackW / 2}}" y1="4" x2="${{trackX + trackW / 2}}" y2="${{units.length * rowH + 8}}" stroke="var(--border-subtle)" stroke-dasharray="2.5 3"/>`
                + `<line x1="${{trackX + trackW}}" y1="4" x2="${{trackX + trackW}}" y2="${{units.length * rowH + 8}}" stroke="var(--border-subtle)"/>`;
            units.forEach((u, idx) => {{
                const y = 6 + idx * rowH;
                const shortLbl = u.label.length > 14 ? u.label.slice(0, 13) + '…' : u.label;
                let x = trackX, w = 4;
                if (Number.isFinite(tOrigin) && spanMs > 0 && Number.isFinite(u.startMs) && Number.isFinite(u.endMs)) {{
                    x = trackX + Math.max(0, Math.min(1, (u.startMs - tOrigin) / spanMs)) * trackW;
                    w = Math.max(3, Math.max(0, Math.min(1, (u.endMs - u.startMs) / spanMs)) * trackW);
                }}
                const clippedW = Math.max(3, Math.min(w, trackX + trackW - x));
                const rowG = `<g class="ov-bar-row"><title>${{escapeHtml(u.label)}}: ${{escapeHtml(formatDuration(u.seconds))}} (${{escapeHtml(u.status)}})</title>`
                    + `<text class="ov-bar-lbl" x="116" y="${{y + 12.5}}" text-anchor="end">${{escapeHtml(shortLbl)}}</text>`
                    + `<rect x="${{trackX}}" y="${{y + 4.5}}" width="${{trackW}}" height="9" rx="2" fill="var(--surface-muted)"/>`
                    + `<rect x="${{x.toFixed(1)}}" y="${{y + 4.5}}" width="${{clippedW.toFixed(1)}}" height="9" rx="2" fill="${{u.color}}" opacity="0.9"/>`
                    + `</g>`;
                gParts += u.href ? `<a href="${{escapeHtml(u.href)}}" target="_blank" rel="noopener">${{rowG}}</a>` : rowG;
            }});
            const axisY = units.length * rowH + 20;
            gParts += `<text x="${{trackX}}" y="${{axisY}}" class="ov-ax-txt">0s</text>`
                + `<text x="${{trackX + trackW / 2}}" y="${{axisY}}" text-anchor="middle" class="ov-ax-txt">${{escapeHtml(formatDuration(spanMs / 2000))}}</text>`
                + `<text x="${{trackX + trackW}}" y="${{axisY}}" text-anchor="end" class="ov-ax-txt">${{escapeHtml(formatDuration(spanMs / 1000))}}</text>`;
            const ganttSub = seqEstimated
                ? (isZh ? '按串行耗时排布' : 'sequential est.')
                : (isZh ? '真实起止时间' : 'wall clock');
            const ganttCard = `<article class="ov-chart-card"><div class="ov-chart-head"><h4>${{isZh ? '执行时间轴 (甘特图)' : 'Execution Timeline'}}</h4><span class="ov-chart-meta">${{escapeHtml(ganttSub)}}</span></div><div class="ov-svg-scroll" style="max-height:340px;"><svg class="ov-svg" viewBox="0 0 ${{svgW}} ${{gSvgH}}" role="img" aria-label="Execution timeline Gantt">${{gParts}}</svg></div></article>`;

            // Block 3: Compact Parameter Line + Unit Detail Table
            const pPairs = [
                ['kmer_size', 'k-mer'],
                ['kmer_num', 'k-mer num'],
                ['MaximumExtensionRound', isZh ? '最大轮次' : 'max rounds'],
                ['MaximumExtensionLength', isZh ? '最大延伸' : 'max ext'],
                ['edge', 'edge'],
                ['remove', 'remove'],
            ].filter(([k]) => params[k] !== undefined && params[k] !== null)
             .map(([k, l]) => `${{l}} ${{k === 'MaximumExtensionLength' ? formatBP(params[k]) : params[k]}}`);
            const paramLine = pPairs.length ? `<div class="ov-rt-params">${{isZh ? '运行参数：' : 'Parameters: '}}${{escapeHtml(pPairs.join(' · '))}}</div>` : '';

            const rowsHtml = units.map(u => {{
                const pct = (u.seconds / sumUnitSec * 100).toFixed(1) + '%';
                const nameInner = u.href
                    ? `<a href="${{escapeHtml(u.href)}}" target="_blank" rel="noopener"><code>${{escapeHtml(u.label)}}</code></a>`
                    : `<code>${{escapeHtml(u.label)}}</code>`;
                const rssCell = u.peakRssMb && u.peakRssMb > 0 ? escapeHtml(formatMemoryMB(u.peakRssMb)) : '—';
                return `<tr>`
                    + `<th scope="row"><i class="ov-rt-dot" style="display:inline-block;margin-right:6px;background:${{u.color}};vertical-align:middle"></i>${{nameInner}}</th>`
                    + `<td class="col-stage">${{escapeHtml(u.stage || '-')}}</td>`
                    + `<td class="col-num"><b>${{escapeHtml(formatDuration(u.seconds))}}</b></td>`
                    + `<td class="col-num muted">${{pct}}</td>`
                    + `<td class="col-num muted">${{rssCell}}</td>`
                    + `<td class="col-status"><span class="rt-badge ${{u.tone}}">${{escapeHtml(u.status)}}</span></td>`
                    + `</tr>`;
            }}).join('');
            const tableHtml = `<div class="ov-rt-table-wrap"><table class="ov-rt-table"><thead><tr>`
                + `<th scope="col" class="col-unit">${{isZh ? '执行单元' : 'Unit'}}</th>`
                + `<th scope="col" class="col-stage">${{isZh ? '阶段' : 'Stage'}}</th>`
                + `<th scope="col" class="col-num">${{isZh ? '耗时' : 'Duration'}}</th>`
                + `<th scope="col" class="col-num">${{isZh ? '占比' : 'Share'}}</th>`
                + `<th scope="col" class="col-num">${{isZh ? '峰值内存' : 'Peak RSS'}}</th>`
                + `<th scope="col" class="col-status">${{isZh ? '状态' : 'Status'}}</th>`
                + `</tr></thead><tbody>${{rowsHtml}}</tbody></table></div>`;

            body.innerHTML = `${{stripHtml}}<div class="ov-charts-grid">${{durCard}}${{ganttCard}}</div>${{paramLine}}${{tableHtml}}`;
        }}

        function openRuntimeModal() {{
            const dlg = document.getElementById('degapRuntimeDialog');
            if (!dlg) return;
            renderRuntimeModalContent();
            if (typeof dlg.showModal === 'function') {{
                if (!dlg.open) dlg.showModal();
            }} else {{
                dlg.setAttribute('open', '');
            }}
        }}

        function closeRuntimeModal() {{
            const dlg = document.getElementById('degapRuntimeDialog');
            if (!dlg) return;
            if (typeof dlg.close === 'function' && dlg.open) {{
                dlg.close();
            }} else {{
                dlg.removeAttribute('open');
            }}
        }}

        // Initialize
        document.addEventListener('DOMContentLoaded', () => {{
            populateReadsInfo();
            populateInitialGenomeTable();
            populateGapFillingTasksTable();
            populateFinalGenomeTable();
            populateChromSelector();
            drawChromVisualization();
            renderOverviewCharts();
            initChromFilters();
            switchLanguage(currentLang);
            ['degapRuntimeDialog', 'degapZoomDialog'].forEach(id => {{
                const d = document.getElementById(id);
                if (d && d.addEventListener) {{
                    d.addEventListener('click', (e) => {{
                        if (e.target === d) {{
                            if (typeof d.close === 'function' && d.open) d.close();
                            else d.removeAttribute('open');
                        }}
                    }});
                }}
            }});
        }});
    </script>
</body>
</html>
"""

        return html

    def _format_bp(self, bp):
        """格式化碱基对数量"""
        if abs(bp) >= 1000000:
            return f"{bp/1000000:+.2f} Mb"
        elif abs(bp) >= 1000:
            return f"{bp/1000:+.2f} Kb"
        else:
            return f"{bp:+,} bp"

    def _save_report(self, html_content):
        """保存 HTML 报告"""
        html_file = self.output_dir / 'Global.report.html'

        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"  Report saved: {html_file}")


def main():
    """命令行接口"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Generate gap filling visualization report',
        epilog='''
Example:
  %(prog)s -o output

Note: This script requires gap filling to be completed first.
      It will read results from:
      - output/03.gap_filling/gap_filling_results.json (required)
      - output/04.genome_integration/integration_config.json (optional)
      - output/01.reads_preprocessor/preprocessing_config.json (optional)

Features:
  - Interactive HTML report with chromosome visualization
  - Bilingual support (English/Chinese)
  - Gap filling statistics and distribution
  - Chromosome band visualization with gap positions
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--output', '-o', required=True, help='Output directory')

    args = parser.parse_args()

    try:
        visualizer = GapFillingVisualizer(args.output)
        result = visualizer.generate_report()

        print("\nVisualization result:")
        print(json.dumps(result, indent=2, default=str))
        print(f"\n✅ Open the HTML file in a web browser to view the report:")
        print(f"   {result['html_report']}")
        print(f"\n💡 The report supports:")
        print(f"   - Language switching (EN/中文)")
        print(f"   - Interactive chromosome visualization")
        print(f"   - Chromosome filtering (dropdown menu)")
        print(f"   - Gap details on hover")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

