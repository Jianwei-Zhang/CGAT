#!/usr/bin/env python3
"""
Genome Integrator - Step 4

将成功填充的 gaps 整合到原始基因组中，生成填充后的基因组文件。

使用策略 3（构建新序列）：
- 按照 gap 的位置，分段构建新序列
- 将原始序列和填充序列拼接起来
- 避免位置信息失效的问题

输入：
- 原始基因组文件（从 gap_detection_config.json 读取）
- Gap filling 统计结果（gap_filling_results.json）

输出：
- genome.filled.fasta：填充后的基因组
- integration.log：整合日志
- integration_config.json：整合配置
"""

import json
import sys
from pathlib import Path
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord


class GenomeIntegrator:
    """将填充后的 gaps 整合到原始基因组中"""
    
    def __init__(self, output_dir):
        """
        初始化 Genome Integrator
        
        Args:
            output_dir: 主输出目录
        """
        self.main_output_dir = Path(output_dir)
        
        # 输出目录
        self.output_dir = self.main_output_dir / "04.genome_integration"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 读取 gap detection 配置（获取原始基因组路径）
        self.gap_detection_dir = self.main_output_dir / "02.gap_detection"
        self.gap_detection_config_file = self.gap_detection_dir / "gap_detection_config.json"
        if not self.gap_detection_config_file.exists():
            raise FileNotFoundError(
                f"Gap detection config not found: {self.gap_detection_config_file}\n"
                f"Please run gap_detector.py first!"
            )
        
        with open(self.gap_detection_config_file, 'r') as f:
            self.gap_detection_config = json.load(f)
        
        # 原始基因组文件
        self.genome_file = Path(self.gap_detection_config['genome_file'])
        if not self.genome_file.exists():
            raise FileNotFoundError(f"Genome file not found: {self.genome_file}")
        
        # 读取 gap filling 统计结果
        self.gap_filling_dir = self.main_output_dir / "03.gap_filling"
        self.gap_filling_results_file = self.gap_filling_dir / "gap_filling_results.json"
        if not self.gap_filling_results_file.exists():
            raise FileNotFoundError(
                f"Gap filling results not found: {self.gap_filling_results_file}\n"
                f"Please run job_manager.py first!"
            )
        
        with open(self.gap_filling_results_file, 'r') as f:
            self.gap_filling_results = json.load(f)
        
        # 统计信息
        self.stats = {
            'total_chromosomes': 0,
            'chromosomes_with_filled_gaps': 0,
            'total_gaps_filled': 0,
            'total_bp_added': 0,
            'chromosomes': {}
        }
    
    def integrate(self):
        """
        执行基因组整合的完整流程
        
        Returns:
            dict: 包含整合结果的字典
        """
        print(f"\n{'='*60}")
        print(f"Genome Integration")
        print(f"{'='*60}\n")
        
        print(f"[1/4] Reading original genome...")
        genome_dict = self._load_genome()
        
        print(f"\n[2/4] Organizing filled gaps by chromosome...")
        filled_gaps_by_chrom = self._organize_filled_gaps()
        
        print(f"\n[3/4] Integrating filled gaps into genome...")
        filled_genome = self._integrate_gaps(genome_dict, filled_gaps_by_chrom)
        
        print(f"\n[4/4] Saving filled genome and logs...")
        self._save_results(filled_genome)
        
        print(f"\n{'='*60}")
        print("Genome integration completed successfully!")
        print(f"{'='*60}\n")
        
        return {
            'output_dir': str(self.output_dir),
            'filled_genome_file': str(self.output_dir / 'genome.filled.fasta'),
            'integration_log': str(self.output_dir / 'integration.log'),
            'stats': self.stats
        }
    
    def _load_genome(self):
        """读取原始基因组"""
        print(f"  Genome file: {self.genome_file}")
        
        genome_dict = SeqIO.to_dict(SeqIO.parse(self.genome_file, "fasta"))
        
        self.stats['total_chromosomes'] = len(genome_dict)
        print(f"  Loaded {len(genome_dict)} chromosomes")
        
        return genome_dict
    
    def _organize_filled_gaps(self):
        """按染色体组织成功填充的 gaps"""
        filled_gaps_by_chrom = {}
        
        for gap in self.gap_filling_results['gaps']:
            if gap['filled']:
                chrom = gap['chromosome']
                if chrom not in filled_gaps_by_chrom:
                    filled_gaps_by_chrom[chrom] = []
                filled_gaps_by_chrom[chrom].append(gap)
        
        # 按 replace_start 排序（从小到大）
        for chrom in filled_gaps_by_chrom:
            filled_gaps_by_chrom[chrom].sort(key=lambda x: x['replace_start'])
        
        self.stats['chromosomes_with_filled_gaps'] = len(filled_gaps_by_chrom)
        self.stats['total_gaps_filled'] = sum(len(gaps) for gaps in filled_gaps_by_chrom.values())
        
        print(f"  Chromosomes with filled gaps: {len(filled_gaps_by_chrom)}")
        print(f"  Total filled gaps: {self.stats['total_gaps_filled']}")
        
        for chrom, gaps in filled_gaps_by_chrom.items():
            print(f"    {chrom}: {len(gaps)} gaps")
        
        return filled_gaps_by_chrom
    
    def _integrate_gaps(self, genome_dict, filled_gaps_by_chrom):
        """
        将填充后的 gaps 整合到基因组中
        
        使用策略 3：构建新序列
        """
        filled_genome = {}
        
        for chrom, seq_record in genome_dict.items():
            print(f"\n  Processing {chrom}...")
            
            if chrom not in filled_gaps_by_chrom:
                # 没有填充的 gap，直接使用原始序列
                filled_genome[chrom] = seq_record
                print(f"    No filled gaps, using original sequence")
                continue
            
            # 有填充的 gap，构建新序列
            gaps = filled_gaps_by_chrom[chrom]
            new_seq = self._build_new_sequence(str(seq_record.seq), gaps, chrom)
            
            # 创建新的 SeqRecord
            filled_genome[chrom] = SeqRecord(
                Seq(new_seq),
                id=seq_record.id,
                description=f"{seq_record.description} [gaps filled]"
            )
            
            # 统计信息
            original_len = len(seq_record.seq)
            new_len = len(new_seq)
            bp_added = new_len - original_len
            
            self.stats['chromosomes'][chrom] = {
                'original_length': original_len,
                'filled_length': new_len,
                'bp_added': bp_added,
                'gaps_filled': len(gaps)
            }
            self.stats['total_bp_added'] += bp_added
            
            print(f"    Original length: {original_len:,} bp")
            print(f"    Filled length: {new_len:,} bp")
            print(f"    BP added: {bp_added:+,} bp")
            print(f"    Gaps filled: {len(gaps)}")
        
        return filled_genome
    
    def _build_new_sequence(self, original_seq, gaps, chrom):
        """
        构建新序列（策略 3）
        
        Args:
            original_seq: 原始染色体序列（字符串）
            gaps: 该染色体上成功填充的 gaps（已按 replace_start 排序）
            chrom: 染色体名称
        
        Returns:
            str: 新的染色体序列
        """
        new_seq_parts = []
        current_pos = 0
        
        for gap in gaps:
            gap_id = gap['gap_id']
            replace_start = gap['replace_start']
            replace_end = gap['replace_end']
            
            # 检查位置是否合法
            if replace_start < 0:
                print(f"    Warning: Gap {gap_id} replace_start={replace_start} < 0, adjusting to 0")
                replace_start = 0
            
            if replace_end >= len(original_seq):
                print(f"    Warning: Gap {gap_id} replace_end={replace_end} >= seq_len={len(original_seq)}, adjusting")
                replace_end = len(original_seq) - 1
            
            # 检查是否有重叠
            if replace_start < current_pos:
                print(f"    Warning: Gap {gap_id} overlaps with previous gap!")
                print(f"      Current position: {current_pos}, replace_start: {replace_start}")
                # 跳过重叠的部分
                replace_start = current_pos
            
            # 添加 gap 之前的原始序列
            if replace_start > current_pos:
                new_seq_parts.append(original_seq[current_pos:replace_start])
            
            # 读取并添加填充序列
            filled_seq = self._read_filled_sequence(gap['final_sequence_file'])
            new_seq_parts.append(filled_seq)
            
            # 更新当前位置
            current_pos = replace_end + 1
        
        # 添加最后一个 gap 之后的原始序列
        if current_pos < len(original_seq):
            new_seq_parts.append(original_seq[current_pos:])
        
        # 拼接所有片段
        return ''.join(new_seq_parts)
    
    def _read_filled_sequence(self, seq_file):
        """读取填充后的序列"""
        seq_file = Path(seq_file)
        if not seq_file.exists():
            raise FileNotFoundError(f"Filled sequence file not found: {seq_file}")
        
        # 读取 FASTA 文件
        record = SeqIO.read(seq_file, "fasta")
        return str(record.seq)
    
    def _save_results(self, filled_genome):
        """保存填充后的基因组和日志"""
        # 保存填充后的基因组
        filled_genome_file = self.output_dir / 'genome.filled.fasta'
        with open(filled_genome_file, 'w') as f:
            SeqIO.write(filled_genome.values(), f, "fasta")
        
        print(f"  Filled genome saved: {filled_genome_file}")
        
        # 保存整合日志
        self._save_integration_log()
        
        # 保存配置
        self._save_config()
    
    def _save_integration_log(self):
        """保存整合日志"""
        log_file = self.output_dir / 'integration.log'
        
        with open(log_file, 'w') as f:
            f.write("="*60 + "\n")
            f.write("Genome Integration Log\n")
            f.write("="*60 + "\n\n")
            
            f.write(f"Original genome: {self.genome_file}\n")
            f.write(f"Total chromosomes: {self.stats['total_chromosomes']}\n")
            f.write(f"Chromosomes with filled gaps: {self.stats['chromosomes_with_filled_gaps']}\n")
            f.write(f"Total gaps filled: {self.stats['total_gaps_filled']}\n")
            f.write(f"Total BP added: {self.stats['total_bp_added']:+,}\n\n")
            
            f.write("="*60 + "\n")
            f.write("Per-Chromosome Statistics\n")
            f.write("="*60 + "\n\n")
            
            for chrom, stats in self.stats['chromosomes'].items():
                f.write(f"{chrom}:\n")
                f.write(f"  Original length: {stats['original_length']:,} bp\n")
                f.write(f"  Filled length: {stats['filled_length']:,} bp\n")
                f.write(f"  BP added: {stats['bp_added']:+,} bp\n")
                f.write(f"  Gaps filled: {stats['gaps_filled']}\n\n")
        
        print(f"  Integration log saved: {log_file}")
    
    def _save_config(self):
        """保存配置到 JSON 文件"""
        config = {
            'original_genome': str(self.genome_file),
            'filled_genome': str((self.output_dir / 'genome.filled.fasta').resolve()),
            'gap_filling_results': str(self.gap_filling_results_file.resolve()),
            'output_dir': str(self.output_dir.resolve()),
            'stats': self.stats
        }
        
        config_file = self.output_dir / 'integration_config.json'
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"  Configuration saved: {config_file}")


def main():
    """命令行接口"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Integrate filled gaps into the original genome',
        epilog='''
Example:
  %(prog)s -o output

Note: This script requires gap filling to be completed first.
      It will read configurations from:
      - output/02.gap_detection/gap_detection_config.json
      - output/03.gap_filling/gap_filling_results.json
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--output', '-o', required=True, help='Output directory')
    
    args = parser.parse_args()
    
    try:
        integrator = GenomeIntegrator(args.output)
        result = integrator.integrate()
        
        print("\nIntegration result:")
        print(json.dumps(result, indent=2, default=str))
    
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

