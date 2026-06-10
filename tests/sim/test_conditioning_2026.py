"""Real-2026-bracket played-results conditioning smoke test (Phase 0 §3).

The per-cutoff conditioning canary (``test_leakage_sim.py``) proves conditioning
is LOAD-BEARING but over a *synthetic* 1-group bracket and asserts only that
progression DIFFERS. The deterministic ``simulate_one`` tests (``test_tournament.py``)
pin the in-loop group/knockout FIX mechanics with stub rate books. NEITHER runs
the end-to-end conditioning path against the REAL ``config/tournament_2026.yaml``
48-team draw, and neither asserts the *directional* (coherent) shift the spec
requires: the winner's ``advance_from_group`` strictly UP, the loser's strictly
DOWN.

This test fills exactly that gap. It:
  1. builds a tiny store with minimal pre-cutoff history for ALL 48 bracket teams
     (so ``RateBook(posterior)`` resolves every fixture) + ``strength_prior``
     pinned OFF (the house pattern for tiny synthetic fits) + ``advi_iters=300``,
     fixed seed;
  2. fits at a fake mid-groups cutoff and sims the REAL bracket UNCONDITIONED
     (``n_sims=2000``) -> ``adv0``;
  3. ingests a fabricated PLAYED matchday-1 fixture from the real draw — the
     hosts' opener Mexico vs South Africa (2026-06-11, BEFORE the cutoff), score
     5-0 to the home side — written POINT_IN_TIME keyed ``match_id``;
  4. re-sims CONDITIONED -> ``adv1`` and asserts (a) the played match is FIXED
     (it enters ``_played_as_of`` — the exact leakage-safe set the conditioning
     consumes), (b) the winner's advance strictly rises and the loser's strictly
     falls, (c) determinism (same seed -> identical ``adv1``).

Speed: one tiny ADVI fit + two 2k-sims over the real bracket — measured well
under the 90s default-suite budget, so it is NOT marked slow.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from wcmodel.config import load_config
from wcmodel.data.sources.results import normalize_results
from wcmodel.data.store import BitemporalStore, Policy
from wcmodel.data.tournament import load_tournament
from wcmodel.model.scoreline import fit
from wcmodel.sim.run import SimConfig, _played_as_of, simulate

# Fake cutoff midway through the groups: AFTER the 2026-06-11 hosts' opener, so
# that fixture is played-as-of-cutoff and gets FIXED by the conditioning.
_CUTOFF = "2026-06-15T00:00:00Z"
# The REAL hosts' opener (group A, matchday 1) — an actual fixture row in the draw.
_HOME, _AWAY = "Mexico", "South Africa"
_PLAYED_DATE = "2026-06-11"   # strictly before _CUTOFF -> knowable as-of cutoff
_REAL_DRAW = Path(__file__).resolve().parents[2] / "config" / "tournament_2026.yaml"


def _tiny_cfg() -> dict:
    """Production config with ``strength_prior`` pinned OFF (house pattern for tiny
    synthetic fits) — the only deviation from ``load_config()``; the ``model:`` block
    is otherwise untouched."""
    cfg = load_config()
    sp = {**cfg["model"].get("strength_prior", {}), "enabled": False}
    return {**cfg, "model": {**cfg["model"], "strength_prior": sp}}


def _bracket_team_history(teams: list[str]) -> pd.DataFrame:
    """Minimal pre-cutoff friendly history giving EVERY bracket team a couple of
    played matches, so ``features.build`` (and thus the fit) covers all 48 teams and
    ``RateBook(posterior)`` resolves every real-draw fixture. All 1-1 draws on unique
    early-2025 dates (deterministic Elo input); all strictly before the cutoff."""
    d0 = pd.Timestamp("2025-01-01")
    rows = []
    day = 0
    for i, tm in enumerate(teams):
        opp = teams[(i + 1) % len(teams)]
        for _ in range(2):
            day += 1
            rows.append((str((d0 + pd.Timedelta(days=day)).date()), tm, opp, 1, 1,
                         "Friendly", "London", "England", False))
    return pd.DataFrame(rows, columns=[
        "date", "home_team", "away_team", "home_score", "away_score",
        "tournament", "city", "country", "neutral"])


def _write_results(store: BitemporalStore, raw: pd.DataFrame) -> None:
    """Normalize + POINT_IN_TIME write keyed ``match_id`` (the canonical results path)."""
    norm = normalize_results(raw)
    norm["winner_override"] = pd.NA
    store.write("results", norm, policy=Policy.POINT_IN_TIME, keys=["match_id"],
                source="martj42", source_version="test")


@pytest.fixture
def bracket_store(tmp_path):
    """A tiny store covering all 48 real-2026 bracket teams' minimal history."""
    teams = list(load_tournament(_REAL_DRAW)["teams"])
    store = BitemporalStore(root=Path(tempfile.mkdtemp(dir=tmp_path)))
    _write_results(store, _bracket_team_history(teams))
    return store


