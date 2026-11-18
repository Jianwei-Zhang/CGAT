"""Incident-only admission: isolate long queries, retain two small mappings.

Not a RAM predictor or a global production default. No alignment parameters,
commands, task identities, or scientific outputs are changed. Unknown profiles
run exclusively. Existing small manifests avoid scanning chromosome FASTAs.
"""
import json
from functools import lru_cache
from pathlib import Path

from alignment_tasks import AdaptiveDispatcher


@lru_cache(maxsize=128)
def _manifest(path):
    return json.loads(Path(path).read_text())


def needs_exclusive(task):
    """Use the wheat incident's conservative 100 Mb admission threshold."""
    command = task.command
    try:
        if command.parent.parent.name == "batches":
            manifest = _manifest(command.parents[2] / "self_batch_manifest.json")
            rows = [row for row in manifest["batches"]
                    if Path(row["directory"]) == command.parent]
            if len(rows) != 1:
                return True
            lengths = [entry["length"] for entry in rows[0]["entries"]]
            size = sum(lengths)
        elif "_vs_" in command.parent.name and not command.parent.name.endswith("_vs_self"):
            query = command.parent.name.split("_vs_", 1)[1]
            manifest = _manifest(command.parents[1] / (query + "_vs_self") / "self_batch_manifest.json")
            lengths = list(manifest["target_lengths"].values())
            size = max(lengths)
        else:
            return True
        if not lengths or any(type(length) is not int or length <= 0 for length in lengths):
            return True
        return size >= 100_000_000
    except (OSError, ValueError, KeyError, TypeError):
        return True


class MemoryBoundedDispatcher(AdaptiveDispatcher):
    """Large/unknown tasks run alone; small tasks retain a two-process cap."""
    def __init__(self, exclusive=needs_exclusive):
        super().__init__()
        self.exclusive = exclusive

    def __call__(self, pending, available, budget, active, slots):
        slots = min(slots, max(0, 2 - len(active)))
        if not slots or any(self.exclusive(item["task"]) for item in active):
            return []
        first = super().__call__(pending, available, budget, active, 1)
        if not first:
            return []
        if self.exclusive(first[0][0]):
            return [] if active else first
        small = [task for task in pending if not self.exclusive(task)]
        return super().__call__(small, available, budget, active, slots)
