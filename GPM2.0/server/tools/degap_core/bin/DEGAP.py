import re
import os
import sys
import argparse  # Replace getopt
import pysam
from pysam import AlignmentFile
import math
import Bio
from Bio import SeqIO
import GapFiller
from GapFiller import GapFiller
import CtgLinker
from CtgLinker import CtgLinker
# Note: TelSeeker is now the main module, TelSeekerPart1 is a submodule
# Import handled based on mode selection

import selectRawReads
from selectRawReads import selectRawReads
import subprocess
import GapfillerVisualizer
from GapfillerVisualizer import GapfillerLogParser, HTMLReportGenerator
import glob
def generate_stats_with_seqkit(input_file, output_file):
	try:
		# 直接调用 seqkit（不检查是否安装，不做本地检测）
		cmd = ['seqkit', 'stats', input_file, '-T']  # TSV 输出：file\tformat\ttype\tnum_seqs\tsum_len\tmin_len\tavg_len\tmax_len
		result = subprocess.run(cmd, capture_output=True, text=True, check=True)
		lines = [l for l in result.stdout.strip().split('\n') if l.strip()]
		if len(lines) < 2:
			raise RuntimeError('seqkit stats returned no data')
		cols = lines[1].split('\t')
		if len(cols) < 8:
			raise RuntimeError('seqkit stats TSV columns insufficient')
		# 解析列 (正确的索引)
		reads_count = int(cols[3])      # num_seqs
		total_length = int(cols[4])     # sum_len
		min_length = int(cols[5])       # min_len
		mean_length = float(cols[6])    # avg_len
		max_length = int(cols[7])       # max_len
		# 计算 SeedLength
		a = 10**(int(math.log(max_length, 10))) if max_length > 0 else 1
		b = max_length / a + 1
		seed_length = int(a * b)
		# 写文件（保持原有键名/拼写）
		with open(output_file, 'w') as f:
			f.write(f"Number\t{reads_count}\n")
			f.write(f"TolalLenth\t{total_length}\n")
			f.write(f"MaxLength\t{max_length}\n")
			f.write(f"MeanLength\t{int(mean_length)}\n")
			f.write(f"SeedLength\t{seed_length}\n")
		return reads_count, total_length, max_length, mean_length, seed_length
	except subprocess.CalledProcessError as e:
		print(f"Error running seqkit stats: {e}")
		print(f"seqkit stderr: {e.stderr}")
		sys.exit(1)
	except Exception as e:
		print(f"Error generating statistics with seqkit: {e}")
		sys.exit(1)


def preprocess_reads_files(hifi_reads, ont_reads, out, data_type):
    """
    预处理reads文件（STEP 1）：
    1. 检测文件格式（FASTQ或FASTA）
    2. 统一转换为FASTA格式供workflow使用
       - 支持单文件和多文件输入（FASTA/FASTQ/.gz）
       - 使用 seqkit fq2fa 合并/转换，始终输出 FASTA

    Returns: (hifi_fa, hifi_orig, hifi_fmt, ont_fa, ont_orig, ont_fmt)
    """
    processed_dir = os.path.join(out, "processed_reads")
    os.makedirs(processed_dir, exist_ok=True)

    def normalize_file_list(file_input):
        if file_input is None:
            return []
        if isinstance(file_input, (list, tuple)):
            return [str(f) for f in file_input if f]
        return [str(file_input)]

    def detect_file_format(file_path):
        lower = file_path.lower()
        if lower.endswith(('.fastq', '.fastq.gz', '.fq', '.fq.gz')):
            return 'fastq'
        if lower.endswith(('.fasta', '.fasta.gz', '.fa', '.fa.gz', '.fna', '.fna.gz')):
            return 'fasta'
        raise ValueError(f"Unsupported file format: {file_path}")

    def process_single_file(file_input, file_type="HiFi"):
        """
        处理单个或多个reads文件，输出统一的FASTA文件
        """
        file_list = normalize_file_list(file_input)
        if not file_list:
            return None, None, None

        prefix = "ont_reads" if file_type == "ONT" else "hifi_reads"
        working_fa = os.path.join(processed_dir, f"{prefix}.fa")

        input_formats = []
        for file_path in file_list:
            if not os.path.exists(file_path):
                print(f"Error: {file_type} reads file does not exist: {file_path}")
                sys.exit(1)
            try:
                input_formats.append(detect_file_format(file_path))
            except ValueError as e:
                print(f"Error: {e}")
                sys.exit(1)

        if 'fastq' in input_formats and 'fasta' in input_formats:
            original_format = 'mixed'
        elif 'fastq' in input_formats:
            original_format = 'fastq'
        else:
            original_format = 'fasta'

        if not os.path.exists(working_fa):
            try:
                if len(file_list) == 1:
                    print(f"Converting {file_type} reads to FASTA...")
                    print(f"    Input:  {file_list[0]}")
                else:
                    print(f"Merging and converting {len(file_list)} {file_type} files to FASTA...")
                    for idx, f in enumerate(file_list, 1):
                        print(f"    [{idx}] {f}")
                print(f"    Output: {working_fa}")

                # seqkit fq2fa handles FASTA/FASTQ and .gz, always outputs FASTA
                cmd = ['seqkit', 'fq2fa', '-o', working_fa] + file_list
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                print(f"  ✓ {file_type} FASTA ready: {working_fa}")
            except subprocess.CalledProcessError as e:
                print(f"  ✗ Error preparing {file_type} FASTA:")
                print(f"    {e.stderr}")
                sys.exit(1)
            except FileNotFoundError:
                print(f"  ✗ Error: seqkit not found. Please install seqkit:")
                print(f"    conda install -c bioconda seqkit")
                sys.exit(1)
        else:
            print(f"  ✓ Using existing {file_type} FASTA: {working_fa}")

        original_input = file_list if len(file_list) > 1 else file_list[0]
        return working_fa, original_input, original_format

    # 根据data_type处理文件
    if data_type == 'mixed':
        hifi_fa, hifi_orig, hifi_fmt = process_single_file(hifi_reads, "HiFi")
        ont_fa, ont_orig, ont_fmt = process_single_file(ont_reads, "ONT")
    elif data_type == 'ont':
        # 单ONT模式：hifi_reads参数实际传入的是ONT文件（现在可能是列表）
        ont_fa, ont_orig, ont_fmt = process_single_file(hifi_reads, "ONT")
        hifi_fa, hifi_orig, hifi_fmt = None, None, None
    else:
        # 单HiFi模式
        hifi_fa, hifi_orig, hifi_fmt = process_single_file(hifi_reads, "HiFi")
        ont_fa, ont_orig, ont_fmt = None, None, None

    return (hifi_fa, hifi_orig, hifi_fmt, ont_fa, ont_orig, ont_fmt)

def convert_extension_fasta_to_fastq(extension_fasta, original_fastq, output_fastq):
	"""
	将筛选后的extension reads FASTA转换为FASTQ
	从原始FASTQ中提取对应reads的质量信息
	"""
	if not os.path.exists(extension_fasta) or os.path.getsize(extension_fasta) == 0:
		print(f"Warning: Extension FASTA file not found or empty: {extension_fasta}")
		return None

	if not os.path.exists(original_fastq):
		print(f"Warning: Original FASTQ file not found: {original_fastq}")
		return None

	print(f"Converting {extension_fasta} to FASTQ format using quality from {original_fastq}")

	# 读取extension reads ID列表
	extension_ids = set()
	try:
		for record in SeqIO.parse(extension_fasta, "fasta"):
			extension_ids.add(record.id)
		print(f"Found {len(extension_ids)} extension reads to convert")
	except Exception as e:
		print(f"Error reading extension FASTA: {e}")
		return None

	if len(extension_ids) == 0:
		print("No extension reads found in FASTA file")
		return None

	# 从原始FASTQ中提取对应reads
	converted_count = 0
	try:
		with open(output_fastq, 'w') as out_f:
			# Determine format of original file
			if original_fastq.endswith(('.fastq', '.fq', '.fastq.gz', '.fq.gz')):
				format_type = "fastq"
			else:
				format_type = "fasta"

			for record in SeqIO.parse(original_fastq, format_type):
				if record.id in extension_ids:
					if format_type == "fastq":
						# Write as FASTQ with original quality
						SeqIO.write(record, out_f, "fastq")
					else:
						# If original was FASTA, generate dummy quality scores
						record.letter_annotations["phred_quality"] = [40] * len(record.seq)
						SeqIO.write(record, out_f, "fastq")
					converted_count += 1

		print(f"Successfully converted {converted_count} reads to FASTQ format: {output_fastq}")
		return output_fastq if converted_count > 0 else None

	except Exception as e:
		print(f"Error converting to FASTQ: {e}")
		return None

