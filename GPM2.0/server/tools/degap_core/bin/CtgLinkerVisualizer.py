#!/usr/bin/env python3
"""
CtgLinkerVisualizer.py - Visualization module for CtgLinker mode.

Generates a summary report for the iterative contig linking process.
Integrates with GapfillerVisualizer to provide detailed views for each linking step.
"""

import os
import re
import sys
import json
from pathlib import Path
from datetime import datetime

# Import GapfillerVisualizer
try:
    import GapfillerVisualizer
    from GapfillerVisualizer import GapfillerLogParser, HTMLReportGenerator
except ImportError:
    # Fallback if running independently
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from GapfillerVisualizer import GapfillerLogParser, HTMLReportGenerator


class CtgLinkerVisualizer:
    """
    Visualizer for CtgLinker results.
    
    Parses the output directory of CtgLinker, generates individual reports for each
    extension step using GapfillerVisualizer, and creates a global summary report.
    """
    
    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)
        self.project_dir = self.output_dir / "project"
        self.report_dir = self.output_dir / "visual.report"
        
        if not self.project_dir.exists():
            print(f"Warning: Project directory not found at {self.project_dir}")
            

    def _parse_agp(self):
        """
        Parse DG.scaffold.agp to reconstruct scaffold structures recursively.
        
        If ctglinker_check.json is available (from CtgLinkerCheck), use it directly
        for more accurate scaffold-contig mapping.
        
        New Logic:
        1. Read all object definitions from AGP into self.agp_objects.
        2. Identify 'Root Scaffolds' (objects that are not components of any other object).
        3. Recursively expand root scaffolds to get the final list of atomic components (Contigs & GapFillers).
        """
        scaffolds = {}
        
        # ✨ 优先使用 CtgLinkerCheck 的结果
        if self.check_result and 'valid_scaffolds' in self.check_result:
            print("  Using CtgLinkerCheck results for scaffold visualization...")
            return self._build_scaffolds_from_check_result()
        
        agp_file = self.output_dir / "DG.scaffold.agp"
        
        if not agp_file.exists():
            return scaffolds
            
        # 1. Read all objects
        self.agp_objects = {}
        all_component_ids = set()
        
        try:
            with open(agp_file, 'r') as f:
                for line in f:
                    if line.startswith('#') or not line.strip():
                        continue
                    
                    parts = line.strip().split('\t')
                    if len(parts) < 9:
                        continue
                        
                    obj_id = parts[0]
                    comp_id = parts[5]
                    orientation = parts[8]
                    comp_start = int(parts[6])
                    comp_end = int(parts[7])
                    
                    if obj_id not in self.agp_objects:
                        self.agp_objects[obj_id] = []
                    
                    self.agp_objects[obj_id].append({
                        "id": comp_id,
                        "orientation": orientation,
                        "length": abs(comp_end - comp_start) + 1
                    })
                    
                    all_component_ids.add(comp_id)
                    
            # 2. Identify Root Scaffolds
            # A root scaffold is an object ID that never appears as a component ID
            root_scaffolds = []
            for obj_id in self.agp_objects:
                # Heuristic: Check if obj_id matches any component ID
                # Exact match check is safest.
                # Note: Sometimes object names have extra info, but component names in AGP refer to them.
                # In the provided example:
                # Object: Scaffold_2(DG3)DG3
                # Component in it: DG2
                # Object: Scaffold_2(DG3)DG2 (This corresponds to DG2 component)
                
                is_component = False
                # Check if this object ID is used as a component in any other object
                # We need to be careful about naming. 
                # Usually, if obj_id is "Scaffold_X(DG_Y)DG_Y", it's likely a root.
                # If obj_id is "Scaffold_X(DG_Y)DG_Z", it might be a sub-part.
                
                # Better approach: Check if any component ID "looks like" this object.
                # But component IDs are like "DG2", while Object IDs are "Scaffold_2(DG3)DG2".
                # So we check if the Object ID *ends with* the component ID (common convention in this tool).
                
                # Actually, let's reverse it:
                # For a given Object ID, is there a component ID in ANY object that "points" to it?
                # Pointing means: Object ID ends with Component ID (e.g. ...DG2 ends with DG2)
                
                for comp_id in all_component_ids:
                    # Check if Object ID is a "realization" of this Component ID
                    # e.g. Object "Scaffold_2(DG3)DG2" is the realization of Component "DG2"
                    if obj_id == comp_id or obj_id.endswith(f"){comp_id}") or obj_id.endswith(f"_{comp_id}") or obj_id.endswith(f"({comp_id})"):
                        is_component = True
                        break
                
                if not is_component:
                    root_scaffolds.append(obj_id)
            
            # 3. Expand Root Scaffolds
            for scaffold_id in root_scaffolds:
                # Sort components of the root scaffold first
                sorted_root_comps = self._sort_object_components(self.agp_objects[scaffold_id])
                
                # Recursively expand
                expanded_components = []
                # Root is always + orientation effectively
                for comp in sorted_root_comps:
                    expanded_components.extend(self._expand_component(comp, '+'))
                
                # Clean up scaffold ID for display
                display_id = scaffold_id
                # Remove (DGxx) from name
                # Pattern: Scaffold_X(DGY) -> Scaffold_X
                # Or Scaffold_X(DGY)DGZ -> Scaffold_X
                # User wants: "去掉Scaffold后的(DGXX)"
                # Example: Scaffold_1(DG1) -> Scaffold_1
                
                # First remove the (DG..) part
                clean_id = re.sub(r'\s*\(DG\d+\).*', '', scaffold_id)
                # Also handle if it's just Scaffold_1(DG1) without trailing text
                clean_id = re.sub(r'\(DG\d+\)', '', clean_id)
                
                # If the regex was too aggressive or didn't match, fallback to simple split
                if not clean_id:
                     clean_id = scaffold_id
                
                # Calculate total length from expanded components
                total_length = sum(c['length'] for c in expanded_components)
                
                # Identify Seed in the final expanded list for highlighting
                # The seed is the longest contig
                max_len = -1
                seed_idx = -1
                for i, c in enumerate(expanded_components):
                    if c['type'] == 'contig' and c['length'] > max_len:
                        max_len = c['length']
                        seed_idx = i
                
                if seed_idx != -1:
                    expanded_components[seed_idx]['is_seed'] = True

                scaffolds[clean_id] = {
                    "length": total_length,
                    "components": expanded_components
                }

        except Exception as e:
            print(f"Error parsing AGP file: {e}")
            import traceback
            traceback.print_exc()
            
        return scaffolds

    def _build_scaffolds_from_check_result(self):
        """
        从 CtgLinkerCheck 的结果构建 scaffold 可视化数据
        
        这个方法使用 ctglinker_check.json 中的有效 scaffold 信息，
        结合 AGP 文件中的详细组件信息，生成可视化所需的数据结构。
        
        在 contigs 之间插入成功的 gap_fill 块（绿色），点击可跳转到报告。
        """
        scaffolds = {}
        
        # ✨ 修复：从原始 contig 文件获取长度，而不是从 AGP 文件
        # AGP 文件中的长度可能是 DG 的长度，不是原始 contig 的长度
        contig_info = {}  # {contig_id: {'length': int, 'orientation': str}}
        
        # 方法1：从 Genome.inputCtg.fa 读取原始 contig 长度
        input_ctg_fa = self.output_dir / "Genome.inputCtg.fa"
        if input_ctg_fa.exists():
            try:
                from Bio import SeqIO
                for record in SeqIO.parse(input_ctg_fa, "fasta"):
                    contig_id = record.id
                    contig_info[contig_id] = {
                        'length': len(record.seq),
                        'orientation': '+'
                    }
                print(f"  Loaded {len(contig_info)} contig lengths from {input_ctg_fa}")
            except Exception as e:
                print(f"  Warning: Error reading contig lengths from FASTA: {e}")
        
        # 如果没有从 FASTA 获取到，尝试从 AGP 文件获取（fallback）
        if not contig_info:
            agp_file = self.output_dir / "DG.scaffold.agp"
            if agp_file.exists():
                try:
                    with open(agp_file, 'r') as f:
                        for line in f:
                            if line.startswith('#') or not line.strip():
                                continue
                            parts = line.strip().split('\t')
                            if len(parts) < 9:
                                continue
                            comp_id = parts[5]
                            # 只记录原始 Contig（不包含 DG 或 noExtension）
                            if comp_id.startswith('Contig-') and 'noExtension' not in comp_id and 'DG' not in comp_id:
                                comp_start = int(parts[6])
                                comp_end = int(parts[7])
                                orientation = parts[8]
                                length = abs(comp_end - comp_start) + 1
                                # 取最小长度（避免使用 DG 的长度）
                                if comp_id not in contig_info or length < contig_info[comp_id]['length']:
                                    contig_info[comp_id] = {
                                        'length': length,
                                        'orientation': orientation
                                    }
                except Exception as e:
                    print(f"  Warning: Error reading AGP for contig info: {e}")
        
        # 从 check_result 构建 scaffold 数据
        for scaffold_data in self.check_result['valid_scaffolds']:
            # ✨ 过滤空的 scaffold（长度为 0 或没有 contigs）
            if scaffold_data.get('length', 0) == 0 or not scaffold_data.get('contigs'):
                print(f"  Skipping empty scaffold: {scaffold_data.get('id')}")
                continue
            scaffold_id = scaffold_data['id']
            scaffold_length = scaffold_data['length']
            contigs = scaffold_data['contigs']
            gap_fills = scaffold_data.get('gap_fills', [])
            
            components = []
            
            # ✨ 修复：seed 是第一个 DG 的 seed contig，而不是最长的 contig
            # 优先使用 ctglinker_check.json 中的 seed_contig 字段
            seed_contig = scaffold_data.get('seed_contig')
            
            # 如果没有 seed_contig 字段，从 gap_fills 推断
            if not seed_contig:
                # gap_fills 中的 linked_contig 都不是 seed，剩下的就是 seed
                linked_contigs = set()
                for gf in gap_fills:
                    if gf.get('linked_contig'):
                        linked_contigs.add(gf['linked_contig'])
                
                for contig_id in contigs:
                    if contig_id not in linked_contigs:
                        seed_contig = contig_id
                        break
            
            # 如果还是没找到，使用第一个 contig 作为 seed（fallback）
            if not seed_contig and contigs:
                seed_contig = contigs[0]
            
            # 构建组件列表，在 contigs 之间插入成功的 gap_fill
            for i, contig_id in enumerate(contigs):
                info = contig_info.get(contig_id, {'length': scaffold_length // max(len(contigs), 1), 'orientation': '+'})
                
                # 添加 contig
                comp = {
                    'id': contig_id,
                    'length': info['length'],
                    'orientation': info['orientation'],
                    'type': 'contig',
                    'is_seed': contig_id == seed_contig
                }
                components.append(comp)
                
                # 在 contigs 之间添加成功的 gap_fill 块
                if i < len(contigs) - 1:
                    # 查找连接当前 contig 和下一个 contig 的 gap_fill
                    gap_fill_info = self._find_gap_fill_between(contig_id, contigs[i + 1], gap_fills, scaffold_data)
                    if gap_fill_info:
                        components.append(gap_fill_info)
            
            scaffolds[scaffold_id] = {
                'length': scaffold_length,
                'components': components
            }
        
        return scaffolds
    
    def _find_gap_fill_between(self, contig1, contig2, gap_fills, scaffold_data):
        """
        查找连接两个 contig 的成功 gap_fill
        
        返回 gap_fill 组件信息，包含报告链接
        
        逻辑说明：
        - gap_fill 的 linked_contig 表示该 gap_fill 连接到的 contig
        - 例如：DG1-Left linked_contig=Contig-1 表示 DG1 向左延伸连接到了 Contig-1
        - 所以这个 gap_fill 应该显示在 Contig-1 和 seed 之间
        
        contigs 顺序: [Contig-0, Contig-1, Contig-2(seed)]
        gap_fills:
          - DG1-Left linked_contig=Contig-1 -> 显示在 Contig-1 和 Contig-2 之间
          - DG2-Left linked_contig=Contig-0 -> 显示在 Contig-0 和 Contig-1 之间
        """
        gap_length = 5000  # 默认显示宽度
        
        report_link = None
        matched_gf = None
        
        # ✨ 修复：linked_contig 是 gap_fill 连接到的目标 contig
        # 如果 linked_contig == contig1，说明这个 gap_fill 连接了 contig1，
        # 它应该显示在 contig1 和它右边的 contig 之间
        # 所以我们需要检查 linked_contig == contig1（左边的 contig）
        for gf in gap_fills:
            linked_contig = gf.get('linked_contig')
            if linked_contig and linked_contig == contig1:
                # 这个 gap_fill 连接到了 contig1，应该显示在 contig1 和 contig2 之间
                matched_gf = gf
                report_path = gf.get('report_path', '')
                if report_path:
                    parts = report_path.split('/')
                    if len(parts) >= 1:
                        report_link = f"{parts[-1]}/gapfiller_report.html"
                break
        
        # 如果没找到匹配的 gap_fill，返回 None
        if not matched_gf:
            return None
        
        return {
            'id': f'gap_{contig1}_{contig2}',
            'length': 0,  # 长度设为 0，在渲染时使用固定宽度
            'type': 'gap_fill',
            'is_success': True,
            'report_link': report_link,
            'source': contig1,
            'target': contig2,
            'is_direct': matched_gf.get('is_direct', False)
        }

    def _sort_object_components(self, components):
        """
        Sort components of a single object based on CtgLinker topology:
        [Left Extension] -> [Left Linker] -> [Seed] -> [Right Linker] -> [Right Extension]
        """
        if not components:
            return []
            
        # Separate Linkers and Content
        linkers = []
        content = []
        
        for c in components:
            cid = c['id']
            # Check if it's a linker (DGx-Left/Right)
            # Note: A component might be a nested DG (e.g. DG2) which is Content,
            # or a Linker task (DG2-Left).
            # Linkers usually have 'Left' or 'Right' in name AND 'DG'.
            # But nested DG also has 'DG'.
            # Distinction: Linker usually has 'noExtension' or is just 'DGx-Left'.
            # Nested DG is just 'DGx'.
            
            is_linker = False
            if 'DG' in cid:
                if 'Left' in cid or 'Right' in cid:
                    # Likely a linker
                    is_linker = True
            
            if is_linker:
                linkers.append(c)
            else:
                content.append(c)
        
        if not content:
            # Just linkers? Return as is (or sorted by Left/Right)
            return sorted(linkers, key=lambda x: 0 if 'Left' in x['id'] else 1)
            
        # Identify Seed (Longest Content)
        seed = max(content, key=lambda x: x['length'])
        extensions = [c for c in content if c != seed]
        
        # Identify Left and Right Linkers
        l_linker = None
        r_linker = None
        
        for l in linkers:
            if 'Left' in l['id'] or '_L' in l['id']:
                l_linker = l
            elif 'Right' in l['id'] or '_R' in l['id']:
                r_linker = l
        
        # Assign Extensions
        l_ext = None
        r_ext = None
        
        # If we have extensions, try to assign them
        if extensions:
            # Check Linker Status to guide assignment
            # We can't easily check status here without parsing logs, 
            # but we can check if Linker is "Failed" based on name (noExtension)
            
            l_success = l_linker and 'noExtension' not in l_linker['id']
            r_success = r_linker and 'noExtension' not in r_linker['id']
            
            remaining_exts = extensions[:]
            
            if l_success and remaining_exts:
                # Assign one to Left
                # Heuristic: If 2 extensions, use coordinates?
                # If 1 extension, assign here.
                l_ext = remaining_exts.pop(0)
                
            if r_success and remaining_exts:
                r_ext = remaining_exts.pop(0)
                
            # If any extensions remain (e.g. both success, but we picked arbitrarily),
            # we might need better logic.
            # But CtgLinker typically has 1 seed + 0-2 extensions.
            
        # Construct sorted list
        sorted_list = []
        if l_ext: sorted_list.append(l_ext)
        if l_linker: sorted_list.append(l_linker)
        sorted_list.append(seed)
        if r_linker: sorted_list.append(r_linker)
        if r_ext: sorted_list.append(r_ext)
        
        return sorted_list

    def _parse_direct_connection_contig(self, dg_id, direction):
        """
        从 process.log 中解析 direct connection 连接的 contig ID
        
        Args:
            dg_id: DG ID，如 "DG1"
            direction: "Left" 或 "Right"
        
        Returns:
            str: 连接的 contig ID（如 "Contig-1"），如果没有找到则返回 None
        """
        process_log = self.project_dir / dg_id / f"{dg_id}-{direction}" / "process.log"
        
        if not process_log.exists():
            return None
        
        try:
            with open(process_log, 'r') as f:
                content = f.read()
                # 查找 "Connected edge: Contig-1-edge-right" 格式的行
                match = re.search(r'Connected edge:\s*(\S+)', content)
                if match:
                    connected_edge = match.group(1)
                    # 解析 contig ID，格式: "Contig-1-edge-right" 或 "Contig-1-edge-left_rc"
                    if '-edge-' in connected_edge:
                        parts = connected_edge.split('-edge-')
                        contig_id = parts[0]
                        return contig_id
        except Exception as e:
            print(f"  Warning: Error parsing direct connection from {process_log}: {e}")
        
        return None

    def _expand_component(self, component_info, parent_orientation):
        """
        Recursively expand a component.
        
        Args:
            component_info (dict): The component dict from AGP (id, length, orientation).
            parent_orientation (str): '+' or '-'. The orientation of the parent object.
            
        Returns:
            list: A list of atomic components (dicts).
        """
        component_id = component_info['id']
        
        # Calculate effective orientation of THIS component relative to the global scaffold
        # If parent is +, we keep our orientation.
        # If parent is -, we flip our orientation.
        current_orientation = component_info['orientation']
        if parent_orientation == '-':
            current_orientation = '+' if current_orientation == '-' else '-'
            
        # 1. Find the Object definition that corresponds to this component_id
        target_obj_id = None
        if component_id in self.agp_objects:
            target_obj_id = component_id
        else:
            # Search for an object that "implements" this component
            for obj_id in self.agp_objects:
                if obj_id.endswith(f"){component_id}") or obj_id.endswith(f"_{component_id}") or obj_id.endswith(f"({component_id})"):
                    target_obj_id = obj_id
                    break
        
        # 2. If found, it's a composite object (DG) -> Recursively expand
        if target_obj_id:
            sub_components = self.agp_objects[target_obj_id]
            
            # SORT sub-components before expanding
            sub_components = self._sort_object_components(sub_components)
            
            # If current effective orientation is '-', we need to process sub-components in reverse order
            if current_orientation == '-':
                sub_components = sub_components[::-1]
            
            expanded_list = []
            for sub in sub_components:
                # Pass current_orientation as the parent_orientation for the child
                expanded_list.extend(self._expand_component(sub, current_orientation))
                
            return expanded_list
            
        # 3. If not found, it's an atomic component (Contig or GapFiller task)
        else:
            # Determine type
            is_gap_fill = False
            is_failed = False
            dg_id = None
            fill_side = None
            linked_contig = None  # ✨ 新增：direct connection 连接的 contig
            
            # Check for DG identifier pattern
            dg_match = re.search(r'DG(\d+)', component_id)
            if dg_match:
                 if "Contig" in component_id and "noExtension" not in component_id:
                     # It's a contig (e.g. Contig-1)
                     pass
                 else:
                     is_gap_fill = True
                     dg_id = f"DG{dg_match.group(1)}"
                     
                     if 'Left' in component_id or '_L' in component_id:
                         fill_side = 'Left'
                     elif 'Right' in component_id or '_R' in component_id:
                         fill_side = 'Right'
                         
                     if '_no' in component_id or 'noExtension' in component_id:
                         is_failed = True
                     
                     # ✨ 新增：检查是否为 direct_overlap，解析连接的 contig
                     if '_direct_overlap' in component_id or 'direct_overlap' in component_id:
                         # 从 process.log 解析 Connected edge
                         linked_contig = self._parse_direct_connection_contig(dg_id, fill_side)
                         if linked_contig:
                             print(f"  [Visualizer] Resolved direct_overlap: {component_id} -> {linked_contig}")
            
            component = {
                "id": component_id,
                "length": component_info['length'],
                "orientation": current_orientation,
                "type": "gap_fill" if is_gap_fill else "contig"
            }
            
            if is_gap_fill:
                component["dg_id"] = dg_id
                component["fill_side"] = fill_side
                component["is_failed"] = is_failed
                # ✨ 新增：记录 direct connection 连接的 contig
                if linked_contig:
                    component["linked_contig"] = linked_contig
                    component["is_direct_connection"] = True
                
            return [component]


    def _detect_input_mode(self):
        """
        Detect whether the input was a single scaffold (Ordered) or multiple contigs (Unordered).
        Reads Genome.inputCtg.fa and checks the original sequence IDs in descriptions.
        """
        input_fa = self.output_dir / "Genome.inputCtg.fa"
        mode = "Unknown"
        mode_zh = "未知"
        
        if not input_fa.exists():
            return mode, mode_zh
            
        original_ids = set()
        try:
            with open(input_fa, 'r') as f:
                for line in f:
                    if line.startswith('>'):
                        # Format: >Contig-X\tOriginal_ID
                        parts = line.strip().split('\t')
                        if len(parts) >= 2:
                            original_ids.add(parts[1])
                        else:
                            # Fallback if no tab, maybe space separated or just ID
                            # But N50Check usually adds tab
                            original_ids.add(line.strip()[1:])
            
            if len(original_ids) == 1:
                mode = "Scaffolding (Ordered)"
                mode_zh = "Scaffolding (有序)"
            elif len(original_ids) > 1:
                mode = "De novo Assembly (Unordered)"
                mode_zh = "De novo Assembly (无序)"
            else:
                mode = "Empty Input"
                mode_zh = "输入为空"
                
        except Exception as e:
            print(f"Error detecting input mode: {e}")
            
        return mode, mode_zh

    def generate_report(self):
        """
        Main execution method.
        """
        # Create report directory
        self.report_dir.mkdir(exist_ok=True)
        
        print("Parsing CtgLinker statistics...")
        self.stats = self._parse_n50_stats()
        
        print("Detecting input mode...")
        self.input_mode, self.input_mode_zh = self._detect_input_mode()
        
        print("Parsing iteration details...")
        self.iterations = self._parse_iterations()
        
        # Try to load pre-computed check results from CtgLinkerCheck
        check_file = self.output_dir / "ctglinker_check.json"
        self.check_result = None
        if check_file.exists():
            print("Loading CtgLinkerCheck results...")
            try:
                with open(check_file, 'r') as f:
                    self.check_result = json.load(f)
                print(f"  Loaded {len(self.check_result.get('valid_scaffolds', []))} valid scaffolds from check results")
            except Exception as e:
                print(f"  Warning: Failed to load check results: {e}")
                self.check_result = None
        
        print("Parsing AGP for scaffold visualization...")
        self.scaffolds = self._parse_agp()
        
        print("Generating sub-reports for iterations...")
        self._generate_sub_reports()
        
        print("Generating global HTML report...")
        report_path = self._generate_global_html()
        
        return str(report_path)

    def _parse_n50_stats(self):
        """Parse initial and final N50 statistics from log files."""
        stats = {
            "initial": {"N50": 0, "count": 0, "sum": 0},
            "final": {"N50": 0, "count": 0, "sum": 0}
        }
        
        # Initial stats: Genome.inputCtg.log
        init_log = self.output_dir / "Genome.inputCtg.log"
        if init_log.exists():
            stats["initial"] = self._parse_single_n50_log(init_log)
            
        # Final stats: DG.scaffold.log (if exists) or calculate from DG.scaffold.fa
        final_log = self.output_dir / "DG.scaffold.log"
        if final_log.exists():
            stats["final"] = self._parse_single_n50_log(final_log)
        else:
            # If log doesn't exist, calculate from FASTA file
            scaffold_fa = self.output_dir / "DG.scaffold.fa"
            if scaffold_fa.exists():
                stats["final"] = self._calculate_n50_from_fasta(scaffold_fa)
            
        return stats

    def _parse_single_n50_log(self, log_file):
        """
        Helper to parse N50Check log format.
        Supports two formats:
        1. Tab-separated simple key-value: key\tvalue
        2. Colon-separated verbose: key:\tvalue
        """
        data = {"N50": 0, "count": 0, "sum": 0}
        try:
            with open(log_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    
                    # Try splitting by tab first (new/mock format)
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        key = parts[0].lower().strip().rstrip(':')
                        val = parts[1].strip()
                    else:
                        # Try splitting by colon (legacy format found in ctg_test2)
                        parts = line.split(':')
                        if len(parts) >= 2:
                            key = parts[0].lower().strip()
                            val = parts[1].strip()
                        else:
                            continue

                    try:
                        if key == 'n50':
                            data['N50'] = int(val)
                        elif 'contig number' in key or key == 'number':
                            data['count'] = int(val)
                        elif 'total non-n base' in key or key == 'sum':
                            data['sum'] = int(val)
                    except ValueError:
                        pass
                        
        except Exception as e:
            print(f"Error parsing {log_file}: {e}")
        return data
    
    def _calculate_n50_from_fasta(self, fasta_file):
        """
        Calculate N50 statistics directly from a FASTA file.
        Used when log file doesn't exist.
        """
        from Bio import SeqIO
        
        data = {"N50": 0, "count": 0, "sum": 0}
        
        try:
            # Read all sequence lengths
            lengths = []
            for record in SeqIO.parse(fasta_file, "fasta"):
                seq_len = len(str(record.seq).replace('N', '').replace('n', ''))  # Exclude N bases
                if seq_len > 0:
                    lengths.append(seq_len)
            
            if not lengths:
                return data
            
            # Calculate statistics
            data['count'] = len(lengths)
            data['sum'] = sum(lengths)
            
            # Calculate N50
            lengths.sort(reverse=True)
            half_sum = data['sum'] / 2
            cumulative = 0
            for length in lengths:
                cumulative += length
                if cumulative >= half_sum:
                    data['N50'] = length
                    break
                    
        except Exception as e:
            print(f"Error calculating N50 from {fasta_file}: {e}")
            
        return data

    def _parse_iterations(self):
        """
        Find and parse all DG iterations in the project directory.
        Returns a dict keyed by DG ID (e.g., "DG1").
        """
        iterations = {}
        
        if not self.project_dir.exists():
            return iterations
            
        # List all directories starting with DG
        dg_dirs = [d for d in self.project_dir.iterdir() if d.is_dir() and d.name.startswith("DG")]
        
        # Sort by ID number
        def get_id(d):
            m = re.match(r"DG(\d+)", d.name)
            return int(m.group(1)) if m else 0
            
        dg_dirs.sort(key=get_id)
        
        for dg_dir in dg_dirs:
            dg_name = dg_dir.name
            iter_data = {"id": dg_name}
            
            # Check for Left and Right sub-directories
            for direction in ["Left", "Right"]:
                sub_dir = dg_dir / f"{dg_name}-{direction}"
                
                if sub_dir.exists():
                    status = self._get_extension_status(sub_dir)
                    
                    data = {
                        "path": str(sub_dir),
                        "status": status,
                        "report_link": None  # Will be filled later if we generate sub-reports
                    }
                    
                    # Store in lowercase key matching directory name
                    # Note: 'left' maps to DG-Left directory (flag='left', extends scaffold RIGHT)
                    #       'right' maps to DG-Right directory (flag='right', extends scaffold LEFT)
                    iter_data[direction.lower()] = data
                    
            iterations[dg_name] = iter_data
            
        return iterations

    def _get_extension_status(self, sub_dir):
        """Determine the status of an extension from its logs."""
        log_file = sub_dir / "process.log"
        status = "unknown"
        
        if not log_file.exists():
            return "not_run"
            
        try:
            with open(log_file, 'r') as f:
                content = f.read()
                content_lower = content.lower()
                
                if "GAP can be closed!" in content:
                    status = "closed"
                elif "GAP still not closed!" in content:
                    status = "open"
                elif "noextensionreadsfound" in content_lower or \
                     "noextensioncontigsor" in content_lower or \
                     ("no extension" in content_lower and ("reads" in content_lower or "contigs" in content_lower)):
                    # Matches various forms: "noExtensionReadsFoundAfterParameterRelaxation",
                    # "noExtensionContigsorReads", "No Extension Reads Found", etc.
                    status = "no_extension"
                elif "ExtensionSequence can close the GAP!" in content:
                    status = "closed"
                elif "Extension" in content and "Success" in content:
                    # Sometimes generic success
                    status = "extended"
        except:
            pass
            
        return status

    def _generate_sub_reports(self):
        """
        拷贝 GapFiller 任务的可视化报告到 visual.report/ 目录
        
        GapFiller 报告已在任务完成时生成（在 CtgLinker.py 中），
        报告和 direct_connection_check 都在 visualization_output/ 目录中，
        这里只需要拷贝整个 visualization_output 目录。
        """
        import shutil
        
        for dg_name, data in self.iterations.items():
            for direction in ["left", "right"]:
                if direction in data:
                    sub_info = data[direction]
                    sub_dir = Path(sub_info["path"])
                    status = sub_info.get("status", "unknown")
                    
                    # 只处理成功的任务（closed, extended）
                    if status not in ["closed", "extended"]:
                        continue
                    
                    # 源目录：GapFiller 结果中的 visualization_output
                    src_vis_dir = sub_dir / "visualization_output"
                    
                    # 目标目录
                    report_out_dir = self.report_dir / f"{dg_name}-{direction.capitalize()}"
                    
                    if src_vis_dir.exists():
                        try:
                            # 复制整个 visualization_output 目录内容
                            if report_out_dir.exists():
                                shutil.rmtree(report_out_dir)
                            shutil.copytree(src_vis_dir, report_out_dir)
                            sub_info["report_link"] = f"{dg_name}-{direction.capitalize()}/gapfiller_report.html"
                            print(f"  Copied visualization_output: {dg_name}-{direction.capitalize()}")
                        except Exception as e:
                            print(f"  Warning: Failed to copy report for {dg_name}-{direction}: {e}")
                    else:
                        print(f"  Warning: No visualization_output found for {dg_name}-{direction} at {src_vis_dir}")

    def _translate_status(self, status):
        """Translate status code to Chinese."""
        translations = {
            "closed": "已闭合",
            "open": "未闭合",
            "extended": "已延伸",
            "no_extension": "无延伸",
            "unknown": "未知",
            "not_run": "未运行"
        }
        return translations.get(status, status)

    def _generate_global_html(self):
        """Generate the main summary HTML file."""
        
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CtgLinker Summary Report</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background-color: #f5f7fa; color: #333; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        
        .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #3498db; padding-bottom: 10px; margin-bottom: 20px; }}
        h1 {{ color: #2c3e50; margin: 0; }}
        
        .language-switcher {{ display: flex; gap: 10px; }}
        .lang-btn {{ padding: 5px 15px; border: 1px solid #3498db; border-radius: 20px; cursor: pointer; background: white; color: #3498db; font-weight: bold; transition: all 0.2s; }}
        .lang-btn:hover {{ background: #e8f4fd; }}
        .lang-btn.active {{ background: #3498db; color: white; }}
        
        h2 {{ color: #34495e; margin-top: 30px; }}
        
        /* Stats Table */
        .stats-table {{ width: 100%; border-collapse: collapse; margin-bottom: 30px; }}
        .stats-table td {{ padding: 15px; border-bottom: 1px solid #eee; }}
        .stat-key {{ font-weight: bold; color: #7f8c8d; width: 30%; background: #f8f9fa; }}
        .stat-value {{ font-size: 1.2em; font-weight: bold; color: #2c3e50; }}
        
        .diff-positive {{ color: #27ae60; font-size: 0.8em; margin-left: 10px; }}
        .diff-negative {{ color: #c0392b; font-size: 0.8em; margin-left: 10px; }}
        
        /* Linking Table */
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th {{ background: #34495e; color: white; padding: 12px; text-align: left; }}
        td {{ padding: 12px; border-bottom: 1px solid #eee; }}
        tr:hover {{ background-color: #f1f2f6; }}
        
        .status-badge {{ padding: 5px 10px; border-radius: 15px; font-size: 12px; font-weight: bold; text-transform: uppercase; display: inline-block; min-width: 80px; text-align: center; }}
        .status-closed {{ background: #d5f5e3; color: #27ae60; }}
        .status-open {{ background: #fadbd8; color: #c0392b; }}
        .status-extended {{ background: #d6eaf8; color: #3498db; }}
        .status-unknown {{ background: #f2f3f4; color: #7f8c8d; }}
        .status-no_extension {{ background: #fce4ec; color: #c0392b; }}
        
        .btn {{ display: inline-block; padding: 6px 12px; background: #3498db; color: white; text-decoration: none; border-radius: 4px; font-size: 12px; transition: background 0.2s; margin-left: 10px; }}
        .btn:hover {{ background: #2980b9; }}
        .btn-disabled {{ background: #bdc3c7; cursor: not-allowed; pointer-events: none; }}
    </style>
    <script>
        function switchLanguage(lang) {{
            document.querySelectorAll('.lang-en').forEach(el => el.style.display = lang === 'en' ? '' : 'none');
            document.querySelectorAll('.lang-zh').forEach(el => el.style.display = lang === 'zh' ? '' : 'none');
            
            document.getElementById('btn-en').classList.toggle('active', lang === 'en');
            document.getElementById('btn-zh').classList.toggle('active', lang === 'zh');
        }}
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>🧬 CtgLinker Summary Report</h1>
                <p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            <div class="language-switcher">
                <button id="btn-en" class="lang-btn active" onclick="switchLanguage('en')">English</button>
                <button id="btn-zh" class="lang-btn" onclick="switchLanguage('zh')">中文</button>
            </div>
        </div>
        
        <h2>📈 Assembly Statistics <span class="lang-zh" style="display:none;">(组装统计)</span></h2>
        <table class="stats-table">
            <tr>
                <td class="stat-key">
                    <span class="lang-en">Contig Count</span>
                    <span class="lang-zh" style="display:none;">Contig 数量</span>
                </td>
                <td class="stat-value">
                    {self.stats['initial']['count']} → {self.stats['final']['count']}
                    <span class="diff-positive">({self.stats['final']['count'] - self.stats['initial']['count']})</span>
                </td>
            </tr>
            <tr>
                <td class="stat-key">
                    <span class="lang-en">N50 Length</span>
                    <span class="lang-zh" style="display:none;">N50 长度</span>
                </td>
                <td class="stat-value">
                    {self.stats['initial']['N50']:,} bp → {self.stats['final']['N50']:,} bp
                    <span class="diff-positive">(+{self.stats['final']['N50'] - self.stats['initial']['N50']:,} bp)</span>
                </td>
            </tr>
        </table>
        
        <h2>🏗️ Scaffold Visualization <span class="lang-zh" style="display:none;">(Scaffold 可视化)</span></h2>
        <div id="scaffold-container"></div>

        <script>
            const scaffolds = SC_DATA_PLACEHOLDER;
            const iterations = ITER_DATA_PLACEHOLDER;

            function renderScaffolds() {{
                const container = document.getElementById('scaffold-container');
                
                // Sort scaffolds by length (descending)
                const sortedIds = Object.keys(scaffolds).sort((a, b) => scaffolds[b].length - scaffolds[a].length);
                
                if (sortedIds.length === 0) return;
                
                // Calculate max length for relative scaling
                const maxLen = scaffolds[sortedIds[0]].length;
                
                sortedIds.forEach(scaffoldId => {{
                    const scaffold = scaffolds[scaffoldId];
                    
                    // ✨ 过滤空的 scaffold（0 bp 或无组件）
                    if (scaffold.length === 0 || !scaffold.components || scaffold.components.length === 0) {{
                        return;  // 跳过空 scaffold
                    }}
                    
                    const scaffoldDiv = document.createElement('div');
                    scaffoldDiv.className = 'scaffold-track-container';
                    scaffoldDiv.innerHTML = '<h3>' + scaffoldId + ' <span style="font-size:0.8em;color:#777">(' + scaffold.length.toLocaleString() + ' bp)</span></h3>';
                    
                    const trackDiv = document.createElement('div');
                    trackDiv.className = 'scaffold-track';
                    
                    // Set relative width
                    const relativeWidth = (scaffold.length / maxLen) * 100;
                    trackDiv.style.width = relativeWidth + '%';
                    
                    // 计算所有 contig 的长度总和（不包括 gap_fill）
                    const totalContigLength = scaffold.components
                        .filter(c => c.type === 'contig')
                        .reduce((sum, c) => sum + c.length, 0);
                    
                    // 计算 gap_fill 的数量
                    const gapFillCount = scaffold.components.filter(c => c.type === 'gap_fill').length;
                    
                    // gap_fill 使用固定宽度（每个 5%），剩余空间给 contig
                    const gapFillWidthPercent = 5;
                    const contigTotalWidthPercent = 100 - (gapFillCount * gapFillWidthPercent);
                    
                    scaffold.components.forEach((comp, compIndex) => {{
                        const compDiv = document.createElement('div');
                        let widthPercent;
                        
                        if (comp.type === 'gap_fill') {{
                            // gap_fill 使用固定宽度
                            widthPercent = gapFillWidthPercent;
                        }} else {{
                            // contig 按比例分配剩余空间
                            widthPercent = (comp.length / totalContigLength) * contigTotalWidthPercent;
                        }}
                        
                        if (comp.type === 'contig') {{
                            compDiv.className = 'component-contig';
                            
                            // Check for seed marker
                            const isSeed = comp.is_seed;
                            const displayId = comp.id;
                            const orient = comp.orientation === '-' ? '◀' : '▶';
                            
                            // User request: "seedcontig's contig should be bold, behind add a bracket (seed)"
                            // "do not use ▶" for seed
                            
                            if (isSeed) {{
                                compDiv.classList.add('seed');
                                compDiv.title = displayId + ' (Seed Contig, ' + comp.length.toLocaleString() + ' bp)';
                                // Bold text, add (Seed), NO arrow
                                compDiv.innerHTML = '<b>' + displayId + ' (Seed)</b>';
                            }} else {{
                                compDiv.title = displayId + ' (' + comp.length.toLocaleString() + ' bp)';
                                // Normal text, NO arrow (user request: remove ▶ marker)
                                compDiv.innerText = displayId;
                            }}
                            
                            compDiv.style.width = widthPercent + '%';
                            
                            // Add specific class for orientation if needed (for color/style)
                            if (comp.orientation === '-') {{
                                compDiv.classList.add('reverse-strand');
                            }}
                            
                        }} else if (comp.type === 'gap_fill') {{
                            // ✨ 新增：检查是否为 direct connection，显示连接的 contig
                            if (comp.is_direct_connection && comp.linked_contig) {{
                                // Direct connection: 显示为 contig（蓝色），带 linked 标记
                                compDiv.className = 'component-contig linked';
                                const linkedContig = comp.linked_contig;
                                const orient = comp.orientation === '-' ? '◀' : '▶';
                                compDiv.title = linkedContig + ' (via Direct Connection, ' + comp.length.toLocaleString() + ' bp) ' + orient;
                                compDiv.innerText = linkedContig + ' ' + orient;
                                compDiv.style.width = widthPercent + '%';
                            }} else if (comp.is_failed) {{
                                // 失败的 gap_fill：跳过不显示
                                return;
                            }} else {{
                                // 成功的 gap_fill 块（绿色，可点击）
                                compDiv.className = 'component-gap success';
                                
                                // 固定宽度显示
                                const displayWidth = Math.max(widthPercent, 2); 
                                compDiv.style.width = displayWidth + '%';
                                compDiv.style.minWidth = '30px';
                                
                                // 提示信息
                                const source = comp.source || '';
                                const target = comp.target || '';
                                compDiv.title = 'Gap Fill: ' + source + ' → ' + target + ' (Click to view report)';
                                compDiv.innerHTML = '🔗';
                                
                                // 点击打开报告
                                if (comp.report_link) {{
                                    compDiv.style.cursor = 'pointer';
                                    compDiv.onclick = () => window.open(comp.report_link, '_blank');
                                }}
                            }}
                        }} else {{
                            // 其他类型的 gap（不显示失败的块）
                            // 跳过失败的 gap_fill
                            return;
                        }}
                        trackDiv.appendChild(compDiv);
                    }});
                    
                    scaffoldDiv.appendChild(trackDiv);
                    container.appendChild(scaffoldDiv);
                }});
            }}
            
            function openReport(dgId, preferredDir) {{
                // preferredDir: 'left' or 'right' (physical directory name)
                const dgData = iterations[dgId];
                if (dgData) {{
                    let reportLink = null;
                    
                    // Try preferred direction first
                    if (preferredDir && dgData[preferredDir] && dgData[preferredDir].report_link) {{
                        reportLink = dgData[preferredDir].report_link;
                    }} else {{
                        // Fallback: try left then right
                        if (dgData.left && dgData.left.report_link) {{
                            reportLink = dgData.left.report_link;
                        }} else if (dgData.right && dgData.right.report_link) {{
                            reportLink = dgData.right.report_link;
                        }}
                    }}
                    
                    if (reportLink) {{
                        window.open(reportLink, '_blank');
                    }} else {{
                        alert('No report available for ' + dgId);
                    }}
                }} else {{
                    alert('No data found for ' + dgId);
                }}
            }}
            
            // Initial render
            renderScaffolds();
        </script>
        
        <style>
            .scaffold-track-container {{ margin-bottom: 30px; }}
            .scaffold-track {{ 
                width: 100%; 
                height: 40px; 
                background: #eee; 
                display: flex; 
                border-radius: 5px; 
                overflow: hidden; 
                position: relative;
            }}
            .component-contig {{
                background-color: #3498db;
                height: 100%;
                border-right: 1px solid white;
                transition: opacity 0.2s;
                color: white;
                font-size: 10px;
                display: flex;
                align-items: center;
                justify-content: center;
                overflow: hidden;
                white-space: nowrap;
                text-overflow: ellipsis;
                padding: 0 2px;
            }}
            
            /* Seed Contig Highlight */
            .component-contig.seed {{
                font-weight: bold;
                box-shadow: inset 0 0 0 2px rgba(255,255,255,0.5);
            }}
            .component-contig.seed:hover {{
                background-color: #2980b9;
            }}
            
            /* Linked Contig - keep same style as regular contig (blue) */
            .component-contig.linked {{
                background-color: #3498db;
                color: white;
            }}
            .component-contig.linked:hover {{
                background-color: #2980b9;
            }}
            
            .component-contig:hover {{ opacity: 0.8; }}
            
            .component-gap {{
                height: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 10px;
                color: white;
                font-weight: bold;
                border-right: 1px solid white;
                min-width: 20px;
                background-color: #95a5a6;
            }}
            
            /* Success: Light Green for closed/extended gaps */
            .component-gap.success {{
                background-color: #a5d6a7;
                color: #1b5e20;
            }}
            .component-gap.success:hover {{
                background-color: #81c784;
            }}
            
            /* Failed: Orange/Red for unclosed gaps */
            .component-gap.failed {{
                background-color: #ffab91;
                color: #b71c1c;
            }}
            .component-gap.failed:hover {{
                background-color: #ef9a9a;
            }}
        </style>
    </div>
</body>
</html>"""

        # Inject JSON data
        html_content = html_content.replace("SC_DATA_PLACEHOLDER", json.dumps(self.scaffolds))
        html_content = html_content.replace("ITER_DATA_PLACEHOLDER", json.dumps(self.iterations))

        output_file = self.report_dir / "CtgLinker_Report.html"

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        return output_file

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate visualization report for CtgLinker")
    parser.add_argument("--out", required=True, help="CtgLinker output directory")
    args = parser.parse_args()
    
    visualizer = CtgLinkerVisualizer(args.out)
    report_path = visualizer.generate_report()
    print(f"Report generated: {report_path}")
