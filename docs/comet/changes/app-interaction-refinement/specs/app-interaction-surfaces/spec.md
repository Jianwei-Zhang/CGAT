# App interaction surfaces

## Purpose

Complete target behavior for the confirmed GPM application interaction and information-architecture refinement plus the startup updater timing adjustment. Existing editor/navigation/cache behavior not explicitly changed remains authoritative. This is not a release or deployment specification.

## Phased-track and Final Path reconciliation

- Creating the first phased track successfully refreshes Final Path context and hides the precomputed-path action immediately, without route switching or reload.
- Adding another phased track or deleting a non-last track reconciles active paths and keeps the phased-state action visibility correct.
- Deleting the last phased track restores the main-path context and applicable precomputed-path action, clearing only invalid phased selections.
- The precomputed action is absent without an available baseline and remains disabled when already current; showing it never executes restoration or overwrites the user main path.
- Failed phase mutations publish no success state; reconciliation remains chromosome scoped, preserves unrelated viewport/edits, and respects existing dependent-data deletion contracts.

## Navigation context-menu boundary

- Right-clicking the horizontal navigation thumb, track, or non-business background exposes no Reload/web-page menu and does not reload the application on Windows or macOS.
- Existing Contig, track, and Final Path business context menus and input copy/paste remain usable; no app-wide indiscriminate context-menu ban is introduced.
- Menu handling preserves navigation dragging, wheel and zoom behavior; diagnosis distinguishes an application-added menu from a native default menu instead of asserting an unverified root cause.

## Final Path and member tooltip contract

- Final Path Contig hover displays an application-controlled tooltip on the next paint without deliberate delay or prior selection, consistently on Windows and macOS.
- Moving inside one fragment between its bar and label keeps the tooltip stable; entering a different fragment updates immediately, with no duplicate native title popup.
- Final Path tooltip includes full identity, source interval and orientation, with adopted fragment length primary and source Contig total length separately labeled and semantically accurate.
- Tooltips are viewport-clamped, offset from the pointer, read-only and non-intercepting; they neither move layout nor change selection or trigger graph/page reconstruction.
- Leave, drag start, scroll, context-menu opening or route switching hides stale tooltips; accessible names and standalone SVG source information are preserved.
- Member cards also expose complete source/local/state details through immediate controlled tooltips, stable within the card; unrelated alignment-band tooltip delays remain unchanged.

## Application terminology and casing

- Audit both application locales: major headings use English Title Case, minor headings/field labels use sentence case, and system-provided option values use Title Case.
- Buttons and action/context-menu entries use sentence case while standard proper names, GRT/FASTA and bp/Mb retain their canonical forms.
- Remove redundant ds from Contig-length labels, expand ctg/len, and use Auxiliary contig length (bp)/辅助组装 Contig 长度 (bp), Auxiliary dataset/辅助数据集, and Primary Dataset Members/主数据集成员 in their approved contexts.
- User project/dataset names, Contig identifiers and chromosome suffixes, paths, internal keys/enums and serialized data are not recased or renamed by the terminology audit.

## Stable Main View parameter layout

- Main View title stays on its own row; marker display, auxiliary dataset, Contig length, alignment length, identity, history, precomputed results and phased-track action are peer groups in fixed reading order.
- Each label/control/unit/closely related action group remains intact, with common control height and vertical alignment, consistent gaps and left-aligned wrapped rows; control semantics and content-based widths remain distinct.
- CSS-driven wrapping replaces measurement-driven single/split/stacked reparenting; resize, locale changes and long names do not cause threshold oscillation, DOM reconstruction or loss of focus/menu/selection/viewport.
- Long selected names ellipsize inside controls with access to complete values, without forcing other controls or the page outside the available width.
- No new application minimum width is imposed: normal shrink wraps intact groups, and only below a single readable group width the toolbar scrolls internally horizontally, without smaller fonts, splitting groups, global page overflow or chart navigation changes.

## Project-page information and compact paths

