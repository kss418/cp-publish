#!/usr/bin/env python3
"""Install GitHub CLI into the current user's home directory on Linux."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import stat
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


LATEST_RELEASE_API = "https://api.github.com/repos/cli/cli/releases/latest"
USER_AGENT = "cp-publish-gh-user-installer"


def linux_asset_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "amd64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    if machine.startswith("armv6"):
        return "armv6"
    raise RuntimeError(f"Unsupported Linux architecture for gh user install: {machine}")


def request_url(url: str, *, timeout: int) -> urllib.request.addinfourl:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=timeout)


def fetch_latest_release(*, timeout: int) -> dict[str, Any]:
    with request_url(LATEST_RELEASE_API, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def select_linux_tarball(release: dict[str, Any]) -> tuple[str, str]:
    arch = linux_asset_arch()
    suffix = f"_linux_{arch}.tar.gz"
    for asset in release.get("assets", []):
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name", ""))
        url = str(asset.get("browser_download_url", ""))
        if name.endswith(suffix) and url:
            return name, url
    tag = release.get("tag_name", "latest")
    raise RuntimeError(f"No gh {tag} Linux tarball found for architecture: {arch}")


def download(url: str, destination: Path, *, timeout: int) -> None:
    with request_url(url, timeout=timeout) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def safe_extract_tarball(archive_path: Path, destination: Path) -> None:
    root = destination.resolve()
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"Refusing unsafe tar entry: {member.name}")
        archive.extractall(destination)


def find_gh_binary(extract_dir: Path) -> Path:
    matches = sorted(extract_dir.glob("gh_*_linux_*/bin/gh"))
    if not matches:
        matches = sorted(extract_dir.rglob("bin/gh"))
    if not matches:
        raise RuntimeError("Downloaded gh archive did not contain bin/gh")
    return matches[0]


def install_binary(source: Path, bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    target = bin_dir / "gh"
    temp_target = bin_dir / ".gh.tmp"
    shutil.copy2(source, temp_target)
    mode = temp_target.stat().st_mode
    temp_target.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(temp_target, target)
    return target


def path_contains(directory: Path) -> bool:
    directory_text = str(directory)
    return any(item == directory_text for item in os.environ.get("PATH", "").split(os.pathsep))


def install_gh(*, bin_dir: Path, timeout: int) -> Path:
    if platform.system() != "Linux":
        raise RuntimeError("User-local gh installer is only supported on Linux.")

    release = fetch_latest_release(timeout=timeout)
    asset_name, asset_url = select_linux_tarball(release)
    print(f"downloading: {asset_name}")

    with tempfile.TemporaryDirectory(prefix="cp-publish-gh-") as temp:
        temp_dir = Path(temp)
        archive_path = temp_dir / asset_name
        download(asset_url, archive_path, timeout=timeout)
        safe_extract_tarball(archive_path, temp_dir / "extract")
        return install_binary(find_gh_binary(temp_dir / "extract"), bin_dir)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install GitHub CLI to ~/.local/bin without sudo."
    )
    parser.add_argument(
        "--bin-dir",
        type=Path,
        default=Path.home() / ".local" / "bin",
        help="Directory that receives the gh executable. Defaults to ~/.local/bin.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Network timeout in seconds for GitHub release requests.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        target = install_gh(bin_dir=args.bin_dir.expanduser(), timeout=args.timeout)
    except Exception as exc:
        print(f"error: {exc}")
        return 1

    print(f"installed: {target}")
    if not path_contains(target.parent):
        print(f"note: {target.parent} is not on PATH for this shell.")
        print('add it with: export PATH="$HOME/.local/bin:$PATH"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
