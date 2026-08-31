"""Adversarial synthetic tests for the unfrozen betting-evaluation core."""

from __future__ import annotations

from fractions import Fraction

import pytest

from epl import beteval


def _probabilities():
    return {"home": "0.50", "draw": "0.25", "away": "0.25"}


def _offer(
    book: str = "book-a", order: int = 0,
    odds: dict[str, str] | None = None, *, venue: str = "bookmaker",
    commission: str = "0",
) -> beteval.EligibleEntryOffer:
    return beteval.EligibleEntryOffer(
        book=book,
        book_order=order,
        odds_raw=odds or {"home": "2.10", "draw": "4.20", "away": "3.50"},
        venue_type=venue,
        commission_rate=commission,
    )


def _clock_case() -> dict[str, str]:
    return {
        "kickoff_as_known": "2026-09-03T12:00:00Z",
        "entry_target": "2026-09-01T12:00:00Z",
        "model_sealed_at": "2026-09-01T11:30:00Z",
        "first_entry_request_at": "2026-09-01T12:00:00Z",
        "entry_provider_at": "2026-09-01T12:00:00Z",
        "entry_observed_at": "2026-09-01T12:10:00Z",
        "actual_kickoff": "2026-09-03T12:00:00Z",
        "close_provider_at": "2026-09-03T11:50:00Z",
        # Retrieval after kickoff is explicitly permitted when provider time
        # remains the valid pre-kickoff close.
        "close_observed_at": "2026-09-03T12:01:00Z",
    }


def _identity(fixture_id: str = "fixture-1", *, home: str = "arsenal",
              away: str = "chelsea") -> beteval.FixtureIdentity:
    return beteval.FixtureIdentity(
        fixture_id=fixture_id,
        competition="English Premier League",
        market="full-time 90-minute 1X2",
        home=home,
        away=away,
    )


def test_module_is_explicitly_unfrozen_and_does_not_export_a_ledger():
    assert beteval.BUILD_STATE == "BUILT_UNFROZEN"
    assert not hasattr(beteval, "HashChainedEventStream")
    assert not hasattr(beteval, "OutcomeTriple")
    assert not hasattr(beteval, "QuoteReference")
    assert not hasattr(beteval, "flat_roi")


@pytest.mark.parametrize("bad", ["HOME", "h", 0, None])
def test_outcome_vocabulary_is_exact(bad):
    with pytest.raises(beteval.SchemaError, match="exactly one"):
        beteval.validate_outcome(bad)
    assert beteval.validate_outcome("home") == "home"


def test_probability_and_odds_triples_refuse_missing_or_extra_outcomes():
    with pytest.raises(beteval.SchemaError, match="missing=.*away"):
        beteval.validate_probabilities({"home": "0.5", "draw": "0.5"})
    with pytest.raises(beteval.SchemaError, match="extra=.*other"):
        beteval.validate_odds({
            "home": "2", "draw": "3.5", "away": "4", "other": "2",
        })


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_prices_refuse(bad):
    with pytest.raises(beteval.SchemaError, match="finite decimal"):
        beteval.validate_odds({"home": bad, "draw": "3.5", "away": "4"})


def test_price_strings_must_be_decimal_not_fraction_notation():
    with pytest.raises(beteval.SchemaError, match="finite decimal string"):
        beteval.validate_odds({"home": "21/10", "draw": "3.5", "away": "4"})


def test_binary_float_prices_refuse_until_decimal_law_is_amended():
    with pytest.raises(beteval.SchemaError, match="binary float"):
        beteval.validate_odds({"home": 2.0, "draw": "3.5", "away": "4"})


