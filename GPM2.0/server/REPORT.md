# Server reports

In the current numbered workspace, start at `06_report/report.html`. This page explains how the delivered sequence was assembled. The original LGZ process report (`06_report/01_lgz/`), per-tool diagnostics (`06_report/02_refinement/<tool>/`) and frozen comparison (`06_report/03_comparison/<batch>/`) remain available separately. The directory contract below describes the
LGZ process-report family, not the separate `cgat.refinement-report` schema.
See the [refinement guide](REFINEMENT.md) ([中文](REFINEMENT_zh.md)) for the complete
job/native/accepted-result and delivery path, pins, append and migration commands.
Unmigrated old workspaces retain their old `report/`, `logs/` and `.report_history/`
locations; they are not shadow directories in new workspaces.

`prepare.sh` records input provenance after argument, input-access and tool preflight
checks, before FASTA normalization. Errors before that point are terminal errors
and do not create a report. `run_all.sh` records each execution unit and maintains
the LGZ process report under `<workspace>/06_report/01_lgz/`, including on a handled failure or
SIGINT/SIGTERM. SIGKILL or host loss cannot run finalizers; the last atomic snapshot
remains available and the next invocation archives it.

After a successful baseline run, the finalized LGZ report is embedded as `report/`
in both LGZ App archives under `07_delivery/00_lgz/`. Each successfully published
refinement has its own full/light archives with the matching refinement report.
No separate report HTML or report ZIP is written beside them. The report records the App payload archive size and SHA-256 before `report/`
is embedded, avoiding a checksum cycle. Final delivery archive sizes and SHA-256 values
are printed to the terminal and `.runtime/logs/run_all.log`. Standalone packaging commands
embed the latest workspace report when available; standalone incremental commands
remain outside the recorded invocation history.

## Logging presentation boundary

`.runtime/logs/progress.log` and the default console output are compact views. Neither is an
input to report collection, checkpoint/cache validation, or delivery finalization.
`ReportSession.event()` receives the original event codes/messages and runtime rows;
`child_output()` receives original child text before metric suppression, progress
aggregation or cache-hash shortening. Terminal ANSI controls are removed at that
boundary. The existing 80-line/4000-character-per-line output-tail limit is unchanged;
full diagnostics, including copy/parse timings, remain in `.runtime/logs/run_all.log`.

Color is applied only to terminal output (or the read-only log viewer), never to
report JSON/HTML or persistent logs. The report schema, renderer, provenance facts,
cache classifications, failure records and full/light archive embedding are unchanged.
The `--log-style detailed` option restores verbose console output without changing
reporting behavior. Progress counts are alignment progress, not biological QC results.

## Directory contract: `cgat_server_report_v1`

| File | Meaning |
| --- | --- |
| `manifest.json` | Invocation identity, ordered execution-unit records, start/end time, status and report errors. |
| `inputs.json` | Original argv and source identities; actual normalized input statistics and parameters at run start. Changed preparation facts are preserved separately. |
| `steps/NNN.json` | One execution unit: runtime, execution/cache status, commands, event history, recent output and collected facts. |
| `steps/grt-<stage>.json` | Immutable first publication of each completed LGZ substage, including its original events, sequence versions and evidence tables. |
| `final_snapshot.json` | Final path and reconciled events, collected only after successful validation in this invocation. |
| `final_summary.json` | Original event status versus final status, final-path segment associations, sequence statistics and source contribution. |
| `statistics/` | Report-local sequence statistics cached by file identity, without sequence payloads. |
| `render_report.py` | Standalone Python renderer, with embedded presentation code and no project imports. |
| `report.html` | Self-contained HTML; all data, CSS and JavaScript are inline. |

Previous complete or partial directories are moved to `.runtime/history/reports/` before
each new invocation. Preparation provenance is also stored in
`.runtime/metadata/report_inputs.json` for the generated runner. Runtime stage records use
the runner's invocation ID; existing LGZ recipe/content IDs retain their own
meaning inside the copied results. Renderers reject mixed invocation IDs,
unsupported schema versions and manifest paths outside the report directory.

Collectors may read the server workspace **at the stage boundary**. The renderer
reads only report-local JSON. Paths inside a result are provenance strings, never
instructions to load a workspace file. There are no symlinks, CDNs, remote fonts,
external JavaScript or `fetch()` calls in a generated report. Ordinary Python 3.10+
and a browser suffice; no third-party renderer packages are required.

## Interpretation

- Runtime success means that a command and its terminal validation completed.
  It does not mean every biological problem was repaired. Cache reuse is an
  execution property and does not add another biological contribution.
- LGZ events are recorded on first publication before downstream reconciliation.
  Re-publishing an earlier result does not overwrite that snapshot. A failed
  Step3 can therefore retain a completed Step2 record. A failed invocation never
  adopts an old q4 merely because its file still exists.
- Step1's current external-contig compatibility stages leave sequences unchanged.
  Their reported events explain the deferred work rather than claiming a repair.
- Event counts, candidate counts and unique gap counts have different units.
  Rejected candidates do not establish that their entire target gap is unresolved.
  The final event table and final sequence gap statistics remain separate.
