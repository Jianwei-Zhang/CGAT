# Frontend Development Guidelines

> Executable conventions for the framework-free JavaScript UI, state, rendering, services, tests, and CSS.

## Scope

Use this layer for changes under `app/frontend/`. The frontend is plain ES
modules with HTML-string renderers and explicit DOM binding functions; do not
apply React-specific component or hook assumptions.

## Guidelines Index

| Guide | Description | Status |
| --- | --- | --- |
| [Directory Structure](./directory-structure.md) | Composition, page/feature/service ownership, file and CSS review triggers | Active |
| [Component Guidelines](./component-guidelines.md) | Pure view models/renderers, DOM binding boundary, escaping and accessibility | Active |
| [Runtime and Binding Guidelines](./hook-guidelines.md) | Listener lifecycle, async work, stale-response guards, cleanup | Active |
| [State Management](./state-management.md) | Store categories, immutable nested updates, persistence and canonical state | Active |
| [Quality Guidelines](./quality-guidelines.md) | Node/Vite tests, review triggers, fixtures, transport and CSS checks | Active |
| [Type and Runtime Validation](./type-safety.md) | Boundary normalization, exact payloads, conversion ownership, compatibility | Active |

## Pre-Development Checklist

- [ ] Always read [Directory Structure](./directory-structure.md),
  [Type and Runtime Validation](./type-safety.md), and
  [Quality Guidelines](./quality-guidelines.md).
- [ ] For markup or interaction, read [Component Guidelines](./component-guidelines.md)
  and [Runtime and Binding Guidelines](./hook-guidelines.md).
- [ ] For store, cache, persisted view state, or async loading, read
  [State Management](./state-management.md).
- [ ] Map transport → normalization → state → render flow, including exact
  identities/coordinates, validation owner, compatibility behavior, and errors.
- [ ] Search services, feature modules, i18n catalogs, selectors, and tests for
  every changed field/constant before editing.
- [ ] Read active scenario sections in quality/state specs for the touched feature.

## Quality Check

- [ ] Imports follow composition → page → feature → service/state direction.
- [ ] Renderers are pure; bindings own DOM effects; services own transport and normalization.
- [ ] Data and coordinates transform once, before canonical state/render consumption.
- [ ] Nested state is replaced immutably and late responses are identity-guarded.
- [ ] Error codes and exact camelCase request/response shapes match Tauri/dev/mock tests.
- [ ] A size trigger produced a responsibility/test-seam review, not an arbitrary split.
- [ ] Both locales, accessibility behavior, feature CSS ownership, and responsive selectors were checked.
- [ ] Run `npm test`, `npm run build`, the applicable cross-runtime tests, LF check, and `git diff --check`.

**Language**: All documents in this spec layer are written in English.
