# Quality Guidelines

> Code quality standards for frontend development.

---

## Overview

The frontend is plain ES modules tested with Node's built-in runner and built by
Vite. `npm test` must discover the complete `*.test.mjs` suite; the canonical
Windows quality gate also runs `npm run build`. No ESLint/TypeScript gate exists
today, so module boundaries, runtime validation, exact transport payload tests,
and strict review of new warnings are mandatory.

---

## Forbidden Patterns

- Do not add framework-specific commands or Jest-only flags to the Node test runner.
- Do not call Tauri, HTTP, or backend CLI transports from render/page code.
- Do not add new module-global mutable state without an identity key and reset lifecycle.
- Do not classify a new backend error only by message substring when a stable code exists.
- Do not bypass escaping for data-derived HTML/attributes.
- Do not add unrelated selectors to the legacy `components.css`; use a feature
  prefix and move the rule with its owner during the style-split task.

## Structure Review Triggers

| Trigger | Required review |
| --- | --- |
| Production module > 800 lines or > 30 top-level functions | Identify render, binding, service, state, and domain-policy change axes. |
| Transport adapter > 500 lines or > 15 operations | Define one operation contract and generated/shared mappings before adding another route. |
| Test file > 1,500 lines or > 40 tests | Split by owning feature contract and reusable fixture, not arbitrary line range. |
| Stylesheet > 1,000 lines or > 3 unrelated feature prefixes | Map selectors to feature entrypoints and preserve cascade/import order. |

These thresholds trigger analysis, not mandatory splitting. A cohesive catalog,
data table, or single renderer may remain large with one owner and focused tests.
Audit findings F3 (`assembly-page.js`, `render-tracks.js`, and the former
`tabs-semantics.test.mjs` monolith), F4 (`workflow-api.js`/dev bridge), and F10
(`components.css`) trigger review because size coincides with mixed ownership.

### Audit Rule Calibration

| Finding | Rule decision |
| --- | --- |
| F3 assembly UI | All three thresholds fire: page/controller and renderer combine independent concerns, while the 15k-line semantics suite obscures feature ownership; split by state, render, runtime, and feature tests. |
| F4 runtime adapters | `workflow-api.js`, Vite routes, Tauri commands, and CLI dispatch repeat operation mappings/errors; define one operation contract and keep each transport as a thin adapter. |
| F10 `components.css` | The stylesheet exceeds the size and feature-namespace triggers; split by feature ownership while preserving base/layout import order and responsive cascade. |

---

## Feature Stylesheet Ownership and Cascade

`src/main.js` imports `base.css`, `layout.css`, and `components.css` in that
order. `base.css` owns reset rules and global tokens, `layout.css` owns global
page/shell geometry, and `components.css` is a short compatibility manifest.
It imports component owners in this dependency order:

```text
shared-components → overlays → shell → importer → workspace → assembly
                  → subview → final-path → degap → project-export
```

Reusable modal shells therefore load before feature dialog modifiers. Assembly
track foundations load before Subview and Final Path specializations; Final
Path foundations load before DEGAP and project-export integrations. This order
is protected by `src/styles/__tests__/stylesheet-architecture.test.mjs`; do not
alphabetize it or add cascade layers without a dedicated migration.

| Stylesheet | Owner |
| --- | --- |
| `shared-components.css` | Cards, form controls, lists, status text, tables, and documented cross-feature selectors. |
| `overlays.css` | Modal shells, progress pipelines, context menus, toasts, and import/export progress. |
| `shell.css` | Top bar, route navigation, and session metadata. |
| `importer.css` | Importer option cards and workspace-history import affordances. |
| `workspace.css` | Project initialization, recipe summaries, project selection, and workspace tools. |
| `assembly.css` | Assembly shell, chromosome/member controls, primary tracks, confirmations, and GRT visualization. |
| `subview.css` | Subview selection, evidence, anchors, fragments, canvas overlays, and track overrides. |
| `final-path.css` | Final Path cards, table/graph modes, sorting, logs, and export-menu triggers. |
| `degap.css` | DEGAP settings, forms, jobs, and graph integration. |
| `project-export.css` | Project statistics, filters, detail tables, and Final Path previews. |

A selector with one feature prefix belongs to that feature. A rule combining
multiple feature prefixes belongs in shared styles only when its declaration is
one semantic contract for every consumer. Keep responsive overrides and
`@keyframes` with their owner; animation names are global and unique. Add a
token to `base.css` only when equal values also have equal semantic meaning.

Before moving a rule, search renderer markup, runtime selectors, tests,
responsive variants, combined selectors, and animation references. Move the
complete contract. Preserve rules when dead-code evidence is incomplete.

```css
/* Wrong: feature CSS added back to the compatibility manifest. */
.subview-track-svg .track-collinearity-band { cursor: crosshair; }

/* Correct: keep the rule in subview.css after the Assembly track base. */
.subview-track-svg .track-collinearity-band { cursor: crosshair; }
```

CSS assertions must expand the manifest with
`src/styles/__tests__/style-test-support.mjs`; reading the import-only entry does
not prove that a feature rule exists. For a mechanical split, compare pre/post
rule inventories, run relevant render/runtime tests, full `npm test`, and
`npm run build`, then review importer, workspace, Assembly/Subview/Final Path,
and project-export selectors for visual parity.

### Visibility Utility Cascade Contract

The shared `.is-hidden { display: none; }` utility loads before feature
stylesheets. A feature component that later declares its own `display` value
must also own a more-specific hidden-state rule; otherwise equal-specificity
feature CSS can make a node visible even while runtime code correctly retains
the `is-hidden` class and `aria-expanded="false"` state.

```css
/* Wrong: later feature CSS overrides the earlier shared utility. */
.assembly-track-combo-menu { display: grid; }

/* Correct: the feature owner makes its closed state order-independent. */
.assembly-track-combo-menu.is-hidden { display: none; }
```

When adding or moving a feature rule with `display`, search its rendered markup
and runtime class toggles for shared visibility utilities. Test the expanded
stylesheet tree for the scoped hidden selector as well as testing the markup or
class mutation; DOM-only assertions do not validate the computed cascade.

---

## Recommended and Required Patterns

### Import Progress Semantics

Importer progress has two distinct counters:

- `phaseIndex/phaseTotal` describes high-level workflow phases and is the preferred header meter.
- `progressIndex/progressTotal` describes emitted detail operations such as extracted ZIP entries and alignment runs.

Do not present ZIP entry progress as the overall import completion percentage. When phase metadata is present, render the meter and summary from phase metadata, keep detail counts out of stage labels, and localize stable backend `stageCode` values through the importer message catalog. Unknown or add-package stages without phase metadata continue to use the detail-operation fallback.

Required regression coverage:

