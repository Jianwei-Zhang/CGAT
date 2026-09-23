# Outcome

Use `light` as the accurate public name for the reduced Server delivery package, and make Windows the only production-build environment for the Windows-facing GPM2.0 frontend.

# Scope

- Rename the generated reduced delivery archive from `<workspace>.no_fasta.zip` to `<workspace>.light.zip`.
- Replace user-visible Server result, report, App validation, and documentation terminology from `no_fasta` / `No-FASTA` to `light` / `Light` where it names the delivery tier.
- Preserve the reduced package capability: it omits FASTA while retaining FAI, metadata, Final Path, source-card state, PAF views, and the embedded report.
- Preserve compatibility with the internal delivery contract value `package_mode=no_fasta` and with importing legacy archives whose filenames end in `.no_fasta.zip`.
- Record and follow the project convention that production frontend builds use Windows Node through `npm.cmd`, not WSL Node.
- Remove generated build output created during the preceding validation attempt. The current generated target is `GPM2.0/app/frontend/dist/`.

# Non-goals

- Do not change the package payload or add FASTA to the Light package.
- Do not rename the internal metadata value `package_mode=no_fasta` or the internal validator contract in this change.
- Do not remove `node_modules`, reinstall dependencies, or delete the pre-existing `node_modules/.vite` cache dated 2026-09-15.
- Do not change unrelated Full-package behavior.

# Acceptance examples

- A1: A successful Server workflow produces `<workspace>.zip` and `<workspace>.light.zip`, and its user-facing completion result identifies the second artifact as the Light package without presenting `No-FASTA` as the tier name.
- A2: The App and maintained user documentation describe the reduced tier as Light while the package remains importable with `package_mode=no_fasta`, including legacy `.no_fasta.zip` inputs.
- A3: Frontend production-build verification runs with Windows `npm.cmd`; no WSL production build is run, and generated `dist/` output from validation is absent when the change is handed off.

# Constraints and invariants

- The Light package remains a ZIP delivery containing the complete embedded report.
- Import and validation behavior is content- and contract-based, not dependent on the archive filename.
- Frontend tests may run from WSL; the restriction applies to production builds because the shared dependency tree contains Windows-native binaries.
- Cleanup must target only confirmed generated output and must preserve source files, dependencies, and unrelated caches.

# Decisions

- Public delivery-tier terminology is `Full` and `Light`.
- The new reduced archive suffix is `.light.zip`.
- `no_fasta` remains an internal compatibility value rather than a user-facing package name.
- Windows Node/npm.cmd is authoritative for frontend production builds.
- The Comet project memory records the build-environment convention for future work.

# Open questions

None.

# Verification expectations

- Run focused Server package/report tests that assert archive names and completion labels.
- Run focused App i18n/import tests for the Light terminology.
- Run the relevant complete frontend and Server test suites in proportion to the touched files.
- Run any required frontend production build only through Windows `npm.cmd`.
- Confirm `GPM2.0/app/frontend/dist/` is absent after verification and Git contains only task-related changes.
