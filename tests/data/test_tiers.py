from wcmodel.data.tiers import confederation, strength_band, match_type, is_covid


def test_confederation_lookup():
    assert confederation("Brazil") == "CONMEBOL"
    assert confederation("France") == "UEFA"
    assert confederation("Curacao") == "CONCACAF"


def test_unmapped_team_is_unknown_not_guessed():
    assert confederation("Atlantis") == "Unknown"


def test_strength_band_from_rank():
    assert strength_band(5) == "Elite"
    assert strength_band(20) == "Strong"
    assert strength_band(40) == "Mid"
    assert strength_band(80) == "Weak"
    assert strength_band(200) == "Minnow"


def test_match_type_normalization():
    assert match_type("FIFA World Cup") == "wc_finals"
    assert match_type("FIFA World Cup qualification") == "wc_qualifier"
    assert match_type("Friendly") == "friendly"
    assert match_type("UEFA Nations League") == "nations_league"
    assert match_type("Some Random Cup 1997") == "other"


def test_covid_flag():
    assert is_covid("2020-09-01") is True
    assert is_covid("2019-09-01") is False
    assert is_covid("2021-06-30") is True
