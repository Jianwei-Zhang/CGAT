# DEGAP Jobs Export Contracts

## Scenario: gapfiller and telseeker-ctg job export

### 1. Scope / Trigger

- Trigger: final path DEGAP-JOBS export sends frontend job cards through the Tauri `export_degap_jobs` command to backend script generation.
- This is a cross-layer contract: frontend job state, Tauri JSON parsing, backend script generation, and server-side DEGAP `--out` directory layout must agree.

### 2. Signatures

- Tauri command:
  ```rust
  export_degap_jobs(workspaceRoot, projectId, outputDir, settings, jobs)
  ```
- Browser/dev bridge:
  ```text
  POST /api/export-degap-jobs
  { workspaceRoot, projectId, outputDir, settings, jobs }
  ```
- Backend CLI used by the dev bridge:
  ```text
  gpm_next_backend export-degap-jobs <workspace_root> <project_id> <output_dir> --settings-json <json> --jobs-json <json>
  ```
- Shared settings fields include:
  - `degapPath`, `hifiReads`, `ontReads`, `gpmServerPath`, `outRoot`
  - `thread`, `kmerFilter`, `kmerSize`, `kmerNum`, `MaximumExtension*`
  - gapfiller-only depth fields: `filterDepthHifi`, `filterDepthOnt`
  - telseeker fields: `motif`, `work`, `telN`, `telR`, `telMm`
- Optional numeric settings may cross the frontend/backend boundary as `null` or `""`; both mean unset. The backend parser must not attempt to parse either form as an integer/number.
- Job fields:
  - common: `jobType`, `jobId`, `chrName`, `outPath`, `settings`
  - gapfiller: `leftCtg`, `rightCtg`, `flag`, `left`, `right`
  - telseeker-ctg: `endpointCtg`, `endpointEnd`, `endpoint`
- Export manifest:
  ```text
  jobs.tsv
  job_id  chr_name  job_type  ...  script_path  ...
  ```
  `chr_name` is required so repeated exports to the same output directory can replace the exported chromosome's rows while preserving other chromosomes.

### 3. Contracts

- `jobType` defaults to `gapfiller`; `telseeker_ctg` is the only other accepted type.
- Tauri and backend CLI exports must share the backend `parse_degap_export_settings` and `parse_degap_export_jobs` functions. Do not maintain separate frontend, Tauri, and CLI parsers for the same payload fields.
- Browser/dev export must call `/api/export-degap-jobs` instead of reporting `BROWSER_EXPORT_UNAVAILABLE`; the bridge must invoke the backend CLI above and return Tauri-compatible fields: `outputDir`, `manifestPath`, `prepareScriptPath`, and `scripts`.
- `outRoot` is the server-side `Main DEGAP --out` root. The exported prepare script writes to:
  ```text
  Main DEGAP --out/shared_prepare/
  ```
- Frontend export payloads must build an effective settings object before validation:
  - Start from the current global/workspace DEGAP settings.
  - Backfill missing global software fields such as `degapPath` from persisted job settings/baseline settings when reopening a project.
  - Keep the current global `outRoot` as the source of truth when it is set, so every job `--out` remains based on `Main DEGAP --out`.
- Assembly-page DEGAP-JOBS export is scoped to the current final-path chromosome:
  - Resolve the export chromosome with the final-path selection helper, not just `selectedChrName`.
  - In phased views, an active haplotype final path such as `Chr01B` exports only jobs with `job.chrName == "Chr01B"`.
  - Do not export all configured DEGAP jobs from the assembly page.
- Project Export does not export DEGAP-JOBS in the current MVP:
  - No Project Export `DEGAP-JOBS` action.
  - Project Export `All` remains PNG/TSV/log/FASTA only.
- Exported DEGAP-JOBS packages include `prepare_degap_shared.sh` by default. It must be run once before running any `degap_jobs/*.sh` job script.
- The assembly final-path export dialog displays DEGAP-JOBS at task granularity even though the backend call remains one batched `export_degap_jobs` command:
  - `prepare_degap_shared.sh`
  - one visible row per exported DEGAP job
  - `jobs.tsv`
  The completed-output list should include the prepare script, exported job scripts, and manifest paths returned by the backend.
