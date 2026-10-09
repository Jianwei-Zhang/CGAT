# Outcome

Make assembly-page navigation express the user's viewing range directly instead of requiring the product of a tick interval and a maximum tick count. Main and local views get an overview range navigator; Final Path retires the same legacy scale controls but exposes only a ruler-interval parameter, without a navigator or span input.

# Scope

- GPM2.0 App assembly main view and all supported local-view modes (ordinary pair, track pair, and custom composition).
- A separate overview navigator in each main/local view, below its existing toolbar and above the ruler/track graphic.
- Main/local range panning, range-edge resizing, zoom buttons, fit-all, and editable visible span with explicit genomic units. Add direct wheel zoom without modifier keys, a mouse/hand interaction-mode switch in each navigation row, and left/right half-window movement buttons.
- Main/local ruler settings inside the existing toolbar's Display settings, defaulting to automatic with an optional manual interval.
- Final Path's App graphic: remove both legacy controls, retain only a ruler interval control in its existing header, and do not add the new overview navigator, visible-span input, or zoom buttons.
- Decouple ruler density from horizontal graph scale, preserve existing data/editor semantics, and accommodate legacy saved preferences.

# Non-goals

- Native application fullscreen, pinch zoom, box-selection zoom, a new vertical zoom mechanism, or a raster/minimap preview of the track content. No Ctrl/Space combination is required for the new wheel or hand-pan controls.
- Changes to contig placement/orientation, alignment filters, assembly editing history, Final Path path composition, export data, or biological coordinates.
- Server/offline report redesign, installer release, remote deployment, new branches/worktrees, or delegated/parallel agent development.

# Acceptance examples

- A1: Main and local views remove the visible legacy 最小刻度单位(kb) and 最多可展示数 fields. Each view renders one navigator below its own toolbar and above its graphic; the overview remains outside the horizontally scrolling content and its axis aligns with the plot area rather than the track-name gutter.
- A2: Dragging the overview selection translates the actual visible genomic interval without changing its span, stays within the complete view domain, and updates the graphic. Scrolling the graphic updates that same overview selection and span display; neither direction creates a feedback loop.
- A3: Dragging either selection edge changes the visible span with the opposite edge stationary, within the valid domain and supported rendering limits. The overview, input value, ruler, and graphic remain synchronized; completing or cancelling a drag does not edit contigs.
- A4: Main/local zoom-in decreases the span and zoom-out increases it while keeping the current genomic center wherever domain bounds allow. Fit-all selects the entire current domain and displays all current content; these controls do not change font size or track height.
- A5: The navigator row offers an editable visible-span value with explicit kb/Mb units and meaningful unit conversion. Committing a valid span keeps the current center subject to domain bounds and synchronizes the range selection; invalid or unsupported values receive actionable feedback rather than NaN, hidden geometry changes, or an unbounded render.
- A6: Main/local Display settings default to automatic tick spacing and allow a manual interval. Changing tick spacing only changes ruler ticks/labels, not the visible interval, contig pixel geometry, scroll position, alignment filtering, or the other view's preferences. Automatic spacing remains legible at the current plot/font width.
- A7: Main and local navigation state remain independent after entry. Ordinary, track-pair, and composition local modes all navigate their own complete rendered domain rather than automatically using the entire reference chromosome; changes of chromosome/content safely clamp or restore an applicable interval.
- A8: Legacy saved preferences are accepted without losing assembly data or unrelated settings. Existing scale preferences are interpreted for main/local viewing-range compatibility where applicable; no obsolete tick-count preference can secretly change a migrated view when the new ruler interval changes. Existing persisted/session ownership boundaries are retained unless necessary for the navigator.
- A9: Navigation, tick changes, responsive layout changes, and view restoration do not create assembly edit-history entries or alter contig positions, orientations, local anchors, alignment evidence, Final Path order, or exported sequence/data. Existing selection, contig dragging, focus and history actions continue to work in mouse mode; hand-mode drag exclusively pans the viewing interval.
- A10: Final Path removes both legacy inputs from the App header and displays only its ruler interval control. It has no new overview range navigator, visible-span input, fit-all button, or zoom buttons. Main/local navigation does not modify its interval preference.
- A11: Final Path exposes one ruler interval control, defaulting to Auto with manual spacing available. Manual ruler changes affect only ticks/labels, not path pixel geometry, segment order, segment lengths, or export coordinates. Empty and very short paths remain well defined.
- A12: Final Path displays its complete assembled path fitted to the available plot width on render and window resize, without needing horizontal navigation to reach the last segment. Legacy scale/tick-count preferences cannot override that fit; automatic tick density follows the width while a manually chosen interval remains a ruler-only preference.
- A13: New main/local navigation controls, Display settings, and the Final Path interval control have Chinese/English labels and accessible names, preserve keyboard-operable numeric controls and existing focus behavior, provide usable drag handles, and remain operable at representative wide/narrow App widths without covering track content.
- A14: Current Windows-host frontend regression tests and a Windows-host production build pass, with generated dist removed after inspection. Interaction/visual evidence covers main view, all local modes, and Final Path, including reciprocal scroll/range updates, boundaries, empty data, and manual ticks; unexecuted native or platform checks are reported as unverified, not passed.

