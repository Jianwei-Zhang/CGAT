# Backend Error Handling

> Validation ownership and stable behavior across Rust, Tauri, CLI, Python, shell, and frontend transports.

## Current Error Surfaces

- Rust domain/service functions return `anyhow::Result<T>` and add operation or
  path context with `Context`/`with_context`; invalid state uses `bail!`.
- Contract validators expose stable machine codes. Python uses
  `ContractError(code, message)`; Rust GRT validation prefixes errors through
  `grt_anyhow(code, message)`.
- Tauri commands return `CommandResult<T>` with a serializable `CommandError`
  envelope; the full anyhow context chain remains in `message`.
- The dev bridge returns the same stable envelope plus the legacy `error` field;
  `workflow-api.js` normalizes transport failures into an `Error` with `code`,
  `source`, `operation`, `detail`, `data`, and `cause`.

## Scenario: Cross-Runtime Operation Error Contract

### 1. Scope / Trigger

- Trigger: adding or changing an operation exposed through Tauri, the backend
  CLI/dev bridge, and `workflow-api.js`.
- Legacy message parsing is allowed only for errors carrying an explicit legacy
  wrapper code and has a documented removal condition.

### 2. Signatures

```text
Rust service: Result<T, anyhow::Error> with stable domain-code context
Tauri: CommandResult<T> = Result<T, CommandError>
CommandError: { code, message, operation, data }
Dev bridge: HTTP non-2xx { code, message, operation, data, error }
Frontend normalized Error: { message, code, source, operation, detail, data, cause }
```

### 3. Contracts

- Validate transport shape once at the adapter and semantic state once in the
  backend service. Frontend validation may improve UX but is not authoritative.
- A new user-actionable error receives a stable uppercase code. UI category and
  localization select by code; message text is diagnostic, not an API enum.
- Add context while propagating an error; do not replace the underlying reason.
- Convert an error only once per boundary. The frontend service normalizes
  Tauri/dev-bridge errors; renderers consume the normalized shape and do not
  parse backend strings again.
- Generic adapter categories use `INVALID_REQUEST`, `NOT_FOUND`,
  `STATE_CONFLICT`, and `RUNTIME_ERROR`; a more specific stable backend prefix
  such as `GRT_IMPORT_INVALID_JSON` survives unchanged.
- `assembly/error-contract.js` may use message regex only for
  `ASSEMBLY_ERROR`, `WORKFLOW_ERROR`, `TAURI_INVOKE_ERROR`, or
  `DEV_BRIDGE_ERROR`. Remove that compatibility set after persisted, mock, and
  third-party producers all emit stable codes.
- Compatibility changes are explicit: either preserve the existing payload, or
  version/update Tauri, dev bridge, frontend adapter, mocks, and tests together.

### 4. Validation & Error Matrix

| Failure | Owner | Required outward behavior |
| --- | --- | --- |
| Missing/wrong JSON field | Transport adapter | Reject before service call; stable invalid-request code. |
| Invalid ID/state/coordinate | Domain service | Stable domain code plus contextual message; no writes. |
| SQLite/filesystem/tool failure | Persistence/external boundary | Preserve source cause and add operation/path context. |
| Tauri task join failure | Tauri adapter | Runtime code/source/operation; never classify as domain validation. |
| Unknown backend error | Tauri/dev adapter | `BACKEND_ERROR`, preserved diagnostic message, no domain guess. |
| Task/process/runtime failure | Tauri/dev adapter | `RUNTIME_ERROR`; never classify as domain validation. |
| Legacy string/wrapper error | Frontend adapter | Compatibility message parsing only for the named legacy wrapper codes. |

### 5. Good/Base/Bad Cases

- Good: backend returns `CURRENT_CHR_NO_MATCHING_CTG: ...`; the transport keeps
  the code, and the frontend maps that code to localized copy.
- Base: a low-level I/O error gains workspace/import context and remains visible
  in diagnostics.
- Bad: change a sentence and thereby change a regex-selected UI category.

### 6. Tests Required

- Domain test for good, missing, invalid, conflict, and no-write-on-error cases.
- Tauri request deserialization plus exact `CommandError` serialization/code test.
- Dev-bridge non-2xx envelope test for invalid/not-found/conflict/runtime.
- Frontend normalization test for string, `Error`, nested `data`, and unknown
  values, followed by localized category tests using stable codes.

### 7. Wrong vs Correct

#### Wrong

```js
if (/does not exist|not found/.test(error.message)) category = "not-found";
```

#### Correct

```js
if (error.code === "PROJECT_NOT_FOUND") category = "not-found";
```

## Recommended Patterns

- Use `with_context(|| format!(...))` at filesystem, SQL, task, and external-tool
  boundaries; use `?` between layers.
- Perform validation before mutation. For file-plus-database workflows, stage
  files first, commit the database transaction, then promote atomically or use
  the operation-specific rollback contract.
- Shell/Python command entrypoints print concise errors to stderr and return a
  non-zero status. Machine consumers receive a stable code separately or as a
  documented prefix.

## Prohibited Patterns

- `unwrap()`/`expect()` in production paths for user input, package content,
  files, database rows, or external command output.
- Empty `catch` blocks or catch-all fallback from a failed real transport to a
  successful mock for a mutating operation. Existing browser-preview fallbacks
  in `workflow-api.js` are a migration target; new operations must make fallback
  policy explicit and test it.
- Localizing backend messages or using localized copy as a machine contract.

## Common Mistakes

- Validating the same coordinate or payload independently in multiple layers,
  then letting the rules drift.
- Returning a friendly message without the underlying path, operation, or cause.
- Mapping every transport failure to a domain-state category.

## Review Checklist

- [ ] Is structural versus semantic validation owned by one clear layer each?
- [ ] Does every user-actionable failure have a stable code?
- [ ] Is the cause preserved with useful, non-sensitive context?
- [ ] Does the operation leave no partial state on failure?
- [ ] Are all transports, mocks, localization, and tests updated together?
