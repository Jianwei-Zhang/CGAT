# Outcome

Make the chromosome Preview page inexpensive to revisit and reopen, using a session-memory layer and a project-owned persistent layer without showing obsolete assembly results or changing scientific data.

# Scope

- Existing GPM2.0 Preview route, loader, card model, geometry synchronization, and relevant project/session transitions.
- Additive, project-scoped derived-cache persistence in the workspace's existing `project.sqlite`, exposed through the existing Rust backend/Tauri/service boundary.
- Dependency-specific content validity, invalidation across relevant project mutations and undo/redo, and chromosome-level rebuild/reuse when dependency boundaries are known.
- Reuse current, valid card models (and in-memory DOM where safe), deduplicate loading, and remove redundant whole-project loading on warm entry.
- Preserve all previously approved Preview appearance and navigation; the feature is a loading/caching change, not a new visual redesign.

# Non-goals

- No assembly, sequence, coordinate, path-order, or export-format changes.
- No persistent HTML, pixel geometry, raw FASTA/sequence data, or authoritative project data inside the cache.
- No periodic timer-based refresh, cache-management UI, new external dependencies, or new settings page.
- No changes to Server pipelines or unrelated import/runtime settings.
- No performance claim in milliseconds before measurement; no testing, building, browser validation, CI push, or workflow acceptance closure while the user's test deferral remains in force.

# Acceptance examples

- A1: Re-entering Preview for an unchanged project in the same session reuses a valid memory model without the four whole-project source reads, model reconstruction, or a redundant loading placeholder; valid card DOM is reused where applicable.
- A2: After reopening the app/project, a valid project-owned persistent snapshot is read with lightweight validity metadata and rendered without whole-project source fetching or model reconstruction.
- A3: A project with no usable cache follows the existing full-read/normalize/build path, presents the correct preview, and saves a reusable derived snapshot when persistence is available.
- A4: Relevant Final Path, gap, source-contig structure/orientation/assignment/name, dataset, reference, baseline, or phased-track changes (including undo/redo and supported import/copy paths) invalidate affected snapshots before they can be presented as current.
- A5: Navigation, scrolling, view zoom, hover, locale, font, and pure view-state saves do not invalidate semantic preview data; presentation changes still update the rendered result.
- A6: When only Chr1's dependencies change, Chr1 is reconstructed while unrelated Chr2 models/cards are reused; shared-source and project-wide dependency changes invalidate every affected chromosome, with a safe full-project fallback when impact cannot be established.
- A7: Current in-memory unsaved Final Path edits, including explicit empty paths, take priority over saved/persistent state; a session-only edit is never stored as a restart-reusable saved-project snapshot.
- A8: Switching or closing projects, concurrent refresh/entry, and edits during an in-flight load cannot install or persist a result for the wrong project, route, request generation, or content revision; equal project IDs in different workspaces do not collide.
- A9: Missing, corrupt, incompatible, or stale cache data falls back safely to rebuilding; cache read/write failures alone do not prevent an otherwise successful preview, and required-source failures retain an honest error/retry state.
- A10: The existing refresh icon forces fresh source reads and reconstruction, updates the cache after success, and preserves one set of delegated handlers/observers without accumulating listeners.
- A11: Persistent snapshots are compact, schema/model-versioned structured data with true genomic lengths and source identities, not HTML, width-dependent coordinates, or raw source records/sequences; deleting a snapshot is harmless, and relocating a complete workspace does not make cached project data depend on its old absolute path.
- A12: Cache-hit and cold-built views preserve one card per chromosome, hidden unpositioned information, dataset colors, uniform source-band height, gap labels, minimum visible path widths, source/path alignment, whole-name hiding when too narrow, whole-card provenance hover, and chromosome-to-Assembly navigation with edits preserved.
- A13: Cache operations write only derived cache/validity metadata and cannot overwrite assembly view state, Final Path edits, source-contig data, or exported biological coordinates.
- A14: Targeted regression cases and measurement hooks/evidence are prepared, but unexecuted checks remain pending; no tests, builds, browser checks, CI-triggering push, successful verification claim, or archive completion occurs until the user lifts the existing restriction.

# Constraints and invariants

- Work in the current `master` checkout; no new branch/worktree, delegation, or subagent is authorized.
- Use lowercase `/mnt/d/desktop/CGAT` for WSL writes and preserve unrelated untracked `=2050`.
- Preserve request/project guards and prioritize actual original-source identities and orientation-aware intervals rather than guessing from assembly IDs.
- Use a dedicated preview-content validity mechanism, not the whole database mtime or broad assembly `updatedAt` (which changes on ordinary view saves and cache writes).
- Build invalidation and cache updates around actual project-content commits; reject publication of a candidate built against superseded dependencies.
- Keep cache storage additive and recoverable. Cache material is derived, never a substitute for source records.
- Do not put arbitrary HTML in persistent cache or impose blanket card overflow clipping that would break existing menus.
- Frontend production tests/builds, once explicitly allowed, must use the Windows host; Rust desktop validation must also use the Windows host.
- Do not push while it would trigger the tests the user has deferred. Do not bypass the disabled CodeGraph preference through Git hooks.

# Decisions

- The user accepted the two-layer design and delegated execution: “可，你全权负责，进入工作流程。”
- Use one normal Comet Native change, not a Supervisor/Child decomposition; the current conversation performs all work.
- Keep the cache with the workspace's `project.sqlite`, keyed by project identity within that database; memory additionally distinguishes the workspace.
- Cache semantic, compact chromosome card models; derive labels, localized text, and geometry at render time. In-memory DOM reuse is subordinate to content/presentation validity.
- Reuse unaffected chromosomes; prefer a correct full invalidation when dependencies are ambiguous over a stale incremental result.
- Persistent cache corresponds to saved project content. Current-session unsaved edits overlay or rebuild memory models without poisoning the saved snapshot.
- The user's existing “本对话暂时禁止测试，后续统一测试” remains active. Implementation and static review may proceed only after Shape confirmation; execution/acceptance remains deferred.

# Open questions

- No unresolved product decisions. Runtime's final Shape confirmation is still required before Build.

# Verification expectations

- Prepare frontend cases for warm entry, persistence hits, forced refresh, incremental reuse, in-memory edits/empty paths, request races, failure fallback, version compatibility, locale/resize geometry, and handler ownership.
- Prepare Rust cases for additive schema creation/migration, content-specific validity changes, per-chromosome invalidation, transactional stale-write rejection, project isolation, copy/import lifecycle, and nonfatal derived-cache failure.
- Once testing is explicitly authorized, run targeted Windows-host tests first and then the approved unified frontend/backend/desktop quality checks; treat mocks as scoped evidence, not native acceptance.
- Until then, only inspect source, schema, and diffs. Do not execute the above checks or record acceptance as passed.
