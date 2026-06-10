"""P3 v0 [LOAD-BEARING]: the sim-mirrors-predict invariant for the squad anchor.

The squad-strength covariate enters the fit's att/def PRIOR (k_squad·squad_z·
has_squad). RateBook (the sim-side rate builder) reads the FITTED att/def
directly — the SAME arrays Posterior.predict_scoreline reads — so whatever the
squad anchor does to the fit is reflected wherever the sim builds rates for
unplayed fixtures, EXACTLY as elo_z/strength_prior is. This file pins that
end-to-end:

  * sim-side rate for a COVERED team MOVES when k_squad>0 (vs k_squad=0), AND
  * sim-side rate is byte-identical at k_squad=0 (with vs without a squad_tag), AND
  * the RateBook rate equals Posterior.predict_scoreline's rate for the same
    fixture/draw (the mirror is exact, not approximate).

Tiny synthetic store + tiny advi + fixed seed; the squad anchor loads from the
REAL committed config/squads/ CSVs (offline).
"""
import copy
import tempfile

import numpy as np
import pandas as pd

from wcmodel.config import load_config
from wcmodel.data.sources.results import normalize_results
from wcmodel.data.store import BitemporalStore, Policy
from wcmodel.model.scoreline import fit
from wcmodel.sim.scoreline import RateBook

_CUTOFF = "2024-01-01"

# Real WC-2022 covered nations so the squad anchor has signal.
_BASE = pd.DataFrame(
    [
        ("2023-01-02", "Brazil", "Germany", 2, 0, "Friendly", "London", "England", True),
        ("2023-02-02", "Spain", "France", 1, 1, "Friendly", "London", "England", True),
        ("2023-03-02", "Brazil", "Spain", 3, 0, "Friendly", "London", "England", True),
        ("2023-04-02", "Germany", "France", 0, 2, "Friendly", "London", "England", True),
        ("2023-05-02", "Brazil", "France", 2, 1, "Friendly", "London", "England", True),
        ("2023-06-02", "Germany", "Spain", 1, 1, "Friendly", "London", "England", True),
        ("2023-07-02", "Brazil", "Germany", 4, 0, "Friendly", "London", "England", True),
        ("2023-08-02", "Spain", "France", 0, 0, "Friendly", "London", "England", True),
    ],
    columns=["date", "home_team", "away_team", "home_score", "away_score",
             "tournament", "city", "country", "neutral"],
)


def _store():
    d = tempfile.mkdtemp()
    store = BitemporalStore(root=d)
    store.write("results", normalize_results(_BASE.copy()), policy=Policy.POINT_IN_TIME,
                keys=["match_id"], source="martj42", source_version="test")
    return store


def _cfg(*, k_squad, squad_tag, k_elo=0.6):
    cfg = copy.deepcopy(load_config())
    sp = {"enabled": True, "source": "elo", "k_att": k_elo, "k_def": k_elo,
          "k_squad": float(k_squad)}
    if squad_tag is not None:
        sp["squad_tag"] = squad_tag
    cfg["model"]["strength_prior"] = sp
    return cfg


def _fit(cfg):
    return fit(_CUTOFF, _store(), backend="advi", draws=80, seed=0,
              advi_iters=300, config=cfg)


def _mean_rate(rb, home, away, draws=None):
    """Mean (lh, la) over draws for a neutral fixture (the sim-side rate)."""
    n = rb.n_draws if draws is None else draws
    lhs, las = [], []
    for s in range(n):
        lh, la = rb.rates(home, away, neutral=True, draw=s)
        lhs.append(lh); las.append(la)
    return float(np.mean(lhs)), float(np.mean(las))


def test_sim_rate_moves_for_covered_team_when_k_squad_positive():
    """A covered team's sim-side rate MOVES when k_squad>0 vs k_squad=0 — the
    anchor reaches the sim through the fitted att/def RateBook reads."""
    rb0 = RateBook(_fit(_cfg(k_squad=0.0, squad_tag="wc2022")))
    rb1 = RateBook(_fit(_cfg(k_squad=0.6, squad_tag="wc2022")))
    lh0, _ = _mean_rate(rb0, "Brazil", "France")
    lh1, _ = _mean_rate(rb1, "Brazil", "France")
    assert abs(lh1 - lh0) > 1e-3, (
        "covered team's sim-side rate did not move with k_squad>0 — the squad "
        "anchor is not mirrored into the sim (sim-mirrors-predict broken)")


def test_sim_rate_byte_identical_at_k_squad_zero():
    """At k_squad=0 the sim-side rate is byte-identical with vs without a
    squad_tag — the squad term is fully off in the sim too."""
    rb_no = RateBook(_fit(_cfg(k_squad=0.0, squad_tag=None)))
    rb_tag = RateBook(_fit(_cfg(k_squad=0.0, squad_tag="wc2022")))
    lh_no, la_no = _mean_rate(rb_no, "Brazil", "France")
    lh_tag, la_tag = _mean_rate(rb_tag, "Brazil", "France")
    assert abs(lh_no - lh_tag) < 1e-9 and abs(la_no - la_tag) < 1e-9, (
        "k_squad=0 sim rate differs with a squad_tag — not byte-identical-off")


def test_ratebook_rate_mirrors_predict_scoreline_exactly():
    """The RateBook rate for a fixture/draw EQUALS what Posterior.predict_scoreline
    builds for the same fixture (the sim-must-mirror-predict discipline). Checked
    on a single draw to byte precision."""
    post = _fit(_cfg(k_squad=0.6, squad_tag="wc2022"))
    rb = RateBook(post)
    home, away, s = "Brazil", "France", 0
    lh_rb, la_rb = rb.rates(home, away, neutral=True, draw=s)
    # Rebuild predict_scoreline's per-draw rate directly from the posterior.
    p = post.idata.posterior
    att = p["att"].stack(z=("chain", "draw")).values
    defe = p["def"].stack(z=("chain", "draw")).values
    mu = p["mu"].stack(z=("chain", "draw")).values
    home_adv = p["home_adv"].stack(z=("chain", "draw")).values
    k = post._cfg["neutral_home_adv_fraction"]
    hi = post.teams.index(home); ai = post.teams.index(away)
    lh_ref = float(np.exp(mu[s] + k * home_adv[s] + att[hi, s] - defe[ai, s]))
    la_ref = float(np.exp(mu[s] + k * home_adv[s] + att[ai, s] - defe[hi, s]))
    assert abs(lh_rb - lh_ref) < 1e-12 and abs(la_rb - la_ref) < 1e-12, (
        "RateBook rate diverges from predict_scoreline's arithmetic")
