# CP Publish Workflow Reference

This reference contains detailed command examples for the `cp-publish` skill. Keep `SKILL.md` focused on mandatory workflow and safety rules; load this file when exact command syntax is needed.

## Command Working Directory

For commands that write files, update a target Git repository, or use GitHub credentials, run from the resolved target repository or another known writable workspace. Treat the skill directory as read-only runtime code and call bundled scripts with an absolute `skill_root` path when the working directory is not the skill root.

Use repository-local temporary plan files, then remove them before committing:

```powershell
$skillRoot = "C:\path\to\cp-publish-skill"
$repo = "C:\path\to\resolved\repo"
Set-Location $repo
```

```sh
skill_root=/path/to/cp-publish-skill
repo=/path/to/resolved/repo
cd "$repo"
```

If a command needs to write `.git/index`, push, access the `gh` keyring, write outside the active writable root, or access metadata/results over the network, request sandbox escalation on the first attempt.

## Session Gate Cache

During one Codex session, remember successful gate checks for:

- dependency check: Python environment plus `git`/`gh` availability
- GitHub auth check: active `gh` account and git protocol
- route check: platform, resolved repo path, `base_dir`, `target_base`, and `user_id`

For another publish in the same session and same resolved repository, skip rerunning the matching gate when the cached values still apply. Rerun only the affected gate if the platform, repository path, config file, `user_id`, remote, branch, GitHub account, Python executable, or tool availability changes.

Do not cache failed checks. If a later git, gh, metadata, result, or push command fails in a way that suggests auth/config/environment drift, rerun the relevant gate before continuing.

The session cache does not replace per-publish safety checks: always inspect the current working tree, build a fresh plan, dry-run the plan, inspect warnings/conflicts, and commit explicit paths only.

## Solution Build Validation

Do not compile or run solution source files during routine publishing. The publish workflow validates detection, paths, README updates, git scope, and push behavior; it does not validate algorithm correctness or language compilation by default.

Compile or run source code only when the user explicitly requests solution verification/debugging, or when there is local evidence of file corruption or a mismatched extension. Keep any compilation result separate from publish gate status.

## Dependency And Auth

Check required tools before modifying files:

```powershell
python scripts/init/check_dependencies.py
python scripts/init/check_dependencies.py --json
```

```sh
python3 scripts/init/check_dependencies.py
python3 scripts/init/check_dependencies.py --json
```

Required tools:

- `git`: inspect, stage, commit, and push repository changes.
- `gh`: check GitHub authentication and configure git credentials.
- `python`: run helper scripts.

When HTTPS/TLS fails with `CERTIFICATE_VERIFY_FAILED`, diagnose with:

```powershell
python scripts/init/check_dependencies.py --https
```

```sh
python3 scripts/init/check_dependencies.py --https
```

If a dependency is missing, preview installation before asking the user:

```powershell
python scripts/init/install_dependencies.py --dry-run
python scripts/init/install_dependencies.py --only gh --dry-run
```

```sh
python3 scripts/init/install_dependencies.py --dry-run
python3 scripts/init/install_dependencies.py --only gh --dry-run
```

Codex may run the installer only after explicit approval:

```powershell
python scripts/init/install_dependencies.py --yes
python scripts/init/install_dependencies.py --only gh --yes
```

```sh
python3 scripts/init/install_dependencies.py --yes
python3 scripts/init/install_dependencies.py --only gh --yes
```

On Linux, missing `gh` installs without sudo through `scripts/init/install_gh_user.py` into `~/.local/bin`. If a dry-run plan says `automatic: no` or contains `sudo`/`pkexec`, treat it as a manual OS administration step and ask the user to run it themselves.

Verify GitHub authentication:

```powershell
python scripts/init/github_integration.py auth
python scripts/init/github_integration.py auth --login
```

```sh
python3 scripts/init/github_integration.py auth
python3 scripts/init/github_integration.py auth --login
```

For Codex-run auth checks and interactive login, request network escalation from the first attempt. Never ask for or store GitHub tokens, passwords, cookies, or credentials.

## Repository Routing

Require repository routing before identifying, moving, committing, or pushing a solution. Supported platforms:

