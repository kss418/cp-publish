import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from init import github_integration as gh


class TimingTests(unittest.TestCase):
    def invoke(self, enabled, failure=False):
        stream = io.StringIO()
        token = gh.TIMINGS.set(enabled)
        result = subprocess.CompletedProcess([], 0, "private output")
        error = subprocess.CalledProcessError(7, ["git", "secret"])
        try:
            with patch.object(gh.subprocess, "run", side_effect=error if failure else None,
                              return_value=result), contextlib.redirect_stderr(stream):
                if failure:
                    with self.assertRaises(subprocess.CalledProcessError):
                        gh.run(["git", "secret"])
                else:
                    self.assertIs(gh.run(["git", "secret"]), result)
        finally:
            gh.TIMINGS.reset(token)
        return stream.getvalue()

    def test_default_is_silent(self):
        self.assertEqual(self.invoke(False), "")

    def test_success_is_timed_without_sensitive_data(self):
        output = self.invoke(True)
        record = json.loads(output)
        self.assertEqual(record["returncode"], 0)
        self.assertGreaterEqual(record["seconds"], 0)
        self.assertNotIn("secret", output)
        self.assertNotIn("private output", output)

    def test_failure_is_timed_and_propagated(self):
        self.assertEqual(json.loads(self.invoke(True, failure=True))["returncode"], 7)

    def test_cli_resets_timing_after_error(self):
        with patch.object(gh, "ensure_auth", side_effect=gh.CommandError("failed")), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(gh.main(["--timings", "auth"]), 1)
        self.assertFalse(gh.TIMINGS.get())


if __name__ == "__main__":
    unittest.main()
