"""Shared eval-suite guards.

The probe tests drive mocked ``--live`` runs end-to-end, and the ONLY thing
between their fabricated payloads and the real paid-evidence store
(``data/odds_raw``) is the probe's transport allowlist. Isolation here is
defense-in-depth for the whole suite: every test sees an ``ODDS_RAW_DIR``
under its own ``tmp_path``, so a future regression in that allowlist (or any
other archive path) writes into a per-test sandbox — where the probe e2e's
strict tmp_path file-set assertions turn the leak into a loud failure —
never into the repo store.

Same defense-in-depth for the WIRE and the KEY (``no_live_network``): one
future mocked ``--live`` test that forgets its single
``monkeypatch.setattr(mod, "_live_transport", ...)`` line would otherwise
place up to 45 real paid calls against the developer's env ``ODDS_API_KEY``.
"""
from __future__ import annotations

import httpx
import pytest


@pytest.fixture(autouse=True)
def isolated_odds_raw_dir(tmp_path, monkeypatch):
    isolated = tmp_path / "odds_raw_isolated"
    # Patch the SOURCE module: scripts/oa_probe.py re-binds the name at each
    # test's fresh module load, so it inherits the patched value too.
    monkeypatch.setattr("wcmodel.data.sources.odds.ODDS_RAW_DIR", isolated)
    return isolated


class LiveNetworkRefused(BaseException):
    """Sentinel for a live-network attempt that escaped the test mocks.

    Deliberately BaseException-derived, NOT Exception: the probe's
    per-fixture handlers catch ``Exception`` by design (a 401/429/timeout is
    a coverage finding, not a crash), so the suite's established
    ``AssertionError("no network")`` idiom (tests/data/test_odds.py) is
    SWALLOWED by it — the run exits 0 and writes a LIVE-bannered report
    whose 15 rows carry the sentinel as per-fixture notes, after attempting
    every call. Only a BaseException can cut through those handlers and kill
    the run before the first request is placed."""


@pytest.fixture(autouse=True)
def no_live_network(monkeypatch):
    """Suite-wide spend/leak backstop: no eval test may reach the real Odds
    API even when a mocked ``--live`` test forgets to monkeypatch the probe's
    transport factory. The env key is cleared (tests that need one set their
    own fake), and the genuine network transport's entrypoint is replaced
    with the sentinel. Returns the sentinel type so the non-vacuity test can
    assert on it."""
    monkeypatch.delenv("ODDS_API_KEY", raising=False)

    def _refuse(self, request):
        # host + path only: the query string carries the apiKey and must
        # never enter pytest output.
        raise LiveNetworkRefused(
            f"refusing live network call to "
            f"{request.url.host}{request.url.path} — eval tests must inject "
            "a mock transport")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _refuse)
    return LiveNetworkRefused