- `atcoder`
- `codeforces`

Create or update config:

```powershell
python scripts/init/configure_repos.py init
python scripts/init/configure_repos.py init --platform codeforces --codeforces-repo C:\path\to\codeforces --codeforces-base-dir .
python scripts/init/configure_repos.py init --platform atcoder --atcoder-repo C:\path\to\atcoder --atcoder-base-dir .
python scripts/init/configure_repos.py init --platform both --atcoder-repo C:\path\to\atcoder --codeforces-repo C:\path\to\codeforces --atcoder-base-dir . --codeforces-base-dir .
python scripts/init/configure_repos.py init --platform both --atcoder-repo C:\path\to\cp-solutions --codeforces-repo C:\path\to\cp-solutions --atcoder-base-dir atcoder --codeforces-base-dir codeforces
```

```sh
python3 scripts/init/configure_repos.py init
python3 scripts/init/configure_repos.py init --platform codeforces --codeforces-repo /path/to/codeforces --codeforces-base-dir .
python3 scripts/init/configure_repos.py init --platform atcoder --atcoder-repo /path/to/atcoder --atcoder-base-dir .
python3 scripts/init/configure_repos.py init --platform both --atcoder-repo /path/to/atcoder --codeforces-repo /path/to/codeforces --atcoder-base-dir . --codeforces-base-dir .
python3 scripts/init/configure_repos.py init --platform both --atcoder-repo /path/to/cp-solutions --codeforces-repo /path/to/cp-solutions --atcoder-base-dir atcoder --codeforces-base-dir codeforces
```

Validate and resolve only the platform being published. A broken unused route should not block the current platform:

```powershell
python scripts/init/configure_repos.py validate --platform atcoder
python scripts/init/configure_repos.py resolve atcoder
python scripts/init/configure_repos.py validate --platform codeforces
python scripts/init/configure_repos.py resolve codeforces
```

```sh
python3 scripts/init/configure_repos.py validate --platform atcoder
python3 scripts/init/configure_repos.py resolve atcoder
python3 scripts/init/configure_repos.py validate --platform codeforces
python3 scripts/init/configure_repos.py resolve codeforces
```

Save platform IDs for README result tables:

```powershell
python scripts/init/configure_repos.py user atcoder --id <atcoder_id>
python scripts/init/configure_repos.py user codeforces --id <codeforces_handle>
```

```sh
python3 scripts/init/configure_repos.py user atcoder --id <atcoder_id>
python3 scripts/init/configure_repos.py user codeforces --id <codeforces_handle>
```

## Metadata And Results

Use metadata scripts when contest titles, problem titles, ratings, or Codeforces round placement are needed.

```powershell
python scripts/api/codeforces_metadata.py contests
python scripts/api/codeforces_metadata.py problems
python scripts/api/codeforces_metadata.py all
python scripts/api/atcoder_metadata.py contests
python scripts/api/atcoder_metadata.py problems
python scripts/api/atcoder_metadata.py merged-problems
python scripts/api/atcoder_metadata.py contest-problems
python scripts/api/atcoder_metadata.py ratings
python scripts/api/atcoder_metadata.py all
python scripts/api/atcoder_metadata.py problem abc422_a
python scripts/api/atcoder_metadata.py rating abc422_a
```

```sh
python3 scripts/api/codeforces_metadata.py contests
python3 scripts/api/codeforces_metadata.py problems
python3 scripts/api/codeforces_metadata.py all
python3 scripts/api/atcoder_metadata.py contests
python3 scripts/api/atcoder_metadata.py problems
python3 scripts/api/atcoder_metadata.py merged-problems
python3 scripts/api/atcoder_metadata.py contest-problems
python3 scripts/api/atcoder_metadata.py ratings
python3 scripts/api/atcoder_metadata.py all
python3 scripts/api/atcoder_metadata.py problem abc422_a
python3 scripts/api/atcoder_metadata.py rating abc422_a
```

For `plan_publish.py`, use `--refresh-metadata` only when the user explicitly requests fresh metadata. For metadata and result helper scripts, use `--refresh`. If a fetch fails because network access is blocked, request approval to rerun the same command with network access.

