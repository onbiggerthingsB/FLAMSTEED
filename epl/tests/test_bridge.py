"""The bridge, the Elo arm and the nulls (plan v2 T7).

What these tests are actually for
---------------------------------
`epl.bridge` exists so the retrospective's three arms differ in exactly one
place — how a fixture becomes an outcome — and in nothing else. That makes the
comparison meaningful only if three things are true, and each is a test here:

1. **The bridge is point-in-time.** It is an empirical conditional estimated
   from played matches, which is precisely the kind of object that leaks if the
   filter lives in the caller. So the filter lives in `fit`, and the test moves
   a result across the cutoff and demands the estimate not notice — paired with
   the positive control that moving a result on the *other* side of the cutoff
   does move it.
2. **The DC-WDL arm is the DC arm's 1X2 and nothing more.** If the bridge arm's
   outcome marginals drifted from the native arm's, the "does native scoreline
   structure buy anything" contrast would be measuring two differences at once.
   The test compares per-fixture 1X2 frequencies within cluster SE — and, as its
   positive control, asserts the *scoreline* laws differ, because if they did
   not there would be no contrast to measure.
3. **The arms share random numbers.** Slot `u[0]` decides the outcome in both
   bridge arms and slot `u[2]` draws the scoreline, so two arms that agree on
   1X2 must produce the *same* season, sim for sim. The test asserts that
   equality and then perturbs one arm's probabilities to prove the equality was
   not an artefact of the comparison.

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_bridge.py -q
"""

from __future__ import annotations

import concurrent.futures as cf
import dataclasses
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from epl import baseline, bridge as bridge_mod, freeze, leaguesim, ordlogit
from epl import anchor as anchor_mod, paths, particles, season as season_mod
from epl import table as table_mod, walk
from epl.schema import sort_for_walk_forward
from wcmodel.model import draw_api
from wcmodel.model.widening import inflate_predictive

SEED = 20260611
OPENER = "2026-08-21"

needs_archive = pytest.mark.skipif(
    not paths.MATCHES_PARQUET.exists(),
    reason="archive parquet absent (data/epl is gitignored)")


# ==========================================================================
# synthetic inputs
# ==========================================================================

def _synthetic_matches(n: int = 1200, *, seed: int = 7,
                       start: str = "2020-01-01") -> pd.DataFrame:
    """League-shaped played matches: a date, two goal counts, an H/D/A label."""
    rng = np.random.default_rng(seed)
    hg = rng.poisson(1.55, n)
    ag = rng.poisson(1.20, n)
    day0 = pd.Timestamp(start)
    dates = day0 + pd.to_timedelta(np.sort(rng.integers(0, 1400, n)), unit="D")
    ftr = np.where(hg > ag, "H", np.where(hg == ag, "D", "A"))
    return pd.DataFrame({"date": dates, "fthg": hg, "ftag": ag, "ftr": ftr,
                         "played": True})


@pytest.fixture(scope="module")
def rows() -> pd.DataFrame:
    return _synthetic_matches()


@pytest.fixture(scope="module")
def bridge(rows) -> "bridge_mod.EmpiricalBridge":
    return bridge_mod.EmpiricalBridge.fit(rows, "2024-01-01")


@pytest.fixture(scope="module")
def season():
    return season_mod.Season.load("2026/27")


@pytest.fixture(scope="module")
def state(season):
    return season.at(OPENER)


def _book(clubs, n_particles=16, *, spread="ladder", provisional=(), alpha=0.5):
    """A hand-built `ParticleBook`; `spread="flat"` makes every particle equal."""
    clubs = tuple(clubs)
    n_teams, n_draws = len(clubs), n_particles
    ladder = np.linspace(-0.20, 0.20, n_teams)
    att = np.repeat(ladder[:, None], n_draws, axis=1)
    defe = np.repeat(ladder[:, None], n_draws, axis=1)
    if spread == "ladder":
        # A per-particle tilt, so the particles are not interchangeable.
        tilt = np.linspace(-0.15, 0.15, n_draws)
        att = att + tilt[None, :]
    elif spread != "flat":
        raise ValueError(spread)
    return particles.ParticleBook(
        teams=clubs, idx={c: i for i, c in enumerate(clubs)},
        att=att, defe=defe,
        mu=np.zeros(n_draws), home_adv=np.full(n_draws, 0.25),
        rho=np.full(n_draws, -0.03),
        sigma_att=np.full(n_draws, 0.4), sigma_def=np.full(n_draws, 0.4),
        provisional=frozenset(provisional), cold_start=frozenset(provisional),
        likelihood="dixon_coles", alpha=alpha,
        max_goals=particles.PRODUCTION_MAX_GOALS, cfg_hash="test-cfg",
    )


