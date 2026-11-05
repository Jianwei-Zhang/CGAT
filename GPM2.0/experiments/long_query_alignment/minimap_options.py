"""Typed initial-reference tuning; no arbitrary minimap2 arguments or retries."""
from __future__ import annotations

import csv
import os
from pathlib import Path
import re

BATCH_ENV = "GPM_RUN_MINIMAP_BATCH"


def batch_size(value):
    text = str(value).upper()
    match = re.fullmatch(r"([1-9][0-9]*)([KMG]?)", text, flags=re.ASCII)
    if not match or int(match[1]) * {"": 1, "K": 1000, "M": 1000000, "G": 1000000000}[match[2]] > 2**63 - 1:
        raise ValueError("-K/--minimap-batch requires a positive base count, e.g. 1G or 500M (not a memory limit)")
    return text


def seed_fraction(value):
    text = str(value)
    if not re.fullmatch(r"0\.[0-9]+", text, flags=re.ASCII) or not 0 < float(text) < 1:
        raise ValueError("-f/--minimap-filter requires a fraction between 0 and 1, e.g. 0.01")
    return text.rstrip("0")


def seed_flags(value=None, *, mid_occ=None):
    if mid_occ is not None:
        if type(mid_occ) is not int or mid_occ < 1:
            raise ValueError("invalid inherited minimap2 occurrence threshold")
        return ["-f", str(mid_occ)]
    return [] if value is None else ["-f", seed_fraction(value)]


def native_flags(args, *, mid_occ=None):
    batch = getattr(args, "minimap_batch", None)
    return ([] if batch is None else ["-K", batch_size(batch)]) + seed_flags(
        getattr(args, "minimap_filter", None), mid_occ=mid_occ)


def command_tail(command, tool, *, fraction=None, mid_occ=None):
    """Validate the exact permitted prefix; K is execution-only, f is scientific."""
    if type(command) is not list or command[:4] != [tool, "-c", "-x", "asm10"]:
        raise ValueError("native flags/preset/tool changed")
    rest = command[4:]
    if rest[:1] == ["-K"]:
        if len(rest) < 2 or batch_size(rest[1]) != rest[1]:
            raise ValueError("invalid native batch size")
        rest = rest[2:]
    inherited = seed_flags(fraction, mid_occ=mid_occ)
    if rest[:len(inherited)] != inherited:
        raise ValueError("native minimizer filtering flags differ from the prepared policy")
    return rest[len(inherited):]


def prepared_options(root):
    path = Path(root) / "metadata/prepare_options.tsv"
    if not path.exists() and not path.is_symlink():
        return {}  # Legacy adapter fixtures/workspaces: retain original native flags.
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024**2:
        raise ValueError("invalid prepared minimap2 settings")
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    values = {row["key"]: row["value"] for row in rows}
    result = {}
    if "minimap_batch" in values:
        result["minimap_batch"] = batch_size(values["minimap_batch"])
    if values.get("minimap_filter", "default") != "default":
        result["minimap_filter"] = seed_fraction(values["minimap_filter"])
    return result


def workspace_options(root):
    options = prepared_options(root)
    if BATCH_ENV in os.environ:
        options["minimap_batch"] = batch_size(os.environ[BATCH_ENV])
    return options
