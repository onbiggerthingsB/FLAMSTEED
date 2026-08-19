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


def test_a_changed_elo_head_parameter_is_refused_by_the_derivation_itself(
        written, book, state, elo_provider):
    """The HEAD path must fail on its own, not via a downstream hash mismatch.

    Every message this module raises names the arm, so asserting only that
    `'elo_wdl_bridge' in message` is satisfied by any failure anywhere — a
    missing file, a schema bump, the provider hash comparison at the end. The
    claim being made here is narrower: a changed `b` is caught by RE-DERIVING
    the 1X2 rows from the ratings and the head and finding they no longer
    reproduce the persisted ones, which is the check that makes the sidecar
    evidence rather than a cache.
    """
    # POSITIVE CONTROL: untouched, this bundle rebuilds to the published arm, so
    # the refusal below cannot be an artefact of a bundle that never worked.
    assert simbundle.rebuild_provider(
        "elo_wdl_bridge", written, book=book,
        state=state).content_hash() == elo_provider.content_hash()

    _edit(written / simbundle.ELO_SIDECAR,
          lambda p: p["params"].__setitem__("b", p["params"]["b"] * 1.05))
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.rebuild_provider("elo_wdl_bridge", written, book=book,
                                   state=state)
    message = str(exc.value)
    assert "elo_wdl_bridge" in message
    # it is the DERIVATION that refuses...
    assert "re-derived" in message and simbundle.ELO_SIDECAR in message
    assert "head" in message
    # ...and not `_same_hash`, whose message is the other way a changed head
    # could have been noticed
    assert "the provider rebuilt from the bundle hashes to" not in message


def test_a_head_parameter_that_is_not_a_number_is_refused_not_raised(
        written, book, state):
    _edit(written / simbundle.ELO_SIDECAR,
          lambda p: p["params"].__setitem__("b", "one-point-oh"))
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.rebuild_provider("elo_wdl_bridge", written, book=book,
                                   state=state)
    message = str(exc.value)
    assert "elo_wdl_bridge" in message and simbundle.ELO_SIDECAR in message
    assert "params" in message and "not a number" in message


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


# ==========================================================================
# 4. the anchor — a bundle coherent with ITSELF is not evidence
# ==========================================================================
def _anchors_of(directory: Path, book, elo_provider,
                bridge: bridge_mod.EmpiricalBridge) -> dict:
    """What `issuance.json` records for this bundle, before anything is edited."""
    return {
        "bridge_hash": bridge.content_hash(),
        "arms_manifest_hash": simbundle.arms_manifest_hash(directory),
        "provider_hashes": {
            "dc_wdl_bridge": bridge_mod.DCWDLProvider(book, bridge).content_hash(),
            "elo_wdl_bridge": elo_provider.content_hash()},
    }


def _double_every_count(directory: Path, book, elo_provider) -> dict:
    """The coherent cross-file tamper, made as well as it can be made.

    Doubling every count leaves the pmf — and therefore the cdf — bit-for-bit
    identical, because each row is divided by its own total. The editor then
    rewrites the three hashes the bundle checks against itself: `bridge.json`'s
    own `hash`, and both arm hashes in `arms.json` and `elo_arm.json`. Nothing
    inside the bundle disagrees with anything else after this.
    """
    bridge_path = directory / simbundle.BRIDGE_SIDECAR
    payload = json.loads(bridge_path.read_text())
    before = [list(row) for row in payload["cdf"]]

    doubled = bridge_mod.EmpiricalBridge(
        counts=np.asarray(payload["counts"], np.int64) * 2,
        max_goals=int(payload["max_goals"]), cutoff=str(payload["cutoff"]),
        n_rows=int(payload["n_rows"]) * 2,
        n_excluded=int(payload["n_excluded"]) * 2)
    payload["counts"] = doubled.counts.tolist()
    payload["n_rows"] = int(doubled.n_rows)
    payload["n_excluded"] = int(doubled.n_excluded)
    payload["cdf"] = doubled.cdf.tolist()
    payload["hash"] = doubled.content_hash()
    bridge_path.write_text(json.dumps(payload))
    # the premise of the whole tamper: the derived cdf did not move at all
    assert payload["cdf"] == before

    elo_path = directory / simbundle.ELO_SIDECAR
    elo_payload = json.loads(elo_path.read_text())
    elo = bridge_mod.EloOutcomeProvider(
        probs=elo_provider.probs, fixture_ids=elo_provider.fixture_ids,
        bridge=doubled, params=elo_provider.params,
        cutoff=elo_provider.cutoff, n_fit_rows=elo_provider.n_fit_rows,
        n_particles=elo_provider.n_particles, ratings=elo_provider.ratings)
    elo_payload["content_hash"] = elo.content_hash()
    elo_path.write_text(json.dumps(elo_payload))

    arms_path = directory / simbundle.ARMS_SIDECAR
    arms = json.loads(arms_path.read_text())
    arms["arms"]["dc_wdl_bridge"]["content_hash"] = bridge_mod.DCWDLProvider(
        book, doubled).content_hash()
    arms["arms"]["elo_wdl_bridge"]["content_hash"] = elo.content_hash()
    arms_path.write_text(json.dumps(arms))
    return {"doubled_hash": doubled.content_hash()}


