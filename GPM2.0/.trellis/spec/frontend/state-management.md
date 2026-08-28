# State Management

> How state is managed in this project.

---

## Overview

The application uses `createStore` from `src/state/store.js`. `setState(partial)`
performs a shallow top-level merge and notifies subscribers; therefore every
changed nested object/array must be replaced explicitly. `main.js` is the
composition root for the initial serializable state. Feature modules own
normalizers, selectors, and action-specific updates.

---

## State Categories

| Category | Owner and examples | Rule |
| --- | --- | --- |
| Authoritative server data | projects, chromosomes, contigs, GRT view | Load through a service; do not infer missing required fields in UI. |
| Persisted workspace view state | Final Path, drag offsets, hidden IDs, support rules | Normalize on load and persist through the one workspace-state service. |
| Session/navigation state | current workspace/project/route/locale | Owned at app shell; clear or rekey when identity changes. |
| Transient UI state | open menu/modal, loading/error, pointer preview | Keep in the nearest feature unless multiple routes/render passes require it. |
| Derived view data | sorted rows, geometry, labels, filters | Recompute with pure functions; do not persist/cache without measured need. |
| DOM/runtime cache | detached assembly DOM, listener flags | Key by workspace/project/locale and clear through lifecycle code. |

---

## When to Use Global State

Promote state to the app store only when it must survive rerender, be consumed
by multiple sibling modules/routes, or be persisted/restored. Pointer-local
coordinates, temporary DOM nodes, and pure derived models remain local. A new
top-level state key needs an owner, reset rule, persistence decision, and at
least one state transition test.

Nested updates replace the complete changed branch:

```js
store.setState({
  assembly: {
    ...state.assembly,
    finalPathByChr: nextFinalPathByChr,
  },
});
```

---

## Server State

Server responses are normalized once before entering the store. A load captures
the requested workspace/project identity and discards a late response after the
session changes. Mutations update state from the returned authoritative summary,
then perform any scoped refresh. Browser mocks mirror backend validation and
state transitions but never define production semantics.

Persisted view state is not a blind cache: canonicalize versioned/default fields
and cross-check authoritative IDs/lengths before using it. Preserve successful
state when a later optional refresh fails, and expose the secondary error.

---

## Common Mistakes

- Mutating `state.assembly.finalPathByChr` in place and then shallow-merging the
  unchanged `assembly` object.
- Writing derived geometry or localized labels into persisted workspace state.
- Applying a late response to a different project after a session switch.
- Keeping module-level mutable state that is neither keyed nor reset.
- Recomputing a source/display coordinate transform in multiple state/render layers.

## Recommended Patterns

- Pure `normalize*`, `build*`, and `set*` functions return new values and accept
  all authoritative inputs explicitly.
- Store stable identities and source facts; derive labels, ordering, filters,
  and geometry at the nearest consumer.
- Use per-workspace/project cache keys and clone snapshots when restoring state.

## Prohibited Patterns

- Direct nested mutation followed by notification.
- Persisting transient DOM handles, callbacks, `Error` objects, or unbounded raw
  transport payloads.
- Using display names or array positions as entity identity.
- Silent fallback from malformed required server state to a plausible empty model.

## Review Checklist

- [ ] Is the state category, owner, reset rule, and persistence rule explicit?
- [ ] Does each nested update replace every changed branch immutably?
- [ ] Are server/storage payloads normalized exactly once before store use?
- [ ] Are async responses guarded by workspace/project/request identity?
- [ ] Is derived state kept out of persistence unless a contract requires it?
- [ ] Do tests cover transition, restore, stale response, and invalid payload cases?

## Scenario: Assembly Runtime Cache Lifecycle

### 1. Scope / Trigger

- Applies when adding or changing Assembly renderer caches, pointer previews,
  timers, pending dialogs, viewport measurements, or other mutable values that
  must survive a local rerender but must not cross workspace/project identity.
- Trigger: a feature would otherwise introduce a module-level `let`, `Map`, or
  `WeakMap` under `ui/pages/assembly/`.

### 2. Signatures

