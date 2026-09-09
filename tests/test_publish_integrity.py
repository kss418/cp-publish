from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cp_publish import apply_plan as ap
from cp_publish import batch_publish as bp
from cp_publish import file_io
from cp_publish import planning
from cp_publish import update_readme as ur


class PublishIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.args = bp.build_parser().parse_args(["--copy", "--no-results"])

    def plans(self, count=5):
        result = []
        for index in range(count):
            label = chr(65 + index)
            source = self.root / f"{label}.cpp"
            source.write_text(f"// original {label}\n", encoding="utf-8")
            result.append({
                "source": str(source), "source_sha256": file_io.source_sha256(source),
                "repo": str(self.repo), "platform": "atcoder", "needs_confirmation": False,
                "targets": [str(self.repo / "contest" / source.name)],
                "readme_updates": [{"readme": str(self.repo / "contest" / "README.md"),
                    "contest_url": "https://atcoder.jp/contests/abc432", "problem_id": label,
                    "rating": "12", "tags": "Math"}],
            })
        return result

    def test_atomic_failures_preserve_destination_and_remove_temp(self):
        path = self.root / "README.md"
        path.write_bytes(b"original\n")
        for operation in ("fsync", "replace"):
            with self.subTest(operation=operation):
                with patch(f"cp_publish.file_io.os.{operation}", side_effect=OSError("disk full")):
                    with self.assertRaises(OSError):
                        file_io.atomic_write_text(path, "replacement\n")
                self.assertEqual(path.read_bytes(), b"original\n")
                self.assertEqual(list(self.root.glob(".*.tmp")), [])

    def test_atomic_success_supports_unicode_and_existing_file(self):
        path = self.root / "README.md"
        file_io.atomic_write_text(path, "풀이\n")
        self.assertEqual(path.read_bytes(), "풀이\n".encode())
        file_io.atomic_write_text(path, "new\n")
        self.assertEqual(path.read_bytes(), b"new\n")

    def test_five_entries_use_one_write_and_no_readme_subprocess(self):
        plans = self.plans()
        with patch.object(ap, "atomic_write_text", wraps=file_io.atomic_write_text) as write:
            with patch.object(ap.subprocess, "run", side_effect=AssertionError("unexpected process")):
                result = bp.apply_batch(plans, self.args)
        self.assertEqual(write.call_count, 1)
        self.assertEqual(len(result["commit_paths"]), 6)
        readme = self.repo / "contest" / "README.md"
        text = readme.read_text(encoding="utf-8")
        for label in "ABCDE":
            self.assertEqual(text.count(f"{label} / Rating"), 1)
        for plan in plans:
            self.assertEqual(Path(plan["source"]).read_bytes(), Path(plan["targets"][0]).read_bytes())

    def test_dry_run_writes_nothing_and_is_idempotent_after_apply(self):
        plans = self.plans()
        self.args.dry_run = True
        bp.apply_batch(plans, self.args)
        self.assertEqual(list(self.repo.iterdir()), [])
        self.args.dry_run = False
        bp.apply_batch(plans, self.args)
        with patch.object(ap, "atomic_write_text", wraps=file_io.atomic_write_text) as write:
            result = bp.apply_batch(plans, self.args)
        self.assertEqual(write.call_count, 0)
        self.assertEqual(result["changed_paths"], [])

    def test_bad_later_entry_prevents_all_source_writes(self):
        plans = self.plans()
        plans[-1]["readme_updates"][0]["tags"] = "Not_A_Real_Tag"
        with self.assertRaises(ap.ApplyPlanError):
            bp.apply_batch(plans, self.args)
        self.assertEqual(list(self.repo.iterdir()), [])

    def test_multiple_readmes_preserve_notes_entries_and_results(self):
        plans = self.plans(2)
        readme = self.repo / "contest" / "README.md"
        readme.parent.mkdir()
        readme.write_text("# https://atcoder.jp/contests/abc432\n\n## Solutions\n\nZ / Rating : $9$ / DP\n\nMy notes\n", encoding="utf-8")
        results_path = self.root / "results.json"
        results_path.write_text(json.dumps({"problems": [{"problem_id": "A", "wrong_attempts": 2,
            "accepted_at_seconds": 61}]}), encoding="utf-8")
        updates = [p["readme_updates"][0] for p in plans]
        for update in updates:
            update["_results_json"] = str(results_path)
        other = dict(updates[0], readme=str(self.repo / "other" / "README.md"))
        prepared, writes = ap.prepare_grouped_readmes([updates[0], other, updates[1]])
        self.assertEqual(len(writes), 2)
        self.assertEqual([row["problem_id"] for row in prepared], ["A", "A", "B"])
        ap.write_grouped_readmes(writes)
        text = readme.read_text(encoding="utf-8")
        for value in ("My notes", "Z / Rating : $9$ / DP", "00:01:01", "| Wrong | 2 |"):
            self.assertIn(value, text)

    def test_failed_results_fetch_once_per_batch_but_retry_next_batch(self):
        updates = [dict(p["readme_updates"][0], contest_result_command=["fetch", "contest"]) for p in self.plans()]
        with patch.object(ap, "fetch_result_json", side_effect=ap.ApplyPlanError("offline")) as fetch:
            prepared, reports, warnings = ap.prepare_readme_updates(updates, with_results=True,
                require_results=False, temp_dir=self.root)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual([r["reused"] for r in reports], [False, True, True, True, True])
            self.assertTrue(all("_results_json" not in item for item in prepared))
            self.assertTrue(warnings)
            ap.prepare_readme_updates(updates, with_results=True, require_results=False, temp_dir=self.root)
            self.assertEqual(fetch.call_count, 2)

    def test_required_results_failure_stops_immediately(self):
        updates = [dict(p["readme_updates"][0], contest_result_command=["fetch"]) for p in self.plans()]
        with patch.object(ap, "fetch_result_json", side_effect=ap.ApplyPlanError("offline")) as fetch:
            with self.assertRaises(ap.ApplyPlanError):
                ap.prepare_readme_updates(updates, with_results=True, require_results=True, temp_dir=self.root)
            self.assertEqual(fetch.call_count, 1)

    def test_successful_results_still_shared(self):
        updates = [dict(p["readme_updates"][0], contest_result_command=["fetch"]) for p in self.plans()]
        with patch.object(ap, "fetch_result_json", return_value=(self.root / "results.json", {"problems": []})) as fetch:
            prepared, reports, _ = ap.prepare_readme_updates(updates, with_results=True,
                require_results=False, temp_dir=self.root)
            self.assertEqual(fetch.call_count, 1)
            self.assertTrue(all("_results_json" in item for item in prepared))

    def test_saved_hash_rejects_changed_or_legacy_source_before_writes(self):
        plans = self.plans()
        path = self.root / "plan.json"
        bp.write_batch_plan_bundle(path, plans, self.args)
        loaded, _ = bp.load_batch_plan_bundle(path)
        self.assertEqual(loaded, plans)
        source = Path(loaded[-1]["source"])
        source.write_text("// different\n", encoding="utf-8")
        with self.assertRaisesRegex(ap.ApplyPlanError, "Source changed"):
            bp.apply_batch(loaded, self.args)
        del loaded[0]["source_sha256"]
        with self.assertRaisesRegex(ap.ApplyPlanError, "rebuild the plan"):
            bp.apply_batch(loaded, self.args)
        self.assertEqual(list(self.repo.iterdir()), [])

    def test_change_during_readme_preparation_rejected(self):
        plans = self.plans()
        original = bp.prepare_grouped_readmes
        def change(updates):
            result = original(updates)
            Path(plans[-1]["source"]).write_text("changed", encoding="utf-8")
            return result
        with patch.object(bp, "prepare_grouped_readmes", side_effect=change):
            with self.assertRaisesRegex(ap.ApplyPlanError, "Source changed"):
                bp.apply_batch(plans, self.args)
        self.assertEqual(list(self.repo.iterdir()), [])

    def test_plan_write_failure_preserves_previous_plan(self):
        path = self.root / "plan.json"
        path.write_bytes(b"old plan")
        with patch("cp_publish.file_io.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(bp.BatchPublishError):
                bp.write_batch_plan_bundle(path, self.plans(), self.args)
        self.assertEqual(path.read_bytes(), b"old plan")

    def test_single_readme_cli_compatible(self):
        path = self.repo / "README.md"
        command = ["--readme", str(path), "--contest-url", "https://atcoder.jp/contests/abc432",
                   "--problem-id", "A", "--tags", "Math", "--json"]
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(ur.main(command), 0)
        self.assertEqual(json.loads(output.getvalue())["problem_id"], "A")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(ur.main(command + ["--dry-run"]), 0)
        self.assertFalse(json.loads(output.getvalue())["changed"])

    def test_generated_plan_hash_and_single_apply(self):
        import types
        source = self.root / "abc432_a.cpp"
        source.write_text("// original\n", encoding="utf-8")
        arguments = bp.build_parser().parse_args([
            "--copy", "--no-metadata", "--platform", "atcoder", "--contest-id", "abc432",
            "--problem-title", "Permute to Maximize", "--tags", "Sorting",
        ])
        route = types.SimpleNamespace(repo_path=self.repo, target_base=self.repo, base_dir=".",
                                      user_id="test", warnings=[])
        with patch.object(planning, "load_route", return_value=route):
            plan, status = planning.build_plan(bp.plan_args_for_source(arguments, source))
        self.assertEqual(status, 0)
        self.assertEqual(plan["source_sha256"], file_io.source_sha256(source))
        self.assertFalse(plan["needs_confirmation"], plan)
        ap.apply_plan(plan, self.args)
        self.assertEqual(Path(plan["targets"][0]).read_bytes(), source.read_bytes())
        source.write_text("// edited\n", encoding="utf-8")
        with self.assertRaisesRegex(ap.ApplyPlanError, "Source changed"):
            ap.apply_plan(plan, self.args)


if __name__ == "__main__":
    unittest.main()
