#!/usr/bin/env python3
"""
Job Manager for DEGAPv2
Creates working directories for each gap and manages parallel gap filling jobs

Author: DEGAPv2 Team
"""

import os
import sys
import json
import subprocess
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed


class JobManager:
    """管理 gap filling 的工作目录和并行任务"""

    def __init__(self, output_dir, degap_params=None):
        """
        初始化 Job Manager

        Args:
            output_dir: 主输出目录
            degap_params: DEGAP.py 的参数字典
        """
        # 主输出目录
        self.main_output_dir = Path(output_dir)

        # Gap filling 工作目录保存到 03.gap_filling/ 子目录
        self.output_dir = self.main_output_dir / "03.gap_filling"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 读取预处理配置
        self.preprocessing_dir = self.main_output_dir / "01.reads_preprocessor"
        if not self.preprocessing_dir.exists():
            raise FileNotFoundError(
                f"Preprocessing directory not found: {self.preprocessing_dir}\n"
                f"Please run reads_preprocessor.py first!"
            )

        # 读取 gap 检测配置
        self.gap_detection_dir = self.main_output_dir / "02.gap_detection"
        self.gap_detection_config_file = self.gap_detection_dir / "gap_detection_config.json"
        if not self.gap_detection_config_file.exists():
            raise FileNotFoundError(
                f"Gap detection config not found: {self.gap_detection_config_file}\n"
                f"Please run gap_detector.py first!"
            )

        # 读取 gap 检测配置
        with open(self.gap_detection_config_file, 'r') as f:
            self.gap_config = json.load(f)

        # gapData 目录（最终 gaps 的 flanking sequences）
        self.gap_data_dir = Path(self.gap_config['gap_data_dir'])

        # DEGAP.py 参数
        self.degap_params = degap_params or {}

        # DEGAP.py 脚本路径（假设在同一目录）
        self.degap_script = Path(__file__).parent / "DEGAP.py"

        # 存储创建的工作目录
        self.job_dirs = []
    
    def setup_jobs(self):
        """
        为所有 gaps 创建工作目录
        
        Returns:
            dict: 包含创建的工作目录信息
        """
        print(f"\n{'='*60}")
        print(f"Job Manager - Setting up gap filling jobs")
        print(f"{'='*60}\n")
        
        print(f"[1/3] Reading gap information...")
        gaps_by_chromosome = self.gap_config.get('gaps_by_chromosome', {})
        total_gaps = sum(info['count'] for info in gaps_by_chromosome.values())
        print(f"  Total gaps to process: {total_gaps}")
        print(f"  Chromosomes: {len(gaps_by_chromosome)}")
        
        print(f"\n[2/3] Creating working directories...")
        self._create_working_directories(gaps_by_chromosome)
        
        print(f"\n[3/3] Saving job configuration...")
        self._save_config()
        
        print(f"\n{'='*60}")
        print(f"Job setup completed successfully!")
        print(f"{'='*60}\n")
        print(f"  Total working directories created: {len(self.job_dirs)}")
        print(f"  Output directory: {self.output_dir}")
        
        return {
            'output_dir': str(self.output_dir),
            'total_jobs': len(self.job_dirs),
            'job_dirs': self.job_dirs
        }
    
    def _create_working_directories(self, gaps_by_chromosome):
        """为每个 gap 创建工作目录"""
        total_created = 0
        
        for chrom, info in gaps_by_chromosome.items():
            print(f"\n  Chromosome {chrom}: {info['count']} gaps")
            
            for gap in info['gaps']:
                gap_id = gap['id']
                
                # 为每个 gap 创建两个方向的工作目录
                for direction in ['left', 'right']:
                    job_name = f"{chrom}.{gap_id}.{direction}"
                    job_dir = self.output_dir / job_name
                    
                    # 创建工作目录
                    job_dir.mkdir(parents=True, exist_ok=True)
                    
                    # 软链接 01.reads_preprocessor/ 下的所有内容（除了 preprocessing_config.json）
                    self._create_symlinks(job_dir)
                    
                    # 复制 flanking sequences
                    self._copy_flanking_sequences(job_dir, chrom, gap_id)

                    # 生成 run.sh 脚本
                    self._generate_run_script(job_dir, direction)
                    
                    # 记录工作目录
                    self.job_dirs.append({
                        'job_name': job_name,
                        'job_dir': str(job_dir.resolve()),
                        'chromosome': chrom,
                        'gap_id': gap_id,
                        'direction': direction,
                        'gap_info': gap
                    })
                    
                    total_created += 1
            
            print(f"    Created {info['count'] * 2} working directories")
        
        print(f"\n  Total working directories created: {total_created}")
    
    def _create_symlinks(self, job_dir):
        """
        在工作目录中创建软链接到 01.reads_preprocessor/ 的内容
        
        Args:
            job_dir: gap 工作目录
        """
        # 遍历 01.reads_preprocessor/ 下的所有文件和目录
        for item in self.preprocessing_dir.iterdir():
            # 跳过 preprocessing_config.json
            if item.name == 'preprocessing_config.json':
                continue
            
            # 目标软链接路径
            target_path = job_dir / item.name
            
            # 如果已存在，跳过
            if target_path.exists() or target_path.is_symlink():
                continue
            
            # 创建软链接（使用绝对路径）
            try:
                target_path.symlink_to(item.resolve())
            except Exception as e:
                print(f"    Warning: Failed to create symlink {target_path}: {e}")
    
    def _copy_flanking_sequences(self, job_dir, chrom, gap_id):
        """
        复制 flanking sequences 到工作目录

        Args:
            job_dir: gap 工作目录
            chrom: 染色体名称
            gap_id: gap 编号
        """
        # 左侧序列
        left_source = self.gap_data_dir / f"{chrom}.{gap_id}.left.fasta"
        left_target = job_dir / "seqleft.fasta"
        if left_source.exists() and not left_target.exists():
            import shutil
            shutil.copy2(left_source, left_target)

        # 右侧序列
        right_source = self.gap_data_dir / f"{chrom}.{gap_id}.right.fasta"
        right_target = job_dir / "seqright.fasta"
        if right_source.exists() and not right_target.exists():
            import shutil
            shutil.copy2(right_source, right_target)

    def _generate_run_script(self, job_dir, direction):
        """
        生成 run.sh 脚本

        Args:
            job_dir: gap 工作目录
            direction: 延伸方向（left/right）
        """
        run_script = job_dir / "run.sh"

        # 构建命令
        cmd_parts = [
            "#!/bin/bash",
            "",
            f"python {self.degap_script.resolve()} \\",
            "    --mode gapfiller \\",
            f"    --out {job_dir.resolve()} \\",
            f"    --seqleft {(job_dir / 'seqleft.fasta').resolve()} \\",
            f"    --seqright {(job_dir / 'seqright.fasta').resolve()} \\",
        ]

        # 添加必需的 reads 参数（支持多文件）
        if 'hifi' in self.degap_params and self.degap_params['hifi']:
            hifi_value = self.degap_params['hifi']
            if isinstance(hifi_value, (list, tuple)):
                hifi_paths = " ".join(str(Path(p).resolve()) for p in hifi_value)
            else:
                hifi_paths = str(Path(hifi_value).resolve())
            cmd_parts.append(f"    --hifi {hifi_paths} \\")

        if 'ont' in self.degap_params and self.degap_params['ont']:
            ont_value = self.degap_params['ont']
            if isinstance(ont_value, (list, tuple)):
                ont_paths = " ".join(str(Path(p).resolve()) for p in ont_value)
            else:
                ont_paths = str(Path(ont_value).resolve())
            cmd_parts.append(f"    --ont {ont_paths} \\")

        # 添加 --flag 参数（根据工作目录的方向自动设置）
        cmd_parts.append(f"    --flag {direction} \\")

        # 添加可选参数（只有用户指定了才添加，排除 flag）
        # NOTE: 不传递 filterDepthHifi/Ont 参数，因为深度过滤已在 Part1 统一完成
        optional_params = {
            'thread': '-t',
            'remove': '--remove',
            'edge': '--edge',
            # 'filterDepthHifi': '--filterDepthHifi',  # 已在 Part1 完成，不再传递
            # 'filterDepthOnt': '--filterDepthOnt',    # 已在 Part1 完成，不再传递
            'MaximumExtensionLength': '--MaximumExtensionLength',
            'MaximumExtensionRound': '--MaximumExtensionRound',
            'kmer_size': '--kmer_size',
            'kmer_num': '--kmer_num'
            # Note: -j parameter removed, parallel control unified under -t parameter
        }

        for param_key, param_flag in optional_params.items():
            if param_key in self.degap_params and self.degap_params[param_key] is not None:
                cmd_parts.append(f"    {param_flag} {self.degap_params[param_key]} \\")

        # 添加布尔型参数
        if self.degap_params.get('kmer_filter', False):
            cmd_parts.append(f"    --kmer_filter \\")

        # 移除最后一行的反斜杠
        if cmd_parts[-1].endswith(" \\"):
            cmd_parts[-1] = cmd_parts[-1][:-2]

        # 写入文件
        with open(run_script, 'w') as f:
            f.write('\n'.join(cmd_parts))
            f.write('\n')

        # 添加执行权限
        run_script.chmod(0o755)
    
    def _save_config(self):
        """保存 job 配置到 JSON 文件（使用绝对路径）"""
        config = {
            'output_dir': str(self.output_dir.resolve()),
            'preprocessing_dir': str(self.preprocessing_dir.resolve()),
            'gap_detection_dir': str(self.gap_detection_dir.resolve()),
            'gap_data_dir': str(self.gap_data_dir.resolve()),
            'total_jobs': len(self.job_dirs),
            'jobs': self.job_dirs
        }
        
        config_file = self.output_dir / 'job_manager_config.json'
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"  Configuration saved: {config_file}")