def test_price_bounds_and_underround_tolerance_are_exact():
    # Reciprocal sum exactly 1.20 is valid.
    assert beteval.reciprocal_sum({
        "home": "2.5", "draw": "2.5", "away": "2.5",
    }) == Fraction(6, 5)
    with pytest.raises(beteval.SchemaError, match="exceeds 1.20"):
        beteval.validate_odds({"home": "2", "draw": "2.5", "away": "3"})

    # Exactly 1e-9 below one is within the arithmetic tolerance; any further
    # below refuses as malformed.
    accepted = Fraction(3_000_000_000, 999_999_999)
    beteval.validate_odds({"home": accepted, "draw": accepted, "away": accepted})
    refused = Fraction(3_000_000_000, 999_999_998)
    with pytest.raises(beteval.SchemaError, match="underround"):
        beteval.validate_odds({"home": refused, "draw": refused, "away": refused})


@pytest.mark.parametrize("bad", ["1", "0", "-2"])
def test_each_price_must_be_strictly_greater_than_one(bad):
    with pytest.raises(beteval.SchemaError, match="strictly greater"):
        beteval.validate_odds({"home": bad, "draw": "3.5", "away": "4"})


def test_utc_parser_requires_explicit_z_and_compares_subseconds_exactly():
    a = beteval.utc_instant("2026-09-01T00:00:00.0000001Z")
    b = beteval.utc_instant("2026-09-01T00:00:00.000001Z")
    assert b - a == Fraction(9, 10_000_000)
    with pytest.raises(beteval.ClockError, match="explicit Z"):
        beteval.utc_instant("2026-09-01T00:00:00+00:00")
    with pytest.raises(beteval.ClockError, match="valid UTC"):
        beteval.utc_instant("2026-02-30T00:00:00Z")
    with pytest.raises(beteval.ClockError, match="explicit Z"):
        beteval.utc_instant("٢٠٢٦-09-01T00:00:00Z")


def test_model_clock_accepts_all_documented_equalities():
    seal = beteval.validate_model_seal(
        model_arm="dc_native",
        expected_arm="dc_native",
        probabilities=_probabilities(),
        cutoff="2026-09-01T11:30:00Z",
        observed_by="2026-09-01T11:30:00Z",
        model_issued_at="2026-09-01T11:30:00Z",
        kickoff_as_known="2026-09-03T12:00:00Z",
        entry_target="2026-09-01T12:00:00Z",
        sealed_at="2026-09-01T11:30:00Z",
    )
    assert seal.model_arm == "dc_native"
    assert sum(seal.probabilities.as_dict().values()) == 1


def test_entry_target_is_bound_exactly_to_known_kickoff_minus_48_hours():
    assert beteval.validate_entry_target(
        kickoff_as_known="2026-09-03T12:00:00Z",
        entry_target="2026-09-01T12:00:00Z",
    ) == beteval.utc_instant("2026-09-01T12:00:00Z")
    with pytest.raises(beteval.ClockError, match="minus 48 hours"):
        beteval.validate_entry_target(
            kickoff_as_known="2026-09-03T12:00:00Z",
            entry_target="2026-09-01T12:00:00.000001Z",
        )


def test_model_clock_refuses_one_microsecond_late_issue_or_durable_seal():
    common = {
        "model_arm": "dc_native",
        "expected_arm": "dc_native",
        "probabilities": _probabilities(),
        "cutoff": "2026-09-01T11:30:00Z",
        "observed_by": "2026-09-01T11:30:00Z",
        "kickoff_as_known": "2026-09-03T12:00:00Z",
        "entry_target": "2026-09-01T12:00:00Z",
        "sealed_at": "2026-09-01T11:30:00Z",
    }
    with pytest.raises(beteval.ClockError, match="model_late"):
        beteval.validate_model_seal(
            **common, model_issued_at="2026-09-01T11:30:00.000001Z",
        )
    with pytest.raises(beteval.ClockError, match="cannot precede"):
        beteval.validate_model_seal(
            **{
                **common,
                "model_issued_at": "2026-09-01T11:30:00Z",
                "sealed_at": "2026-09-01T11:29:59.999999Z",
            }
        )
    with pytest.raises(beteval.ClockError, match="durable no later"):
        beteval.validate_model_seal(
            **{
                **common,
                "model_issued_at": "2026-09-01T11:30:00Z",
                "sealed_at": "2026-09-01T11:30:00.000001Z",
            }
        )


