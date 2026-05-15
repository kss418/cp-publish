#!/usr/bin/env python3
"""Fetch AtCoder metadata from kenkoooo AtCoder Problems resources."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import http_support


RESOURCE_BASE = "https://kenkoooo.com/atcoder/resources"
DEFAULT_MAX_AGE_SECONDS = 24 * 60 * 60
DEFAULT_TIMEOUT_SECONDS = 20
MIN_API_INTERVAL_SECONDS = 1.1
USER_AGENT = "cp-publish/0.1"

RESOURCES = {
    "contests": "contests.json",
    "problems": "problems.json",
    "merged-problems": "merged-problems.json",
    "contest-problems": "contest-problem.json",
    "ratings": "problem-models.json",
}


class AtCoderMetadataError(RuntimeError):
    def __init__(self, message: str, returncode: int = 1) -> None:
        super().__init__(message)
        self.returncode = returncode


def default_cache_dir() -> Path:
    if platform.system() == "Windows":
        local_appdata = os.environ.get("LOCALAPPDATA")
        base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
        return base / "cp-publish" / "atcoder"

    xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg_cache_home).expanduser() if xdg_cache_home else Path.home() / ".cache"
    return base / "cp-publish" / "atcoder"


def cache_path(cache_dir: Path, resource: str) -> Path:
    return cache_dir / f"{resource}.json"


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


def resource_url(resource: str) -> str:
    filename = RESOURCES[resource]
    return f"{RESOURCE_BASE}/{filename}"


def fetch_resource(resource: str, timeout: int) -> dict[str, Any]:
    url = resource_url(resource)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with http_support.open_url(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise AtCoderMetadataError(f"AtCoder metadata HTTP {exc.code}: {url}") from exc
    except urllib.error.URLError as exc:
        raise AtCoderMetadataError(
            f"Failed to reach AtCoder metadata: {http_support.format_url_error(exc)}"
        ) from exc
    except TimeoutError as exc:
        raise AtCoderMetadataError("Timed out while fetching AtCoder metadata.") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AtCoderMetadataError(f"AtCoder metadata returned invalid JSON: {resource}") from exc

    return {
        "source": "api",
        "resource": resource,
        "url": url,
        "fetched_at_unix": int(time.time()),
        "result": payload,
    }


def load_resource(
    resource: str,
    *,
    cache_dir: Path,
    max_age_seconds: int,
    refresh: bool,
    no_cache: bool,
    timeout: int,
) -> dict[str, Any]:
    path = cache_path(cache_dir, resource)

    if not refresh and not no_cache:
        cached = read_cache(path, max_age_seconds)
        if cached is not None:
            return cached

    data = fetch_resource(resource, timeout)
    if not no_cache:
        write_cache(path, data)
    return data


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


def fetch_one(args: argparse.Namespace, resource: str) -> int:
    data = load_resource(resource, **common_fetch_kwargs(args))
    output_json(data, args.output)
    return 0


def fetch_all(args: argparse.Namespace) -> int:
    kwargs = common_fetch_kwargs(args)
    results: dict[str, dict[str, Any]] = {}
    last_api_fetch = False

    for resource in RESOURCES:
        if last_api_fetch:
            time.sleep(MIN_API_INTERVAL_SECONDS)
        data = load_resource(resource, **kwargs)
        results[resource] = data
        last_api_fetch = data.get("source") == "api"

    output_json(
        {
            "source": {name: data["source"] for name, data in results.items()},
            "fetched_at_unix": int(time.time()),
            "resources": results,
        },
        args.output,
    )
    return 0


def problem_id_value(problem: Any) -> str | None:
    if not isinstance(problem, dict):
        return None
    value = problem.get("id")
    return value if isinstance(value, str) else None


def problem_title(problem: Any) -> str | None:
    if not isinstance(problem, dict):
        return None
    for key in ("title", "name"):
        value = problem.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def find_problem(problems: Any, problem_id: str) -> dict[str, Any] | None:
    if not isinstance(problems, list):
        return None
    for problem in problems:
        if problem_id_value(problem) == problem_id:
            return problem
    return None


def extract_difficulty(model: Any) -> int | None:
    if not isinstance(model, dict):
        return None

    difficulty = model.get("difficulty")
    if difficulty is None:
        return None

    try:
        return round(float(difficulty))
    except (TypeError, ValueError):
        return None


def lookup_rating(args: argparse.Namespace) -> int:
    data = load_resource("ratings", **common_fetch_kwargs(args))
    models = data.get("result")
    if not isinstance(models, dict):
        raise AtCoderMetadataError("problem-models.json did not contain an object.")

    model = models.get(args.problem_id)
    difficulty = extract_difficulty(model)
    result = {
        "problem_id": args.problem_id,
        "rating": difficulty,
        "rating_markdown": f"${difficulty}$" if difficulty is not None else "$-$",
        "model": model,
        "metadata_source": data["source"],
        "fetched_at_unix": data["fetched_at_unix"],
    }
    output_json(result, args.output)
    return 0


def lookup_problem(args: argparse.Namespace) -> int:
    kwargs = common_fetch_kwargs(args)
    problems_data = load_resource("problems", **kwargs)
    problem = find_problem(problems_data.get("result"), args.problem_id)

    merged_problem = None
    merged_data = None
    needs_merged = args.include_merged or problem_title(problem) is None
    if needs_merged:
        if problems_data.get("source") == "api":
            time.sleep(MIN_API_INTERVAL_SECONDS)
        merged_data = load_resource("merged-problems", **kwargs)
        merged_problem = find_problem(merged_data.get("result"), args.problem_id)

    ratings_data = None
    rating_value = None
    rating_markdown = "$-$"
    if args.include_rating:
        if problems_data.get("source") == "api" or (
            merged_data is not None and merged_data.get("source") == "api"
        ):
            time.sleep(MIN_API_INTERVAL_SECONDS)
        ratings_data = load_resource("ratings", **kwargs)
        models = ratings_data.get("result")
        if isinstance(models, dict):
            rating_value = extract_difficulty(models.get(args.problem_id))
            if rating_value is not None:
                rating_markdown = f"${rating_value}$"

    title = problem_title(problem) or problem_title(merged_problem)
    result = {
        "problem_id": args.problem_id,
        "title": title,
        "rating": rating_value,
        "rating_markdown": rating_markdown,
        "problem": problem,
        "merged_problem": merged_problem,
        "metadata_source": {
            "problems": problems_data["source"],
            "merged-problems": merged_data["source"] if merged_data else None,
            "ratings": ratings_data["source"] if ratings_data else None,
        },
        "fetched_at_unix": int(time.time()),
    }
    output_json(result, args.output)
    return 0


def add_common_fetch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=default_cache_dir(),
        help="Directory for cached AtCoder metadata responses.",
    )
    parser.add_argument(
        "--max-age",
        type=int,
        default=DEFAULT_MAX_AGE_SECONDS,
        help="Cache max age in seconds. Use 0 with --refresh for a fresh fetch.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Ignore cache and fetch from kenkoooo.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Do not read or write cache.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write JSON output to this file instead of stdout.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch AtCoder contest, problem title, mapping, and estimated rating metadata."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    contests = subparsers.add_parser("contests", help="Fetch contests.json.")
    add_common_fetch_args(contests)

    problems = subparsers.add_parser("problems", help="Fetch problems.json.")
    add_common_fetch_args(problems)

    merged_problems = subparsers.add_parser(
        "merged-problems", help="Fetch merged-problems.json."
    )
    add_common_fetch_args(merged_problems)

    contest_problems = subparsers.add_parser(
        "contest-problems", help="Fetch contest-problem.json."
    )
    add_common_fetch_args(contest_problems)

    ratings = subparsers.add_parser("ratings", help="Fetch problem-models.json.")
    add_common_fetch_args(ratings)

    rating = subparsers.add_parser(
        "rating", help="Look up estimated difficulty for one AtCoder problem ID."
    )
    add_common_fetch_args(rating)
    rating.add_argument("problem_id", help="AtCoder problem ID, for example abc422_a.")

    problem = subparsers.add_parser(
        "problem", help="Look up title and optional estimated rating for one problem ID."
    )
    add_common_fetch_args(problem)
    problem.add_argument("problem_id", help="AtCoder problem ID, for example abc422_a.")
    problem.add_argument(
        "--include-merged",
        action="store_true",
        help="Always search merged-problems.json. It is also used automatically if problems.json has no title.",
    )
    problem.add_argument(
        "--no-rating",
        dest="include_rating",
        action="store_false",
        help="Do not look up problem-models.json.",
    )
    problem.set_defaults(include_rating=True)

    all_parser = subparsers.add_parser(
        "all",
        help="Fetch contests, problems, merged problems, contest-problem mapping, and estimated ratings.",
    )
    add_common_fetch_args(all_parser)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "contests":
            return fetch_one(args, "contests")
        if args.command == "problems":
            return fetch_one(args, "problems")
        if args.command == "merged-problems":
            return fetch_one(args, "merged-problems")
        if args.command == "contest-problems":
            return fetch_one(args, "contest-problems")
        if args.command == "ratings":
            return fetch_one(args, "ratings")
        if args.command == "rating":
            return lookup_rating(args)
        if args.command == "problem":
            return lookup_problem(args)
        if args.command == "all":
            return fetch_all(args)
        parser.error(f"Unknown command: {args.command}")
    except AtCoderMetadataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
