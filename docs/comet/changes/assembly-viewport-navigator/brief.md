# Outcome

Make assembly-page navigation express the user's viewing range directly instead of requiring the product of a tick interval and a maximum tick count. Main and local views get an overview range navigator; Final Path retires the same legacy scale controls but exposes only a ruler-interval parameter, without a navigator or span input.

# Scope

- GPM2.0 App assembly main view and all supported local-view modes (ordinary pair, track pair, and custom composition).
- A separate overview navigator in each main/local view, below its existing toolbar and above the ruler/track graphic.
- Main/local range panning, range-edge resizing, Full range (全览), and a read-only Window (窗口) span display with automatic kb/Mb units. Add direct wheel zoom without modifier keys, a mouse/hand interaction-mode switch in each navigation row, and left/right half-window movement buttons.
- Main/local ruler interval directly in the existing toolbar: one editable control whose options include Auto (default) and numeric kb intervals, with custom positive values accepted. No Display settings wrapper or separate Auto/Manual selector.
- Final Path's App graphic: remove both legacy controls, retain only a ruler interval control in its existing header, and do not add the new overview navigator, visible-span input, or zoom buttons.
- Decouple ruler density from horizontal graph scale, preserve existing data/editor semantics, and accommodate legacy saved preferences.

# Non-goals

- Native application fullscreen, pinch zoom, box-selection zoom, a new vertical zoom mechanism, or a raster/minimap preview of the track content. No Ctrl/Space combination is required for the new wheel or hand-pan controls.
- Changes to contig placement/orientation, alignment filters, assembly editing history, Final Path path composition, export data, or biological coordinates.
- Server/offline report redesign, installer release, remote deployment, new branches/worktrees, or delegated/parallel agent development.

# Acceptance examples

- A1: Main and local views remove the visible legacy 最小刻度单位(kb) and 最多可展示数 fields. Each view renders one navigator below its own toolbar and above its graphic; the overview remains outside the horizontally scrolling content and its axis aligns with the plot area rather than the track-name gutter.
- A2: Dragging the overview selection translates the actual visible genomic interval without changing its span, stays within the complete view domain, and updates the graphic. Scrolling the graphic updates that same overview selection and span display; neither direction creates a feedback loop.
- A3: Dragging either selection edge changes the visible span with the opposite edge stationary, within the valid domain and supported rendering limits. The overview, read-only Window display, ruler, and graphic remain synchronized; completing or cancelling a drag does not edit contigs.
- A4: Main/local wheel zoom decreases/increases span within bounds; the navigator has no minus/plus zoom buttons. Full range (全览) selects the entire current domain and displays all current content, without changing font size or track height. Its tooltip explains that it displays the complete viewing range, not application fullscreen.
- A5: The navigator shows a read-only Window (窗口) span value with automatic kb/Mb formatting. It contains no editable span input or unit selector. Wheel zoom, edge resize, panning, horizontal scrolling, Full range, content changes and refreshes keep this display synchronized with the actual visible span.
- A6: Main/local ruler spacing is controlled directly in the existing toolbar, not inside Display settings. A single editable interval control offers Auto as its first/default option, the shared kb presets (250, 500, 750, 1000, 10000, 100000), and custom positive values. Enter or blur commits; invalid input gives explicit feedback without changing ruler or window state. Changing ticks leaves visible interval, contig geometry, scroll position, filters and the other view unchanged; Auto stays legible at actual plot/font width.
- A7: Main and local navigation state remain independent after entry. Ordinary, track-pair, and composition local modes all navigate their own complete rendered domain rather than automatically using the entire reference chromosome; changes of chromosome/content safely clamp or restore an applicable interval.
- A8: Legacy saved preferences are accepted without losing assembly data or unrelated settings. Existing scale preferences are interpreted for main/local viewing-range compatibility where applicable; no obsolete tick-count preference can secretly change a migrated view when the new ruler interval changes. Existing persisted/session ownership boundaries are retained unless necessary for the navigator.
- A9: Navigation, tick changes, responsive layout changes, and view restoration do not create assembly edit-history entries or alter contig positions, orientations, local anchors, alignment evidence, Final Path order, or exported sequence/data. Existing selection, contig dragging, focus and history actions continue to work in mouse mode; hand-mode drag exclusively pans the viewing interval.
- A10: Final Path removes both legacy inputs from the App header and displays only its ruler interval control. It has no new overview range navigator, visible-span input, fit-all button, or zoom buttons. Main/local navigation does not modify its interval preference.
- A11: Final Path exposes one ruler interval control, defaulting to Auto with manual spacing available. Manual ruler changes affect only ticks/labels, not path pixel geometry, segment order, segment lengths, or export coordinates. Empty and very short paths remain well defined.
- A12: Final Path displays its complete assembled path fitted to the available plot width on render and window resize, without needing horizontal navigation to reach the last segment. Legacy scale/tick-count preferences cannot override that fit; automatic tick density follows the width while a manually chosen interval remains a ruler-only preference.
- A13: New main/local controls and the direct Final Path interval control have Chinese/English labels and accessible names. Tick entry and selection remain keyboard-operable; window display is not editable or focusable. Overview handles remain usable. Wide/narrow layouts group left/right movement icons before the overview axis and keep Full range directly on its right without covering the graphic.
- A14: Current Windows-host frontend regression tests and a Windows-host production build pass, with generated dist removed after inspection. Interaction/visual evidence covers main view, all local modes, and Final Path, including reciprocal scroll/range updates, boundaries, empty data, and manual ticks; unexecuted native or platform checks are reported as unverified, not passed.