def usage():
	print ("DEGAP v2.0 - Dynamic Elongation of a Genome Assembly Path")
	print ("==========================================================")
	print ("\nData Input Options:")
	print ("--hifi file1 [file2 ...]         HiFi read file(s) (FASTA/FASTQ, supports multiple files)")
	print ("--ont file1 [file2 ...]          ONT read file(s) (FASTA/FASTQ, supports multiple files)")
	print ("Note: Use --hifi alone for HiFi-only mode")
	print ("      Use --ont alone for ONT-only mode")
	print ("      Use both --hifi and --ont for Mixed mode")
	print ("\nBasic Options:")
	print ("-o | --out ./path/               Output directory")
	print ("-t | --thread num                Number of threads (default: 20)")
	print ("--remove 1|2|3                   File cleanup level (default: 2)")
	print ("                                 1: only keep final result")
	print ("                                 2: keep every round basic result")
	print ("                                 3: keep all files")
	print ("\nFiltering Options:")
	print ("--filterDepthHifi num            Filter HiFi reads by mapped depth (default: None)")
	print ("--filterDepthOnt num             Filter ONT reads by mapped depth (default: None)")
	print ("                                 Example: 0.3 means filter reads with depth")
	print ("                                 outside [0.3*avgdepth, (2-0.3)*avgdepth] range")
	print ("--edge num                       Max edge length for misassembly detection (default: 500)")
	print ("\nExtension Control Options:")
	print ("--MaximumExtensionLength num     Maximum cumulative extension length in bp (default: None, no limit)")
	print ("                                 Extension stops when total extended length exceeds this value")
	print ("                                 Applies to all modes (gapfiller/ctglinker/telseeker/telseeker_ctg)")
	print ("--MaximumExtensionRound num      Maximum number of extension rounds (default: None, no limit)")
	print ("                                 Extension stops when round number exceeds this value")
	print ("                                 Applies to all modes (gapfiller/ctglinker/telseeker/telseeker_ctg)")
	print ("                                 Minimum recommended value: 5")
	print ("\nK-mer Filtering Options:")
	print ("--kmer_filter                    Enable k-mer filtering to reduce reads before alignment (default: disabled)")
	print ("                                 Note: K-mer filtering can significantly speed up processing for large datasets")
	print ("                                 If gap filling fails with this option, try without it")
	print ("--kmer_size | -ks num            K-mer size for filtering reads (default: 41, only used when --kmer_filter is enabled)")
	print ("--kmer_num | -kn num             Number of k-mers to use for filtering (default: 20, only used when --kmer_filter is enabled)")
	print ("\nMode Options:")
	print ("--mode gapfiller|ctglinker|telseeker|telseeker_ctg")
	print ("\nResume Options:")
	print ("--resume num                     Resume from specified round (e.g.: --resume 118)")
	print ("--resume_auto                    Automatically resume from last interrupted round")
	print ("\n=== MODE SPECIFIC PARAMETERS ===")
	print ("\ngapfiller mode:")
	print ("\t--seqleft sequence_file      Sequence before GAP (FASTA format)")
	print ("\t--seqright sequence_file     Sequence after GAP (FASTA format)")
	print ("\t--flag left|right            Choose seqleft or seqright as seed (default: left)")

	print ("\ntelseeker mode:")
	print ("\t--genome genome.fasta         Genome file with all chromosomes (FASTA)")
	print ("\t-m | --motif ATCG...          Telomere motif (uppercase A/T/C/G); required in telseeker mode, no default")
	print ("\t--target_ends|-e END [END ...] Target chromosome ends to extend, e.g. Chr01.L Chr01.R, or one text file")
	print ("\t-tn | --tel-n num             Motif-length units checked at each read end for tel_reads (default: 100)")
	print ("\t-tr | --tel-r num             Minimum terminal hit ratio, hits/tel-n (default: 0.6)")
	print ("\t-tmm | --tel-mm 0|1           Allowed mismatches per motif-length unit (default: 0)")
	print ("\t--work num                    Number of chromosome ends to process in parallel (default: 1)")
	print ("\tNote: telomere checking is independent; pass target ends with -e/--target_ends")

	print ("\ntelseeker_ctg mode:")
	print ("\t--ctg contig.fa L|R            Contig endpoint task; repeat for multiple endpoints")
	print ("\t-m | --motif ATCG...           Telomere motif (uppercase A/T/C/G); required")
	print ("\t-tn | --tel-n num              Motif-length units checked at each read end for tel_reads (default: 100)")
	print ("\t-tr | --tel-r num              Minimum terminal hit ratio, hits/tel-n (default: 0.6)")
	print ("\t-tmm | --tel-mm 0|1            Allowed mismatches per motif-length unit (default: 0)")
	print ("\t--work num                     Number of contig endpoints to process in parallel (default: 1)")

	print ("\nctglinker mode:")
	print ("\t--ctgseq contig_file         Contig set (FASTA format)")
	print ("\n-h | --help                      Show this help message")



