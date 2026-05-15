from __future__ import annotations

from pathlib import Path

import configure_repos

from .models import PlanError, Route


def load_route(platform: str, config_path: str | None) -> Route:
    path = Path(config_path).expanduser() if config_path else configure_repos.default_config_path()
    try:
        config = configure_repos.read_config(path)
    except configure_repos.ConfigError as exc:
        raise PlanError(str(exc)) from exc

    errors, validation_warnings = configure_repos.validate_config(config)
    if errors:
        raise PlanError("; ".join(errors))

    route = (config.get("routes") or {}).get(platform)
    if not route:
        raise PlanError(
            f"No configured route for {platform}. Run scripts/configure_repos.py init --platform {platform} first."
        )

    repos = config.get("repositories") or {}
    users = config.get("users") or {}
    repo_name = route.get("repo")
    repo = repos.get(repo_name)
    if not repo:
        raise PlanError(f"Route for {platform} references missing repository {repo_name!r}.")

    repo_path = configure_repos.normalize_repo_path(repo.get("path", ""))
    base_dir = configure_repos.normalize_base_dir(route.get("base_dir", ""))
    target_base = repo_path / base_dir if base_dir else repo_path
    relevant_warnings = [
        warning
        for warning in validation_warnings
        if not warning.startswith("route ") or warning.startswith(f"route {platform} ")
    ]
    return Route(
        repo_path=repo_path,
        base_dir=base_dir,
        target_base=target_base,
        user_id=users.get(platform),
        warnings=relevant_warnings,
    )
