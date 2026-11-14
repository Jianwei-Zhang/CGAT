#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TelSeeker.py - Main module for telomere extension workflow

Receives parameters from DEGAP.py and orchestrates telomere extension.
"""

import os
import sys
from pathlib import Path


class TelSeeker:
    """
    TelSeeker main class - receives and validates parameters from DEGAP.py
    """
    
    def __init__(self, parameter: list, kparameters: list):
        """
        Initialize TelSeeker with parameters from DEGAP.py.

        Args:
            parameter: List of 21 parameters from DEGAP.py
                [0]  mode: 'telseeker'
                [1]  remove: File cleanup level (1-3)
                [2]  thread: Number of threads (str)
                [3]  reads: HiFi/ONT reads file path (working FASTA)
                [4]  out: Output directory
                [5]  genome_file: Genome FASTA file
                [6]  motif: Telomere motif (e.g., 'TTAGGG')
                [7]  work: Number of parallel workers
                [8]  edge: Edge tolerance (bp)
                [9]  filterDepthHifi: HiFi depth filter (or None)
                [10] filterDepthOnt: ONT depth filter (or None)
                [11] MaximumExtensionLength: Max extension length (default: 1000000)
                [12] MaximumExtensionRound: Max extension rounds (default: 20)
                [13] data_type: 'hifi', 'ont', or 'mixed'
                [14] ont_reads: ONT reads file path (or None)
	                [15] target_ends: Target chromosome ends to extend
	                [16] tel_read_params: Dict with tel_n/tel_r/tel_mm (optional)
		                [17] readsDict: Path to HiFi reads index
		                [18] maxReadsLen: Maximum read length
		                [19] hifiSeedLen: HiFi seed length
		                [20] ontSeedLen: ONT seed length (or None)
		                [21] original_reads_info: Dict with file paths
		                [22] ont_readsdict: Path to ONT reads index (or None)

            kparameters: List of 2-3 k-mer parameters
                [0] kmer_size: K-mer size (default: 41)
                [1] kmer_num: Number of k-mers (default: 20)
                [2] kmer_filter: Enable k-mer filtering (default: False)
        """
        print(f"\n{'='*80}")
        print(f"TelSeeker Initialization")
        print(f"{'='*80}")

        # Validate parameter list lengths (support both old 20-param and new 21-param formats)
        if len(parameter) < 20:
            raise ValueError(f"Expected at least 20 parameters, got {len(parameter)}")
        if len(kparameters) < 2:
            raise ValueError(f"Expected 2-3 k-parameters, got {len(kparameters)}")

        print(f"[TelSeeker] Receiving parameters from DEGAP.py...")
        print(f"  Parameter count: {len(parameter)}")
        print(f"  K-parameter count: {len(kparameters)}")

        # Parse basic parameters (0-14)
        self.mode = parameter[0]
        self.remove = parameter[1]
        self.thread = int(parameter[2]) if parameter[2] else 20
        self.reads = parameter[3]
        self.out = Path(parameter[4])
        self.genome_file = Path(parameter[5])
        self.motif = parameter[6]
        self.work = parameter[7]
        self.edge = parameter[8]
        self.filterDepthHifi = parameter[9]
        self.filterDepthOnt = parameter[10]
        self.MaximumExtensionLength = parameter[11]
        self.tel_n = 100
        self.tel_r = 0.6
        self.tel_mm = 0

        # Handle current target-end format and older internal formats
        if len(parameter) >= 22 and isinstance(parameter[15], list):
            self.MaximumExtensionRound = parameter[12]
            self.data_type = parameter[13]
            self.ont_reads = parameter[14]
            self.target_ends = parameter[15]
            offset = 16
            if len(parameter) > offset and isinstance(parameter[offset], dict):
                tel_params = parameter[offset]
                self.tel_n = tel_params.get("tel_n", self.tel_n)
                self.tel_r = tel_params.get("tel_r", self.tel_r)
                self.tel_mm = tel_params.get("tel_mm", self.tel_mm)
                offset += 1
            self.readsDict = parameter[offset]
            self.maxReadsLen = parameter[offset + 1]
            self.hifiSeedLen = parameter[offset + 2]
            self.ontSeedLen = parameter[offset + 3]
            self.original_reads_info = parameter[offset + 4]
            self.ont_readsdict = parameter[offset + 5]
        elif len(parameter) >= 21:
            # New format with MaximumExtensionRound
            self.MaximumExtensionRound = parameter[12]
            self.data_type = parameter[13]
            self.ont_reads = parameter[14]
            self.target_ends = None
            # Parse extended parameters (15-20)
            self.readsDict = parameter[15]
            self.maxReadsLen = parameter[16]
            self.hifiSeedLen = parameter[17]
            self.ontSeedLen = parameter[18]
            self.original_reads_info = parameter[19]
            self.ont_readsdict = parameter[20]
        else:
            # Old format without MaximumExtensionRound (backward compatibility)
            self.MaximumExtensionRound = None  # Default value
            self.data_type = parameter[12]
            self.ont_reads = parameter[13]
            self.target_ends = None
            # Parse extended parameters (14-19)
            self.readsDict = parameter[14]
            self.maxReadsLen = parameter[15]
            self.hifiSeedLen = parameter[16]
            self.ontSeedLen = parameter[17]
            self.original_reads_info = parameter[18]
            self.ont_readsdict = parameter[19]

        # Parse k-mer parameters
        self.kmer_size = kparameters[0]
        self.kmer_num = kparameters[1]
        self.kmer_filter = kparameters[2] if len(kparameters) >= 3 else False
        
        # Validate parameters
        self._validate_parameters()
        
        # Print configuration
        self._print_configuration()
        
        print(f"[TelSeeker] Initialization complete ✓")
        print(f"{'='*80}\n")
    
    def _validate_parameters(self):
        """Validate all received parameters."""
        print(f"\n[TelSeeker] Validating parameters...")
        
        # Validate mode
        if self.mode != 'telseeker':
            raise ValueError(f"Invalid mode: {self.mode}")
        
        # Validate genome file
        if not self.genome_file.exists():
            raise FileNotFoundError(f"Genome file not found: {self.genome_file}")
        
        # Validate motif
        if not self.motif or not all(c in 'ACGT' for c in self.motif):
            raise ValueError(f"Invalid motif: {self.motif}")
        
        # Validate numeric parameters
        if self.thread <= 0:
            raise ValueError(f"Invalid thread count: {self.thread}")
        if self.work <= 0:
            raise ValueError(f"Invalid work parameter: {self.work}")
        if self.edge < 0:
            raise ValueError(f"Invalid edge: {self.edge}")
        
        # Validate data type
        if self.data_type not in ['hifi', 'ont', 'mixed']:
            raise ValueError(f"Invalid data_type: {self.data_type}")

        if self.tel_n <= 0:
            raise ValueError(f"Invalid tel_n: {self.tel_n}")
        if not (0 < self.tel_r <= 1):
            raise ValueError(f"Invalid tel_r: {self.tel_r}")
        if self.tel_mm not in [0, 1]:
            raise ValueError(f"Invalid tel_mm: {self.tel_mm}")
        
        # Validate mixed mode requirements
        if self.data_type == 'mixed' and not self.ont_reads:
            raise ValueError("Mixed mode requires ONT reads")

        if not self.target_ends:
            raise ValueError("TelSeeker requires target chromosome ends from --target_ends/-e")
        
        # Validate seed lengths
        if not self.hifiSeedLen or self.hifiSeedLen <= 0:
            raise ValueError(f"Invalid HiFi seed length: {self.hifiSeedLen}")
        
        if self.data_type in ['ont', 'mixed']:
            if not self.ontSeedLen or self.ontSeedLen <= 0:
                print(f"  Warning: Invalid ONT seed length: {self.ontSeedLen}")
        
        # In mixed mode, each data type uses its own seed length
        if self.data_type == 'mixed':
            print(f"  Mixed mode seed lengths:")
            print(f"    HiFi seedLen: {self.hifiSeedLen} bp (for hifi.inputCutSequence.fasta)")
            print(f"    ONT seedLen:  {self.ontSeedLen} bp (for ont.inputCutSequence.fasta)")
            # Use HiFi seedLen as primary (hifiasm uses HiFi as main input)
            self.seedLen = self.hifiSeedLen
        else:
            # Single mode: use respective seed length
            self.seedLen = self.hifiSeedLen if self.data_type == 'hifi' else self.ontSeedLen
        
        # Validate max read length
        if not self.maxReadsLen or self.maxReadsLen <= 0:
            raise ValueError(f"Invalid max read length: {self.maxReadsLen}")
        
        # Validate k-mer parameters
        if self.kmer_size <= 0:
            raise ValueError(f"Invalid kmer_size: {self.kmer_size}")
        if self.kmer_num <= 0:
            raise ValueError(f"Invalid kmer_num: {self.kmer_num}")
        
        # Validate readsDict
        if not self.readsDict:
            raise ValueError("HiFi readsDict path is empty")
        
        # Validate original_reads_info
        if not isinstance(self.original_reads_info, dict):
            raise ValueError(f"original_reads_info must be dict, got {type(self.original_reads_info)}")
        
        required_keys = ['original_hifi', 'original_ont', 'working_hifi', 'working_ont']
        for key in required_keys:
            if key not in self.original_reads_info:
                raise ValueError(f"original_reads_info missing key: {key}")
        
        print(f"[TelSeeker] Validation passed ✓")
    
    def _print_configuration(self):
        """Print configuration summary."""
        print(f"\n{'='*80}")
        print(f"TelSeeker Configuration")
        print(f"{'='*80}")
        
        print(f"\nGenome & Motif:")
        print(f"  Genome file:        {self.genome_file}")
        print(f"  Motif:              {self.motif}")
        print(f"  Output directory:   {self.out}")
        print(f"  Target ends:        {len(self.target_ends)}")
        for target_end in self.target_ends[:10]:
            print(f"    - {target_end}")
        if len(self.target_ends) > 10:
            print(f"    ... and {len(self.target_ends) - 10} more")
        
        print(f"\nData Type:")
        print(f"  Data type:          {self.data_type}")
        print(f"  HiFi reads:         {self.reads}")
        if self.ont_reads:
            print(f"  ONT reads:          {self.ont_reads}")
        
        print(f"\nProcessing Parameters:")
        print(f"  Threads:            {self.thread}")
        print(f"  Parallel workers:   {self.work}")
        print(f"  Edge tolerance:     {self.edge} bp")
        print(f"  Tel read units:     {self.tel_n}")
        print(f"  Tel read ratio:     {self.tel_r}")
        print(f"  Tel read mismatch:  {self.tel_mm}")
        if self.MaximumExtensionLength:
            print(f"  Max extension:      {self.MaximumExtensionLength} bp")
        
        print(f"\nK-mer Parameters:")
        print(f"  K-mer size:         {self.kmer_size}")
        print(f"  K-mer number:       {self.kmer_num}")
        print(f"  K-mer filter:       {'Enabled' if self.kmer_filter else 'Disabled'}")
        
        print(f"\nSeed Lengths:")
        if self.data_type == 'mixed':
            # In mixed mode, show ONT seedlen strategy
            print(f"  HiFi seed length:   {self.hifiSeedLen} bp (for hifi.inputCutSequence.fasta)")
            print(f"  ONT seed length:    {self.ontSeedLen} bp (for ont.inputCutSequence.fasta)")
            print(f"  Strategy:           Each data type uses its own seed length")
        else:
            # Single mode
            print(f"  HiFi seed length:   {self.hifiSeedLen} bp")
            if self.ontSeedLen:
                print(f"  ONT seed length:    {self.ontSeedLen} bp")
        print(f"  Max read length:    {self.maxReadsLen} bp")
        
        print(f"\nReads Index Files:")
        print(f"  HiFi index:         {self.readsDict}")
        if self.ont_readsdict:
            print(f"  ONT index:          {self.ont_readsdict}")
        
        print(f"\nOriginal Reads Info:")
        for key, value in self.original_reads_info.items():
            if value:
                print(f"  {key:20s}: {value}")
        
        print(f"{'='*80}")
    
    def run(self):
        """
        Execute TelSeeker workflow.

        Workflow:
        0. Load target chromosome ends
        1. Extract telomeric reads (TelSeekerPart1)
        2. Extend chromosome ends (TelSeekerPart2)
        3. Integrate and summarize results (TelSeekerPart3)
        4. Generate visualization report (TelSeekerVisualizer)
        """
        print(f"\n{'='*80}")
        print(f"Starting TelSeeker Workflow")
        print(f"{'='*80}\n")

        try:
            # Step 0: Load target chromosome ends
            self._step0_load_target_ends()

            # Stop early only if the provided target list is explicitly empty.
            if not self._has_chr_ends_needing_extension():
                print(f"\n[TelSeeker] No target chromosome ends were provided.")
                print(f"[TelSeeker] Skipping telomeric read extraction, extension, integration, and visualization.")
                print(f"Output directory: {self.out}")
                return

            # Step 1: Extract telomeric reads
            self._step1_extract_telomeric_reads()

            # Stop early when no telomeric reads are available for extension.
            if not self._has_telomeric_reads():
                print(f"\n[TelSeeker] No telomeric reads found after Step 1.")
                print(f"[TelSeeker] Skipping chromosome end extension, integration, and visualization.")
                print(f"Output directory: {self.out}")
                return

            # Step 2: Extend chromosome ends
            self._step2_extend_chromosome_ends()

            # Step 3: Integrate results
            self._step3_integrate_results()

            # Step 4: Generate visualization report
            self._step4_generate_visualization()

            # Print final summary
            print(f"\n{'='*80}")
            print(f"TelSeeker Workflow Completed Successfully")
            print(f"{'='*80}")
            print(f"Output directory: {self.out}")
            print(f"  - genome.telomere.check/      : User-provided target chromosome end list")
            print(f"  - part1.telo.reads/           : Telomeric reads extraction results")
            print(f"  - part2.chr.end.job/          : Chromosome end extension results")
            print(f"  - part3.integration.results/  : Integration and summary")
            print(f"  - visual.report/              : Visualization reports")
            print(f"    - Global.report.html        : Global overview report")
            print(f"    - <Chr.X>.report.html       : Individual chromosome end reports")
            print(f"{'='*80}\n")

        except Exception as e:
            print(f"\n{'='*80}")
            print(f"TelSeeker Workflow FAILED")
            print(f"{'='*80}")
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    def _get_chr_ends_needing_extension(self):
        """Return chromosome ends listed by Step 0, or None if the list is unavailable."""
        need_extension_file = self.out / "genome.telomere.check" / "need_extension_chr_end.txt"
        if not need_extension_file.exists():
            return None

        try:
            with open(need_extension_file, 'r') as f:
                return [line.strip() for line in f if line.strip() and not line.startswith('#')]
        except Exception as e:
            print(f"[TelSeeker] Warning: Could not read {need_extension_file}: {e}")
            return None

    def _has_chr_ends_needing_extension(self) -> bool:
        """Return False only when Step 0 explicitly produced an empty extension list."""
        chr_ends = self._get_chr_ends_needing_extension()
        return chr_ends is None or len(chr_ends) > 0

    def _count_fasta_records(self, fasta_file: Path) -> int:
        """Count FASTA records by header lines without loading sequences into memory."""
        if not fasta_file.exists():
            return 0

        count = 0
        try:
            with open(fasta_file, 'r') as f:
                for line in f:
                    if line.startswith('>'):
                        count += 1
        except Exception as e:
            print(f"[TelSeeker] Warning: Could not count FASTA records in {fasta_file}: {e}")
            return 0

        return count

    def _has_telomeric_reads(self) -> bool:
        """Return True when Step 1 produced at least one global telomeric read."""
        part1_dir = self.out / "part1.telo.reads"
        global_left = part1_dir / "Global.left.telo.reads.fa"
        global_right = part1_dir / "Global.right.telo.reads.fa"

        left_count = self._count_fasta_records(global_left)
        right_count = self._count_fasta_records(global_right)

        print(f"[TelSeeker] Telomeric reads available: left={left_count}, right={right_count}")
        return (left_count + right_count) > 0

    def _step0_load_target_ends(self):
        """
        Step 0: Load user-provided target chromosome ends.

        TelSeeker no longer performs telomere detection internally. The target
        list comes from DEGAP.py's required --target_ends/-e argument and is
        written to the internal file consumed by TelSeekerPart2.
        """
        print(f"[Step 0/4] Loading target chromosome ends...")
        print(f"-" * 80)

        check_dir = self.out / "genome.telomere.check"
        check_dir.mkdir(parents=True, exist_ok=True)
        need_extension_file = check_dir / "need_extension_chr_end.txt"

        with open(need_extension_file, 'w') as f:
            for target_end in self.target_ends:
                f.write(f"{target_end}\n")

        print(f"[Step 0/4] Target chromosome ends: {len(self.target_ends)}")
        for target_end in self.target_ends[:10]:
            print(f"  - {target_end}")
        if len(self.target_ends) > 10:
            print(f"  ... and {len(self.target_ends) - 10} more")
        print(f"[Step 0/4] Target list saved to: {need_extension_file}")
        print()

    def _step1_extract_telomeric_reads(self):
        """
        Step 1: Extract telomeric reads from preprocessed data.
        
        Uses TelSeekerPart1.TeloReadsExtractor to extract reads that contain
        telomeric sequences at their ends.
        
        Input: 
            - hifi_reads_part/ and/or ont_reads_part/ (created by DEGAP)
        
        Output:
            - part1.telo.reads/left.telo.reads.fa
            - part1.telo.reads/right.telo.reads.fa
            - part1.telo.reads/Global.*.fa
            - part1.telo.reads/part1.log
        """
        print(f"[Step 1/4] Extracting telomeric reads...")
        print(f"-" * 80)

        # Check if Step 1 output already exists (skip mechanism)
        part1_dir = self.out / "part1.telo.reads"
        global_left = part1_dir / "Global.left.telo.reads.fa"
        global_right = part1_dir / "Global.right.telo.reads.fa"

        if self._check_step1_complete(global_left, global_right):
            print(f"[Step 1/4] Found existing telomeric reads files:")
            print(f"  - {global_left}")
            print(f"  - {global_right}")
            print(f"[Step 1/4] Skipping telomeric reads extraction (already complete) ✓")
            print()
            return
        
        try:
            # Import TeloReadsExtractor
            from TelSeekerPart1 import TeloReadsExtractor
            
            # Create extractor with parameters from TelSeeker
            extractor = TeloReadsExtractor(
                output_dir=str(self.out),           # TelSeeker output directory
                motif=self.motif,                    # Telomere motif
                threads=self.thread,                 # Use thread parameter for parallel processing
                batch_size=1000,                     # Batch size (default 1000 reads)
                overlapping=False,                   # Non-overlapping count
                tel_n=self.tel_n,
                tel_r=self.tel_r,
                tel_mm=self.tel_mm
            )
            
            # Run extraction
            extractor.run()

            print(f"\n[Step 1/4] Telomeric reads extraction complete ✓")
            print()

        except ImportError as e:
            print(f"\n[Step 1/4] ERROR: Failed to import TelSeekerPart1")
            print(f"  Error: {e}")
            raise
        except Exception as e:
            print(f"\n[Step 1/4] ERROR: Telomeric reads extraction failed")
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _check_step1_complete(self, global_left: Path, global_right: Path) -> bool:
        """
        Check if Step 1 (telomeric reads extraction) is already complete.
        
        Args:
            global_left: Path to Global.left.telo.reads.fa
            global_right: Path to Global.right.telo.reads.fa
        
        Returns:
            True if both files exist and are not empty, False otherwise
        """
        # Check if both files exist
        if not global_left.exists() or not global_right.exists():
            return False
        
        # Check if both files are not empty
        try:
            if global_left.stat().st_size == 0 or global_right.stat().st_size == 0:
                print(f"[Step 1/4] Warning: Found empty telomeric reads files, will re-run extraction")
                return False
        except Exception as e:
            print(f"[Step 1/4] Warning: Error checking file sizes: {e}")
            return False
        
        return True
    
    def _check_step2_complete(self, part2_dir: Path) -> bool:
        """
        Check if Step 2 (chromosome end extension) is already complete.
        
        Args:
            part2_dir: Path to part2.chr.end.job directory
        
        Returns:
            True if directory exists and contains chromosome end subdirectories, False otherwise
        """
        need_extension_file = self.out / 'genome.telomere.check' / 'need_extension_chr_end.txt'

        if not need_extension_file.exists():
            return False

        try:
            with open(need_extension_file, 'r') as f:
                expected_ends = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        except Exception as e:
            print(f"[Step 2/4] Warning: Error reading expected chromosome ends: {e}")
            return False

        if not expected_ends:
            print(f"[Step 2/4] No chromosome ends require extension")
            return True

        # Check if directory exists
        if not part2_dir.exists():
            return False

        try:
            missing_or_incomplete = []
            for chr_end in expected_ends:
                chr_dir = part2_dir / chr_end
                if not chr_dir.is_dir():
                    missing_or_incomplete.append(chr_end)
                    continue

                linker_complete = (chr_dir / 'linker.fa').exists() and (chr_dir / 'linker.info').exists()
                extension_complete = (chr_dir / 'extension' / 'extension.summary').exists()

                if not (linker_complete or extension_complete):
                    missing_or_incomplete.append(chr_end)

            if missing_or_incomplete:
                preview = ', '.join(missing_or_incomplete[:5])
                if len(missing_or_incomplete) > 5:
                    preview += f", ... and {len(missing_or_incomplete) - 5} more"
                print(f"[Step 2/4] Incomplete chromosome end results: {preview}")
                return False

            return True

        except Exception as e:
            print(f"[Step 2/4] Warning: Error checking part2 directory: {e}")
            return False
    
    def _step2_extend_chromosome_ends(self):
        """
        Step 2: Extend chromosome ends.
        
        Calls TelSeekerPart2.py via command line to:
        - Build workspace for each chromosome end
        - Check direct connections
        - Perform iterative extension
        
        Input:
            - genome.telomere.check/need_extension_chr_end.txt
            - part1.telo.reads/Global.*.fa
            - HiFi.reads.stat / ONT.reads.stat
        
        Output:
            - part2.chr.end.job/<chr_end>/
        """
        print(f"[Step 2/4] Extending chromosome ends...")
        print(f"-" * 80)

        # Check if Step 2 output already exists (skip mechanism)
        part2_dir = self.out / 'part2.chr.end.job'
        if self._check_step2_complete(part2_dir):
            print(f"[Step 2/4] Found existing chromosome end extension results:")
            print(f"  - {part2_dir}")
            print(f"[Step 2/4] Skipping chromosome end extension (already complete) ✓")
            print()
            return

        # Check if Step 2 prerequisites exist
        if not self._check_step2_prerequisites():
            print(f"[Step 2/4] ERROR: Missing prerequisites for Step 2")
            raise FileNotFoundError("Required files for Step 2 not found")
        
        try:
            # Build TelSeekerPart2.py command
            cmd = self._build_part2_command()
            
            print(f"\n[Step 2/4] Launching TelSeekerPart2.py...")
            print(f"  Command: {' '.join(cmd[:5])}... ({len(cmd)} args total)")
            print()

            # Execute TelSeekerPart2.py
            import subprocess
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )

            # Print Part2 output
            if result.stdout:
                print(result.stdout)

            # Check execution result
            if result.returncode != 0:
                print(f"\n[Step 2/4] ERROR: TelSeekerPart2.py failed with exit code {result.returncode}")
                if result.stderr:
                    print(f"\nError output:")
                    print(result.stderr)
                raise RuntimeError(f"TelSeekerPart2.py failed")

            print(f"\n[Step 2/4] Chromosome end extension complete ✓")
            print()

        except FileNotFoundError as e:
            print(f"\n[Step 2/4] ERROR: TelSeekerPart2.py not found")
            print(f"  Error: {e}")
            print(f"  Make sure TelSeekerPart2.py is in the same directory as TelSeeker.py")
            raise
        except Exception as e:
            print(f"\n[Step 2/4] ERROR: Chromosome end extension failed")
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _build_part2_command(self) -> list:
        """
        Build command line arguments for TelSeekerPart2.py.

        Returns:
            List of command arguments
        """
        # Get the directory where TelSeeker.py is located
        telseeker_dir = Path(__file__).parent.resolve()
        part2_script = telseeker_dir / 'TelSeekerPart2.py'

        cmd = [
            sys.executable,              # python
            str(part2_script),           # absolute path to TelSeekerPart2.py
            '--out', str(self.out),
            '--genome', str(self.genome_file),
            '--kmer_num', str(self.kmer_num),
            '--kmer_size', str(self.kmer_size),
            '--work', str(self.work),
            '-t', str(self.thread),
            '--edge', str(self.edge)
        ]

        # Add kmer_filter flag if enabled
        if self.kmer_filter:
            cmd.append('--kmer_filter')

        # Add max_rounds parameter (unified with gapfiller and ctglinker)
        if hasattr(self, 'MaximumExtensionRound') and self.MaximumExtensionRound is not None:
            cmd.extend(['--max_rounds', str(self.MaximumExtensionRound)])

        # Add max_extension_length parameter
        if hasattr(self, 'MaximumExtensionLength') and self.MaximumExtensionLength is not None:
            cmd.extend(['--max_extension_length', str(self.MaximumExtensionLength)])

        # Add original reads paths if available (support single file or multiple files)
        original_hifi = self.original_reads_info.get('original_hifi')
        if original_hifi:
            if isinstance(original_hifi, (list, tuple)):
                cmd.extend(['--hifi'] + [str(p) for p in original_hifi])
            else:
                cmd.extend(['--hifi', str(original_hifi)])

        original_ont = self.original_reads_info.get('original_ont')
        if original_ont:
            if isinstance(original_ont, (list, tuple)):
                cmd.extend(['--ont'] + [str(p) for p in original_ont])
            else:
                cmd.extend(['--ont', str(original_ont)])

        return cmd
    
    def _step3_integrate_results(self):
        """
        Step 3: Integrate and summarize Part2 extension results.
        
        Reads all chromosome end results from part2.chr.end.job/ and generates:
        - check_part2_jobs.csv: Summary of all chromosome ends
        
        Output:
            - part3.integration.results/check_part2_jobs.csv
        """
        print(f"[Step 3/4] Integrating results...")
        print(f"-" * 80)
        
        part2_dir = self.out / 'part2.chr.end.job'
        part3_dir = self.out / 'part3.integration.results'
        
        # Check if Part2 results exist
        if not part2_dir.exists():
            print(f"[Step 3/4] Warning: No Part2 results found at {part2_dir}")
            print(f"[Step 3/4] Skipping integration")
            print()
            return
        
        # Create Part3 output directory
        part3_dir.mkdir(parents=True, exist_ok=True)
        
        # Collect results from all chromosome ends
        results = self._collect_part2_results(part2_dir)
        
        # Write summary CSV
        csv_file = part3_dir / 'check_part2_jobs.csv'
        self._write_results_csv(results, csv_file)
        
        # Print summary statistics
        self._print_integration_summary(results)
        
        # Integrate genome sequences
        print(f"\n[Step 3/4] Integrating genome sequences...")
        final_genome = self._integrate_genome_sequences(part2_dir, results, part3_dir)
        
        # Prepare final-genome chromosome ends for manual telomere review.
        if final_genome and final_genome.exists():
            print(f"\n[Step 3/4] Preparing final genome for manual telomere review...")
            self._analyze_final_genome(final_genome, part3_dir)
        
        print(f"\n[Step 3/4] Integration complete ✓")
        print(f"  Statistics saved to: {csv_file}")
        if final_genome:
            print(f"  Final genome saved to: {final_genome}")
            print(f"  Telomere check results: {part3_dir / 'final.genome.telomere.check'}")
        print()
    
    def _collect_part2_results(self, part2_dir: Path) -> list:
        """
        Collect results from all chromosome end subdirectories.
        
        Args:
            part2_dir: Path to part2.chr.end.job directory
        
        Returns:
            List of result dictionaries
        """
        results = []
        
        # Get all subdirectories
        chr_end_dirs = sorted([d for d in part2_dir.iterdir() if d.is_dir()])
        
        print(f"[Step 3/4] Found {len(chr_end_dirs)} chromosome ends to analyze")
        print()
        
        for chr_end_dir in chr_end_dirs:
            chr_end = chr_end_dir.name
            result = {
                'chr_end': chr_end,
                'extended': 'no',
                'connected_read': 'NA',
                'round_num': 'NA',
                'connection_type': 'NA'
            }
            
            # Check if linker.fa and linker.info exist
            linker_fa = chr_end_dir / 'linker.fa'
            linker_info = chr_end_dir / 'linker.info'
            
            if linker_fa.exists() and linker_info.exists():
                # A linker was produced. Final telomere completeness is reviewed
                # separately from the chromosome-end sequence and motif plots.
                result['extended'] = 'yes'
                
                # Parse linker.info
                info = self._parse_linker_info(linker_info)
                result['connected_read'] = info.get('connected_read', 'NA')
                result['round_num'] = info.get('round_num', 'NA')
                result['connection_type'] = info.get('connection_type', 'NA')
            
            results.append(result)
        
        return results
    
    def _parse_linker_info(self, linker_info_file: Path) -> dict:
        """
        Parse linker.info file to extract connection information.
        
        Args:
            linker_info_file: Path to linker.info file
        
        Returns:
            Dictionary with parsed information
        """
        info = {
            'connection_type': 'NA',
            'round_num': 'NA',
            'connected_read': 'NA'
        }
        
        try:
            with open(linker_info_file, 'r') as f:
                lines = [line.strip() for line in f.readlines()]
            
            fields = {}
            for line in lines:
                if ':' not in line:
                    continue
                key, value = line.split(':', 1)
                fields[key.strip()] = value.strip()

            method = fields.get('Connection Method')
            status = fields.get('Status', '')

            if method:
                info['connection_type'] = method
            elif 'Direct connection' in status:
                info['connection_type'] = 'direct'
            elif 'Extension connection' in status:
                info['connection_type'] = 'extension'

            if info['connection_type'] == 'direct':
                info['round_num'] = '0'
            elif 'Extension Rounds' in fields:
                info['round_num'] = fields['Extension Rounds']
            elif 'Extension Rounds Attempted' in fields:
                info['round_num'] = fields['Extension Rounds Attempted']

            if 'Connected Read' in fields:
                info['connected_read'] = fields['Connected Read']
        
        except Exception as e:
            print(f"  Warning: Error parsing {linker_info_file}: {e}")
        
        return info
    
    def _write_results_csv(self, results: list, csv_file: Path):
        """
        Write results to CSV file.
        
        Args:
            results: List of result dictionaries
            csv_file: Output CSV file path
        """
        import csv
        
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            # Write header
            writer.writerow(['Chr_end', 'Extended', 'Connected_read', 'Round_num', 'Connection_type'])
            
            # Write data rows
            for result in results:
                writer.writerow([
                    result['chr_end'],
                    result['extended'],
                    result['connected_read'],
                    result['round_num'],
                    result['connection_type']
                ])
    
    def _integrate_genome_sequences(self, part2_dir: Path, results: list, part3_dir: Path) -> Path:
        """
        Integrate successful linker sequences into the original genome.
        
        Args:
            part2_dir: Path to part2.chr.end.job directory
            results: List of result dictionaries
            part3_dir: Path to part3.integration.results directory
        
        Returns:
            Path to final genome file, or None if integration failed
        """
        from Bio import SeqIO
        from Bio.SeqRecord import SeqRecord
        
        # Filter successful results
        successful = [r for r in results if r['extended'] == 'yes']
        
        if not successful:
            print(f"  No successful connections to integrate")
            return None
        
        print(f"  Integrating {len(successful)} successful connections...")
        
        # Load original genome
        try:
            genome_records = {rec.id: rec for rec in SeqIO.parse(self.genome_file, 'fasta')}
            print(f"  Loaded {len(genome_records)} chromosomes from original genome")
        except Exception as e:
            print(f"  Error loading genome: {e}")
            return None
        
        # Process each successful connection
        modifications = {}
        for result in successful:
            chr_end = result['chr_end']
            chr_end_dir = part2_dir / chr_end
            
            # Parse chromosome name and end type
            parts = chr_end.rsplit('.', 1)
            if len(parts) != 2:
                print(f"  Warning: Invalid chr_end format: {chr_end}")
                continue
            
            chr_name, end_type = parts
            
            if chr_name not in genome_records:
                print(f"  Warning: Chromosome {chr_name} not found in genome")
                continue
            
            # Determine seedlen from seed.fa
            seed_file = chr_end_dir / 'seed.fa'
            if not seed_file.exists():
                print(f"  Warning: seed.fa not found for {chr_end}")
                continue
            
            try:
                seed_record = next(SeqIO.parse(seed_file, 'fasta'))
                seedlen = len(seed_record.seq)
            except Exception as e:
                print(f"  Warning: Error reading seed.fa for {chr_end}: {e}")
                continue
            
            # Read linker sequence
            linker_file = chr_end_dir / 'linker.fa'
            if not linker_file.exists():
                print(f"  Warning: linker.fa not found for {chr_end}")
                continue
            
            try:
                linker_record = next(SeqIO.parse(linker_file, 'fasta'))
                linker_seq = linker_record.seq
            except Exception as e:
                print(f"  Warning: Error reading linker.fa for {chr_end}: {e}")
                continue
            
            # Store modification
            if chr_name not in modifications:
                modifications[chr_name] = {}
            
            modifications[chr_name][end_type] = {
                'seedlen': seedlen,
                'linker_seq': linker_seq
            }
            
            print(f"    ✓ {chr_end}: seedlen={seedlen}bp, linker={len(linker_seq)}bp")
        
        # Apply modifications to genome
        print(f"\n  Applying modifications to genome...")
        modified_records = []
        
        for chr_name, record in genome_records.items():
            if chr_name in modifications:
                original_seq = record.seq
                original_len = len(original_seq)
                
                # Determine which parts to use
                left_mod = modifications[chr_name].get('L')
                right_mod = modifications[chr_name].get('R')
                
                if left_mod and right_mod:
                    # Both ends need modification
                    left_seedlen = left_mod['seedlen']
                    right_seedlen = right_mod['seedlen']
                    left_linker = left_mod['linker_seq']
                    right_linker = right_mod['linker_seq']
                    
                    # New sequence = left_linker + middle + right_linker
                    middle = original_seq[left_seedlen:-right_seedlen]
                    new_seq = left_linker + middle + right_linker
                    print(f"    ✓ {chr_name}.L+R: {original_len}bp → {len(new_seq)}bp")
                    
                elif left_mod:
                    # Only left end modification
                    seedlen = left_mod['seedlen']
                    linker_seq = left_mod['linker_seq']
                    new_seq = linker_seq + original_seq[seedlen:]
                    print(f"    ✓ {chr_name}.L: {original_len}bp → {len(new_seq)}bp")
                    
                elif right_mod:
                    # Only right end modification
                    seedlen = right_mod['seedlen']
                    linker_seq = right_mod['linker_seq']
                    new_seq = original_seq[:-seedlen] + linker_seq
                    print(f"    ✓ {chr_name}.R: {original_len}bp → {len(new_seq)}bp")
                else:
                    # Should not happen
                    new_seq = original_seq
                
                # Create modified record
                modified_record = SeqRecord(
                    seq=new_seq,
                    id=record.id,
                    description=f"{record.description} [telomere_extended]"
                )
                modified_records.append(modified_record)
            else:
                # Keep original record
                modified_records.append(record)
        
        # Write final genome
        final_genome_file = part3_dir / 'final.genome.fa'
        try:
            SeqIO.write(modified_records, final_genome_file, 'fasta')
            print(f"\n  Successfully integrated genome with {len(modifications)} modified chromosomes")
            return final_genome_file
        except Exception as e:
            print(f"  Error writing final genome: {e}")
            return None
    
    def _analyze_final_genome(self, final_genome_file: Path, part3_dir: Path):
        """
        Prepare final chromosome-end sequences and motif plots for manual review.

        Args:
            final_genome_file: Path to final.genome.fa
            part3_dir: Path to part3.integration.results directory
        """
        try:
            # Import TelomereChecker
            from TelSeekerCheck import TelomereChecker

            checker = TelomereChecker(
                genome_file=str(final_genome_file),
                motif=self.motif,
                output_dir=str(part3_dir),
                check_name='final.genome.telomere.check',
            )
            checker.run()

            check_output_dir = part3_dir / 'final.genome.telomere.check'
            print("  ✓ Final manual-review evidence prepared")
            print("    Automatic telomeric/untelomeric calls are not generated")
            print(f"    Results saved to: {check_output_dir}")
            
        except ImportError as e:
            print(f"  Warning: Could not import TelomereChecker: {e}")
        except Exception as e:
            print(f"  Warning: Error during telomere analysis: {e}")
            import traceback
            traceback.print_exc()
    
    def _print_integration_summary(self, results: list):
        """
        Print summary statistics of integration results.
        
        Args:
            results: List of result dictionaries
        """
        total = len(results)
        
        if total == 0:
            print(f"\n[Step 3/4] Summary Statistics:")
            print(f"  No chromosome ends found to analyze")
            return
        
        extended_yes = sum(1 for r in results if r['extended'] == 'yes')
        extended_no = total - extended_yes
        
        direct = sum(1 for r in results if r['connection_type'] == 'direct')
        extension = sum(1 for r in results if r['connection_type'] == 'extension')
        
        print(f"\n[Step 3/4] Summary Statistics:")
        print(f"  Total chromosome ends:     {total}")
        print(f"  Successfully extended:     {extended_yes} ({extended_yes/total*100:.1f}%)")
        print(f"  Failed to extend:          {extended_no} ({extended_no/total*100:.1f}%)")
        print("  Final telomere status:     manual review required")
        
        if extended_yes > 0:
            print(f"\n  Connection Methods:")
            print(f"    Direct connection:       {direct}")
            print(f"    Extension connection:    {extension}")
    
    def _check_step2_prerequisites(self) -> bool:
        """
        Check if all prerequisites for Step 2 exist.
        
        Required files:
        - genome.telomere.check/need_extension_chr_end.txt
        - part1.telo.reads/Global.left.telo.reads.fa
        - part1.telo.reads/Global.right.telo.reads.fa
        - HiFi.reads.stat or ONT.reads.stat
        
        Returns:
            True if all prerequisites exist, False otherwise
        """
        print(f"[Step 2/4] Checking prerequisites...")
        
        missing_files = []
        
        # Check need_extension_chr_end.txt
        need_extension_file = self.out / 'genome.telomere.check' / 'need_extension_chr_end.txt'
        if not need_extension_file.exists():
            missing_files.append(str(need_extension_file))
            print(f"  ✗ Missing: {need_extension_file}")
            print(f"     Hint: Provide target ends with -e/--target_ends; use TelSeekerCheck.py only for manual plots and end sequences")
        else:
            print(f"  ✓ Found: need_extension_chr_end.txt")
        
        # Check Global telomeric reads files
        part1_dir = self.out / 'part1.telo.reads'
        global_left = part1_dir / 'Global.left.telo.reads.fa'
        global_right = part1_dir / 'Global.right.telo.reads.fa'
        
        if not global_left.exists():
            missing_files.append(str(global_left))
            print(f"  ✗ Missing: {global_left}")
        else:
            print(f"  ✓ Found: Global.left.telo.reads.fa")
        
        if not global_right.exists():
            missing_files.append(str(global_right))
            print(f"  ✗ Missing: {global_right}")
        else:
            print(f"  ✓ Found: Global.right.telo.reads.fa")
        
        # Check reads statistics files
        hifi_stat = self.out / 'HiFi.reads.stat'
        ont_stat = self.out / 'ONT.reads.stat'
        
        if not hifi_stat.exists() and not ont_stat.exists():
            missing_files.append("HiFi.reads.stat or ONT.reads.stat")
            print(f"  ✗ Missing: reads statistics files")
        else:
            if hifi_stat.exists():
                print(f"  ✓ Found: HiFi.reads.stat")
            if ont_stat.exists():
                print(f"  ✓ Found: ONT.reads.stat")
        
        if missing_files:
            print(f"\n  Missing {len(missing_files)} required file(s)")
            return False
        
        print(f"  All prerequisites found ✓")
        return True
    
    def _step4_generate_visualization(self):
        """
        Step 4: Generate interactive HTML visualization report.
        
        Calls TelSeekerVisualizer.py to generate an interactive HTML report
        that visualizes all results from previous steps.
        
        Output:
            - visual.report/Global.report.html: Interactive visualization report
        """
        print(f"[Step 4/4] Generating visualization report...")
        print(f"-" * 80)
        
        try:
            # Get the directory where TelSeeker.py is located
            telseeker_dir = Path(__file__).parent.resolve()
            visualizer_script = telseeker_dir / 'TelSeekerVisualizer.py'
            
            # Check if visualizer script exists
            if not visualizer_script.exists():
                print(f"[Step 4/4] Warning: TelSeekerVisualizer.py not found at {visualizer_script}")
                print(f"[Step 4/4] Skipping visualization report generation")
                print()
                return
            
            # Build command to run visualizer
            cmd = [
                sys.executable,                  # python
                str(visualizer_script),          # TelSeekerVisualizer.py
                '--out', str(self.out)           # output directory
            ]
            
            print(f"[Step 4/4] Running TelSeekerVisualizer.py...")
            print(f"  Output directory: {self.out}")
            print()
            
            # Execute visualizer
            import subprocess
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )
            
            # Print visualizer output
            if result.stdout:
                print(result.stdout)
            
            # Check execution result
            if result.returncode != 0:
                print(f"\n[Step 4/4] Warning: TelSeekerVisualizer.py failed with exit code {result.returncode}")
                if result.stderr:
                    print(f"Error output:")
                    print(result.stderr)
                print(f"[Step 4/4] Visualization report generation failed, but workflow can continue")
                print()
                return
            
            # Check if report was generated in new location
            report_file = self.out / 'visual.report' / 'Global.report.html'
            if report_file.exists():
                print(f"\n[Step 4/4] Visualization report generated successfully ✓")
                print(f"  Report location: {report_file}")
                print(f"  Open this file in a web browser to view the interactive report")
            else:
                print(f"\n[Step 4/4] Warning: Global.report.html was not generated")
            
            print()
            
        except Exception as e:
            print(f"\n[Step 4/4] Warning: Visualization report generation failed")
            print(f"  Error: {e}")
            print(f"  This is non-critical, workflow can continue")
            import traceback
            traceback.print_exc()
            print()


# For testing
if __name__ == '__main__':
    print("TelSeeker module")
    print("Usage: Called from DEGAP.py with --mode telseeker")
