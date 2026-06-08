"""Venue fidelity for the totals runner: genuine HOST games must NOT be forced neutral.

The runner previously hardcoded ``neutral=True`` for every fixture, zeroing the fitted ``home_adv``
even for ties where the listed home team genuinely hosts (Nations League / WCQ at the home ground).
``_fixture_neutral`` is the LOCAL (runner-only) venue lookup that fixes this WITHOUT touching the
shared ``STRATIFIED_MATCHES`` tuple arity (the ``accuracy`` subcommand still unpacks 5-tuples).
"""
import scripts.run_totals_backtest as runner
from scripts.clv_validation import STRATIFIED_MATCHES


def test_euro2024_marquee_games_are_neutral_ground():
    # Euro 2024 group games were played on neutral German grounds; the listed home team is NOT the
    # tournament host (Germany), so these are genuinely neutral.
    assert runner._fixture_neutral("Spain", "Croatia", "2024-06-15T16:00:00Z", "marquee", "x") is True
    assert runner._fixture_neutral("Italy", "Albania", "2024-06-15T19:00:00Z", "marquee", "x") is True


def test_nations_league_and_wcq_home_team_genuinely_hosts():
    # Nations League + WCQ ties are played at the listed home team's ground -> NOT neutral.
    assert runner._fixture_neutral("Germany", "Hungary", "2024-09-07T18:45:00Z", "mid", "x") is False
    assert runner._fixture_neutral("Kazakhstan", "Wales", "2025-09-04T14:00:00Z", "thin", "x") is False
    assert runner._fixture_neutral("Liechtenstein", "Belgium", "2025-09-04T18:45:00Z", "thin", "x") is False
    assert runner._fixture_neutral("Faroe Islands", "Croatia", "2025-09-05T18:45:00Z", "thin", "x") is False


def test_every_stratified_fixture_resolves_to_a_bool():
    # No fixture silently falls through to a wrong default; each resolves to an explicit bool.
    for h, a, ko, tier, sp in STRATIFIED_MATCHES:
        assert isinstance(runner._fixture_neutral(h, a, ko, tier, sp), bool)


def test_at_least_one_host_game_is_not_neutral():
    # The whole point of the fix: the curated set contains genuine host games that must NOT be
    # forced neutral (otherwise the model price the totals edge is compared against is mis-specified).
    flags = [runner._fixture_neutral(h, a, ko, tier, sp) for h, a, ko, tier, sp in STRATIFIED_MATCHES]
    assert any(f is False for f in flags), "expected >=1 genuine host (non-neutral) fixture"
