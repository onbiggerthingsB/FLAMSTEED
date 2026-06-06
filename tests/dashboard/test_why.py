import numpy as np
from wcmodel.dashboard.why import team_strength, xg_or_gap


class _FakePost:
    teams = ["Spain", "Morocco"]
    _idx = {"Spain": 0, "Morocco": 1}
    def _post(self, name):
        rng = np.random.default_rng(0)
        if name == "att":
            return np.vstack([rng.normal(0.4, 0.1, 200), rng.normal(-0.2, 0.1, 200)])
        return np.vstack([rng.normal(0.1, 0.1, 200), rng.normal(-0.1, 0.1, 200)])


def test_team_strength_carries_mean_and_94pct_hdi():
    s = team_strength(_FakePost(), "Spain")
    assert "attack" in s and "defense" in s
    lo, hi = s["attack"]["ci"]
    assert lo < s["attack"]["value"] < hi
    assert s["attack"]["value"] > 0.2


def test_xg_is_coverage_gated_never_imputed():
    assert xg_or_gap(xg=1.7, covered=True) == {"value": 1.7}
    g = xg_or_gap(xg=None, covered=False)
    assert g["coverage_gap"] is True and g["value"] is None
