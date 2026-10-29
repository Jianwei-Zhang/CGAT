# Post-DP score provenance and missing MAPQ, 2026-10-29

## Delivered scope

Two distinct changes, neither a production long-query fallback:

- **App source fix** (`c8e3a4f`): split-preview confidence and recommended cuts no
  longer treat PAF MAPQ=255 (unavailable) as high quality. Raw values, ordinary
  coverage, coordinates, CIGARs and manual candidate availability are retained.
- **Isolated experiment**: a real post-DP counterexample shows why AS cannot replace
  chain score. Original seed traces plus diagnostic windowed fragments reproduce
  the tool's split-chain scores in a bounded positive-strand two-fragment case.

No minimap2 source/binary, Server runtime, installed customer workspace or published
asset is changed. No installer was built/published. The existing guided prototype
still rejects the two unresolved decoy cases; this audit does not bypass its guard.

## App missing-confidence fix

Affected source: `app/backend/src/contig_split/mod.rs`.

Both high-quality coverage and automatic boundary recommendations previously used
`mapq >= 20`. They now use the same predicate accepting **20 through 254** only.
255 and invalid numeric values do not contribute high-quality support. A raw 255
is **not** rewritten to zero or deleted, and `minMapq` retains its raw-value/sentinel
contract. Known low confidence and missing confidence remain distinct in the data.

Regression coverage includes:

- all-unknown hits remain visible with unchanged ordinary coverage and serialized
  MAPQ=255, but no high-quality coverage or recommended splits;
- unknown evidence cannot supply one side of a recommended boundary;
- mixed known/unknown intervals do not inflate high-quality union coverage;
- known high-quality support ranks above missing-confidence-only support;
- 19/20 and 254/255 boundaries, negative and out-of-range values;
- preview remains read-only, with unchanged database bytes.

### Native host validation

Commands ran on the **Windows host**, not WSL Cargo:

```powershell
Set-Location D:\Desktop\CGAT\GPM2.0\app\backend
cargo test --locked contig_split::tests:: -- --nocapture
cargo test --locked
cargo fmt --all -- --check
cargo clippy --all-targets --locked -- -D warnings
```

- Before the fix, all four new regressions failed: targeted slice **24 passed,
  4 failed**. The unknown-only candidate incorrectly outranked known support,
  and unavailable scores generated recommended boundaries.
- After the fix, the full backend suite: **312 passed, 0 failed, 2 ignored**.
  Ignored tests are the opt-in Q4 and SQLite-index performance probes, not failures
  or silently skipped correctness checks. Formatting and clippy also passed.
- Cargo/rustc 1.92.0, rustfmt 1.8.0-stable, clippy 0.1.92.
- This is Windows backend/runtime-logic evidence, **not native UI interaction or
  signed-install acceptance**. No frontend source/build or browser check was needed.

The frontend audit found transport/preservation of raw MAPQ, but no additional
numeric high-quality thresholds in the inspected UI path. Server GRT's independent
flank/candidate-validation scoring was not modified; fixing this App consumer is
not blanket acceptance of unknown MAPQ in every workflow stage.

Local logs: `/tmp/cgat-mapq255-before-20261029.log`,
`/tmp/cgat-mapq255-after-20261029.log`, `/tmp/cgat-mapq255-clippy-20261029.log`.
Source/log fingerprints and test boundaries are in
`evidence/mapq-consumer-validation.json`.

## Real AS-only filtering counterexample

`audit_post_dp.py` creates three deterministic **200 kb** synthetic cases. The
important case has a full-query exact reference plus a decoy with periodic prefix
substitutions and a 2 kb divergent block near position 185 kb.

All normal comparisons explicitly use `-x asm10 -p 0.8`. The diagnostic `-P` pass
is only used to inspect unselected chains/fragments; its output and MAPQ are never
forwarded as production evidence.

Pinned executable: minimap2 **2.31-r1302**, SHA-256
`b6c81294dc0b68b2f54f8e2f6f3ad6be71a40bccc47a6e244ecebc73bae9501d`.

| Evidence | Chain score (`s1`) | Alignment score (`AS`) | Seeds (`cm`) |
| --- | ---: | ---: | ---: |
| Complete-query exact competitor | 199976 | 200000 | 19986 |
| Decoy before DP splitting | 160915 | unavailable | 14246 |
| Decoy first diagnostic DP fragment | **146016** | **160340** | 12927 |
| Decoy second diagnostic DP fragment | 14899 | 13000 | 1319 |

