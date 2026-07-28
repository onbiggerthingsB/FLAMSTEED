"""One RPS convention across the codebase (OA finding 16)."""
import numpy as np

from wcmodel.model.calibration import rps as canonical_rps
from wcmodel.backtest.devig_select import _rps as devig_rps
from wcmodel.backtest.baselines import rps as baselines_rps


def test_devig_rps_matches_canonical_on_random_forecasts():
    rng = np.random.default_rng(0)
    for _ in range(200):
        p = rng.dirichlet([1.0, 1.0, 1.0])
        outcome = ("home", "draw", "away")[rng.integers(0, 3)]
        probs_dict = {"home": p[0], "draw": p[1], "away": p[2]}
        assert abs(devig_rps(list(p), outcome)
                   - canonical_rps(probs_dict, outcome)) < 1e-12


def test_baselines_rps_matches_canonical_on_random_forecasts():
    # Third implementation (the backtest/headroom/ablation scoring path) — it
    # must obey the SAME convention, else "one canonical RPS" is only partial.
    rng = np.random.default_rng(1)
    for _ in range(200):
        p = rng.dirichlet([1.0, 1.0, 1.0])
        outcome = ("home", "draw", "away")[rng.integers(0, 3)]
        probs_dict = {"home": p[0], "draw": p[1], "away": p[2]}
        assert abs(baselines_rps(probs_dict, outcome)
                   - canonical_rps(probs_dict, outcome)) < 1e-12


def test_worked_example_half_normalized():
    # Docstring example from calibration.py: canonical value 0.445 (in [0,1]).
    probs = {"home": 0.5, "draw": 0.3, "away": 0.2}
    assert abs(canonical_rps(probs, "away") - 0.445) < 1e-9
    assert abs(devig_rps([0.5, 0.3, 0.2], "away") - 0.445) < 1e-9
