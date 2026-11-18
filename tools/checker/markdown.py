"""Reading lesson Markdown: markers, code blocks and the rules between them.

A marker is an HTML comment on a line of its own, not indented, directly
above its code block (only blank lines in between):

    <!-- KIND: NAME attributes -->

The grammar of each kind is documented in tools/checker/README.md.
Anything that looks like a marker but does not follow the grammar is a
protocol error; ordinary HTML comments such as `<!-- TODO: ... -->` stay
text unless a code block follows them directly.
"""

from __future__ import annotations

import re
from pathlib import Path

from .model import (
    KNOWN_KINDS, PROGRAM_KINDS, PROJECT_MODES, RESERVED_KINDS,
    Block, Lesson, MarkedBlock, Marker, Program, ProjectRef, ProtocolIssue, Run, Status, Verdict,
)
from .datafiles import validate_data_dir, validate_input_file
from .paths import check_relative, resolve_repo_path

_CANONICAL = re.compile(r"<!-- ([a-z_]+): (.+?) -->\Z")
_FRAGMENT = "<!-- fragment -->"
_LOOKALIKE = re.compile(
    r"\s*<!--\s*(?:" + "|".join(KNOWN_KINDS + RESERVED_KINDS) + r")s?\s*(?::|-->)", re.IGNORECASE
)
_GENERIC = re.compile(r"<!-- ([A-Za-z_][A-Za-z0-9_-]*): .* -->\Z")
_NAME = re.compile(r"[a-z0-9_]+\Z")
_FLAT_FILE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\.(?:cpp|hpp)\Z")
_ALLOW = re.compile(r"(-W[a-z0-9][a-z0-9+-]*)@([1-9][0-9]*)\Z")
_AT = re.compile(r"([1-9][0-9]*)(?::([1-9][0-9]*))?\Z")
_TARGET = re.compile(r"[A-Za-z0-9_]+\Z")
_EXIT = re.compile(r"(?:0|[1-9][0-9]{0,2})\Z")

CODE_LANGS = ("cpp", "c++", "cxx")
_LANG = {
    "run": "cpp", "compile": "cpp", "test": "cpp", "compile_fail": "cpp",
    "compile_unsafe": "cpp", "file": "cpp", "fragment": "cpp",
    "input": "text", "output": "text",
}
# Optional attributes of each kind, in their only allowed order.
_OPTIONAL = {
    "run": ("exit", "source", "data"),
    "compile": ("source",),
    "test": ("source", "data", "against"),
    "compile_unsafe": ("allow",),
    "file": ("source",),
    "input": (),
    "output": ("in",),
    "project": ("target", "exit", "data"),
}


def protocol(rel: str, line: int, category: str, message: str) -> Verdict:
    return Verdict(
        id=f"{rel}:{line}:{category}", source=rel, mode="protocol",
        expected="valid lesson markup", status=Status.PROTOCOL_ERROR,
        category=category, actual=message,
    )


def read_text(path: Path):
    data = path.read_bytes()
    crlf = b"\r\n" in data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProtocolIssue("encoding", f"not valid UTF-8 ({exc.reason} at byte {exc.start})") from None
    # Technical normalisation only: Windows line ends become "\n". A lone "\r" stays.
    return text.replace("\r\n", "\n"), crlf


