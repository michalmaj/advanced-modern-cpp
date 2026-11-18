"""The five modes against real compiler output (needs LLVM clang++ 22+)."""

import os
import sys
from pathlib import Path

from tests.checker.helpers import FAKE_COMPILER, CheckerTest, code, pair, wait_until_dead
from tools.checker.execute import Settings
from tools.checker.model import Status
from tools.checker.toolchain import Toolchain

HELLO = '#include <iostream>\n\nint main() {\n    std::cout << "hello\\n";\n}\n'
SENTINEL = "SENTINEL-selftest-was-executed.txt"
SENTINEL_PROGRAM = (
    "#include <fstream>\n\nint main() {\n"
    f'    std::ofstream trace{{"{SENTINEL}"}};\n'
    '    trace << "executed\\n";\n}\n'
)


class ModeTest(CheckerTest):
    def run_lesson(self, text, *, settings=None, work=None, extra_fail_flags=None, toolchain=None):
        root = self.make_repo(pair("course/lesson", text))
        return self.check(root, settings=settings, work=work, extra_fail_flags=extra_fail_flags,
                          toolchain=toolchain)

    def sentinels(self, folder: Path) -> list:
        return sorted(p.name for p in folder.rglob("SENTINEL-*"))


class RunModeTests(ModeTest):
    def test_matching_output_passes(self):
        result = self.run_lesson(code("<!-- run: hello -->", HELLO) + code("<!-- output: hello -->", "hello\n", "text"))
        self.one(result, "#hello/build", Status.PASS)
        self.one(result, "#hello/run1", Status.PASS)

    def test_different_output_fails(self):
        result = self.run_lesson(code("<!-- run: hello -->", HELLO) + code("<!-- output: hello -->", "bye\n", "text"))
        self.one(result, "#hello/run1", Status.FAIL, "output_mismatch")

    def test_standard_input_per_run(self):
        program = ('#include <iostream>\n#include <string>\n\nint main() {\n    std::string word;\n'
                   '    std::cin >> word;\n    std::cout << word << word << "\\n";\n}\n')
        text = (code("<!-- run: echo -->", program)
                + code("<!-- input: echo -->", "ab\n", "text") + code("<!-- output: echo -->", "abab\n", "text")
                + code("<!-- input: echo -->", "x\n", "text") + code("<!-- output: echo -->", "xx\n", "text"))
        result = self.run_lesson(text)
        self.one(result, "#echo/run1", Status.PASS)
        self.one(result, "#echo/run2", Status.PASS)

    def test_expected_exit_code(self):
        program = "int main() {\n    return 3;\n}\n"
        self.one(self.run_lesson(code("<!-- run: three exit=3 -->", program) + code("<!-- output: three -->", "", "text")),
                 "#three/run1", Status.PASS)
        self.one(self.run_lesson(code("<!-- run: three -->", program) + code("<!-- output: three -->", "", "text")),
                 "#three/run1", Status.FAIL, "exit_code")

    def test_stderr_fails_the_run(self):
        program = '#include <iostream>\n\nint main() {\n    std::cerr << "oops\\n";\n}\n'
        self.one(self.run_lesson(code("<!-- run: noisy -->", program) + code("<!-- output: noisy -->", "", "text")),
                 "#noisy/run1", Status.FAIL, "stderr")

    def test_run_timeout(self):
        program = ("#include <chrono>\n#include <thread>\n\nint main() {\n    for (;;) {\n"
                   "        std::this_thread::sleep_for(std::chrono::milliseconds(50));\n    }\n}\n")
        result = self.run_lesson(code("<!-- run: forever -->", program) + code("<!-- output: forever -->", "", "text"),
                                 settings=Settings(run_timeout=1.5))
        self.one(result, "#forever/run1", Status.FAIL, "timeout")

    def test_output_limit(self):
        program = ('#include <iostream>\n#include <string>\n\nint main() {\n    const std::string line(1000, \'x\');\n'
                   '    for (int i = 0; i < 100; ++i) {\n        std::cout << line << "\\n";\n    }\n}\n')
        result = self.run_lesson(code("<!-- run: loud -->", program) + code("<!-- output: loud -->", "", "text"))
        self.one(result, "#loud/run1", Status.FAIL, "output_limit")

    def test_abort_is_a_failure(self):
        # std::abort() is defined behaviour. On Windows the error-reporting dialog is switched off,
        # so the program ends at once with exit code 3; POSIX systems report SIGABRT.
        program = ("#include <cstdlib>\n\nint main() {\n#ifdef _WIN32\n"
                   "    _set_abort_behavior(0, _WRITE_ABORT_MSG | _CALL_REPORTFAULT);\n#endif\n"
                   "    std::abort();\n}\n")
        verdict = self.one(self.run_lesson(code("<!-- run: crash -->", program) + code("<!-- output: crash -->", "", "text")),
                           "#crash/run1", Status.FAIL)
        self.assertEqual(verdict.category, "exit_code" if os.name == "nt" else "crashed", verdict.actual)

    def test_warning_fails_the_strict_build(self):
        program = "int main() {\n    int unused{0};\n    return 0;\n}\n"
        result = self.run_lesson(code("<!-- compile: warns -->", program))
        verdict = self.one(result, "#warns/build", Status.FAIL, "build_failed")
        self.assertIn("-Wunused-variable", verdict.detail)

    def test_long_logs_are_shortened(self):
        program = "int main() {\n" + "    undeclared_name_with_a_long_spelling();\n" * 40 + "}\n"
        verdict = self.one(self.run_lesson(code("<!-- compile: noisy -->", program)), "#noisy/build", Status.FAIL)
        self.assertIn("more characters, not shown", verdict.detail)
        self.assertLess(len(verdict.detail), 1100)


