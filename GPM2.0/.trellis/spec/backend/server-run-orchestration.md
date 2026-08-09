# Server Run Orchestration Contract

## Scope

Applies when changing `server/prepare.sh`, the generated `gpm_server/run_all.sh`, outer Server checkpoints, run locks, or operator-facing Server execution logs.

This contract is an execution layer around the existing GRT v2 computation. It must not change the GRT biological recipe, q transitions, donor identities, evidence semantics, package schema, or Final Path schema.

## Public Entry Point

The public initial execution command remains:

```bash
bash gpm_server/run_all.sh
```

The generated shell entrypoint invokes:

```text
python3 gpm_server/.prepare_lib/tools/run_all_runner.py --server-dir <gpm_server>
```

The Server-private plan is `gpm_server/.run_all/plan.tsv` with this exact header:

```text
unit_id<TAB>command_relpath<TAB>detail_log_relpath
```

Command and detail-log paths are workspace-relative, must not contain `..` or Windows separators, and remain outside the App delivery projection.

The prepared thread value from `server/prepare.sh -t/--threads` remains authoritative. Runtime thread override, stage selectors, parallel jobs, and scheduler integration are not part of the current contract.

## Canonical Unit Plan

Top-level unit IDs and dependencies are stable:

| Unit | Dependencies |
|------|--------------|
| `ref:<dataset>` | none; every initial dataset has one unit |
| `assign` | every `ref:<dataset>` |
| `grt_prepare` | `assign` |
| `grt_step1` | `grt_prepare` |
| `grt_step23` | `grt_step1` |
| `grt_telomere_finalize` | `grt_step23` |
| `chr:<chromosome>` | `grt_telomere_finalize` |
| `finalize_evidence` | every `chr:<chromosome>` |
| `package_full` | `finalize_evidence` |
| `package_light` | `package_full` |

Chromosome-local subunit IDs are:

- `chr:<chromosome>:self:<dataset>`;
- `chr:<chromosome>:pair:<left-dataset>:<right-dataset>`;
- `chr:<chromosome>:telomere_scan`;
- `chr:<chromosome>:centromere_scan`.

Dataset and chromosome components use the same `[A-Za-z0-9._-]+` name domain accepted by `prepare.sh`. Pair direction is preserved because target/query direction is part of the command identity.

The generated runner preserves fail-fast serial behavior. Unit IDs are internal observability and checkpoint keys; they do not expose `--from`, `--until`, or `--stage` CLI behavior.

## State Model

Allowed operational states are:

- `pending`: no execution attempt has started in the current workspace state;
- `running`: the unit has an active owner and no validated terminal result yet;
- `success`: the latest attempt completed and its authoritative checkpoint/output validation passed;
- `failed`: the command or post-command validation failed;
- `interrupted`: execution ended before a validated terminal result;
- `stale`: a recorded success no longer matches current inputs, tools, parameters, command identity, or outputs.

State is an operator-facing index, not checkpoint authority. A `success` row never permits reuse by itself. Every candidate reuse must revalidate the authoritative checkpoint and its referenced output hashes.

On startup, a `running` state whose recorded owner is no longer live is treated as interrupted. Catchable `INT` and `TERM` signals record the active unit as interrupted and return a non-zero exit. `SIGKILL` is recovered by stale-owner detection on the next invocation.

## Checkpoint Authority

Existing GRT checkpoints and caches remain authoritative for:

- q0/D0/Dtel preparation;
- Step1 rounds and filter;
- Step2 and Step3;
- telomere recovery and q4 finalization;
- GRT supplemental display evidence where an internal cache already exists.

Do not duplicate or weaken those validators in the outer runner. The runner maps their validated outcome into operational status.

New outer checkpoints cover non-GRT units. Each fingerprint includes:

- checkpoint schema version and execution engine version;
- exact input artifact hashes;
- resolved tool identity;
- complete relevant parameters;
- command/script identity using a workspace-relative path plus exact bytes;
- exact output artifact hashes.

Checkpoint writes use a temporary file and atomic replacement. They occur only after command exit success and output validation. Missing, malformed, partial, or hash-mismatched output invalidates reuse even if a status row or checkpoint says success.

Changing the prepared thread value, an input, a tool identity, a parameter, or command bytes changes the affected fingerprint. Downstream output may be reused only when its own full fingerprint still validates; status alone never carries validity forward.

## PAF Validation

