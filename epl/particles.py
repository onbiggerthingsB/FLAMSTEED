"""The effective posterior, frozen into arrays the simulator can sample from.

One rule governs this module: **the simulator must sample from the law the
forecast publishes.** Not a re-derivation of it, not a close approximation of it
— the same per-fixture marginal, to floating-point. Everything below exists to
make that true and to make it checkable.

WHY THIS MODULE EXISTS AT ALL (plan v2 D11, Codex P0-2)
------------------------------------------------------
``wcmodel.sim.scoreline.RateBook`` — the World Cup sampler — reads
``posterior.idata.posterior`` directly. :class:`epl.dcfit.ColdStartPosterior`
keeps a promoted club's ``att``/``def`` draws OUTSIDE ``idata`` (they are prior
draws at the fitted hyperparameters, not fitted rows) and serves them through the
``_post`` accessor. So ``RateBook`` sees 20 rows where the posterior has 21, and
the promoted club — the one club a league-table simulator most needs to price —
raises ``IndexError``. :meth:`ParticleBook.from_posterior` reads every parameter
through ``_post``, which is the accessor ``draw_api.per_draw_rates`` itself uses,
so the cold-start rows come along.

THE FOUR LEGS, AND WHAT EACH IS PINNED TO
-----------------------------------------
1. **Rates** (:meth:`ParticleBook.rates`) — ``exp(mu + home_adv + att[h] -
   def[a] + 0.0)`` and ``exp(mu + 0.0 + att[a] - def[h] + 0.0)``, the plain-home
   branch of ``draw_api.per_draw_rates`` written out in the same order with the
   same terms. Pinned BITWISE against it.
2. **Grids** (:func:`fixture_grids`) — the per-particle Dixon-Coles grid:
   Poisson outer product, ``dc_tau_np`` on the four cells at that particle's own
   ``rho``, clip (the DC quasi-likelihood can drive a cell negative), renormalise
   per particle. Identical arithmetic to ``draw_api.mean_grid_over_draws``'s
   loop, evaluated across all S particles at once because the scalar path is a
   measured bottleneck (plan v2 D13). Pinned to 1e-12 against the loop.
3. **Truncation** — ``PRODUCTION_MAX_GOALS`` (10), the frozen production
   truncation, NOT the WC sim's ``sim.max_goals`` (12). A simulator that
   truncated differently would sample a different law from the one the forecast
   issues. The mass the truncation excludes is MEASURED per particle, so "the
   tail is negligible" is a checked claim rather than an assumption. Under D11
   v1.0.1 (owner ruling 2026-08-19, ``reports/epl_sim_amendments.md`` A1) the
   measurement is REPORTED rather than fatal up to :data:`FLAG_EXCLUDED_MASS`
   — production truncates at the same 10 goals and discards the same tail
   silently, so a simulator that refused would be quieter about the tail than
   the forecast it prices, not louder — and the fixture fails closed only above
   :data:`HARD_STOP_EXCLUDED_MASS`, which catches a mis-scaled rate.
4. **Widening** (:func:`widening_component`, the ``q_cdf`` leg) — production
   issues, for a fixture involving a provisional club, ``(1-a)*gbar + a*q``
   where ``q`` is the max-entropy product grid matched to ``gbar``'s marginal
   means (``wcmodel.model.widening.inflate_predictive``, a = 0.5 frozen). A
   sampler that ignored this would price provisional fixtures more confidently
   than the published forecast does. So the sim carries a per-fixture Bernoulli
   branch: with probability ``a`` the scoreline comes from ``q``, otherwise from
   that sim's own particle grid. Averaged over particles and over the coin, the
   marginal is EXACTLY ``(1-a)*gbar + a*q`` — the production grid (plan v2 D12).
   ``q`` is recovered from ``inflate_predictive``'s own output as
   ``(out - (1-a)*gbar)/a`` rather than re-implemented, so there is no second
   copy of the max-entropy solve to drift.

The Bernoulli is drawn PER FIXTURE, independently. That is the construction that
reproduces the per-fixture marginal exactly and adds no correlation assumption;
drawing it once per club per season is a defensible alternative and is a
deferred sensitivity (plan v1.1 R5), not a thing to improvise here.

WHAT THIS MODULE REFUSES
------------------------
A bivariate-Poisson posterior, an enabled covariate, or a persisted covariate
transform: all raise :class:`UnsupportedPosterior`. v1 prices the frozen
Dixon-Coles stack with no covariates, and a silent fallback to a different map
is exactly the drift ``draw_api`` was built to close.

WHAT IS SAMPLED, AND HOW
------------------------
:func:`fixture_cdfs` returns flat cumulative distributions — ``cdf[s]`` over the
121 scorelines for particle ``s``, plus ``q_cdf`` when the fixture is
provisional. The engine consumes them by inverse-CDF against uniforms, which is
why the RNG contract can be "only ``Generator.random()`` is drawn" (plan v2 D14)
and why a played fixture can own a stream it never touches.

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_particles.py -q
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.stats import poisson

# --- READ-ONLY imports from the attested package ---------------------------
from wcmodel.model.draw_api import PRODUCTION_MAX_GOALS
from wcmodel.model.likelihoods import dc_tau_np
from wcmodel.model.widening import inflate_predictive

__all__ = [
    "FLAG_EXCLUDED_MASS", "HARD_STOP_EXCLUDED_MASS", "LARGE_PARTICLE_MASS",
    "MAX_EXCLUDED_MASS", "ParticleError", "UnsupportedPosterior",
    "ExcludedMassTooLarge", "DegenerateGrid", "ParticleBook", "FixtureCDF",
    "excluded_mass_stats", "fixture_grids", "mean_grid", "widening_component",
    "fixture_cdfs",
]

#: The particle-mean tail mass above which a fixture is FLAGGED (plan v2 D11 as
#: amended by D11 v1.0.1, owner ruling 2026-08-19; the entry is
#: ``reports/epl_sim_amendments.md`` A1, recorded before this guard was changed).
#: At Premier League rates the real number is ~1e-7; a fixture near this
#: threshold is one whose rates are not league-shaped, and at the 2026-08-21
#: opener exactly one of 380 was — a promoted club with zero archive rows,
#: priced from cold-start prior draws.
#:
#: The number is UNCHANGED at its preregistered 5e-3; what changed is what
#: happens at it. A flagged fixture is recorded in the run's envelope and listed
#: by id in ``limitations.md``, and the run completes, because
#: ``draw_api.production_grid`` truncates at the same 10 goals and discards the
#: same tail without saying so. The flag makes the simulator MORE visible about
#: that tail than production is.
FLAG_EXCLUDED_MASS = 5e-3

#: The particle-mean tail mass above which the fixture still fails CLOSED with
#: :class:`ExcludedMassTooLarge`. Pre-stated in amendment A1, before any run
#: under the amended rule existed, as 4x the worst fixture observed at the
#: opener (0.005365). It still catches what the original guard was built for: a
#: mis-scaled rate — ``lambda`` around 20 excludes about half the mass and
#: trips this by more than an order of magnitude.
HARD_STOP_EXCLUDED_MASS = 2e-2

#: A particle counts as a "large" contributor to the flag record above this.
#: Reported per flagged fixture because the mean is a poor description of a
#: distribution where ten draws of a thousand carry 43% of it.
LARGE_PARTICLE_MASS = 0.01

#: The pre-amendment name for the 5e-3 threshold, kept as an alias so the
#: number has one definition. It is the FLAG threshold, not a hard stop.
MAX_EXCLUDED_MASS = FLAG_EXCLUDED_MASS

#: The posterior parameters the book freezes, in the order the content hash
#: consumes them. ``def`` is spelled ``defe`` on the book (``def`` is a keyword).
_PARAMS: tuple[tuple[str, str], ...] = (
    ("att", "att"), ("def", "defe"), ("mu", "mu"), ("home_adv", "home_adv"),
    ("rho", "rho"), ("sigma_att", "sigma_att"), ("sigma_def", "sigma_def"),
)

#: Which of those are per-team ``(T, S)`` rather than per-particle ``(S,)``.
_TEAM_PARAMS = frozenset({"att", "def"})


class ParticleError(RuntimeError):
    """Anything this module refuses to do."""


class UnsupportedPosterior(ParticleError):
    """The posterior is outside the v1 scope (likelihood or covariates)."""


class ExcludedMassTooLarge(ParticleError):
    """The truncation excludes more than :data:`HARD_STOP_EXCLUDED_MASS`.

    Not raised between :data:`FLAG_EXCLUDED_MASS` and this ceiling: that band is
    recorded and reported instead (D11 v1.0.1).
    """


class DegenerateGrid(ParticleError):
    """A particle's grid is non-finite or has no mass — an unusable forecast.

    Mirrors ``draw_api._renorm_draw``'s fail-loud contract: a diverged fit can
    overflow ``exp(...)`` so the truncated Poisson pmf underflows to zeros, and
    ``0/0`` would otherwise smuggle a NaN grid into the sampler.
    """


# ==========================================================================
# the book
# ==========================================================================
@dataclass(eq=False)
class ParticleBook:
    """The effective posterior as plain arrays: S joint particles, T clubs.

    One column ``s`` of ``att``/``defe`` together with ``mu[s]``,
    ``home_adv[s]`` and ``rho[s]`` is ONE joint draw from the (approximate)
    posterior — the object plan v2 D1 assigns to one simulated season, so that
    parameter uncertainty and its cross-fixture correlation reach the title and
    relegation tails instead of averaging out fixture by fixture.

    ``sigma_att``/``sigma_def`` are carried because they are what the cold-start
    prior draws were generated from (``epl.dcfit._prior_draws``); they are part
    of the bundle's provenance even though the rate leg does not read them.
    """

    teams: tuple[str, ...]
    idx: dict[str, int]
    att: np.ndarray           #: (T, S)
    defe: np.ndarray          #: (T, S)
    mu: np.ndarray            #: (S,)
    home_adv: np.ndarray      #: (S,)
    rho: np.ndarray           #: (S,)
    sigma_att: np.ndarray     #: (S,)
    sigma_def: np.ndarray     #: (S,)
    provisional: frozenset[str]
    cold_start: frozenset[str]
    likelihood: str
    alpha: float
    max_goals: int
    cfg_hash: str
    schema_version: str = field(default="epl-particlebook-1")

    # ---- construction ----------------------------------------------------
    @classmethod
    def from_posterior(cls, post, *, max_goals: int = PRODUCTION_MAX_GOALS
                       ) -> "ParticleBook":
        """Freeze a fitted posterior, cold-start rows included (plan v2 D11).

        Every parameter is read through ``post._post(name)`` — the accessor
        ``draw_api.per_draw_rates`` uses — so a :class:`epl.dcfit.ColdStartPosterior`
        yields ``(n_fitted + n_promoted, S)`` for ``att``/``def`` and the promoted
        club is priceable. Reading ``idata`` directly is the P0-2 defect.
        """
        likelihood = getattr(post, "likelihood", None)
        if likelihood != "dixon_coles":
            raise UnsupportedPosterior(
                f"likelihood {likelihood!r}: this simulator prices the frozen "
                "Dixon-Coles stack only. A bivariate-Poisson posterior needs a "
                "different per-particle grid (the proper joint pmf, not tau on "
                "four cells) and is out of v1 scope — fail closed rather than "
                "price a different model than the one the forecast issues.")

        cfg = post._cfg                      # NB: already the `model` block
        enabled = list((cfg.get("covariates") or {}).get("enabled") or ())
        transforms = sorted(getattr(post, "covariate_transforms", None) or {})
        if enabled or transforms:
            raise UnsupportedPosterior(
                f"covariates enabled={enabled} transforms={transforms}: the sim "
                "prices fixtures with no per-fixture covariate values, so a "
                "covariate-carrying posterior would be sampled at a DIFFERENT "
                "linear predictor than the one it was fitted with. The frozen "
                "config enables none; fail closed rather than drop the terms.")

        arrays: dict[str, np.ndarray] = {}
        for name, _attr in _PARAMS:
            try:
                arr = np.ascontiguousarray(post._post(name), dtype=float)
            except KeyError as exc:                       # pragma: no cover
                raise UnsupportedPosterior(
                    f"posterior carries no {name!r}; the Dixon-Coles fit this "
                    "package runs always does") from exc
            arrays[name] = arr

        teams = tuple(str(t) for t in post.teams)
        n_particles = int(arrays["mu"].shape[-1])
        for name, arr in arrays.items():
            want = (len(teams), n_particles) if name in _TEAM_PARAMS else (n_particles,)
            if arr.shape != want:
                raise UnsupportedPosterior(
                    f"{name!r} has shape {arr.shape}, expected {want} — the "
                    "effective posterior does not line up with the team list")
        if not np.all(np.isfinite(np.concatenate([a.ravel() for a in arrays.values()]))):
            raise UnsupportedPosterior(
                "the effective posterior carries non-finite draws; a diverged "
                "fit is not something to simulate from")

        widening = cfg["widening"]
        # Mirror `draw_api.finalize_grid`: mechanism (c) is the ONLY predict-time
        # widening. Under (a) the widening already happened in the likelihood, so
        # the predictive grid is not inflated and the mixture branch is off.
        alpha = (min(float(widening["strength"]), 0.99)
                 if widening["mechanism"] == "c" else 0.0)

        return cls(
            teams=teams,
            idx={t: i for i, t in enumerate(teams)},
            att=arrays["att"], defe=arrays["def"], mu=arrays["mu"],
            home_adv=arrays["home_adv"], rho=arrays["rho"],
            sigma_att=arrays["sigma_att"], sigma_def=arrays["sigma_def"],
            provisional=frozenset(str(t) for t in getattr(post, "provisional_teams", ()) or ()),
            cold_start=frozenset(str(t) for t in getattr(post, "cold_start_teams", ()) or ()),
            likelihood=likelihood, alpha=alpha, max_goals=int(max_goals),
            cfg_hash=_hash_json(cfg),
        )

    # ---- shape -----------------------------------------------------------
    @property
    def n_particles(self) -> int:
        return int(self.mu.shape[-1])

    @property
    def n_teams(self) -> int:
        return len(self.teams)

    @property
    def n_scorelines(self) -> int:
        return (self.max_goals + 1) ** 2

    # ---- the rate leg ----------------------------------------------------
    def rates(self, home: str, away: str) -> tuple[np.ndarray, np.ndarray]:
        """Per-particle ``(lam_home, lam_away)``, each ``(S,)``.

        The plain-home branch of ``draw_api.per_draw_rates``, term for term and
        in the same order, with the ``+ 0.0`` covariate offsets written out
        because that is what the production path adds (and dropping them would
        make the parity approximate instead of bitwise). No neutral branch and
        no host factor: every Premier League fixture is an ordinary home game.
        """
        hi, ai = self.idx[home], self.idx[away]      # KeyError on unknown club
        lh = np.exp(self.mu + self.home_adv + self.att[hi] - self.defe[ai] + 0.0)
        la = np.exp(self.mu + 0.0 + self.att[ai] - self.defe[hi] + 0.0)
        return lh, la

    def is_provisional(self, home: str, away: str) -> bool:
        """Does production widen this fixture? (``finalize_grid``'s predicate.)"""
        return home in self.provisional or away in self.provisional

    # ---- the bundle ------------------------------------------------------
    def _meta(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "teams": list(self.teams),
            "provisional": sorted(self.provisional),
            "cold_start": sorted(self.cold_start),
            "likelihood": self.likelihood,
            "alpha": float(self.alpha),
            "max_goals": int(self.max_goals),
            "cfg_hash": self.cfg_hash,
            "n_particles": self.n_particles,
        }

    def content_hash(self) -> str:
        """sha256 over the metadata and every array byte, in a fixed order.

        This is the ``effective_posterior_hash`` the reproducibility envelope
        carries (plan v2 D14): two runs quoting the same hash sampled from the
        same posterior, cold-start rows and widening strength included.
        """
        h = hashlib.sha256()
        h.update(_canonical(self._meta()).encode("utf-8"))
        for name, attr in _PARAMS:
            arr = np.ascontiguousarray(getattr(self, attr), dtype=float)
            h.update(name.encode("utf-8"))
            h.update(repr(arr.shape).encode("utf-8"))
            h.update(arr.tobytes())
        return h.hexdigest()

    def save(self, path) -> Path:
        """Write ``<path>.npz`` (arrays) + ``<path>.json`` (metadata)."""
        path = Path(path)
        if path.suffix != ".npz":
            path = path.with_suffix(".npz")
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, **{attr: getattr(self, attr) for _n, attr in _PARAMS})
        meta = dict(self._meta(), content_hash=self.content_hash())
        path.with_suffix(".json").write_text(_canonical(meta) + "\n")
        return path

    @classmethod
    def load(cls, path) -> "ParticleBook":
        """Read a bundle back; refuses one whose arrays no longer hash to its json."""
        path = Path(path)
        if path.suffix != ".npz":
            path = path.with_suffix(".npz")
        meta = json.loads(path.with_suffix(".json").read_text())
        with np.load(path) as npz:
            arrays = {attr: np.ascontiguousarray(npz[attr], dtype=float)
                      for _n, attr in _PARAMS}
        teams = tuple(meta["teams"])
        book = cls(
            teams=teams, idx={t: i for i, t in enumerate(teams)},
            provisional=frozenset(meta["provisional"]),
            cold_start=frozenset(meta["cold_start"]),
            likelihood=meta["likelihood"], alpha=float(meta["alpha"]),
            max_goals=int(meta["max_goals"]), cfg_hash=meta["cfg_hash"],
            schema_version=meta.get("schema_version", "epl-particlebook-1"),
            **arrays)
        recorded = meta.get("content_hash")
        if recorded is not None and book.content_hash() != recorded:
            raise ParticleError(
                f"{path.name} does not match its recorded content hash "
                f"({recorded}); the bundle changed on disk and no forecast "
                "built from it would be reproducible")
        return book


