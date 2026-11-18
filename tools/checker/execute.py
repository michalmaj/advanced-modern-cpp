"""Building, compiling and running examples.

Markdown programs are compiled with one direct clang++ call; directory
projects are configured and built with CMake and Ninja, as a learner does.
Only `run` and `test` programs are ever started, and only through
`execute_binary`, which refuses every other kind.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .datafiles import fingerprint, fresh_run_folder, run_input
from .diagnostics import compiler_crashed, parse
from .model import EXECUTED_KINDS, UNSAFE_KINDS, GuardViolation, Status, Verdict
from .proc import run_process
from .toolchain import EnvProblem, probe_build_tools

STD = ["-std=c++20"]
WARNINGS = ["-Wall", "-Wextra", "-Wpedantic"]
STRICT = WARNINGS + ["-Werror"]
DIAGNOSTIC_FORMAT = ["-fno-color-diagnostics", "-fno-caret-diagnostics",
                     "-fdiagnostics-show-option", "-fmessage-length=0"]
EXE = ".exe" if os.name == "nt" else ""
TOOL_OUTPUT_LIMIT = 4 * 1024 * 1024


@dataclass
class Settings:
    compile_timeout: float = 120.0
    configure_timeout: float = 120.0
    run_timeout: float = 10.0
    output_limit: int = 65536
    log_limit: int = 1000
    cmake: str = "cmake"
    ninja: str = "ninja"
    min_clang: int = 22


class Context:
    def __init__(self, repo_root: Path, toolchain, work_root: Path, settings: Settings,
                 extra_fail_flags=None) -> None:
        self.repo_root = repo_root
        self.toolchain = toolchain
        self.work_root = work_root
        self.settings = settings
        self.extra_fail_flags = list(extra_fail_flags or [])  # self-tests only
        self._build_tools = None
        self._build_tools_problem = None

    def build_tools(self):
        if self._build_tools is None and self._build_tools_problem is None:
            try:
                self._build_tools = probe_build_tools(self.settings.cmake, self.settings.ninja, self.work_root)
            except EnvProblem as exc:
                self._build_tools_problem = exc
        if self._build_tools_problem is not None:
            raise self._build_tools_problem
        return self._build_tools


def shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"... {len(text) - limit} more characters, not shown"


def decode(data: bytes) -> str:
    # Technical normalisation only: "\r\n" becomes "\n"; a lone "\r" is kept.
    return data.decode("utf-8", errors="replace").replace("\r\n", "\n")


def example_env() -> dict:
    """A small, predictable environment for started examples."""
    keep = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP") if os.name == "nt" else ("PATH",)
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env["LC_ALL"] = "C"
    env["TZ"] = "UTC"
    return env


def example_dir(ctx: Context, rel: str, name: str) -> Path:
    digest = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:8]
    path = ctx.work_root / f"{digest}-{name}"
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def verdict(vid, rel, mode, expected, status, category="", actual="", detail="", duration=0) -> Verdict:
    return Verdict(id=vid, source=rel, mode=mode, expected=expected, status=status,
                   category=category, actual=actual, detail=detail, duration_ms=duration)


def write_program(program, src: Path, replace: dict | None = None) -> list:
    """Write main.cpp and the program's files; REPLACE maps file names to other contents."""
    replace = replace or {}
    src.mkdir(parents=True, exist_ok=True)
    (src / "main.cpp").write_bytes(program.main.content.encode("ascii"))
    sources = ["main.cpp"]
    for path, block in program.files:
        (src / path).write_bytes(replace.get(path, block.content).encode("ascii"))
        if path.endswith(".cpp"):
            sources.append(path)
    return sources


def _originals(owner) -> list:
    return [owner.data_root] + [run.stdin_path for run in owner.runs]


def check_originals(rel: str, base: str, mode: str, before: dict, owner) -> list:
    """A FAIL verdict when a run changed a data file of the repository; [] otherwise."""
    after = fingerprint(_originals(owner))
    if after == before:
        return []
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    return [verdict(f"{base}/data", rel, mode, "data files in the repository stay unchanged",
                    Status.FAIL, "source_modified",
                    f"a run changed {len(changed)} original data file(s) outside its working copy",
                    ", ".join(Path(c).name for c in changed))]


