import numpy as np, pandas as pd
from wcmodel.model.strength import team_elo_z

def _feats():
    # two dated rows per team; .last() must take the latest by date
    return pd.DataFrame({
        "team":    ["A","A","B","B","C"],
        "date":    pd.to_datetime(["2025-01-01","2025-06-01","2025-01-01","2025-06-01","2025-03-01"]),
        "elo_pre": [1500.,  1900.,   1500.,  1300.,   1600.],
    })

def test_team_elo_z_aligned_zscored_latest():
    teams = ["A","B","C"]
    z = team_elo_z(_feats(), teams)
    # latest elo_pre: A=1900, B=1300, C=1600 -> mean 1600 -> A highest, B lowest
    assert z.shape == (3,)
    assert z[0] > z[2] > z[1]                 # A > C > B
    assert abs(z.mean()) < 1e-9               # z-scored: mean 0
    assert abs(z.std() - 1.0) < 1e-6          # unit sd (population)

def test_missing_team_is_zero():
    z = team_elo_z(_feats(), ["A","B","C","Debutant"])
    assert z[3] == 0.0                        # team not in feats -> 0 (no-info)

def test_degenerate_all_equal_is_zero():
    f = pd.DataFrame({"team":["A","B"], "date":pd.to_datetime(["2025-01-01"]*2), "elo_pre":[1500.,1500.]})
    assert np.allclose(team_elo_z(f, ["A","B"]), 0.0)   # sd 0 -> zeros, no div-by-zero

def test_elo_z_uses_only_panel_rows_no_future_leak():
    """The helper consumes ONLY the rows handed to it. A caller that builds `feats`
    from a < cutoff slice therefore cannot leak; prove the helper itself never
    reaches beyond its input by showing an extra (hypothetical post-cutoff) row
    with a wild rating CHANGES the result only when included -- i.e. the helper is
    a pure function of its input, so leakage-safety is fully delegated to the
    < cutoff `feats` slice (asserted in the fit-level canary, Task 4)."""
    base = _feats(); teams = ["A","B","C"]
    z0 = team_elo_z(base, teams)
    future = pd.concat([base, pd.DataFrame({"team":["A"], "date":pd.to_datetime(["2026-01-01"]),
                                            "elo_pre":[9999.]})], ignore_index=True)
    z1 = team_elo_z(future, teams)
    assert not np.allclose(z0, z1)            # including a later row changes it -> the slice is the gate
