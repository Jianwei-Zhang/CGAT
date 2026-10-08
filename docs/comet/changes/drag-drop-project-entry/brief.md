# Outcome

Allow the user to drag a delivery archive (.zip or .tar.gz, retaining existing .tgz compatibility), an already extracted delivery directory, or an existing GPM workspace directory from the desktop file manager into the running GPM application to import or open it. Reopening an existing workspace must not create duplicate project-page records. The user explicitly confirmed the complete Shape on 2026-10-08 and authorized implementation. Formal independent review and verification remain separate from implementation and automatic checks.

# Scope

- The user explicitly requested all three input types, drag-and-drop entry, reuse of existing workspace records, and discussion before implementation.
- Confirmed scope: accept one filesystem item anywhere in the GPM main application content area, with a temporary drag overlay and clear import/open feedback.
- Existing workspace detection takes precedence over extracted-delivery detection, including a resolved nested delivery root that has already become a workspace. An existing but unusable database must produce an error, not silently fall back to reimport.
- Reuse the existing compressed-archive import, extracted import, workspace session switching, progress, cancellation, and project-entry flows rather than building a separate importer.
- Confirmed scope: import a new extracted delivery in place, following current backend behavior; open it after successful import.
- Workspace history must use a consistent filesystem path identity and preserve existing record metadata. Repeated drops must not duplicate history cards or database projects. Distinct workspace copies remain distinct even if their data or names match.
- Confirmed: dropping a compressed delivery opens a compact confirmation dialog with the source and an editable destination already filled. The default destination is a sibling directory named <archive-stem>_<YYYYMMDD_HHMMSS>, using the computer local time to second precision and removing the entire .zip/.tar.gz/.tgz suffix. Existing destinations must never be overwritten.

# Non-goals

- No release publishing or installer packaging in this change; implementation began only after explicit Shape confirmation.
- Confirmed first-version boundary: no batch import, recursive directory discovery, shortcut-file resolution, dropping onto an unopened application icon, or importing additional datasets into the currently selected project.
- Do not merge separate workspace copies based on project name or bundle content.
- Do not delete, overwrite, or rebuild an existing workspace as an implicit consequence of dropping it.

# Acceptance examples

- A1: Dropping a valid delivery archive (.zip or .tar.gz, retaining existing .tgz compatibility) enters the existing compressed-archive import flow with the selected destination policy, retains progress/cancellation, and opens the successfully imported workspace.
- A2: Dropping a fresh extracted delivery root or a supported one-level wrapper resolves the bundle and uses the existing in-place import flow, without requiring the user to recreate a ZIP.
- A3: Dropping an existing workspace opens its existing projects and edits without running delivery import or creating a new database project.
- A4: Reopening a workspace already recorded on the project page leaves exactly one record for that filesystem workspace, preserving its existing user metadata and arrival order. Equivalent path spellings and supported canonical aliases do not add records.
- A5: Dropping the currently open workspace is harmless and does not duplicate records or recreate the active project. A separate workspace copy remains an independent record.
- A6: Invalid inputs, ambiguous wrapper directories, unusable existing databases, unsupported multi-item drops, and drops during conflicting work produce actionable feedback without starting imports or adding history records.
- A7: Switching through drag-and-drop retains the existing assembly-state flush/session handling, and cancel/error paths do not present the operation as a successful import.
- A8: The existing button-based compressed archive import, extracted import, workspace open, and project-page entry flows remain available and share the same identity/deduplication rules.
- A9: The archive confirmation pre-fills an editable destination beside the archive using its complete stem plus a local timestamp formatted YYYYMMDD_HHMMSS. A compound .tar.gz suffix is entirely removed, intervening stem suffixes such as .no_fasta are preserved, generated-name collisions receive a visible numeric disambiguator before confirmation, and an existing destination or a creation-time race is rejected without overwriting it. Cancelling the confirmation creates no workspace or project history.

# Constraints and invariants

