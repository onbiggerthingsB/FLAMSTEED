"""A12 — `dc_1x2_avail`: the availability shadow arm. A fixed prior, not a fit.

    PYTHONPATH=src:. .venv/bin/python -m epl.availarm verify
    PYTHONPATH=src:. .venv/bin/python -m epl.availarm score \\
        --directory data/epl/sim/issuances/2026_27/2026-08-28 \\
        --results <results.jsonl>

WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
---------------------------------------------
A12 authorises a SECOND shadow challenger beside A8's, and the two are
siblings by construction: a match-only transform of the PUBLISHED `dc_native`
1X2 marginals, filed in its own append-only ledger, scored against the same
results through the same literal. It produces **no table, no position matrix,
no consequence state, no matchboard, no arm in any issuance, and no change to
any published number of any kind.** `ISSUANCE_SCHEMA_VERSION` stays
`epl-issuance-5`; the A7 scorecard and the A8 shadow ledger are byte-untouched;
`check` gains no criterion. This ledger reports. It decides nothing, triggers
nothing and gates nothing — there is no pass rule here, and none is authorised.

THE RULE, WITH EVERY CONSTANT IN ONE BLOCK BELOW
-----------------------------------------------
Per side, over the club's INCLUDED players (status not `u`/`n`)::

    feat_side = sum over included players of  w_p * u_p

`u_p` is the per-player unavailability probability from A12 (b)'s table and
`w_p` is the minutes share once the club has three matches' worth of minutes on
the clock, the price share until then. Then the tilt::

    d       = k_avail * (feat_home - feat_away)
    q_home  ~ p_home * exp(-d/2)
    q_draw  ~ p_draw
    q_away  ~ p_away * exp(+d/2)

renormalised. The whole content of that map is one identity —
`log(q_home / q_away) = log(p_home / p_away) - d` — the home-vs-away log-odds
of the published marginals move by exactly `d` nats and the draw cell's
log-strength is untouched, moving only through renormalisation. It is not A8's
power transform, and deliberately: recalibration is a symmetric statement about
sharpness, availability is a directional statement about relative strength.

`k_avail = 1.0` is **a PRIOR, not a fit**, and A12 says so in exactly those
words. Its basis is the injury-cost literature — Hägglund et al. 2013, the UEFA
elite-club injury study — which puts one key first-XI absence at low
single-digit percentage points of match win probability; the arithmetic that
places 1.0 in that band is A12 item 3 and is a test in this suite. NOTHING
in-season moves it: no drift trigger, no refit schedule, no monitoring rule
that re-opens it. Unlike A8's annual constant it is not refit, because there is
nothing here to refit. It changes only by a new amendment.

ZERO FITTED PARAMETERS. Every constant this module uses is in the block below
and every one of them is quoted from A12, which is why a test parses the
amendment's own text and compares the two.

ABSTENTION, NOT A BORROWED SNAPSHOT
-----------------------------------
The A11 capture began on 2026-08-27. An issuance whose knowledge clock predates
the first manifest line has no availability view at all, so this arm files an
ABSTENTION row — the fixture, the clocks, `abstained: true`, `reason:
"no_snapshot"` — and never fabricates, backfills or borrows a later snapshot.
MW1 and MW2 are abstentions by construction, and this arm's scored record
starts strictly after its input's archive does. Abstentions are counted and
never scored: any aggregate over this ledger is an aggregate over scored rows
and prints the abstention count beside itself.

TWO CLOCKS, AND THIS ARM BINDS ON OURS
--------------------------------------
Snapshot selection reads `observed_at` — OUR pull clock — and never
`news_added`, the source's own. Not as a filter, not as a tiebreak. So a source
restating its own history cannot move this arm's information set, and a
`news_added` stamped in the future changes nothing. `news_added` is still
carried through the read side, because the GAP between the two clocks is what
the A12 (g) audit will want to see.

THE INPUT IS ON PROBATION
-------------------------
A12 (g): for this arm's first ten scored matchweeks the capture's flagged list
is spot-audited against official club or press publications before that
matchweek's record is treated as meaningful, and until the tenth entry exists in
`reports/epl_avail_audit.md` every summary of this arm's record carries
:data:`PROVISIONAL_SENTENCE`. A language rule in the A8 (e) sense, binding on
every surface this project writes — including this module's own output.

THE BOUNDARY A12 (e) MOVED
--------------------------
A11 made the capture standalone and a test enforced it. A12 is the
preregistration for the SHADOW use only, and it moves the boundary exactly as
far as the rule needs: **this module is the only authorised bridge.** It
imports the capture's read side and the matchboard's scoring side;
`epl.livecycle` imports THIS and still does not import `epl.availability`; the
capture still imports no model module. The covariate gate is untouched and it
stands where A11 left it — this arm reads no `dc_native` input and moves no
published number, so the gate keeps its jurisdiction and gains no ruling.
Entry into the published law would be a gate run plus its own amendment, and
A12 pre-commits neither.

NO CLOCK
--------
A row is a function of the bundle, the archive and the frozen rule. Nothing
here reads a wall clock, so the same inputs produce the same bytes tomorrow. A
test moves the clock and requires the bytes to be identical.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from epl import availability, leaguesim, matchboard, paths, season as season_mod

# ==========================================================================
# 0. THE CONSTANTS BLOCK — A12, quoted. There is no other one.
# ==========================================================================
# A12 "What is pre-stated", item 1, reproduced here field for field:
#
#     k_avail            = 1.0                       (a prior, not a fit)
#     null d-chance      -> u_p = 0.5                (chance 50, the middle rung)
#     i, s               -> u_p = 1.0                (chance ignored)
#     u, n               -> excluded from squad and denominator
#     minutes switchover = 2970                      (= 3 x 990, arithmetic)
#     weight fallback    = now_cost share            (below the switchover)
#     rule_version       = dc-1x2-avail-1
#     schema_version     = epl-avail-shadow-1
#     ledger             = reports/epl_avail_shadow.jsonl
#     audit file         = reports/epl_avail_audit.md
#
# A test parses that block out of the amendment and compares it to what is
# below, so the entry and the code cannot drift apart quietly.

#: The arm's name. The `dc_1x2_` family prefix is the CONTRACT — "a transform of
#: the published `dc_native` 1X2 marginals and nothing else" — and the suffix
#: names the lever, so this ledger and A8's sort as siblings and read as
#: siblings.
ARM = "dc_1x2_avail"

#: The frozen rule, by name. A row filed under a name it was not computed under
#: cannot be read beside the rows that were.
RULE_VERSION = "dc-1x2-avail-1"

#: Carried ON EVERY ROW, not only in this file's prose: a JSONL ledger has no
#: header to put a version in, and A12 (d) requires every row to be checkable
#: without opening anything else.
SCHEMA_VERSION = "epl-avail-shadow-1"

#: **A PRIOR, not a fit.** No repository data was consulted to choose it and
#: none could have been: no fixture had ever been scored under this rule when
#: A12 was written. See the module docstring for the literature basis and A12
#: item 3 for the arithmetic that places it inside the literature's band.
K_AVAIL = 1.0

#: The status the source uses for "available". Contributes nothing.
AVAILABLE_STATUS = "a"

#: The one status on which the chance field binds.
DOUBTFUL_STATUS = "d"

#: `i` (injured) and `s` (suspended): `u_p = 1.0` flat, and the chance figure on
#: those rows is DELIBERATELY IGNORED. A12 states what that costs — some injured
#: players carry a nonzero chance and a flat 1.0 overstates their absence — and
#: keeps it, because the rule's job is to be checkable at zero parameters, not
#: optimal. Sharpening it is a new amendment, not an implementation refinement.
FLAT_UNAVAIL_STATUSES = ("i", "s")

#: `u` (unavailable) and `n` (on loan / left): removed from the squad AND its
#: denominator entirely. Not an absence — a non-member.
EXCLUDED_STATUSES = ("u", "n")

#: The ruled default for a `d` row whose `chance_of_playing_next_round` is null.
#: FPL's own ladder is 25/50/75 and 50 is its middle rung; a null is the source
#: DECLINING to guess, and either extreme rung would import a directional guess
#: the source did not make. Ruled for the edge before the edge exists: zero of
#: the 21 observed `d` rows in the only real snapshot carry null.
NULL_CHANCE = 50.0
NULL_CHANCE_UNAVAIL = 1.0 - NULL_CHANCE / 100.0

#: 2970 = 3 x 990 — three matches of eleven ninety-minute slots. An ARITHMETIC
#: IDENTITY, not a tuned number: minutes share is used the moment it can
#: distinguish rotation from absence, and three matches is the earliest that
#: distinction means anything.
MINUTES_SWITCHOVER = 3 * 990

#: The two weighting branches, recorded per side on every row so the switchover
#: is auditable rather than inferred.
WEIGHT_BASIS_MINUTES = "minutes"
WEIGHT_BASIS_FALLBACK = "now_cost"

#: A12 (d) — in `reports/`, append-only, one JSON object per line, written per
#: matchweek AFTER the results have entered the season ledger and never before.
SHADOW_FILENAME = "epl_avail_shadow.jsonl"
SHADOW_PATH = paths.REPO_ROOT / "reports" / SHADOW_FILENAME

#: A12 (g) — the input's probation record, append-only, one dated entry per
#: audited matchweek.
AUDIT_FILENAME = "epl_avail_audit.md"
AUDIT_PATH = paths.REPO_ROOT / "reports" / AUDIT_FILENAME

#: The only reason an abstention row may carry, because it is the only case
#: A12 authorises one for.
ABSTENTION_REASON = "no_snapshot"

#: A12 (g)'s language rule, binding until the tenth scored matchweek's audit
#: entry exists. Printed beside every summary this module writes.
PROVISIONAL_SENTENCE = ("the input feed is under audit; this record is "
                        "provisional")

#: A12 item 4's two tolerances. The first is arithmetic on the row's own inputs
#: and the archive's own bytes, which is why it sits twelve orders down; the
#: second is the sum invariant, a belt to that brace.
AVAIL_TOLERANCE = 1e-12
SUM_TOLERANCE = 1e-9

#: A12 (d)'s table, in order. `tuple(row) == ROW_FIELDS` is asserted by a test:
#: a field this ledger was not authorised to carry is as much a schema change
#: as a missing one.
ROW_FIELDS = (
    "schema_version", "arm", "fixture_id", "date", "home", "away",
    "season", "cutoff", "observed_by", "run_digest", "source_bundle",
    "probs_raw", "probs_avail", "feat_home", "feat_away",
    "weight_basis_home", "weight_basis_away", "k_avail",
    "snapshot_stamp", "snapshot_sha256", "rule_version",
    "outcome", "rps_raw", "rps_avail", "rps_uniform", "matchweek", "ingest",
)

#: An abstention row: the fixture, the clocks, the provenance, the frozen-rule
#: names — and NONE of the probability, feature or score fields.
ABSTENTION_FIELDS = (
    "schema_version", "arm", "fixture_id", "date", "home", "away",
    "season", "cutoff", "observed_by", "run_digest", "source_bundle",
    "rule_version", "abstained", "reason",
)

#: The two modes A12 (e) and (f) pre-state by name.
MODES = ("verify", "score")


# ==========================================================================
# 1. the refusal family — A12 item 5, by name
# ==========================================================================

class AvailArmError(RuntimeError):
    """Everything this arm refuses on. Printed as STOP, exit 2."""


class SnapshotMissing(AvailArmError):
    """The manifest attests a payload the archive no longer holds."""


class SnapshotDigestMismatch(AvailArmError):
    """The bytes on disk are not the bytes the manifest attested."""


class StatusUnruled(AvailArmError):
    """A status code A12 (b)'s table has no rung for. Named, never skipped."""


