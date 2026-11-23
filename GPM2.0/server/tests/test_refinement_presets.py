"""Workspace-local parameter alignment, validation and native recipe evidence."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import refinement_presets as presets
from refinement_recipes import make_invocation
from refinement_tools import fingerprint, load_lock
from test_refinement_native import workspace


class RefinementPresetTests(unittest.TestCase):
    def test_default_arguments_explicit_and_other_tool_recipe_unchanged(self):
        lock = load_lock()
        runtime = {'lock_sha256': fingerprint(lock)}
        reads = {'hifi': ['/reads/one.fq.gz'], 'ont': []}
        args = [Path('/base.fa'), reads, Path('/run/native'), 2]
        degap = make_invocation('degap', *args, runtime=runtime, lock=lock)
        self.assertEqual(degap.recipe['extension_parameters'], {'max_extension_rounds': 10, 'max_extension_bp': 500000, 'kmer_filter': True})
        self.assertIn('--kmer_filter', degap.command)
        for option, expected in (('--MaximumExtensionRound', '10'), ('--MaximumExtensionLength', '500000')):
            self.assertEqual(degap.command[degap.command.index(option) + 1], expected)
        tgs = make_invocation('tgsgapcloser', *args, runtime=runtime, lock=lock)
        self.assertNotIn('extension_parameters', tgs.recipe)

    def test_sync_and_offline_fallback_preserve_comments_and_installed_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root, installed = base/'workspace', base/'installed'
            workspace(root)
            layout = presets.WorkspaceLayout.detect(root)
            binding = layout.path('.prepare_lib/server-tools.path')
            binding.parent.mkdir(parents=True, exist_ok=True)
            binding.write_text(str(installed)+'\n')
            copy = presets.workspace_file(layout)
            copy.parent.mkdir(parents=True, exist_ok=True)
            (installed/'tools').mkdir(parents=True)
            launcher = installed/'run.sh'
            launcher.touch()
            config = installed/'tools/gapfill.toml'
            content = b'# local\n[degap]\nmax_extension_rounds = "unlimited"\nkmer_filter = false\n'
            config.write_bytes(content)
            expected = {'max_extension_rounds': 'unlimited', 'max_extension_bp': 500000, 'kmer_filter': False}
            self.assertEqual(presets.sync_workspace(root), expected)
            self.assertEqual(presets.effective(root), expected)
            self.assertEqual(config.read_bytes(), content)
            self.assertEqual(copy.read_bytes(), content)
            launcher.unlink()
            self.assertEqual(presets.sync_workspace(root), expected)
            launcher.touch()
            config.unlink()
            self.assertEqual(presets.sync_workspace(root), presets.defaults())

    def test_unknown_invalid_and_symlink_are_not_silent_fallbacks(self):
        for raw in (b'[degap]\nmax_extension_rounds = 0', b'[degap]\nmax_extension_bp = false',
                    b'[degap]\nkmer_filter = "false"', b'[degap]\ncommand = "x"', b'[other]\nn = 1'):
            with self.subTest(config=raw), self.assertRaisesRegex(ValueError, 'gapfill.toml'):
                presets.parse(raw, Path('gapfill.toml'))
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp)/'gapfill.toml'
            link.symlink_to(Path(tmp)/'missing')
            with self.assertRaisesRegex(ValueError, 'regular'):
                presets.regular_bytes(link)
