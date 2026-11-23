# Native completion and re-admission recovery

Date: 2026-11-22. This adds a recovery boundary inside each tool attempt, not another scheduler or an orphan-directory fallback.

- A native process and CGAT admission are separate phases. After a real native completion, validate required outputs, chromosome identities, native child/iteration closure and explicit upstream no-candidate outcomes. Seal the native evidence before attempting source reconstruction, report generation or delivery.
- A reusable native checkpoint binds the selected pinned runtime and native command/parameters, actual assembly, typed raw reads and consumed conversions. Attempt-local output/input/driver locations are normalized by declared roles; thread budget alone is not a scientific input. Admission adapter hashes are deliberately not the native cache key: a corrected parser can re-admit exactly the original evidence without rerunning the producer. The completion verifier revision is recorded separately. A changed verifier must revalidate the same sealed bytes and artifact inventory under its current rules; a logging/verifier code change alone does not force a native rerun or silently trust obsolete validation.
- Reuse requires the complete sealed input/output inventory and checksums. Parent exit zero, directory existence, a partial FASTA or a failed child summary is not a checkpoint. Existing unsealed native folders are retained but not silently adopted. A missing/changed artifact causes no cache hit; a new attempt never overwrites that history.
- Re-admission has a new attempt ID and current adapter/version provenance. Native files stay in their original attempt, with an explicit origin link; they are not copied, renamed into the new attempt or represented as newly executed. Reports include the original command, actual original native threads/timing, the requested budget and whether native time was reused. This is not a tool-speed ranking.
- Baseline/reads/runtime must remain unchanged through checkpoint capture and admission. Native completion never authorizes a failed admission or a fake refined copy of LGZ; only a reconstructed, accepted Final Path may reach final publication.
- DEGAP child completion and LR iteration completion are checked independently of their parent exit. Only the exact pinned no-fill/no-candidate conditions are successful empty outcomes. Other errors remain failures.

This boundary covers completed native phases after downstream interruption/failure. Recovery inside an unfinished native phase is specified below; each engine needs its own validated execution boundary. Final acceptance still includes real pinned-tool runs, environment/architecture checks and the full A01–A18 matrix; development uses only targeted checks.

## Checkpoint and report locations

A successful producer writes `04_refinement/<numbered_tool>/02_jobs/<producer_run>/native_complete.json` after validating and sealing native evidence. The checkpoint records actual input hashes, native outcome, chromosome sequence/N summaries and child/iteration closure. New attempts keep their own `01_inputs`, `02_jobs`, `04_accepted` and `05_report`; `execution.native_origin` points to the original `03_native/<producer_run>` and completion receipt. No fake new native directory is created on a cache hit.

`native_executed` means execution in the current admission attempt; `native_reused` distinguishes a verified prior producer. Original native command/threads/time remain under `native_origin`, requested budget is separate, and this attempt's native execution time is zero when reused. Admission failures retain a successful native status but have no final publication. Successful and failed reports load the original receipt and preserve its artifact checksums rather than assigning fresh hashes to changed diagnostic files.

A no-remaining-gap DEGAP attempt is an explicit no-op and does not scan/hash unused reads; it is not a failed-tool fallback. Known quartet no-candidate and no-eligible-flank exits retain their exact pinned evidence conditions.


## Partial native work: immutable consumed-output units

Whole-native reuse remains the first choice. Partial recovery does not relocate or
resume an unsealed native directory: each admission still starts in a fresh native
directory. A CGAT-owned launcher wraps an explicit upstream execution boundary,
without editing pinned upstream sources or changing scientific parameters. It may
restore only an immutable, previously sealed consumed output (not an arbitrary
native tree). The original command, launcher command/code, unit producer and reuse
are separately recorded. Old logs keep their original paths and are never rewritten.