def _sim(post, store, cfg) -> pd.Series:
    """Sim the REAL bracket (``tournament=None`` -> config/tournament_2026.yaml) at the
    fake cutoff and return the per-team ``advance_from_group`` column."""
    simcfg = SimConfig(tournament=None, n_sims=2000, seed=0, max_goals=8,
                       et_scale=0.3333, pen_home_prob=0.5, config=cfg)
    res = simulate(_CUTOFF, post, store, simcfg)
    return res.progression["advance_from_group"]


def test_real_bracket_played_conditioning_shifts_advance(bracket_store):
    cfg = _tiny_cfg()
    post = fit(_CUTOFF, bracket_store, backend="advi", draws=120, seed=0,
               advi_iters=300, config=cfg)
    assert _HOME in post.teams and _AWAY in post.teams  # fit covers the bracket teams

    # UNCONDITIONED: the hosts' opener is not yet in the store -> it is SIMULATED.
    adv0 = _sim(post, bracket_store, cfg)

    # Ingest the fabricated PLAYED hosts' opener (5-0 home win), dated BEFORE the cutoff.
    played = pd.DataFrame([
        (_PLAYED_DATE, _HOME, _AWAY, 5, 0, "FIFA World Cup", "Mexico City", "Mexico", True),
    ], columns=["date", "home_team", "away_team", "home_score", "away_score",
                "tournament", "city", "country", "neutral"])
    _write_results(bracket_store, played)

    # (a) The played match is FIXED: it enters _played_as_of — the EXACT leakage-safe
    # set the conditioning consumes (same mechanism the per-cutoff canary asserts on).
    p = _played_as_of(bracket_store, _CUTOFF)
    hit = p[(p["home_team"] == _HOME) & (p["away_team"] == _AWAY)
            & (p["date"] == pd.Timestamp(_PLAYED_DATE))]
    assert len(hit) == 1, "the fabricated hosts' opener must be played-as-of the cutoff"
    assert (int(hit.iloc[0]["home_score"]), int(hit.iloc[0]["away_score"])) == (5, 0)

    # CONDITIONED on the same posterior (only the played set changed).
    adv1 = _sim(post, bracket_store, cfg)

    # (b) Coherent shift: the 5-0 winner advances MORE, the loser advances LESS — strictly.
    assert adv1.loc[_HOME] > adv0.loc[_HOME], (
        f"winner {_HOME} advance_from_group did not rise: "
        f"{adv0.loc[_HOME]:.4f} -> {adv1.loc[_HOME]:.4f}")
    assert adv1.loc[_AWAY] < adv0.loc[_AWAY], (
        f"loser {_AWAY} advance_from_group did not fall: "
        f"{adv0.loc[_AWAY]:.4f} -> {adv1.loc[_AWAY]:.4f}")

    # (c) Determinism: same seed + same played set -> identical conditioned advance.
    adv1_rerun = _sim(post, bracket_store, cfg)
    assert adv1.equals(adv1_rerun), "conditioned sim is not seed-deterministic"
