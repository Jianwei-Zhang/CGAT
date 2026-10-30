# Hypothesis branch: selective long-CIGAR recovery

Branch: `fix/minimap2-long-cigar-recovery`
Base: `988ca4e907da2fd31cf9d5c1c19eeaf696582b10`
Status: implementation only; **no tests or experiments executed** in this phase.

## Authorized objective and constraints

Develop the isolated recovery path assuming a long CIGAR-operation encoding overflow,
without claiming that assumption is the confirmed customer root cause. Keep
minimap2 source/binary unchanged. The eventual Server integration must retain the
existing `run.sh`/`sbatch` interface and must not ask the customer to split FASTA,
write JSON or estimate memory. Do not change master, Release assets, the running
customer diagnostic or existing workspaces.

## Current branch entry: native first, exact-assertion recovery only

`selective_reference_alignment.py` now composes the unchanged native command with
an actual-failure isolation path. This supersedes the initial length-first route;
the obsolete length partition/two-route merge helpers were removed, not left as
an alternate way to window every long record.

1. Capture source/tool identity and run the original `-c -x asm10 -t ... -o ...`
   shape against the original complete target/query. No FASTA normalization,
   length scan, extra MMI, companion lookup or PAF parser precedes native success.
2. On native exit 0, preserve the complete PAF byte-for-byte, including native
   tags/confidence, long successful records and native-complete zero-byte output.
   The harness does not introduce new cg/AS/line-size requirements on this path.
3. Recovery requires BOTH an abort exit and the exact `mm_update_extra` predicate
   from the customer's assertion. OOM/kill, timeout, unrelated assertion, ordinary
   nonzero or a masked assertion with exit 0 stop. Failed partial PAF is evidence
   only: **no failed-batch prefix is reused**, even if it contains valid-looking rows.
4. Only after this failure, catalog raw FASTA byte ranges without normalized
   sequence spools, rebuild the original default-partition MMI and retain its
   serialized original parts/order. Inherit `mid_occ` from the failed original
   mapping's completed log prefix, not a fresh per-part threshold calculation.
5. Run original-order whole-record groups against each original index part. Keep
   every successful native group unchanged. Divide ONLY an actually asserting
   group into two nonempty halves; recover ONLY an actually asserting singleton.
   Each group has at most one attempt, with at most `2*N-1` tree nodes per original
   part. An independently verified original first-part abort may supply ONLY the
   root node, avoiding its duplicate whole-group run; every asserting singleton
   still executes natively. Missing/ambiguous attribution retains the normal run.
   This is not a parameter sweep or an unlimited retry. **Length is not a trigger**:
   a short query may have a target-consuming long D; unsupported paths still refuse.
6. The prebuilt pinned companion is required only at the actual recovery leaf.
   Existing 50 Mb cores, 100 kb context, original-part whole-query guidance,
   base checks, anchor/state association and native selection remain mandatory.
   The maintainer, not the customer, must build/package the companion.
7. A recovered leaf additionally needs an original-chain-supported **pre-filter**
   path with a logical CIGAR operation longer than 268435455. Adjacent textual
   chunks are coalesced in Python; `=` and `X` both belong to native `-c` M. A merely
   long query or a long path lacking original-chain support is insufficient. A
   supported overflowing path that would later be filtered can supply the witness.
   This evidence supports the hypothesis; it does not prove historical crashed DP.
8. Within recovery, joins require actual native shared-overlap CIGAR evidence,
   not merely touching endpoints; see the raw-seam section below. Merge only
   completed `(original part, original query)` cells. Explicit native
   no-hit cells count as completed; absent, overlapping or foreign cells do not.
   Stream native optional bodies opaquely, validate recovered rows strictly, check
   hashes while assembling and again on shards, preserve multiplicity and emit in
   original part/query order. A rejected source invalidates that assembly.
9. Emit `reference.candidate.experimental.paf` and non-production receipts. A
   separate complete private native-evaluated view is available for maintainer
   comparisons only; neither file is `result.paf`, a success checkpoint or a
   downstream acceptance marker.
   If no singleton assertion reproduces, refuse to call a rerun a recovery.

`native_first.py` contains the classifier, raw record catalog, bounded bisection,
completed-cell merger and logical-operation witness. These are implementation
only, including the mock cases: **no new code has run in this phase**.

Recovered rows still keep unknown MAPQ and omit `AS/ms/s1/s2/tp` claims. Native rows
retain their original bytes/tags; that alone does not establish whole-workflow
scientific equivalence. `guided.experimental.paf` remains a conditional candidate.

The default CLI is **plan only**, creating nothing and starting no tool. Its
`--execute` switch is for a developer's final-validation harness, not a new customer
`run.sh` option. A separate package-overlay/adapter implementation is now present,
but it has not been executed or installed and recovered publication remains
closed. Do not call the branch deliverable before its explicit correctness,
packaging and appropriate acceptance gates are satisfied.

## Original multipart reference context: implemented, execution unverified

`minimap_index_context.py` reads the pinned v2.31 MMI2 serialization: metadata
contains original record membership, followed by bucket and sequence payloads.
The reader skips payloads with bounded metadata reads and checked extents. It
checks little-endian format, supported flags, record IDs/lengths/order, partition
boundaries, file identity and byte hashes. Missing target sequences/names, HPC,
unknown format/flags, duplicates, truncation or a foreign context are refused.

For target-assertion recovery experiments, build the reference index with the normal `asm10`
**default partition policy** (no `-I` override). Copy each serialized part
byte-for-byte into a private index file; do not guess FASTA chunk boundaries or
re-index subsets. Pass that same verified part to both whole-query guidance and
window mapping. Verify its hash again between/after the passes. The legacy
standalone single-index experiment remains available; it is not silently used
for the customer's multipart context anymore.

An additional upstream state must be preserved: v2.31 `mm_mapopt_update` computes
`mid_occ` on the first index part only while its value is unset; subsequent parts
retain it. Independent part invocations would otherwise recalculate it and could
change seed filtering. The native-first branch takes the shared value from the original failed
mapping's completed log prefix. One completed first-part update is sufficient if
the job aborted before later parts; all observed updates must agree and fit the
known original part count. The separate complete-pass helper remains only for
native comparison controls. Both window and whole-query guidance pass
that measured integer via `-f`, after the preset. This is preservation of original
filtering state, not a parameter-workaround sweep or an arbitrary new threshold.
Missing, inconsistent or out-of-range threshold evidence is refused.

The selective driver records each original part and keeps part/query ownership
when combining rows. A normal-only run preserves native PAF order byte-for-byte;
a mixed run uses original part-major order followed by original query order,
not query-major concatenation across parts. A row cannot migrate to another
part's target. Original target records/order and reference bytes are unchanged.

A successful native group with zero rows supplies explicit complete no-hit cells.
An actually asserting singleton cannot be reclassified as an empty/no-hit success:
its guided recovery must produce a supported retained result and the long-operation
witness. The standalone guided empty-output refusal remains; the top-level native
success path accepts native-complete empty output without invoking guidance.

**This addresses index-context handling, not MAPQ or candidate reconciliation.**
No global MAPQ is fabricated from part-local output. The added implementation and
its deferred tests have not run, and a real large-reference equivalence run is
still mandatory before delivery. This does not prove the customer's job will fit
its memory/time/disk allocation.

## Remaining work before a usable branch build

- Execute pinned-MMI format/part-reuse validation and real default-index context
  comparisons on representative large references; context handling is implemented
  but not yet execution-validated.
- Full post-DP candidate completeness, parent/secondary decisions and MAPQ; coarse
  guidance and an AS threshold are not replacements. The known decoy counterexample
  must continue to refuse until correctly handled.