def getoptions():
	parser = argparse.ArgumentParser(description='DEGAP: Dynamic Elongation of a Genome Assembly Path',
	                                add_help=False,  # Disable auto-generated help
	                                formatter_class=argparse.RawTextHelpFormatter)

	# Basic parameters
	parser.add_argument('--mode', type=str, help='Operation mode: gapfiller or ctglinker or telseeker or telseeker_ctg')
	parser.add_argument('-o', '--out', type=str, help='Output directory path')
	parser.add_argument('-t', '--thread', type=str, help='Number of threads for parallel processing (default: 20)')
	parser.add_argument('-h', '--help', help='Show help message and exit', action='store_true')

	# Reads input parameters (can be used individually or together for mixed mode)
	# Support multiple input files: --hifi F1.fq.gz F2.fq.gz F3.fq.gz
	parser.add_argument('--hifi', nargs='+', help='HiFi reads file(s) (FASTA/FASTQ format, multiple files supported)')
	parser.add_argument('--ont', nargs='+', help='ONT reads file(s) (FASTA/FASTQ format, multiple files supported)')

	parser.add_argument('--remove', type=int, default=2,
	                   help='1: only keep final result; 2: keep every round basic result; 3: keep all files')
	parser.add_argument('--edge', type=int, default=500, help='Edge Controller set max Edge length')
	parser.add_argument('--filterDepthHifi', type=float, default=None, help='Filter HiFi reads by mapped depth. if num==0.3 means: mapped HiFi reads on depth>=0.3*avgdepth and depth<=(2-0.3)*avgdepth will be filtered')
	parser.add_argument('--filterDepthOnt', type=float, default=None, help='Filter ONT reads by mapped depth. if num==0.2 means: mapped ONT reads on depth>=0.2*avgdepth and depth<=(2-0.2)*avgdepth will be filtered')
	parser.add_argument('--MaximumExtensionLength', type=int, default=None,
	                    help='Maximum cumulative extension length in bp. Extension stops when total extended length exceeds this value. '
	                         'Applies to all modes (gapfiller/ctglinker/telseeker). Default: None (no limit)')
	parser.add_argument('--MaximumExtensionRound', type=int, default=None,
	                    help='Maximum number of extension rounds. Extension stops when round number exceeds this value. '
	                         'Applies to all modes (gapfiller/ctglinker/telseeker). Default: None (no limit). '
	                         'Note: Setting to 0 will skip extension; minimum recommended value is 5')

	# K-mer related parameters
	parser.add_argument('--kmer_filter', action='store_true', help='Enable k-mer filtering to reduce reads before alignment (default: disabled)')
	parser.add_argument('--kmer_size', '-ks', type=int, default=41, help='k-mer size for filtering reads (only used when --kmer_filter is enabled)')
	parser.add_argument('--kmer_num', '-kn', type=int, default=20, help='number of k-mers to use for filtering reads (only used when --kmer_filter is enabled)')


	# Resume functionality
	parser.add_argument('--resume', type=int, help='Resume from specified round')
	parser.add_argument('--resume_auto', action='store_true', help='Automatically resume from last interrupted round')

	# telseeker mode specific parameters
	parser.add_argument('--genome', type=str, help='Genome FASTA file with all chromosomes')
	parser.add_argument('--chr', type=str, help='[Deprecated] Single chromosome FASTA (use --genome instead)')
	parser.add_argument('-m', '--motif', type=str, help='Telomere motif (uppercase A/T/C/G); required in telseeker modes')
	parser.add_argument('--target_ends', '-e', nargs='+',
	                    help='Target chromosome ends for telseeker mode, e.g. Chr01.L Chr01.R, or a text file with one target per line')
	parser.add_argument('--ctg', nargs=2, action='append', metavar=('CONTIG_FASTA', 'END'),
	                    help='Contig endpoint for telseeker_ctg mode; repeat as --ctg contig.fa L --ctg contig2.fa R')
	parser.add_argument('-tn', '--tel-n', type=int, default=100,
	                    help='Number of motif-length units checked at each read end for tel_reads (default: 100)')
	parser.add_argument('-tr', '--tel-r', type=float, default=0.6,
	                    help='Minimum terminal motif-unit hit ratio for tel_reads, computed as hits/tel-n (default: 0.6)')
	parser.add_argument('-tmm', '--tel-mm', type=int, choices=[0, 1], default=0,
	                    help='Allowed mismatches per motif-length unit for tel_reads, 0 or 1 (default: 0)')
	parser.add_argument('--work', '-w', type=int, default=1, help='Number of parallel workers (default: 1)')


	# Parameters for gapfiller mode
	parser.add_argument('--seqleft', type=str, help='Sequence before GAP (FASTA format)')
	parser.add_argument('--seqright', type=str, help='Sequence after GAP (FASTA format)')
	parser.add_argument('--flag', type=str, default='left', help='Choose seqleft or seqright as seed to fill the gap')

	# ctglinker mode specific parameters
	parser.add_argument('--ctgseq', type=str, help='Contig set file path')

	# Show help if no arguments provided
	if len(sys.argv) == 1:
		print("NO PARAMETER!!!")
		print("Use '-h | --help' for same information")
		sys.exit()

	args = parser.parse_args()

	# Handle help information
	if args.help:
		usage()
		sys.exit()

	# Check required parameters
	if not args.mode:
		print("Mode must be specified (gapfiller or ctglinker or telseeker or telseeker_ctg)")
		sys.exit()

	# Determine mode based on parameter combination
	# args.hifi and args.ont are now lists (nargs='+') or None
	if args.hifi and args.ont:
		# Mixed mode: HiFi + ONT (as ultra-long)
		reads_file = args.hifi  # list of HiFi file(s)
		ont_reads = args.ont    # list of ONT file(s)
		data_type = 'mixed'
		print(f"DEGAP: Mixed mode enabled (HiFi + Ultra-long ONT)")
		print(f"  HiFi files ({len(reads_file)}): {', '.join(reads_file)}")
		print(f"  ONT files ({len(ont_reads)}): {', '.join(ont_reads)}")

		# Verify all files exist
		for f in reads_file:
			if not os.path.exists(f):
				print(f"HiFi reads file does not exist: {f}")
				sys.exit()
		for f in ont_reads:
			if not os.path.exists(f):
				print(f"ONT reads file does not exist: {f}")
				sys.exit()

	elif args.hifi:
		reads_file = args.hifi  # list of HiFi file(s)
		ont_reads = None
		data_type = 'hifi'
		print(f"DEGAP: HiFi mode enabled ({len(reads_file)} file(s))")

		for f in reads_file:
			if not os.path.exists(f):
				print(f"HiFi reads file does not exist: {f}")
				sys.exit()

	elif args.ont:
		reads_file = args.ont  # list of ONT file(s)
		ont_reads = None
		data_type = 'ont'
		print(f"DEGAP: ONT mode enabled ({len(reads_file)} file(s))")

		for f in reads_file:
			if not os.path.exists(f):
				print(f"ONT reads file does not exist: {f}")
				sys.exit()

	else:
		print("Either --hifi or --ont (or both for mixed mode) must be specified")
		sys.exit()

	if not args.out:
		print("Output directory must be specified")
		sys.exit()

	# Create kparameters list containing kmer related parameters
	kparameters = [args.kmer_size, args.kmer_num, args.kmer_filter]

	# Resume functionality parameters
	resume_params = (args.resume, args.resume_auto)

	# Build return values (maintain same return format as original function)
	if args.mode == "gapfiller":
		# Check files required for gapfiller mode
		if args.seqleft:
			if os.path.exists(args.seqleft) and os.path.getsize(args.seqleft) != 0:
				seqleft = args.seqleft
			else:
				print("seqleft file doesn't exist or is empty!")
				sys.exit()
		else:
			print("seqleft parameter is required for gapfiller mode")
			sys.exit()

		if args.seqright:
			if os.path.exists(args.seqright) and os.path.getsize(args.seqright) != 0:
				seqright = args.seqright
			else:
				print("seqright file doesn't exist or is empty!")
				sys.exit()
		else:
			print("seqright parameter is required for gapfiller mode")
			sys.exit()

		return [args.mode, args.remove, args.thread or '20', reads_file, args.out,
		        seqleft, seqright, args.flag, args.edge, args.filterDepthHifi, args.filterDepthOnt,
		        args.MaximumExtensionLength, args.MaximumExtensionRound, data_type, ont_reads], kparameters, resume_params
	elif args.mode == "telseeker":
		# Validate required parameters for telseeker
		# Support both --genome (new) and --chr (deprecated)
		genome_file = None
		if args.genome:
			genome_file = args.genome
			if not os.path.exists(genome_file) or os.path.getsize(genome_file) == 0:
				print("--genome file doesn't exist or is empty")
				sys.exit()
		elif args.chr:
			print("Warning: --chr is deprecated, please use --genome instead")
			genome_file = args.chr
			if not os.path.exists(genome_file) or os.path.getsize(genome_file) == 0:
				print("--chr file doesn't exist or is empty")
				sys.exit()
		else:
			print("--genome parameter is required for telseeker mode")
			sys.exit()

		if not args.motif:
			print("--motif parameter is required for telseeker mode and must be uppercase A/T/C/G")
			sys.exit()
		motif = args.motif.strip()
		if re.match(r'^[ACGT]+$', motif) is None:
			print("--motif must be uppercase letters consisting of A/T/C/G only, e.g., TTTAGGG")
			sys.exit()

		if not args.target_ends:
			print("--target_ends/-e parameter is required for telseeker mode")
			sys.exit()

		try:
			from TelSeekerTargets import parse_target_ends
			target_ends = parse_target_ends(args.target_ends, genome_file)
		except ValueError as e:
			print(f"--target_ends/-e error: {e}")
			sys.exit()

		# Work parameter for parallel processing
		work = args.work if args.work else 1
		if args.tel_n <= 0:
			print("--tel-n must be greater than 0")
			sys.exit()
		if args.tel_r <= 0 or args.tel_r > 1:
			print("--tel-r must be in the interval (0, 1]")
			sys.exit()

		# Note: flag parameter is not needed for telseeker mode

		return [args.mode, args.remove, args.thread or '20', reads_file, args.out,
		        genome_file, motif, work, args.edge, args.filterDepthHifi, args.filterDepthOnt,
		        args.MaximumExtensionLength, args.MaximumExtensionRound, data_type, ont_reads,
		        target_ends,
		        {'tel_n': args.tel_n, 'tel_r': args.tel_r, 'tel_mm': args.tel_mm}], kparameters, resume_params

	elif args.mode == "telseeker_ctg":
		if not args.ctg:
			print("--ctg parameter is required for telseeker_ctg mode, e.g. --ctg contig.fa L")
			sys.exit()
		if not args.motif:
			print("--motif parameter is required for telseeker_ctg mode and must be uppercase A/T/C/G")
			sys.exit()
		motif = args.motif.strip()
		if re.match(r'^[ACGT]+$', motif) is None:
			print("--motif must be uppercase letters consisting of A/T/C/G only, e.g., TTTAGGG")
			sys.exit()
		for ctg_file, ctg_end in args.ctg:
			if not os.path.exists(ctg_file) or os.path.getsize(ctg_file) == 0:
				print(f"--ctg file doesn't exist or is empty: {ctg_file}")
				sys.exit()
			if ctg_end.upper() not in ["L", "R"]:
				print(f"--ctg endpoint must be L or R: {ctg_file} {ctg_end}")
				sys.exit()
		if args.resume is not None or args.resume_auto:
			print("telseeker_ctg mode does not support --resume or --resume_auto in v1")
			sys.exit()
		if args.filterDepthHifi is not None or args.filterDepthOnt is not None:
			print("telseeker_ctg mode does not support --filterDepthHifi or --filterDepthOnt in v1")
			sys.exit()
		if args.tel_n <= 0:
			print("--tel-n must be greater than 0")
			sys.exit()
		if args.tel_r <= 0 or args.tel_r > 1:
			print("--tel-r must be in the interval (0, 1]")
			sys.exit()

		work = args.work if args.work else 1
		read_inputs = {
			'hifi': args.hifi or [],
			'ont': args.ont or []
		}

		return [args.mode, args.remove, args.thread or '20', reads_file, args.out,
		        args.ctg, motif, work, args.edge, args.filterDepthHifi, args.filterDepthOnt,
		        args.MaximumExtensionLength, args.MaximumExtensionRound, data_type, ont_reads,
		        {'tel_n': args.tel_n, 'tel_r': args.tel_r, 'tel_mm': args.tel_mm}, read_inputs], kparameters, resume_params

	elif args.mode == "ctglinker":
		# Check files required for ctglinker mode
		if args.ctgseq:
			if os.path.exists(args.ctgseq) and os.path.getsize(args.ctgseq) != 0:
				seqfile = args.ctgseq
			else:
				print("contigs file doesn't exist or is empty")
				sys.exit()
		else:
			print("ctgseq parameter is required for ctglinker mode")
			sys.exit()

		return [args.mode, args.remove, args.thread or '20', reads_file, args.out,
		        seqfile, args.edge, args.filterDepthHifi, args.filterDepthOnt,
		        args.MaximumExtensionLength, args.MaximumExtensionRound, data_type, ont_reads], kparameters, resume_params

	else:
		print("You should use gapfiller or ctglinker or telseeker or telseeker_ctg!")
		sys.exit()