- GRT validation after layout normalization renders phase 4/7 rather than an archive-entry count near 100%.
- The latest visible stage names the active GRT subvalidation, not `normalize_workspace_layout`.
- Both Chinese and English catalogs cover the long-running GRT validation stage.
- Existing non-phase add-package progress still renders its operation count.

### Targeted Frontend Test Commands

This frontend uses Node's built-in test runner, not Jest. The required complete
suite is:

```bash
cd app/frontend
npm test
```

For a targeted test file during iteration, run Node directly:

```bash
cd app/frontend
node --test src/ui/pages/__tests__/importer-i18n.test.mjs
```

Do not use Jest-only flags such as `--runInBand`. A targeted pass does not replace
the complete `npm test` gate before commit.

### Importer Failed-History Cleanup Contract

#### 1. Scope / Trigger

- Applies when changing importer history validation, delete confirmation, or local history persistence.

#### 2. Signatures

- Persisted history key: `gpm_next:workspace_history`.
- Validation state: `importer.historyValidation[path] = { ok, message }`.
- Bulk confirmation mode: `importer.deleteSelectionMode = "failed-history"`.
- Optional directory deletion state: `importer.deleteWithFiles: boolean`, default `false` when confirmation opens.

#### 3. Contracts

- Offer bulk cleanup only after at least one current history record has a validation result; display the current failure count and disable the action at zero failures.
- Derive targets from the intersection of current persisted history and entries whose current validation result has `ok === false`. Ignore orphaned validation keys.
- Recompute and filter that intersection again at confirmation time; do not trust mutable `deleteTargets` alone.
- Failed-history confirmation renders the same irreversible `deleteWithFiles` checkbox used by single-row deletion and leaves it unchecked by default.
- When unchecked, failed-history mode deletes only history rows and their matching validation state; it preserves project directories, source ZIP fields, current session, and open-workspace input.
- When checked, call `deleteWorkspaceDirectory` only for the filtered current-failure paths. If a deleted path is the current session or open-workspace path, clear that now-invalid state. Source ZIP fields remain unchanged because history does not retain a ZIP-to-workspace deletion mapping.
- Normal single-row deletion keeps its existing optional on-disk directory deletion behavior.

#### 4. Validation & Error Matrix

| Condition | Required behavior |
|---|---|
| Validation has two current failures | Show count 2 and confirm only those two paths |
| Validation has zero failures | Render the bulk action disabled |
| Validation contains a failed path absent from history | Do not show or delete that path |
| File deletion is unchecked | Remove failed history/validation only and make no backend delete request |
| File deletion is checked and targets include a successful or orphaned path | Filter those paths out and request directory deletion only for current failures |
| Checked directory deletion includes the active workspace | Clear the current session and open-workspace path after deletion |
| User cancels confirmation | Reset delete modal state without changing history or validation |

#### 5. Good/Base/Bad Cases

- Good: check file deletion, delete two failed workspace directories and their records, retain successful history, and report both record and directory counts.
- Base: leave file deletion unchecked and remove only failed history/validation; all-valid history keeps the zero-count action disabled.
- Bad: default the irreversible checkbox to checked, or trust mutable `deleteTargets` and delete a successful/orphaned path.

#### 6. Tests Required

- `app/frontend/src/ui/pages/__tests__/importer-i18n.test.mjs` covers Chinese/English copy, current-history intersection, cancel, default-unchecked rendering, unchecked no-file deletion, checked filtered directory deletion, session cleanup, preserved ZIP state, and zero-failure disabling.
- Run the targeted importer test and the complete `node --test` frontend suite.

#### 7. Wrong vs Correct

#### Wrong

```js
deleteTargets = Object.keys(historyValidation).filter((path) => !historyValidation[path].ok);
```

#### Correct

```js
deleteTargets = recentRecords
  .map((record) => record.path)
  .filter((path) => historyValidation[path]?.ok === false);
deleteWithFiles = importer.deleteWithFiles === true;
```

### Assembly Local Refresh Boundaries

#### 1. Scope / Trigger
- Applies to assembly-route interactions that mutate only the main track, Subview, or Final Path card.
- Trigger: adding, editing, deleting, reordering, restoring, dragging, flipping, switching a local view mode, or changing local track controls.

#### 2. Contracts
- A Final Path-only mutation normally renders and replaces only `.final-path-card`. It must not regenerate the main-track or Subview renderer output while their derived state is unchanged.
- GRT result availability is the explicit exception: compare `resolveGrtResultContext().available` before and after Final Path persistence. When it changes, refresh the Final Path card and both GRT consumer regions (main track and Subview) after committing the new state. This removes stale enabled overlays/switches when the path diverges and recreates both unchecked switches when the baseline is restored.
- A Final Path mutation that starts and ends with GRT unavailable must not refresh the main track or Subview. Do not widen every Final Path edit into a three-region refresh.
- A main-track-only mutation must replace only the chromosome/member strip and `.assembly-track-unified`. The main-track refresh renderer must skip Subview and Final Path generation.
- A Subview-only mutation must replace only `[data-subview-panel='1']`.
- Partial bindings must pass an explicit `main`, `subview`, or `final-path` scope. They must not run route initialization, register route-level resize/hotkey listeners, or clear persisted scroll state for absent sibling regions.
- Scroll synchronization remains active for the replaced region, and unchanged sibling DOM and scroll positions remain intact.
- Final Path status/error feedback must patch the shared assembly toast without replacing the main or Subview DOM.
- Full-route rendering remains valid for route/tab/chromosome transitions and route-level modals.

#### 3. Tests Required
- `app/frontend/src/ui/pages/assembly/__tests__/bindings.test.mjs`
  - Assert Final Path view switching and graph drag receive the Final Path card refresh callback, not the full-route callback.
  - Assert partial Final Path binding skips unrelated lifecycle hooks and passes the `final-path` scroll scope.
- `app/frontend/src/ui/pages/assembly/__tests__/final-path-runtime.test.mjs`
  - Assert a baseline edit transitions GRT availability from true to false, clears both display states, and refreshes both GRT consumer regions.
  - Assert restoring the baseline transitions availability from false to true, refreshes both consumers, and keeps both recreated switches disabled by default.
  - Assert another edit while availability remains false does not refresh either GRT consumer region.
- Assembly feature suites under `app/frontend/src/ui/pages/assembly/__tests__/`
  - Keep page-shell, main-track, Subview, Final Path, coordinate, and phased-track rendering regressions green after renderer extraction.

#### 4. Wrong vs Correct
#### Wrong
Calling the route-level `rerender` after a local Final Path edit or Subview drag, which recreates unrelated large SVG trees; or always refreshing main/Subview for every Final Path edit without checking the GRT availability transition.

#### Correct
Persist the authoritative state, replace only the affected region, and leave sibling DOM untouched unless a documented derived-state transition changes a sibling consumer. For GRT availability, refresh main and Subview only when the before/after boolean differs.

### Subview Ruler Virtualization