- Session factory: `createAssemblyPageSession()`.
- Reset entry point: `resetAssemblyPageSession(nextWidths?, { timerApi? }?)`.
- Destroy entry point: `destroyAssemblyPageSession(options?)`.
- Render-cache fields:
  - `subviewRenderCache.filteredRefCtgs: WeakMap`;
  - `subviewRenderCache.segmentPairs: Map`, limited to 256 entries;
  - `finalPathGraphPreviewState: object | null`.

### 3. Contracts

- Mutable renderer/runtime state belongs to the explicit Assembly page session,
  not an independent module global.
- `resetAssemblyPageSession()` rebuilds cache containers, clears pointer
  previews, cancels timers/coordinators, and resolves pending dialogs before a
  workspace/project switch can render the next identity.
- `destroyAssemblyPageSession()` delegates to the same reset contract.
- Cache entries are derived presentation values only. They are never persisted
  into project assembly view state or the app store.
- Strong-reference caches must have a fixed capacity or identity-scoped eviction;
  a `WeakMap` may use authoritative array/object identity for automatic release.
- Cache reset must not change canonical coordinates, selection state, or
  persisted payloads; the next render recomputes equivalent presentation data.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Local rerender in the same project | Reuse eligible cache/preview state until the interaction finishes. |
| Workspace switch | Rebuild cache containers and clear previews before the new workspace renders. |
| Project switch | Rebuild cache containers and clear previews before cached/new project state renders. |
| Segment-pair cache reaches 256 entries | Evict the oldest entry before inserting another. |
| Pointer drag ends or is canceled | Clear `finalPathGraphPreviewState` and remove temporary window listeners. |
| Reset occurs with pending timers/dialogs | Cancel timers/coordinators and resolve pending dialogs without applying stale UI state. |

### 5. Good/Base/Bad Cases

- Good: Subview pair geometry is cached in `assemblyPageSession`, capped, and
  both workspace/project switch tests prove a fresh cache object is installed.
- Base: a pointer preview lives only for one drag and becomes `null` on pointerup.
- Bad: a module-level `Map` retains project-specific geometry indefinitely, or
  a module-level preview object remains visible after switching projects.

### 6. Tests Required

- `page-session.test.mjs` seeds render-cache and preview values, calls reset, and
  asserts new cache identity, zero strong-cache entries, and a null preview.
- `session-switchers.test.mjs` seeds Assembly render cache before both workspace
  and project switches and asserts each switch installs a fresh empty cache.
- Feature runtime tests still assert cache reuse within one identity and pointer
  preview cleanup after commit/cancel.

### 7. Wrong vs Correct

#### Wrong

```js
const pairCache = new Map();
let graphPreview = null;
```

#### Correct

```js
const pairCache = assemblyPageSession.subviewRenderCache.segmentPairs;
assemblyPageSession.finalPathGraphPreviewState = nextPreview;

// Workspace/project switching calls this shared lifecycle boundary.
resetAssemblyPageSession();
```

## Scenario: Authoritative Final Path Source Length

### 1. Scope / Trigger

- Applies when normalizing GRT project views, loading persisted Final Path state, restoring the immutable GRT baseline, or exporting Final Path tables.
- Trigger: a GRT source contig is used through an internal slice, reverse slice, repeated segment, N-aware split, or terminal replacement.

### 2. Contracts

- Backend `source_length` is the complete original Dataset contig length and maps to frontend `overallLen`.
- `overallLen` does not describe the contribution length. The contribution remains `abs(end - start) + 1` in original source coordinates.
- Frontend must not infer `overallLen` from source start/end or segment length. Missing, non-positive, or too-small authoritative length is an invalid project-view contract.
- Immutable GRT baseline and persisted baseline-derived rows are canonicalized from the same authoritative source identity before display, comparison, restore, edit validation, or export.
- Current-chromosome assembly rows may additionally supply `assemblyCtgId`, `originId`, and the same `totalLength`, but may not override the backend authoritative length with a different value.
- Canonicalization preserves segment order, source interval, orientation, gap rows, hidden-primary state, q4 length/hash, and user edits.

### 3. Validation Matrix