def test_a_coherent_cross_file_tamper_is_caught_only_by_the_recorded_hashes(
        written, book, state, fitted_bridge, elo_provider):
    """THE hole this closes: every check inside the bundle can be satisfied.

    The rebuild used to be held against the sidecars' own hashes, so an editor
    who doubled the evidence and rewrote those hashes produced a bundle that
    rebuilt, re-derived and re-hashed without a complaint — a bridge fitted on
    twice as many matches as ever existed, passing as the published one. The
    only thing that can tell the difference is a hash written down somewhere the
    bundle does not control: `issuance.json`.
    """
    anchors = _anchors_of(written, book, elo_provider, fitted_bridge)
    tamper = _double_every_count(written, book, elo_provider)
    assert tamper["doubled_hash"] != anchors["bridge_hash"]

    # POSITIVE CONTROL for the anchor being the thing that catches it: with no
    # anchors, every internal check passes and both arms rebuild happily.
    for arm in ("dc_wdl_bridge", "elo_wdl_bridge"):
        assert simbundle.rebuild_provider(arm, written, book=book,
                                          state=state) is not None, arm

    # ...and against what the issuance recorded, both refuse, naming the file
    # the recorded hash came from and both hashes.
    for arm in ("dc_wdl_bridge", "elo_wdl_bridge"):
        with pytest.raises(simbundle.BundleError) as exc:
            simbundle.rebuild_provider(arm, written, book=book, state=state,
                                       anchors=anchors)
        message = str(exc.value)
        assert arm in message
        assert "bridge_hash" in message
        assert simbundle.ISSUANCE_RECORD in message
        assert anchors["bridge_hash"] in message
        assert tamper["doubled_hash"] in message


def test_the_untampered_bundle_passes_every_recorded_anchor(
        written, book, state, fitted_bridge, elo_provider):
    """POSITIVE CONTROL: the anchors are satisfiable, so the test above is not
    asserting that anchoring refuses everything."""
    anchors = _anchors_of(written, book, elo_provider, fitted_bridge)
    for arm in ("dc_wdl_bridge", "elo_wdl_bridge"):
        provider = simbundle.rebuild_provider(arm, written, book=book,
                                              state=state, anchors=anchors)
        assert provider.content_hash() == anchors["provider_hashes"][arm], arm


def test_an_edited_arms_manifest_fails_against_its_recorded_hash(
        written, book, state, fitted_bridge, elo_provider):
    """The manifest's cold-start set is read by nothing else in the rebuild."""
    anchors = _anchors_of(written, book, elo_provider, fitted_bridge)
    _edit(written / simbundle.ARMS_SIDECAR,
          lambda p: p.__setitem__("cold_start_teams", ["a_club_that_was_not"]))

    # without the anchor nothing notices, because nothing else reads that field
    assert simbundle.rebuild_provider("dc_wdl_bridge", written, book=book,
                                      state=state) is not None
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.rebuild_provider("dc_wdl_bridge", written, book=book,
                                   state=state, anchors=anchors)
    message = str(exc.value)
    assert simbundle.ARMS_SIDECAR in message
    assert simbundle.ISSUANCE_RECORD in message


def test_a_provider_hash_the_issuance_did_not_record_is_refused(
        written, book, state, fitted_bridge, elo_provider):
    anchors = _anchors_of(written, book, elo_provider, fitted_bridge)
    anchors["provider_hashes"]["dc_wdl_bridge"] = "not-the-provider-published"
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.rebuild_provider("dc_wdl_bridge", written, book=book,
                                   state=state, anchors=anchors)
    message = str(exc.value)
    assert simbundle.ISSUANCE_RECORD in message
    assert "not-the-provider-published" in message


def test_the_manifest_hash_is_over_content_not_bytes(written):
    """A re-serialised manifest is the same manifest; an edited one is not."""
    path = written / simbundle.ARMS_SIDECAR
    before = simbundle.arms_manifest_hash(written)
    payload = json.loads(path.read_text())
    path.write_text(json.dumps(payload, indent=4))          # same content
    assert simbundle.arms_manifest_hash(written) == before
    _edit(path, lambda p: p["arms"]["dc_wdl_bridge"].__setitem__(
        "content_hash", "0" * 64))
    assert simbundle.arms_manifest_hash(written) != before


def test_recorded_anchors_reports_an_older_record_as_unanchored():
    """An `epl-issuance-2` record carries no manifest hash; None anchors nothing."""
    got = simbundle.recorded_anchors({"bridge_hash": "abc",
                                      "provider_hashes": {"dc_wdl_bridge": "d"}})
    assert got["bridge_hash"] == "abc"
    assert got["arms_manifest_hash"] is None
    assert got["provider_hashes"] == {"dc_wdl_bridge": "d"}


