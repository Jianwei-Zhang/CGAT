---
generated_from_state_version: 24
---

# Verification

## Current result

- Result: **Archived**
- Verification status: **Checks completed; result confirmed**
- Goal cycle: 5
- Iteration: 2
- Verifier attempt: 2
- Completed: 2026-10-09T10:31:22.043Z
- Summary: Final full pass: independent read-only verification found A1-A17 satisfied on current HEAD f12cd24 after the empty-state repair; Runtime checks and browser evidence all pass within the disclosed non-native boundary.

## Acceptance

| ID | Result | Source | Criterion | Reason |
| --- | --- | --- | --- | --- |
| A1 | passed | brief.md | A1: Main and local views remove the visible legacy 最小刻度单位(kb) and 最多可展示数 fields. Each view renders one navigator below its own toolbar and above its graphic; the overview remains outside the horizontally scrolling content and its axis aligns with the plot area rather than the track-name gutter. | Legacy scale fields are removed; one external navigator per main/local view is correctly placed and aligned. |
| A2 | passed | brief.md | A2: Dragging the overview selection translates the actual visible genomic interval without changing its span, stays within the complete view domain, and updates the graphic. Scrolling the graphic updates that same overview selection and span display; neither direction creates a feedback loop. | Overview range drag preserves span, clamps to the domain, synchronizes plot scroll, and avoids feedback loops. |
| A3 | passed | brief.md | A3: Dragging either selection edge changes the visible span with the opposite edge stationary, within the valid domain and supported rendering limits. The overview, read-only Window display, ruler, and graphic remain synchronized; completing or cancelling a drag does not edit contigs. | Edge resize preserves the opposite endpoint, respects bounds, synchronizes all representations, and does not edit contigs. |
| A4 | passed | brief.md | A4: Main/local wheel zoom decreases/increases span within bounds; the navigator has no minus/plus zoom buttons. Full range (全览) selects the entire current domain and displays all current content, without changing font size or track height. Its tooltip explains that it displays the complete viewing range, not application fullscreen. | Bounded main/local wheel zoom and Full range behavior pass with no plus/minus controls and correct tooltip semantics. |
| A5 | passed | brief.md | A5: The navigator shows a read-only Window (窗口) span value with automatic kb/Mb formatting. It contains no editable span input or unit selector. Wheel zoom, edge resize, panning, horizontal scrolling, Full range, content changes and refreshes keep this display synchronized with the actual visible span. | Window is read-only and geometry-derived; empty primary content now shows — with disabled, aria-disabled, inert navigation while populated views retain kb/Mb synchronization. |
| A6 | passed | brief.md | A6: Main/local ruler spacing is controlled directly in the existing toolbar, not inside Display settings. A single editable interval control offers Auto as its first/default option, the shared kb presets (250, 500, 750, 1000, 10000, 100000), and custom positive values. Enter or blur commits; invalid input gives explicit feedback without changing ruler or window state. Changing ticks leaves visible interval, contig geometry, scroll position, filters and the other view unchanged; Auto stays legible at actual plot/font width. | Inline Auto/numeric ruler controls, all presets, validation, keyboard operation, and interval independence pass. |
| A7 | passed | brief.md | A7: Main and local navigation state remain independent after entry. Ordinary, track-pair, and composition local modes all navigate their own complete rendered domain rather than automatically using the entire reference chromosome; changes of chromosome/content safely clamp or restore an applicable interval. | Main/local state isolation and ordinary, track-pair, and composition domain navigation pass, including responsive composition interval preservation. |
| A8 | passed | brief.md | A8: Legacy saved preferences are accepted without losing assembly data or unrelated settings. Existing scale preferences are interpreted for main/local viewing-range compatibility where applicable; no obsolete tick-count preference can secretly change a migrated view when the new ruler interval changes. Existing persisted/session ownership boundaries are retained unless necessary for the navigator. | Legacy scale migration initializes visible span while ruler settings remain independent and persistence ownership is preserved. |
| A9 | passed | brief.md | A9: Navigation, tick changes, responsive layout changes, and view restoration do not create assembly edit-history entries or alter contig positions, orientations, local anchors, alignment evidence, Final Path order, or exported sequence/data. Existing selection, contig dragging, focus and history actions continue to work in mouse mode; hand-mode drag exclusively pans the viewing interval. | Navigation changes only view state and preserves biological records, offsets, anchors, evidence, selections, histories, and Final Path state. |
| A10 | passed | brief.md | A10: Final Path removes both legacy inputs from the App header and displays only its ruler interval control. It has no new overview range navigator, visible-span input, fit-all button, or zoom buttons. Main/local navigation does not modify its interval preference. | Final Path remains navigator-free and exposes only its independent direct ruler interval control. |
| A11 | passed | brief.md | A11: Final Path exposes one ruler interval control, defaulting to Auto with manual spacing available. Manual ruler changes affect only ticks/labels, not path pixel geometry, segment order, segment lengths, or export coordinates. Empty and very short paths remain well defined. | Final Path Auto/manual ruler changes leave segment geometry and state unchanged, including defined empty/short behavior. |
| A12 | passed | brief.md | A12: Final Path displays its complete assembled path fitted to the available plot width on render and window resize, without needing horizontal navigation to reach the last segment. Legacy scale/tick-count preferences cannot override that fit; automatic tick density follows the width while a manually chosen interval remains a ruler-only preference. | Final Path fits the measured viewport across responsive widths and ignores legacy scale fields for geometry. |
| A13 | passed | brief.md | A13: New main/local controls and the direct Final Path interval control have Chinese/English labels and accessible names. Tick entry and selection remain keyboard-operable; window display is not editable or focusable. Overview handles remain usable when the selected interval is wide enough; below 48px on the overview axis hide resize handles and prioritize pan through a transparent target of at least 24px, clamped inside the axis. Keep the visible selection proportional to the real interval; wheel zoom remains available and handles return at 48px or wider. Wide/narrow layouts group left/right movement icons before the overview axis and keep Full range directly on its right without covering the graphic. | Localization, accessibility, keyboard operation, responsive grouping, compact pan target, and focus fallbacks pass. |
| A14 | passed | brief.md | A14: Current Windows-host frontend regression tests and a Windows-host production build pass, with generated dist removed after inspection. Interaction/visual evidence covers main view, all local modes, and Final Path, including reciprocal scroll/range updates, boundaries, empty data, and manual ticks; unexecuted native or platform checks are reported as unverified, not passed. | Current Runtime receipts pass 1227/1227 Windows tests, production build with dist removed, 43+34+34 populated and 6 empty browser checks, no page errors, and Git diff check. |
| A15 | passed | brief.md | A15: Ordinary wheel over the main/local overview axis or plot zooms without Ctrl/Space in either interaction mode. Wheel-up zooms in and wheel-down zooms out, anchored at the cursor's genomic point on the plot or the current range center on the overview. Range, span, graphic and ruler stay synchronized; invalid/empty domains, limits and high-frequency events remain bounded. Wheel over form fields, menus or outside these surfaces is not captured as chart zoom, and Final Path gains no new wheel zoom. | Modifier-free wheel handling has correct surfaces, anchoring, coalescing, isolation, bounds, empty-domain inertness, and Final Path exclusion. |
| A16 | passed | brief.md | A16: Each main/local navigation row has one clear sliding mouse/hand mode switch component (off = mouse, on = hand), not separate independent mode buttons, defaulting to mouse for a new context and independent of the other view. Mouse mode preserves existing selection/contig-drag/blank-area box-selection behavior; hand mode makes ordinary plot left-drag pan the interval without changing its span, moving contigs, committing a box selection or triggering a post-drag click. Cursor/active state reflect the mode; pointer cancellation, mode change, blur and repeated rerenders do not leave dragging stuck or duplicate handlers. | The mutual-exclusive mouse/hand switch, ownership, span-preserving pan, click suppression, cancellation, cleanup, and rerender behavior pass. |
| A17 | passed | brief.md | A17: Left/right icons form an adjacent movement group before each overview axis; Full range is immediately after the axis. Each moves the visible interval by half its current genomic span toward lower/higher coordinates, preserving span and synchronizing plot/range/display. Near edges move only the remaining distance and disable blocked directions; disable both on Full range. They are navigation controls, not history controls, and are absent from Final Path. | Half-window controls are correctly placed, named, bounded, disable at edges/full range, preserve span, and are absent from Final Path. |

