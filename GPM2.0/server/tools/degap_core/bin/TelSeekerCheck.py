#!/usr/bin/env python3
"""
TelSeekerCheck.py - Prepare chromosome-end telomere review files

This script extracts chromosome-end sequences and telomere motif plots for
manual review before TelSeeker extension.

Default method:
- Extract 100kb from each chromosome end
- Count the motif and reverse-complement motif in fixed 10kb bins
- Generate whole-genome motif distribution plots for visual review using the
  same 1kb plotting window as the final TelSeeker report

Usage:
    python TelSeekerCheck.py --genome genome.fa --motif TTAGGG --out output_dir

Output:
    output_dir/genome.telomere.check/
        ├── genome.telomere.check.left.2kb.fa  # Left end sequences (2kb)
        ├── genome.telomere.check.right.2kb.fa # Right end sequences (2kb)
        ├── all_chromosomes_combined.png       # Whole-genome motif plot
        └── <chromosome>_telomere_motif.png    # Per-chromosome motif plots
"""

import os
import sys
import re
import math
import argparse
from pathlib import Path
from typing import List, Tuple
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from TelSeekerMotifPlot import (
    DEFAULT_MOTIF_PLOT_WINDOW_SIZE,
    generate_motif_distribution_plots,
)


# ============================================================================
# TRC Calculation Functions (Topsicle-based algorithm)
# ============================================================================

def _pattern_scramble_telo(pattern: str, cut_length: int) -> List[str]:
    """
    Generate all k-mer permutations of telomere motif (including reverse complement).
    
    Args:
        pattern: Telomere motif (e.g., 'TTAGGG')
        cut_length: Length of k-mers to generate
        
    Returns:
        Sorted list of unique k-mers
    """
    pattern = (pattern or "").upper()
    if not pattern:
        return []
    
    cut_length = max(1, cut_length)
    extended = pattern * 2
    kmers = set()
    
    # Generate cyclic rotations
    for i in range(len(pattern)):
        fragment = extended[i : i + cut_length]
        if len(fragment) == cut_length:
            kmers.add(fragment)
    
    # Add reverse complements
    kmers.update(str(Seq(kmer).reverse_complement()) for kmer in list(kmers))
    return sorted(kmers)


def patterns_to_search_topsicle(motif: str, cut_length: int) -> List[str]:
    """
    Generate regex patterns for Topsicle-based telomere detection.

    This non-overlapping implementation mirrors the original Topsicle behaviour:
    each pattern is matched in a classic left-to-right scan without lookahead,
    so successive hits do not share bases.

    Args:
        motif: Telomere motif
        cut_length: Length of k-mers

    Returns:
        List of escaped regex patterns for non-overlapping matching
    """
    kmers = _pattern_scramble_telo(motif, cut_length)
    return [re.escape(kmer) for kmer in kmers]


def calculate_trc(sequence: str, motif: str, kmer_length: int, check_length: int = 1000) -> float:
    """
    Calculate Telomere Repeat Content (TRC) using Topsicle method.

    This function implements the exact algorithm from Topsicle:
    1. Generate all telomere k-mer patterns (including reverse complements)
    2. Calculate match density for each pattern
    3. Return the maximum density as TRC score

    Args:
        sequence: DNA sequence to check
        motif: Telomeric motif (e.g., 'TTAGGG')
        kmer_length: Length of k-mers to use (typically motif_length - 2)
        check_length: Length of sequence to check from the start

    Returns:
        TRC score between 0 and infinity (typically 0-1 range)
    """
    # Truncate sequence to check_length
    seq_to_check = sequence[:min(len(sequence), check_length)].upper()

    if len(seq_to_check) < kmer_length:
        return 0.0

    # Generate Topsicle patterns (non-overlapping)
    pattern_all = patterns_to_search_topsicle(motif, kmer_length)
    compiled_patterns = [re.compile(pattern) for pattern in pattern_all]

    # Calculate TRC using Topsicle method: max density across all patterns
    # Ensure ratio_perfect_hit is at least 1.0
    ratio_perfect_hit = max(1.0, len(seq_to_check) / len(motif))
    max_trc = 0.0

    for pattern in compiled_patterns:
        matches = len(pattern.findall(seq_to_check))
        pattern_trc = matches / ratio_perfect_hit if ratio_perfect_hit > 0 else 0.0
        max_trc = max(max_trc, pattern_trc)

    return max_trc


