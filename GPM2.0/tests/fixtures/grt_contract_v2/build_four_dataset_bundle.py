#!/usr/bin/env python3
"""Build a tiny, importable 1-primary/3-support LGZ bundle (synthetic, not biological).

The extra supports intentionally have no chromosome assignments: project roles
and the Assembly dataset menu must not drop datasets without chromosome hits.
Uses only the Python standard library and never modifies the source fixture.
"""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import zipfile


def extend_supports(root):
    for name in ("support2", "support3"):
        for suffix in ("fa", "fa.fai"):
            shutil.copyfile(root / f"data/datasets/support.{suffix}",
                            root / f"data/datasets/{name}.{suffix}")
        for filename in ("datasets.tsv", "source_seq_locator.tsv", "grt_contig_roles.tsv"):
            path = root / "metadata" / filename
            text = path.read_text(encoding="utf-8")
            extra = [line.replace("support", name) for line in text.splitlines()
                     if line.startswith("support\t")]
            path.write_text(text.rstrip("\n") + "\n" + "\n".join(extra) + "\n",
                            encoding="utf-8", newline="\n")
    recipe_path = root / "metadata/grt_recipe.tsv"
    rows = list(csv.DictReader(io.StringIO(recipe_path.read_text(encoding="utf-8")), delimiter="\t"))
    assert len(rows) == 1 and rows[0]["primary_dataset"] == "primary"
    rows[0]["support_datasets_json"] = json.dumps(["support", "support2", "support3"])
    with recipe_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_bundle(output):
    fixture = Path(__file__).resolve().parent / "valid/gpm_server"
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation: never overwrite a user's existing package.
    with tempfile.TemporaryDirectory(prefix="gpm-four-datasets-") as temporary:
        root = Path(temporary) / "gpm_server"
        shutil.copytree(fixture, root)
        extend_supports(root)
        with output.open("xb") as handle, zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    info = zipfile.ZipInfo(path.relative_to(root.parent).as_posix(), (2026, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, path.read_bytes())
    return {"package": str(output), "bytes": output.stat().st_size,
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "primary": "primary", "supports": ["support", "support2", "support3"],
            "unplacedSupports": ["support", "support2", "support3"],
            "scope": "Synthetic contract fixture; not a biological/server-performance test."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New ZIP path; refuses to overwrite existing files")
    args = parser.parse_args()
    print(json.dumps(build_bundle(args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
