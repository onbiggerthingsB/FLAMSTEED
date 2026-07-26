import copy
import pytest

from wcmodel.data.tournament import (HOST_COUNTRY_BY_TEAM, load_tournament,
                                     tournament_format, validate_tournament)

_REAL = "config/tournament_2026.yaml"

AC_FORMAT = {"n_groups": 6, "teams_per_group": 4, "per_group_advance": 2,
             "best_thirds": 4, "third_place_match": False,
             "tiebreak_order": "afc_2027",
             "assignment_table": "third_place_assignment_ac2027.json",
             "competition_name": "AFC Asian Cup", "source_tag": "ac2027_schedule",
             "hosts": {"Saudi Arabia": "SA"}, "ko_host_advantage": True}


def _ac_min():
    """Minimal valid AC-2027-shaped dict: 36 group fixtures + 15 KO (no 3rd-place)."""
    letters = "ABCDEF"
    groups = [{"name": g, "teams": [f"Team{g}{i}" for i in range(4)]}
              for g in letters]
    teams = [t for g in groups for t in g["teams"]]
    fixtures = []
    for g in letters:
        t = [f"Team{g}{i}" for i in range(4)]
        for a, b in [(0, 1), (2, 3), (0, 2), (1, 3), (0, 3), (1, 2)]:
            fixtures.append({"home": t[a], "away": t[b], "date": "2027-01-08",
                             "group": g, "round": "Matchday", "venue": "Riyadh"})
    ko = ([(49, "1A", "3rd-CDE", "Round of 16"), (50, "1B", "3rd-ADF", "Round of 16"),
           (51, "1C", "3rd-ABF", "Round of 16"), (52, "1D", "3rd-ABC", "Round of 16"),
           (53, "2A", "2C", "Round of 16"), (54, "1E", "2D", "Round of 16"),
           (55, "1F", "2B", "Round of 16"), (56, "2E", "2F", "Round of 16"),
           (57, "W49", "W53", "Quarter-final"), (58, "W50", "W54", "Quarter-final"),
           (59, "W51", "W55", "Quarter-final"), (60, "W52", "W56", "Quarter-final"),
           (61, "W57", "W58", "Semi-final"), (62, "W59", "W60", "Semi-final"),
           (63, "W61", "W62", "Final")])
    for m, h, a, r in ko:
        fixtures.append({"match": m, "home": h, "away": a, "round": r,
                         "date": "2027-01-25", "venue": "Riyadh"})
    return {"format": dict(AC_FORMAT), "teams": teams, "groups": groups,
            "fixtures": fixtures,
            "bracket": {"paths": [{"name": "left"}, {"name": "right"}]},
            "venues": [{"name": "X", "city": "Riyadh", "country": "SA"}]}


def test_no_format_block_yields_wc2026_defaults():
    fmt = tournament_format({"teams": []})
    assert fmt["n_groups"] == 12 and fmt["best_thirds"] == 8
    assert fmt["third_place_match"] is True and fmt["ko_host_advantage"] is False
    assert fmt["hosts"] == HOST_COUNTRY_BY_TEAM and fmt["hosts"] is not HOST_COUNTRY_BY_TEAM
    assert fmt["source_tag"] == "wc2026_schedule"


def test_real_wc_draw_loads_unchanged():
    t = load_tournament(_REAL)
    assert tournament_format(t)["n_groups"] == 12


def test_format_null_rejected():
    with pytest.raises(ValueError, match="format must be a mapping"):
        tournament_format({"format": None})


def test_format_missing_key_rejected():
    d = _ac_min()
    del d["format"]["third_place_match"]
    with pytest.raises(ValueError, match="format block missing"):
        validate_tournament(d)


def test_ac_shape_validates_15_ko_no_third_place():
    out = validate_tournament(_ac_min())
    assert tournament_format(out)["third_place_match"] is False


def test_ac_wrong_ko_count_rejected():
    d = _ac_min()
    d["fixtures"] = d["fixtures"][:-1]          # drop the Final -> 14 KO
    with pytest.raises(ValueError, match="knockout fixture count"):
        validate_tournament(d)


def test_legacy_valid_min_still_accepted():
    """The pre-format minimal WC structure (104 fixtures, no match keys) must
    keep validating exactly as before — the split check is format-gated."""
    from tests.data.test_tournament import _valid_min
    validate_tournament(_valid_min())


