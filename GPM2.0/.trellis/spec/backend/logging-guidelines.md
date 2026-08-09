# Logging Guidelines

> Stable operator events and diagnostic context for imports, server runs, and command adapters.

## Current Logging Model

The project does not use one cross-runtime logging library. It uses explicit
machine-readable stage/event codes and runtime-specific sinks:

- Rust import progress is `ImportProgress { stage, detail, progress_*, phase_* }`
  and is persisted to `cache/import.log` after the workspace exists.
- Tauri forwards progress events to the frontend without localizing stage codes.
- The backend CLI writes documented `key=value` result lines to stdout and
  returns errors through its non-zero process result.
- server orchestration appends operator events to `logs/run_all.log`, writes an
  atomic `logs/status.tsv`, and leaves raw tool evidence in its run/cache paths.

## Event Levels and Fields

Use the existing event vocabulary rather than inventing prose-only levels:

| Meaning | Stable representation | Minimum fields |
| --- | --- | --- |
| Operation began | `START` or a `*_start` stage | operation/unit, run ID when available |
| Successful reuse | `SKIP_VALID`, `CACHE_HIT`, `RESUME` | unit, validated fingerprint/checkpoint |
| Completion | `SUCCESS` or `complete` | operation/unit and result summary |
| Recoverable mismatch | `STALE` | unit, invalidated artifact/check |
| Failure/interruption | `FAILED`, `INTERRUPTED` | unit, error/exit code, detail-log path |

Machine code and human detail are separate fields. Codes are stable and
English; user-facing localization occurs in the frontend catalog.

### Import Progress Events

- `ImportProgress.stage` is a stable machine-readable stage code; `detail` carries diagnostic context.
- Long-running work must emit its stage before starting. A completion-only event is insufficient because the UI otherwise continues to show the previous operation while blocked in the long-running call.
- Initial ZIP import exposes high-level `phase_index/phase_total` independently from `progress_index/progress_total`. Phase progress describes the user workflow; progress counts describe emitted operations such as ZIP entries or alignment runs.
- Initial ZIP phases are: validate input, extract, normalize layout, validate GRT, prepare workspace, index alignments, complete.
- GRT validation reports required files, metadata tables, source FASTA/FAI, locked recipe, q artifacts, donor artifacts, evidence/events, Final Path, and source-card trace integrity before their corresponding validation blocks.
- Stable backend stage codes remain in `cache/import.log`; Tauri/frontend localization must not replace the logged code.

### Server `run_all.sh` Progress

- The generated Server workflow maintains one append-only `gpm_server/logs/run_all.log`; recovery invocations append invocation separators rather than creating a history tree.
- Long-running orchestration units emit their stable unit ID and `START` before invoking the child command.
- Stable Server event codes are `START`, `SKIP_VALID`, `CACHE_HIT`, `RESUME`, `SUCCESS`, `FAILED`, `INTERRUPTED`, and `STALE`.
- `gpm_server/logs/status.tsv` is an atomic operator view, not checkpoint authority. Reuse still requires checkpoint and output-hash validation.
- Failure events include the unit, exit code when available, existing detail-log path, and normal `bash gpm_server/run_all.sh` rerun command.
- Raw tool/evidence logs remain under their existing `runs/**` or `grt/cache/**` paths. The run log summarizes and links; it does not relocate raw artifacts.
- Server run logs and statuses never enter App delivery packages.

## Recommended Patterns

- Emit `START` before a blocking command or validation phase, then exactly one
  terminal event for that attempt.
- Include the operation/unit, run ID if one exists, attempt number, stable event
  code, elapsed time for completed work, and the path to existing detail output.
- Append durable run histories; replace current-status summaries atomically.
- Let pure parsers and domain functions return errors. The entrypoint or
  orchestration boundary decides whether and where to log them.
- Keep stdout parseable for CLI consumers. Diagnostics and failures go to stderr.

## Prohibited Patterns

- Do not log environment dumps, tokens, credentials, full FASTA sequences,
  base64 images, unbounded JSON payloads, or complete database rows.
- Do not duplicate every raw tool line into the summary log; link to the raw log.
- Do not emit success before output hashes/checkpoints are validated.
- Do not use localized or mutable prose as the only event identifier.
- Do not add browser `console.log` calls as persistent application logging.

Workspace paths and dataset names may be needed for local diagnostics but can
contain private information. Log only the path/name required to identify the
failed artifact; do not upload or expose local logs by default.

## Common Mistakes

- Emitting a completion event only, leaving the UI stuck on the previous stage
  during a long call.
- Treating `status.tsv` as checkpoint authority instead of validating outputs.
- Logging an exception in a helper and again at every caller, producing duplicate
  failure lines without added context.

## Review Checklist

- [ ] Is there a stable code distinct from human detail/localization?
- [ ] Does long-running work emit start and terminal events?
- [ ] Are durable histories append-only and current summaries atomic?
- [ ] Are secrets, full biological payloads, and unbounded objects excluded?
- [ ] Can an operator locate the detailed failure and safe rerun command?
