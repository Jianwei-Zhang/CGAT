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
  --ref reference /path/to/reference.fa \
  --ds assembly /path/to/assembly.fa \
  -o ./gpm_server

# 4. Run the workflow and create the delivery archives
bash ./gpm_server/run_all.sh
```

A successful installation ends with `GPM Server installation: READY`. Check it later without changing the environment:

```bash
bash install.sh --check
```

The installer searches for `mamba`, `micromamba`, then `conda`. Select one explicitly when needed:

```bash
bash install.sh --manager conda
```

## File roles

| File | Purpose | When to run it |
| --- | --- | --- |
| `install.sh` | Create, update, and verify the `cgat-server` environment | First installation or dependency updates |
| `env.sh` | Compatibility entry for `install.sh` | Only for existing commands |
| `prepare.sh` | Check inputs and tools, then generate one project's `gpm_server/` workspace | Once for each new project |
| `export_final_path_fasta.sh` | Rebuild FASTA from a Final Path TSV exported by the App | Optional late-stage task, not installation |

`prepare.sh` prepares a project; the generated `gpm_server/run_all.sh` performs the computation.

See the parent repository's `README.md` for the complete options and desktop workflow.
