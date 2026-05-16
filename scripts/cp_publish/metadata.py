from __future__ import annotations

from typing import Any

from .models import Detection
from .paths import (
    extract_codeforces_round_number,
    infer_codeforces_kind_from_title,
    normalize_codeforces_problem_id,
    rating_markdown,
)


def load_atcoder_metadata(no_metadata: bool, refresh: bool, warnings: list[str]) -> dict[str, Any]:
    if no_metadata:
        return {}
    try:
        from api import atcoder_metadata

        cache_dir = atcoder_metadata.default_cache_dir()
        fetch_kwargs = {
            "cache_dir": cache_dir,
            "max_age_seconds": atcoder_metadata.DEFAULT_MAX_AGE_SECONDS,
            "refresh": refresh,
            "no_cache": False,
            "timeout": atcoder_metadata.DEFAULT_TIMEOUT_SECONDS,
        }
        metadata: dict[str, Any] = {"module": atcoder_metadata, "fetch_kwargs": fetch_kwargs}
        for resource, key, default in (
            ("problems", "problems", []),
            ("merged-problems", "merged", []),
            ("ratings", "ratings", {}),
        ):
            try:
                metadata[key] = atcoder_metadata.load_resource(resource, **fetch_kwargs).get("result")
            except Exception as exc:  # noqa: BLE001 - official AtCoder fallback may still provide titles
                metadata[key] = default
                warnings.append(f"AtCoder {resource} metadata unavailable: {exc}")
        return metadata
    except Exception as exc:  # noqa: BLE001 - plan should degrade to confirmation instead of crashing
        warnings.append(f"AtCoder metadata unavailable: {exc}")
        return {}


def load_codeforces_metadata(no_metadata: bool, refresh: bool, warnings: list[str]) -> dict[str, Any]:
    if no_metadata:
        return {}
    try:
        from api import codeforces_metadata

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


def atcoder_problem_title(problem_id: str, metadata: dict[str, Any], warnings: list[str] | None = None) -> str | None:
    module = metadata.get("module")
    if not module:
        return None
    problem = module.find_problem(metadata.get("problems", []), problem_id)
    title = module.problem_title(problem)
    if title:
        return title
    problem = module.find_problem(metadata.get("merged", []), problem_id)
    title = module.problem_title(problem)
    if title:
        return title

    fetch_kwargs = metadata.get("fetch_kwargs")
    if not isinstance(fetch_kwargs, dict):
        return None
    try:
        official_problem, _official_data = module.lookup_official_problem(problem_id, **fetch_kwargs)
    except Exception as exc:  # noqa: BLE001 - title fallback should not crash planning
        if warnings is not None:
            warnings.append(f"AtCoder official tasks title fallback unavailable: {exc}")
        return None
    return module.problem_title(official_problem)


def atcoder_rating(problem_id: str, metadata: dict[str, Any]) -> str:
    module = metadata.get("module")
    if not module:
        return "$-$"
    models = metadata.get("ratings", {})
    difficulty = module.extract_difficulty(models.get(problem_id))
    if difficulty is None:
        return "$-$"
    return rating_markdown(difficulty)


def codeforces_problemset(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    problemset = metadata.get("problemset") or {}
    if isinstance(problemset, dict):
        return problemset.get("problems") or []
    return []


def find_codeforces_problem(contest_id: str, problem_id: str, metadata: dict[str, Any]) -> dict[str, Any] | None:
    try:
        wanted_contest = int(contest_id)
    except ValueError:
        return None
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
    try:
        wanted = int(contest_id)
    except ValueError:
        return None
    for contest in contests:
        if contest.get("id") == wanted:
            return contest
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
        warnings.append("Codeforces contest kind is unknown; pass --contest-kind regular|Educational|Global|Others.")
        return None, None

    return infer_codeforces_kind_from_title(title), title


def resolve_codeforces_detection_by_round(
    detection: Detection,
    metadata: dict[str, Any],
    warnings: list[str],
) -> None:
    if detection.contest_id or not detection.round_number or not detection.problem_id:
        return

    contests = metadata.get("contests") or []
    candidates: list[tuple[str, str, str]] = []
    for contest in contests:
        contest_id = contest.get("id")
        title = contest.get("name")
        if not isinstance(contest_id, int) or not isinstance(title, str):
            continue

        contest_kind = infer_codeforces_kind_from_title(title)
        if detection.contest_kind and contest_kind != detection.contest_kind:
            continue

        round_number = extract_codeforces_round_number(title, contest_kind)
        if round_number != detection.round_number:
            continue

        if not find_codeforces_problem(str(contest_id), detection.problem_id, metadata):
            continue

        candidates.append((str(contest_id), contest_kind, title))

    if len(candidates) == 1:
        contest_id, contest_kind, title = candidates[0]
        detection.contest_id = contest_id
        detection.contest_kind = detection.contest_kind or contest_kind
        detection.contest_title = detection.contest_title or title
        detection.evidence.append(
            f"Codeforces metadata matched round {detection.round_number} to contest {contest_id}"
        )
        detection.confidence = "high"
        return

    if not candidates:
        warnings.append(
            f"Could not match Codeforces round {detection.round_number} problem "
            f"{normalize_codeforces_problem_id(detection.problem_id)} to a contest ID from metadata."
        )
        return

    warnings.append(
        f"Codeforces round {detection.round_number} problem "
        f"{normalize_codeforces_problem_id(detection.problem_id)} matched multiple contest IDs: "
        + ", ".join(contest_id for contest_id, _kind, _title in candidates)
    )
