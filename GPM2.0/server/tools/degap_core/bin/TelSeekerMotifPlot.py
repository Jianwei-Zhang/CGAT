#!/usr/bin/env python3
"""
Shared telomere motif distribution plotting helpers.

The same plotting code is used by the pre-check genome review and the final
TelSeeker HTML report so their motif distribution figures stay consistent.
"""

import re
from pathlib import Path
from typing import Any, List, Optional, Tuple

try:
    from Bio import SeqIO
    from Bio.Seq import Seq
    HAS_BIOPYTHON = True
except ImportError:
    HAS_BIOPYTHON = False
    SeqIO = None
    Seq = None

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    plt = None
    FuncFormatter = None


DEFAULT_MOTIF_PLOT_WINDOW_SIZE = 1000


def reverse_complement(seq: str) -> str:
    """Get reverse complement of a DNA sequence."""
    if HAS_BIOPYTHON:
        return str(Seq(seq).reverse_complement())

    complement = {
        'A': 'T', 'T': 'A', 'G': 'C', 'C': 'G',
        'a': 't', 't': 'a', 'g': 'c', 'c': 'g',
    }
    return ''.join(complement.get(b, b) for b in reversed(seq))


def count_motif_in_window(sequence: str, motif: str, motif_rc: str) -> Tuple[int, int]:
    """Count occurrences of motif and its reverse complement in one window."""
    forward_count = len(re.findall(f'(?={motif})', sequence, re.IGNORECASE))
    rc_count = len(re.findall(f'(?={motif_rc})', sequence, re.IGNORECASE))
    return forward_count, rc_count


def process_chromosome_motif(
    seq_record: Any,
    motif: str,
    motif_rc: str,
    window_size: int = DEFAULT_MOTIF_PLOT_WINDOW_SIZE,
) -> Tuple[List[int], List[int], List[int]]:
    """Count motif occurrences in non-overlapping windows for one chromosome."""
    sequence = str(seq_record.seq).upper()
    seq_length = len(sequence)

    positions = []
    forward_counts = []
    rc_counts = []

    for start in range(0, seq_length, window_size):
        end = min(start + window_size, seq_length)
        window_seq = sequence[start:end]
        mid_pos = start + (end - start) // 2
        forward_count, rc_count = count_motif_in_window(window_seq, motif, motif_rc)

        positions.append(mid_pos)
        forward_counts.append(forward_count)
        rc_counts.append(rc_count)

    return positions, forward_counts, rc_counts


def plot_single_chromosome_motif(
    chrom_name: str,
    positions: List[int],
    forward_counts: List[int],
    rc_counts: List[int],
    motif: str,
    motif_rc: str,
    output_dir: Path,
) -> Optional[Path]:
    """Create and save a line plot for a single chromosome."""
    if not HAS_MATPLOTLIB:
        return None

    try:
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(positions, forward_counts, color='blue', linewidth=1, alpha=0.7, label=f'{motif}')
        ax.plot(positions, rc_counts, color='purple', linewidth=1, alpha=0.7, label=f'{motif_rc}')

        def format_mb(x, pos):
            return f'{x/1e6:.1f}'

        ax.xaxis.set_major_formatter(FuncFormatter(format_mb))
        ax.set_xlabel('Position (Mb)', fontsize=12)
        ax.set_ylabel('Motif Count', fontsize=12)
        ax.set_title(f'Telomere Motif Distribution - {chrom_name}', fontsize=14, fontweight='bold')
        ax.legend(loc='upper right', framealpha=0.9)
        ax.grid(True, alpha=0.3, linestyle='--')

        plt.tight_layout()
        output_file = output_dir / f'{chrom_name}_telomere_motif.png'
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()

        return output_file
    except Exception as e:
        print(f"  Warning: Failed to plot {chrom_name}: {e}")
        return None