@pytest.mark.parametrize("field", ["cutoff", "observed_by"])
def test_model_information_clocks_refuse_one_microsecond_after_issue(field):
    values = {
        "model_arm": "dc_native",
        "expected_arm": "dc_native",
        "probabilities": _probabilities(),
        "cutoff": "2026-09-01T11:30:00Z",
        "observed_by": "2026-09-01T11:30:00Z",
        "model_issued_at": "2026-09-01T11:30:00Z",
        "kickoff_as_known": "2026-09-03T12:00:00Z",
        "entry_target": "2026-09-01T12:00:00Z",
        "sealed_at": "2026-09-01T11:30:00Z",
    }
    values[field] = "2026-09-01T11:30:00.000001Z"
    with pytest.raises(beteval.ClockError, match=field):
        beteval.validate_model_seal(**values)


def test_model_seal_refuses_arm_and_probability_substitution():
    common = {
        "cutoff": "2026-09-01T11:00:00Z",
        "observed_by": "2026-09-01T11:00:00Z",
        "model_issued_at": "2026-09-01T11:30:00Z",
        "kickoff_as_known": "2026-09-03T12:00:00Z",
        "entry_target": "2026-09-01T12:00:00Z",
        "sealed_at": "2026-09-01T11:30:00Z",
    }
    with pytest.raises(beteval.SchemaError, match="model_arm_mismatch"):
        beteval.validate_model_seal(
            model_arm="shadow", expected_arm="dc_native",
            probabilities=_probabilities(), **common,
        )
    with pytest.raises(beteval.SchemaError, match="sum"):
        beteval.validate_model_seal(
            model_arm="dc_native", expected_arm="dc_native",
            probabilities={"home": "0.6", "draw": "0.3", "away": "0.2"},
            **common,
        )


def test_entry_and_close_window_equalities_are_inclusive():
    got = beteval.validate_quote_clocks(**_clock_case())
    assert got["entry_provider_at"] == got["entry_target"]
    assert got["effective_entry_at"] == got["entry_observed_at"]
    assert got["close_provider_at"] == got["actual_kickoff"] - 600


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("entry_target", "2026-09-01T12:00:00.000001Z"),
        ("entry_provider_at", "2026-09-01T11:59:59.999999Z"),
        ("entry_observed_at", "2026-09-01T12:10:00.000001Z"),
        ("close_provider_at", "2026-09-03T11:49:59.999999Z"),
        ("close_provider_at", "2026-09-03T11:59:00.000001Z"),
        ("model_sealed_at", "2026-09-01T12:00:00Z"),
    ],
)
def test_clock_windows_refuse_one_microsecond_violations(field, value):
    case = {**_clock_case(), field: value}
    with pytest.raises(beteval.ClockError):
        beteval.validate_quote_clocks(**case)


def test_commission_is_applied_once_to_exchange_winnings_only():
    assert beteval.net_entry_odds(
        "3.00", venue_type="exchange", commission_rate="0.05",
    ) == Fraction(29, 10)
    assert beteval.net_entry_odds(
        "3.00", venue_type="bookmaker", commission_rate="0",
    ) == 3
    with pytest.raises(beteval.SchemaError, match="bookmaker commission"):
        beteval.net_entry_odds(
            "3.00", venue_type="bookmaker", commission_rate="0.05",
        )


def test_exact_edge_at_threshold_is_a_one_unit_bet():
    decision = beteval.select_from_eligible_offers(
        "fixture-1", _probabilities(),
        [_offer(odds={"home": "2.04", "draw": "3.60", "away": "4.00"})],
    )
    assert decision.decision_status == "bet_intent"
    assert decision.selected_outcome == "home"
    assert decision.model_edge == Fraction(1, 50)
    assert decision.stake_units == 1


def test_tie_break_is_outcome_then_manifest_book_order():
    # home at 2.10 and draw at 4.20 both have exact +5% edge.  Outcome order
    # chooses home; identical prices at two books then choose lower book_order.
    decision = beteval.select_from_eligible_offers(
        "fixture-1", _probabilities(),
        [_offer("later", 1), _offer("earlier", 0)],
    )
    assert decision.selected_outcome == "home"
    assert decision.entry_book == "earlier"
    assert decision.model_edge == Fraction(1, 20)


