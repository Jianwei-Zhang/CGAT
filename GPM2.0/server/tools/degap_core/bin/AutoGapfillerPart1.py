#!/usr/bin/env python3
"""
Reads Preprocessor Module for AutoGapfiller v3
功能：预处理 HiFi/ONT reads，包括格式转换、索引构建、统计生成
"""

import os
import sys
import subprocess
import math
from pathlib import Path
from Bio import SeqIO
import json


class ReadsPreprocessor:
    """Reads预处理器"""
    
    def __init__(self, output_dir, filterDepthHifi=None, filterDepthOnt=None):
        """
        初始化预处理器

        Args:
            output_dir: 输出目录路径（主输出目录）
            filterDepthHifi: HiFi reads 深度过滤参数 (float, 例如 0.3)
            filterDepthOnt: ONT reads 深度过滤参数 (float, 例如 0.2)
        """
        # 主输出目录
        self.main_output_dir = Path(output_dir)

        # 预处理结果保存到 01.reads_preprocessor/ 子目录
        self.output_dir = self.main_output_dir / "01.reads_preprocessor"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # processed_reads 目录
        self.processed_dir = self.output_dir / "processed_reads"
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        # 深度过滤参数
        self.filterDepthHifi = filterDepthHifi
        self.filterDepthOnt = filterDepthOnt

        # 存储处理结果
        self.hifi_fasta = None
        self.ont_fasta = None
        self.hifi_stats = {}
        self.ont_stats = {}
        self.data_type = None
    
    def process(self, hifi_reads=None, ont_reads=None):
        """
        处理reads文件

        Args:
            hifi_reads: HiFi reads文件路径 (FASTA/FASTQ，支持 .fa/.fasta/.fq/.fastq 及 .gz 压缩)
            ont_reads: ONT reads文件路径 (FASTA/FASTQ，支持 .fa/.fasta/.fq/.fastq 及 .gz 压缩)

        Returns:
            dict: 包含处理结果的字典
        """
        if not hifi_reads and not ont_reads:
            raise ValueError("At least one of hifi_reads or ont_reads must be provided")

        # 检查是否已存在 preprocessing_config.json
        config_file = self.output_dir / "preprocessing_config.json"
        if config_file.exists() and config_file.stat().st_size > 0:
            print(f"\n{'='*60}")
            print(f"Reads Preprocessing - SKIPPED")
            print(f"{'='*60}\n")
            print(f"✅ Found existing preprocessing config: {config_file}")
            print(f"   Skipping reads preprocessing...")

            # 读取并返回已有配置
            with open(config_file, 'r') as f:
                config = json.load(f)

            return {
                'data_type': config.get('data_type'),
                'hifi_fasta': config.get('hifi_fasta'),
                'ont_fasta': config.get('ont_fasta'),
                'hifi_stats': config.get('hifi_stats', {}),
                'ont_stats': config.get('ont_stats', {}),
                'output_dir': str(self.output_dir),
                'processed_dir': str(self.processed_dir),
                'skipped': True
            }

        # 确定数据类型
        if hifi_reads and ont_reads:
            self.data_type = 'mixed'
        elif hifi_reads:
            self.data_type = 'hifi'
        else:
            self.data_type = 'ont'

        print(f"\n{'='*60}")
        print(f"Reads Preprocessing - Data Type: {self.data_type.upper()}")
        print(f"{'='*60}\n")

        # 处理 HiFi reads
        if hifi_reads:
            print("[1/5] Processing HiFi reads...")
            self.hifi_fasta = self._convert_to_fasta(hifi_reads, 'HiFi')

        # 处理 ONT reads
        if ont_reads:
            print("\n[2/5] Processing ONT reads...")
            self.ont_fasta = self._convert_to_fasta(ont_reads, 'ONT')

        # 深度过滤（可选，与 DEGAP.py 一致）
        print("\n[3/5] Depth filtering...")
        final_hifi_fasta, final_ont_fasta = self._apply_depth_filter()

        # 建立索引和生成统计（使用过滤后的文件）
        print("\n[4/5] Building index and generating statistics...")
        if final_hifi_fasta:
            self._build_index(final_hifi_fasta, 'HiFi')
            self.hifi_stats = self._generate_stats(final_hifi_fasta, 'HiFi')
        if final_ont_fasta:
            self._build_index(final_ont_fasta, 'ONT')
            self.ont_stats = self._generate_stats(final_ont_fasta, 'ONT')

        # 更新为最终文件路径
        self.hifi_fasta = final_hifi_fasta
        self.ont_fasta = final_ont_fasta

        # 分割 reads（默认总是执行，与 DEGAP.py 一致）
        print("\n[5/5] Splitting reads file...")
        if self.hifi_fasta:
            self._split_reads(self.hifi_fasta, 'hifi')
        if self.ont_fasta:
            self._split_reads(self.ont_fasta, 'ont')

        # 保存配置
        print("\nSaving preprocessing configuration...")
        self._save_config()

        # 返回结果
        result = {
            'data_type': self.data_type,
            'hifi_fasta': str(self.hifi_fasta) if self.hifi_fasta else None,
            'ont_fasta': str(self.ont_fasta) if self.ont_fasta else None,
            'hifi_stats': self.hifi_stats,
            'ont_stats': self.ont_stats,
            'seed_length': self._get_unified_seed_length(),
            'hifi_reads_part': str(self.output_dir / 'hifi_reads_part') if self.hifi_fasta else None,
            'ont_reads_part': str(self.output_dir / 'ont_reads_part') if self.ont_fasta else None
        }

        print(f"\n{'='*60}")
        print("Preprocessing completed successfully!")
        print(f"{'='*60}\n")

        return result
    
    def _convert_to_fasta(self, input_file, label):
        """
        将单个或多个输入 reads 文件统一转换/合并为 FASTA。
        使用 seqkit fq2fa 统一处理 FASTA/FASTQ（含 .gz），始终输出 FASTA。

        Args:
            input_file: 输入文件路径或路径列表
            label: 标签 ('HiFi' 或 'ONT')

        Returns:
            Path: FASTA文件路径（在processed_reads目录下）
        """
        # 统一输出文件名：hifi_reads.fa 或 ont_reads.fa（小写，.fa 扩展名）
        output_fa = self.processed_dir / f"{label.lower()}_reads.fa"

        # 规范输入为列表
        if isinstance(input_file, (list, tuple)):
            input_files = [str(p) for p in input_file if p]
        else:
            input_files = [str(input_file)] if input_file else []

        if not input_files:
            print(f"  ✗ Error: No {label} input files provided")
            sys.exit(1)

        resolved_inputs = []
        for f in input_files:
            p = Path(f).resolve()
            if not p.exists():
                print(f"  ✗ Error: {label} input file not found: {p}")
                sys.exit(1)

            lower = p.name.lower()
            supported = lower.endswith(('.fa', '.fasta', '.fna', '.fq', '.fastq',
                                        '.fa.gz', '.fasta.gz', '.fna.gz', '.fq.gz', '.fastq.gz'))
            if not supported:
                print(f"  ✗ Error: Unsupported file format: {p}")
                sys.exit(1)
            resolved_inputs.append(p)

        # 检查 FASTA 输出文件是否已存在
        if output_fa.exists():
            if output_fa.is_symlink() or output_fa.stat().st_size > 0:
                print(f"  ✓ Using existing FASTA file: {output_fa}")
                return output_fa
            print(f"  ⚠ Removing empty file: {output_fa}")
            output_fa.unlink()

        # 转换/合并到单一FASTA
        if len(resolved_inputs) == 1:
            print(f"  Converting {label} reads to FASTA")
            print(f"    Input:  {resolved_inputs[0]}")
        else:
            print(f"  Merging and converting {len(resolved_inputs)} {label} files to FASTA")
            for idx, p in enumerate(resolved_inputs, 1):
                print(f"    [{idx}] {p}")
        print(f"    Output: {output_fa}")

        try:
            # seqkit fq2fa handles FASTA/FASTQ and .gz, always outputs FASTA
            cmd = ['seqkit', 'fq2fa', '-o', str(output_fa)] + [str(p) for p in resolved_inputs]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"  ✓ FASTA ready: {output_fa}")
            return output_fa
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Error converting {label} reads to FASTA:")
            print(f"    {e.stderr}")
            sys.exit(1)
        except FileNotFoundError:
            print(f"  ✗ Error: seqkit not found. Please install seqkit:")
            print(f"    conda install -c bioconda seqkit")
            sys.exit(1)
    
    def _build_index(self, fasta_file, label):
        """
        构建FASTA索引（包括 .fai 和 .idx 两种格式）

        Args:
            fasta_file: FASTA文件路径
            label: 标签 ('HiFi' 或 'ONT')
        """
        # 1. 构建 samtools .fai 索引
        fai_index_file = Path(str(fasta_file) + '.fai')

        if fai_index_file.exists():
            print(f"  ✓ {label} .fai index already exists: {fai_index_file}")
        else:
            print(f"  Building {label} .fai index with samtools faidx...")

            try:
                cmd = ['samtools', 'faidx', str(fasta_file)]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                print(f"  ✓ .fai index created: {fai_index_file}")
            except subprocess.CalledProcessError as e:
                print(f"  ✗ Error building .fai index:")
                print(f"    {e.stderr}")
                sys.exit(1)
            except FileNotFoundError:
                print(f"  ✗ Error: samtools not found. Please install samtools:")
                print(f"    conda install -c bioconda samtools")
                sys.exit(1)

        # 2. 构建 BioPython .idx 索引（用于 DEGAP.py）
        # 索引文件保存在主输出目录下，与 DEGAP.py 保持一致
        if label == 'HiFi':
            idx_file = self.output_dir / 'hifi_reads.idx'
        else:  # ONT
            idx_file = self.output_dir / 'ont_reads.idx'

        if idx_file.exists() and idx_file.stat().st_size > 0:
            try:
                # 尝试加载已存在的索引
                test_dict = SeqIO.index_db(str(idx_file))
                if test_dict:
                    print(f"  ✓ {label} .idx index already exists and is valid: {idx_file}")
                    test_dict.close()
                    return
            except Exception as e:
                print(f"  ⚠ Existing .idx index is invalid ({e}), rebuilding...")

        print(f"  Building {label} .idx index with BioPython...")
        try:
            # 使用 SeqIO.index_db 创建索引
            readsdict = SeqIO.index_db(str(idx_file), str(fasta_file), 'fasta')
            readsdict.close()
            print(f"  ✓ .idx index created: {idx_file}")
        except Exception as e:
            print(f"  ✗ Error building .idx index: {e}")
            sys.exit(1)
    
    def _generate_stats(self, fasta_file, label):
        """
        生成reads统计信息
        
        Args:
            fasta_file: FASTA文件路径
            label: 标签 ('HiFi' 或 'ONT')
        
        Returns:
            dict: 统计信息字典
        """
        stats_file = self.output_dir / f"{label}.reads.stat"
        
        # 检查是否已存在
        if stats_file.exists() and stats_file.stat().st_size > 0:
            print(f"  ✓ {label} statistics file already exists: {stats_file}")
            return self._read_stats_file(stats_file)
        
        print(f"  Generating {label} statistics with seqkit stats...")
        
        try:
            # 运行 seqkit stats
            cmd = ['seqkit', 'stats', str(fasta_file), '-T']
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            # 解析输出
            lines = [l for l in result.stdout.strip().split('\n') if l.strip()]
            if len(lines) < 2:
                raise RuntimeError('seqkit stats returned no data')
            
            cols = lines[1].split('\t')
            if len(cols) < 8:
                raise RuntimeError('seqkit stats TSV columns insufficient')
            
            # 提取统计信息
            num_seqs = int(cols[3])
            sum_len = int(cols[4])
            min_len = int(cols[5])
            avg_len = float(cols[6])
            max_len = int(cols[7])

            # 计算 SeedLength（使用 DEGAP.py 的算法）
            # 算法：将 max_length 向上取整到下一个"整数倍"的数量级
            # 例如：25000 -> 35000, 150000 -> 250000
            a = 10**(int(math.log(max_len, 10))) if max_len > 0 else 1
            b = max_len / a + 1
            seed_len = int(a * b)
            
            stats = {
                'Number': num_seqs,
                'TolalLenth': sum_len,  # 保持拼写以兼容旧版
                'MinLength': min_len,
                'MeanLength': avg_len,
                'MaxLength': max_len,
                'SeedLength': seed_len
            }
            
            # 保存统计文件
            self._write_stats_file(stats_file, stats)
            
            print(f"  ✓ Statistics generated:")
            print(f"    Number:     {num_seqs:,}")
            print(f"    Total:      {sum_len:,} bp")
            print(f"    Mean:       {avg_len:.1f} bp")
            print(f"    Max:        {max_len:,} bp")
            print(f"    SeedLength: {seed_len:,} bp")
            
            return stats
            
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Error running seqkit stats:")
            print(f"    {e.stderr}")
            sys.exit(1)
        except Exception as e:
            print(f"  ✗ Error generating statistics: {e}")
            sys.exit(1)
    
    def _write_stats_file(self, stats_file, stats):
        """写入统计文件"""
        with open(stats_file, 'w') as f:
            for key, value in stats.items():
                f.write(f"{key}\t{value}\n")
    
    def _read_stats_file(self, stats_file):
        """读取统计文件"""
        stats = {}
        with open(stats_file, 'r') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) == 2:
                    key, value = parts
                    # 尝试转换为数字
                    try:
                        if '.' in value:
                            stats[key] = float(value)
                        else:
                            stats[key] = int(value)
                    except ValueError:
                        stats[key] = value
        return stats
    
    def _apply_depth_filter(self):
        """
        执行深度过滤（可选）
        与 DEGAP.py 的 STEP 2 逻辑一致

        Returns:
            tuple: (final_hifi_fasta, final_ont_fasta) 过滤后的文件路径
        """
        # 默认使用原始转换后的文件
        final_hifi = self.hifi_fasta
        final_ont = self.ont_fasta

        # 检查是否需要深度过滤
        filter_hifi = self.filterDepthHifi is not None
        filter_ont = self.filterDepthOnt is not None

        if not filter_hifi and not filter_ont:
            print("  Depth filtering disabled, using preprocessed files directly")
            if final_hifi:
                print(f"    HiFi: {final_hifi}")
            if final_ont:
                print(f"    ONT:  {final_ont}")
            return final_hifi, final_ont

        print("  Depth filtering enabled:")
        print(f"    HiFi: {'Yes' if filter_hifi else 'No'} (threshold={self.filterDepthHifi if filter_hifi else 'N/A'})")
        print(f"    ONT:  {'Yes' if filter_ont else 'No'} (threshold={self.filterDepthOnt if filter_ont else 'N/A'})")

        # 构建 selectRawReads 参数（临时参数列表）
        # 使用 gapfiller 模式的参数格式
        temp_param_list = [
            'gapfiller',                    # mode
            2,                              # remove
            '20',                           # thread
            str(self.hifi_fasta) if self.hifi_fasta else '',  # reads
            str(self.output_dir.parent),    # out (使用主输出目录)
            '',                             # seqleft (dummy)
            '',                             # seqright (dummy)
            'left',                         # flag
            500,                            # edge
            self.filterDepthHifi,           # filterDepthHifi
            self.filterDepthOnt,            # filterDepthOnt
            None,                           # MaximumExtensionLength
            None,                           # MaximumExtensionRound
            self.data_type,                 # data_type
            str(self.ont_fasta) if self.ont_fasta else None  # ont_reads
        ]

        # 临时 seedlen (在真正建立索引前，使用一个临时值)
        temp_seedlen = 10000

        try:
            # 导入 selectRawReads
            from selectRawReads import selectRawReads

            print("  Executing depth filtering...")
            selected_reads = selectRawReads(temp_param_list, temp_seedlen)

            # 更新过滤后的文件路径
            if filter_hifi:
                final_hifi = Path(selected_reads.readFile)
                print(f"  ✓ HiFi depth filtering completed: {final_hifi}")
            else:
                print(f"  ⊗ HiFi depth filtering skipped, using: {final_hifi}")

            if filter_ont and self.data_type == 'mixed':
                if hasattr(selected_reads, 'ont_readFile') and selected_reads.ont_readFile:
                    final_ont = Path(selected_reads.ont_readFile)
                    print(f"  ✓ ONT depth filtering completed: {final_ont}")
                else:
                    print("  ⚠ Warning: ONT filtering enabled but no filtered file generated")
            elif filter_ont and self.data_type == 'ont':
                # ONT-only模式，readFile 包含 ONT 数据
                final_hifi = Path(selected_reads.readFile)
                print(f"  ✓ ONT depth filtering completed: {final_hifi}")
            else:
                if self.data_type == 'mixed' and final_ont:
                    print(f"  ⊗ ONT depth filtering skipped, using: {final_ont}")

            print("  Depth filtering summary:")
            if final_hifi:
                print(f"    Final HiFi: {final_hifi}")
            if final_ont:
                print(f"    Final ONT:  {final_ont}")

        except ImportError as e:
            print(f"  ✗ Error: Failed to import selectRawReads module: {e}")
            print(f"  ⚠ Warning: Depth filtering skipped, using original files")
        except Exception as e:
            print(f"  ✗ Error during depth filtering: {e}")
            print(f"  ⚠ Warning: Depth filtering failed, using original files")
            import traceback
            traceback.print_exc()

        return final_hifi, final_ont

    def _get_unified_seed_length(self):
        """
        获取统一的SeedLength
        Mixed模式取HiFi和ONT中的较大值
        """
        if self.data_type == 'mixed':
            # Mixed模式：取HiFi和ONT中的较大值
            hifi_seed = self.hifi_stats.get('SeedLength', 10000)
            ont_seed = self.ont_stats.get('SeedLength', 10000)
            return max(hifi_seed, ont_seed)
        elif self.data_type == 'hifi':
            return self.hifi_stats.get('SeedLength', 10000)
        else:  # ont
            return self.ont_stats.get('SeedLength', 10000)
    
    def _split_reads(self, fasta_file, reads_type):
        """
        分割reads文件（用于k-mer过滤）

        Args:
            fasta_file: FASTA文件路径
            reads_type: 'hifi' 或 'ont'
        """
        # 确定输出目录
        split_dir = self.output_dir / f"{reads_type}_reads_part"

        # 检查是否已存在分割文件
        if split_dir.exists() and list(split_dir.glob('*.fa*')):
            split_files = list(split_dir.glob('*.fa*'))
            print(f"  ✓ Found {len(split_files)} existing {reads_type.upper()} split files, skipping")
            return

        # 创建输出目录
        split_dir.mkdir(parents=True, exist_ok=True)

        print(f"  Splitting {reads_type.upper()} reads into chunks (100,000 reads per file)...")
        print(f"    Input:  {fasta_file}")
        print(f"    Output: {split_dir}/")

        try:
            cmd = [
                'seqkit', 'split',
                str(fasta_file),
                '-O', str(split_dir),
                '--force',
                '--by-size', '100000',
                '--two-pass',
                '-w', '0'
            ]
            subprocess.run(cmd, check=True, capture_output=True, text=True)

            # 统计生成的文件数
            split_files = list(split_dir.glob('*.fa*'))
            print(f"  ✓ Splitting completed: {len(split_files)} files generated")

        except subprocess.CalledProcessError as e:
            print(f"  ✗ Error splitting {reads_type.upper()} reads:")
            print(f"    {e.stderr}")
            # 不退出，分割失败不应该阻止整个流程
            print(f"  ⚠ Warning: Continuing without split files")

    def _save_config(self):
        """保存预处理配置到JSON文件（使用绝对路径）"""
        config = {
            'data_type': self.data_type,
            'hifi_fasta': str(self.hifi_fasta.resolve()) if self.hifi_fasta else None,
            'ont_fasta': str(self.ont_fasta.resolve()) if self.ont_fasta else None,
            'hifi_stats': self.hifi_stats,
            'ont_stats': self.ont_stats,
            'seed_length': self._get_unified_seed_length(),
            'hifi_reads_part': str((self.output_dir / 'hifi_reads_part').resolve()) if self.hifi_fasta else None,
            'ont_reads_part': str((self.output_dir / 'ont_reads_part').resolve()) if self.ont_fasta else None,
            'output_dir': str(self.output_dir.resolve()),
            'processed_dir': str(self.processed_dir.resolve())
        }

        config_file = self.output_dir / 'preprocessing_config.json'
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)

        print(f"  ✓ Configuration saved: {config_file}")


def main():
    """命令行接口（用于测试）"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Preprocess reads for gap filling',
        epilog='''
Examples:
  # HiFi-only mode
  %(prog)s --hifi hifi_reads.fastq -o output

  # ONT-only mode
  %(prog)s --ont ont_reads.fastq -o output

  # Mixed mode (HiFi + ONT)
  %(prog)s --hifi hifi_reads.fastq --ont ont_reads.fastq -o output

Supported formats: .fa, .fasta, .fq, .fastq (with optional .gz compression)
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--hifi', nargs='+', help='HiFi reads file(s) (FASTA/FASTQ, .gz supported; multiple files supported)')
    parser.add_argument('--ont', nargs='+', help='ONT reads file(s) (FASTA/FASTQ, .gz supported; multiple files supported)')
    parser.add_argument('--output', '-o', required=True, help='Output directory')

    args = parser.parse_args()

    if not args.hifi and not args.ont:
        print("Error: At least one of --hifi or --ont must be specified")
        parser.print_help()
        sys.exit(1)

    preprocessor = ReadsPreprocessor(args.output)
    result = preprocessor.process(args.hifi, args.ont)

    print("\nPreprocessing result:")
    print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    main()

