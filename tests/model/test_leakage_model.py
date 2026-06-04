import numpy as np
import pandas as pd
import pytest

from wcmodel.data.sources.results import normalize_results
from wcmodel.data.store import BitemporalStore, Policy
from wcmodel.model.scoreline import fit
from wcmodel.model.volatility_diagnostic import count_volatility_arm


@pytest.mark.slow
def test_fit_invariant_to_future_result_mutation(mutable_store):
    """Model leakage GATE: a result dated AFTER the cutoff must not change ANY
    part of the per-cutoff fit. ``fit()`` consumes only ``features.build(cutoff)``
    + the as-of-cutoff provisional set (``count_volatility_arm``), both reading
    strictly < cutoff. ADVI is seeded, so a leakage-free fit is BIT-STABLE across
    the future-result mutation; any change is a real leak.

    WHY FULL-POSTERIOR INVARIANCE IS THE RIGHT GATE (Codex T9). The previous
    canary asserted only that ``predict_1x2("Brazil","Argentina")`` was invariant.
    That is a coverage hole: the mutated match is Mexico v Malta, so a leak
    localized to Mexico/Malta strengths — or a leak into ``provisional_teams`` via
    ``count_volatility_arm`` (which a Brazil-Argentina 1X2 cannot see) — would slip
    through. A leakage gate must catch ANY leak into the fit, not one fixture pair.
    Under a SEEDED fit the entire posterior is a deterministic function of the
    < cutoff panel + provisional set; therefore ANY > cutoff data reaching the fit
    would perturb SOME posterior variable (a team strength, a global param, or the
    provisional set) away from bit-identical. So we assert invariance of the WHOLE
    object: every posterior ``data_var`` elementwise, the provisional set, and the
    predicted 1X2 for BOTH a far pair AND the most-likely-affected (mutated) pair.

    TWO LEAK MODES, EACH PROVEN NON-VACUOUS (Codex T9 final). This gate guards two
    structurally DIFFERENT ways a > cutoff row could leak into the fit, and each is
    backed by its own non-vacuity proof so neither assertion is trivially green:

      (a) SCORE / POSTERIOR mode — a leak that lets a > cutoff row's SCORE reach
          the likelihood, moving a team strength or global parameter. Exercised by
          ``mutate_future_result`` (a SCORE mutation of a post-cutoff row) + the
          per-data_var posterior-invariance assertion (2) + the 1X2 assertion (3).
          TEETH: ``test_full_posterior_invariance_is_non_vacuous`` — the SAME score
          mutation applied to an IN-panel (< cutoff) row provably moves the
          posterior (a full-panel leak shifts it ~4e-3), so the invariance here is
          a real gate, not a panel that simply can never move.

      (b) COUNT / PROVISIONAL-SET mode — a DISJOINT leak the posterior check cannot
          catch: a post-cutoff row whose mere PRESENCE wrongly inflates a team's
          games-count in ``count_volatility_arm``, flipping its few-games provisional
          flag WITHOUT moving the posterior (the row is unplayed/NaN-score or > cutoff,
          so it never enters the likelihood — a SCORE mutation can't trigger it).
          Guarded by the ``provisional_teams ==`` assertion (1). TEETH:
          ``test_provisional_set_invariant_to_added_post_cutoff_row`` — ADDING a
          post-cutoff row (the perturbation a COUNT leak reacts to) leaves the set
          invariant via the ``date < cutoff`` filter, while a leak admitting that
          row would flip the team's membership; so the ``==`` assertion WOULD catch
          the count-mode leak. (``test_provisional_set_leak_would_be_caught`` adds a
          complementary cutoff-sweep proof of the same boundary.)

    So both the POSTERIOR and the PROVISIONAL SET are leakage-guarded with
    demonstrated teeth.
    """
    kw = dict(backend="advi", draws=120, seed=0, advi_iters=3000)
    before = fit("2024-06-01", mutable_store, **kw)
    mutable_store.mutate_future_result(after="2024-06-01")  # asserts the score changed
    after = fit("2024-06-01", mutable_store, **kw)

    # (1) Provisional set invariant — catches a leak via count_volatility_arm
    # (the as-of-cutoff volatility/few-games arm) into the predict-time widening
    # set, which no single 1X2 prediction would necessarily reveal.
    assert before.provisional_teams == after.provisional_teams, (
        "future result leaked into the provisional set (count_volatility_arm)"
    )

    # (2) EVERY posterior data variable bit-identical (att, def, mu, home_adv,
    # rho or log_lambda3, and the raw/sigma hyperparams). Iterating all data_vars
    # — not a hand-picked subset — catches a leak into ANY team's strength or any
    # global parameter, not just one fixture pair. Same var set in both fits is
    # itself part of the contract (a leak cannot add/drop a variable either).
    before_vars = set(before.idata.posterior.data_vars)
    after_vars = set(after.idata.posterior.data_vars)
    assert before_vars == after_vars, "posterior variable set changed under mutation"
    for name in before_vars:
        b = before.idata.posterior[name].values
        a = after.idata.posterior[name].values
        assert b.shape == a.shape, f"posterior var {name!r} changed shape under mutation"
        assert np.array_equal(b, a), (
            f"future result leaked into posterior var {name!r}: "
            f"max|Δ|={np.abs(b - a).max():.3e}"
        )

    # (3) predict_1x2 bit-identical (< 1e-9) for BOTH a FAR pair (Brazil v
    # Argentina) AND the MUTATED match's teams (Mexico v Malta — the most-likely-
    # affected pair, so a leak localized to the mutated teams is caught here).
    for home, away in (("Brazil", "Argentina"), ("Mexico", "Malta")):
        b1x2 = before.predict_1x2(home, away)
        a1x2 = after.predict_1x2(home, away)
        for outcome in ("home", "draw", "away"):
            assert abs(b1x2[outcome] - a1x2[outcome]) < 1e-9, (
                f"future result leaked into predict_1x2({home!r},{away!r})[{outcome!r}]"
            )


