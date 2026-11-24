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
    hook = 'select_request_paths' if hasattr(q0_admission, 'select_request_paths') else 'select_q0_paths'
    selector = getattr(q0_admission, hook)

    def capture(data, **kwargs):
        selection = selector(data, **kwargs)
        selected.append((data, selection))
        return selection

    with patch.object(q0_admission, hook, capture):
        row = arm(panel, pin)
    (data, selection), = selected
    if hook == 'select_request_paths':
        # Do not time a report the production first-request consumer no longer
        # asks for. Still compare actual winners before digesting the full record.
        full = q0_admission.select_q0_paths(data)
        def winners(result):
            return {c: None if (p := r.path) is None else (p.nodes, p.joins, p.slices, p.score)
                    for c, r in result.paths.items()}
        if selection.admission.placements != full.admission.placements or winners(selection) != winners(full):
            raise ValueError('request-only placement or winning path differs from complete selection')
        selection = full
    a = selection.admission
    def intervals(by_source):
        return [(asdict(k), [asdict(i) for i in v]) for k, v in sorted(by_source.items())]
    return {"panel": row["panel"], "pin": pin, "seconds": row["seconds"], "has_path": row["has_path"],
            "request": digest(row["request"]), "admission": digest([a.records, [asdict(p) for p in a.placements],
                a.unplaced_segment_ids, intervals(a.ambiguous_intervals), asdict(a.policy)]),
            "selection": digest([{c: s.record() for c, s in selection.paths.items()}, intervals(selection.occupied)])}


if __name__ == "__main__":
    print(json.dumps(run(Path(sys.argv[1]).resolve(strict=True), sys.argv[2]), sort_keys=True))
