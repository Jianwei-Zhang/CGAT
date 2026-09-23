# GPM2.0 Server

[中文](README_zh.md) | **English**

## Quick start

```bash
# 1. Install and verify the isolated environment
bash install.sh

# 2. Activate it with the command printed by the installer, for example
mamba activate cgat-server

# 3. Prepare one project workspace
bash prepare.sh \
  --ref /path/to/reference.fa \
  --ds /path/to/assembly.fa \
  -o ./gpm_server

# 4. Run the workflow and create the delivery archives
bash ./gpm_server/run_all.sh
```

A successful run ends with an explicit `Final delivery packages` summary. The only
delivery files are `gpm_server.zip` (Full: FASTA + report) and
`gpm_server.light.zip` (Light: FASTA omitted, report included). Both contain the complete
`gpm_server/report/` directory; no separate report ZIP is created. The local report
remains available at `gpm_server/report/report.html`.

`--ref` and repeatable `--ds` accept either `<name> <fasta>` or just `<fasta>`.
When the name is omitted, it comes from the FASTA basename: `.gz` and one
`.fa`, `.fasta`, or `.fna` suffix are removed case-insensitively. Runs outside
letters, numbers, dot, underscore, and hyphen are replaced with `_`. Use the
explicit form when you want another name:

```bash
bash prepare.sh \
  --ref reference /path/to/reference.fa \
  --ds assembly /path/to/assembly.fa \
  -o ./gpm_server
```

A successful installation ends with `GPM Server installation: READY`. Check it later without changing the environment:

```bash
bash install.sh --check
```

The installer searches for `mamba`, `micromamba`, then `conda`. Select one explicitly when needed:

```bash
bash install.sh --manager conda
```

### ARM64 and cluster environments

On Linux ARM64 (`aarch64`/`arm64`), the installer selects a separate dependency
specification with `blast=2.16.0` for package availability. Both Linux ARM64
and x86_64 use `meryl=1.4.2`, avoiding a reproduced multithreaded Meryl 1.4.1
crash on ARM64 while keeping the Meryl version consistent.
Deploy the complete `server/` directory, including both specification files.

When using cluster modules, load tools and runtime libraries for the execution
node's architecture and set `MERQURY` as required by that Merqury installation.
Finding a command on `PATH` does not prove it can run: `GLIBCXX_* not found`
indicates an incompatible C++ runtime. Load the matching GCC runtime or use the
isolated environment created by the installer. Keep the same environment active
for `prepare.sh` and `run_all.sh`.

When an external QC command fails, the Server log includes bounded stdout/stderr
tails so the underlying error remains available after temporary QC cleanup.

## File roles

| File | Purpose | When to run it |
| --- | --- | --- |
| `install.sh` | Create, update, and verify the `cgat-server` environment | First installation or dependency updates |
| `env.sh` | Compatibility entry for `install.sh` | Only for existing commands |
| `prepare.sh` | Check inputs and tools, then generate one project's `gpm_server/` workspace | Once for each new project |
| `export_final_path_fasta.sh` | Rebuild FASTA from a Final Path TSV exported by the App | Optional late-stage task, not installation |

`prepare.sh` prepares a project; the generated `gpm_server/run_all.sh` performs the computation.

See the parent repository's `README.md` for the complete options and desktop workflow.
