#!/usr/bin/env python3
"""
Gap Detector for DEGAPv2
Detects gaps in genome assembly and extracts flanking sequences

Author: DEGAPv2 Team
"""

import os
import sys
import json
from pathlib import Path
from Bio import SeqIO


class GapDetector:
    """检测 genome 中的 gaps 并提取 flanking sequences"""
    
    def __init__(self, genome_file, output_dir):
        """
        初始化 Gap Detector
        
        Args:
            genome_file: genome FASTA 文件路径
            output_dir: 主输出目录
        """
        # 主输出目录
        self.main_output_dir = Path(output_dir)
        
        # Gap 检测结果保存到 02.gap_detection/ 子目录
        self.output_dir = self.main_output_dir / "02.gap_detection"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # gapDataBase 目录（原始 gaps 的 flanking sequences）
        self.gap_database_dir = self.output_dir / "gapDataBase"
        self.gap_database_dir.mkdir(parents=True, exist_ok=True)

        # gapData 目录（过滤和合并后的最终 gaps 的 flanking sequences）
        self.gap_data_dir = self.output_dir / "gapData"
        self.gap_data_dir.mkdir(parents=True, exist_ok=True)
        
        # Genome 文件
        self.genome_file = Path(genome_file).resolve()
        if not self.genome_file.exists():
            raise FileNotFoundError(f"Genome file not found: {genome_file}")
        
        # 读取 SeedLength
        self.seed_length = self._load_seed_length()
        
        # 存储检测结果
        self.raw_gaps = {}  # 原始 gaps（按染色体）
        self.filtered_gaps = []  # 过滤和合并后的 gaps
        self.stats = {}  # 统计信息
    
    def _load_seed_length(self):
        """从预处理配置中读取 SeedLength（取最大值）"""
        config_file = self.main_output_dir / "01.reads_preprocessor" / "preprocessing_config.json"
        
        if not config_file.exists():
            raise FileNotFoundError(
                f"Preprocessing config not found: {config_file}\n"
                f"Please run reads_preprocessor.py first!"
            )
        
        print(f"Reading SeedLength from: {config_file}")
        
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        # 获取 HiFi 和 ONT 的 SeedLength
        hifi_seed = config.get('hifi_stats', {}).get('SeedLength', 0)
        ont_seed = config.get('ont_stats', {}).get('SeedLength', 0)
        
        # 取两者中的最大值
        seed_length = max(hifi_seed, ont_seed)
        
        if seed_length == 0:
            raise ValueError("No valid SeedLength found in preprocessing config")
        
        print(f"  HiFi SeedLength: {hifi_seed}")
        print(f"  ONT SeedLength: {ont_seed}")
        print(f"  Using SeedLength: {seed_length} (max)")
        
        return seed_length
    
    def detect(self):
        """
        执行 gap 检测的完整流程
        
        Returns:
            dict: 包含检测结果的字典
        """
        print(f"\n{'='*60}")
        print(f"Gap Detection")
        print(f"{'='*60}\n")
        
        # Step 1: 扫描 genome，检测所有 gaps
        print("[1/5] Scanning genome for gaps...")
        self._scan_genome()
        
        # Step 2: 生成 gapbase.log
        print("\n[2/5] Generating gapbase.log...")
        self._generate_gapbase_log()
        
        # Step 3: 过滤和合并 gaps
        print("\n[3/5] Filtering and merging gaps...")
        self._filter_and_merge_gaps()
        
        # Step 4: 生成 gap.log
        print("\n[4/5] Generating gap.log...")
        self._generate_gap_log()

        # Step 5: 保存最终 gaps 的 flanking sequences
        print("\n[5/6] Saving final gap flanking sequences...")
        self._save_final_flanking_sequences()

        # Step 6: 保存配置
        print("\n[6/6] Saving configuration...")
        self._save_config()
        
        # 返回结果
        result = {
            'genome_file': str(self.genome_file),
            'seed_length': self.seed_length,
            'gapbase_log': str(self.output_dir / 'gapbase.log'),
            'gap_log': str(self.output_dir / 'gap.log'),
            'gap_database_dir': str(self.gap_database_dir),
            'gap_data_dir': str(self.gap_data_dir),
            'stats': self.stats
        }
        
        print(f"\n{'='*60}")
        print("Gap detection completed successfully!")
        print(f"{'='*60}\n")
        
        return result
    
    def _scan_genome(self):
        """扫描 genome，检测所有 'N' 区域"""
        print(f"  Genome file: {self.genome_file}")
        print(f"  SeedLength: {self.seed_length}")
        print(f"  Gap database: {self.gap_database_dir}")

        # 检查 gapDataBase 是否已存在
        existing_files = list(self.gap_database_dir.glob("*.fasta"))
        if existing_files:
            print(f"  Found {len(existing_files)} existing flanking sequence files, will reuse them")

        total_gaps = 0
        
        for seq_record in SeqIO.parse(self.genome_file, "fasta"):
            chrom = seq_record.id
            seq = str(seq_record.seq)
            seq_len = len(seq)
            
            print(f"\n  Processing chromosome: {chrom} ({seq_len} bp)")
            
            # 检测所有 'N' 区域
            gaps = []
            in_gap = False
            gap_start = 0
            
            for i, c in enumerate(seq):
                if c.upper() == 'N':
                    if not in_gap:
                        in_gap = True
                        gap_start = i
                else:
                    if in_gap:
                        in_gap = False
                        gaps.append((gap_start, i - 1))
            
            # 处理可能在末尾的 gap
            if in_gap:
                gaps.append((gap_start, len(seq) - 1))
            
            print(f"    Found {len(gaps)} gaps")
            
            # 为每个 gap 提取 flanking sequences
            chrom_gaps = []
            for gap_id, (start, end) in enumerate(gaps, 1):
                gap_info = self._extract_flanking_sequences(
                    seq, chrom, gap_id, start, end
                )
                chrom_gaps.append(gap_info)
            
            self.raw_gaps[chrom] = chrom_gaps
            total_gaps += len(gaps)
        
        print(f"\n  Total gaps detected: {total_gaps}")
        self.stats['total_gaps_detected'] = total_gaps
    
    def _extract_flanking_sequences(self, seq, chrom, gap_id, start, end):
        """
        提取 gap 两侧的 flanking sequences

        Args:
            seq: 染色体序列
            chrom: 染色体名称
            gap_id: gap 编号
            start: gap 起始位置（0-based）
            end: gap 结束位置（0-based）

        Returns:
            dict: gap 信息
        """
        # 转换为 1-based 坐标
        chr_start = start + 1
        chr_end = end + 1
        gap_len = end - start + 1

        # 检查是否已存在 flanking sequence 文件
        left_file = self.gap_database_dir / f"{chrom}.{gap_id}.left.fasta"
        right_file = self.gap_database_dir / f"{chrom}.{gap_id}.right.fasta"

        # 如果文件已存在，从文件读取
        if left_file.exists() and right_file.exists():
            # 读取左侧序列
            left_seq = ''
            if left_file.exists():
                with open(left_file, 'r') as f:
                    f.readline()  # 跳过 header
                    left_seq = f.readline().strip()

            # 读取右侧序列
            right_seq = ''
            if right_file.exists():
                with open(right_file, 'r') as f:
                    f.readline()  # 跳过 header
                    right_seq = f.readline().strip()

            return {
                'chrom': chrom,
                'id': gap_id,
                'start': chr_start,
                'end': chr_end,
                'gap_len': gap_len,
                'left_len': len(left_seq),
                'right_len': len(right_seq),
                'left_seq': left_seq,
                'right_seq': right_seq
            }

        # 否则，提取并保存
        # 提取左侧 flanking sequence
        left_chars = []
        current_pos = start - 1
        while current_pos >= 0 and len(left_chars) < self.seed_length:
            char = seq[current_pos].upper()
            if char == 'N':
                break
            left_chars.append(char)
            current_pos -= 1
        left_seq = ''.join(reversed(left_chars))
        left_len = len(left_seq)

        # 提取右侧 flanking sequence
        right_chars = []
        current_pos = end + 1
        while current_pos < len(seq) and len(right_chars) < self.seed_length:
            char = seq[current_pos].upper()
            if char == 'N':
                break
            right_chars.append(char)
            current_pos += 1
        right_seq = ''.join(right_chars)
        right_len = len(right_seq)

        # 保存 flanking sequences 到文件
        if left_len > 0:
            with open(left_file, 'w') as f:
                f.write(f">{chrom}.{gap_id}.left\n{left_seq}\n")

        if right_len > 0:
            with open(right_file, 'w') as f:
                f.write(f">{chrom}.{gap_id}.right\n{right_seq}\n")

        return {
            'chrom': chrom,
            'id': gap_id,
            'start': chr_start,
            'end': chr_end,
            'gap_len': gap_len,
            'left_len': left_len,
            'right_len': right_len,
            'left_seq': left_seq,
            'right_seq': right_seq
        }
    
    def _generate_gapbase_log(self):
        """生成 gapbase.log（记录所有原始 gaps）"""
        gapbase_log = self.output_dir / 'gapbase.log'
        
        with open(gapbase_log, 'w') as f:
            # 写入表头
            f.write("Chromosome\tId\tStart\tEnd\tGapLen\tLeftLen\tRightLen\n")
            
            # 写入每个 gap
            for chrom, gaps in self.raw_gaps.items():
                for gap in gaps:
                    f.write(
                        f"{gap['chrom']}\t{gap['id']}\t{gap['start']}\t{gap['end']}\t"
                        f"{gap['gap_len']}\t{gap['left_len']}\t{gap['right_len']}\n"
                    )
        
        print(f"  Generated: {gapbase_log}")
        print(f"  Total gaps: {sum(len(gaps) for gaps in self.raw_gaps.values())}")
    
    def _filter_and_merge_gaps(self):
        """过滤和合并 gaps"""
        total_filtered = 0
        total_merged = 0
        total_final = 0
        
        merge_threshold = 11000  # 11kb
        
        print(f"  Minimum gap length: 20 bp")
        print(f"  Merge distance threshold: {merge_threshold} bp")
        
        for chrom, gaps in self.raw_gaps.items():
            print(f"\n  Chromosome {chrom}:")
            print(f"    Original gaps: {len(gaps)}")
            
            # Step 1: 过滤小 gaps（< 20 bp）
            filtered = [gap for gap in gaps if gap['gap_len'] >= 20]
            filtered_count = len(gaps) - len(filtered)
            total_filtered += filtered_count
            print(f"    Filtered out (< 20 bp): {filtered_count}")
            
            # Step 2: 合并相邻 gaps
            merged = []
            for gap in sorted(filtered, key=lambda x: x['start']):
                if not merged:
                    merged.append(gap)
                else:
                    last = merged[-1]
                    distance = gap['start'] - last['end'] - 1

                    if distance < merge_threshold:
                        # 合并
                        last_id = last.get('id', 'merged')
                        gap_id = gap.get('id', 'unknown')
                        print(f"      Merging gaps {last_id} and {gap_id} (distance={distance} bp)")
                        merged_gap = {
                            'chrom': chrom,
                            'start': last['start'],
                            'end': gap['end'],
                            'gap_len': gap['end'] - last['start'] + 1,
                            'left_len': last['left_len'],
                            'right_len': gap['right_len'],
                            'left_seq': last['left_seq'],
                            'right_seq': gap['right_seq']
                        }
                        merged[-1] = merged_gap
                        total_merged += 1
                    else:
                        merged.append(gap)
            
            print(f"    After merging: {len(merged)}")
            
            # Step 3: 重新编号
            for new_id, gap in enumerate(merged, 1):
                gap['id'] = new_id
                self.filtered_gaps.append(gap)
            
            total_final += len(merged)
        
        print(f"\n  Summary:")
        print(f"    Total gaps detected: {self.stats['total_gaps_detected']}")
        print(f"    Filtered out (< 20 bp): {total_filtered}")
        print(f"    Merged gaps: {total_merged}")
        print(f"    Final gaps for filling: {total_final}")
        
        self.stats['gaps_filtered'] = total_filtered
        self.stats['gaps_merged'] = total_merged
        self.stats['gaps_final'] = total_final

    def _generate_gap_log(self):
        """生成 gap.log（记录过滤和合并后的最终 gaps）"""
        gap_log = self.output_dir / 'gap.log'

        with open(gap_log, 'w') as f:
            # 写入表头
            f.write("Chromosome\tId\tStart\tEnd\tGapLen\tLeftLen\tRightLen\n")

            # 写入每个 gap
            for gap in self.filtered_gaps:
                f.write(
                    f"{gap['chrom']}\t{gap['id']}\t{gap['start']}\t{gap['end']}\t"
                    f"{gap['gap_len']}\t{gap['left_len']}\t{gap['right_len']}\n"
                )

        print(f"  Generated: {gap_log}")
        print(f"  Final gaps: {len(self.filtered_gaps)}")

    def _save_final_flanking_sequences(self):
        """保存过滤和合并后的最终 gaps 的 flanking sequences 到 gapData/"""
        print(f"  Saving to: {self.gap_data_dir}")

        # 检查是否已存在
        existing_files = list(self.gap_data_dir.glob("*.fasta"))
        if len(existing_files) == len(self.filtered_gaps) * 2:
            print(f"  Found {len(existing_files)} existing files, skipping")
            return

        saved_count = 0
        for gap in self.filtered_gaps:
            chrom = gap['chrom']
            gap_id = gap['id']

            # 保存左侧序列
            if gap['left_len'] > 0:
                left_file = self.gap_data_dir / f"{chrom}.{gap_id}.left.fasta"
                with open(left_file, 'w') as f:
                    f.write(f">{chrom}.{gap_id}.left\n{gap['left_seq']}\n")
                saved_count += 1

            # 保存右侧序列
            if gap['right_len'] > 0:
                right_file = self.gap_data_dir / f"{chrom}.{gap_id}.right.fasta"
                with open(right_file, 'w') as f:
                    f.write(f">{chrom}.{gap_id}.right\n{gap['right_seq']}\n")
                saved_count += 1

        print(f"  Saved {saved_count} flanking sequence files")

    def _save_config(self):
        """保存配置到 JSON 文件（使用绝对路径）"""
        # 按染色体组织 gap 信息
        gaps_by_chromosome = {}
        for gap in self.filtered_gaps:
            chrom = gap['chrom']
            if chrom not in gaps_by_chromosome:
                gaps_by_chromosome[chrom] = {
                    'count': 0,
                    'gaps': []
                }

            gaps_by_chromosome[chrom]['count'] += 1
            gaps_by_chromosome[chrom]['gaps'].append({
                'id': gap['id'],
                'start': gap['start'],
                'end': gap['end'],
                'gap_len': gap['gap_len'],
                'left_len': gap['left_len'],
                'right_len': gap['right_len']
            })

        config = {
            'genome_file': str(self.genome_file),
            'seed_length': self.seed_length,
            'gapbase_log': str((self.output_dir / 'gapbase.log').resolve()),
            'gap_log': str((self.output_dir / 'gap.log').resolve()),
            'gap_database_dir': str(self.gap_database_dir.resolve()),
            'gap_data_dir': str(self.gap_data_dir.resolve()),
            'output_dir': str(self.output_dir.resolve()),
            'stats': self.stats,
            'gaps_by_chromosome': gaps_by_chromosome
        }

        config_file = self.output_dir / 'gap_detection_config.json'
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)

        print(f"  Configuration saved: {config_file}")
        print(f"  Chromosomes with gaps: {len(gaps_by_chromosome)}")


def main():
    """命令行接口"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Detect gaps in genome assembly and extract flanking sequences',
        epilog='''
Example:
  %(prog)s --genome genome.fasta -o output

Note: This script requires preprocessing to be completed first.
      It will read SeedLength from output/01.reads_preprocessor/preprocessing_config.json
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--genome', required=True, help='Genome FASTA file')
    parser.add_argument('--output', '-o', required=True, help='Output directory')

    args = parser.parse_args()

    try:
        detector = GapDetector(args.genome, args.output)
        result = detector.detect()

        print("\nGap detection result:")
        print(json.dumps(result, indent=2, default=str))

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

