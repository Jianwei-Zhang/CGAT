# Project-owned chromosome preview caching

## Purpose

Preview is a read-only overview of how each chromosome's Final Path uses source datasets. Entering this route must reuse valid derived results instead of repeatedly reading all project inputs and rebuilding every chromosome. The cache accelerates viewing; authoritative contigs, original-source coordinates, saved paths, and current unsaved edits remain outside it.

## Layers and project identity

The current session maintains a memory entry associated with workspace identity, project ID, semantic content validity, and card dependencies. An unchanged warm entry uses that entry without full source reads, semantic rebuilding, or replacement by a loading placeholder. Existing in-memory card DOM may also be reused while its content and presentation context remain applicable. Ordinary route transitions must not automatically destroy valid preview data.

A separate derived cache in the workspace's `project.sqlite` survives project/app reopening. Reading a valid snapshot and lightweight validity metadata does not fetch full ctg/project/path payloads or reconstruct chromosome models. Persistence is project-scoped, schema/model-versioned, and independent of the workspace's former absolute location. Memory must never confuse different workspaces that happen to contain the same numeric project ID. Project close/delete/copy/import and workspace switches respect their own identities and invalidate or preserve only applicable derived entries.

## Cache representation

Store the compact semantic material needed to render cards: chromosome/reference/path lengths and order, dataset identifiers/names/colors or stable palette inputs, positioned source intervals and names/orientations, adopted-use mappings, final path segment/gap descriptors, and dependency metadata. Keep true biological lengths/source coordinates rather than screen pixel widths. Do not persist HTML, DOM/event handlers, raw source records, source sequences, or width-specific label/geometry decisions. Version changes invalidate incompatible data and fall back to reconstruction. Deleting derived snapshots cannot delete or modify project content.

Render with current locale, typography, and viewport dimensions. Recompute pixel alignment, minimum path widths, gap-label positions, and all-or-nothing source/path label visibility after restoration or presentation changes. Locale/font/resize changes may require DOM/geometry refresh but not semantic invalidation or source reload.

## Validity and mutations

Validity is based on dependencies that actually affect Preview. Do not equate broad assembly view `updatedAt`, whole-database mtime, navigation, zoom, scroll, hover, or cache-write timestamps with content changes. Relevant committed changes include Final Path/gap edits, original-source and editable-ctg structure/orientation/name/assignment, dataset configuration/identity, reference/chromosome metadata, baseline results, and phased-track membership/labels; undo/redo participates identically to its underlying content mutation.

Update validity alongside the corresponding content commit, or use an equally reliable coherent dependency mechanism. A snapshot built for an older dependency revision must not be published as valid after a newer commit. Cache publication itself cannot invalidate unchanged content. Cover supported project copy/import operations and reject identity/version mismatches.

For a chromosome-local change, reconstruct that chromosome and reuse unrelated models/cards. Account for source reuse, co-assignment, old/new chromosome membership, and phased parent dependencies: a shared mutation may affect several cards. Global dataset/reference/palette or topology changes may affect the full project. If the affected set cannot be proved, invalidate the project rather than guessing.

## Current-session edits

Merge sources using the existing baseline/saved/current-session priority. Current in-memory Final Path changes, including explicit empty paths, win over persistent cache data. Rebuild or overlay only necessary memory entries for unsaved edits; do not save that edited preview as a restart-reusable snapshot of saved project content. A completed save changes the appropriate validity metadata and allows a corresponding saved snapshot. Cache writes cannot overwrite authoritative assembly/view-state records.

## Loading and refresh lifecycle

On entry, reuse valid memory first; otherwise read a valid project snapshot; otherwise take the existing source-read/normalize/build path and opportunistically persist a compact result. Share/deduplicate applicable pending loads. Switching/closing projects or requesting a newer refresh prevents an obsolete completion from updating either the page or cache. Concurrent edits cannot publish a candidate whose revision is obsolete. No timer-based refresh is added.

The existing refresh icon explicitly bypasses cache reuse, fetches current sources, rebuilds, and replaces applicable entries after success. Maintain delegated handler/observer ownership when restoring or replacing DOM. Optimize source indexing/grouping so building one chromosome does not repeatedly scan unrelated contigs; avoid unnecessary serial per-chromosome backend reads where batching is available.

## Failure behavior

Missing, invalid, stale, corrupt, or incompatible snapshots are cache misses, not project failures. Cache I/O/publication failures alone are nonfatal when fresh source reading/building succeeds. Retain the existing honest source-error/retry behavior when required inputs cannot be obtained. Do not silently present an invalid snapshot as current. Persist only under matching project/content validity, with additive schema changes and recoverable derived-cache storage.

## Existing presentation and navigation

Preserve the confirmed Preview layout: one full-width card per real chromosome; a compact header/info disclosure and refresh icon; Ref as length reference when available; dataset-specific, uniform-height source tracks without collinearity ribbons; no unpositioned list/count; Final Path tracks with gaps and minimum visible widths; aligned adopted regions; fully hidden names when too narrow with complete hover titles; provenance outlines while hovering the whole chromosome card; and card navigation to the matching Assembly chromosome without losing edits. Source coordinate orientation, repeated/cut sources, phased paths, and biological export semantics remain unchanged. Shared page boundaries and inner-card radius styling are unaffected by caching.

## Delivery and evidence boundary

This is a single-session Native change in the existing master checkout. Prepare targeted frontend/backend/desktop regressions and distinguish call-count/rebuild evidence from native visual acceptance and measured timing. While the user's test deferral is active, do not execute tests, builds, browser checks, or CI-triggering pushes; do not mark unexecuted acceptance as passed or archive the change as complete. Resume actual verification only when the user explicitly lifts that restriction.
