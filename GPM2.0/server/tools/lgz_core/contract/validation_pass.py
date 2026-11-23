"""A locked run can hand off its completed contract check, not cache it across runs."""
from contextlib import contextmanager
from contextvars import ContextVar
import json
import os
from pathlib import Path

try:
    from workspace_layout import MANIFEST, MIGRATION, canonical_relative, observe_workspace_paths
except ModuleNotFoundError:
    from ...workspace_layout import MANIFEST, MIGRATION, canonical_relative, observe_workspace_paths

from .errors import fail
from .schema import DEFAULT_SCHEMA_PATH

CHANNEL_ENV = "GPM_LGZ_CONTRACT_HANDOFF"
DEFER_ENV = "GPM_LGZ_VALIDATE_IN_RUNNER"
READY = "LGZ evidence assembled: ready for runner validation"
_active = ContextVar("lgz_contract_pass", default=None)


def signature(path):
    # Include link destination and inode/ctime: same length and restored mtime
    # do not excuse replacement. A missing layout marker is itself an input.
    resolved = path.resolve()
    try:
        st = resolved.stat()
    except FileNotFoundError:
        return [str(resolved), None]
    return [str(resolved), st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


class ValidationPass:
    def __init__(self, root):
        self.root = root
        self.paths = {}
        self.inputs = {}

    def observe(self, path):
        if path not in self.inputs:
            self.inputs[path] = signature(path)

    @contextmanager
    def checking(self):
        self.observe(self.root / MANIFEST)
        self.observe(self.root / MIGRATION)
        token = _active.set(self)
        try:
            with observe_workspace_paths(self.root, self.observe):
                yield
            if any(signature(p) != stamp for p, stamp in self.inputs.items()):
                fail("INPUT_CHANGED", "contract input changed during validation")
        finally:
            _active.reset(token)


def active_pass(root):
    check = _active.get()
    return check if check is not None and check.root == root else None


def refinement_channel():
    path = os.environ.get(CHANNEL_ENV)
    if path and os.environ.get("GPM_REPORT_UNIT_ID") == "refinement" and os.environ.get("GPM_REPORT_RUN_ID"):
        return Path(path)
    return None


def write_handoff(channel, root, run_id, inputs, summary_path):
    # The runner owns an initially empty private temporary directory outside
    # the bundle. Only the runner writes here, after it has verified the bundle.
    if channel is None or not inputs:
        return
    files = {**inputs["files"], str(summary_path.relative_to(root)): signature(summary_path)}
    with channel.open("x", encoding="utf-8") as stream:
        json.dump({"version": 1, "root": str(root), "run": run_id, "count": len(files),
                   "schema": inputs["schema"], "files": files}, stream, separators=(",", ":"))


def can_reuse_validation(channel, root, run_id):
    """Fall back to full validation unless this same locked run still matches."""
    if not channel or not run_id:
        return False
    try:
        data = json.loads(Path(channel).read_text(encoding="utf-8"))
        if (data["version"] != 1 or data["root"] != str(root) or data["run"] != run_id
                or data["schema"] != signature(DEFAULT_SCHEMA_PATH)):
            return False
        files = data["files"]
        required = {MANIFEST, MIGRATION, canonical_relative("metadata/grt_contract_summary.json"),
                    canonical_relative("metadata/package.tsv"), canonical_relative("metadata/grt_final_path.json")}
        if not isinstance(files, dict) or data["count"] != len(files) or not required.issubset(files):
            return False
        for name, expected in files.items():
            p = Path(name)
            if p.is_absolute() or ".." in p.parts or signature(root / p) != expected:
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        return False
