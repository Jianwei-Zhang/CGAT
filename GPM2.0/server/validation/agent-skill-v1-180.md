# GPM Server skill v1: SSH 180 smoke validation

Date: **2026-10-13**, Asia/Shanghai. This is a historical validation record, not
portable cluster configuration or a claim that the same modules remain available.
Machine-readable hashes and outcomes: [agent-skill-v1-180.json](agent-skill-v1-180.json).

## Intent and evidence boundary

Build the first official `gpm-server` skill and follow it on SSH alias `180` with
small synthetic inputs to discover operational pitfalls. **No scientific result
was requested or accepted.** The maintainer agent followed the skill; no independent
fresh agent or subagent was used. The pipeline used real site executables, not the
fake commands used in some local unit tests.

The portable skill is under `server/skills/gpm-server/` and ships with the complete
Server source tree. It has no hard-coded SSH host, account, queue, or module path.
The site's settings below belong only to this validation record.

## Source and isolated workspace

- Base source commit: `b8caa58038e995899a764c0d59834001c4e46ab8`.
- Source transfer SHA-256:
  `b955b109b6c5cdff42a02901906e387c7008680852f7fffc6e36413f9f9f2f4b`.
  This archive contains the baseline pipeline plus the initial skill/README changes,
  not a newly published release. No pipeline implementation was changed for the test.
- All remote files are beneath `~/cgat-reads-debug/skill-v1-20261013/`, separated into
  `source/`, `inputs/`, `jobs/`, `runs/`, `logs/`, and `reports/`.
- Raw logs, scripts, fixture manifest, stage snapshots and exit codes remain there.
  No production inputs, shared modules, shell startup files, or other workspaces
  were modified. No dependency installation was needed.
- After the run, `references/execution.md` was clarified to use the companion
  Python specification and tolerate the MUMmer help commands' documented nonzero
  status while inspecting their text. The final skill files were copied to the
  remote test tree and every file hash was compared with the local copy. These
  documentation-only edits are reflected in `skill_sha256` in the JSON; they do
  not change the transferred source archive hash or imply a third pipeline run.

## Environment and resource checks

WSL OpenSSH alias configuration was checked before connection (port 18081, local
CONNECT proxy, configured multiplexing). The login host reported `cli-ARM-01`,
`aarch64`; both compute jobs ran on `agent-ARM-40`, `aarch64`.

The site-specific environment script used:

```bash
source /etc/profile.d/modules.sh
export MODULEPATH="/share/software/modulefiles:/share/software/HPCKit/latest/modulefiles:${MODULEPATH:-}"
export appdir=/share/software/app/
module load arm/gcc/12.2.0 arm/python/3.11.11 arm/minimap2/2.28 arm/samtools/1.21 arm/mummer/4.0.0rc1
export PYTHONDONTWRITEBYTECODE=1
```

The module dependencies also loaded `arm/htslib/1.21`. Actual Python/minimap2/
samtools startup, MUMmer help capabilities, archive tools, writable shared storage,
queue availability and scheduler access were checked. This is **module-based
runtime validation**, not `install.sh --check` / installer `READY` acceptance.
The tested module versions are not claimed identical to the installer-pinned versions.

Each job requested **4 CPU cores**, queue `arm`, with `-aa` and no multi-node
option. Memory followed the site's per-core queue policy; no larger-memory override
was requested. Each job had a 900-second task-local execution cap via
`timeout --signal=TERM --kill-after=30s`. Computation, including preparation and
negative-input checks, ran on the allocated compute node, not the login node.

## Data and commands

The skill's `scripts/make_smoke_inputs.py` generated three FASTAs, **120,000 bases
each**, comprising two 60,000-base chromosomes:

- reference: complete synthetic sequence;
- primary: identical flanks with one 200-base internal N gap per chromosome;
- support: complete sequence with distinct contig IDs.

Total fixture size is below 400 KB including its manifest. Seed, roles, lengths,
N counts and SHA-256 are in the JSON record. No raw research data, reads, telomere
motifs or centromere inputs were used. No biological thresholds were weakened.

With `TASK` set to that dedicated root and `SERVER="$TASK/source/server"`, the
fresh command was:

```bash
bash "$SERVER/run.sh" \
  --ref reference "$TASK/inputs/tiny/reference.fa" \
  --ds primary "$TASK/inputs/tiny/primary.fa" \
  --ds support "$TASK/inputs/tiny/support.fa" \
  -t 4 -o "$TASK/runs/gpm_server"
```

The second, separately submitted job ran:

```bash
bash "$SERVER/run.sh" -o "$TASK/runs/gpm_server"
```

## Observed outcomes