| Case | Expected behavior |
| --- | --- |
| Same source contig appears in three reverse GRT slices | All rows share one `overallLen`; each keeps its own reversed start/end. |
| One source contig is split around an internal N run | Both rows use the full contig `overallLen`; the N-aware source intervals remain unchanged. |
| Persisted project state contains old endpoint-derived `overallLen` | Load replaces it from the matching immutable source identity before display/export. |
| Backend omits `source_length` or reports less than a source endpoint | Project-view normalization fails; do not guess a fallback length. |
| no-FASTA delivery package | Behavior matches full package because imported FAI still supplies `source_seq.length`. |

### 4. Tests Required

- GRT state test covers repeated internal source intervals with one shared complete source length.
- Assembly load test covers persisted endpoint-derived values and proves canonicalization preserves coordinates, orientation, order, hidden state, and q4 metadata.
- Restore-baseline test proves the restored rows use canonical complete lengths.
- Final Path card and TSV/project TSV tests assert displayed/exported `overall_len` uses the canonical value.

## Scenario: Subview Fragment Coordinates in Final Path

### 1. Scope / Trigger

- Applies when an anchor-derived Subview fragment is appended to Final Path.
- Trigger: the fragment range comes from pairwise evidence already projected into the current ctg display space.

### 2. Contracts

- Subview `start` / `end` are display coordinates; persisted Final Path `start` / `end` are original-source coordinates.
- Forward display ranges persist unchanged.
- Reversed display ranges project each endpoint once with `sourcePos = overallLen - displayPos + 1`; descending source order records `-` orientation.
- The effective Subview context orientation overrides the stored source orientation so local flips are materialized without mutating the source ctg.
- Backend export consumes the canonical source range directly and must not repeat the projection.
- Existing persisted user-edited rows are not inferred or silently rewritten.

### 3. Validation Matrix

| Case | Expected behavior |
| --- | --- |
| Forward fragment `101..500`, length 1,200 | Persist `101..500`. |
| Reversed fragment `101..500`, length 1,200 | Persist `1100..701`. |
| Reversed whole ctg `1..1200` | Persist `1200..1`. |
| Source ctg is `+`, but Subview-local context is `-` | Project by the local `-` orientation; keep source state unchanged. |
| Canonical App split moves aligned flank bases into a donor fragment | Exported concatenated sequence may equal the GRT split even when per-row boundaries differ. |

## Scenario: Processed Project Selected-Panel Drafts

### 1. Scope / Trigger
- Trigger: changing the selected-project edit panel in `app/frontend/src/ui/pages/workspace-page.js` for projects with `isProcessed: true`.
- Applies to workspace state fields under `initializer.edit*`, `initializer.existingProjects`, and `session.projectName`.

### 2. Signatures
- Frontend API call: `updateProject({ workspaceRoot, projectId, projectName, referenceGenomeId, primaryDatasetId, supportDatasetIds, chrAssignmentMinCoveragePercent, phasedAssemblyEnabled })`.
- Selected project source fields: `projectName`, `referenceGenomeId`, `primaryDatasetId`, `supportDatasetIds`, `chrAssignmentMinCoveragePercent`, `phasedAssemblyEnabled`, `isProcessed`.

### 3. Contracts
- For processed projects, the panel may edit only:
  - project name;
  - append-only support dataset IDs;
  - phased assembly enablement (`false -> true`).
- The effective draft sent to `updateProject` must force locked fields from the selected project source: `referenceGenomeId`, `primaryDatasetId`, and `chrAssignmentMinCoveragePercent`.
- Existing processed support datasets remain selected and cannot be removed from UI state. Newly checked support datasets may be unchecked before saving.
- If the selected project already has phased assembly enabled, the switch is locked. If it is disabled, the switch may be enabled.
- After save, update both `session.projectName` and the matching row in `initializer.existingProjects`, then rebuild the edit draft from the saved project.
- When a processed-project save appends support datasets, show the existing auto-pipeline modal style and run scoped orientation for the newly appended dataset IDs after the save succeeds.
- If the save succeeds but scoped orientation fails, keep the saved project state visible and report the orientation failure in the modal.
- Assembly support-dataset selection must recover when a project changes from zero support datasets to one or more support datasets in the same session: choose the first available support dataset, persist it, and load its support track instead of leaving `assembly.supportDatasetId` as `null`.

