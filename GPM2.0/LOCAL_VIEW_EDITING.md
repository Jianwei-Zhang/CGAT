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

Not yet implemented by this stage: independent anchor-derived interval objects; interval-scoped local delete/flip/drag; synchronized partial deletion/splitting; local fragment merging; the new scoped menu layout; Main DS card local-state annotations. The agreed behavior above remains the specification for these next stages, not a claim that their UI or data paths are already shipped.

Automated checks are not native-window acceptance. A running desktop process can retain an older Rust backend even when Vite reloads the frontend. Do not terminate it or overwrite its locked executable; use an unused isolated build target and explicitly distinguish that artifact from the user's running app. Published installers remain unchanged.

### Stage 1 verification snapshot (2026-10-23)

- Windows frontend: 1,621 tests passed; production build passed (existing large-chunk warning only).
- Windows backend: 299 tests passed, 2 existing ignored; format and strict Clippy passed.
- Windows Tauri: 18 tests passed; format and strict Clippy passed.
- The default debug executable was locked by the user's running app. An unused `D:\tools\gpm-preview-verification-target` build succeeded and passed embedded-icon validation without terminating the app. This does not update or visually validate the running window.
