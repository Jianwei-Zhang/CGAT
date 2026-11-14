![DEGAP](./DEGAP.png)

## Dynamic Elongation of a Genome Assembly Path

**DEGAP degaps gaps!**

**DEGAP2.0** is an enhanced gap-filling and sequence-extension toolkit that resolves assembly gaps and extends chromosome ends using high-fidelity (HiFi) and/or Oxford Nanopore (ONT) long reads.

## System Requirements

**DEGAP2.0** runs on Linux with Python 3.10. Required Python packages and external tools are declared in `environment.yml`, with selected versions pinned:

**Python Packages:**
- Python (3.10)
- Biopython
- Pysam
- NumPy
- Matplotlib
- SciPy

**External Tools:**
- Minimap2 (2.28)
- Hifiasm (0.25.0)
- SAMtools (1.22.1)
- Seqkit (2.8.0)
- MUMmer4
- GNU Parallel
- Ripgrep (15.1.0)

### Recommended environment setup (Micromamba)

We recommend using [Micromamba](https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html) to create an isolated environment with all required Python packages and external tools. Micromamba is a lightweight, standalone package manager that is faster than conda.

1. Install Micromamba following the [official installation guide](https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html):

   ```bash
   "${SHELL}" <(curl -L micro.mamba.pm/install.sh)
   ```

   **Tip for Micromamba users:** To use `mamba` command instead of `micromamba`, add this line to the end of your `~/.bashrc`:
   ```bash
   alias mamba='micromamba'
   ```
   Then run `source ~/.bashrc` to apply.

2. Clone this repository and change into its directory.
3. Create the environment using Micromamba with the provided `environment.yml` file:

   ```bash
   micromamba env create -f environment.yml
   ```

4. Activate the environment:

   ```bash
   micromamba activate degap_env
   ```

5. If `environment.yml` is updated in the future, you can update the environment with:

   ```bash
   micromamba env update -f environment.yml --prune
   ```

The `environment.yml` file declares Python, core Python packages (Biopython, Pysam, NumPy, Matplotlib, SciPy), and required external tools (Minimap2, Hifiasm, SAMtools, Seqkit, MUMmer4, GNU Parallel, Ripgrep). It pins Python and selected tool versions; unpinned dependencies are resolved when the **DEGAP2.0** environment is created or updated.

## Tutorial

**DEGAP2.0** provides 5 execution modes to fill gaps, link contigs, and extend telomeres:

| Mode | Command Entry | Use Case | Key Inputs |
| --- | --- | --- | --- |
| **GapFiller** | `bin/DEGAP.py --mode gapfiller` | Fill a specific gap between known left and right flanking sequences | `--seqleft`, `--seqright`, `--hifi`/`--ont`, `--flag left\|right` |
| **CtgLinker** | `bin/DEGAP.py --mode ctglinker` | Link contigs and close gaps by elongating contig edges | `--ctgseq`, `--hifi`/`--ont` |
| **TelSeeker** | `bin/DEGAP.py --mode telseeker` | Extend specified chromosome ends (`Chr.L` / `Chr.R`) toward telomeres | `--genome`, `--motif`, `-e`, `--hifi`/`--ont` |
| **TelSeeker Ctg** | `bin/DEGAP.py --mode telseeker_ctg` | Extend individual single-record contig endpoints (`L` or `R`) with shared read caching | `--ctg <fasta> <L\|R>`, `--motif`, `--hifi`/`--ont` |
| **AutoGapfiller** | `bin/AutoGapfiller.py` | Automatically detect all genome gaps and run parallel gap-filling jobs | `--genome`, `--hifi`/`--ont`, `--work` (optional `--setup_only`) |

### Input Data Requirements

**Supported Read Files:**
- `--hifi`: HiFi reads file(s), supports one or more files (formats: `.fa`, `.fq`, `.fa.gz`, `.fq.gz`, `.fasta`, `.fastq`)
- `--ont`: ONT reads file(s), supports one or more files (formats: `.fa`, `.fq`, `.fa.gz`, `.fq.gz`, `.fasta`, `.fastq`)

