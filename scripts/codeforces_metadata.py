#!/usr/bin/env python3
"""Fetch Codeforces contest and problemset metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import http_support


API_BASE = "https://codeforces.com/api"
DEFAULT_MAX_AGE_SECONDS = 24 * 60 * 60
DEFAULT_TIMEOUT_SECONDS = 20
USER_AGENT = "cp-publish/0.1"


class CodeforcesApiError(RuntimeError):
    def __init__(self, message: str, returncode: int = 1) -> None:
        super().__init__(message)
        self.returncode = returncode


def default_cache_dir() -> Path:
    if platform.system() == "Windows":
        local_appdata = os.environ.get("LOCALAPPDATA")
        base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
        return base / "cp-publish" / "codeforces"

    xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg_cache_home).expanduser() if xdg_cache_home else Path.home() / ".cache"
    return base / "cp-publish" / "codeforces"


def normalized_params(params: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            result[key] = "true" if value else "false"
        else:
            result[key] = str(value)
    return result


def cache_path(cache_dir: Path, method: str, params: dict[str, str]) -> Path:
    payload = json.dumps(
        {"method": method, "params": params}, sort_keys=True, separators=(",", ":")
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    filename = f"{method.replace('.', '-')}-{digest}.json"
    return cache_dir / filename


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


def api_url(method: str, params: dict[str, str]) -> str:
    query = urllib.parse.urlencode(params)
    url = f"{API_BASE}/{method}"
    return f"{url}?{query}" if query else url


def fetch_api(method: str, params: dict[str, str], timeout: int) -> dict[str, Any]:
    url = api_url(method, params)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with http_support.open_url(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise CodeforcesApiError(f"Codeforces API HTTP {exc.code}: {url}") from exc
    except urllib.error.URLError as exc:
        raise CodeforcesApiError(
            f"Failed to reach Codeforces API: {http_support.format_url_error(exc)}"
        ) from exc
    except TimeoutError as exc:
        raise CodeforcesApiError("Timed out while calling Codeforces API.") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise CodeforcesApiError("Codeforces API returned invalid JSON.") from exc

    status = payload.get("status")
    if status != "OK":
        comment = payload.get("comment") or "no error comment"
        raise CodeforcesApiError(f"Codeforces API returned status {status}: {comment}")

    return {
        "source": "api",
        "method": method,
        "params": params,
        "fetched_at_unix": int(time.time()),
        "result": payload.get("result"),
    }


def load_method(
    method: str,
    params: dict[str, Any],
    *,
    cache_dir: Path,
    max_age_seconds: int,
    refresh: bool,
    no_cache: bool,
    timeout: int,
) -> dict[str, Any]:
    normalized = normalized_params(params)
    path = cache_path(cache_dir, method, normalized)

    if not refresh and not no_cache:
        cached = read_cache(path, max_age_seconds)
        if cached is not None:
            return cached

    data = fetch_api(method, normalized, timeout)
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


def fetch_contests(args: argparse.Namespace) -> int:
    params: dict[str, Any] = {
        "gym": True if args.gym else None,
        "groupCode": args.group_code,
    }
    data = load_method("contest.list", params, **common_fetch_kwargs(args))
    output_json(data, args.output)
    return 0


def fetch_problems(args: argparse.Namespace) -> int:
    tags = args.tags
    if args.tag:
        joined_tags = ";".join(args.tag)
        tags = f"{tags};{joined_tags}" if tags else joined_tags

    params: dict[str, Any] = {
        "tags": tags,
        "problemsetName": args.problemset_name,
    }
    data = load_method("problemset.problems", params, **common_fetch_kwargs(args))
    output_json(data, args.output)
    return 0


def fetch_all(args: argparse.Namespace) -> int:
    kwargs = common_fetch_kwargs(args)
    contests = load_method("contest.list", {}, **kwargs)
    problems = load_method("problemset.problems", {}, **kwargs)
    data = {
        "source": {
            "contest.list": contests["source"],
            "problemset.problems": problems["source"],
        },
        "fetched_at_unix": int(time.time()),
        "contest_list": contests,
        "problemset_problems": problems,
    }
    output_json(data, args.output)
    return 0


def add_common_fetch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=default_cache_dir(),
        help="Directory for cached API responses.",
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
        help="Ignore cache and fetch from Codeforces.",
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
        description="Fetch Codeforces contest.list and problemset.problems metadata."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    contests = subparsers.add_parser("contests", help="Fetch contest.list.")
    add_common_fetch_args(contests)
    contests.add_argument("--gym", action="store_true", help="Fetch gym contests.")
    contests.add_argument("--group-code", help="Fetch contests for a Codeforces group.")

    problems = subparsers.add_parser("problems", help="Fetch problemset.problems.")
    add_common_fetch_args(problems)
    problems.add_argument(
        "--tags", help="Semicolon-separated Codeforces tags, for example 'dp;math'."
    )
    problems.add_argument(
        "--tag",
        action="append",
        help="Single tag. Can be repeated and combined with --tags.",
    )
    problems.add_argument(
        "--problemset-name",
        help="Custom problemset short name, for example 'acmsguru'.",
    )

    all_parser = subparsers.add_parser(
        "all", help="Fetch regular contest.list and problemset.problems."
    )
    add_common_fetch_args(all_parser)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "contests":
            return fetch_contests(args)
        if args.command == "problems":
            return fetch_problems(args)
        if args.command == "all":
            return fetch_all(args)
        parser.error(f"Unknown command: {args.command}")
    except CodeforcesApiError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
