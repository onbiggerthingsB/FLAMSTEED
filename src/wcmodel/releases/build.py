"""Assemble one gated, provenance- and freshness-stamped release payload.

Gate order: cutoff form -> text hygiene -> PIT -> unknown teams -> price ->
coherence -> betting-key scan. Fail-loud everywhere; a partial artifact is
never emitted."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from wcmodel.dashboard.provenance import Provenance, _git_rev
from wcmodel.releases import (ARCHIVE_URL, BETTING_FIELD_DENYLIST,
                              DATA_SOURCE_NAME, LICENSE_STAMP,
                              METHODOLOGY_URL, MODEL_NAME)
from wcmodel.releases.fixtures import unknown_teams
from wcmodel.releases.pricing import known_team_set, price_fixtures

# The ONLY accepted cutoff spelling. Requiring the literal string (not merely a
# timestamp that happens to land on midnight) makes `provenance.as_of` canonical
# by construction: every artifact citing the same cutoff cites the same bytes.
_CUTOFF_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T00:00:00Z$")

# Leading chars a spreadsheet interprets as a formula when a CSV cell is opened.
# NOT including "-": scores like 1-0 and names like Guinea-Bissau are legitimate.
_FORMULA_PREFIX = ("=", "+", "@")


def _check_text(value: str, what: str) -> None:
    """Reject text that would corrupt the CSV/HTML surfaces it is rendered into."""
    if "\n" in value or "\r" in value:
        raise ValueError(f"newline in {what}: {value!r}")
    if value[:1] in _FORMULA_PREFIX:
        raise ValueError(f"formula-prefix in {what}: {value!r}")


def build_release(*, cutoff: str, fixtures: pd.DataFrame, post,
                  posterior_key: str, window_label: str, n_draws: int,
                  latest_result: str) -> dict:
    if not isinstance(cutoff, str) or not _CUTOFF_RE.match(cutoff):
        raise ValueError("release cutoff must be the literal form YYYY-MM-DDT00:00:00Z "
                         f"(UTC midnight), got {cutoff!r}")

    _check_text(str(window_label), "window label")
    for col in ("home", "away"):
        for name in fixtures[col].astype(str):
            _check_text(name, f"team name ({col})")

    cutoff_day = pd.Timestamp(cutoff[:10])
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

        # The totals ladder is nested by construction (P(>1.5) >= P(>2.5) >= P(>3.5));
        # a coherent 1X2 does NOT imply a coherent ladder — a grid can hide a defect
        # in the anti-diagonal bands that 1X2 sums away.
        t = r["totals"]
        tvals = [t["over_1_5"], t["over_2_5"], t["over_3_5"]]
        if (not all(np.isfinite(tvals))
                or any(v < -1e-9 or v > 1 + 1e-9 for v in tvals)
                or tvals[0] < tvals[1] - 1e-9 or tvals[1] < tvals[2] - 1e-9):
            raise ValueError(f"incoherent totals for {r['home']} v {r['away']}: {t!r}")

        mp = r["modal_score_p"]
        if not np.isfinite(mp) or mp < -1e-9 or mp > 1 + 1e-9:
            raise ValueError(
                f"incoherent modal score probability for {r['home']} v {r['away']}: {mp!r}")

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
