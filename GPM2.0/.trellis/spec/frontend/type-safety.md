# Frontend Type and Runtime Validation

> Shape safety for plain JavaScript values crossing Tauri, HTTP, storage, and UI boundaries.

## Current Type Model

The frontend is ES modules without TypeScript or a schema library. Safety comes
from narrow operation signatures, runtime normalizers, stable field names,
tests, and backend semantic validation. Existing examples include
`normalizeWorkflowError`, `normalizeGrtProjectView`, and the focused assembly
state normalizers.

## Boundary Rule: Normalize Once

```text
Tauri/dev bridge/storage payload
  → service or feature boundary normalizer
  → canonical camelCase frontend model
  → state/render consumers (no second interpretation)
```

- Transport adapters map snake_case/backend output to the established camelCase
  response exactly once. Renderers never inspect transport alternatives.
- Coordinate systems, orientation, IDs, and lengths are projected at the
  documented domain boundary exactly once. Downstream code consumes the
  canonical value and must not mirror, swap, or infer it again.
- Structural validation belongs at the transport/storage boundary; semantic
  validation remains authoritative in the backend. Frontend guards provide
  fast feedback but do not replace backend checks.
- Compatibility is deliberate: preserve the current shape, introduce an
  explicit version/default, or update all producers/consumers/mocks/tests in one
  change. Do not accept multiple undocumented aliases indefinitely.

## Recommended Patterns

```js
function normalizeLimit(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

const items = Array.isArray(payload.items) ? payload.items : [];
const enabled = payload.enabled === true;
```

- Use `Number.isFinite`, integer/range checks, `Array.isArray`, plain-object
  checks, and explicit boolean comparison.
- Use `??` when `0`, `false`, or an empty string is a valid value; use `||` only
  when every falsy value intentionally means missing.
- Normalize identifiers to one domain type before equality/Map/Set use. Do not
  compare a string ID in one path and a number in another.
- Keep operation payload construction next to the service function and test its
  exact command name, nesting, optional fields, and camelCase spelling.
- A normalized error carries `{ message, code, source, operation, detail, data,
  cause }`; UI categories prefer stable `code` over message matching.

## Data Ownership Examples

- Backend GRT `source_length` becomes frontend `overallLen`; segment endpoints
  remain contribution coordinates and cannot be used to infer that length.
- Tauri request structs use Rust snake_case with
  `#[serde(rename_all = "camelCase")]`; JavaScript sends the documented nested
  `request` object.
- Persisted JSON view state is canonicalized when loaded, then the store and
  renderers use only the canonical structure.

## Prohibited Patterns

- Passing raw `Value`/JSON through several modules with each caller selecting
  defaults independently.
- `value || default` for valid zero/false values.
- Guessing required IDs, origin names, lengths, or coordinates from display
  labels or string prefixes.
- Message-regex classification for a new error that has a stable code.
- Adding a second transport-specific model directly to page state.

## Common Mistakes

- Converting a reversed coordinate at both the append boundary and renderer.
- Spreading an unvalidated payload into state, preserving unknown stale fields.
- Treating a malformed required value as an empty array/object and hiding a
  broken backend contract.
- Updating Tauri request nesting without updating frontend mocks and exact
  payload tests.

## Tests and Review Checklist

- [ ] Normalizer tests cover good/base/bad, null, empty, zero, false, and wrong type.
- [ ] Exact request and response shapes are asserted at every changed transport.
- [ ] Round-trip tests prove values survive persistence and reload unchanged.
- [ ] Coordinate/identity transformations have one named owner and one application.
- [ ] Required malformed fields fail instead of receiving a lossy fallback.
- [ ] Compatibility defaults/version behavior are explicit and tested.

## Scenario: Workflow Operation Extension Contract

### 1. Scope / Trigger

- Trigger: adding, removing, or changing an operation exposed by
  `src/services/workflow-api.js` across Tauri, dev bridge, or browser mock mode.

### 2. Signatures

- Public facade: `workflow-api.js` re-exports domain functions from
  `workflow/operations/*.js`.
- Registry: `WORKFLOW_OPERATION_CONTRACTS = [{ domain, name, preview }]` where
  `preview` is `bridge`, `mock`, or `unavailable`.
- Tauri error: `{ code, message, operation, data }` normalized to the frontend
  Error shape `{ code, message, source, operation, detail, data, cause }`.

### 3. Contracts

- Add the public operation to exactly one domain module and to
  `operation-contract.js`; `workflow-api.js` remains a re-export facade.
- Add the Tauri payload/response mapping to the matching
  `workflow/tauri/*.js` factory and the Rust command to the matching
  `app/src-tauri/src/commands/*.rs` module plus the central handler list.
- For `preview=bridge`, add the dev route to `dev-bridge/route-registry.js` and
  the matching domain operation mapper. For `preview=mock`, add or reuse the
  matching `workflow/mock/*.js` factory operation. For `unavailable`, return a
  stable code rather than silently succeeding.
- If the dev bridge calls the backend CLI, add the Clap variant and one domain
  dispatcher under `app/backend/src/cli/`; `main.rs` remains parse/dispatch only.
- Request fields remain exact camelCase at JavaScript/Tauri boundaries. Semantic
  validation remains backend-owned; adapters validate only transport shape.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Registry name lacks a public export | Contract test fails. |
| Public operation lacks a Tauri method | Contract test fails. |
| Preview strategy is `bridge` but the route is absent | Add route/handler coverage before merge. |
| Preview strategy is `mock` | Real transport failure may use the documented mock path; no hidden mutation fallback. |
| Preview strategy is `unavailable` | Reject with a stable unavailable/runtime code. |
| Transport rejects invalid/not-found/conflict/runtime | Preserve stable code and operation across normalization. |

### 5. Good/Base/Bad Cases

- Good: add one Assembly query to the registry, public Assembly module, Tauri
  Assembly transport/command, dev Assembly route/mapper, mock factory, and
  parity assertions.
- Base: add a Tauri-only file operation with `preview=unavailable` and a stable
  browser error.
- Bad: export a function from `workflow-api.js` while manually embedding Tauri,
  fetch, and mock logic in that facade or classifying its error by new prose.

### 6. Tests Required

- Registry test asserts every public operation and Tauri transport method match.
- Exact command/route and nested camelCase payload test for the new operation.
- Dev non-2xx, Tauri rejection, and mock result tests assert the same category
  code where the operation is supported.
- Mock factory isolation test proves mutable preview state does not leak between instances.
- Run complete frontend tests/build plus affected Windows Rust/Tauri gates.

### 7. Wrong vs Correct

#### Wrong

```js
// Adds an unregistered transport branch to the facade.
export async function newOperation(payload) {
  return window.__TAURI__.core.invoke("new_operation", payload);
}
```

#### Correct

```js
// workflow-api.js stays unchanged; the domain module selects a registered adapter.
export async function newOperation(payload) {
  return workflowRuntime.tauri.newOperation(payload);
}
```