#### 1. Scope / Trigger
- Applies to ruler guides and labels rendered inside `.subview-track-scroll` for both `subview-ctg` and `subview-track` modes.
- Trigger: any Subview scale where the full domain would produce more ruler nodes than the visible horizontal viewport can display.

#### 2. Contracts
- Subview SVG width, viewBox origin, domain-to-x mapping, contig bars, alignment bands, anchors, and drag offsets remain authoritative and unchanged.
- The initial Subview renderer emits a metadata-only `[data-subview-virtual-ruler='1']` SVG group; it must not serialize one line/text pair per full-domain tick.
- `bindSubviewRulerRuntime` populates that group with only visible ticks plus bounded overscan and updates it from the Subview scroll event without replacing the panel.
- `minTickUnitKb` and `maxTickCount` continue to determine tick spacing and inner width; virtualization must not silently change those preferences.
- Main-track and Final Path rulers are outside this contract and keep their existing render paths.

#### 3. Tests Required
- `app/frontend/src/ui/pages/assembly/__tests__/subview-ruler-runtime.test.mjs`
  - A 43.7 Mb / 1 kb domain returns a bounded visible tick set.
  - The endpoint label is present when the viewport reaches the domain end.
  - Scrolling replaces only the ruler layer and keeps the node count bounded.
  - Metadata-only markup does not serialize the full domain.

#### 4. Wrong vs Correct
#### Wrong
Calling `buildTrackTickItems` over a 43.7 Mb domain during every Subview render and placing all resulting SVG nodes in the panel.

#### Correct
Emit ruler geometry metadata once, then derive and paint the visible tick window from the live scroll viewport.

### Assembly Track Coordinate Contracts

#### 1. Scope / Trigger
- Applies when rendering assembly track hit bands from `list_chr_view_ctgs` in `app/frontend/src/ui/pages/assembly/render-tracks.js`.
- Trigger: any change that uses `ctg.hits[*].ctgStart/ctgEnd` or `ctg.hits[*].ctg_start/ctg_end` for main-track rendering.

#### 2. Signatures
- Backend command: `list_chr_view_ctgs(workspaceRoot, projectId, chrName?, datasetId?)`.
- Frontend fields consumed by main tracks:
  - `item.orient`: the visible assembly sequence orientation from `assembly_seq.orient`.
  - `item.refOrient`: the chromosome/reference placement orientation from `assembly_ctg.ref_orient`.
  - `item.hits[*].strand`: hit alignment direction relative to the reference.
  - `item.hits[*].ctgStart`, `item.hits[*].ctgEnd`: ctg display coordinates already projected by backend.
  - `item.hits[*].refStart`, `item.hits[*].refEnd`: reference coordinates.

#### 3. Contracts
- `list_chr_view_ctgs` returns main-track hit coordinates in ctg display space. If a ctg is flipped, backend already mirrors `ctgStart/ctgEnd` using `assembly_seq.orient`.
- `renderAssemblyTracks` must draw main-track hit bands from `ctgStart/ctgEnd` as-is. Do not mirror those hit coordinates again based on `item.orient` or `item.refOrient`.
- Main-track hit band point order must still use hit direction. If `item.orient` and `hit.strand` differ, connect ctg-left to ref-right and ctg-right to ref-left so the band crosses; if they match, connect left-to-left and right-to-right.
- `get_track_pairwise_evidence` returns subview pairwise coordinates in each persisted ctg display space, and its `strand` is normalized for that persisted query/subject orientation. For `subview-ctg` and `subview-track`, draw `strand: "-"` bands as crossed by connecting top-left to bottom-right and top-right to bottom-left.
- Subview-only local flip state is separate. `buildSubviewLocallyFlippedContig` may mirror local subview hits because that state has not been persisted through the backend projection path.
- When appending a subview contig to final path, treat context `orient` / `refOrient` as the current view orientation and prefer it over the source ctg's stored `orient`. Subview-local flips are not persisted to the source ctg, but append-to-path must materialize the current subview orientation into the final path row.
- Final Path assembly-ctg `start` / `end` are always coordinates on the original Dataset sequence, while Subview anchor cuts and fragment ranges are display-space coordinates. At the append boundary, keep forward ranges unchanged and project each reversed endpoint exactly once with `sourcePos = overallLen - displayPos + 1`. Do not merely swap reversed display endpoints.
- Whole-contig append is the same projection with display range `1..overallLen`, yielding `1..overallLen` for `+` and `overallLen..1` for `-`.
- Pairwise evidence must also honor subview-only local flips in the frontend. When exactly one side of a pairwise hit is locally flipped, mirror that side's hit interval with the same ctg length used for drawing and toggle the band crossedness. When both sides are locally flipped, mirror both intervals and keep the original crossedness.
- Local flip actions in `subview-ctg` and `subview-track` should refresh the subview panel, not rebuild the whole assembly route.
- `rerenderSubviewPanel` must call `renderAssemblySubviewPanelImpl` with the same render-track dependency object used by `renderAssemblyMainTab`. Passing shell renderer deps breaks local subview repaint because the subview renderer requires `getCurrentProject`, `getDatasetNameById`, `getSupportDatasetOptions`, and `getMeasuredTrackViewportPx`.
- Persisted main-track `flip-ctg` actions should use a local refresh path (`localRefresh: true`) and avoid setting `assembly.loading=true`; the user should not see the chromosome loading curtain for a single contig flip.

#### 4. Validation & Error Matrix
| Case | Expected frontend behavior |
|------|----------------------------|
| `orient: "+"`, hit `ctgStart=20_000`, `ctgEnd=40_000` | Draw band at the supplied left-side interval. |
| `orient: "-"`, backend hit `ctgStart=960_001`, `ctgEnd=980_001` for a 1,000,000 bp ctg | Draw band at the supplied right-side interval. |
| `orient: "-"`, `strand: "-"` | Draw a non-crossing band because display direction matches reference direction. |
| `orient: "+"`, `strand: "-"` | Draw a crossing band because display direction opposes reference direction. |
| Subview pairwise hit `strand: "-"` | Draw a crossing subview band; do not re-transform the pairwise coordinates. |
| Subview pairwise hit `strand: "+"`, bottom side locally flipped | Mirror only the bottom interval and draw a crossing band. |
| Subview pairwise hit `strand: "-"`, both sides locally flipped | Mirror both intervals and keep the band crossing state equivalent to persisted display space. |
| Missing or non-numeric `ctgStart/ctgEnd/refStart/refEnd` | Skip the malformed hit band. |
| Subview local flip entry exists | Mirror only the subview-local contig copy, not the main-track persisted ctg. |
| Reversed Subview fragment `101..500` on a 1,200 bp ctg | Persist Final Path source range `1100..701`; never persist `500..101`. |
| Reversed Subview fragment `14,814,691..14,814,725` on a 43,726,252 bp ctg | Persist `28,911,562..28,911,528`. |
| Main-track `flip-ctg` from selected ctg button or context menu | Run the editor action with local refresh and no loading curtain. |
| Subview local flip requests a panel repaint | Re-render `[data-subview-panel='1']` with render-track deps, then bind the new panel. |