- Boundary conflicts, long target-only deletions, repeats and complex split events.
  A short query window does not bound every possible target-consuming CIGAR op.
- Server command generation/runtime bundling and correct nonzero-exit/checkpoint
  handling, only after there is an accepted recovery result to publish. The branch
  must not quietly run GRT on diagnostic candidates with unknown semantics.
- End-to-end original workflow/scientific acceptance on repaired customer data.

## Deferred validation

`test_native_first.py` defines exact abort/predicate classification, masked-zero
and non-target refusal, failed-prefix threshold capture, raw-record bytes/order,
bounded bisection (including short-query assertion), no-hit completed cells,
opaque/large native PAF bodies, cell ownership/order/duplication, poisoned or
changed shards and source-supported overflowing M/D witness controls.
`test_selective_reference_alignment.py` defines the original native command,
no-scan/no-spool/no-companion native success, opaque and empty output preservation,
lazy companion lookup, partial-output exclusion, deferred witness orchestration,
non-reproduction refusal, identity checks, plan-only and fresh-output controls.
These have **not run**, including mock-only checks. Old validation receipts do
not certify the newly added code or supply scientific evidence for mocked paths.

Additional deferred modules:

- `test_minimap_index_context.py`: MMI2 boundaries, raw-part copying, metadata/payload
  truncation, flags, duplicate IDs, reference ordering and context/hash binding.
- `test_original_index_part_guidance.py`: same part reused across both passes,
  explicit no-hit part, disagreement refusal and unchanged standalone empty guard.

Final testing also needs real mixed ordinary/long synthetic inputs, both strands,
normal-only output comparison, index-part cases, retained decoy negative controls,
and the existing assignment/GRT/Final Path comparisons. Returned customer logs now
establish independent whole-record reproduction (see below), NOT the exact
overflow mechanism or acceptance of a repaired customer result.

## Delivery gate status

- Original multipart index bytes, membership, shared first-part threshold and
  emission order: implemented; static syntax/diff reviewed, execution deferred.
- Native-first preservation, actual-assertion whole-record isolation and
  long-operation witness: implemented; execution deferred.
- Native shared-overlap seam evidence and evidence-compatible fork resolution
  without dropping owned candidates: implemented; execution deferred.
- Complete public/private candidate pairing, unchanged native-cell reuse and
  native-metadata/GRT comparison entry: implemented; execution deferred.
- Native-state/path association, native selection and supplied-state MAPQ:
  implemented in the experimental branch; execution/equivalence unverified.
  Public confidence promotion and full-query DP-state completeness remain open.
- Transparent initial-reference `run.sh` adapter and separate package overlays:
  source implementation added; no development package generated or integration
  executed. Recovered-output admission is still explicitly CLOSED.
- Distributable accepted branch package/rollback and formal recovered publication:
  incomplete; no official Release refresh is authorized by this branch work.
- Existing failed-workspace resume: internal lock/provenance/checkpoint-bound
  handoff and transactional command backup/rollback are source-implemented, not
  executed. Supported old source inventories are prebound by the maintainer;
  actual old/current run.sh resume, compatibility and interruption acceptance
  remain open. No customer edit/configuration or manual migration is required
  by the implemented supported path; unknown/custom recipes refuse untouched.
- Persistent forced-native control reporter: source-implemented; the original
  eight cases plus a 70-target split/competition case are defined, NOT executed.
  No new native comparison receipt or gate pass has been generated.
- Real >28-bit mixed-query selective-entry control: source-defined, NOT executed;
  both 270 Mb strands plus ordinary and native-empty cells are required. No new
  actual-assertion recovery receipt has been generated.
- Final automated/scientific validation: deferred under the existing user request.
- Customer-specific root-cause and complete-workflow acceptance: not established.

A source commit is progress toward delivery, not a claim that all delivery gates
are met. No test result or production readiness is asserted for this increment.


## Window candidate pool and native selection core: implementation only

The selective branch now requests an internal `all_chains_pool` window policy.
Only the short-window mapping command adds native `-P`; the ordinary whole-record
route and preliminary whole-query guidance do not. Existing standalone defaults
also do not change. This avoids pruning competitors solely by each window's
primary/best_n decision. It does NOT prove full-query candidate completeness:
local chaining, seed filtering, DP extension and global ranking-score correction
can still differ. The raw pool is never final PAF or accepted downstream evidence.
All base checks, coordinate restoration, core ownership, reciprocal-unique
stitching, and guided coverage/corridor refusals remain in place.

`post_dp_selection.py` implements the pinned v2.31 **post-skeleton** hit sort,
query-overlap parent assignment and secondary selection for the ordinary asm10
single-query/index-part case. The module does not parse window PAF into native
state and is deliberately NOT wired into the recovery output yet. Its boundary:

- Require complete explicit original state after skeleton filters and optional
  `mm_update_dp_max`, before native hit sorting. No guessed AS/ms/cm/hash or zero
  defaults for missing pre-DP subsc/n_sub/dp_max2.
- Sort by native corrected dp_max and original hash. Port the original radix
  partition order, including hash ties above its 64-record insertion-sort limit;
  Python stable sort is not silently substituted.
- Determine parent competition using query overlap and UNION coverage of current
  primaries, across target IDs/strands. Preserve native strict mask inequality,
  float32 comparison steps and first-primary versus later-primary counter reset.
- Preserve upstream differences between identical-DP-hit exclusion when updating
  dp_max2 and identical-coordinate exclusion when retaining secondary rows.
- Apply native chain-score ratio OR absolute score difference, with a single
  query-wide best_n=50 count, then synchronize retained parent IDs. No AS cutoff.
- Emit a structured selection receipt only, not PAF, native confidence or MAPQ.
  Keep `production_ready:false`, provenance/completeness unproven and execution
  validation explicitly false.

Pinned official source hashes are embedded for hit.c/map.c/options.c/misc.c and
ksort.h; the upstream MIT notices accompany the port. **No minimap2 implementation
or installed binary is patched.** `post_dp_native_oracle.c` is only a deferred
verification harness linking a PRIVATE build of unmodified upstream sources. It
calls native selection functions without running alignment or altering that tool.

### Deferred final-validation checks (NOT run during implementation)

`test_post_dp_selection.py` includes deterministic cases for the score-decoy,
coverage union, different targets/strands, first/later-primary prior counters,
identical/nested DP geometry, seed-count/DP competition, query-wide best_n, small
sort ties and binary32 large-score comparisons. The optional native-source oracle
covers 0/1/2/63/64/65/100/257/600 candidates, large ties, both strands and prior
state. Enabling that oracle will compile a fresh private source copy; it requires
an explicit maintainer-provided `CGAT_MINIMAP2_NATIVE_SOURCE` path and must wait
for the user-authorized final validation phase. This is NOT customer configuration.
The original-index guidance checks also cover pool flag isolation, legacy default
preservation and continued refusal of chain/window disagreement.

Writing these cases and statically parsing Python is NOT a passing test result.
Do not infer an upstream-equivalence or customer-repair claim from this commit.

### Remaining delivery gates

1. Establish all original candidate/anchor ownership and the actual split/trim
   state, retaining global native scores and pre-DP parent metadata; handle native
   DP rejection without demanding fictitious canonical coverage.
2. Reconstruct and validate native post-skeleton ranking-score adjustment before
   supplying state to the new selection core; raw all-chain `ms` is insufficient.
3. Reconstruct/verify whole-query MAPQ, including repetitive length and primary
   competitors; never inherit window MAPQ or mark unknown as high-confidence.
4. Connect only the validated reference-alignment path to the existing run.sh/task
   entry, with atomic final output and original workspace/checkpoint protection.
