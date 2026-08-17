#!/usr/bin/env python3

"""Render an allowlisted shell template with shell-escaped values."""

from __future__ import annotations

import argparse
import os
import re
import shlex
from pathlib import Path


PLACEHOLDER_RE = re.compile(r"__([A-Z][A-Z0-9_]*)__")


def render_shell_template(
    template_path: Path,
    output_path: Path,
    allowed_names: list[str],
    values: list[tuple[str, str]],
) -> None:
    allowed = set(allowed_names)
    if len(allowed) != len(allowed_names):
        raise ValueError("template allowlist contains duplicate names")

    variables: dict[str, str] = {}
    for name, value in values:
        if name in variables:
            raise ValueError(f"template value provided more than once: {name}")
        variables[name] = value

    source_bytes = template_path.read_bytes()
    if b"\r" in source_bytes:
        raise ValueError(f"template must use LF line endings: {template_path}")
    source = source_bytes.decode("utf-8")
    placeholders = set(PLACEHOLDER_RE.findall(source))
    if placeholders != allowed:
        missing = sorted(allowed - placeholders)
        unexpected = sorted(placeholders - allowed)
        raise ValueError(
            f"template placeholder mismatch; missing={missing}, unexpected={unexpected}"
        )
    if set(variables) != allowed:
        missing = sorted(allowed - set(variables))
        unexpected = sorted(set(variables) - allowed)
        raise ValueError(
            f"template value mismatch; missing={missing}, unexpected={unexpected}"
        )

    rendered = PLACEHOLDER_RE.sub(
        lambda match: shlex.quote(variables[match.group(1)]),
        source,
    )
    if PLACEHOLDER_RE.search(rendered):
        raise ValueError("unresolved template placeholder remains after rendering")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.tmp.{os.getpid()}")
    temporary.write_text(rendered, encoding="utf-8", newline="")
    os.replace(temporary, output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow", action="append", default=[])
    parser.add_argument(
        "--shell-var",
        action="append",
        nargs=2,
        metavar=("NAME", "VALUE"),
        default=[],
    )
    args = parser.parse_args()
    try:
        render_shell_template(
            args.template,
            args.output,
            args.allow,
            [(name, value) for name, value in args.shell_var],
        )
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
