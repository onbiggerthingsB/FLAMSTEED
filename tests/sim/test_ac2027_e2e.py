"""AFC Asian Cup 2027 acceptance gate (Phase-2A Task 5) — NON-SKIPPING.

Tasks 0-4 generalized every shape constant behind the ``format:`` block and
proved the WC-2026 path frozen (golden hash). What none of them proved is that
the AC-2027 configuration actually WORKS end-to-end: a 24-team / 6-group /
best-4-thirds / 15-knockout bracket driven through the REAL production entry
point ``sim.run.simulate`` — real tiny posterior, real ``BitemporalStore``,
real per-cutoff conditioning. This module is that proof. Any failure here is a
generalization gap, to be fixed in production (minimally, golden kept green) —
never papered over in the test.

Construction (nothing invented):

  * The bracket is SYNTHETIC (the real drawn yaml is Task 6's deliverable) but
    its knockout wiring mirrors the secured regs extract
    ``config/afc2027_rules_extract.md`` — Art. 9.2 (6 groups of 4), Art. 9.8
    (R16 pairings), Arts. 9.10-9.12 (QF/SF/Final wiring), no third-place match.
    The four winner-vs-third R16 fixtures are DERIVED at runtime from the
    Task-3 table ``config/third_place_assignment_ac2027.json``: third-slot
    labels via :func:`_slot_sets_from_table` (eligible sets recomputed from the
    table BODY, not trusted from ``_meta``) and the winner-slot match numbers
    via ``_meta.columns_winner_slot_to_match`` — so bracket and table can never
    drift apart.
  * Team names are synthetic (``TeamA1`` ...) EXCEPT the host "Saudi Arabia"
    (slot A1), so the F5 host machinery — group-stage ``host_factor_map`` AND
    the opt-in KO host policy — runs live through the whole gate. A test-design
    choice, not a claim about the real draw.
  * The posterior is REAL and fitted here: the history-builder / tiny-config /
    ADVI-fit pattern is mirrored VERBATIM from
    ``tests/sim/test_conditioning_2026.py`` / ``scripts/capture_wc_golden.py``,
    extended to a panel of EXACTLY the 24 bracket teams (the same
    panel==bracket-coverage rule ``tests/dashboard/conftest.py`` applies to its
    synthetic tournament). The fixture ASSERTS the fit succeeded and covers all
    24 — a broken fit is a hard FAIL on every test below, never a skip.
  * Store wiring mirrors the production daily loop: friendly history + the
    36-row UNPLAYED schedule via ``ingest_wc_group_fixtures`` (validating the
    formatted document at entry), then played results overlaid later — the
    later write wins the store's deterministic same-timestamp tie-break, the
    exact schedule->result overlay production performs.

The conditioning canary (last test) is run-LEVEL: baseline before matchday 1,
a played matchday-1 result must move ``advance_from_group`` (winner strictly
up, loser strictly down) AND the champion distribution — the POSITIVE control
— and a result dated after the cutoff must leave both output frames
byte-identical — the leakage canary the positive control licenses.
"""
from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from wcmodel.config import load_config
from wcmodel.dashboard.schema import _LADDER, validate_progression_coherence
from wcmodel.data.sources.results import normalize_results
from wcmodel.data.store import BitemporalStore, Policy
from wcmodel.data.tournament import (ingest_wc_group_fixtures, tournament_format,
                                     validate_tournament)
from wcmodel.model.scoreline import fit
from wcmodel.sim.run import SimConfig, _played_as_of, simulate
from wcmodel.sim.thirds import load_assignment_table

# --- The AC-2027 shape (regs Arts. 9.2/9.5/9.6; extract in config/) -----------
_TABLE_FILE = "third_place_assignment_ac2027.json"
_AC_FORMAT = {"n_groups": 6, "teams_per_group": 4, "per_group_advance": 2,
              "best_thirds": 4, "third_place_match": False,
              "tiebreak_order": "afc_2027", "assignment_table": _TABLE_FILE,
              "competition_name": "AFC Asian Cup", "source_tag": "ac2027_schedule",
              "hosts": {"Saudi Arabia": "SA"}, "ko_host_advantage": True}

