"""Publisher projection: key stripping plus wire-string enforcement."""

from wcmodel.releases import BETTING_FIELD_DENYLIST, BETTING_VOCAB
from wcmodel.releases.projection import (
    normalize_publisher_provenance,
    scan_betting_keys,
    scan_betting_strings,
    strip_betting,
)


def test_denylist_uses_real_field_names():
    for key in ("market_1x2", "beat_close_rate", "avg_clv"):
        assert key in BETTING_FIELD_DENYLIST
    assert "avg_clv_pct" not in BETTING_FIELD_DENYLIST
    assert "betting" in BETTING_VOCAB


def test_strip_removes_market_and_edge():
    row = {
        "forecast_summary": {
            "one_x_two": {"home": 0.5},
            "market_1x2": {"home": 0.48},
        },
        "edge": {"staked": 1.0},
    }
    out = strip_betting(row)
    assert "edge" not in out
    assert "market_1x2" not in out["forecast_summary"]


def test_scan_keys_reports_all_offending_keys():
    assert scan_betting_keys(
        {"a": {"edge": 1}, "b": [{"odds": 2, "ok": {"clv": 3}}]}
    ) == {"edge", "odds", "clv"}
    assert scan_betting_keys({"clean": [1, 2, {"x": "y"}]}) == set()


def test_scan_strings_catches_the_real_banner():
    """The failure key-only stripping misses: the banner VALUE."""
    meta = {
        "provenance": {
            "banner": (
                "DRY-RUN · SYNTHETIC ODDS · NOT REAL — "
                "no real odds were sourced, no bet was placed"
            )
        }
    }
    hits = scan_betting_strings(meta)
    assert hits and "SYNTHETIC ODDS" in hits[0]


def test_scan_strings_no_false_positive_on_substrings():
    assert scan_betting_strings({"team": "Real Betis", "note": "Roieland"}) == []
    assert scan_betting_strings({"x": ["clean", {"y": "Tibet"}]}) == []
    assert scan_betting_strings({"banner": "not betting advice"}) == []
    assert scan_betting_strings({"banner": "betting tips"}) == ["betting tips"]


def test_normalize_provenance_replaces_banner_and_drops_taint():
    meta = {
        "provenance": {
            "as_of": "2027-01-07T00:00:00Z",
            "is_synthetic": True,
            "banner": "DRY-RUN · SYNTHETIC ODDS · NOT REAL",
        },
        "data": {"markets": []},
    }
    out = normalize_publisher_provenance(meta)
    assert scan_betting_strings(out) == []
    assert "probabilities, not picks" in out["provenance"]["banner"]
    assert "is_synthetic" not in out["provenance"]
    assert out["provenance"]["as_of"] == "2027-01-07T00:00:00Z"
