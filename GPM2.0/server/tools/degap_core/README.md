![DEGAP](./DEGAP.png)

# DEGAP 2.0 — Dynamic Elongation of a Genome Assembly Path

**English** | [中文](README_zh.md)

**DEGAP 2.0** resolves genome assembly gaps, links contigs, and extends chromosome ends using HiFi and/or Oxford Nanopore (ONT) long reads.

## What's New in DEGAP 2.0

Relative to DEGAP 1.0 ([historical v1 guide](v1/README.md)), DEGAP 2.0 adds four core upgrades:

1. **Faster candidate-read selection** — DEGAP 1.0 already offered post-alignment mapped-depth filtering; DEGAP 2.0 adds optional `--kmer_filter` (off by default) to narrow candidate reads *before* alignment, which can reduce mapping work on large datasets.
2. **Bidirectional gap extension** — Replaces single-sided gap filling with sequential alternating left/right extension: each new version is checked against all opposite historical versions (including initial flanks), and a normally stopped side stays frozen as a target while the other continues.
3. **TelSeeker chromosome-end extension** — Adds single-ended extension of targeted chromosome ends toward telomeric reads (`telseeker`) plus a contig-end variant (`telseeker_ctg`), supplementing internal-gap filling and contig linking.
4. **Clearer job reports** — Produces self-contained offline interactive HTML reports (not real-time dashboards) explaining outcomes, extension history, selected connections, evidence, and stop reasons; open the generated `.html` file in a local browser (see the [report guide](HOWTO.md#reading-the-html-reports); `TelSeeker Ctg` uses `result/status.tsv` instead of HTML).

## Installation

DEGAP 2.0 targets Linux. The supplied environment pins Python 3.10; packages and external tools are declared in [environment.yml](environment.yml):

- **Python packages**: Python 3.10, Biopython, Pysam, NumPy, Matplotlib, SciPy
- **External tools**: Minimap2 (2.28), Hifiasm (0.25.0), SAMtools (1.22.1), Seqkit (2.8.0), MUMmer4, GNU Parallel, Ripgrep (15.1.0)

Recommended setup with [Micromamba](https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html):

```bash
micromamba env create -f environment.yml
micromamba activate degap_env
```

To update an existing environment after `environment.yml` changes:

```bash
micromamba env update -f environment.yml --prune
```

For manual setup without Micromamba, see [HOWTO.md — Installation](HOWTO.md#installation).

## Choosing a Mode

| Mode | Command Entry | Purpose | Key Inputs |
| --- | --- | --- | --- |
| **GapFiller** | `python bin/DEGAP.py --mode gapfiller` | Fill one gap between known left and right flanks using bidirectional extension families | `--seqleft`, `--seqright`, `--hifi`/`--ont`, `-o/--out` |
| **CtgLinker** | `python bin/DEGAP.py --mode ctglinker` | Link contigs and close gaps from contig edges using primary plus forward/reverse candidate families | `--ctgseq`, `--hifi`/`--ont`, `-o/--out` |
| **TelSeeker** | `python bin/DEGAP.py --mode telseeker` | Single-ended extension of specified chromosome ends (`<chr>.L` / `<chr>.R`) toward telomeric reads | `--genome`, `-m/--motif`, `-e/--target_ends`, `--hifi`/`--ont`, `-o/--out` |
| **TelSeeker Ctg** | `python bin/DEGAP.py --mode telseeker_ctg` | Single-ended extension of one or more single-record contig endpoints (`L` or `R`) with shared read/telomere caching | `--ctg <fasta> <L\|R>`, `-m/--motif`, `--hifi`/`--ont`, `-o/--out` |
| **AutoGapfiller** | `python bin/AutoGapfiller.py` | Detect genome N gaps and run one bidirectional gap-filling job per gap | `--genome`, `--hifi`/`--ont`, `-o/--output` (optional `--setup_only`) |

Optional chromosome-end review plots and 2 kb end FASTAs can be prepared before running TelSeeker with `python bin/TelSeekerCheck.py --genome <genome.fa> --motif <MOTIF> --out <dir>`.

## Quick Start

Fill one gap between left and right flanking sequences (`gapfiller`):

```bash
python bin/DEGAP.py --mode gapfiller \
    --seqleft ./left_flank.fa \
    --seqright ./right_flank.fa \
    --hifi ./hifi_reads.fq.gz \
    --ont ./ont_reads.fq.gz \
    --out ./gap_out \
    --MaximumExtensionRound 25 \
    -t 20
```

When the job finishes:

- Open `./gap_out/family-report.html` directly in a local web browser to inspect closure status, family histories, candidate connections, junction metrics, and stop reasons.
- Check `status: "closed"` in `./gap_out/family-result.json` (or the report header) before using `./gap_out/<name>.final.fa`; a zero process exit code alone does not mean the gap closed or that the sequence is biologically verified.
- Supply **original FASTQ/FASTQ.gz** files for `--ont` whenever ONT-only assembly or mixed-to-ONT-only fallback may occur (`--hifi` accepts FASTA or FASTQ).

For the other modes, shared budgets, resume rules, and full options, see [HOWTO.md](HOWTO.md).

## Documentation

- **Practical Users' Guide**: [HOWTO.md](HOWTO.md) — full operational reference for all five modes, parameters, HTML reports, outputs, and troubleshooting.
- **Design Notes**:
  - [docs/design/bidirectional-extension.md](docs/design/bidirectional-extension.md) — bidirectional historical families, shared budgets, and checkpoint/resume policy.
  - [docs/design/junction-validation.md](docs/design/junction-validation.md) — full-sequence fallback, original-flank protection, bounded read-supported terminal repair, and anchor-backoff retries.
  - [docs/design/telomere-target-search.md](docs/design/telomere-target-search.md) — TelSeeker shared target index, batched candidate validation, and local junction corroboration.
  - [docs/design/report-presentation.md](docs/design/report-presentation.md) — offline HTML report presentation and schema alignment.
- **Dated Validation Records**:
  - [SSH 180 expanded real-read matrix](docs/validation/2026-11-22-ssh180-expanded-matrix.md) — 39 workloads across fixed gaps, workflow modes, shared limits, and negative cases.
  - [SSH 180: two masked HiFi gaps closed](docs/validation/2026-11-22-ssh180-new-dataset.md) — measured gap-only comparisons and ONT suitability limits.
  - [SSH 180 junction validation](docs/validation/2026-11-22-junction-repair.md) — junction checks and bounded terminal repair validation.
  - [SSH 180 TelSeeker target search](docs/validation/2026-11-22-telomere-target-search.md) — shared target index, batched refinement, and local support checks.
  - Earlier records: [docs/validation/2026-11-21-ssh180-real-ont.md](docs/validation/2026-11-21-ssh180-real-ont.md), [docs/validation/2026-11-21-ont-quality-repair.md](docs/validation/2026-11-21-ont-quality-repair.md)
- **Historical v1 Guide**: [v1/README.md](v1/README.md) — legacy DEGAP 1.0 documentation (historical reference only).

## Citation

Huang, Y. et al. DEGAP: Dynamic Elongation of a Genome Assembly Path. *Briefings in Bioinformatics*, Volume 25, Issue 3, May 2024, bbae194. [DOI: 10.1093/bib/bbae194](https://doi.org/10.1093/bib/bbae194)

## Contact

For comments, bug reports, or questions, please contact <jzhang@mail.hzau.edu.cn>.