class SquadEmpty(AvailArmError):
    """No included players, or a zero denominator on the active branch.

    REFUSED and never a zero feature: a zero says "everyone is fit", which is
    the opposite of "this archive knows nothing about this club".
    """


class AvailMismatch(AvailArmError):
    """A number on a filed row is not what re-deriving it produces."""


class SchemaMismatch(AvailArmError):
    """A row was filed under a rule, a schema or a snapshot that is not its own."""


class RowInadmissible(AvailArmError):
    """The forecast did not precede the kickoff the season knew."""


class RowConflict(AvailArmError):
    """Two disagreeing rows for one `(fixture_id, run_digest)`."""


#: `TeamUnmapped` is the CAPTURE's and this arm lets it through untranslated,
#: because it is the same fact: a club the season does not field, or a spelling
#: the registry does not know. A12 (c) makes it a hard error on the arm's whole
#: run for that snapshot — never a silent skip of one club's players, because a
#: feature computed over nineteen clubs' worth of a twenty-club payload would be
#: a wrong number wearing a right number's name.
TeamUnmapped = availability.TeamUnmapped


# ==========================================================================
# 2. the feature — A12 (b), per player and per side
# ==========================================================================

def unavailability(player: Mapping[str, Any]) -> float | None:
    """`u_p` for one player, or ``None`` when the player is not a squad member.

    A12 (b)'s table, rung for rung. ``None`` is not zero and the caller must not
    treat it as one: an excluded player leaves the denominator too.
    """
    status = player.get("status")
    if status == AVAILABLE_STATUS:
        return 0.0
    if status in FLAT_UNAVAIL_STATUSES:
        return 1.0
    if status in EXCLUDED_STATUSES:
        return None
    if status == DOUBTFUL_STATUS:
        chance = player.get("chance_next")
        chance = NULL_CHANCE if chance is None else float(chance)
        return (100.0 - chance) / 100.0
    raise StatusUnruled(
        f"player {player.get('web_name')!r} (id {player.get('player_id')}) "
        f"carries status {status!r}, which A12 (b)'s table has no rung for. "
        "Refused rather than skipped: a rule that covers only the statuses it "
        "has seen is a rule that narrows silently the week the feed invents "
        "one, and the narrowing would look like a fit squad")