# --------------------------------------------------------------------------- #
# Task 6: the REAL config/tournament_ac2027.yaml (May-2026 draw, official       #
# AC27F_MatchSchedule_5june26.pdf) + format-driven ingest tags (F11/F12).       #
# --------------------------------------------------------------------------- #
_REAL_AC = "config/tournament_ac2027.yaml"

#: The 24 drawn nations in martj42 store keys (the P1-WC2026 reconciliation
#: process): 19 names identical to the AFC official spelling, 5 mapped —
#: DPR Korea->North Korea, Islamic Republic of Iran->Iran, Kyrgyz Republic->
#: Kyrgyzstan, China PR->China, Korea Republic->South Korea. Pinned literally
#: so a silent rename in the yaml (which would orphan the team's history join)
#: is a hard test failure.
_AC_GROUPS_MARTJ42 = {
    "A": ["Saudi Arabia", "Kuwait", "Oman", "Palestine"],
    "B": ["Uzbekistan", "Bahrain", "North Korea", "Jordan"],
    "C": ["Iran", "Syria", "Kyrgyzstan", "China"],
    "D": ["Australia", "Tajikistan", "Iraq", "Singapore"],
    "E": ["South Korea", "United Arab Emirates", "Vietnam", "Yemen"],
    "F": ["Japan", "Qatar", "Thailand", "Indonesia"],
}


def _real_ac():
    return load_tournament(_REAL_AC)


def test_real_ac_draw_loads_validates_and_matches_official_shape():
    """The committed real draw: 6 groups of 4 in official seat order (A1..F4,
    martj42 keys), 36 dated group fixtures + 15 knockouts (no 3rd-place match),
    the Task-0 AC format block, hosts {Saudi Arabia: SA}."""
    t = _real_ac()                                     # validate_tournament inside
    fmt = tournament_format(t)
    assert fmt == dict(AC_FORMAT)
    assert {g["name"]: g["teams"] for g in t["groups"]} == _AC_GROUPS_MARTJ42
    group_fx = [f for f in t["fixtures"] if f.get("match") is None]
    ko_fx = [f for f in t["fixtures"] if f.get("match") is not None]
    assert (len(group_fx), len(ko_fx)) == (36, 15)
    # Window: group stage 2027-01-07..20; knockouts 2027-01-22..02-05 (schedule).
    assert min(f["date"] for f in group_fx) == "2027-01-07"
    assert max(f["date"] for f in group_fx) == "2027-01-20"
    assert max(f["date"] for f in ko_fx) == "2027-02-05"
    # Every fixture venue resolves in the venues block (host detection depends on it).
    cities = {v["city"] for v in t["venues"]}
    assert {f["venue"] for f in t["fixtures"]} <= cities
    assert all(v["country"] == "SA" for v in t["venues"])


def test_real_ac_final_matchday_pairs_are_last_two_per_group():
    """The sim reads each group's final-matchday pairings (AFC penalties
    criterion) as the LAST TWO fixtures of the group's schedule-ordered list —
    so the yaml MUST keep schedule order. Official MD3: A: OMA-PLE + KSA-KUW
    (Jan 17) ... F: JPN-QAT + THA-IDN (Jan 20)."""
    t = _real_ac()
    by_group: dict[str, list] = {}
    for f in t["fixtures"]:
        if f.get("match") is None:
            by_group.setdefault(f["group"], []).append(f)
    md3 = {g: {frozenset((f["home"], f["away"])) for f in fxs[-2:]}
           for g, fxs in by_group.items()}
    assert md3["A"] == {frozenset(("Oman", "Palestine")),
                        frozenset(("Saudi Arabia", "Kuwait"))}
    assert md3["F"] == {frozenset(("Japan", "Qatar")),
                        frozenset(("Thailand", "Indonesia"))}
    # ... and each group's last two fixtures share one date (simultaneous MD3).
    for g, fxs in by_group.items():
        assert len(fxs) == 6
        assert len({f["date"] for f in fxs[-2:]}) == 1, f"group {g} MD3 not simultaneous"


def test_real_ac_third_slots_resolve_against_committed_table():
    """Every 3rd-slot ref resolves in build_bracket (the Task-1 loud check), and
    the bracket's {match: eligible-set} equals the committed renumbered table —
    derived from the table BODY, so yaml and table can never drift apart."""
    from wcmodel.sim.bracket import build_bracket
    from wcmodel.sim.thirds import load_assignment_table

    t = _real_ac()
    b = build_bracket(t)                       # raises on any unresolved 3rd-*
    data = load_assignment_table("third_place_assignment_ac2027.json")
    eligible: dict[int, set] = {}
    for row in data["table"].values():
        for m, g in row.items():
            eligible.setdefault(int(m), set()).add(g)
    assert {m: set(s) for m, s in b.third_place_slots.items()} == eligible
    # Official schedule numbers: R16 37-44, QF 45-48, SF 49-50, Final 51.
    assert {m for m, r in b.match_round.items() if r == "R16"} == set(range(37, 45))
    assert {m for m, r in b.match_round.items() if r == "QF"} == set(range(45, 49))
    assert {m for m, r in b.match_round.items() if r == "SF"} == {49, 50}
    assert {m for m, r in b.match_round.items() if r == "Final"} == {51}


