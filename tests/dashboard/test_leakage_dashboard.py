import pandas as pd
import pytest
from wcmodel.data.store import Policy
from wcmodel.dashboard.build import build_snapshot


@pytest.mark.slow
def test_snapshot_is_leakage_safe_post_cutoff_mutation_does_not_change_it(
        small_store, synthetic_tournament, tmp_path):
    """A snapshot built at cutoff C is unchanged by a result observed AFTER C: the bundle is
    a read(C). (The dashboard-layer analog of the P2-P5 leakage canaries.)

    NON-VACUITY: the appended row is a real played WC result (Brazil 5-0 Serbia) dated
    2026-06-20 — AFTER the 2026-06-12 cutoff — so it is excluded from BOTH the cached_fit
    feature hash and the sim conditioning (the strict date < cutoff set). It genuinely
    WOULD change a non-as-of (current-state) read; the as-of-cutoff bundle must not feel it.
    The fit cache lands under each out_root, so build 'b' re-fits against the mutated store
    rather than short-circuiting on a shared cache hit — a real leak would surface here."""
    cutoff = "2026-06-12T00:00:00Z"
    fk = {"draws": 60, "advi_iters": 1500, "seed": 0}
    b1 = build_snapshot(cutoff, store=small_store, fit_kwargs=fk, items=[],
                        out_root=tmp_path / "a", tournament=synthetic_tournament)
    before = (b1 / "tournament.json").read_text()
    # A real played WC result OBSERVED after the cutoff: valid_as_of == observed_at ==
    # date == 2026-06-20 (the normalize_results convention; the bitemporal write REQUIRES
    # both time columns). Both are > the 2026-06-12 cutoff, so the leakage-safe read(cutoff)
    # excludes it from BOTH the feature hash and the sim conditioning — yet a current-state
    # read WOULD see it (the mutation is non-vacuous).
    small_store.write("results", pd.DataFrame([{
        "match_id": "post", "date": pd.Timestamp("2026-06-20"),
        "valid_as_of": pd.Timestamp("2026-06-20"), "observed_at": pd.Timestamp("2026-06-20"),
        "home_team": "Brazil", "away_team": "Serbia", "home_score": 5, "away_score": 0,
        "tournament": "FIFA World Cup", "neutral": True, "city": "x", "country": "y",
    }]), policy=Policy.POINT_IN_TIME, keys=["match_id"], source="t")
    b2 = build_snapshot(cutoff, store=small_store, fit_kwargs=fk, items=[],
                        out_root=tmp_path / "b", tournament=synthetic_tournament)
    assert (b2 / "tournament.json").read_text() == before    # as-of-cutoff bundle unchanged


@pytest.mark.slow
def test_snapshot_is_reproducible_same_cutoff_seed_byte_identical(
        small_store, synthetic_tournament, tmp_path):
    """Same cutoff+seed -> byte-identical bundle (determinism)."""
    cutoff = "2026-06-12T00:00:00Z"
    fk = {"draws": 60, "advi_iters": 1500, "seed": 0}
    a = build_snapshot(cutoff, store=small_store, fit_kwargs=fk, items=[],
                       out_root=tmp_path / "a", tournament=synthetic_tournament)
    b = build_snapshot(cutoff, store=small_store, fit_kwargs=fk, items=[],
                       out_root=tmp_path / "b", tournament=synthetic_tournament)
    assert (a / "tournament.json").read_text() == (b / "tournament.json").read_text()