parameter, kparameters, resume_params = getoptions()

#parameter: mode,remove,thread,reads,out,seqleft,seqright,flag,edge,filterDepthHifi,filterDepthOnt,MaximumExtensionLength,MaximumExtensionRound,data_type,ont_reads

def generate_gapfiller_visualization_report(output_dir, flag, max_extension_length):
    """
    生成gapfiller可视化报告

    Args:
        output_dir (str): gapfiller输出目录
        flag (str): 延伸方向 ('left' 或 'right')
        max_extension_length (int): 最大延伸长度限制
    """
    try:
        print("正在生成可视化报告...")

        # 创建可视化输出目录
        visualization_output = os.path.join(output_dir, "visualization_output")
        if not os.path.exists(visualization_output):
            os.makedirs(visualization_output)

        # 构建文件路径
        from pathlib import Path
        result_dir = Path(output_dir)
        log_file = result_dir / 'process.log'
        summary_file = result_dir / 'process.summary'

        if not log_file.exists():
            print(f"警告: 找不到日志文件 {log_file}，跳过可视化报告生成")
            return

        # 解析日志文件
        parser = GapfillerLogParser(log_file, summary_file if summary_file.exists() else None, result_dir)
        data = parser.parse_log()

        # 生成可视化报告
        generator = HTMLReportGenerator(data, visualization_output, result_dir,
                                      max_extension_length=max_extension_length,
                                      extension_flag=flag)
        report_path = generator.generate_report()

        print(f"可视化报告已生成: {report_path}")
        print(f"请在浏览器中打开: {report_path}")

    except Exception as e:
        print(f"生成可视化报告时出错: {e}")
        print("继续执行程序...")
reads=parameter[3]
out=parameter[4]

# Extract data_type from parameter list (position varies by mode)
if parameter[0] == "gapfiller":
    data_type = parameter[13]  # gapfiller has 15 parameters, data_type at index 13
elif parameter[0] == "ctglinker":
    data_type = parameter[11]  # ctglinker has 13 parameters, data_type at index 11
elif parameter[0] in ["telseeker", "telseeker_ctg"]:
    data_type = parameter[13]  # telseeker modes have data_type at index 13
else:
    data_type = 'hifi'  # fallback default

#make outpit file
if out[-1]=="/":
	out=out[:-1]
	parameter[4]=out
if os.path.exists(out)!=True:
	os.makedirs(out, exist_ok=True)

if parameter[0] == "telseeker_ctg":
	try:
		from TelSeekerCtg import validate_shared_manifest_compatibility
		validate_shared_manifest_compatibility(
			out,
			parameter[16],
			parameter[6],
			parameter[15],
		)
	except ValueError as e:
		print(f"telseeker_ctg cache mismatch: {e}")
		sys.exit(1)

# ============================================================
# STEP 1: File Preprocessing
# ============================================================
# Extract ont_reads parameter from parameter list
ont_reads = None
if len(parameter) >= 14 and parameter[0] == "gapfiller":
	ont_reads = parameter[14]  # ONT reads for gapfiller (index 14)
elif len(parameter) >= 13 and parameter[0] == "ctglinker":
	ont_reads = parameter[12]  # ONT reads for ctglinker (index 12)
elif len(parameter) >= 14 and parameter[0] in ["telseeker", "telseeker_ctg"]:
	ont_reads = parameter[14]  # ONT reads for telseeker (index 14)

# Preprocess reads files: create symlinks/conversions in processed_reads/
# This is STEP 1, always happens first
hifi_reads = reads  # Rename for clarity
(hifi_working_fa, hifi_original, hifi_fmt,
 ont_working_fa, ont_original, ont_fmt) = preprocess_reads_files(
	hifi_reads, ont_reads, out, data_type
)

# After preprocessing, we have:
# - processed_reads/hifi_reads.fa (or .fq if input was FASTQ)
# - processed_reads/ont_reads.fa (or .fq if input was FASTQ)
# - FASTA versions for workflow

# Store file information
original_reads_info = {
	'original_hifi': hifi_original,
	'original_ont': ont_original,
	'hifi_format': hifi_fmt,
	'ont_format': ont_fmt,
	'working_hifi': hifi_working_fa,  # Will be updated if depth filtering applied
	'working_ont': ont_working_fa     # Will be updated if depth filtering applied
}

print(f"Preprocessing completed:")
print(f"  HiFi: {hifi_working_fa} (format: {hifi_fmt})")
print(f"  ONT: {ont_working_fa} (format: {ont_fmt})")
print(f"  Original HiFi: {hifi_original}")
print(f"  Original ONT: {ont_original}")

# ============================================================
# STEP 2: Depth Filtering (Optional)
# ============================================================
# If depth filtering is enabled, filter the preprocessed reads from processed_reads/
# Then use filtered results for subsequent indexing and splitting

# Check filterDepthHifi and filterDepthOnt parameters
# NOTE: telseeker and ctglinker do not use selectRawReads for depth filtering
# because they don't have seqLeft/seqRight. Depth filtering for these modes
# should be done differently or skipped.
if parameter[0] == "gapfiller":
	filter_hifi = parameter[9] is not None   # filterDepthHifi for gapfiller
	filter_ont = parameter[10] is not None   # filterDepthOnt for gapfiller
	param_length = 14
	use_selectRawReads = True
elif parameter[0] == "ctglinker":
	filter_hifi = parameter[7] is not None   # filterDepthHifi for ctglinker
	filter_ont = parameter[8] is not None    # filterDepthOnt for ctglinker
	param_length = 12
	use_selectRawReads = False  # ctglinker doesn't use selectRawReads
elif parameter[0] in ["telseeker", "telseeker_ctg"]:
	filter_hifi = parameter[9] is not None   # filterDepthHifi for telseeker
	filter_ont = parameter[10] is not None   # filterDepthOnt for telseeker
	param_length = 14
	use_selectRawReads = False  # telseeker doesn't use selectRawReads
else:
	filter_hifi = False
	filter_ont = False
	use_selectRawReads = False

