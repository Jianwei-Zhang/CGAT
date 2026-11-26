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
    from ReportStyle import esc, report_css
except ImportError:
    from .ReportStyle import esc, report_css


class GapFillingVisualizer:
    """生成 gap filling 结果的可视化报告"""

    def __init__(self, output_dir):
        """
        初始化 Visualizer

        Args:
            output_dir: 主输出目录
        """
        self.main_output_dir = Path(output_dir)

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
        total_gaps = summary.get('total_gaps', 0)
        filled_gaps = summary.get('filled_gaps', 0)
        fill_rate = summary.get('fill_rate', '0%')
        chrom_count = len(self.gaps_by_chrom)

        bp_metric_html = ""
        if self.integration_config:
            stats = self.integration_config.get('stats', {})
            total_bp_added = getattr(self, 'total_bp_added', stats.get('total_bp_added', 0))
            bp_metric_html = f"""
            <span class="summary-strip-item">
                <span class="summary-strip-label"><span class="lang-en">Net Length</span><span class="lang-zh">净长度变化</span></span>
                <span class="summary-strip-val accent">{esc(self._format_bp(total_bp_added))}</span>
            </span>"""

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
        js_summary = json.dumps(summary, separators=(',', ':'))
        js_gaps_by_chrom = json.dumps(slim_gaps_by_chrom, separators=(',', ':'), default=str)
        js_preprocessing_config = json.dumps(self.preprocessing_config if self.preprocessing_config else {}, separators=(',', ':'))
        js_integration_config = json.dumps(self.integration_config if self.integration_config else {}, separators=(',', ':'))

        extra_css = """
        .table-toggle-container {
            position: sticky;
            bottom: 0;
            width: 100%;
            display: flex;
            justify-content: flex-end;
            padding: 8px 10px;
            background: rgba(255, 255, 255, 0.96);
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
            padding: 12px 20px;
            background: var(--surface-subtle);
            border-bottom: 1px solid var(--border);
        }

        .track-control-row {
            display: flex;
            align-items: center;
            gap: 14px;
            flex-wrap: wrap;
        }

        .track-control-label {
            font-weight: 600;
            font-size: 0.84rem;
            color: var(--ink-secondary);
            min-width: 110px;
        }

        .track-control-value {
            font-weight: 600;
            font-size: 0.85rem;
            color: var(--accent);
            font-variant-numeric: tabular-nums;
            min-width: 90px;
            text-align: right;
        }

        input[type="range"] {
            -webkit-appearance: none;
            appearance: none;
            height: 6px;
            background: var(--border-strong);
            border-radius: 3px;
            flex: 1;
            min-width: 160px;
        }

        input[type="range"]::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 16px;
            height: 16px;
            background: var(--accent);
            border: 2px solid var(--surface);
            border-radius: 50%;
            box-shadow: 0 0 0 1px var(--accent);
            cursor: pointer;
        }

        input[type="range"]::-moz-range-thumb {
            width: 16px;
            height: 16px;
            background: var(--accent);
            border: 2px solid var(--surface);
            border-radius: 50%;
            box-shadow: 0 0 0 1px var(--accent);
            cursor: pointer;
        }

        #chromVisualization {
            margin: 8px 0 12px;
            min-height: 120px;
        }

        .chrom-track {
            margin-bottom: 24px;
            padding-bottom: 18px;
            border-bottom: 1px solid var(--border);
        }

        .chrom-track:last-child {
            margin-bottom: 0;
            padding-bottom: 0;
            border-bottom: none;
        }

        .chrom-track-multirow {
            margin-bottom: 16px;
            padding-bottom: 14px;
        }

        .chrom-track-header {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            gap: 12px;
            margin-bottom: 10px;
            flex-wrap: wrap;
        }

        .chrom-track-name {
            font-family: var(--font-mono);
            font-weight: 600;
            font-size: 0.88rem;
            color: var(--ink);
            overflow-wrap: anywhere;
        }

        .chrom-track-length {
            font-size: 0.82rem;
            color: var(--ink-muted);
            font-variant-numeric: tabular-nums;
        }

        .chrom-track-bar-container {
            position: relative;
            height: 74px;
            padding: 24px 0;
        }

        .chrom-track-bar {
            position: relative;
            height: 16px;
            background: #e2e8f0;
            border: 1px solid #cbd5e1;
            border-radius: 8px;
        }

        .gap-marker {
            position: absolute;
            transform: translateX(-50%);
            cursor: pointer;
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
            width: 2px;
            height: 100%;
            margin: 0 auto;
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
            background: #15803d;
        }

        .gap-marker-line.unfilled {
            background: #b91c1c;
        }

        .gap-marker-label {
            position: absolute;
            left: 50%;
            transform: translateX(-50%);
            font-family: var(--font-mono);
            font-size: 11px;
            font-weight: 600;
            white-space: nowrap;
            cursor: pointer;
        }

        .gap-marker-label.top {
            bottom: 100%;
            margin-bottom: 3px;
        }

        .gap-marker-label.bottom {
            top: 100%;
            margin-top: 3px;
        }

        .gap-marker-label.filled {
            color: #166534;
        }

        .gap-marker-label.unfilled {
            color: #991b1b;
        }

        .gap-marker:hover .gap-marker-label {
            text-decoration: underline;
        }

        .legend {
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
            margin-top: 16px;
            padding: 12px 14px;
            background: var(--surface-subtle);
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            font-size: 0.84rem;
            color: var(--ink-secondary);
        }

        .legend-item {
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }

        .legend-color {
            width: 22px;
            height: 12px;
            border-radius: 3px;
            border: 1px solid rgba(15, 23, 42, 0.15);
            flex-shrink: 0;
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
            font-weight: 600;
            white-space: nowrap;
        }

        .fold-body > .jr-root { border: 0; margin: 0; }
        .fold-body > .jr-root > .section-header { display: none; }
        .fold-body > .jr-root > .section-body { padding: 4px 0 0; }
        .reads-bar { display: flex; flex-wrap: wrap; gap: 6px 18px; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); font-size: 0.8rem; color: var(--ink-muted); }
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

        html = f"""<!DOCTYPE html>
