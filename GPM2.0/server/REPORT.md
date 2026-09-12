# Server reports

`prepare.sh` records input provenance after argument, input-access and tool preflight
checks, before FASTA normalization. Errors before that point are terminal errors
and do not create a report. `run_all.sh` records each execution unit and exports
`<workspace>.report.html` and `<workspace>.report.zip`, including on a handled
failure or SIGINT/SIGTERM. SIGKILL or host loss cannot run finalizers; the last
atomic snapshot remains available and the next invocation archives it.

The two App archives keep their existing contract. Reports are separate sidecars,
written after the archives, so they can contain the archives' actual sizes and
SHA-256 values without a cyclic dependency. No report hash is embedded in itself.
Standalone incremental/packaging commands are outside this invocation history.

## Directory contract: `cgat_server_report_v1`

| File | Meaning |
| --- | --- |
| `manifest.json` | Invocation identity, ordered execution-unit records, start/end time, status and report errors. |
| `inputs.json` | Original argv and source identities; actual normalized input statistics and parameters at run start. Changed preparation facts are preserved separately. |
| `steps/NNN.json` | One execution unit: runtime, execution/cache status, commands, event history, recent output and collected facts. |
| `steps/grt-<stage>.json` | Immutable first publication of each completed GRT substage, including its original events, sequence versions and evidence tables. |
| `final_snapshot.json` | Final path and reconciled events, collected only after successful validation in this invocation. |
| `final_summary.json` | Original event status versus final status, final-path segment associations, sequence statistics and source contribution. |
| `statistics/` | Report-local sequence statistics cached by file identity, without sequence payloads. |
| `render_report.py` | Standalone Python renderer, with embedded presentation code and no project imports. |
| `report.html` | Self-contained HTML; all data, CSS and JavaScript are inline. |

Previous complete or partial directories are moved to `.report_history/` before
each new invocation. Preparation provenance is also stored in
`metadata/report_inputs.json` for the generated runner. Runtime stage records use
the runner's invocation ID; existing GRT recipe/content IDs retain their own
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
- GRT events are recorded on first publication before downstream reconciliation.
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
  q0-to-q4 comparisons describe GRT processing. N50 increases alone do not prove
  quality improvement. QV/CRAQ currently describe measured input contigs, not a
  newly measured final assembly.
- Original paths, sizes and mtimes describe submitted files. SHA-256 is computed
  for normalized FASTA and delivered archives; reads are not reread solely to
  manufacture a report checksum. Coverage statistics union query intervals,
  avoiding double-counting overlapping PAF rows.
- JSON retains all collected rows. HTML tables are searchable and paginated;
  summary content is visible without JavaScript. User-controlled text is escaped
  and the document blocks network connections with a content security policy.

## Validation

`server/tests/test_server_report.py` exercises real GRT Python stages with
deterministic external-tool fixtures, cache reuse, partial failures, old-result
isolation, immutable events, portable regeneration, gap boundaries, PAF union
coverage and HTML escaping. Existing runner tests cover execution and signal
handling; prepare shell regressions verify the generated workspace.