#### 5. Good/Base/Bad Cases
```js
// Good: main track consumes backend-projected display coordinates.
const hits = Array.isArray(ctg?.hits) ? ctg.hits : [];
const reversed = hit.strand ? resolveTrackCtgOrient(ctg) !== hit.strand : false;

// Bad: double-flips persisted main-track hits and makes flip-ctg appear unchanged.
const hits = ctg.orient === "-" ? mirrorHits(ctg.hits, ctg.totalLength) : ctg.hits;
// Bad: ignores strand, so reverse-strand hits never cross after ctg flip.
const points = [ctgLeft, ctgRight, refRight, refLeft];
```

#### 6. Tests Required
- Files: `assembly-main-track-layout.test.mjs`,
  `assembly-main-track-coordinates.test.mjs`, and
  `assembly-subview-pairwise.test.mjs` under the Assembly `__tests__/` directory.
  - Assert a flipped ctg with backend-projected right-side `ctgStart/ctgEnd` still renders the hit band on the right.
  - Assert `orient` and `strand` mismatch reverses the ref-side point order so the band crosses.
  - Assert `subview-ctg` and `subview-track` pairwise `strand: "-"` hit bands cross in display space.
  - Assert `subview-ctg` and `subview-track` local flips mirror pairwise hit intervals and toggle crossedness when exactly one side is flipped.
  - Assert local contig flip rerenders only the subview panel.
  - Assert persisted and Subview-local reversed fragment appends convert display coordinates into original-source Final Path coordinates.
  - Pair the frontend coordinate regression with a backend export regression proving alternative GRT/App boundary splits produce identical sequence.
  - Assert the real subview panel rerender uses render-track deps and paints the flipped label immediately.
  - Assert main-track `flip-ctg` editor actions use local refresh without a loading rerender.
  - Assert malformed hit coordinates are skipped, not coerced.

#### 7. Wrong vs Correct
#### Wrong
Recomputing main-track hit display positions in the frontend from `orient` or `refOrient`.

#### Correct
Treat `list_chr_view_ctgs` hit coordinates as the display contract for main tracks; use `hit.strand` only to choose band point order, and only transform coordinates for explicitly local, unsaved subview state.

### Assembly Drag Preview Overlay Synchronization

#### 1. Scope / Trigger
- Applies when a main-track or Subview contig drag previews geometry that is rendered outside the dragged contig `<g>`.
- Trigger: GRT result junctions, labels, hover targets, or any future overlay whose endpoints depend on one or more movable contigs.

#### 2. Signatures
- Movable contig group: `data-grt-result-entry-key` identifies the GRT entry represented by that group.
- Junction group: `data-grt-result-junction-left-entry-key` and `data-grt-result-junction-right-entry-key` identify its endpoint owners.
- Cross-entry junction children use `data-grt-result-junction-line="1"`; a movable gap label uses `data-grt-result-junction-label="1"`.
- `previewTrackContigDrag` and `previewSubviewTrackContigDrag` are responsible for applying the same transient drag offset to dependent GRT geometry.

#### 3. Contracts
- Drag preview remains a transient DOM transform. It must not mutate persisted contig coordinates or GRT baseline data.
- When exactly one junction endpoint belongs to the dragged contig, move only that endpoint on every visible and hover line; move its gap label to the new midpoint.
- When both endpoints belong to the dragged contig, translate the whole junction group. This preserves same-contig arcs and moves all group-owned geometry together.
- A zero preview offset must restore the original geometry even when only one endpoint matched. Endpoint ownership, not numeric offset equality, determines whether the whole group moves.
- Clearing or cancelling preview must restore original `x`, `x1`, and `x2` values and remove all transient preview attributes and transforms.
- Main-track and Subview drag paths must implement the same behavior.

#### 4. Validation & Error Matrix
| Case | Expected preview behavior |
|------|---------------------------|
| Dragged contig owns only the left endpoint | Move `x1` on visible and hover lines; move the label by half the drag offset. |
| Dragged contig owns only the right endpoint | Move `x2` on visible and hover lines; move the label by half the drag offset. |
| Dragged contig owns both endpoints | Translate the junction group, including same-contig arcs. |
| Preview offset returns to zero | Restore the original endpoint and label geometry without waiting for cleanup. |
| Drag is cancelled or committed | Cleanup restores originals and removes transient attributes. |
| Junction has no dragged endpoint | Leave its geometry unchanged. |

#### 5. Good/Base/Bad Cases
- Good: a cross-contig junction stretches with the moved endpoint while its hover target and gap label stay aligned.
- Base: a junction unrelated to the dragged contig remains unchanged.
- Bad: move only the contig `<g>`, leaving an independently rendered GRT line at its old coordinates.

#### 6. Tests Required
- `track-drag-preview-runtime.test.mjs` covers one-endpoint movement, hover geometry, label midpoint, both-endpoint group translation, zero-offset restoration, cleanup, and main/Subview parity.
- `grt-result-state.test.mjs` verifies stable endpoint identity and junction-child markers in rendered GRT markup.
- `grt-visualization.test.mjs` verifies main and Subview contigs expose matching entry identities and keeps the Subview GRT switch in the inline control row before the minimum tick control.

#### 7. Wrong vs Correct
#### Wrong
Apply drag transforms only to the contig group and ordinary PAF polygons.

#### Correct
Resolve dependent junctions by stable entry identity, update every geometry consumer during preview, and restore their original attributes during cleanup.

### Subview Anchor Identity Contracts

#### 1. Scope / Trigger
- Applies when changing Subview anchor activation, persistence, track order swapping, or hit-key generation in `app/frontend/src/ui/pages/assembly/render-tracks.js`, `app/frontend/src/ui/pages/assembly-page.js`, or `app/frontend/src/ui/pages/assembly/subview-anchor-state.js`.
- Trigger: any state or rendering path that stores active evidence anchors by `hitKey:edge` while allowing the same pair to be viewed with top/bottom order swapped.

#### 2. Contracts
- Copied/manual anchors are endpoint-key based and order-insensitive. Evidence anchors are hit-key based and may encode current top/bottom order.
- If a Subview pair can be rendered in either vertical order, evidence anchor activation must either use an order-insensitive canonical key or include an explicit reverse-key alias when resolving active state.
- Do not assume persisted `activeAnchors` can be matched verbatim after `swapSubviewSummaryOrder`. For track-pair evidence keys shaped like `pair:<topCtg>:<topHit>:<bottomCtg>:<bottomHit>`, the reverse order is the same evidence pair and must preserve the same active `left`/`right` edge.
- Regression tests should cover both manual anchors and original evidence anchors after top/bottom track order swaps.