def tool_problem(result, what: str, timeout: float, ctx: Context):
    """An environment problem of a compiler or build-tool call, or None."""
    if not result.started:
        return ("compiler_missing", f"{what} could not be started: {result.error}")
    if result.timed_out:
        return ("compile_timeout", f"{what} did not finish within {timeout:g} s")
    text = decode(result.stdout + result.stderr)
    if compiler_crashed(text) or (result.returncode is not None and result.returncode < 0):
        return ("compiler_crash", f"{what} crashed: {shorten(text, ctx.settings.log_limit)}")
    return None


def crash_description(code: int) -> str:
    if code is None:
        return "did not report an exit code"
    if os.name != "nt" and code < 0:
        return f"was terminated by signal {-code}"
    if os.name == "nt" and code >= 0xC0000000:
        return f"was terminated with status 0x{code:08X}"
    return ""


def first_difference(actual: str, expected: str) -> str:
    a, b = actual.split("\n"), expected.split("\n")
    for index, (left, right) in enumerate(zip(a, b), start=1):
        if left != right:
            return f"line {index}: got {left!r}, expected {right!r}"
    return f"got {len(a)} line(s), expected {len(b)}"


def execute_binary(kind: str, ctx: Context, exe: Path, cwd: Path, stdin: bytes | None):
    """The only place where an example is started."""
    if kind not in EXECUTED_KINDS or kind in UNSAFE_KINDS:
        raise GuardViolation(f"refusing to start a program of kind '{kind}'")
    return run_process([str(exe)], cwd=cwd, env=example_env(), timeout=ctx.settings.run_timeout,
                       stdin=stdin, limit=ctx.settings.output_limit)


def check_started(ctx: Context, vid: str, rel: str, mode: str, result, expected_exit: int,
                  expected_stdout) -> Verdict:
    """Judge one started run. EXPECTED_STDOUT is None for test programs."""
    s = ctx.settings
    if expected_stdout is None:
        expected = "exit 0 and empty stderr"
    else:
        expected = f"exit {expected_exit}, empty stderr, stdout equal to its output block"
    if not result.started:
        return verdict(vid, rel, mode, expected, Status.ENV_ERROR, "start_failed",
                       f"the built program could not be started: {result.error}")
    problems = []
    if result.overflow:
        problems.append(("output_limit", f"{result.overflow} exceeded the {s.output_limit}-byte limit, "
                                         "so the program was stopped"))
    elif result.timed_out:
        problems.append(("timeout", f"did not finish within {s.run_timeout:g} s"))
    else:
        crash = crash_description(result.returncode)
        if crash:
            problems.append(("crashed", f"the program {crash}"))
        elif result.returncode != expected_exit:
            category = "test_failed" if expected_stdout is None else "exit_code"
            problems.append((category, f"exit code {result.returncode}, expected {expected_exit}"))
        err = decode(result.stderr)
        if err:
            problems.append(("stderr", f"printed to stderr: {shorten(err, s.log_limit)!r}"))
        out = decode(result.stdout)
        if expected_stdout is not None and out != expected_stdout:
            problems.append(("output_mismatch", f"stdout differs: {first_difference(out, expected_stdout)}"))
    detail = shorten(decode(result.stdout), s.log_limit)
    if not problems:
        return verdict(vid, rel, mode, expected, Status.PASS, actual="as expected",
                       detail=detail if expected_stdout is None else "", duration=result.duration_ms)
    return verdict(vid, rel, mode, expected, Status.FAIL, problems[0][0],
                   "; ".join(message for _, message in problems), detail, result.duration_ms)


def _build_markdown(ctx: Context, lesson, program, ex: Path):
    """Compile and link a Markdown program with the strict flags. Returns (verdict, exe)."""
    exe = ex / ("program" + EXE)
    result = _compile_and_link(ctx, program, ex / "src", exe)
    vid = f"{lesson.rel}#{program.name}/build"
    expected = "compiles and links with -Wall -Wextra -Wpedantic -Werror"
    problem = tool_problem(result, "the compiler", ctx.settings.compile_timeout, ctx)
    if problem:
        return verdict(vid, lesson.rel, program.kind, expected, Status.ENV_ERROR, *problem,
                       duration=result.duration_ms), None
    if result.returncode != 0 or not exe.is_file():
        text = decode(result.stdout + result.stderr)
        return verdict(vid, lesson.rel, program.kind, expected, Status.FAIL, "build_failed",
                       "the program does not build", shorten(text, ctx.settings.log_limit),
                       result.duration_ms), None
    return verdict(vid, lesson.rel, program.kind, expected, Status.PASS, actual="built",
                   duration=result.duration_ms), exe


