"""Versioned physical paths for Server workspaces.

Unmarked workspaces retain their legacy layout. New layout manifests are strict:
unknown or interrupted layouts must never be interpreted as an empty old project.
This module resolves paths; it does not migrate user data or create compatibility
symlinks. Immutable legacy receipts may retain logical paths and use this resolver.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import tempfile
from pathlib import Path, PurePosixPath
import re

LAYOUT_SCHEMA = "cgat.workspace"
LAYOUT_VERSION = 2
MANIFEST = ".runtime/workspace.json"
MIGRATION = ".runtime/migration.json"
TOOL_DIRECTORIES = {
    "degap": "01_degap",
    "tgsgapcloser": "02_tgsgapcloser",
    "quartet": "03_quartet",
    "lrgapcloser": "04_lrgapcloser",
}
STAGE_DIRECTORIES = (
    "01_inputs", "02_alignments", "03_lgz", "04_refinement",
    "05_final", "06_report", "07_delivery", ".runtime",
)
# Longest prefixes take precedence. Persisted LGZ proof names (grt, q4) remain
# readable; changing these scientific identities is not a filesystem migration.
_PREFIXES = {
    "data/reference": "01_inputs/01_reference",
    "data/datasets": "01_inputs/02_assemblies",
    "data/reads": "01_inputs/03_reads",
    "data/degap": "04_refinement/01_degap/04_accepted",
    "data": "01_inputs/04_derived",
    "runs": "02_alignments",
    "grt/evidence": "03_lgz/05_evidence",
    "grt/donors": "03_lgz/01_q0/donors",
    "grt/qc": "03_lgz/01_q0/qc",
    "grt/checkpoints": ".runtime/checkpoints/lgz",
    "grt/cache": ".runtime/cache/lgz",
    "grt/failed": ".runtime/history/lgz_failed",
    "grt/q": "03_lgz/04_step3",
    "grt": "03_lgz",
    "degap": "04_refinement/01_degap/03_native",
    "report": "06_report",
    ".report_history": ".runtime/history/reports",
    "metadata": ".runtime/metadata",
    "logs": ".runtime/logs",
    ".run_all": ".runtime/run_all",
    ".prepare_lib": ".runtime/prepared",
    "tel": "03_lgz/06_annotations/tel",
    "cen": "03_lgz/06_annotations/cen",
}
_ROOT_COMMANDS = {
    "prepare_q0_evidence.sh", "prepare_lgz_inputs.sh", "prepare_grt_inputs.sh",
    "run_lgz_step1.sh", "run_lgz_step2.sh", "run_lgz_step3.sh",
    "run_grt_step1.sh", "run_grt_step2.sh", "run_grt_step3.sh",
    "run_grt_step12.sh", "run_grt_step23.sh", "run_post_lgz_degap.sh",
    "package_full_zip.sh", "package_light_zip.sh", "export_final_path_fasta.sh",
    "finalize_evidence.sh", "finalize_lgz_evidence.sh", "finalize_grt_evidence.sh",
    "assign_chr_groups.sh",
}


class LayoutError(ValueError):
    pass


def relative_path(value: str | PurePosixPath) -> str:
    text = str(value)
    if (not text or text.startswith("/") or "\\" in text or re.match(r"^[A-Za-z]:", text)
            or any(ord(c) < 32 or ord(c) == 127 for c in text)):
        raise LayoutError(f"invalid workspace relative path: {text!r}")
    parts = text.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise LayoutError(f"invalid workspace relative path: {text!r}")
    return text


def canonical_relative(value: str | PurePosixPath) -> str:
    """Translate one full logical artifact path; idempotent on canonical paths."""
    text = relative_path(value)
    # q0..q4 sidecars follow their sequence, including .fai, .sha256 and .tmp.
    match = re.match(r"grt/q/\.?q([0-4])(?=[._/]|$)", text)
    if match:
        stage = {"0": "01_q0", "1": "02_step1", "2": "03_step2",
                 "3": "04_step3", "4": "04_step3"}[match[1]]
        return "03_lgz/" + stage + "/" + text.removeprefix("grt/q/")
    if text in _ROOT_COMMANDS:
        return ".runtime/commands/" + text
    for source in sorted(_PREFIXES, key=len, reverse=True):
        if text == source or text.startswith(source + "/"):
            return _PREFIXES[source] + text[len(source):]
    return text


def _read_object(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise LayoutError(f"workspace manifest must be a regular file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise LayoutError(f"invalid workspace manifest: {path}") from exc
    if not isinstance(value, dict):
        raise LayoutError(f"invalid workspace manifest object: {path}")
    return value


@dataclass(frozen=True)
class WorkspaceLayout:
    root: Path
    version: int

    def __post_init__(self):
        object.__setattr__(self, "root", Path(self.root).resolve())
        if type(self.version) is not int or self.version not in {1, LAYOUT_VERSION}:
            raise LayoutError(f"unsupported workspace layout: {self.version!r}")

    @classmethod
    def detect(cls, root: Path) -> "WorkspaceLayout":
        root = Path(root).resolve()
        private = root / ".runtime"
        if private.is_symlink():
            raise LayoutError("workspace .runtime must not be a symlink")
        # A migration owner survives process interruption. Ordinary execution
        # cannot bypass it merely because a local PID/lock has disappeared.
        transaction = root / MIGRATION
        migration = None
        if transaction.exists() or transaction.is_symlink():
            migration = _read_object(transaction)
            if (migration.get("schema") != "cgat.workspace-migration"
                    or type(migration.get("from_version")) is not int or migration.get("from_version") != 1
                    or type(migration.get("to_version")) is not int or migration.get("to_version") != LAYOUT_VERSION
                    or not isinstance(migration.get("id"), str)
                    or re.fullmatch(r"[0-9a-f]{32}", migration["id"]) is None):
                raise LayoutError("invalid workspace migration manifest")
            if migration.get("state") not in {"committed", "rolled_back"}:
                raise LayoutError("workspace migration is incomplete; resume or roll back migration first")
        path = root / MANIFEST
        if not path.exists() and not path.is_symlink():
            if migration and migration["state"] == "committed":
                raise LayoutError("committed migration is missing its layout manifest")
            return cls(root, 1)
        value = _read_object(path)
        if migration and (migration["state"] == "rolled_back" or value.get("migration_id") != migration["id"]):
            raise LayoutError("layout manifest disagrees with migration receipt")
        if (value.get("schema") != LAYOUT_SCHEMA
                or type(value.get("layout_version")) is not int
                or value.get("layout_version") != LAYOUT_VERSION
                or value.get("state") != "ready"):
            raise LayoutError("unsupported or incomplete workspace layout manifest")
        return cls(root, LAYOUT_VERSION)

    def relative(self, logical: str | PurePosixPath) -> str:
        text = relative_path(logical)
        return canonical_relative(text) if self.version == LAYOUT_VERSION else text

    def path(self, logical: str | PurePosixPath) -> Path:
        path = self.root / self.relative(logical)
        # Never allow a directory symlink to redirect metadata/output writes.
        # The final component may be a read-only input symlink; callers decide
        # whether that particular artifact is writable.
        parent = path.parent
        while parent != self.root:
            if parent.is_symlink():
                raise LayoutError(f"workspace path traverses a symlink: {parent}")
            if parent.exists() and not parent.is_dir():
                raise LayoutError(f"workspace path parent is not a directory: {parent}")
            parent = parent.parent
        return path

    def tool_relative(self, area: str, tool: str) -> str:
        if self.version != LAYOUT_VERSION:
            raise LayoutError("tool result paths require workspace layout 2")
        if area not in {"04_refinement", "05_final", "07_delivery"}:
            raise LayoutError(f"not a tool result area: {area}")
        if tool == "lgz" and area in {"05_final", "07_delivery"}:
            directory = "00_lgz"
        else:
            try:
                directory = TOOL_DIRECTORIES[tool]
            except KeyError as exc:
                raise LayoutError(f"unknown refinement tool: {tool}") from exc
        return f"{area}/{directory}"

    def manifest(self) -> dict:
        if self.version != LAYOUT_VERSION:
            raise LayoutError("legacy workspaces do not have a layout 2 manifest")
        return {"schema": LAYOUT_SCHEMA, "layout_version": LAYOUT_VERSION, "state": "ready"}


def workspace_path(root: Path, logical: str | PurePosixPath) -> Path:
    return WorkspaceLayout.detect(root).path(logical)


def workspace_join(root: Path, *parts: str | Path) -> Path:
    """Path.joinpath with layout translation only at an identified workspace root.

    This is for existing internal code that also joins explicit external input
    paths. Validation boundaries must continue using WorkspaceLayout.path (which
    rejects absolute/traversing paths). No search of ancestor directories or
    global pathlib monkey-patching is performed.
    """
    root = Path(root)
    joined = root.joinpath(*parts)
    layout = WorkspaceLayout.detect(root)
    if layout.version == 1:
        return joined
    try:
        relative = joined.relative_to(root)
    except ValueError:
        # An explicitly absolute input can refer outside the workspace. Preserve
        # that existing caller contract; never reinterpret it as a local output.
        try:
            relative = joined.relative_to(layout.root)
        except ValueError:
            return joined
    if relative == Path("."):
        return layout.root
    return layout.path(relative.as_posix())


def initialize_workspace(root: Path) -> WorkspaceLayout:
    """Create a numbered workspace in an empty directory; never convert in place."""
    root = Path(root).resolve()
    if root.exists() and any(root.iterdir()):
        raise LayoutError("new workspace must be empty; existing workspaces require migration")
    root.mkdir(parents=True, exist_ok=True)
    layout = WorkspaceLayout(root, LAYOUT_VERSION)
    private = root / ".runtime"
    private.mkdir(mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".workspace.", dir=private)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(layout.manifest(), stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, root / MANIFEST)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return layout


def render_workspace_shell(text: str, layout: WorkspaceLayout, logical_script: str) -> str:
    """Render repository-owned shell templates, never arbitrary customer scripts.

    The template's shell variables remain variables; no unquoted user path is
    interpolated. Relocated command scripts discover the root two levels above.
    """
    if layout.version == 1:
        return text
    if layout.relative(logical_script).startswith(".runtime/commands/"):
        for variable in ("server_dir", "SCRIPT_DIR"):
            for pwd in ("pwd", "pwd -P"):
                original = variable + '="$(cd "$(dirname "${BASH_SOURCE[0]}")" && ' + pwd + ')"'
                replacement = variable + '="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && ' + pwd + ')"'
                text = text.replace(original, replacement)
    variable_root = r"(\$\{(?:server_dir|SCRIPT_DIR|GPM_FAST_WORK_ROOT|work_root)\}/)"
    # Full q-stage names and relocated commands must win over the broad grt/q
    # directory mapping. In particular q0 and q1 do not live beside q4.
    text = re.sub(
        variable_root + r"(grt/q/\.?q[0-4])(?=[._/\"'\s]|$)",
        lambda match: match[1] + canonical_relative(match[2]), text,
    )
    for command in sorted(_ROOT_COMMANDS):
        text = re.sub(
            variable_root + re.escape(command) + r"(?=[\"'\s]|$)",
            lambda match, command=command: match[1] + layout.relative(command), text,
        )
    for prefix in sorted(_PREFIXES, key=len, reverse=True):
        pattern = variable_root + re.escape(prefix) + r"(?=[/\"'\s]|$)"
        text = re.sub(pattern, lambda match: match[1] + _PREFIXES[prefix], text)
    return text


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Resolve versioned CGAT workspace paths")
    parser.add_argument("--server-dir", type=Path, required=True)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--path")
    actions.add_argument("--relative")
    actions.add_argument("--initialize", action="store_true")
    actions.add_argument("--render-shell", type=Path)
    parser.add_argument("--logical-script")
    args = parser.parse_args()
    try:
        layout = initialize_workspace(args.server_dir) if args.initialize else WorkspaceLayout.detect(args.server_dir)
        if args.path is not None:
            print(layout.path(args.path))
        elif args.relative is not None:
            print(layout.relative(args.relative))
        elif args.render_shell:
            if not args.logical_script:
                raise LayoutError("--render-shell requires --logical-script")
            args.render_shell.write_text(render_workspace_shell(args.render_shell.read_text(), layout, args.logical_script))
        else:
            print(json.dumps(layout.manifest(), sort_keys=True))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"ERROR: workspace layout: {exc}\n")


if __name__ == "__main__":
    main()
