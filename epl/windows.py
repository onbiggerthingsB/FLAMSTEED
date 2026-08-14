"""The tuning/scoring split, as a module constant with a guard attached.

THE ONE RULE. Every hyperparameter this probe carries — the Elo K, the
promoted-club seed, the cold-start prior, the season carryover, the update-side
home advantage — is chosen on :data:`TUNE_SEASONS` and nowhere else. The
scoring window is not looked at, not peeked at, and not "sanity-checked"
during tuning. A number chosen against the window it will be judged on is not a
hyperparameter; it is a fitted parameter, and reporting it as out-of-sample is
the specific dishonesty this whole exercise exists to avoid.

WHY THESE SEASONS.

* ``2014/15`` is Elo burn-in. Every club starts at ``initial_rating``, so the
  ratings carry no information and scoring the season would measure the seed
  rather than the rating system. It is walked, never scored.
* ``2015/16``–``2018/19`` is the tuning objective: 1,520 matches, four seasons,
  nine clubs arriving with no prior match in the archive — enough promoted-club
  events for the seed to be identifiable at all, which a two-season window
  would not be.
* ``2019/20``–``2024/25`` is the scoring window: 2,280 matches, six seasons,
  complete odds coverage. Never touched during tuning.
* ``2025/26`` is EXCLUDED ENTIRELY, from both windows. Its odds coverage is a
  contiguous first-half slice — prices stop after 2026-01-08, 210 of 380
  matches — and the covered rows have a home-win rate of 0.452 against 0.394
  for the uncovered ones. That is a biased sample of a season, not a sample of
  a biased season, and including it would put a selection effect inside the
  headline. The paired model-versus-Elo comparison would survive it (both
  forecasters see the same fixtures), but the market column would not, and the
  market column is how the result is read.

The split moved once, deliberately and BEFORE any model-versus-Elo number
existed. The Elo baseline (``reports/epl_baseline.md``) tuned on 2014/15–
2017/18 and scored 2018/19–2025/26. This phase tunes on 2014/15–2018/19 and
scores 2019/20–2024/25: 2018/19 moves into tuning to buy a fourth scored tuning
season and three more promoted-club events, and 2025/26 leaves for the reason
above. What that costs in honesty is recorded in ``reports/epl_prereg.md`` §7
and is not hidden: the Elo baseline's per-season scores on 2019/20–2024/25 are
already published, so the scoring window is blind with respect to the Bayesian
model and NOT blind with respect to Elo.
"""

from __future__ import annotations

from typing import Iterable

__all__ = [
    "TUNE_SEASONS", "TUNE_BURN_IN", "TUNE_SCORED", "SCORE_SEASONS",
    "EXCLUDED_SEASONS", "assert_tuning_only", "assert_no_score_leak",
]

#: Walked during tuning. Hyperparameters are chosen against these and no others.
TUNE_SEASONS: tuple[str, ...] = ("2014/15", "2015/16", "2016/17", "2017/18",
                                 "2018/19")

#: Walked but not scored: with every club at `initial_rating` the ratings are
#: uninformative, so this season would measure the seed, not the model.
TUNE_BURN_IN: tuple[str, ...] = ("2014/15",)

#: The tuning OBJECTIVE's seasons — 1,520 matches.
TUNE_SCORED: tuple[str, ...] = tuple(s for s in TUNE_SEASONS
                                     if s not in TUNE_BURN_IN)

#: Scored once, after the freeze. 2,280 matches.
SCORE_SEASONS: tuple[str, ...] = ("2019/20", "2020/21", "2021/22", "2022/23",
                                  "2023/24", "2024/25")

#: In the archive, in neither window. See the module docstring.
EXCLUDED_SEASONS: tuple[str, ...] = ("2025/26",)


def assert_tuning_only(seasons: Iterable[str], what: str = "the tuning frame",
                       ) -> None:
    """Raise if `seasons` contains anything outside the tuning window.

    Called by every function that selects a hyperparameter. The check is on the
    seasons actually present in the frame, not on a flag the caller passes, so
    a mis-sliced frame fails loudly instead of quietly widening the window.
    """
    present = set(seasons)
    leak = sorted(present & (set(SCORE_SEASONS) | set(EXCLUDED_SEASONS)))
    if leak:
        raise ValueError(
            f"{what} contains non-tuning season(s) {leak}. Hyperparameters "
            "chosen against the window they will be judged on are fitted "
            "parameters, not hyperparameters, and a result computed that way "
            "is not out-of-sample.")


def assert_no_score_leak(seasons: Iterable[str], what: str = "the frame",
                         ) -> None:
    """Raise if `seasons` contains an EXCLUDED season. Scoring-side guard."""
    leak = sorted(set(seasons) & set(EXCLUDED_SEASONS))
    if leak:
        raise ValueError(
            f"{what} contains excluded season(s) {leak}; see epl.windows for "
            "why 2025/26 is in neither window.")