#### 3. Validation & Error Matrix
| Case | Expected frontend behavior |
|------|----------------------------|
| Active track-pair evidence anchor is stored before top/bottom swap | The corresponding reversed `pair:` hit key still renders as active after the swap. |
| Copied/manual offset anchor is stored before top/bottom swap | Endpoint matching keeps the manual anchor active after the swap. |
| User opens context menu on a reversed evidence band | The active state shown in the menu must match the preserved anchor state. |

#### 4. Tests Required
- Files: `assembly-subview-state.test.mjs` and
  `assembly-subview-anchors.test.mjs` under the Assembly `__tests__/` directory.
  - Assert swapped `subview-track` order keeps original evidence anchors active.
  - Assert copied/manual anchors remain active after the same order swap.

#### 5. Wrong vs Correct
#### Wrong
Treating `hitKey:edge` as order-insensitive when the key embeds `top` and `bottom` identity.

#### Correct
Canonicalize or alias order-encoded evidence keys at the active-state boundary, while leaving manual anchors endpoint-key based.

### Assembly Phased Track Interaction Contracts

#### 1. Scope / Trigger
- Applies when changing phased assembly track item menus, phased track deletion/removal flows, or subview selection in `app/frontend/src/ui/pages/assembly-page.js`, `app/frontend/src/ui/pages/assembly/context-menu.js`, `app/frontend/src/ui/pages/assembly/bindings.js`, `app/frontend/src/ui/pages/assembly/render-tracks.js`, or `app/frontend/src/ui/pages/assembly/subview-state.js`.
- Trigger: any behavior that treats a phased track item as a contig action target, final path append source, `subview-ctg` candidate, or `subview-track` lane.

#### 2. Signatures
- Phased item identity fields: `phasedTrackId`, `phasedTrackItemId`, `phasedHaplotypeKey`, and `assemblyCtgId`.
- Subview track selection fields for phased lanes: `{ role: "phased", source, phasedTrackId, haplotypeKey }`.
- Main-card local refresh entry points: `refreshPhasedTracksForCurrentChr(host, store)` and editor actions with `localRefresh: true`.

#### 3. Contracts
- A phased item instance is identified by `phasedTrackItemId` for removal and by `phasedTrackId` plus `phasedHaplotypeKey` for track-level selection. Do not use only `assemblyCtgId` when the action targets a phased item instance because the same contig can appear in multiple phased tracks.
- Phased item context menus must offer append-to-matching-haplotype final path, persisted flip, and remove-from-current-phased-track actions. Removing an item deletes only that phased track item, not the source contig and not matching items in other phased tracks.
- Phased item append actions must target the corresponding haplotype final path (`A`, `B`, `C`, ...), using the phased track label when available.
- Phased item removal and main-track persisted flips should refresh the main assembly card locally. They must not reload the whole route or show the full chromosome loading curtain.
- Phased item bars must reuse the corresponding primary-track base layout rectangle. Do not recalculate a phased item as a standalone one-contig row, because primary-track min-gap compression or shifting must remain visible-identical for the same `assemblyCtgId`.
- Phased item hit bands must carry phased item identity (`data-band-phased-track-item-id`) and drag preview must select phased bands by item identity when available. The same `assemblyCtgId` can appear multiple times inside one phased track.
- Phased item sticky ctg labels must carry the same item-scoped identity. The rendered label metadata should include `data-track-label-phased-track-item-id`, sticky label keys should include the phased item id when available, and main-track drag preview must move the matching sticky label with the dragged bar. Otherwise left-clipped phased labels appear fixed while the ctg is dragged, or duplicate phased items with one `assemblyCtgId` can share one overlay label.
- Adding a primary-track contig to a phased track must copy the current primary drag offset to the new phased item using `phasedTrackItemId`. Do not rely on the source primary offset at render time, because each phased item instance must remain independently draggable after it is created.
- When restoring project assembly view state, filter persisted phased drag offsets only after the fresh `phasedChrTracks` item list is available. Otherwise valid duplicate-item offsets keyed by `phasedTrackItemId` look stale and are dropped on reload.
- Phased track labels can be selected as `subview-track` lanes, and Ctrl/Cmd-clicked phased track items can be selected as `subview-ctg` candidates. Preserve phased track identity through selection state, summary construction, and rendering.
- Phased `subview-track` lanes must render contigs in the same left-to-right order as the primary track visual position (`order`/`anchorStart`), with phased `displayOrder`/item id only as tie-breakers. This keeps the subview lane aligned with the main phased row, which reuses primary layout rectangles.
- `subview-ctg` whole-contig groups, `subview-ctg` fragment hit zones, and `subview-track` contig groups must expose phased identity metadata when the rendered ctg comes from a phased lane: `data-subview-*-phased-track-id`, `data-subview-*-phased-track-item-id`, and `data-subview-*-phased-haplotype-key`. Append-to-path actions intentionally do not enforce a phased-source restriction: phased, primary, and support sources in a phased chromosome offer one append target per haplotype path in both the main view and subview.
- Phased subview ctg pools must project each item into the phased item display orientation before rendering. If a phased item `orient` differs from its source ctg orientation, mirror its hit ranges once into item display space and mark the item so pairwise PAF ranges are mirrored for both `subview-ctg` and `subview-track`.
- `subview-ctg` candidate state and summaries must preserve `phasedTrackId`, `phasedTrackItemId`, and `phasedHaplotypeKey` for phased selections. Resolve phased candidates by `phasedTrackItemId` first, then by track/haplotype, and only then fall back to `assemblyCtgId`.
- Pairwise PAF rendering for phased subview items must mirror a side when `(phased item orientation differs from source orientation) XOR (that side is locally flipped)`. Do not treat local flip as the only pairwise mirror source.
- When a dataset has `selfAlignmentAvailable: false`, treat phased tracks as part of the primary dataset for Subview compatibility. Block same-dataset Subview entry for `primary + primary`, `primary + phased`, and `phased + phased` in both `subview-ctg` and `subview-track`, while still allowing cross-dataset `support + primary/phased` pairs.

