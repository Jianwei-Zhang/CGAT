# Pairwise import engine

## Loading architecture

Initial import reads canonical pairwise PAF files with a bounded parser-worker pool. Workers parse into bounded batches and apply backpressure to one SQLite writer. No worker writes directly to SQLite.

The writer uses transactions and batch-oriented insertion. The two pairwise-hit lookup indexes are absent or temporarily deferred while initial hits are loaded and are created after successful loading. Query behavior after index creation remains compatible with existing normal and swapped-direction lookups.

Cancellation and failures leave no accepted partial import. Existing initial-import workspace cleanup and rollback guarantees remain authoritative.

## Parallelism

The parser-worker count is resolved from the persisted import-parallelism preference. Explicit values are `1`, `2`, `4`, and `8`; `Auto` chooses a bounded value from available host parallelism and never creates multiple SQLite writers.

## Progress

The import engine emits structured progress containing the active run and path, current and total bytes when known, parsed rows, written hits, file progress, and overall pairwise progress. Updates are throttled enough to avoid dominating import cost while remaining visibly live on large files.

### Scenario: Bulk-load pairwise hits safely

Given multiple large pairwise PAF files, when initial import loads them, then bounded parser workers feed one writer, hit indexes are created after data loading, and the completed database passes integrity and query checks.

### Scenario: Preserve pairwise query results

Given a canonical package and the same query filters, when results are queried from baseline and optimized imports, then both normal and swapped-direction pairwise evidence are equivalent.

### Scenario: Cancel during a large PAF

Given an import is cancelled while parser workers are active, when cancellation propagates, then workers and the writer stop, no partial workspace is accepted, and the existing rollback contract is preserved.

### Scenario: Report granular progress

Given a PAF requires long processing, when import is active, then progress updates advance within that file and report bytes, rows, hits, file position, and overall pairwise position without waiting for the next file.

### Scenario: Meet the large-package performance target

Given baseline and candidate imports of `zyr-test9.light.tar.gz` on the same Windows host and clean destinations, when the pairwise-index phase is measured, then the candidate is at least 30 percent faster and produces equivalent usable hit results.