@dataclass(frozen=True)
class SideFeature:
    """One club's expected weighted unavailable fraction, and how it got there.

    `flagged` is every player with `u_p > 0`, which is the list A12 (g)'s audit
    checks against official club publications. It is NOT a ledger field: the
    ledger carries the two features and the two branches, and the flagged list
    is recomputed from the archive whenever the audit wants it.
    """
    feat: float
    weight_basis: str
    n_included: int
    denominator: int
    flagged: tuple[dict, ...]


def side_feature(players: Sequence[Mapping[str, Any]]) -> SideFeature:
    """A12 (b): `feat_side = sum over included players of w_p * u_p`, in [0, 1].

    The branch is decided over the INCLUDED players only, in both the test and
    the denominator: an excluded player must not push a club over the
    switchover, and must not dilute the shares of the players who remain.
    """
    included: list[tuple[Mapping[str, Any], float]] = []
    for player in players:
        u_p = unavailability(player)
        if u_p is None:
            continue
        included.append((player, u_p))
    if not included:
        raise SquadEmpty(
            f"this club has no included players in the snapshot ({len(players)} "
            "row(s), all of them `u` or `n` or none at all). A12 (b) refuses "
            "rather than returning a zero feature, because a zero reads as "
            "'everyone is fit' and means 'we know nothing'")

    total_minutes = sum(int(p["minutes"]) for p, _ in included)
    basis = (WEIGHT_BASIS_MINUTES if total_minutes >= MINUTES_SWITCHOVER
             else WEIGHT_BASIS_FALLBACK)
    weights = [int(p[basis]) for p, _ in included]
    denominator = sum(weights)
    if denominator <= 0:
        raise SquadEmpty(
            f"this club's {basis} denominator is {denominator} over "
            f"{len(included)} included player(s). A12 (b) refuses a zero "
            "denominator rather than dividing by it or calling the feature "
            "zero")

    # SUMMED EXACTLY, not accumulated. A12 states the feature is a number in
    # [0, 1], and left-to-right accumulation of eleven equal shares of one
    # lands on 1.0000000000000002 — outside the interval the ruling names, by
    # an artefact of the order the payload happened to list players in.
    # `math.fsum` is the correctly-rounded sum of the same terms: the literal Σ
    # A12 writes, order-independent, and re-derivable to the bit by the
    # verifier.
    contributions: list[float] = []
    flagged: list[dict] = []
    for (player, u_p), weight in zip(included, weights):
        share = weight / denominator
        contributions.append(share * u_p)
        if u_p > 0.0:
            flagged.append({
                "player_id": player.get("player_id"),
                "web_name": player.get("web_name"),
                "status": player.get("status"),
                "chance_next": player.get("chance_next"),
                "u_p": u_p, "weight": share, "contribution": share * u_p,
                "news": player.get("news"),
                # the SOURCE's clock, carried and never read by the rule (A12
                # (h)); the GAP between the two clocks is what the audit wants.
                "news_added": player.get("news_added"),
            })
    return SideFeature(feat=math.fsum(contributions), weight_basis=basis,
                       n_included=len(included), denominator=denominator,
                       flagged=tuple(flagged))


# ==========================================================================
# 3. the transform — A12 (b), a tilt and nothing else
# ==========================================================================

