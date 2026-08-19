"""The engine: keyed streams, stratified particles, coherence, MC error (plan v2 T5).

What these tests are actually for
---------------------------------
The engine is where a league-table forecast can go wrong invisibly. A dropped
uniform shifts every later fixture and nobody notices; a chunk boundary that
leaks into the stream key makes "20,000 sims" mean something different on a
different machine; a matrix whose columns do not sum to one is not a badly
calibrated forecast but an inadmissible one. So the tests here are mostly
*structural*: they pin the RNG contract, the decomposition of a run into chunks,
and the identities a simulated season cannot violate.

Every guard carries a positive control. The pinned-fixture test is worthless
unless the run's numbers can move at all, so it also asserts the matrix DOES
change when the pinned result changes. The kickoff-invariance test asserts a
result change moves the matrix. The identical-particles MC test is paired with a
strong-spread one, so "cluster SE equals binomial SE" cannot pass by the
estimator being blind.

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_leaguesim.py -q
"""

from __future__ import annotations

import concurrent.futures as cf
import dataclasses
import datetime as dt
import json

import numpy as np
import pytest

from epl import leaguesim, particles, season as season_mod, table as table_mod

# --------------------------------------------------------------------------
# synthetic inputs — the shape of a real issuance, none of the fit cost
# --------------------------------------------------------------------------

SEED = 20260611


@pytest.fixture(scope="module")
def season():
    return season_mod.Season.load("2026/27")


@pytest.fixture(scope="module")
def state(season):
    """The opener: 380 unplayed fixtures, 20 clubs, nothing played."""
    return season.at("2026-08-21")


def _book(clubs, n_particles=16, *, spread="none", provisional=(), alpha=0.5):
    """A `ParticleBook` built by hand, with league-shaped rates.

    `spread="champion"` makes particle ``s`` favour club ``s % T`` heavily, which
    is the only honest way to get a book whose between-particle variance
    dominates: the posterior draw, not the match randomness, decides the title.
    `spread="none"` gives every particle the SAME strengths, so all the variance
    is match randomness and the cluster SE must collapse onto the binomial one.
    """
    clubs = tuple(clubs)
    n_teams, n_draws = len(clubs), n_particles
    ladder = np.linspace(-0.20, 0.20, n_teams)
    att = np.repeat(ladder[:, None], n_draws, axis=1)
    defe = np.repeat(ladder[:, None], n_draws, axis=1)
    if spread == "champion":
        for s in range(n_draws):
            att[s % n_teams, s] += 0.40
            defe[s % n_teams, s] += 0.40
    elif spread != "none":
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


def _with_played(state, played: dict):
    """The same state with `played` results added (statuses kept consistent)."""
    merged = dict(state.played)
    merged.update(played)
    statuses = dict(state.statuses)
    for fid in played:
        statuses[fid] = season_mod.STATUS_PLAYED
    return dataclasses.replace(
        state,
        played=dict(sorted(merged.items())),
        unplayed=tuple(f for f in state.unplayed if f not in played),
        statuses=dict(sorted(statuses.items())),
    )


@pytest.fixture(scope="module")
def small_run(state):
    """One cheap reference run reused by the coherence tests."""
    book = _book(state.clubs, n_particles=16, provisional=("coventry",))
    return leaguesim.simulate("dc_native", state, book, 320, SEED, 128)


@pytest.fixture(scope="module")
def flat_run(state):
    """Every particle identical: all the variance is match randomness."""
    book = _book(state.clubs, n_particles=32, spread="none")
    return leaguesim.simulate("dc_native", state, book, 3200, SEED, 800)


@pytest.fixture(scope="module")
def spread_run(state):
    """The posterior draw decides the title: the outer leg dominates."""
    book = _book(state.clubs, n_particles=32, spread="champion")
    return leaguesim.simulate("dc_native", state, book, 3200, SEED, 800)


def _champion_se_ratios(run):
    """cluster SE / binomial SE for every non-degenerate champion market."""
    ratios = []
    for i, club in enumerate(run.clubs):
        p = run.matrix[i, 0]
        if not 0.02 < p < 0.98:
            continue
        ratios.append(run.consequences[club]["champion"]["se"]
                      / np.sqrt(p * (1 - p) / run.n_sims))
    return ratios


