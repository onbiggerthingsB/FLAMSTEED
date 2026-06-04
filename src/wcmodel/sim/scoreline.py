"""Per-draw scoreline sampling from a Phase-2 Posterior. RateBook exposes, for one
posterior draw s, the (lambda_home, lambda_away) for any fixture; sample_score
samples a scoreline from the RAW DC/BP pmf. The (c) provisional widening is
deliberately NOT applied (spec 2.2/5.2): uncertainty enters the sim once, via the
posterior draw + this scoreline sampling."""
from __future__ import annotations

import numpy as np
from scipy.stats import poisson

from wcmodel.model.likelihoods import dc_tau_np


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
        self.likelihood = posterior.likelihood
        if self.likelihood == "dixon_coles":
            self.rho = p["rho"].stack(s=("chain", "draw")).values  # (S,)
        else:  # bivariate_poisson: l3 = exp(log_lambda3), the shared BP term
            self.l3 = np.exp(p["log_lambda3"].stack(s=("chain", "draw")).values)
        self.n_draws = self.mu.shape[-1]

    def rates(self, home, away, neutral, draw):
        # Mirrors scoreline._rates EXACTLY:
        #   log lambda_home = mu + home_adv*(1-neutral) + att[home] - def[away]
        #   log lambda_away = mu +                        att[away] - def[home]
        # home_adv enters ONLY the non-neutral home rate; away has no home term.
        hi, ai = self._idx[home], self._idx[away]   # KeyError on unknown team
        s = draw
        lh = np.exp(
            self.mu[s] + (0.0 if neutral else self.home_adv[s])
            + self.att[hi, s] - self.defe[ai, s]
        )
        la = np.exp(self.mu[s] + self.att[ai, s] - self.defe[hi, s])
        return float(lh), float(la)


def sample_score(lh, la, *, rng, likelihood, rho=None, l3=None, max_goals=12):
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
    sampling -- no negative probability, valid (x, y) in [0, max_goals]."""
    if likelihood == "bivariate_poisson":
        w3 = rng.poisson(l3)                        # generative: X=W1+W3, Y=W2+W3
        return int(rng.poisson(lh) + w3), int(rng.poisson(la) + w3)
    n = max_goals + 1
    xs = np.arange(n)                               # Dixon-Coles: tau-corrected grid
    g = poisson.pmf(xs, lh)[:, None] * poisson.pmf(xs, la)[None, :]
    for (x, y) in ((0, 0), (0, 1), (1, 0), (1, 1)):
        g[x, y] *= dc_tau_np(x, y, lh, la, rho)
    g = np.clip(g, 0.0, None)                       # tau<0 guard: no negative prob
    g = g / g.sum()                                 # quasi-likelihood -> renormalize
    flat = rng.choice(n * n, p=g.ravel())
    return int(flat // n), int(flat % n)
