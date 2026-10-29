# Customer minimap2 assertion: remaining validation queue — 2026-10-30

## Scope decision

This work is limited to the customer's wheat run failing at
`minimap2::align.c:301 mm_update_extra` with:

```text
Assertion `qoff == r->qe - r->qs && toff == r->re - r->rs' failed.
```

The minimap2 binary/source is not modified. General memory discovery, job-budget
planning, admission scheduling and dispatcher adaptation were out of scope and
have been rolled back. They cannot establish a CIGAR-assertion repair. The App
MAPQ fix `c8e3a4f` is retained as an independent approved change, not evidence
that this customer failure is fixed.

Per the user's instruction, this phase runs no tests, synthetic experiments or CI.
Static source/diff review only. Commits use `[skip ci]`; this is not a test result.
The customer's submitted job, workspace and running diagnostic package are unchanged.

## Evidence currently established

- The failed stage was the first reference mapping, not self-alignment or GRT.
- The task recorded minimap2 **2.31-r1302**. The installed conda specification
  pins `minimap2=2.31`; the binary collected later matches the local controlled
  reproduction hash. The original task did not record its executable hash/path,
  so retrospective byte identity is not claimed.
- Slurm allocation was 503.07G, batch MaxRSS 222.56G, and `sacct` shows no OOM
  state. A sampled MaxRSS is not an exact instantaneous peak, but memory shortage
  is not the supported primary explanation for the assertion.
- The original command was:
  `minimap2 -c -x asm10 -t ${GPM_TASK_THREADS:-10} ...`
- The existing partial PAF is incomplete. Its last output ID does not identify the
  failed query; multithreaded trace without a matched active-query event does not.
- A controlled 270 Mb synthetic self-alignment reproduces the same assertion on
  the unchanged 2.31 binary. Existing parameter contrasts (`--eqx`, smaller query
  or index batches, `--no-long-join` with narrower band, `asm5`, Z-drop and SW
  memory cap) still asserted. `--max-qlen=250M` exited zero only by omitting the
  oversized data and producing empty output, which is not a repair.
- Long-query/CIGAR consistency remains the leading hypothesis. Length alone does
  not prove a particular overflowing CIGAR operation.

## Work kept for this customer issue

| Work | Status | Boundary |
| --- | --- | --- |
| Query localization and selected-record replay | Previously delivered; customer result pending | Does not itself prove a fix |
| Returned-diagnostic read-only reviewer | Implemented; execution validation deferred | Checks evidence identity/association; no replay |
| Existing parameter audit | Previously executed on unchanged binaries | No validated parameter-only workaround yet |
| Normal-input parameter control harness | Implemented; not executed | Rejects a candidate if normal PAF/candidates/MAPQ change |
| Restricted multi-fragment score provenance | Implemented; not executed | Tests split accounting only; not a general recovery |
| Window and downstream comparisons | Existing experimental harnesses | Final scientific acceptance still required |

## Next actions after customer evidence returns

1. Verify the returned archive hash and its stable input/tool identities.
2. Extract a well-formed active query only from matched QR/QT/assertion evidence.
3. Independently replay that complete record against the original target order.
4. If it fails, compare only mechanism-motivated parameters against this exact
   failing baseline. Require nonempty complete output with unchanged normal-input
   coordinates, strands, CIGAR, candidates and confidence semantics.
5. If parameter-only mitigation fails, evaluate checked whole-record windowing or
   another CGAT-level fallback. Reject incomplete candidates, invented MAPQ or
   missing records.
6. Run downstream repair decisions and Final Path comparison. Only the complete
   original workflow succeeding with accepted scientific results closes the issue.

## Final validation queue

1. Review all accumulated changes since the last tested revision.
2. Run tests with unchanged minimap2 2.26-r1175 and 2.31-r1302; retain raw logs.
3. Validate the read-only reviewer against synthetic and returned archives.
4. Run normal-input parameter controls, then only eligible long-query contrasts.
5. Exercise forward/reverse multi-fragment accounting and existing window/downstream
   comparisons, retaining all fail-closed unsupported cases.
6. Apply the selected approach to customer data and verify complete CGAT outputs.

Receiving diagnostics is not completion. The customer trigger, a verified mitigation,
and the original complete workflow remain open.