def parse_marker(kind: str, rest: str, line: int, text: str) -> Marker:
    if kind == "compile_fail":
        m = re.match(r"([a-z0-9_]+) at=(\S+) error=(.+)\Z", rest)
        if not m:
            raise ProtocolIssue("bad_attribute", "compile_fail needs 'NAME at=LINE[:COL] error=REGEX', in this order")
        name, at, regex = m.groups()
        if not _AT.match(at):
            raise ProtocolIssue("bad_attribute", f"at={at} must be LINE or LINE:COLUMN")
        try:
            re.compile(regex)
        except re.error as exc:
            raise ProtocolIssue("bad_attribute", f"error= is not a valid regular expression: {exc}") from None
        return Marker(kind, name, {"at": at, "error": regex}, line, text)

    tokens = rest.split(" ")
    if "" in tokens:
        raise ProtocolIssue("bad_attribute", "parts of a marker are separated by single spaces")
    name = tokens.pop(0)
    if not _NAME.match(name):
        raise ProtocolIssue("bad_name", f"name '{name}' may use only lowercase letters, digits and '_'")
    attrs: dict = {}
    path = ""
    if kind == "file":
        if not tokens or "=" in tokens[0]:
            raise ProtocolIssue("bad_attribute", "a file marker needs a PATH after the name")
        path = tokens.pop(0)
    if kind == "project":
        for key in ("dir", "mode"):
            if not tokens or not tokens[0].startswith(key + "="):
                raise ProtocolIssue("bad_attribute", f"project needs '{key}=' (order: dir, mode, target, exit)")
            attrs[key] = tokens.pop(0)[len(key) + 1:]
        if attrs["mode"] not in PROJECT_MODES:
            raise ProtocolIssue("unknown_mode", f"project mode '{attrs['mode']}' is not one of {', '.join(PROJECT_MODES)}")
    order = _OPTIONAL[kind]
    position = 0
    for token in tokens:
        key, sep, value = token.partition("=")
        if not sep or not value:
            raise ProtocolIssue("bad_attribute", f"'{token}' is not KEY=VALUE")
        if key not in order:
            raise ProtocolIssue("bad_attribute", f"unknown attribute '{key}' for {kind}")
        index = order.index(key)
        if index < position:
            raise ProtocolIssue("bad_attribute", f"attribute '{key}' is out of order (order: {', '.join(order)})")
        position = index + 1
        attrs[key] = value
    if "exit" in attrs and not (_EXIT.match(attrs["exit"]) and int(attrs["exit"]) <= 255):
        raise ProtocolIssue("bad_attribute", f"exit={attrs['exit']} must be a number from 0 to 255")
    if "target" in attrs and not _TARGET.match(attrs["target"]):
        raise ProtocolIssue("bad_attribute", f"target={attrs['target']} is not a CMake target name")
    if "allow" in attrs:
        items = attrs["allow"].split(",")
        if any(not _ALLOW.match(item) for item in items) or len(set(items)) != len(items):
            raise ProtocolIssue("bad_attribute", "allow= is a list of -Wflag@LINE items, without repeats")
    return Marker(kind, name, attrs, line, text, path)


def scan(text: str, rel: str):
    """Split a lesson into marked blocks; returns (marked, fragments, issues)."""
    lines = text.split("\n")
    marked: list = []
    issues: list = []
    fragments = 0
    pending: Marker | None = None
    unknown: tuple | None = None   # (line, kind) of a comment shaped like a marker of an unknown kind

    def lost_marker() -> None:
        nonlocal pending
        if pending is not None:
            issues.append(protocol(rel, pending.line, "marker_without_block",
                                   f"{pending.kind} marker is not directly followed by its code block"))
            pending = None

    i = 0
    while i < len(lines):
        line = lines[i]
        number = i + 1
        if line.startswith("```"):
            info = line[3:].strip()
            j = i + 1
            while j < len(lines) and lines[j].rstrip() != "```":
                j += 1
            if j >= len(lines):
                issues.append(protocol(rel, number, "unclosed_block", "code block is not closed"))
                pending = None
                break
            body = lines[i + 1:j]
            block = Block(info, "\n".join(body) + "\n" if body else "", number)
            if pending is not None:
                expected = _LANG[pending.kind]
                if info != expected:
                    issues.append(protocol(rel, pending.line, "wrong_block_language",
                                           f"{pending.kind} needs a ```{expected} block, found ```{info or '(none)'}"))
                else:
                    marked.append(MarkedBlock(pending, block))
                    if pending.kind == "fragment":
                        fragments += 1
                pending = None
            elif info in CODE_LANGS:
                if unknown is not None:
                    issues.append(protocol(rel, unknown[0], "unknown_kind", f"unknown marker kind '{unknown[1]}'"))
                else:
                    issues.append(protocol(rel, number, "unmarked_block", "C++ code block without a marker"))
            unknown = None
            i = j + 1
            continue

        if not line.strip():
            i += 1
            continue

        stripped = line.lstrip()
        if stripped != line and stripped.startswith("```") and stripped[3:].strip() in CODE_LANGS:
            lost_marker()
            issues.append(protocol(rel, number, "indented_block",
                                   "indented C++ code block is never checked; start its fence at the beginning of the line"))
            i += 1
            continue

        m = _CANONICAL.match(line)
        if line == _FRAGMENT or (m and m.group(1) in KNOWN_KINDS + RESERVED_KINDS):
            lost_marker()
            unknown = None
            if line == _FRAGMENT:
                pending = Marker("fragment", "", {}, number, line)
            elif m.group(1) in RESERVED_KINDS:
                issues.append(protocol(rel, number, "reserved_kind",
                                       f"'{m.group(1)}' is reserved for a later phase and is not implemented"))
            else:
                try:
                    marker = parse_marker(m.group(1), m.group(2), number, line)
                except ProtocolIssue as exc:
                    issues.append(protocol(rel, number, exc.category, exc.message))
                else:
                    if marker.kind == "project":
                        marked.append(MarkedBlock(marker, None))
                    else:
                        pending = marker
            i += 1
            continue

        if _LOOKALIKE.match(line):
            lost_marker()
            issues.append(protocol(rel, number, "malformed_marker",
                                   "line looks like a marker but does not follow the marker syntax"))
            i += 1
            continue

        generic = _GENERIC.match(line)
        lost_marker()
        unknown = (number, generic.group(1)) if generic else None
        i += 1
    lost_marker()
    return marked, fragments, issues


