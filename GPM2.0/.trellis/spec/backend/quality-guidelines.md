# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

The canonical checks are repository-owned and platform-specific. The Windows
host runs `scripts/quality-gate-windows.ps1` for the frontend and both Rust
crates. Linux CI runs `scripts/quality-gate-server.sh` for line endings, shell,
Python, and the GRT server-to-app E2E. WSL may set
`GPM_SKIP_GRT_SERVER_APP_E2E=1` only for an explicitly incomplete local server
run; Rust and Tauri validation remain authoritative on Windows.

Quality rules protect existing scenario contracts. A structural refactor is
behavior-preserving unless its PRD explicitly versions a public contract.

---

## Forbidden Patterns

- Do not add `#[allow(clippy::...)]`, broad exception swallowing, or shell
  `|| true` to make a required quality gate green.
- Do not copy a domain rule into CLI, Tauri, Python, and shell adapters. Define
  one owner and make transports delegate or validate against the same fixture.
- Do not add an unversioned SQLite schema mutation; follow
  [Database Guidelines](./database-guidelines.md).
- Do not parse TSV/JSON/FASTA with delimiter shortcuts that bypass the active
  contract validators.
- Do not mix unrelated mechanical formatting/line-ending normalization with a
  semantic change.

## Structure Review Triggers

Request a responsibility review, not an automatic split, when any condition is
met:

| Trigger | Review question |
| --- | --- |
| Production file > 800 lines or > 30 top-level functions/types | Does it contain independently changing domains, adapters, or persistence? |
| Adapter > 500 lines or > 15 commands/routes | Can registration, decoding, mapping, and domain dispatch be separated? |
| Test file > 1,500 lines or > 40 tests | Can feature fixtures and contracts be independently located and run? |
| Python/shell entrypoint > 500 lines | Which algorithms or generated programs should be importable/lintable modules? |
| Embedded generated program > 100 lines | Can it become a real template with direct syntax/tests? |

Exceptions require one cohesive responsibility, one owner, clear section/index
navigation, and focused tests. Size alone never justifies `part1`/`part2` files.
The audit findings for `importer.rs` (F5), `grt_package.rs` (F7), GRT Python
stages (F8), and `prepare.sh` (F9) all trigger review because size coincides with
mixed responsibilities and weak test seams.

### Audit Rule Calibration

| Finding | Rule decision |
| --- | --- |
| F5 `importer.rs` | Triggered by production size/function count and distinct initial/add-dataset/add-ctg validation, transaction, promotion, and rollback owners; split by import operation plus shared package/persistence services. |
| F6 `db.rs` schema evolution | Fails the versioned-migration rule because ordered history and newer-version rejection are absent; migrate through the database-guideline contract before adding schema growth. |
| F7 `grt_package.rs` | Triggered by contract parsing, persistence, initialization, view, and trace query change axes; preserve one shared contract model while separating those services. |
| F8 GRT Python stages | Shared I/O/hash/interval/checkpoint/metadata semantics now live in `server/tools/grt_core/`, and stage entrypoints have no executable-stage import chain. `grt_step23.py` and `grt_telomere_finalize.py` remain cohesive algorithm owners pending a versioned multi-module checkpoint engine identity. |
| F9 `prepare.sh` | Completed: full add-dataset/add-ctg programs are static templates, assignment and staging programs are Python tools, and generated incremental scripts share `.prepare_lib/lib/incremental_common.sh`. |

---

## Recommended and Required Patterns

### GRT Contract TSV Decoding

GRT metadata is written by Python `csv.DictWriter` with a tab delimiter. Rust consumers must parse these files with a delimiter-aware reader that implements standard double-quote escaping. Do not use `line.split('\t')` for GRT contract tables: JSON cells are emitted with outer quotes and doubled inner quotes, and a literal tab may legally occur inside a quoted field.

Decode the TSV layer first, then perform JSON and semantic validation. Preserve `GRT_IMPORT_INVALID_TSV` for malformed UTF-8, quoted records, headers, widths, or row counts. Regression coverage must include a Python-style quoted JSON cell such as `"[""support""]"` and an inconsistent-width record.

### Assembly Placement Anchor Weighting

When computing `assembly_ctg.anchor_start` from reference alignment hits, use the same weighted-anchor contract in every producer:

- `server/prepare.sh` generates `metadata/chr_assignments.tsv`.
- `app/backend/src/auto_placement.rs::collect_source_chr_candidates` computes software-side auto assignment.
- A qualified hit contributes `candidate_anchor` plus `block_length` weight.
- The final `anchor_start` is the upper weighted median of candidate anchors ordered by coordinate.

Do not use an unweighted median or raw hit count for placement anchors. Short repetitive hits must not have the same voting power as long alignment blocks. Keep hit filtering and chromosome support coverage separate from anchor weighting: merged query coverage still determines `support_bp` and `support_percent`; hit `block_length` determines anchor vote weight.

Required regression test point: include a contig with multiple short anchors and one long alignment block, and assert the chosen `anchor_start` follows the long block.

### Assembly Source Orientation Weighting

