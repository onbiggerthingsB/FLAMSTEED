"""StatsBomb Open Data adapter (xG, point-in-time, coverage-gated).

StatsBomb Open Data is **static + versioned** and **append-mostly** (new
competitions are added over time; data for an already-covered match is stable).
So for a COVERED match xG is **point-in-time, NOT revision-contaminated**: we
pin a release marker and set ``valid_as_of == observed_at == match_date`` — the
fact was knowable at kickoff and never gets quietly revised (north-star §4.2).
The store policy is therefore POINT_IN_TIME, exactly like results.

The real risk is **coverage**, not revision: StatsBomb is rich for big nations
and sparse/absent for minnows. xG is **NULL-safe** and **NEVER imputed** — a
match (or match-team) with no shot data produces **no row** (absent / NULL),
never a fabricated ``xg = 0``. Whether a row exists IS the coverage signal; the
companion ``xg_covered`` flag is ``True`` on every emitted row, and the
team-level coverage gap is enumerated separately in ``coverage.py``.

Release pinning: the client exposes no per-pull git tag, so we pin the installed
``statsbombpy`` version + the pull date (``config.yaml`` ``statsbomb.open_data_version``,
e.g. ``"statsbombpy-1.18.0@2026-06-03"``) as the release marker — point-in-time
"as close as release versioning allows".

Network boundary: ``statsbombpy`` hits GitHub. The thin ``fetch_*`` wrappers are
the ONLY functions that touch the network; ``normalize_match_xg`` is a pure
transform over already-pulled records, so tests inject fixtures and never
require the network.
"""
from __future__ import annotations

import pandas as pd
from statsbombpy import sb

# Public, no-auth Open Data credentials (statsbombpy's default). Naming the
# constant keeps the network boundary explicit and easy to grep.
OPEN_DATA_CREDS: dict = {"user": None, "passwd": None}

# Candidate keys for the per-shot xG value across statsbombpy/raw shapes.
_SHOT_XG_KEYS = ("shot_statsbomb_xg", "statsbomb_xg", "xg")
# Candidate keys for a pre-aggregated match-team xG (passthrough shape).
_TEAM_XG_KEYS = ("home_xg", "away_xg")


def _team_name(value) -> str:
    """Normalise a team field to its plain name.

    statsbombpy flattens nested objects, but raw match JSON nests the team under
    keys like ``{"home_team_name": "Brazil"}`` / ``{"away_team_name": ...}`` or a
    generic ``{"name": ...}``. A bare string passes straight through.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for k in ("home_team_name", "away_team_name", "team_name", "name"):
            if k in value:
                return value[k]
    return str(value)


def _shot_xg(shot: dict) -> float | None:
    for k in _SHOT_XG_KEYS:
        if k in shot and shot[k] is not None:
            return float(shot[k])
    return None


def _match_team_xg_rows(match: dict) -> list[dict]:
    """Per-(match, team) xG rows for ONE match. NEVER imputes.

    Aggregates shot-level xG (``shots``: list of ``{team, shot_statsbomb_xg}``)
    by summing each team's shots. If the record instead carries pre-aggregated
    ``home_xg`` / ``away_xg`` (match-level passthrough), those are used directly.
    A team with no shot data / no xG yields **no row** (absent, not ``0``).
    """
    match_id = match.get("match_id")
    match_date = match["match_date"]
    home = _team_name(match.get("home_team"))
    away = _team_name(match.get("away_team"))

    team_xg: dict[str, float] = {}

    shots = match.get("shots")
    if shots:
        for shot in shots:
            xg = _shot_xg(shot)
            if xg is None:
                continue  # no xG on this shot -> do not fabricate
            team = _team_name(shot.get("team"))
            team_xg[team] = team_xg.get(team, 0.0) + xg
    else:
        # Pre-aggregated match-level passthrough (only when explicitly present).
        if match.get("home_xg") is not None:
            team_xg[home] = float(match["home_xg"])
        if match.get("away_xg") is not None:
            team_xg[away] = float(match["away_xg"])

    rows: list[dict] = []
    for team, xg in team_xg.items():
        opponent = away if team == home else home
        rows.append({
            "match_id": match_id,
            "match_date": match_date,
            "team": team,
            "opponent": opponent,
            "is_home": team == home,
            "xg": xg,
        })
    return rows


def normalize_match_xg(raw, source_version: str) -> pd.DataFrame:
    """Pure transform: raw StatsBomb match records -> per-match-team xG frame.

    No store/network dependency. Emits one row per ``(match_id, team)`` that has
    xG, with ``valid_as_of == observed_at == match_date`` (point-in-time),
    ``source_version`` stamped on every row, and ``xg_covered = True`` (a row
    exists ONLY for covered match-teams; uncovered ones are absent, never
    imputed). ``match_date`` is parsed to datetime.

    Columns: ``match_id, match_date, team, opponent, is_home, xg, source_version,
    xg_covered, valid_as_of, observed_at``.
    """
    rows: list[dict] = []
    for match in raw:
        rows.extend(_match_team_xg_rows(match))

    cols = ["match_id", "match_date", "team", "opponent", "is_home", "xg",
            "source_version", "xg_covered", "valid_as_of", "observed_at"]
    if not rows:
        return pd.DataFrame(columns=cols)

    df = pd.DataFrame(rows)
    df["match_date"] = pd.to_datetime(df["match_date"])
    df["source_version"] = source_version
    df["xg_covered"] = True
    df["valid_as_of"] = df["match_date"]
    df["observed_at"] = df["match_date"]
    return df[cols]


def fetch_competitions(creds: dict | None = None) -> pd.DataFrame:
    """Pull the StatsBomb Open Data competition index (network).

    Thin wrapper over ``statsbombpy.sb.competitions``; the ONLY network entry for
    competition metadata. Tests never call this (they inject fixtures).
    """
    return sb.competitions(creds=creds or OPEN_DATA_CREDS)


def fetch_matches(competition_id: int, season_id: int,
                  creds: dict | None = None) -> pd.DataFrame:
    """Pull the match list for one competition-season (network).

    Thin wrapper over ``statsbombpy.sb.matches``. Tests never call this.
    """
    return sb.matches(competition_id, season_id, creds=creds or OPEN_DATA_CREDS)


def fetch_shots(match_id: int, creds: dict | None = None) -> pd.DataFrame:
    """Pull shot events (with ``shot_statsbomb_xg``) for one match (network).

    Thin wrapper over ``statsbombpy.sb.events`` filtered to shots. This is the
    raw xG source ``normalize_match_xg`` aggregates. Tests never call this.
    """
    events = sb.events(match_id, creds=creds or OPEN_DATA_CREDS)
    if "type" in events.columns:
        events = events[events["type"] == "Shot"]
    return events