def _plain_fixture(home: str, away: str, ordinal: int = 0):
    return leaguesim.FixturePlan(
        fixture_id=f"2627:{home}:{away}", ordinal=ordinal,
        home_key=home, away_key=away, home_idx=0, away_idx=1, result=None)


def _one_x_two_frequencies(run, fixture_id):
    """Per-fixture simulated H/D/A frequencies and their cluster SEs."""
    plan = run.plan
    ordinal = plan.fixtures[plan.position_of(fixture_id)].ordinal
    column = {int(o): j for j, o
              in enumerate(run.retained_rows.fixture_ordinals.tolist())}[ordinal]
    goals = run.retained_rows.scorelines[:, column, :].astype(np.int64)
    indicators = np.stack([(goals[:, 0] > goals[:, 1]).astype(float),
                           (goals[:, 0] == goals[:, 1]).astype(float),
                           (goals[:, 0] < goals[:, 1]).astype(float)], axis=1)
    se = np.array([leaguesim.cluster_se(indicators[:, k], run.retained_rows.particle)
                   for k in range(3)])
    return indicators.mean(axis=0), se


def _scoreline_frequencies(run, fixture_id, side):
    plan = run.plan
    ordinal = plan.fixtures[plan.position_of(fixture_id)].ordinal
    column = {int(o): j for j, o
              in enumerate(run.retained_rows.fixture_ordinals.tolist())}[ordinal]
    goals = run.retained_rows.scorelines[:, column, :].astype(np.int64)
    flat = np.clip(goals[:, 0], 0, side - 1) * side + np.clip(goals[:, 1], 0, side - 1)
    return np.bincount(flat, minlength=side * side) / len(flat)


# ==========================================================================
# 1. the bridge is point-in-time (plan v2 D18)
# ==========================================================================

def test_bridge_is_point_in_time(rows):
    cutoff = "2022-06-01"
    day = pd.Timestamp(cutoff).normalize()

    fitted = bridge_mod.EmpiricalBridge.fit(rows, cutoff)
    pre_only = bridge_mod.EmpiricalBridge.fit(
        rows.loc[pd.to_datetime(rows["date"]) < day], cutoff)

    # The filter is in `fit`, not in the caller.
    assert fitted.n_rows == int((pd.to_datetime(rows["date"]) < day).sum())
    assert fitted.n_rows < len(rows)                    # the filter really bites
    assert np.array_equal(fitted.counts, pre_only.counts)
    assert fitted.hash == pre_only.hash

    # NEGATIVE CONTROL: rewriting a post-cutoff result changes nothing.
    after = rows.copy()
    post = np.flatnonzero(pd.to_datetime(after["date"]).to_numpy() >= day.to_datetime64())
    after.iloc[post[0], after.columns.get_loc("fthg")] = 9
    after.iloc[post[0], after.columns.get_loc("ftag")] = 0
    after.iloc[post[0], after.columns.get_loc("ftr")] = "H"
    unmoved = bridge_mod.EmpiricalBridge.fit(after, cutoff)
    assert np.array_equal(unmoved.counts, fitted.counts)
    assert unmoved.hash == fitted.hash

    # POSITIVE CONTROL: rewriting a pre-cutoff result does move it.
    before = rows.copy()
    pre = np.flatnonzero(pd.to_datetime(before["date"]).to_numpy() < day.to_datetime64())
    before.iloc[pre[0], before.columns.get_loc("fthg")] = 9
    before.iloc[pre[0], before.columns.get_loc("ftag")] = 0
    before.iloc[pre[0], before.columns.get_loc("ftr")] = "H"
    moved = bridge_mod.EmpiricalBridge.fit(before, cutoff)
    assert not np.array_equal(moved.counts, fitted.counts)
    assert moved.hash != fitted.hash

    # A later cutoff is a different estimate, and says so.
    later = bridge_mod.EmpiricalBridge.fit(rows, "2023-06-01")
    assert later.n_rows > fitted.n_rows
    assert later.hash != fitted.hash