class TestModeTests(ModeTest):
    def test_passing_and_failing_check_programs(self):
        ok = '#include <iostream>\n\nint main() {\n    std::cout << "PASS one\\n";\n    return 0;\n}\n'
        bad = '#include <iostream>\n\nint main() {\n    std::cout << "FAIL one\\n";\n    return 1;\n}\n'
        result = self.run_lesson(code("<!-- test: good -->", ok) + code("<!-- test: bad -->", bad))
        self.one(result, "#good/test", Status.PASS)
        self.one(result, "#bad/test", Status.FAIL, "test_failed")


class CompileFailTests(ModeTest):
    BROKEN = "int main() {\n    int value{1};\n    const int* reader{&value};\n    *reader = 2;\n    return value;\n}\n"

    def test_expected_error_passes(self):
        result = self.run_lesson(code("<!-- compile_fail: ro at=4:13 error=not assignable -->", self.BROKEN))
        self.one(result, "#ro", Status.PASS)

    def test_unrelated_error_is_the_wrong_reason(self):
        broken = self.BROKEN.replace("int value{1};", "int value{1};\n    undeclared();")
        result = self.run_lesson(code("<!-- compile_fail: ro at=5:13 error=not assignable -->", broken))
        self.one(result, "#ro", Status.FAIL, "wrong_location")

    def test_wrong_message_is_the_wrong_reason(self):
        result = self.run_lesson(code("<!-- compile_fail: ro at=4:13 error=undeclared identifier -->", self.BROKEN))
        self.one(result, "#ro", Status.FAIL, "wrong_message")

    def test_a_warning_alone_is_not_a_compile_error(self):
        program = "int main() {\n    int unused{0};\n    return 0;\n}\n"
        result = self.run_lesson(code("<!-- compile_fail: warn at=2:9 error=unused -->", program))
        self.one(result, "#warn", Status.FAIL, "unexpected_success")

    def test_warning_turned_into_an_error_by_werror(self):
        program = "int main() {\n    int unused{0};\n    return 0;\n}\n"
        result = self.run_lesson(code("<!-- compile_fail: warn at=2:9 error=unused -->", program),
                                 extra_fail_flags=["-Werror"])
        self.one(result, "#warn", Status.FAIL, "werror_only")

    def test_warning_turned_into_an_error_by_a_pragma(self):
        program = ('#pragma clang diagnostic error "-Wunused-variable"\n'
                   "int main() {\n    int unused{0};\n    return 0;\n}\n")
        result = self.run_lesson(code("<!-- compile_fail: warn at=3:9 error=unused -->", program))
        self.one(result, "#warn", Status.FAIL, "werror_only")

    def test_narrowing_is_a_real_error_despite_its_option_tag(self):
        program = "int main() {\n    double d{1.5};\n    int n{d};\n    return n;\n}\n"
        result = self.run_lesson(code("<!-- compile_fail: narrow at=3:11 error=narrowed -->", program))
        self.one(result, "#narrow", Status.PASS)

    def test_missing_compiler_is_an_environment_problem(self):
        tool = Toolchain([str(Path(self.work_dir()) / "missing-clang++")])
        result = self.run_lesson(code("<!-- compile_fail: ro at=4:13 error=x -->", self.BROKEN), toolchain=tool)
        self.one(result, "#ro", Status.ENV_ERROR, "compiler_missing")

    def test_compiler_crash_is_an_environment_problem(self):
        fake = self.work_dir() / "fake_cc.py"
        fake.write_text(FAKE_COMPILER)
        tool = Toolchain([sys.executable, str(fake), "crash"])
        result = self.run_lesson(code("<!-- compile_fail: ro at=4:13 error=x -->", self.BROKEN), toolchain=tool)
        self.one(result, "#ro", Status.ENV_ERROR, "compiler_crash")

    def test_compile_timeout_stops_the_compiler_and_its_children(self):
        work = self.work_dir()
        fake = work / "fake_cc.py"
        fake.write_text(FAKE_COMPILER)
        pid_file = work / "child.pid"
        tool = Toolchain([sys.executable, str(fake), "sleep", str(pid_file)])
        result = self.run_lesson(code("<!-- compile_fail: ro at=4:13 error=x -->", self.BROKEN), toolchain=tool,
                                 settings=Settings(compile_timeout=2))
        self.one(result, "#ro", Status.ENV_ERROR, "compile_timeout")
        self.assertTrue(pid_file.exists(), "the fake compiler never started its child")
        self.assertTrue(wait_until_dead(int(pid_file.read_text())), "a child of the compiler survived the timeout")

    def test_missing_source_file_is_refused_before_compiling(self):
        text = (code("<!-- compile_fail: ro at=4:13 error=x -->", self.BROKEN)
                + code("<!-- file: ro h.hpp source=support/missing.hpp -->", "#pragma once\n"))
        result = self.run_lesson(text)
        self.assertProtocol(result, "missing_file")
        self.assertEqual(result.summary["examples_built"], 0)


