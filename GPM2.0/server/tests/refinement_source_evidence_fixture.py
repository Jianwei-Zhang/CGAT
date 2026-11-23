"""Explicit controlled annotation inputs/producers; never native-tool acceptance."""
import hashlib
import json
from pathlib import Path
from workspace_layout import WorkspaceLayout


def frozen_rules(root, *, chromosome="*"):
    layout = WorkspaceLayout.detect(root)
    entries = [{"source": "parameter", "id": "controlled", "sha256": "a" * 64, "note": "controlled source annotation fixture"}]
    provenance = json.dumps(entries)
    values = {"tel/rules.tsv": "rule_id\tmotif\tmin_repeat\treverse_complement\tprovenance\nfixture_tel\tGT\t1\ttrue\t" + provenance + "\n",
              "cen/reference.tsv": "cen_id\tchr_name\tsequence_name\tfasta_relpath\tmin_len\tmin_identity\tprovenance\nfixture_cen\t" + chromosome + "\trepeat_1\tcen/library.fa\t2\t90\t" + provenance + "\n",
              "cen/library.fa": ">repeat_1\nGT\n"}
    for name, value in values.items():
        path = layout.path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
    snapshot = {"schema_version": 1, "tel": [{"rule_id": "fixture_tel", "motif": "GT", "min_repeat": 1, "reverse_complement": "true", "entries": entries}],
                "cen": [{"cen_id": "fixture_cen", "sequence_sha256": hashlib.sha256(b"GT").hexdigest(), "length": 2, "entries": entries}],
                "files": {name: hashlib.sha256(value.encode()).hexdigest() for name, value in values.items()}}
    layout.path("metadata/annotation_library_snapshot.json").write_text(json.dumps(snapshot))
    return {layout.path(name): layout.path(name).read_bytes() for name in values}

def controlled_mummer(home):
    folder = Path(home) / "controlled-bin"
    folder.mkdir()
    (folder / "nucmer").write_text("#!/usr/bin/env python3\nfrom pathlib import Path\nimport json,sys\n"
        "name=next(line[1:].split()[0] for line in Path(sys.argv[-1]).read_text().splitlines() if line.startswith('>'))\n"
        "Path(sys.argv[sys.argv.index('-p')+1]+'.delta').write_text(json.dumps({'name':name}))\n")
    (folder / "show-coords").write_text("#!/usr/bin/env python3\nfrom pathlib import Path\nimport json,sys\n"
        "name=json.loads(Path(sys.argv[-1]).read_text())['name']\n"
        "print('1\\t2\\t1\\t2\\t2\\t2\\t100\\t2\\t6\\t100\\t33\\trepeat_1\\t'+name)\n".replace("\\t", "\t"))
    for path in folder.iterdir():
        path.chmod(0o755)
    return folder
