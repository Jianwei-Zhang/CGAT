# Post-LGZ refinement and numbered workspaces

**English** | [中文](REFINEMENT_zh.md) · [Server manual](README.md)

This guide describes the feature-branch source implementation, not a feature retroactively added to published v2.0.21 archives. The shared environment and all four pinned tools were verified with synthetic inputs on native Linux x86_64 and ARM64. The repository’s `GPM2.0/docs/server-refinement-final-acceptance-20261122.md` records scope and evidence. Use the installer and App built from the matching source; do not overwrite an active installation or update an environment while jobs use it.

## 1. Environment and first run

All four engines use the same **cgat-server** environment. There is no separate DEGAP, quarTeT or LR environment. In the matching source/package:

```bash
SERVER=/path/to/GPM2.0/server
bash "$SERVER/install.sh"
# Activate cgat-server with the command printed by the installer.
bash "$SERVER/install.sh" --check
```

Installation changes dependencies; `--check` only verifies them. Stop affected jobs before an environment update. The installer verifies the pinned source/distribution hashes and recorded compatibility patches; normal analysis does not download tools. Workspace and environment paths must avoid spaces and shell metacharacters because of upstream shell drivers.

```bash
# LGZ followed by the default engine, DEGAP.
bash "$SERVER/run.sh" --ref /data/reference.fa --ds /data/assembly.fa \
  --out /work/cgat_server --threads 32 \
  --hifi /reads/hifi_1.fq.gz /reads/hifi_2.fq.gz --ont /reads/ont.fq.gz

# Without typed reads: LGZ only, with an explicitly unrefined baseline.
bash "$SERVER/run.sh" --ref /data/reference.fa --ds /data/assembly.fa \
  --out /work/lgz_only --threads 32
```

`--hifi` and `--ont` accept multiple files and can be repeated. Supply raw reads; they do not enable the legacy pre-LGZ Meryl/Merqury/CRAQ QC pipeline. Required FASTA conversions are content-bound and do not correct, trim or filter reads. Do not supply one file twice or label it as both technologies. A native engine may still perform its own documented processing, such as TGS-GapCloser's ONT Racon round.

## 2. Append or select refinement

A completed **numbered** LGZ-only workspace can append reads in place:

```bash
bash /work/lgz_only/run_all.sh --hifi /reads/hifi.fq.gz --ont /reads/ont.fq.gz
# Or use the installed launcher with the same output root.
bash "$SERVER/run.sh" --out /work/lgz_only --hifi /reads/hifi.fq.gz
```

Validated completed LGZ/reference results are reused; changing downstream reads/tools does not re-prepare them. Both entrypoints save typed-read/tool settings. Omitting both read flags reuses saved reads. **Supplying either read flag replaces the whole saved selection**: `--hifi new.fq.gz` also clears any saved ONT group; supply both flags to keep both. File order is preserved.

```bash
# Independent branches from the same LGZ result, in the fixed order below.
bash /work/lgz_only/run_all.sh --gapfill-tools degap,tgsgapcloser,quartet,lrgapcloser
# A subset; it need not include DEGAP.
bash /work/lgz_only/run_all.sh --gapfill-tools quartet,lrgapcloser
# Disable refinement only for this invocation; retain saved settings and history.
bash /work/lgz_only/run_all.sh --gapfill-tools none
```

Use exactly the lowercase comma-separated identifiers shown above, without duplicates; `none` must stand alone. Selecting an engine without available typed reads is an error. Omitting the tool flag reuses the saved choice; a new reads-backed task defaults to `degap`. A direct preparation-only `prepare.sh --gapfill-tools none` instead seeds a disabled configuration. There is **no `--final-tool`**: each successful selected engine has its own final result and independent App project, not a hidden winning result.

| Order / identifier | Both technologies supplied | Pinned source/distribution |
| --- | --- | --- |
| `01_degap` / `degap` | One native mixed-input run | DEGAP 2.0, revision `ff4d753511fc8556d77b9a578e064e69fe47ade9` |
| `02_tgsgapcloser` / `tgsgapcloser` | HiFi only; otherwise ONT | TGS-GapCloser `1.2.1`, distribution variant `1.2.1_ml`, build 4; revision `52818b3e464209477baec506ade3240be43b4fa8` |
| `03_quartet` / `quartet` | One GapFiller run consuming both groups | quarTeT `1.3.1`, revision `a44d8c87e3f4bcefaf43dc4134e88b6a21890265` |
| `04_lrgapcloser` / `lrgapcloser` | HiFi only; otherwise ONT | LR_Gapcloser `1.0`, build `pl5321hdfd78af_0`; revision `156381adec01a5c664edbf5df1d866b5c70e82a1` |

