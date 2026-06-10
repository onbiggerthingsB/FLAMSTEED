"""Per-draw scoreline sampling from a Phase-2 Posterior. RateBook exposes, for one
posterior draw s, the (lambda_home, lambda_away) for any fixture; sample_score
samples a scoreline from the RAW DC/BP pmf. The (c) provisional widening is
deliberately NOT applied (spec 2.2/5.2): uncertainty enters the sim once, via the
posterior draw + this scoreline sampling."""
from __future__ import annotations

import numpy as np
from scipy.stats import poisson

from wcmodel.model.likelihoods import dc_tau_np
from wcmodel.model.widening import inflate_predictive


def fatten_grid(grid: np.ndarray, alpha: float) -> np.ndarray:
    """Phase-4b SIM-ONLY mean-preserving tail-fattening of a scoreline grid.

    A thin wrapper over the AUDITED ``model.widening.inflate_predictive`` with
    ``is_provisional=True`` forced, so the mean-preserving max-entropy mix fires on
    ANY fixture (not just provisional teams) at mix weight ``alpha``. The transform
    preserves BOTH marginal means (E[home], E[away]) to machine precision and is the
    flattest (highest-entropy, fattest-tailed) reshape at those fixed means — i.e. a
    "mean-preserving tail-fattening" transform, reusing a construction whose
    mean-preservation/entropy-increase invariants are already RED->GREEN-locked in
    ``tests/model/...widening...``. ``alpha == 0.0`` is the IDENTITY (off-state). An
    out-of-range ``alpha`` raises (inherited from ``inflate_predictive``).

    This is the 4b SIM-EXPERIMENT knob ONLY — it is NOT wired into the model fit,
    ``predict_scoreline``, ``config``, or any production path; it is applied solely
    inside the sim sampler when ``SimConfig.tail_fatten`` is set, so production
    forecasts are byte-identical."""
    return inflate_predictive(grid, is_provisional=True, strength=float(alpha))


def bucket_alpha(gap: float, alpha_by_bucket, edges) -> float:
    """Map a SIGNED Elo gap to its |gap| bucket's tail-fatten ``alpha``.

    ``edges`` are the INTERIOR |gap| bucket boundaries (ascending; ``len ==
    len(alpha_by_bucket) - 1``); a |gap| in ``[edges[i-1], edges[i])`` lands in
    bucket ``i``. Sign-symmetric (only ``|gap|`` matters). With a monotone
    ``alpha_by_bucket`` the returned alpha is monotone non-decreasing in |gap| (the
    high-mismatch buckets get the most fattening). Pure / no I/O."""
    g = abs(float(gap))
    i = int(np.searchsorted(np.asarray(edges, dtype=float), g, side="right"))
    return float(alpha_by_bucket[i])


class RateBook:
    """Per-draw (lambda_home, lambda_away) for any fixture from one Posterior.

    Stacks each posterior var to a trailing sample axis (chain*draw -> s): a
    team-indexed var becomes (n_teams, S) so ``att[hi, s]`` is a scalar; a scalar
    var becomes (S,). ``rates(home, away, neutral, draw)`` reads draw ``s`` only and
    rebuilds the model's ``_rates`` exactly. NO (c) widening is applied here -- this
    is the RAW rate structure; cross-fixture correlation across a tournament's
    fixtures is preserved precisely because every fixture in one sim shares the same
    draw ``s`` of att/def/mu/home_adv (re-widening per draw would double-count
    uncertainty and destroy that shared-parameter correlation)."""

    def __init__(self, posterior):
        self.teams = list(posterior.teams)
        self._idx = {t: i for i, t in enumerate(self.teams)}
        p = posterior.idata.posterior
        self.att = p["att"].stack(s=("chain", "draw")).values     # (n_teams, S)
        self.defe = p["def"].stack(s=("chain", "draw")).values    # (n_teams, S)
        self.mu = p["mu"].stack(s=("chain", "draw")).values        # (S,)
        self.home_adv = p["home_adv"].stack(s=("chain", "draw")).values  # (S,)
        # Neutral-venue calibration fraction k: a neutral game scores at the AVERAGE
        # environment (mu + k*home_adv on both sides), MIRRORING predict_scoreline so
        # the Monte-Carlo progression sim and the per-fixture grid agree (no card-vs-
        # progression divergence). posterior._cfg IS the `model` block, so the key is
        # read WITHOUT a leading "model".
        self.neutral_home_adv_fraction = posterior._cfg["neutral_home_adv_fraction"]
        self.likelihood = posterior.likelihood
        if self.likelihood == "dixon_coles":
            self.rho = p["rho"].stack(s=("chain", "draw")).values  # (S,)
        else:  # bivariate_poisson: l3 = exp(log_lambda3), the shared BP term
            self.l3 = np.exp(p["log_lambda3"].stack(s=("chain", "draw")).values)
        self.n_draws = self.mu.shape[-1]

    def rates(self, home, away, neutral, draw, host_factor=None):
        # Mirrors Posterior.predict_scoreline EXACTLY (the sim-must-mirror-predict
        # discipline) — per-side home terms (home_term, away_term):
        #   * host_factor set (T5): the 2026 hosts play a HOME game. A PREDICTION-time
        #     scalar (= k from config) on the ALREADY-FITTED home_adv (no new fitted
        #     parameter). Home carries host_factor*home_adv; the opponent stays at the
        #     away rate (away_term=0). UNCHANGED.
        #   * neutral (CALIBRATION FIX): a truly-neutral game scores at the AVERAGE
        #     environment — k_neutral*home_adv on BOTH sides — not the bare away rate.
        #     This is the IDENTICAL term predict_scoreline applies, so the progression
        #     sim and the per-fixture grid agree.
        #   * ordinary home/away: home carries the full home_adv; away has none. UNCHANGED.
        #   log lambda_home = mu + home_term + att[home] - def[away]
        #   log lambda_away = mu + away_term + att[away] - def[home]
        hi, ai = self._idx[home], self._idx[away]   # KeyError on unknown team
        s = draw
        if host_factor is not None:
            home_term, away_term = host_factor * self.home_adv[s], 0.0
        elif neutral:
            k_neutral = self.neutral_home_adv_fraction
            home_term = away_term = k_neutral * self.home_adv[s]
        else:
            home_term, away_term = self.home_adv[s], 0.0
        lh = np.exp(
            self.mu[s] + home_term
            + self.att[hi, s] - self.defe[ai, s]
        )
        la = np.exp(self.mu[s] + away_term + self.att[ai, s] - self.defe[hi, s])
        return float(lh), float(la)


