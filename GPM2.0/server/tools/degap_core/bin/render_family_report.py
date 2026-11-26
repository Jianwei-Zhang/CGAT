"""Create a new offline L/R report alongside a finished job, using only its JSON records."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from ExtensionFamilies import fingerprint
from FamilyResult import SCHEMA, render_family_report_from_data


def write_preview(directory):
    directory = Path(directory)
    result = json.loads((directory / "family-result.json").read_bytes())
    payload = {k: v for k, v in result.items() if k != "payload_sha256"}
    if result.get("schema") != SCHEMA or result.get("payload_sha256") != fingerprint(payload):
        raise ValueError("Invalid family result manifest")

    def optional(name):
        path = directory / name
        if not path.exists():
            return None
        raw = path.read_bytes()
        digest = result["artifacts"].get(name)
        if digest is not None and sha256(raw).hexdigest() != digest:
            raise ValueError(f"JSON artifact changed: {name}")
        return json.loads(raw)

    html = render_family_report_from_data(
        result,
        optional("families.json"),
        optional("junction-evidence.json"),
        optional("connection-diagnostics.json"),
    )
    # A sibling keeps artifact links valid. Exclusive creation protects previous previews and symlinks.
    output = directory / "family-report.preview.html"
    with output.open("x", encoding="utf-8") as stream:
        stream.write(html)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_directory", type=Path, help="directory containing family-result.json")
    args = parser.parse_args()
    try:
        print(write_preview(args.job_directory))
    except (OSError, KeyError, ValueError) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")
