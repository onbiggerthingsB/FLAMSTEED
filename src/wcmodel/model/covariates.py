"""Leakage-safe covariate transform: standardize on the < cutoff TRAINING rows only,
mask missing values' CONTRIBUTION to zero (never impute a fabricated value). The SAME
fitted transform is used at fit and at predict — the single source of truth that keeps
the covariate leakage-safe and the fit/predict consistent."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


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
        return cls(name, float(obs.mean()), sd, any_observed=True)

    def apply(self, values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        x = np.asarray(values, dtype=float)
        observed = np.isfinite(x) & self.any_observed
        if self.sd > 0.0:
            z = np.where(observed, (x - self.mean) / self.sd, 0.0)
        else:                                   # zero variance (or never observed) -> no signal
            z = np.zeros_like(x)
        return z.astype(float), observed.astype(float)