When Server assignment producers write `metadata/chr_assignments.tsv`, determine `source_orientation` from the same qualified ds-vs-ref hits used for that dataset/contig/chromosome candidate:

- sum `block_length` independently for `+` and `-` PAF strands;
- choose `-` only when its sum is strictly greater;
- choose `+` for positive-majority and ties;
- persist `orientation_source=ref_alignment`;
- keep source coordinates increasing for both orientations.

This rule applies to initial `server/prepare.sh` assignment and incremental Server assignment producers such as `server/tools/add_ctg_stage.py`. GRT q0 construction must consume the persisted assignment orientation rather than recomputing it from PAF, because the assignment row is the package-wide immutable baseline.

Required regression points: cover a reverse-majority assignment, a deterministic tie, and a q0 test proving the persisted baseline wins even if a downstream PAF re-read would infer another strand.

### Server Delivery TSV Parsing in Shell Scripts

When shell packaging scripts need a specific column from `metadata/*.tsv`, do not parse rows with `IFS=$'\t' read -r col1 col2 ...` when earlier columns may be empty. Bash treats tab as IFS whitespace and collapses consecutive tabs, which shifts fields left. For example, an empty `assembler_version` in `metadata/datasets.tsv` can make `fai_relpath` look like `fasta_relpath`.

Use a tab-aware column extractor instead:

```bash
while IFS= read -r fasta_relpath; do
  zip_args+=(-x "${bundle_name}/${fasta_relpath}")
done < <(awk -F '\t' 'NR > 1 && $4 != "" { print $4 }' "${server_dir}/metadata/datasets.tsv")
```

Required regression test point: full-package zip arguments must exclude original `.fa` source payloads but must not exclude their `.fa.fai` index files when `assembler_version` is empty.

### Server Delivery FASTA Index Freshness

After `server/prepare.sh` or its generated `add_dataset.sh` materializes a FASTA into the server output tree, always regenerate the colocated `.fai` from that exact FASTA. Do not keep an existing `${fasta}.fai` just because it is present.

This matters when an output directory is reused across prepare runs: `cp -f` or gzip decompression can replace `data/datasets/<name>.fa` while a stale `data/datasets/<name>.fa.fai` remains. Later partition metadata is generated from the current FASTA, but the desktop importer builds `source_seq` rows from `.fai`; a stale index can make `metadata/source_seq_locator.tsv` reference sequences that do not exist in the imported catalog.

Required pattern:

```bash
ensure_fai() {
  local fasta="$1"
  rm -f "${fasta}.fai"
  samtools faidx "$fasta"
}
```

Required regression test point: pre-create stale reference and dataset `.fai` files in the output directory, rerun prepare with different FASTA content, and assert the resulting `.fai` names/lengths match the current FASTA.

### Server Reference Segment Scanner

`server/prepare.sh` must generate `metadata/reference_segments.tsv` with the
bundled `server/tools/reference_segments.py` scanner. Do not restore an awk
per-base `substr()` loop: its runtime and memory depend strongly on whichever
awk implementation appears first on `PATH`.

The scanner contract is:

- fixed-size binary input chunks; an unwrapped chromosome line must not be
  loaded as one Python line or record;
- FASTA whitespace is ignored and `N`/`n` runs of at least 100 bp split the
  non-N segments;
- segment coordinates are 1-based closed and segment order resets per FASTA
  record;
- N-runs continue across FASTA line and binary chunk boundaries;
- sequence before the first header and empty record names are errors;
- TSV uses LF and replaces the destination atomically only after a successful
  complete scan;
- `reference_segments.py` is copied to generated
  `gpm_server/.prepare_lib/tools/` with the other runtime tools.

Required regression points: CRLF, lowercase N, short/exact-threshold N-runs,
empty/all-N records, no final newline, a multi-megabase unwrapped record,
cross-chunk gaps, and preservation of an existing output after failed input.

### Server Tool Bundle Entrypoints

#### 1. Scope / Trigger
- Applies when changing server-side prepare, generated server scripts, package scripts, or final-path FASTA export helpers.
- Trigger: any change that alters where users upload server tooling, how prepare is invoked, or how generated `gpm_server/` helpers locate metadata and FASTA payloads.

#### 2. Signatures
- Prepare command: `bash server/prepare.sh --ref <reference_name> <reference.fa> --ds <dataset_name> <dataset.fa> [--ds <dataset_name> <dataset.fa> ...] [-o|--out <gpm_server_output_dir>] [other prepare options]`
- Server-side final-path export command: `bash server/export_final_path_fasta.sh --tsv <final_path_export.tsv> --gpm_server <prepared_gpm_server_dir> -o <output.fa> [--ds <dataset_name> ...]`
- Generated final-path export command: `bash gpm_server/export_final_path_fasta.sh --tsv <final_path_export.tsv> -o <output.fa> [--ds <dataset_name> ...]`
- Initial execution command: `bash gpm_server/run_all.sh`; after all compute and evidence stages it automatically runs the full and light package scripts.
- Standalone re-package commands: `bash gpm_server/package_full_zip.sh` and `bash gpm_server/package_light_no_fasta_zip.sh`.

