"""Payload gates: cutoff form, PIT (+control), unknown teams, coherence
(incl. NaN + negative controls), betting-key scan, envelope + freshness."""
import numpy as np
import pandas as pd
import pytest

from wcmodel.releases.build import build_release


class FakePost:
    _idx = {"A": 0, "B": 1}

    def __init__(self, grid=None):
        self._g = grid if grid is not None else np.array([[0.10, 0.20], [0.30, 0.40]])

    def predict_scoreline(self, home, away, neutral=False, max_goals=10, **kw):
        return self._g


def _fx(date="2026-09-21", home="A", away="B"):
    return pd.DataFrame({"date": [pd.Timestamp(date)], "home": [home],
                         "away": [away], "neutral": [False]})


def _build(fx, post=None, cutoff="2026-09-20T00:00:00Z"):
    return build_release(cutoff=cutoff, fixtures=fx, post=post or FakePost(),
                         posterior_key="deadbeef", window_label="Test window",
                         n_draws=4000, latest_result="2026-09-18")


def test_envelope_freshness_and_rows():
    rel = _build(_fx())
    assert rel["provenance"]["as_of"] == "2026-09-20T00:00:00Z"
    assert rel["provenance"]["posterior_key"] == "deadbeef"
    assert rel["n_draws"] == 4000
    assert rel["data_source"]["latest_result"] == "2026-09-18"
    assert "martj42" in rel["data_source"]["name"]
    assert len(rel["rows"]) == 1


def test_cutoff_must_be_utc_midnight():
    with pytest.raises(ValueError, match="UTC midnight"):
        _build(_fx(), cutoff="2026-09-20T15:30:00Z")


def test_pit_guard_rejects_past_fixture():
    with pytest.raises(ValueError, match="before the release cutoff"):
        _build(_fx("2026-09-19"))


def test_pit_guard_allows_same_day():
    assert len(_build(_fx("2026-09-20"))["rows"]) == 1


def test_unknown_team_gate_lists_all():
    fx = pd.DataFrame({"date": [pd.Timestamp("2026-09-21")] * 2,
                       "home": ["X", "A"], "away": ["B", "Y"],
                       "neutral": [False, False]})
    with pytest.raises(ValueError, match=r"\['X', 'Y'\]"):
        _build(fx)


def test_coherence_gate_bad_sum():
    with pytest.raises(ValueError, match="incoherent 1X2"):
        _build(_fx(), post=FakePost(np.array([[0.10, 0.20], [0.30, 0.60]])))


def test_coherence_gate_nan():
    with pytest.raises(ValueError, match="incoherent 1X2"):
        _build(_fx(), post=FakePost(np.array([[np.nan, 0.20], [0.30, 0.50]])))


def test_coherence_gate_negative_component():
    # components sum to 1.0 but one is negative — must still trip
    with pytest.raises(ValueError, match="incoherent 1X2"):
        _build(_fx(), post=FakePost(np.array([[0.60, 0.70], [-0.40, 0.10]])))