def find_all_occurrences(seq: str, pattern: str) -> List[int]:
    """
    Find all occurrences of pattern in sequence (overlapping allowed for finding positions).

    Args:
        seq: DNA sequence to search
        pattern: Pattern to find

    Returns:
        List of starting positions
    """
    positions = []
    start = 0
    while True:
        pos = seq.find(pattern, start)
        if pos == -1:
            break
        positions.append(pos)
        start = pos + 1  # Allow overlapping search
    return positions


def calculate_trc_window_based(sequence: str, motif: str, kmer_length: int,
                                window_flank: int = 500) -> Tuple[float, int]:
    """
    Calculate maximum TRC using window-based scanning method.

    This method:
    1. Generates window markers (motif*2 and its reverse complement)
    2. Finds all marker positions in the sequence
    3. Creates windows around each marker (flank + marker + flank)
    4. Calculates TRC for each window
    5. Returns the maximum TRC found

    Args:
        sequence: DNA sequence to check (e.g., chromosome-end segment)
        motif: Telomeric motif (e.g., 'TTAGGG')
        kmer_length: Length of k-mers for TRC calculation
        window_flank: Flank size on each side of marker (default: 500bp)

    Returns:
        Tuple of (max_trc, num_windows_found)
    """
    seq_str = sequence.upper()

    # Generate window markers (motif*2)
    pat_right = motif * 2  # e.g., TTAGGGTTAGGG
    pat_left = str(Seq(pat_right).reverse_complement())  # e.g., CCCTAACCCTAA

    marker_len = len(pat_right)
    target_window_size = 2 * window_flank + marker_len

    # Find all marker positions
    right_positions = find_all_occurrences(seq_str, pat_right)
    left_positions = find_all_occurrences(seq_str, pat_left)

    total_windows = len(right_positions) + len(left_positions)

    if total_windows == 0:
        return 0.0, 0

    max_trc = 0.0

    # Process right marker windows (forward)
    for pos in right_positions:
        # Extract window with fixed size, compensating for insufficient flanks
        ideal_start = pos - window_flank
        ideal_end = pos + marker_len + window_flank

        if ideal_start < 0:
            # Upstream insufficient, start from 0 and extend downstream
            window_start = 0
            window_end = min(len(seq_str), target_window_size)
        elif ideal_end > len(seq_str):
            # Downstream insufficient, end at sequence end and extend upstream
            window_end = len(seq_str)
            window_start = max(0, len(seq_str) - target_window_size)
        else:
            # Both flanks sufficient
            window_start = ideal_start
            window_end = ideal_end

        window_seq = seq_str[window_start:window_end]

        if len(window_seq) >= marker_len:
            # Don't pass check_length - use the full window sequence
            window_trc = calculate_trc(window_seq, motif, kmer_length, len(window_seq))
            max_trc = max(max_trc, window_trc)

    # Process left marker windows (reverse)
    for pos in left_positions:
        # Extract window with fixed size, compensating for insufficient flanks
        ideal_start = pos - window_flank
        ideal_end = pos + marker_len + window_flank

        if ideal_start < 0:
            # Upstream insufficient, start from 0 and extend downstream
            window_start = 0
            window_end = min(len(seq_str), target_window_size)
        elif ideal_end > len(seq_str):
            # Downstream insufficient, end at sequence end and extend upstream
            window_end = len(seq_str)
            window_start = max(0, len(seq_str) - target_window_size)
        else:
            # Both flanks sufficient
            window_start = ideal_start
            window_end = ideal_end

        window_seq = seq_str[window_start:window_end]

        if len(window_seq) >= marker_len:
            # Don't pass check_length - use the full window sequence
            window_trc = calculate_trc(window_seq, motif, kmer_length, len(window_seq))
            max_trc = max(max_trc, window_trc)

    return max_trc, total_windows


