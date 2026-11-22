"""Bounded full-record source FASTA serialization, independent of native recipes."""
from pathlib import Path
import re

try:
    from refinement_path import segment_blocks
except ModuleNotFoundError:
    from .refinement_path import segment_blocks


def write_source_fasta(path, rows, catalog):
    """Copy complete patch records, not chromosome assemblies; write exact FAI."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fai = []
    with path.open("xb") as stream:
        for row in sorted(rows, key=lambda value: value["contig"]):
            name, dataset, length = row["contig"], row["dataset"], row["length"]
            if not name or re.search(r"\s|[\x00-\x1f]", name):
                raise ValueError("patch source has an invalid FASTA identifier")
            stream.write(b">" + name.encode("utf-8") + b"\n")
            offset, pending = stream.tell(), b""
            origin = {"dataset": dataset, "contig": name, "start": 1, "end": length, "orientation": "+"}
            for block in segment_blocks({"kind": "patch", "length": length, "source": origin, "orientation": "+"}, catalog):
                data = pending + block
                end = len(data) // 60 * 60
                if end:
                    stream.write(b"\n".join(data[index:index + 60] for index in range(0, end, 60)) + b"\n")
                pending = data[end:]
            if pending:
                stream.write(pending + b"\n")
            fai.append([name, length, offset, min(60, length), min(60, length) + 1])
    # Source N intervals use the same bounded index as reconstruction, avoiding
    # unbounded chromosome/read dictionaries in the delivery serializer.
    Path(str(path) + ".fai").write_text("".join("\t".join(map(str, row)) + "\n" for row in fai), encoding="utf-8")
    return fai