def _finite(value, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise AvailArmError(f"{label} is {value!r}: the tilt is defined on "
                            "finite probabilities, and a non-finite cell "
                            "renormalises to a non-finite vector")
    return number


def tilt(probs: Mapping[str, float], d: float) -> dict[str, float]:
    """`q_home ~ p_home e^(-d/2)`, `q_draw ~ p_draw`, `q_away ~ p_away e^(+d/2)`.

    Renormalised exactly — the denominator is the sum of the three tilted cells
    and never an assumption that the input summed to one. `d = 0` is the
    identity. The single identity this map contains:
    `log(q_home / q_away) = log(p_home / p_away) - d`.
    """
    shift = _finite(d, "the tilt")
    half = math.exp(-shift / 2.0), 1.0, math.exp(shift / 2.0)
    weighted = {}
    for key, factor in zip(matchboard.OUTCOMES, half):
        if key not in probs:
            raise AvailArmError(f"the vector carries no {key!r} cell; A12 (b) "
                                f"is defined on the ordered triple "
                                f"{matchboard.OUTCOMES}")
        cell = _finite(probs[key], f"probs[{key!r}]")
        if cell < 0.0:
            raise AvailArmError(
                f"probs[{key!r}] is {cell!r}: a negative cell is not a "
                "probability and a tilt of one is not a forecast")
        weighted[key] = cell * factor
    total = sum(weighted.values())
    if not math.isfinite(total) or total <= 0.0:
        raise AvailArmError(f"the tilted cells sum to {total!r}, which is not a "
                            "vector anything can be renormalised against")
    return {key: weighted[key] / total for key in matchboard.OUTCOMES}


def adjust(probs: Mapping[str, float], feat_home: float, feat_away: float, *,
           k_avail: float = K_AVAIL) -> dict[str, float]:
    """The published marginals through the frozen rule: `d = k (f_h - f_a)`."""
    return tilt(probs, _finite(k_avail, "k_avail")
                * (_finite(feat_home, "feat_home")
                   - _finite(feat_away, "feat_away")))


# ==========================================================================
# 4. the snapshot, selected by our clock and nobody else's
# ==========================================================================

def snapshot_for(observed_by, *, raw_dir=None, manifest_path=None,
                 season: str = availability.SEASON,
                 season_root=None) -> availability.AsOfSnapshot | None:
    """The archive's view at an issuance's knowledge clock, or ``None``.

    ``None`` is the ABSTENTION case and is not a refusal: the capture began on
    2026-08-27 and an issuance older than that is a question this archive
    cannot answer. Everything else the read side refuses on is re-raised under
    the names A12 item 5 pre-states, so an operator reading a STOP line sees
    the type the ledger names; :class:`TeamUnmapped` alone passes through
    untranslated, because it is the same fact on both surfaces.
    """
    try:
        return availability.as_of(observed_by, raw_dir=raw_dir,
                                  manifest_path=manifest_path, season=season,
                                  season_root=season_root)
    except availability.NoSnapshotAsOf:
        return None
    except availability.SnapshotMissing as exc:
        raise SnapshotMissing(str(exc)) from exc
    except availability.SnapshotDigestMismatch as exc:
        raise SnapshotDigestMismatch(str(exc)) from exc


def _squad_of(snapshot: availability.AsOfSnapshot, club: str) -> tuple[dict, ...]:
    rows = snapshot.squad(club)
    if not rows:
        raise SquadEmpty(
            f"the snapshot observed at {snapshot.observed_at} carries no "
            f"players for {club!r}. A12 (b) refuses rather than pricing the "
            "club at a zero feature, and A12 (c) makes a club this arm cannot "
            "read a hard error on the whole run rather than a silent skip")
    return rows


# ==========================================================================
# 5. the source — the published matchboard, and nothing else
# ==========================================================================

def board_from(source, *, season_root=None) -> dict:
    """The matchboard document this layer copies ``probs_raw`` out of.

    A directory is an issuance bundle and goes through
    :func:`epl.matchboard.derive`; a file is a matchboard document already
    derived, and must say so by its own schema version. Mirrors
    :func:`epl.recalshadow.board_from` because it is the same question.
    """
    path = Path(source)
    if path.is_dir():
        record = json.loads((path / "issuance.json").read_text())
        board = matchboard.derive(path, record=record, season_root=season_root)
        return {**board, "source_bundle": paths.rel(path)}
    if not path.exists():
        raise AvailArmError(
            f"{path} is neither an issuance bundle nor a matchboard document: "
            "there is nothing at that path. Refused by name rather than dying "
            "on the open, because a mistyped `--directory` is an operator's "
            "error and a traceback is not an answer to one")
    document = json.loads(path.read_text())
    version = document.get("schema_version")
    if version != matchboard.SCHEMA_VERSION:
        raise AvailArmError(
            f"{path} declares schema {version!r} and this layer copies "
            f"`probs_raw` from a {matchboard.SCHEMA_VERSION!r} matchboard. A "
            "document of another shape may carry a `probs` object that means "
            "something else")
    if not document.get("rows"):
        raise AvailArmError(f"{path} carries no rows: there is nothing to copy")
    return document


def _required(board: Mapping[str, Any], field: str) -> Any:
    value = board.get(field)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise AvailArmError(
            f"the source matchboard records no {field!r}, and A12 (d) makes "
            "every row self-contained — a row that cannot name the run it came "
            "from is a row nobody can check without this file's prose")
    return value


def _refuse_a_late_stamp(fixture_id, kickoff, stamps) -> None:
    kick = pd.Timestamp(kickoff)
    for name, stamp in stamps:
        if pd.Timestamp(stamp) > kick:
            raise RowInadmissible(
                f"{fixture_id}: the issuance's {name} ({stamp}) is after the "
                f"kickoff the season knew ({kickoff}); the forecast did not "
                "precede the match, so the row is REFUSED rather than dropped "
                "— an append-only ledger cannot show what it silently omitted")


def _refuse_inadmissible(board: Mapping[str, Any],
                         results: Sequence[Mapping[str, Any]]) -> None:
    """A7 (e), restated by A12 (d) because this is a third surface reading it.

    Runs BEFORE any delegation, so the operator gets the type A12 pre-stated
    rather than a differently-named refusal of the same fact. It runs on
    abstention rows too: a row this arm could not price is still a row whose
    clocks have to be in order before it goes into an append-only file.
    """
    by_id = {row["fixture_id"]: row for row in (board.get("rows") or [])}
    stamps = (("cutoff", pd.Timestamp(board["cutoff"])),
              ("observed_by", pd.Timestamp(board["observed_by"])))
    for result in results:
        row = by_id.get(result.get("fixture_id"))
        if row is None:
            continue            # matchboard.score refuses this, and says why
        _refuse_a_late_stamp(result.get("fixture_id"), row["date"], stamps)


# ==========================================================================
# 6. the rows
# ==========================================================================

def _head(board: Mapping[str, Any], row: Mapping[str, Any]) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "arm": ARM,
        "fixture_id": row["fixture_id"],
        "date": row["date"],
        "home": row["home"],
        "away": row["away"],
        "season": _required(board, "season"),
        "cutoff": str(board["cutoff"]),
        "observed_by": str(board["observed_by"]),
        "run_digest": _required(board, "run_digest"),
        "source_bundle": _required(board, "source_bundle"),
    }


def abstention_row(board: Mapping[str, Any], row: Mapping[str, Any]) -> dict:
    """The row A12 (b) files when no manifest line qualifies.

    It makes the gap AUDITABLE instead of invisible: the ledger shows that the
    arm sat out, and why, in its own append-only record.
    """
    return {**_head(board, row), "rule_version": RULE_VERSION,
            "abstained": True, "reason": ABSTENTION_REASON}