#### 4. Validation & Error Matrix
| Case | Expected frontend behavior |
|------|----------------------------|
| Same `assemblyCtgId` appears in phased tracks A and B | Drag, remove, and subview selection target only the selected phased item/track identity. |
| Right-click a phased item in track B | Menu includes one append action per haplotype path (`A`, `B`, ...), flip contig, and remove from current phased group. |
| Remove a phased item | Re-render the main assembly card only; leave other route panels and matching phased instances intact. |
| Same `assemblyCtgId` appears in the primary track and a phased track | Render both ctg container bars with identical base x/width before role-specific drag offsets. |
| Drag a primary contig, then add it to a phased track | The new phased item appears at the dragged primary visual position by inheriting the offset as an item-scoped phased drag offset. |
| Same `assemblyCtgId` appears twice in one phased track | Drag preview and persisted drag offsets move only the target item's bar and hit bands. |
| Same `assemblyCtgId` appears twice in one phased track and the page reloads | Restore each persisted drag offset by `phasedTrackItemId`; do not drop them during stale-offset filtering. |
| Select phased track A and primary track for `subview-track` | Summary top/bottom slots preserve `role: "phased"` and `phasedTrackId`. |
| Phased track item save order differs from primary visual order | The `subview-track` phased lane renders in primary left-to-right order, matching the main phased row. |
| Right-click a phased ctg or fragment inside `subview-ctg` or `subview-track` | Menu shows one append action per haplotype path (`A`, `B`, ...), not only the source ctg's matching haplotype path. |
| Right-click a primary/support ctg or fragment inside a phased chromosome subview | Menu shows one append action per haplotype path (`A`, `B`, ...), not one generic append action. |
| Ctrl/Cmd-click a phased item | It can enter the two-contig subview candidate set with `selected*Role: "phased"`. |
| Same `assemblyCtgId` appears in phased tracks A and B and both can be chosen for `subview-ctg` | Candidate slots preserve distinct `phasedTrackItemId` values and resolve to the clicked item instances. |
| Phased item `orient` differs from the source primary ctg | `subview-ctg` and `subview-track` draw hit bands and pairwise PAF intervals in the phased item display orientation. |
| Phased item is orientation-flipped and the user also applies a subview-local flip | Pairwise PAF intervals are mirrored exactly once overall when the two flips differ, and not mirrored twice when they cancel out. |
| Primary dataset has `selfAlignmentAvailable: false`, and the user selects primary + phased or phased + phased | Keep the selections visible, but do not enter Subview; return the existing self-alignment-unavailable error. |

#### 5. Tests Required
- Files: `assembly-context-phased.test.mjs`,
  `assembly-subview-track-rendering.test.mjs`, and
  `assembly-subview-pairwise.test.mjs` under the Assembly `__tests__/` directory.
  - Assert phased item context menus expose all haplotype append targets, flip, and remove actions.
  - Assert adding a dragged primary ctg to a phased track copies the primary offset to the new phased item id.
  - Assert phased item removal refreshes only the main assembly card.
  - Assert phased sticky ctg labels are keyed by `phasedTrackItemId` and main-track drag preview shifts the matching sticky label with the dragged item.
  - Assert phased contigs can be selected as `subview-ctg` candidates.
  - Assert phased track labels preserve `phasedTrackId` when selected for `subview-track`.
  - Assert `subview-track` rendering includes only items from the selected phased track.
  - Assert `subview-track` phased lanes render in primary visual order when phased item `displayOrder` conflicts with `anchorStart`.
  - Assert `subview-ctg` and `subview-track` rendered ctg contexts expose phased metadata for append menus.
  - Assert phased subview candidate slots preserve `phasedTrackItemId` and resolve duplicate `assemblyCtgId` items by item identity.
  - Assert phased item hit ranges are mirrored into item display orientation for `subview-ctg`.
  - Assert pairwise PAF ranges for phased items are mirrored in both `subview-ctg` and `subview-track`, and local flips XOR with phased item orientation.
  - Assert `subview-ctg` fragment append and `subview-track` contig append can route to any selected phased final path target.
  - Assert primary + phased and phased + phased same-dataset selections are rejected when the primary dataset has no self alignment, for both `subview-ctg` and `subview-track`.
  - Assert `support + phased` remains allowed when the support dataset differs from the primary dataset.
- `app/frontend/src/ui/pages/assembly/__tests__/assembly-data-runtime.test.mjs`
  - Assert `loadAssemblyView` restores persisted drag offsets for duplicate phased items sharing one `assemblyCtgId`.
- `app/frontend/src/ui/pages/assembly/__tests__/bindings.test.mjs`
  - Assert phased track label clicks pass `phasedTrackId` and `haplotypeKey` to the subview track selection handler.

#### 6. Wrong vs Correct
#### Wrong
Using `assemblyCtgId` as the only identity for phased track item drag, deletion, or subview-track selection.

#### Correct
Carry phased item and track identity separately: use `phasedTrackItemId` for item-level actions and `phasedTrackId` plus `phasedHaplotypeKey` for track-level selection and final path routing.

### Subview Track-Pair Same-Contig Pairwise Dedupe

#### 1. Scope / Trigger
- Applies when rendering `subview-track` pairwise evidence in `app/frontend/src/ui/pages/assembly/render-tracks.js`.
- Trigger: a pairwise hit resolves to the same `assemblyCtgId` on both the top and bottom track lanes, especially when backend evidence includes reciprocal self-hit rows.

#### 2. Contracts
- Detect same-contig pairings per hit, after both lane entries are resolved.
- Canonicalize the top/bottom interval key before deduping reciprocal self-hit records.
- Dedupe only same-contig pair records; keep non-self pair ordering unchanged.

#### 3. Validation & Error Matrix
| Case | Expected frontend behavior |
|------|---------------------------|
| Top and bottom lanes resolve to the same `assemblyCtgId` and backend returns reciprocal self-hit rows | Render one band for the reciprocal pair, not two overlapping duplicates. |
| Top and bottom lanes resolve to different `assemblyCtgId` values | Keep the original pairwise rendering path and ordering. |
| Same-contig hit appears with a distinct interval pair | Keep it if the interval pair is distinct; dedupe only identical reciprocal copies. |

#### 4. Tests Required
- Add a regression in `app/frontend/src/ui/pages/assembly/__tests__/assembly-subview-pairwise.test.mjs` that loads reciprocal self-hit rows for the same contig and asserts only one `track-collinearity-band` polygon is rendered.
- Keep the existing ds-ds pairwise interval test to ensure the non-self path still uses true pairwise coordinates.

#### 5. Wrong vs Correct
#### Wrong
Applying a global same-track sort or dedupe rule to every pairwise hit in `subview-track`.

#### Correct
Apply canonicalization and dedupe only to the hits whose resolved top and bottom lanes reference the same contig, then feed the remaining records into the existing band pairing path.

### Project Final Path Export Contracts

#### 1. Scope / Trigger
- Applies when changing `app/frontend/src/ui/pages/project-export-page.js`, final-path export service APIs in `app/frontend/src/services/workflow-api.js`, or Tauri/Rust final-path FASTA commands.
- Trigger: project export page actions for `png`, `tsv`, `log`, `fasta`, or `all`.

#### 2. Signatures
- Frontend entry point: `runProjectExport(host, store, kind, deps)`.
- Tauri service for project FASTA: `exportProjectFinalPathFasta({ workspaceRoot, projectId, finalPathByChr, outputPath, stateOrLocale })`.
- Tauri command: `export_project_final_path_fasta(workspaceRoot, projectId, finalPathByChr, outputPath)`.
- Backend params: `ExportProjectFinalPathFastaParams { output_path, records: Vec<FinalPathFastaRecord> }`.
- `FinalPathFastaRecord { chr_name, final_path_segments }`.