# ==========================================================================
# the per-fixture legs
# ==========================================================================
def fixture_grids(lh, la, rho, max_goals: int
                  ) -> tuple[np.ndarray, np.ndarray]:
    """Per-particle scoreline grids ``(S, n, n)`` and excluded tail mass ``(S,)``.

    The vectorised form of ``draw_api.mean_grid_over_draws``'s per-draw loop:
    the independent Poisson outer product, ``dc_tau_np`` applied to the four
    Dixon-Coles cells at each particle's own ``rho``, negative cells clipped
    (the DC tau is a quasi-likelihood correction and CAN go negative on a tail
    ``rho`` against unbounded rates), then a per-particle renormalisation.

    ``excluded_mass[s] = 1 - sum(grid[s])``, measured after the clip and before
    the renormalisation: the probability the ``max_goals`` truncation throws
    away. The four tau perturbations cancel exactly in aggregate, so this is the
    Poisson truncation tail and nothing else — except where the clip fired,
    which raises the sum and so can only make the reported mass SMALLER. The
    number is honest either way and the gate in :func:`fixture_cdfs` is
    one-sided, so a clip cannot hide a truncation problem behind it.
    """
    lh = np.asarray(lh, dtype=float)
    la = np.asarray(la, dtype=float)
    rho = np.asarray(rho, dtype=float)
    if lh.shape != la.shape or lh.shape != rho.shape or lh.ndim != 1:
        raise ParticleError(
            f"rate/rho shapes disagree: lh {lh.shape}, la {la.shape}, "
            f"rho {rho.shape}; all must be (S,)")

    n = int(max_goals) + 1
    xs = np.arange(n)
    ph = poisson.pmf(xs[None, :], lh[:, None])          # (S, n)
    pa = poisson.pmf(xs[None, :], la[:, None])          # (S, n)
    g = ph[:, :, None] * pa[:, None, :]                 # (S, n, n)
    # The four Dixon-Coles cells, at each particle's own rho. `dc_tau_np` takes
    # x/y as scalars and the rates as arrays, so this IS the production tau.
    g[:, 0, 0] *= dc_tau_np(0, 0, lh, la, rho)
    g[:, 0, 1] *= dc_tau_np(0, 1, lh, la, rho)
    g[:, 1, 0] *= dc_tau_np(1, 0, lh, la, rho)
    g[:, 1, 1] *= dc_tau_np(1, 1, lh, la, rho)
    g = np.clip(g, 0.0, None)                           # tau<0 guard

    total = g.sum(axis=(1, 2))
    if not np.all(np.isfinite(g)) or not np.all(np.isfinite(total)) \
            or np.any(total <= 0.0):
        raise DegenerateGrid("non-finite predictive grid")
    return g / total[:, None, None], 1.0 - total


