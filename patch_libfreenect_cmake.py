#!/usr/bin/env python3
"""Patch vendored libfreenect wrappers/python/CMakeLists.txt for Python 3.12+.

Upstream still imports distutils (removed in 3.12+) to find platlib, and
it crashes with "list GET given empty list" if Cython --version cannot be
parsed. This edit is idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path


def patch(path: Path) -> bool:
    text = path.read_text()
    original = text

    old_dist = (
        '-c "from distutils.sysconfig import get_python_lib; '
        "print(get_python_lib(plat_specific=False, standard_lib=False, "
        "prefix='${CMAKE_INSTALL_PREFIX}'))\""
    )
    new_dist = '-c "import sysconfig; print(sysconfig.get_path(\'platlib\'))"'
    text = text.replace(old_dist, new_dist)

    old_cy_lines = [
        "execute_process(COMMAND",
        "  ${CYTHON_EXECUTABLE} --version",
        "  ERROR_VARIABLE CYTHON_VERSION_OUTPUT ERROR_STRIP_TRAILING_WHITESPACE)",
        'string(REGEX MATCH "[0-9]+\\\\.[0-9]+\\\\.[0-9]+" CYTHON_VERSION "${CYTHON_VERSION_OUTPUT}")',
        'string(REGEX MATCHALL "[0-9]+" CYTHON_VERSION_COMPONENTS "${CYTHON_VERSION}")',
        "list(GET CYTHON_VERSION_COMPONENTS 0 CYTHON_VERSION_MAJOR)",
        "list(GET CYTHON_VERSION_COMPONENTS 1 CYTHON_VERSION_MINOR)",
        "list(GET CYTHON_VERSION_COMPONENTS 2 CYTHON_VERSION_PATCH)",
        "if (${CYTHON_VERSION_MAJOR} LESS_EQUAL 0)",
    ]
    new_cy = r"""execute_process(COMMAND
  ${CYTHON_EXECUTABLE} --version
  OUTPUT_VARIABLE CYTHON_VERSION_OUTPUT_OUT
  ERROR_VARIABLE CYTHON_VERSION_OUTPUT_ERR
  OUTPUT_STRIP_TRAILING_WHITESPACE
  ERROR_STRIP_TRAILING_WHITESPACE)
set(CYTHON_VERSION_OUTPUT "${CYTHON_VERSION_OUTPUT_ERR} ${CYTHON_VERSION_OUTPUT_OUT}")
string(REGEX MATCH "[0-9]+\.[0-9]+\.[0-9]+" CYTHON_VERSION "${CYTHON_VERSION_OUTPUT}")
string(REGEX MATCHALL "[0-9]+" CYTHON_VERSION_COMPONENTS "${CYTHON_VERSION}")
if (NOT CYTHON_VERSION_COMPONENTS)
  set(CYTHON_VERSION_MAJOR 3)
  set(CYTHON_VERSION_MINOR 0)
  set(CYTHON_VERSION_PATCH 0)
else()
  list(GET CYTHON_VERSION_COMPONENTS 0 CYTHON_VERSION_MAJOR)
  list(LENGTH CYTHON_VERSION_COMPONENTS _cy_len)
  if (_cy_len GREATER 1)
    list(GET CYTHON_VERSION_COMPONENTS 1 CYTHON_VERSION_MINOR)
  else()
    set(CYTHON_VERSION_MINOR 0)
  endif()
  if (_cy_len GREATER 2)
    list(GET CYTHON_VERSION_COMPONENTS 2 CYTHON_VERSION_PATCH)
  else()
    set(CYTHON_VERSION_PATCH 0)
  endif()
endif()
if (${CYTHON_VERSION_MAJOR} LESS_EQUAL 0)
"""
    old_cy = "\n".join(old_cy_lines) + "\n"
    text = text.replace(old_cy, new_cy)

    already = "sysconfig.get_path('platlib')" in text and "CYTHON_VERSION_OUTPUT_OUT" in text
    if text == original:
        if already:
            print(f"Already patched: {path}")
            return False
        print(
            f"Warning: could not patch {path}; the file may have changed upstream.",
            file=sys.stderr,
        )
        return False
    path.write_text(text)
    print(f"Patched {path}")
    return True


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: patch_libfreenect_cmake.py <CMakeLists.txt>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"Error: missing {path}", file=sys.stderr)
        return 1
    patch(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
