#!/usr/bin/env python3
"""Install missing CP publish workflow dependencies after user approval."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

import check_dependencies


MANUAL_PREFIXES = ("Install ", "Open ")


@dataclass(frozen=True)
class InstallPlan:
    name: str
    purpose: str
    commands: list[str]
    docs: str | None
    manual: bool


def is_manual_command(command: str) -> bool:
    return command.startswith(MANUAL_PREFIXES)


def command_sequence_for(item: dict[str, Any]) -> list[str]:
    commands = [str(command) for command in item.get("install_commands") or []]
    if not commands:
        command = item.get("install_command")
        return [str(command)] if command else []

    system = platform.system()
    if system in {"Windows", "Darwin"}:
        return [commands[0]]

    return commands


def build_plans(only: set[str] | None) -> tuple[list[InstallPlan], list[dict[str, Any]]]:
    results = check_dependencies.check_all()
    plans: list[InstallPlan] = []

    for item in results:
        name = str(item["name"])
        if only and name not in only:
            continue
        if item["ok"]:
            continue

        commands = command_sequence_for(item)
        manual = not commands or any(is_manual_command(command) for command in commands)
        plans.append(
            InstallPlan(
                name=name,
                purpose=str(item["purpose"]),
                commands=commands,
                docs=item.get("install_docs") if isinstance(item.get("install_docs"), str) else None,
                manual=manual,
            )
        )

    return plans, results


def print_check_summary(results: list[dict[str, Any]]) -> None:
    for item in results:
        status = "ok" if item["ok"] else "missing"
        print(f"{item['name']}: {status}")
        if item.get("version"):
            print(f"  version: {item['version']}")


def print_plan(plans: list[InstallPlan]) -> None:
    if not plans:
        print("All selected dependencies are already installed.")
        return

    print("Missing dependencies:")
    for plan in plans:
        print(f"- {plan.name}: {plan.purpose}")
        if plan.docs:
            print(f"  docs: {plan.docs}")
        if plan.commands:
            print("  commands:")
            for command in plan.commands:
                print(f"    {command}")
        else:
            print("  commands: none")


def confirm(prompt: str) -> bool:
    if not sys.stdin.isatty():
        print(f"{prompt} [y/N] N")
        return False
    answer = input(f"{prompt} [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def run_command(command: str) -> int:
    print(f"running: {command}")
    result = subprocess.run(command, shell=True, check=False)
    return result.returncode


def install_plan(plan: InstallPlan, *, assume_yes: bool) -> bool:
    if plan.manual:
        print(f"{plan.name}: no safe automatic install command is available.")
        if plan.docs:
            print(f"docs: {plan.docs}")
        for command in plan.commands:
            print(f"manual: {command}")
        return False

    if not assume_yes and not confirm(f"Install {plan.name} now?"):
        print(f"skipped: {plan.name}")
        return False

    for command in plan.commands:
        returncode = run_command(command)
        if returncode != 0:
            print(f"failed: {command} (exit {returncode})")
            return False

    return True


def json_plan(plans: list[InstallPlan]) -> dict[str, Any]:
    return {
        "missing": [
            {
                "name": plan.name,
                "purpose": plan.purpose,
                "commands": plan.commands,
                "docs": plan.docs,
                "manual": plan.manual,
            }
            for plan in plans
        ]
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install missing CP publish dependencies after approval."
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=[dependency.name for dependency in check_dependencies.DEPENDENCIES],
        help="Install only this dependency. Can be repeated.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show the install plan only.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Run install commands without interactive prompts. Use only after explicit approval.",
    )
    parser.add_argument("--json", action="store_true", help="Print the install plan as JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    only = set(args.only) if args.only else None
    plans, results = build_plans(only)

    if args.json:
        print(json.dumps(json_plan(plans), indent=2))
        return 0
    else:
        print_check_summary(results)
        print()
        print_plan(plans)

    if not plans:
        return 0
    if args.dry_run:
        return 0

    installed = [install_plan(plan, assume_yes=args.yes) for plan in plans]
    if not all(installed):
        return 1

    remaining, _ = build_plans(only)
    if remaining:
        print("Some dependencies are still missing after installation:")
        print_plan(remaining)
        return 1

    print("All selected dependencies are installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
