# Post-LGZ refinement: consolidated acceptance

Started 2026-11-22. **In progress, not a release or completion claim.**
The requirements remain A01–A18 in the approved design. Green controlled tests
are not substitutes for installed/native, architecture, file-browser or App checks.

## Isolated environment

Source at start: `70673d5cb268a3f3ab1549a92783255e7ad192e3` on the feature worktree.
Validation state: `/tmp/cgat-refinement-final-20261122.t4d1vgxo/context.json`.
The public `server/install.sh --manager micromamba` is being executed using a
private HOME, mamba root/registry/cache and a disclosed manager wrapper that adds
only `--no-rc --root-prefix <private-root>`. The real executable, wrapper hash,
source specification/lock hashes, process PID/start identity, log and terminal
status are recorded there. Existing named environments are not updated.

The Linux x86_64 install/check and real runs are separate from Linux aarch64
resolver/install/native evidence. An ARM solve or emulation alone must not be
relabeled as a run on native ARM hardware. No remote host is implicitly selected.

## Native sample and end-to-end order

Use a reproducible 500-kb random reference and one assembly whose central 2-kb
sequence is replaced by N. There is no alternate assembly donor containing the
missing interval. HiFi inputs are error-free synthetic long reads split between
two files with the same basename; ONT inputs are independently identified reads
with deterministic substitution errors. Both orientations occur. This is a known
synthetic bridge/interop example, **not biological-accuracy or performance data**.
Exact generator parameters, read coordinates/strand/errors and file hashes are
saved with the sample. No native scientific command/format is mocked.

1. Run the public Server without typed reads to produce a real LGZ-only workspace.
2. Snapshot its contract, original scientific checkpoints/outputs and reference
   alignments. Append typed reads through the workspace's actual `run_all.sh`,
   selecting the four independent pinned engines and a small shared CPU budget.
3. Verify actual commands/versions/consumed inputs, native outputs, admission,
   source reconstruction, independent patch evidence, numbered final/delivery
   paths and portable reports. Inspect why any engine fails or accepts no edit;
   directory existence and a native exit zero are not sufficient.
4. Repeat unchanged input through public entrypoints to test completed reuse,
   then exercise supported single-technology and explicit-none behavior. Do not
   count skipped/no-gap invocations as real native execution.
5. Validate Full/Light archives and execute the matching Windows App import /
   source export roundtrip, preserving edited projects and old protocol cases.
6. Consolidate automated regressions and targeted failure/termination/resume,
   migration/rollback and actual file-browser/CSP/relative-resource checks.

Each requirement receives its actual source/output/receipt/test evidence and a
separate achieved/incomplete status. This document must not summarize success
from intent, an early installer transcript or the existence of output files.


## First actual install finding: directory softlinks

The real x86_64 Conda transaction installed 195 packages successfully (644 MB
archive plan). Refinement verification then rejected `lib/python3.1` as though a
required regular file were absent. The installed Python 3.11.14 metadata actually
records that path as a **directory softlink to `python3.11`**, with an empty-content
`sha256_in_prefix`. It is not a missing Python installation.

Repair boundary: directory links receive a separate structural receipt containing
the literal link and owned resolved directory. They must stay within the prefix
and their target must be covered by package members; ordinary package files still
need their actual expected hashes. Do not drop all symlinks or weaken archive,
version/build or file-integrity checks. Runtime checks must revalidate the link
identity without treating unrelated directory mtime/cache changes as source-file
changes. Retry the public installer in the same isolated prefix, preserving its
completed Conda packages and source installation, then run its real `--check`.


## First real LGZ-only run: numbered q0 command routing

After the directory-link repair, public installation and public `--check` both
completed with identical runtime identity and all 21 commands verified. The first
500-kb LGZ-only run actually completed the initial reference alignment and
assignment, then exposed a remaining hardcoded `workspace/runs/chr_*` path in the
manual q0 checkpoint entrypoint. The real generated q0 script correctly lives in
`02_alignments/chr_*`; the Python entrypoint must use the central layout resolver.

Also normalize that q0 command's persisted identity to its actual layout path so
manual and adaptive entrypoints prepare the same fingerprint. Repair the one
module in the stopped controlled workspace, recording its original/new hashes
and backup; retain the completed reference/assignment checkpoints and outputs.
Do not create a legacy shadow directory, delete/reprepare the workspace or count
an attempted failed q0 command as scientific completion.


## Numbered publication finding and exact-input recovery

The second actual resume reused the completed reference and assignment checkpoints,
then actually executed minimap2/MUMmer and LGZ Step1/Step2. Step3 correctly refused
missing frozen `tel/rules.tsv`. Investigation found that numbered q0 publication
replaced all of `03_lgz`, including `06_annotations`, which belongs to preparation
rather than the q0 transaction. Publication now replaces LGZ-owned child groups,
leaves frozen annotation inputs in place, and rolls back both directory and file
groups. Focused success/failure tests check original annotation bytes/mtime/inode
and restored old scientific outputs.

