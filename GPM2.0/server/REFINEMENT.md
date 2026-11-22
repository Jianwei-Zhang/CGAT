# Post-LGZ refinement and numbered workspaces

**English** | [中文](REFINEMENT_zh.md) · [Server manual](README.md)

This guide describes the feature-branch source implementation, not a feature retroactively added to published v2.0.21 archives. Four-tool native examples, Linux x86_64/ARM64 environments and the final acceptance matrix are still awaiting consolidated validation. Use the installer and App built from the matching source; do not overwrite an active installation or update an environment while jobs use it.

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
| `01_degap` / `degap` | One native mixed-input run | DEGAP 2.0, revision `0b3c9bc7acc5bd290ad2b23d53cc57815f1c7e75` |
| `02_tgsgapcloser` / `tgsgapcloser` | HiFi only; otherwise ONT | TGS-GapCloser `1.2.1`, distribution variant `1.2.1_ml`, build 4; revision `52818b3e464209477baec506ade3240be43b4fa8` |
| `03_quartet` / `quartet` | One GapFiller run consuming both groups | quarTeT `1.3.1`, revision `a44d8c87e3f4bcefaf43dc4134e88b6a21890265` |
| `04_lrgapcloser` / `lrgapcloser` | HiFi only; otherwise ONT | LR_Gapcloser `1.0`, build `pl5321hdfd78af_0`; revision `156381adec01a5c664edbf5df1d866b5c70e82a1` |

With only one technology, each selected engine uses that group. TGS/LR do not silently run two technology-specific jobs. Reports record supplied, consumed and unused inputs. The authoritative platform-specific package hashes, dependency builds, parameters and disclosed wrapper patches are in [`contracts/refinement-tools.lock.json`](contracts/refinement-tools.lock.json); a version label alone is not the pin. The environment definitions cover `linux-64` and `linux-aarch64`; this is not yet a successful native-run claim for either architecture. Engines run sequentially within the saved thread budget, not with four separate full budgets.

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
  .runtime/                          locks, checkpoints, metadata, logs, history
    refinement/<tool-dir>/<run>/final/  private, source-reconstructed staging
```

Brackets denote two files, not literal filenames; `--archive-format zip` uses `.zip`. Each selected tool uses the same fixed directory under `04_refinement`, `05_final`, `06_report/02_refinement` and `07_delivery`, even if it is the only tool selected. There are no legacy root `data/`, `grt/`, `report/` or `logs/` shadow trees in the numbered workspace. App package internals still use their protocol's `data/` and `metadata/` paths; do not rename those inside archives.

A tool directory alone is not proof of current success. Follow the current overview and its committed, content-bound publication receipt. Failed new attempts retain diagnostics and do not erase an older successful publication or label it as the new result. One tool's failure does not prevent other successful tools or the LGZ baseline being delivered; the overall invocation returns nonzero.

The final assembly is rebuilt from accepted source edits, not copied from a native whole chromosome or relabeled LGZ FASTA. Valid partial/joint/reverse/overlap edits retain their source lineage; ambiguous or out-of-bounds proposals remain unaccepted with reasons. Zero accepted edits is possible and must be distinguished from native failure. Structural/source validation does **not** establish biological accuracy. Unchanged source-coordinate evidence is retained. New accepted patch sources now receive independent reference alignments and tel/cen scans against the original prepared reference and frozen library, without rerunning LGZ or gap filling. Their measurements live under `04_accepted/<run>/01_source_evidence/<generation>/`; reports and both App modes carry the same evidence. `no_hit`, `disabled`, `no_rules` and `no_chr_library` are distinct states. `metadata/refinement/source_intervals.tsv` and `final_annotations.tsv` trace real source slices to final coordinates, including reverse/clipped intervals. These are source scans and coordinate projections, not an exhaustive final-genome rescan or a biological accuracy claim.

## 4. Reports, App import and recovery

Open `06_report/report.html`, then the per-tool report and its job/native diagnostic links. Reports distinguish every original gap from native candidates, accepted edits, remaining N and terminal gaps, and disclose different consumed inputs. They do not select a best tool or invent accuracy/peak-memory measurements. Copy the entire portable report directory to retain relative links; HTML source from upstream is currently a safe text attachment, not a verified offline interactive upstream visualization.

Import one tool's **Full** archive into a new project in a matching new App. Its authoritative Final Path and exported chromosomes represent that tool's accepted result; the `00_lgz` package remains explicitly unrefined. Full includes source FASTA; Light omits it but retains indexes, metadata and path/source lineage, so FASTA export requires the real sequence sources to be ready. Do not import over an existing manually edited project. The refinement package protocol is schema 5 / App Final Path 4; old Apps reject it rather than silently showing the LGZ path. New-App compatibility with older packages is retained.

Manual App `DEGAP-JOBS` is a separate entrypoint. The source collector now stores versioned manual candidate catalogs under `04_refinement/01_degap/06_manual/01_catalog/`, with an authoritative `.runtime/manual_degap/current.json` pointer, leaving original LGZ tables untouched. Matching App source builds resolve the actual Server runtime and content-bound original/refinement/manual seed sources; Full/Light deliveries include `metadata/server_sources.json` identities. A controlled export → Server → original App import preserved the manually edited Final Path. Original manual packages bound to the committed migration inventory can now enter the immutable registry without rerunning native work or their alignments. Unknown prior result ZIPs remain protected: preserve them and collect from a fresh folder containing the unchanged original `jobs.tsv` and `degap_jobs/` receipts, not a newly exported token. Final native-tool acceptance remains pending; do not treat these protocol checks as full manual-workflow acceptance.

After a stopped/failed invocation, rerun the same launcher. Verified complete results are reused. A sealed complete native run can be readmitted without rerunning the engine after an admission/report/publication failure. Report-only or serializer-only changes refresh the reports/archives without replacing unchanged final sequence files. quarTeT can also reuse a sealed per-input alignment after a later input fails; empty PAFs remain explicit completed no-hit results and later inputs are still processed. The retry uses a fresh native directory, restores only verified PAF bytes and records original producers under `02_jobs/<run>/native_units/` and `native_substeps.json`. This is not arbitrary native-folder resume. DEGAP also restores sealed terminal gap/direction outputs through its original LEFT/RIGHT scheduler: an unresolved LEFT still runs RIGHT, and reused children remain in the native summary. Its preprocessing/detection run fresh; incomplete extension rounds are not adopted. TGS reuses sealed minimap2/Racon command outputs across native chunks/rounds while running scaffold/candidate preparation and integration fresh; native done tags are never restored. LR internal iteration recovery is still pending. Retained partial files alone are never a completion receipt. Do not delete checkpoints or remove locks to force reuse.

```bash
# Read-only progress; this does not cancel a job.
tail -F /work/cgat_server/.runtime/logs/progress.log
python3 "$SERVER/tools/view_run_log.py" --server-dir /work/cgat_server --detailed --follow
# After the old job is stopped, change the budget through run.sh, not run_all.sh.
bash "$SERVER/run.sh" --out /work/cgat_server --threads 64
```

## 5. Explicit migration of a completed old workspace

An unmarked old layout must be migrated explicitly before append; do not run `prepare.sh` over it or create symlinks pretending it is numbered. The current adapter requires a verifiably **completed** original LGZ baseline. Migration/resume of unfinished old LGZ stages remains pending and is refused rather than recomputed with a new engine.

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

Changed user data or unknown/live lock owners are not overwritten. Preserve the journal/backups and diagnose a refusal instead of deleting workspace metadata. These source-level contracts and controlled checks still require the final real-tool/environment and A01–A18 acceptance pass before release.