## Checks

| Check | Command | Working directory | Status | Exit | Duration |
| --- | --- | --- | --- | ---: | ---: |
| Windows frontend regression tests after empty-state repair | proxy /mnt/c/Program Files/PowerShell/7/pwsh.exe -NoLogo -NoProfile -Command Set-Location "D:\desktop\CGAT\GPM2.0\app\frontend"; & npm.cmd test; exit $LASTEXITCODE | . | passed | 0 | 3655 ms |
| Windows production build and cleanup after empty-state repair | proxy /mnt/c/Program Files/PowerShell/7/pwsh.exe -NoLogo -NoProfile -Command Set-Location "D:\desktop\CGAT\GPM2.0\app\frontend"; try { & npm.cmd run build; $code=$LASTEXITCODE } finally { if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" } }; exit $code | . | passed | 0 | 5689 ms |
| Windows Chrome populated general, compact, and closure checks after repair | proxy /mnt/c/Program Files/PowerShell/7/pwsh.exe -NoLogo -NoProfile -Command & "D:\desktop\CGAT\.comet\runtime\viewport-runtime-browser.ps1"; exit $LASTEXITCODE | . | passed | 0 | 81010 ms |
| Windows Chrome empty primary/local/Final Path acceptance after repair | proxy /mnt/c/Program Files/PowerShell/7/pwsh.exe -NoLogo -NoProfile -Command Set-Location "D:\desktop\CGAT"; & node .comet/runtime/viewport-empty-state-browser.cjs; exit $LASTEXITCODE | . | passed | 0 | 6974 ms |
| Repair Git whitespace check | git diff --check | . | passed | 0 | 5298 ms |

## Blockers

_None._

## Risks and skipped work

- Browser acceptance used the real frontend renderer with fixture state and intercepted APIs, not native Tauri/live-backend end-to-end acceptance.
- Real backend persistence/live export and unchanged Rust/backend contracts were not separately exercised.
- Installer, release, deployment, and platform-native checks were not run.
- The successful build retained the pre-existing greater-than-500-kB chunk warning.

## Previous iterations

| Goal cycle | Iteration | Attempt | Outcome | Unresolved | Summary | Completed |
| ---: | ---: | ---: | --- | --- | --- | --- |
| 1 | 0 | 0 | recovery | — | Native confirmed acceptance criteria changed | 2026-10-09T05:55:32.897Z |
| 2 | 1 | 0 | recovery | — | Native confirmed acceptance criteria changed | 2026-10-09T07:10:39.181Z |
| 3 | 1 | 0 | recovery | — | Native confirmed acceptance criteria changed | 2026-10-09T07:43:55.681Z |
| 4 | 1 | 0 | recovery | — | Native confirmed acceptance criteria changed | 2026-10-09T08:29:39.486Z |
| 5 | 1 | 1 | fail | A5, A14, A15 | Fail: A5, A14, and A15 failed because an empty primary assembly is presented as a normal 2 Mb navigable window instead of an unavailable noninteractive state; the other 14 acceptance items passed. | 2026-10-09T10:08:47.213Z |
| 5 | 2 | 1 | recovery | — | Repair verification passed for A5, A14, A15; final full verification is required. | 2026-10-09T10:24:16.094Z |
| 5 | 2 | 2 | pass | — | Final full pass: independent read-only verification found A1-A17 satisfied on current HEAD f12cd24 after the empty-state repair; Runtime checks and browser evidence all pass within the disclosed non-native boundary. | 2026-10-09T10:31:22.043Z |



## Conclusion

Final full pass: independent read-only verification found A1-A17 satisfied on current HEAD f12cd24 after the empty-state repair; Runtime checks and browser evidence all pass within the disclosed non-native boundary.
