"""Config-gated dynamics: decay, cadence, break widening, home term, congestion.

WHAT THIS MODULE IS FOR. The first run (``reports/epl_walkforward.md``) put the
frozen Dixon-Coles model 0.00117 RPS below walk-forward Elo with a 95% CI of
[-0.00281, +0.00047] — a precise null, not a win. The four candidate levers that
survive "is this legally clean and derivable from data we already hold" are
implemented here. Each is a GATE. Every gate is OFF by default, and with every
gate off this module is required to be INERT: the config it produces must be
byte-identical to ``epl.freeze.frozen_wcmodel_config()``, the cutoff schedule
identical to ``epl.walkforward``'s, and the forecast bit-identical to
``epl.dcfit.fit_epl`` + ``Posterior.predict_1x2``. That is not a comment; it is
:mod:`epl.tests.test_improve`, including one end-to-end comparison of real
fitted probabilities with ``np.array_equal``.

WHY THE INERTNESS CONTRACT IS THE LOAD-BEARING PART. A gate that changes
behaviour when it is off is a silent confound: every subsequent A/B measures the
lever PLUS the gate's own footprint, and the two can never be separated
afterwards because there is no run that isolates them. The frozen configuration
is the control arm of every comparison this package will make from here, so it
has to be reachable exactly, not approximately.

THE WINDOW RULE, RESTATED BECAUSE THIS MODULE IS WHERE IT WOULD BE BROKEN.
Tuning, exploration and adoption happen on 2014/15-2018/19 and nowhere else.
2019/20-2024/25 has been scored ONCE; any further scoring there is a SECOND LOOK
and :func:`run_walk` will not touch it without ``second_look=True`` recorded in
the ledger. 2025/26 is a fresh holdout for the DC-vs-Elo question (it needs no
odds) and is reachable only with ``holdout=True``, which is meant to be used
once, at the end, after everything else is frozen.

THE FOUR GATES
--------------
**I1a — decay half-life** (``decay_half_life_days``). ``config.windows.
decay_half_life_days`` is 365, a number chosen for international football where
a team plays ~10 matches a year. An EPL club plays 38. At 365 days a match from
last season still carries ~0.5 weight and a match from three seasons ago ~0.13,
so the fit is averaging over squads that no longer exist. This is the largest
known lever in the literature and it is a one-number change threaded through the
config deep-copy — ``wcmodel.data.features.build`` turns it into
``decay_weight``, ``to_match_panel`` renames that to ``weight``, and
``build_model`` uses it as the per-match likelihood weight. Nothing is patched.

**I1b — refit cadence** (``refit_cadence_weeks``). Run 1 refit every matchweek
because the preregistration fixed that cadence. It is a dial, not a law, and the
opposite direction is also interesting: a coarser cadence is cheaper but staler,
a finer one is impossible (the matchweek IS the round). Exposed so the cost of
staleness can be measured rather than assumed. Values > 1 are recorded in the
ledger as off-protocol, exactly as ``epl.walkforward`` does.

(c) A genuine random-walk state on attack/defence was NOT attempted. It cannot
be reached through the config — it is a different likelihood — so it would have
to be a separate model fitted outside ``wcmodel``, and a separate model is not a
gated variant of this one. Deliberately left undone rather than half-done; see
``note`` in the structured record.

**I2 — season-break and transfer-window variance inflation**
(``break_widen_strength``, ``break_widen_half_life_matches``,
``break_widen_january``). The honest way to represent squad turnover without
claiming to know what changed: widen the predictive when the squad plausibly
changed, and let the widening decay as matches accumulate and the new squad
becomes observable. The package already owns the mechanism — ``wcmodel.model.
widening.inflate_predictive``, mechanism (c), mean-preserving in expected goals
and strictly entropy-increasing — but its existing TRIGGER (``count_volatility_
arm``) was measured INERT on EPL at league K: no club trips the few-games or
volatility arms, so mechanism (c) fires only for cold-start clubs. This supplies
an EPL-specific trigger instead: matches since the club's most recent squad
break, where a break is the season opening (summer window) and optionally the
first fixture on or after 1 February (the January window's close).

The inflation is applied ONCE per fixture at strength ``1 - (1 - s_base)(1 -
s_break)``, which is EXACTLY equal to applying the base provisional widening and
then the break widening in sequence. That identity is not an approximation and
not a convenience: mixing toward the max-entropy product preserves the marginal
means, so the max-entropy target is unchanged by the first mix and the two mixes
compose linearly. It is proved on real grids in the tests.

**I3 — a faster-adapting home term** (``home_term_blend``,
``home_term_half_life_days``). ``home_adv`` is refitted at every cutoff, so it
already drifts — but it drifts at the decay half-life, which is the same
half-life that governs everything else. Home advantage in the EPL did not drift
in 2020/21; it stepped. Behind closed doors the home-win rate fell to 38% and it
rebounded to 43% the following season. A single half-life cannot represent a
step in one parameter and continuity in the others.

What is implemented is a SHIFT, not a refit: the league-wide home term is
estimated twice off the same pre-cutoff matches — once at the model's own decay
half-life (``h_slow``, what the fit already knows) and once at a shorter one
(``h_fast``) — and the posterior's ``home_adv`` draws are shifted by ``blend *
(h_fast - h_slow)``. The estimator is the moment identity the model's own linear
predictor implies: with ``log E[home goals] = mu + att_h - def_a + home_adv`` and
``log E[away goals] = mu + att_a - def_h``, the attack/defence terms cancel over
a balanced schedule and the difference of the log weighted mean goals estimates
``home_adv``. At ``blend = 0`` the shift is identically zero and no wrapper is
built at all. The spread of the posterior is untouched — this moves the centre
only, which is the honest claim: it says "the league's home edge is currently
this much different from what the long window thinks", not "I am more certain".

**I4 — congestion / rest differential** (``congestion``). Days since each side's
previous match, derived entirely from fixture dates already in the archive.
``wcmodel`` already threads this: ``features.build`` emits a per-team
``rest_days`` column computed from prior fixtures only, ``to_match_panel``
carries it onto the match row as ``rest_days`` / ``rest_days__away``, and
``scoreline._build_covariates`` fits ONE standardization on the pre-cutoff
training rows and applies it to both sides. So the gate is a config change —
``model.covariates.enabled = ["rest_days"]`` — plus the predict-time value,
which comes from ``wcmodel.model.rest.predict_rest_days`` under the same
``< cutoff`` filter. The rest DIFFERENTIAL is represented implicitly and
correctly: one shared beta multiplies the home side's standardized rest on the
home rate and the away side's on the away rate, so only the difference moves the
1X2 split. Evidence on average rest effects is weak; this is a candidate that
has to earn adoption on the tuning window, and the prior (``beta_scale`` 0.25)
is the shipped one.

I5 — MANAGERIAL CHANGE: FEASIBILITY, INVESTIGATED AND DROPPED
------------------------------------------------------------
A lawful, timestamped, CC0 source DOES exist. Wikidata models a club's head
coach as ``P286`` statements qualified with ``P580`` (start time) and ``P582``
(end time); the public SPARQL endpoint answers it without scraping and the data
is CC0. Measured on 2026-08-14, restricted to clubs currently carrying
``P118 = Q9448`` (Premier League) and spells starting on or after 2014-06-01:
20 clubs, 116 spells, of which 114 are DAY precision, 1 month, 1 year. Manchester
United's spell list resolves correctly to the day, including caretakers.

It is dropped anyway, for two reasons that are worth writing down so the decision
does not have to be re-derived.

1. **The snapshot is CURRENT_ONLY in this repo's own taxonomy.** Today's
   statement set reflects today's knowledge, including retroactive edits and
   corrections. Pricing a 2019 fixture from it is not look-ahead in CONTENT — who
   managed a club on a date was public on that date — but it is unprovable in
   PROVENANCE, and this package's whole claim is that its provenance is
   checkable. Making it point-in-time means reconstructing each statement from
   the item's revision timestamps (MediaWiki ``prop=revisions``, or the dump
   stream), which is an ingestion project, not a feature.
2. **The defensible model of it is already implemented.** The evidence is that
   the post-sacking bounce is regression to the mean, so the honest response to a
   managerial change is variance inflation — which is I2, generically, triggered
   by an observable the archive already contains. A manager trigger would add a
   sparser second trigger to the same mechanism. The marginal value over I2 is
   small and it costs a CURRENT_ONLY dependency.

The query is recorded in :data:`I5_WIKIDATA_QUERY` so a future run can reproduce
the counts rather than trust this paragraph.

NO BETTING. Nothing here reads or produces a price.
"""

