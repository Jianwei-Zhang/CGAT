"""4D arm for the frozen Donau group.py/compare.py protocol, after the request-only selector split.

Run in a fresh qualification directory, never in the baseline. The caller binds
the runtime, group.py, staged inputs and allocation. No mapper or publication.
"""
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import sys
from time import monotonic
from unittest.mock import patch


def winners(selection):
    return {chrom: None if (p := row.path) is None else (p.chromosome, p.nodes, p.joins, p.slices, p.score)
            for chrom, row in selection.paths.items()}


def main(work):
    from group import CH, digest, hashbytes, must, write
    from lgz_core import q0_admission as adm, q0_preparation as prep, q0_threshold_prepare as threshold
    from lgz_core.q0_paths import reconstruct
    from lgz_core.q0_threshold_acceptance import record
    from lgz_core.q0_threshold_questions import questions

    meta = json.loads((work / 'group.json').read_bytes())
    rev = Path('latest.rev').read_text().strip()
    must(CH == '4D' and meta['n'] == 766 and meta['bp'] == 1074672025 and re.fullmatch('[a-f0-9]{40}', rev),
         'wrong group or revision')
    timing, captured = {}, []
    select = adm.select_request_paths
    start = monotonic()
    seqs = prep._dataset_sequences(work, meta['ds'])  # historical timer starts before reading these FASTAs

    def capture(data, **options):
        entered = monotonic()
        timing['to_selector_s'] = entered - start
        print('ENTER_SELECTOR latest', len(data.parts), len(data.pair_links), flush=True)
        result = select(data, **options)
        timing['selector_s'] = monotonic() - entered
        captured.append((data, result))
        return result

    with patch.object(adm, 'select_request_paths', capture):
        need, has_path = threshold.initial_questions(work, seqs, meta['refs'], meta['assign'], meta['matrices'], threads=8)
    timing['draft_s'] = monotonic() - start
    (data, draft), = captured
    # A request-only result deliberately has no full record. Obtain the actual
    # full selection independently, outside the candidate timer, on the same inputs.
    full = adm.select_q0_paths(data, screen_threads=8)
    raw = record(need)
    must(draft.admission.placements == full.admission.placements and winners(draft) == winners(full),
         'first-request placements or winning paths differ from full selection')
    must(raw == record(questions(data, full, meta['assign'])[0]) and has_path == any(r.path for r in full.paths.values()),
         'first-request routing differs from full selection')

    def geom(rows):
        return [[asdict(k), [asdict(i) for i in v]] for k, v in sorted(rows.items())]

    a = full.admission
    scientific = {'paths': {c: digest(r.record()) for c, r in sorted(full.paths.items())},
                  'records': digest(a.records), 'placements': digest([asdict(p) for p in a.placements]),
                  'unplaced': digest(a.unplaced_segment_ids), 'occupied': digest(geom(full.occupied)),
                  'ambiguous': digest(geom(a.ambiguous_intervals)), 'request': digest(raw), 'has_path': has_path,
                  'sequences': {c: hashbytes(reconstruct(r.path, seqs).encode()) for c, r in full.paths.items() if r.path}}
    write(Path('candidate.partial'), {'chromosome': CH, 'revision': rev, 'scientific': scientific, 'timing': timing,
          'members': meta['n'], 'bp': meta['bp'], 'matrix_bytes': meta['matrix_bytes'], 'ref_records': meta['ref_records'],
          'request_sources': None if need is None else len(need),
          'request_intervals': None if need is None else sum(map(len, need.values()))})
    write(Path('first-request.partial'), raw)
    # Do not overwrite evidence if invoked twice. compare.py only consumes both committed files.
    os.link('first-request.partial', '4d-first-request.json')
    os.link('candidate.partial', 'candidate.json')
    print('4D_REQUEST_AND_FULL_WINNERS_MATCH; historical comparison pending', flush=True)


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve(strict=True))
