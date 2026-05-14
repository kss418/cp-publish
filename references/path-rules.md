# Path Rules

Use these rules after platform detection and after resolving repository routing with:

```text
scripts/configure_repos.py resolve <platform>
```

The resolved `target_base` is the root for all file placement. Never place a solution outside `target_base`.

## Supported Platforms

Only these platforms are supported:

- `atcoder`
- `codeforces`

If the platform is not one of these values, stop and ask the user.

## Language Extensions

Preserve the source language by extension. Normalize common extensions as follows:

| Language | Input extensions | Stored extension |
| --- | --- | --- |
| C++ | `.cpp`, `.cc`, `.cxx` | `.cpp` |
| C | `.c` | `.c` |
| Python | `.py`, `.py3` | `.py` |
| Rust | `.rs` | `.rs` |
| Java | `.java` | `.java` |
| Kotlin | `.kt` | `.kt` |
| Go | `.go` | `.go` |

If the extension is unknown, keep the original extension and ask for confirmation before publishing.

## AtCoder

For numeric AtCoder contest series, use:

```text
<target_base>/<series>/<hundreds_bucket>/<tens_bucket>/<contest_number>/<problem_label>_<problem_title_slug>.<ext>
```

For PAST, use:

```text
<target_base>/PAST/<past_contest_key>/<problem_label>_<problem_title_slug>.<ext>
```

Normalize:

- `series`: uppercase contest series. Supported values are `ABC`, `ARC`, `AGC`, `AHC`, and `PAST`.
- `contest_number`: integer contest number without leading zeroes for `ABC`, `ARC`, `AGC`, and `AHC`, for example `422`.
- `hundreds_bucket`: `(contest_number // 100) * 100`, for example `422 -> 400`. Use this for `ABC`, `ARC`, `AGC`, and `AHC`.
- `tens_bucket`: `(contest_number // 10) * 10`, for example `422 -> 420`. Use this for `ABC`, `ARC`, `AGC`, and `AHC`.
- `past_contest_key`: the PAST contest key without the leading `past`, for example `past202309-open -> 202309-open`.
- `problem_label`: problem number or task label, for example `A`, `B`, `C`, or `Ex`.
- `problem_title_slug`: problem title with spaces replaced by underscores and unsafe filename characters removed.
- `ext`: normalized language extension.

Filename format:

```text
<problem_label>_<problem_title_slug>.<ext>
```

Preserve useful capitalization in the problem title, as in `A_Stage_Clear.cpp`. If the problem title is unavailable from reliable metadata, ask the user before publishing.

Examples:

| Signal | Problem title | Target path below `target_base` |
| --- | --- | --- |
| `https://atcoder.jp/contests/abc422/tasks/abc422_a` | `Stage Clear` | `ABC/400/420/422/A_Stage_Clear.cpp` |
| `abc422_a.cpp` | `Stage Clear` | `ABC/400/420/422/A_Stage_Clear.cpp` |
| `ABC422A.py` | `Stage Clear` | `ABC/400/420/422/A_Stage_Clear.py` |
| `arc180_b.cpp` | `Example Title` | `ARC/100/180/180/B_Example_Title.cpp` |
| `agc064_a.rs` | `Example Title` | `AGC/0/60/64/A_Example_Title.rs` |
| `https://atcoder.jp/contests/ahc043/tasks/ahc043_a` | `Example Title` | `AHC/0/40/43/A_Example_Title.cpp` |
| `https://atcoder.jp/contests/past202309-open/tasks/past202309_a` | `Example Title` | `PAST/202309-open/A_Example_Title.cpp` |

Contest series outside `ABC`, `ARC`, `AGC`, `AHC`, and `PAST` are not supported yet. If a source appears to be another AtCoder series, stop and ask the user.

If an AtCoder task suffix contains multiple parts, preserve it as the problem label after normalizing capitalization, for example `abc999_ex -> Ex`.

## Codeforces

For regular numeric contests, use:

```text
<target_base>/<hundreds_bucket>/<tens_bucket>/<contest_id>/<problem_id>.<ext>
```

For Educational contests, use the same bucket structure under `Educational`:

```text
<target_base>/Educational/<hundreds_bucket>/<tens_bucket>/<contest_id>/<problem_id>.<ext>
```

For non-regular named contests, use the same bucket structure under `Others`:

```text
<target_base>/Others/<hundreds_bucket>/<tens_bucket>/<contest_id>/<problem_id>.<ext>
```

Normalize:

- `contest_id`: numeric contest ID as written by Codeforces, for example `1900`.
- `contest_kind`: one of regular numeric contest, Educational contest, or Others. Ignore Div. 1, Div. 2, and Div. 3 labels for path placement.
- `hundreds_bucket`: `(contest_id // 100) * 100`, for example `1900 -> 1900` and `1917 -> 1900`.
- `tens_bucket`: `(contest_id // 10) * 10`, for example `1900 -> 1900` and `1917 -> 1910`.
- `problem_id`: uppercase problem index, preserving multi-part indices such as `A1`, `B2`, or `C`.
- `ext`: normalized language extension.

Classify by the Codeforces contest `name` from `contest.list`; do not classify by the API `type` alone. Many official Div. 3, Div. 4, and Educational rounds have API `type` values such as `ICPC`.

Classify as regular numeric contests when the contest name contains an official `Codeforces Round` token, including:

- `Codeforces Round 1098 (Div. 2)`.
- `Codeforces Round 1097 (Div. 1, Based on Zhili Cup 2026)`.
- `Spectral::Cup 2026 Round 1 (Codeforces Round 1094, Div. 1 + Div. 2)`.
- `CodeCraft-22 and Codeforces Round 795 (Div. 2)`.

In other words, company, event, or sponsor text does not make a contest `Others` when the title still contains `Codeforces Round` as an official round token.

Classify as `Educational` when the contest name contains `Educational Codeforces Round`.

Classify these as `Others`:

- Codeforces Global rounds.
- Hello and Good Bye rounds.
- ICPC, IOI, regional, online mirror, and team-preferred contests.
- Kotlin Heroes, April Fools, Testing Round, VK Cup, Technocup, Russian Code Cup, and similar special series.
- Company, product, sponsor, or event named contests that do not contain the official `Codeforces Round` token, such as `CodeTON Round`, `Pinely Round`, `EPIC Institute of Technology Round August 2024`, `Deltix Round`, and `Harbour.Space Scholarship Contest`.

Examples:

| Signal | Target path below `target_base` |
| --- | --- |
| `https://codeforces.com/problemset/problem/1900/A` | `1900/1900/1900/A.cpp` |
| `https://codeforces.com/contest/1917/problem/B` | `1900/1910/1917/B.cpp` |
| `1900A.cpp` | `1900/1900/1900/A.cpp` |
| `codeforces/1917/b.py` | `1900/1910/1917/B.py` |
| `cf_1917_a1.rs` | `1900/1910/1917/A1.rs` |
| Educational contest `1900`, problem `A` | `Educational/1900/1900/1900/A.cpp` |
| `Spectral::Cup 2026 Round 1 (Codeforces Round 1094, Div. 1 + Div. 2)`, contest `2222`, problem `A` | `2200/2220/2222/A.cpp` |
| `CodeTON Round 9`, contest `2039`, problem `B` | `Others/2000/2030/2039/B.cpp` |
| Global Round contest `1917`, problem `B` | `Others/1900/1910/1917/B.cpp` |
| Hello contest `1900`, problem `A` | `Others/1900/1900/1900/A.cpp` |
| ICPC-style contest `1917`, problem `C` | `Others/1900/1910/1917/C.cpp` |

If the contest looks Educational but the numeric contest ID is unclear, ask the user before publishing.

If the contest looks like Global, Hello, Good Bye, ICPC, IOI, online mirror, or special named contest but the numeric contest ID is unclear, ask the user before publishing.

If the contest kind is unclear, ask the user whether to place it as regular numeric, `Educational`, or `Others`.

### Codeforces Combined Rounds

Some Codeforces Div. 1 + Div. 2 rounds share problems under different contest IDs and problem labels, for example a Div. 2 `A` can be the same problem as a Div. 1 `C`.

When reliable metadata says the submitted solution corresponds to multiple Codeforces contest/problem pairs, publish the same solution to every target path.

Represent the targets as pairs:

```text
contest_id=<contest id>, problem_id=<problem id>
```

Apply the normal Codeforces path rule to each pair:

```text
<target_base>/<hundreds_bucket>/<tens_bucket>/<contest_id>/<problem_id>.<ext>
```

Example:

| Shared problem mapping | Target paths below `target_base` |
| --- | --- |
| Div. 2 `1917A` == Div. 1 `1916C` | `1900/1910/1917/A.cpp` and `1900/1910/1916/C.cpp` |

For multiple targets, copy the source solution to each target path. Do not move the source into only one target when more than one target is required.

Do not guess the paired Div. 1 or Div. 2 target from contest naming alone. Require reliable evidence such as:

- An explicit user instruction, for example "also publish this as Div. 1 C".
- Source metadata comments listing both contest/problem pairs.
- A problem URL or known mapping source that clearly identifies both pairs.

If a round appears combined but the paired contest/problem ID is unclear, ask the user before publishing.

## Ambiguity Rules

Ask the user before moving or copying files when any of these are true:

- The source filename is weak, such as `a.cpp`, `main.py`, `solution.cpp`, or `solve.rs`.
- Multiple candidate solution files are plausible.
- The platform cannot be determined confidently.
- The contest ID or problem ID cannot be determined confidently.
- The Codeforces contest kind cannot be determined confidently.
- A Codeforces problem may belong to a combined Div. 1 + Div. 2 round but the paired target is unclear.
- The AtCoder problem title cannot be determined confidently.
- The target path already exists.
- The language extension is unknown.

The confirmation should show:

```text
source: <source path>
platform: <atcoder|codeforces>
contest_id: <contest id>
problem_id: <problem id>
contest_kind: <regular|Educational|Others, for Codeforces>
problem_title: <problem title, for AtCoder>
target: <target path>
additional_targets: <extra target paths, for Codeforces combined rounds>
```

Do not publish until the user confirms ambiguous metadata.

## Collision Rules

If the target path does not exist, create parent directories as needed and move or copy the file.

If the target path exists:

- Treat it as an update only when the user explicitly intended to update that exact solution.
- Otherwise, stop and ask whether to overwrite, keep both, or cancel.
- Never overwrite silently.

If keeping both, ask for the desired suffix or filename. Do not invent a duplicate naming scheme without confirmation.