- Use Comet Native, current master workspace, and main-conversation work only.
- Before creating this change, Git had no tracked or untracked changes; HEAD and the live origin/master branch both resolved to 02c0c24cc88712bd8181f573c85a7e9d56963b7f. All four pre-existing Native changes were archived with passed acceptance records.
- Comet doctor reports this change healthy. Comet knowledge retrieval emitted source/index-budget warnings; these are retrieval limitations, not evidence of workflow-state corruption. Current repository source is the basis for the design.
- Current archive validation/extraction supports .zip, .tar.gz and .tgz in backend/src/importer/workspace_io.rs; the native picker already exposes archive formats. Some internal entry names still say ZIP.
- Existing entry points are runImportZipFlow, runImportExtractedFlow, and runOpenWorkspaceFlow in GPM2.0/app/frontend/src/ui/pages/importer-page.js. Main-shell history updates use updateWorkspaceHistory in src/ui/shell/session-switchers.js; another history writer exists in importer-page.js.
- The extracted importer resolves the bundle root, uses that same root as the workspace, initializes project.sqlite, syncs the catalog, and indexes alignment payloads. Recognizing an existing workspace before import is therefore necessary.
- Path identity must respect filesystem semantics; do not indiscriminately lowercase case-sensitive paths. Resolve identity without changing the user's source data.
- Implementation-stage desktop drag/drop validation must use real filesystem paths from the native application event boundary, not just browser filename mocks.
- Future frontend production builds must run on the Windows host using Windows Node and npm.cmd; remove only the generated dist after verification.

# Decisions

- Confirmed by user: support delivery archives (.zip or .tar.gz, retaining existing .tgz compatibility), already extracted deliveries, and previous workspace directories.
- Confirmed by user: opening a previously recorded workspace must not create duplicate project-page records.
- Initial instruction: discuss first and follow Comet; implementation was authorized by the later complete-Shape confirmation below.
- Selected by configured Runtime: Native workflow, new change drag-drop-project-entry, current workspace on master.
- Confirmed by user: accept the compact compressed-import confirmation and pre-fill an editable workspace destination.
- User-proposed naming adopted in the draft: create the workspace beside the archive with the same archive stem plus a timestamp accurate to seconds. Use YYYYMMDD_HHMMSS to avoid filesystem-invalid colon characters.
- Safe default: generated destination collisions use a visible _01, _02, ... suffix before confirmation; user-specified existing destinations and creation-time collisions are rejected, never overwritten.
- Confirmed by user on 2026-10-08: the complete Shape including first-version boundaries; enter implementation.
- Explicit scope revision requested by user on 2026-10-08: skip macOS native desktop acceptance for this change only, record it as skipped/unverified, keep Windows native acceptance and A1-A9 behavior unchanged, and make no macOS verification claim.

# Open questions

No unresolved requirement questions. Shape was explicitly confirmed; remaining work concerns verification and workflow closure.

# Verification expectations

- Unit and integration coverage for input classification, directory precedence, Windows/case-sensitive path identity, record metadata preservation, history deduplication across both existing writers, busy guards, invalid/multi-item inputs, repeated events, and session switching.
- Backend fixtures for valid Full/Light deliveries in ZIP and tar.gz formats, an extracted wrapper, an existing workspace, and an unusable pre-existing database; unsuccessful classification must not mutate the filesystem.
- Real desktop smoke checks on Windows for dragging .zip/.tar.gz/.tgz archives and directories from Explorer, overlay lifecycle, success, cancellation, busy feedback, and preservation of existing work. Browser mocks alone are not desktop-drag acceptance. macOS Finder/native desktop checks are explicitly skipped for this change at the user's request on 2026-10-08, remain unverified, and are not required for this change's acceptance; this is not a macOS pass or a removal of functional support.
- Deterministic timestamp/compound-extension and collision tests, custom-path validation, confirmation cancellation, and preservation of a prefilled path across rendering.
- Existing importer and project-session regression tests plus a Windows-host production build, removal of generated dist, task-scoped Git diff review, and the configured Comet Verify gate at implementation time.

