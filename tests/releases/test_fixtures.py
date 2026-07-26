"""Fixtures CSV loader: strict where it matters, permissive on extra columns."""
import pandas as pd
import pytest

from wcmodel.releases.fixtures import load_fixtures, unknown_teams

GOOD = "date,home,away,neutral\n2026-09-21,Senegal,Mozambique,0\n2026-09-22,Egypt,Ethiopia,1\n"


def _write(tmp_path, text, name="fx.csv"):
    p = tmp_path / name
    p.write_text(text)
    return p


def test_loads_good_csv(tmp_path):
    df = load_fixtures(_write(tmp_path, GOOD))
    assert list(df.columns) == ["date", "home", "away", "neutral"]
    assert df["date"].dtype.kind == "M"
    assert bool(df.loc[1, "neutral"]) is True and bool(df.loc[0, "neutral"]) is False


def test_extra_columns_allowed_and_dropped(tmp_path):
    df = load_fixtures(_write(
        tmp_path, "date,home,away,venue,notes\n2026-09-21,Senegal,Mozambique,Dakar,x\n"))
    assert list(df.columns) == ["date", "home", "away", "neutral"]


def test_neutral_optional_defaults_false(tmp_path):
    df = load_fixtures(_write(tmp_path, "date,home,away\n2026-09-21,Senegal,Mozambique\n"))
    assert bool(df.loc[0, "neutral"]) is False


def test_invalid_neutral_value_rejected(tmp_path):
    with pytest.raises(ValueError, match="invalid neutral value"):
        load_fixtures(_write(tmp_path, "date,home,away,neutral\n2026-09-21,A,B,yes\n"))


def test_rejects_missing_column(tmp_path):
    with pytest.raises(ValueError, match="missing required column"):
        load_fixtures(_write(tmp_path, "date,home\n2026-09-21,Senegal\n"))


def test_rejects_bad_date(tmp_path):
    with pytest.raises(ValueError, match="unparseable date"):
        load_fixtures(_write(tmp_path, "date,home,away\nnope,Senegal,Mozambique\n"))


def test_rejects_tz_aware_date(tmp_path):
    """A tz-aware date would blow up later in the PIT compare with a raw TypeError."""
    with pytest.raises(ValueError, match="tz-aware"):
        load_fixtures(_write(
            tmp_path, "date,home,away\n2026-09-21T12:00:00+02:00,Senegal,Mozambique\n"))


def test_rejects_blank_team(tmp_path):
    with pytest.raises(ValueError, match="blank team"):
        load_fixtures(_write(tmp_path, "date,home,away\n2026-09-21,,Mozambique\n"))


def test_rejects_duplicate_fixture(tmp_path):
    dup = "date,home,away\n2026-09-21,Senegal,Mozambique\n2026-09-21,Senegal,Mozambique\n"
    with pytest.raises(ValueError, match="duplicate fixture"):
        load_fixtures(_write(tmp_path, dup))


def test_rejects_self_match(tmp_path):
    with pytest.raises(ValueError, match="home == away"):
        load_fixtures(_write(tmp_path, "date,home,away\n2026-09-21,Senegal,Senegal\n"))


def test_rejects_empty_frame(tmp_path):
    with pytest.raises(ValueError, match="no rows"):
        load_fixtures(_write(tmp_path, "date,home,away\n"))


def test_rejects_whitespace_only_team(tmp_path):
    with pytest.raises(ValueError, match="blank team"):
        load_fixtures(_write(tmp_path, "date,home,away\n2026-09-21,   ,Mozambique\n"))


def test_padded_duplicate_rejected_after_strip(tmp_path):
    dup = ("date,home,away\n2026-09-21, Senegal ,Mozambique\n"
           "2026-09-21,Senegal,Mozambique\n")
    with pytest.raises(ValueError, match="duplicate fixture"):
        load_fixtures(_write(tmp_path, dup))


def test_unknown_teams_exact_set(tmp_path):
    fx = load_fixtures(_write(
        tmp_path, "date,home,away\n2026-09-21,X,B\n2026-09-22,A,Y\n"))
    out = unknown_teams(fx, known={"A", "B"})
    assert out == ["X", "Y"]          # exactly the unknowns; A and B NOT listed