def _count_overlapping_motif(sequence: str, motif: str) -> int:
    """Count overlapping motif hits in a sequence."""
    if not motif:
        return 0
    return len(re.findall(f"(?={re.escape(motif)})", sequence, re.IGNORECASE))


def count_telomere_repeat_windows(sequence: str, motif: str,
                                  window_size: int = 10000) -> List[dict]:
    """
    Count forward and reverse-complement telomere repeats in fixed windows.

    The window-count view mirrors the TeloExplorer/tidk style signal used for
    manual telomere review: it preserves where repeat density is concentrated
    instead of reducing the whole end to one local TRC maximum.
    """
    if window_size <= 0:
        raise ValueError("window_size must be greater than 0")

    seq_str = (sequence or "").upper()
    motif_forward = (motif or "").upper()
    motif_reverse = str(Seq(motif_forward).reverse_complement()) if motif_forward else ""

    windows = []
    for start in range(0, len(seq_str), window_size):
        end = min(start + window_size, len(seq_str))
        window_seq = seq_str[start:end]
        forward_count = _count_overlapping_motif(window_seq, motif_forward)
        reverse_count = _count_overlapping_motif(window_seq, motif_reverse)
        total_count = forward_count + reverse_count
        window_len_kb = max((end - start) / 1000.0, 0.001)

        windows.append({
            "start": start,
            "end": end,
            "forward_count": forward_count,
            "reverse_count": reverse_count,
            "total_count": total_count,
            "density_per_kb": total_count / window_len_kb,
        })

    return windows


def classify_terminal_telomere_signal(windows: List[dict], end: str,
                                      terminal_window_count: int = 3,
                                      min_terminal_repeats: int = 100,
                                      min_terminal_density: float = 10.0,
                                      min_terminal_to_internal_ratio: float = 3.0) -> dict:
    """
    Classify one chromosome end from fixed-window telomere repeat counts.

    A telomeric call requires enough repeats at the physical end and enrichment
    over internal windows in the checked region. Strong repeat signal away from
    the end is treated as a warning signal instead of proof of a terminal
    telomere.
    """
    if terminal_window_count <= 0:
        raise ValueError("terminal_window_count must be greater than 0")

    if not windows:
        return {
            "status": "untelomeric",
            "terminal_repeat_count": 0,
            "terminal_density": 0.0,
            "internal_max_density": 0.0,
            "terminal_to_internal_ratio": 0.0,
            "confidence": "low",
            "reason": "no windows were available for terminal telomere review",
        }

    normalized_end = end.lower()
    if normalized_end not in {"left", "right"}:
        raise ValueError("end must be Left or Right")

    terminal_count = min(terminal_window_count, len(windows))
    if normalized_end == "left":
        terminal_windows = windows[:terminal_count]
        internal_windows = windows[terminal_count:]
    else:
        terminal_windows = windows[-terminal_count:]
        internal_windows = windows[:-terminal_count]

    terminal_repeat_count = sum(window["total_count"] for window in terminal_windows)
    terminal_bases = sum(window["end"] - window["start"] for window in terminal_windows)
    terminal_density = (
        terminal_repeat_count / max(terminal_bases / 1000.0, 0.001)
    )
    internal_max_density = max(
        (window["density_per_kb"] for window in internal_windows),
        default=0.0,
    )
    if internal_max_density <= 0:
        terminal_to_internal_ratio = float("inf") if terminal_density > 0 else 0.0
    else:
        terminal_to_internal_ratio = terminal_density / internal_max_density

    has_terminal_signal = (
        terminal_repeat_count >= min_terminal_repeats
        and terminal_density >= min_terminal_density
    )
    has_terminal_enrichment = (
        internal_max_density <= 0
        or terminal_to_internal_ratio >= min_terminal_to_internal_ratio
    )

    if has_terminal_signal and has_terminal_enrichment:
        confidence = "high" if internal_max_density <= 0 else "medium"
        reason = "terminal windows contain enriched telomere repeat signal"
        status = "telomeric"
    elif has_terminal_signal:
        confidence = "low"
        reason = "telomere repeats are not enriched at the terminal windows"
        status = "uncertain"
    else:
        confidence = "low"
        reason = "terminal windows do not contain enough telomere repeat signal"
        status = "untelomeric"

    return {
        "status": status,
        "terminal_repeat_count": terminal_repeat_count,
        "terminal_density": terminal_density,
        "internal_max_density": internal_max_density,
        "terminal_to_internal_ratio": terminal_to_internal_ratio,
        "confidence": confidence,
        "reason": reason,
    }


