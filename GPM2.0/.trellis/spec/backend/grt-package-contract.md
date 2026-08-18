# GRT Package Contract

## Scope

Applies to every producer or consumer of the precomputed GRT Server package:

- Server q/donor/stage execution;
- delivery package generation;
- Rust backend import and persistence;
- frontend Final Path/source/evidence navigation;
- cross-layer fixtures and E2E validation.

The executable sources of truth are:

- schema: `server/contracts/grt_precomputed_v2.json`;
- validator: `server/tools/grt_contract.py`;
- App projector: `server/tools/grt_app_package.py`;
- fixtures: `tests/fixtures/grt_contract_v2/`.

## Version Boundary

- Server workdir workflow: `gpm_grt_precomputed_v2`.
- App delivery workflow: `gpm_grt_app_precomputed_v2`.
- Package schema version: `2`; the Server workdir Final Path schema remains `1`, while newly projected App deliveries use Final Path display schema `2`.
- Development builds reject v1 workflows/package schemas rather than upgrading or inferring them.
- App workflow/schema v2 packages with legacy Final Path schema `1` remain importable, but GRT result-display controls stay hidden because they do not carry the display mapping contract.
- No legacy workflow/package-schema or project migration is implemented.
- Unknown workflow/schema values must fail with `UNSUPPORTED_SCHEMA`; never fall back to an empty or legacy Final Path.

## Coordinate and Hash Contracts

- App-facing source, q, event, usage, and Final Path intervals are 1-based closed.
- Raw PAF stays 0-based half-open; raw MUMmer coords stay tool-native and declare their coordinate system.
- Source orientation is explicit `+`/`-`; coordinate ordering does not encode orientation.
- Artifact SHA-256 values hash exact file bytes.
- Sequence SHA-256 values hash the uppercase sequence only, excluding FASTA headers and whitespace.
- Raw evidence and checkpoint artifacts carry their own exact-byte SHA-256.
- Executable identity always retains the resolved path and exact binary
  SHA-256. Version text is accepted only from a successful `--version` probe;
  tools that reject the flag use `version=unknown` rather than persisting the
  command's error text as an apparent version.
- Step3 refill may align against an internal corrected-q2 working FASTA. Its raw query artifact/hash remains exact, while public target coordinates are projected once to the origin q2 object and event `q_after` coordinates are projected to final q3.

## Scenario: App Final Path Display Schema 2

### 1. Scope / Trigger

- Applies when changing Server-to-App projection, App import validation, project-view reads, Final Path semantics, or main/Subview GRT-result rendering.
- The feature displays only the current accepted GRT result. It is not a trace/evidence projection.

### 2. Signatures

- Server input: `gpm_grt_precomputed_v2`, package schema `2`, Final Path schema `1`.
- New App output: `gpm_grt_app_precomputed_v2`, package schema `2`, `final_path_schema_version=2` in `metadata/package.tsv`, and `schema_version="2"` in `metadata/grt_final_path.json`.
- Project-view chromosome field: `grt_display_available: boolean`.
- Project-view non-gap segment fields when available: `assembly_ctg_id: positive integer`, `assembly_source_start: positive integer`, `assembly_source_end: positive integer`.
- Tauri/CLI project-view reads require `project_id`; the mapping is derived from that project's visible `assembly_ctg -> assembly_seq -> source_seq -> dataset` rows.

### 3. Contracts

- The Server projector must validate every non-gap source interval against the authoritative Dataset FAI and require a current-chromosome display card from `chr_assignments.tsv` or `grt_used_contigs.tsv` before emitting schema 2.
- Source coordinates remain 1-based closed, increasing, and orientation-explicit. A segment length is exactly `source.end - source.start + 1`.
- The App backend maps each schema-2 segment to exactly one visible current-project assembly ctg whose source window contains the result interval. If any segment is absent or ambiguous, the whole chromosome gets `grt_display_available=false` and no segment mapping fields.
- Mapping fields are derived read-model data. They remain in `grtProjectView.baselineFinalPathByChr` and must not be copied into editable/persisted Final Path rows.
- Frontend controls require schema 2, `grt_display_available=true`, an unphased single current path, and semantic equality with the immutable baseline. Semantic equality includes ordered source identity, range, orientation, and gap values.
- Schema-1 App Final Path packages remain importable for compatibility but never expose either GRT-result switch.

### 4. Validation & Error Matrix