### 4. Validation & Error Matrix
| Case | Expected frontend behavior |
| --- | --- |
| Processed project name input changes | Update `initializer.editProjectNameInput` and allow save. |
| Existing processed support checkbox is unchecked | Ignore the event; draft keeps the existing support dataset. |
| New processed support checkbox is checked | Add dataset ID to `initializer.editSupportDatasetIds`. |
| Processed project has phased enabled and switch changes to false | Ignore the event. |
| Processed project has phased disabled and switch changes to true | Update draft and allow save. |

### 5. Good/Base/Bad Cases
- Good: user renames a processed project, checks a new support dataset, enables phased assembly, saves, and the selected-project card immediately reflects the returned project.
- Base: unprocessed projects keep the full edit behavior for reference, primary dataset, support datasets, and phased switch.
- Bad: only asserting that `updateProject` was called; this misses stale selected-panel state where the save succeeds but the visible current project does not change.

### 6. Tests Required
- Workspace panel test must drive DOM-like events for the selected processed project and assert the outgoing payload uses locked source fields.
- Workspace panel test must assert `session.projectName`, `initializer.existingProjects`, and edit draft fields all update after save.
- Service mock test must mirror backend processed-project validation so dev-mode UI tests catch the same one-way constraints.

### 7. Wrong vs Correct
#### Wrong
Return early from selected-project handlers whenever `selectedProject.isProcessed` is true.

#### Correct
Gate each control by field semantics: keep unsafe fields locked, but allow project name, support append, and phased enablement to flow through the normal save path.

## Scenario: Subview Pair History

### 1. Scope / Trigger

- Applies when changing Subview-local deletion, anchors, flips, drag offsets,
  top/bottom ordering, reset behavior, project view-state transport, or SQLite
  persistence for Subview edits.
- Subview history protects local exploratory edits only. It must never roll back
  Final Path, phased-track membership, project-level contig data, imports, or
  jobs.

### 2. Signatures

```js
assembly.subviewHistoryByKey[pairKey] = {
  version: 1,
  pairKey,
  current: editableSnapshot,
  default: editableSnapshot,
  past: [{ operation, snapshot }],
  forward: [{ operation, snapshot }],
  updatedAt: "ISO-8601",
};
```

- `editableSnapshot` contains only `topKey`, `trackPairHiddenCtgs`,
  `flippedCtgs`, `activeAnchors`, `manualAnchors`, and `dragOffsets`.
- Transport uses `subviewHistoryByKey` on both the update request and project
  assembly view-state response.
- SQLite stores one `state_json` record per `(project_id, pair_key)` in
  `project_subview_history`, with project deletion cascading to history rows.

### 3. Contracts

- Create history only after two contigs or two tracks successfully enter
  Subview. Candidate selection alone does not create a record.
- The database scopes history to a project. `pairKey` contains Subview mode,
  chromosome, and both full endpoint identities. Normalize endpoint order so
  swapping top/bottom keeps the same pair.
- Keep every valid pair and at most 50 logical steps per pair. `past` and
  `forward` share the limit; moving backward or forward adds no step.
- A new edit after rollback clears `forward`. One batch deletion and one
  completed pointer drag each count as one step.
- Record local hide/restore, original-anchor toggle, offset-anchor
  create/delete, local flip, drag, top/bottom swap, and reset.
- Do not record selection, hover, scroll, zoom, filters, evidence loading,
  loading/error state, or DOM state.
- Reset clears local hidden contigs, flips, original/offset anchors, and drag
  offsets, including edits that are currently dormant because a track member is
  filtered out; restores first-entered ordering, preserves browsing state, and
  is itself rollback-able.
- Persist Subview history and related assembly view state in one backend
  transaction.
- On pair re-entry, restore `current`, `past`, and `forward` after validating
  the record shape and the normalized pair identity.
- For `track-pair`, current main-view filters and resolved T1/T2 membership are
  applicability inputs, not history identity or validity inputs. Keep one
  continuous record for the same project, chromosome, and unordered track pair
  when filter changes add or temporarily remove ctgs.
- Newly resolved track-pair ctgs enter without local edits. Keep edits for
  temporarily absent ctgs dormant in every snapshot and reactivate them when
  the same stable identities return; back, forward, and reset continue to move
  the complete snapshots while some entries are dormant.