The decoy is genuinely present in the complete-query preliminary candidates.
An AS-only cutoff at 0.8 × 200000 = **160000** would keep its first fragment.
But normal complete-query minimap2 returns **only the exact reference**. The first
fragment's post-split chain score is below 0.8 × 199976 = **159980.8**.

Upstream v2.31 `hit.c::mm_split_reg` apportions the original chain score by original
anchor counts; `mm_select_sub` consults the resulting chain score/parent relation,
not AS alone. `map.c::align_regs` performs post-alignment parent/subalignment
selection. This is why a CIGAR-score-only patch is not an equivalent repair.
The full selection policy includes other conditions; the ratio here illustrates
this fixture, not a replacement implementation of minimap2 parent selection.

## Original-seed and window-pool witness

The bounded diagnostic obtains original seed records through the **unmodified**
minimap2 flags `--print-chains --print-qname -t 1`. The resulting preliminary PAF
must be byte-identical to the non-traced preliminary run.

The collector accepts only one query, a unique positive-strand original chain,
and two fragment intervals. It validates trace identity, coordinate bounds,
monotonic seed positions, complete/unique seed ownership and original seed counts.
Incomplete, duplicated, mismatched or unsupported trace data is rejected.

A separate diagnostic window pool uses `-P -c --eqx` to avoid discarding fragments
through window-local competition. It retains all raw evidence, restores original
coordinates and applies the existing exact-adjacency stitching/base checks.
This pool is **not** the ordinary guided output and is never published as a final
Server candidate.

In the measured counterexample:

1. Ordinary window-local selection does **not** retain the complete diagnostic
   fragment pool. This limitation remains visible in the receipt.
2. The diagnostic all-chain window pool recovers the same aligned-base/indel paths
   as the bounded whole-query diagnostic pass.
3. Assigning the **original** anchors to the window-recovered fragments gives
   12927 and 1319 seeds, summing to the original 14246.
4. Original chain-score accounting, with the source's float32 rounding behavior,
   reconstructs **146016 and 14899**, exactly matching the independent whole-query
   diagnostic DP scores. Fragment scores are not copied from that oracle.
5. For this unambiguous `=`/`X`-only asm10 fixture, the recovered CIGARs independently
   reproduce AS as well. Indels/ambiguity and general scoring are not supported by
   this small score witness.
6. A threshold illustration with the known full-query exact competitor yields
   the normal baseline's candidate set, unlike the AS-only illustration.

This identifies usable missing provenance and validates a limited recovery path;
**general parent assignment, full candidate selection and MAPQ are not reconstructed**.
The ordinary guided runs still report failure for both decoy cases, and no final
`guided.experimental.paf` is created for them. Neither rejection is relabeled as
an accepted production recovery.

## Reproduction and evidence

```bash
python3 GPM2.0/experiments/long_query_alignment/audit_post_dp.py \
  --minimap2 /absolute/path/to/minimap2 \
  --out /tmp/new-post-dp-audit

python3 -m unittest discover -s GPM2.0/experiments/long_query_alignment
```

- Retained run: `/tmp/cgat-post-dp-final-evidence-20261029`; commands, raw PAFs, original
  trace, window ownership/stitching provenance and refused guidance are separate.
- `evidence/post-dp-audit.json` includes all three cases, original-score witnesses,
  window-derived scores, hypotheses/counterexamples and source/tool fingerprints.
- **53 experimental tests pass** on minimap2 2.26-r1175 and 2.31-r1302, including
  the new score counterexample and malformed/incomplete provenance checks.
- The previous nine GRT comparisons and 270 Mb recovery were **not rerun in this
  phase**; their mapping/recovery implementations are unchanged. Their earlier
  evidence is retained, not presented as new validation of this score witness.

## Next integration gate

The current collector intentionally generates only bounded synthetic input. It
reads the debug trace in memory; the debug protocol is not a stable production API.
Do not run it as a wheat-scale trace collector. A larger-input implementation needs
bounded/streaming provenance handling and resource measurement first.

Next work should connect original-chain provenance to general recovered fragments
(reverse strand, indels, multiple splits/joins, repeats), then validate full
parent/subalignment selection and confidence. The App sentinel fix removes one
consumer hazard, but does not make experimental mappings biologically equivalent
or the customer's failed run accepted. Customer diagnostics/data remain necessary
for that final acceptance.
