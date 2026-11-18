"""Directory projects: C++ and CMake files kept in the repository.

A project folder holds a `CMakeLists.txt` and a `checker-project.json`
manifest that declares its id, the modes a lesson may use and its targets:

    {"id": "inventory", "modes": ["compile", "run", "test"],
     "targets": ["inventory_app", "inventory_checks"]}

A lesson that asks for a mode or target the manifest does not declare is
refused before anything is built. Projects are controlled material of this
repository; the checks below catch mistakes, they are not a sandbox for
untrusted projects.
"""

from __future__ import annotations

import json
import re

from .markdown import read_text
from .model import PROJECT_MODES, ProtocolIssue
from .paths import resolve_inside, resolve_repo_path, tree_links

MANIFEST = "checker-project.json"
_ID = re.compile(r"[a-z0-9_]+\Z")
_TARGET = re.compile(r"[A-Za-z0-9_]+\Z")
# Commands that download, run external programs or pull in the CTest module.
_FORBIDDEN = re.compile(
    r"\b(FetchContent\w*|ExternalProject\w*|execute_process|add_custom_command|add_custom_target"
    r"|file\s*\(\s*DOWNLOAD|include\s*\(\s*CTest\s*\))",
    re.IGNORECASE,
)


def _manifest(root, rel_dir) -> dict:
    path = root / MANIFEST
    if not path.is_file():
        raise ProtocolIssue("missing_file", f"project '{rel_dir}' has no {MANIFEST}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProtocolIssue("bad_manifest", f"{rel_dir}/{MANIFEST} is not valid JSON: {exc}") from None
    if not isinstance(data, dict) or set(data) != {"id", "modes", "targets"}:
        raise ProtocolIssue("bad_manifest", f"{rel_dir}/{MANIFEST} must have exactly the keys id, modes, targets")
    if not isinstance(data["id"], str) or not _ID.match(data["id"]):
        raise ProtocolIssue("bad_manifest", f"{rel_dir}/{MANIFEST}: id must use lowercase letters, digits and '_'")
    modes, targets = data["modes"], data["targets"]
    if (not isinstance(modes, list) or not modes or len(set(modes)) != len(modes)
            or any(m not in PROJECT_MODES for m in modes)):
        raise ProtocolIssue("bad_manifest", f"{rel_dir}/{MANIFEST}: modes must be a non-empty list from {', '.join(PROJECT_MODES)}")
    if (not isinstance(targets, list) or len(set(targets)) != len(targets)
            or any(not isinstance(t, str) or not _TARGET.match(t) for t in targets)):
        raise ProtocolIssue("bad_manifest", f"{rel_dir}/{MANIFEST}: targets must be a list of distinct CMake target names")
    return data


def validate_project(ref, repo_root, allowed_roots) -> None:
    root = resolve_repo_path(repo_root, ref.dir, allowed_roots, "project", "dir")
    links = tree_links(root)
    if links:
        raise ProtocolIssue("symlink", f"project '{ref.dir}' contains symbolic links: {', '.join(links[:3])}")
    data = _manifest(root, ref.dir)
    if not (root / "CMakeLists.txt").is_file():
        raise ProtocolIssue("missing_file", f"project '{ref.dir}' has no CMakeLists.txt")
    for cmake_file in sorted(list(root.rglob("CMakeLists.txt")) + list(root.rglob("*.cmake"))):
        found = _FORBIDDEN.search(cmake_file.read_text(encoding="utf-8", errors="replace"))
        if found:
            raise ProtocolIssue("forbidden_cmake",
                                f"{cmake_file.relative_to(root).as_posix()} in '{ref.dir}' uses '{found.group(1)}', "
                                "which is not allowed in course projects")
    if ref.mode not in data["modes"]:
        raise ProtocolIssue("mode_not_allowed",
                            f"project '{data['id']}' allows modes {', '.join(data['modes'])}; the lesson asks for '{ref.mode}'")
    if ref.target and ref.target not in data["targets"]:
        raise ProtocolIssue("unknown_target", f"project '{data['id']}' has no target '{ref.target}'")
    for path, block in ref.files:
        shown = resolve_inside(root, path, "file", "file")
        content, _ = read_text(shown)
        if content != block.content:
            raise ProtocolIssue("source_mismatch", f"the block differs from {ref.dir}/{path}")
    ref.manifest = data
    ref.root = root