A unit key binds the whole normalized native input/runtime/recipe binding, exact
native threads, launcher/helper revision, actual consumed input contents and native
helper arguments. Restoring requires matching sealed bytes, valid output format,
and an owned regular-file receipt. A failed or interrupted unit has no completion
receipt. Tampering, changed inputs/version/parameters or unsealed files cause a
fresh unit execution, never automatic adoption. Each new native directory is fresh,
so upstream bare-existence reuse cannot accidentally accept old partial files.

Each producer unit is kept below its original `02_jobs/<run>/native_units/<key>/`.
A reused unit gets a fresh receipt and verified output copy in the current attempt,
with an explicit original producer reference; it is not labeled newly computed.
The native completion closure includes the unit receipts and consumed copies, so
reports and offline deliveries retain the evidence. Repeated recovery looks up
original producers, not chains of derived cache hits. Unit restore never bypasses
native parsing, integration, CGAT source reconstruction or final admission.

The first supported boundary is quarTeT GapFiller's `util.minimap` call for each
selected input FASTA. Bind the actual gapfill/flanking FASTAs and aligner/options;
restore only its PAF. Zero alignments are a completed empty output when the pinned
`allow_empty=True` policy applies, not a failed job or a reason to omit later inputs.
All selected inputs still run through native processing. A failure after input A
can reuse A on retry while executing B again. Final completion still requires the
native filled outputs or the exact pinned all-input no-candidate outcome.

The implemented DEGAP terminal-child boundary is described below. TGS command units and LR iteration-processing units are described below; each
has its own consumed-input/output closure and native failure checks. For DEGAP,
verified cached jobs must remain in the native summary (the upstream all-skipped
summary is not complete); LR cannot resume from an iteration FASTA alone. No
adapter may turn bare `.skip_right`, preprocessing files or exit-zero markers into
completion proof. Actual four-engine and architecture acceptance remains pending.


### Implementation and focused validation

`refinement_native_runner.py` bootstraps the verified managed source using the
original isolated Python flags and wraps only GapFiller's alignment helper. The
pinned modules and scientific command remain unchanged. `native_launch.json`
records both commands and helper hashes; `native_substeps.json` and unit receipts
are sealed into native completion. `native_substeps` reports its producer run,
completed/computed/reused counts, not a claim that a later admission reran them.
The native completion verifier revision also binds the unit validator: changing a
verification helper rechecks completed bytes, rather than forcing native science.

The pinned helper moves PAFs to `tmp/`. Completion checks now cover that actual
location; the root-file case remains compatible with previously sealed controlled
evidence. A completed summary must cover every selected input in order. Malformed
PAF/CIGAR, changed consumed outputs, missing input units and mismatched original
producer copies cannot become native completion.

The portable controlled launcher tests are `test_refinement_native_units`.
An optional source-level smoke installs only the checksummed, compatibility-patched
quarTeT source into a temporary directory and uses the developer minimap2 with an
injected second-input failure. It does not solve/upgrade an environment or establish
pinned-package/architecture acceptance. From `GPM2.0`, opt in with
`CGAT_TEST_QUARTET_ARCHIVE=/path/to/pinned-quartet.tar.gz`,
`PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=server/tests` and
`python3 -B -m unittest test_refinement_native_units.NativeUnitTests.test_pinned_source_with_developer_aligner_smoke`.


## DEGAP: terminal per-gap/direction consumed outputs

DEGAP resumes at the pinned `JobExecutor._run_single_job` boundary inside its
original ProcessPool executor, not by invoking the native bare checkpoint/skip
markers. Keep `--work 1`, the original job order/LEFT-before-RIGHT dependency and
all scientific parameters. The managed Python is the pinned Linux Python 3.11
fork runtime; refuse an incompatible process start method rather than silently
losing instrumentation in spawned workers. Upstream sources remain unchanged.

