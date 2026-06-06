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


def test_bundle_taint_fail_safe_unmarked_item_reads_non_real():
    """FIX A: an UNMARKED item (a dict with no ``is_synthetic`` marker at the item level NOR
    in its sample) must read NON-REAL — the invariant is 'NON-REAL unless EVERY item is
    EXPLICITLY real'. Pre-fix ``any(_item_synth(it))`` only flagged POSITIVELY-synthetic
    items, so an unmarked item slipped through as REAL (the banner could drop on data that
    never proved itself real). The fix requires an explicit ``is_synthetic is False`` marker
    (item-level OR in the sample) AND a non-synthetic sample to clear the taint.

    RED before (unmarked -> any() returns False -> REAL); GREEN after (unmarked -> NON-REAL)."""
    from wcmodel.dashboard.build import _bundle_is_synthetic
    # an UNMARKED item (no is_synthetic marker anywhere) is NOT explicitly real -> NON-REAL
    assert _bundle_is_synthetic([{"sample": {"book": {"home": 2.0}}}]) is True
    # an item explicitly real at BOTH the item level AND in its sample -> REAL
    assert _bundle_is_synthetic([{"is_synthetic": False, "sample": {"is_synthetic": False}}]) is False
    # a positively-synthetic item still taints
    assert _bundle_is_synthetic([{"is_synthetic": True}]) is True
    # ONE unmarked item among an explicitly-real one taints the WHOLE bundle (every item must clear)
    assert _bundle_is_synthetic([{"is_synthetic": False}, {"sample": {}}]) is True
    # empty / None preserved as synthetic-by-default
    assert _bundle_is_synthetic([]) is True
    assert _bundle_is_synthetic(None) is True


@pytest.mark.slow
def test_dry_run_taints_the_bundle_non_real_even_with_real_items(
        small_store, synthetic_tournament, tmp_path):
    """MED-6 (C5 FOCAL Codex): when ``cfg["dashboard"]["dry_run"]`` is True, the WHOLE bundle
    must be stamped NON-REAL (``provenance.is_synthetic == True``) regardless of the items.

    THE BUG (before the fix). ``track_record``'s payload hardcodes ``is_synthetic=True`` (a
    paper track), but the BUNDLE provenance ORed only ``_bundle_is_synthetic(items)`` +
    ``ranked.is_synthetic``. So with EXPLICITLY-REAL items (no synthetic flag), the bundle
    banner read REAL while the embedded paper track read NON-REAL — a paper track sitting under
    a real-looking banner. In v1 (``dashboard.dry_run=True``) the bundle is synthetic-odds
    posture, so it must ALWAYS be NON-REAL.

    THE FIX. ``is_synth = cfg["dashboard"]["dry_run"] or _bundle_is_synthetic(items) or
    ranked.is_synthetic``. RED before (real items + dry_run -> banner False); GREEN after
    (dry_run alone taints)."""
    import copy
    import json
    from wcmodel.config import load_config
    from wcmodel.dashboard.build import build_snapshot, _bundle_is_synthetic

    cfg = copy.deepcopy(load_config())
    cfg["dashboard"]["dry_run"] = True

    # EXPLICITLY-REAL items: _bundle_is_synthetic reads them REAL (so the items themselves do
    # NOT taint), and they decide-fail as counted non-bets so the scan's own taint stays False
    # too. Pre-fix, BOTH taint sources are False -> the banner would read REAL despite dry_run.
    real_items = [{"sample": {"_is_synthetic": False}, "liquidity": 50.0}]
    assert _bundle_is_synthetic(real_items) is False     # the items alone do NOT taint

    b = build_snapshot("2026-06-12T12:00:00Z", store=small_store, items=real_items,
                       config=cfg, fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0,
                                               "cache_dir": str(tmp_path / "fc")},
                       tournament=synthetic_tournament, out_root=tmp_path / "out")
    # Every artifact's provenance is NON-REAL because the dashboard is in dry-run.
    for p in b.rglob("*.json"):
        env = json.loads(p.read_text())
        assert env["provenance"]["is_synthetic"] is True, (
            f"{p.name}: dry_run=True did NOT taint the bundle NON-REAL — a paper track would "
            "sit under a real-looking banner (MED-6)"
        )


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