| Condition | Required result |
|---|---|
| Server Final Path source is missing from FAI or range/length is invalid | Projector fails; no App package is emitted |
| Non-gap source lacks an assignment/used-contig display card for the target chromosome | Projector fails; no App package is emitted |
| App package/JSON Final Path schema values disagree | Import fails with `GRT_IMPORT_UNSUPPORTED_SCHEMA` |
| App Final Path schema is neither `1` nor `2` | Import fails with `GRT_IMPORT_UNSUPPORTED_SCHEMA` |
| Schema-2 source has no unique visible project ctg mapping | Import/project creation remains valid; chromosome read model sets `grt_display_available=false` |
| Current Final Path differs semantically or chromosome is phased | Hide both controls and clear any active display state |
| Current main tracks / Subview combination contain no display interval/link | Do not fabricate a mapping; show the scoped three-second empty-result toast only on off-to-on |

### 5. Good/Base/Bad Cases

- Good: schema-2 App package maps every segment uniquely; the unchanged current path exposes independent main and Subview switches.
- Base: a valid schema-1 App package imports and its Final Path remains editable, but both switches are absent.
- Bad: frontend matches `dataset_name + contig_name` strings and guesses an assembly ctg when the backend did not provide a unique ID.

### 6. Tests Required

- Python projector unit tests assert schema-2 output and reject missing display cards or invalid source ranges.
- Rust persistence tests assert unique `assembly_ctg_id/source_start/source_end` mappings and whole-chromosome disablement after a required ctg becomes hidden.
- Server-to-App E2E imports schema 2 and legacy Final Path schema 1; schema 2 exposes mappings, while schema 1 does not enable display.
- Frontend unit tests cover semantic invalidation, `+`/`-` continuity, noncontiguous source ranges, real gap labels, repeated `×N` occurrences, independent switches, and old-package hiding.

### 7. Wrong vs Correct

#### Wrong

```text
frontend sees source name -> guesses visible ctg -> renders partial GRT result
```

#### Correct

```text
Server validates source/card completeness
  -> App schema 2 import
  -> project-aware backend resolves one exact assembly_ctg mapping per segment
  -> whole chromosome available or unavailable
  -> frontend only renders the supplied IDs and 1-based closed intervals
```

## Scenario: App Workspace History Integrity Validation

### 1. Scope / Trigger

- Applies when changing App delivery projection, desktop import layout, or the importer's history validation action.
- The validation target is an imported App workspace, not the Server workdir that produced the delivery ZIP.

### 2. Signatures

- Tauri command: `validate_workspace_integrity(workspaceRoot: String) -> Result<Value, String>`.
- Success payload: `{ workspaceRoot, ok, missing, resultPafCount }`.
- `missing` contains App-relative required paths; `resultPafCount` counts recursive `runs/**/result.paf` files.

### 3. Contracts

- Require `project.sqlite`, `metadata/reference.tsv`, `metadata/datasets.tsv`, non-empty `data/reference` and `data/datasets` directories, `runs`, and at least one `runs/**/result.paf`.
- Full and no-FASTA App workspaces use the same structural check; `.fai` payloads make the no-FASTA data directories non-empty.
- Never require Server-only orchestration files such as `run_all.sh`, generated shell/Python tools, logs, locks, checkpoints, donor work files, or trace evidence. The App projector and delivery allowlist intentionally omit them.
- Missing paths produce `ok=false`; an unreadable/non-directory workspace remains a command error.

### 4. Validation & Error Matrix

| Condition | Required result |
|---|---|
| Workspace path is missing or not a directory | Return command error |
| Required App path is absent | `ok=false` and include that relative path in `missing` |
| No recursive `result.paf` exists | Include `runs/*/result.paf` in `missing` |
| App workspace has all required App files but no `run_all.sh` | `ok=true`; do not report `run_all.sh` |
| no-FASTA workspace contains only source `.fai` files under `data` | Treat the data directories as non-empty |

### 5. Good/Base/Bad Cases

- Good: an imported full package with `project.sqlite`, metadata, FASTA/FAI, and PAF results passes.
- Base: an imported no-FASTA package with FAI-only source directories and PAF results passes.
- Bad: validating an App workspace against the Server workdir layout reports the intentionally omitted `run_all.sh` as missing.

### 6. Tests Required

- Rust regression test creates a valid App workspace without `run_all.sh` and asserts `ok=true`, an empty `missing` list, and the exact recursive PAF count.
- Server-to-App E2E keeps asserting that App delivery ZIPs contain no `.sh` or `.py` files.
- Frontend validation rendering continues to show only paths returned by this command.

### 7. Wrong vs Correct

#### Wrong

```text
Server workdir has run_all.sh -> require run_all.sh in every imported App workspace
```

#### Correct

```text
Server workdir -> App projector allowlist -> imported App workspace
                                        -> validate App-consumed files only
```

