"""against=: the check program must reject a deliberately faulty implementation."""

from tests.checker.helpers import CheckerTest, code, pair
from tools.checker.execute import Settings
from tools.checker.model import Status

HEADER = "#pragma once\n\nint twice(int value);\n"
CORRECT = '#include "twice.hpp"\n\nint twice(int value) {\n    return 2 * value;\n}\n'
CHECKS = ('#include <iostream>\n\n#include "twice.hpp"\n\nint main() {\n    const bool ok{twice(3) == 6};\n'
          '    std::cout << (ok ? "PASS twice\\n" : "FAIL twice\\n");\n    return ok ? 0 : 1;\n}\n')
FAULTY = {
    "wrong": '#include "twice.hpp"\n\nint twice(int value) {\n    return value + 2;\n}\n',
    "untested": '#include "twice.hpp"\n\nint twice(int value) {\n    return value == 3 ? 6 : 0;\n}\n',
    "no_build": '#include "twice.hpp"\n\nint twice(int value) {\n    return undefined_name(value);\n}\n',
    "wrong_signature": '#include "twice.hpp"\n\nlong twice(long value) {\n    return 2 * value;\n}\n',
    "hangs": ('#include <chrono>\n#include <thread>\n\n#include "twice.hpp"\n\nint twice(int) {\n    for (;;) {\n'
              '        std::this_thread::sleep_for(std::chrono::milliseconds(50));\n    }\n}\n'),
    "aborts": ('#include <cstdlib>\n\n#include "twice.hpp"\n\nint twice(int) {\n#ifdef _WIN32\n'
               '    _set_abort_behavior(0, _WRITE_ABORT_MSG | _CALL_REPORTFAULT);\n#endif\n    std::abort();\n}\n'),
    "loud": ('#include <iostream>\n\n#include "twice.hpp"\n\nint twice(int value) {\n'
             '    std::cerr << "debug output\\n";\n    return value;\n}\n'),
}


def lesson(faulty_name: str = "wrong", checks: str = CHECKS, against: str | None = None) -> str:
    target = against or f"support/faulty/{faulty_name}/twice.cpp"
    return (code(f"<!-- test: checks against={target} -->", checks)
            + code("<!-- file: checks twice.hpp -->", HEADER) + code("<!-- file: checks twice.cpp -->", CORRECT))


class AgainstTests(CheckerTest):
    def files(self) -> dict:
        return {f"support/faulty/{name}/twice.cpp": body for name, body in FAULTY.items()}

    def run_case(self, text: str, settings=None):
        return self.check(self.make_repo({**pair("course/lesson", text), **self.files()}), settings=settings)

    def test_detected_fault_passes(self):
        result = self.run_case(lesson("wrong"))
        self.one(result, "#checks/test", Status.PASS)
        verdict = self.one(result, "#checks/against", Status.PASS)
        self.assertIn("rejected with exit code 1", verdict.actual)

    def test_fault_that_the_checks_miss_is_refused(self):
        self.one(self.run_case(lesson("untested")), "#checks/against", Status.FAIL, "faulty_not_detected")

    def test_build_failure_is_not_a_detection(self):
        for name in ("no_build", "wrong_signature"):
            with self.subTest(faulty=name):
                self.one(self.run_case(lesson(name)), "#checks/against", Status.FAIL, "faulty_build_failed")

    def test_hang_is_not_a_detection(self):
        self.one(self.run_case(lesson("hangs"), settings=Settings(run_timeout=1.5)),
                 "#checks/against", Status.FAIL, "faulty_timeout")

    def test_crash_is_not_a_detection(self):
        import os
        verdict = self.one(self.run_case(lesson("aborts")), "#checks/against", Status.FAIL)
        # POSIX reports SIGABRT; on Windows abort() ends with exit code 3, which is not the agreed report.
        self.assertEqual(verdict.category, "faulty_unrecognized" if os.name == "nt" else "faulty_crashed")

    def test_rejection_must_follow_the_protocol(self):
        no_fail_line = CHECKS.replace('"FAIL twice\\n"', '"wrong result\\n"')
        other_code = CHECKS.replace("return ok ? 0 : 1;", "return ok ? 0 : 2;")
        for name, checks, faulty in (("no FAIL line", no_fail_line, "wrong"), ("exit code 2", other_code, "wrong"),
                                     ("stderr", CHECKS, "loud")):
            with self.subTest(case=name):
                self.one(self.run_case(lesson(faulty, checks)), "#checks/against", Status.FAIL, "faulty_unrecognized")

    def test_failing_correct_implementation_cannot_be_judged(self):
        broken_checks = CHECKS.replace("twice(3) == 6", "twice(3) == 7")
        self.one(self.run_case(lesson("wrong", broken_checks)), "#checks/against", Status.FAIL, "correct_failed")

    def test_against_rules(self):
        cases = {
            "support/faulty/wrong/other.cpp": "against_target_missing",
            "support/faulty/main.cpp": "against_target_missing",
            "support/faulty/same/twice.cpp": "against_identical",
            "support/faulty/none/twice.cpp": "missing_file",
            "support/../outside/twice.cpp": "path_escape",
            "elsewhere/twice.cpp": "path_not_allowed",
        }
        extra = {**self.files(), "support/faulty/wrong/other.cpp": CORRECT, "support/faulty/main.cpp": CORRECT,
                 "support/faulty/same/twice.cpp": CORRECT, "elsewhere/twice.cpp": FAULTY["wrong"]}
        for target, category in cases.items():
            with self.subTest(target=target):
                result = self.lint(self.make_repo({**pair("course/lesson", lesson(against=target)), **extra}))
                self.assertProtocol(result, category)

    def test_against_is_only_for_test_programs(self):
        text = (code("<!-- run: demo against=support/faulty/wrong/twice.cpp -->", CHECKS)
                + code("<!-- output: demo -->", "PASS twice\n", "text"))
        self.assertProtocol(self.lint(self.make_repo({**pair("course/lesson", text), **self.files()})), "bad_attribute")
