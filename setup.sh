#!/usr/bin/env bash
# One-step macOS setup for Ridgeford Star Pop.
# Safe to run more than once. Do not run this script with sudo;
# the official Homebrew installer may ask for your password on its own.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VENDOR_DIR="$ROOT/vendor/libfreenect"
VENV_DIR="$ROOT/.venv"
MODEL_PATH="$ROOT/models/pose_landmarker_lite.task"
MODEL_URL="https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"

VERIFY_ONLY=0

usage() {
  cat <<'EOF'
Usage: ./setup.sh [--verify-only] [--help]

  --verify-only   Only run the import and PoseLandmarker checks.
  --help          Show this message.

This script is meant for macOS. It installs Homebrew (if you agree),
libfreenect, a Python virtualenv, the game packages, the freenect
Python module, and the MediaPipe pose model, then verifies them.
EOF
}

info() { printf '==> %s\n' "$*"; }
warn() { printf 'Warning: %s\n' "$*" >&2; }
die()  { printf 'Error: %s\n' "$*" >&2; exit 1; }

for arg in "$@"; do
  case "$arg" in
    --verify-only) VERIFY_ONLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $arg  (try --help)" ;;
  esac
done

run_verify() {
  local py="${1:-}"
  if [[ -z "$py" ]]; then
    if [[ -x "$VENV_DIR/bin/python" ]]; then
      py="$VENV_DIR/bin/python"
    else
      die "No virtualenv found at $VENV_DIR. Run ./setup.sh first."
    fi
  fi
  # Help the freenect module find Homebrew's libfreenect.dylib.
  if command -v brew >/dev/null 2>&1; then
    local brew_lib
    brew_lib="$(brew --prefix)/lib"
    export DYLD_LIBRARY_PATH="${brew_lib}${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
  fi
  info "Verifying installs"
  local rc=0
  "$py" "$ROOT/verify_setup.py" || rc=$?
  cat <<'EOF'

With the Kinect powered and plugged in, test the sensor with:

  freenect-glview

Then start the game from this folder:

  ./run.sh
  ./run.sh --mouse
  ./run.sh --webcam
  ./run.sh --depth

EOF
  return "$rc"
}

if [[ "$VERIFY_ONLY" -eq 1 ]]; then
  run_verify
  exit 0
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  die "This setup script is for macOS. On this computer you can still run the checks with:  ./setup.sh --verify-only"
fi

# --- Machine and Python architecture ---

machine="$(uname -m)"
translated="$(sysctl -in sysctl.proc_translated 2>/dev/null || true)"

if [[ "$machine" == "x86_64" && "$translated" == "1" ]]; then
  warn "This Terminal is running under Rosetta (x86_64 on Apple Silicon)."
  warn "MediaPipe and Homebrew need a native arm64 Terminal."
  warn "Open a new Terminal window (not under Rosetta) and run ./setup.sh again."
  if ! arch -arm64 true >/dev/null 2>&1; then
    die "Could not switch to arm64. Please start a native Terminal and retry."
  fi
  die "Rerun from a native (arm64) Terminal. You can check with:  uname -m    (should print arm64)"
fi

IS_APPLE_SILICON=0
if [[ "$machine" == "arm64" ]]; then
  IS_APPLE_SILICON=1
  info "Apple Silicon detected (arm64)."
else
  warn "This Mac reports architecture '$machine', not Apple Silicon (arm64)."
  warn "Current MediaPipe Python wheels for macOS are Apple Silicon only, so pose tracking may not install."
  warn "You can still use ./run.sh --mouse, and Kinect depth mode may still work with libfreenect."
  if [[ -t 0 ]]; then
    printf 'Continue anyway? [y/N] '
    read -r reply
    [[ "$reply" =~ ^[Yy]([Ee][Ss])?$ ]] || die "Stopped. Use an Apple Silicon Mac for the full pose-tracking setup."
  else
    die "Not Apple Silicon, and this session is not interactive. Rerun from Terminal to confirm, or use an arm64 Mac."
  fi
fi

# --- Homebrew ---

ensure_brew_on_path() {
  if command -v brew >/dev/null 2>&1; then
    return 0
  fi
  if [[ -x /opt/homebrew/bin/brew ]]; then
    # shellcheck disable=SC1091
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    # shellcheck disable=SC1091
    eval "$(/usr/local/bin/brew shellenv)"
  fi
  command -v brew >/dev/null 2>&1
}

if ! ensure_brew_on_path; then
  info "Homebrew is not installed."
  if [[ ! -t 0 ]]; then
    die "Rerun ./setup.sh from a Terminal so you can confirm the Homebrew install."
  fi
  printf 'Install Homebrew now? The official installer may ask for your Mac password. [y/N] '
  read -r reply
  [[ "$reply" =~ ^[Yy]([Ee][Ss])?$ ]] || die "Homebrew is required. Install it from https://brew.sh and run ./setup.sh again."
  info "Installing Homebrew"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  ensure_brew_on_path || die "Homebrew installed, but 'brew' is not on PATH. Open a new Terminal and run ./setup.sh again."
