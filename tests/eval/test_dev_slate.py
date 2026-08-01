"""The FROZEN development-slate rule (OA Plan 2 v2, V0 / Codex finding 9).

The rule is frozen BEFORE any coverage inspection, verbatim:

    "every completed senior men's international in the probed competitions with
     kickoff in [2022-01-01, 2025-12-31], excluding any fixture in the scored
     pools' windows, ordered chronologically, truncated to the first N_dev with
     admissible coverage."

Competition KEYS are an evidence choice (the --slate mini-probe, then G-B);
fixture SELECTION within them is this rule and nothing else. These tests pin
every clause of it plus the config block that carries it, so a later hand-edit
that quietly reorders, re-windows or re-truncates the slate fails here.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import yaml

from wcmodel.eval.dev_slate import (
    DEV_WINDOW,
    SCORED_POOL_WINDOWS,
    THE_RULE,
    DevSlateError,
    eligible_dev_fixtures,
    load_dev_slate_config,
    truncate_to_n_dev,
)

_ROOT = Path(__file__).resolve().parents[2]


def _frame(rows) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=["match_id", "date", "home_team", "away_team",
                 "home_score", "away_score", "tournament"])


def _row(mid, day, tournament="UEFA Nations League", home="A", away="B",
         hs=1, aw=0):
    return [mid, day, home, away, hs, aw, tournament]


_COMPS = ("UEFA Nations League",)


# --------------------------------------------------------------------------- #
# The rule text and its parameters are FROZEN — pinned literally.               #
# --------------------------------------------------------------------------- #
def test_rule_text_is_frozen_verbatim():
    # 2026-08-01 pre-lock rule correction (plan2 batch-1 finding 9, Codex
    # RATIFIED): "excluding any fixture in the scored pools' windows" became
    # exact scored-fixture MEMBERSHIP — the euro2024 calendar window
    # blanketed Copa America 2024, killing an entire eligible development
    # competition that shares not one fixture with the scored pools.
    assert THE_RULE == (
        "every completed senior men's international in the probed "
        "competitions with kickoff in [2022-01-01, 2025-12-31], excluding "
        "every fixture in the frozen scored inventory (exact scored-fixture "
        "membership by canonical fixture identity, "
        "config/oa_scored_inventory.yaml), ordered chronologically, "
        "truncated to the first N_dev with admissible coverage")


def test_window_and_scored_pool_windows_are_frozen():
    assert DEV_WINDOW == (date(2022, 1, 1), date(2025, 12, 31))
    assert SCORED_POOL_WINDOWS == (
        ("wc2022", date(2022, 11, 20), date(2022, 12, 18)),
        ("euro2024", date(2024, 6, 14), date(2024, 7, 14)),
        ("wc2026", date(2026, 6, 11), date(2026, 7, 19)),
    )


def test_config_block_carries_the_same_rule_and_parameters():
    # The config comment is the human-readable freeze; the code constants are
    # the machine one. They must not drift apart.
    cfg = load_dev_slate_config()
    assert cfg["window"] == {"start": "2022-01-01", "end": "2025-12-31"}
    # 2026-08-01 USER RULING at the G-B spend gate: the four competitions
    # the slate probe verified covered WITH Pinnacle, n_dev 300 — set by
    # coverage EVIDENCE (reports/oa_slate_probe.md), exactly the flow the
    # empty-until-probed freeze demanded.
    assert cfg["competitions"] == [
        "Copa América", "African Cup of Nations", "UEFA Nations League",
        "FIFA World Cup qualification"]
    assert cfg["n_dev"] == 260   # 2026-08-01 amendment: supply limit
    # The acquisition scope maps each competition to its PROBED key; the
    # WCQ participants filter bounds SPEND to the CONMEBOL evidence, never
    # selection.
    keys = cfg["acquisition"]["sport_keys"]
    assert set(keys) == set(cfg["competitions"])
    assert keys["FIFA World Cup qualification"] == \
        "soccer_fifa_world_cup_qualifiers_south_america"
    assert len(cfg["acquisition"]["participants"]
               ["FIFA World Cup qualification"]) == 10
    # The rule is quoted VERBATIM in the config comment. Comment markers and
    # line wrapping are stripped so the check is on the words, not the layout.
    raw = (_ROOT / "config" / "config.yaml").read_text().replace("#", " ")
    assert THE_RULE in " ".join(raw.split())


# --------------------------------------------------------------------------- #
# Clause by clause.                                                             #
# --------------------------------------------------------------------------- #
def test_keeps_only_the_probed_competitions():
    df = _frame([_row("a", "2023-03-23", "UEFA Nations League"),
                 _row("b", "2023-03-23", "Friendly")])
    assert list(eligible_dev_fixtures(df, competitions=_COMPS)["match_id"]) == ["a"]


def test_window_is_inclusive_on_both_ends_and_excludes_outside():
    df = _frame([_row("early", "2021-12-31"), _row("open", "2022-01-01"),
                 _row("close", "2025-12-31"), _row("late", "2026-01-01")])
    got = list(eligible_dev_fixtures(df, competitions=_COMPS)["match_id"])
    assert got == ["open", "close"]


def test_scored_exclusion_is_exact_membership_not_calendar_windows():
    # THE RATIFIED AMENDMENT (finding 9): Copa America 2024 ran entirely
    # inside the euro2024 calendar window yet shares not one fixture with
    # the scored pools — a date-window exclusion killed the whole
    # competition. Exact scored-fixture membership keeps it.
    df = _frame([_row("copa1", "2024-06-22", "Copa América"),
                 _row("copa2", "2024-07-06", "Copa América")])
    got = list(eligible_dev_fixtures(
        df, competitions=("Copa América",))["match_id"])
    assert got == ["copa1", "copa2"]


def test_scored_ids_are_excluded_by_identity():
    df = _frame([_row("a", "2023-03-23"), _row("b", "2023-03-24")])
    got = list(eligible_dev_fixtures(df, competitions=_COMPS,
                                     scored_ids={"a"})["match_id"])
    assert got == ["b"]


def test_default_exclusion_uses_the_committed_inventory():
    from wcmodel.eval.dev_slate import load_scored_inventory

    scored = load_scored_inventory()["fixtures"][0]["match_id"]
    # Identity beats every other filter: a scored fixture is excluded even
    # when its row wears a dev competition's label on a dev-window date.
    df = _frame([_row(scored, "2023-03-23"), _row("ok", "2023-03-24")])
    got = list(eligible_dev_fixtures(df, competitions=_COMPS)["match_id"])
    assert got == ["ok"]


def test_scored_inventory_artifact_is_frozen_and_complete():
    # The committed artifact: 217 odds-scored fixtures = the bk harness's
    # 185-pool (windows/labels verbatim) + the 32 WC-2026 knockouts. Its
    # identity set is what the dev slate excludes; Copa America appears
    # NOWHERE in it — the amendment's whole point.
    doc = yaml.safe_load(
        (_ROOT / "config" / "oa_scored_inventory.yaml").read_text())
    fixtures = doc["fixtures"]
    assert len(fixtures) == 217
    ids = [f["match_id"] for f in fixtures]
    assert len(set(ids)) == 217
    pools = {}
    for f in fixtures:
        pools[f["pool"]] = pools.get(f["pool"], 0) + 1
    assert pools == {"wc2022": 63, "euro2024": 50, "wc2026": 104}
    assert all("copa" not in f["tournament"].lower() for f in fixtures)
    assert {f["tournament"] for f in fixtures} == {"FIFA World Cup",
                                                   "UEFA Euro"}


@pytest.mark.parametrize("hs,aw", [(None, 0), (0, None), (-1, 0), (1.5, 0)])
def test_uncompleted_or_malformed_scores_are_excluded(hs, aw):
    df = _frame([_row("bad", "2023-03-23", hs=hs, aw=aw),
                 _row("good", "2023-03-24")])
    got = list(eligible_dev_fixtures(df, competitions=_COMPS)["match_id"])
    assert got == ["good"]


def test_ordered_chronologically_with_a_deterministic_tie_break():
    # Same-day fixtures need a tie-break or the order depends on input order —
    # i.e. on whatever the store happened to hand us. match_id is a content
    # hash of fixture identity: arbitrary, but pre-committed and stable.
    rows = [_row("zzz", "2023-03-24"), _row("aaa", "2023-03-24"),
            _row("mmm", "2023-03-23")]
    ordered = list(eligible_dev_fixtures(_frame(rows),
                                         competitions=_COMPS)["match_id"])
    assert ordered == ["mmm", "aaa", "zzz"]
    shuffled = list(eligible_dev_fixtures(_frame(rows[::-1]),
                                          competitions=_COMPS)["match_id"])
    assert shuffled == ordered


def test_duplicate_match_ids_are_refused():
    df = _frame([_row("dup", "2023-03-23"), _row("dup", "2023-03-24")])
    with pytest.raises(DevSlateError) as exc:
        eligible_dev_fixtures(df, competitions=_COMPS)
    assert "duplicate" in str(exc.value)


def test_empty_competition_set_is_refused():
    # An empty set silently yields an empty slate, which would read as "no
    # coverage" rather than "you never chose the competitions".
    with pytest.raises(DevSlateError) as exc:
        eligible_dev_fixtures(_frame([_row("a", "2023-03-23")]),
                              competitions=())
    assert "competition" in str(exc.value)


# --------------------------------------------------------------------------- #
# Truncation — "the first N_dev WITH ADMISSIBLE COVERAGE".                       #
# --------------------------------------------------------------------------- #
def test_truncation_keeps_the_first_n_dev_admissible_in_rule_order():
    ordered = eligible_dev_fixtures(
        _frame([_row("a", "2023-03-21"), _row("b", "2023-03-22"),
                _row("c", "2023-03-23"), _row("d", "2023-03-24")]),
        competitions=_COMPS)
    got = truncate_to_n_dev(ordered, admissible={"a", "c", "d"}, n_dev=2)
    assert list(got["match_id"]) == ["a", "c"]


def test_truncation_refuses_when_too_few_are_admissible():
    # Silently returning a short slate would change N_dev after the fact —
    # the manifest is hash-bound into the V8 lock, so its size is a
    # pre-registered quantity, not a yield.
    ordered = eligible_dev_fixtures(_frame([_row("a", "2023-03-21")]),
                                    competitions=_COMPS)
    with pytest.raises(DevSlateError) as exc:
        truncate_to_n_dev(ordered, admissible={"a"}, n_dev=5)
    assert "1" in str(exc.value) and "5" in str(exc.value)


def test_truncation_refuses_admissible_ids_outside_the_ordered_slate():
    # An admissible id the rule never selected means the coverage input and
    # the slate disagree about which fixtures exist — never silently ignored.
    ordered = eligible_dev_fixtures(_frame([_row("a", "2023-03-21")]),
                                    competitions=_COMPS)
    with pytest.raises(DevSlateError) as exc:
        truncate_to_n_dev(ordered, admissible={"a", "ghost"}, n_dev=1)
    assert "ghost" in str(exc.value)


def test_truncation_refuses_scored_ids_at_select_time(monkeypatch):
    # dev_ids ∩ scored_ids = ∅ is asserted at manifest GENERATION and again
    # at SELECT time (the amendment): a hand-edited manifest smuggling a
    # scored fixture past the generator must still refuse here.
    ordered = _frame([_row("a", "2023-03-21"), _row("s", "2023-03-22")])
    ordered["date"] = pd.to_datetime(ordered["date"]).dt.date
    with pytest.raises(DevSlateError) as exc:
        truncate_to_n_dev(ordered, admissible={"a", "s"}, n_dev=1,
                          scored_ids={"s"})
    assert "scored" in str(exc.value)


# --------------------------------------------------------------------------- #
# The generator stub refuses to emit until the evidence exists.                  #
# --------------------------------------------------------------------------- #
def _load_generator():
    import importlib.util
    path = _ROOT / "scripts" / "oa_dev_manifest.py"
    spec = importlib.util.spec_from_file_location("oa_dev_manifest", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_generator_import_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _load_generator()
    assert list(tmp_path.rglob("*")) == []


def test_generator_refuses_to_emit_before_admissibility_evidence(tmp_path,
                                                                 monkeypatch,
                                                                 capsys):
    # Competitions and n_dev are now decided (2026-08-01 ruling), so the
    # remaining --emit blocker is the per-fixture coverage admissibility the
    # V4/G-B acquisition produces. The generator must still refuse — and for
    # THAT reason, not the already-satisfied ones.
    monkeypatch.chdir(tmp_path)
    mod = _load_generator()
    assert mod.main(["--emit"]) == 1
    err = capsys.readouterr().err
    assert "admissibility" in err
    assert "competitions" not in err and "n_dev" not in err
    assert not (tmp_path / "config" / "oa_dev_manifest.yaml").exists()


def test_generator_status_reports_the_frozen_rule(tmp_path, monkeypatch,
                                                  capsys):
    monkeypatch.chdir(tmp_path)
    mod = _load_generator()
    assert mod.main([]) == 0
    assert THE_RULE in capsys.readouterr().out


def test_generator_emits_the_manifest_once_the_inputs_exist(tmp_path,
                                                            monkeypatch):
    monkeypatch.chdir(tmp_path)
    mod = _load_generator()
    results = _frame([_row("a", "2023-03-21"), _row("b", "2023-03-22"),
                      _row("c", "2023-03-23")])
    out = tmp_path / "manifest.yaml"
    mod.emit_manifest(results, competitions=_COMPS,
                      admissible={"a", "b", "c"}, n_dev=2, out_path=out)
    doc = yaml.safe_load(out.read_text())
    assert doc["rule"] == THE_RULE
    assert doc["n_dev"] == 2 and doc["competitions"] == list(_COMPS)
    assert [f["match_id"] for f in doc["fixtures"]] == ["a", "b"]
    assert doc["fixtures"][0]["date"] == "2023-03-21"
