#!/usr/bin/env python3
"""
DEGAP v2 Gapfiller 可视化工具 - 重构版
动态展示gap填充过程的HTML报告生成器
"""

import os
import re
import json
import argparse
from datetime import datetime
from pathlib import Path


class GapfillerLogParser:
    """解析gapfiller日志文件"""

    def __init__(self, log_file, summary_file=None, result_dir=None):
        self.log_file = log_file
        self.summary_file = summary_file
        self.result_dir = Path(result_dir) if result_dir else None
        self.rounds_data = []
        self.initial_info = {}
        self.final_info = {}
        self.direct_connection_info = {}
        
    def parse_log(self):
        """解析process.log文件"""
        with open(self.log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 解析直接连接检查信息
        self._parse_direct_connection(content)
        
        # 解析初始信息
        self._parse_initial_info(content)
        
        # 解析每轮extension信息
        self._parse_extension_rounds(content)
        
        # 解析最终结果
        self._parse_final_info(content)
        
        # 如果有summary文件，补充详细信息
        if self.summary_file and os.path.exists(self.summary_file):
            self._parse_summary()
            
        return {
            'direct_connection': self.direct_connection_info,
            'initial_info': self.initial_info,
            'rounds': self.rounds_data,
            'final_info': self.final_info
        }

    def _get_translation(self, key, lang='zh'):
        """获取翻译文本"""
        translations = {
            'zh': {
                'direct_connection': '✅ 直接连接',
                'partial_pass': '❌ 部分达标',
                'not_meet_standard': '❌ 不符合直接连接标准',
                'length_insufficient': '比对长度不足',
                'identity_insufficient': '序列一致性不足',
                'left_too_far': 'Left序列距离右端过远',
                'right_too_far': 'Right序列距离左端过远',
                'meets_degap_standard': '✅ 符合DEGAPv2标准',
                'length_pass': '长度达标',
                'identity_pass': '一致性达标',
                'position_pass': '位置达标',
                'pass': '✅ 通过',
                'fail': '❌ 不通过',
                'no_alignment_data_to_analyze': '无比对数据可分析',
                'position_failure_reason': '{count}条记录位置不符合要求(距离边缘>{edge}bp)',
                'length_failure_reason': '{count}条记录比对长度不足(<10,000bp)',
                'identity_failure_reason': '{count}条记录序列一致性不足(<80%)',
                'failure_separator': '，',
                'no_qualified_alignment': '未找到符合DEGAPv2直接连接条件的比对',
                'analysis_no_pass': '共找到 {total} 条比对记录，但均未达到DEGAPv2直接连接标准。具体原因：{reasons}。DEGAPv2要求比对长度≥10,000bp、序列一致性≥80%且距离序列边缘≤{edge}bp，因此需要进行Gap填充。',
                'analysis_partial_pass': '共找到 {total} 条比对记录，其中 {passed} 条达到DEGAPv2直接连接标准，但可能由于其他因素（如序列方向、结构变异等）最终未能实现直接连接，因此进入了Gap填充流程。'
            },
            'en': {
                'direct_connection': '✅ Direct Connection',
                'partial_pass': '❌ Partially Qualified',
                'not_meet_standard': '❌ Does not meet direct connection standard',
                'length_insufficient': 'Alignment length insufficient',
                'identity_insufficient': 'Sequence identity insufficient',
                'left_too_far': 'Left sequence too far from right end',
                'right_too_far': 'Right sequence too far from left end',
                'meets_degap_standard': '✅ Meets DEGAPv2 standard',
                'length_pass': 'Length qualified',
                'identity_pass': 'Identity qualified',
                'position_pass': 'Position qualified',
                'pass': '✅ Pass',
                'fail': '❌ Fail',
                'no_alignment_data_to_analyze': 'No alignment data to analyze',
                'position_failure_reason': '{count} records failed position requirement (distance from edge >{edge}bp)',
                'length_failure_reason': '{count} records failed length requirement (<10,000bp)',
                'identity_failure_reason': '{count} records failed identity requirement (<80%)',
                'failure_separator': ', ',
                'no_qualified_alignment': 'No alignments meeting DEGAPv2 direct connection criteria found',
                'analysis_no_pass': 'Found {total} alignment records, but none met DEGAPv2 direct connection standards. Specific reasons: {reasons}. DEGAPv2 requires alignment length ≥10,000bp, sequence identity ≥80%, and distance from sequence edges ≤{edge}bp, therefore Gap filling is required.',
                'analysis_partial_pass': 'Found {total} alignment records, of which {passed} met DEGAPv2 direct connection standards, but may not have achieved direct connection due to other factors (such as sequence orientation, structural variations, etc.), therefore entered Gap filling process.'
            }
        }
        return translations.get(lang, {}).get(key, key)

    def _parse_direct_connection(self, content):
        """解析直接连接检查信息"""
        # 模式1：传统 GapFiller 格式（新版，包含 Mode: single sequence）
        traditional_new_pattern = (
            r'========== Direct Connection Check ==========\n'
            r'(?:Left file sequences: \d+\n)?'
            r'(?:Right file sequences: \d+\n)?'
            r'Mode: single sequence vs single sequence \(traditional\)\n'
            r'Original left sequence length: (\d+)bp\n'
            r'Original right sequence length: (\d+)bp\n'
            r'Seed sequence: [^,]+, length: \d+bp\n'
            r'Using seed length: (\d+)bp\n'
        )
        
        match = re.search(traditional_new_pattern, content, re.DOTALL)
        if match:
            left_length = int(match.group(1))
            right_length = int(match.group(2))
            seed_length = int(match.group(3))
            
            # 检查是否找到了直连
            connection_found = '*** Found direct connection! ***' in content
            
            # 解析连接的 edge
            connected_edge = None
            edge_match = re.search(r'Connected edge: (\S+)', content)
            if edge_match:
                connected_edge = edge_match.group(1)
            
            # 解析 GAP Length
            gap_length = None
            gap_match = re.search(r'GAP Length: ([-\d]+)', content)
            if gap_match:
                gap_length = int(gap_match.group(1))
            
            result_text = f"Found direct connection to {connected_edge}" if connection_found and connected_edge else ("Found direct connection" if connection_found else "No valid direct connection found")
            
            self.direct_connection_info = {
                'left_length': left_length,
                'right_length': right_length,
                'seed_length': seed_length,
                'left_fragment_length': seed_length,
                'right_fragment_length': seed_length,
                'alignment_file': './direct_connection_check/direct_connection_0.delta.filter.coords',
                'connection_found': connection_found,
                'result_text': result_text,
                'gap_length': gap_length,
                'connected_edge': connected_edge
            }
            return
        
        # 模式2：传统 GapFiller/TelSeeker 格式（旧版）
        direct_check_pattern = (
            r'========== Direct Connection Check ==========\n'
            r'Original left sequence length: (\d+)bp\n'
            r'Original right sequence length: (\d+)bp\n'
            r'Using seed length: (\d+)bp\n'
            r'Flag=(?:left|right): extracting [^\n]+\n'
            r'Left fragment length: (\d+)bp\n'
            r'Right fragment length: (\d+)bp\n'
            r'Running mummer alignment: ([^\n]+)\n'
            r'(?:.*?\n)*?'  # 匹配任意多行中间内容
            r'(No valid direct connection found|Valid direct connection found|Found direct connection)'
        )

        match = re.search(direct_check_pattern, content, re.DOTALL)
        if match:
            # 将服务器路径转换为本地路径
            alignment_file = match.group(6)
            if 'direct_connection_check' in alignment_file:
                local_alignment_file = './direct_connection_check/direct_connection.delta.filter.coords'
            else:
                local_alignment_file = alignment_file

            self.direct_connection_info = {
                'left_length': int(match.group(1)),        # 原始左序列长度
                'right_length': int(match.group(2)),       # 原始右序列长度
                'seed_length': int(match.group(3)),        # 种子序列长度
                'left_fragment_length': int(match.group(4)),  # 左片段长度
                'right_fragment_length': int(match.group(5)), # 右片段长度
                'alignment_file': local_alignment_file,
                'connection_found': 'Valid' in match.group(7) or 'Found direct connection' in match.group(7),
                'result_text': match.group(7)
            }
            return
        
        # 模式2：CtgLinker 格式
        ctglinker_pattern = (
            r'========== Direct Connection Check ==========\n'
            r'(?:Left file sequences: \d+\n)?'
            r'(?:Right file sequences: \d+\n)?'
            r'Mode: CtgLinker[^\n]*\n'
            r'Seed sequence: ([^,]+), length: (\d+)bp\n'
            r'Using seed length: (\d+)bp\n'
        )
        
        match = re.search(ctglinker_pattern, content, re.DOTALL)
        if match:
            seed_id = match.group(1)
            seed_length = int(match.group(2))  # 完整 seed contig 长度
            fragment_length = int(match.group(3))  # 用于比对的片段长度（seedlen）
            
            # 检查是否找到了直连
            connection_found = '*** Found direct connection! ***' in content
            
            # 解析连接的 edge
            connected_edge = None
            edge_match = re.search(r'Connected edge: (\S+)', content)
            if edge_match:
                connected_edge = edge_match.group(1)
            
            # ✨ 修复：解析原始序列长度
            # 优先从新格式字段获取（Connected edge original length / Seed original length）
            edge_original_length = None
            seed_original_length = None
            
            # 方法1（优先）：从新格式字段获取（直连成功时）
            edge_len_match = re.search(r'Connected edge original length: (\d+)bp', content)
            seed_len_match = re.search(r'Seed original length: (\d+)bp', content)
            if edge_len_match:
                edge_original_length = int(edge_len_match.group(1))
                print(f"[DEBUG] 从 'Connected edge original length' 获取 edge 长度: {edge_original_length}")
            if seed_len_match:
                seed_original_length = int(seed_len_match.group(1))
                print(f"[DEBUG] 从 'Seed original length' 获取 seed 长度: {seed_original_length}")
            
            # 方法2（回退）：从 initialSeqnenceLength 获取 seed 长度
            if seed_original_length is None:
                initial_len_match = re.search(r'initialSeqnenceLength:\s*(\d+)', content)
                if initial_len_match:
                    seed_original_length = int(initial_len_match.group(1))
                else:
                    seed_original_length = seed_length  # 最终回退到 seed_length
            
            # 方法3（回退）：从 "Linked ctg:" 比对数据获取 edge 长度（延伸成功时）
            if edge_original_length is None:
                linked_ctg_match = re.search(r'Linked ctg:\s*(\S+)\n([^\n]+)', content)
                if linked_ctg_match:
                    alignment_line = linked_ctg_match.group(2)
                    parts = alignment_line.split('\t')
                    if len(parts) >= 8:
                        try:
                            # parts[7] 是 terminal/edge 序列的总长度
                            edge_original_length = int(parts[7])
                            print(f"[DEBUG] 从 'Linked ctg' 比对数据获取 edge 长度: {edge_original_length}")
                        except (ValueError, IndexError) as e:
                            print(f"[DEBUG] 解析 Linked ctg 比对数据失败: {e}")
            
            # 方法4（最终回退）：使用 seed 长度作为近似
            if edge_original_length is None:
                edge_original_length = seed_original_length
                print(f"[DEBUG] edge 长度未找到，使用 seed 长度作为近似: {edge_original_length}")
            
            # 解析 Mode 行，确定 seqleft 和 seqright 的含义
            # 格式: "Mode: CtgLinker - edge library (left, X edges) vs seed (right)"
            # 或: "Mode: CtgLinker - seed (left) vs edge library (right, X edges)"
            mode_match = re.search(r'Mode: CtgLinker.*edge library \((\w+)', content)
            edge_is_left = True  # 默认 edge 在左边
            if mode_match:
                edge_position = mode_match.group(1)
                edge_is_left = (edge_position == 'left')
            
            # 根据 edge 的位置确定 left_length 和 right_length
            if edge_is_left:
                # edge library 在左边，seed contig 在右边
                # seqleft = edge library，seqright = seed contig
                left_length = edge_original_length  # edge 的原始长度
                right_length = seed_original_length # seed contig 的原始长度
            else:
                # seed contig 在左边，edge library 在右边
                # seqleft = seed contig，seqright = edge library
                left_length = seed_original_length  # seed contig 的原始长度
                right_length = edge_original_length # edge 的原始长度
            
            # 解析 GAP Length
            gap_length = None
            gap_match = re.search(r'GAP Length: ([-\d]+)', content)
            if gap_match:
                gap_length = int(gap_match.group(1))
            
            # 构建结果文本
            if connection_found:
                result_text = f"Found direct connection to {connected_edge}" if connected_edge else "Found direct connection"
            else:
                result_text = "No valid direct connection found"
            
            # ✨ 修复：选择第一个符合直连标准的比对结果文件
            # 直连标准：比对长度 ≥ 10,000bp，一致性 ≥ 80%，距离边缘 ≤ 500bp
            alignment_file = None
            if self.result_dir:
                direct_conn_dir = self.result_dir / 'direct_connection_check'
                if direct_conn_dir.exists():
                    coords_files = sorted(direct_conn_dir.glob('direct_connection_*.delta.filter.coords'))
                    for coords_file in coords_files:
                        if coords_file.stat().st_size > 0:
                            # 检查文件中是否有符合直连标准的比对
                            try:
                                with open(coords_file, 'r') as f:
                                    for line in f:
                                        if line.strip() and not line.startswith('#'):
                                            parts = line.strip().split('\t')
                                            if len(parts) >= 9:
                                                align_len = int(parts[4])  # 比对长度
                                                identity = float(parts[6])  # 一致性
                                                left_total = int(parts[7])  # 左序列总长
                                                right_total = int(parts[8])  # 右序列总长
                                                # 计算距离边缘
                                                left_start, left_end = int(parts[0]), int(parts[1])
                                                right_start, right_end = int(parts[2]), int(parts[3])
                                                left_edge_dist = min(left_start - 1, left_total - left_end)
                                                right_edge_dist = min(right_start - 1, right_total - right_end)
                                                
                                                # 检查是否符合直连标准
                                                if align_len >= 10000 and identity >= 80.0 and left_edge_dist <= 500 and right_edge_dist <= 500:
                                                    alignment_file = f'./direct_connection_check/{coords_file.name}'
                                                    break
                                    if alignment_file:
                                        break
                            except Exception as e:
                                print(f"[DEBUG] 解析 {coords_file} 失败: {e}")
                                continue
            
            if not alignment_file:
                alignment_file = './direct_connection_check/direct_connection.delta.filter.coords'
            
            self.direct_connection_info = {
                'left_length': left_length,       # 左序列的原始长度
                'right_length': right_length,     # 右序列的原始长度
                'seed_length': fragment_length,   # 用于比对的片段长度
                'left_fragment_length': fragment_length,
                'right_fragment_length': fragment_length,
                'alignment_file': alignment_file,
                'connection_found': connection_found,
                'result_text': result_text,
                'connected_edge': connected_edge,
                'gap_length': gap_length,
                'mode': 'ctglinker'
            }
    
    def _parse_initial_info(self, content):
        """解析初始序列信息"""
        # 解析种子序列长度信息
        hifi_seed_match = re.search(r'hifiSeedSequenceLength: (\d+)', content)
        ont_seed_match = re.search(r'ontSeedSequenceLength: (\d+)', content)
        primary_seed_match = re.search(r'seedSequenceLength: (\d+)', content)

        # 确定数据类型
        data_type = 'hifi'  # 默认
        if hifi_seed_match and ont_seed_match:
            data_type = 'mixed'
        elif ont_seed_match and not hifi_seed_match:
            data_type = 'ont'

        if self.direct_connection_info:
            self.initial_info = {
                'left_length': self.direct_connection_info['left_length'],           # 原始左序列长度
                'right_length': self.direct_connection_info['right_length'],         # 原始右序列长度
                'left_fragment_length': self.direct_connection_info.get('left_fragment_length', self.direct_connection_info['left_length']),   # 左片段长度
                'right_fragment_length': self.direct_connection_info.get('right_fragment_length', self.direct_connection_info['right_length']), # 右片段长度
                'seed_length': self.direct_connection_info.get('seed_length', 1000), # 种子序列长度
                'direct_connection': self.direct_connection_info['connection_found'],
                # 添加种子序列长度信息
                'hifi_seed_len': int(hifi_seed_match.group(1)) if hifi_seed_match else 76759,
                'ont_seed_len': int(ont_seed_match.group(1)) if ont_seed_match else 868730,
                'primary_seed_len': int(primary_seed_match.group(1)) if primary_seed_match else 76759,
                'data_type': data_type
            }
    
    def _parse_extension_rounds(self, content):
        """解析每轮extension信息"""
        # 匹配每轮extension的模式 - 修复正则表达式
        round_pattern = r'\*+\s*ExtensionRound (\d+)\s*\*+(.*?)(?=\*+\s*ExtensionRound|\*+\s*Final|\Z)'

        rounds = re.findall(round_pattern, content, re.DOTALL)

        for round_num, round_content in rounds:
            round_data = self._parse_single_round(int(round_num), round_content)
            if round_data:
                self.rounds_data.append(round_data)
    
    def _parse_single_round(self, round_num, content):
        """解析单轮extension信息"""
        round_data = {'round': round_num}

        # 解析基本信息
        patterns = {
            'input_length': r'initialSeqnenceLength: (\d+)',
            'extension_reads_num': r'extensionReadsNum: (\d+)',
            'extension_length': r'extensionLength: (-?\d+)',
            'output_length': r'outputSequenceLength: (\d+)',
            'used_reads_num': r'usedReadsNum: (\d+)',
            'extension_method': r'extensionSequneceNote: ([^\n]+)',
            'extension_contig': r'Extension: ([^\n]+)',
            'total_extension_length': r'totalExtensionLength: (\d+)'
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, content)
            if match:
                if key == 'extension_method' or key == 'extension_contig':
                    round_data[key] = match.group(1).strip()
                else:
                    round_data[key] = int(match.group(1))

        # 检查gap状态
        if 'GAP can be closed!' in content:
            round_data['gap_closed'] = True
            round_data['gap_status'] = 'closed'
            # 解析gap长度
            gap_length_match = re.search(r'GAP Length: (\d+)', content)
            if gap_length_match:
                round_data['gap_length'] = int(gap_length_match.group(1))
        elif 'GAP still not closed!' in content:
            round_data['gap_closed'] = False
            round_data['gap_status'] = 'open'

        # 检查是否无延伸发现
        if round_data.get('extension_length', 0) == 0:
            round_data['extension_status'] = 'no_extension'
        elif round_data.get('extension_length', 0) > 0:
            round_data['extension_status'] = 'extended'

        # 解析使用的reads列表 - 在当前轮次内容中查找
        # 修复：使用更通用的模式匹配所有reads，不限制前缀
        used_reads_pattern = r'usedReads:\n((?:\s+[^\n]+\n)*?)(?=\s*usedNewReads|\s*outputFile|\s*\*|\Z)'
        used_reads_match = re.search(used_reads_pattern, content, re.DOTALL)
        if used_reads_match:
            reads_text = used_reads_match.group(1)
            reads_list = [line.strip() for line in reads_text.split('\n') if line.strip()]
            round_data['used_reads_list'] = reads_list
        else:
            round_data['used_reads_list'] = []

        # 解析outputExtensionSequence.log信息（新增）
        # 计算到当前轮次的累计延申长度
        cumulative_extension = sum(r.get('extension_length', 0) for r in self.rounds_data if r.get('round', 0) <= round_num)
        round_data['extension_alignment'] = self._parse_round_extension_alignment(round_num, cumulative_extension)

        # 分析下一步操作（新增）
        round_data['next_action'] = self._analyze_next_action(round_data)

        return round_data

    def _parse_round_extension_alignment(self, round_num, cumulative_extension_length=0):
        """解析每轮的outputExtensionSequence.log文件"""
        try:
            # 构建round目录路径
            if self.result_dir:
                round_dir = self.result_dir / f"process/round{round_num}"
            else:
                # 从log文件路径推断结果目录
                log_dir = Path(self.log_file).parent
                round_dir = log_dir / f"process/round{round_num}"

            output_log_file = round_dir / "outputExtensionSequence.log"

            if not output_log_file.exists():
                return None

            alignment_info = {}
            with open(output_log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # 支持两种格式：flag=left使用linkedSequenceAln，flag=right使用selectContigNote
                    if line.startswith('linkedSequenceAln'):
                        # flag=left格式：解析比对信息：a	b	c	d	len1	len2	identity	seq1_len	seq2_len	cov1	cov2	seq1_name	seq2_name
                        parts = line.split('\t')[1:]  # 去掉'linkedSequenceAln'标签
                        print(f"[DEBUG] linkedSequenceAln: parts数量={len(parts)}, parts={parts}")
                        if len(parts) >= 13:
                            # 注意：对于flag=left，数据格式是：
                            # Right序列区域 | Left+Extension序列区域 | ... | Right序列名 | Left+Extension序列名

                            # 原始坐标（基于完整序列）
                            original_terminal_start = int(parts[0])
                            original_terminal_end = int(parts[1])
                            original_extension_start = int(parts[2])
                            original_extension_end = int(parts[3])

                            # 暂时保存原始坐标，稍后在HTML生成时进行转换
                            alignment_info = {
                                'terminal_start': original_terminal_start,      # 原始Right序列起始位置
                                'terminal_end': original_terminal_end,          # 原始Right序列结束位置
                                'extension_start': original_extension_start,    # 原始Left+Extension序列起始位置
                                'extension_end': original_extension_end,        # 原始Left+Extension序列结束位置
                                'terminal_align_len': int(parts[4]),   # Right序列比对长度
                                'extension_align_len': int(parts[5]),  # Left+Extension序列比对长度
                                'identity': float(parts[6]),           # 序列一致性
                                'terminal_total_len': int(parts[7]),   # 原始Right序列总长度
                                'extension_total_len': int(parts[8]),  # 原始Left+Extension序列总长度
                                'terminal_coverage': float(parts[9]),  # Right序列覆盖度
                                'extension_coverage': float(parts[10]), # Left+Extension序列覆盖度
                                'terminal_name': parts[11],            # Right序列名称
                                'extension_name': parts[12],           # Left+Extension序列名称
                                # 标记需要坐标转换
                                'needs_coordinate_conversion': True,
                                # 修复：添加正确的累计延申长度
                                'cumulative_extension_length': cumulative_extension_length
                            }

                            # 判断是否满足gap闭合标准（≥10000bp）
                            alignment_info['meets_gap_closure_standard'] = alignment_info['terminal_align_len'] >= 10000

                            # 计算gap长度和连接信息
                            alignment_info['gap_length'] = self._calculate_gap_length(alignment_info)

                    elif line.startswith('selectContigNote') and 'Extensionseq alignment:' in line:
                        # flag=right格式：selectContigNote\tExtensionseq alignment:29986598\t30000000\t1\t13418\t13403\t13418\t99.57\t30000000\t59007418\t65.38\t65.45\tContig-0-edge-right\tExtensionSequence-DG2-Left
                        # 提取比对数据部分 - 注意冒号后面直接跟着第一个数字
                        alignment_part = line.split('Extensionseq alignment:')[1]
                        # 先用制表符分割
                        raw_parts = alignment_part.split('\t')
                        # 第一个元素可能是 "29986598" 或者包含空格的情况
                        # 重新组装 parts 列表
                        parts = []
                        for p in raw_parts:
                            p = p.strip()
                            if p:
                                parts.append(p)
                        print(f"[DEBUG] 解析 Extensionseq alignment: parts数量={len(parts)}, parts={parts}")
                        if len(parts) >= 13:
                            # 注意：对于flag=right，数据格式是：
                            # Left序列区域 | Right+Extension序列区域 | ... | Left序列名 | Right+Extension序列名
                            # 这与flag=left相反：flag=left是Right序列区域 | Left+Extension序列区域

                            # 原始坐标（基于完整序列）
                            original_terminal_start = int(parts[0])
                            original_terminal_end = int(parts[1])
                            original_extension_start = int(parts[2])
                            original_extension_end = int(parts[3])

                            # 暂时保存原始坐标，稍后在HTML生成时进行转换
                            alignment_info = {
                                'terminal_start': original_terminal_start,      # 原始Left序列起始位置
                                'terminal_end': original_terminal_end,          # 原始Left序列结束位置
                                'extension_start': original_extension_start,    # 原始Right+Extension序列起始位置
                                'extension_end': original_extension_end,        # 原始Right+Extension序列结束位置
                                'terminal_align_len': int(parts[4]),   # Left序列比对长度
                                'extension_align_len': int(parts[5]),  # Right+Extension序列比对长度
                                'identity': float(parts[6]),           # 序列一致性
                                'terminal_total_len': int(parts[7]),   # 原始Left序列总长度
                                'extension_total_len': int(parts[8]),  # 原始Right+Extension序列总长度
                                'terminal_coverage': float(parts[9]),  # Left序列覆盖度
                                'extension_coverage': float(parts[10]), # Right+Extension序列覆盖度
                                'terminal_name': parts[11],            # Left序列名称
                                'extension_name': parts[12],           # Right+Extension序列名称
                                # 标记需要坐标转换
                                'needs_coordinate_conversion': True,
                                # 修复：添加正确的累计延申长度
                                'cumulative_extension_length': cumulative_extension_length
                            }

                            # 判断是否满足gap闭合标准（≥10000bp）
                            alignment_info['meets_gap_closure_standard'] = alignment_info['terminal_align_len'] >= 10000

                            # 计算gap长度和连接信息
                            alignment_info['gap_length'] = self._calculate_gap_length(alignment_info)

                    elif line.startswith('linkedSequenceNote'):
                        note_content = line.split('\t', 1)[1] if '\t' in line else ''
                        if 'ExtensionSequence can close the GAP!' in note_content:
                            alignment_info['can_close_gap'] = True
                        elif 'GAP still not closed!' in note_content:
                            alignment_info['can_close_gap'] = False

            return alignment_info if alignment_info else None

        except Exception as e:
            print(f"Warning: Could not parse round {round_num} extension alignment: {e}")
            return None

    def _calculate_gap_length(self, alignment_info):
        """根据比对信息计算gap长度"""
        # 从比对信息中获取terminal序列的比对长度
        # 这个长度表示延伸序列与terminal序列的重叠长度
        return alignment_info.get('terminal_align_len', 0)

    def _analyze_next_action(self, round_data):
        """分析下一步操作"""
        if round_data.get('gap_closed'):
            return {
                'action': 'gap_closed',
                'description': 'Gap已成功闭合，延伸过程结束',
                'reason': f"延伸序列与terminalSeq的比对长度达到{round_data.get('gap_length', 'N/A')}bp，满足闭合标准"
            }
        elif round_data.get('extension_status') == 'no_extension':
            return {
                'action': 'no_extension_end',
                'description': '本轮未能延伸，结束延伸过程',
                'reason': '未找到合适的extension reads或contigs进行延伸'
            }
        elif round_data.get('extension_status') == 'extended':
            # 检查是否达到最大延伸长度
            total_length = round_data.get('total_extension_length', 0)
            max_extension_length = self.max_extension_length if hasattr(self, 'max_extension_length') and self.max_extension_length else 1000000
            if total_length >= max_extension_length:
                return {
                    'action': 'max_length_reached',
                    'description': '达到最大延伸长度限制，结束延伸过程',
                    'reason': f'总延伸长度已达到{total_length:,}bp，超过最大限制({max_extension_length:,}bp)'
                }
            else:
                return {
                    'action': 'continue_extension',
                    'description': '进入下一轮延伸',
                    'reason': f'本轮成功延伸{round_data.get("extension_length", 0):,}bp，但尚未达到terminalSeq，继续延伸'
                }
        else:
            return {
                'action': 'unknown',
                'description': '状态未知',
                'reason': '无法确定下一步操作'
            }

    def _parse_final_info(self, content):
        """解析最终结果信息"""
        # 查找最终结果部分
        final_match = re.search(
            r'Final ExtensionSequence: ([^\n]+)\n'
            r'Final EXtendFile: ([^\n]+)',
            content
        )
        
        if final_match:
            self.final_info = {
                'final_sequence_id': final_match.group(1).strip(),
                'final_file': final_match.group(2).strip()
            }
        
        # 检查是否使用了直接连接结果（而不是延伸结果）
        used_direct_connection = (
            'Decided to use direct connection result' in content or
            'Using direct connection result file' in content or
            '_direct_overlap' in self.final_info.get('final_sequence_id', '')
        )
        
        # 检查最终状态
        if 'GAP can be closed!' in content:
            # 如果使用了直接连接结果，说明延伸失败了
            if used_direct_connection:
                self.final_info['success'] = False  # extension失败
                self.final_info['extension_success'] = False
                self.final_info['used_direct_connection'] = True
                self.final_info['status'] = 'used_direct_connection'
                self.final_info['overall_success'] = True  # 但整体成功（通过直接连接）
            else:
                # 通过延伸成功连接
                self.final_info['success'] = True
                self.final_info['extension_success'] = True
                self.final_info['used_direct_connection'] = False
                self.final_info['status'] = 'success'
                self.final_info['overall_success'] = True
            
            # 解析最终统计信息
            gap_length_match = re.search(r'GAP Length: (\d+)', content)
            linked_length_match = re.search(r'Linked Sequence Length: (\d+)', content)
            
            if gap_length_match:
                self.final_info['gap_length'] = int(gap_length_match.group(1))
            if linked_length_match:
                self.final_info['linked_length'] = int(linked_length_match.group(1))
        else:
            self.final_info['success'] = False
            self.final_info['extension_success'] = False
            self.final_info['used_direct_connection'] = False
            self.final_info['overall_success'] = False
            # 判断失败原因
            if 'Reached maximum extension rounds' in content:
                self.final_info['status'] = 'max_rounds_reached'
            elif self.rounds_data:
                last_round = self.rounds_data[-1]
                if last_round.get('extension_status') == 'no_extension':
                    self.final_info['status'] = 'no_extension'
                else:
                    self.final_info['status'] = 'max_extension_reached'
            else:
                self.final_info['status'] = 'failed'
    
    def _parse_summary(self):
        """解析summary文件补充详细信息"""
        try:
            with open(self.summary_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            for line in lines:
                if line.strip():
                    parts = line.strip().split('\t')
                    if len(parts) >= 8 and parts[0].startswith('round'):
                        round_num = int(parts[0].replace('round', ''))
                        
                        # 找到对应的round数据
                        for round_data in self.rounds_data:
                            if round_data['round'] == round_num:
                                round_data['summary_input_length'] = int(parts[1])
                                round_data['summary_output_length'] = int(parts[2])
                                round_data['summary_extension_length'] = int(parts[3])
                                round_data['summary_contig_id'] = parts[4]
                                round_data['summary_used_reads_num'] = int(parts[5])
                                break
        except Exception as e:
            print(f"Warning: Could not parse summary file: {e}")


class HTMLReportGenerator:
    """生成HTML可视化报告"""

    def __init__(self, data, output_dir, result_dir=None, max_extension_length=None, extension_flag='left'):
        self.data = data
        self.output_dir = Path(output_dir)
        self.result_dir = Path(result_dir) if result_dir else None
        self.output_dir.mkdir(exist_ok=True)

        # 设置最大延伸长度
        self.max_extension_length = max_extension_length

        # 设置延伸方向flag
        self.flag = extension_flag

        # 从数据中获取种子序列长度信息
        initial_info = self.data.get('initial_info', {})
        self.hifi_seed_len = initial_info.get('hifi_seed_len', 76759)
        self.ont_seed_len = initial_info.get('ont_seed_len', 868730)
        self.primary_seed_len = initial_info.get('primary_seed_len', 76759)
        self.data_type = initial_info.get('data_type', 'hifi')

        # 注意：不再从result_dir自动推断flag，完全依赖用户传入的参数
        # 这样确保用户的--flag参数不会被覆盖
    
    def generate_report(self):
        """生成完整的HTML报告"""
        import shutil
        
        # ✨ 复制 direct_connection_check 目录到 visualization_output
        # 这样报告和数据文件在一起，路径更简单
        print(f"[DEBUG] generate_report: result_dir={self.result_dir}, output_dir={self.output_dir}")
        if self.result_dir:
            src_direct_conn = self.result_dir / 'direct_connection_check'
            print(f"[DEBUG] 检查源目录: {src_direct_conn}, exists={src_direct_conn.exists()}")
            if src_direct_conn.exists():
                dst_direct_conn = self.output_dir / 'direct_connection_check'
                try:
                    if dst_direct_conn.exists():
                        shutil.rmtree(dst_direct_conn)
                    shutil.copytree(src_direct_conn, dst_direct_conn)
                    print(f"已复制 direct_connection_check 到 {dst_direct_conn}")
                    # 验证复制成功
                    if dst_direct_conn.exists():
                        files = list(dst_direct_conn.glob('*.coords'))
                        print(f"[DEBUG] 复制后目标目录包含 {len(files)} 个 .coords 文件")
                except Exception as e:
                    print(f"Warning: 复制 direct_connection_check 失败: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"[DEBUG] 源目录不存在: {src_direct_conn}")
        else:
            print(f"[DEBUG] result_dir 未设置")
        
        html_content = self._generate_html()

        # 写入HTML文件
        html_file = self.output_dir / 'gapfiller_report.html'
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"HTML报告已生成: {html_file}")
        return html_file

    def _generate_html(self):
        """生成HTML内容"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DEGAP v2 Gapfiller 可视化报告</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        {self._get_css_styles()}
    </style>
</head>
<body>
    <div class="container">
        {self._generate_header()}
        {self._generate_direct_connection_section()}
        {self._generate_gap_visualization()}
        {self._generate_round_details()}
        {self._generate_statistics_section()}
    </div>

    <script>
        {self._generate_javascript()}
    </script>
</body>
</html>"""

    def _get_css_styles(self):
        """获取CSS样式"""
        return """
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh;
            color: #333;
            line-height: 1.6;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        .section {
            background: white;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }

        .section-title {
            font-size: 1.5em;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .header {
            text-align: center;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            position: relative;
        }

        .language-switcher {
            position: absolute;
            top: 20px;
            right: 30px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .language-btn {
            background: rgba(255, 255, 255, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.3);
            color: white;
            padding: 6px 12px;
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 12px;
            font-weight: 500;
            min-width: 40px;
        }

        .language-btn:hover {
            background: rgba(255, 255, 255, 0.3);
            transform: translateY(-1px);
        }

        .language-btn.active {
            background: rgba(255, 255, 255, 0.9);
            color: #3498db;
            font-weight: bold;
        }

        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }

        .header .subtitle {
            font-size: 1.2em;
            opacity: 0.9;
        }

        .status-badges {
            display: flex;
            justify-content: center;
            gap: 15px;
            margin-top: 20px;
            flex-wrap: wrap;
        }

        .badge {
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            color: white;
        }

        .badge-success { background: #2ecc71; }
        .badge-warning { background: #f39c12; }
        .badge-danger { background: #e74c3c; }
        .badge-info { background: #3498db; }

        .direct-connection-layout {
            display: grid;
            grid-template-columns: auto 1fr;
            gap: 25px;
            align-items: center;
            margin-bottom: 25px;
        }

        .connection-status-compact {
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 15px;
            border-radius: 10px;
            min-width: 120px;
            text-align: center;
        }

        .connection-success {
            background: linear-gradient(135deg, #2ecc71, #27ae60);
            color: white;
        }

        .connection-failed {
            background: linear-gradient(135deg, #e74c3c, #c0392b);
            color: white;
        }

        .status-icon {
            font-size: 2em;
            margin-bottom: 8px;
        }

        .status-text {
            font-weight: bold;
            font-size: 0.9em;
        }

        .connection-info {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
        }

        .info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }

        .info-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px;
            background: white;
            border-radius: 5px;
            border-left: 3px solid #3498db;
        }

        .info-label {
            font-weight: bold;
            color: #2c3e50;
        }

        .info-value {
            color: #7f8c8d;
            font-family: monospace;
        }

        .connection-standards {
            background: #e8f4fd;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 25px;
        }

        .connection-standards h4 {
            color: #2c3e50;
            margin-bottom: 15px;
        }

        .standards-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }

        .standard-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px;
            background: white;
            border-radius: 5px;
            border-left: 3px solid #f39c12;
        }

        .standard-label {
            font-weight: bold;
            color: #2c3e50;
        }

        .standard-value {
            color: #f39c12;
            font-weight: bold;
        }

        .alignment-visualization {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
        }

        .alignment-visualization h4 {
            color: #2c3e50;
            margin-bottom: 15px;
        }

        .alignment-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }



        /* 比对结果内容布局 */
        .alignment-content {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        .alignment-table-section {
            width: 100%;
        }

        .alignment-chart-section {
            width: 100%;
        }

        .synteny-chart {
            text-align: center;
            padding: 20px;
            display: flex;
            flex-direction: column;
        }

        .chart-header {
            margin-bottom: 20px;
        }

        .synteny-chart h5 {
            color: #2c3e50;
            margin: 0;
            font-size: 1.2em;
            text-align: center;
        }

        .synteny-chart svg {
            border: 1px solid #e9ecef;
            border-radius: 5px;
            background: white;
            max-width: 100%;
            height: auto;
        }

        .chart-info {
            margin-top: 20px;
            text-align: left;
            background: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            border-left: 4px solid #3498db;
        }

        .chart-info ul {
            margin: 10px 0;
            padding-left: 20px;
        }

        .chart-info li {
            margin: 5px 0;
            color: #7f8c8d;
        }

        /* 共线图分页控件样式 */
        .synteny-pagination {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 15px;
            margin: 20px 0;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
            border: 1px solid #e9ecef;
        }

        .pagination-info {
            color: #2c3e50;
            font-weight: 500;
            font-size: 0.9em;
        }

        .pagination-btn {
            background: #3498db;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 20px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s ease;
            min-width: 80px;
        }

        .pagination-btn:hover {
            background: #2980b9;
            transform: translateY(-1px);
            box-shadow: 0 3px 10px rgba(52, 152, 219, 0.3);
        }

        .pagination-btn:disabled {
            background: #bdc3c7;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }

        .page-input-group {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .page-input {
            width: 60px;
            padding: 6px 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            text-align: center;
            font-size: 14px;
        }

        .page-input:focus {
            outline: none;
            border-color: #3498db;
            box-shadow: 0 0 5px rgba(52, 152, 219, 0.3);
        }



        .status-pass {
            color: #28a745;
            font-weight: bold;
        }

        .status-fail {
            color: #dc3545;
            font-weight: bold;
        }

        /* 反向比对样式 */
        .alignment-rect.reverse {
            stroke-dasharray: 3,3;
            stroke-width: 2px;
        }

        .alignment-rect.forward {
            stroke-dasharray: none;
        }

        /* 悬停效果 */
        .alignment-rect:hover,
        .connection-line:hover,
        .alignment-label:hover {
            stroke-width: 3px !important;
            opacity: 1 !important;
        }

        .hover-area-left:hover,
        .hover-area-right:hover {
            opacity: 0.1;
            fill: #3498db;
        }

        /* 悬停时的视觉反馈 */
        .synteny-chart:hover .alignment-rect,
        .synteny-chart:hover .connection-line {
            transition: all 0.2s ease;
        }

        .alignment-file-info {
            margin-bottom: 20px;
            padding: 10px;
            background: white;
            border-radius: 5px;
            font-size: 0.9em;
        }

        .alignment-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            font-size: 0.9em;
        }

        /* 比对结果表格容器 - 限制高度并添加滚动条 */
        .alignment-table-container {
            max-height: 280px; /* 约4行数据的高度：表头(44px) + 4行数据(4*59px) = 280px */
            overflow-y: auto;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }

        .alignment-table-container .alignment-table {
            margin-top: 0;
            box-shadow: none;
            border-radius: 0;
        }

        .alignment-table th {
            background: #34495e;
            color: white;
            padding: 12px 8px;
            text-align: center;
            font-weight: bold;
            font-size: 0.85em;
            border-right: 1px solid #2c3e50;
        }

        .alignment-table th:last-child {
            border-right: none;
        }

        .alignment-table td {
            padding: 15px 8px;
            text-align: center;
            border-bottom: 1px solid #eee;
            border-right: 1px solid #f1f3f4;
            color: #34495e;
            font-weight: 500;
        }

        .alignment-table td:last-child {
            border-right: none;
        }

        .alignment-table tr.hover {
            background: #f8f9fa;
            cursor: pointer;
        }

        .alignment-table tbody tr.selected {
            background: #e3f2fd !important;
            border-left: 3px solid #2196f3;
            font-weight: 500;
        }

        .alignment-table tbody tr.selected.hover {
            background: #e3f2fd !important;
        }

        .alignment-table td.pass {
            background: #d5f4e6;
            color: #27ae60;
            font-weight: bold;
        }

        .alignment-table td.fail {
            background: #fadbd8;
            color: #e74c3c;
            font-weight: bold;
        }

        .alignment-row.pass {
            background: #f8fff8;
        }

        .alignment-row.fail {
            background: #fff8f8;
        }

        .status-pass {
            color: #27ae60;
            font-weight: bold;
        }

        .status-fail {
            color: #e74c3c;
            font-weight: bold;
        }

        .reason-text {
            font-size: 0.9em;
            color: #e74c3c;
            font-style: italic;
        }

        .standards-note {
            margin-top: 15px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 5px;
            border-left: 4px solid #3498db;
        }

        .standards-note p {
            margin: 0 0 10px 0;
            color: #2c3e50;
            font-weight: bold;
        }

        .standards-note ul {
            margin: 0;
            padding-left: 20px;
        }

        .standards-note li {
            margin: 5px 0;
            color: #7f8c8d;
        }

        .alignment-summary {
            margin-top: 15px;
            padding: 15px;
            background: white;
            border-radius: 5px;
            border-left: 4px solid #3498db;
        }

        .summary-note {
            color: #2c3e50;
            line-height: 1.6;
        }

        .gap-visualization {
            padding: 20px 0;
        }

        .chromosome-diagram {
            margin: 30px 0;
            padding: 20px;
            background: #ffffff;
            border-radius: 15px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            display: flex;
            justify-content: center;
            align-items: center;
        }

        .chromosome-svg {
            width: 100%;
            max-width: 1400px;
            height: 200px;
            display: block;
        }

        .chromosome-arm {
            stroke-width: 2;
            stroke: #2c3e50;
        }

        .left-arm {
            fill: url(#leftGradient);
        }

        .right-arm {
            fill: url(#rightGradient);
        }

        .gap-region-svg {
            fill: #ecf0f1;
            stroke: #bdc3c7;
            stroke-width: 2;
            stroke-dasharray: 5,5;
        }

        .extension-fill {
            fill: url(#extensionGradient);
            transition: width 0.8s ease;
        }

        .chromosome-label {
            font-family: 'Arial', sans-serif;
            font-size: 12px;
            font-weight: bold;
            fill: #2c3e50;
        }

        .sequence-length-label {
            font-family: 'Arial', sans-serif;
            font-size: 10px;
            fill: #7f8c8d;
        }



        .status-display {
            text-align: center;
            margin: 25px 0;
            font-size: 1.1em;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 10px;
            border-left: 4px solid #3498db;
        }

        .round-switcher {
            margin-top: 20px;
            padding: 12px;
            background: #f8f9fa;
            border-radius: 8px;
            border: 1px solid #e9ecef;
        }

        .round-switcher-title {
            display: none;
        }

        .timeline-container {
            display: flex;
            justify-content: center;
            align-items: center;
            margin: 8px 0;
            gap: 15px;
        }

        .timeline {
            display: flex;
            justify-content: center;
            align-items: center;
            flex-wrap: wrap;
            gap: 6px;
        }

        .timeline-nav-btn {
            width: 28px;
            height: 28px;
            border-radius: 50%;
            border: 2px solid #3498db;
            background: white;
            color: #3498db;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 14px;
            user-select: none;
        }

        .timeline-nav-btn:hover {
            background: #3498db;
            color: white;
            transform: scale(1.05);
        }

        .timeline-nav-btn:disabled {
            border-color: #bdc3c7;
            color: #bdc3c7;
            cursor: not-allowed;
            background: #f8f9fa;
        }

        .timeline-nav-btn:disabled:hover {
            transform: none;
            background: #f8f9fa;
            color: #bdc3c7;
        }

        .timeline-point {
            width: 24px;
            height: 24px;
            border-radius: 50%;
            border: 2px solid #bdc3c7;
            background: white;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 10px;
            color: #7f8c8d;
        }

        .timeline-point:hover {
            transform: scale(1.05);
            border-color: #3498db;
        }

        .timeline-point.active {
            background: #3498db;
            border-color: #3498db;
            color: white;
            transform: scale(1.1);
        }

        .timeline-point.completed {
            background: #2ecc71;
            border-color: #2ecc71;
            color: white;
        }

        .timeline-point.failed {
            background: #e74c3c;
            border-color: #e74c3c;
            color: white;
        }

        .timeline-line {
            height: 2px;
            background: #bdc3c7;
            flex: 1;
            max-width: 30px;
        }

        .timeline-line.completed {
            background: #2ecc71;
        }

        .round-info {
            display: none;
        }

        /* 轮次详情子卡片样式 */
        .round-detail-card {
            margin-top: 20px;
            padding: 20px;
            background: white;
            border-radius: 10px;
            border-left: 4px solid #3498db;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }

        .round-detail-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #e9ecef;
        }

        .round-detail-title {
            font-size: 1.1em;
            font-weight: bold;
            color: #2c3e50;
        }

        .round-detail-status {
            font-size: 0.9em;
        }

        .round-detail-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 15px;
        }

        .round-detail-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 15px;
            background: #f8f9fa;
            border-radius: 6px;
            border-left: 3px solid #3498db;
        }

        .round-detail-label {
            font-weight: 600;
            color: #2c3e50;
            font-size: 0.9em;
        }

        .round-detail-value {
            color: #34495e;
            font-weight: 500;
            font-size: 0.9em;
        }

        .round-detail-reads {
            margin-top: 15px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 6px;
            border-left: 3px solid #95a5a6;
        }

        .round-detail-reads h6 {
            margin: 0 0 10px 0;
            color: #2c3e50;
            font-size: 0.95em;
        }

        .reads-list {
            font-family: monospace;
            font-size: 0.8em;
            line-height: 1.4;
            max-height: 150px;
            overflow-y: auto;
        }

        .reads-item {
            margin: 2px 0;
            padding: 2px 5px;
            background: white;
            border-radius: 3px;
            color: #495057;
        }

        .controls {
            display: flex;
            justify-content: center;
            gap: 15px;
            margin: 20px 0;
            flex-wrap: wrap;
        }

        .btn {
            background: linear-gradient(45deg, #3498db, #2980b9);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 25px;
            cursor: pointer;
            font-size: 16px;
            transition: all 0.3s ease;
            font-weight: bold;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(52, 152, 219, 0.4);
        }

        .btn:disabled {
            background: #bdc3c7;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }

        .btn-success { background: linear-gradient(45deg, #2ecc71, #27ae60); }
        .btn-warning { background: linear-gradient(45deg, #f39c12, #e67e22); }
        .btn-danger { background: linear-gradient(45deg, #e74c3c, #c0392b); }

        .round-details {
            display: none;
            animation: fadeIn 0.5s ease;
        }

        .round-details.active {
            display: block;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .details-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            font-size: 0.9em;
        }

        .details-table th {
            background: #34495e;
            color: white;
            padding: 12px 8px;
            text-align: center;
            font-weight: bold;
            font-size: 0.85em;
            border-right: 1px solid #2c3e50;
        }

        .details-table th:last-child {
            border-right: none;
        }

        .details-table td {
            padding: 15px 8px;
            text-align: center;
            border-bottom: 1px solid #eee;
            border-right: 1px solid #f1f3f4;
            color: #34495e;
            font-weight: 500;
        }

        .details-table td:last-child {
            border-right: none;
        }

        .details-table tr:hover {
            background: #f8f9fa;
        }

        .statistics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }

        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }

        .stat-card h3 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }

        .stat-card p {
            opacity: 0.9;
            font-size: 1.1em;
        }

        .statistics-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }

        .statistics-table td {
            padding: 15px 20px;
            border-bottom: 1px solid #eee;
        }

        .statistics-table tr:last-child td {
            border-bottom: none;
        }

        .statistics-table tr:hover {
            background: #f8f9fa;
        }

        .stat-label {
            font-weight: 600;
            color: #2c3e50;
            width: 40%;
        }

        .stat-value {
            color: #34495e;
            font-weight: 500;
        }

        .stat-value .badge {
            font-size: 1em;
            padding: 5px 12px;
        }

        /* 横向统计表格样式 */
        .statistics-table-horizontal {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            font-size: 0.9em;
        }

        .statistics-table-horizontal th {
            background: #34495e;
            color: white;
            padding: 12px 8px;
            text-align: center;
            font-weight: bold;
            font-size: 0.85em;
            border-right: 1px solid #2c3e50;
        }

        .statistics-table-horizontal th:last-child {
            border-right: none;
        }

        .statistics-table-horizontal td {
            padding: 15px 8px;
            text-align: center;
            border-bottom: 1px solid #eee;
            border-right: 1px solid #f1f3f4;
            color: #34495e;
            font-weight: 500;
        }

        .statistics-table-horizontal td:last-child {
            border-right: none;
        }

        .statistics-table-horizontal tr:hover {
            background: #f8f9fa;
        }

        .statistics-table-horizontal .badge {
            font-size: 0.9em;
            padding: 5px 10px;
            white-space: nowrap;
        }

        /* 连接状态说明样式 */
        .connection-status-explanation {
            margin-top: 25px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
            border-left: 4px solid #3498db;
        }

        .connection-status-explanation h4 {
            color: #2c3e50;
            margin-bottom: 15px;
            font-size: 1.1em;
        }

        .connection-status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }

        .status-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 15px;
            background: white;
            border-radius: 8px;
            border-left: 3px solid #3498db;
        }

        .status-item.final-result {
            border-left-color: #e67e22;
            background: #fef9e7;
        }

        .status-label {
            font-weight: bold;
            color: #2c3e50;
        }

        .status-result {
            font-weight: 600;
            color: #34495e;
        }

        .logic-explanation {
            background: white;
            padding: 15px;
            border-radius: 8px;
            border-left: 3px solid #27ae60;
        }

        .logic-explanation p {
            margin: 0 0 10px 0;
            color: #2c3e50;
            font-weight: bold;
        }

        .logic-explanation ul {
            margin: 0;
            padding-left: 20px;
        }

        .logic-explanation li {
            margin: 5px 0;
            color: #7f8c8d;
            line-height: 1.5;
        }

        /* 初始状态信息样式 */
        .initial-state-info {
            margin-bottom: 25px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
            border-left: 4px solid #3498db;
        }

        .rounds-table-container {
            margin-top: 25px;
        }

        .reads-details-section {
            margin-top: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 3px solid #95a5a6;
        }

        .progress-info {
            display: flex;
            justify-content: space-between;
            margin: 15px 0;
            font-size: 0.9em;
            color: #7f8c8d;
        }

        @media (max-width: 768px) {
            .direct-connection-layout {
                grid-template-columns: 1fr;
                gap: 15px;
            }

            .chromosome-diagram {
                flex-direction: column;
                gap: 15px;
            }

            .timeline {
                flex-direction: column;
                gap: 15px;
            }

            .timeline-line {
                width: 3px;
                height: 30px;
                max-width: none;
            }

            .timeline-point {
                width: 28px;
                height: 28px;
                font-size: 11px;
            }

            .info-grid,
            .standards-grid {
                grid-template-columns: 1fr;
            }

            .alignment-table {
                font-size: 0.8em;
            }

            .header h1 {
                font-size: 2em;
            }

            /* 移动设备上的分页控件优化 */
            .synteny-pagination {
                flex-direction: column;
                gap: 10px;
                padding: 10px;
            }

            .pagination-info {
                text-align: center;
                font-size: 0.85em;
            }

            .page-input-group {
                justify-content: center;
            }

            .pagination-btn {
                min-width: 70px;
                font-size: 12px;
                padding: 6px 12px;
            }
        }
        """

    def _generate_header(self):
        """生成页面头部"""
        final_info = self.data.get('final_info', {})
        rounds = self.data.get('rounds', [])
        direct_conn = self.data.get('direct_connection', {})

        # 确定状态 - 支持国际化
        # 优先检查 overall_success（考虑直接连接的情况）
        overall_success = final_info.get('overall_success', final_info.get('success', False))
        
        if overall_success:
            status_badge = '<span class="badge badge-success" data-i18n="status.success">✅ Gap填充成功</span>'
        elif final_info.get('status') == 'no_extension':
            status_badge = '<span class="badge badge-danger" data-i18n="status.no_extension">❌ 无延伸发现</span>'
        elif final_info.get('status') == 'max_extension_reached':
            status_badge = '<span class="badge badge-warning" data-i18n="status.max_extension">⚠️ 达到最大延伸限制</span>'
        else:
            status_badge = '<span class="badge badge-danger" data-i18n="status.failed">❌ 填充失败</span>'

        # ✨ 修复：直连成功时显示"使用直连"而不是"X 轮延伸"
        is_direct_connection = direct_conn.get('connection_found', False)
        if is_direct_connection:
            rounds_badge = '<span class="badge badge-info" data-i18n="header.direct_connection">🔗 使用直连</span>'
        else:
            rounds_badge = f'<span class="badge badge-info" data-i18n="header.rounds" data-count="{len(rounds)}">📊 {len(rounds)} 轮延伸</span>'

        return f"""
        <div class="header">
            <div class="language-switcher">
                <button class="language-btn active" onclick="switchLanguage('zh')" id="lang-zh">中文</button>
                <button class="language-btn" onclick="switchLanguage('en')" id="lang-en">EN</button>
            </div>
            <h1 data-i18n="header.title">🧬 DEGAP v2 Gapfiller 可视化报告</h1>
            <p class="subtitle" data-i18n="header.subtitle" data-time="{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}">动态展示Gap填充过程 - 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <div class="status-badges">
                {status_badge}
                {rounds_badge}
            </div>
        </div>
        """

    def _generate_direct_connection_section(self):
        """生成直接连接检查部分"""
        direct_conn = self.data.get('direct_connection', {})

        if not direct_conn:
            return ""

        connection_found = direct_conn.get('connection_found', False)
        status_class = 'badge-success' if connection_found else 'badge-danger'
        status_icon = '✅' if connection_found else '❌'
        status_key = 'direct_connection.can_connect' if connection_found else 'direct_connection.cannot_connect'
        status_text = '可以直接连接' if connection_found else '无法直接连接'

        return f"""
        <div class="section">
            <div class="section-title" data-i18n="direct_connection.title">
                🔗 直接连接检查
            </div>

            <!-- 直接连接检查统计表格 -->
            <table class="statistics-table-horizontal">
                <thead>
                    <tr>
                        <th data-i18n="direct_connection.status">处理状态</th>
                        <th data-i18n="direct_connection.left_length">左序列长度</th>
                        <th data-i18n="direct_connection.right_length">右序列长度</th>
                        <th data-i18n="direct_connection.result">检查结果</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>
                            <span class="badge {status_class}" data-i18n="{status_key}">
                                {status_icon} {status_text}
                            </span>
                        </td>
                        <td>{direct_conn.get('left_length', 'N/A'):,} bp</td>
                        <td>{direct_conn.get('right_length', 'N/A'):,} bp</td>
                        <td>{direct_conn.get('result_text', 'N/A')}</td>
                    </tr>
                </tbody>
            </table>

            <!-- 直接连接标准说明 -->
            <div class="gap-closure-standards" style="margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px; border-left: 3px solid #3498db;">
                <h6 style="margin: 0 0 10px 0; color: #2c3e50;" data-i18n="direct_connection.standards_title">🎯 直接连接标准</h6>
                <ul style="margin: 0; padding-left: 20px; color: #7f8c8d;">
                    <li><strong data-i18n="direct_connection.length_requirement_title">比对长度</strong><span data-i18n="direct_connection.length_requirement_desc">：要求≥10,000bp，确保连接的可靠性</span></li>
                    <li><strong data-i18n="direct_connection.position_requirement_title">位置要求</strong><span data-i18n="direct_connection.position_requirement_desc">：比对区域必须接近序列边缘(≤500bp)，确保能够直接连接</span></li>
                    <li><strong data-i18n="direct_connection.quality_requirement_title">质量要求</strong><span data-i18n="direct_connection.quality_requirement_desc">：序列一致性≥80%，确保连接的准确性</span></li>
                </ul>
            </div>

            <!-- 比对文件可视化 -->
            {self._generate_alignment_visualization(direct_conn)}
        </div>
        """

    def _generate_alignment_visualization(self, direct_conn):
        """生成比对文件可视化"""
        alignment_file = direct_conn.get('alignment_file', '')

        # 尝试读取比对文件
        alignment_data = self._read_alignment_file(alignment_file)

        if not alignment_data:
            return f"""
            <div class="alignment-visualization">
                <h4 data-i18n="visualization.comparison_title">📊 比对结果可视化</h4>
                <div class="alignment-file-info">
                    <strong data-i18n="visualization.alignment_file">比对文件：</strong> <code>{alignment_file}</code>
                    <div style="margin-top: 10px; color: #e74c3c;" data-i18n="visualization.cannot_read_file">
                        ⚠️ 无法读取比对文件或文件为空
                    </div>
                </div>
            </div>
            """

        # 生成比对结果表格
        alignment_table = self._generate_alignment_table(alignment_data)

        # 生成共线图
        synteny_chart = self._generate_synteny_chart(alignment_data)

        return f"""
        <div class="alignment-visualization">
            <div class="alignment-header">
                <h4 data-i18n="visualization.comparison_title">📊 比对结果可视化</h4>
            </div>

            <div class="alignment-file-info">
                <strong data-i18n="visualization.alignment_file">比对文件：</strong> <code>{alignment_file}</code>
                <span style="margin-left: 15px; color: #27ae60;" data-i18n="visualization.found_records" data-count="{len(alignment_data)}">找到 {len(alignment_data)} 条比对记录</span>
            </div>

            <div class="alignment-results">
                <div class="alignment-content">
                    <div class="alignment-table-section">
                        {alignment_table}
                    </div>
                    <div class="alignment-chart-section">
                        {synteny_chart}
                    </div>
                </div>
            </div>

            <div class="alignment-summary">
                <div class="summary-note">
                    <strong data-i18n="direct_connection.analysis_result">分析结果：</strong>
                    <span id="analysis-result-text">{self._analyze_alignment_results(alignment_data, 'zh')}</span>
                </div>
            </div>
        </div>
        """

    def _read_alignment_file(self, alignment_file):
        """读取比对文件"""
        try:
            # 构建完整路径
            # ✨ 优先从 output_dir 读取（因为 direct_connection_check 已复制到那里）
            full_path = None
            
            if alignment_file.startswith('./'):
                relative_path = alignment_file[2:]
                
                # 优先尝试 output_dir
                if self.output_dir:
                    candidate_path = self.output_dir / relative_path
                    if candidate_path.exists():
                        full_path = candidate_path
                        print(f"[DEBUG] 从 output_dir 读取比对文件: {full_path}")
                
                # fallback 到 result_dir
                if full_path is None and self.result_dir:
                    candidate_path = self.result_dir / relative_path
                    if candidate_path.exists():
                        full_path = candidate_path
                        print(f"[DEBUG] 从 result_dir 读取比对文件: {full_path}")
                
                # 最后尝试相对路径
                if full_path is None:
                    candidate_path = Path(relative_path)
                    if candidate_path.exists():
                        full_path = candidate_path
            else:
                full_path = Path(alignment_file)

            if full_path is None or not full_path.exists():
                print(f"[DEBUG] 比对文件不存在: {alignment_file}")
                print(f"[DEBUG]   output_dir: {self.output_dir}")
                print(f"[DEBUG]   result_dir: {self.result_dir}")
                return []

            alignments = []
            with open(full_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = line.split('\t')
                        if len(parts) >= 12:
                            alignments.append({
                                'left_start': int(parts[0]),      # chr1A_TA299.4.left 起始位置
                                'left_end': int(parts[1]),        # chr1A_TA299.4.left 结束位置
                                'right_start': int(parts[2]),     # chr1A_TA299.4.right 起始位置
                                'right_end': int(parts[3]),       # chr1A_TA299.4.right 结束位置
                                'left_align_len': int(parts[4]),  # chr1A_TA299.4.left 比对长度
                                'right_align_len': int(parts[5]), # chr1A_TA299.4.right 比对长度
                                'identity': float(parts[6]),      # 一致性分数
                                'left_total_len': int(parts[7]),  # chr1A_TA299.4.left 总长度
                                'right_total_len': int(parts[8]), # chr1A_TA299.4.right 总长度
                                'left_cov': float(parts[9]),      # chr1A_TA299.4.left 覆盖度
                                'right_cov': float(parts[10]),    # chr1A_TA299.4.right 覆盖度
                                'left_name': parts[11] if len(parts) > 11 else 'chr1A_TA299.4.left',
                                'right_name': parts[12] if len(parts) > 12 else 'chr1A_TA299.4.right'
                            })
            return alignments
        except Exception as e:
            print(f"Warning: Could not read alignment file {alignment_file}: {e}")
            return []

    def _generate_alignment_table(self, alignment_data):
        """生成比对结果表格"""
        if not alignment_data:
            return '<p data-i18n="visualization.no_alignment_data">无比对数据</p>'

        # 分页设置
        records_per_page = 50
        total_records = len(alignment_data)
        total_pages = (total_records + records_per_page - 1) // records_per_page

        table_html = f"""
        <div class="alignment-table-container">
            <table class="alignment-table" id="alignment-table">
                <thead>
                    <tr>
                        <th data-i18n="visualization.sequence">序列</th>
                        <th data-i18n="visualization.left_region">Left区间</th>
                        <th data-i18n="visualization.right_region">Right区间</th>
                        <th data-i18n="visualization.alignment_length">比对长度</th>
                        <th data-i18n="visualization.identity">一致性</th>
                        <th data-i18n="visualization.connection_type">连接类型</th>
                        <th data-i18n="visualization.description">说明</th>
                    </tr>
                </thead>
                <tbody id="alignment-table-body">
                </tbody>
            </table>
        </div>
        """

        # 将比对数据传递给JavaScript进行分页渲染
        table_html += f"""
        <script>
        // 比对表格数据和配置
        const tableAlignmentData = {json.dumps(alignment_data)};
        const tableConfig = {{
            recordsPerPage: {records_per_page},
            totalRecords: {total_records},
            totalPages: {total_pages}
        }};

        // 当前表格页面状态
        let currentTablePage = 1;

        // 渲染表格页面
        function renderTablePage(pageNumber) {{
            const tbody = document.getElementById('alignment-table-body');
            if (!tbody || !tableAlignmentData) return;

            // 清空表格体
            tbody.innerHTML = '';

            // 计算当前页的数据范围
            const startIndex = (pageNumber - 1) * tableConfig.recordsPerPage;
            const endIndex = Math.min(startIndex + tableConfig.recordsPerPage, tableConfig.totalRecords);
            const pageData = tableAlignmentData.slice(startIndex, endIndex);

            // 渲染当前页的表格行
            pageData.forEach((aln, pageIndex) => {{
                const globalIndex = startIndex + pageIndex;
                renderTableRow(aln, globalIndex + 1, tbody);
            }});

            // 更新分页控件状态
            updateTablePaginationControls(pageNumber);
        }}

        function renderTableRow(aln, alignmentIndex, tbody) {{
            // 判断是否满足直接连接标准
            const leftTotalLen = aln.left_total_len;
            const rightTotalLen = aln.right_total_len;
            const leftAlignLen = aln.left_align_len;
            const rightAlignLen = aln.right_align_len;
            const identity = aln.identity;

            // 计算比对区域在序列中的位置
            const leftEndPos = aln.left_end;
            const rightStartPos = aln.right_start;

            const edge = 500;
            const leftDistanceToEdge = leftTotalLen - leftEndPos;
            const rightDistanceToEdge = rightStartPos - 1;

            const meetsPositionRequirement = (leftDistanceToEdge <= edge && rightDistanceToEdge <= edge);
            const meetsLengthRequirement = leftAlignLen >= 10000;
            const meetsIdentityRequirement = identity >= 80.0;
            const meetsDirectConnection = (meetsPositionRequirement && meetsLengthRequirement && meetsIdentityRequirement);
            const allPass = meetsDirectConnection;

            // 收集未达标的原因
            const failedReasons = [];
            if (!allPass) {{
                if (!meetsLengthRequirement) {{
                    failedReasons.push(`比对长度不足(${{leftAlignLen.toLocaleString()}} < 10,000 bp)`);
                }}
                if (!meetsIdentityRequirement) {{
                    failedReasons.push(`序列一致性不足(${{identity.toFixed(1)}}% < 80%)`);
                }}
                if (!meetsPositionRequirement) {{
                    if (leftDistanceToEdge > edge) {{
                        failedReasons.push(`Left序列距离右端过远(${{leftDistanceToEdge.toLocaleString()}} > ${{edge}} bp)`);
                    }}
                    if (rightDistanceToEdge > edge) {{
                        failedReasons.push(`Right序列距离左端过远(${{rightDistanceToEdge.toLocaleString()}} > ${{edge}} bp)`);
                    }}
                }}
            }}

            const statusClass = allPass ? 'pass' : 'fail';
            const statusText = allPass ? '✅ 通过' : '❌ 不通过';

            // 确定连接类型
            let connectionType = "";
            if (meetsDirectConnection) {{
                connectionType = '✅ 直接连接';
            }} else {{
                const passedCriteria = [];
                if (meetsLengthRequirement) passedCriteria.push('长度达标');
                if (meetsIdentityRequirement) passedCriteria.push('一致性达标');
                if (meetsPositionRequirement) passedCriteria.push('位置达标');

                if (passedCriteria.length > 0) {{
                    connectionType = `❌ 部分达标(${{passedCriteria.join(', ')}})`;
                }} else {{
                    connectionType = '❌ 不符合直接连接标准';
                }}
            }}

            const reasonText = failedReasons.length > 0 ? failedReasons.join('; ') : '✅ 符合DEGAPv2标准';

            // 创建表格行
            const row = document.createElement('tr');
            row.className = `alignment-row ${{statusClass}}`;
            row.id = `main-alignment-row-${{alignmentIndex}}`;
            row.style.cursor = 'pointer';

            row.innerHTML = `
                <td>${{aln.left_name}} vs ${{aln.right_name}}</td>
                <td>${{aln.left_start.toLocaleString()}} - ${{aln.left_end.toLocaleString()}}</td>
                <td>${{aln.right_start.toLocaleString()}} - ${{aln.right_end.toLocaleString()}}</td>
                <td class="${{meetsLengthRequirement ? 'pass' : 'fail'}}">${{aln.left_align_len.toLocaleString()}} / ${{aln.right_align_len.toLocaleString()}} bp</td>
                <td class="${{identity >= 80.0 ? 'pass' : 'fail'}}">${{aln.identity.toFixed(1)}}%</td>
                <td class="${{allPass ? 'pass' : 'fail'}}">${{connectionType}}</td>
                <td class="reason-text">${{reasonText}}</td>
            `;

            // 添加点击事件
            row.addEventListener('click', function(e) {{
                e.preventDefault();
                e.stopPropagation();
                selectAlignment(alignmentIndex);
            }});

            // 添加悬停效果
            row.addEventListener('mouseenter', function() {{
                if (!this.classList.contains('selected')) {{
                    this.classList.add('hover');
                }}
            }});

            row.addEventListener('mouseleave', function() {{
                this.classList.remove('hover');
            }});

            tbody.appendChild(row);
        }}

        // 表格分页控制函数
        function changeTablePage(direction) {{
            const newPage = currentTablePage + direction;
            if (newPage >= 1 && newPage <= tableConfig.totalPages) {{
                currentTablePage = newPage;
                renderTablePage(currentTablePage);
                // 同步共线图页面
                if (typeof currentSyntenyPage !== 'undefined') {{
                    currentSyntenyPage = currentTablePage;
                    renderSyntenyPage(currentSyntenyPage);
                }}
            }}
        }}

        function goToTablePage(pageNumber) {{
            const page = parseInt(pageNumber);
            if (page >= 1 && page <= tableConfig.totalPages) {{
                currentTablePage = page;
                renderTablePage(currentTablePage);
                // 同步共线图页面
                if (typeof currentSyntenyPage !== 'undefined') {{
                    currentSyntenyPage = currentTablePage;
                    renderSyntenyPage(currentSyntenyPage);
                }}
            }}
        }}

        function updateTablePaginationControls(currentPage) {{
            // 更新页码显示
            const currentPageElement = document.getElementById('table-current-page');
            const pageInputElement = document.getElementById('table-page-input');
            if (currentPageElement) currentPageElement.textContent = currentPage;
            if (pageInputElement) pageInputElement.value = currentPage;

            // 更新按钮状态
            const prevBtn = document.getElementById('table-prev-btn');
            const nextBtn = document.getElementById('table-next-btn');
            if (prevBtn) prevBtn.disabled = currentPage <= 1;
            if (nextBtn) nextBtn.disabled = currentPage >= tableConfig.totalPages;

            // 同步共线图分页控件（避免循环调用）
            if (typeof updateSyntenyPaginationControlsOnly !== 'undefined') {{
                updateSyntenyPaginationControlsOnly(currentPage);
            }}
        }}

        // 仅更新共线图分页控件，不触发同步
        function updateSyntenyPaginationControlsOnly(currentPage) {{
            const currentPageElement = document.getElementById('synteny-current-page');
            const pageInputElement = document.getElementById('synteny-page-input');
            if (currentPageElement) currentPageElement.textContent = currentPage;
            if (pageInputElement) pageInputElement.value = currentPage;

            const prevBtn = document.getElementById('synteny-prev-btn');
            const nextBtn = document.getElementById('synteny-next-btn');
            if (prevBtn) prevBtn.disabled = currentPage <= 1;
            if (nextBtn) nextBtn.disabled = currentPage >= syntenyChartConfig.totalPages;
        }}

        // 初始化表格
        function initializeAlignmentTable() {{
            if (tableAlignmentData && tableAlignmentData.length > 0) {{
                renderTablePage(1);
            }}
        }}

        // 页面加载完成后初始化表格
        document.addEventListener('DOMContentLoaded', function() {{
            initializeAlignmentTable();
        }});

        // 如果DOM已经加载完成，立即初始化
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', initializeAlignmentTable);
        }} else {{
            initializeAlignmentTable();
        }}

        </script>
        """

        return table_html

    def _generate_synteny_chart(self, alignment_data):
        """生成共线图"""
        if not alignment_data:
            return "<p>无比对数据可绘制共线图</p>"

        # 获取序列长度信息 - 使用片段长度而不是完整序列长度
        initial_info = self.data.get('initial_info', {})
        left_length = initial_info.get('left_fragment_length', alignment_data[0]['left_total_len'] if alignment_data else 60000)
        right_length = initial_info.get('right_fragment_length', alignment_data[0]['right_total_len'] if alignment_data else 60000)

        # 分页设置
        records_per_page = 50
        total_records = len(alignment_data)
        total_pages = (total_records + records_per_page - 1) // records_per_page

        # 生成SVG共线图容器
        svg_width = 1200
        svg_height = 400
        margin = 80

        # 计算绘图区域
        plot_width = svg_width - 2 * margin
        plot_height = svg_height - 2 * margin

        # 序列轴的位置
        ref_y = margin + 50
        query_y = svg_height - margin - 50

        # 生成分页控件（放在图表下方）
        pagination_html = ""
        if total_pages > 1:
            pagination_html = f"""
            <div class="synteny-pagination">
                <button class="pagination-btn" id="synteny-prev-btn" onclick="changeSyntenyPage(-1)" disabled>
                    <span data-i18n="pagination.previous">上一页</span>
                </button>
                <div class="pagination-info">
                    <span data-i18n="pagination.page_info" data-current="1" data-total="{total_pages}">
                        第 <span id="synteny-current-page">1</span> 页, 共 {total_pages} 页
                    </span>
                    <span style="margin-left: 15px;" data-i18n="pagination.records_info" data-total="{total_records}">
                        (共 {total_records} 条记录)
                    </span>
                </div>
                <div class="page-input-group">
                    <span data-i18n="pagination.goto">跳转到</span>
                    <input type="number" class="page-input" id="synteny-page-input" min="1" max="{total_pages}" value="1" onchange="goToSyntenyPage(this.value)">
                    <span data-i18n="pagination.page">页</span>
                </div>
                <button class="pagination-btn" id="synteny-next-btn" onclick="changeSyntenyPage(1)" {"disabled" if total_pages <= 1 else ""}>
                    <span data-i18n="pagination.next">下一页</span>
                </button>
            </div>
            """

        svg_content = f"""
        <div class="synteny-chart">
            <div class="chart-header">
                <h5 data-i18n="visualization.left_right_synteny">Left-Right序列共线性图</h5>
            </div>

            <div id="synteny-chart-container">
                <svg width="{svg_width}" height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}" id="synteny-svg">
                    <!-- 背景 -->
                    <rect width="{svg_width}" height="{svg_height}" fill="#f8f9fa" stroke="#e9ecef"/>

                    <!-- 图例 - 放在SVG内右上角, 上下布局 -->
                    <g class="svg-legend">
                        <rect x="{svg_width - 220}" y="20" width="200" height="120" fill="white" stroke="#e9ecef" rx="5" fill-opacity="0.95"/>
                        <text x="{svg_width - 210}" y="35" fill="#2c3e50" font-weight="bold" font-size="12">Legend</text>

                        <rect x="{svg_width - 205}" y="45" width="16" height="8" fill="#27ae60" opacity="0.8"/>
                        <text x="{svg_width - 185}" y="52" fill="#2c3e50" font-size="11">Qualified Alignment</text>

                        <rect x="{svg_width - 205}" y="65" width="16" height="8" fill="#e74c3c" opacity="0.6"/>
                        <text x="{svg_width - 185}" y="72" fill="#2c3e50" font-size="11">Unqualified Alignment</text>

                        <rect x="{svg_width - 205}" y="85" width="16" height="8" fill="#3498db"/>
                        <text x="{svg_width - 185}" y="92" fill="#2c3e50" font-size="11">LeftSeq</text>

                        <rect x="{svg_width - 205}" y="105" width="16" height="8" fill="#9b59b6"/>
                        <text x="{svg_width - 185}" y="112" fill="#2c3e50" font-size="11">RightSeq</text>
                    </g>

                    <!-- Left序列轴 -->
                    <line x1="{margin}" y1="{ref_y}" x2="{margin + plot_width}" y2="{ref_y}"
                          stroke="#3498db" stroke-width="8" stroke-linecap="round"/>
                    <text x="{margin}" y="{ref_y - 15}" fill="#2c3e50" font-weight="bold" font-size="14">
                        Left Sequence
                    </text>
                    <text x="{margin}" y="{ref_y + 25}" fill="#7f8c8d" font-size="12">
                        0 bp
                    </text>
                    <text x="{margin + plot_width}" y="{ref_y + 25}" fill="#7f8c8d" font-size="12">
                        {left_length:,} bp
                    </text>

                    <!-- Right序列轴 -->
                    <line x1="{margin}" y1="{query_y}" x2="{margin + plot_width}" y2="{query_y}"
                          stroke="#9b59b6" stroke-width="8" stroke-linecap="round"/>
                    <text x="{margin}" y="{query_y + 35}" fill="#2c3e50" font-weight="bold" font-size="14">
                        Right Sequence
                    </text>
                    <text x="{margin}" y="{query_y + 50}" fill="#7f8c8d" font-size="12">
                        0 bp
                    </text>
                    <text x="{margin + plot_width}" y="{query_y + 50}" fill="#7f8c8d" font-size="12">
                        {right_length:,} bp
                    </text>

                    <!-- 比对数据容器 - 将通过JavaScript动态填充 -->
                    <g id="synteny-alignments-container">
                    </g>
                </svg>
            </div>

            {pagination_html}
        </div>

        <script>
        // 传递比对数据和绘图参数给JavaScript
        const syntenyAlignmentData = {json.dumps(alignment_data)};
        const syntenyChartConfig = {{
            svgWidth: {svg_width},
            svgHeight: {svg_height},
            margin: {margin},
            plotWidth: {plot_width},
            plotHeight: {plot_height},
            refY: {ref_y},
            queryY: {query_y},
            leftLength: {left_length},
            rightLength: {right_length},
            recordsPerPage: {records_per_page},
            totalRecords: {total_records},
            totalPages: {total_pages},
            flag: '{self.flag}'
        }};

        // 当前页面状态
        let currentSyntenyPage = 1;

        // 生成分析结果文本的函数
        function generateAnalysisResultText(lang) {{
            if (!syntenyAlignmentData || syntenyAlignmentData.length === 0) {{
                return lang === 'zh' ? '无比对数据可分析' : 'No alignment data to analyze';
            }}

            const total_alignments = syntenyAlignmentData.length;
            let passed_alignments = 0;
            let position_failures = 0;
            let simple_overlap_failures = 0;
            let identity_failures = 0;

            for (const aln of syntenyAlignmentData) {{
                const left_total_len = aln.left_total_len;
                const right_total_len = aln.right_total_len;
                const left_align_len = aln.left_align_len;
                const identity = aln.identity;

                const left_end_pos = aln.left_end;
                const right_start_pos = aln.right_start;

                const edge = 500;

                const left_distance_to_edge = left_total_len - left_end_pos;
                const right_distance_to_edge = right_start_pos - 1;

                const meets_position_requirement = (left_distance_to_edge <= edge && right_distance_to_edge <= edge);
                const meets_length_requirement = left_align_len >= 10000;
                const meets_identity_requirement = identity >= 80.0;

                const meets_direct_connection = (meets_position_requirement && meets_length_requirement && meets_identity_requirement);

                if (meets_direct_connection) {{
                    passed_alignments++;
                }} else {{
                    if (!meets_length_requirement) simple_overlap_failures++;
                    if (!meets_identity_requirement) identity_failures++;
                    if (!meets_position_requirement) position_failures++;
                }}
            }}

            if (passed_alignments === 0) {{
                const failure_reasons = [];
                if (position_failures > 0) {{
                    if (lang === 'zh') {{
                        failure_reasons.push(`${{position_failures}}条记录位置不符合要求(距离边缘>500bp)`);
                    }} else {{
                        failure_reasons.push(`${{position_failures}} records failed position requirement (distance from edge >500bp)`);
                    }}
                }}
                if (simple_overlap_failures > 0) {{
                    if (lang === 'zh') {{
                        failure_reasons.push(`${{simple_overlap_failures}}条记录比对长度不足(<10,000bp)`);
                    }} else {{
                        failure_reasons.push(`${{simple_overlap_failures}} records failed length requirement (<10,000bp)`);
                    }}
                }}
                if (identity_failures > 0) {{
                    if (lang === 'zh') {{
                        failure_reasons.push(`${{identity_failures}}条记录序列一致性不足(<80%)`);
                    }} else {{
                        failure_reasons.push(`${{identity_failures}} records failed identity requirement (<80%)`);
                    }}
                }}

                const separator = lang === 'zh' ? ', ' : ', ';
                const reason_text = failure_reasons.length > 0 ? failure_reasons.join(separator) :
                    (lang === 'zh' ? '未找到符合DEGAPv2直接连接条件的比对' : 'No alignments meeting DEGAPv2 direct connection criteria found');

                if (lang === 'zh') {{
                    return `共找到 ${{total_alignments}} 条比对记录, 但均未达到DEGAPv2直接连接标准。具体原因: ${{reason_text}}。DEGAPv2要求比对长度≥10,000bp、序列一致性≥80%且距离序列边缘≤500bp, 因此需要进行Gap填充。`;
                }} else {{
                    return `Found ${{total_alignments}} alignment records, but none met DEGAPv2 direct connection standards. Specific reasons: ${{reason_text}}. DEGAPv2 requires alignment length ≥10,000bp, sequence identity ≥80%, and distance from sequence edges ≤500bp, therefore Gap filling is required.`;
                }}
            }} else {{
                if (lang === 'zh') {{
                    return `共找到 ${{total_alignments}} 条比对记录, 其中 ${{passed_alignments}} 条达到DEGAPv2直接连接标准, 但可能由于其他因素（如序列方向、结构变异等）最终未能实现直接连接, 因此进入了Gap填充流程。`;
                }} else {{
                    return `Found ${{total_alignments}} alignment records, of which ${{passed_alignments}} met DEGAPv2 direct connection standards, but may not have achieved direct connection due to other factors (such as sequence orientation, structural variations, etc.), therefore entered Gap filling process.`;
                }}
            }}
        }}

        // 更新分析结果文本
        function updateAnalysisResultText() {{
            const analysisResultElement = document.getElementById('analysis-result-text');
            if (analysisResultElement) {{
                analysisResultElement.textContent = generateAnalysisResultText(currentLanguage);
            }}
        }}

        // 更新处理统计卡片
        function updateProcessingStatsCard() {{
            // 标题和表格头现在通过data-i18n属性处理，由updateI18nElements()函数统一处理

            // 更新状态文本
            document.querySelectorAll('[data-i18n-status]').forEach(element => {{
                const status = element.getAttribute('data-i18n-status');
                if (status === '成功' || status === 'success') {{
                    element.textContent = t('processing_stats.status_values.success');
                }} else if (status === '失败' || status === 'failed') {{
                    element.textContent = t('processing_stats.status_values.failed');
                }}
            }});

            // 更新Gap填充状态
            document.querySelectorAll('[data-i18n-status^="gap_filling_"]').forEach(element => {{
                const statusAttr = element.getAttribute('data-i18n-status');
                if (statusAttr === 'gap_filling_成功' || statusAttr === 'gap_filling_success') {{
                    element.textContent = t('processing_stats.status_values.gap_filling_success');
                }} else if (statusAttr === 'gap_filling_失败' || statusAttr === 'gap_filling_failed') {{
                    element.textContent = t('processing_stats.status_values.gap_filling_failed');
                }}
            }});

            // 更新使用结果
            document.querySelectorAll('[data-i18n-result]').forEach(element => {{
                const result = element.getAttribute('data-i18n-result');
                if (result === '延申连接结果' || result === 'extension_result') {{
                    element.textContent = t('processing_stats.status_values.extension_result');
                }} else if (result === '直接连接结果' || result === 'direct_result') {{
                    element.textContent = t('processing_stats.status_values.direct_result');
                }} else if (result === '无可用结果' || result === 'no_result') {{
                    element.textContent = t('processing_stats.status_values.no_result');
                }}
            }});

            // 更新连接状态说明
            const connectionTitle = document.querySelector('.connection-status-explanation h4');
            if (connectionTitle) {{
                connectionTitle.textContent = t('processing_stats.connection_status.title');
            }}

            // 更新处理逻辑
            const logicTitle = document.querySelector('.logic-explanation p strong');
            if (logicTitle) {{
                logicTitle.textContent = t('processing_stats.connection_status.processing_logic');
            }}

            const logicItems = document.querySelectorAll('.logic-explanation li');
            if (logicItems.length >= 3) {{
                logicItems[0].textContent = t('processing_stats.connection_status.logic_items.extension_success');
                logicItems[1].textContent = t('processing_stats.connection_status.logic_items.extension_fail_direct_success');
                logicItems[2].textContent = t('processing_stats.connection_status.logic_items.both_fail');
            }}
        }}

        // 共线图分页渲染函数
        function renderSyntenyPage(pageNumber) {{
            const container = document.getElementById('synteny-alignments-container');
            if (!container || !syntenyAlignmentData) return;

            // 清空容器
            container.innerHTML = '';

            // 计算当前页的数据范围
            const startIndex = (pageNumber - 1) * syntenyChartConfig.recordsPerPage;
            const endIndex = Math.min(startIndex + syntenyChartConfig.recordsPerPage, syntenyChartConfig.totalRecords);
            const pageData = syntenyAlignmentData.slice(startIndex, endIndex);

            // 渲染当前页的比对记录
            pageData.forEach((aln, pageIndex) => {{
                const globalIndex = startIndex + pageIndex;
                renderSyntenyAlignment(aln, globalIndex + 1, container);
            }});

            // 更新分页控件状态
            updateSyntenyPaginationControls(pageNumber);
        }}

        function renderSyntenyAlignment(aln, alignmentIndex, container) {{
            const config = syntenyChartConfig;

            // 计算坐标
            let leftStartX = config.margin + (aln.left_start / config.leftLength) * config.plotWidth;
            let leftEndX = config.margin + (aln.left_end / config.leftLength) * config.plotWidth;
            let rightStartX = config.margin + (aln.right_start / config.rightLength) * config.plotWidth;
            let rightEndX = config.margin + (aln.right_end / config.rightLength) * config.plotWidth;

            // 设置最小可见宽度（至少2像素）
            const minWidth = 2;
            if (Math.abs(leftEndX - leftStartX) < minWidth) {{
                const centerX = (leftStartX + leftEndX) / 2;
                leftStartX = centerX - minWidth / 2;
                leftEndX = centerX + minWidth / 2;
            }}
            if (Math.abs(rightEndX - rightStartX) < minWidth) {{
                const centerX = (rightStartX + rightEndX) / 2;
                rightStartX = centerX - minWidth / 2;
                rightEndX = centerX + minWidth / 2;
            }}

            // 处理反向比对：确保矩形宽度为正值
            const leftRectX = Math.min(leftStartX, leftEndX);
            const leftRectWidth = Math.abs(leftEndX - leftStartX);
            const rightRectX = Math.min(rightStartX, rightEndX);
            const rightRectWidth = Math.abs(rightEndX - rightStartX);

            // 判断比对方向
            const leftIsReverse = aln.left_start > aln.left_end;
            const rightIsReverse = aln.right_start > aln.right_end;

            // 判断比对质量
            const edge = 500;
            const leftDistanceToEdge = aln.left_total_len - aln.left_end;
            const rightDistanceToEdge = aln.right_start - 1;
            const meetsPositionRequirement = (leftDistanceToEdge <= edge && rightDistanceToEdge <= edge);
            const meetsLengthRequirement = aln.left_align_len >= 10000;
            const meetsIdentityRequirement = aln.identity >= 80.0;
            const allPass = (meetsPositionRequirement && meetsLengthRequirement && meetsIdentityRequirement);

            const color = allPass ? "#27ae60" : "#e74c3c";
            const opacity = allPass ? "0.8" : "0.6";

            // 确定连接类型文本
            let connectionTypeText = "";
            if (allPass) {{
                connectionTypeText = "直接连接";
            }} else {{
                const passedCriteria = [];
                if (meetsLengthRequirement) passedCriteria.push("长度达标");
                if (meetsIdentityRequirement) passedCriteria.push("一致性达标");
                if (meetsPositionRequirement) passedCriteria.push("位置达标");

                if (passedCriteria.length > 0) {{
                    connectionTypeText = `部分达标(${{passedCriteria.join(', ')}})`;
                }} else {{
                    connectionTypeText = "不符合直接连接标准";
                }}
            }}

            // 计算位置百分比
            const leftPosPercent = (aln.left_end / config.leftLength) * 100;
            const rightPosPercent = (aln.right_start / config.rightLength) * 100;

            // 创建SVG组元素
            const alignmentGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            alignmentGroup.setAttribute('class', `alignment-${{alignmentIndex}}`);
            alignmentGroup.setAttribute('data-alignment', alignmentIndex);

            // 创建SVG元素的HTML字符串
            const svgElements = `
                <!-- Left序列比对区域 -->
                <rect x="${{leftRectX}}" y="${{config.refY - 4}}" width="${{leftRectWidth}}" height="8"
                      fill="${{color}}" opacity="${{opacity}}" stroke="#2c3e50" stroke-width="1"
                      class="alignment-rect left-rect ${{leftIsReverse ? 'reverse' : 'forward'}}"
                      onmouseover="showSyntenyTooltip(evt, ${{alignmentIndex}})"
                      onmouseout="hideSyntenyTooltip()"
                      onclick="selectAlignmentFromChart(${{alignmentIndex}})"
                      style="cursor: pointer;"/>

                <!-- Left序列悬停区域 -->
                <rect x="${{leftRectX - 5}}" y="${{config.refY - 15}}"
                      width="${{leftRectWidth + 10}}" height="30"
                      fill="transparent" stroke="none"
                      class="hover-area-left"
                      onmouseover="showSyntenyTooltip(evt, ${{alignmentIndex}})"
                      onmouseout="hideSyntenyTooltip()"
                      onclick="selectAlignmentFromChart(${{alignmentIndex}})"
                      style="cursor: pointer;"/>

                <!-- Right序列比对区域 -->
                <rect x="${{rightRectX}}" y="${{config.queryY - 4}}" width="${{rightRectWidth}}" height="8"
                      fill="${{color}}" opacity="${{opacity}}" stroke="#2c3e50" stroke-width="1"
                      class="alignment-rect right-rect ${{rightIsReverse ? 'reverse' : 'forward'}}"
                      onmouseover="showSyntenyTooltip(evt, ${{alignmentIndex}})"
                      onmouseout="hideSyntenyTooltip()"
                      onclick="selectAlignmentFromChart(${{alignmentIndex}})"
                      style="cursor: pointer;"/>

                <!-- Right序列悬停区域 -->
                <rect x="${{rightRectX - 5}}" y="${{config.queryY - 15}}"
                      width="${{rightRectWidth + 10}}" height="30"
                      fill="transparent" stroke="none"
                      class="hover-area-right"
                      onmouseover="showSyntenyTooltip(evt, ${{alignmentIndex}})"
                      onmouseout="hideSyntenyTooltip()"
                      onclick="selectAlignmentFromChart(${{alignmentIndex}})"
                      style="cursor: pointer;"/>

                <!-- 连接区域 - 使用多边形创建填充区域，连接左序列区域到右序列区域 -->
                <!-- 按顺时针顺序定义四个顶点：左上、右上、右下、左下 -->
                <polygon points="${{leftStartX}},${{config.refY + 4}} ${{leftEndX}},${{config.refY + 4}} ${{rightEndX}},${{config.queryY - 4}} ${{rightStartX}},${{config.queryY - 4}}"
                         fill="${{color}}" opacity="${{opacity}}" stroke="${{color}}" stroke-width="1"
                         class="connection-area"
                         onmouseover="showSyntenyTooltip(evt, ${{alignmentIndex}})"
                         onmouseout="hideSyntenyTooltip()"
                         onclick="selectAlignmentFromChart(${{alignmentIndex}})"
                         style="cursor: pointer;"/>

                <!-- 连接边框线 - 连接左序列区域的边界到右序列区域的边界 -->
                <path d="M ${{leftStartX}} ${{config.refY + 4}} L ${{rightStartX}} ${{config.queryY - 4}}"
                      stroke="${{color}}" stroke-width="1" fill="none" opacity="${{opacity}}"
                      class="connection-line"
                      onmouseover="showSyntenyTooltip(evt, ${{alignmentIndex}})"
                      onmouseout="hideSyntenyTooltip()"
                      onclick="selectAlignmentFromChart(${{alignmentIndex}})"
                      style="cursor: pointer;"/>
                <path d="M ${{leftEndX}} ${{config.refY + 4}} L ${{rightEndX}} ${{config.queryY - 4}}"
                      stroke="${{color}}" stroke-width="1" fill="none" opacity="${{opacity}}"
                      class="connection-line"
                      onmouseover="showSyntenyTooltip(evt, ${{alignmentIndex}})"
                      onmouseout="hideSyntenyTooltip()"
                      onclick="selectAlignmentFromChart(${{alignmentIndex}})"
                      style="cursor: pointer;"/>

                <!-- 比对信息标签 -->
                <text x="${{leftRectX + leftRectWidth/2}}" y="${{config.refY - 10}}" fill="#2c3e50" font-size="10" text-anchor="middle"
                      class="alignment-label"
                      onmouseover="showSyntenyTooltip(evt, ${{alignmentIndex}})"
                      onmouseout="hideSyntenyTooltip()"
                      style="cursor: pointer;">
                    ${{aln.left_align_len.toLocaleString()}}bp
                </text>
                <text x="${{rightRectX + rightRectWidth/2}}" y="${{config.queryY + 20}}" fill="#2c3e50" font-size="10" text-anchor="middle"
                      class="alignment-label"
                      onmouseover="showSyntenyTooltip(evt, ${{alignmentIndex}})"
                      onmouseout="hideSyntenyTooltip()"
                      style="cursor: pointer;">
                    ${{aln.identity.toFixed(1)}}%
                </text>

                <!-- 隐藏的tooltip数据 -->
                <g class="tooltip-data" style="display: none;" data-alignment="${{alignmentIndex}}">
                    <text class="tooltip-title">比对记录 #${{alignmentIndex}}</text>
                    <text class="tooltip-left-region">Left区间: ${{aln.left_start.toLocaleString()}} - ${{aln.left_end.toLocaleString()}}</text>
                    <text class="tooltip-right-region">Right区间: ${{aln.right_start.toLocaleString()}} - ${{aln.right_end.toLocaleString()}}</text>
                    <text class="tooltip-length">比对长度: ${{aln.left_align_len.toLocaleString()}} / ${{aln.right_align_len.toLocaleString()}} bp</text>
                    <text class="tooltip-identity">序列一致性: ${{aln.identity.toFixed(1)}}%</text>
                    <text class="tooltip-position">位置: Left末端${{leftPosPercent.toFixed(1)}}%, Right开头${{rightPosPercent.toFixed(1)}}%</text>
                    <text class="tooltip-type">连接类型: ${{connectionTypeText}}</text>
                    <text class="tooltip-status">状态: ${{allPass ? '✅ 符合DEGAPv2标准' : '❌ 未达标'}}</text>
                </g>
            `;

            alignmentGroup.innerHTML = svgElements;
            container.appendChild(alignmentGroup);
        }}

        // 分页控制函数
        function changeSyntenyPage(direction) {{
            const newPage = currentSyntenyPage + direction;
            if (newPage >= 1 && newPage <= syntenyChartConfig.totalPages) {{
                currentSyntenyPage = newPage;
                renderSyntenyPage(currentSyntenyPage);
                // 同步表格页面
                if (typeof currentTablePage !== 'undefined') {{
                    currentTablePage = currentSyntenyPage;
                    renderTablePage(currentTablePage);
                }}
            }}
        }}

        function goToSyntenyPage(pageNumber) {{
            const page = parseInt(pageNumber);
            if (page >= 1 && page <= syntenyChartConfig.totalPages) {{
                currentSyntenyPage = page;
                renderSyntenyPage(currentSyntenyPage);
                // 同步表格页面
                if (typeof currentTablePage !== 'undefined') {{
                    currentTablePage = currentSyntenyPage;
                    renderTablePage(currentTablePage);
                }}
            }}
        }}

        function updateSyntenyPaginationControls(currentPage) {{
            // 更新页码显示
            const currentPageElement = document.getElementById('synteny-current-page');
            const pageInputElement = document.getElementById('synteny-page-input');
            if (currentPageElement) currentPageElement.textContent = currentPage;
            if (pageInputElement) pageInputElement.value = currentPage;

            // 更新按钮状态
            const prevBtn = document.getElementById('synteny-prev-btn');
            const nextBtn = document.getElementById('synteny-next-btn');
            if (prevBtn) prevBtn.disabled = currentPage <= 1;
            if (nextBtn) nextBtn.disabled = currentPage >= syntenyChartConfig.totalPages;

            // 同步表格分页控件（避免循环调用）
            if (typeof updateTablePaginationControlsOnly !== 'undefined') {{
                updateTablePaginationControlsOnly(currentPage);
            }}
        }}

        // 仅更新表格分页控件，不触发同步
        function updateTablePaginationControlsOnly(currentPage) {{
            const currentPageElement = document.getElementById('table-current-page');
            const pageInputElement = document.getElementById('table-page-input');
            if (currentPageElement) currentPageElement.textContent = currentPage;
            if (pageInputElement) pageInputElement.value = currentPage;

            const prevBtn = document.getElementById('table-prev-btn');
            const nextBtn = document.getElementById('table-next-btn');
            if (prevBtn) prevBtn.disabled = currentPage <= 1;
            if (nextBtn) nextBtn.disabled = currentPage >= tableConfig.totalPages;
        }}

        // 从共线图选择比对记录的函数
        function selectAlignmentFromChart(alignmentIndex) {{
            // 计算该记录在哪一页
            const recordsPerPage = 50;
            const targetPage = Math.ceil(alignmentIndex / recordsPerPage);

            // 如果不在当前页，先跳转到目标页
            if (typeof currentTablePage !== 'undefined' && currentTablePage !== targetPage) {{
                currentTablePage = targetPage;
                renderTablePage(currentTablePage);
            }}

            // 同步共线图页面
            if (typeof currentSyntenyPage !== 'undefined' && currentSyntenyPage !== targetPage) {{
                currentSyntenyPage = targetPage;
                renderSyntenyPage(currentSyntenyPage);
            }}

            // 选择表格中的对应行
            if (typeof selectAlignment === 'function') {{
                selectAlignment(alignmentIndex);
            }}
        }}

        // Tooltip相关函数
        function showSyntenyTooltip(evt, alignmentIndex) {{
            // 实现tooltip显示逻辑
            const tooltipData = document.querySelector(`[data-alignment="${{alignmentIndex}}"] .tooltip-data`);
            if (tooltipData) {{
                // 这里可以添加tooltip显示逻辑
                console.log('Show tooltip for alignment', alignmentIndex);
            }}
        }}

        function hideSyntenyTooltip() {{
            // 实现tooltip隐藏逻辑
            console.log('Hide tooltip');
        }}

        // 初始化共线图
        function initializeSyntenyChart() {{
            if (syntenyAlignmentData && syntenyAlignmentData.length > 0) {{
                renderSyntenyPage(1);
            }}
        }}

        // 页面加载完成后初始化共线图
        document.addEventListener('DOMContentLoaded', function() {{
            initializeSyntenyChart();
        }});

        // 如果DOM已经加载完成，立即初始化
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', initializeSyntenyChart);
        }} else {{
            initializeSyntenyChart();
        }}

        </script>
        """

        return svg_content

    def _analyze_alignment_results(self, alignment_data, lang='zh'):
        """分析比对结果"""
        # 定义翻译字典
        translations = {
            'zh': {
                'no_alignment_data_to_analyze': '无比对数据可分析',
                'position_failure_reason': '{count}条记录位置不符合要求(距离边缘>{edge}bp)',
                'length_failure_reason': '{count}条记录比对长度不足(<10,000bp)',
                'identity_failure_reason': '{count}条记录序列一致性不足(<80%)',
                'failure_separator': '，',
                'no_qualified_alignment': '未找到符合DEGAPv2直接连接条件的比对',
                'analysis_no_pass': '共找到 {total} 条比对记录，但均未达到DEGAPv2直接连接标准。具体原因：{reasons}。DEGAPv2要求比对长度≥10,000bp、序列一致性≥80%且距离序列边缘≤{edge}bp，因此需要进行Gap填充。',
                'analysis_partial_pass': '共找到 {total} 条比对记录，其中 {passed} 条达到DEGAPv2直接连接标准，但可能由于其他因素（如序列方向、结构变异等）最终未能实现直接连接，因此进入了Gap填充流程。'
            },
            'en': {
                'no_alignment_data_to_analyze': 'No alignment data to analyze',
                'position_failure_reason': '{count} records failed position requirement (distance from edge >{edge}bp)',
                'length_failure_reason': '{count} records failed length requirement (<10,000bp)',
                'identity_failure_reason': '{count} records failed identity requirement (<80%)',
                'failure_separator': ', ',
                'no_qualified_alignment': 'No alignments meeting DEGAPv2 direct connection criteria found',
                'analysis_no_pass': 'Found {total} alignment records, but none met DEGAPv2 direct connection standards. Specific reasons: {reasons}. DEGAPv2 requires alignment length ≥10,000bp, sequence identity ≥80%, and distance from sequence edges ≤{edge}bp, therefore Gap filling is required.',
                'analysis_partial_pass': 'Found {total} alignment records, of which {passed} met DEGAPv2 direct connection standards, but may not have achieved direct connection due to other factors (such as sequence orientation, structural variations, etc.), therefore entered Gap filling process.'
            }
        }

        def get_text(key):
            return translations.get(lang, {}).get(key, key)

        if not alignment_data:
            return get_text('no_alignment_data_to_analyze')

        total_alignments = len(alignment_data)
        passed_alignments = 0

        # 统计各种失败原因
        simple_overlap_failures = 0
        tandem_repeat_failures = 0
        identity_failures = 0
        position_failures = 0

        for aln in alignment_data:
            left_total_len = aln['left_total_len']
            right_total_len = aln['right_total_len']
            left_align_len = aln['left_align_len']
            identity = aln['identity']

            # 计算比对区域在序列中的位置
            left_end_pos = aln['left_end']
            right_start_pos = aln['right_start']

            # 使用新的直接连接标准
            edge = 500  # 默认edge参数

            # 计算距离边缘的距离
            left_distance_to_edge = left_total_len - left_end_pos
            right_distance_to_edge = right_start_pos - 1

            # 位置要求：距离边缘不超过edge
            meets_position_requirement = (left_distance_to_edge <= edge and
                                        right_distance_to_edge <= edge)

            # 长度要求：≥10,000bp
            meets_length_requirement = left_align_len >= 10000

            # 一致性要求：≥80%
            meets_identity_requirement = identity >= 80.0

            # 综合判断
            meets_direct_connection = (meets_position_requirement and
                                     meets_length_requirement and
                                     meets_identity_requirement)

            if meets_direct_connection:
                passed_alignments += 1
            else:
                if not meets_length_requirement:
                    simple_overlap_failures += 1  # 重用这个变量统计长度不足
                if not meets_identity_requirement:
                    identity_failures += 1
                if not meets_position_requirement:
                    position_failures += 1

        if passed_alignments == 0:
            failure_reasons = []
            if position_failures > 0:
                failure_reasons.append(get_text('position_failure_reason').format(count=position_failures, edge=edge))
            if simple_overlap_failures > 0:
                failure_reasons.append(get_text('length_failure_reason').format(count=simple_overlap_failures))
            if identity_failures > 0:
                failure_reasons.append(get_text('identity_failure_reason').format(count=identity_failures))

            reason_text = get_text('failure_separator').join(failure_reasons) if failure_reasons else get_text('no_qualified_alignment')
            return get_text('analysis_no_pass').format(total=total_alignments, reasons=reason_text, edge=edge)
        else:
            return get_text('analysis_partial_pass').format(total=total_alignments, passed=passed_alignments)

    def _generate_gap_visualization(self):
        """生成Gap可视化部分"""
        initial_info = self.data.get('initial_info', {})
        rounds = self.data.get('rounds', [])

        initial_length = initial_info.get('right_length', 0)
        current_length = initial_length
        if rounds:
            current_length = rounds[-1].get('output_length', initial_length)

        extension_length = current_length - initial_length

        # 生成timeline点 - 根据flag调整顺序
        timeline_points = []

        # 构建所有点的数据
        all_points = [{'num': 0, 'title': '初始状态', 'class': 'active', 'is_initial': True}]

        for i, round_data in enumerate(rounds):
            round_num = i + 1
            status_class = ''
            if round_data.get('gap_closed'):
                status_class = 'completed'
            elif round_data.get('extension_status') == 'no_extension':
                status_class = 'failed'

            all_points.append({
                'num': round_num,
                'title': f'第{round_num}轮',
                'class': status_class,
                'is_initial': False
            })

        # 根据flag决定顺序
        if self.flag == 'right':
            # right模式：与left相反，从右到左，所以反转顺序
            all_points.reverse()

        # 生成HTML - 注意：点击事件使用原始的round号码，显示使用排序后的位置
        for i, point in enumerate(all_points):
            if i > 0:  # 不是第一个点时添加连接线
                timeline_points.append(f'<div class="timeline-line"></div>')

            timeline_points.append(
                f'<div class="timeline-point {point["class"]}" onclick="goToRound({point["num"]})" title="{point["title"]}">{point["num"]}</div>'
            )

        return f"""
        <div class="section">
            <div class="section-title" data-i18n="visualization.title">
                🎯 Gap填充可视化
            </div>
            <div class="gap-visualization">


                <div class="chromosome-diagram">
                    {self._generate_improved_chromosome_svg()}
                </div>






                <!-- 延伸轮次timeline -->
                <div class="round-switcher">
                    <div class="round-switcher-title">🔄 延伸轮次</div>
                    <div class="timeline-container">
                        <div class="timeline-nav-btn" id="prevRoundBtn" onclick="goToPrevRound()" title="上一轮">‹</div>
                        <div class="timeline">
                            {''.join(timeline_points)}
                        </div>
                        <div class="timeline-nav-btn" id="nextRoundBtn" onclick="goToNextRound()" title="下一轮">›</div>
                    </div>
                    <div class="round-info">
                        <span>当前轮次: <span id="currentRoundDisplay">初始状态</span></span>
                        <span style="margin-left: 20px;">点击圆点切换轮次</span>
                    </div>
                </div>

                <!-- 当前轮次详情卡片 -->
                <div id="roundDetailCard" class="round-detail-card" style="display: none;">
                    <!-- 轮次详情内容将通过JavaScript动态生成 -->
                </div>
            </div>
        </div>
        """

    def _generate_improved_chromosome_svg(self):
        """生成改进的染色体SVG图 - 动态可更新的结构"""
        initial_info = self.data.get('initial_info', {})
        direct_connection = self.data.get('direct_connection', {})

        # 使用片段长度而不是完整序列长度
        left_length = initial_info.get('left_fragment_length', initial_info.get('left_length', 60000))
        right_length = initial_info.get('right_fragment_length', initial_info.get('right_length', 60000))

        # 判断是否有直接连接
        has_direct_connection = direct_connection.get('connection_found', False)

        return self._generate_dynamic_chromosome_svg(left_length, right_length, has_direct_connection)

    def _generate_dynamic_chromosome_svg(self, left_length, right_length, has_direct_connection):
        """生成动态可更新的染色体SVG结构"""
        svg_width = 1200
        svg_height = 250
        margin = 50

        # 计算各部分的显示宽度（基于固定比例）
        available_width = svg_width - 2 * margin
        left_width = 250  # 固定左臂宽度
        right_width = 250  # 固定右臂宽度

        # 左臂位置
        left_x = margin
        left_y = svg_height // 2 - 20

        # 右臂位置（从右边开始）
        right_x = svg_width - margin - right_width
        right_y = left_y

        # Gap区域
        gap_x = left_x + left_width
        gap_width = right_x - gap_x

        svg_parts = [
            f'<svg class="chromosome-svg" width="{svg_width}" height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}" id="chromosomeSVG">',

            # 定义渐变
            '<defs>',
            '<linearGradient id="leftGradient" x1="0%" y1="0%" x2="100%" y2="0%">',
            '<stop offset="0%" style="stop-color:#3498db;stop-opacity:1" />',
            '<stop offset="100%" style="stop-color:#2980b9;stop-opacity:1" />',
            '</linearGradient>',
            '<linearGradient id="rightGradient" x1="0%" y1="0%" x2="100%" y2="0%">',
            '<stop offset="0%" style="stop-color:#e74c3c;stop-opacity:1" />',
            '<stop offset="100%" style="stop-color:#c0392b;stop-opacity:1" />',
            '</linearGradient>',
            '<linearGradient id="extensionGradient" x1="0%" y1="0%" x2="100%" y2="0%">',
            '<stop offset="0%" style="stop-color:#2ecc71;stop-opacity:1" />',
            '<stop offset="100%" style="stop-color:#27ae60;stop-opacity:1" />',
            '</linearGradient>',
            '</defs>',

            # 左臂
            f'<rect x="{left_x}" y="{left_y}" width="{left_width}" height="40" fill="url(#leftGradient)" stroke="#2c3e50" stroke-width="2" rx="5"/>',
            f'<text x="{left_x + left_width/2}" y="{left_y - 10}" text-anchor="middle" class="chromosome-label">Left Sequence</text>',
            f'<text x="{left_x + left_width/2}" y="{left_y + 55}" text-anchor="middle" class="sequence-length-label">{left_length:,} bp</text>',

            # 右臂
            f'<rect x="{right_x}" y="{right_y}" width="{right_width}" height="40" fill="url(#rightGradient)" stroke="#2c3e50" stroke-width="2" rx="5"/>',
            f'<text x="{right_x + right_width/2}" y="{right_y - 10}" text-anchor="middle" class="chromosome-label">Right Sequence</text>',
            f'<text x="{right_x + right_width/2}" y="{right_y + 55}" text-anchor="middle" class="sequence-length-label">{right_length:,} bp</text>',
        ]

        # Gap区域和延伸可视化
        if has_direct_connection:
            # 直接连接 - 显示连接线
            svg_parts.extend([
                f'<line x1="{left_x + left_width}" y1="{left_y + 20}" x2="{right_x}" y2="{right_y + 20}" stroke="#2ecc71" stroke-width="4"/>',
                f'<text x="{gap_x + gap_width/2}" y="{left_y + 15}" text-anchor="middle" class="chromosome-label" fill="#2ecc71">Direct Connection</text>'
            ])
        else:
            # Gap区域背景
            svg_parts.append(f'<rect x="{gap_x}" y="{left_y}" width="{gap_width}" height="40" fill="#ecf0f1" stroke="#bdc3c7" stroke-width="2" stroke-dasharray="5,5" rx="5" id="gapRegion"/>')

            # 动态延伸填充容器 - 这将通过JavaScript动态更新
            svg_parts.append(f'<g id="extensionContainer"></g>')

            # Gap标签 - 支持国际化
            svg_parts.append(f'<text x="{gap_x + gap_width/2}" y="{left_y - 10}" text-anchor="middle" class="chromosome-label" data-i18n="gap.region">Gap Region</text>')

            # 根据flag参数动态调整延伸方向标识 - 支持国际化
            direction_key = 'gap.direction_left' if self.flag == 'left' else 'gap.direction_right'
            direction_text = 'Extension Direction →' if self.flag == 'left' else '← Extension Direction'

            svg_parts.append(f'<text x="{gap_x + gap_width/2}" y="{left_y + 55}" text-anchor="middle" class="sequence-length-label" data-i18n="{direction_key}">{direction_text}</text>')

        svg_parts.append('</svg>')

        return '\n'.join(svg_parts)

    def _generate_extension_alignment_visualization(self, round_data):
        """生成延伸序列与terminalSeq比对可视化"""
        alignment_info = round_data.get('extension_alignment')
        if not alignment_info:
            return """
            <div class="extension-alignment-section">
                <h5>🔗 延伸序列与TerminalSeq比对分析</h5>
                <div class="alignment-info">
                    <p style="color: #7f8c8d; font-style: italic;">本轮未生成比对信息</p>
                </div>
            </div>
            """

        # 判断是否满足gap闭合标准
        meets_standard = alignment_info.get('meets_gap_closure_standard', False)
        can_close_gap = alignment_info.get('can_close_gap', False)

        status_class = 'badge-success' if can_close_gap else 'badge-warning'
        status_icon = '✅' if can_close_gap else '⚠️'
        status_text = 'Gap可以闭合' if can_close_gap else 'Gap尚未闭合'

        # 生成比对信息表格
        alignment_table = f"""
        <div class="alignment-table-container">
            <table class="alignment-table">
                <thead>
                    <tr>
                        <th>序列类型</th>
                        <th>比对区间</th>
                        <th>比对长度</th>
                        <th>序列总长</th>
                        <th>覆盖度</th>
                        <th>一致性</th>
                        <th>标准检查</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>{alignment_info.get('terminal_name', 'TerminalSeq')}</strong></td>
                        <td>{alignment_info.get('terminal_start', 0):,} - {alignment_info.get('terminal_end', 0):,}</td>
                        <td class="{'pass' if meets_standard else 'fail'}">{alignment_info.get('terminal_align_len', 0):,} bp</td>
                        <td>{alignment_info.get('terminal_total_len', 0):,} bp</td>
                        <td>{alignment_info.get('terminal_coverage', 0):.1f}%</td>
                        <td rowspan="2" style="vertical-align: middle; font-weight: bold;">{alignment_info.get('identity', 0):.2f}%</td>
                        <td rowspan="2" style="vertical-align: middle;" class="{'pass' if meets_standard else 'fail'}">
                            {'✅ 达标 (≥10,000bp)' if meets_standard else '❌ 未达标 (<10,000bp)'}
                        </td>
                    </tr>
                    <tr>
                        <td><strong>{alignment_info.get('extension_name', 'ExtensionSeq')}</strong></td>
                        <td>{alignment_info.get('extension_start', 0):,} - {alignment_info.get('extension_end', 0):,}</td>
                        <td class="{'pass' if meets_standard else 'fail'}">{alignment_info.get('extension_align_len', 0):,} bp</td>
                        <td>{alignment_info.get('extension_total_len', 0):,} bp</td>
                        <td>{alignment_info.get('extension_coverage', 0):.1f}%</td>
                    </tr>
                </tbody>
            </table>
        </div>
        """

        # 生成共线图
        synteny_chart = self._generate_extension_synteny_chart(alignment_info)

        return f"""
        <div class="extension-alignment-section">
            <h5>🔗 延伸序列与TerminalSeq比对分析</h5>

            <!-- 比对状态 -->
            <div class="alignment-status" style="text-align: center; margin: 15px 0;">
                <span class="badge {status_class}" style="font-size: 1.1em; padding: 10px 20px;">
                    {status_icon} {status_text}
                </span>
            </div>

            <!-- 比对信息表格 -->
            {alignment_table}

            <!-- 共线图 -->
            {synteny_chart}

            <!-- Gap闭合标准说明 -->
            <div class="gap-closure-standards" style="margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px; border-left: 3px solid #3498db;">
                <h6 style="margin: 0 0 10px 0; color: #2c3e50;">🎯 Gap闭合标准</h6>
                <ul style="margin: 0; padding-left: 20px; color: #7f8c8d;">
                    <li><strong>比对长度要求</strong>：≥ 10,000 bp（当前：{alignment_info.get('terminal_align_len', 0):,} bp）</li>
                    <li><strong>比对质量</strong>：序列一致性 {alignment_info.get('identity', 0):.2f}%</li>
                </ul>
            </div>
        </div>
        """

    def _generate_extension_synteny_chart(self, alignment_info):
        """生成延伸序列比对共线图"""
        if not alignment_info:
            return "<p>无比对数据可绘制共线图</p>"

        # 获取序列信息
        terminal_len = alignment_info.get('terminal_total_len', 60000)
        extension_len = alignment_info.get('extension_total_len', 100000)

        terminal_start = alignment_info.get('terminal_start', 0)
        terminal_end = alignment_info.get('terminal_end', 0)
        extension_start = alignment_info.get('extension_start', 0)
        extension_end = alignment_info.get('extension_end', 0)

        identity = alignment_info.get('identity', 0)
        meets_standard = alignment_info.get('meets_gap_closure_standard', False)

        # SVG参数
        svg_width = 1000
        svg_height = 300
        margin = 60

        # 计算绘图区域
        plot_width = svg_width - 2 * margin
        plot_height = svg_height - 2 * margin

        # 序列轴位置
        terminal_y = margin + 40
        extension_y = svg_height - margin - 40

        # 计算比例尺
        terminal_scale = plot_width / terminal_len
        extension_scale = plot_width / extension_len

        # 计算比对区域位置
        terminal_align_x1 = margin + terminal_start * terminal_scale
        terminal_align_x2 = margin + terminal_end * terminal_scale
        extension_align_x1 = margin + extension_start * extension_scale
        extension_align_x2 = margin + extension_end * extension_scale

        # 颜色设置
        alignment_color = "#2ecc71" if meets_standard else "#f39c12"
        connection_color = "#3498db" if meets_standard else "#e67e22"

        return f"""
        <div class="synteny-chart" style="margin: 20px 0;">
            <h6 style="text-align: center; margin-bottom: 15px; color: #2c3e50;" data-i18n="alignment.synteny_title">延伸序列-TerminalSeq共线性图</h6>
            <svg width="{svg_width}" height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}">
                <!-- 背景 -->
                <rect width="{svg_width}" height="{svg_height}" fill="#f8f9fa" stroke="#e9ecef"/>

                <!-- TerminalSeq序列轴 -->
                <line x1="{margin}" y1="{terminal_y}" x2="{margin + plot_width}" y2="{terminal_y}"
                      stroke="#2c3e50" stroke-width="3"/>
                <text x="{margin - 10}" y="{terminal_y - 10}" fill="#2c3e50" font-weight="bold" font-size="12">
                    {alignment_info.get('terminal_name', 'TerminalSeq')}
                </text>
                <text x="{margin}" y="{terminal_y + 20}" fill="#7f8c8d" font-size="10">1</text>
                <text x="{margin + plot_width}" y="{terminal_y + 20}" fill="#7f8c8d" font-size="10">{terminal_len:,}</text>

                <!-- ExtensionSeq序列轴 -->
                <line x1="{margin}" y1="{extension_y}" x2="{margin + plot_width}" y2="{extension_y}"
                      stroke="#2c3e50" stroke-width="3"/>
                <text x="{margin - 10}" y="{extension_y + 20}" fill="#2c3e50" font-weight="bold" font-size="12">
                    {alignment_info.get('extension_name', 'ExtensionSeq')}
                </text>
                <text x="{margin}" y="{extension_y - 10}" fill="#7f8c8d" font-size="10">1</text>
                <text x="{margin + plot_width}" y="{extension_y - 10}" fill="#7f8c8d" font-size="10">{extension_len:,}</text>

                <!-- 比对区域 -->
                <rect x="{terminal_align_x1}" y="{terminal_y - 8}"
                      width="{terminal_align_x2 - terminal_align_x1}" height="16"
                      fill="{alignment_color}" stroke="{alignment_color}" stroke-width="2" opacity="0.7"/>

                <rect x="{extension_align_x1}" y="{extension_y - 8}"
                      width="{extension_align_x2 - extension_align_x1}" height="16"
                      fill="{alignment_color}" stroke="{alignment_color}" stroke-width="2" opacity="0.7"/>

                <!-- 连接线 -->
                <line x1="{terminal_align_x1}" y1="{terminal_y + 8}"
                      x2="{extension_align_x1}" y2="{extension_y - 8}"
                      stroke="{connection_color}" stroke-width="2" opacity="0.6"/>
                <line x1="{terminal_align_x2}" y1="{terminal_y + 8}"
                      x2="{extension_align_x2}" y2="{extension_y - 8}"
                      stroke="{connection_color}" stroke-width="2" opacity="0.6"/>

                <!-- 比对信息标签 -->
                <text x="{(terminal_align_x1 + terminal_align_x2) / 2}" y="{terminal_y - 15}"
                      fill="#2c3e50" font-size="10" text-anchor="middle" font-weight="bold">
                    {terminal_start:,}-{terminal_end:,} ({alignment_info.get('terminal_align_len', 0):,}bp)
                </text>
                <text x="{(extension_align_x1 + extension_align_x2) / 2}" y="{extension_y + 30}"
                      fill="#2c3e50" font-size="10" text-anchor="middle" font-weight="bold">
                    {extension_start:,}-{extension_end:,} ({alignment_info.get('extension_align_len', 0):,}bp)
                </text>

                <!-- 一致性信息 -->
                <text x="{svg_width / 2}" y="{(terminal_y + extension_y) / 2}"
                      fill="#2c3e50" font-size="12" text-anchor="middle" font-weight="bold">
                    Identity: {identity:.2f}%
                </text>
            </svg>

            <div style="text-align: center; margin-top: 10px; font-size: 0.9em; color: #7f8c8d;">
                <p>
                    <span data-i18n="alignment.synteny_chart_summary.alignment_length" data-length="{alignment_info.get('terminal_align_len', 0):,}">比对长度：{alignment_info.get('terminal_align_len', 0):,} bp</span> |
                    <span data-i18n="alignment.synteny_chart_summary.gap_closure_standard" data-status="{'meets' if meets_standard else 'not_meets'}">Gap闭合标准：{'✅ 达标' if meets_standard else '❌ 未达标'} (需要 ≥10,000 bp)</span>
                </p>
            </div>
        </div>
        """

    def _generate_round_details(self):
        """轮次详细信息现在作为子卡片显示在Gap可视化部分，此方法返回空字符串"""
        return ""

    def _generate_reads_info(self, round_data):
        """生成reads信息"""
        used_reads = round_data.get('used_reads_list', [])
        if not used_reads:
            return ""

        # 显示所有reads，使用滚动效果
        reads_html = f"""
        <div style="margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 10px;">
            <h5 style="color: #2c3e50; margin-bottom: 10px;">🧬 使用的Reads列表 (共 {len(used_reads)} 条)</h5>
            <div style="font-family: monospace; font-size: 0.9em; line-height: 1.4; max-height: 300px; overflow-y: auto; border: 1px solid #e9ecef; border-radius: 5px; padding: 10px; background: white;">
        """

        for read in used_reads:
            reads_html += f"<div style='margin: 2px 0; padding: 2px 5px; background: #f8f9fa; border-radius: 3px; border-left: 3px solid #3498db;'>{read}</div>"

        reads_html += """
            </div>
        </div>
        """

        return reads_html

    def _generate_statistics_section(self):
        """生成统计信息部分"""
        rounds = self.data.get('rounds', [])
        final_info = self.data.get('final_info', {})
        initial_info = self.data.get('initial_info', {})
        direct_connection = self.data.get('direct_connection', {})

        # 计算统计数据
        total_rounds = len(rounds)
        initial_length = initial_info.get('right_length', 0)
        final_length = rounds[-1].get('output_length', initial_length) if rounds else initial_length
        # 修复：使用各轮次extension_length的累计值，而不是final_length - initial_length
        total_extension = sum(round_data.get('extension_length', 0) for round_data in rounds)

        total_reads_used = sum(round_data.get('used_reads_num', 0) for round_data in rounds)
        total_candidate_reads = sum(round_data.get('extension_reads_num', 0) for round_data in rounds)

        # 方法统计
        hifiasm_count = sum(1 for r in rounds if r.get('extension_method') == 'hifiasm')
        reads_common_count = sum(1 for r in rounds if r.get('extension_method') == 'readsCommon')
        only_one_read_count = sum(1 for r in rounds if r.get('extension_method') == 'onlyOneRead')

        # 效率计算
        reads_efficiency = (total_reads_used / total_candidate_reads * 100) if total_candidate_reads > 0 else 0
        avg_extension_per_round = total_extension / total_rounds if total_rounds > 0 else 0

        # 分析连接状态和最终结果
        direct_connection_success = direct_connection.get('connection_found', False)
        # 使用 extension_success 来判断延伸是否成功，而不是 success
        extension_connection_success = final_info.get('extension_success', final_info.get('success', False))
        # 整体是否成功（可能通过延伸或直接连接）
        overall_success = final_info.get('overall_success', final_info.get('success', False))
        used_direct_connection = final_info.get('used_direct_connection', False)

        # 确定最终使用的结果和处理状态
        if extension_connection_success:
            # 延申连接成功，使用延申连接结果
            final_status = '成功'
            final_status_class = 'badge-success'
            final_status_icon = '✅'
            used_result = '延申连接结果'
        elif direct_connection_success and used_direct_connection:
            # 延申连接失败但直接连接成功，使用直接连接结果
            final_status = '成功'
            final_status_class = 'badge-success'
            final_status_icon = '✅'
            used_result = '直接连接结果'
        else:
            # 都失败，处理状态为失败
            final_status = '失败'
            final_status_class = 'badge-danger'
            final_status_icon = '❌'
            used_result = '无可用结果'

        # 连接状态显示
        direct_status = '成功' if direct_connection_success else '失败'
        direct_status_icon = '✅' if direct_connection_success else '❌'
        extension_status = '成功' if extension_connection_success else '失败'
        extension_status_icon = '✅' if extension_connection_success else '❌'

        gap_length = final_info.get('gap_length', 'N/A')
        gap_length_display = f"{gap_length:,} bp" if gap_length != 'N/A' else 'N/A'
        final_sequence_id = final_info.get('final_sequence_id', 'N/A')

        # 计算填补Gap长度：总延伸长度减去与terminal序列的重叠长度
        filled_gap_length = 0
        if rounds and extension_connection_success:
            last_round = rounds[-1]
            last_round_extension = last_round.get('extension_length', 0)
            last_round_alignment = last_round.get('extension_alignment', {})

            if last_round_alignment:
                # 获取比对信息
                terminal_align_len = last_round_alignment.get('terminal_align_len', 0)

                # 填补Gap长度 = 总延伸长度 - 与terminal序列的重叠长度
                # 重叠部分不算作填补的Gap，因为这部分是与已有序列重复的
                filled_gap_length = max(0, total_extension - terminal_align_len)

                print(f"Debug: 计算填补Gap长度")
                print(f"  总延伸长度: {total_extension} bp")
                print(f"  与terminal重叠长度: {terminal_align_len} bp")
                print(f"  填补Gap长度: {filled_gap_length} bp")
            else:
                # 如果没有比对信息，使用总延申长度
                filled_gap_length = total_extension
                print(f"Debug: 无比对信息，使用总延伸长度: {filled_gap_length} bp")
        
        filled_gap_length_display = f"{filled_gap_length:,} bp" if filled_gap_length > 0 else "0 bp"

        return f"""
        <div class="section">
            <div class="section-title" data-i18n="processing_stats.title">
                📊 处理统计
            </div>

            <!-- 横向统计表格 -->
            <table class="statistics-table-horizontal">
                <thead>
                    <tr>
                        <th data-i18n="processing_stats.table_headers.status">处理状态</th>
                        <th data-i18n="processing_stats.table_headers.initial_gap_length">初始Gap长度</th>
                        <th data-i18n="processing_stats.table_headers.filled_gap_length">填补Gap长度</th>
                        <th data-i18n="processing_stats.table_headers.rounds">延伸轮次</th>
                        <th data-i18n="processing_stats.table_headers.total_extension">总延伸长度</th>
                        <th data-i18n="processing_stats.table_headers.total_reads">使用Reads总数</th>
                        <th data-i18n="processing_stats.table_headers.reads_efficiency">Reads利用效率</th>
                        <th data-i18n="processing_stats.table_headers.avg_extension">平均每轮延伸</th>
                        <th data-i18n="processing_stats.table_headers.method_stats">方法统计</th>
                        <th data-i18n="processing_stats.table_headers.final_sequence_id">最终序列ID</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>
                            <span class="badge {final_status_class}" data-status-type="gap_filling" data-status="{final_status}">{final_status_icon} <span data-i18n-status="gap_filling_{final_status}">Gap填充{final_status}</span></span>
                        </td>
                        <td>{gap_length_display}</td>
                        <td>{filled_gap_length_display}</td>
                        <td>{total_rounds}</td>
                        <td>{total_extension:,} bp</td>
                        <td>{total_reads_used:,}</td>
                        <td>{reads_efficiency:.1f}%</td>
                        <td>{avg_extension_per_round:,.0f} bp</td>
                        <td>hifiasm:{hifiasm_count} / readsCommon:{reads_common_count} / onlyOneRead:{only_one_read_count}</td>
                        <td><code>{final_sequence_id}</code></td>
                    </tr>
                </tbody>
            </table>

            <!-- 连接状态说明 -->
            <div class="connection-status-explanation">
                <h4>🔗 连接状态说明</h4>
                <div class="connection-status-grid">
                    <div class="status-item">
                        <span class="status-label" data-i18n="processing_stats.connection_status.direct_connection">直接连接：</span>
                        <span class="status-result">{direct_status_icon} <span data-i18n-status="{direct_status}">{direct_status}</span></span>
                    </div>
                    <div class="status-item">
                        <span class="status-label" data-i18n="processing_stats.connection_status.extension_connection">延申连接：</span>
                        <span class="status-result">{extension_status_icon} <span data-i18n-status="{extension_status}">{extension_status}</span></span>
                    </div>
                    <div class="status-item final-result">
                        <span class="status-label" data-i18n="processing_stats.connection_status.used_result">使用结果：</span>
                        <span class="status-result" data-i18n-result="{used_result}">{used_result}</span>
                    </div>
                </div>
                <div class="logic-explanation">
                    <p><strong>处理逻辑：</strong></p>
                    <ul>
                        <li>如果延申连接成功 → 使用延申连接结果</li>
                        <li>如果延申连接失败，直接连接成功 → 使用直接连接结果</li>
                        <li>如果都失败 → 处理状态为失败</li>
                    </ul>
                </div>
            </div>
        </div>
        """



    def _generate_javascript(self):
        """生成JavaScript代码"""
        # 准备数据
        rounds_data = json.dumps(self.data.get('rounds', []))
        initial_info = json.dumps(self.data.get('initial_info', {}))

        # 准备比对数据 - 从direct_connection中获取
        alignment_data = []
        if 'direct_connection' in self.data:
            alignment_file = self.data['direct_connection'].get('alignment_file', '')
            if alignment_file:
                alignment_data = self._read_alignment_file(alignment_file)

        alignment_data_js = json.dumps(alignment_data)

        return f"""
        // 语言包
        const i18n = {{
            zh: {{
                header: {{
                    title: '🧬 DEGAP v2 Gapfiller 可视化报告',
                    subtitle: '动态展示Gap填充过程 - 生成时间: {{time}}',
                    rounds: '📊 {{count}} 轮延伸',
                    direct_connection: '🔗 使用直连'
                }},
                status: {{
                    success: '✅ Gap填充成功',
                    failed: '❌ 填充失败',
                    no_extension: '❌ 无延伸发现',
                    max_extension: '⚠️ 达到最大延伸限制',
                    initial_left: '初始状态 - 准备从左序列向右延伸填充Gap',
                    initial_right: '初始状态 - 准备从右序列向左延伸填充Gap'
                }},
                timeline: {{
                    initial: '初始状态',
                    round: '第{{round}}轮 / 共{{total}}轮'
                }},
                gap: {{
                    region: 'Gap Region',
                    direction_left: 'Extension Direction →',
                    direction_right: '← Extension Direction'
                }},
                alignment: {{
                    title: '🔗 延伸序列与TerminalSeq比对分析',
                    synteny_title: '延伸序列-TerminalSeq共线性图',
                    extension_part: '延伸部分',
                    no_data: '本轮比对未得到结果',
                    table_headers: {{
                        sequence_pair: '比对序列对',
                        terminal_region: 'TerminalSeq区间',
                        extension_region: 'ExtensionSeq区间',
                        alignment_length: '比对长度',
                        identity: '一致性',
                        standard_check: '标准检查'
                    }},
                    standard_status: {{
                        meets_standard: '✅ 达标 (≥10,000bp)',
                        not_meets_standard: '❌ 未达标 (<10,000bp)'
                    }},
                    gap_closure_standards: {{
                        title: '🎯 Gap闭合标准',
                        length_requirement: '比对长度要求：≥ 10,000 bp（当前：{{length}} bp）',
                        quality_requirement: '比对质量：序列一致性 {{identity}}%',
                        coverage_requirement: '比对覆盖：TerminalSeq覆盖度 {{coverage}}%'
                    }},
                    no_alignment_chart: '无比对数据可绘制共线图',
                    synteny_chart_summary: {{
                        alignment_length: '比对长度：{{length}} bp',
                        gap_closure_standard: 'Gap闭合标准：{{status}} (需要 ≥10,000 bp)',
                        meets_standard: '✅ 达标',
                        not_meets_standard: '❌ 未达标'
                    }}
                }},
                direct_connection: {{
                    title: '🔗 直接连接检查',
                    status: '处理状态',
                    left_length: '左序列长度',
                    right_length: '右序列长度',
                    result: '检查结果',
                    can_connect: '可以直接连接',
                    cannot_connect: '无法直接连接',
                    no_connection: '无直接连接检查',
                    standards_title: '🎯 直接连接标准',
                    length_requirement_title: '比对长度',
                    length_requirement_desc: '：要求≥10,000bp，确保连接的可靠性',
                    position_requirement_title: '位置要求',
                    position_requirement_desc: '：比对区域必须接近序列边缘(≤500bp)，确保能够直接连接',
                    quality_requirement_title: '质量要求',
                    quality_requirement_desc: '：序列一致性≥80%，确保连接的准确性',
                    analysis_result: 'Analysis Result:'
                }},
                analysis: {{
                    result_title: '分析结果：',
                    gap_closed_success: '延伸序列与TerminalSeq成功比对，比对长度为{{length}}bp，序列一致性为{{identity}}%，满足Gap闭合标准（≥10,000bp），Gap已成功闭合。下一步操作：延伸过程结束。',
                    meets_standard: '延伸序列与TerminalSeq比对长度为{{length}}bp，已达到Gap闭合标准（≥10,000bp）。下一步操作：继续延伸。',
                    below_standard: '延伸序列与TerminalSeq比对长度为{{length}}bp，未达到Gap闭合标准（需要≥10,000bp），序列一致性为{{identity}}%。下一步操作：继续延伸以获得更长的比对区域。',
                    no_alignment: '延伸序列与TerminalSeq比对未得到有效结果，可能是延伸长度不足或序列相似性较低。下一步操作：继续延伸或调整参数。',
                    no_result: '本轮延伸序列与TerminalSeq的比对未得到有效结果，可能是延伸长度不足或序列相似性较低。下一步操作：继续延伸。',
                    next_actions: {{
                        gap_closed: '下一步操作：延伸过程结束，Gap已成功闭合',
                        continue_extension: '下一步操作：进入下一轮延伸',
                        no_extension_end: '下一步操作：延伸过程结束，本轮未能延伸',
                        max_length_reached: '下一步操作：延伸过程结束，达到最大延伸长度限制',
                        max_rounds_reached: '下一步操作：延伸过程结束，达到最大延伸轮次限制'
                    }}
                }},
                visualization: {{
                    title: '🎯 Gap填充可视化',
                    comparison_title: '📊 比对结果可视化',
                    alignment_file: '比对文件：',
                    cannot_read_file: '⚠️ 无法读取比对文件或文件为空',
                    found_records: '找到 {{count}} 条比对记录',
                    no_alignment_data: '无比对数据',
                    sequence: '序列',
                    left_region: 'Left区间',
                    right_region: 'Right区间',
                    alignment_length: '比对长度',
                    identity: '一致性',
                    connection_type: '连接类型',
                    description: '说明',
                    direct_connection: '✅ 直接连接',
                    partial_pass: '❌ 部分达标',
                    not_meet_standard: '❌ 不符合直接连接标准',
                    length_insufficient: '比对长度不足',
                    identity_insufficient: '序列一致性不足',
                    left_too_far: 'Left序列距离右端过远',
                    right_too_far: 'Right序列距离左端过远',
                    meets_degap_standard: '✅ 符合DEGAPv2标准',
                    length_pass: '长度达标',
                    identity_pass: '一致性达标',
                    position_pass: '位置达标',
                    pass: '✅ 通过',
                    fail: '❌ 不通过',
                    left_right_synteny: 'Left-Right序列共线性图'
                }},
                round_detail: {{
                    initial_state: '📋 初始状态',
                    initial_status: '起始状态',
                    extension_round: '🔄 第{{round}}轮延伸',
                    success_extension: '✅ 成功延伸',
                    no_extension: '❌ 无延伸',
                    unknown_status: '⚠️ 未知状态',
                    gap_closed: '✅ 已关闭',
                    gap_open: '🔓 未关闭',
                    table_headers: {{
                        extension_type: '延伸类型',
                        input_length: '输入长度',
                        extension_length: '延伸长度',
                        output_length: '输出长度',
                        candidate_reads: '候选Reads',
                        used_reads: '使用Reads',
                        extension_contig: '延伸Contig',
                        gap_status: 'Gap状态',
                        left_length: '左序列长度',
                        right_length: '右序列长度',
                        seed_length: '种子序列长度',
                        direct_connection: '直接连接'
                    }},
                    connection_status: {{
                        connectable: '✅ 可连接',
                        not_connectable: '❌ 不可连接'
                    }},
                    used_reads_title: '🧬 使用的Reads列表 (共{{count}}条)',
                    gap_analysis_title: '🎯 Gap闭合标准',
                    gap_analysis_items: {{
                        length_requirement: '比对长度要求：≥10,000 bp (当前：{{length}} bp)',
                        identity_requirement: '序列一致性：{{identity}}%',
                        terminal_requirement: 'TerminalSeq覆盖度：{{coverage}}%'
                    }}
                }},
                processing_stats: {{
                    title: '📊 处理统计',
                    table_headers: {{
                        status: '处理状态',
                        initial_gap_length: '初始Gap长度',
                        filled_gap_length: '填补Gap长度',
                        rounds: '延伸轮次',
                        total_extension: '总延伸长度',
                        total_reads: '使用Reads总数',
                        reads_efficiency: 'Reads利用效率',
                        avg_extension: '平均每轮延伸',
                        method_stats: '方法统计',
                        final_sequence_id: '最终序列ID'
                    }},
                    connection_status: {{
                        title: '🔗 连接状态说明',
                        direct_connection: '直接连接：',
                        extension_connection: '延申连接：',
                        used_result: '使用结果：',
                        processing_logic: '处理逻辑：',
                        logic_items: {{
                            extension_success: '如果延申连接成功 → 使用延申连接结果',
                            extension_fail_direct_success: '如果延申连接失败，直接连接成功 → 使用直接连接结果',
                            both_fail: '如果都失败 → 处理状态为失败'
                        }}
                    }},
                    status_values: {{
                        success: '成功',
                        failed: '失败',
                        gap_filling_success: 'Gap填充成功',
                        gap_filling_failed: 'Gap填充失败',
                        extension_result: '延申连接结果',
                        direct_result: '直接连接结果',
                        no_result: '无可用结果'
                    }}
                }}
            }},
            en: {{
                header: {{
                    title: '🧬 DEGAP v2 Gapfiller Visualization Report',
                    subtitle: 'Dynamic Gap Filling Process - Generated: {{time}}',
                    rounds: '📊 {{count}} Extension Rounds',
                    direct_connection: '🔗 Direct Connection'
                }},
                status: {{
                    success: '✅ Gap Filling Successful',
                    failed: '❌ Filling Failed',
                    no_extension: '❌ No Extension Found',
                    max_extension: '⚠️ Max Extension Limit Reached',
                    initial_left: 'Initial State - Ready to extend from left sequence to fill Gap',
                    initial_right: 'Initial State - Ready to extend from right sequence to fill Gap'
                }},
                timeline: {{
                    initial: 'Initial State',
                    round: 'Round {{round}} / Total {{total}}'
                }},
                gap: {{
                    region: 'Gap Region',
                    direction_left: 'Extension Direction →',
                    direction_right: '← Extension Direction'
                }},
                alignment: {{
                    title: '🔗 Extension-TerminalSeq Alignment Analysis',
                    synteny_title: 'Extension-TerminalSeq Synteny Chart',
                    extension_part: 'Extension Part',
                    no_data: 'No alignment result for this round',
                    table_headers: {{
                        sequence_pair: 'Sequence Pair',
                        terminal_region: 'TerminalSeq Region',
                        extension_region: 'ExtensionSeq Region',
                        alignment_length: 'Alignment Length',
                        identity: 'Identity',
                        standard_check: 'Standard Check'
                    }},
                    standard_status: {{
                        meets_standard: '✅ Meets Standard (≥10,000bp)',
                        not_meets_standard: '❌ Below Standard (<10,000bp)'
                    }},
                    gap_closure_standards: {{
                        title: '🎯 Gap Closure Standards',
                        length_requirement: 'Alignment Length Requirement: ≥ 10,000 bp (Current: {{length}} bp)',
                        quality_requirement: 'Alignment Quality: Sequence Identity {{identity}}%',
                        coverage_requirement: 'Alignment Coverage: TerminalSeq Coverage {{coverage}}%'
                    }},
                    no_alignment_chart: 'No alignment data available for synteny chart',
                    synteny_chart_summary: {{
                        alignment_length: 'Alignment Length: {{length}} bp',
                        gap_closure_standard: 'Gap Closure Standard: {{status}} (requires ≥10,000 bp)',
                        meets_standard: '✅ Meets Standard',
                        not_meets_standard: '❌ Below Standard'
                    }}
                }},
                direct_connection: {{
                    title: '🔗 Direct Connection Check',
                    status: 'Processing Status',
                    left_length: 'Left Sequence Length',
                    right_length: 'Right Sequence Length',
                    result: 'Check Result',
                    can_connect: 'Can connect directly',
                    cannot_connect: 'Cannot connect directly',
                    no_connection: 'No direct connection check',
                    standards_title: '🎯 Direct Connection Standards',
                    length_requirement_title: 'Alignment Length',
                    length_requirement_desc: ': Requires ≥10,000bp to ensure connection reliability',
                    position_requirement_title: 'Position Requirement',
                    position_requirement_desc: ': Alignment region must be close to sequence edges (≤500bp) to ensure direct connection',
                    quality_requirement_title: 'Quality Requirement',
                    quality_requirement_desc: ': Sequence identity ≥80% to ensure connection accuracy',
                    analysis_result: 'Analysis Result:'
                }},
                analysis: {{
                    result_title: 'Analysis Result:',
                    gap_closed_success: 'Extension sequence successfully aligned with TerminalSeq, alignment length {{length}}bp, sequence identity {{identity}}%, meets gap closure standard (≥10,000bp), gap successfully closed. Next action: Extension process completed.',
                    meets_standard: 'Extension sequence aligned with TerminalSeq with length {{length}}bp, meets gap closure standard (≥10,000bp). Next action: Continue extension.',
                    below_standard: 'Extension sequence aligned with TerminalSeq with length {{length}}bp, below gap closure standard (requires ≥10,000bp), sequence identity {{identity}}%. Next action: Continue extension for longer alignment region.',
                    no_alignment: 'Extension sequence alignment with TerminalSeq yielded no valid results, possibly due to insufficient extension length or low sequence similarity. Next action: Continue extension or adjust parameters.',
                    no_result: 'This round of extension sequence alignment with TerminalSeq yielded no valid results, possibly due to insufficient extension length or low sequence similarity. Next action: Continue extension.',
                    next_actions: {{
                        gap_closed: 'Next action: Extension process completed, gap successfully closed',
                        continue_extension: 'Next action: Proceed to next extension round',
                        no_extension_end: 'Next action: Extension process ended, no extension in this round',
                        max_length_reached: 'Next action: Extension process ended, maximum extension length reached',
                        max_rounds_reached: 'Next action: Extension process ended, maximum extension rounds reached'
                    }}
                }},
                visualization: {{
                    title: '🎯 Gap Filling Visualization',
                    comparison_title: '📊 Alignment Results Visualization',
                    alignment_file: 'Alignment File:',
                    cannot_read_file: '⚠️ Cannot read alignment file or file is empty',
                    found_records: 'Found {{count}} alignment records',
                    no_alignment_data: 'No alignment data',
                    sequence: 'Sequence',
                    left_region: 'Left Region',
                    right_region: 'Right Region',
                    alignment_length: 'Alignment Length',
                    identity: 'Identity',
                    connection_type: 'Connection Type',
                    description: 'Description',
                    direct_connection: '✅ Direct Connection',
                    partial_pass: '❌ Partially Qualified',
                    not_meet_standard: '❌ Does not meet direct connection standard',
                    length_insufficient: 'Alignment length insufficient',
                    identity_insufficient: 'Sequence identity insufficient',
                    left_too_far: 'Left sequence too far from right end',
                    right_too_far: 'Right sequence too far from left end',
                    meets_degap_standard: '✅ Meets DEGAPv2 standard',
                    length_pass: 'Length qualified',
                    identity_pass: 'Identity qualified',
                    position_pass: 'Position qualified',
                    pass: '✅ Pass',
                    fail: '❌ Fail',
                    left_right_synteny: 'Left-Right Sequence Synteny Chart'
                }},
                round_detail: {{
                    initial_state: '📋 Initial State',
                    initial_status: 'Starting State',
                    extension_round: '🔄 Round {{round}} Extension',
                    success_extension: '✅ Successfully Extended',
                    no_extension: '❌ No Extension',
                    unknown_status: '⚠️ Unknown Status',
                    gap_closed: '✅ Closed',
                    gap_open: '🔓 Open',
                    table_headers: {{
                        extension_type: 'Extension Type',
                        input_length: 'Input Length',
                        extension_length: 'Extension Length',
                        output_length: 'Output Length',
                        candidate_reads: 'Candidate Reads',
                        used_reads: 'Used Reads',
                        extension_contig: 'Extension Contig',
                        gap_status: 'Gap Status',
                        left_length: 'Left Sequence Length',
                        right_length: 'Right Sequence Length',
                        seed_length: 'Seed Sequence Length',
                        direct_connection: 'Direct Connection'
                    }},
                    connection_status: {{
                        connectable: '✅ Connectable',
                        not_connectable: '❌ Not Connectable'
                    }},
                    used_reads_title: '🧬 Used Reads List ({{count}} reads)',
                    gap_analysis_title: '🎯 Gap Closure Standards',
                    gap_analysis_items: {{
                        length_requirement: 'Alignment Length Requirement: ≥10,000 bp (Current: {{length}} bp)',
                        identity_requirement: 'Sequence Identity: {{identity}}%',
                        terminal_requirement: 'TerminalSeq Coverage: {{coverage}}%'
                    }}
                }},
                processing_stats: {{
                    title: '📊 Processing Statistics',
                    table_headers: {{
                        status: 'Processing Status',
                        initial_gap_length: 'Initial Gap Length',
                        filled_gap_length: 'Filled Gap Length',
                        rounds: 'Extension Rounds',
                        total_extension: 'Total Extension Length',
                        total_reads: 'Total Reads Used',
                        reads_efficiency: 'Reads Efficiency',
                        avg_extension: 'Average Extension per Round',
                        method_stats: 'Method Statistics',
                        final_sequence_id: 'Final Sequence ID'
                    }},
                    connection_status: {{
                        title: '🔗 Connection Status Explanation',
                        direct_connection: 'Direct Connection:',
                        extension_connection: 'Extension Connection:',
                        used_result: 'Used Result:',
                        processing_logic: 'Processing Logic:',
                        logic_items: {{
                            extension_success: 'If extension connection succeeds → Use extension connection result',
                            extension_fail_direct_success: 'If extension connection fails but direct connection succeeds → Use direct connection result',
                            both_fail: 'If both fail → Processing status is failed'
                        }}
                    }},
                    status_values: {{
                        success: 'Success',
                        failed: 'Failed',
                        gap_filling_success: 'Gap Filling Success',
                        gap_filling_failed: 'Gap Filling Failed',
                        extension_result: 'Extension Connection Result',
                        direct_result: 'Direct Connection Result',
                        no_result: 'No Available Result'
                    }}
                }}
            }}
        }};

        // 当前语言
        let currentLanguage = 'zh';

        // 语言切换函数
        function switchLanguage(lang) {{
            currentLanguage = lang;

            // 更新按钮状态
            document.querySelectorAll('.language-btn').forEach(btn => {{
                btn.classList.remove('active');
            }});
            document.getElementById(`lang-${{lang}}`).classList.add('active');

            // 更新所有带有data-i18n属性的元素
            updateI18nElements();

            // 重新生成动态内容
            updateDisplay();

            // 更新分析结果文本
            updateAnalysisResultText();

            // 更新处理统计卡片
            updateProcessingStatsCard();
        }}

        // 更新国际化元素
        function updateI18nElements() {{
            document.querySelectorAll('[data-i18n]').forEach(element => {{
                const key = element.getAttribute('data-i18n');
                const keys = key.split('.');
                let text = i18n[currentLanguage];

                for (const k of keys) {{
                    text = text[k];
                }}

                if (text) {{
                    // 处理模板变量
                    if (element.hasAttribute('data-time')) {{
                        text = text.replace('{{time}}', element.getAttribute('data-time'));
                    }}
                    if (element.hasAttribute('data-count')) {{
                        text = text.replace('{{count}}', element.getAttribute('data-count'));
                    }}
                    if (element.hasAttribute('data-length')) {{
                        text = text.replace('{{length}}', element.getAttribute('data-length'));
                    }}
                    if (element.hasAttribute('data-status')) {{
                        const status = element.getAttribute('data-status');
                        if (status === 'meets') {{
                            text = text.replace('{{status}}', t('alignment.synteny_chart_summary.meets_standard'));
                        }} else if (status === 'not_meets') {{
                            text = text.replace('{{status}}', t('alignment.synteny_chart_summary.not_meets_standard'));
                        }}
                    }}

                    element.textContent = text;
                }}
            }});
        }}

        // 获取翻译文本
        function t(key, params = {{}}) {{
            const keys = key.split('.');
            let text = i18n[currentLanguage];

            for (const k of keys) {{
                text = text[k];
            }}

            if (text && typeof text === 'string') {{
                // 替换参数
                for (const [param, value] of Object.entries(params)) {{
                    text = text.replace(`{{${{param}}}}`, value);
                }}
            }}

            return text || key;
        }}

        // 全局变量
        let currentRound = 0;
        let roundsData = {rounds_data};
        let initialInfo = {initial_info};
        const flag = '{self.flag}';
        const maxExtensionLength = {self.max_extension_length if self.max_extension_length else 'null'};
        let totalRounds = roundsData.length;
        let selectedExtensionAlignment = 1; // 默认选中第一条

        // 初始化
        document.addEventListener('DOMContentLoaded', function() {{
            // 初始化国际化
            updateI18nElements();
            updateDisplay();

            // 初始化分页比对表格（如果存在）
            if (typeof tableAlignmentData !== 'undefined' && tableAlignmentData.length > 0) {{
                initializeAlignmentTable();
                if (tableAlignmentData.length > 0) {{
                    selectAlignment(1);
                }}
            }} else if (typeof initializeStaticAlignmentTable === 'function') {{
                // 如果没有分页数据，使用静态表格初始化
                initializeStaticAlignmentTable();
                if (typeof alignmentTableData !== 'undefined' && alignmentTableData.length > 0) {{
                    selectAlignment(1);
                }}
            }}

            // 初始化分页共线图（如果存在）
            if (typeof syntenyAlignmentData !== 'undefined' && syntenyAlignmentData.length > 0) {{
                initializeSyntenyChart();
            }}

            // 初始化延伸序列比对表格
            initializeExtensionAlignmentTable();
        }});

        // 跳转到指定轮次
        function goToRound(round) {{
            currentRound = round;
            updateDisplay();
        }}

        // 上一轮 - 根据flag调整逻辑
        function goToPrevRound() {{
            if (flag === 'right') {{
                // right模式：与left相反，左按钮表示时间上的下一轮（round号码增加）
                if (currentRound < totalRounds) {{
                    currentRound++;
                    updateDisplay();
                }}
            }} else {{
                // left模式：左按钮表示时间上的上一轮（round号码减少）
                if (currentRound > 0) {{
                    currentRound--;
                    updateDisplay();
                }}
            }}
        }}

        // 下一轮 - 根据flag调整逻辑
        function goToNextRound() {{
            if (flag === 'right') {{
                // right模式：与left相反，右按钮表示时间上的上一轮（round号码减少）
                if (currentRound > 0) {{
                    currentRound--;
                    updateDisplay();
                }}
            }} else {{
                // left模式：右按钮表示时间上的下一轮（round号码增加）
                if (currentRound < totalRounds) {{
                    currentRound++;
                    updateDisplay();
                }}
            }}
        }}

        // 更新导航按钮状态
        function updateNavButtons() {{
            const prevBtn = document.getElementById('prevRoundBtn');
            const nextBtn = document.getElementById('nextRoundBtn');

            if (flag === 'right') {{
                // right模式：与left相反，左按钮=下一轮，右按钮=上一轮
                if (prevBtn) {{
                    prevBtn.disabled = currentRound >= totalRounds;
                }}
                if (nextBtn) {{
                    nextBtn.disabled = currentRound === 0;
                }}
            }} else {{
                // left模式：左按钮=上一轮，右按钮=下一轮
                if (prevBtn) {{
                    prevBtn.disabled = currentRound === 0;
                }}
                if (nextBtn) {{
                    nextBtn.disabled = currentRound >= totalRounds;
                }}
            }}
        }}

        // 更新显示
        function updateDisplay() {{
            updateTimeline();
            updateGapVisualization();
            updateRoundDetailCard();
            updateCurrentRoundDisplay();
            updateNavButtons();
        }}

        // 更新timeline
        function updateTimeline() {{
            const timelinePoints = document.querySelectorAll('.timeline-point');
            const timelineLines = document.querySelectorAll('.timeline-line');

            timelinePoints.forEach((point, index) => {{
                point.classList.remove('active', 'completed');

                // 获取按钮对应的实际round号码
                const roundNum = parseInt(point.textContent);

                if (roundNum === currentRound) {{
                    point.classList.add('active');
                }} else if (roundNum < currentRound) {{
                    point.classList.add('completed');
                }}
            }});

            // 对于连接线，需要根据flag调整逻辑
            timelineLines.forEach((line, index) => {{
                line.classList.remove('completed');

                // 获取连接线前后两个点的round号码
                const points = Array.from(timelinePoints);
                let beforeRound, afterRound;

                if (flag === 'right') {{
                    // right模式：与left相反，连接线在反转后的位置
                    beforeRound = index < points.length - 1 ? parseInt(points[index].textContent) : -1;
                    afterRound = index + 1 < points.length ? parseInt(points[index + 1].textContent) : -1;
                }} else {{
                    // left模式：正常顺序
                    beforeRound = index > 0 ? parseInt(points[index - 1].textContent) : -1;
                    afterRound = index < points.length ? parseInt(points[index].textContent) : -1;
                }}

                // 如果连接线两端的较小round号码小于currentRound，则标记为completed
                const minRound = Math.min(beforeRound, afterRound);
                if (minRound >= 0 && minRound < currentRound) {{
                    line.classList.add('completed');
                }}
            }});
        }}

        // 更新Gap可视化 - 改进版：动态生成延伸段
        function updateGapVisualization() {{
            const extensionContainer = document.getElementById('extensionContainer');
            if (!extensionContainer) return;

            // 清空现有的延伸段
            extensionContainer.innerHTML = '';

            // 如果没有轮次数据或当前轮次为0，不显示任何延伸
            if (currentRound === 0 || roundsData.length === 0) {{
                return;
            }}

            // SVG参数（与生成时保持一致）
            const svgWidth = 1200;
            const svgHeight = 250;
            const margin = 50;
            const leftWidth = 250;
            const rightWidth = 250;
            const leftX = margin;
            const leftY = svgHeight / 2 - 20;
            const rightX = svgWidth - margin - rightWidth;
            const gapX = leftX + leftWidth;
            const gapWidth = rightX - gapX;

            // 计算要显示的轮次（从1到currentRound）
            const roundsToShow = Math.min(currentRound, roundsData.length);

            // 检查是否为失败情况（最后一轮无延伸或gap未闭合）
            const isFailed = roundsData.length > 0 && !roundsData[roundsData.length - 1].gap_closed;
            const isSuccessful = roundsData.length > 0 && roundsData[roundsData.length - 1].gap_closed;

            // 计算所有轮次的总延伸长度（用于确定每轮的固定比例）
            let allRoundsTotalLength = 0;
            let cumulativeLength = 0;
            for (let i = 0; i < roundsData.length; i++) {{
                const extensionLength = Math.abs(roundsData[i].extension_length || 0);
                // 应用最大延伸长度限制
                if (maxExtensionLength && cumulativeLength + extensionLength > maxExtensionLength) {{
                    // 如果超过限制，只计算到限制为止的部分
                    const remainingLength = maxExtensionLength - cumulativeLength;
                    if (remainingLength > 0) {{
                        allRoundsTotalLength += remainingLength;
                        cumulativeLength = maxExtensionLength;
                    }}
                    break;
                }} else {{
                    allRoundsTotalLength += extensionLength;
                    cumulativeLength += extensionLength;
                }}
            }}

            // 生成延伸段 - 根据flag确定起始位置和方向
            let currentX, extensionDirection;
            if (flag === 'left') {{
                // 从左序列开始延伸，向右延伸
                currentX = gapX;
                extensionDirection = 1; // 向右
            }} else {{
                // flag=right：与left相反，从右序列开始延伸，向左延伸
                currentX = gapX + gapWidth;
                extensionDirection = -1; // 向左
            }}

            // 确定可用宽度 - 成功时100%，失败时80%
            const availableWidth = isSuccessful ? gapWidth * 1.00 : gapWidth * 0.80;

            // 跟踪累积延伸长度以应用最大延伸长度限制
            let cumulativeExtensionLength = 0;

            for (let i = 0; i < roundsToShow; i++) {{
                const roundData = roundsData[i];
                const extensionLength = roundData.extension_length || 0;
                let absExtensionLength = Math.abs(extensionLength);

                // 应用最大延伸长度限制
                if (maxExtensionLength && cumulativeExtensionLength + absExtensionLength > maxExtensionLength) {{
                    // 如果超过限制，只显示到限制为止的部分
                    const remainingLength = maxExtensionLength - cumulativeExtensionLength;
                    if (remainingLength <= 0) {{
                        break; // 已达到最大延伸长度，停止显示后续轮次
                    }}
                    absExtensionLength = remainingLength;
                }}

                cumulativeExtensionLength += absExtensionLength;

                if (absExtensionLength > 0) {{
                    // 计算段宽度 - 基于在所有轮次中的固定比例
                    let segmentWidth;
                    if (isSuccessful) {{
                        // 成功情况：每轮的宽度基于其在最终状态下的比例
                        segmentWidth = (absExtensionLength / allRoundsTotalLength) * availableWidth;
                    }} else {{
                        // 失败情况：也基于总延伸长度的比例，但使用较小的可用宽度
                        segmentWidth = (absExtensionLength / allRoundsTotalLength) * availableWidth;
                    }}

                    // 确保段宽度合理
                    if (segmentWidth > 0) {{
                        // 对于成功情况，确保最后一段（gap闭合段）能够显示
                        if (isSuccessful && roundData.gap_closed) {{
                            // gap闭合段必须显示，调整宽度以适应剩余空间
                            let remainingWidth;
                            if (extensionDirection === 1) {{
                                // 向右延伸：计算到右边界的剩余宽度
                                remainingWidth = gapX + availableWidth - currentX;
                            }} else {{
                                // 向左延伸：计算到左边界的剩余宽度
                                remainingWidth = currentX - gapX;
                            }}
                            if (segmentWidth > remainingWidth && remainingWidth > 10) {{
                                segmentWidth = remainingWidth - 2; // 留2px边距
                            }}
                        }}

                        // 根据延伸方向计算实际位置
                        let segmentX;
                        if (extensionDirection === 1) {{
                            // 向右延伸
                            segmentX = currentX;
                        }} else {{
                            // 向左延伸
                            segmentX = currentX - segmentWidth;
                        }}

                        // 检查是否超出边界 - 调整逻辑以确保所有延申块都能显示在80%的空间内
                        let withinBounds = true;
                        if (extensionDirection === 1) {{
                            // 向右延伸：如果超出边界，调整宽度而不是隐藏
                            if (segmentX + segmentWidth > gapX + availableWidth) {{
                                segmentWidth = Math.max(5, gapX + availableWidth - segmentX); // 最小5px宽度
                            }}
                        }} else {{
                            // 向左延伸：如果超出边界，调整位置和宽度
                            if (segmentX < gapX) {{
                                segmentWidth = Math.max(5, segmentWidth - (gapX - segmentX));
                                segmentX = gapX;
                            }}
                        }}

                        if (withinBounds) {{
                        // 确定颜色
                        let color = '#2ecc71'; // 默认绿色（成功延伸）
                        if (roundData.gap_closed) {{
                            color = '#f39c12'; // 橙色（gap闭合）
                        }} else if (extensionLength < 0) {{
                            color = '#3498db'; // 蓝色（负值延伸/序列调整）
                        }}

                        // 创建延伸段矩形
                        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                        rect.setAttribute('x', segmentX);
                        rect.setAttribute('y', leftY + 5);
                        rect.setAttribute('width', segmentWidth);
                        rect.setAttribute('height', 30);
                        rect.setAttribute('fill', color);
                        rect.setAttribute('opacity', '0.8');
                        rect.setAttribute('rx', '3');
                        rect.setAttribute('stroke', '#2c3e50');
                        rect.setAttribute('stroke-width', '1');

                        extensionContainer.appendChild(rect);

                        // 添加轮次标签和延伸长度
                        if (segmentWidth > 25) {{
                            const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                            text.setAttribute('x', segmentX + segmentWidth / 2);
                            text.setAttribute('y', leftY + 20);
                            text.setAttribute('text-anchor', 'middle');
                            text.setAttribute('class', 'sequence-length-label');
                            text.setAttribute('fill', 'white');
                            text.setAttribute('font-weight', 'bold');
                            text.setAttribute('font-size', '9px');
                            text.textContent = `R${{i + 1}}`;

                            extensionContainer.appendChild(text);

                            // 添加延伸长度标签
                            const lengthText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                            lengthText.setAttribute('x', segmentX + segmentWidth / 2);
                            lengthText.setAttribute('y', leftY + 30);
                            lengthText.setAttribute('text-anchor', 'middle');
                            lengthText.setAttribute('class', 'sequence-length-label');
                            lengthText.setAttribute('fill', 'white');
                            lengthText.setAttribute('font-weight', 'normal');
                            lengthText.setAttribute('font-size', '8px');
                            lengthText.textContent = `${{(extensionLength/1000).toFixed(1)}}k`;

                            extensionContainer.appendChild(lengthText);
                        }}

                        // 根据延伸方向更新currentX
                        if (extensionDirection === 1) {{
                            currentX += segmentWidth + 2; // 向右延伸，增加位置
                        }} else {{
                            currentX -= segmentWidth + 2; // 向左延伸，减少位置
                        }}
                        }}
                    }}
                }}
            }}

            // 对于失败情况，末端留白（不添加任何可视元素）
            // 失败情况下，延伸段只占用75%的空间，剩余25%保持空白

            // 更新状态文本
            updateStatusText();
        }}

        // 更新状态文本
        function updateStatusText() {{
            const statusEl = document.getElementById('currentStatus');
            if (!statusEl) return;

            if (currentRound === 0) {{
                const statusKey = flag === 'left' ? 'status.initial_left' : 'status.initial_right';
                statusEl.innerHTML = t(statusKey);
                statusEl.style.color = '#7f8c8d';
            }} else if (currentRound <= roundsData.length) {{
                const roundData = roundsData[currentRound - 1];
                const method = roundData.extension_method || 'unknown';
                const extensionLength = roundData.extension_length || 0;

                if (roundData.gap_closed) {{
                    const text = currentLanguage === 'zh'
                        ? `第${{currentRound}}轮 (${{method}}) - <span style="color: #2ecc71;">✅ Gap成功关闭!</span> 延伸了 ${{extensionLength.toLocaleString()}} bp`
                        : `Round ${{currentRound}} (${{method}}) - <span style="color: #2ecc71;">✅ Gap Successfully Closed!</span> Extended ${{extensionLength.toLocaleString()}} bp`;
                    statusEl.innerHTML = text;
                }} else if (roundData.extension_status === 'no_extension') {{
                    const text = currentLanguage === 'zh'
                        ? `第${{currentRound}}轮 (${{method}}) - <span style="color: #e74c3c;">❌ 未找到有效延伸</span>`
                        : `Round ${{currentRound}} (${{method}}) - <span style="color: #e74c3c;">❌ No Valid Extension Found</span>`;
                    statusEl.innerHTML = text;
                }} else {{
                    const direction = currentLanguage === 'zh'
                        ? (flag === 'left' ? '继续向右填充' : '继续向左填充')
                        : (flag === 'left' ? 'continuing rightward filling' : 'continuing leftward filling');
                    const text = currentLanguage === 'zh'
                        ? `第${{currentRound}}轮 (${{method}}) - <span style="color: #3498db;">🔄 成功延伸</span> ${{extensionLength.toLocaleString()}} bp，${{direction}}`
                        : `Round ${{currentRound}} (${{method}}) - <span style="color: #3498db;">🔄 Successfully Extended</span> ${{extensionLength.toLocaleString()}} bp, ${{direction}}`;
                    statusEl.innerHTML = text;
                }}
            }}
        }}

        // 更新轮次详情卡片
        function updateRoundDetailCard() {{
            const cardEl = document.getElementById('roundDetailCard');
            if (!cardEl) return;

            if (currentRound === 0) {{
                // 显示初始状态
                cardEl.style.display = 'block';
                cardEl.innerHTML = `
                    <div class="round-detail-header">
                        <div class="round-detail-title">${{t('round_detail.initial_state')}}</div>
                        <div class="round-detail-status">
                            <span class="badge badge-info">${{t('round_detail.initial_status')}}</span>
                        </div>
                    </div>

                    <!-- 初始状态表格 -->
                    <table class="statistics-table-horizontal" style="margin-top: 15px;">
                        <thead>
                            <tr>
                                <th>${{t('round_detail.table_headers.left_length')}}</th>
                                <th>${{t('round_detail.table_headers.right_length')}}</th>
                                <th>${{t('round_detail.table_headers.seed_length')}}</th>
                                <th>${{t('round_detail.table_headers.direct_connection')}}</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td>${{(initialInfo.left_length || 0).toLocaleString()}} bp</td>
                                <td>${{(initialInfo.right_length || 0).toLocaleString()}} bp</td>
                                <td>${{(initialInfo.seed_length || 0).toLocaleString()}} bp</td>
                                <td>${{initialInfo.direct_connection ? t('round_detail.connection_status.connectable') : t('round_detail.connection_status.not_connectable')}}</td>
                            </tr>
                        </tbody>
                    </table>
                `;
            }} else if (currentRound > 0 && roundsData.length > 0) {{
                // 显示轮次详情
                const roundIndex = Math.min(currentRound - 1, roundsData.length - 1);
                const roundData = roundsData[roundIndex];

                // 确定延伸状态
                let statusBadge = '';
                const extensionStatus = roundData.extension_status || 'unknown';
                if (extensionStatus === 'extended') {{
                    statusBadge = `<span class="badge badge-success">${{t('round_detail.success_extension')}}</span>`;
                }} else if (extensionStatus === 'no_extension') {{
                    statusBadge = `<span class="badge badge-danger">${{t('round_detail.no_extension')}}</span>`;
                }} else {{
                    statusBadge = `<span class="badge badge-warning">${{t('round_detail.unknown_status')}}</span>`;
                }}

                // Gap状态
                const gapStatus = roundData.gap_closed ? t('round_detail.gap_closed') : t('round_detail.gap_open');
                const gapClass = roundData.gap_closed ? 'badge-success' : 'badge-warning';

                // 生成reads列表
                let readsHtml = '';
                if (roundData.used_reads_list && roundData.used_reads_list.length > 0) {{
                    const readsTitle = t('round_detail.used_reads_title').replace('{{count}}', roundData.used_reads_list.length);
                    readsHtml = `
                        <div class="round-detail-reads">
                            <h6>${{readsTitle}}</h6>
                            <div class="reads-list" style="max-height: 200px; overflow-y: auto; border: 1px solid #e9ecef; border-radius: 5px; padding: 10px; background: white;">
                                ${{roundData.used_reads_list.map(read => `<div class="reads-item" style="margin: 2px 0; padding: 2px 5px; background: #f8f9fa; border-radius: 3px; border-left: 3px solid #3498db;">${{read}}</div>`).join('')}}
                            </div>
                        </div>
                    `;
                }}

                cardEl.style.display = 'block';
                const roundTitle = t('round_detail.extension_round').replace('{{round}}', currentRound);
                cardEl.innerHTML = `
                    <div class="round-detail-header">
                        <div class="round-detail-title">${{roundTitle}}</div>
                        <div class="round-detail-status">${{statusBadge}}</div>
                    </div>

                    <!-- 统计指标表格 -->
                    <table class="statistics-table-horizontal" style="margin-top: 15px;">
                        <thead>
                            <tr>
                                <th>${{t('round_detail.table_headers.extension_type')}}</th>
                                <th>${{t('round_detail.table_headers.input_length')}}</th>
                                <th>${{t('round_detail.table_headers.extension_length')}}</th>
                                <th>${{t('round_detail.table_headers.output_length')}}</th>
                                <th>${{t('round_detail.table_headers.candidate_reads')}}</th>
                                <th>${{t('round_detail.table_headers.used_reads')}}</th>
                                <th>${{t('round_detail.table_headers.extension_contig')}}</th>
                                <th>${{t('round_detail.table_headers.gap_status')}}</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td><code>${{roundData.extension_method || 'N/A'}}</code></td>
                                <td>${{(roundData.input_length || 0).toLocaleString()}} bp</td>
                                <td>${{(roundData.extension_length || 0).toLocaleString()}} bp</td>
                                <td>${{(roundData.output_length || 0).toLocaleString()}} bp</td>
                                <td>${{(roundData.extension_reads_num || 0).toLocaleString()}}</td>
                                <td>${{(roundData.used_reads_num || 0).toLocaleString()}}</td>
                                <td><code>${{roundData.extension_contig || 'N/A'}}</code></td>
                                <td><span class="badge ${{gapClass}}">${{gapStatus}}</span></td>
                            </tr>
                        </tbody>
                    </table>

                    <!-- 延伸序列与TerminalSeq比对分析 -->
                    ${{generateExtensionAlignmentSection(roundData)}}

                    ${{readsHtml}}

                    <!-- 分析结果 -->
                    ${{generateAnalysisResultSection(roundData)}}
                `;
            }} else {{
                cardEl.style.display = 'none';
            }}
        }}

        // 生成延伸序列比对分析部分
        function generateExtensionAlignmentSection(roundData) {{
            const alignmentInfo = roundData.extension_alignment;
            if (!alignmentInfo) {{
                return `
                    <div class="extension-alignment-section" style="margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px; border-left: 3px solid #95a5a6;">
                        <h5 style="margin: 0 0 10px 0; color: #2c3e50;">${{t('alignment.title')}}</h5>
                        <p style="color: #7f8c8d; font-style: italic; margin: 0;">${{t('alignment.no_data')}}</p>
                    </div>
                `;
            }}

            const meetsStandard = alignmentInfo.meets_gap_closure_standard || false;
            const canCloseGap = alignmentInfo.can_close_gap || false;

            // 修复：在此函数内部定义坐标变量，解决作用域问题
            let terminalStart = alignmentInfo.terminal_start || 0;
            let terminalEnd = alignmentInfo.terminal_end || 0;
            let extensionStart = alignmentInfo.extension_start || 0;
            let extensionEnd = alignmentInfo.extension_end || 0;

            // 表格展示：直接显示 process.log 的原始坐标（不进行坐标转换）
            // 注意：共线图中的坐标窗口与映射在 generateExtensionSyntenyChart 内部处理
            // 因此这里保留 terminalStart/End 与 extensionStart/End 为 alignmentInfo 的原始值

            return `
                <div class="extension-alignment-section" style="margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px; border-left: 3px solid #3498db;">
                    <h5 style="margin: 0 0 15px 0; color: #2c3e50;">${{t('alignment.title')}}</h5>

                    <!-- 比对状态 -->
                    ${{canCloseGap ? `<div style="text-align: center; margin: 15px 0;">
                        <span class="badge badge-success" style="font-size: 1.1em; padding: 8px 16px;">
                            ✅ Gap可以闭合
                        </span>
                    </div>` : ''}}

                    <!-- 比对信息表格 -->
                    <div class="alignment-table-container">
                        <table class="alignment-table extension-alignment-table" style="font-size: 0.85em;">
                            <thead>
                                <tr>
                                    <th>${{t('alignment.table_headers.sequence_pair')}}</th>
                                    <th>${{t('alignment.table_headers.terminal_region')}}</th>
                                    <th>${{t('alignment.table_headers.extension_region')}}</th>
                                    <th>${{t('alignment.table_headers.alignment_length')}}</th>
                                    <th>${{t('alignment.table_headers.identity')}}</th>
                                    <th>${{t('alignment.table_headers.standard_check')}}</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr class="alignment-row ${{meetsStandard ? 'pass' : 'fail'}}" data-alignment-id="1">
                                    <td><strong>${{alignmentInfo.terminal_name || 'TerminalSeq'}} vs ${{alignmentInfo.extension_name || 'ExtensionSeq'}}</strong></td>
                                    <td>${{terminalStart.toLocaleString()}} - ${{terminalEnd.toLocaleString()}}</td>
                                    <td>${{extensionStart.toLocaleString()}} - ${{extensionEnd.toLocaleString()}}</td>
                                    <td class="${{meetsStandard ? 'pass' : 'fail'}}">${{(alignmentInfo.terminal_align_len || 0).toLocaleString()}} / ${{(alignmentInfo.extension_align_len || 0).toLocaleString()}} bp</td>
                                    <td>${{(alignmentInfo.identity || 0).toFixed(2)}}%</td>
                                    <td class="${{meetsStandard ? 'pass' : 'fail'}}">
                                        ${{meetsStandard ? t('alignment.standard_status.meets_standard') : t('alignment.standard_status.not_meets_standard')}}
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>

                    <!-- 延伸序列与TerminalSeq共线图 -->
                    ${{generateExtensionSyntenyChart(alignmentInfo, flag)}}

                    <!-- Gap闭合标准说明 -->
                    <div style="margin-top: 15px; padding: 12px; background: #e8f4fd; border-radius: 6px; border-left: 3px solid #3498db;">
                        <h6 style="margin: 0 0 8px 0; color: #2c3e50; font-size: 0.9em;">${{t('alignment.gap_closure_standards.title')}}</h6>
                        <ul style="margin: 0; padding-left: 18px; color: #7f8c8d; font-size: 0.85em;">
                            <li><strong>${{t('alignment.gap_closure_standards.length_requirement').replace('{{length}}', (alignmentInfo.terminal_align_len || 0).toLocaleString())}}</strong></li>
                            <li><strong>${{t('alignment.gap_closure_standards.quality_requirement').replace('{{identity}}', (alignmentInfo.identity || 0).toFixed(2))}}</strong></li>
                        </ul>
                    </div>
                </div>
            `;
        }}

        // 生成延伸序列与TerminalSeq共线图
        function generateExtensionSyntenyChart(alignmentInfo, flag) {{
            if (!alignmentInfo) {{
                return `<p style="text-align: center; color: #7f8c8d; font-style: italic; margin: 20px 0;">${{t('alignment.no_alignment_chart')}}</p>`;
            }}

            // 修复：显示完整序列，不进行种子序列截取
            // 显示完整的ptg000001l_hifi+ont_right vs ExtensionSequence-output10

            // 获取完整序列长度
            const originalLeftLen = initialInfo.left_length || 0;
            const originalRightLen = initialInfo.right_length || 0;

            // 修复：计算到当前轮次为止的累计延申长度
            let totalExtensionLen = 0;
            for (let i = 0; i < currentRound; i++) {{
                const roundData = roundsData[i];
                if (roundData && roundData.extension_length) {{
                    totalExtensionLen += roundData.extension_length;
                }}
            }}

            // 调试信息
            console.log('Debug - calculated totalExtensionLen:', totalExtensionLen);
            console.log('Debug - currentRound:', currentRound, 'roundsData length:', roundsData.length);
            console.log('Debug - originalLeftLen:', originalLeftLen);
            console.log('Debug - originalRightLen:', originalRightLen);
            console.log('Debug - initialInfo:', initialInfo);

            let terminalLen, extensionLen, extensionPartLen;

            if (flag === 'right') {{
                // flag=right: 显示完整序列
                // 上方: 完整的Left Sequence
                terminalLen = originalLeftLen;

                // 下方: Extension + 完整的Right Sequence
                extensionPartLen = totalExtensionLen; // 总延伸长度
                extensionLen = extensionPartLen + originalRightLen; // 总延伸长度 + 完整Right序列
            }} else {{
                // flag=left: 显示完整序列
                // 上方: 完整的Left Sequence + Extension
                terminalLen = originalRightLen; // 完整的Right序列
                extensionPartLen = totalExtensionLen; // 总延伸长度
                extensionLen = originalLeftLen + extensionPartLen; // 完整Left序列 + 总延伸长度
            }}

            // 解析延伸序列的组成
            const extensionName = alignmentInfo.extension_name || 'ExtensionSeq';

            // 获取种子序列长度信息
            const hifiSeedLen = {self.hifi_seed_len if hasattr(self, 'hifi_seed_len') else 76759};
            const ontSeedLen = {self.ont_seed_len if hasattr(self, 'ont_seed_len') else 868730};

            // 延伸序列-TerminalSeq共线性图统一使用HiFi种子长度
            const dataType = '{self.data_type if hasattr(self, 'data_type') else 'hifi'}';
            let leftSeedLen, rightSeedLen;

            // 统一使用HiFi种子长度
            leftSeedLen = rightSeedLen = hifiSeedLen;

            // 根据新方案计算序列组成和位置
            let originalSeqStart, originalSeqEnd, extensionPartStart, extensionPartEnd, originalSeqLen;
            let upperAxisStart, upperAxisEnd, lowerAxisStart, lowerAxisEnd;

            if (flag === 'right') {{
                // flag=right:
                // 下方轴为完整的 Extension + Right Sequence（全长）
                extensionPartStart = 0;
                extensionPartEnd = extensionPartLen;
                originalSeqStart = extensionPartLen;
                originalSeqEnd = extensionLen;  // 使用完整长度
                originalSeqLen = extensionLen - extensionPartLen; // Right序列完整长度

                // 下方轴显示范围：0 到 extensionPartLen + rightSeedLen
                lowerAxisStart = 0;
                lowerAxisEnd = extensionPartLen + rightSeedLen;

                // 上方轴显示Left序列尾端的种子窗口：[originalLeftLen - leftSeedLen, originalLeftLen]
                upperAxisStart = Math.max(0, originalLeftLen - leftSeedLen);
                upperAxisEnd = originalLeftLen;
            }} else {{
                // flag=left:
                // 上方轴为完整的 Left Sequence + Extension（全长）
                const leftSeedStart = originalLeftLen - leftSeedLen;  // Left种子序列开始位置
                originalSeqStart = leftSeedStart;
                originalSeqEnd = originalLeftLen;
                extensionPartStart = originalLeftLen;
                extensionPartEnd = extensionLen;
                originalSeqLen = leftSeedLen;

                // 上方轴显示范围：leftSeedStart 到 extensionLen（全长）
                upperAxisStart = leftSeedStart;
                upperAxisEnd = extensionLen;

                // 下方轴只显示Right种子序列：0 到 rightSeedLen（相对长度）
                lowerAxisStart = 0;
                lowerAxisEnd = rightSeedLen;
            }}

            // 修复：不进行坐标转换，直接使用原始坐标显示完整序列
            let terminalStart = alignmentInfo.terminal_start || 0;
            let terminalEnd = alignmentInfo.terminal_end || 0;
            let extensionStart = alignmentInfo.extension_start || 0;
            let extensionEnd = alignmentInfo.extension_end || 0;

            // 不进行任何坐标转换，保持原始坐标以显示完整序列

            const identity = alignmentInfo.identity || 0;
            const meetsStandard = alignmentInfo.meets_gap_closure_standard || false;

            // SVG参数 - 与Left-Right图保持一致
            const svgWidth = 1200;
            const svgHeight = 400;
            const margin = 80;

            // 计算绘图区域
            const plotWidth = svgWidth - 2 * margin;
            const plotHeight = svgHeight - 2 * margin;

            // 序列轴位置 - 与Left-Right图保持一致
            const terminalY = margin + 50;
            const extensionY = svgHeight - margin - 50;

            // 计算比例尺 - 根据flag使用不同的最大长度
            let maxLen, terminalScale, extensionScale, terminalAxisLength, extensionAxisLength;

            if (flag === 'right') {{
                // flag=right: 下方显示全长，上方显示种子长度
                const lowerAxisLen = lowerAxisEnd - lowerAxisStart;
                const upperAxisLen = upperAxisEnd - upperAxisStart;
                maxLen = Math.max(lowerAxisLen, upperAxisLen);
                terminalScale = plotWidth / maxLen;
                extensionScale = plotWidth / maxLen;
                terminalAxisLength = upperAxisLen * terminalScale;  // 上方轴长度
                extensionAxisLength = lowerAxisLen * extensionScale; // 下方轴长度
            }} else {{
                // flag=left: 上方显示全长，下方显示种子长度
                const upperAxisLen = upperAxisEnd - upperAxisStart;
                const lowerAxisLen = lowerAxisEnd - lowerAxisStart;
                maxLen = Math.max(upperAxisLen, lowerAxisLen);
                terminalScale = plotWidth / maxLen;
                extensionScale = plotWidth / maxLen;
                terminalAxisLength = lowerAxisLen * terminalScale;  // 下方轴长度
                extensionAxisLength = upperAxisLen * extensionScale; // 上方轴长度
            }}

            // 计算比对区域位置
            // 注意：对于flag=left
            // - terminalStart/End 是 Right序列上的比对区域，应该绘制在下方轴（extensionY）
            // - extensionStart/End 是 Left+Extension序列上的比对区域，应该绘制在上方轴（terminalY）
            // 对于flag=right
            // - terminalStart/End 是 Left序列上的比对区域，应该绘制在上方轴（terminalY）
            // - extensionStart/End 是 Extension+Right序列上的比对区域，应该绘制在下方轴（extensionY）

            let upperAlignX1, upperAlignX2, lowerAlignX1, lowerAlignX2;

            if (flag === 'right') {{
                // flag=right: 上方显示 Left 尾端的种子窗口 [upperAxisStart, upperAxisEnd]
                // 将比对区域裁剪并映射到该窗口（以 upperAxisStart 为零点）
                const terminalStartInWindow = Math.max(upperAxisStart, Math.min(terminalStart, upperAxisEnd));
                const terminalEndInWindow   = Math.max(upperAxisStart, Math.min(terminalEnd, upperAxisEnd));
                upperAlignX1 = margin + (terminalStartInWindow - upperAxisStart) * terminalScale;
                upperAlignX2 = margin + (terminalEndInWindow   - upperAxisStart) * terminalScale;

                // 下方比对区域基于完整序列
                lowerAlignX1 = margin + (extensionStart - lowerAxisStart) * extensionScale;
                lowerAlignX2 = margin + (extensionEnd - lowerAxisStart) * extensionScale;
            }} else {{
                // flag=left: 上方是Left+Extension完整序列，下方是Right种子序列
                // 上方比对区域基于完整序列
                upperAlignX1 = margin + (extensionStart - upperAxisStart) * extensionScale;
                upperAlignX2 = margin + (extensionEnd - upperAxisStart) * extensionScale;

                // 下方比对区域需要映射到种子序列范围内
                const terminalStartInSeed = Math.max(0, Math.min(terminalStart, rightSeedLen));
                const terminalEndInSeed = Math.max(0, Math.min(terminalEnd, rightSeedLen));
                lowerAlignX1 = margin + terminalStartInSeed * terminalScale;
                lowerAlignX2 = margin + terminalEndInSeed * terminalScale;
            }}

            // 设置最小可见宽度（至少2像素）
            const minWidth = 2;
            if (Math.abs(upperAlignX2 - upperAlignX1) < minWidth) {{
                const centerX = (upperAlignX1 + upperAlignX2) / 2;
                upperAlignX1 = centerX - minWidth / 2;
                upperAlignX2 = centerX + minWidth / 2;
            }}
            if (Math.abs(lowerAlignX2 - lowerAlignX1) < minWidth) {{
                const centerX = (lowerAlignX1 + lowerAlignX2) / 2;
                lowerAlignX1 = centerX - minWidth / 2;
                lowerAlignX2 = centerX + minWidth / 2;
            }}

            // 序列轴长度已在上面计算，这里删除重复声明

            // 颜色设置 - 与Left-Right图保持一致
            const alignmentColor = meetsStandard ? "#27ae60" : "#e74c3c";
            const connectionColor = meetsStandard ? "#27ae60" : "#e74c3c";
            const opacity = meetsStandard ? "0.8" : "0.6";

            return `
                <div style="margin: 20px 0; text-align: center;">
                    <h6 style="text-align: center; margin-bottom: 15px; color: #2c3e50;">${{t('alignment.synteny_title')}}</h6>
                    <div style="display: inline-block;">
                        <svg width="${{svgWidth}}" height="${{svgHeight}}" viewBox="0 0 ${{svgWidth}} ${{svgHeight}}" style="border: 1px solid #e9ecef; border-radius: 5px; background: white; max-width: 100%; height: auto;">
                        <!-- 背景 -->
                        <rect width="${{svgWidth}}" height="${{svgHeight}}" fill="#f8f9fa" stroke="#e9ecef"/>

                        <!-- 图例 - 与Left-Right图保持一致，上下布局 -->
                        <g class="svg-legend">
                            <rect x="${{svgWidth - 220}}" y="20" width="200" height="120" fill="white" stroke="#e9ecef" rx="5" fill-opacity="0.95"/>
                            <text x="${{svgWidth - 210}}" y="35" fill="#2c3e50" font-weight="bold" font-size="12">Legend</text>

                            <rect x="${{svgWidth - 205}}" y="45" width="16" height="8" fill="#27ae60" opacity="0.8"/>
                            <text x="${{svgWidth - 185}}" y="52" fill="#2c3e50" font-size="11">Qualified Alignment</text>

                            <rect x="${{svgWidth - 205}}" y="65" width="16" height="8" fill="#e74c3c" opacity="0.6"/>
                            <text x="${{svgWidth - 185}}" y="72" fill="#2c3e50" font-size="11">Unqualified Alignment</text>

                            <rect x="${{svgWidth - 205}}" y="85" width="16" height="8" fill="#3498db"/>
                            <text x="${{svgWidth - 185}}" y="92" fill="#2c3e50" font-size="11">LeftSeq</text>

                            <rect x="${{svgWidth - 205}}" y="105" width="16" height="8" fill="#9b59b6"/>
                            <text x="${{svgWidth - 185}}" y="112" fill="#2c3e50" font-size="11">RightSeq</text>
                        </g>

                        <!-- 上方序列轴 - 根据flag决定显示内容 -->
                        ${{flag === 'left' ? `
                            <!-- flag=left时：上方显示完整的Left Sequence + Extension -->
                            <!-- Left Sequence部分 -->
                            <line x1="${{margin + (originalSeqStart - upperAxisStart) * extensionScale}}" y1="${{terminalY}}" x2="${{margin + (originalSeqEnd - upperAxisStart) * extensionScale}}" y2="${{terminalY}}"
                                  stroke="#3498db" stroke-width="8" stroke-linecap="round"/>
                            <!-- 延伸部分 -->
                            <line x1="${{margin + (extensionPartStart - upperAxisStart) * extensionScale}}" y1="${{terminalY}}" x2="${{margin + (extensionPartEnd - upperAxisStart) * extensionScale}}" y2="${{terminalY}}"
                                  stroke="#e67e22" stroke-width="8" stroke-linecap="round"/>
                        ` : `
                            <!-- flag=right：上方只显示Left Sequence种子部分 -->
                            <line x1="${{margin}}" y1="${{terminalY}}" x2="${{margin + terminalAxisLength}}" y2="${{terminalY}}"
                                  stroke="#3498db" stroke-width="8" stroke-linecap="round"/>
                        `}}
                        <!-- 删除上方序列主标题 -->

                        <!-- 上方序列的分段标注 - 根据flag显示不同内容 -->
                        ${{flag === 'left' ? `
                            <!-- Left Sequence种子序列标注 -->
                            <text x="${{margin + (originalSeqStart + originalSeqEnd) * extensionScale / 2}}" y="${{terminalY - 35}}"
                                  fill="#3498db"
                                  font-size="14" text-anchor="middle"
                                  font-weight="bold">
                                LeftSeq
                            </text>

                            <!-- Extension标注 -->
                            <text x="${{margin + (extensionPartStart + extensionPartEnd) * extensionScale / 2}}" y="${{terminalY - 35}}"
                                  fill="#e67e22"
                                  font-size="14" text-anchor="middle"
                                  font-weight="bold">
                                ExtensionSeq
                            </text>
                        ` : `
                            <!-- flag=right新方案：上方只有Left Sequence，无需分段标注 -->
                        `}}
                        <text x="${{margin}}" y="${{terminalY + 25}}" fill="#7f8c8d" font-size="12">
                            ${{upperAxisStart.toLocaleString()}} bp
                        </text>
                        <text x="${{margin + (flag === 'left' ? extensionAxisLength : terminalAxisLength)}}" y="${{terminalY + 25}}" fill="#7f8c8d" font-size="12">
                            ${{upperAxisEnd.toLocaleString()}} bp
                        </text>

                        <!-- 下方序列轴 - 根据flag决定显示内容 -->
                        ${{flag === 'left' ? `
                            <!-- flag=left时：下方只显示Right Sequence种子部分 -->
                            <line x1="${{margin}}" y1="${{extensionY}}" x2="${{margin + terminalAxisLength}}" y2="${{extensionY}}"
                                  stroke="#9b59b6" stroke-width="8" stroke-linecap="round"/>
                        ` : `
                            <!-- flag=right：下方显示完整的Extension + Right Sequence -->
                            <!-- Extension部分 -->
                            <line x1="${{margin + (extensionPartStart - lowerAxisStart) * extensionScale}}" y1="${{extensionY}}" x2="${{margin + (extensionPartEnd - lowerAxisStart) * extensionScale}}" y2="${{extensionY}}"
                                  stroke="#e67e22" stroke-width="8" stroke-linecap="round"/>
                            <!-- Right Sequence部分 -->
                            <line x1="${{margin + (extensionPartEnd - lowerAxisStart) * extensionScale}}" y1="${{extensionY}}" x2="${{margin + (lowerAxisEnd - lowerAxisStart) * extensionScale}}" y2="${{extensionY}}"
                                  stroke="#9b59b6" stroke-width="8" stroke-linecap="round"/>
                        `}}

                        <!-- 下方序列标注 - 根据flag显示不同内容 -->
                        ${{flag === 'left' ? `
                            <!-- flag=left时：下方只有Right Sequence，无需额外标注 -->
                        ` : `
                            <!-- flag=right新方案：显示Extension和Right Sequence的标注 -->
                            <!-- Extension部分标注 - 橙色，在左侧 -->
                            <text x="${{margin + (extensionPartStart + extensionPartEnd) * extensionScale / 2}}" y="${{extensionY + 50}}"
                                  fill="#e67e22" font-size="14" text-anchor="middle"
                                  font-weight="bold">
                                ExtensionSeq
                            </text>

                            <!-- Right Sequence种子序列标注 - 紫色，在右侧 -->
                            <text x="${{margin + (originalSeqStart + originalSeqEnd) * extensionScale / 2}}" y="${{extensionY + 50}}"
                                  fill="#9b59b6"
                                  font-size="14" text-anchor="middle"
                                  font-weight="bold">
                                RightSeq
                            </text>
                        `}}



                        <!-- 删除下方序列主标题 -->

                        <!-- 长度标注 -->
                        <text x="${{margin}}" y="${{extensionY - 10}}" fill="#7f8c8d" font-size="12">
                            ${{flag === 'left' ? '0' : lowerAxisStart.toLocaleString()}} bp
                        </text>
                        <text x="${{margin + (flag === 'left' ? terminalAxisLength : extensionAxisLength)}}" y="${{extensionY - 10}}" fill="#7f8c8d" font-size="12">
                            ${{flag === 'left' ? lowerAxisEnd.toLocaleString() : lowerAxisEnd.toLocaleString()}} bp
                        </text>

                        <!-- 比对区域 -->
                        <g class="extension-alignment-1" data-alignment="1">
                            <!-- 上方序列比对区域 -->
                            <rect x="${{upperAlignX1}}" y="${{terminalY - 4}}"
                                  width="${{upperAlignX2 - upperAlignX1}}" height="8"
                                  fill="${{alignmentColor}}" stroke="#2c3e50" stroke-width="1" opacity="${{opacity}}"
                                  class="alignment-rect upper-rect"
                                  onmouseover="showExtensionTooltip(evt, 1)"
                                  onmouseout="hideExtensionTooltip()"
                                  onclick="selectExtensionAlignment(1)"
                                  style="cursor: pointer;"/>

                            <!-- 上方序列悬停区域 -->
                            <rect x="${{upperAlignX1 - 5}}" y="${{terminalY - 15}}"
                                  width="${{upperAlignX2 - upperAlignX1 + 10}}" height="30"
                                  fill="transparent" stroke="none"
                                  class="hover-area-upper"
                                  onmouseover="showExtensionTooltip(evt, 1)"
                                  onmouseout="hideExtensionTooltip()"
                                  onclick="selectExtensionAlignment(1)"
                                  style="cursor: pointer;"/>

                            <!-- 下方序列比对区域 -->
                            <rect x="${{lowerAlignX1}}" y="${{extensionY - 4}}"
                                  width="${{lowerAlignX2 - lowerAlignX1}}" height="8"
                                  fill="${{alignmentColor}}" stroke="#2c3e50" stroke-width="1" opacity="${{opacity}}"
                                  class="alignment-rect lower-rect"
                                  onmouseover="showExtensionTooltip(evt, 1)"
                                  onmouseout="hideExtensionTooltip()"
                                  onclick="selectExtensionAlignment(1)"
                                  style="cursor: pointer;"/>

                            <!-- 下方序列悬停区域 -->
                            <rect x="${{lowerAlignX1 - 5}}" y="${{extensionY - 15}}"
                                  width="${{lowerAlignX2 - lowerAlignX1 + 10}}" height="30"
                                  fill="transparent" stroke="none"
                                  class="hover-area-lower"
                                  onmouseover="showExtensionTooltip(evt, 1)"
                                  onmouseout="hideExtensionTooltip()"
                                  onclick="selectExtensionAlignment(1)"
                                  style="cursor: pointer;"/>

                            <!-- 连接区域 - 只保留半透明填充，无边界线 -->
                            <polygon points="${{upperAlignX1}},${{terminalY + 4}} ${{upperAlignX2}},${{terminalY + 4}} ${{lowerAlignX2}},${{extensionY - 4}} ${{lowerAlignX1}},${{extensionY - 4}}"
                                     fill="#4CAF50" opacity="0.3" stroke="none"
                                     class="connection-area"
                                     onmouseover="showExtensionTooltip(evt, 1)"
                                     onmouseout="hideExtensionTooltip()"
                                     onclick="selectExtensionAlignment(1)"
                                     style="cursor: pointer;"/>

                            <!-- 比对信息标签 - 修正显示位置 -->
                            <!-- 上方序列的比对区域标注 -->
                            <text x="${{(upperAlignX1 + upperAlignX2) / 2}}" y="${{terminalY - 15}}"
                                  fill="#2c3e50" font-size="10" text-anchor="middle" font-weight="bold"
                                  class="alignment-label"
                                  onmouseover="showExtensionTooltip(evt, 1)"
                                  onmouseout="hideExtensionTooltip()"
                                  onclick="selectExtensionAlignment(1)"
                                  style="cursor: pointer;">
                                ${{flag === 'right' ? terminalStart.toLocaleString() + ' - ' + terminalEnd.toLocaleString() : extensionStart.toLocaleString() + ' - ' + extensionEnd.toLocaleString()}}
                            </text>
                            <!-- 下方序列的比对区域标注 -->
                            <text x="${{(lowerAlignX1 + lowerAlignX2) / 2}}" y="${{extensionY + 30}}"
                                  fill="#2c3e50" font-size="10" text-anchor="middle" font-weight="bold"
                                  class="alignment-label"
                                  onmouseover="showExtensionTooltip(evt, 1)"
                                  onmouseout="hideExtensionTooltip()"
                                  onclick="selectExtensionAlignment(1)"
                                  style="cursor: pointer;">
                                ${{flag === 'right' ? extensionStart.toLocaleString() + ' - ' + extensionEnd.toLocaleString() : terminalStart.toLocaleString() + ' - ' + terminalEnd.toLocaleString()}}
                            </text>
                        </g>


                        </svg>
                    </div>

                    <div style="text-align: center; margin-top: 10px; font-size: 0.9em; color: #7f8c8d;">
                        <p>${{t('alignment.synteny_chart_summary.alignment_length').replace('{{length}}', (alignmentInfo.terminal_align_len || 0).toLocaleString())}} |
                           ${{t('alignment.synteny_chart_summary.gap_closure_standard').replace('{{status}}', meetsStandard ? t('alignment.synteny_chart_summary.meets_standard') : t('alignment.synteny_chart_summary.not_meets_standard'))}}</p>
                    </div>
                </div>
            `;
        }}

        // 生成分析结果部分
        function generateAnalysisResultSection(roundData) {{
            const alignmentInfo = roundData.extension_alignment;
            const nextAction = roundData.next_action;

            if (!alignmentInfo && !nextAction) {{
                return '';
            }}

            // 确定Gap闭合状态
            const canCloseGap = alignmentInfo ? alignmentInfo.can_close_gap : false;
            const meetsStandard = alignmentInfo ? alignmentInfo.meets_gap_closure_standard : false;

            // 生成分析结果文本
            let analysisText = '';
            if (alignmentInfo) {{
                const alignLen = alignmentInfo.terminal_align_len || 0;
                const identity = alignmentInfo.identity || 0;

                if (canCloseGap) {{
                    analysisText = t('analysis.gap_closed_success')
                        .replace('{{length}}', alignLen.toLocaleString())
                        .replace('{{identity}}', identity.toFixed(2));
                }} else if (meetsStandard) {{
                    analysisText = t('analysis.meets_standard')
                        .replace('{{length}}', alignLen.toLocaleString());
                }} else if (alignLen > 0) {{
                    analysisText = t('analysis.below_standard')
                        .replace('{{length}}', alignLen.toLocaleString())
                        .replace('{{identity}}', identity.toFixed(2));
                }} else {{
                    analysisText = t('analysis.no_alignment');
                }}
            }} else {{
                analysisText = t('analysis.no_result');
            }}

            // 根据nextAction调整下一步操作描述
            if (nextAction) {{
                const actionKey = `analysis.next_actions.${{nextAction.action}}`;
                const actionText = t(actionKey);
                if (currentLanguage === 'zh') {{
                    analysisText = analysisText.replace(/下一步操作：[^。]*/, actionText);
                }} else {{
                    analysisText = analysisText.replace(/Next action: [^.]*/, actionText);
                }}
            }}

            return `
                <div class="analysis-result-section" style="margin-top: 25px; padding: 20px; background: white; border-radius: 8px; border-left: 3px solid #27ae60;">
                    <p style="margin: 0; color: #2c3e50; line-height: 1.6;">
                        <strong>${{t('analysis.result_title')}}</strong> ${{analysisText}}
                    </p>
                </div>
            `;
        }}

        // 更新当前轮次显示
        function updateCurrentRoundDisplay() {{
            const displayEl = document.getElementById('currentRoundDisplay');
            if (displayEl) {{
                if (currentRound === 0) {{
                    displayEl.textContent = t('timeline.initial');
                }} else {{
                    displayEl.textContent = t('timeline.round', {{round: currentRound, total: totalRounds}});
                }}
            }}
        }}



        // 比对表格功能
        let selectedAlignment = 1; // 默认选中第一个

        // 比对数据 - 直接从Python传递
        const alignmentTableData = {alignment_data_js};

        function initializeStaticAlignmentTable() {{
            // 为主表格添加交互功能（静态表格版本）
            const mainTableRows = document.querySelectorAll('.alignment-table:not(.extension-alignment-table) tbody tr');

            mainTableRows.forEach((row, index) => {{
                const alignmentIndex = index + 1;
                row.id = `main-alignment-row-${{alignmentIndex}}`;
                row.style.cursor = 'pointer';

                // 添加点击事件处理
                row.addEventListener('click', function(e) {{
                    e.preventDefault();
                    e.stopPropagation();
                    selectAlignment(alignmentIndex);
                }});

                // 添加悬停效果
                row.addEventListener('mouseenter', function() {{
                    if (selectedAlignment !== alignmentIndex) {{
                        row.classList.add('hover');
                        highlightAlignment(alignmentIndex);
                    }}
                }});

                row.addEventListener('mouseleave', function() {{
                    row.classList.remove('hover');
                    if (selectedAlignment !== alignmentIndex) {{
                        clearHighlight();
                    }}
                }});
            }});

            // 为延伸序列表格添加交互功能
            const extensionTableRows = document.querySelectorAll('.extension-alignment-table tbody tr');
            extensionTableRows.forEach((row, index) => {{
                const alignmentIndex = index + 1;
                row.id = `extension-alignment-row-${{alignmentIndex}}`;
                row.style.cursor = 'pointer';

                // 添加点击事件处理
                row.addEventListener('click', function(e) {{
                    e.preventDefault();
                    e.stopPropagation();
                    selectExtensionAlignment(alignmentIndex);
                }});

                // 添加悬停效果
                row.addEventListener('mouseenter', function() {{
                    // 只有在未选中状态下才响应悬停
                    if (selectedAlignment !== alignmentIndex) {{
                        row.classList.add('hover');
                        highlightExtensionAlignment(alignmentIndex);
                    }}
                }});

                row.addEventListener('mouseleave', function() {{
                    // 移除悬停状态
                    row.classList.remove('hover');
                    // 如果当前行不是选中行，恢复到选中状态的高亮
                    if (selectedAlignment !== alignmentIndex) {{
                        highlightExtensionAlignment(selectedAlignment);
                    }}
                }});
            }});
        }}

        function initializeExtensionAlignmentTable() {{
            // 为延伸序列表格添加交互功能
            const extensionTableRows = document.querySelectorAll('.extension-alignment-table tbody tr');

            extensionTableRows.forEach((row, index) => {{
                const alignmentIndex = index + 1;
                row.id = `extension-alignment-row-${{alignmentIndex}}`;
                row.style.cursor = 'pointer';

                // 添加点击事件处理
                row.addEventListener('click', function(e) {{
                    e.preventDefault();
                    e.stopPropagation();
                    selectExtensionAlignment(alignmentIndex);
                }});

                // 添加悬停效果
                row.addEventListener('mouseenter', function() {{
                    if (selectedExtensionAlignment !== alignmentIndex) {{
                        row.classList.add('hover');
                        highlightExtensionAlignment(alignmentIndex);
                    }}
                }});

                row.addEventListener('mouseleave', function() {{
                    row.classList.remove('hover');
                    if (selectedExtensionAlignment !== alignmentIndex) {{
                        highlightExtensionAlignment(selectedExtensionAlignment);
                    }}
                }});
            }});

            // 默认选中第一条
            if (extensionTableRows.length > 0) {{
                selectExtensionAlignment(1);
            }}
        }}

        function selectAlignment(alignmentIndex) {{
            // 更新全局选中状态
            selectedAlignment = alignmentIndex;

            // 移除之前的选中状态
            document.querySelectorAll('.alignment-table tbody tr').forEach(row => {{
                row.classList.remove('selected');
            }});

            // 添加新的选中状态到主表格行
            const selectedRow = document.getElementById(`main-alignment-row-${{alignmentIndex}}`);
            if (selectedRow) {{
                selectedRow.classList.add('selected');
            }}

            // 添加新的选中状态到延伸序列表格行
            const extensionSelectedRow = document.getElementById(`extension-alignment-row-${{alignmentIndex}}`);
            if (extensionSelectedRow) {{
                extensionSelectedRow.classList.add('selected');

                // 滚动到选中的行（如果表格有滚动条）
                selectedRow.scrollIntoView({{
                    behavior: 'smooth',
                    block: 'nearest'
                }});
            }}

            // 高亮对应的图形元素
            highlightAlignment(alignmentIndex);
        }}

        function highlightAlignment(alignmentIndex) {{
            // 重置所有元素的样式
            document.querySelectorAll('.alignment-rect, .connection-line, .alignment-label').forEach(el => {{
                el.style.strokeWidth = '';
                el.style.opacity = '';
                el.style.filter = '';
                el.style.transform = '';
            }});

            // 将所有非选中元素设为半透明
            document.querySelectorAll('[class*="alignment-"]').forEach(group => {{
                if (!group.classList.contains(`alignment-${{alignmentIndex}}`)) {{
                    const elements = group.querySelectorAll('.alignment-rect, .connection-line, .alignment-label');
                    elements.forEach(el => {{
                        el.style.opacity = '0.3';
                    }});
                }}
            }});

            // 高亮选中的元素
            const alignmentGroup = document.querySelector(`.alignment-${{alignmentIndex}}`);
            if (alignmentGroup) {{
                const rects = alignmentGroup.querySelectorAll('.alignment-rect');
                const lines = alignmentGroup.querySelectorAll('.connection-line');
                const labels = alignmentGroup.querySelectorAll('.alignment-label');

                rects.forEach(rect => {{
                    rect.style.strokeWidth = '4px';
                    rect.style.opacity = '1';
                    rect.style.filter = 'drop-shadow(0 0 6px rgba(52, 152, 219, 0.8))';
                }});

                lines.forEach(line => {{
                    line.style.strokeWidth = '4px';
                    line.style.opacity = '1';
                    line.style.filter = 'drop-shadow(0 0 4px rgba(52, 152, 219, 0.6))';
                }});

                labels.forEach(label => {{
                    label.style.opacity = '1';
                    label.style.fontWeight = 'bold';
                    label.style.filter = 'drop-shadow(0 0 2px rgba(255, 255, 255, 0.8))';
                }});
            }}
        }}

        function showTooltip(evt, alignmentIndex) {{
            // 阻止事件冒泡
            if (evt) {{
                evt.stopPropagation();
            }}

            // 选择对应的比对记录
            selectAlignment(alignmentIndex);
        }}

        // 延伸序列交互函数
        function showExtensionTooltip(evt, alignmentIndex) {{
            // 阻止事件冒泡
            if (evt) {{
                evt.stopPropagation();
            }}

            // 选择对应的比对记录
            selectExtensionAlignment(alignmentIndex);
        }}

        function hideExtensionTooltip() {{
            // 保持选中状态，不做额外操作
        }}

        function selectExtensionAlignment(alignmentIndex) {{
            // 更新全局选中状态
            selectedExtensionAlignment = alignmentIndex;

            // 移除之前的选中状态
            document.querySelectorAll('.extension-alignment-table tbody tr').forEach(row => {{
                row.classList.remove('selected');
            }});

            // 添加新的选中状态到延伸序列表格行
            const extensionSelectedRow = document.getElementById(`extension-alignment-row-${{alignmentIndex}}`);
            if (extensionSelectedRow) {{
                extensionSelectedRow.classList.add('selected');

                // 滚动到选中行
                extensionSelectedRow.scrollIntoView({{
                    behavior: 'smooth',
                    block: 'nearest'
                }});
            }}

            // 高亮对应的图形元素
            highlightExtensionAlignment(alignmentIndex);
        }}

        function highlightExtensionAlignment(alignmentIndex) {{
            // 重置所有元素的样式
            document.querySelectorAll('.alignment-rect, .connection-line').forEach(el => {{
                el.style.strokeWidth = '';
                el.style.opacity = '';
                el.style.filter = '';
                el.style.transform = '';
            }});

            // 高亮选中的元素
            const alignmentGroup = document.querySelector(`.extension-alignment-${{alignmentIndex}}`);
            if (alignmentGroup) {{
                const rects = alignmentGroup.querySelectorAll('.alignment-rect');
                const lines = alignmentGroup.querySelectorAll('.connection-line');

                rects.forEach(rect => {{
                    rect.style.strokeWidth = '3px';
                    rect.style.opacity = '1';
                    rect.style.filter = 'drop-shadow(0 0 6px rgba(0,0,0,0.3))';
                }});

                lines.forEach(line => {{
                    line.style.strokeWidth = '4px';
                    line.style.opacity = '1';
                    line.style.filter = 'drop-shadow(0 0 4px rgba(0,0,0,0.2))';
                }});
            }}
        }}

        function clearExtensionHighlight() {{
            document.querySelectorAll('.alignment-rect, .connection-line').forEach(el => {{
                el.style.strokeWidth = '';
                el.style.opacity = '';
                el.style.filter = '';
                el.style.transform = '';
            }});
        }}

        function hideTooltip() {{
            // 不隐藏表格，保持显示
            // 可以在这里添加其他清理逻辑
        }}

        // 添加键盘导航支持
        document.addEventListener('keydown', function(e) {{
            if (e.target.closest('.tooltip-table')) {{
                const currentIndex = selectedAlignment;
                const maxIndex = alignmentTableData.length;

                switch(e.key) {{
                    case 'ArrowUp':
                        e.preventDefault();
                        if (currentIndex > 1) {{
                            selectAlignment(currentIndex - 1);
                        }}
                        break;
                    case 'ArrowDown':
                        e.preventDefault();
                        if (currentIndex < maxIndex) {{
                            selectAlignment(currentIndex + 1);
                        }}
                        break;
                }}
            }}
        }});

        // 键盘快捷键 - 简化版
        document.addEventListener('keydown', function(e) {{
            switch(e.key) {{
                case 'ArrowLeft':
                    if (currentRound > 0) {{
                        goToRound(currentRound - 1);
                    }}
                    break;
                case 'ArrowRight':
                    if (currentRound < totalRounds) {{
                        goToRound(currentRound + 1);
                    }}
                    break;
                case 'Home':
                    goToRound(0);
                    break;
                case 'End':
                    goToRound(totalRounds);
                    break;
            }}
        }});
        """


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='DEGAP v2 Gapfiller 可视化工具')
    parser.add_argument('result_dir', help='结果文件夹路径')
    parser.add_argument('-o', '--output', help='输出目录', default='./visualization_output')
    parser.add_argument('--MaximumExtensionLength', type=int, help='最大延伸长度限制')
    parser.add_argument('--flag', type=str, choices=['left', 'right'], default='left',
                       help='延伸方向：left表示从左序列延伸，right表示从右序列延伸')

    args = parser.parse_args()
    
    # 检查输入文件
    result_dir = Path(args.result_dir)
    log_file = result_dir / 'process.log'
    summary_file = result_dir / 'process.summary'
    
    if not log_file.exists():
        print(f"错误: 找不到日志文件 {log_file}")
        return
    
    # 解析日志
    print("正在解析日志文件...")
    parser = GapfillerLogParser(log_file, summary_file if summary_file.exists() else None, result_dir)
    data = parser.parse_log()

    # 生成HTML报告
    print("正在生成HTML报告...")
    generator = HTMLReportGenerator(data, args.output, result_dir,
                                  max_extension_length=args.MaximumExtensionLength,
                                  extension_flag=args.flag)
    html_file = generator.generate_report()
    
    print(f"可视化报告生成完成!")
    print(f"请在浏览器中打开: {html_file}")


if __name__ == '__main__':
    main()
