"""Orchestrator: fetch -> parse -> normalise -> validate -> parquet + manifest.

Run it with:

    PYTHONPATH=src:. .venv/bin/python -m epl.build

Idempotent. The raw CSVs are cached, so a second run re-parses the same bytes
and produces the same artifacts. Nothing is re-downloaded unless `--refresh` is
passed explicitly.

Outputs, all under `data/epl/` (gitignored):
    matches.parquet          tidy match table, the one file downstream reads
    manifest.json            per-season counts, date ranges, odds coverage, hashes
    team_name_mapping.json   raw spelling -> canonical -> key, with occurrences
    raw/provenance.json      URL, fetch timestamp, SHA-256, byte count per file
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone

import pandas as pd

from epl import fetch, parse, paths, schema, teams, validate


def _sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _odds_summary(frame: pd.DataFrame) -> dict:
    """Per-season odds coverage. Measured, never assumed.

    The research flagged Pinnacle closing prices missing for a large block of
    2025/26; this is where that gets counted rather than taken on faith. Mean
    overround is reported alongside because coverage without a plausible
    overround (~1.02-1.06 for Pinnacle) would mean the prices are not what the
    column names claim.
    """
    n = len(frame)
    closing = frame[["psch", "pscd", "psca"]].notna().all(axis=1)
    opening = frame[["psh", "psd", "psa"]].notna().all(axis=1)
    usable = frame[["odds_h", "odds_d", "odds_a"]].notna().all(axis=1)
    overround = frame.loc[usable, "odds_overround"]

    # Where the gap sits matters more than how big it is. If the missing rows
    # form a contiguous tail, the odds-covered subset is the FIRST part of the
    # season, not a random sample of it — so a market comparison over that
    # subset is a comparison over a biased slice and must be reported that way.
    gap: dict | None = None
    if (~usable).any():
        missing_dates = frame.loc[~usable, "date"]
        present_dates = frame.loc[usable, "date"]
        gap = {
            "missing_from": missing_dates.min().strftime("%Y-%m-%d"),
            "missing_to": missing_dates.max().strftime("%Y-%m-%d"),
            "contiguous_tail": bool(
                present_dates.empty or missing_dates.min() > present_dates.max()
            ),
            "home_win_rate_with_odds": (
                round(float((frame.loc[usable, "ftr"] == "H").mean()), 4)
                if usable.any() else None
            ),
            "home_win_rate_without_odds": round(
                float((frame.loc[~usable, "ftr"] == "H").mean()), 4
            ),
            "warning": (
                "Odds-covered rows are NOT a random sample of this season. Any "
                "market comparison restricted to them is a comparison over a "
                "biased slice — report the subset explicitly."
            ),
        }

    return {
        "gap": gap,
        "rows": n,
        "closing_rows": int(closing.sum()),
        "opening_rows": int(opening.sum()),
        "usable_rows": int(usable.sum()),
        "missing_rows": int(n - usable.sum()),
        "coverage": round(float(usable.sum()) / n, 4) if n else 0.0,
        "source_counts": {
            str(k): int(v) for k, v in frame["odds_source"].value_counts().items()
        },
        "overround_mean": round(float(overround.mean()), 5) if len(overround) else None,
        "overround_min": round(float(overround.min()), 5) if len(overround) else None,
        "overround_max": round(float(overround.max()), 5) if len(overround) else None,
    }


def _team_mapping_report(
    raw_counts_by_season: dict[str, dict[str, int]]
) -> dict:
    """raw spelling -> canonical -> key, with the seasons it appears in.

    `aliased` flags spellings that differ from their canonical name — the ones
    that would have fractured into separate clubs under a naive slugger.
    `declared_unobserved` lists registry entries no file actually used, so the
    defensive aliases stay visibly distinct from the load-bearing ones.
    """
    observed: dict[str, dict] = {}
    for season, counts in raw_counts_by_season.items():
        for spelling, count in counts.items():
            entry = observed.setdefault(
                spelling, {"appearances": 0, "seasons": [], "canonical": None, "key": None}
            )
            entry["appearances"] += count
            entry["seasons"].append(season)
            try:
                canonical, key = teams.resolve(spelling)
                entry["canonical"], entry["key"] = canonical, key
            except teams.UnknownTeamError:
                entry["canonical"], entry["key"] = None, None

    for spelling, entry in observed.items():
        entry["seasons"] = sorted(set(entry["seasons"]))
        entry["n_seasons"] = len(entry["seasons"])
        entry["aliased"] = entry["canonical"] is not None and entry["canonical"] != spelling

    known = teams.known_spellings()
    unobserved = sorted(set(known) - set(observed))
    unresolved = sorted(s for s, e in observed.items() if e["canonical"] is None)

    by_key: dict[str, list[str]] = {}
    for spelling, entry in observed.items():
        if entry["key"]:
            by_key.setdefault(entry["key"], []).append(spelling)

    return {
        "n_registry_clubs": teams.registry_size(),
        "n_observed_spellings": len(observed),
        "n_resolved": len(observed) - len(unresolved),
        "n_aliased": sum(1 for e in observed.values() if e["aliased"]),
        "unresolved_spellings": unresolved,
        "spellings": dict(sorted(observed.items())),
        "spellings_per_club_key": {
            k: sorted(v) for k, v in sorted(by_key.items()) if len(v) > 1
        },
        "declared_unobserved_aliases": unobserved,
    }


def build(
    season_codes: tuple[str, ...] = fetch.SEASON_CODES,
    *,
    refresh: bool = False,
    write_csv: bool = False,
) -> dict:
    """Build the full EPL match table and its manifest. Returns the manifest."""
    paths.ensure_dirs()

    fetch_records = fetch.fetch_all(season_codes, refresh=refresh)

    frames: list[pd.DataFrame] = []
    season_entries: list[dict] = []
    issues: list[str] = []
    raw_counts_by_season: dict[str, dict[str, int]] = {}

    for code in season_codes:
        parsed = parse.parse_season(code)
        raw_counts_by_season[parsed.season] = parsed.raw_team_counts
        frames.append(parsed.frame)

        report = validate.validate_season(parsed.frame, code, parsed.season)
        for issue in parsed.issues:
            issues.append(f"{parsed.season}: {issue}")
        for failure in report.failures:
            issues.append(f"{parsed.season}: CHECK FAILED [{failure.name}] {failure.detail}")

        frame = parsed.frame
        club_keys = pd.unique(pd.concat([frame["home_key"], frame["away_key"]]).dropna())
        season_entries.append(
            {
                "season": parsed.season,
                "season_code": code,
                "matches": len(frame),
                "played": int(frame["played"].sum()),
                "teams": int(len(club_keys)),
                "date_min": frame["date"].min().strftime("%Y-%m-%d"),
                "date_max": frame["date"].max().strftime("%Y-%m-%d"),
                "kickoff_time_rows": int(frame["time"].notna().sum()),
                "odds": _odds_summary(frame),
                "raw": fetch_records[code].to_json(),
                "validation": report.to_json(),
            }
        )

    matches = schema.sort_for_walk_forward(pd.concat(frames, ignore_index=True))

    # A match_id collision would silently merge two fixtures downstream.
    dup_ids = matches["match_id"].duplicated().sum()
    if dup_ids:
        issues.append(f"GLOBAL: {dup_ids} duplicate match_id(s) — ids are not unique")

    matches.to_parquet(paths.MATCHES_PARQUET, index=False)
    if write_csv:
        matches.to_csv(paths.MATCHES_CSV, index=False)

    mapping = _team_mapping_report(raw_counts_by_season)
    with open(paths.TEAM_MAPPING_PATH, "w") as fh:
        json.dump(mapping, fh, indent=2, sort_keys=True)
        fh.write("\n")

    total_usable = int(
        matches[["odds_h", "odds_d", "odds_a"]].notna().all(axis=1).sum()
    )
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "name": "football-data.co.uk",
            "url_pattern": fetch.BASE_URL,
            "division": "E0 (Premier League)",
            "licence_note": "Free to use for research; credit football-data.co.uk.",
        },
        "odds_policy": (
            "BENCHMARK ONLY. Odds are used solely as an internal accuracy "
            "benchmark, never displayed publicly and never turned into a "
            "betting signal."
        ),
        "point_in_time_rule": schema.ORDERING_RULE,
        "output": {
            "matches": {
                "path": paths.rel(paths.MATCHES_PARQUET),
                "rows": len(matches),
                "bytes": paths.MATCHES_PARQUET.stat().st_size,
                "sha256": _sha256_file(paths.MATCHES_PARQUET),
                "columns": list(matches.columns),
            },
            "team_name_mapping": paths.rel(paths.TEAM_MAPPING_PATH),
            "provenance": paths.rel(paths.PROVENANCE_PATH),
        },
        "totals": {
            "seasons": len(season_entries),
            "matches": len(matches),
            "played": int(matches["played"].sum()),
            "distinct_clubs": int(
                pd.concat([matches["home_key"], matches["away_key"]]).dropna().nunique()
            ),
            "date_min": matches["date"].min().strftime("%Y-%m-%d"),
            "date_max": matches["date"].max().strftime("%Y-%m-%d"),
            "odds_usable_rows": total_usable,
            "odds_coverage": round(total_usable / len(matches), 4) if len(matches) else 0.0,
            "seasons_passing_all_checks": sum(
                1 for e in season_entries if e["validation"]["passed"]
            ),
        },
        "seasons": season_entries,
        "issues": issues,
    }
    with open(paths.MANIFEST_PATH, "w") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")

    return manifest


def _print_summary(manifest: dict) -> None:
    t = manifest["totals"]
    print(f"{'season':9} {'matches':>7} {'teams':>5} {'played':>6} "
          f"{'odds':>5} {'cov':>6} {'ovr':>6}  {'dates':<23} checks")
    print("-" * 92)
    for entry in manifest["seasons"]:
        odds = entry["odds"]
        ovr = odds["overround_mean"]
        status = "PASS" if entry["validation"]["passed"] else "FAIL: " + ", ".join(
            c["name"] for c in entry["validation"]["checks"] if not c["passed"]
        )
        print(
            f"{entry['season']:9} {entry['matches']:>7} {entry['teams']:>5} "
            f"{entry['played']:>6} {odds['usable_rows']:>5} "
            f"{odds['coverage']:>6.3f} {ovr if ovr is None else f'{ovr:.4f}':>6}  "
            f"{entry['date_min']} .. {entry['date_max']}  {status}"
        )
    print("-" * 92)
    print(
        f"{'TOTAL':9} {t['matches']:>7} {t['distinct_clubs']:>5} {t['played']:>6} "
        f"{t['odds_usable_rows']:>5} {t['odds_coverage']:>6.3f}         "
        f"{t['date_min']} .. {t['date_max']}  "
        f"{t['seasons_passing_all_checks']}/{t['seasons']} seasons pass"
    )
    if manifest["issues"]:
        print(f"\nISSUES ({len(manifest['issues'])}):")
        for issue in manifest["issues"]:
            print(f"  - {issue}")
    else:
        print("\nNo issues.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--refresh",
        action="store_true",
        help="re-download raw CSVs even when cached (default: never re-download)",
    )
    ap.add_argument("--csv", action="store_true", help="also write matches.csv")
    args = ap.parse_args(argv)

    manifest = build(refresh=args.refresh, write_csv=args.csv)
    _print_summary(manifest)
    return 1 if manifest["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