With only one technology, each selected engine uses that group. TGS/LR do not silently run two technology-specific jobs. Reports record supplied, consumed and unused inputs. The authoritative platform-specific package hashes, dependency builds, parameters and disclosed wrapper patches are in [`contracts/refinement-tools.lock.json`](contracts/refinement-tools.lock.json); a version label alone is not the pin. The environment definitions cover `linux-64` and `linux-aarch64`; this is not yet a successful native-run claim for either architecture. Engines run sequentially within the saved thread budget, not with four separate full budgets.

CGAT pins DEGAP and explicitly passes its now-matching new upstream GapFiller defaults: k-mer filtering enabled, at most 10 shared left/right attempts per gap, and a 500,000 bp cumulative extension budget (which the last complete attempt may exceed). Other tools use their pinned upstream defaults except for listed overrides. Advanced users can edit the installed Server `tools/gapfill.toml`; the workspace copy syncs automatically without needing a new CLI option, and details live in the config comments.

CGAT explicitly sets the thread budget and I/O for all tools. TGS HiFi also uses `--ne` and `-x asm20`; LR uses `-n 1` instead of the upstream `-n 5`; quarTeT uses `--noplot`.

## 3. Find the actual final result

`--out` is the workspace root, including delivery files:

```text
cgat_server/
  run_all.sh
  01_inputs/                         reference, assemblies, derived inputs
  02_alignments/                     original alignment work
  03_lgz/                            original LGZ stages/evidence/annotations
  04_refinement/
    01_degap/                        other engines use their fixed directory above
      01_inputs/<run>/
      02_jobs/<run>/                 command, status, native-completion receipt
      03_native/<run>/               retained native output, not the final result
      04_accepted/<run>/             accepted patch source sequences
        01_source_evidence/<generation>/  measured reference/annotation evidence
      05_report/<run>/<site>/        portable attempt report
  05_final/
    00_lgz/                          LGZ baseline: refinement_applied=false
    01_degap/                        a verified published refined result
      assembly.fa
      final_path.json
      sources.tsv
      remaining_gaps.tsv
      provenance.json
  06_report/
    report.html                      start here: overview and current comparison
    01_lgz/report.html               original LGZ process
    02_refinement/01_degap/report.html
    03_comparison/<batch>/
  07_delivery/
    00_lgz/cgat_server[.light].tar.gz
    01_degap/cgat_server.degap[.light].tar.gz
  08_refinement_jobs/
    02_manual/
      <batch_sha256>/                project-scoped manual refinement batch & report.html
  .lib/                              workspace-scoped runtime copy (includes .lib/tools/refine.py)
  .runtime/                          locks, checkpoints, metadata, logs, history
    refinement/<tool-dir>/<run>/final/  private, source-reconstructed staging
```

Brackets denote two files, not literal filenames; `--archive-format zip` uses `.zip`. Each selected tool uses the same fixed directory under `04_refinement`, `05_final`, `06_report/02_refinement` and `07_delivery`, even if it is the only tool selected. There are no legacy root `data/`, `grt/`, `report/` or `logs/` shadow trees in the numbered workspace. App package internals still use their protocol's `data/` and `metadata/` paths; do not rename those inside archives.

A tool directory alone is not proof of current success. Follow the current overview and its committed, content-bound publication receipt. Failed new attempts retain diagnostics and do not erase an older successful publication or label it as the new result. One tool's failure does not prevent other successful tools or the LGZ baseline being delivered; the overall invocation returns nonzero.

The final assembly is rebuilt from accepted source edits, not copied from a native whole chromosome or relabeled LGZ FASTA. Valid partial/joint/reverse/overlap edits retain their source lineage; ambiguous or out-of-bounds proposals remain unaccepted with reasons. Zero accepted edits is possible and must be distinguished from native failure. Structural/source validation does **not** establish biological accuracy. Unchanged source-coordinate evidence is retained. New accepted patch sources now receive independent reference alignments and tel/cen scans against the original prepared reference and frozen library, without rerunning LGZ or gap filling. Their measurements live under `04_accepted/<run>/01_source_evidence/<generation>/`; reports and both App modes carry the same evidence. `no_hit`, `disabled`, `no_rules` and `no_chr_library` are distinct states. `metadata/refinement/source_intervals.tsv` and `final_annotations.tsv` trace real source slices to final coordinates, including reverse/clipped intervals. These are source scans and coordinate projections, not an exhaustive final-genome rescan or a biological accuracy claim.