# Variables for final working files (will point to filtered or original)
final_hifi_fa = hifi_working_fa
final_ont_fa = ont_working_fa

if filter_hifi or filter_ont:
	print("\n=== Step 2: Depth Filtering ===")
	print(f"Depth filtering enabled: HiFi={filter_hifi}, ONT={filter_ont}")
	print(f"Input: processed_reads/ files")

	# Only use selectRawReads for gapfiller mode
	if use_selectRawReads:
		# Update parameter with preprocessed files as INPUT for depth filtering
		# For ONT-only mode, parameter[3] should be ont_working_fa, not hifi_working_fa
		if data_type == 'ont':
			parameter[3] = ont_working_fa if ont_working_fa else hifi_working_fa
		else:
			parameter[3] = hifi_working_fa
		
		if ont_working_fa and data_type == 'mixed':
			if parameter[0] == "gapfiller":
				parameter[14] = ont_working_fa

		# Import selectRawReads for depth filtering
		from selectRawReads import selectRawReads

		# For depth filtering, we need a temporary seedlen value
		temp_seedlen = 10000  # Temporary value for depth filtering

		# Execute depth filtering
		selectedReads = selectRawReads(parameter[:param_length], temp_seedlen)

		# Update final working files based on what was filtered
		if filter_hifi:
			final_hifi_fa = selectedReads.readFile  # Filtered HiFi reads (FASTA)
			print(f"HiFi depth filtering completed: {final_hifi_fa}")
			original_reads_info['working_hifi'] = final_hifi_fa
		else:
			print(f"HiFi depth filtering skipped, using: {final_hifi_fa}")

		if filter_ont and data_type == 'mixed':
			if hasattr(selectedReads, 'ont_readFile') and selectedReads.ont_readFile:
				final_ont_fa = selectedReads.ont_readFile  # Filtered ONT reads (FASTA)
				print(f"ONT depth filtering completed: {final_ont_fa}")
				original_reads_info['working_ont'] = final_ont_fa
			else:
				print("Warning: ONT filtering enabled but no filtered file generated")
		elif filter_ont and data_type == 'ont':
			final_hifi_fa = selectedReads.readFile  # For ONT-only mode, readFile contains ONT data
			print(f"ONT depth filtering completed: {final_hifi_fa}")
			original_reads_info['working_hifi'] = final_hifi_fa
		else:
			if data_type == 'mixed':
				print(f"ONT depth filtering skipped, using: {final_ont_fa}")

		print(f"Depth filtering summary:")
		print(f"  Final HiFi: {final_hifi_fa}")
		if data_type == 'mixed':
			print(f"  Final ONT: {final_ont_fa}")
	else:
		# telseeker/ctglinker: depth filtering not supported yet via selectRawReads
		print(f"  Note: Depth filtering for {parameter[0]} mode is not yet implemented")
		print(f"  Using preprocessed files without filtering")
		print(f"  HiFi: {final_hifi_fa}")
		if data_type == 'mixed':
			print(f"  ONT: {final_ont_fa}")
else:
	print("\n=== Step 2: Depth Filtering ===")
	print("Depth filtering disabled, using preprocessed files directly")
	print(f"  HiFi: {final_hifi_fa}")
	if data_type == 'mixed':
		print(f"  ONT: {final_ont_fa}")

# Update parameter list with final working files
# For ONT-only mode, parameter[3] should contain ONT reads
if data_type == 'ont':
	parameter[3] = final_ont_fa if final_ont_fa else final_hifi_fa
else:
	parameter[3] = final_hifi_fa

	if final_ont_fa and data_type == 'mixed':
		if parameter[0] == "gapfiller":
			parameter[14] = final_ont_fa
		elif parameter[0] == "ctglinker":
			parameter[12] = final_ont_fa
		elif parameter[0] in ["telseeker", "telseeker_ctg"]:
			parameter[14] = final_ont_fa

# ============================================================
# STEP 3: Build Index, Calculate Stats, Split Reads
# ============================================================
# Use final working files (filtered or original preprocessed) for:
# - Building reads index (.idx)
# - Calculating statistics (.stat)
# - Splitting reads (_part/)

print ("\n=== Step 3: Build Index, Calculate Stats, Split Reads ===")
print(f"Processing files: HiFi={final_hifi_fa}, ONT={final_ont_fa}")

# For mixed mode, create separate indices for HiFi and ONT
if data_type == 'mixed':
    # HiFi index
    hifi_idx_path = out+"/hifi_reads.idx"
    hifi_stats_path = out+"/HiFi.reads.stat"

    # ONT index
    ont_idx_path = out+"/ont_reads.idx"
    ont_stats_path = out+"/ONT.reads.stat"

    # Check HiFi index
    rebuild_hifi_index = True
    if os.path.exists(hifi_idx_path) and os.path.getsize(hifi_idx_path) > 0:
        try:
            print("Detected existing HiFi index file, attempting to load...")
            hifi_readsdict = SeqIO.index_db(hifi_idx_path)
            if hifi_readsdict:
                print("HiFi index file loaded successfully, skipping HiFi index rebuild")
                rebuild_hifi_index = False
        except Exception as e:
            print(f"Failed to load HiFi index file: {e}")
            print("Will rebuild HiFi index")

    if rebuild_hifi_index:
        print("Building HiFi reads index file...")
        print(f"Creating HiFi index for working file: {final_hifi_fa}")
        hifi_readsdict = SeqIO.index_db(hifi_idx_path, final_hifi_fa, 'fasta')
        print("HiFi index construction completed")

    # Check ONT index
    rebuild_ont_index = True
    if final_ont_fa and os.path.exists(final_ont_fa):
        if os.path.exists(ont_idx_path) and os.path.getsize(ont_idx_path) > 0:
            try:
                print("Detected existing ONT index file, attempting to load...")
                ont_readsdict = SeqIO.index_db(ont_idx_path)
                if ont_readsdict:
                    print("ONT index file loaded successfully, skipping ONT index rebuild")
                    rebuild_ont_index = False
            except Exception as e:
                print(f"Failed to load ONT index file: {e}")
                print("Will rebuild ONT index")

        if rebuild_ont_index:
            print("Building ONT reads index file...")
            print(f"Creating ONT index for working file: {final_ont_fa}")
            ont_readsdict = SeqIO.index_db(ont_idx_path, final_ont_fa, 'fasta')
            print("ONT index construction completed")
    else:
        print("No ONT reads available for indexing")
        ont_readsdict = None

    # Use HiFi index as main readsdict for compatibility
    readsdict = hifi_readsdict

else:
    # Single data type mode
    # Determine file names and working file based on data_type
    if data_type == 'ont':
        idx_path = out+"/ont_reads.idx"
        stats_path = out+"/ONT.reads.stat"
        data_type_label = "ONT"
        working_file = final_ont_fa  # For ONT-only, use ont file
        print(f"ONT-only mode: using index {idx_path} and stats {stats_path}")
    else:
        idx_path = out+"/hifi_reads.idx"
        stats_path = out+"/HiFi.reads.stat"
        data_type_label = "HiFi"
        working_file = final_hifi_fa  # For HiFi-only, use hifi file
        print(f"HiFi-only mode: using index {idx_path} and stats {stats_path}")

    old_idx_path = out+"/reads.idx"  # For backward compatibility

    # Check if index file exists and is valid
    rebuild_index = True

    # First check new naming convention
    if os.path.exists(idx_path) and os.path.getsize(idx_path) > 0:
        try:
            print(f"Detected existing {data_type_label} index file, attempting to load...")
            readsdict = SeqIO.index_db(idx_path)
            if readsdict:
                print(f"{data_type_label} index file loaded successfully, skipping index rebuild")
                rebuild_index = False
        except Exception as e:
            print(f"Failed to load {data_type_label} index file: {e}")
            print(f"Will rebuild {data_type_label} index")

    # Backward compatibility: check old naming convention
    elif os.path.exists(old_idx_path) and os.path.getsize(old_idx_path) > 0:
        try:
            print("Detected existing old-format index file, attempting to migrate...")
            readsdict = SeqIO.index_db(old_idx_path)
            if readsdict:
                print(f"Old index file loaded successfully, migrating to new naming convention ({data_type_label})")
                # Copy to new location
                import shutil
                shutil.copy2(old_idx_path, idx_path)
                print("Index file migrated to new naming convention")
                rebuild_index = False
        except Exception as e:
            print(f"Failed to load old index file: {e}")
            print(f"Will rebuild {data_type_label} index")

    if rebuild_index:
        print(f"Building {data_type_label} reads index file...")
        file_format = 'fasta'
        print(f"Using file format: {file_format} (preprocessed working file)")
        print(f"Creating {data_type_label} index for working file: {working_file}")
        readsdict = SeqIO.index_db(idx_path, working_file, file_format)
        print(f"{data_type_label} index construction completed")

