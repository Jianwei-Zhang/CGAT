# Outcome

Reduce GPM2.0 pairwise-alignment generation and desktop import time without losing the relationships between different contigs on the same dataset track, weakening alignment quality, or exposing temporary identifiers to downstream consumers.

# Scope

- Optimize chromosome-partitioned Server self-runs by treating a self-run as the set of unique unordered pairs of different contigs within one dataset track.
- Do not schedule a dataset-track self-run when that chromosome partition contains fewer than two contigs.
- For tracks with two or more contigs, avoid computing same-contig pairs and duplicate reverse-direction pairs while preserving every different-contig relationship required by the App.
- Keep the final Server `result.paf` contract canonical: original contig names, unchanged coordinate semantics, strand, mapping quality, alignment metrics, and CIGAR tags.
- Optimize desktop PAF ingestion with bounded parallel parsing, one SQLite writer, batched inserts, and bulk index creation after hit loading.
- Add a persisted import-parallelism preference with `Auto`, `1`, `2`, `4`, and `8` parser-worker choices; `Auto` is the default and recommended option.
- Report current file, bytes, parsed rows, written hits, file progress, and overall pairwise-index progress during import.
- Benchmark the implementation on the provided `zyr-test9.light.tar.gz` package or an unchanged extracted equivalent, using the same Windows host and clean destination for baseline and candidate runs.

# Non-goals

- Do not remove or hide pairwise relationships between different contigs in the same primary or support dataset track.
- Do not add a same-contig repeat-analysis view or preserve same-contig hits in the current App pairwise cache.
- Do not change minimap presets, MAPQ, identity, alignment-length thresholds, chromosome assignment rules, or biological acceptance thresholds.
- Do not implement lazy/on-demand pairwise indexing in this change.
- Do not allow multiple threads to write concurrently to the same SQLite database.
- Do not change Full versus Light FASTA inclusion semantics except for pairwise artifacts made smaller by the confirmed self-run contract.
- Do not merge directly into `master`; implementation and Native artifacts remain on the change branch until the user selects an Archive finish action.

# Acceptance examples

- A1: A chromosome-partitioned dataset track with zero or one contig schedules no `*_vs_self` alignment task and produces no required pairwise run for that track.
- A2: A chromosome-partitioned dataset track with two or more contigs produces alignments for every required different-contig unordered pair exactly once, with no same-contig pair and no duplicate reverse-direction pair.
- A3: The final Server PAF uses original contig names and preserves downstream coordinates, strand, MAPQ, alignment metrics, CIGAR semantics, hashes, checkpoints, reports, Full delivery, and Light delivery contracts.
- A4: Desktop import persists the same usable cross-contig pairwise evidence as the canonical Server PAF and existing pairwise queries return equivalent results after the optimized load.
- A5: Initial pairwise import uses bounded batches and a single SQLite writer, avoids maintaining the two pairwise-hit lookup indexes per inserted row, creates those indexes after loading, and retains cancellation and rollback safety.
- A6: The Settings panel offers persisted `Auto`, `1`, `2`, `4`, and `8` import-parallelism choices, defaults to `Auto`, and applies the selected value to parser workers without creating concurrent SQLite writers.
- A7: Import progress reports the active PAF, bytes processed, rows parsed, hits written, per-file progress, and overall pairwise progress often enough that a large file does not appear stalled.
- A8: On the same Windows host and clean destination, the optimized candidate reduces the pairwise-index phase wall time for `zyr-test9.light.tar.gz` by at least 30 percent versus the recorded baseline, with matching usable hit results and no required verification regression.

# Constraints and invariants

- The Git target branch is `master`, but all implementation commits must stay on `comet/pairwise-import-performance` or Native-managed child branches until Archive finish is explicitly selected.
- Server self-run optimization must preserve all relationships between different contigs on the same dataset track.
- Temporary alignment identifiers, if used, must be deterministic, collision-free, restored before final artifact publication, and absent from user-visible metadata and App delivery files.
- Final PAF integrity metadata must be computed from the canonical artifact after name restoration and atomic publication.
- Parser concurrency must be bounded and memory use must be controlled by a bounded queue or equivalent backpressure.
- SQLite has exactly one hit writer; import acceleration must not rely on weakening durable-workspace safety or setting `synchronous=OFF` on the final project database.
- Frontend builds and tests use Windows Node/npm from the Windows checkout. Desktop Rust tests use Windows Cargo. Generated `dist/` is removed after verification.
- Server and backend changes retain LF line endings and Bash compatibility required by the existing Server test matrix.

# Decisions

- Model this work as a Supervisor Change with separate Server generation, backend import-engine, and frontend control/progress children.
- Treat “dataset self alignment” as pairwise evidence between different contigs within the same dataset track, not as same-contig internal repeat analysis.
- Skip a self-run only when fewer than two contigs exist in that chromosome/track partition; multi-contig tracks retain their internal cross-contig relationships.
- Use parallelism only for parsing and preparation of bounded batches; serialize SQLite writes.
- Defer lazy/on-demand indexing to a future change so this change can be judged by equivalent eager-import behavior.
- Use a 30 percent pairwise-index wall-time improvement on the supplied large package as the material performance acceptance threshold.

# Open questions

None. The user-visible behavior, data-preservation boundary, branch isolation, and performance target are specified.

# Verification expectations

- Add focused Server tests for zero/one/many-contig chromosome partitions, unique pair coverage, canonical-name restoration, and task/checkpoint behavior.
- Compare the new multi-contig Server result against the old result filtered to different-contig canonical pairs, including coordinates, strand, MAPQ, alignment lengths, and CIGAR tags.
- Run the maintained Server Python and shell/package tests affected by preparation, task scheduling, delivery, and evidence metadata.
- Add backend tests for parser batches, single-writer behavior, deferred index creation, query equivalence, cancellation, and rollback.
- Add frontend tests for settings persistence, accepted values, transport wiring, localized labels, and granular progress rendering.
- Run backend and Tauri Rust validation with Windows Cargo.
- Run frontend tests and production build with Windows Node/npm.cmd, then remove generated `dist/`.
- Record baseline and candidate phase timings plus hit counts for `D:\\Desktop\\测试\\zyr-test9.light.tar.gz` on the same Windows host and clean destinations.
- Run `git diff --check`, review only task-related files, and obtain a separate read-only Builder review and Verifier acceptance through Native.
