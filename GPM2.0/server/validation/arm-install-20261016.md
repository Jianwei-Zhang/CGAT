# ARM fresh installer and execution acceptance — 2026-10-16

## Result and evidence boundary

**PASS** for an isolated fresh official installer-managed Linux ARM64 environment,
then synthetic no-reads and full reads-QC workflows through both delivery packages.
Source is pinned to `b12fce9f375eb0422adbeccc9ec10586bccf251b`, not an updated
public Release asset. This is functional smoke evidence, NOT real-genome speed,
biological accuracy, exact cross-architecture equality, every optional branch,
or native App/import acceptance.

Remote root: `~/cgat-reads-debug/arm-install-20261016-b12fce9/` on SSH 180.
Source archive SHA-256:
`59dbc3e8b048662dccf89d49a271bee437b8ea9bb13c27b6ab0cee2aee72112b`.
Complete machine-readable results, manifests, stage times, package hashes,
package architectures and script hashes: `arm-install-20261016-results.json`.

## Architecture and isolation

- Login: port18081, cli-ARM-01, aarch64. Compute: agent-ARM-39, ARM queue only.
- Existing registered x86 environments were project-local. ARM login did not
  automatically expose mamba/conda. Public ARM Conda defaults to shared HOME
  `.conda/envs` and `.conda/pkgs`; an ARM login alone is NOT isolation.
- This test sets HOME to `<root>/home`, MAMBA_ROOT_PREFIX to `<root>/mamba`,
  CONDA_ENVS_PATH to `<root>/mamba/envs`, CONDA_PKGS_DIRS to `<root>/mamba/pkgs`,
  plus test-local XDG cache/config. Runtime prefix is `<root>/mamba/envs/cgat-server`.
- No user shell startup, public module software or existing environments changed.
  Existing test8 x86 ownership/state/history hashes were unchanged after testing.
  No x86 jobs were killed, resubmitted, migrated, or hot-edited.

## Actual installation

1. The initial test archive path was corrected before dependency installation;
   the launcher-only exit127 log is retained, not counted as an installer failure.
2. Public module `arm/miniconda3/23.1.0` was loaded. Official
   `bash source/server/install.sh --manager conda` failed while fetching full
   repodata: HTTP `ChunkedEncodingError / InvalidChunkLength`. This is retained
   as a failed Conda/network attempt, not silently counted as success.
3. Downloaded ARM micromamba 2.9.0 into `<root>/bin`, verified aarch64 executable
   startup and hashes. No global micromamba bootstrap or shell init was used.
4. Unmodified official `install.sh --manager micromamba` returned **0 / READY**;
   `install.sh --check --manager micromamba` returned **0 / READY**, 12/12 commands.
   All 188 Conda packages were ARM64 (138) or noarch (50); no linux-64 packages.
5. Actual compute-node startup: Python3.11.14, minimap2 2.31-r1302,
   samtools1.23.1, MUMmer4.0.1, Meryl1.4.2, pigz2.8. MERQURY was set by activation.

This qualifies the explicit micromamba installer path. It does not claim that
all manager/bootstrap/network combinations, including the failed stock Conda
attempt, are proven working.

## Necessary compute tests only

Both scripts request four CPUs, queue `arm`, `-aa`, with pipeline `-t 4` and a
1500-second test cap. Installation/network activity stayed on the login node;
input generation, QC and alignment ran on compute nodes. No broad local tests,
frontend/browser checks or baseline engine reruns were added.

| Test | Job | Scheduler | Complete stages | Job wall time |
| --- | ---: | --- | ---: | ---: |
| No reads, 2 x 60kb chromosomes | 40587548 | SUCCEEDED | 13/13 | 32s |
| Full reads QC, 2 x 120kb chromosomes | 40587562 | SUCCEEDED | 13/13 | 55s |

Job wall includes activation, fixture generation, startup and artifact checks;
these tiny inputs are NOT a performance benchmark. The full-QC fixture contains
1268 synthetic 6kb reads (7,608,000bp), deterministic 0.1% substitutions. Both
assembly datasets completed Meryl/Merqury/CRAQ; four contig QVs were 46.60–48.10,
CRAQ scores parsed, and all `reads_qc_pass` values were true. Production filtering
and biological thresholds were not changed.

The first full-QC fixture (40587549, 60kb chromosomes) completed both datasets'
external QC but then failed the primary q-eligible-record gate. Its failed logs
remain. Only the test fixture was lengthened for a fresh independent retry;
there was no test-output rewriting or threshold weakening. The exact cause of
that first fixture's QC eligibility was not fully diagnosed; the successful
120kb fixture does not erase this boundary.

Full and Light archives were read through gzip EOF/CRC, paths inspected, report
HTML confirmed, and all stage statuses checked. Full contains ten FASTA files;
Light contains none. Sizes and SHA-256 are in the JSON. Actual App import and
native rendering were not tested.

## Reproduction and retained records

The remote root retains unmodified `source/server/`, `environment.sh`, installer
logs/check reports, `no_reads.dsub`, `with_reads_v2.dsub`, fixture generators,
`startup.sh`, `verify_run.py`, all failed/successful workspaces and hashes.
Use the pinned environment script and **ARM** scheduler; do not reuse the x86
runtime directory. No new Release source asset was published for this test.