- Project page retains the existing project list and project selection duties; its right side first shows 项目信息/Project Information with the existing selected-project table and operations.
- The right side second shows 路径概览/Path Overview with the compact Final Path strip migrated from the former export page, preserving applicable geometry, role colors, gaps and existing navigation behavior.
- Both sections describe the same selected project; rendering cannot silently activate another project or mutate a path, and rapid project switching cannot publish obsolete results.
- Missing path data produces an honest empty state, never stale strips from the previous project; table and strip controls remain correctly scoped after refresh.

## Overview composition and navigation

- Top navigation is 项目/装配/概览, preserving existing English project/assembly labels and replacing Project Export with Overview; independent Preview entry is removed and prior application Preview jumps resolve to the new destination.
- 概览/Overview retains project identification, statistics and an explicit 导出/Export operation; exporter formats, data, range, job progress and error states remain intact.
- The lower 项目预览/Project Preview area embeds the full former Preview module instead of the compact strip, preserving legend, refresh, chromosome cards, applicable jumps and loading/error/retry/empty states.
- Preview asynchronous/model/DOM refresh is contained to its component and cannot erase statistics/export UI or mix projects; applicable memory/disk cache validity, explicit refresh and obsolete-request rejection contracts remain preserved.
- Navigation and project switching preserve authoritative edits and export tasks and do not alter biological coordinates/results; repeated visits keep handler/observer ownership bounded and valid preview state reusable.

## Compact equal-height member popover

- The Primary Dataset Members trigger opens an anchored member popover without squeezing or increasing Main View layout height; it fits the viewport and scrolls internally for many members.
- Every normal/derived/split member card has exactly two equal-height rows: identity first, length plus necessary concise state markers second; cards have consistent line height/padding and no redundant 78px/blank-row reservation.
- Member card width follows readable content without equal grid-column stretching, forced half-row sizing or fixed two-column layout; order is stable, long names remain distinguishable and complete values are accessible.
- Source interval, full name and local-use details move to complete hover details; overflow states may use explained summaries without a third row, silent information loss or unbounded card widening.
- Member click keeps the panel open and preserves existing single-selection/focus behavior, Ctrl/Cmd multiselection, box selection and business context menus.
- Trigger toggle, outside click and Escape close the member panel; leaving the combined trigger/panel/owned-menu region closes after the existing 400ms grace period, with reentry canceling it and no premature close between related surfaces.
- Member selection updates only necessary DOM/state and related views, retaining panel openness, internal scroll, focus and unaffected viewport; existing explicit focus behavior is not silently removed.
- Member selected styling preserves role colors and outer dimensions/padding/weight so selection cannot change wrapping; hover and selection do not rebuild the popover/page or hide flicker with animation.

## Final Path source-interval selection

- Final Path graph click or table-row selection selects one path-segment instance; graph/table share valid selection across mode changes, with no new Ctrl/Cmd multiselection and no loss of existing Main/Local multi-selection contracts.
- Clicking or keyboard-focusing a row editor selects its row and links the highlight without saving, rerendering, stealing editor focus, intercepting text selection or changing drag/right-click behavior.
- Editing uses the last successfully committed source interval until new values validate and save successfully; incomplete/invalid/failed values cannot alter the effective highlight and no per-keystroke preview is introduced.
- Main View and an already-open Local View highlight only the selected adopted source interval intersected with each displayed matching source object, not the whole Contig; closed/missing Local objects are not opened, inserted or regrouped.
- For ctg1 length 10000 and adopted source interval [5001,10000], complete Main ctg1 highlights [5001,10000], and a Local source interval [4001,8000] highlights only [5001,8000], with data-layer endpoint conventions explicitly normalized.
- Reverse orientation maps the same source interval to its actual visual position, which may be screen-left; source, path-cumulative and reference coordinates are not conflated.
- Source dataset/Contig identity, path/chromosome scope and path-segment instance distinguish repeated occurrences and same-parent splits; each target fragment highlights only its intersection, with empty/single-base/boundary cases correct.
- Unknown mappings and GAPs never fall back to whole-Contig correlation; missing intersections stay unhighlighted and source/sequence data is not physically split for visualization.
- Clicking another path fragment replaces selection; clicking path-plot background clears only that path selection/correlation, while hover alone changes no selection and no automatic scroll/zoom/locate occurs.
- Actively selecting an object in Main/Local clears prior Final Path selection/correlation, while hover/scroll/zoom does not; visual correlation never expands delete/move/edit selection sets.
- Same project/chromosome/path survives temporary route departure; path/chromosome/project switches, deletion/invalidity and app restart clear rather than restore obsolete temporary selection.
- Plain pointer clicks below the drag threshold do not invoke drag-cleanup unconditional card redraw; genuine drag sorting still commits and cleans up according to the existing gesture contract.
- Highlighter updates stable fragment-local overlays/outlines without changing original role fills, coordinates, geometry, labels, card size or scroll/zoom and without rebuilding/blanking the graph, Main/Local view or page.
- PNG/SVG exports exclude the newly added temporary selection/correlation/hover layers without first clearing visible user selection; original colors, data, range and standalone source tooltip information remain intact.