Use result scripts when README work needs the user's per-problem wrong attempts and accepted time:

```powershell
python scripts/api/codeforces_results.py contest --contest-id 2061 --user <codeforces_handle>
python scripts/api/atcoder_results.py contest --contest-id abc422 --user <atcoder_id>
python scripts/api/atcoder_results.py contest --contest-id abc422 --user <atcoder_id> --source kenkoooo-submissions
```

```sh
python3 scripts/api/codeforces_results.py contest --contest-id 2061 --user <codeforces_handle>
python3 scripts/api/atcoder_results.py contest --contest-id abc422 --user <atcoder_id>
python3 scripts/api/atcoder_results.py contest --contest-id abc422 --user <atcoder_id> --source kenkoooo-submissions
```

For Codeforces, `codeforces_results.py contest` uses the user's bulk `user.status` response by default and caches it for 1 hour. This lets multi-contest README updates reuse one user submission fetch instead of calling a contest endpoint for every contest. Use `--standings` only when official standings data is required, and use `--fallback-standings` only when the bulk status path is insufficient.

When result JSON is available, pass it to `scripts/cp_publish/update_readme.py --results-json`. If the user has no contest-time submissions, skip the result table and continue with the solution entry only.

## Plan And Apply

Build a plan before changing files:

```powershell
python "$skillRoot\scripts\cp_publish\plan_publish.py" C:\path\to\solution.cpp --tags DP,Greedy
```

```sh
python3 "$skill_root/scripts/cp_publish/plan_publish.py" /path/to/solution.cpp --tags DP,Greedy
```

Apply confirmed plans through `scripts/cp_publish/apply_plan.py`:

```powershell
$planDir = Join-Path $repo ".cp-publish-plans"
New-Item -ItemType Directory -Force -Path $planDir | Out-Null
python "$skillRoot\scripts\cp_publish\plan_publish.py" C:\path\to\solution.cpp --tags DP,Greedy > "$planDir\cp-plan.json"
python "$skillRoot\scripts\cp_publish\apply_plan.py" --plan "$planDir\cp-plan.json" --copy --dry-run
python "$skillRoot\scripts\cp_publish\apply_plan.py" --plan "$planDir\cp-plan.json" --copy
Remove-Item -LiteralPath "$planDir\cp-plan.json"
```

```sh
plan_dir="$repo/.cp-publish-plans"
mkdir -p "$plan_dir"
python3 "$skill_root/scripts/cp_publish/plan_publish.py" /path/to/solution.cpp --tags DP,Greedy > "$plan_dir/cp-plan.json"
python3 "$skill_root/scripts/cp_publish/apply_plan.py" --plan "$plan_dir/cp-plan.json" --copy --dry-run
python3 "$skill_root/scripts/cp_publish/apply_plan.py" --plan "$plan_dir/cp-plan.json" --copy
rm "$plan_dir/cp-plan.json"
```

`apply_plan.py` verifies the source file, creates target parents, copies or moves the solution, runs each README update's `contest_result_command` by default, passes fetched JSON to `update_readme.py --results-json`, and prints `changed_paths` plus `commit_paths`. Result fetch failures are warnings while the solution entry still updates. Use `--no-results` only when result lookup should be skipped, and use `--require-results` when result fetch failure should fail the apply. It refuses plans with `needs_confirmation: true` unless the user has explicitly confirmed and the command is rerun with `--allow-confirmation`.

## Batch Plan And Apply

Use `scripts/cp_publish/batch_publish.py` when publishing more than one source file. It builds a plan for each source, validates the batch, prints one JSON dry-run summary, shares result fetches across README updates by command, applies all file operations in one loop, and returns combined `commit_paths` plus `suggested_commit_message`.

For non-trivial batches, save the dry-run plan and apply that saved plan. This avoids rebuilding detection and metadata work during apply:

Folder migration example:

```powershell
Set-Location $repo
$planDir = Join-Path $repo ".cp-publish-plans"
New-Item -ItemType Directory -Force -Path $planDir | Out-Null
$batchPlan = Join-Path $planDir "batch.json"
python "$skillRoot\scripts\cp_publish\batch_publish.py" --from-dir C:\path\to\contest --move --dry-run --tags-from-readme --save-plan "$batchPlan"
python "$skillRoot\scripts\cp_publish\batch_publish.py" --apply-plan "$batchPlan"
Remove-Item -LiteralPath "$batchPlan"
```