from __future__ import annotations

import argparse
import copy
import json
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from epl import anchor as anchor_mod
from epl import baseline, dcfit, fit as epl_fit, freeze, paths
from epl import score as score_mod, walkforward, windows
from epl.schema import sort_for_walk_forward

__all__ = [
    "Improvements", "OFF", "wcmodel_config", "cadence_weeks", "BreakClock",
    "home_term", "home_term_shift", "RestSchedule", "Forecaster",
    "fit_improved", "run_walk", "score_walk", "IMPROVE_DIR",
    "I5_WIKIDATA_QUERY", "I5_FEASIBILITY",
]

#: Ledgers and scored results for gated variants. Under ``data/``, gitignored
#: like everything else the probe writes.
IMPROVE_DIR = paths.FIT_DIR / "improve"

#: The SPARQL that produced the I5 counts in the module docstring. Recorded, not
#: run: this package makes no network call.
I5_WIKIDATA_QUERY = (
    "SELECT ?prec (COUNT(*) AS ?n) WHERE { "
    "?club wdt:P118 wd:Q9448 . ?club p:P286 ?st . "
    "?st pq:P580 ?s . ?st pqv:P580 ?sv . ?sv wikibase:timePrecision ?prec . "
    'FILTER(?s >= "2014-06-01T00:00:00Z"^^xsd:dateTime) } GROUP BY ?prec'
)

#: What that query returned on 2026-08-14, and the verdict. See the docstring.
I5_FEASIBILITY: dict[str, Any] = {
    "source": "Wikidata P286 (head coach) + P580/P582 qualifiers",
    "licence": "CC0",
    "access": "public SPARQL endpoint (query.wikidata.org) — an API, not scraping",
    "measured_on": "2026-08-14",
    "clubs": 20,
    "spells_since_2014_06_01": 116,
    "date_precision": {"day": 114, "month": 1, "year": 1},
    "coverage_caveat": (
        "wdt:P118 = Q9448 selects clubs CURRENTLY in the league; the 13 further "
        "clubs this archive holds (relegated since) need a QID mapping"),
    "verdict": "FEASIBLE, NOT ADOPTED",
    "why_not": [
        "today's statement set is CURRENT_ONLY: point-in-time use needs the "
        "item's revision timestamps, which is an ingestion project",
        "the defensible modelling is variance inflation, which I2 already "
        "implements from an observable the archive contains",
    ],
}


