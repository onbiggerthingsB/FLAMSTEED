"""WC-2026 tournament structure: loader + validator (GATED).

The 2026 World Cup is the first 48-team edition: **12 groups of 4** (48 teams),
**104 fixtures**, top two of each group plus the **8 best third-placed teams**
advancing to a 32-team knockout, with the bracket split into two halves
("paths") that only meet in the final.

This module deliberately ships **no draw data**. Authoring or fabricating the
groups/fixtures here would invent facts; the verified draw is supplied by the
user as ``config/tournament_2026.yaml`` (Phase-0 decision 2). What lives here is
purely the *structure contract* — a strict ``validate_tournament`` plus a thin
``load_tournament`` that reads the YAML and validates it — so that whenever the
real file lands it is checked against the known 2026 format before anything
downstream consumes it.

The third-place tiebreaker ORDER is the published FIFA sequence and is enforced
exactly: ``goal_difference``, ``goals_scored``, ``head_to_head``, ``fair_play``,
``drawing_of_lots``. No network, no store dependency — pure validation + a YAML
read.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from wcmodel.data.sources.results import normalize_results
from wcmodel.data.store import BitemporalStore, Policy

#: 2026 is the first 48-team World Cup.
N_TEAMS = 48
#: Twelve groups...
N_GROUPS = 12
#: ...of four teams each.
TEAMS_PER_GROUP = 4
#: 104 matches across group stage + knockouts (the published 2026 count).
N_FIXTURES = 104
#: Top two of every group advance directly.
ADVANCE_PER_GROUP = 2
#: Plus the eight best third-placed teams.
BEST_THIRDS = 8
#: Published FIFA third-place tiebreaker sequence — order is significant.
THIRD_PLACE_TIEBREAKERS = [
    "goal_difference",
    "goals_scored",
    "head_to_head",
    "fair_play",
    "drawing_of_lots",
]

#: A team name that FULLY matches this is a knockout-bracket PLACEHOLDER, not a
#: nation: a group-position slot (``2A`` — a digit then a group letter A-L), a
#: winner/loser ref (``W74`` / ``L101``), or a best-third slot (``3rd-ABCDF`` /
#: ``3rd ABCDF``). ANCHORED (``^...$``) so it can never partial-match a real
#: nation — no WC-2026 country name starts with a digit+A-L, ``W``/``L``+digits,
#: or ``3rd``. (Real nations were verified against this; see
#: ``validate_tournament`` and its tests.) IGNORECASE makes ``3RD``/``w74`` etc.
#: also trip — bracket exports vary in case, nations still never match.
_PLACEHOLDER_TEAM_RE = re.compile(r"^(\d[A-L]|W\d+|L\d+|3rd[- ].*)$", re.IGNORECASE)
#: Structural word tokens that only ever appear in PLACEHOLDER labels (never in a
#: real nation's common-English name). A name whose lowercase form CONTAINS any
#: of these is rejected as a placeholder, complementing the anchored regex above
#: (this catches free-text slot labels like "Playoff Winner A" / "Runner-up
#: Group B" / "UEFA Path A" that the slot/ref regex would miss).
_PLACEHOLDER_WORDS = (
    "tbd", "playoff", "play-off", "winner", "runner-up", "runner up",
    "uefa path",
)


def _is_placeholder_team(name: object) -> bool:
    """True iff ``name`` is a knockout-bracket placeholder, not a real nation.

    A name is a placeholder if it FULLY matches :data:`_PLACEHOLDER_TEAM_RE`
    (slot/winner/loser/best-third shape) OR — lowercased — CONTAINS any
    :data:`_PLACEHOLDER_WORDS` token. Non-string names are treated as
    placeholders (a real team name is always a string). Real WC-2026 nation
    names never satisfy either condition.
    """
    if not isinstance(name, str):
        return True
    if _PLACEHOLDER_TEAM_RE.match(name):
        return True
    low = name.lower()
    return any(word in low for word in _PLACEHOLDER_WORDS)


def validate_tournament(data: dict) -> dict:
    """Validate a WC-2026 tournament structure against the known 2026 format.

    Enforces, raising :class:`ValueError` with a clear message on any violation:

      - exactly 12 ``groups``, each with exactly 4 ``teams``;
      - 48 teams total across the groups, all distinct;
      - a top-level ``teams`` list of exactly 48 DISTINCT names whose SET equals
        the union of the group teams (so a placeholder smuggled into top-level
        ``teams`` is a hard failure — the drawn-48 set ingestion trusts is
        code-enforced to be exactly the group set);
      - exactly 104 ``fixtures``;
      - ``advancement.per_group == 2`` and ``advancement.best_thirds == 8``;
      - ``third_place_tiebreakers`` equal to the published FIFA sequence, in the
        exact order ``[goal_difference, goals_scored, head_to_head, fair_play,
        drawing_of_lots]``;
      - a ``bracket`` with exactly two ``paths`` (the two knockout halves).

    Returns ``data`` unchanged when valid. This does NOT author or infer any
    draw content — it only checks the shape of a user-supplied structure.

    FORMAT DISPATCH (Phase-2A). A document carrying a ``format`` block declares
    its own shape and is validated by :func:`_validate_formatted` against THAT
    format. A document WITHOUT one — every WC-2026 document, including the
    published ``config/tournament_2026.yaml`` — falls through to the frozen body
    below, which is unchanged byte-for-byte: the WC path never routes through the
    generalized checks, so it cannot be perturbed by them.
    """
    has_format = "format" in data
    if has_format:
        # Raises on ``format: null`` / non-dict / partial block (fail loud — a
        # malformed format block is a config bug, never a silent WC default).
        fmt = tournament_format(data)
        return _validate_formatted(data, fmt)

    groups = data.get("groups")
    if not isinstance(groups, list) or len(groups) != N_GROUPS:
        n = len(groups) if isinstance(groups, list) else "missing"
        raise ValueError(f"expected exactly {N_GROUPS} groups, got {n}")

    all_teams: list[str] = []
    for group in groups:
        teams = group.get("teams") if isinstance(group, dict) else None
        if not isinstance(teams, list) or len(teams) != TEAMS_PER_GROUP:
            name = group.get("name") if isinstance(group, dict) else group
            n = len(teams) if isinstance(teams, list) else "missing"
            raise ValueError(
                f"group {name!r}: expected exactly {TEAMS_PER_GROUP} teams, got {n}"
            )
        all_teams.extend(teams)

    if len(all_teams) != N_TEAMS:
        raise ValueError(
            f"expected {N_TEAMS} teams total across groups, got {len(all_teams)}"
        )
    if len(set(all_teams)) != N_TEAMS:
        dupes = sorted({t for t in all_teams if all_teams.count(t) > 1})
        raise ValueError(f"team names must be distinct; duplicates: {dupes}")

    # Placeholder-SHAPED name guard (defense-in-depth). The teams==groups /
    # 48-distinct checks reject a placeholder smuggled into ONLY top-level `teams`
    # (it would be in no group). But a placeholder smuggled into BOTH a group AND
    # top-level `teams` is self-consistent — it passes those checks — and would
    # then be ingested as if it were a real nation. Real nations never look like
    # bracket slots, so reject placeholder-SHAPED names outright: scan EVERY team
    # in EVERY group AND top-level `teams`, and raise if ANY matches the anchored
    # slot/ref regex or carries a structural word token (see _is_placeholder_team).
    candidate_names = list(all_teams)
    raw_teams = data.get("teams")
    if isinstance(raw_teams, list):
        candidate_names.extend(raw_teams)
    offending = sorted(
        {n for n in candidate_names if _is_placeholder_team(n)}, key=str
    )
    if offending:
        raise ValueError(
            "team names must be real nations, not knockout-bracket placeholders; "
            f"offending: {offending}"
        )

    # Top-level `teams` is the drawn-48 set that downstream ingestion trusts, so
    # it MUST be a list of exactly 48 DISTINCT names AND equal (as a set) to the
    # union of the group teams. This is what makes "a placeholder can't reach the
    # store" code-enforced rather than convention: a token smuggled into
    # top-level `teams` (e.g. "2A") that is in no group, OR any teams/groups
    # mismatch, is a hard validation failure here — before anything consumes it.
    teams = data.get("teams")
    if not isinstance(teams, list) or len(teams) != N_TEAMS:
        n = len(teams) if isinstance(teams, list) else "missing"
        raise ValueError(
            f"top-level 'teams' must be a list of exactly {N_TEAMS}, got {n}"
        )
    if len(set(teams)) != N_TEAMS:
        dupes = sorted({t for t in teams if teams.count(t) > 1})
        raise ValueError(f"top-level 'teams' must be distinct; duplicates: {dupes}")
    if set(teams) != set(all_teams):
        only_top = sorted(set(teams) - set(all_teams))
        only_grp = sorted(set(all_teams) - set(teams))
        raise ValueError(
            "top-level 'teams' must equal the union of group teams; "
            f"in 'teams' but no group: {only_top}; in a group but not 'teams': "
            f"{only_grp}"
        )

    fixtures = data.get("fixtures")
    if not isinstance(fixtures, list) or len(fixtures) != N_FIXTURES:
        n = len(fixtures) if isinstance(fixtures, list) else "missing"
        raise ValueError(f"expected exactly {N_FIXTURES} fixtures, got {n}")

    advancement = data.get("advancement")
    if not isinstance(advancement, dict):
        raise ValueError("missing 'advancement' block")
    if advancement.get("per_group") != ADVANCE_PER_GROUP:
        raise ValueError(
            f"advancement.per_group must be {ADVANCE_PER_GROUP}, "
            f"got {advancement.get('per_group')!r}"
        )
    if advancement.get("best_thirds") != BEST_THIRDS:
        raise ValueError(
            f"advancement.best_thirds must be {BEST_THIRDS}, "
            f"got {advancement.get('best_thirds')!r}"
        )

    tiebreakers = data.get("third_place_tiebreakers")
    if tiebreakers != THIRD_PLACE_TIEBREAKERS:
        raise ValueError(
            "third_place_tiebreakers must be exactly "
            f"{THIRD_PLACE_TIEBREAKERS}, got {tiebreakers!r}"
        )

    bracket = data.get("bracket")
    paths = bracket.get("paths") if isinstance(bracket, dict) else None
    if not isinstance(paths, list) or len(paths) != 2:
        n = len(paths) if isinstance(paths, list) else "missing"
        raise ValueError(f"bracket must declare exactly two paths, got {n}")

    return data


def load_tournament(path: str | Path) -> dict:
    """Read a WC-2026 draw YAML, validate it, and return the parsed structure.

    GATED: the verified ``config/tournament_2026.yaml`` is provided by the user
    (Phase-0 decision 2) and is intentionally absent from the repo; nothing here
    fabricates it. Reads the file, runs :func:`validate_tournament`, and returns
    the validated dict.
    """
    with open(path) as f:
        data = yaml.safe_load(f)
    return validate_tournament(data)


#: 2026 co-host nations -> the ISO country code their venues carry in the draw's
#: ``venues`` block. A group fixture at a venue in a host's country is NOT played
#: on neutral ground *for that host* (Mexico/USA/Canada playing at home); every
#: other group match is on neutral ground. Keyed by the martj42 team name (the
#: same key the fixtures use) so the membership test is exact.
HOST_COUNTRY_BY_TEAM = {
    "Mexico": "MX",
    "United States": "US",
    "Canada": "CA",
}

#: Every key a ``format`` block must declare. Deliberately EXHAUSTIVE and with no
#: per-key defaults: a partially-specified edition is a config bug that must fail
#: loud at load time, not silently inherit half of the World Cup's shape.
_FORMAT_KEYS = ("n_groups", "teams_per_group", "per_group_advance", "best_thirds",
                "third_place_match", "tiebreak_order", "assignment_table",
                "competition_name", "source_tag", "hosts", "ko_host_advantage")

#: The frozen WC-2026 shape — the effective format of every document WITHOUT a
#: ``format`` block. Values mirror the module constants above so the two can never
#: disagree; ``hosts`` is copied per call (see :func:`tournament_format`) so a
#: caller mutating the returned map cannot corrupt :data:`HOST_COUNTRY_BY_TEAM`.
_WC2026_FORMAT = {
    "n_groups": N_GROUPS, "teams_per_group": TEAMS_PER_GROUP,
    "per_group_advance": ADVANCE_PER_GROUP, "best_thirds": BEST_THIRDS,
    "third_place_match": True, "tiebreak_order": "fifa_2026",
    "assignment_table": "third_place_assignment.json",
    "competition_name": "FIFA World Cup", "source_tag": "wc2026_schedule",
    "hosts": dict(HOST_COUNTRY_BY_TEAM), "ko_host_advantage": False,
}


def tournament_format(data: dict) -> dict:
    """Effective format. Absent 'format' key -> frozen WC-2026 defaults
    (byte-identical published path). Present -> ALL keys required, fail loud.
    format: null / non-dict is a config bug, never a silent default."""
    if "format" in data:
        fmt = data["format"]
        if not isinstance(fmt, dict):
            raise ValueError("format must be a mapping")
        missing = [k for k in _FORMAT_KEYS if k not in fmt]
        if missing:
            raise ValueError(f"format block missing key(s): {missing}")
        out = {k: fmt[k] for k in _FORMAT_KEYS}
        out["hosts"] = dict(out["hosts"])
        return out
    return {**_WC2026_FORMAT, "hosts": dict(HOST_COUNTRY_BY_TEAM)}


def _validate_formatted(data: dict, fmt: dict) -> dict:
    """Validate a tournament that DECLARES its format (the non-WC path).

    Replicates the structural guarantees of the frozen WC-2026 branch — group
    count/size, distinct teams, no placeholder-shaped nation names, top-level
    ``teams`` equal to the group union — but derives every count from ``fmt``
    instead of the WC literals, and replaces the single ``N_FIXTURES`` check with
    a group/knockout SPLIT check (group fixtures carry no ``match`` key, knockout
    fixtures do):

      - ``len(group fixtures) == n_groups * 6`` (each 4-team group plays 6 games);
      - ``len(knockout fixtures) == (advancers - 1) + third_place_match``, where
        ``advancers = n_groups * per_group_advance + best_thirds``. A single-
        elimination bracket needs exactly one match per eliminated team, plus the
        third-place play-off IFF the edition stages one (the AFC Asian Cup does
        NOT — 24 teams, 16 advancers, 15 knockout matches, 51 total).

    The legacy ``advancement`` / ``third_place_tiebreakers`` / ``bracket.paths``
    LITERAL checks are deliberately NOT applied here: those facts are declared by
    the format block itself (``per_group_advance`` / ``best_thirds`` /
    ``tiebreak_order``), and the two-halves bracket shape is a WC-specific
    convention. ``bracket.paths`` is left unchecked for formatted editions.
    """
    groups = data.get("groups")
    if not isinstance(groups, list) or len(groups) != fmt["n_groups"]:
        n = len(groups) if isinstance(groups, list) else "missing"
        raise ValueError(f"expected exactly {fmt['n_groups']} groups, got {n}")

    all_teams: list[str] = []
    for group in groups:
        teams = group.get("teams") if isinstance(group, dict) else None
        if not isinstance(teams, list) or len(teams) != fmt["teams_per_group"]:
            name = group.get("name") if isinstance(group, dict) else group
            n = len(teams) if isinstance(teams, list) else "missing"
            raise ValueError(
                f"group {name!r}: expected exactly {fmt['teams_per_group']} teams, got {n}"
            )
        all_teams.extend(teams)

    n_teams = fmt["n_groups"] * fmt["teams_per_group"]
    if len(all_teams) != n_teams:
        raise ValueError(
            f"expected {n_teams} teams total across groups, got {len(all_teams)}"
        )
    if len(set(all_teams)) != n_teams:
        dupes = sorted({t for t in all_teams if all_teams.count(t) > 1})
        raise ValueError(f"team names must be distinct; duplicates: {dupes}")

    # Placeholder-SHAPED name guard — identical policy to the WC branch: a bracket
    # slot/ref smuggled into a group AND top-level `teams` is self-consistent, so
    # reject the SHAPE outright (see _is_placeholder_team).
    candidate_names = list(all_teams)
    raw_teams = data.get("teams")
    if isinstance(raw_teams, list):
        candidate_names.extend(raw_teams)
    offending = sorted(
        {n for n in candidate_names if _is_placeholder_team(n)}, key=str
    )
    if offending:
        raise ValueError(
            "team names must be real nations, not knockout-bracket placeholders; "
            f"offending: {offending}"
        )

    teams = data.get("teams")
    if not isinstance(teams, list) or len(teams) != n_teams:
        n = len(teams) if isinstance(teams, list) else "missing"
        raise ValueError(
            f"top-level 'teams' must be a list of exactly {n_teams}, got {n}"
        )
    if len(set(teams)) != n_teams:
        dupes = sorted({t for t in teams if teams.count(t) > 1})
        raise ValueError(f"top-level 'teams' must be distinct; duplicates: {dupes}")
    if set(teams) != set(all_teams):
        only_top = sorted(set(teams) - set(all_teams))
        only_grp = sorted(set(all_teams) - set(teams))
        raise ValueError(
            "top-level 'teams' must equal the union of group teams; "
            f"in 'teams' but no group: {only_top}; in a group but not 'teams': "
            f"{only_grp}"
        )

    fixtures = data.get("fixtures")
    if not isinstance(fixtures, list):
        raise ValueError("'fixtures' must be a list")

    group_fx = [f for f in fixtures if f.get("match") is None]
    ko_fx = [f for f in fixtures if f.get("match") is not None]
    if len(group_fx) != fmt["n_groups"] * 6:
        raise ValueError(f"group fixture count {len(group_fx)} != {fmt['n_groups'] * 6}")
    advancers = fmt["n_groups"] * fmt["per_group_advance"] + fmt["best_thirds"]
    expected_ko = (advancers - 1) + (1 if fmt["third_place_match"] else 0)
    if len(ko_fx) != expected_ko:
        raise ValueError(f"knockout fixture count {len(ko_fx)} != {expected_ko}")
    if fmt["teams_per_group"] != 4:
        raise ValueError("only 4-team groups supported (6-games-per-group math)")

    return data


def host_home_factor(home, away, venue_city, venue_country, cfg, hosts=None):
    """The T5 host-advantage multiplier for one fixture, or ``None`` for neutral ground.

    Returns ``cfg["model"]["covariates"]["host_k"]`` IFF the HOME team is a host
    nation of THIS edition AND the fixture's venue is in **that same host's country**;
    otherwise ``None`` (the fixture is modelled on neutral ground — the existing WC
    default).

    ``hosts`` is the edition's ``{team: ISO-country}`` map. ``None`` (the default)
    means the frozen WC-2026 module literal :data:`HOST_COUNTRY_BY_TEAM`, so every
    pre-Phase-2A call site is byte-identical; a formatted edition passes its own map
    (``tournament_format(t)["hosts"]``). The map is read HERE rather than at the
    caller so no call site can accidentally keep applying the World Cup's hosts to
    another tournament (Phase-2A F5: the fix belongs at the source).

    This is the focal host-detection rule the predict path consumes as ``host_factor``
    (a prediction-time scalar on the already-fitted ``home_adv`` — NO new fitted DOF).
    It is deliberately STRICTER than the ``ingest_wc_group_fixtures`` neutral flag (which
    fires when EITHER team is the venue's host): host advantage accrues to the HOME team
    only, and only at a venue in its OWN country. So:

      * a host playing AWAY (the host is ``away``)        -> ``None`` (home team is not a host);
      * a host at an OUT-OF-COUNTRY venue (USA in Mexico) -> ``None`` (venue country != USA);
      * a non-host home team                              -> ``None`` (not a host nation);
      * a host at an in-country venue (Mexico in Mexico)  -> ``host_k``.

    ``venue_country`` is the ``{city: ISO-country}`` map built from the draw's ``venues``
    block (see :func:`host_factor_map`). An unknown/None venue country can never match a
    host's code, so it correctly yields ``None``. The ``away`` argument is accepted for a
    symmetric, self-documenting signature even though the rule is HOME-only (a future
    refinement could read it; today it is intentionally unused)."""
    if hosts is None:
        hosts = HOST_COUNTRY_BY_TEAM      # frozen WC-2026 default (byte-identical)
    host_code = hosts.get(home)
    if host_code is None:
        return None                       # home team is not a host nation
    if venue_country.get(venue_city) != host_code:
        return None                       # venue is not in the host's own country
    return cfg["model"]["covariates"]["host_k"]


def host_factor_map(tournament, cfg):
    """``{(home, away): host_factor}`` for every GROUP fixture that is host-home.

    Walks the tournament's group fixtures (``match is None``), resolves each fixture's
    venue to its ISO country via the draw's ``venues`` block, and records the per-fixture
    :func:`host_home_factor` only for the host-home ones (a neutral fixture is simply
    absent from the map, so a lookup miss == neutral). The sim threads this map so a
    host's home group game carries ``k*home_adv`` while every other fixture stays neutral.

    A tournament dict with no ``venues`` block (e.g. a tiny synthetic test bracket) yields
    an EMPTY country map, so no fixture is ever host-home and the map is ``{}`` — the sim
    is then byte-identical to its neutral default. Knockout fixtures (placeholder feeders,
    no concrete home team) are skipped here: a KO host advantage cannot be resolved from
    the draw (the feeders are placeholders), so it is applied IN-SIM once the participants
    are concrete — and only for editions whose format sets ``ko_host_advantage``.

    The host map comes from the tournament's own format block
    (``tournament_format(t)["hosts"]``), so a non-WC edition never inherits the World
    Cup's hosts; a document with no ``format`` block resolves to the frozen WC literal."""
    hosts = tournament_format(tournament)["hosts"]
    venue_country = {v["city"]: v.get("country") for v in tournament.get("venues", [])}
    out = {}
    for fx in tournament.get("fixtures", []):
        if fx.get("match") is not None:
            continue                      # skip knockouts (placeholder feeders, no concrete home)
        home, away = fx.get("home"), fx.get("away")
        factor = host_home_factor(home, away, fx.get("venue"), venue_country, cfg,
                                  hosts=hosts)
        if factor is not None:
            out[(home, away)] = factor
    return out

#: The ``source`` tag stamped on ingested WC-2026 schedule rows (distinct from
#: the historical martj42 ``results`` feed).
WC2026_SOURCE = "wc2026_schedule"


def _drawn_teams(tournament: dict) -> set[str]:
    """The drawn-48 set, derived from the GROUP teams, EXCLUDING any
    placeholder-shaped name (second belt-and-suspenders guard).

    ``ingest_wc_group_fixtures`` uses this set as the group/knockout
    discriminator. Reading it from the groups (not raw top-level ``teams``)
    already prevents a placeholder smuggled into top-level ``teams`` from
    widening the membership test; filtering out :func:`_is_placeholder_team`
    names here additionally ensures that even a placeholder smuggled into a
    GROUP can never enter ``drawn`` — so it can never be written as a group row.
    On a validated document this filter is a no-op (the validator already
    rejects placeholder-shaped names), so it never changes the happy path.
    """
    return {
        team
        for group in tournament["groups"]
        for team in group["teams"]
        if not _is_placeholder_team(team)
    }


def ingest_wc_group_fixtures(
    tournament: dict,
    store: BitemporalStore,
    *,
    observed_at: str | pd.Timestamp,
) -> int:
    """Write the 72 WC-2026 **group-stage** fixtures into ``results`` as
    future-dated, UNPLAYED rows; return the number of rows written.

    Each group fixture (the only fixtures whose BOTH teams are real drawn
    nations — see below) becomes one ``results`` row with:

      - ``home_team`` / ``away_team`` straight from the draw (already martj42
        keys, so :func:`wcmodel.data.features.build` can join each team's
        history);
      - ``date`` = the fixture date, ``home_score`` / ``away_score`` = **NaN**
        (the match has not been played — it is a *schedule*, not a result);
      - ``neutral`` = ``False`` iff one of the EDITION's host nations (the
        format's ``hosts`` map — the WC-2026 default is exactly
        :data:`HOST_COUNTRY_BY_TEAM`: Mexico/USA/Canada) plays at a venue in
        **its own** country, else ``True``;
      - ``tournament`` = the format's ``competition_name`` (WC default:
        the literal ``"FIFA World Cup"``), ``city`` / ``country`` from the
        venue;
      - a deterministic ``match_id`` (the standard
        ``sha1(date|home|away|city)`` via :func:`normalize_results`);
      - ``valid_as_of == observed_at == date`` (POINT_IN_TIME): the fixture
        schedule is treated as knowable on the fixture's own day and the row
        never gets revised (the same immutable-result convention the historical
        martj42 feed uses). ``observed_at`` is asserted to be on/before the
        earliest fixture date so this PIT stamping is self-consistent.

    The 32 **knockout** fixtures are deliberately **NOT** ingested: their
    "teams" are structure placeholders (group-position slots like ``2A`` /
    ``3rd-ABCDF`` and winner/loser refs like ``W74`` / ``L101``), not real
    matches. They stay in the config as bracket structure for Phase 3. The
    group/knockout split is made on a hard fact — *both* participants being
    members of the drawn-teams set, derived from the validated GROUP teams — so
    no placeholder token can ever reach the store even if the fixture shape
    changes (and even if ``validate_tournament`` were bypassed).

    UNPLAYED + future-dated by construction, these rows are leakage-SAFE: the
    played filter in ``features.build`` drops every NaN-score row (so an
    in-progress group match before a mid-tournament cutoff cannot enter as-of
    features), and a pre-WC cutoff excludes them on date. See the WC in-progress
    leakage test for the proof.
    """
    # Validate at ENTRY so ingestion can NEVER run on an unvalidated/malformed
    # doc: the validator rejects teams!=groups, non-48, and placeholder-SHAPED
    # names (`2A`/`W74`/…) outright. This closes the bypass where a caller skips
    # `validate_tournament` and smuggles a placeholder into a group — such a doc
    # now raises here before any row is derived. (Idempotent: re-validating an
    # already-validated dict returns it unchanged.)
    validate_tournament(tournament)
    observed_at = pd.Timestamp(observed_at)
    # Provenance + host wiring come from the EFFECTIVE FORMAT (Phase-2A F11):
    # a document with no `format` block resolves to the frozen WC-2026 defaults
    # — competition_name "FIFA World Cup", source_tag WC2026_SOURCE, hosts ==
    # HOST_COUNTRY_BY_TEAM — so every WC row below is byte-identical to the
    # pre-format literals; a formatted edition stamps its own tags and hosts.
    fmt = tournament_format(tournament)

    # Drawn-48 set derived from the GROUP teams — the VALIDATED source — with
    # placeholder-shaped names excluded as a SECOND guard (see `_drawn_teams`).
    # `validate_tournament` (run above) guarantees top-level `teams` equals this
    # group union, but we read it from the groups directly (not raw top-level
    # `teams`) so that even absent validation, no placeholder smuggled into
    # top-level `teams` could widen the membership test below. Belt-and-suspenders
    # with the validator: a knockout placeholder (e.g. `2A`/`W74`), never a member
    # of any group AND filtered by `_is_placeholder_team`, can never enter `drawn`
    # and so can never be written as a group row.
    drawn = _drawn_teams(tournament)
    venue_country = {v["city"]: v.get("country") for v in tournament["venues"]}
    # country-code -> host team name, for the neutral-ground test (edition hosts).
    host_by_country = {code: team for team, code in fmt["hosts"].items()}

    rows: list[dict] = []
    for fx in tournament["fixtures"]:
        home, away = fx.get("home"), fx.get("away")
        # GROUP discriminator: both participants are real drawn nations.
        # Knockout rows fail this (a placeholder like `2A`/`W74` is not in
        # `drawn`), so they are skipped — never ingested.
        if home not in drawn or away not in drawn:
            continue

        city = fx.get("venue")
        country = venue_country.get(city)
        # Non-neutral iff THIS venue's host nation is one of the two teams.
        host_team = host_by_country.get(country)
        neutral = not (host_team is not None and host_team in (home, away))

        rows.append({
            "date": fx["date"],
            "home_team": home,
            "away_team": away,
            "home_score": np.nan,   # UNPLAYED — schedule, not result
            "away_score": np.nan,
            "tournament": fmt["competition_name"],
            "neutral": neutral,
            "city": city,
            "country": country,
        })

    raw = pd.DataFrame(
        rows,
        columns=["date", "home_team", "away_team", "home_score", "away_score",
                 "tournament", "neutral", "city", "country"],
    )
    # normalize_results stamps the deterministic match_id and sets
    # valid_as_of == observed_at == date (the immutable-result convention). That
    # is exactly the PIT stamping the task requires (`valid_as_of=observed_at=
    # date`), so we keep it as-is. We only assert the caller's `observed_at` is
    # consistent with it (knowable on/before the first kickoff) — a guard that
    # the schedule isn't being back-stamped as known AFTER matches start.
    out = normalize_results(raw)
    if not out.empty:
        first_kickoff = pd.to_datetime(out["date"]).min()
        if observed_at > first_kickoff:
            raise ValueError(
                f"observed_at {observed_at.date()} is after the first "
                f"{fmt['competition_name']} fixture {first_kickoff.date()}: "
                "the schedule must be ingested as knowable on/before kickoff "
                "(PIT valid_as_of==date)"
            )

    store.write(
        "results",
        out,
        policy=Policy.POINT_IN_TIME,
        keys=["match_id"],
        source=fmt["source_tag"],
        source_version=fmt["source_tag"],
    )
    return len(out)
