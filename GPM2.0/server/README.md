# GPM2.0 Server

[中文](README_zh.md) | **English**

## Quick start

On your Linux server, download the GPM Server tools (source package) from [Release v2.0.12](https://github.com/Jianwei-Zhang/CGAT/releases/tag/v2.0.12), then extract, enter the tool directory, and install:

```bash
# 1. Download, extract, and enter the Server tool directory
curl -fLO https://github.com/Jianwei-Zhang/CGAT/releases/download/v2.0.12/GPM_Server_2.0.12_source.tar.gz
tar -xzf GPM_Server_2.0.12_source.tar.gz
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
cp tools/grt_step2.py "$workspace/.prepare_lib/tools/grt_step2.py"
cp tools/grt_step3.py "$workspace/.prepare_lib/tools/grt_step3.py"
cp -R tools/grt_core "$workspace/.prepare_lib/tools/"
```

These updates apply to workspaces that already have independent Step2/Step3
entrypoints, and only while the workspace is not running. Rerun or resubmit
`run_all.sh` in the same environment; compatible raw MUMmer alignments can be
reused while stage results are regenerated. Older workspaces using
`run_grt_step23.sh` must retain their matching runtime; copying these files alone
does not migrate a combined execution plan.

### Independent GRT stage controls

New workspaces generate `run_grt_step2.sh` and `run_grt_step3.sh`, with separate
scheduler status and checkpoints. Run Step2 before Step3; Step3 refuses a missing,
changed, or incompatible completed Step2 result. Implementations are physically
separate in `grt_core/step2_engine.py` and `grt_core/step3_engine.py`; shared
alignment, structural-analysis and metadata services live in `repair_*.py`.
The source no longer ships `tools/grt_step23.py`. Existing legacy workspaces
retain their own combined entrypoint/runtime and are not modified automatically.

Step2 structural edits that remove a gap record the retained junction coordinate,
not a nonexistent output gap. Their events use `replacement_kind: none`, zero
replacement length and the empty-sequence digest; absorbed gap events retain
explicit supersession links. Terminal deletions anchor to a retained base rather
than one past the chromosome end. Missing gap origins or invalid edit prototypes
still fail explicitly; no gap is silently skipped or replaced with synthetic Ns.

Both stages share a content fingerprint covering both engines, entry scripts
and common modules. Changing any of them invalidates repair-stage results and
requires Step2 to run again. Independently validated raw MUMmer results remain
reusable when their exact input, tool and alignment-parameter identities match.

Newly prepared workflows enable the validated optimization route by default:

- `--grt-execution-profile optimized`: a shared CPU/memory-bounded nucmer pool,
  largest-target-first scheduling, verified partition FASTA reuse, exact anchor
  indexes and reuse of already-validated parsed coordinates. Publication and
  candidate tie-breaking retain their original order.
- Step2 remains **full scope**; its diagnostic-changing screen is not enabled.
- `--grt-step3-mummer-scope gap-screen`: anchor-safe donor-partition screening,
  followed by full-chromosome alignment of selected original partitions.
- Optimized Step3 refill batches same-round flank queries, preserves each
  chromosome’s query/hit order, and reuses a compatible content-verified `.mmi`.
  A cold mapping saves its index in the same invocation; changed target bytes,
  preset or executable invalidate index reuse. Empty queries remain skipped.

For rollback when preparing a **new** workspace, use
`--grt-execution-profile baseline --grt-step3-mummer-scope full` with either
`run.sh` or `prepare.sh`. Direct Python entries accept
`--execution-profile baseline|optimized` and the corresponding
`--step2-mummer-scope` / `--step3-mummer-scope`; defaults are optimized, full Step2
and gap-screen Step3. Refill batching follows the execution profile.

Existing workspace scripts/runtime are not modified automatically. Do not copy
these changes into a running workspace. Screening is not proof of universal
metadata/evidence equivalence; full datasets are compared against preserved old
results before release. Cache-assisted timings are not cold-pipeline benchmarks.

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

Skill v3 automatically retains concise, verified operational lessons in
`local/notes.md` when a similar pitfall could plausibly recur; it does not ask users
to choose persistence modes. It deduplicates notes and checks their scope/evidence
before reuse. Explicit no-write instructions and permissions still apply. Notes
never authorize scientific parameter changes, destructive repairs or uploads.
See [local learning](skills/gpm-server/references/local-learning.md).

For [official version checks and updates](skills/gpm-server/references/official-updates.md),
`official_update.py check` queries the official stable Server Release and the
repository-current skill separately. It uses asset digests and pinned commits,
not a historical version string. `stage` verifies a reviewed plan, downloads new
source to a fresh directory, preserves user-local experience and binds the candidate
to the new tools. Validation/activation and environment changes remain separate;
it does not overwrite a running installation, migrate runs or edit agent settings.
The offline `stage_skill_update.py` is still available for trusted local bundles.
This is agent guidance, not a background service or enforced permissions sandbox.
See the [v3 validation boundary](validation/agent-skill-v3-official-updates.md).

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
