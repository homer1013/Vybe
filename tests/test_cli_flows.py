import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(REPO_ROOT / "src")


def run_vybe(args, env):
    cmd = [sys.executable, "-m", "vybe.cli"] + args
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        text=True,
        capture_output=True,
    )


class VybeCliFlowsTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_file = tempfile.NamedTemporaryFile(delete=False)
        self.state_file.close()
        self.base_env = os.environ.copy()
        self.base_env["PYTHONPATH"] = SRC_PATH
        self.base_env["VYBE_DIR"] = self.tmpdir.name
        self.base_env["VYBE_INDEX"] = str(Path(self.tmpdir.name) / "index.jsonl")
        self.base_env["VYBE_STATE"] = self.state_file.name

    def tearDown(self):
        try:
            os.unlink(self.state_file.name)
        except FileNotFoundError:
            pass
        self.tmpdir.cleanup()

    def test_retry_alias_flow(self):
        run1 = run_vybe(["r", sys.executable, "-c", "print('hello')"], self.base_env)
        self.assertEqual(run1.returncode, 0, run1.stderr)

        retry = run_vybe(["rr"], self.base_env)
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertIn("hello", retry.stdout)

        snip = run_vybe(["s"], self.base_env)
        self.assertEqual(snip.returncode, 0, snip.stderr)
        self.assertEqual(snip.stdout.strip(), "hello")

    def test_tag_filter_and_diff(self):
        run_a = run_vybe(
            ["run", "--tag", "smoke", sys.executable, "-c", "print('one')"],
            self.base_env,
        )
        self.assertEqual(run_a.returncode, 0, run_a.stderr)

        run_b = run_vybe(
            ["run", "--tag", "smoke", sys.executable, "-c", "print('two')"],
            self.base_env,
        )
        self.assertEqual(run_b.returncode, 0, run_b.stderr)

        ls_tag = run_vybe(["ls", "--tag", "smoke"], self.base_env)
        self.assertEqual(ls_tag.returncode, 0, ls_tag.stderr)
        self.assertIn("tag: smoke", ls_tag.stdout)

        diff_tag = run_vybe(["diff", "--tag", "smoke"], self.base_env)
        self.assertEqual(diff_tag.returncode, 0, diff_tag.stderr)
        self.assertIn("-one", diff_tag.stdout)
        self.assertIn("+two", diff_tag.stdout)

    def test_export_json_redaction(self):
        fail_run = run_vybe(
            [
                "r",
                sys.executable,
                "-c",
                "print('token=abc123'); print('ValueError: boom'); raise SystemExit(1)",
            ],
            self.base_env,
        )
        self.assertNotEqual(fail_run.returncode, 0)

        exported = run_vybe(["export", "--last", "--json", "--snip", "--redact"], self.base_env)
        self.assertEqual(exported.returncode, 0, exported.stderr)
        payload = json.loads(exported.stdout)
        self.assertTrue(payload["redacted"])
        self.assertTrue(payload["output_only"])
        self.assertNotIn("abc123", payload["text"])
        self.assertIn("[REDACTED]", payload["text"])

    def test_share_json_with_errors(self):
        fail_run = run_vybe(
            [
                "r",
                sys.executable,
                "-c",
                "print('token=abc123'); print('Traceback (most recent call last):'); print('ValueError: boom'); raise SystemExit(1)",
            ],
            self.base_env,
        )
        self.assertNotEqual(fail_run.returncode, 0)

        shared = run_vybe(["share", "--json", "--errors", "--redact"], self.base_env)
        self.assertEqual(shared.returncode, 0, shared.stderr)
        payload = json.loads(shared.stdout)
        self.assertTrue(payload["errors_included"])
        self.assertGreaterEqual(len(payload["error_blocks"]), 1)
        self.assertNotIn("abc123", payload["output"])


if __name__ == "__main__":
    unittest.main()