print ("BUILD DICT SUCCEED")
# Store readsdict separately to avoid modifying parameter list length before selectRawReads call
main_readsdict = readsdict

# Store ONT readsdict for mixed mode (will be passed to GapFiller)
main_ont_readsdict = None
if data_type == 'mixed' and 'ont_readsdict' in locals():
    main_ont_readsdict = ont_readsdict

print("Splitting reads file")
# Split reads by record count (100,000 records per file)

if data_type == 'mixed':
    # Mixed mode: separate directories for HiFi and ONT
    hifi_reads_part_dir = out+"/hifi_reads_part"
    ont_reads_part_dir = out+"/ont_reads_part"

    # Create directories
    if not os.path.exists(hifi_reads_part_dir):
        os.makedirs(hifi_reads_part_dir)
    if not os.path.exists(ont_reads_part_dir):
        os.makedirs(ont_reads_part_dir)

    # Check if HiFi directory exists and is not empty
    if os.path.exists(hifi_reads_part_dir) and os.listdir(hifi_reads_part_dir):
        hifi_split_files = glob.glob(f"{hifi_reads_part_dir}/*.fa*")
        if hifi_split_files:
            print(f"Found {len(hifi_split_files)} existing HiFi split files in {hifi_reads_part_dir}, skipping HiFi split")
        else:
            print(f"HiFi directory exists but no valid split files found, will perform splitting")
            # Perform splitting
            print("Splitting HiFi reads...")
            print(f"Splitting HiFi working file: {final_hifi_fa}")
            hifi_cmd = ["seqkit", "split", final_hifi_fa, "-O", hifi_reads_part_dir, "--force", "--by-size", "100000", "--two-pass", "-w", "0"]
            try:
                subprocess.run(hifi_cmd, check=True)
                print(f"HiFi reads splitting completed")
            except subprocess.CalledProcessError as e:
                print(f"HiFi reads splitting failed: {e}")
                sys.exit(1)
    else:
        print("Splitting HiFi reads...")
        print(f"Splitting HiFi working file: {final_hifi_fa}")
        hifi_cmd = ["seqkit", "split", final_hifi_fa, "-O", hifi_reads_part_dir, "--force", "--by-size", "100000", "--two-pass", "-w", "0"]
        try:
            subprocess.run(hifi_cmd, check=True)
            print(f"HiFi reads splitting completed")
        except subprocess.CalledProcessError as e:
            print(f"HiFi reads splitting failed: {e}")
            sys.exit(1)

    # Check if ONT directory exists and is not empty
    if final_ont_fa and os.path.exists(final_ont_fa):
        if os.path.exists(ont_reads_part_dir) and os.listdir(ont_reads_part_dir):
            ont_split_files = glob.glob(f"{ont_reads_part_dir}/*.fa*")
            if ont_split_files:
                print(f"Found {len(ont_split_files)} existing ONT split files in {ont_reads_part_dir}, skipping ONT split")
            else:
                print(f"ONT directory exists but no valid split files found, will perform splitting")
                # Perform splitting
                print("Splitting ONT reads...")
                print(f"Splitting ONT working file: {final_ont_fa}")
                ont_cmd = ["seqkit", "split", final_ont_fa, "-O", ont_reads_part_dir, "--force", "--by-size", "100000", "--two-pass", "-w", "0"]
                try:
                    subprocess.run(ont_cmd, check=True)
                    print(f"ONT reads splitting completed")
                except subprocess.CalledProcessError as e:
                    print(f"ONT splitting failed: {e}")
                    # Don't exit, ONT splitting failure shouldn't stop the process
        else:
            print("Splitting ONT reads...")
            print(f"Splitting ONT working file: {final_ont_fa}")
            ont_cmd = ["seqkit", "split", final_ont_fa, "-O", ont_reads_part_dir, "--force", "--by-size", "100000", "--two-pass", "-w", "0"]
            try:
                subprocess.run(ont_cmd, check=True)
                print(f"ONT reads splitting completed")
            except subprocess.CalledProcessError as e:
                print(f"ONT splitting failed: {e}")
                # Don't exit, ONT splitting failure shouldn't stop the process
    else:
        print("No ONT reads available for splitting")

    # Set reads_part_dir to HiFi directory for compatibility with existing code
    reads_part_dir = hifi_reads_part_dir

else:
    # Single data type mode
    # Determine directory name based on data_type
    if data_type == 'ont':
        reads_part_dir = out+"/ont_reads_part"  # ONT-only uses ont_reads_part
        data_type_label = "ONT"
        print(f"ONT-only mode: using directory {reads_part_dir}")
    else:
        reads_part_dir = out+"/hifi_reads_part"  # HiFi-only uses hifi_reads_part
        data_type_label = "HiFi"
        print(f"HiFi-only mode: using directory {reads_part_dir}")

    old_reads_part_dir = out+"/reads_part"  # For backward compatibility

    # Check for existing split files in new location
    if os.path.exists(reads_part_dir):
        split_files = glob.glob(f"{reads_part_dir}/*.fa*")
        if split_files:
            print(f"Found {len(split_files)} existing {data_type_label} split files in {reads_part_dir}, skipping split step")
            need_splitting = False
        else:
            need_splitting = True
    # Backward compatibility: check old location
    elif os.path.exists(old_reads_part_dir):
        old_split_files = glob.glob(f"{old_reads_part_dir}/*.fa*")
        if old_split_files:
            print(f"Found {len(old_split_files)} existing split files in old location, migrating to new naming...")
            # Create new directory and move files
            os.makedirs(reads_part_dir, exist_ok=True)
            import shutil
            for old_file in old_split_files:
                new_file = os.path.join(reads_part_dir, os.path.basename(old_file))
                shutil.copy2(old_file, new_file)
            print("Migration completed, skipping split step")
            need_splitting = False
        else:
            need_splitting = True
    else:
        # Neither directory exists
        os.makedirs(reads_part_dir)
        need_splitting = True

    if need_splitting:
        print(f"No {data_type_label} split files found, performing {data_type_label} reads splitting...")
        print(f"Splitting {data_type_label} working file: {working_file}")
        cmd = ["seqkit", "split", working_file, "-O", reads_part_dir, "--force", "--by-size", "100000", "--two-pass", "-w", "0"]
        try:
            subprocess.run(cmd, check=True)
            print(f"{data_type_label} reads splitting completed")
        except subprocess.CalledProcessError as e:
            print(f"{data_type_label} reads splitting failed: {e}")
            sys.exit(1)

# Calculate read length statistics
# Initialize seed lengths
hifiseedlen = None
ontseedlen = None

if data_type == 'mixed':
    # For mixed mode, read both HiFi and ONT statistics
    hifi_pwd = hifi_stats_path
    ont_pwd = ont_stats_path

    # Read HiFi statistics
    if os.path.exists(hifi_pwd) and os.path.getsize(hifi_pwd) > 0:
        try:
            print(f"Reading HiFi statistics file: {hifi_pwd}")
            with open(hifi_pwd, 'r') as file1:
                for i in file1:
                    i1 = i.rstrip().split("\t")
                    if i1[0] == "MaxLength":
                        lenmax = int(i1[1])
                        print(f"  HiFi MaxLength: {lenmax}")
                    elif i1[0] == "SeedLength":
                        hifiseedlen = int(float(i1[1]))
                        print(f"  HiFi SeedLength: {hifiseedlen}")
                    elif i1[0] == "Number":
                        reads_count = int(i1[1])
                        print(f"  HiFi Number: {reads_count}")
                    elif i1[0] == "TolalLenth" or i1[0] == "TotalLength":
                        total_length = int(i1[1])
                        print(f"  HiFi TotalLength: {total_length}")
        except Exception as e:
            print(f"Error reading HiFi statistics: {e}")

    # Read ONT statistics
    if os.path.exists(ont_pwd) and os.path.getsize(ont_pwd) > 0:
        try:
            print(f"Reading ONT statistics file: {ont_pwd}")
            with open(ont_pwd, 'r') as file1:
                for i in file1:
                    i1 = i.rstrip().split("\t")
                    if i1[0] == "SeedLength":
                        ontseedlen = int(float(i1[1]))
                        print(f"  ONT SeedLength: {ontseedlen}")
        except Exception as e:
            print(f"Error reading ONT statistics: {e}")

    # Set primary seedlen for compatibility (use HiFi)
    seedlen = hifiseedlen
    pwd1 = hifi_pwd