def test_bridge_conditional_pmfs_sum_to_one_and_respect_outcome(bridge):
    side = bridge.max_goals + 1
    home_goals = np.repeat(np.arange(side), side)
    away_goals = np.tile(np.arange(side), side)

    assert bridge.pmf.shape == (3, side * side)
    np.testing.assert_allclose(bridge.pmf.sum(axis=1), 1.0, atol=1e-12)
    np.testing.assert_allclose(bridge.cdf[:, -1], 1.0, atol=0.0)

    # H puts mass only where the home side scored more, and so on down.
    assert bridge.pmf[0][home_goals <= away_goals].max() == 0.0
    assert bridge.pmf[0][home_goals > away_goals].sum() == pytest.approx(1.0)
    assert bridge.pmf[1][home_goals != away_goals].max() == 0.0
    assert bridge.pmf[1][home_goals == away_goals].sum() == pytest.approx(1.0)
    assert bridge.pmf[2][home_goals >= away_goals].max() == 0.0
    assert bridge.pmf[2][home_goals < away_goals].sum() == pytest.approx(1.0)


def test_bridge_sampler_reproduces_its_own_pmf(bridge):
    rng = np.random.default_rng(11)
    n = 60_000
    side = bridge.max_goals + 1
    for code in (0, 1, 2):
        outcome = np.full(n, code)
        hg, ag = bridge.sample(outcome, rng.random(n))
        # Never off-support: the sampled scoreline always realises the outcome.
        assert {0: (hg > ag), 1: (hg == ag), 2: (hg < ag)}[code].all()
        empirical = np.bincount((hg.astype(np.int64) * side + ag).astype(np.int64),
                                minlength=side * side) / n
        se = np.sqrt(np.clip(bridge.pmf[code] * (1 - bridge.pmf[code]), 0, None) / n)
        big = bridge.pmf[code] * n >= 30
        assert np.all(np.abs(empirical - bridge.pmf[code])[big] <= 5 * se[big])


def test_bridge_refuses_a_thin_outcome_class(rows):
    draws = rows.loc[rows["ftr"] == "D"].head(3)
    thin = pd.concat([rows.loc[rows["ftr"] != "D"], draws], ignore_index=True)
    with pytest.raises(bridge_mod.BridgeError, match="draw"):
        bridge_mod.EmpiricalBridge.fit(thin, "2024-01-01")


def test_bridge_refuses_a_label_that_contradicts_the_scoreline(rows):
    lying = rows.copy()
    lying.iloc[0, lying.columns.get_loc("ftr")] = (
        "A" if lying.iloc[0]["ftr"] != "A" else "H")
    with pytest.raises(bridge_mod.BridgeError, match="ftr"):
        bridge_mod.EmpiricalBridge.fit(lying, "2024-01-01")


# ==========================================================================
# 2. the DC-WDL arm is the DC arm's 1X2 (plan v2 D18)
# ==========================================================================

def test_dc_wdl_1x2_marginals_match_dc_native_1x2_within_se(state, bridge):
    book = _book(state.clubs, n_particles=20, provisional=("coventry",))
    n_sims = 4_000

    native = leaguesim.simulate("dc_native", state, book, n_sims, SEED, 1_000)
    wdl = leaguesim.simulate("dc_wdl_bridge", state,
                             bridge_mod.DCWDLProvider(book, bridge),
                             n_sims, SEED, 1_000)

    provisional = [f.fixture_id for f in state.fixtures.values()
                   if "coventry" in (f.home_key, f.away_key)][:2]
    plain = [f.fixture_id for f in state.fixtures.values()
             if "coventry" not in (f.home_key, f.away_key)][:4]
    assert provisional and plain

    for fid in provisional + plain:
        p_native, se_native = _one_x_two_frequencies(native, fid)
        p_wdl, se_wdl = _one_x_two_frequencies(wdl, fid)
        se = np.maximum(np.hypot(se_native, se_wdl),
                        np.sqrt(2 * 0.25 / n_sims))
        assert np.all(np.abs(p_native - p_wdl) <= 4 * se), fid

    # POSITIVE CONTROL: the scoreline laws are NOT the same object. The bridge
    # spreads a home win over the league's empirical home-win scorelines, the
    # DC grid over this fixture's own — if these agreed there would be no
    # contrast for the retrospective to measure.
    side = book.max_goals + 1
    gaps = [np.abs(_scoreline_frequencies(native, fid, side)
                   - _scoreline_frequencies(wdl, fid, side)).max()
            for fid in plain]
    assert max(gaps) > 0.01