else
  info "Homebrew already installed: $(command -v brew)"
fi

# --- Xcode Command Line Tools (compiler, git, headers) ---

if ! xcode-select -p >/dev/null 2>&1; then
  info "Xcode Command Line Tools are not installed. A macOS dialog will open."
  xcode-select --install || true
  die "When the Command Line Tools finish installing, run ./setup.sh again."
fi

# --- Homebrew packages ---

info "Installing libfreenect, cmake, git, and Python with Homebrew"
# brew install is safe to re-run; installed packages are left as-is or upgraded.
brew install libfreenect cmake git python

# --- Find a suitable base Python ---

python_version_ok() {
  local py="$1"
  "$py" -c 'import sys; v=sys.version_info; raise SystemExit(0 if v.major==3 and 9<=v.minor<=14 else 1)' 2>/dev/null
}

python_is_arm64() {
  local py="$1"
  "$py" -c 'import platform; raise SystemExit(0 if platform.machine()=="arm64" else 1)' 2>/dev/null
}

python_describe() {
  local py="$1"
  "$py" -c 'import platform, sys; print("Python " + sys.version.split()[0] + " (" + platform.machine() + ") at " + sys.executable)'
}

PYTHON=""
PYTHON_WRONG_ARCH=""
CANDIDATES=()

# Prefer Homebrew's python3 when present, then whatever is on PATH.
if command -v brew >/dev/null 2>&1; then
  if [[ -x "$(brew --prefix)/bin/python3" ]]; then
    CANDIDATES+=("$(brew --prefix)/bin/python3")
  fi
fi
for name in python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
  if command -v "$name" >/dev/null 2>&1; then
    CANDIDATES+=("$(command -v "$name")")
  fi
done

# Walk unique, existing interpreters only (bash 3.2-safe; no associative arrays).
SEEN=""
for cand in "${CANDIDATES[@]}"; do
  [[ -n "$cand" && -x "$cand" ]] || continue
  resolved="$cand"
  if command -v realpath >/dev/null 2>&1; then
    resolved="$(realpath "$cand" 2>/dev/null || printf '%s' "$cand")"
  fi
  case " $SEEN " in
    *" $resolved "*) continue ;;
  esac
  SEEN="$SEEN $resolved"
  if ! python_version_ok "$cand"; then
    continue
  fi
  if [[ "$IS_APPLE_SILICON" -eq 1 ]] && ! python_is_arm64 "$cand"; then
    PYTHON_WRONG_ARCH="$cand"
    continue
  fi
  PYTHON="$cand"
  break
done

if [[ -z "$PYTHON" ]]; then
  if [[ -n "$PYTHON_WRONG_ARCH" ]]; then
    warn "Found $(python_describe "$PYTHON_WRONG_ARCH"), but it is not a native arm64 interpreter."
    warn "A Rosetta (x86_64) Python will not load current MediaPipe or arm64 Homebrew libraries."
    die "Install a native Python with  brew install python  or use Homebrew's python3, then rerun ./setup.sh."
  fi
  die "Need Python 3.9 through 3.14. Install one with  brew install python  and rerun ./setup.sh."
fi

info "Using $(python_describe "$PYTHON")"
if [[ "$IS_APPLE_SILICON" -eq 1 ]] && ! python_is_arm64 "$PYTHON"; then
  die "Internal error: selected Python is not arm64."
fi

# --- Virtualenv ---

if [[ -x "$VENV_DIR/bin/python" ]]; then
  if python_version_ok "$VENV_DIR/bin/python" && { [[ "$IS_APPLE_SILICON" -eq 0 ]] || python_is_arm64 "$VENV_DIR/bin/python"; }; then
    info "Reusing existing virtualenv at $VENV_DIR"
  else
    warn "Existing virtualenv is not a native Python 3.9–3.14. Replacing $VENV_DIR."
    rm -rf "$VENV_DIR"
  fi
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  info "Creating virtualenv"
  "$PYTHON" -m venv "$VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"
info "Installing Python packages"
"$VENV_PY" -m pip install --upgrade pip
# pygame and pygame-ce both install into a "pygame" package dir; they
# cannot coexist. Official pygame 2.6.x breaks fonts on Python 3.14.
"$VENV_PY" -m pip uninstall -y pygame || true
"$VENV_PY" -m pip install -r "$ROOT/requirements.txt"
"$VENV_PY" -m pip install --force-reinstall pygame-ce
# setuptools provides a distutils shim on Python 3.12+ (upstream CMake still
# imports distutils). Cython compiles the official wrapper.
"$VENV_PY" -m pip install setuptools cython

