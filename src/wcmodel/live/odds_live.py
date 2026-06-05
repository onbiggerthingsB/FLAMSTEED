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

#: The NEW live route (no ``date`` => the CURRENT snapshot for every event). This is
#: DISTINCT from the gated historical route ``fetch_historical`` uses.
LIVE_ODDS_ROUTE = "/v4/sports/{sport}/odds"

#: Dry-run marker stamped on a fixture/synthetic-derived live mapping so a dry-run
#: snapshot can never be mistaken for a real pull downstream.
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
                    budget: CallBudget | None = None,
                    base_backoff: float = 2.0, max_retries: int = 4) -> list[dict]:
    """Pull the CURRENT live odds snapshot from the regular route (network, PAID).

    GATED: raises ``RuntimeError`` without an ``api_key`` (the feed is funded
    separately, L1) — never exercised with a real key by tests. When a key IS
    supplied it charges the call budget, hits ``GET /v4/sports/{sport}/odds`` with
    backoff, and returns the raw event list (wrap it with ``wrap_live_response``).
    """
    if api_key is None:
        raise RuntimeError(
            "live odds pull gated: no api_key — the paid feed is funded separately "
            "(L1 spend gate; run in dry_run until funded)"
        )
    if budget is not None:
        budget.charge()
    url = f"{ODDSAPI_BASE}{LIVE_ODDS_ROUTE.format(sport=sport)}"

    def _call() -> list[dict]:
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
    ``which`` selects the snapshot to treat as the CURRENT live one (``"bet_time"``
    for the decision-time price, ``"close"`` for a near-kickoff refresh). The chosen
    snapshot is re-exposed under a single ``"live"`` key + a ``_dry_run`` flag, so
    ``entry_close_prices`` reads exactly one snapshot and the result can never be
    mistaken for a real pull. The ``budget`` is NOT charged (no real call happened).
    """
    snap = sample[which]
    out = {"live": snap, _DRY_RUN_KEY: True}
    # Preserve the synthetic marker if present so the non-real taint propagates
    # (load_odds_snapshots refuses to persist it as real).
    from wcmodel.backtest.odds_ingest import _SYNTHETIC_KEY
    if sample.get(_SYNTHETIC_KEY) or (isinstance(snap, dict) and snap.get(_SYNTHETIC_KEY)):
        out[_SYNTHETIC_KEY] = True
    return out
