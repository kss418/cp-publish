from __future__ import annotations

import argparse
import json
import re

from .models import PlanError, TAG_MAP_PATH


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
