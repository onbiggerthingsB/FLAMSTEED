"""Unfrozen, network-free primitives for the EPL betting-evidence design.

Build state: ``BUILT_UNFROZEN``.

Only preregistration rules with an unambiguous representation are implemented
here.  In particular this module deliberately does *not* define canonical JSON
bytes, a hash-chain envelope/genesis rule, entry-book manifest field names,
multi-book snapshot assembly, the final flat evidence-table types/nullability,
decision-to-void status transitions, cross-provider quote-sameness identifiers,
or aggregate ROI denominator rules.  Those are freeze-critical and require a
committed amendment before implementation.

Arithmetic accepts exact decimal strings, integers, :class:`decimal.Decimal`,
or :class:`fractions.Fraction` and converts them to exact rational numbers.
Binary floats are refused rather than silently selecting a decimal context or
rounding law that the preregistration did not specify.  Serialization of those
rational values is intentionally absent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from typing import Any, Mapping, Sequence


BUILD_STATE = "BUILT_UNFROZEN"
OUTCOMES = ("home", "draw", "away")
OUTCOME_SET = frozenset(OUTCOMES)
SELECTION_THRESHOLD = Fraction(1, 50)  # +2.00%
PROBABILITY_TOLERANCE = Fraction(1, 1_000_000_000)
MAX_RECIPROCAL_SUM = Fraction(6, 5)


def _frozen_selection_threshold() -> Fraction:
    """Return the code-fixed threshold; the public display constant is not read."""
    return Fraction(1, 50)

_UTC_Z = re.compile(
    r"(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})T"
    r"(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
    r"(?:\.(?P<fraction>[0-9]+))?Z"
)
_DECIMAL = re.compile(
    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
)


class BetEvalError(ValueError):
    """Base class for a refused pure betting-evidence operation."""


class SchemaError(BetEvalError):
    """A value violates an unambiguous closed contract."""


class ClockError(BetEvalError):
    """A UTC clock violates the preregistered information barrier."""


class IdentityError(BetEvalError):
    """Records cannot be joined without guessing identity."""


class DecisionStatus(str, Enum):
    BET_INTENT = "bet_intent"
    NON_BET = "non_bet"
    FAILURE = "failure"
    VOID = "void"


class FailureReason(str, Enum):
    FIXTURE_UNMAPPED = "fixture_unmapped"
    MODEL_MISSING = "model_missing"
    MODEL_LATE = "model_late"
    MODEL_INVALID = "model_invalid"
    MODEL_ARM_MISMATCH = "model_arm_mismatch"
    SCHEDULE_CHANGED_PRE_ENTRY = "schedule_changed_pre_entry"
    ENTRY_SOURCE_UNREACHABLE = "entry_source_unreachable"
    ENTRY_QUOTE_MISSING = "entry_quote_missing"
    ENTRY_QUOTE_STALE = "entry_quote_stale"
    ENTRY_MARKET_SUSPENDED = "entry_market_suspended"
    ENTRY_MARKET_INCOMPLETE = "entry_market_incomplete"
    ENTRY_MARKET_MALFORMED = "entry_market_malformed"
    ENTRY_PRICE_NOT_PURCHASABLE = "entry_price_not_purchasable"
    BOOK_UNAVAILABLE = "book_unavailable"
    CLOSE_SOURCE_UNREACHABLE = "close_source_unreachable"
    CLOSE_QUOTE_MISSING = "close_quote_missing"
    CLOSE_QUOTE_STALE = "close_quote_stale"
    CLOSE_MARKET_INCOMPLETE = "close_market_incomplete"
    CLOSE_MARKET_MALFORMED = "close_market_malformed"
    ENTRY_BOOK_VOID = "entry_book_void"
    FIXTURE_ABANDONED = "fixture_abandoned"
    FIXTURE_UNRESOLVED_AT_H2 = "fixture_unresolved_at_H2"
    RESULT_MISSING = "result_missing"
    ROW_CONFLICT = "row_conflict"


FAILURE_REASONS = frozenset(reason.value for reason in FailureReason)
PREDECISION_FAILURE_REASONS = frozenset({
    FailureReason.FIXTURE_UNMAPPED.value,
    FailureReason.MODEL_MISSING.value,
    FailureReason.MODEL_LATE.value,
    FailureReason.MODEL_INVALID.value,
    FailureReason.MODEL_ARM_MISMATCH.value,
    FailureReason.SCHEDULE_CHANGED_PRE_ENTRY.value,
    FailureReason.ENTRY_SOURCE_UNREACHABLE.value,
    FailureReason.ENTRY_QUOTE_MISSING.value,
    FailureReason.ENTRY_QUOTE_STALE.value,
    FailureReason.ENTRY_MARKET_SUSPENDED.value,
    FailureReason.ENTRY_MARKET_INCOMPLETE.value,
    FailureReason.ENTRY_MARKET_MALFORMED.value,
    FailureReason.ENTRY_PRICE_NOT_PURCHASABLE.value,
    FailureReason.BOOK_UNAVAILABLE.value,
})


def _exact_keys(value: Mapping[str, Any], expected: Sequence[str],
                label: str) -> None:
    expected_set = frozenset(expected)
    got = frozenset(value)
    if got != expected_set:
        raise SchemaError(
            f"{label} keys differ: missing={sorted(expected_set - got)}, "
            f"extra={sorted(got - expected_set)}"
        )


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"{label} must be a non-empty string")
    return value


def exact_number(value: Any, label: str = "number") -> Fraction:
    """Parse a finite decimal exactly; deliberately refuse binary floats."""
    if isinstance(value, bool) or isinstance(value, float):
        raise SchemaError(
            f"{label} must be an exact decimal string/integer/Decimal/Fraction, "
            "not a binary float"
        )
    if isinstance(value, Fraction):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise SchemaError(f"{label} must be finite")
        return Fraction(value)
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, str):
        if value != value.strip() or _DECIMAL.fullmatch(value) is None:
            raise SchemaError(f"{label} must be a finite decimal string")
        try:
            return Fraction(value)
        except (ValueError, ZeroDivisionError) as exc:
            raise SchemaError(f"{label} is not a finite decimal") from exc
    raise SchemaError(
        f"{label} must be an exact decimal string/integer/Decimal/Fraction"
    )


@dataclass(frozen=True)
class _ProbabilityTriple:
    home: Fraction
    draw: Fraction
    away: Fraction

    def __post_init__(self) -> None:
        values = (self.home, self.draw, self.away)
        if any(not isinstance(value, Fraction) for value in values):
            raise SchemaError("validated probabilities must be exact fractions")
        if any(value < 0 for value in values):
            raise SchemaError("probabilities must be non-negative")
        if abs(sum(values, Fraction(0)) - 1) > PROBABILITY_TOLERANCE:
            raise SchemaError("probabilities must sum to one within 1e-9")

    def __getitem__(self, outcome: str) -> Fraction:
        validate_outcome(outcome)
        return getattr(self, outcome)

    def as_dict(self) -> dict[str, Fraction]:
        return {outcome: getattr(self, outcome) for outcome in OUTCOMES}


@dataclass(frozen=True)
class _OddsTriple:
    home: Fraction
    draw: Fraction
    away: Fraction

    def __post_init__(self) -> None:
        values = (self.home, self.draw, self.away)
        if any(not isinstance(value, Fraction) for value in values):
            raise SchemaError("validated odds must be exact fractions")
        if any(value <= 1 for value in values):
            raise SchemaError("every odds price must be strictly greater than one")
        overround = sum((1 / value for value in values), Fraction(0))
        if overround > MAX_RECIPROCAL_SUM:
            raise SchemaError("odds reciprocal sum exceeds 1.20")
        if overround + PROBABILITY_TOLERANCE < 1:
            raise SchemaError("odds are a malformed underround")

    def __getitem__(self, outcome: str) -> Fraction:
        validate_outcome(outcome)
        return getattr(self, outcome)

    def as_dict(self) -> dict[str, Fraction]:
        return {outcome: getattr(self, outcome) for outcome in OUTCOMES}


def validate_outcome(value: Any, label: str = "outcome") -> str:
    if not isinstance(value, str) or value not in OUTCOME_SET:
        raise SchemaError(f"{label} must be exactly one of {list(OUTCOMES)}")
    return value


def validate_probabilities(value: Mapping[str, Any]) -> _ProbabilityTriple:
    if not isinstance(value, Mapping):
        raise SchemaError("probabilities must be an object")
    _exact_keys(value, OUTCOMES, "probabilities")
    parsed = {
        outcome: exact_number(value[outcome], f"p_{outcome}")
        for outcome in OUTCOMES
    }
    if any(number < 0 for number in parsed.values()):
        raise SchemaError("probabilities must be non-negative")
    total = sum(parsed.values(), Fraction(0))
    if abs(total - 1) > PROBABILITY_TOLERANCE:
        raise SchemaError(
            f"probabilities sum to {total}, outside 1e-9 of one"
        )
    return _ProbabilityTriple(**parsed)


def validate_odds(value: Mapping[str, Any], label: str = "odds") -> _OddsTriple:
    """Validate one complete same-book, same-snapshot 1X2 odds triple."""
    if not isinstance(value, Mapping):
        raise SchemaError(f"{label} must be an object")
    _exact_keys(value, OUTCOMES, label)
    parsed = {
        outcome: exact_number(value[outcome], f"{label}.{outcome}")
        for outcome in OUTCOMES
    }
    if any(number <= 1 for number in parsed.values()):
        raise SchemaError(f"every {label} price must be strictly greater than one")
    overround = sum((1 / parsed[outcome] for outcome in OUTCOMES), Fraction(0))
    if overround > MAX_RECIPROCAL_SUM:
        raise SchemaError(f"{label} reciprocal sum exceeds 1.20")
    if overround + PROBABILITY_TOLERANCE < 1:
        raise SchemaError(f"{label} is a malformed underround")
    return _OddsTriple(**parsed)


def reciprocal_sum(value: Mapping[str, Any]) -> Fraction:
    odds = validate_odds(value)
    return sum((1 / odds[outcome] for outcome in OUTCOMES), Fraction(0))


def utc_instant(value: Any, label: str = "timestamp") -> Fraction:
    """Convert an explicit-Z RFC-3339 clock to exact seconds since epoch.

    Arbitrarily many fractional-second digits are compared exactly, so the
    one-microsecond adversarial boundaries do not depend on ``datetime``
    truncation.
    """
    if not isinstance(value, str):
        raise ClockError(f"{label} must be RFC 3339 UTC with explicit Z")
    match = _UTC_Z.fullmatch(value)
    if match is None:
        raise ClockError(f"{label} must be RFC 3339 UTC with explicit Z")
    fields = {name: int(match.group(name)) for name in (
        "year", "month", "day", "hour", "minute", "second"
    )}
    try:
        whole = datetime(**fields, tzinfo=timezone.utc)
    except ValueError as exc:
        raise ClockError(f"{label} is not a valid UTC timestamp") from exc
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = whole - epoch
    epoch_seconds = delta.days * 86_400 + delta.seconds
    digits = match.group("fraction")
    fractional = Fraction(int(digits), 10 ** len(digits)) if digits else Fraction(0)
    return Fraction(epoch_seconds) + fractional


@dataclass(frozen=True)
class _ValidatedModelSeal:
    model_arm: str
    probabilities: _ProbabilityTriple
    model_issued_at: Fraction
    sealed_at: Fraction


def validate_entry_target(*, kickoff_as_known: str, entry_target: str) -> Fraction:
    """Require the entry target to be exactly 48 hours before known kickoff."""
    kickoff = utc_instant(kickoff_as_known, "kickoff_as_known")
    target = utc_instant(entry_target, "entry_target")
    if target != kickoff - 48 * 60 * 60:
        raise ClockError("entry_target must equal kickoff_as_known minus 48 hours")
    return target


def validate_model_seal(
    *, model_arm: str, expected_arm: str, probabilities: Mapping[str, Any],
    cutoff: str, observed_by: str, model_issued_at: str,
    kickoff_as_known: str, entry_target: str, sealed_at: str,
) -> _ValidatedModelSeal:
    """Validate the model arm/probabilities and model-before-entry clocks.

    Hash-envelope validation is intentionally excluded until its canonical
    bytes and chain format are amended into the preregistration.
    """
    _nonempty_string(model_arm, "model_arm")
    _nonempty_string(expected_arm, "expected_arm")
    if model_arm != expected_arm:
        raise SchemaError(
            f"model_arm_mismatch: expected {expected_arm!r}, got {model_arm!r}"
        )
    probs = validate_probabilities(probabilities)
    issued = utc_instant(model_issued_at, "model_issued_at")
    cutoff_at = utc_instant(cutoff, "cutoff")
    observed_at = utc_instant(observed_by, "observed_by")
    target = validate_entry_target(
        kickoff_as_known=kickoff_as_known, entry_target=entry_target,
    )
    sealed = utc_instant(sealed_at, "sealed_at")
    seal_deadline = target - 30 * 60
    if issued > seal_deadline:
        raise ClockError("model_late: model_issued_at exceeds target minus 30m")
    if cutoff_at > issued:
        raise ClockError("cutoff must be no later than model_issued_at")
    if observed_at > issued:
        raise ClockError("observed_by must be no later than model_issued_at")
    if sealed < issued:
        raise ClockError("durable model seal cannot precede model_issued_at")
    if sealed > seal_deadline:
        raise ClockError("model seal must be durable no later than target minus 30m")
    return _ValidatedModelSeal(model_arm, probs, issued, sealed)


def validate_quote_clocks(
    *, kickoff_as_known: str, entry_target: str, model_sealed_at: str,
    first_entry_request_at: str,
    entry_provider_at: str, entry_observed_at: str, actual_kickoff: str,
    close_provider_at: str, close_observed_at: str,
) -> dict[str, Fraction]:
    """Enforce the inclusive entry/close windows and strict clock ordering."""
    clocks = {
        name: utc_instant(value, name)
        for name, value in {
            "entry_target": entry_target,
            "model_sealed_at": model_sealed_at,
            "first_entry_request_at": first_entry_request_at,
            "entry_provider_at": entry_provider_at,
            "entry_observed_at": entry_observed_at,
            "actual_kickoff": actual_kickoff,
            "close_provider_at": close_provider_at,
            "close_observed_at": close_observed_at,
        }.items()
    }
    validate_entry_target(
        kickoff_as_known=kickoff_as_known, entry_target=entry_target,
    )
    if clocks["model_sealed_at"] > clocks["entry_target"] - 30 * 60:
        raise ClockError("model seal must be durable no later than target minus 30m")
    if clocks["model_sealed_at"] >= clocks["first_entry_request_at"]:
        raise ClockError("model seal must precede first entry-source request")
    if clocks["entry_observed_at"] < clocks["first_entry_request_at"]:
        raise ClockError("entry observation cannot precede its first request")
    entry_end = clocks["entry_target"] + 10 * 60
    for name in ("entry_provider_at", "entry_observed_at"):
        if not clocks["entry_target"] <= clocks[name] <= entry_end:
            raise ClockError(f"entry_quote_stale: {name} is outside entry window")
    close_start = clocks["actual_kickoff"] - 10 * 60
    close_end = clocks["actual_kickoff"] - 60
    if not close_start <= clocks["close_provider_at"] <= close_end:
        raise ClockError("close_quote_stale: close_provider_at is outside close window")
    if clocks["close_observed_at"] < clocks["close_provider_at"]:
        raise ClockError("close observation cannot precede provider publication")
    effective_entry = max(clocks["entry_provider_at"], clocks["entry_observed_at"])
    if effective_entry >= clocks["close_provider_at"]:
        raise ClockError("entry must strictly precede close provider time")
    clocks["effective_entry_at"] = effective_entry
    return clocks


def net_entry_odds(raw_odds: Any, *, venue_type: str,
                   commission_rate: Any) -> Fraction:
    raw = exact_number(raw_odds, "raw_odds")
    commission = exact_number(commission_rate, "commission_rate")
    if raw <= 1:
        raise SchemaError("raw_odds must be strictly greater than one")
    if commission < 0 or commission >= 1:
        raise SchemaError("commission_rate must satisfy 0 <= c < 1")
    if venue_type == "bookmaker":
        if commission != 0:
            raise SchemaError("bookmaker commission must be zero")
        return raw
    if venue_type == "exchange":
        return 1 + (raw - 1) * (1 - commission)
    raise SchemaError("venue_type must be exactly 'bookmaker' or 'exchange'")


@dataclass(frozen=True)
class EligibleEntryOffer:
    """An already-assembled, already-eligible complete manifest-book quote.

    Quote collection/assembly and owner-manifest validation are intentionally
    upstream and not yet implemented.  ``book_order`` is the already-frozen
    manifest position used only for the unambiguous tie-break.
    """

    book: str
    book_order: int
    odds_raw: Mapping[str, Any]
    venue_type: str
    commission_rate: Any


@dataclass(frozen=True)
class DecisionRow:
    fixture_id: str
    decision_status: str
    reason: str | None
    selected_outcome: str | None
    entry_book: str | None
    entry_odds_raw: Fraction | None
    entry_odds_net: Fraction | None
    model_edge: Fraction | None
    selection_threshold: Fraction
    stake_units: Fraction

    def __post_init__(self) -> None:
        _nonempty_string(self.fixture_id, "fixture_id")
        if self.selection_threshold != _frozen_selection_threshold():
            raise SchemaError("decision threshold must be the frozen +2.00%")
        if not isinstance(self.stake_units, Fraction):
            raise SchemaError("stake_units must be an exact Fraction")
        if self.decision_status == DecisionStatus.BET_INTENT.value:
            validate_outcome(self.selected_outcome, "selected_outcome")
            _nonempty_string(self.entry_book, "entry_book")
            if self.reason is not None or self.stake_units != 1:
                raise SchemaError("bet_intent must have null reason and one unit")
            values = (self.entry_odds_raw, self.entry_odds_net, self.model_edge)
            if any(not isinstance(value, Fraction) for value in values):
                raise SchemaError("bet_intent odds and edge must be exact Fractions")
            if self.entry_odds_raw <= 1 or self.entry_odds_net <= 1:
                raise SchemaError("bet_intent odds must be greater than one")
            if self.model_edge < _frozen_selection_threshold():
                raise SchemaError("bet_intent edge must meet the frozen threshold")
            return
        if self.decision_status == DecisionStatus.NON_BET.value:
            if self.reason != "no_edge" or self.stake_units != 0:
                raise SchemaError("non_bet must have reason no_edge and zero stake")
            if any(value is not None for value in (
                self.selected_outcome, self.entry_book, self.entry_odds_raw,
                self.entry_odds_net,
            )):
                raise SchemaError("non_bet cannot carry a selected offer")
            if not isinstance(self.model_edge, Fraction):
                raise SchemaError("non_bet must retain an exact maximum edge")
            if self.model_edge >= _frozen_selection_threshold():
                raise SchemaError("non_bet maximum edge must be below +2.00%")
            return
        if self.decision_status == DecisionStatus.FAILURE.value:
            if self.reason not in PREDECISION_FAILURE_REASONS:
                raise SchemaError("failure reason is not a predecision reason")
            if self.stake_units != 0 or any(value is not None for value in (
                self.selected_outcome, self.entry_book, self.entry_odds_raw,
                self.entry_odds_net, self.model_edge,
            )):
                raise SchemaError("predecision failure must carry no selection or stake")
            return
        raise SchemaError("DecisionRow represents only bet_intent/non_bet/predecision failure")


def predecision_failure_row(
    fixture_id: str, reason: FailureReason | str,
) -> DecisionRow:
    _nonempty_string(fixture_id, "fixture_id")
    reason_value = reason.value if isinstance(reason, FailureReason) else reason
    if reason_value not in PREDECISION_FAILURE_REASONS:
        raise SchemaError(f"reason {reason_value!r} is not a predecision reason")
    return DecisionRow(
        fixture_id, DecisionStatus.FAILURE.value, reason_value, None, None,
        None, None, None, _frozen_selection_threshold(), Fraction(0),
    )


def select_from_eligible_offers(
    fixture_id: str, probabilities: Mapping[str, Any] | None,
    offers: Sequence[EligibleEntryOffer],
) -> DecisionRow:
    """Apply the exact max-EV rule after upstream quote eligibility is fixed.

    Close and result data are intentionally absent from the signature.
    Snapshot assembly, missing-book handling, and failure mapping are deferred
    because the preregistration does not yet specify them.
    """
    _nonempty_string(fixture_id, "fixture_id")
    if probabilities is None:
        return predecision_failure_row(fixture_id, FailureReason.MODEL_MISSING)
    try:
        probs = validate_probabilities(probabilities)
    except SchemaError:
        return predecision_failure_row(fixture_id, FailureReason.MODEL_INVALID)
    if not offers:
        raise SchemaError(
            "empty eligible offers cannot be classified until quote assembly is amended"
        )

    seen_books: set[str] = set()
    seen_orders: set[int] = set()
    prepared: list[tuple[EligibleEntryOffer, _OddsTriple]] = []
    for offer in offers:
        book = _nonempty_string(offer.book, "book")
        if isinstance(offer.book_order, bool) or not isinstance(offer.book_order, int):
            raise SchemaError("book_order must be a non-negative integer")
        if offer.book_order < 0:
            raise SchemaError("book_order must be a non-negative integer")
        if book in seen_books or offer.book_order in seen_orders:
            raise SchemaError("eligible offers contain a duplicate book/order")
        seen_books.add(book)
        seen_orders.add(offer.book_order)
        prepared.append((offer, validate_odds(offer.odds_raw, f"{book} odds")))
    prepared.sort(key=lambda item: item[0].book_order)

    best: tuple[Fraction, int, int, EligibleEntryOffer, _OddsTriple] | None = None
    for outcome_index, outcome in enumerate(OUTCOMES):
        for offer, odds in prepared:
            net = net_entry_odds(
                odds[outcome], venue_type=offer.venue_type,
                commission_rate=offer.commission_rate,
            )
            edge = probs[outcome] * net - 1
            candidate = (edge, outcome_index, offer.book_order, offer, odds)
            if best is None or edge > best[0]:
                best = candidate
    assert best is not None
    edge, outcome_index, _, offer, odds = best
    outcome = OUTCOMES[outcome_index]
    if edge < _frozen_selection_threshold():
        return DecisionRow(
            fixture_id, DecisionStatus.NON_BET.value, "no_edge", None, None,
            None, None, edge, _frozen_selection_threshold(), Fraction(0),
        )
    raw = odds[outcome]
    net = net_entry_odds(
        raw, venue_type=offer.venue_type,
        commission_rate=offer.commission_rate,
    )
    return DecisionRow(
        fixture_id, DecisionStatus.BET_INTENT.value, None, outcome, offer.book,
        raw, net, edge, _frozen_selection_threshold(), Fraction(1),
    )


@dataclass(frozen=True)
class FixtureIdentity:
    fixture_id: str
    competition: str
    market: str
    home: str
    away: str

    def __post_init__(self) -> None:
        for field in ("fixture_id", "competition", "market", "home", "away"):
            _nonempty_string(getattr(self, field), field)
        if self.home == self.away:
            raise IdentityError("home and away canonical identities must differ")


def validate_entry_close_identity(
    entry: FixtureIdentity, close: FixtureIdentity,
) -> None:
    """Refuse cross-event joins; quote sameness remains amendment-dependent."""
    if entry != close:
        raise IdentityError("entry and close do not have exact same-event identity")


def proportional_close_devig(
    close_odds: Mapping[str, Any],
) -> dict[str, Fraction]:
    odds = validate_odds(close_odds, "close odds")
    reciprocals = {outcome: 1 / odds[outcome] for outcome in OUTCOMES}
    total = sum(reciprocals.values(), Fraction(0))
    return {
        outcome: reciprocals[outcome] / total for outcome in OUTCOMES
    }


def economic_clv(
    entry_net_odds: Any,
    pinnacle_close_odds: Mapping[str, Any],
    selected_outcome: str,
) -> Fraction:
    """Compute primary CLV only from a raw, valid Pinnacle close triple.

    The caller cannot supply a normalized probability vector: proportional
    de-vigging is performed here so an alternative close law cannot impersonate
    the preregistered primary statistic.  Pinnacle source identity/provenance is
    still an event-assembly concern and remains unavailable while unfrozen.
    """
    outcome = validate_outcome(selected_outcome, "selected_outcome")
    net = exact_number(entry_net_odds, "entry_net_odds")
    if net <= 1:
        raise SchemaError("entry_net_odds must be strictly greater than one")
    probabilities = validate_probabilities(
        proportional_close_devig(pinnacle_close_odds)
    )
    return probabilities[outcome] * net - 1


def flat_pnl(
    entry_net_odds: Any, selected_outcome: str,
    result_outcome: str | None, *, void: bool = False,
) -> Fraction:
    selected = validate_outcome(selected_outcome, "selected_outcome")
    net = exact_number(entry_net_odds, "entry_net_odds")
    if net <= 1:
        raise SchemaError("entry_net_odds must be strictly greater than one")
    if void:
        if result_outcome is not None:
            validate_outcome(result_outcome, "result_outcome")
        return Fraction(0)
    result = validate_outcome(result_outcome, "result_outcome")
    return net - 1 if selected == result else Fraction(-1)


@dataclass(frozen=True)
class UnfrozenEvidenceRow:
    """Noncanonical audit projection used only to prove census retention."""

    fixture_id: str
    census: Mapping[str, Any]
    stages: Mapping[str, Mapping[str, Any] | None]


def derive_unfrozen_evidence_rows(
    census_rows: Sequence[Mapping[str, Any]],
    stage_rows: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[UnfrozenEvidenceRow, ...]:
    """Left-derive one audit row per census fixture without defining schema.

    Every stage row must use an exact ``fixture_id``.  Duplicate, extra, and
    cross-event rows refuse.  Missing stage records remain explicit ``None``;
    failure records are retained byte-for-value in the audit projection.
    """
    census_by_id: dict[str, Mapping[str, Any]] = {}
    order: list[str] = []
    for census in census_rows:
        if not isinstance(census, Mapping):
            raise SchemaError("census row must be an object")
        fixture_id = _nonempty_string(census.get("fixture_id"), "fixture_id")
        if fixture_id in census_by_id:
            raise SchemaError(f"duplicate census fixture {fixture_id!r}")
        census_by_id[fixture_id] = dict(census)
        order.append(fixture_id)

    indexed_stages: dict[str, dict[str, Mapping[str, Any]]] = {}
    for stage, rows in stage_rows.items():
        _nonempty_string(stage, "stage")
        by_id: dict[str, Mapping[str, Any]] = {}
        for row in rows:
            if not isinstance(row, Mapping):
                raise SchemaError(f"{stage} row must be an object")
            fixture_id = _nonempty_string(row.get("fixture_id"), "fixture_id")
            if fixture_id not in census_by_id:
                raise IdentityError(
                    f"{stage} row references non-census fixture {fixture_id!r}"
                )
            if fixture_id in by_id:
                raise SchemaError(f"duplicate {stage} row for fixture {fixture_id!r}")
            by_id[fixture_id] = dict(row)
        indexed_stages[stage] = by_id

    return tuple(
        UnfrozenEvidenceRow(
            fixture_id=fixture_id,
            census=census_by_id[fixture_id],
            stages={
                stage: indexed_stages[stage].get(fixture_id)
                for stage in stage_rows
            },
        )
        for fixture_id in order
    )


__all__ = [
    "BUILD_STATE", "BetEvalError", "ClockError",
    "DecisionRow", "DecisionStatus", "EligibleEntryOffer", "FailureReason",
    "FixtureIdentity", "IdentityError", "MAX_RECIPROCAL_SUM",
    "PROBABILITY_TOLERANCE", "SELECTION_THRESHOLD", "SchemaError",
    "UnfrozenEvidenceRow",
    "derive_unfrozen_evidence_rows", "economic_clv", "exact_number",
    "flat_pnl", "net_entry_odds", "predecision_failure_row",
    "proportional_close_devig", "reciprocal_sum", "select_from_eligible_offers",
    "utc_instant", "validate_entry_close_identity", "validate_entry_target",
    "validate_model_seal",
    "validate_odds", "validate_outcome", "validate_probabilities",
    "validate_quote_clocks",
]