**Note:** At least one of `--hifi` or `--ont` must be provided.
You can provide multiple files directly, for example:
`--hifi HIFI1.fq.gz HIFI2.fq.gz HIFI3.fq.gz`

### K-mer Filtering Option

The `--kmer_filter` parameter is a switch to enable k-mer based read filtering:

- **When to enable** (add `--kmer_filter`):
  - Processing large-scale datasets (reads.fa >20GB)
  - Significantly reduces memory usage and processing time
- **When to disable** (omit `--kmer_filter`):
  - For highest accuracy requirements
  - Small to medium datasets (reads.fa <20GB)
  - When computational resources are sufficient

**Note:** K-mer filtering provides a good balance between speed and accuracy for most applications.

For all modes, we recommend adding `--MaximumExtensionRound 25`. In our tests,
successful extension jobs usually finished within 25 rounds, so this parameter
helps avoid long-running jobs that are unlikely to converge.

### GapFiller Mode
Designed for filling a specific gap when the exact left and right sequences are known.

```bash
python bin/DEGAP.py --mode gapfiller \
    --seqleft ./path/gapLeftSequence.fasta \
    --seqright ./path/gapRightSequence.fasta \
    --hifi ./path/HiFiReads.fa \
    --ont ./path/ONTReads.fa \
    --out ./path/Output \
    --flag left \
    --MaximumExtensionRound 25 \
    --kmer_filter \
    -t 20
```

### CtgLinker Mode
Designed for assemblies with gaps. Links contigs and fills gaps by elongating edges.

```bash
python bin/DEGAP.py --mode ctglinker \
    --ctgseq ./path/contigs.fasta \
    --hifi ./path/HiFiReads.fa \
    --ont ./path/ONTReads.fa \
    --out ./path/Output \
    --MaximumExtensionRound 25 \
    --kmer_filter \
    -t 20
```

### TelSeeker Mode
Designed for telomere extension and chromosome-level assembly.

```bash
python bin/DEGAP.py --mode telseeker \
    --genome ./path/genome.fasta \
    --motif TTAGGG \
    -e Chr01.L Chr01.R \
    --hifi ./path/HiFiReads.fa \
    --ont ./path/ONTReads.fa \
    --out ./path/Output \
    --work 4 \
    --tel-n 100 \
    --tel-r 0.6 \
    --tel-mm 0 \
    --MaximumExtensionRound 25 \
    --kmer_filter \
    -t 20
```

`-e/--target_ends` is required and supports two input forms:
direct chromosome-end values, for example `-e Chr01.L Chr01.R`, or one text file
containing one target end per line, for example `-e target_ends.txt`. Telomere
quality checking is run separately with `bin/TelSeekerCheck.py` when needed.

To discover target ends first:

```bash
python bin/TelSeekerCheck.py \
    --genome ./path/genome.fasta \
    --motif TTAGGG \
    --out ./path/telomere_check
```

Review the generated plots and end sequences, then create `target_ends.txt`
manually. The file must contain one target end per line, using
`<chromosome_id>.L` for the left end and `<chromosome_id>.R` for the right end:

```text
Chr01.L
Chr03.R
```

Blank lines and comment lines starting with `#` are allowed:

```text
# target chromosome ends selected from TelSeekerCheck plots
Chr01.L
Chr03.R
```

Then run TelSeeker with that reviewed target list:

```bash
python bin/DEGAP.py --mode telseeker \
    --genome ./path/genome.fasta \
    --motif TTAGGG \
    -e ./path/target_ends.txt \
    --hifi ./path/HiFiReads.fa \
    --out ./path/Output \
    --MaximumExtensionRound 25
```

Review the `TelSeekerCheck.py` output before choosing TelSeeker targets. The check
step generates whole-genome motif distribution plots using a 1 kb plotting
window (`all_chromosomes_combined.png` plus `<chromosome>_telomere_motif.png` per chromosome) and writes `genome.telomere.check.left.2kb.fa` and
`genome.telomere.check.right.2kb.fa` for terminal sequence inspection. If you
already know the target chromosome ends, skip `TelSeekerCheck.py` and pass them
directly with `-e Chr01.L Chr01.R` or `-e target_ends.txt`.

