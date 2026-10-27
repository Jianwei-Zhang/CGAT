#!/usr/bin/env python3
"""Tests for the release guide version check."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("check_release_guides.py")
SPEC = importlib.util.spec_from_file_location("check_release_guides", SCRIPT)
check = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = check
SPEC.loader.exec_module(check)


def landing_page(version: str, badge: str | None = None) -> str:
    return "\n".join(
        [
            f"[![GitHub Releases](https://img.shields.io/badge/Releases-v{badge or version}-2563eb)]"
            "(https://github.com/Jianwei-Zhang/CGAT/releases)",
            "",
            f"  archive=GPM_Server_{version}_source.tar.gz",
            f'    "https://riceome.hzau.edu.cn/cgat/downloads/v{version}/$archive" ||',
            f'      "https://github.com/Jianwei-Zhang/CGAT/releases/download/v{version}/$archive"',
        ]
    )


def install_guide(version: str) -> str:
    return "\n".join(
        [
            f"Download from [Release v{version}](https://github.com/Jianwei-Zhang/CGAT/releases/tag/v{version}).",
            f"  archive=GPM_Server_{version}_source.tar.gz",
            f'    "https://riceome.hzau.edu.cn/cgat/downloads/v{version}/$archive" ||',
            f'      "https://github.com/Jianwei-Zhang/CGAT/releases/download/v{version}/$archive"',
        ]
    )


class GuideTree:
    """Write a minimal checkout containing every guide the check inspects."""

    def __init__(self, version: str = "1.2.3") -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.write(version)

    def write(self, version: str = "1.2.3") -> None:
        pages = {
            "README.md": landing_page(version),
            "README_zh.md": landing_page(version),
            "GPM2.0/README.md": install_guide(version),
            "GPM2.0/README_zh.md": install_guide(version),
            "GPM2.0/server/README.md": install_guide(version),
            "GPM2.0/server/README_zh.md": install_guide(version),
        }
        for relative, content in pages.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content + "\n", encoding="utf-8")

    def close(self) -> None:
        self.tmp.cleanup()


class ReleaseGuideCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tree = GuideTree()
        self.addCleanup(self.tree.close)

    def test_consistent_guides_pass(self) -> None:
        version, report = check.collect(self.tree.root)
        self.assertEqual("1.2.3", version)
        self.assertTrue(any(line.startswith("README.md: release badge") for line in report))

    def test_stale_landing_page_archive_is_reported(self) -> None:
        (self.tree.root / "README.md").write_text(landing_page("1.2.2"), encoding="utf-8")
        with self.assertRaises(ValueError) as raised:
            check.collect(self.tree.root)
        self.assertIn("README.md", str(raised.exception))
        self.assertIn("v1.2.2", str(raised.exception))

    def test_stale_badge_is_reported(self) -> None:
        (self.tree.root / "README_zh.md").write_text(
            landing_page("1.2.3", badge="1.2.0"), encoding="utf-8"
        )
        with self.assertRaises(ValueError) as raised:
            check.collect(self.tree.root)
        self.assertIn("release badge shows v1.2.0", str(raised.exception))

    def test_missing_badge_is_reported(self) -> None:
        (self.tree.root / "README.md").write_text(
            install_guide("1.2.3"), encoding="utf-8"
        )
        with self.assertRaises(ValueError) as raised:
            check.collect(self.tree.root)
        self.assertIn("release badge is missing", str(raised.exception))

    def test_missing_archive_reference_is_reported(self) -> None:
        (self.tree.root / "GPM2.0/server/README_zh.md").write_text(
            "See the downloads page.\n", encoding="utf-8"
        )
        with self.assertRaises(ValueError) as raised:
            check.collect(self.tree.root)
        self.assertIn("GPM2.0/server/README_zh.md", str(raised.exception))

    def test_conflicting_versions_in_one_guide_are_reported(self) -> None:
        (self.tree.root / "GPM2.0/README.md").write_text(
            install_guide("1.2.3") + "\nFallback: v1.2.2\n" + landing_page("1.2.2"),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as raised:
            check.collect(self.tree.root)
        self.assertIn("conflicting", str(raised.exception))

    def test_main_rejects_mismatched_release_version(self) -> None:
        self.assertEqual(0, check.main(["--root", str(self.tree.root), "--version", "v1.2.3"]))
        self.assertEqual(1, check.main(["--root", str(self.tree.root), "--version", "v1.2.4"]))
        self.assertEqual(2, check.main(["--root", str(self.tree.root), "--version", "latest"]))


class VersionNormalizationTest(unittest.TestCase):
    def test_accepts_prefixed_and_bare_versions(self) -> None:
        self.assertEqual("2.0.15", check.normalize_version("v2.0.15"))
        self.assertEqual("2.0.15", check.normalize_version("2.0.15"))

    def test_rejects_other_shapes(self) -> None:
        for value in ("", "v2.0", "2.0.15-beta", "latest"):
            with self.assertRaises(ValueError):
                check.normalize_version(value)


if __name__ == "__main__":
    unittest.main()
