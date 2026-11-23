#!/usr/bin/env python3

"""Validate a staged dataset before promotion."""

import csv
import sys
from pathlib import Path
from workspace_layout import workspace_join


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


stage_dir = Path(sys.argv[1])
dataset_name = sys.argv[2]
required_files = [
    workspace_join(stage_dir, "metadata", "datasets.tsv"),
    workspace_join(stage_dir, "metadata", "chr_assignments.tsv"),
    workspace_join(stage_dir, "metadata", "source_seq_locator.tsv"),
    workspace_join(stage_dir, "data", "datasets", f"{dataset_name}.fa"),
    workspace_join(stage_dir, "data", "datasets", f"{dataset_name}.fa.fai"),
    workspace_join(stage_dir, "runs", f"{dataset_name}_vs_ref", "result.paf"),
]
for path in required_files:
    if not path.exists():
        fail(f"staged add output is missing: {path}")

with (workspace_join(stage_dir, "metadata", "datasets.tsv")).open(newline="", encoding="utf-8") as handle:
    datasets = list(csv.DictReader(handle, delimiter="\t"))
if not any(row.get("dataset_name") == dataset_name for row in datasets):
    fail(f"staged datasets.tsv is missing dataset: {dataset_name}")

with (workspace_join(stage_dir, "metadata", "source_seq_locator.tsv")).open(newline="", encoding="utf-8") as handle:
    locators = list(csv.DictReader(handle, delimiter="\t"))
if not any(row.get("dataset_name") == dataset_name for row in locators):
    fail(f"staged source_seq_locator.tsv is missing dataset: {dataset_name}")
