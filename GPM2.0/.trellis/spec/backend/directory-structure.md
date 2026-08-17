# Backend Directory Structure

> Ownership and dependency rules for Rust, Tauri, Python, and shell backend code.

## Scope and Current Layout

```text
app/backend/src/
├── lib.rs                  # public domain/service module registry
├── main.rs                 # CLI composition root and output adapter
├── db.rs                   # workspace SQLite connection and schema entrypoint
├── importer.rs             # import facade and rollback/dependency contract
├── importer/               # initial/add-dataset/add-ctg workflows and services
├── grt_package.rs          # legacy GRT monolith; migration target
├── ctg_editor/             # feature package split by operation
└── <feature>.rs            # domain/service modules
app/src-tauri/src/
├── lib.rs                  # desktop composition root and command registration
├── commands.rs             # legacy IPC adapter monolith; migration target
└── *_cancel.rs             # adapter-owned cancellation registries
server/
├── prepare.sh              # Linux bundle entrypoint and legacy generator
├── tools/*.py              # executable stages and reusable server logic
├── templates/*.sh          # directly lintable generated-program sources
├── contracts/*.json        # delivery contract schemas
└── tests/test_*.py         # server unit and integration tests
```

The project is one repository with four runtime surfaces. Do not treat all code
that runs outside the browser as one layer: Rust domain code, Tauri IPC, server
Python, and shell orchestration have distinct owners and test environments.

## Required Dependency Direction

```text
CLI main.rs / Tauri lib.rs                 composition roots
                 ↓
CLI dispatch / Tauri commands              transport adapters
                 ↓
app/backend feature modules                domain and application services
                 ↓
rusqlite and filesystem helpers            persistence and external I/O

server/*.sh                                operator entrypoints
                 ↓
server/tools entrypoint modules             stage orchestration
                 ↓
server/tools shared modules                 parsing, hashing, intervals, state
```

- Composition roots register commands and assemble dependencies. They do not
  own validation rules, SQL, coordinate projection, or package semantics.
- Transport adapters decode input, call exactly one application operation, and
  encode its result/error. They do not reimplement the operation for each
  transport.
- Domain/service modules own semantic validation and return transport-neutral
  Rust structs or Python values.
- Persistence code accepts a `Connection` or `Transaction` owned by the service
  when multiple writes must be atomic. It does not decide UI messages.
- Generated shell programs live as real files under `server/templates/` once
  they contain independently testable behavior; `prepare.sh` may render or copy
  them but must not become their only source.

## Module and File Review Triggers

Size is a discovery signal, not an automatic split rule. Request an explicit
structure review when a production file exceeds 800 lines or 30 top-level
functions/types, an adapter registers more than 15 operations, or an entrypoint
embeds a program longer than 100 lines. A review must identify responsibilities,
change axes, dependencies, and test seams before choosing a split.

A large file may remain intact when it is one cohesive declarative contract,
generated source, or table and has one owner, searchable sections, and focused
tests. Split when two sections change for different reasons, require unrelated
dependencies, need separate rollback/transaction boundaries, or cannot be
tested without constructing the whole subsystem.

Current migration targets found by the engineering audit include
`grt_package.rs`, the GRT stage scripts, and the programs embedded by
`prepare.sh`. The completed importer split keeps its public facade in
`importer.rs` and owns workflow, validation, catalog, alignment, payload, and
rollback concerns in focused modules under `importer/`. Existing public
contracts must be preserved while ownership moves.

## Naming and Placement

- Rust modules and files use `snake_case`; request/response structs use the
  operation name, such as `ProjectUpdateRequest`.
- Python modules use `snake_case`; a stage entrypoint keeps `main()` and argument
  parsing thin, while reusable functions move to a stage-neutral module.
- Shell templates describe the generated command (`package_full_zip.sh`), not
  the generator implementation detail.
- Put tests beside Rust production code in `#[cfg(test)] mod tests` until a
  feature package has a deliberate integration-test boundary. Python tests use
  `server/tests/test_<feature>.py`; cross-runtime shell tests use
  `tests/gpm_server/<feature>_test.sh`.

## Recommended Pattern

`app/backend/src/ctg_editor/` and `app/backend/src/importer/` are preferred
feature-package shapes: the package exposes a narrow facade, shares invariants
through domain-focused modules, and keeps operation-specific workflows and
tests in separate files. Incremental file-plus-database workflows also document
and test their rollback owner explicitly.

## Prohibited Patterns

- Do not import Tauri, CLI parsing, or frontend-specific JSON keys into
  `app/backend` domain modules.
- Do not let an adapter open a database and reproduce domain SQL already owned
  by a backend service.
- Do not make a later Python stage import reusable semantics from an earlier
  executable stage; shared logic belongs in a neutral module.
- Do not split a large file into arbitrary `part1`/`helpers` files while keeping
  the same circular ownership and hidden mutable state.

## Common Mistakes

- Calling a file a service while it still renders transport JSON and commits its
  own partial writes.
- Moving functions without moving their constants, fixtures, and error codes,
  leaving two sources of truth.
- Counting test lines together with production lines and mechanically splitting
  a cohesive module for size alone.

## Review Checklist

- [ ] Is the composition root limited to wiring and process-level concerns?
- [ ] Does each transport adapter delegate to one shared application operation?
- [ ] Is semantic validation owned once, below the transport boundary?
- [ ] Is a multi-table or file-plus-database operation given an explicit atomic boundary?
- [ ] Did every size trigger result in a responsibility review rather than a line-only split?
- [ ] Are tests placed with the owning feature and shared fixtures reused?