5. At final validation, execute the deferred native oracle and small/large/normal
   controls, then GRT/Final Path comparisons. Customer localization and the real
   full run remain a separate acceptance gate. No new run.sh flags or manual
   splitting/configuration should be required from the customer.


## Full recovered-path statistics and rank adjustment: implementation only

`whole_query_scores.py` now supplies the score/statistic part of the earlier
selection-state boundary. It reads the **complete recovered path** against
original query/target bases, with at most a 1 MiB sequence fetch per side:

- Base-check =/X on either strand; reproduce native mlen/blen/nn accounting,
  including IUPAC-as-N, insertion/deletion ambiguity and negative ambiguous-base
  scores. Recover the zero-reset local maximum `dp_max0`, without trusting any
  window AS/ms/cm/s1/MAPQ. No AS claim is produced.
- Coalesce adjacent textual pieces of one logical operation with Python integer
  lengths. A serialized >268435455 bp exact run is never encoded into minimap2's
  internal CIGAR, and a gap split across ownership/text boundaries is charged
  only once. Whole-query scoring is not the sum of window scores.
- Port the pinned binary32 `mg_log2` approximation and asm10 gap penalties, not
  math.log2. Preserve ambiguous-base ordering within matches and the native
  truncation model. Refuse unsupported leading-gap normalization, false =/X,
  inconsistent coordinates/counts or native field/arithmetic overflow.
- Implement `mm_update_dp_max`'s query-coverage/runner-up gates, first-equal-best
  convention, event-identity reference, global mismatch/gap factor and corrected
  scores over a caller-supplied **first-filtered** query/index-part candidate set.
  Original anchor counts and that set's completeness remain mandatory separate
  provenance. Mixed or unbound original index parts are refused. This function does NOT discover or certify that set.

The selective branch internally enables `recover_path_scores` (no customer CLI
flag). Guided recovery writes `guided.path-scores.jsonl` before its final private
candidate is promoted, and records the sidecar hash, PAF source hash, input hashes
original index-part hash and implementation identities in guidance.json. Existing normal records and legacy
standalone defaults are unchanged. Sidecar scoring failure prevents candidate
promotion; it cannot bless a partial/incorrect result. The PAF itself still has
unknown MAPQ and no invented native score/type tags.

**Global correction is deliberately NOT applied automatically to the provisional
guided set.** Original anchor ownership and post-DP filtering are not yet proven;
pretending that the set already passed those gates would supply wrong competitors
to ranking. The new functions are score-state implementation, not a bypass of the
existing guided refusals or an assertion of complete whole-query DP equivalence.

### Original chain-state evidence boundary

Pinned map.c/hit.c show that the native hash uses encoded anchor data, including
seed flags; the CN columns currently collected do not print all those bits. It is
not sound to hash just the printed coordinates, to hash window names, or to set
missing pre-DP subsc/n_sub to zero. Remaining work must acquire that state without
changing minimap2, then bind it to actual recovered paths/splits and the new score
outputs before connecting the post-DP selector. No conditional hash guess has
been added to make the branch appear complete.

### Deferred validation additions (none executed)

- `test_whole_query_scores.py`: competing exact/decoy/deletion paths, global
  correction, ambiguity, local resets, gap coalescing, different read-chunk sizes,
  reverse orientation, a >28-bit virtual exact path with bounded reads, native
  threshold/source-identity guards, invalid paths and immutable sidecar input.
- The optional native oracle now includes the **unmodified** pinned align.c only
  in its isolated test translation unit. It can call native static score logic
  and public rank correction without patching/rebuilding the installed minimap2.
  It verifies normalized controlled paths and rejects any oracle input whose
  native normalization changes its coordinates or CIGAR. This is not an aligner.
- Native-source checks compare mlen/blen/nn, local and globally corrected scores,
  event identity, forward/reverse gaps and ambiguous bases. The native source hash
  pins now also cover align.c. Compiler/FMA behavior of the actual pinned tool
  remains a final-oracle acceptance concern, not a claimed bitwise result.
- Original-part guidance mock checks now include binding the path-score receipt
  to the unchanged private PAF; neither AS nor MAPQ is silently promoted.

All these are written, not passed tests. No minimap2 execution, native build,
customer job, downstream run, formal result.paf, Release artifact or new customer
configuration was produced by this implementation increment. Final automated and
scientific acceptance, original-chain-state recovery, MAPQ, transparent run.sh
integration and customer acceptance remain open.


## Original pre-DP chain-state acquisition: implementation only

`native_chain_state.c` is a separate API client of the UNMODIFIED pinned minimap2
v2.31 library. It never enables `MM_F_CIGAR`, never performs DP, and never replaces
or interposes on the installed minimap2 binary. It loads the verified serialized
original index part and maps one complete original query with the inherited
first-part `mid_occ` and fixed asm10 defaults. It reads existing private sequence
spools; original FASTA/MMI/workspace files remain read-only.

The companion exports the actual original hash, score/score0, anchor count/offset,
parent/id, subsc/n_sub, coordinates, strand/retained/split flags, exact hexadecimal
native divergence, repetitive length and fragment gap. It also emits the original
CN trace and complete QR/QT scope markers for later seed-ownership reconstruction.
Those fields are not reconstructed from incomplete printed coordinates, defaulted
to zero, or copied from a window. Retain raw native IDs and multiplicity.

`native_chain_state.py` parses a bounded, complete protocol and compares EACH
native PAF row, generated by unmodified upstream format.c, byte-for-byte with the
independent original whole-query chain pass run by the installed minimap2. It
also checks each state's coordinates/scores/tags/parent references against that
PAF and the original index membership. Any producer failure, missing footer,
foreign query/part, protocol error or PAF difference stops recovery. A matching
coarse PAF is a necessary cross-producer check, NOT proof that the provisional
window candidate set equals native post-DP output.

The branch selective entry requires this companion only for an actually asserting
singleton recovery, never merely for a long query. It checks the bundle before
starting the recovery passes, NOT before the initial or successful native passes.
Native-successful input does not need the companion. The guided branch acquires
`native-chains/original-chain-state.jsonl` before provisional candidate selection.
The ledger preserves original chain-Paf row numbers, input/index/binary hashes,
full-query sequence digest, per-query raw state and trace receipts. This is usable
source state for the next split/ranking/MAPQ bridge, not yet that bridge itself.
Legitimate empty index parts retain the existing explicit no-hit handling.

### Build/delivery contract: maintainer responsibility, NOT customer configuration

The existing Server dependency locks use Conda minimap2=2.31 and do not imply that
a compiler is present on the customer cluster. Therefore **no compiler, source
checkout, manual JSON, new run.sh flag or manual splitting may be required from
the customer**. Build and carry the platform companion in the branch artifact.
Default lookup is internal `native/linux-x86_64` or `native/linux-aarch64`.
`--native-state-bundle` exists only on the isolated developer experiment harness;
it is not a Server/customer option. A missing bundle is a maintainer packaging
failure and is refused before expensive mapping, not a request for user setup.

`build_native_chain_state.py` is maintainer-only, default plan-only. Explicit
execution exports canonical Git object `3c28777e7e2dcc90f825de1b9f17a89cca7d4452`,
not dirty checkout bytes or stale .o/.a files, into a fresh private directory. It
builds only libminimap2.a plus the companion, never the installed minimap2. Source
hash checks before/after, flags, platform, compiler/archiver hashes, library and
helper hashes and upstream license are recorded. CPU architecture selection is
automatic; aarch64 retains the upstream NEON build mode. Generated native outputs
are ignored and must not be committed as if already validated. The runtime reads
only the prebuilt bundle and never downloads or invokes a compiler.

