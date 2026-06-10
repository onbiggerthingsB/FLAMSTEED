"""Hand-curated elevation reference for the acclimatized-altitude covariate (P2a).

The acclimatized-home advantage (mission brief Phase 2a): a high-altitude home side
(Bolivia/Ecuador/Colombia in WC qualifiers; Mexico at Azteca/Akron in 2026) playing a
lowland visitor enjoys an edge BEYOND standard home advantage. The cleanly fittable
signal is the GAP between the venue altitude and what each team is *accustomed* to:

    accl_gap[team] = venue_alt − accustomed_alt[team]

A large positive gap (a lowland team at La Paz) means "far above home" — the
unacclimatized team is the one penalised. The home side of an accustomed nation has a
gap ≈ 0, so the asymmetry IS the acclimatized-home advantage. (For two lowland teams at
altitude both gaps are large + → roughly symmetric → the model barely moves, the brief's
"ambiguous, possible no-lift" secondary case.)

DETERMINISTIC, NO GEOCODING API. Both tables are hand-keyed from published elevation
references (recorded in ``SOURCES.md``). A city absent from ``CITY_ELEVATION_M`` resolves
to ``NaN`` — masked to a zero contribution downstream (the leakage-safe
``CovariateTransform`` + the ``accl_alt`` missing indicator), **never imputed/geocoded**.

These are PURE values/functions — no I/O, no network, no store. ``features.build`` joins
``accl_gap(city, team)`` onto each ``(match_id, team)`` row as the per-team ``accl_alt``
covariate column.
"""
from __future__ import annotations

import math

# Lowland default for any country not in ACCUSTOMED_ALT_M: sea-level habituation. The
# brief's "lowland default ~0–500 m" — we use 0.0 so the gap for a lowland team at a high
# venue is the full venue altitude (the honest upper-bound penalty), and a lowland team at
# a lowland venue has gap ≈ 0.
ACCUSTOMED_ALT_DEFAULT_M = 0.0

# Country → accustomed (national base-city) altitude in metres. ONLY the four nations
# whose home football environment is materially elevated; every other country defaults to
# ACCUSTOMED_ALT_DEFAULT_M. Keyed by the martj42 team name.
#
# MODELING CHOICE (documented, not a fact claim): "accustomed" = the dominant home venue's
# city altitude. Bolivia's is La Paz (the altitude-habituation-defining home, despite some
# Sucre/Santa Cruz games); Ecuador's Quito; Colombia's Bogotá; Mexico's Mexico City. This
# is a single national number — a deliberate simplification (squads may train at sea level
# in Europe), so it is an UPPER BOUND on habituation. The natural experiment leans on the
# home side being genuinely habituated, which holds for these four nations. Sources in
# SOURCES.md.
ACCUSTOMED_ALT_M: dict[str, float] = {
    "Bolivia": 3640.0,    # La Paz
    "Ecuador": 2850.0,    # Quito
    "Colombia": 2640.0,   # Bogotá
    "Mexico": 2240.0,     # Mexico City
}

# City → elevation in metres, hand-keyed from published references (SOURCES.md). Covers:
#   (a) CONMEBOL qualifier high-altitude venues that appear in the panel's `city` column,
#   (b) other notably-high venue cities encountered in the martj42 `city` data,
#   (c) the 16 WC-2026 venue cities (most lowland; listed for an exact 2026 join).
# A city NOT here → accl_gap is NaN → masked (never imputed). Both the accented "Bogotá"
# and the plain "Bogota" appear in the feed, so both are keyed.
CITY_ELEVATION_M: dict[str, float] = {
    # (a) CONMEBOL high-altitude qualifier/finals venues
    "La Paz": 3640.0,          # Bolivia (Estadio Hernando Siles)
    "Quito": 2850.0,           # Ecuador (Estadio Olímpico Atahualpa)
    "Bogotá": 2640.0,          # Colombia (Estadio El Campín)
    "Bogota": 2640.0,          # martj42 also emits the unaccented form
    "Sucre": 2810.0,           # Bolivia (constitutional capital; some Bolivia home games)
    "Cusco": 3399.0,           # Peru (Estadio Garcilaso)
    "Cuzco": 3399.0,           # alternate spelling
    "Oruro": 3735.0,           # Bolivia
    "Cochabamba": 2558.0,      # Bolivia
    # (b) other notable high venue cities in the panel
    "Mexico City": 2240.0,     # Mexico (Estadio Azteca)
    "Toluca": 2660.0,          # Mexico (Estadio Nemesio Díez; higher than Mexico City)
    "Pachuca": 2400.0,         # Mexico
    "Puebla": 2135.0,          # Mexico
    "Guadalajara": 1566.0,     # Mexico (city proper; the 2026 stadium is in Zapopan, below)
    "Quetzaltenango": 2330.0,  # Guatemala
    "Guatemala City": 1500.0,  # Guatemala
    "San José": 1170.0,        # Costa Rica
    "Addis Ababa": 2355.0,     # Ethiopia
    "Asmara": 2325.0,          # Eritrea
    "Nairobi": 1795.0,         # Kenya
    "Johannesburg": 1753.0,    # South Africa
    "Sanaa": 2250.0,           # Yemen
    "Sana'a": 2250.0,          # alternate spelling
    "Calama": 2260.0,          # Chile (high-altitude Atacama)
    "Riobamba": 2754.0,        # Ecuador
    "Ambato": 2577.0,          # Ecuador
    "Cuenca": 2560.0,          # Ecuador
    # (c) the 16 WC-2026 venue cities (from config/tournament_2026.yaml). Most lowland.
    "Vancouver": 18.0,
    "Seattle": 10.0,
    "San Francisco Bay Area (Santa Clara)": 3.0,
    "Los Angeles (Inglewood)": 38.0,
    "Guadalajara (Zapopan)": 1675.0,    # Estadio Akron — the 2026 high-ish venue
    # "Mexico City" already keyed above (2240) — Estadio Azteca, the 2026 high venue.
    "Monterrey (Guadalupe)": 494.0,
    "Houston": 13.0,
    "Dallas (Arlington)": 193.0,
    "Kansas City": 259.0,
    "Atlanta": 308.0,
    "Miami (Miami Gardens)": 5.0,
    "Toronto": 83.0,
    "Boston (Foxborough)": 84.0,
    "Philadelphia": 0.0,
    "New York/New Jersey (East Rutherford)": 4.0,
}


def accustomed_alt(team: str) -> float:
    """Accustomed (national base-city) altitude in metres for ``team``.

    The four habituated nations return their documented base-city altitude; every other
    team returns ``ACCUSTOMED_ALT_DEFAULT_M`` (lowland). Pure lookup, never raises.
    """
    return ACCUSTOMED_ALT_M.get(team, ACCUSTOMED_ALT_DEFAULT_M)


def accl_gap(city, team: str) -> float:
    """Acclimatized-altitude gap (metres) for ``team`` at ``city``:

        venue_elevation(city) − accustomed_alt(team)

    A large positive gap = "much higher than this team is used to" (the unacclimatized
    penalty). An accustomed nation at its own high venue has gap ≈ 0. A city NOT in
    ``CITY_ELEVATION_M`` (or a null ``city``) → ``NaN`` (masked downstream, never imputed).
    """
    if city is None or (isinstance(city, float) and math.isnan(city)):
        return float("nan")
    venue = CITY_ELEVATION_M.get(city)
    if venue is None:
        return float("nan")
    return float(venue) - accustomed_alt(team)
