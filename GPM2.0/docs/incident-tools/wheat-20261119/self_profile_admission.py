"""Incident-only reservation heuristic for a 320-GiB x86 allocation.

Not a RAM guarantee. Long/approximate, cross and unknown work stays exclusive.
One completed low-RSS query is NOT evidence that other long queries can overlap.
Only the existing native-small two-process allowance is retained.
"""
import time
from pathlib import Path

from alignment_tasks import AdaptiveDispatcher

POLICY = {'scheduler_memory_mib': 327680, 'reservation_pool_gib': 288,
          'fast_reservation_gib': 288, 'native_reservation_gib': 128,
          'maximum_processes': 2, 'maximum_native_processes': 2, 'maximum_fast_processes': 1,
          'maximum_query_bases': 300_000_000, 'maximum_target_bases': 1_000_000_000}


class SelfDispatcher(AdaptiveDispatcher):
    def __init__(self, bindings, native_exclusive, *, max_fast):
        super().__init__()
        if type(max_fast) is not int or max_fast != POLICY['maximum_fast_processes']:
            raise ValueError('invalid bounded fast-self concurrency')
        self.max_fast = max_fast
        self.native_exclusive = native_exclusive
        self.fast = set()
        self.oversized_native = set()
        for rel, profile in bindings.profiles.items():
            total = sum(profile.native['target_lengths'].values())
            if total > POLICY['maximum_target_bases']:
                self.oversized_native.update(Path(b['directory']) / 'command.sh' for b in profile.native['batches'])
            for index in profile.selected:
                entries = profile.native['batches'][index]['entries']
                if (len(entries) == 1 and entries[0]['length'] <= POLICY['maximum_query_bases']
                        and total <= POLICY['maximum_target_bases']):
                    self.fast.add(Path(bindings.rows[rel]['scripts'][str(index)]['path']))

    def kind(self, task):
        if task.command in self.fast:
            return 'fast'
        if (task.command in self.oversized_native
                or ('_vs_' in task.command.parent.name and not task.command.parent.name.endswith('_vs_self'))):
            return 'exclusive'
        return 'exclusive' if self.native_exclusive(task) else 'native'

    def cost(self, task):
        return {'fast': POLICY['fast_reservation_gib'], 'native': POLICY['native_reservation_gib'],
                'exclusive': POLICY['reservation_pool_gib']}[self.kind(task)]

    def __call__(self, pending, available, budget, active, slots):
        slots = min(slots, POLICY['maximum_processes'] - len(active))
        if slots <= 0 or not available or any(self.kind(item['task']) in ('exclusive', 'fast') for item in active):
            return []
        first = super().__call__(pending, available, budget, active, 1)
        if not first:
            return []
        if self.kind(first[0][0]) in ('exclusive', 'fast'):
            return [] if active else first
        used = sum(self.cost(item['task']) for item in active)
        counts = {kind: sum(self.kind(item['task']) == kind for item in active) for kind in ('fast', 'native')}
        selected, running = [], list(active)
        left = list(pending)
        for _ in range(slots):
            eligible = [t for t in left if self.kind(t) == 'native'
                        and used + self.cost(t) <= POLICY['reservation_pool_gib']
                        and counts[self.kind(t)] < (self.max_fast if self.kind(t) == 'fast' else POLICY['maximum_native_processes'])]
            got = super().__call__(eligible, available, budget, running, 1)
            if not got:
                break
            task, threads = got[0]
            selected.append((task, threads)); left = [t for t in left if t is not task]
            used += self.cost(task); counts[self.kind(task)] += 1; available -= threads
            running.append({'task': task, 'threads': threads, 'started': time.monotonic()})
        return selected
