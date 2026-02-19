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

def run_module(module, args, env):
    cmd = [sys.executable, "-m", module] + args
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
        self.base_env["HOME"] = self.tmpdir.name
        self.base_env["VYBE_DIR"] = self.tmpdir.name
        self.base_env["VYBE_INDEX"] = str(Path(self.tmpdir.name) / "index.jsonl")
        self.base_env["VYBE_STATE"] = self.state_file.name
        self.base_env["VYBE_CONFIG"] = str(Path(self.tmpdir.name) / "config.json")

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

    def test_non_utf8_output_does_not_crash(self):
        bad_bytes = (
            "import sys; "
            "sys.stdout.buffer.write(b'hello\\\\x80world\\\\n'); "
            "sys.stdout.buffer.flush()"
        )
        run_bad = run_vybe(["r", sys.executable, "-c", bad_bytes], self.base_env)
        self.assertEqual(run_bad.returncode, 0, run_bad.stderr)
        self.assertIn("Saved:", run_bad.stdout)

        snip = run_vybe(["s"], self.base_env)
        self.assertEqual(snip.returncode, 0, snip.stderr)
        self.assertIn("hello", snip.stdout)
        self.assertIn("world", snip.stdout)

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

    def test_main_module_entrypoint(self):
        proc = run_module("vybe", ["--help"], self.base_env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("vybe - vibe coding terminal capture toolkit", proc.stdout)

    def test_init_cfg_and_completion_install(self):
        init = run_vybe(["init"], self.base_env)
        self.assertEqual(init.returncode, 0, init.stderr)
        cfg_path = Path(self.base_env["VYBE_CONFIG"])
        self.assertTrue(cfg_path.exists())

        cfg = run_vybe(["cfg", "--json"], self.base_env)
        self.assertEqual(cfg.returncode, 0, cfg.stderr)
        cfg_obj = json.loads(cfg.stdout)
        self.assertIn("paths", cfg_obj)
        self.assertIn("config", cfg_obj)

        comp = run_vybe(["completion", "install", "zsh"], self.base_env)
        self.assertEqual(comp.returncode, 0, comp.stderr)
        dest = Path(self.base_env["HOME"]) / ".zsh" / "completions" / "_vybe"
        self.assertTrue(dest.exists())

    def test_self_check_json(self):
        check = run_vybe(["self-check", "--json"], self.base_env)
        self.assertEqual(check.returncode, 0, check.stderr)
        obj = json.loads(check.stdout)
        self.assertIn("externally_managed", obj)
        self.assertIn("pipx_available", obj)
        self.assertIn("recommendations", obj)
        self.assertIsInstance(obj["recommendations"], list)

    def test_prompt_debug(self):
        fail_run = run_vybe(
            ["r", sys.executable, "-c", "print('ValueError: boom'); raise SystemExit(1)"],
            self.base_env,
        )
        self.assertNotEqual(fail_run.returncode, 0)

        prompt = run_vybe(["prompt", "debug"], self.base_env)
        self.assertEqual(prompt.returncode, 0, prompt.stderr)
        self.assertIn("# Vybe Prompt (debug)", prompt.stdout)
        self.assertIn("ValueError: boom", prompt.stdout)
        self.assertIn("## Response format", prompt.stdout)

    def test_new_commands_basic(self):
        # Test cmdcopy
        run1 = run_vybe(["r", sys.executable, "-c", "print('hello')"], self.base_env)
        self.assertEqual(run1.returncode, 0)
        
        cc = run_vybe(["cc"], self.base_env)
        self.assertEqual(cc.returncode, 0)
        self.assertIn("Copied command", cc.stdout)
        
        # Test history
        history = run_vybe(["history", "1"], self.base_env)
        self.assertEqual(history.returncode, 0)
        self.assertIn("hello", history.stdout)
        
        # Test stats
        stats = run_vybe(["stats"], self.base_env)
        self.assertEqual(stats.returncode, 0)
        self.assertIn("Total runs:", stats.stdout)
        
        # Test clean (should not crash)
        clean = run_vybe(["clean", "--keep", "10"], self.base_env)
        self.assertEqual(clean.returncode, 0)
        
        # Test cwd set
        cwd_set = run_vybe(["cwd", "set"], self.base_env)
        self.assertEqual(cwd_set.returncode, 0)
        self.assertIn("Saved working directory", cwd_set.stdout)
        
        # Test cwd run
        cwd_run = run_vybe(["cwd", "run"], self.base_env)
        self.assertEqual(cwd_run.returncode, 0)

    def test_flow_basic(self):
        # Save a flow
        flow_save = run_vybe(["flow", "save", "test-flow", "echo", "test"], self.base_env)
        self.assertEqual(flow_save.returncode, 0)
        self.assertIn("Saved flow", flow_save.stdout)
        
        # List flows
        flow_list = run_vybe(["flow", "list"], self.base_env)
        self.assertEqual(flow_list.returncode, 0)
        self.assertIn("test-flow", flow_list.stdout)

    def test_help_variations(self):
        # Test all help variations
        for help_arg in ["-h", "--help", "-H", "-Help", "-HELP", "help", "HELP"]:
            result = run_vybe([help_arg], self.base_env)
            self.assertEqual(result.returncode, 0, f"Failed for {help_arg}")
            self.assertIn("vybe - vibe coding terminal capture toolkit", result.stdout)


if __name__ == "__main__":
    unittest.main()
