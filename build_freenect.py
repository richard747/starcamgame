#!/usr/bin/env python3
"""Build and install the official libfreenect Python wrapper.

Upstream's wrappers/python/CMakeLists.txt still calls distutils (removed
in Python 3.12+) and can fail to parse the Cython version, which is what
broke ./setup.sh on Python 3.13. This script compiles freenect.pyx with
Cython and setuptools, then links it against an already-installed
libfreenect (Homebrew on a Mac, or a prefix passed with --prefix).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_SRC = ROOT / "vendor" / "libfreenect"


def die(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(1)


def run(cmd: list[str], **kwargs) -> None:
    print("+", " ".join(str(c) for c in cmd))
    subprocess.check_call(cmd, **kwargs)


def brew_prefix(*formula: str) -> Path | None:
    brew = shutil.which("brew")
    if not brew:
        for candidate in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew"):
            if Path(candidate).is_file():
                brew = candidate
                break
    if not brew:
        return None
    cmd = [brew, "--prefix", *formula]
    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    path = Path(out)
    return path if path.exists() else None


def cython_version() -> tuple[int, int, int]:
    try:
        from Cython.Compiler.Main import version as raw
    except Exception:
        try:
            import Cython

            raw = Cython.__version__
        except Exception as exc:
            die(f"Cython is not installed in this environment ({exc}).")
    parts = []
    for bit in str(raw).split(".")[:3]:
        num = ""
        for ch in bit:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num or 0))
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2]


def pick_pyx(wrapper_dir: Path) -> Path:
    major, _, _ = cython_version()
    name = "freenect.cython0.pyx" if major == 0 else "freenect.pyx"
    path = wrapper_dir / name
    if not path.is_file():
        die(f"Could not find {name} in {wrapper_dir}")
    return path


def lib_name_variants(stem: str) -> list[str]:
    # stem is like "freenect" or "usb-1.0"
    names = [
        f"lib{stem}.dylib",
        f"lib{stem}.so",
        f"lib{stem}.a",
    ]
    return names


def has_library(directory: Path, stem: str) -> bool:
    if any((directory / name).exists() for name in lib_name_variants(stem)):
        return True
    # Accept SONAME files such as libusb-1.0.so.0 when the unversioned .so is absent.
    return any(directory.glob(f"lib{stem}.so.*"))


def discover_prefixes(explicit: list[Path]) -> list[Path]:
    prefixes: list[Path] = []
    for item in explicit:
        if item and item.exists():
            prefixes.append(item)
    for env_name in ("FREENECT_PREFIX", "CMAKE_PREFIX_PATH", "HOMEBREW_PREFIX"):
        raw = os.environ.get(env_name, "")
        for part in raw.split(os.pathsep):
            if part:
                prefixes.append(Path(part))
    for formula in (("libfreenect",), ("libusb",), ()):
        prefix = brew_prefix(*formula)
        if prefix:
            prefixes.append(prefix)
    # Common fallbacks, including a local vendor install.
    prefixes.extend(
        [
            ROOT / "vendor" / "prefix",
            Path("/opt/homebrew"),
            Path("/usr/local"),
            Path("/usr"),
        ]
    )
    unique: list[Path] = []
    seen = set()
    for prefix in prefixes:
        resolved = prefix.resolve() if prefix.exists() else prefix
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(prefix)
    return unique


def find_include_dir(prefixes: list[Path], header: str, extra: list[Path] | None = None) -> Path | None:
    candidates = list(extra or [])
    for prefix in prefixes:
        candidates.extend(
            [
                prefix / "include",
                prefix / "include" / "libfreenect",
                prefix / "include" / "libusb-1.0",
                prefix,
            ]
        )
    seen = set()
    for directory in candidates:
        if directory in seen or not directory.is_dir():
            continue
        seen.add(directory)
        if (directory / header).is_file():
            return directory
        # Allow include/libusb-1.0/libusb.h via a parent include dir
        if (directory / "libusb-1.0" / header).is_file():
            return directory
    return None


def lib_search_dirs(prefix: Path) -> list[Path]:
    dirs = [prefix / "lib", prefix / "lib64", prefix]
    # Debian/Ubuntu multiarch, e.g. lib/x86_64-linux-gnu
    for base in (prefix / "lib", prefix / "lib64"):
        if base.is_dir():
            dirs.extend(sorted(p for p in base.iterdir() if p.is_dir()))
    # Direct system multiarch when prefix is /usr
    machine = os.uname().machine
    dirs.append(prefix / "lib" / f"{machine}-linux-gnu")
    return dirs


def find_lib_dir(prefixes: list[Path], stem: str) -> Path | None:
    for prefix in prefixes:
        for directory in lib_search_dirs(prefix):
            if directory.is_dir() and has_library(directory, stem):
                return directory
    return None


def build(args: argparse.Namespace) -> int:
    src = Path(args.src).resolve()
    wrapper_dir = src / "wrappers" / "python"
    if not wrapper_dir.is_dir():
        die(f"libfreenect wrapper sources not found at {wrapper_dir}")

    explicit = [Path(p) for p in args.prefix]
    prefixes = discover_prefixes(explicit)

    include_freenect = find_include_dir(
        prefixes,
        "libfreenect.h",
        extra=[src / "include"],
    )
    include_sync = find_include_dir(
        prefixes,
        "libfreenect_sync.h",
        extra=[src / "wrappers" / "c_sync"],
    )
    include_usb = find_include_dir(prefixes, "libusb.h") or find_include_dir(
        prefixes, "libusb.h", extra=[]
    )
    # libusb.h usually lives in include/libusb-1.0/
    if include_usb is None:
        for prefix in prefixes:
            path = prefix / "include" / "libusb-1.0"
            if (path / "libusb.h").is_file():
                include_usb = path
                break

    libdir_freenect = find_lib_dir(prefixes, "freenect")
    libdir_sync = find_lib_dir(prefixes, "freenect_sync") or libdir_freenect
    libdir_usb = find_lib_dir(prefixes, "usb-1.0")

    missing = []
    if include_freenect is None:
        missing.append("libfreenect.h")
    if include_sync is None:
        missing.append("libfreenect_sync.h")
    if include_usb is None:
        missing.append("libusb.h")
    if libdir_freenect is None:
        missing.append("libfreenect")
    if libdir_sync is None:
        missing.append("libfreenect_sync")
    if libdir_usb is None:
        missing.append("libusb-1.0")
    if missing:
        searched = ", ".join(str(p) for p in prefixes[:8])
        die(
            "Could not find "
            + ", ".join(missing)
            + f". Looked in: {searched}. "
            + "On a Mac, install libfreenect with Homebrew and rerun ./setup.sh."
        )

    try:
        import numpy as np
    except ImportError as exc:
        die(f"numpy is required to build the wrapper ({exc}).")

    pyx = pick_pyx(wrapper_dir)
    work = Path(args.build_dir).resolve() if args.build_dir else ROOT / "vendor" / "freenect-python-build"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    generated = work / "freenect.c"
    print(f"Cythonizing {pyx} -> {generated} (Cython {'.'.join(map(str, cython_version()))})")
    run(
        [sys.executable, "-m", "cython", "-3", "-o", str(generated), str(pyx)],
        cwd=str(wrapper_dir),
    )
    if not generated.is_file():
        die(f"Cython did not write {generated}")

    include_dirs = [
        str(include_freenect),
        str(include_sync),
        str(include_usb),
        str(src / "include"),
        str(src / "wrappers" / "c_sync"),
        np.get_include(),
    ]
    py_inc = Path(sysconfig.get_path("include"))
    if py_inc.is_dir():
        include_dirs.append(str(py_inc))
    else:
        # Virtualenv often points at the system include path, which may
        # not be installed. Search prefixes for Python.h instead.
        found_py = find_include_dir(prefixes, "Python.h")
        if found_py is None:
            ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
            found_py = find_include_dir(prefixes, "Python.h", extra=[])
            for prefix in prefixes:
                candidate = prefix / "include" / ver
                if (candidate / "Python.h").is_file():
                    found_py = candidate
                    break
        if found_py is not None:
            include_dirs.append(str(found_py))
            print(f"Using Python headers from {found_py}")
        else:
            die(f"Python.h not found (sysconfig path was {py_inc}).")
    # If we captured include/libusb-1.0, also add the parent include/ dir.
    usb_parent = include_usb.parent if include_usb.name == "libusb-1.0" else include_usb
    if usb_parent not in (include_usb,):
        include_dirs.append(str(usb_parent))

    library_dirs = list(dict.fromkeys(str(d) for d in (libdir_freenect, libdir_sync, libdir_usb) if d))
    extra_link = []
    for libdir in library_dirs:
        extra_link.append(f"-Wl,-rpath,{libdir}")

    # macOS: also add the Homebrew lib dir when present, so the module
    # finds libfreenect.dylib without DYLD_LIBRARY_PATH.
    brew_lib = brew_prefix()
    if brew_lib and (brew_lib / "lib").is_dir():
        extra_link.append(f"-Wl,-rpath,{brew_lib / 'lib'}")

    from setuptools import Extension, setup

    ext = Extension(
        "freenect",
        sources=[str(generated)],
        include_dirs=include_dirs,
        library_dirs=library_dirs,
        libraries=["freenect_sync", "freenect", "usb-1.0"],
        extra_compile_args=["-fPIC"],
        extra_link_args=extra_link,
    )

    platlib = Path(sysconfig.get_path("platlib"))
    print(f"Installing freenect into {platlib}")
    # Build in-process so we use this interpreter, then copy the built module.
    setup(
        name="freenect",
        ext_modules=[ext],
        script_args=["build_ext", "--build-temp", str(work / "tmp"), "--build-lib", str(work)],
    )

    suffix = sysconfig.get_config_var("EXT_SUFFIX") or ".so"
    built = work / f"freenect{suffix}"
    if not built.is_file():
        # Some setups write freenect.so regardless of EXT_SUFFIX.
        matches = list(work.glob("freenect*.so")) + list(work.glob("freenect*.dylib"))
        if not matches:
            die(f"Build finished, but no freenect extension was found in {work}")
        built = matches[0]

    platlib.mkdir(parents=True, exist_ok=True)
    dest = platlib / built.name
    shutil.copy2(built, dest)
    print(f"Installed {dest}")

    # Sanity import using the same interpreter.
    try:
        import importlib

        sys.path.insert(0, str(platlib))
        # Drop a previously failed import, if any.
        sys.modules.pop("freenect", None)
        module = importlib.import_module("freenect")
        print("import freenect: OK", getattr(module, "__file__", ""))
    except Exception as exc:
        die(f"The module was built, but 'import freenect' failed: {exc}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--src",
        default=str(DEFAULT_SRC),
        help="Path to the libfreenect source tree (default: vendor/libfreenect).",
    )
    parser.add_argument(
        "--prefix",
        action="append",
        default=[],
        help="Prefix that contains include/ and lib/ for libfreenect and libusb. Repeatable.",
    )
    parser.add_argument(
        "--build-dir",
        default="",
        help="Temporary build directory (deleted and recreated).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(build(parse_args()))