## Scenario: Authoritative Assignment Source Orientation

### 1. Scope / Trigger

- Applies whenever ds-vs-ref assignment metadata, q0 mappings, normal source cards, imported assignment rows, or locked-project bootstrap behavior changes.
- The Server assignment row is the immutable baseline. q0 and the App must consume it; neither layer may independently recompute initial source orientation.

### 2. Signatures

- `metadata/chr_assignments.tsv` columns, in order:
  `dataset_name, seq_name, seq_length_bp, assigned_chr_name, source_orientation, orientation_source, support_bp, support_percent, anchor_start`.
- `source_orientation` is `+` or `-`; `orientation_source` is exactly `ref_alignment`.
- SQLite `imported_chr_assignment` persists `source_orientation TEXT NOT NULL` and `orientation_source TEXT NOT NULL` beside the source/chromosome/anchor baseline.
- The bootstrap projection is `imported_chr_assignment.source_orientation -> assembly_seq.orient` for exactly one normal main-view card per assignment row.

### 3. Contracts

- `+` means the projected sequence follows the original Dataset FASTA source interval; `-` means its reverse complement.
- Source coordinates remain 1-based closed and increasing for both orientations. Raw PAF coordinates remain 0-based half-open.
- Server assignment generation sums qualified ds-vs-ref PAF block length by strand for each dataset/contig/chromosome candidate. `-` wins only when its total is strictly greater; ties resolve to `+`.
- q0 source segments must use the assignment baseline orientation and canonical `<dataset>:<contig>:<chr>:normal` card key.
- A `placement_mode=normal` used card must match the assignment baseline orientation and anchor. Promoted/cross-chromosome cards retain their accepted GRT orientation and anchor instead.
- Locked-project initialization validates all normal main-view projections before setting `auto_pipeline_done=true`. Any mismatch deletes the incomplete project.
- Project-level manual flips may change `assembly_seq.orient`; they never rewrite `imported_chr_assignment`.
- Packages or projects that predate these required fields are not migrated or accepted.

### 4. Validation & Error Matrix

| Condition | Required result |
|---|---|
| Missing new assignment columns / old header | `INVALID_TSV` / `GRT_IMPORT_INVALID_TSV` |
| `source_orientation` is not `+` or `-` | `INVALID_VALUE` / `GRT_IMPORT_INVALID_VALUE` |
| `orientation_source != ref_alignment` | `INVALID_VALUE` / `GRT_IMPORT_INVALID_VALUE` |
| q0 orientation differs from assignment | `BROKEN_REFERENCE` / `GRT_IMPORT_BROKEN_REFERENCE` |
| Normal used-card orientation or anchor differs | `BROKEN_REFERENCE` / `GRT_IMPORT_BROKEN_REFERENCE` |
| Existing normal main-view card differs during initialization | Initialization fails and deletes the project |
| Assignment projection count is not exactly one | Initialization fails and deletes the project |

### 5. Good/Base/Bad Cases

- Good: negative PAF block length exceeds positive; assignment, q0, imported baseline, and first main-view render all use `-` with increasing source coordinates.
- Base: strand totals tie; the deterministic baseline is `+` everywhere.
- Bad: bootstrap inserts `+`, q0 uses `-`, then marks the automatic pipeline complete. This is a contract violation even if the frontend faithfully renders the stored `+`.

### 6. Tests Required

- Server preparation test proves q0 consumes `source_orientation` without recomputing PAF strand.
- Shared invalid fixtures cover illegal orientation/provenance, q0 mismatch, and normal used-card mismatch in both Python and Rust validators.
- Importer round-trip asserts orientation/provenance/support/anchor persistence.
- Project bootstrap test inserts a negative baseline and asserts `assembly_seq.orient='-'`.
- Locked initialization test corrupts the projection, asserts failure, and proves the incomplete project was deleted before `auto_pipeline_done` could become true.

### 7. Wrong vs Correct

#### Wrong

```text
bootstrap assigned contig as '+' -> skip initial auto-orient -> auto_pipeline_done=true
```

#### Correct

```text
qualified ds-vs-ref PAF -> chr_assignments source_orientation
  -> q0 and normal used-card validation
  -> imported_chr_assignment baseline
  -> assembly_seq.orient bootstrap
  -> full projection verification
  -> auto_pipeline_done=true
```

## Identity Contracts

