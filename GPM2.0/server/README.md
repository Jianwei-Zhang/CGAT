# GPM2.0 Server

[中文](README_zh.md) | **English**

## Quick start

On your Linux server, download the GPM Server tools (source package) from [Release v2.0.12](https://github.com/Jianwei-Zhang/CGAT/releases/tag/v2.0.12), or the [official docs](https://riceome.hzau.edu.cn/cgat/en/downloads), then verify, extract into the default or custom directory, and install:

```bash
# 1. Download into the tools directory; keep your project working directory
SERVER="$HOME/bin/GPM_Server"  # Custom paths are supported; do not overwrite an existing installation
(
  set -euo pipefail
  mkdir -p "$(dirname "$SERVER")"
  mkdir "$SERVER"
  cd "$SERVER"
  archive=GPM_Server_2.0.12_source.tar.gz
  curl -fL --connect-timeout 8 --max-time 60 -o "$archive" \
    "https://riceome.hzau.edu.cn/cgat/downloads/v2.0.12/$archive" ||
    curl -fL --connect-timeout 8 --max-time 60 -o "$archive" \
      "https://github.com/Jianwei-Zhang/CGAT/releases/download/v2.0.12/$archive"
  curl -fL --connect-timeout 8 --max-time 30 -o SHA256SUMS \
    https://riceome.hzau.edu.cn/cgat/downloads/v2.0.12/SHA256SUMS ||
    curl -fL --connect-timeout 8 --max-time 30 \
      https://api.github.com/repos/Jianwei-Zhang/CGAT/releases/tags/v2.0.12 |
      python3 -c 'import json,sys; r=json.load(sys.stdin); print("\n".join(a["digest"].removeprefix("sha256:")+"  "+a["name"] for a in r["assets"] if a["name"].endswith("_source.tar.gz")))' > SHA256SUMS
  grep "  $archive$" SHA256SUMS | sha256sum -c -
  tar -xzf "$archive" --strip-components=1
  # 2. Install and verify the isolated environment
  bash ./install.sh
)
```

Continue only after installation succeeds. Run analysis from your project working directory, not the tools directory.

```bash

# 3. Activate it with the command printed by the installer, for example
mamba activate cgat-server

# 4. Prepare, compute, and create the delivery archives
bash "$SERVER/run.sh" \
  --ref /path/to/reference.fa \
  --ds /path/to/assembly.fa \
  -o ./gpm_server
```

A successful run ends with an explicit `Final delivery packages` summary. The only
delivery files are `gpm_server.tar.gz` (Full: FASTA + report) and
`gpm_server.light.tar.gz` (Light: FASTA omitted, report included). Both contain the complete
`gpm_server/report/` directory; no separate report ZIP is created. The local report
remains available at `gpm_server/report/report.html`.

Report tables embed up to 200 preview rows with exact full counts and source paths;
full audit details remain in the Server workspace. This keeps HTML and App report
snapshots compact instead of repeatedly embedding the evidence registry.


The default is parallel `tar.gz` compression with pigz. Use `--archive-format zip` for ZIP; the App accepts both formats.

`--ref` and repeatable `--ds` accept either `<name> <fasta>` or just `<fasta>`.
When the name is omitted, it comes from the FASTA basename: `.gz` and one
`.fa`, `.fasta`, or `.fna` suffix are removed case-insensitively. Runs outside
letters, numbers, dot, underscore, and hyphen are replaced with `_`. Use the
explicit form when you want another name:

```bash
bash "$SERVER/run.sh" \
  --ref reference /path/to/reference.fa \
  --ds assembly /path/to/assembly.fa \
  -o ./gpm_server
```

A successful installation ends with `GPM Server installation: READY`. Check it later without changing the environment:

```bash
bash "$SERVER/install.sh" --check
```

The installer searches for `mamba`, `micromamba`, then `conda`. Select one explicitly when needed:

```bash
bash "$SERVER/install.sh" --manager conda
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

### Resuming a workspace after Step3 provenance fixes

The error `cannot map filtered Step3 gap back to q2` can occur when a run of
`N` bases lies inside a source contig or spans multiple path segments. Step3 now
preserves those gap origins through filtering, including merged gaps.
The finalization error `accepted event disappeared before q4 without one exact q3 segment`
can also result from a partially trimmed Step2 patch; the retained-source fix
preserves its exact surviving fragments and original replay history.

Use the updater below, then rerun or resubmit `run_all.sh` in the same environment
when you are ready. Required stage results are regenerated while compatible raw
MUMmer caches can be reused. The updater itself never starts analysis.

### Update tools, skill, and project runtime

Use the same command to check or update:

```bash
bash ~/bin/GPM_Server/update.sh
```

This entrypoint requires a source package containing `update.sh`. If an older package lacks it, follow the Server/skill one-time adoption instructions rather than overwriting the installation.

For custom installations use the actual path. Run it from the project root or a
child directory to align that project's `.prepare_lib/` with tools. Outside a
project, other projects are not scanned. Checks/downloads prefer the
[official docs](https://riceome.hzau.edu.cn/cgat/en/downloads), falling back to
[GitHub Release](https://github.com/Jianwei-Zhang/CGAT/releases/latest) on failure.
Size, SHA-256 and the source file manifest are verified. Tools and skill come from
one release bundle; refreshed same-version assets are detected too.

- All scoped files match: reports already up to date.
- New files or an outdated runtime: lists changes and asks `[y/N]`.
- `Y/y` proceeds; `N/n`, Enter, EOF or no interactive terminal cancels. No `--check`/`--yes` flags.
- Preserves the whole skill `local/`, valid bindings, inputs, results, logs, caches,
  generated scripts and dependency environment.
- Separately installed skills registered with `server_tools_path.sh --set` are
  updated too; agent configuration is not scanned.

Stop all affected jobs, including other nodes, before confirming. Active jobs,
conflicting paths, known custom edits, dependency-spec changes and unsupported
legacy plans stop the update; it never reinstalls dependencies or reruns analysis.
Legacy files without a baseline are listed for review because customizations
cannot be distinguished automatically. Backups live under the project's
`.run_all/server-update-*`, or under tools when no project is selected. Failed
writes attempt rollback; a successful update prints an advanced rollback command.
Reload the agent session after a skill update. For older tools without `update.sh`,
follow the [one-time adoption procedure](skills/gpm-server/references/official-updates.md),
not an overwrite/reinstall. Docs can work without GitHub; a stale mirror cannot
downgrade a newer installed version/build. Network or integrity failure never
means “already latest”.

### Independent GRT stage controls and execution profiles

New workspaces generate separate `run_grt_step2.sh` and `run_grt_step3.sh` stage scripts with independent scheduler status and checkpoints. Run Step2 before Step3; Step3 validates that a compatible Step2 result is present before starting. Both stages share a content fingerprint covering the repair engines and shared modules—when any repair code changes, stage outputs are invalidated and regenerated from Step2 while compatible raw MUMmer alignment caches remain reusable.

Newly prepared workflows enable the validated optimization route by default:

- `--grt-execution-profile optimized`: uses a shared CPU/memory-bounded `nucmer` pool, largest-target-first scheduling, verified partition FASTA reuse, exact anchor indexes, and coordinate-parse cache reuse while preserving deterministic output and tie-breaking order.
- Step2 always runs at **full scope**.
- `--grt-step3-mummer-scope gap-screen`: screens donor partitions safely by anchor before running full-chromosome alignment on selected partitions.
- Optimized Step3 refill batches same-round flank queries and reuses content-verified `.mmi` indexes.

To fall back to the unscreened baseline profile when preparing a **new** workspace, pass:

```bash
--grt-execution-profile baseline --grt-step3-mummer-scope full
```

Existing workspace scripts and embedded runtimes are not modified automatically; run `update.sh` inside a stopped project workspace when you want to synchronize its `.prepare_lib/` runtime.

## Optional AI agent skill

### Installation prompt for your AI agent

Copy this into your current agent:

```text
Install the official gpm-server skill for this AI agent:
https://github.com/Jianwei-Zhang/CGAT/tree/master/GPM2.0/server/skills/gpm-server
For downloads and updates, prefer the Server source package from
https://riceome.hzau.edu.cn/cgat/ and fall back to GitHub Release on failure.
Install the complete skills/gpm-server/ directory from that package.
If Server tools are installed, ask me for their path. Otherwise, ask whether to
install them at ~/bin/GPM_Server or a location I choose. After confirmation,
complete installation and path binding; preserve any existing skill local/ experience.
```

### Installation and use

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

The skill automatically retains concise, verified operational lessons in
`local/notes.md` when a similar pitfall could plausibly recur; it does not ask users
to choose persistence modes. It deduplicates notes and checks their scope/evidence
before reuse. Explicit no-write instructions and permissions still apply. Notes
never authorize scientific parameter changes, destructive repairs or uploads.
See [local learning](skills/gpm-server/references/local-learning.md).

Skill installation and updates use the same [official sources and safety rules](skills/gpm-server/references/official-updates.md)
as Server: `~/bin/GPM_Server` for new tools, existing/custom paths retained, and
`update.sh` for routine checks and updates. This is optional agent guidance, not
a background service or an enforced permissions sandbox.

For a workflow-only trial, ask for the [synthetic smoke test](skills/gpm-server/references/smoke-test.md).
It uses small generated inputs and real tools, not scientifically meaningful data.
See the [ARM/Donau record](validation/agent-skill-v1-180.md) and
[x86/LSF and tools-location record](validation/agent-skill-v1-140-1.md) for actual
coverage and exclusions; a skill is guidance, not a permissions sandbox.

## Progress logs and terminal colors

The prepared `run_all.sh` uses a compact console view by default. Stage boundaries,
validated reuse, rate-limited MUMmer chromosome counts, warnings and errors remain
visible. Per-chromosome copy/parse timings and cache hashes stay in the detailed log.
A quiet running unit emits a heartbeat after 60 seconds; progress is append-only,
not a terminal animation. Unknown child output is retained rather than guessed away.

- `logs/progress.log`: compact, plain-text progress; appended across invocations.
- `logs/run_all.log`: full timestamp/run-ID/event diagnostics, including performance metrics.
- `report/report.html`: unchanged report schema and data source. Original events and
  child output reach reporting/cache detection before presentation filtering. The
  existing bounded report output tail is retained; the full log remains authoritative.

From the Server tools directory:

```bash
# Read-only viewer; Ctrl+C stops viewing, not the analysis job.
python3 "$SERVER/tools/view_run_log.py" --server-dir ./gpm_server --follow
# Read full diagnostics instead.
python3 "$SERVER/tools/view_run_log.py" --server-dir ./gpm_server --detailed --follow
# Plain-text viewing works without the viewer.
tail -F ./gpm_server/logs/progress.log
```

Colors apply only to displayed status labels. Auto mode colors interactive terminals,
not Slurm `.out` files or pipes, and respects `NO_COLOR` and `TERM=dumb`.
Both the viewer and generated runner accept `--color auto|always|never`; an explicit
`always` overrides auto detection/`NO_COLOR`. Persistent logs and report data never
receive presentation color codes. To retain the old verbose console format on a
**subsequent** invocation, use `bash ./gpm_server/run_all.sh --log-style detailed`.
These flags belong to `run_all.sh`, not `run.sh`/`prepare.sh`.

Old prepared workspaces retain their embedded runtime until explicitly updated.
Do not replace tools/runtime while a job is running. This presentation change does
not require deleting caches, repreparing inputs, or changing the dependency environment.

## File roles

| File | Purpose | When to run it |
| --- | --- | --- |
| `install.sh` | Create, update, and verify the `cgat-server` environment | First installation or dependency updates |
| `update.sh` | Check and update Server tools, bound skills, and project `.prepare_lib/` runtime | Routine maintenance and workspace runtime alignment |
| `env.sh` | Compatibility entry for `install.sh` | Only for existing commands |
| `run.sh` | Prepare and execute the full workflow, or resume an existing workspace | First run or recovery |
| `prepare.sh` | Compatibility entry for preparation only | When separate script generation is needed |
| `export_final_path_fasta.sh` | Rebuild FASTA from a Final Path TSV exported by the App | Optional late-stage task, not installation |

Rerun the same `run.sh` command, or use `bash "$SERVER/run.sh" -o ./gpm_server` to resume with validated results reused. The generated `run_all.sh` remains directly executable.

`--max-fill <bp>` sets the length limit for both Step3 optimized refill rounds (default: `1000000`). Change it with `bash "$SERVER/run.sh" -o ./gpm_server --max-fill 2000000`; use a new output directory when changing inputs or other preparation settings.


See the parent repository's `README.md` for the complete options and desktop workflow.