```sh
cd "$repo"
plan_dir="$repo/.cp-publish-plans"
mkdir -p "$plan_dir"
batch_plan="$plan_dir/batch.json"
python3 "$skill_root/scripts/cp_publish/batch_publish.py" --from-dir /path/to/contest --move --dry-run --tags-from-readme --save-plan "$batch_plan"
python3 "$skill_root/scripts/cp_publish/batch_publish.py" --apply-plan "$batch_plan"
rm "$batch_plan"
```

Multiple explicit files:

```powershell
python "$skillRoot\scripts\cp_publish\batch_publish.py" --move --dry-run --tags DP,Greedy C:\path\to\A.cpp C:\path\to\B.cpp
```

```sh
python3 "$skill_root/scripts/cp_publish/batch_publish.py" --move --dry-run --tags DP,Greedy /path/to/A.cpp /path/to/B.cpp
```

Useful options:

- `--tags-from-readme`: use existing per-problem README tags when migrating an old contest folder.
- `--problem-id-from-filename`: use trusted filename prefixes such as `A`, `C1`, or `G-1` as problem IDs.
- `--no-results`: skip result lookup; by default, batch publishing fetches each unique contest/user result once.
- `--require-results`: fail the batch if a required result fetch fails.
- `--allow-confirmation`: apply plans that were already reviewed and confirmed.
- `--save-plan <path>`: save the built batch plan bundle after planning.
- `--apply-plan <path>`: load a saved batch plan bundle and apply or dry-run it without rebuilding plans.

If any plan has errors or `needs_confirmation` and `--allow-confirmation` is not passed, the batch prints a blocked summary and writes nothing.

## README Updates

Use `scripts/cp_publish/update_readme.py` directly only when applying a full plan is not appropriate:

```powershell
python scripts/cp_publish/update_readme.py --contest-dir C:\path\to\contest --contest-url https://codeforces.com/contest/2061 --problem-id A --rating 800 --tags Case_Work
python scripts/cp_publish/update_readme.py --contest-dir C:\path\to\contest --contest-url https://atcoder.jp/contests/abc422 --problem-id A --rating - --tags Case_Work
python scripts/cp_publish/update_readme.py --contest-dir C:\path\to\contest --contest-url https://codeforces.com/contest/2061 --problem-id A --rating 800 --tags Case_Work --results-json C:\path\to\results.json
```

```sh
python3 scripts/cp_publish/update_readme.py --contest-dir /path/to/contest --contest-url https://codeforces.com/contest/2061 --problem-id A --rating 800 --tags Case_Work
python3 scripts/cp_publish/update_readme.py --contest-dir /path/to/contest --contest-url https://atcoder.jp/contests/abc422 --problem-id A --rating - --tags Case_Work
python3 scripts/cp_publish/update_readme.py --contest-dir /path/to/contest --contest-url https://codeforces.com/contest/2061 --problem-id A --rating 800 --tags Case_Work --results-json /path/to/results.json
```

## GitHub Helpers

Use the bundled GitHub helper for safe status, auth, commit, and push operations:

```powershell
Set-Location $repo
python "$skillRoot\scripts\init\github_integration.py" status
python "$skillRoot\scripts\init\github_integration.py" commit -m "Add AtCoder ABC350 A solution" path/to/file.cpp
python "$skillRoot\scripts\init\github_integration.py" push --dry-run
python "$skillRoot\scripts\init\github_integration.py" push
```

```sh
cd "$repo"
python3 "$skill_root/scripts/init/github_integration.py" status
python3 "$skill_root/scripts/init/github_integration.py" commit -m "Add AtCoder ABC350 A solution" path/to/file.cpp
python3 "$skill_root/scripts/init/github_integration.py" push --dry-run
python3 "$skill_root/scripts/init/github_integration.py" push
```

Stage and commit only explicit paths. Preserve unrelated user changes in the working tree.
