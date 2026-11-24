#!/usr/bin/env bash
# Activate the Star Pop virtualenv and start the game. Any arguments
# are passed through to star_pop.py (for example: ./run.sh --mouse).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  printf 'Error: the virtualenv is missing. Run ./setup.sh first.\n' >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"

if command -v brew >/dev/null 2>&1; then
  brew_lib="$(brew --prefix)/lib"
  export DYLD_LIBRARY_PATH="${brew_lib}${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
elif [[ -x /opt/homebrew/bin/brew ]]; then
  brew_lib="$(/opt/homebrew/bin/brew --prefix)/lib"
  export DYLD_LIBRARY_PATH="${brew_lib}${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
fi

exec python "$ROOT/star_pop.py" "$@"
