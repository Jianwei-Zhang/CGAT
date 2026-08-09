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
