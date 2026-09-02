from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from api import atcoder_metadata  # noqa: E402
from cp_publish.batch_publish import load_source_manifest, plan_args_for_source  # noqa: E402
from cp_publish.metadata import (  # noqa: E402
    resolve_atcoder_detection_by_title,
    strip_atcoder_problem_label,
)
from cp_publish.models import Detection  # noqa: E402


class AtCoderMetadataTests(unittest.TestCase):
    def test_sub_400_difficulty_uses_displayed_value(self) -> None:
        cases = {
            -1091: 10,
            -725: 24,
            125: 201,
            400: 400,
            903: 903,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(
                    atcoder_metadata.extract_difficulty({"difficulty": raw}),
                    expected,
                )

    def test_matching_problem_label_is_removed_from_title(self) -> None:
        self.assertEqual(
            atcoder_metadata.problem_title(
                {"name": "Too Many Requests", "title": "A. Too Many Requests"}
            ),
            "Too Many Requests",
        )
        self.assertEqual(
            strip_atcoder_problem_label("A. Too Many Requests", "abc429_a"),
            "Too Many Requests",
        )
        self.assertEqual(
            strip_atcoder_problem_label("N - 1", "abc429_b"),
            "N - 1",
        )
        self.assertEqual(
            strip_atcoder_problem_label("A - B", "abc999_a"),
            "A - B",
        )

    def test_title_only_filename_resolves_within_contest(self) -> None:
        detection = Detection(platform="atcoder", contest_id="abc429")
        metadata = {
            "problems": [
                {
                    "id": "abc429_a",
                    "contest_id": "abc429",
                    "problem_index": "A",
                    "name": "Too Many Requests",
                    "title": "A. Too Many Requests",
                },
                {
                    "id": "abc429_b",
                    "contest_id": "abc429",
                    "problem_index": "B",
                    "name": "N - 1",
                    "title": "B. N - 1",
                },
            ],
            "merged": [],
        }
        warnings: list[str] = []

        resolve_atcoder_detection_by_title(
            detection,
            Path("Too_Many_Requests.cpp"),
            metadata,
            warnings,
        )

        self.assertEqual(detection.problem_id, "A")
        self.assertEqual(detection.problem_title, "Too Many Requests")
        self.assertEqual(detection.confidence, "high")
        self.assertEqual(warnings, [])


class BatchManifestTests(unittest.TestCase):
    def test_manifest_applies_per_source_problem_and_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            source = temp_dir / "Too_Many_Requests.cpp"
            source.write_text("int main() {}\n", encoding="utf-8")
            manifest_path = temp_dir / "abc429.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        source.name: {
                            "problem_id": "A",
                            "problem_title": "Too Many Requests",
                            "rating": 10,
                            "tags": ["Implementation", "Case_Work"],
                        }
                    }
                ),
                encoding="utf-8",
            )

            manifest = load_source_manifest(manifest_path)
            args = argparse.Namespace(
                config=None,
                platform="atcoder",
                contest_id="abc429",
                problem_id=None,
                problem_title=None,
                contest_kind=None,
                contest_title=None,
                round_number=None,
                contest_group=None,
                additional_target=[],
                rating=None,
                tags=None,
                tag=[],
                tags_from_readme=False,
                problem_id_from_filename=False,
                no_metadata=False,
                refresh_metadata=False,
            )

            planned = plan_args_for_source(args, source, manifest[source.resolve()])

            self.assertEqual(planned.problem_id, "A")
            self.assertEqual(planned.problem_title, "Too Many Requests")
            self.assertEqual(planned.rating, "10")
            self.assertEqual(planned.tags, "Implementation,Case_Work")


if __name__ == "__main__":
    unittest.main()