- A15: Ordinary wheel over the main/local overview axis or plot zooms without Ctrl/Space in either interaction mode. Wheel-up zooms in and wheel-down zooms out, anchored at the cursor's genomic point on the plot or the current range center on the overview. Range, span, graphic and ruler stay synchronized; invalid/empty domains, limits and high-frequency events remain bounded. Wheel over form fields, menus or outside these surfaces is not captured as chart zoom, and Final Path gains no new wheel zoom.
- A16: Each main/local navigation row has a clear mouse/hand mode switch, defaulting to mouse for a new context and independent of the other view. Mouse mode preserves existing selection/contig-drag/blank-area box-selection behavior; hand mode makes ordinary plot left-drag pan the interval without changing its span, moving contigs, committing a box selection or triggering a post-drag click. Cursor/active state reflect the mode; pointer cancellation, mode change, blur and repeated rerenders do not leave dragging stuck or duplicate handlers.
- A17: Left/right icons in each main/local navigation row move the visible interval by half of its current genomic span toward lower/higher coordinates, leaving span unchanged and updating the plot and range box together. Near domain edges they move only the remaining distance, at a blocked edge the corresponding direction is disabled, and with the complete domain visible both directions are disabled. They are navigation controls, not history controls, and are absent from Final Path.

# Constraints and invariants

- Work in the existing clean master checkout; writes use /mnt/d/desktop/CGAT. Preserve unrelated work and do not create or use agents without explicit current user permission.
- Use CodeGraph before locating/changing indexed code. Use RTK-prefixed shell commands.
- Frontend dependency use, tests, and builds run with Windows Node/npm.cmd on the Windows host. Desktop/Tauri tests, if needed, use the Windows host too. Do not reuse the Windows node_modules with WSL Node.
- Visible span and ruler interval are independent dimensions. The old product minTickUnitKb * maxTickCount must not remain the live scale model for the migrated surfaces.
- The complete domain follows the actual coordinate/geometry contract of each view. Do not relabel assembled/local coordinates as reference chromosome positions or disregard local offsets and reversed contigs.
- Preserve finite, bounded geometry and a single source of truth for view range; rate-limit/reuse existing render and persistence mechanisms rather than persisting every pointer event separately.
- Only task-related implementation and formal artifacts are committed and pushed when verified and safe; Native state/report transitions remain Runtime-managed.

# Decisions

- Confirmed through the discussion: interpret the navigator as a complete-domain axis with a selected interval representing the current window, not as an ordinary single-thumb zoom slider.
- Confirmed: selected interval translation pans; edge resizing zooms; fit-all selects the whole domain; plus/minus buttons adjust span around the current center.
- Confirmed: place each main/local navigator below its own toolbar and above the ruler/plot; do not share one navigator between those views.
- Confirmed: visible-span entry goes in the navigator row; ruler interval goes in Display settings on the existing main/local toolbar. Remove, rather than duplicate, the legacy fields.
- Confirmed on October 9, 2026: extend this same change to Final Path. Retire its old dual controls, add no new navigation widget, and retain only a ruler-unit/interval control. This supersedes the earlier proposal to exclude Final Path.
- Required invariant: Final Path's remaining ruler interval must not be a renamed zoom parameter.
- Confirmed on October 9, 2026 in response to Q1: Final Path always fits the complete path to the available plot width, recomputes layout on resize, and defaults its one interval control to Auto with optional custom spacing.
- Keep one Native change: shared preferences, ruler geometry and view synchronization are tightly coupled; splitting them into independently integrated children would increase coordination and regression risk.
- Confirmed Q2 scope revision on October 9, 2026: the user requests modifier-free wheel zoom, a mouse/hand mode switch in the navigation row instead of combination-key panning, and left/right buttons that move the current interval by half its span. Refresh the complete final Shape summary before Build.
- Investigated interaction constraint: existing primary/local contig pointer drags move assembly objects, and left-dragging blank plot areas performs box selection. Do not reassign ordinary plot left-drag to panning.
- Accepted gesture direction: ordinary wheel over the main/local navigator or plot zooms without Ctrl; over the plot it anchors the genomic point under the cursor, while over the overview axis it keeps the current viewing center. The navigation row provides a mouse/hand switch: mouse mode retains current editing/selection gestures; hand mode uses ordinary left-drag to pan only. Forward/up wheel zooms in and backward/down wheel zooms out. Final Path has none of these new navigation gestures.
- Left/right navigation buttons move the interval toward decreasing/increasing coordinates by exactly half its current genomic span where the domain allows; clamp at boundaries and disable a direction with no remaining movement. Do not confuse these buttons with edit-history undo/redo.
- Safety defaults: main/local modes are independent and new contexts start in mouse mode; hand mode has visible active state and a hand/grabbing cursor. Wheel interception is limited to the navigator axis/plot, not inputs, menus, labels outside the plot or the rest of the page. Pan/zoom never becomes a data edit or post-drag click.

# Open questions

None. Q1 (Final Path fit/interval policy) and Q2 (wheel, mode switch and half-window buttons) are resolved. Final Shape confirmation is a Runtime-managed boundary, not an unresolved requirements question.

# Verification expectations

- Pure/state tests for ranges, clamping, center/edge anchoring, unit conversion, tick/scale independence, legacy preferences, and view isolation.
- Render/binding tests for all main/local modes, toolbar placement, removal of obsolete inputs, reciprocal scroll/navigation updates, independent Final Path settings, and unaffected edit/data flows.
- Real Windows frontend browser interaction evidence for dragging/edge resizing, modifier-free wheel zoom and cursor anchoring, mouse/hand switching and gesture ownership, half-window movement and boundary states, input commit/error, fit-all, changing tick settings, changing content, and window resize. Browser tests cannot be claimed as full native desktop acceptance.
- Final Path regression checks for its confirmed full-path policy, interval-only header, empty/short/long paths, segment interactions, and unchanged data exports.
- Windows-host frontend tests and production build, and relevant Rust/Tauri tests only if changed contracts require them; remove generated dist after verification and record exact executed/skipped boundaries.
- Builder review and the Native Verifier use genuinely separate read-only executions as required by Runtime; do not falsely report a self-review as independent verification or violate the project's no-agent rule.