Each retry uses fresh preprocessing, detection and job setup, then may restore a
sealed terminal child result. The key binds actual prepared read/split/index/stat
contents, both copied flanks (including an explicitly absent native flank),
normalized declared output/native path roles in the
generated argv, gap geometry, whole raw-input/runtime binding and exact threads.
Do not reuse an interrupted round, `checkpoint.info`, `.skip_right` or a parent
exit code as proof. This boundary does not yet reuse preprocessing itself.

A terminal child is either native success or the exact pinned exit-zero unresolved
result. Nonzero/error/timeout jobs have no unit completion. Preserve success versus
unresolved: a reused unresolved LEFT still schedules RIGHT; a reused successful
LEFT still skips RIGHT through the original scheduler. Cached results pass back
through normal futures and appear in the complete native child summary, avoiding
the native all-skipped/missing-summary case.

Seal only the consumer-visible top-level final FASTAs, process/stdout/stderr logs
and native result, not a relocated round tree or index databases. On restore,
retain original log bytes, reference the original producer receipt and rebind only
the structured result's job directory. Report current restore time separately
from original native child time. The native analyzer, integration and CGAT admission
still execute against the new native directory. Ambiguous native selection among
multiple eligible final FASTAs is recorded but not reused; it must not silently
change which candidate the upstream glob selected or veto an otherwise valid run.

Worker receipts are immutable and the parent rebuilds its substep summary from
committed current-attempt units. Whole-native completion checks configured jobs,
non-skipped result coverage, exact unresolved outcomes, restored consumer bytes,
native result/producer identity and chosen FASTA validity. The report retains these
unit diagnostics even when a later native child makes the overall attempt fail.


The DEGAP launcher validates that generated `run.sh` is one native command and
that its declared job/flank/direction arguments match the actual job. Preserve
shell-safe Unicode and punctuation; do not replace this with a narrow ASCII
chromosome-name gate. Bind explicitly absent flank inputs without claiming they
are present or completed, and leave the pinned child to determine its outcome.
Prepared-read links must target the freshly generated, owned preprocessing tree;
unknown directory aliases cannot enter the cache key as unrecorded inputs.

Focused validation uses the checksummed bundled `AutoGapfillerPart3.py`, its real
JobManager/JobExecutor/GapFillingAnalyzer, real fork workers and shell children.
Preprocessing and child assemblies are controlled fixtures, so these checks do not
establish full DEGAP, fixed-environment, architecture or biological acceptance.


Each DEGAP child commits only its own immutable receipt; it does not rescan and
rewrite all earlier units. The parent builds the aggregate on normal/error exit,
keeping metadata work linear in job count. An abruptly killed parent can retain a
provisional running summary; committed unit receipts, not that aggregate, are the
recovery authority. LEFT dependency lookup is indexed rather than a whole-config
scan for every skipped RIGHT. Neither optimization changes native scheduling.


## TGS: native alignment/correction command units

Use the exact pinned bioconda build-4 driver, not the different upstream release
script. A private driver copy changes only helper discovery for its new location
and routes `MiniMap2`/`RACON` through CGAT-owned executable wrappers after the
original argument checks. The original script, native argv, thresholds, chunk and
round loops, candidate selection, merge, gap filling and sequence generation stay
unchanged. Record original source SHA, exact driver/wrapper bytes and actual
launcher command; never relabel the instrumented copy as unmodified upstream.

Each retry starts fresh. Scaffold split, candidate selection, shell filtering,
merge and integration run again; successful expensive minimap2/Racon calls may
restore their sealed stdout/stderr. The original shell still sets loop variables
and writes fresh done tags after each successful wrapper return. Do not restore
native done tags or use their existence as completion proof. Individual correction
chunks/rounds can be reused without skipping later chunks or native integration.

A unit binds the normalized declared attempt paths, original binary/argv, actual
consumed FASTA/PAF bytes, phase and native threads/runtime/helper binding. Minimap2
uses its pinned native PAF policy (no fabricated mandatory CIGAR when the native
command does not request `-c`); an exit-zero empty PAF is explicit empty output.
Racon output is validated FASTA, with exit-zero empty output kept distinct. Failed
calls leave diagnostics but no completion receipt.

