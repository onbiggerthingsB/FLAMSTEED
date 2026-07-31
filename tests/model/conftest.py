"""Phase-2 model tests reuse the Phase-1 data fixtures."""
from tests.data.conftest import (  # noqa: F401
    small_store, mutable_store, matches_df,
)


def fit_compact_real_posterior(root):
    """The smallest REAL fitted Posterior the suite can build (OA Plan 2 V2).

    A genuine ADVI fit (~3 s) on the compact Phase-1 results panel — the same
    ``_RAW_RESULTS`` panel ``small_store`` seeds, results table only — with the
    suite's smallest sampler settings (``draws=40, advi_iters=300, seed=0``,
    the ``tests/model/test_fit_predict.py`` pattern). The draw-api parity and
    implied-solver tests require a REAL Posterior (finding 11: stub-only parity
    proves nothing about the per-draw structure), and this is the cheapest one
    the existing fit helpers provide — never a live network, never a scored
    pool. The compact panel's few-games teams land in ``provisional_teams``,
    so the provisional/widening branch is reachable without a second fit.

    A plain function (not a fixture) so both ``tests/model/test_draw_api.py``
    and ``tests/eval/test_implied.py`` can wrap it in their own module-scoped
    fixtures without cross-package fixture plumbing.
    """
    from tests.data.conftest import _RAW_RESULTS
    from wcmodel.data.sources.results import normalize_results
    from wcmodel.data.store import BitemporalStore, Policy
    from wcmodel.model.scoreline import fit

    store = BitemporalStore(root=root)
    store.write("results", normalize_results(_RAW_RESULTS),
                policy=Policy.POINT_IN_TIME, keys=["match_id"],
                source="martj42", source_version="test")
    return fit("2024-06-01", store, backend="advi", draws=40, seed=0,
               advi_iters=300)
