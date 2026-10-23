# Main / Local View fragment editing contract

## Agreed behavior

- Object identity includes the view instance, source identity, inclusive source interval and orientation. Anchor-derived Local View fragments are not automatically real Main View entities.
- Delete contig / Delete current fragment has two scopes: current Local View only, or synchronize deletion to Main View. Remove the redundant Remove from Local View menu item. Local deletion must survive anchor changes and never delete the whole parent when a fragment was clicked.
- Split contig / Split current fragment has two scopes: current Local View only, or split and synchronize Main View. A synchronized interval deletion is an atomic split-and-delete operation, including dependency inspection and one Main View history entry.
- Undo Split acts only in the current Local View, with Undo Left Split / Undo Right Split and no scope selector. It may restore the exact adjacent deleted fragment from its deletion record before joining compatible same-source, same-orientation intervals. It never restores, joins or otherwise mutates Main View entities. Main View Undo Split restores/joins its own native entities, in one undoable Main history operation.
- Main View flip changes the selected real entity. Local View flip changes only the clicked local object/interval, including after splitting or partial deletion. Flip must not move siblings or restore removed intervals.
- Creating an anchor only partitions hit-testing/display intervals; dragging or box-selecting an anchor interval must not create new local objects or cut records. Existing explicitly split/edited objects remain independently movable.
- A plain drag moves only the clicked object, not every sibling with the same source/group. A drag started on a boxed selected object translates the explicit visible selection by one common horizontal delta, preserving each object's prior offset and relative placement. Starting on an unselected object does not drag the previous selection. Apply in Main View and every Local View mode; one gesture is one history operation. Do not change source intervals or fabricate N gaps.
- Main DS member cards represent real Main View entities, not virtual local fragments. Refresh after real mutations; local-only edits must not change main member lengths/counts. Show source ranges where required to disambiguate real fragments.
- Local contig menu order: Add to Final Path; Move to other lane; Flip; Split; Undo Split; Delete. Keep anchor-only operations in the anchor/hit context. Show only supported actions and explain disabled boundaries.
- Preserve Main / Local / Final Path history ownership, scoped dependencies, viewport and independent layout. Do not silently rewrite Final Path when performing local edits.

## Validation and delivery

Use targeted state/controller/rendering tests and Windows-host frontend/backend/Tauri checks. Do not use WSL Node against Windows node_modules. Remove generated frontend dist after verification. Native visual interaction acceptance is separate from automated checks. Commit and push only scoped task changes; do not rebuild or replace published installers without a new release request.

## Implementation history

The stage snapshots below record earlier checkpoints. The final integration audit supersedes their then-pending scope.

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
- Local undo-split requires one source family, lane, dataset/source context, effective orientation and contiguous source bases (live or explicitly recovered from a deletion record). The merged boundary suppresses the corresponding visual anchor cut, rather than immediately re-splitting the merged object. Invalid persisted coverage, overlapping backing instances and duplicate backing IDs fail closed.
- Composition rendering projects and jointly clips both alignment endpoints to each surviving interval, including reverse strands and multiple real backing IDs. N-region annotations are clipped as well. Manual and stored evidence anchor endpoints follow surviving source bases. Local member hover/manager labels show source ranges.
- Local fragment append expands the chosen interval into its actual backing ranges, in the effective orientation, with one Final Path persistence operation. Missing backing data aborts the append rather than adding a whole parent or a partial path. Other local edits do not rewrite Final Path.
- Successful Main View reloads rebind primary-source local objects and composition history snapshots to the current real entities. Main split/undo does not collapse independent local partitions; main-deleted bases are clipped from ordinary local composition snapshots; explicitly restored local objects can retain read-only archived backing intervals. Evidence cache identity includes backing IDs/ranges/orientations, so a stable local identity cannot reuse stale parent evidence.
- Native `edit-local-fragment` preparation validates source instance, exact expected parent ranges/orientations, chromosome/project/primary-dataset eligibility, unique targets and complete non-overlapping coverage. Requested interval boundaries, cuts, tombstones, dependency changes and layout offsets share one transaction and Main View history entry. At the Stage 2 checkpoint this primitive was not yet connected to frontend synchronized menu entries; that connection is completed in the final integration below.
- Native split converts adopted Final Path ranges to immutable source locators; deleting a real child does not silently delete already-adopted DNA. Tests verify retained source intervals, tombstone lineage, unaffected other paths, and undo/redo. The final synchronized UI dependency confirmation explains this behavior explicitly.

