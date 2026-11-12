from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


class OddsPapiProbeEntrypointTests(unittest.TestCase):
    def test_direct_entrypoint_resolves_repository_app_package(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "scripts/probe_oddspapi_safe.py", "--help"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--output", result.stdout)


if __name__ == "__main__":
    unittest.main()