# Matchday dates (synthetic schedule inside the real Jan-2027 window).
_MD_DATES = ("2027-01-08", "2027-01-12", "2027-01-16")
# Round-robin in schedule order: MD1 = first two pairs, ... MD3 = last two.
# The LAST TWO fixtures of each group are therefore the final-matchday pairings
# the AFC penalties criterion reads (sim/tournament.py's documented assumption).
_RR = [(0, 1), (2, 3), (0, 2), (1, 3), (0, 3), (1, 2)]

# Cutoffs (strict day-floored semantics: a result on day D is knowable from D+1).
_C0 = "2027-01-08T00:00:00Z"     # before matchday 1 -> nothing played-as-of
_C1 = "2027-01-09T00:00:00Z"     # after matchday 1's date -> MD1 results knowable
# MC params: house tiny-fit pattern (conditioning-2026 test: n_sims=2000, max_goals=8).
_SIM = dict(n_sims=2000, seed=0, max_goals=8, et_scale=0.3333, pen_home_prob=0.5)

# The canary's pinned matchday-1 fixture: the hosts' opener (group A, _RR[0]).
_HOME, _AWAY = "Saudi Arabia", "TeamA1"
# The 11 public market columns (sim/tournament.py::_COLUMNS), pinned literally.
_EXPECTED_COLUMNS = ["win_group", "advance_from_group", "reach_r16", "reach_qf",
                     "reach_sf", "reach_final", "champion",
                     "first", "second", "third", "out"]


# ---------------------------------------------------------------------------
# Bracket construction (third slots DERIVED from the Task-3 table)
# ---------------------------------------------------------------------------
def _slot_sets_from_table() -> dict[int, str]:
    """{R16 match_no: "3rd-<eligible letters>"} derived from the table BODY.

    A slot's eligible set is the set of groups the published 15-row table can
    ever assign to that match — recomputed here rather than read from ``_meta``
    so the fixtures this test builds are consistent with the table the sim
    actually looks up (``verify_thirds_table.py`` pins body==_meta separately).
    """
    data = load_assignment_table(_TABLE_FILE)
    eligible: dict[int, set[str]] = {}
    for row in data["table"].values():
        for m, g in row.items():
            eligible.setdefault(int(m), set()).add(g)
    return {m: "3rd-" + "".join(sorted(gs)) for m, gs in eligible.items()}


def _winner_slot_by_match() -> dict[int, str]:
    """{R16 match_no: winner slot ("1A"...)} from ``_meta.columns_winner_slot_to_match``."""
    data = load_assignment_table(_TABLE_FILE)
    return {int(m): slot
            for slot, m in data["_meta"]["columns_winner_slot_to_match"].items()}