# ==========================================================================
# 1. the gates
# ==========================================================================
@dataclass(frozen=True)
class Improvements:
    """Which dynamics are switched on, and how hard.

    Every field's default is the OFF value, and OFF means "reproduce the frozen
    configuration exactly" — not "reproduce it closely". ``None`` is used where
    the shipped configuration already carries a number (I1a, I1b) so that OFF is
    literally "do not write to this key" rather than "write the same number
    back", which would be indistinguishable in the output but not in the code.
    """

    # --- I1a: recency ------------------------------------------------------
    decay_half_life_days: float | None = None
    # --- I1b: refit cadence ------------------------------------------------
    refit_cadence_weeks: int | None = None
    # --- I2: season-break / transfer-window widening -----------------------
    break_widen_strength: float = 0.0
    break_widen_half_life_matches: float = 3.0
    break_widen_january: bool = False
    # --- I3: faster-adapting home term -------------------------------------
    home_term_blend: float = 0.0
    home_term_half_life_days: float = 120.0
    # --- I4: congestion ----------------------------------------------------
    congestion: bool = False

    def __post_init__(self) -> None:
        if self.decay_half_life_days is not None and self.decay_half_life_days <= 0:
            raise ValueError("decay_half_life_days must be > 0 days")
        if self.refit_cadence_weeks is not None and self.refit_cadence_weeks < 1:
            raise ValueError("refit_cadence_weeks must be >= 1 matchweek")
        if not 0.0 <= self.break_widen_strength <= 1.0:
            raise ValueError(
                "break_widen_strength is a mixing weight and must lie in "
                f"[0, 1]; got {self.break_widen_strength!r}")
        if self.break_widen_half_life_matches <= 0:
            raise ValueError("break_widen_half_life_matches must be > 0")
        if not 0.0 <= self.home_term_blend <= 1.0:
            raise ValueError(
                "home_term_blend is a blend weight and must lie in [0, 1]; "
                f"got {self.home_term_blend!r}")
        if self.home_term_half_life_days <= 0:
            raise ValueError("home_term_half_life_days must be > 0 days")

    # --- which gates are live ---------------------------------------------
    @property
    def i1a(self) -> bool:
        return self.decay_half_life_days is not None

    @property
    def i1b(self) -> bool:
        return self.refit_cadence_weeks is not None

    @property
    def i2(self) -> bool:
        return self.break_widen_strength > 0.0

    @property
    def i3(self) -> bool:
        return self.home_term_blend > 0.0

    @property
    def i4(self) -> bool:
        return bool(self.congestion)

    @property
    def enabled(self) -> tuple[str, ...]:
        return tuple(g for g in ("i1a", "i1b", "i2", "i3", "i4")
                     if getattr(self, g))

    def is_off(self) -> bool:
        """True iff this is the frozen configuration, byte for byte."""
        return not self.enabled

    def touches_the_fit(self) -> bool:
        """True iff a gate changes the panel, the design or the likelihood.

        The remaining gates (I2, I3) act only at predict time, so a variant that
        touches none of these can reuse a fit. Not an optimisation this module
        performs — a fact the runner records, so that a reader can see which
        variants are and are not comparable at fixed posterior.
        """
        return self.i1a or self.i4

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Improvements":
        return cls(**{k: v for k, v in d.items()
                      if k in cls.__dataclass_fields__})

    @property
    def spec(self) -> str:
        """Short token identifying this variant. ``"off"`` when nothing is on.

        Goes into the ledger and into ``cfg["epl_improvements"]``. It is
        deliberately NOT written into ``cfg["elo"]`` or ``cfg["windows"]``:
        those two blocks are hashed into ``features._build_cache_key``, so a
        token there would invalidate the panel cache for gates that provably do
        not change the panel. I1a lives in ``windows`` on its own merit and
        flips the key correctly, which is the behaviour we want.
        """
        if self.is_off():
            return "off"
        bits = []
        if self.i1a:
            bits.append(f"decay={self.decay_half_life_days:g}d")
        if self.i1b:
            bits.append(f"cadence={self.refit_cadence_weeks:d}w")
        if self.i2:
            bits.append(f"break={self.break_widen_strength:g}"
                        f"@hl{self.break_widen_half_life_matches:g}"
                        + ("+jan" if self.break_widen_january else ""))
        if self.i3:
            bits.append(f"home={self.home_term_blend:g}"
                        f"@hl{self.home_term_half_life_days:g}d")
        if self.i4:
            bits.append("congestion")
        return "epl.improve/" + "/".join(bits)

    def label(self) -> str:
        """Filesystem-safe variant name for a ledger file."""
        return (self.spec.replace("epl.improve/", "")
                .replace("/", "_").replace("=", "").replace("@", "")
                .replace("+", "_").replace(".", "p"))


#: The frozen configuration. Every comparison's control arm.
OFF = Improvements()

#: The covariates ``epl.dcfit`` will fit on EPL data. I4's gate writes this list
#: into the config; the guard in ``dcfit.fit_epl`` refuses anything else, because
#: travel/altitude/acclimatisation are World Cup features with no EPL analogue.
CONGESTION_COVARIATES: tuple[str, ...] = ("rest_days",)