class GapFillingAnalyzer:
    """分析 gap filling 结果并生成统计信息"""

    def __init__(self, main_output_dir):
        """
        初始化 GapFillingAnalyzer

        Args:
            main_output_dir: 主输出目录
        """
        self.main_output_dir = Path(main_output_dir)
        self.output_dir = self.main_output_dir / "03.gap_filling"
        self.results = []

    def analyze_all_gaps(self, jobs, execution_results=None):
        """
        分析所有 gap 的填充结果

        Args:
            jobs: job 配置列表（来自 job_manager_config.json）
            execution_results: 执行结果映射 {job_name: 'completed'/'failed'/'skipped'}

        Returns:
            list: 每个 gap 的统计信息
        """
        print(f"\n{'='*60}")
        print("Analyzing gap filling results...")
        print(f"{'='*60}")

        # 如果没有提供执行结果，使用空字典
        if execution_results is None:
            execution_results = {}

        # 按 gap 分组（合并 left 和 right）
        gaps_dict = {}
        for job in jobs:
            gap_key = f"{job['chromosome']}.{job['gap_id']}"
            if gap_key not in gaps_dict:
                gaps_dict[gap_key] = {
                    'chromosome': job['chromosome'],
                    'gap_id': job['gap_id'],
                    'gap_info': job['gap_info'],
                    'left': None,
                    'right': None
                }

            direction = job['direction']
            gaps_dict[gap_key][direction] = {
                'job_dir': Path(job['job_dir']),
                'job_name': job['job_name'],
                'execution_status': execution_results.get(job['job_name'], 'unknown')
            }

        # 分析每个 gap
        total = len(gaps_dict)
        for idx, (gap_key, gap_data) in enumerate(gaps_dict.items(), 1):
            print(f"  Analyzing gap {idx}/{total}: {gap_key}", end='\r')
            result = self._analyze_single_gap(gap_data)
            self.results.append(result)

        print(f"  Analyzed {total} gaps" + " " * 30)
        return self.results

    def _analyze_single_gap(self, gap_data):
        """
        分析单个 gap 的填充结果

        Returns:
            dict: gap 的统计信息
        """
        # 检查 left 和 right 方向
        left_result = self._analyze_direction(gap_data['left']) if gap_data['left'] else None
        right_result = self._analyze_direction(gap_data['right']) if gap_data['right'] else None

        # 确定最终结果（优先使用成功的方向）
        if left_result and left_result['filled']:
            final_result = left_result
            final_result['fill_direction'] = 'left'
        elif right_result and right_result['filled']:
            final_result = right_result
            final_result['fill_direction'] = 'right'
        else:
            # 都失败，使用 left 的结果（如果有）
            final_result = left_result or right_result or {
                'filled': False,
                'fill_type': 'unfilled',
                'fill_length': 0,
                'rounds': 0,
                'final_sequence_file': ''
            }
            final_result['fill_direction'] = 'none'

        # 计算完整的替换区域（seqleft + gap + seqright）
        gap_info = gap_data['gap_info']
        gap_start = gap_info['start']  # gap 起始位置（0-based）
        gap_end = gap_info['end']      # gap 结束位置（0-based）
        left_len = gap_info['left_len']  # seqleft 长度
        right_len = gap_info['right_len']  # seqright 长度

        # 替换区域的起始和结束位置（包含 seqleft 和 seqright）
        # seqleft 的起始位置 = gap_start - left_len
        # seqright 的结束位置 = gap_end + right_len
        replace_start = gap_start - left_len
        replace_end = gap_end + right_len

        # 组合结果
        return {
            'chromosome': gap_data['chromosome'],
            'gap_id': gap_data['gap_id'],
            'gap_start': gap_start,
            'gap_end': gap_end,
            'gap_len': gap_info['gap_len'],
            'left_flank_len': left_len,
            'right_flank_len': right_len,
            'replace_start': replace_start,
            'replace_end': replace_end,
            'replace_len': replace_end - replace_start + 1,
            'filled': final_result['filled'],
            'fill_type': final_result['fill_type'],
            'fill_direction': final_result['fill_direction'],
            'fill_length': final_result['fill_length'],
            'rounds': final_result['rounds'],
            'final_sequence_file': final_result.get('final_sequence_file', ''),
            'left_status': left_result['status'] if left_result else 'not_executed',
            'right_status': right_result['status'] if right_result else 'not_executed'
        }

    def _analyze_direction(self, direction_data):
        """
        分析单个方向的结果

        Returns:
            dict: 方向的统计信息
        """
        job_dir = direction_data['job_dir']
        execution_status = direction_data.get('execution_status', 'unknown')
        process_log = job_dir / 'process.log'

        # 如果任务被跳过，直接返回
        if execution_status == 'skipped':
            return {
                'filled': False,
                'fill_type': 'skipped',
                'fill_length': 0,
                'rounds': 0,
                'final_sequence_file': '',
                'status': 'skipped'
            }

        if not process_log.exists():
            return {
                'filled': False,
                'fill_type': 'unfilled',
                'fill_length': 0,
                'rounds': 0,
                'final_sequence_file': '',
                'status': 'no_log'
            }

        # 读取 process.log
        try:
            with open(process_log, 'r', encoding='utf-8') as f:
                log_content = f.read()
        except Exception as e:
            print(f"  Warning: Error reading {process_log}: {e}")
            return {
                'filled': False,
                'fill_type': 'unfilled',
                'fill_length': 0,
                'rounds': 0,
                'final_sequence_file': '',
                'status': 'error'
            }

        # 判断填充类型
        extension_success = ("GAP can be closed!" in log_content and
                            "Reach the maximum Length" not in log_content)
        direct_connection_success = "Decided to use direct connection result" in log_content

        if extension_success and not direct_connection_success:
            # Extension 成功
            return self._parse_extension_result(job_dir, log_content)
        elif direct_connection_success:
            # Direct Connection 成功
            return self._parse_direct_connection_result(job_dir, log_content)
        else:
            # 失败
            return {
                'filled': False,
                'fill_type': 'unfilled',
                'fill_length': 0,
                'rounds': self._count_rounds(log_content),
                'final_sequence_file': '',
                'status': 'failed'
            }

    def _parse_extension_result(self, job_dir, log_content):
        """解析 Extension 成功的结果"""
        import re

        # 提取轮次
        rounds = self._count_rounds(log_content)

        # 提取填补长度（最后一个 totalExtensionLength）
        extension_lengths = re.findall(r'totalExtensionLength:\s*(\d+)', log_content)
        fill_length = int(extension_lengths[-1]) if extension_lengths else 0

        # 查找 final.fa 文件
        final_files = list(job_dir.glob("*.final.fa"))
        # 排除 .direct.final.fa
        final_files = [f for f in final_files if '.direct.final.fa' not in str(f)]
        final_file = str(final_files[0].resolve()) if final_files else ''

        return {
            'filled': True,
            'fill_type': 'extension',
            'fill_length': fill_length,
            'rounds': rounds,
            'final_sequence_file': final_file,
            'status': 'success'
        }

    def _parse_direct_connection_result(self, job_dir, log_content):
        """解析 Direct Connection 成功的结果"""
        import re

        # 提取轮次（Direct Connection 也会尝试 Extension）
        rounds = self._count_rounds(log_content)

        # 提取 overlap length
        overlap_match = re.search(r'Overlap length:\s*(\d+)', log_content)
        fill_length = int(overlap_match.group(1)) if overlap_match else 0

        # 查找 direct.final.fa 文件
        direct_files = list(job_dir.glob("*.direct.final.fa"))
        final_file = str(direct_files[0].resolve()) if direct_files else ''

        return {
            'filled': True,
            'fill_type': 'direct_connection',
            'fill_length': fill_length,
            'rounds': rounds,
            'final_sequence_file': final_file,
            'status': 'success'
        }

    def _count_rounds(self, log_content):
        """统计轮次数"""
        import re
        rounds = re.findall(r'ExtensionRound\s+(\d+)', log_content)
        return int(rounds[-1]) if rounds else 0

    def save_to_json(self, output_file):
        """保存统计结果到 JSON 文件"""
        import json

        # 生成统计摘要
        total_gaps = len(self.results)
        filled_gaps = sum(1 for r in self.results if r['filled'])
        extension_filled = sum(1 for r in self.results if r['fill_type'] == 'extension')
        direct_connection_filled = sum(1 for r in self.results if r['fill_type'] == 'direct_connection')

        output_data = {
            'summary': {
                'total_gaps': total_gaps,
                'filled_gaps': filled_gaps,
                'unfilled_gaps': total_gaps - filled_gaps,
                'fill_rate': f"{filled_gaps / total_gaps * 100:.2f}%" if total_gaps > 0 else "0.00%",
                'extension_filled': extension_filled,
                'direct_connection_filled': direct_connection_filled
            },
            'gaps': self.results
        }

        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)

        print(f"\n{'='*60}")
        print(f"Gap Filling Statistics:")
        print(f"{'='*60}")
        print(f"  Total gaps: {total_gaps}")
        if total_gaps > 0:
            print(f"  Filled gaps: {filled_gaps} ({filled_gaps / total_gaps * 100:.2f}%)")
        else:
            print(f"  Filled gaps: 0 (0.00%)")
        print(f"    - Extension: {extension_filled}")
        print(f"    - Direct Connection: {direct_connection_filled}")
        print(f"  Unfilled gaps: {total_gaps - filled_gaps}")
        print(f"  Results saved to: {output_file}")
        print(f"{'='*60}\n")

        return output_data