- Step1/2/3 rows reference one frozen ordinary `donor_set_id` and FASTA hash.
- Step4 references the independent telomere donor set.
- q mappings are explicit in `metadata/grt_q_segments.tsv`: `segment_kind=source` carries the original source identity/evidence, while `segment_kind=gap` carries no fabricated source and reconstructs its interval as `N`; together the ordered rows must reconstruct q exactly.
- `metadata/chr_assignments.tsv` is a required contract input. Every q0 source segment must be assigned to its target chromosome, match its `source_orientation`, use the canonical normal card key, and point to assignment-stage evidence over that dataset's original ds-vs-ref PAF. Multi-chromosome assignments are represented as a set rather than collapsed by last-row overwrite.
- `grt_contig_roles.tsv` covers exactly the primary plus locked initial support datasets. Datasets or derived contigs appended after precompute remain in the complete GPM source domain but do not acquire retroactive GRT eligibility rows.
- Donor member registries, per-set manifests, donor FASTA records, source intervals, and source slice hashes must agree exactly.
- `metadata/grt_donor_fragments.tsv` is a Server-only derived index over the frozen ordinary D0. Long `N{100,}` runs are boundaries; every indexed fragment retains its D0 member/local coordinates and sequence hash. Creating the index never changes D0 FASTA bytes, `donor_set_id`, or q0.
- A donor interval may be reused for a different gap object only with the same source orientation. Reuse is not physical consumption: target overlap and same-object arbitration still reject conflicts, while accepted reuse records the prior candidate ID and policy in the event lineage.
- q stage rows form the fixed q0 -> q0r1 -> q0f -> q1 -> q2 -> q3 -> q4 transition order.
- Step2 and Step3 MUMmer use `nucmer -c 1000 -l 100 --batch=500000000`, `delta-filter -r -l 10000`, and `show-coords -r -l`; a malformed bare `delta-filter -i` is not part of the contract.
- `server/prepare.sh` resolves the MUMmer tools from PATH and, before creating
  the output workspace, verifies that their help output advertises every
  option consumed by the locked recipe: nucmer `--batch` plus `-t/--threads`,
  delta-filter `-r` plus `-l`, and show-coords `-r` plus `-l`. Command
  existence alone is insufficient because legacy nucmer builds may use the
  same executable name while lacking threaded batch mode.
- `metadata/grt_step2_strategies.tsv` is required and records exactly one controller branch per chromosome: `no_patch_fixer`, `full_fixer_reuse_patches`, `partial_success_no_fixer`, or `no_gaps`, together with patch/fallback counts and the applied result.
- `metadata/grt_step3_classifications.tsv` is required and records each Type1-Type6 candidate, subtype, JSON features, confidence, `conservative|aggressive` repair mode, outcome, fragment and reuse lineage, and the linked Step3 event. When there are no candidates it remains an explicit header-only table. The same classification is carried by the event/evidence trace.
- Step4 searches only q3 terminals lacking the configured telomere signal. It uses the independent frozen Dtel, preserves assigned/unplaced/cross-chr source identity, records one terminal result for both ends of every chromosome, and emits explicit unresolved results when no candidate survives.
- Step4 MUMmer anchors require identity >= 99% and aligned length >= 15 kb. Candidate merges require forward minimap2 `asm5` overlap identity >= 99%, overlap >= 3 kb, and MAPQ >= 20. Raw per-terminal coords, per-candidate PAF, exact query/target hashes, ranking, and arbitration outcomes are retained.
- Step4 may fully supersede a prior accepted path segment at a chromosome end; the old event/evidence/usage loses its Final Path claim and links bidirectionally to the accepted terminal event. Partial removal of a traceable segment is a program error.
- Finalization rebuilds every q4 chromosome solely from ordered Final Path source/gap segments and fails on any sequence, length, or SHA-256 mismatch.

## TSV Encoding Contract

- Every `metadata/*.tsv` contract table is UTF-8 and uses tab as its field delimiter.
- Server writers use Python `csv.DictWriter(delimiter="\t")`; therefore fields containing JSON double quotes use standard CSV-style quoting and doubled quote escapes. For example, the logical JSON value `["support"]` is serialized as `"[""support""]"`.
- Consumers must decode the TSV record and its quote escapes before parsing JSON, numbers, booleans, IDs, or paths. Raw line splitting with `split('\t')` is forbidden because it neither decodes quoted JSON nor preserves tabs inside quoted fields.
- Malformed records, invalid UTF-8, and inconsistent field counts fail with `INVALID_TSV` / `GRT_IMPORT_INVALID_TSV`; JSON syntax is validated only after successful TSV decoding.

## Trace Contracts

Initial q backbone:

```text
Final Path source segment
  -> q0 source mapping
  -> original dataset/contig/source interval
  -> existing source card
  -> ref/main-view evidence
```

Accepted GRT donor:

```text
Final Path segment
  -> accepted event
  -> donor usage/source interval
  -> original source identity
  -> visible usage card
  -> GRT stage evidence
  -> display pairwise evidence
  -> ref hit or explicit no-hit with GRT-derived anchor
```

All accepted path-producing event, usage, segment, card, and evidence relationships are bidirectional. A filter/delete/gap-correction event may be accepted without producing a Final Path segment. A previously accepted donor contribution or correction that is removed by a later stage becomes `superseded`, retains its historical evidence and consumed-interval audit trail, links bidirectionally to its replacing event, and must not claim a surviving Final Path segment. A dangling reference is a package error.

`metadata/grt_used_contigs.tsv` contains exactly the cards for surviving accepted path-producing source events. Every row must use the canonical key `<dataset>:<contig>:<target_chr>:<placement_mode>` and link the exact accepted-event and Final Path segment sets in both directions. It also carries non-empty `ref_evidence_ids_json` and `pairwise_evidence_ids_json`; both evidence roles cover the full original source contig.

Ref profiles remain `stage=assignment` evidence over the original dataset-vs-ref PAF. `hit`, `weak_hit`, and `multi_hit` require an explicit target-chromosome ref interval; `multi_hit` requires more than one source PAF hit, whether or not the hits span multiple chromosomes. `other_chr_only` and `no_hit` forbid a target-chromosome interval and declare `anchor_source=grt_final_path`; `no_hit` has an empty hit-chromosome set, while `other_chr_only` has only non-target chromosomes. A source assigned to multiple chromosomes is `normal` on any member of that assignment set and cross-chromosome only outside it. No synthetic ref PAF is allowed.

Normal assigned cards reuse existing target-chromosome main-view pairwise PAF. Only surviving `grt_promoted` and `cross_chr_grt_usage` cards may trigger supplemental display alignment, using the full original source contig against each relevant target dataset's visible-member FASTA. Rejected, superseded, or unused unplaced sources must not produce a card or supplemental display directory.

`run_all.sh` runs evidence finalization after every chromosome-local command, then invokes the full package script followed by the no-FASTA package script. A successful initial run therefore produces both delivery archives without a second user action. Both package scripts remain standalone re-packaging entrypoints for later Server workspace changes and execute the same contract validator before invoking zip, so an incomplete or post-run-mutated trace chain cannot be delivered.

Package scripts write to a temporary archive and atomically replace the final archive only after zip succeeds. Re-running a packager must rebuild from the current Server workspace rather than update an older archive in place; failed validation or zip creation must leave an existing successful archive unchanged.

## Scenario: Step3 Overlap Correction and Cache Identity

### 1. Scope / Trigger

- Applies when changing Step3 Type1-Type6 classification, correction edit coordinates, corrected-q2 origin projection, or Step2/3 cache fingerprints.
- Trigger: any change to `server/tools/grt_step23.py`, its generated runtime copy, correction constants, or the interpretation of MUMmer reference overlap.

### 2. Signatures

- Classifier: `_step3_classify_features(features) -> (error_type, subtype, feature_names, confidence_score)`.
- Edit guard: `_step3_edit_scope_decision(error_type, features, start, end) -> (safe, reason)`.
- Step2/3 fingerprint fields include `engine_version`, exact `engine_sha256`, q/donor/tool identities, parameters, and consumed-interval identity.
- Public correction/event coordinates remain 1-based closed; internal gap keys remain 0-based half-open.

### 3. Contracts

- A crossing alignment remains Type1.
- Any positive reference overlap between anchors on the same frozen D0 record is Type5, regardless of overlap ratio. Small reference overlap must never fall through to Type4.
- Type5 subtype thresholds match current GRT: `<10 kb` small, `<50 kb` medium, otherwise large. Confidence is `min(0.9 + overlap_bp / 1,000,000, 0.99)`.
- Type5 projects the overlap through the right anchor, adds the configured correction margin, then widens the edit only enough to cover the complete origin q2 gap.
- Before applying the normalized-gap Type5 edit, Step3 inspects the exact q2 path neighbors. When both are distinct source contigs from the locked primary dataset and their oriented sequences have an exact terminal overlap of at least 10 kb, Step3 resolves the junction as a primary-only direct deletion.
- Direct primary overlap uses `keep_left_trim_right`: a qualifying flush suffix-prefix match always keeps the complete left source (`trim_left=0`) and removes the duplicate prefix from the right source. Only when no flush match qualifies may Step3 trim at most the correction margin from an unsupported left tail before applying the same ownership policy.
- Direct primary overlap is bounded by the Step3 search range, must leave at least one base of the right source segment, removes the complete normalized gap, and has replacement length zero. It never creates a donor-derived Final Path segment.
- The Type5 MUMmer row and frozen donor usage remain structural support evidence for a direct primary merge; the event records both primary source identities, independent trim counts, overlap length, policy, and `support_sequence_inserted=false`.
- A zero-length direct edit reports `q_after` as the first retained right-side base so public event coordinates remain valid 1-based closed intervals. Deterministic replay deletes the input interval and inserts no sequence.
- If the exact primary overlap is absent or unsafe, Type5 retains the existing overlap-plus-margin normalized-gap correction and corrected-gap refill behavior.
- Every eligible correction edit contains its entire associated q2 gap. If widening would consume another gap object, the candidate is rejected by the existing multi-gap guard.
- An overlap-driven automatic edit larger than 1 Mb is rejected when it exceeds ten times the observed query/reference overlap evidence.
- Corrected-q2 refill objects project once to the origin q2 object and interval; adjacent N-runs must not create an untraceable merged object.
- Changing Step2/3 executable bytes changes `engine_sha256` and forces a cache miss even if a developer forgets to change another parameter. Semantic releases also increment `engine_version`.