# --- Official freenect Python module ---
# Upstream wrappers/python/CMakeLists.txt calls distutils (removed in
# Python 3.12+) and can fail with "list GET given empty list" if it
# cannot parse the Cython version. Prefer a direct Cython + setuptools
# build against Homebrew's libfreenect; fall back to a patched CMake
# build if that does not work.

info "Building the official libfreenect Python wrapper"
mkdir -p "$ROOT/vendor"
if [[ -d "$VENDOR_DIR/.git" ]]; then
  info "Updating existing clone at $VENDOR_DIR"
  git -C "$VENDOR_DIR" pull --ff-only || warn "Could not update the clone; using the copy that is already there."
elif [[ -e "$VENDOR_DIR" ]]; then
  die "$VENDOR_DIR exists but is not a git clone. Move it aside and rerun ./setup.sh."
else
  git clone --depth 1 https://github.com/OpenKinect/libfreenect.git "$VENDOR_DIR"
fi

# Stale CMake cache from a failed run will keep failing. Start clean.
if [[ -d "$VENDOR_DIR/build" ]]; then
  info "Removing stale CMake build directory"
  rm -rf "$VENDOR_DIR/build"
fi
rm -rf "$ROOT/vendor/freenect-python-build"

install_built_freenect_module() {
  local search_root="$1"
  local site module found
  site="$("$VENV_PY" -c 'import sysconfig; print(sysconfig.get_path("platlib"))')"
  module=""
  while IFS= read -r -d '' found; do
    module="$found"
    break
  done < <(find "$search_root" \( -name 'freenect*.so' -o -name 'freenect*.dylib' \) -print0 2>/dev/null)
  if [[ -z "$module" ]]; then
    return 1
  fi
  info "Installing $(basename "$module") into the virtualenv"
  cp -f "$module" "$site/"
}

build_freenect_with_setuptools() {
  local prefixes=()
  if command -v brew >/dev/null 2>&1; then
    prefixes+=(--prefix "$(brew --prefix libfreenect)")
    prefixes+=(--prefix "$(brew --prefix libusb)")
    prefixes+=(--prefix "$(brew --prefix)")
  fi
  "$VENV_PY" "$ROOT/build_freenect.py" --src "$VENDOR_DIR" "${prefixes[@]}"
}

build_freenect_with_cmake() {
  command -v cmake >/dev/null 2>&1 || return 1
  [[ -x "$VENV_DIR/bin/cython" ]] || return 1
  "$VENV_PY" "$ROOT/patch_libfreenect_cmake.py" "$VENDOR_DIR/wrappers/python/CMakeLists.txt"
  # So CMake's find_program(cython) and the distutils shim both work.
  export PATH="$VENV_DIR/bin:${PATH}"
  export SETUPTOOLS_USE_DISTUTILS=local
  cmake -S "$VENDOR_DIR" -B "$VENDOR_DIR/build" \
    -DBUILD_PYTHON3=ON \
    -DBUILD_EXAMPLES=OFF \
    -DPython3_EXECUTABLE="$VENV_PY" \
    -DCYTHON_EXECUTABLE="$VENV_DIR/bin/cython" \
    -DCMAKE_PREFIX_PATH="$(brew --prefix 2>/dev/null || printf '%s' /usr/local)"
  cmake --build "$VENDOR_DIR/build"
  install_built_freenect_module "$VENDOR_DIR/build/wrappers/python"
}

FREENECT_OK=0
if build_freenect_with_setuptools; then
  FREENECT_OK=1
else
  warn "Direct Cython/setuptools build failed. Trying a patched CMake build."
  if build_freenect_with_cmake; then
    FREENECT_OK=1
  fi
fi

if [[ "$FREENECT_OK" -ne 1 ]]; then
  die "Could not build the freenect Python module. See the errors above. After fixing them, rerun ./setup.sh (it will clean the stale build and try again)."
fi

# --- MediaPipe model ---

mkdir -p "$ROOT/models"
if [[ -f "$MODEL_PATH" ]] && [[ "$(wc -c < "$MODEL_PATH" | tr -d ' ')" -gt 1000 ]]; then
  info "Pose model already present: $MODEL_PATH"
else
  info "Downloading MediaPipe Pose Landmarker lite model"
  tmp="$MODEL_PATH.partial"
  curl -fL --retry 3 --retry-delay 2 -o "$tmp" "$MODEL_URL" \
    || die "Could not download the pose model from $MODEL_URL"
  mv "$tmp" "$MODEL_PATH"
fi

# --- Verify ---

if run_verify "$VENV_PY"; then
  printf 'Setup complete.\n'
else
  printf 'Setup finished, but some checks failed. See the FAIL lines above.\n' >&2
  exit 1
fi