def _compile_and_link(ctx: Context, program, src: Path, exe: Path, replace: dict | None = None):
    sources = write_program(program, src, replace)
    argv = ctx.toolchain.cxx + STD + STRICT + DIAGNOSTIC_FORMAT + sources + ["-o", str(exe)]
    return run_process(argv, cwd=src, env=None, timeout=ctx.settings.compile_timeout, limit=TOOL_OUTPUT_LIMIT)


def check_run(ctx: Context, lesson, program) -> list:
    if program.kind != "run":
        raise GuardViolation(f"check_run called for kind '{program.kind}'")
    ex = example_dir(ctx, lesson.rel, program.name)
    build, exe = _build_markdown(ctx, lesson, program, ex)
    found = [build]
    if exe is None:
        return found
    expected_exit = int(program.marker.attrs.get("exit", "0"))
    before = fingerprint(_originals(program))
    for run in program.runs:
        cwd = fresh_run_folder(ex, f"run{run.index}", program.data_root)
        result = execute_binary("run", ctx, exe, cwd, run_input(run))
        found.append(check_started(ctx, f"{lesson.rel}#{program.name}/run{run.index}", lesson.rel,
                                   "run", result, expected_exit, run.expected))
    found.extend(check_originals(lesson.rel, f"{lesson.rel}#{program.name}", "run", before, program))
    return found


def check_test(ctx: Context, lesson, program) -> list:
    if program.kind != "test":
        raise GuardViolation(f"check_test called for kind '{program.kind}'")
    ex = example_dir(ctx, lesson.rel, program.name)
    build, exe = _build_markdown(ctx, lesson, program, ex)
    found = [build]
    correct = None
    before = fingerprint(_originals(program))
    if exe is not None:
        cwd = fresh_run_folder(ex, "test", program.data_root)
        result = execute_binary("test", ctx, exe, cwd, None)
        correct = check_started(ctx, f"{lesson.rel}#{program.name}/test", lesson.rel, "test", result, 0, None)
        found.append(correct)
    if program.against_path is not None:
        found.append(check_against(ctx, lesson, program, ex, correct))
    found.extend(check_originals(lesson.rel, f"{lesson.rel}#{program.name}", "test", before, program))
    return found


# A check program reports failed checks with lines starting with "FAIL " and exit code 1.
_FAIL_LINE = re.compile(r"^FAIL(?: |$)", re.MULTILINE)
REJECTION_EXIT = 1


def check_against(ctx: Context, lesson, program, ex: Path, correct) -> Verdict:
    """Does the check program reject the faulty implementation named by against=?"""
    s = ctx.settings
    rel = lesson.rel
    vid = f"{rel}#{program.name}/against"
    expected = (f"with {program.marker.attrs['against']} in place of {program.against_target}: builds, runs and "
                f"is rejected (exit code {REJECTION_EXIT}, a 'FAIL ' line on stdout, empty stderr)")
    if correct is None or correct.status is not Status.PASS:
        return verdict(vid, rel, "test", expected, Status.FAIL, "correct_failed",
                       "the check program does not build or pass with the correct implementation, "
                       "so its rejection of the faulty one cannot be judged")
    folder = ex / "against"
    exe = folder / ("program" + EXE)
    faulty = program.against_path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    result = _compile_and_link(ctx, program, folder / "src", exe, {program.against_target: faulty})
    problem = tool_problem(result, "the compiler", s.compile_timeout, ctx)
    if problem:
        return verdict(vid, rel, "test", expected, Status.ENV_ERROR, *problem, duration=result.duration_ms)
    if result.returncode != 0 or not exe.is_file():
        return verdict(vid, rel, "test", expected, Status.FAIL, "faulty_build_failed",
                       "the faulty implementation does not build, so the check program never ran against it "
                       "(a build failure is not a detected fault)",
                       shorten(decode(result.stdout + result.stderr), s.log_limit), result.duration_ms)
    cwd = fresh_run_folder(folder, "test", program.data_root)
    run = execute_binary("test", ctx, exe, cwd, None)
    if not run.started:
        return verdict(vid, rel, "test", expected, Status.ENV_ERROR, "start_failed",
                       f"the check program could not be started: {run.error}")
    out, err = decode(run.stdout), decode(run.stderr)
    detail = shorten(out + (f"\n[stderr]\n{err}" if err else ""), s.log_limit)
    if run.overflow:
        category, actual = "faulty_output_limit", f"{run.overflow} exceeded the {s.output_limit}-byte limit"
    elif run.timed_out:
        category, actual = "faulty_timeout", f"did not finish within {s.run_timeout:g} s (a hang is not a detected fault)"
    elif crash_description(run.returncode):
        category, actual = "faulty_crashed", f"the check program {crash_description(run.returncode)} (a crash is not a detected fault)"
    elif run.returncode == 0:
        category, actual = "faulty_not_detected", "the check program passes on the faulty implementation too"
    elif run.returncode == REJECTION_EXIT and not err and _FAIL_LINE.search(out):
        lines = len(_FAIL_LINE.findall(out))
        return verdict(vid, rel, "test", expected, Status.PASS,
                       actual=f"rejected with exit code {REJECTION_EXIT} and {lines} FAIL line(s)",
                       detail=detail, duration=run.duration_ms)
    else:
        category = "faulty_unrecognized"
        actual = (f"exit code {run.returncode}, {'a' if _FAIL_LINE.search(out) else 'no'} FAIL line, "
                  f"{'non-empty' if err else 'empty'} stderr: not the agreed report of failed checks")
    return verdict(vid, rel, "test", expected, Status.FAIL, category, actual, detail, run.duration_ms)


