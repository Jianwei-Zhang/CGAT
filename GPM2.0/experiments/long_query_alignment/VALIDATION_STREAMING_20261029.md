# Streaming seed-evidence validation — 2026-10-29

## Scope

Follow-up: `VALIDATION_REVERSE_ADAPTIVE_20261029.md` extends the restricted reader
to reverse two-fragment evidence and process-budget adaptation. The measurements
and positive-only boundary below describe this earlier phase and are not relabelled
as the newer implementation's validation.

Replaces only the original CN trace collector used by the bounded post-DP score
witness. No minimap2 modification, production Server/App change, customer job,
isolation-tool update, automatic fallback or release asset change. Existing
customer isolation jobs and their package remain unchanged.

`stream_seed_trace.py` holds a current-chain summary and one matched summary,
rather than the entire trace plus a dictionary of all anchors. Raw trace remains
on disk as evidence; no new spool/database is needed for this restricted witness.
The score allocation formula in `audit_post_dp.py` is unchanged.

## Accepted protocol and budgets

Pinned diagnostic subset: one QR query with thread ID zero; CN chain IDs must
increase between contiguous chains, as emitted by the tested minimap2 trace
producer. The collector supports exactly the existing positive-strand/two-fragment
witness; this is **not** a general chain-reconstruction API. It retains counts,
first/last anchors and validation flags, not individual anchors or prior chains.

Default budgets, all explicitly checked:

- 512 MiB total trace bytes, including non-CN log lines;
- 10,000,000 total lines;
- 64 KiB per line, with a bounded `readline` request;
- 120 seconds processing time (checked during scanning and before returning).

The in-process deadline is checked between reads; it cannot interrupt a stalled
filesystem syscall. The resource benchmark adds a separate worker timeout.

Input must be a regular file. SHA256 is computed during the same read pass;
descriptor/path identity and size are checked before returning. FIFO input is
opened nonblocking and rejected. No files are written by the collector.

Previously valid supported inputs retain their witness values. New strict refusals
include exceeded resource budgets, unfinished trailing lines, invalid delimiters,
unknown numeric/text format, noncontiguous/reordered chain IDs, nonzero query
thread IDs, invalid optional QT identity and changed files. This intentionally does
not preserve acceptance of malformed/unsupported traces. Existing score/geometry,
unique-chain, monotonicity and fragment-ownership refusal boundaries remain.

Synthetic excerpts without QT remain accepted as in the original witness and are
marked `query_end_marker_observed: false`; this is not a successful-producer signal.
The surrounding audit independently checks the minimap2 command exit. CN after QT
or another QR is rejected. Debug output is not a stable production protocol.

## Resource measurements

Opt-in synthetic **trace** benchmark, not genome alignment. Local runtime:
Linux x86_64, CPython 3.12.3. The previous witness
is frozen from commit `2bb61fafa0063067b88310b7938267f8d469a134`. Both implementations
run in separate Linux processes loading the same modules, with identical input
bytes and an equal per-process address-space cap. Peak RSS is measured using
`resource.getrusage(RUSAGE_SELF)` (Linux KiB). Hashes, commands, full witness values
and resource readings are retained in `evidence/streaming-seed-validation.json`.

At a **512 MiB address-space cap**, both implementations complete:

| Trace shape | Old peak RSS, MiB | Streaming peak RSS, MiB | Old / streaming seconds |
| --- | ---: | ---: | ---: |
| 10,000 seeds, one chain | 22.7 | 20.2 | 0.011 / 0.019 |
| 1,000,000 seeds, one chain | 233.9 | 21.2 | 1.164 / 1.832 |
| 100,000 irrelevant chains + 5 selected seeds | 64.1 | 21.3 | 0.141 / 0.177 |

For every completed old/new pair, the **entire witness is equal**, excluding the
new resource metadata. For the million-seed case, counts are 600000/400000 and
scores 1200000/800000. These are deliberately generated ownership/accounting data,
not minimap2-produced biological evidence.

At an equal **128 MiB address-space cap**, the old million-seed collector raises
`MemoryError`; streaming completes at 21.3 MiB peak RSS. Failed baseline artifacts
are retained, not treated as a successful run or a speed comparison.

This is a memory reduction with additional parsing/validation CPU overhead,
**not a speedup**. Numbers describe this collector process only: they do not measure
whole-genome mapping, page-cache use, total pipeline memory or the customer's
assertion. That customer failure was not established to be an OOM event.

Reproduce (Linux checkout with the frozen baseline commit available locally):

```bash
python3 GPM2.0/experiments/long_query_alignment/benchmark_seed_trace.py \
  --out /tmp/new-stream-benchmark-128 --memory-mib 128
python3 GPM2.0/experiments/long_query_alignment/benchmark_seed_trace.py \
  --out /tmp/new-stream-benchmark-512 --memory-mib 512
```

This benchmark is opt-in, not part of normal CI. It generates bounded synthetic
traces, never invokes minimap2, and uses a new directory. Each worker has a
180-second external timeout; retained logs distinguish budget failure from success.

## Scientific regression checks

Fresh real minimap2 **2.31-r1302** post-DP audit:

- All three cases' complete PAF rows/tags, AS-only hypotheses, guidance statuses,
  error messages and final-output presence equal the previous evidence.
- The score counterexample still has original seed counts **12927/1319** and
  reconstructed chain scores **146016/14899**, agreeing with the real DP oracle.
- The frozen old collector and streaming collector return equal full witnesses
  on the **same fresh real trace**, both for whole-query DP fragments and recovered
  window fragments (excluding added resource metrics).
- The identity case retains its experimental result. Both decoy cases continue
  to refuse incomplete candidate recovery; no final guided PAF is created.
- General candidate selection and MAPQ reconstruction remain explicitly false.

Fresh raw evidence: `/tmp/cgat-stream-post-dp-final-20261029`.
Current source-bound receipt: `evidence/streaming-post-dp-audit.json`.
Previous receipts are preserved, not overwritten or relabelled.

**73 tests pass on each of minimap2 2.26-r1175 and 2.31-r1302**: the prior 64 plus
nine focused streaming tests. Coverage includes all resource budgets, a 32 MiB
malformed single line without whole-line allocation, FIFO rejection, file-identity
changes, duplicate/ambiguous chains, ordering, query scope, invalid coordinates,
fragment overlap/missing anchors, original score refusals, no eager text read,
streamed hash equality and 30 deterministic randomized ownership fixtures.

## Remaining boundary

Only CN evidence processing is bounded by this change. The broader experimental
PAF pools and other stages still have separate in-memory structures. The audit
continues to generate only its small synthetic fixtures; this is not permission
to run it as a full wheat trace collector. Larger traces can exceed the explicit
budgets and must fail rather than silently dropping evidence.

Reverse-strand/multiple-split/indel/repeat generalization, complete parent/sub-hit
selection, MAPQ equivalence and customer acceptance remain unfinished. The nine
historical GRT comparisons and 270 Mb recovery were not rerun here: their mapping
code is unchanged, and their past results are not new validation of this reader.
