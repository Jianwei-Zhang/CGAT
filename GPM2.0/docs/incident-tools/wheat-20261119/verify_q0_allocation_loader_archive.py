import json
from pathlib import Path
import socket
import sys

from lgz_core import q0_regional_mapping as mapping
from probe_q0_loader_allocation import qualify_loader, sha256, smoke_scope
from q0_allocation_loader_replay import replay_archive

root = Path.cwd().resolve()
stage = Path(sys.argv[1]).resolve(strict=True)
if (Path(mapping.__file__).resolve() != stage/'package/server/tools/lgz_core/q0_regional_mapping.py'
        or sha256(mapping.__file__) != '25866e25156c2bf5d7cc90b66ee821c1b7d1485fc64752050092f75c9037c33a'):
    raise ValueError('wrong isolated candidate module')
loader = mapping._probe_mapper_loader('minimap2')
if loader is None:
    raise ValueError('this node has no guarded child-only loader')
child, local = loader.child({'resolved': loader.tool_path, 'sha256': loader.tool_sha256})
smoke = stage/'smoke-v2/smoke.jsonl'
if sha256(smoke) != '04128820aef899c062bdbe0aae39ba3cd3408e2daeae77edf25c612a2060f861':
    raise ValueError('frozen writer smoke changed')
old = smoke_scope(smoke)
print(json.dumps({'phase': 'dependencies_checked', 'host': socket.gethostname(),
                  'differences': sorted(k for k in old if old[k] != local[k])}), flush=True)
replay = lambda: replay_archive(root, stage.parent/'gpm_server', child)
result = qualify_loader(local, old, replay)
if local == old:
    result['explicit_diagnostic_replay'] = replay()
with (root/'archive-diagnostic.json').open('x') as f:
    json.dump({'status': 'native_archive_proof_diagnostic_only', 'no_handoff_authority': True,
               'host': socket.gethostname(), 'proof': result}, f, sort_keys=True, indent=2)
    f.write('\n')