def test_ac_ingest_stamps_format_tags_and_is_pit_correct(tmp_path):
    """F11+F12: ingesting the REAL AC draw writes 36 UNPLAYED rows tagged
    tournament='AFC Asian Cup', source=source_version='ac2027_schedule', with
    the schedule's own PIT stamping (valid_as_of==observed_at==date). Read
    back at 2027-01-21 (after the last group fixture, so every row's
    observed_at has passed) -> all 36; at 2027-01-09 -> exactly the 7 fixtures
    dated on/before Jan 9 (the PIT ramp — rows become visible on their own
    date, so a mid-schedule cutoff sees only the fixtures already dated)."""
    import pandas as pd

    from wcmodel.data.store import BitemporalStore
    from wcmodel.data.tournament import ingest_wc_group_fixtures

    t = _real_ac()
    store = BitemporalStore(root=tmp_path / "store")
    n = ingest_wc_group_fixtures(t, store, observed_at="2026-06-05")
    assert n == 36

    rows = store.read("results", cutoff="2027-01-21T00:00:00Z")
    assert len(rows) == 36
    assert (rows["tournament"] == "AFC Asian Cup").all()
    assert (rows["source"] == "ac2027_schedule").all()
    assert (rows["source_version"] == "ac2027_schedule").all()
    assert rows["home_score"].isna().all() and rows["away_score"].isna().all()
    assert (rows["valid_as_of"] == rows["observed_at"]).all()
    # Host rule from the FORMAT hosts: Saudi Arabia's 3 group games (all at SA
    # venues) are the only non-neutral rows.
    ksa = rows[(rows["home_team"] == "Saudi Arabia") | (rows["away_team"] == "Saudi Arabia")]
    assert len(ksa) == 3 and (~ksa["neutral"]).all()
    assert rows["neutral"].sum() == 33

    ramp = store.read("results", cutoff="2027-01-09T00:00:00Z")
    assert len(ramp) == 7                     # matches 1 (Jan 7) + 2-4 (Jan 8) + 5-7 (Jan 9)
    assert (pd.to_datetime(ramp["date"]) <= pd.Timestamp("2027-01-09")).all()


def test_ingest_guard_names_the_edition_not_wc(tmp_path):
    """Review-round fix: the post-kickoff ingest guard names the edition being
    ingested (format competition_name) — an AC-2027 back-stamp says 'AFC Asian
    Cup', the blockless WC path says 'FIFA World Cup', never the literal 'WC'."""
    from wcmodel.data.store import BitemporalStore
    from wcmodel.data.tournament import ingest_wc_group_fixtures

    store = BitemporalStore(root=tmp_path / "store")
    # AC first kickoff is 2027-01-07 -> observing the schedule on Jan 8 is late.
    with pytest.raises(ValueError, match="after the first AFC Asian Cup fixture"):
        ingest_wc_group_fixtures(_real_ac(), store, observed_at="2027-01-08")
    # WC first kickoff is 2026-06-11 -> Jun 12 is late; the guard still fires
    # and names the default format's competition, resolved not hardcoded.
    with pytest.raises(ValueError, match="after the first FIFA World Cup fixture"):
        ingest_wc_group_fixtures(load_tournament(_REAL), store,
                                 observed_at="2026-06-12")


def test_wc_ingest_tags_are_byte_identical_defaults():
    """The WC path must keep stamping EXACTLY today's literals once the tags
    come from the format block: no format block -> competition_name ==
    'FIFA World Cup', source_tag == WC2026_SOURCE ('wc2026_schedule'), hosts ==
    the module literal."""
    from wcmodel.data.tournament import WC2026_SOURCE

    fmt = tournament_format({"teams": []})
    assert fmt["competition_name"] == "FIFA World Cup"
    assert fmt["source_tag"] == WC2026_SOURCE == "wc2026_schedule"
    assert fmt["hosts"] == HOST_COUNTRY_BY_TEAM
