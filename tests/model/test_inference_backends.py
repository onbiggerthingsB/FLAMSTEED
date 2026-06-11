"""P5 inference-upgrade: backend dispatch, NUTS knobs/diagnostics, fail-loud deps.

Companion to ``test_inference.py`` (which pins the pre-P5 advi/nuts/pathfinder
behaviour). This file pins the P5 ADDITIONS:

  * ``fullrank_advi`` is a real, dependency-free backend (stock ``pm.fit`` method).
  * ``backend="advi"`` is BYTE-IDENTICAL to the pre-P5 path even with the new
    ``chains``/``target_accept``/``nuts_sampler`` kwargs present (they are
    NUTS-only — the advi branch must never read them).
  * ``_resolve_nuts_sampler`` AUTO-selects native ``pymc`` in this venv (nutpie /
    numpyro absent) and FAILS LOUD (ImportError naming the pip install) when an
    accelerated engine is explicitly requested but missing.
  * ``nuts_diagnostics`` extracts (divergences, min-ESS, max-Rhat) and degrades to
    ``None`` (never raises) on a posterior-only / single-chain idata.

The heavy sampling tests are ``@pytest.mark.slow``; the resolution / diagnostics /
byte-identical tests are FAST (no real NUTS fit) so they run under the curfew.
"""
import arviz as az
import numpy as np
import pytest

from tests.model.test_scoreline import _sim_design
from wcmodel.model.inference import (
    _resolve_nuts_sampler,
    nuts_diagnostics,
    sample,
)
from wcmodel.model.scoreline import build_model


# --------------------------------------------------------------------------- #
# fullrank_advi — real backend, no new dependency.                            #
# --------------------------------------------------------------------------- #
@pytest.mark.slow
def test_fullrank_advi_returns_idata_and_learns():
    """fullrank_advi is a stock pm.fit method (no extra dep). It must return an
    idata with the model params AND actually move off the prior (att has spread)."""
    d, *_ = _sim_design(n_matches=200)
    m = build_model(d, "dixon_coles")
    idata = sample(m, backend="fullrank_advi", draws=100, seed=7, advi_iters=2000)
    assert "mu" in idata.posterior
    att = idata.posterior["att"].mean(("chain", "draw")).values
    assert float(att.std()) > 0.01


@pytest.mark.slow
def test_fullrank_advi_is_seeded_reproducible():
    """Two fullrank_advi fits at the same seed are bit-identical (project
    invariant — seed threaded into BOTH fit and draw)."""
    d, *_ = _sim_design(n_matches=200)
    m = build_model(d, "dixon_coles")
    a = sample(m, backend="fullrank_advi", draws=100, seed=11, advi_iters=2000)
    b = sample(m, backend="fullrank_advi", draws=100, seed=11, advi_iters=2000)
    assert np.isclose(a.posterior["mu"].mean().item(),
                      b.posterior["mu"].mean().item(), atol=1e-6)


# --------------------------------------------------------------------------- #
# BYTE-IDENTICAL-OFF: advi unchanged by the new NUTS kwargs.                   #
# --------------------------------------------------------------------------- #
@pytest.mark.slow
def test_advi_byte_identical_with_new_nuts_kwargs_present():
    """The new chains/target_accept/nuts_sampler kwargs are NUTS-only. An advi
    fit run with them present (non-default values) must be BIT-IDENTICAL to one
    run without them — proving the advi branch never reads them (byte-identical
    -OFF guarantee for the default backend)."""
    d, *_ = _sim_design(n_matches=200)
    m = build_model(d, "dixon_coles")
    base = sample(m, backend="advi", draws=100, seed=3, advi_iters=2000)
    withk = sample(m, backend="advi", draws=100, seed=3, advi_iters=2000,
                   chains=8, target_accept=0.99, nuts_sampler="numpyro")
    a = base.posterior["att"].mean(("chain", "draw")).values
    b = withk.posterior["att"].mean(("chain", "draw")).values
    assert np.allclose(a, b, atol=1e-9), (
        "advi output changed when NUTS-only kwargs were supplied -> the advi "
        "branch is reading a NUTS knob -> byte-identical-off is broken"
    )


