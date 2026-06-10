"""PRODUCTION-FIDELITY regression (the coarse-fit confound, caught 2026-06-10).

``build_snapshot`` used to hardcode dev-coarse fit defaults (``draws=200,
advi_iters=2000``) when the caller passed no ``fit_kwargs``. Both production
entrypoints (``scripts/build_real_snapshot.py``, ``scripts/daily_update.py``)
passed none — so EVERY production bundle was built from an under-converged
ADVI fit, which flattens the model toward uniform (the documented coarse-fit
confound; the staged champion board read Spain ~12% where the true
production-fidelity posterior gives ~19%).

The contract pinned here: with NO ``fit_kwargs``, ``build_snapshot`` must
request EXACTLY the production inference params from ``config["model"]
["inference"]``. Explicit ``fit_kwargs`` still win (the tests' tiny fits and
the canaries' distinct cache_dirs keep working).
"""
import pytest

import wcmodel.dashboard.build as build_mod
import wcmodel.model.cache as model_cache  # cached_fit is imported function-locally in build.py


class _StopAfterCapture(RuntimeError):
    """Abort build_snapshot right after the fit call — we only test the kwargs."""


def _capture_cached_fit(captured):
    def _fake(*, cutoff, store, backend, draws, seed, advi_iters, cache_dir, config):
        captured.update(backend=backend, draws=draws, seed=seed,
                        advi_iters=advi_iters)
        raise _StopAfterCapture()
    return _fake


def _cfg():
    from wcmodel.config import load_config
    return load_config()


def test_no_fit_kwargs_requests_production_inference(monkeypatch, tmp_path):
    cfg = _cfg()
    captured: dict = {}
    monkeypatch.setattr(model_cache, "cached_fit", _capture_cached_fit(captured))
    with pytest.raises(_StopAfterCapture):
        build_mod.build_snapshot("2026-06-07T00:00:00Z", store=object(),
                                 config=cfg, items=[], out_root=tmp_path)
    inf = cfg["model"]["inference"]
    assert captured["draws"] == inf["draws"], (
        f"build_snapshot requested draws={captured['draws']} but production "
        f"config says {inf['draws']} — the coarse-fit confound is back")
    assert captured["advi_iters"] == inf["advi_iters"]
    assert captured["backend"] == inf["backend"]
    assert captured["seed"] == cfg["seed"]


def test_explicit_fit_kwargs_still_win(monkeypatch, tmp_path):
    cfg = _cfg()
    captured: dict = {}
    monkeypatch.setattr(model_cache, "cached_fit", _capture_cached_fit(captured))
    with pytest.raises(_StopAfterCapture):
        build_mod.build_snapshot("2026-06-07T00:00:00Z", store=object(),
                                 config=cfg, items=[], out_root=tmp_path,
                                 fit_kwargs={"draws": 60, "advi_iters": 1500,
                                             "seed": 0})
    assert captured["draws"] == 60          # tests' tiny fits unaffected
    assert captured["advi_iters"] == 1500
    assert captured["seed"] == 0