# ==========================================================================
# 1. the RNG contract (D14)
# ==========================================================================

def test_streams_are_pcg64_and_keyed_by_chunk_and_fixture():
    a = leaguesim.streams(SEED, 0, 7)
    again = leaguesim.streams(SEED, 0, 7)
    assert isinstance(a.bit_generator, np.random.PCG64), "the bit generator is pinned"

    first = a.random(8)
    assert np.array_equal(first, again.random(8)), "same key -> same stream"

    other_fixture = leaguesim.streams(SEED, 0, 8).random(8)
    other_chunk = leaguesim.streams(SEED, 1, 7).random(8)
    other_seed = leaguesim.streams(SEED + 1, 0, 7).random(8)
    assert not np.array_equal(first, other_fixture), "fixture ordinal is in the key"
    assert not np.array_equal(first, other_chunk), "chunk index is in the key"
    assert not np.array_equal(first, other_seed), "the seed is in the key"


def test_particle_index_is_i_mod_s_and_int16():
    idx = leaguesim.particle_index(10, 4)
    assert idx.dtype == np.int16
    assert idx.tolist() == [0, 1, 2, 3, 0, 1, 2, 3, 0, 1]


def test_particle_stratified_each_used_N_over_S_times(state):
    n_sims, n_particles = 320, 16
    book = _book(state.clubs, n_particles=n_particles)
    run = leaguesim.simulate("dc_native", state, book, n_sims, SEED, 128)

    counts = np.bincount(run.retained_rows.particle, minlength=n_particles)
    assert counts.tolist() == [n_sims // n_particles] * n_particles, (
        "stratification: every posterior draw is used exactly N/S times")
    # positive control: the stratification is a real constraint, not an artefact
    # of N and S happening to be equal.
    assert n_sims != n_particles


# ==========================================================================
# 2. determinism and the chunk decomposition (D14, §1 constraint)
# ==========================================================================

def test_determinism_byte_identical_two_runs(state):
    book = _book(state.clubs, n_particles=16, provisional=("hull",))
    one = leaguesim.simulate("dc_native", state, book, 256, SEED, 128)
    two = leaguesim.simulate("dc_native", state, book, 256, SEED, 128)

    assert one.digest() == two.digest(), "same inputs -> same numbers"
    assert one.matrix.tobytes() == two.matrix.tobytes()
    assert (one.retained_rows.scorelines.tobytes()
            == two.retained_rows.scorelines.tobytes())
    assert one.retained_rows.points.tobytes() == two.retained_rows.points.tobytes()

    # positive control: the digest is sensitive to the thing it is meant to pin.
    three = leaguesim.simulate("dc_native", state, book, 256, SEED + 1, 128)
    assert three.digest() != one.digest(), "a different seed must move the digest"


def test_serial_equals_chunked_equals_parallel(state):
    """N = 4,000, chunk 1,000, 2 processes — the three execution modes agree."""
    book = _book(state.clubs, n_particles=20)
    serial = leaguesim.simulate("dc_native", state, book, 4000, SEED, 1000)

    plan = serial.plan
    provider = leaguesim.DCNativeProvider(book)
    chunks = [leaguesim.simulate_chunk(provider, plan, i)
              for i in range(plan.n_chunks)]
    assert plan.n_chunks == 4
    stacked = np.concatenate([c.scorelines for c in chunks], axis=0)
    assert stacked.tobytes() == serial.retained_rows.scorelines.tobytes(), (
        "a run is exactly the concatenation of its chunks")

    with cf.ProcessPoolExecutor(max_workers=2) as pool:
        parallel = leaguesim.simulate("dc_native", state, book, 4000, SEED, 1000,
                                      executor=pool)
    assert parallel.digest() == serial.digest()
    assert (parallel.retained_rows.scorelines.tobytes()
            == serial.retained_rows.scorelines.tobytes())
    assert parallel.matrix.tobytes() == serial.matrix.tobytes()