def forecast_rows(board: Mapping[str, Any], *,
                  snapshot: availability.AsOfSnapshot | None,
                  k_avail: float = K_AVAIL) -> list[dict]:
    """The half of every row that exists before a result does.

    ``probs_raw`` is the matchboard's own ``probs`` object, COPIED and never
    re-priced — which is what makes ``rps_raw`` the same double the A7
    scorecard publishes rather than a number that is nearly it.
    """
    out: list[dict] = []
    features: dict[str, SideFeature] = {}
    for row in (board.get("rows") or []):
        if snapshot is None:
            out.append(abstention_row(board, row))
            continue
        for club in (row["home"], row["away"]):
            if club not in features:
                features[club] = side_feature(_squad_of(snapshot, club))
        home, away = features[row["home"]], features[row["away"]]
        probs_raw = dict(row["probs"])
        out.append({
            **_head(board, row),
            "probs_raw": probs_raw,
            "probs_avail": adjust(probs_raw, home.feat, away.feat,
                                  k_avail=k_avail),
            "feat_home": home.feat,
            "feat_away": away.feat,
            "weight_basis_home": home.weight_basis,
            "weight_basis_away": away.weight_basis,
            "k_avail": float(k_avail),
            "snapshot_stamp": snapshot.stamp,
            "snapshot_sha256": snapshot.sha256,
            "rule_version": RULE_VERSION,
        })
    return out


def score(board: Mapping[str, Any], results: Iterable[Mapping[str, Any]], *,
          snapshot: availability.AsOfSnapshot | None,
          ledger=None, season_root=None,
          k_avail: float = K_AVAIL) -> list[dict]:
    """Complete A12 rows for results that have entered the SEASON LEDGER.

    The result half — which fixtures were played, with what scoreline, and
    therefore which outcome — is :func:`epl.matchboard.score`'s answer,
    unmodified. Nothing about "what was played" is decided here, and the
    results file is a REQUEST to score rows the ledger already carries rather
    than a second door a result can come through.

    ``rps_raw`` is recomputed from the row's own ``probs_raw`` and then held to
    the matchboard's own ``rps`` for the same fixture, EXACTLY: the two score
    the same probabilities against the same outcome through the same literal,
    so a difference is a defect in the copy or in the score.

    When ``snapshot`` is ``None`` the batch is a batch of abstentions: the
    fixtures still have to be in the season ledger and the clocks still have to
    be in order, and nothing is scored.
    """
    results = list(results)
    _refuse_inadmissible(board, results)
    scored = matchboard.score(board, results, ledger=ledger,
                              season_root=season_root)
    heads = {row["fixture_id"]: row for row in
             forecast_rows(board, snapshot=snapshot, k_avail=k_avail)}

    out: list[dict] = []
    for row in scored:
        head = heads[row["fixture_id"]]
        if is_abstention(head):
            out.append(head)
            continue
        outcome = row["outcome"]
        rps_raw = matchboard.rps(head["probs_raw"], outcome)
        if rps_raw != row["rps"]:
            raise AvailMismatch(
                f"{row['fixture_id']}: this layer scores the published "
                f"marginals at {rps_raw!r} and the matchboard scores the same "
                f"marginals against the same outcome at {row['rps']!r}. "
                "`probs_raw` is copied and not re-priced, so these are the "
                "SAME double and a difference is a defect in the copy")
        out.append({**head,
                    "outcome": outcome,
                    "rps_raw": rps_raw,
                    "rps_avail": matchboard.rps(head["probs_avail"], outcome),
                    "rps_uniform": matchboard.uniform_rps(outcome),
                    "matchweek": row["matchweek"],
                    "ingest": row["ingest"]})
    return out


def is_abstention(row: Mapping[str, Any]) -> bool:
    return bool(row.get("abstained"))


def tally(rows: Sequence[Mapping[str, Any]]) -> dict:
    """What an aggregate over this ledger may say, with its denominator.

    A12 (d): abstentions are counted and never scored, and any aggregate over
    this ledger must print the abstention count beside itself — an aggregate
    that hides its denominator is the oldest trick in forecasting.
    """
    scored = [row for row in rows if not is_abstention(row)]
    abstained = [row for row in rows if is_abstention(row)]

    def mean(field: str):
        values = [float(row[field]) for row in scored if row.get(field) is not None]
        return sum(values) / len(values) if values else None

    raw, avail = mean("rps_raw"), mean("rps_avail")
    return {
        "n_rows": len(rows), "n_scored": len(scored),
        "n_abstained": len(abstained),
        "mean_rps_raw": raw, "mean_rps_avail": avail,
        "mean_rps_uniform": mean("rps_uniform"),
        # published minus challenger: positive means the tilt scored better.
        "mean_delta": None if raw is None or avail is None else raw - avail,
        "matchweeks": sorted({row.get("matchweek") for row in scored},
                             key=lambda v: (v is None, v)),
    }


# ==========================================================================
# 7. the append-only file — A12 (d)
# ==========================================================================

def shadow_key(row: Mapping[str, Any]) -> tuple[str, str]:
    """A12 (d): one row per ``(fixture_id, run_digest)``.

    ``run_digest`` is the source record's own ``digests["dc_native"]`` — WHICH
    RUN priced the forecast. Two issuances may legitimately both cover one
    fixture and those are two rows; one issuance filed twice is one row.
    """
    return (str(row.get("fixture_id")), str(row.get("run_digest")))


