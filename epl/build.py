"""Orchestrator: fetch -> parse -> normalise -> validate -> parquet + manifest.

Run it with:

    PYTHONPATH=src:. .venv/bin/python -m epl.build                 # E0
    PYTHONPATH=src:. .venv/bin/python -m epl.build --division E1   # Championship

Idempotent. The raw CSVs are cached, so a second run re-parses the same bytes
and produces the same artifacts. Nothing is re-downloaded unless `--refresh` is
passed explicitly.

Outputs, all under `data/epl/` (gitignored). E0 keeps every file name it had:
    matches.parquet          tidy match table, the one file downstream reads
    manifest.json            per-season counts, date ranges, odds coverage, hashes
    team_name_mapping.json   raw spelling -> canonical -> key, with occurrences
    raw/provenance.json      URL, fetch timestamp, SHA-256, byte count per file

and E1 writes the same five artifacts under its own names (`matches_e1.parquet`
and so on), resolved through `epl.paths`' per-division accessors.

EVERY OUTPUT PATH IS RESOLVED THROUGH AN ACCESSOR, NEVER THROUGH A MODULE
CONSTANT. `paths.MATCHES_PARQUET` is bound to the real `data/epl/` at import, so
a test that points `paths.DATA_DIR` at a temporary directory does NOT move it: a
`build()` that wrote through the constant would overwrite the pinned E0 archive
from inside a test. `paths.matches_parquet(division)` reads `DATA_DIR` at call
time and cannot. `epl/tests/test_e1ingest.py` asserts exactly this.

TWO REFUSAL DISCIPLINES, AND THE DIFFERENCE IS DELIBERATE.

*   **E0 reports.** A failed check or an unregistered club is recorded in the
    manifest, the row is retained and the parquet is written; `main` exits 1.
    The daily live cycle depends on this: it meets a newly promoted club's
    spelling before anybody has registered it, and must still produce a table.
*   **A division whose archive this build INTRODUCES refuses.** Any blocking
    issue raises `AcquisitionIncomplete` before a single byte is written. A
    partial second-tier archive is worse than none, because the experiment that
    revives it pins it *as-found* and cannot tell that it is short.

The one issue that does not block is the vendor's own formatting — the line of
bare commas every football-data file ends with. The gate recognises it by
DERIVING the string from `parse.blank_rows_issue`, the same function the parser
reports it with, so a reworded message cannot silently start blocking every
season or silently stop blocking anything else.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone

import pandas as pd

from epl import fetch, parse, paths, schema, teams, validate


class AcquisitionIncomplete(RuntimeError):
    """A division's archive could not be built completely, so it was not built.

    Raised only for a division whose archive this build introduces — never for
    E0, whose orchestrator reports and continues. It carries every blocking
    issue, because the operator's next act is to fix them and re-run, and a
    message naming one of five failures would cost four more round trips.
    """


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
    division: str = schema.DEFAULT_DIVISION,
) -> dict:
    """Build one division's match table and its manifest. Returns the manifest.

    `division` defaults to E0, so a caller that names none gets exactly the
    behaviour it got before divisions existed: the same source URL, the same
    cache files, the same provenance keys, the same output file names, the same
    `match_id` recipe, the same checks and the same report-rather-than-refuse
    handling of a bad season.
    """
    shape = schema.division_shape(division)
    strict = division != schema.DEFAULT_DIVISION
    paths.ensure_dirs()

    fetch_records = fetch.fetch_all(season_codes, refresh=refresh, division=division)

    frames: list[pd.DataFrame] = []
    season_entries: list[dict] = []
    issues: list[str] = []
    #: The subset of `issues` that must stop a strict build. Everything except
    #: the vendor's blank trailing rows.
    blocking: list[str] = []
    raw_counts_by_season: dict[str, dict[str, int]] = {}

    for code in season_codes:
        parsed = parse.parse_season(code, division)
        raw_counts_by_season[parsed.season] = parsed.raw_team_counts
        frames.append(parsed.frame)

        report = validate.validate_season(parsed.frame, code, parsed.season, division)

        # Derived from the parser's own function, never matched as prose: the
        # exact issue text this season's blank-row count would have produced.
        benign = (
            {parse.blank_rows_issue(parsed.dropped_blank_rows)}
            if parsed.dropped_blank_rows else set()
        )
        for issue in parsed.issues:
            issues.append(f"{parsed.season}: {issue}")
            if issue not in benign:
                blocking.append(f"{parsed.season}: {issue}")
        for failure in report.failures:
            text = f"{parsed.season}: CHECK FAILED [{failure.name}] {failure.detail}"
            issues.append(text)
            blocking.append(text)

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
        text = f"GLOBAL: {dup_ids} duplicate match_id(s) — ids are not unique"
        issues.append(text)
        blocking.append(text)

    # THE GATE, AND IT IS BEFORE THE FIRST WRITE. Nothing above this line has
    # touched an output file, so a refusal leaves any previously built archive
    # exactly as it was rather than truncating it into a shorter one.
    if strict and blocking:
        raise AcquisitionIncomplete(
            f"{division} ({shape.label}): {len(blocking)} blocking issue(s); "
            f"refusing to write a partial archive. A partial second-tier "
            f"archive is worse than none, because whatever pins it next pins "
            f"it as-found and cannot tell that it is short. Issues: {blocking}"
        )

    matches_path = paths.matches_parquet(division)
    matches.to_parquet(matches_path, index=False)
    if write_csv:
        matches.to_csv(paths.matches_csv(division), index=False)

    mapping = _team_mapping_report(raw_counts_by_season)
    with open(paths.team_mapping_path(division), "w") as fh:
        json.dump(mapping, fh, indent=2, sort_keys=True)
        fh.write("\n")

    total_usable = int(
        matches[["odds_h", "odds_d", "odds_a"]].notna().all(axis=1).sum()
    )
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "name": "football-data.co.uk",
            "url_pattern": fetch.url_pattern(division),
            "division": f"{division} ({shape.label})",
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
                "path": paths.rel(matches_path),
                "rows": len(matches),
                "bytes": matches_path.stat().st_size,
                "sha256": _sha256_file(matches_path),
                "columns": list(matches.columns),
            },
            "team_name_mapping": paths.rel(paths.team_mapping_path(division)),
            "provenance": paths.rel(paths.provenance_path(division)),
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
    with open(paths.manifest_path(division), "w") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")

    return manifest


def _print_summary(manifest: dict) -> None:
    t = manifest["totals"]
    print(f"{manifest['source']['division']} — {manifest['output']['matches']['path']}")
    print(f"{'season':9} {'matches':>7} {'teams':>5} {'played':>6} "
          f"{'odds':>5} {'cov':>6} {'ovr':>6}  {'dates':<23} checks")
    print("-" * 92)
    for entry in manifest["seasons"]:
        odds = entry["odds"]
        ovr = odds["overround_mean"]
        # A season with no usable odds has no mean overround, and `format(None,
        # '>6')` raises. Every E0 season carries prices, so this never fired on
        # the Premier League archive — but a division whose odds coverage is not
        # guaranteed would have crashed the summary AFTER writing the parquet,
        # reporting a failed build that had in fact succeeded.
        ovr_text = "-" if ovr is None else f"{ovr:.4f}"
        status = "PASS" if entry["validation"]["passed"] else "FAIL: " + ", ".join(
            c["name"] for c in entry["validation"]["checks"] if not c["passed"]
        )
        print(
            f"{entry['season']:9} {entry['matches']:>7} {entry['teams']:>5} "
            f"{entry['played']:>6} {odds['usable_rows']:>5} "
            f"{odds['coverage']:>6.3f} {ovr_text:>6}  "
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
    ap.add_argument("--csv", action="store_true", help="also write the CSV mirror")
    ap.add_argument(
        "--division",
        default=schema.DEFAULT_DIVISION,
        choices=sorted(schema.DIVISIONS),
        help="which division to build (default: %(default)s). `choices` comes "
             "from the registered season shapes, so a division this ingest "
             "could not validate is rejected at the command line rather than "
             "part-way through a build.",
    )
    ap.add_argument(
        "--seasons",
        nargs="+",
        metavar="CODE",
        default=list(fetch.SEASON_CODES),
        help="season codes to build (default: all twelve, %(default)s)",
    )
    args = ap.parse_args(argv)

    try:
        manifest = build(
            tuple(args.seasons),
            refresh=args.refresh,
            write_csv=args.csv,
            division=args.division,
        )
    except (AcquisitionIncomplete, parse.PhantomClub) as exc:
        # An operator-facing refusal, not a crash: the archive was not written,
        # and the message is the whole fix list.
        print(f"REFUSED — no archive was written.\n\n{exc}")
        return 1

    _print_summary(manifest)
    return 1 if manifest["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