def check_compile(ctx: Context, lesson, program) -> list:
    if program.kind != "compile":
        raise GuardViolation(f"check_compile called for kind '{program.kind}'")
    ex = example_dir(ctx, lesson.rel, program.name)
    build, _ = _build_markdown(ctx, lesson, program, ex)
    return [build]


def _syntax_only(ctx: Context, program, ex: Path, flags: list):
    sources = write_program(program, ex / "src")
    argv = ctx.toolchain.cxx + STD + flags + DIAGNOSTIC_FORMAT + ["-fsyntax-only"] + sources
    if "-fsyntax-only" not in argv or "-o" in argv or "-c" in argv:
        raise GuardViolation("a syntax-only check must not produce output files")
    result = run_process(argv, cwd=ex / "src", env=None, timeout=ctx.settings.compile_timeout,
                         limit=TOOL_OUTPUT_LIMIT)
    return result, sources


def check_compile_fail(ctx: Context, lesson, program) -> list:
    if program.kind != "compile_fail":
        raise GuardViolation(f"check_compile_fail called for kind '{program.kind}'")
    s = ctx.settings
    at, regex = program.marker.attrs["at"], program.marker.attrs["error"]
    line_s, _, col_s = at.partition(":")
    want_line, want_col = int(line_s), int(col_s) if col_s else None
    vid = f"{lesson.rel}#{program.name}"
    expected = f"compile error at main.cpp:{at} whose message matches /{regex}/"
    ex = example_dir(ctx, lesson.rel, program.name)
    # Never -Werror here: a warning must not be able to pass as the expected error.
    result, _ = _syntax_only(ctx, program, ex, WARNINGS + ctx.extra_fail_flags)
    problem = tool_problem(result, "the compiler", s.compile_timeout, ctx)
    if problem:
        return [verdict(vid, lesson.rel, "compile_fail", expected, Status.ENV_ERROR, *problem,
                        duration=result.duration_ms)]
    text = decode(result.stdout + result.stderr)
    detail = shorten(text, s.log_limit)
    errors = [d for d in parse(text) if d.is_error]
    if result.returncode == 0:
        return [verdict(vid, lesson.rel, "compile_fail", expected, Status.FAIL, "unexpected_success",
                        "the program compiled without errors", detail, result.duration_ms)]
    if not errors:
        return [verdict(vid, lesson.rel, "compile_fail", expected, Status.ENV_ERROR, "compiler_failed",
                        "the compiler failed without reporting an error in the program", detail,
                        result.duration_ms)]
    real = [d for d in errors if not d.promoted]
    if not real:
        return [verdict(vid, lesson.rel, "compile_fail", expected, Status.FAIL, "werror_only",
                        "the only errors are warnings turned into errors (-Werror)", detail, result.duration_ms)]
    first = real[0]
    where = f"{first.file}:{first.line}:{first.col}"
    if first.file != "main.cpp" or first.line != want_line or (want_col is not None and first.col != want_col):
        return [verdict(vid, lesson.rel, "compile_fail", expected, Status.FAIL, "wrong_location",
                        f"first error at {where}: {first.message}", detail, result.duration_ms)]
    if not re.search(regex, first.message):
        return [verdict(vid, lesson.rel, "compile_fail", expected, Status.FAIL, "wrong_message",
                        f"first error at {where} does not match: {first.message}", detail, result.duration_ms)]
    return [verdict(vid, lesson.rel, "compile_fail", expected, Status.PASS,
                    actual=f"error at {where}", detail=first.message, duration=result.duration_ms)]


