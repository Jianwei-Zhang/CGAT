# Component Guidelines

> Rendering and interaction components for the framework-free ES module UI.

## Component Model

GPM2.0 components are functions, not framework instances. Use three explicit
roles:

```js
export function buildFeatureModel(state) { /* pure data */ }
export function renderFeature(state, deps) { /* escaped HTML string */ }
export function bindFeature(host, store, deps) { /* DOM events and actions */ }
```

Small components may combine build and render, but rendering and side effects
remain separate. `assembly/render-shell.js`, `assembly/degap-card.js`, and the
focused `*-runtime.js` modules show the intended direction.

## Recommended Patterns

- Pass `state` and explicit dependencies; do not read an ambient singleton.
- Derive a small view model before building complex markup. Pure builders are
  directly testable without a fake document.
- Escape all data-derived text/attributes with the supplied `escapeHtml` and
  `escapeAttr` helpers. Literal trusted markup is kept close to the renderer.
- Use stable `data-*` attributes for binding and test selection. Keep business
  identity (project ID, `assemblyCtgId`, phased item ID) distinct from display
  text and DOM position.
- A binding function delegates events at the smallest stable host and calls a
  service/action before replacing the relevant nested store state.
- User-visible text comes from the `ui/i18n` catalog. Both `zh` and `en` are
  updated and tested in the same change.

## Input and Output Contracts

- Required state fields are normalized before render. A renderer may use safe
  empty collections for optional presentation data but must not repair a broken
  backend contract silently.
- Rendering returns deterministic markup for the same state/dependencies.
- Actions expose a promise when asynchronous; the caller owns loading, success,
  and normalized error state.
- Geometry written to inline styles/SVG attributes must be computed from a
  tested model. Static appearance belongs in feature CSS.

## Styling

- Use global CSS with feature-prefixed selectors until the style-split task
  moves rules to feature files. Preserve selector names during behavior-only
  refactors.
- Reuse base primitives (`button`, `card`, layout classes) and add a modifier
  such as `.is-active` instead of copying a component block.
- Do not couple behavior to computed style or selector order when a `data-*`
  state/identity attribute is available.

## Accessibility

- Use `<button>` for actions and form controls with associated labels.
- Keyboard activation, focus visibility, `aria-*` state, and disabled state
  must match pointer behavior for menus, dialogs, tabs, and draggable controls.
- Decorative SVG/canvas content needs an accessible label or an adjacent text
  representation when it communicates state.
- Modal focus/close behavior and destructive confirmation cannot depend only on
  hover or color.

## Prohibited Patterns

- Unescaped backend/dataset text in `innerHTML`.
- Fetching data or mutating the store inside `render*`.
- Selecting an entity by displayed name, array index, or DOM order when a stable
  identity is available.
- Copying a whole card/page renderer for a small variant instead of composing a
  view model or modifier.
- Pointer-only interaction for an action that can be expressed as a control.

## Common Mistakes

- Binding listeners after every render without an idempotence guard.
- Recomputing a coordinate transformation in markup after state normalization
  already projected it.
- Updating visible copy in one locale only.

## Tests and Review Checklist

- [ ] Pure builders cover empty/base/edge data without DOM globals.
- [ ] Renderer tests cover escaped content, stable IDs, both locales, and a11y attributes.
- [ ] Binding tests drive real event-shaped objects and assert service payload plus state.
- [ ] Rendering has no transport/store side effect.
- [ ] Static style stays in CSS and dynamic geometry has a tested model.
- [ ] Global/window listeners have explicit idempotence and cleanup behavior.
