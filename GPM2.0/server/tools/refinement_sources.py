"""Content-bound, indexed source catalog shared by refinement adapters/publication."""
from __future__ import annotations

import csv
from pathlib import Path

try:
    from post_lgz_degap import IndexedFasta, digest, stat_key
    from workspace_layout import workspace_join
    from refinement_path import PathError, identity
except ModuleNotFoundError:
    from .post_lgz_degap import IndexedFasta, digest, stat_key
    from .workspace_layout import workspace_join
    from .refinement_path import PathError, identity


class FastaCatalog:
    def __init__(self, root: Path, index_directory: Path):
        self.root = root.absolute()
        self.index_directory = index_directory
        self.index_directory.mkdir(parents=True, exist_ok=False)
        self.sources = {}
        self.files = {}

    def register(self, dataset: str, contig: str, path: Path, *, origin: str) -> None:
        key = (dataset, contig)
        path = path.absolute()
        if key in self.sources:
            raise PathError(f"duplicate source registration: {dataset}:{contig}")
        resolved = path.resolve(strict=True)
        if resolved not in self.files:
            before = stat_key(resolved)
            sha256 = digest(resolved)
            index = IndexedFasta(resolved, self.index_directory / (identity(str(resolved)) + ".fa"))
            if stat_key(resolved) != before:
                raise PathError("source changed while being registered")
            self.files[resolved] = {"index": index, "sha256": sha256, "identity": before}
        info = self.files[resolved]
        if contig not in info["index"].records:
            raise PathError(f"missing source sequence: {dataset}:{contig}")
        self.sources[key] = {"path": path, "resolved": resolved, "origin": origin}

    def load_workspace(self) -> None:
        with workspace_join(self.root, "metadata/source_seq_locator.tsv").open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream, delimiter="\t"):
                self.register(row["dataset_name"], row["seq_name"], workspace_join(self.root, row["fasta_relpath"]), origin="lgz")
        if not self.sources:
            raise PathError("workspace has no source sequences")

    def index(self, dataset, contig):
        try:
            return self.files[self.sources[dataset, contig]["resolved"]]["index"]
        except KeyError as exc:
            raise PathError(f"unregistered source: {dataset}:{contig}") from exc

    def length(self, dataset, contig):
        return self.index(dataset, contig).records[contig][0]

    def fetch(self, dataset, contig, start, end):
        return self.index(dataset, contig).fetch(contig, start, end)

    def verify_unchanged(self):
        for path, info in self.files.items():
            if stat_key(path) != info["identity"]:
                raise PathError(f"registered source changed: {path}")
        for source in self.sources.values():
            if source["path"].resolve(strict=True) != source["resolved"]:
                raise PathError(f"source locator changed: {source['path']}")

    def manifest_rows(self, final_path):
        used = set()
        for chromosome in final_path["chromosomes"]:
            for segment in chromosome["segments"]:
                source = segment.get("source") if segment["kind"] != "gap" else segment.get("refinement_source")
                if source:
                    used.add((source["dataset"], source["contig"]))
        return self.source_rows(used)

    def source_rows(self, used):
        rows = []
        for dataset, contig in sorted(used):
            source = self.sources[dataset, contig]
            try:
                location = source["path"].relative_to(self.root).as_posix()
                scope = "workspace"
            except ValueError:
                location, scope = str(source["path"]), "external"
            rows.append({"dataset": dataset, "contig": contig, "length": self.length(dataset, contig),
                         "fasta_path": location, "path_scope": scope, "origin": source["origin"],
                         "fasta_sha256": self.files[source["resolved"]]["sha256"]})
        return rows

    def baseline_bindings(self):
        used = [key for key, row in self.sources.items() if row["origin"] == "lgz"]
        unique = {}
        for row in self.source_rows(used):
            key = row["path_scope"], row["fasta_path"]
            unique[key] = {name: row[name] for name in ("path_scope", "fasta_path", "fasta_sha256")}
        return [unique[key] for key in sorted(unique)]