#### 3. Contracts
- `server/` is the uploadable server tool bundle. Do not require users to upload multiple root-level helper scripts.
- Root-level `gpm_server_prepare.sh` and `gpm_server_export_final_path_fasta.sh` compatibility entrypoints are not part of the public contract.
- `server/prepare.sh` defaults `-o/--out` to `./gpm_server` under the current working directory, not under the `server/` tool directory.
- `server/prepare.sh` may read templates from `server/templates/`; generated scripts must remain runnable after the generated `gpm_server/` directory is copied.
- Static templates such as `add_dataset.sh` and `add_ctg.sh` are copied
  byte-for-byte. Configured templates use `server/tools/render_template.py`;
  every placeholder and value name must exactly match an explicit allowlist,
  values are shell-escaped, missing/unexpected variables fail, and unresolved
  placeholders never reach the generated workspace.
- When extracting a program from an unquoted shell heredoc, compare and execute
  the generated result rather than assuming the source body is byte-equivalent:
  the outer shell consumes one escaping layer for backslashes, dollar signs,
  and command substitutions before the nested program runs.
- `server/prepare.sh` must copy runtime dependencies into `gpm_server/.prepare_lib/`.
- Shared shell/library logic belongs under `server/lib/` and should be copied to `gpm_server/.prepare_lib/lib/`.
- Standalone Python tools belong under `server/tools/` and should be copied to `gpm_server/.prepare_lib/tools/`.
- Generated `gpm_server/export_final_path_fasta.sh` must default `--gpm_server` to its own directory when `metadata/datasets.tsv` is present.
- Generated `gpm_server/run_all.sh` must invoke `package_full_zip.sh` and then `package_light_no_fasta_zip.sh` after GRT evidence finalization.
- Generated shell entrypoints are invoked through explicit `bash` commands;
  Unix executable bits are a best-effort convenience, not a correctness
  requirement. A failed `chmod +x` on DrvFS, a network mount, or a bind mount
  must not abort prepare after the script file was written successfully.
- Python generated-script writers must not require `Path.chmod(0o755)` for
  scripts that every caller launches through `bash`.
- Each package script must build a fresh temporary zip and atomically replace the final archive only after success; never update the prior final archive in place.
- Template scripts must keep LF line endings and pass `bash -n`.

#### 4. Validation & Error Matrix
| Condition | Expected behavior |
|-----------|-------------------|
| `server/templates/package_full_zip.sh` is missing during prepare | Fail before writing an incomplete generated package script. |
| `server/templates/package_light_no_fasta_zip.sh` is missing during prepare | Fail before writing an incomplete generated package script. |
| `server/templates/export_final_path_fasta.sh` is missing during prepare | Fail before writing an incomplete generated export helper. |
| `server/templates/add_dataset.sh` or `add_ctg.sh` is missing during prepare | Fail before writing an incomplete incremental helper. |
| An assignment template placeholder/value is missing or unexpected | Fail before publishing `assign_chr_groups.sh`; never leave unresolved input. |
| `server/lib/` is missing during prepare | Fail before writing generated helpers that depend on runtime libraries. |
| `server/tools/` is missing during prepare | Fail before writing generated helpers that depend on runtime tools. |
| `server/export_final_path_fasta.sh` is called without `--gpm_server` outside a generated `gpm_server/` directory | Fail with `Missing --gpm_server`. |
| Generated `gpm_server/export_final_path_fasta.sh` is called without `--gpm_server` inside a valid generated server directory | Use its own directory as the server root. |

#### 5. Good/Base/Bad Cases
- Good: upload `server/`, run `bash server/prepare.sh ... -o /work/gpm_server`, then run `bash /work/gpm_server/export_final_path_fasta.sh --tsv path.tsv -o path.fa`.
- Base: run `bash server/export_final_path_fasta.sh --tsv path.tsv --gpm_server /work/gpm_server -o path.fa` from the uploaded tool directory.
- Bad: document `bash ./gpm_server_prepare.sh ...` as a supported command after the server tool bundle migration.
- Bad: make the default prepare output land under `server/gpm_server/` when the user runs `bash server/prepare.sh` from the upload parent directory.

#### 6. Tests Required
- Shell syntax checks for `server/prepare.sh`, `server/export_final_path_fasta.sh`, and every `server/templates/*.sh`.
- Prepare regression asserting the default output root is the current working directory's `gpm_server/`.
- Prepare regression asserting generated `gpm_server/export_final_path_fasta.sh`, `package_full_zip.sh`, and `package_light_no_fasta_zip.sh` exist.
- Prepare regression asserting the package scripts are the final two fail-fast stages in generated `run_all.sh`.
- End-to-end Server shell regression asserting one `run_all.sh` invocation creates both delivery archives and that the light archive excludes all `.fa` / `.fasta` payloads.
- Prepare regression asserting generated `gpm_server/.prepare_lib/lib/` and `gpm_server/.prepare_lib/tools/` contain required runtime files.
- Prepare regression asserting static add templates and generated add scripts
  are byte-identical, generated assignment placeholders are fully resolved, and
  all source/generated shell programs pass `bash -n` with LF endings.