Stage 2 verification snapshot (2026-10-23, source checkpoint; overall goal still active):

- Windows frontend: 1,652 tests passed; production build passed (existing large-chunk warning only).
- Windows backend: 305 tests passed, 2 existing ignored; strict all-target Clippy passed. Six new native tests cover interval deletion, reverse placement, joined-real-sibling cuts, invalid/stale scopes, immutable Final Path locators/lineage and rollback after a later dependency failure.
- This checkpoint does not claim synchronized UI, direct virtual-anchor gestures, Main DS annotations or native-window acceptance. These were completed in the subsequent integration below. No installer/release/test-data assets were changed.


## Final integration audit (2026-10-23)

| Requirement | Implementation and regression evidence |
| --- | --- |
| Scoped synchronized split/delete | `subview-fragment-sync-runtime.js` connects workflow contracts to native `edit-local-fragment`. Dependency inspection and explicit confirmation precede one native history operation. Exact source preconditions, serialized persistence, stale-context cancellation and post-commit reload-failure guards are covered by `subview-fragment-sync.test.mjs` and `workflow-api.test.mjs`. |
| Anchor display intervals vs editable objects | Explicit fragment-scoped edits may create source-owned objects. Dragging and box selection must never materialize anchor intervals; they address the owning ctg or already edited member. Three local modes, overview/zoom, both directions, local flips, explicit split siblings and selected multi-lane motion are covered by `subview-fragment-gestures.test.mjs`. |
| Explicit box-selection movement | Main and Local View drag only the clicked object unless it belongs to the explicit visible selection. Selected members retain their individual initial offsets plus one shared delta. No implicit source-family movement. Stage 1 native atomic-target checks and final local gesture tests cover this contract. |
| Delete/split/flip/merge and menu order | Local controller/model tests cover clicked-range operations, same-source contiguous local-only merging, stale dialogs and the agreed menu order. Main native tests cover real-child flip after splitting and partial deletion without changing the sibling. No redundant Remove from Local View context action. |
| Main DS cards reflect real data | `main-member-local-state.js` annotates real entities without increasing real counts/lengths for virtual pieces. Cards show source ranges, local deletion/coverage, split/merge, orientation and movement annotations. Local changes refresh only the member panel, not main geometry. Deleted source ranges pass through CLI/Tauri/dev bridge. `main-member-local-state.test.mjs` covers counts, rendering and refresh. |
| History and persisted source identity | `subview-fragment-history.js` preserves legacy baselines, drag offsets, anchors, undo and redo. A source-owned backup permits later native parent retirement without stale IDs. `subview-fragment-reconcile.js` rebinds primary/phased members and clips main-deleted bases from local history. Tests cover legacy undo followed by native split and redo, JSON round trips, and local deletion surviving anchor disable/reopen/anchor-only undo. |
| Final Path ownership | Local append uses selected backing intervals; local edits do not mutate adopted paths. Native synchronized edits preserve adopted DNA as immutable source locators with lineage. Confirmation states this explicitly. Backend interval tests cover dependencies, rollback, deletion and history. |
| GRT and auxiliary/phased views | `subview-fragment-grt.js` clips overlays/evidence and maps anchor source points through surviving ranges/orientation. Ambiguous duplicate placements fail closed. Phased native and displayed orientations are separate; no wrong-track candidate fallback. `subview-fragment-grt.test.mjs` and `subview-fragment-phased.test.mjs` cover clipping, deleted anchors, lineage and negative orientation. |
| Viewport and persistence | Local gestures/actions preserve rendered scale and viewport. One gesture commits one local operation. Synchronized edits flush prior state and persist within the mutation coordinator without nested-queue deadlock. Cancel/stale/project-switch tests prevent old-context writes. |

### Final local validation

