import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "work" / "e2e_adversarial.py"


class AdversarialRunnerTest(unittest.TestCase):
    def _run(self, *arguments):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "backend")
        return subprocess.run(
            [sys.executable, str(RUNNER), *arguments],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

    def test_default_suite_prints_pass_and_returns_zero(self):
        result = self._run()

        self.assertEqual(
            result.returncode,
            0,
            msg=result.stdout + result.stderr,
        )
        self.assertIn("ADVERSARIAL PASS", result.stdout)

    def test_load_failure_prints_fail_and_returns_nonzero(self):
        result = self._run(
            "--module",
            "backend.tests.module_that_does_not_exist",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ADVERSARIAL FAIL", result.stdout)


if __name__ == "__main__":
    unittest.main()