def mean_grid(grids: np.ndarray) -> np.ndarray:
    """``gbar`` — the mean over particles, i.e. parameter uncertainty integrated in.

    Identical to ``draw_api.mean_grid_over_draws``'s trailing ``grids.mean(0)``.
    """
    return np.asarray(grids).mean(axis=0)


def widening_component(gbar: np.ndarray, alpha: float) -> np.ndarray | None:
    """``q`` — the max-entropy component of production's mechanism-(c) mixture.

    Recovered from ``inflate_predictive``'s own output rather than re-derived::

        out = (1-a)*gbar + a*q   ->   q = (out - (1-a)*gbar) / a

    so the exponential-tilt solve stays in ONE place (``wcmodel.model.widening``)
    and this module cannot drift from it. ``None`` when there is no widening to
    reproduce (``alpha == 0``), which is also what ``inflate_predictive`` does at
    ``strength == 0``.

    Two edge cases resolve themselves: when a marginal mean sits on the support
    edge ``inflate_predictive`` returns the grid unchanged, and the algebra above
    then returns ``q == gbar`` — sampling from either branch gives the same law,
    which is exactly right. And ``gbar`` sums to 1 to floating point, so the
    normalisation inside ``inflate_predictive`` is a no-op at the 1e-16 level;
    ``q`` is renormalised here anyway because a CDF must be built from a proper
    pmf.
    """
    alpha = float(alpha)
    if alpha <= 0.0:
        return None
    out = inflate_predictive(np.asarray(gbar, dtype=float),
                             is_provisional=True, strength=alpha)
    q = (out - (1.0 - alpha) * gbar) / alpha
    q = np.clip(q, 0.0, None)
    total = float(q.sum())
    if not np.isfinite(total) or total <= 0.0:          # pragma: no cover
        raise DegenerateGrid("non-finite widening component")
    return q / total


