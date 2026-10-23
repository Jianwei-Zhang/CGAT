# Main / Local View fragment editing contract

## Agreed behavior

- Object identity includes the view instance, source identity, inclusive source interval and orientation. Anchor-derived Local View fragments are not automatically real Main View entities.
- Delete contig / Delete current fragment has two scopes: current Local View only, or synchronize deletion to Main View. Remove the redundant Remove from Local View menu item. Local deletion must survive anchor changes and never delete the whole parent when a fragment was clicked.
- Split contig / Split current fragment has two scopes: current Local View only, or split and synchronize Main View. A synchronized interval deletion is an atomic split-and-delete operation, including dependency inspection and one Main View history entry.
- Merge Local Fragments acts only in the current Local View, with left/right actions. Merge only compatible, same-source, contiguous surviving intervals; never resurrect a deleted interval or merge the underlying Main View entities.
- Main View flip changes the selected real entity. Local View flip changes only the clicked local object/interval, including after splitting or partial deletion. Flip must not move siblings or restore removed intervals.
- A plain drag moves only the clicked object, not every sibling with the same source/group. A drag started on a boxed selected object translates the explicit visible selection by one common horizontal delta, preserving each object's prior offset and relative placement. Starting on an unselected object does not drag the previous selection. Apply in Main View and every Local View mode; one gesture is one history operation. Do not change source intervals or fabricate N gaps.
- Main DS member cards represent real Main View entities, not virtual local fragments. Refresh after real mutations; local-only edits must not change main member lengths/counts. Show source ranges where required to disambiguate real fragments.
- Local contig menu order: Add to Final Path; Move to other lane; Flip; Split; Merge Local Fragments; Delete. Keep anchor-only operations in the anchor/hit context. Show only supported actions and explain disabled boundaries.
- Preserve Main / Local / Final Path history ownership, scoped dependencies, viewport and independent layout. Do not silently rewrite Final Path when performing local edits.

## Validation and delivery

Use targeted state/controller/rendering tests and Windows-host frontend/backend/Tauri checks. Do not use WSL Node against Windows node_modules. Remove generated frontend dist after verification. Native visual interaction acceptance is separate from automated checks. Commit and push only scoped task changes; do not rebuild or replace published installers without a new release request.

## Implementation progress

### Stage 1: explicit-selection horizontal drag

Implemented for existing Main View primary-track entities and Local View members in track-pair, two-contig and composition modes:

- Plain drag targets only the clicked entity; same-source siblings are no longer implicitly collected.
- A selected leader translates the explicit visible selection, preserving individual prior offsets and one common delta. An unselected leader does not move the old selection.
- Composition selections retain entity keys, highlight selected instances and avoid moving another presentation sharing a backing contig ID, including in preview.
- Main View validates same-track/project/chromosome membership, unique targets and a rigid common delta; it records every affected target in one persistent history entry. Local View commits one local history entry.
- Existing local box-selection Delete handling also works for two-contig/composition selections without modifying Main View data. Batch deletion freezes the pre-delete rendered scale and viewport in track-pair/composition modes, retaining surviving member positions and undo layout.
- Automated coverage includes both directions, zoomed/full-range previews, either selected leader, cancellation, context changes, unequal initial offsets, instance isolation, and undo/redo.

Not implemented in Stage 1 (see Stage 2 progress below): independent anchor-derived interval objects; interval-scoped local delete/flip/drag; synchronized partial deletion/splitting; local fragment merging; the new scoped menu layout; Main DS card local-state annotations. The agreed behavior above remains the specification for these next stages, not a claim that their UI or data paths are already shipped.

Automated checks are not native-window acceptance. A running desktop process can retain an older Rust backend even when Vite reloads the frontend. Do not terminate it or overwrite its locked executable; use an unused isolated build target and explicitly distinguish that artifact from the user's running app. Published installers remain unchanged.

### Stage 1 verification snapshot (2026-10-23)

- Windows frontend: 1,621 tests passed; production build passed (existing large-chunk warning only).
- Windows backend: 299 tests passed, 2 existing ignored; format and strict Clippy passed.
- Windows Tauri: 18 tests passed; format and strict Clippy passed.
- The default debug executable was locked by the user's running app. An unused `D:\tools\gpm-preview-verification-target` build succeeded and passed embedded-icon validation without terminating the app. This does not update or visually validate the running window.