#### 3. Contracts
- Project export page outputs are project-level merged artifacts, not one artifact per chr.
- Single-format exports choose one save path and write exactly one file for that format.
- Final path single-chr exports and project-level exports append a sortable timestamp before the extension using `YYYYMMDDHHMMSS` format, for example `project1_Chr01_path_20260430205930.png`.
- Single-format exports choose one save path and write exactly one file for that format; if the chosen file name has no trailing `_YYYYMMDDHHMMSS` timestamp, the frontend appends one before writing.
- `all` chooses one directory and writes at most one `.png`, one `.tsv`, one `.log`, and one `.fasta` using one shared timestamped base name.
- Project TSV must include a `Chr` column and rows for every non-empty final path chr in chromosome order.
- Project TSV `Origin ID` values for non-gap, non-ref rows must come from stored segment `originId` or reliable `assemblyCtgId -> originId/source_seq.seq_name` data loaded from the project. Do not infer them from display `ctgName` prefixes/suffixes.
- Project FASTA must pass a `finalPathByChr` object to `export_project_final_path_fasta`; backend writes one FASTA record per chr.
- Project PNG must render a whole-project final-path overview snapshot, not the current assembly chr card.
- Project log export remains disabled when any final path contains ref segments; PNG/TSV/FASTA remain available.
- Project statistics must count primary track hidden contigs by chr. Build the hidden-id map from `finalPathByChr[chr].hiddenPrimaryCtgIds`, the loaded project assembly view state's top-level `hiddenPrimaryCtgIds`, and the current assembly state's `hiddenPrimaryCtgIds` for `assembly.selectedChrName`.
- Final path edits must preserve the selected chr's `hiddenPrimaryCtgIds` when rebuilding a segment entry; otherwise a later edit can silently erase hidden counts from project export statistics.

#### 4. Validation & Error Matrix
| Case | Expected behavior |
|------|-------------------|
| No current project | Render no export menu action result; export returns `false`. |
| No non-empty final paths | Export returns `false`; no file writes. |
| `kind="tsv"` with two final path chrs | One TSV file containing rows for both chrs. |
| `kind="all"` with two final path chrs | One merged file per enabled export type, named from `<project>_project_path_<YYYYMMDDHHMMSS>`. |
| Any final path contains ref segment | Hide/disable log action; keep PNG/TSV/FASTA/all available. |
| Non-gap, non-ref TSV row lacks `originId`, but loaded ctg data has the same `assemblyCtgId` with `originId` | Enrich the export payload with that real origin ID before writing TSV/FASTA payloads. |
| Non-gap, non-ref TSV row lacks `originId` and no loaded ctg row can resolve it | Export fails in the progress dialog; no TSV file is written and no origin ID is guessed from `ctgName`. |
| Project FASTA has duplicate or blank chr names | Backend command rejects the payload. |
| Current chr has primary track hidden IDs outside the final path segments | Project statistics count those hidden primary contigs and their full lengths for that chr. |

#### 5. Good/Base/Bad Cases
```js
// Good: one merged FASTA payload for the project.
await exportProjectFinalPathFasta({ workspaceRoot, projectId, finalPathByChr, outputPath });

// Bad: per-chr loop creates several files or overwrites one target.
for (const [chrName, finalPathEntry] of Object.entries(finalPathByChr)) {
  await exportFinalPathFasta({ workspaceRoot, projectId, chrName, finalPathEntry, outputPath });
}
```

#### 6. Tests Required
- `app/frontend/src/ui/pages/__tests__/project-export-page.test.mjs`
  - Assert the project export page renders the final-path style export dropdown in the top-right header.
  - Assert the project export page renders export progress in the final-path style modal, not a page-bottom job card.
  - Assert current main-track hidden primary contigs are counted in project export count/length bars.
  - Assert TSV export writes one file containing all final path chromosomes.
  - Assert TSV export fills a missing segment `originId` from loaded ctg data by `assemblyCtgId`.
  - Assert TSV export fails without writing when `originId` is missing and cannot be resolved; the test must prove it does not guess from `ctgName`.
  - Assert TSV and `all` export output paths include one sortable timestamp.
  - Assert `all` export writes one merged artifact per enabled export type and passes merged `finalPathByChr` to FASTA.
- `app/frontend/src/ui/pages/__tests__/project-export-state.test.mjs`
  - Assert `buildProjectExportStatsModel` accepts per-chr hidden primary IDs outside `finalPathByChr` and counts them as used hidden primary ctgs.
- `app/frontend/src/ui/pages/assembly/__tests__/final-path-export-runtime.test.mjs`
  - Assert final-path export timestamp helpers format `YYYYMMDDHHMMSS` and append before the extension without duplicating an existing timestamp.
- `app/frontend/src/services/__tests__/workflow-api.test.mjs`
  - Assert `exportProjectFinalPathFasta` invokes `export_project_final_path_fasta` with `finalPathByChr`.
- Rust tests:
  - Assert project final-path FASTA normalization accepts multiple chr entries.
  - Assert backend project FASTA writes multiple FASTA records in one file.

#### 7. Wrong vs Correct
#### Wrong
Treating project export as a batch wrapper around single-chr final path export.

#### Correct
Treat project export as its own merged-output contract and only reuse single-chr helpers when their output format is explicitly adapted to include the chr dimension.

### Importer Add Dataset Package UI Contract

#### 1. Scope / Trigger
- Applies when changing the importer page's existing-project actions or add-package API wiring:
  - `app/frontend/src/ui/pages/importer-page.js`
  - `app/frontend/src/services/workflow-api.js`
  - `app/frontend/src/ui/i18n/messages/importer.js`
  - Tauri command wiring for `import_add_dataset_package`
- Trigger: any UI or service change that applies `add_ds*.zip` to an already imported workspace/project.

#### 2. Signatures
- Frontend service: `importAddDatasetPackage({ workspaceRoot, projectId, zipPath, runId, stateOrLocale, onStage })`
- Tauri command: `import_add_dataset_package(workspaceRoot, projectId, zipPath, runId?)`
- Required inputs:
  - `workspaceRoot`: existing project area root containing `project.sqlite`
  - `projectId`: selected existing project row id
  - `zipPath`: add-package zip path
  - `runId`: optional progress/cancel correlation id

#### 3. Contracts
- Add-package import is an action on a selected existing project row, not a replacement for full zip import.
- Canceling the add-package zip picker is a no-op. It must not set `inFlight`, append progress stages, or show incomplete-parameter errors.
- After a successful add import, refresh initializer options so existing project rows and dataset choices reflect the new support dataset.
- Progress text should follow existing import progress conventions and use the returned backend stage text when available.
- Browser/dev mock paths must keep importer preview usable without Tauri.
- Chinese and English labels/errors for add-package import must be updated together.

