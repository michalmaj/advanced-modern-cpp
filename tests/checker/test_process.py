"""Process control: time limit, output limit, process groups, the execution guard."""

import tempfile
import time
import unittest
from pathlib import Path

from tests.checker.helpers import PYTHON, CheckerTest, wait_until_dead
from tools.checker.execute import Context, Settings, check_run, check_started, execute_binary
from tools.checker.model import Block, GuardViolation, Marker, Program, Status
from tools.checker.proc import ProcResult, run_process


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="amc-proc-"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_exit_code_and_separate_streams(self):
        r = run_process([PYTHON, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"],
                        cwd=self.tmp, env=None, timeout=30)
        self.assertEqual((r.returncode, r.stdout.strip(), r.stderr.strip()), (3, b"out", b"err"))
        self.assertFalse(r.timed_out)

    def test_standard_input_is_given(self):
        r = run_process([PYTHON, "-c", "import sys; print(sys.stdin.read().upper(), end='')"],
                        cwd=self.tmp, env=None, timeout=30, stdin=b"abc\n")
        self.assertEqual(r.stdout.replace(b"\r\n", b"\n"), b"ABC\n")

    def test_timeout_stops_the_whole_process_group(self):
        pid_file = self.tmp / "child.pid"
        script = ("import subprocess, sys, time\n"
                  "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                  f"open({str(pid_file)!r}, 'w').write(str(child.pid))\n"
                  "time.sleep(60)\n")
        start = time.monotonic()
        r = run_process([PYTHON, "-c", script], cwd=self.tmp, env=None, timeout=2)
        self.assertTrue(r.timed_out)
        self.assertLess(time.monotonic() - start, 20)
        self.assertTrue(pid_file.exists(), "the child process never started")
        self.assertTrue(wait_until_dead(int(pid_file.read_text())), "the grandchild survived the timeout")

    def test_output_limit_stops_the_program(self):
        start = time.monotonic()
        r = run_process([PYTHON, "-c", "import sys\nwhile True: sys.stdout.write('x' * 1000)"],
                        cwd=self.tmp, env=None, timeout=30, limit=65536)
        self.assertEqual(r.overflow, "stdout")
        self.assertEqual(len(r.stdout), 65536)
        self.assertLess(time.monotonic() - start, 20)

    def test_exact_limit_is_allowed(self):
        r = run_process([PYTHON, "-c", "import sys; sys.stdout.write('x' * 1000)"],
                        cwd=self.tmp, env=None, timeout=30, limit=1000)
        self.assertEqual((r.overflow, len(r.stdout)), ("", 1000))

    def test_missing_program_is_not_started(self):
        r = run_process([str(self.tmp / "no-such-program")], cwd=self.tmp, env=None, timeout=5)
        self.assertFalse(r.started)
        self.assertTrue(r.error)


class NormalisationTests(unittest.TestCase):
    """Line-end normalisation in the judgement of a run, independent of the platform's text mode."""

    def judge(self, stdout: bytes, expected: str):
        ctx = Context(Path("."), None, Path("."), Settings())
        result = ProcResult(started=True, returncode=0, stdout=stdout)
        return check_started(ctx, "x/run1", "x", "run", result, 0, expected)

    def test_windows_line_ends_become_newlines(self):
        self.assertEqual(self.judge(b"a\r\nb\r\n", "a\nb\n").status, Status.PASS)

    def test_lone_carriage_return_is_kept(self):
        verdict = self.judge(b"a\rb\n", "ab\n")
        self.assertEqual((verdict.status, verdict.category), (Status.FAIL, "output_mismatch"))

    def test_missing_final_line_end_is_a_difference(self):
        self.assertEqual(self.judge(b"a", "a\n").category, "output_mismatch")


class GuardTests(CheckerTest):
    def test_only_run_and_test_programs_can_be_started(self):
        ctx = Context(Path("."), None, Path("."), Settings())
        for kind in ("compile_unsafe", "compile", "compile_fail", "fragment"):
            with self.subTest(kind=kind), self.assertRaises(GuardViolation):
                execute_binary(kind, ctx, Path("never"), Path("."), None)

    def test_run_check_refuses_an_unsafe_program(self):
        marker = Marker("compile_unsafe", "x", {}, 1, "<!-- compile_unsafe: x -->")
        program = Program("x", "compile_unsafe", marker, Block("cpp", "int main() {}\n", 2))
        ctx = Context(Path("."), None, self.work_dir(), Settings())
        with self.assertRaises(GuardViolation):
            check_run(ctx, type("L", (), {"rel": "x.md"})(), program)