An empty PAF is a valid biological result when the producing command exited successfully. It records zero alignment rows and must not be rejected merely because no hit exists.

Every non-empty, non-comment record must:

- contain at least the 12 mandatory PAF fields;
- have non-empty query and target names;
- use integer mandatory length, coordinate, match, alignment-length, and MAPQ fields;
- use `+` or `-` strand;
- have 0-based half-open query/target intervals contained by positive sequence lengths;
- have residue matches no greater than alignment length;
- have MAPQ in `0..255`.

## Workspace Lock

Only one orchestrated run may own a `gpm_server/` workspace at a time. A second invocation fails before modifying stage state or outputs and reports the active owner.

The lock is Server runtime state. It must not enter full/no-FASTA App delivery projections or add-package payloads. A copied stale lock must not become an active owner in another workspace; ownership validation includes the current workspace and live process identity.

## Log Contract

Runtime logs live only under:

```text
gpm_server/logs/
|-- run_all.log
+-- status.tsv
```

`run_all.log` is append-only. A normal successful workspace has one invocation section. A later recovery invocation appends a new separator and events to the same file; no automatic history directory or log rotation is required.

Each invocation separator records timestamp, run ID, workspace, prepared thread count, unit count, and whether the invocation is fresh or resuming.

Required event codes are:

- `START`;
- `SKIP_VALID` or `CACHE_HIT`;
- `RESUME`;
- `SUCCESS`;
- `FAILED`;
- `INTERRUPTED`;
- `STALE`.

Every event contains an ISO-8601 timestamp, run ID, unit ID, unit position/total, and message. Terminal events include elapsed time. Failure events include exit code when available, the existing detail-log path, and the normal whole-pipeline rerun command.

The runner streams child output to the terminal and `logs/run_all.log` while preserving the child exit code. Existing detailed logs under `runs/**` and `grt/cache/**` remain in place; the run log links to them instead of relocating or duplicating raw evidence artifacts.

`status.tsv` is atomically replaced and describes the current unit states. It is for monitoring only and must not be used as a substitute for checkpoint/output validation.

Logs and status remain Server-side and are excluded from both App delivery packages.

## Error Matrix

| Condition | Required behavior |
|-----------|-------------------|
| Concurrent runner owns the workspace | Fail before mutation and report owner |
| Status says success but output hash changed | Emit `STALE` and recompute |
| Checkpoint is missing or malformed | Recompute the unit |
| Tool exits non-zero | Emit `FAILED`, stop downstream execution |
| Catchable signal arrives | Terminate child, emit `INTERRUPTED`, exit non-zero |
| Previous owner was killed | Mark stale `running` state interrupted, then revalidate |
| PAF is empty after successful command | Accept zero records and checkpoint it |
| PAF has malformed mandatory fields | Fail validation and do not checkpoint |
| Package build fails | Preserve the previous valid archive |

## Tests Required

- Stable unit plan and dependency tests.
- Invalid/duplicate name tests.
- Empty, valid, and malformed PAF tests.
- Deterministic fake-command controls for invocation counts, selected delay, selected failure, and empty output.
- Interruption tests at reference, GRT, and chromosome-local boundaries.
- Output corruption and fingerprint invalidation tests.
- Concurrent invocation rejection test.
- Live `run_all.log` event test and atomic `status.tsv` test.
- Package allowlist tests proving logs, locks, statuses, and outer checkpoints are absent.
- Existing GRT Server validator, package projection, add-dataset/add-ctg, and Server-to-App E2E regressions.

## Good, Base, and Bad Cases

- Good: an interrupted run starts again with the same prepared configuration; valid reference and GRT checkpoints emit `SKIP_VALID`/`CACHE_HIT`, the incomplete unit runs, and both packages are produced.
- Base: a fresh run has no checkpoints, executes every canonical unit in order, appends one invocation section to `logs/run_all.log`, and ends with every unit successful.
- Bad: `status.tsv` says a reference unit succeeded but `result.paf` was truncated. The runner must emit `STALE` and recompute it; skipping from status alone is forbidden.
- Bad: a second process enters the same workspace while an owner is live. It must fail before running or rewriting any unit.

## Wrong vs Correct

### Wrong

```text
status=success -> skip command -> package possibly corrupted output
```

### Correct

```text
status=success -> validate authoritative checkpoint + current output hashes
  -> SKIP_VALID when exact
  -> STALE and recompute when any identity differs
```