- Windows-host frontend: **1,721 tests passed**, no failures; production build and Windows Light quality gate passed. Existing large-bundle advisory only. Generated `dist/` is removed after verification.
- Windows-host backend: **306 passed, 2 existing ignored**; strict all-target Clippy passed.
- Windows-host Tauri: **18 passed**; formatting and strict Clippy passed. Isolated debug native build passed, with embedded icon sizes/transparency verified.
- Isolated native artifact: `D:\tools\gpm-preview-verification-target\debug\gpm_next_desktop.exe`; SHA-256 `00265F8679E3E1C4CC86A33A4F6327DF90A226D072025A3E5DD5F6FB8F9C5F29`. The interval-edit native source marker was also checked. This is a verification artifact, not a newly published installer.
- Automated state/controller/render-contract checks and a native build **do not constitute native GUI interaction acceptance**. No user desktop process was terminated or replaced. Gesture tests use a lightweight event/DOM contract harness rather than a browser.
- Published installers, release tags, official test-data assets and project workspaces are not modified by this delivery. Repository closure requires a scoped commit/push and successful Quality jobs for that exact final revision; old-checkpoint CI is not evidence for a newer revision.


### Viewport regression follow-up (2026-10-23)

- Replacing a local panel can leave a queued scroll-to-zero event on its detached scroll element. That event must not overwrite the current world viewport or persisted pixel position. Shared Main / Local / Final Path scroll binding now accepts only the live node's latest binding in the same workspace/project/view context; rebinding removes the prior listener.
- Undoing the first interval edit can restore a legacy two-contig/track-pair presentation within source-owned composition history. This is not a new view: restore its saved world position using the rendered origin/scale, and keep that world position current while scrolling, so redo does not jump back.
- `viewport-edit-preservation.test.mjs` uses real rendered anchor-fragment attributes with controlled scroll-event delivery. It checks deletion, flip, split, local merge, lane movement, undo/redo and delayed evidence-style rerenders across all three local modes. Main/Local/Final Path cases also reject detached and old-context events, retain one live listener, and allow genuine scrolling. These are automated regression checks, not native-window visual acceptance.
- Follow-up validation: **1,740 Windows-host frontend tests passed** (19 new viewport regressions); production build and Windows Light quality gate passed. No backend, release assets or test-data changes are needed for this frontend-only fix.


### Anchor retention and Main DS card follow-up (2026-10-23)

- Local interval deletion must preserve every anchor whose two source endpoints survive. An edit must not clear unrelated anchors because an alignment hit key changes after clipping. Existing composition views now capture endpoint descriptors for older hit-key-only evidence anchors before partitioning members; already source-owned descriptors remain authoritative and are not mirrored again.
- Anchor regression tests cover an interval containing no anchor (all anchors survive), an interval containing one endpoint (only its anchor is invalidated), both sides of the deletion, all Local View modes, local reversal, persistence round trips, local undo/redo, and Main View history reload followed by local undo/redo. Main and Local history operations remain independent.
- Main DS cards use a uniform responsive grid: a short name plus real length in the heading, one authoritative source-range row, and a compact local-status row. Generated interval text is omitted from the visible name only when a real source range is available; split suffixes remain. Original names and detailed local coverage remain in tooltips/accessibility labels. This is presentation only: no source entity is renamed and local fragments never inflate real member counts/lengths.
- Static isolated Chromium checks cover wide light and narrower dark card layouts, using synthetic data matching the reported ranges. They do not load a user project and are not native desktop acceptance.
- Validation for this follow-up: **1,759 Windows-host frontend tests passed**, production build and Windows Light quality gate passed. Published installers, backend code and retained test data are unchanged.


### Split-marker consistency follow-up (2026-10-23)

- A manual fragment's nonzero source start/end is not by itself evidence of a new cut: an exterior endpoint inherited from an N-delimited parent retains its original gap metadata. The shared marker resolver excludes these natural N boundaries while retaining real cuts even when the sibling is moved, hidden or deleted.
- Main View, two-contig, track-pair and composition rendering share the same source-cut projection and marker geometry. Marks live inside the ctg's group, follow its effective orientation and position, and never create sequence/N bases or alter anchor state.
- Local fragment metadata keeps real Main View cuts (`nativeCuts`) separate from explicit local cuts (`manualCuts`). Anchor-only visual partitions do not acquire manual markers. Main reload/history reconciles real cuts from current backing entities, without depending on the optional composition candidate cache or erasing independent local cuts. At this checkpoint a local merge removed only its local cut. The follow-up below supersedes this: an explicit local Undo Split also suppresses that internal Main cut in the local presentation, without changing Main.
- Regression coverage checks both native orientations and local flips, the reported false N-edge mark, all three Local View modes, local movement/deletion/merge, persistence, local undo/redo and Main split undo/redo projection. Repeated splits of an N-delimited parent retain its retired-parent lineage rather than dropping later descendants from Local View. **1,779 Windows frontend tests passed**, as did the production build and Windows Light gate. These are source/render-contract checks, not native-window visual acceptance. No backend, installer or retained test-data changes were required.


