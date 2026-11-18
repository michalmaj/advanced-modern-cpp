"""Command line, exit codes and reports."""

import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.checker.helpers import REPO, CheckerTest
from tools.checker import cli
from tools.checker.engine import run_check
from tools.checker.execute import Settings
from tools.checker.model import STABLE_FIELDS
from tools.checker.report import compare, make_report, write_report

FIXTURES = "tests/checker/fixtures/lessons"


def run_cli(*args) -> int:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return cli.main(list(args))


class ExitCodeTests(CheckerTest):
    def test_fixtures_pass_with_exit_code_0(self):
        self.need_toolchain()
        self.assertEqual(run_cli("check", FIXTURES), 0)

    def test_content_failure_is_exit_code_1(self):
        self.need_toolchain()
        self.assertEqual(run_cli("check", "tests/checker/cli_cases/content_failure"), 1)

    def test_protocol_error_is_exit_code_2(self):
        self.assertEqual(run_cli("lint", "tests/checker/cli_cases/protocol_error"), 2)
        self.assertEqual(run_cli("check", "tests/checker/cli_cases/protocol_error"), 2)

    def test_missing_compiler_is_exit_code_3(self):
        self.assertEqual(run_cli("check", FIXTURES, "--cxx", "definitely-not-a-compiler"), 3)

    def test_internal_error_is_exit_code_4(self):
        with mock.patch.object(cli, "run_check", side_effect=RuntimeError("simulated bug")):
            self.assertEqual(run_cli("lint", FIXTURES), 4)

    def test_work_folder_inside_the_sources_is_refused(self):
        self.assertEqual(run_cli("check", FIXTURES, "--work-dir", "tests/checker/work"), 2)
        self.assertFalse((REPO / "tests" / "checker" / "work").exists())


class ReportTests(CheckerTest):
    def test_reports_are_repeatable(self):
        tool = self.need_toolchain()
        first = make_report(run_check([FIXTURES], REPO, toolchain=tool))
        second = make_report(run_check([FIXTURES], REPO, toolchain=tool))
        self.assertEqual(compare([("first", first), ("second", second)]), [])
        self.assertEqual(first["exit_code"], 0)
        ids = [v["id"] for v in first["verdicts"]]
        self.assertEqual(len(ids), len(set(ids)), "verdict ids must be unique")

    def test_stable_fields_hold_no_environment_values(self):
        # A tool version or a path in a stable field would make reports of different systems differ.
        tool = self.need_toolchain()
        self.need_build_tools()
        report = make_report(run_check([FIXTURES], REPO, toolchain=tool, settings=Settings(
            cmake=os.environ.get("CMAKE", "cmake"), ninja=os.environ.get("NINJA", "ninja"))))
        env = report["environment"]
        values = [str(env[key]) for key in ("clang_version", "target", "stdlib", "cmake_version",
                                             "ninja_version", "cxx", "cmake", "ninja") if env.get(key)]
        self.assertIn("cmake_version", env, "the fixtures include a directory project")
        for verdict in report["verdicts"]:
            for field in STABLE_FIELDS:
                for value in values:
                    self.assertNotIn(value, str(verdict[field]), f"{verdict['id']}: {field} contains {value!r}")

    def test_report_file_is_sorted_json(self):
        result = run_check([FIXTURES], REPO, build=False)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            write_report(path, make_report(result))
            text = path.read_text(encoding="utf-8")
        self.assertEqual(json.dumps(json.loads(text), indent=2, sort_keys=True, ensure_ascii=True) + "\n", text)

    def test_compare_finds_differences_in_stable_fields_only(self):
        tool = self.need_toolchain()
        base = make_report(run_check([FIXTURES], REPO, toolchain=tool))
        other = copy.deepcopy(base)
        for verdict in other["verdicts"]:
            verdict["duration_ms"] += 1000
            verdict["detail"] = "platform-specific text"
        self.assertEqual(compare([("a", base), ("b", other)]), [])
        other["verdicts"][0]["status"] = "fail"
        self.assertEqual(len(compare([("a", base), ("b", other)])), 1)
        del other["verdicts"][-1]
        self.assertTrue(any("no verdict" in line for line in compare([("a", base), ("b", other)])))

    def test_compare_command(self):
        result = run_check([FIXTURES], REPO, build=False)
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.json", Path(tmp) / "b.json"
            report = make_report(result)
            write_report(a, report)
            write_report(b, report)
            self.assertEqual(run_cli("compare", str(a), str(b)), 0)
            report["verdicts"].append({"id": "extra", "source": "x", "mode": "run", "expected": "",
                                       "status": "pass", "category": ""})
            write_report(b, report)
            self.assertEqual(run_cli("compare", str(a), str(b)), 1)
            b.write_text("{}", encoding="utf-8")
            self.assertEqual(run_cli("compare", str(a), str(b)), 2)


if __name__ == "__main__":
    unittest.main()
