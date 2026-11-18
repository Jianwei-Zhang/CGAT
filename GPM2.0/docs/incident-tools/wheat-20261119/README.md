# Wheat 2026-11-19 incident admission patch

This directory preserves a tested onsite recovery policy, not a production
scheduler default. See `../../wheat-remote-handoff-20261118.md` for the dated
incident, job IDs and receipts. Do not run a historical submission blindly.

`memory_admission.py` subclasses the existing `alignment_tasks.AdaptiveDispatcher`.
It changes admission only: long/unknown mappings run alone, small mappings retain
a two-process limit, and the existing per-task thread allocation is unchanged.
The 100 Mb threshold is an incident heuristic, not a RAM guarantee. Both cross
mappings and self-alignment batches are covered. No scientific parameters change.

The onsite entry point imports this class instead of its previous fixed
`TwoMappingDispatcher`, retains the original checkpoint wrappers, and requests
32 scheduler CPUs plus 327680 MiB memory while preserving the 16-thread execution
budget. Its receipts and all 14 pre-existing cross checkpoints remain on 180.
Do not install this module into an active workspace whose fingerprint captures
runtime files; use a reviewed recovery boundary and preserve the original
checkpoint and leaf-cache locations.

Focused local validation (from the repository root):

```bash
python3 -B -m unittest discover -s GPM2.0/docs/incident-tools/wheat-20261119 -p 'test_*.py' -v
```

On the incident host, prepend the frozen workspace `.prepare_lib/tools` to
`PYTHONPATH`; tests must use that runtime, not whichever master happens to be
checked out. The admission profile is memoized only for the process lifetime;
input/output integrity remains enforced by the existing outer checkpoints.

Future integration must separately generalize admission, durable cross-leaf
reuse and integrity-preserving resume validation. Archiving this patch in master
does not claim those features are enabled in the default Server runtime.


## Isolated seed-filter pilots (not deployed)

- `seed_filter_pilot.py`: three disjoint 5 Mb windows from the longest query in
  each of 3D and 1A; baseline, `-f 0.001`, and `-f 0.005`, with a 300-second
  timeout per alignment. Full source hashes and the frozen Minimap2 hash are
  verified on a compute node. Outputs stay outside the analysis workspace.
- `long_window_pilot.py`: repeats with 20 Mb windows and 600-second timeouts,
  then compares both pilot sets using `paf_anchor_comparison.py`.
- Position checks project a query grid (every 10 kb) through primary CIGARs,
  respect reverse strand and indels, and report missing/additional/ambiguous
  positions. Coverage and PAF row counts alone do not prove mapping agreement.

Remote jobs `42675569` and `42677292` succeeded. The larger pilot measured:

| Query windows | Baseline time / peak RSS | `-f 0.001` | `-f 0.005` |
|---|---|---|---|
| 3D, 3 x 20 Mb | 250.36 s / 22.231 GB | 125.41 s / 12.700 GB | 24.80 s / 4.334 GB |
| 1A, 3 x 20 Mb | 229.39 s / 19.774 GB | 118.41 s / 11.580 GB | 30.25 s / 4.413 GB |

Time is the measured mapping-command wall time, excluding source extraction,
source verification and index construction; RSS is Minimap2's reported GB.
Each configuration ran once, in baseline/0.001/0.005 order, on one x86 node
with the same tool and three threads. These are not end-to-end speedups.

In 3D, all 5998 baseline primary grid positions retained an exactly matching
position under both filters; candidate coverage and CIGAR details still changed.
In 1A, exact support was 5972/5981 and 5965/5981 respectively, with additional
and missing positions. These are agreement with a baseline, not ground-truth
accuracy. All candidate PAFs differ bytewise from baseline. A grid may miss
short changes and windows omit whole-query chaining context.

No production parameters were changed. Do not silently generalize these cross
mapping pilots to self-alignment (`-X`, custom chain/minimizer thresholds),
all chromosomes, or initial reference mapping. Do not adopt a candidate PAF
as if it were produced by the original command: any future use needs an explicit
algorithm/parameter provenance transition and checkpoint-safe adoption.


### Full-context 3D follow-up (candidate only)

`full_3d_seed_pilot.py` runs one full 3D cross mapping with `-f 0.005`, three
threads and an 1800-second command timeout. It uses the original FASTAs, not
sampled windows, and retains input/tool/output hashes. Job `42681096` was
submitted to `agent-X86-46` with 8 CPU / 81920 MiB; inspect its live state.

There is no duplicate baseline submission: the baseline is the already-running
3D leaf of main job `42646893`. The script compares only after that leaf has a
successful checkpoint whose command, input, tool and output identities match.
A PAF file existing (even valid/nonempty) without its leaf checkpoint is not
sufficient. If the baseline is still pending, the candidate is preserved with
status `candidate_complete_native_comparison_pending`, not adopted or declared
equivalent. A later scheduled invocation with `--compare-only` validates the
stored artifacts and performs only comparison; it must not rerun alignment.
This follow-up does not modify either analysis workspace or approve a global
approximation policy. Native and candidate run on different x86 nodes, so any
later timing comparison must disclose that boundary.

Four focused tests exercise refusal of changed inputs/corrupt candidates,
ignore an uncommitted baseline PAF, and verify comparison without replacement.


### Completed full-context measurement and stratification

The full candidate job `42681096` and comparison-only job `42685578` both
succeeded. Native 3D finished and its verified leaf checkpoint was retained.
Minimap2 reported **7091.836 s / 125.225 GB** for native, versus
**583.913 s / 18.254 GB** for the full `-f 0.005` candidate: an observed time
ratio of 12.15 on these two x86 nodes, not a full-workflow speedup.
The candidate processed all 113 queries against 988 targets; query coverage
was 99.686%, versus native 99.625%. All PAF names and lengths were checked
against the assignment-checkpoint-bound `metadata/chr_assignments.tsv`.

Unlike the fragment pilots, full-context results are not position-equivalent:
62577/62772 primary grid positions retained an exact position. In particular,
`stratify_full_3d.py` (job `42686656`, succeeded) found:

| Group | Baseline positions | Exact support | Changed/missing positions |
|---|---:|---:|---:|
| Queries >=100 Mb | 28899 | 28861 | 38 |
| Queries <100 Mb | 33873 | 33716 | 157 |
| All baseline MAPQ=60 positions | 62517 | 62417 | 100 |
| >=100 Mb, baseline MAPQ=60 | 28875 | 28857 | 18 |

Quality filtering is applied only to the baseline; a candidate MAPQ decrease
must not be mistaken for a changed destination. Candidate geometry is always
compared without that quality filter. These are baseline-agreement measures,
not ground-truth accuracy. About 80.5% of the sampled position differences were
in queries below 100 Mb, arguing against indiscriminate whole-group filtering.

A next design to evaluate is whole-record routing: approximate only eligible
very long queries and keep the ordinary path for others, preserving record
order, all query records and per-record provenance. This is **not implemented
or deployed**, has not demonstrated a 12x speedup, and is not validated for the
self-alignment path. The already completed native 3D result should be reused,
not replaced merely to install an optimization. No candidate has been adopted.
