"""Real process exits and resource accounting, separate from synthetic native outputs."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import refinement_native_checkpoint as checkpoint


class NativeProcessTests(unittest.TestCase):
    def test_real_producer_exit_and_peak_memory(self):
        for code in (0, 7):
            with self.subTest(code=code):
                status, rss = checkpoint._run_native(
                    [sys.executable, "-c", f"import sys; data=bytearray(8*1024*1024); sys.exit({code})"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                self.assertEqual(status, code)
                if hasattr(os, "wait4"):
                    self.assertIsNotNone(rss)
                    self.assertGreater(rss, 0)

    @unittest.skipUnless(hasattr(os, "wait4"), "POSIX child accounting")
    def test_signal_exit_keeps_negative_return_code(self):
        status, _ = checkpoint._run_native(
            [sys.executable, "-c", "import os,signal; os.kill(os.getpid(), signal.SIGTERM)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.assertEqual(status, -signal.SIGTERM)

    @unittest.skipUnless(hasattr(os, "wait4"), "POSIX child accounting")
    def test_interruption_kills_and_reaps_the_producer(self):
        process = mock.MagicMock()
        child = process.__enter__.return_value
        with mock.patch.object(checkpoint.subprocess, "Popen", return_value=process), \
             mock.patch.object(checkpoint.os, "wait4", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                checkpoint._run_native(["controlled-producer"])
        child.kill.assert_called_once_with()
        child.wait.assert_called_once_with()
