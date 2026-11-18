"""Freeze an already-validated, controlled Server bundle as portable text files.

This copies the validation closure; it does not invent evidence or run a legacy
q0 builder. No aligner or Python runtime is needed to consume it in Rust tests.
"""
import argparse
import json
from pathlib import Path
import tempfile

from server.tools.lgz_core.common import read_tsv
from server.tools.lgz_core.contract.validator import validate_contract


def materialize(data, root):
    for name, text in data["files"].items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def freeze_delivery_fixture(root, output, provenance):
    validate_contract(root)
    schema = json.loads((Path(__file__).parents[1] / "contracts/grt_precomputed_v2.json").read_text())
    freeze = json.loads((root / "metadata/grt_q0_freeze.json").read_text())
    selection = json.loads((root / "metadata/grt_q0_selection.json").read_text())
    paths = (set(schema["required_files"]) | set(schema["tables"]) | set(freeze["artifacts"])
             | set(selection["artifact_hashes"]) | {"metadata/grt_q0_freeze.json"})
    paths.update("metadata/" + name for name in ("track_member_orders.tsv", "reference_chr_locator.tsv", "source_seq_n_regions.tsv")
                 if (root / "metadata" / name).is_file())
    paths.update(f"grt/q/{version}.fa" for version in ("q0", "q0r1", "q0f", "q1", "q2", "q3", "q4"))
    for table in schema["tables"]:
        for row in read_tsv(root / table):
            paths.update(value for field, value in row.items() if field.endswith("_relpath") and value)
    data = {"fixture_schema": "lgz_frozen_delivery_fixture_v1", "provenance": provenance,
            "files": {name: (root / name).read_text(encoding="utf-8") for name in sorted(paths)}}
    with tempfile.TemporaryDirectory() as temporary:
        materialize(data, Path(temporary))
        validate_contract(Path(temporary))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=True, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provenance", required=True)
    args = parser.parse_args()
    freeze_delivery_fixture(args.server_dir, args.output, args.provenance)
