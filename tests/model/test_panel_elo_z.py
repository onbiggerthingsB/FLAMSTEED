import numpy as np, pandas as pd
from wcmodel.model.panel import build_design

def _mp():
    # full match-panel schema build_design consumes (see panel.to_match_panel)
    return pd.DataFrame({
        "match_id":[1], "date":pd.to_datetime(["2025-06-10"]),
        "home_team":["A"], "away_team":["B"], "home_goals":[1], "away_goals":[0],
        "neutral":[False], "match_type":["friendly"], "weight":[1.0],
        "home_provisional":[False], "away_provisional":[False]})

def test_design_carries_elo_z_aligned_to_teams():
    d = build_design(_mp(), elo_z=np.array([0.7, -0.7]))   # teams sorted -> ["A","B"]
    assert d.teams == ["A","B"]
    assert d.elo_z is not None and d.elo_z.shape == (2,)
    assert d.elo_z[0] == 0.7 and d.elo_z[1] == -0.7

def test_elo_z_defaults_to_zeros_when_absent():
    d = build_design(_mp())
    assert d.elo_z is not None and np.allclose(d.elo_z, 0.0) and d.elo_z.shape == (2,)
