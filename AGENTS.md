# Project Overview

This project automates publishing competitive programming solutions to a GitHub repository.

The main use case is: after the user solves an AtCoder or Codeforces problem locally, Codex can be invoked to identify the problem, normalize the file location and name, update repository indexes, run lightweight validation, commit the change, and push it to the configured remote GitHub repository.

## Goals

- Detect whether a solution belongs to AtCoder or Codeforces.
- Infer contest ID, problem ID, language, and target path from reliable metadata.
- Organize solution files using the repository's existing directory conventions.
- Update README, index, or problem list files when applicable.
- Run compile/test checks when the language and local environment support it.
- Commit and push the solution to GitHub with a consistent commit message.
- Keep authentication secure by relying on `gh` and `git`, never stored tokens.

## Non-Goals

- Do not solve the competitive programming problem unless explicitly asked.
- Do not submit solutions to AtCoder or Codeforces.
- Do not scrape private account data.
- Do not force-push, rewrite git history, or delete existing solutions unless explicitly requested.
- Do not publish a solution when the contest/problem identity is ambiguous.

## Expected Workflow

When asked to publish a solution:

1. Inspect the current git repository and working tree.
2. Identify the candidate solution file from the user prompt, recent changes, or current directory.
3. Detect problem metadata using this priority order:
   - Explicit URL in source comments.
   - Structured metadata comments in the source file.
   - Existing directory path.
   - Filename pattern.
   - User prompt.
4. If confidence is low or multiple problems are plausible, ask the user for confirmation before modifying files or pushing.
5. Move or copy the solution into the expected repository path.
6. Update repository indexes such as README files if the project uses them.
7. Run available validation:
   - Compile C++/Rust/Java where reasonable.
   - Run Python syntax checks where reasonable.
   - Run project-provided scripts if present.
8. Check GitHub authentication with `gh auth status`.
9. If authentication is missing, run the configured setup/auth script or guide the user through `gh auth login --web`.
10. Commit with a clear message.
11. Push to the configured remote.

## Authentication Rules

GitHub authentication must be handled through GitHub CLI and git credential helpers.

- Use `gh auth status` to check login state.
- Use `gh auth login --web` when login is required.
- Use `gh auth setup-git` after login if needed.
- Never ask the user for a GitHub password or token.
- Never write tokens, cookies, or credentials into project files, skill files, logs, commits, or config templates.

## Detection Policy

Prefer explicit metadata over guesses.

Good signals include:

- `https://atcoder.jp/contests/abc350/tasks/abc350_a`
- `https://codeforces.com/problemset/problem/1900/A`
- `abc350_a.cpp`
- `ABC350A.py`
- `atcoder/abc350/a.cpp`
- `codeforces/1900/a.cpp`

Weak signals include:

- `a.cpp`
- `main.py`
- `solution.cpp`
- `solve.rs`
- `d.cpp`

If only weak signals are available, stop and ask the user to confirm the platform, contest, and problem.

## Safety Rules

- Preserve existing user changes.
- Do not overwrite an existing solution unless it clearly refers to the same problem and the user intended an update.
- Do not run destructive git commands.
- Do not force-push.
- Do not commit unrelated changes.
- Show the planned file moves and index updates before publishing when the change is non-trivial.
- If validation fails, do not push unless the user explicitly asks to publish anyway.

## Commit Message Style

Use concise commit messages like:

- `Add AtCoder ABC350 A solution`
- `Add Codeforces 1900A solution`
- `Update AtCoder ABC350 B solution`

Prefer platform, contest, and problem ID in the message.