A sequential helper invocation uses the current task's inherited/explicit process
budget, not a new Slurm/cgroup policy or parallel resource dispatcher. Its trace
file is capped at 16 GiB (and any smaller inherited limit), protocol at 256 MiB,
line at 64 KiB, native rows at 100000/query. These are explicit experimental
refusal boundaries, not proof of customer-size completeness. Full-query sequence
memory in the C library remains part of its normal mapping cost; Python reads
sequence digests/trace in chunks rather than retaining all bases/anchors.

### Deferred validation gates: no build, helper or tests executed yet

- Protocol/metadata preservation, missing fields, differing PAF, original IDs,
  empty query, trace scope/footer, artifact identity, no runtime compiler, default
  plan-only behavior and inherited file limit checks have been written.
- Native-success checks reject unnecessary companion lookup. An actually
  asserting singleton requires the packaged companion before recovery alignment.
  Guidance checks refuse a native/coarse mismatch before producing a private PAF.
- `test_native_chain_state_integration.py` requires an explicitly maintainer-built
  `CGAT_NATIVE_CHAIN_STATE_BUNDLE` and unchanged `CGAT_MINIMAP2_BINARY`. It defines
  real forward/reverse duplicate-target and mismatching-PAF controls, without
  compiling/downloading inside the test. A missing artifact is a visible skip,
  NOT equivalence evidence; final acceptance must actually enable this gate.
- We have NOT built either platform helper or established loader/glibc/customer
  runtime compatibility. No distributable branch package exists yet. No native
  acquisition success or original-state/DP equivalence result is claimed.

Next: bind this ledger and its native anchor trace to recovered paths and actual
split/trim state, feed checked full-path/global ranking into post_dp_selection,
then reconstruct MAPQ and integrate the verified path transparently with run.sh.
The old canonical-coverage refusal is still in force until that replacement has
an evidence-backed implementation. All final tests and real customer acceptance
remain outstanding, as do formal package/rollback verification.


## Native state/path/selection bridge: implementation only, not delivery acceptance

`native_recovery.py` now connects the original-chain ledger to recovered paths,
whole-path score calculation and native post-DP selection. The branch native
route no longer relies on the legacy demand that every canonical base of every
preliminary chain be covered. It has NOT simply deleted that guard:

1. Bind all source coarse rows, query receipts, native binary/manifest, original
   index part, window FASTA/manifest, raw PAF and stitched PAF by identity/hash.
2. `batch_seed_ownership.py` scans each original query's complete native CN trace
   ONCE for all retained coarse chains. Match original groups by full geometry
   and count; require a complete sequential partition of the original counts on
   either strand. Native cuts count ORIGINAL anchor endpoints before each aligned
   head end, including bad-end/ignored seeds, not just seeds inside final path
   rectangles. Unsplit records retain original cnt/score even after normal end
   trimming. Use original counts, never local cm/s1. No arrays of all anchors.
3. Candidate association permits genuine cancelling I/D paths rather than an
   endpoint-interpolated diagonal corridor. Only outer extension is bounded by
   pinned asm10 max_gap plus non-HPC k; actual anchor/path evidence must follow.
   Nearby window alternatives need actual original-anchor placement on CIGAR =
   runs, not rectangle containment alone. A positive fragment needs exact support;
   original seeds not on the final path remain in native count accounting (they
   are not erased as if DP never saw the chain). Unsupported competing paths are
   refused; zero-support alternatives are recorded and not promoted.
4. A gap between windows is NOT evidence of a native DP split. For every claimed
   split require a same-window, distinct native head/tail pair with zd flags,
   exact target/oriented-query endpoints and agreeing shared CIGAR path. Rebuild
   source count/score partitions with sequential binary32 tail accounting. All
   source counts must be conserved before filtering; no invented gap coverage.
   A local split showing an unrepresented original-anchor head/tail is refused,
   rather than silently treating its surviving path as an unsplit chain.
5. In original chain/target order apply the pinned first filter (cnt/mlen/DP),
   full-query rank adjustment, then its second DP threshold. Preserve score0,
   native hash, subsc/n_sub and source order through splits. A new native DP extra
   starts with dp_max2=0 by original allocation semantics, not a missing-field
   default. Keep per-fragment score/filter provenance, including rejected rows.
6. `native_selection.py` feeds only complete numerical metadata to the companion
   --select mode. It calls the UNMODIFIED library's hit sort, parent assignment,
   secondary selection and mm_set_mapq2. No CIGAR is encoded, normalized, packed or
   passed back to minimap2. An independent parent/retention replay must agree;
   MAPQ itself comes from the native library, not window MAPQ or Python log math.
   Unsupported native integer/float conversion ranges are refused, not patched
   or replaced with invented confidence.

### Deliberately distinct output levels

- `guided.experimental.paf` and the selective aggregate still withhold confidence
  (MAPQ=255, no native AS/ms/s1/s2/tp claims). They now use the source-backed native
  candidate decisions when the bridge is active; this is NOT final result.paf.
- `native-recovery/native-evaluated.experimental.paf` separately records actual
  native-API MAPQ and computed supplied-state tags for **explicit maintainer
  comparison only**. AS is not reconstructed or emitted. It must not be imported
  or promoted as biologically equivalent merely because the native API exits 0.
- The complete private evaluated file is renamed only after all query decisions
  and input checks finish. Partial files remain pending/error evidence. Reports
  keep whole_query_dp_equivalence_certified:false and production_ready:false.

Native functions being evaluated correctly on supplied metadata does not prove
that window-derived paths/fragments are the complete native whole-query DP set.
Formal confidence promotion, Server run.sh integration, packaging/rollback and
scientific/customer acceptance remain required. The goal is NOT complete.

### Complete evaluated view and real downstream comparison: implementation only

The selective native-first entry now assembles TWO deliberately separate views:

- Public: `reference.candidate.experimental.paf`; native-success cells retain
  their original rows, while recovered cells retain unknown MAPQ=255/no native
  score claims as before.
- Private: `reference.native-evaluated.experimental.paf`; the EXACT SAME ordered
  candidate paths, with supplied-state native API metadata on recovered cells.
  Native-success cells reuse the existing checked shards unchanged; no second
  native-cell spool/copy is created just to construct this view. On an entirely
  native-success run, the evaluation receipt refers to the unchanged public
  native file; no extra parser, companion or duplicate output is needed.

`native_evaluation.py` pairs each recovered cell against its actual producer
hashes. It requires identical first eleven PAF fields, CIGAR, NM/nn and original
chain provenance, identical candidate order/count, the documented metadata tags,
known native MAPQ (0..60), and coherent primary/subscore/secondary metadata.
It rejects guessed AS, missing/extra candidates, duplicate tags, changed private
files and a missing evaluated replacement. Pair failure invalidates assembly.
The evaluated output is reread and hashed when combining; missing pairs can
NEVER silently reuse a public row's sentinel 255.

This makes native confidence available for verification, NOT automatically safe
for production. `whole_query_dp_equivalence_certified` and `production_ready`
remain false. Matching public/private geometry only proves that metadata is
being compared on the same candidate set, not that this is the original DP set.

Why this matters for the actual call chain: `assign_chr_groups.py` exports initial
PAF MAPQ, `grt_prepare_inputs.parse_assignment_paf` retains it, and
`grt_evidence_package.parse_source_paf`/`build_ref_evidence` use the initial PAF core counts and MAPQ to choose/display source
evidence. The current inspected initial-PAF parsers use core fields rather than
AS. This is a source-level dependency observation, NOT proof of complete GRT
acceptance, a promise about future consumers or permission to fabricate AS.
Independent GRT flank/validation alignments and their confidence are unchanged.

