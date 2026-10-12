# Builder checks — 2026-10-12

## Implementation status

Implementation and regression additions are complete. The user lifted the test/build/push deferral in this conversation on 2026-10-12 and requested unified checks for all jobs, followed by push. This file records Builder evidence, not an independent Native verifier verdict. Native acceptance and archive remain pending; the original verification turn did not authorize independent agents, so no independent verifier was launched or impersonated at that point. The user explicitly authorized an independent verifier on 2026-10-12 in the subsequent release request.

## Scope checked

- Project validation actions remain inline with compact text; error toasts have nonshrinking status text and wrapping workspace paths.
- Unsaved Assembly viewports start at full-range overview without overwriting saved viewports.
- Preview: single-line heading, contained information disclosure, refresh icon, one chromosome per row, distinct card headers, hidden unpositioned details, dataset-specific flat uniform source bands, whole-card provenance outlines, whole-name hiding, matching chromosome navigation, and white Gap fills.
- Preview/Export heading typography, shared content boundaries, and internal card-radius token.
- Preview/Project Export use the Assembly minimum-width layout for short contigs/gaps without altering biological coordinates; source alignment and label visibility are recomputed after measurement.
- Cache: session and project-persistent hits; revision/dependency invalidation; parent-chromosome/phased mapping; unsaved/empty path priority; safe corruption/I/O fallback; refresh; project/host/generation races; metadata/source/path mutation bridges; real backend undo/redo and Tauri command roundtrip.

## Executed checks

All frontend/Rust desktop checks used Windows host Node/npm.cmd/Cargo.

| Check | Result |
| --- | --- |
| Preview/cache/content-events focused frontend suite | 29 passed |
| Complete frontend suite | 1367 passed, 0 failed |
| Windows frontend production build | passed |
| Complete backend suite | 220 passed, 0 failed (includes 14 cache tests) |
| Tauri suite | 16 passed, 0 failed (includes cache command roundtrip) |
| Backend/Tauri rustfmt and clippy with -D warnings | passed |
| Windows Full quality gate | passed |
| Fresh desktop executable and embedded icon verification | passed with isolated CARGO_TARGET_DIR |
| Local Server Python suite | 155 passed |
| Local Server shell/package regressions and shell syntax | passed |
| LF and scoped git diff checks | passed |

The default desktop executable could not be overwritten (OS error 5). The user application was not terminated; the successful fresh build used `D:\tools\gpm-preview-verification-target`, whose executable icon was checked explicitly. Generated frontend `dist/` was removed afterward. Vite still reports its existing >500 kB bundle-size advisory; it is not a build failure.

Local Server checks explicitly skipped server-to-app E2E to avoid using Linux Node against the shared Windows dependency directory. The canonical Linux CI gate runs that E2E without the override; its terminal result must be checked after push.

## Performance evidence and limits

Fixture call-count assertions show a cold load makes four source reads and one whole-project build. Subsequent unchanged session entry makes no further source reads, builds, or snapshot writes; restart-equivalent snapshot restoration also makes no full-source reads or model builds. A committed Chr1-only path edit rebuilds Chr1 while preserving the Chr2 model identity. No native wall-clock latency claim is made.

No browser or interactive desktop visual acceptance was performed. Automated rendering/style/geometry and native command tests are not a substitute for visual acceptance. Native Build-to-Verify review/acceptance remains pending under the no-subagent policy.


## Independent-review repair before release

The fresh read-only review found that `source_seq_n_region` affects GRT display-app baseline gap partitioning but was missing from invalidation. Publication was held. The Builder added N-region INSERT/UPDATE/DELETE tracking, derived-cache schema/tracking version 3, transactional legacy cache reset, and an older-native tracking safe miss. Regression tests exercise actual GRT gap partition changes (50 bp, 100 bp, then no gap), stale publication rejection, snapshot/cold equivalence, v2 cache migration, old/new chromosome/source reassignment, retained assembly/original-source dependencies across restart/incremental rebuild, and repeated delegated binding/observer ownership.

The targeted Windows frontend suite now passes 32 checks and backend cache suite passes 17. Updated full-gate and independent formal verdict evidence must be checked before release; this repair note alone is not a verdict.


Fresh read-only builder re-review `01a13000-aa66-76f3-af72-d0635b26f0e3` returned PASS after the repair; it is separate from the Builder and is not the formal Native verdict. Completed Windows Full gate evidence in `.comet/runtime/preview-full-quality-reviewed.log`: frontend 1370 passed, backend 223 passed, Tauri 16 passed, strict format/Clippy, production build, isolated desktop build and icon checks passed. The DOM/observer regression uses stand-ins, not a visual WebView test. The formal Verifier will receive Runtime-owned checks next.