## Chromosome button-grid selector

- One clearly clickable current-chromosome/name-and-arrow trigger toggles the anchored panel; only collapsed/expanded states exist, with no nested small/large selector, duplicate toolbar/title, separate maximize or close buttons.
- The floating panel does not squeeze Main View or cover its own trigger; it uses adaptive columns of compact equal-height two-line buttons with original full chromosome identity and a Contig-count/length summary.
- Current item has stable selected appearance distinct from hover; names/version suffixes and ordering are preserved, compact Mb summaries expose exact bp details and do not change the placedBp statistic.
- All selectable chromosomes share one non-paginated panel, internally scrollable for large sets; no unrequested search/groups are added and narrow windows reduce columns rather than font size.
- Chromosome selection keeps the panel open for consecutive choices; trigger toggle, outside click or Escape collapses it, and combined trigger/panel departure retains the global 400ms grace/reentry-cancel behavior across mounting boundaries.
- Expand/collapse never loads or changes a chromosome or reconstructs the page; actual selection retains asynchronous validity checks, successful identity/active-item updates and honest failure behavior; project switch clears old options without new cross-session persistence.
- Keyboard can reach options, the trigger declares expansion/panel association, Escape restores trigger focus, and repeated renders do not multiply handlers or leave close timers targeting obsolete panels.

## Three-second automatic update startup check

- After updater initialization succeeds and it is enabled, schedule the first automatic check at 3000ms instead of 10000ms, never earlier or twice; disabled updater schedules no startup check.
- Keep the existing six-hour recurring check and 30-second deferred-offer notify cadence, silent current-version/error behavior, busy/hidden/modal deferral and persisted snooze/manual-check semantics unchanged.
- Keep docs-first sequential GitHub-release fallback, signature/version validation and install/save safety unchanged; the request changes startup delay, not request timeout or update sources.

## Data safety and delivery evidence

- Existing Main/Local navigation, scientific data, sequence/orientation/intervals, anchors, Final Path order, undo/redo and project/cache formats are unchanged except for explicit confirmed mutation/selection behavior; no release/installers/deployment are implicitly authorized.
- Each staged implementation has targeted regression checks and path-limited reviewed commits/pushes without absorbing unrelated changes; applicable integrated frontend tests and a Windows-host production build pass, generated dist is cleaned and Windows-only dependencies are not reused by WSL Node.
- No browser is launched by default; necessary visual validation is explained first. Evidence names actual checks and distinguishes source/unit/browser/static proof from Windows/macOS native hover, Reload, click-flicker and resize acceptance, with unexecuted native checks left unverified.
- Comet stages, candidate review and independent verifier are obeyed through public Runtime commands; implementation is serial in the current master checkout, with no subagents unless the user explicitly authorizes only the required independent read-only review/verifier executions.
