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

            # 确定要复制的 flag
            if filled and fill_direction in ['left', 'right']:
                # 成功填充：复制成功的方向
                flag_to_copy = fill_direction
            else:
                # 失败：固定复制 left
                flag_to_copy = 'left'

            # 源文件路径
            source_report = gap_filling_dir / f"{chrom}.{gap_id}.{flag_to_copy}" / "visualization_output" / "gapfiller_report.html"

            # 目标文件路径
            target_report = self.output_dir / f"{chrom}.{gap_id}.{flag_to_copy}.html"

            # 复制文件
            if source_report.exists():
                try:
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
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 准备 JavaScript 数据
        js_summary = json.dumps(summary, indent=2)
        js_gaps_by_chrom = json.dumps(self.gaps_by_chrom, indent=2, default=str)
        js_preprocessing_config = json.dumps(self.preprocessing_config if self.preprocessing_config else {}, indent=2)
        js_integration_config = json.dumps(self.integration_config if self.integration_config else {}, indent=2)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoGapfiller - Gap Filling Report</title>
    <style>
        * {{
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh;
        }}

        .container {{
            max-width: 1180px;
            margin: 0 auto;
        }}

        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 24px;
            border-radius: 15px;
            margin-bottom: 30px;
            text-align: left;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }}

        .header-top {{
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 12px;
            flex-wrap: wrap;
        }}

        .header-info {{
            display: flex;
            flex-direction: column;
            gap: 6px;
        }}

        .header h1 {{
            margin: 0;
            font-size: 2.1em;
            font-weight: 600;
        }}

        .header p {{
            margin: 0;
            opacity: 0.9;
            font-size: 1.05em;
        }}

        .language-switcher {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-left: auto;
            align-self: flex-start;
        }}

        .language-btn {{
            background: rgba(255, 255, 255, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.3);
            color: #fff;
            padding: 6px 14px;
            border-radius: 18px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            min-width: 46px;
        }}

        .language-btn:hover {{
            background: rgba(255, 255, 255, 0.28);
            transform: translateY(-1px);
        }}

        .language-btn:active {{
            transform: translateY(0);
        }}

        .language-btn.active {{
            background: #fff;
            color: #667eea;
            box-shadow: 0 4px 10px rgba(0,0,0,0.15);
        }}

        .language-btn:focus {{
            outline: none;
            box-shadow: 0 0 0 2px rgba(255,255,255,0.6);
        }}

        .card {{
            background: white;
            border-radius: 15px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            margin-bottom: 30px;
            overflow: hidden;
        }}

        .card-header {{
            background: linear-gradient(135deg, #7889e0 0%, #9d87cc 100%);
            color: #fff;
            padding: 15px 25px;
            font-size: 1.2em;
            font-weight: 600;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #e9ecef;
        }}

        .card-content {{
            padding: 25px;
        }}

        .table-container {{
            max-height: 400px;
            overflow-y: auto;
            border: 1px solid #dee2e6;
            border-radius: 10px;
            background: white;
            margin-bottom: 20px;
        }}

        .table-container-limited {{
            max-height: 400px;
            overflow-y: auto;
            border: 1px solid #dee2e6;
            border-radius: 10px;
            background: white;
            position: relative;
        }}

        .table-container-limited.expanded {{
            max-height: none;
            overflow-y: visible;
        }}

        .table-toggle-container {{
            position: sticky;
            bottom: 0;
            width: 100%;
            display: flex;
            justify-content: flex-end;
            padding: 6px 8px;
            background: linear-gradient(180deg, rgba(255,255,255,0), rgba(255,255,255,0.95));
            border-top: 1px solid #e9ecef;
        }}

        .table-toggle-btn {{
            background: #667eea;
            color: #fff;
            border: none;
            border-radius: 16px;
            padding: 6px 12px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            box-shadow: 0 2px 6px rgba(0,0,0,0.1);
        }}

        .table-toggle-btn:hover {{
            background: #5a6fd8;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
        }}

        /* Key-Value table style (like TelSeeker) */
        .kv {{
            width: 100%;
            border-collapse: collapse;
        }}

        .kv td {{
            padding: 8px 10px;
            border-bottom: 1px solid #eee;
        }}

        .kv td:first-child {{
            width: 220px;
            color: #34495e;
            font-weight: 600;
            background: #fafbff;
        }}

        thead {{
            position: sticky;
            top: 0;
            background: #f8f9fa;
            z-index: 10;
        }}

        .table-container-limited thead, .table-container thead {{
            position: sticky;
            top: 0;
            z-index: 15;
        }}

        th {{
            padding: 12px;
            text-align: left;
            font-weight: 600;
            color: #495057;
            border-bottom: 2px solid #dee2e6;
        }}

        td {{
            padding: 10px 12px;
            border-bottom: 1px solid #dee2e6;
        }}

        tr:hover {{
            background: #f8f9fa;
        }}

        .badge {{
            padding: 6px 12px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.9em;
            display: inline-block;
        }}

        .badge-yes {{
            background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
            color: #155724;
        }}

        .badge-no {{
            background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%);
            color: #721c24;
        }}

        .badge-direct {{
            background: linear-gradient(135deg, #cce5ff 0%, #b3d9ff 100%);
            color: #004085;
        }}

        .badge-extension {{
            background: linear-gradient(135deg, #d1ecf1 0%, #bee5eb 100%);
            color: #0c5460;
        }}

        .badge-na {{
            background: linear-gradient(135deg, #e9ecef 0%, #dee2e6 100%);
            color: #495057;
        }}

        .chrom-filter-icon {{
            display: inline-block;
            margin-left: 6px;
            cursor: pointer;
            font-size: 0.75em;
            color: #adb5bd;
            position: relative;
            user-select: none;
            vertical-align: middle;
        }}

        .chrom-filter-icon:hover {{
            color: #495057;
        }}

        .chrom-filter-menu {{
            display: none;
            position: absolute;
            top: 100%;
            left: 0;
            background: white;
            border: 1px solid #dee2e6;
            border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 1000;
            min-width: 150px;
            max-height: 300px;
            overflow-y: auto;
            margin-top: 4px;
        }}

        .chrom-filter-menu.show {{
            display: block;
        }}

        .chrom-filter-item {{
            padding: 8px 12px;
            cursor: pointer;
            font-size: 0.9em;
            font-weight: normal;
            color: #495057;
            border-bottom: 1px solid #f0f1f3;
        }}

        .chrom-filter-item:last-child {{
            border-bottom: none;
        }}

        .chrom-filter-item:hover {{
            background: #f8f9fa;
        }}

        .chrom-filter-item.active {{
            background: #e7f1ff;
            color: #0056b3;
            font-weight: 600;
        }}

        .success {{
            color: #28a745;
            font-weight: 600;
        }}

        .failed {{
            color: #dc3545;
            font-weight: 600;
        }}

        .fill-type-stats {{
            margin-top: 20px;
        }}

        .fill-type-stats h3 {{
            margin-top: 0;
            color: #495057;
        }}

        .stat-item {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 8px;
            margin: 8px 0;
        }}

        .stat-icon {{
            font-size: 1.5em;
        }}

        .view-btn {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 6px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9em;
            font-weight: 500;
            transition: all 0.3s ease;
            box-shadow: 0 2px 4px rgba(102, 126, 234, 0.2);
        }}

        .view-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(102, 126, 234, 0.3);
        }}

        .view-btn:active {{
            transform: translateY(0);
        }}

        .chrom-selector {{
            background: rgba(255, 255, 255, 0.95);
            border: 1px solid rgba(255, 255, 255, 0.5);
            color: #495057;
            padding: 6px 32px 6px 12px;
            border-radius: 18px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            appearance: none;
            background-image: url('data:image/svg+xml;charset=US-ASCII,%3Csvg%20width%3D%2214%22%20height%3D%228%22%20viewBox%3D%220%200%2014%208%22%20fill%3D%22none%22%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%3E%3Cpath%20d%3D%22M1%201L7%207L13%201%22%20stroke%3D%22%23495057%22%20stroke-width%3D%222%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22/%3E%3C/svg%3E');
            background-repeat: no-repeat;
            background-position: right 10px center;
            min-width: 180px;
        }}

        .chrom-selector:hover {{
            background: rgba(255, 255, 255, 1);
            border-color: rgba(255, 255, 255, 0.7);
            transform: translateY(-1px);
        }}

        .chrom-selector:focus {{
            outline: none;
            box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.6);
        }}

        .chrom-selector option {{
            background: white;
            color: #495057;
        }}

        #chromVisualization {{
            margin: 20px 0;
            min-height: 300px;
        }}

        .chrom-track {{
            margin-bottom: 40px;
            padding-bottom: 30px;
            border-bottom: 2px solid #dee2e6;
        }}

        .chrom-track:last-child {{
            border-bottom: none;
        }}

        .chrom-track-multirow {{
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid #e9ecef;
        }}

        .chrom-track-multirow:last-child {{
            border-bottom: none;
        }}

        .chrom-track-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding: 0 10px;
        }}

        .chrom-track-name {{
            font-weight: 600;
            font-size: 16px;
            color: #495057;
        }}

        .chrom-track-length {{
            font-size: 14px;
            color: #6c757d;
        }}

        /* Track length slider styling */
        input[type="range"] {{
            -webkit-appearance: none;
            appearance: none;
            height: 6px;
            background: #d3d3d3;
            border-radius: 3px;
            outline: none;
        }}

        input[type="range"]::-webkit-slider-thumb {{
            -webkit-appearance: none;
            appearance: none;
            width: 18px;
            height: 18px;
            background: #28a745;
            border-radius: 50%;
            cursor: pointer;
        }}

        input[type="range"]::-moz-range-thumb {{
            width: 18px;
            height: 18px;
            background: #28a745;
            border-radius: 50%;
            cursor: pointer;
            border: none;
        }}

        .chrom-track-bar-container {{
            position: relative;
            height: 80px;
            padding: 20px 0;
        }}

        .chrom-track-bar {{
            position: relative;
            height: 20px;
            background: linear-gradient(to bottom, #d0d5dd 0%, #e9ecef 50%, #d0d5dd 100%);
            border-radius: 10px;
            box-shadow: inset 0 1px 3px rgba(0,0,0,0.1);
        }}

        .gap-marker {{
            position: absolute;
            transform: translateX(-50%);
            cursor: pointer;
        }}

        .gap-marker.top {{
            top: 0;
            height: 50%;
        }}

        .gap-marker.bottom {{
            top: 25%;
            height: 50%;
        }}

        /* Gap marker line - default fixed width for single-row view */
        .gap-marker-line {{
            width: 2px;
            height: 100%;
            margin: 0 auto;
        }}

        /* Gap region - variable width for multi-row view */
        .gap-marker.has-width {{
            transform: none;
        }}

        .gap-marker.has-width .gap-marker-line {{
            width: 100%;
            margin: 0;
        }}

        .gap-marker.has-width .gap-marker-label {{
            left: 50%;
            transform: translateX(-50%);
        }}

        .gap-marker-line.filled {{
            background: #28a745;
        }}

        .gap-marker-line.unfilled {{
            background: #dc3545;
        }}

        .gap-marker-label {{
            position: absolute;
            left: 50%;
            transform: translateX(-50%);
            font-size: 11px;
            font-weight: 600;
            white-space: nowrap;
            cursor: pointer;
        }}

        .gap-marker-label.top {{
            bottom: 100%;
            margin-bottom: 4px;
        }}

        .gap-marker-label.bottom {{
            top: 100%;
            margin-top: 4px;
        }}

        .gap-marker-label.filled {{
            color: #28a745;
        }}

        .gap-marker-label.unfilled {{
            color: #dc3545;
        }}

        .gap-marker:hover .gap-marker-label {{
            font-weight: 700;
        }}

        .legend {{
            display: flex;
            gap: 20px;
            margin-top: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .legend-color {{
            width: 30px;
            height: 20px;
            border-radius: 4px;
        }}

        .tooltip {{
            position: absolute;
            background: rgba(0, 0, 0, 0.9);
            color: white;
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 12px;
            pointer-events: none;
            z-index: 1000;
            display: none;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <div class="header-top">
                <div class="header-info">
                    <h1>🧬 AutoGapfiller</h1>
                    <p class="lang-en">Gap Filling Visualization Report</p>
                    <p class="lang-zh" style="display:none;">Gap 填充可视化报告</p>
                    <p style="opacity: 0.8; font-size: 0.95em;">{current_time}</p>
                </div>
                <div class="language-switcher">
                    <button class="language-btn active" onclick="switchLanguage('en')">EN</button>
                    <button class="language-btn" onclick="switchLanguage('zh')">中文</button>
                </div>
            </div>
        </div>

        <!-- Reads Information Card -->
        <div class="card">
            <div class="card-header">
                <span class="lang-en">📊 Reads Information</span>
                <span class="lang-zh" style="display:none;">📊 Reads 信息</span>
            </div>
            <div class="card-content">
                <table class="kv" id="readsInfoTable">
                    <!-- Will be populated by JavaScript -->
                </table>
            </div>
        </div>

        <!-- Initial Genome Overview Card -->
        <div class="card">
            <div class="card-header">
                <span class="lang-en">📊 Initial Genome Overview</span>
                <span class="lang-zh" style="display:none;">📊 初始基因组概览</span>
            </div>
            <div class="card-content">
                <div id="initial-table-container" class="table-container-limited">
                    <table id="initialGenomeTable">
                        <thead>
                            <tr>
                                <th class="lang-en">
                                    Chromosome
                                    <span class="chrom-filter-icon" onclick="toggleFilterMenu('initial', event)">
                                        ▼
                                        <div id="initial-chrom-filter" class="chrom-filter-menu"></div>
                                    </span>
                                </th>
                                <th class="lang-zh" style="display:none;">
                                    染色体
                                    <span class="chrom-filter-icon" onclick="toggleFilterMenu('initial', event)">
                                        ▼
                                        <div id="initial-chrom-filter-zh" class="chrom-filter-menu"></div>
                                    </span>
                                </th>
                                <th class="lang-en">Gap ID</th>
                                <th class="lang-zh" style="display:none;">Gap ID</th>
                                <th class="lang-en">Region</th>
                                <th class="lang-zh" style="display:none;">区域</th>
                            </tr>
                        </thead>
                        <tbody id="initialGenomeTableBody">
                            <!-- Will be populated by JavaScript -->
                        </tbody>
                    </table>
                    <div class="table-toggle-container">
                        <button id="initial-toggle-btn" class="table-toggle-btn" onclick="toggleTableExpand('initial')"><span class="lang-en">Expand</span><span class="lang-zh" style="display:none;">展开</span></button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Gap Filling Tasks Card -->
        <div class="card">
            <div class="card-header">
                <span class="lang-en">🔧 Gap Filling Tasks</span>
                <span class="lang-zh" style="display:none;">🔧 Gap 填充任务</span>
            </div>
            <div class="card-content">
                <div id="tasks-table-container" class="table-container-limited">
                    <table id="gapFillingTasksTable">
                        <thead>
                            <tr>
                                <th class="lang-en">
                                    Chromosome
                                    <span class="chrom-filter-icon" onclick="toggleFilterMenu('tasks', event)">
                                        ▼
                                        <div id="tasks-chrom-filter" class="chrom-filter-menu"></div>
                                    </span>
                                </th>
                                <th class="lang-zh" style="display:none;">
                                    染色体
                                    <span class="chrom-filter-icon" onclick="toggleFilterMenu('tasks', event)">
                                        ▼
                                        <div id="tasks-chrom-filter-zh" class="chrom-filter-menu"></div>
                                    </span>
                                </th>
                                <th class="lang-en">Gap ID</th>
                                <th class="lang-zh" style="display:none;">Gap ID</th>
                                <th class="lang-en">Extended</th>
                                <th class="lang-zh" style="display:none;">是否延伸</th>
                                <th class="lang-en">Connection Type</th>
                                <th class="lang-zh" style="display:none;">连接类型</th>
                                <th class="lang-en">Flag</th>
                                <th class="lang-zh" style="display:none;">Flag</th>
                                <th class="lang-en">Rounds</th>
                                <th class="lang-zh" style="display:none;">轮次数量</th>
                                <th class="lang-en">Fill Length</th>
                                <th class="lang-zh" style="display:none;">填补长度</th>
                                <th class="lang-en">Details</th>
                                <th class="lang-zh" style="display:none;">详情</th>
                            </tr>
                        </thead>
                        <tbody id="gapFillingTasksTableBody">
                            <!-- Will be populated by JavaScript -->
                        </tbody>
                    </table>
                    <div class="table-toggle-container">
                        <button id="tasks-toggle-btn" class="table-toggle-btn" onclick="toggleTableExpand('tasks')"><span class="lang-en">Expand</span><span class="lang-zh" style="display:none;">展开</span></button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Final Integrated Genome Card -->
        <div class="card">
            <div class="card-header">
                <span class="lang-en">✅ Final Integrated Genome</span>
                <span class="lang-zh" style="display:none;">✅ 最终整合基因组</span>
            </div>
            <div class="card-content">
                <div id="final-table-container" class="table-container-limited">
                    <table id="finalGenomeTable">
                        <thead>
                            <tr>
                                <th class="lang-en">
                                    Chromosome
                                    <span class="chrom-filter-icon" onclick="toggleFilterMenu('final', event)">
                                        ▼
                                        <div id="final-chrom-filter" class="chrom-filter-menu"></div>
                                    </span>
                                </th>
                                <th class="lang-zh" style="display:none;">
                                    染色体
                                    <span class="chrom-filter-icon" onclick="toggleFilterMenu('final', event)">
                                        ▼
                                        <div id="final-chrom-filter-zh" class="chrom-filter-menu"></div>
                                    </span>
                                </th>
                                <th class="lang-en">Gap ID</th>
                                <th class="lang-zh" style="display:none;">Gap ID</th>
                                <th class="lang-en">Region</th>
                                <th class="lang-zh" style="display:none;">区域</th>
                            </tr>
                        </thead>
                        <tbody id="finalGenomeTableBody">
                            <!-- Will be populated by JavaScript -->
                        </tbody>
                    </table>
                    <div class="table-toggle-container">
                        <button id="final-toggle-btn" class="table-toggle-btn" onclick="toggleTableExpand('final')"><span class="lang-en">Expand</span><span class="lang-zh" style="display:none;">展开</span></button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Chromosome Visualization Card -->
        <div class="card">
            <div class="card-header">
                <span class="lang-en">🧬 Chromosome Visualization</span>
                <span class="lang-zh" style="display:none;">🧬 染色体可视化</span>
                <select id="chromSelect" class="chrom-selector" onchange="filterChromosome()">
                    <option value="all" class="lang-en">All Chromosomes</option>
                    <option value="all" class="lang-zh" style="display:none;">所有染色体</option>
                </select>
            </div>

            <!-- Track Length Control (only visible for single chromosome) -->
            <div id="trackLengthControl" style="display: none; padding: 15px 20px; background: #f8f9fa; border-bottom: 1px solid #e0e0e0;">
                <div style="display: flex; align-items: center; gap: 15px;">
                    <label style="font-weight: 600; color: #495057; min-width: 120px;">
                        <span class="lang-en">Track Length:</span>
                        <span class="lang-zh" style="display:none;">轨道长度:</span>
                    </label>
                    <input type="range" id="trackLengthSlider" min="1000000" max="300000000" step="1000000"
                           style="flex: 1;" oninput="updateTrackLength()">
                    <span id="trackLengthValue" style="font-weight: 600; color: #28a745; min-width: 100px; text-align: right;">50.00 Mb</span>
                </div>
            </div>

            <div class="card-content">
                <div id="chromVisualization">
                    <!-- Will be populated by JavaScript -->
                </div>

                <div class="legend">
                    <div class="legend-item">
                        <span class="legend-color" style="background: #e9ecef;"></span>
                        <span class="lang-en">Normal sequence</span>
                        <span class="lang-zh" style="display:none;">正常序列</span>
                    </div>
                    <div class="legend-item">
                        <span class="legend-color" style="background: #28a745;"></span>
                        <span class="lang-en">Filled gap</span>
                        <span class="lang-zh" style="display:none;">已填充 gap</span>
                    </div>
                    <div class="legend-item">
                        <span class="legend-color" style="background: #dc3545;"></span>
                        <span class="lang-en">Unfilled gap</span>
                        <span class="lang-zh" style="display:none;">未填充 gap</span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Tooltip -->
    <div class="tooltip" id="tooltip"></div>

    <script>
        // Data from Python
        const summary = {js_summary};
        const gapsByChrom = {js_gaps_by_chrom};
        const preprocessingConfig = {js_preprocessing_config};
        const integrationConfig = {js_integration_config};

        // Current language
        let currentLang = 'en';

        // Language switching
        function switchLanguage(lang) {{
            currentLang = lang;

            // Update button states
            document.querySelectorAll('.language-btn').forEach(btn => {{
                btn.classList.remove('active');
            }});
            event.target.classList.add('active');

            // Show/hide elements
            if (lang === 'en') {{
                document.querySelectorAll('.lang-en').forEach(el => el.style.display = '');
                document.querySelectorAll('.lang-zh').forEach(el => el.style.display = 'none');
            }} else {{
                document.querySelectorAll('.lang-en').forEach(el => el.style.display = 'none');
                document.querySelectorAll('.lang-zh').forEach(el => el.style.display = '');
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

            // Update button text based on current language
            if (currentLang === 'en') {{
                btn.innerHTML = expanded ? '<span class="lang-en">Collapse</span><span class="lang-zh" style="display:none;">收起</span>' : '<span class="lang-en">Expand</span><span class="lang-zh" style="display:none;">展开</span>';
            }} else {{
                btn.innerHTML = expanded ? '<span class="lang-en" style="display:none;">Collapse</span><span class="lang-zh">收起</span>' : '<span class="lang-en" style="display:none;">Expand</span><span class="lang-zh">展开</span>';
            }}
        }}

        // Format number with commas
        function formatNumber(num) {{
            return num.toString().replace(/\\B(?=(\\d{{3}})+(?!\\d))/g, ",");
        }}

        // Format BP
        function formatBP(bp) {{
            if (Math.abs(bp) >= 1000000) {{
                return (bp / 1000000).toFixed(2) + ' Mb';
            }} else if (Math.abs(bp) >= 1000) {{
                return (bp / 1000).toFixed(2) + ' Kb';
            }} else {{
                return bp + ' bp';
            }}
        }}

        // Populate Reads Information
        function populateReadsInfo() {{
            const table = document.getElementById('readsInfoTable');

            if (!preprocessingConfig || Object.keys(preprocessingConfig).length === 0) {{
                table.innerHTML = '<tr><td colspan="2" style="color: #6c757d; text-align: center;">No reads information available</td></tr>';
                return;
            }}

            const dataType = preprocessingConfig.data_type || 'unknown';
            const hifiStats = preprocessingConfig.hifi_stats || {{}};
            const ontStats = preprocessingConfig.ont_stats || {{}};

            let html = '';

            // Data Type
            html += `
                <tr>
                    <td><span class="lang-en">Data Type</span><span class="lang-zh" style="display:none;">数据类型</span></td>
                    <td>${{dataType.charAt(0).toUpperCase() + dataType.slice(1)}}</td>
                </tr>
            `;

            // HiFi Stats
            if (hifiStats && Object.keys(hifiStats).length > 0) {{
                html += `
                    <tr>
                        <td>HiFi Reads</td>
                        <td>${{formatNumber(hifiStats.Number || hifiStats.NumSeqs || 0)}} reads</td>
                    </tr>
                    <tr>
                        <td>HiFi Max Length</td>
                        <td>${{formatNumber(hifiStats.MaxLength || 0)}} bp</td>
                    </tr>
                `;
            }}

            // ONT Stats
            if (ontStats && Object.keys(ontStats).length > 0) {{
                html += `
                    <tr>
                        <td>ONT Reads</td>
                        <td>${{formatNumber(ontStats.Number || ontStats.NumSeqs || 0)}} reads</td>
                    </tr>
                    <tr>
                        <td>ONT Max Length</td>
                        <td>${{formatNumber(ontStats.MaxLength || 0)}} bp</td>
                    </tr>
                `;
            }}

            // Seed Length - use unified seed_length (max of HiFi and ONT)
            const seedLength = preprocessingConfig.seed_length || 0;
            if (seedLength > 0) {{
                html += `
                    <tr>
                        <td><span class="lang-en">Seed Length</span><span class="lang-zh" style="display:none;">Seed 长度</span></td>
                        <td>${{formatNumber(seedLength)}} bp</td>
                    </tr>
                `;
            }}

            table.innerHTML = html;
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

                // Sort gaps by gap_id
                const sortedGaps = chromData.gaps.sort((a, b) => a.gap_id - b.gap_id);

                sortedGaps.forEach(gap => {{
                    const region = `${{formatNumber(gap.gap_start)}} - ${{formatNumber(gap.gap_end)}}`;

                    html += `
                        <tr>
                            <td>${{chrom}}</td>
                            <td>${{gap.gap_id}}</td>
                            <td>${{region}}</td>
                        </tr>
                    `;
                    rowCount++;
                }});
            }});

            tbody.innerHTML = html;

            // Show/hide toggle button based on row count (show if >= 6 rows)
            const toggleContainer = document.querySelector('#initial-table-container .table-toggle-container');
            if (rowCount >= 6) {{
                toggleContainer.style.display = 'flex';
            }} else {{
                toggleContainer.style.display = 'none';
            }}
        }}

        // Populate Gap Filling Tasks Table
        function populateGapFillingTasksTable() {{
            const tbody = document.getElementById('gapFillingTasksTableBody');

            let html = '';
            let rowCount = 0;

            // Sort chromosomes
            const chromNames = Object.keys(gapsByChrom).sort();

            chromNames.forEach(chrom => {{
                const chromData = gapsByChrom[chrom];

                // Sort gaps by gap_id
                const sortedGaps = chromData.gaps.sort((a, b) => a.gap_id - b.gap_id);

                sortedGaps.forEach(gap => {{
                    // Extended - use badge style
                    const extended = gap.filled ?
                        '<span class="badge badge-yes" data-i18n-en="Yes" data-i18n-zh="是">Yes</span>' :
                        '<span class="badge badge-no" data-i18n-en="No" data-i18n-zh="否">No</span>';

                    // Connection Type - use badge style
                    let connectionType = '<span class="badge badge-na">-</span>';
                    if (gap.filled) {{
                        if (gap.fill_type === 'extension') {{
                            connectionType = '<span class="badge badge-extension" data-i18n-en="Extension" data-i18n-zh="延伸">Extension</span>';
                        }} else if (gap.fill_type === 'direct_connection') {{
                            connectionType = '<span class="badge badge-direct" data-i18n-en="Direct" data-i18n-zh="直连">Direct</span>';
                        }}
                    }}

                    // Flag column - show fill_direction (left/right/none)
                    const displayFlag = gap.fill_direction || 'none';

                    const rounds = gap.filled ? gap.rounds : '-';

                    // Fill length - show formatted BP if filled
                    const fillLength = gap.filled && gap.fill_length ?
                        formatBP(gap.fill_length) : '-';

                    // Details - View link to sub-task report
                    // For filled gaps: use fill_direction, for unfilled: use 'left'
                    const linkFlag = gap.filled && gap.fill_direction ? gap.fill_direction : 'left';
                    const reportFile = `${{chrom}}.${{gap.gap_id}}.${{linkFlag}}.html`;
                    const details = `<a href="${{reportFile}}" target="_blank" title="View details for ${{chrom}} Gap ${{gap.gap_id}}" data-i18n-en="View" data-i18n-zh="查看">View</a>`;

                    html += `
                        <tr>
                            <td>${{chrom}}</td>
                            <td>${{gap.gap_id}}</td>
                            <td>${{extended}}</td>
                            <td>${{connectionType}}</td>
                            <td>${{displayFlag}}</td>
                            <td>${{rounds}}</td>
                            <td class="success">${{fillLength}}</td>
                            <td>${{details}}</td>
                        </tr>
                    `;
                    rowCount++;
                }});
            }});

            tbody.innerHTML = html;

            // Show/hide toggle button based on row count (show if >= 6 rows)
            const toggleContainer = document.querySelector('#tasks-table-container .table-toggle-container');
            if (rowCount >= 6) {{
                toggleContainer.style.display = 'flex';
            }} else {{
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

                // Sort all gaps by gap_id
                const allGaps = chromData.gaps.sort((a, b) => a.gap_id - b.gap_id);

                // Calculate position offset based on filled gaps
                let positionOffset = 0;

                allGaps.forEach(gap => {{
                    if (!gap.filled) {{
                        // This gap still exists in the final genome
                        // Calculate new position by adding offset from all previous filled gaps
                        const newStart = gap.gap_start + positionOffset;
                        const newEnd = gap.gap_end + positionOffset;
                        const region = `${{formatNumber(newStart)}} - ${{formatNumber(newEnd)}}`;

                        html += `
                            <tr>
                                <td>${{chrom}}</td>
                                <td>${{gap.gap_id}}</td>
                                <td>${{region}}</td>
                            </tr>
                        `;
                        rowCount++;
                    }} else {{
                        // This gap was filled, update offset for subsequent gaps
                        // Offset = fill_length - original_gap_length
                        const originalGapLen = gap.gap_end - gap.gap_start;
                        const fillLength = gap.fill_length || 0;
                        positionOffset += (fillLength - originalGapLen);
                    }}
                }});
            }});

            // If no unfilled gaps, show a message
            if (html === '') {{
                html = '<tr><td colspan="3" style="text-align: center; color: #28a745; font-weight: 600;"><span data-i18n-en="🎉 All gaps have been filled!" data-i18n-zh="🎉 所有 gaps 已填充！">🎉 All gaps have been filled!</span></td></tr>';
            }}

            tbody.innerHTML = html;

            // Show/hide toggle button based on row count (show if >= 6 rows)
            const toggleContainer = document.querySelector('#final-table-container .table-toggle-container');
            if (rowCount >= 6) {{
                toggleContainer.style.display = 'flex';
            }} else {{
                toggleContainer.style.display = 'none';
            }}
        }}

        // Populate Chromosome Selector
        function populateChromSelector() {{
            const select = document.getElementById('chromSelect');
            let selectHtml = '<option value="all">All Chromosomes</option>';

            // Sort chromosomes
            const chromNames = Object.keys(gapsByChrom).sort();

            chromNames.forEach(chrom => {{
                selectHtml += `<option value="${{chrom}}">${{chrom}}</option>`;
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

            // Show/hide track length control
            const trackLengthControl = document.getElementById('trackLengthControl');
            if (selectedChrom !== 'all') {{
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
                const chromLength = chromData.length;
                if (chromLength > maxChromLength) {{
                    maxChromLength = chromLength;
                }}
            }});

            chromNames.forEach(chrom => {{
                const chromData = gapsByChrom[chrom];
                const chromLength = chromData.length;

                // Multi-row view for single chromosome
                if (selectedChrom !== 'all' && currentTrackLength > 0) {{
                    drawMultiRowChromosome(chrom, chromData, chromLength, currentTrackLength, container);
                }} else {{
                    // Single row view for all chromosomes
                    drawSingleRowChromosome(chrom, chromData, chromLength, maxChromLength, container);
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
                <span class="chrom-track-name">${{chrom}}</span>
                <span class="chrom-track-length">${{formatBP(chromLength)}}</span>
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

            // Add gap markers
            chromData.gaps.forEach((gap, index) => {{
                addGapMarker(barContainerDiv, gap, index, chromLength, chrom, null, false, barWidthPercent);
            }});

            trackDiv.appendChild(barContainerDiv);
            container.appendChild(trackDiv);
        }}

        // Draw multi-row chromosome (for single chromosome view)
        function drawMultiRowChromosome(chrom, chromData, chromLength, trackLength, container) {{
            const numRows = Math.ceil(chromLength / trackLength);

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
                    <span class="chrom-track-name">${{chrom}} (Row ${{row + 1}}/${{numRows}})</span>
                    <span class="chrom-track-length">${{formatBP(rowStart)}} - ${{formatBP(rowEnd)}}</span>
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

                // Add gap markers for gaps in this row
                chromData.gaps.forEach((gap, index) => {{
                    if (gap.gap_start >= rowStart && gap.gap_start < rowEnd) {{
                        // Calculate position relative to this row
                        const relativePosition = gap.gap_start - rowStart;
                        addGapMarker(barContainerDiv, gap, index, trackLength, chrom, relativePosition, true);
                    }}
                }});

                trackDiv.appendChild(barContainerDiv);
                container.appendChild(trackDiv);
            }}
        }}

        // Add gap marker to a bar container
        function addGapMarker(barContainerDiv, gap, index, chromLength, chrom, customPosition = null, useVariableWidth = false, barWidthPercent = 100) {{
            const isTop = index % 2 === 0;

            const markerDiv = document.createElement('div');
            markerDiv.className = `gap-marker ${{isTop ? 'top' : 'bottom'}}`;

            // Position based on gap_start (or custom position for multi-row)
            const gapPosition = customPosition !== null ? customPosition : gap.gap_start;

            if (useVariableWidth) {{
                // Multi-row view: draw gap as a region with width
                // Use fill_length for filled gaps, gap_len for unfilled gaps
                let gapDisplayLength;
                if (gap.filled && gap.fill_length > 0) {{
                    // Filled gap: use fill_length (extended length)
                    gapDisplayLength = gap.fill_length;
                }} else {{
                    // Unfilled gap or direct connection (negative): use original gap_len
                    gapDisplayLength = gap.gap_len;
                }}

                const gapWidthPercent = (gapDisplayLength / chromLength * 100);
                const minWidthPercent = 0.1; // Minimum 0.1% width to ensure visibility
                const finalWidthPercent = Math.max(gapWidthPercent, minWidthPercent);

                markerDiv.classList.add('has-width');
                markerDiv.style.left = (gapPosition / chromLength * 100).toFixed(2) + '%';
                markerDiv.style.width = finalWidthPercent.toFixed(2) + '%';
            }} else {{
                // Single-row view: draw gap as a line
                // Position gap relative to the bar's actual width, not the full container
                const gapPositionInBar = (gapPosition / chromLength * 100);
                const finalPosition = gapPositionInBar * barWidthPercent / 100;
                markerDiv.style.left = finalPosition.toFixed(2) + '%';
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
            const status = gap.filled ? 'Filled' : 'Unfilled';
            const statusZh = gap.filled ? '已填充' : '未填充';

            let content = `
                <strong>${{chrom}}.gap${{gap.gap_id}}</strong><br>
                <span class="lang-en">Status: ${{status}}</span>
                <span class="lang-zh" style="display:none;">状态: ${{statusZh}}</span><br>
                <span class="lang-en">Position: ${{formatNumber(gap.gap_start)}} - ${{formatNumber(gap.gap_end)}}</span>
                <span class="lang-zh" style="display:none;">位置: ${{formatNumber(gap.gap_start)}} - ${{formatNumber(gap.gap_end)}}</span><br>
                <span class="lang-en">Initial Length: ${{formatBP(gap.gap_len)}}</span>
                <span class="lang-zh" style="display:none;">初始长度: ${{formatBP(gap.gap_len)}}</span><br>
            `;

            // Extended length (only for filled gaps)
            if (gap.filled && gap.fill_length > 0) {{
                content += `
                    <span class="lang-en">Extended Length: ${{formatBP(gap.fill_length)}}</span>
                    <span class="lang-zh" style="display:none;">延伸后长度: ${{formatBP(gap.fill_length)}}</span><br>
                `;
            }} else {{
                content += `
                    <span class="lang-en">Extended Length: -</span>
                    <span class="lang-zh" style="display:none;">延伸后长度: -</span><br>
                `;
            }}

            if (gap.filled) {{
                content += `<span class="lang-en">Type: ${{gap.fill_type}}</span>`;
                content += `<span class="lang-zh" style="display:none;">类型: ${{gap.fill_type}}</span>`;
            }}

            tooltip.innerHTML = content;
            tooltip.style.display = 'block';
            tooltip.style.left = event.pageX + 10 + 'px';
            tooltip.style.top = event.pageY + 10 + 'px';

            // Update language display
            if (currentLang === 'zh') {{
                tooltip.querySelectorAll('.lang-en').forEach(el => el.style.display = 'none');
                tooltip.querySelectorAll('.lang-zh').forEach(el => el.style.display = '');
            }}
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

        function initChromFilters() {{
            const chromNames = Object.keys(gapsByChrom).sort();

            // Initialize filters for all three tables
            ['initial', 'tasks', 'final'].forEach(tableType => {{
                // English filter
                const containerEn = document.getElementById(`${{tableType}}-chrom-filter`);
                let htmlEn = '<div class="chrom-filter-item active" onclick="selectChrom(\\'${{tableType}}\\', \\'all\\')">All</div>';
                chromNames.forEach(chrom => {{
                    htmlEn += `<div class="chrom-filter-item" onclick="selectChrom('${{tableType}}', '${{chrom}}')">${{chrom}}</div>`;
                }});
                containerEn.innerHTML = htmlEn;

                // Chinese filter
                const containerZh = document.getElementById(`${{tableType}}-chrom-filter-zh`);
                let htmlZh = '<div class="chrom-filter-item active" onclick="selectChrom(\\'${{tableType}}\\', \\'all\\')">全部</div>';
                chromNames.forEach(chrom => {{
                    htmlZh += `<div class="chrom-filter-item" onclick="selectChrom('${{tableType}}', '${{chrom}}')">${{chrom}}</div>`;
                }});
                containerZh.innerHTML = htmlZh;
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