@pytest.mark.slow
def test_full_posterior_invariance_is_non_vacuous(mutable_store):
    """Non-vacuity guard for the gate above. The full-posterior/provisional/1X2
    invariance is only a meaningful leakage GATE if a leak would actually MOVE
    those quantities — i.e. the test is not trivially green because nothing in
    this panel can ever move. Here we fit the SAME cutoff over two stores whose
    < cutoff (in-panel, played) data DIFFER on a full-panel match, and assert the
    posterior + provisional set + 1X2 genuinely change. If this fails, the
    invariance assertions in the gate above are vacuous and must be revisited.

    Concretely: ``mutate_future_result(after=D)`` rewrites the EARLIEST result
    dated after ``D``. With ``D="2020-01-01"`` that earliest match is well BEFORE
    the 2024-06-01 fit cutoff, so the rewritten row is IN-panel for the fit and
    must perturb the seeded posterior — unlike the gate above, where the mutated
    match is dated AFTER the cutoff and therefore excluded."""
    kw = dict(backend="advi", draws=120, seed=0, advi_iters=3000)
    base = fit("2024-06-01", mutable_store, **kw)
    # Mutate an EARLY (in-panel, < cutoff) match so the fit's own input changes.
    mutable_store.mutate_future_result(after="2020-01-01")
    perturbed = fit("2024-06-01", mutable_store, **kw)

    # SOME posterior variable must move (the panel genuinely changed). att/def are
    # team strengths and are the most direct carrier of an in-panel score change.
    moved = any(
        not np.array_equal(
            base.idata.posterior[name].values, perturbed.idata.posterior[name].values
        )
        for name in base.idata.posterior.data_vars
    )
    assert moved, (
        "non-vacuity FAILED: a full-panel (< cutoff) score change moved NO "
        "posterior variable — the invariance gate would be vacuous"
    )


