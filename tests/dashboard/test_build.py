import json
import math
import pytest
from wcmodel.dashboard.build import _write, gate_artifact, sanitize_nans, stringify_keys
from wcmodel.dashboard.provenance import Provenance


def test_gate_rejects_a_naked_or_incoherent_artifact():
    good = {"Brazil": {"champion": {"value": 0.10, "se": 0.002},
                       "reach_final": {"value": 0.18, "se": 0.003}}}
    gate_artifact(good)                                          # no raise
    naked = {"Brazil": {"champion": {"value": 0.10}}}           # no SE/CI companion
    with pytest.raises(ValueError, match="naked"):
        gate_artifact(naked)
    incoherent = {"Brazil": {"champion": {"value": 0.30, "se": 0.0},
                             "reach_final": {"value": 0.18, "se": 0.0}}}
    with pytest.raises(ValueError, match="coherence"):
        gate_artifact(incoherent)


def test_sanitize_nans_turns_nan_into_null_so_json_is_valid():
    import json
    out = sanitize_nans({"a": float("nan"), "b": [1.0, float("nan")], "c": {"d": 2.0}})
    assert out == {"a": None, "b": [1.0, None], "c": {"d": 2.0}}
    json.dumps(out, allow_nan=False)        # must NOT raise (no NaN tokens remain)


def test_stringify_keys_makes_tuple_keys_json_safe():
    out = stringify_keys({("Spain", "Morocco", "2026-06-11"): {"edge": 0.04}})
    assert "Spain|Morocco|2026-06-11" in out


def test_write_stringifies_tuple_keys_so_a_tuple_keyed_artifact_serializes(tmp_path):
    """``_write`` must stringify a payload's tuple keys before ``json.dumps`` — an
    event-tuple-keyed artifact (e.g. ``edges_by_event`` returns ``(home, away, date) ->
    node``) would otherwise raise ``TypeError: keys must be str...``. RED before
    ``_write`` calls ``stringify_keys`` (json.dumps raises on the tuple key); GREEN after
    (the on-disk JSON carries the joined string key). ``stringify_keys`` is unit-tested in
    isolation but was never wired into ``_write`` — this pins the wiring."""
    prov = Provenance(cutoff="2026-06-12T00:00:00Z", posterior_key="k", git="abc",
                      is_synthetic=True, n_sims=10)
    payload = {("Spain", "Morocco", "2026-06-11"): {"edge": 0.04},
               ("Brazil", "Serbia", "2026-06-12"): {"edge": 0.01}}
    _write(tmp_path, "edges_by_event.json", payload, prov)        # must NOT raise

    env = json.loads((tmp_path / "edges_by_event.json").read_text())
    # The provenance envelope is intact AND the tuple keys are now JSON string keys.
    assert "Spain|Morocco|2026-06-11" in env["data"]
    assert "Brazil|Serbia|2026-06-12" in env["data"]
    assert env["data"]["Spain|Morocco|2026-06-11"]["edge"] == 0.04
    # No tuple-shaped (un-stringified) key leaked through as a Python repr string.
    assert not any(k.startswith("(") for k in env["data"])


def test_bundle_taint_is_fail_safe_any_synthetic_taints():
    from wcmodel.dashboard.build import _bundle_is_synthetic
    # a MIXED batch (one synthetic, one not) must taint the whole bundle NON-REAL
    assert _bundle_is_synthetic([{"sample": {"_is_synthetic": True}},
                                 {"sample": {"_is_synthetic": False}}]) is True
    # a nested/wrapper marker also taints
    assert _bundle_is_synthetic([{"sample": {"x": {"_is_synthetic": True}}}]) is True
    # items=None (no real feed supplied) is synthetic by default
    assert _bundle_is_synthetic(None) is True
    # ONLY an all-explicitly-real batch is real
    assert _bundle_is_synthetic([{"sample": {"_is_synthetic": False}}]) is False


def test_bundle_taint_catches_wrapper_level_and_bare_items():
    from wcmodel.dashboard.build import _bundle_is_synthetic
    # taint flag at the ITEM/wrapper level (sample inner is clean) -> must still be NON-REAL
    assert _bundle_is_synthetic([{"sample": {"_is_synthetic": False}, "is_synthetic": True}]) is True
    assert _bundle_is_synthetic([{"sample": {"x": 1}, "_is_synthetic": True}]) is True
    # a bare synthetic item (no "sample" key; the item IS the sample) -> NON-REAL
    assert _bundle_is_synthetic([{"_is_synthetic": True}]) is True
    # all-explicitly-real (no taint anywhere) -> real
    assert _bundle_is_synthetic([{"sample": {"_is_synthetic": False}}]) is False


@pytest.mark.slow
def test_bundle_dir_contains_only_stamped_artifacts(small_store, synthetic_tournament, tmp_path):
    import json
    from wcmodel.dashboard.build import build_snapshot
    # synthetic_tournament: the compact small_store posterior covers only the PANEL teams, so
    # the real 48-team draw would KeyError in RateBook(posterior) (see conftest). The bundle
    # COMPOSITION (only stamped *.json, no _fit_cache sidecar) is independent of which bracket
    # is simulated, so we use the same synthetic bracket every other small_store build uses.
    b = build_snapshot("2026-06-12T00:00:00Z", store=small_store, items=[],
                       fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0},
                       out_root=tmp_path, tournament=synthetic_tournament)
    arts = list(b.glob("*.json"))
    assert arts, "bundle must contain at least one artifact"
    for p in arts:                                  # every top-level json is a stamped artifact
        env = json.loads(p.read_text())
        assert "provenance" in env and "data" in env
    assert not (b / "_fit_cache").exists()          # the fit cache is NOT a sidecar inside the bundle
    # no stray non-artifact dirs in the bundle
    assert all(child.suffix == ".json" or child.is_dir() and child.name == "fixtures"
               for child in b.iterdir())
    # AND the cache is OUT of the whole output tree: out_root (the dashboard output dir that a
    # production build reuses across cutoffs) holds ONLY per-cutoff bundle subdirs, never a
    # `_fit_cache` sidecar. RED before C4 (default cache = out_root/_fit_cache pollutes the
    # output dir); GREEN after (default cache = paths.cache, OUTSIDE out_root). A reader
    # globbing the output tree for stamped bundles never trips over a cache dir.
    assert not (tmp_path / "_fit_cache").exists()
