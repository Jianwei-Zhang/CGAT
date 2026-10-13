# GPM Server skill v1: SSH 140-1 and saved-tools-location validation

Date: **2026-10-13**, Asia/Shanghai. Historical test evidence, not a portable host
configuration. See [machine-readable evidence](agent-skill-v1-140-1.json) for input,
source, skill and archive hashes. The earlier ARM/Donau test is documented in
[the SSH 180 record](agent-skill-v1-180.md).

## Scope and target identity

The user corrected the requested target from the old external-login entry to the
previous `ssh 211` endpoint, then named that endpoint **`ssh 140-1`**:
`211.69.141.142:22333`, login host `mn02.hpc.hzau`, x86_64. WSL and Windows aliases
were updated without changing the existing dedicated identity. Both could log in.
The separate `140-2` alias retains `211.69.141.140:33322` and its prior default
identity selection; non-interactive authentication there did not succeed. No skill
workflow ran on `140-2`, and no keys were replaced/deleted or backups created.
Private SSH configuration and keys are not part of this repository change.

The remote `/etc/motd` explicitly directs program tests to LSF's `interactive`
queue. No Donau settings or SSH-180-only skills were applied to this host.
Both real-tool runs used an interactive allocation on `gpu02`, x86_64; despite
that node's name, **no GPU resource was requested or used by this CPU workflow**.

## Isolated source and environment

Task root: `~/gpm-skill-smoke/20261013-140-1/`, with separate `source/`, `skills/`,
`inputs/`, `jobs/`, `runs/`, `logs/`, and `reports/` directories. Existing research
data and environments were not modified. The complete source archive was verified
before extraction:

- Base revision: `6c1e255cb292bb07d3184785d9682f828c2bf9dc`.
- Archive SHA-256: `8cf5aeb29da23dc2dc1d41bd028b8116026fc6933ac77fede48a89f1dec6a28a`.
- Contents: base Server plus saved-location guidance/helper and installer-summary
  refinements. No biological pipeline implementation or threshold was changed.
- Existing environment: `micromamba run -n GRT`, Python 3.11.15, minimap2 2.31,
  samtools 1.23.1, and working MUMmer `--batch` / `--threads` support. Commands were
  checked again inside the compute allocation, not merely found on the login node.
- No package installation, environment update, or shell startup edit was performed.
  This is existing-environment runtime evidence, not installer `READY` acceptance.

## Persisted Server tools location

A **separate copy of the skill**, outside the Server source tree, was placed at:

```text
~/gpm-skill-smoke/20261013-140-1/skills/gpm-server/
```

It was explicitly bound once using `scripts/server_tools_path.sh --set` to:

```text
/public/home/xbzhang/gpm-skill-smoke/20261013-140-1/source/server
```

The helper then resolved that same absolute directory with the current working
directory set to `/`. Both scheduled runs obtained `SERVER` from the saved
`server-tools.path` through the helper, rather than searching directories or
relying on the skill's parent location. The job recorded this resolved location;
acceptance asserted that it matched the binding and the staged source.
All non-binding skill file hashes were compared with the local working copy.
The JSON's `server-tools.path` hash is host-specific because this installed copy
contains the explicit absolute path; the distributed default remains `../..`.

The same standalone-skill binding was installed and resolved from `/` on SSH 180:

```text
Skill: ~/cgat-reads-debug/skill-v1-20261013/skills/gpm-server/
Tools: /share/home/xbzhang26/cgat-reads-debug/skill-v1-20261013/source/server
```

No biological workflow was rerun on 180 for this path-only follow-up. Its earlier
successful pipeline runs remain separately identified in the earlier record.

## Allocation pitfall and corrected execution

The first submission requested 4 CPUs and was rejected **before a job was created**:
`Queue does not have enough per-user job slots. Job not submitted.`
`bqueues -l interactive` showed a per-user slot limit of **2**, and `bjobs` showed no
unfinished jobs for this user in that queue. Free node CPUs were not sufficient
proof that a 4-slot request was allowed.