`compare_grt.py --native-bridge` is a MAINTAINER-ONLY final-validation mode. It
forces the bridge on the existing nine SMALL synthetic controls (even though
native -c succeeds), and adds a mapped-plus-N-only-unmapped query-member control.
The ten-case mode cannot accidentally validate only the native-first fast path. It preserves original default MMI parts/shared threshold, validates
real native-complete no-hit cells, pairs complete public/private outputs and
substitutes ONLY the private evaluated initial PAF into fresh isolated GRT
workspaces. All other GRT alignments are genuine unchanged native commands.
It compares the ordered native metadata contract AND assignment/GRT/final
sequence/orientation/coordinates/events/Final Path checks. A MAPQ/tag difference
cannot be hidden by similar geometry or a coincidentally equal final sequence.
Source/companion/input receipts are retained; changed comparison/Server sources
invalidate attribution. The native-bridge CLI returns nonzero on any compared
metadata/downstream mismatch, even if geometry and final sequence look equal.
Exit 0 means requested comparisons equal, NOT production acceptance or complete
suite coverage; requested-case equality is distinct from full-suite coverage. All outputs still say production_ready:false; no actual assertion or
customer-scale recovery is claimed by these small controls.

For the later authorized final-testing phase ONLY (not executed now):

```bash
python3 GPM2.0/experiments/long_query_alignment/compare_grt.py \
  --native-bridge \
  --minimap2 /path/to/unchanged/pinned/minimap2 \
  --server-dir "$PWD/GPM2.0/server" \
  --out /tmp/NEW_CGAT_NATIVE_GRT_COMPARISON
```

The maintainer-built pinned companion must already be packaged at its default
platform location, or selected by the harness-only `--native-state-bundle` override.
These are NOT additional customer run.sh flags or customer build/config duties.
The default native-first production-intended trigger is NOT weakened: this forced
small-fixture path exists only in the isolated comparison harness.

`test_native_evaluation.py`, updated selective-driver mocks and the existing
native-DP integration definitions cover pair bindings, metadata differences,
complete mixed views, private replacement mutation/missing-pair refusal, native
byte preservation and the forced comparison path. They have **not run**. The new
GRT mode has **not run**; no helper has been compiled. Old GRT/Final Path receipts
cannot certify this new view. Real >28-bit forward/reverse selective entry,
context/candidate completeness and unsupported-path audits remain mandatory for
a runnable hypothesis-branch delivery or formal confidence promotion. Actual
customer-flow acceptance is a separate requirement before claiming the customer's
problem has been resolved; it must not be substituted by these local controls.


### Native raw-overlap seams: implementation only, no second normalization

The earlier stitch graph tested reciprocal-unique endpoint adjacency. That alone
cannot establish that two native windows agree on the path around the seam: two
base-valid rows can share endpoint coordinates but disagree on an indel placement.
The branch now adds `seam_witness.py`, with no change to minimap2 or its parameters:

- Recovery records exact raw byte extents and SHA-256 for every source PAF row.
  This is binary `tell`/`readline`, not guessed offsets through text translation.
  Retained and exact-duplicate rows both preserve their original source mappings.
- Every owned candidate must still clip exactly from a recorded original raw row,
  including candidates not used by any join. For each potential join, use the
  entire actual shared query overlap and require it to **strictly straddle** the
  core seam. Compare both target intervals and the explicit =XID paths.
- Endpoint-compatible but overlap-conflicting edges do not join. In a fork,
  remove only unsupported JOIN EDGES, then require reciprocal uniqueness among
  the supported edges. A uniquely supported continuation can therefore be joined
  instead of being lost to an endpoint-only fork. Every other owned candidate
  remains an explicit row; this is not score selection or candidate filtering.
- Exact duplicate cores can have different surrounding raw paths. Preserve all
  origins and accept only a real agreeing source pair, rather than trusting the
  first duplicate's context or inventing a path through it.
- Do not apply another whole-path left-normalization pass to already processed
  native-window paths. No coordinates/bases/CIGAR are rewritten by this check.
  The selected join witness records source raw rows, the straddling overlap and
  its exact shared-path digest in `stitch-provenance.jsonl`.
- The native companion route and `all_chains_pool` request these witnesses
  automatically; there is no customer option to disable them. A native-guided
  run refuses an endpoint-only window report. Standalone legacy endpoint-only
  experiment mode remains explicitly labelled as such, not promoted to native
  recovery evidence.
- Hash and recheck raw PAF, ownership/stitch provenance and the seam implementation
  through guided/native recovery. Pending output cannot be renamed to a candidate
  after source evidence changes, even when a changed raw row was context-only.

The extra raw paths are read by offset on demand, not loaded as another complete
raw PAF in memory. A comparison retains a pair and its bounded overlap clips;
the existing owned-path graph is still in memory, so this is NOT a claim that all recovery
memory is constant or automatically fits every allocation. Explicit prototype
bounds are 1M provenance rows, 32 MiB/raw row, 4 MiB/provenance row, 100000 candidate
edges/origin pairs and 16 GiB of source-row read work. Exceeding a bound refuses;
it never skips data, retries parameters or presents partial coverage as success.
These are internal evidence-work bounds, not Slurm/cgroup policy or new user
configuration. Runtime/resource qualification remains part of final acceptance.

`test_seam_witness.py` defines forward/reverse joins, boundary insertion/deletion,
conflicting overlap despite equal endpoints, false-fork resolution with all rows
retained, duplicate-origin choice, partial straddling overlap, no-overlap refusal,
CRLF offsets, tampered owned/raw/provenance records, unused context-row identity
and explicit work-bound controls. Existing native-DP integration definitions now
require the overlap check as well. **None have run**, including the synthetic
mock checks. Their constructed paths are NOT native DP oracle receipts.

This improves local continuity evidence. It does NOT prove whole-query DP path
choice, complete candidate discovery or equality of window/full-query extension
contexts. Original-state association, native selection, the actual nine native
controls (original eight retained), ten GRT controls and >28-bit forward/reverse selective-entry validation
still have to be executed before a runnable branch can be accepted. No Server
entry, customer command/job, compiler, installed minimap2 or Release was changed.


### Additional unsupported evidence patterns remain explicit

Ambiguous CN signatures or unsupported/nonsequential original target-end cuts,
missing anchor-supported paths or unrepresented split children, unobserved split boundaries, native inversion rescue, >64 positive split fragments, a split
tail below the native min_cnt, and unsupported normalization/numeric ranges are
refused rather than dropped or silently reinterpreted. The raw candidate pool is
bounded at 100000 fragments/chain; zero-seed alternatives do not consume the
64-positive-fragment partition ceiling. These are unvalidated experimental
boundaries, not a claim that all customer wheat patterns have been covered.

### Deferred oracle scope (NOT executed)

New protocol/ownership cases cover one/three fragments, both strands, seedless
canonical gaps, nearby alternative diagonals, ambiguous/shared/missing anchors,
missing source fields, native selection output, split observations and withheld
public confidence. The real integration gate now defines NINE comparisons
against unchanged whole-query -c --eqx minimap2: the original identity, two decoy
cases, cancelling indels forward/reverse, three-split decoy forward/reverse,
three-split case without an exact parent, plus a 70-target split/competition pool. Compare complete ordered geometry,
CIGAR, MAPQ, cm/s1/s2/ms/tp, NM/nn/rl and split flags; exit success is insufficient.
AS is explicitly absent rather than claimed equal.