<html lang="en" data-lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoGapfiller - Gap Filling Report</title>
    <style>
{css}
    </style>
</head>
<body>
    <main class="container">
        <!-- Header & Summary Strip -->
        <header class="header">
            <div class="header-top">
                <div class="header-info">
                    <div class="report-eyebrow">DEGAP · AutoGapfiller</div>
                    <h1><span class="lang-en">Gap Filling Report</span><span class="lang-zh">Gap 填补报告</span></h1>
                </div>
                <div class="header-actions">
                    <div class="language-switcher" role="group" aria-label="Language Switcher">
                        <button type="button" class="language-btn active" data-lang="en" aria-pressed="true" onclick="switchLanguage('en')">EN</button>
                        <button type="button" class="language-btn" data-lang="zh" aria-pressed="false" onclick="switchLanguage('zh')">中文</button>
                    </div>
                </div>
            </div>
            <div class="summary-strip" role="group" aria-label="Summary overview">
                <span class="summary-strip-item">
                    <span class="summary-strip-label"><span class="lang-en">Total Gaps</span><span class="lang-zh">Gap 总数</span></span>
                    <span class="summary-strip-val">{esc(total_gaps)}</span>
                </span>
                <span class="summary-strip-item">
                    <span class="summary-strip-label"><span class="lang-en">Filled</span><span class="lang-zh">已填补</span></span>
                    <span class="summary-strip-val ok">{esc(filled_gaps)}</span>
                </span>
                <span class="summary-strip-item">
                    <span class="summary-strip-label"><span class="lang-en">Fill Rate</span><span class="lang-zh">填补率</span></span>
                    <span class="summary-strip-val accent">{esc(fill_rate)}</span>
                </span>
                <span class="summary-strip-item">
                    <span class="summary-strip-label"><span class="lang-en">Chromosomes</span><span class="lang-zh">染色体</span></span>
                    <span class="summary-strip-val">{chrom_count}</span>
                </span>{bp_metric_html}
            </div>
            <div id="readsInfoBar" class="reads-bar" style="display:none;"></div>
        </header>

        <!-- Chromosome Visualization Card (visual-first) -->
        <section class="section">
            <div class="section-header">
                <h2><span class="lang-en">Chromosome Overview</span><span class="lang-zh">染色体分布总览</span></h2>
                <select id="chromSelect" class="chrom-selector" aria-label="Select chromosome" onchange="filterChromosome()">
                    <option value="all" class="lang-en">All Chromosomes</option>
                    <option value="all" class="lang-zh">所有染色体</option>
                </select>
            </div>

            <!-- Track Length Control (only visible for single chromosome) -->
            <div id="trackLengthControl" class="track-control-bar">
                <div class="track-control-row">
                    <label for="trackLengthSlider" class="track-control-label">
                        <span class="lang-en">Track Length:</span>
                        <span class="lang-zh">轨道长度：</span>
                    </label>
                    <input type="range" id="trackLengthSlider" min="1000000" max="300000000" step="1000000"
                           oninput="updateTrackLength()">
                    <span id="trackLengthValue" class="track-control-value">50.00 Mb</span>
                </div>
            </div>

            <div class="section-body">
                <div id="chromVisualization">
                    <!-- Will be populated by JavaScript -->
                </div>

                <div class="legend">
                    <div class="legend-item">
                        <span class="legend-color" style="background: #e2e8f0;"></span>
                        <span class="lang-en">Normal sequence</span>
                        <span class="lang-zh">正常序列</span>
                    </div>
                    <div class="legend-item">
                        <span class="legend-color" style="background: #15803d;"></span>
                        <span class="lang-en">Filled gap</span>
                        <span class="lang-zh">已填补 gap</span>
                    </div>
                    <div class="legend-item">
                        <span class="legend-color" style="background: #b91c1c;"></span>
                        <span class="lang-en">Unfilled gap</span>
                        <span class="lang-zh">未填补 gap</span>
                    </div>
                </div>
                <p class="section-note" id="chromCoordinateNote" style="margin:8px 0 0;">
                    <span class="lang-en">Tracks use the original assembly coordinate frame; hover a gap for fill length and flank delta.</span>
                    <span class="lang-zh">轨道采用原始组装坐标系；悬停查看填补长度与末端变化。</span>
                </p>
            </div>
        </section>

        <!-- Gap Filling Tasks Card -->
        <section class="section">
            <div class="section-header">
                <h2><span class="lang-en">Gap Filling Tasks</span><span class="lang-zh">Gap 填补任务</span></h2>
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
            </div>
        </section>

        <!-- Secondary Coordinate & Diagnostics Drawers -->
        <div class="fold-panel">
            <details class="fold">
                <summary><span class="fold-title"><span class="lang-en">Remaining Gaps (Final Coordinates)</span><span class="lang-zh">剩余未填补 Gap（终版坐标）</span> <span id="remainingCount" class="muted num"></span></span></summary>
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
        <footer class="report-footer">
            <p>DEGAP · AutoGapfiller · <span class="num">{esc(current_time)}</span></p>
        </footer>
    </main>

    <!-- Tooltip -->
    <div class="tooltip" id="tooltip" role="tooltip"></div>

    <script>
        // Data from Python
        const summary = {js_summary};
        const gapsByChrom = {js_gaps_by_chrom};
        const preprocessingConfig = {js_preprocessing_config};
        const integrationConfig = {js_integration_config};

        // Current language
        let currentLang = 'en';

        function escapeHtml(value) {{
            return String(value ?? '')
                .replaceAll('&', '&amp;')
                .replaceAll('<', '&lt;')
                .replaceAll('>', '&gt;')
                .replaceAll('"', '&quot;')
                .replaceAll("'", '&#039;');
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

        // Format BP
        function formatBP(bp) {{
            const num = toFiniteNumber(bp);
            if (num === null) {{
                return '-';
            }}
            if (Math.abs(num) >= 1000000) {{
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
                    content += bilingualSpan(
                        `Type: ${{escapeHtml(gap.fill_type)}}`,
                        `类型：${{escapeHtml(gap.fill_type)}}`
                    );
                }}
            }} else {{
                content += bilingualSpan('Filled Sequence Length: -', '填补序列长度：-');
            }}

            return content;
        }}

        // Populate Reads Information (compact inline bar, hidden when absent)
        function populateReadsInfo() {{
            const bar = document.getElementById('readsInfoBar');
            if (!bar) return;

            if (!preprocessingConfig || Object.keys(preprocessingConfig).length === 0) {{
                bar.style.display = 'none';
                return;
            }}

            const dataType = String(preprocessingConfig.data_type || 'unknown');
            const hifiStats = preprocessingConfig.hifi_stats || {{}};
            const ontStats = preprocessingConfig.ont_stats || {{}};
            const items = [];

            const displayType = dataType.charAt(0).toUpperCase() + dataType.slice(1);
            items.push(`<span>${{bilingualSpan('Reads', '数据类型')}}: <b>${{escapeHtml(displayType)}}</b></span>`);

            if (hifiStats && Object.keys(hifiStats).length > 0) {{
                items.push(`<span class="num">HiFi <b>${{escapeHtml(formatNumber(hifiStats.Number || hifiStats.NumSeqs || 0))}}</b> (max ${{escapeHtml(formatBP(hifiStats.MaxLength || 0))}})</span>`);
            }}
            if (ontStats && Object.keys(ontStats).length > 0) {{
                items.push(`<span class="num">ONT <b>${{escapeHtml(formatNumber(ontStats.Number || ontStats.NumSeqs || 0))}}</b> (max ${{escapeHtml(formatBP(ontStats.MaxLength || 0))}})</span>`);
            }}
            const seedLength = preprocessingConfig.seed_length || 0;
            if (seedLength > 0) {{
                items.push(`<span class="num">${{bilingualSpan('Seed', 'Seed 长度')}}: <b>${{escapeHtml(formatBP(seedLength))}}</b></span>`);
            }}

            bar.innerHTML = items.join('');
            bar.style.display = items.length ? 'flex' : 'none';
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

        // Populate Gap Filling Tasks Table
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

                // Sort gaps by numeric genomic start then stable gap_id
                const sortedGaps = [...chromData.gaps].sort(compareGapsGenomic);

                sortedGaps.forEach(gap => {{
                    const region = `${{formatNumber(gap.gap_start)}} - ${{formatNumber(gap.gap_end)}}`;

                    // Merged status + connection type badge
                    let statusBadge;
                    if (gap.filled) {{
                        if (gap.fill_type === 'direct_connection') {{
                            statusBadge = '<span class="badge badge-yes" data-i18n-en="Filled · Direct" data-i18n-zh="已填补 · 直连">Filled · Direct</span>';
                        }} else if (gap.fill_type === 'extension') {{
                            statusBadge = '<span class="badge badge-yes" data-i18n-en="Filled · Ext" data-i18n-zh="已填补 · 延伸">Filled · Ext</span>';
                        }} else {{
                            statusBadge = '<span class="badge badge-yes" data-i18n-en="Filled" data-i18n-zh="已填补">Filled</span>';
                        }}
                    }} else {{
                        statusBadge = '<span class="badge badge-no" data-i18n-en="Unfilled" data-i18n-zh="未填补">Unfilled</span>';
                    }}

                    // Direction column (auto-hidden when uniform across all gaps)
                    const displayFlag = gap.report_direction || gap.fill_direction || 'none';
                    seenDirs.add(displayFlag);

                    const rounds = gap.filled && gap.rounds !== undefined && gap.rounds !== null ? gap.rounds : '-';

                    // Fill length - distinguish 0 bp, negative overlap trimming, and flank delta
                    const fillCell = formatFillLengthCell(gap);

                    // Details - View link to sub-task report
                    const linkFlag = gap.report_direction || (gap.filled && gap.fill_direction ? gap.fill_direction : 'left');
                    const reportFile = `${{chrom}}.${{gap.gap_id}}.${{linkFlag}}.html`;
                    const details = `<a class="table-link" href="${{escapeHtml(reportFile)}}" target="_blank" rel="noopener" title="View details for ${{escapeHtml(chrom)}} Gap ${{escapeHtml(gap.gap_id)}}" data-i18n-en="View" data-i18n-zh="查看">View</a>`;

                    html += `
                        <tr>
                            <td class="mono">${{escapeHtml(chrom)}}</td>
                            <td class="num">${{escapeHtml(gap.gap_id)}}</td>
                            <td class="num muted">${{escapeHtml(region)}}</td>
                            <td>${{statusBadge}}</td>
                            <td data-col="dir" class="mono">${{escapeHtml(displayFlag)}}</td>
                            <td class="num">${{escapeHtml(rounds)}}</td>
                            <td class="${{fillCell.className}}">${{fillCell.html}}</td>
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
                html = '<tr><td colspan="8" class="empty-state"><span class="lang-en">No gap filling tasks recorded</span><span class="lang-zh">暂无 Gap 填充任务记录</span></td></tr>';
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

                    html += `
                        <tr>
                            <td class="mono">${{escapeHtml(chrom)}}</td>
                            <td class="num">${{escapeHtml(item.gap.gap_id)}}</td>
                            <td class="num">${{escapeHtml(region)}}</td>
                        </tr>
                    `;
                    rowCount++;
                }});
            }});

            // If no unfilled gaps, show a message
            if (html === '') {{
                html = '<tr><td colspan="3" class="empty-state success"><span data-i18n-en="All gaps have been filled." data-i18n-zh="所有 gaps 已填充。">All gaps have been filled.</span></td></tr>';
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

        // Current track length for multi-row view
        let currentTrackLength = 0;

        // Draw Chromosome Visualization
        function drawChromVisualization(selectedChrom = 'all') {{
            const container = document.getElementById('chromVisualization');
            container.innerHTML = '';

            const chromNames = selectedChrom === 'all'
                ? Object.keys(gapsByChrom).sort()
                : [selectedChrom];

            if (chromNames.length === 0) {{
                container.innerHTML = '<div class="empty-state"><span class="lang-en">No chromosomes to display</span><span class="lang-zh">暂无可显示的染色体</span></div>';
                return;
            }}

            // Show/hide track length control
            const trackLengthControl = document.getElementById('trackLengthControl');
            if (selectedChrom !== 'all' && gapsByChrom[selectedChrom]) {{
                trackLengthControl.style.display = 'block';
                const chromData = gapsByChrom[selectedChrom];
                const chromLength = chromData.length;

                // Set slider range and default value
                const slider = document.getElementById('trackLengthSlider');
                slider.max = chromLength;
                slider.min = Math.min(1000000, chromLength); // 1 Mb minimum

                // Default: chromosome length / 5
                if (currentTrackLength === 0 || currentTrackLength > chromLength) {{
                    currentTrackLength = Math.floor(chromLength / 5);
                }}
                slider.value = currentTrackLength;
                updateTrackLengthDisplay(currentTrackLength);
            }} else {{
                trackLengthControl.style.display = 'none';
                currentTrackLength = 0;
            }}

            // Find max chromosome length for scaling
            let maxChromLength = 0;
            chromNames.forEach(chrom => {{
                const chromData = gapsByChrom[chrom];
                if (!chromData) return;
                const chromLength = chromData.length;
                if (chromLength > maxChromLength) {{
                    maxChromLength = chromLength;
                }}
            }});

            chromNames.forEach(chrom => {{
                const chromData = gapsByChrom[chrom];
                if (!chromData) return;
                const chromLength = chromData.length;

                // Multi-row view for single chromosome
                if (selectedChrom !== 'all' && currentTrackLength > 0) {{
                    drawMultiRowChromosome(chrom, chromData, chromLength, currentTrackLength, container);
                }} else {{
                    // Single row view for all chromosomes
                    drawSingleRowChromosome(chrom, chromData, chromLength, maxChromLength || 1, container);
                }}
            }});
        }}

        // Draw single row chromosome (for "All Chromosomes" view)
        function drawSingleRowChromosome(chrom, chromData, chromLength, maxChromLength, container) {{
            // Create chromosome track
            const trackDiv = document.createElement('div');
            trackDiv.className = 'chrom-track';

            // Header
            const headerDiv = document.createElement('div');
            headerDiv.className = 'chrom-track-header';
            headerDiv.innerHTML = `
                <span class="chrom-track-name">${{escapeHtml(chrom)}}</span>
                <span class="chrom-track-length">${{escapeHtml(formatBP(chromLength))}} (${{bilingualSpan('original coords', '原始坐标')}})</span>
            `;
            trackDiv.appendChild(headerDiv);

            // Bar container
            const barContainerDiv = document.createElement('div');
            barContainerDiv.className = 'chrom-track-bar-container';

            // Bar (scaled relative to max chromosome)
            const barDiv = document.createElement('div');
            barDiv.className = 'chrom-track-bar';
            const barWidth = (chromLength / maxChromLength * 100).toFixed(2);
            barDiv.style.width = barWidth + '%';

            barContainerDiv.appendChild(barDiv);

            // Calculate bar width percentage for gap positioning
            const barWidthPercent = (chromLength / maxChromLength * 100);

            // Add gap markers in genomic order using original assembly coordinates
            const sortedGaps = [...chromData.gaps].sort(compareGapsGenomic);
            sortedGaps.forEach((gap, index) => {{
                const placement = getOriginalTrackPlacement(gap);
                addGapMarker(barContainerDiv, gap, index, chromLength || 1, chrom, placement, false, barWidthPercent);
            }});

            trackDiv.appendChild(barContainerDiv);
            container.appendChild(trackDiv);
        }}

        // Draw multi-row chromosome (for single chromosome view)
        function drawMultiRowChromosome(chrom, chromData, chromLength, trackLength, container) {{
            const numRows = Math.ceil(chromLength / trackLength);
            const sortedGaps = [...chromData.gaps].sort(compareGapsGenomic);

            for (let row = 0; row < numRows; row++) {{
                const rowStart = row * trackLength;
                const rowEnd = Math.min((row + 1) * trackLength, chromLength);
                const rowLength = rowEnd - rowStart;

                // Create chromosome track
                const trackDiv = document.createElement('div');
                trackDiv.className = 'chrom-track chrom-track-multirow';

                // Header
                const headerDiv = document.createElement('div');
                headerDiv.className = 'chrom-track-header';
                headerDiv.innerHTML = `
                    <span class="chrom-track-name">${{escapeHtml(chrom)}} (Row ${{row + 1}}/${{numRows}})</span>
                    <span class="chrom-track-length">${{escapeHtml(formatBP(rowStart))}} - ${{escapeHtml(formatBP(rowEnd))}} (${{bilingualSpan('original', '原始坐标')}})</span>
                `;
                trackDiv.appendChild(headerDiv);

                // Bar container
                const barContainerDiv = document.createElement('div');
                barContainerDiv.className = 'chrom-track-bar-container';

                // Bar (width based on actual length, not full track length for last row)
                const barDiv = document.createElement('div');
                barDiv.className = 'chrom-track-bar';
                const barWidth = (rowLength / trackLength * 100).toFixed(2);
                barDiv.style.width = barWidth + '%';

                barContainerDiv.appendChild(barDiv);

                // Add gap markers for gaps whose 0-based original start falls in this row
                sortedGaps.forEach((gap, index) => {{
                    const placement = getOriginalTrackPlacement(gap, rowStart, rowEnd);
                    if (placement !== null) {{
                        addGapMarker(barContainerDiv, gap, index, trackLength, chrom, placement, true);
                    }}
                }});

                trackDiv.appendChild(barContainerDiv);
                container.appendChild(trackDiv);
            }}
        }}

        // Add gap marker to a bar container in original assembly coordinates
        function addGapMarker(barContainerDiv, gap, index, chromLength, chrom, placement = null, useVariableWidth = false, barWidthPercent = 100) {{
            const isTop = index % 2 === 0;
            const resolved = placement || getOriginalTrackPlacement(gap);

            const markerDiv = document.createElement('div');
            markerDiv.className = `gap-marker ${{isTop ? 'top' : 'bottom'}}`;
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

        // Update track length display
        function updateTrackLengthDisplay(length) {{
            const valueSpan = document.getElementById('trackLengthValue');
            valueSpan.textContent = formatBP(length);
        }}

        // Update track length from slider
        function updateTrackLength() {{
            const slider = document.getElementById('trackLengthSlider');
            currentTrackLength = parseInt(slider.value);
            updateTrackLengthDisplay(currentTrackLength);

            // Redraw visualization
            const select = document.getElementById('chromSelect');
            const selectedChrom = select.value;
            drawChromVisualization(selectedChrom);
        }}

        // Show tooltip
        function showTooltip(event, gap, chrom) {{
            const tooltip = document.getElementById('tooltip');
            tooltip.innerHTML = buildTooltipContent(gap, chrom);
            tooltip.style.display = 'block';
            tooltip.style.left = event.pageX + 10 + 'px';
            tooltip.style.top = event.pageY + 10 + 'px';
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
                    if (selectedChrom === 'all' || chromName === selectedChrom) {{
                        row.style.display = '';
                    }} else {{
                        row.style.display = 'none';
                    }}
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

        // Initialize
        document.addEventListener('DOMContentLoaded', () => {{
            populateReadsInfo();
            populateInitialGenomeTable();
            populateGapFillingTasksTable();
            populateFinalGenomeTable();
            populateChromSelector();
            drawChromVisualization();
            initChromFilters();
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