# ==========================================================================
# 2. the config (I1a, I4)
# ==========================================================================
def wcmodel_config(imp: Improvements = OFF, base: dict | None = None,
                   path: Path | str | None = None) -> dict:
    """The frozen wcmodel config with this variant's gates written in.

    OFF RETURNS THE FROZEN CONFIG UNCHANGED — the same dict content, not a
    similar one. The function returns early on ``imp.is_off()`` rather than
    falling through a chain of no-op writes, because a no-op write is only a
    no-op until someone edits it.
    """
    cfg = freeze.frozen_wcmodel_config(base=base, path=path)
    if imp.is_off():
        return cfg
    if imp.i1a:
        cfg["windows"]["decay_half_life_days"] = float(imp.decay_half_life_days)
    if imp.i4:
        enabled = list(cfg["model"]["covariates"].get("enabled") or [])
        for name in CONGESTION_COVARIATES:
            if name not in enabled:
                enabled.append(name)
        cfg["model"]["covariates"]["enabled"] = enabled
    cfg["epl_improvements"] = imp.as_dict() | {"spec": imp.spec}
    return cfg


def cadence_weeks(imp: Improvements = OFF) -> int:
    """I1b. The preregistered cadence unless the gate says otherwise."""
    if not imp.i1b:
        return walkforward.CADENCE_WEEKS
    return int(imp.refit_cadence_weeks)


# ==========================================================================
# 3. I2 — the break clock
# ==========================================================================
class BreakClock:
    """How many league matches a club has played since its squad last changed.

    A BREAK is a date on which the squad plausibly changed and the model cannot
    know how. Two kinds are recognised, both read off the fixture list and
    neither requiring a transfer feed:

    * the season's first fixture — every club's summer window has closed or is
      closing, and the model's information about the new squad is zero;
    * optionally, the first fixture on or after 1 February — the day after the
      English January window shuts, so the squad that will finish the season is
      final and, again, unobserved.

    A club's clock reads ``k`` = the number of its own played league matches in
    ``[most recent break <= cutoff, cutoff)``. A promoted club reads 0 at its
    season opener for the same reason an established club does, and a club that
    was in the second tier last season reads 0 too — correctly, since the archive
    holds nothing about it either way.

    POINT-IN-TIME. Every date consumed is strictly before the cutoff. The break
    dates themselves come from the FIXTURE LIST, which is published before a ball
    is kicked and carries no result; the counting uses only matches with
    ``date < cutoff``.
    """

    def __init__(self, played: pd.DataFrame, january: bool = True):
        played = sort_for_walk_forward(played)
        dates = pd.to_datetime(played["date"]).dt.normalize()
        self.january = bool(january)
        self._epochs = self._break_dates(played, dates, january)
        self._club_dates: dict[str, np.ndarray] = {}
        long = pd.concat([
            pd.DataFrame({"club": played["home_key"].astype(str).to_numpy(),
                          "date": dates.to_numpy()}),
            pd.DataFrame({"club": played["away_key"].astype(str).to_numpy(),
                          "date": dates.to_numpy()})])
        for club, grp in long.groupby("club", sort=True):
            self._club_dates[str(club)] = np.sort(
                grp["date"].to_numpy(dtype="datetime64[ns]"))

    @staticmethod
    def _break_dates(played: pd.DataFrame, dates: pd.Series,
                     january: bool) -> np.ndarray:
        out: list[pd.Timestamp] = []
        for _, grp in played.assign(_d=dates).groupby("season", sort=True):
            d = grp["_d"]
            first = pd.Timestamp(d.min())
            out.append(first)
            if not january:
                continue
            # The 1 February inside this season's span. Derived from the data
            # (not from parsing the season string) so a season that starts in a
            # different month still resolves.
            year = first.year + 1 if first.month >= 6 else first.year
            feb = pd.Timestamp(year=year, month=2, day=1)
            after = d.loc[d >= feb]
            if not after.empty:
                out.append(pd.Timestamp(after.min()))
        return np.sort(np.array([np.datetime64(t) for t in out],
                                dtype="datetime64[ns]"))

    def matches_since_break(self, club: str, cutoff) -> int:
        """``k`` for one club at one cutoff. Unknown club -> 0 (maximal widening)."""
        cut = np.datetime64(pd.Timestamp(cutoff).normalize())
        pos = int(np.searchsorted(self._epochs, cut, side="right")) - 1
        if pos < 0:                       # before the archive's first season
            epoch = self._epochs[0] if self._epochs.size else cut
        else:
            epoch = self._epochs[pos]
        d = self._club_dates.get(str(club))
        if d is None:
            return 0
        return int(np.searchsorted(d, cut, side="left")
                   - np.searchsorted(d, epoch, side="left"))

    def strength(self, club: str, cutoff, imp: Improvements) -> float:
        """The inflation weight for one club: ``s0 * 2 ** (-k / half_life)``.

        Exponential in MATCHES, not in days, because what resolves the
        uncertainty is observing the new squad play, and a fixture backlog
        resolves it faster than the calendar does.
        """
        if not imp.i2:
            return 0.0
        k = self.matches_since_break(club, cutoff)
        s = float(imp.break_widen_strength) * 2.0 ** (
            -k / float(imp.break_widen_half_life_matches))
        return 0.0 if s < 1e-9 else min(s, 1.0)


def combine_widening(*strengths: float) -> float:
    """Strength of ONE mix equivalent to applying these mixes in sequence.

    ``inflate_predictive`` mixes the grid toward the product of its own
    max-entropy marginals, and it preserves the marginal MEANS. The max-entropy
    pmf on a bounded integer support is determined by its mean alone, so the
    target of the second mix is IDENTICAL to the target of the first, and

        (1 - s2)[(1 - s1) g + s1 M] + s2 M = (1 - s1)(1 - s2) g
                                             + [1 - (1 - s1)(1 - s2)] M

    exactly. Applying one mix at the combined strength is therefore not an
    approximation of applying two — it is the same grid, to floating point. That
    is what lets I2 stack on the existing provisional widening without either
    double-counting or suppressing it.
    """
    keep = 1.0
    for s in strengths:
        if not 0.0 <= s <= 1.0:
            raise ValueError(f"a mixing weight must lie in [0, 1]; got {s!r}")
        keep *= (1.0 - s)
    return 1.0 - keep