Gap closure and changes to known flanks are evaluated separately. When an exact,
unique gap-edge anchor distinguishes a bridge from an unsupported change in the
original flank, CGAT admits the bridge and retains the LGZ flank. The gap detail
reports the retained interval and the native difference. If the boundary cannot
be established, CGAT retains the native evidence but does not guess a cut or
publish the inseparable edit. A mismatch to the reference is not itself a reason
to reject an edit.

The pinned DEGAP revision runs one bidirectional job per native gap attempt. CGAT validates the sealed `family-result.json`, checks the candidate against the original flanks and admits only the evidenced junction interval, not the entire candidate. An unresolved job retains its reason and is neither an execution exception nor an App candidate. On upgrade, run the new Server `install.sh` to refresh the tool lock in the same managed environment; no separate DEGAP environment is needed. Old runs remain accessible as history and are not reused as results of the new recipe.

## 4. Reports, App import and recovery

Open `06_report/report.html` for the workflow overview. `01_lgz/` contains the LGZ baseline report, `02_refinement/` contains the numbered tool reports, and `03_comparison/` stores per-batch TSV/JSON. Open a tool or gap from the overview to see which reads were used, whether native work ran or was reused, which edits CGAT accepted, and whether the final results were published. A failed job shows its recorded phase, reason and diagnostic links; zero accepted edits instead mean the LGZ sequence was retained. Copy the entire `06_report/` directory to keep links to LGZ, current published tool reports and comparison tables, or extract an App archive and open `report/report.html`. Failed or unpublished attempts may link to diagnostics under `04_refinement/`, and final files and archives link to sibling `05_final/` and `07_delivery/`. Keep the workspace layout if you need those links as well.

In a tool report, follow **Native job reports and logs → Offline native visualization** (`native_visualization/index.html`). The updated DEGAP overview `Global.report.html` and available bidirectional `family-report.html` pages have managed offline display copies, alongside unchanged hashed HTML-source attachments. The display retains upstream inline JS/SVG, is framed separately from CGAT acceptance, and does not use a CDN. Native work-directory file links are replaced by the allowlisted CGAT diagnostics list. Historical LEFT/RIGHT reports retain their own portability rules. Source binding is visible: `observed_diagnostic` means observed when reporting, **not** sealed proof of native completion. Missing, unsupported or oversized detail views explain their state instead of exposing broken links. The overview's embedded gap data is checked against available native gap diagnostics.

TGS-GapCloser, quarTeT GapFiller and LR_Gapcloser do not generate native HTML in their pinned recipes; their actual logs/fill-detail/AGP diagnostics are retained rather than inventing an upstream visualization. Full and Light keep the same portable report files. Windows offline browser checks covered the batch hierarchy, native graphics and relative links in the extracted Full and Light reports. Report rendering does not establish biological accuracy.

Import one tool's **Full** archive into a new project in a matching new App. Its authoritative Final Path and exported chromosomes represent that tool's accepted result; the `00_lgz` package remains explicitly unrefined. Full includes source FASTA; Light omits it but retains indexes, metadata and path/source lineage, so FASTA export requires the real sequence sources to be ready. Do not import over an existing manually edited project. The refinement package protocol is schema 5 / App Final Path 4; old Apps reject it rather than silently showing the LGZ path. New-App compatibility with older packages is retained.

Manual App `DEGAP-JOBS` is a separate entrypoint. The source collector now stores versioned manual candidate catalogs under `04_refinement/01_degap/06_manual/01_catalog/`, with an authoritative `.runtime/manual_degap/current.json` pointer, leaving original LGZ tables untouched. Matching App source builds resolve the actual Server runtime and content-bound original/refinement/manual seed sources; Full/Light deliveries include `metadata/server_sources.json` identities. A controlled export → Server → original App import preserved the manually edited Final Path. Original manual packages bound to the committed migration inventory can now enter the immutable registry without rerunning native work or their alignments. Unknown prior result ZIPs remain protected: preserve them and collect from a fresh folder containing the unchanged original `jobs.tsv` and `degap_jobs/` receipts, not a newly exported token. Do not treat these protocol checks as full manual-workflow acceptance.