# --------------------------------------------------------------------------- #
# NUTS sampler resolution — auto + fail-loud (FAST, no sampling).             #
# --------------------------------------------------------------------------- #
def test_resolve_nuts_sampler_auto_falls_back_to_native_pymc():
    """nutpie/numpyro are absent in this venv -> AUTO (None) resolves to the
    native 'pymc' engine (dependency-free)."""
    assert _resolve_nuts_sampler(None) == "pymc"


def test_resolve_nuts_sampler_explicit_pymc_passes_through():
    assert _resolve_nuts_sampler("pymc") == "pymc"


def test_resolve_nuts_sampler_explicit_missing_engine_fails_loud():
    """An EXPLICIT nutpie/numpyro request, when absent, must raise ImportError
    naming the package AND the pip install command — never silently downgrade."""
    for engine in ("nutpie", "numpyro"):
        with pytest.raises(ImportError, match=rf"{engine}.*pip install {engine}"):
            _resolve_nuts_sampler(engine)


def test_resolve_nuts_sampler_unknown_name_raises_valueerror():
    with pytest.raises(ValueError, match="unknown nuts_sampler"):
        _resolve_nuts_sampler("stan")


def test_resolve_nuts_sampler_prefers_accelerated_when_importable(monkeypatch):
    """If an accelerated engine WERE importable, AUTO must prefer it over native.
    We simulate nutpie being importable via a fake import to prove the preference
    order without installing anything (the lazy __import__ is monkeypatched)."""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "nutpie":
            return object()  # pretend nutpie imports
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert _resolve_nuts_sampler(None) == "nutpie"


# --------------------------------------------------------------------------- #
# nuts_diagnostics — extraction + graceful degradation (FAST).                #
# --------------------------------------------------------------------------- #
def _nuts_like_idata(n_chains=2, n_draws=200, n_div=3, seed=0):
    """A NUTS-shaped idata: a posterior group (2 params) + a sample_stats group
    carrying a ``diverging`` boolean array with ``n_div`` True entries."""
    rng = np.random.default_rng(seed)
    post = {
        "mu": rng.normal(0, 1, (n_chains, n_draws)),
        "home_adv": rng.normal(0, 1, (n_chains, n_draws)),
    }
    div = np.zeros((n_chains, n_draws), dtype=bool)
    flat = div.reshape(-1)
    flat[:n_div] = True
    stats = {"diverging": div.reshape(n_chains, n_draws)}
    return az.from_dict({"posterior": post, "sample_stats": stats})


def test_nuts_diagnostics_counts_divergences_and_shapes():
    idata = _nuts_like_idata(n_chains=2, n_draws=200, n_div=3)
    diag = nuts_diagnostics(idata)
    assert diag["divergences"] == 3
    assert diag["n_chains"] == 2
    assert diag["n_draws"] == 200
    # 2 chains -> ess/rhat are computable and finite.
    assert diag["min_ess_bulk"] is not None and np.isfinite(diag["min_ess_bulk"])
    assert diag["max_rhat"] is not None and np.isfinite(diag["max_rhat"])


def test_nuts_diagnostics_posterior_only_idata_degrades_to_none():
    """A cache-reloaded posterior-ONLY idata has NO sample_stats group (NETCDF3
    limitation). divergences must degrade to None (NOT raise) so the caller can
    record 'unavailable' rather than crash."""
    rng = np.random.default_rng(1)
    idata = az.from_dict({"posterior": {"mu": rng.normal(0, 1, (2, 100))}})
    diag = nuts_diagnostics(idata)
    assert diag["divergences"] is None      # no sample_stats -> None, no crash
    assert diag["n_chains"] == 2


def test_nuts_diagnostics_single_chain_guards_ess_rhat():
    """R-hat needs >=2 chains; a 1-chain idata must yield min_ess_bulk/max_rhat
    None (guarded) rather than a NaN/exception leaking out."""
    rng = np.random.default_rng(2)
    idata = az.from_dict({"posterior": {"mu": rng.normal(0, 1, (1, 100))}})
    diag = nuts_diagnostics(idata)
    assert diag["n_chains"] == 1
    assert diag["min_ess_bulk"] is None
    assert diag["max_rhat"] is None