### 4. Validation & Error Matrix

| Condition | Required result |
|---|---|
| Same-record reference overlap is positive | Classify as Type5 and use overlap-plus-margin coordinates |
| Type5 has a >=10 kb flush exact overlap between adjacent primary q2 sources | Keep the complete left source, remove the gap and duplicated right prefix, and insert no support sequence |
| Flush and shifted-cut overlap candidates both exist | Select the flush `trim_left=0` candidate |
| No flush overlap exists, but one appears after <= correction-margin left trim | Permit that explicit left trim and retain keep-left ownership across the overlap |
| Direct overlap would consume the complete right source | Reject direct merge and retain the existing Type5 correction/refill path |
| Correction edit omits any part of its associated q2 gap | Fail before applying the edit with `does not cover associated q2 gap` |
| Widened edit intersects a different q2 gap | Reject as `target_interval_spans_other_gap:<object_id>` |
| Overlap-driven edit is >1 Mb and >10x overlap evidence | Reject as `automatic_edit_exceeds_overlap_evidence` |
| Runtime Step2/3 script bytes differ from the checkpoint fingerprint | Recompute Step2/3; never report cache hit |
| Corrected gap cannot resolve one exact origin | Fail rather than fabricate q2 coordinates |

### 5. Good/Base/Bad Cases

- Good: a 10,187 bp same-record overlap next to a 100 bp q2 gap becomes Type5 and edits about 10.4 kb, not the complete 2.89 Mb anchor.
- Good: Type5 donor evidence accompanies a 19,542 bp exact primary suffix-prefix overlap; Step3 keeps the left primary contig intact, trims 19,542 bp from the right primary prefix, removes 100N, and inserts zero donor bases.
- Base: a Type5 edit begins on one side of the gap; widening includes the full gap and still produces one normalized 100 bp corrected gap.
- Bad: classify a 1% same-record overlap as Type4 and replace the entire shorter multi-megabase alignment.
- Bad: reuse a successful Step3 checkpoint after the runtime script changed because only q/donor hashes were checked.

### 6. Tests Required

- Golden classifier coverage proves small and large same-record overlaps are Type5 and query-overlap-only evidence remains the Type4 fixture.
- A real-shape Chr05 regression asserts `27328071-27338457`, Type5, and an edit shorter than 20 kb.
- Unit coverage proves origin-gap containment, second-gap rejection, and large overlap/edit-ratio rejection.
- Unit coverage proves exact suffix-prefix matching, flush keep-left precedence, bounded shifted-left fallback, reverse-orientation source-coordinate slicing, zero-length replay, and primary-only output.
- Cache tests prove `engine_version`/`engine_sha256` changes invalidate Step2/3 while unchanged second runs hit both checkpoints.
- Real Server validation must reconstruct q4, pass the complete contract, and produce both delivery archives.

### 7. Wrong vs Correct

#### Wrong

```text
10,187 bp same-record overlap -> Type4 -> replace 2,891,900 bp -> 100 N
```

#### Correct

```text
10,187 bp same-record overlap -> Type5 -> project overlap + 100 bp margin
-> widen to contain the origin q2 gap -> replace about 10.4 kb -> 100 N
```

When the adjacent primary sources themselves have a safe exact overlap, the
more specific Type5 resolution is:

```text
Type5 donor evidence + exact primary terminal overlap
-> keep complete left primary source
-> delete 100 N + duplicated right-primary prefix
-> zero support bases inserted
```

## Validation Command

```bash
python3 server/tools/grt_contract.py --bundle /path/to/gpm_server
```

