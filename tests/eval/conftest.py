"""Shared eval-suite guards.

The probe tests drive mocked ``--live`` runs end-to-end, and the ONLY thing
between their fabricated payloads and the real paid-evidence store
(``data/odds_raw``) is the probe's transport allowlist. Isolation here is
defense-in-depth for the whole suite: every test sees an ``ODDS_RAW_DIR``
under its own ``tmp_path``, so a future regression in that allowlist (or any
other archive path) writes into a per-test sandbox — where the probe e2e's
strict tmp_path file-set assertions turn the leak into a loud failure —
never into the repo store.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_odds_raw_dir(tmp_path, monkeypatch):
    isolated = tmp_path / "odds_raw_isolated"
    # Patch the SOURCE module: scripts/oa_probe.py re-binds the name at each
    # test's fresh module load, so it inherits the patched value too.
    monkeypatch.setattr("wcmodel.data.sources.odds.ODDS_RAW_DIR", isolated)
    return isolated
