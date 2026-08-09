# Runtime and Binding Guidelines

> Lifecycle rules for DOM bindings, global listeners, timers, and asynchronous frontend work.

## Scope

The frontend does not use React hooks. In this project, the equivalent reusable
stateful boundary is a `bind*` or `*-runtime.js` function. Examples include
`bindAssemblyPage`, `bindBandCanvasRuntime`, and the drag/selection runtime
modules under `ui/pages/assembly/`.

## Recommended Binding Pattern

```js
const FEATURE_BOUND = Symbol("featureBound");

export function bindFeature(host, store, deps) {
  if (!host?.addEventListener || host[FEATURE_BOUND]) return;
  host[FEATURE_BOUND] = true;
  host.addEventListener("click", (event) => {
    const action = event.target.closest("[data-feature-action]");
    if (!action) return;
    // validate identity, call a dependency, then replace nested state
  });
}
```

- Bind once to a stable host and use event delegation for rerendered children.
- Inject services, timers, `window`, and render callbacks through `deps` when a
  test needs control over them.
- A temporary window listener records its exact handler/options and removes it
  on completion, cancellation, host replacement, or error.
- Timer/animation callbacks verify that their workspace/project/viewport key is
  still current before applying state or DOM changes.
- Return an unbind function for listeners owned by a shorter-lived host. A
  process-lifetime delegated host may use an idempotence symbol instead.

## Async Data Flow

```text
DOM event → validate UI input → service operation → normalize response
         → stale-request guard → immutable store replacement → rerender
```

- Services own Tauri/dev-bridge transport selection. Binding code does not call
  `fetch` or `window.__TAURI__` directly.
- Set loading state before the awaited operation and clear it in a deterministic
  success/error path.
- Preserve a successful mutation if a later optional refresh/orientation step
  fails; report the secondary failure without inventing rollback.
- Do not catch a real transport failure and silently execute a mock mutation.

## Naming and Placement

- `bind<Feature>` installs DOM listeners.
- `load<Feature>` performs a read and updates state.
- `run<Action>` performs a user-triggered operation.
- `sync<Feature>` reconciles already available state/DOM without transport.
- Put feature-specific lifecycle code in `<feature>-runtime.js`; keep generic
  low-level viewport/drag primitives in a narrowly named owner module.

## Prohibited Patterns

- Rebinding listeners on every render without a guard or cleanup.
- Anonymous global listeners that cannot be removed.
- Module-level mutable state shared across workspaces/projects unless keyed and
  explicitly cleared by the session lifecycle.
- Async response writes that do not verify the request still belongs to the
  current workspace/project.
- A binding function that also builds a large markup tree or implements backend
  validation rules.

## Common Mistakes

- Removing a listener with a different closure or capture option.
- Letting pointer cancellation skip cleanup and leave drag state active.
- Treating an absent optional DOM node as an error even though the same binding
  is reused across view modes.
- Updating only a top-level loading flag while leaving stale nested feature data.

## Tests and Review Checklist

- [ ] Calling `bind*` twice does not duplicate the observable action.
- [ ] Pointer/keyboard success, cancellation, and cleanup are covered.
- [ ] Window listeners/timers are injected or otherwise controllable in tests.
- [ ] Late async responses cannot update a different workspace/project.
- [ ] Service errors become normalized UI state; no silent real-to-mock fallback.
- [ ] The binding depends on stable data identities, not DOM position or copy.
