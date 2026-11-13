#!/usr/bin/env python3
"""
CtgLinkerCheck.py - 检查和整理 CtgLinker 组装结果

功能：
1. 直接从 project/DGxx/DGxx-Left|Right/process.log 解析每个 DG 的延伸结果
2. 识别 scaffold 锚点（双端都失败，或只有一个任务且失败）
3. 正确追溯每个 Scaffold 包含的原始 Contigs
4. 输出结构化数据供可视化脚本使用

输出文件：
- {out}/ctglinker_check.json: 结构化的 Scaffold 信息
"""

import os
import sys
import re
import json
from collections import OrderedDict
from pathlib import Path


class CtgLinkerCheck:
    """CtgLinker 结果检查器"""
    
    def __init__(self, output_dir):
        """
        初始化检查器
        
        Args:
            output_dir: CtgLinker 输出目录
        """
        self.output_dir = Path(output_dir)
        self.project_dir = self.output_dir / "project"
        self.scaffold_fa = self.output_dir / "DG.scaffold.fa"
        self.unplaced_file = self.output_dir / "unplaced.txt"
        self.input_log = self.output_dir / "Genome.inputCtg.log"
        self.scaffold_log = self.output_dir / "DG.scaffold.log"
        
        # 解析结果
        self.scaffolds = OrderedDict()  # scaffold_id -> {length, dg_id}
        self.dg_list = []  # 按顺序的 DG 列表
        self.dg_info = {}  # dg_id -> {left: {...}, right: {...}, seed_contig, contigs, absorbed_dg}
        self.valid_scaffolds = []
        self.invalid_scaffolds = []
        self.unplaced = []
        self.input_stats = {}
        self.output_stats = {}
    
    def parse_scaffold_fa(self):
        """解析 DG.scaffold.fa，获取 scaffold 信息"""
        if not self.scaffold_fa.exists():
            return
        
        current_id = None
        current_dg = None
        current_len = 0
        
        with open(self.scaffold_fa, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('>'):
                    if current_id:
                        self.scaffolds[current_id] = {
                            'length': current_len,
                            'dg_id': current_dg
                        }
                    parts = line[1:].split('\t')
                    current_id = parts[0]
                    current_dg = parts[1] if len(parts) > 1 else None
                    current_len = 0
                else:
                    current_len += len(line)
            
            if current_id:
                self.scaffolds[current_id] = {
                    'length': current_len,
                    'dg_id': current_dg
                }

    def parse_dg_directories(self):
        """
        直接从 project/DGxx/ 目录解析每个 DG 的信息
        
        遍历 project 目录下的所有 DG 目录，解析：
        1. DGxx.input.log: 获取 seed contig
        2. DGxx-Left/process.log: 获取左端延伸结果
        3. DGxx-Right/process.log: 获取右端延伸结果
        """
        if not self.project_dir.exists():
            print(f"  Warning: Project directory not found: {self.project_dir}")
            return
        
        # 获取所有 DG 目录并按数字排序
        dg_dirs = []
        for d in self.project_dir.iterdir():
            if d.is_dir() and d.name.startswith('DG'):
                match = re.match(r'DG(\d+)', d.name)
                if match:
                    dg_dirs.append((int(match.group(1)), d.name))
        
        dg_dirs.sort(key=lambda x: x[0])
        self.dg_list = [d[1] for d in dg_dirs]
        
        print(f"  Found {len(self.dg_list)} DG directories")
        
        # 解析每个 DG
        for dg_id in self.dg_list:
            dg_dir = self.project_dir / dg_id
            info = {
                'seed_contig': None,
                'absorbed_dg': None,  # 如果 seed 是另一个 DG
                'contigs': [],
                'left': None,
                'right': None
            }
            
            # 1. 解析 input.log 获取 seed
            input_log = dg_dir / f"{dg_id}.input.log"
            if input_log.exists():
                seed_info = self._parse_input_log(input_log)
                info['seed_contig'] = seed_info.get('seed_contig')
                info['absorbed_dg'] = seed_info.get('absorbed_dg')
            
            # 2. 解析 Left 方向
            left_dir = dg_dir / f"{dg_id}-Left"
            if left_dir.exists():
                info['left'] = self._parse_direction_log(left_dir, dg_id, 'Left')
            
            # 3. 解析 Right 方向
            right_dir = dg_dir / f"{dg_id}-Right"
            if right_dir.exists():
                info['right'] = self._parse_direction_log(right_dir, dg_id, 'Right')
            
            # 收集所有 contigs
            if info['seed_contig'] and info['seed_contig'].startswith('Contig'):
                info['contigs'].append(info['seed_contig'])
            
            if info['left'] and info['left'].get('linked_contig'):
                linked = info['left']['linked_contig']
                if linked.startswith('Contig') and linked not in info['contigs']:
                    info['contigs'].append(linked)
            
            if info['right'] and info['right'].get('linked_contig'):
                linked = info['right']['linked_contig']
                if linked.startswith('Contig') and linked not in info['contigs']:
                    info['contigs'].append(linked)
            
            self.dg_info[dg_id] = info
            
            # 打印调试信息
            left_status = info['left']['status'] if info['left'] else 'N/A'
            right_status = info['right']['status'] if info['right'] else 'N/A'
            print(f"    {dg_id}: seed={info['seed_contig'] or info['absorbed_dg']}, "
                  f"left={left_status}, right={right_status}, contigs={info['contigs']}")

    def _parse_input_log(self, input_log):
        """解析 DGxx.input.log 获取 seed 信息"""
        result = {'seed_contig': None, 'absorbed_dg': None}
        
        try:
            with open(input_log, 'r') as f:
                for line in f:
                    if line.startswith('roundInputSeqID'):
                        parts = line.strip().split('\t')
                        if len(parts) >= 2:
                            seed_id = parts[1]
                            if seed_id.startswith('Contig'):
                                result['seed_contig'] = seed_id
                            elif seed_id.startswith('DG'):
                                result['absorbed_dg'] = seed_id
                            else:
                                result['seed_contig'] = seed_id
                        break
        except Exception as e:
            print(f"    Warning: Error parsing {input_log}: {e}")
        
        return result

    def _parse_direction_log(self, direction_dir, dg_id, direction):
        """
        解析 DGxx-Left 或 DGxx-Right 目录的 process.log
        
        逻辑：
        1. 首先检查延伸阶段是否成功（Linked ctg:）
        2. 如果延伸成功，使用延伸结果
        3. 如果延伸失败，再检查是否有 direct connection 可用
        
        Returns:
            dict: {
                'status': 'success' | 'failed' | 'not_run',
                'linked_contig': str or None,  # 连接到的 contig
                'linked_dg': str or None,  # 连接到的 DG
                'is_direct': bool,  # 是否使用了 direct connection
                'gap_length': int or None
            }
        """
        result = {
            'status': 'not_run',
            'linked_contig': None,
            'linked_dg': None,
            'is_direct': False,
            'gap_length': None
        }
        
        process_log = direction_dir / "process.log"
        if not process_log.exists():
            return result
        
        # 保存 direct connection 信息（备用）
        direct_info = {
            'has_direct': False,
            'linked_contig': None,
            'linked_dg': None,
            'gap_length': None
        }
        
        try:
            with open(process_log, 'r') as f:
                content = f.read()
            
            # 1. 先解析 direct connection 信息（备用）
            direct_match = re.search(r'Connected edge:\s*(\S+)', content)
            if direct_match:
                connected_edge = direct_match.group(1)
                direct_info['has_direct'] = True
                
                # 解析连接的 contig/DG
                if '-edge-' in connected_edge:
                    parts = connected_edge.split('-edge-')
                    target_id = parts[0]
                    if target_id.startswith('Contig'):
                        direct_info['linked_contig'] = target_id
                    elif target_id.startswith('DG'):
                        direct_info['linked_dg'] = target_id
                
                # 解析 direct connection 的 GAP Length（在 Direct Connection Check 块中）
                # 格式: GAP Length: -11000
                direct_gap_match = re.search(r'Direct Connection Check.*?GAP Length:\s*([-\d]+)', content, re.DOTALL)
                if direct_gap_match:
                    direct_info['gap_length'] = int(direct_gap_match.group(1))
            
            # 2. 检查延伸阶段是否成功
            extension_success = False
            
            if 'Linked ctg:' in content:
                # 延伸阶段成功连接
                extension_success = True
                result['status'] = 'success'
                result['is_direct'] = False
                
                # 解析连接的目标
                linked_match = re.search(r'Linked ctg:\s*(\S+)', content)
                if linked_match:
                    linked_edge = linked_match.group(1)
                    if '-edge-' in linked_edge:
                        parts = linked_edge.split('-edge-')
                        target_id = parts[0]
                        if target_id.startswith('Contig'):
                            result['linked_contig'] = target_id
                        elif target_id.startswith('DG'):
                            result['linked_dg'] = target_id
                
                # 解析 GAP Length（延伸阶段，取最后一个）
                gap_matches = re.findall(r'GAP Length:\s*([-\d]+)', content)
                if gap_matches:
                    result['gap_length'] = int(gap_matches[-1])
            
            # 3. 如果延伸失败，检查是否可以使用 direct connection
            if not extension_success:
                # 判断延伸是否失败
                extension_failed = ('noExtension' in content or 
                                   'No Extension' in content or
                                   'reachMaximum' in content or 
                                   'Reach the maximum' in content or
                                   'GAP still not closed' in content)
                
                if extension_failed and direct_info['has_direct']:
                    # 延伸失败但有 direct connection，使用 direct connection
                    result['status'] = 'success'
                    result['is_direct'] = True
                    result['linked_contig'] = direct_info['linked_contig']
                    result['linked_dg'] = direct_info['linked_dg']
                    result['gap_length'] = direct_info['gap_length']
                else:
                    # 延伸失败且没有 direct connection
                    result['status'] = 'failed'
                
        except Exception as e:
            print(f"    Warning: Error parsing {process_log}: {e}")
        
        return result

    def get_all_contigs_for_dg(self, dg_id, visited=None):
        """递归获取一个 DG 包含的所有原始 Contigs"""
        if visited is None:
            visited = set()
        
        if dg_id in visited:
            return []
        visited.add(dg_id)
        
        if dg_id not in self.dg_info:
            return []
        
        info = self.dg_info[dg_id]
        all_contigs = list(info.get('contigs', []))
        
        # 如果 seed 是另一个 DG，递归获取其 contigs
        absorbed_dg = info.get('absorbed_dg')
        if absorbed_dg:
            sub_contigs = self.get_all_contigs_for_dg(absorbed_dg, visited)
            for c in sub_contigs:
                if c not in all_contigs:
                    all_contigs.append(c)
        
        return all_contigs
    
    def get_all_absorbed_dgs(self, dg_id, visited=None):
        """递归获取一个 DG 吸收的所有 DG"""
        if visited is None:
            visited = set()
        
        if dg_id in visited:
            return []
        visited.add(dg_id)
        
        if dg_id not in self.dg_info:
            return []
        
        info = self.dg_info[dg_id]
        all_absorbed = []
        
        # 如果 seed 是另一个 DG
        absorbed_dg = info.get('absorbed_dg')
        if absorbed_dg:
            all_absorbed.append(absorbed_dg)
            sub_absorbed = self.get_all_absorbed_dgs(absorbed_dg, visited.copy())
            for d in sub_absorbed:
                if d not in all_absorbed:
                    all_absorbed.append(d)
        
        return all_absorbed
    
    def parse_unplaced(self):
        """解析未放置的 contigs"""
        if not self.unplaced_file.exists():
            return
        
        with open(self.unplaced_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    self.unplaced.append(line.split('\t')[0].split()[0])
    
    def parse_stats_log(self, log_file):
        """解析 N50 统计日志"""
        stats = {}
        if not log_file.exists():
            return stats
        
        with open(log_file, 'r') as f:
            for line in f:
                if ':' in line or '\t' in line:
                    parts = re.split(r'[:\t]+', line.strip())
                    if len(parts) >= 2:
                        key = parts[0].strip().lower()
                        val = parts[1].strip()
                        try:
                            stats[key] = int(val)
                        except ValueError:
                            stats[key] = val
        return stats
    
    def analyze_scaffolds(self):
        """
        分析 Scaffold 有效性
        
        新逻辑：从 DG1 开始遍历，找到 scaffold 锚点：
        - 双端都失败（left=failed, right=failed 或 N/A）
        - 只有一个方向且失败
        
        一个锚点代表一个 scaffold 的终点，追溯包含的所有 DG 和 contigs
        """
        print("\n  Analyzing scaffolds from DG sequence...")
        
        # 从 DG.scaffold.fa 获取 scaffold 信息
        scaffold_by_dg = {}
        for scaffold_id, info in self.scaffolds.items():
            dg_id = info['dg_id']
            if dg_id:
                scaffold_by_dg[dg_id] = {
                    'scaffold_id': scaffold_id,
                    'length': info['length']
                }
        
        # 遍历 DG 列表，识别 scaffold 锚点
        processed_dgs = set()
        
        for dg_id in self.dg_list:
            if dg_id in processed_dgs:
                continue
            
            info = self.dg_info.get(dg_id, {})
            left = info.get('left')
            right = info.get('right')
            
            # 判断是否为锚点
            left_failed = left is None or left.get('status') == 'failed'
            right_failed = right is None or right.get('status') == 'failed'
            
            is_anchor = left_failed and right_failed
            
            if is_anchor:
                # 这是一个 scaffold 的锚点
                # 追溯这个 scaffold 包含的所有 DG 和 contigs
                scaffold_dgs = [dg_id]
                gap_fills = []
                
                # ✨ 修复：先收集所有 DG，然后按正确顺序构建 contigs 列表
                # 追溯所有被吸收的 DG
                absorbed_dg = info.get('absorbed_dg')
                while absorbed_dg and absorbed_dg not in processed_dgs:
                    scaffold_dgs.append(absorbed_dg)
                    absorbed_info = self.dg_info.get(absorbed_dg, {})
                    absorbed_dg = absorbed_info.get('absorbed_dg')
                
                # scaffold_dgs 现在是 [DG3, DG2, DG1]（从外到内）
                # 反转得到 [DG1, DG2, DG3]（从内到外，即组装顺序）
                scaffold_dgs_ordered = list(reversed(scaffold_dgs))
                
                # 找到第一个原始 DG（seed 是 Contig 的 DG）
                first_dg = None
                original_seed = None
                for dg in scaffold_dgs_ordered:
                    dg_info_temp = self.dg_info.get(dg, {})
                    seed = dg_info_temp.get('seed_contig')
                    if seed and seed.startswith('Contig'):
                        first_dg = dg
                        original_seed = seed
                        break
                
                # 按组装顺序构建 contigs 列表
                # 从 first_dg 的 seed 开始，按照每个 DG 的 left/right 方向扩展
                ordered_contigs = []
                if original_seed:
                    ordered_contigs.append(original_seed)
                
                # 按组装顺序遍历 DG，收集 gap_fills 和 linked_contigs
                for dg in scaffold_dgs_ordered:
                    dg_info_temp = self.dg_info.get(dg, {})
                    
                    # 收集成功的 gap_fills
                    for direction in ['left', 'right']:
                        dir_info = dg_info_temp.get(direction)
                        if dir_info and dir_info.get('status') == 'success':
                            linked_contig = dir_info.get('linked_contig')
                            
                            gap_fills.append({
                                'dg_id': dg,
                                'direction': direction.capitalize(),
                                'linked_contig': linked_contig,
                                'linked_dg': dir_info.get('linked_dg'),
                                'is_direct': dir_info.get('is_direct', False),
                                'report_path': f"project/{dg}/{dg}-{direction.capitalize()}"
                            })
                            
                            # 按方向添加 linked_contig 到有序列表
                            # Left 方向：contig 添加到列表开头（在 seed 左边）
                            # Right 方向：contig 添加到列表末尾（在 seed 右边）
                            if linked_contig and linked_contig.startswith('Contig') and linked_contig not in ordered_contigs:
                                if direction == 'left':
                                    ordered_contigs.insert(0, linked_contig)
                                else:  # right
                                    ordered_contigs.append(linked_contig)
                
                # 使用有序的 contigs 列表
                all_contigs = ordered_contigs
                
                # 恢复 scaffold_dgs 为原始顺序（从外到内）用于后续处理
                scaffold_dgs = list(reversed(scaffold_dgs_ordered))
                
                # 标记所有 DG 为已处理
                for d in scaffold_dgs:
                    processed_dgs.add(d)
                
                # 获取 scaffold 信息
                scaffold_info = scaffold_by_dg.get(dg_id, {})
                scaffold_id = scaffold_info.get('scaffold_id', f'Scaffold_{dg_id}')
                scaffold_length = scaffold_info.get('length', 0)
                
                self.valid_scaffolds.append({
                    'id': scaffold_id,
                    'length': scaffold_length,
                    'dg_id': dg_id,
                    'seed_contig': original_seed,  # ✨ 新增：第一个 DG 的 seed contig
                    'contigs': all_contigs,
                    'gap_fills': gap_fills,
                    'absorbed_dgs': scaffold_dgs[1:] if len(scaffold_dgs) > 1 else []
                })
                
                print(f"    Scaffold {scaffold_id}: DGs={scaffold_dgs}, seed={original_seed}, contigs={all_contigs}")
    
    def run(self):
        """执行检查"""
        print("[CtgLinkerCheck] Parsing scaffold sequences...")
        self.parse_scaffold_fa()
        
        print("[CtgLinkerCheck] Parsing DG directories...")
        self.parse_dg_directories()
        
        print("[CtgLinkerCheck] Parsing unplaced contigs...")
        self.parse_unplaced()
        
        print("[CtgLinkerCheck] Parsing statistics...")
        self.input_stats = self.parse_stats_log(self.input_log)
        self.output_stats = self.parse_stats_log(self.scaffold_log)
        
        print("[CtgLinkerCheck] Analyzing scaffold validity...")
        self.analyze_scaffolds()
        
        # 保存结果
        result = self.get_result()
        output_file = self.output_dir / "ctglinker_check.json"
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"[CtgLinkerCheck] Results saved to: {output_file}")
        
        # 打印摘要
        self.print_summary()
        
        return result
    
    def get_result(self):
        """获取结构化结果"""
        all_used_contigs = set()
        for scaffold in self.valid_scaffolds:
            all_used_contigs.update(scaffold['contigs'])
        
        return {
            'valid_scaffolds': self.valid_scaffolds,
            'invalid_scaffolds': self.invalid_scaffolds,
            'unplaced_contigs': self.unplaced,
            'input_stats': self.input_stats,
            'output_stats': self.output_stats,
            'summary': {
                'valid_scaffold_count': len(self.valid_scaffolds),
                'invalid_scaffold_count': len(self.invalid_scaffolds),
                'used_contig_count': len(all_used_contigs),
                'unplaced_contig_count': len(self.unplaced),
                'total_valid_length': sum(s['length'] for s in self.valid_scaffolds)
            }
        }
    
    def print_summary(self):
        """打印摘要"""
        print("\n" + "=" * 60)
        print("CtgLinker Check Summary")
        print("=" * 60)
        
        print(f"\n  Valid Scaffolds: {len(self.valid_scaffolds)}")
        for s in self.valid_scaffolds:
            contigs_str = ', '.join(s['contigs']) if s['contigs'] else '-'
            print(f"    {s['id']}: {s['length']:,} bp ({s['dg_id']}) -> {contigs_str}")
        
        if self.invalid_scaffolds:
            print(f"\n  Invalid Scaffolds: {len(self.invalid_scaffolds)}")
            for s in self.invalid_scaffolds:
                print(f"    {s['id']}: {s['length']:,} bp ({s['dg_id']}) - {s['reason']}")
        
        if self.unplaced:
            print(f"\n  Unplaced Contigs: {len(self.unplaced)}")
            for c in self.unplaced:
                print(f"    {c}")
        
        all_used = set()
        for s in self.valid_scaffolds:
            all_used.update(s['contigs'])
        
        total_len = sum(s['length'] for s in self.valid_scaffolds)
        print(f"\n  Total Valid Length: {total_len:,} bp")
        print(f"  Used Contigs: {len(all_used)}")
        print("=" * 60 + "\n")


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Check CtgLinker assembly results')
    parser.add_argument('output_dir', help='CtgLinker output directory')
    
    args = parser.parse_args()
    
    checker = CtgLinkerCheck(args.output_dir)
    result = checker.run()
    
    return result


if __name__ == "__main__":
    main()