The stopped controlled workspace was not deleted or prepared again. Recovered
annotation files were generated separately and accepted **only when all three
SHA-256 values exactly matched the original pre-run annotation manifest**. That
manifest was neither replaced nor amended. No source/content validation was
bypassed. The previously completed embedded publisher was not replaced during
recovery, avoiding a gratuitous LGZ cache invalidation; the source fix applies to
new preparations. Recovery receipts remain under
`evidence/annotation-recovery/recovery-receipt.json`.

## Actual Linux x86_64 checkpoints achieved so far

- Public installer retry in the same private prefix completed on 2026-11-22,
  05:16:52 UTC; public `--check` separately completed at 05:20:45 UTC. All 21
  required commands and the four pinned runtimes were verified. The runtime
  fingerprint was `815f0d38a8a70139b902fcd515ba0b96028228383cbba476ffef9b8eb8e85e18`.
- Actual public workspace resume completed LGZ-only and generated Full/Light
  baseline packages at 05:45:04 UTC. The 500-kb sequence retained exactly the
  intended 2,000 N bases, and its FASTA SHA matched the original assembly input.
  All 21 original reference/assignment checkpoint/output files retained both
  content hashes and mtimes across targeted repairs and successful resume.
- `evidence/lgz-only-completed-snapshot.json` records 203 original scientific and
  baseline files before reads are appended. Later publication bookkeeping may
  rewrite byte-identical summaries/finalization files; distinguish that from
  actually recomputing reference/LGZ native stages.
- A first observer-launched resume was conservatively rejected by the unchanged
  direct-process guard because the supervising observer also exposed the
  workspace shell path in its argv. The harness now resolves the private run
  environment via a completed `micromamba run env -0`, then invokes the actual
  public shell without a live supervising argv that looks like a second job.
  This does not disable or patch the workspace lock/process guard.

Four-tool native execution, final admission/source reconstruction, App roundtrip,
ARM and the remaining A01–A18 requirements are **not implied by these checkpoints**.


## First actual four-tool append and detached payload audit

The actual workspace `run_all.sh` appended both HiFi files and the ONT file,
selecting all four fixed engines sequentially with a two-thread shared budget.
The invocation completed at 2026-11-22 05:48:11 UTC, exit 0. Each engine actually
ran its pinned native command, rather than a no-gap shortcut or controlled fake.

| Tool | Actual selected reads | Accepted edits | Final chr1 length | Remaining N | Result on this case |
| --- | --- | ---: | ---: | ---: | --- |
| DEGAP | HiFi + ONT | 0 | 500,000 | 2,000 | Native normal stopping/no bridge; no accepted edit |
| TGS-GapCloser | HiFi; ONT explicitly unused | 0 | 500,000 | 2,000 | Native fill detail retained original gap |
| quarTeT GapFiller | HiFi + ONT | 1 | 499,957 | 0 | Sourced patch admitted; 43-bp length difference from known reference |
| LR_Gapcloser | HiFi; ONT explicitly unused | 1 | 500,000 | 0 | Sourced patch admitted; exact known-reference sequence on this synthetic case |

These are interoperability observations, not an accuracy/ranking benchmark. The
DEGAP left/right logs report normal `noExtensionReadsFoundAfterParameterRelaxation`
stops, not a hidden command exception; its upstream aggregate calls their
unclosed status `failed`. TGS native `gap_fill_detail` explicitly keeps the N
interval. A completed native invocation with no admitted edit does not imply a
closed gap. Console summaries now print actual publication status/admission/gap
counts and label zero-admission FASTA as **UNCHANGED AFTER REFINEMENT**, rather
than implying that a patch was applied.

An independent stdlib audit parsed each published `sources.tsv`, checked its
actual FASTA hashes, fetched each 1-based source slice, applied orientation,
reinserted genuine gap Ns and rebuilt each chromosome without using the production
path writer. All four rebuilt sequences equal their published FASTA and sealed
chromosome hashes. The two admitted paths use named refinement source contigs and
actually differ from the original LGZ baseline; the other two are explicitly
unchanged, not claimed patched.

All eight actual refined Full/Light tar archives were hash-checked and extracted
to detached evidence directories. The real payload validator checked exact file
inventory, path/provenance, independent source evidence and reconstruction for
Full, and the explicit unavailable-sequence contract for Light. Detached Full
final FASTA bytes equal the corresponding published Server assembly. Report trees
are byte-identical between Full and Light for each tool (DEGAP 37, TGS 23,
quarTeT 32 and LR 30 files; actual audit inventory is authoritative).

