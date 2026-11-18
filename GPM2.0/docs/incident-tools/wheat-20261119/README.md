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
