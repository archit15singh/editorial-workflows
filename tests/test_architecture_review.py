import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "architecture_review.py"
RECORD = "architecture/reviews/first.md"
REVIEW = """Trigger: Example code change.
Evidence: Reproduced a failure in the old code.
Design: Keep the rule near the code that owns it.
Decision: Apply the fix.
Verification: Passed the regression.
"""


class ArchitectureReviewTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.git("init", "-q")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.com",
                 "commit", "-qm", "base", "--allow-empty")
        self.git("branch", "baseline")

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def write(self, path, contents):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(contents, encoding="utf-8")

    def review(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), "--base", "baseline", *args],
                              cwd=self.root, capture_output=True, text=True)

    def test_editorial_only_changes_skip(self):
        self.write("WORKFLOW.md", "# Drafting")
        self.write("tests/test_sample.py", "")
        result = self.review()
        self.assertEqual(result.returncode, 0)
        self.assertIn("SKIP", result.stdout)

    def test_code_change_requires_complete_new_record(self):
        self.write("harness.py", "# new production code")
        result = self.review()
        self.assertEqual(result.returncode, 1)
        self.assertIn("harness.py", result.stdout)

        self.write(RECORD, "Trigger: Example code change.\n")
        self.assertEqual(self.review().returncode, 1)

        self.write(RECORD, REVIEW)
        self.git("add", ".")
        result = self.review()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(RECORD, result.stdout)

    def test_manual_signal_catches_friction_without_code_changes(self):
        args = ("--signal", "Repeated manual verification.")
        self.assertEqual(self.review(*args).returncode, 1)
        self.write(RECORD, REVIEW)
        self.assertEqual(self.review(*args).returncode, 0)


if __name__ == "__main__":
    unittest.main()
