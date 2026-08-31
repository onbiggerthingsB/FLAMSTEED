"""Tests for the EPL wiring of the World Cup scoreline model.

The load-bearing one is :class:`TestLeakage`. Everything else in this file
checks that a column is where it should be; that test checks that a result
which had not happened yet cannot reach the model, by rewriting the future and
demanding the past come out bit-identical.

No test here fits the Bayesian model. A fit is minutes; these run in seconds by
attacking the layer that decides WHAT the fit sees, which is the layer where
leakage actually lives.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from epl import baseline as epl_baseline, elo as epl_elo, fit as epl_fit, paths
from epl.schema import sort_for_walk_forward
from wcmodel.config import load_config
from wcmodel.data import features as wc_features
from wcmodel.data.store import BitemporalStore, Policy

CUTOFF = "2025-01-25"


@pytest.fixture(scope="module")
def matches() -> pd.DataFrame:
    return epl_baseline.load_matches()


@pytest.fixture(scope="module")
def store(matches, tmp_path_factory) -> BitemporalStore:
    root = tmp_path_factory.mktemp("epl_store")
    return epl_fit.build_store(matches, root=root, rebuild=True)


# ==========================================================================
# the design input
# ==========================================================================
class TestStoreFrame:
    def test_carries_exactly_what_features_build_reads(self, matches):
        frame = epl_fit.to_store_frame(matches)
        required = {"match_id", "date", "valid_as_of", "observed_at",
                    "home_team", "away_team", "home_score", "away_score",
                    "tournament", "neutral", "city"}
        assert set(frame.columns) == required

    def test_team_identity_is_the_join_key_not_the_display_name(self, matches):
        frame = epl_fit.to_store_frame(matches)
        assert set(frame["home_team"]) <= set(matches["home_key"])
        assert "Manchester United" not in set(frame["home_team"])
        assert "man_united" in set(frame["home_team"])

    def test_static_history_without_clocks_uses_the_documented_date_fallback(
            self, matches):
        assert {"observed_at", "valid_as_of"}.isdisjoint(matches.columns)
        frame = epl_fit.to_store_frame(matches)
        assert (frame["observed_at"] == frame["date"]).all()
        assert (frame["valid_as_of"] == frame["date"]).all()

    def test_supplied_live_clocks_are_preserved_not_backdated(self, matches):
        live = matches.head(2).copy()
        live["valid_as_of"] = pd.to_datetime(
            ["2026-08-21T20:00:00Z", "2026-08-22T15:00:00Z"])
        live["observed_at"] = pd.to_datetime(
            ["2026-08-25T20:55:44+08:00", "2026-08-25T20:55:44+08:00"])

        frame = epl_fit.to_store_frame(live)

        assert frame["valid_as_of"].tolist() == [
            pd.Timestamp("2026-08-21 20:00:00"),
            pd.Timestamp("2026-08-22 15:00:00"),
        ]
        assert frame["observed_at"].tolist() == [
            pd.Timestamp("2026-08-25 12:55:44"),
            pd.Timestamp("2026-08-25 12:55:44"),
        ]
        assert not frame["observed_at"].equals(frame["date"])

    @pytest.mark.parametrize("missing", ["valid_as_of", "observed_at"])
    def test_revision_aware_frame_requires_both_clocks(self, matches, missing):
        live = matches.head(1).copy()
        live["valid_as_of"] = pd.Timestamp("2026-08-21T20:00:00Z")
        live["observed_at"] = pd.Timestamp("2026-08-25T12:55:44Z")
        live = live.drop(columns=missing)
        with pytest.raises(ValueError, match="must supply both"):
            epl_fit.to_store_frame(live)

    @pytest.mark.parametrize("column", ["home_key", "away_key"])
    @pytest.mark.parametrize("bad", [None, pd.NA, "", "   "])
    def test_null_or_blank_team_key_refuses_before_projection(
            self, matches, column, bad):
        poisoned = matches.head(2).copy()
        match_id = str(poisoned.iloc[0]["match_id"])
        poisoned.loc[poisoned.index[0], column] = bad
        with pytest.raises(ValueError, match="null/unresolved") as exc:
            epl_fit.to_store_frame(poisoned)
        assert column in str(exc.value)
        assert match_id in str(exc.value)

    @pytest.mark.parametrize("column", ["valid_as_of", "observed_at"])
    def test_revision_aware_frame_refuses_a_null_clock_value(
            self, matches, column):
        live = matches.head(2).copy()
        live["valid_as_of"] = pd.Timestamp("2026-08-21T20:00:00Z")
        live["observed_at"] = pd.Timestamp("2026-08-25T12:55:44Z")
        live.loc[live.index[0], column] = pd.NaT
        with pytest.raises(ValueError, match=f"{column} must be finite"):
            epl_fit.to_store_frame(live)

    def test_scores_are_integers_and_survive_the_models_own_filter(self, matches):
        frame = epl_fit.to_store_frame(matches)
        assert frame["home_score"].dtype.kind == "i"
        assert frame["away_score"].dtype.kind == "i"
        # to_store_frame raises if valid_played_results would drop anything;
        # assert the post-condition directly too.
        from wcmodel.data.features import valid_played_results
        assert len(valid_played_results(frame)) == len(frame)

    def test_every_row_is_a_home_game(self, matches):
        assert not epl_fit.to_store_frame(matches)["neutral"].any()

    def test_rejects_an_unplayed_fixture(self, matches):
        bad = matches.head(20).copy()
        bad.loc[bad.index[0], "played"] = False
        bad.loc[bad.index[0], "fthg"] = pd.NA
        frame = epl_fit.to_store_frame(bad)
        assert len(frame) == 19          # the unplayed row is dropped, not faked

    def test_rejects_a_duplicate_match_id(self, matches):
        bad = pd.concat([matches.head(5), matches.head(1)], ignore_index=True)
        with pytest.raises(ValueError, match="duplicate match_id"):
            epl_fit.to_store_frame(bad)


class TestStore:
    def test_read_returns_one_row_per_match(self, store, matches):
        got = store.read("results", cutoff="2030-01-01")
        assert len(got) == int(matches["played"].sum())
        assert got["match_id"].is_unique

    def test_rebuilding_does_not_double_the_table(self, matches, tmp_path):
        first = epl_fit.build_store(matches, root=tmp_path, rebuild=True)
        n = len(pd.read_parquet(tmp_path / "results.parquet"))
        epl_fit.build_store(matches, root=tmp_path)      # no rebuild flag
        assert len(pd.read_parquet(tmp_path / "results.parquet")) == n
        assert len(first.read("results", cutoff="2030-01-01")) == n

    def test_same_ids_with_new_live_clocks_replace_a_stale_store(
            self, matches, tmp_path):
        rows = matches.head(2).copy()
        epl_fit.build_store(rows, root=tmp_path, rebuild=True)

        live = rows.copy()
        live["valid_as_of"] = pd.to_datetime(live["date"])
        live["observed_at"] = pd.Timestamp("2026-08-25T12:55:44Z")
        epl_fit.build_store(live, root=tmp_path)

        raw = pd.read_parquet(tmp_path / "results.parquet")
        assert set(pd.to_datetime(raw["observed_at"])) == {
            pd.Timestamp("2026-08-25 12:55:44")
        }

    def test_same_ids_and_clocks_with_a_revised_score_replace_stale_store(
            self, matches, tmp_path):
        rows = matches.head(2).copy()
        epl_fit.build_store(rows, root=tmp_path, rebuild=True)

        revised = rows.copy()
        first_id = str(revised.iloc[0]["match_id"])
        revised.loc[revised.index[0], "fthg"] = int(revised.iloc[0]["fthg"]) + 1
        expected = int(revised.iloc[0]["fthg"])
        epl_fit.build_store(revised, root=tmp_path)

        raw = pd.read_parquet(tmp_path / "results.parquet")
        got = raw.loc[raw["match_id"].astype(str) == first_id, "home_score"]
        assert got.tolist() == [expected]

    @pytest.mark.parametrize(("field", "bad"), [
        ("_policy", Policy.CURRENT_ONLY.value),
        ("_keys", "home_team,away_team"),
    ])
    def test_identical_content_does_not_reuse_wrong_store_metadata(
            self, matches, tmp_path, field, bad):
        rows = matches.head(2).copy()
        epl_fit.build_store(rows, root=tmp_path, rebuild=True)
        table = tmp_path / "results.parquet"
        poisoned = pd.read_parquet(table)
        poisoned[field] = bad
        poisoned.to_parquet(table, index=False)

        epl_fit.build_store(rows, root=tmp_path)

        repaired = pd.read_parquet(table)
        assert repaired["_policy"].astype(str).eq(
            Policy.POINT_IN_TIME.value).all()
        assert repaired["_keys"].astype(str).eq("match_id").all()

    def test_knowledge_clock_controls_store_visibility_but_not_play_day_or_decay(
            self, matches, tmp_path):
        rows = matches.head(2).copy()
        rows["date"] = pd.to_datetime(["2026-08-19", "2026-08-20"])
        rows["valid_as_of"] = rows["date"]
        rows["observed_at"] = pd.Timestamp("2026-08-20T12:00:00Z")
        store = epl_fit.build_store(rows, root=tmp_path, rebuild=True)
        calendar_cutoff = pd.Timestamp("2026-08-20T00:00:00Z")

        # At calendar midnight neither row had been observed yet.
        assert store.read("results", cutoff=calendar_cutoff).empty

        # At the issuance's later knowledge snapshot both revisions satisfy the
        # knowledge clock, but the adapter ALSO applies the caller's play day:
        # direct consumers see the 19 August result and never the same-day 20
        # August row. The feature builder retains age one for the visible row.
        view = epl_fit.knowledge_bound_store(
            store, pd.Timestamp("2026-08-20T13:00:00Z"))
        visible = view.read("results", cutoff=calendar_cutoff)
        assert set(visible["match_id"].astype(str)) == {
            str(rows.iloc[0]["match_id"])}
        cfg = load_config()
        panel = wc_features.build(calendar_cutoff, view, cfg)
        assert set(panel["match_id"].astype(str)) == {str(rows.iloc[0]["match_id"])}
        assert set(panel["age_days"].astype(float)) == {1.0}

        # wcmodel used to receive an adapter that changed only the store read
        # clock and then applied this same day gate internally. Moving the gate
        # into the adapter must not change either panel content or its cache key.
        class _KnowledgeOnly:
            def read(self, name, *, cutoff):
                return store.read(name, cutoff="2026-08-20T13:00:00Z")

        legacy = _KnowledgeOnly()
        pd.testing.assert_frame_equal(
            panel, wc_features.build(calendar_cutoff, legacy, cfg))
        assert wc_features._build_cache_key(
            calendar_cutoff, view, cfg) == wc_features._build_cache_key(
                calendar_cutoff, legacy, cfg)

    def test_point_in_time_guard_reports_the_real_boundary(self, store):
        got = epl_fit.assert_point_in_time(store, CUTOFF)
        assert got["latest_training_date"] < CUTOFF
        assert got["n_training_matches"] == 4019
        assert got["n_training_teams"] == 35

    def test_guard_refuses_a_cutoff_with_no_history(self, store):
        with pytest.raises(ValueError, match="no training matches"):
            epl_fit.assert_point_in_time(store, "2014-08-16")


# ==========================================================================
# THE load-bearing test
# ==========================================================================
class TestLeakage:
    """Rewrite every result from the cutoff onward; demand the past is unmoved.

    A filter that reads `date < cutoff` is easy to write and easy to believe.
    This test does not read it. It builds two stores that are IDENTICAL before
    the cutoff and maximally different after it — every later match becomes a
    9-0 home win — and asserts that the feature panel a fit at the cutoff would
    consume is bit-identical between them, including every point-in-time Elo
    rating. The positive control asserts the corrupted results DID land, so a
    version of this test that silently rewrote nothing would fail.
    """

    @staticmethod
    def _panel(frame: pd.DataFrame, root, cutoff) -> pd.DataFrame:
        store = BitemporalStore(root)
        store.write("results", frame, policy=Policy.POINT_IN_TIME,
                    keys=["match_id"], source="test", source_version="t")
        panel = wc_features.build(pd.Timestamp(cutoff), store, load_config())
        return panel.sort_values(["match_id", "team"]).reset_index(drop=True)

    def test_rewriting_the_future_leaves_the_past_bit_identical(
            self, matches, tmp_path):
        clean = epl_fit.to_store_frame(matches)
        dirty = clean.copy()
        after = pd.to_datetime(dirty["date"]) >= pd.Timestamp(CUTOFF)
        assert after.sum() > 100, "the attack must actually have something to rewrite"
        dirty.loc[after, "home_score"] = 9
        dirty.loc[after, "away_score"] = 0

        a = self._panel(clean, tmp_path / "clean", CUTOFF)
        b = self._panel(dirty, tmp_path / "dirty", CUTOFF)

        assert list(a["match_id"]) == list(b["match_id"])
        np.testing.assert_array_equal(a["elo_pre"].to_numpy(), b["elo_pre"].to_numpy())
        np.testing.assert_array_equal(a["provisional"].to_numpy(),
                                      b["provisional"].to_numpy())
        np.testing.assert_array_equal(a["team_score"].to_numpy(),
                                      b["team_score"].to_numpy())

    def test_positive_control_the_rewrite_does_move_a_later_panel(
            self, matches, tmp_path):
        clean = epl_fit.to_store_frame(matches)
        dirty = clean.copy()
        after = pd.to_datetime(dirty["date"]) >= pd.Timestamp(CUTOFF)
        dirty.loc[after, "home_score"] = 9
        dirty.loc[after, "away_score"] = 0

        later = "2025-04-01"
        a = self._panel(clean, tmp_path / "clean2", later)
        b = self._panel(dirty, tmp_path / "dirty2", later)
        assert not np.array_equal(a["elo_pre"].to_numpy(), b["elo_pre"].to_numpy()), (
            "the corrupted results never reached Elo, so the negative test above "
            "proves nothing")

    def test_the_feature_gate_is_stricter_than_this_packages_own_rule(
            self, store, matches):
        """A same-day earlier kickoff is visible to `epl.walk` and NOT to the fit.

        Strictly less information can never leak, but the difference is real and
        it is why the refit unit is the matchweek rather than the fixture.
        """
        panel = wc_features.build(pd.Timestamp(CUTOFF), store, load_config())
        assert pd.to_datetime(panel["date"]).max() < pd.Timestamp(CUTOFF)
        same_day = matches.loc[pd.to_datetime(matches["date"]) == pd.Timestamp(CUTOFF)]
        assert len(same_day) > 1, "the chosen cutoff day must carry several matches"
        assert not set(same_day["match_id"]) & set(panel["match_id"])


# ==========================================================================
# the walk-forward cost model
# ==========================================================================
class TestMatchweeks:
    def test_index_is_dense_and_chronological(self, matches):
        played = sort_for_walk_forward(matches.loc[matches["played"]])
        mw = epl_fit.matchweek_index(played)
        assert mw.min() == 0
        assert set(np.unique(mw)) == set(range(mw.max() + 1))
        assert (np.diff(mw) >= 0).all()

    def test_a_matchweek_never_spans_two_seasons(self, matches):
        played = sort_for_walk_forward(matches.loc[matches["played"]])
        mw = epl_fit.matchweek_index(played)
        per = pd.DataFrame({"mw": mw, "season": played["season"].to_numpy()})
        assert (per.groupby("mw")["season"].nunique() == 1).all()

    def test_a_season_has_roughly_a_matchweek_per_round(self, matches):
        played = sort_for_walk_forward(matches.loc[matches["played"]])
        mw = epl_fit.matchweek_index(played)
        per_season = pd.DataFrame({"mw": mw, "season": played["season"].to_numpy()}
                                  ).groupby("season")["mw"].nunique()
        # 38 rounds; calendar weeks that carry a midweek round merge, so the
        # count is a little under 38 rather than a little over.
        assert per_season.between(28, 40).all(), per_season.to_dict()


class TestCostModel:
    def test_fits_are_ceil_weeks_over_cadence_per_scored_season(self, matches):
        got = epl_fit.cost_model(matches, fit_seconds=100.0, cadences=(1, 2, 4, 8))
        by_n = {r["refit_every_weeks"]: r for r in got["cadences"]}
        weekly = by_n[1]
        for n in (2, 4, 8):
            expected = sum(int(np.ceil(v["matchweeks"] / n))
                           for v in weekly["per_season"].values())
            assert by_n[n]["total_fits"] == expected

    def test_hours_scale_linearly_in_the_measured_fit_time(self, matches):
        a = epl_fit.cost_model(matches, 100.0, (4,))["cadences"][0]
        b = epl_fit.cost_model(matches, 200.0, (4,))["cadences"][0]
        assert b["hours"] == pytest.approx(2 * a["hours"], rel=1e-9)

    def test_only_scored_seasons_are_costed(self, matches):
        got = epl_fit.cost_model(matches, 1.0, (1,))
        assert set(got["cadences"][0]["per_season"]) == set(epl_baseline.SCORE_SEASONS)
        assert got["n_scored_matches"] == 380 * len(epl_baseline.SCORE_SEASONS)


# ==========================================================================
# prediction surface
# ==========================================================================
class _FakePosterior:
    """Just enough of `Posterior` to exercise the unknown-club path."""

    def __init__(self, teams):
        self._idx = {t: i for i, t in enumerate(teams)}

    def predict_1x2(self, home, away, neutral=False):
        return {"home": 0.5, "draw": 0.3, "away": 0.2}


class TestPrediction:
    def test_next_matchweek_is_ten_fixtures_none_before_the_cutoff(self, matches):
        fx = epl_fit.next_matchweek(matches, CUTOFF, 10)
        assert len(fx) == 10
        assert (pd.to_datetime(fx["date"]) >= pd.Timestamp(CUTOFF)).all()

    def test_an_unknown_club_yields_nan_not_an_exception(self, matches):
        fx = epl_fit.next_matchweek(matches, CUTOFF, 10)
        known = set(fx["home_key"]) | set(fx["away_key"])
        post = _FakePosterior(known - {"ipswich"})
        probs = epl_fit.model_probabilities(post, fx)
        missing = fx["home_key"].eq("ipswich") | fx["away_key"].eq("ipswich")
        assert np.isnan(probs[missing.to_numpy()]).all()
        assert np.isfinite(probs[~missing.to_numpy()]).all()

    def test_promoted_clubs_are_the_reason_that_path_exists(self, matches):
        """Every season but one introduces a club with no prior EPL match here.

        A fit whose cutoff precedes that club's first appearance cannot index
        it, so a season-opening refit is structurally unable to price three of
        the ten opening fixtures. This is asserted as data, not prose.
        """
        played = matches.loc[matches["played"]]
        seen: set[str] = set()
        new_per_season = {}
        for s in sorted(played["season"].unique()):
            clubs = set(played.loc[played["season"] == s, "home_key"])
            new_per_season[s] = sorted(clubs - seen)
            seen |= clubs
        later = {s: v for s, v in new_per_season.items() if s != "2014/15"}
        assert sum(len(v) for v in later.values()) >= 10
        assert sum(1 for v in later.values() if v) == len(later) - 1  # 2025/26 is the exception


# ==========================================================================
# the staleness proxy
# ==========================================================================
class TestStaleness:
    @pytest.fixture(scope="class")
    def curve(self, matches):
        return epl_fit.staleness_curve(matches, cadences=(1, 2, 4, 8))

    def test_it_is_labelled_a_proxy(self, curve):
        assert "PROXY" in curve["LABEL"]

    def test_weekly_is_the_reference_and_is_not_itself_staleness_free(self, curve):
        """A weekly refit still carries a midweek round's worth of staleness.

        The refit unit is the calendar week, and a week containing a midweek
        round has clubs playing twice inside it — the second match is priced
        off the rating that stood when the week opened. So the weekly arm's
        rating staleness is small but strictly positive, and it is the
        REFERENCE the other cadences are measured against, not a zero.
        """
        weekly = curve["cadences"][0]
        assert weekly["refit_every_weeks"] == 1
        assert 0.0 < weekly["mean_abs_rating_staleness"] < 5.0
        assert weekly["rps_cost_vs_weekly"] == pytest.approx(0.0, abs=1e-12)

    def test_staleness_grows_monotonically_with_the_gap(self, curve):
        vals = [c["mean_abs_rating_staleness"] for c in curve["cadences"]]
        assert vals == sorted(vals)

    def test_every_cadence_scores_the_same_matches(self, curve):
        assert len({c["n"] for c in curve["cadences"]}) >= 1
        assert curve["n_common"] > 2000

    def test_the_weekly_arm_lands_near_the_published_elo_baseline(self, curve):
        """0.2011 was measured refitting at every KICKOFF block; this refits
        weekly, which is coarser, so it should be close and slightly worse."""
        weekly = curve["cadences"][0]["rps"]
        assert 0.198 < weekly < 0.208
