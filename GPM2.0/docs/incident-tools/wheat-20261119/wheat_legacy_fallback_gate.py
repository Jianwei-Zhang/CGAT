"""Historical decision replay only. Never run a mapper from this tool."""
from lgz_core.q0_native_frontier import descriptor, first_contact
from lgz_core.q0_sources import Q0EvidenceError


class FallbackGate:
    """Private to one threshold pass. Only recalculate questions for a new set of exact PAFs."""
    def __init__(self, parts, initial, refresh, forced=()):
        self.parts, self.refresh, self.forced = parts, refresh, frozenset(forced)
        self.last_pafs, self.need = (), initial
        self.omissions = []
        self.planned = {}

    def dispatch(self, phase, requests, available, run):
        # Hits enter the draft in original order, including siblings from this batch.
        matrices = [descriptor(phase,r['query_ids'],r['target_ids']) for r in requests]
        self.planned[phase] = [r['id'] for r in matrices]
        results = [run(request, True) for request in requests]
        cold = [(i,row) for i,row in enumerate(matrices) if results[i] is None]
        if not cold:
            return results
        if any(row['id'] not in self.forced for _,row in cold):
            tasks = [*available, *(t for t in results if t is not None)]
            pafs = tuple(dict.fromkeys(t['paf'] for t in tasks))
            if pafs != self.last_pafs:
                print(f'LGZ q0 native fallback: phase={phase} refreshing draft from {len(pafs)} completed PAFs before {len(cold)} cold matrices',flush=True)
                need, have_path = self.refresh(tasks)
                self.need = need if have_path else None
                self.last_pafs = tuple(dict.fromkeys(t['paf'] for t in tasks))
        for i,row in cold:
            reason = ('final_selection_reopened' if row['id'] in self.forced else 'no_bounded_demand' if self.need is None
                      else first_contact(row,self.parts,self.need))
            relevant = reason is not None
            action = 'original_matrix' if relevant else 'defer_disjoint'
            print(f"LGZ q0 native fallback: phase={phase} matrix={row['id']} query_parts={len(row['query_ids'])} "
                  f"target_parts={len(row['target_ids'])} decision={action} reason={reason or 'no_remaining_contact'}",flush=True)
            if relevant:
                results[i] = run(requests[i], False)
                if results[i] is None: raise Q0EvidenceError('required native fallback produced no task')
            else:
                self.omissions.append(row)
        return [t for t in results if t is not None]
