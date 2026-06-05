"""Content-addressed posterior cache (spec 4.4).

A Bayesian fit (``scoreline.fit`` -> ``Posterior``) is expensive (ADVI/MCMC) and
the walk-forward backtest refits at many cutoffs, so each fit is cached on disk.
The cache is CONTENT-ADDRESSED: the key is a hash of EVERYTHING that determines
the posterior -- the cutoff, the leakage-safe feature-data hash (so a new/changed
result -> different key), the FULL resolved ``model`` config block (likelihood,
prior, widening, inference), the ``elo`` + ``windows`` blocks (they change the
features and the provisional set), the inference knobs actually used (backend,
draws, tune, seed, advi_iters), the resolved likelihood, and the git commit. A
change to ANY of these yields a different key -> a miss. The cache therefore NEVER
serves a stale posterior (a stale serve would silently corrupt downstream betting
decisions); stale-posterior bugs come from an INCOMPLETE key, so the key here is
deliberately exhaustive.

On a MISS we ``fit`` and persist two files keyed by the content hash:

* ``posterior-<key>.nc`` -- the posterior group, written as netCDF.
* ``posterior-<key>.meta.json`` -- the full keyed params PLUS ``teams`` /
  ``likelihood`` / ``provisional_teams`` so a HIT reconstructs the complete
  ``Posterior`` from disk WITHOUT recomputing features/Elo (a hit is just: load
  the netCDF + read the meta JSON; no compute).

Serialization note (verified against the INSTALLED arviz 1.1.0 / pymc 6.0.1):
arviz 1.1.0 made ``InferenceData`` an xarray ``DataTree``. There is NO
``az.to_netcdf`` in this version, and ``DataTree.to_netcdf`` only supports the
NETCDF4 format (engine ``netcdf4``/``h5netcdf``) -- neither backend is installed
here, so the spec's ``az.to_netcdf`` path is unavailable. We instead persist the
posterior group as a plain xarray ``Dataset`` via the always-available ``scipy``
NETCDF3 engine, and reload it into a one-group ``DataTree`` whose ``.posterior``
is exactly what ``Posterior.predict_*`` reads. All posterior variables/coords are
float64/int64 (NETCDF3-safe); only the arviz metadata ATTRS contain strings/lists
(unsupported by NETCDF3), and predictions never read those attrs, so they are
dropped before writing. This round-trip is BIT-IDENTICAL: cached ``predict_1x2``
matches a fresh fit to 0.0 (verified << 1e-9).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import arviz as az  # noqa: F401  (kept for parity with the spec; reload uses xarray)
import pandas as pd
import xarray as xr

from wcmodel.config import load_config
from wcmodel.data import features
from wcmodel.data.cache import _git_commit, content_key
from wcmodel.model.panel import to_match_panel
from wcmodel.model.posterior import Posterior
from wcmodel.model.scoreline import fit


def _feature_hash(cutoff, store, cfg) -> str:
    """Stable 16-hex hash of the leakage-safe match panel at ``cutoff``.

    Hashes the SAME panel ``fit`` consumes (``to_match_panel(features.build(
    cutoff, store, cfg))``), so a new or revised result before the cutoff (which
    would change the fit) changes the hash -> a different key -> a miss. Built off
    the row-and-index content hash so column/row order is irrelevant only insofar
    as pandas' object hash is order-sensitive on rows -- the panel is emitted in a
    deterministic order by ``to_match_panel`` (reset_index), so the hash is
    reproducible across runs.
    """
    mp = to_match_panel(features.build(cutoff, store, cfg))
    blob = pd.util.hash_pandas_object(mp, index=True).values.tobytes()
    return hashlib.sha256(blob).hexdigest()[:16]


def _posterior_to_netcdf(post: Posterior, path: Path) -> None:
    """Persist the posterior group as scipy NETCDF3 (see module docstring).

    The arviz DataTree node is converted to a plain ``Dataset`` and its
    string/list attrs (arviz provenance metadata, unsupported by NETCDF3 and
    unused by predictions) are stripped before writing.
    """
    ds = post.idata.posterior.to_dataset().copy()
    ds.attrs = {}
    for var in ds.data_vars.values():
        var.attrs = {}
    for coord in ds.coords.values():
        coord.attrs = {}
    ds.to_netcdf(path, engine="scipy")


def _posterior_from_netcdf(path: Path, *, teams, likelihood, provisional_teams,
                           cfg) -> Posterior:
    """Reconstruct a ``Posterior`` from a cached netCDF + meta fields.

    Reloads the posterior ``Dataset`` (scipy engine) into a one-group
    ``DataTree`` so ``Posterior._post`` (``idata.posterior[name].stack(...)``)
    works exactly as on a fresh fit. No features/Elo recompute -- ``teams`` /
    ``likelihood`` / ``provisional_teams`` come straight from the meta JSON.

    POSTERIOR-ONLY (NETCDF3 limitation). Only the ``posterior`` group is
    persisted/reloaded; ``sample_stats`` and ``observed_data`` are NOT cached.
    The returned ``Posterior.idata`` therefore has NO ``sample_stats`` group, so
    a divergence check like ``idata.sample_stats.get("diverging", ...).sum()``
    would silently see nothing (effectively 0) on a CACHED fit -- masking real
    NUTS divergences. Divergence diagnostics and posterior-predictive checks MUST
    be run on a FRESH fit (see ``cached_fit``).
    """
    ds = xr.open_dataset(path, engine="scipy").load()
    idata = xr.DataTree.from_dict({"posterior": ds})
    return Posterior(
        idata, teams, likelihood,
        provisional_teams=set(provisional_teams), config=cfg,
    )


def _cache_key_params(*, cutoff, store, backend, draws, seed, advi_iters,
                      likelihood, tune, cfg) -> dict:
    """Build the exhaustive content-key params for a posterior fit.

    D6: ``elo`` is now keyed from the PASSED ``cfg`` (not the global
    ``load_config()["elo"]``). ``compute_elo_history`` / ``count_volatility_arm``
    are config-threaded as of Phase-4 Task 0, so the elo that ACTUALLY determines
    the posterior is ``cfg["elo"]`` — keying that makes a caller-supplied custom
    ``cfg.elo`` (e.g. a lockbox K/T sweep) invalidate the cache correctly and
    forbids recording an elo the computation never used (the P2-T8 stale-serve
    lesson). Every other field is unchanged from the original exhaustive key.
    """
    return {
        "cutoff": str(pd.Timestamp(cutoff)),
        "likelihood": likelihood,
        "backend": backend,
        "draws": draws,
        "tune": tune,
        "seed": seed,
        "advi_iters": advi_iters,
        "model": cfg["model"],
        "elo": cfg["elo"],                       # D6: threaded cfg, not global disk
        "windows": cfg["windows"],
        "feature_hash": _feature_hash(cutoff, store, cfg),
        "git": _git_commit(),
    }


def cached_fit(*, cutoff, store, backend, draws, seed, advi_iters, cache_dir,
               likelihood=None, tune=None, config=None):
    """Fit ``scoreline.fit`` through the content-addressed posterior cache.

    Returns ``(Posterior, {"cache_hit": bool, "key": str})``. On a HIT the
    Posterior is rebuilt from disk (netCDF + meta JSON) with NO recompute; on a
    MISS we fit, persist, and return ``cache_hit=False``.

    WARNING -- the cached (HIT) ``Posterior`` is POSTERIOR-ONLY. The netCDF
    persists ONLY the ``posterior`` group (NETCDF3 limitation, see module
    docstring); ``sample_stats`` (NUTS ``diverging``, energy, tree depth, ...) and
    ``observed_data`` are NOT cached and are absent from a reconstructed fit. So
    divergence diagnostics (e.g. ``idata.sample_stats["diverging"].sum()``) and
    posterior-predictive checks would silently return nothing on a CACHED fit,
    masking real divergences. Any such diagnostic -- notably the T10 calibration
    task -- MUST be run on a FRESH fit (``scoreline.fit`` directly, or a
    guaranteed-MISS ``cached_fit``), NEVER routed through a cache hit. (Cached
    PREDICTIONS are bit-identical to a fresh fit; this caveat is strictly about
    the sampler-diagnostic groups, which predictions do not use.)
    """
    cfg = config or load_config()
    likelihood = likelihood or cfg["model"]["likelihood"]
    tune = tune if tune is not None else cfg["model"]["inference"]["tune"]
    # The key includes EVERYTHING that determines the posterior (any change ->
    # different key -> a miss, never a stale serve). `_cache_key_params` builds it.
    # D6 (Phase-4 Task 0): `elo` is keyed from the PASSED `cfg` now that
    # `compute_elo_history`/`count_volatility_arm` are config-threaded — so a
    # caller-supplied custom `cfg.elo` (a lockbox K/T sweep) invalidates the cache
    # correctly and CANNOT record an elo the computation never used.
    params = _cache_key_params(
        cutoff=cutoff, store=store, backend=backend, draws=draws, seed=seed,
        advi_iters=advi_iters, likelihood=likelihood, tune=tune, cfg=cfg,
    )
    key = content_key("posterior", params)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    nc = cache_dir / f"posterior-{key}.nc"
    meta_path = cache_dir / f"posterior-{key}.meta.json"

    if nc.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        post = _posterior_from_netcdf(
            nc, teams=meta["teams"], likelihood=meta["likelihood"],
            provisional_teams=meta["provisional_teams"], cfg=cfg,
        )
        return post, {"cache_hit": True, "key": key}

    post = fit(
        cutoff, store, likelihood=likelihood, backend=backend, draws=draws,
        tune=tune, seed=seed, advi_iters=advi_iters, config=cfg,
    )
    _posterior_to_netcdf(post, nc)
    # Persist teams / likelihood / provisional_teams so a HIT reconstructs the
    # full Posterior without recomputing features/Elo.
    meta_path.write_text(json.dumps(
        {**params, "teams": list(post.teams), "likelihood": post.likelihood,
         "provisional_teams": sorted(post.provisional_teams)},
        indent=2, default=str,
    ))
    return post, {"cache_hit": False, "key": key}