- Prepare regression with a failing `chmod` command asserting workspace
  generation succeeds and non-executable scripts pass syntax checks and run
  through explicit `bash`.
- Final-path export regression asserting generated `gpm_server/export_final_path_fasta.sh` works without `--gpm_server`.

#### 7. Wrong vs Correct
#### Wrong
```bash
bash ./gpm_server_prepare.sh --ref ref ref.fa --ds ds ds.fa
```

#### Correct
```bash
bash server/prepare.sh --ref ref ref.fa --ds ds ds.fa
```

### Add Dataset Incremental Import Contract

#### 1. Scope / Trigger
- Applies when changing server add-dataset packages or backend add-package import paths:
  - `server/prepare.sh` generated `add_dataset.sh`
  - `app/backend/src/importer.rs`
  - `app/backend/src/alignment_cache.rs`
  - `app/backend/src/project_initializer.rs`
  - `app/backend/src/auto_orientation.rs`
- Trigger: any change that creates, validates, extracts, merges, indexes, bootstraps, or orients an `add_ds*.zip` payload.

#### 2. Signatures
- Server command: `bash gpm_server/add_dataset.sh --ds <dataset_name> <dataset_fasta_path> [-o|--out <zip_path>]`
- Backend entry point: `import_add_dataset_package_with_hooks(zip_path, workspace_root, project_id, on_progress, should_cancel)`
- Add manifest path: `add_package/manifest.tsv`
- Add payload root: `gpm_server/`
- Manifest fields:
  - `package_type=add_dataset`
  - `dataset_name`
  - `reference_name`
  - `sequence_layout=partitioned`
  - `preassigned_chr=true`
  - `chr_assignment_min_coverage_percent`
  - `minimap_preset`
  - `skip_self`
  - `self_alignment_available`
  - `tel_enabled`
  - `cen_enabled`

#### 3. Contracts
- An add zip is not a full delivery zip. It contains only a manifest plus append-only payload for one new dataset.
- After `add_dataset.sh` succeeds, the server-side `gpm_server/` directory is the new complete server state; a later `package_full_zip.sh` must produce a full package containing the added dataset.
- Backend add import must validate the manifest against the existing workspace before merging files.
- Add import must reject duplicate dataset names and mismatched reference, score, layout, `skip_self`, minimap preset, tel, or cen settings.
- Add import must use an allowlist for payload files and reject absolute paths, `..`, Windows separators, and unexpected files.
- Add import must be append-only for catalog tables and alignment caches. It must not call full-import sync functions that clear `source_seq_locator`, tel/cen marks, ref hits, or pairwise runs for existing datasets.
- File merge, catalog append, alignment indexing, assembly append, and scoped orientation must be rollback-safe as one user-visible operation. If a later step fails, restore `project.sqlite` and affected payload files.
- When `skip_self=false`, the add payload must include the new dataset self PAF. When `skip_self=true`, it must not require or advertise self alignment.
- The add payload must include chr-local pairwise PAFs between the new dataset and every existing project dataset required by the server package.
- Assembly append must only create rows for source sequences from the new dataset in the selected project.
- Scoped orientation must only process the added dataset's assembly ctgs and must not mutate existing dataset ctgs. In scoped runs, manual ctgs are skipped before any mutation.