- Exported job script file names should be self-explanatory:
  - Gapfiller: include chromosome, `gapfiller`, side/direction, and involved ctgs.
  - Telseeker-ctg: include chromosome, `telseeker_ctg`, endpoint side, and endpoint ctg.
  The manifest keeps the original `job_id`; script file naming is an export-time presentation/packaging concern.
- Job scripts do not silently run prepare. They check and symlink shared artifacts, or fail with a message telling the user to run `prepare_degap_shared.sh`.
- Re-exporting to an existing DEGAP-JOBS output directory is a chr-scoped update:
  - Read existing `jobs.tsv` rows that have `chr_name`.
  - Replace rows and scripts for the chr names present in the current export payload.
  - Preserve rows and scripts for other chr names.
  - Rewriting `prepare_degap_shared.sh` is allowed because it represents the shared current DEGAP settings.
- Job outputs remain shallow first-level children of `outRoot`, for example:
  ```text
  Main DEGAP --out/
    shared_prepare/
    gapfiller_chr1_gap5_left/
    telseeker_ctg_right_chr8/
  ```
- Normal gapfiller and telseeker-ctg jobs symlink shared `processed_reads`, read indexes, and split directories into their own `--out`.
- Gapfiller jobs with `filterDepthHifi` or `filterDepthOnt` must not symlink shared index/split outputs because depth filtering is job-specific.
- Telseeker-ctg jobs must not pass `filterDepthHifi` or `filterDepthOnt`.
- Telseeker-ctg UI creation is bound to right-clicking the final path endpoint ctgs only. In phased/all mode, use the clicked graph's `chrName`, not the selected chromosome fallback.

### 4. Validation & Error Matrix

- Missing `outRoot` -> backend validation error.
- Missing reads in both `hifiReads` and `ontReads` -> backend validation error.
- Assembly-page export with zero jobs for the current final-path chr -> frontend validation error; it must not fall back to exporting all jobs.
- Export job missing `chrName` -> backend validation error.
- Gapfiller missing `left` or `right` seed -> backend validation error.
- Gapfiller `flag` other than `left` or `right` -> backend validation error.
- Telseeker-ctg missing `endpoint` -> backend validation error.
- Telseeker-ctg `endpointEnd` other than `L` or `R` -> backend validation error.
- Telseeker-ctg with depth filter fields -> backend validation error.
- Missing dev bridge backend executable or failed CLI export -> `/api/export-degap-jobs` returns a dev bridge error; the frontend final-path export dialog should surface the backend error instead of a generic browser-preview unavailable error.
- Backend validation returned through Tauri as `TAURI_INVOKE_ERROR` -> frontend error mapping must classify the backend message first. For example, `maximumExtensionLength is not a valid integer` maps to invalid parameters, not runtime/backend-unavailable.
- If DEGAP-JOBS export validation still fails after effective settings are built, the final-path export dialog must surface the raw backend/frontend validation text, not only the generic invalid-parameters message.
- Existing shared prepare manifest with mismatched reads -> prepare script error.

### 5. Good/Base/Bad Cases

- Good: user runs `prepare_degap_shared.sh`, then runs `degap_jobs/telseeker_ctg_right_Chr8.sh`; the job links shared reads and writes its own `part1.telo.reads`, `telseeker_ctg.jobs`, and `result` under its own `outPath`.
- Good: user exports Chr01 jobs to a directory, then exports Chr02 jobs to the same directory; the final `jobs.tsv` and `degap_jobs/` contain both Chr01 and Chr02 jobs.
- Good: user re-exports Chr01 after removing one Chr01 job; the output directory replaces Chr01 rows/scripts and keeps Chr02 rows/scripts.
- Base: gapfiller without depth filters links shared split outputs and DEGAP skips repeated split work.
- Base: browser/dev preview posts the same payload to `/api/export-degap-jobs`, and the bridge invokes `gpm_next_backend export-degap-jobs` with JSON strings.
- Base: reopening a project where `runtime_settings.degap_workspace_settings_json` contains only reads/server/outRoot still exports jobs by backfilling `degapPath` from persisted job settings, while job `outPath` follows the current global `outRoot`.
- Bad: a telseeker-ctg add button in the task panel creates jobs for the current selected path instead of the right-clicked phased graph.
- Bad: frontend `exportDegapJobs` throws `BROWSER_EXPORT_UNAVAILABLE` before trying the dev bridge, causing the export dialog to show a generic assembly runtime connection error.
- Bad: assembly-page DEGAP export sends every configured DEGAP job while the user is exporting the current chr.
- Bad: backend overwrites `jobs.tsv` with only the latest chr's rows when users export Chr01 and Chr02 to the same directory in separate actions.
- Bad: frontend validates only the current global DEGAP settings and drops persisted job `degapPath`, causing reopened projects to fail with invalid parameters even though the job cards still contain complete settings.
- Bad: gapfiller with depth filtering links shared `hifi_reads.idx` or `hifi_reads_part`, causing DEGAP to skip job-specific filtered reads.