- A15: Ordinary wheel over the main/local overview axis or plot zooms without Ctrl/Space in either interaction mode. Wheel-up zooms in and wheel-down zooms out, anchored at the cursor's genomic point on the plot or the current range center on the overview. Range, span, graphic and ruler stay synchronized; invalid/empty domains, limits and high-frequency events remain bounded. Wheel over form fields, menus or outside these surfaces is not captured as chart zoom, and Final Path gains no new wheel zoom.
- A16: Each main/local navigation row has one clear sliding mouse/hand mode switch component (off = mouse, on = hand), not separate independent mode buttons, defaulting to mouse for a new context and independent of the other view. Mouse mode preserves existing selection/contig-drag/blank-area box-selection behavior; hand mode makes ordinary plot left-drag pan the interval without changing its span, moving contigs, committing a box selection or triggering a post-drag click. Cursor/active state reflect the mode; pointer cancellation, mode change, blur and repeated rerenders do not leave dragging stuck or duplicate handlers.
- A17: Left/right icons form an adjacent movement group before each overview axis; Full range is immediately after the axis. Each moves the visible interval by half its current genomic span toward lower/higher coordinates, preserving span and synchronizing plot/range/display. Near edges move only the remaining distance and disable blocked directions; disable both on Full range. They are navigation controls, not history controls, and are absent from Final Path.

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
- Superseded by the latest confirmed simplification: the earlier plus/minus buttons and editable span entry are removed; interval translation and edge resizing are retained.
- Confirmed: place each main/local navigator below its own toolbar and above the ruler/plot; do not share one navigator between those views.
- Confirmed: Window is a read-only display in the navigator; ruler interval is directly in the existing toolbar, with Auto as the default option in the same editable control.
- Confirmed on October 9, 2026: extend this same change to Final Path. Retire its old dual controls, add no new navigation widget, and retain only a ruler-unit/interval control. This supersedes the earlier proposal to exclude Final Path.
- Required invariant: Final Path's remaining ruler interval must not be a renamed zoom parameter.
- Confirmed on October 9, 2026 in response to Q1: Final Path always fits the complete path to the available plot width, recomputes layout on resize, and defaults its one interval control to Auto with optional custom spacing.
- Keep one Native change: shared preferences, ruler geometry and view synchronization are tightly coupled; splitting them into independently integrated children would increase coordination and regression risk.
- Confirmed Q2 scope revision on October 9, 2026: the user requests modifier-free wheel zoom, a mouse/hand mode switch in the navigation row instead of combination-key panning, and left/right buttons that move the current interval by half its span. Refresh the complete final Shape summary before Build.
- Investigated interaction constraint: existing primary/local contig pointer drags move assembly objects, and left-dragging blank plot areas performs box selection. Do not reassign ordinary plot left-drag to panning.
- Accepted gesture direction: ordinary wheel over the main/local navigator or plot zooms without Ctrl; over the plot it anchors the genomic point under the cursor, while over the overview axis it keeps the current viewing center. The navigation row provides a mouse/hand switch: mouse mode retains current editing/selection gestures; hand mode uses ordinary left-drag to pan only. Forward/up wheel zooms in and backward/down wheel zooms out. Final Path has none of these new navigation gestures.
- Left/right navigation buttons move the interval toward decreasing/increasing coordinates by exactly half its current genomic span where the domain allows; clamp at boundaries and disable a direction with no remaining movement. Do not confuse these buttons with edit-history undo/redo.
- Safety defaults: main/local modes are independent and new contexts start in mouse mode; hand mode has visible active state and a hand/grabbing cursor. Wheel interception is limited to the navigator axis/plot, not inputs, menus, labels outside the plot or the rest of the page. Pan/zoom never becomes a data edit or post-drag click.

- Confirmed on October 9, 2026: remove +/- buttons; rename Span to read-only Window with automatic units; remove Display settings indirection and expose a single Auto/numeric interval control. Name the complete-range action 全览 (Full range), with the right movement icon initially placed immediately to the right of the overview axis (superseded by the following layout refinement). This supersedes the earlier editable-span/zoom-button UI.

- Confirmed user refinement on October 9, 2026: move the right navigation arrow back beside the left arrow before the overview axis; attach Full range directly to the axis right side. Combine mouse/hand into one mutually exclusive sliding switch rather than two independent buttons. Auto remains the first/default tick preset. This supersedes the previous arrow placement.

# Open questions

None. Q1 (Final Path fit/interval policy) and Q2 (wheel, mode switch and half-window buttons) are resolved. Final Shape confirmation is a Runtime-managed boundary, not an unresolved requirements question.

# Verification expectations

- Pure/state tests for ranges, clamping, center/edge anchoring, unit conversion, tick/scale independence, legacy preferences, and view isolation.
- Render/binding tests for all main/local modes, toolbar placement, removal of obsolete inputs, reciprocal scroll/navigation updates, independent Final Path settings, and unaffected edit/data flows.
- Real Windows frontend browser interaction evidence for dragging/edge resizing, modifier-free wheel zoom and cursor anchoring, mouse/hand switching and gesture ownership, half-window movement and boundary states, tick entry commit/error and read-only window synchronization, fit-all, changing tick settings, changing content, and window resize. Browser tests cannot be claimed as full native desktop acceptance.
- Final Path regression checks for its confirmed full-path policy, interval-only header, empty/short/long paths, segment interactions, and unchanged data exports.
- Windows-host frontend tests and production build, and relevant Rust/Tauri tests only if changed contracts require them; remove generated dist after verification and record exact executed/skipped boundaries.
- Builder review and the Native Verifier use genuinely separate read-only executions as required by Runtime; do not falsely report a self-review as independent verification or violate the project's no-agent rule.
