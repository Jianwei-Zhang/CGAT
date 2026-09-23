# Windows Frontend Build Verification

## Authoritative build environment

GPM2.0 is Windows-facing and shares a dependency tree containing Windows-native build binaries. Production frontend build verification therefore runs only through Windows Node using `npm.cmd`. Agents do not run the production frontend build from WSL.

Frontend test execution from WSL remains allowed when it does not invoke the production bundler.

## Generated-output cleanup

After build verification, generated frontend output is removed from the shared worktree. Cleanup targets confirmed generated output such as `GPM2.0/app/frontend/dist/` and does not delete dependencies, source files, or unrelated pre-existing caches.
