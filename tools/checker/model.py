"""Data model shared by the checker modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"                      # the checked content is wrong
    PROTOCOL_ERROR = "protocol_error"  # markers, paths, PL/EN pairing
    ENV_ERROR = "env_error"            # tools missing, wrong version, tool crashed
    INTERNAL_ERROR = "internal_error"  # a bug or a broken guarantee in the checker


EXIT_CODE = {
    Status.PASS: 0,
    Status.FAIL: 1,
    Status.PROTOCOL_ERROR: 2,
    Status.ENV_ERROR: 3,
    Status.INTERNAL_ERROR: 4,
}

# Kinds of code blocks that form a program of their own.
PROGRAM_KINDS = ("run", "compile", "test", "compile_fail", "compile_unsafe")
# The only kinds whose programs are ever started. Everything else is at most compiled.
EXECUTED_KINDS = ("run", "test")
UNSAFE_KINDS = ("compile_unsafe",)
BLOCK_KINDS = PROGRAM_KINDS + ("file", "input", "output", "fragment")
KNOWN_KINDS = BLOCK_KINDS + ("project",)
# Named in the course contract, not implemented in this prototype.
RESERVED_KINDS = ("diagnostic", "concurrent", "benchmark")
PROJECT_MODES = ("compile", "run", "test")

# Fields that must be identical in the reports of every platform.
STABLE_FIELDS = ("id", "source", "mode", "expected", "status", "category")


class ProtocolIssue(Exception):
    """A problem in the lesson markup, a path or the PL/EN pairing."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message


class GuardViolation(Exception):
    """A checker safety guarantee would be broken; always an internal error."""


@dataclass
class Verdict:
    id: str
    source: str
    mode: str
    expected: str
    status: Status
    category: str = ""
    actual: str = ""
    detail: str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "mode": self.mode,
            "expected": self.expected,
            "status": self.status.value,
            "category": self.category,
            "actual": self.actual,
            "detail": self.detail,
            "duration_ms": self.duration_ms,
        }

    def stable(self) -> dict:
        data = self.to_dict()
        return {key: data[key] for key in STABLE_FIELDS}


@dataclass
class Marker:
    kind: str
    name: str
    attrs: dict
    line: int
    text: str        # the marker line, compared byte for byte between PL and EN
    path: str = ""   # PATH of a `file` marker


@dataclass
class Block:
    lang: str
    content: str     # line ends normalised to "\n"
    line: int        # line of the opening fence


@dataclass
class MarkedBlock:
    marker: Marker
    block: Block | None  # None for `project`, which has no code block


@dataclass
class Run:
    index: int
    stdin: str | None          # from an `input` block, normalised text
    expected: str
    line: int
    stdin_file: str = ""       # `in=` on the `output` marker (repository path)
    stdin_path: Path | None = None


@dataclass
class Program:
    name: str
    kind: str
    marker: Marker
    main: Block
    files: list = field(default_factory=list)   # [(path, Block)]
    runs: list = field(default_factory=list)    # [Run]
    data_root: Path | None = None               # `data=` folder, copied into each run folder
    against_path: Path | None = None            # `against=` faulty file
    against_target: str = ""                    # the program file that the faulty file replaces


@dataclass
class ProjectRef:
    name: str
    marker: Marker
    dir: str
    mode: str
    target: str
    exit: int
    runs: list = field(default_factory=list)    # [Run]
    files: list = field(default_factory=list)   # [(path, Block)] shown in the lesson
    manifest: dict = field(default_factory=dict)
    root: Path | None = None
    data_root: Path | None = None


@dataclass
class Lesson:
    path: Path
    rel: str
    marked: list = field(default_factory=list)   # [MarkedBlock] in document order
    owners: list = field(default_factory=list)   # [Program | ProjectRef] in document order
    fragments: int = 0
    issues: list = field(default_factory=list)   # [Verdict] with PROTOCOL_ERROR
    crlf: bool = False