## Implementation checkpoint (2026-10-08)

- Implemented native drag/drop routing, read-only archive/directory inspection, timestamped editable archive destinations, atomic new-directory reservation for dropped archives, existing-workspace priority, canonical alias reconciliation, shared metadata-preserving history upserts, and guards for startup restoration/conflicting tasks.
- Windows frontend: `npm.cmd test` passed 1166/1166 tests; `npm.cmd run build` passed. The existing large-chunk warning remains a non-failing build warning. Generated `dist/` was removed after validation; the shared Windows dependency cache was not changed.
- Windows backend: `cargo.exe test` passed 206 library tests, with binary/doc-test targets also successful.
- Windows Tauri: `cargo.exe test` passed 15 library tests, with binary/doc-test targets also successful.
- Linux backend path-classification checks used a separate `/tmp/gpm-drag-drop-linux-target` and passed 6/6 tests, including POSIX case-sensitive and symlink identities. No desktop/Tauri Rust test or shared frontend dependency test ran in WSL.
- Production-bundle browser checks passed six scenarios: overlay, archive confirmation at 1280/390/320 pixels, cancellation, and existing-workspace open/repeated-open history preservation. These checks simulated Tauri event payloads and commands; they are not real Explorer/Finder filesystem drag/drop acceptance.
- Known validation limits: actual Windows/macOS desktop file-manager drag/drop is not yet tested. No independent reviewer or Verifier was invoked because `GPM2.0/AGENTS.md` expressly prohibits subagents without explicit user permission. The Comet Builder handoff requires a separate passed review, so it has not been submitted and no formal acceptance or Archive completion is claimed.

## Closure checkpoint (2026-10-08)

- Independent read-only review `01a11a3f-f18e-7222-937b-bbe51e5e5daa` found an A8 omission: the project-page click/selection comparison still conflated a literal POSIX backslash with a directory separator. Fixed entry/selection comparisons to use shared structural identity and defer native aliases rather than guessing case equivalence. Legacy Windows copy/delete safety guards are retained separately and no longer rewrite literal POSIX backslashes.
- Added six tests through the actual bound project-page record click handler covering POSIX literal backslashes, case-sensitive directories, same-path no-ops, equivalent Windows separators and native resolution of Windows case aliases. The focused importer-page suite passed 35/35 tests and full frontend tests passed 1181/1181 on Windows. The Windows production build and all six browser regression scenarios also passed; generated dist was removed.
- User reported actual Windows desktop drop initially did not trigger, then explicitly reported "可以了" after troubleshooting. This is user-reported native Windows functionality, not an agent-observed per-format or full lifecycle desktop matrix. Local token inspection during diagnosis showed an elevated GPM process and non-elevated Explorer. macOS desktop dragging remains untested.
- Reads-QC badge visibility was changed independently in `be4a080`; it is not an added acceptance requirement for this change.
- Independent re-review, Runtime checks, Verifier results and Archive are still pending at this checkpoint. No formal pass is inferred from the manual feedback alone.

## Validation scope revision (2026-10-08)

- User explicitly requested "macos跳过验收". This change no longer requires a macOS Finder/native desktop test matrix for acceptance. Such checks are skipped/unverified, not passed; implemented cross-platform behavior is unchanged.
- Windows Explorer/native desktop evidence remains required for archive formats and import lifecycle, fresh extracted roots/wrappers, preservation of existing projects/edits, active/copy workspaces, invalid/multi-item/busy feedback, session persistence and cancellation/error safety. A1-A9 behavioral requirements remain unchanged.
- The prior independent blocked result and all completed automatic checks remain historical evidence. Skipping macOS does not create missing Windows observations or silently convert the prior blocked verdict into a pass. Re-confirm the revised complete Shape and have a new independent Verifier evaluate the Windows evidence before Archive.
