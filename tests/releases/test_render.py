"""Renderers: full envelope in BOTH formats, escaping, no betting vocabulary."""
import pytest

from wcmodel.releases.render import render_csv, render_html

REL = {
    "provenance": {"as_of": "2026-09-20T00:00:00Z", "posterior_key": "deadbeef",
                   "git": "abc1234", "is_synthetic": False, "n_sims": 0},
    "license": "CC BY 4.0 — free to republish with attribution and link",
    "model_name": "the model", "methodology_url": "https://example.org/m",
    "archive_url": "https://example.org/a", "window_label": "Test window",
    "n_draws": 4000,
    "data_source": {"name": "martj42/international_results (community dataset)",
                    "latest_result": "2026-09-18"},
    "rows": [{"date": "2026-09-21", "home": "S<enegal", "away": "Mozambique",
              "neutral": False,
              "one_x_two": {"home": 0.5731, "draw": 0.2513, "away": 0.1756},
              "totals": {"over_1_5": 0.61, "over_2_5": 0.34, "over_3_5": 0.15},
              "modal_score": "1-0", "modal_score_p": 0.181}],
}

_ENVELOPE = ("the model", "Test window", "2026-09-20T00:00:00Z", "deadbeef",
             "abc1234", "4,000", "CC BY 4.0", "https://example.org/m",
             "https://example.org/a", "martj42", "2026-09-18")


def test_html_full_envelope():
    h = render_html(REL)
    for needle in _ENVELOPE:
        assert needle in h, f"HTML missing {needle!r}"


def test_csv_full_envelope():
    c = render_csv(REL)
    for needle in ("the model", "Test window", "2026-09-20T00:00:00Z", "deadbeef",
                   "abc1234", "4000", "CC BY 4.0", "https://example.org/m",
                   "https://example.org/a", "martj42", "2026-09-18"):
        assert needle in c, f"CSV missing {needle!r}"


def test_html_escapes_team_names():
    h = render_html(REL)
    assert "S<enegal" not in h and "S&lt;enegal" in h


def test_html_probabilities_one_decimal():
    h = render_html(REL)
    assert "57.3%" in h and "0.5731" not in h


def test_csv_keeps_full_precision():
    c = render_csv(REL)
    data = [l for l in c.splitlines() if not l.startswith("#")]
    assert data[0].split(",")[4] == "p_home" or data[0].startswith("date")
    assert "0.5731" in c


def test_no_betting_vocabulary_in_either_output():
    from wcmodel.releases import BETTING_FIELD_DENYLIST
    for text in (render_html(REL).lower(), render_csv(REL).lower()):
        for word in BETTING_FIELD_DENYLIST:
            assert f" {word}" not in text and f'"{word}"' not in text, word
