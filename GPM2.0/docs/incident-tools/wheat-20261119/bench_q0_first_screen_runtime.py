"""Compare actual serial and adaptive selection on the same bounded real reference inputs."""
import json
from pathlib import Path
import sys
from time import monotonic

from bench_q0_indexed_screen_batch import adm, load, require
from lgz_core.q0_threshold_questions import questions


def compare(root):
    data, access = load(root); trials = []; expected = None
    for threads in (1, 8, 8, 1):
        log = []; start = monotonic()
        selection = adm.select_q0_paths(data, screen_threads=threads, progress=log.append)
        decision = selection, questions(data, selection, [])
        elapsed = monotonic()-start
        if expected is None:
            expected = decision
        else:
            require(decision == expected, "serial and production draft decisions differ")
        screens = [m for m in log if m.startswith("reference screen")]
        row = {"budget":threads, "seconds":elapsed, "screen":screens}; trials.append(row)
        print(json.dumps(row), file=sys.stderr, flush=True)
        del decision, selection
    return {"scope":"bounded real reference-only sample; no whole-wheat time or supplementary mapper count",
            "sources":len(data.sources), "parts":len(data.parts), "access":access,
            "trials":trials, "all_decisions_equal":True}


if __name__ == "__main__":
    print(json.dumps(compare(Path(sys.argv[1]).resolve(strict=True)), indent=2))
