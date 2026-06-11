"""P2a Task 1 — elevation reference tables + accl_gap (acclimatized-altitude input).

Pure-value tests: the hand-curated tables are plausible, the four accustomed nations
resolve to their documented altitudes (everyone else lowland), accl_gap does the right
arithmetic, and an UNKNOWN city resolves to NaN (masked downstream, never imputed).
"""
from __future__ import annotations

import math
from pathlib import Path

import yaml

from wcmodel.data.sources.altitude_ref import (
    ACCUSTOMED_ALT_DEFAULT_M,
    ACCUSTOMED_ALT_M,
    CITY_ELEVATION_M,
    accl_gap,
    accustomed_alt,
)


def test_accustomed_nations_resolve_others_default_lowland():
    # The four habituated nations carry their documented base-city altitude.
    assert accustomed_alt("Bolivia") == 3640.0   # La Paz
    assert accustomed_alt("Ecuador") == 2850.0   # Quito
    assert accustomed_alt("Colombia") == 2640.0  # Bogotá
    assert accustomed_alt("Mexico") == 2240.0    # Mexico City
    # Every other team → lowland default (0.0). No fabricated mid-altitude guesses.
    for team in ("Brazil", "Argentina", "Germany", "Japan", "Peru", "Costa Rica"):
        assert accustomed_alt(team) == ACCUSTOMED_ALT_DEFAULT_M == 0.0


def test_city_table_covers_conmebol_altitude_venues_with_plausible_values():
    # The CONMEBOL natural-experiment venues are present and plausible.
    assert abs(CITY_ELEVATION_M["La Paz"] - 3640.0) < 100.0
    assert abs(CITY_ELEVATION_M["Quito"] - 2850.0) < 100.0
    assert abs(CITY_ELEVATION_M["Bogotá"] - 2640.0) < 100.0
    assert "Sucre" in CITY_ELEVATION_M and CITY_ELEVATION_M["Sucre"] > 2000.0
    # Both spellings the feed emits resolve identically.
    assert CITY_ELEVATION_M["Bogotá"] == CITY_ELEVATION_M["Bogota"]


def test_city_table_covers_all_16_wc2026_venue_cities():
    # Every WC-2026 venue city must be in the table (an exact 2026 join, no NaN host venue).
    yaml_path = Path(__file__).resolve().parents[2] / "config" / "tournament_2026.yaml"
    venues = yaml.safe_load(yaml_path.read_text())["venues"]
    cities = {v["city"] for v in venues}
    missing = cities - set(CITY_ELEVATION_M)
    assert not missing, f"WC-2026 venue cities absent from CITY_ELEVATION_M: {sorted(missing)}"
    # The two high 2026 venues are meaningfully elevated; the rest lowland.
    assert CITY_ELEVATION_M["Mexico City"] > 2000.0          # Estadio Azteca
    assert CITY_ELEVATION_M["Guadalajara (Zapopan)"] > 1000.0  # Estadio Akron
    for low in ("Seattle", "Miami (Miami Gardens)", "Philadelphia", "Houston"):
        assert CITY_ELEVATION_M[low] < 100.0


def test_accl_gap_arithmetic_acclimatized_home_vs_lowland_visitor():
    # The natural experiment: Bolivia at La Paz is acclimatized (gap ≈ 0); a lowland
    # visitor faces the full altitude gap (the unacclimatized penalty).
    assert abs(accl_gap("La Paz", "Bolivia")) < 50.0            # home, acclimatized
    assert abs(accl_gap("La Paz", "Brazil") - 3640.0) < 50.0    # lowland visitor at altitude
    assert abs(accl_gap("Quito", "Brazil") - 2850.0) < 50.0
    # An accustomed nation playing AWAY at a sea-level venue: a large NEGATIVE gap
    # (lower than home) — direction matters, the term is signed.
    assert accl_gap("Seattle", "Bolivia") < -3000.0
    # A lowland team at a lowland venue: gap ≈ 0.
    assert abs(accl_gap("Miami (Miami Gardens)", "Brazil")) < 50.0


def test_accl_gap_unknown_city_is_nan_not_imputed():
    # Coverage honesty: an unknown venue city → NaN (masked, never guessed).
    assert math.isnan(accl_gap("Nowhere-City", "Brazil"))
    assert math.isnan(accl_gap("Nowhere-City", "Bolivia"))
    assert math.isnan(accl_gap(None, "Brazil"))
    assert math.isnan(accl_gap(float("nan"), "Brazil"))