### Project-scoped manual refinement (`refine.py`, current source)

In addition to the legacy `DEGAP-JOBS` script bundle (labeled **Legacy DEGAP-JOBS (scripts)** in the App), the current feature-branch source adds a project-scoped **Refinement Tasks** path between the matching Desktop App and the matching Server workspace:

1. **App export (Assembly → Export Refinement Tasks):** In Assembly, queue one or more Final Path **Gap** loci (single-selecting **one** tool per gap among `degap` [default], `lrgapcloser`, `tgsgapcloser`, or `quartet`) and/or **Left/Right Telomere** endpoints (fixed to `DEGAP TelSeeker (telseeker_ctg)` with telomere motif) across chromosomes in the current project. Export `refinement_tasks.zip` using either **Current Chr** (only queued loci on the active chromosome) or **All Queued** (all queued loci registered in this project, never scanning unselected loci or crossing projects). New tasks send a single tool per job (existing multi-tool archives remain read-compatible). Verified project reads are inherited by default (without exposing private Server paths in the App UI), or may be explicitly overridden or cleared; empty reads remain exportable.
2. **Server execution:** Copy `refinement_tasks.zip` into the matching Server workspace and run `python .lib/tools/refine.py refinement_tasks.zip` (or the installed `~/bin/refine.py`, which delegates to the workspace runtime). Add `--hifi <files...>` / `--ont <files...>` when overriding or supplying reads on Server, or `--help` to inspect options. Results are written under `08_refinement_jobs/02_manual/<batch_sha256>/`, including `refinement_results.zip`, `summary.json`, and `report.html`, and the manual section is merged into `06_report/report.html` without touching automatic `05_final/` deliveries.
3. **Report honesty & privacy:** Shareable HTML reports omit private Server read paths (retaining read technology and SHA-256 digests) and distinguish `Pending App import` (`等待导回 App`) from `No patch to import` (`无可导回补丁`). Manual batches are never marked imported without an App receipt.
4. **App import, provenance, and undo/switch status:** The Project page **Refinement** card (placed between **Datasets** and **Pseudomolecule Preview**) loads imported batches via `list_manual_refinement_results` and imports `refinement_results.zip` directly via `import_manual_refinement_results` (flushing pending Final Path edits first and reloading authoritative Assembly/Preview data after import, without creating or assigning tracks). Accepted segments carry a lightweight **Refined** marker on the Final Path graph/table (with full provenance in tooltips and the Final Path Log contribution table). Locus-level undo and candidate switching are wired to `undo_manual_refinement_locus` / `switch_manual_refinement_locus` (no local simulation; backend verification enforces revision and boundary rules). Unit coverage for the Server CLI and report generator lives in `GPM2.0/server/tests/test_refine.py`.

Updated App exports select a separate `shared_prepare.family-v1/` cache for the bundled family runtime. It records the original reads and converter by hash and does not adopt an older unverified FASTA/index cache. If an older exported script points to that cache, keep its results; re-export with the updated App into a fresh job output directory for a new native run. Existing candidate packages can still be collected/imported under their original rules.

After a stopped/failed invocation, rerun the same launcher. Verified complete results are reused. A sealed complete native run can be readmitted after an admission/report/publication failure without rerunning the engine. Report-only or serializer-only changes refresh reports/archives without replacing unchanged final sequence files.

Internal recovery boundaries:

- **DEGAP:** restore sealed terminal bidirectional jobs through the native scheduler after checking the gap definition, inputs, family manifest and artifacts. Preprocessing/detection run fresh; incomplete extension rounds are not adopted.
- **quarTeT:** restore a verified per-input PAF, including an explicit empty alignment; later inputs still run through native processing.
- **TGS:** restore completed minimap2/Racon command outputs across native chunks/rounds. Scaffold/candidate preparation and integration run fresh; native done tags are never restored.
- **LR:** restore a completed iteration-processing FASTA **and** its `info_filter2` evidence. Preprocessing and the first index run fresh; native gap detection still decides early stop. A bare FASTA or failed background child is not completion proof.

Each retry uses fresh native directories. Original producers and replay are recorded under `02_jobs/<run>/native_units/` and `native_substeps.json`; this is not arbitrary old-folder resume. Retained partial files alone are never a completion receipt. Do not delete checkpoints or remove locks to force reuse.

