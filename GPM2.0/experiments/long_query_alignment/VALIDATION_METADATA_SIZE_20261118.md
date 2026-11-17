# Scale-dependent metadata admission (2026-11-18)

## Incident and scope

JM19 full-wheat job `42172320` on Donau ARM failed on November 17 at
22:35:53 CST. The Flye ordinary controller had completed all 18 units, but
publication rejected its 9,495,548-byte routing plan against a 1 MiB reader
limit. The other alignment retained eight completed hifiasm units before
fail-fast interruption. This was a metadata admission failure, not evidence
that the alignment itself was invalid. The full reference was IWGSC; the
older six-day KN9204 incident is not a directly comparable timing baseline.

## Change

- Remove implicit file-size vetoes for scale-dependent routing, query catalogs,
  controller/resume state and delivery-policy metadata. Do not just raise a cap.
- Use a stdlib incremental JSON reader (64 KiB read chunks), compare stored
  plans against the existing object without a second decoded tree, and select
  only needed top-level fields for preliminary checks. Required decoded state,
  object-key tracking and the largest scalar still consume size-dependent RAM;
  this is not a constant-memory claim.
- Retain regular-file/no-symlink checks, before/after identity fences, digest
  binding where required, strict JSON syntax, complete-source/output validation,
  and safe final publication. Keep explicit bounds for fixed-schema locators,
  runtime manifests and the native protocol, plus a parser nesting safeguard.
- Permit only the reviewed published source profile
  `b61402b11101780c865f9b26654a7a5c104f696c90d3fabb82e53760495a2961`
  to migrate to the pinned new profile, alongside the already reviewed older
  pairs. Scientific kernels, filtering, score policy and native commands are
  unchanged. Incomplete units do not become completed by migration.

## Regression coverage

`test_metadata_json.py` checks >1 MiB real record catalogs, >64 MiB valid JSON,
small read chunks, Unicode/escaping, selected-field parsing, non-finite values,
duplicate keys, truncation, trailing garbage, changed content, explicit protocol
budgets, symlinks and file replacement during reading. Buffer-memory assertions
apply only to the controlled comparison/discard fixtures.

The native adapter regression deliberately fails publication after completing
mapping, then resumes with mapper/index execution forbidden. It checks reuse of
the same attempt and identical completed PAF hashes and final output. Migration
coverage uses the frozen file inventory from the actual v2.0.20 release and
retains a nondefault assignment threshold.

Local checks before submission: 12 incremental-reader tests, 16 native adapter
tests, 38 migration tests (one optional skip), 772 alignment tests (ten optional
helper/source-dependent skips), 476 Server tests (one skip), and 17 release-doc
renderer tests passed. A helper-enabled alignment rerun and the remaining local
shell gate are tracked in release evidence; the local Server/App E2E is left
to the canonical CI rather than running Windows dependencies through WSL.

A separate read-only real-data replay is submitted as Donau job `42390897` under
`~/cgat-reads-debug/jm19-metadata-fix-20261118/`. Its script forbids mutations to
the original workspace and new mapper execution; it verifies exact runtime
compatibility and hashes all 26 completed native PAFs before/after Flye admission.
Submission is not a passing replay or a resumed full analysis. Acceptance and
release/deployment results are recorded separately in the release evidence.
