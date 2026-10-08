# Drag-and-drop project entry

## Purpose and entry surface

The running GPM desktop application accepts one filesystem archive or directory dropped onto its main content area. A temporary drag overlay indicates the available entry action and is removed on leave, cancellation, or drop. A successful drop routes to the existing compressed import, extracted import, or workspace-open machinery; the existing button-based entries remain available. Application-icon launch drops, shortcut-file resolution, batch imports, arbitrary recursive discovery, and adding data to an active project are outside this capability.

## Compressed delivery import

Support .zip and .tar.gz deliveries, including Full and Light packages, while retaining existing .tgz compatibility. Format recognition is case-insensitive for the supported suffixes and preserves the existing backend archive-validation and safe-extraction checks. Merely dropping a file is not permission to start writing a workspace: it opens a compact confirmation dialog displaying the source and an editable destination. The user can confirm or cancel; cancellation before import writes no workspace and creates no project record. An unsupported or invalid archive fails with actionable feedback.

After confirmation, import uses the existing progress, cancellation, contract validation, indexing, completion, and session-entry flow. Failed or cancelled imports must not be presented as successful projects. Existing archive cleanup and source-archive preservation semantics remain intact.

## Default destination naming

For an archive in directory P with filename F, the suggested destination is P / (<stem>_<YYYYMMDD_HHMMSS>). Stem removes the entire terminal .tar.gz, .zip, or .tgz suffix, but preserves preceding components such as .no_fasta. The timestamp is the user's computer local date/time, accurate to seconds, generated for the accepted drop and held stable for the lifetime of that confirmation rather than regenerated during UI rendering. Colon characters are not used in the filename.

Examples with an illustrative local time of October 8, 2026 at 14:30:25:

- D:\deliveries\sample.zip -> D:\deliveries\sample_20261008_143025
- D:\deliveries\sample.tar.gz -> D:\deliveries\sample_20261008_143025
- D:\deliveries\sample.no_fasta.tar.gz -> D:\deliveries\sample.no_fasta_20261008_143025

The generated suggestion must not select an existing directory or file; if necessary append _01, _02, etc., displaying the resulting actual destination before confirmation. The field remains user editable. A user-chosen existing destination, missing write permission, invalid path, or creation-time collision must fail without overwriting existing files or silently choosing a different destination after confirmation. Existing workspaces must never be deleted or rebuilt to make room for this import. Repeated native drop events must not dispatch concurrent duplicate operations.

## Extracted delivery and workspace classification

Classify paths before mutation. Existing workspace detection takes priority over fresh extracted-delivery detection, including a supported resolved delivery root beneath a one-level wrapper. A pre-existing unusable database is an open error, not permission to reimport. Resolve extracted bundles using the supported root and unique one-level wrapper forms; do not pick an arbitrary child if several candidates exist.

A fresh extracted delivery is imported in place using current behavior, then opened. It is not copied into a timestamped directory and need not be recompressed. An existing workspace opens directly, preserving its database projects, edits and catalog. This action does not invoke delivery import or create a new database project. Dropping the active workspace is a harmless already-open operation.

## Project-page record identity

Use consistent filesystem-aware identity for both drag/drop and existing history-writing paths. Normalize equivalent separators/trailing separators and filesystem-supported canonical aliases; respect case-sensitive filesystem semantics rather than lowercasing every path. Opening one recorded actual workspace leaves one project-page record, preserving its user metadata and arrival order while allowing the existing last-used information to update. This rule also applies to existing button-based entry flows.

Separate physical workspace copies remain independent records even when their names or delivery data match. Importing the same compressed source into a genuinely different destination creates a separate workspace; this is not the same as repeatedly opening one previous working directory. Do not deduplicate by display name or package content.

## Session safety and conflicting operations

Reuse the existing assembly-state flush and project-session switching flow before changing workspace. While an import, project copy, initialization update, or automatic pipeline operation conflicts with entry, provide a clear busy response and do not start or queue hidden work. Do not accept a multi-item batch by silently choosing one item. Invalid paths, ambiguous roots, unsupported inputs, cancellation and open/import failures must give actionable feedback without adding successful project records.

## Acceptance mapping

The authoritative acceptance examples are A1-A9 in this change brief: A1 covers compressed formats and lifecycle, A2 fresh extracted delivery resolution, A3 existing workspace preservation, A4 history identity and metadata, A5 active/separate workspaces, A6 invalid and busy cases, A7 session/cancellation safety, A8 shared existing entries, and A9 destination suggestion, editability, collisions and pre-import cancellation. Desktop filesystem drag/drop must be validated at the real native boundary; browser-only mock tests are not sufficient evidence.
