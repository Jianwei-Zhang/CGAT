# Customer2665 complete optimized workflows on ARM/32 — 2026-10-16

## Request and submission

User requested both complete real-data workflows on ARM, **32 CPUs each**, in a
new path. Existing original/x86 optimized/suffix tasks must remain untouched.

Root: `~/cgat-reads-debug/full-optimized-2665-arm32-20261016-6cc768d/` on SSH 180.

| Case | Job | Queue/CPU | Started | Initial observed state/node |
| --- | ---: | --- | --- | --- |
| skip-self | 40587687 | arm / 32 | 13:09:49 CST | RUNNING / agent-ARM-01 |
| self-m200-n100 | 40587688 | arm / 32 | 13:09:49 CST | RUNNING / agent-ARM-31 |

Scripts use `-q arm`, `-aa`, `cpu=32`, and the pipeline `--threads 32`. Resource
checks before submission found several ARM nodes with at least 118 free CPUs.
No single-node exclusive allocation, CPU oversubscription or x86 resubmission.

## Frozen source, full inputs and settings

Same workflow source as the new x86 pair: `6cc768d864dc2a541964dce080f0f8d938018938`.
Source archive SHA-256:
`d7718ee3ccedc73471da27a18249d505ffa579bf2d3ef09c5a36119d4f8da49b`;
verified after copying into the new ARM root and before extraction.

The launcher `full_optimized_2665.py` now accepts explicit architecture, thread
budget and required tool prefix. Its defaults stay x86/16; the copy used by the
running x86 pair was NOT changed. This ARM launcher SHA-256 is
`658dd18edaa0d97b2e458b17d60dd3020499adaea5560dabde15f4249baa2312`.

Original recorded argv is reused, changing output path and thread budget32,
plus explicit optimized/Step3 settings. Complete Caryophyllales_ref and datasets
hifiasm/nextdenovo/flye in the original order; score60, asm10, TTTAGGG3,
max-fill1000000, tar.gz, no reads. Cases differ only in skip-self versus m200/n100.

Both run **optimized Step2/full**, **optimized Step3/gap-screen**, production
refill batching and compatible index reuse. Step2 gap-screen is NOT enabled.
No upstream checkpoint, raw alignment, .mmi or numerical cache is borrowed.
Complete workflow runs from preparation/reference alignment to Full/Light packages.

## ARM environment and interpretation

Reuse only the verified installed ARM environment:
`~/cgat-reads-debug/arm-install-20261016-b12fce9/mamba/envs/cgat-server`.
Activation uses the ARM Conda module. No install/update operation touches this
environment, and tools must resolve inside its prefix; ELF architecture and
actual version startup are checked on compute nodes. Test HOME/XDG config/cache
are in the new root; every workspace owns its generated runtime and data/cache.
No original ARM smoke output or active x86 workspace is modified.

Expected versions: Python3.11.14, minimap2 2.31-r1302, MUMmer4.0.1,
samtools1.23.1, pigz2.8. The x86 pair uses minimap2 2.30-r1287, Python3.10.12,
samtools1.21 and pigz2.4. Hence architecture, tool versions **and** CPU budgets
all differ. Report ARM total wall/stage times independently; do not interpret
ARM32/x8616 wall ratio as isolated thread scaling or architecture performance.

Preflight records full input hashes, binary paths/hashes and actual versions.
Postchecks retain the existing DNA/Final Path comparisons against saved customer
golden results, actual Step2/full and Step3/gap-screen checkpoint settings and
all successful stages/package presence. Cross-architecture differences fail the
checks rather than being waived; baseline results are only read, never rerun.
Full archive acceptance and App import remain distinct later gates.

## Submission evidence and validation boundary

Remote `.dsub`, `environment.sh`, source archive, launcher, input/tool reports,
per-case logs, generated workspaces and script hashes remain under the new root.
Machine-readable job/resource records: `full-optimized-2665-arm32-20261016-results.json`.
At 13:10:01 both jobs were RUNNING in preflight; no completion/results claim.
Only scoped Python syntax, Bash syntax, transfer hash and startup checks were
required; no unrelated unit suite, frontend/browser or baseline tests added.

At 13:10:52 both jobs passed architecture/tool-prefix/input preflight and entered
preparation. Actual minimap2 was 2.31-r1302; generated options confirmed threads32,
optimized, Step2 full, Step3 gap-screen and the correct skip_self flag.