def test_dc_wdl_widening_branch_reproduces_the_production_1x2(bridge):
    """The D12 mixture, restated at the 1X2 level — exactly, not within SE.

    The engine-level comparison above cannot see this: it compares the bridge
    arm against the native arm, and both would move together if the branch were
    dropped from both. This one compares against what PRODUCTION publishes for a
    provisional fixture, which is the property D12 is actually about.
    """
    clubs = tuple(f"c{i:02d}" for i in range(20))
    book = _book(clubs, n_particles=20, provisional=("c19",))
    provider = bridge_mod.DCWDLProvider(book, bridge)
    fixture = _plain_fixture("c00", "c19")

    one_x_two, widened = provider.laws_for(fixture)
    assert widened is not None, "a provisional fixture must carry the branch"

    grids, _ = particles.fixture_grids(*book.rates("c00", "c19"), book.rho,
                                       book.max_goals)
    produced = inflate_predictive(particles.mean_grid(grids), is_provisional=True,
                                  strength=book.alpha)
    published = draw_api.grid_one_x_two(produced)
    reference = np.array([published["home"], published["draw"], published["away"]])

    mixture = (1 - book.alpha) * one_x_two.mean(axis=0) + book.alpha * widened
    np.testing.assert_allclose(mixture, reference, rtol=0, atol=1e-12)

    # POSITIVE CONTROL: without the branch the arm would publish something else,
    # so the equality above is a property of the mixture and not of the grid.
    unwidened = one_x_two.mean(axis=0)
    assert np.abs(unwidened - reference).max() > 0.02

    # And the SAMPLER realises the mixture, not the unwidened law.
    n = 200_000
    u = np.random.default_rng(101).random((3, n))
    hg, ag = provider.sample(fixture, np.arange(n) % book.n_particles, u)
    empirical = np.array([float((hg > ag).mean()), float((hg == ag).mean()),
                          float((hg < ag).mean())])
    se = np.sqrt(reference * (1 - reference) / n)
    assert np.all(np.abs(empirical - reference) <= 5 * se)
    assert np.any(np.abs(empirical - unwidened) > 5 * se)


def test_dc_wdl_provider_is_a_scoreline_provider_and_names_its_bridge(state, bridge):
    book = _book(state.clubs, n_particles=8)
    provider = bridge_mod.DCWDLProvider(book, bridge)
    assert isinstance(provider, leaguesim.ScorelineProvider)
    assert provider.name == "dc_wdl_bridge"
    assert provider.n_particles == 8
    assert provider.bridge_hash == bridge.hash
    assert provider.content_hash() != book.content_hash()

    run = leaguesim.simulate("dc_wdl_bridge", state, provider, 400, SEED, 200)
    table_mod.check_doubly_stochastic(run.matrix)
    assert run.envelope["bridge_hash"] == bridge.hash
    assert run.envelope["arm"] == "dc_wdl_bridge"


# ==========================================================================
# 3. the Elo arm (plan v2 D18)
# ==========================================================================

def _synthetic_history(n: int = 900, *, seed: int = 3) -> pd.DataFrame:
    """`Anchor.history`-shaped rows: a date, an Elo edge, an H/D/A label."""
    rng = np.random.default_rng(seed)
    edge = rng.normal(0.0, 140.0, n)
    eta = 2.0 * edge / 400.0 + 0.25
    p_home = 1.0 / (1.0 + np.exp(-(eta - 0.4)))
    p_away = 1.0 / (1.0 + np.exp(-(-eta - 0.4)))
    draw = np.clip(1.0 - p_home - p_away, 1e-6, None)
    probs = np.stack([p_home, draw, p_away], axis=1)
    probs = probs / probs.sum(axis=1, keepdims=True)
    codes = np.array([rng.choice(3, p=row) for row in probs])
    dates = pd.Timestamp("2020-01-01") + pd.to_timedelta(
        np.sort(rng.integers(0, 1400, n)), unit="D")
    return pd.DataFrame({"date": dates, "elo_diff_pre": edge,
                         "ftr": np.array(["H", "D", "A"])[codes]})


def _anchor_state(ratings: dict[str, float], cutoff) -> anchor_mod.AnchorState:
    teams = tuple(sorted(ratings))
    values = np.array([ratings[t] for t in teams])
    return anchor_mod.AnchorState(cutoff=pd.Timestamp(cutoff), ratings=dict(ratings),
                                  teams=teams, mean=float(values.mean()),
                                  sd=float(values.std()))