# ==========================================================================
# 4. I3 — the home term
# ==========================================================================
def home_term(played: pd.DataFrame, cutoff, half_life_days: float) -> float:
    """League-wide home advantage on the model's log-rate scale, one half-life.

    The moment estimator the model's own linear predictor implies. With
    ``log E[home goals] = mu + att_h - def_a + home_adv`` and ``log E[away
    goals] = mu + att_a - def_h``, summing over a schedule in which every club
    plays home and away equally often makes the attack and defence terms cancel,
    leaving ``home_adv`` as the difference of the logs of the two weighted mean
    goal counts. It is a moment estimator, not a fit: it ignores the
    schedule imbalance that exists mid-season and it is exact only in the
    balanced limit. That is acceptable HERE because it is never used as a level
    — only as the DIFFERENCE between two half-lives, where the imbalance and the
    Jensen gap are common to both terms and cancel to first order.

    Uses strictly pre-cutoff played matches. Returns ``nan`` if either side has
    no weighted goals, which the caller treats as "no shift".
    """
    cut = pd.Timestamp(cutoff).normalize()
    d = pd.to_datetime(played["date"]).dt.normalize()
    m = played.loc[(d < cut).to_numpy()]
    if m.empty:
        return float("nan")
    age = (cut - pd.to_datetime(m["date"]).dt.normalize()).dt.days.to_numpy(float)
    w = 0.5 ** (age / float(half_life_days))
    tot = w.sum()
    if tot <= 0:
        return float("nan")
    mh = float((w * m["fthg"].to_numpy(float)).sum() / tot)
    ma = float((w * m["ftag"].to_numpy(float)).sum() / tot)
    if not (mh > 0 and ma > 0):
        return float("nan")
    return float(np.log(mh) - np.log(ma))


def home_term_shift(played: pd.DataFrame, cutoff, imp: Improvements,
                    model_half_life_days: float) -> float:
    """How far to move ``home_adv``: ``blend * (fast - slow)``. 0.0 when off.

    ``model_half_life_days`` must be the half-life the FIT actually used (i.e.
    after I1a), because ``h_slow`` is meant to be an estimate of what the
    posterior already believes. Passing the shipped 365 while the fit ran at 180
    would double-count the recency the fit had already applied.
    """
    if not imp.i3:
        return 0.0
    fast = home_term(played, cutoff, imp.home_term_half_life_days)
    slow = home_term(played, cutoff, model_half_life_days)
    if not (np.isfinite(fast) and np.isfinite(slow)):
        return 0.0
    return float(imp.home_term_blend) * float(fast - slow)


class HomeShiftedPosterior(dcfit.ColdStartPosterior):
    """A fitted posterior whose ``home_adv`` draws are translated by a constant.

    Every other read — ``att``, ``def``, ``mu``, ``rho``, the cold-start
    extensions — is the base posterior's, unchanged and un-copied. The shift
    moves the CENTRE of the home term and leaves its spread alone, which is the
    only claim the estimator supports.
    """

    def __init__(self, base: dcfit.ColdStartPosterior, shift: float):
        self.__dict__.update(base.__dict__)
        self._home_shift = float(shift)

    def _post(self, name):
        arr = super()._post(name)
        if name == "home_adv" and self._home_shift:
            return np.asarray(arr, dtype=float) + self._home_shift
        return arr


# ==========================================================================
# 5. I4 — congestion at predict time
# ==========================================================================
class RestSchedule:
    """Per-fixture ``rest_days``, from ``wcmodel.model.rest``, unmodified.

    The fit side needs nothing: ``features.build`` already emits ``rest_days``
    per team from prior fixtures only (12,000 EPL team-rows at a mid-archive
    cutoff, 1.3% missing — the archive's first appearances). This class supplies
    the PREDICT side, which is the half ``wcmodel`` exposes as a helper rather
    than a pipeline stage.

    THE STALENESS, NAMED. ``predict_rest_days`` filters ``date < cutoff`` as
    well as ``date < fixture``, and a weekly refit block's cutoff is the block's
    opening day. So a Wednesday fixture priced by Saturday's fit measures rest
    from before Saturday, ignoring a Saturday match the club may since have
    played. That is STALE, never leaky — the model sees strictly less — and it is
    the same day-resolution asymmetry ``epl.anchor.Anchor.state`` documents for
    the strength anchor. Making it fresher would mean refitting inside the block,
    which is a cadence question (I1b), not a covariate question.
    """

    def __init__(self, played: pd.DataFrame):
        d = pd.to_datetime(played["date"]).dt.normalize()
        self._long = pd.concat([
            pd.DataFrame({"team": played["home_key"].astype(str).to_numpy(),
                          "date": d.to_numpy()}),
            pd.DataFrame({"team": played["away_key"].astype(str).to_numpy(),
                          "date": d.to_numpy()})], ignore_index=True)

    def covariates(self, home: str, away: str, fixture_date, cutoff,
                   ) -> dict[str, float]:
        """``{"rest_days": home_value, "rest_days__away": away_value}``.

        The key names are ``wcmodel``'s per-team side wiring
        (``panel._PER_TEAM_COVS`` + ``posterior._covariate_offsets``): the bare
        name lands on the home rate, ``__away`` on the away rate. A NaN — a club
        with no prior match in the archive — standardises to a zero contribution
        through the persisted transform, so it is passed rather than dropped.
        """
        from wcmodel.model.rest import predict_rest_days

        return {
            "rest_days": predict_rest_days(str(home), fixture_date, cutoff,
                                           self._long),
            "rest_days__away": predict_rest_days(str(away), fixture_date,
                                                 cutoff, self._long),
        }