# ==========================================================================
# 5. strict decoding — 7.5 is not 7, and NaN is not agreement
# ==========================================================================
def test_a_fractional_count_is_refused_rather_than_truncated(written, book,
                                                             state):
    """`np.asarray([7.5], np.int64)` is 7: a lenient decode would rebuild a
    bridge from evidence nobody wrote and then hash it as the fitted one."""
    _edit(written / simbundle.BRIDGE_SIDECAR,
          lambda p: p["counts"][0].__setitem__(0, 7.5))
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.read_bridge(written)
    message = str(exc.value)
    assert "7.5" in message and "counts[0][0]" in message
    assert "not an integer" in message


def test_a_negative_count_is_refused(written):
    _edit(written / simbundle.BRIDGE_SIDECAR,
          lambda p: p["counts"][1].__setitem__(3, -1))
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.read_bridge(written)
    assert "never negative" in str(exc.value)


def test_a_nan_cdf_cell_is_refused_and_does_not_pass_the_tolerance(written):
    """|persisted - rebuilt| > tol is False for NaN, so the comparison that
    exists to catch an edited cdf would have read this as agreement."""
    _edit(written / simbundle.BRIDGE_SIDECAR,
          lambda p: p["cdf"][0].__setitem__(5, float("nan")))
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.read_bridge(written)
    message = str(exc.value)
    assert "cdf[0][5]" in message and "non-finite" in message


def test_a_nan_elo_probability_is_refused(written, book, state):
    _edit(written / simbundle.ELO_SIDECAR,
          lambda p: p["probs"][2].__setitem__(1, float("nan")))
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.rebuild_provider("elo_wdl_bridge", written, book=book,
                                   state=state)
    message = str(exc.value)
    assert "probs[2][1]" in message and "non-finite" in message


def test_a_nan_rating_is_refused(written, book, state):
    _edit(written / simbundle.ELO_SIDECAR,
          lambda p: p["ratings"].__setitem__(sorted(p["ratings"])[0],
                                             float("nan")))
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.rebuild_provider("elo_wdl_bridge", written, book=book,
                                   state=state)
    message = str(exc.value)
    assert "ratings" in message and "non-finite" in message


def test_a_nan_head_parameter_is_refused_before_it_can_make_nan_probabilities(
        written, book, state):
    _edit(written / simbundle.ELO_SIDECAR,
          lambda p: p["params"].__setitem__("c1", float("nan")))
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.rebuild_provider("elo_wdl_bridge", written, book=book,
                                   state=state)
    message = str(exc.value)
    assert "params" in message and "non-finite" in message


# ==========================================================================
# 6. malformed sidecars — a refusal naming the arm and the file, never a crash
# ==========================================================================
def test_a_sidecar_that_is_not_a_json_object_is_refused(written, book, state):
    for name, arm in ((simbundle.BRIDGE_SIDECAR, "dc_wdl_bridge"),
                      (simbundle.ARMS_SIDECAR, "dc_wdl_bridge"),
                      (simbundle.ELO_SIDECAR, "elo_wdl_bridge")):
        directory = written
        payload = json.loads((directory / name).read_text())
        (directory / name).write_text(json.dumps([payload]))
        with pytest.raises(simbundle.BundleError) as exc:
            simbundle.rebuild_provider(arm, directory, book=book, state=state)
        message = str(exc.value)
        assert arm in message and name in message
        assert "not a JSON object" in message
        (directory / name).write_text(json.dumps(payload))     # restore


def test_an_unparseable_rating_is_refused_naming_the_arm_and_the_file(
        written, book, state):
    _edit(written / simbundle.ELO_SIDECAR,
          lambda p: p["ratings"].__setitem__(sorted(p["ratings"])[0], "1500ish"))
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.rebuild_provider("elo_wdl_bridge", written, book=book,
                                   state=state)
    message = str(exc.value)
    assert "elo_wdl_bridge" in message and simbundle.ELO_SIDECAR in message
    assert "'1500ish'" in message and "not a number" in message


def test_a_ratings_block_that_is_not_a_mapping_is_refused(written, book, state):
    _edit(written / simbundle.ELO_SIDECAR,
          lambda p: p.__setitem__("ratings", ["arsenal", 1500.0]))
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.rebuild_provider("elo_wdl_bridge", written, book=book,
                                   state=state)
    message = str(exc.value)
    assert "elo_wdl_bridge" in message and simbundle.ELO_SIDECAR in message


def test_a_missing_field_is_refused_naming_the_field(written):
    _edit(written / simbundle.BRIDGE_SIDECAR, lambda p: p.pop("counts"))
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.read_bridge(written)
    assert "'counts'" in str(exc.value)


def test_a_ragged_counts_grid_is_refused(written):
    _edit(written / simbundle.BRIDGE_SIDECAR,
          lambda p: p["counts"].__setitem__(1, p["counts"][1][:-1]))
    with pytest.raises(simbundle.BundleError) as exc:
        simbundle.read_bridge(written)
    assert "ragged" in str(exc.value)
