# GPM2.0 Server

[中文](README_zh.md) | **English**

## Quick start

On your Linux server, download the GPM Server tools (source package) from [Release v2.0.10](https://github.com/Jianwei-Zhang/CGAT/releases/tag/v2.0.10), then extract, enter the tool directory, and install:

```bash
# 1. Download, extract, and enter the Server tool directory
curl -fLO https://github.com/Jianwei-Zhang/CGAT/releases/download/v2.0.10/GPM_Server_2.0.10_source.tar.gz
tar -xzf GPM_Server_2.0.10_source.tar.gz
cd GPM_Server

# 2. Install and verify the isolated environment
bash install.sh

# 3. Activate it with the command printed by the installer, for example
mamba activate cgat-server

# 4. Prepare, compute, and create the delivery archives
bash run.sh \
  --ref /path/to/reference.fa \
  --ds /path/to/assembly.fa \
  -o ./gpm_server
```

A successful run ends with an explicit `Final delivery packages` summary. The only
delivery files are `gpm_server.tar.gz` (Full: FASTA + report) and
`gpm_server.light.tar.gz` (Light: FASTA omitted, report included). Both contain the complete
`gpm_server/report/` directory; no separate report ZIP is created. The local report
remains available at `gpm_server/report/report.html`.

The default is parallel `tar.gz` compression with pigz. Use `--archive-format zip` for ZIP; the App accepts both formats.

`--ref` and repeatable `--ds` accept either `<name> <fasta>` or just `<fasta>`.
When the name is omitted, it comes from the FASTA basename: `.gz` and one
`.fa`, `.fasta`, or `.fna` suffix are removed case-insensitively. Runs outside
letters, numbers, dot, underscore, and hyphen are replaced with `_`. Use the
explicit form when you want another name:

```bash
bash run.sh \
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
specification. Both Linux ARM64 and x86_64 use `meryl=1.4.2`, avoiding a reproduced multithreaded Meryl 1.4.1
crash on ARM64 while keeping the Meryl version consistent.
Deploy the complete `server/` directory, including both specification files.

When using cluster modules, load tools and runtime libraries for the execution
node's architecture and set `MERQURY` as required by that Merqury installation.
Finding a command on `PATH` does not prove it can run: `GLIBCXX_* not found`
indicates an incompatible C++ runtime. Load the matching GCC runtime or use the
isolated environment created by the installer. Keep the same environment active
for `run.sh`.

When an external QC command fails, the Server log includes bounded stdout/stderr
tails so the underlying error remains available after temporary QC cleanup.

`run.sh -t 32` sets the total compute-thread budget. Newly prepared workspaces
automatically share it across independent alignment tasks.

### Resuming a workspace after the Step3 gap-origin fix

The error `cannot map filtered Step3 gap back to q2` can occur when a run of
`N` bases lies inside a source contig or spans multiple path segments. Step3 now
preserves those gap origins through filtering, including merged gaps.

A prepared workspace contains its own runtime copy. After updating this Server
checkout, update the failed workspace from this directory:

```bash
workspace=/path/to/gpm_server
cp tools/grt_step23.py "$workspace/.prepare_lib/tools/grt_step23.py"
```

Then rerun or resubmit that workspace's `run_all.sh` in the same environment.
Keep the existing workspace and caches; compatible raw MUMmer alignments can be
reused while the corrected stage outputs are regenerated.

## Optional AI agent skill

The source tree includes the official [gpm-server skill](skills/gpm-server/SKILL.md)
for first runs, safe resume, diagnosis, and verified result handoff. It is optional:
the CLI above still works without an AI agent. Keep the skill with its companion
Server source; do not assume older release archives already include this addition.

Point your agent at that `SKILL.md`, or copy the **whole** `skills/gpm-server/`
folder into your chosen agent's skill directory according to its documentation.
No agent configuration is changed by `install.sh`.
The skill's `server-tools.path` records the tools location: `../..` relative to
the skill directory in a complete source bundle. After installing the skill alone,
run `bash /actual/skill/scripts/server_tools_path.sh --set /actual/Server` once.
Later tasks read and validate that saved location without searching; a stale path
fails explicitly rather than silently choosing another installation.
On failure, the agent first asks for the existing tools location. If unknown, it
asks whether to perform a bounded search or reinstall; neither happens without
authorization. The installer summary prints the absolute tools path and binding
command without adding Server-path exports to `.bashrc`/`.zshrc`. This is separate
from the existing Bash initialization when bootstrapping micromamba.
For first setup, tell the agent the Server path; later tasks reuse the binding.
Provide input roles (the first `--ds` is the primary assembly), output path,
resource budget, and local scheduler/environment instructions. For example:

> Follow the gpm-server skill. The Server tools are at /work/GPM_Server. Use
> /work/inputs/ref.fa as reference and /work/inputs/assembly.fa as primary.
> Check the environment, then run in /work/runs/sample with at most 4 threads.
> Follow this cluster's submission rules; do not run on the login node, alter
> scientific parameters, or overwrite existing results. Report logs and outputs.

Skill v2 supports [user-local operational lessons](skills/gpm-server/references/local-learning.md)
in `local/notes.md`, separate from the official rules. It reads relevant lessons on
future tasks, but saves a verified repair only with user consent (default: ask;
explicit scoped `auto-local` opt-in or `off` is supported). This is agent guidance,
not a background learning service or enforced permission system. Local notes never
authorize scientific parameter changes, destructive repairs, or uploads.

For an approved skill upgrade, use the new bundle's `scripts/stage_skill_update.py`
to stage a **new directory outside agent discovery**, preserving the existing
`local/` and tools binding. Review and activate it separately; do not overwrite the
installed folder. The helper does not upgrade Server tools, merge custom official
files, or change agent configuration. See the linked instructions for consent scope
and revalidating old lessons. Earlier v1 smoke records do not validate v2 learning;
its automated checks cover filesystem preservation, not agent decision behavior.

See the [v2 validation boundary and behavioral acceptance matrix](validation/agent-skill-v2-local-learning.md).

For a workflow-only trial, ask for the [synthetic smoke test](skills/gpm-server/references/smoke-test.md).
It uses small generated inputs and real tools, not scientifically meaningful data.
See the [ARM/Donau record](validation/agent-skill-v1-180.md) and
[x86/LSF and tools-location record](validation/agent-skill-v1-140-1.md) for actual
coverage and exclusions; a skill is guidance, not a permissions sandbox.

## File roles

| File | Purpose | When to run it |
| --- | --- | --- |
| `install.sh` | Create, update, and verify the `cgat-server` environment | First installation or dependency updates |
| `env.sh` | Compatibility entry for `install.sh` | Only for existing commands |
| `run.sh` | Prepare and execute the full workflow, or resume an existing workspace | First run or recovery |
| `prepare.sh` | Compatibility entry for preparation only | When separate script generation is needed |
| `export_final_path_fasta.sh` | Rebuild FASTA from a Final Path TSV exported by the App | Optional late-stage task, not installation |

Rerun the same `run.sh` command, or use `bash run.sh -o ./gpm_server` to resume with validated results reused. The generated `run_all.sh` remains directly executable.

`--max-fill <bp>` sets the length limit for both Step3 optimized refill rounds (default: `1000000`). Change it with `bash run.sh -o ./gpm_server --max-fill 2000000`; use a new output directory when changing inputs or other preparation settings.

See the parent repository's `README.md` for the complete options and desktop workflow.
