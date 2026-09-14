from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from api import atcoder_metadata as ac
from api import codeforces_metadata as cf
from cp_publish import metadata as md, batch_publish as bp, apply_plan as ap
from cp_publish.file_io import source_sha256
from init import github_integration as gh


class MetadataReuseTests(unittest.TestCase):
    def test_real_title_only_batch_loads_three_resources_total(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            sources, problems = [], []
            for i, label in enumerate("abcdef"):
                source = root / f"Problem_{i}.cpp"
                source.write_text("// example\n", encoding="utf-8")
                sources.append(source)
                problems.append({"id": f"abc433_{label}", "contest_id": "abc433",
                                 "problem_index": label.upper(), "name": f"Problem {i}"})
            args = bp.build_parser().parse_args(["--copy", "--platform", "atcoder", "--contest-id", "abc433", "--tags", "Math"])
            route = types.SimpleNamespace(repo_path=root, target_base=root, base_dir=".", user_id="example", warnings=[])
            def load(resource, **kwargs):
                return {"result": {} if resource == "ratings" else problems}
            with patch("cp_publish.planning.load_route", return_value=route), patch.object(ac, "load_resource", side_effect=load) as fetch:
                plans, status = bp.build_batch_plans(args, sources)
            self.assertEqual(status, 0)
            self.assertEqual(fetch.call_count, 3)
            self.assertTrue(all(not plan["needs_confirmation"] for plan in plans))

    def test_resources_loaded_once_per_scope_and_options_separated(self):
        @md.metadata_session
        def build():
            for _ in range(6):
                md.load_atcoder_metadata(False, False, [])
                md.load_atcoder_metadata(False, False, [])
                md.load_codeforces_metadata(False, False, [])
            md.load_atcoder_metadata(True, False, [])
        with patch.object(ac, "load_resource", return_value={"result": []}) as atcoder:
            with patch.object(cf, "load_method", return_value={"result": []}) as codeforces:
                build()
                self.assertEqual(atcoder.call_count, 3)
                self.assertEqual(codeforces.call_count, 2)
                build()
                self.assertEqual(atcoder.call_count, 6)
                self.assertEqual(codeforces.call_count, 4)

    def test_nested_scope_refresh_and_warnings(self):
        @md.metadata_session
        def single(warnings):
            md.load_atcoder_metadata(False, True, warnings)
        @md.metadata_session
        def batch():
            first, second = [], []
            single(first)
            single(second)
            self.assertEqual(first, second)
            self.assertEqual(len(first), 3)
        with patch.object(ac, "load_resource", side_effect=OSError("offline")) as fetch:
            batch()
            self.assertEqual(fetch.call_count, 3)
            batch()
            self.assertEqual(fetch.call_count, 6)

    def test_exception_closes_scope(self):
        @md.metadata_session
        def fail():
            md.load_atcoder_metadata(False, False, [])
            raise RuntimeError("stop")
        with patch.object(ac, "load_resource", return_value={"result": []}) as fetch:
            with self.assertRaises(RuntimeError):
                fail()
            self.assertIsNone(md._SNAPSHOT.get())
            md.load_atcoder_metadata(False, False, [])
            self.assertEqual(fetch.call_count, 6)


class SavedResultsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.command = ["python", "results.py", "--contest-id", "abc433", "--user", "example"]
        self.payload = {"participated": False, "problems": []}
        self.update = {"readme": str(self.root / "README.md"), "contest_result_command": self.command}
        self.record = {"command": self.command, "fetched_at": time.time(), "payload": self.payload}

    def fetch(self, **kwargs):
        path = kwargs["temp_dir"] / "fetched.json"
        path.write_text(json.dumps(self.payload), encoding="utf-8")
        return path, self.payload

    def prepare(self, records, **kwargs):
        return ap.prepare_readme_updates([self.update, self.update], with_results=True,
            require_results=True, temp_dir=self.root, saved_results=records, **kwargs)

    def test_fresh_results_restore_without_fetch_and_keep_timestamp(self):
        captured = []
        with patch.object(ap, "fetch_result_json", side_effect=AssertionError("unexpected fetch")):
            prepared, reports, _ = self.prepare([self.record], captured_results=captured)
        self.assertEqual(json.loads(Path(prepared[0]["_results_json"]).read_text()), self.payload)
        self.assertTrue(all(r["from_saved_plan"] for r in reports))
        self.assertEqual(captured, [self.record])

    def test_invalid_expired_or_different_identity_refetch(self):
        variants = [
            dict(self.record, fetched_at=time.time() - 301),
            dict(self.record, fetched_at=time.time() + 3600),
            dict(self.record, fetched_at=float("nan")),
            dict(self.record, fetched_at=True),
            dict(self.record, payload={"broken": True}),
            dict(self.record, command=self.command[:-1] + ["another-user"]),
            dict(self.record, command=["other-contest"]),
            {}, None,
        ]
        for record in variants:
            with self.subTest(record=record):
                with patch.object(ap, "fetch_result_json", side_effect=self.fetch) as fetch:
                    _, reports, _ = self.prepare([record])
                    self.assertEqual(fetch.call_count, 1)
                    self.assertFalse(reports[0]["from_saved_plan"])

    def test_failed_fetch_not_captured(self):
        captured = []
        with patch.object(ap, "fetch_result_json", side_effect=ap.ApplyPlanError("offline")):
            ap.prepare_readme_updates([self.update], with_results=True, require_results=False,
                temp_dir=self.root, captured_results=captured)
        self.assertEqual(captured, [])

    def test_cli_save_and_apply_reuses_and_can_bypass(self):
        source = self.root / "A.cpp"
        source.write_text("// example\n", encoding="utf-8")
        repo = self.root / "repo"
        repo.mkdir()
        update = dict(self.update, readme=str(repo / "README.md"),
                      contest_url="https://atcoder.jp/contests/abc433", problem_id="A", rating="43", tags="Math")
        plans = [{"source": str(source), "source_sha256": source_sha256(source), "repo": str(repo),
                  "targets": [str(repo / "A.cpp")], "readme_updates": [update], "platform": "atcoder"}]
        saved = self.root / "plan.json"
        with patch.object(bp, "build_batch_plans", return_value=(plans, 0)):
            with patch.object(ap, "fetch_result_json", side_effect=self.fetch) as fetch:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(bp.main([str(source), "--copy", "--dry-run", "--save-plan", str(saved)]), 0)
                self.assertEqual(fetch.call_count, 1)
        bundle = json.loads(saved.read_text())
        self.assertEqual(len(bundle["result_snapshots"]), 1)
        self.assertFalse((repo / "A.cpp").exists())
        with patch.object(ap, "fetch_result_json", side_effect=AssertionError("unexpected fetch")):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bp.main(["--apply-plan", str(saved)]), 0)
        self.assertEqual(source.read_bytes(), (repo / "A.cpp").read_bytes())
        with patch.object(ap, "fetch_result_json", side_effect=self.fetch) as fetch:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bp.main(["--apply-plan", str(saved), "--dry-run", "--no-saved-results"]), 0)
            self.assertEqual(fetch.call_count, 1)


