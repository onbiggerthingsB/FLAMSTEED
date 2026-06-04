#!/usr/bin/env python
"""Phase-2 sizing diagnostic — how many WC-2026 field teams trip the Elo
`provisional` flag's *volatility arm*.

Run:  ``uv run python scripts/volatility_field_diagnostic.py``

This drives the pure helper ``wcmodel.model.volatility_diagnostic.
count_volatility_arm`` over the REAL martj42 international-results history and
the ACTUAL 48-team WC-2026 field (read from ``config/tournament_2026.yaml``
``groups[*].teams``), then writes ``reports/phase2_volatility_field_sizing.md``.

The count sizes how much effort a later Phase-2 task ("provisional-widening")
must spend: the few-games arm is irrelevant for a WC field (every qualified
nation has played far more than 5 matches), so what matters is the *volatility*
arm specifically.

NO FABRICATION. martj42 is the Phase-1-sanctioned free, public, CC0 GitHub CSV
results source (commit-pinned in ``sources/results``). It is fetched through the
existing content-addressed cache (``data/cache``). If the raw history is neither
cached nor fetchable, this script RAISES with explicit fetch instructions — it
never invents a count.

Analysis-only: ingest goes to a throwaway temp store; nothing the model consumes
is written, and the real bitemporal store is untouched.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import yaml

# Repo root = parent of scripts/. Put ``src`` on the path so the script runs via
# ``uv run python scripts/volatility_field_diagnostic.py`` regardless of whether
# the editable install is active (mirrors pytest ``pythonpath = ["src"]``).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from wcmodel.config import load_config  # noqa: E402
from wcmodel.data.sources.results import (  # noqa: E402
    MARTJ42_COMMIT,
    MARTJ42_RAW_URL,
    fetch_results,
    normalize_results,
)
from wcmodel.data.store import BitemporalStore, Policy  # noqa: E402
from wcmodel.model.volatility_diagnostic import count_volatility_arm  # noqa: E402

CUTOFF = "2026-06-01"  # WC-2026 kicks off 2026-06-11; cut strictly before it.
TOURNAMENT_PATH = ROOT / "config" / "tournament_2026.yaml"
REPORT_PATH = ROOT / "reports" / "phase2_volatility_field_sizing.md"


def _field_teams() -> list[str]:
    """The 48 WC-2026 field teams, read from ``groups[*].teams`` (the draw)."""
    with open(TOURNAMENT_PATH) as f:
        cfg = yaml.safe_load(f)
    teams = [t for g in cfg["groups"] for t in g["teams"]]
    if len(teams) != 48:
        raise ValueError(
            f"expected 48 field teams in {TOURNAMENT_PATH} groups[*].teams, "
            f"got {len(teams)} — the 2026 config is malformed"
        )
    return teams


def _ingest_real_martj42(store: BitemporalStore) -> int:
    """Fetch the REAL martj42 CSV (cache-first) and write it to ``store``.

    FAILS LOUDLY if the raw history is neither cached nor fetchable, rather than
    fabricating a result. Returns the number of ingested rows.
    """
    cache_dir = ROOT / load_config()["paths"]["cache"]
    try:
        raw = fetch_results(cache_dir)
    except Exception as exc:  # noqa: BLE001 — re-raise with actionable guidance
        raise RuntimeError(
            "Could not obtain the real martj42 results history. The diagnostic "
            "refuses to fabricate a count.\n"
            f"  cache dir : {cache_dir}\n"
            f"  source    : {MARTJ42_RAW_URL}\n"
            f"  commit    : {MARTJ42_COMMIT}\n"
            "Fetch it (CC0, no key) with network access, e.g.:\n"
            "  uv run python -c \"from wcmodel.data.sources.results import "
            "fetch_results; fetch_results('data/cache')\"\n"
            "then re-run this script."
        ) from exc

    if raw is None or len(raw) == 0:
        raise RuntimeError(
            f"martj42 fetch returned no rows (cache dir {cache_dir}, commit "
            f"{MARTJ42_COMMIT}). Refusing to fabricate a count — investigate the "
            "source/cache before re-running."
        )

    results = normalize_results(raw)
    store.write(
        "results", results, policy=Policy.POINT_IN_TIME,
        keys=["match_id"], source="martj42", source_version=MARTJ42_COMMIT,
    )
    return len(results)


def _render_report(res: pd.DataFrame, n_rows: int) -> str:
    cfg = load_config()["elo"]
    win = int(cfg["volatility_window"])
    thr = float(cfg["provisional_volatility_threshold"])
    n_few = int(cfg["provisional_games"])

    n_field = len(res)
    n_vol = int(res["volatility_flag"].sum())
    n_few_arm = int(res["few_games_flag"].sum())
    sizing = (
        "**tiny handful, keep (a)/(c) minimal**" if n_vol <= 4
        else "**material — budget real effort for provisional-widening**"
    )

    table = res.sort_values(
        "recent_volatility", ascending=False, na_position="last", kind="mergesort"
    )

    lines: list[str] = []
    lines.append("# Phase-2 volatility-arm field sizing")
    lines.append("")
    lines.append(
        "Generated by `scripts/volatility_field_diagnostic.py` over the REAL "
        f"martj42 history (commit `{MARTJ42_COMMIT}`, {n_rows:,} normalised "
        f"rows) at cutoff `{CUTOFF}` (strictly before the 2026-06-11 kickoff). "
        "Point-in-time: only PLAYED matches dated `< cutoff` enter the Elo, via "
        "the same `compute_elo_history` + `tiers.match_type` K-wiring as "
        "`features.build`."
    )
    lines.append("")
    lines.append(
        "The **volatility arm** flags a team whose population std of its last "
        f"`volatility_window={win}` rating deltas (inclusive of its final "
        f"pre-cutoff result) exceeds `provisional_volatility_threshold={thr}` — "
        "i.e. erratic recent ratings = low-information even with a long history. "
        "It is reported separately from the **few-games arm** (`games < "
        f"provisional_games={n_few}`), which is essentially irrelevant for a WC "
        "field (every qualified nation has played far more than "
        f"{n_few} matches). The two arms are mutually exclusive here: a "
        "few-games team is never volatility-flagged."
    )
    lines.append("")
    lines.append("## Headline counts")
    lines.append("")
    lines.append(f"- Field teams: **{n_field}**")
    lines.append(f"- **Volatility-arm provisional: {n_vol}**")
    lines.append(f"- Few-games-arm provisional: {n_few_arm}")
    lines.append("")
    lines.append(f"Sizing (threshold `<=4` -> tiny): {sizing}")
    lines.append("")
    lines.append("## Per-team (sorted by recent_volatility desc)")
    lines.append("")
    lines.append("| team | games | recent_volatility | volatility_flag | few_games_flag |")
    lines.append("| --- | ---: | ---: | :---: | :---: |")
    for r in table.itertuples(index=False):
        vol = "NaN" if pd.isna(r.recent_volatility) else f"{r.recent_volatility:.3f}"
        lines.append(
            f"| {r.team} | {r.games} | {vol} | "
            f"{'YES' if r.volatility_flag else ''} | "
            f"{'YES' if r.few_games_flag else ''} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    teams = _field_teams()

    # Throwaway store — the diagnostic writes nothing the model consumes and
    # leaves the real bitemporal store untouched.
    with tempfile.TemporaryDirectory() as tmp:
        store = BitemporalStore(root=tmp)
        n_rows = _ingest_real_martj42(store)
        res = count_volatility_arm(store=store, cutoff=CUTOFF, field_teams=teams)

    report = _render_report(res, n_rows)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report)

    n_vol = int(res["volatility_flag"].sum())
    n_few = int(res["few_games_flag"].sum())
    print(f"Wrote {REPORT_PATH}")
    print(f"  field teams              : {len(res)}")
    print(f"  volatility-arm provisional: {n_vol}")
    print(f"  few-games-arm provisional : {n_few}")
    flagged = res.loc[res["volatility_flag"], "team"].tolist()
    if flagged:
        print(f"  volatility-flagged teams : {', '.join(flagged)}")


if __name__ == "__main__":
    main()