Success prints a JSON summary. Failure exits with code 2 and writes:

```text
ERROR <STABLE_CODE>: <message>
```

## App Import and Persistence

- The Rust backend independently enforces package schema v2, Server Final Path schema 1, App Final Path schema 1-or-2 compatibility, and stable-code semantics; desktop import does not shell out to Python.
- Rust dependency direction is `grt_package` facade -> pure contract/delivery
  validators -> parsing/domain helpers. Only an already validated in-memory
  package crosses into persistence, where the importer-owned transaction writes
  the complete graph. Read models, project initialization, and trace queries
  consume persisted rows and do not depend on raw package parser state.
- Python dependency direction is executable `server/tools/grt_*.py` facade ->
  `server/tools/grt_core/` domain/I/O/checkpoint services. Executable stages do
  not import reusable primitives from another executable stage. The
  `grt_contract.py` CLI delegates schema, table, artifact, cross-reference, and
  Final Path validation to `grt_core.contract`.
- `server/prepare.sh` recursively copies the complete `grt_core` package into
  `.prepare_lib/tools/grt_core/`, including nested contract modules, and removes
  generated bytecode caches. Every copied GRT stage must remain directly
  executable from `.prepare_lib/tools` without repository `sys.path` injection.
- Server workdirs are validated against the complete GRT artifact closure before projection. Initial App import accepts only `gpm_grt_app_precomputed_v2` delivery payloads (plus the complete v2 Server fixture path used by operator/backend tests); validation finishes before `project.sqlite`, `exports/`, or `cache/` is created. A rejected ZIP workspace is removed as a whole.
- App delivery packages deliberately omit q0–q3, D0/Dtel, raw evidence FASTA, `grt/cache`, checkpoints, raw trace files, Server scripts, and tool caches. Full packages include source/reference FASTA and q4; no-FASTA packages retain `.fai`, Final Path length/hash metadata, and import with `fasta_available=false`.
- Legacy `package.tsv` headers, unknown workflow/package schema versions, App Final Path schemas outside `1|2`, incomplete App payloads, malformed FAI, broken IDs/coordinates/source chains, and checksum mismatches fail as `GRT_IMPORT_<STABLE_CODE>`.
- After validation, the base catalog, immutable assignment orientation/provenance baseline, locked recipe, minimal source cards, and projected Final Path rows are written in one SQLite transaction. Trace tables are empty for App delivery packages; no Server audit package or legacy-project backfill is used.
- Server-normalized coordinate strings are stored verbatim in row JSON. Raw PAF/MUMmer coordinate-system declarations remain unchanged; the backend never projects them a second time.
- Rust/backend operator queries retain access to the locked recipe, whole Final Path, gap/terminal attempts, evidence rows, and bidirectional Final Path -> event -> source card -> evidence/usage/donor traces. The desktop App/Tauri `get_grt_project_view` boundary intentionally exposes only the locked recipe, projected `final_path_by_chr`, six-field source-card status rows, and the persisted verification summary.
- `verify_persisted_grt_final_path` rebuilds every chromosome from persisted segment/source coordinates and orientations, compares per-chromosome sequence SHA-256, then compares the reconstructed records and exact artifact SHA-256 with `grt/q/q4.fa`.

## Scenario: Import-Trusted GRT Project View

### 1. Scope / Trigger

- Applies when changing locked-project creation, GRT project-view queries, persisted Final Path summaries, or explicit Final Path integrity verification.
- The successful Rust import is the trust boundary for normal App reads. Whole-genome reconstruction must not run synchronously whenever a project is created or its assembly view is opened.

### 2. Signatures

- Normal query: `load_grt_project_view(project_db_path: &Path) -> Result<GrtProjectView>`.
- Lightweight summary: `load_persisted_grt_final_path_verification(project_db_path: &Path) -> Result<GrtFinalPathVerification>`.
- Explicit deep check: `verify_persisted_grt_final_path(project_db_path: &Path) -> Result<GrtFinalPathVerification>`.
- The serialized `verification` object remains `{ chromosome_count, segment_count, q4_artifact_sha256 }` in Rust and camel-case at the Tauri boundary.

### 3. Contracts

- Server validation fully validates q0-q4 and reconstructs the Final Path before projection; App import validates projected Final Path structure/coordinates and q4 manifest metadata before persisting any GRT rows.
- Normal project-view loading reads its verification summary only from SQLite: chromosome and segment table counts plus `grt_package.q4_artifact_sha256`.
- Normal project-view loading must not open source FASTA files or `grt/q/q4.fa`.
- The explicit deep check keeps rebuilding every chromosome, hashing the q4 artifact, and comparing reconstructed records with q4 FASTA records.
- Locked-project creation still bootstraps assembly rows, materializes surviving GRT source cards, and validates every authoritative assignment orientation/anchor projection before setting `auto_pipeline_done=true`.
- The frontend and Tauri response shape do not distinguish the summary source; callers keep receiving the same verification fields.

