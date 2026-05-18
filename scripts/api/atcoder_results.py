#!/usr/bin/env python3
"""Fetch and normalize one user's AtCoder contest problem results."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from . import atcoder_metadata, atcoder_user_history, http_support
except ImportError:
    import atcoder_metadata
    import atcoder_user_history
    import http_support


ATCODER_CONTEST_BASE = "https://atcoder.jp/contests"
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
        stdout_buffer = getattr(sys.stdout, "buffer", None)
        if stdout_buffer is not None:
            stdout_buffer.write(text.encode("utf-8"))
        else:
            sys.stdout.write(text)


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


def normalized_not_participated(
    *,
    user: str,
    contest_id: str,
    contest_info: dict[str, Any] | None,
    source: dict[str, Any],
) -> dict[str, Any]:
    return {
        "platform": "atcoder",
        "user": user,
        "participated": False,
        "contest": {
            "contest_id": contest_id,
            "contest_name": contest_name(contest_id, contest_info),
            "url": f"{ATCODER_CONTEST_BASE}/{contest_id}",
        },
        "problems": [],
        "source": source,
        "fetched_at_unix": int(time.time()),
    }


def load_participation_history(args: argparse.Namespace) -> dict[str, Any] | None:
    if args.no_history_filter:
        return None

    try:
        return atcoder_user_history.load_normalized_history(
            user=args.user,
            cache_dir=args.history_cache_dir.expanduser().resolve(),
            max_age_seconds=args.history_max_age,
            refresh=args.refresh,
            no_cache=args.no_cache,
            timeout=args.timeout,
            contest_id=args.contest_id,
        )
    except atcoder_user_history.AtCoderUserHistoryError as exc:
        message = f"AtCoder user history fetch failed; falling back to standings: {exc}"
        if args.require_history:
            raise AtCoderResultsError(message) from exc
        print(f"warning: {message}", file=sys.stderr)
        return None


def fetch_standings_result(args: argparse.Namespace) -> dict[str, Any]:
    contest_info = find_contest_info(args.contest_id, args)
    history = load_participation_history(args)
    history_source = "atcoder.user.history.json" if history is not None else None
    if history is not None and history.get("participated") is False:
        return normalized_not_participated(
            user=args.user,
            contest_id=args.contest_id,
            contest_info=contest_info,
            source={
                "participation_history": history_source,
                "standings": None,
                "submissions": None,
                "contest_metadata": "atcoder.metadata.contests" if contest_info else None,
            },
        )

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
            "participation_history": history_source,
            "standings": "atcoder.standings.json",
            "submissions": None,
            "contest_metadata": "atcoder.metadata.contests" if contest_info else None,
        },
    )


def get_contest_result(args: argparse.Namespace) -> dict[str, Any]:
    if args.source == "standings":
        return fetch_standings_result(args)
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
        help="Directory for cached AtCoder metadata responses.",
    )
    parser.add_argument(
        "--history-cache-dir",
        type=Path,
        default=atcoder_user_history.default_cache_dir(),
        help="Directory for cached AtCoder user history responses.",
    )
    parser.add_argument(
        "--history-max-age",
        type=int,
        default=atcoder_user_history.DEFAULT_MAX_AGE_SECONDS,
        help="AtCoder user history cache max age in seconds. Defaults to 1 day.",
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
        choices=("standings",),
        default="standings",
        help="Result source. standings uses AtCoder standings JSON.",
    )
    contest.add_argument(
        "--no-history-filter",
        action="store_true",
        help="Do not check AtCoder user history before fetching standings.",
    )
    contest.add_argument(
        "--require-history",
        action="store_true",
        help="Fail instead of falling back to standings when user history cannot be fetched.",
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
