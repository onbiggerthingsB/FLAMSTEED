"""Leakage-safe covariate transform: standardize on the < cutoff TRAINING rows only,
mask missing values' CONTRIBUTION to zero (never impute a fabricated value). The SAME
fitted transform is used at fit and at predict — the single source of truth that keeps
the covariate leakage-safe and the fit/predict consistent."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Standardized-value sanity bound: this transform feeds exp() in a rate model, so a
# near-constant / degenerate covariate (tiny positive sd -> enormous z) could otherwise
# push exp(rate) to overflow. A 10-sigma clamp is a no-op on healthy rest/travel/altitude
# data but caps the worst case. This is a SANITY BOUND, not imputation.
Z_CLAMP = 10.0


@dataclass(frozen=True)
class CovariateTransform:
    name: str
    mean: float
    sd: float            # observed-row sample std (ddof=1); 0.0 -> treated as "no signal"
    any_observed: bool

    @classmethod
    def fit(cls, name: str, train_values: np.ndarray) -> "CovariateTransform":
        x = np.asarray(train_values, dtype=float)
        obs = x[np.isfinite(x)]
        if obs.size == 0:
            return cls(name, 0.0, 0.0, any_observed=False)
        # Sample std (ddof=1) is the conventional standardizer; a single observed
        # row has no spread (ddof=1 would divide by 0) -> sd=0.0 "no signal".
        sd = float(obs.std(ddof=1)) if obs.size > 1 else 0.0
        mean = float(obs.mean())
        # Pathological-but-finite inputs (e.g. 1e200) can overflow mean/sd to inf/nan.
        # A non-finite standardizer cannot produce a trustworthy z -> treat as NO SIGNAL
        # (any_observed=False) so apply() masks everything to a zero contribution.
        if not (np.isfinite(mean) and np.isfinite(sd)):
            return cls(name, 0.0, 0.0, any_observed=False)
        return cls(name, mean, sd, any_observed=True)

    def apply(self, values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        x = np.asarray(values, dtype=float)
        observed = np.isfinite(x) & self.any_observed
        if self.sd > 0.0:
            z = np.where(observed, (x - self.mean) / self.sd, 0.0)
        else:                                   # zero variance (or never observed) -> no signal
            z = np.zeros_like(x)
        # GUARANTEE finiteness: a non-finite standardized value cannot be trusted, so
        # force it to 0.0 AND drop it from the mask (treat as missing, not a real signal).
        finite = np.isfinite(z)
        z = np.where(finite, z, 0.0)
        observed = observed & finite
        # Standardized-value sanity bound (NOT imputation: missing values stay masked to a
        # zero contribution). Clamp keeps exp(rate) from overflowing on a degenerate covariate.
        z = np.clip(z, -Z_CLAMP, Z_CLAMP)
        return z.astype(float), observed.astype(float)
