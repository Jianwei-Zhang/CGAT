# Frontend Directory Structure

> Ownership and dependency rules for the vanilla JavaScript desktop UI.

## Current Layout

```text
app/frontend/
├── vite.config.js                    # dev-only HTTP/CLI transport adapter
└── src/
    ├── main.js                       # application composition root and initial state
    ├── services/
    │   ├── backend-api.js            # low-level Tauri runtime adapter
    │   ├── workflow-api.js           # operation facade, normalization, dev/mock adapters
    │   └── __tests__/
    ├── state/store.js                # shallow immutable store primitive
    ├── ui/
    │   ├── i18n/                     # catalogs and state relocalization
    │   ├── shell/                    # app shell, routing, session switching/cache
    │   └── pages/
    │       ├── <feature>-page.js     # page orchestration/render/bind boundary
    │       └── assembly/             # assembly feature state/render/runtime modules
    └── styles/
        ├── base.css
        ├── layout.css
        └── components.css            # legacy style monolith; migration target
```

This frontend is framework-free ES modules. React component/hook conventions do
not apply. Rendering returns HTML strings, binding functions attach DOM events,
services own transport, and the store owns serializable application state.

## Required Dependency Direction

```text
main.js (composition root)
  → shell/router and page orchestration
    → feature state, render, and binding modules
      → services and i18n
services → backend-api/Tauri or dev bridge
```

- `main.js` owns initial state, dependencies, route registration, and top-level
  subscriptions. It must not accumulate feature algorithms or page markup.
- A page composes feature modules. Pure state/normalization modules do not import
  DOM, service, or store objects.
- Render modules receive state and explicit dependencies and return markup/model
  values. They do not fetch, mutate the store, or install global listeners.
- Binding/runtime modules may call services and update the store; transport
  request construction and response/error normalization remain in `services/`.
- `services/` must not import pages, renderers, or localized UI copy.

## Feature Module Shape

```text
ui/pages/<feature>/
├── <concern>-state.js       # pure normalize/reducer/selector functions
├── <concern>-runtime.js     # DOM binding or async orchestration
├── <concern>-card.js        # focused markup/model renderer
└── __tests__/
    └── <concern>[-runtime].test.mjs
```

`assembly/final-path-*-state.js`, `assembly/track-layout.js`, and their colocated
tests are current examples. New code should extend this feature shape rather
than add another responsibility to `assembly-page.js` or `render-tracks.js`.

## File Review Triggers

Request a structure review when a production module exceeds 800 lines or 30
top-level functions, a page owns render + binding + transport + domain policy,
a test file exceeds 1,500 lines or 40 tests, or a stylesheet exceeds 1,000 lines
or spans more than three unrelated feature prefixes. These are review triggers,
not mechanical split limits.

A cohesive data table, localized catalog, or focused renderer may exceed a
threshold when it has one owner, an indexable structure, and isolated tests.
Split by feature responsibility and dependency direction, never by line ranges.
The audit findings for `assembly-page.js`, `render-tracks.js`, the former
`tabs-semantics.test.mjs` monolith, `workflow-api.js`, and `components.css` trigger review
because they combine size with independent change axes.

## Recommended Pattern

The focused modules under `ui/pages/assembly/` are the migration pattern: put
pure model/state logic, DOM runtime behavior, focused rendering, and colocated
tests in separately owned files while the page remains their composition point.

## Naming and Placement

- ES module files use `kebab-case`; exported functions use verbs such as
  `normalize*`, `build*`, `render*`, `bind*`, `load*`, or `set*`.
- Runtime modules that touch DOM/global listeners use `-runtime.js`; pure state
  modules use `-state.js` when the distinction is useful.
- Tests use `<owner>.test.mjs` and live in the nearest `__tests__/` directory.
- CSS selectors use stable feature prefixes (`assembly-`, `subview-`,
  `final-path-`, `importer-`, `workspace-`, `degap-`) before moving to the
  corresponding feature stylesheet.

## Prohibited Patterns

- Do not call `window.__TAURI__`, `fetch`, or backend CLI logic from page/render
  modules; route all operations through a service facade.
- Do not import a page from `services/`, state utilities, or another feature's
  low-level runtime module.
- Do not create generic `utils.js` or `helpers.js` as a dumping ground; name the
  domain and owner.
- Do not split a monolith into `part1.js`/`part2.js` while retaining shared
  mutable module globals and circular callbacks.

## Common Mistakes

- Moving a function but leaving its test in a broad semantics suite, so the new
  owner remains invisible.
- Treating browser mock behavior as the domain source of truth.
- Putting computed geometry into global state when it can be derived from the
  current view model.

## Review Checklist

- [ ] Can each module be described with one responsibility and one change axis?
- [ ] Do imports follow composition → page → feature → service/state direction?
- [ ] Are renderers pure and transport adapters UI-independent?
- [ ] Did a size trigger lead to a responsibility/test-seam review?
- [ ] Are tests and CSS placed with the feature owner?
- [ ] Were moved contracts, fixtures, selectors, and imports searched and updated?