def test_pinned_fixture_consumes_no_rng_and_equals_result(state):
    book = _book(state.clubs, n_particles=16)
    target = sorted(state.fixtures)[123]

    free = leaguesim.simulate("dc_native", state, book, 256, SEED, 128)
    pinned = leaguesim.simulate("dc_native", _with_played(state, {target: (4, 1)}),
                                book, 256, SEED, 128)
    flipped = leaguesim.simulate("dc_native", _with_played(state, {target: (0, 3)}),
                                 book, 256, SEED, 128)

    # the pinned column is the result, in every simulated season
    pos = pinned.plan.position_of(target)
    assert set(map(tuple, pinned.full_scorelines()[:, pos].tolist())) == {(4, 1)}

    # every OTHER fixture draws exactly what it drew when this one was unplayed:
    # a played fixture owns a stream it never consumes, so nothing downstream
    # shifts. Compared by fixture ordinal, since the retained set differs.
    shared = set(pinned.retained_rows.fixture_ordinals) & set(free.retained_rows.fixture_ordinals)
    assert len(shared) == 379
    a = {o: i for i, o in enumerate(free.retained_rows.fixture_ordinals)}
    b = {o: i for i, o in enumerate(pinned.retained_rows.fixture_ordinals)}
    for ordinal in sorted(shared):
        assert np.array_equal(free.retained_rows.scorelines[:, a[ordinal]],
                              pinned.retained_rows.scorelines[:, b[ordinal]]), (
            f"fixture ordinal {ordinal} moved when a different fixture was pinned")

    # positive control: pinning is not a no-op — the table it produces moves.
    assert not np.array_equal(pinned.matrix, flipped.matrix)
    assert not np.array_equal(pinned.matrix, free.matrix)


def test_kickoff_dates_do_not_enter_numbers(state):
    """Kickoffs are metadata (D3): move all 380 and nothing numeric changes."""
    book = _book(state.clubs, n_particles=16)
    base = leaguesim.simulate("dc_native", state, book, 256, SEED, 128)

    moved = dataclasses.replace(state, kickoffs_known={
        fid: (date + dt.timedelta(days=17), "12:34")
        for fid, (date, _t) in state.kickoffs_known.items()})
    shifted = leaguesim.simulate("dc_native", moved, book, 256, SEED, 128)

    assert shifted.matrix.tobytes() == base.matrix.tobytes()
    assert (shifted.retained_rows.scorelines.tobytes()
            == base.retained_rows.scorelines.tobytes())

    # positive control: a RESULT does enter the numbers, so the comparison above
    # is not comparing two runs that could never differ.
    target = sorted(state.fixtures)[7]
    with_result = leaguesim.simulate(
        "dc_native", _with_played(state, {target: (5, 0)}), book, 256, SEED, 128)
    assert not np.array_equal(with_result.matrix, base.matrix)


# ==========================================================================
# 3. coherence (D10)
# ==========================================================================

def test_matrix_doubly_stochastic_and_markets_equal_column_sums(small_run):
    matrix = small_run.matrix
    assert matrix.shape == (20, 20)
    assert np.allclose(matrix.sum(axis=1), 1.0, atol=1e-12), "every club finishes"
    assert np.allclose(matrix.sum(axis=0), 1.0, atol=1e-12), "every position taken"

    clubs = small_run.clubs
    for i, club in enumerate(clubs):
        cons = small_run.consequences[club]
        assert cons["champion"]["p"] == pytest.approx(matrix[i, 0], abs=1e-12)
        assert cons["top4"]["p"] == pytest.approx(matrix[i, :4].sum(), abs=1e-12)
        assert cons["top5"]["p"] == pytest.approx(matrix[i, :5].sum(), abs=1e-12)
        assert cons["top7"]["p"] == pytest.approx(matrix[i, :7].sum(), abs=1e-12)
        assert cons["relegated"]["p"] == pytest.approx(matrix[i, 17:].sum(), abs=1e-12)

    # the markets are a probability distribution over clubs, too
    for market, expected in (("champion", 1.0), ("top4", 4.0), ("top5", 5.0),
                             ("top7", 7.0), ("relegated", 3.0)):
        total = sum(small_run.consequences[c][market]["p"] for c in clubs)
        assert total == pytest.approx(expected, abs=1e-9)