def test_elo_provider_static_and_uses_only_pre_cutoff_history(bridge):
    history = _synthetic_history()
    cutoff = "2022-06-01"
    day = pd.Timestamp(cutoff).normalize()
    ratings = {"alpha": 1650.0, "bravo": 1500.0, "charlie": 1420.0}
    anchor_state = _anchor_state(ratings, cutoff)
    fixtures = [_plain_fixture("alpha", "bravo", 0),
                _plain_fixture("charlie", "alpha", 1)]

    provider = bridge_mod.EloOutcomeProvider.fit(anchor_state, history, fixtures,
                                                 bridge)
    trimmed = bridge_mod.EloOutcomeProvider.fit(
        anchor_state, history.loc[pd.to_datetime(history["date"]) < day],
        fixtures, bridge)
    assert provider.n_fit_rows == int((pd.to_datetime(history["date"]) < day).sum())
    assert provider.n_fit_rows < len(history)
    np.testing.assert_array_equal(provider.probs, trimmed.probs)
    assert provider.content_hash() == trimmed.content_hash()

    # NEGATIVE CONTROL: a post-cutoff result cannot move the head.
    after = history.copy()
    post = np.flatnonzero(pd.to_datetime(after["date"]).to_numpy() >= day.to_datetime64())
    after.iloc[post[:50], after.columns.get_loc("ftr")] = "A"
    unmoved = bridge_mod.EloOutcomeProvider.fit(anchor_state, after, fixtures, bridge)
    np.testing.assert_array_equal(unmoved.probs, provider.probs)

    # POSITIVE CONTROL: a pre-cutoff result does.
    before = history.copy()
    pre = np.flatnonzero(pd.to_datetime(before["date"]).to_numpy() < day.to_datetime64())
    before.iloc[pre[:50], before.columns.get_loc("ftr")] = "A"
    moved = bridge_mod.EloOutcomeProvider.fit(anchor_state, before, fixtures, bridge)
    assert not np.allclose(moved.probs, provider.probs)

    # STATIC: the ratings do not move with the simulated season, so the law a
    # fixture is sampled from cannot depend on which particle priced it.
    u = np.random.default_rng(5).random((3, 500))
    a = provider.sample(fixtures[0], np.zeros(500, np.int16), u)
    b = provider.sample(fixtures[0], np.arange(500, dtype=np.int16) % 7, u)
    np.testing.assert_array_equal(a[0], b[0])
    np.testing.assert_array_equal(a[1], b[1])

    # And the head is the ordered logit on the rating difference, read straight.
    expected = ordlogit.predict(provider.params,
                                np.array([ratings["alpha"] - ratings["bravo"],
                                          ratings["charlie"] - ratings["alpha"]]))
    np.testing.assert_allclose(provider.probs, expected, rtol=0, atol=0)


@needs_archive
def test_elo_provider_reproduces_walk_forward_head_probs_at_a_block(bridge):
    matches = baseline.load_matches()
    frame = sort_for_walk_forward(matches.loc[matches["played"]])
    anchor = anchor_mod.Anchor(frame, freeze.frozen_elo_config())
    history = anchor.history
    dates = pd.to_datetime(history["date"]).dt.normalize().to_numpy()

    # A block that OPENS a day: there, "strictly earlier block" and the model
    # layer's day-floored `date < cutoff` select the same rows, so the two
    # objects are answerable against each other at all.
    chosen = None
    for rows_ in walk.groups(history["block"].to_numpy()):
        cut = int(rows_[0])
        if cut < 1_000 or len(rows_) < 5:
            continue
        if dates[:cut].max() < dates[cut]:
            chosen = (rows_, cut, pd.Timestamp(dates[cut]))
            break
    assert chosen is not None, "no day-opening block in the archive"
    block_rows, cut, cutoff = chosen

    want = np.zeros(len(history), bool)
    want[block_rows] = True
    reference, log = baseline.walk_forward_head(history, want)
    assert len(log) == 1 and log[0]["block_start_row"] == cut

    clubs = sorted(set(history["home_key"].iloc[block_rows])
                   | set(history["away_key"].iloc[block_rows]))
    anchor_state = anchor.state(cutoff, clubs)
    fixtures = [_plain_fixture(history["home_key"].iloc[r],
                               history["away_key"].iloc[r], i)
                for i, r in enumerate(block_rows)]

    provider = bridge_mod.EloOutcomeProvider.fit(anchor_state, history, fixtures,
                                                 bridge)
    assert provider.n_fit_rows == cut
    np.testing.assert_array_equal(provider.probs, reference[block_rows])