Telomere parameters also have concise aliases: `-m/--motif`, `-tn/--tel-n`,
`-tr/--tel-r`, and `-tmm/--tel-mm`.

Telomeric read discovery checks both physical read ends. At each end, TelSeeker
scans `--tel-n * len(--motif)` bases with motif rotations and reverse-complement
rotations. A read end passes when `hits / --tel-n >= --tel-r`; `--tel-mm` allows
0 or 1 mismatch per motif-length unit. With the default motif `TTAGGG`, the
default `--tel-n 100` checks 600 bp at each read end and `--tel-r 0.6` requires
at least 60 motif-unit hits. If Step 1 finds too few telo reads, lower `--tel-r`,
allow `--tel-mm 1`, or reduce `--tel-n`:

```bash
python bin/DEGAP.py --mode telseeker \
    --genome ./path/genome.fasta \
    --motif TTAGGG \
    -e Chr01.L Chr01.R \
    --hifi ./path/HiFiReads.fa \
    --out ./path/Output \
    --tel-r 0.5 \
    --tel-mm 1 \
    --MaximumExtensionRound 25
```

### TelSeeker Ctg Mode
Designed for extending selected contig endpoints without preparing a split genome
FASTA for each task. Each `--ctg` FASTA must contain exactly one record, and the
endpoint is `L` for left-end extension or `R` for right-end extension.

```bash
python bin/DEGAP.py --mode telseeker_ctg \
    --ctg ./path/chr1.L.ctg.fa L \
    --ctg ./path/chr2.R.ctg.fa R \
    --motif TTAGGG \
    --hifi ./path/HiFiReads.fa \
    --ont ./path/ONTReads.fa \
    --out ./path/TelSeekerCtgOut \
    --work 4 \
    --tel-n 100 \
    --tel-r 0.6 \
    --tel-mm 0 \
    --MaximumExtensionRound 25 \
    --MaximumExtensionLength 1000000 \
    -t 20
```

All contig endpoints in one run share the same preprocessed reads, split reads,
and `part1.telo.reads/` cache. Reusing the same `--out` with additional `--ctg`
tasks is allowed only when `--hifi`, `--ont`, `--motif`, `--tel-n`, `--tel-r`,
and `--tel-mm` match the existing cache manifest. If they differ, DEGAP reports
the mismatch and stops.

Per-endpoint outputs are written under
`telseeker_ctg.jobs/<contig_id>.<L|R>/result/`. The aggregate status file is
`result/status.tsv`. If no telomeric reads are found, or none are available for
the requested end direction, the endpoint is marked failed with
`no_tel_reads` or `no_tel_reads_for_target_end`.

Example target file:

```text
Chr01.L
Chr01.R
```

### AutoGapfiller Mode
Automated pipeline for whole-genome gap filling. Automatically detects gaps and fills them in parallel.

```bash
python bin/AutoGapfiller.py \
    --genome ./path/genome.fasta \
    --hifi ./path/HiFiReads.fa \
    --ont ./path/ONTReads.fa \
    --out ./path/Output \
    --work 4 \
    --MaximumExtensionRound 25 \
    --kmer_filter \
    -t 20
```

**Note:** You can add the `--setup_only` parameter to only create the gap-filling job directories without executing them. This is useful for inspecting the tasks before running or for manual execution control.

## Key Features in DEGAP2.0

- **Multi-data support**: HiFi-only, ONT-only, or Mixed (HiFi+ONT) modes
- **K-mer filtering**: `--kmer_filter` for faster processing with large datasets
- **Enhanced performance**: Optimized parallel processing and memory management

## Quick Start

For detailed usage, parameter descriptions, and advanced features, please refer to [Users' Guide](HOWTO.md).

## How to Cite?

Huang, Y. et al. DEGAP: Dynamic Elongation of a Genome Assembly Path. Briefings in Bioinformatics, Volume 25, Issue 3, May 2024, bbae194. [DOI: 10.1093/bib/bbae194](https://doi.org/10.1093/bib/bbae194)

## Contact

For comments and suggestions, please contact <jzhang@mail.hzau.edu.cn>.
