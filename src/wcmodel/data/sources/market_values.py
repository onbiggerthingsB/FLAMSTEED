"""Squad market-value source — INTERFACE ONLY (optional / gated).

Squad market values (e.g. Transfermarkt) are an *optional* feature, explicitly
the **first optional feature to revisit** (spec §10.2). They are deferred for
two reasons:

  1. **Licensing is UNVERIFIED** — Transfermarkt's terms do not clearly permit
     programmatic collection, so no scraper is implemented here.
  2. **Revision hazard** — market values are restated over time. Scraping the
     *current* value and stamping it with an old ``valid_as_of`` would leak that
     revision past the bitemporal read invariant (north-star §4.2). A correct
     implementation needs point-in-time snapshots, not present-day state.

This module therefore defines only the *contract* — a :class:`MarketValueSource`
typing protocol — plus a concrete :class:`TransfermarktMarketValues` whose
``pull`` raises :class:`NotImplementedError`. No network and no scraping happen.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # import only for type-checking; no runtime/network dependency
    import pandas as pd


@runtime_checkable
class MarketValueSource(Protocol):
    """Contract for a squad market-value provider.

    Implementations return a :class:`pandas.DataFrame` of point-in-time market
    values (so they can be loaded into the bitemporal store without leaking
    later revisions). Intentionally minimal — this is a forward-looking
    interface for an optional feature, not yet a working source.
    """

    def pull(self) -> "pd.DataFrame":
        """Return point-in-time squad market values as a DataFrame."""
        ...


class TransfermarktMarketValues:
    """Transfermarkt market-value source — NOT IMPLEMENTED (optional / gated).

    Conforms to :class:`MarketValueSource` in shape, but ``pull`` raises: the
    license is UNVERIFIED and no scraping is implemented. Revisit per spec
    §10.2 with proper point-in-time snapshots if/when this feature is enabled.
    """

    def pull(self) -> "pd.DataFrame":  # pragma: no cover - intentional stub
        raise NotImplementedError(
            "Optional/gated — first optional feature to revisit (spec §10.2); "
            "license UNVERIFIED; no scraping implemented"
        )