def test_arms_share_uniform_slots(state, bridge):
    """Common random numbers: agreeing on 1X2 means agreeing on the season."""
    book = _book(state.clubs, n_particles=8, spread="flat")
    home, away = state.clubs[0], state.clubs[1]
    fixture = _plain_fixture(home, away)

    dc = bridge_mod.DCWDLProvider(book, bridge)
    probabilities = particles.fixture_cdfs(book, home, away).one_x_two[0]
    elo = bridge_mod.EloOutcomeProvider(
        probs=np.array([probabilities]), fixture_ids=(fixture.fixture_id,),
        bridge=bridge, params=None, cutoff="2026-08-21", n_fit_rows=0,
        n_particles=book.n_particles)

    n = 3_000
    u = leaguesim.streams(SEED, 0, fixture.ordinal).random((3, n))
    pidx = np.arange(n, dtype=np.int16) % book.n_particles

    hg_dc, ag_dc = dc.sample(fixture, pidx, u)
    hg_elo, ag_elo = elo.sample(fixture, pidx, u)
    np.testing.assert_array_equal(hg_dc, hg_elo)
    np.testing.assert_array_equal(ag_dc, ag_elo)

    # POSITIVE CONTROL: the equality is the shared slot, not a blind comparison.
    tilted = bridge_mod.EloOutcomeProvider(
        probs=np.array([[0.05, 0.10, 0.85]]), fixture_ids=(fixture.fixture_id,),
        bridge=bridge, params=None, cutoff="2026-08-21", n_fit_rows=0,
        n_particles=book.n_particles)
    hg_t, ag_t = tilted.sample(fixture, pidx, u)
    assert not np.array_equal(hg_dc, hg_t)


def test_elo_provider_runs_through_the_engine(state, bridge):
    history = _synthetic_history()
    ratings = {club: 1500.0 + 12.0 * i for i, club in enumerate(state.clubs)}
    anchor_state = _anchor_state(ratings, OPENER)
    provider = bridge_mod.EloOutcomeProvider.fit(
        anchor_state, history, list(state.fixtures.values()), bridge,
        n_particles=8)
    assert isinstance(provider, leaguesim.ScorelineProvider)

    run = leaguesim.simulate("elo_wdl_bridge", state, provider, 400, SEED, 200)
    table_mod.check_doubly_stochastic(run.matrix)
    assert run.envelope["bridge_hash"] == bridge.hash
    assert run.envelope["widening_mode"] == "none"
    assert run.envelope["effective_posterior_hash"] is None
    # Every club still plays 38 matches and the ladder still adds up.
    np.testing.assert_array_equal(run.retained_rows.points.shape, (400, 20))


def test_bridge_arms_are_deterministic_and_parallel_safe(state, bridge):
    """D10's byte-identical requirement, for the two arms this task adds.

    Both carry derived per-fixture state that is rebuilt in a worker rather than
    shipped to it, so "serial equals parallel" is a property of THEIR pickling,
    not only of the engine's chunking — and a broken `__setstate__` would
    otherwise surface for the first time inside a retrospective.
    """
    book = _book(state.clubs, n_particles=8, provisional=("coventry",))
    ratings = {club: 1500.0 + 9.0 * i for i, club in enumerate(state.clubs)}
    arms = {
        "dc_wdl_bridge": bridge_mod.DCWDLProvider(book, bridge),
        "elo_wdl_bridge": bridge_mod.EloOutcomeProvider.fit(
            _anchor_state(ratings, OPENER), _synthetic_history(),
            list(state.fixtures.values()), bridge, n_particles=8),
    }
    for arm, provider in arms.items():
        serial = leaguesim.simulate(arm, state, provider, 400, SEED, 200)
        again = leaguesim.simulate(arm, state, provider, 400, SEED, 200)
        assert serial.digest() == again.digest(), arm
        with cf.ProcessPoolExecutor(max_workers=2) as pool:
            parallel = leaguesim.simulate(arm, state, provider, 400, SEED, 200,
                                          executor=pool)
        assert parallel.digest() == serial.digest(), arm
        assert (parallel.retained_rows.scorelines.tobytes()
                == serial.retained_rows.scorelines.tobytes()), arm
        # positive control: the digest is sensitive to what it is meant to pin.
        assert leaguesim.simulate(arm, state, provider, 400, SEED + 1, 200
                                  ).digest() != serial.digest(), arm