The corrected submission used 2 CPUs, within the original maximum of 4, with a
15-minute scheduler wall-time limit and a 900-second process timeout:

```bash
bsub -q interactive -n 2 -R 'span[hosts=1]' -W 00:15 \
  -J gpm-skill-v1-fresh -Is \
  /public/home/xbzhang/bin/micromamba run -n GRT \
  timeout --signal=TERM --kill-after=30s 900 \
  bash /public/home/xbzhang/gpm-skill-smoke/20261013-140-1/jobs/run-smoke.sh fresh
```

The job script read the persisted Server location and executed the smoke recipe
with `-t 2`. The separate resume submission used the same allocation and environment,
passing `resume` to that script, which ran `bash "$SERVER/run.sh" -o "$WORK"`.
The default queue memory policy was retained; no larger-memory override was requested.
The portable guidance now explicitly checks per-user slot limits before submission.

## Results

The deterministic fixture is unchanged from the 180 test: two 60,000-base chromosomes
per FASTA, reference + primary with two 200-base N gaps + complete support, no reads.
This is an operational smoke test, not scientific validation.

| Check | Fresh | Resume |
| --- | --- | --- |
| Job ID | `75764477` | `75765716` |
| LSF terminal state / process exit | `DONE` / `0` | `DONE` / `0` |
| Job-script start (UTC+8) | 2026-10-13T11:25:35+0800 | 2026-10-13T13:37:56+0800 |
| Job-script end (UTC+8) | 2026-10-13T11:25:43+0800 | 2026-10-13T13:38:08+0800 |
| Successful stages | 12 / 12 | 12 / 12 |
| Outer `SKIP_VALID` events | 0 | 5 |
| Report | success, no errors | success, new run ID, no errors |

The interval between fresh and resume reflects separate submissions/user pauses,
not a multi-hour computation. Both archive pairs were read to the end of the gzip
stream for CRC/trailer checks. Their tar members and embedded report manifests
were inspected without extraction. Full has 10 FASTA members; Light has none.
Each report has the corresponding current run ID, not a stale prior run's ID.
The final resumed Full/Light sizes are **364,693** /
**103,891** bytes; all SHA-256 values are in the JSON.

Negative cases in separate workspaces also passed: missing FASTA exited 2, zero
threads exited 1, neither produced archives nor claimed finalized delivery.
The successful inputs/workspace were not corrupted for these checks.

## Location-failure and installation policy

The final skill instructs the agent to show a failed saved path and ask the user
for the existing tools directory first. If the user does not know, it asks whether
they authorize a bounded search or a new installation, and confirms scope before
either. It never silently scans the machine, chooses another version, reinstalls,
or edits `.bashrc`/`.zshrc` as a path-recovery action.

The installer success summary now prints the absolute tools path, skill entrypoint
and binding command. It does not add Server-path exports to shell startup files.
The pre-existing micromamba bootstrap can still initialize Bash when no manager
exists; this separate side effect is explicitly disclosed in the skill and requires
authorization. It was not exercised on either remote host in this validation.

## Local verification

- Full Server Python discovery: **168 tests passed** in 167.638 seconds, including
  all **13** skill-helper tests (fixture and saved-location behavior).
- `tests/gpm_server/env_test.sh`: passed, including install/check output and
  unchanged startup files/location binding when using an existing manager.
- Skill frontmatter validation and Bash syntax checks: passed.
- The full suite still emits pre-existing runner `ResourceWarning` messages about
  unclosed subprocess streams; no unrelated runner changes were made.

## Verification limits

The maintainer agent followed the skill; no independent fresh-agent evaluation or
subagent was used. Not covered: actual installer creation/update, reads QC,
Meryl/Merqury/CRAQ, real biological accuracy/QV/T2T, App import/export, browser/native
visual acceptance, or every interrupted-stage recovery path. A completed-workspace
resume is not evidence for all possible interruptions. No task ran on `140-2`.