#### 4. Validation & Error Matrix
| Condition | Expected behavior |
|-----------|-------------------|
| `package_type` is not `add_dataset` | Reject before extracting into the workspace. |
| `dataset_name` already exists | Reject before file merge. |
| Manifest reference or score differs from workspace | Reject before file merge. |
| Manifest `skip_self` conflicts with workspace `prepare_options.tsv` | Reject before file merge. |
| `self_alignment_available == skip_self` | Reject as an inconsistent manifest. |
| Payload path is absolute, contains `..`, or contains `\` | Reject before file merge. |
| Payload contains an unexpected file | Reject before file merge. |
| `skip_self=false` and new dataset self PAF is missing | Reject before file merge. |
| Required chr-local pairwise PAF is missing | Reject before file merge. |
| Failure after file merge or during DB append/orientation | Roll back copied/appended files and restore `project.sqlite`. |

#### 5. Good/Base/Bad Cases
```text
Good: add_ds4.zip has add_package/manifest.tsv plus gpm_server metadata rows and ds4-only payload.
Base: workspace already has ds_a; add import appends ds4 rows, ds4 PAF indexes, ds4 assembly rows, and ds4 scoped orientation.
Bad: add_ds4.zip contains a copied full gpm_server payload with ds_a metadata/data/runs.
Bad: add import appends metadata files before DB work and leaves them behind after a later SQLite failure.
Bad: scoped orientation loops over all project ctgs and clears or flips existing datasets.
```

#### 6. Tests Required
- Server shell tests:
  - Assert `add_dataset.sh` reads `metadata/prepare_options.tsv`.
  - Assert add zip is append-only and does not include base dataset payload.
  - Assert updated `gpm_server/` can still create a full package containing the new dataset.
- Backend importer tests:
  - Successful add import appends dataset, source seq, locators, chr assignments, ref hits, pairwise indexes, project support link, assembly rows, and scoped orientation.
  - Invalid manifests and unsafe payload paths are rejected before merge.
  - Missing self PAF and missing chr-local pairwise PAF are rejected.
  - Failure after file merge rolls back DB and filesystem changes.
- Orientation tests:
  - Scoped orientation flips only the requested dataset and preserves existing ctg `orient`/`ref_orient`.
  - Scoped orientation does not clear manual ctgs before the manual-skip guard.

#### 7. Wrong vs Correct
#### Wrong
Reusing full bundle import for add packages, or copying add payload files before all later DB/index/orientation steps can be rolled back.

#### Correct
Use an add-package-specific validation and append path with payload allowlisting, append-only DB operations, incremental alignment indexing, append-only assembly bootstrap, scoped orientation, and explicit rollback snapshots.

### Add Ctg Incremental Package Contract

#### 1. Scope / Trigger
- Applies when changing derived-ctg server packages or future desktop add-ctg import paths:
  - `server/prepare.sh` generated `add_ctg.sh`
  - `server/tools/add_ctg_stage.py`
  - `server/tools/add_ctg_package.py`
  - future backend/frontend add-ctg import wiring.
- Trigger: any change that creates, validates, extracts, merges, indexes, bootstraps, or displays an `add_<ctg>.zip` payload.

#### 2. Signatures
- Server command: `bash gpm_server/add_ctg.sh --ctg <new_ctg_name> --chr <chr_name> --track <dataset_name> -i <single_sequence_fasta> [-o|--out <zip_path>] [--source <free_text>]`
- Add manifest path: `add_ctg/manifest.tsv`
- Add payload root: `gpm_server/`
- Manifest fields:
  - `package_type=add_ctg`
  - `ctg_name`
  - `derived_dataset=derived_ctg`
  - `target_chr`
  - `target_track`
  - `source`
  - `reference_name`
  - `alignment_engine` and engine-specific prepare options
  - `skip_self`
  - `self_alignment_scope`
  - `cross_alignment_scope`
  - `sequence_layout=partitioned`
  - `preassigned_chr=true`
  - `contains_fasta=true`

#### 3. Contracts
- One add-ctg package adds exactly one ctg, and the ctg is bound to one existing dataset-backed target track on one chromosome.
- Direct phased-track targeting is out of scope. The frontend may show the derived ctg in track-specific UI, but the server package binds it with `target_track=<dataset_name>`.
- The input FASTA must be plain text, not `.fa.gz`, and must contain exactly one sequence. The staged FASTA header is rewritten to `--ctg`.
- The derived FASTA namespace is `derived_ctg`. Per-ctg source payloads live under `data/derived_ctgs/<ctg>.fa`; chr-local display FASTA lives under `runs/chr_<chr>/datasets/derived_ctg.fa`.
- `source_seq_n_regions.tsv` must include N-runs scanned from the rewritten derived sequence so derived ctgs behave like normal ctgs for downstream N-aware features.
- After `add_ctg.sh` succeeds, the server-side `gpm_server/` directory is the new complete server state; a later full package must include the derived ctg.
- The add zip is append-only payload, not a full delivery zip. It must include only the derived metadata rows, derived FASTA payload, add-ctg reference alignment, and the required chr-group dataset-backed pairwise alignments.
- If `skip_self=false`, generate a single-direction pairwise PAF for every existing dataset-backed track with members on the target chr, using `<dataset>_vs_<ctg>` run names. Do not generate reciprocal `new_ctg` vs `<dataset>`.
- Subview/junction pairwise lookup must treat `derived_ctg` as an internal dataset namespace. When one selected member belongs to `derived_ctg`, resolve chr-local pairwise PAFs from `runs/chr_<chr>/add_ctg/<normal_dataset>_vs_<derived_ctg_name>/result.paf`, not from `<normal_dataset>_vs_derived_ctg`.
- `--source` is free text and may be empty. Empty source should be displayed by the frontend as a generic derived source label.

#### 4. Validation & Error Matrix
| Condition | Expected behavior |
|-----------|-------------------|
| `--ctg`, `--chr`, `--track`, or `-i` is missing | Fail before staging. |
| `-i` ends with `.gz` or `.fa.gz` | Reject and ask for a plain single-sequence FASTA. |
| `-i` has zero or multiple FASTA records | Reject and report the observed record count. |
| `--ctg` already exists in source locator, chr assignments, or derived metadata | Reject with `ctg name already exists` and tell the user to choose a different `--ctg`. |
| `--track` is unknown or equals `derived_ctg` | Reject before staging. |
| `--track` has no members on `--chr` | Reject before staging. |
| The prepared server has not run `run_all.sh` | Reject with missing metadata guidance before staging. |
| Reference alignment has no qualified hit for the new ctg on `--chr` | Reject before appending metadata. |
| `--source` contains tabs or newlines | Reject before writing metadata. |

#### 5. Good/Base/Bad Cases
```text
Good: add_Chr01_gap3_filled.zip has add_ctg/manifest.tsv plus derived_ctg-only metadata, FASTA, ref PAF, and every required chr-group dataset-vs-derived pairwise PAF.
Base: source is empty; frontend displays the derived ctg with a generic [derived] tag.
Bad: add package contains base hifiasm metadata/data/runs rows unrelated to the new ctg.
Bad: direct add into haplotype A/B track in v1.
Bad: package uses the original FASTA header instead of rewriting it to --ctg.
```

#### 6. Tests Required
- Server shell test for generated `add_ctg.sh` existence, one-sequence FASTA staging, header rewrite, N-region scan, metadata append, package manifest, and duplicate-name rejection.
- Server shell test that `add_ctg.sh` inherits alignment engine options from `metadata/prepare_options.tsv`.
- Server shell test that `skip_self=false` packages the single-direction pairwise PAFs for every dataset-backed track with members on the target chr.
- Future backend importer tests must reject manifest/reference/aligner/option mismatches before file merge and must allowlist add-ctg payload paths.
- Backend subview/junction tests must assert normal dataset ctgs can draw hits against imported `derived_ctg` members from the add-ctg pairwise PAF path in either selected order.
- Future frontend tests must assert add-new-ds style progress UI, track mismatch rejection, source tag rendering, and refresh of the target track's member/card list.

#### 7. Wrong vs Correct
#### Wrong
```bash
bash gpm_server/add_ctg.sh --ctg gap3 --chr Chr01 --track Chr01A -i final.fa
```

#### Correct
```bash
bash gpm_server/add_ctg.sh --ctg Chr01_gap3_filled --chr Chr01 --track hifiasm -i final.fa --source gapfiller
```

### Server-Owned Dataset Track Member Order Contract

#### 1. Scope / Trigger
- Applies to initial delivery, generated `add_dataset.sh`, generated `add_ctg.sh`, desktop import, project assembly bootstrap, and dataset-track rendering.
- Trigger: any change to chr assignment metadata, derived track membership, package filtering, `assembly_ctg.chr_order`, or main-track layout ordering.

#### 2. Signatures
- Server calculator: `python3 .prepare_lib/tools/track_member_order.py --server-dir <gpm_server>`.
- Required metadata: `metadata/track_member_orders.tsv`.
- Exact columns: `target_track`, `target_chr`, `member_dataset`, `member_ctg`, `member_order`.
- SQLite catalog table: `imported_track_member_order(target_dataset_id, reference_chr_id, source_seq_id, member_order)`.
- Desktop destination: `assembly_ctg.chr_order`.

#### 3. Contracts
- The Server owns dataset-track member order. The PC imports and renders that order; it must not recalculate domain order from `anchor_start`, TSV row order, FASTA order, or SQLite ids.
- Calculate each `(target_track, target_chr)` independently. Sort by ascending `anchor_start`; equal anchors preserve stable source order.
- `anchor_start` is a signed integer estimate, not a clamped reference coordinate. Values at or below zero are valid when a contig is estimated to extend left of reference position 1 and must participate in the same numeric sort.
- Initial and new-dataset source order is FASTA order. During add-ctg, existing equal-anchor members retain their prior authoritative order and the new equal-anchor member follows them.
- Normal members use `target_track=member_dataset`. A `derived_ctg` member uses the actual dataset-backed `target_track` and `target_chr` from `metadata/track_members.tsv`.
- `member_order` is 1-based, unique, and contiguous inside each target group.
- Initial/full packages carry the complete file. An add-dataset package carries all groups for the new dataset. An add-ctg package carries the complete replacement snapshot for its affected `(target_track, target_chr)` group, including old and new members.
- Add-ctg import must insert the new assembly ctg and update present old members from the snapshot in one SQLite transaction. Workspace TSV merge replaces the affected group instead of appending duplicate rows.
- Pixel positions, lanes, label collision, and other visual geometry remain frontend-owned and may derive from the already ordered input list.

#### 4. Validation & Error Matrix
| Condition | Expected behavior |
|-----------|-------------------|
| `track_member_orders.tsv` is missing or has the wrong header | Reject before workspace merge/DB mutation and tell the user to regenerate with current Server scripts. |
| `chr_assignments.tsv.anchor_start` is not an integer | Reject order generation and identify the invalid row. |
| A field is empty or `member_order < 1` | Reject the package. |
| A group has duplicate members, duplicate orders, or non-contiguous orders | Reject the package. |
| An order member has no matching chr assignment | Reject the package. |
| A normal assignment is ordered under another target track | Reject the package. |
| Add-dataset metadata contains another target track | Reject before merge. |
| Add-ctg snapshot is not exactly the existing catalog group plus the new member | Reject before merge. |
| Add-ctg package and PC workspace originate from different Server states | Reject as an incomplete/mismatched snapshot. |

#### 5. Good/Base/Bad Cases
```text
Good: ds_a/Chr01 has orders 1..N, including physical member derived_ctg:gap1 under target_track=ds_a.
Base: two new-dataset ctgs share one anchor; their FASTA order is retained.
Base: a new derived ctg shares an anchor with old members; old authoritative order is retained and the new member follows.
Base: anchors -500, 0, and 300 are valid and sort in that numeric order.
Bad: add-ctg package contains only the new member order row.
Bad: order generation rejects or clamps a non-positive anchor estimate.
Bad: frontend sorts the imported ctg list by anchor_start before rendering.
Bad: importer uses reference_chr.chr_order as the ctg member order.
```

#### 6. Tests Required
- Server unit tests assert signed anchor ordering (negative, zero, positive), FASTA-stable ties, existing-order-stable add-ctg ties, `derived_ctg` target mapping, contiguous 1-based output, and LF output.
- Packaging tests assert add-dataset filters by `target_track` and add-ctg includes the full affected group.
- Backend tests assert initial/add-dataset orders reach `assembly_ctg.chr_order`, add-ctg updates shifted old members atomically, and workspace TSV replacement preserves unrelated groups.
- Backend tests reject legacy initial/add-dataset/add-ctg packages that omit the required metadata and reject malformed/non-contiguous snapshots.
- Frontend tests use input whose anchors disagree with Server order and assert main-track layout and drag-offset rebasing preserve input order.

#### 7. Wrong vs Correct
#### Wrong
```javascript
normalizeCtgs(ctgs); // sorts dataset-track members by anchor on the PC
```

#### Correct
```javascript
normalizeCtgs(ctgs, { preserveInputOrder: true }); // backend already ordered by chr_order
```

### Server Alignment Engine Contract

#### 1. Scope / Trigger
- Applies when changing server prepare alignment command generation, generated `assign_chr_groups.sh`, generated `add_dataset.sh`, add-package manifests, or backend add-package validation.
- Trigger: any change that alters `--aligner`, engine-specific prepare options, `metadata/prepare_options.tsv`, or generated alignment result formats.

#### 2. Signatures
- Prepare command: `bash server/prepare.sh --ref <reference_name> <reference.fa> --ds <dataset_name> <dataset.fa> [--aligner minimap2|blastn|winnowmap] [engine-specific options] [-t|--threads <n>]`.
- Shared prepare option: `--threads/-t`, default `10`.
- Engine-specific options:
  - `--minimap-preset asm10|asm5`, default `asm10`, only valid with `--aligner minimap2`.
  - `--blastn-task blastn|megablast|dc-megablast`, default `blastn`, only valid with `--aligner blastn`.
  - `--blastn-evalue <number>`, default `1e-10`, only valid with `--aligner blastn`.
  - `--winnowmap-preset asm20|asm10|asm5`, default `asm20`, only valid with `--aligner winnowmap`.
  - `--winnowmap-kmer <positive-int>`, default `19`, only valid with `--aligner winnowmap`.
  - `--winnowmap-repeat-fraction <0..1 float>`, default `0.9998`, only valid with `--aligner winnowmap`.

#### 3. Contracts
- All engines must produce standard `result.paf` files at the existing paths consumed by importer/orientation/subview code.
- `blastn` may produce `result.blast6` as an intermediate, but must convert it to `result.paf` before downstream steps run.
- `winnowmap` must generate repetitive k-mer input with `meryl` before running `winnowmap`.
- `metadata/prepare_options.tsv` must persist:
  - `alignment_engine`
  - `threads`
  - `minimap_preset`
  - `blastn_task`, `blastn_evalue`, `blastn_dust`
  - `winnowmap_preset`, `winnowmap_kmer`, `winnowmap_repeat_fraction`
- Generated add-dataset manifests must carry the same alignment engine fields.
- Backend add-package validation must compare `alignment_engine` first, then compare only the effective option set for that engine.

#### 4. Validation & Error Matrix
| Condition | Expected behavior |
|-----------|-------------------|
| `--blastn-*` is passed with `--aligner minimap2` or `winnowmap` | Fail before output generation and name the invalid option plus selected aligner. |
| `--minimap-preset` is passed with `--aligner blastn` or `winnowmap` | Fail before output generation and name the invalid option plus selected aligner. |
| `--winnowmap-*` is passed with `--aligner minimap2` or `blastn` | Fail before output generation and name the invalid option plus selected aligner. |
| Required engine executable is missing | Fail early via `require_cmd` before generated jobs are expected to run. |
| Add package `alignment_engine` differs from workspace prepare options | Reject before payload merge. |
| Add package engine-specific option differs from workspace prepare options | Reject before payload merge. |

#### 5. Good/Base/Bad Cases
- Good: `--aligner blastn` writes `alignment_engine=blastn`, runs `makeblastdb`/`blastn`, converts `result.blast6` to `result.paf`, and add-dataset inherits the same blastn options.
- Base: omitting `--aligner` uses minimap2 with `--minimap-preset asm10` and `--threads 10`.
- Bad: accepting `--aligner blastn --minimap-preset asm5`; that creates misleading metadata and must fail before writing output.
- Bad: teaching the desktop importer to parse BLAST tabular output directly; the server contract is PAF at boundary paths.

#### 6. Tests Required
- Server shell tests for default minimap2 command generation and default `threads=10`.
- Server shell tests for blastn and winnowmap command generation.
- Server shell tests for engine-specific option rejection before output generation.
- Converter test for BLAST outfmt 6 to PAF coordinate/strand conversion.
- Backend importer tests for add-package `alignment_engine` mismatch and engine-specific option mismatch.

#### 7. Wrong vs Correct
#### Wrong
```bash
bash server/prepare.sh --aligner blastn --minimap-preset asm5 --ref ref ref.fa --ds ds ds.fa
```

#### Correct
```bash
bash server/prepare.sh --aligner blastn --ref ref ref.fa --ds ds ds.fa
```

---

## Common Mistakes

- Running one focused test and reporting the whole layer as verified.
- Splitting a large file by line range while shared state and dependencies remain coupled.
- Copying fixture builders between Rust and Python instead of reusing the shared contract fixture.
- Treating a successful process exit as sufficient without validating artifacts, hashes, and rollback state.
- Making a failure quiet through a skip, warning suppression, or catch-all fallback.

## Testing Requirements

- Rust unit tests stay in the owning module and use `tempfile::tempdir` for
  isolated workspaces. Cross-runtime GRT tests reuse
  `tests/fixtures/grt_contract_v2`; do not create a second almost-equivalent
  contract fixture inside one language.
- Python tests use `unittest`, `TemporaryDirectory`, and fake executable tools;
  they assert artifacts, hashes, restart behavior, and error codes rather than
  only stdout prose.
- Shell tests create a temporary workspace, install fake commands through
  `PATH`, clean up with `trap`, and fail on missing required tools. A skip must be
  opt-in, visible, and prohibited in the canonical CI gate.
- A bug fix adds a regression at the lowest owning layer. A cross-layer contract
  change adds producer, consumer, and round-trip/E2E assertions.
- Tests must not mutate repository fixtures or leave trackable `dist/`, `target/`,
  databases, archives, or temporary workspaces.

## Rust Quality Gates

- The GPM2.0 root pins Rust `1.92.0` in `rust-toolchain.toml` with the `rustfmt` and `clippy` components. Do not rely on an unpinned developer toolchain for formatting or lint baselines.
- Backend changes must pass these Windows-host checks from `app/backend`:

```powershell
cargo fmt --all -- --check
cargo clippy --all-targets --locked -- -D warnings
cargo test --locked
```

- Tauri changes must pass the complete Tauri gate below from `app/src-tauri`.
- Resolve new Clippy findings structurally. Do not add `#[allow(clippy::...)]` merely to make a strict gate pass.
- When a formatting baseline is restored, keep the mechanical formatting commit separate from semantic refactors so behavior review remains focused.