def read_shadow(path=None) -> list[dict]:
    """Every row on file, in the order they were appended. Missing is empty."""
    target = Path(SHADOW_PATH if path is None else path)
    if not target.exists():
        return []
    return [json.loads(line) for line in
            target.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_shadow(path, rows: Sequence[Mapping[str, Any]]) -> dict:
    """Append ONCE per key. Idempotent; a disagreeing re-file REFUSES.

    Nothing is written unless every row passes — the file is opened once, after
    the whole batch has been checked, so a batch with one bad row appends none
    of them and the re-run after the fix is a clean run rather than a partial
    repair.
    """
    target = Path(SHADOW_PATH if path is None else path)
    existing: dict[tuple[str, str], str] = {}
    for row in read_shadow(target):
        existing[shadow_key(row)] = leaguesim.canonical_json(row)

    fresh: list[str] = []
    repeated = 0
    for row in rows:
        key = shadow_key(row)
        text = leaguesim.canonical_json(row)
        already = existing.get(key)
        if already is not None:
            if already == text:
                repeated += 1
                continue
            raise RowConflict(
                f"{key[0]}: this shadow ledger already carries a row for this "
                f"fixture under run digest {key[1]}, and the new row disagrees "
                "with it. The ledger is append-only and a fixture gets one row "
                "per issuance, so the conflicting row is refused rather than "
                f"filed beside the first one.\n  on file: {already}\n  "
                f"offered: {text}")
        existing[key] = text
        fresh.append(text)

    if fresh:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            for text in fresh:
                handle.write(text + "\n")
    return {"appended": len(fresh), "repeated": repeated}


# ==========================================================================
# 8. verification — A12 (f), a standalone re-derivation that can fail
# ==========================================================================

def _manifest_line_named(lines: Sequence[dict], row: Mapping[str, Any]) -> dict:
    stamp = row.get("snapshot_stamp")
    for line in lines:
        if line.get("stamp") == stamp:
            return line
    raise SnapshotMissing(
        f"{row.get('fixture_id')}: this row names snapshot {stamp!r} and the "
        f"tracked manifest holds no line for it ({len(lines)} line(s) on "
        "file). The manifest is the attestation and a row that cites one it "
        "does not carry cannot be re-derived at all")


def check_snapshot(row: Mapping[str, Any], *, lines: Sequence[dict],
                   raw_dir: Path) -> dict:
    """A12 (f) steps 1 and 2 — the snapshot, before anything else."""
    line = _manifest_line_named(lines, row)
    path = Path(raw_dir) / line.get("raw",
                                    availability.raw_name(line["stamp"]))
    if not path.exists():
        raise SnapshotMissing(
            f"{row.get('fixture_id')}: the manifest attests {path.name} and "
            f"the archive does not hold it ({path})")
    import gzip                                     # deferred: only verify reads bytes

    digest = availability.sha256_bytes(gzip.decompress(path.read_bytes()))
    for label, expected in (("the manifest", line["sha256"]),
                            ("this row", row.get("snapshot_sha256"))):
        if digest != expected:
            raise SnapshotDigestMismatch(
                f"{row.get('fixture_id')}: {path.name} hashes to "
                f"{digest[:12]}… and {label} says {str(expected)[:12]}…. The "
                "bytes are the record, so nothing read out of them is what was "
                "attested")

    chosen = availability.select_manifest_line(lines, row["observed_by"])
    if chosen is None or chosen.get("stamp") != line.get("stamp"):
        raise SchemaMismatch(
            f"{row.get('fixture_id')}: this row used snapshot "
            f"{line.get('stamp')!r} and re-deriving the selection at its own "
            f"observed_by ({row['observed_by']}) chooses "
            f"{(chosen or {}).get('stamp')!r}. A12 (b) takes the LATEST line "
            "observed at or before the knowledge clock, so a row that used "
            "another one was priced on an information set the rule does not "
            "authorise")
    return line


def check_row(row: Mapping[str, Any], *, snapshot: availability.AsOfSnapshot,
              k_avail: float = K_AVAIL) -> None:
    """A12 (f) steps 3 to 6 on ONE scored row, in the order the ruling gives.

    Step 3 re-derives the features FROM THE SNAPSHOT'S BYTES rather than from
    the row's own fields, which is the only version of the check that can catch
    a row whose feature was never what the archive said. Step 4 then re-derives
    `probs_avail` from the row's OWN inputs, deliberately before step 5 has
    established that its `k_avail` is the frozen rule's: a row internally
    consistent under some other constant passes 4 and is refused by 5, which is
    the discrimination the ruling is after.
    """
    fixture_id = row.get("fixture_id")

    # --- step 3: the features, re-derived from the bytes
    for side, key in (("home", "feat_home"), ("away", "feat_away")):
        recomputed = side_feature(_squad_of(snapshot, row[side])).feat
        recorded = float(row[key])
        if abs(recorded - recomputed) > AVAIL_TOLERANCE:
            raise AvailMismatch(
                f"{fixture_id}: {key} is {recorded!r} and re-deriving the "
                f"{side} side from {snapshot.raw_path.name} gives "
                f"{recomputed!r}, a difference of "
                f"{abs(recorded - recomputed):.3e} against {AVAIL_TOLERANCE}")
        basis = side_feature(_squad_of(snapshot, row[side])).weight_basis
        if row.get(f"weight_basis_{side}") != basis:
            raise SchemaMismatch(
                f"{fixture_id}: weight_basis_{side} is "
                f"{row.get(f'weight_basis_{side}')!r} and the snapshot's own "
                f"minutes put this club on the {basis!r} branch")

    # --- step 4: probs_avail, from the row's own inputs
    k_row = row.get("k_avail")
    if not isinstance(k_row, (int, float)):
        raise SchemaMismatch(f"{fixture_id}: this row records no numeric "
                             "'k_avail', so its `probs_avail` cannot be "
                             "re-derived at all")
    expected = adjust(row["probs_raw"], float(row["feat_home"]),
                      float(row["feat_away"]), k_avail=float(k_row))
    for key in matchboard.OUTCOMES:
        recorded = float(row["probs_avail"][key])
        if abs(recorded - expected[key]) > AVAIL_TOLERANCE:
            raise AvailMismatch(
                f"{fixture_id}: probs_avail[{key!r}] is {recorded!r} and this "
                f"row's own probs_raw and features at k_avail = {k_row!r} give "
                f"{expected[key]!r}, a difference of "
                f"{abs(recorded - expected[key]):.3e} against "
                f"{AVAIL_TOLERANCE}. This comparison is arithmetic — there is "
                "nothing here for two faithful implementations to differ on")
    total = sum(float(row["probs_avail"][k]) for k in matchboard.OUTCOMES)
    if abs(total - 1.0) > SUM_TOLERANCE:
        raise AvailMismatch(
            f"{fixture_id}: the tilted cells sum to {total!r}, which is "
            f"further than {SUM_TOLERANCE} from one")

    # --- step 5: the frozen-rule fields
    for field, frozen in (("schema_version", SCHEMA_VERSION), ("arm", ARM),
                          ("rule_version", RULE_VERSION)):
        if row.get(field) != frozen:
            raise SchemaMismatch(
                f"{fixture_id}: this row records {field} = {row.get(field)!r} "
                f"and the frozen rule's is {frozen!r}. A row filed under a "
                "name it was not computed under cannot be read beside the rows "
                "that were")
    if float(k_row) != float(k_avail):
        raise SchemaMismatch(
            f"{fixture_id}: this row records k_avail = {k_row!r} and A12's "
            f"prior is {k_avail!r}. The constant is a PRIOR and changes only by "
            "a new amendment, so a row carrying another one was computed under "
            "a rule this repository does not hold")

    # --- step 6: admissibility and the three scores
    _refuse_a_late_stamp(fixture_id, row["date"],
                         (("cutoff", row["cutoff"]),
                          ("observed_by", row["observed_by"])))
    outcome = row.get("outcome")
    for field, probs in (("rps_raw", row["probs_raw"]),
                         ("rps_avail", row["probs_avail"])):
        recomputed = matchboard.rps(probs, outcome)
        if float(row[field]) != recomputed:
            raise AvailMismatch(
                f"{fixture_id}: {field} is {row[field]!r} and scoring this "
                f"row's own probabilities against {outcome!r} by the project's "
                f"literal gives {recomputed!r}")
    uniform = matchboard.uniform_rps(outcome)
    if float(row["rps_uniform"]) != uniform:
        raise AvailMismatch(
            f"{fixture_id}: rps_uniform is {row['rps_uniform']!r} and a "
            f"{outcome!r} result scores {uniform!r} against (1/3, 1/3, 1/3) — "
            "exactly 5/18 for a home or away result and 1/9 for a draw")


def check_abstention(row: Mapping[str, Any]) -> None:
    """A12 (f) step 6: an abstention row carries no score field, and says why."""
    fixture_id = row.get("fixture_id")
    # SORTED, not ordered: the file is `leaguesim.canonical_json`, which sorts
    # keys so the bytes never depend on the order a dict happened to be built
    # in. The ORDER is asserted where it exists, on the row `score()` returns.
    if sorted(row) != sorted(ABSTENTION_FIELDS):
        raise SchemaMismatch(
            f"{fixture_id}: an abstention row carries "
            f"{sorted(ABSTENTION_FIELDS)} and this one carries {sorted(row)}. "
            "The unauthorised field(s) "
            f"{sorted(set(row) - set(ABSTENTION_FIELDS))} would be a score, a "
            "probability or a feature on a row that pre-states it has none, "
            f"and the missing one(s) {sorted(set(ABSTENTION_FIELDS) - set(row))} "
            "are what makes an abstention auditable")
    if row.get("reason") != ABSTENTION_REASON:
        raise SchemaMismatch(
            f"{fixture_id}: this abstention records reason "
            f"{row.get('reason')!r} and A12 (b) authorises exactly one, "
            f"{ABSTENTION_REASON!r}")
    for field, frozen in (("schema_version", SCHEMA_VERSION), ("arm", ARM),
                          ("rule_version", RULE_VERSION)):
        if row.get(field) != frozen:
            raise SchemaMismatch(
                f"{fixture_id}: this abstention records {field} = "
                f"{row.get(field)!r} and the frozen rule's is {frozen!r}")
    _refuse_a_late_stamp(fixture_id, row["date"],
                         (("cutoff", row["cutoff"]),
                          ("observed_by", row["observed_by"])))


def verify(path=None, *, raw_dir=None, manifest_path=None,
           season: str = availability.SEASON, season_root=None,
           k_avail: float = K_AVAIL) -> dict:
    """A12 (f), in order, stopping at the first refusal.

    CI has no `data/`, so this command refuses there — loudly and correctly.
    That is its job. A verification that quietly declines to verify is worse
    than one that was never run, because it prints something.
    """
    target = Path(SHADOW_PATH if path is None else path)
    rows = read_shadow(target)
    lines = availability.read_manifest(
        manifest_path if manifest_path is not None
        else availability.default_manifest_path(season, season_root))
    raw = Path(raw_dir) if raw_dir is not None else availability.RAW_DIR

    seen: dict[tuple[str, str], int] = {}
    views: dict[str, availability.AsOfSnapshot] = {}
    for index, row in enumerate(rows):
        key = shadow_key(row)
        if key in seen:
            raise RowConflict(
                f"{key[0]}: this shadow ledger carries two rows for this "
                f"fixture under run digest {key[1]} (lines {seen[key] + 1} and "
                f"{index + 1}). A12 (d) gives a fixture one row per issuance, "
                "and a file holding two says nothing a reader can use")
        seen[key] = index
        if is_abstention(row):
            check_abstention(row)
            continue
        check_snapshot(row, lines=lines, raw_dir=raw)
        stamp = str(row["observed_by"])
        if stamp not in views:
            view = snapshot_for(stamp, raw_dir=raw, manifest_path=manifest_path,
                                season=season, season_root=season_root)
            if view is None:                                # pragma: no cover
                raise SchemaMismatch(
                    f"{row.get('fixture_id')}: step 2 accepted this row's "
                    "snapshot and re-selecting it returned nothing")
            views[stamp] = view
        check_row(row, snapshot=views[stamp], k_avail=k_avail)

    return {"ledger": str(target), "exists": target.exists(),
            "arm": ARM, "rule_version": RULE_VERSION,
            "schema_version": SCHEMA_VERSION, "k_avail": float(k_avail),
            "n_snapshots": len(lines), **tally(rows)}


# ==========================================================================
# 9. what a command needs: a whole scoring run
# ==========================================================================

def read_results(path) -> list[dict]:
    """A results file — a REQUEST to score rows the season ledger carries."""
    target = Path(path)
    if not target.exists():
        raise AvailArmError(
            f"{target} does not exist. The results file is the REQUEST to "
            "score, and a missing one is a mistyped `--results` rather than a "
            "run with nothing to do")
    return [json.loads(line) for line in
            target.read_text(encoding="utf-8").splitlines() if line.strip()]


def score_bundle(source, results_file, *, ledger_path=None, season_root=None,
                 raw_dir=None, manifest_path=None,
                 season: str = availability.SEASON, avail_season_root=None,
                 k_avail: float = K_AVAIL) -> dict:
    """Derive, score and append in one pass, refusing before anything is written.

    The whole batch is scored first — which is where the season ledger, the
    admissibility ordering, the snapshot digest and the raw-score identity all
    refuse — and only then is the file opened.
    """
    board = board_from(source, season_root=season_root)
    snapshot = snapshot_for(board["observed_by"], raw_dir=raw_dir,
                            manifest_path=manifest_path, season=season,
                            season_root=avail_season_root)
    rows = score(board, read_results(results_file), snapshot=snapshot,
                 season_root=season_root, k_avail=k_avail)
    target = Path(SHADOW_PATH if ledger_path is None else ledger_path)
    counts = append_shadow(target, rows)
    return {"board": board, "rows": rows, "ledger": str(target),
            "snapshot": snapshot, **counts, **tally(rows)}


# ==========================================================================
# 10. the command — A12 (e), (f)
# ==========================================================================

#: Everything a refusal may be. `AvailArmError` is A12's own base; the others
#: are the surfaces this command delegates to, and their refusals are refusals
#: of this command just the same — a `MatchboardError` printed as a traceback
#: would be exactly the defect the STOP convention exists to stop.
REFUSALS = (AvailArmError, availability.AvailabilityError,
            matchboard.MatchboardError, season_mod.SeasonError)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m epl.availarm",
        description="the dc_1x2_avail shadow ledger: score it, and verify it")
    sub = parser.add_subparsers(dest="mode", required=True)

    for name, help_text in (("verify", "re-derive every row from the archive"),
                            ("score", "derive rows from a bundle and score them")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--ledger", default=None,
                       help=f"the shadow ledger (default {SHADOW_PATH}). "
                            "Append-only and idempotent by "
                            "(fixture_id, run_digest).")
        p.add_argument("--raw-dir", default=None,
                       help=f"the archived snapshots (default "
                            f"{availability.RAW_DIR}).")
        p.add_argument("--manifest", default=None,
                       help="the tracked availability manifest (default the "
                            "season's own).")

    s = sub.choices["score"]
    s.add_argument("--directory", required=True,
                   help="an issuance bundle, or a matchboard document already "
                        "derived from one. `probs_raw` is copied from its "
                        "published marginals and never re-priced.")
    s.add_argument("--results", required=True,
                   help="a JSONL of results (fixture_id, home_goals, "
                        "away_goals, matchweek, ingest). Every row must ALREADY "
                        "be in the season's results ledger, which is the source "
                        "of truth for what was played.")
    s.add_argument("--season-root", default=None,
                   help=f"where the season ledger lives (default "
                        f"{season_mod.SEASON_ROOT}).")
    return parser


