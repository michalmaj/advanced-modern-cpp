"""Shared helpers for the checker self-tests.

Tests that need the toolchain are skipped when LLVM clang++ 22+ (or CMake and
Ninja) are missing, unless AMC_CHECKER_REQUIRE_TOOLCHAIN=1 is set, as in CI:
then a missing tool fails the test instead of hiding it.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tools.checker.engine import run_check
from tools.checker.model import Status
from tools.checker.proc import pid_alive
from tools.checker.toolchain import EnvProblem, probe_build_tools, probe_compiler

REPO = Path(__file__).resolve().parents[2]
ROOTS = ("course", "projects", "support")
REQUIRE = os.environ.get("AMC_CHECKER_REQUIRE_TOOLCHAIN") == "1"
_CACHE: dict = {}

FAKE_COMPILER = r'''
import subprocess, sys, time
mode = sys.argv[1]
if mode == "crash":
    sys.stderr.write("PLEASE submit a bug report to https://example.invalid/ and include the crash backtrace.\n")
    sys.stderr.write("clang++: error: clang frontend command failed with exit code 139\n")
    sys.exit(1)
if mode == "sleep":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    with open(sys.argv[2], "w") as handle:
        handle.write(str(child.pid))
    time.sleep(60)
'''


def _probe(key, func):
    if key not in _CACHE:
        work = Path(tempfile.mkdtemp(prefix="amc-probe-"))
        try:
            _CACHE[key] = (func(work), None)
        except EnvProblem as exc:
            _CACHE[key] = (None, exc.message)
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return _CACHE[key]


def toolchain():
    return _probe("cxx", lambda work: probe_compiler(os.environ.get("CXX", "clang++"), 22, work))


def build_tools():
    return _probe("tools", lambda work: probe_build_tools(os.environ.get("CMAKE", "cmake"),
                                                          os.environ.get("NINJA", "ninja"), work))


def code(marker: str, body: str, lang: str = "cpp") -> str:
    return f"{marker}\n\n```{lang}\n{body}```\n"


def pair(base: str, text: str, en_text: str | None = None) -> dict:
    return {f"{base}.md": text, f"{base}.en.md": text if en_text is None else en_text}


def wait_until_dead(pid: int, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return True
        time.sleep(0.05)
    return not pid_alive(pid)


def dump(result) -> str:
    return "\n".join(f"{v.status.value:<15} {v.category:<20} {v.id}: {v.actual}" for v in result.verdicts)


class CheckerTest(unittest.TestCase):
    maxDiff = None

    def make_repo(self, files: dict) -> Path:
        root = Path(tempfile.mkdtemp(prefix="amc-selftest-"))
        self.addCleanup(shutil.rmtree, root, True)
        for rel, content in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        return root

    def work_dir(self) -> Path:
        path = Path(tempfile.mkdtemp(prefix="amc-selftest-work-"))
        self.addCleanup(shutil.rmtree, path, True)
        return path

    def need_toolchain(self):
        tool, problem = toolchain()
        if tool is None:
            if REQUIRE:
                self.fail(f"the toolchain is required here: {problem}")
            self.skipTest(f"no LLVM clang++ 22 or newer: {problem}")
        return tool

    def need_build_tools(self):
        tools, problem = build_tools()
        if tools is None:
            if REQUIRE:
                self.fail(f"CMake and Ninja are required here: {problem}")
            self.skipTest(f"no CMake 3.28+ or Ninja: {problem}")
        return tools

    def check(self, root, paths=("course",), *, build=True, settings=None, toolchain=None,
              work=None, extra_fail_flags=None):
        if build and toolchain is None:
            toolchain = self.need_toolchain()
        return run_check(list(paths), root, build=build, settings=settings, allowed_roots=ROOTS,
                         work_dir=work, keep_work=work is not None, toolchain=toolchain,
                         extra_fail_flags=extra_fail_flags)

    def lint(self, root, paths=("course",)):
        return self.check(root, paths, build=False)

    def one(self, result, suffix: str, status: Status, category: str = ""):
        matches = [v for v in result.verdicts if v.id.endswith(suffix)]
        self.assertEqual(len(matches), 1, f"verdicts ending with {suffix!r}:\n{dump(result)}")
        verdict = matches[0]
        self.assertEqual(verdict.status, status, dump(result))
        if category:
            self.assertEqual(verdict.category, category, dump(result))
        return verdict

    def protocol_categories(self, result) -> list:
        return sorted({v.category for v in result.verdicts if v.status is Status.PROTOCOL_ERROR})

    def assertProtocol(self, result, category: str) -> None:
        self.assertIn(category, self.protocol_categories(result), dump(result))

    def assertClean(self, result) -> None:
        bad = [v for v in result.verdicts if v.status is not Status.PASS]
        self.assertEqual(bad, [], dump(result))


PYTHON = sys.executable
