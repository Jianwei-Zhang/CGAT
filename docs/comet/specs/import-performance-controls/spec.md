# Import performance controls

## Settings

The desktop Settings panel contains an import-parallelism control with these values:

- `Auto` (default and recommended)
- `1`
- `2`
- `4`
- `8`

The preference is available before a project is imported, persists across application restarts, is validated at the frontend/Tauri boundary, and is passed to ZIP, TAR, and extracted-bundle initial imports that perform pairwise indexing. Invalid or unavailable stored values fall back to `Auto`.

The UI explains that this setting controls PAF parser workers and that SQLite remains a single writer. Existing unrelated settings remain unchanged.

## Progress presentation

The import progress view presents the active chromosome/run, file-relative path, byte progress, parsed rows, written hits, and overall run progress. The presentation remains concise, localized, and updates the current stage rather than appending an unbounded log entry for every progress tick.

### Scenario: Persist an explicit import parallelism

Given the user selects `4`, when the application restarts and starts a supported initial import, then the Settings panel still shows `4` and the backend uses four parser workers with one SQLite writer.

### Scenario: Use Auto safely

Given the setting is absent, invalid, or set to `Auto`, when an import starts, then the application resolves a bounded host-appropriate parser count and does not create concurrent SQLite writers.

### Scenario: Show live progress without log flooding

Given a large PAF is being indexed, when structured progress events arrive, then the current progress presentation updates bytes, rows, hits, file percentage, and overall percentage without adding one permanent stage row per tick.

### Scenario: Preserve Windows frontend validation

Given the settings and progress UI changes are complete, when frontend tests and the production build run with Windows Node/npm.cmd, then they pass and no generated `dist/` remains tracked or untracked afterward.