def _ac_tournament() -> dict:
    """Synthetic 24-team AC-2027-shaped tournament dict (regs-wired knockouts).

    36 dated group fixtures (6 groups x 3 matchdays), 15 knockout fixtures —
    R16 numbered 37..44 (the table ``_meta``'s regs-derived R16-1..R16-8
    encoding), QF 45..48, SF 49..50, Final 51 — and NO third-place match.
    Knockout round labels use the official AFC plural spellings (Task 1's
    aliases) exactly as the schedule PDFs do.
    """
    groups = []
    for g in "ABCDEF":
        teams = [f"Team{g}{i}" for i in range(4)]
        if g == "A":
            teams[0] = _HOME              # the host, slot A1
        groups.append({"name": g, "teams": teams})

    fixtures = []
    for grp in groups:
        t = grp["teams"]
        for md in range(3):
            for a, b in _RR[2 * md:2 * md + 2]:
                fixtures.append({"home": t[a], "away": t[b],
                                 "date": _MD_DATES[md], "group": grp["name"],
                                 "round": f"Matchday {md + 1}", "venue": "Riyadh"})

    # R16: the four winner-vs-third pairings come from the table (labels from the
    # body, match numbers + winner slots from _meta); the four runner-up pairings
    # are the regs Art. 9.8 ones (R16-1: 2A v 2C, R16-4: 1F v 2E, R16-6: 1E v 2D,
    # R16-8: 2B v 2F), placed on the R16 numbers the table does NOT claim.
    third_label = _slot_sets_from_table()
    winner_slot = _winner_slot_by_match()
    assert set(third_label) == set(winner_slot), (
        "table body and _meta disagree on the winner-vs-third match numbers")
    r16 = {m: (winner_slot[m], third_label[m]) for m in winner_slot}
    rest = sorted(set(range(37, 45)) - set(r16))
    for m, pair in zip(rest, [("2A", "2C"), ("1F", "2E"), ("1E", "2D"), ("2B", "2F")]):
        r16[m] = pair
    ko = [(m, *r16[m], "Round of 16", "2027-01-24") for m in sorted(r16)]
    ko += [(45, "W37", "W38", "Quarter-finals", "2027-01-28"),   # regs Art. 9.10
           (46, "W39", "W40", "Quarter-finals", "2027-01-28"),
           (47, "W41", "W42", "Quarter-finals", "2027-01-29"),
           (48, "W43", "W44", "Quarter-finals", "2027-01-29"),
           (49, "W45", "W46", "Semi-finals", "2027-02-01"),      # regs Art. 9.11
           (50, "W47", "W48", "Semi-finals", "2027-02-02"),
           (51, "W49", "W50", "Final", "2027-02-05")]            # regs Art. 9.12
    for m, h, a, rnd, date in ko:
        fixtures.append({"match": m, "home": h, "away": a, "round": rnd,
                         "date": date, "venue": "Riyadh"})

    return {"format": dict(_AC_FORMAT),
            "teams": [t for g in groups for t in g["teams"]],
            "groups": groups, "fixtures": fixtures,
            "venues": [{"name": "King Fahd International Stadium",
                        "city": "Riyadh", "country": "SA"}]}


# ---------------------------------------------------------------------------
# Panel + fit (mirrored VERBATIM from tests/sim/test_conditioning_2026.py /
# scripts/capture_wc_golden.py, extended to the 24 AC bracket teams)
# ---------------------------------------------------------------------------
def _tiny_cfg() -> dict:
    """Production config with ``strength_prior`` pinned OFF (house pattern for tiny
    synthetic fits) — verbatim from ``tests/sim/test_conditioning_2026.py``."""
    cfg = load_config()
    sp = {**cfg["model"].get("strength_prior", {}), "enabled": False}
    return {**cfg, "model": {**cfg["model"], "strength_prior": sp}}


def _bracket_team_history(teams: list[str]) -> pd.DataFrame:
    """Minimal pre-cutoff friendly history giving EVERY bracket team a couple of
    played matches (all 1-1 draws on unique early-2025 dates) — verbatim from
    ``tests/sim/test_conditioning_2026.py``."""
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


def _played_row(home: str, away: str, date: str, hg: int, ag: int) -> pd.DataFrame:
    """One played AC group result, city matching the draw's venue so its
    ``match_id`` equals the ingested schedule row's — the production overlay."""
    return pd.DataFrame([
        (date, home, away, hg, ag, "AFC Asian Cup", "Riyadh", "Saudi Arabia", False),
    ], columns=["date", "home_team", "away_team", "home_score", "away_score",
                "tournament", "city", "country", "neutral"])


def _sim(tournament: dict, post, store, cfg: dict, cutoff: str):
    """One conditioned run through the REAL production entry point ``sim.run.simulate``."""
    simcfg = SimConfig(tournament=tournament, config=cfg, **_SIM)
    return simulate(cutoff, post, store, simcfg)