@dataclass(eq=False)
class FixtureCDF:
    """Everything the engine needs to sample one fixture, and nothing else.

    ``cdf[s]`` is the flat cumulative distribution over the ``(max_goals+1)^2``
    scorelines for particle ``s`` (row-major: index ``h*n + a``). ``q_cdf`` is
    the widening component's, present iff the fixture is provisional. The engine
    draws a uniform, picks the branch with a second uniform against ``alpha``,
    and inverse-CDFs — no rejection, no rate-level work, nothing that consumes a
    variable number of random numbers.
    """

    cdf: np.ndarray                 #: (S, n^2), each row ending at exactly 1.0
    q_cdf: np.ndarray | None        #: (n^2,) or None
    one_x_two: np.ndarray           #: (S, 3) — home / draw / away per particle
    excluded_mean: float            #: particle-mean truncated tail mass
    provisional: bool
    #: The D11 v1.0.1 record: ``{mean, median, worst, n_over_1pct, flagged}``.
    #: Carried on every fixture, not only the flagged ones, so the envelope can
    #: report the whole distribution rather than its outliers (ruling A1 (b)).
    excluded: dict = field(default_factory=dict)


def excluded_mass_stats(excluded) -> dict:
    """One fixture's truncation record: mean, median, worst, and the tail count.

    The mean alone is a poor description of this quantity. At the 2026-08-21
    opener the worst fixture's particle-mean was 0.0054 while its MEDIAN
    particle was 1.9e-4 and its worst particle 0.45: ten draws of a thousand
    carried 43% of the mean. So the record keeps all four numbers, and
    ``limitations.md`` prints all four for a flagged fixture — a reader who sees
    only the mean would conclude the tail is uniformly small, which is the one
    thing it is not.

    ``flagged`` is the mean against :data:`FLAG_EXCLUDED_MASS`; the hard stop is
    :data:`HARD_STOP_EXCLUDED_MASS` and is applied in :func:`fixture_cdfs`.
    """
    e = np.asarray(excluded, dtype=float)
    mean = float(e.mean())
    return {
        "mean": mean,
        "median": float(np.median(e)),
        "worst": float(e.max()),
        "n_over_1pct": int((e > LARGE_PARTICLE_MASS).sum()),
        "flagged": bool(mean > FLAG_EXCLUDED_MASS),
    }


