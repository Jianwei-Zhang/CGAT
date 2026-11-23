#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import logging
import subprocess
import shutil
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from multiprocessing import Pool, Manager
from Bio import SeqIO


def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)


logger = setup_logging()


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="TelSeekerPart2: Prepare files for chromosome end extension",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--out',
        required=True,
        type=str,
        help='Output directory path (same as used in Part1)'
    )
    
    parser.add_argument(
        '--genome',
        required=True,
        type=str,
        help='Path to genome FASTA file'
    )
    
    parser.add_argument(
        '--kmer_num',
        type=int,
        default=10,
        help='Number of kmers (default: 10)'
    )
    
    parser.add_argument(
        '--kmer_size',
        type=int,
        default=41,
        help='Size of kmers (default: 41)'
    )

    parser.add_argument(
        '--work', '-w',
        type=int,
        default=1,
        help='Number of parallel workers for chromosome end extension (default: 1)'
    )
    
    parser.add_argument(
        '-t', '--threads',
        type=int,
        default=20,
        help='Number of threads (default: 20)'
    )
    
    parser.add_argument(
        '--edge',
        type=int,
        default=500,
        help='Edge tolerance for alignment boundary checking (default: 500bp)'
    )
    
    parser.add_argument(
        '--max_rounds',
        type=int,
        default=None,
        help='Maximum number of extension rounds per chromosome end. Extension stops when round number exceeds this value. '
             'Default: None (no limit, unified with gapfiller and ctglinker modes). '
             'Note: Each chromosome end is extended independently; this limit applies to each end separately'
    )

    parser.add_argument(
        '--max_extension_length',
        type=int,
        default=None,
        help='Maximum cumulative extension length in bp per chromosome end. Extension stops when total extended length exceeds this value. '
             'Default: None (no limit, unified with gapfiller and ctglinker modes). '
             'Note: Each chromosome end is extended independently; this limit applies to each end separately'
    )

    parser.add_argument(
        '--hifi',
        nargs='+',
        default=None,
        help='Path(s) to original HiFi reads file(s) (FASTQ/FA, multiple files supported)'
    )

    parser.add_argument(
        '--ont',
        nargs='+',
        default=None,
        help='Path(s) to original ONT reads file(s) (FASTQ/FA, multiple files supported)'
    )

    parser.add_argument(
        '--kmer_filter',
        action='store_true',
        help='Enable k-mer filtering to reduce reads before alignment (default: disabled)'
    )

    return parser.parse_args()


