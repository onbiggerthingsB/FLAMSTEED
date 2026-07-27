"""Roll up the privacy-minimal publisher meter into monthly MD and CSV.

Usage:
  PYTHONPATH=src .venv/bin/python scripts/publisher_usage_report.py \
      --meter data/meter.jsonl --month 2027-01 --out reports/usage/
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
from typing import Any


_MONTH = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
_DAY = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$")
_PATH_CLASSES = ("token", "bundle", "fixture")


def summarize(meter_path: str | Path, month: str) -> dict[str, dict[str, int]]:
    """Aggregate valid records for *month*; malformed lines are counted."""
    if not _MONTH.fullmatch(month):
        raise ValueError("month must be YYYY-MM")
    meter_path = Path(meter_path)
    summary: dict[str, dict[str, int]] = {}
    days: dict[str, set[str]] = {}
    skipped = 0
    try:
        lines = meter_path.read_text().splitlines()
    except FileNotFoundError:
        lines = []
    for line in lines:
        try:
            row: Any = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("record is not an object")
            day, pid, path_class = row["day"], row["pid"], row["path_class"]
            if (
                not isinstance(day, str)
                or not _DAY.fullmatch(day)
                or not isinstance(pid, str)
                or not pid
                or path_class not in _PATH_CLASSES
                or set(row) != {"day", "pid", "path_class"}
            ):
                raise ValueError("record shape is invalid")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            skipped += 1
            continue
        if not day.startswith(month + "-"):
            continue
        bucket = summary.setdefault(
            pid,
            {"token": 0, "bundle": 0, "fixture": 0, "days_active": 0},
        )
        bucket[path_class] += 1
        days.setdefault(pid, set()).add(day)
    for pid, active_days in days.items():
        summary[pid]["days_active"] = len(active_days)
    summary["_meta"] = {"skipped_lines": skipped}
    return summary


def write_report(
    summary: dict[str, dict[str, int]], month: str, out_dir: str | Path
) -> Path:
    """Write matching Markdown and CSV reports; return the Markdown path."""
    if not _MONTH.fullmatch(month):
        raise ValueError("month must be YYYY-MM")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"usage-{month}.md"
    csv_path = out_dir / f"usage-{month}.csv"
    pids = sorted(pid for pid in summary if pid != "_meta")
    skipped = summary.get("_meta", {}).get("skipped_lines", 0)

    markdown = [
        f"# Publisher usage — {month}",
        "",
        "| Publisher | Token | Bundle | Fixture | Days active |",
        "|---|---:|---:|---:|---:|",
    ]
    for pid in pids:
        row = summary[pid]
        markdown.append(
            f"| {pid} | {row['token']} | {row['bundle']} | "
            f"{row['fixture']} | {row['days_active']} |"
        )
    if not pids:
        markdown.append("| _No usage_ | 0 | 0 | 0 | 0 |")
    markdown.extend(["", f"Skipped malformed lines: {skipped}", ""])
    md_path.write_text("\n".join(markdown))

    with csv_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["publisher", "token", "bundle", "fixture", "days_active"])
        for pid in pids:
            row = summary[pid]
            writer.writerow(
                [pid, row["token"], row["bundle"], row["fixture"], row["days_active"]]
            )
    return md_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meter", required=True)
    parser.add_argument("--month", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    summary = summarize(Path(args.meter), args.month)
    report = write_report(summary, args.month, Path(args.out))
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