def _summary(report: Mapping[str, Any]) -> list[str]:
    """The count beside the denominator, and the language rule beneath both."""
    lines = [
        f"[avail] {ARM} / {RULE_VERSION} / {SCHEMA_VERSION} / "
        f"k_avail {K_AVAIL!r}",
        f"[avail] {report['n_scored']} scored row(s), "
        f"{report['n_abstained']} abstention(s)"
        + (f", matchweek(s) {report['matchweeks']}" if report["matchweeks"]
           else ""),
    ]
    if report["mean_rps_avail"] is not None:
        lines.append(
            f"[avail] mean RPS published {report['mean_rps_raw']!r}  "
            f"tilted {report['mean_rps_avail']!r}  "
            f"difference {report['mean_delta']!r}")
    # A12 (g), binding until the tenth scored matchweek's audit entry exists.
    lines.append(f"[avail] {PROVISIONAL_SENTENCE}")
    return lines


def _verify(args) -> int:
    report = verify(args.ledger, raw_dir=args.raw_dir,
                    manifest_path=args.manifest)
    for line in _summary(report):
        print(line)
    print(f"[avail] {report['ledger']}: {report['n_rows']} row(s) re-derived "
          f"against {report['n_snapshots']} attested snapshot(s)")
    # A12 (d) + (g): this ledger reports. It decides nothing and triggers
    # nothing, so nothing is printed here that a reader could take for a
    # ruling on the arm.
    return 0


