"""Content-bound evidence for the reviewed ARM-to-x86 native-tool transition.

This module does not migrate a checkpoint or admit any PAF. Callers must still
verify completed commands, full inputs, index membership, outputs and policy.
Historical binary identity and the executable for future work are never merged.
No environment variable or workspace receipt can extend the reviewed inventory.
"""
from __future__ import annotations

from pathlib import Path
import struct
import subprocess

import windowed_alignment as wa

VERSION = "2.31-r1302"
_ARM_SHA = "03f361d0b8dba343adb6067fbdc109719196ef0e2619ba02c5295826dcec56dc"
_X86_SHA = "cb7e8f228d516fe4632a2250d09d1635ddd7aa95588c9fd5442d1dbe6e9a20a3"
# Observed --version and SHA on the corresponding native architecture. This
# deliberately does not admit other builds merely reporting the same version.
_REVIEWED = {_ARM_SHA: (183, "aarch64"), _X86_SHA: (62, "x86_64")}
_PAIRS = frozenset({(_ARM_SHA, _X86_SHA)})


def _descriptor(tool):
    if not isinstance(tool, dict):
        raise wa.ExperimentError("tool transition requires a source descriptor")
    source = tool.get("path", tool.get("source"))
    digest = tool.get("sha256")
    if not isinstance(source, str) or not source or not isinstance(digest, str) or digest not in _REVIEWED:
        raise wa.ExperimentError("tool binary is not in the reviewed transition inventory")
    path = Path(source)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise wa.ExperimentError("tool transition requires an absolute regular binary")
    if tool.get("source", source) != source:
        raise wa.ExperimentError("tool path and historical source disagree")
    before = wa.fingerprint(path)
    if wa.verified_sha256(path) != digest:
        raise wa.ExperimentError("reviewed tool binary content changed")
    with path.open("rb") as stream:
        header = stream.read(20)
    machine, architecture = _REVIEWED[digest]
    if (len(header) != 20 or header[:7] != b"\x7fELF\x02\x01\x01"
            or struct.unpack("<H", header[18:20])[0] != machine):
        raise wa.ExperimentError("reviewed tool ELF architecture differs")
    if wa.fingerprint(path) != before:
        raise wa.ExperimentError("tool changed while validating transition evidence")
    return {"path": str(path), "sha256": digest, "architecture": architecture, "version": VERSION}


def historical_version(tool):
    """Verify a reviewed artifact without trying to execute a foreign binary.

    Only use this for auditing already completed receipts. This is NOT permission
    to launch it, trust cached PAF bytes, or skip the receipt's command checks.
    """
    return _descriptor(tool)["version"]


def transition_record(origin, execution):
    """Prove the exact allowed binary pair and actually probe the new executable."""
    old = _descriptor(origin)
    new = _descriptor(execution)
    if (old["sha256"], new["sha256"]) not in _PAIRS:
        raise wa.ExperimentError("unreviewed execution-tool transition")
    try:
        version = subprocess.check_output([new["path"], "--version"], text=True, timeout=5).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise wa.ExperimentError("new execution tool cannot report its version") from exc
    if version != VERSION:
        raise wa.ExperimentError("new execution tool version differs")
    if _descriptor(origin) != old or _descriptor(execution) != new:
        raise wa.ExperimentError("tool transition source changed during version probe")
    return {"schema": 1, "kind": "reviewed-ordinary-execution-tool-transition",
            "origin": old, "execution": new,
            "completed_payload_revalidation_required": True,
            "historical_commands_rewritten": False}


def verify_transition(record):
    """Receipts never authorize new binary pairs or seed content hashes."""
    if (not isinstance(record, dict) or type(record.get("schema")) is not int
            or record.get("completed_payload_revalidation_required") is not True
            or record.get("historical_commands_rewritten") is not False):
        raise wa.ExperimentError("invalid tool transition receipt")
    checked = transition_record(record.get("origin"), record.get("execution"))
    if checked != record:
        raise wa.ExperimentError("tool transition receipt differs from actual binaries")
    return checked


def checked_version(tool, *, historical=False):
    """Keep ordinary version checks; only reviewed historical artifacts avoid exec."""
    if historical and tool.get("sha256") in _REVIEWED:
        return historical_version(tool)
    return subprocess.check_output([tool["path"], "--version"], text=True, timeout=5).strip()