All 203 pre-append baseline/scientific file contents remained unchanged; 13
finalization/summary files were rewritten with identical bytes. All 21 original
reference/assignment files retained their hashes **and mtimes**. LGZ stage logs
show validated cache reuse; no reference or LGZ native scientific recomputation
was introduced by appending reads. Exact evidence:
`evidence/four-tools-native-audit.json`, public invocation/process log and detached
payload inventories. This is **not yet a matching Windows App import/export,
browser/CSP check, ARM execution, complete recovery matrix or A01–A18 closure**.


## Completed reuse and a fresh ONT-only public run

The original four-engine workspace was resumed unchanged through public
`run_all.sh` and completed at 05:54:33 UTC. All native producer trees retained
file size/mtime with no new native attempt (DEGAP 248, TGS 28, quarTeT 18 and LR
54 files); no native-start marker occurred. The actual console correctly
separated two zero-admission unchanged results from the two applied results.
Evidence: `evidence/four-tools-unchanged-resume-audit.json`.

A separate **new** `workspace-ont-only` was then run from the latest public
`run.sh`, not prepared again or patched in place. It completed LGZ, TGS ONT
refinement and delivery at 05:56:16 UTC. Its q0 CLI and frozen annotation
publication worked without either recovery used for the original test workspace.
The three relevant prepared modules match the source bytes; the frozen annotation
snapshot verifies. Actual TGS native substeps include five minimap2 commands and
**three Racon corrections**, all newly executed and all eight receipts hash-bound.
One sourced edit closes the gap. The resulting 500,000-bp chr1 contains zero N;
its sequence equals the known reference on this synthetic case (not an accuracy
benchmark). Its two
actual detached Full/Light packages also pass source reconstruction/payload audit.
Evidence: `evidence/ont-tgs-native-audit.json` and the fresh public run log.

## Fixed DEGAP coordinate boundary exposed by the real diagnostic

The real native row for the 0-based `[249000,251000)` gap contains
`gap_start=249001`, `gap_end=251000`. Inspection of the fixed upstream code
confirms Part2 explicitly adds one to both coordinates; Part3 forwards those
values while retaining an obsolete comment saying "0-based". The CGAT adapter
and earlier controlled positive fixtures had followed that comment. A genuinely
filled native candidate would consequently have been rejected for the wrong
interval. The first real DEGAP run was unfilled, so that run does **not** exercise
this positive boundary.

The adapter now converts the fixed **1-based inclusive** report exactly once to
0-based half-open edits; replacement geometry and rejection attribution use the
same contract. Report job-to-gap association also normalizes coordinates before
intersection, including a one-base native interval and a merely touching
neighbor. There is no heuristic retry against a shifted gap and no anchor check
relaxation. Original native coordinate values remain in provenance.

Python 3.11 checks in the actual private environment passed seven focused cases
(6.299 s), including execution of the hash-verified native Part2 detector and
Part3 analyzer for real generated geometry. That geometry is paired with a
**controlled** positive bridge for admission/reconstruction; it is not relabeled
as a native gap-filling algorithm result. Existing positive/recovery fixtures are
corrected to the actual fixed protocol. This source correction still needs its
full final regression and a genuinely filled DEGAP native case; preserve the
prior real native producer evidence instead of replacing it with a fixture.


The corrected native-coordinate report association and controlled DEGAP native
checkpoint reuse additionally passed two focused Python 3.11 checks (4.923 s).
Then public `run_all.sh` completed **real native-evidence re-admission** with the
latest CGAT admission/report modules at 06:08:22 UTC. All four actual original
producer trees retained hashes/size/mtime, no new native producer ran, and their
new admission attempts bind the original producer IDs. Independent sourced
reconstruction and all eight newly generated detached Full/Light payloads passed
again; the two applied and two unchanged outcomes remain honest. Evidence:
`evidence/native-coordinate-readmission-reuse.json` and
`evidence/four-tools-coordinate-readmission-audit.json`. Only three CGAT modules
were targeted into the stopped controlled workspace; original pinned driver
bytes, scientific artifacts, runtime hash profiles and completed LGZ proof were
not replaced. This proves actual evidence reuse across the CGAT adapter repair,
not a positive DEGAP native gap closure or whole-matrix completion.


## User sequencing update: re-audit DEGAP after upstream feature merge

On 2026-11-22 the user specified that they will merge DEGAP's feature branch
later, then re-evaluate the CGAT integration. Keep the present pinned snapshot,
its verified findings and actual evidence as a dated baseline. Do not merge that
upstream branch, move the submodule pointer, upgrade the runtime, tune more
old-version DEGAP cases or assume its future interface from this checkout.
After the user's merge, inspect the actual new revision and re-check commands,
typed reads, dependencies/platforms, report/candidate/final artifacts, coordinate
semantics and native recovery before changing the adapter/environment/lock.
Existing receipts must not be relabeled as evidence for the new version. This
sequencing change applies to DEGAP-specific follow-up, not to the remaining
CGAT tools, provenance, App/report/migration or final consolidated acceptance.