These cases have NOT run. The updated companion has NOT been compiled. A rebuild
from the unchanged pinned source is mandatory before enabling final native tests
because its own companion source hash changed. Existing large guided evidence is
NOT evidence for this new bridge: final validation must also execute the selective
entry with the new companion on real >268435455-bp forward/reverse fixtures, audit
all unsupported-path refusals, then run GRT/Final Path and the real customer flow.
No testing, compilation, mapping, job submission or Release change occurred in
this implementation increment. The existing customer run.sh/sbatch interface has
not acquired any configuration obligation.


Known context boundary, not a hidden success claim: an all-chain window pool may
change local chaining/frequency and nearby-seed DP extension context relative to
the original preselected whole-query set. Replaying native ranking/MAPQ cannot
undo a different base path. Before delivery, retain native-successful long records
unchanged (native-first routing is now implemented but unexecuted), audit path/context
counterexamples and prove the fallback's accepted scope with the named controls
and actual customer input. Do not treat a native-API MAPQ receipt alone as proof
of original DP/path equivalence or an excuse to skip these gates.


## Branch Server adapter and package preparation: source only, not a repair release

This increment adds `server_alignment.py` and `prepare_branch_server_package.py`
under experiments ONLY. The tracked published Server, master, official Releases,
existing customer installation/workspace and running diagnostic remain untouched.
No package, compiler, helper, command-generation shell or mapping was executed.

### Internal run.sh path without customer configuration

The separate package builder now defines three EXACT source overlays in its new copy:

1. `prepare.sh`: keep `run.sh` and all its arguments unchanged; only the
   `write_ref_command_script` asm10 branch generates an internal Python-adapter
   call. asm5, self, chromosome-local/pair and independent GRT commands stay native.
   Copy the complete package runtime into `.prepare_lib/tools/long_cigar_recovery`.
2. `tools/run_outer_checkpoints.py`: bind the initial-reference checkpoint to
   the installed branch runtime/companion files, excluding Python caches, ONLY
   when that reference command actually uses the branch adapter. Installing code
   for a failed reference therefore does NOT invalidate a completed original
   native command's checkpoint. A branch runtime change cannot silently reuse
   an adapted command's checkpoint. No checkpoint success is invented.
3. `tools/server_run.py`: on an already-prepared original -o workspace, call the
   internal handoff after the existing workspace lock/launch-option checks and
   before the original Runner. Fresh preparation keeps the prepare-overlay route.

The builder refuses source drift, duplicate anchors or hooks outside the named
functions. It never rewrites the original Server files. The builder itself does not touch an existing prepared
workspace. The new internal resume hook defines a narrowly scoped handoff when
the user later launches the original run.sh -o command against the branch package;
see the following section. Merely demonstrating fresh preparation would still
be insufficient: the same-existing-workspace route has NOT been executed.
Incremental `add_dataset`/`add_ctg` routes are not silently widened by this overlay.

The adapter takes only GENERATED internal arguments. There is no new customer
run.sh option, JSON obligation, FASTA-splitting step, compiler or binary download.
It uses the same PATH minimap2 and scheduler-provided `GPM_TASK_THREADS`. The
ordinary native fast path does not inherit the six-hour experiment timeout or
an artificial memory cap; job lifetime/allocation remain with the existing job.
Explicit diagnostic recovery passes retain their current prototype bounds.

A narrowly scoped Python-only `prepared_workspace` keyword allows the selective
harness to operate inside its adapter-owned fresh attempt under
`runs/<dataset>_vs_ref/.long-cigar-attempt-*/selective`. Standalone experiment CLI
still refuses prepared workspaces; no user switch disables that protection.

### Publication/attempt semantics

- Acquire a LIVE per-run advisory lock; a leftover lock file alone is not a job.
- Create a fresh private attempt on the same filesystem as `result.paf`. Before
  mapping, move an earlier regular result into that attempt as `prior-result.paf`;
  do not delete it or restore it automatically after a failed new run.
- Native complete success can publish its exact PAF bytes, including an empty
  native-complete file. Hash the exact copied bytes and create `result.paf` via
  an atomic no-clobber hard link. A concurrent output is never overwritten;
  unsupported filesystem publication refuses instead of using an unsafe fallback.
- OOM, unrelated error, cancellation and incomplete/mutated candidates are
  nonzero. Keep attempt evidence, not a partially written formal result. Signals
  TERM/HUP enter the existing child process-group cancellation path, rather than
  abandoning an independently started mapper. No new retry/scheduler logic.
- A recovered candidate currently ALWAYS refuses formal publication, regardless
  of public/private PAF presence or supplied-state MAPQ. The admission closure is
  implemented in code, not a customer-editable manifest/flag/environment option.
  Candidate/evidence files remain available for final validation; downstream must
  not treat them as accepted `result.paf`.

**This closed adapter is not the requested finished fix.** Final acceptance still
has to resolve candidate/path completeness and confidence, then implement the
accepted recovered-publication branch and prove the generated original workflow.
Do not relabel a native-only successful run or a prepared archive as completing
that requirement. The full goal remains active.

### Maintainer package preparation only

The builder's default is plan-only, without scanning sources, validating a binary,
creating an output tree or starting commands. Later explicit `--execute` requires
an ALREADY maintainer-built pinned companion; it never compiles/downloads at job
or package time. This is not a customer build/configuration task.

Its implementation packages the tracked Git Server inventory, excluding tests,
validation receipts and caches, rather than broad-copying an installation with
possible customer FASTA/workspace data. Preserve native executable mode and
licenses; copy the exact named Python dependency closure and own C-client source,
record runtime/source/helper hashes, then prepare a separate development archive.
Archive members are re-read and checked against their named file hashes. Both
`SOURCE.json` and `BRANCH_README.txt` explicitly identify an UNVALIDATED non-official
branch with closed recovered admission; an earlier SOURCE receipt is retained as
`SOURCE.base.json`. Git revision is a baseline; actual copied file hashes bind
any worktree snapshot. No official installer/updater/feed is repointed.

The package is currently NOT customer-deliverable even if this preparation later
executes successfully. Keep the old installation, use an independent workspace,
and preserve evidence. Rollback is selecting the untouched installation and its
own workspace, not mixing branch runtime into existing results/checkpoints.

`test_server_alignment.py`, `test_branch_server_package.py` and updated selective
scope definitions cover opaque native publication, retained prior results, closed
recovery admission, no-clobber races, cancellation handlers, live-lock behavior,
source drift, checkpoint/runtime bindings, tracked-only archive membership,
companion preflight, import closure and preservation of ordinary Server commands.
These checks have been WRITTEN ONLY, NOT RUN. Actual generated-shell/runtime,
archive relocation, loader compatibility, original pipeline and scientific gates
remain unverified and required before declaring the branch deliverable.


## Existing original -o resume handoff: implemented, never run in this phase

`resume_reference.py` is internal package runtime, not a user updater/config CLI.
It complements the adapter without replacing GRT modules, libraries or the
workspace's other generated commands. No existing customer workspace, dependency
environment, running job or diagnostic was changed during implementation.

### Supported handoff and unchanged completed work

1. Enter only inside the existing run.sh workspace lock owned by the current
   process/run ID/host. Retain the normal saved-launch/input/option checks.
   Supplement that lock with local /proc checks for direct standalone workspace
   scripts/minimap2 and the reference adapter's per-run locks. This is not a
   cross-host scan or a promise to identify unregistered remote standalone jobs.
2. Read the prepared metadata and exact original reference plan. Accept only the
   standard initial-reference asm10 command template/one-task manifest. Bash
   printf %q formats DATA arguments in a fixed builtin-only child; saved scripts
   are never evaluated to infer their arguments. Custom options, foreign paths,
   symlinked code/metadata and incompatible recipes refuse before mutation.