class UnsafeTests(ModeTest):
    DANGLING = "const int& pick_local() {\n    int local{42};\n    return local;\n}\n\nint main() {\n    return 0;\n}\n"

    def test_allowed_warning_passes_and_says_it_was_not_run(self):
        verdict = self.one(self.run_lesson(code("<!-- compile_unsafe: d allow=-Wreturn-stack-address@3 -->",
                                                self.DANGLING)), "#d", Status.PASS)
        self.assertIn("not run", verdict.actual)

    def test_unexpected_warning_fails(self):
        self.one(self.run_lesson(code("<!-- compile_unsafe: d -->", self.DANGLING)), "#d", Status.FAIL,
                 "unexpected_warning")

    def test_warning_on_another_line_is_unexpected(self):
        self.one(self.run_lesson(code("<!-- compile_unsafe: d allow=-Wreturn-stack-address@2 -->", self.DANGLING)),
                 "#d", Status.FAIL, "unexpected_warning")

    def test_missing_allowed_warning_fails(self):
        clean = "int main() {\n    return 0;\n}\n"
        self.one(self.run_lesson(code("<!-- compile_unsafe: d allow=-Wreturn-stack-address@3 -->", clean)),
                 "#d", Status.FAIL, "missing_warning")

    def test_sentinel_is_never_executed(self):
        work = self.work_dir()
        result = self.run_lesson(code("<!-- compile_unsafe: sentinel -->", SENTINEL_PROGRAM), work=work)
        self.one(result, "#sentinel", Status.PASS)
        self.assertEqual(self.sentinels(work), [])
        files = sorted(p.relative_to(work).as_posix() for p in work.rglob("*") if p.is_file())
        self.assertEqual([f.split("/", 1)[1] for f in files], ["src/main.cpp"], files)

    def test_sentinel_does_appear_when_the_same_program_is_run(self):
        # Control: proves that the sentinel would show an execution.
        work = self.work_dir()
        result = self.run_lesson(code("<!-- run: sentinel -->", SENTINEL_PROGRAM)
                                 + code("<!-- output: sentinel -->", "", "text"), work=work)
        self.one(result, "#sentinel/run1", Status.PASS)
        self.assertEqual(self.sentinels(work), [SENTINEL])

    def test_forcing_a_run_of_unsafe_code_is_refused(self):
        work = self.work_dir()
        result = self.run_lesson(code("<!-- compile_unsafe: sentinel -->", SENTINEL_PROGRAM)
                                 + code("<!-- input: sentinel -->", "x\n", "text")
                                 + code("<!-- output: sentinel -->", "", "text"), work=work)
        self.assertProtocol(result, "mode_conflict")
        self.assertEqual(result.summary["examples_built"], 0)
        self.assertEqual(self.sentinels(work), [])

    def test_protocol_error_stops_the_whole_lesson(self):
        work = self.work_dir()
        result = self.run_lesson(code("<!-- run: sentinel -->", SENTINEL_PROGRAM)
                                 + code("<!-- output: sentinel -->", "", "text")
                                 + code("<!-- static_unsafe: other -->", "int main() {}\n"), work=work)
        self.assertProtocol(result, "unknown_kind")
        self.assertEqual(result.summary["examples_built"], 0)
        self.assertEqual(self.sentinels(work), [])

    def test_compile_mode_links_but_does_not_run(self):
        work = self.work_dir()
        result = self.run_lesson(code("<!-- compile: sentinel -->", SENTINEL_PROGRAM), work=work)
        self.one(result, "#sentinel/build", Status.PASS)
        self.assertEqual(self.sentinels(work), [])
        self.assertTrue(any(p.name.startswith("program") for p in work.rglob("*")), "compile mode should link")
