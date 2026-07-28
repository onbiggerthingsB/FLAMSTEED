"""Scaffold: public constants + the shared betting-field denylist."""
from wcmodel import releases


def test_release_constants_exist_and_are_nonempty_strings():
    for name in ("MODEL_NAME", "LICENSE_STAMP", "METHODOLOGY_URL",
                 "ARCHIVE_URL", "DATA_SOURCE_NAME"):
        val = getattr(releases, name)
        assert isinstance(val, str) and val, f"{name} must be a non-empty str"


def test_license_is_cc_by_4():
    assert "CC BY 4.0" in releases.LICENSE_STAMP


def test_no_tournament_marks_in_model_name():
    banned = ("world cup", "fifa", "uefa", "afc", "euro", "copa", "afcon")
    low = releases.MODEL_NAME.lower()
    assert not any(b in low for b in banned)


def test_betting_denylist_covers_known_bundle_fields():
    # The fields production build.py actually attaches to forecast surfaces.
    for key in ("edge", "staked", "stake_signal", "entry_odds", "clv",
                "roi", "kelly", "bankroll", "value_bets", "odds",
                "market_1x2", "beat_close_rate", "avg_clv"):
        assert key in releases.BETTING_FIELD_DENYLIST


def test_archive_url_uses_current_github_owner():
    assert "onbiggerthingsB" in releases.ARCHIVE_URL   # repo moved 2026-07-25


def test_wc2026_archive_doi_is_pinned_zenodo_doi():
    # Published 2026-07-28; a DOI never changes, so this is an exact pin.
    assert releases.WC2026_ARCHIVE_DOI == "10.5281/zenodo.21641225"
    assert releases.WC2026_ARCHIVE_DOI_URL == (
        "https://doi.org/" + releases.WC2026_ARCHIVE_DOI)