def assemble(lesson: Lesson, repo_root: Path, allowed_roots) -> None:
    """Group marked blocks into programs and projects and check the rules between them."""
    rel = lesson.rel
    owners: dict = {}

    def issue(marker: Marker, category: str, message: str) -> None:
        lesson.issues.append(protocol(rel, marker.line, category, message))

    for item in lesson.marked:
        mk = item.marker
        if mk.kind not in PROGRAM_KINDS and mk.kind != "project":
            continue
        if mk.name in owners:
            issue(mk, "duplicate_name", f"name '{mk.name}' is used by more than one program in this lesson")
            continue
        if mk.kind == "project":
            owner = ProjectRef(mk.name, mk, mk.attrs["dir"], mk.attrs["mode"],
                               mk.attrs.get("target", ""), int(mk.attrs.get("exit", "0")))
        else:
            owner = Program(mk.name, mk.kind, mk, item.block)
        owners[mk.name] = owner
        lesson.owners.append(owner)

    waiting_input: dict = {}
    for item in lesson.marked:
        mk = item.marker
        if mk.kind == "file":
            owner = owners.get(mk.name)
            if owner is None:
                issue(mk, "orphan_block", f"file block for '{mk.name}', which is not a program in this lesson")
            elif isinstance(owner, Program):
                if not _FLAT_FILE.match(mk.path) or mk.path == "main.cpp":
                    issue(mk, "bad_path", f"file '{mk.path}' of a Markdown program must be a flat .cpp or .hpp name other than main.cpp")
                elif any(path == mk.path for path, _ in owner.files):
                    issue(mk, "duplicate_file", f"program '{mk.name}' already has a file '{mk.path}'")
                else:
                    owner.files.append((mk.path, item.block))
            else:
                if "source" in mk.attrs:
                    issue(mk, "bad_attribute", "a file of a project is compared with the project folder; source= is not used")
                    continue
                try:
                    check_relative(mk.path, "file")
                except ProtocolIssue as exc:
                    issue(mk, exc.category, exc.message)
                else:
                    owner.files.append((mk.path, item.block))
        elif mk.kind in ("input", "output"):
            owner = owners.get(mk.name)
            if owner is None:
                issue(mk, "orphan_block", f"{mk.kind} block for '{mk.name}', which is not a program in this lesson")
                continue
            kind = owner.kind if isinstance(owner, Program) else f"project mode={owner.mode}"
            if not ((isinstance(owner, Program) and owner.kind == "run")
                    or (isinstance(owner, ProjectRef) and owner.mode == "run")):
                issue(mk, "mode_conflict", f"{mk.kind} block for '{mk.name}' ({kind}): only run programs are ever started")
                continue
            if mk.kind == "input":
                if mk.name in waiting_input:
                    issue(mk, "missing_output", f"two input blocks for '{mk.name}' without an output block between them")
                waiting_input[mk.name] = item
            else:
                given = waiting_input.pop(mk.name, None)
                run = Run(len(owner.runs) + 1, given.block.content if given else None, item.block.content, mk.line)
                stdin_file = mk.attrs.get("in", "")
                if stdin_file:
                    if given is not None:
                        issue(mk, "input_conflict", f"run {run.index} of '{mk.name}' has an input block and in=; "
                                                    "standard input comes from exactly one of them")
                        continue
                    try:
                        run.stdin_path = validate_input_file(repo_root, stdin_file, allowed_roots)
                    except ProtocolIssue as exc:
                        issue(mk, exc.category, exc.message)
                        continue
                    run.stdin_file = stdin_file
                owner.runs.append(run)
    for item in waiting_input.values():
        issue(item.marker, "missing_output", f"input block for '{item.marker.name}' is not followed by an output block")

    for owner in lesson.owners:
        mk = owner.marker
        data = mk.attrs.get("data")
        if data:
            try:
                owner.data_root = validate_data_dir(repo_root, data, allowed_roots)
            except ProtocolIssue as exc:
                issue(mk, exc.category, exc.message)
        if isinstance(owner, Program) and "against" in mk.attrs:
            _check_against(owner, repo_root, allowed_roots, issue)
        if isinstance(owner, Program):
            if owner.kind == "run" and not owner.runs:
                issue(mk, "missing_output", f"run program '{owner.name}' needs at least one output block")
        else:
            if owner.mode == "run" and not owner.runs:
                issue(mk, "missing_output", f"project '{owner.name}' in mode=run needs at least one output block")
            if owner.mode in ("run", "test") and not owner.target:
                issue(mk, "missing_target", f"project '{owner.name}' in mode={owner.mode} needs target=")
            if owner.mode != "run" and "exit" in mk.attrs:
                issue(mk, "bad_attribute", "exit= is only used with mode=run")
            if owner.mode == "compile" and data:
                issue(mk, "bad_attribute", "data= is only used with mode=run or mode=test")

    for item in lesson.marked:
        if item.block is not None and not item.block.content.isascii():
            issue(item.marker, "non_ascii", "marked blocks must be ASCII (code, input and output are identical in PL and EN)")
        source = item.marker.attrs.get("source")
        if source and item.block is not None:
            try:
                path = resolve_repo_path(repo_root, source, allowed_roots, "source", "file")
                expected, _ = read_text(path)
            except ProtocolIssue as exc:
                issue(item.marker, exc.category, exc.message)
                continue
            if expected != item.block.content:
                issue(item.marker, "source_mismatch", f"the block differs from {source}")