def test_per_sim_identities(small_run):
    rows = small_run.retained_rows
    full = small_run.full_scorelines()
    plan = small_run.plan
    totals = table_mod.accumulate(full, plan.home_idx, plan.away_idx,
                                  n_clubs=len(plan.clubs),
                                  adjustments=plan.adjustments)
    table_mod.check_identities(totals)

    assert np.array_equal(totals.pts, rows.points), "retained points are the run's"
    assert np.array_equal(totals.gd, rows.gd)
    assert np.array_equal(totals.gf, rows.gf)
    assert np.all(totals.w + totals.d + totals.l == 38)
    assert np.all(totals.gd.sum(axis=1) == 0)
    assert np.array_equal(totals.gf.sum(axis=1), totals.ga.sum(axis=1))
    assert np.array_equal(totals.w.sum(axis=1), totals.l.sum(axis=1))

    # positive control: the identity checker is not vacuous.
    broken = dataclasses.replace(totals, gd=(totals.gd + 1).astype(np.int16))
    with pytest.raises(table_mod.IdentityViolation):
        table_mod.check_identities(broken)


def test_promoted_club_completes_38_and_appears_in_matrix(small_run):
    plan = small_run.plan
    for promoted in ("coventry", "hull", "ipswich"):
        i = plan.clubs.index(promoted)
        assert plan.fixtures_per_club[i] == 38, f"{promoted} plays a full season"
        row = small_run.matrix[i]
        assert row.sum() == pytest.approx(1.0, abs=1e-12)
        assert (row > 0).sum() >= 2, f"{promoted} is priced across positions"


# ==========================================================================
# 4. Monte-Carlo error, cluster-by-particle (D15)
# ==========================================================================

def test_accumulate_by_particle_matches_bincount_reference():
    """The stride trick the aggregator uses, against the obvious slow form."""
    rng = np.random.default_rng(0)
    values = rng.random((37, 3, 2))
    lo, n_particles = 5, 8
    fast = leaguesim.sum_by_particle(values, lo, n_particles)

    idx = (np.arange(lo, lo + 37) % n_particles)
    slow = np.zeros((n_particles, 3, 2))
    for i, p in enumerate(idx):
        slow[p] += values[i]
    assert np.allclose(fast, slow)
    # positive control: the offset matters, so the roll is load-bearing.
    assert not np.allclose(leaguesim.sum_by_particle(values, 0, n_particles), slow)


def test_cluster_se_matches_binomial_when_particles_identical(flat_run):
    ratios = _champion_se_ratios(flat_run)
    assert ratios, "the fixture must produce at least one non-degenerate market"
    assert 0.5 <= float(np.mean(ratios)) <= 2.0, (
        f"identical particles -> cluster SE is the binomial one, got {ratios}")


def test_cluster_se_ge_binomial_se_when_particles_matter(spread_run):
    ratios = _champion_se_ratios(spread_run)
    assert ratios
    assert min(ratios) > 3.0, (
        "with the posterior draw deciding the title, the binomial SE understates "
        f"the real uncertainty by a lot; ratios={sorted(ratios)[:5]}")


def test_outer_inner_decomposition_sums_to_total_within_tolerance(spread_run):
    run = spread_run
    worst = 0.0
    seen = 0
    for club in run.clubs:
        for cell in run.consequences[club].values():
            total = cell["se"] ** 2
            recomposed = cell["outer"] + cell["inner"]
            worst = max(worst, abs(recomposed - total))
            seen += 1
    assert seen == 5 * len(run.clubs)
    assert worst < 1e-15, f"outer + inner must reconstitute the cluster variance ({worst})"
    assert run.mc["identity_max_abs_error"] < 1e-12
    # positive control: the outer term is doing work in this fixture.
    outer = [run.consequences[c]["champion"]["outer"] for c in run.clubs]
    inner = [run.consequences[c]["champion"]["inner"] for c in run.clubs]
    assert max(outer) > 10 * max(inner)


# ==========================================================================
# 5. the outputs
# ==========================================================================

def test_cut_lines_monotone_and_from_points_rows(small_run):
    cuts = small_run.cut_lines
    assert set(cuts) == {"champion", "pos4", "pos5", "pos17", "pos18"}

    ordered = ("champion", "pos4", "pos5", "pos17", "pos18")
    quantiles = tuple(cuts["champion"])
    for q in quantiles:
        values = [cuts[key][q] for key in ordered]
        assert values == sorted(values, reverse=True), (
            f"cut lines must fall down the table at quantile {q}: {values}")

    ranked = -np.sort(-small_run.retained_rows.points, axis=1)
    for key, position in (("champion", 1), ("pos4", 4), ("pos5", 5),
                          ("pos17", 17), ("pos18", 18)):
        column = set(ranked[:, position - 1].tolist())
        for q, value in cuts[key].items():
            assert value in column, (
                f"{key} {q} = {value} is not a points total any season reached")


