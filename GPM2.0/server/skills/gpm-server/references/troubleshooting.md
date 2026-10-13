# Diagnose before retrying

Start with the earliest failing stage and its stderr, not the last generic error.
Keep the workspace, source identity, exact command, allocation, and first failure.
For a tiny workflow, a narrowly scoped corrective retry is reasonable; if the
same failure persists, stop and report the evidence rather than looping.

| Symptom | Evidence and next decision |
| --- | --- |
| SSH connects but submission fails | Inspect scheduler authentication/queue permissions separately. A query command may have different permissions from submission. Request user authentication if required; never ask for passwords in chat. |
| `module` absent or module initialization fails | Consult site startup instructions and load modules explicitly in the job. Site-required variables must be set first; do not solve this by editing global shell startup files. |
| `GLIBCXX_* not found`, wrong ELF architecture, help cannot start | Check node architecture, actual executable path, and loaded compiler runtime. Use matching site modules or an authorized isolated installation. `command -v` alone is not validation. |
| Missing `pigz`, incompatible MUMmer options | Check default archive dependencies and the required MUMmer capabilities in execution.md. Do not swap formats or reduce the computation silently. |
| Managed-environment `--check` fails on a module setup | Distinguish installer ownership from runtime dependencies. Validate loaded tools; do not claim installer READY or reinstall a working shared setup. |
| Empty/truncated reads or FASTA | Check file size, format and compression integrity. Stop before computing; do not substitute another dataset without agreement. |
| Output already exists or inputs changed | Inspect `.run_all/` and saved manifest. Resume only the same task; choose a new workspace for different inputs. Never delete the old directory to make preparation pass. |
| Lock already held | Check scheduler and recorded owner process. Do not launch a second runner or remove a possibly live lock. |
| Scheduler killed/OOM/wall time | Inspect allocation and stderr; request a justified resource change if it exceeds authorization. Do not silently switch off QC. |
| Failed preparation, no status table | Read `logs/prepare.log`; execution stages may not have started. Fix the demonstrated cause and resume. |
| Step2/Step3 reconciliation or provenance audit fails | Preserve `grt/evidence/step2/result.json`, `grt/evidence/step3/result.json`, runtime/source identity and logs. Do not disable the audit, hand-edit evidence, or blame dependencies without evidence. |
| Source fixed but workspace still fails | The workspace has its own `.prepare_lib/` runtime. Use a documented version-specific migration only with authorization; avoid blind file copying. |
| Report/archives exist after failure | They may be stale. Check current run ID/status and final delivery summary; report incomplete, not delivered. |

Prefer a small diagnostic bundle of logs/status and relevant evidence JSON over
raw sequence files. State which hypothesis is supported, what changed on a retry,
and what remains unverified. Never equate a skipped optional QC stage with measured
scientific quality.