def test_elo_provider_refuses_a_fixture_it_did_not_price(bridge):
    history = _synthetic_history()
    ratings = {"alpha": 1600.0, "bravo": 1500.0}
    provider = bridge_mod.EloOutcomeProvider.fit(
        _anchor_state(ratings, "2022-06-01"), history,
        [_plain_fixture("alpha", "bravo")], bridge)
    with pytest.raises(bridge_mod.BridgeError, match="alien"):
        provider.sample(_plain_fixture("alien", "bravo"),
                        np.zeros(4, np.int16), np.zeros((3, 4)) + 0.5)


# ==========================================================================
# 4. the nulls
# ==========================================================================

def test_flat_matrix_is_uniform_and_doubly_stochastic():
    matrix = bridge_mod.flat_matrix(20)
    assert matrix.shape == (20, 20)
    assert np.all(matrix == 1.0 / 20.0)
    table_mod.check_doubly_stochastic(matrix)


def _played_through_matchday(season, last_matchday: int):
    """A `SeasonState` with matchdays 1..N in the results ledger."""
    played = [f for f in season.fixtures if f.matchday <= last_matchday]
    rng = np.random.default_rng(19)
    rows = []
    for f in played:
        rows.append({
            "fixture_id": f.fixture_id,
            "date_played": f.base_date.isoformat(),
            "hg": int(rng.integers(0, 4)), "ag": int(rng.integers(0, 4)),
            "source": "test", "observed_at": f.base_date.isoformat(), "note": "",
        })
    cutoff = max(f.base_date for f in played) + dt.timedelta(days=1)
    loaded = dataclasses.replace(season, results=tuple(rows))
    return loaded.at(cutoff.isoformat())


def test_ppg_none_at_opener_pointmass_after_mw3(season, state):
    assert bridge_mod.ppg_pointmass(state) is None

    after = _played_through_matchday(season, 3)
    assert min(row.played for row in after.table_so_far.values()) == 3

    matrix = bridge_mod.ppg_pointmass(after)
    assert matrix is not None
    assert matrix.shape == (20, 20)
    table_mod.check_doubly_stochastic(matrix)
    # A point mass: 18 clubs certain, one exactly-tied pair sharing two rungs
    # half and half. Both numbers are deterministic — the fixture list is
    # hash-pinned and the scoreline RNG is seeded.
    assert int(np.sum(matrix == 1.0)) == 18
    assert int((matrix > 0).sum(axis=1).max()) == 2

    # It really is the points-per-game extrapolation: the club with the best
    # PPG is the one it puts first.
    best = max(after.table_so_far,
               key=lambda c: (after.table_so_far[c].pts / after.table_so_far[c].played,
                              after.table_so_far[c].gd, after.table_so_far[c].gf))
    assert matrix[list(after.clubs).index(best), 0] > 0.0

    # Two rounds is not enough to extrapolate from.
    assert bridge_mod.ppg_pointmass(_played_through_matchday(season, 2)) is None


# ==========================================================================
# 6. the per-particle draw is load-bearing (D1 through D18)
# ==========================================================================
#
# Verifier finding (d): `DCWDLProvider.sample` indexes `one_x_two[particle_idx]`,
# and NOTHING downstream would notice if it averaged over particles instead —
# the per-fixture 1X2 MARGINAL is identical either way, so every marginal-parity
# test in this file passes under the mutant. What the mean mixture destroys is
# the JOINT: under it every simulated season is priced at the same 1X2, the
# posterior draw stops deciding anything, and the parameter uncertainty D1
# exists to carry never reaches the title and relegation tails.
#
# So the guard is conditional: per-particle law variance > 0, and realised 1X2
# frequencies that differ ACROSS particles by more than binomial noise.

def _particle_spread_book(clubs, home, away, *, n_particles=16, swing=0.6):
    """A book whose particles genuinely disagree about ONE fixture's 1X2.

    The `_book` ladder tilts every club's attack together, which moves the total
    goal rate but barely moves 1X2. Here only the home club's attack moves, so
    the particles disagree about the OUTCOME and not merely the score.
    """
    clubs = tuple(clubs)
    att = np.zeros((len(clubs), n_particles))
    defe = np.zeros((len(clubs), n_particles))
    att[clubs.index(home)] = np.linspace(-swing, swing, n_particles)
    return particles.ParticleBook(
        teams=clubs, idx={c: i for i, c in enumerate(clubs)},
        att=att, defe=defe, mu=np.zeros(n_particles),
        home_adv=np.full(n_particles, 0.25), rho=np.full(n_particles, -0.03),
        sigma_att=np.full(n_particles, 0.4), sigma_def=np.full(n_particles, 0.4),
        provisional=frozenset(), cold_start=frozenset(),
        likelihood="dixon_coles", alpha=0.0,
        max_goals=particles.PRODUCTION_MAX_GOALS, cfg_hash="test-spread")


