"""Live odds fetch (Phase-5 §2.1) — the NEW regular ``GET /v4/sports/{sport}/odds``
route + a dry-run harness + a pinned call-budget guard.

Only the fetch ROUTE is new. The current snapshot it returns is wrapped into the
SAME ``{timestamp, data:[...]}`` snapshot shape the existing pure
``wcmodel.data.sources.odds.parse_snapshot`` / ``backtest.odds_ingest.entry_close_prices``
path already consumes, so the parse/store path is reused UNCHANGED.

GATING (L1, binding). The live pull is PAID and the feed is funded SEPARATELY, so
``fetch_live_odds`` RAISES without an ``api_key`` (exactly like
``odds.fetch_historical``) and is never exercised with a real key by any test. In
DRY-RUN (``config.live.dry_run=true``, the default) the pipeline never calls it at
all — it reads the fixture / the clearly-labelled-non-real synthetic harness via
``live_snapshot_from_fixture`` and ``wrap_live_response``, so NO real odds spend and
NO real number is ever produced here.

FEED-AGNOSTIC (L1 rider b). The bookmaker / sharp benchmark is a config value
(``live.bookmaker`` / ``live.sharp_benchmark``), never hard-coded — the Pinnacle-via-
aggregator vs Betfair-Exchange pick is deferred to funding-time.

COST DISCIPLINE (L1 rider c). ``CallBudget`` pins cadence x event-count <= the plan
quota and REFUSES once the budget is spent; ``with_backoff`` retries a 429/5xx with
exponential backoff up to ``max_retries``. Never a scraper-at-volume.
"""
from __future__ import annotations

import time

import httpx

from wcmodel.data.sources.odds import ODDSAPI_BASE

#: The NEW live route (no ``date`` => the CURRENT snapshot for every event), DISTINCT
#: from the gated historical route ``fetch_historical`` uses. The leading ``/v4`` is
#: NOT repeated here: ``ODDSAPI_BASE`` already ends in ``/v4`` and we append this to
#: it (exactly as ``fetch_historical`` appends ``/historical/sports/...``), so the
#: joined URL is ``.../v4/sports/{sport}/odds`` — a doubled ``/v4`` would 404 when funded.
LIVE_ODDS_ROUTE = "/sports/{sport}/odds"

#: Dry-run marker stamped on a fixture/synthetic-derived live mapping. INFORMATIONAL
#: only: the *non-real guarantee* rides on ``_is_synthetic`` (``_SYNTHETIC_KEY``, the
#: store-boundary refusal key), which the dry-run output ALSO carries — see
#: ``live_snapshot_from_fixture`` — so a dry-run number can never be mistaken for or
#: persisted as real even if ``_dry_run`` were dropped.
_DRY_RUN_KEY = "_dry_run"


class BudgetExhaustedError(RuntimeError):
    """Raised when a live fetch would exceed the pinned per-day call budget."""


class CallBudget:
    """A pinned per-day call budget (L1 rider c): cadence x events <= plan quota.

    ``charge()`` increments the spent count and REFUSES (raises) once the ceiling is
    reached, so a runaway cadence can never scrape-at-volume. Dry-run reads never
    call ``charge`` (no real call happened), so they are free.
    """

    def __init__(self, *, max_calls_per_day: int):
        self.max_calls_per_day = int(max_calls_per_day)
        self.spent = 0

    def charge(self) -> None:
        if self.spent >= self.max_calls_per_day:
            raise BudgetExhaustedError(
                f"live call budget exhausted ({self.spent}/{self.max_calls_per_day} "
                "calls today) — refusing to over-call the paid feed (L1 cost discipline)"
            )
        self.spent += 1


def with_backoff(fn, *, max_retries: int, base_backoff: float):
    """Call ``fn()`` retrying a 429/5xx with exponential backoff up to ``max_retries``.

    A transient rate-limit/5xx is retried (``base_backoff * 2**attempt`` seconds); a
    4xx other than 429 is not retried (a real client error). Re-raises the last error
    once retries are exhausted.
    """
    attempt = 0
    while True:
        try:
            return fn()
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            retryable = code == 429 or 500 <= code < 600
            if not retryable or attempt >= max_retries:
                raise
            time.sleep(base_backoff * (2 ** attempt))
            attempt += 1


def wrap_live_response(raw_events: list[dict], *, observed_ts: str) -> dict:
    """Wrap the regular route's event LIST into a ``{timestamp, data}`` snapshot.

    The ``GET /v4/sports/{sport}/odds`` route returns a bare ``list[event]`` (the
    current odds), NOT the ``{bet_time, close}`` mapping the historical fixture uses.
    We wrap it with the observation timestamp so ``parse_snapshot`` (which expects a
    single snapshot dict with ``timestamp`` + ``data``) consumes it unchanged.
    """
    return {"timestamp": observed_ts, "data": list(raw_events)}