```bash
# Read-only progress; this does not cancel a job.
tail -F /work/cgat_server/.runtime/logs/progress.log
python3 "$SERVER/tools/view_run_log.py" --server-dir /work/cgat_server --detailed --follow
# After the old job is stopped, change the budget through run.sh, not run_all.sh.
bash "$SERVER/run.sh" --out /work/cgat_server --threads 64
```

## 5. Explicit migration of a completed old workspace

Unmarked legacy layouts require explicit migration before refinement; do not overwrite them with `prepare.sh` or create symlink aliases to pretend they are numbered. Physical migration requires a **completed, validated original LGZ baseline**. For unfinished work, a separate content-reviewed original-engine continuation is available below: only reviewed engine bytes are accepted, completed work is validated rather than reinterpreted by the new engine, and migration needs a second approval.

Back up the workspace and ensure no active **or queued** task can write it on any node. Use the **new installed Server**, not the old embedded runtime:

```bash
python3 -B "$SERVER/tools/migrate_workspace.py" --server-dir /work/old_server --preview
# Review approval_sha256, physical moves, command replacements and added runtime.
# Set APPROVAL to the exact approval_sha256 printed by the reviewed preview.
APPROVAL=replace_with_reviewed_approval_sha256
python3 -B "$SERVER/tools/migrate_workspace.py" --server-dir /work/old_server \
  --apply --approve "$APPROVAL" --confirm-idle
bash /work/old_server/run_all.sh --hifi /reads/hifi.fq.gz --ont /reads/ont.fq.gz
```

Preview is read-only. `--confirm-idle` records your scheduler/all-node check; it does not perform one. Changed inventory invalidates the approval. Migration preserves the original scientific proof and freezes the completed LGZ engine boundary; it does not manufacture newer-engine checkpoints. Changing LGZ scientific parameters after such a migration requires a new workspace, while reads/tool settings remain adjustable.

An interrupted migration blocks normal launches. Use the same source version to recover the recorded transaction, selecting **one** operation:

```bash
python3 -B "$SERVER/tools/migrate_workspace.py" --server-dir /work/old_server --resume --confirm-idle
# Alternative: roll back only still-owned, unchanged migration outputs.
python3 -B "$SERVER/tools/migrate_workspace.py" --server-dir /work/old_server --rollback --confirm-idle
```

Changed user data or unknown/live lock owners are not overwritten. Preserve the journal/backups and diagnose a refusal instead of deleting workspace metadata. The reviewed x86_64 legacy workspace passed continuation, interrupted migration and refinement append checks. The separate native ARM64 checks cover the current engines, not unknown historical runtimes.

### Unfinished LGZ work

The original physical layout and installed engine remain in place until LGZ
finishes. The currently reviewed registry supports the pre-numbered source
`f2ceafb0`; matching is by the complete installed runtime content, **not** a
claimed version. An unknown/modified engine is refused without upgrading it.
Saved/generated root bindings must still refer to this workspace; stale paths
into another project are refused, not silently rebased or executed.

```bash
python3 -B "$SERVER/tools/migrate_workspace.py" --server-dir /work/old_server \
  --preview-lgz-continuation
# Review the original engine, scientific prefix, validated checkpoints and digest.
# Confirm no active OR queued writer on any node before continuing.
python3 -B "$SERVER/tools/migrate_workspace.py" --server-dir /work/old_server \
  --continue-lgz --approve <continuation_approval_sha256> --confirm-idle
# Success returns a NEW completed-migration preview and its approval digest.
python3 -B "$SERVER/tools/migrate_workspace.py" --server-dir /work/old_server \
  --apply --approve <new_migration_approval_sha256> --confirm-idle
```

Only the original prefix through evidence finalization runs; old DEGAP/package
units do not. The persisted plan, scientific command bytes, original runtime and
environment are not replaced during continuation. Valid outer checkpoints use
their original validator; a completed q0/donor/q-stage cache miss stops before
invalidation instead of silently rerunning it. Each attempt keeps approval,
cache events and status under `.run_all/legacy_continuation/`. On failure, inspect
the original logs and request a **fresh** continuation preview before retrying;
do not remove checkpoints or bypass the cache fence. These are controlled-script
checks, not yet real-native or scheduler-termination acceptance.
