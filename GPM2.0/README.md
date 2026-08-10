# GPM2.0

**English** | [中文](README_zh.md)

GPM2.0 combines reference-anchored results from multiple de novo assemblies in one workflow for import, inspection, lightweight editing, and Final Path export.

## Architecture

| Component | Role |
| --- | --- |
| Linux server | Runs alignment and GRT processing, then creates App delivery archives. Upload the repository's `server/` directory to the server. |
| Desktop App | Imports a delivery archive and provides visualization, editing, DEGAP integration, and export. |

Installers for `win-x86`, `win-arm64`, `mac-x86`, and `mac-arm64` are published on [GitHub Releases](https://github.com/Jianwei-Zhang/CGAT/releases). Development and release checks are documented in [Quality gates](QUALITY.md).

## Server Workflow

![GPM server-side workflow](app/readme-assets/serve_pipeline_en.png)

### 1. Create the environment

Run once on the Linux server:

```bash
bash server/env.sh
```

The script reuses `mamba`, `micromamba`, or `conda`. If none is available, it installs micromamba for the current user without `sudo`. Activate the generated environment with the command printed by the script, for example:

```bash
micromamba activate cgat-server
```

Re-running `env.sh` validates the managed environment and updates it only when the dependency specification changes.

| Purpose | Commands installed or required |
| --- | --- |
| Core workflow | `python3`, `samtools`, `zip`, `gzip` |
| GRT Final Path | `minimap2`, `nucmer`, `delta-filter`, `show-coords` |
| Alternative aligners | `blastn` + `makeblastdb`, or `winnowmap` + `meryl` |
| Optional reads QC | `meryl`, `merqury.sh`, `craq`; used only when `--reads` is supplied |

Keep this environment active for both `prepare.sh` and the generated `run_all.sh`.

### 2. Prepare a workspace

Minimal example with an explicit output directory:

```bash
bash server/prepare.sh \
  --ref rice_IRGSP_1_0 /path/to/ref.fa \
  --ds hifiasm /path/to/hifi.fa \
  --ds flye /path/to/flye.fa \
  --ds canu2 /path/to/canu2.fa \
  -o ./gpm_server \
  -t 10
```

The first `--ds` is the locked primary dataset; later initial `--ds` entries are support datasets. Plain or gzip-compressed `.fa`, `.fasta`, and `.fna` inputs are accepted.

#### Common options

| Option | Required / default | Description |
| --- | --- | --- |
| `--ref <name> <fasta>` | Required once | Reference name and FASTA. |
| `--ds <name> <fasta>` | Required, repeatable | Assembly dataset. The first is primary; the rest are support datasets. |
| `-o, --out <dir>` | `./gpm_server` | Server workspace and generated scripts. |
| `-s, --score <0-100>` | `60` | Minimum chromosome-assignment coverage percentage. |
| `--aligner <engine>` | `minimap2` | Main alignment engine: `minimap2`, `blastn`, or `winnowmap`. |
| `-t, --threads <n>` | `10` | Worker threads written into generated commands. |
| `--skip-self` | Off | Skip same-dataset self alignment; same-dataset Subview becomes unavailable. |
| `--tel <motif> <count>` | Optional, repeatable | Mark exact telomere-like repeats on both strands. Example: `--tel TTAGGG 20`. |
| `--cen <fasta>` | Optional | Reference centromere FASTA. Record names must end in `_centromere`, such as `Chr01_centromere`. |
| `--cen-min-len <bp>` | `10000` | Minimum centromere alignment length. |
| `--cen-min-identity <pct>` | `80` | Minimum centromere alignment identity percentage. |
| `--reads <fastq>` | Optional, repeatable | Enable shared Meryl data plus per-dataset Merqury/CRAQ QC. |
| `--grt-qc-memory-gb <n>` | `80` | Memory limit for optional reads QC. |
| `--grt-kmer-size <n>` | `21` | K-mer size for optional reads QC. |

#### Aligner-specific options

| Aligner | Option | Allowed values / default |
| --- | --- | --- |
| `minimap2` | `--minimap-preset` | `asm10` or `asm5`; default `asm10` |
| `blastn` | `--blastn-task` | `blastn`, `megablast`, or `dc-megablast`; default `blastn` |
| `blastn` | `--blastn-evalue` | Positive number; default `1e-10` |
| `winnowmap` | `--winnowmap-preset` | `asm20`, `asm10`, or `asm5`; default `asm20` |
| `winnowmap` | `--winnowmap-kmer` | Positive integer; default `19` |
| `winnowmap` | `--winnowmap-repeat-fraction` | Number in `(0, 1)`; default `0.9998` |

An aligner-specific option is valid only with its matching `--aligner`. GRT processing always resolves `minimap2` and the MUMmer4 commands from `PATH`.

### 3. Run, resume, and monitor

```bash
bash ./gpm_server/run_all.sh
```

The runner executes the generated plan serially, stops at the first error, validates checkpoints before reuse, and creates both archives beside `gpm_server/`:

| Archive | Contents and use |
| --- | --- |
| `gpm_server.zip` | Full App package with source/reference FASTA and authoritative q4 FASTA. Supports client-side FASTA export. |
| `gpm_server.no_fasta.zip` | No-FASTA App package with `.fai`, metadata, Final Path, source-card state, and PAF views. Supports import, inspection, and PNG/TSV export. |

Resume without extra options by running the same `run_all.sh` command. The prepared thread count remains fixed; runtime `--threads`, `--from`, `--until`, and `--stage` overrides are not supported.

```bash
tail -F ./gpm_server/logs/run_all.log
```

Current unit states are written to `gpm_server/logs/status.tsv`. Only one runner may own a workspace at a time.

### 4. Add data and re-package

Append one dataset and create an add package for an existing desktop workspace/project:

```bash
bash ./gpm_server/add_dataset.sh \
  --ds ds4_name /path/to/ds4.fa \
  -o ./gpm_server/add_ds4_name.zip
```

The new dataset is merged into the server workspace but does not join the locked GRT recipe or rewrite the precomputed Final Path. Its contigs remain available for manual editing in the App.

The initial `run_all.sh` already builds both delivery archives. Re-run the standalone packagers only after later changes such as `add_dataset.sh` or `add_ctg.sh`:

```bash
bash ./gpm_server/package_full_zip.sh
bash ./gpm_server/package_light_no_fasta_zip.sh
```

Use a rebuilt full package for a new desktop workspace or a complete re-import. Add packages are only for an existing workspace/project.

## Desktop App

### Install and import

Download the installer for the client architecture from [GitHub Releases](https://github.com/Jianwei-Zhang/CGAT/releases), then import either delivery archive.

The package fixes the primary/support recipe and loads the Server-precomputed Final Path. Project-level paths remain editable and can continue into DEGAP or export. Only the current v2 GRT delivery contract is supported; regenerate v1 or non-GRT packages with the current Server scripts.

### Export Final Path FASTA from a no-FASTA package

Export Final Path TSV from the App, copy it back to the server that retains the original FASTA files, and run:

```bash
bash server/export_final_path_fasta.sh \
  --tsv /path/to/project_Chr01_path.tsv \
  --gpm_server ./gpm_server \
  -o /path/to/project_Chr01_path.fa
```

The helper generated inside `gpm_server/` detects that workspace automatically:

```bash
bash ./gpm_server/export_final_path_fasta.sh \
  --tsv /path/to/project_Chr01_path.tsv \
  -o /path/to/project_Chr01_path.fa
```