class JobExecutor:
    """执行 gap filling 任务的并行管理器"""

    def __init__(self, output_dir, workers=4):
        """
        初始化任务执行器

        Args:
            output_dir: 主输出目录
            workers: 最大并行任务数
        """
        self.main_output_dir = Path(output_dir)
        self.gap_filling_dir = self.main_output_dir / "03.gap_filling"
        self.workers = workers

        # 读取 job 配置
        config_file = self.gap_filling_dir / "job_manager_config.json"
        if not config_file.exists():
            raise FileNotFoundError(
                f"Job config not found: {config_file}\n"
                f"Please run job setup first!"
            )

        with open(config_file, 'r') as f:
            self.job_config = json.load(f)

        # 待执行任务列表
        self.job_list = []

        # 已完成任务
        self.completed_jobs = []

        # 失败任务
        self.failed_jobs = []

        # 跳过的任务
        self.skipped_jobs = []

    def _collect_jobs(self):
        """收集所有待执行的 gapfiller 任务到内存"""
        print(f"\n{'='*60}")
        print(f"Collecting gap filling jobs...")
        print(f"{'='*60}\n")

        all_jobs = self.job_config.get('jobs', [])

        # 按照 chromosome, gap_id, direction 组织任务
        jobs_by_gap = {}
        for job in all_jobs:
            chrom = job['chromosome']
            gap_id = job['gap_id']
            direction = job['direction']

            key = f"{chrom}.{gap_id}"
            if key not in jobs_by_gap:
                jobs_by_gap[key] = {}

            jobs_by_gap[key][direction] = job

        # 构建任务列表：优先 left，然后 right
        for gap_key in sorted(jobs_by_gap.keys()):
            gap_jobs = jobs_by_gap[gap_key]

            # 先添加 left 任务
            if 'left' in gap_jobs:
                left_job = gap_jobs['left']
                # 检查是否已经完成
                if not self._is_job_completed(left_job):
                    self.job_list.append({
                        'job': left_job,
                        'gap_key': gap_key,
                        'has_right': 'right' in gap_jobs,
                        'right_job': gap_jobs.get('right')
                    })

            # 再添加 right 任务
            if 'right' in gap_jobs:
                right_job = gap_jobs['right']
                # 检查是否已经完成或被标记跳过
                if not self._is_job_completed(right_job) and not self._is_job_skipped(right_job):
                    self.job_list.append({
                        'job': right_job,
                        'gap_key': gap_key,
                        'has_right': False,
                        'right_job': None
                    })

        print(f"  Total jobs collected: {len(self.job_list)}")
        print(f"  Maximum parallel workers: {self.workers}")

        return len(self.job_list)

    def _is_job_completed(self, job):
        """
        检查任务是否已完成

        Args:
            job: 任务信息字典

        Returns:
            bool: 任务是否完成
        """
        job_dir = Path(job['job_dir'])
        return self._check_job_success(job_dir)

    def _is_job_skipped(self, job):
        """
        检查任务是否被标记为跳过

        Args:
            job: 任务信息字典

        Returns:
            bool: 任务是否被跳过
        """
        job_dir = Path(job['job_dir'])
        skip_marker = job_dir / ".skip_right"
        return skip_marker.exists()

    def _mark_right_job_skipped(self, gap_key):
        """
        标记 right 任务为跳过（当 left 任务成功时）

        Args:
            gap_key: gap 的唯一标识（例如：chr1A_TA299.1）
        """
        # 查找对应的 right 任务
        for job_info in self.job_list:
            if job_info['gap_key'] == gap_key and job_info['job']['direction'] == 'right':
                right_job_dir = Path(job_info['job']['job_dir'])
                skip_marker = right_job_dir / ".skip_right"

                # 创建跳过标记文件
                skip_marker.touch()
                print(f"  Marked right job as skipped: {right_job_dir.name}")

                # 从任务列表中移除
                self.job_list.remove(job_info)
                print(f"  Removed right job from job list")
                break

    def _run_single_job(self, job_info):
        """
        执行单个 gapfiller 任务

        注意：此方法在子进程中执行，不应使用 print()，
        所有信息通过返回值传递给主进程

        Args:
            job_info: 任务信息字典

        Returns:
            dict: 执行结果
        """
        job = job_info['job']
        job_dir = Path(job['job_dir'])
        job_name = job['job_name']
        run_script = job_dir / "run.sh"

        start_time = time.time()

        try:
            # 执行 run.sh
            result = subprocess.run(
                ['bash', str(run_script)],
                cwd=str(job_dir),
                capture_output=True,
                text=True,
                timeout=None  # 不设置超时
            )

            elapsed_time = time.time() - start_time

            # 保存 stdout 和 stderr 到日志文件
            stdout_log = job_dir / "run.stdout.log"
            stderr_log = job_dir / "run.stderr.log"

            with open(stdout_log, 'w') as f:
                f.write(result.stdout if result.stdout else "")

            with open(stderr_log, 'w') as f:
                f.write(result.stderr if result.stderr else "")

            # 检查退出码
            if result.returncode != 0:
                error_msg = f"Exit code: {result.returncode}"
                if result.stderr:
                    error_msg += f"\nStderr: {result.stderr[:500]}"  # 只显示前500字符

                return {
                    'job_name': job_name,
                    'status': 'failed',
                    'elapsed_time': elapsed_time,
                    'job_dir': str(job_dir),
                    'error': error_msg,
                    'exit_code': result.returncode
                }

            # 检查是否成功（通过 process.log 判断）
            success = self._check_job_success(job_dir)

            if success:
                return {
                    'job_name': job_name,
                    'status': 'success',
                    'elapsed_time': elapsed_time,
                    'job_dir': str(job_dir)
                }
            else:
                return {
                    'job_name': job_name,
                    'status': 'failed',
                    'elapsed_time': elapsed_time,
                    'job_dir': str(job_dir),
                    'error': 'Job execution completed but did not produce expected results'
                }

        except subprocess.TimeoutExpired:
            elapsed_time = time.time() - start_time
            return {
                'job_name': job_name,
                'status': 'timeout',
                'elapsed_time': elapsed_time,
                'job_dir': str(job_dir),
                'error': 'Job execution timeout'
            }

        except Exception as e:
            elapsed_time = time.time() - start_time
            return {
                'job_name': job_name,
                'status': 'error',
                'elapsed_time': elapsed_time,
                'job_dir': str(job_dir),
                'error': str(e)
            }

    def _check_job_success(self, job_dir):
        """
        检查任务是否成功

        判断标准：
        1. process.log 文件存在
        2. 满足以下任一条件：
           a) process.log 中包含 "GAP can be closed!" 且不包含 "Reach the maximum Length"
           b) process.log 中包含 "Decided to use direct connection result"
        3. 存在非空的 .final.fa 或 .direct.final.fa 文件

        Args:
            job_dir: 任务工作目录

        Returns:
            bool: 任务是否成功
        """
        job_dir = Path(job_dir)

        # 检查 process.log 是否存在
        process_log = job_dir / "process.log"
        if not process_log.exists():
            return False

        # 读取 process.log 内容
        try:
            with open(process_log, 'r') as f:
                log_content = f.read()

            # 检查成功标记
            # 方式1：Extension 成功
            extension_success = ("GAP can be closed!" in log_content and
                                "Reach the maximum Length" not in log_content)

            # 方式2：Direct Connection 成功
            direct_connection_success = "Decided to use direct connection result" in log_content

            # 任一方式成功即可
            if not (extension_success or direct_connection_success):
                return False

            # 检查是否存在 final.fa 文件
            final_files = list(job_dir.glob("*.final.fa"))
            if not final_files:
                return False

            # 检查 final.fa 文件是否为空
            for final_file in final_files:
                if final_file.stat().st_size > 0:
                    return True

            return False

        except Exception as e:
            # 不在子进程中打印，将错误信息通过返回值传递
            # 这里只是返回 False，表示检查失败
            return False

    def execute_jobs(self):
        """
        执行所有 gap filling 任务（使用并行处理）

        执行策略：
        - 对于同一个 gap，必须先完成 left 任务，才能提交 right 任务
        - 使用 --workers 控制最大并行数

        Returns:
            dict: 执行结果统计
        """
        print(f"\n{'='*60}")
        print(f"Executing gap filling jobs")
        print(f"{'='*60}\n")

        # 收集任务
        total_jobs = self._collect_jobs()

        if total_jobs == 0:
            print("\nNo jobs to execute!")
            return {
                'total_jobs': 0,
                'completed': 0,
                'failed': 0,
                'skipped': 0
            }

        print(f"\n{'='*60}")
        print(f"Starting parallel execution (workers={self.workers})")
        print(f"Strategy: For each gap, LEFT must complete before RIGHT can start")
        print(f"{'='*60}\n")

        # 按 gap 组织任务
        jobs_by_gap = {}
        for job_info in self.job_list:
            gap_key = job_info['gap_key']
            direction = job_info['job']['direction']

            if gap_key not in jobs_by_gap:
                jobs_by_gap[gap_key] = {}

            jobs_by_gap[gap_key][direction] = job_info

        # 使用 ProcessPoolExecutor 并行执行
        with ProcessPoolExecutor(max_workers=self.workers) as executor:
            # 跟踪每个 gap 的状态
            gap_status = {}  # gap_key -> {'left_done': bool, 'left_success': bool}

            # 活跃的 futures
            active_futures = {}  # future -> job_info

            # 待提交的 right 任务队列
            pending_right_jobs = {}  # gap_key -> job_info

            # 初始化：提交所有 left 任务
            print(f"\n{'='*60}")
            print(f"Submitting initial LEFT tasks...")
            print(f"{'='*60}\n")

            for gap_key, gap_jobs in jobs_by_gap.items():
                gap_status[gap_key] = {'left_done': False, 'left_success': False}

                if 'left' in gap_jobs:
                    # 有 left 任务，提交执行
                    job_info = gap_jobs['left']
                    print(f"  → Submitting: {job_info['job']['job_name']}")
                    future = executor.submit(self._run_single_job, job_info)
                    active_futures[future] = job_info

                    # 如果有 right 任务，记录到待提交队列
                    if 'right' in gap_jobs:
                        pending_right_jobs[gap_key] = gap_jobs['right']
                else:
                    # 没有 left 任务，标记为已完成（失败）
                    gap_status[gap_key]['left_done'] = True
                    gap_status[gap_key]['left_success'] = False

                    # 如果有 right 任务，直接提交（因为没有 left）
                    if 'right' in gap_jobs:
                        job_info = gap_jobs['right']
                        print(f"  → Submitting: {job_info['job']['job_name']} (no LEFT task)")
                        future = executor.submit(self._run_single_job, job_info)
                        active_futures[future] = job_info

            print(f"\n{'='*60}")
            print(f"Waiting for tasks to complete...")
            print(f"{'='*60}\n")

            # 处理任务完成（使用 as_completed 高效等待）
            while active_futures:
                # 使用 as_completed 等待任意一个任务完成
                # 注意：需要复制 keys，因为在迭代过程中会修改 active_futures
                current_futures = list(active_futures.keys())

                # 等待至少一个任务完成
                for future in as_completed(current_futures):
                    # 检查这个 future 是否还在 active_futures 中
                    # （可能已经被之前的迭代处理过了）
                    if future not in active_futures:
                        continue

                    job_info = active_futures.pop(future)
                    gap_key = job_info['gap_key']
                    direction = job_info['job']['direction']

                    try:
                        result = future.result()

                        # 打印任务完成信息（在主进程中）
                        if result['status'] == 'success':
                            print(f"  ✓ [Success] {result['job_name']} (elapsed: {result['elapsed_time']:.1f}s)")
                            self.completed_jobs.append(result)
                        elif result['status'] == 'failed':
                            error_info = result.get('error', 'Unknown error')
                            # 只显示错误信息的第一行
                            error_first_line = error_info.split('\n')[0]
                            print(f"  ✗ [Failed] {result['job_name']} (elapsed: {result['elapsed_time']:.1f}s) - {error_first_line}")
                            self.failed_jobs.append(result)
                        else:
                            # timeout, error, etc.
                            print(f"  ✗ [{result['status'].upper()}] {result['job_name']} - {result.get('error', 'Unknown error')}")
                            self.failed_jobs.append(result)

                        # 如果是 left 任务完成
                        if direction == 'left':
                            gap_status[gap_key]['left_done'] = True
                            gap_status[gap_key]['left_success'] = (result['status'] == 'success')

                            # 决定是否提交 right 任务
                            if gap_key in pending_right_jobs:
                                right_job_info = pending_right_jobs.pop(gap_key)

                                if result['status'] == 'success':
                                    # left 成功，跳过 right，记录到 skipped_jobs
                                    print(f"  ⊘ [Skipped] {right_job_info['job']['job_name']} (LEFT succeeded)")
                                    self.skipped_jobs.append({
                                        'job_name': right_job_info['job']['job_name'],
                                        'status': 'skipped',
                                        'elapsed_time': 0,
                                        'job_dir': right_job_info['job']['job_dir'],
                                        'reason': 'LEFT task succeeded'
                                    })
                                else:
                                    # left 失败，提交 right
                                    print(f"  → Submitting: {right_job_info['job']['job_name']} (LEFT failed)")
                                    right_future = executor.submit(self._run_single_job, right_job_info)
                                    active_futures[right_future] = right_job_info

                    except Exception as e:
                        print(f"  ✗ [Exception] {job_info['job']['job_name']}: {e}")
                        self.failed_jobs.append({
                            'job_name': job_info['job']['job_name'],
                            'status': 'exception',
                            'error': str(e)
                        })

                        # 如果是 left 任务异常，标记为失败并提交 right
                        if direction == 'left':
                            gap_status[gap_key]['left_done'] = True
                            gap_status[gap_key]['left_success'] = False

                            if gap_key in pending_right_jobs:
                                right_job_info = pending_right_jobs.pop(gap_key)
                                print(f"  → Submitting: {right_job_info['job']['job_name']} (LEFT exception)")
                                right_future = executor.submit(self._run_single_job, right_job_info)
                                active_futures[right_future] = right_job_info

                    # 只处理一个完成的任务后就跳出，重新检查 active_futures
                    break

        # 统计结果
        print(f"\n{'='*60}")
        print(f"Execution completed")
        print(f"{'='*60}\n")

        print(f"  Total jobs: {total_jobs}")
        print(f"  Completed: {len(self.completed_jobs)}")
        print(f"  Failed: {len(self.failed_jobs)}")
        print(f"  Skipped: {len(self.skipped_jobs)} (LEFT succeeded)")

        # 生成 gap filling 统计信息
        analyzer = GapFillingAnalyzer(self.main_output_dir)

        # 构建执行结果映射（job_name -> result）
        execution_results = {}
        for job in self.completed_jobs:
            execution_results[job['job_name']] = 'completed'
        for job in self.failed_jobs:
            execution_results[job['job_name']] = 'failed'
        for job in self.skipped_jobs:
            execution_results[job['job_name']] = 'skipped'

        analyzer.analyze_all_gaps(self.job_config.get('jobs', []), execution_results)

        # 保存统计结果到 JSON 文件
        results_file = self.gap_filling_dir / 'gap_filling_results.json'
        stats = analyzer.save_to_json(results_file)

        return {
            'total_jobs': total_jobs,
            'completed': len(self.completed_jobs),
            'failed': len(self.failed_jobs),
            'skipped': len(self.skipped_jobs),
            'completed_jobs': self.completed_jobs,
            'failed_jobs': self.failed_jobs,
            'skipped_jobs': self.skipped_jobs,
            'results_file': str(results_file),
            'gap_statistics': stats
        }


