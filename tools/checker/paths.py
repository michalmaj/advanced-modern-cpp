"""Validation of the repository-relative paths written in markers.

Paths in markers are always relative to the repository root, use '/', and
never contain '..'. They must stay inside one of the allowed folders, and no
part of them may be a symbolic link. This keeps examples inside the
repository's own, reviewed material; it is not a security boundary.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .model import ProtocolIssue

DEFAULT_ALLOWED_ROOTS = ("course", "projects", "exercises", "support", "tests/checker/fixtures")

_SEGMENT = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\Z")
_DRIVE = re.compile(r"[A-Za-z]:")


def is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)  # Python 3.12+
    return bool(isjunction and isjunction(path))


def check_relative(rel: str, what: str) -> list:
    """Syntax check of a relative path; returns its segments."""
    if not rel:
        raise ProtocolIssue("bad_path", f"empty {what} path")
    if "\\" in rel:
        raise ProtocolIssue("bad_path", f"{what} path '{rel}' uses '\\'; use '/'")
    if rel.startswith("/") or _DRIVE.match(rel):
        raise ProtocolIssue("bad_path", f"{what} path '{rel}' is absolute")
    parts = rel.split("/")
    if ".." in parts:
        raise ProtocolIssue("path_escape", f"{what} path '{rel}' contains '..'")
    for part in parts:
        if not _SEGMENT.match(part):
            raise ProtocolIssue("bad_path", f"{what} path '{rel}' has an invalid part '{part}'")
    return parts


def resolve_inside(base: Path, rel: str, what: str, want: str) -> Path:
    """Resolve REL under BASE, refusing links, missing parts and escapes."""
    parts = check_relative(rel, what)
    current = base
    for part in parts:
        current = current / part
        if is_link(current):
            raise ProtocolIssue("symlink", f"{what} path '{rel}' goes through a symbolic link")
        if not current.exists():
            raise ProtocolIssue("missing_file", f"{what} '{rel}' does not exist")
    try:
        current.resolve().relative_to(base.resolve())
    except ValueError:
        raise ProtocolIssue("path_escape", f"{what} path '{rel}' leaves the repository") from None
    if want == "file" and not current.is_file():
        raise ProtocolIssue("missing_file", f"{what} '{rel}' is not a file")
    if want == "dir" and not current.is_dir():
        raise ProtocolIssue("missing_file", f"{what} '{rel}' is not a folder")
    return current


def resolve_repo_path(repo_root: Path, rel: str, allowed_roots, what: str, want: str) -> Path:
    check_relative(rel, what)
    if not any(rel == root or rel.startswith(root + "/") for root in allowed_roots):
        raise ProtocolIssue(
            "path_not_allowed",
            f"{what} path '{rel}' is outside the allowed folders ({', '.join(allowed_roots)})",
        )
    return resolve_inside(repo_root, rel, what, want)


def tree_links(root: Path) -> list:
    """All symbolic links (and Windows junctions) inside ROOT, without following them."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            if is_link(path):
                found.append(path.relative_to(root).as_posix())
    return sorted(found)
