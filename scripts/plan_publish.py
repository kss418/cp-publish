#!/usr/bin/env python3
"""Build a dry-run publish plan for a competitive programming solution."""

from __future__ import annotations

import argparse
import json
import sys

from cp_publish.models import PlanError, SUPPORTED_PLATFORMS
from cp_publish.paths import (
    normalize_codeforces_contest_group,
    normalize_codeforces_kind,
    normalize_codeforces_round_number,
)
from cp_publish.planning import build_plan, make_error_plan


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a dry-run publish plan for a CP solution.")
    parser.add_argument("source", help="Solution source file to publish.")
    parser.add_argument("--config", help="Path to cp-publish config JSON.")
    parser.add_argument("--platform", choices=sorted(SUPPORTED_PLATFORMS), help="Override detected platform.")
    parser.add_argument("--contest-id", help="Override detected contest id.")
    parser.add_argument("--problem-id", help="Override detected problem id/index.")
    parser.add_argument("--problem-title", help="Override or provide the problem title for the stored filename.")
    parser.add_argument(
        "--contest-kind",
        metavar="{regular,Educational,Others}",
        type=normalize_codeforces_kind,
        help="Codeforces path class.",
    )
    parser.add_argument("--contest-title", help="Codeforces contest title used for path classification.")
    parser.add_argument(
        "--round-number",
        type=normalize_codeforces_round_number,
        help="Codeforces round number used for path placement.",
    )
    parser.add_argument(
        "--contest-group",
        type=normalize_codeforces_contest_group,
        help="Codeforces Others group directory name, for example Global_Round.",
    )
    parser.add_argument(
        "--additional-target",
        action="append",
        default=[],
        help="Extra Codeforces target as CONTEST_ID:PROBLEM_ID[:KIND[:ROUND_NUMBER[:CONTEST_GROUP]]].",
    )
    parser.add_argument("--rating", help="Override README rating. Use '-' for unknown.")
    parser.add_argument("--tags", help="Comma-separated README tags.")
    parser.add_argument("--tag", action="append", default=[], help="README tag. Can be repeated or comma-separated.")
    parser.add_argument("--no-metadata", action="store_true", help="Do not fetch or read platform metadata.")
    parser.add_argument("--refresh-metadata", action="store_true", help="Refresh cached platform metadata if needed.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        plan, status = build_plan(args)
    except PlanError as exc:
        print(json.dumps(make_error_plan(args.source, str(exc)), ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