| Check | Fresh run | Resume |
| --- | --- | --- |
| Donau job | `40529698` | `40529701` |
| Terminal state / process exit | `SUCCEEDED` / `0` | `SUCCEEDED` / `0` |
| Scheduler start–end (UTC+8) | 10:47:22–10:47:45 | 10:48:58–10:49:10 |
| Successful status rows | 12 / 12 | 12 / 12 |
| Outer `SKIP_VALID` events | 0 | 5 |
| Report status | `success`, no errors | `success`, no errors |
| Full / Light archives | Both finalized | Both refreshed and finalized |

The resumed report has a new run ID. Reference alignments, chromosome assignment,
and two chromosome alignment units reused valid outer checkpoints. Other units
were entered under their own cache/validation rules; this is not a claim that the
entire resume did zero work.

Both final resumed gzip streams were read to EOF (including CRC/trailer), and tar
members were inspected without extraction. Both contain `report/report.html` and
a success manifest with the **current resumed run ID**. Full contains 10 FASTA
members; Light contains none. Final sizes: Full **365,444 bytes**, Light **103,806
bytes**. SHA-256 values for both fresh and resumed archives are in the JSON.

Current remote deliverables:

```text
~/cgat-reads-debug/skill-v1-20261013/runs/gpm_server.tar.gz
~/cgat-reads-debug/skill-v1-20261013/runs/gpm_server.light.tar.gz
~/cgat-reads-debug/skill-v1-20261013/runs/gpm_server/report/report.html
```

Negative checks used separate workspaces:

- Missing reference FASTA: exit **2**, explicit missing-file error, no delivery.
- `-t 0`: exit **1**, `Invalid --threads value '0'` in `logs/prepare.log`, no delivery.
- Neither emitted `Final delivery packages` or produced Full/Light archives.
- Fixture overwrite/symlink refusal was verified by local unit tests, not by
  corrupting successful remote inputs.

## Pitfalls found and guidance retained

1. **Non-interactive module initialization:** loading GCC/samtools without the
   site's `appdir` failed even though some other modules loaded. Set the verified
   site prerequisite in the task-local environment script; do not assume a partial
   module load means the whole toolchain is ready.
2. **SSH and scheduler authentication differ:** an attempted non-interactive
   `dlogin` requested a password and failed. Subsequent scheduler queries and actual
   `dsub` submission succeeded with available access. No credentials were supplied,
   guessed, or bypassed. Check actual scheduler access and request authentication
   only when needed; do not infer a compute blocker solely from that login attempt.
3. **Executable presence is insufficient:** verify runtime startup and MUMmer
   capabilities rather than relying only on `command -v` or the module version.
4. **Preparation failures have different evidence:** a zero-thread failure is in
   `logs/prepare.log`, before a normal execution status table exists.
5. **Resume is validation, not unconditional skip:** preserve the existing
   workspace/runtime and use the official entrypoint; verify new run provenance
   and current archives rather than accepting stale files.

These decisions are expressed in the portable skill without copying the site's
host/module settings into it.

## Local checks and exclusions

- Skill frontmatter/scaffold validation: passed.
- `test_agent_skill.py`: **6 tests passed** (deterministic bytes/hashes, small
  valid FASTA/gap geometry, non-overwrite, symlink refusal, CLI paths with spaces,
  and standalone operation after copying the complete skill outside the repository).
- Full Server Python discovery: **160 tests passed** in 177.695 seconds before
  the standalone-copy regression was added; the final six helper tests were then
  rerun successfully. This is not a claim of a Full desktop/release quality gate.
- Existing `test_server_run.py`: **6 tests passed**; this is local unit/mock
  evidence for CLI/resume semantics, separate from the two real-tool remote jobs.
  Existing runner `ResourceWarning` messages about unclosed subprocess streams
  were observed; no runner code was changed in this skill-only task.

Not covered: installer creation/update, reads QC/Meryl/Merqury/CRAQ, other clusters
or architectures, real biological accuracy/QV/T2T, interruption at every stage,
App import/FASTA export, native UI/browser rendering, or independent-agent behavior.
The successful completed-workspace resume is not proof of all interruption paths.

## Same-day follow-up: persisted tools location

A separate updated skill copy under `~/cgat-reads-debug/skill-v1-20261013/skills/`
was bound explicitly to the original staged Server source. Resolution from `/`
returned `/share/home/xbzhang26/cgat-reads-debug/skill-v1-20261013/source/server`.
This verifies the new path-binding helper on ARM without relying on shell startup
or the caller's working directory; it is not another biological pipeline run.
The source/skill hashes above remain the **earlier tested snapshot**, not rewritten
hashes of the follow-up skill. See the [follow-up record](agent-skill-v1-140-1.md)
for the current helper policy and real-tool x86/LSF validation.
