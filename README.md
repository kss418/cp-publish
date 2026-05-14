# CP Publish

CP Publish는 Codex가 로컬의 CP 풀이를 GitHub 풀이 저장소에 안전하게 정리해서 올리도록 돕는 Codex Skill입니다.

AtCoder와 Codeforces 풀이 파일을 대상으로 문제 정보를 식별하고, 저장소 라우팅 설정과 플랫폼별 경로 규칙을 적용한 뒤, contest README 갱신 계획과 커밋 메시지까지 미리 만들어 줍니다.

## 주요 기능

- AtCoder, Codeforces 풀이 파일 식별
- 문제 URL, 주석 메타데이터, 파일명, 기존 경로 기반 문제 추론
- 사용자별 풀이 저장소 라우팅 설정
- AtCoder / Codeforces 경로 규칙 적용
- AtCoder Kenkoooo 메타데이터 기반 문제 제목, 추정 난이도 조회
- Codeforces API 기반 contest, problem, rating 조회
- contest `README.md` 항목 생성 또는 갱신
- 풀이 태그 문서 기반 README 태그 추론 보조
- GitHub CLI 인증 확인
- 안전한 commit / push 보조
- 실제 변경 전 publish plan JSON 생성

이 스킬은 풀이 파일을 정리하고 GitHub에 올리는 작업만 다룹니다.

## 지원 플랫폼

- AtCoder
- Codeforces

## 저장 경로 규칙 요약

AtCoder는 `ABC`, `ARC`, `AGC`, `AHC`, `PAST`를 지원합니다.

예를 들어 `abc422_a`, 문제 제목 `Stage Clear`, C++ 풀이 파일이면 다음과 같이 저장합니다.

```text
ABC/400/420/422/A_Stage_Clear.cpp
```

Codeforces 일반 라운드는 contest 번호 기준으로 저장합니다. 라운드 이름에 공식 `Codeforces Round` 토큰이 있으면 앞에 sponsor나 event 이름이 붙어 있어도 일반 라운드로 봅니다.

```text
2000/2060/2061/A.cpp
```

Educational Round는 `Educational/` 아래에 저장합니다.

```text
Educational/100/160/162/A.cpp
```

Global Round, Hello, Good Bye, ICPC/IOI mirror, Kotlin Heroes, April Fools, Testing Round, 그리고 공식 `Codeforces Round` 토큰이 없는 sponsor/event contest는 `Others/` 아래에 저장합니다.

```text
Others/2000/2060/2062/C.cpp
```

자세한 규칙은 `references/path-rules.md`를 봅니다.

## 설치 방법

이 저장소를 Codex skill 디렉터리 아래에 `cp-publish` 이름으로 복사하거나 clone합니다.

Windows:

```powershell
git clone https://github.com/kss418/cp-publish $env:USERPROFILE\.codex\skills\cp-publish
```

macOS / Linux:

```sh
git clone https://github.com/kss418/cp-publish ~/.codex/skills/cp-publish
```

이미 로컬에 받은 폴더가 있다면 해당 폴더 전체를 위 위치로 복사해도 됩니다. 최소한 다음 파일과 폴더가 함께 있어야 합니다.

```text
SKILL.md
agents/openai.yaml
scripts/
references/
```

설치는 여기까지입니다. 의존성 확인과 GitHub 인증은 스킬 실행 중 Codex가 자동으로 확인합니다.

## 첫 실행 시 자동 확인

스킬을 처음 사용할 때 Codex는 publish 전에 다음 항목을 확인합니다.

- `python`: helper script 실행
- `git`: 저장소 상태 확인, commit, push
- `gh`: GitHub 인증 확인 및 git credential 설정

빠진 의존성이 있으면 Codex가 설치 계획을 보여주고 사용자에게 설치해도 되는지 먼저 묻습니다. 승인된 경우에만 `scripts/install_dependencies.py`를 실행합니다.

GitHub 로그인이 필요할 때도 Codex가 먼저 확인을 요청한 뒤 `gh auth login --web` 기반 흐름을 실행합니다. 이 스킬은 GitHub 토큰, 비밀번호, 쿠키를 파일에 저장하지 않습니다.

직접 점검하고 싶을 때만 아래 명령을 사용하면 됩니다.

Windows:

```powershell
python scripts/check_dependencies.py
python scripts/install_dependencies.py --dry-run
python scripts/github_integration.py auth
```

macOS / Linux:

```sh
python3 scripts/check_dependencies.py
python3 scripts/install_dependencies.py --dry-run
python3 scripts/github_integration.py auth
```

## 저장소 설정

풀이를 올릴 GitHub 저장소 설정도 스킬 실행 중 Codex가 확인합니다. 설정 파일이 없거나, 현재 publish하려는 플랫폼 route가 없으면 Codex가 필요한 값을 물어보고 `scripts/configure_repos.py`로 설정합니다.

Codex가 물어보는 내용은 보통 다음과 같습니다.

- AtCoder만 쓸지, Codeforces만 쓸지, 둘 다 쓸지
- AtCoder와 Codeforces를 서로 다른 저장소로 둘지
- 한 저장소 안에서 `atcoder/`, `codeforces/` 같은 폴더로 나눌지
- 각 저장소의 로컬 경로
- 저장소 안에서 사용할 base directory

