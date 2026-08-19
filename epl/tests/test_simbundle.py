"""v1.1 R2 — the sidecars that make a bridge arm re-derivable from its issuance.

`simcli check` rebuilds an arm and demands the same numbers. Until now only
``dc_native`` could be rebuilt, because the particle book is the whole of that
arm; the two bridge arms additionally need the fitted
:class:`epl.bridge.EmpiricalBridge` and, for the Elo arm, the rating table and
the ordered-logit head that priced every fixture. None of that was written down,
so a bridge issuance was unfalsifiable after the process that made it exited.

This module's contract, and the reason every test here pairs a rebuild with a
tamper: the sidecars are not a cache of the answer. The bridge is rebuilt from
its RAW COUNTS and its persisted cdf is then checked against the rebuilt one;
the Elo probabilities are re-derived from the ratings and the head and then
checked against the persisted row. A sidecar whose numbers were edited therefore
fails at the derivation, not merely at a hash comparison — and it fails NAMING
the arm it broke.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from epl import bridge as bridge_mod, ordlogit, particles, season as season_mod
from epl import simbundle
from epl.simcanary import _synthetic_book as synthetic_book

SEASON = "2026/27"
OPENER = "2026-08-21"
N_PARTICLES = 16


# ==========================================================================
# fixtures — one real season state, one synthetic book, one real bridge
# ==========================================================================
@pytest.fixture(scope="module")
def season_obj() -> season_mod.Season:
    return season_mod.Season.load(SEASON)


@pytest.fixture(scope="module")
def state(season_obj) -> season_mod.SeasonState:
    return season_obj.at(OPENER)


@pytest.fixture(scope="module")
def book(state) -> particles.ParticleBook:
    return synthetic_book(state.clubs, n_particles=N_PARTICLES)


def _archive(n: int = 900, *, seed: int = 5) -> pd.DataFrame:
    """League-shaped completed rows, all before the opener, on real club keys."""
    rng = np.random.default_rng(seed)
    hg = rng.poisson(1.55, n)
    ag = rng.poisson(1.20, n)
    dates = pd.Timestamp("2023-01-01") + pd.to_timedelta(
        np.sort(rng.integers(0, 1100, n)), unit="D")
    return pd.DataFrame({
        "match_id": [f"arch{i:05d}" for i in range(n)],
        "season": "2025/26", "date": dates, "kickoff": pd.NaT,
        "home_key": "aaa", "away_key": "bbb", "fthg": hg, "ftag": ag,
        "ftr": np.where(hg > ag, "H", np.where(hg == ag, "D", "A")),
        "played": True,
    })


@pytest.fixture(scope="module")
def fitted_bridge() -> bridge_mod.EmpiricalBridge:
    return bridge_mod.EmpiricalBridge.fit(_archive(), OPENER,
                                          max_goals=particles.PRODUCTION_MAX_GOALS)


@pytest.fixture(scope="module")
def elo_provider(state, fitted_bridge) -> bridge_mod.EloOutcomeProvider:
    """A real Elo arm over the real fixture list, on a synthetic rating table."""
    clubs = list(state.clubs)
    ratings = {club: 1500.0 + 12.0 * i for i, club in enumerate(sorted(clubs))}
    rng = np.random.default_rng(7)
    edge = rng.normal(0.0, 90.0, 600)
    p = ordlogit.predict(ordlogit.OrdLogitParams(c1=-0.9, s=-0.4, b=1.0), edge)
    codes = np.array([rng.choice(3, p=row) for row in p])
    params = ordlogit.fit(edge, codes)

    fixtures = [state.fixtures[fid] for fid in sorted(state.fixtures)]
    diff = np.array([ratings[f.home_key] - ratings[f.away_key] for f in fixtures])
    return bridge_mod.EloOutcomeProvider(
        probs=ordlogit.predict(params, diff),
        fixture_ids=[f.fixture_id for f in fixtures], bridge=fitted_bridge,
        params=params, cutoff=OPENER, n_fit_rows=len(edge),
        n_particles=N_PARTICLES, ratings=ratings)


@pytest.fixture()
def written(tmp_path, book, fitted_bridge, elo_provider) -> Path:
    """An issuance directory carrying both bridge arms' sidecars."""
    directory = tmp_path / "issuance"
    directory.mkdir()
    book.save(directory / "particles.npz")
    simbundle.write_sidecars(
        directory, arms=("dc_native", "dc_wdl_bridge", "elo_wdl_bridge"),
        bridge=fitted_bridge, book=book,
        providers={"dc_wdl_bridge": bridge_mod.DCWDLProvider(book, fitted_bridge),
                   "elo_wdl_bridge": elo_provider},
        fit_info={"cold_start_teams": ["burnley"]})
    return directory


