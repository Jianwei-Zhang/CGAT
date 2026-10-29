# Returned customer evidence: review and acceptance gates

**Development status, 2026-10-30:** `review_isolation.py` and its test cases have
been written and statically inspected only. Per the user's instruction, **no
execution tests or customer-archive executions of this reviewer were performed**.
Do not present it as a validated customer delivery tool. Keep the already delivered
isolation ZIP and the customer's running diagnostic unchanged.

## Purpose

The forthcoming archive is a **localization diagnostic**, not a repaired CGAT
project. The reviewer reads it without extracting files, launching commands,
opening referenced FASTA paths, altering data, or rerunning minimap2. Its JSON
output never sets `repair_accepted` or `customer_recovered` to true.

This reviewer targets the existing isolation producer's five-member format, not
the earlier broad `CGAT-diagnostics-*.tar.gz` collector. The producer stores its
member `checksums.json` alongside, **not inside**, `diagnostics.tar.gz`; therefore
the reviewer requires the outer SHA-256 separately and computes its own member
hashes. An archive/hash pair is transport consistency, not proof of authenticity.
The harness hash is checked against the local isolation source unless an explicit
expected source hash is supplied. Tool hash comparison is available and should be
used when the operator's independently collected expected hash is known.

### Review constraints

- Regular-file input, no symlink/device input, no extracted paths or overwritten files.
- Maximum compressed input 256 MiB; expanded stream 64 MiB, including TAR/PAX
  metadata; per JSON member 4 MiB; per log 32 MiB; per log line 64 KiB; 60 seconds
  per archive, checked between bounded reads. These guards are review budgets,
  not an OS-enforced memory/time reservation.
- Exact allowlist and producer order: `plan.json`, `report.json`, `inputs.json`,
  `stdout.log`, `stderr.log`. Missing later evidence is allowed only for early
  diagnostic failures. Links, special/sparse files, duplicate or unexpected
  members, unsafe names and oversized metadata are refused.
- SHA-256 and input file identity checks around reading; complete gzip processing;
  duplicate JSON keys and non-finite constants rejected.
- Independent single-thread QR/QT parsing, selected-query/length checks and an
  exact matching assertion; cross-check with the reported trace. A last query
  name, last PAF line or generic nonzero exit is not accepted as localization.
- Cross-check duplicated plans, original supported CIGAR/asm10 command, tool and
  recorded FASTA identities, selected-record provenance and exit/outcome metadata.
- No FASTA is in the archive, so sequence hashes are **reported identity metadata**,
  not sequences independently rehashed by this reviewer. PAF completeness,
  coordinate correctness and biological outputs cannot be accepted from this archive.

## Future commands — deferred until final validation

These examples are **not executed during implementation**. Keep input archives
and SHA strings in private storage. Do not copy customer paths or data into Git.

```bash
python3 GPM2.0/experiments/long_query_alignment/review_isolation.py \
  /private/returned/diagnostics.tar.gz \
  --expected-sha256 "$OPERATOR_ARCHIVE_SHA256" \
  --expected-tool-sha256 "$OPERATOR_MINIMAP2_SHA256"
```

Exit 0 means the diagnostic could be reviewed, **not that alignment succeeded**.
Exit 2 means review refused: retain originals and inspect the reason; do not
weaken the guards automatically. JSON is printed only; shell redirection, if
wanted later, should use a fresh private file.

For two independently collected packages:

```bash
python3 GPM2.0/experiments/long_query_alignment/review_isolation.py \
  /private/returned/selected-replay.tar.gz \
  --expected-sha256 "$REPLAY_SHA256" \
  --baseline-archive /private/returned/locate.tar.gz \
  --baseline-sha256 "$LOCATE_SHA256" \
  --expected-tool-sha256 "$OPERATOR_MINIMAP2_SHA256"
```

The baseline/current comparison requires the same recorded reference bytes,
original query bytes and tool, and the query selected by the baseline assertion.
Parameter contrasts additionally require a **failing selected-record baseline**;
otherwise removing other queries and changing parameters are confounded. A zero
exit under `eqx` or `no-long-join` remains `exited_zero_only`, never a repair.

## Response decision table

| Returned evidence | Supported next step | Not justified |
| --- | --- | --- |
| Wrong SHA, changed identities, inconsistent trace/plan | Preserve originals, resolve evidence mismatch | Blaming version or claiming a fix |
| Timeout, disk guard, other nonzero exit | Review resource/exit evidence | Labeling every failure OOM |
| Matching assertion, no well-formed active query | Continue targeted localization | Inferring query from last PAF row |
| Matching assertion and identified query | Independently replay that whole record against the original target/order | Claiming the root mechanism or repair is proven |
| Whole-record independent replay also fails | Compare narrowly chosen parameters against this exact failing baseline | Treating omitted data as recovery |
| Parameter contrast exits zero | Check complete PAF/CIGAR/coordinates, identities and scientific semantics | Calling exit zero a successful repair |
| Original CGAT workflow completes with accepted results | Customer acceptance after result checks | Replacing missing result checks with log completion |

Do not automatically resubmit jobs. The existing isolation tool already requires
an explicit query for contrasts and an explicit `--execute` for computation. Its
`--case locate --query-id ...` provides the independent baseline after a query is
identified; use a new sibling output directory and preserve the full original
target order/index partitioning. Current customer execution is not interrupted.

## Deferred reviewer test inventory

`test_review_isolation.py` is provided for final validation but has **not run**:
read-only/no-process behavior; hash/source/tool/plan mismatch; bounded archives,
JSON and log lines; malformed/truncated QR/QT; selected-query identity; unexpected
members/links/duplicates; early failures; zero-exit refusal; independent replay and
parameter-contrast identity gates. Test implementation alone is not passing
validation; any discovered failures must be corrected before customer use.
