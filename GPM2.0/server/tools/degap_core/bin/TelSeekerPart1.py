#!/usr/bin/env python3
"""
TelSeekerPart1.py - Extract terminal telomeric reads

Algorithm:
- Check both physical read ends.
- The checked length at each end is --tel-n * len(motif).
- Greedily scan motif-length units against motif rotations and reverse
  complement rotations.
- On a hit, jump by motif length; on a miss, slide one base.
- Classify a read as telomeric when hits / tel_n >= --tel-r.
- --tel-mm controls whether each motif-length unit allows 0 or 1 mismatch.

Input:
    - Reads split into fragments in: --out/hifi_reads_part/ and/or --out/ont_reads_part/
    
Output:
    - --out/part1.telo.reads/left.telo.reads.fa   # Left telomeric reads
    - --out/part1.telo.reads/right.telo.reads.fa  # Right telomeric reads  
    - --out/part1.telo.reads/part1.log            # Processing log

Usage:
    python TelSeekerPart1.py --motif TTAGGG --out output_dir -t 100
"""

import os
import sys
import argparse
import glob
import subprocess
import tempfile
import shutil
import math
from pathlib import Path
from typing import List
from Bio import SeqIO
from Bio.SeqRecord import SeqRecord
from Bio.Seq import Seq

# Import TRC calculation functions from TelSeekerCheck
from TelSeekerCheck import calculate_trc


# ===== Motif Filtering Functions =====

def get_reverse_complement(motif: str) -> str:
    """
    Get reverse complement of motif
    
    Args:
        motif: DNA motif
    
    Returns:
        Reverse complement sequence
    """
    return str(Seq(motif).reverse_complement())


def count_exact_motif_matches(sequence: str, motif: str, include_reverse_complement: bool = True) -> int:
    """
    Count exact matches of motif in sequence (non-overlapping)
    Considers both forward motif and its reverse complement
    Returns the maximum count between forward and reverse complement
    
    Args:
        sequence: DNA sequence to search
        motif: Exact motif to search for (e.g., 'TTAGGG')
        include_reverse_complement: Whether to also count reverse complement
    
    Returns:
        Maximum number of non-overlapping exact matches (max of forward and RC)
    """
    sequence = sequence.upper()
    motif = motif.upper()
    
    # Count forward motif (non-overlapping)
    forward_count = sequence.count(motif)
    
    # Count reverse complement if requested and take the maximum
    if include_reverse_complement:
        rc_motif = get_reverse_complement(motif)
        # Only check RC if it's different from forward
        if rc_motif != motif:
            rc_count = sequence.count(rc_motif)
            return max(forward_count, rc_count)
    
    return forward_count


def motif_rotations(motif: str) -> List[str]:
    """Return all cyclic rotations of a motif."""
    motif = (motif or "").upper()
    if not motif:
        return []
    doubled = motif + motif
    return sorted({doubled[i:i + len(motif)] for i in range(len(motif))})


def _hamming_distance(seq1: str, seq2: str) -> int:
    return sum(base1 != base2 for base1, base2 in zip(seq1, seq2))


def _matches_any_motif_unit(kmer: str, patterns: set, mismatch: int) -> bool:
    if mismatch == 0:
        return kmer in patterns
    return any(_hamming_distance(kmer, pattern) <= mismatch for pattern in patterns)


def count_terminal_telomere_hits(sequence: str, patterns: set,
                                 motif_length: int, mismatch: int = 0) -> int:
    """
    Count motif units in one terminal sequence with greedy non-overlapping hits.

    On a hit, the scanner jumps by motif_length. On a miss, it slides one base
    and tests the next motif_length-bp window.
    """
    if motif_length <= 0:
        return 0

    seq_str = (sequence or "").upper()
    hits = 0
    pos = 0
    while pos + motif_length <= len(seq_str):
        kmer = seq_str[pos:pos + motif_length]
        if _matches_any_motif_unit(kmer, patterns, mismatch):
            hits += 1
            pos += motif_length
        else:
            pos += 1
    return hits


def classify_read_by_terminal_telomere(sequence: str, motif: str,
                                       tel_n: int = 100,
                                       tel_r: float = 0.6,
                                       tel_mm: int = 0) -> dict:
    """
    Classify one read from motif-rotation content at the two physical read ends.

    A read side passes when hits / tel_n >= tel_r in either terminal sequence,
    where each terminal sequence has length tel_n * len(motif).
    """
    if tel_n <= 0:
        raise ValueError("tel_n must be greater than 0")
    if not (0 < tel_r <= 1):
        raise ValueError("tel_r must be in the interval (0, 1]")
    if tel_mm not in {0, 1}:
        raise ValueError("tel_mm must be 0 or 1")

    seq_str = (sequence or "").upper()
    motif_forward = (motif or "").upper()
    motif_length = len(motif_forward)
    if motif_length == 0:
        return {
            "passed": False,
            "side": None,
            "right_pass": False,
            "left_pass": False,
            "forward_hits": 0,
            "reverse_hits": 0,
            "required_hits": 0,
            "terminal_len": 0,
            "forward_ratio": 0.0,
            "reverse_ratio": 0.0,
        }

    terminal_len = min(len(seq_str), tel_n * motif_length)
    left_terminal = seq_str[:terminal_len]
    right_terminal = seq_str[-terminal_len:] if terminal_len > 0 else ""

    forward_patterns = set(motif_rotations(motif_forward))
    reverse_patterns = set(motif_rotations(get_reverse_complement(motif_forward)))
    required_hits = math.ceil(tel_n * tel_r)

    terminal_sequences = [left_terminal]
    if right_terminal != left_terminal:
        terminal_sequences.append(right_terminal)

    best_forward_hits = max(
        count_terminal_telomere_hits(term, forward_patterns, motif_length, tel_mm)
        for term in terminal_sequences
    )
    best_reverse_hits = max(
        count_terminal_telomere_hits(term, reverse_patterns, motif_length, tel_mm)
        for term in terminal_sequences
    )

    right_pass = best_forward_hits >= required_hits
    left_pass = best_reverse_hits >= required_hits

    if right_pass and (not left_pass or best_forward_hits >= best_reverse_hits):
        passed = True
        side = "right"
    elif left_pass:
        passed = True
        side = "left"
    else:
        passed = False
        side = None

    return {
        "passed": passed,
        "side": side,
        "right_pass": right_pass,
        "left_pass": left_pass,
        "forward_hits": best_forward_hits,
        "reverse_hits": best_reverse_hits,
        "required_hits": required_hits,
        "terminal_len": terminal_len,
        "forward_ratio": best_forward_hits / tel_n,
        "reverse_ratio": best_reverse_hits / tel_n,
    }


