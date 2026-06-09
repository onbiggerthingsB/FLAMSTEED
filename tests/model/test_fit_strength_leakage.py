"""Task 4 [LOAD-BEARING]: fit-level leakage canary for the Elo strength anchor.

``fit()`` computes ``elo_z = team_elo_z(feats, teams)`` where ``feats`` is the
strictly ``< cutoff`` panel, then threads it into ``build_design`` -> the
anchored att/def prior. This canary proves the anchor is leakage-safe AND that
the canary has TEETH:

  * LEAKAGE: with strength_prior ON, a POST-cutoff result (dated > cutoff) that
    would massively change a team's Elo must NOT change the fitted ``att`` — the
    row is invisible to the ``< cutoff`` panel, hence invisible to ``elo_z`` (and
    to the likelihood).
  * POSITIVE CONTROL (teeth): the SAME result ingested PRE-cutoff (dated < cutoff)
    DOES change ``att`` — now it is in the ``< cutoff`` panel, so it moves both
    the likelihood and the elo_z anchor. This proves the leakage assertion is not
    vacuously green (a fit that could never move would make the canary toothless).

Uses a tiny synthetic store + tiny advi_iters + a fixed seed for speed.
"""
import copy
import tempfile

import numpy as np
import pandas as pd

from wcmodel.config import load_config
from wcmodel.data.sources.results import normalize_results
from wcmodel.data.store import BitemporalStore, Policy
from wcmodel.model.scoreline import fit

# Cutoff for every fit below. All BASE matches are < this; the perturbing match
# is placed either AFTER (leakage) or BEFORE (positive control) it.
_CUTOFF = "2024-01-01"

# Base panel: 4 teams, several < cutoff neutral matches so the fit has signal and
# each team has a distinct pre-cutoff Elo (so elo_z is non-degenerate).
_BASE = pd.DataFrame(
    [
        ("2023-01-02", "A", "B", 2, 0, "Friendly", "London", "England", True),
        ("2023-02-02", "C", "D", 1, 1, "Friendly", "London", "England", True),
        ("2023-03-02", "A", "C", 3, 0, "Friendly", "London", "England", True),
        ("2023-04-02", "B", "D", 0, 2, "Friendly", "London", "England", True),
        ("2023-05-02", "A", "D", 2, 1, "Friendly", "London", "England", True),
        ("2023-06-02", "B", "C", 1, 1, "Friendly", "London", "England", True),
        ("2023-07-02", "A", "B", 4, 0, "Friendly", "London", "England", True),
        ("2023-08-02", "C", "D", 0, 0, "Friendly", "London", "England", True),
    ],
    columns=["date", "home_team", "away_team", "home_score", "away_score",
             "tournament", "city", "country", "neutral"],
)

# A LOPSIDED result that would massively move team B's Elo (B annihilates A).
# Placed post-cutoff for the leakage arm, pre-cutoff for the positive control.
_PERTURB_COLS = ["date", "home_team", "away_team", "home_score", "away_score",
                 "tournament", "city", "country", "neutral"]
_PERTURB_ROW = ("B", "A", 9, 0, "FIFA World Cup", "Doha", "Qatar", True)


def _store(extra_date: str | None):
    raw = _BASE.copy()
    if extra_date is not None:
        extra = pd.DataFrame(
            [(extra_date, *_PERTURB_ROW)], columns=_PERTURB_COLS
        )
        raw = pd.concat([raw, extra], ignore_index=True)
    d = tempfile.mkdtemp()
    store = BitemporalStore(root=d)
    store.write("results", normalize_results(raw), policy=Policy.POINT_IN_TIME,
                keys=["match_id"], source="martj42", source_version="test")
    return store


def _strength_cfg(enabled=True):
    cfg = copy.deepcopy(load_config())
    cfg["model"]["strength_prior"] = {
        "enabled": enabled, "source": "elo", "k_att": 0.30, "k_def": 0.30
    }
    return cfg


def _fit_att(store, cfg):
    """Fit (strength ON), return the team->mean-att map. Tiny advi + fixed seed."""
    post = fit(_CUTOFF, store, backend="advi", draws=80, seed=0,
               advi_iters=300, config=cfg)
    att = post.idata.posterior["att"].mean(dim=("chain", "draw")).values
    return dict(zip(post.teams, att))


def test_fit_att_invariant_to_post_cutoff_result_strength_on():
    """LEAKAGE: a POST-cutoff result that would massively move team B's Elo must
    NOT change the fitted att — it is invisible to the < cutoff panel/elo_z."""
    cfg = _strength_cfg(enabled=True)
    base = _fit_att(_store(extra_date=None), cfg)
    # Same base panel + a lopsided B-9-0-A result dated AFTER the cutoff.
    leaked = _fit_att(_store(extra_date="2024-06-05"), cfg)
    assert set(base) == set(leaked)
    for team in base:
        assert abs(base[team] - leaked[team]) < 1e-9, (
            f"post-cutoff result leaked into att[{team!r}]: "
            f"|Δ|={abs(base[team] - leaked[team]):.3e} (strength anchor not "
            f"leakage-safe)"
        )


def test_positive_control_pre_cutoff_result_does_change_att():
    """TEETH: the SAME lopsided result ingested PRE-cutoff (dated < cutoff) DOES
    change att for the affected team — it now enters the < cutoff panel, moving
    both the likelihood and the elo_z anchor. Proves the leakage assertion above
    is non-vacuous: the apparatus CAN detect a change when one is warranted."""
    cfg = _strength_cfg(enabled=True)
    base = _fit_att(_store(extra_date=None), cfg)
    # Same result, dated BEFORE the cutoff -> in-panel -> must move att.
    moved = _fit_att(_store(extra_date="2023-09-02"), cfg)
    affected = max(base, key=lambda t: abs(base[t] - moved.get(t, base[t])))
    assert abs(base[affected] - moved[affected]) > 1e-3, (
        "positive control FAILED: a PRE-cutoff result moved att by <1e-3 — the "
        "leakage canary would be vacuous (the fit cannot move, so its invariance "
        "proves nothing)"
    )