def main():
    """命令行接口"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Setup and execute gap filling jobs',
        epilog='''
Example:
  %(prog)s -o output --hifi hifi.fa --ont ont.fa --thread 30 --workers 4

Note: This script requires preprocessing and gap detection to be completed first.
      It will read configurations from:
      - output/01.reads_preprocessor/
      - output/02.gap_detection/gap_detection_config.json
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # 必需参数
    parser.add_argument('--output', '-o', required=True, help='Output directory')
    parser.add_argument('--hifi', nargs='+', help='HiFi reads file path(s) (FASTA/FASTQ format, multiple files supported)')
    parser.add_argument('--ont', nargs='+', help='ONT reads file path(s) (FASTA/FASTQ format, multiple files supported)')

    # 并行控制参数
    parser.add_argument('--work', '-w', type=int, default=1, help='Maximum parallel workers (default: 1)')

    # DEGAP.py 可选参数
    parser.add_argument('-t', '--thread', type=str, help='Number of threads (default: 20)')
    parser.add_argument('--remove', type=int, help='File cleanup level (1/2/3, default: 2)')
    parser.add_argument('--edge', type=int, help='Max edge length for misassembly detection (default: 500)')
    parser.add_argument('--filterDepthHifi', type=float,
                        help='Filter HiFi reads by mapped depth. '
                             'Example: 0.3 means keep reads with depth >= 0.3*avgdepth and depth <= (2-0.3)*avgdepth')
    parser.add_argument('--filterDepthOnt', type=float,
                        help='Filter ONT reads by mapped depth. '
                             'Example: 0.2 means keep reads with depth >= 0.2*avgdepth and depth <= (2-0.2)*avgdepth')
    parser.add_argument('--MaximumExtensionLength', type=int,
                        help='Maximum cumulative extension length in bp (default: None, no limit). '
                             'Extension stops when total extended length exceeds this value')
    parser.add_argument('--MaximumExtensionRound', type=int,
                        help='Maximum number of extension rounds (default: None, no limit). '
                             'Extension stops when round number exceeds this value. '
                             'Minimum recommended value is 5')
    parser.add_argument('--kmer_filter', action='store_true', help='Enable k-mer filtering')
    parser.add_argument('--kmer_size', '-ks', type=int, help='K-mer size for filtering (default: 41)')
    parser.add_argument('--kmer_num', '-kn', type=int, help='Number of k-mers for filtering (default: 20)')

    args = parser.parse_args()

    # 检查至少指定了 HiFi 或 ONT
    if not args.hifi and not args.ont:
        print("Error: Either --hifi or --ont (or both) must be specified")
        sys.exit(1)

    try:
        # 构建 DEGAP 参数字典
        # NOTE: 不包含 filterDepthHifi/Ont，因为深度过滤已在 Part1 统一完成
        degap_params = {
            'hifi': args.hifi,
            'ont': args.ont,
            'thread': args.thread,
            'remove': args.remove,
            'edge': args.edge,
            # 'filterDepthHifi': args.filterDepthHifi,  # 已在 Part1 完成，不再传递
            # 'filterDepthOnt': args.filterDepthOnt,    # 已在 Part1 完成，不再传递
            'MaximumExtensionLength': args.MaximumExtensionLength,
            'MaximumExtensionRound': args.MaximumExtensionRound,
            'kmer_filter': args.kmer_filter,
            'kmer_size': args.kmer_size,
            'kmer_num': args.kmer_num
            # Note: -j parameter removed, parallel control unified under -t parameter
        }

        # Step 1: Setup working directories
        print("\n" + "="*60)
        print("STEP 1: Setting up working directories")
        print("="*60)
        manager = JobManager(args.output, degap_params)
        setup_result = manager.setup_jobs()

        # Step 2: Execute gap filling jobs
        print("\n" + "="*60)
        print("STEP 2: Executing gap filling jobs")
        print("="*60)
        executor = JobExecutor(args.output, workers=args.work)
        exec_result = executor.execute_jobs()

        # Final summary
        print("\n" + "="*60)
        print("FINAL RESULT")
        print("="*60)
        print(f"\nSetup: {setup_result['total_jobs']} jobs created")
        print(f"Execution: {exec_result['completed']} completed, {exec_result['failed']} failed, {exec_result['skipped']} skipped")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

