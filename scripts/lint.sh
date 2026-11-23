#!/usr/bin/env bash
# lint.sh: run the same checks as CI (.github/workflows/ci.yml) before you push. No sudo.
#
#   Check everything:                       ./scripts/lint.sh
#   Also auto-fix what can be fixed:        ./scripts/lint.sh --fix
#
# --fix runs `ruff check --fix`, `ruff format`, and Prettier --write, then checks again.
# Uses the repo's root .venv. If ruff/shellcheck are missing there, it installs the versions
# pinned in requirements.txt (nothing system-wide).

set -uo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
FIX=0
[[ "${1:-}" == "--fix" ]] && FIX=1
cd "$ROOT" || exit 1

if [[ -t 1 ]]; then G=$'\e[32m' R=$'\e[31m' N=$'\e[0m'; else G='' R='' N=''; fi
failed=()

step() {
    local name="$1"
    shift
    printf '\n==> %s\n' "$name"
    if "$@"; then
        printf '%s[ok]%s %s\n' "$G" "$N" "$name"
    else
        printf '%s[FAIL]%s %s\n' "$R" "$N" "$name"
        failed+=("$name")
    fi
}

# Tools come from the root .venv (versions pinned in requirements.txt).
if [[ ! -x "$VENV/bin/ruff" || ! -x "$VENV/bin/shellcheck" ]]; then
    printf '==> Installing the lint tools from requirements.txt into .venv\n'
    [[ -x "$VENV/bin/pip" ]] || python3 -m venv "$VENV"
    "$VENV/bin/pip" -q install -r requirements.txt || {
        echo "Could not install lint tools" >&2
        exit 1
    }
fi
RUFF="$VENV/bin/ruff"
SHELLCHECK="$VENV/bin/shellcheck"

if ((FIX)); then
    printf '\n==> Fixing what can be fixed\n'
    "$RUFF" check --fix .
    "$RUFF" format .
    npm --prefix frontend run format >/dev/null
fi

step "ruff lint" "$RUFF" check .
step "ruff format" "$RUFF" format --check .
step "python syntax" python3 -m compileall -q -x '/\.venv' backend projects
step "shell syntax" bash -n scripts/*.sh scripts/deploy/*.sh
step "shellcheck" "$SHELLCHECK" -x -S warning scripts/*.sh scripts/deploy/*.sh projects/dataviz/start_servers.sh
step "prettier (frontend)" npm --prefix frontend run --silent format:check

echo
if ((${#failed[@]})); then
    printf '%s%d check(s) failed:%s %s\n' "$R" "${#failed[@]}" "$N" "${failed[*]}"
    ((FIX)) || echo "Try ./scripts/lint.sh --fix for formatting and simple lint issues."
    exit 1
fi
printf '%sAll checks passed.%s (The frontend build runs in CI and in ./scripts/publish.sh.)\n' "$G" "$N"