Native stdout/stderr already target fresh owned regular native files. Execute the
original binary using those descriptors unchanged, then seal snapshots before the
script deletes or moves them. A producer snapshot may hard-link its own declared
read-only command outputs; a new attempt copies bytes to its fresh descriptors,
never hard-links a new consumer to historical evidence. Original logs remain
unchanged and unit receipts identify the actual producer and replay.

Raw prepared inputs already hashed by the live outer native attempt may use that
attempt's content SHA plus full file-identity fence across wrapper processes.
Those snapshots are regenerated for every new attempt, never a cross-run stat-only
cache. Generated native inputs are content-hashed. Parent completion verifies the
ordered expected command phases, receipts, output structure, source/wrapper pins
and original producer snapshots before CGAT admission. Full pinned-tool,
architecture and termination/process-quiescence acceptance is still required.


The optional `CGAT_TEST_TGS_ARCHIVE` tests verify the archive against the tool lock
and use its exact driver with controlled native helper programs. One HiFi test
uses the developer minimap2 to produce a genuine short-input empty PAF. This is
not a fixed-environment/real-Racon/C++ filling or ARM execution acceptance. The
current source SHA was verified against the pinned linux-64 build-4 archive;
architecture checks remain in the final matrix. Generated executable wrappers
are server-only script evidence, not active report assets or FASTA payloads.


## LR: completed iteration-processing units

Instrument a private copy of the lock-verified, path-discovery-patched LR driver.
Keep preprocessing, the first BWA index and tag split fresh in their original
order. Gate the first mapping/filter/reconstruction block, and each subsequent
iteration-processing block, with a checked restore/commit boundary. The original
gap-finder/empty-genome-ID test still decides early stop before any restore.
Do not precreate the native output directory or change scientific parameters.

Each unit binds raw/native runtime recipe, actual normalized reads, read lengths,
tag partitions, input genome and, for later iterations, fresh gap/ID prelude
files. The first stage also binds its freshly built BWA index. Completed output
means the native block exited successfully and both `gapclosed.fasta` (complete
chromosome identities) and `tmp/info_filter2` exist and are sealed. Restore these
regular files into the new iteration directory, with original producer receipts;
never restore a partial BWA/Perl tree or trust an unsealed FASTA by itself.

Native foreground failures remain fatal. Track the original background coverage
and gap-finder PIDs and wait for each exit status; bare `wait` must not hide a
failed native child. Keep the same commands and concurrency, rather than turning
an unchecked parent exit zero into a complete unit. A restore miss is distinct
from an input/protocol error, so malformed state cannot be treated as permission
to continue a native block.

A live-attempt input snapshot cache may avoid repeatedly hashing large normalized
reads across the fixed three iterations. It is regenerated per attempt and guarded
by the actual controller PID/start identity plus complete file-identity fences;
no old-run stat-only cache is accepted. Native cleanup still removes its common
working inputs; final admission and offline validation depend on sealed iteration
outputs/receipts, not deleted preprocessing files. Shared completed native-phase
reuse remains the first choice. Reports distinguish this processing-stage reuse
from fresh preprocessing/initial-index work and still reconstruct the Final Path
through the existing CGAT trace/admission path.


Focused LR validation uses the lock-pinned packaged driver (including the already
approved helper-discovery patch), its actual loops, branch/early-stop logic and
shell process execution, with controlled BWA/Perl programs. The optional
`CGAT_TEST_LR_DRIVER` selects that exact source file and rejects a different SHA.
It tests iteration 2 failure, iteration 1 replay, original early stop and cleanup,
background error propagation, restore miss versus protocol error, byte/recipe
changes and cross-attempt file independence. Real helper algorithms, pinned env,
ARM and termination/quiescence acceptance remain in the final matrix.
