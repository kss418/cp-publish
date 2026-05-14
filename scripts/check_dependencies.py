#!/usr/bin/env python3
"""Check local tools required by the CP publish workflow."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass


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


def command_version(command: list[str]) -> tuple[bool, str | None]:
    executable = command[0]
    if executable != sys.executable and shutil.which(executable) is None:
        return False, None

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
    if has_tool("brew"):
        return ["brew install gh"]

    if has_tool("apt"):
        return [
            "type -p wget >/dev/null || (sudo apt update && sudo apt install wget -y)",
            "sudo mkdir -p -m 755 /etc/apt/keyrings",
            "out=$(mktemp) && wget -nv -O$out https://cli.github.com/packages/githubcli-archive-keyring.gpg && cat $out | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null",
            "sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg",
            "sudo mkdir -p -m 755 /etc/apt/sources.list.d",
            'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null',
            "sudo apt update",
            "sudo apt install gh -y",
        ]

    if has_tool("dnf5"):
        return [
            "sudo dnf install dnf5-plugins -y",
            "sudo dnf config-manager addrepo --from-repofile=https://cli.github.com/packages/rpm/gh-cli.repo",
            "sudo dnf install gh --repo gh-cli -y",
        ]

    if has_tool("dnf"):
        return [
            "sudo dnf install 'dnf-command(config-manager)' -y",
            "sudo dnf config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo",
            "sudo dnf install gh --repo gh-cli -y",
        ]

    if has_tool("yum"):
        return [
            "type -p yum-config-manager >/dev/null || sudo yum install yum-utils -y",
            "sudo yum-config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo",
            "sudo yum install gh -y",
        ]

    if has_tool("zypper"):
        return [
            "sudo zypper addrepo https://cli.github.com/packages/rpm/gh-cli.repo",
            "sudo zypper ref",
            "sudo zypper install -y gh",
        ]

    if has_tool("pacman"):
        return ["sudo pacman -S --needed github-cli"]

    if has_tool("apk"):
        return ["sudo apk add github-cli"]

    if has_tool("conda"):
        return ["conda install gh --channel conda-forge"]

    return ["Open https://github.com/cli/cli/blob/trunk/docs/install_linux.md and choose the command for this distro."]


def linux_git_install_commands() -> list[str]:
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
    if has_tool("brew"):
        return ["brew install git"]
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check CP publish workflow dependencies.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results = check_all()

    if args.json:
        print(json.dumps({"dependencies": results}, indent=2))
    else:
        print_text(results)

    missing_required = [
        item["name"] for item in results if item["required"] and not item["ok"]
    ]
    return 1 if missing_required else 0


if __name__ == "__main__":
    raise SystemExit(main())
