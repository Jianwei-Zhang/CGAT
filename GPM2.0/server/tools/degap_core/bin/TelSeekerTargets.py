#!/usr/bin/env python3
"""Utilities for parsing TelSeeker target chromosome ends."""

import re
from pathlib import Path
from typing import Iterable, List

from Bio import SeqIO


TARGET_END_RE = re.compile(r"^(.+)\.([LR])$")


def _read_genome_ids(genome_file: Path) -> set:
    """Read sequence IDs from a genome FASTA file."""
    with open(genome_file, "r") as f:
        return {record.id for record in SeqIO.parse(f, "fasta")}


def _read_target_file(target_file: Path) -> List[str]:
    """Read one target chromosome end per line from a text file."""
    targets = []
    with open(target_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            targets.append(line)
    return targets


def _deduplicate_preserving_order(items: Iterable[str]) -> List[str]:
    seen = set()
    unique = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def parse_target_ends(target_inputs: List[str], genome_file) -> List[str]:
    """
    Parse TelSeeker target ends from CLI values or a single text file.

    Args:
        target_inputs: Values from -e/--target_ends. If this contains one
            existing file path, the file is read with one target per line.
            Otherwise every value is treated as a target end.
        genome_file: Genome FASTA path used to validate chromosome IDs.

    Returns:
        Ordered, de-duplicated target ends such as ["Chr01.L", "Chr01.R"].

    Raises:
        ValueError: If input is empty, target format is invalid, the target
            file is empty, or a chromosome ID is not present in the genome.
    """
    if not target_inputs:
        raise ValueError("--target_ends/-e is required for telseeker mode")

    genome_path = Path(genome_file)
    genome_ids = _read_genome_ids(genome_path)
    if not genome_ids:
        raise ValueError(f"No sequences found in genome: {genome_path}")

    if len(target_inputs) == 1 and Path(target_inputs[0]).is_file():
        targets = _read_target_file(Path(target_inputs[0]))
    else:
        targets = [target.strip() for target in target_inputs if target.strip()]

    targets = _deduplicate_preserving_order(targets)
    if not targets:
        raise ValueError("No target ends were provided")

    for target in targets:
        match = TARGET_END_RE.match(target)
        if not match:
            raise ValueError(f"Invalid target end '{target}'. Expected format: Chr01.L or Chr01.R")

        chrom_name = match.group(1)
        if chrom_name not in genome_ids:
            raise ValueError(f"Target chromosome '{chrom_name}' from '{target}' was not found in genome")

    return targets
