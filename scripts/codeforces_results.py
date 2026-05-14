#!/usr/bin/env python3
"""Fetch and normalize one user's Codeforces contest problem results."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import codeforces_metadata
from plan_publish import extract_codeforces_round_number


NON_PENALTY_VERDICTS = {"COMPILATION_ERROR", "SKIPPED", "TESTING"}


class CodeforcesResultsError(RuntimeError):
    def __init__(self, message: str, returncode: int = 1) -> None:
        super().__init__(message)
        self.returncode = returncode


def output_json(data: dict[str, Any], output: Path | None) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


def common_fetch_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "cache_dir": args.cache_dir.expanduser().resolve(),
        "max_age_seconds": args.max_age,
        "refresh": args.refresh,
        "no_cache": args.no_cache,
        "timeout": args.timeout,
    }


def load_method(method: str, params: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    return codeforces_metadata.load_method(method, params, **common_fetch_kwargs(args))


def problem_id(problem: dict[str, Any]) -> str:
    value = problem.get("index")
    return str(value).upper() if value is not None else ""


def find_user_row(rows: list[dict[str, Any]], handle: str) -> dict[str, Any] | None:
    wanted = handle.lower()
    for row in rows:
        party = row.get("party")
        if not isinstance(party, dict):
            continue
        for member in party.get("members") or []:
            if isinstance(member, dict) and str(member.get("handle", "")).lower() == wanted:
                return row
    return None


def int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def accepted_seconds_from_standings(result: dict[str, Any]) -> int | None:
    accepted_at = int_or_none(result.get("bestSubmissionTimeSeconds"))
    if accepted_at is None:
        return None

    points = number_or_none(result.get("points"))
    if points is not None and points <= 0:
        return None
    return accepted_at


def normalized_from_standings(
    *,
    handle: str,
    contest: dict[str, Any],
    problems: list[dict[str, Any]],
    row: dict[str, Any],
    source: dict[str, Any],
) -> dict[str, Any]:
    results = row.get("problemResults") or []
    normalized_problems: list[dict[str, Any]] = []

    for index, problem in enumerate(problems):
        result = results[index] if index < len(results) and isinstance(results[index], dict) else {}
        accepted_at = accepted_seconds_from_standings(result)
        normalized_problems.append(
            {
                "problem_id": problem_id(problem),
                "wrong_attempts": int_or_none(result.get("rejectedAttemptCount")) or 0,
                "accepted_at_seconds": accepted_at,
            }
        )

    contest_id = str(contest.get("id"))
    contest_name = contest.get("name")
    round_number = extract_codeforces_round_number(contest_name, None)

    return {
        "platform": "codeforces",
        "user": handle,
        "participated": True,
        "contest": {
            "contest_id": contest_id,
            "round_number": round_number,
            "contest_name": contest_name,
            "url": f"https://codeforces.com/contest/{contest_id}",
        },
        "problems": normalized_problems,
        "source": source,
        "fetched_at_unix": int(time.time()),
    }


def should_count_wrong_submission(submission: dict[str, Any]) -> bool:
    verdict = submission.get("verdict")
    return isinstance(verdict, str) and verdict != "OK" and verdict not in NON_PENALTY_VERDICTS


def normalized_from_submissions(
    *,
    handle: str,
    contest: dict[str, Any],
    problems: list[dict[str, Any]],
    submissions: list[dict[str, Any]],
    source: dict[str, Any],
) -> dict[str, Any]:
    start_time = int_or_none(contest.get("startTimeSeconds")) or 0
    by_problem: dict[str, list[dict[str, Any]]] = {}
    for submission in submissions:
        problem = submission.get("problem")
        if not isinstance(problem, dict):
            continue
        index = str(problem.get("index", "")).upper()
        if index:
            by_problem.setdefault(index, []).append(submission)

    normalized_problems: list[dict[str, Any]] = []
    for problem in problems:
        index = problem_id(problem)
        wrong_attempts = 0
        accepted_at: int | None = None
        for submission in sorted(by_problem.get(index, []), key=lambda item: item.get("creationTimeSeconds", 0)):
            if accepted_at is not None:
                break
            if submission.get("verdict") == "OK":
                creation_time = int_or_none(submission.get("creationTimeSeconds"))
                accepted_at = max(0, creation_time - start_time) if creation_time is not None else None
            elif should_count_wrong_submission(submission):
                wrong_attempts += 1
        normalized_problems.append(
            {
                "problem_id": index,
                "wrong_attempts": wrong_attempts,
                "accepted_at_seconds": accepted_at,
            }
        )

    contest_id = str(contest.get("id"))
    contest_name = contest.get("name")
    round_number = extract_codeforces_round_number(contest_name, None)
    return {
        "platform": "codeforces",
        "user": handle,
        "participated": True,
        "contest": {
            "contest_id": contest_id,
            "round_number": round_number,
            "contest_name": contest_name,
            "url": f"https://codeforces.com/contest/{contest_id}",
        },
        "problems": normalized_problems,
        "source": source,
        "fetched_at_unix": int(time.time()),
    }


def get_contest_result(args: argparse.Namespace) -> dict[str, Any]:
    standings_data = load_method(
        "contest.standings",
        {"contestId": args.contest_id, "handles": args.user, "showUnofficial": True},
        args,
    )
    result = standings_data.get("result")
    if not isinstance(result, dict):
        raise CodeforcesResultsError("contest.standings returned an unexpected payload.")

    contest = result.get("contest")
    problems = result.get("problems")
    rows = result.get("rows")
    if not isinstance(contest, dict) or not isinstance(problems, list) or not isinstance(rows, list):
        raise CodeforcesResultsError("contest.standings is missing contest, problems, or rows.")

    row = find_user_row(rows, args.user)
    if row is not None:
        return normalized_from_standings(
            handle=args.user,
            contest=contest,
            problems=problems,
            row=row,
            source={"standings": "contest.standings", "submissions": None},
        )

    if not args.fallback_submissions:
        raise CodeforcesResultsError(f"User {args.user!r} was not found in contest standings.")

    submissions_data = load_method(
        "contest.status",
        {"contestId": args.contest_id, "handle": args.user},
        args,
    )
    submissions = submissions_data.get("result")
    if not isinstance(submissions, list):
        raise CodeforcesResultsError("contest.status returned an unexpected payload.")
    if not submissions:
        raise CodeforcesResultsError(
            f"No contest submissions found for {args.user!r} in contest {args.contest_id}."
        )

    return normalized_from_submissions(
        handle=args.user,
        contest=contest,
        problems=problems,
        submissions=submissions,
        source={"standings": "contest.standings", "submissions": "contest.status"},
    )


def fetch_contest_result(args: argparse.Namespace) -> int:
    output_json(get_contest_result(args), args.output)
    return 0


def add_common_fetch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=codeforces_metadata.default_cache_dir() / "results",
        help="Directory for cached Codeforces API responses.",
    )
    parser.add_argument(
        "--max-age",
        type=int,
        default=codeforces_metadata.DEFAULT_MAX_AGE_SECONDS,
        help="Cache max age in seconds. Use 0 with --refresh for a fresh fetch.",
    )
    parser.add_argument("--refresh", action="store_true", help="Ignore cache and fetch from Codeforces.")
    parser.add_argument("--no-cache", action="store_true", help="Do not read or write cache.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=codeforces_metadata.DEFAULT_TIMEOUT_SECONDS,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument("--output", type=Path, help="Write JSON output to this file instead of stdout.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch one user's Codeforces contest wrong attempts and accepted times."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    contest = subparsers.add_parser("contest", help="Fetch one user's contest problem results.")
    add_common_fetch_args(contest)
    contest.add_argument("--contest-id", required=True, help="Codeforces contest ID from the URL.")
    contest.add_argument("--user", required=True, help="Codeforces handle.")
    contest.add_argument(
        "--no-fallback-submissions",
        dest="fallback_submissions",
        action="store_false",
        help="Do not call contest.status if the user is missing from standings.",
    )
    contest.set_defaults(fallback_submissions=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "contest":
            return fetch_contest_result(args)
        parser.error(f"Unknown command: {args.command}")
    except (CodeforcesResultsError, codeforces_metadata.CodeforcesApiError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return getattr(exc, "returncode", 1)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