def _edit(path: Path, mutate) -> None:
    payload = json.loads(path.read_text())
    mutate(payload)
    path.write_text(json.dumps(payload))


# ==========================================================================
# 1. what gets written
# ==========================================================================
def test_dc_native_needs_no_sidecar_and_the_files_are_named_per_arm():
    assert simbundle.ARM_SIDECARS["dc_native"] == ()
    assert simbundle.BRIDGE_SIDECAR in simbundle.ARM_SIDECARS["dc_wdl_bridge"]
    assert simbundle.ELO_SIDECAR in simbundle.ARM_SIDECARS["elo_wdl_bridge"]
    assert simbundle.BRIDGE_SIDECAR in simbundle.ARM_SIDECARS["elo_wdl_bridge"]


def test_a_native_only_forecast_writes_no_sidecar(tmp_path, book):
    directory = tmp_path / "native"
    directory.mkdir()
    assert simbundle.write_sidecars(directory, arms=("dc_native",), bridge=None,
                                    book=book, providers={}) == []
    assert sorted(p.name for p in directory.iterdir()) == []


def test_the_written_bridge_carries_its_counts_its_cdf_and_its_hash(
        written, fitted_bridge):
    payload = json.loads((written / simbundle.BRIDGE_SIDECAR).read_text())
    assert payload["schema"] == simbundle.BRIDGE_SCHEMA
    assert payload["hash"] == fitted_bridge.content_hash()
    assert np.array_equal(np.asarray(payload["counts"], np.int64),
                          fitted_bridge.counts)
    np.testing.assert_allclose(np.asarray(payload["cdf"], float),
                               fitted_bridge.cdf, rtol=0, atol=0)


def test_the_written_elo_arm_carries_ratings_head_and_priced_fixtures(
        written, elo_provider):
    payload = json.loads((written / simbundle.ELO_SIDECAR).read_text())
    assert payload["schema"] == simbundle.ELO_SCHEMA
    assert payload["content_hash"] == elo_provider.content_hash()
    assert payload["ratings"] == elo_provider.ratings
    assert payload["params"]["b"] == elo_provider.params.b
    assert tuple(payload["fixture_ids"]) == elo_provider.fixture_ids
    assert np.asarray(payload["probs"], float).shape == (380, 3)


def test_the_arms_manifest_carries_the_provisional_and_cold_start_sets(
        written, book):
    payload = json.loads((written / simbundle.ARMS_SIDECAR).read_text())
    assert payload["book_hash"] == book.content_hash()
    assert payload["provisional_teams"] == sorted(book.provisional)
    assert payload["cold_start_teams"] == ["burnley"]
    assert set(payload["arms"]) == {"dc_wdl_bridge", "elo_wdl_bridge"}


# ==========================================================================
# 2. the round trip — a rebuilt arm IS the arm
# ==========================================================================
def test_the_bridge_rebuilds_to_the_same_object(written, fitted_bridge):
    rebuilt = simbundle.read_bridge(written)
    assert rebuilt.content_hash() == fitted_bridge.content_hash()
    np.testing.assert_allclose(rebuilt.cdf, fitted_bridge.cdf, rtol=0, atol=0)
    assert rebuilt.n_rows == fitted_bridge.n_rows
    assert rebuilt.max_goals == fitted_bridge.max_goals