def _outcome_matrix(n: int) -> np.ndarray:
    """``(n^2, 3)`` indicator columns: home win, draw, away win."""
    xs = np.arange(n)
    home = (xs[:, None] > xs[None, :]).reshape(-1)
    draw = (xs[:, None] == xs[None, :]).reshape(-1)
    away = (xs[:, None] < xs[None, :]).reshape(-1)
    return np.stack([home, draw, away], axis=1).astype(float)


def _to_cdf(pmf: np.ndarray) -> np.ndarray:
    """Cumulative sum with the last entry pinned to exactly 1.0.

    The pin matters: an inverse-CDF search against a uniform in [0, 1) must
    never fall off the end because the cumulative sum stopped at 1 - 2e-16.
    """
    cdf = np.cumsum(pmf, axis=-1)
    cdf[..., -1] = 1.0
    return cdf


def fixture_cdfs(book: ParticleBook, home: str, away: str) -> FixtureCDF:
    """Build one fixture's sampling object from the book.

    Rates -> per-particle grids -> truncation record -> per-particle CDFs, plus
    the widening component when production would widen this fixture. The
    resulting mixture ``(1-alpha)*mean(grids) + alpha*q`` is the production
    grid to floating point, which is the property plan v2 D12 is built on and
    the parity test asserts against ``Posterior.predict_scoreline`` directly.

    The truncation record (D11 v1.0.1) is attached to every fixture and refuses
    none below :data:`HARD_STOP_EXCLUDED_MASS`; :mod:`epl.leaguesim` collects it
    into the run's envelope and prints the flagged fixtures by id.
    """
    lh, la = book.rates(home, away)
    grids, excluded = fixture_grids(lh, la, book.rho, book.max_goals)
    stats = excluded_mass_stats(excluded)
    excluded_mean = stats["mean"]
    if excluded_mean > HARD_STOP_EXCLUDED_MASS:
        raise ExcludedMassTooLarge(
            f"{home} v {away}: the {book.max_goals}-goal truncation excludes a "
            f"particle-mean {excluded_mean:.3g} of the probability mass, over "
            f"the {HARD_STOP_EXCLUDED_MASS:g} ceiling pre-stated in amendment "
            "A1. A mass this large is a mis-scaled rate, not a cold-start tail: "
            "the sampled law would differ materially from the published grid, "
            "so the run fails closed instead of quietly discarding the tail.")

    provisional = book.is_provisional(home, away)
    flat = grids.reshape(grids.shape[0], -1)
    q = widening_component(mean_grid(grids), book.alpha) if provisional else None
    return FixtureCDF(
        cdf=_to_cdf(flat),
        q_cdf=None if q is None else _to_cdf(q.reshape(-1)),
        one_x_two=flat @ _outcome_matrix(book.max_goals + 1),
        excluded_mean=excluded_mean,
        provisional=provisional,
        excluded=stats,
    )


# ==========================================================================
# helpers
# ==========================================================================
def _canonical(obj) -> str:
    """Deterministic JSON: sorted keys, no incidental whitespace (plan v2 D14)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _hash_json(obj) -> str:
    return hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()