def read_fasta(fasta_file: Path) -> Dict[str, str]:
    """
    Read FASTA file and return dictionary of sequences.
    
    Args:
        fasta_file: Path to FASTA file
        
    Returns:
        Dictionary mapping sequence name to sequence
    """
    sequences = {}
    current_name = None
    current_seq = []
    
    with open(fasta_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('>'):
                if current_name is not None:
                    sequences[current_name] = ''.join(current_seq)
                current_name = line[1:].split()[0]
                current_seq = []
            else:
                current_seq.append(line)
        
        if current_name is not None:
            sequences[current_name] = ''.join(current_seq)
    
    return sequences


class ConnectionChecker:
    """
    Handles sequence connection checking using MUMmer alignment.
    
    This class provides methods for:
    - Running MUMmer alignment between sequences
    - Checking if sequences can connect based on alignment criteria
    - Creating linked sequences from successful connections
    
    Can be used for:
    - Direct connection checking (seed vs telomeric reads)
    - Extension validation (extended sequence vs terminal sequence)
    """
    
    def __init__(self, edge: int = 500, min_alignment_length: int = 10000, min_identity: float = 80.0, *, strict_tools=False, cache_directory=None):
        """
        Initialize connection checker.
        
        Args:
            edge: Edge tolerance for boundary checking (bp)
            min_alignment_length: Minimum alignment length required (bp)
            min_identity: Minimum alignment identity required (%)
        """
        self.strict_tools = strict_tools
        self.cache_directory = Path(cache_directory) if cache_directory is not None else None
        self.edge = edge
        self.min_alignment_length = min_alignment_length
        self.min_identity = min_identity
    
    def _checked_alignment(self, reference, query, prefix):
        from ExtensionFamilies import fingerprint
        from FamilyOverlap import MummerOverlap
        from FamilyTools import content_hash
        if not reference.is_file() or not query.is_file():
            raise FileNotFoundError(f"Missing telomere alignment input: {reference}, {query}")
        cache = self.cache_directory or prefix.parent
        if not hasattr(self, "_family_aligner"):
            self._family_aligner = MummerOverlap(cache, self.edge)
        aligner = self._family_aligner
        key = fingerprint([content_hash(reference), content_hash(query), aligner.contract])
        directory = cache / key
        directory.mkdir(parents=True, exist_ok=True)
        # Stable input paths let successful tool stages survive interrupted read
        # scanning, and avoid depending on Part2's disposable temp read files.
        import shutil
        for source, name in ((reference, "reference.fa"), (query, "query.fa")):
            target = directory / name
            if not target.exists():
                shutil.copyfile(source, target)
            elif content_hash(target) != content_hash(source):
                raise ValueError(f"Changed cached telomere input: {target}")
        ref, qry = directory / "reference.fa", directory / "query.fa"
        output = directory / "alignment"
        delta = directory / "alignment.delta"
        filtered = directory / "alignment.filtered.delta"
        coords = directory / "alignment.coords"
        aligner._stage(directory, "nucmer", [aligner.tools["nucmer"], "-c", "90", "-l", "40",
                       "-p", str(output), str(ref), str(qry)], [ref, qry], delta, generated=delta)
        aligner._stage(directory, "delta-filter", [aligner.tools["delta-filter"], "-m", str(delta)],
                       [delta], filtered)
        aligner._stage(directory, "coords", [aligner.tools["show-coords"], "-TrHcl", str(filtered)],
                       [filtered], coords)
        return coords

    def run_mummer_alignment(self, seq1_file: Path, seq2_file: Path, 
                            output_prefix: Path) -> Optional[Path]:
        """
        Run MUMmer alignment between two sequences.
        
        Args:
            seq1_file: Path to first sequence file (reference/seed)
            seq2_file: Path to second sequence file (query/reads)
            output_prefix: Output prefix for alignment files
            
        Returns:
            Path to coords file if successful, None otherwise
        """
        if self.strict_tools:
            return self._checked_alignment(seq1_file, seq2_file, output_prefix)

        # Check input files
        if not seq1_file.exists():
            logger.error(f"Sequence file 1 not found: {seq1_file}")
            return None
        
        if not seq2_file.exists():
            logger.error(f"Sequence file 2 not found: {seq2_file}")
            return None
        
        try:
            # Step 1: Run nucmer
            nucmer_cmd = [
                'nucmer',
                '-c', '90',  # Minimum cluster length
                '-l', '40',  # Minimum match length
                '-p', str(output_prefix),
                str(seq1_file),
                str(seq2_file)
            ]
            
            result = subprocess.run(nucmer_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.warning(f"nucmer failed: {result.stderr}")
                return None
            
            # Step 2: Run delta-filter
            delta_file = Path(str(output_prefix) + '.delta')
            if not delta_file.exists():
                logger.warning(f"Delta file not created: {delta_file}")
                return None
            
            filter_output = Path(str(output_prefix) + '.delta.filter')
            with open(filter_output, 'w') as f:
                filter_cmd = ['delta-filter', '-m', str(delta_file)]
                result = subprocess.run(filter_cmd, stdout=f, stderr=subprocess.PIPE, text=True)
                if result.returncode != 0:
                    logger.warning(f"delta-filter failed: {result.stderr}")
                    return None
            
            # Step 3: Run show-coords
            coords_file = Path(str(output_prefix) + '.delta.filter.coords')
            with open(coords_file, 'w') as f:
                coords_cmd = ['show-coords', '-TrHcl', str(filter_output)]
                result = subprocess.run(coords_cmd, stdout=f, stderr=subprocess.PIPE, text=True)
                if result.returncode != 0:
                    logger.warning(f"show-coords failed: {result.stderr}")
                    return None
            
            return coords_file
            
        except FileNotFoundError as e:
            logger.error(f"MUMmer tool not found: {e}. Please ensure MUMmer is installed and in PATH.")
            return None
        except Exception as e:
            logger.error(f"Error during MUMmer alignment: {e}")
            return None
    
    def check_connection(self, ref_file: Path, qry_file: Path, output_dir: Path,
                        end_type: str, alignment_prefix: str = "alignment") -> Optional[Dict]:
        """
        Check if query sequence can connect to reference sequence.
        
        Args:
            ref_file: Path to reference sequence file (seed/extended)
            qry_file: Path to query sequence file (read/terminal)
            output_dir: Directory for alignment output files
            end_type: 'L' or 'R'
            alignment_prefix: Prefix for alignment files
            
        Returns:
            Dictionary with connection info if successful, None otherwise
        """
        # Create alignment output directory
        output_dir.mkdir(parents=True, exist_ok=True)
        aln_prefix = output_dir / alignment_prefix
        
        # Run MUMmer alignment
        coords_file = self.run_mummer_alignment(ref_file, qry_file, aln_prefix)
        
        if coords_file is None or not coords_file.exists():
            return None
        
        # Parse alignment results
        try:
            with open(coords_file, 'r') as f:
                alignments = []
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split('\t')
                    if len(parts) < 9 or (self.strict_tools and len(parts) != 13):
                        if self.strict_tools:
                            raise ValueError('Malformed telomere MUMmer coordinates')
                        continue
                    
                    try:
                        aln = {
                            's1': int(parts[0]),      # Start in reference
                            'e1': int(parts[1]),      # End in reference
                            's2': int(parts[2]),      # Start in query
                            'e2': int(parts[3]),      # End in query
                            'len1': int(parts[4]),    # Alignment length in reference
                            'len2': int(parts[5]),    # Alignment length in query
                            'identity': float(parts[6]),  # Identity %
                            'ref_len': int(parts[7]), # Reference length
                            'qry_len': int(parts[8]), # Query length
                            'ref_id': parts[11] if len(parts) == 13 else '',
                            'qry_id': parts[12] if len(parts) == 13 else ''
                        }
                        alignments.append(aln)
                    except (ValueError, IndexError):
                        if self.strict_tools:
                            raise
                        continue
            
            if not alignments:
                return None
            
            # Filter alignments by length
            filtered_alns = [aln for aln in alignments if aln['len1'] >= self.min_alignment_length]
            
            if not filtered_alns:
                return None
            
            # Filter by identity
            filtered_alns = [aln for aln in filtered_alns if aln['identity'] >= self.min_identity]
            
            if not filtered_alns:
                return None
            
            # Check boundary conditions based on end type
            valid_alns = []
            for aln in filtered_alns:
                if aln["s1"] > aln["e1"] or aln["s2"] > aln["e2"]:
                    continue
                if end_type == 'L':
                    # Left end: check if alignment extends to reference's right edge
                    # and query's left edge is within boundary
                    if aln['e2'] >= aln['qry_len'] - self.edge and aln['s1'] <= self.edge:
                        valid_alns.append(aln)
                else:  # 'R'
                    # Right end: check if alignment extends to reference's left edge
                    # and query's right edge is within boundary
                    if aln['e1'] >= aln['ref_len'] - self.edge and aln['s2'] <= self.edge:
                        valid_alns.append(aln)
            
            if not valid_alns:
                return None
            
            # Select best alignment by identity
            best_aln = max(valid_alns, key=lambda x: x['identity'])
            
            return best_aln
            
        except Exception as e:
            logger.error(f"Error parsing alignment results: {e}")
            if self.strict_tools:
                raise
            return None
    
    def create_linked_sequence(self, ref_file: Path, qry_file: Path, alignment: Dict,
                              end_type: str, output_file: Path) -> bool:
        """
        Create linked sequence from reference and query based on alignment.
        
        Args:
            ref_file: Path to reference sequence file
            qry_file: Path to query sequence file
            alignment: Alignment dictionary
            end_type: 'L' or 'R'
            output_file: Output file for linked sequence
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Read sequences
            ref_seq = None
            for record in SeqIO.parse(ref_file, 'fasta'):
                ref_seq = str(record.seq)
                ref_id = record.id
                break
            
            qry_seq = None
            qry_id = alignment['qry_id']
            for record in SeqIO.parse(qry_file, 'fasta'):
                if record.id == qry_id:
                    qry_seq = str(record.seq)
                    break
            
            if ref_seq is None or qry_seq is None:
                return False
            
            # Create linked sequence based on end type
            if end_type == 'L':
                # Left end: query + reference[e1:]
                linked_seq = qry_seq[:alignment['e2']] + ref_seq[alignment['e1']:]
            else:  # 'R'
                # Right end: reference[:s1] + query
                linked_seq = ref_seq[:alignment['s1'] - 1] + qry_seq[alignment['s2'] - 1:]
            
            # Calculate overlap
            overlap = alignment['len1']
            
            # Write linked sequence
            with open(output_file, 'w') as f:
                header = (f">{ref_id}_linked\t"
                         f"query={qry_id}\t"
                         f"overlap={overlap}bp\t"
                         f"identity={alignment['identity']:.2f}%\t"
                         f"length={len(linked_seq)}bp\n")
                f.write(header)
                # Write sequence in 80 character lines
                for i in range(0, len(linked_seq), 80):
                    f.write(linked_seq[i:i+80] + '\n')
            
            return True
            
        except Exception as e:
            logger.error(f"Error creating linked sequence: {e}")
            return False


def check_single_chr_end(chr_end: str, work_path: Path, edge: int = 500) -> Dict:
    """
    Check direct connection for a single chromosome end (seed vs all telomeric reads).
    This function is designed to be called in parallel.
    
    Args:
        chr_end: Chromosome end identifier
        work_path: Working directory for this chromosome end
        edge: Edge tolerance
        
    Returns:
        Dictionary with check results
    """
    result = {
        'chr_end': chr_end,
        'success': False,
        'read_id': None,
        'alignment': None,
        'error': None
    }
    
    if (Path(work_path) / 'extension' / 'families.json').exists():
        # Round zero was already passed. Let the persistent extension engine
        # validate/resume rather than repeating seed-to-read comparisons.
        result['skip_reason'] = 'resume_family_extension'
        return result

    try:
        # Parse end type
        parts = chr_end.rsplit('.', 1)
        if len(parts) != 2:
            result['error'] = f"Invalid chromosome end format: {chr_end}"
            return result
        
        chr_name, end_type = parts
        
        # Check required files
        seed_file = work_path / 'seed.fa'
        telo_reads_file = work_path / 'telo.reads.fa'
        
        if not seed_file.exists():
            result['error'] = f"Seed file not found: {seed_file}"
            return result
        
        if not telo_reads_file.exists():
            result['error'] = f"Telomeric reads file not found: {telo_reads_file}"
            return result
        
        # Create check directory
        check_dir = work_path / 'direct.check'
        check_dir.mkdir(parents=True, exist_ok=True)
        
        checker = TelomereExtensionChecker(
            edge=edge, cache_directory=work_path / "telomere-alignments",
            shared_directory=work_path.parent / ".telomere-target-cache")
        try:
            connection = checker.check_with_telo_reads(seed_file, telo_reads_file, check_dir, end_type, 0)
            diagnostics = checker.last_diagnostics
        finally:
            checker.close()
        total_reads = diagnostics["pool_records"]
        checked_reads = diagnostics["refined_records"]
        if connection:
            result.update(connection)

        # Write check log
        log_file = check_dir / 'direct.check.log'
        with open(log_file, 'w') as f:
            f.write(f"Chromosome End: {chr_end}\n")
            f.write(f"End Type: {end_type}\n")
            f.write(f"Total Telomeric Reads: {total_reads}\n")
            f.write(f"Reads Checked: {checked_reads}\n")
            f.write(f"\n")
            
            if result['success']:
                f.write(f"Status: SUCCESS - Direct connection found\n")
                f.write(f"Connected Read: {result['read_id']}\n")
                aln = result['alignment']
                f.write(f"Alignment Length: {aln['len1']} bp\n")
                f.write(f"Identity: {aln['identity']:.2f}%\n")
                f.write(f"Reference Positions: {aln['s1']}-{aln['e1']}\n")
                f.write(f"Query Positions: {aln['s2']}-{aln['e2']}\n")
                f.write(f"Linked Sequence: direct.linker.fa\n")
            else:
                f.write(f"Status: FAILED - No direct connection found\n")
                if result['error']:
                    f.write(f"Error: {result['error']}\n")
        
        from TelomereTargets import check_log_lines
        with log_file.open("a") as stream:
            stream.write(check_log_lines(diagnostics))

        return result
        
    except Exception as e:
        result['error'] = str(e)
        logger.error(f"  [{chr_end}] Error during direct connection check: {e}")
        return result


class DirectConnectionChecker:
    """Performs direct connection checking for all chromosome ends in parallel."""
    
    def __init__(self, work_base_dir: Path, chr_ends: List[str], work_paths: Dict[str, Path],
                 max_workers: int = 4, edge: int = 500):
        """
        Initialize direct connection checker.
        
        Args:
            work_base_dir: Base working directory
            chr_ends: List of chromosome ends to check
            work_paths: Dictionary mapping chr_end to work path
            max_workers: Maximum number of parallel workers
            edge: Edge tolerance for alignment boundary checking
        """
        self.work_base_dir = work_base_dir
        self.chr_ends = chr_ends
        self.work_paths = work_paths
        self.max_workers = max_workers
        self.edge = edge
        self.results = {}
    
    def run_checks(self):
        """Run direct connection checks in parallel."""
        logger.info("=" * 80)
        logger.info("Starting Direct Connection Checking")
        logger.info("=" * 80)
        logger.info(f"Chromosome ends to check: {len(self.chr_ends)}")
        logger.info(f"Max parallel workers: {self.max_workers}")
        logger.info(f"Edge tolerance: {self.edge} bp")
        logger.info("")
        
        # Prepare arguments for parallel processing
        check_args = []
        for chr_end in self.chr_ends:
            work_path = self.work_paths[chr_end]
            check_args.append((chr_end, work_path, self.edge))
        
        # Run checks in parallel
        if self.max_workers == 1:
            # Serial processing
            results = []
            for args in check_args:
                result = check_single_chr_end(*args)
                results.append(result)
        else:
            # Parallel processing
            with Pool(processes=self.max_workers) as pool:
                results = pool.starmap(check_single_chr_end, check_args)
        
        # Store results
        for result in results:
            self.results[result['chr_end']] = result
        
        errors = [r for r in results if r.get("error")]
        if errors:
            raise RuntimeError("Telomere direct-check error: " + "; ".join(
                f"{r['chr_end']}: {r['error']}" for r in errors))

        # Summary
        logger.info("")
        logger.info("=" * 80)
        logger.info("Direct Connection Check Summary")
        logger.info("=" * 80)
        
        success_count = sum(1 for r in results if r['success'])
        failed_count = len(results) - success_count
        
        logger.info(f"Total checked: {len(results)}")
        logger.info(f"  ✓ Successful: {success_count}")
        logger.info(f"  ✗ Failed: {failed_count}")
        logger.info("")
        
        if success_count > 0:
            logger.info("Successful connections:")
            for result in results:
                if result['success']:
                    chr_end = result['chr_end']
                    read_id = result['read_id']
                    identity = result['alignment']['identity']
                    logger.info(f"  • {chr_end}: {read_id} (identity: {identity:.2f}%)")
        
        logger.info("")
        logger.info("=" * 80)
        
        # Finalize successful direct connections
        self._finalize_direct_connections()
        
        return self.results
    
    def _finalize_direct_connections(self):
        """Create unified linker.fa files for successful direct connections."""
        logger.info("")
        logger.info("Creating unified linker.fa files for direct connections...")
        
        success_count = 0
        for chr_end, result in self.results.items():
            if result['success']:
                work_path = self.work_paths[chr_end]
                # Create simple result dict for finalize function
                finalize_result = {
                    'success': True,
                    'skipped': False,
                    'skip_reason': 'direct_connection_found',
                    'connection_info': {
                        'method': 'direct',
                        'read_id': result.get('read_id'),
                        'linker_file': str(work_path / 'direct.check' / 'direct.linker.fa')
                    }
                }
                # Treat as direct connection for finalization
                finalize_result['skipped'] = True
                if finalize_chr_end_result(chr_end, work_path, finalize_result):
                    success_count += 1
        
        logger.info(f"Created {success_count} linker.fa files from direct connections")
        logger.info("")


class WorkspaceBuilder:
    """Handles the creation and setup of chromosome end workspaces."""
    
    def __init__(self, out_dir: str, genome_file: str, work_base_name: str = 'part2.chr.end.job'):
        """
        Initialize workspace builder.
        
        Args:
            out_dir: Output directory path
            genome_file: Path to genome FASTA file
            work_base_name: Job directory name under out_dir
        """
        self.out_dir = Path(out_dir)
        self.genome_file = Path(genome_file)
        self.work_base_dir = self.out_dir / work_base_name
        self.chr_ends = []
        self.work_paths = {}
        self.seed_length = 0
    
    def setup_workspace(self):
        """Execute all workspace setup steps."""
        from FamilyTelomere import reject_legacy_telomere_project
        reject_legacy_telomere_project(self.out_dir)
        logger.info("=" * 80)
        logger.info("Starting workspace setup for chromosome end extension")
        logger.info("=" * 80)
        
        # Step 1: Load chromosome ends to process
        self._load_chromosome_ends()
        
        # Step 2: Create work directories
        self._create_work_directories()
        
        # Step 3: Determine optimal seed length
        self._determine_seed_length()
        
        # Step 4: Extract seed sequences
        self._extract_seed_sequences()
        
        # Step 5: Link telomeric reads
        self._link_telomeric_reads()
        
        # Step 6: Link reads data files
        self._link_reads_data()
        
        logger.info("=" * 80)
        logger.info(f"Workspace setup completed successfully!")
        logger.info(f"Created {len(self.chr_ends)} chromosome end workspaces")
        logger.info(f"Location: {self.work_base_dir}")
        logger.info("=" * 80)
    
    def _load_chromosome_ends(self):
        """Step 1: Read user-selected target chromosome ends."""
        logger.info("[Step 1/6] Loading user-selected target chromosome ends...")
        
        need_extension_file = self.out_dir / 'genome.telomere.check' / 'need_extension_chr_end.txt'
        
        if not need_extension_file.exists():
            logger.error(f"File not found: {need_extension_file}")
            sys.exit(1)
        
        with open(need_extension_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    self.chr_ends.append(line)
        
        logger.info(f"  → Found {len(self.chr_ends)} target chromosome ends: {self.chr_ends}")
        logger.info("")
    
    def _create_work_directories(self):
        """Step 2: Create work directories for each chromosome end."""
        logger.info("[Step 2/6] Creating work directories...")
        
        # Check if work_base_dir exists and is not a directory
        if self.work_base_dir.exists() and not self.work_base_dir.is_dir():
            logger.warning(f"  ⚠ Removing existing file: {self.work_base_dir}")
            self.work_base_dir.unlink()
        elif self.work_base_dir.is_symlink() and not self.work_base_dir.exists():
            logger.warning(f"  ⚠ Removing broken symlink: {self.work_base_dir}")
            self.work_base_dir.unlink()
        
        self.work_base_dir.mkdir(parents=True, exist_ok=True)
        
        for chr_end in self.chr_ends:
            chr_work_path = self.work_base_dir / chr_end
            
            # Check if chr_work_path exists and is not a directory
            if chr_work_path.exists() and not chr_work_path.is_dir():
                logger.warning(f"  ⚠ Removing existing file: {chr_work_path}")
                chr_work_path.unlink()
            elif chr_work_path.is_symlink() and not chr_work_path.exists():
                logger.warning(f"  ⚠ Removing broken symlink: {chr_work_path}")
                chr_work_path.unlink()
            
            chr_work_path.mkdir(parents=True, exist_ok=True)
            self.work_paths[chr_end] = chr_work_path
            logger.info(f"  → Created: {chr_work_path}")
        
        logger.info("")
    
    def _determine_seed_length(self):
        """Step 3: Determine seed length from reads statistics."""
        logger.info("[Step 3/6] Determining seed length...")
        
        ont_stat = self.out_dir / 'ONT.reads.stat'
        hifi_stat = self.out_dir / 'HiFi.reads.stat'
        
        seed_lengths = []
        
        ont_seed = self._read_seed_length_from_stat(ont_stat)
        if ont_seed:
            seed_lengths.append(ont_seed)
            logger.info(f"  → ONT SeedLength: {ont_seed}")
        
        hifi_seed = self._read_seed_length_from_stat(hifi_stat)
        if hifi_seed:
            seed_lengths.append(hifi_seed)
            logger.info(f"  → HiFi SeedLength: {hifi_seed}")
        
        if not seed_lengths:
            logger.error("  ✗ No reads statistics found (neither ONT nor HiFi)")
            sys.exit(1)
        
        self.seed_length = max(seed_lengths)
        logger.info(f"  → Using seed length: {self.seed_length} bp")
        logger.info("")
    
    def _read_seed_length_from_stat(self, stat_file: Path) -> Optional[int]:
        """Read SeedLength value from a reads stat file."""
        if not stat_file.exists():
            return None
        
        with open(stat_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('SeedLength'):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1])
        return None
    
    def _extract_seed_sequences(self):
        """Step 4: Extract seed sequences for each chromosome end."""
        logger.info("[Step 4/6] Extracting seed sequences...")
        
        if not self.genome_file.exists():
            logger.error(f"  ✗ Genome file not found: {self.genome_file}")
            sys.exit(1)
        
        logger.info(f"  → Reading genome: {self.genome_file}")
        genome_sequences = read_fasta(self.genome_file)
        logger.info(f"  → Loaded {len(genome_sequences)} sequences")
        
        for chr_end in self.chr_ends:
            self._extract_single_seed(chr_end, genome_sequences)
        
        logger.info("")
    
    def _extract_single_seed(self, chr_end: str, genome_sequences: Dict[str, str]):
        """Extract seed sequence for a single chromosome end."""
        parts = chr_end.rsplit('.', 1)
        if len(parts) != 2:
            logger.warning(f"  ⚠ Invalid chromosome end format: {chr_end}")
            return
        
        chr_name, end_type = parts
        
        if chr_name not in genome_sequences:
            logger.warning(f"  ⚠ Chromosome {chr_name} not found in genome")
            return
        
        chr_seq = genome_sequences[chr_name]
        chr_len = len(chr_seq)
        
        # Extract seed based on end type
        if end_type == 'L':
            seed_seq = chr_seq[:min(self.seed_length, chr_len)]
        elif end_type == 'R':
            seed_seq = chr_seq[max(0, chr_len - self.seed_length):]
        else:
            logger.warning(f"  ⚠ Unknown end type: {end_type}")
            return
        
        # Write seed to file
        seed_file = self.work_paths[chr_end] / 'seed.fa'
        with open(seed_file, 'w') as f:
            f.write(f">{chr_end}_seed\n")
            for i in range(0, len(seed_seq), 80):
                f.write(seed_seq[i:i+80] + '\n')
        
        logger.info(f"  → {chr_end}: seed.fa ({len(seed_seq)} bp)")
    
    def _link_telomeric_reads(self):
        """Step 5: Create symlinks to telomeric reads files."""
        logger.info("[Step 5/6] Linking telomeric reads...")
        
        telo_reads_dir = self.out_dir / 'part1.telo.reads'
        left_reads = telo_reads_dir / 'Global.left.telo.reads.fa'
        right_reads = telo_reads_dir / 'Global.right.telo.reads.fa'
        
        if not left_reads.exists():
            logger.error(f"  ✗ Left telomeric reads not found: {left_reads}")
            sys.exit(1)
        
        if not right_reads.exists():
            logger.error(f"  ✗ Right telomeric reads not found: {right_reads}")
            sys.exit(1)
        
        for chr_end in self.chr_ends:
            self._link_single_telo_reads(chr_end, left_reads, right_reads)
        
        logger.info("")
    
    def _link_single_telo_reads(self, chr_end: str, left_reads: Path, right_reads: Path):
        """Create symlink to telomeric reads for a single chromosome end."""
        parts = chr_end.rsplit('.', 1)
        if len(parts) != 2:
            return
        
        chr_name, end_type = parts
        work_path = self.work_paths[chr_end]
        
        if end_type == 'L':
            target = left_reads.resolve()
        elif end_type == 'R':
            target = right_reads.resolve()
        else:
            return
        
        link = work_path / 'telo.reads.fa'
        
        # Remove existing link if present
        if link.exists() or link.is_symlink():
            link.unlink()
        
        # Create symlink or copy
        try:
            link.symlink_to(target)
            logger.info(f"  → {chr_end}: linked telo.reads.fa")
        except OSError:
            import shutil
            shutil.copy2(target, link)
            logger.info(f"  → {chr_end}: copied telo.reads.fa")
    
    def _link_reads_data(self):
        """Step 6: Create symlinks to reads data files."""
        logger.info("[Step 6/6] Linking reads data files...")
        
        items_to_link = [
            'ONT.reads.stat',
            'ont_reads_part',
            'ont_reads.idx',
            'processed_reads',
            'HiFi.reads.stat',
            'hifi_reads.idx',
            'hifi_reads_part'
        ]
        
        linked_items = []
        for item_name in items_to_link:
            source = self.out_dir / item_name
            if source.exists():
                linked_items.append(item_name)
                self._link_to_all_workspaces(item_name, source)
        
        logger.info(f"  → Linked {len(linked_items)} items to {len(self.chr_ends)} workspaces")
        logger.info("")
    
    def _link_to_all_workspaces(self, item_name: str, source: Path):
        """Link a single item to all chromosome end workspaces."""
        for chr_end in self.chr_ends:
            work_path = self.work_paths[chr_end]
            link = work_path / item_name
            
            # Remove existing link if present
            if link.exists() or link.is_symlink():
                link.unlink()
            
            # Create symlink or copy
            try:
                link.symlink_to(source.resolve(), target_is_directory=source.is_dir())
            except OSError:
                import shutil
                if source.is_dir():
                    if link.exists():
                        shutil.rmtree(link)
                    shutil.copytree(source, link)
                else:
                    shutil.copy2(source, link)


class TelomereExtender:
    """
    Manages iterative extension for a single chromosome end.
    Similar to Gapfiller's Elongation class.
    """
    
    def __init__(self, chr_end: str, work_path: Path, out_dir: Path,
                 kmer_num: int, kmer_size: int, threads: int, edge: int,
                 max_rounds: int = 30, max_extension_length: int = 1000000,
                 original_hifi: Optional[str] = None, original_ont: Optional[str] = None,
                 kmer_filter: bool = False):
        self.chr_end = chr_end
        self.work_path = work_path
        self.out_dir = Path(out_dir)
        self.kmer_num = kmer_num
        self.kmer_size = kmer_size
        self.threads = threads
        self.edge = edge
        self.max_rounds = max_rounds
        self.max_extension_length = max_extension_length
        self.kmer_filter = kmer_filter

        # Parse end type
        parts = chr_end.rsplit('.', 1)
        self.chr_name, self.end_type = parts if len(parts) == 2 else (chr_end, 'L')

        # Extension state
        self.round_num = 0
        self.total_extension_length = 0
        self.end_signal = False
        self.connection_result = None

        # Paths
        self.extension_dir = work_path / 'extension'
        from FamilyTelomere import reject_legacy_telomere
        reject_legacy_telomere(self.extension_dir)
        self.extension_dir.mkdir(parents=True, exist_ok=True)
        self.telo_reads_file = work_path / 'telo.reads.fa'
        self.seed_file = work_path / 'seed.fa'

        # Initialize checker
        self.extension_checker = TelomereExtensionChecker(
            edge=edge, min_alignment_length=10000, min_identity=80.0,
            cache_directory=self.work_path / "telomere-alignments",
            shared_directory=self.work_path.parent / ".telomere-target-cache")

        # Prepare base object for GapFillerClass
        self.base = prepare_base_object(
            chr_end=chr_end,
            work_path=work_path,
            out_dir=self.out_dir,
            kmer_num=kmer_num,
            kmer_size=kmer_size,
            threads=threads,
            edge=edge,
            max_extension_length=max_extension_length,
            original_hifi=original_hifi,
            original_ont=original_ont,
            kmer_filter=kmer_filter
        )
    
    def run_extension(self) -> Dict:
        """Run one real endpoint through shared rounds, budgets and checkpoints."""
        from FamilyTelomere import run_telomere
        try:
            return run_telomere(self)
        finally:
            self.extension_checker.close()

    def _check_connection(self, round_dir: Path, extended_seq_file: Path) -> Optional[Dict]:
        """Check if extended sequence connects to telomeric reads."""
        check_dir = round_dir / 'connection_check'
        check_dir.mkdir(parents=True, exist_ok=True)
        
        result = self.extension_checker.check_with_telo_reads(
            extended_seq_file=extended_seq_file,
            telo_reads_file=self.telo_reads_file,
            check_dir=check_dir,
            end_type=self.end_type,
            round_num=self.round_num
        )
        
        # Write check log
        self.extension_checker.write_check_log(
            check_dir=check_dir,
            round_num=self.round_num,
            result=result,
            extended_seq_file=extended_seq_file,
            end_type=self.end_type
        )
        
        return result
    
    def _log_to_main(self, message: str):
        """Append message to main extension log."""
        main_log = self.extension_dir / 'extension.log'
        with open(main_log, 'a') as f:
            f.write(f"{message}\n")
    
    def _write_round_log(self, round_dir: Path, ext_result: Dict):
        """Write detailed log for a single round."""
        round_log = round_dir / 'round.log'
        with open(round_log, 'w') as f:
            f.write(f"Round Number: {self.round_num}\n")
            f.write(f"Chromosome End: {self.chr_end}\n")
            f.write(f"\n")
            f.write(f"Extension Result:\n")
            f.write(f"  Status: {'Success' if ext_result.get('success') else 'Failed'}\n")
            
            if ext_result.get('success'):
                f.write(f"  Extension Length: {ext_result.get('extension_length', 0)} bp\n")
                f.write(f"  Extended Sequence: {ext_result.get('extended_seq_file', 'N/A')}\n")
                f.write(f"  Cumulative Extension: {self.total_extension_length + ext_result.get('extension_length', 0)} bp\n")
            else:
                f.write(f"  Reason: {ext_result.get('reason', 'unknown')}\n")
                if 'note' in ext_result:
                    f.write(f"  Note: {ext_result['note']}\n")
    
    def _generate_result(self, final_seq_file: Path, stop_reason: Optional[str] = None) -> Dict:
        """Generate final result dictionary."""
        result = {
            'chr_end': self.chr_end,
            'success': self.connection_result is not None,
            'rounds': self.round_num,
            'total_extension_length': self.total_extension_length,
            'final_seq_file': str(final_seq_file),
            'connection_info': self.connection_result,
            'stop_reason': stop_reason
        }
        
        # Write summary
        summary_file = self.extension_dir / 'extension.summary'
        with open(summary_file, 'w') as f:
            f.write(f"{'='*60}\n")
            f.write(f"Extension Summary\n")
            f.write(f"{'='*60}\n")
            f.write(f"Chromosome End: {self.chr_end}\n")
            f.write(f"Total Rounds: {self.round_num}\n")
            f.write(f"Total Extension Length: {self.total_extension_length} bp\n")
            f.write(f"Stop Reason: {stop_reason or 'unknown'}\n")
            f.write(f"\n")
            f.write(f"Connection Found: {'Yes' if result['success'] else 'No'}\n")
            if result['success']:
                f.write(f"Connected Read: {self.connection_result['read_id']}\n")
                aln = self.connection_result['alignment']
                f.write(f"Alignment Identity: {aln['identity']:.2f}%\n")
                f.write(f"Alignment Length: {aln['len1']} bp\n")
                f.write(f"Final Linked Sequence: {self.connection_result['linker_file']}\n")
            else:
                f.write(f"Final Extended Sequence: {final_seq_file}\n")
            f.write(f"\n")
            f.write(f"Configuration:\n")
            f.write(f"  Max Rounds: {self.max_rounds}\n")
            f.write(f"  Max Extension Length: {self.max_extension_length} bp\n")
            f.write(f"  Edge Tolerance: {self.edge} bp\n")
            f.write(f"  K-mer: num={self.kmer_num}, size={self.kmer_size}\n")
            f.write(f"{'='*60}\n")
        
        return result

    def _cleanup_round_memory(self, ext_result: Optional[Dict]):
        """Clean up memory after each round to prevent memory accumulation."""
        import gc
        
        if ext_result is None:
            gc.collect()
            return
        
        # Clear the result_object which contains GapFillerClass data
        if 'result_object' in ext_result:
            result_obj = ext_result['result_object']
            
            # Clear ExtensionReads data (完整清理所有大型数据结构)
            if hasattr(result_obj, 'ExtensionReads'):
                er = result_obj.ExtensionReads
                # 清理列表类型属性
                for attr in ['minimumThresholdReadsID', 'minimumThresholdExtensionReadsID',
                             'selectPotentialExtensionReadsID', 'extensionReadsID',
                             'lastRoundUsedReads', 'usedReads']:
                    if hasattr(er, attr):
                        setattr(er, attr, [])
                # 清理 roundInput 引用
                if hasattr(er, 'roundInput'):
                    er.roundInput = None
            
            # Clear ExtensionContigs data (完整清理所有大型数据结构)
            if hasattr(result_obj, 'ExtensionContigs'):
                ec = result_obj.ExtensionContigs
                # 清理字典类型属性
                for attr in ['hifiasmResultDict', 'potentialExtensionContigsAlnDict']:
                    if hasattr(ec, attr):
                        setattr(ec, attr, {})
                # 清理列表类型属性
                for attr in ['selectExtensionContigsAln', 'FuzzyAln', 'extensionContigID']:
                    if hasattr(ec, attr):
                        setattr(ec, attr, [])
            
            # Clear roundInput and roundOutput references
            if hasattr(result_obj, 'roundInput'):
                result_obj.roundInput = None
            if hasattr(result_obj, 'roundOutput'):
                result_obj.roundOutput = None
            
            # Remove the reference
            del ext_result['result_object']
        
        # Force garbage collection
        gc.collect()
        logger.debug(f"  [{self.chr_end}] Memory cleanup completed for round {self.round_num}")

    def _final_cleanup(self):
        """Final memory cleanup after all extension rounds complete."""
        import gc
        
        # Clear base object's large data structures
        if hasattr(self, 'base') and self.base is not None:
            # Clear reads-related attributes
            for attr in ['readsDict', 'ont_readsdict', 'original_reads_info']:
                if hasattr(self.base, attr):
                    setattr(self.base, attr, None)
        
        # Clear extension checker
        if hasattr(self, 'extension_checker'):
            self.extension_checker.close()
        
        # Force garbage collection
        gc.collect()
        logger.debug(f"  [{self.chr_end}] Final memory cleanup completed")


class TelomereExtensionChecker:
    """
    Checks if extended sequence can connect to any telomeric read.
    
    Uses one shared target index and one batched comparison per sequence.
    Ranks all eligible records, then checks independent read corroboration.
    """
    
    def __init__(self, edge=500, min_alignment_length=10000, min_identity=80.0,
                 *, cache_directory=None, shared_directory=None):
        self.edge = edge
        self.min_alignment_length = min_alignment_length
        self.min_identity = min_identity
        self.cache_directory = Path(cache_directory) if cache_directory is not None else None
        self.shared_directory = Path(shared_directory) if shared_directory is not None else None
        self.targets = None
        self.last_diagnostics = {}

    def close(self):
        if self.targets is not None:
            self.targets.close()
            self.targets = None

    def check_with_telo_reads(self, extended_seq_file, telo_reads_file, check_dir, end_type, round_num):
        from TelomereTargets import TelomereTargets, publish_check
        from ExtensionFamilies import read_json
        check_dir = Path(check_dir)
        cache = self.cache_directory or check_dir.parent / "telomere-alignments"
        shared = self.shared_directory or check_dir.parent / ".telomere-target-cache"
        if self.targets is None:
            self.targets = TelomereTargets(telo_reads_file, shared, cache, edge=self.edge,
                minimum_length=self.min_alignment_length, minimum_identity=self.min_identity)
        if Path(telo_reads_file).resolve() != self.targets.index.pool:
            raise ValueError("Telomere checker target pool changed; use a new checker")
        result = publish_check(self.targets, extended_seq_file, end_type, check_dir, round_num)
        self.last_diagnostics = read_json(check_dir / "connection-diagnostics.json")
        logger.info("    Telomere targets: pool=%s, retrieved=%s, eligible=%s, decision=%s",
                    self.last_diagnostics['pool_records'], self.last_diagnostics['retrieved_records'],
                    self.last_diagnostics['eligible_records'], self.last_diagnostics['reason'])
        return result

    def write_check_log(self, check_dir: Path, round_num: int, result: Optional[Dict],
                       extended_seq_file: Path, end_type: str):
        """
        Write connection check log.
        
        Args:
            check_dir: Directory for check output
            round_num: Current round number
            result: Check result from check_with_telo_reads()
            extended_seq_file: Path to extended sequence
            end_type: 'L' or 'R'
        """
        log_file = check_dir / f'round{round_num}.check.log'
        
        with open(log_file, 'w') as f:
            f.write(f"Round: {round_num}\n")
            f.write(f"Extended Sequence: {extended_seq_file}\n")
            f.write(f"End Type: {end_type}\n")
            f.write(f"\n")
            
            if result and result['success']:
                f.write(f"Status: SUCCESS - Connection found\n")
                f.write(f"Connected Read: {result['read_id']}\n")
                f.write(f"Reads Checked: {result['checked_reads']}/{result['total_reads']}\n")
                aln = result['alignment']
                f.write(f"Alignment Length: {aln['len1']} bp\n")
                f.write(f"Identity: {aln['identity']:.2f}%\n")
                f.write(f"Reference Positions: {aln['s1']}-{aln['e1']}\n")
                f.write(f"Query Positions: {aln['s2']}-{aln['e2']}\n")
                f.write(f"Linked Sequence: {result['linker_file']}\n")
            else:
                f.write(f"Status: FAILED - No connection found\n")
                if result and 'checked_reads' in result:
                    f.write(f"Reads Checked: {result['checked_reads']}/{result['total_reads']}\n")
        from TelomereTargets import check_log_lines
        with log_file.open("a") as stream:
            stream.write(check_log_lines(self.last_diagnostics))


def prepare_base_object(chr_end: str, work_path: Path, out_dir: Path,
                        kmer_num: int, kmer_size: int, threads: int,
                        edge: int, max_extension_length: int = 1000000,
                        original_hifi: Optional[str] = None,
                        original_ont: Optional[str] = None,
                        kmer_filter: bool = False):
    """
    Prepare base object for GapFillerClass.

    Converts TelSeekerPart2 parameters to GapFillerClass base object format.

    Args:
        chr_end: Chromosome end identifier (e.g., 'Chr01.L')
        work_path: Working directory for this chromosome end
        out_dir: Output directory
        kmer_num: Number of k-mers
        kmer_size: Size of k-mers
        threads: Number of threads
        edge: Edge tolerance
        max_extension_length: Maximum extension length
        original_hifi: Path to original HiFi reads file
        original_ont: Path to original ONT reads file
        kmer_filter: Enable k-mer filtering (default: False)

    Returns:
        base object with all required attributes
    """
    # Parse chromosome end
    parts = chr_end.rsplit('.', 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid chromosome end format: {chr_end}")
    
    chr_name, end_type = parts
    
    # Create base object (simple namespace)
    class BaseObject:
        pass
    
    base = BaseObject()
    
    # Set basic attributes
    # IMPORTANT: GapFiller's flag behavior is opposite to intuition:
    #   flag='left' extracts right-end seed and extends rightward
    #   flag='right' extracts left-end seed and extends leftward
    # For telomere extension:
    #   Chr.L (left telomere) needs to extend leftward → use flag='right'
    #   Chr.R (right telomere) needs to extend rightward → use flag='left'
    if end_type == 'L':
        base.tag = 'left'    # Tag for logging/naming
        base.flag = 'right'  # GapFiller flag: extends leftward
    elif end_type == 'R':
        base.tag = 'right'   # Tag for logging/naming
        base.flag = 'left'   # GapFiller flag: extends rightward
    else:
        raise ValueError(f"Invalid end_type: {end_type}. Expected 'L' or 'R'.")
    
    base.name = f"{chr_name}.{end_type}"
    base.edge = edge
    base.thread = threads
    base.MaximumExtensionLength = max_extension_length
    base.original_hifi_reads = original_hifi
    base.original_ont_reads = original_ont
    
    # Set file paths
    base.out = str(work_path / 'extension')
    base.initialSeq = str(work_path / 'seed.fa')
    base.terminalSeq = None  # Single-ended objective: never a seed-to-itself target
    
    # Set k-mer parameters
    base.kmer_size = kmer_size
    base.kmer_num = kmer_num
    base.j = 70  # Default parallel jobs for k-mer filtering
    base.kmer_filter = kmer_filter  # Enable/disable k-mer filtering

    # Determine data type from available reads files
    ont_stat = out_dir / 'ONT.reads.stat'
    hifi_stat = out_dir / 'HiFi.reads.stat'
    
    ont_exists = ont_stat.exists()
    hifi_exists = hifi_stat.exists()
    
    if ont_exists and hifi_exists:
        base.data_type = 'mixed'
        logger.info(f"  [{chr_end}] Detected mixed mode (ONT + HiFi)")
    elif ont_exists:
        base.data_type = 'ont'
        logger.info(f"  [{chr_end}] Detected ONT-only mode")
    elif hifi_exists:
        base.data_type = 'hifi'
        logger.info(f"  [{chr_end}] Detected HiFi-only mode")
    else:
        raise ValueError(f"No reads statistics found in {out_dir}")
    
    # Set reads paths (links should already exist in work_path)
    ont_reads_idx = work_path / 'ont_reads.idx'
    hifi_reads_idx = work_path / 'hifi_reads.idx'
    
    if base.data_type == 'mixed':
        base.reads = str(hifi_reads_idx) if hifi_reads_idx.exists() else None
        base.ont_reads = str(ont_reads_idx) if ont_reads_idx.exists() else None
    elif base.data_type == 'ont':
        base.reads = str(ont_reads_idx) if ont_reads_idx.exists() else None
        base.ont_reads = None
    else:  # hifi
        base.reads = str(hifi_reads_idx) if hifi_reads_idx.exists() else None
        base.ont_reads = None
    
    # Prepare readsDict by loading from index files
    from Bio import SeqIO
    
    # Load HiFi readsDict (main readsDict)
    base.readsDict = None
    if base.data_type in ['hifi', 'mixed'] and hifi_reads_idx.exists():
        try:
            logger.info(f"  [{chr_end}] Loading HiFi readsDict from {hifi_reads_idx}")
            base.readsDict = SeqIO.index_db(str(hifi_reads_idx))
            logger.info(f"  [{chr_end}] HiFi readsDict loaded: {len(base.readsDict)} entries")
        except Exception as e:
            logger.error(f"  [{chr_end}] Failed to load HiFi readsDict: {e}")
            raise
    elif base.data_type == 'ont' and ont_reads_idx.exists():
        # For ONT-only mode, load ONT reads as main readsDict
        try:
            logger.info(f"  [{chr_end}] Loading ONT readsDict from {ont_reads_idx}")
            base.readsDict = SeqIO.index_db(str(ont_reads_idx))
            logger.info(f"  [{chr_end}] ONT readsDict loaded: {len(base.readsDict)} entries")
        except Exception as e:
            logger.error(f"  [{chr_end}] Failed to load ONT readsDict: {e}")
            raise
    
    if base.readsDict is None:
        raise ValueError(f"Failed to load readsDict for {chr_end}")
    
    # Read seed length from stats
    base.seedLen = 0
    base.hifiSeedLen = 0
    base.ontSeedLen = 0
    base.maxReadsLen = 0
    
    if hifi_exists:
        with open(hifi_stat, 'r') as f:
            for line in f:
                if line.startswith('SeedLength'):
                    base.hifiSeedLen = int(line.split()[1])
                elif line.startswith('MaxLength'):
                    base.maxReadsLen = max(base.maxReadsLen, int(line.split()[1]))
    
    if ont_exists:
        with open(ont_stat, 'r') as f:
            for line in f:
                if line.startswith('SeedLength'):
                    base.ontSeedLen = int(line.split()[1])
                elif line.startswith('MaxLength'):
                    base.maxReadsLen = max(base.maxReadsLen, int(line.split()[1]))
    
    # Set primary seed length
    if base.data_type == 'mixed':
        # In mixed mode, each data type uses its own seed length
        # Use HiFi seedLen as primary (hifiasm uses HiFi as main input)
        base.seedLen = base.hifiSeedLen
        logger.info(f"  [{chr_end}] Mixed mode: HiFi seedLen={base.hifiSeedLen} bp, ONT seedLen={base.ontSeedLen} bp")
    elif base.data_type == 'ont':
        base.seedLen = base.ontSeedLen
    else:
        base.seedLen = base.hifiSeedLen
    
    # Set filter depth (optional, can be None)
    base.filterDepth = None
    base.filterDepthHifi = None
    base.filterDepthOnt = None
    
    # Set original reads info (for hifiasm mixed mode)
    original_reads_info = {}
    if original_hifi:
        original_reads_info['original_hifi'] = original_hifi
    if original_ont:
        original_reads_info['original_ont'] = original_ont
    base.original_reads_info = original_reads_info if original_reads_info else None
    base.reads_info = dict(original_reads_info)
    
    # Load ONT readsDict for mixed mode
    base.ont_readsDict = None
    if base.data_type == 'mixed' and ont_reads_idx.exists():
        try:
            logger.info(f"  [{chr_end}] Loading ONT readsDict from {ont_reads_idx}")
            base.ont_readsDict = SeqIO.index_db(str(ont_reads_idx))
            logger.info(f"  [{chr_end}] ONT readsDict loaded: {len(base.ont_readsDict)} entries")
        except Exception as e:
            logger.error(f"  [{chr_end}] Failed to load ONT readsDict: {e}")
            # Non-fatal for mixed mode - can fall back to HiFi only
            base.ont_readsDict = None
    
    return base


def finalize_chr_end_result(chr_end: str, work_path: Path, result: Dict) -> bool:
    """
    Consolidate final result to a unified linker.fa file.
    
    Creates a unified linker.fa in the chromosome end's root work directory,
    copying from either:
    - direct.check/direct.linker.fa (direct connection)
    - extension/roundN/connection_check/roundN.linker.fa (extension connection)
    
    Args:
        chr_end: Chromosome end identifier
        work_path: Working directory for this chromosome end
        result: Result dictionary from extension process
        
    Returns:
        True if linker.fa created successfully, False otherwise
    """
    final_linker = work_path / 'linker.fa'
    
    try:
        # Check if connection was successful
        if not result.get('success'):
            logger.info(f"  [{chr_end}] No connection found, no linker.fa to create.")
            return False
        
        # Determine source linker file
        source_linker = None
        method = None
        
        # Case 1: Extension connection (prioritize)
        if result.get('connection_info'):
            conn_info = result['connection_info']
            if 'linker_file' in conn_info:
                source_linker = Path(conn_info['linker_file'])
                method = conn_info.get('method') or 'extension'
        
        # Validate source exists
        if source_linker is None:
            logger.warning(f"  [{chr_end}] Success marked but no linker file found in result.")
            return False
        
        if not source_linker.exists():
            logger.warning(f"  [{chr_end}] Source linker file not found: {source_linker}")
            return False
        
        # Copy to final location
        import shutil
        shutil.copy2(source_linker, final_linker)
        
        logger.info(f"  [{chr_end}] ✓ Created linker.fa ({method} connection)")
        
        # Write metadata file
        metadata_file = work_path / 'linker.info'
        with open(metadata_file, 'w') as f:
            f.write(f"Chromosome End: {chr_end}\n")
            f.write(f"Connection Method: {method}\n")
            f.write(f"Source File: {source_linker}\n")
            f.write(f"Final File: {final_linker}\n")
            
            if method == 'direct':
                f.write(f"Status: Direct connection found\n")
                f.write(f"Extension Rounds: 0\n")
                f.write(f"Total Extension Length: 0 bp\n")
                if 'connection_info' in result and 'read_id' in result['connection_info']:
                    f.write(f"Connected Read: {result['connection_info']['read_id']}\n")
            elif method == 'extension':
                f.write(f"Status: Extension connection found\n")
                rounds = result.get('rounds', 0)
                ext_len = result.get('total_extension_length', 0)
                f.write(f"Extension Rounds: {rounds}\n")
                f.write(f"Total Extension Length: {ext_len} bp\n")
                # Record connected read for extension connection
                if 'connection_info' in result and 'read_id' in result['connection_info']:
                    f.write(f"Connected Read: {result['connection_info']['read_id']}\n")
        
        return True
        
    except Exception as e:
        logger.error(f"  [{chr_end}] Error creating final linker.fa: {e}")
        return False


def extend_single_chr_end(chr_end: str, work_path: Path, out_dir: Path,
                          kmer_num: int, kmer_size: int, threads: int, edge: int,
                          max_rounds: int = 30, max_extension_length: int = 1000000,
                          original_hifi: Optional[str] = None,
                          original_ont: Optional[str] = None,
                          kmer_filter: bool = False) -> Dict:
    """
    Entry function for extending a single chromosome end (for parallel execution).

    This function is designed to be robust against failures - any exception is caught
    and returned in the result dict, ensuring that one chromosome end's failure
    does not affect the processing of other ends in parallel execution.

    Args:
        chr_end: Chromosome end identifier
        work_path: Working directory for this chromosome end
        out_dir: Output directory
        kmer_num: Number of k-mers
        kmer_size: Size of k-mers
        threads: Number of threads
        edge: Edge tolerance
        max_rounds: Maximum extension rounds
        max_extension_length: Maximum extension length in bp
        
    Returns:
        Result dictionary with keys:
        - chr_end: Chromosome end identifier
        - success: Boolean indicating if connection was found
        - skipped: Boolean indicating if extension was skipped
        - error: Error message if failed, None otherwise
        - rounds: Number of extension rounds completed
        - total_extension_length: Total bp extended
        - final_seq_file: Path to final sequence
        - connection_info: Connection details if successful
        - stop_reason: Reason for stopping extension
    """
    result = {
        'chr_end': chr_end,
        'success': False,
        'skipped': False,
        'error': None,
        'rounds': 0,
        'total_extension_length': 0
    }
    
    try:
        # Validate input parameters
        if not work_path.exists():
            error_msg = f"Work path does not exist: {work_path}"
            logger.error(f"  [{chr_end}] {error_msg}")
            result['error'] = error_msg
            return result
        
        # Check required files
        seed_file = work_path / 'seed.fa'
        telo_reads_file = work_path / 'telo.reads.fa'
        
        if not seed_file.exists():
            error_msg = f"Seed file not found: {seed_file}"
            logger.error(f"  [{chr_end}] {error_msg}")
            result['error'] = error_msg
            return result
        
        if not telo_reads_file.exists():
            error_msg = f"Telomeric reads file not found: {telo_reads_file}"
            logger.error(f"  [{chr_end}] {error_msg}")
            result['error'] = error_msg
            return result
        
        end_type = chr_end.rsplit('.', 1)[-1]
        if end_type not in ('L','R'):
            raise ValueError(f"Invalid chromosome endpoint: {chr_end}")

        # A completed direct check is identified by its receipt, never by
        # mutable log text. Re-entry validates the current code, pool and seed.
        direct_dir = work_path / 'direct.check'
        marker = direct_dir / 'telomere-check.json'
        if marker.is_file():
            verifier = TelomereExtensionChecker(
                edge=edge, cache_directory=work_path / "telomere-alignments",
                shared_directory=work_path.parent / ".telomere-target-cache")
            try:
                connection = verifier.check_with_telo_reads(seed_file,telo_reads_file,direct_dir,end_type,0)
            finally:
                verifier.close()
            if connection:
                result.update({
                    'success': True, 'skipped': True, 'skip_reason': 'direct_connection_found',
                    'rounds': 0, 'total_extension_length': 0,
                    'final_seq_file': connection['linker_file'],
                    'connection_info': dict(connection,method='direct'),
                    'stop_reason': 'direct_connection_found'
                })
                return result
        elif (direct_dir / 'direct.check.log').exists():
            raise ValueError("Legacy direct telomere result; use a new output directory")

        # Run extension
        try:
            extender = TelomereExtender(
                chr_end=chr_end,
                work_path=work_path,
                out_dir=out_dir,
                kmer_num=kmer_num,
                kmer_size=kmer_size,
                threads=threads,
                edge=edge,
                max_rounds=max_rounds,
                max_extension_length=max_extension_length,
                original_hifi=original_hifi,
                original_ont=original_ont,
                kmer_filter=kmer_filter
            )
            
            ext_result = extender.run_extension()
            result.update(ext_result)

        except ValueError as e:
            # Parameter validation errors
            logger.error(f"  [{chr_end}] Parameter error: {e}")
            result['error'] = f"Parameter error: {str(e)}"
        except ImportError as e:
            # Missing dependencies
            logger.error(f"  [{chr_end}] Import error: {e}")
            result['error'] = f"Import error: {str(e)}"
        except MemoryError as e:
            # Out of memory
            logger.error(f"  [{chr_end}] Memory error: {e}")
            result['error'] = "Memory error: Out of memory"
        except KeyboardInterrupt:
            # User interruption - should propagate
            logger.warning(f"  [{chr_end}] Extension interrupted by user")
            result['error'] = "Interrupted by user"
            raise
        except Exception as e:
            # Catch-all for unexpected errors
            logger.error(f"  [{chr_end}] Unexpected error during extension: {e}")
            import traceback
            result['error'] = str(e)
            result['traceback'] = traceback.format_exc()
            logger.debug(result['traceback'])
        finally:
            # Memory cleanup: release extender object and its internal data
            if 'extender' in dir():
                # Clear base object references
                if hasattr(extender, 'base'):
                    extender.base = None
                # Clear extension checker
                if hasattr(extender, 'extension_checker'):
                    extender.extension_checker = None
                # Clear connection result
                if hasattr(extender, 'connection_result'):
                    extender.connection_result = None
                del extender
            import gc
            gc.collect()
        
    except KeyboardInterrupt:
        # Propagate keyboard interrupt
        raise
    except Exception as e:
        # Final safety net
        logger.error(f"  [{chr_end}] Critical error: {e}")
        import traceback
        result['error'] = f"Critical error: {str(e)}"
        result['traceback'] = traceback.format_exc()
        logger.debug(result['traceback'])
    finally:
        # Final memory cleanup
        import gc
        gc.collect()
    
    return result


class ParallelExtensionManager:
    """Manages parallel extension of multiple chromosome ends."""

    def __init__(self, chr_ends: List[str], work_paths: Dict[str, Path], out_dir: Path,
                 kmer_num: int, kmer_size: int, threads: int, edge: int,
                 max_workers: int = 4, max_rounds: int = 30, max_extension_length: int = 1000000,
                 original_hifi: Optional[str] = None,
                 original_ont: Optional[str] = None,
                 kmer_filter: bool = False):
        self.chr_ends = chr_ends
        self.work_paths = work_paths
        self.out_dir = out_dir
        self.kmer_num = kmer_num
        self.kmer_size = kmer_size
        self.threads = threads
        self.edge = edge
        self.max_workers = max_workers
        self.max_rounds = max_rounds
        self.max_extension_length = max_extension_length
        self.results = {}
        self.original_hifi = original_hifi
        self.original_ont = original_ont
        self.kmer_filter = kmer_filter
    
    def run_parallel_extension(self) -> Dict[str, Dict]:
        """Execute parallel extension for all chromosome ends."""
        logger.info("=" * 80)
        logger.info("Starting Parallel Extension")
        logger.info("=" * 80)
        logger.info(f"Chromosome ends: {len(self.chr_ends)}")
        logger.info(f"Max parallel workers: {self.max_workers}")
        logger.info(f"Max rounds per end: {self.max_rounds}")
        logger.info(f"Max extension length: {self.max_extension_length} bp")
        logger.info("")

        # Prepare arguments
        extension_args = []
        for chr_end in self.chr_ends:
            extension_args.append((
                chr_end,
                self.work_paths[chr_end],
                self.out_dir,
                self.kmer_num,
                self.kmer_size,
                self.threads,
                self.edge,
                self.max_rounds,
                self.max_extension_length,
                self.original_hifi,
                self.original_ont,
                self.kmer_filter
            ))
        
        # Execute in parallel
        if self.max_workers == 1:
            # Serial execution
            results = []
            for args in extension_args:
                result = extend_single_chr_end(*args)
                results.append(result)
        else:
            # Parallel execution
            with Pool(processes=self.max_workers) as pool:
                results = pool.starmap(extend_single_chr_end, extension_args)
        
        # Collect results
        for result in results:
            self.results[result['chr_end']] = result
        
        # Generate summary
        self._print_summary()
        
        # Finalize results - create unified linker.fa files
        self._finalize_results()
        errors = {key: value['error'] for key, value in self.results.items() if value.get('error')}
        if errors:
            raise RuntimeError(f"Telomere extension errors; completed families are preserved for resume: {errors}")
        return self.results
    
    def _print_summary(self):
        """Print extension summary."""
        logger.info("")
        logger.info("=" * 80)
        logger.info("Extension Summary")
        logger.info("=" * 80)
        
        total = len(self.results)
        extension_success = sum(1 for r in self.results.values() if r.get('success'))
        extended_no_connection = sum(1 for r in self.results.values() if not r.get('success') and not r.get('error'))
        failed = sum(1 for r in self.results.values() if r.get('error'))
        
        logger.info(f"Total: {total}")
        logger.info(f"  Extension with connection: {extension_success}")
        logger.info(f"  Extended without connection: {extended_no_connection}")
        logger.info(f"  Failed: {failed}")
        logger.info("")
        
        if extension_success > 0:
            logger.info("Extension connections found:")
            for chr_end, result in self.results.items():
                if result.get('success'):
                    conn_info = result.get('connection_info', {})
                    logger.info(f"  • {chr_end}: {conn_info.get('read_id', 'N/A')} "
                              f"(rounds: {result.get('rounds', 0)})")

        logger.info("")
        logger.info("=" * 80)
    
    def _finalize_results(self):
        """Create unified linker.fa files for all successful connections."""
        logger.info("")
        logger.info("=" * 80)
        logger.info("Finalizing Results")
        logger.info("=" * 80)
        
        success_count = 0
        for chr_end, result in self.results.items():
            if result.get('success'):
                work_path = self.work_paths[chr_end]
                if finalize_chr_end_result(chr_end, work_path, result):
                    success_count += 1
        
        logger.info(f"Created {success_count} unified linker.fa files")
        logger.info("=" * 80)


def select_chr_ends_for_extension(chr_ends: List[str], direct_results: Dict[str, Dict]) -> List[str]:
    """Return chromosome ends that did not connect in Round0 direct checking."""
    return [
        chr_end
        for chr_end in chr_ends
        if not direct_results.get(chr_end, {}).get('success')
    ]


def prepare_chromosome_end_workspaces(out_dir: str, genome_file: str, work_base_name: str = 'part2.chr.end.job') -> WorkspaceBuilder:
    """
    Prepare workspaces for chromosome end extension.
    
    This function orchestrates all steps needed to set up individual
    workspaces for each chromosome end that needs extension.
    
    Args:
        out_dir: Output directory path
        genome_file: Path to genome FASTA file
        
    Returns:
        WorkspaceBuilder instance with setup completed
    """
    builder = WorkspaceBuilder(out_dir, genome_file, work_base_name=work_base_name)
    builder.setup_workspace()
    return builder


def main():
    """Main entry point."""
    args = parse_arguments()
    
    # Display configuration
    logger.info("=" * 80)
    logger.info("TelSeekerPart2: Chromosome End Workspace Preparation")
    logger.info("=" * 80)
    logger.info("Configuration:")
    logger.info(f"  Output directory : {args.out}")
    logger.info(f"  Genome file      : {args.genome}")
    logger.info(f"  Kmer num         : {args.kmer_num}")
    logger.info(f"  Kmer size        : {args.kmer_size}")
    logger.info(f"  Kmer filter      : {'ENABLED' if args.kmer_filter else 'DISABLED'}")
    logger.info(f"  Work (max parallel): {args.work}")
    logger.info(f"  Threads          : {args.threads}")
    logger.info(f"  Edge tolerance   : {args.edge} bp")
    if args.hifi:
        logger.info(f"  HiFi reads       : {len(args.hifi)} file(s)")
        for h in args.hifi:
            logger.info(f"                       - {h}")
    else:
        logger.info(f"  HiFi reads       : Not provided")

    if args.ont:
        logger.info(f"  ONT reads        : {len(args.ont)} file(s)")
        for o in args.ont:
            logger.info(f"                       - {o}")
    else:
        logger.info(f"  ONT reads        : Not provided")
    logger.info("")
    
    # Step 1: Prepare workspaces
    logger.info("Stage 1: Preparing workspaces...")
    builder = prepare_chromosome_end_workspaces(
        out_dir=args.out,
        genome_file=args.genome
    )
    logger.info("")
    
    # Step 2: Run direct connection checking
    logger.info("Stage 2: Running direct connection checks...")
    checker = DirectConnectionChecker(
        work_base_dir=builder.work_base_dir,
        chr_ends=builder.chr_ends,
        work_paths=builder.work_paths,
        max_workers=args.work,
        edge=args.edge
    )
    results = checker.run_checks()
    
    # Stage 3: Parallel extension. Round0 direct successes are complete and do
    # not enter GapFiller extension.
    extension_chr_ends = select_chr_ends_for_extension(builder.chr_ends, results)
    logger.info("")
    logger.info("Stage 3: Running parallel extension for ends without Round0 direct connection...")
    logger.info(f"  Ends entering extension: {len(extension_chr_ends)} / {len(builder.chr_ends)}")

    if not extension_chr_ends:
        logger.info("  All chromosome ends connected in Round0; skipping GapFiller extension.")
        return

    ext_manager = ParallelExtensionManager(
        chr_ends=extension_chr_ends,
        work_paths=builder.work_paths,
        out_dir=Path(args.out),
        kmer_num=args.kmer_num,
        kmer_size=args.kmer_size,
        threads=args.threads,
        edge=args.edge,
        max_workers=args.work,
        max_rounds=args.max_rounds,
        max_extension_length=args.max_extension_length,
        original_hifi=args.hifi,
        original_ont=args.ont,
        kmer_filter=args.kmer_filter
    )
    ext_results = ext_manager.run_parallel_extension()


if __name__ == '__main__':
    main()