def plot_combined_chromosomes_motif(
    chrom_data: List[Tuple],
    motif: str,
    motif_rc: str,
    output_dir: Path,
) -> Optional[Path]:
    """Create a combined plot with all chromosomes in aligned subplots."""
    if not HAS_MATPLOTLIB:
        return None

    n_chroms = len(chrom_data)
    if n_chroms == 0:
        return None

    try:
        global_max_pos = max(data[4] for data in chrom_data)
        fig_height = max(3 * n_chroms, 8)
        fig, axes = plt.subplots(n_chroms, 1, figsize=(14, fig_height), sharex=True)

        if n_chroms == 1:
            axes = [axes]

        def format_mb(x, pos):
            return f'{x/1e6:.1f}'

        for idx, (chrom_name, positions, forward_counts, rc_counts, max_pos) in enumerate(chrom_data):
            ax = axes[idx]
            ax.plot(positions, forward_counts, color='blue', linewidth=1, alpha=0.7, label=f'{motif}')
            ax.plot(positions, rc_counts, color='purple', linewidth=1, alpha=0.7, label=f'{motif_rc}')
            ax.set_ylabel('Motif Count', fontsize=10)
            ax.set_title(chrom_name, fontsize=11, fontweight='bold', loc='left')
            ax.grid(True, alpha=0.3, linestyle='--')

            if idx == 0:
                ax.legend(loc='upper right', framealpha=0.9, fontsize=9)

            ax.set_xlim(-global_max_pos * 0.02, global_max_pos * 1.02)
            ax.xaxis.set_major_formatter(FuncFormatter(format_mb))

        axes[-1].set_xlabel('Position (Mb)', fontsize=12)
        fig.suptitle(
            'Telomere Motif Distribution - All Chromosomes',
            fontsize=14,
            fontweight='bold',
            y=0.995,
        )
        plt.tight_layout(rect=[0, 0, 1, 0.995])

        output_file = output_dir / 'all_chromosomes_combined.png'
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()

        return output_file
    except Exception as e:
        print(f"  Warning: Failed to create combined plot: {e}")
        return None


def generate_motif_distribution_plots(
    genome_file: Path,
    motif: str,
    output_dir: Path,
    window_size: int = DEFAULT_MOTIF_PLOT_WINDOW_SIZE,
) -> Tuple[List[str], List[str], Optional[Path]]:
    """
    Generate per-chromosome and combined whole-genome motif distribution plots.

    Returns:
        Tuple of (individual image names, chromosome names, combined image path).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not HAS_BIOPYTHON:
        print("  Warning: BioPython not found. Motif distribution plots will be skipped.")
        return [], [], None
    if not HAS_MATPLOTLIB:
        print("  Warning: Matplotlib not found. Motif distribution plots will be skipped.")
        return [], [], None
    if not Path(genome_file).exists():
        print(f"  Warning: Genome file not found for motif plotting: {genome_file}")
        return [], [], None

    motif_rc = reverse_complement(motif)
    motif_images = []
    chrom_names = []
    chrom_data = []

    print(f"  Motif: {motif} / {motif_rc}")
    print(f"  Window size: {window_size} bp")
    print(f"  Genome: {Path(genome_file).name}")

    with open(genome_file, 'r') as handle:
        for record in SeqIO.parse(handle, 'fasta'):
            chrom_name = record.id
            chrom_length = len(record.seq)
            print(f"    Processing {chrom_name} ({chrom_length:,} bp)...", end=" ")

            positions, forward_counts, rc_counts = process_chromosome_motif(
                record,
                motif,
                motif_rc,
                window_size,
            )

            max_pos = max(positions) if positions else 0
            chrom_data.append((chrom_name, positions, forward_counts, rc_counts, max_pos))
            chrom_names.append(chrom_name)

            img_path = plot_single_chromosome_motif(
                chrom_name,
                positions,
                forward_counts,
                rc_counts,
                motif,
                motif_rc,
                output_dir,
            )
            if img_path:
                motif_images.append(img_path.name)
                print("OK")
            else:
                print("SKIP")

    combined_img = None
    if chrom_data:
        print("    Generating combined plot...", end=" ")
        combined_img = plot_combined_chromosomes_motif(chrom_data, motif, motif_rc, output_dir)
        print("OK" if combined_img else "SKIP")

    return motif_images, chrom_names, combined_img