## Windows archive roundtrip: reproduction and first finding

Use `scripts/stage-refinement-app-acceptance.py` from `GPM2.0/` with Python 3.11+,
`--workspace LABEL=/path/to/settled-workspace` for each workspace, and `--out`
pointing to a new Windows-readable directory. It stages byte-identical Full/Light
tar deliveries and separately published Server FASTA, verifying refinement
run identities and publication hashes before writing `cases.json`. It does not
modify or rerun a Server workspace. Use the Windows host toolchain from
`GPM2.0/app/src-tauri`; keep a separate target directory if sharing a checkout:

```cmd
set "CGAT_REFINEMENT_APP_CASES=D:\acceptance\input\cases.json"
set "CGAT_ACCEPTANCE_NODE=D:\tools\nodejs\node.exe"
cargo test --lib --locked actual_server_archives_roundtrip_through_desktop_commands -- --ignored --nocapture
```

The test needs a fresh evidence destination alongside the manifest. It checks
the bridge-bearing positive cases and zero-admission controls in this sample.
It drives the same importer/options as the desktop import command, native initialization,
production frontend state normalization (via Windows Node), the desktop FASTA
export body and persistence of a manual path edit. It emits an archive-bound
`desktop-roundtrip/roundtrip-receipt.json` if all cases pass. This is not a GUI,
WebView, installer or installed-release test.

The first real import of the positive quarTeT package found an empty Final Path
trace on its otherwise imported refinement source card. Sealed schema-5 cards
intentionally have no legacy LGZ event or path-ID links. The App now resolves
these cards by exact chromosome/dataset/contig in the persisted, validated
refined path, including residual N source intervals, without changing delivery
bytes, DB schema, LGZ card semantics or homology evidence. Project descriptions
also distinguish zero accepted edits from a genuinely applied refinement.

### Result with unmodified public archives

Windows host Cargo and Node passed all **14 imports (seven Full/Light pairs)**:
LGZ plus the four refined outputs from the mixed-read workspace, and LGZ plus
TGS from the ONT-only workspace. Each Full App export equals the independently
staged Server FASTA by chromosome name and sequence. Each Light import keeps
its path and source cards but refuses sequence export and creates no output
FASTA. All 14 independently save a manual path edit, reject reuse of the same
import destination, retain the identical database SHA-256, and reload the edit
without changing the precomputed baseline. No customer project was used.

The Full App exports for quarTeT, LR_Gapcloser and ONT-only TGS differ from their
own LGZ outputs and preserve the accepted source cards and intervals. The mixed
DEGAP and TGS runs exported unchanged sequence and are labelled zero-admission,
not patched. Receipt and log: `evidence/windows-app-roundtrip-receipt.json`,
`evidence/windows-app-roundtrip.log`; independent comparison to each LGZ App
export: `evidence/windows-app-vs-lgz.json`. The receipt SHA-256 is
`9cc14ee53aeb0a5659ce17705157cee7fac4094837d7414649d5dc022b4f86c4`.

### Reverse compatibility with the pre-refinement Windows importer

Built the backend CLI from the immutable pre-feature merge base
`a8eca1de4bd97761210ce737bc047d6d8a494a66` using Windows Cargo and its locked
dependencies. The actual LGZ Full and Light controls both imported successfully.
The same executable rejected the actual quarTeT Full and Light archives with
exit 1 and `GRT_IMPORT_UNSUPPORTED_SCHEMA`, with no project SQLite database
and no LGZ fallback. This exercises historical importer code, not a historical
GUI installation. The executable hash, input archive hashes and errors are in
`evidence/windows-legacy-import-receipt.json`; build transcript is
`evidence/windows-legacy-build.log`.

The separate Windows backend `grt_package::` regression completed with 59
passed and one ignored (320 outside the filter); see
`evidence/windows-grt-regression.log`. This includes the controlled residual-N
source-card trace as well as legacy-source and tamper checks. It does not
replace the actual archive roundtrip above.

## Native migration from a genuinely prepared legacy workspace

On 2026-11-22, isolated Linux x86_64 validation ran public `prepare.sh` from
archived historical engine `f2ceafb0df1f9d932122c5af3a733b9214ca7eb2` against the
same known synthetic sequence. The legacy workspace had typed HiFi inputs, no
`.run_all/launch.json` and no numbered manifest. The original installation was
made unavailable by moving only the disposable source archive; the generated
launcher then used its real embedded runtime, all 202 registered files verified
against the historical registry. A preview against a live legacy owner refused
migration before starting work. No customer workspace, remote scheduler, or
ordinary environment was changed.

