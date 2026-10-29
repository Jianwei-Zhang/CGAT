# Standalone query isolation validation — 2026-10-29

## Scope

`isolate_minimap2.py` is a standalone, opt-in diagnostic, not a Server runtime
change or a parameter fix. No customer FASTA or customer paths are committed.
No minimap2 patch, scheduler submission, remote mutation or release change.
The customer bundle motivated this work; these executions are synthetic only.

## Real 270 Mb localization and replay

Unmodified minimap2 **2.31-r1302**, executable SHA256
`b6c81294dc0b68b2f54f8e2f6f3ad6be71a40bccc47a6e244ecebc73bae9501d`.
The existing deterministic 270 Mb reference was reused read-only. A new query
file contains a 1 Mb `prefix_control` followed by `synthetic_270M` (270 Mb).
One mapping thread; 600 seconds overall budget; 10 GiB child address-space cap;
8 GiB per-file cap; 4 GiB minimum free disk; core dumps disabled.

| Run | Mapping seconds | Child exit | Completed query events | Active query at assertion |
| --- | ---: | ---: | ---: | --- |
| Whole query file | 66.262 | -6 (SIGABRT) | 1 | synthetic_270M, 270000000 bp |
| Selected whole-record replay | 71.268 | -6 (SIGABRT) | 0 | synthetic_270M, 270000000 bp |

Both reproduce the exact `mm_update_extra` qoff/toff assertion. A successfully
completed preceding query is **not** mistaken for the failing query. The parser
uses upstream `QR name thread_id length` / `QT name thread_id elapsed` fields;
the third field is a thread ID, **not** a query record index. Nonzero thread IDs
and interleaved/malformed pairing are rejected for attribution.

The replay scans the original query file, extracts only the named complete record,
keeps the target unchanged, and independently reproduces the failure. Original
inputs' stat identities and the executable hash remain unchanged. The script
records pre-run input SHA256; no after-run full input rehash is claimed.
Both runs bind the exact final harness SHA256 in the committed JSON receipt.

Local execution directories (not required to run the standalone tool):

- `/tmp/cgat-isolate-final-20261029`
- `/tmp/cgat-isolate-replay-final-20261029`

Each return archive was opened and its allowlist verified: only `plan.json`,
`report.json`, `inputs.json`, `stdout.log`, `stderr.log`. No sequence, PAF, binary
or core is sent. Diagnostic output remains explicitly non-production even when
minimap2 exits zero. A captured assertion is a successful **collection**, not a
successful alignment; the report retains the child exit and `alignment_assertion`.

## Targeted and existing regressions

**64 tests passed on each of 2.26-r1175 and 2.31-r1302** (11 new isolation tests,
53 existing experimental tests). Tests include:

- preview does not create files or invoke the executable;
- paths containing spaces, fresh output and prepared-workspace refusal;
- 0700 private output directory;
- bounded parsing of unwrapped FASTA, IUPAC validation, duplicates/empty IDs,
  missing selected record and scan deadline;
- QR/QT matching, assertion attribution, unsupported thread and malformed trace;
- captured assertion/exit status, no input modification, no sequence in archive;
- wrong tool version or inconsistent query identity refuses attribution;
- changed input during mapping invalidates localization;
- timeout terminates the diagnostic and preserves evidence;
- zero exit without alignment cannot become an accepted workaround;
- real minimap2 small control and selected-record CIGAR output.

Run with a real minimap2 on PATH:

```bash
python3 -m unittest discover -s GPM2.0/experiments/long_query_alignment -v
```

## Boundary

Customer query localization/replay, full wheat indexing, downstream scientific
acceptance and recovery remain **unperformed**. No new universal parameter
workaround is claimed. The previously recorded parameter audit is not relabelled
as a fresh run: `--eqx`, smaller batches and long-join/band tuning still have no
established fix for the controlled long-CIGAR case. This tool supplies the missing
operator-run evidence, not a replacement production PAF or automatic fallback.
