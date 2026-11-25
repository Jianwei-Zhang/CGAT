"""Run the frozen 4D candidate unchanged; separately identify cap-only record differences.

Write both original and projected digests for diagnosis. Never substitute the
projection in candidate.json, comparison.json or the scientific release gate.
"""
import sys
from pathlib import Path
from unittest.mock import patch


def main(work):
    from lgz_core.q0_paths import SearchResult
    import candidate
    from group import digest, write
    original = SearchResult.record
    pairs = []

    def record(self):
        r = original(self)
        policy = r['diagnostics'].get('policy', {})
        with_old_cap = r
        if 'maximum_coverage_boundaries' in policy:
            if policy['maximum_coverage_boundaries'] is not None:
                raise ValueError('unexpected new cap in original result')
            with_old_cap = dict(r, diagnostics=dict(r['diagnostics'], policy=dict(policy, maximum_coverage_boundaries=200000)))
        pairs.append((digest(r), digest(with_old_cap)))
        return r

    with patch.object(SearchResult, 'record', record):
        candidate.main(work)
    import json
    current = json.loads(Path('candidate.json').read_bytes())
    base = json.loads((Path(Path('baseline-dir').read_text().strip())/'candidate.json').read_bytes())
    paths = current['scientific']['paths']; rows = {}
    for chrom, pair in zip(sorted(paths), pairs, strict=True):
        if pair[0] != paths[chrom]:
            raise ValueError('record capture disagrees with raw path digest')
        rows[chrom] = dict(raw=pair[0], with_old_diagnostic_only=pair[1], reference=base['scientific']['paths'][chrom])
    write(Path('cap-diagnostic-audit.json'), dict(revision=current['revision'], paths=rows,
          only_policy_projection_matches=all(r['with_old_diagnostic_only']==r['reference'] for r in rows.values())))


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve(strict=True))