The exact scoped historical runner received SIGTERM at the boundary after
reference alignment, assignment, chr-local q0, supplementary evidence and
q0/D0/Dtel. It exited 143 with the later LGZ stages still pending. The checked
continuation preview verified three outer checkpoints, q0 evidence and the
original donor freeze. It exposed that the real old plan placed `degap_gapfill`
**before** per-chromosome and evidence finalization. The isolated runner now
omits that exact old unit, agreeing with preview's already filtered prefix.
Original scripts/plan and runtime stay unchanged. No packaging or DEGAP ran
from this successfully interrupted workspace.

The approved `--continue-lgz` reused the three outer units plus the original
q0/donor result, ran the remaining actual LGZ commands, validated the scientific
contract and returned a separate physical migration approval. All 250 checked
original files (202 runtime and 48 script/receipt/output files) retained hashes
and mtimes. The first observation attempt had let another disposable workspace
advance further due to an overly narrow observer assertion; it is not counted
as this interruption or continuation evidence. Authoritative artifacts:
`evidence/legacy-native-interruption-2-process.json`,
`evidence/legacy-native-continuation-audit.json` and
`evidence/legacy-native-continue-1.log`.

Two real process-crash branches used the public migration CLI and its durable
journal, with no patched filesystem primitives. SIGKILL during `moving` left
actual files under their new locations; ordinary launch failed and `--rollback`
restored 623 original files exactly (regular-file contents/mode/mtime and
literal symlink targets). A fresh approved transaction was cut during
`validating` after the physical moves and before the ready marker. Launch was
again refused; `--resume` committed that same journal and original LGZ proof.
The receipt `evidence/legacy-native-transaction-events.jsonl` includes the
process identities, signal outcomes, transaction IDs and validation. This
covers these move/validation interruption points, not foreign-scheduler execution.

An additional genuine legacy launch exposed an earlier gap: after SIGKILL at
`prepared` and before the first move, the old launcher ignored the new marker
and rewrote its status, log and report. With the fence installed at the old
lock path, the same legacy launcher exited 2 without changing any of the 600
original files or links. `--resume` rejected incomplete staged bytes before
moving anything, `--rollback` preserved all 600 entries (bytes, modes, mtimes
and symlink targets) and released the fence, and a fresh approved apply
committed without starting analysis. The migrated LGZ FASTA matched the validated
historical digest. Receipts: `evidence/early-migration-before-fix-audit.json`,
`evidence/early-migration-after-fix-audit.json`, and
`evidence/early-migration-after-fix-reapply.json`. This tests local process loss,
not a power-cut simulation or a multi-host filesystem.

### Actual append and packaging boundary after migration

On resuming the migrated public `run_all.sh` with typed reads and quarTeT, all
10 LGZ units were labelled `SKIP_MIGRATED_LGZ`; the native engine admitted one
sourced edit. Initial baseline packaging then exposed a separate problem: a
preserved legacy DEGAP reads receipt was incorrectly interpreted as requiring
an old DEGAP output. The numbered LGZ package now intentionally omits old DEGAP
attachments. Legacy-layout packaging still uses its previous content checks;
this does not loosen projection or old-result integrity. The stopped synthetic
workspace was repaired under lock by changing only its packager module, with the
previous bytes and hashes recorded, not by rewriting migration/scientific
receipts or rerunning LGZ.

A normal `run_all.sh` resume completed both LGZ and quarTeT Full/Light tar
pairs under their numbered paths. The 337 tracked scientific regular files and
all eight original quarTeT native files retained their hashes and mtimes.
Independent source-slice reconstruction matches the admitted 499,957-bp
quarTeT output with zero remaining N and differs from the original LGZ sequence.
The detached refined Full/Light packages validated, and the old reads receipt
remained in the workspace but not in either `00_lgz` archive. Evidence:
`evidence/legacy-native-migrated-quartet-2.log`,
`evidence/legacy-native-packager-repair/receipt.json`, and
`evidence/legacy-native-migrated-refinement-audit.json`. These four newly generated
archives were not separately driven through Windows App in this run. The
observations are workflow/provenance tests, not tool-accuracy comparisons.

Focused Python 3.11 checks in the private environment also passed: 8 reviewed
legacy-continuation cases and 18 completed-migration/old App package cases.
These include the historical DEGAP unit before finalization, numbered baseline
packaging with a preserved old reads receipt, old-layout DEGAP integrity and
original cache-miss refusal. Logs: `evidence/legacy-native-continuation-tests.log`
and `evidence/legacy-native-focused-tests.log` (18 passing executed cases; the
other module in that initial invocation had a test harness `PYTHONPATH` error
and was run separately with its correct package root).


## Windows file-browser acceptance