def _files_under(path: Path) -> set:
    return {p.relative_to(path).as_posix() for p in path.rglob("*") if p.is_file()}


def check_compile_unsafe(ctx: Context, lesson, program) -> list:
    if program.kind != "compile_unsafe":
        raise GuardViolation(f"check_compile_unsafe called for kind '{program.kind}'")
    s = ctx.settings
    allowed = set()
    for item in filter(None, program.marker.attrs.get("allow", "").split(",")):
        flag, _, line = item.partition("@")
        allowed.add(("main.cpp", int(line), flag))
    shown = ", ".join(f"{f}@{line}" for _, line, f in sorted(allowed, key=lambda x: (x[1], x[2]))) or "none"
    vid = f"{lesson.rel}#{program.name}"
    expected = f"syntax check only, never linked or run; allowed warnings: {shown}"
    ex = example_dir(ctx, lesson.rel, program.name)
    result, sources = _syntax_only(ctx, program, ex, WARNINGS)
    leftovers = _files_under(ex) - {f"src/{p}" for p in sources} - {f"src/{p}" for p, _ in program.files}
    if leftovers:
        return [verdict(vid, lesson.rel, "compile_unsafe", expected, Status.INTERNAL_ERROR, "artifact_created",
                        f"the syntax check left files behind: {', '.join(sorted(leftovers))}")]
    problem = tool_problem(result, "the compiler", s.compile_timeout, ctx)
    if problem:
        return [verdict(vid, lesson.rel, "compile_unsafe", expected, Status.ENV_ERROR, *problem,
                        duration=result.duration_ms)]
    text = decode(result.stdout + result.stderr)
    detail = shorten(text, s.log_limit)
    diags = parse(text)
    if result.returncode != 0 or any(d.is_error for d in diags):
        return [verdict(vid, lesson.rel, "compile_unsafe", expected, Status.FAIL, "build_failed",
                        "the example does not compile", detail, result.duration_ms)]
    seen = {(d.file, d.line, d.flag) for d in diags if d.severity == "warning"}
    unexpected, missing = seen - allowed, allowed - seen
    if unexpected:
        listed = ", ".join(f"{f or '(no option)'}@{file}:{line}" for file, line, f in sorted(unexpected, key=str))
        return [verdict(vid, lesson.rel, "compile_unsafe", expected, Status.FAIL, "unexpected_warning",
                        f"warnings that are not allowed: {listed}", detail, result.duration_ms)]
    if missing:
        listed = ", ".join(f"{f}@{line}" for _, line, f in sorted(missing, key=str))
        return [verdict(vid, lesson.rel, "compile_unsafe", expected, Status.FAIL, "missing_warning",
                        f"allowed warnings that did not appear: {listed}", detail, result.duration_ms)]
    return [verdict(vid, lesson.rel, "compile_unsafe", expected, Status.PASS,
                    actual="compiles with exactly the allowed warnings; not run, so this says nothing "
                           "about whether the program is safe",
                    detail=detail, duration=result.duration_ms)]


CHECKS = {
    "run": check_run,
    "test": check_test,
    "compile": check_compile,
    "compile_fail": check_compile_fail,
    "compile_unsafe": check_compile_unsafe,
}


def check_program(ctx: Context, lesson, program) -> list:
    return CHECKS[program.kind](ctx, lesson, program)


_CONFIGURE_ENV = ("No CMAKE_CXX_COMPILER could be found", "is not able to compile a simple test program",
                  "CMAKE_MAKE_PROGRAM is not set", "could not find any instance of Visual Studio")
_COMPILER_ID = re.compile(r"The CXX compiler identification is (\S+) (\d+)\.(\d+)\.(\d+)")


def _find_executable(build: Path, target: str):
    candidates = [p for p in build.rglob(target + EXE)
                  if p.is_file() and "CMakeFiles" not in p.relative_to(build).parts]
    return candidates[0] if len(candidates) == 1 else None


