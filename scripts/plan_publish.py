#!/usr/bin/env python3
"""Build a dry-run publish plan for a competitive programming solution.

This script does not move files, update README files, commit, or push. It
combines solution detection, configured repository routing, path rules, and
available metadata into a JSON plan that another workflow can review or execute.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import configure_repos


SUPPORTED_PLATFORMS = {"atcoder", "codeforces"}
WEAK_FILE_STEMS = {"a", "b", "c", "d", "e", "f", "g", "h", "main", "solution", "solve"}
SOURCE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".go",
    ".java",
    ".js",
    ".kt",
    ".kts",
    ".py",
    ".py3",
    ".rs",
}
EXTENSION_ALIASES = {
    ".cc": ".cpp",
    ".cxx": ".cpp",
    ".py3": ".py",
    ".kts": ".kt",
}
ATCODER_NUMERIC_SERIES = {"abc", "arc", "agc", "ahc"}
TAG_MAP_PATH = Path(__file__).resolve().parent.parent / "references" / "solvedac-tag-map.json"


class PlanError(Exception):
    """A recoverable issue that should be reported as a JSON planning error."""


@dataclass
class Detection:
    platform: str | None = None
    contest_id: str | None = None
    problem_id: str | None = None
    problem_title: str | None = None
    contest_kind: str | None = None
    contest_title: str | None = None
    evidence: list[str] = field(default_factory=list)
    confidence: str = "none"


@dataclass
class Route:
    repo_path: Path
    base_dir: str
    target_base: Path
    user_id: str | None
    warnings: list[str]


@dataclass
class CodeforcesTarget:
    contest_id: str
    problem_id: str
    contest_kind: str | None = None
    contest_title: str | None = None
    round_number: str | None = None
    contest_group: str | None = None


def normalize_ext(path: Path) -> str:
    ext = path.suffix.lower()
    return EXTENSION_ALIASES.get(ext, ext)


def normalize_atcoder_problem_id(problem_id: str) -> str:
    lowered = problem_id.strip().lower()
    if lowered == "ex":
        return "Ex"
    return lowered.upper()


def normalize_codeforces_problem_id(problem_id: str) -> str:
    return problem_id.strip().upper()


def normalize_codeforces_kind(value: str) -> str:
    lowered = value.strip().lower()
    if lowered == "regular":
        return "regular"
    if lowered == "educational":
        return "Educational"
    if lowered in {"other", "others"}:
        return "Others"
    raise argparse.ArgumentTypeError("contest kind must be regular, Educational, or Others")


def normalize_codeforces_round_number(value: str) -> str:
    cleaned = value.strip()
    if not re.fullmatch(r"\d+", cleaned):
        raise argparse.ArgumentTypeError("Codeforces round number must be a positive integer")
    number = int(cleaned)
    if number <= 0:
        raise argparse.ArgumentTypeError("Codeforces round number must be a positive integer")
    return str(number)


def normalize_codeforces_contest_group(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise argparse.ArgumentTypeError("Codeforces contest group must not be empty")
    cleaned = re.sub(r"[\\/:*?\"<>|]", "", cleaned)
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        raise argparse.ArgumentTypeError("Codeforces contest group must contain letters or digits")
    return cleaned


def rating_markdown(value: Any) -> str:
    if value is None:
        return "$-$"
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned in {"", "-", "$-$"}:
            return "$-$"
        if cleaned.startswith("$") and cleaned.endswith("$"):
            return cleaned
        if re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned):
            return f"${cleaned}$"
        return cleaned
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            return f"${int(value)}$"
        return f"${value}$"
    return "$-$"


def safe_title_slug(title: str | None) -> str | None:
    if not title:
        return None
    slug = re.sub(r"[\\/:*?\"<>|]", "", title.strip())
    slug = re.sub(r"\s+", "_", slug)
    slug = re.sub(r"_+", "_", slug).strip("._ ")
    return slug or None


def load_tag_map() -> dict[str, str]:
    try:
        payload = json.loads(TAG_MAP_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanError(f"Could not load README tag map: {TAG_MAP_PATH}") from exc

    tags = payload.get("tags")
    if not isinstance(tags, dict):
        raise PlanError(f"README tag map has no tags object: {TAG_MAP_PATH}")

    result: dict[str, str] = {}
    for key, value in tags.items():
        if isinstance(key, str) and isinstance(value, str) and key and value:
            result[key] = value
    if not result:
        raise PlanError(f"README tag map is empty: {TAG_MAP_PATH}")
    return result


def normalize_tag_key(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "_", lowered)
    return re.sub(r"_+", "_", lowered).strip("_")


def normalize_readme_tag(value: str, tag_map: dict[str, str]) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise PlanError("README tag must not be empty.")

    allowed_values = set(tag_map.values())
    if cleaned in allowed_values:
        return cleaned

    key = normalize_tag_key(cleaned)
    if key in tag_map:
        return tag_map[key]

    raise PlanError(
        f"Unsupported README tag: {cleaned}. "
        "Use a tag name or solved.ac key from references/solvedac-tag-map.json."
    )


def read_source_text(path: Path, max_bytes: int = 200_000) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            return handle.read(max_bytes)
    except OSError:
        return ""


def atcoder_problem_from_task_id(contest_id: str, task_id: str) -> str:
    lowered_task = task_id.lower()
    lowered_contest = contest_id.lower()
    prefix = lowered_contest + "_"
    if lowered_task.startswith(prefix):
        return lowered_task[len(prefix) :]
    parts = lowered_task.rsplit("_", 1)
    if len(parts) == 2:
        return parts[1]
    return lowered_task


def detect_from_text(text: str) -> Detection:
    detection = Detection()

    atcoder_url = re.search(
        r"https?://atcoder\.jp/contests/([A-Za-z0-9_-]+)/tasks/([A-Za-z0-9_-]+)",
        text,
    )
    if atcoder_url:
        contest_id = atcoder_url.group(1).lower()
        task_id = atcoder_url.group(2).lower()
        detection.platform = "atcoder"
        detection.contest_id = contest_id
        detection.problem_id = atcoder_problem_from_task_id(contest_id, task_id)
        detection.evidence.append(f"AtCoder task URL: {atcoder_url.group(0)}")
        detection.confidence = "high"
        return detection

    cf_patterns = [
        r"https?://codeforces\.com/problemset/problem/(\d+)/([A-Za-z0-9]+)",
        r"https?://codeforces\.com/contest/(\d+)/problem/([A-Za-z0-9]+)",
        r"https?://codeforces\.com/gym/(\d+)/problem/([A-Za-z0-9]+)",
    ]
    for pattern in cf_patterns:
        match = re.search(pattern, text)
        if match:
            detection.platform = "codeforces"
            detection.contest_id = match.group(1)
            detection.problem_id = match.group(2)
            detection.evidence.append(f"Codeforces problem URL: {match.group(0)}")
            detection.confidence = "high"
            return detection

    metadata: dict[str, str] = {}
    metadata_keys = {
        "platform": "platform",
        "judge": "platform",
        "contest": "contest_id",
        "contest_id": "contest_id",
        "problem": "problem_id",
        "problem_id": "problem_id",
        "index": "problem_id",
        "title": "problem_title",
        "problem_title": "problem_title",
    }
    for raw_line in text.splitlines()[:120]:
        line = raw_line.strip()
        if line.startswith("//"):
            content = line[2:].strip()
        elif line.startswith("#"):
            content = line[1:].strip()
        elif line.startswith("/*"):
            content = line[2:].strip()
        elif line.startswith("*"):
            content = line[1:].strip()
        else:
            continue
        match = re.fullmatch(r"([A-Za-z_]+)\s*:\s*(.+?)\s*", content)
        if not match:
            continue
        key = metadata_keys.get(match.group(1).lower())
        if key:
            metadata[key] = match.group(2).strip()

    if metadata:
        if metadata.get("platform") and metadata["platform"].lower() not in SUPPORTED_PLATFORMS:
            metadata.pop("platform")
        detection.platform = metadata.get("platform", detection.platform)
        detection.contest_id = metadata.get("contest_id", detection.contest_id)
        detection.problem_id = metadata.get("problem_id", detection.problem_id)
        detection.problem_title = metadata.get("problem_title", detection.problem_title)
        detection.evidence.append("Structured metadata comments")
        detection.confidence = "medium" if detection.contest_id and detection.problem_id else "low"

    return detection


def detect_from_filename(path: Path) -> Detection:
    stem = path.stem
    compact = re.sub(r"[^A-Za-z0-9]", "", stem).lower()
    detection = Detection()

    atcoder_match = re.fullmatch(r"(abc|arc|agc|ahc)(\d{2,4})([a-z][0-9]?|ex)", compact)
    if atcoder_match:
        detection.platform = "atcoder"
        detection.contest_id = f"{atcoder_match.group(1)}{int(atcoder_match.group(2)):03d}"
        detection.problem_id = atcoder_match.group(3)
        detection.evidence.append(f"AtCoder compact filename: {path.name}")
        detection.confidence = "medium"
        return detection

    atcoder_split = re.fullmatch(
        r"(abc|arc|agc|ahc)(\d{2,4})[_-]?([a-z][0-9]?|ex)",
        stem.lower(),
    )
    if atcoder_split:
        detection.platform = "atcoder"
        detection.contest_id = f"{atcoder_split.group(1)}{int(atcoder_split.group(2)):03d}"
        detection.problem_id = atcoder_split.group(3)
        detection.evidence.append(f"AtCoder filename: {path.name}")
        detection.confidence = "medium"
        return detection

    past_match = re.fullmatch(r"(past[0-9a-z_-]+)[_-]([a-z][0-9]?|ex)", stem.lower())
    if past_match:
        detection.platform = "atcoder"
        detection.contest_id = past_match.group(1)
        detection.problem_id = past_match.group(2)
        detection.evidence.append(f"AtCoder PAST filename: {path.name}")
        detection.confidence = "medium"
        return detection

    cf_match = re.fullmatch(r"(?:cf[_-]?)?(\d{3,5})[_-]?([A-Za-z][0-9]?)", stem)
    if cf_match:
        detection.platform = "codeforces"
        detection.contest_id = cf_match.group(1)
        detection.problem_id = cf_match.group(2)
        detection.evidence.append(f"Codeforces filename: {path.name}")
        detection.confidence = "medium"
        return detection

    if stem.lower() in WEAK_FILE_STEMS:
        detection.evidence.append(f"Weak filename only: {path.name}")
        detection.confidence = "low"

    return detection


def detect_from_path(path: Path) -> Detection:
    parts = [part.lower() for part in path.parts]
    detection = Detection()

    for idx, part in enumerate(parts):
        if part in ATCODER_NUMERIC_SERIES and idx + 3 < len(parts):
            contest_candidate = parts[idx + 3]
            if contest_candidate.isdigit():
                detection.platform = "atcoder"
                detection.contest_id = f"{part}{int(contest_candidate):03d}"
                detection.problem_id = path.stem.split("_", 1)[0].lower()
                detection.evidence.append("AtCoder path convention")
                detection.confidence = "medium"
                return detection
        if part == "past" and idx + 1 < len(parts):
            detection.platform = "atcoder"
            detection.contest_id = "past" + parts[idx + 1]
            detection.problem_id = path.stem.split("_", 1)[0].lower()
            detection.evidence.append("AtCoder PAST path convention")
            detection.confidence = "medium"
            return detection

    for idx, part in enumerate(parts):
        if part == "educational" and idx + 3 < len(parts) and parts[idx + 3].isdigit():
            detection.platform = "codeforces"
            detection.contest_kind = "Educational"
            detection.contest_id = parts[idx + 3]
            detection.problem_id = path.stem
            detection.evidence.append("Codeforces Educational path convention")
            detection.confidence = "medium"
            return detection
        if part == "others" and idx + 3 < len(parts) and parts[idx + 3].isdigit():
            detection.platform = "codeforces"
            detection.contest_kind = "Others"
            detection.contest_id = parts[idx + 3]
            detection.problem_id = path.stem
            detection.evidence.append("Codeforces Others path convention")
            detection.confidence = "medium"
            return detection

    numeric_parts = [part for part in parts if part.isdigit()]
    if len(numeric_parts) >= 3 and path.stem and re.fullmatch(r"[a-z][0-9]?", path.stem):
        detection.platform = "codeforces"
        detection.contest_id = numeric_parts[-1]
        detection.problem_id = path.stem
        detection.evidence.append("Codeforces numeric path convention")
        detection.confidence = "low"

    return detection


def merge_detection(base: Detection, incoming: Detection) -> Detection:
    confidence_rank = {"none": 0, "low": 1, "medium": 2, "high": 3}
    merged = Detection(
        platform=base.platform,
        contest_id=base.contest_id,
        problem_id=base.problem_id,
        problem_title=base.problem_title,
        contest_kind=base.contest_kind,
        contest_title=base.contest_title,
        evidence=[*base.evidence],
        confidence=base.confidence,
    )

    if confidence_rank[incoming.confidence] > confidence_rank[merged.confidence]:
        merged.confidence = incoming.confidence
    for attr in ("platform", "contest_id", "problem_id", "problem_title", "contest_kind", "contest_title"):
        current = getattr(merged, attr)
        value = getattr(incoming, attr)
        if not current and value:
            setattr(merged, attr, value)
    merged.evidence.extend(item for item in incoming.evidence if item not in merged.evidence)
    return merged


def detect_solution(path: Path) -> Detection:
    text_detection = detect_from_text(read_source_text(path))
    filename_detection = detect_from_filename(path)
    path_detection = detect_from_path(path)
    return merge_detection(merge_detection(text_detection, filename_detection), path_detection)


def apply_overrides(detection: Detection, args: argparse.Namespace) -> Detection:
    overridden = Detection(
        platform=detection.platform,
        contest_id=detection.contest_id,
        problem_id=detection.problem_id,
        problem_title=detection.problem_title,
        contest_kind=detection.contest_kind,
        contest_title=detection.contest_title,
        evidence=[*detection.evidence],
        confidence=detection.confidence,
    )
    overrides = {
        "platform": args.platform,
        "contest_id": args.contest_id,
        "problem_id": args.problem_id,
        "problem_title": args.problem_title,
        "contest_kind": args.contest_kind,
        "contest_title": args.contest_title,
    }
    for attr, value in overrides.items():
        if value:
            old = getattr(overridden, attr)
            setattr(overridden, attr, value)
            if old and old != value:
                overridden.evidence.append(f"CLI override changed {attr}: {old} -> {value}")
            else:
                overridden.evidence.append(f"CLI override set {attr}: {value}")
    if args.platform and args.contest_id and args.problem_id:
        overridden.confidence = "high"
    elif args.contest_id and args.problem_id and overridden.confidence == "none":
        overridden.confidence = "medium"
    return overridden


def load_route(platform: str, config_path: str | None) -> Route:
    path = Path(config_path).expanduser() if config_path else configure_repos.default_config_path()
    try:
        config = configure_repos.read_config(path)
    except configure_repos.ConfigError as exc:
        raise PlanError(str(exc)) from exc

    errors, validation_warnings = configure_repos.validate_config(config)
    if errors:
        raise PlanError("; ".join(errors))

    route = (config.get("routes") or {}).get(platform)
    if not route:
        raise PlanError(
            f"No configured route for {platform}. Run scripts/configure_repos.py init --platform {platform} first."
        )

    repos = config.get("repositories") or {}
    users = config.get("users") or {}
    repo_name = route.get("repo")
    repo = repos.get(repo_name)
    if not repo:
        raise PlanError(f"Route for {platform} references missing repository {repo_name!r}.")

    repo_path = configure_repos.normalize_repo_path(repo.get("path", ""))
    base_dir = configure_repos.normalize_base_dir(route.get("base_dir", ""))
    target_base = repo_path / base_dir if base_dir else repo_path
    relevant_warnings = [
        warning
        for warning in validation_warnings
        if not warning.startswith("route ") or warning.startswith(f"route {platform} ")
    ]
    return Route(
        repo_path=repo_path,
        base_dir=base_dir,
        target_base=target_base,
        user_id=users.get(platform),
        warnings=relevant_warnings,
    )


def load_atcoder_metadata(no_metadata: bool, refresh: bool, warnings: list[str]) -> dict[str, Any]:
    if no_metadata:
        return {}
    try:
        import atcoder_metadata

        cache_dir = atcoder_metadata.default_cache_dir()
        fetch_kwargs = {
            "cache_dir": cache_dir,
            "max_age_seconds": atcoder_metadata.DEFAULT_MAX_AGE_SECONDS,
            "refresh": refresh,
            "no_cache": False,
            "timeout": atcoder_metadata.DEFAULT_TIMEOUT_SECONDS,
        }
        problems = atcoder_metadata.load_resource("problems", **fetch_kwargs).get("result")
        merged = atcoder_metadata.load_resource("merged-problems", **fetch_kwargs).get("result")
        ratings = atcoder_metadata.load_resource("ratings", **fetch_kwargs).get("result")
        return {"module": atcoder_metadata, "problems": problems, "merged": merged, "ratings": ratings}
    except Exception as exc:  # noqa: BLE001 - plan should degrade to confirmation instead of crashing
        warnings.append(f"AtCoder metadata unavailable: {exc}")
        return {}


def load_codeforces_metadata(no_metadata: bool, refresh: bool, warnings: list[str]) -> dict[str, Any]:
    if no_metadata:
        return {}
    try:
        import codeforces_metadata

        cache_dir = codeforces_metadata.default_cache_dir()
        fetch_kwargs = {
            "cache_dir": cache_dir,
            "max_age_seconds": codeforces_metadata.DEFAULT_MAX_AGE_SECONDS,
            "refresh": refresh,
            "no_cache": False,
            "timeout": codeforces_metadata.DEFAULT_TIMEOUT_SECONDS,
        }
        contests = codeforces_metadata.load_method("contest.list", {}, **fetch_kwargs).get("result")
        problems = codeforces_metadata.load_method("problemset.problems", {}, **fetch_kwargs).get("result")
        return {"contests": contests, "problemset": problems}
    except Exception as exc:  # noqa: BLE001 - plan should degrade to confirmation instead of crashing
        warnings.append(f"Codeforces metadata unavailable: {exc}")
        return {}


def atcoder_problem_title(problem_id: str, metadata: dict[str, Any]) -> str | None:
    module = metadata.get("module")
    if not module:
        return None
    problem = module.find_problem(metadata.get("problems", []), problem_id)
    title = module.problem_title(problem)
    if title:
        return title
    problem = module.find_problem(metadata.get("merged", []), problem_id)
    return module.problem_title(problem)


def atcoder_rating(problem_id: str, metadata: dict[str, Any]) -> str:
    module = metadata.get("module")
    if not module:
        return "$-$"
    models = metadata.get("ratings", {})
    difficulty = module.extract_difficulty(models.get(problem_id))
    if difficulty is None:
        return "$-$"
    return rating_markdown(difficulty)


def atcoder_contest_parts(contest_id: str) -> tuple[str, int | None, str | None]:
    lowered = contest_id.lower()
    if lowered.startswith("past"):
        return "PAST", None, lowered.removeprefix("past")
    match = re.fullmatch(r"(abc|arc|agc|ahc)(\d+)", lowered)
    if not match:
        raise PlanError(f"Unsupported AtCoder contest id: {contest_id}")
    series = match.group(1).upper()
    if series not in {"ABC", "ARC", "AGC", "AHC"}:
        raise PlanError(f"Unsupported AtCoder contest series: {series}")
    return series, int(match.group(2)), None


def build_atcoder_target(
    route: Route,
    contest_id: str,
    problem_id: str,
    problem_title: str | None,
    ext: str,
    warnings: list[str],
) -> Path:
    series, number, past_key = atcoder_contest_parts(contest_id)
    label = normalize_atcoder_problem_id(problem_id)
    title_slug = safe_title_slug(problem_title)
    if not title_slug:
        title_slug = "TITLE_REQUIRED"
        warnings.append("AtCoder problem title is required to create the final filename.")
    filename = f"{label}_{title_slug}{ext}"

    if series == "PAST":
        if not past_key:
            raise PlanError(f"Unsupported PAST contest id: {contest_id}")
        return route.target_base / "PAST" / past_key / filename

    assert number is not None
    hundreds = (number // 100) * 100
    tens = (number // 10) * 10
    return route.target_base / series / str(hundreds) / str(tens) / str(number) / filename


def codeforces_problemset(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    problemset = metadata.get("problemset") or {}
    if isinstance(problemset, dict):
        return problemset.get("problems") or []
    return []


def find_codeforces_problem(contest_id: str, problem_id: str, metadata: dict[str, Any]) -> dict[str, Any] | None:
    wanted_contest = int(contest_id)
    wanted_index = normalize_codeforces_problem_id(problem_id)
    for problem in codeforces_problemset(metadata):
        if problem.get("contestId") == wanted_contest and str(problem.get("index", "")).upper() == wanted_index:
            return problem
    return None


def codeforces_rating(contest_id: str, problem_id: str, metadata: dict[str, Any]) -> str:
    problem = find_codeforces_problem(contest_id, problem_id, metadata)
    if not problem:
        return "$-$"
    return rating_markdown(problem.get("rating"))


def codeforces_problem_title(contest_id: str, problem_id: str, metadata: dict[str, Any]) -> str | None:
    problem = find_codeforces_problem(contest_id, problem_id, metadata)
    if not problem:
        return None
    title = problem.get("name")
    if not isinstance(title, str):
        return None
    return title.strip() or None


def find_codeforces_contest(contest_id: str, metadata: dict[str, Any]) -> dict[str, Any] | None:
    contests = metadata.get("contests") or []
    wanted = int(contest_id)
    for contest in contests:
        if contest.get("id") == wanted:
            return contest
    return None


def has_official_codeforces_round_token(title: str) -> bool:
    return re.search(r"\bcodeforces\s+(?:beta\s+)?round\b", title, re.IGNORECASE) is not None


def extract_codeforces_round_number(title: str | None, contest_kind: str | None) -> str | None:
    if not title:
        return None

    patterns: list[str] = []
    if contest_kind == "Educational":
        patterns.append(r"\beducational\s+codeforces\s+round\s+#?(\d+)\b")
    elif contest_kind == "regular":
        patterns.append(r"\bcodeforces\s+(?:beta\s+)?round\s+#?(\d+)\b")
    elif contest_kind == "Others":
        direct_patterns = [
            r"\bcodeforces\s+global\s+round\s+#?(\d+)\b",
            r"\bkotlin\s+heroes:\s*(?:episode|practice)\s+(\d+)\b",
            r"\bapril\s+fools(?:\s+day)?\s+contest\s+#?(\d{1,3})\b",
            r"\b(?:codeforces\s+)?testing\s+round\s+#?(\d+)\b",
            r"\bround\s+#?(\d+)\b",
        ]
        for pattern in direct_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return str(int(match.group(1)))

        year_patterns = [
            r"\b(?:hello|good\s+bye|goodbye)\s+((?:19|20)\d{2})\b",
            r"\bapril\s+fools(?:\s+day)?\s+contest\s+((?:19|20)\d{2})\b",
            r"\b((?:19|20)\d{2})\b",
        ]
        for pattern in year_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return str(int(match.group(1)[-2:]))
        return None
    else:
        patterns.extend(
            [
                r"\beducational\s+codeforces\s+round\s+#?(\d+)\b",
                r"\bcodeforces\s+global\s+round\s+#?(\d+)\b",
                r"\bcodeforces\s+(?:beta\s+)?round\s+#?(\d+)\b",
                r"\b(?:hello|good\s+bye|goodbye)\s+(\d{4})\b",
                r"\bround\s+#?(\d+)\b",
            ]
        )

    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return str(int(match.group(1)))
    return None


def extract_codeforces_contest_group(title: str | None, contest_kind: str | None) -> str | None:
    if contest_kind != "Others" or not title:
        return None

    lowered = title.lower()
    group: str | None = None
    if "codeforces global round" in lowered:
        group = "Global_Round"
    elif re.search(r"\bgood\s+bye\b|\bgoodbye\b", title, re.IGNORECASE):
        group = "Good_Bye"
    elif re.search(r"\bhello\b", title, re.IGNORECASE):
        group = "Hello"
    elif "april fools" in lowered:
        group = "April_Fools"
    elif "kotlin heroes" in lowered:
        group = "Kotlin_Heroes"
    elif "testing round" in lowered or "codeforces testing round" in lowered:
        group = "Testing_Round"
    elif "vk cup" in lowered:
        group = "VK_Cup"
    elif "technocup" in lowered or "технокубок" in lowered:
        group = "Technocup"
    elif "icpc" in lowered or "acm-icpc" in lowered:
        group = "ICPC"
    elif "ioi" in lowered:
        group = "IOI"
    else:
        match = re.search(
            r"^\s*(.+?\b(?:Round|Contest|Cup|Challenge|Forces|Heroes|Marathon|Championship))\b",
            title,
            re.IGNORECASE,
        )
        if match:
            group = match.group(1)
        else:
            group = re.split(r"\s*[\(\[:\-]\s*", title, maxsplit=1)[0]

    try:
        return normalize_codeforces_contest_group(group)
    except argparse.ArgumentTypeError:
        return None


def classify_codeforces_contest(
    contest_id: str,
    explicit_kind: str | None,
    explicit_title: str | None,
    metadata: dict[str, Any],
    warnings: list[str],
) -> tuple[str | None, str | None]:
    if explicit_kind:
        return explicit_kind, explicit_title

    title = explicit_title
    contest = find_codeforces_contest(contest_id, metadata)
    if not title and contest:
        title = contest.get("name")

    if not title:
        warnings.append("Codeforces contest kind is unknown; pass --contest-kind regular|Educational|Others.")
        return None, None

    lowered = title.lower()
    if "educational codeforces round" in lowered:
        return "Educational", title

    if "codeforces global round" in lowered:
        return "Others", title

    if has_official_codeforces_round_token(title):
        return "regular", title

    return "Others", title


def resolve_codeforces_round_number(target: CodeforcesTarget) -> str | None:
    if target.round_number:
        try:
            return normalize_codeforces_round_number(target.round_number)
        except argparse.ArgumentTypeError as exc:
            raise PlanError(str(exc)) from exc
    return extract_codeforces_round_number(target.contest_title, target.contest_kind)


def resolve_codeforces_contest_group(target: CodeforcesTarget) -> str | None:
    if target.contest_kind != "Others":
        return None
    if target.contest_group:
        try:
            return normalize_codeforces_contest_group(target.contest_group)
        except argparse.ArgumentTypeError as exc:
            raise PlanError(str(exc)) from exc
    return extract_codeforces_contest_group(target.contest_title, target.contest_kind)


def build_codeforces_target(
    route: Route,
    target: CodeforcesTarget,
    problem_title: str | None,
    ext: str,
    warnings: list[str],
) -> Path:
    round_number = resolve_codeforces_round_number(target)
    if not round_number:
        raise PlanError(
            f"Codeforces round number could not be determined for contest {target.contest_id}; "
            "provide --round-number or include a contest title with a numeric round."
        )

    folder_number = int(round_number)
    hundreds = (folder_number // 100) * 100
    tens = (folder_number // 10) * 10
    problem_id = normalize_codeforces_problem_id(target.problem_id)
    title_slug = safe_title_slug(problem_title)
    if not title_slug:
        title_slug = "TITLE_REQUIRED"
        warnings.append("Codeforces problem title is required to create the final filename.")
    filename = f"{problem_id}_{title_slug}{ext}"
    base = route.target_base
    if target.contest_kind == "Educational":
        base = base / "Educational"
    elif target.contest_kind == "Others":
        contest_group = resolve_codeforces_contest_group(target)
        if not contest_group:
            raise PlanError(
                f"Codeforces contest group could not be determined for contest {target.contest_id}; "
                "provide --contest-group or include a contest title."
            )
        base = base / "Others" / contest_group
    return base / str(hundreds) / str(tens) / str(folder_number) / filename


def parse_additional_target(raw: str, default_kind: str | None) -> CodeforcesTarget:
    parts = raw.split(":")
    if len(parts) not in {2, 3, 4, 5}:
        raise PlanError("--additional-target must use CONTEST_ID:PROBLEM_ID[:KIND[:ROUND_NUMBER[:CONTEST_GROUP]]]")
    kind = parts[2] if len(parts) >= 3 and parts[2] else default_kind
    round_number = parts[3] if len(parts) >= 4 and parts[3] else None
    contest_group = parts[4] if len(parts) == 5 else None
    if kind:
        try:
            kind = normalize_codeforces_kind(kind)
        except argparse.ArgumentTypeError as exc:
            raise PlanError(f"Unsupported Codeforces contest kind in additional target: {kind}") from exc
    if round_number:
        try:
            round_number = normalize_codeforces_round_number(round_number)
        except argparse.ArgumentTypeError as exc:
            raise PlanError(str(exc)) from exc
    if contest_group:
        try:
            contest_group = normalize_codeforces_contest_group(contest_group)
        except argparse.ArgumentTypeError as exc:
            raise PlanError(str(exc)) from exc
    return CodeforcesTarget(
        contest_id=parts[0],
        problem_id=parts[1],
        contest_kind=kind,
        round_number=round_number,
        contest_group=contest_group,
    )


def build_update_command(update: dict[str, Any]) -> list[str]:
    command = [
        sys.executable,
        str(Path(__file__).with_name("update_readme.py")),
        "--readme",
        update["readme"],
        "--contest-url",
        update["contest_url"],
        "--problem-id",
        update["problem_id"],
        "--rating",
        update["rating"],
    ]
    tags = update.get("tags")
    if tags:
        command.extend(["--tags", tags])
    return command


def build_contest_result_command(platform: str, contest_id: str, user_id: str | None) -> list[str] | None:
    if not user_id:
        return None
    script_name = "atcoder_results.py" if platform == "atcoder" else "codeforces_results.py"
    return [
        sys.executable,
        str(Path(__file__).with_name(script_name)),
        "contest",
        "--contest-id",
        contest_id,
        "--user",
        user_id,
    ]


def make_readme_update(
    contest_dir: Path,
    contest_url: str,
    problem_id: str,
    rating: str,
    tags: str | None,
    *,
    platform: str,
    contest_id: str,
    user_id: str | None,
) -> dict[str, Any]:
    update = {
        "readme": str(contest_dir / "README.md"),
        "contest_url": contest_url,
        "problem_id": problem_id,
        "rating": rating,
        "tags": tags,
        "user_id": user_id,
        "contest_result_command": build_contest_result_command(platform, contest_id, user_id),
    }
    update["command"] = build_update_command(update)
    return update


def plan_atcoder(
    source: Path,
    detection: Detection,
    route: Route,
    args: argparse.Namespace,
    warnings: list[str],
) -> dict[str, Any]:
    if not detection.contest_id or not detection.problem_id:
        raise PlanError("AtCoder planning requires contest_id and problem_id.")

    metadata = load_atcoder_metadata(args.no_metadata, args.refresh_metadata, warnings)
    task_problem_id = f"{detection.contest_id.lower()}_{detection.problem_id.lower()}"
    problem_title = detection.problem_title or atcoder_problem_title(task_problem_id, metadata)
    rating = rating_markdown(args.rating) if args.rating else atcoder_rating(task_problem_id, metadata)
    ext = normalize_ext(source)
    target = build_atcoder_target(
        route=route,
        contest_id=detection.contest_id,
        problem_id=detection.problem_id,
        problem_title=problem_title,
        ext=ext,
        warnings=warnings,
    )
    contest_url = f"https://atcoder.jp/contests/{detection.contest_id.lower()}"
    tags = collect_tags(args)
    readme_update = make_readme_update(
        contest_dir=target.parent,
        contest_url=contest_url,
        problem_id=normalize_atcoder_problem_id(detection.problem_id),
        rating=rating,
        tags=tags,
        platform="atcoder",
        contest_id=detection.contest_id.lower(),
        user_id=route.user_id,
    )

    return {
        "targets": [str(target)],
        "readme_updates": [readme_update],
        "commit_message": f"Add AtCoder {detection.contest_id.upper()} {normalize_atcoder_problem_id(detection.problem_id)} solution",
        "metadata": {
            "contest_url": contest_url,
            "contest_id": detection.contest_id.lower(),
            "problem_id": normalize_atcoder_problem_id(detection.problem_id),
            "problem_title": problem_title,
            "rating": rating,
            "user_id": route.user_id,
        },
    }


def plan_codeforces(
    source: Path,
    detection: Detection,
    route: Route,
    args: argparse.Namespace,
    warnings: list[str],
) -> dict[str, Any]:
    if not detection.contest_id or not detection.problem_id:
        raise PlanError("Codeforces planning requires contest_id and problem_id.")

    metadata = load_codeforces_metadata(args.no_metadata, args.refresh_metadata, warnings)
    main_kind, main_title = classify_codeforces_contest(
        detection.contest_id,
        detection.contest_kind,
        detection.contest_title,
        metadata,
        warnings,
    )
    main_target = CodeforcesTarget(
        contest_id=detection.contest_id,
        problem_id=detection.problem_id,
        contest_kind=main_kind,
        contest_title=main_title,
        round_number=args.round_number,
        contest_group=args.contest_group,
    )
    targets = [main_target]
    for raw in args.additional_target:
        additional = parse_additional_target(raw, main_kind)
        if not additional.contest_kind:
            additional.contest_kind, additional.contest_title = classify_codeforces_contest(
                additional.contest_id,
                None,
                None,
                metadata,
                warnings,
            )
        targets.append(additional)

    ext = normalize_ext(source)
    tags = collect_tags(args)
    target_paths: list[str] = []
    readme_updates: list[dict[str, Any]] = []
    target_metadata: list[dict[str, Any]] = []
    readme_urls_by_dir: dict[str, str] = {}
    readme_url_warnings: set[str] = set()

    for target in targets:
        if not target.contest_kind:
            warnings.append(f"Codeforces contest kind is required for contest {target.contest_id}.")
            target.contest_kind = "regular"
        problem_title = detection.problem_title or codeforces_problem_title(
            target.contest_id,
            target.problem_id,
            metadata,
        )
        target_path = build_codeforces_target(route, target, problem_title, ext, warnings)
        contest_url = f"https://codeforces.com/contest/{target.contest_id}"
        contest_dir_key = str(target_path.parent)
        readme_url = readme_urls_by_dir.setdefault(contest_dir_key, contest_url)
        if readme_url != contest_url and contest_dir_key not in readme_url_warnings:
            warnings.append(
                f"Multiple Codeforces contest IDs share README {target_path.parent / 'README.md'}; "
                f"using {readme_url} as the header."
            )
            readme_url_warnings.add(contest_dir_key)
        rating = rating_markdown(args.rating) if args.rating else codeforces_rating(
            target.contest_id,
            target.problem_id,
            metadata,
        )
        target_paths.append(str(target_path))
        readme_updates.append(
            make_readme_update(
                contest_dir=target_path.parent,
                contest_url=readme_url,
                problem_id=normalize_codeforces_problem_id(target.problem_id),
                rating=rating,
                tags=tags,
                platform="codeforces",
                contest_id=target.contest_id,
                user_id=route.user_id,
            )
        )
        target_metadata.append(
            {
                "contest_url": contest_url,
                "contest_id": target.contest_id,
                "round_number": resolve_codeforces_round_number(target),
                "contest_group": resolve_codeforces_contest_group(target),
                "contest_kind": target.contest_kind,
                "contest_title": target.contest_title,
                "problem_id": normalize_codeforces_problem_id(target.problem_id),
                "problem_title": problem_title,
                "rating": rating,
                "user_id": route.user_id,
            }
        )

    return {
        "targets": target_paths,
        "readme_updates": readme_updates,
        "commit_message": f"Add Codeforces {resolve_codeforces_round_number(main_target)}{normalize_codeforces_problem_id(detection.problem_id)} solution",
        "metadata": {
            "problem_title": target_metadata[0].get("problem_title") if target_metadata else None,
            "targets": target_metadata,
        },
    }


def collect_tags(args: argparse.Namespace) -> str | None:
    raw_tags: list[str] = []
    if args.tags:
        raw_tags.extend(tag.strip() for tag in args.tags.split(",") if tag.strip())
    for raw in args.tag:
        raw_tags.extend(tag.strip() for tag in raw.split(",") if tag.strip())
    if not raw_tags:
        return None

    tag_map = load_tag_map()
    tags = [normalize_readme_tag(tag, tag_map) for tag in raw_tags]
    return ", ".join(dict.fromkeys(tags))


def source_is_weak(source: Path, detection: Detection) -> bool:
    return detection.confidence in {"none", "low"} or source.stem.lower() in WEAK_FILE_STEMS


def check_target_conflicts(targets: list[str], warnings: list[str]) -> bool:
    needs_confirmation = False
    for target in targets:
        if Path(target).exists():
            warnings.append(f"Target already exists: {target}")
            needs_confirmation = True
    return needs_confirmation


def build_plan(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    source = Path(args.source).expanduser().resolve()
    warnings: list[str] = []

    if not source.exists():
        raise PlanError(f"Source file does not exist: {source}")
    if not source.is_file():
        raise PlanError(f"Source path is not a file: {source}")

    ext = normalize_ext(source)
    unknown_extension = ext not in SOURCE_EXTENSIONS
    if unknown_extension:
        warnings.append(f"Source extension is not a known solution language: {source.suffix}")

    detection = apply_overrides(detect_solution(source), args)
    if not detection.platform:
        raise PlanError("Could not detect platform. Pass --platform atcoder|codeforces.")
    detection.platform = detection.platform.lower()
    if detection.platform not in SUPPORTED_PLATFORMS:
        raise PlanError(f"Unsupported platform: {detection.platform}")
    if not detection.contest_id or not detection.problem_id:
        raise PlanError("Could not detect contest/problem. Pass --contest-id and --problem-id.")

    route = load_route(detection.platform, args.config)
    warnings.extend(route.warnings)
    if not route.user_id:
        user_warning = (
            f"{detection.platform} user id is not configured; ask the user and run "
            f"`scripts/configure_repos.py user {detection.platform} --id <id>` before adding contest results to README."
        )
        if not any("user id" in warning and detection.platform in warning for warning in warnings):
            warnings.append(user_warning)

    if detection.platform == "atcoder":
        platform_plan = plan_atcoder(source, detection, route, args, warnings)
    else:
        platform_plan = plan_codeforces(source, detection, route, args, warnings)

    needs_confirmation = False
    if unknown_extension:
        needs_confirmation = True
    if source_is_weak(source, detection):
        warnings.append("Problem identity is based on weak evidence; confirm before publishing.")
        needs_confirmation = True
    if any(item.startswith("CLI override changed ") for item in detection.evidence):
        warnings.append("CLI overrides conflict with detected source metadata; confirm before publishing.")
        needs_confirmation = True
    if not collect_tags(args):
        warnings.append("README tags were not provided; infer tags from the solution code before updating README.")
        needs_confirmation = True
    if any("required" in warning.lower() or "ambiguous" in warning.lower() for warning in warnings):
        needs_confirmation = True
    if not route.user_id:
        needs_confirmation = True
    if check_target_conflicts(platform_plan["targets"], warnings):
        needs_confirmation = True

    plan = {
        "source": str(source),
        "platform": detection.platform,
        "repo": str(route.repo_path),
        "base_dir": route.base_dir,
        "user_id": route.user_id,
        "targets": platform_plan["targets"],
        "readme_updates": platform_plan["readme_updates"],
        "commit_message": platform_plan["commit_message"],
        "needs_confirmation": needs_confirmation,
        "detection": {
            "contest_id": detection.contest_id,
            "problem_id": detection.problem_id,
            "problem_title": platform_plan["metadata"].get("problem_title"),
            "contest_kind": detection.contest_kind,
            "contest_title": detection.contest_title,
            "confidence": detection.confidence,
            "evidence": detection.evidence,
        },
        "metadata": platform_plan["metadata"],
        "warnings": warnings,
    }
    return plan, 0


def make_error_plan(source: str | None, message: str) -> dict[str, Any]:
    return {
        "source": source,
        "targets": [],
        "readme_updates": [],
        "commit_message": None,
        "needs_confirmation": True,
        "errors": [message],
    }


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
