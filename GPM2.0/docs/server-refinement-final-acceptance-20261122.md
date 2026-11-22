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