@pytest.fixture(scope="module")
def ac(tmp_path_factory):
    """The acceptance harness: validated AC document, seeded store (history +
    ingested schedule), REAL tiny ADVI posterior over exactly the 24 bracket
    teams, and the BASELINE (pre-matchday-1) sim. Assertions here make any
    setup breakage an ERROR on every test — a hard FAIL, never a skip."""
    tournament = _ac_tournament()
    validate_tournament(tournament)          # the formatted-branch validator gate

    store = BitemporalStore(root=tmp_path_factory.mktemp("ac2027-store"))
    _write_results(store, _bracket_team_history(list(tournament["teams"])))
    n = ingest_wc_group_fixtures(tournament, store, observed_at=_MD_DATES[0])
    assert n == 36, f"expected the 36 AC group fixtures ingested, got {n}"

    cfg = _tiny_cfg()
    post = fit(_C0, store, backend="advi", draws=120, seed=0, advi_iters=300,
               config=cfg)
    assert set(post.teams) == set(tournament["teams"]), (
        "the tiny posterior must cover EXACTLY the 24 AC bracket teams")

    baseline = _sim(tournament, post, store, cfg, _C0)
    return SimpleNamespace(tournament=tournament, store=store, cfg=cfg, post=post,
                           baseline=baseline)


# ---------------------------------------------------------------------------
# Shape: the formatted document itself
# ---------------------------------------------------------------------------
def test_document_validates_as_ac_shape(ac):
    """51 matches: 36 group + 15 knockout, third_place_match=False — the F1 shape,
    accepted by the formatted validator branch (already run in the fixture)."""
    fmt = tournament_format(ac.tournament)
    assert fmt["third_place_match"] is False
    assert fmt["best_thirds"] == 4 and fmt["tiebreak_order"] == "afc_2027"
    fixtures = ac.tournament["fixtures"]
    group_fx = [f for f in fixtures if f.get("match") is None]
    ko_fx = [f for f in fixtures if f.get("match") is not None]
    assert (len(group_fx), len(ko_fx)) == (36, 15)
    assert len(fixtures) == 51


# ---------------------------------------------------------------------------
# Markets: the 11-column public contract
# ---------------------------------------------------------------------------
def test_eleven_canonical_market_columns(ac):
    assert list(ac.baseline.progression.columns) == _EXPECTED_COLUMNS
    assert list(ac.baseline.se.columns) == _EXPECTED_COLUMNS
    assert list(ac.baseline.progression.index) == list(ac.baseline.se.index)


def test_advance_equals_reach_r16_values_and_ses(ac):
    """In a 4-round bracket the deepest KO depth IS the R16, so entering the
    knockouts and reaching the R16 are the same event — values AND SEs must be
    IDENTICAL arrays (F8/F13), not merely close."""
    prog, se = ac.baseline.progression, ac.baseline.se
    assert np.array_equal(prog["advance_from_group"].to_numpy(),
                          prog["reach_r16"].to_numpy())
    assert np.array_equal(se["advance_from_group"].to_numpy(),
                          se["reach_r16"].to_numpy())


def test_group_places_partition_and_champion_sums_to_one(ac):
    prog = ac.baseline.progression
    places = prog[["first", "second", "third", "out"]].sum(axis=1).to_numpy()
    assert np.allclose(places, 1.0, atol=1e-9), "group places must partition each team"
    assert np.isclose(prog["champion"].sum(), 1.0, atol=1e-9)
    assert np.array_equal(prog["win_group"].to_numpy(), prog["first"].to_numpy())