class _MeanMixtureMutant(bridge_mod.DCWDLProvider):
    """The mutant the guard must catch: every season priced at the particle MEAN."""

    def sample(self, fixture, particle_idx, u):
        one_x_two, widened = self.laws_for(fixture)
        n = len(np.asarray(particle_idx))
        probs = np.repeat(one_x_two.mean(axis=0)[None, :], n, axis=0)
        if widened is not None:
            coin = np.asarray(u[1]) < self.book.alpha
            if coin.any():
                probs[coin] = widened
        return self.bridge.sample(
            bridge_mod._draw_outcome(probs, np.asarray(u[0])), np.asarray(u[2]))


def _home_win_homogeneity(run, fixture_id) -> float:
    """Pearson statistic for "every particle priced this fixture identically".

    ``sum_s (k_s - n_s p)^2 / (n_s p (1-p))`` over the S particles, which is
    chi-squared on S-1 df under that null. Large means the particles disagree —
    which is what a per-particle draw is FOR.
    """
    plan = run.plan
    ordinal = plan.fixtures[plan.position_of(fixture_id)].ordinal
    column = {int(o): j for j, o
              in enumerate(run.retained_rows.fixture_ordinals.tolist())}[ordinal]
    goals = run.retained_rows.scorelines[:, column, :].astype(np.int64)
    home_win = (goals[:, 0] > goals[:, 1]).astype(float)
    particle = run.retained_rows.particle
    n_particles = int(particle.max()) + 1

    counts = np.bincount(particle, minlength=n_particles).astype(float)
    wins = np.bincount(particle, weights=home_win, minlength=n_particles)
    p = float(home_win.mean())
    assert 0.0 < p < 1.0 and counts.min() > 0
    return float((((wins - counts * p) ** 2) / (counts * p * (1 - p))).sum())


def test_dc_wdl_prices_each_season_at_its_own_particle_not_at_the_mean(state, bridge):
    home, away = state.clubs[0], state.clubs[1]
    book = _particle_spread_book(state.clubs, home, away)
    provider = bridge_mod.DCWDLProvider(book, bridge)
    fixture_id = f"2627:{home}:{away}"
    plan_fixture = _plain_fixture(home, away)

    # 1. the laws themselves differ particle by particle
    laws, widened = provider.laws_for(plan_fixture)
    assert widened is None
    assert laws.shape == (book.n_particles, 3)
    assert laws.var(axis=0).max() > 1e-4, \
        "the engineered book must make the particles disagree"
    assert not np.allclose(laws, laws.mean(axis=0)[None, :])

    # 2. and the SEASONS realise that disagreement. Under the mean mixture the
    #    per-particle frequencies would differ only by binomial noise.
    n_sims, chunk = 3200, 800
    run = leaguesim.simulate("dc_wdl_bridge", state, provider, n_sims, SEED, chunk)
    real = _home_win_homogeneity(run, fixture_id)

    mutant = _MeanMixtureMutant(book, bridge)
    mutant_run = leaguesim.simulate("dc_wdl_bridge", state, mutant, n_sims, SEED,
                                    chunk)
    mutated = _home_win_homogeneity(mutant_run, fixture_id)

    from scipy.stats import chi2
    df = book.n_particles - 1
    assert float(chi2.sf(real, df)) < 1e-6, (
        f"per-particle 1X2 frequencies must differ beyond binomial noise "
        f"(statistic {real:.1f} on {df} df)")
    assert float(chi2.sf(mutated, df)) > 1e-3, (
        f"the mean-mixture mutant must look homogeneous (statistic "
        f"{mutated:.1f} on {df} df) — otherwise the test above is not "
        "measuring the per-particle draw")
    assert real > 20 * mutated

    # 3. and the two are different runs at the same seed, so the mutant is
    #    something this suite could otherwise have missed entirely.
    assert not np.array_equal(run.retained_rows.scorelines,
                              mutant_run.retained_rows.scorelines)
    # ...while their per-fixture MARGINALS agree, which is exactly why a
    # marginal test cannot catch it.
    freq, se = _one_x_two_frequencies(run, fixture_id)
    mutant_freq, _ = _one_x_two_frequencies(mutant_run, fixture_id)
    assert np.all(np.abs(freq - mutant_freq) <= 5 * np.maximum(se, 1e-12) + 0.02)