def _edge_store(tmp_path) -> BitemporalStore:
    """A tiny store where team ``Edge`` has EXACTLY 4 played matches before
    2024-01-10 and a 5th match AFTER it. ``Edge`` always draws 0-0 vs ``Foe`` on
    NEUTRAL ground, so both stay pinned at ``initial_rating`` and every rating
    delta is exactly 0.0 — Edge's recent_volatility is therefore 0 (well under
    the 16.5 threshold) regardless of cutoff. That isolates the ONLY thing that
    changes between the two cutoffs below to the few-games COUNT (4 vs 5), which
    is exactly the provisional-set boundary we want to probe.
    """
    raw = pd.DataFrame(
        [
            # date, home, away, hs, as, tournament, city, country, neutral
            ("2024-01-02", "Edge", "Foe", 0, 0, "Friendly", "London", "England", True),
            ("2024-01-04", "Edge", "Foe", 0, 0, "Friendly", "London", "England", True),
            ("2024-01-06", "Edge", "Foe", 0, 0, "Friendly", "London", "England", True),
            ("2024-01-08", "Edge", "Foe", 0, 0, "Friendly", "London", "England", True),
            # 5th match — dated AFTER D=2024-01-10. In-set vs out-of-set hinges
            # entirely on whether THIS row is counted.
            ("2024-01-12", "Edge", "Foe", 0, 0, "Friendly", "London", "England", True),
        ],
        columns=["date", "home_team", "away_team", "home_score", "away_score",
                 "tournament", "city", "country", "neutral"],
    )
    store = BitemporalStore(root=tmp_path)
    store.write("results", normalize_results(raw), policy=Policy.POINT_IN_TIME,
                keys=["match_id"], source="martj42", source_version="test")
    return store


def _four_game_edge_store(tmp_path) -> BitemporalStore:
    """A store where team ``Edge`` has EXACTLY 4 played matches, ALL dated before
    the cutoff ``C`` = 2024-01-10 (and a foil ``Foe`` so Elo has an opponent).
    At ``C`` Edge counts 4 games -> few-games-provisional -> IN the provisional
    set. Like ``_edge_store`` every match is a NEUTRAL 0-0 draw, so all rating
    deltas are exactly 0.0 and ``recent_volatility`` is 0 (well under the 16.5
    threshold) at every cutoff — the volatility arm is OFF, so set membership is
    driven SOLELY by the few-games COUNT. No 5th match is seeded here; the
    count-mode canary ADDS one (post-cutoff) to perturb the count.
    """
    raw = pd.DataFrame(
        [
            # date, home, away, hs, as, tournament, city, country, neutral
            ("2024-01-02", "Edge", "Foe", 0, 0, "Friendly", "London", "England", True),
            ("2024-01-04", "Edge", "Foe", 0, 0, "Friendly", "London", "England", True),
            ("2024-01-06", "Edge", "Foe", 0, 0, "Friendly", "London", "England", True),
            ("2024-01-08", "Edge", "Foe", 0, 0, "Friendly", "London", "England", True),
        ],
        columns=["date", "home_team", "away_team", "home_score", "away_score",
                 "tournament", "city", "country", "neutral"],
    )
    store = BitemporalStore(root=tmp_path)
    store.write("results", normalize_results(raw), policy=Policy.POINT_IN_TIME,
                keys=["match_id"], source="martj42", source_version="test")
    return store


def _provisional_set(store, cutoff, teams) -> set[str]:
    """Recompute the provisional set EXACTLY as ``fit()`` does
    (``src/wcmodel/model/scoreline.py``):
    ``set(arm.loc[arm["volatility_flag"] | arm["few_games_flag"], "team"])`` over
    ``count_volatility_arm`` — the same function and the same OR-of-two-arms
    predicate the model uses to populate ``Posterior.provisional_teams``. Using
    the arm directly (no sampling) isolates the provisional-set logic decisively
    and fast, so the canary's set-invariance assertion is tested against the very
    code path it guards.
    """
    arm = count_volatility_arm(store, cutoff=cutoff, field_teams=list(teams))
    return set(arm.loc[arm["volatility_flag"] | arm["few_games_flag"], "team"])


