# Backend Development Guidelines

> Executable conventions for Rust backend, Tauri adapters, Linux server Python, shell, and SQLite.

## Scope

Use this layer for changes under `app/backend/`, `app/src-tauri/`, `server/`, or
`tests/gpm_server/`. Scenario documents preserve detailed business contracts;
the core documents define boundaries and quality rules shared across scenarios.

## Guidelines Index

| Guide | Description | Status |
| --- | --- | --- |
| [Directory Structure](./directory-structure.md) | Composition roots, adapters, services, persistence, module review triggers | Active |
| [Database Guidelines](./database-guidelines.md) | rusqlite queries, transactions, versioned migration target | Active |
| [Error Handling](./error-handling.md) | Validation ownership, stable codes, cross-runtime error contract | Active |
| [DEGAP Jobs Export Contracts](./degap-jobs-export.md) | Cross-layer DEGAP gapfiller/telseeker-ctg export semantics | Active |
| [Final Path Export Contracts](./final-path-export.md) | Cross-layer final path FASTA orientation semantics | Active |
| [GRT Package Contract](./grt-package-contract.md) | New-only Server-to-App GRT package schema and trace integrity | Active |
| [Server Run Orchestration](./server-run-orchestration.md) | Generated run plan, checkpoint authority, state, lock, and live log contract | Active |
| [Quality Guidelines](./quality-guidelines.md) | Review triggers, tests, Rust/Python/shell/LF gates, active patterns | Active |
| [Logging Guidelines](./logging-guidelines.md) | Stable progress/event codes, sinks, privacy, operator diagnostics | Active |

## Pre-Development Checklist

- [ ] Always read [Directory Structure](./directory-structure.md),
  [Error Handling](./error-handling.md), and
  [Quality Guidelines](./quality-guidelines.md).
- [ ] For schema, SQL, persisted JSON, or transaction changes, read
  [Database Guidelines](./database-guidelines.md).
- [ ] For progress, orchestration, external commands, or durable logs, read
  [Logging Guidelines](./logging-guidelines.md) and, when applicable,
  [Server Run Orchestration](./server-run-orchestration.md).
- [ ] Read every scenario contract whose command, table, file, coordinate, or
  package field is touched; preserve it unless the task explicitly versions it.
- [ ] Map dependency direction, validation owner, conversion owner, transaction/
  rollback boundary, and platform-authoritative test command before coding.
- [ ] Search for equivalent Rust/Tauri/CLI/Python/shell implementations and
  shared fixtures before adding another helper or constant.

## Quality Check

- [ ] The change follows composition root → adapter → service/domain → persistence.
- [ ] A file/function-count trigger produced a responsibility review, not an arbitrary split.
- [ ] Structural and semantic validation plus coordinate/data conversion each have one owner.
- [ ] Stable error/event codes survive transport and localization boundaries.
- [ ] Database changes are versioned and tested from fresh/old/failure states.
- [ ] Tests reuse authoritative fixtures and assert cleanup/no partial state.
- [ ] Run the affected focused checks and the canonical commands in
  `QUALITY.md`; Tauri/Rust authority is the Windows host.
- [ ] `python3 scripts/check_line_endings.py` and `git diff --check` pass with no fixture/build artifacts.

**Language**: All documents in this spec layer are written in English.
