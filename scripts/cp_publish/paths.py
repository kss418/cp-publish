from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from .models import CodeforcesTarget, EXTENSION_ALIASES, PlanError, Route


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


def has_official_codeforces_round_token(title: str) -> bool:
    return re.search(r"\bcodeforces\s+(?:beta\s+)?round\b", title, re.IGNORECASE) is not None


def infer_codeforces_kind_from_title(title: str) -> str:
    lowered = title.lower()
    if "educational codeforces round" in lowered:
        return "Educational"
    if "codeforces global round" in lowered:
        return "Others"
    if has_official_codeforces_round_token(title):
        return "regular"
    return "Others"


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
