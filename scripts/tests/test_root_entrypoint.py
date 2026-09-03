from pathlib import Path
import subprocess
import sys
import unittest


ROOT_DIR = Path(__file__).resolve().parents[2]


class RootEntrypointTests(unittest.TestCase):
    def test_root_analysis_entrypoint_exposes_cli(self):
        result = subprocess.run(
            [sys.executable, str(ROOT_DIR / "analyze.py"), "--help"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Build the Royal Road raw timelines", result.stdout)


if __name__ == "__main__":
    unittest.main()
