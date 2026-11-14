#!/usr/bin/env python3
"""
TelSeekerVisualizer.py - Generate interactive HTML visualization for TelSeeker results

Generates two types of reports:
1. Global report: Overview of all telomere extension results
2. Task reports: Detailed reports for each chromosome end

Usage:
    python TelSeekerVisualizer.py --out /path/to/telseeker/output

Output:
    --out/visual.report/Global.report.html - Global overview report
    --out/visual.report/<Chr.X>.report.html - Individual task reports
"""

import os
import sys
import json
import re
import argparse
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime

try:
    from Bio import SeqIO
    HAS_BIOPYTHON = True
except ImportError:
    HAS_BIOPYTHON = False
    print("Warning: BioPython not found. Some features may be limited.")

# ============================================================================
# Part2 Task Report Generator (从 telo_part2_visual.py 移植)
# ============================================================================

class TelSeekerPart2LogParser:
    """
    解析TelSeeker Part2的extension日志文件（1 vs N 检查）。
    
    解析文件：
    - direct.check/direct.check.log: 直接连接检查日志
    - extension/extension.log: 主日志
    - extension/round{N}/round.log: 每轮详细日志
    - extension/round{N}/connection_check/round{N}.check.log: 每轮的1 vs N检查结果
    """
    
    def __init__(self, chr_end_dir: Path):
        self.chr_end_dir = chr_end_dir
        self.chr_end_name = chr_end_dir.name
        self.extension_dir = chr_end_dir / 'extension'
        self.direct_dir = chr_end_dir / 'direct.check'
        
        # 解析的数据
        self.initial_info: Dict = {}
        self.rounds_data: List[Dict] = []
        self.final_info: Dict = {}
        self.summary_info: Dict = {}
        self.config: Dict = {}
        self.direct_check: Dict = {}
    
    def parse(self) -> Dict:
        # 1) 初始信息
        self._parse_initial_info()
        # 2) 直接连接检查
        self._parse_direct_check()
        # 3) 主日志配置
        self._parse_main_log()
        # 4) 轮次信息
        self._parse_rounds()
        # 5) 摘要
        self._parse_summary()
        # 6) 最终状态
        self._parse_final_info()
        
        return {
            'chr_end': self.chr_end_name,
            'initial_info': self.initial_info,
            'config': self.config,
            'direct_check': self.direct_check,
            'rounds': self.rounds_data,
            'final_info': self.final_info,
            'summary_info': self.summary_info
        }
    
    def _parse_initial_info(self):
        # seed长度
        seed_file = self.chr_end_dir / 'seed.fa'
        if seed_file.exists():
            seed_seq = self._read_fasta_sequence(seed_file)
            self.initial_info['seed_length'] = len(seed_seq) if seed_seq else 0
        else:
            self.initial_info['seed_length'] = 0
        
        # 解析任务名
        parts = self.chr_end_name.rsplit('.', 1)
        if len(parts) == 2:
            self.initial_info['chr_name'] = parts[0]
            self.initial_info['end_type'] = parts[1]  # 'L' or 'R'
        else:
            self.initial_info['chr_name'] = self.chr_end_name
            self.initial_info['end_type'] = 'L'
        
        # 端粒reads数量
        telo_reads_file = self.chr_end_dir / 'telo.reads.fa'
        if telo_reads_file.exists():
            self.initial_info['telo_reads_count'] = self._count_fasta_records(telo_reads_file)
        else:
            self.initial_info['telo_reads_count'] = 0
    
    def _parse_main_log(self):
        """解析 extension/extension.log 中的参数配置"""
        defaults = {
            'max_rounds': 30,  # Updated default value to match new unified parameter
            'max_extension_length': 1000000,
            'edge': 500,
            'kmer_num': 10,
            'kmer_size': 41,
        }
        log_file = self.extension_dir / 'extension.log'
        if log_file.exists():
            text = log_file.read_text(encoding='utf-8', errors='ignore')
            m = re.search(r'Max Rounds:\s*(\d+)', text)
            if m: self.config['max_rounds'] = int(m.group(1))
            m = re.search(r'Max Extension Length:\s*(\d+)', text)
            if m: self.config['max_extension_length'] = int(m.group(1))
            m = re.search(r'Edge Tolerance:\s*(\d+)\s*bp', text)
            if m: self.config['edge'] = int(m.group(1))
            m = re.search(r'K-mer Parameters:\s*num=(\d+),\s*size=(\d+)', text)
            if m:
                self.config['kmer_num'] = int(m.group(1))
                self.config['kmer_size'] = int(m.group(2))
        # 填充缺失的配置为默认值
        for k, v in defaults.items():
            if k not in self.config:
                self.config[k] = v
    
    def _parse_rounds(self):
        if not self.extension_dir.exists():
            return
        round_dirs = sorted([d for d in self.extension_dir.iterdir() if d.is_dir() and d.name.startswith('round')],
                            key=lambda p: int(re.sub('[^0-9]', '', p.name) or 0))
        cumulative = 0
        for rd in round_dirs:
            try:
                num = int(rd.name.replace('round', ''))
            except Exception:
                continue
            rdata = {'round': num}
            rlog = rd / 'round.log'
            if rlog.exists():
                content = rlog.read_text(encoding='utf-8', errors='ignore')
                m = re.search(r'Extension Length:\s*(\d+)\s*bp', content)
                ext_len = int(m.group(1)) if m else 0
                rdata['extension_length'] = ext_len
                cumulative = cumulative + ext_len
                rdata['cumulative_extension'] = cumulative
                rdata['extension_status'] = 'extended' if 'Status: Success' in content else 'no_extension'
            else:
                rdata['extension_length'] = 0
                rdata['cumulative_extension'] = cumulative
                rdata['extension_status'] = 'unknown'
            cdir = rd / 'connection_check'
            if cdir.exists():
                clog = cdir / f'round{num}.check.log'
                if clog.exists():
                    ctext = clog.read_text(encoding='utf-8', errors='ignore')
                    success = 'Status: SUCCESS' in ctext
                    rdata['connection_found'] = success
                    m = re.search(r'Extended Sequence:\s*(.+)', ctext)
                    if m:
                        rdata['extended_seq_file'] = m.group(1).strip()
                    m = re.search(r'Connected Read:\s*(.+)', ctext)
                    if m: rdata['connected_read'] = m.group(1).strip()
                    m = re.search(r'Reads Checked:\s*(\d+)/(\d+)', ctext)
                    if m:
                        rdata['checked_reads'] = int(m.group(1))
                        rdata['total_reads'] = int(m.group(2))
                    m = re.search(r'Alignment Length:\s*(\d+)\s*bp', ctext)
                    if m: rdata['aln_length'] = int(m.group(1))
                    m = re.search(r'Identity:\s*([0-9.]+)%', ctext)
                    if m: rdata['identity'] = float(m.group(1))
                    m = re.search(r'Reference Positions:\s*(\d+)-(\d+)', ctext)
                    if m:
                        rdata['ref_start'] = int(m.group(1))
                        rdata['ref_end'] = int(m.group(2))
                    m = re.search(r'Query Positions:\s*(\d+)-(\d+)', ctext)
                    if m:
                        rdata['qry_start'] = int(m.group(1))
                        rdata['qry_end'] = int(m.group(2))
                    lfa = cdir / f'round{num}.linker.fa'
                    if lfa.exists():
                        rdata['linker_file'] = str(lfa)
                else:
                    rdata['connection_found'] = False
            else:
                rdata['connection_found'] = False
            self.rounds_data.append(rdata)
    
    def _parse_summary(self):
        summary_file = self.extension_dir / 'extension.summary'
        if not summary_file.exists():
            return
        content = summary_file.read_text(encoding='utf-8', errors='ignore')
        m = re.search(r'Total Rounds:\s*(\d+)', content)
        if m: self.summary_info['total_rounds'] = int(m.group(1))
        m = re.search(r'Total Extension Length:\s*(\d+)\s*bp', content)
        if m: self.summary_info['total_extension_length'] = int(m.group(1))
        m = re.search(r'Stop Reason:\s*(.+)', content)
        if m: self.summary_info['stop_reason'] = m.group(1).strip()
        self.summary_info['connection_found'] = ('Connection Found: Yes' in content)
        m = re.search(r'Connected Read:\s*(.+)', content)
        if m: self.summary_info['connected_read_id'] = m.group(1).strip()
    
    def _parse_final_info(self):
        ext_success = self.summary_info.get('connection_found', False)
        direct_success = self.direct_check.get('success', False)
        
        self.final_info['success'] = bool(direct_success or ext_success)
        self.final_info['method'] = 'direct' if direct_success else ('extension' if ext_success else 'none')
        self.final_info['total_rounds'] = self.summary_info.get('total_rounds', len(self.rounds_data))
        self.final_info['total_extension_length'] = self.summary_info.get('total_extension_length', sum(r.get('extension_length', 0) for r in self.rounds_data))
        self.final_info['stop_reason'] = self.summary_info.get('stop_reason', 'unknown' if not direct_success else 'direct_connection_found')
        
        if self.final_info['success']:
            self.final_info['status'] = 'success'
        else:
            reason = self.final_info['stop_reason'].lower()
            if 'no' in reason and 'extension' in reason:
                self.final_info['status'] = 'no_extension'
            elif 'max' in reason:
                self.final_info['status'] = 'max_limit_reached'
            else:
                self.final_info['status'] = 'failed'
    
    @staticmethod
    def _read_fasta_sequence(fasta_file: Path) -> str:
        seq = []
        with open(fasta_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('>'):
                    continue
                seq.append(line)
        return ''.join(seq)
    
    def _parse_direct_check(self):
        """解析 direct.check 结果"""
        dlog = self.direct_dir / 'direct.check.log'
        info: Dict = {}
        if not dlog.exists():
            self.direct_check = info
            return
        text = dlog.read_text(encoding='utf-8', errors='ignore')
        info['checked'] = True
        info['success'] = ('Status: SUCCESS' in text)
        m = re.search(r'Connected Read:\s*(.+)', text)
        if m: info['read_id'] = m.group(1).strip()
        m = re.search(r'Alignment Length:\s*(\d+)\s*bp', text)
        if m: info['aln_length'] = int(m.group(1))
        m = re.search(r'Identity:\s*([0-9.]+)%', text)
        if m: info['identity'] = float(m.group(1))
        m = re.search(r'Reads Checked:\s*(\d+)', text)
        if m: info['reads_checked'] = int(m.group(1))
        m = re.search(r'Total Telomeric Reads:\s*(\d+)', text)
        if m: info['total_reads'] = int(m.group(1))
        m = re.search(r'Reference Positions:\s*(\d+)-(\d+)', text)
        if m:
            info['ref_start'] = int(m.group(1))
            info['ref_end'] = int(m.group(2))
        m = re.search(r'Query Positions:\s*(\d+)-(\d+)', text)
        if m:
            info['qry_start'] = int(m.group(1))
            info['qry_end'] = int(m.group(2))
        lfa = self.direct_dir / 'direct.linker.fa'
        if lfa.exists():
            info['linker_file'] = str(lfa)
        self.direct_check = info
    
    @staticmethod
    def _count_fasta_records(fasta_file: Path) -> int:
        cnt = 0
        with open(fasta_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if line.startswith('>'):
                    cnt += 1
        return cnt


# Note: Part2HTMLReportGenerator 类太长，将在下一个 diff 中插入
class Part2HTMLReportGenerator:
    """生成符合 TelSeeker Part2 1vsN 流程的独立HTML报告"""
    def __init__(self, data: Dict, output_dir: Path):
        self.data = data
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _ensure_local_file(self, src_path: Any, dest_name: Optional[str] = None) -> Optional[str]:
        """Copy a source file into the report directory and return local file name.
        If dest_name is provided, the file will be saved under that name.
        Returns None if copy fails or file missing.
        """
        try:
            if not src_path:
                return None
            p = Path(src_path)
            if not p.exists():
                return None
            local_name = dest_name or p.name
            dst = self.output_dir / local_name
            # Copy if missing or different size (cheap check)
            try:
                if (not dst.exists()) or (dst.stat().st_size != p.stat().st_size):
                    shutil.copy2(p, dst)
            except Exception:
                # Fallback simple copy
                try:
                    shutil.copyfile(p, dst)
                except Exception:
                    return None
            return local_name
        except Exception:
            return None
    
    def generate(self) -> Path:
        html = self._build_html()
        out_file = self.output_dir / 'telo_part2_report.html'
        out_file.write_text(html, encoding='utf-8')
        # Silent generation - let caller handle output
        return out_file
    
    def _build_html(self) -> str:
        info = self.data.get('initial_info', {})
        conf = self.data.get('config', {})
        fin = self.data.get('final_info', {})
        rounds = self.data.get('rounds', [])
        chr_end = self.data.get('chr_end', 'N/A')
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        status_badge = self._status_badge(fin)
        rows_html = '\n'.join(self._row_html(r) for r in rounds)

        css = self._css()
        js = self._js()

        # Hide round details when direct method succeeded
        show_rounds = not (fin.get('method') == 'direct')
        rounds_section = ''
        if show_rounds:
            rounds_section = f"""
  <div class=\"section\">
    <div class=\"section-title\" data-i18n-en=\"🔄 Round Details (1 vs N Check)\" data-i18n-zh=\"🔄 轮次详情（1 vs N 检查）\">🔄 Round Details (1 vs N Check)</div>
    <table class=\"table\">
      <thead>
        <tr>
          <th data-i18n-en=\"Round\" data-i18n-zh=\"轮次\">Round</th>
          <th data-i18n-en=\"Extension Length\" data-i18n-zh=\"延伸长度\">Extension Length</th>
          <th data-i18n-en=\"Cumulative Extension\" data-i18n-zh=\"累计延伸\">Cumulative Extension</th>
          <th data-i18n-en=\"Extension Status\" data-i18n-zh=\"延伸状态\">Extension Status</th>
          <th data-i18n-en=\"Connection Result\" data-i18n-zh=\"连接结果\">Connection Result</th>
          <th data-i18n-en=\"Connected Read\" data-i18n-zh=\"连接的Read\">Connected Read</th>
          <th data-i18n-en=\"Reads Checked\" data-i18n-zh=\"Reads检查\">Reads Checked</th>
          <th data-i18n-en=\"Identity\" data-i18n-zh=\"Identity\">Identity</th>
          <th data-i18n-en=\"Alignment Length\" data-i18n-zh=\"AlnLen\">Alignment Length</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </div>
"""

        total_rounds = fin.get('total_rounds', len(rounds))

        return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<title>TelSeeker Part2 Report - {chr_end}</title>
<style>
{css}
</style>
</head>
<body>
<div class=\"container\">
  <div class=\"header\">
    <div class=\"header-top\">
      <h1 data-i18n-en=\"🧬 TelSeeker Part2 Report\" data-i18n-zh=\"🧬 TelSeeker Part2 报告\">🧬 TelSeeker Part2 Report</h1>
      <div class=\"language-switcher\" role=\"group\" aria-label=\"Language Switcher\">
        <button class=\"language-btn\" data-lang=\"zh\" type=\"button\" aria-label=\"切换为中文\">中文</button>
        <button class=\"language-btn active\" data-lang=\"en\" type=\"button\" aria-label=\"Switch to English\">EN</button>
      </div>
    </div>
    <div class=\"sub\" data-i18n-en=\"Task: <code>{chr_end}</code> · Generated: {now}\" data-i18n-zh=\"任务：<code>{chr_end}</code> · 生成时间：{now}\">Task: <code>{chr_end}</code> · Generated: {now}</div>
    <div class=\"badges\">{status_badge}<span class=\"badge info\" data-i18n-en=\"Rounds: {total_rounds}\" data-i18n-zh=\"轮次：{total_rounds}\">Rounds: {total_rounds}</span></div>
  </div>

  <div class=\"section\">
    <div class=\"section-title\" data-i18n-en=\"📋 Initial Information\" data-i18n-zh=\"📋 初始信息\">📋 Initial Information</div>
    <table class=\"kv\">
      <tr><td data-i18n-en=\"Chromosome End\" data-i18n-zh=\"染色体端\">Chromosome End</td><td>{info.get('chr_name','N/A')}.{info.get('end_type','?')}</td></tr>
      <tr><td data-i18n-en=\"Seed Length\" data-i18n-zh=\"Seed长度\">Seed Length</td><td>{info.get('seed_length',0):,} bp</td></tr>
      <tr><td data-i18n-en=\"Telomere Reads\" data-i18n-zh=\"端粒reads数量\">Telomere Reads</td><td>{info.get('telo_reads_count',0):,}</td></tr>
      <tr><td data-i18n-en=\"Edge Tolerance\" data-i18n-zh=\"边缘阈值\">Edge Tolerance</td><td>{conf.get('edge','N/A')} bp</td></tr>
      <tr><td data-i18n-en=\"K-mer Parameters\" data-i18n-zh=\"K-mer参数\">K-mer Parameters</td><td>num={conf.get('kmer_num','N/A')}, size={conf.get('kmer_size','N/A')}</td></tr>
      <tr><td data-i18n-en=\"Max Rounds\" data-i18n-zh=\"最大轮次\">Max Rounds</td><td>{conf.get('max_rounds','N/A')}</td></tr>
      <tr><td data-i18n-en=\"Max Extension Length\" data-i18n-zh=\"最大延伸长度\">Max Extension Length</td><td>{conf.get('max_extension_length','N/A')}</td></tr>
    </table>
  </div>

  <div class=\"section\">
    <div class=\"section-title\" data-i18n-en=\"🔗 Connection Overview\" data-i18n-zh=\"🔗 连接结果总览\">🔗 Connection Overview</div>
    {self._connection_overview_html()}
  </div>

  {rounds_section}

  <div class=\"section\">
    <div class=\"section-title\" data-i18n-en=\"🧩 Connection Visualization\" data-i18n-zh=\"🧩 连接情况可视化\">🧩 Connection Visualization</div>
    {self._connection_visualization_html()}
  </div>

  <div class=\"footer\" data-i18n-en=\"Report generated by telo_part2_visual.py.\" data-i18n-zh=\"本报告由 telo_part2_visual.py 自动生成。\">Report generated by telo_part2_visual.py.</div>
</div>
<script>
{js}
</script>
</body>
</html>"""
    
    def _row_html(self, r: Dict) -> str:
        ext_status = r.get('extension_status')
        if ext_status == 'extended':
            status_html = ('<span data-i18n-en="Extended" data-i18n-zh="成功延伸">Extended</span>')
        elif ext_status == 'no_extension':
            status_html = ('<span data-i18n-en="No Extension" data-i18n-zh="无延伸">No Extension</span>')
        else:
            status_html = ('<span data-i18n-en="Unknown" data-i18n-zh="未知">Unknown</span>')

        if r.get('connection_found'):
            conn_html = ('<span data-i18n-en="✅ Found Connection" data-i18n-zh="✅ 找到连接">✅ Found Connection</span>')
        else:
            conn_html = ('<span data-i18n-en="❌ Not Found" data-i18n-zh="❌ 未找到">❌ Not Found</span>')

        rid = r.get('connected_read', '-')
        reads_chk = '-'
        if 'checked_reads' in r and 'total_reads' in r:
            reads_chk = f"{r['checked_reads']}/{r['total_reads']}"
        idt = (f"{r.get('identity', 0):.2f}%" if 'identity' in r else '-')
        alnlen = (f"{r.get('aln_length', 0):,} bp" if 'aln_length' in r else '-')
        return (
            f"<tr>"
            f"<td>{r.get('round', '')}</td>"
            f"<td>{r.get('extension_length', 0):,} bp</td>"
            f"<td>{r.get('cumulative_extension', 0):,} bp</td>"
            f"<td>{status_html}</td>"
            f"<td>{conn_html}</td>"
            f"<td>{rid}</td>"
            f"<td>{reads_chk}</td>"
            f"<td>{idt}</td>"
            f"<td>{alnlen}</td>"
            f"</tr>"
        )
    
    def _status_badge(self, fin: Dict) -> str:
        if fin.get('success'):
            if fin.get('method') == 'direct':
                return ('<span class="badge success" data-i18n-en="✅ Direct Connection Success" '
                        'data-i18n-zh="✅ 直接连接成功">✅ Direct Connection Success</span>')
            return ('<span class="badge success" data-i18n-en="✅ Extension Connection Success" '
                    'data-i18n-zh="✅ 延伸连接成功">✅ Extension Connection Success</span>')
        status = fin.get('status', 'failed')
        if status == 'no_extension':
            return ('<span class="badge danger" data-i18n-en="❌ No Extension" '
                    'data-i18n-zh="❌ 无延伸">❌ No Extension</span>')
        if status == 'max_limit_reached':
            return ('<span class="badge warn" data-i18n-en="⚠️ Limit Reached" '
                    'data-i18n-zh="⚠️ 达到上限">⚠️ Limit Reached</span>')
        return ('<span class="badge danger" data-i18n-en="❌ Failed" '
                'data-i18n-zh="❌ 失败">❌ Failed</span>')
    
    def _css(self) -> str:
        return """
body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Inter,Helvetica,Arial,sans-serif;background:#f5f7fb;color:#2c3e50;margin:0}
.container{max-width:1180px;margin:0 auto;padding:22px}
.header{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;border-radius:12px;padding:20px 24px;box-shadow:0 8px 24px rgba(0,0,0,.12);margin-bottom:18px}
.header-top{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px;flex-wrap:wrap}
.header h1{margin:0;font-size:22px}
.header .sub{opacity:.95;font-size:13px;margin:0}
.language-switcher{display:flex;align-items:center;gap:8px}
.language-btn{background:rgba(255,255,255,0.2);border:1px solid rgba(255,255,255,0.3);color:#fff;padding:6px 14px;border-radius:18px;font-size:12px;font-weight:600;cursor:pointer;transition:all .2s ease;min-width:46px}
.language-btn:hover{background:rgba(255,255,255,0.28);transform:translateY(-1px)}
.language-btn:active{transform:translateY(0)}
.language-btn.active{background:#fff;color:#3498db;box-shadow:0 4px 10px rgba(0,0,0,0.15)}
.language-btn:focus{outline:none;box-shadow:0 0 0 2px rgba(255,255,255,0.6)}
.badges{margin-top:10px;display:flex;gap:10px;flex-wrap:wrap}
.badge{display:inline-block;padding:6px 10px;border-radius:20px;font-weight:600;font-size:12px}
.badge.success{background:#2ecc71}
.badge.warn{background:#f39c12}
.badge.danger{background:#e74c3c}
.badge.info{background:#3498db}
.section{background:#fff;border-radius:12px;padding:16px 18px;margin:14px 0;box-shadow:0 2px 12px rgba(0,0,0,.06)}
.section-title{font-weight:700;margin-bottom:10px}
.kv{width:100%;border-collapse:collapse}
.kv td{padding:8px 10px;border-bottom:1px solid #eee}
.kv td:first-child{width:220px;color:#34495e;font-weight:600;background:#fafbff}
.table{width:100%;border-collapse:collapse;font-size:14px}
.table th,.table td{padding:10px 8px;border-bottom:1px solid #eee;text-align:center}
.table thead th{background:#34495e;color:#fff;position:sticky;top:0}
.progress{height:10px;background:#eef2ff;border-radius:6px;overflow:hidden}
.progress .bar{height:100%;background:#27ae60}
.footer{color:#95a5a6;text-align:center;font-size:12px;margin:16px 0}
.viz-placeholder{color:#7f8c8d;font-size:14px}
.viz-error{color:#e74c3c;font-size:14px}
"""
    
    def _js(self) -> str:
        return """
(function(){
  function applyTranslations(lang){
    var langAttr = lang === 'zh' ? 'zh-CN' : 'en';
    document.documentElement.setAttribute('lang', langAttr);
    var nodes = document.querySelectorAll('[data-i18n-en]');
    nodes.forEach(function(node){
      var value = node.getAttribute('data-i18n-' + lang);
      if (value !== null) {
        node.innerHTML = value;
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function(){
    var currentLang = 'en';
    var buttons = Array.prototype.slice.call(document.querySelectorAll('.language-btn'));

    function setActiveButton(){
      buttons.forEach(function(btn){
        var isActive = btn.getAttribute('data-lang') === currentLang;
        if (isActive) {
          btn.classList.add('active');
          btn.setAttribute('aria-pressed', 'true');
        } else {
          btn.classList.remove('active');
          btn.setAttribute('aria-pressed', 'false');
        }
      });
    }

    function updateLanguage(lang){
      if (!lang) {
        return;
      }
      currentLang = lang;
      applyTranslations(currentLang);
      setActiveButton();
    }

    if (buttons.length) {
      buttons.forEach(function(btn){
        btn.addEventListener('click', function(){
          var lang = btn.getAttribute('data-lang');
          updateLanguage(lang);
        });
      });
    }

    updateLanguage(currentLang);
  });
})();
"""

    def _read_fasta_total_len(self, file_path: Path) -> int:
        try:
            length = 0
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if not line or line.startswith('>'):
                        continue
                    length += len(line.strip())
            return length
        except Exception:
            return 0

    def _read_fasta_len_by_id(self, file_path: Path, read_id: str) -> int:
        try:
            if not file_path.exists():
                return 0
            length = 0
            found = False
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.startswith('>'):
                        # new record
                        current_id = line[1:].strip().split()[0]
                        found = (current_id == read_id)
                        length = 0 if found else 0
                        continue
                    if found:
                        length += len(line.strip())
                        # continue until next header or EOF
            return length if found else 0
        except Exception:
            return 0

    def _connection_overview_html(self) -> str:
        direct = self.data.get('direct_check', {})
        fin = self.data.get('final_info', {})
        rounds = self.data.get('rounds', [])
        # 找到成功的extension轮次（如有）
        ext_success_round = next((r for r in rounds if r.get('connection_found')), None)
        direct_rows = []
        if direct:
            status_text = ('<span data-i18n-en="✅ Success" data-i18n-zh="✅ 成功">✅ Success</span>'
                           if direct.get('success') else
                           '<span data-i18n-en="❌ Failed" data-i18n-zh="❌ 失败">❌ Failed</span>')
            idt_text = f"{direct.get('identity')}%" if 'identity' in direct else '-'
            alnlen_text = f"{direct.get('aln_length')} bp" if 'aln_length' in direct else '-'
            link_display = '-'
            link_path = direct.get('linker_file')
            if link_path:
                task_name = self.data.get('chr_end', 'task')
                local_name = self._ensure_local_file(link_path, f"{task_name}.linker.fa")
                if local_name:
                    link_display = (f'<a href="{local_name}" target="_blank" rel="noopener" data-i18n-en="View" '
                                    f'data-i18n-zh="查看">View</a>')
            direct_rows.append(
                f"<tr><td data-i18n-en=\"Direct Connection\" data-i18n-zh=\"直接连接\">Direct Connection</td>"
                f"<td>{status_text}</td><td>{direct.get('read_id','-')}</td>"
                f"<td>{idt_text}</td><td>{alnlen_text}</td><td>{link_display}</td></tr>"
            )
        else:
            direct_rows.append(
                "<tr><td data-i18n-en=\"Direct Connection\" data-i18n-zh=\"直接连接\">Direct Connection</td>"
                "<td colspan=5 data-i18n-en=\"Not run or missing log\" data-i18n-zh=\"未执行或无日志\">Not run or missing log</td></tr>"
            )
        ext_rows = []
        if ext_success_round:
            link = ext_success_round.get('linker_file')
            link_display = '-'
            if link:
                p = Path(link)
                if not p.exists():
                    # try relative to round dir
                    round_no = ext_success_round.get('round')
                    p2 = chr_dir / 'extension' / f"round{round_no}" / Path(link).name
                    if p2.exists():
                        p = p2
                task_name = self.data.get('chr_end', 'task')
                local_name = self._ensure_local_file(p, f"{task_name}.linker.fa")
                if local_name:
                    link_display = (f'<a href="{local_name}" target="_blank" rel="noopener" data-i18n-en="View" '
                                    f'data-i18n-zh="查看">View</a>')
            idt_text = f"{ext_success_round.get('identity')}%" if 'identity' in ext_success_round else '-'
            alnlen_text = f"{ext_success_round.get('aln_length')} bp" if 'aln_length' in ext_success_round else '-'
            round_no = ext_success_round.get('round')
            ext_rows.append(
                f"<tr><td data-i18n-en=\"Extension Connection\" data-i18n-zh=\"延伸连接\">Extension Connection</td>"
                f"<td data-i18n-en=\"✅ Success (Round {round_no})\" data-i18n-zh=\"✅ 成功(第{round_no}轮)\">✅ Success (Round {round_no})</td>"
                f"<td>{ext_success_round.get('connected_read','-')}</td>"
                f"<td>{idt_text}</td><td>{alnlen_text}</td><td>{link_display}</td></tr>"
            )
        else:
            # 直连成功则未执行延伸
            if fin.get('method') == 'direct' and fin.get('success'):
                ext_rows.append(
                    "<tr><td data-i18n-en=\"Extension Connection\" data-i18n-zh=\"延伸连接\">Extension Connection</td>"
                    "<td colspan=5 data-i18n-en=\"Skipped (direct success)\" data-i18n-zh=\"直连成功未执行\">Skipped (direct success)</td></tr>"
                )
            # 如果总状态成功但method是extension，可能未解析到细节
            elif fin.get('method') == 'extension' and fin.get('success'):
                ext_rows.append(
                    "<tr><td data-i18n-en=\"Extension Connection\" data-i18n-zh=\"延伸连接\">Extension Connection</td>"
                    "<td data-i18n-en=\"✅ Success\" data-i18n-zh=\"✅ 成功\">✅ Success</td>"
                    "<td colspan=4 data-i18n-en=\"See round table for details\" data-i18n-zh=\"详情见轮次表\">See round table for details</td></tr>"
                )
            else:
                ext_rows.append(
                    "<tr><td data-i18n-en=\"Extension Connection\" data-i18n-zh=\"延伸连接\">Extension Connection</td>"
                    "<td data-i18n-en=\"❌ Not Successful\" data-i18n-zh=\"❌ 未成功\">❌ Not Successful</td>"
                    "<td colspan=4>-</td></tr>"
                )
        if fin.get('method') == 'direct':
            used = ('<span data-i18n-en="Direct Connection" data-i18n-zh="直接连接">Direct Connection</span>')
        elif fin.get('method') == 'extension':
            used = ('<span data-i18n-en="Extension Connection" data-i18n-zh="延伸连接">Extension Connection</span>')
        else:
            used = ('<span data-i18n-en="None" data-i18n-zh="无">None</span>')
        return """
<table class=\"table\">
  <thead>
    <tr>
      <th data-i18n-en=\"Type\" data-i18n-zh=\"类型\">Type</th>
      <th data-i18n-en=\"Result\" data-i18n-zh=\"结果\">Result</th>
      <th>Read</th>
      <th data-i18n-en=\"Identity\" data-i18n-zh=\"Identity\">Identity</th>
      <th data-i18n-en=\"Alignment Length\" data-i18n-zh=\"AlnLen\">Alignment Length</th>
      <th data-i18n-en=\"Linker\" data-i18n-zh=\"Linker\">Linker</th>
    </tr>
  </thead>
  <tbody>
    {direct_rows}
    {ext_rows}
    <tr><td data-i18n-en=\"Adopted Result\" data-i18n-zh=\"使用结果\">Adopted Result</td><td colspan=5>{used}</td></tr>
  </tbody>
</table>
""".format(direct_rows=''.join(direct_rows), ext_rows=''.join(ext_rows), used=used)

    def _connection_visualization_html(self) -> str:
        fin = self.data.get('final_info', {})
        info = self.data.get('initial_info', {})
        rounds = self.data.get('rounds', [])
        direct = self.data.get('direct_check', {})
        chr_dir = self.output_dir
        end_type = info.get('end_type', 'L')
        ext_len_for_overlay = 0  # 累计延伸长度（仅在延伸连接时使用）

        # Determine which connection to show
        title_en = 'Connection Overview'
        title_zh = '连接总览'

        if fin.get('method') == 'direct' and fin.get('success') and direct:
            # Use direct connection data
            ref_name = 'Seed'
            ref_len = info.get('seed_length', 0)
            # try to recompute from file for accuracy
            seed_path = chr_dir / 'seed.fa'
            if seed_path.exists():
                ref_len = self._read_fasta_total_len(seed_path) or ref_len
            qry_id = direct.get('read_id')
            reads_file = chr_dir / 'telo.reads.fa'
            qry_len = self._read_fasta_len_by_id(reads_file, qry_id) if qry_id else 0
            ref_start = direct.get('ref_start')
            ref_end = direct.get('ref_end')
            qry_start = direct.get('qry_start')
            qry_end = direct.get('qry_end')
            identity = direct.get('identity')
            title_en = f"Direct Connection Success - Read: {qry_id}"
            title_zh = f"直连成功 - Read: {qry_id}"
        else:
            # Find extension success round
            ext_round = next((r for r in rounds if r.get('connection_found')), None)
            if not ext_round:
                return ('<div class="viz-placeholder" data-i18n-en="No successful connection available for visualization" '
                        'data-i18n-zh="无成功连接可可视化">No successful connection available for visualization</div>')
            ref_name = 'ExtendedSeq'
            # extended seq length
            ref_len = 0
            ext_path = ext_round.get('extended_seq_file')
            if ext_path:
                p = Path(ext_path)
                if not p.is_file():
                    # handle relative path from round dir
                    p2 = chr_dir / 'extension' / f"round{ext_round.get('round')}" / Path(ext_path).name
                    if p2.exists():
                        p = p2
                if p.exists():
                    ref_len = self._read_fasta_total_len(p)
            # read length
            qry_id = ext_round.get('connected_read')
            reads_file = chr_dir / 'telo.reads.fa'
            qry_len = self._read_fasta_len_by_id(reads_file, qry_id) if qry_id else 0
            ref_start = ext_round.get('ref_start')
            ref_end = ext_round.get('ref_end')
            qry_start = ext_round.get('qry_start')
            qry_end = ext_round.get('qry_end')
            identity = ext_round.get('identity')
            round_no = ext_round.get('round')
            title_en = f"Extension Connection Success - Round {round_no} - Read: {qry_id}"
            title_zh = f"延伸连接成功 - 第{round_no}轮 - Read: {qry_id}"
            # 记录用于可视化的累计延伸长度（最后一轮）
            try:
                ext_len_for_overlay = int(ext_round.get('cumulative_extension') or 0)
            except Exception:
                ext_len_for_overlay = int(fin.get('total_extension_length') or 0)

        # Prepare label texts
        identity_text = f"{identity:.2f}%" if isinstance(identity, (int, float)) else "-"
        read_aln_len = abs(qry_end - qry_start) + 1 if isinstance(qry_end, int) and isinstance(qry_start, int) else None
        read_len_text = f"{read_aln_len:,} bp" if isinstance(read_aln_len, int) and read_aln_len > 0 else "-"
        read_label_text = f"{read_len_text}; {identity_text}" if identity_text != "-" else read_len_text

        # Fallback lengths from coordinates if missing
        if (not isinstance(ref_len, int)) or ref_len <= 0:
            if isinstance(ref_start, int) and isinstance(ref_end, int):
                ref_len = max(ref_start, ref_end)
        if (not isinstance(qry_len, int)) or qry_len <= 0:
            if isinstance(qry_start, int) and isinstance(qry_end, int):
                qry_len = max(qry_start, qry_end)

        # Validate positions
        missing_any = any(v is None or (isinstance(v, int) and v <= 0) for v in [ref_start, ref_end, qry_start, qry_end])
        if missing_any or ref_len <= 0 or qry_len <= 0:
            return ('<div class="viz-error" data-i18n-en="Missing alignment coordinates or sequence length, unable to render visualization" '
                    'data-i18n-zh="缺少比对坐标或序列长度，无法绘制可视化">Missing alignment coordinates or sequence length, unable to render visualization</div>')

        # ==== Ref axis windowing ====
        # Direct connection: window = min(ref_len, 2 * read_len)
        # Extension connection: window = min(ref_len, cumulative_extension + read_len)
        if isinstance(qry_len, int) and qry_len > 0:
            if fin.get('method') == 'extension':
                base_len = (ext_len_for_overlay if isinstance(ext_len_for_overlay, int) else 0) + qry_len
            else:
                base_len = 2 * qry_len
            ref_view_len = min(ref_len, base_len)
            if end_type == 'L':
                ref_view_start = 1
                ref_view_end = ref_view_len
            else:  # 'R'
                ref_view_start = max(1, ref_len - ref_view_len + 1)
                ref_view_end = ref_len
        else:
            ref_view_start = 1
            ref_view_end = ref_len
            ref_view_len = ref_len

        # SVG params
        svg_width = 1000
        svg_height = 320
        margin = 60
        plot_width = svg_width - 2*margin
        # Move ref 稍微靠上，避免遮盖图注
        ref_y = margin + 30
        qry_y = svg_height - margin - 40
        # Unified scale: longer axis fills, shorter scales proportionally
        scale = plot_width / max(ref_view_len, qry_len, 1)
        # Axis ends
        ref_axis_end = margin + ref_view_len * scale
        qry_axis_end = margin + qry_len * scale
        # Compute positions (clamped to viewing window)
        ref_aln_start = max(min(ref_start, ref_end), ref_view_start)
        ref_aln_end = min(max(ref_start, ref_end), ref_view_end)
        # If alignment window doesn't intersect view, early return placeholder
        if ref_aln_end < ref_aln_start:
            return ('<div class="viz-error" data-i18n-en="No collinear region within the view window" '
                    'data-i18n-zh="可视窗口内无共线区域">No collinear region within the view window</div>')
        ref_x1 = margin + (ref_aln_start - ref_view_start) * scale
        ref_x2 = margin + (ref_aln_end - ref_view_start) * scale
        qry_x1 = margin + min(qry_start, qry_end) * scale
        qry_x2 = margin + max(qry_start, qry_end) * scale
        # Rect widths
        ref_rect_x = min(ref_x1, ref_x2)
        ref_rect_w = abs(ref_x2 - ref_x1)
        qry_rect_x = min(qry_x1, qry_x2)
        qry_rect_w = abs(qry_x2 - qry_x1)

        # Labels for ref axis ends (windowed)
        ref_left_label = f"{ref_view_start:,}"
        ref_right_label = f"{ref_view_end:,}"

        # Extension overlay fragment (only for extension method)
        ext_overlay = ""
        try:
            if fin.get('method') == 'extension' and isinstance(ext_len_for_overlay, int) and ext_len_for_overlay > 0:
                ext_len_clamped = min(max(ext_len_for_overlay, 0), int(ref_view_len) if isinstance(ref_view_len, int) else ref_view_len)
                ext_w = ext_len_clamped * scale
                if end_type == 'R':
                    ext_x1 = ref_axis_end - ext_w
                    ext_x2 = ref_axis_end
                else:  # 'L'
                    ext_x1 = margin
                    ext_x2 = margin + ext_w
                ext_overlay = (
                    f"    <!-- Extension overlay (cumulative extension highlighted) -->\n"
                    f"    <line x1=\"{ext_x1}\" y1=\"{ref_y}\" x2=\"{ext_x2}\" y2=\"{ref_y}\" "
                    f"stroke=\"#f39c12\" stroke-width=\"8\" stroke-linecap=\"round\"/>\n"
                )
        except Exception:
            ext_overlay = ""

        # Legend (bottom-right). Hide orange when direct connection.
        legend_has_ext = fin.get('method') == 'extension' and isinstance(ext_len_for_overlay, int) and ext_len_for_overlay > 0
        legend_items = 2 + (1 if legend_has_ext else 0)
        legend_w = 130
        legend_h = 20 * legend_items + 12
        legend_x = svg_width - margin - legend_w
        legend_y = svg_height - margin - legend_h + 6
        ly1 = legend_y + 22
        ly2 = ly1 + 20
        ly3 = ly2 + 20
        legend_svg = (
            f"    <!-- Legend -->\n"
            f"    <g>\n"
            f"      <rect x=\"{legend_x}\" y=\"{legend_y}\" width=\"{legend_w}\" height=\"{legend_h}\" rx=\"6\" ry=\"6\" fill=\"#ffffff\" stroke=\"#e1e5ee\"/>\n"
            f"      <line x1=\"{legend_x+10}\" y1=\"{ly1}\" x2=\"{legend_x+34}\" y2=\"{ly1}\" stroke=\"#3498db\" stroke-width=\"6\" stroke-linecap=\"round\"/>\n"
            f"      <text x=\"{legend_x+42}\" y=\"{ly1+4}\" fill=\"#2c3e50\" font-size=\"12\" data-i18n-en=\"Seed\" data-i18n-zh=\"Seed序列\">Seed</text>\n"
            f"      <line x1=\"{legend_x+10}\" y1=\"{ly2}\" x2=\"{legend_x+34}\" y2=\"{ly2}\" stroke=\"#9b59b6\" stroke-width=\"6\" stroke-linecap=\"round\"/>\n"
            f"      <text x=\"{legend_x+42}\" y=\"{ly2+4}\" fill=\"#2c3e50\" font-size=\"12\" data-i18n-en=\"Read\" data-i18n-zh=\"Read序列\">Read</text>\n"
            + (
                f"      <line x1=\"{legend_x+10}\" y1=\"{ly3}\" x2=\"{legend_x+34}\" y2=\"{ly3}\" stroke=\"#f39c12\" stroke-width=\"6\" stroke-linecap=\"round\"/>\n"
                f"      <text x=\"{legend_x+42}\" y=\"{ly3+4}\" fill=\"#2c3e50\" font-size=\"12\" data-i18n-en=\"Extension\" data-i18n-zh=\"延伸区域\">Extension</text>\n"
              if legend_has_ext else ""
            ) +
            f"    </g>\n"
        )

        # Build SVG
        svg = f"""
<div class=\"synteny-chart\" style=\"margin-top:10px;\">
  <svg width=\"{svg_width}\" height=\"{svg_height}\" viewBox=\"0 0 {svg_width} {svg_height}\">
    <rect width=\"{svg_width}\" height=\"{svg_height}\" fill=\"#f8f9fa\" stroke=\"#e9ecef\"/>
    <text x=\"{svg_width/2}\" y=\"24\" text-anchor=\"middle\" fill=\"#2c3e50\" font-weight=\"600\" data-i18n-en=\"{title_en}\" data-i18n-zh=\"{title_zh}\">{title_en}</text>
    <!-- Ref axis -->
    <line x1=\"{margin}\" y1=\"{ref_y}\" x2=\"{ref_axis_end}\" y2=\"{ref_y}\" stroke=\"#3498db\" stroke-width=\"8\" stroke-linecap=\"round\"/>
    <text x=\"{margin}\" y=\"{ref_y+24}\" fill=\"#7f8c8d\" font-size=\"11\">{ref_left_label}</text>
    <text x=\"{ref_axis_end}\" y=\"{ref_y+24}\" fill=\"#7f8c8d\" font-size=\"11\">{ref_right_label}</text>
    <!-- Qry axis -->
    <line x1=\"{margin}\" y1=\"{qry_y}\" x2=\"{qry_axis_end}\" y2=\"{qry_y}\" stroke=\"#9b59b6\" stroke-width=\"8\" stroke-linecap=\"round\"/>
    <text x=\"{margin}\" y=\"{qry_y+50}\" fill=\"#7f8c8d\" font-size=\"11\">1</text>
    <text x=\"{qry_axis_end}\" y=\"{qry_y+50}\" fill=\"#7f8c8d\" font-size=\"11\">{qry_len:,}</text>
{ext_overlay}
    <!-- Alignment rects -->
    <rect x=\"{ref_rect_x}\" y=\"{ref_y-6}\" width=\"{max(ref_rect_w,2)}\" height=\"12\" fill=\"#27ae60\" opacity=\"0.8\" stroke=\"#2c3e50\" stroke-width=\"1\"/>
    <rect x=\"{qry_rect_x}\" y=\"{qry_y-6}\" width=\"{max(qry_rect_w,2)}\" height=\"12\" fill=\"#27ae60\" opacity=\"0.8\" stroke=\"#2c3e50\" stroke-width=\"1\"/>

    <!-- Connection polygon -->
    <polygon points=\"{ref_x1},{ref_y+6} {ref_x2},{ref_y+6} {qry_x2},{qry_y-6} {qry_x1},{qry_y-6}\" fill=\"#27ae60\" opacity=\"0.35\" stroke=\"#27ae60\" stroke-width=\"1\"/>

    <!-- Labels -->
    <text x=\"{(ref_rect_x+ref_rect_x+max(ref_rect_w,2))/2}\" y=\"{ref_y-8}\" text-anchor=\"middle\" fill=\"#2c3e50\" font-size=\"11\">{(max(ref_start,ref_end)-min(ref_start,ref_end)+1):,} bp</text>
    <text x=\"{(qry_rect_x+qry_rect_x+max(qry_rect_w,2))/2}\" y=\"{qry_y+22}\" text-anchor=\"middle\" fill=\"#2c3e50\" font-size=\"11\">{read_label_text}</text>
{legend_svg}  </svg>
</div>
"""
        return svg




# ============================================================================
# Data Parsing Functions (FIXED)
# ============================================================================

def parse_telo_reads_stats(out_dir: Path) -> Dict:
    """
    Parse telomeric reads extraction statistics.
    
    FIXED: Look for the actual file names from TelSeekerPart1 output
    """
    part1_dir = out_dir / 'part1.telo.reads'
    
    stats = {
        'total_reads': 0,
        'hifi_reads': 0,
        'ont_reads': 0,
        'left_reads': 0,
        'right_reads': 0,
        'files': []
    }
    
    if not part1_dir.exists():
        print(f"  ⚠ part1.telo.reads directory not found: {part1_dir}")
        return stats
    
    # Check for left/right merged files (filtered output after second filter)
    left_telo = part1_dir / 'left.telo.reads.fa'
    right_telo = part1_dir / 'right.telo.reads.fa'
    
    if left_telo.exists():
        count = count_fasta_records(left_telo)
        stats['left_reads'] = count
        stats['total_reads'] += count
        stats['files'].append(str(left_telo.name))
        print(f"    ✓ Found {count:,} left telomeric reads")
    
    if right_telo.exists():
        count = count_fasta_records(right_telo)
        stats['right_reads'] = count
        stats['total_reads'] += count
        stats['files'].append(str(right_telo.name))
        print(f"    ✓ Found {count:,} right telomeric reads")
    
    # Check for platform-specific files (if available)
    # Note: These might not exist in all runs
    
    return stats


def count_fasta_records(fasta_path: Path) -> int:
    """Count number of records in a FASTA file."""
    if not HAS_BIOPYTHON:
        # Fallback: count headers
        count = 0
        try:
            with open(fasta_path, 'r') as f:
                for line in f:
                    if line.startswith('>'):
                        count += 1
        except:
            return 0
        return count
    
    try:
        return sum(1 for _ in SeqIO.parse(fasta_path, 'fasta'))
    except:
        return 0


def parse_part2_results(part2_dir: Path) -> List[Dict]:
    """
    Parse chromosome end extension results from part2.
    
    Returns list of extension results for each chromosome end.
    """
    if not part2_dir.exists():
        print(f"  ⚠ part2.chr.end.job directory not found: {part2_dir}")
        return []
    
    results = []
    chr_end_dirs = sorted([d for d in part2_dir.iterdir() if d.is_dir()])
    
    print(f"    Found {len(chr_end_dirs)} chromosome end directories")
    
    for chr_end_dir in chr_end_dirs:
        chr_end = chr_end_dir.name
        
        # Parse chromosome and end (format: Chr01_100001-246753025.L)
        if '.' in chr_end:
            parts = chr_end.rsplit('.', 1)
            chromosome = parts[0]
            end = parts[1]
        else:
            chromosome = chr_end
            end = 'unknown'
        
        result = {
            'chr_end': chr_end,
            'chromosome': chromosome,
            'end': end,
            'extended': False,
            'connection_type': 'NA',
            'round_num': 'NA',
            'connected_read': 'NA',
            'extension_length': 0
        }
        
        # Check for linker files
        linker_fa = chr_end_dir / 'linker.fa'
        linker_info = chr_end_dir / 'linker.info'
        
        if linker_fa.exists() and linker_info.exists():
            result['extended'] = True
            
            # Parse linker.info
            info = parse_linker_info(linker_info)
            result.update(info)
            
            # Get extension length from linker.fa
            if HAS_BIOPYTHON:
                try:
                    for record in SeqIO.parse(linker_fa, 'fasta'):
                        result['extension_length'] = len(record.seq)
                        break
                except:
                    pass
        
        # Fallback: If direct connection, fill Connected Read from direct.check log
        try:
            if (str(result.get('connected_read', 'NA')).strip().lower() in ('na', '', 'none')) or \
               (str(result.get('connection_type', 'NA')).strip().lower() in ('na', '', 'none')):
                dlog = chr_end_dir / 'direct.check' / 'direct.check.log'
                if dlog.exists():
                    text = dlog.read_text(encoding='utf-8', errors='ignore')
                    m_read = re.search(r'Connected Read:\s*(.+)', text)
                    if m_read:
                        rid = m_read.group(1).strip()
                        if rid:
                            result['connected_read'] = rid
                            # If connection type unknown, mark as Direct and rounds 0
                            if str(result.get('connection_type', 'NA')).strip().lower() in ('na', '', 'none'):
                                result['connection_type'] = 'Direct'
                                result['round_num'] = '0'
                            # Treat as successful connection for display
                            result['extended'] = True
        except Exception:
            pass
        
        results.append(result)
    
    return results


def parse_linker_info(linker_info_file: Path) -> Dict:
    """
    Parse linker.info file.
    
    FIXED: Handle the actual format from TelSeekerPart2
    """
    info = {
        'connection_type': 'NA',
        'round_num': 'NA',
        'connected_read': 'NA'
    }
    
    try:
        with open(linker_info_file, 'r') as f:
            lines = [line.strip() for line in f.readlines()]
        
        # Look for connection type
        for i, line in enumerate(lines):
            # Check for "Status: Direct connection found"
            if 'Status:' in line and 'Direct' in line:
                info['connection_type'] = 'Direct'
                info['round_num'] = '0'
            
            # Check for "Extension Rounds:"
            if 'Extension Rounds:' in line or 'Rounds:' in line:
                info['connection_type'] = 'Extension'
                parts = line.split(':')
                if len(parts) >= 2:
                    try:
                        info['round_num'] = parts[1].strip()
                    except:
                        pass
            
            # Check for connected read ID
            if 'Connected' in line and 'read' in line.lower() and ':' in line:
                parts = line.split(':', 1)
                if len(parts) >= 2:
                    info['connected_read'] = parts[1].strip()
    
    except Exception as e:
        print(f"    ⚠ Error parsing {linker_info_file}: {e}")
    
    return info


def parse_part3_integration(part3_dir: Path) -> Dict:
    """
    Parse part3 integration results.
    
    FIXED: Handle the actual CSV format from TelSeeker.py Part3
    """
    stats = {
        'csv_exists': False,
        'total_ends': 0,
        'extended_ends': 0,
        'direct_connections': 0,
        'extension_connections': 0,
        'failed_ends': 0
    }
    
    csv_file = part3_dir / 'check_part2_jobs.csv'
    if not csv_file.exists():
        print(f"  ⚠ check_part2_jobs.csv not found: {csv_file}")
        return stats
    
    stats['csv_exists'] = True
    
    with open(csv_file, 'r') as f:
        header = f.readline()  # Skip header: Chr_end,Extended,Connected_read,Round_num,Connection_type
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split(',')
            if len(parts) >= 5:
                stats['total_ends'] += 1
                extended = parts[1].strip().lower()
                conn_type = parts[4].strip().lower()
                
                if extended == 'yes':
                    stats['extended_ends'] += 1
                    if conn_type == 'direct':
                        stats['direct_connections'] += 1
                    elif conn_type == 'extension':
                        stats['extension_connections'] += 1
                else:
                    stats['failed_ends'] += 1
    
    print(f"    ✓ Parsed {stats['total_ends']} chromosome ends from check_part2_jobs.csv")
    print(f"      Extended: {stats['extended_ends']}, Failed: {stats['failed_ends']}")
    
    return stats


def parse_need_extension_list(out_dir: Path) -> List[str]:
    """
    Parse need_extension_chr_end.txt to get the confirmed task list.
    
    Returns:
        List of chromosome ends that need extension
    """
    need_ext_file = out_dir / 'genome.telomere.check' / 'need_extension_chr_end.txt'
    
    if not need_ext_file.exists():
        print(f"  ⚠ need_extension_chr_end.txt not found: {need_ext_file}")
        return []
    
    chr_ends = []
    try:
        with open(need_ext_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    chr_ends.append(line)
        
        print(f"  ✓ Found {len(chr_ends)} chromosome ends to extend")
        return chr_ends
    except Exception as e:
        print(f"  ⚠ Error reading need_extension_chr_end.txt: {e}")
        return []


def normalize_chr_end_key(value: str) -> str:
    """Normalize chromosome-end labels to <chromosome>.L or <chromosome>.R."""
    value = str(value or '').strip()
    if '.' not in value:
        return value

    chromosome, end = value.rsplit('.', 1)
    normalized_end = end.strip().upper()
    if normalized_end in {'L', 'LEFT'}:
        return f'{chromosome}.L'
    if normalized_end in {'R', 'RIGHT'}:
        return f'{chromosome}.R'
    return value


def parse_manual_review_sequences(
    left_file: Path,
    right_file: Path,
    sequence_base_href: str,
    plot_base_href: str,
) -> List[Dict]:
    """Build chromosome-end review rows from the generated left/right FASTA files."""
    rows = []

    def read_fasta_entries(fasta_file: Path):
        if HAS_BIOPYTHON:
            with open(fasta_file, 'r') as handle:
                for record in SeqIO.parse(handle, 'fasta'):
                    yield record.id, len(record.seq)
            return

        record_id = None
        sequence_length = 0
        with open(fasta_file, 'r') as handle:
            for line in handle:
                line = line.strip()
                if line.startswith('>'):
                    if record_id is not None:
                        yield record_id, sequence_length
                    record_id = line[1:].split()[0]
                    sequence_length = 0
                elif record_id is not None:
                    sequence_length += len(line)
        if record_id is not None:
            yield record_id, sequence_length

    for end, fasta_file in (('L', left_file), ('R', right_file)):
        if not fasta_file.exists():
            continue

        for record_id, sequence_length in read_fasta_entries(fasta_file):
            suffix = f'_{end}'
            chromosome = record_id[:-len(suffix)] if record_id.endswith(suffix) else record_id
            plot_file = fasta_file.parent / f'{chromosome}_telomere_motif.png'
            rows.append({
                'chromosome': chromosome,
                'end': end,
                'chr_end': f'{chromosome}.{end}',
                'sequence_length': sequence_length,
                'sequence_href': f'{sequence_base_href}/{fasta_file.name}',
                'plot_href': (
                    f'{plot_base_href}/{plot_file.name}' if plot_file.exists() else None
                ),
            })

    return sorted(rows, key=lambda row: (row['chromosome'], row['end']))


def get_genome_info(genome_path: Path) -> Dict:
    """Get basic genome information."""
    info = {
        'exists': genome_path.exists(),
        'size_mb': 0,
        'chromosomes': 0,
        'total_length': 0
    }
    
    if not info['exists']:
        return info
    
    info['size_mb'] = genome_path.stat().st_size / (1024 * 1024)
    
    if HAS_BIOPYTHON:
        try:
            chr_count = 0
            total_len = 0
            for record in SeqIO.parse(genome_path, 'fasta'):
                chr_count += 1
                total_len += len(record.seq)
            info['chromosomes'] = chr_count
            info['total_length'] = total_len
        except:
            pass
    
    return info


# ============================================================================
# HTML Generation (same as original, no changes needed)
# ============================================================================

def generate_html_visualization(out_dir: Path, output_path: Path, motif: str = 'TTAGGG'):
    """Generate the complete HTML visualization.
    
    Args:
        out_dir: TelSeeker output directory
        output_path: Path to write HTML file
        motif: Telomere motif sequence (default: TTAGGG)
    """
    
    print("\n" + "="*80)
    print("TelSeeker Visualization Report Generator")
    print("="*80)
    
    # Locate the manual-review evidence prepared before extension.
    print("\n[1/6] Locating initial manual-review evidence...")
    initial_check_dir = out_dir / 'genome.telomere.check'
    initial_left = initial_check_dir / 'genome.telomere.check.left.2kb.fa'
    initial_right = initial_check_dir / 'genome.telomere.check.right.2kb.fa'
    initial_combined_plot = initial_check_dir / 'all_chromosomes_combined.png'
    print(f"  Initial review directory: {initial_check_dir}")
    
    print("\n[2/6] Parsing extension task list...")
    need_extension_list = parse_need_extension_list(out_dir)
    
    print("\n[3/6] Parsing telomeric reads extraction...")
    telo_reads_stats = parse_telo_reads_stats(out_dir)
    print(f"  ✓ Total telomeric reads: {telo_reads_stats['total_reads']:,}")
    print(f"    Files found: {telo_reads_stats.get('files', [])}")
    
    print("\n[4/6] Parsing chromosome end extension results...")
    part2_dir = out_dir / 'part2.chr.end.job'
    extension_results = parse_part2_results(part2_dir)
    print(f"  ✓ Processed {len(extension_results)} chromosome ends")
    
    print("\n[5/6] Parsing final integration results...")
    part3_dir = out_dir / 'part3.integration.results'
    parse_part3_integration(part3_dir)
    
    # Locate the final manual-review evidence generated by TelSeekerCheck.
    final_check_dir = part3_dir / 'final.genome.telomere.check'
    final_left = final_check_dir / 'final.genome.telomere.check.left.2kb.fa'
    final_right = final_check_dir / 'final.genome.telomere.check.right.2kb.fa'
    final_combined_plot = final_check_dir / 'all_chromosomes_combined.png'
    print(f"  Final review directory: {final_check_dir}")

    print("\n[6/6] Generating HTML report...")

    selected_end_keys = {
        normalize_chr_end_key(chr_end) for chr_end in need_extension_list
    }
    extension_by_end = {
        normalize_chr_end_key(result.get('chr_end')): result
        for result in extension_results
    }

    initial_review_rows = parse_manual_review_sequences(
        initial_left,
        initial_right,
        '../genome.telomere.check',
        '../genome.telomere.check',
    )
    for row in initial_review_rows:
        row['selected'] = row['chr_end'] in selected_end_keys

    final_review_rows = parse_manual_review_sequences(
        final_left,
        final_right,
        '../part3.integration.results/final.genome.telomere.check',
        '../part3.integration.results/final.genome.telomere.check',
    )
    for row in final_review_rows:
        extension = extension_by_end.get(row['chr_end'])
        if extension and extension.get('extended'):
            row['extension_status'] = 'connected'
        elif extension:
            row['extension_status'] = 'failed'
        elif row['chr_end'] in selected_end_keys:
            row['extension_status'] = 'targeted'
        else:
            row['extension_status'] = 'not_targeted'
        row['manual_review'] = 'manual_review'
    
    # Prepare data for JavaScript
    js_need_extension_list = json.dumps(need_extension_list, indent=2)
    js_extension_results = json.dumps(extension_results, indent=2)
    js_initial_review_rows = json.dumps(initial_review_rows, indent=2)
    js_final_review_rows = json.dumps(final_review_rows, indent=2)

    # Reuse the plots generated by the final manual check. The visualizer must
    # not run a second, independent chromosome-end analysis.
    motif_suffix = '_telomere_motif.png'
    motif_images = sorted(final_check_dir.glob(f'*{motif_suffix}'))
    chrom_names_list = [path.name[:-len(motif_suffix)] for path in motif_images]
    js_chrom_names = json.dumps(chrom_names_list, indent=2)
    js_final_motif_base = json.dumps('../part3.integration.results/final.genome.telomere.check')

    if initial_left.exists() or initial_right.exists() or initial_combined_plot.exists():
        initial_review_html = """
                <p data-i18n-en="Review the initial chromosome-end sequences and motif plots, then select target ends manually. No automatic telomeric call is made."
                   data-i18n-zh="请查看初始染色体末端序列和 motif 图，再人工选择延伸端点；这里不做自动端粒判定。">
                    Review the initial chromosome-end sequences and motif plots, then select target ends manually. No automatic telomeric call is made.
                </p>
                <p>
                    <a href="../genome.telomere.check/genome.telomere.check.left.2kb.fa">Left-end FASTA</a> |
                    <a href="../genome.telomere.check/genome.telomere.check.right.2kb.fa">Right-end FASTA</a>
                </p>
                <div class="motif-plot-container">
                    <img src="../genome.telomere.check/all_chromosomes_combined.png" alt="Initial telomere motif distribution" style="width: 100%; height: auto; display: block;">
                </div>
        """
    else:
        initial_review_html = """
                <p class="empty-state" data-i18n-en="Initial manual-review files are not present in this run. Target ends were supplied directly."
                   data-i18n-zh="本次运行中没有初始人工检查文件；延伸端点由用户直接提供。">
                    Initial manual-review files are not present in this run. Target ends were supplied directly.
                </p>
        """

    final_review_links = """
                <p>
                    <a href="../part3.integration.results/final.genome.telomere.check/final.genome.telomere.check.left.2kb.fa">Left-end FASTA</a> |
                    <a href="../part3.integration.results/final.genome.telomere.check/final.genome.telomere.check.right.2kb.fa">Right-end FASTA</a>
                </p>
    """ if final_left.exists() or final_right.exists() else """
                <p class="empty-state" data-i18n-en="Final chromosome-end review files are not available."
                   data-i18n-zh="最终染色体末端人工检查文件尚不可用。">Final chromosome-end review files are not available.</p>
    """

    if final_combined_plot.exists():
        final_motif_html = """
        <div class="card">
            <div class="card-header" style="display: flex; justify-content: space-between; align-items: center;">
                <span data-i18n-en="📊 7. Final Genome Motif Distribution" data-i18n-zh="📊 7. 最终基因组 Motif 分布">📊 7. Final Genome Motif Distribution</span>
                <select id="motif-chr-selector" class="chr-selector">
                    <option value="all" data-i18n-en="All Chromosomes" data-i18n-zh="所有染色体" selected>All Chromosomes</option>
                </select>
            </div>
            <div class="card-content">
                <div class="motif-plot-container">
                    <img id="motif-plot-img" src="../part3.integration.results/final.genome.telomere.check/all_chromosomes_combined.png" alt="Final telomere motif distribution" style="width: 100%; height: auto; display: block;">
                </div>
            </div>
        </div>
        """
    else:
        final_motif_html = """
        <div class="card">
            <div class="card-header" data-i18n-en="📊 7. Final Genome Motif Distribution" data-i18n-zh="📊 7. 最终基因组 Motif 分布">📊 7. Final Genome Motif Distribution</div>
            <div class="card-content"><p class="empty-state">No final motif plots available</p></div>
        </div>
        """
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TelSeeker Results Visualization</title>
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
            color: #3498db;
            box-shadow: 0 4px 10px rgba(0,0,0,0.15);
        }}

        .language-btn:focus {{
            outline: none;
            box-shadow: 0 0 0 2px rgba(255,255,255,0.6);
        }}

        .stats-overview {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .stat-card {{
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            text-align: center;
            transition: transform 0.2s ease;
        }}

        .stat-card:hover {{
            transform: translateY(-5px);
        }}

        .stat-value {{
            font-size: 2.2em;
            font-weight: bold;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}

        .stat-label {{
            color: #666;
            margin-top: 8px;
            font-size: 1em;
            font-weight: 500;
        }}

        .stat-value.positive {{
            background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}

        .stat-value.negative {{
            background: linear-gradient(135deg, #dc3545 0%, #e74c3c 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}

        .card {{
            background: white;
            border-radius: 15px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            margin-bottom: 30px;
            overflow: hidden;
        }}

        .card-header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 25px;
            font-size: 1.2em;
            font-weight: 600;
        }}

        .card-content {{
            padding: 25px;
        }}

        .table-container {{
            max-height: 600px;
            overflow-y: auto;
            border: 1px solid #dee2e6;
            border-radius: 10px;
            background: white;
            position: relative;
        }}
        
        table {{
            width: 100%;
            border-collapse: separate;  /* Important for sticky headers */
            border-spacing: 0;          /* Keep cell borders touching */
        }}

        th, td {{
            padding: 15px 12px;
            text-align: left;
            border-bottom: 1px solid #f1f3f4;
        }}

        th, thead th {{
            background: #f8f9fa;
            font-weight: 600;
            position: sticky;
            top: 0;
            z-index: 20;  /* ensure header stays above cells */
            color: #495057;
            box-shadow: 0 2px 2px -1px rgba(0, 0, 0, 0.1);
        }}

        tr:hover {{
            background-color: #f8f9fa;
        }}
        
        .table-container thead {{
            position: sticky; /* enhances cross-browser behavior */
            top: 0;
            z-index: 15;
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

        .badge-selected, .badge-targeted {{
            background: #dbeafe;
            color: #1d4ed8;
        }}

        .badge-connected {{
            background: #dcfce7;
            color: #166534;
        }}

        .badge-failed {{
            background: #ffedd5;
            color: #9a3412;
        }}

        .badge-not-targeted {{
            background: #e5e7eb;
            color: #4b5563;
        }}

        .badge-manual-review {{
            background: #ede9fe;
            color: #6d28d9;
        }}

        .review-evidence a {{
            margin-right: 10px;
            white-space: nowrap;
        }}

        .chromosome-task-tracks {{
            display: grid;
            gap: 14px;
            margin: 24px 0;
        }}

        .task-track {{
            display: grid;
            grid-template-columns: minmax(100px, 180px) 1fr;
            align-items: center;
            gap: 18px;
        }}

        .task-track-name {{
            font-weight: 600;
            color: #495057;
            overflow-wrap: anywhere;
        }}

        .task-track-bar {{
            position: relative;
            height: 24px;
            border-radius: 12px;
            background: linear-gradient(135deg, #e9ecef 0%, #dee2e6 100%);
            border: 1px solid #ced4da;
        }}

        .end-marker {{
            display: inline-block;
            width: 18px;
            height: 18px;
            border-radius: 50%;
            border: 2px solid #fff;
            box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.15);
            vertical-align: middle;
        }}

        .task-track-bar .end-marker {{
            position: absolute;
            top: 50%;
            transform: translateY(-50%);
        }}

        .task-track-bar .end-marker.left {{ left: 3px; }}
        .task-track-bar .end-marker.right {{ right: 3px; }}
        .end-marker.not-targeted {{ background: #9ca3af; }}
        .end-marker.targeted {{ background: #3b82f6; }}
        .end-marker.connected {{ background: #22c55e; }}
        .end-marker.failed {{ background: #f97316; }}

        .task-legend {{
            display: flex;
            flex-wrap: wrap;
            gap: 18px;
            color: #495057;
        }}

        .task-legend > span {{
            display: inline-flex;
            align-items: center;
            gap: 7px;
        }}


        .empty-state {{
            text-align: center;
            padding: 40px 20px;
            color: #6c757d;
            font-style: italic;
        }}

        .chr-selector {{
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

        .chr-selector:hover {{
            background: rgba(255, 255, 255, 1);
            border-color: rgba(255, 255, 255, 0.7);
            transform: translateY(-1px);
        }}

        .chr-selector:focus {{
            outline: none;
            box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.6);
        }}

        .motif-plot-container {{
            text-align: center;
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            border: 1px solid #e9ecef;
        }}

        .motif-plot-container img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        }}

        @media (max-width: 768px) {{
            .header-top {{
                flex-direction: column;
                align-items: flex-start;
            }}

            .language-switcher {{
                align-self: flex-start;
                margin-left: 0;
            }}

            .stats-overview {{
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            }}

            .task-track {{
                grid-template-columns: 1fr;
                gap: 6px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-top">
                <div class="header-info">
                    <h1 data-i18n-en="🧬 TelSeeker Results Visualization" data-i18n-zh="🧬 TelSeeker 可视化结果">🧬 TelSeeker Results Visualization</h1>
                    <p data-i18n-en="Telomere Extension Analysis Report" data-i18n-zh="端粒延伸分析报告">Telomere Extension Analysis Report</p>
                </div>
                <div class="language-switcher" role="group" aria-label="Language Switcher">
                    <button class="language-btn" data-lang="zh" type="button" aria-label="切换为中文">中文</button>
                    <button class="language-btn active" data-lang="en" type="button" aria-label="Switch to English">EN</button>
                </div>
            </div>
        </div>

        <!-- Section 1: Initial manual review -->
        <div class="card">
            <div class="card-header" data-i18n-en="🔎 1. Initial Chromosome-End Manual Review" data-i18n-zh="🔎 1. 初始染色体末端人工检查">🔎 1. Initial Chromosome-End Manual Review</div>
            <div class="card-content">
                {initial_review_html}
                <div class="table-container">
                    <table id="initial-review-table">
                        <thead>
                            <tr>
                                <th>Chromosome</th>
                                <th>End</th>
                                <th>Sequence Length</th>
                                <th data-i18n-en="Selected Target" data-i18n-zh="人工选择目标">Selected Target</th>
                                <th data-i18n-en="Review Evidence" data-i18n-zh="检查证据">Review Evidence</th>
                            </tr>
                        </thead>
                        <tbody id="initial-review-tbody"></tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- Section 2: Extension Task List -->
        <div class="card">
            <div class="card-header" data-i18n-en="📋 2. Extension Task List" data-i18n-zh="📋 2. 延伸任务列表">📋 2. Extension Task List</div>
            <div class="card-content">
                <div style="margin-bottom: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #667eea;">
                    <h4 style="margin: 0 0 10px 0; color: #495057;" data-i18n-en="User-selected chromosome ends:" data-i18n-zh="用户选择的染色体端：">User-selected chromosome ends:</h4>
                    <p style="margin: 0 0 15px 0; color: #6c757d; font-size: 0.95em;" data-i18n-en="These target ends were supplied explicitly with -e/--target_ends after manual review." data-i18n-zh="这些目标端点由人工检查后通过 -e/--target_ends 明确提供。">
                        These target ends were supplied explicitly with -e/--target_ends after manual review.
                    </p>
                    <div id="need-extension-list" style="font-family: 'Courier New', monospace; font-size: 0.9em;">
                        <!-- Populated by JavaScript -->
                    </div>
                </div>
            </div>
        </div>

        <!-- Section 3: Telomeric Reads Extraction -->
        <div class="card">
            <div class="card-header" data-i18n-en="🔍 3. Telomeric Reads Extraction" data-i18n-zh="🔍 3. 端粒 Reads 提取">🔍 3. Telomeric Reads Extraction</div>
            <div class="card-content">
                <div class="stats-overview">
                    <div class="stat-card">
                        <div class="stat-value">{telo_reads_stats['total_reads']:,}</div>
                        <div class="stat-label" data-i18n-en="Total Telo Reads" data-i18n-zh="端粒Reads总数">Total Telo Reads</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{telo_reads_stats.get('left_reads', 0):,}</div>
                        <div class="stat-label" data-i18n-en="Left Telo Reads" data-i18n-zh="左端粒Reads">Left Telo Reads</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{telo_reads_stats.get('right_reads', 0):,}</div>
                        <div class="stat-label" data-i18n-en="Right Telo Reads" data-i18n-zh="右端粒Reads">Right Telo Reads</div>
                    </div>
                </div>
                <div style="margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px;">
                    <h4 style="margin: 0 0 10px 0; color: #495057;" data-i18n-en="Extracted Files:" data-i18n-zh="提取到的文件：">Extracted Files:</h4>
                    <ul style="margin: 0; padding-left: 20px; color: #6c757d;" data-i18n-wrapper="file-list">
                        {"".join(f"<li>{f}</li>" for f in telo_reads_stats.get('files', [])) if telo_reads_stats.get('files') else "<li data-i18n-en='No files found' data-i18n-zh='未找到文件'>No files found</li>"}
                    </ul>
                </div>
            </div>
        </div>

        <!-- Section 4: Chromosome End Extension -->
        <div class="card">
            <div class="card-header" data-i18n-en="🔗 4. Chromosome End Extension" data-i18n-zh="🔗 4. 染色体端延伸">🔗 4. Chromosome End Extension</div>
            <div class="card-content">
                <div class="table-container">
                    <table id="extension-table">
                        <thead>
                            <tr>
                                <th>Chr End</th>
                                <th>Extended</th>
                                <th>Connection Type</th>
                                <th>Rounds</th>
                                <th>Extension Length</th>
                                <th>Connected Read</th>
                                <th>Details</th>
                            </tr>
                        </thead>
                        <tbody id="extension-tbody">
                            <!-- Populated by JavaScript -->
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- Section 5: Final manual review -->
        <div class="card">
            <div class="card-header" data-i18n-en="🔎 5. Final Chromosome-End Manual Review" data-i18n-zh="🔎 5. 最终染色体末端人工检查">🔎 5. Final Chromosome-End Manual Review</div>
            <div class="card-content">
                <p data-i18n-en="Review the final chromosome-end sequences and motif plots manually. A successful extension means that a linker was produced; it is not an automatic telomere-completeness call."
                   data-i18n-zh="请人工检查最终染色体末端序列和 motif 图。延伸成功仅表示已生成 linker，不等同于自动判定端粒完整。">
                    Review the final chromosome-end sequences and motif plots manually. A successful extension means that a linker was produced; it is not an automatic telomere-completeness call.
                </p>
                {final_review_links}
                <div class="table-container">
                    <table id="final-review-table">
                        <thead>
                            <tr>
                                <th>Chromosome</th>
                                <th>End</th>
                                <th>Sequence Length</th>
                                <th data-i18n-en="Extension Status" data-i18n-zh="延伸状态">Extension Status</th>
                                <th data-i18n-en="Review Evidence" data-i18n-zh="检查证据">Review Evidence</th>
                                <th data-i18n-en="Final Assessment" data-i18n-zh="最终判定">Final Assessment</th>
                            </tr>
                        </thead>
                        <tbody id="final-review-tbody"></tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- Section 6: task and connection status overview -->
        <div class="card">
            <div class="card-header" data-i18n-en="📊 6. Chromosome-End Task Status" data-i18n-zh="📊 6. 染色体末端任务状态">📊 6. Chromosome-End Task Status</div>
            <div class="card-content">
                <p data-i18n-en="This diagram shows target selection and extension connection status only. Connected does not mean telomere-complete."
                   data-i18n-zh="该图仅展示目标选择和延伸连接状态；Connected 不代表端粒完整。">
                    This diagram shows target selection and extension connection status only. Connected does not mean telomere-complete.
                </p>
                <div id="chromosome-task-tracks" class="chromosome-task-tracks"></div>
                <div class="task-legend">
                    <span><i class="end-marker not-targeted"></i> <span data-i18n-en="Not targeted" data-i18n-zh="未选择">Not targeted</span></span>
                    <span><i class="end-marker targeted"></i> <span data-i18n-en="Targeted" data-i18n-zh="已选择">Targeted</span></span>
                    <span><i class="end-marker connected"></i> <span data-i18n-en="Connected" data-i18n-zh="已连接">Connected</span></span>
                    <span><i class="end-marker failed"></i> <span data-i18n-en="Failed" data-i18n-zh="延伸失败">Failed</span></span>
                </div>
            </div>
        </div>

        {final_motif_html}
    </div>

    <script>
        // Data from Python
        const needExtensionList = {js_need_extension_list};
        const extensionResults = {js_extension_results};
        const initialReviewRows = {js_initial_review_rows};
        const finalReviewRows = {js_final_review_rows};
        const motifChromosomes = {js_chrom_names};
        const finalMotifBase = {js_final_motif_base};

        let currentLang = 'en';
        let languageButtons = [];

        const translations = {{
            en: {{
                no_extension_needed: 'No target chromosome ends were supplied.',
                yes: 'Yes',
                no: 'No',
                sequence: 'Sequence',
                motif_plot: 'Motif plot',
                connected: 'Connected',
                failed: 'Failed',
                targeted: 'Targeted',
                not_targeted: 'Not targeted',
                manual_review: 'Manual review',
                no_review_data: 'No chromosome-end review data available.'
            }},
            zh: {{
                no_extension_needed: '未提供需要延伸的目标染色体端。',
                yes: '是',
                no: '否',
                sequence: '末端序列',
                motif_plot: 'Motif 图',
                connected: '已连接',
                failed: '延伸失败',
                targeted: '已选择',
                not_targeted: '未选择',
                manual_review: '人工检查',
                no_review_data: '没有可用的染色体末端检查数据。'
            }}
        }};

        function t(key) {{
            const langPack = translations[currentLang] || translations.en;
            if (langPack && Object.prototype.hasOwnProperty.call(langPack, key)) {{
                return langPack[key];
            }}
            if (translations.en && Object.prototype.hasOwnProperty.call(translations.en, key)) {{
                return translations.en[key];
            }}
            return key;
        }}

        function applyAttributeTranslations(lang) {{
            const langAttr = lang === 'zh' ? 'zh-CN' : 'en';
            document.documentElement.setAttribute('lang', langAttr);
            document.querySelectorAll('[data-i18n-en]').forEach((node) => {{
                const value = node.getAttribute('data-i18n-' + lang);
                if (value !== null) {{
                    node.innerHTML = value;
                }}
            }});
        }}

        function setActiveLanguageButton() {{
            languageButtons.forEach((btn) => {{
                const isActive = btn.getAttribute('data-lang') === currentLang;
                if (isActive) {{
                    btn.classList.add('active');
                    btn.setAttribute('aria-pressed', 'true');
                }} else {{
                    btn.classList.remove('active');
                    btn.setAttribute('aria-pressed', 'false');
                }}
            }});
        }}

        function getConnectionTypeLabel(type) {{
            if (!type) {{
                return 'NA';
            }}
            const normalized = String(type).trim().toLowerCase();
            if (normalized === 'direct') {{
                return 'Direct';
            }}
            if (normalized === 'extension') {{
                return 'Extension';
            }}
            if (normalized === 'na' || normalized === 'n/a' || normalized === 'none') {{
                return 'NA';
            }}
            return type;
        }}


        function refreshLanguageSensitiveContent() {{
            populateInitialReviewTable();
            populateNeedExtensionList();
            populateExtensionTable();
            populateFinalReviewTable();
            generateChromosomeTaskTracks();
            // Update i18n in motif selector options
            try {{
                const sel = document.getElementById('motif-chr-selector');
                if (sel) {{
                    const firstOpt = sel.querySelector('option[value="all"]');
                    if (firstOpt) {{
                        const label = currentLang === 'zh' ? '所有染色体' : 'All Chromosomes';
                        firstOpt.textContent = label;
                    }}
                }}
            }} catch (e) {{}}
        }}

        function updateLanguage(lang) {{
            if (!lang) {{
                return;
            }}
            if (currentLang === lang) {{
                applyAttributeTranslations(currentLang);
                refreshLanguageSensitiveContent();
                setActiveLanguageButton();
                return;
            }}
            currentLang = lang;
            applyAttributeTranslations(currentLang);
            refreshLanguageSensitiveContent();
            setActiveLanguageButton();
        }}

        document.addEventListener('DOMContentLoaded', () => {{
            languageButtons = Array.prototype.slice.call(document.querySelectorAll('.language-btn'));
            if (languageButtons.length) {{
                languageButtons.forEach((btn) => {{
                    btn.addEventListener('click', () => {{
                        const lang = btn.getAttribute('data-lang');
                        updateLanguage(lang);
                    }});
                }});
            }}
            applyAttributeTranslations(currentLang);
            refreshLanguageSensitiveContent();
            setActiveLanguageButton();

            // Initialize motif selector
            const motifSelector = document.getElementById('motif-chr-selector');
            const motifImg = document.getElementById('motif-plot-img');
            if (motifSelector && motifImg) {{
                // Populate selector options
                try {{
                    // Add per-chromosome options
                    (motifChromosomes || []).forEach(chr => {{
                        const opt = document.createElement('option');
                        opt.value = chr;
                        opt.textContent = chr;
                        motifSelector.appendChild(opt);
                    }});
                }} catch (e) {{}}

                motifSelector.addEventListener('change', () => {{
                    const val = motifSelector.value;
                    if (val === 'all') {{
                        motifImg.src = finalMotifBase + '/all_chromosomes_combined.png';
                    }} else {{
                        motifImg.src = finalMotifBase + '/' + val + '_telomere_motif.png';
                    }}
                }});
            }}
        }});

        function escapeHtml(value) {{
            return String(value ?? '')
                .replaceAll('&', '&amp;')
                .replaceAll('<', '&lt;')
                .replaceAll('>', '&gt;')
                .replaceAll('"', '&quot;')
                .replaceAll("'", '&#039;');
        }}

        function evidenceLinks(row) {{
            const links = [];
            if (row.sequence_href) {{
                links.push(`<a href="${{escapeHtml(row.sequence_href)}}">${{t('sequence')}}</a>`);
            }}
            if (row.plot_href) {{
                links.push(`<a href="${{escapeHtml(row.plot_href)}}">${{t('motif_plot')}}</a>`);
            }}
            return links.length ? links.join(' ') : '-';
        }}

        function populateInitialReviewTable() {{
            const tbody = document.getElementById('initial-review-tbody');
            if (!tbody) return;
            tbody.innerHTML = '';

            if (initialReviewRows.length === 0) {{
                tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${{t('no_review_data')}}</td></tr>`;
                return;
            }}

            initialReviewRows.forEach(row => {{
                const tr = document.createElement('tr');
                const selectedClass = row.selected ? 'selected' : 'not-targeted';
                const selectedLabel = row.selected ? t('yes') : t('no');
                tr.innerHTML = `
                    <td>${{escapeHtml(row.chromosome)}}</td>
                    <td>${{escapeHtml(row.end)}}</td>
                    <td>${{Number(row.sequence_length || 0).toLocaleString()}} bp</td>
                    <td><span class="badge badge-${{selectedClass}}">${{selectedLabel}}</span></td>
                    <td class="review-evidence">${{evidenceLinks(row)}}</td>
                `;
                tbody.appendChild(tr);
            }});
        }}

        function populateFinalReviewTable() {{
            const tbody = document.getElementById('final-review-tbody');
            if (!tbody) return;
            tbody.innerHTML = '';

            if (finalReviewRows.length === 0) {{
                tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${{t('no_review_data')}}</td></tr>`;
                return;
            }}

            finalReviewRows.forEach(row => {{
                const status = row.extension_status || 'not_targeted';
                const statusClass = status.replaceAll('_', '-');
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${{escapeHtml(row.chromosome)}}</td>
                    <td>${{escapeHtml(row.end)}}</td>
                    <td>${{Number(row.sequence_length || 0).toLocaleString()}} bp</td>
                    <td><span class="badge badge-${{statusClass}}">${{t(status)}}</span></td>
                    <td class="review-evidence">${{evidenceLinks(row)}}</td>
                    <td><span class="badge badge-manual-review">${{t('manual_review')}}</span></td>
                `;
                tbody.appendChild(tr);
            }});
        }}

        function generateChromosomeTaskTracks() {{
            const container = document.getElementById('chromosome-task-tracks');
            if (!container) return;
            container.innerHTML = '';

            const sourceRows = finalReviewRows.length
                ? finalReviewRows
                : initialReviewRows.map(row => ({{
                    ...row,
                    extension_status: row.selected ? 'targeted' : 'not_targeted'
                }}));
            if (sourceRows.length === 0) {{
                container.innerHTML = `<div class="empty-state">${{t('no_review_data')}}</div>`;
                return;
            }}

            const chromosomeEnds = {{}};
            sourceRows.forEach(row => {{
                if (!chromosomeEnds[row.chromosome]) chromosomeEnds[row.chromosome] = {{}};
                chromosomeEnds[row.chromosome][row.end] = row.extension_status || 'not_targeted';
            }});

            Object.keys(chromosomeEnds).sort().forEach(chromosome => {{
                const ends = chromosomeEnds[chromosome];
                const leftStatus = ends.L || 'not_targeted';
                const rightStatus = ends.R || 'not_targeted';
                const track = document.createElement('div');
                track.className = 'task-track';
                track.innerHTML = `
                    <div class="task-track-name">${{escapeHtml(chromosome)}}</div>
                    <div class="task-track-bar">
                        <i class="end-marker left ${{leftStatus.replaceAll('_', '-')}}" title="L: ${{t(leftStatus)}}"></i>
                        <i class="end-marker right ${{rightStatus.replaceAll('_', '-')}}" title="R: ${{t(rightStatus)}}"></i>
                    </div>
                `;
                container.appendChild(track);
            }});
        }}

        // Populate need extension list
        function populateNeedExtensionList() {{
            const container = document.getElementById('need-extension-list');
            container.innerHTML = '';
            
            if (needExtensionList.length === 0) {{
                const msg = document.createElement('p');
                msg.style.color = '#6c757d';
                msg.style.fontStyle = 'italic';
                msg.textContent = t('no_extension_needed');
                container.appendChild(msg);
                return;
            }}
            
            const list = document.createElement('ul');
            list.style.margin = '0';
            list.style.padding = '0 0 0 20px';
            list.style.listStyle = 'none';
            
            needExtensionList.forEach((chrEnd, index) => {{
                const li = document.createElement('li');
                li.style.padding = '8px 12px';
                li.style.marginBottom = '5px';
                li.style.background = '#fff';
                li.style.border = '1px solid #dee2e6';
                li.style.borderRadius = '5px';
                li.style.display = 'flex';
                li.style.alignItems = 'center';
                
                const badge = document.createElement('span');
                badge.textContent = (index + 1);
                badge.style.display = 'inline-block';
                badge.style.width = '24px';
                badge.style.height = '24px';
                badge.style.lineHeight = '24px';
                badge.style.textAlign = 'center';
                badge.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
                badge.style.color = 'white';
                badge.style.borderRadius = '50%';
                badge.style.marginRight = '12px';
                badge.style.fontSize = '0.85em';
                badge.style.fontWeight = 'bold';
                
                const text = document.createElement('span');
                text.textContent = chrEnd;
                text.style.color = '#495057';
                text.style.fontWeight = '500';
                
                li.appendChild(badge);
                li.appendChild(text);
                list.appendChild(li);
            }});
            
            container.appendChild(list);
        }}

        // Populate extension table
        function populateExtensionTable() {{
            const tbody = document.getElementById('extension-tbody');
            tbody.innerHTML = '';
            
            if (extensionResults.length === 0) {{
                tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No extension data available</td></tr>';
                return;
            }}
            
            extensionResults.forEach(row => {{
                const tr = document.createElement('tr');
                const normalizedType = row.connection_type ? String(row.connection_type).trim().toLowerCase() : 'na';
                const connTypeBadge = normalizedType === 'direct' ? 'direct' :
                                      normalizedType === 'extension' ? 'extension' : 'na';
                const extendedLabel = row.extended ? 'Yes' : 'No';
                const connectionTypeLabel = getConnectionTypeLabel(row.connection_type);
                const reportFileName = `${{row.chr_end}}.report.html`;
                tr.innerHTML = `
                    <td>${{row.chr_end}}</td>
                    <td><span class="badge badge-${{row.extended ? 'yes' : 'no'}}">${{extendedLabel}}</span></td>
                    <td><span class="badge badge-${{connTypeBadge}}">${{connectionTypeLabel}}</span></td>
                    <td>${{row.round_num}}</td>
                    <td>${{row.extension_length > 0 ? row.extension_length.toLocaleString() + ' bp' : '-'}}</td>
                    <td style="font-size: 0.85em; color: #6c757d;">${{row.connected_read}}</td>
                    <td><a href="${{reportFileName}}" target="_blank" rel="noopener" title="View detailed report for ${{row.chr_end}}">View</a></td>
                `;
                tbody.appendChild(tr);
            }});
        }}

    </script>
</body>
</html>"""
    
    # Write HTML file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"\n✓ HTML report generated successfully!")
    print(f"  Output: {output_path}")
    print(f"\n{'='*80}\n")


# ============================================================================
# Main Function
# ============================================================================


def generate_all_task_reports(out_dir: Path) -> Tuple[int, int]:
    """
    生成所有单任务报告
    
    Returns:
        (success_count, total_count)
    """
    job_dir = out_dir / 'part2.chr.end.job'
    if not job_dir.exists():
        print(f"  ⚠ Job directory not found: {job_dir}")
        return 0, 0
    
    task_dirs = [d for d in job_dir.iterdir() if d.is_dir()]
    if not task_dirs:
        print(f"  ⚠ No task directories found in {job_dir}")
        return 0, 0
    
    print(f"Found {len(task_dirs)} tasks to process\n")
    
    visual_report_dir = out_dir / 'visual.report'
    visual_report_dir.mkdir(parents=True, exist_ok=True)
    
    success_count = 0
    for task_dir in sorted(task_dirs):
        try:
            chr_end_name = task_dir.name
            print(f"  Processing {chr_end_name}...", end=" ")
            
            # 1. 解析日志
            parser = TelSeekerPart2LogParser(task_dir)
            data = parser.parse()
            
            # 2. 生成HTML
            generator = Part2HTMLReportGenerator(data=data, output_dir=visual_report_dir)
            report_file = generator.generate()
            
            # 3. 重命名
            target_report = visual_report_dir / f'{chr_end_name}.report.html'
            if report_file.exists():
                if target_report.exists():
                    target_report.unlink()
                report_file.rename(target_report)
                print(f"✓")
                success_count += 1
            else:
                print(f"✗ (failed)")
        except Exception as e:
            print(f"✗ (error: {e})")
    
    return success_count, len(task_dirs)

def main():
    parser = argparse.ArgumentParser(
        description='Generate interactive HTML visualization for TelSeeker results'
    )
    parser.add_argument(
        '--out',
        required=True,
        help='TelSeeker output directory path'
    )
    parser.add_argument(
        '-m', '--motif',
        default='TTAGGG',
        help='Telomere motif sequence (default: TTAGGG for vertebrates)'
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*80)
    print("TelSeeker Visualization Report Generator")
    print("="*80)
    print()
    
    # Validate output directory
    out_dir = Path(args.out)
    if not out_dir.exists():
        print(f"Error: Output directory does not exist: {out_dir}")
        sys.exit(1)
    
    # Check for required files
    initial_check = out_dir / 'genome.telomere.check'
    if not initial_check.exists():
        print(f"Warning: Initial telomere check not found: {initial_check}")
        print("  This may indicate TelSeeker has not been run yet.")
    
    # Generate output path to visual.report directory
    visual_report_dir = out_dir / 'visual.report'
    visual_report_dir.mkdir(parents=True, exist_ok=True)
    
    # Validate motif
    motif = args.motif.upper()
    if not motif or not all(c in 'ACGT' for c in motif):
        print(f"Error: Invalid motif '{args.motif}'. Must contain only A, C, G, T.")
        sys.exit(1)
    
    # ========================================
    # 1. Generate Global Report
    # ========================================
    print("\n[1/2] Generating Global Report...")
    print("-" * 80)
    output_path = visual_report_dir / 'Global.report.html'
    generate_html_visualization(out_dir, output_path, motif=motif)
    print(f"  ✓ Global report: {output_path}")
    
    # ========================================
    # 2. Generate Task Reports
    # ========================================
    print("\n[2/2] Generating Task Reports...")
    print("-" * 80)
    success_count, total_count = generate_all_task_reports(out_dir)
    if total_count > 0:
        print(f"  ✓ Task reports: {success_count}/{total_count} successful")
    
    # ========================================
    # Summary
    # ========================================
    print("\n" + "="*80)
    print("Report Generation Complete")
    print("="*80)
    print(f"Output directory: {visual_report_dir}")
    print(f"  - Global.report.html      : Global overview")
    if total_count > 0:
        print(f"  - <Chr.X>.report.html     : {total_count} task reports")
    print("\nOpen Global.report.html in a web browser to view the results.")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
