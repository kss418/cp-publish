from __future__ import annotations

from pathlib import Path

import configure_repos

from .models import PlanError, Route


def relevant_validation_errors(
    platform: str, repo_name: str | None, errors: list[str]
) -> list[str]:
    relevant: list[str] = []
    for error in errors:
        if error.startswith(("version ", "repositories must ", "routes must ", "users must ")):
            relevant.append(error)
        elif error.startswith(f"route {platform} "):
            relevant.append(error)
        elif repo_name and error.startswith(f"repository {repo_name} "):
            relevant.append(error)
        elif repo_name and error == f"invalid repository name: {repo_name}":
            relevant.append(error)
        elif error.startswith(f"user id for {platform} "):
            relevant.append(error)
    return relevant


def relevant_validation_warnings(
    platform: str, repo_name: str | None, warnings: list[str]
) -> list[str]:
    relevant: list[str] = []
    for warning in warnings:
        if warning.startswith(f"route {platform} "):
            relevant.append(warning)
        elif repo_name and warning.startswith(f"repository {repo_name} "):
            relevant.append(warning)
        elif warning.startswith(f"user id for {platform} "):
            relevant.append(warning)
        elif not (
            warning.startswith("route ")
            or warning.startswith("repository ")
            or warning.startswith("user id for ")
        ):
            relevant.append(warning)
    return relevant


def load_route(platform: str, config_path: str | None) -> Route:
    path = Path(config_path).expanduser() if config_path else configure_repos.default_config_path()
    try:
        config = configure_repos.read_config(path)
    except configure_repos.ConfigError as exc:
        raise PlanError(str(exc)) from exc

    errors, validation_warnings = configure_repos.validate_config(config)
    routes = config.get("routes") if isinstance(config.get("routes"), dict) else {}
    route = routes.get(platform)
    repo_name = route.get("repo") if isinstance(route, dict) else None

    relevant_errors = relevant_validation_errors(platform, repo_name, errors)
    if relevant_errors:
        raise PlanError("; ".join(relevant_errors))

    if not isinstance(route, dict):
        raise PlanError(
            f"No configured route for {platform}. Run scripts/configure_repos.py init --platform {platform} first."
        )

    repos = config.get("repositories") if isinstance(config.get("repositories"), dict) else {}
    users = config.get("users") if isinstance(config.get("users"), dict) else {}
    repo = repos.get(repo_name)
    if not isinstance(repo, dict):
        raise PlanError(f"Route for {platform} references missing repository {repo_name!r}.")

    repo_path = configure_repos.normalize_repo_path(repo.get("path", ""))
    base_dir = configure_repos.normalize_base_dir(route.get("base_dir", ""))
    target_base = repo_path / base_dir if base_dir else repo_path
    relevant_warnings = relevant_validation_warnings(
        platform, repo_name, validation_warnings
    )
    return Route(
        repo_path=repo_path,
        base_dir=base_dir,
        target_base=target_base,
        user_id=users.get(platform),
        warnings=relevant_warnings,
    )