def sample_score(lh, la, *, rng, likelihood, rho=None, l3=None, max_goals=12,
                 fatten_alpha=0.0):
    """Sample one scoreline (x_home, y_away) from the RAW DC/BP pmf at the given rates.

    NO (c) provisional widening (no inflate_predictive) -- raw pmf only; uncertainty
    in the sim comes from the posterior draw (RateBook) + this outcome sampling.

    bivariate_poisson: GENERATIVE -- W1~Pois(lh), W2~Pois(la), W3~Pois(l3) shared,
    return (W1+W3, W2+W3). ``lh``/``la`` are the BP independent parts (the model's
    ``_rates`` lambda1/lambda2); the shared ``l3`` induces positive goal correlation
    and the marginals are lambda1+l3, lambda2+l3 -- correct by construction. No grid.

    dixon_coles: tau-corrected independent-Poisson grid over [0, max_goals]^2. The
    DC tau is a quasi-likelihood (does not integrate to 1), so a tau<0 cell (extreme
    rho against unbounded rates) is CLIPPED to 0 and the grid is RENORMALIZED before
    sampling -- no negative probability, valid (x, y) in [0, max_goals].

    ``fatten_alpha`` (Phase-4b SIM-EXPERIMENT ONLY, default 0.0 = the RAW pmf above,
    byte-identical): when > 0 the per-draw scoreline grid is reshaped by the
    mean-preserving :func:`fatten_grid` before sampling. ``fatten_alpha == 0.0`` short-
    circuits to the EXACT raw path (so the default sim is unchanged, RNG-identical:
    DC still ``rng.choice`` on the raw grid, BP still the generative draw). When
    ``fatten_alpha > 0`` BOTH likelihoods sample from an explicitly-built, fattened
    grid via ``rng.choice`` (BP's grid is the proper joint pmf ``exp(bp_loglik_np)``)
    -- the experiment changes the SAMPLED outcomes only, no fitted parameter, no
    config, no posterior. This is the only consumer of the override."""
    if fatten_alpha == 0.0:
        # RAW path -- byte-identical to the pre-4b sim (same RNG consumption).
        if likelihood == "bivariate_poisson":
            w3 = rng.poisson(l3)                    # generative: X=W1+W3, Y=W2+W3
            return int(rng.poisson(lh) + w3), int(rng.poisson(la) + w3)
        n = max_goals + 1
        xs = np.arange(n)                           # Dixon-Coles: tau-corrected grid
        g = poisson.pmf(xs, lh)[:, None] * poisson.pmf(xs, la)[None, :]
        for (x, y) in ((0, 0), (0, 1), (1, 0), (1, 1)):
            g[x, y] *= dc_tau_np(x, y, lh, la, rho)
        g = np.clip(g, 0.0, None)                   # tau<0 guard: no negative prob
        g = g / g.sum()                             # quasi-likelihood -> renormalize
        flat = rng.choice(n * n, p=g.ravel())
        return int(flat // n), int(flat % n)
    # FATTEN path (4b experiment): build the explicit per-draw grid, fatten it
    # (mean-preserving), sample via rng.choice. BP gets its proper joint pmf here.
    g = _scoreline_grid(lh, la, likelihood=likelihood, rho=rho, l3=l3, max_goals=max_goals)
    g = fatten_grid(g, fatten_alpha)
    n = g.shape[0]
    flat = rng.choice(n * n, p=g.ravel())
    return int(flat // n), int(flat % n)


def _scoreline_grid(lh, la, *, likelihood, rho=None, l3=None, max_goals=12) -> np.ndarray:
    """Normalized per-draw scoreline grid ``g[x_home, y_away]`` over [0, max_goals]^2.

    Mirrors :meth:`Posterior.predict_scoreline`'s per-draw construction: DC =
    tau-corrected independent Poissons (tau<0 clipped, renormalized — quasi-likelihood);
    BP = the proper joint pmf ``exp(bp_loglik_np)`` renormalized (the finite-grid
    truncation is the only reason the sum differs from 1). Used only by the 4b fatten
    path so a fattened grid is sampled from the SAME structure the raw path uses."""
    n = max_goals + 1
    xs = np.arange(n)
    if likelihood == "bivariate_poisson":
        from wcmodel.model.likelihoods import bp_loglik_np
        g = np.array(
            [[np.exp(bp_loglik_np(x, y, lh, la, l3)) for y in range(n)] for x in range(n)]
        )
        return g / g.sum()
    g = poisson.pmf(xs, lh)[:, None] * poisson.pmf(xs, la)[None, :]
    for (x, y) in ((0, 0), (0, 1), (1, 0), (1, 1)):
        g[x, y] *= dc_tau_np(x, y, lh, la, rho)
    g = np.clip(g, 0.0, None)
    return g / g.sum()