class TeloReadsExtractor:
    """Extract telomeric reads from split read files using terminal read-end ratios."""
    
    def __init__(self, output_dir: str, motif: str, threads: int = 20,
                 trc_threshold: float = None, check_length: int = None,
                 batch_size: int = 1000, enable_second_filter: bool = None,
                 min_motif_count: int = None, overlapping: bool = False,
                 read_window_size: int = None,
                 min_window_repeats: int = None,
                 min_window_density: float = None,
                 tel_n: int = 100,
                 tel_r: float = 0.6,
                 tel_mm: int = 0):
        """
        Initialize TeloReadsExtractor

        Args:
            output_dir: Output directory (where DEGAP placed reads_part/)
            motif: Telomere repeat motif (e.g., TTAGGG)
            threads: Number of threads for parallel processing (-t parameter)
            trc_threshold: Compatibility option; terminal-ratio mode ignores it
            check_length: Compatibility option; terminal-ratio mode ignores it
            batch_size: Number of reads to read at once (default: 1000)
            enable_second_filter: Enable second-level terminal-ratio filtering
            min_motif_count: Compatibility option; terminal-ratio mode ignores it
            overlapping: Compatibility option; terminal-ratio mode ignores it
            read_window_size: Compatibility option; terminal-ratio mode ignores it
            min_window_repeats: Compatibility option; terminal-ratio mode ignores it
            min_window_density: Compatibility option; terminal-ratio mode ignores it
            tel_n: Number of motif units checked at each read end
            tel_r: Minimum terminal hit ratio (hits / tel_n)
            tel_mm: Allowed mismatches per motif-length unit, either 0 or 1
        """
        self.output_dir = output_dir
        self.motif = motif.upper()
        self.threads = threads
        self.kmer_length = len(motif) - 2
        self.batch_size = batch_size
        self.enable_second_filter = True if enable_second_filter is None else enable_second_filter
        if tel_n <= 0:
            raise ValueError("tel_n must be greater than 0")
        if not (0 < tel_r <= 1):
            raise ValueError("tel_r must be in the interval (0, 1]")
        if tel_mm not in {0, 1}:
            raise ValueError("tel_mm must be 0 or 1")
        self.tel_n = tel_n
        self.tel_r = tel_r
        self.tel_mm = tel_mm

        # Direction marker labels retained for logs and output naming.
        self.pat_right = self.motif * 2  # e.g., TTAGGGTTAGGG
        self.pat_left = get_reverse_complement(self.pat_right)  # e.g., CCCTAACCCTAA

        # Locate reads_part directories
        self.hifi_reads_part_dir = os.path.join(output_dir, "hifi_reads_part")
        self.ont_reads_part_dir = os.path.join(output_dir, "ont_reads_part")
        
        # Output directory
        self.telo_reads_dir = os.path.join(output_dir, "part1.telo.reads")
        os.makedirs(self.telo_reads_dir, exist_ok=True)
        
        # Output files - Level 1 (temp files)
        self.temp_left_output = os.path.join(self.telo_reads_dir, "temp1.left.telo.reads.fa")
        self.temp_right_output = os.path.join(self.telo_reads_dir, "temp1.right.telo.reads.fa")
        self.temp_left_hifi = os.path.join(self.telo_reads_dir, "temp1.left.hifi.fa")
        self.temp_left_ont = os.path.join(self.telo_reads_dir, "temp1.left.ont.fa")
        self.temp_right_hifi = os.path.join(self.telo_reads_dir, "temp1.right.hifi.fa")
        self.temp_right_ont = os.path.join(self.telo_reads_dir, "temp1.right.ont.fa")
        
        # Output files - Level 2 final outputs
        self.left_output = os.path.join(self.telo_reads_dir, "left.telo.reads.fa")
        self.right_output = os.path.join(self.telo_reads_dir, "right.telo.reads.fa")
        
        # Platform-specific output files (for Global file creation)
        self.left_hifi_output = os.path.join(self.telo_reads_dir, "left.telo.reads.hifi.fa")
        self.left_ont_output = os.path.join(self.telo_reads_dir, "left.telo.reads.ont.fa")
        self.right_hifi_output = os.path.join(self.telo_reads_dir, "right.telo.reads.hifi.fa")
        self.right_ont_output = os.path.join(self.telo_reads_dir, "right.telo.reads.ont.fa")
        
        # Output files - Global merged outputs
        self.global_left_output = os.path.join(self.telo_reads_dir, "Global.left.telo.reads.fa")
        self.global_right_output = os.path.join(self.telo_reads_dir, "Global.right.telo.reads.fa")
        
        # Output files - Level 2 failed (temp files)
        self.temp_left_failed = os.path.join(self.telo_reads_dir, "temp2.left.telo.reads.filter.failed.fa")
        self.temp_right_failed = os.path.join(self.telo_reads_dir, "temp2.right.telo.reads.filter.failed.fa")
        
        self.log_file = os.path.join(self.telo_reads_dir, "part1.log")
        
        # Statistics
        self.stats = {
            'total_reads': 0,
            'left_telo': 0,
            'right_telo': 0,
            'both_telo': 0,
            'non_telo': 0
        }
        
        # Second filter statistics
        self.filter_stats = {
            'left': {'total': 0, 'passed': 0, 'failed': 0},
            'right': {'total': 0, 'passed': 0, 'failed': 0}
        }
        
    def run(self):
        """Run the complete telomeric reads extraction workflow"""
        print(f"[Part1-NEW] Starting telomeric reads extraction...")
        print(f"  Motif: {self.motif}")
        print(f"  Window markers:")
        print(f"    Right (forward): {self.pat_right}")
        print(f"    Left (reverse):  {self.pat_left}")
        print(f"  Scan mode: terminal_ratio")
        print(f"  Terminal units (--tel-n): {self.tel_n}")
        print(f"  Terminal ratio (--tel-r): {self.tel_r}")
        print(f"  Terminal mismatch (--tel-mm): {self.tel_mm}")
        print(f"  Terminal length per end: {self.tel_n * len(self.motif)} bp")
        print(f"  Threads: {self.threads}")
        print(f"  Batch size: {self.batch_size} reads")
        print(f"  Output order: Platform-grouped, reads sorted by ID within each platform")
        print()
        
        # Find all split read files
        split_files = self._find_split_files()
        
        if not split_files:
            print(f"[Part1-NEW] ERROR: No split read files found in:")
            print(f"  {self.hifi_reads_part_dir}")
            print(f"  {self.ont_reads_part_dir}")
            print(f"  Please run DEGAP.py first to create these directories.")
            sys.exit(1)
        
        print(f"[Part1-NEW] Found {len(split_files)} split read files")
        
        # Process split files in parallel
        self._process_split_files_parallel(split_files)
        
        # Merge results
        self._merge_results()
        
        # Apply second-level filter if enabled
        if self.enable_second_filter:
            self._apply_second_filter()
        
        # Create Global merged files
        if self.enable_second_filter:
            self._create_global_files()
        
        # Write log
        self._write_log()
        
        # Print summary
        self._print_summary()
        
        print(f"\n[Part1-NEW] Complete! Results saved to: {self.telo_reads_dir}")
        
    def _find_split_files(self):
        """Find all split read files and categorize by platform"""
        split_files = []
        self.hifi_files = []  # Store HiFi files separately
        self.ont_files = []   # Store ONT files separately
        
        # Check HiFi reads_part
        if os.path.exists(self.hifi_reads_part_dir):
            hifi_files = sorted(glob.glob(os.path.join(self.hifi_reads_part_dir, "*.fa*")))
            self.hifi_files = hifi_files
            split_files.extend(hifi_files)
            print(f"[Part1-NEW] Found {len(hifi_files)} HiFi split files")
        
        # Check ONT reads_part
        if os.path.exists(self.ont_reads_part_dir):
            ont_files = sorted(glob.glob(os.path.join(self.ont_reads_part_dir, "*.fa*")))
            self.ont_files = ont_files
            split_files.extend(ont_files)
            print(f"[Part1-NEW] Found {len(ont_files)} ONT split files")
        
        return split_files
    
    def _process_split_files_parallel(self, split_files):
        """Process split files using GNU parallel"""
        print(f"\n[Part1-NEW] Processing {len(split_files)} files with {self.threads} threads...")

        # Create temporary directory
        temp_dir = os.path.join(self.telo_reads_dir, "temp_parallel")
        os.makedirs(temp_dir, exist_ok=True)

        try:
            # Create processing script
            script_path = self._create_processing_script(temp_dir)

            # Create file list
            file_list_path = os.path.join(temp_dir, "file_list.txt")
            with open(file_list_path, 'w') as f:
                for file_path in split_files:
                    f.write(f"{file_path}\n")

            # Run GNU parallel
            parallel_cmd = [
                'parallel', '--will-cite', '-j', str(self.threads),
                sys.executable, script_path, '{}',
                '::::', file_list_path
            ]
            
            print(f"[Part1-NEW] Running parallel processing...")
            result = subprocess.run(parallel_cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"[Part1-NEW] Warning: parallel processing had issues")
                print(f"  Return code: {result.returncode}")
                if result.stderr:
                    print(f"  Stderr: {result.stderr[:500]}")
            
            print("[Part1-NEW] Parallel processing completed")
            
        finally:
            pass  # Keep temp_dir for merging
    
    def _create_processing_script(self, temp_dir):
        """Create Python script for processing single split file with window-based algorithm"""
        script_path = os.path.join(temp_dir, "process_single_file.py")
        
        # Embed terminal-ratio functions directly to avoid import issues.
        script_content = f'''#!/usr/bin/env python3
import sys
import os
import math
import re
from Bio import SeqIO
from Bio.Seq import Seq

# ===== Embedded terminal-ratio functions =====
def _pattern_scramble_telo(pattern, cut_length):
    pattern = (pattern or "").upper()
    if not pattern:
        return []
    cut_length = max(1, cut_length)
    extended = pattern * 2
    kmers = set()
    for i in range(len(pattern)):
        fragment = extended[i:i + cut_length]
        if len(fragment) == cut_length:
            kmers.add(fragment)
    kmers.update(str(Seq(kmer).reverse_complement()) for kmer in list(kmers))
    return sorted(kmers)

def patterns_to_search_topsicle(motif, cut_length):
    kmers = _pattern_scramble_telo(motif, cut_length)
    return [re.escape(kmer) for kmer in kmers]

def motif_rotations(motif):
    motif = (motif or "").upper()
    if not motif:
        return []
    doubled = motif + motif
    return sorted(set(doubled[i:i + len(motif)] for i in range(len(motif))))

def _hamming_distance(seq1, seq2):
    return sum(base1 != base2 for base1, base2 in zip(seq1, seq2))

def _matches_any_motif_unit(kmer, patterns, mismatch):
    if mismatch == 0:
        return kmer in patterns
    return any(_hamming_distance(kmer, pattern) <= mismatch for pattern in patterns)

def count_terminal_telomere_hits(sequence, patterns, motif_length, mismatch=0):
    if motif_length <= 0:
        return 0
    seq_str = (sequence or "").upper()
    hits = 0
    pos = 0
    while pos + motif_length <= len(seq_str):
        kmer = seq_str[pos:pos + motif_length]
        if _matches_any_motif_unit(kmer, patterns, mismatch):
            hits += 1
            pos += motif_length
        else:
            pos += 1
    return hits

def classify_read_by_terminal_telomere(sequence, motif, tel_n=100, tel_r=0.6, tel_mm=0):
    seq_str = (sequence or "").upper()
    motif_forward = (motif or "").upper()
    motif_length = len(motif_forward)
    if motif_length == 0:
        return dict(passed=False, side=None, right_pass=False, left_pass=False)

    terminal_len = min(len(seq_str), tel_n * motif_length)
    left_terminal = seq_str[:terminal_len]
    right_terminal = seq_str[-terminal_len:] if terminal_len > 0 else ""
    terminal_sequences = [left_terminal]
    if right_terminal != left_terminal:
        terminal_sequences.append(right_terminal)

    forward_patterns = set(motif_rotations(motif_forward))
    reverse_patterns = set(motif_rotations(str(Seq(motif_forward).reverse_complement())))
    required_hits = math.ceil(tel_n * tel_r)

    best_forward_hits = max(
        count_terminal_telomere_hits(term, forward_patterns, motif_length, tel_mm)
        for term in terminal_sequences
    )
    best_reverse_hits = max(
        count_terminal_telomere_hits(term, reverse_patterns, motif_length, tel_mm)
        for term in terminal_sequences
    )

    right_pass = best_forward_hits >= required_hits
    left_pass = best_reverse_hits >= required_hits

    if right_pass and (not left_pass or best_forward_hits >= best_reverse_hits):
        side = "right"
    elif left_pass:
        side = "left"
    else:
        side = None

    return dict(
        passed=right_pass or left_pass,
        side=side,
        right_pass=right_pass,
        left_pass=left_pass,
    )

def process_file(input_file, motif, temp_dir, batch_size=1000,
                 tel_n=100, tel_r=0.6, tel_mm=0):
    """Process a single split file to extract terminal telomeric reads."""
    base_name = os.path.basename(input_file)
    left_output = os.path.join(temp_dir, "left_" + base_name)
    right_output = os.path.join(temp_dir, "right_" + base_name)
    stats_output = os.path.join(temp_dir, "stats_" + base_name + ".txt")
    
    left_reads = []
    right_reads = []
    total = 0
    both_telo = 0

    try:
        with open(input_file, 'r') as handle:
            record_iter = SeqIO.parse(handle, 'fasta')
            
            while True:
                # Read a batch of reads
                batch = []
                for _ in range(batch_size):
                    try:
                        batch.append(next(record_iter))
                    except StopIteration:
                        break
                
                if not batch:
                    break  # No more reads
                
                # Process each read in the batch
                for record in batch:
                    total += 1
                    seq_str = str(record.seq).upper()

                    terminal_result = classify_read_by_terminal_telomere(
                        seq_str,
                        motif,
                        tel_n,
                        tel_r,
                        tel_mm
                    )
                    if terminal_result["right_pass"]:
                        right_reads.append(record)
                    if terminal_result["left_pass"]:
                        left_reads.append(record)
                    if terminal_result["right_pass"] and terminal_result["left_pass"]:
                        both_telo += 1
        
        # Write results
        with open(left_output, 'w') as f:
            SeqIO.write(left_reads, f, 'fasta')
        
        with open(right_output, 'w') as f:
            SeqIO.write(right_reads, f, 'fasta')
        
        # Write statistics
        with open(stats_output, 'w') as f:
            f.write("total=" + str(total) + "\\n")
            f.write("left=" + str(len(left_reads)) + "\\n")
            f.write("right=" + str(len(right_reads)) + "\\n")
            f.write("both=" + str(both_telo) + "\\n")
        
        print("Processed " + input_file + ": L=" + str(len(left_reads)) + ", R=" + str(len(right_reads)))
        
    except Exception as e:
        print("Error processing " + input_file + ": " + str(e))

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python process_single_file.py <input_file>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    process_file(
        input_file,
        motif="{self.motif}",
        temp_dir="{temp_dir}",
        batch_size={self.batch_size},
        tel_n={self.tel_n},
        tel_r={self.tel_r},
        tel_mm={self.tel_mm}
    )
'''
        
        with open(script_path, 'w') as f:
            f.write(script_content)
        
        return script_path
    
    def _merge_results(self):
        """Merge results from all parallel processes, ordered by platform (HiFi first, ONT second)"""
        print(f"\n[Part1-NEW] Merging results...")
        
        temp_dir = os.path.join(self.telo_reads_dir, "temp_parallel")
        
        # Collect statistics
        stats_files = glob.glob(os.path.join(temp_dir, "stats_*.txt"))
        for stats_file in stats_files:
            try:
                with open(stats_file, 'r') as f:
                    for line in f:
                        if '=' in line:
                            key, value = line.strip().split('=')
                            if key == 'total':
                                self.stats['total_reads'] += int(value)
                            elif key == 'left':
                                self.stats['left_telo'] += int(value)
                            elif key == 'right':
                                self.stats['right_telo'] += int(value)
                            elif key == 'both':
                                self.stats['both_telo'] += int(value)
            except Exception as e:
                print(f"Warning: Error reading stats from {stats_file}: {e}")
        
        # Calculate non-telomeric
        self.stats['non_telo'] = (
            self.stats['total_reads']
            - self.stats['left_telo']
            - self.stats['right_telo']
            + self.stats['both_telo']
        )
        
        # Merge left telomeric reads to temp1 file (platform-ordered)
        print(f"[Part1-NEW] Merging left telomeric reads (HiFi first, ONT second)...")
        with open(self.temp_left_output, 'w') as outfile, \
             open(self.temp_left_hifi, 'w') as hifi_out, \
             open(self.temp_left_ont, 'w') as ont_out:
            # First: HiFi reads
            for input_file in self.hifi_files:
                base_name = os.path.basename(input_file)
                left_file = os.path.join(temp_dir, f"left_{base_name}")
                if os.path.exists(left_file) and os.path.getsize(left_file) > 0:
                    try:
                        for record in SeqIO.parse(left_file, 'fasta'):
                            SeqIO.write(record, outfile, 'fasta')
                            SeqIO.write(record, hifi_out, 'fasta')  # Also save to HiFi-specific file
                    except Exception as e:
                        print(f"Warning: Error reading {left_file}: {e}")
            
            # Second: ONT reads
            for input_file in self.ont_files:
                base_name = os.path.basename(input_file)
                left_file = os.path.join(temp_dir, f"left_{base_name}")
                if os.path.exists(left_file) and os.path.getsize(left_file) > 0:
                    try:
                        for record in SeqIO.parse(left_file, 'fasta'):
                            SeqIO.write(record, outfile, 'fasta')
                            SeqIO.write(record, ont_out, 'fasta')  # Also save to ONT-specific file
                    except Exception as e:
                        print(f"Warning: Error reading {left_file}: {e}")
        
        # Merge right telomeric reads to temp1 file (platform-ordered)
        print(f"[Part1-NEW] Merging right telomeric reads (HiFi first, ONT second)...")
        with open(self.temp_right_output, 'w') as outfile, \
             open(self.temp_right_hifi, 'w') as hifi_out, \
             open(self.temp_right_ont, 'w') as ont_out:
            # First: HiFi reads
            for input_file in self.hifi_files:
                base_name = os.path.basename(input_file)
                right_file = os.path.join(temp_dir, f"right_{base_name}")
                if os.path.exists(right_file) and os.path.getsize(right_file) > 0:
                    try:
                        for record in SeqIO.parse(right_file, 'fasta'):
                            SeqIO.write(record, outfile, 'fasta')
                            SeqIO.write(record, hifi_out, 'fasta')  # Also save to HiFi-specific file
                    except Exception as e:
                        print(f"Warning: Error reading {right_file}: {e}")
            
            # Second: ONT reads
            for input_file in self.ont_files:
                base_name = os.path.basename(input_file)
                right_file = os.path.join(temp_dir, f"right_{base_name}")
                if os.path.exists(right_file) and os.path.getsize(right_file) > 0:
                    try:
                        for record in SeqIO.parse(right_file, 'fasta'):
                            SeqIO.write(record, outfile, 'fasta')
                            SeqIO.write(record, ont_out, 'fasta')  # Also save to ONT-specific file
                    except Exception as e:
                        print(f"Warning: Error reading {right_file}: {e}")
        
        # Clean up temporary directory
        try:
            shutil.rmtree(temp_dir)
            print(f"[Part1-NEW] Temporary files cleaned up")
        except Exception as e:
            print(f"[Part1-NEW] Warning: Could not remove temp directory: {e}")
    
    def _apply_second_filter(self):
        """Apply second-level terminal telomere ratio filter to telomeric reads"""
        print(f"\n[Part1-NEW] Applying second-level terminal telomere ratio filter...")
        print(f"  Motif: {self.motif}")
        print(f"  Reverse complement: {get_reverse_complement(self.motif)}")
        print(f"  Terminal units (--tel-n): {self.tel_n}")
        print(f"  Terminal ratio (--tel-r): {self.tel_r}")
        print(f"  Terminal mismatch (--tel-mm): {self.tel_mm}")
        print()
        
        # Filter left telomeric reads - check anywhere in sequence
        left_stats = self._filter_reads_by_motif_count(
            input_file=self.temp_left_output,
            output_file=self.left_output,
            failed_file=self.temp_left_failed,
            side='left'
        )
        
        # Filter right telomeric reads - check anywhere in sequence
        right_stats = self._filter_reads_by_motif_count(
            input_file=self.temp_right_output,
            output_file=self.right_output,
            failed_file=self.temp_right_failed,
            side='right'
        )
        
        # Filter platform-specific files (HiFi)
        print(f"\n[Part1-NEW] Filtering platform-specific files...")
        self._filter_reads_by_motif_count(
            input_file=self.temp_left_hifi,
            output_file=self.left_hifi_output,
            failed_file=None,  # Don't save failed for platform files
            side='left-hifi'
        )
        self._filter_reads_by_motif_count(
            input_file=self.temp_right_hifi,
            output_file=self.right_hifi_output,
            failed_file=None,
            side='right-hifi'
        )
        
        # Filter platform-specific files (ONT)
        self._filter_reads_by_motif_count(
            input_file=self.temp_left_ont,
            output_file=self.left_ont_output,
            failed_file=None,
            side='left-ont'
        )
        self._filter_reads_by_motif_count(
            input_file=self.temp_right_ont,
            output_file=self.right_ont_output,
            failed_file=None,
            side='right-ont'
        )
        
        # Store filter statistics
        self.filter_stats['left'] = left_stats
        self.filter_stats['right'] = right_stats
        
        # Clean up temp files
        self._cleanup_temp_files()
        
        print(f"[Part1-NEW] Second-level filtering complete")
    
    def _filter_reads_by_motif_count(self, input_file: str, output_file: str, 
                                      failed_file: str, side: str) -> dict:
        """
        Filter reads based on terminal motif-rotation ratio
        
        Args:
            input_file: Input FASTA file (temp1 files)
            output_file: Output filtered FASTA file (final files)
            failed_file: Output file for failed reads (temp2 files)
            side: 'left' or 'right'
        
        Returns:
            Dictionary with statistics
        """
        if not os.path.exists(input_file):
            return {'total': 0, 'passed': 0, 'failed': 0}
        
        if os.path.getsize(input_file) == 0:
            return {'total': 0, 'passed': 0, 'failed': 0}
        
        print(f"[Filter] Processing {side} telomeric reads...")
        
        total_reads = 0
        passed_reads = 0
        passed_records = []
        failed_records = []
        
        with open(input_file, 'r') as f:
            for record in SeqIO.parse(f, 'fasta'):
                total_reads += 1
                seq_str = str(record.seq)
                
                terminal_result = classify_read_by_terminal_telomere(
                    seq_str,
                    self.motif,
                    self.tel_n,
                    self.tel_r,
                    self.tel_mm,
                )
                tel_hits = max(
                    terminal_result["forward_hits"],
                    terminal_result["reverse_hits"],
                )
                tel_ratio = max(
                    terminal_result["forward_ratio"],
                    terminal_result["reverse_ratio"],
                )

                if side.startswith("left"):
                    side_passed = terminal_result["left_pass"]
                elif side.startswith("right"):
                    side_passed = terminal_result["right_pass"]
                else:
                    side_passed = terminal_result["passed"]

                if side_passed:
                    passed_reads += 1
                    new_record = SeqRecord(
                        seq=record.seq,
                        id=record.id,
                        description=f"{record.description} tel_hits={tel_hits} tel_ratio={tel_ratio:.3f}"
                    )
                    passed_records.append(new_record)
                else:
                    failed_record = SeqRecord(
                        seq=record.seq,
                        id=record.id,
                        description=f"{record.description} tel_hits={tel_hits} tel_ratio={tel_ratio:.3f} FAILED"
                    )
                    failed_records.append(failed_record)
        
        # Sort passed reads by ID for consistent ordering
        passed_records.sort(key=lambda rec: rec.id)
        
        # Write passed reads to final output
        with open(output_file, 'w') as f:
            SeqIO.write(passed_records, f, 'fasta')
        
        # Write failed reads to temp2 file (if specified)
        if failed_file:
            with open(failed_file, 'w') as f:
                SeqIO.write(failed_records, f, 'fasta')
        
        filtered_reads = total_reads - passed_reads
        
        print(f"[Filter] {side.upper()} results:")
        print(f"  Total reads: {total_reads}")
        if total_reads > 0:
            print(f"  Passed (terminal ratio >= {self.tel_r}): {passed_reads} ({passed_reads/total_reads*100:.1f}%)")
            print(f"  Failed (terminal ratio < {self.tel_r}): {filtered_reads} ({filtered_reads/total_reads*100:.1f}%)")
            print(f"  Note: Output sorted by read ID")
        print()
        
        return {
            'total': total_reads,
            'passed': passed_reads,
            'failed': filtered_reads
        }
    
    def _cleanup_temp_files(self):
        """Clean up temporary files after second filter"""
        temp_files = [
            self.temp_left_output,
            self.temp_right_output,
            self.temp_left_failed,
            self.temp_right_failed,
            self.temp_left_hifi,
            self.temp_left_ont,
            self.temp_right_hifi,
            self.temp_right_ont
        ]
        
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as e:
                    print(f"Warning: Could not remove temp file {temp_file}: {e}")
    
    def _create_global_files(self):
        """
        Create Global merged files with platform grouping:
        - Global.left.telo.reads.fa = HiFi left + RC(HiFi right) + ONT left + RC(ONT right)
        - Global.right.telo.reads.fa = HiFi right + RC(HiFi left) + ONT right + RC(ONT left)
        """
        print(f"\n[Part1-NEW] Creating Global merged files (platform-grouped)...")
        
        # Create Global.left.telo.reads.fa
        print(f"[Global] Creating Global.left.telo.reads.fa...")
        print(f"  Order: HiFi left → RC(HiFi right) → ONT left → RC(ONT right)")
        with open(self.global_left_output, 'w') as out_f:
            # 1. HiFi left reads
            if os.path.exists(self.left_hifi_output):
                for record in SeqIO.parse(self.left_hifi_output, 'fasta'):
                    SeqIO.write(record, out_f, 'fasta')
            
            # 2. RC(HiFi right reads)
            if os.path.exists(self.right_hifi_output):
                for record in SeqIO.parse(self.right_hifi_output, 'fasta'):
                    rc_record = SeqRecord(
                        seq=record.seq.reverse_complement(),
                        id=record.id,
                        description=record.description + " [RC]"
                    )
                    SeqIO.write(rc_record, out_f, 'fasta')
            
            # 3. ONT left reads
            if os.path.exists(self.left_ont_output):
                for record in SeqIO.parse(self.left_ont_output, 'fasta'):
                    SeqIO.write(record, out_f, 'fasta')
            
            # 4. RC(ONT right reads)
            if os.path.exists(self.right_ont_output):
                for record in SeqIO.parse(self.right_ont_output, 'fasta'):
                    rc_record = SeqRecord(
                        seq=record.seq.reverse_complement(),
                        id=record.id,
                        description=record.description + " [RC]"
                    )
                    SeqIO.write(rc_record, out_f, 'fasta')
        
        # Create Global.right.telo.reads.fa
        print(f"[Global] Creating Global.right.telo.reads.fa...")
        print(f"  Order: HiFi right → RC(HiFi left) → ONT right → RC(ONT left)")
        with open(self.global_right_output, 'w') as out_f:
            # 1. HiFi right reads
            if os.path.exists(self.right_hifi_output):
                for record in SeqIO.parse(self.right_hifi_output, 'fasta'):
                    SeqIO.write(record, out_f, 'fasta')
            
            # 2. RC(HiFi left reads)
            if os.path.exists(self.left_hifi_output):
                for record in SeqIO.parse(self.left_hifi_output, 'fasta'):
                    rc_record = SeqRecord(
                        seq=record.seq.reverse_complement(),
                        id=record.id,
                        description=record.description + " [RC]"
                    )
                    SeqIO.write(rc_record, out_f, 'fasta')
            
            # 3. ONT right reads
            if os.path.exists(self.right_ont_output):
                for record in SeqIO.parse(self.right_ont_output, 'fasta'):
                    SeqIO.write(record, out_f, 'fasta')
            
            # 4. RC(ONT left reads)
            if os.path.exists(self.left_ont_output):
                for record in SeqIO.parse(self.left_ont_output, 'fasta'):
                    rc_record = SeqRecord(
                        seq=record.seq.reverse_complement(),
                        id=record.id,
                        description=record.description + " [RC]"
                    )
                    SeqIO.write(rc_record, out_f, 'fasta')
        
        # Count reads in Global files
        global_left_count = sum(1 for _ in SeqIO.parse(self.global_left_output, 'fasta'))
        global_right_count = sum(1 for _ in SeqIO.parse(self.global_right_output, 'fasta'))
        
        print(f"[Global] Global.left.telo.reads.fa: {global_left_count} reads")
        print(f"[Global] Global.right.telo.reads.fa: {global_right_count} reads")
        print(f"[Global] Global files created successfully (platform-grouped)")
    
    def _write_log(self):
        """Write processing log"""
        with open(self.log_file, 'w') as f:
            f.write("TelSeekerPart1 - Telomeric Reads Extraction Log (Terminal-ratio)\n")
            f.write("=" * 60 + "\n\n")
            
            # Algorithm description
            f.write("ALGORITHM: Terminal read-end motif ratio\n")
            f.write("-" * 60 + "\n")
            f.write(f"Window markers:\n")
            f.write(f"  Right (forward): {self.pat_right}\n")
            f.write(f"  Left (reverse):  {self.pat_left}\n")
            f.write(f"Terminal-ratio configuration:\n")
            f.write(f"  Terminal units (--tel-n): {self.tel_n}\n")
            f.write(f"  Terminal ratio (--tel-r): {self.tel_r}\n")
            f.write(f"  Terminal mismatch (--tel-mm): {self.tel_mm}\n")
            f.write(f"  Terminal length per read end: {self.tel_n * len(self.motif)} bp\n")
            f.write(f"Scan method: Greedy motif-rotation scan at both physical read ends\n")
            f.write(f"Classification: Based on hits / tel_n at read ends\n")
            f.write(f"Output order:\n")
            f.write(f"  - Platform level: HiFi first, ONT second\n")
            f.write(f"  - Within platform: Sorted by read ID (alphabetical)\n")
            f.write(f"\n")
            
            # First-level terminal-ratio filtering parameters and statistics
            f.write("FIRST-LEVEL FILTERING (terminal-ratio)\n")
            f.write("-" * 60 + "\n")
            f.write(f"Parameters:\n")
            f.write(f"  Motif: {self.motif}\n")
            f.write(f"  Terminal units: {self.tel_n}\n")
            f.write(f"  Terminal ratio: {self.tel_r}\n")
            f.write(f"  Terminal mismatch: {self.tel_mm}\n")
            f.write(f"  Threads: {self.threads}\n")
            f.write(f"\n")
            f.write(f"Statistics:\n")
            f.write(f"  Total reads processed: {self.stats['total_reads']}\n")
            f.write(f"  Left telomeric reads: {self.stats['left_telo']}\n")
            f.write(f"  Right telomeric reads: {self.stats['right_telo']}\n")
            f.write(f"  Both ends telomeric (excluded): {self.stats['both_telo']}\n")
            f.write(f"  Non-telomeric reads: {self.stats['non_telo']}\n")
            f.write(f"\n")
            f.write(f"Temp output files (Level 1):\n")
            f.write(f"  Left reads: {self.temp_left_output} [cleaned after Level 2]\n")
            f.write(f"  Right reads: {self.temp_right_output} [cleaned after Level 2]\n")
            f.write(f"\n")
            
            # Second-level motif count filtering (if enabled)
            if self.enable_second_filter:
                f.write("SECOND-LEVEL FILTERING (terminal-ratio)\n")
                f.write("-" * 60 + "\n")
                f.write(f"Parameters:\n")
                f.write(f"  Motif: {self.motif}\n")
                f.write(f"  Reverse complement: {get_reverse_complement(self.motif)}\n")
                f.write(f"  Terminal units: {self.tel_n}\n")
                f.write(f"  Terminal ratio: {self.tel_r}\n")
                f.write(f"  Terminal mismatch: {self.tel_mm}\n")
                f.write(f"  Scan region: Read ends\n")
                f.write(f"\n")
                
                # Left reads statistics
                left_total = self.filter_stats['left']['total']
                left_passed = self.filter_stats['left']['passed']
                left_failed = self.filter_stats['left']['failed']
                
                f.write(f"Left telomeric reads:\n")
                f.write(f"  Input reads: {left_total}\n")
                if left_total > 0:
                    f.write(f"  Passed (ratio >= {self.tel_r}): {left_passed} ({left_passed/left_total*100:.2f}%)\n")
                    f.write(f"  Failed (ratio < {self.tel_r}): {left_failed} ({left_failed/left_total*100:.2f}%)\n")
                else:
                    f.write(f"  Passed: 0\n")
                    f.write(f"  Failed: 0\n")
                f.write(f"  Input file: {self.temp_left_output}\n")
                f.write(f"  Passed output (final): {self.left_output}\n")
                f.write(f"  Failed output (temp): {self.temp_left_failed} [cleaned]\n")
                f.write(f"\n")
                
                # Right reads statistics
                right_total = self.filter_stats['right']['total']
                right_passed = self.filter_stats['right']['passed']
                right_failed = self.filter_stats['right']['failed']
                
                f.write(f"Right telomeric reads:\n")
                f.write(f"  Input reads: {right_total}\n")
                if right_total > 0:
                    f.write(f"  Passed (ratio >= {self.tel_r}): {right_passed} ({right_passed/right_total*100:.2f}%)\n")
                    f.write(f"  Failed (ratio < {self.tel_r}): {right_failed} ({right_failed/right_total*100:.2f}%)\n")
                else:
                    f.write(f"  Passed: 0\n")
                    f.write(f"  Failed: 0\n")
                f.write(f"  Input file: {self.temp_right_output}\n")
                f.write(f"  Passed output (final): {self.right_output}\n")
                f.write(f"  Failed output (temp): {self.temp_right_failed} [cleaned]\n")
                f.write(f"\n")
                
                # Overall summary
                total_input = left_total + right_total
                total_passed = left_passed + right_passed
                total_failed = left_failed + right_failed
                
                f.write(f"Overall summary:\n")
                f.write(f"  Total input reads: {total_input}\n")
                if total_input > 0:
                    f.write(f"  Total passed reads: {total_passed} ({total_passed/total_input*100:.2f}%)\n")
                    f.write(f"  Total failed reads: {total_failed} ({total_failed/total_input*100:.2f}%)\n")
                else:
                    f.write(f"  Total passed reads: 0\n")
                    f.write(f"  Total failed reads: 0\n")
                f.write(f"\n")
                f.write(f"FINAL OUTPUT FILES:\n")
                f.write(f"-" * 60 + "\n")
                f.write(f"Standard files (platform-ordered: HiFi→ONT):\n")
                f.write(f"  {self.left_output}\n")
                f.write(f"  {self.right_output}\n")
                f.write(f"\n")
                f.write(f"Global merged files (platform-grouped):...\n")
                f.write(f"  {self.global_left_output}\n")
                f.write(f"    Structure: HiFi left → RC(HiFi right) → ONT left → RC(ONT right)\n")
                f.write(f"  {self.global_right_output}\n")
                f.write(f"    Structure: HiFi right → RC(HiFi left) → ONT right → RC(ONT left)\n")
                f.write(f"  Rationale: Platform grouping prioritizes high-quality HiFi reads\n")
                f.write(f"\n")
                f.write(f"Platform-specific files:\n")
                f.write(f"  {self.left_hifi_output}\n")
                f.write(f"  {self.right_hifi_output}\n")
                f.write(f"  {self.left_ont_output}\n")
                f.write(f"  {self.right_ont_output}\n")
                f.write(f"\n")
                f.write(f"Note: All temporary files (temp1.*, temp2.*) have been cleaned up.\n")
        
        print(f"[Part1-NEW] Log written to: {self.log_file}")
    
    def _print_summary(self):
        """Print summary statistics"""
        total = self.stats['total_reads']
        left = self.stats['left_telo']
        right = self.stats['right_telo']
        both = self.stats['both_telo']
        non = self.stats['non_telo']
        
        print(f"\n{'='*60}")
        print(f"SUMMARY (Terminal-ratio Algorithm)")
        print(f"{'='*60}")
        print(f"\nFirst-level filtering (terminal_ratio):")
        print(f"  Total reads processed:           {total:>10}")
        
        if total > 0:
            print(f"  Left telomeric reads:            {left:>10} ({left/total*100:>5.1f}%)")
            print(f"  Right telomeric reads:           {right:>10} ({right/total*100:>5.1f}%)")
            print(f"  Both directions telomeric:       {both:>10} ({both/total*100:>5.1f}%)")
            print(f"  Non-telomeric reads:             {non:>10} ({non/total*100:>5.1f}%)")
        else:
            print(f"  Left telomeric reads:            {left:>10}")
            print(f"  Right telomeric reads:           {right:>10}")
            print(f"  Both directions telomeric:       {both:>10}")
            print(f"  Non-telomeric reads:             {non:>10}")
            print(f"\n  WARNING: No reads were processed. Check for errors above.")
        
        # Second filter summary
        if self.enable_second_filter:
            left_total = self.filter_stats['left']['total']
            left_passed = self.filter_stats['left']['passed']
            right_total = self.filter_stats['right']['total']
            right_passed = self.filter_stats['right']['passed']
            total_filter_input = left_total + right_total
            total_filter_passed = left_passed + right_passed
            
            print(f"\nSecond-level filtering (terminal ratio >= {self.tel_r}):")
            print(f"  Total input reads:               {total_filter_input:>10}")
            if total_filter_input > 0:
                print(f"  Total passed reads:              {total_filter_passed:>10} ({total_filter_passed/total_filter_input*100:>5.1f}%)")
                left_pct = left_passed / left_total * 100 if left_total else 0.0
                right_pct = right_passed / right_total * 100 if right_total else 0.0
                print(f"    Left passed:                   {left_passed:>10} ({left_pct:>5.1f}%)")
                print(f"    Right passed:                  {right_passed:>10} ({right_pct:>5.1f}%)")
            else:
                print(f"  Total passed reads:              {total_filter_passed:>10}")
        
        print(f"{'='*60}")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="TelSeekerPart1: Extract telomeric reads using terminal read-end ratios",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument(
        '-m', '--motif',
        required=True,
        help='Telomere repeat motif (e.g., TTAGGG)'
    )
    
    parser.add_argument(
        '--out',
        required=True,
        help='Output directory (where DEGAP placed reads_part/)'
    )
    
    parser.add_argument(
        '-t', '--threads',
        type=int,
        default=20,
        help='Number of threads for parallel processing (default: 20)'
    )
    
    parser.add_argument(
        '--threshold',
        type=float,
        default=None,
        help='Compatibility option; ignored by terminal-ratio mode'
    )
    
    parser.add_argument(
        '--check-length',
        type=int,
        default=None,
        help='Compatibility option; ignored by terminal-ratio mode'
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        default=1000,
        help='Number of reads to read at once for each batch (default: 1000)'
    )
    
    parser.add_argument(
        '--enable-second-filter',
        action='store_true',
        help='Enable second-level terminal-ratio filtering (default: enabled)'
    )
    
    parser.add_argument(
        '--disable-second-filter',
        action='store_true',
        help='Disable second-level motif count filtering'
    )
    
    parser.add_argument(
        '--min-motif-count',
        type=int,
        default=None,
        help='Compatibility option; ignored by terminal-ratio mode'
    )

    parser.add_argument(
        '-tn', '--tel-n',
        type=int,
        default=100,
        help='Number of motif-length units checked at each read end (default: 100)'
    )

    parser.add_argument(
        '-tr', '--tel-r',
        type=float,
        default=0.6,
        help='Minimum terminal motif-unit hit ratio, computed as hits / tel-n (default: 0.6)'
    )

    parser.add_argument(
        '-tmm', '--tel-mm',
        type=int,
        choices=[0, 1],
        default=0,
        help='Allowed mismatches per motif-length unit, 0 or 1 (default: 0)'
    )
    
    parser.add_argument(
        '--overlapping',
        action='store_true',
        help='Use overlapping count in second-level filter (default: non-overlapping)'
    )
    
    args = parser.parse_args()
    
    # Handle filter enable/disable logic
    if args.disable_second_filter:
        enable_second_filter = False
    elif args.enable_second_filter:
        enable_second_filter = True
    else:
        enable_second_filter = None
    
    # Validate output directory
    if not os.path.exists(args.out):
        print(f"Error: Output directory not found: {args.out}")
        sys.exit(1)
    
    # Create extractor and run
    extractor = TeloReadsExtractor(
        output_dir=args.out,
        motif=args.motif,
        threads=args.threads,
        trc_threshold=args.threshold,
        check_length=args.check_length,
        batch_size=args.batch_size,
        enable_second_filter=enable_second_filter,
        min_motif_count=args.min_motif_count,
        overlapping=args.overlapping,
        tel_n=args.tel_n,
        tel_r=args.tel_r,
        tel_mm=args.tel_mm,
    )
    
    extractor.run()


if __name__ == '__main__':
    main()
