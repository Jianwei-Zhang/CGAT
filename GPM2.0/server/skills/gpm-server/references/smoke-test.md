# Synthetic workflow smoke test

Use only when the user asks to test operation rather than scientific results.
No real datasets, downloads, reads QC, telomere/centromere claims, or desktop UI
acceptance are needed. This baseline exercises real alignment/GRT/report/packaging
on two small chromosomes and two assemblies; it is not a benchmark.

## Prepare the test

After the main skill's host/environment/resource checks, choose a dedicated task
root. Keep `source/`, `inputs/`, `jobs/`, `runs/`, `logs/`, and `reports/` beneath it.
Do not reuse a production workspace. Copy the complete companion Server source,
not just entrypoint scripts; verify the source archive's SHA-256 before use.

Set `SKILL` to the actual skill directory, `SERVER` to the staged Server source,
and `TASK` to the dedicated task root. Generate deterministic local input:

```bash
python3 "$SKILL/scripts/make_smoke_inputs.py" --out "$TASK/inputs/tiny"
```

The generator refuses an existing destination. It writes 120,000 bases per FASTA:
reference, primary with two 200-base internal N gaps, and complete support.
`manifest.json` records seed, purpose, roles and hashes. The sequences are synthetic;
never interpret their repair/QV metrics as biological validation.

## Execute with real tools

Default starting budget: 4 threads on one compute node, a site-appropriate small
memory allocation, and a 15-minute execution cap. Adjust only from evidence and
within authorization. With a cluster, put this command in its scheduler job script;
use a task-local timeout if the scheduler has no suitable wall-time option:

```bash
bash "$SERVER/run.sh" \
  --ref reference "$TASK/inputs/tiny/reference.fa" \
  --ds primary "$TASK/inputs/tiny/primary.fa" \
  --ds support "$TASK/inputs/tiny/support.fa" \
  -t 4 -o "$TASK/runs/gpm_server"
```

Do not use fake executables for the remote smoke test. Declare that reads-based QC
is untested rather than fabricating reads or lowering biological thresholds.
Follow execution.md completion gates, then run a second scheduled command:

```bash
bash "$SERVER/run.sh" -o "$TASK/runs/gpm_server"
```

Verify the new run ID, checkpoint reuse/recomputation decisions, terminal state,
and finalized packages again. A successful post-completion resume is not evidence
that every possible interrupted stage can recover.

## Negative checks and evidence

In separate throwaway workspaces, check a missing FASTA and an invalid/zero thread
budget fail nonzero without a final-delivery claim. Never corrupt the successful
workspace or its inputs for these checks. Verify existing fixture output cannot
be overwritten by the generator. Unit tests may cover these safeguards; label
unit/mock evidence separately from remote real-tool evidence.

Record source/skill/fixture hashes, job IDs, allocation, durations, process exit
codes, stage counts/status, report/archive inspection, encountered problems and
corrective changes. Retain small logs and a durable validation note, not generated
sequence data or large archives in Git. State whether this was a maintainer following
the skill or an independent fresh-agent evaluation; do not conflate them.