3. Ask the actual outer checkpoint manager whether each original reference is
   complete. Keep validated completed command/result/checkpoint/logs untouched.
   Prior status text alone never establishes completion; conversely a recorded
   success whose checkpoint is now incompatible is not quietly reclassified as
   the reported failed task. No GRT or completed-reference rerun is requested by
   the handoff. The original Runner remains responsible for subsequent execution.
4. For unfinished standard commands only, verify a WHOLE package-bound staged
   source inventory. Do not mix arbitrary per-file versions or call a differing
   source tree a wrong minimap2 version. A maintained alternate old profile may
   differ in diagnostics while retaining the exact reference/launch/checkpoint
   recipe. Unknown/user-edited source is preserved and refused, not overwritten.
5. Retain original command bytes/modes and stdout.log/stderr.log/tool_version.txt
   in a new `.run_all/long-cigar-handoff-*` backup/journal. Data, original partial
   PAF, checkpoints, other staged Python/GRT files and logs remain in place. The
   adapter later preserves any old PAF in its own mapping attempt as documented.
6. Install only the named package runtime subdirectory, verified by source/helper
   hashes/modes; do not replace a different shared branch runtime silently. Write
   only selected reference command.sh files with atomic file replacement and
   recheck owner/metadata/source bindings. The report states analysis_started:false:
   the handoff itself starts NO analysis. After a successful handoff, run.sh's
   original Runner proceeds under the user's existing execution request.
7. On failed/interrupted application, restore only command files that still match
   this transaction's exact new hash. Never overwrite a concurrent user edit or
   restore/delete user data. Keep backups and verified installed code for retry.
   An incomplete durable journal is recognized on the next same run.sh command;
   restore its backed-up command state before planning a fresh transaction.
   Unknown/tampered/conflicting journal state refuses instead of guessing success.
   Successful and rolled-back journals are retained, not cleaned out automatically.

This provides a source implementation of the original-workspace entry, NOT an
accepted customer repair. Source-only checks and transaction mocks cannot prove
actual cancellation, filesystem semantics or generated-shell/runtime equivalence.
The recovered-output admission closure remains UNCHANGED: adapted jobs cannot
publish recovered PAF or report recovery success before final acceptance.

### Prebinding the customer's collected source without customer configuration

The already-collected diagnostic identifies installed v2.0.15 source revision
`d1519a76ce1f1df37c9186db1edb26e03a51ab26` and includes its original launch.json
and standard initial-reference command. This turn re-read that existing evidence,
not a new customer result. Git source inspection shows that revision and branch
base retain identical prepare.sh, server_run.py, run_outer_checkpoints.py and
alignment_tasks.py; several diagnostic/retained-failure modules differ. It would
therefore be incorrect to require every staged module to equal the newest tree
or to treat those differences as evidence of the minimap2 failure's root cause.
Only a subset of that customer's staged modules was in the diagnostic; a full
customer-side staged-source match is still UNVERIFIED.

The development builder now accepts maintainer-only
`--resume-source-revision <full immutable Git SHA>`. It reads original module bytes
from the Git object (never executes/materializes old code), requires the same
original prepare/launch/reference-checkpoint/task recipe and binds the COMPLETE
old tool-module inventory into `resume-base.json`, itself hashed by the runtime
receipt. This is generated package provenance, NOT a file/flag the customer must
write. The maintainer can include the collected d1519a76 revision for the eventual
customer build. Missing objects, different recipes, partial/mixed profiles and
unbound staged code refuse rather than adding a manual customer configuration
step. This flag does NOT approve scientific compatibility or enable recovery.

The customer's collected launch manifest supports the normal saved-launch route.
Unsupported legacy workspaces without that recorded launch still retain the
original Server's launch-option restrictions; no general legacy migration is
claimed. Actual acceptance must use the customer's same original command/out
workspace, validate its staged-source profile, retain failed evidence and prove
that already-completed work is not recomputed. The actual failing query/FASTA and
complete recovery remain unconfirmed; this plumbing does not change that boundary.

`test_resume_reference.py` and added package/source-profile definitions cover
checkpoint-preserving selective handoff, no-op/retry, whole old-source profiles,
custom recipe/source refusal, lock/process guards, log/PAF/GRT preservation,
mid-transaction rollback, stopped-journal recovery and concurrent-user-edit
refusal. All are WRITTEN ONLY, NOT RUN. Mocked source/binary/process fixtures are
not native/customer evidence. No helper was compiled, package generated, original
run.sh executed, customer job submitted or Release changed in this increment.


## Persistent native-DP comparison entry: source only, no acceptance receipts

The existing native integration test uses TemporaryDirectory. It is useful as a
future assertion gate, but it cannot by itself leave the full native PAF, state,
raw-overlap and score evidence available after cleanup. This increment adds
`compare_native_controls.py` as a separate MAINTAINER final-validation entry.
It defaults to PLAN ONLY: no output directory, fixture generation, companion
lookup, tool/version command, compile, mapping or job is started in that mode.
This increment has NOT executed even that preview command.

On a later explicitly authorized --execute run, its implementation:

- Requires an already-built pinned companion and unchanged minimap2 2.31-r1302;
  never builds/downloads a binary, reinstalls dependencies or changes minimap2.
- Generates only deterministic SMALL synthetic fixtures under a new private
  directory outside any prepared workspace; uses the same default asm10 index
  policy without -I overrides. These controls are single-part by design and do
  NOT certify the customer's real default multipart context.
- Keeps the native baseline -c --eqx PAF, original index/threshold/input hashes,
  original chain state and traces, raw windows, stitching witnesses, scoring,
  public unknown-confidence and private native-evaluated outputs. Refused/failed
  cases and their full directory are retained rather than deleted or relabelled
  as an accepted workaround.
- Pairs public/private paths using the actual producer hashes, then compares
  the complete ORDERED native contract: all twelve core fields including MAPQ,
  plus cg/NM/nn/ms/cm/s1/s2/tp/rl/zd. Both row multiplicity and candidate order
  matter. Missing/extra rows, a MAPQ difference or a CIGAR/native-tag difference
  are failures even if broad geometry looks similar. AS remains explicitly
  uncomputed/uncompared; full original PAF bytes are retained for investigation.
- Writes per-case field-level differences and an overall source/tool/helper-bound
  receipt. Limit displayed differing rows to 100 but count/compare ALL differing
  rows; a display limit never turns additional differences into equality.
- Retains the original eight controls through shared `native_controls.py` and
  adds `many_equal_split_targets`: seventy identical split-capable target copies
  exercise real pre/post-DP candidate competition and larger split pools, not
  merely an in-memory sort replay or primary-only example. It is an unexecuted
  stress control, NOT a claim that the bridge currently passes it.
- Continues ordinary refused/different cases to retain the other requested
  comparisons. Source/tool/helper mutation invalidates attribution and stops;
  cancellation stops before another case even when the child runner has already
  retained a cancellation receipt. No automatic mapping retry/parameter sweep.
- Distinguishes requested-subset equality from full nine-case coverage/equality.
  Exit 0 means only the requested comparisons are equal. Every output retains
  production_ready:false, customer_validated:false, no promoted confidence and
  no whole-query-DP equivalence certificate. No report unlocks Server admission.

`native_controls.py` is shared with the existing integration definition, avoiding
independently drifting fixture lists. `native_evaluation.py` exposes the same
core/tag key constants to the signature comparison and detailed reporter.
`test_compare_native_controls.py` defines plan-only, field/order/multiplicity,
report-limit, subset/full-matrix, retained-refusal, mutation and cancellation
checks. Those mocks are NOT native evidence. No new definitions, original native
integration, expanded matrix, compiler, package or mapping have run in this phase.