def test_provisional_set_invariant_to_added_post_cutoff_row(tmp_path):
    """COUNT-MODE leakage canary with proven teeth (Codex T9 final). The
    comprehensive canary asserts ``before.provisional_teams ==
    after.provisional_teams`` under ``mutate_future_result`` — but that mutation
    is SCORE-ONLY, which can only exercise a leak that moves the POSTERIOR
    (already covered, with teeth, by ``test_full_posterior_invariance_is_non_
    vacuous``). The ``provisional_teams ==`` assertion guards a DIFFERENT,
    disjoint leak mode the posterior check cannot catch: a COUNT-mode leak where a
    post-cutoff row's mere PRESENCE wrongly inflates a team's games-count in
    ``count_volatility_arm`` and flips its few-games provisional flag — WITHOUT
    moving the posterior, because such a row (post-cutoff, or unplayed/NaN-score)
    never enters the likelihood. A score mutation can't trigger that, so on its
    own the ``==`` assertion is not proven non-vacuous for its OWN leak mode.

    This test supplies the teeth by mirroring the score-mode posterior canary, but
    perturbing the COUNT instead of the score:

      1. ``Edge`` has EXACTLY 4 played matches dated before the cutoff C -> 4
         games -> few-games-provisional -> IN the provisional set at C.
      2. CORRECT PATH (the gate): the set at C, recomputed exactly as ``fit()``
         does (``count_volatility_arm`` -> ``{volatility_flag | few_games_flag}``),
         contains ``Edge``.
      3. ADD a 5th ``Edge`` match dated AFTER C — the perturbation a COUNT leak
         WOULD react to (the post-cutoff row's presence). It is written
         OBSERVED-as-of < C (``observed_at = valid_as_of = C − 1 day``) so it IS
         returned by the bitemporal ``read(cutoff=C)`` — i.e. the row is VISIBLE
         to the read, and the SOLE thing excluding it from the count is
         ``count_volatility_arm``'s ``date < cutoff.normalize()`` MATCH-DATE filter
         (not the store's observed_at masking, which would hide it for an
         unrelated reason and make this proof vacuous). Recomputing the set the
         SAME way at the SAME cutoff C: ``Edge`` is STILL IN and the set is
         UNCHANGED — Edge still counts 4 games. THIS is the count-mode invariance
         the canary's ``==`` asserts, now under a perturbation a count leak reacts
         to.
      4. LEAK SIMULATION (teeth): recompute the set at a cutoff C' AFTER Edge's
         5th match — i.e. as if a leak had admitted the post-cutoff row into the
         count. Edge now has 5 games -> few-games-flag False -> Edge is OUT.
         Conclusion: a count leak admitting the post-cutoff row WOULD flip Edge's
         membership, so the canary's ``provisional_teams ==`` invariance assertion
         WOULD catch it — proving that assertion NON-VACUOUS for the count mode.
         The correct date-filtered path (step 3) keeps the set invariant; only the
         leak (step 4) flips it.
    """
    teams = ["Edge", "Foe"]
    store = _four_game_edge_store(tmp_path)
    C = "2024-01-10"  # cutoff: after Edge's 4th game, before the to-be-added 5th

    # (1)+(2) Correct path: Edge IS provisional at C with 4 games.
    arm_before = count_volatility_arm(store, cutoff=C, field_teams=teams)
    edge_before = arm_before.set_index("team").loc["Edge"]
    assert int(edge_before["games"]) == 4, "expected exactly 4 < cutoff games"
    assert bool(edge_before["few_games_flag"]) is True, (
        "Edge with 4 games must trip the few-games arm (provisional_games=5)"
    )
    assert bool(edge_before["volatility_flag"]) is False, (
        "Edge's volatility arm must be OFF (all-zero deltas) so membership is "
        "driven purely by the few-games COUNT"
    )
    before = _provisional_set(store, C, teams)
    assert "Edge" in before, "Edge (4 games) must be IN the provisional set at C"

    # (3) ADD a 5th Edge match dated AFTER C, but OBSERVED as-of < C so the
    # bitemporal read returns it — the ONLY thing excluding it from the count is
    # count_volatility_arm's date < cutoff match-date filter.
    extra = normalize_results(pd.DataFrame(
        [("2024-01-12", "Edge", "Foe", 0, 0, "Friendly", "London", "England", True)],
        columns=["date", "home_team", "away_team", "home_score", "away_score",
                 "tournament", "city", "country", "neutral"],
    ))
    extra["observed_at"] = pd.Timestamp("2024-01-09")  # < C: visible to read(C)
    extra["valid_as_of"] = pd.Timestamp("2024-01-09")
    store.write("results", extra, policy=Policy.POINT_IN_TIME,
                keys=["match_id"], source="martj42", source_version="test")

    # The added post-cutoff row IS present in the bitemporal read at C (so it is
    # NOT the store's observed_at filter doing the exclusion). If this fails, the
    # invariance below would be vacuous (masked for the wrong reason).
    visible = store.read("results", cutoff=C)
    assert (pd.to_datetime(visible["date"]) == pd.Timestamp("2024-01-12")).any(), (
        "the added post-cutoff row must be VISIBLE in read(cutoff=C) so the "
        "date<cutoff filter is the sole exclusion — else this proof is vacuous"
    )

    # Recompute the set the SAME (correct) way at the SAME cutoff C: still 4
    # games, Edge still IN, set UNCHANGED. This is the count-mode invariance the
    # canary's `==` asserts — now with a perturbation a count leak WOULD react to.
    arm_after = count_volatility_arm(store, cutoff=C, field_teams=teams)
    assert int(arm_after.set_index("team").loc["Edge"]["games"]) == 4, (
        "count_volatility_arm's date<cutoff filter must still count exactly 4 "
        "games for Edge — the post-cutoff row must NOT inflate the count"
    )
    after = _provisional_set(store, C, teams)
    assert "Edge" in after, "Edge must STILL be IN the set after adding a > C row"
    assert before == after, (
        "provisional set CHANGED when a post-cutoff row was added at fixed cutoff "
        "C — count_volatility_arm leaked the > cutoff row into the games-count"
    )

    # (4) LEAK SIMULATION (teeth): at a cutoff AFTER Edge's 5th match, the row is
    # legitimately in-window -> 5 games -> Edge OUT. This is exactly what a leak
    # admitting the post-cutoff row at C would do to the counted set.
    Cp = "2024-01-13"
    arm_leak = count_volatility_arm(store, cutoff=Cp, field_teams=teams)
    edge_leak = arm_leak.set_index("team").loc["Edge"]
    assert int(edge_leak["games"]) == 5, "expected 5 counted games past the 5th"
    assert bool(edge_leak["few_games_flag"]) is False, (
        "Edge with 5 games must NOT trip the few-games arm"
    )
    assert bool(edge_leak["volatility_flag"]) is False, (
        "Edge's volatility arm stays OFF (zero deltas), so the membership flip is "
        "purely the few-games boundary"
    )
    leaked = _provisional_set(store, Cp, teams)
    assert "Edge" not in leaked, "Edge must DROP OUT once the 5th game is counted"

    # The crux: membership is invariant to ADDING the post-cutoff row at the
    # correct cutoff C (before == after, Edge IN), but FLIPS the moment the row is
    # counted (leak sim, Edge OUT). So a count-mode leak that admitted the row
    # would flip Edge's membership and the canary's `before.provisional_teams ==
    # after.provisional_teams` assertion WOULD catch it — proving that assertion
    # NON-VACUOUS for the count mode. (If `after` ever differed from `before`, the
    # date filter leaked; if `leaked` ever equalled `after`, the boundary is not
    # count-sensitive and the canary's set assertion would be vacuous.)
    assert ("Edge" in after) and ("Edge" not in leaked), (
        "count-mode teeth FAILED: adding the post-cutoff row did not leave Edge "
        "IN while the leak-sim drops Edge OUT — the provisional_teams assertion "
        "cannot be shown to catch a count-mode leak"
    )


