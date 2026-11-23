"""Read one pinned panel with the imported selector. Digest the full selection after timing."""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch

from compare_fused_draft_panels import arm
from lgz_core import q0_admission


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def run(panel, pin):
    selected = []
    selector = q0_admission.select_q0_paths

    def capture(*args, **kwargs):
        selection = selector(*args, **kwargs)
        selected.append(selection)
        return selection

    with patch.object(q0_admission, "select_q0_paths", capture):
        row = arm(panel, pin)
    selection, = selected
    a = selection.admission
    def intervals(by_source):
        return [(asdict(k), [asdict(i) for i in v]) for k, v in sorted(by_source.items())]
    return {"panel": row["panel"], "pin": pin, "seconds": row["seconds"], "has_path": row["has_path"],
            "request": digest(row["request"]), "admission": digest([a.records, [asdict(p) for p in a.placements],
                a.unplaced_segment_ids, intervals(a.ambiguous_intervals), asdict(a.policy)]),
            "selection": digest([{c: s.record() for c, s in selection.paths.items()}, intervals(selection.occupied)])}


if __name__ == "__main__":
    print(json.dumps(run(Path(sys.argv[1]).resolve(strict=True), sys.argv[2]), sort_keys=True))