### Tauri Quality Gate

The Tauri crate is part of the Rust quality gate. Run `cargo fmt --all -- --check`, `cargo clippy --all-targets --locked --no-default-features -- -D warnings`, and `cargo test --locked --no-default-features` from `app/src-tauri`. Tauri commands with several related inputs must use a deserializable request struct rather than accumulating positional parameters.

## Python and Shell Quality Gates

The canonical Linux command is `bash scripts/quality-gate-server.sh`. Focused
commands during development are:

```bash
python3 -m unittest discover -s server/tests -p 'test_*.py'
find server tests/gpm_server -type f -name '*.sh' -print0 |
  xargs -0 -n1 bash -n
```

Python code uses the standard library unless a declared server dependency is
required, explicit UTF-8/newline handling for contract files, `pathlib.Path`,
and typed/stable contract exceptions. Shell code uses `set -euo pipefail`,
quotes expansions, validates commands before work, and uses LF line endings.

### Bash 4.2 Nounset Compatibility for Optional Arrays

`server/prepare.sh` supports GNU Bash 4.2 and newer. Bash 3.x is outside the
support boundary because the Server scripts use Bash 4 features such as
associative arrays and `mapfile`.

Under Bash 4.2, expanding a declared-but-empty indexed array as
`"${values[@]}"` can fail with `unbound variable` when `set -u` is active.
Whenever an optional array is forwarded to a function or command, branch on
its length and expand it only in the non-empty branch. The empty branch must
omit the optional arguments entirely; do not add an empty-string sentinel and
do not disable nounset.

Wrong:

```bash
write_command "$output" "${optional_inputs[@]}"
```

Correct:

```bash
if [[ "${#optional_inputs[@]}" -gt 0 ]]; then
  write_command "$output" "${optional_inputs[@]}"
else
  write_command "$output"
fi
```

Regression tests must cover empty, one-item, and multi-item inputs. A focused
Server test that needs to validate a specific Bash runtime should accept an
explicit executable through `GPM_TEST_BASH`; its default remains the Bash on
`PATH` so the canonical quality gate has no undeclared runtime dependency.

---

## Code Review Checklist

- [ ] The dependency direction and ownership in `directory-structure.md` remain intact.
- [ ] A size trigger includes a responsibility/test-seam analysis; no mechanical split.
- [ ] Validation and coordinate/data conversion happen exactly once.
- [ ] Multi-row/file operations have an explicit rollback or transaction boundary.
- [ ] Errors preserve stable codes and context across every changed transport.
- [ ] Tests reuse authoritative fixtures and cover good/base/bad plus failure cleanup.
- [ ] Windows Rust/Tauri and applicable Linux Python/shell checks pass.
- [ ] No warning suppression, silent skip, generated artifact, or fixture mutation remains.
