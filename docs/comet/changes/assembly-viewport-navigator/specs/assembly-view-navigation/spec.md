# Assembly viewing ranges and independent ruler intervals

## Purpose and surfaces

Main and local assembly views expose their visible genomic interval directly through an overview navigator. Final Path intentionally does not expose navigation controls and retains a ruler-interval parameter only. This capability changes visualization preferences and interaction, not assembly or sequence data.

The main view, ordinary local pairs, local track pairs and custom local compositions are supported. Each navigator uses the complete domain of its own rendered content, respecting coordinate origins, local offsets, reversal and existing domain padding/geometry. A local domain is not automatically the entire reference chromosome. Reference, local and assembled Final Path coordinate semantics remain distinct and correctly labelled.

## Main/local layout

A compact dedicated navigation row appears between the current toolbar and the coordinate ruler/track graphic. The horizontal overview axis aligns with the track plotting area rather than the name gutter. It is outside the horizontally scrolling graphic and is not a floating overlay. Main and local views have separate instances/state.

The row contains a mouse/hand mode switch, left/right half-window navigation buttons, zoom-out/zoom-in buttons, the complete-domain overview axis with a selected visible interval, an editable visible-span field with explicit genomic units, and Fit all. These are synchronized presentations of one interval, not independent scale variables. Small drag handles have usable interaction targets without falsely displaying a large selection for a very small actual range. New controls and feedback support the App's Chinese/English localization and accessibility conventions.

The old minimum-tick-unit and maximum-visible-count inputs are absent. Ruler settings stay in a Display settings entry in the existing toolbar, not alongside the navigation row's primary viewing-range input.

## Visible interval operations

Dragging the selected interval translates it with unchanged span. Dragging an edge changes span while preserving the opposite edge. Both are bounded by the complete domain and finite supported rendering range. Native horizontal scrolling of the graphic updates the overview interval and input value, and overview operations update the graphic, without event loops or duplicate listeners.

Zoom-in narrows the interval and zoom-out widens it about the current genomic center; domain bounds may require clamping. Manual span entry applies the same center rule. Fit all selects the complete domain and fits its content to the available plot width; it is not application fullscreen. These actions do not change track height or font size.

Visible-span input supports explicit kb/Mb units, conversion to the internal coordinate scale, and legible output. Positive values outside the supported domain/render range are bounded or rejected with explicit feedback and actual applied values; malformed, nonfinite, zero or negative input does not poison state or silently edit the graphic. Empty data has a defined noninteractive/disabled navigation state rather than a fabricated normal chromosome range.

Graph resize preserves the represented interval wherever possible rather than using tick count to silently change the amount of sequence viewed. Domain/content changes restore an applicable interval or clamp/fallback safely. Existing entry-state/filter inheritance may initialize local preferences, but subsequent main/local navigation and ruler preferences are independent. Existing persistence ownership remains respected, and restored legacy preferences retain meaningful prior main/local scale where applicable.

## Ruler density

Ruler interval is independent of visible span. Automatic interval selection chooses legible genomic spacing based on the current interval, plot width and label/font measurements; manual spacing specifies an explicit interval. A ruler preference change never changes graph scale, contig pixel widths, scroll position, the navigator selection, data filtering, or any other view's preferences. Label collision handling must not create unbounded tick lists or disguise a change to biological scale.

Main/local ruler control lives inside Display settings and defaults to Auto. Removing the legacy maximum-count control does not leave a hidden live multiplier that still couples manual ruler spacing to graph width.

## Final Path header and semantics

Final Path retires both legacy inputs in the same change. Its existing App header shows a single ruler-unit/interval control and no overview axis, visible-span input, fit-all control, or zoom buttons. The remaining interval is a ruler setting only, not a replacement zoom mechanism; changing it does not change segment geometry, order, assembled coordinates or sequence export.

Final Path fits the complete assembled path to the available plot width on render and resize, so reaching the last segment does not require horizontal navigation. Its one ruler interval control defaults to Auto and permits manual spacing. Automatic spacing follows the actual width/font measurements; manual interval changes only the ruler and never graph width. Legacy minimum-unit/maximum-count scale preferences cannot override the full-path fit. An empty path remains a defined empty state, and very short and long paths use bounded geometry while preserving actual assembled-coordinate semantics.