def test_envelope_has_every_required_field(small_run):
    env = small_run.envelope
    assert set(env) == set(leaguesim.ENVELOPE_FIELDS), (
        "the envelope's field set is frozen; add a field to ENVELOPE_FIELDS "
        "deliberately, never by accident")

    # D14 names these explicitly; each must carry a real value here.
    for field in ("schema_version", "output_schema_version", "git_commit",
                  "python_version", "numpy_version", "scipy_version",
                  "pymc_version", "arviz_version", "platform", "uv_lock_sha256",
                  "rng_algorithm", "stream_mapping", "seed", "n_sims",
                  "n_particles", "chunk_size", "effective_posterior_hash",
                  "frozen_config_sha256", "anchor_spec", "cutoff",
                  "manifest_sha256", "fixtures_base_sha256",
                  "kickoff_amendments_sha256", "results_snapshot_sha256",
                  "points_adjustments_sha256", "tiebreak_rule_id", "max_goals",
                  "widening_mode", "wall_seconds"):
        assert env[field] is not None, f"{field} is unset"

    assert env["git_dirty"] in (True, False)
    assert env["rng_algorithm"] == f"PCG64@numpy-{np.__version__}"
    assert env["seed"] == SEED and env["n_sims"] == 320 and env["chunk_size"] == 128
    assert env["max_goals"] == 10
    assert env["widening_mode"].startswith("per_fixture_bernoulli")
    assert env["fixtures_base_sha256"] == (
        "ec7f37c90517fe8d697bff0e8be9ce87d2bb54e11c67c0883c5bf5c955aa9e91")


def test_output_json_canonical(small_run, tmp_path):
    first = leaguesim.write_outputs(small_run, tmp_path / "a")
    second = leaguesim.write_outputs(small_run, tmp_path / "b")

    for key in ("output", "envelope"):
        assert first[key].read_bytes() == second[key].read_bytes(), (
            f"{key} json must serialise deterministically")
    payload = json.loads(first["output"].read_text())
    assert payload["arm"] == "dc_native"
    assert payload["envelope"]["seed"] == SEED
    assert set(payload["matrix"]) == set(small_run.clubs)

    with np.load(first["rows"]) as a, np.load(second["rows"]) as b:
        assert set(a.files) == set(b.files)
        for name in a.files:
            assert np.array_equal(a[name], b[name])

    text = first["limitations"].read_text()
    assert "unresolved" in text.lower() and "Monte" in text


def test_retained_rows_carry_every_d20_field(small_run):
    rows = small_run.retained_rows
    n_sims, n_clubs = small_run.n_sims, len(small_run.clubs)
    n_unplayed = len(small_run.plan.unplayed_positions)

    assert rows.particle.shape == (n_sims,) and rows.particle.dtype == np.int16
    assert rows.scorelines.shape == (n_sims, n_unplayed, 2)
    assert rows.scorelines.dtype == np.int8
    assert rows.fixture_ordinals.shape == (n_unplayed,)
    for name in ("points", "gd", "gf"):
        arr = getattr(rows, name)
        assert arr.shape == (n_sims, n_clubs) and arr.dtype == np.int16
    for name in ("block_start", "block_span", "resolution_code"):
        arr = getattr(rows, name)
        assert arr.shape == (n_sims, n_clubs) and arr.dtype == np.uint8
    assert rows.block_start.min() >= 1 and rows.block_start.max() <= n_clubs


def test_default_boundaries_match_the_2026_27_manifest(season):
    assert leaguesim.DEFAULT_RULE_ID == season.manifest.tiebreak_rule_id
    assert leaguesim.DEFAULT_BOUNDARIES == season.manifest.material_boundaries
    table_mod.check_rule_id(leaguesim.DEFAULT_RULE_ID, leaguesim.DEFAULT_BOUNDARIES)
