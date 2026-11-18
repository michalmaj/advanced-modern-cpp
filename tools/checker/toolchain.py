"""Finding and identifying the tools: LLVM clang++, CMake and Ninja."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .proc import run_process

_CLANG = re.compile(r"clang version (\d+)\.(\d+)\.(\d+)")
_TARGET = re.compile(r"^Target: (\S+)", re.MULTILINE)
_CMAKE = re.compile(r"cmake version (\d+)\.(\d+)\.(\d+)")
MIN_CMAKE = (3, 28)

_PROBE = """#include <version>
AMC_STDLIB_BEGIN
#if defined(_LIBCPP_VERSION)
libc++ _LIBCPP_VERSION
#elif defined(_MSVC_STL_VERSION)
msvc-stl _MSVC_STL_VERSION _MSVC_STL_UPDATE
#elif defined(_GLIBCXX_RELEASE)
libstdc++ _GLIBCXX_RELEASE __GLIBCXX__
#else
unknown
#endif
AMC_STDLIB_END
"""


class EnvProblem(Exception):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message


@dataclass
class Toolchain:
    cxx: list            # argv prefix of the compiler, normally [path to clang++]
    clang_version: str = ""
    target: str = ""
    stdlib: str = ""

    def describe(self) -> dict:
        return {"cxx": " ".join(self.cxx), "clang_version": self.clang_version,
                "target": self.target, "stdlib": self.stdlib}


@dataclass
class BuildTools:
    cmake: str
    cmake_version: str
    ninja: str
    ninja_version: str

    def describe(self) -> dict:
        return {"cmake": self.cmake, "cmake_version": self.cmake_version,
                "ninja": self.ninja, "ninja_version": self.ninja_version}


def _which(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    path = Path(name)
    return str(path) if path.is_file() else None


def probe_compiler(cxx: str, min_major: int, work: Path) -> Toolchain:
    path = _which(cxx)
    if path is None:
        raise EnvProblem("compiler_missing", f"C++ compiler '{cxx}' was not found")
    if Path(path).stem.lower() in ("cl", "clang-cl"):
        raise EnvProblem("wrong_driver", f"'{path}' is an MSVC-style driver; the checker needs the clang++ driver")
    result = run_process([path, "--version"], cwd=work, env=None, timeout=60)
    if not result.started:
        raise EnvProblem("compiler_missing", f"'{path}' could not be started: {result.error}")
    text = result.stdout.decode("utf-8", errors="replace")
    first = text.splitlines()[0] if text.strip() else ""
    if "Apple clang" in first:
        raise EnvProblem("compiler_version", f"'{first}' is Apple clang, not LLVM Clang {min_major} or newer")
    found = _CLANG.search(first)
    if result.returncode != 0 or not found:
        raise EnvProblem("compiler_version", f"no Clang version in the output of '{path} --version': '{first}'")
    if int(found.group(1)) < min_major:
        raise EnvProblem("compiler_version", f"{found.group(0)} is older than Clang {min_major}")
    target = _TARGET.search(text)
    tool = Toolchain([path], ".".join(found.groups()), target.group(1) if target else "")
    tool.stdlib = probe_stdlib(tool, work)
    return tool


def probe_stdlib(tool: Toolchain, work: Path) -> str:
    source = work / "stdlib_probe.cpp"
    source.write_text(_PROBE, encoding="ascii")
    result = run_process(tool.cxx + ["-std=c++20", "-E", "-P", source.name], cwd=work, env=None, timeout=60)
    text = result.stdout.decode("utf-8", errors="replace")
    if result.returncode != 0 or "AMC_STDLIB_BEGIN" not in text:
        raise EnvProblem("stdlib_missing", "the C++ standard library headers could not be used: "
                         + result.stderr.decode("utf-8", errors="replace")[:400])
    inner = text.split("AMC_STDLIB_BEGIN", 1)[1].split("AMC_STDLIB_END", 1)[0]
    return " ".join(inner.split())


def probe_build_tools(cmake: str, ninja: str, work: Path) -> BuildTools:
    cmake_path = _which(cmake)
    if cmake_path is None:
        raise EnvProblem("cmake_missing", f"CMake '{cmake}' was not found")
    result = run_process([cmake_path, "--version"], cwd=work, env=None, timeout=60)
    found = _CMAKE.search(result.stdout.decode("utf-8", errors="replace")) if result.started else None
    if not found:
        raise EnvProblem("cmake_version", f"no CMake version from '{cmake_path} --version'")
    version = tuple(int(x) for x in found.groups())
    if version[:2] < MIN_CMAKE:
        raise EnvProblem("cmake_version", f"CMake {'.'.join(found.groups())} is older than {MIN_CMAKE[0]}.{MIN_CMAKE[1]}")
    ninja_path = _which(ninja)
    if ninja_path is None:
        raise EnvProblem("ninja_missing", f"Ninja '{ninja}' was not found")
    result = run_process([ninja_path, "--version"], cwd=work, env=None, timeout=60)
    if not result.started or result.returncode != 0:
        raise EnvProblem("ninja_missing", f"'{ninja_path} --version' failed")
    return BuildTools(cmake_path, ".".join(found.groups()), ninja_path,
                      result.stdout.decode("utf-8", errors="replace").strip())