Final Path preferences remain separate from main/local controls. Empty/short/long paths and existing segment interactions/exports must remain valid under the confirmed policy. This capability does not redesign Server/offline reports.

## Compatibility and invariants

Accept old saved minTickUnitKb/maxTickCount preferences without losing project data, edits, filters or unrelated preferences. Interpret their former product for main/local range compatibility when needed, then use independent range and tick state. Final Path's obsolete scale count is not authoritative and cannot restore the former zoom coupling. Avoid changing existing supported coordinate precision or serialization contracts unnecessarily.

View-only interactions do not enter assembly edit history or modify contig offsets/orientations, anchors, selections, path segment order, export coordinates or alignment evidence. Existing editor drag and blank-area box selection retain their contracts in mouse mode; hand mode intentionally owns primary plot drags for viewport panning only. Existing focus, history and data actions retain their contracts. Pointer ownership must distinguish these modes and cannot edit contigs while hand-panning, leak capture, or leave permanently active drag state. Cancelled drags leave consistent visualization without producing data edits.

## Scope and acceptance mapping

Brief A1-A17 is the authoritative acceptance matrix. A1-A5 cover main/local layout and synchronized range controls; A6 covers independent rulers; A7-A8 cover modes, state isolation and compatibility; A9 preserves editor/data invariants; A10-A12 define Final Path's interval-only surface and complete-path fit policy; A13 covers responsive/localized/accessible behavior; A14 covers executable regression/build and truthful interaction evidence; A15 covers modifier-free wheel zoom, A16 mouse/hand ownership and cleanup, and A17 bounded half-window movement.

Pinch zoom, box zoom, vertical zoom, native fullscreen, raster previews, remote deployment and release installers are non-goals. Wheel zoom, mouse/hand panning and half-window movement are included; no Ctrl/Space combination is required. The Windows host is the required frontend dependency/test/build environment. Native desktop checks that were not executed remain unverified; screenshots, browser tests, and pure geometry tests are not interchangeable acceptance evidence.


## Main/local wheel zoom

Ordinary wheel over a main/local plot or the overview axis zooms in both mouse and hand modes without modifier keys. Wheel-up zooms in and wheel-down zooms out. Plot zoom preserves the genomic coordinate under the pointer at its screen position wherever domain bounds allow; overview-axis zoom preserves the current viewing center. Both use the same bounded interval/scale model as the buttons and span input and update range box, graphic, ruler and displayed span together. Normalize wheel delta units and coalesce high-frequency events rather than creating unbounded renders or persistence writes.

Intercept wheel only on the intended plot or overview axis, not on form inputs, menus, unrelated toolbar controls, track-name gutter or the rest of the page. Empty/invalid domains do not produce false zoom state. Prevent native page/browser effects for handled chart wheel events; events elsewhere keep their normal behavior. Existing horizontal-scroll transport can still synchronize the range. Final Path receives no new wheel-zoom behavior.

## Mouse/hand interaction modes

Each main/local navigation row has a visible mouse/hand mode switch. A new viewing context defaults to mouse; the setting is independent between main and local views. Mouse mode retains normal contig selection/edit drags and blank-area box selection. Hand mode gives ordinary primary-button plot dragging to viewport pan, with unchanged span and domain clamping, and no contig move or box-selection operation. Show a hand cursor and a grabbing cursor while panning, and visibly indicate the selected mode. Overview-range dragging remains available regardless of plot mode.

No Space/Ctrl combination is required. Ensure exclusive pointer ownership before existing editor/selection handlers start; suppress accidental clicks resulting from a pan. Final Path's existing segment-edit gestures are unaffected, and it has no new mode switch. Clean up pan capture and temporary state on pointer cancellation, mode changes, window blur, content replacement and unbinding. Repeated renders/partial panel refreshes do not multiply gesture owners. Focused numeric/text editing must not be interpreted as a chart gesture.

## Half-window movement

The main/local navigation row exposes separate left/right icons with accessible names/tooltips that state Move left/right half a window, not Undo/Redo. For current interval [L,R] with span S=R-L, left requests [L-S/2,R-S/2] and right requests [L+S/2,R+S/2]. Apply domain clamping without changing S; near a boundary move only the remaining distance. Disable a direction when no movement is possible, and disable both when the entire domain is visible. These buttons work in either mouse/hand mode, update all representations of the interval, create no edit history, and are absent from Final Path.
