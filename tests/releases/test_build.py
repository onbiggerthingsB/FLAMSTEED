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


@pytest.mark.parametrize("bad", [
    "2026-09-20T00:00:00-05:00",   # offset form — as_of would not be canonical
    "2026-09-20",                  # date only
    "2026-09-20 00:00:00",         # space separator, no zone
    "2026-09-20T00:00:00",         # no zone marker
])
def test_cutoff_must_be_the_literal_canonical_form(bad):
    with pytest.raises(ValueError, match="literal form"):
        _build(_fx(), cutoff=bad)


def test_canonical_cutoff_form_accepted():
    assert _build(_fx(), cutoff="2026-09-20T00:00:00Z")["provenance"]["as_of"] == \
        "2026-09-20T00:00:00Z"


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


def test_coherence_gate_totals_escape_grid():
    """1X2 is coherent (0.35/0.35/0.30) but the totals ladder goes negative."""
    escape = np.array([[0.40, 0.10, 0.10],
                       [0.20, 0.15, 0.10],
                       [0.10, 0.05, -0.20]])
    with pytest.raises(ValueError, match="incoherent totals"):
        _build(_fx(), post=FakePost(escape))


def test_hygiene_rejects_newline_in_label():
    with pytest.raises(ValueError, match="newline in"):
        build_release(cutoff="2026-09-20T00:00:00Z", fixtures=_fx(), post=FakePost(),
                      posterior_key="deadbeef", window_label="Test\nwindow",
                      n_draws=4000, latest_result="2026-09-18")


def test_hygiene_rejects_newline_in_team_name():
    with pytest.raises(ValueError, match="newline in"):
        _build(_fx(home="A\rZ"))


def test_hygiene_rejects_formula_prefix_label():
    with pytest.raises(ValueError, match="formula-prefix"):
        build_release(cutoff="2026-09-20T00:00:00Z", fixtures=_fx(), post=FakePost(),
                      posterior_key="deadbeef", window_label="=cmd|' /c calc'!A1",
                      n_draws=4000, latest_result="2026-09-18")


@pytest.mark.parametrize("name", ["=A1", "+A1", "@SUM(1)"])
def test_hygiene_rejects_formula_prefix_team_name(name):
    with pytest.raises(ValueError, match="formula-prefix"):
        _build(_fx(home=name))


def test_hygiene_allows_hyphen_and_comma_names():
    """'-' and ',' are NOT banned: real names and 1-0 scores must survive."""
    post = FakePost()
    post._idx = {"Bosnia, Herzegovina": 0, "Guinea-Bissau": 1}
    rel = _build(_fx(home="Bosnia, Herzegovina", away="Guinea-Bissau"), post=post)
    assert rel["rows"][0]["home"] == "Bosnia, Herzegovina"