def fetch_live_odds(*, api_key: str | None, sport: str, regions: str, market: str,
                    dry_run: bool = True,
                    budget: CallBudget | None = None,
                    base_backoff: float = 2.0, max_retries: int = 4) -> list[dict]:
    """Pull the CURRENT live odds snapshot from the regular route (network, PAID).

    DOUBLE-GATED (L1 spend gate, defense-in-depth): the ONLY path to ``httpx.get`` is
    ``dry_run=false AND api_key present``. It raises ``RuntimeError`` if EITHER
    ``dry_run`` is true (the whole-phase spend gate — a key alone must NOT spend; in
    dry-run the pipeline reads the fixture / synthetic harness, never this) OR the
    ``api_key`` is missing (the feed is funded separately). ``dry_run`` defaults to
    true so this can never spend unless explicitly funded; the gate is enforced HERE,
    not only at the caller's dispatch. When BOTH gates clear it appends the route to
    ``ODDSAPI_BASE`` (``.../v4/sports/{sport}/odds``), retries 429/5xx with backoff,
    and returns the raw event list (wrap it with ``wrap_live_response``).

    COST DISCIPLINE (L1 rider c): ``budget`` is charged PER actual http attempt
    (inside the retried call), so N retries count N+1 against ``max_calls_per_day`` —
    the budget caps PAID api calls, not decisions — and exhausting it mid-retry
    refuses further attempts.
    """
    if dry_run:
        raise RuntimeError(
            "live odds pull refused: dry_run is true — the whole-phase spend gate is "
            "dry_run, so the fetch must not touch the network (read the fixture / "
            "synthetic harness instead). Flip live.dry_run=false ONLY when funded (L1)."
        )
    if api_key is None:
        raise RuntimeError(
            "live odds pull gated: no api_key — the paid feed is funded separately "
            "(L1 spend gate; run in dry_run until funded)"
        )
    url = f"{ODDSAPI_BASE}{LIVE_ODDS_ROUTE.format(sport=sport)}"

    def _call() -> list[dict]:
        # Charge PER http attempt (a retry is another PAID call): the budget caps
        # paid api calls, not decisions, so a runaway retry can never bypass it.
        if budget is not None:
            budget.charge()
        resp = httpx.get(
            url,
            params={"apiKey": api_key, "regions": regions, "markets": market,
                    "oddsFormat": "decimal"},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    return with_backoff(_call, max_retries=max_retries, base_backoff=base_backoff)


def live_snapshot_from_fixture(sample: dict, *, which: str = "bet_time",
                               budget: CallBudget | None = None) -> dict:
    """DRY-RUN: build a live snapshot mapping from a fixture/synthetic sample — NO network.

    ``sample`` is the ``{bet_time, close}`` fixture mapping (or a synthetic one);
    ``which`` selects WHAT the dry-run pull exposes:

      * ``"bet_time"`` (default) — the decision-time price as the CURRENT live one;
      * ``"close"``              — a near-kickoff refresh as the current live one;
        Both single-snapshot modes re-expose the chosen snapshot under a single
        ``"live"`` key + a ``_dry_run`` flag, so ``entry_close_prices`` reads exactly
        one snapshot (a single ``GET /odds`` is one point-in-time).
      * ``"all"``                — the ACCUMULATED live snapshot history a ``read(now)``
        would hold by kickoff: BOTH the early decision-time line (under ``bet_time``)
        AND the kickoff close (under ``close``). This is the mapping the live DECISION
        consumes (``decide_live``/``scan``): the bet_time line drives the edge/stake at
        ``cutoff`` and the close is recorded for realized CLV. Every nested snapshot is
        tainted, so a dry-run multi-snapshot pull is non-real exactly like the
        single-snapshot ones. (No ``"live"`` alias here: every consumer iterates the
        snapshot VALUES, so aliasing one snapshot under a second key would only
        duplicate it in the candidate lists.)

    The ``budget`` is NOT charged (no real call happened).

    NON-REAL TAINT (betting-safety, binding): a dry-run number is NOT a real pull, so
    the output is stamped ``_is_synthetic = True`` (``_SYNTHETIC_KEY``) on the wrapper
    AND EVERY nested snapshot — UNCONDITIONALLY, even off the REAL fixture, since the
    *value* (fixture price replayed as "current") is not a live quote. Therefore
    ``entry_close_prices(...).is_synthetic`` is True and ``load_odds_snapshots``
    REFUSES to persist it as real (the store boundary). The non-real guarantee rides
    on ``_is_synthetic``, not on ``_dry_run``.
    """
    from wcmodel.backtest.odds_ingest import _SYNTHETIC_KEY

    def _taint(snap):
        """Shallow-copy a snapshot before stamping the marker so we NEVER mutate the
        caller's input sample (e.g. a shared/session fixture), and stamp non-real."""
        snap = dict(snap) if isinstance(snap, dict) else snap
        if isinstance(snap, dict):
            snap[_SYNTHETIC_KEY] = True
        return snap

    if which == "all":
        # The ACCUMULATED dry-run pull: expose BOTH snapshots so the live decision
        # prices a genuine entry (bet_time, <= cutoff) distinct from the close
        # (recorded for CLV only). `decide_live`/`scan` iterate the mapping's snapshot
        # values (no key is special), so the keys are descriptive. Every nested
        # snapshot is tainted non-real (a dry-run multi-pull is not real odds).
        return {"bet_time": _taint(sample["bet_time"]),
                "close": _taint(sample["close"]),
                _DRY_RUN_KEY: True, _SYNTHETIC_KEY: True}

    # The dry-run output is non-real BY CONSTRUCTION: stamp the synthetic marker on
    # the wrapper AND the nested snap so the store-write refuses it and
    # entry_close_prices reports is_synthetic (a dry-run number can never be mistaken
    # for, or persisted as, real). _dry_run is kept as an informational flag.
    snap = _taint(sample[which])
    return {"live": snap, _DRY_RUN_KEY: True, _SYNTHETIC_KEY: True}