def test_no_edge_and_missing_model_are_typed_zero_stake_rows():
    no_edge = beteval.select_from_eligible_offers(
        "fixture-1", _probabilities(),
        [_offer(odds={"home": "1.90", "draw": "3.60", "away": "3.80"})],
    )
    assert (no_edge.decision_status, no_edge.reason, no_edge.stake_units) == (
        "non_bet", "no_edge", 0,
    )
    missing = beteval.select_from_eligible_offers("fixture-2", None, [])
    assert (missing.decision_status, missing.reason, missing.stake_units) == (
        "failure", "model_missing", 0,
    )
    with pytest.raises(beteval.SchemaError, match="predecision reason"):
        beteval.predecision_failure_row("fixture-3", "invented_reason")


@pytest.mark.parametrize(
    "reason",
    ["close_quote_missing", "result_missing", "entry_book_void", "fixture_abandoned"],
)
def test_predecision_rows_refuse_close_result_and_void_reasons(reason):
    with pytest.raises(beteval.SchemaError, match="predecision reason"):
        beteval.predecision_failure_row("fixture-1", reason)


def test_empty_eligible_offer_set_is_not_mapped_to_an_invented_failure():
    with pytest.raises(beteval.SchemaError, match="cannot be classified"):
        beteval.select_from_eligible_offers("fixture-1", _probabilities(), [])


def test_selection_threshold_has_no_override_surface():
    with pytest.raises(TypeError, match="threshold"):
        beteval.select_from_eligible_offers(
            "fixture-1", _probabilities(), [_offer()], threshold="0.03",
        )


def test_public_threshold_rebinding_cannot_change_selection(monkeypatch):
    monkeypatch.setattr(beteval, "SELECTION_THRESHOLD", Fraction(99))
    decision = beteval.select_from_eligible_offers(
        "fixture-1", _probabilities(),
        [_offer(odds={"home": "2.04", "draw": "3.60", "away": "4.00"})],
    )
    assert decision.decision_status == "bet_intent"
    assert decision.selection_threshold == Fraction(1, 50)


def test_public_decision_row_refuses_impossible_status_combinations():
    with pytest.raises(beteval.SchemaError, match="represents only"):
        beteval.DecisionRow(
            fixture_id="fixture-1", decision_status="void",
            reason="entry_book_void", selected_outcome="home",
            entry_book="book-a", entry_odds_raw=Fraction(2),
            entry_odds_net=Fraction(2), model_edge=Fraction(1, 20),
            selection_threshold=beteval.SELECTION_THRESHOLD,
            stake_units=Fraction(0),
        )
    with pytest.raises(beteval.SchemaError, match="edge must meet"):
        beteval.DecisionRow(
            fixture_id="fixture-1", decision_status="bet_intent", reason=None,
            selected_outcome="home", entry_book="book-a",
            entry_odds_raw=Fraction(2), entry_odds_net=Fraction(2),
            model_edge=Fraction(1, 100),
            selection_threshold=beteval.SELECTION_THRESHOLD,
            stake_units=Fraction(1),
        )


def test_duplicate_book_or_manifest_position_refuses():
    with pytest.raises(beteval.SchemaError, match="duplicate book/order"):
        beteval.select_from_eligible_offers(
            "fixture-1", _probabilities(), [_offer("a", 0), _offer("b", 0)],
        )