@pytest.mark.slow
def test_rebuild_clears_stale_artifacts_from_the_bundle_dir(small_store, synthetic_tournament,
                                                            tmp_path):
    """FIX B: a rebuild into an EXISTING per-cutoff bundle dir must REMOVE stale artifacts a
    prior/different build left behind — ``mkdir(exist_ok=True)`` overwrites named files but
    leaves ORPHANED top-level/``fixtures/*.json`` (a stale-provenance file the frontend would
    render + a byte-reproducibility/§10 violation). The clear is scoped EXACTLY to the
    per-cutoff bundle dir (never out_root or above).

    RED before (the stale ``fixtures/STALE.json`` + top-level ``extra.json`` survive the
    rebuild); GREEN after (only the current build's stamped artifacts remain)."""
    from wcmodel.dashboard.build import build_snapshot
    cutoff = "2026-06-12T00:00:00Z"
    out_root = tmp_path / "out"
    bundle_name = cutoff.replace(":", "").replace(" ", "T")
    bundle = out_root / bundle_name

    # Pre-seed the bundle dir with stale orphans from a hypothetical prior/different build.
    (bundle / "fixtures").mkdir(parents=True)
    (bundle / "fixtures" / "STALE.json").write_text('{"stale": true}')
    (bundle / "extra.json").write_text('{"orphan": true}')
    # A sibling bundle dir under the SAME out_root must NOT be touched (scope = this dir only).
    sibling = out_root / "2026-06-13T000000Z"
    sibling.mkdir(parents=True)
    (sibling / "keepme.json").write_text('{"sibling": true}')

    b = build_snapshot(cutoff, store=small_store, items=[],
                       fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0,
                                   "cache_dir": str(tmp_path / "fc")},
                       out_root=out_root, tournament=synthetic_tournament)
    assert b == bundle

    # The stale orphans are GONE.
    assert not (bundle / "extra.json").exists(), "stale top-level orphan survived the rebuild"
    assert not (bundle / "fixtures" / "STALE.json").exists(), \
        "stale fixtures/ orphan survived the rebuild"
    # Only the current build's stamped artifacts remain (each a {provenance, data} envelope).
    for p in bundle.rglob("*.json"):
        env = json.loads(p.read_text())
        assert "provenance" in env and "data" in env
    # The clear was scoped to THIS bundle dir — the sibling bundle is untouched.
    assert (sibling / "keepme.json").exists(), "the clear leaked OUTSIDE the per-cutoff bundle dir"


@pytest.mark.slow
def test_schedule_gate_is_wired_and_real_occupants_carry_se(small_store, synthetic_tournament,
                                                            tmp_path):
    """FIX D: build_snapshot GATES schedule.json (the homepage) as a true STOP before writing,
    and the real production occupant nodes carry ``se`` (so the occupant-se gate has TEETH on
    real data without false-raising). A naked-prob schedule would RAISE in ``gate_schedule``
    before any write; here we prove the VALID production schedule passes AND every emitted KO
    occupant carries a finite ``se`` (proving team_progression emits se on the placing markets
    that feed ko_slot_occupants)."""
    from wcmodel.dashboard.build import build_snapshot
    b = build_snapshot("2026-06-12T12:00:00Z", store=small_store, items=[],
                       fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0,
                                   "cache_dir": str(tmp_path / "fc")},
                       out_root=tmp_path / "out", tournament=synthetic_tournament)
    sched = json.loads((b / "schedule.json").read_text())["data"]
    # Every group row's forecast_summary is either a gap or a coherent headline+1X2 (it
    # already passed gate_schedule or the build would have raised). Spot-check the KO rows:
    # an emitted (non-gap) occupant carries {team, prob, se} with a finite se.
    saw_occupant = False
    for row in sched["knockout"]:
        for side in ("home_occupants", "away_occupants"):
            occ = row[side]
            if isinstance(occ, list):                  # a non-gap occupant-list
                for o in occ:
                    saw_occupant = True
                    assert {"team", "prob", "se"} <= set(o), f"occupant missing a field: {o!r}"
                    assert isinstance(o["se"], (int, float)) and math.isfinite(o["se"]), \
                        f"occupant {o['team']!r} se is not finite — would false-raise the gate"
    assert saw_occupant, "no real occupant nodes emitted — the occupant-se gate was never exercised"