### Stage 2: source-owned Local View objects and atomic native primitive

Implementation now includes:

- `subview-fragment-model.js` stores inclusive source intervals and a validated list of real backing entities with their source ranges/orientations. Local fragments may share one backing entity; a local join may reference multiple real entities. Neither operation merges or deletes those real entities.
- Local context actions preserve the clicked anchor range and promote it plus its remainders to independent objects. Local flip, delete, manual split and left/right merge commit one local history operation and preserve the rendered scale/viewport. Split dialogs reject stale contexts; cancellation does not persist an edit.
- Local merging requires one source instance, lane, dataset/source context, effective orientation and contiguous surviving bases. The merged boundary suppresses the corresponding visual anchor cut, rather than immediately re-splitting the merged object. Invalid persisted coverage, overlapping backing instances and duplicate backing IDs fail closed.
- Composition rendering projects and jointly clips both alignment endpoints to each surviving interval, including reverse strands and multiple real backing IDs. N-region annotations are clipped as well. Manual and stored evidence anchor endpoints follow surviving source bases. Local member hover/manager labels show source ranges.
- Local fragment append expands the chosen interval into its actual backing ranges, in the effective orientation, with one Final Path persistence operation. Missing backing data aborts the append rather than adding a whole parent or a partial path. Other local edits do not rewrite Final Path.
- Successful Main View reloads rebind primary-source local objects and composition history snapshots to the current real entities. Main split/undo does not collapse independent local partitions; main-deleted bases are clipped from local composition snapshots. Evidence cache identity includes backing IDs/ranges/orientations, so a stable local identity cannot reuse stale parent evidence.
- Native `edit-local-fragment` preparation validates source instance, exact expected parent ranges/orientations, chromosome/project/primary-dataset eligibility, unique targets and complete non-overlapping coverage. Requested interval boundaries, cuts, tombstones, dependency changes and layout offsets share one transaction and Main View history entry. This backend primitive is **not yet connected to the frontend synchronized menu entries**.
- Native split converts adopted Final Path ranges to immutable source locators; deleting a real child does not silently delete already-adopted DNA. Tests verify retained source intervals, tombstone lineage, unaffected other paths, and undo/redo. Dependency inspection/confirmation must explain this behavior when the synchronized UI is connected.

Remaining required work for the full objective (do not mark the overall goal complete):

1. Connect synchronized split/delete through workflow contracts and the native action, with dependency inspection, explicit confirmation, stale/context guards, error recovery, local baseline/history migration and fresh DS data. Verify legacy two-contig/track-pair history baselines as well as existing compositions.
2. Materialize anchor-derived intervals for direct drag and box selection, not only context actions. A gesture must retain one undo entry, stable instance selection, both movement directions, cancellation and viewport behavior; an untouched sibling must not move.
3. Audit Main DS member cards against real Main View entities, including source ranges, local-only annotations, deleted members and refresh after synchronized mutations. Do not count virtual pieces as real members.
4. Audit GRT anchors/overlays and auxiliary/phased source representations against the new interval projection. Complete regression coverage for cross-surface history ownership and persistence/reopen.
5. Run final scoped and complete Windows frontend/backend/Tauri checks, isolated native build where the running app locks the normal target, and exact-head CI. Remove generated frontend dist, commit/push only scoped files, and keep native-window acceptance separate from automated evidence. Published installers/test data remain unchanged.


Stage 2 verification snapshot (2026-10-23, source checkpoint; overall goal still active):

- Windows frontend: 1,652 tests passed; production build passed (existing large-chunk warning only).
- Windows backend: 305 tests passed, 2 existing ignored; strict all-target Clippy passed. Six new native tests cover interval deletion, reverse placement, joined-real-sibling cuts, invalid/stale scopes, immutable Final Path locators/lineage and rollback after a later dependency failure.
- This checkpoint does not claim synchronized UI, direct virtual-anchor gestures, Main DS annotations or native-window acceptance. These remain in the required-work list above. No installer/release/test-data assets were changed.
