#!/usr/bin/env python3
"""Fetch and normalize one user's AtCoder contest participation history."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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


ATCODER_USER_BASE = "https://atcoder.jp/users"
DEFAULT_MAX_AGE_SECONDS = 24 * 60 * 60
USER_AGENT = "cp-publish/0.1"


class AtCoderUserHistoryError(RuntimeError):
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


def user_history_url(user: str) -> str:
    encoded_user = urllib.parse.quote(user.strip(), safe="")
    return f"{ATCODER_USER_BASE}/{encoded_user}/history/json"


def cache_path(cache_dir: Path, url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return cache_dir / f"atcoder-user-history-{digest}.json"


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
        raise AtCoderUserHistoryError(f"AtCoder user history HTTP {exc.code}: {url}") from exc
    except urllib.error.URLError as exc:
        raise AtCoderUserHistoryError(
            f"Failed to reach AtCoder user history: {http_support.format_url_error(exc)}"
        ) from exc
    except TimeoutError as exc:
        raise AtCoderUserHistoryError("Timed out while fetching AtCoder user history.") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AtCoderUserHistoryError(f"AtCoder user history returned invalid JSON: {url}") from exc

    return {
        "source": "api",
        "url": url,
        "fetched_at_unix": int(time.time()),
        "result": payload,
    }


def load_user_history(
    *,
    user: str,
    cache_dir: Path,
    max_age_seconds: int,
    refresh: bool,
    no_cache: bool,
    timeout: int,
) -> dict[str, Any]:
    url = user_history_url(user)
    path = cache_path(cache_dir.expanduser().resolve(), url)

    if not refresh and not no_cache:
        cached = read_cache(path, max_age_seconds)
        if cached is not None:
            return cached

    data = fetch_json(url, timeout)
    if not no_cache:
        write_cache(path, data)
    return data


def int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def normalize_contest_id(value: str) -> str | None:
    cleaned = value.strip().lower()
    if not cleaned:
        return None
    suffix = ".contest.atcoder.jp"
    if cleaned.endswith(suffix):
        cleaned = cleaned[: -len(suffix)]
    if cleaned.startswith("https://atcoder.jp/contests/"):
        cleaned = cleaned.rsplit("/", 1)[-1]
    return cleaned or None


def contest_id_from_entry(entry: dict[str, Any]) -> str | None:
    for key in ("ContestScreenName", "ContestId", "ContestID"):
        value = string_or_none(entry.get(key))
        if value:
            return normalize_contest_id(value)
    return None


def normalize_history_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    contest_id = contest_id_from_entry(entry)
    if not contest_id:
        return None

    old_rating = int_or_none(entry.get("OldRating"))
    new_rating = int_or_none(entry.get("NewRating"))
    diff = new_rating - old_rating if old_rating is not None and new_rating is not None else None

    return {
        "contest_id": contest_id,
        "contest_name": string_or_none(entry.get("ContestName")),
        "rank": int_or_none(entry.get("Place")),
        "performance": int_or_none(entry.get("Performance")),
        "old_rating": old_rating,
        "new_rating": new_rating,
        "diff": diff,
        "is_rated": entry.get("IsRated") if isinstance(entry.get("IsRated"), bool) else None,
        "end_time": string_or_none(entry.get("EndTime")),
    }


def normalize_contest_filter(value: str | None) -> str | None:
    if value is None:
        return None
    return normalize_contest_id(value)


def find_contest(contests: list[dict[str, Any]], contest_id: str) -> dict[str, Any] | None:
    wanted = normalize_contest_filter(contest_id)
    if wanted is None:
        return None
    for contest in contests:
        if contest.get("contest_id") == wanted:
            return contest
    return None


def normalize_history(
    *,
    user: str,
    data: dict[str, Any],
    contest_id: str | None = None,
) -> dict[str, Any]:
    payload = data.get("result")
    if not isinstance(payload, list):
        raise AtCoderUserHistoryError("AtCoder user history returned an unexpected payload.")

    contests = [
        contest
        for entry in payload
        if isinstance(entry, dict)
        for contest in [normalize_history_entry(entry)]
        if contest is not None
    ]

    normalized = {
        "platform": "atcoder",
        "user": user,
        "contest_count": len(contests),
        "contest_ids": [contest["contest_id"] for contest in contests],
        "contests": contests,
        "source": {
            "history": "atcoder.user.history.json",
            "url": data.get("url"),
            "cache": data.get("source") == "cache",
        },
        "fetched_at_unix": data.get("fetched_at_unix") or int(time.time()),
    }

    wanted = normalize_contest_filter(contest_id)
    if wanted is not None:
        contest = find_contest(contests, wanted)
        normalized.update(
            {
                "contest_id": wanted,
                "participated": contest is not None,
                "contest": contest,
            }
        )

    return normalized


def load_normalized_history(
    *,
    user: str,
    cache_dir: Path,
    max_age_seconds: int,
    refresh: bool,
    no_cache: bool,
    timeout: int,
    contest_id: str | None = None,
) -> dict[str, Any]:
    data = load_user_history(
        user=user,
        cache_dir=cache_dir,
        max_age_seconds=max_age_seconds,
        refresh=refresh,
        no_cache=no_cache,
        timeout=timeout,
    )
    return normalize_history(user=user, data=data, contest_id=contest_id)


def default_cache_dir() -> Path:
    return atcoder_metadata.default_cache_dir() / "history"


def safe_user(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise argparse.ArgumentTypeError("user must not be empty.")
    if re.search(r"[\r\n/\\]", cleaned):
        raise argparse.ArgumentTypeError("user contains unsupported path or newline characters.")
    return cleaned


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch one user's AtCoder contest history.")
    parser.add_argument("--user", required=True, type=safe_user, help="AtCoder user ID.")
    parser.add_argument(
        "--contest-id",
        help="Optional contest ID to check. Adds participated=true/false to the output.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=default_cache_dir(),
        help="Directory for cached AtCoder user history responses.",
    )
    parser.add_argument(
        "--max-age",
        type=int,
        default=DEFAULT_MAX_AGE_SECONDS,
        help="Cache max age in seconds. Defaults to 1 day. Use 0 with --refresh for a fresh fetch.",
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = load_normalized_history(
            user=args.user,
            cache_dir=args.cache_dir,
            max_age_seconds=args.max_age,
            refresh=args.refresh,
            no_cache=args.no_cache,
            timeout=args.timeout,
            contest_id=args.contest_id,
        )
        output_json(result, args.output)
    except AtCoderUserHistoryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
