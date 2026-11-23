# Native refinement report portability contract

Date: 2026-11-22. Implements the approved native/offline portion of A13; it
neither changes scientific recipes nor treats a report as a publication receipt.

## DEGAP bidirectional family revision

At `6cd01f1b983c43648e51389c129dfbd8b5926284`, AutoGapfiller still emits `Global.report.html`. Its detail view now comes from each bidirectional job’s sealed `family-report.html`, with the relative link from the overview generated for that job. The new producer uses bundled inline JS/SVG, not Chart.js. Managed copies use the same frame and CSP. Approved native links to working files are disabled within the display copy; the corresponding selected JSON, AGP and logs are exposed separately by CGAT diagnostics. An exhaustive family search with no candidate is labeled as a completed search with no fill, not an execution failure. Report-source hashes and the allowlist capture the precise pinned renderer dependencies.

## Evidence and fixed producers (previous DEGAP pin)

The bundled DEGAP visualizer actually writes `05.visualization/Global.report.html`.
Its chosen per-gap reports are copied beside it; individual LEFT/RIGHT jobs can
also produce `visualization_output/gapfiller_report.html`. The former collector
looked only for `gap_filling_report.html`, so a synthetic legacy-named HTML fixture
was not proof that the real report tree was delivered.

The pinned Gapfiller visualizer includes an unversioned Chart.js CDN script, but
its JavaScript uses its own inline SVG and does not call Chart.js. The offline
copy removes only that known, unused external script; it does not fetch or add a
new library. Source SHA-256 pins and the allowed transformation policy are a
separate machine-readable report contract. The original bundled tool bytes,
original report bytes, tool version and scientific parameters remain untouched.

The selected TGS-GapCloser, quarTeT GapFiller and LR_Gapcloser entrypoints do not
produce native HTML. Their real text/AGP/fill-detail/job diagnostics remain
available. Do not manufacture an upstream visualization or imply that a CGAT
report was produced by those tools.

## Reading the HTML reports

Open `06_report/report.html` for the batch overview. Its numbered sections
cover the LGZ baseline, refinements and comparison data. The LGZ report is
under `01_lgz/`; the per-tool reports under `02_refinement/` show original gaps,
CGAT decisions, native jobs and logs. Comparison JSON and TSV stay under
`03_comparison/`. The overview only links current refined Final Path and App
archives when the published batch record matches the verified receipt.

The HTML layout and copy were drafted with AGY CLI (`gemini-4-neon-high`) and
reviewed against CGAT's App styling and the Server's recorded states. Native
execution (or reuse), CGAT acceptance and final publication are separate.
Completed with zero accepted changes means the LGZ sequence was retained; it
is not a failed batch or a closed gap. A missing job status is not counted as
success or failure. When recorded, the failed phase and exact error are shown
with links to the relevant diagnostics. IDs, JSON, logs and source evidence
remain available without repeating their raw contents in the main summary.

The HTML stays standalone: embedded styles, no external dependencies, and
unchanged archive entrypoints. The CSS, local links and result text were checked
by regenerating the LGZ and all four tool reports from the existing synthetic
runs without launching the scientific tools. The [Windows offline browser acceptance](server-refinement-final-acceptance-20261122.md#windows-file-browser-acceptance)
separately exercised the real `file://` browser and sandbox.

## Portable display and containment

Keep every selected original HTML as an inert, content-bound text attachment.
Only the known DEGAP report locations have a managed interactive display copy.
Unknown HTML remains inert. Report copies have no remote scripts/assets, fetches,
forms, embedded documents or workstation links. Unsupported dependencies or
markup are explicit display-unavailable diagnostics, not a license to execute
arbitrary HTML and not grounds for rerunning a successful native analysis.

The display retains native inline JS/CSS/SVG and makes only disclosed presentation
changes: remove the unused CDN tag, add restrictive CSP, keep approved inline SVG data-URI/gradient assets and detail navigation
inside its report frame and add native-versus-accepted provenance/navigation.
Each CGAT wrapper embeds native content with `sandbox=allow-scripts`, without
same-origin, top-navigation or popup permissions. Windows Chrome blocks a
sandboxed `file://` document from navigating itself to another local file. The
overview therefore sends a fixed detail-selection message to its own wrapper.
Only the overview wrapper runs a CSP-hash-pinned script, which checks the sender
and resolves the exact detail name against its own list of packaged pages and
explicit unavailable placeholders. It never accepts a URL from the frame. Other
wrappers are script-free. Native detail links stay inside the sandbox and within
the copied report closure. Closure is derived from the overview's actual embedded gap JSON and checked against available native gap diagnostics; a drifted overview is not silently relabeled with another gap list. Missing, blocked or quota-limited detail
reports get an explicit CGAT unavailable page rather than a dangling hyperlink
or fabricated native result. The native overview, both available job directions,
CGAT original-gap pages and raw diagnostic attachments remain separately labeled.

Bindings distinguish artifacts already sealed by native completion from files
observed only when building diagnostics, including incomplete/failed attempts.
Neither a diagnostic HTML nor its successful display establishes native success,
CGAT admission, biological accuracy or final publication.

## Bounded closure and delivery

The portable site records source/report paths, original and displayed hashes,
transformation policy, observed availability and source identities in its report
manifest. The report generation identity includes the helper/policy and complete
native-view closure so cached old text-only sites are not mistaken for new ones.
Native science checkpoints are not invalidated by a display-policy change.

Raw attachments and display bodies share explicit size limits (index/manifest metadata is separate); identical originals share one content-addressed attachment without merging their logical provenance. Raw copies reserve half the shared budget when supported views exist, with the overview first. The display reserves a closed overview and truthful placeholders before admitting larger individual job bodies; copies do not
recursively include reads, whole native genomes, arbitrary directories or unrelated
files. Indexes are bounded/paginated with constant-size neighbouring-page navigation, not an all-pages link list on every page. Known copied report names are matched against one visualization-directory inventory, not a filesystem probe for every gap. Full and Light deliveries include the same
portable report closure. Tests detach that site/package, check every relative
link/frame/resource and hashes, and exercise the actual pinned visualizer over
controlled diagnostic data. Syntax/DOM-double checks are not native biological,
real-browser or final App acceptance; those remain in the final unified matrix.