Codeforces만 푸는 사용자는 AtCoder route를 설정하지 않아도 됩니다. 반대로 AtCoder만 푸는 사용자도 Codeforces route 없이 사용할 수 있습니다.

직접 미리 설정하고 싶을 때만 아래 명령을 사용하면 됩니다.

Windows:

```powershell
python scripts/configure_repos.py init
python scripts/configure_repos.py validate
```

macOS / Linux:

```sh
python3 scripts/configure_repos.py init
python3 scripts/configure_repos.py validate
```

## Codex에서 사용하는 법

Codex에서 다음처럼 요청합니다.

```text
Use $cp-publish to publish my latest AtCoder solution to GitHub.
```

또는 한국어로 자연스럽게 요청해도 됩니다.

```text
$cp-publish로 방금 푼 Codeforces 풀이 GitHub에 올려줘.
```

Codex는 대략 다음 순서로 작업합니다.

1. 의존성 확인
2. GitHub 인증 확인
3. 저장소 라우팅 설정 확인
4. 풀이 파일 식별
5. 문제 플랫폼, contest ID, problem ID 식별
6. 메타데이터 조회
7. publish plan 생성
8. 애매하거나 위험한 부분이 있으면 사용자에게 확인
9. 풀이 파일 복사 또는 이동
10. contest README 갱신
11. 가능한 경우 가벼운 검증
12. 관련 파일만 commit
13. push

문제 식별이 애매하거나 대상 파일이 이미 존재하면 Codex는 바로 publish하지 않고 확인을 요청해야 합니다.

## Publish plan 직접 확인

실제 파일을 옮기기 전에 plan만 확인할 수 있습니다.

Windows:

```powershell
python scripts/plan_publish.py C:\path\to\solution.cpp --tags DP,Greedy
```

macOS / Linux:

```sh
python3 scripts/plan_publish.py /path/to/solution.cpp --tags DP,Greedy
```

출력 예시는 다음과 같습니다.

```json
{
  "source": "...",
  "targets": ["..."],
  "readme_updates": [
    {
      "readme": "...",
      "contest_url": "...",
      "problem_id": "A",
      "rating": "$800$",
      "tags": "DP, Greedy"
    }
  ],
  "commit_message": "Add Codeforces 2061A solution",
  "needs_confirmation": false
}
```

`needs_confirmation`이 `true`이면 실제 변경 전에 사용자의 확인이 필요합니다.

## README 갱신 양식

각 contest 폴더의 `README.md`는 다음 형식을 사용합니다.

```md
# https://codeforces.com/contest/2061

A / Rating : $800$ / Case_Work

B / Rating : $1100$ / Math, Greedy
```

AtCoder도 같은 형식을 사용합니다. AtCoder rating은 Kenkoooo의 추정 난이도를 사용하고, 없거나 모르면 `$-$`로 씁니다.

README 항목만 직접 갱신하려면 다음 명령을 사용할 수 있습니다.

```powershell
python scripts/update_readme.py --contest-dir C:\path\to\contest --contest-url https://codeforces.com/contest/2061 --problem-id A --rating 800 --tags Case_Work
```

```sh
python3 scripts/update_readme.py --contest-dir /path/to/contest --contest-url https://atcoder.jp/contests/abc422 --problem-id A --rating - --tags Case_Work
```

## 메타데이터 캐시

Codeforces 메타데이터:

```powershell
python scripts/codeforces_metadata.py all
```

```sh
python3 scripts/codeforces_metadata.py all
```

AtCoder 메타데이터:

```powershell
python scripts/atcoder_metadata.py all
```

```sh
python3 scripts/atcoder_metadata.py all
```

메타데이터 스크립트는 캐시가 없거나 오래된 경우 API에서 새로 가져옵니다. 네트워크 접근이 필요한 환경에서는 Codex가 사용자 승인을 요청할 수 있습니다.

## 안전 정책

- 문제를 대신 풀지 않습니다.
- AtCoder나 Codeforces에 제출하지 않습니다.
- GitHub 토큰이나 비밀번호를 요구하거나 저장하지 않습니다.
- 문제 식별이 애매하면 publish하지 않습니다.
- 기존 풀이 파일을 덮어쓰기 전에 사용자 확인을 받습니다.
- force push, history rewrite, destructive git command를 사용하지 않습니다.
- commit할 때는 관련 파일만 명시적으로 포함합니다.

## 파일 구성

```text
SKILL.md                         # Codex가 읽는 스킬 지침
agents/openai.yaml               # Codex UI 표시용 메타데이터
scripts/check_dependencies.py    # 의존성 확인
scripts/install_dependencies.py  # 승인 후 의존성 설치
scripts/configure_repos.py       # 저장소 라우팅 설정
scripts/plan_publish.py          # publish 전 dry-run 계획 생성
scripts/update_readme.py         # contest README 갱신
scripts/github_integration.py    # GitHub 인증, commit, push 보조
scripts/atcoder_metadata.py      # AtCoder 메타데이터 조회
scripts/codeforces_metadata.py   # Codeforces 메타데이터 조회
references/path-rules.md         # 저장 경로 규칙
references/readme-format.md      # README 양식
references/solution-tags.md      # 풀이 태그 규칙
references/solvedac-tag-map.json # solved.ac 태그 매핑
```