# ============================================================================
# Telomere Checker Main Class
# ============================================================================


class TelomereChecker:
    """Prepare chromosome-end sequences and motif plots for manual telomere review."""

    def __init__(self, genome_file: str, motif: str, output_dir: str,
                 trc_threshold: float = 0.7, check_length: int = 100000,
                 extract_length: int = 2000, window_flank: int = 500,
                 window_size: int = 10000, terminal_windows: int = 1,
                 min_terminal_repeats: int = 100,
                 min_terminal_density: float = 10.0,
                 min_terminal_to_internal_ratio: float = 3.0,
                 method: str = "window_count",
                 plot_window_size: int = DEFAULT_MOTIF_PLOT_WINDOW_SIZE,
                 check_name: str = "genome.telomere.check"):
        """
        Initialize TelomereChecker

        Args:
            genome_file: Path to input genome FASTA file
            motif: Telomere repeat motif (e.g., 'TTAGGG')
            output_dir: Output directory
            trc_threshold: TRC threshold for legacy_trc mode (default: 0.7)
            check_length: Length to extract from chromosome end for window scanning (default: 100000bp)
            extract_length: Length to extract for output sequences (default: 2000bp)
            window_flank: Flank size for window creation (default: 500bp)
            window_size: Fixed repeat-count bin size (default: 10000bp)
            terminal_windows: Number of terminal bins used for classification (default: 1)
            min_terminal_repeats: Minimum terminal motif hits for telomeric call
            min_terminal_density: Minimum terminal motif hits per kb for telomeric call
            min_terminal_to_internal_ratio: Required terminal/internal density enrichment
            method: Detection method, either 'window_count' or 'legacy_trc'
            plot_window_size: Whole-genome motif plot window size (default: 1000bp)
            check_name: Output directory and end-sequence filename prefix
        """
        if method not in {"window_count", "legacy_trc"}:
            raise ValueError("method must be 'window_count' or 'legacy_trc'")
        if not check_name or Path(check_name).name != check_name:
            raise ValueError("check_name must be a non-empty directory name")

        self.genome_file = genome_file
        self.motif = motif.upper()
        self.output_dir = output_dir
        self.trc_threshold = trc_threshold
        self.check_length = check_length
        self.extract_length = extract_length
        self.window_flank = window_flank
        self.window_size = window_size
        self.terminal_windows = terminal_windows
        self.min_terminal_repeats = min_terminal_repeats
        self.min_terminal_density = min_terminal_density
        self.min_terminal_to_internal_ratio = min_terminal_to_internal_ratio
        self.method = method
        self.plot_window_size = plot_window_size
        self.check_name = check_name
        self.kmer_length = len(motif) - 2

        # Window markers (motif*2)
        self.pat_right = self.motif * 2
        self.pat_left = str(Seq(self.pat_right).reverse_complement())

        # Results storage
        self.results = []
        self.left_sequences = []
        self.right_sequences = []
        
    def run(self):
        """Run the manual telomere review preparation workflow"""
        print("[TelomereChecker] Starting manual telomere review preparation...")
        print(f"  Genome: {self.genome_file}")
        print(f"  Motif: {self.motif}")
        print("  Window markers:")
        print(f"    Right (forward): {self.pat_right}")
        print(f"    Left (reverse):  {self.pat_left}")
        print(f"  Extract length: {self.extract_length} bp (for output)")
        print(f"  Motif plot window size: {self.plot_window_size} bp")
        print()

        # Step 1: Create output directory
        self._create_output_directory()

        # Remove automatic-call artifacts left by older versions so this
        # directory contains only current manual-review evidence.
        self._remove_legacy_automatic_outputs()

        # Step 2: Extract manual-review sequences. Initial and final checks use
        # this same evidence-only path.
        self._process_genome_for_review()

        # Step 3: Write manual review outputs only.
        self._write_left_sequences()
        self._write_right_sequences()
        self._write_motif_plots()

        # Step 4: Print summary
        self._print_summary()

        print(f"\n[TelomereChecker] Complete! Manual review files saved to: {self.check_dir}")
        
    def _create_output_directory(self):
        """Create output directory structure"""
        self.check_dir = os.path.join(self.output_dir, self.check_name)
        os.makedirs(self.check_dir, exist_ok=True)
        
        print(f"[TelomereChecker] Output directory: {self.check_dir}")

    def _remove_legacy_automatic_outputs(self):
        """Remove obsolete automatic telomere-call files from the check directory."""
        legacy_filenames = [
            "genome.telomere.check.csv",
            "uncertain_chr_end.txt",
        ]
        # In the initial directory, need_extension_chr_end.txt can be the
        # explicit user-supplied task list. Only the final review directory can
        # safely treat it as an obsolete automatic-call artifact.
        if self.check_name == "final.genome.telomere.check":
            legacy_filenames.append("need_extension_chr_end.txt")

        for filename in legacy_filenames:
            legacy_file = Path(self.check_dir) / filename
            if legacy_file.exists():
                legacy_file.unlink()
        
    def _process_genome(self):
        """Process genome and check each chromosome end"""
        print(f"[TelomereChecker] Processing genome...")
        
        try:
            with open(self.genome_file, 'r') as f:
                for record in SeqIO.parse(f, 'fasta'):
                    chr_name = record.id
                    seq_str = str(record.seq)
                    chr_length = len(seq_str)
                    
                    print(f"  Processing {chr_name} ({chr_length} bp)...")
                    
                    # Check left end
                    left_result = self._check_end(chr_name, seq_str, 'Left')
                    self.results.append(left_result)
                    
                    # Extract left sequence
                    left_seq = self._extract_left_sequence(chr_name, seq_str)
                    if left_seq:
                        self.left_sequences.append(left_seq)
                    
                    # Check right end
                    right_result = self._check_end(chr_name, seq_str, 'Right')
                    self.results.append(right_result)
                    
                    # Extract right sequence
                    right_seq = self._extract_right_sequence(chr_name, seq_str)
                    if right_seq:
                        self.right_sequences.append(right_seq)
                        
        except FileNotFoundError:
            print(f"[TelomereChecker] Error: Genome file not found: {self.genome_file}")
            sys.exit(1)
        except Exception as e:
            print(f"[TelomereChecker] Error processing genome: {e}")
            sys.exit(1)

    def _process_genome_for_review(self):
        """Extract chromosome-end sequences without automatic end classification."""
        print("[TelomereChecker] Extracting chromosome-end sequences...")

        try:
            with open(self.genome_file, 'r') as f:
                for record in SeqIO.parse(f, 'fasta'):
                    chr_name = record.id
                    seq_str = str(record.seq)
                    chr_length = len(seq_str)

                    print(f"  Processing {chr_name} ({chr_length} bp)...")

                    left_seq = self._extract_left_sequence(chr_name, seq_str)
                    if left_seq:
                        self.left_sequences.append(left_seq)

                    right_seq = self._extract_right_sequence(chr_name, seq_str)
                    if right_seq:
                        self.right_sequences.append(right_seq)

        except FileNotFoundError:
            print(f"[TelomereChecker] Error: Genome file not found: {self.genome_file}")
            sys.exit(1)
        except Exception as e:
            print(f"[TelomereChecker] Error processing genome: {e}")
            sys.exit(1)
            
    def _check_end(self, chr_name: str, seq_str: str, end: str) -> dict:
        """
        Check one chromosome end for telomeric content using terminal windows.

        Args:
            chr_name: Chromosome name
            seq_str: Full chromosome sequence
            end: 'Left' or 'Right'

        Returns:
            dict with check results including max_trc and num_windows
        """
        # Extract sequence to check from the chromosome end.
        if end == 'Left':
            check_seq = seq_str[:min(self.check_length, len(seq_str))]
        else:  # Right
            check_seq = seq_str[-min(self.check_length, len(seq_str)):]

        # Keep the historical TRC score in the report for continuity.
        max_trc, num_windows = calculate_trc_window_based(
            check_seq,
            self.motif,
            self.kmer_length,
            self.window_flank
        )

        count_windows = count_telomere_repeat_windows(
            check_seq,
            self.motif,
            self.window_size
        )
        classification = classify_terminal_telomere_signal(
            count_windows,
            end,
            terminal_window_count=self.terminal_windows,
            min_terminal_repeats=self.min_terminal_repeats,
            min_terminal_density=self.min_terminal_density,
            min_terminal_to_internal_ratio=self.min_terminal_to_internal_ratio,
        )

        forward_count = sum(window["forward_count"] for window in count_windows)
        reverse_count = sum(window["reverse_count"] for window in count_windows)
        if forward_count > reverse_count:
            dominant_direction = "forward"
        elif reverse_count > forward_count:
            dominant_direction = "reverse"
        elif forward_count > 0:
            dominant_direction = "mixed"
        else:
            dominant_direction = "none"

        if self.method == "legacy_trc":
            status = "telomeric" if max_trc >= self.trc_threshold else "untelomeric"
            classification["confidence"] = "legacy"
            classification["reason"] = "legacy TRC threshold was used for classification"
        else:
            status = classification["status"]

        return {
            'chr': chr_name,
            'end': end,
            'status': status,
            'method': self.method,
            'trc': max_trc,
            'num_windows': num_windows,
            'check_length': len(check_seq),
            'motif': self.motif,
            'forward_count': forward_count,
            'reverse_count': reverse_count,
            'dominant_direction': dominant_direction,
            'count_windows': len(count_windows),
            'terminal_repeat_count': classification["terminal_repeat_count"],
            'terminal_density': classification["terminal_density"],
            'internal_max_density': classification["internal_max_density"],
            'terminal_to_internal_ratio': classification["terminal_to_internal_ratio"],
            'confidence': classification["confidence"],
            'reason': classification["reason"],
        }
    
    def _extract_left_sequence(self, chr_name: str, seq_str: str) -> SeqRecord:
        """Extract left end sequence"""
        extract_len = min(self.extract_length, len(seq_str))
        left_seq = seq_str[:extract_len]
        
        return SeqRecord(
            seq=Seq(left_seq),
            id=f"{chr_name}_L",
            description=f"Left end of {chr_name}, {extract_len} bp"
        )
    
    def _extract_right_sequence(self, chr_name: str, seq_str: str) -> SeqRecord:
        """Extract right end sequence"""
        extract_len = min(self.extract_length, len(seq_str))
        right_seq = seq_str[-extract_len:]
        
        return SeqRecord(
            seq=Seq(right_seq),
            id=f"{chr_name}_R",
            description=f"Right end of {chr_name}, {extract_len} bp"
        )
    
    def _write_csv_report(self):
        """Write CSV report with terminal window-count results"""
        # Fixed filename: genome.telomere.check.csv
        csv_file = os.path.join(self.check_dir, "genome.telomere.check.csv")

        print(f"\n[TelomereChecker] Writing CSV report: {csv_file}")

        with open(csv_file, 'w') as f:
            # Write results with additional window information
            for result in self.results:
                ratio = result['terminal_to_internal_ratio']
                ratio_text = "Inf" if math.isinf(ratio) else f"{ratio:.2f}"
                line = (f"{result['chr']},{result['end']},{result['status']},"
                       f"TRC={result['trc']:.2f},"
                       f"Windows={result['num_windows']},"
                       f"CheckLen={result['check_length']},"
                       f"Method={result['method']},"
                       f"Motif={result['motif']},"
                       f"ForwardCount={result['forward_count']},"
                       f"ReverseCount={result['reverse_count']},"
                       f"DominantDirection={result['dominant_direction']},"
                       f"CountWindows={result['count_windows']},"
                       f"TerminalRepeatCount={result['terminal_repeat_count']},"
                       f"TerminalDensity={result['terminal_density']:.2f},"
                       f"InternalMaxDensity={result['internal_max_density']:.2f},"
                       f"TerminalToInternalRatio={ratio_text},"
                       f"Confidence={result['confidence']},"
                       f"Reason={result['reason']}\n")
                f.write(line)

        print(f"  Written {len(self.results)} records")
    
    def _write_extension_list(self):
        """Write automatically classified untelomeric ends for final-genome QC."""
        extension_file = os.path.join(self.check_dir, "need_extension_chr_end.txt")
        
        print(f"[TelomereChecker] Writing extension list: {extension_file}")
        
        # Collect untelomeric ends
        untelomeric_ends = []
        for result in self.results:
            if result['status'] == 'untelomeric':
                # Format: Chr01.L or Chr01.R
                end_suffix = 'L' if result['end'] == 'Left' else 'R'
                untelomeric_ends.append(f"{result['chr']}.{end_suffix}")
        
        # Write to file
        with open(extension_file, 'w') as f:
            for end in untelomeric_ends:
                f.write(f"{end}\n")
        
        print(f"  Written {len(untelomeric_ends)} ends requiring extension")

    def _write_uncertain_list(self):
        """Write list of chromosome ends that need manual telomere review"""
        uncertain_file = os.path.join(self.check_dir, "uncertain_chr_end.txt")

        print(f"[TelomereChecker] Writing uncertain list: {uncertain_file}")

        uncertain_ends = []
        for result in self.results:
            if result['status'] == 'uncertain':
                end_suffix = 'L' if result['end'] == 'Left' else 'R'
                uncertain_ends.append(f"{result['chr']}.{end_suffix}")

        with open(uncertain_file, 'w') as f:
            for end in uncertain_ends:
                f.write(f"{end}\n")

        print(f"  Written {len(uncertain_ends)} ends requiring manual review")
    
    def _write_left_sequences(self):
        """Write left end sequences"""
        left_file = os.path.join(self.check_dir, f"{self.check_name}.left.2kb.fa")
        
        print(f"[TelomereChecker] Writing left sequences: {left_file}")
        
        with open(left_file, 'w') as f:
            SeqIO.write(self.left_sequences, f, 'fasta')
        
        print(f"  Written {len(self.left_sequences)} sequences")
    
    def _write_right_sequences(self):
        """Write right end sequences"""
        right_file = os.path.join(self.check_dir, f"{self.check_name}.right.2kb.fa")
        
        print(f"[TelomereChecker] Writing right sequences: {right_file}")
        
        with open(right_file, 'w') as f:
            SeqIO.write(self.right_sequences, f, 'fasta')
        
        print(f"  Written {len(self.right_sequences)} sequences")

    def _write_motif_plots(self):
        """Generate whole-genome motif plots for visual telomere review."""
        print(f"[TelomereChecker] Generating whole-genome motif plots in: {self.check_dir}")

        motif_images, chrom_names, combined_img = generate_motif_distribution_plots(
            Path(self.genome_file),
            self.motif,
            Path(self.check_dir),
            window_size=self.plot_window_size,
        )

        if combined_img:
            print(f"  Written {len(motif_images)} individual plots + 1 combined plot")
        elif chrom_names:
            print(f"  Written {len(motif_images)} individual plots; combined plot was skipped")
        else:
            print("  Motif plots skipped")
    
    def _print_summary(self):
        """Print summary statistics with window information"""
        total_ends = len(self.left_sequences) + len(self.right_sequences)

        print(f"\n{'='*60}")
        print("SUMMARY (Manual Review Outputs)")
        print(f"{'='*60}")
        print(f"Total chromosome ends prepared: {total_ends}")
        print(f"  Left end sequences:  {len(self.left_sequences)}")
        print(f"  Right end sequences: {len(self.right_sequences)}")
        print("  Automatic telomeric/untelomeric files are not written.")
        print("  Choose target ends manually from the end sequences and motif plots.")
        print(f"{'='*60}")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Prepare chromosome-end sequences and telomere motif plots for manual review",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Example usage:
  python TelSeekerCheck.py --genome genome.fa --motif TTAGGG --out results

