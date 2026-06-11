"""Leakage canary WITH positive control for the matchday-1 MANUAL results-ingest
fallback (Phase 0, binding rule 1).

Mirrors ``tests/sim/test_conditioning_2026.py`` but drives the conditioning through
the REAL manual-results path (``validate_manual_csv`` -> ``ingest_manual_rows`` ->
``ingest_live_result``), proving the hand-entered result is leakage-safe AND
load-bearing:

  (i)  NEGATIVE (inert): a manual row whose match date is AFTER the cutoff is
       EXCLUDED by the bitemporal gate — absent from ``store.read(cutoff)`` AND from
       ``_played_as_of(cutoff)`` — so the sim at the earlier cutoff does NOT fix it
       (advance probs UNCHANGED, byte-identical conditioned series);
  (ii) POSITIVE CONTROL (teeth): the SAME row dated BEFORE the cutoff IS visible,
       enters ``_played_as_of``, and CHANGES the sim conditioning — the fixture
       becomes FIXED and the 5-0 winner's ``advance_from_group`` strictly RISES while
       the loser's strictly FALLS.

House tiny-fixture rules: ``strength_prior`` pinned OFF, ``advi_iters=300``, fixed
seed, ``n_sims=2000`` over the real 48-team draw. One tiny ADVI fit + a few small
sims — under the default-suite budget, so NOT marked slow.
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
from wcmodel.live.manual_results import ingest_manual_rows, validate_manual_csv
from wcmodel.model.scoreline import fit
from wcmodel.sim.run import SimConfig, _played_as_of, simulate

_CUTOFF = "2026-06-15T00:00:00Z"          # midway through the groups
# POSITIVE control fixture: the real group-A hosts' opener, dated BEFORE the cutoff.
_HOME, _AWAY = "Mexico", "South Africa"
_BEFORE_DATE = "2026-06-11"               # strictly before _CUTOFF -> conditions
# NEGATIVE (leakage) fixture: a real group-A matchday-14 fixture dated AFTER the cutoff
# (Mexico v South Africa plays only on 06-11, so the after-cutoff canary uses a distinct
# real fixture whose 5-0 result WOULD move advancement if it leaked — non-vacuous).
_AFT_HOME, _AFT_AWAY = "Czech Republic", "Mexico"
_AFTER_DATE = "2026-06-24"                # strictly after _CUTOFF -> must be inert
_REAL_DRAW = Path(__file__).resolve().parents[2] / "config" / "tournament_2026.yaml"


def _tiny_cfg() -> dict:
    cfg = load_config()
    sp = {**cfg["model"].get("strength_prior", {}), "enabled": False}
    return {**cfg, "model": {**cfg["model"], "strength_prior": sp}}


def _bracket_team_history(teams: list[str]) -> pd.DataFrame:
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


def _write_history(store: BitemporalStore, raw: pd.DataFrame) -> None:
    norm = normalize_results(raw)
    norm["winner_override"] = pd.NA
    store.write("results", norm, policy=Policy.POINT_IN_TIME, keys=["match_id"],
                source="martj42", source_version="test")


@pytest.fixture
def bracket_store(tmp_path):
    teams = list(load_tournament(_REAL_DRAW)["teams"])
    store = BitemporalStore(root=Path(tempfile.mkdtemp(dir=tmp_path)))
    _write_history(store, _bracket_team_history(teams))
    return store


def _manual_csv(tmp_path, date: str, home: str, away: str) -> Path:
    p = tmp_path / f"manual_{date}_{home}.csv".replace(" ", "_")
    p.write_text(
        "date,home_team,away_team,home_score,away_score,shootout_winner\n"
        f"{date},{home},{away},5,0,\n")
    return p


def _sim(post, store, cfg) -> pd.Series:
    simcfg = SimConfig(tournament=None, n_sims=2000, seed=0, max_goals=8,
                       et_scale=0.3333, pen_home_prob=0.5, config=cfg)
    return simulate(_CUTOFF, post, store, simcfg).progression["advance_from_group"]


def test_manual_result_before_cutoff_conditions_sim_positive_control(bracket_store, tmp_path):
    """POSITIVE CONTROL: a manual row dated BEFORE the cutoff enters _played_as_of and
    FIXES the fixture — the 5-0 winner advances strictly more, the loser strictly less."""
    cfg = _tiny_cfg()
    post = fit(_CUTOFF, bracket_store, backend="advi", draws=120, seed=0,
               advi_iters=300, config=cfg)
    assert _HOME in post.teams and _AWAY in post.teams

    adv0 = _sim(post, bracket_store, cfg)  # unconditioned (opener not yet entered)

    # Hand-enter the 5-0 hosts' opener via the REAL manual path, dated BEFORE the cutoff.
    csv = _manual_csv(tmp_path, _BEFORE_DATE, _HOME, _AWAY)
    rows = validate_manual_csv(csv)
    ingest_manual_rows(bracket_store, rows, observed_at="2026-06-11T23:30:00Z")

    # It enters _played_as_of (the exact leakage-safe set the conditioning consumes).
    p = _played_as_of(bracket_store, _CUTOFF)
    hit = p[(p["home_team"] == _HOME) & (p["away_team"] == _AWAY)
            & (p["date"] == pd.Timestamp(_BEFORE_DATE))]
    assert len(hit) == 1, "the manual opener must be played-as-of the cutoff"
    assert (int(hit.iloc[0]["home_score"]), int(hit.iloc[0]["away_score"])) == (5, 0)

    adv1 = _sim(post, bracket_store, cfg)  # conditioned (only the played set changed)
    assert adv1.loc[_HOME] > adv0.loc[_HOME], (
        f"winner {_HOME} advance did not rise: {adv0.loc[_HOME]:.4f} -> {adv1.loc[_HOME]:.4f}")
    assert adv1.loc[_AWAY] < adv0.loc[_AWAY], (
        f"loser {_AWAY} advance did not fall: {adv0.loc[_AWAY]:.4f} -> {adv1.loc[_AWAY]:.4f}")
    # Determinism: same seed + same played set -> identical conditioned advance.
    assert adv1.equals(_sim(post, bracket_store, cfg)), "conditioned sim not seed-deterministic"


def test_manual_result_after_cutoff_is_inert_leakage_canary(bracket_store, tmp_path):
    """NEGATIVE (leakage canary): a manual row dated AFTER the cutoff is excluded by the
    bitemporal gate — absent from store.read(cutoff) AND _played_as_of — so the sim at
    the earlier cutoff is byte-identical (the after-cutoff result cannot leak)."""
    cfg = _tiny_cfg()
    post = fit(_CUTOFF, bracket_store, backend="advi", draws=120, seed=0,
               advi_iters=300, config=cfg)

    adv0 = _sim(post, bracket_store, cfg)  # baseline

    # Hand-enter a 5-0 result dated AFTER the cutoff (a real group-A 2026-06-24 fixture).
    csv = _manual_csv(tmp_path, _AFTER_DATE, _AFT_HOME, _AFT_AWAY)
    rows = validate_manual_csv(csv)
    # observed_at = now (the operator could enter it early); the DATE-floored cutoff
    # filter must still exclude it from conditioning at the earlier cutoff.
    ingest_manual_rows(bracket_store, rows, observed_at="2026-06-24T23:30:00Z")

    # The bitemporal/date gate excludes it: absent from the as-of read AND _played_as_of.
    read = bracket_store.read("results", cutoff=_CUTOFF)
    assert read[(read["home_team"] == _AFT_HOME) & (read["away_team"] == _AFT_AWAY)
                & (pd.to_datetime(read["date"]) == pd.Timestamp(_AFTER_DATE))].empty, (
        "an after-cutoff manual result leaked into store.read(cutoff)")
    p = _played_as_of(bracket_store, _CUTOFF)
    assert p[(p["home_team"] == _AFT_HOME) & (p["away_team"] == _AFT_AWAY)
             & (p["date"] == pd.Timestamp(_AFTER_DATE))].empty, (
        "an after-cutoff manual result leaked into _played_as_of (conditioning set)")

    # The sim at the earlier cutoff is UNCHANGED (byte-identical advance series).
    adv1 = _sim(post, bracket_store, cfg)
    assert adv1.equals(adv0), (
        "an after-cutoff manual result changed the conditioned sim — LEAK (the date<cutoff_day "
        "filter must keep it inert at the earlier cutoff)")
