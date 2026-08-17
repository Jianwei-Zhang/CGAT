import json
import re
from pathlib import Path

from .errors import *

DEFAULT_SCHEMA_PATH = Path(__file__).parents[3] / "contracts" / "grt_precomputed_v2.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

TRUE_VALUES = {"true"}

FALSE_VALUES = {"false"}

def parse_bool(value, label):
    normalized = (value or "").strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    fail("INVALID_VALUE", f"{label} must be true or false")

def parse_int(value, label, minimum=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        fail("INVALID_VALUE", f"{label} must be an integer")
    if minimum is not None and parsed < minimum:
        fail("INVALID_COORDINATE" if minimum == 1 else "INVALID_VALUE", f"{label} must be >= {minimum}")
    return parsed

def parse_float(value, label, minimum=None, maximum=None):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        fail("INVALID_VALUE", f"{label} must be numeric")
    if minimum is not None and parsed < minimum:
        fail("INVALID_VALUE", f"{label} must be >= {minimum}")
    if maximum is not None and parsed > maximum:
        fail("INVALID_VALUE", f"{label} must be <= {maximum}")
    return parsed

def parse_json(value, label, expected_type=None):
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        fail("INVALID_JSON", f"{label}: {exc}")
    if expected_type is not None and not isinstance(parsed, expected_type):
        fail("INVALID_JSON", f"{label} must contain {expected_type.__name__}")
    return parsed
