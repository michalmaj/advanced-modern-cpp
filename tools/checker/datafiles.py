"""Data files: `in=` files for standard input and `data=` folders for runs.

Both are ordinary files of this repository and follow the path rules of
paths.py. They are used byte for byte: there is no line-end normalisation,
because a data file's line ends can be the point of an exercise. Keep data
folders free of Git line-end conversion with a `.gitattributes` entry
`-text` (as the fixtures do), so every system gets the same bytes.

A `data=` folder is copied into a new, empty folder for every run; the
program never sees the original, and the checker compares fingerprints of
the originals before and after the runs.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from .model import ProtocolIssue
from .paths import resolve_repo_path, tree_links

MAX_DATA_FILES = 100
MAX_DATA_BYTES = 4 * 1024 * 1024
MAX_INPUT_BYTES = 1024 * 1024


def validate_input_file(repo_root: Path, rel: str, allowed_roots) -> Path:
    path = resolve_repo_path(repo_root, rel, allowed_roots, "in", "file")
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ProtocolIssue("data_too_large", f"input file '{rel}' is larger than {MAX_INPUT_BYTES} bytes")
    return path


def validate_data_dir(repo_root: Path, rel: str, allowed_roots) -> Path:
    if rel in allowed_roots:
        raise ProtocolIssue("data_too_broad", f"data folder '{rel}' is a whole allowed folder; name a folder inside it")
    root = resolve_repo_path(repo_root, rel, allowed_roots, "data", "dir")
    links = tree_links(root)
    if links:
        raise ProtocolIssue("symlink", f"data folder '{rel}' contains symbolic links: {', '.join(links[:3])}")
    files = [p for p in root.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    if len(files) > MAX_DATA_FILES or total > MAX_DATA_BYTES:
        raise ProtocolIssue("data_too_large", f"data folder '{rel}' has {len(files)} files and {total} bytes; "
                                              f"the limits are {MAX_DATA_FILES} files and {MAX_DATA_BYTES} bytes")
    return root


def fingerprint(paths) -> dict:
    """SHA-256 of every file under PATHS (files or folders)."""
    found = {}
    for path in paths:
        if path is None:
            continue
        files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
        for item in files:
            found[item.as_posix()] = hashlib.sha256(item.read_bytes()).hexdigest()
    return found


def fresh_run_folder(parent: Path, label: str, data_root: Path | None) -> Path:
    """A new, empty working folder for one run, holding a copy of the data folder."""
    folder = parent / label
    if folder.exists():
        shutil.rmtree(folder)
    if data_root is not None:
        shutil.copytree(data_root, folder, symlinks=False)
    else:
        folder.mkdir(parents=True)
    return folder


def run_input(run) -> bytes | None:
    """The bytes given on standard input: an `in=` file as is, or the `input` block."""
    if run.stdin_path is not None:
        return run.stdin_path.read_bytes()
    if run.stdin is not None:
        return run.stdin.encode("ascii")
    return None