def _check_against(program: Program, repo_root: Path, allowed_roots, issue) -> None:
    """`against=PATH`: a faulty version of one of the program's files, with the same file name."""
    mk = program.marker
    rel = mk.attrs["against"]
    target = rel.rsplit("/", 1)[-1]
    files = {path: block for path, block in program.files}
    if target not in files:
        issue(mk, "against_target_missing",
              f"against={rel} must replace a file of '{program.name}' with the same name; "
              f"its files are: {', '.join(sorted(files)) or 'none besides main.cpp'}")
        return
    try:
        path = resolve_repo_path(repo_root, rel, allowed_roots, "against", "file")
        content, _ = read_text(path)
    except ProtocolIssue as exc:
        issue(mk, exc.category, exc.message)
        return
    if not content.isascii():
        issue(mk, "non_ascii", f"{rel} must be ASCII, like every program file")
        return
    if content == files[target].content:
        issue(mk, "against_identical", f"{rel} is identical to the correct {target}, so it proves nothing")
        return
    program.against_path = path
    program.against_target = target


def load_lesson(path: Path, repo_root: Path, allowed_roots) -> Lesson:
    rel = path.relative_to(repo_root).as_posix()
    lesson = Lesson(path=path, rel=rel)
    try:
        text, lesson.crlf = read_text(path)
    except ProtocolIssue as exc:
        lesson.issues.append(protocol(rel, 1, exc.category, exc.message))
        return lesson
    lesson.marked, lesson.fragments, lesson.issues = scan(text, rel)
    assemble(lesson, repo_root, allowed_roots)
    return lesson