### 6. Tests Required

- Frontend state tests:
  - telseeker-ctg jobs are created only from left/right final path endpoint ctgs.
  - telseeker export payload clears depth filter fields.
  - per-job settings inherit global `outRoot`.
  - export settings backfill missing global software fields from persisted job settings.
- Frontend runtime tests:
  - phased/all mode right-click on endpoint ctg adds a job scoped to the clicked graph's `chrName`.
  - `exportDegapJobs` uses `/api/export-degap-jobs` when Tauri is unavailable and preserves `settings` and `jobs` payloads.
  - `buildDegapExportPayload` succeeds for reopened workspace settings that omit `degapPath` when persisted jobs still carry it.
  - `buildDegapExportPayload` exports only jobs for the current final-path chr.
  - `buildDegapExportPayload` exports only the active phased haplotype final-path chr's jobs.
  - `buildDegapExportPayload` errors when the current final-path chr has no jobs.
  - final-path export errors surface raw non-runtime validation text in the dialog.
  - final-path DEGAP-JOBS export dialog expands the current chromosome jobs into task-level rows and records returned script paths in completed outputs.
- Backend tests:
  - export writes `prepare_degap_shared.sh`.
  - manifest records `chr_name`, `job_type`, and prepare path.
  - re-export to the same output directory replaces current chr rows/scripts and preserves other chr rows/scripts.
  - parser treats optional numeric `null` and `""` as unset for DEGAP export settings.
  - gapfiller scripts link shared artifacts when depth filtering is disabled.
  - telseeker-ctg scripts use `--mode telseeker_ctg`, one `--ctg endpoint.ctg.fa <L|R>`, and no depth filter flags.
  - exported script filenames encode job type, chromosome, direction/side, and ctg names instead of relying only on raw `job_id`.

### 7. Wrong vs Correct

#### Wrong

```text
DEGAP-JOBS panel header -> add telseeker-ctg
```

This loses the user's clicked final path context, especially in phased/all views.

#### Correct

```text
right-click final path endpoint ctg -> add left/right telseeker-ctg
```

The runtime reads `data-final-path-target-chr-name` from the clicked graph and stores the job under that chromosome's task group.

#### Wrong

```text
gapfiller depth-filter job -> symlink shared hifi_reads.idx and hifi_reads_part
```

DEGAP will skip rebuilding job-specific filtered read indexes and split files.

#### Correct

```text
gapfiller depth-filter job -> symlink processed_reads only; build job-local index/split
```

This keeps DEGAP's job-specific `selectRawReads` output isolated while still avoiding repeated raw FASTQ-to-FASTA conversion.

#### Wrong

```text
browser/dev export -> throw BROWSER_EXPORT_UNAVAILABLE
```

This hides the real export path behind the assembly page runtime error message.

#### Correct

```text
browser/dev export -> POST /api/export-degap-jobs -> gpm_next_backend export-degap-jobs
```

The dev bridge and Tauri command both use the backend parser and script generator.

#### Wrong

```text
assembly DEGAP export on Chr02 -> send degap.jobs for Chr01 + Chr02
```

This exports unintended work and makes it impossible to maintain one output directory chromosome-by-chromosome.

#### Correct

```text
assembly DEGAP export on Chr02 -> send only jobs where job.chrName == current final-path chr
backend same-directory export -> replace Chr02 rows/scripts, preserve other chr rows/scripts
```

The output directory can accumulate valid multi-chromosome DEGAP-JOBS packages across separate exports.

#### Wrong

```text
export settings = current workspace settings only
validate before reading persisted jobs
```

This loses software-only settings such as `degapPath` when the workspace settings row stores only reads/server/outRoot.

#### Correct

```text
export settings = current workspace settings + missing fields backfilled from persisted job settings
job --out = current main outRoot when it is set
```

The export payload remains valid after reopening a project, and jobs still inherit the current main DEGAP output root.
