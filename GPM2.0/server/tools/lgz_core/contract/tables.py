import csv
import json
from pathlib import Path, PurePosixPath

from .errors import *
def safe_relative_path(value, label):
    if not value:
        fail("INVALID_PATH", f"{label} is empty")
    if "\\" in value:
        fail("INVALID_PATH", f"{label} contains a backslash")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        fail("INVALID_PATH", f"{label} is not a safe relative path: {value}")
    return path

def bundle_path(bundle_root, relpath, label, required=True):
    relative = safe_relative_path(relpath, label)
    path = bundle_root.joinpath(*relative.parts)
    if required and (not path.exists() or not path.is_file()):
        fail("MISSING_REQUIRED_FILE", f"{label} does not exist: {relpath}")
    try:
        path.resolve().relative_to(bundle_root.resolve())
    except ValueError:
        fail("INVALID_PATH", f"{label} escapes bundle root: {relpath}")
    return path

def read_tsv(bundle_root, relpath, table_spec):
    path = bundle_path(bundle_root, relpath, relpath)
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            header = list(reader.fieldnames or [])
            expected_header = table_spec["header"]
            if header != expected_header:
                fail("INVALID_TSV", f"{relpath} header must be {expected_header}, got {header}")
            rows = list(reader)
    except UnicodeDecodeError as exc:
        fail("INVALID_TSV", f"{relpath} is not UTF-8: {exc}")
    minimum = table_spec.get("min_rows", 0)
    maximum = table_spec.get("max_rows")
    if len(rows) < minimum:
        fail("INVALID_TSV", f"{relpath} requires at least {minimum} data rows")
    if maximum is not None and len(rows) > maximum:
        fail("INVALID_TSV", f"{relpath} allows at most {maximum} data rows")
    return rows

def read_json_file(bundle_root, relpath):
    path = bundle_path(bundle_root, relpath, relpath)
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail("INVALID_JSON", f"{relpath}: {exc}")

def read_jsonl(bundle_root, relpath):
    path = bundle_path(bundle_root, relpath, relpath)
    rows = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    fail("INVALID_JSON", f"{relpath}:{line_number}: {exc}")
                if not isinstance(value, dict):
                    fail("INVALID_JSON", f"{relpath}:{line_number} must contain an object")
                rows.append(value)
    except UnicodeDecodeError as exc:
        fail("INVALID_JSON", f"{relpath} is not UTF-8: {exc}")
    return rows

def unique_index(rows, key, relpath):
    result = {}
    for row_number, row in enumerate(rows, start=2):
        value = (row.get(key) or "").strip()
        if not value:
            fail("INVALID_VALUE", f"{relpath}:{row_number} has empty {key}")
        if value in result:
            fail("DUPLICATE_ID", f"{relpath} duplicates {key}={value}")
        result[value] = row
    return result
