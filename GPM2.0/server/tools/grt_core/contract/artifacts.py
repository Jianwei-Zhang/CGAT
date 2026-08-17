import hashlib
from pathlib import Path

from .errors import *
from .schema import *
from .tables import *
def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()

def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def validate_sha256(value, label):
    if not SHA256_RE.fullmatch(value or ""):
        fail("INVALID_VALUE", f"{label} must be a lowercase SHA-256")

def read_fasta(path, label, allow_empty=False):
    records = {}
    current_name = None
    chunks = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith(">"):
                    if current_name is not None:
                        records[current_name] = "".join(chunks).upper()
                    current_name = stripped[1:].split()[0]
                    if not current_name or current_name in records:
                        fail("INVALID_FASTA", f"{label}:{line_number} has an empty or duplicate record")
                    chunks = []
                else:
                    if current_name is None:
                        fail("INVALID_FASTA", f"{label}:{line_number} has sequence before header")
                    sequence = "".join(stripped.split()).upper()
                    if not re.fullmatch(r"[ACGTRYSWKMBDHVN]+", sequence):
                        fail("INVALID_FASTA", f"{label}:{line_number} has unsupported bases")
                    chunks.append(sequence)
    except UnicodeDecodeError as exc:
        fail("INVALID_FASTA", f"{label} is not UTF-8: {exc}")
    if current_name is not None:
        records[current_name] = "".join(chunks).upper()
    if not records and allow_empty:
        return records
    if not records or any(not sequence for sequence in records.values()):
        fail("INVALID_FASTA", f"{label} has no non-empty records")
    return records

def validate_artifact(bundle_root, relpath, expected_sha, label):
    validate_sha256(expected_sha, f"{label}.sha256")
    path = bundle_path(bundle_root, relpath, label)
    actual = sha256_file(path)
    if actual != expected_sha:
        fail("CHECKSUM_MISMATCH", f"{label} expected {expected_sha}, got {actual}")
    return path
