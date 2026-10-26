#!/usr/bin/env python3
"""Offline regression checks for the canonical release-note archive."""
import copy
import importlib.util
import json
import re
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / "GPM2.0/releases"
spec = importlib.util.spec_from_file_location("release_docs", HERE / "render-release-docs.py")
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


class ReleaseDocsTests(unittest.TestCase):
    def setUp(self):
        self.releases = archive.collect_releases(SOURCE)

    def test_archive_contains_initial_versions_newest_first(self):
        versions = [r["version"] for r in self.releases]
        self.assertTrue({"v2.0.12", "v2.0.11", "v2.0.10"}.issubset(versions))
        self.assertEqual(versions, sorted(versions, key=lambda v: tuple(map(int, v[1:].split("."))), reverse=True))
        self.assertEqual(len(versions), len(set(versions)))

    def test_sort_uses_numeric_versions_not_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            for version in ("v2.0.9", "v2.0.10"):
                text = (SOURCE / "v2.0.10.md").read_text().replace("v2.0.10", version)
                (Path(tmp) / (version + ".md")).write_text(text)
            self.assertEqual(archive.collect_releases(Path(tmp))[0]["version"], "v2.0.10")

    def test_locales_are_not_interleaved(self):
        releases = copy.deepcopy(self.releases)
        for release in releases:
            release["en"] += "\nEN_ONLY"
            release["zh"] += "\nZH_ONLY"
        pages = archive.render_pages(releases)
        self.assertIn("EN_ONLY", pages["en/changelog/v2.0.12.md"])
        self.assertNotIn("ZH_ONLY", pages["en/changelog/v2.0.12.md"])
        self.assertIn("ZH_ONLY", pages["zh/changelog/v2.0.12.md"])
        self.assertNotIn("EN_ONLY", pages["zh/changelog/v2.0.12.md"])

    def test_mac_notices_match_the_canonical_guide(self):
        guide = (ROOT / "GPM2.0/RELEASING.md").read_text()
        notices = guide.split("````markdown\n", 1)[1].split("\n````", 1)[0]
        en, zh = notices.split("### macOS 首次启动\n", 1)
        def unquote(markdown):
            lines = (re.sub(r"^> ?", "", line) for line in markdown.splitlines())
            return "\n".join(line for line in lines if line.strip() and line != "[!WARNING]")

        for release in self.releases:
            self.assertIn(unquote(en), unquote(release["en"]))
            self.assertIn(unquote("### macOS 首次启动\n" + zh), unquote(release["zh"]))

    def test_github_export_uses_the_same_language_sections(self):
        release = self.releases[0]
        body = archive.release_body(release)
        self.assertEqual(body, release["en"] + "\n\n---\n\n" + release["zh"] + "\n")
        self.assertNotIn("## English", body)
        self.assertNotIn("## 中文", body)
        self.assertIn(release["en"], body)
        self.assertIn(release["zh"], body)
        self.assertNotIn("summary_en:", body)
        self.assertNotIn("release_source_sha256", body)

    def test_release_styling_is_shared_by_github_and_docs(self):
        release = next(r for r in self.releases if r["version"] == "v2.0.12")
        pages = archive.render_pages(self.releases)
        for locale in ("en", "zh"):
            content = release[locale]
            page = pages[f"{locale}/changelog/v2.0.12.md"]
            self.assertIn(content, page)
            self.assertIn("pageClass: release-notes", page)
            for alert in ("NOTE", "IMPORTANT", "WARNING"):
                self.assertEqual(content.count(f"> [!{alert}]"), 1)
            for icon in ("🟢", "🔵", "🟣"):
                self.assertIn("#### " + icon, content)
            self.assertIn(release["summary_" + locale], content)
            self.assertNotIn("<span", content)
            self.assertNotIn("style=", content)
            self.assertNotIn("::: ", content)
            self.assertIn("| Windows |", content)
            self.assertIn("| macOS |", content)
            self.assertIn("| Linux Server |", content)
            self.assertIn("`test_data.zip`", content)
            self.assertEqual(content.count("> xattr -dr com.apple.quarantine /Applications/GPM.app"), 1)
            self.assertEqual(content.count("> ```"), 2)

    def test_unpublished_drafts_are_not_archived(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            original = (SOURCE / "v2.0.12.md").read_text()
            (source / "v2.0.12.md").write_text(original)
            drafts = source / "drafts"
            drafts.mkdir()
            (drafts / "v2.0.13.md").write_text(original.replace("v2.0.12", "v2.0.13"))
            self.assertEqual([r["version"] for r in archive.collect_releases(source)], ["v2.0.12"])

    def test_new_release_drafts_use_plain_shared_markdown(self):
        guide = (ROOT / "GPM2.0/RELEASING.md").read_text()
        notices = guide.split("````markdown\n", 1)[1].split("\n````", 1)[0]
        en_notice, zh_notice = notices.split("### macOS 首次启动", 1)
        for path in (SOURCE / "drafts").glob("v*.md"):
            with self.subTest(draft=path.name):
                draft = path.read_text()
                self.assertIn("Unpublished draft", draft)
                self.assertNotRegex(draft, r"(?m)^> \[!")
                self.assertNotRegex(draft, r"(?m)^\|")
                self.assertNotRegex(draft, "[🟢🔵🟣]")
                en, zh = draft.split("\n## English\n", 1)[1].split("\n## 中文\n", 1)
                self.assertIn(en_notice.strip(), en)
                self.assertIn("### macOS 首次启动" + zh_notice.rstrip(), zh)
                release = {"version": path.stem, "published": "2026-10-26",
                           "updated": "2026-10-26", "summary_en": "Draft fixture",
                           "summary_zh": "草稿测试", "sha256": "fixture",
                           "en": en.strip(), "zh": zh.strip()}
                pages = archive.render_pages([release])
                body = archive.release_body(release)
                for locale in ("en", "zh"):
                    content = release[locale]
                    self.assertLess(content.index("### Server"), content.index("### App"))
                    self.assertIn("`test_data.zip`", content)
                    self.assertIn(content, body)
                    self.assertIn(content, pages[f"{locale}/changelog/{path.stem}.md"])

    def test_language_delimiters_are_never_exported_for_any_version(self):
        for release in self.releases:
            body = archive.release_body(release)
            self.assertTrue(body.startswith(release["en"]))
            self.assertTrue(body.endswith(release["zh"] + "\n"))
            self.assertNotRegex(body, r"(?m)^## (English|中文)$")
            for locale in ("en", "zh"):
                page = archive.render_pages([release])[f'{locale}/changelog/{release["version"]}.md']
                self.assertNotRegex(page, r"(?m)^## (English|中文)$")

    def test_generated_pages_and_registry_are_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp)
            registry = docs / ".vitepress/data/pages.json"
            registry.parent.mkdir(parents=True)
            registry.write_text("[]\n")
            self.assertEqual(archive.generate(SOURCE, docs), (len(self.releases), 2 * (len(self.releases) + 1)))
            first = registry.read_text()
            archive.generate(SOURCE, docs)
            self.assertEqual(first, registry.read_text())
            self.assertEqual(archive.generate(SOURCE, docs, check=True), (len(self.releases), 2 * (len(self.releases) + 1)))
            self.assertEqual(len(json.loads(first)), 2 * (len(self.releases) + 1))

    def test_stale_generated_page_fails_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp)
            archive.generate(SOURCE, docs)
            (docs / "en/changelog/index.md").write_text("stale")
            with self.assertRaisesRegex(ValueError, "Stale or missing generated"):
                archive.generate(SOURCE, docs, check=True)

    def test_missing_route_fails_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "pages.json"
            registry.write_text("[]\n")
            with self.assertRaisesRegex(ValueError, "registry"):
                archive.update_registry(registry, self.releases, check=True)

    def check_rejected_source(self, transform, error):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "v2.0.12.md"
            target.write_text(transform((SOURCE / "v2.0.12.md").read_text()))
            with self.assertRaisesRegex(ValueError, error):
                archive.read_release(target)

    def test_reversed_languages_fail(self):
        self.check_rejected_source(lambda s: s.replace("## English", "## TEMP").replace("## 中文", "## English").replace("## TEMP", "## 中文"), "English must precede")

    def test_missing_arm64_guidance_fails(self):
        self.check_rejected_source(lambda s: s.replace("ARM64", "other"), "macOS notice")

    def test_wrong_version_filename_fails(self):
        self.check_rejected_source(lambda s: s.replace('version: "v2.0.12"', 'version: "v2.0.99"'), "filename")

    def test_invalid_update_date_fails(self):
        self.check_rejected_source(lambda s: s.replace('updated: "2026-10-26"', 'updated: "2020-01-01"'), "precedes publication")

    def test_unshipped_app_label_changes_are_not_archived_as_released(self):
        release = next(r for r in self.releases if r["version"] == "v2.0.12")
        app = release["en"].split("### App\n", 1)[1].split("### Downloads", 1)[0]
        self.assertNotIn("Auxiliary", app)
        self.assertNotIn("Import / Open", app)
        self.assertIn("leave the App installers", release["en"])


if __name__ == "__main__":
    unittest.main()