### App Project-View Projection

- The Server workdir retains the complete evidence closure for validation and operator audit; the App package and SQLite import retain only the projected result contract.
- App-facing project view is a result contract, not a trace browser: Final Path segments retain source dataset/contig intervals, orientation, lengths, q4 hashes, and gap structure; schema-2 reads additionally include only project-resolved display IDs/source windows and chromosome availability. Event/evidence/source-card link arrays and object attempts are not serialized across the Tauri boundary.
- Every non-gap project-view segment carries `source_length`, resolved from the imported SQLite `source_seq.length` row for its `(source.dataset, source.contig)`. This is the authoritative complete source-contig length; it is independent of the segment interval and orientation.
- Project-view projection must reject a missing source catalog row, a non-positive source length, or a source interval outside `source_length`. It must never infer complete length from `max(source.start, source.end, segment.length)`.
- Normal project-view length enrichment remains SQLite-only. Full and no-FASTA imports obtain the same `source_seq.length` from Dataset FAI, so this projection must not open Dataset FASTA or q4.
- Source-card status rows are limited to `source_card_key`, `dataset_name`, `contig_name`, `target_chr`, `placement_mode`, and `ref_alignment_status` so the main view can show passive placement badges without carrying trace payloads.
- Source-card/event/evidence trace commands remain backend CLI/operator capabilities and are not registered as App/Tauri or Vite dev-bridge endpoints.

### 4. Validation & Error Matrix

| Condition | Normal project view | Explicit deep check |
|---|---|---|
| `grt_package` row is missing | Reject as unavailable | Reject as unavailable |
| Persisted Final Path tables are intact | Return their counts and stored q4 hash | Reconstruct and compare all sequences/hashes |
| q4 FASTA is missing after a successful no-FASTA import | Return the persisted summary | Deep check is unavailable until a FASTA-bearing source is supplied |
| q4 FASTA or a source FASTA is corrupted | Return the persisted summary | Reject checksum or reconstruction mismatch |
| Assignment projection differs during locked initialization | Delete the incomplete project and reject | Not applicable |

### 5. Good/Base/Bad Cases

- Good: importing a complete package performs full validation once; later project creation returns the persisted summary without reading large FASTA files.
- Base: an explicit diagnostic calls `verify_persisted_grt_final_path` and receives the same summary after reconstruction succeeds.
- Bad: `load_grt_project_view` calls the deep verifier, causing every create/open request to parse source FASTA, rebuild q4, hash q4, and parse q4 again.
- Bad: removing the deep verifier entirely; explicit integrity diagnostics and mutation regression coverage must remain available.

### 6. Tests Required

- Import a valid fixture, run the deep check once, remove the temporary q4 artifact, and assert `load_grt_project_view` still returns the same persisted verification summary.
- On the same missing-q4 fixture, assert `verify_persisted_grt_final_path` fails while reading the artifact.
- Project a source contig through multiple internal positive/reverse intervals and assert every segment exposes the same FAI-derived `source_length` while retaining its own source coordinates and segment length.
- Assert project-view projection rejects a persisted source interval whose endpoint exceeds the imported `source_seq.length`; no endpoint-derived fallback is allowed.
- Keep locked initialization tests proving corrupt assignment projection deletes the incomplete project before `auto_pipeline_done` is set.
- Keep response-contract tests proving the frontend consumes the unchanged project-view verification shape.

### 7. Wrong vs Correct

#### Wrong

```text
create/open project -> load project view -> rebuild all Final Path sequences -> hash and parse q4
```

#### Correct

```text
import -> full contract validation -> persist trusted GRT closure
create/open project -> load persisted summary
explicit integrity check -> rebuild and hash Final Path artifacts
```

## Tests Required

- The minimal valid fixture passes and its Final Path reconstructs q4 exactly.
- Mutation fixtures cover missing files, unsupported schema, bad TSV, dangling references, invalid coordinates, illegal assignment orientation/provenance, q0/normal-card orientation mismatch, donor/raw/checkpoint checksum mismatches, q0 mapping errors, and missing display evidence.
- Shared fixtures include standard Python-CSV-quoted JSON cells, and Rust tests cover quote unescaping plus malformed record widths.
- Server, Rust, and E2E layers reuse the same fixture family rather than constructing divergent contract examples.