- Sequence gap counts are maximal consecutive N/n runs of at least 100 bp,
  including runs crossing FASTA line breaks. N-base counts include shorter runs.
  Explicit connector segments are counted from q0/q4 source mappings; they are
  not subtracted from maximal N-run counts because adjacent runs may merge.
- Input-to-q0 comparisons describe assignment/order/initial construction;
  q0-to-q4 comparisons describe LGZ processing. N50 increases alone do not prove
  quality improvement. QV/CRAQ currently describe measured input contigs, not a
  newly measured final assembly.
- Original paths, sizes and mtimes describe submitted files. SHA-256 is computed
  for normalized FASTA and delivered archives; reads are not reread solely to
  manufacture a report checksum. Coverage statistics union query intervals,
  avoiding double-counting overlapping PAF rows.
- Report snapshots and HTML tables retain at most 200 preview rows per table,
  together with exact original row counts and provenance paths. Counts and
  biological summaries are computed before projection. Full audit TSV/JSONL
  files remain unchanged in the Server workspace; they are not copied repeatedly
  into App delivery reports. Duplicate result arrays refer to their report table,
  and HTML/download payloads reference each embedded table only once. Search and
  pagination cover the explicitly labelled preview, not the full Server audit.
  Complete published-event snapshots remain in the report JSON so final
  reconciliation and process totals never operate on a preview. Accepted
  interval summaries and final paths are not truncated. Legacy snapshots are
  projected when rendered without rewriting their JSON. Summary content is visible without JavaScript. User-controlled text is escaped
  and the document blocks network connections with a content security policy.

## Validation

`server/tests/test_server_report.py` exercises real LGZ Python stages with
deterministic external-tool fixtures, cache reuse, partial failures, old-result
isolation, immutable events, portable regeneration, gap boundaries, PAF union
coverage and HTML escaping. Existing runner tests cover execution and signal
handling; prepare shell regressions verify the generated workspace.

## Workspace overview and offline regeneration

`06_report/report.html` follows the sequence, not the list of files. Start with input and chromosome groups; compare the reference and q0 on a shared bp ruler, then open individual q0 → q1 repairs, q1 → q2 structural changes or either q2 → q3 end. The overlay explains the evidence without moving the chromosome tracks. A missing alignment is not a failed candidate.

- **LGZ only:** 06 previews the committed Final Path. Copy the FASTA location; the offline report is not a download service. Each collapsed chromosome occupies one line. Expand it to inspect the reference and oriented source intervals.
- **Automatic refinement:** 06 compares each original LGZ gap across tools; 07 switches between the independently published versions. A tool failure is not an unchanged gap, and multiple successful tools do not form a hybrid assembly. Only the DEGAP tab offers a verified native process view when one was captured.
- **Manual jobs:** 08 compares the path exported by the App with that batch’s actual choices. Extra chromosomes and user edits already present at export are part of the baseline, not new Server edits. Switch the batch to switch its snapshot. Inclusion in the batch FASTA is not confirmation of import into the App. Old bundles without a complete snapshot show only recorded outcomes.

 The machine contract and offline renderer interfaces are in `../docs/server-report-viewmodel-contract-20261124.md`. New `cgat_server_report_v1` snapshots additionally record `workspace_layout`, `stage_timing_summary` and `delivery_summary` (optional when reading older runs). `package_full` / `package_light` record staged payloads **before** final compression: final archive size and SHA are not known or guessed at this point. The workspace overview is refreshed under lock **after** project Full/Light and any cumulative auto patch commit. The embedded archive `report/` is still just the LGZ report. Failed/interrupted numbered launches can produce a diagnostic overview; preparation alone never creates it.

Use a current Server tools checkout against a completed old workspace. Neither updating that workspace's runtime nor rerunning the pipeline is required:

```sh
python3 -B /path/to/current/server/tools/regenerate_reports.py \
  --server-dir /path/to/completed-workspace --out-dir /separate/path/report
```

Use an absent or empty destination outside the workspace. Open `report/report.html` there. The export includes `overview_view_model.json`, refreshed `01_lgz/` with its stand-alone renderer, available tool reports under `02_refinement/`, existing comparison tables, and `manual/<batch>/` when applicable. It checks report/provenance receipts, reads small catalog and audit data, **does not** open original genome FASTAs, invoke native tools, update a completion, or edit source files. `checksum_source: receipt` means the published SHA was read, not independently recomputed. Workspace pickup paths remain visible text; only copied report pages/files are linked. Original on-disk LGZ events keep complete evidence/usage lists; only the HTML projection is bounded. The manual worker’s legacy Python `report` return value points to a mode-0600 private audit outside `03_report/`; `public_summary` and the HTML link point to the path-free `03_report/summary.json`. Historical preparation source paths remain in private workspace metadata; portable typed-read identities omit private paths.

`--in-place` instead of `--out-dir` obtains the workspace lock and refreshes **only the receipt-bound overview and automatic job index**. Use the detached export for a complete template upgrade: replacing the published tool report pages in place would invalidate tool-publication receipts and already-delivered archives. No mode silently republishes archives or declares prior App imports.