class AuthReuseTests(unittest.TestCase):
    def test_success_checks_auth_once(self):
        with patch.object(gh, "gh_auth_status", return_value=subprocess.CompletedProcess([], 0)) as status:
            with patch.object(gh, "require_tool", side_effect=lambda tool: tool):
                with patch.object(gh, "run") as run:
                    gh.ensure_auth(login=False, setup_git=True)
        self.assertEqual(status.call_count, 1)
        run.assert_called_once_with(["gh", "auth", "setup-git"], check=True, capture=False)

    def test_login_is_rechecked(self):
        with patch.object(gh, "gh_auth_status", side_effect=[subprocess.CompletedProcess([], 1), subprocess.CompletedProcess([], 0)]) as status:
            with patch.object(gh, "gh_auth_login_web") as login:
                gh.ensure_auth(login=True, setup_git=False)
        self.assertEqual(status.call_count, 2)
        login.assert_called_once()

    def push(self, run, **kwargs):
        with patch.object(gh, "ensure_auth") as auth, patch.object(gh, "origin_url", return_value="url"), \
                patch.object(gh, "current_branch", return_value="main"), patch.object(gh, "upstream_ref", return_value="origin/main"), \
                patch.object(gh, "require_tool", side_effect=lambda tool: tool), patch.object(gh, "run", side_effect=run):
            gh.push_current_branch(Path.cwd(), dry_run=False, verify_first=True)
            auth.assert_called_once()

    def test_verified_push_reuses_auth(self):
        commands = []
        def run(command, **kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, "same-head\n")
        self.push(run)
        self.assertEqual([c for c in commands if c[1] == "push"], [["git", "push", "--dry-run"], ["git", "push"]])

    def test_failed_dry_run_never_pushes(self):
        commands = []
        def run(command, **kwargs):
            commands.append(command)
            if "--dry-run" in command:
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0, "head\n")
        with self.assertRaises(subprocess.CalledProcessError):
            self.push(run)
        self.assertNotIn(["git", "push"], commands)

    def test_changed_head_never_pushes(self):
        heads = iter(["before", "after"])
        commands = []
        def run(command, **kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, next(heads) if "rev-parse" in command else "")
        with self.assertRaises(gh.CommandError):
            self.push(run)
        self.assertNotIn(["git", "push"], commands)


if __name__ == "__main__":
    unittest.main()
