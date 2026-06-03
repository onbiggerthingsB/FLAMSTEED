import json

from wcmodel.data.coverage import enumerate_coverage, write_coverage_report


def _comps():
    return json.load(open("fixtures/statsbomb_competitions_sample.json"))


def test_coverage_flags_uncovered_team():
    comps = _comps()
    cov = enumerate_coverage(comps, ["Brazil", "Curacao"])
    assert cov.loc[cov.team == "Brazil", "covered"].iloc[0] == True
    assert cov.loc[cov.team == "Curacao", "covered"].iloc[0] == False


def test_coverage_one_row_per_requested_team():
    teams = ["Brazil", "Argentina", "Curacao", "San Marino"]
    cov = enumerate_coverage(_comps(), teams)
    assert list(cov["team"]) == teams  # order preserved, one row each
    assert cov.loc[cov.team == "Argentina", "covered"].iloc[0] == True
    assert cov.loc[cov.team == "San Marino", "covered"].iloc[0] == False


def test_write_coverage_report_lists_gap_set(tmp_path):
    cov = enumerate_coverage(_comps(), ["Brazil", "Curacao"])
    md_path = tmp_path / "phase1_statsbomb_coverage.md"
    write_coverage_report(cov, md_path)
    md = md_path.read_text()
    assert "Curacao" in md  # uncovered team named in the gap set
    assert "Brazil" in md
    # CSV companion is written next to the markdown.
    csv_path = md_path.with_suffix(".csv")
    assert csv_path.exists()
    assert "covered" in csv_path.read_text()