A later final-validation invocation (not executed now) is:

```bash
python3 GPM2.0/experiments/long_query_alignment/compare_native_controls.py \
  --out /tmp/NEW_CGAT_NATIVE_CONTROLS \
  --minimap2 /path/to/unchanged/pinned/minimap2 \
  --native-state-bundle /path/to/maintainer-built/companion \
  --execute
```

These are maintainer validation arguments, NOT customer run.sh options/config.
Actual >28-bit forward/reverse selective recovery, default multipart semantics,
unsupported-path audits, GRT/Final Path, original-command fresh/resume packaging,
and customer-specific acceptance remain separate required gates. Passing a small
matrix cannot substitute for them or prove that window-derived paths comprise
all native whole-query DP candidates. The goal is not complete.


## Remove an invented trace-reader ceiling: source correction only

A scoped audit found a recovery-path refusal unrelated to native alignment
correctness: when neither an explicit reader-process budget nor finite RLIMIT_AS
was present, `trace_memory.choose_buffer` inserted an artificial 128 MiB TOTAL
process budget. Its current-VMS/reserve check could therefore reject a larger
Python parent without any evidence of that actual limit. This is a source-derived
failure condition, NOT a reproduced customer failure or the original assertion's
root cause.

Unknown-limit handling now chooses only a conservative 64 KiB read buffer (or an
already supported bounded explicit buffer request). Effective process budget,
reserve and headroom are null, with explicit unknown flags and no synthetic
source. It neither claims sufficient physical memory nor discovers/reserves
node/job/cgroup memory. Finite RLIMIT_AS and existing explicit process budgets
still use their minimum and refuse insufficient headroom; no real limit is
relaxed. Native child bounds, candidate counts, anchor ownership, byte/line/time
limits, MAPQ policy and recovered-output admission are unchanged. This is not a
new scheduler/resource-management feature or a new customer configuration.

Deferred definitions cover small/large mocked VMS with no limit, bounded buffer
requests, real-limit preservation, and the actual batch anchor-reader path on
both strands. All are WRITTEN ONLY, NOT RUN. Static source parsing/diff review is
not a runtime or scientific acceptance result; the delivery gates remain unmet.


## Real long mixed-input selective-entry control: unexecuted source

`compare_long_identity.py` closes a final-validation ENTRY gap, not the native
algorithm's proof gap. Default PLAN ONLY performs no fixture generation, binary
lookup, version call, mapping, compiler/download or filesystem creation. This
increment has not executed even its preview command.

Later explicit --execute uses the unchanged pinned 2.31-r1302 tool and an already
built companion. A bounded-memory writer creates a deterministic 270,000,000 bp
reference, full forward/reverse exact queries, a 60 kb ordinary exact query and a
3 kb N-only unmapped query. Query order deliberately differs from lexical order;
each binary half contains an asserting long member. More than 810 MB of INPUT
alone is generated, with additional retained index/spool/evidence space required.
There is no CLI length reduction or forced -I override.

The actual existing selective-reference driver is used with its production-
intended 50 Mb cores/100 kb contexts, not forced-small windows or a mock mapper.
A later accepted report checks the actual command/execution files (no dropped
-c, preset switch or skip-length option), real native SIGABRT+the exact assertion, actual
asserting singleton receipts for BOTH long strands, source-supported >28-bit
logical-M witnesses, native shared-overlap evidence and native selection. Both
ordinary and empty cells require completed native-success receipts, never missing
output treated as success. An independent ordinary native -c pass retains the
same default index part and inherited threshold. Its PAF must be byte-identical
to both assembled views; ordinary geometry is also checked against fixture bases.

The long paths must each span the full exact interval, have the expected strand,
full mlen/blen, zero NM/nn and bounded numeric CIGAR chunks forming one long = run.
The private clean-identity MAPQ must be 60 and ms the exact match length, while
public confidence remains 255 without promoted score/parent tags. Public/private
paths are re-paired against producer hashes, and merged rows must remain byte-
identical to those paired source cells. Extra/missing/duplicate candidates,
query reordering, skipped empty cells, source/tool/helper/index/input mutation or
masked/native-success-without-assertion cannot count as an accepted control.
All receipts, failed partials and source evidence remain on disk; cancellation
must stop before the independent ordinary baseline. Nothing retries parameters.

This is single-part simple-identity evidence ONLY, not full arbitrary whole-query
DP equivalence, native-AS reconstruction, actual default multipart validation,
GRT/Final Path, customer run.sh resume or customer root-cause confirmation. Every
report remains production_ready:false/customer_validated:false, with no automatic
Server admission. The current hard-closed recovered-publication policy is unchanged.

Deferred unit definitions cover no-work previews, tiny chunked writer geometry,
both-strand analytic row checks, metadata/order/multiplicity/path/ordinary-byte
refusals, exit+assertion verification, missing prebuilt artifact preflight,
nonasserting native success and cancellation. Mocks/tiny inputs are NOT passing
real-long receipts; none of these definitions or any native execution has run.

Later maintainer invocation (NOT executed in this phase):

```bash
python3 GPM2.0/experiments/long_query_alignment/compare_long_identity.py \
  --out /tmp/NEW_CGAT_REAL_LONG_CONTROL \
  --minimap2 /path/to/unchanged/pinned/minimap2 \
  --native-state-bundle /path/to/maintainer-built/companion \
  --execute
```


## Verified original first-part assertion reuse: unexecuted implementation

The returned customer localization and selected-record replay logs both show the
same exact abort on the unchanged pinned minimap2 2.31-r1302. The independent
selected record is 411,848,600 bp and also aborts on its own. This completes the
whole-record reproduction step; it does NOT prove which original DP operation
overflowed, nor that the branch recovers a correct result. No customer sequence or
PAF was included in the returned log archives, so those logs are not local repair
acceptance. No customer is asked to repeat this completed diagnostic step.

The native-first driver previously repeated the whole original query group on
index part zero even when that first-part assertion was already present. It now
passes an internal original-attempt context, not a new customer flag. Reuse needs
at least two queries, part zero, exact original argv/preset/thread/input paths,
matching command/execution/receipt files, SIGABRT plus the exact assertion, an
unusable failed PAF flag, and current source/tool/default-part bindings. Evidence
files are hashed and guarded against mutation throughout isolation, with final
hash checks. The failed PAF BODY is never read for this decision or reused.

Attribution counts actual `loaded/built the index` log entries independently of
`mid_occ`: upstream may print the threshold only once while loading multiple
parts. Only one complete first-part load matching its source membership and
threshold is eligible. Missing files or missing/ambiguous load metadata retain
the normal root probe; contradictory command/exit/log/context refuses. No
singleton or later index part may reuse the original group abort.

A reused root has its own evidence link, not invented execution files. Its two
nonempty children are still mapped; only actual asserting singleton receipts
enter recovery. Reports distinguish completed tree nodes from actually started
native attempts. Source mutation and non-target failures still abort, and no
asserting singleton still means the selective driver refuses recovery.

Deferred definitions in `test_original_assertion_reuse.py` cover attribution,
root-only reuse, actual singleton replay, no-hit/native child completion,
non-target refusal, safe fallback, command/tool/source/log integrity and final
rehashing. The real-long mixed-input acceptance entry now requires exactly one
verified root reuse and actual remaining attempts; its existing actual receipt,
both-strand singleton, paired path and ordinary-byte checks remain mandatory.
These definitions and the modified entry have NOT RUN. No native build, fixture,
package or mapping was started. Formal recovered-output publication stays CLOSED;
normal native success and the customer run.sh/sbatch interface are unchanged.