#### 4. Validation & Error Matrix
| Case | Expected frontend behavior |
|------|----------------------------|
| User cancels zip picker | No state change beyond preserving the current importer page. |
| Missing workspace root or project id | Do not call the backend; show a localized failure summary. |
| Backend rejects add package | Clear `inFlight`, show localized failed status and backend error text. |
| Backend succeeds | Clear `inFlight`, append completion stage, refresh options/existing projects. |

#### 5. Good/Base/Bad Cases
```js
// Good: selected project identity flows into the command.
await importAddDatasetPackage({ workspaceRoot, projectId, zipPath, runId, stateOrLocale, onStage });

// Bad: treating add_ds4.zip as the full import zip path.
await importZipBundle({ zipPath: addZipPath, workspaceRoot });

// Bad: picker cancel falls through to validation and shows "incomplete parameters".
```

#### 6. Tests Required
- `app/frontend/src/ui/pages/__tests__/importer-i18n.test.mjs`
  - Assert zh/en add-package labels and runtime messages exist.
  - Assert existing project row renders the add-package action.
  - Assert canceling the add-package picker is a no-op.
- `workflow-api` or integration-level tests when adding new command wrappers:
  - Assert Tauri command name and camelCase parameter mapping match backend command signature.

#### 7. Wrong vs Correct
#### Wrong
Wiring add-package import through the full zip importer or losing the selected project id.

#### Correct
Treat add-package import as a selected-project operation that passes `workspaceRoot`, `projectId`, and `zipPath` to `import_add_dataset_package`, then refreshes existing project options.

---

## Common Mistakes

- Reporting a focused file as the full frontend suite.
- Moving functions out of a monolith while leaving their state, transport, and tests owned by the old file.
- Storing derived geometry/localized labels and then fighting stale persisted state.
- Updating Tauri payload nesting without exact service and Rust deserialization tests.
- Moving CSS selectors without searching responsive variants and combined selectors.

## Testing Requirements

- Place pure state/model tests beside the owning feature under `__tests__`.
  Runtime tests inject host/window/service dependencies and drive event-shaped
  objects. Broad page tests verify composition, not every low-level branch.
- Reuse authoritative project/GRT fixtures and
  `tabs-semantics-harness.mjs`. Do not copy shared state/DOM fixture builders or
  business assertions between Assembly feature suites.
- Every transport operation test asserts command/route, exact nested camelCase
  request, normalized response, normalized error, and mock parity when preview
  mode intentionally supports the operation.
- Every cross-layer coordinate/identity change tests producer, frontend
  normalizer, renderer/export consumer, and a round trip when persisted.
- UI copy changes update and test both Chinese and English catalogs.
- CSS has no standalone linter today. Minimum checks are a successful Vite
  build, relevant render/runtime tests, selector search for moved rules, and
  visual ownership review for feature prefix, responsive rules, and cascade
  order. Do not treat a build-only pass as proof that a selector is live.
- Tests/builds must not mutate tracked fixtures or create commit candidates.

## Scenario: Tauri Nested Command Requests

### 1. Scope / Trigger

- Applies when changing Tauri commands and their frontend service wrappers in `app/src-tauri/src/commands.rs` and `app/frontend/src/services/workflow-api.js`.
- Trigger: a command has several related inputs or a Rust command signature would otherwise exceed the strict Clippy argument limit.

### 2. Signatures

- Tauri command shape: `#[tauri::command] fn update_project(request: UpdateProjectCommandRequest) -> Result<Value, String>`.
- Frontend invoke shape: `invokeCommand("update_project", { request: { ...camelCaseFields } })`.
- Request structs derive `Deserialize` and use `#[serde(rename_all = "camelCase")]`.
- Responses keep the existing command JSON keys and error string mapping.

### 3. Contracts

- Related command inputs are grouped under one `request` object at the IPC boundary.
- Rust request fields use snake_case; Serde maps them to the existing camelCase JavaScript names.
- `update_project` preserves all project IDs, optional support/threshold/phased fields, and backend validation.
- `update_project_assembly_view_state` preserves every normalized view-state field and its default/shape handling. Unknown extra fields remain harmless unless explicitly rejected by the request type.
- Removing an immediately-invoked closure must preserve the command's `Result<Value, String>` error conversion and output object.
- New-only desktop IPC contracts do not provide a compatibility shim for the former flat payload.

### 4. Validation & Error Matrix

| Condition | Required result |
|---|---|
| Nested request contains all required camelCase fields | Tauri deserializes it and dispatches the same backend request. |
| Optional project field is omitted | It remains `None` and backend defaults/validation apply as before. |
| Assembly view value has the wrong JSON shape | Existing command normalization converts it to `{}` or `[]` as appropriate. |
| Backend returns an error | Frontend receives the same normalized error message/source as before. |
| Caller sends the former flat payload | Reject as an unsupported new-only IPC shape. |

### 5. Good/Base/Bad Cases

- Good: `workflow-api.js` passes `{ request: { workspaceRoot, projectId, ... } }`, and Rust maps the fields into the existing backend request type.
- Base: optional values are omitted or use the service defaults; command behavior remains unchanged.
- Bad: retain a large flat Rust command signature and add `#[allow(clippy::too_many_arguments)]`.
- Bad: rename Rust fields without an explicit Serde camelCase mapping, causing silent invoke deserialization failures.

### 6. Tests Required

- Rust Tauri tests deserialize representative nested camelCase project and assembly-view requests.
- `app/frontend/src/services/__tests__/workflow-api.test.mjs` asserts both command names and exact nested payloads.
- Tauri `cargo fmt --all -- --check`, `cargo clippy --all-targets --no-default-features -- -D warnings`, and `cargo test --no-default-features` must pass.
- Backend tests and strict Clippy remain green because business-layer request types are unchanged.

### 7. Wrong vs Correct

#### Wrong

```js
invokeCommand("update_project", { workspaceRoot, projectId, projectName, ... });
```

#### Correct

```js
invokeCommand("update_project", {
  request: { workspaceRoot, projectId, projectName, ... },
});
```

---

## Code Review Checklist

- [ ] Imports follow composition → page → feature → service/state direction.
- [ ] Render/model code is pure; bindings own DOM effects; services own transport.
- [ ] Data shape, identity, orientation, and coordinates are normalized exactly once.
- [ ] Nested state updates are immutable and late async responses are identity-guarded.
- [ ] New errors use stable codes and normalized envelopes, not prose-only parsing.
- [ ] A size trigger includes responsibility, dependency, and test-seam analysis.
- [ ] Tests are feature-scoped, reuse fixtures, and cover both locales where applicable.
- [ ] `npm test`, `npm run build`, LF checks, and affected cross-runtime gates pass.
- [ ] CSS selectors have a feature owner and no accidental cascade duplication.
