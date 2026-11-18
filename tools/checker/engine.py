"""The checker run: read lessons, check the protocol, then build and run examples."""

from __future__ import annotations

import platform
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .execute import Context, Settings, check_program, check_project
from .markdown import load_lesson, protocol
from .model import GuardViolation, ProtocolIssue, Status, Verdict
from .pairing import check_pairs
from .paths import DEFAULT_ALLOWED_ROOTS
from .projects import validate_project
from .toolchain import EnvProblem, probe_compiler

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class CheckResult:
    verdicts: list = field(default_factory=list)
    environment: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)
    work_root: Path | None = None


def discover(repo_root: Path, paths) -> tuple:
    """Markdown files under PATHS (files or folders inside the repository)."""
    files, issues = [], []
    root = repo_root.resolve()
    for given in paths:
        path = (repo_root / given) if not Path(given).is_absolute() else Path(given)
        try:
            resolved = path.resolve()
            resolved.relative_to(root)
        except (OSError, ValueError):
            issues.append(protocol(str(given), 1, "path_escape", f"'{given}' is outside the repository"))
            continue
        if resolved.is_file() and resolved.suffix == ".md":
            files.append(resolved)
        elif resolved.is_dir():
            files.extend(p for p in resolved.rglob("*.md") if p.is_file())
        else:
            issues.append(protocol(str(given), 1, "missing_file", f"'{given}' is not a Markdown file or a folder"))
    unique = sorted(set(files), key=lambda p: p.relative_to(root).as_posix())
    return unique, issues


def _work_root(repo_root: Path, work_dir) -> Path:
    if work_dir is None:
        return Path(tempfile.mkdtemp(prefix="amc-checker-"))
    path = Path(work_dir).resolve()
    root = repo_root.resolve()
    try:
        inside = path.relative_to(root)
    except ValueError:
        inside = None
    if inside is not None and (not inside.parts or inside.parts[0] != "build"):
        raise ProtocolIssue("bad_work_dir", "the work folder must be outside the repository or under build/")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _remove(path: Path) -> None:
    def retry(func, target, _exc):
        try:
            Path(target).chmod(0o700)
            func(target)
        except OSError:
            pass
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


def run_check(paths, repo_root: Path = REPO_ROOT, *, build: bool = True, cxx: str = "clang++",
              settings: Settings | None = None, allowed_roots=DEFAULT_ALLOWED_ROOTS, work_dir=None,
              keep_work: bool = False, toolchain=None, extra_fail_flags=None) -> CheckResult:
    settings = settings or Settings()
    # The repository root is trusted; resolve it once (e.g. macOS /var -> /private/var).
    # Every path inside it is then checked part by part, without following links.
    repo_root = Path(repo_root).resolve()
    result = CheckResult()
    files, issues = discover(repo_root, paths)
    result.verdicts.extend(issues)

    lessons: dict = {}
    for path in files:
        lesson = load_lesson(path, repo_root, allowed_roots)
        lessons[lesson.rel] = lesson

    project_ids: dict = {}
    for rel in sorted(lessons):
        lesson = lessons[rel]
        if lesson.issues:
            continue
        for owner in lesson.owners:
            if not hasattr(owner, "dir"):
                continue
            try:
                validate_project(owner, repo_root, allowed_roots)
            except ProtocolIssue as exc:
                lesson.issues.append(protocol(rel, owner.marker.line, exc.category, exc.message))
                continue
            known = project_ids.setdefault(owner.manifest["id"], owner.dir)
            if known != owner.dir:
                lesson.issues.append(protocol(rel, owner.marker.line, "duplicate_id",
                                              f"project id '{owner.manifest['id']}' is used by {known} and {owner.dir}"))

    pair_issues, primaries = check_pairs(lessons)
    for rel in sorted(lessons):
        result.verdicts.extend(lessons[rel].issues)
    result.verdicts.extend(pair_issues)

    blocked = {v.source for v in result.verdicts if v.status is Status.PROTOCOL_ERROR}
    runnable = []
    for rel in primaries:
        en = rel[: -len(".md")] + ".en.md"
        if rel not in blocked and en not in blocked:
            runnable.append(lessons[rel])

    result.environment = {
        "platform": sys.platform,
        "machine": platform.machine(),
        "python": platform.python_version(),
        "lesson_line_ends": "crlf" if any(l.crlf for l in lessons.values()) else "lf",
    }
    result.summary = {
        "lessons": len(lessons),
        "lesson_pairs_checked": len(runnable),
        "lessons_blocked_by_protocol_errors": len([r for r in lessons if not r.endswith(".en.md")]) - len(runnable),
        "programs": sum(len(l.owners) for l in runnable),
        "fragments": sum(l.fragments for l in runnable),
        "examples_built": 0,
    }
    if not build or not runnable:
        result.summary.update(_counts(result.verdicts))
        return result

    work = _work_root(repo_root, work_dir)
    result.work_root = work
    try:
        if toolchain is None:
            try:
                toolchain = probe_compiler(cxx, settings.min_clang, work)
            except EnvProblem as exc:
                for lesson in runnable:
                    for owner in lesson.owners:
                        result.verdicts.append(Verdict(
                            id=f"{lesson.rel}#{owner.name}", source=lesson.rel,
                            mode=getattr(owner, "kind", "project"), expected="the toolchain is available",
                            status=Status.ENV_ERROR, category=exc.category, actual=exc.message))
                result.summary.update(_counts(result.verdicts))
                return result
        result.environment.update(toolchain.describe())
        ctx = Context(repo_root, toolchain, work, settings, extra_fail_flags)
        for lesson in runnable:
            for owner in lesson.owners:
                try:
                    if hasattr(owner, "dir"):
                        found = check_project(ctx, lesson, owner)
                    else:
                        found = check_program(ctx, lesson, owner)
                except GuardViolation as exc:
                    found = [Verdict(id=f"{lesson.rel}#{owner.name}", source=lesson.rel, mode="guard",
                                     expected="checker safety guarantees hold", status=Status.INTERNAL_ERROR,
                                     category="guard_violation", actual=str(exc))]
                result.verdicts.extend(found)
                result.summary["examples_built"] += 1
        if ctx._build_tools is not None:
            result.environment.update(ctx._build_tools.describe())
    finally:
        if not keep_work:
            _remove(work)
    result.summary.update(_counts(result.verdicts))
    return result


def _counts(verdicts) -> dict:
    counts = {status.value: 0 for status in Status}
    for v in verdicts:
        counts[v.status.value] += 1
    return {"verdicts": len(verdicts), "by_status": counts}