def test_both_bridge_arms_rebuild_to_the_same_provider(written, book, state,
                                                       elo_provider):
    dc = simbundle.rebuild_provider("dc_wdl_bridge", written, book=book,
                                    state=state)
    assert dc.content_hash() == bridge_mod.DCWDLProvider(
        book, simbundle.read_bridge(written)).content_hash()

    elo = simbundle.rebuild_provider("elo_wdl_bridge", written, book=book,
                                     state=state)
    assert elo.content_hash() == elo_provider.content_hash()
    np.testing.assert_allclose(elo.probs, elo_provider.probs, rtol=0, atol=0)


def test_rebuilding_dc_native_is_the_book_itself(written, book, state):
    assert simbundle.rebuild_provider("dc_native", written, book=book,
                                      state=state) is book


# ==========================================================================
# 3. the tampers — every one of them must be caught, and named
# ==========================================================================
def test_a_perturbed_bridge_cdf_cell_is_refused(written):
    _edit(written / simbundle.BRIDGE_SIDECAR,
          lambda p: p["cdf"][0].__setitem__(40, p["cdf"][0][40] + 0.01))
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.read_bridge(written)
    assert "cdf" in str(exc.value)


def test_a_perturbed_bridge_count_is_refused_by_its_own_hash(written):
    _edit(written / simbundle.BRIDGE_SIDECAR,
          lambda p: p["counts"][2].__setitem__(7, p["counts"][2][7] + 1))
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.read_bridge(written)
    assert "hash" in str(exc.value)


def test_a_changed_elo_rating_is_refused(written, book, state):
    def bump(payload):
        club = sorted(payload["ratings"])[0]
        payload["ratings"][club] = payload["ratings"][club] + 25.0

    _edit(written / simbundle.ELO_SIDECAR, bump)
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.rebuild_provider("elo_wdl_bridge", written, book=book,
                                   state=state)
    message = str(exc.value)
    assert "elo_wdl_bridge" in message
    assert "ratings" in message or "re-derived" in message


def test_a_changed_elo_head_parameter_is_refused(written, book, state):
    _edit(written / simbundle.ELO_SIDECAR,
          lambda p: p["params"].__setitem__("b", p["params"]["b"] * 1.05))
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.rebuild_provider("elo_wdl_bridge", written, book=book,
                                   state=state)
    assert "elo_wdl_bridge" in str(exc.value)


def test_a_swapped_book_is_refused_by_the_arms_manifest(written, book, state):
    import dataclasses

    other = dataclasses.replace(book, att=book.att + 0.05)
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.rebuild_provider("dc_wdl_bridge", written, book=other,
                                   state=state)
    assert "book" in str(exc.value)


def test_a_missing_sidecar_fails_closed_with_the_file_and_the_arm(written, book,
                                                                 state):
    (written / simbundle.ELO_SIDECAR).unlink()
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.rebuild_provider("elo_wdl_bridge", written, book=book,
                                   state=state)
    message = str(exc.value)
    assert simbundle.ELO_SIDECAR in message and "elo_wdl_bridge" in message
    # ...and the arm that does not need it is unaffected
    assert simbundle.rebuild_provider("dc_wdl_bridge", written, book=book,
                                      state=state) is not None


def test_a_missing_bridge_sidecar_fails_closed_for_both_bridge_arms(written, book,
                                                                    state):
    (written / simbundle.BRIDGE_SIDECAR).unlink()
    for arm in ("dc_wdl_bridge", "elo_wdl_bridge"):
        with pytest.raises(simbundle.BundleError) as exc:
            simbundle.rebuild_provider(arm, written, book=book, state=state)
        assert simbundle.BRIDGE_SIDECAR in str(exc.value)


def test_a_wrong_schema_version_is_refused(written):
    _edit(written / simbundle.BRIDGE_SIDECAR,
          lambda p: p.__setitem__("schema", "epl-bridge-sidecar-0"))
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.read_bridge(written)
    assert "schema" in str(exc.value)


def test_a_fixture_set_the_elo_arm_never_priced_is_refused(written, book, state):
    _edit(written / simbundle.ELO_SIDECAR,
          lambda p: p["fixture_ids"].__setitem__(0, "2627:nobody:nowhere"))
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.rebuild_provider("elo_wdl_bridge", written, book=book,
                                   state=state)
    assert "fixture" in str(exc.value)
