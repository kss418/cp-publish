#!/usr/bin/env python3
"""Check local tools required by the CP publish workflow."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api import http_support


@dataclass(frozen=True)
class Dependency:
    name: str
    command: list[str]
    required: bool
    purpose: str


DEPENDENCIES = [
    Dependency(
        name="git",
        command=["git", "--version"],
        required=True,
        purpose="inspect, commit, and push repository changes",
    ),
    Dependency(
        name="gh",
        command=["gh", "--version"],
        required=True,
        purpose="check GitHub authentication and configure git credentials",
    ),
    Dependency(
        name="python",
        command=[sys.executable, "--version"],
        required=True,
        purpose="run publish helper scripts",
    ),
]


INSTALL_DOCS = {
    "gh": {
        "Windows": "https://github.com/cli/cli/blob/trunk/docs/install_windows.md",
        "Darwin": "https://github.com/cli/cli/blob/trunk/docs/install_macos.md",
        "Linux": "https://github.com/cli/cli/blob/trunk/docs/install_linux.md",
    },
}

HTTPS_PROBES = [
    ("codeforces", "https://codeforces.com/api/user.info?handles=tourist"),
    ("kenkoooo", "https://kenkoooo.com/atcoder/resources/contests.json"),
    ("atcoder", "https://atcoder.jp/"),
]


def user_local_tool(name: str) -> Path | None:
    if platform.system() != "Linux":
        return None
    return Path.home() / ".local" / "bin" / name


def tool_path(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found

    candidate = user_local_tool(name)
    if candidate and candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)

    return None


def script_command(script_name: str) -> str:
    script = Path(__file__).resolve().with_name(script_name)
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"


def command_version(command: list[str]) -> tuple[bool, str | None]:
    executable = command[0]
    if executable != sys.executable:
        resolved = tool_path(executable)
        if resolved is None:
            return False, None
        command = [resolved, *command[1:]]

    result = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = result.stdout.strip().splitlines()
    version = output[0] if output else None
    return result.returncode == 0, version


def has_tool(name: str) -> bool:
    return shutil.which(name) is not None


def windows_install_commands(name: str) -> list[str]:
    if name == "gh":
        commands = []
        if has_tool("winget"):
            commands.append("winget install --id GitHub.cli --source winget")
        if has_tool("choco"):
            commands.append("choco install gh")
        if has_tool("scoop"):
            commands.append("scoop install gh")
        return commands or ["Install GitHub CLI from https://cli.github.com/"]

    if name == "git":
        commands = []
        if has_tool("winget"):
            commands.append("winget install --id Git.Git --source winget")
        if has_tool("choco"):
            commands.append("choco install git")
        if has_tool("scoop"):
            commands.append("scoop install git")
        return commands or ["Install Git from https://git-scm.com/download/win"]

    return []


def macos_install_commands(name: str) -> list[str]:
    if name == "gh":
        commands = []
        if has_tool("brew"):
            commands.append("brew install gh")
        if has_tool("port"):
            commands.append("sudo port install gh")
        if has_tool("conda"):
            commands.append("conda install gh --channel conda-forge")
        return commands or ["Install Homebrew, then run `brew install gh`"]

    if name == "git":
        commands = []
        if has_tool("brew"):
            commands.append("brew install git")
        if has_tool("port"):
            commands.append("sudo port install git")
        return commands or ["Install Xcode Command Line Tools with `xcode-select --install`"]

    return []


def linux_gh_install_commands() -> list[str]:
    return [script_command("install_gh_user.py")]


def linux_git_install_commands() -> list[str]:
    if has_tool("brew"):
        return ["brew install git"]
    if has_tool("conda"):
        return ["conda install git --channel conda-forge"]
    if has_tool("apt"):
        return ["sudo apt-get install -y git"]
    if has_tool("dnf"):
        return ["sudo dnf install -y git"]
    if has_tool("yum"):
        return ["sudo yum install -y git"]
    if has_tool("zypper"):
        return ["sudo zypper install -y git"]
    if has_tool("pacman"):
        return ["sudo pacman -S --needed git"]
    if has_tool("apk"):
        return ["sudo apk add git"]
    return ["Install git with this distro's package manager."]


def linux_install_commands(name: str) -> list[str]:
    if name == "gh":
        return linux_gh_install_commands()
    if name == "git":
        return linux_git_install_commands()
    return []


def install_commands(name: str) -> list[str]:
    system = platform.system()
    if system == "Windows":
        return windows_install_commands(name)
    if system == "Darwin":
        return macos_install_commands(name)
    if system == "Linux":
        return linux_install_commands(name)
    return []


def install_command(name: str) -> str | None:
    commands = install_commands(name)
    return commands[0] if commands else None


def install_docs(name: str) -> str | None:
    return INSTALL_DOCS.get(name, {}).get(platform.system())


def check_all() -> list[dict[str, object]]:
    results = []
    for dependency in DEPENDENCIES:
        ok, version = command_version(dependency.command)
        commands = [] if ok else install_commands(dependency.name)
        results.append(
            {
                "name": dependency.name,
                "ok": ok,
                "required": dependency.required,
                "purpose": dependency.purpose,
                "version": version,
                "install_command": commands[0] if commands else None,
                "install_commands": commands,
                "install_docs": None if ok else install_docs(dependency.name),
            }
        )
    return results


def check_https(timeout: int) -> dict[str, object]:
    probes = []
    for name, url in HTTPS_PROBES:
        result = http_support.probe_https(url, timeout=timeout)
        result["name"] = name
        probes.append(result)

    return {
        "ok": all(bool(item["ok"]) for item in probes),
        "probes": probes,
        "diagnostics": http_support.https_diagnostics(),
    }


def print_text(results: list[dict[str, object]]) -> None:
    for item in results:
        status = "ok" if item["ok"] else "missing"
        print(f"{item['name']}: {status}")
        print(f"  purpose: {item['purpose']}")
        if item["version"]:
            print(f"  version: {item['version']}")
        if item["install_command"]:
            print(f"  install_command: {item['install_command']}")
        commands = item.get("install_commands") or []
        if len(commands) > 1:
            print("  install_commands:")
            for command in commands:
                print(f"    - {command}")
        if item["install_docs"]:
            print(f"  docs: {item['install_docs']}")


def print_https(result: dict[str, object]) -> None:
    print("https: ok" if result["ok"] else "https: failed")

    diagnostics = result["diagnostics"]
    assert isinstance(diagnostics, dict)
    print(f"  python: {diagnostics['python']}")
    print(f"  openssl: {diagnostics['openssl']}")
    print(f"  selected_ca_bundle: {diagnostics['selected_ca_bundle'] or '(default)'}")

    probes = result["probes"]
    assert isinstance(probes, list)
    for item in probes:
        assert isinstance(item, dict)
        status = "tls ok" if item["ok"] else "failed"
        print(f"  {item['name']}: {status}")
        print(f"    url: {item['url']}")
        if item["status"]:
            print(f"    http_status: {item['status']}")
        if item["error"]:
            print("    error:")
            for line in str(item["error"]).splitlines():
                print(f"      {line}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check CP publish workflow dependencies.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--https",
        action="store_true",
        help="Also verify Python HTTPS/TLS access to Codeforces, Kenkoooo, and AtCoder.",
    )
    parser.add_argument(
        "--https-timeout",
        type=int,
        default=10,
        help="HTTPS probe timeout in seconds. Used only with --https.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results = check_all()
    https_result = check_https(args.https_timeout) if args.https else None

    if args.json:
        payload: dict[str, object] = {"dependencies": results}
        if https_result is not None:
            payload["https"] = https_result
        print(json.dumps(payload, indent=2))
    else:
        print_text(results)
        if https_result is not None:
            print_https(https_result)

    missing_required = [
        item["name"] for item in results if item["required"] and not item["ok"]
    ]
    https_failed = https_result is not None and not bool(https_result["ok"])
    return 1 if missing_required or https_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