# ==========================================================================
# 6. the forecaster
# ==========================================================================
class Forecaster:
    """One fitted posterior plus this variant's predict-time gates.

    THE OFF PATH IS THE BARE CALL. With every predict-time gate off,
    :meth:`predict_1x2` evaluates to ``post.predict_1x2(home, away,
    neutral=False, covariates=None)``, which is the identical call
    ``epl.walkforward._one_cutoff`` makes today (``covariates`` defaults to
    ``None``). No branch, no wrapper, no re-implementation of the production
    grid — the widening path, the DC per-draw correction and the renormalisation
    all stay inside ``wcmodel.model.draw_api``.
    """

    def __init__(self, post: dcfit.ColdStartPosterior, imp: Improvements,
                 cutoff, clock: BreakClock | None = None,
                 rest: RestSchedule | None = None):
        self.post = post
        self.imp = imp
        self.cutoff = pd.Timestamp(cutoff).normalize()
        self.clock = clock
        self.rest = rest
        if imp.i2:
            if clock is None:
                raise ValueError("I2 is on but no BreakClock was supplied")
            if post._cfg["widening"]["mechanism"] != "c":
                raise ValueError(
                    "I2 inflates the PREDICTIVE, which is mechanism (c); the "
                    f"config says {post._cfg['widening']['mechanism']!r}, so "
                    "the inflation would never fire and the gate would be a "
                    "silent no-op")
            # Detach this posterior's view of the model config so the per-fixture
            # strength swap below cannot reach the frozen dict every other fit
            # is reading. `_cfg` is read-only everywhere in wcmodel, so replacing
            # the attribute on an object this Forecaster exclusively owns is
            # contained.
            self.post._cfg = copy.deepcopy(post._cfg)
            self._base_strength = float(self.post._cfg["widening"]["strength"])
        if imp.i4 and rest is None:
            raise ValueError("I4 is on but no RestSchedule was supplied")

    # --- the gates, per fixture -------------------------------------------
    def _covariates(self, home: str, away: str, date) -> dict | None:
        if not self.imp.i4:
            return None
        if date is None:
            raise ValueError(
                "I4 needs the fixture's DATE to measure rest against; passing "
                "None would silently standardise to a zero contribution and "
                "the gate would look inert instead of broken")
        return self.rest.covariates(home, away, date, self.cutoff)

    def break_strength(self, home: str, away: str) -> float:
        """I2's inflation for this fixture: the WIDER of the two clubs' clocks.

        Widening acts on the joint scoreline grid, not on one team's rate, so
        there is no per-side version of it. Taking the maximum says the fixture
        is as uncertain as its least-known squad, which is the direction that
        does not quietly cancel one club's turnover against the other's.
        """
        if not self.imp.i2:
            return 0.0
        return max(self.clock.strength(home, self.cutoff, self.imp),
                   self.clock.strength(away, self.cutoff, self.imp))

    def predict_1x2(self, home: str, away: str, date=None) -> dict[str, float]:
        cov = self._covariates(home, away, date)
        s_break = self.break_strength(home, away)
        if s_break <= 0.0:
            return self.post.predict_1x2(str(home), str(away), neutral=False,
                                         covariates=cov)
        # ONE inflation at the combined strength — see combine_widening for why
        # that is exactly, not approximately, the two mixes in sequence.
        base_prov = (home in self.post.provisional_teams
                     or away in self.post.provisional_teams)
        total = combine_widening(self._base_strength if base_prov else 0.0,
                                 s_break)
        saved_prov = self.post.provisional_teams
        saved_strength = self.post._cfg["widening"]["strength"]
        self.post.provisional_teams = {str(home), str(away)}
        self.post._cfg["widening"]["strength"] = total
        try:
            return self.post.predict_1x2(str(home), str(away), neutral=False,
                                         covariates=cov)
        finally:
            self.post.provisional_teams = saved_prov
            self.post._cfg["widening"]["strength"] = saved_strength


def fit_improved(cutoff, store, anchor: anchor_mod.Anchor, cfg: dict,
                 imp: Improvements = OFF, matches: pd.DataFrame | None = None,
                 clock: BreakClock | None = None,
                 rest: RestSchedule | None = None,
                 feature_cache_dir=None,
                 ) -> tuple[Forecaster, dcfit.EplFit]:
    """``epl.dcfit.fit_epl`` plus this variant's predict-time wrappers.

    The FIT is not re-implemented. I1a and I4 have already been written into
    ``cfg`` by :func:`wcmodel_config` and reach the model through the panel and
    the covariate design; I2 and I3 act after the fit. So the only thing this
    function adds to ``fit_epl`` is the wrapping, and with the gates off it adds
    nothing at all.
    """
    if imp.i3 and matches is None:
        raise ValueError(
            "I3 estimates the league's home term from the pre-cutoff match "
            "frame; pass matches= so it has one to read")
    post, res = dcfit.fit_epl(cutoff, store, anchor, cfg, matches=matches,
                              feature_cache_dir=feature_cache_dir)
    if imp.i3:
        shift = home_term_shift(matches, cutoff, imp,
                                float(cfg["windows"]["decay_half_life_days"]))
        post = HomeShiftedPosterior(post, shift)
    return Forecaster(post, imp, cutoff, clock=clock, rest=rest), res


