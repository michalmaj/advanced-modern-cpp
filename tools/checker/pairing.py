"""Polish / English lesson pairs.

Every `X.md` (Polish) has an `X.en.md` (English) and the other way round.
The marked blocks of both files form the same list: the same marker lines,
in the same order, with identical code, input and output after line-end
normalisation. Prose is not compared; that stays a review task.
"""

from __future__ import annotations

from .markdown import protocol

EN_SUFFIX = ".en.md"


def english_name(rel: str) -> str:
    return rel[: -len(".md")] + EN_SUFFIX


def polish_name(rel: str) -> str:
    return rel[: -len(EN_SUFFIX)] + ".md"


def is_english(rel: str) -> bool:
    return rel.endswith(EN_SUFFIX)


def _signature(lesson) -> list:
    return [
        (item.marker.text, item.block.lang if item.block else None, item.block.content if item.block else None)
        for item in lesson.marked
    ]


def check_pairs(lessons: dict) -> tuple:
    """Returns (issues, primaries): primaries are the Polish files of complete, matching pairs."""
    issues = []
    primaries = []
    for rel in sorted(lessons):
        if is_english(rel):
            if polish_name(rel) not in lessons:
                issues.append(protocol(rel, 1, "pairing_missing", f"no Polish lesson {polish_name(rel)} for this English lesson"))
            continue
        en_rel = english_name(rel)
        if en_rel not in lessons:
            issues.append(protocol(rel, 1, "pairing_missing", f"no English lesson {en_rel} for this Polish lesson"))
            continue
        pl, en = lessons[rel], lessons[en_rel]
        a, b = _signature(pl), _signature(en)
        mismatch = None
        for index, (left, right) in enumerate(zip(a, b)):
            if left != right:
                where = "marker" if left[0] != right[0] else "block content"
                mismatch = (index, where)
                break
        if mismatch is None and len(a) != len(b):
            mismatch = (min(len(a), len(b)), "number of marked blocks")
        if mismatch is not None:
            index, where = mismatch
            line = en.marked[index].marker.line if index < len(en.marked) else 1
            issues.append(protocol(en_rel, line, "pairing_mismatch",
                                   f"marked block {index + 1} differs from {rel} ({where}); "
                                   f"{len(a)} marked blocks in PL, {len(b)} in EN"))
            continue
        primaries.append(rel)
    return issues, primaries
