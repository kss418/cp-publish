#!/usr/bin/env python3
"""Fetch and normalize one user's AtCoder contest problem results."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from . import atcoder_metadata, http_support
except ImportError:
    import atcoder_metadata
    import http_support


ATCODER_CONTEST_BASE = "https://atcoder.jp/contests"
KENKOOOO_API_BASE = "https://kenkoooo.com/atcoder/atcoder-api/v3"
USER_AGENT = "cp-publish/0.1"


class AtCoderResultsError(RuntimeError):
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


def cache_path(cache_dir: Path, url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return cache_dir / f"atcoder-results-{digest}.json"


def read_cache(path: Path, max_age_seconds: int) -> dict[str, Any] | None:
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    fetched_at = data.get("fetched_at_unix")
    if not isinstance(fetched_at, int):
        return None

    if max_age_seconds >= 0 and int(time.time()) - fetched_at > max_age_seconds:
        return None

    data["source"] = "cache"
    return data


def write_cache(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch_json(url: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with http_support.open_url(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise AtCoderResultsError(f"AtCoder results API HTTP {exc.code}: {url}") from exc
    except urllib.error.URLError as exc:
        raise AtCoderResultsError(
            f"Failed to reach AtCoder results API: {http_support.format_url_error(exc)}"
        ) from exc
    except TimeoutError as exc:
        raise AtCoderResultsError("Timed out while fetching AtCoder results.") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AtCoderResultsError(f"AtCoder results API returned invalid JSON: {url}") from exc

    return {
        "source": "api",
        "url": url,
        "fetched_at_unix": int(time.time()),
        "result": payload,
    }


def load_url(url: str, args: argparse.Namespace) -> dict[str, Any]:
    cache_dir = args.cache_dir.expanduser().resolve()
    path = cache_path(cache_dir, url)

    if not args.refresh and not args.no_cache:
        cached = read_cache(path, args.max_age)
        if cached is not None:
            return cached

    data = fetch_json(url, args.timeout)
    if not args.no_cache:
        write_cache(path, data)
    return data


def standings_url(contest_id: str) -> str:
    return f"{ATCODER_CONTEST_BASE}/{contest_id}/standings/json"


def submissions_url(user: str, from_second: int) -> str:
    query = urllib.parse.urlencode({"user": user, "from_second": from_second})
    return f"{KENKOOOO_API_BASE}/user/submissions?{query}"


def common_metadata_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "cache_dir": args.metadata_cache_dir.expanduser().resolve(),
        "max_age_seconds": args.max_age,
        "refresh": args.refresh,
        "no_cache": args.no_cache,
        "timeout": args.timeout,
    }


def load_metadata_resource(resource: str, args: argparse.Namespace) -> dict[str, Any]:
    return atcoder_metadata.load_resource(resource, **common_metadata_kwargs(args))


def find_contest_info(contest_id: str, args: argparse.Namespace) -> dict[str, Any] | None:
    try:
        data = load_metadata_resource("contests", args)
    except atcoder_metadata.AtCoderMetadataError:
        return None

    contests = data.get("result")
    if not isinstance(contests, list):
        return None

    for contest in contests:
        if isinstance(contest, dict) and contest.get("id") == contest_id:
            return contest
    return None


def contest_name(contest_id: str, contest_info: dict[str, Any] | None) -> str | None:
    if contest_info:
        for key in ("title", "name"):
            value = contest_info.get(key)
            if isinstance(value, str) and value:
                return value
    return contest_id


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


def elapsed_to_seconds(value: Any) -> int | None:
    numeric = number_or_none(value)
    if numeric is None or numeric <= 0:
        return None

    # AtCoder standings JSON usually stores elapsed time in nanoseconds.
    if numeric >= 10_000_000:
        return int(numeric // 1_000_000_000)
    return int(numeric)


def task_problem_id(task: dict[str, Any]) -> str:
    for key in ("TaskScreenName", "TaskName"):
        value = task.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def task_label(task: dict[str, Any], contest_id: str) -> str:
    assignment = task.get("Assignment")
    if isinstance(assignment, str) and assignment:
        return assignment.upper()

    problem_id = task_problem_id(task)
    return problem_label(problem_id, contest_id)


def problem_label(problem_id: str, contest_id: str) -> str:
    lower_id = problem_id.lower()
    prefix = f"{contest_id.lower()}_"
    if lower_id.startswith(prefix):
        return problem_id[len(prefix) :].upper()
    return problem_id.upper()


def accepted_result(result: dict[str, Any]) -> bool:
    elapsed = elapsed_to_seconds(result.get("Elapsed"))
    score = number_or_none(result.get("Score"))
    status = int_or_none(result.get("Status"))
    if elapsed is None:
        return False
    if status is not None:
        return status == 1
    if score is not None:
        return score > 0
    return False


def wrong_attempts_from_standings(result: dict[str, Any]) -> int:
    failure = int_or_none(result.get("Failure"))
    if failure is not None:
        return max(0, failure)
    return 0


def find_user_row(rows: list[dict[str, Any]], user: str) -> dict[str, Any] | None:
    wanted = user.lower()
    for row in rows:
        for key in ("UserScreenName", "UserName", "UserId"):
            value = row.get(key)
            if isinstance(value, str) and value.lower() == wanted:
                return row
    return None


def normalized_from_standings(
    *,
    user: str,
    contest_id: str,
    contest_info: dict[str, Any] | None,
    standings: dict[str, Any],
    source: dict[str, Any],
) -> dict[str, Any]:
    task_info = standings.get("TaskInfo")
    rows = standings.get("StandingsData")
    if not isinstance(task_info, list) or not isinstance(rows, list):
        raise AtCoderResultsError("AtCoder standings JSON is missing TaskInfo or StandingsData.")

    row = find_user_row([item for item in rows if isinstance(item, dict)], user)
    if row is None:
        raise AtCoderResultsError(f"User {user!r} was not found in AtCoder standings.")

    task_results = row.get("TaskResults")
    if not isinstance(task_results, dict):
        task_results = {}

    normalized_problems: list[dict[str, Any]] = []
    for task in task_info:
        if not isinstance(task, dict):
            continue
        problem_id_value = task_problem_id(task)
        result = task_results.get(problem_id_value)
        if not isinstance(result, dict):
            result = {}
        accepted_at = elapsed_to_seconds(result.get("Elapsed")) if accepted_result(result) else None
        normalized_problems.append(
            {
                "problem_id": task_label(task, contest_id),
                "wrong_attempts": wrong_attempts_from_standings(result),
                "accepted_at_seconds": accepted_at,
            }
        )

    return {
        "platform": "atcoder",
        "user": user,
        "participated": True,
        "contest": {
            "contest_id": contest_id,
            "contest_name": contest_name(contest_id, contest_info),
            "url": f"{ATCODER_CONTEST_BASE}/{contest_id}",
        },
        "problems": normalized_problems,
        "source": source,
        "fetched_at_unix": int(time.time()),
    }


def contest_problem_ids(contest_id: str, args: argparse.Namespace) -> list[str]:
    data = load_metadata_resource("contest-problems", args)
    mappings = data.get("result")
    if not isinstance(mappings, list):
        raise AtCoderResultsError("contest-problem.json did not contain a list.")

    problem_ids: list[str] = []
    seen: set[str] = set()
    for mapping in mappings:
        if not isinstance(mapping, dict) or mapping.get("contest_id") != contest_id:
            continue
        value = mapping.get("problem_id")
        if isinstance(value, str) and value not in seen:
            problem_ids.append(value)
            seen.add(value)

    if not problem_ids:
        raise AtCoderResultsError(f"No contest-problem mapping found for {contest_id!r}.")
    return problem_ids


def contest_time_window(contest_id: str, contest_info: dict[str, Any] | None) -> tuple[int, int | None]:
    if not contest_info:
        raise AtCoderResultsError(f"Contest metadata is required for Kenkoooo submissions: {contest_id}")

    start = int_or_none(contest_info.get("start_epoch_second"))
    duration = int_or_none(contest_info.get("duration_second"))
    if start is None:
        raise AtCoderResultsError(f"Contest start time is missing for {contest_id!r}.")
    end = start + duration if duration is not None else None
    return start, end


def normalized_from_kenkoooo_submissions(
    *,
    user: str,
    contest_id: str,
    contest_info: dict[str, Any] | None,
    problem_ids: list[str],
    submissions: list[dict[str, Any]],
    source: dict[str, Any],
) -> dict[str, Any]:
    start, end = contest_time_window(contest_id, contest_info)
    by_problem: dict[str, list[dict[str, Any]]] = {problem_id: [] for problem_id in problem_ids}

    for submission in submissions:
        if submission.get("contest_id") != contest_id:
            continue
        problem_id_value = submission.get("problem_id")
        if not isinstance(problem_id_value, str):
            continue
        epoch_second = int_or_none(submission.get("epoch_second"))
        if epoch_second is None or epoch_second < start:
            continue
        if end is not None and epoch_second > end:
            continue
        by_problem.setdefault(problem_id_value, []).append(submission)

    if not any(by_problem.values()):
        raise AtCoderResultsError(
            f"No contest submissions found for {user!r} in contest {contest_id}."
        )

    normalized_problems: list[dict[str, Any]] = []
    for problem_id_value in problem_ids:
        wrong_attempts = 0
        accepted_at: int | None = None

        for submission in sorted(
            by_problem.get(problem_id_value, []),
            key=lambda item: item.get("epoch_second", 0),
        ):
            if accepted_at is not None:
                break
            result = submission.get("result")
            epoch_second = int_or_none(submission.get("epoch_second"))
            if result == "AC":
                accepted_at = max(0, epoch_second - start) if epoch_second is not None else None
            elif result not in (None, "WJ", "IE"):
                wrong_attempts += 1

        normalized_problems.append(
            {
                "problem_id": problem_label(problem_id_value, contest_id),
                "wrong_attempts": wrong_attempts,
                "accepted_at_seconds": accepted_at,
            }
        )

    return {
        "platform": "atcoder",
        "user": user,
        "participated": True,
        "contest": {
            "contest_id": contest_id,
            "contest_name": contest_name(contest_id, contest_info),
            "url": f"{ATCODER_CONTEST_BASE}/{contest_id}",
        },
        "problems": normalized_problems,
        "source": source,
        "fetched_at_unix": int(time.time()),
    }


def fetch_standings_result(args: argparse.Namespace) -> dict[str, Any]:
    contest_info = find_contest_info(args.contest_id, args)
    standings_data = load_url(standings_url(args.contest_id), args)
    standings = standings_data.get("result")
    if not isinstance(standings, dict):
        raise AtCoderResultsError("AtCoder standings JSON returned an unexpected payload.")

    return normalized_from_standings(
        user=args.user,
        contest_id=args.contest_id,
        contest_info=contest_info,
        standings=standings,
        source={
            "standings": "atcoder.standings.json",
            "submissions": None,
            "contest_metadata": "kenkoooo.resources.contests" if contest_info else None,
        },
    )


def fetch_kenkoooo_submissions_result(args: argparse.Namespace) -> dict[str, Any]:
    contest_info = find_contest_info(args.contest_id, args)
    start, _ = contest_time_window(args.contest_id, contest_info)
    problem_ids = contest_problem_ids(args.contest_id, args)
    submissions_data = load_url(submissions_url(args.user, start), args)
    submissions = submissions_data.get("result")
    if not isinstance(submissions, list):
        raise AtCoderResultsError("Kenkoooo user submissions returned an unexpected payload.")

    return normalized_from_kenkoooo_submissions(
        user=args.user,
        contest_id=args.contest_id,
        contest_info=contest_info,
        problem_ids=problem_ids,
        submissions=[item for item in submissions if isinstance(item, dict)],
        source={
            "standings": None,
            "submissions": "kenkoooo.user.submissions",
            "contest_metadata": "kenkoooo.resources.contests",
            "contest_problem_metadata": "kenkoooo.resources.contest-problem",
        },
    )


def get_contest_result(args: argparse.Namespace) -> dict[str, Any]:
    if args.source == "standings":
        return fetch_standings_result(args)
    if args.source == "kenkoooo-submissions":
        return fetch_kenkoooo_submissions_result(args)
    raise AtCoderResultsError(f"Unknown source: {args.source}")


def fetch_contest_result(args: argparse.Namespace) -> int:
    output_json(get_contest_result(args), args.output)
    return 0


def add_common_fetch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=atcoder_metadata.default_cache_dir() / "results",
        help="Directory for cached AtCoder result API responses.",
    )
    parser.add_argument(
        "--metadata-cache-dir",
        type=Path,
        default=atcoder_metadata.default_cache_dir(),
        help="Directory for cached Kenkoooo metadata responses.",
    )
    parser.add_argument(
        "--max-age",
        type=int,
        default=atcoder_metadata.DEFAULT_MAX_AGE_SECONDS,
        help="Cache max age in seconds. Use 0 with --refresh for a fresh fetch.",
    )
    parser.add_argument("--refresh", action="store_true", help="Ignore cache and fetch fresh data.")
    parser.add_argument("--no-cache", action="store_true", help="Do not read or write cache.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=atcoder_metadata.DEFAULT_TIMEOUT_SECONDS,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument("--output", type=Path, help="Write JSON output to this file instead of stdout.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch one user's AtCoder contest wrong attempts and accepted times."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    contest = subparsers.add_parser("contest", help="Fetch one user's contest problem results.")
    add_common_fetch_args(contest)
    contest.add_argument("--contest-id", required=True, help="AtCoder contest ID, for example abc422.")
    contest.add_argument("--user", required=True, help="AtCoder user ID.")
    contest.add_argument(
        "--source",
        choices=("standings", "kenkoooo-submissions"),
        default="standings",
        help="Result source. standings uses AtCoder standings JSON; kenkoooo-submissions computes from user submissions.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "contest":
            return fetch_contest_result(args)
        parser.error(f"Unknown command: {args.command}")
    except (AtCoderResultsError, atcoder_metadata.AtCoderMetadataError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return getattr(exc, "returncode", 1)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
