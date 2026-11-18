"""Reading Clang diagnostics.

The checker passes `-fno-color-diagnostics -fno-caret-diagnostics
-fdiagnostics-show-option -fmessage-length=0` and relative file names, so
each diagnostic is one line: `FILE:LINE:COL: SEVERITY: MESSAGE [OPTIONS]`.
Only the location, the severity and the option tag are relied on; message
text is matched with short, author-chosen regular expressions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_LINE = re.compile(
    r"(?P<file>.+?):(?P<line>\d+):(?P<col>\d+): "
    r"(?P<sev>fatal error|error|warning|note|remark): (?P<msg>.*)\Z"
)
_TAG = re.compile(r"(?P<msg>.*?) \[(?P<tag>-W[^\]]*)\]\Z")

# Text that only appears when the compiler itself failed.
_CRASH = (
    "PLEASE submit a bug report",
    "clang frontend command failed",
    "Stack dump:",
    "LLVM ERROR:",
    "unable to execute command",
)


@dataclass
class Diagnostic:
    file: str
    line: int
    col: int
    severity: str
    message: str
    options: tuple

    @property
    def is_error(self) -> bool:
        return self.severity in ("error", "fatal error")

    @property
    def promoted(self) -> bool:
        """A warning turned into an error by -Werror or `#pragma ... error`."""
        return any(o == "-Werror" or o.startswith("-Werror=") for o in self.options)

    @property
    def flag(self) -> str:
        """The warning option, e.g. -Wreturn-stack-address ("" when none)."""
        flags = [o for o in self.options if o != "-Werror" and not o.startswith("-Werror=")]
        return flags[-1] if flags else ""


def parse(text: str) -> list:
    found = []
    for raw in text.splitlines():
        m = _LINE.match(raw.strip())
        if not m:
            continue
        message, options = m.group("msg"), ()
        tagged = _TAG.match(message)
        if tagged:
            message = tagged.group("msg")
            options = tuple(tagged.group("tag").split(","))
        name = m.group("file").replace("\\", "/")
        if name.startswith("./"):
            name = name[2:]
        found.append(Diagnostic(name, int(m.group("line")), int(m.group("col")),
                                m.group("sev"), message, options))
    return found


def compiler_crashed(text: str) -> bool:
    return any(marker in text for marker in _CRASH)