def test_sixteen_r16_entrants_thirds_placed_and_finite_tail(ac):
    """Every sim advances EXACTLY 16 teams (6x2 + the best-4 thirds), so the
    advance column sums to 16 — structural proof the 4 third slots were actually
    filled from the table. random_tail_rate is a finite diagnostic."""
    prog = ac.baseline.progression
    assert np.isclose(prog["advance_from_group"].sum(), 16.0, atol=1e-6)
    vals = prog.to_numpy()
    assert np.isfinite(vals).all() and (vals >= 0).all() and (vals <= 1).all()
    assert math.isfinite(ac.baseline.random_tail_rate)
    assert 0.0 <= ac.baseline.random_tail_rate <= 1.0


def test_progression_coherence_gate_on_raw_floats(ac):
    """The dashboard coherence gate consumes RAW float markets (schema.py:15) —
    feed it exactly that, per team, over the full published ladder (F8)."""
    for team, row in ac.baseline.progression.iterrows():
        validate_progression_coherence({k: float(row[k]) for k in _LADDER})


# ---------------------------------------------------------------------------
# Run-level conditioning canary (positive control + leakage byte-identity)
# ---------------------------------------------------------------------------
def test_run_level_conditioning_canary_with_positive_control(ac):
    """(a) baseline pre-MD1; (b) a played MD1 result moves the winner's
    advance strictly UP, the loser's strictly DOWN, and changes the champion
    distribution (positive control); (c) a result dated AFTER the cutoff leaves
    both output frames byte-identical (the leakage canary (b) licenses)."""
    p0 = ac.baseline

    # (b) The hosts' opener, played 5-0, dated matchday 1 (BEFORE cutoff _C1).
    _write_results(ac.store, _played_row(_HOME, _AWAY, _MD_DATES[0], 5, 0))

    # The played row is in the leakage-safe played set at _C1 — the exact set
    # the conditioning consumes (and the schedule->result overlay won the
    # store's deterministic tie-break: one row, real score, not the NaN row).
    played = _played_as_of(ac.store, _C1)
    hit = played[(played["home_team"] == _HOME) & (played["away_team"] == _AWAY)
                 & (played["date"] == pd.Timestamp(_MD_DATES[0]))]
    assert len(hit) == 1, "the played opener must be played-as-of the cutoff"
    assert (int(hit.iloc[0]["home_score"]), int(hit.iloc[0]["away_score"])) == (5, 0)

    p1 = _sim(ac.tournament, ac.post, ac.store, ac.cfg, _C1)
    adv0, adv1 = p0.progression["advance_from_group"], p1.progression["advance_from_group"]
    assert adv1.loc[_HOME] > adv0.loc[_HOME], (
        f"winner advance did not rise: {adv0.loc[_HOME]:.4f} -> {adv1.loc[_HOME]:.4f}")
    assert adv1.loc[_AWAY] < adv0.loc[_AWAY], (
        f"loser advance did not fall: {adv0.loc[_AWAY]:.4f} -> {adv1.loc[_AWAY]:.4f}")
    assert not p1.progression["champion"].equals(p0.progression["champion"]), (
        "a played group result must move the champion distribution")
    # The structural identity holds under conditioning too.
    assert np.array_equal(p1.progression["advance_from_group"].to_numpy(),
                          p1.progression["reach_r16"].to_numpy())
    assert np.array_equal(p1.se["advance_from_group"].to_numpy(),
                          p1.se["reach_r16"].to_numpy())

    # (c) A dramatic result dated AFTER the cutoff (matchday 2): if any layer
    # leaked it, the hosts' numbers would crater. Byte-identical or bust.
    _write_results(ac.store, _played_row(_HOME, "TeamA2", _MD_DATES[1], 0, 4))
    p1_mut = _sim(ac.tournament, ac.post, ac.store, ac.cfg, _C1)
    assert p1_mut.progression.equals(p1.progression), (
        "post-cutoff result changed the as-of-cutoff progression — leakage")
    assert p1_mut.se.equals(p1.se), (
        "post-cutoff result changed the as-of-cutoff SEs — leakage")