On 2026-11-22, stock Windows Chrome `157.0.8103.80` in an isolated headless
profile loaded the redesigned reports from `file://`, including directories
with spaces and Chinese characters. The tested renderer revision was
`2d5bd017d79865b1bd1684141c696d0657d788d1`. HTTP(S) and WS(S) were blocked in
both the page and attached iframe sessions; there were zero network attempts,
failed resources or runtime/security errors during the audited navigation.

- Opened the current publication's report from the workflow overview, checked
  its Final Path and Full/Light file links, and followed an original gap to its
  native job fragment. This used actual packaging/publication over controlled
  partial admission, not an additional scientific benchmark.
- Extracted the actual Full/Light ZIPs outside the Server tree and opened each
  copy of `report/report.html`. Both rendered the DEGAP global gap track and
  both directions' inline graphics; the language switch and table expansion
  worked inside `sandbox=allow-scripts`. The wrapper could not read the frame's
  document, and no same-origin permission was used. The report bytes matched
  across the two separately validated packages.
- Opened the regenerated reports from the actual synthetic LGZ/four-tool runs.
  The LGZ audit rows rendered on expansion, admissions displayed 0/0/1/1 as
  measured, and the DEGAP job page showed the recorded missing-output error.
  The same page switched light/dark palettes and stayed within a 390 px
  document viewport; wide tables scroll within their own containers.

Receipt and capture files: `evidence/browser-offline-2d5bd017/`, including
`browser-receipt.json` (SHA-256
`b58d1a26eb0c293f7fcb45fdcaa40ad614eb90af7448d9bf060aa62eb478b28e`), the
local CDP harness and three screenshots. This is actual browser behavior,
not a native App window or Linux ARM acceptance.


## Actual partial failure and retry

A fresh local LGZ-only workspace was appended through its generated public
`run_all.sh` with mixed reads and quarTeT plus LR_Gapcloser. As a controlled
fault, the observer matched the owned quarTeT launch request to a descendant
process and used its pidfd to send SIGTERM to that producer only. The batch
exited 1 (`partial_failure`); LR_Gapcloser published its own validated files and
App packages, while the failed quarTeT attempt had a diagnostic report and no
final publication. No command, tool bytes or workspace checkpoints were mocked.

The first run showed a diagnostic ordering bug: a process exit of `-15` was
reported as missing `native_substeps.json`. Revision `93e85ee1` checks the process
outcome before reading the substep summary. A new real fault-injected run with
that revision displayed SIGTERM/`-15` as the reason and preserved the native log.
The explicit same-input retry ran quarTeT only, published both accepted results,
and preserved 40 LR native files and 37 alignment files by hash and mtime, as
well as the LGZ assembly digest. See `native-failure-isolation-3fa6ba49.json`
and `native-failure-isolation-93e85ee1.json` in the evidence directory. This
checks A10 at the producer boundary, not arbitrary multi-host failure.

## ARM64 solve and remaining consolidated checks

Micromamba 2.4.0 solved the full pinned `linux-aarch64` environment with strict
conda-forge/Bioconda priority on an isolated root, using `--dry-run`. All 192
resolved records were captured; version constraints matched the lock, and the
TGS-GapCloser, LR_Gapcloser, BWA and Racon records matched their locked build,
URL and distribution SHA-256. See `evidence/aarch64-solve-2d5bd017.json`. This is
the resolver portion of A05 only: ARM installation, `--check` and native tool
execution were not performed and require an authorized ARM worker.

The consolidated Server gate first caught stale generated runtime provenance;
`3fa6ba49` regenerated the two manifest hashes without changing the reference
runtime/binary. The gate then reached Python discovery (995 tests, 11 failing
assertions, 9 errors, 16 skips), not the later shell and App smoke stages.
`93e85ee1` addresses report/recovery regressions from that run; 42 focused
checks ran (32 passed, 10 skipped) and the real retry above passed. The
remaining failures were triaged and the complete gate was rerun, as recorded
below. This earlier run was not an A01–A18 pass.


## Numbered workspace and incremental App regression

The full Server suite at `1937cf33` reached 1,002 Python cases with no failures
(16 skips), and the eight Shell regression scripts completed. Updating only the
fixtures was not enough: the Shell cases exposed a real two-assembly q0 failure
and a numbered incremental-promotion bug. The q0 reader now resolves expected
and recorded PAF paths through the same layout before requiring the exact pair
and direction. The incremental promoter resolves both endpoints, preserves the
numbered prepared runtime and distinguishes assemblies/derived data from the
unmodified reference/reads. Incremental ZIP locators and payload members still
use the portable App namespace rather than the Server's physical paths.

