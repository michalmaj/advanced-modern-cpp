"""Command line: python -m tools.checker COMMAND ..."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import traceback
import unittest
from pathlib import Path

from .engine import REPO_ROOT, run_check
from .execute import Settings
from .model import EXIT_CODE, ProtocolIssue, Status
from .report import compare, load_report, make_report, print_text, write_report
from .toolchain import EnvProblem, probe_build_tools, probe_compiler

INTERNAL = EXIT_CODE[Status.INTERNAL_ERROR]


def _settings(args) -> Settings:
    return Settings(
        compile_timeout=args.compile_timeout, configure_timeout=args.compile_timeout,
        run_timeout=args.run_timeout, output_limit=args.output_limit,
        cmake=args.cmake, ninja=args.ninja, min_clang=args.min_clang,
    )


def _tool_options(parser) -> None:
    parser.add_argument("--cxx", default=os.environ.get("CXX", "clang++"),
                        help="clang++ to use (default: $CXX or clang++)")
    parser.add_argument("--cmake", default="cmake", help="CMake for directory projects")
    parser.add_argument("--ninja", default="ninja", help="Ninja for directory projects")
    parser.add_argument("--min-clang", type=int, default=22, help="lowest accepted Clang major version")


def _cmd_check(args, build: bool) -> int:
    settings = _settings(args) if build else Settings()
    result = run_check(args.paths, REPO_ROOT, build=build, cxx=getattr(args, "cxx", "clang++"),
                       settings=settings, work_dir=getattr(args, "work_dir", None),
                       keep_work=getattr(args, "keep_work", False))
    print_text(result, sys.stdout, verbose=args.verbose)
    report = make_report(result)
    if args.report:
        write_report(args.report, report)
    return report["exit_code"]


def _cmd_compare(args) -> int:
    try:
        named = [(path, load_report(path)) for path in args.reports]
    except (OSError, ValueError) as exc:
        print(f"compare: {exc}", file=sys.stderr)
        return EXIT_CODE[Status.PROTOCOL_ERROR]
    differences = compare(named)
    for line in differences:
        print(line)
    rows = len(named[0][1]["verdicts"])
    if differences:
        print(f"{len(differences)} difference(s) in the stable fields")
        return 1
    print(f"{len(named)} reports agree on all {rows} verdicts (fields: id, source, mode, expected, status, category)")
    return 0


def _cmd_selftest(args) -> int:
    loader = unittest.TestLoader()
    if args.pattern:
        loader.testNamePatterns = [args.pattern]
    suite = loader.discover(start_dir=str(REPO_ROOT / "tests" / "checker"), pattern="test_*.py",
                            top_level_dir=str(REPO_ROOT))
    outcome = unittest.TextTestRunner(verbosity=2 if args.verbose else 1, stream=sys.stdout).run(suite)
    skipped = len(outcome.skipped)
    print(f"self-test: {outcome.testsRun} run, {len(outcome.failures)} failed, "
          f"{len(outcome.errors)} errors, {skipped} skipped")
    for test, reason in outcome.skipped:
        print(f"  skipped {test.id()}: {reason}")
    return 0 if outcome.wasSuccessful() else 1


def _cmd_toolchain(args) -> int:
    with tempfile.TemporaryDirectory(prefix="amc-probe-") as work:
        info = {}
        try:
            info.update(probe_compiler(args.cxx, args.min_clang, Path(work)).describe())
            info.update(probe_build_tools(args.cmake, args.ninja, Path(work)).describe())
        except EnvProblem as exc:
            info["problem"] = {"category": exc.category, "message": exc.message}
            print(json.dumps(info, indent=2, sort_keys=True))
            return EXIT_CODE[Status.ENV_ERROR]
    print(json.dumps(info, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.checker",
                                     description="Checks the marked examples of the course lessons.")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="check markers, PL/EN pairs, then build and run the examples")
    check.add_argument("paths", nargs="+", help="lesson files or folders, relative to the repository")
    _tool_options(check)
    check.add_argument("--report", help="write the JSON report to this file")
    check.add_argument("--work-dir", help="work folder (default: a new temporary folder)")
    check.add_argument("--keep-work", action="store_true", help="keep the work folder after the check")
    check.add_argument("--compile-timeout", type=float, default=120.0, help="seconds per compiler or CMake call")
    check.add_argument("--run-timeout", type=float, default=10.0, help="seconds per run of an example")
    check.add_argument("--output-limit", type=int, default=65536, help="bytes per output stream of a run")
    check.add_argument("--verbose", action="store_true", help="also list passing verdicts")

    lint = sub.add_parser("lint", help="check markers, paths, projects and PL/EN pairs only (no compiler)")
    lint.add_argument("paths", nargs="+")
    lint.add_argument("--report")
    lint.add_argument("--verbose", action="store_true")

    cmp = sub.add_parser("compare", help="compare the stable fields of two or more reports")
    cmp.add_argument("reports", nargs="+")

    selftest = sub.add_parser("selftest", help="run the checker's own tests")
    selftest.add_argument("--verbose", action="store_true")
    selftest.add_argument("-k", dest="pattern", help="run only tests whose name contains this text")

    tool = sub.add_parser("toolchain", help="identify clang++, the standard library, CMake and Ninja")
    _tool_options(tool)
    return parser


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")  # program output may not fit the console code page
    args = build_parser().parse_args(argv)
    try:
        if args.command == "check":
            return _cmd_check(args, build=True)
        if args.command == "lint":
            return _cmd_check(args, build=False)
        if args.command == "compare":
            if len(args.reports) < 2:
                print("compare needs at least two reports", file=sys.stderr)
                return EXIT_CODE[Status.PROTOCOL_ERROR]
            return _cmd_compare(args)
        if args.command == "selftest":
            return _cmd_selftest(args)
        return _cmd_toolchain(args)
    except ProtocolIssue as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return EXIT_CODE[Status.PROTOCOL_ERROR]
    except Exception:  # noqa: BLE001 - any unexpected failure is an internal error
        print("internal error in the checker:", file=sys.stderr)
        print("".join(traceback.format_exc().splitlines(keepends=True)[-20:]), file=sys.stderr)
        return INTERNAL
