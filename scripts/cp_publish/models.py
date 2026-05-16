from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


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
TAG_MAP_PATH = Path(__file__).resolve().parents[2] / "references" / "solvedac-tag-map.json"
CODEFORCES_CONTEST_RULE_MAP_PATH = (
    Path(__file__).resolve().parents[2] / "references" / "codeforces-contest-rule-map.json"
)


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
    round_number: str | None = None
    contest_group: str | None = None
    evidence: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
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