- Do not add current filter values or a resolved-member signature to `pairKey`,
  and do not invalidate a track-pair record merely because one saved ctg is
  absent from the current filtered pool.
- If one pair has a malformed key/version/snapshot, references a track role
  outside that pair, or no longer matches the selected track identities,
  replace only that pair with a clean default, keep all other valid records,
  and show localized feedback. Two-contig histories still require their exact
  endpoint identities.
- UI terminology is fixed: `←` means “回退上一步操作”; `→` means
  “撤销最近一次回退操作”. The right arrow restores exactly one rollback.
- Do not render the history control group before a pair successfully enters
  Subview. After entry, place one indivisible group immediately after MAPQ.
- After entry, always render the fixed action order `← → | ↺`. Keep every
  unavailable action visible but disabled; an empty `forward` stack disables
  `→` instead of removing it. All three actions use consistent decorative SVG
  icons, localized tooltips, and accessible names.
- On wide layouts, render the `Subview` title, entry guide, and selected-object
  badges in one responsive row. On narrow layouts, wrap the guide below the
  title and give the candidate badge group its own full-width line.
- Render each selected object as one integrated removable tag surface. The slot
  marker and trailing remove affordance must not draw nested borders or solid
  button surfaces; only the remove control is interactive, and long primary
  labels may truncate while their full contig name remains available by
  tooltip.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| No successful Subview pair | Do not create history or render the history group |
| `past` empty | Keep `←` visible and disabled |
| `forward` empty | Keep `→` visible and disabled |
| One rollback | Move one snapshot from `past` to `forward`; enable `→` |
| One rollback restore | Move one snapshot from `forward` to `past` |
| New edit after rollback | Clear `forward`; disable `→` |
| `past + forward` reaches 51 | Drop only the oldest step for that pair |
| Pair key/version/snapshot invalid | Reset only that pair and persist its replacement |
| Same T1/T2 resolves additional ctgs | Keep history; additional ctgs start unedited |
| Saved track-pair ctg is absent from the current filtered pool | Keep its edits dormant without invalidating history |
| Dormant ctg returns with the same identity | Reactivate its saved edits and history |
| Saved hidden state references a track role outside T1/T2 | Treat only the current pair as stale |
| Persistence fails | Roll back assembly view-state and history-row writes together |

### 5. Good/Base/Bad Cases

- Good: delete two Subview contigs, add an offset anchor, click `←` twice, then
  click `→` once; only the latest rollback is restored and state survives a
  project reopen.
- Base: enter a pair for the first time; all three actions are visible and
  disabled. Re-enter the same T1/T2 after a filter adds ctgs; existing edits are
  restored and the new ctgs are unedited.
- Bad: key history by current top/bottom order, keep an unbounded global stack,
  include pairwise evidence or resolved membership in snapshots, invalidate a
  pair because a filter temporarily removes one member, or use `→` to restore
  all rollbacks.

### 6. Tests Required

- State-machine tests cover unordered identity, one-step backward/forward,
  forward clearing, reset rollback, the 50-step limit, pair-only invalidation,
  track-pair member expansion, dormant-member preservation/reactivation, and
  back/forward/reset while dormant edits exist.
- UI/binding tests cover the fixed `← → | ↺` action order after MAPQ, pre-entry
  group hiding, per-action disabled states, responsive title/guide structure,
  localized tooltip semantics, and dispatch of all three actions.
- Transport and persistence tests cover exact camelCase payloads, fresh and
  upgraded database schemas, per-project round trips, and atomic updates.
- Run the complete Windows quality gate before commit.

### 7. Wrong vs Correct

#### Wrong

```js
history = [...history, wholeAssemblyState];
redoButton.onclick = () => restoreAllForwardStates();
```

This mixes unrelated browse/cross-domain state, grows without a pair boundary,
and gives `→` the wrong product meaning.

#### Correct

```js
const result = commitSubviewHistoryOperation(assembly, {
  nextSubview,
  operation: { kind: "toggle-anchor" },
});
const restored = restoreSubviewHistoryRollback(result.assembly);
```

The shared state machine records one editable snapshot for one normalized pair
and moves one step per click.