def test_close_and_result_mutation_cannot_change_selection_positive_control_can():
    offers = [_offer()]
    before = beteval.select_from_eligible_offers(
        "fixture-1", _probabilities(), offers,
    )
    # Mutate both downstream quantities.  They can change CLV/P&L, but they
    # cannot be supplied to the selection function at all.
    close_a = {
        "home": "2.00", "draw": "3.60", "away": "4.00",
    }
    close_b = {
        "home": "2.20", "draw": "3.40", "away": "3.60",
    }
    assert beteval.economic_clv(before.entry_odds_net, close_a, "home") != (
        beteval.economic_clv(before.entry_odds_net, close_b, "home")
    )
    assert beteval.flat_pnl(before.entry_odds_net, "home", "home") != (
        beteval.flat_pnl(before.entry_odds_net, "home", "away")
    )
    after = beteval.select_from_eligible_offers(
        "fixture-1", _probabilities(), offers,
    )
    assert after == before

    moved_entry = beteval.select_from_eligible_offers(
        "fixture-1", _probabilities(),
        [_offer(odds={"home": "1.90", "draw": "3.60", "away": "3.80"})],
    )
    assert moved_entry != before
    assert moved_entry.decision_status == "non_bet"


def test_identity_refuses_cross_event_and_home_away_swap():
    identity = _identity()
    beteval.validate_entry_close_identity(identity, identity)

    with pytest.raises(beteval.IdentityError, match="same-event"):
        beteval.validate_entry_close_identity(identity, _identity("fixture-2"))
    with pytest.raises(beteval.IdentityError, match="same-event"):
        beteval.validate_entry_close_identity(
            identity, _identity(home="chelsea", away="arsenal"),
        )


def test_proportional_devig_economic_clv_and_flat_pnl_are_exact():
    close = beteval.proportional_close_devig({
        "home": "2.00", "draw": "4.00", "away": "4.00",
    })
    assert close == {
        "home": Fraction(1, 2),
        "draw": Fraction(1, 4),
        "away": Fraction(1, 4),
    }
    assert sum(close.values()) == 1
    assert beteval.economic_clv(
        "2.10", {"home": "2.00", "draw": "4.00", "away": "4.00"}, "home",
    ) == Fraction(1, 20)
    assert beteval.flat_pnl("2.50", "home", "home") == Fraction(3, 2)
    assert beteval.flat_pnl("2.50", "home", "away") == -1
    assert beteval.flat_pnl("2.50", "home", None, void=True) == 0


def test_scoring_refuses_normalized_probabilities_impersonating_raw_close_odds():
    with pytest.raises(beteval.SchemaError, match="strictly greater"):
        beteval.economic_clv(
            "2.10", {"home": "0.60", "draw": "0.20", "away": "0.20"}, "home",
        )


def test_scoring_revalidates_raw_close_triple_before_internal_devig():
    with pytest.raises(beteval.SchemaError, match="underround"):
        beteval.economic_clv(
            "2.10", {"home": "3.20", "draw": "4.00", "away": "4.00"}, "home",
        )


def test_unfrozen_derivation_retains_failure_and_missing_stage_rows():
    census = [
        {"fixture_id": "f1", "home": "a", "away": "b"},
        {"fixture_id": "f2", "home": "c", "away": "d"},
        {"fixture_id": "f3", "home": "e", "away": "f"},
    ]
    failure = {"fixture_id": "f2", "decision_status": "failure",
               "reason": "entry_quote_missing", "stake_units": "0"}
    derived = beteval.derive_unfrozen_evidence_rows(
        census,
        {"entry_decisions": [
            {"fixture_id": "f1", "decision_status": "non_bet", "reason": "no_edge"},
            failure,
        ]},
    )
    assert [row.fixture_id for row in derived] == ["f1", "f2", "f3"]
    assert derived[1].stages["entry_decisions"] == failure
    assert derived[2].stages["entry_decisions"] is None


def test_unfrozen_derivation_refuses_duplicate_and_cross_event_rows():
    census = [{"fixture_id": "f1"}]
    with pytest.raises(beteval.SchemaError, match="duplicate census"):
        beteval.derive_unfrozen_evidence_rows([*census, *census], {})
    with pytest.raises(beteval.SchemaError, match="duplicate entry"):
        beteval.derive_unfrozen_evidence_rows(
            census,
            {"entry": [{"fixture_id": "f1"}, {"fixture_id": "f1"}]},
        )
    with pytest.raises(beteval.IdentityError, match="non-census"):
        beteval.derive_unfrozen_evidence_rows(
            census, {"entry": [{"fixture_id": "other"}]},
        )
