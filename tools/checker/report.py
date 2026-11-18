"""Reports: JSON for machines and comparison, text for people."""

from __future__ import annotations

import json

from .model import EXIT_CODE, STABLE_FIELDS, Status

FORMAT = "amc-checker-report/1"


def exit_code(verdicts) -> int:
    return max((EXIT_CODE[v.status] for v in verdicts), default=0)


def make_report(result) -> dict:
    return {
        "format": FORMAT,
        "stable_fields": list(STABLE_FIELDS),
        "environment": result.environment,
        "summary": result.summary,
        "exit_code": exit_code(result.verdicts),
        "verdicts": [v.to_dict() for v in result.verdicts],
    }


def write_report(path, report: dict) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, ensure_ascii=True)
        handle.write("\n")


def load_report(path) -> dict:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError(f"{path} is not a {FORMAT} report")
    return data


def stable_part(report: dict) -> list:
    return [{key: v[key] for key in STABLE_FIELDS} for v in report["verdicts"]]


def compare(named_reports) -> list:
    """Differences between the stable parts of reports; [] when they agree."""
    (base_name, base), *others = named_reports
    base_rows = stable_part(base)
    differences = []
    for name, report in others:
        rows = stable_part(report)
        base_ids = [r["id"] for r in base_rows]
        ids = [r["id"] for r in rows]
        for missing in sorted(set(base_ids) - set(ids)):
            differences.append(f"{name}: no verdict {missing} (present in {base_name})")
        for extra in sorted(set(ids) - set(base_ids)):
            differences.append(f"{name}: extra verdict {extra} (absent from {base_name})")
        if not differences and ids != base_ids:
            differences.append(f"{name}: the verdicts are in a different order than in {base_name}")
        by_id = {r["id"]: r for r in rows}
        for row in base_rows:
            other = by_id.get(row["id"])
            if other is None:
                continue
            for key in STABLE_FIELDS:
                if other[key] != row[key]:
                    differences.append(f"{name}: {row['id']}: {key} is {other[key]!r}, "
                                       f"{base_name} has {row[key]!r}")
    return differences


_LABEL = {
    Status.PASS: "PASS",
    Status.FAIL: "FAIL",
    Status.PROTOCOL_ERROR: "PROTOCOL",
    Status.ENV_ERROR: "ENV",
    Status.INTERNAL_ERROR: "INTERNAL",
}


def print_text(result, stream, verbose: bool = False) -> None:
    for v in result.verdicts:
        if v.status is Status.PASS and not verbose:
            continue
        line = f"{_LABEL[v.status]:<9} {v.mode:<15} {v.id}"
        if v.category:
            line += f"  [{v.category}]"
        print(line, file=stream)
        if v.status is not Status.PASS:
            print(f"          expected: {v.expected}", file=stream)
            print(f"          actual:   {v.actual}", file=stream)
            if v.detail:
                for detail_line in v.detail.splitlines()[:12]:
                    print(f"          | {detail_line}", file=stream)
    counts = result.summary.get("by_status", {})
    print(
        f"{result.summary.get('lessons', 0)} lesson file(s), "
        f"{result.summary.get('lesson_pairs_checked', 0)} PL/EN pair(s) checked, "
        f"{result.summary.get('programs', 0)} program(s), {result.summary.get('fragments', 0)} fragment(s); "
        + ", ".join(f"{key}: {value}" for key, value in counts.items()),
        file=stream,
    )
    print(f"exit code {exit_code(result.verdicts)}", file=stream)
