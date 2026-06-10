"""P3 v0 — the cached squad-anchor LOADER (tag -> (squad_z, has_squad) per team).

``load_squad_anchor(tag)`` reads ONLY the committed ``config/squads/`` CSVs (the
squad list + the point-in-time clubelo snapshot + the alias map for that
tournament tag), composes the TDD'd pure ``squad_z`` primitives, and returns the
per-team ``squad_z`` + ``has_squad`` dicts the model wiring threads into the
att/def prior. It is the squad mirror of ``team_elo_z``: pure (offline, no store,
no network), and CACHED (keyed by tag) so repeated fits at the same cutoff reuse
the parse.

Three tags map to the three pre-registered snapshots (the LEAKAGE contract): each
snapshot endpoint D is strictly pre-cutoff for its tournament (pinned by the
snapshot-content tests in ``test_squad_z.py``).

  wc2022   -> clubelo_20221120.csv  (WC-2022 cutoff 2022-11-20)
  euro2024 -> clubelo_20240614.csv  (Euro-2024 cutoff 2024-06-14)
  wc2026   -> clubelo_20260610.csv  (the 2026 live path)
"""
from __future__ import annotations

import pytest

from wcmodel.data.sources.squad_anchor import (
    SNAPSHOT_FOR_TAG,
    load_squad_anchor,
)


def test_known_tags_map_to_prereg_snapshots():
    assert SNAPSHOT_FOR_TAG["wc2022"] == "clubelo_20221120.csv"
    assert SNAPSHOT_FOR_TAG["euro2024"] == "clubelo_20240614.csv"
    assert SNAPSHOT_FOR_TAG["wc2026"] == "clubelo_20260610.csv"


def test_unknown_tag_raises():
    with pytest.raises(KeyError):
        load_squad_anchor("euro2020")


@pytest.mark.parametrize("tag", ["wc2022", "euro2024", "wc2026"])
def test_returns_aligned_squad_z_and_has_squad(tag):
    sz, hs = load_squad_anchor(tag)
    # same team keys in both dicts.
    assert set(sz) == set(hs)
    assert len(sz) > 0
    # has_squad is a 0/1 mask; squad_z finite everywhere (no NaN leak).
    for t in sz:
        assert hs[t] in (0, 1)
        assert sz[t] == sz[t]                   # not NaN


@pytest.mark.parametrize("tag", ["wc2022", "euro2024", "wc2026"])
def test_uncovered_team_has_zero_squad_z(tag):
    """A masked team (has_squad=0) carries squad_z == 0.0 (belt-and-suspenders:
    the model also multiplies by has_squad, but the loader zeros it too)."""
    sz, hs = load_squad_anchor(tag)
    for t in sz:
        if hs[t] == 0:
            assert sz[t] == 0.0


def test_covered_set_is_zero_mean_unit_std():
    """squad_z is z-scored OVER the covered teams of that tournament (spec §4.4):
    the covered subset has mean ~0 and population std ~1."""
    import numpy as np
    sz, hs = load_squad_anchor("wc2022")
    covered = np.array([sz[t] for t in sz if hs[t] == 1], dtype=float)
    assert covered.size >= 13                    # plenty covered in WC-2022
    assert abs(float(covered.mean())) < 1e-9
    assert abs(float(covered.std()) - 1.0) < 1e-9


def test_wc2022_masks_known_uncovered_teams():
    """The prereg names Uruguay & Iran among WC-2022's has_squad=0 set (the
    coverage-asymmetry slice). They must be masked OFF."""
    sz, hs = load_squad_anchor("wc2022")
    assert hs.get("Iran") == 0, "Iran must be masked off in WC-2022 (prereg §4)"
    assert hs.get("Uruguay") == 0, "Uruguay must be masked off in WC-2022 (prereg §4)"


def test_is_cached_returns_identical_object():
    """Cached: a second call for the same tag returns the SAME object (no re-parse)."""
    a = load_squad_anchor("euro2024")
    b = load_squad_anchor("euro2024")
    assert a is b
