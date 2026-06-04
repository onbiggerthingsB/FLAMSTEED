import pandas as pd
from wcmodel.model.volatility_diagnostic import count_volatility_arm


def test_counts_only_volatility_arm_not_few_games(small_store):
    res = count_volatility_arm(
        store=small_store, cutoff="2024-06-01",
        field_teams=["Brazil", "Argentina", "Croatia", "Mexico"],
    )
    assert set(res.columns) >= {"team", "games", "recent_volatility",
                                "volatility_flag", "few_games_flag"}
    vol = res[res["volatility_flag"]]
    assert (vol["games"] >= 5).all()
