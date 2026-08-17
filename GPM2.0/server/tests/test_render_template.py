import subprocess
import tempfile
import unittest
from pathlib import Path

from server.tools.render_template import render_shell_template


class RenderTemplateTests(unittest.TestCase):
    def test_shell_quotes_allowlisted_values_and_preserves_lf(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            template = root / "script.sh"
            output = root / "generated.sh"
            template.write_text(
                '#!/usr/bin/env bash\nvalue=__VALUE__\nprintf \'%s\' "$value"\n',
                encoding="utf-8",
                newline="",
            )
            value = "space ' quote $(must-not-run)"

            render_shell_template(template, output, ["VALUE"], [("VALUE", value)])

            self.assertNotIn(b"\r", output.read_bytes())
            completed = subprocess.run(
                ["bash", str(output)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.stdout, value)

    def test_rejects_missing_and_unexpected_placeholders(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            template = root / "script.sh"
            output = root / "generated.sh"
            template.write_text("value=__VALUE__\n", encoding="utf-8", newline="")

            with self.assertRaisesRegex(ValueError, "placeholder mismatch"):
                render_shell_template(
                    template,
                    output,
                    ["VALUE", "MISSING"],
                    [("VALUE", "ok"), ("MISSING", "missing")],
                )
            with self.assertRaisesRegex(ValueError, "value mismatch"):
                render_shell_template(template, output, ["VALUE"], [])

    def test_rejects_crlf_template(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            template = root / "script.sh"
            output = root / "generated.sh"
            template.write_bytes(b"value=__VALUE__\r\n")

            with self.assertRaisesRegex(ValueError, "LF line endings"):
                render_shell_template(template, output, ["VALUE"], [("VALUE", "ok")])


if __name__ == "__main__":
    unittest.main()