# ==========================================================================
# 7. the exploration runner — window-guarded
# ==========================================================================
_WINDOWS = {
    "tune": windows.TUNE_SCORED,
    "confirm": windows.SCORE_SEASONS,
    "holdout": windows.EXCLUDED_SEASONS,
}


def _resolve_seasons(window: str, second_look: bool, holdout: bool,
                     ) -> tuple[str, ...]:
    """The one place a variant is allowed to choose which seasons it sees.

    Structural, not advisory. ``tune`` needs no argument; ``confirm`` needs
    ``second_look=True`` because 2019/20-2024/25 has already been scored once and
    every further look multiplies; ``holdout`` needs ``holdout=True`` because
    2025/26 is meant to be touched exactly once, at the end.
    """
    if window not in _WINDOWS:
        raise ValueError(f"window must be one of {sorted(_WINDOWS)}; got {window!r}")
    if window == "confirm" and not second_look:
        raise ValueError(
            "2019/20-2024/25 was scored once, before any of these gates "
            "existed. Scoring it again is a SECOND LOOK and multiplies: pass "
            "second_look=True so the ledger records it as one.")
    if window == "holdout" and not holdout:
        raise ValueError(
            "2025/26 is the fresh holdout for the DC-vs-Elo question. Pass "
            "holdout=True only when everything else is frozen, and never tune "
            "on what comes back.")
    return tuple(_WINDOWS[window])


def run_walk(imp: Improvements = OFF, window: str = "tune",
             second_look: bool = False, holdout: bool = False,
             matches: pd.DataFrame | None = None,
             ledger_path: Path | str | None = None, resume: bool = True,
             limit: int | None = None, verbose: bool = True,
             fast_panel: bool = True) -> dict[str, Any]:
    """Walk one variant across one window, one ledger row per cutoff.

    Same shape as ``epl.walkforward.run_walk`` — append-only, resumable, one fit
    per cutoff, every fixture priced — with the variant and its window recorded
    on every row so two ledgers can never be silently pooled.
    """
    seasons = _resolve_seasons(window, second_look, holdout)
    matches = baseline.load_matches() if matches is None else matches
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    frame = played.loc[played["season"].isin(seasons)]
    if window == "tune":
        windows.assert_tuning_only(frame["season"], "the exploration frame")

    cfg = wcmodel_config(imp)
    cadence = cadence_weeks(imp)
    cuts = walkforward.matchweek_cutoffs(played, score_seasons=seasons,
                                         cadence=cadence,
                                         allow_excluded=(window == "holdout"))
    if limit:
        cuts = cuts[:limit]

    anchor = anchor_mod.Anchor(played, freeze.frozen_elo_config())
    store = epl_fit.build_store(played)
    clock = BreakClock(played, january=imp.break_widen_january) if imp.i2 else None
    rest = RestSchedule(played) if imp.i4 else None

    IMPROVE_DIR.mkdir(parents=True, exist_ok=True)
    ledger_path = Path(ledger_path or
                       IMPROVE_DIR / f"{window}_{imp.label()}.jsonl")
    done: set[str] = set()
    if resume and ledger_path.exists():
        done = {json.loads(l)["key"]
                for l in ledger_path.read_text().splitlines() if l.strip()}
    todo = [c for c in cuts if c.key not in done]
    if verbose:
        print(f"[improve] spec={imp.spec} window={window} "
              f"{len(cuts)} cutoffs at cadence {cadence}w, {len(todo)} to run",
              flush=True)

    home = played["home_key"].astype(str).to_numpy()
    away = played["away_key"].astype(str).to_numpy()
    dates = pd.to_datetime(played["date"]).to_numpy()
    started = time.time()
    ctx = epl_fit.config_read_once(cfg) if fast_panel else walkforward._null_context()
    with ctx:
        for i, cut in enumerate(todo, 1):
            t0 = time.perf_counter()
            fc, res = fit_improved(cut.cutoff, store, anchor, cfg, imp,
                                   matches=played, clock=clock, rest=rest,
                                   feature_cache_dir=paths.FIT_CACHE_DIR)
            probs, unpriceable = [], []
            for mid, h, a, dt in zip(cut.match_ids, home[cut.rows],
                                     away[cut.rows], dates[cut.rows]):
                if h not in fc.post._idx or a not in fc.post._idx:
                    probs.append([float("nan")] * 3)
                    unpriceable.append({"match_id": mid, "home": h, "away": a})
                    continue
                p = fc.predict_1x2(h, a, date=pd.Timestamp(dt))
                probs.append([float(p[k]) for k in score_mod.OUTCOMES])
            arr = np.asarray(probs, dtype=float)
            row = {
                "key": cut.key, "season": cut.season,
                "matchweek": cut.matchweek, "cutoff": str(cut.cutoff.date()),
                "spec": imp.spec, "improvements": imp.as_dict(),
                "window": window, "second_look": bool(window == "confirm"),
                "cadence_weeks": int(cadence),
                "off_protocol": bool(cadence != walkforward.CADENCE_WEEKS),
                "n_fixtures": len(cut.match_ids),
                "match_ids": list(cut.match_ids),
                "probs": [[round(v, 8) for v in r] for r in arr.tolist()],
                "seconds": round(time.perf_counter() - t0, 2),
                "n_training_matches": res.n_training_matches,
                "n_teams": res.n_teams,
                "cold_start_teams": res.cold_start_teams,
                "provisional_teams": res.provisional_teams,
                "home_shift": float(getattr(fc.post, "_home_shift", 0.0)),
                "unpriceable": unpriceable,
                "health": walkforward._health(fc.post, cfg),
            }
            with ledger_path.open("a") as fh:
                fh.write(json.dumps(row, default=str) + "\n")
            if verbose:
                el = time.time() - started
                print(f"[improve] {i}/{len(todo)} {cut.key} {row['seconds']}s "
                      f"(elapsed {el/60:.1f}m, eta {el/i*(len(todo)-i)/60:.1f}m)",
                      flush=True)
    return {"spec": imp.spec, "window": window, "n_cutoffs": len(cuts),
            "n_run": len(todo), "seconds": round(time.time() - started, 1),
            "ledger": str(ledger_path)}