else:
    # Single data type mode
    pwd1 = stats_path

if data_type != 'mixed' and os.path.exists(pwd1) and os.path.getsize(pwd1) > 0:
    # Read existing statistics file for single mode
    try:
        print(f"Detected existing statistics file, attempting to load: {pwd1}")
        file1 = open(pwd1, 'r')
        mean_length = None
        reads_count = None
        total_length = None
        lenmax = None
        seedlen = None

        print("Reading statistics file content:")
        for i in file1:
            i1 = i.rstrip().split("\t")
            print(f"  Line: {i.rstrip()} -> Split: {i1}")
            if i1[0] == "MaxLength":
                lenmax = int(i1[1])
                print(f"  Found MaxLength: {lenmax}")
            elif i1[0] == "SeedLength":
                seedlen = int(float(i1[1]))
                print(f"  Found SeedLength: {seedlen}")
                # Set appropriate seed length for single mode
                if data_type == 'hifi':
                    hifiseedlen = seedlen
                elif data_type == 'ont':
                    ontseedlen = seedlen
            elif i1[0] == "Number":
                reads_count = int(i1[1])
                print(f"  Found Number: {reads_count}")
            elif i1[0] == "TolalLenth" or i1[0] == "TotalLength":  # Compatible with both spellings
                total_length = int(i1[1])
                print(f"  Found TotalLength: {total_length}")
        file1.close()

        # Verify if all necessary information was obtained
        print(f"Statistics parsing results: lenmax={lenmax}, seedlen={seedlen}, reads_count={reads_count}, total_length={total_length}")
        if lenmax is not None and seedlen is not None and reads_count is not None and total_length is not None:
            mean_length = total_length / reads_count
            print(f"Statistics file loaded successfully: average read length {mean_length:.2f} bp, maximum read length {lenmax} bp, seed length {seedlen} bp")
        else:
            print("Statistics file format incorrect or missing key information, will recalculate")
            print(f"Missing values: lenmax={lenmax is None}, seedlen={seedlen is None}, reads_count={reads_count is None}, total_length={total_length is None}")
            mean_length = None  # Trigger recalculation
    except Exception as e:
        print(f"Failed to read statistics file: {e}")
        mean_length = None  # Trigger recalculation
else:
    mean_length = None  # Trigger recalculation

# If no valid statistics information, recalculate
if mean_length is None:
    if data_type == 'mixed':
        # Check if HiFi statistics file already exists and is valid
        if os.path.exists(hifi_stats_path) and os.path.getsize(hifi_stats_path) > 0:
            print(f"HiFi statistics file already exists: {hifi_stats_path}, skipping HiFi statistics generation")
            # Read existing HiFi statistics to get necessary values
            try:
                with open(hifi_stats_path, 'r') as f:
                    for line in f:
                        line_parts = line.rstrip().split('\t')
                        if line_parts[0] == "MaxLength":
                            lenmax = int(line_parts[1])
                        elif line_parts[0] == "SeedLength":
                            seedlen = int(float(line_parts[1]))
                        elif line_parts[0] == "Number":
                            reads_count = int(line_parts[1])
                        elif line_parts[0] == "TolalLenth" or line_parts[0] == "TotalLength":
                            total_length = int(line_parts[1])
                if reads_count and total_length:
                    mean_length = total_length / reads_count
                    print(f"Loaded HiFi statistics: average read length {mean_length:.2f} bp, maximum read length {lenmax} bp, seed length {seedlen} bp")
            except Exception as e:
                print(f"Error reading existing HiFi statistics file: {e}")
                print("Will regenerate HiFi statistics...")
                # Fall through to regenerate statistics
        else:
            # Generate HiFi statistics using seqkit (remove Python fallback)
            print("Creating HiFi read length statistics file using seqkit...")
            n, total_length, lenmax, mean_length, seedlen = generate_stats_with_seqkit(final_hifi_fa, hifi_stats_path)
            print(f"HiFi statistics complete using seqkit: average read length {mean_length:.2f} bp, maximum read length {lenmax} bp")

        # Check if ONT statistics file already exists and is valid
        if ont_readsdict is not None:
            if os.path.exists(ont_stats_path) and os.path.getsize(ont_stats_path) > 0:
                print(f"ONT statistics file already exists: {ont_stats_path}, skipping ONT statistics generation")
            else:
                print("Creating ONT read length statistics file using seqkit...")
                ont_n, ont_total_length, ont_lenmax, ont_mean_length, ont_seedlen = generate_stats_with_seqkit(final_ont_fa, ont_stats_path)
                print(f"ONT statistics complete using seqkit: average read length {ont_mean_length:.2f} bp, maximum read length {ont_lenmax} bp")
        else:
            print("No ONT reads available for statistics generation")

    else:
        # Single data type mode using seqkit (remove Python fallback)
        print("Creating read length statistics file using seqkit...")
        n, total_length, lenmax, mean_length, seedlen = generate_stats_with_seqkit(working_file, pwd1)
        print(f"Statistics complete using seqkit: average read length {mean_length:.2f} bp, maximum read length {lenmax} bp")

# kmer_length parameter has been removed, using optimized k-mer extraction strategy
print(f"Average read length: {mean_length:.2f} bp")
print(f"Using optimized k-mer extraction strategy with multiplier=3, range_multiplier=10")

print(f"Final values before parameter processing:")
print(f"  lenmax: {lenmax}")
print(f"  seedlen: {seedlen}")
print(f"  seedlen type: {type(seedlen)}")

if seedlen is None:
    print("ERROR: seedlen is None! This will cause issues in GapFiller.")
    print("Checking if HiFi.reads.stat file exists and has correct format...")
    stats_file = out + "/HiFi.reads.stat"
    if os.path.exists(stats_file):
        print(f"HiFi.reads.stat file exists: {stats_file}")
        with open(stats_file, 'r') as f:
            content = f.read()
            print(f"File content:\n{content}")
    else:
        print(f"HiFi.reads.stat file does not exist: {stats_file}")
else:
    print(f"seedlen is properly set: {seedlen}")
# Append readsDict to parameter list
# Note: Depth filtering was already performed earlier if enabled
# The main_readsdict was built using the filtered reads (if filtering was enabled)
if parameter[0] in ["telseeker", "telseeker_ctg"]:
	# For telseeker, pass HiFi index path string instead of object
	parameter.append(out+"/hifi_reads.idx")
else:
	# For other modes, pass the readsdict object
	parameter.append(main_readsdict)

# Ensure maximum read length and seed lengths are added to parameter list
parameter.append(lenmax)  # Add maxReadsLen

# In mixed mode, use respective seedlen for each data type
if data_type == 'mixed':
	# Use respective seed lengths for HiFi and ONT
	hifi_seed = hifiseedlen if hifiseedlen is not None else seedlen
	ont_seed = ontseedlen if (ontseedlen is not None) else seedlen
	
	print(f"\n[Mixed Mode] Separate seed length strategy:")
	print(f"  HiFi seed length: {hifi_seed} bp (for hifi.inputCutSequence.fasta)")
	print(f"  ONT seed length:  {ont_seed} bp (for ont.inputCutSequence.fasta)")
	print(f"  Rationale: Each data type uses its own optimal seed length\n")
	
	parameter.append(hifi_seed)  # HiFi seedLen = HiFi's own seedlen
	parameter.append(ont_seed)   # ONT seedLen = ONT's own seedlen
else:
	# Single data type mode: use respective seedlen
	parameter.append(hifiseedlen if hifiseedlen is not None else seedlen) # Add HiFi seedLen
	# Only set ONT seedLen when ONT reads are available; otherwise leave as None
	if data_type == 'ont':
		if 'ontseedlen' in locals() and ontseedlen is not None:
			parameter.append(ontseedlen)
		else:
			parameter.append(seedlen)  # Fallback to main seedlen
	else:
		parameter.append(None)   # HiFi-only mode, no ONT seedLen