The public x86_64 `run.sh --gapfill-tools none` on two synthetic assemblies
produced the actual `alternate_vs_primary` PAF at `02_alignments/chr_chr1/`, a
successful q0 evidence manifest, and both LGZ-only archives. Its subsequent
`add_dataset.sh` used actual native alignments and kept the original q0 freeze,
recipe, q0 and q3 FASTAs, and baseline archive SHA-256 unchanged. The first real
App append exposed two distinct defects: the base archive omitted the alignment
and annotation policy that incremental validation reads, and the App expected a
self PAF even where only one contig was assigned. Full and Light now project only
five necessary policy keys from the prepared workspace. A single-contig
chromosome no longer requires a nonexistent self PAF; configured multi-contig
self and cross-dataset alignment checks remain in place.

With Server `1937cf33` and importer `b0b16c13`, the real backend imported the
fresh Full baseline and incremental ZIP into an isolated workspace. The database
contained `alternate`, `primary`, and `supplementary`; the appended FASTA matched
the Server bytes, with two real pairwise runs indexed and no fabricated self PAF.
Six focused Rust incremental tests passed, including the strict multi-contig
negative case. See `evidence/numbered-two-assemblies-2f204cd2.json` and
`evidence/numbered-incremental-app-roundtrip.json`. This is a Linux CLI/backend
roundtrip, separate from the earlier Windows refined Full/Light roundtrip.

The Windows host backend rebuilt from the exact `b0b16c13` source also
imported both unmodified archives into a fresh workspace. SQLite integrity
passed, the appended FASTA and both PAF files matched the Server bytes, and
both cross-pair runs indexed two hits each without adding a fake self pair.
All six incremental Rust regressions passed on Windows. See
`evidence/windows-incremental-b0b16c13.json` (SHA-256
`f31308403ad8b5771b66c61194b17467e19474f6202ac3bee73bcb6d7295b771`),
`evidence/windows-incremental-real-b0b16c13.log` and
`evidence/windows-incremental-rust-tests-b0b16c13.log`. This verifies native
Windows backend behavior, not a GUI interaction or release installer.


## Consolidated gate and acceptance coverage

The canonical `GPM2.0/scripts/quality-gate-server.sh` at `1937cf33` exited 0
in an isolated x86_64 checkout with the managed environment and the locked
frontend dependencies. It ran Python discovery, all eight Shell regression
scripts, and the Server-to-App LGZ end-to-end check (including the reverse,
bridge and direct q0 cases through Server, Full and Light modes). See
`evidence/server-quality-gate-1937cf33.log` (SHA-256
`3510bc61b3a212a077ca2307b45e9c443f774f00e390277657aa394941a28c3e`) and its
exit receipt. The exact `b0b16c13` rerun, including the App single-contig fix,
also exited 0: 1,002 Python cases (986 passed, 16 skipped), eight Shell scripts,
and the same LGZ Server-to-App check. See `evidence/server-quality-gate-b0b16c13.log`
(SHA-256 `21d6a41109f463ecc74078bedc8ac416ee05352132a062284e5a173609b69448`)
and its exit receipt.

Separately, **27 producer-unit tests passed with no skips** at
`b0b16c13` after supplying the locked TGS archive, original pinned LR shell
script, and locked quarTeT source archive. These cover interruption/reuse and
invalid-artifact rejection with controlled subprocesses and one real minimap2
smoke; they supplement rather than replace the real tool runs above. See
`evidence/pinned-native-producer-units-b0b16c13.log` (SHA-256
`f3022568cf133c44410a69216479cf82f6729eb0b2869adb74b7eed9e243c597`).

The table distinguishes real runs from controlled regressions and records the
scope of each result. It does not certify releases, customer runs or arbitrary
legacy versions.

