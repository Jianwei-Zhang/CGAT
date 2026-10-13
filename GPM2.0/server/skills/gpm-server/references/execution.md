# Execution and recovery

## Preflight

Set `SERVER` to the verified absolute Server source path; set `WORK` to the
chosen absolute workspace. Keep source, inputs, jobs, logs, and runs separate.
Read `README.md` (or `README_zh.md`) in that source and `run.sh --help` first.
The companion code, not a generic online example, is the command authority.
Record the source revision/hash and the skill's `metadata.skill-version`.

For an installer-managed environment, `bash "$SERVER/install.sh" --check`
is read-only. It checks the managed environment, **not necessarily the current
shell**; activate the environment using the installer's actual printed command.
Do not invent a mamba activation command for a non-interactive job. If installation
is needed and authorized, use `install.sh`, not ad-hoc package upgrades.

For site-managed modules, a failed installer ownership/manager check is not by
itself a reason to reinstall: load the site's verified modules and test the real
commands in the job environment. Record this as module-based validation, not an
installer `READY` result. For the current workflow check:

```bash
python3 --version
for tool in bash python3 samtools minimap2 nucmer delta-filter show-coords zip gzip pigz; do
  command -v "$tool" || exit 1
done
minimap2 --version
samtools --version
nucmer --help
# These MUMmer utilities may print help and return nonzero; inspect their text.
delta-filter -h 2>&1 || true
show-coords -h 2>&1 || true
```

Use the Python version in the companion dependency specification (currently the
3.11 series), not an arbitrary system Python. MUMmer must actually start and expose
`nucmer --batch` and `-t/--threads`, `delta-filter -l`, and `show-coords -r`/`-l`.
An executable's presence or version label alone is insufficient. Default `tar.gz`
needs `pigz`; the current preparation also checks `zip` even for tar delivery.
An explicitly selected `--archive-format zip` does not need `pigz`.

With `--reads`, also verify `meryl`, `merqury.sh`, Merqury's `MERQURY` environment,
read-file integrity, and memory budget. `--reads-qc full` additionally needs `craq`.
Do not silently omit user-provided reads when dependencies fail. Without reads,
reads-based QC is skipped; this does not skip the entire GRT workflow.

Confirm input files are readable/nonempty and really FASTA (or FASTQ for reads),
with nonempty sequence records and unique IDs within each FASTA. Check compressed
file integrity when applicable. Do not modify original inputs to test parsing.
Use content hashes for tiny fixtures/transferred source; budget large production
hashing/scans as real I/O rather than treating them as free preflight work.
Check free disk and requested CPU/memory against the allocation.

## First run

The first `--ds` is the locked primary assembly, not an interchangeable list.
Use explicit unique dataset names if basenames collide. For example, after roles
and resources are agreed (replace paths and budget with the user's choices):

```bash
bash "$SERVER/run.sh" \
  --ref reference /absolute/inputs/reference.fa \
  --ds primary /absolute/inputs/primary.fa \
  --ds support /absolute/inputs/support.fa \
  -t 4 -o "$WORK"
```

Keep optional biological parameters at the agreed values. `-t` is the total compute
thread budget, not a request to run that many concurrent full-size jobs.
Run under Bash `set -euo pipefail` if piping through `tee`; otherwise a successful
`tee` can hide pipeline failure. Capture the real exit code, including on failure.

On a cluster, write a small, inspectable job script with environment loading,
`cd` to the task root, the command, and logs on shared storage. Check authentication
and resource availability before submitting. Use the site's actual scheduler
syntax, queue, CPU/memory mapping, and wall-time controls; this skill contains no
default host, account, queue, or module names. Submit once, record the returned job
ID, and check that job to a terminal state. An existing valid session may suffice;
if authentication really fails, ask the user to authenticate instead of retrying
passwords or bypassing it. Downloads belong where the site permits networking;
compute nodes may be offline.

## Resume

```bash
bash "$SERVER/run.sh" -o "$WORK"
```

Resume in the same verified software environment and within the original resource
budget. Do not supply new inputs or unrelated preparation parameters. The workspace
stores its options, input identities, plan, checkpoints, and a copied runtime in
`.prepare_lib/`; updating the source directory does not update that runtime.
Use a new output directory when inputs/settings change. A supported, explicitly
requested `--max-fill` adjustment is an exception; inspect local help first.
Resuming does not guarantee zero work: the runner validates checkpoints and may
rerun invalidated stages. Do not promise every previous stage will be skipped.

If `.run_all/lock/` exists, inspect owner/job/process state first. A disconnected
SSH session or old-looking timestamp does not prove the owner is dead. Never
remove a lock merely to get past a failure.

## Completion gates

Inspect together:
1. Actual process exit code; for scheduled work also terminal scheduler state.
2. `logs/prepare.log` if preparation failed; otherwise `logs/status.tsv`,
   `logs/run_all.log`, and `.run_all/plan.tsv` for current execution evidence.
3. `report/report.html` and the report's machine-readable provenance. HTML presence
   alone is not success: reports also describe failed/incomplete runs.
4. The runner's **current** `Final delivery packages` summary and both archives.
   Check `tar -tzf` or `unzip -t`, inspect that each contains the finalized `report/`,
   and record `sha256sum`. Full must include sequence FASTA; Light must not.
   Do not extract untrusted archives without checking member paths first.

Tar delivery is normally `<workspace>.tar.gz` and `<workspace>.light.tar.gz` in
its parent directory; ZIP compatibility uses `<workspace>.zip` and
`<workspace>.no_fasta.zip`. Trust the actual run's summary and metadata.