## 2026-10-23 follow-up: recoverable deletion, boundary anchors, and confirmation consent

- **撤销分割** is the Local View menu name; its children are **撤销左侧分割 / 撤销右侧分割**. There is no second scope selection. An adjacent deleted fragment can be restored and joined locally, including after a synchronized Main deletion. This is distinct from the history controls: local history undoes local presentation edits; Main history undoes native edits.
- Anchor-defined fragment deletion materializes source-owned fragments and keeps a deletion archive, including removed anchors. Explicit Undo Split consumes only the matching adjacent archive, not an old whole-view snapshot. Ordinary anchor toggling, history reconciliation or view reload must not restore missing source bases implicitly. No synthetic Ns, guessed intervals, unrelated copies, lanes or source groups are used.
- A synchronized deletion is one atomic native split-and-delete history operation. It does **not** add a duplicate Local deletion entry. Recovery metadata is retained in local snapshots without consuming earlier local operations. Local-only deletion and local Undo Split remain undoable/redoable local operations.
- A local restoration may read evidence from a deleted native fragment without restoring that fragment in Main. Such source intervals survive project-state normalization/reload. Native sync still requires live valid backing entities. Final Path append validates every backing fragment before writing; existing adopted paths are not changed by a local restoration.
- Main Undo Split can restore an exact adjacent native deletion record and merge in the same transaction. Stale identity/range/orientation and dependency checks still apply; any failure rolls back restoration as well. Undo/redo snapshots include the tombstone and both source entities, including projects that have no saved view-state row.
- An anchor on a shared cut survives on the remaining same-instance side. `sourceCutAfter` records its source boundary through orientation changes, serialization and rendering. Only anchors strictly inside the deleted interval disappear. Restoring the fragment locally may restore its archived anchors when both endpoints are still available.
- Manual deletion cuts are introduced only at real adjacent boundaries, not at natural terminal/N-delimited edges. Local Undo Split hides the merged cut locally; untouched split marks continue following their contigs across Main/Local views.
- Similar secondary confirmation dialogs share an unchecked **本次运行不再询问此类操作** checkbox. Consent is held only in application memory and keyed by explicit action type (local-to-main split/delete are separate). Cancellation, stale dialogs, notices and typed-input prompts never grant consent. Restarting clears it; confirmations skipped this way do not bypass inspection, validation or native preconditions.
- Regression checks cover the rendered history button after local deletion, shared-boundary anchors in all local modes, reversed source orientation, local restoration through JSON reload and undo/redo without Main changes, atomic native restoration with undo/redo, and confirmation consent isolation. These automated checks do not replace native App visual acceptance on the user's project. No release or retained test-data assets are changed.


## 2026-10-23 correction: anchors are not implicit drag-time splits

- The former gesture preprocessing materialized anchor intervals on pointer movement and box selection. This created independent local objects without an actual Split command, which looked like a split with missing markers. That preprocessing and its partition helper have been removed; no ordinary gesture mutates source topology or silently promotes comparison mode.
- Dragging anywhere on an uncut ctg (including an anchor hit zone) moves the owning ctg. Box selection selects existing ctgs/members; selected members translate together. Explicitly split pieces and retained pieces from explicit fragment edits remain independently movable. Cancellation leaves state/history untouched; a completed move is one local history operation.
- Local Undo Split requires a recorded `manualCuts` or `nativeCuts` boundary in addition to source/lane/orientation/adjacency checks. Adjacent anchor-only intervals do not enable it, and direct/stale invocations return unchanged rather than materializing a fake split. Partial deletion still creates recoverable genuine boundaries.
- Suppressed cut metadata survives transient anchor slicing at member edges. Only a new explicit split (or fragment deletion at that boundary) clears the suppression. This prevents anchor hit-testing from resurrecting an already undone cut, while repeat explicit splits retain their visible marks.
- Tests exercise real rendered anchor hit zones with pointer/box events in all three local modes, overview/zoom, both movement directions, flips, cancellation, multi-lane selection and history. Explicit split marks are checked before/after movement and undo/redo. Existing user project states are not silently merged or migrated; use Local View history to undo a previous unintended drag.
