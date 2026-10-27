# Step2 cross-GAP origin recovery (2026-10-27)

## Diagnosis and regression scope

Two failed-workspace read-only diagnostics exposed the same defect in
`arbitrate_structural_candidates`: an accepted edit registered its own GAP and
later absorbed GAPs, but omitted already-visited GAPs covered to its left.
The untouched-origin pass could then overwrite the accepted replacement origin.

- Shape A: `CM054994.1`, accepted interval 16,400,305–16,518,606 (1-based,
  inclusive); the selected GAP was 16,432,220–16,432,319 and the omitted earlier
  GAP was 16,400,305–16,400,404.
- Shape B: `CP144746.1`, accepted interval 46,202,455–46,309,689; the selected
  GAP was 46,215,982–46,216,081. The later GAP 46,237,040–46,237,139 was
  registered, but the earlier GAP 46,202,455–46,202,554 was omitted.

`tests/test_step2_structural_coverage.py` checks both exact interval shapes and
small replayable normal-gap/gapless variants. It checks forward/backward
supersession, primary-first identity, chromosome isolation, occupied edits,
partial-GAP rejection, origin ambiguity and coordinate shifts from emitted
replacement lengths. Step3 already rejects edits spanning another GAP; that
policy remains unchanged and is covered by the new tests. Shared correction
writing now rejects incomplete/duplicate coverage before creating output paths.

These are source, synthetic replay and operator-provided diagnostic results,
not complete reruns of either customer genome. Do not declare either customer
workflow successful before its actual resumed analysis and final validation pass.

## Code-only recovery

Use a freshly extracted official Server source archive, not an extraction over
an installed tools directory or workspace. Verify its published SHA-256 first.
Stop all affected jobs, including jobs on other cluster nodes; Linux process and
workspace-lock checks cannot enumerate idle queued jobs on other hosts.

The extracted archive includes `tools/update_workspace_runtime.py`. This updater
supports the independent Step2/Step3 schema-2 runtime. It intentionally refuses
legacy combined-stage workspaces; it does not migrate or regenerate them.

```bash
# Edit these to the confirmed extracted source, installation and workspace.
SOURCE=/path/to/fresh/GPM_Server
TOOLS=/path/to/installed/GPM_Server
WORKSPACE=/path/to/project/gpm_server
REV=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["git_revision"])' "$SOURCE/SOURCE.json")

# Dry-run: verifies the source manifest, target schema, paths and idle state.
python3 -B "$SOURCE/tools/update_workspace_runtime.py" \
  --source-root "$SOURCE" --tools-root "$TOOLS" \
  --workspace "$WORKSPACE" --expected-revision "$REV"

# Apply only after a successful dry-run and the cross-node job check.
python3 -B "$SOURCE/tools/update_workspace_runtime.py" \
  --source-root "$SOURCE" --tools-root "$TOOLS" \
  --workspace "$WORKSPACE" --expected-revision "$REV" --apply
```

The updater replaces manifested installed-tool files and the required
`.prepare_lib/tools` runtime files, including its `SOURCE.json` provenance.
It preserves generated `run_all.sh`/stage scripts, `.prepare_lib/lib`, custom
unlisted installation files, skill binding, input data, logs, results, checkpoints,
raw-alignment caches and the dependency environment. It never runs `install.sh`
or starts analysis. Locks, SHA-256/mode checks, backups and rollback are mandatory.

Update each affected workspace explicitly. With a shared tools installation,
perform all dry-runs first; apply one workspace at a time and stop on any failure.
Each successful update prints `status: updated`, `analysis_started: false`,
`engine_sha256` and its own backup path under `.run_all/runtime-update-*`.
Keep these JSON outputs. If reverting several updates, roll them back in reverse
application order because each backup also records the shared tools state.

```bash
python3 -B "$SOURCE/tools/update_workspace_runtime.py" \
  --rollback /exact/backup/path/printed/by/the/updater
```

Do not delete caches or rewrite event registries. After updating, resume only
through the original execution environment/scheduler and existing `run_all.sh`.
The engine fingerprint invalidates derived repair decisions as needed; raw
alignment reuse is checked independently. Do not run a cluster-scale analysis
on a login node merely to test the fix.