# Add original reads info for hifiasm FASTQ conversion
# Note: original_reads_info was already created during preprocessing
# Just append it to parameter list
parameter.append(original_reads_info)

# Add ONT readsDict for mixed mode
# For telseeker, pass ONT index path string (if available) instead of object
if parameter[0] in ["telseeker", "telseeker_ctg"]:
	# Explicitly check for mixed mode and use the ont_reads.idx path
	if data_type == 'mixed' and main_ont_readsdict is not None:
		ont_index_path = out + "/ont_reads.idx"
		if os.path.exists(ont_index_path):
			parameter.append(ont_index_path)
			print(f"Added ONT readsDict index path to parameters: {ont_index_path}")
		else:
			print(f"Warning: ONT index file not found: {ont_index_path}")
			parameter.append(None)
	else:
		parameter.append(None)
else:
	parameter.append(main_ont_readsdict)

print("Calculating average and maximum read lengths...")
print(f"Average read length: {mean_length:.2f}, maximum read length: {lenmax}")

# Display seed length information based on mode
if data_type == 'mixed':
	print(f"Final seed lengths (unified for mixed mode):")
	print(f"  HiFi seed length: {parameter[-4]} bp (set to ONT seedlen)")
	print(f"  ONT seed length:  {parameter[-3]} bp (original)")
else:
	print(f"HiFi seed length: {hifiseedlen if hifiseedlen is not None else seedlen}")
	print(f"ONT seed length: {ontseedlen if ontseedlen is not None else seedlen}")

print(f"Parameter list length: {len(parameter)}")  # Print parameter length for debugging
print(parameter)

# Unpack resume parameters
resume_round, resume_auto = resume_params

# Set up resume functionality
if resume_auto:
    # Automatically search for checkpoint file
    checkpoint_file = out+"/checkpoint.info"
    if os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file, 'r') as f:
                checkpoint_data = f.read().strip()
                if checkpoint_data and checkpoint_data.startswith("round:"):
                    resume_round = int(checkpoint_data.split("round:")[1])
                    print(f"Auto resume mode: Found checkpoint information, will continue from round{resume_round}")
        except Exception as e:
            print(f"Failed to read checkpoint information: {e}")
            resume_round = None

# Execute main functionality
if parameter[0] == "gapfiller":
    # original_reads_info已经在上面添加过了，不需要重复添加

    if resume_round is not None:
        # If specified which round to continue from, set resume_round attribute
        print(f"Preparing to continue from round{resume_round}...")
        gapfiller = GapFiller(parameter, kparameters)
        gapfiller.resume_round = resume_round
    else:
        # Normal startup
        GapFiller(parameter, kparameters)

    # 生成可视化报告
    output_dir = parameter[4]  # parameter[4] is the output directory
    flag = parameter[7]        # parameter[7] is the flag
    max_extension_length = parameter[11]  # parameter[11] is MaximumExtensionLength
    max_extension_round = parameter[12]   # parameter[12] is MaximumExtensionRound
    generate_gapfiller_visualization_report(output_dir, flag, max_extension_length)
elif parameter[0] == "ctglinker":
    if resume_round is not None:
        print(f"Warning: ctglinker mode does not support resume functionality yet, will ignore --resume parameter")

    # The parameter list should already contain readsDict, maxReadsLen, hifiSeedLen, ontSeedLen, original_reads_info, ont_readsDict
    # from the processing above (lines 1107-1163)
    # Expected structure: [mode, remove, thread, reads, out, genomeSeq, edge, filterDepthHifi, filterDepthOnt,
    #                      MaximumExtensionLength, MaximumExtensionRound, data_type, ont_reads, readsDict,
    #                      maxReadsLen, hifiSeedLen, ontSeedLen, original_reads_info, ont_readsDict]
    print(f"CtgLinker parameter list length: {len(parameter)}")
    print(f"CtgLinker parameters: {[str(p)[:50] + '...' if isinstance(p, str) and len(str(p)) > 50 else p for p in parameter]}")

    # Normal startup for ctglinker
    CtgLinker(parameter, kparameters)
    
    # Run CtgLinkerCheck to analyze and validate results
    print("\n=== Running CtgLinker Result Check ===")
    try:
        import CtgLinkerCheck
        from CtgLinkerCheck import CtgLinkerCheck
        
        output_dir = parameter[4]  # parameter[4] is the output directory
        checker = CtgLinkerCheck(output_dir)
        check_result = checker.run()
        
        print(f"CtgLinker check completed: {len(check_result['valid_scaffolds'])} valid scaffolds")
        
    except Exception as e:
        print(f"Error running CtgLinker check: {e}")
        print("Continuing with visualization...")
        check_result = None
    
    # Generate visualization report
    print("\n=== Generating CtgLinker Visualization Report ===")
    try:
        import CtgLinkerVisualizer
        from CtgLinkerVisualizer import CtgLinkerVisualizer
        
        visualizer = CtgLinkerVisualizer(output_dir)
        report_path = visualizer.generate_report()
        
        print(f"CtgLinker visualization report generated: {report_path}")
        print(f"Please open in browser: {report_path}")
        
    except Exception as e:
        print(f"Error generating CtgLinker visualization report: {e}")
        print("Continuing execution...")
elif parameter[0] == "telseeker":
    # The parameter list should already contain readsDict, maxReadsLen, hifiSeedLen, ontSeedLen
    # from the processing above
    # Expected structure: [mode, remove, thread, reads, out, genome_fasta, motif, work, edge, filterDepthHifi, filterDepthOnt, MaximumExtensionLength, MaximumExtensionRound, data_type, ont_reads, target_ends, tel_read_params, readsDict, maxReadsLen, hifiSeedLen, ontSeedLen, original_reads_info, ont_readsdict]
    print(f"TelSeeker parameter list length: {len(parameter)}")
    print(f"TelSeeker parameters: {[str(p)[:50] + '...' if isinstance(p, str) and len(str(p)) > 50 else p for p in parameter]}")

    # Check if using genome mode (multiple chromosomes) or single chromosome mode
    genome_file = parameter[5]  # This is the genome/chr file
    work_param = parameter[7] if len(parameter) > 7 else 1  # Work parameter for parallel processing

    # Check if genome file contains multiple chromosomes
    from Bio import SeqIO
    chr_count = 0
    try:
        for record in SeqIO.parse(genome_file, "fasta"):
            chr_count += 1
            if chr_count > 1:
                break
    except:
        chr_count = 1

    # Use unified TelSeeker for genome-wide processing
    # TelSeeker now handles both single and multiple chromosomes automatically
    print(f"[DEGAP] Using TelSeeker for genome-wide processing ({chr_count} chromosome(s), {work_param} parallel workers)")
    from TelSeeker import TelSeeker
    telseeker = TelSeeker(parameter, kparameters)
    telseeker.run()
elif parameter[0] == "telseeker_ctg":
    print(f"TelSeekerCtg parameter list length: {len(parameter)}")
    print(f"TelSeekerCtg parameters: {[str(p)[:50] + '...' if isinstance(p, str) and len(str(p)) > 50 else p for p in parameter]}")

    from TelSeekerCtg import TelSeekerCtg
    telseeker_ctg = TelSeekerCtg(parameter, kparameters)
    telseeker_ctg.run()
# 清理预处理文件（当 --remove=1 或 --remove=2 时）
if parameter[1] in [1, 2] and parameter[0] != "telseeker_ctg":
    import shutil
    out_dir = parameter[4]
    cleanup_dirs = [
        os.path.join(out_dir, 'processed_reads'),
        os.path.join(out_dir, 'hifi_reads_part'),
        os.path.join(out_dir, 'ont_reads_part'),
    ]
    for d in cleanup_dirs:
        if os.path.exists(d) or os.path.islink(d):
            # 跳过软链接，不删除
            if os.path.islink(d):
                continue
            try:
                if os.path.isdir(d):
                    shutil.rmtree(d)
                else:
                    os.remove(d)
                print(f"Cleaned up: {d}")
            except Exception as e:
                print(f"Warning: Failed to clean up {d}: {e}")

print('welldone')
