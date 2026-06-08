import numpy as np
from wcmodel.dashboard.fixtures import scoreline_shortlist, fixture_forecast


class _FakePost:
    teams = ["Spain", "Morocco"]
    # Mirrors the real Posterior signature incl. the T5 host_factor kwarg (a host's home
    # game carries k*home_adv); this fake is grid-fixed, so it ignores host_factor but
    # must ACCEPT it to match the production signature fixture_forecast now calls.
    def predict_scoreline(self, home, away, neutral=False, max_goals=10,
                          covariates=None, host_factor=None):
        g = np.zeros((4, 4)); g[1, 0] = 0.5; g[2, 1] = 0.3; g[0, 0] = 0.2
        return g
    def predict_1x2(self, home, away, neutral=False, max_goals=10,
                    covariates=None, host_factor=None):
        return {"home": 0.8, "draw": 0.2, "away": 0.0}


def test_shortlist_is_sorted_and_carries_probabilities():
    sl = scoreline_shortlist(_FakePost().predict_scoreline("Spain", "Morocco"), top=3)
    assert sl[0] == {"home_goals": 1, "away_goals": 0, "prob": 0.5}
    assert [s["prob"] for s in sl] == sorted([s["prob"] for s in sl], reverse=True)


def test_fixture_forecast_pairs_score_with_its_probability_never_naked():
    f = fixture_forecast(_FakePost(), home="Spain", away="Morocco", neutral=True, max_goals=3)
    assert f["most_likely"] == {"home_goals": 1, "away_goals": 0, "prob": 0.5}
    assert f["one_x_two"] == {"home": 0.8, "draw": 0.2, "away": 0.0}
    assert len(f["grid"]) == 4 and len(f["grid"][0]) == 4
    assert abs(sum(s["prob"] for s in f["shortlist"]) - (0.5 + 0.3 + 0.2)) < 1e-9


from wcmodel.dashboard.fixtures import build_schedule


def test_build_schedule_orders_all_fixtures_and_tags_stage():
    fixtures = [
        {"home": "Spain", "away": "Morocco", "date": "2026-06-11", "group": "A"},
        {"home": "Brazil", "away": "Serbia", "date": "2026-06-12", "group": "B"},
    ]
    sched = build_schedule(fixtures, cutoff="2026-06-10T00:00:00Z")
    assert [r["date"] for r in sched] == ["2026-06-11", "2026-06-12"]
    assert all(r["stage"] == "group" for r in sched)
    assert sched[0]["status"] == "upcoming"