def _score(args) -> int:
    result = score_bundle(args.directory, args.results,
                          ledger_path=args.ledger,
                          season_root=args.season_root,
                          raw_dir=args.raw_dir, manifest_path=args.manifest)
    where = ("no snapshot qualified" if result["snapshot"] is None
             else f"snapshot {result['snapshot'].stamp}")
    print(f"[avail] {len(result['rows'])} row(s) from {args.directory} "
          f"({where})")
    print(f"[avail] appended {result['appended']} to {result['ledger']}"
          + (f"; {result['repeated']} already filed, unchanged"
             if result["repeated"] else ""))
    for line in _summary(result):
        print(line)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.mode == "verify":
            return _verify(args)
        if args.mode == "score":
            return _score(args)
    except REFUSALS as exc:
        print(f"STOP: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 1                                                # pragma: no cover


__all__ = [
    "ARM", "RULE_VERSION", "SCHEMA_VERSION", "K_AVAIL", "AVAILABLE_STATUS",
    "DOUBTFUL_STATUS", "FLAT_UNAVAIL_STATUSES", "EXCLUDED_STATUSES",
    "NULL_CHANCE", "NULL_CHANCE_UNAVAIL", "MINUTES_SWITCHOVER",
    "WEIGHT_BASIS_MINUTES", "WEIGHT_BASIS_FALLBACK", "SHADOW_FILENAME",
    "SHADOW_PATH", "AUDIT_FILENAME", "AUDIT_PATH", "ABSTENTION_REASON",
    "PROVISIONAL_SENTENCE", "AVAIL_TOLERANCE", "SUM_TOLERANCE", "ROW_FIELDS",
    "ABSTENTION_FIELDS", "MODES", "REFUSALS",
    "AvailArmError", "SnapshotMissing", "SnapshotDigestMismatch",
    "StatusUnruled", "SquadEmpty", "AvailMismatch", "SchemaMismatch",
    "RowInadmissible", "RowConflict", "TeamUnmapped",
    "SideFeature", "unavailability", "side_feature", "tilt", "adjust",
    "snapshot_for", "board_from", "abstention_row", "forecast_rows", "score",
    "is_abstention", "tally", "shadow_key", "read_shadow", "append_shadow",
    "check_snapshot", "check_row", "check_abstention", "verify",
    "read_results", "score_bundle", "main",
]


if __name__ == "__main__":                                  # pragma: no cover
    sys.exit(main())