def check_project(ctx: Context, lesson, ref) -> list:
    s = ctx.settings
    mode = f"project_{ref.mode}"
    base = f"{lesson.rel}#{ref.name}"
    ex = example_dir(ctx, lesson.rel, ref.name)
    try:
        tools = ctx.build_tools()
    except EnvProblem as exc:
        return [verdict(f"{base}/configure", lesson.rel, mode, "configures with CMake and Ninja",
                        Status.ENV_ERROR, exc.category, exc.message)]
    src, build = ex / "src", ex / "build"
    shutil.copytree(ref.root, src, ignore=shutil.ignore_patterns("build", "build-*", "cmake-build-*", ".git"))
    # Stable field: no tool versions here, they differ between systems.
    expected = "configures with CMake and Ninja using the checked clang++"
    argv = [tools.cmake, "-S", str(src), "-B", str(build), "-G", "Ninja",
            f"-DCMAKE_MAKE_PROGRAM={tools.ninja}", "-DCMAKE_BUILD_TYPE=Debug",
            f"-DCMAKE_CXX_COMPILER={ctx.toolchain.cxx[0]}",
            "-DCMAKE_CXX_FLAGS=" + " ".join(STRICT + DIAGNOSTIC_FORMAT)]
    result = run_process(argv, cwd=ex, env=None, timeout=s.configure_timeout, limit=TOOL_OUTPUT_LIMIT)
    text = decode(result.stdout + result.stderr)
    vid = f"{base}/configure"
    if not result.started:
        return [verdict(vid, lesson.rel, mode, expected, Status.ENV_ERROR, "cmake_missing", result.error)]
    if result.timed_out:
        return [verdict(vid, lesson.rel, mode, expected, Status.ENV_ERROR, "configure_timeout",
                        f"configuration did not finish within {s.configure_timeout:g} s")]
    if result.returncode != 0:
        status = Status.ENV_ERROR if any(m in text for m in _CONFIGURE_ENV) else Status.FAIL
        return [verdict(vid, lesson.rel, mode, expected, status, "configure_failed",
                        "CMake configuration failed", shorten(text, s.log_limit), result.duration_ms)]
    ident = _COMPILER_ID.search(text)
    if not ident or ident.group(1) != "Clang" or int(ident.group(2)) < s.min_clang:
        return [verdict(vid, lesson.rel, mode, expected, Status.ENV_ERROR, "wrong_compiler",
                        f"CMake did not select Clang {s.min_clang} or newer", shorten(text, s.log_limit))]
    found = [verdict(vid, lesson.rel, mode, expected, Status.PASS,
                     actual=f"configured with CMake {tools.cmake_version} and Clang {ident.group(2)}",
                     duration=result.duration_ms)]
    argv = [tools.cmake, "--build", str(build)]
    if ref.mode in ("run", "test"):
        argv += ["--target", ref.target]
    result = run_process(argv, cwd=ex, env=None, timeout=s.compile_timeout, limit=TOOL_OUTPUT_LIMIT)
    vid = f"{base}/build"
    expected = "builds with -Wall -Wextra -Wpedantic -Werror" + (f" (target {ref.target})" if ref.target else "")
    problem = tool_problem(result, "the build", s.compile_timeout, ctx)
    if problem:
        found.append(verdict(vid, lesson.rel, mode, expected, Status.ENV_ERROR, *problem, duration=result.duration_ms))
        return found
    if result.returncode != 0:
        found.append(verdict(vid, lesson.rel, mode, expected, Status.FAIL, "build_failed", "the project does not build",
                             shorten(decode(result.stdout + result.stderr), s.log_limit), result.duration_ms))
        return found
    found.append(verdict(vid, lesson.rel, mode, expected, Status.PASS, actual="built", duration=result.duration_ms))
    if ref.mode == "compile":
        return found
    exe = _find_executable(build, ref.target)
    if exe is None:
        found.append(verdict(f"{base}/{ref.mode}", lesson.rel, mode, f"one executable '{ref.target}'",
                             Status.FAIL, "missing_executable", f"no single executable '{ref.target}{EXE}' in the build folder"))
        return found
    # The program runs in its own folder holding a copy of data=, never in the build or source folder.
    before = fingerprint(_originals(ref))
    if ref.mode == "test":
        cwd = fresh_run_folder(ex, "test", ref.data_root)
        result = execute_binary("test", ctx, exe, cwd, None)
        found.append(check_started(ctx, f"{base}/test", lesson.rel, mode, result, 0, None))
    else:
        for run in ref.runs:
            cwd = fresh_run_folder(ex, f"run{run.index}", ref.data_root)
            result = execute_binary("run", ctx, exe, cwd, run_input(run))
            found.append(check_started(ctx, f"{base}/run{run.index}", lesson.rel, mode, result, ref.exit,
                                       run.expected))
    found.extend(check_originals(lesson.rel, base, mode, before, ref))
    return found
