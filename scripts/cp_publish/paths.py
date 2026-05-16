from __future__ import annotations

import argparse
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .models import (
    CODEFORCES_CONTEST_RULE_MAP_PATH,
    CodeforcesTarget,
    EXTENSION_ALIASES,
    PlanError,
    Route,
)


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


def normalize_codeforces_contest_id(value: str) -> str:
    cleaned = value.strip()
    if not re.fullmatch(r"\d+", cleaned):
        raise PlanError(f"Codeforces contest id must be numeric, got: {value!r}")
    return str(int(cleaned))


def normalize_codeforces_kind(value: str) -> str:
    lowered = value.strip().lower()
    if lowered == "regular":
        return "regular"
    if lowered == "educational":
        return "Educational"
    if lowered == "global":
        return "Global"
    if lowered in {"other", "others"}:
        return "Others"
    raise argparse.ArgumentTypeError("contest kind must be regular, Educational, Global, or Others")


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
    slug = re.sub(r"[^\w]+", "_", title.strip(), flags=re.UNICODE)
    slug = re.sub(r"_+", "_", slug).strip("._ ")
    return slug or None


def leading_problem_id(stem: str) -> str:
    return stem.split("_", 1)[0]


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


@lru_cache(maxsize=1)
def load_codeforces_contest_rule_map() -> dict[str, Any]:
    try:
        payload = json.loads(CODEFORCES_CONTEST_RULE_MAP_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanError(
            f"Could not load Codeforces contest rule map: {CODEFORCES_CONTEST_RULE_MAP_PATH}"
        ) from exc

    if not isinstance(payload, dict):
        raise PlanError(f"Codeforces contest rule map is not an object: {CODEFORCES_CONTEST_RULE_MAP_PATH}")
    return payload


def normalize_codeforces_rule_key(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "_", lowered)
    return re.sub(r"_+", "_", lowered).strip("_")


def codeforces_patterns(section: Any) -> list[str]:
    if not isinstance(section, list):
        return []
    return [pattern for pattern in section if isinstance(pattern, str) and pattern]


def first_codeforces_pattern_number(
    title: str,
    patterns: list[str],
    *,
    year_suffix: bool = False,
) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if not match:
            continue
        value = match.group(1)
        if year_suffix:
            value = value[-2:]
        return str(int(value))
    return None


def codeforces_kind_patterns(kind: str) -> list[str]:
    payload = load_codeforces_contest_rule_map()
    patterns = payload.get("kind_patterns")
    if not isinstance(patterns, dict):
        return []
    return codeforces_patterns(patterns.get(kind))


def codeforces_other_aliases() -> dict[str, str]:
    payload = load_codeforces_contest_rule_map()
    aliases = payload.get("others_group_aliases")
    if not isinstance(aliases, dict):
        return {}
    return {
        normalize_codeforces_rule_key(key): value
        for key, value in aliases.items()
        if isinstance(key, str) and isinstance(value, str) and key and value
    }


def codeforces_other_priority_aliases() -> list[str]:
    payload = load_codeforces_contest_rule_map()
    priority = payload.get("others_group_priority_aliases")
    if not isinstance(priority, list):
        return []
    return [normalize_codeforces_rule_key(alias) for alias in priority if isinstance(alias, str) and alias]


def codeforces_group_from_rule_map(title: str) -> str | None:
    title_key = normalize_codeforces_rule_key(title)
    aliases = codeforces_other_aliases()
    priority_aliases = [alias for alias in codeforces_other_priority_aliases() if alias in aliases]
    priority_set = set(priority_aliases)
    remaining_aliases = sorted(
        (alias for alias in aliases if alias not in priority_set),
        key=len,
        reverse=True,
    )
    for alias in [*priority_aliases, *remaining_aliases]:
        if alias and alias in title_key:
            return aliases[alias]
    return None


def codeforces_round_number_patterns(contest_kind: str | None) -> Any:
    payload = load_codeforces_contest_rule_map()
    patterns = payload.get("round_number_patterns")
    if not isinstance(patterns, dict) or contest_kind is None:
        return None
    return patterns.get(contest_kind)


def regex_from_codeforces_alias(alias: str) -> str:
    parts = [re.escape(part) for part in alias.split("_") if part]
    return r"\b" + r"[\W_]+".join(parts) + r"[\W_]+#?(\d{1,4})(?:\.\d+)?\b"


def extract_codeforces_alias_number(title: str, group: str | None) -> str | None:
    if not group:
        return None
    aliases = codeforces_other_aliases()
    group_aliases = sorted(
        [alias for alias, alias_group in aliases.items() if alias_group == group],
        key=len,
        reverse=True,
    )
    for alias in group_aliases:
        match = re.search(regex_from_codeforces_alias(alias), title, re.IGNORECASE)
        if match:
            return str(int(match.group(1)))
    return None


def has_official_codeforces_round_token(title: str) -> bool:
    return any(re.search(pattern, title, re.IGNORECASE) for pattern in codeforces_kind_patterns("regular"))


def infer_codeforces_kind_from_title(title: str) -> str:
    for kind in ("Educational", "Global", "regular"):
        if any(re.search(pattern, title, re.IGNORECASE) for pattern in codeforces_kind_patterns(kind)):
            return kind
    return "Others"


def extract_codeforces_round_number(title: str | None, contest_kind: str | None) -> str | None:
    if not title:
        return None

    mapped_patterns = codeforces_round_number_patterns(contest_kind)
    if contest_kind == "Educational":
        return first_codeforces_pattern_number(title, codeforces_patterns(mapped_patterns))
    elif contest_kind == "Global":
        return first_codeforces_pattern_number(title, codeforces_patterns(mapped_patterns))
    elif contest_kind == "regular":
        return first_codeforces_pattern_number(title, codeforces_patterns(mapped_patterns))
    elif contest_kind == "Others":
        if not isinstance(mapped_patterns, dict):
            mapped_patterns = {}
        group = extract_codeforces_contest_group(title, contest_kind)
        year_suffix_patterns = codeforces_patterns(mapped_patterns.get("_year_suffix"))
        if group:
            group_number = first_codeforces_pattern_number(
                title,
                codeforces_patterns(mapped_patterns.get(group)),
            )
            if group_number:
                return group_number
        direct_number = first_codeforces_pattern_number(title, codeforces_patterns(mapped_patterns.get("*")))
        if direct_number:
            return direct_number
        if group in {"April_Fools", "Good_Bye", "Hello"}:
            year_number = first_codeforces_pattern_number(title, year_suffix_patterns, year_suffix=True)
            if year_number:
                return year_number
        alias_number = extract_codeforces_alias_number(title, group)
        if alias_number:
            return alias_number
        year_number = first_codeforces_pattern_number(title, year_suffix_patterns, year_suffix=True)
        if year_number:
            return year_number
        return None
    else:
        fallback_patterns = [
            *codeforces_patterns(codeforces_round_number_patterns("Educational")),
            *codeforces_patterns(codeforces_round_number_patterns("Global")),
            *codeforces_patterns(codeforces_round_number_patterns("regular")),
            r"\b(?:hello|good\s+bye|goodbye)\s+(\d{4})\b",
            r"\bround\s+#?(\d+)\b",
        ]
        return first_codeforces_pattern_number(title, fallback_patterns)


def extract_codeforces_contest_group(title: str | None, contest_kind: str | None) -> str | None:
    if contest_kind != "Others" or not title:
        return None

    lowered = title.lower()
    group: str | None = None
    mapped_group = codeforces_group_from_rule_map(title)
    if mapped_group:
        group = mapped_group
    elif "technocup" in lowered or "технокубок" in lowered:
        group = "Technocup"
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
    elif target.contest_kind == "Global":
        base = base / "Global"
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
        contest_id=normalize_codeforces_contest_id(parts[0]),
        problem_id=parts[1],
        contest_kind=kind,
        round_number=round_number,
        contest_group=contest_group,
    )
