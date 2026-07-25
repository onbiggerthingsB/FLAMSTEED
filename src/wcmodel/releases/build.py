"""Assemble one gated, provenance- and freshness-stamped release payload.

Gate order: cutoff form -> PIT -> unknown teams -> price -> coherence ->
betting-key scan. Fail-loud everywhere; a partial artifact is never emitted."""
from __future__ import annotations

import numpy as np
import pandas as pd

from wcmodel.dashboard.provenance import Provenance, _git_rev
from wcmodel.releases import (ARCHIVE_URL, BETTING_FIELD_DENYLIST,
                              DATA_SOURCE_NAME, LICENSE_STAMP,
                              METHODOLOGY_URL, MODEL_NAME)
from wcmodel.releases.fixtures import unknown_teams
from wcmodel.releases.pricing import known_team_set, price_fixtures


def build_release(*, cutoff: str, fixtures: pd.DataFrame, post,
                  posterior_key: str, window_label: str, n_draws: int,
                  latest_result: str) -> dict:
    ts = pd.Timestamp(cutoff)
    ts_naive = ts.tz_localize(None) if ts.tzinfo else ts
    if ts_naive != ts_naive.normalize():
        raise ValueError(f"release cutoff must be UTC midnight (T00:00:00Z), got {cutoff}")

    cutoff_day = ts_naive.normalize()
    early = fixtures[pd.to_datetime(fixtures["date"]).dt.normalize() < cutoff_day]
    if len(early):
        rows = early[["date", "home", "away"]].astype(str).to_dict("records")
        raise ValueError(f"fixture(s) dated before the release cutoff {cutoff}: {rows}")

    missing = unknown_teams(fixtures, known_team_set(post))
    if missing:
        raise ValueError(f"unknown team name(s) in fixtures: {missing}")

    rows = price_fixtures(post, fixtures)
    for r in rows:
        vals = list(r["one_x_two"].values())
        s = sum(vals)
        if (not all(np.isfinite(vals)) or abs(s - 1.0) > 1e-6
                or any(v < -1e-9 or v > 1 + 1e-9 for v in vals)):
            raise ValueError(
                f"incoherent 1X2 for {r['home']} v {r['away']}: {r['one_x_two']!r}")
        leak = set(r) & BETTING_FIELD_DENYLIST
        if leak:
            raise ValueError(f"betting field(s) in release row: {sorted(leak)}")

    prov = Provenance(cutoff=cutoff, posterior_key=posterior_key,
                      git=_git_rev(), is_synthetic=False, n_sims=0)
    return {
        "provenance": prov.to_dict(),
        "license": LICENSE_STAMP,
        "model_name": MODEL_NAME,
        "methodology_url": METHODOLOGY_URL,
        "archive_url": ARCHIVE_URL,
        "window_label": str(window_label),
        "n_draws": int(n_draws),
        "data_source": {"name": DATA_SOURCE_NAME,
                        "latest_result": str(latest_result)},
        "rows": rows,
    }