def score_walk(ledger_path: Path | str, matches: pd.DataFrame | None = None,
               n_boot: int = 10_000) -> dict[str, Any]:
    """Score one variant's ledger against walk-forward Elo on the same fixtures.

    NO ODDS. The DC-versus-Elo question needs none, and requiring them would
    silently drop the 2025/26 holdout's uncovered tail and re-import the
    selection effect ``epl.windows`` excluded it for. The market column belongs
    to the confirmatory run and stays there.
    """
    rows = [json.loads(l) for l in Path(ledger_path).read_text().splitlines()
            if l.strip()]
    if not rows:
        raise ValueError(f"{ledger_path} is empty")
    specs = sorted({r["spec"] for r in rows})
    if len(specs) != 1:
        raise ValueError(f"{ledger_path} mixes variants {specs}")
    seasons = sorted({r["season"] for r in rows})

    matches = baseline.load_matches() if matches is None else matches
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    ev = baseline.evaluate(played, freeze.frozen_elo_config(), seasons,
                           require_odds=False)
    frame = ev.frame.copy()

    dc = {str(m): [float(v) for v in p]
          for r in rows for m, p in zip(r["match_ids"], r["probs"])}
    ids = frame["match_id"].astype(str).to_numpy()
    arr = np.array([dc.get(m, [np.nan] * 3) for m in ids], dtype=float)
    keep = np.isfinite(arr).all(axis=1)
    frame, arr = frame.loc[keep].reset_index(drop=True), arr[keep]
    y = frame["y"].to_numpy()

    dc_rps = score_mod.rps(arr, y)
    elo_rps = frame["elo_rps"].to_numpy()
    d = dc_rps - elo_rps
    lo, hi, nb = score_mod.block_bootstrap_ci(d, frame["block"].to_numpy(),
                                              n_boot=n_boot)
    return {
        "spec": specs[0], "seasons": seasons, "n": int(len(frame)),
        "n_dropped": int((~keep).sum()),
        "dc_rps": float(dc_rps.mean()), "elo_rps": float(elo_rps.mean()),
        "dc_minus_elo": float(d.mean()), "paired_sd": float(d.std(ddof=1)),
        "ci95_week": [lo, hi], "n_blocks": int(nb),
        "dc_log_loss": float(score_mod.log_loss(arr, y).mean()),
        "per_season": (frame.assign(dc_rps=dc_rps)
                       .groupby("season")
                       .agg(n=("match_id", "size"), dc=("dc_rps", "mean"),
                            elo=("elo_rps", "mean"))
                       .assign(dc_minus_elo=lambda t: t["dc"] - t["elo"])
                       .reset_index().to_dict(orient="records")),
    }


# ==========================================================================
# 8. CLI
# ==========================================================================
def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--walk", action="store_true")
    ap.add_argument("--score", type=str, default=None, metavar="LEDGER")
    ap.add_argument("--window", default="tune", choices=sorted(_WINDOWS))
    ap.add_argument("--second-look", action="store_true")
    ap.add_argument("--holdout", action="store_true")
    ap.add_argument("--decay", type=float, default=None)
    ap.add_argument("--cadence", type=int, default=None)
    ap.add_argument("--break-widen", type=float, default=0.0)
    ap.add_argument("--break-half-life", type=float, default=3.0)
    ap.add_argument("--break-january", action="store_true")
    ap.add_argument("--home-blend", type=float, default=0.0)
    ap.add_argument("--home-half-life", type=float, default=120.0)
    ap.add_argument("--congestion", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--n-boot", type=int, default=10_000)
    args = ap.parse_args()

    imp = Improvements(
        decay_half_life_days=args.decay, refit_cadence_weeks=args.cadence,
        break_widen_strength=args.break_widen,
        break_widen_half_life_matches=args.break_half_life,
        break_widen_january=args.break_january,
        home_term_blend=args.home_blend,
        home_term_half_life_days=args.home_half_life,
        congestion=args.congestion)

    if args.walk:
        print(json.dumps(run_walk(imp, window=args.window,
                                  second_look=args.second_look,
                                  holdout=args.holdout, limit=args.limit),
                         indent=2))
    if args.score:
        out = score_walk(args.score, n_boot=args.n_boot)
        out.pop("per_season", None)
        print(json.dumps(out, indent=2))
    if not (args.walk or args.score):
        print(json.dumps({"spec": imp.spec, "enabled": list(imp.enabled),
                          "i5": I5_FEASIBILITY}, indent=2))


if __name__ == "__main__":
    _cli()