Manual review output:
  - Extracts 100kb from each chromosome end
  - Counts motif and reverse-complement repeats in 10kb bins
  - Writes left/right end FASTA files for sequence review
  - Writes whole-genome and per-chromosome motif plots in 1kb bins
  - Does not write automatic target-end files; choose targets manually

Output structure:
  results/genome.telomere.check/
    ├── genome.telomere.check.left.2kb.fa  # Left end sequences
    ├── genome.telomere.check.right.2kb.fa # Right end sequences
    ├── all_chromosomes_combined.png       # Whole-genome motif plot
    └── <chromosome>_telomere_motif.png    # Per-chromosome motif plot
        """
    )

    parser.add_argument(
        '--genome',
        required=True,
        help='Input genome FASTA file'
    )

    parser.add_argument(
        '-m', '--motif',
        default='TTAGGG',
        help='Telomere repeat motif (default: TTAGGG)'
    )

    parser.add_argument(
        '--out',
        required=True,
        help='Output directory'
    )

    parser.add_argument(
        '--threshold',
        type=float,
        default=0.7,
        help=argparse.SUPPRESS
    )

    parser.add_argument(
        '--check-length',
        type=int,
        default=100000,
        help='Length to extract from chromosome end for checking in bp (default: 100000)'
    )

    parser.add_argument(
        '--extract-length',
        type=int,
        default=2000,
        help='Length to extract for output sequences in bp (default: 2000)'
    )

    parser.add_argument(
        '--window-flank',
        type=int,
        default=500,
        help=argparse.SUPPRESS
    )

    parser.add_argument(
        '--method',
        choices=['window_count', 'legacy_trc'],
        default='window_count',
        help=argparse.SUPPRESS
    )

    parser.add_argument(
        '--window-size',
        type=int,
        default=10000,
        help=argparse.SUPPRESS
    )

    parser.add_argument(
        '--plot-window-size',
        type=int,
        default=DEFAULT_MOTIF_PLOT_WINDOW_SIZE,
        help='Whole-genome motif plot window size in bp (default: 1000)'
    )

    parser.add_argument(
        '--terminal-windows',
        type=int,
        default=1,
        help=argparse.SUPPRESS
    )

    parser.add_argument(
        '--min-terminal-repeats',
        type=int,
        default=100,
        help=argparse.SUPPRESS
    )

    parser.add_argument(
        '--min-terminal-density',
        type=float,
        default=10.0,
        help=argparse.SUPPRESS
    )

    parser.add_argument(
        '--min-terminal-to-internal-ratio',
        type=float,
        default=3.0,
        help=argparse.SUPPRESS
    )

    args = parser.parse_args()

    # Validate genome file
    if not os.path.exists(args.genome):
        print(f"Error: Genome file not found: {args.genome}")
        sys.exit(1)

    # Create checker and run
    checker = TelomereChecker(
        genome_file=args.genome,
        motif=args.motif,
        output_dir=args.out,
        trc_threshold=args.threshold,
        check_length=args.check_length,
        extract_length=args.extract_length,
        window_flank=args.window_flank,
        window_size=args.window_size,
        terminal_windows=args.terminal_windows,
        min_terminal_repeats=args.min_terminal_repeats,
        min_terminal_density=args.min_terminal_density,
        min_terminal_to_internal_ratio=args.min_terminal_to_internal_ratio,
        method=args.method,
        plot_window_size=args.plot_window_size
    )

    checker.run()


if __name__ == '__main__':
    main()
