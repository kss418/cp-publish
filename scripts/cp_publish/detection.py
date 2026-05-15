from __future__ import annotations

import argparse
import re
from pathlib import Path

from .models import ATCODER_NUMERIC_SERIES, Detection, SUPPORTED_PLATFORMS, WEAK_FILE_STEMS
from .paths import leading_problem_id, normalize_codeforces_contest_group


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

    def set_filename_title(suffix: str | None) -> None:
        if not suffix:
            return
        title = re.sub(r"[_-]+", " ", suffix).strip(" ._-")
        title = re.sub(r"\s+", " ", title)
        if title:
            detection.problem_title = title
            detection.evidence.append(f"Filename title suffix: {title}")

    atcoder_match = re.fullmatch(r"(abc|arc|agc|ahc)(\d{2,4})([a-z][0-9]?|ex)", compact)
    if atcoder_match:
        detection.platform = "atcoder"
        detection.contest_id = f"{atcoder_match.group(1)}{int(atcoder_match.group(2)):03d}"
        detection.problem_id = atcoder_match.group(3)
        detection.evidence.append(f"AtCoder compact filename: {path.name}")
        detection.confidence = "medium"
        return detection

    atcoder_split = re.fullmatch(
        r"(abc|arc|agc|ahc)(\d{2,4})[_-]?([a-z][0-9]?|ex)(?:[_-](.+))?",
        stem,
        re.IGNORECASE,
    )
    if atcoder_split:
        detection.platform = "atcoder"
        detection.contest_id = f"{atcoder_split.group(1).lower()}{int(atcoder_split.group(2)):03d}"
        detection.problem_id = atcoder_split.group(3).lower()
        set_filename_title(atcoder_split.group(4))
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

    cf_match = re.fullmatch(
        r"(?:cf[_-]?)?(\d{3,5})[_-]?([A-Za-z][0-9]?)(?:[_-](.+))?",
        stem,
        re.IGNORECASE,
    )
    if cf_match:
        detection.platform = "codeforces"
        detection.contest_id = cf_match.group(1)
        detection.problem_id = cf_match.group(2)
        set_filename_title(cf_match.group(3))
        detection.evidence.append(f"Codeforces filename: {path.name}")
        detection.confidence = "medium"
        return detection

    if stem.lower() in WEAK_FILE_STEMS:
        detection.evidence.append(f"Weak filename only: {path.name}")
        detection.confidence = "low"

    return detection


def detect_from_path(path: Path) -> Detection:
    raw_parts = list(path.parts)
    parts = [part.lower() for part in raw_parts]
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
            detection.round_number = parts[idx + 3]
            detection.problem_id = leading_problem_id(path.stem)
            detection.evidence.append("Codeforces Educational path convention")
            detection.confidence = "medium"
            return detection
        if part == "others" and idx + 4 < len(parts) and parts[idx + 4].isdigit():
            detection.platform = "codeforces"
            detection.contest_kind = "Others"
            detection.contest_group = normalize_codeforces_contest_group(raw_parts[idx + 1])
            detection.round_number = parts[idx + 4]
            detection.problem_id = leading_problem_id(path.stem)
            detection.evidence.append(
                f"Detected Codeforces Others round {parts[idx + 4]} from path"
            )
            detection.confidence = "medium"
            return detection

    numeric_parts = [part for part in parts if part.isdigit()]
    problem_id = leading_problem_id(path.stem)
    if len(numeric_parts) >= 3 and problem_id and re.fullmatch(r"[a-z][0-9]?", problem_id.lower()):
        detection.platform = "codeforces"
        detection.round_number = numeric_parts[-1]
        detection.problem_id = problem_id
        detection.evidence.append("Codeforces numeric path convention")
        detection.confidence = "medium"

    return detection


def merge_field(
    merged: Detection,
    incoming: Detection,
    field_name: str,
    source: str,
) -> None:
    current = getattr(merged, field_name)
    value = getattr(incoming, field_name)

    if not value:
        return

    if not current:
        setattr(merged, field_name, value)
        return

    if current != value:
        merged.conflicts.append(
            f"{field_name} conflict: kept {current!r}, ignored {value!r} from {source}"
        )


def merge_detection(base: Detection, incoming: Detection, *, source: str) -> Detection:
    confidence_rank = {"none": 0, "low": 1, "medium": 2, "high": 3}
    merged = Detection(
        platform=base.platform,
        contest_id=base.contest_id,
        problem_id=base.problem_id,
        problem_title=base.problem_title,
        contest_kind=base.contest_kind,
        contest_title=base.contest_title,
        round_number=base.round_number,
        contest_group=base.contest_group,
        evidence=[*base.evidence],
        conflicts=[*base.conflicts],
        confidence=base.confidence,
    )

    if confidence_rank[incoming.confidence] > confidence_rank[merged.confidence]:
        merged.confidence = incoming.confidence
    for attr in (
        "platform",
        "contest_id",
        "problem_id",
        "problem_title",
        "contest_kind",
        "contest_title",
        "round_number",
        "contest_group",
    ):
        merge_field(merged, incoming, attr, source)
    merged.evidence.extend(item for item in incoming.evidence if item not in merged.evidence)
    merged.conflicts.extend(item for item in incoming.conflicts if item not in merged.conflicts)
    return merged


def detect_solution(path: Path) -> Detection:
    text_detection = detect_from_text(read_source_text(path))
    filename_detection = detect_from_filename(path)
    path_detection = detect_from_path(path)
    return merge_detection(
        merge_detection(text_detection, filename_detection, source="filename"),
        path_detection,
        source="path",
    )


def apply_overrides(detection: Detection, args: argparse.Namespace) -> Detection:
    overridden = Detection(
        platform=detection.platform,
        contest_id=detection.contest_id,
        problem_id=detection.problem_id,
        problem_title=detection.problem_title,
        contest_kind=detection.contest_kind,
        contest_title=detection.contest_title,
        round_number=detection.round_number,
        contest_group=detection.contest_group,
        evidence=[*detection.evidence],
        conflicts=[*detection.conflicts],
        confidence=detection.confidence,
    )
    overrides = {
        "platform": args.platform,
        "contest_id": args.contest_id,
        "problem_id": args.problem_id,
        "problem_title": args.problem_title,
        "contest_kind": args.contest_kind,
        "contest_title": args.contest_title,
        "round_number": args.round_number,
        "contest_group": args.contest_group,
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