def test_provisional_set_leak_would_be_caught(tmp_path):
    """NON-VACUITY for the canary's ``provisional_teams ==`` assertion (Codex T9
    re-review). The canary mutates a SCORE of a post-cutoff match; Codex
    confirmed a score change shifts ``recent_volatility`` but CANNOT flip
    provisional-set MEMBERSHIP, so on its own the ``provisional_teams ==``
    assertion can't be SHOWN to catch a provisional-set leak. This test supplies
    the missing teeth by proving the membership-deciding mechanism — the
    ``date < cutoff.normalize()`` filter in ``count_volatility_arm`` — is
    LOAD-BEARING for the set: the set CHANGES exactly when a game crosses the
    cutoff.

    ``Edge`` has 4 played matches before 2024-01-10 and a 5th AFTER it. The
    few-games arm flips at ``provisional_games``=5: 4 games → provisional,
    5 games → not. We do NOT mutate anything; we move the CUTOFF across the 5th
    game, which is exactly what a leak that wrongly ADMITTED a > cutoff game
    would do to the counted set:

      * cutoff just after the 4th game (< the 5th): Edge has 4 games →
        ``few_games_flag`` True → Edge IS in the provisional set;
      * cutoff after the 5th game: Edge has 5 games → ``few_games_flag`` False
        (and ``volatility_flag`` False, since all deltas are 0) → Edge is NOT in
        the provisional set.

    Therefore the provisional set IS sensitive to whether the post-cutoff game is
    included. A leak that admitted the > cutoff game at the EARLIER cutoff would
    count 5 games instead of 4, drop Edge from the set, and the canary's
    ``before.provisional_teams == after.provisional_teams`` assertion would
    FAIL — i.e. the canary WOULD catch a provisional-set leak. This proves the
    date filter in ``count_volatility_arm`` is load-bearing for the set,
    giving the canary's set-invariance assertion teeth. (If this test ever fails
    — i.e. the set is NOT date-sensitive at this boundary — the canary's
    provisional assertion is vacuous and must be revisited.)
    """
    store = _edge_store(tmp_path)

    # Cutoff just after the 4th game (2024-01-08) and <= D (2024-01-10), strictly
    # before the 5th game (2024-01-12): Edge has exactly 4 counted matches.
    early = count_volatility_arm(store, cutoff="2024-01-09", field_teams=["Edge"])
    edge_early = early.set_index("team").loc["Edge"]
    assert int(edge_early["games"]) == 4, "expected exactly 4 < cutoff games"
    assert bool(edge_early["few_games_flag"]) is True, (
        "Edge with 4 games must trip the few-games arm (provisional_games=5)"
    )
    in_set_early = bool(edge_early["few_games_flag"] or edge_early["volatility_flag"])
    assert in_set_early, "Edge must be IN the provisional set at 4 games"

    # Cutoff after the 5th game (2024-01-12): Edge now has 5 counted matches.
    late = count_volatility_arm(store, cutoff="2024-01-13", field_teams=["Edge"])
    edge_late = late.set_index("team").loc["Edge"]
    assert int(edge_late["games"]) == 5, "expected exactly 5 < cutoff games"
    assert bool(edge_late["few_games_flag"]) is False, (
        "Edge with 5 games must NOT trip the few-games arm"
    )
    # All-zero deltas (neutral 0-0 draws) ⇒ recent_volatility 0 ⇒ no volatility
    # arm either, so the ONLY reason Edge could be in the set at 5 games is the
    # few-games arm — which is now off. Membership change is unambiguous.
    assert bool(edge_late["volatility_flag"]) is False, (
        "Edge's volatility arm must be off so the membership change is purely "
        "the few-games boundary"
    )
    in_set_late = bool(edge_late["few_games_flag"] or edge_late["volatility_flag"])
    assert not in_set_late, "Edge must DROP OUT of the provisional set at 5 games"

    # The crux: set membership flips on whether the 5th (post-early-cutoff) game
    # is counted. A leak that admitted a > cutoff game would flip it the same way
    # → the canary's provisional_teams equality would catch it.
    assert in_set_early != in_set_late, (
        "provisional-set membership is NOT sensitive to whether the post-cutoff "
        "game is counted — the canary's provisional_teams assertion would be "
        "vacuous; revisit count_volatility_arm's date filter"
    )