| ID | Status in this scope | Evidence / boundary |
| --- | --- | --- |
| A01 | Verified | Isolated `feat/server-post-lgz-gapfill-20261121` worktree; shared `master` was not switched or edited. |
| A02 | Verified | Public no-reads, ONT-only, mixed-read and explicit `none` runs; default DEGAP, grouped/unsupported reads and invalid choices also covered in `test_refinement_launch.py`, `test_refinement_tools.py` and `test_refinement_reads.py`. |
| A03 | Verified | Real `run_all.sh` four-tool append, unchanged repeat, original scientific file and alignment identity audits. |
| A04 | Verified | Four actual command/input receipts with mixed and ONT-only cases; grouped same-basename inputs, content-bound reuse, format and source controls. |
| A05 | Partial | x86_64 public install and read-only `--check`; controlled managed-spec upgrade and unmanaged-env refusal. ARM64 pinned solve passed; actual install, `--check` and native runs remain outstanding. |
| A06 | Verified on x86_64 | All four pinned native tools ran against the synthetic workspace with inspected outputs and reports. Not a claim of an accepted edit from every tool or native ARM64 coverage. |
| A07 | Verified | Independent source-slice reconstruction equals each published chromosome; accepted quarTeT, LR and ONT-only TGS outputs differ from LGZ. Zero-admission results are unchanged and explicitly labelled. |
| A08 | Verified in fixtures and the synthetic sample | `test_refinement_admission.py`, `test_refinement_native_trace.py` and `test_refinement_path.py` cover orientations, overlap, competing/nearby intervals, partial edits, residual Ns and zero acceptance. |
| A09 | Verified in controls and native readmission | Proposal conflicts, malformed evidence, mutated inputs and corrupt checkpoints are rejected in admission/path/native tests; the original-frame native readmission audit verifies only validated evidence is reused. |
| A10 | Verified | Actual quarTeT SIGTERM while LR still delivered; nonzero launcher exit and retry of quarTeT only. Separate pinned-driver producer checks. |
| A11 | Verified | Numbered new and migrated workspaces and public two-assembly run; fixed tool roles and separate baseline/publication directories. Layout resolver tests reject shadow destinations. |
| A12 | Verified for reviewed legacy engines | Actual old-engine continuation and append, rollback/resume after interruption, old-launcher fence; no-launch-record, stale evidence and active/foreign lock cases in migration regressions. |
| A13 | Verified | Actual pipeline and detached Full/Light Windows offline report checks. Native diagnostics, CGAT admission, remaining gaps and published files are distinct; DEGAP visualizations preserve sandboxed local navigation. |
| A14 | Verified | Actual `07_delivery/` inventories and detached Full/Light validators; report trees and paths agree across paired archives, Light does not claim sequence availability, archive inputs do not include the delivery tree. |
| A15 | Verified | Windows desktop command roundtrip on seven actual Full/Light pairs; sequence exports equal their Server FASTA and positive refinements differ from LGZ. |
| A16 | Verified | Pre-feature importer accepts LGZ and rejects refined schema; matching App accepts legacy/Light and preserves manual edits, with no Light FASTA export. |
| A17 | Verified for report scope | Immutable input and native-run identities, selected technologies, resources, unclosed/native-candidate versus accepted gaps in the reports. The sample makes no accuracy, speed or tool-ranking claim. |
| A18 | Verified for branch handoff | Bilingual Server guides, migration instructions, pinned recipes, platform limitations, source revisions and verification receipts; no release or merge to `master`. |

### Repeatable native validation and ARM64 handoff

The new runner passed all eight steps on Linux x86_64 against Server source
`e3409e5e` in the isolated environment. Evidence:
`/tmp/cgat-native-validation-final.NRAAS2p3/evidence/validation.json` (SHA-256
`e896cf84fae5a6353dff6f9d761720889064d7b0b4fa5e12ba34cbe9bc9f4da9`). The
fresh command without `--gapfill-tools` ran DEGAP only. Its zero-acceptance
FASTA was rewrapped, but the chromosome sequence matched LGZ. The real
four-tool append had 0/0/1/1 accepted edits; the unchanged repeat kept the
native receipt and assembly file hash for each tool. The four LGZ stage FASTAs
and reference PAF retained bytes and mtimes. Fresh ONT-only TGS recorded three
computed Racon substeps and one accepted edit. All six refined Full/Light
pairs were revalidated; wrong-architecture and existing-output guards refused
without overwriting output. These are synthetic results, not a ranking.

On an explicitly approved Linux ARM64 worker, use a clean checkout of the
reviewed revision and a new private Micromamba root. For example, with an
existing private `/work/private` directory and verified Micromamba on `PATH`:

```bash
export MAMBA_ROOT_PREFIX=/work/private/refinement-mamba
bash GPM2.0/server/install.sh --manager micromamba > /work/private/refinement-install.log 2>&1
# Continue only after installation exits 0. Retain the transcript separately.
micromamba run -n cgat-server python -B GPM2.0/scripts/validate-refinement-native.py \
  --arch aarch64 --manager micromamba --out /work/private/refinement-audit
```

The parent directory must already exist and the output directory must be new.
The runner refuses an architecture mismatch and does not install or update
software. It runs the public read-only environment check, verifies the active
pinned runtime, regenerates the known synthetic data with recorded hashes,
and uses the public launchers for a fresh default DEGAP run, an LGZ-only run
with a four-tool append and unchanged repeat, and the fresh ONT-only TGS
control. `validation.json` ties the step logs, selected read hashes, sealed
native producer receipts, retained LGZ/alignment files and Full/Light source
reconstruction proofs to the source revision. An unexpected result is
reported rather than repaired or overwritten. Compare measured states, not
hardcoded x86_64 patch counts; the helper nevertheless requires at least one
source-backed changed path and actual Racon substeps in the ONT TGS control.

The same runner accepts `--arch x86_64` for local regression. The receipt
records the OS-reported architecture; it does not assert that a remote host
is authorized or that an emulated OS is physical ARM64 hardware. A dry solve,
no-gap run or imported x86_64 checkpoint is not native ARM64 execution
evidence. A DEGAP change after the user’s planned upstream merge requires
its own adapter re-audit against that new revision.
