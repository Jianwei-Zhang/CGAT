"""Calibration for a single frozen experiment; do not change the normal mapper or accept partial output."""
from hashlib import sha256
import json
from pathlib import Path
import sys

from run_wheat_shortlist_panel import LOOK, INDIRECT, TOOL, digest, need

MAPPING = 'b43c87a03d6f9b3e7cb33aea22293086f88e95a961d6149f47303736b5231538'


def metadata(path, expected):
    data = path.read_bytes()
    need(sha256(data).hexdigest() == expected, 'input digest mismatch: ' + path.name)
    return json.loads(data)


def target_groups(lookup, boundaries):
    """Use the observed native index boundaries, not equal size bins or inferred -I rounding."""
    ordered = sorted(lookup); groups = []; start = 0
    for part in boundaries:
        n = part['targets']; chunk = ordered[start:start+n]; start += n
        need(n > 0 and len(chunk) == n and sum(lookup[q]['length'] for q in chunk) == part['bases'], 'native target boundary mismatch')
        groups.append(chunk)
    need(start == len(ordered), 'incomplete target libraries')
    return groups


def reference_blocks(paf, lookup, groups, queries, expected):
    by_target = {p.encode(): i for i,g in enumerate(groups) for p in g}
    qnames = {q.encode() for q in queries}; seen = set(); digests = [sha256() for _ in groups]
    whole = sha256(); counts = [0]*len(groups); sizes = [0]*len(groups); previous = -1
    with paf.open('rb') as f:
        for line in f:
            fields = line.split(b'\t', 7)
            need(len(fields)==8 and fields[0] in qnames and fields[5] in by_target and line.endswith(b'\n'), 'unknown or truncated PAF record')
            need(int(fields[1])==lookup[fields[0].decode()]['length'] and int(fields[6])==lookup[fields[5].decode()]['length'], 'unexpected query or target length')
            i = by_target[fields[5]]; need(i >= previous, 'PAF is not in native index-part order')
            previous=i; seen.add(fields[0]); whole.update(line); digests[i].update(line); counts[i]+=1; sizes[i]+=len(line)
    need(whole.hexdigest()==expected['paf_sha256'] and sum(sizes)==expected['bytes'], 'reference PAF changed')
    need(seen==qnames and all(counts), 'inadequate positive calibration')
    return [dict(records=n, bytes=b, paf_sha256=h.hexdigest()) for n,b,h in zip(counts,sizes,digests)]


def calibrate(panel_file, mapping_file, phases_file, lookup_file, paf):
    panel = metadata(panel_file, INDIRECT); m = metadata(mapping_file, MAPPING); lookup = metadata(lookup_file, LOOK)
    ph = json.loads(phases_file.read_bytes()); need(ph['mapping']==MAPPING and ph['panel']==INDIRECT and m['tool_sha256']==TOOL and m['panel']==INDIRECT, 'wrong native reference')
    parts=ph['arms']['full']['parts']; groups=target_groups(lookup,parts)
    need(len(parts)==4 and len(lookup)==38267 and sum(p['bases'] for p in parts)==m['original_bp']==31706122489, 'not the original full library')
    data=reference_blocks(paf,lookup,groups,panel['queries'],m['mapper']['full'])
    return dict(mapping=MAPPING,panel=INDIRECT,phases=digest(phases_file),lookup=LOOK,full=m['mapper']['full'],query_fasta=m['query_fasta'],
                parts=[dict(**p,**d) for p,d in zip(parts,data)],
                scope='Observed byte boundaries of the original monolithic mapper output, not evidence that separate processes produce these bytes. No search space removed.')


if __name__=='__main__':
    print(json.dumps(calibrate(*map(Path,sys.argv[1:])),indent=2,sort_keys=True))
