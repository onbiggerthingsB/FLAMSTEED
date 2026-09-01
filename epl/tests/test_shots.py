"""Synthetic contract tests for the preregistered EPL shots/SOT challenger.

Run with::

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_shots.py -q

Every model, optimizer, scoring, bootstrap, and manifest test below is
synthetic.  The real-data exceptions are read-only preregistered identity legs:
raw/archive digest-shape-join-quarantine validation, the 1,520-row training
schedule, and the 2,280-row/212-block decision key control.  The decision
projection reads only identity/home/away/schedule fields; no test reads a decision
outcome or probability, creates a native prediction, runs a real fit, or
computes a real score.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import inspect
import io
import json
import os
import signal
import stat
import subprocess
import sys
import tarfile
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from epl import paths
from epl import shots as sh
from epl import shots_harness as runner

_REAL_NATIVE_RUNTIME_CLOSURE = runner._native_runtime_closure


@pytest.fixture(autouse=True)
def _synthetic_runtime_closure(monkeypatch):
    """Keep synthetic tests fast; production calls always hash fresh bytes."""
    sdk_path = Path(
        runner._fixed_tool_output(Path("/usr/bin/xcrun"), "--show-sdk-path")
    )

    def synthetic_runtime_closure(
        *, site_packages, python_runtime, runtime_read_paths,
        process_exec_paths, system_read_literals=(),
    ):
        del python_runtime
        root_paths: list[str] = []
        for path in (*runtime_read_paths, str(site_packages), str(sdk_path)):
            logical = str(Path(path).absolute())
            if logical not in root_paths:
                root_paths.append(logical)
        roots = [{
            "logical_path": logical, "resolved_path": logical,
            "link_chain": [], "tree_sha256": "9" * 64,
            "files": 1, "directories": 1, "symlinks": 0, "bytes": 1,
        } for logical in root_paths]

        executable_paths: list[str] = []
        for path in (
            *process_exec_paths,
            str(runner._NATIVE_SANDBOX_EXECUTABLE),
            str(runner._NATIVE_RSS_MONITOR_EXECUTABLE),
        ):
            logical = str(Path(path).absolute())
            if logical not in executable_paths:
                executable_paths.append(logical)
        launcher = str(
            (runner._ROOT / ".venv" / "bin" / "python").absolute()
        )
        executables = []
        for logical in executable_paths:
            if logical == launcher:
                resolved = str(Path(logical).resolve(strict=True))
                info = Path(resolved).stat()
                digest = sh.sha256_file(resolved)
                size = int(info.st_size)
                mode = stat.S_IMODE(info.st_mode)
            else:
                resolved = logical
                digest = "8" * 64
                size = 1
                mode = 0o755
            executables.append({
                "logical_path": logical, "resolved_path": resolved,
                "link_chain": [], "mode": mode, "bytes": size,
                "sha256": digest,
            })

        system_literals = []
        for literal in system_read_literals:
            logical = str(Path(str(literal)).absolute())
            record = {
                "logical_path": logical, "resolved_path": logical,
                "link_chain": [], "mode": 0o444, "bytes": 1,
                "sha256": "7" * 64,
            }
            if Path(logical).is_file() and not Path(logical).is_symlink():
                info = Path(logical).lstat()
                record["mode"] = stat.S_IMODE(info.st_mode)
                record["bytes"] = int(info.st_size)
                record["sha256"] = sh.sha256_file(logical)
            system_literals.append(record)

        payload = {
            "schema": runner._NATIVE_RUNTIME_CLOSURE_SCHEMA,
            "tree_digest_schema": runner._NATIVE_RUNTIME_TREE_SCHEMA,
            "sealed_read_roots": list(runner._NATIVE_SEALED_READ_ROOTS),
            "system_read_literals": system_literals,
            "mutable_roots": roots,
            "executables": executables,
            "file_count": len(roots),
            "directory_count": len(roots),
            "symlink_count": 0,
            "bytes": len(roots),
            "platform": {
                "architecture": "synthetic-arm64",
                "kernel_release": "synthetic-kernel",
                "sw_vers": "synthetic macOS build",
                "root_mount": "/dev/synthetic on / (apfs, sealed, read-only)",
                "sdk_logical_path": str(sdk_path),
                "sdk_resolved_path": str(sdk_path.resolve()),
                "sdk_link_chain": [],
                "clang_version": "synthetic clang",
            },
        }
        return {
            **payload,
            "sha256": hashlib.sha256(
                runner._canonical_bytes(payload)
            ).hexdigest(),
        }

    monkeypatch.setattr(
        runner, "_native_runtime_closure", synthetic_runtime_closure,
    )


def _csv(rows: list[dict], columns: list[str] | None = None) -> str:
    columns = columns or ["Date", "HomeTeam", "AwayTeam", "HS", "AS",
                          "HST", "AST"]
    lines = [",".join(columns)]
    for row in rows:
        lines.append(",".join("" if row.get(c) is None else str(row[c])
                              for c in columns))
    return "\n".join(lines) + "\n"


def _row(date: str, home: str = "Arsenal", away: str = "Chelsea", *,
         hs=10, ass=8, hst=5, ast=4, **extra) -> dict:
    return {"Date": date, "HomeTeam": home, "AwayTeam": away,
            "HS": hs, "AS": ass, "HST": hst, "AST": ast, **extra}


def _archive_for(rows: pd.DataFrame) -> pd.DataFrame:
    out = rows[["season_code", "date", "home_key", "away_key"]].copy()
    out.insert(0, "match_id", [f"m{i:03d}" for i in range(len(out))])
    return out


def _parsed(rows: list[dict], *, season_code: str = "1415") -> pd.DataFrame:
    return sh.parse_shot_csv(_csv(rows), season_code=season_code,
                             source="synthetic.csv")


def _history() -> pd.DataFrame:
    return pd.DataFrame([
        {"date": "2024-01-01", "home_key": "a", "away_key": "b",
         "HS": 12, "AS": 6, "HST": 6, "AST": 2},
        {"date": "2024-01-03", "home_key": "c", "away_key": "a",
         "HS": 8, "AS": 11, "HST": 3, "AST": 5},
        {"date": "2024-01-05", "home_key": "b", "away_key": "c",
         "HS": 9, "AS": 10, "HST": 4, "AST": 4},
        # At and after the cutoff: deliberately valid, but never eligible.
        {"date": "2024-01-10", "home_key": "a", "away_key": "c",
         "HS": 20, "AS": 2, "HST": 10, "AST": 1},
        {"date": "2024-01-11", "home_key": "b", "away_key": "a",
         "HS": 3, "AS": 18, "HST": 1, "AST": 9},
    ])


def _fixtures() -> pd.DataFrame:
    return pd.DataFrame([
        {"match_id": "target-a", "cutoff": "2024-01-10",
         "home_key": "a", "away_key": "c"},
        {"match_id": "target-b", "cutoff": "2024-01-10",
         "home_key": "b", "away_key": "a"},
    ])


def _native(n: int) -> np.ndarray:
    return np.tile(np.array([[0.45, 0.30, 0.25]], dtype=float), (n, 1))


def _synthetic_predictions(features: pd.DataFrame) -> np.ndarray:
    z = features[list(sh.FEATURE_NAMES)].to_numpy(dtype=float)
    beta = np.array([0.03, -0.02, 0.01, -0.01,
                     -0.02, 0.01, -0.015, 0.02])
    return sh._transform_probabilities(_native(len(features)), z, beta)


# ==========================================================================
# 1. Reader, grain, joins, typed refusals, and the pinned read-only receipt
# ==========================================================================

def test_frozen_constants_match_the_preregistration():
    assert sh.ARM_NAME == "dc_1x2_shots"
    assert sh.RAW_ROWS == 4_180
    assert len(sh.RAW_DIGESTS) == 11
    assert sh.HALF_LIFE_DAYS == 365.0
    assert sh.KAPPA == 10.0
    assert sh.FEATURE_NAMES == ("x1", "x2", "x3", "x4")
    assert sh.TRAINING_ROWS == 1_520
    assert sh.TRAINING_HISTORY_ROWS == 1_900
    assert tuple(sh.TRAINING_RAW_DIGESTS) == (
        "E0_1415.csv", "E0_1516.csv", "E0_1617.csv", "E0_1718.csv",
        "E0_1819.csv",
    )
    assert "load_pinned_training_shot_panel" in sh.__all__
    assert not inspect.signature(
        sh.load_pinned_training_shot_panel
    ).parameters
    assert sh.N_BOOT == 10_000
    assert sh.WEEK_BOOTSTRAP_SEED == 20260831
    assert sh.SEASON_BOOTSTRAP_SEED == 20260832


def test_reader_allowlists_keys_and_exact_four_measures_and_ignores_results():
    cols = ["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR",
            "HS", "AS", "HST", "AST", "AvgH"]
    row = _row("16/08/14", FTHG=9, FTAG=8, FTR="H", Div="E0", AvgH=1.2)
    frame = sh.parse_shot_csv(_csv([row], cols), season_code="1415")
    assert list(frame.columns) == [
        "season_code", "date", "home_key", "away_key", "HS", "AS", "HST",
        "AST", "source", "raw_row", "_invalid_reason",
    ]
    assert not {"FTHG", "FTAG", "FTR", "AvgH"} & set(frame.columns)
    assert frame.loc[0, "date"] == pd.Timestamp("2014-08-16")
    assert frame.loc[0, "home_key"] == "arsenal"


def test_reader_uses_only_two_explicit_date_formats_and_blank_identity_rule():
    text = _csv([_row("16/08/14"), _row("17/08/2014", "Everton", "Liverpool")])
    text += "\n,,,,,,,,\n"
    frame = sh.parse_shot_csv(text, season_code="1415")
    assert list(frame["date"]) == [pd.Timestamp("2014-08-16"),
                                    pd.Timestamp("2014-08-17")]
    with pytest.raises(sh.ShotValueInvalid, match="matches neither"):
        sh.parse_shot_csv(_csv([_row("2014-08-18")]), season_code="1415")


@pytest.mark.parametrize("columns", [
    ["Date", "HomeTeam", "AwayTeam", "HS", "AS", "HST"],
    ["Date", "HomeTeam", "AwayTeam", "HS", "AS", "HST", "AST", "AST"],
])
def test_reader_refuses_missing_or_duplicate_required_headers(columns):
    with pytest.raises(sh.ShotSchemaMismatch):
        sh.parse_shot_csv(_csv([], columns), season_code="1415")


@pytest.mark.parametrize(("changes", "reason"), [
    ({"hs": None}, "missing"),
    ({"ass": "word"}, "nonnumeric"),
    ({"hst": -1}, "negative"),
    ({"ast": 1.5}, "noninteger"),
    ({"hs": 4, "hst": 5}, "HST>HS"),
    ({"ass": 3, "ast": 4}, "AST>AS"),
])
def test_canary_6_poison_values_reach_shot_value_refusal(changes, reason):
    parsed = _parsed([_row("16/08/14", **changes)])
    archive = _archive_for(parsed)
    with pytest.raises(sh.ShotValueInvalid, match=reason):
        sh.validate_and_join_shots(parsed, archive)


def test_canary_6_duplicate_key_and_missing_join_reach_panel_refusal():
    parsed = _parsed([_row("16/08/14"), _row("16/08/14")])
    archive = _archive_for(parsed.iloc[:1])
    with pytest.raises(sh.ShotPanelMismatch, match="duplicate"):
        sh.validate_and_join_shots(parsed, archive)

    parsed = _parsed([_row("16/08/14")])
    archive = _archive_for(parsed)
    archive.loc[0, "away_key"] = "someone_else"
    with pytest.raises(sh.ShotPanelMismatch, match="no archive match"):
        sh.validate_and_join_shots(parsed, archive)


def test_canary_6_exact_quarantine_passes_but_zero_changed_or_second_bad_refuses():
    pinned = _row("15/08/2021", "Newcastle", "West Ham",
                  hs=17, ass=8, hst=3, ast=9)
    valid = _row("16/08/2021", "Arsenal", "Chelsea")
    parsed = _parsed([pinned, valid], season_code="2122")
    archive = _archive_for(parsed)
    panel = sh.validate_and_join_shots(
        parsed, archive, expected_quarantine=sh.PINNED_QUARANTINE,
        expected_rows=2,
    )
    assert panel.raw_rows == 2
    assert len(panel.frame) == 1
    assert len(panel.quarantine) == 1
    assert panel.quarantine[0].values == (17.0, 8.0, 3.0, 9.0)

    no_bad = _parsed([valid], season_code="2122")
    with pytest.raises(sh.ShotPanelMismatch, match="pinned quarantine"):
        sh.validate_and_join_shots(
            no_bad, _archive_for(no_bad),
            expected_quarantine=sh.PINNED_QUARANTINE,
        )

    changed = _parsed([
        _row("15/08/2021", "Newcastle", "West Ham",
             hs=17, ass=8, hst=3, ast=10), valid,
    ], season_code="2122")
    with pytest.raises(sh.ShotPanelMismatch, match="pinned quarantine"):
        sh.validate_and_join_shots(
            changed, _archive_for(changed),
            expected_quarantine=sh.PINNED_QUARANTINE,
        )

    second = _parsed([
        pinned, valid,
        _row("17/08/2021", "Everton", "Liverpool", hs=2, hst=3),
    ], season_code="2122")
    with pytest.raises(sh.ShotPanelMismatch, match="pinned quarantine"):
        sh.validate_and_join_shots(
            second, _archive_for(second),
            expected_quarantine=sh.PINNED_QUARANTINE,
        )


def test_source_digest_guard_refuses_missing_extra_and_changed_bytes(tmp_path, monkeypatch):
    good = tmp_path / "one.csv"
    good.write_text("bytes\n")
    digest = hashlib.sha256(good.read_bytes()).hexdigest()
    monkeypatch.setattr(sh, "RAW_DIGESTS", {"one.csv": digest})
    assert sh.assert_source_digests({"one.csv": good}) == {"one.csv": digest}
    with pytest.raises(sh.SourceDigestMismatch, match="file set differs"):
        sh.assert_source_digests({})
    with pytest.raises(sh.SourceDigestMismatch, match="extra"):
        sh.assert_source_digests({"one.csv": good, "two.csv": good})
    good.write_text("changed\n")
    with pytest.raises(sh.SourceDigestMismatch, match="SHA-256"):
        sh.assert_source_digests({"one.csv": good})


def test_training_source_reader_rejects_missing_extra_and_changed_pins(
    tmp_path, monkeypatch,
):
    selected = tmp_path / "E0_1415.csv"
    selected.write_text("selected bytes\n")
    digest = hashlib.sha256(selected.read_bytes()).hexdigest()
    monkeypatch.setattr(
        sh, "_expected_training_raw_digests",
        lambda: {"E0_1415.csv": digest},
    )
    texts, digests = sh._read_training_source_texts({
        "E0_1415.csv": selected,
    })
    assert texts == {"E0_1415.csv": "selected bytes\n"}
    assert digests == {"E0_1415.csv": digest}
    with pytest.raises(sh.SourceDigestMismatch, match="missing"):
        sh._read_training_source_texts({})
    with pytest.raises(sh.SourceDigestMismatch, match="extra"):
        sh._read_training_source_texts({
            "E0_1415.csv": selected,
            "E0_1920.csv": selected,
        })
    selected.write_text("changed bytes\n")
    with pytest.raises(sh.SourceDigestMismatch, match="SHA-256"):
        sh._read_training_source_texts({"E0_1415.csv": selected})


def _write_synthetic_training_sidecar(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    names = (
        "E0_1415.csv", "E0_1516.csv", "E0_1617.csv", "E0_1718.csv",
        "E0_1819.csv",
    )
    expected, archive_rows = {}, []
    for season_index, name in enumerate(names):
        season_code = name.removeprefix("E0_").removesuffix(".csv")
        dates = pd.date_range(f"{2000 + 2 * season_index}-01-01", periods=380)
        rows = [_row(date.strftime("%d/%m/%y")) for date in dates]
        path = raw_dir / name
        path.write_text(_csv(rows))
        expected[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        archive_rows.extend({
            "match_id": f"{season_code}-{ordinal:03d}",
            "season_code": season_code, "date": date,
            "home_key": "arsenal", "away_key": "chelsea",
        } for ordinal, date in enumerate(dates))
    later = raw_dir / "E0_1920.csv"
    later.write_text("must never be opened\n")
    archive_path = tmp_path / "matches.parquet"
    pd.DataFrame.from_records(archive_rows).to_parquet(archive_path, index=False)
    archive_sha256 = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    return raw_dir, archive_path, later, expected, archive_sha256


def test_training_loader_uses_only_five_fixed_files_and_identity_projection(
    tmp_path, monkeypatch,
):
    raw_dir, archive_path, later, expected, archive_sha256 = (
        _write_synthetic_training_sidecar(tmp_path)
    )
    monkeypatch.setattr(paths, "RAW_DIR", raw_dir)
    monkeypatch.setattr(paths, "MATCHES_PARQUET", archive_path)
    monkeypatch.setattr(sh, "_expected_matches_sha256", lambda: archive_sha256)
    monkeypatch.setattr(
        sh, "_expected_training_raw_digests", lambda: dict(expected),
    )
    # The exported diagnostic copy is not authority for the fixed loader.
    monkeypatch.setitem(sh.TRAINING_RAW_DIGESTS, later.name, "f" * 64)

    original_read_bytes = Path.read_bytes
    opened = []

    def selected_bytes_only(path, *args, **kwargs):
        if path.parent.resolve() == raw_dir.resolve():
            opened.append(path.resolve())
            assert path.name in expected
        elif path.resolve() == archive_path.resolve():
            opened.append(path.resolve())
        assert path.resolve() != later.resolve()
        return original_read_bytes(path, *args, **kwargs)

    original_read_parquet = pd.read_parquet
    parquet_calls = []

    def identity_only(source, *args, **kwargs):
        assert isinstance(source, io.BytesIO)
        parquet_calls.append((
            hashlib.sha256(source.getvalue()).hexdigest(),
            tuple(kwargs["columns"]),
        ))
        assert tuple(kwargs["columns"]) == (
            "match_id", "season_code", "date", "home_key", "away_key",
        )
        return original_read_parquet(source, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", selected_bytes_only)
    monkeypatch.setattr(sh.pd, "read_parquet", identity_only)
    panel = sh.load_pinned_training_shot_panel()

    assert opened == [
        (raw_dir / name).resolve() for name in expected
    ] + [archive_path.resolve()]
    assert parquet_calls == [(archive_sha256, (
        "match_id", "season_code", "date", "home_key", "away_key",
    ))]
    assert panel.raw_rows == 1_900
    assert len(panel.frame) == 1_900
    assert panel.quarantine == ()
    assert panel.source_digests == expected
    assert not {"FTR", "y", "dc_home", "market_home"} & set(panel.frame)

    # A byte-level archive change refuses before a second parquet projection.
    archive_path.write_bytes(archive_path.read_bytes() + b"changed")
    with pytest.raises(sh.SourceDigestMismatch, match="SHA-256"):
        sh.load_pinned_training_shot_panel()
    assert len(parquet_calls) == 1


def test_real_training_shot_sidecar_is_exact_clean_identity_panel(monkeypatch):
    expected = sh._expected_training_raw_digests()
    selected = [paths.RAW_DIR / name for name in expected]
    if not paths.MATCHES_PARQUET.exists() or not all(path.exists() for path in selected):
        pytest.skip("pinned EPL raw/archive artifacts are not present")

    original_read_bytes = Path.read_bytes
    opened = []

    def selected_bytes_only(path, *args, **kwargs):
        if path.parent.resolve() == paths.RAW_DIR.resolve():
            opened.append(path.resolve())
            assert path.name in expected
        elif path.resolve() == paths.MATCHES_PARQUET.resolve():
            opened.append(path.resolve())
        return original_read_bytes(path, *args, **kwargs)

    original_read_parquet = pd.read_parquet
    parquet_calls = []

    def identity_only(source, *args, **kwargs):
        assert isinstance(source, io.BytesIO)
        parquet_calls.append(tuple(kwargs["columns"]))
        assert tuple(kwargs["columns"]) == (
            "match_id", "season_code", "date", "home_key", "away_key",
        )
        return original_read_parquet(source, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", selected_bytes_only)
    monkeypatch.setattr(sh.pd, "read_parquet", identity_only)
    panel = sh.load_pinned_training_shot_panel()

    assert opened == [
        (paths.RAW_DIR / name).resolve() for name in expected
    ] + [paths.MATCHES_PARQUET.resolve()]
    assert parquet_calls == [(
        "match_id", "season_code", "date", "home_key", "away_key",
    )]
    assert panel.raw_rows == 1_900
    assert len(panel.frame) == 1_900
    assert panel.quarantine == ()
    assert panel.source_digests == expected
    assert panel.frame["match_id"].notna().all()
    assert panel.frame["match_id"].is_unique
    assert panel.frame["season_code"].astype(str).value_counts().to_dict() == {
        "1415": 380, "1516": 380, "1617": 380, "1718": 380,
        "1819": 380,
    }
    assert not {
        "fthg", "ftag", "ftr", "y", "dc_home", "dc_draw", "dc_away",
        "market_home", "market_draw", "market_away",
    } & set(panel.frame)


def test_pinned_raw_shape_digests_join_and_one_quarantine_only(monkeypatch):
    """The one sanctioned real-data test: identity/shape only, no fit/score."""
    raw_files = [paths.RAW_DIR / name for name in sh.RAW_DIGESTS]
    if not paths.MATCHES_PARQUET.exists() or not all(p.exists() for p in raw_files):
        pytest.skip("pinned EPL raw/archive artifacts are not present")
    original = pd.read_parquet
    calls = []

    def identity_only(path, *args, **kwargs):
        calls.append((Path(path).resolve(), tuple(kwargs.get("columns", ()))))
        assert Path(path).resolve() == paths.MATCHES_PARQUET.resolve()
        assert tuple(kwargs["columns"]) == (
            "match_id", "season_code", "date", "home_key", "away_key",
        )
        return original(path, *args, **kwargs)

    monkeypatch.setattr(sh.pd, "read_parquet", identity_only)
    panel = sh.load_pinned_shot_panel()
    assert calls == [(paths.MATCHES_PARQUET.resolve(), (
        "match_id", "season_code", "date", "home_key", "away_key",
    ))]
    assert panel.raw_rows == 4_180
    assert len(panel.frame) == 4_179
    assert panel.frame["match_id"].is_unique
    assert panel.frame["match_id"].notna().all()
    assert panel.source_digests == sh.RAW_DIGESTS
    assert len(panel.quarantine) == 1
    q = panel.quarantine[0]
    assert (q.date, q.home_key, q.away_key) == (
        "2021-08-15", "newcastle", "west_ham",
    )
    assert q.values == (17.0, 8.0, 3.0, 9.0)
    assert q.reason == "AST>AS"


def test_pinned_loader_refuses_a_byte_changed_archive(tmp_path):
    archive = pd.read_parquet(
        paths.MATCHES_PARQUET,
        columns=["match_id", "season_code", "date", "home_key", "away_key"],
    )
    archive.loc[0, "match_id"] = "tampered-id"
    changed = tmp_path / "changed_matches.parquet"
    archive.to_parquet(changed, index=False)
    with pytest.raises(sh.SourceDigestMismatch, match="SHA-256"):
        sh.load_pinned_shot_panel(archive_path=changed)


def test_validator_recomputes_invalidity_instead_of_trusting_marker():
    parsed = _parsed([_row("16/08/14")])
    archive = _archive_for(parsed)
    parsed.loc[0, "HS"] = -1
    assert parsed.loc[0, "_invalid_reason"] == ""
    with pytest.raises(sh.ShotValueInvalid, match="HS:negative"):
        sh.validate_and_join_shots(parsed, archive)


def test_real_2280_key_negative_control_and_fixture_positive_controls():
    schedule = sh.load_pinned_decision_schedule()
    assert isinstance(schedule, tuple)
    assert all(isinstance(row, sh.DecisionFixture) for row in schedule)
    ids = tuple(row.match_id for row in schedule)
    assert len(ids) == 2_280 and len(set(ids)) == 2_280
    assert "57b6538de8a5404c" in ids  # pinned quarantined row is not dropped
    assert sh.load_pinned_decision_fixture_ids() == ids
    assert len({row.block for row in schedule}) == 212
    assert {season: sum(row.season == season for row in schedule)
            for season in sorted({row.season for row in schedule})} == {
        "2019/20": 380, "2020/21": 380, "2021/22": 380,
        "2022/23": 380, "2023/24": 380, "2024/25": 380,
    }
    assert sh.assert_fixture_sets(
        candidate_ids=ids, native_ids=ids, market_ids=ids,
        outcome_ids=ids, expected_ids=ids,
    ) == ids
    with pytest.raises(sh.FixtureSetMismatch):
        sh.assert_fixture_sets(candidate_ids=ids, native_ids=ids[:-1],
                               market_ids=ids, outcome_ids=ids)
    duplicate = (ids[0], ids[0], *ids[2:])
    with pytest.raises(sh.FixtureSetMismatch):
        sh.assert_fixture_sets(candidate_ids=ids, native_ids=duplicate,
                               market_ids=ids, outcome_ids=ids)
    reordered = (ids[1], ids[0], *ids[2:])
    with pytest.raises(sh.FixtureSetMismatch):
        sh.assert_fixture_sets(candidate_ids=ids, native_ids=reordered,
                               market_ids=ids, outcome_ids=ids)


# ==========================================================================
# 2. Block schedule, features, and point-in-time canaries 1, 2, and 8
# ==========================================================================

def test_weekly_cutoffs_are_season_iso_week_opening_days_at_midnight():
    fixtures = pd.DataFrame([
        {"match_id": "a", "season": "2024/25", "date": "2024-08-18"},
        {"match_id": "b", "season": "2024/25", "date": "2024-08-12"},
        {"match_id": "c", "season": "2024/25", "date": "2024-08-19"},
    ])
    out = sh.attach_weekly_cutoffs(fixtures)
    assert out.loc[0, "cutoff"] == pd.Timestamp("2024-08-12")
    assert out.loc[1, "cutoff"] == pd.Timestamp("2024-08-12")
    assert out.loc[2, "cutoff"] == pd.Timestamp("2024-08-19")
    assert list(out["match_id"]) == ["a", "b", "c"]  # no repair/reorder
    assert all(t == t.normalize() for t in out["cutoff"])


def _synthetic_training_fixtures() -> pd.DataFrame:
    starts = {
        "2015/16": pd.Timestamp("2015-08-10"),
        "2016/17": pd.Timestamp("2016-08-08"),
        "2017/18": pd.Timestamp("2017-08-07"),
        "2018/19": pd.Timestamp("2018-08-06"),
    }
    rows = []
    for season, n_blocks in sh.TRAINING_BLOCK_COUNTS.items():
        base, extra = divmod(380, n_blocks)
        for block in range(n_blocks):
            size = base + (1 if block < extra else 0)
            date = starts[season] + pd.Timedelta(days=7 * block)
            for j in range(size):
                rows.append({"match_id": f"{season}-{block:02d}-{j:02d}",
                             "season": season, "date": date})
    return pd.DataFrame(rows)


def test_training_cutoff_wrapper_requires_exact_1520_rows_and_142_blocks():
    fixtures = _synthetic_training_fixtures()
    out = sh.attach_training_cutoffs(fixtures)
    assert len(out) == 1_520
    assert out["block"].nunique() == 142
    assert (out.groupby("season")["block"].nunique().to_dict()
            == sh.TRAINING_BLOCK_COUNTS)
    with pytest.raises(sh.FitFailure, match="requires exactly"):
        sh.attach_training_cutoffs(fixtures.iloc[:-1])
    wrong_blocks = fixtures.copy()
    wrong_blocks.loc[0, "date"] = pd.Timestamp("2015-07-01")
    with pytest.raises(sh.FitFailure, match="block counts"):
        sh.attach_training_cutoffs(wrong_blocks)


def test_real_training_identity_projection_is_exact_and_outcome_free(monkeypatch):
    projected = []
    original = pd.read_parquet

    def tracked(*args, **kwargs):
        projected.append(tuple(kwargs.get("columns", ())))
        return original(*args, **kwargs)

    monkeypatch.setattr(sh.pd, "read_parquet", tracked)
    frame = sh.load_pinned_training_fixtures()
    assert len(frame) == 1_520
    assert frame["match_id"].is_unique
    assert frame["block"].nunique() == 142
    assert frame.groupby("season")["block"].nunique().to_dict() == sh.TRAINING_BLOCK_COUNTS
    assert not {"ftr", "fthg", "ftag", "y"} & set(frame.columns)
    assert projected == [("match_id", "season", "date", "home_key", "away_key")]
    assert "played" not in projected[0]


def test_k2_shot_reference_does_not_call_production_ingestion_or_features(
    monkeypatch,
):
    panel = sh.load_pinned_training_shot_panel()
    fixture_frame = sh.load_pinned_training_fixtures()
    production = sh.shot_features(panel.frame, fixture_frame)
    _, schedule = runner._training_binding()
    projected: list[tuple[str, ...]] = []
    real_read_parquet = runner.pd.read_parquet

    def identity_projection_only(*args, **kwargs):
        columns = tuple(kwargs.get("columns", ()))
        projected.append(columns)
        assert not {"fthg", "ftag", "ftr", "played", "y"} & set(columns)
        return real_read_parquet(*args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("K reference called a production shot helper")

    for name in (
        "load_pinned_training_shot_panel", "parse_shot_csv",
        "validate_and_join_shots", "shot_features", "_ratios",
    ):
        monkeypatch.setattr(sh, name, forbidden)
    monkeypatch.setattr(runner.pd, "read_parquet", identity_projection_only)
    # PRE-H verification may inspect the shot sidecar and the archive identity
    # projection, but it must not call the full K loader: that loader properly
    # opens the training goal columns only after H during K construction.
    archive_bytes = runner._read_regular_snapshot(
        paths.MATCHES_PARQUET, label="test matches identity archive",
    )
    independent_panel = runner._independent_k2_training_shot_panel(
        archive_bytes,
    )
    expectations, features = runner._independent_k2_shot_reference(
        independent_panel, schedule,
    )

    assert np.array_equal(
        np.asarray(expectations),
        production[["HS_hat", "AS_hat", "HST_hat", "AST_hat"]].to_numpy(),
    )
    assert np.array_equal(
        np.asarray(features),
        production[list(sh.FEATURE_NAMES)].to_numpy(),
    )
    assert projected == [
        ("match_id", "season_code", "date", "home_key", "away_key"),
    ]


def test_k2_literal_shot_reference_rejects_a_corrupt_pinned_panel():
    archive_bytes = runner._read_regular_snapshot(
        paths.MATCHES_PARQUET, label="test matches archive",
    )
    panel = runner._independent_k2_training_shot_panel(archive_bytes)
    _, schedule = runner._training_binding()
    corrupt = panel.frame.copy()
    corrupt.loc[0, "HST"] = corrupt.loc[0, "HS"] + 1.0
    corrupt_panel = runner._IndependentK2ShotPanel(
        frame=corrupt, raw_rows=panel.raw_rows,
        source_digests=panel.source_digests,
    )
    with pytest.raises(sh.ShotValueInvalid, match="invalid count"):
        runner._independent_k2_shot_reference(corrupt_panel, schedule)


def test_k2_independent_raw_parser_refuses_malformed_shot_values():
    malformed = (
        b"Date,HomeTeam,AwayTeam,HS,AS,HST,AST\n"
        b"16/08/14,Arsenal,Crystal Palace,4,2,5,1\n"
    )
    with pytest.raises(sh.ShotValueInvalid, match="exceed total shots"):
        runner._independent_parse_k2_training_csv(
            malformed, source="E0_1415.csv", season_code="1415",
        )


def test_cold_start_ratios_are_one_and_four_feature_formula_is_literal():
    history = pd.DataFrame([
        {"date": "2024-01-01", "home_key": "a", "away_key": "b",
         "HS": 10, "AS": 8, "HST": 5, "AST": 4},
    ])
    fixture = pd.DataFrame([
        {"match_id": "cold", "cutoff": "2024-01-02",
         "home_key": "new-home", "away_key": "new-away"},
    ])
    out = sh.shot_features(history, fixture).iloc[0]
    assert out["HS_hat"] == pytest.approx(10.0)
    assert out["AS_hat"] == pytest.approx(8.0)
    assert out["HST_hat"] == pytest.approx(5.0)
    assert out["AST_hat"] == pytest.approx(4.0)
    assert [out[x] for x in sh.FEATURE_NAMES] == pytest.approx([1, 1, 9, 9])


def test_weighted_league_means_use_the_literal_365_day_half_life():
    cutoff = pd.Timestamp("2025-01-01")
    history = pd.DataFrame([
        {"date": cutoff - pd.Timedelta(days=365), "home_key": "a", "away_key": "b",
         "HS": 10, "AS": 6, "HST": 5, "AST": 2},
        {"date": cutoff - pd.Timedelta(days=1), "home_key": "c", "away_key": "d",
         "HS": 30, "AS": 14, "HST": 15, "AST": 8},
    ])
    fixture = pd.DataFrame([
        {"match_id": "cold", "cutoff": cutoff,
         "home_key": "new-home", "away_key": "new-away"},
    ])
    out = sh.shot_features(history, fixture).iloc[0]
    w_old = 0.5
    w_new = 2 ** (-1 / 365)
    expected = {
        "HS_hat": (w_old * 10 + w_new * 30) / (w_old + w_new),
        "AS_hat": (w_old * 6 + w_new * 14) / (w_old + w_new),
        "HST_hat": (w_old * 5 + w_new * 15) / (w_old + w_new),
        "AST_hat": (w_old * 2 + w_new * 8) / (w_old + w_new),
    }
    for name, value in expected.items():
        assert out[name] == pytest.approx(value, rel=1e-14)


def test_attack_and_defence_ratios_use_literal_ten_match_shrinkage():
    history = pd.DataFrame([
        {"date": "2024-01-01", "home_key": "a", "away_key": "b",
         "HS": 20, "AS": 5, "HST": 10, "AST": 2},
        {"date": "2024-01-01", "home_key": "c", "away_key": "d",
         "HS": 10, "AS": 15, "HST": 4, "AST": 8},
    ])
    fixture = pd.DataFrame([
        {"match_id": "seen", "cutoff": "2024-01-02",
         "home_key": "a", "away_key": "b"},
    ])
    out = sh.shot_features(history, fixture).iloc[0]
    w = 2 ** (-1 / 365)
    home_ratio = (10 + w * (20 / 15)) / (10 + w)
    away_ratio = (10 + w * (5 / 10)) / (10 + w)
    assert out["HS_hat"] == pytest.approx(15 * home_ratio * home_ratio)
    assert out["AS_hat"] == pytest.approx(10 * away_ratio * away_ratio)


def test_canary_1_literal_cutoff_and_c_minus_one_boundary():
    history = pd.concat([
        _history(),
        pd.DataFrame([{
            "date": "2024-01-09", "home_key": "a", "away_key": "c",
            "HS": 13, "AS": 9, "HST": 6, "AST": 4,
        }]),
    ], ignore_index=True)
    fixtures = _fixtures().iloc[:1]
    baseline = sh.shot_features(history, fixtures)

    at_or_after_c = history.copy()
    mask = pd.to_datetime(at_or_after_c["date"]) >= pd.Timestamp("2024-01-10")
    at_or_after_c.loc[mask, ["HS", "AS", "HST", "AST"]] = [90, 80, 70, 60]
    negative = sh.shot_features(at_or_after_c, fixtures)
    np.testing.assert_array_equal(
        baseline[[*sh.FEATURE_NAMES]].to_numpy(),
        negative[[*sh.FEATURE_NAMES]].to_numpy(),
    )
    np.testing.assert_array_equal(
        _synthetic_predictions(baseline), _synthetic_predictions(negative),
    )

    c_minus_one = history.copy()
    prior = pd.to_datetime(c_minus_one["date"]) == pd.Timestamp("2024-01-09")
    c_minus_one.loc[prior, ["HS", "AS", "HST", "AST"]] = [60, 20, 50, 10]
    positive = sh.shot_features(c_minus_one, fixtures)
    assert np.max(np.abs(
        baseline[list(sh.FEATURE_NAMES)].to_numpy()
        - positive[list(sh.FEATURE_NAMES)].to_numpy()
    )) > 1e-9
    assert np.max(np.abs(
        _synthetic_predictions(baseline) - _synthetic_predictions(positive)
    )) > 1e-9


def test_canary_2_target_and_same_block_rows_are_isolated_with_prior_control():
    history = _history()
    fixtures = _fixtures()
    baseline = sh.shot_features(history, fixtures)
    same_block = history.copy()
    mask = pd.to_datetime(same_block["date"]) >= pd.Timestamp("2024-01-10")
    same_block.loc[mask, ["HS", "AS", "HST", "AST"]] = [40, 30, 20, 10]
    negative = sh.shot_features(same_block, fixtures)
    np.testing.assert_array_equal(
        baseline[list(sh.FEATURE_NAMES)].to_numpy(),
        negative[list(sh.FEATURE_NAMES)].to_numpy(),
    )
    np.testing.assert_array_equal(
        _synthetic_predictions(baseline), _synthetic_predictions(negative),
    )
    prior = history.copy()
    prior.loc[1, ["AS", "AST"]] = [40, 30]
    positive = sh.shot_features(prior, fixtures)
    assert not np.array_equal(
        baseline[list(sh.FEATURE_NAMES)].to_numpy(),
        positive[list(sh.FEATURE_NAMES)].to_numpy(),
    )
    assert np.max(np.abs(
        _synthetic_predictions(baseline) - _synthetic_predictions(positive)
    )) > 1e-9


def test_canary_8_future_outcome_encoding_is_inert_but_prior_encoding_moves():
    history = _history()
    fixtures = _fixtures().iloc[:1]
    baseline = sh.shot_features(history, fixtures)
    future_encoded = history.copy()
    future = pd.to_datetime(future_encoded["date"]) >= pd.Timestamp("2024-01-10")
    # A perfect future "home" signal, while retaining HST<=HS and AST<=AS.
    future_encoded.loc[future, ["HS", "AS", "HST", "AST"]] = [99, 1, 99, 0]
    negative = sh.shot_features(future_encoded, fixtures)
    np.testing.assert_array_equal(
        baseline[list(sh.FEATURE_NAMES)].to_numpy(),
        negative[list(sh.FEATURE_NAMES)].to_numpy(),
    )
    np.testing.assert_array_equal(
        _synthetic_predictions(baseline), _synthetic_predictions(negative),
    )
    prior_encoded = history.copy()
    prior_encoded.loc[0, ["HS", "AS", "HST", "AST"]] = [99, 1, 99, 0]
    positive = sh.shot_features(prior_encoded, fixtures)
    assert np.max(np.abs(
        baseline[list(sh.FEATURE_NAMES)].to_numpy()
        - positive[list(sh.FEATURE_NAMES)].to_numpy()
    )) > 1e-9
    assert np.max(np.abs(
        _synthetic_predictions(baseline) - _synthetic_predictions(positive)
    )) > 1e-9


def test_non_midnight_cutoff_is_a_typed_time_refusal():
    fixtures = _fixtures().iloc[:1].copy()
    fixtures.loc[:, "cutoff"] = "2024-01-10 12:00:00"
    with pytest.raises(sh.TimeBoundaryViolation, match="normalized midnight"):
        sh.shot_features(_history(), fixtures)


# ==========================================================================
# 3. Training-only scaler, tilt arithmetic, and canaries 3 and 5
# ==========================================================================

def _synthetic_training_features() -> pd.DataFrame:
    rows = []
    i = 0
    for season in sh.TRAINING_SEASONS:
        for _ in range(380):
            rows.append({"match_id": f"train-{i:04d}", "season": season,
                         "x1": float(i), "x2": float((i * 3) % 17),
                         "x3": float((i * 5) % 23),
                         "x4": float((i * 7) % 29)})
            i += 1
    return pd.DataFrame(rows)


def test_scaler_is_training_only_population_moments_and_refuses_score_season():
    frame = _synthetic_training_features()
    scaler = sh._fit_training_scaler(frame)
    x = frame[list(sh.FEATURE_NAMES)].to_numpy()
    assert scaler.means == pytest.approx(tuple(x.mean(axis=0)))
    assert scaler.standard_deviations == pytest.approx(tuple(x.std(axis=0, ddof=0)))
    z = sh._standardize_features(frame.iloc[:5], scaler)
    expected = ((x[:5] - x.mean(axis=0)) / x.std(axis=0, ddof=0))
    np.testing.assert_allclose(z, expected, rtol=0, atol=0)

    poisoned = frame.copy()
    poisoned.loc[0, "season"] = "2019/20"
    with pytest.raises(sh.FitFailure, match="requires exactly"):
        sh._fit_training_scaler(poisoned)
    with pytest.raises(sh.FitFailure, match="requires exactly"):
        sh._fit_training_scaler(frame.iloc[:-1])
    duplicate = frame.copy()
    duplicate.loc[1, "match_id"] = duplicate.loc[0, "match_id"]
    with pytest.raises(sh.FixtureSetMismatch, match="nonempty and unique"):
        sh._fit_training_scaler(duplicate)


def test_scaler_refuses_zero_population_standard_deviation():
    frame = _synthetic_training_features()
    frame["x4"] = 1.0
    with pytest.raises(sh.FitFailure, match="zero or nonfinite"):
        sh._fit_training_scaler(frame)


def test_training_native_rounding_is_eight_decimals_without_renormalisation():
    native = np.array([[0.456789123, 0.300000000, 0.243210877]])
    rounded = sh._round_training_native(native)
    np.testing.assert_array_equal(
        rounded, np.array([[0.45678912, 0.30000000, 0.24321088]])
    )
    independently_rounded = sh._round_training_native(
        np.array([[0.333333324, 0.333333324, 0.333333352]])
    )
    np.testing.assert_array_equal(
        independently_rounded,
        np.array([[0.33333332, 0.33333332, 0.33333335]]),
    )
    assert independently_rounded.sum() == pytest.approx(0.99999999)
    model = sh._native_model_probabilities(independently_rounded)
    assert model.sum() == pytest.approx(1.0, abs=1e-12)
    # Stored cells are never repaired in place.
    np.testing.assert_array_equal(
        independently_rounded,
        np.array([[0.33333332, 0.33333332, 0.33333335]]),
    )
    with pytest.raises(sh.ProbabilityInvalid, match="stored native"):
        sh._check_stored_native_probabilities(
            np.array([[0.33333332, 0.33333332, 0.33333332]]),
            label="synthetic stored native",
        )


def test_real_effect_apis_are_not_public_before_the_audited_runner():
    assert sh.BUILD_STATES == (
        "BUILT_UNFROZEN_PRE_H", "H_MANIFEST_PRESENT_UNVERIFIED",
        "FROZEN_H_VERIFIED",
    )
    assert not hasattr(sh, "BUILD_STATE")
    retired = {
        "fit_training_scaler", "standardize_features", "round_training_native",
        "transform_probabilities", "fit_residual_tilt", "fit_training_tilt",
        "paired_rps", "week_block_bootstrap", "season_block_bootstrap",
        "per_season_means", "HarnessGate", "CoefficientGate",
    }
    assert retired.isdisjoint(sh.__all__)
    assert all(not hasattr(sh, name) for name in retired)


def test_tilt_analytic_gradient_matches_central_difference():
    rng = np.random.default_rng(7)
    native = _native(12)
    z = rng.normal(size=(12, 4))
    y = np.arange(12) % 3
    beta = rng.normal(scale=0.1, size=8)
    loss, grad = sh._tilt_loss_gradient(beta, native, z, y)
    assert np.isfinite(loss)
    numeric = np.empty(8)
    eps = 1e-6
    for j in range(8):
        plus, minus = beta.copy(), beta.copy()
        plus[j] += eps
        minus[j] -= eps
        numeric[j] = (
            sh._tilt_loss_gradient(plus, native, z, y)[0]
            - sh._tilt_loss_gradient(minus, native, z, y)[0]
        ) / (2 * eps)
    np.testing.assert_allclose(grad, numeric, rtol=2e-6, atol=2e-6)


def test_fixed_optimizer_is_deterministic_and_improves_its_objective():
    rng = np.random.default_rng(11)
    z = rng.normal(size=(90, 4))
    native = _native(90)
    y = np.where(z[:, 0] > 0.6, 0, np.where(z[:, 1] > 0.2, 1, 2))
    zero = sh._tilt_loss_gradient(np.zeros(8), native, z, y)[0]
    first = sh._fit_residual_tilt(native, z, y)
    second = sh._fit_residual_tilt(native, z, y)
    assert first == second
    assert first.success is True
    assert first.status == 0
    assert first.objective < zero
    assert len(first.beta) == 8
    assert len(first.gradient) == 8
    assert first.iterations >= 0
    assert first.function_evaluations >= 1
    assert first.gradient_evaluations >= 1
    recomputed_objective, recomputed_gradient = sh._tilt_loss_gradient(
        first.beta, native, z, y,
    )
    assert first.objective == recomputed_objective
    np.testing.assert_array_equal(first.gradient, recomputed_gradient)


def test_optimizer_preserves_exact_result_provenance_and_frozen_call(monkeypatch):
    beta = np.zeros(8, dtype=np.float64)
    gradient = np.zeros(8, dtype=np.float64)
    native = _native(6)
    z = np.zeros((6, 4), dtype=np.float64)
    y = np.arange(6) % 3
    objective, _ = sh._tilt_loss_gradient(beta, native, z, y)

    def fake_minimize(fun, start, *, method, jac, options):
        assert callable(fun)
        np.testing.assert_array_equal(start, np.zeros(8, dtype=np.float64))
        assert method == "L-BFGS-B"
        assert jac is True
        assert options == {"maxiter": 10_000, "ftol": 1e-12, "gtol": 1e-10}
        return SimpleNamespace(
            success=True, status=17, x=beta, fun=objective, jac=gradient,
            nit=23, nfev=29, njev=31, message="synthetic exact result",
        )

    monkeypatch.setattr(sh, "minimize", fake_minimize)
    fit = sh._fit_residual_tilt(
        native, z, y,
    )
    assert fit == sh.TiltFit(
        success=True, status=17,
        beta=tuple(float(value) for value in beta), objective=objective,
        independent_objective=objective, objective_consistent=True,
        gradient=tuple(float(value) for value in gradient),
        independent_gradient=tuple(float(value) for value in gradient),
        gradient_consistent=True,
        independent_gradient_max_abs=0.0, gradient_certified=True,
        beta_distance_actual_bound_l2=0.0,
        beta_distance_acceptance_ceiling_l2=(
            sh.OPTIMIZER_BETA_DISTANCE_BOUND_L2
        ),
        iterations=23, function_evaluations=29, gradient_evaluations=31,
        message="synthetic exact result",
    )


def test_finite_optimizer_refusal_preserves_receiptable_result(monkeypatch):
    native = _native(6)
    z = np.zeros((6, 4), dtype=np.float64)
    y = np.arange(6) % 3
    beta = np.zeros(8, dtype=np.float64)
    objective, gradient = sh._tilt_loss_gradient(beta, native, z, y)
    result = SimpleNamespace(
        success=False, status=2,
        x=beta, fun=objective, jac=gradient,
        nit=10_000, nfev=10_111, njev=10_111,
        message="synthetic iteration limit",
    )
    monkeypatch.setattr(sh, "minimize", lambda *args, **kwargs: result)
    with pytest.raises(sh._TiltOptimizerFailure) as caught:
        sh._fit_residual_tilt(
            native, z, y,
        )
    fit = caught.value.fit
    assert fit == sh.TiltFit(
        success=False, status=2,
        beta=tuple(float(value) for value in result.x), objective=objective,
        independent_objective=objective, objective_consistent=True,
        gradient=tuple(float(value) for value in result.jac),
        independent_gradient=tuple(float(value) for value in gradient),
        gradient_consistent=True,
        independent_gradient_max_abs=0.0, gradient_certified=True,
        beta_distance_actual_bound_l2=0.0,
        beta_distance_acceptance_ceiling_l2=(
            sh.OPTIMIZER_BETA_DISTANCE_BOUND_L2
        ),
        iterations=10_000, function_evaluations=10_111,
        gradient_evaluations=10_111, message="synthetic iteration limit",
    )
    assert isinstance(caught.value, sh.FitFailure)
    intent = _synthetic_optimizer_intent()
    intent_raw = runner._canonical_bytes(intent)
    intent_digest = hashlib.sha256(intent_raw).hexdigest()
    intent_record = {
        "path": (
            f"{sh.SHOTS_ARTIFACT_ROOT}/"
            f"{runner._k2_filename('optimizer_intent', intent_digest)}"
        ),
        "sha256": intent_digest,
        "bytes": len(intent_raw),
        "schema": runner._k2_schemas()["optimizer_intent"],
    }
    receipt = runner._make_optimizer_receipt_from_fit(
        intent_record=intent_record, intent=intent, fit=fit,
    )
    assert receipt["success"] is False
    assert receipt["status"] == 2
    assert receipt["beta"] == list(fit.beta)
    assert receipt["gradient"] == list(fit.gradient)
    assert receipt["independent_gradient"] == list(fit.independent_gradient)


def test_scipy_success_without_amendment_gradient_certificate_is_receiptable(
    monkeypatch,
):
    native = _native(6)
    z = np.zeros((6, 4), dtype=np.float64)
    y = np.arange(6) % 3
    beta = np.full(8, 2e-5, dtype=np.float64)
    objective, gradient = sh._tilt_loss_gradient(beta, native, z, y)
    result = SimpleNamespace(
        success=True, status=0, x=beta, fun=objective, jac=gradient,
        nit=4, nfev=5, njev=5, message="synthetic ftol convergence",
    )
    monkeypatch.setattr(sh, "minimize", lambda *args, **kwargs: result)
    with pytest.raises(sh._TiltOptimizerFailure) as caught:
        sh._fit_residual_tilt(native, z, y)
    fit = caught.value.fit
    assert fit.success is True
    assert fit.gradient_certified is False
    assert fit.independent_gradient_max_abs == pytest.approx(2e-5)


@pytest.mark.parametrize("mismatch", ["objective", "gradient"])
def test_finite_optimizer_recomputation_mismatch_remains_receiptable(
    monkeypatch, mismatch,
):
    native = _native(6)
    z = np.zeros((6, 4), dtype=np.float64)
    y = np.arange(6) % 3
    beta = np.zeros(8, dtype=np.float64)
    objective, gradient = sh._tilt_loss_gradient(beta, native, z, y)
    reported_objective = objective + (1.0 if mismatch == "objective" else 0.0)
    reported_gradient = gradient.copy()
    if mismatch == "gradient":
        reported_gradient[0] += 1.0
    result = SimpleNamespace(
        success=True, status=0, x=beta, fun=reported_objective,
        jac=reported_gradient, nit=1, nfev=2, njev=2,
        message="synthetic inconsistent finite result",
    )
    monkeypatch.setattr(sh, "minimize", lambda *args, **kwargs: result)
    with pytest.raises(sh._TiltOptimizerFailure) as caught:
        sh._fit_residual_tilt(native, z, y)
    fit = caught.value.fit
    assert fit.objective == reported_objective
    assert fit.gradient == tuple(float(value) for value in reported_gradient)
    assert fit.independent_objective == objective
    assert fit.independent_gradient == tuple(float(value) for value in gradient)
    assert fit.objective_consistent is (mismatch != "objective")
    assert fit.gradient_consistent is (mismatch != "gradient")


@pytest.mark.parametrize(("field", "bad_value", "message"), [
    ("success", 1, "success/status"),
    ("status", np.int64(0), "success/status"),
    ("x", np.zeros(7, dtype=np.float64), "coefficient vector"),
    ("x", np.zeros(8, dtype=np.float32), "coefficient vector"),
    ("jac", np.zeros(7, dtype=np.float64), "gradient vector"),
    ("jac", np.full(8, np.nan, dtype=np.float64), "L-BFGS-B failed"),
    ("fun", "1.0", "objective type"),
    ("nit", 0.0, "evaluation counts"),
    ("nfev", 0, "evaluation counts"),
    ("njev", 0, "evaluation counts"),
    ("message", b"not text", "message type"),
])
def test_optimizer_refuses_malformed_result_provenance(
    monkeypatch, field, bad_value, message,
):
    result = SimpleNamespace(
        success=True, status=0, x=np.zeros(8, dtype=np.float64), fun=1.0,
        jac=np.zeros(8, dtype=np.float64), nit=0, nfev=1, njev=1,
        message="synthetic result",
    )
    setattr(result, field, bad_value)
    monkeypatch.setattr(sh, "minimize", lambda *args, **kwargs: result)
    with pytest.raises(sh.FitFailure, match=message):
        sh._fit_residual_tilt(
            _native(6), np.zeros((6, 4), dtype=np.float64), np.arange(6) % 3,
        )


def test_canary_3_outcomes_cannot_change_predictions_but_training_control_moves_beta():
    rng = np.random.default_rng(23)
    z = rng.normal(size=(60, 4))
    native = _native(60)
    beta = np.linspace(-0.2, 0.2, 8)
    original_y = np.arange(60) % 3
    changed_y = (original_y + 1) % 3
    before = sh._transform_probabilities(native, z, beta)
    after = sh._transform_probabilities(native, z, beta)  # y is not an input
    np.testing.assert_array_equal(before, after)
    fit_a = sh._fit_residual_tilt(native, z, original_y)
    fit_b = sh._fit_residual_tilt(native, z, changed_y)
    assert np.max(np.abs(fit_a.matrix() - fit_b.matrix())) > 1e-9


def test_canary_5_zero_tilt_is_native_and_positive_coefficient_moves_home():
    native = np.array([[0.5, 0.3, 0.2]], dtype=float)
    z = np.array([[1.0, 0.0, 0.0, 0.0]])
    identity = sh._transform_probabilities(native, z, np.zeros(8))
    np.testing.assert_allclose(identity, native, rtol=0, atol=1e-12)
    beta = np.zeros((2, 4))
    beta[0, 0] = 0.1
    moved = sh._transform_probabilities(native, z, beta)
    assert moved[0, 0] - identity[0, 0] > 1e-9


def test_zero_tilt_uses_normalized_model_native_without_repairing_storage():
    stored = np.array([[0.33333333, 0.33333333, 0.33333333]])
    before = stored.copy()
    expected_model = stored / stored.sum(axis=1, keepdims=True)
    candidate = sh._transform_probabilities(
        stored, np.zeros((1, 4)), np.zeros(8),
    )
    np.testing.assert_allclose(candidate, expected_model, rtol=0, atol=1e-12)
    np.testing.assert_array_equal(stored, before)


@pytest.mark.parametrize("stored", [
    np.array([[0.33333332, 0.33333334, 0.33333333]]),
    np.array([[0.33333334, 0.33333334, 0.33333333]]),
])
def test_stored_native_accepts_both_one_tick_sum_directions(stored):
    checked = sh._check_stored_native_probabilities(
        stored, label="one-tick stored native",
    )
    np.testing.assert_array_equal(checked, stored)


@pytest.mark.parametrize("stored", [
    np.array([[0.33333332, 0.33333332, 0.33333332]]),
    np.array([[0.33333334, 0.33333334, 0.33333334]]),
    np.array([[0.333333331, 0.33333333, 0.33333334]]),
])
def test_stored_native_rejects_two_ticks_or_non_eight_decimal_cells(stored):
    with pytest.raises(sh.ProbabilityInvalid):
        sh._check_stored_native_probabilities(
            stored, label="invalid stored native",
        )


@pytest.mark.parametrize("bad", [
    np.array([[0.5, 0.5, 0.1]]),
    np.array([[0.5, 0.5, 0.0]]),
    np.array([[np.nan, 0.5, 0.5]]),
])
def test_native_probability_validation_is_exact_and_typed(bad):
    with pytest.raises(sh.ProbabilityInvalid):
        sh._transform_probabilities(bad, np.zeros((1, 4)), np.zeros(8))


# ==========================================================================
# 4. Fixture/RPS/bootstrap arithmetic and canaries 4 and 7
# ==========================================================================

def _score_inputs():
    ids = ("m1", "m2", "m3")
    candidate = np.array([[0.6, 0.2, 0.2],
                          [0.2, 0.6, 0.2],
                          [0.2, 0.2, 0.6]])
    native = np.full((3, 3), 0.33333333)
    market = np.array([[0.5, 0.25, 0.25],
                       [0.25, 0.5, 0.25],
                       [0.25, 0.25, 0.5]])
    y = np.array([0, 1, 2])
    return ids, candidate, native, market, y


def test_paired_rps_matches_hand_formula_and_keeps_per_fixture_deltas():
    ids, candidate, native, market, y = _score_inputs()
    scores = sh._paired_rps_unchecked(
        candidate, native, market, y,
        candidate_ids=ids, native_ids=ids, market_ids=ids, outcome_ids=ids,
        expected_ids=ids,
    )
    expected_candidate = np.array([0.10, 0.04, 0.10])
    np.testing.assert_allclose(scores.candidate_rps, expected_candidate)
    assert scores.mean_d_native == pytest.approx(
        np.mean(expected_candidate - sh._rps(native, y))
    )
    np.testing.assert_allclose(
        scores.d_market,
        expected_candidate - np.array([0.15625, 0.0625, 0.15625]),
    )


def test_native_comparator_rps_uses_stored_cells_while_other_simplexes_stay_strict():
    ids = ("m1",)
    stored_native = np.array([[0.6, 0.2, 0.19999999]])
    candidate = np.array([[0.6, 0.2, 0.2]])
    market = np.array([[0.5, 0.25, 0.25]])
    y = np.array([0])
    scores = sh._paired_rps_unchecked(
        candidate, stored_native, market, y,
        candidate_ids=ids, native_ids=ids, market_ids=ids,
        outcome_ids=ids, expected_ids=ids,
    )
    expected_stored = sh._rps(stored_native, y)[0]
    normalized = stored_native / stored_native.sum(axis=1, keepdims=True)
    assert scores.native_rps[0] == expected_stored
    assert scores.native_rps[0] != sh._rps(normalized, y)[0]

    off_simplex = np.array([[0.33333333, 0.33333333, 0.33333333]])
    with pytest.raises(sh.ProbabilityInvalid):
        sh._paired_rps_unchecked(
            off_simplex, stored_native, market, y,
            candidate_ids=ids, native_ids=ids, market_ids=ids,
            outcome_ids=ids, expected_ids=ids,
        )
    with pytest.raises(sh.ProbabilityInvalid):
        sh._paired_rps_unchecked(
            candidate, stored_native, off_simplex, y,
            candidate_ids=ids, native_ids=ids, market_ids=ids,
            outcome_ids=ids, expected_ids=ids,
        )


def test_canary_4_market_changes_benchmark_delta_not_challenger_prediction():
    ids, candidate, native, market, y = _score_inputs()
    candidate_before = candidate.copy()
    first = sh._paired_rps_unchecked(
        candidate, native, market, y,
        candidate_ids=ids, native_ids=ids, market_ids=ids, outcome_ids=ids,
        expected_ids=ids,
    )
    changed_market = np.array([[0.4, 0.3, 0.3],
                               [0.3, 0.4, 0.3],
                               [0.3, 0.3, 0.4]])
    second = sh._paired_rps_unchecked(
        candidate, native, changed_market, y,
        candidate_ids=ids, native_ids=ids, market_ids=ids, outcome_ids=ids,
        expected_ids=ids,
    )
    np.testing.assert_array_equal(candidate, candidate_before)
    assert first.candidate_rps == second.candidate_rps
    assert first.d_market != second.d_market


def test_canary_7_canonical_fixture_set_passes_and_drop_duplicate_reorder_refuse():
    ids = ("a", "b", "c")
    assert sh.assert_fixture_sets(
        candidate_ids=ids, native_ids=ids, market_ids=ids,
        outcome_ids=ids, expected_ids=ids,
    ) == ids
    with pytest.raises(sh.FixtureSetMismatch):
        sh.assert_fixture_sets(candidate_ids=ids, native_ids=ids[:-1],
                               market_ids=ids, outcome_ids=ids)
    with pytest.raises(sh.FixtureSetMismatch):
        sh.assert_fixture_sets(candidate_ids=ids, native_ids=("a", "a", "c"),
                               market_ids=ids, outcome_ids=ids)
    with pytest.raises(sh.FixtureSetMismatch):
        sh.assert_fixture_sets(candidate_ids=ids, native_ids=("b", "a", "c"),
                               market_ids=ids, outcome_ids=ids)


def test_week_and_season_bootstraps_are_paired_seeded_and_fixture_weighted():
    delta = np.array([-0.03, -0.01, 0.02, 0.04, -0.02])
    weeks = np.array(["w1", "w1", "w2", "w3", "w3"])
    seasons = np.array(["s1", "s1", "s1", "s2", "s2"])
    week_a = sh._block_bootstrap(delta, weeks, seed=sh.WEEK_BOOTSTRAP_SEED)
    week_b = sh._block_bootstrap(delta, weeks, seed=sh.WEEK_BOOTSTRAP_SEED)
    season_a = sh._block_bootstrap(delta, seasons, seed=sh.SEASON_BOOTSTRAP_SEED)
    season_b = sh._block_bootstrap(delta, seasons, seed=sh.SEASON_BOOTSTRAP_SEED)
    assert week_a == week_b
    assert season_a == season_b
    assert week_a.mean == pytest.approx(delta.mean())
    assert week_a.n_blocks == 3 and week_a.n_boot == 10_000
    assert week_a.seed == 20260831
    assert season_a.n_blocks == 2 and season_a.seed == 20260832
    assert sh._per_season_means_unchecked(delta, seasons) == pytest.approx({
        "s1": (-0.03 - 0.01 + 0.02) / 3,
        "s2": (0.04 - 0.02) / 2,
    })


# ==========================================================================
# 5. Non-self-referential H-manifest verification hooks
# ==========================================================================

def test_canonical_manifest_bytes_are_strict_ascii_json():
    assert sh.canonical_manifest_bytes({"z": "雪", "a": [1, True, None]}) == (
        b'{"a":[1,true,null],"z":"\\u96ea"}\n'
    )
    with pytest.raises(ValueError):
        sh.canonical_manifest_bytes({"not_finite": float("nan")})
    with pytest.raises(ValueError):
        sh.canonical_manifest_bytes({"not_finite": float("inf")})
    with pytest.raises(TypeError):
        sh.canonical_manifest_bytes({"must_not_stringify": Path("value")})


def test_runtime_dependency_closure_hashes_the_active_repo_modules_freshly():
    first = sh._runtime_dependency_closure(paths.REPO_ROOT)
    expected = {"epl.paths": "epl/paths.py", "epl.teams": "epl/teams.py"}
    assert set(first) == set(expected)
    for name, relative in expected.items():
        source = paths.REPO_ROOT / relative
        assert first[name] == {
            "path": relative,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "bytes": source.stat().st_size,
        }
    first["epl.paths"]["sha256"] = "0" * 64
    assert sh._runtime_dependency_closure(paths.REPO_ROOT)["epl.paths"][
        "sha256"
    ] != "0" * 64


def test_real_h_invariants_are_exact_and_use_identity_only_projections(monkeypatch):
    required = [
        *(paths.RAW_DIR / name for name in sh.RAW_DIGESTS),
        paths.MATCHES_PARQUET,
        paths.FIT_DIR / "walkforward_predictions.parquet",
    ]
    if not all(path.is_file() for path in required):
        pytest.skip("pinned EPL raw/archive artifacts are not present")

    original = pd.read_parquet
    projected = []

    def identity_only(*args, **kwargs):
        columns = tuple(kwargs.get("columns", ()))
        projected.append(columns)
        forbidden = {
            "fthg", "ftag", "ftr", "y", "dc_home", "dc_draw", "dc_away",
            "market_home", "market_draw", "market_away", "dc_rps",
            "market_rps",
        }
        assert forbidden.isdisjoint({str(column).lower() for column in columns})
        return original(*args, **kwargs)

    monkeypatch.setattr(sh.pd, "read_parquet", identity_only)
    invariants = sh._fixed_h_invariants(paths.REPO_ROOT)
    assert invariants == {
        "schema": "epl-shots-h-invariants-1",
        "raw_rows": 4_180,
        "clean_rows": 4_179,
        "quarantine_identity": {
            "date": "2021-08-15", "home_key": "newcastle",
            "away_key": "west_ham", "values": [17.0, 8.0, 3.0, 9.0],
            "reason": "AST>AS", "source": "E0_2122.csv", "raw_row": 10,
            "match_id": "57b6538de8a5404c",
        },
        "training_universe_rows": 1_900,
        "training_schedule": {
            "rows": 1_520, "blocks": 142,
            "sha256": "a30d2faed039a95bde0fded942025d5c853e1aed6d3d78720216d86b18e739a6",
        },
        "decision_schedule": {
            "rows": 2_280, "blocks": 212,
            "sha256": "99a0df46f14039891a0ef4882ad10ee63297b9763fb2313543d0b759da9f57a8",
        },
    }
    assert projected == [
        ("match_id", "season_code", "date", "home_key", "away_key"),
        ("match_id", "season", "date", "home_key", "away_key"),
        ("match_id", "season", "date", "block"),
        ("match_id", "season", "date", "home_key", "away_key", "block"),
    ]


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(root), *args), check=True,
        capture_output=True, text=True,
    )
    return result.stdout.strip()


def _fixed_snapshot() -> dict:
    runtime_payload = {
        "schema": runner._NATIVE_RUNTIME_CLOSURE_SCHEMA,
        "tree_digest_schema": runner._NATIVE_RUNTIME_TREE_SCHEMA,
        "sealed_read_roots": list(runner._NATIVE_SEALED_READ_ROOTS),
        "system_read_literals": [{
            "logical_path": str(literal), "resolved_path": str(literal),
            "link_chain": [], "mode": 0o444, "bytes": 1,
            "sha256": "7" * 64,
        } for literal in runner._NATIVE_SYSTEM_READ_LITERALS],
        "mutable_roots": [{
            "logical_path": "/synthetic/runtime",
            "resolved_path": "/synthetic/runtime",
            "link_chain": [], "tree_sha256": "6" * 64,
            "files": 1, "directories": 1, "symlinks": 0, "bytes": 1,
        }],
        "executables": [{
            "logical_path": "/synthetic/python",
            "resolved_path": "/synthetic/python",
            "link_chain": [], "mode": 0o755, "bytes": 1,
            "sha256": "7" * 64,
        }],
        "platform": {
            "architecture": "synthetic-arm64",
            "kernel_release": "synthetic-kernel",
            "sw_vers": "synthetic macOS",
            "root_mount": "/dev/synthetic on / (apfs, sealed, read-only)",
            "sdk_logical_path": "/synthetic/SDK",
            "sdk_resolved_path": "/synthetic/SDK",
            "sdk_link_chain": [], "clang_version": "synthetic clang",
        },
        "file_count": 1, "directory_count": 1,
        "symlink_count": 0, "bytes": 1,
    }
    runtime_lock = {
        **runtime_payload,
        "sha256": hashlib.sha256(
            sh.canonical_manifest_bytes(runtime_payload)
        ).hexdigest(),
    }
    return {
        "data_identities": {"raw": {"path": "pins/raw", "sha256": "a" * 64}},
        "config_identities": {"config": {"path": "pins/config", "sha256": "b" * 64}},
        "dependency_identities": {"deps": {"path": "pins/deps", "sha256": "c" * 64}},
        "runtime_dependency_closure": {
            "epl.paths": {"path": "epl/paths.py", "sha256": "d" * 64,
                          "bytes": 1},
            "epl.teams": {"path": "epl/teams.py", "sha256": "e" * 64,
                          "bytes": 1},
        },
        "native_runtime_lock": runtime_lock,
        "native_contract": {
            "parent_commit": sh.NATIVE_PARENT_COMMIT,
            "code_family_sha256": sh.NATIVE_CODE_FAMILY_SHA256,
            "native_stored_sum_tolerance": sh.NATIVE_STORED_SUM_TOLERANCE,
            "model_probability_sum_tolerance": (
                sh.MODEL_PROBABILITY_SUM_TOLERANCE
            ),
            "native_last_cell_repair": False,
            "optimizer_independent_gradient_tolerance": (
                sh.OPTIMIZER_GRADIENT_TOLERANCE
            ),
            "optimizer_beta_distance_bound_l2": (
                sh.OPTIMIZER_BETA_DISTANCE_BOUND_L2
            ),
            "amendment_1_commit": sh.AMENDMENT_1_COMMIT,
            "amendment_1_path": sh.AMENDMENT_1_PATH,
            "amendment_1_sha256": sh.AMENDMENT_1_SHA256,
            "amendment_2_commit": sh.AMENDMENT_2_COMMIT,
            "amendment_2_path": sh.AMENDMENT_2_PATH,
            "amendment_2_sha256": sh.AMENDMENT_2_SHA256,
        },
        "resolved_packages": {"python": "test", "numpy": "test"},
        "h_invariants": {
            "schema": "epl-shots-h-invariants-1",
            "raw_rows": 4_180, "clean_rows": 4_179,
            "quarantine_identity": sh._expected_quarantine_identity(),
            "training_universe_rows": 1_900,
            "training_schedule": {"rows": 1_520, "blocks": 142,
                                  "sha256": "1" * 64},
            "decision_schedule": {"rows": 2_280, "blocks": 212,
                                  "sha256": "2" * 64},
        },
    }


def _bind_current_receipts(manifest: dict, *, defects: list | None = None) -> dict:
    """Build a structurally valid synthetic receipt for manifest unit tests."""
    bound = json.loads(json.dumps(manifest))
    subject = sh._expected_receipt_subject(bound)
    subject_sha256 = sh._canonical_sha256(sh.H_RECEIPT_SUBJECT_SCHEMA, subject)
    events = sh._expected_canary_events()
    n_events = len(events)
    counts = {
        "expected": n_events, "collected": n_events, "passed": n_events,
        "failed": 0, "skipped": 0, "xfailed": 0, "xpassed": 0,
        "deselected": 0,
    }
    result = {
        "events": events, "counts": counts,
        "real_validation": bound["h_invariants"],
    }
    semantic_sha256 = sh._canonical_sha256(
        "epl-shots-canary-semantic-result-1", result,
    )
    bound.update({
        "receipt_subject": subject,
        "receipt_subject_sha256": subject_sha256,
        "canary_receipt": {
            "schema": sh.H_CANARY_RECEIPT_SCHEMA,
            "subject_sha256": subject_sha256,
            "execution": sh._expected_canary_execution(bound, subject),
            "events": events,
            "counts": counts,
            "real_validation": bound["h_invariants"],
            "semantic_result_sha256": semantic_sha256,
            "pass": True,
        },
        "audit_receipt": {
            "schema": sh.H_AUDIT_RECEIPT_SCHEMA,
            "subject_sha256": subject_sha256,
            "canary_result_sha256": semantic_sha256,
            "reviewer": {
                "name": "Synthetic Auditor",
                "identity": "shots-test@example.invalid",
            },
            "scope": sh._expected_audit_scope(),
            "deliberate_failures": [{
                **case, "expected": "typed refusal or moving control",
                "observed": "typed refusal or moving control", "pass": True,
            } for case in sh._expected_deliberate_failure_ids()],
            "defects": json.loads(json.dumps(defects)) if defects else [],
            "disposition": "PASS",
            "pass": True,
        },
        "smoke_receipt": _synthetic_smoke_receipt_for(bound),
    })
    return bound


def _synthetic_smoke_receipt_for(bound: dict) -> dict:
    """Bind the example smoke receipt to a synthetic candidate manifest."""
    receipt = json.loads(json.dumps(
        runner._make_example_smoke_receipt_for_tests()
    ))
    receipt["amendment_3_commit"] = sh.AMENDMENT_3_COMMIT
    receipt["amendment_3_sha256"] = sh.AMENDMENT_3_SHA256
    receipt["candidate_files"] = {
        relative: {"sha256": record["sha256"]}
        for relative, record in bound["files"].items()
    }
    receipt["native_runtime_lock_sha256"] = (
        bound["native_runtime_lock"]["sha256"]
    )
    return receipt


def _h_repo(tmp_path: Path, monkeypatch, *, defects: list | None = None):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "shots-test@example.invalid")
    _git(tmp_path, "config", "user.name", "Shots Test")
    # Governance lineage mirrors the real repo: Amendment 1, then Amendment 2
    # as its sole child, and H' hangs off Amendment 2.
    amendment_raw = b"synthetic amendment 1\n"
    amendment_path = tmp_path / sh.AMENDMENT_1_PATH
    amendment_path.parent.mkdir(parents=True)
    amendment_path.write_bytes(amendment_raw)
    (tmp_path / "anchor.txt").write_text("parent\n")
    _git(tmp_path, "add", "anchor.txt", sh.AMENDMENT_1_PATH)
    _git(tmp_path, "commit", "-q", "-m", "amendment 1")
    amendment_1_commit = _git(tmp_path, "rev-parse", "HEAD")
    amendment_1_tree = _git(tmp_path, "rev-parse", "HEAD^{tree}")
    monkeypatch.setattr(sh, "AMENDMENT_1_COMMIT", amendment_1_commit)
    monkeypatch.setattr(sh, "AMENDMENT_1_TREE", amendment_1_tree)
    monkeypatch.setattr(
        sh, "AMENDMENT_1_SHA256", hashlib.sha256(amendment_raw).hexdigest(),
    )
    amendment_2_raw = b"synthetic amendment 2\n"
    amendment_2_path = tmp_path / sh.AMENDMENT_2_PATH
    amendment_2_path.write_bytes(amendment_2_raw)
    _git(tmp_path, "add", sh.AMENDMENT_2_PATH)
    _git(tmp_path, "commit", "-q", "-m", "amendment 2")
    amendment_2_commit = _git(tmp_path, "rev-parse", "HEAD")
    amendment_2_tree = _git(tmp_path, "rev-parse", "HEAD^{tree}")
    monkeypatch.setattr(sh, "AMENDMENT_2_COMMIT", amendment_2_commit)
    monkeypatch.setattr(sh, "AMENDMENT_2_TREE", amendment_2_tree)
    monkeypatch.setattr(
        sh, "AMENDMENT_2_SHA256", hashlib.sha256(amendment_2_raw).hexdigest(),
    )
    # H' — the superseded-for-execution freeze record — hangs off Amendment 2
    # and stays in history untouched; its blobs are the record the Amendment 3
    # parent tree must carry.
    (tmp_path / "epl/tests").mkdir(parents=True)
    (tmp_path / "epl/shots.py").write_text("one\n")
    (tmp_path / "epl/shots_harness.py").write_text("runner\n")
    (tmp_path / "epl/tests/test_shots.py").write_text("two\n")
    h_prime_manifest_raw = b'{"synthetic": "h-prime manifest record"}\n'
    record_path = tmp_path / sh.H_MANIFEST_PATH
    record_path.parent.mkdir(parents=True)
    record_path.write_bytes(h_prime_manifest_raw)
    _git(tmp_path, "add", *sh.H_REQUIRED_FILES, sh.H_MANIFEST_PATH)
    _git(tmp_path, "commit", "-q", "-m", "H-prime")
    monkeypatch.setattr(
        sh, "H_PRIME_COMMIT", _git(tmp_path, "rev-parse", "HEAD"),
    )
    monkeypatch.setattr(
        sh, "H_PRIME_MANIFEST_SHA256",
        hashlib.sha256(h_prime_manifest_raw).hexdigest(),
    )
    # Amendment 3 is the governance parent of H''.
    amendment_3_raw = b"synthetic amendment 3\n"
    (tmp_path / sh.AMENDMENT_3_PATH).write_bytes(amendment_3_raw)
    _git(tmp_path, "add", sh.AMENDMENT_3_PATH)
    _git(tmp_path, "commit", "-q", "-m", "amendment 3")
    parent = _git(tmp_path, "rev-parse", "HEAD")
    parent_tree = _git(tmp_path, "rev-parse", "HEAD^{tree}")
    monkeypatch.setattr(sh, "AMENDMENT_3_COMMIT", parent)
    monkeypatch.setattr(sh, "AMENDMENT_3_TREE", parent_tree)
    monkeypatch.setattr(
        sh, "AMENDMENT_3_SHA256", hashlib.sha256(amendment_3_raw).hexdigest(),
    )
    # The H'' candidates modify the frozen record in the working tree.
    (tmp_path / "epl/shots.py").write_text("one amended\n")
    (tmp_path / "epl/shots_harness.py").write_text("runner amended\n")
    (tmp_path / "epl/tests/test_shots.py").write_text("two amended\n")
    fixed = _fixed_snapshot()

    def synthetic_fixed_identity(root):
        root = Path(root).resolve()
        amendment_commit = sh._git_text(
            root, "rev-parse", f"{sh.AMENDMENT_1_COMMIT}^{{commit}}",
        )
        amendment_tree = sh._git_text(
            root, "rev-parse", f"{sh.AMENDMENT_1_COMMIT}^{{tree}}",
        )
        amendment_blob = sh._git_bytes(
            root, "show", f"{sh.AMENDMENT_1_COMMIT}:{sh.AMENDMENT_1_PATH}",
        )
        current_amendment = (root / sh.AMENDMENT_1_PATH).read_bytes()
        if (amendment_commit != sh.AMENDMENT_1_COMMIT
                or amendment_tree != sh.AMENDMENT_1_TREE
                or hashlib.sha256(amendment_blob).hexdigest()
                    != sh.AMENDMENT_1_SHA256
                or amendment_blob != current_amendment):
            raise sh.LockMismatch(
                "the committed Amendment 1 commit/tree/hash/bytes differ"
            )
        amendment_2_commit = sh._git_text(
            root, "rev-parse", f"{sh.AMENDMENT_2_COMMIT}^{{commit}}",
        )
        amendment_2_tree = sh._git_text(
            root, "rev-parse", f"{sh.AMENDMENT_2_COMMIT}^{{tree}}",
        )
        amendment_2_blob = sh._git_bytes(
            root, "show", f"{sh.AMENDMENT_2_COMMIT}:{sh.AMENDMENT_2_PATH}",
        )
        current_amendment_2 = (root / sh.AMENDMENT_2_PATH).read_bytes()
        if (amendment_2_commit != sh.AMENDMENT_2_COMMIT
                or amendment_2_tree != sh.AMENDMENT_2_TREE
                or hashlib.sha256(amendment_2_blob).hexdigest()
                    != sh.AMENDMENT_2_SHA256
                or amendment_2_blob != current_amendment_2):
            raise sh.LockMismatch(
                "the committed Amendment 2 commit/tree/hash/bytes differ"
            )
        amendment_3_commit = sh._git_text(
            root, "rev-parse", f"{sh.AMENDMENT_3_COMMIT}^{{commit}}",
        )
        amendment_3_tree = sh._git_text(
            root, "rev-parse", f"{sh.AMENDMENT_3_COMMIT}^{{tree}}",
        )
        amendment_3_blob = sh._git_bytes(
            root, "show", f"{sh.AMENDMENT_3_COMMIT}:{sh.AMENDMENT_3_PATH}",
        )
        current_amendment_3 = (root / sh.AMENDMENT_3_PATH).read_bytes()
        if (amendment_3_commit != sh.AMENDMENT_3_COMMIT
                or amendment_3_tree != sh.AMENDMENT_3_TREE
                or hashlib.sha256(amendment_3_blob).hexdigest()
                    != sh.AMENDMENT_3_SHA256
                or amendment_3_blob != current_amendment_3):
            raise sh.LockMismatch(
                "the committed Amendment 3 commit/tree/hash/bytes differ"
            )
        return json.loads(json.dumps(fixed))

    monkeypatch.setattr(sh, "_fixed_identity_snapshot", synthetic_fixed_identity)
    files = {}
    for relative in sh.H_REQUIRED_FILES:
        path = tmp_path / relative
        files[relative] = {
            "sha256": sh.sha256_file(path), "bytes": path.stat().st_size,
            "lines": len(path.read_text().splitlines()),
        }
    candidate = _bind_current_receipts({
        "schema": sh.H_MANIFEST_SCHEMA, "harness_frozen": True,
        "freeze_parent_commit": parent, "freeze_parent_tree": parent_tree,
        "files": files, **fixed,
        "output_schemas": sh._expected_h_output_schemas(),
    }, defects=defects)
    manifest = sh.make_harness_manifest(
        repo_root=tmp_path,
        freeze_parent_commit=parent,
        freeze_parent_tree=parent_tree,
        data_identities=fixed["data_identities"],
        config_identities=fixed["config_identities"],
        dependency_identities=fixed["dependency_identities"],
        resolved_packages=fixed["resolved_packages"],
        canary_receipts=candidate["canary_receipt"],
        audit_receipt=candidate["audit_receipt"],
        smoke_receipt=candidate["smoke_receipt"],
    )
    assert manifest == candidate
    manifest_path = tmp_path / sh.H_MANIFEST_PATH
    manifest_path.write_bytes(sh.canonical_manifest_bytes(manifest))
    # Amendment 3 §C7.2: H'' modifies the four freeze paths, never adds.
    _git(tmp_path, "add", *sh.H_REQUIRED_FILES, sh.H_MANIFEST_PATH)
    _git(tmp_path, "commit", "-q", "-m", "H")
    h_commit = _git(tmp_path, "rev-parse", "HEAD")
    return manifest, h_commit, parent, parent_tree


def test_h_manifest_is_commit_bound_non_self_referential_and_descendant_safe(
    tmp_path, monkeypatch,
):
    manifest, h_commit, parent, parent_tree = _h_repo(tmp_path, monkeypatch)
    assert manifest["harness_frozen"] is True
    assert "harness_freeze_commit" not in manifest
    assert "manifest_sha256" not in manifest
    status = sh.require_harness_manifest(
        manifest, repo_root=tmp_path, harness_commit=h_commit,
        expected_parent_commit=parent, expected_parent_tree=parent_tree,
    )
    assert status["frozen"]
    assert "gate" not in status

    (tmp_path / "result.txt").write_text("descendant artifact\n")
    _git(tmp_path, "add", "result.txt")
    _git(tmp_path, "commit", "-q", "-m", "descendant")
    assert sh.require_harness_manifest(
        manifest, repo_root=tmp_path, harness_commit=h_commit,
    )["frozen"]

    (tmp_path / "epl/shots.py").write_text("mutated\n")
    with pytest.raises(sh.LockMismatch, match="bytes differ"):
        sh.require_harness_manifest(
            manifest, repo_root=tmp_path, harness_commit=h_commit,
        )


def test_amendment_1_governance_and_receipt_versions_are_exact():
    root = paths.REPO_ROOT
    amendment_blob = sh._git_bytes(
        root, "show", f"{sh.AMENDMENT_1_COMMIT}:{sh.AMENDMENT_1_PATH}",
    )
    assert sh.AMENDMENT_1_COMMIT == (
        "bd7431295a1b366a86324ca00e85a8fe524e2876"
    )
    assert sh.AMENDMENT_1_TREE == (
        "dee4fcf2c4cfc9301e87a1badd50198f9eef4854"
    )
    assert sh.AMENDMENT_1_SHA256 == (
        "a563882f8698efa60440ed47c24e4854b4c1cd8d1dd59b5311bb0ed54cdb26b9"
    )
    assert sh._git_text(
        root, "rev-parse", f"{sh.AMENDMENT_1_COMMIT}^{{commit}}",
    ) == sh.AMENDMENT_1_COMMIT
    assert sh._git_text(
        root, "rev-parse", f"{sh.AMENDMENT_1_COMMIT}^{{tree}}",
    ) == sh.AMENDMENT_1_TREE
    assert hashlib.sha256(amendment_blob).hexdigest() == sh.AMENDMENT_1_SHA256
    assert amendment_blob == (root / sh.AMENDMENT_1_PATH).read_bytes()

    assert sh.H_MANIFEST_SCHEMA == "epl-shots-harness-manifest-5"
    assert sh.H_RECEIPT_SUBJECT_SCHEMA == "epl-shots-pre-h-subject-4"
    assert sh.H_CANARY_RECEIPT_SCHEMA == "epl-shots-canary-receipt-3"
    assert sh.H_AUDIT_RECEIPT_SCHEMA == (
        "epl-shots-adversarial-audit-receipt-4"
    )
    assert sh.AUDIT_DEFECT_SEVERITIES == ("blocking", "non_blocking")
    output_schemas = sh._expected_h_output_schemas()
    assert output_schemas["native_block"]["schema"] == (
        "epl-shots-native-training-block-2"
    )
    assert output_schemas["training_predictions"]["schema"] == (
        "epl-shots-training-predictions-2"
    )
    assert output_schemas["feature_moments"]["schema"] == (
        "epl-shots-feature-moments-2"
    )
    assert output_schemas["coefficients"]["schema"] == (
        "epl-shots-coefficients-2"
    )
    assert output_schemas["optimizer_receipt"]["schema"] == (
        "epl-shots-optimizer-receipt-3"
    )
    assert sh.CANARY_NAMES[-1] == "amendment_1_contract"
    amendment_cases = sh._expected_canary_test_plan()["canaries"][
        "amendment_1_contract"
    ]
    assert len(amendment_cases) == 9
    assert {case["control"] for case in amendment_cases} == {
        "negative", "positive",
    }


def test_amendment_2_governance_binding_is_exact_and_gates_the_freeze():
    """H' hangs off Amendment 2, and both amendment shas ride in the manifest.

    Amendment 2 B2 disclosed that the audited candidates still pinned the
    freeze parent to the Amendment 1 commit.  The owner's freeze authorization
    naming Amendment 2 re-binds the parent gates here; Amendment 1 remains
    bound and verified, so the frozen bytes carry both governance shas.
    """
    root = paths.REPO_ROOT
    assert sh.AMENDMENT_2_COMMIT == (
        "d4d2ce3d7b5fcb84545e83fed7cd4846129cad70"
    )
    assert sh.AMENDMENT_2_TREE == (
        "bbbef6b36e177c42200a7e05f17b741ca09e206c"
    )
    assert sh.AMENDMENT_2_PATH == "reports/epl_shots_prereg_amendment_2.md"
    assert sh.AMENDMENT_2_SHA256 == (
        "4b37345e75bb296a98aa1ee5bc694c3e355b7d60ecc843843ea4c2585f3783e6"
    )
    assert sh._git_text(
        root, "rev-parse", f"{sh.AMENDMENT_2_COMMIT}^{{commit}}",
    ) == sh.AMENDMENT_2_COMMIT
    assert sh._git_text(
        root, "rev-parse", f"{sh.AMENDMENT_2_COMMIT}^{{tree}}",
    ) == sh.AMENDMENT_2_TREE
    # Amendment 2 is the sole child of Amendment 1 and adds only its own path.
    assert sh._git_text(
        root, "rev-parse", f"{sh.AMENDMENT_2_COMMIT}^^{{commit}}",
    ) == sh.AMENDMENT_1_COMMIT
    assert sh._git_text(
        root, "diff-tree", "--no-commit-id", "-r", "--name-only",
        sh.AMENDMENT_2_COMMIT,
    ).splitlines() == [sh.AMENDMENT_2_PATH]
    amendment_blob = sh._git_bytes(
        root, "show", f"{sh.AMENDMENT_2_COMMIT}:{sh.AMENDMENT_2_PATH}",
    )
    assert hashlib.sha256(amendment_blob).hexdigest() == sh.AMENDMENT_2_SHA256
    assert amendment_blob == (root / sh.AMENDMENT_2_PATH).read_bytes()

    # Amendment 3 re-binds the parent gates; Amendments 1 and 2 stay bound
    # and verified through the identity snapshot and receipt subject.
    source = inspect.getsource(sh.make_harness_manifest)
    assert "AMENDMENT_3_COMMIT" in source and "AMENDMENT_3_TREE" in source
    assert "AMENDMENT_1_COMMIT" not in source
    assert "AMENDMENT_2_COMMIT" not in source
    status_source = inspect.getsource(sh.harness_manifest_status)
    assert "AMENDMENT_3_COMMIT" in status_source
    assert "AMENDMENT_1_COMMIT" not in status_source
    assert "AMENDMENT_2_COMMIT" not in status_source
    # All three governance shas are carried by the receipt subject.
    subject_source = inspect.getsource(sh._expected_receipt_subject)
    assert "amendment_1_sha256" in subject_source
    assert "amendment_2_sha256" in subject_source
    assert "amendment_3_sha256" in subject_source


def test_make_harness_manifest_refuses_any_parent_but_amendment_3(
    tmp_path, monkeypatch,
):
    """The builder's own parent gates, not just the verifier's.

    ``harness_manifest_status`` already refuses a substituted parent in a
    finished manifest; these are the three refusals on the construction side,
    re-bound by Amendment 3 to its own governance commit.
    """
    manifest, _, parent, parent_tree = _h_repo(tmp_path, monkeypatch)

    def build(commit, tree):
        return sh.make_harness_manifest(
            repo_root=tmp_path, freeze_parent_commit=commit,
            freeze_parent_tree=tree,
            canary_receipts=manifest["canary_receipt"],
            audit_receipt=manifest["audit_receipt"],
            smoke_receipt=manifest["smoke_receipt"],
        )

    for commit, tree in (("0" * 40, parent_tree), (parent, "1" * 40)):
        with pytest.raises(
            sh.LockMismatch,
            match="exact Amendment 3 governance commit/tree",
        ):
            build(commit, tree)

    # HEAD has already advanced to H'', so a replay from the descendant is
    # refused even with the correct governance parent.
    with pytest.raises(
        sh.LockMismatch, match="HEAD at the Amendment 3 governance commit",
    ):
        build(parent, parent_tree)

    # A pinned tree that git does not resolve to is unavailable, not merely
    # mismatched: the constants and the argument agree and git still refuses.
    monkeypatch.setattr(sh, "AMENDMENT_3_TREE", "1" * 40)
    with pytest.raises(
        sh.LockMismatch, match="H freeze parent commit/tree is unavailable",
    ):
        build(parent, "1" * 40)


def test_audit_receipt_carries_disclosed_non_blocking_defects(
    tmp_path, monkeypatch,
):
    """Amendment 2 Rider 2: a disclosed non-blocking defect rides in valid H.

    The superseded validator hard-required ``defects == []``, so a manifest
    structurally could not disclose anything; disclosure is now typed and the
    manifest stays verifiable end to end.
    """
    disclosed = [
        {"severity": "non_blocking",
         "text": "synthetic disclosed defect: cosmetic label drift"},
        {"severity": "non_blocking",
         "text": "synthetic disclosed defect: stale docstring"},
    ]
    manifest, h_commit, parent, parent_tree = _h_repo(
        tmp_path, monkeypatch, defects=disclosed,
    )
    assert manifest["audit_receipt"]["defects"] == disclosed
    status = sh.require_harness_manifest(
        manifest, repo_root=tmp_path, harness_commit=h_commit,
        expected_parent_commit=parent, expected_parent_tree=parent_tree,
    )
    assert status["frozen"]


def test_audit_receipt_blocking_or_untyped_defects_refuse_the_freeze(
    tmp_path, monkeypatch,
):
    blocking = tmp_path / "blocking"; blocking.mkdir()
    with pytest.raises(sh.LockMismatch, match="blocking defect"):
        _h_repo(blocking, monkeypatch, defects=[
            {"severity": "non_blocking",
             "text": "synthetic disclosed defect: rides with a blocker"},
            {"severity": "blocking",
             "text": "synthetic blocking defect: must refuse the freeze"},
        ])
    for ordinal, malformed in enumerate((
        [{"severity": "non_blocking"}],
        [{"severity": "cosmetic", "text": "unknown severity"}],
        [{"severity": "non_blocking", "text": ""}],
        [{"severity": "non_blocking", "text": " padded "}],
        [{"severity": "non_blocking", "text": "x", "extra": True}],
        ["free text is not a typed disclosure"],
    )):
        target = tmp_path / f"malformed-{ordinal}"
        target.mkdir()
        with pytest.raises(
            sh.LockMismatch, match="typed severity/text",
        ):
            _h_repo(target, monkeypatch, defects=malformed)


def test_h_file_set_and_enabled_builder_cannot_be_weakened(
    tmp_path, monkeypatch,
):
    assert sh.H_REQUIRED_FILES == (
        "epl/shots.py", "epl/shots_harness.py", "epl/tests/test_shots.py",
    )
    assert "files" not in inspect.signature(sh.make_harness_manifest).parameters
    assert "output_schemas" not in inspect.signature(
        sh.make_harness_manifest).parameters
    assert "required_files" not in inspect.signature(
        sh.harness_manifest_status).parameters
    assert "required_files" not in inspect.signature(
        sh.require_harness_manifest).parameters
    manifest, h_commit, parent, parent_tree = _h_repo(tmp_path, monkeypatch)
    assert manifest["freeze_parent_commit"] == parent
    assert manifest["freeze_parent_tree"] == parent_tree
    assert manifest["canary_receipt"]["schema"] == sh.H_CANARY_RECEIPT_SCHEMA
    assert manifest["audit_receipt"]["schema"] == sh.H_AUDIT_RECEIPT_SCHEMA
    assert sh.require_harness_manifest(
        manifest, repo_root=tmp_path, harness_commit=h_commit,
    )["frozen"]


@pytest.mark.parametrize(("field", "replacement", "message"), [
    (
        "freeze_parent_commit", "0" * 40,
        "freeze_parent_commit is not the Amendment 3 governance commit",
    ),
    (
        "freeze_parent_tree", "1" * 40,
        "freeze_parent_tree is not the Amendment 3 governance tree",
    ),
])
def test_h_manifest_refuses_amendment_commit_or_tree_substitution(
    tmp_path, monkeypatch, field, replacement, message,
):
    manifest, h_commit, _, _ = _h_repo(tmp_path, monkeypatch)
    substituted = json.loads(json.dumps(manifest))
    substituted[field] = replacement
    with pytest.raises(sh.LockMismatch, match=message):
        sh.require_harness_manifest(
            substituted, repo_root=tmp_path, harness_commit=h_commit,
        )


def test_h_manifest_refuses_amendment_hash_or_worktree_byte_substitution(
    tmp_path, monkeypatch,
):
    manifest, h_commit, _, _ = _h_repo(tmp_path, monkeypatch)
    substituted_hash = json.loads(json.dumps(manifest))
    substituted_hash["native_contract"]["amendment_1_sha256"] = "0" * 64
    with pytest.raises(
        sh.LockMismatch,
        match="native_contract differs from the recomputed preregistered contract",
    ):
        sh.require_harness_manifest(
            substituted_hash, repo_root=tmp_path, harness_commit=h_commit,
        )

    substituted_hash_2 = json.loads(json.dumps(manifest))
    substituted_hash_2["native_contract"]["amendment_2_sha256"] = "0" * 64
    with pytest.raises(
        sh.LockMismatch,
        match="native_contract differs from the recomputed preregistered contract",
    ):
        sh.require_harness_manifest(
            substituted_hash_2, repo_root=tmp_path, harness_commit=h_commit,
        )

    substituted_hash_3 = json.loads(json.dumps(manifest))
    substituted_hash_3["native_contract"]["amendment_3_sha256"] = "0" * 64
    with pytest.raises(
        sh.LockMismatch,
        match="native_contract differs from the recomputed preregistered contract",
    ):
        sh.require_harness_manifest(
            substituted_hash_3, repo_root=tmp_path, harness_commit=h_commit,
        )

    amendment_3_path = tmp_path / sh.AMENDMENT_3_PATH
    original_amendment_3 = amendment_3_path.read_bytes()
    amendment_3_path.write_bytes(b"substituted amendment 3 bytes\n")
    with pytest.raises(
        sh.LockMismatch,
        match="committed Amendment 3 commit/tree/hash/bytes differ",
    ):
        sh.require_harness_manifest(
            manifest, repo_root=tmp_path, harness_commit=h_commit,
        )
    amendment_3_path.write_bytes(original_amendment_3)

    amendment_2_path = tmp_path / sh.AMENDMENT_2_PATH
    original_amendment_2 = amendment_2_path.read_bytes()
    amendment_2_path.write_bytes(b"substituted amendment 2 bytes\n")
    with pytest.raises(
        sh.LockMismatch,
        match="committed Amendment 2 commit/tree/hash/bytes differ",
    ):
        sh.require_harness_manifest(
            manifest, repo_root=tmp_path, harness_commit=h_commit,
        )
    amendment_2_path.write_bytes(original_amendment_2)

    amendment_path = tmp_path / sh.AMENDMENT_1_PATH
    amendment_path.write_bytes(b"substituted amendment bytes\n")
    with pytest.raises(
        sh.LockMismatch,
        match="committed Amendment 1 commit/tree/hash/bytes differ",
    ):
        sh.require_harness_manifest(
            manifest, repo_root=tmp_path, harness_commit=h_commit,
        )


def test_h_manifest_refuses_spoofed_identity_self_hash_and_failed_canary(
    tmp_path, monkeypatch,
):
    manifest, h_commit, _, _ = _h_repo(tmp_path, monkeypatch)
    self_ref = {**manifest, "manifest_sha256": "f" * 64}
    with pytest.raises(sh.LockMismatch, match="self-referential"):
        sh.require_harness_manifest(
            self_ref, repo_root=tmp_path, harness_commit=h_commit,
        )
    weakened = {**manifest, "output_schemas": dict(manifest["output_schemas"])}
    weakened["output_schemas"]["coefficients"] = {"columns": ["anything"]}
    with pytest.raises(sh.LockMismatch, match="semantic contract"):
        sh.require_harness_manifest(
            weakened, repo_root=tmp_path, harness_commit=h_commit,
        )
    monkeypatch.setitem(
        sh.H_OUTPUT_SCHEMAS, "coefficients", {"columns": ["attacker"]},
    )
    monkeypatch.setitem(
        sh.CANARY_TEST_IDS, "lookahead_trap", "attacker_named_test",
    )
    assert sh._expected_h_output_schemas()["coefficients"] != {
        "columns": ["attacker"]}
    assert (sh._expected_canary_test_ids()["lookahead_trap"]
            != "attacker_named_test")
    monkeypatch.setitem(
        sh.CANARY_TEST_PLAN["canaries"], "lookahead_trap", [],
    )
    assert sh._expected_canary_test_plan()["canaries"]["lookahead_trap"]
    failed = json.loads(json.dumps(manifest))
    failed["canary_receipt"]["events"][-1]["outcome"] = "failed"
    with pytest.raises(sh.LockMismatch, match="exact all-pass execution"):
        sh.require_harness_manifest(
            failed, repo_root=tmp_path, harness_commit=h_commit,
        )
    stale_canary_schema = json.loads(json.dumps(manifest))
    stale_canary_schema["canary_receipt"]["schema"] = (
        "epl-shots-canary-receipt-2"
    )
    with pytest.raises(sh.LockMismatch, match="exact all-pass execution"):
        sh.require_harness_manifest(
            stale_canary_schema, repo_root=tmp_path, harness_commit=h_commit,
        )
    stale_audit_schema = json.loads(json.dumps(manifest))
    stale_audit_schema["audit_receipt"]["schema"] = (
        "epl-shots-adversarial-audit-receipt-2"
    )
    with pytest.raises(sh.LockMismatch, match="exact clean audit"):
        sh.require_harness_manifest(
            stale_audit_schema, repo_root=tmp_path, harness_commit=h_commit,
        )
    spoofed_identity = {**manifest, "data_identities": {"bogus": "d" * 64}}
    with pytest.raises(sh.LockMismatch, match="data_identities differs"):
        sh.require_harness_manifest(
            spoofed_identity, repo_root=tmp_path, harness_commit=h_commit,
        )
    spoofed_runtime = {
        **manifest,
        "runtime_dependency_closure": {"epl.paths": {"sha256": "0" * 64}},
    }
    with pytest.raises(sh.LockMismatch, match="runtime_dependency_closure differs"):
        sh.require_harness_manifest(
            spoofed_runtime, repo_root=tmp_path, harness_commit=h_commit,
        )
    spoofed_native_runtime = {
        **manifest,
        "native_runtime_lock": {
            **manifest["native_runtime_lock"], "sha256": "0" * 64,
        },
    }
    with pytest.raises(sh.LockMismatch, match="native_runtime_lock differs"):
        sh.require_harness_manifest(
            spoofed_native_runtime, repo_root=tmp_path, harness_commit=h_commit,
        )
    # Python equality accepts 4180.0 == 4180; canonical JSON equality must not.
    spoofed_invariants = {
        **manifest,
        "h_invariants": {**manifest["h_invariants"], "raw_rows": 4_180.0},
    }
    with pytest.raises(sh.LockMismatch, match="h_invariants differs"):
        sh.require_harness_manifest(
            spoofed_invariants, repo_root=tmp_path, harness_commit=h_commit,
        )


def test_opaque_k_path_is_absent_until_the_semantic_runner_exists():
    retired = {
        "make_coefficient_manifest", "coefficient_manifest_status",
        "require_coefficient_manifest", "_coefficient_artifact_records",
        "_pinned_training_fixture_sha256",
    }
    assert all(not hasattr(sh, name) for name in retired)


# ==========================================================================
# 6. Built PRE-H runner scaffold; live H/K authorization remains mandatory
# ==========================================================================

def test_runner_state_and_public_effect_signatures_are_built_but_unfrozen():
    """Freeze-aware scaffold reading: exact on BOTH sides of the H boundary.

    Amendment 2 Rider 1: the superseded freeze asserted the pre-H reading
    unconditionally, so the committed manifest turned this test red forever.
    A bare ``inspect_state()`` never certifies H (certification requires the
    freeze commit), so ``h_frozen`` is false on both sides; the manifest
    presence and the issue it legitimately carries flip with the boundary.
    """
    state = runner.inspect_state()
    assert state.h_ready
    assert state.training_worker_ready
    assert state.decision_worker_ready
    assert not state.k_manifest_present and not state.k_frozen
    assert not state.h_frozen
    assert len(state.training_schedule_sha256) == 64
    assert len(state.decision_schedule_sha256) == 64
    if runner._H_PATH.is_file():
        assert state.build_state == "H_MANIFEST_PRESENT_UNVERIFIED"
        assert state.h_manifest_present
        assert state.issues == (
            "H manifest exists but no H commit was supplied",)
    else:
        assert state.build_state == "BUILT_UNFROZEN_PRE_H"
        assert not state.h_manifest_present
        assert state.issues == ()
    assert set(inspect.signature(runner.run_training).parameters) == {"h_commit"}
    assert set(inspect.signature(runner.run_decision).parameters) == {
        "h_commit", "k_commit"}


def test_build_state_reading_is_derived_from_live_gates(tmp_path, monkeypatch):
    """Amendment 2 Rider 2: no frozen byte may claim the harness is unfrozen.

    The superseded freeze stored ``BUILD_STATE = "BUILT_UNFROZEN_PRE_H"`` as a
    constant, which was stale inside the frozen bytes.  The reading is now
    derived from the live gates at inspection time, and the stale constant is
    retired on both modules.
    """
    assert sh.BUILD_STATES == (
        "BUILT_UNFROZEN_PRE_H", "H_MANIFEST_PRESENT_UNVERIFIED",
        "FROZEN_H_VERIFIED",
    )
    assert runner.BUILD_STATES == sh.BUILD_STATES
    assert not hasattr(sh, "BUILD_STATE")
    assert not hasattr(runner, "BUILD_STATE")

    scratch = tmp_path / "harness_manifest.json"
    monkeypatch.setattr(runner, "_H_PATH", scratch)
    pre = runner.inspect_state()
    assert pre.build_state == "BUILT_UNFROZEN_PRE_H"
    assert not pre.h_manifest_present and not pre.h_frozen

    scratch.write_text("{}\n", encoding="ascii")
    present = runner.inspect_state()
    assert present.build_state == "H_MANIFEST_PRESENT_UNVERIFIED"
    assert present.h_manifest_present and not present.h_frozen
    assert present.issues == (
        "H manifest exists but no H commit was supplied",)

    verified_h = runner._VerifiedH("a" * 40, "b" * 64, "c" * 64, "d" * 64)
    monkeypatch.setattr(runner, "verify_harness_live", lambda commit: verified_h)
    live = runner.inspect_state(h_commit="a" * 40)
    assert live.build_state == "FROZEN_H_VERIFIED"
    assert live.h_manifest_present and live.h_frozen
    assert live.issues == ()

    def failing_verify(commit):
        raise sh.LockMismatch("synthetic stale H")

    monkeypatch.setattr(runner, "verify_harness_live", failing_verify)
    stale = runner.inspect_state(h_commit="a" * 40)
    assert stale.build_state == "H_MANIFEST_PRESENT_UNVERIFIED"
    assert not stale.h_frozen
    assert stale.issues == ("H verification failed: synthetic stale H",)


def test_runner_exact_schedule_binding_rejects_reordered_identity(monkeypatch):
    digest, rows = runner.decision_schedule_binding()
    assert len(digest) == 64 and len(rows) == 2_280
    assert len({row["block"] for row in rows}) == 212
    read_parquet = runner.pd.read_parquet

    def reordered(*args, **kwargs):
        frame = read_parquet(*args, **kwargs)
        return pd.concat(
            (frame.iloc[[-1]], frame.iloc[1:-1], frame.iloc[[0]]),
            ignore_index=True,
        )

    monkeypatch.setattr(runner.pd, "read_parquet", reordered)
    with pytest.raises(sh.TimeBoundaryViolation, match="not monotone"):
        runner.decision_schedule_binding()


def test_regular_snapshot_refuses_a_path_alias(tmp_path):
    target = tmp_path / "target"; target.write_bytes(b"pinned")
    alias = tmp_path / "alias"; alias.symlink_to(target)
    with pytest.raises(sh.LockMismatch, match="snapshotted"):
        runner._read_regular_snapshot(alias, label="synthetic corpus")


def test_regular_snapshot_refuses_one_way_visible_path_replacement(
    tmp_path, monkeypatch,
):
    visible = tmp_path / "corpus"; visible.write_bytes(b"pinned")
    parked = tmp_path / "parked"
    real_fstat = os.fstat
    fstat_calls = 0
    swapped = False

    def swapping_fstat(descriptor):
        nonlocal fstat_calls, swapped
        info = real_fstat(descriptor)
        fstat_calls += 1
        if not swapped and fstat_calls == 2:
            # Replace the visible name immediately after the final descriptor
            # identity sample; only the named-entry revalidation can catch it.
            visible.rename(parked)
            visible.write_bytes(b"pinned")
            swapped = True
        return info

    monkeypatch.setattr(runner.os, "fstat", swapping_fstat)
    with pytest.raises(sh.LockMismatch, match="visible path changed"):
        runner._read_regular_snapshot(visible, label="synthetic corpus")
    assert swapped
    assert parked.read_bytes() == visible.read_bytes() == b"pinned"


def test_public_effect_calls_require_live_h_and_k_before_writers(monkeypatch):
    """Amendment 3 item 9: the reading is stage-aware from committed bytes.

    The H'-era wording hard-asserted namespace absence, so a lawfully
    preserved mid-lifecycle state (an interrupted run, or post-H training
    artifacts before K) turned the frozen suite red without any defect.  The
    stage is read the way Amendment 2 Rider 1 reads it — the committed H
    manifest's presence — and the invariant proven in every stage is that
    the refused public-effect calls change nothing; outright absence is
    additionally asserted only in the pre-H stage.
    """
    def invalid_h(commit):
        raise sh.LockMismatch(f"synthetic invalid H: {commit}")

    def invalid_k(h_commit, k_commit):
        raise sh.LockMismatch(
            f"synthetic invalid H/K: {h_commit}/{k_commit}"
        )

    monkeypatch.setattr(runner, "verify_harness_live", invalid_h)
    monkeypatch.setattr(runner, "verify_coefficient_freeze_live", invalid_k)
    monkeypatch.setattr(
        runner, "_experiment_transaction_lock",
        lambda **kwargs: contextlib.nullcontext(),
    )
    artifact_root = paths.REPO_ROOT / sh.SHOTS_ARTIFACT_ROOT

    def inventory():
        if not artifact_root.exists():
            return None
        return sorted(
            (str(path.relative_to(artifact_root)),
             sh.sha256_file(path) if path.is_file() else "directory")
            for path in artifact_root.rglob("*")
        )

    committed_pre_h = not runner._H_PATH.is_file()
    before = inventory()
    if committed_pre_h:
        assert before is None
    with pytest.raises(sh.LockMismatch, match="synthetic invalid H"):
        runner.run_training(h_commit="a" * 40)
    h, _ = _decision_test_h_k()
    monkeypatch.setattr(runner, "verify_harness_live", lambda commit: h)
    with pytest.raises(sh.LockMismatch, match="synthetic invalid H/K"):
        runner.run_decision(h_commit="a" * 40, k_commit="b" * 40)
    assert inventory() == before
    if committed_pre_h:
        assert not artifact_root.exists()
    assert not hasattr(runner, "_write_content_addressed")


def test_runner_k2_schemas_match_the_fresh_h_output_contract(monkeypatch):
    expected = sh._expected_h_output_schemas()
    schemas = runner._k2_schemas()
    for logical in (
        "native_intent", "native_block", "native_completion",
        "native_refusal",
        "training_predictions", "feature_moments", "coefficients",
        "optimizer_intent", "optimizer_receipt",
    ):
        assert schemas[logical] == expected[logical]["schema"]
    monkeypatch.setitem(
        sh.H_OUTPUT_SCHEMAS, "coefficients", {"schema": "attacker-schema"},
    )
    assert runner._k2_schemas()["coefficients"] == "epl-shots-coefficients-2"


def test_h_output_contract_lists_exact_implemented_runtime_and_optimizer_fields(
    tmp_path,
):
    expected = sh._expected_h_output_schemas()
    contract = runner._native_sandbox_contract()
    assert set(expected["native_completion"]["sandbox_contract_fields"]) \
        == set(contract)
    temporary = tmp_path / "job"
    parent = temporary / "parent"
    request = temporary / "request.json"
    runtime = temporary / "runtime"
    profile = runner._native_sandbox_profile(
        contract=contract, temporary_root=temporary, parent_root=parent,
        request_path=request, runtime_root=runtime,
    )
    environment = runner._native_environment_values(
        contract=contract, parent_root=parent,
        request_path=request, runtime_root=runtime,
    )
    sandbox_run = runner._native_sandbox_run_receipt(
        contract=contract, profile=profile, temporary_root=temporary,
        parent_root=parent, request_path=request, runtime_root=runtime,
        environment=environment,
    )
    assert set(expected["native_completion"]["sandbox_run_fields"]) \
        == set(sandbox_run)
    runtime.mkdir(parents=True)
    runtime_snapshot = runner._native_runtime_output_snapshot(runtime)
    assert expected["native_completion"]["runtime_tree_completion_schema"] \
        == runtime_snapshot["schema"]
    assert set(expected["native_completion"][
        "runtime_tree_completion_fields"
    ]) == set(runtime_snapshot)
    assert set(expected["native_completion"][
        "runtime_tree_completion_entry_fields"
    ]) == set(runtime_snapshot["entries"][0])

    h = runner._VerifiedH("a" * 40, "b" * 64, "c" * 64, "d" * 64)
    intent = runner._make_optimizer_intent(
        h=h, native_block_set_sha256="e" * 64,
        feature_moments_sha256="f" * 64,
        training_outcomes_sha256="1" * 64,
    )
    intent_raw = runner._canonical_bytes(intent)
    intent_digest = hashlib.sha256(intent_raw).hexdigest()
    intent_record = {
        "path": (
            f"{sh.SHOTS_ARTIFACT_ROOT}/"
            f"{runner._k2_filename('optimizer_intent', intent_digest)}"
        ),
        "sha256": intent_digest, "bytes": len(intent_raw),
        "schema": runner._k2_schemas()["optimizer_intent"],
    }
    receipt = runner._make_optimizer_receipt(
        intent_record=intent_record, intent=intent,
        success=True, status=0, beta=[0.0] * 8, objective_value=1.0,
        gradient=[0.0] * 8, independent_objective_value=1.0,
        independent_gradient=[0.0] * 8,
        iterations=0, function_evaluations=1,
        gradient_evaluations=1, message="stationary synthetic receipt",
    )
    assert set(expected["optimizer_intent"]["fields"]) == set(intent)
    assert set(expected["optimizer_receipt"]["fields"]) == set(receipt)


def test_runner_proves_committed_k_manifest_before_opening_artifacts(monkeypatch):
    h = runner._VerifiedH("h" * 40, "m" * 64, "t" * 64, "d" * 64)
    k = "k" * 40
    monkeypatch.setattr(runner, "verify_harness_live", lambda commit: h)
    monkeypatch.setattr(runner, "_commit", lambda commit, label: k)
    monkeypatch.setattr(
        runner, "_git_text", lambda *args: f"{k} {h.commit}",
    )
    monkeypatch.setattr(
        runner, "_read_canonical", lambda *args, **kwargs: ({}, b"current\n"),
    )
    monkeypatch.setattr(runner, "_git_bytes", lambda *args: b"committed\n")

    def forbidden(*args, **kwargs):
        raise AssertionError("artifact opened before K was proven")

    monkeypatch.setattr(runner, "_load_committed_k2_artifact", forbidden)
    with pytest.raises(sh.LockMismatch, match="differs from committed K"):
        runner.verify_coefficient_freeze_live(h.commit, k)


def test_runner_status_cli_is_read_only_and_explicit(capsys):
    assert runner.main(["status"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["build_state"] in runner.BUILD_STATES
    assert payload["build_state"] == runner.inspect_state().build_state
    assert payload["h_ready"] is True


def test_new_state_root_components_are_synced_before_control_write(
    tmp_path, monkeypatch,
):
    state_root = tmp_path / "missing" / "nested" / "state"
    real_fsync = os.fsync
    synced_directories: list[tuple[int, int]] = []

    def record_fsync(descriptor):
        info = os.fstat(descriptor)
        if stat.S_ISDIR(info.st_mode):
            synced_directories.append((info.st_dev, info.st_ino))
        return real_fsync(descriptor)

    monkeypatch.setattr(runner.os, "fsync", record_fsync)
    with runner._open_decision_state_directory(
        state_root, create=True,
    ) as (_, descriptor):
        assert descriptor is not None
        leaf_identity = os.fstat(descriptor)

    assert state_root.is_dir()
    chain = [Path("/")]
    current = Path("/")
    for component in state_root.absolute().parts[1:]:
        current = current / component
        chain.append(current)
    identities = [
        (item.stat().st_dev, item.stat().st_ino) for item in chain
    ]
    expected = [
        identity
        for index in range(1, len(identities))
        for identity in (identities[index], identities[index - 1])
    ]
    assert synced_directories == expected
    assert (leaf_identity.st_dev, leaf_identity.st_ino) in synced_directories


def test_state_root_pre_mutation_fsync_failure_is_resumable_before_yield(
    tmp_path, monkeypatch,
):
    state_root = tmp_path / "new-state-root"
    yielded = False

    def fail_fsync(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("synthetic directory durability failure")

    monkeypatch.setattr(runner.os, "fsync", fail_fsync)
    with pytest.raises(
        runner.NativeWorkerIOFailure,
        match="decision state directory setup did not complete",
    ) as stopped:
        with runner._open_decision_state_directory(
            state_root, create=True,
        ):
            yielded = True
    assert isinstance(stopped.value, runner.ResumableRunInterruption)
    assert yielded is False
    assert not state_root.exists()


def test_concurrent_state_root_creator_is_synced_before_yield(
    tmp_path, monkeypatch,
):
    state_root = tmp_path / "concurrent-root"
    real_open = os.open
    real_mkdir = os.mkdir
    real_fsync = os.fsync
    injected = False
    synced: list[tuple[int, int]] = []

    def concurrent_open(path, flags, *args, **kwargs):
        nonlocal injected
        if path == state_root.name and not injected:
            injected = True
            real_mkdir(path, 0o755, dir_fd=kwargs["dir_fd"])
            raise FileNotFoundError("synthetic missing-before-concurrent-create")
        return real_open(path, flags, *args, **kwargs)

    def record_fsync(descriptor):
        info = os.fstat(descriptor)
        if stat.S_ISDIR(info.st_mode):
            synced.append((info.st_dev, info.st_ino))
        return real_fsync(descriptor)

    monkeypatch.setattr(runner.os, "open", concurrent_open)
    monkeypatch.setattr(runner.os, "fsync", record_fsync)
    with runner._open_decision_state_directory(
        state_root, create=True,
    ) as (_, descriptor):
        assert descriptor is not None
        child = os.fstat(descriptor)

    assert injected is True
    parent = state_root.parent.stat()
    assert synced[-2:] == [
        (child.st_dev, child.st_ino),
        (parent.st_dev, parent.st_ino),
    ]


def test_state_root_post_mkdir_parent_fsync_failure_is_manual(
    tmp_path, monkeypatch,
):
    state_root = tmp_path / "visible-after-failed-parent-sync"
    parent_identity = tmp_path.stat()
    real_fsync = os.fsync
    failed = False

    def fail_leaf_parent_once(descriptor):
        nonlocal failed
        info = os.fstat(descriptor)
        if (not failed and state_root.exists()
                and (info.st_dev, info.st_ino)
                == (parent_identity.st_dev, parent_identity.st_ino)):
            failed = True
            raise OSError("synthetic parent durability failure")
        return real_fsync(descriptor)

    monkeypatch.setattr(runner.os, "fsync", fail_leaf_parent_once)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="decision state directory setup did not complete",
    ):
        with runner._open_decision_state_directory(
            state_root, create=True,
        ):
            raise AssertionError("failed parent fsync yielded authority")
    assert failed and state_root.is_dir()


def test_state_root_sync_failure_closes_every_opened_descriptor(
    tmp_path, monkeypatch,
):
    state_root = tmp_path / "fd-cleanup"
    real_open = os.open
    real_close = os.close
    live: set[int] = set()

    def track_open(*args, **kwargs):
        descriptor = real_open(*args, **kwargs)
        live.add(descriptor)
        return descriptor

    def track_close(descriptor):
        live.discard(descriptor)
        return real_close(descriptor)

    def fail_sync(descriptor):
        raise OSError("synthetic traversal sync failure")

    monkeypatch.setattr(runner.os, "open", track_open)
    monkeypatch.setattr(runner.os, "close", track_close)
    monkeypatch.setattr(runner.os, "fsync", fail_sync)
    with pytest.raises(
        runner.NativeWorkerIOFailure,
        match="decision state directory setup did not complete",
    ):
        with runner._open_decision_state_directory(
            state_root, create=True,
        ):
            raise AssertionError("failed traversal sync yielded authority")
    assert live == set()


def test_state_root_post_mkdir_open_failure_is_manual(tmp_path, monkeypatch):
    state_root = tmp_path / "post-mkdir-open-failure"
    real_open = runner.os.open
    attempts = 0

    def fail_second_leaf_open(path, flags, *args, **kwargs):
        nonlocal attempts
        if os.fspath(path) == state_root.name:
            attempts += 1
            if attempts == 2:
                raise OSError("synthetic post-mkdir open ambiguity")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(runner.os, "open", fail_second_leaf_open)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="decision state directory setup did not complete",
    ):
        with runner._open_decision_state_directory(
            state_root, create=True,
        ):
            pytest.fail("post-mkdir open failure yielded authority")
    assert attempts == 2 and state_root.is_dir()


def test_state_root_exit_path_ambiguity_is_manual(tmp_path):
    state_root = tmp_path / "visible-state"
    parked = tmp_path / "opened-state"
    state_root.mkdir()

    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="visible path identity changed",
    ):
        with runner._open_decision_state_directory(
            state_root, create=False,
        ) as (_, descriptor):
            assert descriptor is not None
            state_root.rename(parked)
            state_root.mkdir()
    assert state_root.is_dir() and parked.is_dir()


def test_state_root_exit_close_ambiguity_overrides_active_failure(
    tmp_path, monkeypatch,
):
    state_root = tmp_path / "close-state"
    state_root.mkdir()
    real_close = runner.os.close
    leaf_descriptor = -1
    fail_close = False
    active = sh.FitFailure("synthetic active state operation")

    def ambiguous_close(descriptor):
        if fail_close and descriptor == leaf_descriptor:
            raise OSError("synthetic state descriptor close ambiguity")
        return real_close(descriptor)

    monkeypatch.setattr(runner.os, "close", ambiguous_close)
    try:
        with pytest.raises(
            runner.ManualReconciliationRequired,
            match="directory descriptor did not close",
        ) as stopped:
            with runner._open_decision_state_directory(
                state_root, create=False,
            ) as (_, descriptor):
                leaf_descriptor = descriptor
                fail_close = True
                raise active
        assert stopped.value.__cause__ is active
    finally:
        monkeypatch.setattr(runner.os, "close", real_close)
        if leaf_descriptor >= 0:
            try:
                real_close(leaf_descriptor)
            except OSError:
                pass


def test_missing_state_root_preserves_body_oserror(tmp_path):
    state_root = tmp_path / "absent-read-only-state"
    active = OSError("synthetic caller body I/O failure")
    with pytest.raises(OSError) as stopped:
        with runner._open_decision_state_directory(
            state_root, create=False,
        ) as (_, descriptor):
            assert descriptor is None
            raise active
    assert stopped.value is active


def test_state_root_post_mkdir_traversal_close_is_manual(
    tmp_path, monkeypatch,
):
    state_root = tmp_path / "post-mkdir-close"
    real_open = runner.os.open
    real_close = runner.os.close
    parent_descriptor = -1
    opened_leaf = False
    failed = False

    def capture_leaf_open(path, flags, *args, **kwargs):
        nonlocal parent_descriptor, opened_leaf
        descriptor = real_open(path, flags, *args, **kwargs)
        if os.fspath(path) == state_root.name:
            parent_descriptor = kwargs["dir_fd"]
            opened_leaf = True
        return descriptor

    def fail_parent_close(descriptor):
        nonlocal failed
        if opened_leaf and not failed and descriptor == parent_descriptor:
            failed = True
            real_close(descriptor)
            raise OSError("synthetic post-mkdir traversal close ambiguity")
        return real_close(descriptor)

    monkeypatch.setattr(runner.os, "open", capture_leaf_open)
    monkeypatch.setattr(runner.os, "close", fail_parent_close)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="decision state traversal descriptor did not close",
    ):
        with runner._open_decision_state_directory(
            state_root, create=True,
        ):
            pytest.fail("ambiguous traversal close yielded authority")
    assert failed and state_root.is_dir()


def test_state_root_mkdir_error_after_real_creation_is_manual(
    tmp_path, monkeypatch,
):
    """A mkdir wrapper error after the real mkdir succeeded is manual."""
    state_root = tmp_path / "mkdir-reports-error"
    real_mkdir = runner.os.mkdir
    fired = False

    def mkdir_succeeds_but_reports_error(path, mode=0o777, *, dir_fd=None):
        nonlocal fired
        real_mkdir(path, mode, dir_fd=dir_fd)
        if os.fspath(path) == state_root.name:
            fired = True
            raise OSError("synthetic mkdir wrapper error after creation")

    monkeypatch.setattr(runner.os, "mkdir", mkdir_succeeds_but_reports_error)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="decision state directory setup did not complete",
    ):
        with runner._open_decision_state_directory(
            state_root, create=True,
        ):
            pytest.fail("reported-failed mkdir yielded authority")
    assert fired and state_root.is_dir()


def test_state_root_created_child_fsync_failure_is_manual(
    tmp_path, monkeypatch,
):
    """An fsync failure on the just-created child crosses the manual boundary."""
    state_root = tmp_path / "created-child-sync"
    real_fsync = runner.os.fsync
    real_mkdir = runner.os.mkdir
    created = False
    failed = False

    def observe_mkdir(path, mode=0o777, *, dir_fd=None):
        nonlocal created
        real_mkdir(path, mode, dir_fd=dir_fd)
        if os.fspath(path) == state_root.name:
            created = True

    def fail_created_child_fsync(descriptor):
        nonlocal failed
        if created and not failed:
            failed = True
            raise OSError("synthetic created-child fsync failure")
        return real_fsync(descriptor)

    monkeypatch.setattr(runner.os, "mkdir", observe_mkdir)
    monkeypatch.setattr(runner.os, "fsync", fail_created_child_fsync)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="decision state directory setup did not complete",
    ):
        with runner._open_decision_state_directory(
            state_root, create=True,
        ):
            pytest.fail("undurable created child yielded authority")
    assert created and failed and state_root.is_dir()


def test_decision_state_directory_fsync_failure_is_manual(
    tmp_path, monkeypatch,
):
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    monkeypatch.setattr(
        runner.os, "fsync",
        lambda candidate: (_ for _ in ()).throw(
            OSError("synthetic decision directory fsync ambiguity")
        ),
    )
    try:
        with pytest.raises(
            runner.ManualReconciliationRequired,
            match="directory durability is ambiguous",
        ):
            runner._fsync_decision_state_directory(descriptor)
    finally:
        os.close(descriptor)


# ==========================================================================
# 7. PRE-H immutable shards, one-shot intent, and semantic K2 construction
# ==========================================================================

def _content_addressed_test_value() -> dict:
    return {
        "schema": runner._k2_schemas()["feature_moments"],
        "payload": "synthetic immutable writer test",
    }


def _content_addressed_test_path(root: Path, value: dict) -> Path:
    digest = hashlib.sha256(runner._canonical_bytes(value)).hexdigest()
    return root / runner._k2_filename("feature_moments", digest)


def test_content_addressed_writer_pre_name_root_io_is_resumable(
    tmp_path, monkeypatch,
):
    value = _content_addressed_test_value()
    real_open = runner.os.open

    def fail_root_open(path, flags, *args, **kwargs):
        if os.fspath(path) == "/" and "dir_fd" not in kwargs:
            raise OSError("synthetic pre-publication root I/O failure")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(runner.os, "open", fail_root_open)
    with pytest.raises(
        runner.NativeWorkerIOFailure,
        match="decision state directory setup did not complete",
    ) as stopped:
        runner._write_content_addressed_json(
            "feature_moments", value, artifact_root=tmp_path,
        )
    assert isinstance(stopped.value, runner.ResumableRunInterruption)
    assert not _content_addressed_test_path(tmp_path, value).exists()


@pytest.mark.parametrize(("failure", "pattern"), [
    ("open", "may have become durable"),
    ("write", "no longer names the created inode"),
    ("file_fsync", "owned failed artifact preserved at"),
    ("directory_fsync", "owned failed artifact preserved at"),
    ("close", "artifact descriptor cleanup is ambiguous"),
])
def test_content_addressed_writer_post_create_boundary_is_manual(
    tmp_path, monkeypatch, failure, pattern,
):
    value = _content_addressed_test_value()
    name = _content_addressed_test_path(tmp_path, value).name
    real_open = runner.os.open
    real_write = runner.os.write
    real_fsync = runner.os.fsync
    real_close = runner.os.close
    artifact_descriptor = -1

    def controlled_open(path, flags, *args, **kwargs):
        nonlocal artifact_descriptor
        if os.fspath(path) == name and flags & os.O_EXCL:
            if failure == "open":
                raise OSError("synthetic O_CREAT ambiguity")
            artifact_descriptor = real_open(path, flags, *args, **kwargs)
            return artifact_descriptor
        return real_open(path, flags, *args, **kwargs)

    def controlled_write(descriptor, raw):
        if failure == "write" and descriptor == artifact_descriptor:
            raise OSError("synthetic content write ambiguity")
        return real_write(descriptor, raw)

    def controlled_fsync(descriptor):
        if failure == "file_fsync" and descriptor == artifact_descriptor:
            raise OSError("synthetic content fsync ambiguity")
        return real_fsync(descriptor)

    def controlled_close(descriptor):
        if failure == "close" and descriptor == artifact_descriptor:
            raise OSError("synthetic content close ambiguity")
        return real_close(descriptor)

    monkeypatch.setattr(runner.os, "open", controlled_open)
    monkeypatch.setattr(runner.os, "write", controlled_write)
    monkeypatch.setattr(runner.os, "fsync", controlled_fsync)
    monkeypatch.setattr(runner.os, "close", controlled_close)
    if failure == "directory_fsync":
        monkeypatch.setattr(
            runner, "_fsync_artifact_directory",
            lambda descriptor: (_ for _ in ()).throw(
                OSError("synthetic content directory fsync ambiguity")
            ),
        )
    try:
        with pytest.raises(
            runner.ManualReconciliationRequired, match=pattern,
        ):
            runner._write_content_addressed_json(
                "feature_moments", value, artifact_root=tmp_path,
            )
    finally:
        monkeypatch.setattr(runner.os, "close", real_close)
        if artifact_descriptor >= 0:
            try:
                real_close(artifact_descriptor)
            except OSError:
                pass


@pytest.mark.parametrize(("raw_kind", "expected", "pattern"), [
    (
        "empty", runner.ManualReconciliationRequired,
        "not a proven complete entry",
    ),
    (
        "short", runner.ManualReconciliationRequired,
        "not a proven complete entry",
    ),
    ("full_conflict", sh.LockMismatch, "content-address collision"),
])
def test_existing_content_addressed_entry_requires_proven_full_conflict(
    tmp_path, raw_kind, expected, pattern,
):
    value = _content_addressed_test_value()
    path = _content_addressed_test_path(tmp_path, value)
    expected_raw = runner._canonical_bytes(value)
    if raw_kind == "empty":
        raw = b""
    elif raw_kind == "short":
        raw = b"short\n"
    else:
        raw = bytes([expected_raw[0] ^ 1]) + expected_raw[1:]
    assert raw_kind != "full_conflict" or len(raw) == len(expected_raw)
    path.write_bytes(raw)
    path.chmod(0o444)

    with pytest.raises(expected, match=pattern):
        runner._write_content_addressed_json(
            "feature_moments", value, artifact_root=tmp_path,
        )


def test_content_addressed_writer_preserves_owned_failure_and_is_idempotent(
    tmp_path, monkeypatch,
):
    value = _content_addressed_test_value()
    path = _content_addressed_test_path(tmp_path, value)
    real_fsync_directory = runner._fsync_artifact_directory
    calls = 0

    def fail_first_directory_sync(descriptor):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("synthetic directory sync failure")
        return real_fsync_directory(descriptor)

    monkeypatch.setattr(
        runner, "_fsync_artifact_directory", fail_first_directory_sync,
    )
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="owned failed artifact preserved at",
    ):
        runner._write_content_addressed_json(
            "feature_moments", value, artifact_root=tmp_path,
        )
    assert path.read_bytes() == runner._canonical_bytes(value)
    assert not tuple(tmp_path.glob(".*.rollback-*"))

    retry_syncs = 0

    def count_retry_sync(descriptor):
        nonlocal retry_syncs
        retry_syncs += 1
        return real_fsync_directory(descriptor)

    monkeypatch.setattr(
        runner, "_fsync_artifact_directory", count_retry_sync,
    )
    first = runner._write_content_addressed_json(
        "feature_moments", value, artifact_root=tmp_path,
    )
    assert retry_syncs == 1
    second = runner._write_content_addressed_json(
        "feature_moments", value, artifact_root=tmp_path,
    )
    assert retry_syncs == 2
    assert first == second
    assert path.read_bytes() == runner._canonical_bytes(value)
    assert stat.S_IMODE(path.stat().st_mode) == 0o444
    assert len(tuple(tmp_path.glob("*.json"))) == 1


def test_content_addressed_existing_entry_requires_directory_durability(
    tmp_path, monkeypatch,
):
    value = _content_addressed_test_value()
    path = _content_addressed_test_path(tmp_path, value)
    raw = runner._canonical_bytes(value)
    path.write_bytes(raw)
    path.chmod(0o444)

    def fail_directory_sync(descriptor):
        raise OSError("synthetic existing-entry durability failure")

    monkeypatch.setattr(
        runner, "_fsync_artifact_directory", fail_directory_sync,
    )
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="could not be durably bound",
    ):
        runner._write_content_addressed_json(
            "feature_moments", value, artifact_root=tmp_path,
        )
    assert path.read_bytes() == raw


def test_content_addressed_ownership_failure_closes_created_descriptor(
    tmp_path, monkeypatch,
):
    value = _content_addressed_test_value()
    name = _content_addressed_test_path(tmp_path, value).name
    real_open = os.open
    real_close = os.close
    real_fstat = os.fstat
    artifact_fd: int | None = None
    closed: set[int] = set()

    def track_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal artifact_fd
        if dir_fd is None:
            descriptor = real_open(path, flags, mode)
        else:
            descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if os.fspath(path) == name and flags & os.O_EXCL:
            artifact_fd = descriptor
        return descriptor

    def fail_artifact_fstat(descriptor):
        if descriptor == artifact_fd:
            raise OSError("synthetic ownership capture failure")
        return real_fstat(descriptor)

    def track_close(descriptor):
        closed.add(descriptor)
        return real_close(descriptor)

    monkeypatch.setattr(runner.os, "open", track_open)
    monkeypatch.setattr(runner.os, "fstat", fail_artifact_fstat)
    monkeypatch.setattr(runner.os, "close", track_close)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="artifact may have become durable",
    ):
        runner._write_content_addressed_json(
            "feature_moments", value, artifact_root=tmp_path,
        )

    assert artifact_fd is not None
    assert artifact_fd in closed


def test_idempotent_writer_syncs_visible_inode_before_creator_finishes(
    tmp_path, monkeypatch,
):
    value = _content_addressed_test_value()
    raw = runner._canonical_bytes(value)
    path = _content_addressed_test_path(tmp_path, value)
    real_fsync = os.fsync
    creator_waiting = threading.Event()
    release_creator = threading.Event()
    idempotent_synced = threading.Event()
    creator_errors: list[BaseException] = []
    creator_receipts: list[dict] = []
    paused = False

    def controlled_fsync(descriptor):
        nonlocal paused
        info = os.fstat(descriptor)
        if stat.S_ISREG(info.st_mode):
            if (threading.current_thread().name == "artifact-creator"
                    and not paused):
                paused = True
                creator_waiting.set()
                if not release_creator.wait(10):
                    raise OSError("timed out waiting for idempotent writer")
            else:
                idempotent_synced.set()
        return real_fsync(descriptor)

    def create_artifact():
        try:
            creator_receipts.append(runner._write_content_addressed_json(
                "feature_moments", value, artifact_root=tmp_path,
            ))
        except BaseException as exc:  # surfaced below in the main test thread
            creator_errors.append(exc)

    monkeypatch.setattr(runner.os, "fsync", controlled_fsync)
    creator = threading.Thread(
        target=create_artifact, name="artifact-creator", daemon=True,
    )
    creator.start()
    assert creator_waiting.wait(10)
    try:
        idempotent_receipt = runner._write_content_addressed_json(
            "feature_moments", value, artifact_root=tmp_path,
        )
        assert idempotent_synced.is_set()
    finally:
        release_creator.set()
        creator.join(10)

    assert not creator.is_alive()
    assert not creator_errors
    assert creator_receipts == [idempotent_receipt]
    assert path.read_bytes() == raw


def test_idempotent_writer_rejects_identical_inode_swap_during_directory_sync(
    tmp_path, monkeypatch,
):
    value = _content_addressed_test_value()
    raw = runner._canonical_bytes(value)
    path = _content_addressed_test_path(tmp_path, value)
    parked = tmp_path / "original-identical.parked"
    replacement = tmp_path / "identical-replacement.tmp"
    path.write_bytes(raw); path.chmod(0o444)
    replacement.write_bytes(raw); replacement.chmod(0o444)
    original_inode = path.stat().st_ino
    replacement_inode = replacement.stat().st_ino
    real_fsync_directory = runner._fsync_artifact_directory
    swapped = False

    def swap_identical_entry(descriptor):
        nonlocal swapped
        real_fsync_directory(descriptor)
        if not swapped:
            path.rename(parked)
            replacement.rename(path)
            swapped = True

    monkeypatch.setattr(
        runner, "_fsync_artifact_directory", swap_identical_entry,
    )
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="artifact identity is ambiguous",
    ):
        runner._write_content_addressed_json(
            "feature_moments", value, artifact_root=tmp_path,
        )

    assert swapped
    assert original_inode != replacement_inode
    assert parked.stat().st_ino == original_inode
    assert path.stat().st_ino == replacement_inode
    assert parked.read_bytes() == path.read_bytes() == raw


def test_content_addressed_writer_never_deletes_pathname_replacement(
    tmp_path, monkeypatch,
):
    value = _content_addressed_test_value()
    path = _content_addressed_test_path(tmp_path, value)
    replacement = tmp_path / "replacement.tmp"
    parked = tmp_path / "created-artifact.parked"
    replacement_bytes = b"unexpected replacement bytes\n"
    replacement.write_bytes(replacement_bytes)
    replacement_inode = replacement.stat().st_ino
    real_fsync_directory = runner._fsync_artifact_directory
    calls = 0

    def replace_then_fail(descriptor):
        nonlocal calls
        calls += 1
        if calls == 1:
            path.replace(parked)
            replacement.replace(path)
            raise OSError("synthetic post-create failure")
        return real_fsync_directory(descriptor)

    monkeypatch.setattr(
        runner, "_fsync_artifact_directory", replace_then_fail,
    )
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="no longer names the created inode",
    ):
        runner._write_content_addressed_json(
            "feature_moments", value, artifact_root=tmp_path,
        )

    assert path.read_bytes() == replacement_bytes
    assert path.stat().st_ino == replacement_inode
    assert parked.read_bytes() == runner._canonical_bytes(value)
    assert not tuple(tmp_path.glob(f".{path.name}.rollback-*"))


def test_content_addressed_writer_rechecks_visible_name_after_directory_sync(
    tmp_path, monkeypatch,
):
    value = _content_addressed_test_value()
    path = _content_addressed_test_path(tmp_path, value)
    parked = tmp_path / "created-artifact.parked"
    replacement = tmp_path / "replacement.tmp"
    replacement_bytes = b"replacement installed during directory fsync\n"
    replacement.write_bytes(replacement_bytes)
    real_fsync_directory = runner._fsync_artifact_directory
    calls = 0

    def replace_during_successful_sync(descriptor):
        nonlocal calls
        calls += 1
        real_fsync_directory(descriptor)
        if calls == 1:
            path.replace(parked)
            replacement.replace(path)

    monkeypatch.setattr(
        runner, "_fsync_artifact_directory", replace_during_successful_sync,
    )
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="no longer names the created inode",
    ):
        runner._write_content_addressed_json(
            "feature_moments", value, artifact_root=tmp_path,
        )

    assert path.read_bytes() == replacement_bytes
    assert parked.read_bytes() == runner._canonical_bytes(value)


def test_created_writer_rejects_identical_inode_swap_during_directory_sync(
    tmp_path, monkeypatch,
):
    value = _content_addressed_test_value()
    raw = runner._canonical_bytes(value)
    path = _content_addressed_test_path(tmp_path, value)
    parked = tmp_path / "created-identical.parked"
    replacement = tmp_path / "created-identical-replacement.tmp"
    replacement.write_bytes(raw); replacement.chmod(0o444)
    replacement_inode = replacement.stat().st_ino
    real_fsync_directory = runner._fsync_artifact_directory
    swapped = False

    def swap_identical_entry(descriptor):
        nonlocal swapped
        real_fsync_directory(descriptor)
        if not swapped:
            path.rename(parked)
            replacement.rename(path)
            swapped = True

    monkeypatch.setattr(
        runner, "_fsync_artifact_directory", swap_identical_entry,
    )
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="no longer names the created inode",
    ):
        runner._write_content_addressed_json(
            "feature_moments", value, artifact_root=tmp_path,
        )

    assert swapped
    assert path.stat().st_ino == replacement_inode
    assert path.read_bytes() == parked.read_bytes() == raw


def test_content_addressed_failure_never_unlinks_after_ownership_check(
    tmp_path, monkeypatch,
):
    value = _content_addressed_test_value()
    path = _content_addressed_test_path(tmp_path, value)
    raw = runner._canonical_bytes(value)
    path.write_bytes(raw)
    path.chmod(0o444)
    opened = path.stat()
    ownership = runner._ContentAddressedOwnership(
        device=opened.st_dev, inode=opened.st_ino,
        n_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
    )
    parked = tmp_path / "owned.parked"
    victim = tmp_path / "victim.tmp"
    victim_bytes = b"must survive post-check substitution\n"
    victim.write_bytes(victim_bytes)
    real_matches = runner._matches_owned_content_addressed_entry_at

    def swap_after_match(directory_fd, name, expected):
        assert real_matches(directory_fd, name, expected)
        path.replace(parked)
        victim.replace(path)
        return True

    monkeypatch.setattr(
        runner, "_matches_owned_content_addressed_entry_at", swap_after_match,
    )
    directory_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(
            runner.ManualReconciliationRequired,
            match="owned failed artifact preserved at",
        ):
            runner._rollback_content_addressed_entry_at(
                directory_fd, path.name, ownership, label="feature_moments",
            )
    finally:
        os.close(directory_fd)

    assert path.read_bytes() == victim_bytes
    assert parked.read_bytes() == raw


def test_existing_claims_reestablish_directory_durability(tmp_path, monkeypatch):
    digest = "a" * 64
    directory_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert runner._reserve_digest_at(
            directory_fd, "decision-test", digest,
        ) is True
        with runner._digest_reservation_at(
            directory_fd, "optimizer-test", digest, create=True,
        ) as created:
            assert created is True
        intent = _synthetic_optimizer_intent()
        optimizer_record = runner._write_optimizer_artifact_at(
            "optimizer_intent", intent, directory_fd=directory_fd,
        )

        monkeypatch.setattr(
            runner, "_fsync_artifact_directory",
            lambda descriptor: (_ for _ in ()).throw(
                sh.LockMismatch("synthetic decision claim durability failure")
            ),
        )
        with pytest.raises(
            runner.ManualReconciliationRequired,
            match="decision-test reservation name could not be durably bound",
        ):
            runner._reserve_digest_at(
                directory_fd, "decision-test", digest,
            )

        monkeypatch.setattr(
            runner, "_fsync_artifact_directory",
            lambda descriptor: (_ for _ in ()).throw(
                OSError("synthetic optimizer claim durability failure")
            ),
        )
        with pytest.raises(
            runner.ManualReconciliationRequired,
            match="optimizer-test reservation name could not be durably bound",
        ):
            with runner._digest_reservation_at(
                directory_fd, "optimizer-test", digest, create=True,
            ):
                raise AssertionError("existing undurable claim was accepted")
        with pytest.raises(
            runner.ManualReconciliationRequired,
            match="artifact name could not be durably bound",
        ):
            runner._write_optimizer_artifact_at(
                "optimizer_intent", intent, directory_fd=directory_fd,
            )
    finally:
        os.close(directory_fd)

    assert (tmp_path / ".decision-test.claim").read_text() == digest + "\n"
    assert (tmp_path / ".optimizer-test.claim").read_text() == digest + "\n"
    assert (tmp_path / Path(optimizer_record["path"]).name).is_file()


def test_digest_claim_missing_pre_name_read_is_resumable(tmp_path):
    directory_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(
            runner.ResumableRunInterruption,
            match="reservation I/O failed before name creation",
        ):
            with runner._digest_reservation_at(
                directory_fd, "missing-taxonomy", "a" * 64, create=False,
            ):
                pytest.fail("missing claim yielded authority")
    finally:
        os.close(directory_fd)


@pytest.mark.parametrize(("failure", "pattern"), [
    ("open", "reservation name could not be durably bound"),
    ("write", "reservation was created before the active failure"),
    ("file_fsync", "reservation was created before the active failure"),
    ("directory_fsync", "reservation was created before the active failure"),
    ("close", "reservation descriptor cleanup is ambiguous"),
])
def test_digest_claim_post_create_boundary_is_manual(
    tmp_path, monkeypatch, failure, pattern,
):
    directory_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    filename = ".claim-taxonomy.claim"
    real_open = runner.os.open
    real_write = runner.os.write
    real_fsync = runner.os.fsync
    real_close = runner.os.close
    claim_descriptor = -1

    def controlled_open(path, flags, *args, **kwargs):
        nonlocal claim_descriptor
        if os.fspath(path) == filename and flags & os.O_EXCL:
            if failure == "open":
                raise OSError("synthetic claim O_CREAT ambiguity")
            claim_descriptor = real_open(path, flags, *args, **kwargs)
            return claim_descriptor
        return real_open(path, flags, *args, **kwargs)

    def controlled_write(descriptor, raw):
        if failure == "write" and descriptor == claim_descriptor:
            raise OSError("synthetic claim write ambiguity")
        return real_write(descriptor, raw)

    def controlled_fsync(descriptor):
        if failure == "file_fsync" and descriptor == claim_descriptor:
            raise OSError("synthetic claim fsync ambiguity")
        return real_fsync(descriptor)

    def controlled_close(descriptor):
        if failure == "close" and descriptor == claim_descriptor:
            raise OSError("synthetic claim close ambiguity")
        return real_close(descriptor)

    monkeypatch.setattr(runner.os, "open", controlled_open)
    monkeypatch.setattr(runner.os, "write", controlled_write)
    monkeypatch.setattr(runner.os, "fsync", controlled_fsync)
    monkeypatch.setattr(runner.os, "close", controlled_close)
    if failure == "directory_fsync":
        monkeypatch.setattr(
            runner, "_fsync_artifact_directory",
            lambda descriptor: (_ for _ in ()).throw(
                OSError("synthetic claim directory fsync ambiguity")
            ),
        )
    try:
        with pytest.raises(
            runner.ManualReconciliationRequired, match=pattern,
        ):
            with runner._digest_reservation_at(
                directory_fd, "claim-taxonomy", "a" * 64, create=True,
            ):
                pass
    finally:
        monkeypatch.setattr(runner.os, "close", real_close)
        if claim_descriptor >= 0:
            try:
                real_close(claim_descriptor)
            except OSError:
                pass
        real_close(directory_fd)


@pytest.mark.parametrize(("raw", "expected", "pattern"), [
    (
        b"", runner.ManualReconciliationRequired,
        "not a proven complete claim",
    ),
    (
        b"short\n", runner.ManualReconciliationRequired,
        "not a proven complete claim",
    ),
    (
        ("b" * 64 + "\n").encode("ascii"), sh.LockMismatch,
        "reservation differs",
    ),
])
def test_existing_digest_claim_requires_proven_full_conflict(
    tmp_path, raw, expected, pattern,
):
    claim = tmp_path / ".claim-taxonomy.claim"
    claim.write_bytes(raw)
    claim.chmod(0o444)
    directory_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(expected, match=pattern):
            with runner._digest_reservation_at(
                directory_fd, "claim-taxonomy", "a" * 64, create=True,
            ):
                pytest.fail("invalid existing claim yielded authority")
    finally:
        os.close(directory_fd)


def test_valid_existing_digest_claim_preserves_body_failure(tmp_path):
    digest = "a" * 64
    directory_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    active = sh.FitFailure("synthetic claim-body refusal")
    try:
        with runner._digest_reservation_at(
            directory_fd, "claim-taxonomy", digest, create=True,
        ) as created:
            assert created
        with pytest.raises(sh.FitFailure) as stopped:
            with runner._digest_reservation_at(
                directory_fd, "claim-taxonomy", digest, create=True,
            ) as created:
                assert not created
                raise active
        assert stopped.value is active
    finally:
        os.close(directory_fd)


def test_new_digest_claim_preserves_body_failure_after_durable_creation(
    tmp_path,
):
    directory_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    active = sh.FitFailure("synthetic new-claim body refusal")
    try:
        with pytest.raises(sh.FitFailure) as stopped:
            with runner._digest_reservation_at(
                directory_fd, "claim-taxonomy", "a" * 64, create=True,
            ) as created:
                assert created
                raise active
        assert stopped.value is active
    finally:
        os.close(directory_fd)
    assert (tmp_path / ".claim-taxonomy.claim").read_bytes() \
        == ("a" * 64 + "\n").encode("ascii")


def test_digest_claim_close_ambiguity_overrides_active_scientific_result(
    tmp_path, monkeypatch,
):
    """Descriptor-cleanup ambiguity must override a pending scientific stop."""
    directory_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    real_open = runner.os.open
    real_close = runner.os.close
    claim_descriptor = -1
    active = sh.FitFailure("synthetic active scientific refusal")

    def capture_claim_open(path, flags, *args, **kwargs):
        nonlocal claim_descriptor
        descriptor = real_open(path, flags, *args, **kwargs)
        if os.fspath(path) == ".claim-ambiguity.claim":
            claim_descriptor = descriptor
        return descriptor

    def ambiguous_close(descriptor):
        if descriptor == claim_descriptor:
            raise OSError("synthetic claim close ambiguity")
        return real_close(descriptor)

    monkeypatch.setattr(runner.os, "open", capture_claim_open)
    monkeypatch.setattr(runner.os, "close", ambiguous_close)
    try:
        with pytest.raises(
            runner.ManualReconciliationRequired,
            match="reservation descriptor cleanup is ambiguous",
        ) as stopped:
            with runner._digest_reservation_at(
                directory_fd, "claim-ambiguity", "a" * 64, create=True,
            ):
                raise active
        assert "active failure was" in str(stopped.value)
        assert repr(active) in str(stopped.value)
    finally:
        monkeypatch.setattr(runner.os, "close", real_close)
        if claim_descriptor >= 0:
            try:
                real_close(claim_descriptor)
            except OSError:
                pass
        real_close(directory_fd)


def test_leased_claim_body_oserror_propagates_after_clean_close(tmp_path):
    """A caller-body OSError survives only via verified stable cleanup."""
    digest = "a" * 64
    directory_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    active = OSError("synthetic caller body I/O failure")
    try:
        with runner._digest_reservation_at(
            directory_fd, "claim-body-io", digest, create=True,
        ) as created:
            assert created
        with pytest.raises(OSError) as stopped:
            with runner._digest_reservation_at(
                directory_fd, "claim-body-io", digest, create=True,
            ) as created:
                assert not created
                raise active
        assert stopped.value is active
    finally:
        os.close(directory_fd)
    assert (tmp_path / ".claim-body-io.claim").read_bytes() \
        == (digest + "\n").encode("ascii")


def test_existing_decision_claim_rejects_identical_swap_during_directory_sync(
    tmp_path, monkeypatch,
):
    digest = "a" * 64
    visible = tmp_path / ".decision-test.claim"
    parked = tmp_path / ".decision-test.claim.parked"
    replacement = tmp_path / ".decision-test.claim.replacement"
    directory_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert runner._reserve_digest_at(
            directory_fd, "decision-test", digest,
        ) is True
        raw = visible.read_bytes()
        replacement.write_bytes(raw); replacement.chmod(0o444)
        original_inode = visible.stat().st_ino
        replacement_inode = replacement.stat().st_ino
        real_sync = runner._fsync_artifact_directory
        swapped = False

        def swap_identical_claim(descriptor):
            nonlocal swapped
            real_sync(descriptor)
            if not swapped:
                visible.rename(parked)
                replacement.rename(visible)
                swapped = True

        monkeypatch.setattr(
            runner, "_fsync_artifact_directory",
            swap_identical_claim,
        )
        with pytest.raises(
            runner.ManualReconciliationRequired,
            match="decision-test reservation identity is ambiguous",
        ):
            runner._reserve_digest_at(
                directory_fd, "decision-test", digest,
            )
    finally:
        os.close(directory_fd)

    assert swapped
    assert original_inode != replacement_inode
    assert parked.stat().st_ino == original_inode
    assert visible.stat().st_ino == replacement_inode
    assert parked.read_bytes() == visible.read_bytes() == raw


def test_created_decision_claim_rejects_identical_swap_during_directory_sync(
    tmp_path, monkeypatch,
):
    digest = "a" * 64
    raw = (digest + "\n").encode("ascii")
    visible = tmp_path / ".decision-test.claim"
    parked = tmp_path / ".decision-test.claim.parked"
    replacement = tmp_path / ".decision-test.claim.replacement"
    replacement.write_bytes(raw); replacement.chmod(0o444)
    replacement_inode = replacement.stat().st_ino
    directory_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    real_sync = runner._fsync_artifact_directory
    swapped = False

    def swap_identical_claim(descriptor):
        nonlocal swapped
        real_sync(descriptor)
        if not swapped:
            visible.rename(parked)
            replacement.rename(visible)
            swapped = True

    monkeypatch.setattr(
        runner, "_fsync_artifact_directory", swap_identical_claim,
    )
    try:
        with pytest.raises(
            runner.ManualReconciliationRequired,
            match="decision-test reservation identity is ambiguous",
        ):
            runner._reserve_digest_at(
                directory_fd, "decision-test", digest,
            )
    finally:
        os.close(directory_fd)

    assert swapped
    assert parked.stat().st_ino != replacement_inode
    assert visible.stat().st_ino == replacement_inode
    assert parked.read_bytes() == visible.read_bytes() == raw


def test_existing_optimizer_artifact_rejects_identical_swap_during_sync(
    tmp_path, monkeypatch,
):
    intent = _synthetic_optimizer_intent()
    directory_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        record = runner._write_optimizer_artifact_at(
            "optimizer_intent", intent, directory_fd=directory_fd,
        )
        visible = tmp_path / Path(record["path"]).name
        parked = tmp_path / "optimizer-intent-identical.parked"
        replacement = tmp_path / "optimizer-intent-identical.replacement"
        raw = visible.read_bytes()
        replacement.write_bytes(raw); replacement.chmod(0o444)
        original_inode = visible.stat().st_ino
        replacement_inode = replacement.stat().st_ino
        real_sync = runner._fsync_artifact_directory
        swapped = False

        def swap_identical_artifact(descriptor):
            nonlocal swapped
            real_sync(descriptor)
            if not swapped:
                visible.rename(parked)
                replacement.rename(visible)
                swapped = True

        monkeypatch.setattr(
            runner, "_fsync_artifact_directory", swap_identical_artifact,
        )
        with pytest.raises(
            runner.ManualReconciliationRequired,
            match="artifact identity is ambiguous",
        ):
            runner._write_optimizer_artifact_at(
                "optimizer_intent", intent, directory_fd=directory_fd,
            )
    finally:
        os.close(directory_fd)

    assert swapped
    assert original_inode != replacement_inode
    assert parked.stat().st_ino == original_inode
    assert visible.stat().st_ino == replacement_inode
    assert parked.read_bytes() == visible.read_bytes() == raw


def test_idempotent_claims_and_optimizer_artifacts_sync_exact_inodes(
    tmp_path, monkeypatch,
):
    digest = "a" * 64
    directory_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert runner._reserve_digest_at(
            directory_fd, "decision-test", digest,
        ) is True
        with runner._digest_reservation_at(
            directory_fd, "optimizer-test", digest, create=True,
        ) as created:
            assert created is True
        intent = _synthetic_optimizer_intent()
        attempt = runner._begin_optimizer_once(intent, artifact_root=tmp_path)
        receipt = _synthetic_optimizer_receipt(attempt, intent)
        receipt_record = runner._record_optimizer_receipt(
            intent_record=attempt.intent_record, receipt=receipt,
            artifact_root=tmp_path,
        )

        names = (
            ".decision-test.claim",
            ".optimizer-test.claim",
            ".optimizer-intent.claim",
            Path(attempt.intent_record["path"]).name,
            ".optimizer-receipt.claim",
            Path(receipt_record["path"]).name,
        )
        expected_inodes = {os.stat(
            name, dir_fd=directory_fd, follow_symlinks=False,
        ).st_ino for name in names}
        synced_inodes: set[int] = set()
        real_fsync = os.fsync

        def record_file_sync(descriptor):
            info = os.fstat(descriptor)
            if stat.S_ISREG(info.st_mode):
                synced_inodes.add(info.st_ino)
            return real_fsync(descriptor)

        monkeypatch.setattr(runner.os, "fsync", record_file_sync)
        assert runner._reserve_digest_at(
            directory_fd, "decision-test", digest,
        ) is False
        runner._require_digest_at(
            directory_fd, "decision-test", digest,
        )
        with runner._digest_reservation_at(
            directory_fd, "optimizer-test", digest, create=True,
        ) as created:
            assert created is False
        assert runner._record_optimizer_receipt(
            intent_record=attempt.intent_record, receipt=receipt,
            artifact_root=tmp_path,
        ) == receipt_record
    finally:
        os.close(directory_fd)

    assert expected_inodes <= synced_inodes


def _synthetic_k2_bundle(root: Path) -> dict:
    schedule = tuple({
        "ordinal": ordinal,
        "match_id": f"train-{ordinal}",
        "season": "synthetic/01",
        "date": f"2020-01-{4 + ordinal:02d}",
        "home_key": f"home-{ordinal}",
        "away_key": f"away-{ordinal}",
        "block": "synthetic-2020-W01" if ordinal < 2 else "synthetic-2020-W02",
        "cutoff": "2020-01-04" if ordinal < 2 else "2020-01-06",
    } for ordinal in range(4))
    schedule_sha256 = runner._digest_rows(
        runner._K2_SCHEDULE_SCHEMA, schedule,
    )
    h = runner._VerifiedH(
        "a" * 40, "b" * 64, schedule_sha256, "d" * 64,
    )
    sandbox_contract = runner._native_sandbox_contract()
    raw_inputs = [{
        "path": f"data/epl/raw/{name}",
        "sha256": runner._native_raw_digests()[name],
        "bytes": 1,
    } for name in runner._NATIVE_RAW_NAMES]
    native_intent = {
        "schema": runner._NATIVE_INTENT_SCHEMA,
        "harness_commit": h.commit,
        "harness_manifest_sha256": h.manifest_sha256,
        "parent_commit": runner._NATIVE_PARENT_COMMIT,
        "parent_tree": runner._NATIVE_PARENT_TREE,
        "training_schedule_sha256": schedule_sha256,
        "raw_inputs": raw_inputs,
        "schedule": [dict(row) for row in schedule],
        "sandbox_contract_sha256": runner._native_sandbox_contract_sha256(
            sandbox_contract,
        ),
    }
    native_intent_record = runner._write_content_addressed_json(
        "native_intent", native_intent, artifact_root=root,
    )
    native_intent_sha256 = native_intent_record["sha256"]
    # This synthetic design has beta=0 as an exact stationary optimum: the
    # outcome frequencies match the common native vector and every feature
    # column is orthogonal to both residual vectors.
    natives = tuple([0.50, 0.25, 0.25] for _ in range(4))
    outcomes = (0, 0, 1, 2)
    blocks = runner._schedule_blocks_exact(schedule)
    shard_values = []
    shard_records = []
    for block_ordinal, block in enumerate(blocks):
        rows = []
        for expected in block:
            ordinal = expected["ordinal"]
            rows.append({
                key: expected[key] for key in (
                    "ordinal", "match_id", "season", "block", "cutoff",
                    "home_key", "away_key",
                )
            } | {"native": natives[ordinal], "y": outcomes[ordinal]})
        shard = {
            "schema": runner._NATIVE_BLOCK_SCHEMA,
            "native_intent_sha256": native_intent_sha256,
            "block_identity_sha256": runner._native_block_identity_sha256(
                native_intent_sha256, block_ordinal, block,
            ),
            "harness_commit": h.commit,
            "harness_manifest_sha256": h.manifest_sha256,
            "parent_commit": runner._NATIVE_PARENT_COMMIT,
            "parent_tree": runner._NATIVE_PARENT_TREE,
            "training_schedule_sha256": schedule_sha256,
            "block_ordinal": block_ordinal,
            "block": block[0]["block"],
            "cutoff": block[0]["cutoff"],
            "rows": rows,
            # The full fixed worker receipt is required for the real 1,520-row
            # schedule.  Small synthetic schedules deliberately use no model.
            "receipt": {},
        }
        shard_values.append(shard)
        shard_records.append(runner._write_native_block_shard(
            shard, artifact_root=root,
        ))
    job_ordinals = list(range(len(blocks)))
    request = runner._native_request(
        native_intent=native_intent,
        native_intent_sha256=native_intent_sha256,
        block_ordinals=job_ordinals, block_count=len(blocks),
    )
    temporary = root / "synthetic-native-job"
    parent = temporary / "parent"
    request_path = temporary / "request.json"
    runtime = temporary / "runtime"
    profile = runner._native_sandbox_profile(
        contract=sandbox_contract, temporary_root=temporary,
        parent_root=parent, request_path=request_path, runtime_root=runtime,
    )
    environment = runner._native_environment_values(
        contract=sandbox_contract, parent_root=parent,
        request_path=request_path, runtime_root=runtime,
    )
    sandbox_run = runner._native_sandbox_run_receipt(
        contract=sandbox_contract, profile=profile,
        temporary_root=temporary, parent_root=parent,
        request_path=request_path, runtime_root=runtime,
        environment=environment,
    )
    runtime.mkdir(parents=True)
    (runtime / "native-stderr.log").write_bytes(b"synthetic native log\n")
    runtime_snapshot = runner._native_runtime_output_snapshot(runtime)
    completion = runner._make_native_completion_receipt(
        native_intent_sha256=native_intent_sha256,
        job_request_sha256=hashlib.sha256(
            runner._canonical_bytes(request)
        ).hexdigest(),
        job_ordinals=job_ordinals, block_records=shard_records,
        sandbox_run=sandbox_run,
        output_bytes=sum(record["bytes"] for record in shard_records),
        runtime_snapshot=runtime_snapshot,
        runtime_observed={
            "files": runtime_snapshot["file_count"],
            "bytes": runtime_snapshot["bytes"], "rss_bytes": 0,
        },
    )
    completion_record = runner._write_content_addressed_json(
        "native_completion", completion, artifact_root=root,
    )
    block_set_sha256 = runner._native_block_set_sha256(shard_records)

    expectations = (
        {"HS_hat": 14.75, "AS_hat": 10.25, "HST_hat": 6.0, "AST_hat": 3.0},
        {"HS_hat": 11.25, "AS_hat": 9.75, "HST_hat": 4.0, "AST_hat": 3.0},
        {"HS_hat": 13.0, "AS_hat": 10.0, "HST_hat": 5.0, "AST_hat": 3.0},
        {"HS_hat": 13.0, "AS_hat": 10.0, "HST_hat": 5.0, "AST_hat": 3.0},
    )
    x = np.asarray([
        [3.0, 1.5, 9.0, 16.0],
        [1.0, 0.5, 7.0, 14.0],
        [2.0, 1.0, 8.0, 15.0],
        [2.0, 1.0, 8.0, 15.0],
    ], dtype=np.float64)
    means = x.mean(axis=0)
    standard_deviations = x.std(axis=0, ddof=0)
    z = (x - means) / standard_deviations
    moments = {
        "schema": runner._k2_schemas()["feature_moments"],
        "training_schedule_sha256": schedule_sha256,
        "native_block_set_sha256": block_set_sha256,
        "names": list(sh.FEATURE_NAMES),
        "means": means.tolist(),
        "population_standard_deviations": standard_deviations.tolist(),
        "ddof": 0,
        "n_training": len(schedule),
        "seasons": ["synthetic/01"],
    }
    moments_record = runner._write_content_addressed_json(
        "feature_moments", moments, artifact_root=root,
    )
    outcome_sha256 = runner._training_outcome_sha256(schedule, outcomes)
    intent = runner._make_optimizer_intent(
        h=h, native_block_set_sha256=block_set_sha256,
        feature_moments_sha256=moments_record["sha256"],
        training_outcomes_sha256=outcome_sha256,
    )
    attempt = runner._begin_optimizer_once(intent, artifact_root=root)
    assert attempt.may_invoke_optimizer
    beta = np.zeros(8, dtype=np.float64)
    native_array = np.asarray(natives, dtype=np.float64)
    objective, gradient = sh._tilt_loss_gradient(
        beta, native_array, z, np.asarray(outcomes),
    )
    receipt = runner._make_optimizer_receipt(
        intent_record=attempt.intent_record, intent=intent,
        success=True, status=0, beta=beta, objective_value=objective,
        gradient=gradient, independent_objective_value=objective,
        independent_gradient=gradient,
        iterations=7, function_evaluations=10,
        gradient_evaluations=10, message="synthetic convergence receipt",
    )
    receipt_record = runner._record_optimizer_receipt(
        intent_record=attempt.intent_record, receipt=receipt,
        artifact_root=root,
    )
    coefficients = {
        "schema": runner._k2_schemas()["coefficients"],
        "training_schedule_sha256": schedule_sha256,
        "native_block_set_sha256": block_set_sha256,
        "feature_moments_sha256": moments_record["sha256"],
        "optimizer_receipt_sha256": receipt_record["sha256"],
        "feature_names": list(sh.FEATURE_NAMES),
        "reference_outcome": "away",
        "coefficient_order": list(runner._K2_COEFFICIENT_ORDER),
        "beta_H": beta[:4].tolist(),
        "beta_D": beta[4:].tolist(),
    }
    coefficients_record = runner._write_content_addressed_json(
        "coefficients", coefficients, artifact_root=root,
    )
    candidate = sh._transform_probabilities(native_array, z, beta)
    training_rows = []
    for ordinal, expected in enumerate(schedule):
        training_rows.append(dict(expected) | {
            "shot_expectations": expectations[ordinal],
            "features": dict(zip(
                sh.FEATURE_NAMES, map(float, x[ordinal]), strict=True,
            )),
            "standardized_features": dict(zip(
                sh.FEATURE_NAMES, map(float, z[ordinal]), strict=True,
            )),
            "native": natives[ordinal],
            "candidate": candidate[ordinal].tolist(),
            "y": outcomes[ordinal],
        })
    training = {
        "schema": runner._k2_schemas()["training_predictions"],
        "training_schedule_sha256": schedule_sha256,
        "native_block_set_sha256": block_set_sha256,
        "feature_moments_sha256": moments_record["sha256"],
        "coefficients_sha256": coefficients_record["sha256"],
        "optimizer_receipt_sha256": receipt_record["sha256"],
        "n_rows": len(schedule),
        "rows": training_rows,
    }
    training_record = runner._write_content_addressed_json(
        "training_predictions", training, artifact_root=root,
    )
    records = {
        "training_predictions": {
            "index": training_record,
            "native_intent": native_intent_record,
            "native_blocks": shard_records,
            "native_completions": [completion_record],
        },
        "feature_moments": moments_record,
        "coefficients": coefficients_record,
        "optimizer": {
            "intent": dict(attempt.intent_record), "receipt": receipt_record,
        },
    }
    values = {
        "training_predictions": {
            "index": training,
            "native_intent": native_intent,
            "native_blocks": shard_values,
            "native_completions": [completion],
        },
        "feature_moments": moments,
        "coefficients": coefficients,
        "optimizer": {"intent": intent, "receipt": receipt},
    }
    test_reference = runner._K2TrainingReference(
        schedule_sha256=schedule_sha256,
        outcomes=tuple(outcomes),
        shot_expectations=tuple(tuple(
            float(row[name])
            for name in ("HS_hat", "AS_hat", "HST_hat", "AST_hat")
        ) for row in expectations),
        features=tuple(tuple(float(value) for value in row) for row in x),
    )
    return {"h": h, "schedule": schedule, "records": records,
            "values": values,
            "_test_only_training_reference": test_reference}


def _json_copy(value):
    return json.loads(json.dumps(value))


def _orphan_native_shard(*, ordinal: int = 3) -> dict:
    intent_sha256 = "a" * 64
    block = f"synthetic-2020-W{ordinal:02d}"
    cutoff = "2020-01-04"
    return {
        "schema": runner._NATIVE_BLOCK_SCHEMA,
        "native_intent_sha256": intent_sha256,
        "block_identity_sha256": runner._native_block_identity_sha256(
            intent_sha256, ordinal, [{"synthetic": True}],
        ),
        "harness_commit": "c" * 40,
        "harness_manifest_sha256": "d" * 64,
        "parent_commit": runner._NATIVE_PARENT_COMMIT,
        "parent_tree": runner._NATIVE_PARENT_TREE,
        "training_schedule_sha256": "b" * 64,
        "block_ordinal": ordinal,
        "block": block,
        "cutoff": cutoff,
        "rows": [{
            "ordinal": ordinal, "match_id": f"m{ordinal}",
            "season": "synthetic/01", "block": block, "cutoff": cutoff,
            "home_key": "home", "away_key": "away",
            "native": [0.5, 0.3, 0.2], "y": 0,
        }],
        "receipt": {},
    }


def test_orphan_native_shard_retry_with_matching_hash_is_idempotent(tmp_path):
    shard = _orphan_native_shard()
    first = runner._write_native_block_shard(
        shard, artifact_root=tmp_path,
    )
    assert not tuple(tmp_path.glob("native-completion-*.json"))
    assert runner._write_native_block_shard(
        shard, artifact_root=tmp_path,
    ) == first
    assert runner._discover_native_block_shards(
        artifact_root=tmp_path,
    ) == ((first, shard),)


def test_orphan_native_shard_retry_rejects_digest_and_ordinal_forks(tmp_path):
    shard = _orphan_native_shard()
    runner._write_native_block_shard(shard, artifact_root=tmp_path)

    changed_digest = _json_copy(shard)
    changed_digest["rows"][0]["y"] = 1
    with pytest.raises(sh.LockMismatch, match="reservation differs"):
        runner._write_native_block_shard(
            changed_digest, artifact_root=tmp_path,
        )

    # Simulate hostile/partial bytes that bypassed the ordinal claim.  Discovery
    # must still reject two content-addressed values for one ordinal.
    runner._write_content_addressed_json(
        "native_block", changed_digest, artifact_root=tmp_path, ordinal=3,
    )
    with pytest.raises(sh.LockMismatch, match="multiple shards"):
        runner._discover_native_block_shards(artifact_root=tmp_path)

    mismatch_root = tmp_path / "ordinal-mismatch"
    mismatched_ordinal = _orphan_native_shard(ordinal=4)
    runner._write_content_addressed_json(
        "native_block", mismatched_ordinal,
        artifact_root=mismatch_root, ordinal=3,
    )
    with pytest.raises(
        sh.LockMismatch, match="filename/payload ordinal differs",
    ):
        runner._discover_native_block_shards(artifact_root=mismatch_root)


def test_native_block_shards_are_immutable_exact_and_resumable(tmp_path):
    intent_sha256 = "a" * 64
    shard = {
        "schema": runner._NATIVE_BLOCK_SCHEMA,
        "native_intent_sha256": intent_sha256,
        "block_identity_sha256": runner._native_block_identity_sha256(
            intent_sha256, 3, [{"synthetic": True}],
        ),
        "harness_commit": "c" * 40,
        "harness_manifest_sha256": "d" * 64,
        "parent_commit": runner._NATIVE_PARENT_COMMIT,
        "parent_tree": runner._NATIVE_PARENT_TREE,
        "training_schedule_sha256": "b" * 64,
        "block_ordinal": 3,
        "block": "synthetic-2020-W01",
        "cutoff": "2020-01-04",
        "rows": [{
            "ordinal": 0, "match_id": "m0", "season": "synthetic/01",
            "block": "synthetic-2020-W01", "cutoff": "2020-01-04",
            "home_key": "home", "away_key": "away",
            "native": [0.5, 0.3, 0.2], "y": 0,
        }],
        "receipt": {},
    }
    record = runner._write_native_block_shard(shard, artifact_root=tmp_path)
    assert record["path"].startswith(
        f"{sh.SHOTS_ARTIFACT_ROOT}/native-block-003-"
    )
    assert runner._write_native_block_shard(
        shard, artifact_root=tmp_path,
    ) == record
    assert runner._load_native_block_shard(
        record, artifact_root=tmp_path,
    ) == shard
    discovered = runner._discover_native_block_shards(artifact_root=tmp_path)
    assert discovered == ((record, shard),)

    changed = _json_copy(shard)
    changed["rows"][0]["y"] = 1
    with pytest.raises(sh.LockMismatch, match="reservation differs"):
        runner._write_native_block_shard(
            changed, artifact_root=tmp_path,
        )
    escaped = {**record, "path": f"{sh.SHOTS_ARTIFACT_ROOT}/../{Path(record['path']).name}"}
    with pytest.raises(sh.LockMismatch, match="path is not exact"):
        runner._load_native_block_shard(escaped, artifact_root=tmp_path)

    physical = tmp_path / Path(record["path"]).name
    physical.chmod(0o644)
    physical.write_text("{}\n", encoding="ascii")
    with pytest.raises(sh.LockMismatch, match="content-addressed bytes differ"):
        runner._load_native_block_shard(record, artifact_root=tmp_path)


def _synthetic_optimizer_intent():
    h = runner._VerifiedH("a" * 40, "b" * 64, "c" * 64, "d" * 64)
    return runner._make_optimizer_intent(
        h=h, native_block_set_sha256="e" * 64,
        feature_moments_sha256="f" * 64,
        training_outcomes_sha256="1" * 64,
    )


def _synthetic_optimizer_receipt(attempt, intent):
    return runner._make_optimizer_receipt(
        intent_record=attempt.intent_record, intent=intent,
        success=True, status=0, beta=[0.0] * 8, objective_value=1.0,
        gradient=[0.0] * 8, independent_objective_value=1.0,
        independent_gradient=[0.0] * 8,
        iterations=0, function_evaluations=1,
        gradient_evaluations=1, message="synthetic receipt",
    )


def test_optimizer_intent_is_exactly_once_and_receipted_resume_only(tmp_path):
    intent = _synthetic_optimizer_intent()
    first = runner._begin_optimizer_once(intent, artifact_root=tmp_path)
    assert first.may_invoke_optimizer and first.receipt is None
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="optimizer intent exists without a receipt",
    ):
        runner._begin_optimizer_once(intent, artifact_root=tmp_path)

    receipt = _synthetic_optimizer_receipt(first, intent)
    receipt_record = runner._record_optimizer_receipt(
        intent_record=first.intent_record, receipt=receipt,
        artifact_root=tmp_path,
    )
    resumed = runner._begin_optimizer_once(intent, artifact_root=tmp_path)
    assert not resumed.may_invoke_optimizer
    assert resumed.receipt == receipt and resumed.receipt_record == receipt_record
    assert runner._record_optimizer_receipt(
        intent_record=first.intent_record, receipt=receipt,
        artifact_root=tmp_path,
    ) == receipt_record

    changed = {**intent, "training_outcomes_sha256": "2" * 64}
    with pytest.raises(sh.LockMismatch, match="optimizer-intent reservation differs"):
        runner._begin_optimizer_once(changed, artifact_root=tmp_path)


def test_finite_optimizer_failure_is_receipted_then_resumed_without_reinvocation(
    tmp_path, monkeypatch,
):
    intent = _synthetic_optimizer_intent()
    attempt = runner._begin_optimizer_once(intent, artifact_root=tmp_path)
    native = _native(6)
    z = np.zeros((6, 4), dtype=np.float64)
    y = np.arange(6) % 3
    beta = np.zeros(8, dtype=np.float64)
    objective, gradient = sh._tilt_loss_gradient(beta, native, z, y)
    result = SimpleNamespace(
        success=False, status=2,
        x=beta, fun=objective, jac=gradient,
        nit=10_000, nfev=10_111, njev=10_111,
        message="synthetic iteration limit",
    )
    calls = 0

    def finite_failure(*args, **kwargs):
        nonlocal calls
        calls += 1
        return result

    monkeypatch.setattr(sh, "minimize", finite_failure)
    with pytest.raises(sh._TiltOptimizerFailure) as caught:
        sh._fit_residual_tilt(
            native, z, y,
        )
    receipt = runner._make_optimizer_receipt_from_fit(
        intent_record=attempt.intent_record, intent=intent,
        fit=caught.value.fit,
    )
    record = runner._record_optimizer_receipt(
        intent_record=attempt.intent_record, receipt=receipt,
        artifact_root=tmp_path,
    )

    resumed = runner._begin_optimizer_once(intent, artifact_root=tmp_path)
    assert calls == 1
    assert resumed.may_invoke_optimizer is False
    assert resumed.receipt_record == record
    assert resumed.receipt == receipt
    assert resumed.receipt["success"] is False
    assert resumed.receipt["status"] == 2


def test_optimizer_authorization_retains_created_intent_through_final_scan(
    tmp_path, monkeypatch,
):
    intent = _synthetic_optimizer_intent()
    raw = runner._canonical_bytes(intent)
    digest = hashlib.sha256(raw).hexdigest()
    visible = tmp_path / runner._k2_filename("optimizer_intent", digest)
    parked = tmp_path / "held-intent-original.tmp"
    replacement = tmp_path / "held-intent-replacement.tmp"
    replacement.write_bytes(raw); replacement.chmod(0o444)
    replacement_inode = replacement.stat().st_ino
    real_records = runner._optimizer_records_at
    intent_scans = 0
    swapped = False

    def swap_during_final_scan(logical, *, directory_fd):
        nonlocal intent_scans, swapped
        if logical == "optimizer_intent":
            intent_scans += 1
            if intent_scans == 3:
                visible.rename(parked)
                replacement.rename(visible)
                swapped = True
        return real_records(logical, directory_fd=directory_fd)

    monkeypatch.setattr(runner, "_optimizer_records_at", swap_during_final_scan)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="optimizer_intent artifact identity is ambiguous",
    ):
        runner._begin_optimizer_once(intent, artifact_root=tmp_path)

    assert swapped
    assert parked.stat().st_ino != replacement_inode
    assert visible.stat().st_ino == replacement_inode
    assert parked.read_bytes() == visible.read_bytes() == raw


def test_optimizer_commit_retains_created_receipt_through_final_scan(
    tmp_path, monkeypatch,
):
    intent = _synthetic_optimizer_intent()
    attempt = runner._begin_optimizer_once(intent, artifact_root=tmp_path)
    receipt = _synthetic_optimizer_receipt(attempt, intent)
    raw = runner._canonical_bytes(receipt)
    digest = hashlib.sha256(raw).hexdigest()
    visible = tmp_path / runner._k2_filename("optimizer_receipt", digest)
    parked = tmp_path / "held-receipt-original.tmp"
    replacement = tmp_path / "held-receipt-replacement.tmp"
    replacement.write_bytes(raw); replacement.chmod(0o444)
    replacement_inode = replacement.stat().st_ino
    real_records = runner._optimizer_records_at
    receipt_scans = 0
    swapped = False

    def swap_during_final_scan(logical, *, directory_fd):
        nonlocal receipt_scans, swapped
        if logical == "optimizer_receipt":
            receipt_scans += 1
            if receipt_scans == 2:
                visible.rename(parked)
                replacement.rename(visible)
                swapped = True
        return real_records(logical, directory_fd=directory_fd)

    monkeypatch.setattr(runner, "_optimizer_records_at", swap_during_final_scan)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="optimizer_receipt artifact identity is ambiguous",
    ):
        runner._record_optimizer_receipt(
            intent_record=attempt.intent_record, receipt=receipt,
            artifact_root=tmp_path,
        )

    assert swapped
    assert parked.stat().st_ino != replacement_inode
    assert visible.stat().st_ino == replacement_inode
    assert parked.read_bytes() == visible.read_bytes() == raw


def test_optimizer_begin_refuses_claim_substitution_during_fsync(
    tmp_path, monkeypatch,
):
    intent = _synthetic_optimizer_intent()
    digest = hashlib.sha256(runner._canonical_bytes(intent)).hexdigest()
    raw = (digest + "\n").encode("ascii")
    visible = tmp_path / ".optimizer-intent.claim"
    parked = tmp_path / ".optimizer-intent.claim.parked"
    real_fsync = os.fsync
    swapped = False

    def swapping_fsync(descriptor):
        nonlocal swapped
        result = real_fsync(descriptor)
        if not swapped and visible.exists():
            opened = os.fstat(descriptor)
            named = os.stat(visible, follow_symlinks=False)
            if ((opened.st_dev, opened.st_ino)
                    == (named.st_dev, named.st_ino)):
                visible.rename(parked)
                visible.write_bytes(raw); visible.chmod(0o444)
                swapped = True
        return result

    monkeypatch.setattr(runner.os, "fsync", swapping_fsync)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="optimizer-intent reservation identity is ambiguous",
    ):
        runner._begin_optimizer_once(intent, artifact_root=tmp_path)

    assert swapped
    assert parked.read_bytes() == visible.read_bytes() == raw
    assert not tuple(tmp_path.glob("optimizer-intent-*.json"))


def test_optimizer_receipt_refuses_claim_substitution_during_fsync(
    tmp_path, monkeypatch,
):
    intent = _synthetic_optimizer_intent()
    attempt = runner._begin_optimizer_once(intent, artifact_root=tmp_path)
    receipt = _synthetic_optimizer_receipt(attempt, intent)
    digest = hashlib.sha256(runner._canonical_bytes(receipt)).hexdigest()
    raw = (digest + "\n").encode("ascii")
    visible = tmp_path / ".optimizer-receipt.claim"
    parked = tmp_path / ".optimizer-receipt.claim.parked"
    real_fsync = os.fsync
    swapped = False

    def swapping_fsync(descriptor):
        nonlocal swapped
        result = real_fsync(descriptor)
        if not swapped and visible.exists():
            opened = os.fstat(descriptor)
            named = os.stat(visible, follow_symlinks=False)
            if ((opened.st_dev, opened.st_ino)
                    == (named.st_dev, named.st_ino)):
                visible.rename(parked)
                visible.write_bytes(raw); visible.chmod(0o444)
                swapped = True
        return result

    monkeypatch.setattr(runner.os, "fsync", swapping_fsync)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="optimizer-receipt reservation identity is ambiguous",
    ):
        runner._record_optimizer_receipt(
            intent_record=attempt.intent_record, receipt=receipt,
            artifact_root=tmp_path,
        )

    assert swapped
    assert parked.read_bytes() == visible.read_bytes() == raw
    assert not tuple(tmp_path.glob("optimizer-receipt-*.json"))
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="optimizer receipt was claimed without durable bytes",
    ):
        runner._record_optimizer_receipt(
            intent_record=attempt.intent_record, receipt=receipt,
            artifact_root=tmp_path,
        )


def test_optimizer_begin_refuses_artifact_root_substitution(
    tmp_path, monkeypatch,
):
    intent = _synthetic_optimizer_intent()
    digest = hashlib.sha256(runner._canonical_bytes(intent)).hexdigest()
    logical = tmp_path / "optimizer-root"
    parked = tmp_path / "opened-optimizer-root"
    redirected = tmp_path / "redirected-optimizer-root"
    logical.mkdir(); redirected.mkdir()
    real_open = os.open
    swapped = False

    def swapping_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if dir_fd is None:
            descriptor = real_open(path, flags, mode)
        else:
            descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if (not swapped and dir_fd is not None
                and os.fspath(path) == logical.name
                and flags & os.O_DIRECTORY):
            logical.rename(parked)
            logical.symlink_to(redirected, target_is_directory=True)
            swapped = True
        return descriptor

    monkeypatch.setattr(runner.os, "open", swapping_open)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="decision state exit is ambiguous: visible path identity changed",
    ):
        runner._begin_optimizer_once(intent, artifact_root=logical)

    assert swapped and logical.is_symlink()
    assert not tuple(redirected.iterdir())
    assert (parked / ".optimizer-intent.claim").read_bytes() == (
        digest + "\n"
    ).encode("ascii")
    assert len(tuple(parked.glob("optimizer-intent-*.json"))) == 1
    logical.unlink(); parked.rename(logical)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="optimizer intent exists without a receipt",
    ):
        runner._begin_optimizer_once(intent, artifact_root=logical)


def test_optimizer_receipt_refuses_artifact_root_substitution(
    tmp_path, monkeypatch,
):
    logical = tmp_path / "optimizer-root"; logical.mkdir()
    redirected = tmp_path / "redirected-optimizer-root"; redirected.mkdir()
    parked = tmp_path / "opened-optimizer-root"
    intent = _synthetic_optimizer_intent()
    attempt = runner._begin_optimizer_once(intent, artifact_root=logical)
    receipt = _synthetic_optimizer_receipt(attempt, intent)
    real_open = os.open
    swapped = False

    def swapping_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if dir_fd is None:
            descriptor = real_open(path, flags, mode)
        else:
            descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if (not swapped and dir_fd is not None
                and os.fspath(path) == logical.name
                and flags & os.O_DIRECTORY):
            logical.rename(parked)
            logical.symlink_to(redirected, target_is_directory=True)
            swapped = True
        return descriptor

    monkeypatch.setattr(runner.os, "open", swapping_open)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="decision state exit is ambiguous: visible path identity changed",
    ):
        runner._record_optimizer_receipt(
            intent_record=attempt.intent_record, receipt=receipt,
            artifact_root=logical,
        )

    assert swapped and logical.is_symlink()
    assert not tuple(redirected.iterdir())
    assert len(tuple(parked.glob("optimizer-receipt-*.json"))) == 1
    assert (parked / ".optimizer-receipt.claim").is_file()
    logical.unlink(); parked.rename(logical)
    recovered = runner._record_optimizer_receipt(
        intent_record=attempt.intent_record, receipt=receipt,
        artifact_root=logical,
    )
    assert recovered["sha256"] == hashlib.sha256(
        runner._canonical_bytes(receipt)
    ).hexdigest()


def test_k2_manifest_has_exact_four_groups_and_deep_semantics(tmp_path):
    bundle = _synthetic_k2_bundle(tmp_path)
    manifest = runner._build_k2_manifest(**bundle)
    assert manifest["schema"] == runner._K2_MANIFEST_SCHEMA
    assert manifest["coefficient_frozen"] is True
    assert manifest["training_rows"] == 4 and manifest["training_blocks"] == 2
    assert set(manifest["artifacts"]) == {
        "training_predictions", "feature_moments", "coefficients", "optimizer",
    }
    assert len(manifest["artifacts"]["training_predictions"]["native_blocks"]) == 2
    assert manifest["objective"] == pytest.approx(
        bundle["values"]["optimizer"]["receipt"]["objective_value"]
    )
    assert runner.H_READY is True
    assert runner.TRAINING_WORKER_READY is True
    assert runner.DECISION_WORKER_READY is True


def test_k2_default_semantics_refuses_a_non_pinned_test_schedule(tmp_path):
    bundle = _synthetic_k2_bundle(tmp_path)
    with pytest.raises(sh.FixtureSetMismatch, match="pinned 1,520-row"):
        runner._validate_k2_semantics(
            h=bundle["h"], schedule=bundle["schedule"],
            records=bundle["records"], values=bundle["values"],
        )


def test_k2_pinned_reference_rejects_wrong_y_when_k_copies_agree(tmp_path):
    bundle = _synthetic_k2_bundle(tmp_path)
    values = _json_copy(bundle["values"])
    values["training_predictions"]["native_blocks"][0]["rows"][0]["y"] = 1
    values["training_predictions"]["index"]["rows"][0]["y"] = 1
    with pytest.raises(sh.LockMismatch, match="pinned matches archive"):
        runner._validate_k2_semantics(
            h=bundle["h"], schedule=bundle["schedule"],
            records=bundle["records"], values=values,
            _test_only_training_reference=(
                bundle["_test_only_training_reference"]
            ),
        )


def test_k2_pinned_reference_rejects_self_consistent_wrong_expectations(
    tmp_path, monkeypatch,
):
    bundle = _synthetic_k2_bundle(tmp_path)
    values = _json_copy(bundle["values"])
    monkeypatch.setattr(
        sh, "shot_features",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("semantic K consulted production shot features")
        ),
    )
    for row in values["training_predictions"]["index"]["rows"]:
        for name in ("HS_hat", "AS_hat", "HST_hat", "AST_hat"):
            row["shot_expectations"][name] *= 2.0
        for name in sh.FEATURE_NAMES:
            row["features"][name] *= 2.0
    moments = values["feature_moments"]
    moments["means"] = [value * 2.0 for value in moments["means"]]
    moments["population_standard_deviations"] = [
        value * 2.0 for value in moments["population_standard_deviations"]
    ]
    with pytest.raises(sh.FitFailure, match="pinned shot reference"):
        runner._validate_k2_semantics(
            h=bundle["h"], schedule=bundle["schedule"],
            records=bundle["records"], values=values,
            _test_only_training_reference=(
                bundle["_test_only_training_reference"]
            ),
        )


@pytest.mark.parametrize("mutation, error", [
    ("schedule", sh.FixtureSetMismatch),
    ("feature_algebra", sh.FitFailure),
    ("moments", sh.FitFailure),
    ("standardization", sh.FitFailure),
    ("candidate", sh.FitFailure),
    ("objective", sh.LockMismatch),
    ("gradient", sh.LockMismatch),
])
def test_k2_semantic_recomputation_rejects_independently_tampered_values(
    tmp_path, mutation, error,
):
    bundle = _synthetic_k2_bundle(tmp_path / mutation)
    values = _json_copy(bundle["values"])
    if mutation == "schedule":
        values["training_predictions"]["index"]["rows"][0]["date"] = "2020-01-09"
    elif mutation == "feature_algebra":
        values["training_predictions"]["index"]["rows"][0]["features"]["x1"] += 1.0
    elif mutation == "moments":
        values["feature_moments"]["means"][0] += 1.0
    elif mutation == "standardization":
        values["training_predictions"]["index"]["rows"][0][
            "standardized_features"
        ]["x1"] += 1.0
    elif mutation == "candidate":
        candidate = values["training_predictions"]["index"]["rows"][0]["candidate"]
        candidate[0], candidate[1] = candidate[1], candidate[0]
    elif mutation == "objective":
        values["optimizer"]["receipt"]["objective_value"] += 1.0
    else:
        gradient = values["optimizer"]["receipt"]["gradient"]
        gradient[0] += 1.0
        values["optimizer"]["receipt"]["gradient_max_abs"] = max(
            abs(value) for value in gradient
        )
    with pytest.raises(error):
        runner._validate_k2_semantics(
            h=bundle["h"], schedule=bundle["schedule"],
            records=bundle["records"], values=values,
            _test_only_training_reference=(
                bundle["_test_only_training_reference"]
            ),
        )


def test_k2_rejects_self_consistent_but_nonstationary_beta(tmp_path):
    bundle = _synthetic_k2_bundle(tmp_path)
    values = _json_copy(bundle["values"])
    rows = values["training_predictions"]["index"]["rows"]
    beta = np.asarray([
        0.10, -0.05, 0.02, 0.03, -0.04, 0.06, -0.02, 0.01,
    ])
    native = np.asarray([row["native"] for row in rows])
    z = np.asarray([[
        row["standardized_features"][name] for name in sh.FEATURE_NAMES
    ] for row in rows])
    outcomes = np.asarray([row["y"] for row in rows])
    candidate = sh._transform_probabilities(native, z, beta)
    objective, gradient = sh._tilt_loss_gradient(beta, native, z, outcomes)
    values["coefficients"]["beta_H"] = beta[:4].tolist()
    values["coefficients"]["beta_D"] = beta[4:].tolist()
    receipt = values["optimizer"]["receipt"]
    receipt["beta"] = beta.tolist()
    receipt["objective_value"] = objective
    receipt["independent_objective_value"] = objective
    receipt["objective_consistent"] = True
    receipt["gradient"] = gradient.tolist()
    receipt["gradient_max_abs"] = float(np.max(np.abs(gradient)))
    receipt["independent_gradient"] = gradient.tolist()
    receipt["independent_gradient_max_abs"] = float(np.max(np.abs(gradient)))
    receipt["gradient_consistent"] = True
    receipt["gradient_certified"] = False
    receipt["beta_distance_actual_bound_l2"] = float(
        np.linalg.norm(gradient, ord=2)
    )
    for row, probabilities in zip(rows, candidate, strict=True):
        row["candidate"] = probabilities.tolist()
    assert receipt["gradient_max_abs"] > receipt["options"]["gtol"]
    with pytest.raises(sh.FitFailure, match="independent-gradient acceptance"):
        runner._validate_k2_semantics(
            h=bundle["h"], schedule=bundle["schedule"],
            records=bundle["records"], values=values,
            _test_only_training_reference=(
                bundle["_test_only_training_reference"]
            ),
        )


def test_k2_accepts_amended_eight_decimal_native_without_repair(tmp_path):
    bundle = _synthetic_k2_bundle(tmp_path)
    values = _json_copy(bundle["values"])
    bad_native = [0.33333333, 0.33333333, 0.33333333]
    values["training_predictions"]["native_blocks"][0]["rows"][0][
        "native"
    ] = bad_native
    native, _ = runner._validate_native_shards_for_k(
        h=bundle["h"], schedule=bundle["schedule"],
        training_sha256=bundle["h"].training_schedule_sha256,
        native_intent_sha256=bundle["records"]["training_predictions"][
            "native_intent"
        ]["sha256"],
        shards=values["training_predictions"]["native_blocks"],
    )
    np.testing.assert_array_equal(native[0], np.asarray(bad_native))
    np.testing.assert_array_equal(
        sh._native_model_probabilities(native[[0]])[0],
        np.asarray(bad_native) / sum(bad_native),
    )


def test_k2_records_require_exact_content_addressed_paths(tmp_path):
    bundle = _synthetic_k2_bundle(tmp_path)
    records = _json_copy(bundle["records"])
    records["coefficients"]["path"] = (
        f"{sh.SHOTS_ARTIFACT_ROOT}/renamed-"
        + Path(records["coefficients"]["path"]).name
    )
    with pytest.raises(sh.LockMismatch, match="path is not exact"):
        runner._validate_k2_record_values(
            records=records, values=bundle["values"],
        )


def test_native_resume_identity_is_stable_across_remaining_subsets(tmp_path):
    bundle = _synthetic_k2_bundle(tmp_path)
    intent = bundle["values"]["training_predictions"]["native_intent"]
    intent_sha256 = bundle["records"]["training_predictions"][
        "native_intent"
    ]["sha256"]
    first = runner._native_request(
        native_intent=intent, native_intent_sha256=intent_sha256,
        block_ordinals=[0, 1], block_count=2,
    )
    resumed = runner._native_request(
        native_intent=intent, native_intent_sha256=intent_sha256,
        block_ordinals=[1], block_count=2,
    )
    assert runner._canonical_bytes(first) != runner._canonical_bytes(resumed)
    shard = bundle["values"]["training_predictions"]["native_blocks"][1]
    assert shard["native_intent_sha256"] == intent_sha256
    assert shard["block_identity_sha256"] == runner._native_block_identity_sha256(
        intent_sha256, 1, runner._schedule_blocks_exact(bundle["schedule"])[1],
    )


def test_failed_job_shard_is_not_discovered_without_clean_completion(tmp_path):
    bundle = _synthetic_k2_bundle(tmp_path / "source")
    values = bundle["values"]["training_predictions"]
    failed_root = tmp_path / "failed"
    runner._write_native_block_shard(
        values["native_blocks"][0], artifact_root=failed_root,
    )
    intent = values["native_intent"]
    assert runner._discover_completed_native_block_shards(
        artifact_root=failed_root, native_intent=intent,
        native_intent_sha256=hashlib.sha256(
            runner._canonical_bytes(intent)
        ).hexdigest(),
        h=bundle["h"],
        training_sha256=bundle["h"].training_schedule_sha256,
        raw_inputs=intent["raw_inputs"],
        blocks=runner._schedule_blocks_exact(bundle["schedule"]),
        sandbox_contract=runner._native_sandbox_contract(),
    ) == ()


def test_k2_refuses_incomplete_clean_exit_coverage(tmp_path):
    bundle = _synthetic_k2_bundle(tmp_path)
    values = _json_copy(bundle["values"])
    completion = values["training_predictions"]["native_completions"][0]
    completion["job_ordinals"] = [0]
    completion["block_records"] = completion["block_records"][:1]
    completion["stream"]["output_lines"] = 1
    completion["stream"]["output_bytes"] = completion["block_records"][0]["bytes"]
    intent = values["training_predictions"]["native_intent"]
    request = runner._native_request(
        native_intent=intent,
        native_intent_sha256=completion["native_intent_sha256"],
        block_ordinals=[0], block_count=2,
    )
    completion["job_request_sha256"] = hashlib.sha256(
        runner._canonical_bytes(request)
    ).hexdigest()
    with pytest.raises(sh.LockMismatch, match="do not cover every K block"):
        runner._validate_k2_semantics(
            h=bundle["h"], schedule=bundle["schedule"],
            records=bundle["records"], values=values,
            _test_only_training_reference=(
                bundle["_test_only_training_reference"]
            ),
        )


def test_native_runtime_completion_snapshot_binds_generated_tree(tmp_path):
    runtime = tmp_path / "runtime"
    cache = runtime / "pytensor" / "compiled"
    cache.mkdir(parents=True)
    generated = cache / "model.so"
    generated.write_bytes(b"synthetic native image")
    generated.chmod(0o540)
    (runtime / "native-stderr.log").write_bytes(b"synthetic log\n")

    snapshot = runner._native_runtime_output_snapshot(runtime)
    assert snapshot == runner._validate_native_runtime_output_snapshot(snapshot)
    assert snapshot["file_count"] == 2
    assert snapshot["directory_count"] == 3
    assert snapshot["bytes"] == sum(
        entry["bytes"] for entry in snapshot["entries"]
    )
    generated_entry = next(
        entry for entry in snapshot["entries"]
        if entry["relative_path"] == "pytensor/compiled/model.so"
    )
    assert generated_entry["mode"] == 0o540
    assert generated_entry["sha256"] == hashlib.sha256(
        b"synthetic native image"
    ).hexdigest()

    generated.chmod(0o640)
    generated.write_bytes(b"different generated bytes")
    changed = runner._native_runtime_output_snapshot(runtime)
    assert changed["sha256"] != snapshot["sha256"]


@pytest.mark.parametrize(
    ("limit_name", "message"),
    (
        ("_NATIVE_RUNTIME_MAX_DIRECTORIES", "directory/entry quota"),
        ("_NATIVE_RUNTIME_MAX_ENTRIES", "entry quota"),
    ),
)
def test_native_runtime_completion_snapshot_caps_directories_and_entries(
    tmp_path, monkeypatch, limit_name, message,
):
    runtime = tmp_path / "runtime"; runtime.mkdir()
    (runtime / "a").mkdir()
    (runtime / "b").mkdir()
    monkeypatch.setattr(runner, limit_name, 2)
    with pytest.raises(runner.NativeWorkerIOFailure, match=message):
        runner._native_runtime_output_snapshot(runtime)


def test_native_runtime_snapshot_validator_caps_total_entries(
    tmp_path, monkeypatch,
):
    runtime = tmp_path / "runtime"; runtime.mkdir()
    (runtime / "a").write_bytes(b"a")
    (runtime / "b").write_bytes(b"b")
    snapshot = runner._native_runtime_output_snapshot(runtime)
    monkeypatch.setattr(runner, "_NATIVE_RUNTIME_MAX_ENTRIES", 2)
    with pytest.raises(sh.LockMismatch, match="identity is malformed"):
        runner._validate_native_runtime_output_snapshot(snapshot)


@pytest.mark.parametrize(
    "limits",
    (
        {"max_directories": 2, "max_entries": 10},
        {"max_directories": 10, "max_entries": 2},
    ),
)
def test_native_runtime_polling_caps_directories_and_entries(tmp_path, limits):
    runtime = tmp_path / "runtime"; runtime.mkdir()
    (runtime / "a").mkdir(); (runtime / "b").mkdir()
    with pytest.raises(runner.NativeWorkerIOFailure, match="quota exceeded"):
        runner._runtime_tree_usage(
            runtime, max_bytes=100, max_files=10, **limits,
        )


def test_native_runtime_polling_stops_consuming_at_entry_cap(
    tmp_path, monkeypatch,
):
    runtime = tmp_path / "runtime"; runtime.mkdir()
    for ordinal in range(8):
        (runtime / f"entry-{ordinal}").write_bytes(b"x")
    real_scandir = os.scandir
    pulls = 0

    class GuardedScandir:
        def __init__(self, path):
            self._iterator = real_scandir(path)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self._iterator.close()

        def __iter__(self):
            return self

        def __next__(self):
            nonlocal pulls
            pulls += 1
            if pulls > 2:
                raise AssertionError("scandir consumed past the fixed entry cap")
            return next(self._iterator)

    monkeypatch.setattr(runner.os, "scandir", GuardedScandir)
    with pytest.raises(
        runner.NativeWorkerIOFailure, match="entry quota exceeded",
    ):
        runner._runtime_tree_usage(
            runtime, max_bytes=100, max_files=10,
            max_directories=10, max_entries=2,
        )
    assert pulls == 2


@pytest.mark.parametrize("kind", ["symlink", "fifo"])
def test_native_runtime_completion_snapshot_rejects_nonregular_entries(
    tmp_path, kind,
):
    runtime = tmp_path / kind
    runtime.mkdir()
    target = runtime / "forbidden"
    if kind == "symlink":
        target.symlink_to(runtime)
        message = "symlink"
    else:
        os.mkfifo(target)
        message = "special file"
    with pytest.raises(runner.NativeWorkerIOFailure, match=message):
        runner._native_runtime_output_snapshot(runtime)


def test_native_runtime_completion_snapshot_rejects_hash_race(
    tmp_path, monkeypatch,
):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    generated = runtime / "generated.so"
    generated.write_bytes(b"before")
    real_hash = runner._native_runtime_file_sha256
    mutated = False

    def mutate_during_hash(descriptor):
        nonlocal mutated
        if not mutated:
            mutated = True
            generated.write_bytes(b"after")
        return real_hash(descriptor)

    monkeypatch.setattr(
        runner, "_native_runtime_file_sha256", mutate_during_hash,
    )
    with pytest.raises(
        runner.NativeWorkerIOFailure, match="changed while hashing",
    ):
        runner._native_runtime_output_snapshot(runtime)


@pytest.mark.parametrize(
    "mutation, message",
    [
        ("tree_digest", "tree digest differs"),
        ("file_digest", "file digest is malformed"),
        ("byte_count", "counts or bytes do not recompute"),
        ("path_escape", "path is not canonical"),
    ],
)
def test_native_completion_receipt_rejects_runtime_snapshot_tamper(
    tmp_path, mutation, message,
):
    bundle = _synthetic_k2_bundle(tmp_path)
    completion = _json_copy(
        bundle["values"]["training_predictions"]["native_completions"][0]
    )
    snapshot = completion["stream"]["runtime_tree_completion"]
    if mutation == "tree_digest":
        snapshot["sha256"] = "0" * 64
    elif mutation == "file_digest":
        file_entry = next(
            entry for entry in snapshot["entries"] if entry["kind"] == "file"
        )
        file_entry["sha256"] = "not-a-digest"
    elif mutation == "byte_count":
        snapshot["bytes"] += 1
    else:
        file_entry = next(
            entry for entry in snapshot["entries"] if entry["kind"] == "file"
        )
        file_entry["relative_path"] = "../escaped"
        snapshot["entries"].sort(key=lambda entry: entry["relative_path"])
    if mutation != "tree_digest":
        payload = {key: value for key, value in snapshot.items() if key != "sha256"}
        snapshot["sha256"] = hashlib.sha256(
            runner._canonical_bytes(payload)
        ).hexdigest()

    intent = bundle["values"]["training_predictions"]["native_intent"]
    with pytest.raises(sh.LockMismatch, match=message):
        runner._validate_native_completion_receipt(
            completion, native_intent=intent,
            native_intent_sha256=hashlib.sha256(
                runner._canonical_bytes(intent)
            ).hexdigest(),
            block_count=2,
            sandbox_contract=runner._native_sandbox_contract(),
        )


@pytest.mark.parametrize("mode", ["line_cap", "inactivity"])
def test_native_worker_stream_is_bounded_and_typed(mode, monkeypatch):
    monkeypatch.setattr(
        runner, "_native_process_group_rss_bytes", lambda process: 1,
    )
    source = (
        "import sys;sys.stdout.buffer.write(b'x'*64+b'\\n');sys.stdout.flush()"
        if mode == "line_cap" else "import time;time.sleep(1)"
    )
    process = subprocess.Popen(
        (sys.executable, "-c", source), stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=False, start_new_session=True,
    )
    try:
        with pytest.raises(runner.NativeWorkerIOFailure, match=(
            "line cap" if mode == "line_cap" else "inactivity deadline"
        )):
            list(runner._bounded_worker_lines(
                process, total_timeout_seconds=2,
                inactivity_timeout_seconds=0.05,
                max_line_bytes=16, max_output_bytes=128,
            ))
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def test_native_sandbox_unavailable_is_a_typed_stop(monkeypatch):
    contract = runner._native_sandbox_contract()
    monkeypatch.setattr(
        runner, "_NATIVE_SANDBOX_EXECUTABLE", Path("/missing/sandbox-exec"),
    )
    with pytest.raises(runner.NativeWorkerSandboxStop, match="unavailable"):
        runner._native_sandbox_command(
            contract={**contract, "sandbox_executable": "/missing/sandbox-exec"},
            profile="(version 1)\n(deny default)\n", source="pass",
        )


def test_native_sandbox_denies_repo_sentinel_and_network(tmp_path):
    if not runner._NATIVE_SANDBOX_EXECUTABLE.is_file():
        pytest.skip("sandbox-exec is not available on this platform")
    contract = runner._native_sandbox_contract()
    temporary = tmp_path / "sandbox"
    parent = temporary / "parent"; parent.mkdir(parents=True)
    request = temporary / "request.json"; request.write_text("{}\n")
    runtime = temporary / "runtime"; runtime.mkdir()
    environment = runner._native_minimal_environment(
        contract=contract, parent_root=parent,
        request_path=request, runtime_root=runtime,
    )
    profile = runner._native_sandbox_profile(
        contract=contract, temporary_root=temporary,
        parent_root=parent, request_path=request, runtime_root=runtime,
    )
    data_alias = Path("/System/Volumes/Data") / paths.REPO_ROOT.relative_to("/")
    system_library_escapes = (
        "/System/Library/User Template",
        "/System/Library/Frameworks/Ruby.framework/Versions/2.6/usr/lib/"
        "ruby/site_ruby",
        "/System/Library/Assistant/Plugins/Safari.assistantBundle",
        "/System/Library/Caches/com.apple.factorydata",
    )
    source = f'''import json, pathlib, socket, subprocess
results = []
for operation in (
    lambda: pathlib.Path({str(paths.REPO_ROOT / "pyproject.toml")!r}).read_bytes(),
    lambda: pathlib.Path({str(paths.REPO_ROOT / "pyproject.toml")!r}).stat(),
    lambda: pathlib.Path({str(data_alias / "pyproject.toml")!r}).read_bytes(),
    lambda: pathlib.Path({str(data_alias / "pyproject.toml")!r}).stat(),
    *(lambda path=path: pathlib.Path(path).stat()
      for path in {system_library_escapes!r}),
    lambda: pathlib.Path("/dev/urandom").open("rb").read(1),
    lambda: subprocess.run(["/usr/bin/curl", "--version"], check=False),
    lambda: socket.create_connection(("127.0.0.1", 9), timeout=0.1),
    lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM).bind(
        ("127.0.0.1", 0)
    ),
    lambda: socket.socket(socket.AF_INET6, socket.SOCK_STREAM).bind(("::1", 0)),
    lambda: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM).connect(
        "/var/run/syslog"
    ),
):
    try:
        operation()
    except PermissionError:
        results.append("denied")
    else:
        results.append("allowed")
print(json.dumps(results))
'''
    command = runner._native_sandbox_command(
        contract=contract, profile=profile, source=source,
    )
    result = subprocess.run(
        command, cwd=parent, env=environment, capture_output=True,
        check=False, timeout=30,
    )
    if (result.returncode
            and b"sandbox-exec:" in result.stderr
            and b"Operation not permitted" in result.stderr):
        pytest.skip("outer Codex sandbox refuses nested sandbox-exec")
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert json.loads(result.stdout) == [
        "denied", "denied", "denied", "denied",
        "denied", "denied", "denied", "denied",
        "denied", "denied", "denied", "denied", "denied", "denied",
    ]


def test_native_sandbox_contract_records_only_observed_startup_capabilities():
    contract = runner._native_sandbox_contract()
    assert "mach_lookup_services" not in contract
    assert contract["file_read_metadata"] == (
        "allowlisted_paths_and_ancestors"
    )
    assert contract["path_resolution_literals"] == ["/"]
    assert runner._NATIVE_SEALED_READ_ROOTS == ()
    assert all(
        not path.startswith(("/System/", "/usr/", "/bin", "/sbin"))
        for path in contract["runtime_read_paths"]
    )
    assert set(map(str, runner._NATIVE_SYSTEM_LOADABLES)).issubset(
        contract["process_exec_paths"]
    )
    assert any(
        path.endswith("/Resources/Python.app/Contents/MacOS/Python")
        for path in contract["process_exec_paths"]
    )
    profile = runner._native_sandbox_profile(
        contract=contract,
        temporary_root=Path("/private/tmp/probe"),
        parent_root=Path("/private/tmp/probe/parent"),
        request_path=Path("/private/tmp/probe/request.json"),
        runtime_root=Path("/private/tmp/probe/runtime"),
    )
    assert "(allow file-read-data" in profile
    assert "(allow file-read-metadata\n" in profile
    assert "(allow file-read-metadata)" not in profile
    assert "mach-lookup" not in profile


def test_fresh_native_sandbox_contract_passes_pure_receipt_validation():
    contract = runner._native_sandbox_contract()
    normalized = runner._validated_native_refusal_sandbox_contract(
        contract, label="fresh synthetic native sandbox contract",
    )
    assert normalized == contract
    assert runner._native_sandbox_contract_sha256(normalized) \
        == runner._native_sandbox_contract_sha256(contract)


def test_native_environment_uses_a_fixed_sandbox_home(tmp_path):
    contract = runner._native_sandbox_contract()
    runtime = tmp_path / "runtime"
    environment = runner._native_environment_values(
        contract=contract, parent_root=tmp_path / "parent",
        request_path=tmp_path / "request.json", runtime_root=runtime,
    )
    assert environment["HOME"] == str(runtime / "home")
    assert environment["HOME"] != os.environ.get("HOME")
    assert set(environment) == set(contract["environment_keys"])


@pytest.mark.parametrize(("failure", "expected", "pattern"), [
    ("missing", runner.RunnerNotReady, "fixed /usr/bin/git executable"),
    ("launch", runner.ResumableRunInterruption, "fixed git invocation failed"),
    ("timeout", runner.ResumableRunInterruption, "fixed git invocation failed"),
    ("nonzero", runner.ResumableRunInterruption, "git rev-parse HEAD failed"),
])
def test_git_bytes_operational_failures_are_nonpublishing(
    tmp_path, monkeypatch, failure, expected, pattern,
):
    executable = tmp_path / "git"
    if failure != "missing":
        executable.write_bytes(b"#!/bin/sh\nexit 0\n")
        executable.chmod(0o755)
    monkeypatch.setattr(runner, "_GIT_EXECUTABLE", executable)

    def run(*args, **kwargs):
        del args, kwargs
        if failure == "launch":
            raise OSError("synthetic Git launch interruption")
        if failure == "timeout":
            raise subprocess.TimeoutExpired("synthetic-git", 30)
        return SimpleNamespace(
            returncode=7, stdout=b"", stderr=b"synthetic Git refusal\n",
        )

    monkeypatch.setattr(runner.subprocess, "run", run)
    with pytest.raises(expected, match=pattern) as stopped:
        runner._git_bytes("rev-parse", "HEAD")
    assert isinstance(stopped.value, runner.NonPublishingRunStop)


@pytest.mark.parametrize(("arguments", "returncode", "expected"), [
    (("merge-base", "--is-ancestor", "a", "b"), 0, True),
    (("merge-base", "--is-ancestor", "a", "b"), 1, False),
])
def test_git_succeeds_accepts_only_exact_ancestor_boolean_exit(
    tmp_path, monkeypatch, arguments, returncode, expected,
):
    executable = tmp_path / "git"
    executable.write_bytes(b"#!/bin/sh\nexit 0\n"); executable.chmod(0o755)
    monkeypatch.setattr(runner, "_GIT_EXECUTABLE", executable)
    monkeypatch.setattr(
        runner.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=returncode, stderr=b"",
        ),
    )
    assert runner._git_succeeds(*arguments) is expected


@pytest.mark.parametrize(("arguments", "returncode"), [
    (("merge-base", "--is-ancestor", "a"), 1),
    (("merge-base", "--is-ancestor", "a", "b", "extra"), 1),
    (("rev-parse", "--verify", "a", "b"), 1),
    (("merge-base", "--is-ancestor", "a", "b"), 2),
])
def test_git_succeeds_treats_every_other_nonzero_as_interruption(
    tmp_path, monkeypatch, arguments, returncode,
):
    executable = tmp_path / "git"
    executable.write_bytes(b"#!/bin/sh\nexit 0\n"); executable.chmod(0o755)
    monkeypatch.setattr(runner, "_GIT_EXECUTABLE", executable)
    monkeypatch.setattr(
        runner.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=returncode, stderr=b"synthetic Git nonzero\n",
        ),
    )
    with pytest.raises(
        runner.ResumableRunInterruption, match="git .* failed",
    ) as stopped:
        runner._git_succeeds(*arguments)
    assert isinstance(stopped.value, runner.NonPublishingRunStop)


def test_fixed_git_environment_disables_replace_objects(tmp_path, monkeypatch):
    repository = tmp_path / "repo"; repository.mkdir()

    def git(*args, environment=None):
        result = subprocess.run(
            ("/usr/bin/git", "-C", str(repository), *args),
            capture_output=True, check=False, env=environment,
        )
        assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
        return result.stdout

    git("init", "-q")
    git("config", "user.name", "Synthetic Test")
    git("config", "user.email", "synthetic@example.invalid")
    value = repository / "value.txt"
    value.write_text("original\n"); git("add", "value.txt")
    git("commit", "-q", "-m", "original")
    original = git("rev-parse", "HEAD").decode("ascii").strip()
    value.write_text("replacement\n"); git("add", "value.txt")
    git("commit", "-q", "-m", "replacement")
    replacement = git("rev-parse", "HEAD").decode("ascii").strip()
    git("replace", original, replacement)
    assert git("show", f"{original}:value.txt") == b"replacement\n"
    fixed = runner._git_environment()
    assert fixed["GIT_NO_REPLACE_OBJECTS"] == "1"
    assert fixed["GIT_ATTR_NOSYSTEM"] == "1"
    assert git(
        "show", f"{original}:value.txt", environment=fixed,
    ) == b"original\n"
    sh._require_git_regular_blobs(
        repository, original, ("value.txt",), label="synthetic H",
    )
    monkeypatch.setattr(runner, "_ROOT", repository)
    runner._require_git_regular_blobs(
        original, ("value.txt",), label="synthetic K",
    )
    value.chmod(0o755); git("add", "value.txt")
    git("commit", "-q", "-m", "executable")
    executable = git("rev-parse", "HEAD").decode("ascii").strip()
    with pytest.raises(sh.LockMismatch, match="100644"):
        sh._require_git_regular_blobs(
            repository, executable, ("value.txt",), label="synthetic H",
        )
    with pytest.raises(sh.LockMismatch, match="100644"):
        runner._require_git_regular_blobs(
            executable, ("value.txt",), label="synthetic K",
        )


def test_native_sandbox_preflight_imports_and_compiles_the_native_stack(
    tmp_path,
):
    if not runner._NATIVE_SANDBOX_EXECUTABLE.is_file():
        pytest.skip("sandbox-exec is not available on this platform")
    temp_parent = tmp_path / "preflight"; temp_parent.mkdir()
    with runner._native_temporary_root_lease(temp_parent) as workspace:
        temporary = workspace.path
        parent = temporary / "parent"
        runner._materialize_native_parent(parent, workspace=workspace)
        request = temporary / "request.json"
        runner._create_native_immutable_child(
            workspace, request.name, b"{}\n", label="preflight request",
        )
        os.mkdir("runtime", 0o700, dir_fd=workspace.descriptor)
        runtime = temporary / "runtime"
        runner._capture_native_child_lease(
            workspace, "runtime", directory=True,
            label="preflight runtime",
        )
        contract = runner._native_sandbox_contract()
        environment = runner._native_minimal_environment(
            contract=contract, parent_root=parent,
            request_path=request, runtime_root=runtime,
        )
        profile = runner._native_sandbox_profile(
            contract=contract, temporary_root=temporary,
            parent_root=parent, request_path=request, runtime_root=runtime,
        )
        command = runner._native_sandbox_command(
            contract=contract, profile=profile, source="pass",
        )
        runtime_binding_lease = runner._capture_native_runtime_binding_lease(
            contract,
        )
        try:
            runner._native_sandbox_preflight(
                command=command, environment=environment, cwd=parent,
                runtime_contract=contract,
                runtime_binding_lease=runtime_binding_lease,
            )
        except runner.NativeWorkerSandboxStop as exc:
            message = str(exc)
            if "sandbox-exec:" in message and "Operation not permitted" in message:
                pytest.skip("outer Codex sandbox refuses nested sandbox-exec")
            monitor_refusal = any(fragment in message for fragment in (
                "resident-memory monitor could not run",
                "process-group ownership monitor could not run",
                "process-group ownership monitor failed",
            ))
            if monitor_refusal:
                try:
                    monitor = subprocess.run(
                        ("/bin/ps", "-axo", "pid=,pgid=,stat="),
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, timeout=10, check=False,
                    )
                except PermissionError:
                    pytest.skip(
                        "outer Codex sandbox refuses the process-group monitor"
                    )
                if monitor.returncode != 0:
                    pytest.skip(
                        "outer Codex sandbox refuses the process-group monitor"
                    )
            raise


def test_runtime_closure_hashes_bytes_and_rejects_mutation(tmp_path, monkeypatch):
    site = tmp_path / "site"; site.mkdir()
    runtime = tmp_path / "python-runtime"; runtime.mkdir()
    package = site / "package.py"; package.write_bytes(b"alpha")
    runtime_file = runtime / "Python"; runtime_file.write_bytes(b"runtime")
    tool = tmp_path / "tool"; tool.write_bytes(b"tool")
    tool.chmod(0o755)
    sdk = tmp_path / "SDK"; sdk.mkdir()
    (sdk / "SDKSettings.json").write_bytes(b"sdk")

    def tool_output(executable, *args):
        if executable == Path("/usr/bin/xcrun"):
            return str(sdk)
        if executable == Path("/sbin/mount"):
            return "/dev/synthetic on / (apfs, sealed, local, read-only)"
        return f"{executable.name} synthetic identity"

    monkeypatch.setattr(runner, "_fixed_tool_output", tool_output)
    first = _REAL_NATIVE_RUNTIME_CLOSURE(
        site_packages=site, python_runtime=runtime,
        runtime_read_paths=(), process_exec_paths=(str(tool),),
    )
    original_stat = package.stat()
    package.write_bytes(b"bravo")
    os.utime(package, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    second = _REAL_NATIVE_RUNTIME_CLOSURE(
        site_packages=site, python_runtime=runtime,
        runtime_read_paths=(), process_exec_paths=(str(tool),),
    )
    assert first["sha256"] != second["sha256"]
    assert first["file_count"] == second["file_count"]
    assert first["tree_digest_schema"] == runner._NATIVE_RUNTIME_TREE_SCHEMA


def test_runtime_closure_binds_modes_symlinks_and_declared_targets(
    tmp_path, monkeypatch,
):
    site = tmp_path / "site"; site.mkdir()
    runtime = tmp_path / "runtime"; runtime.mkdir()
    target = runtime / "target"; target.write_bytes(b"runtime")
    (site / "inside").symlink_to(target)
    tool = tmp_path / "tool"; tool.write_bytes(b"tool"); tool.chmod(0o755)
    sdk = tmp_path / "SDK"; sdk.mkdir()

    def tool_output(executable, *args):
        if executable == Path("/usr/bin/xcrun"):
            return str(sdk)
        if executable == Path("/sbin/mount"):
            return "/dev/synthetic on / (apfs, sealed, local, read-only)"
        return f"{executable.name} synthetic identity"

    monkeypatch.setattr(runner, "_fixed_tool_output", tool_output)
    first = _REAL_NATIVE_RUNTIME_CLOSURE(
        site_packages=site, python_runtime=runtime,
        runtime_read_paths=(), process_exec_paths=(str(tool),),
    )
    target.chmod(0o600)
    second = _REAL_NATIVE_RUNTIME_CLOSURE(
        site_packages=site, python_runtime=runtime,
        runtime_read_paths=(), process_exec_paths=(str(tool),),
    )
    assert first["sha256"] != second["sha256"]
    (site / "dangling").symlink_to("later")
    dangling = _REAL_NATIVE_RUNTIME_CLOSURE(
        site_packages=site, python_runtime=runtime,
        runtime_read_paths=(), process_exec_paths=(str(tool),),
    )
    (site / "later").write_bytes(b"later")
    resolved = _REAL_NATIVE_RUNTIME_CLOSURE(
        site_packages=site, python_runtime=runtime,
        runtime_read_paths=(), process_exec_paths=(str(tool),),
    )
    assert dangling["sha256"] != resolved["sha256"]
    assert dangling["symlink_count"] == resolved["symlink_count"] == 2
    escape = tmp_path / "escape"; escape.write_bytes(b"secret")
    (site / "outside").symlink_to(escape)
    with pytest.raises(
        runner.NativeWorkerSandboxStop, match="symlink escapes",
    ):
        _REAL_NATIVE_RUNTIME_CLOSURE(
            site_packages=site, python_runtime=runtime,
            runtime_read_paths=(), process_exec_paths=(str(tool),),
        )


def test_runtime_closure_rejects_directory_membership_race(
    tmp_path, monkeypatch,
):
    site = tmp_path / "site"; site.mkdir()
    runtime = tmp_path / "runtime"; runtime.mkdir()
    package = site / "package.py"; package.write_bytes(b"package")
    (runtime / "Python").write_bytes(b"runtime")
    tool = tmp_path / "tool"; tool.write_bytes(b"tool"); tool.chmod(0o755)
    sdk = tmp_path / "SDK"; sdk.mkdir()

    def tool_output(executable, *args):
        if executable == Path("/usr/bin/xcrun"):
            return str(sdk)
        if executable == Path("/sbin/mount"):
            return "/dev/synthetic on / (apfs, sealed, local, read-only)"
        return f"{executable.name} synthetic identity"

    original_sha256_file = sh.sha256_file
    mutated = False

    def mutate_during_hash(path):
        nonlocal mutated
        if Path(path) == package and not mutated:
            mutated = True
            (site / "late.py").write_bytes(b"late")
        return original_sha256_file(path)

    monkeypatch.setattr(runner, "_fixed_tool_output", tool_output)
    monkeypatch.setattr(sh, "sha256_file", mutate_during_hash)
    with pytest.raises(
        runner.NativeWorkerSandboxStop,
        match="runtime directory changed while hashing",
    ):
        _REAL_NATIVE_RUNTIME_CLOSURE(
            site_packages=site, python_runtime=runtime,
            runtime_read_paths=(), process_exec_paths=(str(tool),),
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("replace", "runtime symlink changed while hashing"),
        ("resolve", "runtime symlink resolution changed while hashing"),
    ),
)
def test_runtime_closure_rejects_symlink_race(
    tmp_path, monkeypatch, mutation, message,
):
    site = tmp_path / "site"; site.mkdir()
    runtime = tmp_path / "runtime"; runtime.mkdir()
    package = site / "package.py"; package.write_bytes(b"package")
    first = runtime / "first"
    second = runtime / "second"
    link = site / "link"
    if mutation == "replace":
        first.write_bytes(b"first")
        second.write_bytes(b"second")
        link.symlink_to(first)
    else:
        link.symlink_to(second)
    tool = tmp_path / "tool"; tool.write_bytes(b"tool"); tool.chmod(0o755)
    sdk = tmp_path / "SDK"; sdk.mkdir()

    def tool_output(executable, *args):
        if executable == Path("/usr/bin/xcrun"):
            return str(sdk)
        if executable == Path("/sbin/mount"):
            return "/dev/synthetic on / (apfs, sealed, local, read-only)"
        return f"{executable.name} synthetic identity"

    original_sha256_file = sh.sha256_file
    mutated = False

    def mutate_during_hash(path):
        nonlocal mutated
        if Path(path) == package and not mutated:
            mutated = True
            if mutation == "replace":
                link.unlink()
                link.symlink_to(second)
            else:
                second.write_bytes(b"resolved")
        return original_sha256_file(path)

    monkeypatch.setattr(runner, "_fixed_tool_output", tool_output)
    monkeypatch.setattr(sh, "sha256_file", mutate_during_hash)
    with pytest.raises(
        runner.NativeWorkerSandboxStop,
        match=message,
    ):
        _REAL_NATIVE_RUNTIME_CLOSURE(
            site_packages=site, python_runtime=runtime,
            runtime_read_paths=(), process_exec_paths=(str(tool),),
        )


def test_runtime_closure_revalidates_top_level_logical_root(
    tmp_path, monkeypatch,
):
    first = tmp_path / "site-a"; first.mkdir()
    second = tmp_path / "site-b"; second.mkdir()
    package = first / "package.py"; package.write_bytes(b"package")
    (second / "package.py").write_bytes(b"replacement")
    site = tmp_path / "site"; site.symlink_to(first, target_is_directory=True)
    runtime = tmp_path / "runtime"; runtime.mkdir()
    (runtime / "Python").write_bytes(b"runtime")
    tool = tmp_path / "tool"; tool.write_bytes(b"tool"); tool.chmod(0o755)
    sdk = tmp_path / "SDK"; sdk.mkdir()

    def tool_output(executable, *args):
        if executable == Path("/usr/bin/xcrun"):
            return str(sdk)
        if executable == Path("/sbin/mount"):
            return "/dev/synthetic on / (apfs, sealed, local, read-only)"
        return f"{executable.name} synthetic identity"

    original_sha256_file = sh.sha256_file
    mutated = False

    def mutate_during_hash(path):
        nonlocal mutated
        if Path(path) == package and not mutated:
            mutated = True
            site.unlink()
            site.symlink_to(second, target_is_directory=True)
        return original_sha256_file(path)

    monkeypatch.setattr(runner, "_fixed_tool_output", tool_output)
    monkeypatch.setattr(sh, "sha256_file", mutate_during_hash)
    with pytest.raises(
        runner.NativeWorkerSandboxStop, match="logical root changed after hashing",
    ):
        _REAL_NATIVE_RUNTIME_CLOSURE(
            site_packages=site, python_runtime=runtime,
            runtime_read_paths=(), process_exec_paths=(str(tool),),
        )


def test_runtime_closure_revalidates_top_level_executable(
    tmp_path, monkeypatch,
):
    site = tmp_path / "site"; site.mkdir()
    (site / "package.py").write_bytes(b"package")
    runtime = tmp_path / "runtime"; runtime.mkdir()
    (runtime / "Python").write_bytes(b"runtime")
    first = tmp_path / "tool-a"; first.write_bytes(b"tool-a"); first.chmod(0o755)
    second = tmp_path / "tool-b"; second.write_bytes(b"tool-b"); second.chmod(0o755)
    tool = tmp_path / "tool"; tool.symlink_to(first)
    sdk = tmp_path / "SDK"; sdk.mkdir()

    def tool_output(executable, *args):
        if executable == Path("/usr/bin/xcrun"):
            return str(sdk)
        if executable == Path("/sbin/mount"):
            return "/dev/synthetic on / (apfs, sealed, local, read-only)"
        return f"{executable.name} synthetic identity"

    original_sha256_file = sh.sha256_file
    mutated = False

    def mutate_during_hash(path):
        nonlocal mutated
        if Path(path) == first and not mutated:
            mutated = True
            tool.unlink(); tool.symlink_to(second)
        return original_sha256_file(path)

    monkeypatch.setattr(runner, "_fixed_tool_output", tool_output)
    monkeypatch.setattr(sh, "sha256_file", mutate_during_hash)
    with pytest.raises(
        runner.NativeWorkerSandboxStop, match="executable changed after hashing",
    ):
        _REAL_NATIVE_RUNTIME_CLOSURE(
            site_packages=site, python_runtime=runtime,
            runtime_read_paths=(), process_exec_paths=(str(tool),),
        )


def test_selected_native_developer_paths_are_fixed_and_disjoint(
    tmp_path, monkeypatch,
):
    developer = tmp_path / "developer"; developer.mkdir()
    inside = developer / "SDK"; inside.mkdir()
    outside = tmp_path / "outside"; outside.mkdir()
    monkeypatch.setattr(runner, "_NATIVE_DEVELOPER_ROOT", developer)
    assert runner._approved_native_developer_path(
        inside, label="synthetic SDK",
    ) == inside
    with pytest.raises(
        runner.NativeWorkerSandboxStop, match="escapes the approved developer root",
    ):
        runner._approved_native_developer_path(
            outside, label="synthetic SDK",
        )
    alias = developer / "escape"; alias.symlink_to(outside, target_is_directory=True)
    with pytest.raises(
        runner.NativeWorkerSandboxStop, match="escapes the approved developer root",
    ):
        runner._approved_native_developer_path(
            alias, label="synthetic SDK",
        )


def test_live_native_compiler_and_sdk_stay_under_approved_developer_root():
    contract = runner._native_sandbox_contract()
    developer = runner._NATIVE_DEVELOPER_ROOT.resolve(strict=True)
    selected = [
        *(Path(path) for path in contract["compiler_paths"].values()),
        Path(contract["sdk_root"]),
    ]
    for logical in selected:
        assert runner._path_beneath(logical.absolute(), developer)
        assert runner._path_beneath(logical.resolve(strict=True), developer)
    assert not runner._path_beneath(developer, runner._ROOT)
    assert not runner._path_beneath(developer, runner._ARTIFACT_ROOT)
    assert not runner._path_beneath(developer, runner._NATIVE_TEMP_PARENT)


def test_drifted_h_runtime_lock_stops_before_intent_preflight_or_popen(
    tmp_path, monkeypatch,
):
    frozen_contract = runner._native_sandbox_contract()
    live_contract = _json_copy(frozen_contract)
    live_closure = live_contract["runtime_closure"]
    live_closure["platform"]["kernel_release"] = "drifted-kernel"
    live_closure["sha256"] = hashlib.sha256(runner._canonical_bytes({
        key: value for key, value in live_closure.items() if key != "sha256"
    })).hexdigest()
    h = runner._VerifiedH(
        "a" * 40, "b" * 64, "c" * 64, "d" * 64,
        frozen_contract["runtime_closure"],
    )
    workspace = type("Workspace", (), {"path": tmp_path / "workspace"})()

    class WorkspaceContext:
        def __enter__(self):
            return workspace

        def __exit__(self, exc_type, exc, traceback):
            return False

    calls = {"intent": 0, "preflight": 0, "popen": 0}

    def sandbox_contract(*, frozen_runtime_lock=None):
        return _json_copy(
            frozen_contract if frozen_runtime_lock is not None else live_contract
        )

    monkeypatch.setattr(runner, "verify_harness_live", lambda commit: h)
    monkeypatch.setattr(
        runner, "_training_binding", lambda: (h.training_schedule_sha256, ()),
    )
    monkeypatch.setattr(runner, "_NATIVE_TEMP_PARENT", tmp_path)
    monkeypatch.setattr(
        runner, "_native_temporary_root_lease",
        lambda parent: WorkspaceContext(),
    )
    monkeypatch.setattr(
        runner, "_materialize_native_parent",
        lambda *args, **kwargs: ((), object()),
    )
    monkeypatch.setattr(
        runner, "_install_native_raw_inputs", lambda *args, **kwargs: (),
    )
    monkeypatch.setattr(
        runner, "_native_runtime_output_snapshot", lambda root: {},
    )
    monkeypatch.setattr(runner, "_verify_native_child_lease", lambda *args: None)
    monkeypatch.setattr(runner, "_native_sandbox_contract", sandbox_contract)
    monkeypatch.setattr(
        runner, "_native_intent",
        lambda **kwargs: calls.__setitem__("intent", calls["intent"] + 1),
    )
    monkeypatch.setattr(
        runner, "_native_sandbox_preflight",
        lambda **kwargs: calls.__setitem__(
            "preflight", calls["preflight"] + 1,
        ),
    )
    monkeypatch.setattr(
        runner.subprocess, "Popen",
        lambda *args, **kwargs: calls.__setitem__("popen", calls["popen"] + 1),
    )

    with pytest.raises(
        runner.NativeWorkerSandboxStop, match="differs before native work",
    ):
        runner._run_native_training_blocks_after_h(h_commit=h.commit)
    assert calls == {"intent": 0, "preflight": 0, "popen": 0}


def test_fast_runtime_binding_drift_stops_preflight_before_popen(
    tmp_path, monkeypatch,
):
    contract = _json_copy(runner._native_sandbox_contract())
    first = tmp_path / "tool-a"; first.write_bytes(b"a"); first.chmod(0o755)
    second = tmp_path / "tool-b"; second.write_bytes(b"b"); second.chmod(0o755)
    logical = tmp_path / "tool"; logical.symlink_to(first)
    contract["process_exec_paths"].append(str(logical))
    monkeypatch.setattr(
        runner, "_native_sandbox_contract", lambda: _json_copy(contract),
    )
    lease = runner._capture_native_runtime_binding_lease(contract)
    logical.unlink(); logical.symlink_to(second)
    runtime = tmp_path / "runtime"; runtime.mkdir()
    called = False

    def popen(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("Popen must not be reached after binding drift")

    monkeypatch.setattr(runner.subprocess, "Popen", popen)
    with pytest.raises(
        runner.NativeWorkerSandboxStop, match="binding changed before launch",
    ):
        runner._native_sandbox_preflight(
            command=("ignored",),
            environment={"EPL_SHOTS_RUNTIME_ROOT": str(runtime)},
            cwd=tmp_path, runtime_contract=contract,
            runtime_binding_lease=lease,
        )
    assert called is False


def test_runtime_binding_capture_rejects_contract_swap_after_full_scan(
    monkeypatch,
):
    contract = _json_copy(runner._native_sandbox_contract())
    drifted = _json_copy(contract)
    drifted["runtime_closure"]["platform"]["kernel_release"] = (
        "synthetic-post-scan-swap"
    )
    payload = {
        key: value for key, value in drifted["runtime_closure"].items()
        if key != "sha256"
    }
    drifted["runtime_closure"]["sha256"] = hashlib.sha256(
        runner._canonical_bytes(payload)
    ).hexdigest()
    lease = (("/synthetic/tool", ("binding",)),)
    monkeypatch.setattr(
        runner, "_raw_native_runtime_binding_lease",
        lambda supplied: lease,
    )
    monkeypatch.setattr(
        runner, "_native_sandbox_contract", lambda: _json_copy(drifted),
    )

    with pytest.raises(
        runner.NativeWorkerSandboxStop,
        match="closure changed while binding its scan",
    ):
        runner._capture_native_runtime_binding_lease(contract)


def test_runtime_binding_capture_rejects_path_swap_during_confirmation(
    monkeypatch,
):
    contract = _json_copy(runner._native_sandbox_contract())
    leases = iter((
        (("/synthetic/tool", ("before",)),),
        (("/synthetic/tool", ("after",)),),
    ))
    monkeypatch.setattr(
        runner, "_raw_native_runtime_binding_lease",
        lambda supplied: next(leases),
    )
    monkeypatch.setattr(
        runner, "_native_sandbox_contract", lambda: _json_copy(contract),
    )

    with pytest.raises(
        runner.NativeWorkerSandboxStop,
        match="binding changed during confirmation",
    ):
        runner._capture_native_runtime_binding_lease(contract)


def test_k2_rejects_runtime_closure_change_between_resume_jobs(
    tmp_path, monkeypatch,
):
    bundle = _synthetic_k2_bundle(tmp_path)
    changed = _json_copy(runner._native_sandbox_contract()["runtime_closure"])
    changed["sha256"] = "8" * 64
    monkeypatch.setattr(
        runner, "_native_runtime_closure", lambda **kwargs: _json_copy(changed),
    )
    with pytest.raises(sh.LockMismatch, match="runtime"):
        runner._validate_k2_semantics(
            h=bundle["h"], schedule=bundle["schedule"],
            records=bundle["records"], values=bundle["values"],
            _test_only_training_reference=(
                bundle["_test_only_training_reference"]
            ),
        )


def test_native_coordinator_never_yields_with_a_live_child():
    assert not inspect.isgeneratorfunction(
        runner._run_native_training_blocks_after_h,
    )
    assert not hasattr(runner, "_iter_native_training_blocks_after_h")


def test_native_workspace_stable_lease_is_retained_for_deferred_cleanup(tmp_path):
    temp_parent = tmp_path / "leased"; temp_parent.mkdir()
    with runner._native_temporary_root_lease(temp_parent) as workspace:
        created = workspace.path
        (created / "nested").mkdir()
        (created / "nested" / "generated.bin").write_bytes(b"generated")
    assert (created / "nested" / "generated.bin").read_bytes() == b"generated"
    assert temp_parent.is_dir()


def test_native_workspace_post_final_root_swap_never_deletes_either_tree(
    tmp_path, monkeypatch,
):
    temp_parent = tmp_path / "leased"; temp_parent.mkdir()
    real_verify = runner._verify_native_temporary_lease
    observed = {}
    with runner._native_temporary_root_lease(temp_parent) as workspace:
        (workspace.path / "owned.bin").write_bytes(b"parked owned bytes")

        def verify_then_swap(lease):
            real_verify(lease)
            parked = lease.path.with_name("parked-after-final-root-check")
            lease.path.rename(parked)
            lease.path.mkdir()
            replacement = lease.path / "replacement.bin"
            replacement.write_bytes(b"replacement bytes")
            observed.update(parked=parked, replacement=replacement)

        monkeypatch.setattr(
            runner, "_verify_native_temporary_lease", verify_then_swap,
        )

    assert (observed["parked"] / "owned.bin").read_bytes() == (
        b"parked owned bytes"
    )
    assert observed["replacement"].read_bytes() == b"replacement bytes"


def test_native_workspace_post_final_child_swap_never_deletes_either_tree(
    tmp_path, monkeypatch,
):
    temp_parent = tmp_path / "leased"; temp_parent.mkdir()
    real_verify_child = runner._verify_native_child_lease
    observed = {}
    with runner._native_temporary_root_lease(temp_parent) as workspace:
        parent = workspace.path / "parent"; parent.mkdir()
        (parent / "owned.bin").write_bytes(b"parked child bytes")
        parent_lease = runner._capture_native_child_lease(
            workspace, "parent", directory=True,
            label="parent/raw input root",
        )

        def verify_child_then_swap(lease, child):
            real_verify_child(lease, child)
            if child is parent_lease:
                parked = parent.with_name("parked-after-final-child-check")
                parent.rename(parked)
                parent.mkdir()
                replacement = parent / "replacement.bin"
                replacement.write_bytes(b"replacement child bytes")
                observed.update(parked=parked, replacement=replacement)

        monkeypatch.setattr(
            runner, "_verify_native_child_lease", verify_child_then_swap,
        )

    assert (observed["parked"] / "owned.bin").read_bytes() == (
        b"parked child bytes"
    )
    assert observed["replacement"].read_bytes() == b"replacement child bytes"


@pytest.mark.parametrize("target", ["temporary_root", "parent", "runtime"])
def test_native_workspace_one_way_replacement_is_preserved_for_reconciliation(
    tmp_path, target,
):
    temp_parent = tmp_path / "leased"; temp_parent.mkdir()
    replacement = orphan = None
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="another result was pending",
    ):
        with runner._native_temporary_root_lease(temp_parent) as workspace:
            parent = workspace.path / "parent"; parent.mkdir()
            (parent / "source.py").write_bytes(b"frozen parent\n")
            parent_lease = runner._capture_native_child_lease(
                workspace, "parent", directory=True,
                label="parent/raw input root",
            )
            parent_snapshot = runner._native_runtime_output_snapshot(parent)
            request_raw = b'{"request":"frozen"}\n'
            request = workspace.path / "native-request.json"
            request.write_bytes(request_raw)
            request_lease = runner._capture_native_child_lease(
                workspace, request.name, directory=False,
                label="native request",
            )
            runtime = workspace.path / "runtime"; runtime.mkdir()
            runtime_lease = runner._capture_native_child_lease(
                workspace, "runtime", directory=True,
                label="native runtime root",
            )
            runner._verify_native_workspace_lease(
                workspace, parent=parent_lease,
                parent_snapshot=parent_snapshot, request=request_lease,
                request_raw=request_raw, runtime=runtime_lease,
                verify_parent_tree=True,
            )

            selected = {
                "temporary_root": workspace.path,
                "parent": parent,
                "runtime": runtime,
            }[target]
            orphan = selected.with_name(f"orphan-{target}")
            selected.rename(orphan)
            selected.mkdir()
            replacement = selected / "replacement-sentinel"
            replacement.write_bytes(b"do not delete replacement\n")
            runner._verify_native_workspace_lease(
                workspace, parent=parent_lease,
                parent_snapshot=parent_snapshot, request=request_lease,
                request_raw=request_raw, runtime=runtime_lease,
                verify_parent_tree=True,
            )

    assert replacement is not None and replacement.read_bytes() == (
        b"do not delete replacement\n"
    )
    assert orphan is not None and orphan.exists()


def test_native_workspace_rechecks_parent_tree_and_request_exact_bytes(tmp_path):
    temp_parent = tmp_path / "leased"; temp_parent.mkdir()
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="another result was pending",
    ):
        with runner._native_temporary_root_lease(temp_parent) as workspace:
            parent = workspace.path / "parent"; parent.mkdir()
            source = parent / "source.py"; source.write_bytes(b"frozen parent\n")
            parent_lease = runner._capture_native_child_lease(
                workspace, "parent", directory=True,
                label="parent/raw input root",
            )
            parent_snapshot = runner._native_runtime_output_snapshot(parent)
            request_raw = b'{"request":"frozen"}\n'
            request = workspace.path / "native-request.json"
            request.write_bytes(request_raw)
            request_lease = runner._capture_native_child_lease(
                workspace, request.name, directory=False,
                label="native request",
            )
            runtime = workspace.path / "runtime"; runtime.mkdir()
            runtime_lease = runner._capture_native_child_lease(
                workspace, "runtime", directory=True,
                label="native runtime root",
            )
            source.write_bytes(b"mutated parent\n")
            runner._verify_native_workspace_lease(
                workspace, parent=parent_lease,
                parent_snapshot=parent_snapshot, request=request_lease,
                request_raw=request_raw, runtime=runtime_lease,
                verify_parent_tree=True,
            )

    # A separate lease proves in-place request mutation is independently bound.
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="another result was pending",
    ):
        with runner._native_temporary_root_lease(temp_parent) as workspace:
            parent = workspace.path / "parent"; parent.mkdir()
            (parent / "source.py").write_bytes(b"frozen parent\n")
            parent_lease = runner._capture_native_child_lease(
                workspace, "parent", directory=True,
                label="parent/raw input root",
            )
            parent_snapshot = runner._native_runtime_output_snapshot(parent)
            request_raw = b'{"request":"frozen"}\n'
            request = workspace.path / "native-request.json"
            request.write_bytes(request_raw)
            request_lease = runner._capture_native_child_lease(
                workspace, request.name, directory=False,
                label="native request",
            )
            runtime = workspace.path / "runtime"; runtime.mkdir()
            runtime_lease = runner._capture_native_child_lease(
                workspace, "runtime", directory=True,
                label="native runtime root",
            )
            request.write_bytes(b'{"request":"changed"}\n')
            runner._verify_native_workspace_lease(
                workspace, parent=parent_lease,
                parent_snapshot=parent_snapshot, request=request_lease,
                request_raw=request_raw, runtime=runtime_lease,
                verify_parent_tree=True,
            )


def test_native_request_create_after_root_swap_preserves_victim(
    tmp_path, monkeypatch,
):
    temp_parent = tmp_path / "leased"; temp_parent.mkdir()
    real_open = runner.os.open
    observed = {}
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="another result was pending",
    ):
        with runner._native_temporary_root_lease(temp_parent) as workspace:
            def swap_before_create(path, flags, *args, **kwargs):
                if path == "native-request.json" and flags & os.O_CREAT:
                    parked = temp_parent / "parked-request-root"
                    workspace.path.rename(parked)
                    workspace.path.mkdir()
                    victim = workspace.path / "native-request.json"
                    victim.write_bytes(b"pre-existing victim")
                    observed.update(parked=parked, victim=victim)
                return real_open(path, flags, *args, **kwargs)

            monkeypatch.setattr(runner.os, "open", swap_before_create)
            runner._create_native_immutable_child(
                workspace, "native-request.json", b"intended request\n",
                label="native request",
            )

    assert observed["victim"].read_bytes() == b"pre-existing victim"
    assert (observed["parked"] / "native-request.json").read_bytes() == (
        b"intended request\n"
    )


def test_native_stderr_create_after_runtime_swap_preserves_victim(
    tmp_path, monkeypatch,
):
    temp_parent = tmp_path / "leased"; temp_parent.mkdir()
    real_open = runner.os.open
    observed = {}
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="another result was pending",
    ):
        with runner._native_temporary_root_lease(temp_parent) as workspace:
            os.mkdir("runtime", 0o700, dir_fd=workspace.descriptor)
            runtime = workspace.path / "runtime"
            runtime_lease = runner._capture_native_child_lease(
                workspace, "runtime", directory=True,
                label="native runtime root",
            )

            def swap_before_create(path, flags, *args, **kwargs):
                if path == "native-stderr.log" and flags & os.O_CREAT:
                    parked = workspace.path / "parked-runtime"
                    runtime.rename(parked)
                    runtime.mkdir()
                    victim = runtime / "native-stderr.log"
                    victim.write_bytes(b"pre-existing stderr victim")
                    observed.update(parked=parked, victim=victim)
                return real_open(path, flags, *args, **kwargs)

            monkeypatch.setattr(runner.os, "open", swap_before_create)
            runner._create_native_mutable_nested_file(
                workspace, runtime_lease, "native-stderr.log",
                label="native worker stderr",
            )

    assert observed["victim"].read_bytes() == b"pre-existing stderr victim"
    assert (observed["parked"] / "native-stderr.log").read_bytes() == b""


def test_native_stderr_lease_keeps_exact_writer_and_reader_inode(tmp_path):
    temp_parent = tmp_path / "leased"; temp_parent.mkdir()
    with runner._native_temporary_root_lease(temp_parent) as workspace:
        os.mkdir("runtime", 0o700, dir_fd=workspace.descriptor)
        runtime_lease = runner._capture_native_child_lease(
            workspace, "runtime", directory=True,
            label="native runtime root",
        )
        stderr_lease = runner._create_native_mutable_nested_file(
            workspace, runtime_lease, "native-stderr.log",
            label="native worker stderr",
        )
        os.write(stderr_lease.writer_descriptor, b"exact stderr bytes\n")
        assert runner._native_nested_file_tail(
            workspace, stderr_lease,
        ) == "exact stderr bytes"
        assert os.fstat(stderr_lease.writer_descriptor).st_ino == os.fstat(
            stderr_lease.reader_descriptor,
        ).st_ino


@pytest.mark.parametrize("kind", ["request", "stderr"])
def test_native_exclusive_create_never_overwrites_an_existing_entry(
    tmp_path, kind,
):
    temp_parent = tmp_path / "leased"; temp_parent.mkdir()
    victim = None
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="another result was pending",
    ):
        with runner._native_temporary_root_lease(temp_parent) as workspace:
            if kind == "request":
                victim = workspace.path / "native-request.json"
                victim.write_bytes(b"existing request victim")
                runner._create_native_immutable_child(
                    workspace, victim.name, b"replacement request\n",
                    label="native request",
                )
            else:
                os.mkdir("runtime", 0o700, dir_fd=workspace.descriptor)
                runtime = workspace.path / "runtime"
                runtime_lease = runner._capture_native_child_lease(
                    workspace, "runtime", directory=True,
                    label="native runtime root",
                )
                victim = runtime / "native-stderr.log"
                victim.write_bytes(b"existing stderr victim")
                runner._create_native_mutable_nested_file(
                    workspace, runtime_lease, victim.name,
                    label="native worker stderr",
                )
    expected = (
        b"existing request victim" if kind == "request"
        else b"existing stderr victim"
    )
    assert victim is not None and victim.read_bytes() == expected


def _patch_synthetic_parent_archive_identity(monkeypatch):
    family = ("epl/synthetic_parent.py",)

    def git_text(*arguments):
        assert arguments[0] == "rev-parse"
        if arguments[1].endswith("^{commit}"):
            return runner._NATIVE_PARENT_COMMIT
        if arguments[1].endswith("^{tree}"):
            return runner._NATIVE_PARENT_TREE
        raise AssertionError(arguments)

    monkeypatch.setattr(runner, "_git_text", git_text)
    monkeypatch.setattr(runner, "_native_family_paths", lambda: family)
    return family


def _synthetic_tar_bytes(name, raw=b"synthetic parent bytes\n"):
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w") as archive:
        member = tarfile.TarInfo(name)
        member.size = len(raw)
        member.mode = 0o644
        archive.addfile(member, io.BytesIO(raw))
    return payload.getvalue()


@pytest.mark.parametrize("failure", [
    "git_launch", "git_timeout", "git_nonzero", "extraction_io",
])
def test_native_parent_git_and_extraction_io_are_nonpublishing(
    tmp_path, monkeypatch, failure,
):
    _patch_synthetic_parent_archive_identity(monkeypatch)

    def run(*args, **kwargs):
        del args
        if failure == "git_launch":
            raise OSError("synthetic archive launch interruption")
        if failure == "git_timeout":
            raise subprocess.TimeoutExpired("synthetic git archive", 60)
        if failure == "extraction_io":
            os.write(kwargs["stdout"], b"not a complete tar stream")
            return SimpleNamespace(returncode=0, stderr=b"")
        return SimpleNamespace(
            returncode=3, stderr=b"synthetic archive nonzero\n",
        )

    monkeypatch.setattr(runner.subprocess, "run", run)
    temp_parent = tmp_path / "leased"; temp_parent.mkdir()
    with pytest.raises(
        runner.NativeWorkerIOFailure,
        match=(
            "archive extraction did not complete"
            if failure == "extraction_io" else "git archive"
        ),
    ) as stopped:
        with runner._native_temporary_root_lease(temp_parent) as workspace:
            runner._materialize_native_parent(
                workspace.path / "parent", workspace=workspace,
            )
    assert isinstance(stopped.value, runner.NonPublishingRunStop)


def test_native_parent_git_failure_with_ambiguous_writer_close_is_manual(
    tmp_path, monkeypatch,
):
    _patch_synthetic_parent_archive_identity(monkeypatch)
    monkeypatch.setattr(
        runner.subprocess, "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError("synthetic archive launch interruption")
        ),
    )
    real_create = runner._create_native_direct_writer
    real_close = runner.os.close
    captured = {"descriptor": None, "failed": False}

    def capture_writer(*args, **kwargs):
        descriptor = real_create(*args, **kwargs)
        captured["descriptor"] = descriptor
        return descriptor

    def ambiguous_close(descriptor):
        if (descriptor == captured["descriptor"]
                and not captured["failed"]):
            captured["failed"] = True
            raise OSError("synthetic writer close ambiguity")
        return real_close(descriptor)

    monkeypatch.setattr(runner, "_create_native_direct_writer", capture_writer)
    monkeypatch.setattr(runner.os, "close", ambiguous_close)
    temp_parent = tmp_path / "leased"; temp_parent.mkdir()
    try:
        with pytest.raises(
            runner.ManualReconciliationRequired,
            match="archive writer did not close after Git failed",
        ):
            with runner._native_temporary_root_lease(temp_parent) as workspace:
                runner._materialize_native_parent(
                    workspace.path / "parent", workspace=workspace,
                )
    finally:
        monkeypatch.setattr(runner.os, "close", real_close)
        if captured["descriptor"] is not None:
            try:
                real_close(captured["descriptor"])
            except OSError:
                pass
    assert captured["failed"]


@pytest.mark.parametrize("mismatch", ["unsafe_member", "content"])
def test_native_parent_proven_archive_mismatch_is_lock_mismatch(
    tmp_path, monkeypatch, mismatch,
):
    family = _patch_synthetic_parent_archive_identity(monkeypatch)
    member_name = "../escape.py" if mismatch == "unsafe_member" else family[0]
    archive_raw = _synthetic_tar_bytes(member_name)

    def run(*args, **kwargs):
        del args
        written = os.write(kwargs["stdout"], archive_raw)
        assert written == len(archive_raw)
        return SimpleNamespace(returncode=0, stderr=b"")

    if mismatch == "content":
        monkeypatch.setattr(
            runner, "_verify_extracted_parent",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                sh.LockMismatch("synthetic extracted parent bytes differ")
            ),
        )
    monkeypatch.setattr(runner.subprocess, "run", run)
    temp_parent = tmp_path / "leased"; temp_parent.mkdir()
    with pytest.raises(sh.LockMismatch, match=(
        "unsafe path" if mismatch == "unsafe_member" else "bytes differ"
    )):
        with runner._native_temporary_root_lease(temp_parent) as workspace:
            runner._materialize_native_parent(
                workspace.path / "parent", workspace=workspace,
            )


def test_extracted_parent_real_verifier_detects_native_family_content_mismatch(
    tmp_path, monkeypatch,
):
    family = (
        "epl/fit.py", "epl/walkforward.py", "epl/synthetic_parent.py",
    )
    expected = {
        "epl/fit.py": b"synthetic fit bytes\n",
        "epl/walkforward.py": b"synthetic walkforward bytes\n",
        "epl/synthetic_parent.py": b"synthetic family member bytes\n",
    }
    root = tmp_path / "parent"
    for relative, raw in expected.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    digest = hashlib.sha256()
    for relative in family:
        name = relative.encode("utf-8")
        raw = expected[relative]
        digest.update(len(name).to_bytes(8, "big")); digest.update(name)
        digest.update(len(raw).to_bytes(8, "big")); digest.update(raw)
    monkeypatch.setattr(runner, "_NATIVE_ARCHIVE_RESOURCES", ())
    monkeypatch.setattr(
        runner, "_NATIVE_FIT_SHA256",
        hashlib.sha256(expected["epl/fit.py"]).hexdigest(),
    )
    monkeypatch.setattr(
        runner, "_NATIVE_WALKFORWARD_SHA256",
        hashlib.sha256(expected["epl/walkforward.py"]).hexdigest(),
    )
    monkeypatch.setattr(
        runner, "_NATIVE_CODE_FAMILY_SHA256", digest.hexdigest(),
    )
    (root / "epl/synthetic_parent.py").write_bytes(
        b"tampered synthetic family member bytes\n",
    )

    with pytest.raises(
        sh.LockMismatch, match="native-family digest differs",
    ):
        runner._verify_extracted_parent(root, family)


def test_native_parent_archive_replacement_is_never_unlinked(
    tmp_path, monkeypatch,
):
    temp_parent = tmp_path / "leased"; temp_parent.mkdir()
    real_run = runner.subprocess.run
    observed = {}
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="another result was pending",
    ):
        with runner._native_temporary_root_lease(temp_parent) as workspace:
            def run_then_replace(*args, **kwargs):
                result = real_run(*args, **kwargs)
                command = args[0]
                if "archive" in command and "--format=tar" in command:
                    archive = workspace.path / "native-parent.tar"
                    parked = workspace.path / "parked-native-parent.tar"
                    archive.rename(parked)
                    archive.write_bytes(b"pre-existing tar victim")
                    observed.update(parked=parked, victim=archive)
                return result

            monkeypatch.setattr(runner.subprocess, "run", run_then_replace)
            runner._materialize_native_parent(
                workspace.path / "parent", workspace=workspace,
            )

    assert observed["victim"].read_bytes() == b"pre-existing tar victim"
    assert observed["parked"].stat().st_size > 0


def test_native_parent_and_raw_inputs_materialize_through_leased_descriptors(
    tmp_path,
):
    temp_parent = tmp_path / "leased"; temp_parent.mkdir()
    with runner._native_temporary_root_lease(temp_parent) as workspace:
        parent = workspace.path / "parent"
        family, parent_lease = runner._materialize_native_parent(
            parent, workspace=workspace,
        )
        raw_inputs = runner._install_native_raw_inputs(
            parent, workspace=workspace, parent_lease=parent_lease,
        )
        assert len(family) == runner._NATIVE_CODE_FAMILY_FILES
        assert len(raw_inputs) == 5
        assert (workspace.path / "native-parent.tar").is_file()
        assert [record["path"] for record in raw_inputs] == [
            f"data/epl/raw/{name}" for name in runner._NATIVE_RAW_NAMES
        ]


def test_native_raw_destination_swap_preserves_preexisting_victim(
    tmp_path, monkeypatch,
):
    temp_parent = tmp_path / "leased"; temp_parent.mkdir()
    source_root = tmp_path / "source"
    source_raw = source_root / "data" / "epl" / "raw"
    source_raw.mkdir(parents=True)
    expected = {}
    for ordinal, name in enumerate(runner._NATIVE_RAW_NAMES):
        raw = f"synthetic raw {ordinal}\n".encode("ascii")
        (source_raw / name).write_bytes(raw)
        expected[name] = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(runner, "_ROOT", source_root)
    monkeypatch.setattr(runner, "_native_raw_digests", lambda: dict(expected))
    real_open = runner.os.open
    observed = {}
    first_name = runner._NATIVE_RAW_NAMES[0]
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="another result was pending",
    ):
        with runner._native_temporary_root_lease(temp_parent) as workspace:
            os.mkdir("parent", 0o700, dir_fd=workspace.descriptor)
            parent = workspace.path / "parent"
            parent_lease = runner._capture_native_child_lease(
                workspace, "parent", directory=True,
                label="parent/raw input root",
            )
            raw_root = parent / "data" / "epl" / "raw"

            def swap_before_create(path, flags, *args, **kwargs):
                if path == first_name and flags & os.O_CREAT:
                    parked = raw_root.with_name("parked-raw")
                    raw_root.rename(parked)
                    raw_root.mkdir()
                    victim = raw_root / first_name
                    victim.write_bytes(b"pre-existing raw victim")
                    observed.update(parked=parked, victim=victim)
                return real_open(path, flags, *args, **kwargs)

            monkeypatch.setattr(runner.os, "open", swap_before_create)
            runner._install_native_raw_inputs(
                parent, workspace=workspace, parent_lease=parent_lease,
            )

    assert observed["victim"].read_bytes() == b"pre-existing raw victim"
    assert (observed["parked"] / first_name).read_bytes() == (
        source_raw / first_name
    ).read_bytes()


def test_native_runtime_tree_quota_is_bounded_and_nproc_is_not_used(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(
        runner, "_native_process_group_rss_bytes", lambda process: 1,
    )
    runtime = tmp_path / "runtime"; runtime.mkdir()
    (runtime / "oversize").write_bytes(b"xx")
    process = subprocess.Popen(
        (sys.executable, "-c", "import time;time.sleep(1)"),
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=False, start_new_session=True,
    )
    try:
        with pytest.raises(
            runner.NativeWorkerIOFailure, match="runtime-tree quota",
        ):
            list(runner._bounded_worker_lines(
                process, total_timeout_seconds=2,
                inactivity_timeout_seconds=1,
                runtime_root=runtime, runtime_max_bytes=1,
                runtime_max_files=10,
            ))
    finally:
        if process.poll() is None:
            process.terminate(); process.wait(timeout=5)
    assert "nproc" not in runner._native_sandbox_contract()["resource_limits"]


def test_native_resource_contract_distinguishes_virtual_address_and_rss():
    limits = runner._native_sandbox_contract()["resource_limits"]
    assert limits["address_space_bytes"] is None
    assert limits["resident_memory_scope"] == "process_group_sampled_rss"
    assert limits["resident_memory_bytes"] == runner._NATIVE_RSS_LIMIT_BYTES
    assert limits["resident_memory_poll_seconds"] == runner._NATIVE_RSS_POLL_SECONDS
    assert limits["resident_memory_monitor"] == "/bin/ps"
    assert "memory_bytes" not in limits


def test_native_child_kernel_limits_do_not_set_address_space(monkeypatch):
    applied = []
    monkeypatch.setattr(
        runner.resource, "getrlimit",
        lambda key: (runner.resource.RLIM_INFINITY, runner.resource.RLIM_INFINITY),
    )
    monkeypatch.setattr(
        runner.resource, "setrlimit",
        lambda key, value: applied.append((key, value)),
    )
    runner._apply_native_resource_limits()
    assert applied
    assert all(key != runner.resource.RLIMIT_AS for key, _ in applied)
    assert {key for key, _ in applied} == {
        runner.resource.RLIMIT_CPU, runner.resource.RLIMIT_FSIZE,
        runner.resource.RLIMIT_NOFILE, runner.resource.RLIMIT_CORE,
    }


def test_native_process_group_rss_limit_is_fail_closed(monkeypatch):
    class Process:
        pid = 123

    observed = {"files": 0, "bytes": 0, "rss_bytes": 0}
    monkeypatch.setattr(
        runner, "_native_process_group_rss_bytes",
        lambda process: runner._NATIVE_RSS_LIMIT_BYTES + 1,
    )
    with pytest.raises(
        runner.NativeWorkerIOFailure, match="resident-memory limit exceeded",
    ):
        runner._observe_native_process_group_rss(
            Process(), limit_bytes=runner._NATIVE_RSS_LIMIT_BYTES,
            observed=observed,
        )
    assert observed["rss_bytes"] == runner._NATIVE_RSS_LIMIT_BYTES + 1


def test_native_process_group_rss_monitor_sums_only_group_members(monkeypatch):
    """Amendment 3 item 8: RSS comes from the one group-scoped snapshot."""
    class Process:
        pid = 123
        returncode = None

        @staticmethod
        def poll():
            return None

    class Completed:
        returncode = 0
        stdout = b" 123  123 Ss   10\n 200  123 R    20\n"
        stderr = b""

    calls = []
    monkeypatch.setattr(
        runner.subprocess, "run",
        lambda *args, **kwargs: calls.append((args, kwargs)) or Completed(),
    )
    assert runner._native_process_group_rss_bytes(Process()) == 30 * 1_024
    assert calls[0][0][0] == (
        "/bin/ps", "-o", "pid=,pgid=,stat=,rss=", "-g", "123",
    )
    assert calls[0][1]["timeout"] == 10
    assert len(calls) == 1


def test_native_process_group_normal_exit_is_observed_then_reaped_once(
    monkeypatch,
):
    events = []

    class Process:
        pid = 123
        returncode = None

        def poll(self):
            pytest.fail("poll would reap the process-group leader")

        def wait(self, *, timeout):
            assert timeout == 10
            assert events[-1] == ("state", True, ())
            events.append(("wait",))
            self.returncode = 0
            return 0

    process = Process()
    states = iter((
        runner._NativeProcessGroupState(123, 123, False, ()),
        runner._NativeProcessGroupState(123, 123, True, ()),
        runner._NativeProcessGroupState(123, 123, True, ()),
    ))

    def state(_process):
        assert _process is process and process.returncode is None
        value = next(states)
        events.append((
            "state", value.leader_exited, value.nonleader_pids,
        ))
        return value

    monkeypatch.setattr(runner, "_native_process_group_state", state)
    monkeypatch.setattr(
        runner, "_signal_native_process_group",
        lambda *args, **kwargs: pytest.fail("clean exit was signaled"),
    )
    monkeypatch.setattr(
        runner.time, "sleep", lambda seconds: events.append(("sleep", seconds)),
    )

    observed = {"rss_bytes": 0}
    runner._wait_native_process_with_rss_limit(
        process, timeout_seconds=5, poll_seconds=0.01, observed=observed,
    )
    assert runner._close_native_process_group(
        process, leader_must_have_exited=True,
    ) == (0, False)
    # ownership and RSS ride the same snapshot: no separate ("rss",) event
    assert events == [
        ("state", False, ()), ("sleep", 0.01),
        ("state", True, ()), ("state", True, ()), ("wait",),
    ]
    assert observed["rss_bytes"] == 0
    with pytest.raises(StopIteration):
        next(states)


def test_native_process_group_lingering_descendant_uses_term_then_kill_before_reap(
    monkeypatch,
):
    events = []

    class Process:
        pid = 123
        returncode = None

        def poll(self):
            pytest.fail("poll would reap the process-group leader")

        def wait(self, *, timeout):
            assert timeout == 10
            assert events[-1] == ("state", True, ())
            events.append(("wait",))
            self.returncode = -signal.SIGKILL
            return self.returncode

    process = Process()
    states = iter((
        runner._NativeProcessGroupState(123, 123, True, (222,)),
        runner._NativeProcessGroupState(123, 123, True, (222,)),
        runner._NativeProcessGroupState(123, 123, True, ()),
    ))

    def state(_process):
        assert _process is process and process.returncode is None
        value = next(states)
        events.append((
            "state", value.leader_exited, value.nonleader_pids,
        ))
        return value

    def signal_group(_process, group_state, requested_signal):
        assert _process is process and process.returncode is None
        assert isinstance(group_state, runner._NativeProcessGroupState)
        # A zombie leader is still present and anchors this PGID snapshot.
        assert group_state.leader_exited
        events.append(("signal", requested_signal))

    monotonic = iter((0.0, 3.0, 3.0))
    monkeypatch.setattr(runner, "_native_process_group_state", state)
    monkeypatch.setattr(runner, "_signal_native_process_group", signal_group)
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(monotonic))
    monkeypatch.setattr(
        runner.time, "sleep",
        lambda seconds: pytest.fail(f"unexpected group-close sleep {seconds}"),
    )

    assert runner._close_native_process_group(
        process, leader_must_have_exited=True,
    ) == (-signal.SIGKILL, True)
    assert events == [
        ("state", True, (222,)), ("signal", signal.SIGTERM),
        ("state", True, (222,)), ("signal", signal.SIGKILL),
        ("state", True, ()), ("wait",),
    ]


def test_interrupted_live_native_leader_is_terminated_before_one_final_reap(
    monkeypatch,
):
    events = []

    class Process:
        pid = 123
        returncode = None

        def poll(self):
            pytest.fail("poll would reap the interrupted leader")

        def wait(self, *, timeout):
            assert timeout == 10
            events.append(("wait",))
            self.returncode = -signal.SIGTERM
            return self.returncode

    process = Process()
    states = iter((
        runner._NativeProcessGroupState(123, 123, False, ()),
        runner._NativeProcessGroupState(123, 123, True, ()),
    ))

    def state(_process):
        assert _process is process and process.returncode is None
        value = next(states)
        events.append((
            "state", value.leader_exited, value.nonleader_pids,
        ))
        return value

    def signal_group(_process, group_state, requested_signal):
        assert _process is process and process.returncode is None
        assert group_state == runner._NativeProcessGroupState(
            123, 123, False, (),
        )
        events.append(("signal", requested_signal))

    monkeypatch.setattr(runner, "_native_process_group_state", state)
    monkeypatch.setattr(runner, "_signal_native_process_group", signal_group)
    monkeypatch.setattr(
        runner.time, "sleep",
        lambda seconds: pytest.fail(f"unexpected group-close sleep {seconds}"),
    )

    runner._terminate_native_process_group(process)
    assert events == [
        ("state", False, ()), ("signal", signal.SIGTERM),
        ("state", True, ()), ("wait",),
    ]


def test_native_process_group_signal_accepts_final_member_disappearance_race(
    monkeypatch,
):
    """A failed kill is harmless only after a fresh complete-closure proof."""
    events = []

    class Process:
        pid = 123
        returncode = None

        def wait(self, **kwargs):
            pytest.fail("signal-race validation reaped the leader")

    process = Process()
    before = runner._NativeProcessGroupState(123, 123, True, (222,))
    after = runner._NativeProcessGroupState(123, 123, True, ())

    def disappearing_killpg(process_group_id, requested_signal):
        events.append(("killpg", process_group_id, requested_signal))
        raise ProcessLookupError("synthetic final-member disappearance")

    def resnapshot(candidate):
        assert candidate is process and candidate.returncode is None
        events.append(("state", after))
        return after

    monkeypatch.setattr(runner.os, "killpg", disappearing_killpg)
    monkeypatch.setattr(runner, "_native_process_group_state", resnapshot)
    runner._signal_native_process_group(process, before, signal.SIGTERM)
    assert events == [
        ("killpg", 123, signal.SIGTERM), ("state", after),
    ]


def test_output_closed_with_live_native_leader_refuses_without_signal_or_reap(
    monkeypatch,
):
    class Process:
        pid = 123
        returncode = None

        def wait(self, **kwargs):
            pytest.fail("live leader was reaped")

    signals = []
    monkeypatch.setattr(
        runner, "_native_process_group_state",
        lambda process: runner._NativeProcessGroupState(
            123, 123, False, (),
        ),
    )
    monkeypatch.setattr(
        runner, "_signal_native_process_group",
        lambda *args: signals.append(args),
    )
    with pytest.raises(
        runner.NativeWorkerIOFailure,
        match="leader remained live after its output closed",
    ):
        runner._close_native_process_group(
            Process(), leader_must_have_exited=True,
        )
    assert signals == []


def test_native_process_group_state_parses_zombie_anchor_and_sorted_descendants(
    monkeypatch,
):
    class Process:
        pid = 123
        returncode = None

    completed = SimpleNamespace(
        returncode=0,
        # Amendment 3 item 8: the snapshot is group-scoped, so every row is
        # owned-group evidence and carries its own RSS reading.
        stdout=b"125 123 S    5\n123 123 Z+   0\n124 123 S    6\n",
        stderr=b"",
    )
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs: completed)
    assert runner._native_process_group_state(Process()) \
        == runner._NativeProcessGroupState(
            123, 123, True, (124, 125), (5 + 0 + 6) * 1_024,
        )


@pytest.mark.parametrize("group_state", [
    runner._NativeProcessGroupState(456, 456, True, ()),
    runner._NativeProcessGroupState(123, 456, True, ()),
])
def test_native_process_group_signal_rejects_cross_process_state(
    monkeypatch, group_state,
):
    class Process:
        pid = 123
        returncode = None

    monkeypatch.setattr(
        runner.os, "killpg",
        lambda *args: pytest.fail(f"cross-process state signaled {args}"),
    )
    with pytest.raises(
        runner.NativeWorkerIOFailure,
        match="process-group state is invalid",
    ):
        runner._signal_native_process_group(
            Process(), group_state, signal.SIGTERM,
        )


@pytest.mark.parametrize("stdout", [
    b"+123 123 Z\n",
    b"0123 123 Z\n",
    b"1_23 123 Z\n",
    b"123 123 ZOMBIE\n",
])
def test_native_process_group_state_rejects_noncanonical_ps_tokens(
    monkeypatch, stdout,
):
    class Process:
        pid = 123
        returncode = None

    completed = SimpleNamespace(returncode=0, stdout=stdout, stderr=b"")
    monkeypatch.setattr(
        runner.subprocess, "run", lambda *args, **kwargs: completed,
    )
    with pytest.raises(
        runner.NativeWorkerIOFailure, match="output is malformed",
    ):
        runner._native_process_group_state(Process())


@pytest.mark.parametrize(("field", "value"), [
    ("timeout_seconds", True),
    ("timeout_seconds", float("nan")),
    ("timeout_seconds", float("inf")),
    ("poll_seconds", False),
    ("poll_seconds", float("nan")),
    ("limit_bytes", True),
    ("limit_bytes", 0),
])
def test_native_process_group_wait_rejects_invalid_limits_before_monitoring(
    monkeypatch, field, value,
):
    class Process:
        pid = 123
        returncode = None

    arguments = {
        "timeout_seconds": 1.0,
        "poll_seconds": 0.05,
        "limit_bytes": 1,
    }
    arguments[field] = value
    monkeypatch.setattr(
        runner, "_native_process_group_state",
        lambda process: pytest.fail("invalid limits reached the monitor"),
    )
    with pytest.raises(
        runner.NativeWorkerIOFailure,
        match="resident-memory monitor timing is invalid",
    ):
        runner._wait_native_process_with_rss_limit(Process(), **arguments)


def test_native_worker_reprobes_group_monitor_immediately_before_launch():
    source = inspect.getsource(runner._run_native_training_blocks_after_h)
    launch = source.index("process = subprocess.Popen(")
    probe = source.rfind(
        "_require_native_process_group_monitor()", 0, launch,
    )
    final_binding_check = source.rfind(
        "_verify_native_runtime_binding_lease(", 0, launch,
    )
    assert final_binding_check < probe < launch


@pytest.mark.parametrize(("failure", "pattern"), [
    ("already_reaped", "reaped before process-group closure"),
    ("missing_leader", "lost the unreaped leader"),
    ("malformed", "output is malformed"),
    ("monitor_failed", "ownership monitor failed"),
])
def test_native_process_group_invalid_ownership_refuses_without_signal_or_wait(
    failure, pattern, monkeypatch,
):
    class Process:
        pid = 123
        returncode = 0 if failure == "already_reaped" else None

        def wait(self, **kwargs):
            pytest.fail("invalid group ownership was reaped")

    outputs = {
        "missing_leader": (0, b"124 123 S    5\n"),
        "malformed": (0, b"not-a-process-row\n"),
        "monitor_failed": (1, b"123 123 Ss   10\n"),
    }
    run_calls = []

    def monitor(*args, **kwargs):
        run_calls.append((args, kwargs))
        returncode, stdout = outputs[failure]
        return SimpleNamespace(
            returncode=returncode, stdout=stdout, stderr=b"",
        )

    signals = []
    monkeypatch.setattr(runner.subprocess, "run", monitor)
    monkeypatch.setattr(
        runner, "_signal_native_process_group",
        lambda *args: signals.append(args),
    )
    with pytest.raises(runner.NativeWorkerIOFailure, match=pattern):
        runner._close_native_process_group(
            Process(), leader_must_have_exited=False,
        )
    assert signals == []
    assert len(run_calls) == (0 if failure == "already_reaped" else 1)


def test_native_preflight_does_not_cleanup_group_after_final_reap(
    tmp_path, monkeypatch,
):
    runtime = tmp_path / "runtime"; runtime.mkdir()
    events = []

    class Process:
        returncode = None

    process = Process()
    monkeypatch.setattr(
        runner, "_verify_native_runtime_binding_lease",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        runner, "_require_native_process_group_monitor",
        lambda: events.append("monitor-ready"),
    )
    monkeypatch.setattr(
        runner.subprocess, "Popen",
        lambda *args, **kwargs: events.append("launch") or process,
    )
    monkeypatch.setattr(
        runner, "_wait_native_process_with_rss_limit",
        lambda *args, **kwargs: events.append("observe-zombie"),
    )

    def close_group(candidate, *, leader_must_have_exited):
        assert candidate is process and leader_must_have_exited
        events.append("final-reap")
        candidate.returncode = 0
        return 0, False

    monkeypatch.setattr(runner, "_close_native_process_group", close_group)
    monkeypatch.setattr(
        runner, "_terminate_native_process_group",
        lambda process: pytest.fail("preflight signaled after final reap"),
    )
    runner._native_sandbox_preflight(
        command=("sandbox", "placeholder"),
        environment={"EPL_SHOTS_RUNTIME_ROOT": str(runtime)},
        cwd=tmp_path, runtime_contract={}, runtime_binding_lease=(),
    )
    assert events == [
        "monitor-ready", "launch", "observe-zombie", "final-reap",
    ]


def test_k2_rejects_resident_memory_receipt_above_bound(tmp_path):
    bundle = _synthetic_k2_bundle(tmp_path)
    values = _json_copy(bundle["values"])
    completion = values["training_predictions"]["native_completions"][0]
    completion["stream"]["resident_memory_sampled_peak_bytes"] = (
        runner._NATIVE_RSS_LIMIT_BYTES + 1
    )
    with pytest.raises(sh.LockMismatch, match="stream limits differ"):
        runner._validate_k2_semantics(
            h=bundle["h"], schedule=bundle["schedule"],
            records=bundle["records"], values=values,
            _test_only_training_reference=(
                bundle["_test_only_training_reference"]
            ),
        )


# ==========================================================================
# 8. Safe PRE-H decision lifecycle foundations (synthetic control data only)
# ==========================================================================

def _synthetic_decision_schedule() -> tuple[dict[str, object], ...]:
    season_blocks = (
        ("2019/20", "2019-08-05", 35),
        ("2020/21", "2020-09-07", 34),
        ("2021/22", "2021-08-02", 36),
        ("2022/23", "2022-08-01", 34),
        ("2023/24", "2023-08-07", 37),
        ("2024/25", "2024-08-05", 36),
    )
    rows: list[dict[str, object]] = []
    for season, start, n_blocks in season_blocks:
        base, extra = divmod(380, n_blocks)
        for block_ordinal in range(n_blocks):
            date = pd.Timestamp(start) + pd.Timedelta(days=7 * block_ordinal)
            iso = date.isocalendar()
            block = f"{season}|{iso.year}W{iso.week:02d}"
            for within_block in range(base + (block_ordinal < extra)):
                ordinal = len(rows)
                rows.append({
                    "ordinal": ordinal,
                    "match_id": f"safe-decision-{ordinal:04d}",
                    "season": season,
                    "date": date.date().isoformat(),
                    "home_key": f"home-{within_block:02d}",
                    "away_key": f"away-{within_block:02d}",
                    "block": block,
                    "cutoff": date.date().isoformat(),
                })
    assert len(rows) == 2_280
    return tuple(rows)


def test_decision_schedule_block_validator_is_exact_and_value_blind():
    schedule = _synthetic_decision_schedule()
    blocks = runner._decision_schedule_blocks_exact(schedule)
    assert len(blocks) == 212
    assert sum(map(len, blocks)) == 2_280
    assert tuple(row["ordinal"] for block in blocks for row in block) == tuple(
        range(2_280)
    )

    duplicate = [dict(row) for row in schedule]
    duplicate[1]["match_id"] = duplicate[0]["match_id"]
    with pytest.raises(sh.FixtureSetMismatch, match="duplicated"):
        runner._decision_schedule_blocks_exact(duplicate)

    unsafe = [dict(row) for row in schedule]
    unsafe[0]["outcome"] = 0
    with pytest.raises(sh.LockMismatch, match="fields differ"):
        runner._decision_schedule_blocks_exact(unsafe)

    changed_label = [dict(row) for row in schedule]
    changed_label[0]["block"] = changed_label[1_000]["block"]
    with pytest.raises(sh.FixtureSetMismatch, match="ISO week"):
        runner._decision_schedule_blocks_exact(changed_label)

    only_211_blocks = [dict(row) for row in schedule]
    final_block = only_211_blocks[-1]["block"]
    prior = next(
        row for row in reversed(only_211_blocks)
        if row["block"] != final_block
    )
    for row in only_211_blocks:
        if row["block"] == final_block:
            row["date"] = prior["date"]
            row["cutoff"] = prior["cutoff"]
            row["block"] = prior["block"]
    with pytest.raises(sh.FixtureSetMismatch, match="exactly 212 blocks"):
        runner._decision_schedule_blocks_exact(only_211_blocks)


def test_decision_run_state_is_content_addressed_and_never_reauthorized(
    tmp_path,
):
    schedule_sha256 = runner._digest_rows(
        "epl-shots-decision-schedule-1", _synthetic_decision_schedule(),
    )
    h = runner._VerifiedH(
        "a" * 40, "b" * 64, "c" * 64, schedule_sha256,
    )
    k = runner._VerifiedK("d" * 40, "e" * 64, h)
    state, state_sha256 = runner._decision_run_state(
        h=h, k=k, decision_schedule_sha256=schedule_sha256,
    )
    forbidden = {
        "native", "candidate", "probabilities", "outcome", "y", "market",
        "score", "scores", "artifact", "artifacts",
    }
    assert not forbidden.intersection(state)
    assert state_sha256 == hashlib.sha256(
        runner._canonical_bytes(state)
    ).hexdigest()

    first = runner._reserve_decision_run_state(
        h=h, k=k, decision_schedule_sha256=schedule_sha256,
        state_root=tmp_path,
    )
    assert first.reservation_created
    assert first.state == state and first.state_sha256 == state_sha256
    with pytest.raises(TypeError):
        first.state["rows"] = 0
    with pytest.raises(TypeError):
        runner._decision_schedule_blocks_exact(
            _synthetic_decision_schedule()
        )[0][0]["match_id"] = "mutated"
    state_path = tmp_path / f"decision-run-{state_sha256}.json"
    assert state_path.read_bytes() == runner._canonical_bytes(state)

    repeated = runner._reserve_decision_run_state(
        h=h, k=k, decision_schedule_sha256=schedule_sha256,
        state_root=tmp_path,
    )
    assert not repeated.reservation_created
    assert repeated.state == state and repeated.state_sha256 == state_sha256

    different_k = runner._VerifiedK("f" * 40, "1" * 64, h)
    different, _ = runner._decision_run_state(
        h=h, k=different_k, decision_schedule_sha256=schedule_sha256,
    )
    with pytest.raises(sh.LockMismatch, match="run-lock bytes differ"):
        runner._reserve_decision_run_state(
            h=h, k=different_k, decision_schedule_sha256=schedule_sha256,
            state_root=tmp_path,
        )
    del different

    # The permanent lock is the non-replay tombstone.  Deleting the claim and
    # state must stop as ambiguous; it must never make `reservation_created`
    # true again.
    (tmp_path / ".decision-run.claim").unlink()
    state_path.unlink()
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="incomplete durable state",
    ):
        runner._reserve_decision_run_state(
            h=h, k=k, decision_schedule_sha256=schedule_sha256,
            state_root=tmp_path,
        )
    assert not (tmp_path / ".decision-run.claim").exists()
    assert not state_path.exists()


@pytest.mark.parametrize(("target", "message"), [
    ("claim", "decision-run reservation identity is ambiguous"),
    ("state", "decision run state verification is ambiguous"),
])
def test_decision_creation_retains_every_inode_through_final_scan(
    tmp_path, monkeypatch, target, message,
):
    schedule_sha256 = "6" * 64
    h = runner._VerifiedH("a" * 40, "b" * 64, "c" * 64, schedule_sha256)
    k = runner._VerifiedK("d" * 40, "e" * 64, h)
    state, state_sha256 = runner._decision_run_state(
        h=h, k=k, decision_schedule_sha256=schedule_sha256,
    )
    if target == "claim":
        visible = tmp_path / ".decision-run.claim"
        raw = (state_sha256 + "\n").encode("ascii")
    else:
        visible = tmp_path / f"decision-run-{state_sha256}.json"
        raw = runner._canonical_bytes(state)
    parked = tmp_path / f"held-{target}-original.tmp"
    replacement = tmp_path / f"held-{target}-replacement.tmp"
    replacement.write_bytes(raw); replacement.chmod(0o444)
    replacement_inode = replacement.stat().st_ino
    real_entries = runner._decision_run_state_entries_at
    scans = 0
    swapped = False

    def swap_during_final_scan(directory_fd):
        nonlocal scans, swapped
        scans += 1
        if scans == 2:
            visible.rename(parked)
            replacement.rename(visible)
            swapped = True
        return real_entries(directory_fd)

    monkeypatch.setattr(
        runner, "_decision_run_state_entries_at", swap_during_final_scan,
    )
    with pytest.raises(
        runner.ManualReconciliationRequired, match=message,
    ):
        runner._reserve_decision_run_state(
            h=h, k=k, decision_schedule_sha256=schedule_sha256,
            state_root=tmp_path,
        )

    assert swapped
    assert parked.stat().st_ino != replacement_inode
    assert visible.stat().st_ino == replacement_inode
    assert parked.read_bytes() == visible.read_bytes() == raw


@pytest.mark.parametrize("predating", ["claim", "state"])
def test_decision_run_state_refuses_artifact_predating_permanent_lock(
    tmp_path, predating,
):
    schedule_sha256 = "6" * 64
    h = runner._VerifiedH("a" * 40, "b" * 64, "c" * 64, schedule_sha256)
    k = runner._VerifiedK("d" * 40, "e" * 64, h)
    state, state_sha256 = runner._decision_run_state(
        h=h, k=k, decision_schedule_sha256=schedule_sha256,
    )

    if predating == "claim":
        assert runner._reserve_digest(tmp_path, "decision-run", state_sha256)
        pattern = "decision claim predates its permanent lock"
    else:
        tmp_path.mkdir(exist_ok=True)
        state_path = tmp_path / f"decision-run-{state_sha256}.json"
        state_path.write_bytes(runner._canonical_bytes(state))
        state_path.chmod(0o444)
        pattern = "decision state predates its permanent lock"

    with pytest.raises(
        runner.ManualReconciliationRequired, match=pattern,
    ):
        runner._reserve_decision_run_state(
            h=h, k=k, decision_schedule_sha256=schedule_sha256,
            state_root=tmp_path,
        )
    assert (tmp_path / ".decision-run.lock").exists()


@pytest.mark.parametrize(("missing", "filename"), [
    ("claim", ".decision-run.claim"),
    ("state", None),
])
def test_decision_run_state_missing_component_behind_lock_is_ambiguous(
    tmp_path, missing, filename,
):
    schedule_sha256 = "6" * 64
    h = runner._VerifiedH("a" * 40, "b" * 64, "c" * 64, schedule_sha256)
    k = runner._VerifiedK("d" * 40, "e" * 64, h)
    _, state_sha256 = runner._decision_run_state(
        h=h, k=k, decision_schedule_sha256=schedule_sha256,
    )
    runner._reserve_decision_run_state(
        h=h, k=k, decision_schedule_sha256=schedule_sha256,
        state_root=tmp_path,
    )
    target = tmp_path / (
        filename or f"decision-run-{state_sha256}.json"
    )
    target.unlink()

    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="permanent lock has incomplete durable state",
    ):
        runner._reserve_decision_run_state(
            h=h, k=k, decision_schedule_sha256=schedule_sha256,
            state_root=tmp_path,
        )
    assert (tmp_path / ".decision-run.lock").exists()
    assert not target.exists()


@pytest.mark.parametrize(("stage", "helper", "pattern"), [
    (
        "claim", "_reserve_digest_lease_at",
        "decision run claim write needs manual reconciliation",
    ),
    (
        "state", "_write_decision_state_lease_at",
        "decision run state write needs manual reconciliation",
    ),
])
def test_decision_run_state_creation_oserror_requires_manual_reconciliation(
    tmp_path, monkeypatch, stage, helper, pattern,
):
    schedule_sha256 = "6" * 64
    h = runner._VerifiedH("a" * 40, "b" * 64, "c" * 64, schedule_sha256)
    k = runner._VerifiedK("d" * 40, "e" * 64, h)
    _, state_sha256 = runner._decision_run_state(
        h=h, k=k, decision_schedule_sha256=schedule_sha256,
    )

    @contextlib.contextmanager
    def ambiguous_creation(*args, **kwargs):
        del args, kwargs
        raise OSError(f"synthetic {stage} creation interruption")
        yield  # pragma: no cover - contextmanager generator form

    monkeypatch.setattr(runner, helper, ambiguous_creation)
    with pytest.raises(runner.ManualReconciliationRequired, match=pattern):
        runner._reserve_decision_run_state(
            h=h, k=k, decision_schedule_sha256=schedule_sha256,
            state_root=tmp_path,
        )

    assert (tmp_path / ".decision-run.lock").exists()
    assert (tmp_path / ".decision-run.claim").exists() == (stage == "state")
    assert not (tmp_path / f"decision-run-{state_sha256}.json").exists()


def test_decision_run_state_exact_conflicting_claim_bytes_are_lock_mismatch(
    tmp_path,
):
    schedule_sha256 = "6" * 64
    h = runner._VerifiedH("a" * 40, "b" * 64, "c" * 64, schedule_sha256)
    k = runner._VerifiedK("d" * 40, "e" * 64, h)
    runner._reserve_decision_run_state(
        h=h, k=k, decision_schedule_sha256=schedule_sha256,
        state_root=tmp_path,
    )
    claim = tmp_path / ".decision-run.claim"
    claim.chmod(0o644)
    claim.write_bytes(("f" * 64 + "\n").encode("ascii"))
    claim.chmod(0o444)

    with pytest.raises(sh.LockMismatch, match="reservation bytes differ"):
        runner._reserve_decision_run_state(
            h=h, k=k, decision_schedule_sha256=schedule_sha256,
            state_root=tmp_path,
        )


def test_decision_run_state_refuses_tampered_state(tmp_path):
    schedule_sha256 = "6" * 64
    h = runner._VerifiedH("a" * 40, "b" * 64, "c" * 64, schedule_sha256)
    k = runner._VerifiedK("d" * 40, "e" * 64, h)
    _, state_sha256 = runner._decision_run_state(
        h=h, k=k, decision_schedule_sha256=schedule_sha256,
    )

    tampered = tmp_path / "tampered"
    runner._reserve_decision_run_state(
        h=h, k=k, decision_schedule_sha256=schedule_sha256,
        state_root=tampered,
    )
    path = tampered / f"decision-run-{state_sha256}.json"
    path.chmod(0o644)
    path.write_bytes(path.read_bytes() + b" ")
    path.chmod(0o444)
    with pytest.raises(sh.LockMismatch, match="canonical JSON object"):
        runner._decision_run_state_entries(state_root=tampered)


def test_decision_run_lock_refuses_created_inode_swap_after_fsync(
    tmp_path, monkeypatch,
):
    """The O_EXCL inode stays authoritative through lock verification."""
    state_sha256 = "6" * 64
    raw = (
        f"{runner._DECISION_RUN_LOCK_SCHEMA}\n{state_sha256}\n"
    ).encode("ascii")
    visible = tmp_path / ".decision-run.lock"
    parked = tmp_path / ".decision-run.lock.parked"
    real_fsync = os.fsync
    swapped = False

    def swapping_fsync(descriptor):
        nonlocal swapped
        result = real_fsync(descriptor)
        if not swapped and visible.exists():
            opened = os.fstat(descriptor)
            named = os.stat(visible, follow_symlinks=False)
            if ((opened.st_dev, opened.st_ino)
                    == (named.st_dev, named.st_ino)):
                # The old implementation closed this inode and reopened the
                # attacker-controlled identical replacement before flocking.
                visible.rename(parked)
                visible.write_bytes(raw)
                visible.chmod(0o444)
                swapped = True
        return result

    monkeypatch.setattr(runner.os, "fsync", swapping_fsync)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="decision run-lock identity is ambiguous",
    ):
        with runner._decision_run_lock(
            state_root=tmp_path, state_sha256=state_sha256,
        ):
            pytest.fail("a replaced lock pathname must never be yielded")

    assert swapped
    assert parked.read_bytes() == visible.read_bytes() == raw
    assert not (tmp_path / ".decision-run.claim").exists()
    assert not tuple(tmp_path.glob("decision-run-*.json"))


def test_native_run_lock_refuses_second_coordinator_and_inode_substitution(
    tmp_path, monkeypatch,
):
    """One held O_EXCL inode excludes a second coordinator through fsync."""
    native_intent_sha256 = "7" * 64
    raw = b"epl-shots-native-global-run-1\n"
    visible = tmp_path / ".native-run.lock"
    parked = tmp_path / ".native-run.lock.parked"
    real_fsync = os.fsync
    second_refused = False
    swapped = False

    def adversarial_fsync(descriptor):
        nonlocal second_refused, swapped
        result = real_fsync(descriptor)
        if not swapped and visible.exists():
            opened = os.fstat(descriptor)
            named = os.stat(visible, follow_symlinks=False)
            if ((opened.st_dev, opened.st_ino)
                    == (named.st_dev, named.st_ino)):
                with pytest.raises(
                    runner.RunnerNotReady, match="already running",
                ):
                    with runner._native_run_lock(
                        artifact_root=tmp_path,
                        native_intent_sha256=native_intent_sha256,
                    ):
                        pytest.fail("a second coordinator acquired the lock")
                second_refused = True
                visible.rename(parked)
                visible.write_bytes(raw)
                visible.chmod(0o444)
                swapped = True
        return result

    monkeypatch.setattr(runner.os, "fsync", adversarial_fsync)
    with pytest.raises(sh.LockMismatch, match="native run-lock"):
        with runner._native_run_lock(
            artifact_root=tmp_path,
            native_intent_sha256=native_intent_sha256,
        ):
            pytest.fail("a substituted native lock must never be yielded")

    assert second_refused and swapped
    assert parked.read_bytes() == visible.read_bytes() == raw
    assert stat.S_IMODE(parked.stat().st_mode) == 0o444
    assert stat.S_IMODE(visible.stat().st_mode) == 0o444


def test_native_run_lock_unlock_failure_is_manual_and_still_closes_fd(
    tmp_path, monkeypatch,
):
    native_intent_sha256 = "7" * 64
    real_flock = runner.fcntl.flock
    real_close = os.close
    lock_fd: int | None = None
    closed: set[int] = set()

    def fail_unlock(descriptor, operation):
        nonlocal lock_fd
        if operation & runner.fcntl.LOCK_EX:
            lock_fd = descriptor
        if operation == runner.fcntl.LOCK_UN and descriptor == lock_fd:
            raise OSError("synthetic unlock failure")
        return real_flock(descriptor, operation)

    def track_close(descriptor):
        closed.add(descriptor)
        return real_close(descriptor)

    monkeypatch.setattr(runner.fcntl, "flock", fail_unlock)
    monkeypatch.setattr(runner.os, "close", track_close)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="unlock/close state is ambiguous",
    ):
        with runner._native_run_lock(
            artifact_root=tmp_path,
            native_intent_sha256=native_intent_sha256,
        ):
            pass

    assert lock_fd is not None and lock_fd in closed


def test_native_run_locks_with_different_intent_hashes_serialize_globally(
    tmp_path,
):
    """The native run-lock namespace is global, not scoped per intent hash."""
    with runner._native_run_lock(
        artifact_root=tmp_path, native_intent_sha256="7" * 64,
    ):
        with pytest.raises(runner.RunnerNotReady, match="already running"):
            with runner._native_run_lock(
                artifact_root=tmp_path, native_intent_sha256="8" * 64,
            ):
                pytest.fail(
                    "a different native intent bypassed the global run lock"
                )
    assert (tmp_path / ".native-run.lock").read_bytes() \
        == b"epl-shots-native-global-run-1\n"


def test_native_run_lock_pre_name_io_failure_is_resumable(
    tmp_path, monkeypatch,
):
    real_open = runner.os.open

    def fail_root_open(path, flags, *args, **kwargs):
        if os.fspath(path) == "/" and "dir_fd" not in kwargs:
            raise OSError("synthetic pre-name state-root I/O failure")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(runner.os, "open", fail_root_open)
    with pytest.raises(
        runner.NativeWorkerIOFailure,
        match="decision state directory setup did not complete",
    ) as stopped:
        with runner._native_run_lock(
            artifact_root=tmp_path, native_intent_sha256="7" * 64,
        ):
            pytest.fail("pre-name I/O failure acquired native run-lock")
    assert isinstance(stopped.value, runner.ResumableRunInterruption)
    assert not (tmp_path / ".native-run.lock").exists()


@pytest.mark.parametrize("invalid", [None, b"7" * 64, 7])
def test_native_run_lock_rejects_non_string_identity(invalid, tmp_path):
    with pytest.raises(sh.LockMismatch, match="identity is malformed"):
        with runner._native_run_lock(
            artifact_root=tmp_path, native_intent_sha256=invalid,
        ):
            pytest.fail("non-string native run-lock identity was accepted")


@pytest.mark.parametrize(("failure", "pattern"), [
    ("open", "native run-lock durable state is ambiguous"),
    ("write", "native run-lock durable state is ambiguous"),
    ("file_fsync", "native run-lock durable state is ambiguous"),
    ("directory_fsync", "synthetic native lock directory fsync ambiguity"),
])
def test_native_run_lock_post_name_io_failure_requires_manual_reconciliation(
    failure, pattern, tmp_path, monkeypatch,
):
    real_open = runner.os.open
    real_write = runner.os.write
    real_fsync = runner.os.fsync

    def fail_lock_open(path, flags, *args, **kwargs):
        if path == ".native-run.lock":
            raise OSError("synthetic native lock open failure")
        return real_open(path, flags, *args, **kwargs)

    def fail_lock_write(descriptor, raw):
        if bytes(raw).startswith(b"epl-shots-native-global-run-1"):
            raise OSError("synthetic native lock write failure")
        return real_write(descriptor, raw)

    def fail_lock_fsync(descriptor):
        if stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError("synthetic native lock file fsync failure")
        return real_fsync(descriptor)

    monkeypatch.setattr(
        runner.os, "open",
        fail_lock_open if failure == "open" else real_open,
    )
    monkeypatch.setattr(
        runner.os, "write",
        fail_lock_write if failure == "write" else real_write,
    )
    monkeypatch.setattr(
        runner.os, "fsync",
        fail_lock_fsync if failure == "file_fsync" else real_fsync,
    )
    if failure == "directory_fsync":
        monkeypatch.setattr(
            runner, "_fsync_decision_state_directory",
            lambda descriptor: (_ for _ in ()).throw(
                runner.ManualReconciliationRequired(
                    "synthetic native lock directory fsync ambiguity"
                )
            ),
        )
    with pytest.raises(
        runner.ManualReconciliationRequired, match=pattern,
    ):
        with runner._native_run_lock(
            artifact_root=tmp_path,
            native_intent_sha256="7" * 64,
        ):
            pytest.fail("an incomplete native lock must not be yielded")


@pytest.mark.parametrize("cleanup", ["unlock", "close"])
def test_native_run_lock_cleanup_ambiguity_overrides_active_failure(
    tmp_path, monkeypatch, cleanup,
):
    real_flock = runner.fcntl.flock
    real_close = runner.os.close
    lock_descriptor = -1
    active = sh.FitFailure("synthetic active native operation")

    def ambiguous_flock(descriptor, operation):
        nonlocal lock_descriptor
        if operation & runner.fcntl.LOCK_EX:
            lock_descriptor = descriptor
        if cleanup == "unlock" and operation == runner.fcntl.LOCK_UN:
            raise OSError("synthetic native unlock ambiguity")
        return real_flock(descriptor, operation)

    def ambiguous_close(descriptor):
        if cleanup == "close" and descriptor == lock_descriptor:
            raise OSError("synthetic native close ambiguity")
        return real_close(descriptor)

    monkeypatch.setattr(runner.fcntl, "flock", ambiguous_flock)
    monkeypatch.setattr(runner.os, "close", ambiguous_close)
    try:
        with pytest.raises(
            runner.ManualReconciliationRequired,
            match="unlock/close state is ambiguous",
        ) as stopped:
            with runner._native_run_lock(
                artifact_root=tmp_path, native_intent_sha256="7" * 64,
            ):
                raise active
        assert stopped.value.__cause__ is active
    finally:
        monkeypatch.setattr(runner.os, "close", real_close)
        monkeypatch.setattr(runner.fcntl, "flock", real_flock)
        if cleanup == "close" and lock_descriptor >= 0:
            try:
                real_close(lock_descriptor)
            except OSError:
                pass


def test_durable_native_run_lock_preserves_body_oserror(tmp_path):
    active = OSError("synthetic native lock body I/O failure")
    with pytest.raises(OSError) as stopped:
        with runner._native_run_lock(
            artifact_root=tmp_path, native_intent_sha256="7" * 64,
        ):
            raise active
    assert stopped.value is active


@pytest.mark.parametrize(("raw", "expected", "pattern"), [
    (
        b"short\n", runner.ManualReconciliationRequired,
        "existing native run-lock may be incomplete",
    ),
    (
        b"x" * len(b"epl-shots-native-global-run-1\n"), sh.LockMismatch,
        "native run-lock bytes differ",
    ),
])
def test_existing_native_run_lock_distinguishes_short_from_proven_conflict(
    tmp_path, raw, expected, pattern,
):
    lock = tmp_path / ".native-run.lock"
    lock.write_bytes(raw)
    lock.chmod(0o444)
    with pytest.raises(expected, match=pattern):
        with runner._native_run_lock(
            artifact_root=tmp_path, native_intent_sha256="7" * 64,
        ):
            pytest.fail("invalid existing native run-lock was accepted")


def test_short_wrong_mode_native_run_lock_is_incomplete_manual_state(tmp_path):
    lock = tmp_path / ".native-run.lock"
    lock.write_bytes(b"short\n")
    lock.chmod(0o644)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="existing native run-lock may be incomplete",
    ):
        with runner._native_run_lock(
            artifact_root=tmp_path, native_intent_sha256="7" * 64,
        ):
            pytest.fail("short mutable native run-lock was accepted")


def test_native_run_lock_refuses_artifact_root_path_substitution(
    tmp_path, monkeypatch,
):
    logical = tmp_path / "artifact-root"
    parked = tmp_path / "opened-artifact-root"
    redirected = tmp_path / "redirected-artifact-root"
    logical.mkdir(); redirected.mkdir()
    real_open = os.open
    swapped = False

    def swapping_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if dir_fd is None:
            descriptor = real_open(path, flags, mode)
        else:
            descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if (not swapped and dir_fd is not None
                and os.fspath(path) == logical.name
                and flags & os.O_DIRECTORY):
            logical.rename(parked)
            logical.symlink_to(redirected, target_is_directory=True)
            swapped = True
        return descriptor

    monkeypatch.setattr(runner.os, "open", swapping_open)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="decision state exit is ambiguous",
    ):
        with runner._native_run_lock(
            artifact_root=logical, native_intent_sha256="7" * 64,
        ):
            pass

    assert swapped and logical.is_symlink()
    assert not tuple(redirected.iterdir())
    assert (parked / ".native-run.lock").read_bytes() == (
        b"epl-shots-native-global-run-1\n"
    )


def test_decision_state_dirfd_survives_ancestor_symlink_swap(
    tmp_path, monkeypatch,
):
    """A swap preserves descriptor writes but cannot report safe success."""
    schedule_sha256 = "6" * 64
    h = runner._VerifiedH("a" * 40, "b" * 64, "c" * 64, schedule_sha256)
    k = runner._VerifiedK("d" * 40, "e" * 64, h)
    logical = tmp_path / "state-root"
    parked = tmp_path / "opened-directory"
    redirected = tmp_path / "redirected-directory"
    logical.mkdir()
    redirected.mkdir()
    real_open = os.open
    swapped = False

    def swapping_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if dir_fd is None:
            descriptor = real_open(path, flags, mode)
        else:
            descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if (not swapped and dir_fd is not None
                and os.fspath(path) == logical.name
                and flags & os.O_DIRECTORY):
            # The secure walker already holds this directory descriptor.  Swap
            # the visible pathname immediately after that open, before any
            # lock, claim, or state write occurs.
            logical.rename(parked)
            logical.symlink_to(redirected, target_is_directory=True)
            swapped = True
        return descriptor

    monkeypatch.setattr(runner.os, "open", swapping_open)
    _, state_sha256 = runner._decision_run_state(
        h=h, k=k, decision_schedule_sha256=schedule_sha256,
    )
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="decision state exit is ambiguous",
    ):
        runner._reserve_decision_run_state(
            h=h, k=k, decision_schedule_sha256=schedule_sha256,
            state_root=logical,
        )
    assert swapped
    assert logical.is_symlink()
    assert not tuple(redirected.iterdir())
    assert {path.name for path in parked.iterdir()} == {
        ".decision-run.lock", ".decision-run.claim",
        f"decision-run-{state_sha256}.json",
    }

    # The swapped visible name is never accepted as a fresh namespace, while
    # restoring the descriptor-bound directory exposes its durable tombstones
    # and makes the second reservation an ordinary replay, not first use.
    with pytest.raises(
        runner.NativeWorkerIOFailure,
        match="decision state directory setup did not complete",
    ):
        runner._reserve_decision_run_state(
            h=h, k=k, decision_schedule_sha256=schedule_sha256,
            state_root=logical,
        )
    logical.unlink()
    parked.rename(logical)
    repeated = runner._reserve_decision_run_state(
        h=h, k=k, decision_schedule_sha256=schedule_sha256,
        state_root=logical,
    )
    assert not repeated.reservation_created
    assert repeated.state_sha256 == state_sha256

    # Residual trust boundary: destroying/replacing the *entire* visible state
    # namespace also destroys every local tombstone.  Only an external
    # immutable namespace or append-only ledger could distinguish that event
    # from genuine first use.
    externally_displaced = tmp_path / "externally-displaced-state-root"
    logical.rename(externally_displaced)
    logical.mkdir()
    after_external_destruction = runner._reserve_decision_run_state(
        h=h, k=k, decision_schedule_sha256=schedule_sha256,
        state_root=logical,
    )
    assert after_external_destruction.reservation_created


# ==========================================================================
# 9. Frozen post-K decision worker (synthetic values only)
# ==========================================================================

def _decision_test_h_k():
    h = runner._VerifiedH("a" * 40, "b" * 64, "c" * 64, "d" * 64)
    return h, runner._VerifiedK("e" * 40, "f" * 64, h)


def _small_prediction_and_scoring_rows():
    seasons = ("s1", "s2", "s3", "s4", "s5", "s6")
    native = np.asarray([[0.45, 0.30, 0.25]] * 6, dtype=np.float64)
    candidate = np.asarray([[0.50, 0.28, 0.22]] * 6, dtype=np.float64)
    market = np.asarray([[0.48, 0.29, 0.23]] * 6, dtype=np.float64)
    outcomes = np.asarray([0, 1, 2, 0, 1, 2], dtype=int)
    native_rps = sh._rps(native, outcomes)
    market_rps = sh._rps(market, outcomes)
    predictions = [{
        "match_id": f"m{ordinal}", "season": season,
        "block": f"{season}|w1", "native": native[ordinal].tolist(),
        "candidate": candidate[ordinal].tolist(),
    } for ordinal, season in enumerate(seasons)]
    scoring = [{
        "ordinal": ordinal, "match_id": f"m{ordinal}", "season": season,
        "block": f"{season}|w1", "y": int(outcomes[ordinal]),
        "market": market[ordinal].tolist(),
        "stored_native_rps": float(native_rps[ordinal]),
        "stored_market_rps": float(market_rps[ordinal]),
    } for ordinal, season in enumerate(seasons)]
    return predictions, scoring


def test_decision_projection_allowlists_forbid_outcomes_until_scoring(
    monkeypatch,
):
    raw = b"synthetic parquet snapshot"
    monkeypatch.setattr(runner, "_DECISION_ROWS", 2)
    monkeypatch.setattr(
        sh, "DECISION_CORPUS_SHA256", hashlib.sha256(raw).hexdigest(),
    )
    monkeypatch.setattr(
        runner, "_read_regular_snapshot", lambda *args, **kwargs: raw,
    )
    observed = []

    def projected(_source, *, columns):
        observed.append(tuple(columns))
        return pd.DataFrame([{name: 0 for name in columns}] * 2,
                            columns=columns)

    monkeypatch.setattr(runner.pd, "read_parquet", projected)
    runner._read_decision_projection(
        runner._PREDICTION_COLUMNS, phase="prediction",
    )
    assert observed == [runner._PREDICTION_COLUMNS]
    forbidden = {
        "y", "market_home", "market_draw", "market_away", "dc_rps",
        "market_rps", "fthg", "ftag", "played",
    }
    assert forbidden.isdisjoint(observed[0])
    with pytest.raises(sh.LockMismatch, match="columns differ"):
        runner._read_decision_projection(
            (*runner._PREDICTION_COLUMNS, "y"), phase="prediction",
        )


def test_scoring_projection_cannot_open_before_live_prediction_seal(
    monkeypatch,
):
    h, k = _decision_test_h_k()
    order = []
    seal_record = {"sha256": "1" * 64}

    def sealed(**kwargs):
        order.append("seal")
        return seal_record, {"schema": runner._PREDICTION_SEAL_SCHEMA}, []

    def opened(columns, *, phase, corpus_path=None):
        order.append("outcome_market")
        assert tuple(columns) == runner._SCORING_COLUMNS
        assert phase == "scoring"
        return pd.DataFrame()

    monkeypatch.setattr(runner, "_load_prediction_seal", sealed)
    monkeypatch.setattr(runner, "_read_decision_projection", opened)
    result = runner._read_scoring_projection_after_seal(
        h=h, k=k, schedule=(),
        scaler=sh.FeatureScaler((0, 0, 0, 0), (1, 1, 1, 1), 1520,
                                sh.TRAINING_SEASONS),
        beta=np.zeros(8), artifact_root=Path("/synthetic"),
    )
    assert result[0] == seal_record
    assert order == ["seal", "outcome_market"]


def test_prediction_access_is_exactly_once_and_ambiguous_resume_refuses(
    tmp_path,
):
    h, k = _decision_test_h_k()
    intent = runner._make_prediction_intent(
        h=h, k=k, moments_record={"sha256": "2" * 64},
        coefficients_record={"sha256": "3" * 64},
    )
    first = runner._begin_decision_access_once(
        intent_logical="decision_prediction_intent",
        receipt_logical="prediction_access_receipt", intent=intent,
        artifact_root=tmp_path,
        validate_intent=runner._validate_prediction_intent,
        validate_receipt=runner._validate_prediction_access_receipt,
    )
    assert first.may_open_source
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="source-access state is ambiguous",
    ):
        runner._begin_decision_access_once(
            intent_logical="decision_prediction_intent",
            receipt_logical="prediction_access_receipt", intent=intent,
            artifact_root=tmp_path,
            validate_intent=runner._validate_prediction_intent,
            validate_receipt=runner._validate_prediction_access_receipt,
        )
    receipt = runner._make_prediction_access_receipt(
        intent_record=first.intent_record, intent=first.intent,
        projection_sha256="4" * 64,
    )
    runner._record_decision_access_receipt(
        intent_logical="decision_prediction_intent",
        receipt_logical="prediction_access_receipt",
        intent_record=first.intent_record, intent=first.intent,
        receipt=receipt, artifact_root=tmp_path,
        validate_receipt=runner._validate_prediction_access_receipt,
    )
    resumed = runner._begin_decision_access_once(
        intent_logical="decision_prediction_intent",
        receipt_logical="prediction_access_receipt", intent=intent,
        artifact_root=tmp_path,
        validate_intent=runner._validate_prediction_intent,
        validate_receipt=runner._validate_prediction_access_receipt,
    )
    assert not resumed.may_open_source
    assert resumed.receipt == receipt


def test_all_212_prediction_blocks_are_outcome_and_market_free():
    h, k = _decision_test_h_k()
    schedule = _synthetic_decision_schedule()
    blocks = runner._decision_schedule_blocks_exact(schedule)
    intent_record = {"sha256": "1" * 64}
    access_record = {"sha256": "2" * 64}
    artifacts = []
    for ordinal, block in enumerate(blocks):
        rows = [{
            "ordinal": row["ordinal"], "match_id": row["match_id"],
            "native": [0.45, 0.30, 0.25],
            "candidate": [0.46, 0.29, 0.25],
        } for row in block]
        artifacts.append(runner._make_prediction_block(
            h=h, k=k, intent_record=intent_record,
            access_record=access_record, block_ordinal=ordinal,
            block=block, rows=rows,
        ))
    assert len(artifacts) == 212
    assert sum(len(item["rows"]) for item in artifacts) == 2_280
    forbidden = {"y", "outcome", "market", "dc_rps", "market_rps"}
    for artifact in artifacts:
        assert forbidden.isdisjoint(artifact)
        assert all(forbidden.isdisjoint(row) for row in artifact["rows"])


def test_decision_scoring_math_stored_parity_and_tamper_refusal():
    predictions, scoring = _small_prediction_and_scoring_rows()
    seal_record = {"sha256": "5" * 64}
    access_record = {"sha256": "6" * 64}
    projection_sha256 = runner._digest_rows(
        runner._DECISION_SCORING_PROJECTION_SCHEMA, scoring,
    )
    value = runner._decision_score_payload(
        prediction_rows=predictions, scoring_projection=scoring,
        prediction_seal_record=seal_record,
        scoring_access_record=access_record,
        scoring_projection_sha256=projection_sha256,
    )
    runner._validate_decision_scores(
        value, prediction_rows=predictions,
        prediction_seal_record=seal_record,
        scoring_access_record=access_record,
    )
    assert value["n_rows"] == 6
    assert all(abs(row["native_rps_parity_error"]) <= 1e-12
               for row in value["rows"])
    assert all(row["d_native"] == pytest.approx(
        row["candidate_rps"] - row["native_rps"]
    ) for row in value["rows"])

    altered_stored = _json_copy(scoring)
    altered_stored[0]["stored_native_rps"] += 1e-6
    with pytest.raises(sh.LockMismatch, match="stored corpus score"):
        runner._decision_score_payload(
            prediction_rows=predictions, scoring_projection=altered_stored,
            prediction_seal_record=seal_record,
            scoring_access_record=access_record,
            scoring_projection_sha256=projection_sha256,
        )
    tampered_projection = _json_copy(value)
    tampered_projection["scoring_projection_sha256"] = "7" * 64
    assert tampered_projection["scoring_projection_sha256"] \
        != projection_sha256
    with pytest.raises(
        sh.LockMismatch, match="projection digest does not recompute",
    ):
        runner._validate_decision_scores(
            tampered_projection, prediction_rows=predictions,
            prediction_seal_record=seal_record,
            scoring_access_record=access_record,
        )
    tampered = _json_copy(value)
    tampered["rows"][0]["d_native"] += 1e-5
    with pytest.raises(sh.LockMismatch, match="independently recompute"):
        runner._validate_decision_scores(
            tampered, prediction_rows=predictions,
            prediction_seal_record=seal_record,
            scoring_access_record=access_record,
        )


def test_frozen_bootstrap_gates_and_dispositions_are_literal():
    rows = []
    for season in ("s1", "s2", "s3", "s4", "s5", "s6"):
        for within in range(2):
            rows.append({
                "season": season, "block": f"{season}|w{within}",
                "d_native": -0.002, "d_market": -0.001,
                "candidate_log_loss": 0.9995, "native_log_loss": 1.0,
                "market_log_loss": 1.001,
                "native_rps_parity_error": 0.0,
                "market_rps_parity_error": 0.0,
            })
    value = {"rows": rows}
    estimates = runner._decision_estimates_from_scores(value)
    assert estimates["decision_gates"] == {
        "mean_d_native_lte_minus_0_001": True,
        "weekly_upper_native_lt_zero": True,
        "at_least_four_negative_seasons": True,
        "no_season_native_gt_0_002": True,
        "mean_log_loss_no_harm": True,
        "eligible": True,
    }
    assert estimates["disposition"].startswith("ELIGIBLE_")
    assert estimates["market_competitive"] is True
    assert estimates["week_ci_native"]["n_boot"] == 10_000
    assert estimates["week_ci_native"]["seed"] == 20260831
    assert estimates["season_ci_native"]["seed"] == 20260832

    research = _json_copy(value)
    for row in research["rows"]:
        if row["season"] == "s6":
            row["d_native"] = 0.003
    research_estimate = runner._decision_estimates_from_scores(research)
    assert research_estimate["mean_d_native"] < 0.0
    assert research_estimate["disposition"] == (
        "RESEARCH_SIGNAL_ONLY_DO_NOT_ADOPT"
    )
    rejected = _json_copy(value)
    for row in rejected["rows"]:
        row["d_native"] = 0.0
    assert runner._decision_estimates_from_scores(rejected)["disposition"] \
        == "REJECT"


def test_scoring_resume_uses_durable_scores_and_never_reopens_source(
    tmp_path, monkeypatch,
):
    h, k = _decision_test_h_k()
    predictions, scoring = _small_prediction_and_scoring_rows()
    seal_record = {"sha256": "8" * 64}
    projection_sha256 = runner._digest_rows(
        runner._DECISION_SCORING_PROJECTION_SCHEMA, scoring,
    )
    intent = runner._make_scoring_access_intent(
        h=h, k=k, prediction_seal_record=seal_record,
    )
    intent_record, created = runner._write_decision_artifact_once(
        "scoring_access_intent", intent, artifact_root=tmp_path,
    )
    assert created
    receipt = runner._make_scoring_access_receipt(
        intent_record=intent_record, intent=intent,
        projection_sha256=projection_sha256,
    )
    receipt_record, _ = runner._write_decision_artifact_once(
        "scoring_access_receipt", receipt, artifact_root=tmp_path,
    )
    scores = runner._decision_score_payload(
        prediction_rows=predictions, scoring_projection=scoring,
        prediction_seal_record=seal_record,
        scoring_access_record=receipt_record,
        scoring_projection_sha256=projection_sha256,
    )
    score_record, _ = runner._write_decision_artifact_once(
        "decision_scores", scores, artifact_root=tmp_path,
    )
    monkeypatch.setattr(
        runner, "_read_scoring_projection_after_seal",
        lambda **kwargs: pytest.fail("resume reopened outcomes/market"),
    )
    returned = runner._ensure_decision_scores(
        h=h, k=k, schedule=(),
        scaler=sh.FeatureScaler((0, 0, 0, 0), (1, 1, 1, 1), 1520,
                                sh.TRAINING_SEASONS),
        beta=np.zeros(8), prediction_seal_record=seal_record,
        prediction_rows=predictions, artifact_root=tmp_path,
    )
    assert returned[0] == intent_record
    assert returned[1] == receipt_record
    assert returned[2] == score_record


def test_scoring_intent_without_receipt_refuses_without_reopening(
    tmp_path, monkeypatch,
):
    h, k = _decision_test_h_k()
    predictions, _ = _small_prediction_and_scoring_rows()
    seal_record = {"sha256": "8" * 64}
    intent = runner._make_scoring_access_intent(
        h=h, k=k, prediction_seal_record=seal_record,
    )
    runner._write_decision_artifact_once(
        "scoring_access_intent", intent, artifact_root=tmp_path,
    )
    monkeypatch.setattr(
        runner, "_read_scoring_projection_after_seal",
        lambda **kwargs: pytest.fail("ambiguous resume reopened source"),
    )
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="scoring_access_intent exists without scoring_access_receipt",
    ):
        runner._ensure_decision_scores(
            h=h, k=k, schedule=(),
            scaler=sh.FeatureScaler((0, 0, 0, 0), (1, 1, 1, 1), 1520,
                                    sh.TRAINING_SEASONS),
            beta=np.zeros(8), prediction_seal_record=seal_record,
            prediction_rows=predictions, artifact_root=tmp_path,
        )


def test_refusal_result_publishes_explicit_na_and_supports_pre_k():
    h, k = _decision_test_h_k()
    refusal = sh.ProbabilityInvalid("synthetic market failure")
    value = runner._refusal_result(
        h=h, k=k, prediction_seal_record=None, completed_receipts=[],
        refusal=refusal, stage="scoring_access", counts={"rows": 0},
    )
    runner._validate_decision_result(
        value, h=h, k=k, prediction_seal_record=None,
    )
    expected = "N/A \u2014 not computed after ProbabilityInvalid"
    assert value["headline_rps"] == expected
    assert value["intervals"] == expected
    assert value["season_results"] == expected
    assert value["log_loss"] == expected
    pre_k = runner._refusal_result(
        h=h, k=None, prediction_seal_record=None, completed_receipts=[],
        refusal=refusal, stage="training", counts={"native_blocks": 1},
    )
    runner._validate_decision_result(
        pre_k, h=h, k=None, prediction_seal_record=None,
    )
    assert pre_k["coefficient_commit"] == (
        "N/A \u2014 K not created after ProbabilityInvalid"
    )
    tampered = _json_copy(value)
    tampered["headline_rps"] = 0.0
    with pytest.raises(sh.LockMismatch, match="N/A fields differ"):
        runner._validate_decision_result(
            tampered, h=h, k=k, prediction_seal_record=None,
        )


def test_decision_canary_receipt_is_content_bound(monkeypatch):
    h, k = _decision_test_h_k()
    del h, k
    predictions, scoring = _small_prediction_and_scoring_rows()
    seal_record = {"sha256": "5" * 64}
    access_record = {"sha256": "6" * 64}
    score_value = runner._decision_score_payload(
        prediction_rows=predictions, scoring_projection=scoring,
        prediction_seal_record=seal_record,
        scoring_access_record=access_record,
        scoring_projection_sha256="7" * 64,
    )
    score_record = {"sha256": hashlib.sha256(
        runner._canonical_bytes(score_value)
    ).hexdigest()}
    monkeypatch.setattr(runner, "_DECISION_ROWS", 6)
    monkeypatch.setattr(runner, "_DECISION_BLOCKS", 6)
    monkeypatch.setattr(
        runner, "_DECISION_SEASONS", ("s1", "s2", "s3", "s4", "s5", "s6"),
    )
    receipt = runner._make_decision_canary_receipt(
        prediction_seal_record=seal_record,
        scoring_access_record=access_record,
        prediction_rows=predictions, score_value=score_value,
    )
    runner._validate_decision_canary_receipt(
        receipt, prediction_seal_record=seal_record,
        scoring_access_record=access_record, score_record=score_record,
    )
    corrupted = _json_copy(receipt)
    corrupted["checks"]["odds_isolation"] = False
    with pytest.raises(sh.CanaryFailed):
        runner._validate_decision_canary_receipt(
            corrupted, prediction_seal_record=seal_record,
            scoring_access_record=access_record, score_record=score_record,
        )


def _synthetic_completed_closure_state(monkeypatch):
    """Build a six-row immutable closure without opening either source seam."""
    monkeypatch.setattr(runner, "_DECISION_ROWS", 6)
    monkeypatch.setattr(runner, "_DECISION_BLOCKS", 6)
    monkeypatch.setattr(
        runner, "_DECISION_SEASONS", ("s1", "s2", "s3", "s4", "s5", "s6"),
    )
    h, k = _decision_test_h_k()
    predictions, scoring = _small_prediction_and_scoring_rows()
    projection_sha256 = runner._digest_rows(
        runner._DECISION_SCORING_PROJECTION_SCHEMA, scoring,
    )
    scaler = sh.FeatureScaler(
        (0, 0, 0, 0), (1, 1, 1, 1), 1520, sh.TRAINING_SEASONS,
    )
    beta = np.zeros(8)
    moments_record = {"sha256": "1" * 64}
    coefficients_record = {"sha256": "2" * 64}

    prediction_intent = runner._make_prediction_intent(
        h=h, k=k, moments_record=moments_record,
        coefficients_record=coefficients_record,
    )
    prediction_intent_record = runner._decision_record(
        "decision_prediction_intent", prediction_intent,
    )
    access = {
        "schema": runner._PREDICTION_ACCESS_RECEIPT_SCHEMA,
        "synthetic": "outcome-free access receipt",
    }
    access_record = runner._decision_record(
        "prediction_access_receipt", access,
    )
    predictions_value = {
        "schema": runner._DECISION_PREDICTIONS_SCHEMA,
        "synthetic": "sealed predictions",
    }
    predictions_record = runner._decision_record(
        "decision_predictions", predictions_value,
    )
    seal = {
        "schema": runner._PREDICTION_SEAL_SCHEMA,
        "decision_predictions": predictions_record,
        "access_receipt": access_record,
    }
    seal_record = runner._decision_record("prediction_seal", seal)
    prediction_blocks = []
    for ordinal in range(6):
        block = {
            "schema": runner._DECISION_PREDICTION_BLOCK_SCHEMA,
            "synthetic_ordinal": ordinal,
        }
        prediction_blocks.append((runner._decision_record(
            "decision_prediction_block", block, ordinal=ordinal,
        ), block))

    scoring_intent = runner._make_scoring_access_intent(
        h=h, k=k, prediction_seal_record=seal_record,
    )
    scoring_intent_record = runner._decision_record(
        "scoring_access_intent", scoring_intent,
    )
    scoring_receipt = runner._make_scoring_access_receipt(
        intent_record=scoring_intent_record, intent=scoring_intent,
        projection_sha256=projection_sha256,
    )
    scoring_receipt_record = runner._decision_record(
        "scoring_access_receipt", scoring_receipt,
    )
    score_value = runner._decision_score_payload(
        prediction_rows=predictions, scoring_projection=scoring,
        prediction_seal_record=seal_record,
        scoring_access_record=scoring_receipt_record,
        scoring_projection_sha256=projection_sha256,
    )
    runner._validate_decision_scores(
        score_value, prediction_rows=predictions,
        prediction_seal_record=seal_record,
        scoring_access_record=scoring_receipt_record,
    )
    score_record = runner._decision_record("decision_scores", score_value)
    canary = runner._make_decision_canary_receipt(
        prediction_seal_record=seal_record,
        scoring_access_record=scoring_receipt_record,
        prediction_rows=predictions, score_value=score_value,
    )
    canary_record = runner._decision_record(
        "decision_canary_receipt", canary,
    )
    completed_receipts = [
        seal_record, scoring_intent_record, scoring_receipt_record,
        score_record, canary_record,
    ]
    exclusions = {
        "scoring_fixtures_excluded": 0,
        "raw_shot_rows_quarantined": 1,
        "prediction_rows": 6, "scoring_rows": 6,
    }
    result = {
        "schema": runner._DECISION_RESULT_SCHEMA,
        "status": "COMPLETED",
        "completed_receipts": _json_copy(completed_receipts),
        "exclusions": dict(exclusions),
    }
    result_record = runner._decision_record("decision_result", result)
    singletons = {
        "decision_prediction_intent": (
            (prediction_intent_record, prediction_intent),
        ),
        "decision_predictions": ((predictions_record, predictions_value),),
        "prediction_access_receipt": ((access_record, access),),
        "scoring_access_intent": ((scoring_intent_record, scoring_intent),),
        "scoring_access_receipt": (
            (scoring_receipt_record, scoring_receipt),
        ),
        "decision_scores": ((score_record, score_value),),
        "decision_canary_receipt": ((canary_record, canary),),
    }

    monkeypatch.setattr(
        runner, "decision_schedule_binding",
        lambda: (h.decision_schedule_sha256, ()),
    )
    monkeypatch.setattr(
        runner, "_load_decision_model",
        lambda _k: (scaler, beta, moments_record, coefficients_record),
    )
    monkeypatch.setattr(
        runner, "_decision_singletons",
        lambda logical, **kwargs: singletons.get(logical, ()),
    )
    monkeypatch.setattr(
        runner, "_require_decision_record_claim",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        runner, "_load_prediction_seal",
        lambda **kwargs: (seal_record, seal, predictions),
    )
    monkeypatch.setattr(
        runner, "_discover_prediction_blocks",
        lambda **kwargs: tuple(prediction_blocks),
    )
    monkeypatch.setattr(
        runner, "_read_scoring_projection_after_seal",
        lambda **kwargs: pytest.fail("completed replay reopened scoring source"),
    )
    monkeypatch.setattr(
        runner, "_decision_inventory",
        lambda **kwargs: pytest.fail("target rejection did not fail closed"),
    )
    return {
        "h": h, "k": k, "result": result,
        "result_record": result_record, "singletons": singletons,
        "prediction_blocks": prediction_blocks,
        "seal_record": seal_record,
        "scoring_receipt_record": scoring_receipt_record,
        "score_record": score_record,
    }


@pytest.mark.parametrize("missing", [
    "scoring_access_intent", "scoring_access_receipt",
    "decision_canary_receipt",
])
def test_completed_closure_requires_scoring_and_canary_singletons(
    missing, tmp_path, monkeypatch,
):
    state = _synthetic_completed_closure_state(monkeypatch)
    state["singletons"][missing] = ()
    with pytest.raises(
        sh.LockMismatch,
        match=rf"completed decision closure requires one {missing}",
    ):
        runner._validate_existing_completed_closure(
            h=state["h"], k=state["k"],
            result_record=state["result_record"], result=state["result"],
            artifact_root=tmp_path,
        )


def test_completed_closure_independently_recomputes_canary_before_validator(
    tmp_path, monkeypatch,
):
    state = _synthetic_completed_closure_state(monkeypatch)
    canary_record, canary = state["singletons"][
        "decision_canary_receipt"
    ][0]
    corrupted = _json_copy(canary)
    corrupted["checks"]["odds_isolation"] = False
    state["singletons"]["decision_canary_receipt"] = (
        (canary_record, corrupted),
    )
    shape_hash_calls = 0

    def shape_hash_only(
        value, *, prediction_seal_record, scoring_access_record, score_record,
    ):
        nonlocal shape_hash_calls
        shape_hash_calls += 1
        assert value["schema"] == runner._DECISION_CANARY_RECEIPT_SCHEMA
        assert value["prediction_seal_sha256"] \
            == prediction_seal_record["sha256"]
        assert value["scoring_access_receipt_sha256"] \
            == scoring_access_record["sha256"]
        assert value["decision_scores_sha256"] == score_record["sha256"]

    # This planted canary passes the deliberately limited shape/hash check.
    shape_hash_only(
        corrupted, prediction_seal_record=state["seal_record"],
        scoring_access_record=state["scoring_receipt_record"],
        score_record=state["score_record"],
    )
    monkeypatch.setattr(
        runner, "_validate_decision_canary_receipt", shape_hash_only,
    )
    with pytest.raises(
        sh.CanaryFailed, match="does not independently recompute",
    ):
        runner._validate_existing_completed_closure(
            h=state["h"], k=state["k"],
            result_record=state["result_record"], result=state["result"],
            artifact_root=tmp_path,
        )
    # The closure comparison rejects before delegating to the limited check.
    assert shape_hash_calls == 1


@pytest.mark.parametrize("tamper", [
    "receipt_order", "receipt_omission", "exclusions",
])
def test_completed_closure_rejects_receipt_order_omission_and_exclusions(
    tamper, tmp_path, monkeypatch,
):
    state = _synthetic_completed_closure_state(monkeypatch)
    if tamper == "receipt_order":
        receipts = state["result"]["completed_receipts"]
        receipts[0], receipts[1] = receipts[1], receipts[0]
    elif tamper == "receipt_omission":
        state["result"]["completed_receipts"].pop(1)
    elif tamper == "exclusions":
        state["result"]["exclusions"]["raw_shot_rows_quarantined"] = 0
    else:  # pragma: no cover - parameter list is exact
        raise AssertionError(tamper)
    with pytest.raises(
        sh.LockMismatch, match="receipt order or exclusions differ",
    ):
        runner._validate_existing_completed_closure(
            h=state["h"], k=state["k"],
            result_record=state["result_record"], result=state["result"],
            artifact_root=tmp_path,
        )


@pytest.mark.parametrize("claimless", [
    "decision_prediction_intent", "decision_prediction_block",
])
def test_completed_closure_rejects_claimless_singleton_and_block(
    claimless, tmp_path, monkeypatch,
):
    require_real_claim = runner._require_decision_record_claim
    state = _synthetic_completed_closure_state(monkeypatch)
    if claimless == "decision_prediction_block":
        record, value = state["prediction_blocks"][0]
        ordinal = 0
    else:
        record, value = state["singletons"][claimless][0]
        ordinal = None
    assert runner._write_content_addressed_json(
        claimless, value, artifact_root=tmp_path, ordinal=ordinal,
    ) == record

    def require_target_claim(
        logical, candidate, *, artifact_root, ordinal=None,
    ):
        if logical == claimless:
            return require_real_claim(
                logical, candidate, artifact_root=artifact_root,
                ordinal=ordinal,
            )
        return None

    monkeypatch.setattr(
        runner, "_require_decision_record_claim", require_target_claim,
    )
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="incomplete durable state",
    ):
        runner._validate_existing_completed_closure(
            h=state["h"], k=state["k"],
            result_record=state["result_record"], result=state["result"],
            artifact_root=tmp_path,
        )


def test_decide_cli_returns_zero_and_prints_published_result(
    monkeypatch, capsys,
):
    expected = {"status": "COMPLETED", "disposition": "REJECT"}
    monkeypatch.setattr(runner, "run_decision", lambda **kwargs: expected)
    assert runner.main([
        "decide", "--h", "a" * 40, "--k", "b" * 40,
    ]) == 0
    assert json.loads(capsys.readouterr().out) == expected


# ==========================================================================
# 10. Cross-phase terminal/refusal lifecycle (synthetic effects only)
# ==========================================================================

def _synthetic_publication_state(
    monkeypatch, *, forbidden_logicals: tuple[str, ...] = (),
    namespace_names: tuple[str, ...] | None = None,
    patch_live_provenance: bool = True,
):
    """Replace publication I/O with an in-memory immutable singleton."""
    state = {
        "terminal": None,
        "decision_result_writes": 0,
        "singleton_scans": [],
        "namespace_names_override": namespace_names,
    }

    def singletons(logical, *, artifact_root):
        del artifact_root
        state["singleton_scans"].append(logical)
        if logical in forbidden_logicals:
            raise AssertionError(
                f"planted outcome-bearing artifact was opened: {logical}"
            )
        if logical == "decision_result" and state["terminal"] is not None:
            return [state["terminal"]]
        return []

    def write_once(logical, value, *, artifact_root, **kwargs):
        del artifact_root, kwargs
        assert logical == "decision_result"
        record = runner._decision_record(logical, value)
        if state["terminal"] is None:
            state["terminal"] = (record, _json_copy(value))
            state["decision_result_writes"] += 1
            return record, True
        assert state["terminal"] == (record, value)
        return record, False

    def fixed_canonical(_path, value, *, label):
        del label
        raw = runner._canonical_bytes(value)
        return hashlib.sha256(raw).hexdigest(), len(raw)

    def fixed_bytes(_path, raw, *, label):
        del label
        return hashlib.sha256(raw).hexdigest(), len(raw)

    def listed_names(*, artifact_root):
        del artifact_root
        if state["namespace_names_override"] is not None:
            return state["namespace_names_override"]
        if state["terminal"] is None:
            return ()
        record, _ = state["terminal"]
        return (Path(record["path"]).name, ".decision-result.claim")

    monkeypatch.setattr(runner, "_decision_singletons", singletons)
    monkeypatch.setattr(
        runner, "_experiment_transaction_lock",
        lambda **kwargs: contextlib.nullcontext(),
    )
    monkeypatch.setattr(runner, "_write_decision_artifact_once", write_once)
    monkeypatch.setattr(
        runner, "_read_canonical",
        lambda *args, **kwargs: ({
            "canary_receipt": {"synthetic": True},
            "audit_receipt": {"synthetic": True},
        }, b"synthetic H manifest\n"),
    )
    monkeypatch.setattr(runner, "_write_fixed_canonical_once", fixed_canonical)
    monkeypatch.setattr(runner, "_write_fixed_bytes_once", fixed_bytes)
    monkeypatch.setattr(runner, "_discover_prediction_blocks", lambda **kwargs: [])
    monkeypatch.setattr(runner, "_decision_namespace_names", listed_names)
    monkeypatch.setattr(
        runner, "_require_existing_decision_result_claim",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        runner, "_require_no_orphan_fixed_publication",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        runner, "_require_fixed_publication_bytes",
        lambda *args, **kwargs: None,
    )
    if patch_live_provenance:
        monkeypatch.setattr(
            runner, "_require_live_publication_provenance",
            lambda **kwargs: {
                "canary_receipt": {"synthetic": True},
                "audit_receipt": {"synthetic": True},
            },
        )
    return state


def _synthetic_native_semantic_refusal(
    h, *, native_intent_sha256="1" * 64,
    job_request_sha256="2" * 64,
):
    return {
        "schema": runner._NATIVE_SEMANTIC_REFUSAL_SCHEMA,
        "native_intent_sha256": native_intent_sha256,
        "job_request_sha256": job_request_sha256,
        "harness_commit": h.commit,
        "harness_manifest_sha256": h.manifest_sha256,
        "training_schedule_sha256": h.training_schedule_sha256,
        "refusal_kind": "NativeFitFailure",
        "exception_type": "synthetic.NativeNumericalFailure",
        "message": "synthetic scientific fit refusal",
    }


def _synthetic_bound_native_sandbox_contract():
    """Make an offline-valid contract without hashing the live runtime tree."""
    contract = _json_copy(runner._native_sandbox_contract())
    executable_paths = sorted(
        set(contract["process_exec_paths"]) | {
            contract["sandbox_executable"],
            str(runner._NATIVE_RSS_MONITOR_EXECUTABLE),
        }
    )
    executables = []
    for logical_path in executable_paths:
        is_launcher = logical_path == contract["python_launcher"]
        executables.append({
            "logical_path": logical_path,
            "resolved_path": (
                contract["python_resolved"] if is_launcher
                else logical_path
            ),
            "link_chain": [], "mode": 0o755, "bytes": 1,
            "sha256": (
                contract["python_sha256"] if is_launcher
                else hashlib.sha256(logical_path.encode("utf-8")).hexdigest()
            ),
        })
    runtime_payload = {
        "schema": runner._NATIVE_RUNTIME_CLOSURE_SCHEMA,
        "tree_digest_schema": runner._NATIVE_RUNTIME_TREE_SCHEMA,
        "sealed_read_roots": list(runner._NATIVE_SEALED_READ_ROOTS),
        "system_read_literals": [{
            "logical_path": literal, "resolved_path": literal,
            "link_chain": [], "mode": 0o444, "bytes": 1,
            "sha256": hashlib.sha256(literal.encode("utf-8")).hexdigest(),
        } for literal in contract["system_read_literals"]],
        "mutable_roots": [{
            "logical_path": "/", "resolved_path": "/", "link_chain": [],
            "tree_sha256": "9" * 64, "files": 1, "directories": 1,
            "symlinks": 0, "bytes": 1,
        }],
        "executables": executables,
        "platform": {
            "architecture": "synthetic-arm64",
            "kernel_release": "synthetic-kernel",
            "sw_vers": "synthetic macOS build",
            "root_mount": "/dev/synthetic on / (apfs, sealed, read-only)",
            "sdk_logical_path": contract["sdk_root"],
            "sdk_resolved_path": str(Path(contract["sdk_root"]).resolve()),
            "sdk_link_chain": [], "clang_version": "synthetic clang",
        },
        "file_count": 1, "directory_count": 1,
        "symlink_count": 0, "bytes": 1,
    }
    contract["runtime_closure"] = {
        **runtime_payload,
        "sha256": hashlib.sha256(
            runner._canonical_bytes(runtime_payload)
        ).hexdigest(),
    }
    runner._validate_native_sandbox_contract_shape(
        contract, resolve_live_paths=False,
    )
    return contract


def _mutated_synthetic_native_runtime_contract(contract):
    changed = _json_copy(contract)
    runtime_payload = {
        key: value for key, value in changed["runtime_closure"].items()
        if key != "sha256"
    }
    runtime_payload["platform"]["architecture"] = "synthetic-x86_64"
    changed["runtime_closure"] = {
        **runtime_payload,
        "sha256": hashlib.sha256(
            runner._canonical_bytes(runtime_payload)
        ).hexdigest(),
    }
    runner._validate_native_sandbox_contract_shape(
        changed, resolve_live_paths=False,
    )
    return changed


_SYNTHETIC_REFUSAL_DEFAULT = object()


def _build_synthetic_native_refusal_receipt(
    state, *, block_records=(),
    semantic_refusal=_SYNTHETIC_REFUSAL_DEFAULT,
    refusal_source="worker_semantic_refusal", exit_code=17,
    post_launch_sandbox_contract=None,
):
    if semantic_refusal is _SYNTHETIC_REFUSAL_DEFAULT:
        semantic_refusal = state["semantic_refusal"]
    post_launch_sandbox_contract = (
        state["sandbox_contract"]
        if post_launch_sandbox_contract is None
        else post_launch_sandbox_contract
    )
    block_records = list(block_records)
    streamed_events = [] if semantic_refusal is None else [semantic_refusal]
    return runner._make_native_refusal_receipt(
        semantic_refusal=semantic_refusal,
        refusal_source=refusal_source,
        h=state["h"],
        training_sha256=state["h"].training_schedule_sha256,
        native_intent=state["native_intent"],
        native_intent_record=state["native_intent_record"],
        job_ordinals=[0], block_records=block_records,
        output_bytes=(
            sum(record["bytes"] for record in block_records)
            + sum(len(runner._canonical_bytes(event))
                  for event in streamed_events)
        ),
        exit_code=exit_code,
        sandbox_contract=state["sandbox_contract"],
        sandbox_run=state["sandbox_run"],
        runtime_snapshot=state["runtime_snapshot"],
        runtime_observed=state["runtime_observed"],
        post_launch_sandbox_contract=post_launch_sandbox_contract,
    )


def _synthetic_native_refusal_state(artifact_root):
    schedule = ({
        "ordinal": 0, "match_id": "synthetic-refusal-0",
        "season": "synthetic/01", "date": "2020-01-04",
        "home_key": "home", "away_key": "away",
        "block": "synthetic-2020-W01", "cutoff": "2020-01-04",
    },)
    training_sha256 = runner._digest_rows(
        runner._K2_SCHEDULE_SCHEMA, schedule,
    )
    sandbox_contract = _synthetic_bound_native_sandbox_contract()
    h = runner._VerifiedH(
        "a" * 40, "b" * 64, training_sha256, "d" * 64,
        native_runtime_lock=_json_copy(
            sandbox_contract["runtime_closure"]
        ),
    )
    native_intent = {
        "schema": runner._NATIVE_INTENT_SCHEMA,
        "harness_commit": h.commit,
        "harness_manifest_sha256": h.manifest_sha256,
        "parent_commit": runner._NATIVE_PARENT_COMMIT,
        "parent_tree": runner._NATIVE_PARENT_TREE,
        "training_schedule_sha256": training_sha256,
        "raw_inputs": [{
            "path": f"data/epl/raw/{name}",
            "sha256": runner._native_raw_digests()[name], "bytes": 1,
        } for name in runner._NATIVE_RAW_NAMES],
        "schedule": [dict(row) for row in schedule],
        "sandbox_contract_sha256": runner._native_sandbox_contract_sha256(
            sandbox_contract,
        ),
    }
    native_intent_record, created = runner._write_decision_artifact_once(
        "native_intent", native_intent, artifact_root=artifact_root,
    )
    assert created
    request = runner._native_request(
        native_intent=native_intent,
        native_intent_sha256=native_intent_record["sha256"],
        block_ordinals=[0], block_count=1,
    )
    job_request_sha256 = hashlib.sha256(
        runner._canonical_bytes(request)
    ).hexdigest()
    semantic_refusal = _synthetic_native_semantic_refusal(
        h, native_intent_sha256=native_intent_record["sha256"],
        job_request_sha256=job_request_sha256,
    )
    temporary = Path(artifact_root) / "synthetic-native-refusal-job"
    parent = temporary / "parent"
    request_path = temporary / "request.json"
    runtime = temporary / "runtime"
    profile = runner._native_sandbox_profile(
        contract=sandbox_contract, temporary_root=temporary,
        parent_root=parent, request_path=request_path,
        runtime_root=runtime,
    )
    environment = runner._native_environment_values(
        contract=sandbox_contract, parent_root=parent,
        request_path=request_path, runtime_root=runtime,
    )
    sandbox_run = runner._native_sandbox_run_receipt(
        contract=sandbox_contract, profile=profile,
        temporary_root=temporary, parent_root=parent,
        request_path=request_path, runtime_root=runtime,
        environment=environment,
    )
    runtime.mkdir(parents=True)
    runtime_snapshot = runner._native_runtime_output_snapshot(runtime)
    runtime_observed = {
        "files": runtime_snapshot["file_count"],
        "bytes": runtime_snapshot["bytes"], "rss_bytes": 0,
    }
    state = {
        "h": h, "schedule": schedule, "native_intent": native_intent,
        "native_intent_record": native_intent_record,
        "semantic_refusal": semantic_refusal,
        "sandbox_contract": sandbox_contract,
        "sandbox_run": sandbox_run,
        "runtime_snapshot": runtime_snapshot,
        "runtime_observed": runtime_observed,
    }
    state["receipt"] = _build_synthetic_native_refusal_receipt(state)
    return state


def test_native_refusal_schema_parity_and_valid_receipt_round_trip(tmp_path):
    state = _synthetic_native_refusal_state(tmp_path)
    h = state["h"]
    contract = sh._expected_h_output_schemas()["native_refusal"]
    receipt = state["receipt"]

    assert runner._k2_schemas()["native_refusal"] == contract["schema"]
    assert receipt["schema"] == contract["schema"]
    assert set(receipt) == set(contract["fields"])
    assert receipt["semantic_refusal"]["schema"] \
        == contract["semantic_refusal_schema"]
    assert set(receipt["semantic_refusal"]) \
        == set(contract["semantic_refusal_fields"])
    execution = receipt["semantic_refusal"]
    assert execution["source"] == "worker_semantic_refusal"
    assert execution["source"] in contract["sources"]
    assert execution["worker_event"] == execution["terminal_event"]
    assert execution["terminal_event"]["schema"] \
        == contract["semantic_event_schema"]
    assert set(execution["terminal_event"]) \
        == set(contract["semantic_event_fields"])
    assert execution["sandbox_contract"]["schema"] \
        == contract["sandbox_contract_schema"]
    assert execution["sandbox_run"]["schema"] \
        == contract["sandbox_run_schema"]
    assert execution["runtime_snapshot"]["schema"] \
        == contract["runtime_snapshot_schema"]
    assert set(execution["runtime_observed"]) \
        == set(contract["runtime_observed_fields"])
    assert execution["post_launch_sandbox_contract"] \
        == execution["sandbox_contract"]
    assert execution["post_launch_sandbox_contract_sha256"] \
        == execution["sandbox_contract_sha256"]
    mapped = runner._validate_native_refusal_receipt(
        receipt, h=h, training_sha256=h.training_schedule_sha256,
        artifact_root=tmp_path,
    )
    assert type(mapped) is sh.FitFailure
    assert str(mapped) == (
        "NativeFitFailure (synthetic.NativeNumericalFailure): "
        "synthetic scientific fit refusal"
    )

    record, created = runner._write_decision_artifact_once(
        "native_refusal", receipt, artifact_root=tmp_path,
    )
    assert created
    stored = runner._existing_native_refusal(
        h=h, training_sha256=h.training_schedule_sha256,
        artifact_root=tmp_path,
    )
    assert stored is not None
    stored_record, stored_receipt, stored_error = stored
    assert stored_record == record
    assert stored_receipt == receipt
    assert type(stored_error) is sh.FitFailure
    assert str(stored_error) == str(mapped)


@pytest.mark.parametrize(("shard_state", "expected", "pattern"), [
    (
        "nonexistent", sh.LockMismatch,
        "native_block artifact is absent or not a regular file",
    ),
    ("tampered", sh.FixtureSetMismatch, "native block row identity differs"),
])
def test_native_refusal_rejects_nonexistent_and_tampered_claimed_shards(
    shard_state, expected, pattern, tmp_path,
):
    state = _synthetic_native_refusal_state(tmp_path)
    h = state["h"]
    if shard_state == "nonexistent":
        digest = "3" * 64
        block_record = {
            "path": (
                f"{sh.SHOTS_ARTIFACT_ROOT}/"
                f"native-block-000-{digest}.json"
            ),
            "sha256": digest, "bytes": 137,
            "schema": runner._NATIVE_BLOCK_SCHEMA,
        }
    else:
        expected_row = state["schedule"][0]
        row = {
            name: expected_row[name] for name in (
                "ordinal", "match_id", "season", "block", "cutoff",
                "home_key", "away_key",
            )
        } | {"native": [0.5, 0.3, 0.2], "y": 0}
        row["match_id"] = "tampered-match-id"
        shard = {
            "schema": runner._NATIVE_BLOCK_SCHEMA,
            "native_intent_sha256": state["native_intent_record"]["sha256"],
            "block_identity_sha256": runner._native_block_identity_sha256(
                state["native_intent_record"]["sha256"], 0,
                state["schedule"],
            ),
            "harness_commit": h.commit,
            "harness_manifest_sha256": h.manifest_sha256,
            "parent_commit": runner._NATIVE_PARENT_COMMIT,
            "parent_tree": runner._NATIVE_PARENT_TREE,
            "training_schedule_sha256": h.training_schedule_sha256,
            "block_ordinal": 0, "block": expected_row["block"],
            "cutoff": expected_row["cutoff"], "rows": [row],
            "receipt": {},
        }
        block_record = runner._write_native_block_shard(
            shard, artifact_root=tmp_path,
        )
    receipt = _build_synthetic_native_refusal_receipt(
        state, block_records=[block_record],
    )
    with pytest.raises(expected, match=pattern):
        runner._validate_native_refusal_receipt(
            receipt, h=h, training_sha256=h.training_schedule_sha256,
            artifact_root=tmp_path,
        )


@pytest.mark.parametrize("tamper", [
    "harness_commit", "harness_manifest_sha256", "training_schedule_sha256",
    "native_intent_sha256", "native_intent_record", "job_request_sha256",
    "native_intent_sha256_non_string", "job_ordinals", "message",
    "output_lines", "output_bytes", "exit_code",
])
def test_native_refusal_receipt_rejects_bound_identity_and_stream_tampering(
    tamper, tmp_path,
):
    state = _synthetic_native_refusal_state(tmp_path)
    h = state["h"]
    receipt = _json_copy(state["receipt"])
    if tamper == "harness_commit":
        receipt[tamper] = "9" * 40
    elif tamper in {
        "harness_manifest_sha256", "training_schedule_sha256",
        "native_intent_sha256", "job_request_sha256",
    }:
        receipt[tamper] = "9" * 64
    elif tamper == "native_intent_sha256_non_string":
        receipt["native_intent_sha256"] = 9
    elif tamper == "native_intent_record":
        receipt[tamper]["sha256"] = "9" * 64
    elif tamper == "job_ordinals":
        receipt[tamper] = [0, 0]
    elif tamper == "message":
        receipt["semantic_refusal"]["worker_event"][
            "message"
        ] = "tampered refusal message"
    elif tamper in {"output_lines", "output_bytes"}:
        receipt[tamper] += 1
    elif tamper == "exit_code":
        receipt[tamper] = 0
    else:  # pragma: no cover - parameter list is exact
        raise AssertionError(tamper)

    with pytest.raises(sh.LockMismatch):
        runner._validate_native_refusal_receipt(
            receipt, h=h, training_sha256=h.training_schedule_sha256,
            artifact_root=tmp_path,
        )


@pytest.mark.parametrize(("tamper", "pattern"), [
    ("h_runtime_lock", "sandbox contract differs from exact H"),
    ("sandbox_run", "sandbox policy digest differs"),
    ("runtime_snapshot", "runtime output tree digest differs"),
    (
        "runtime_observed",
        "resource observation does not bind its snapshot",
    ),
    (
        "post_launch_sandbox_contract",
        "worker refusal execution classification differs",
    ),
    (
        "post_launch_sandbox_contract_sha256",
        "native refusal receipt does not recompute",
    ),
    (
        "source",
        "runtime mismatch execution classification differs",
    ),
    ("terminal_event", "native refusal receipt does not recompute"),
    (
        "worker_event",
        "worker refusal execution classification differs",
    ),
    ("v1", "native refusal receipt provenance differs"),
])
def test_native_refusal_v2_execution_envelope_rejects_independent_tampering(
    tamper, pattern, tmp_path,
):
    state = _synthetic_native_refusal_state(tmp_path)
    h = state["h"]
    receipt = _json_copy(state["receipt"])
    execution = receipt["semantic_refusal"]
    if tamper == "h_runtime_lock":
        changed_contract = _mutated_synthetic_native_runtime_contract(
            state["sandbox_contract"],
        )
        h = runner._VerifiedH(
            h.commit, h.manifest_sha256, h.training_schedule_sha256,
            h.decision_schedule_sha256,
            native_runtime_lock=changed_contract["runtime_closure"],
        )
    elif tamper == "sandbox_run":
        execution["sandbox_run"]["policy_sha256"] = "9" * 64
    elif tamper == "runtime_snapshot":
        execution["runtime_snapshot"]["sha256"] = "9" * 64
    elif tamper == "runtime_observed":
        execution["runtime_observed"]["files"] = -1
    elif tamper == "post_launch_sandbox_contract":
        changed_contract = _mutated_synthetic_native_runtime_contract(
            execution["post_launch_sandbox_contract"],
        )
        execution["post_launch_sandbox_contract"] = changed_contract
        execution["post_launch_sandbox_contract_sha256"] = (
            runner._native_sandbox_contract_sha256(changed_contract)
        )
    elif tamper == "post_launch_sandbox_contract_sha256":
        execution[tamper] = "9" * 64
    elif tamper == "source":
        execution["source"] = "parent_runtime_closure_mismatch"
    elif tamper == "terminal_event":
        execution["terminal_event"]["message"] = (
            "tampered terminal refusal"
        )
    elif tamper == "worker_event":
        execution["worker_event"] = None
    elif tamper == "v1":
        receipt["schema"] = "epl-shots-native-refusal-receipt-1"
    else:  # pragma: no cover - parameter list is exact
        raise AssertionError(tamper)

    with pytest.raises(sh.LockMismatch, match=pattern):
        runner._validate_native_refusal_receipt(
            receipt, h=h, training_sha256=h.training_schedule_sha256,
            artifact_root=tmp_path,
        )


def test_native_refusal_v2_maps_proven_parent_runtime_mismatch_exactly(
    tmp_path,
):
    state = _synthetic_native_refusal_state(tmp_path)
    changed_contract = _mutated_synthetic_native_runtime_contract(
        state["sandbox_contract"],
    )
    receipt = _build_synthetic_native_refusal_receipt(
        state, semantic_refusal=None,
        refusal_source="parent_runtime_closure_mismatch",
        exit_code=0,
        post_launch_sandbox_contract=changed_contract,
    )
    execution = receipt["semantic_refusal"]
    assert execution["worker_event"] is None
    assert execution["terminal_event"]["refusal_kind"] \
        == "NativeRuntimeClosureMismatch"
    assert execution["post_launch_sandbox_contract_sha256"] \
        == runner._native_sandbox_contract_sha256(changed_contract)
    assert execution["sandbox_contract_sha256"] \
        != execution["post_launch_sandbox_contract_sha256"]
    assert receipt["output_lines"] == 0
    assert receipt["output_bytes"] == 0
    assert receipt["exit_code"] == 0

    mapped = runner._validate_native_refusal_receipt(
        receipt, h=state["h"],
        training_sha256=state["h"].training_schedule_sha256,
        artifact_root=tmp_path,
    )
    assert type(mapped) is runner.NativeRuntimeClosureMismatch
    assert isinstance(mapped, sh.LockMismatch)
    assert not isinstance(mapped, runner.NonPublishingRunStop)
    assert str(mapped) == runner._NATIVE_RUNTIME_MISMATCH_MESSAGE


def test_existing_native_refusal_stops_before_native_or_training_data_setup(
    tmp_path, monkeypatch,
):
    state = _synthetic_native_refusal_state(tmp_path)
    h = state["h"]
    receipt = state["receipt"]
    record, _ = runner._write_decision_artifact_once(
        "native_refusal", receipt, artifact_root=tmp_path,
    )
    calls = {"verify_h": 0, "data_or_setup": 0}

    def verify_h(commit):
        assert commit == h.commit
        calls["verify_h"] += 1
        return h

    def forbidden_setup(*args, **kwargs):
        del args, kwargs
        calls["data_or_setup"] += 1
        pytest.fail("native worker/data setup ran despite durable refusal")

    def artifact_path_only(value, *, create=False):
        assert create is False
        if Path(value) == tmp_path:
            return tmp_path
        return forbidden_setup(value, create=create)

    monkeypatch.setattr(
        runner, "_fixed_repo_artifact_root", lambda value: Path(value),
    )
    monkeypatch.setattr(runner, "verify_harness_live", verify_h)
    monkeypatch.setattr(runner, "_training_binding", forbidden_setup)
    monkeypatch.setattr(runner, "_componentwise_regular_path", artifact_path_only)
    monkeypatch.setattr(runner, "_native_temporary_root_lease", forbidden_setup)
    monkeypatch.setattr(runner, "_materialize_native_parent", forbidden_setup)
    monkeypatch.setattr(runner, "_install_native_raw_inputs", forbidden_setup)
    monkeypatch.setattr(runner.subprocess, "Popen", forbidden_setup)

    for _ in range(2):
        with pytest.raises(sh.FitFailure) as stopped:
            runner._run_native_training_blocks_after_h(
                h_commit=h.commit, artifact_root=tmp_path,
            )
        assert str(stopped.value) == (
            "NativeFitFailure (synthetic.NativeNumericalFailure): "
            "synthetic scientific fit refusal"
        )
        assert stopped.value.__notes__ == [
            f"durable native refusal receipt: {record['sha256']}"
        ]
    assert calls == {"verify_h": 2, "data_or_setup": 0}


def test_native_refusal_claim_without_bytes_requires_manual_reconciliation(
    tmp_path,
):
    h, _ = _decision_test_h_k()
    assert runner._reserve_digest(tmp_path, "native-refusal", "9" * 64)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="claim lacks complete durable bytes",
    ):
        runner._existing_native_refusal(
            h=h, training_sha256=h.training_schedule_sha256,
            artifact_root=tmp_path,
        )


def test_durable_native_refusal_survives_parent_crash_after_publication(
    tmp_path,
):
    state = _synthetic_native_refusal_state(tmp_path)
    h = state["h"]
    receipt = state["receipt"]
    published = {}

    def publish_then_crash():
        published["record"], _ = runner._write_decision_artifact_once(
            "native_refusal", receipt, artifact_root=tmp_path,
        )
        raise RuntimeError("synthetic parent crash after durable publication")

    with pytest.raises(RuntimeError, match="synthetic parent crash"):
        publish_then_crash()
    stored = runner._existing_native_refusal(
        h=h, training_sha256=h.training_schedule_sha256,
        artifact_root=tmp_path,
    )
    assert stored is not None
    record, stored_receipt, mapped = stored
    assert record == published["record"]
    assert stored_receipt == receipt
    assert type(mapped) is sh.FitFailure
    assert "synthetic scientific fit refusal" in str(mapped)


def test_native_semantic_publication_waits_for_cleanup_and_cleanup_can_veto(
    tmp_path, monkeypatch,
):
    h, _ = _decision_test_h_k()
    receipt = {
        "schema": runner._NATIVE_REFUSAL_RECEIPT_SCHEMA,
        "synthetic": "publication ordering only",
    }
    record = {"sha256": "9" * 64}
    events = []
    cleanup_replaces_unwind = False

    @contextlib.contextmanager
    def outer_cleanup():
        nonlocal cleanup_replaces_unwind
        try:
            yield
        finally:
            events.append("outer-cleanup")
            if cleanup_replaces_unwind:
                raise runner.ManualReconciliationRequired(
                    "synthetic cleanup replaced semantic unwind"
                )

    def publish(logical, value, *, artifact_root, **kwargs):
        del artifact_root, kwargs
        assert logical == "native_refusal"
        assert value == receipt
        assert events == ["outer-cleanup"]
        events.append("publish")
        return dict(record), True

    def reload(**kwargs):
        del kwargs
        events.append("reload")
        return dict(record), dict(receipt), sh.FitFailure("stored refusal")

    monkeypatch.setattr(runner, "_write_decision_artifact_once", publish)
    monkeypatch.setattr(runner, "_existing_native_refusal", reload)

    terminal = sh.FitFailure("synthetic terminal refusal")
    with pytest.raises(sh.FitFailure, match="synthetic terminal refusal"):
        with (
            runner._native_semantic_publication_boundary(
                h=h, training_sha256=h.training_schedule_sha256,
                artifact_root=tmp_path,
            ) as pending,
            outer_cleanup(),
        ):
            pending.arm(receipt, terminal)
    assert events == ["outer-cleanup", "publish", "reload"]
    assert terminal.__notes__ == [
        f"durable native refusal receipt: {record['sha256']}"
    ]

    events.clear()
    cleanup_replaces_unwind = True
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="cleanup replaced semantic unwind",
    ):
        with (
            runner._native_semantic_publication_boundary(
                h=h, training_sha256=h.training_schedule_sha256,
                artifact_root=tmp_path,
            ) as pending,
            outer_cleanup(),
        ):
            pending.arm(receipt, sh.FitFailure("must not publish"))
    assert events == ["outer-cleanup"]


def test_native_completion_publication_waits_for_cleanup_and_cleanup_can_veto(
    tmp_path, monkeypatch,
):
    h, _ = _decision_test_h_k()
    receipt = {
        "schema": runner._NATIVE_COMPLETION_SCHEMA,
        "synthetic": "completion publication ordering only",
    }
    record = {"sha256": "8" * 64}
    events = []
    cleanup_replaces_unwind = False

    @contextlib.contextmanager
    def outer_cleanup():
        nonlocal cleanup_replaces_unwind
        try:
            yield
        finally:
            events.append("outer-cleanup")
            if cleanup_replaces_unwind:
                raise runner.ManualReconciliationRequired(
                    "synthetic cleanup replaced completion unwind"
                )

    def verify_h(candidate):
        assert candidate is h
        events.append("verify-h")

    def publish(logical, value, *, artifact_root, **kwargs):
        del artifact_root, kwargs
        assert logical == "native_completion" and value == receipt
        assert events == ["outer-cleanup", "verify-h"]
        events.append("publish")
        return dict(record)

    def discover(**kwargs):
        del kwargs
        events.append("discover")
        return ((dict(record), {"synthetic": True}),)

    monkeypatch.setattr(runner, "_verify_harness_identity_live", verify_h)
    monkeypatch.setattr(runner, "_write_content_addressed_json", publish)
    monkeypatch.setattr(
        runner, "_discover_completed_native_block_shards", discover,
    )

    with (
        runner._native_completion_publication_boundary(
            artifact_root=tmp_path,
        ) as pending,
        outer_cleanup(),
    ):
        pending.arm(
            receipt, native_intent={"schema": runner._NATIVE_INTENT_SCHEMA},
            native_intent_sha256="1" * 64, h=h,
            training_sha256=h.training_schedule_sha256,
            raw_inputs=(), blocks=(), sandbox_contract={"synthetic": True},
        )
    assert pending.records == (record,)
    assert events == [
        "outer-cleanup", "verify-h", "publish", "discover", "verify-h",
    ]

    events.clear()
    cleanup_replaces_unwind = True
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="cleanup replaced completion unwind",
    ):
        with (
            runner._native_completion_publication_boundary(
                artifact_root=tmp_path,
            ) as pending,
            outer_cleanup(),
        ):
            pending.arm(
                receipt,
                native_intent={"schema": runner._NATIVE_INTENT_SCHEMA},
                native_intent_sha256="1" * 64, h=h,
                training_sha256=h.training_schedule_sha256,
                raw_inputs=(), blocks=(),
                sandbox_contract={"synthetic": True},
            )
    assert events == ["outer-cleanup"]


def test_native_semantic_refusal_envelope_maps_to_typed_terminal_fit_failure():
    h, _ = _decision_test_h_k()
    value = _synthetic_native_semantic_refusal(h)
    refusal = runner._native_semantic_refusal(
        value, native_intent_sha256="1" * 64,
        job_request_sha256="2" * 64, h=h,
        training_sha256=h.training_schedule_sha256,
    )
    assert type(refusal) is sh.FitFailure
    assert str(refusal) == (
        "NativeFitFailure (synthetic.NativeNumericalFailure): "
        "synthetic scientific fit refusal"
    )
    assert not isinstance(refusal, runner.NonPublishingRunStop)


def _isolated_native_semantic_classifier():
    """Compile only the embedded child's classifier, never its data/model body."""
    tree = ast.parse(runner._NATIVE_WORKER_SOURCE)
    assignments = {
        "SEMANTIC_REFUSAL_SCHEMA", "semantic_domain_envelope",
        "SEMANTIC_DOMAIN_EXCEPTION_TYPES", "SEMANTIC_DOMAIN_MODULES",
        "INFRASTRUCTURE_EXCEPTION_TYPES", "INFRASTRUCTURE_EXCEPTION_MODULES",
    }
    definitions = {
        "canonical", "NativeSemanticRefusal", "NativeSemanticDomainEnvelope",
        "module_matches", "exception_graph", "traceback_origin",
        "semantic_domain_failure", "semantic_excepthook",
    }

    def selected(node):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            return node.name in definitions
        if isinstance(node, ast.Assign):
            names = {
                target.id for target in node.targets
                if isinstance(target, ast.Name)
            }
            if not names.intersection(assignments):
                return False
            # Select the classifier's pre-bind sentinel, never the real
            # post-request assignment later in the embedded worker body.
            if "semantic_domain_envelope" in names:
                return (
                    isinstance(node.value, ast.Constant)
                    and node.value.value is None
                )
            return True
        return False

    isolated = ast.Module(
        body=[node for node in tree.body if selected(node)], type_ignores=[],
    )
    ast.fix_missing_locations(isolated)
    namespace = {
        "__name__": "isolated_native_worker", "hashlib": hashlib,
        "json": json,
    }
    exec(compile(isolated, "<isolated-native-classifier>", "exec"), namespace)

    output = io.BytesIO()
    fallbacks = []
    namespace["sys"] = SimpleNamespace(
        stdout=SimpleNamespace(buffer=output),
        __excepthook__=(
            lambda exc_type, exc, traceback:
            fallbacks.append((exc_type, exc, traceback))
        ),
    )
    intent = {
        "harness_commit": "a" * 40,
        "harness_manifest_sha256": "b" * 64,
        "training_schedule_sha256": "c" * 64,
    }
    namespace["semantic_domain_envelope"] = namespace[
        "NativeSemanticDomainEnvelope"
    ](intent, "d" * 64, b"synthetic bound request\n")
    return namespace, output, fallbacks


def _invoke_isolated_native_excepthook(namespace, raise_failure):
    try:
        raise_failure()
    except BaseException as exc:
        namespace["semantic_excepthook"](
            type(exc), exc, exc.__traceback__,
        )
        return exc
    raise AssertionError("synthetic failure did not raise")


@pytest.mark.parametrize(("failure", "expected_kind"), [
    (lambda namespace: ValueError("deterministic post-bind value failure"),
     "NativeFitFailure"),
    (lambda namespace: np.linalg.LinAlgError("singular synthetic system"),
     "NativeFitFailure"),
    (lambda namespace: namespace["NativeSemanticRefusal"](
        "explicit scientific refusal"), "NativeSemanticRefusal"),
])
def test_embedded_native_classifier_emits_one_bound_semantic_envelope(
    failure, expected_kind,
):
    namespace, output, fallbacks = _isolated_native_semantic_classifier()
    raised = failure(namespace)
    _invoke_isolated_native_excepthook(
        namespace, lambda: (_ for _ in ()).throw(raised),
    )

    raw = output.getvalue()
    assert raw.count(b"\n") == 1
    payload = json.loads(raw.decode("ascii"))
    assert payload["schema"] == runner._NATIVE_SEMANTIC_REFUSAL_SCHEMA
    assert payload["refusal_kind"] == expected_kind
    assert payload["exception_type"].endswith(
        f".{type(raised).__name__}",
    )
    assert payload["native_intent_sha256"] == "d" * 64
    assert fallbacks == []


@pytest.mark.parametrize("failure", [
    OSError("synthetic I/O interruption"),
    ImportError("synthetic import interruption"),
    MemoryError("synthetic memory interruption"),
    RecursionError("synthetic recursion interruption"),
    subprocess.SubprocessError("synthetic subprocess interruption"),
    KeyboardInterrupt("synthetic operator interruption"),
])
def test_embedded_native_classifier_does_not_publish_infrastructure_failure(
    failure,
):
    namespace, output, fallbacks = _isolated_native_semantic_classifier()
    caught = _invoke_isolated_native_excepthook(
        namespace, lambda: (_ for _ in ()).throw(failure),
    )
    assert output.getvalue() == b""
    assert len(fallbacks) == 1 and fallbacks[0][1] is caught


@pytest.mark.parametrize("origin", ["subprocess", "pytensor.link.c.cmodule"])
def test_embedded_native_classifier_vetoes_infrastructure_traceback_origin(
    origin,
):
    namespace, output, fallbacks = _isolated_native_semantic_classifier()
    origin_namespace = {"__name__": origin}
    exec(compile(
        "def fail():\n    raise ValueError('synthetic tool failure')\n",
        f"<{origin}-failure>", "exec",
    ), origin_namespace)
    caught = _invoke_isolated_native_excepthook(
        namespace, origin_namespace["fail"],
    )
    assert output.getvalue() == b""
    assert len(fallbacks) == 1 and fallbacks[0][1] is caught


@pytest.mark.parametrize("grouped", [False, True])
def test_embedded_native_classifier_vetoes_chained_or_grouped_infrastructure(
    grouped,
):
    namespace, output, fallbacks = _isolated_native_semantic_classifier()

    def fail():
        if grouped:
            raise ExceptionGroup(
                "mixed synthetic failure",
                [ValueError("semantic leaf"), OSError("I/O leaf")],
            )
        try:
            raise OSError("synthetic infrastructure cause")
        except OSError as cause:
            raise namespace["NativeSemanticRefusal"](
                "synthetic explicit scientific refusal",
            ) from cause

    caught = _invoke_isolated_native_excepthook(namespace, fail)
    assert output.getvalue() == b""
    assert len(fallbacks) == 1 and fallbacks[0][1] is caught


@pytest.mark.parametrize(("field", "replacement"), [
    ("native_intent_sha256", "3" * 64),
    ("job_request_sha256", "4" * 64),
    ("harness_commit", "5" * 40),
    ("harness_manifest_sha256", "6" * 64),
    ("training_schedule_sha256", "7" * 64),
    ("refusal_kind", "InfrastructureFailure"),
    ("exception_type", "invalid exception type"),
    ("message", " untrimmed semantic refusal "),
])
def test_native_semantic_refusal_envelope_rejects_provenance_tampering(
    field, replacement,
):
    h, _ = _decision_test_h_k()
    value = _synthetic_native_semantic_refusal(h)
    value[field] = replacement
    with pytest.raises(sh.LockMismatch, match="semantic refusal provenance"):
        runner._native_semantic_refusal(
            value, native_intent_sha256="1" * 64,
            job_request_sha256="2" * 64, h=h,
            training_sha256=h.training_schedule_sha256,
        )


def test_native_semantic_refusal_envelope_rejects_schema_extension():
    h, _ = _decision_test_h_k()
    value = _synthetic_native_semantic_refusal(h)
    value["attacker_extension"] = True
    with pytest.raises(sh.LockMismatch, match="fields differ"):
        runner._native_semantic_refusal(
            value, native_intent_sha256="1" * 64,
            job_request_sha256="2" * 64, h=h,
            training_sha256=h.training_schedule_sha256,
        )


def test_training_cli_distinguishes_resumable_interruption_from_terminal_stop(
    monkeypatch, capsys,
):
    def interrupted(**kwargs):
        raise runner.NativeWorkerIOFailure("synthetic resumable interruption")

    monkeypatch.setattr(runner, "run_training", interrupted)
    assert runner.main(["train", "--h", "a" * 40]) == 75
    interrupted_output = capsys.readouterr()
    assert interrupted_output.out == ""
    assert interrupted_output.err == (
        "INTERRUPTED NativeWorkerIOFailure: "
        "synthetic resumable interruption\n"
    )

    def terminal(**kwargs):
        raise sh.FitFailure("synthetic terminal fit refusal")

    monkeypatch.setattr(runner, "run_training", terminal)
    assert runner.main(["train", "--h", "a" * 40]) == 2
    terminal_output = capsys.readouterr()
    assert terminal_output.out == ""
    assert terminal_output.err == (
        "STOP FitFailure: synthetic terminal fit refusal\n"
    )


def test_experiment_transaction_lock_serializes_and_binds_h_identity(tmp_path):
    h, _ = _decision_test_h_k()
    expected = (
        "epl-shots-experiment-transaction-lock-1\n"
        f"{h.commit}\n{h.manifest_sha256}\n"
    ).encode("ascii")

    with runner._experiment_transaction_lock(h=h, artifact_root=tmp_path):
        lock_path = tmp_path / ".experiment-transaction.lock"
        assert lock_path.read_bytes() == expected
        assert stat.S_IMODE(lock_path.stat().st_mode) == 0o444
        with pytest.raises(
            runner.RunnerNotReady, match="another experiment transaction",
        ):
            with runner._experiment_transaction_lock(
                h=h, artifact_root=tmp_path,
            ):
                pytest.fail("overlapping experiment lock was acquired")

    # The same H can reacquire its persistent immutable lock after release.
    with runner._experiment_transaction_lock(h=h, artifact_root=tmp_path):
        assert lock_path.read_bytes() == expected

    changed_h = runner._VerifiedH(
        "c" * 40, "d" * 64, h.training_schedule_sha256,
        h.decision_schedule_sha256,
    )
    with pytest.raises(sh.LockMismatch, match="lock bytes differ"):
        with runner._experiment_transaction_lock(
            h=changed_h, artifact_root=tmp_path,
        ):
            pytest.fail("a different H reused the experiment lock")


def test_pre_k_training_refusal_is_one_terminal_and_blocks_later_phases(
    monkeypatch,
):
    h, _ = _decision_test_h_k()
    state = _synthetic_publication_state(monkeypatch)
    executions = 0

    def training_effect(**kwargs):
        nonlocal executions
        del kwargs
        executions += 1
        if executions == 1:
            raise sh.FitFailure("synthetic terminal optimizer refusal")
        pytest.fail("terminal replay reached training native/data access")

    monkeypatch.setattr(runner, "verify_harness_live", lambda commit: h)
    monkeypatch.setattr(runner, "_run_training_after_h", training_effect)
    monkeypatch.setattr(
        runner, "_experiment_transaction_lock",
        lambda **kwargs: contextlib.nullcontext(),
    )
    monkeypatch.setattr(
        runner, "_training_refusal_receipts",
        lambda **kwargs: ([], {"native_blocks": 0}),
    )
    monkeypatch.setattr(
        runner, "_run_decision_after_k",
        lambda **kwargs: pytest.fail(
            "terminal replay reached K verification or decision data access"
        ),
    )

    first = runner.run_training(h_commit=h.commit)
    assert first["status"] == "REFUSED"
    assert state["decision_result_writes"] == 1
    terminal_record, terminal_value = state["terminal"]
    assert terminal_record == first["decision_result"]
    assert terminal_value["coefficient_commit"] == (
        "N/A — K not created after FitFailure"
    )

    assert runner.run_training(h_commit=h.commit) == first
    assert runner.run_decision(
        h_commit=h.commit, k_commit="f" * 40,
    ) == first
    assert executions == 1
    assert state["decision_result_writes"] == 1


@pytest.mark.parametrize(("exception_type", "message"), [
    (runner.NativeWorkerIOFailure, "synthetic worker channel interruption"),
    (runner.NativeWorkerSandboxStop, "synthetic sandbox infrastructure stop"),
    (RuntimeError, "synthetic process crash"),
])
def test_resumable_training_interruption_publishes_no_terminal_and_can_resume(
    monkeypatch, exception_type, message,
):
    h, _ = _decision_test_h_k()
    calls = 0
    expected = {"status": "K_DRAFT_WRITTEN_UNFROZEN", "resumed": True}

    def training_effect(**kwargs):
        nonlocal calls
        del kwargs
        calls += 1
        if calls == 1:
            raise exception_type(message)
        return expected

    monkeypatch.setattr(runner, "verify_harness_live", lambda commit: h)
    monkeypatch.setattr(runner, "_run_training_after_h", training_effect)
    monkeypatch.setattr(
        runner, "_experiment_transaction_lock",
        lambda **kwargs: contextlib.nullcontext(),
    )
    monkeypatch.setattr(
        runner, "_decision_singletons", lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        runner, "_publish_refusal",
        lambda **kwargs: pytest.fail(
            "resumable infrastructure interruption published a terminal"
        ),
    )

    with pytest.raises(exception_type, match=message):
        runner.run_training(h_commit=h.commit)
    assert calls == 1
    assert runner.run_training(h_commit=h.commit) == expected
    assert calls == 2


@pytest.mark.parametrize(("failure", "classification"), [
    (sh.FitFailure("synthetic scientific fit refusal"), "publish"),
    (runner.NativeRuntimeClosureMismatch(
        "synthetic proven runtime closure mismatch"), "publish"),
    (sh.LockMismatch("synthetic generic integrity mismatch"), "manualize"),
    (runner.ManualReconciliationRequired(
        "synthetic existing manual stop"), "propagate"),
    (runner.NativeWorkerIOFailure(
        "synthetic resumable worker stop"), "propagate"),
])
def test_training_orchestrator_publishes_only_authorized_refusal_taxonomy(
    monkeypatch, failure, classification,
):
    h, _ = _decision_test_h_k()
    calls = {"receipts": 0, "publish": 0}

    monkeypatch.setattr(runner, "verify_harness_live", lambda commit: h)
    monkeypatch.setattr(
        runner, "_experiment_transaction_lock",
        lambda **kwargs: contextlib.nullcontext(),
    )
    monkeypatch.setattr(
        runner, "_resume_pre_k_terminal", lambda **kwargs: None,
    )
    monkeypatch.setattr(
        runner, "_require_pre_k_decision_namespace",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        runner, "_require_no_orphan_fixed_publication",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        runner, "_run_training_after_h",
        lambda **kwargs: (_ for _ in ()).throw(failure),
    )

    def receipts(*, artifact_root, strict):
        del artifact_root
        assert strict is True
        calls["receipts"] += 1
        return [], {"native_blocks": 0}

    published = {"status": "synthetic terminal publication"}

    def publish(**kwargs):
        assert kwargs["h"] == h
        assert kwargs["k"] is None
        assert kwargs["refusal"] is failure
        assert kwargs["stage"] == "training"
        calls["publish"] += 1
        return published

    monkeypatch.setattr(runner, "_training_refusal_receipts", receipts)
    monkeypatch.setattr(runner, "_publish_refusal", publish)

    if classification == "publish":
        assert runner.run_training(h_commit=h.commit) is published
        assert calls == {"receipts": 1, "publish": 1}
    elif classification == "manualize":
        with pytest.raises(
            runner.ManualReconciliationRequired,
            match="integrity failure is not an authorized publishable refusal",
        ) as stopped:
            runner.run_training(h_commit=h.commit)
        assert stopped.value.__cause__ is failure
        assert calls == {"receipts": 0, "publish": 0}
    else:
        with pytest.raises(type(failure)) as stopped:
            runner.run_training(h_commit=h.commit)
        assert stopped.value is failure
        assert calls == {"receipts": 0, "publish": 0}


@pytest.mark.parametrize(("failure", "classification"), [
    (sh.FitFailure("synthetic decision fit refusal"), "publish"),
    (sh.LockMismatch("synthetic decision integrity mismatch"), "manualize"),
])
def test_decision_orchestrator_never_publishes_integrity_mismatch(
    tmp_path, monkeypatch, failure, classification,
):
    h, k = _decision_test_h_k()
    calls = {"model": 0, "publish": 0}
    monkeypatch.setattr(
        runner, "_fixed_repo_artifact_root", lambda value: tmp_path,
    )
    monkeypatch.setattr(
        runner, "verify_coefficient_freeze_live",
        lambda h_commit, k_commit: k,
    )
    monkeypatch.setattr(
        runner, "decision_schedule_binding",
        lambda: (h.decision_schedule_sha256, ()),
    )
    monkeypatch.setattr(
        runner, "_reserve_decision_run_state", lambda **kwargs: None,
    )
    monkeypatch.setattr(
        runner, "_existing_decision_result_only", lambda **kwargs: None,
    )

    def load_model(candidate):
        assert candidate == k
        calls["model"] += 1
        raise failure

    published = {"status": "synthetic decision refusal"}

    def publish(**kwargs):
        assert kwargs["h"] == h and kwargs["k"] == k
        assert kwargs["prediction_seal_record"] is None
        assert kwargs["completed_receipts"] == []
        assert kwargs["refusal"] is failure
        assert kwargs["stage"] == "prediction"
        calls["publish"] += 1
        return published

    monkeypatch.setattr(runner, "_load_decision_model", load_model)
    monkeypatch.setattr(runner, "_publish_refusal", publish)
    monkeypatch.setattr(
        runner, "_ensure_prediction_seal",
        lambda **kwargs: pytest.fail("decision corpus opened after model stop"),
    )

    if classification == "publish":
        assert runner._run_decision_after_k(
            h_commit=h.commit, k_commit=k.commit, artifact_root=tmp_path,
        ) is published
        assert calls == {"model": 1, "publish": 1}
    else:
        with pytest.raises(
            runner.ManualReconciliationRequired,
            match="integrity failure is not an authorized publishable refusal",
        ) as stopped:
            runner._run_decision_after_k(
                h_commit=h.commit, k_commit=k.commit, artifact_root=tmp_path,
            )
        assert stopped.value.__cause__ is failure
        assert calls == {"model": 1, "publish": 0}


def test_pre_k_refusal_publication_never_scans_planted_decision_scores(
    monkeypatch,
):
    h, _ = _decision_test_h_k()
    forbidden = (
        "decision_prediction_intent", "prediction_access_receipt",
        "decision_predictions", "prediction_seal", "scoring_access_intent",
        "scoring_access_receipt", "decision_scores",
        "decision_canary_receipt",
    )
    state = _synthetic_publication_state(
        monkeypatch, forbidden_logicals=forbidden,
        namespace_names=(
            "decision-scores-" + "9" * 64 + ".json",
        ),
    )
    monkeypatch.setattr(runner, "verify_harness_live", lambda commit: h)
    monkeypatch.setattr(
        runner, "_run_training_after_h",
        lambda **kwargs: (_ for _ in ()).throw(
            sh.FitFailure("synthetic pre-K semantic refusal")
        ),
    )
    monkeypatch.setattr(
        runner, "_training_refusal_receipts",
        lambda **kwargs: ([], {"native_blocks": 0}),
    )

    with pytest.raises(sh.LockMismatch, match="decision-stage state exists"):
        runner.run_training(h_commit=h.commit)
    assert set(forbidden).isdisjoint(state["singleton_scans"])
    assert state["decision_result_writes"] == 0


def test_h_mutation_during_training_refusal_publication_cannot_return_success(
    monkeypatch,
):
    h, _ = _decision_test_h_k()
    state = _synthetic_publication_state(
        monkeypatch, patch_live_provenance=False,
    )
    verification_calls = 0

    def changing_h(commit):
        nonlocal verification_calls
        assert commit == h.commit
        verification_calls += 1
        if verification_calls == 1:
            return h
        raise sh.LockMismatch("synthetic H changed during refusal publication")

    monkeypatch.setattr(runner, "verify_harness_live", changing_h)
    monkeypatch.setattr(
        runner, "_run_training_after_h",
        lambda **kwargs: (_ for _ in ()).throw(
            sh.FitFailure("synthetic terminal training refusal")
        ),
    )
    monkeypatch.setattr(
        runner, "_training_refusal_receipts", lambda **kwargs: ([], {}),
    )

    with pytest.raises(sh.LockMismatch, match="H changed"):
        runner.run_training(h_commit=h.commit)
    assert verification_calls >= 2
    # A terminal may have reached durable storage before the final live-H
    # check, but no caller may receive a claimed successful publication.
    assert state["decision_result_writes"] in (0, 1)


def test_existing_pre_k_terminal_is_checked_before_training_data_or_native(
    monkeypatch,
):
    h, _ = _decision_test_h_k()
    state = _synthetic_publication_state(monkeypatch)
    refusal = sh.FitFailure("synthetic already-terminal refusal")
    value = runner._refusal_result(
        h=h, k=None, prediction_seal_record=None, completed_receipts=[],
        refusal=refusal, stage="training", counts={"native_blocks": 0},
    )
    record = runner._decision_record("decision_result", value)
    state["terminal"] = (record, value)
    expected = {"status": "REFUSED", "decision_result": record}

    monkeypatch.setattr(runner, "verify_harness_live", lambda commit: h)
    monkeypatch.setattr(
        runner, "_finalize_result_publication", lambda **kwargs: expected,
    )
    monkeypatch.setattr(
        runner, "_run_training_after_h",
        lambda **kwargs: pytest.fail(
            "existing terminal reached training schedule/native/data access"
        ),
    )
    monkeypatch.setattr(
        runner, "_training_refusal_receipts",
        lambda **kwargs: pytest.fail(
            "existing terminal scanned partial training artifacts"
        ),
    )

    assert runner.run_training(h_commit=h.commit) == expected
    assert state["decision_result_writes"] == 0


def test_existing_terminal_bytes_without_claim_refuse_before_phase_access(
    tmp_path,
):
    h, _ = _decision_test_h_k()
    value = runner._refusal_result(
        h=h, k=None, prediction_seal_record=None, completed_receipts=[],
        refusal=sh.FitFailure("synthetic orphan terminal"), stage="training",
        counts={"native_blocks": 0},
    )
    raw = runner._canonical_bytes(value)
    digest = hashlib.sha256(raw).hexdigest()
    path = tmp_path / runner._k2_filename("decision_result", digest)
    path.write_bytes(raw)
    path.chmod(0o444)

    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="incomplete durable state",
    ):
        runner._existing_decision_result_only(artifact_root=tmp_path)


# ==========================================================================
# 10. Amendment 2 Rider 3: the ten previously unexecuted durable-state
#     taxonomy conversions.  Each test drives the production path into the
#     crash/resume state its conversion guards and asserts the strictly
#     stricter ManualReconciliationRequired classification.
# ==========================================================================

def test_optimizer_intent_claim_without_durable_bytes_requires_reconciliation(
    tmp_path,
):
    """A claim name with no durable intent bytes is an interrupted write."""
    intent = _synthetic_optimizer_intent()
    digest = hashlib.sha256(runner._canonical_bytes(intent)).hexdigest()
    claim = tmp_path / ".optimizer-intent.claim"
    claim.write_bytes((digest + "\n").encode("ascii"))
    claim.chmod(0o444)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="optimizer intent was claimed without durable intent bytes",
    ):
        runner._begin_optimizer_once(intent, artifact_root=tmp_path)


def test_optimizer_artifacts_predating_their_claim_require_reconciliation(
    tmp_path, monkeypatch,
):
    """Durable intent bytes that predate their fresh claim are ambiguous."""
    intent = _synthetic_optimizer_intent()
    first = runner._begin_optimizer_once(intent, artifact_root=tmp_path)
    assert first.may_invoke_optimizer
    (tmp_path / ".optimizer-intent.claim").unlink()
    real_records = runner._optimizer_records_at
    intent_scans = 0

    def concurrent_install_scan(logical, *, directory_fd):
        nonlocal intent_scans
        if logical == "optimizer_intent":
            intent_scans += 1
            if intent_scans == 1:
                # The competing writer's durable intent lands between this
                # scan and this process's fresh claim creation.
                return ()
        return real_records(logical, directory_fd=directory_fd)

    monkeypatch.setattr(runner, "_optimizer_records_at", concurrent_install_scan)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="optimizer artifacts predate their durable intent claim",
    ):
        runner._begin_optimizer_once(intent, artifact_root=tmp_path)
    assert intent_scans >= 2


def test_optimizer_receipt_predating_its_claim_requires_reconciliation(
    tmp_path, monkeypatch,
):
    """A durable receipt whose claim was freshly re-created is ambiguous."""
    intent = _synthetic_optimizer_intent()
    attempt = runner._begin_optimizer_once(intent, artifact_root=tmp_path)
    receipt = _synthetic_optimizer_receipt(attempt, intent)
    runner._record_optimizer_receipt(
        intent_record=attempt.intent_record, receipt=receipt,
        artifact_root=tmp_path,
    )
    (tmp_path / ".optimizer-receipt.claim").unlink()
    real_reservation = runner._digest_reservation_at

    @contextlib.contextmanager
    def resurrected_claim(directory_fd, name, digest, *, create):
        # The committed receipt's claim vanished and a concurrent writer
        # re-created it between the receipt scan and this reservation.
        if name == "optimizer-receipt":
            create = True
        with real_reservation(
            directory_fd, name, digest, create=create,
        ) as created:
            yield created

    monkeypatch.setattr(runner, "_digest_reservation_at", resurrected_claim)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="optimizer receipt predates its durable claim",
    ):
        runner._record_optimizer_receipt(
            intent_record=attempt.intent_record, receipt=receipt,
            artifact_root=tmp_path,
        )


def test_stray_decision_result_names_without_terminal_require_reconciliation(
    tmp_path,
):
    """Decision-result names without a terminal singleton never read as clean."""
    (tmp_path / ".decision-result.claim").write_bytes(b"0" * 64 + b"\n")
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="decision result claim/bytes are incomplete",
    ):
        runner._existing_decision_result_only(artifact_root=tmp_path)


def test_orphan_fixed_publication_without_terminal_requires_reconciliation(
    tmp_path, monkeypatch,
):
    """Fixed publication outputs without a terminal result must stop the run."""
    evidence = tmp_path / "evidence_manifest.json"
    report = tmp_path / "epl_shots_result.md"
    monkeypatch.setattr(runner, "_RESULT_EVIDENCE_PATH", evidence)
    monkeypatch.setattr(runner, "_RESULT_REPORT_PATH", report)
    evidence.write_text("{}\n", encoding="ascii")
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="fixed publication output exists without a terminal result",
    ):
        runner._require_no_orphan_fixed_publication(terminal_present=False)
    report.write_text("orphan\n", encoding="ascii")
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="fixed publication output exists without a terminal result",
    ):
        runner._require_no_orphan_fixed_publication(terminal_present=False)
    assert runner._require_no_orphan_fixed_publication(
        terminal_present=True,
    ) is None


def test_concurrently_claimed_access_intent_requires_reconciliation(
    tmp_path, monkeypatch,
):
    """An intent installed between the scan and the claim cannot open source."""
    h, k = _decision_test_h_k()
    intent = runner._make_prediction_intent(
        h=h, k=k, moments_record={"sha256": "2" * 64},
        coefficients_record={"sha256": "3" * 64},
    )
    first = runner._begin_decision_access_once(
        intent_logical="decision_prediction_intent",
        receipt_logical="prediction_access_receipt", intent=intent,
        artifact_root=tmp_path,
        validate_intent=runner._validate_prediction_intent,
        validate_receipt=runner._validate_prediction_access_receipt,
    )
    assert first.may_open_source
    real_singletons = runner._decision_singletons
    intent_scans = 0

    def concurrent_claim_scan(logical, *, artifact_root):
        nonlocal intent_scans
        if logical == "decision_prediction_intent":
            intent_scans += 1
            if intent_scans == 1:
                # The competing writer's intent lands after this scan; it may
                # already have opened the source.
                return ()
        return real_singletons(logical, artifact_root=artifact_root)

    monkeypatch.setattr(runner, "_decision_singletons", concurrent_claim_scan)
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="decision_prediction_intent was concurrently claimed",
    ):
        runner._begin_decision_access_once(
            intent_logical="decision_prediction_intent",
            receipt_logical="prediction_access_receipt", intent=intent,
            artifact_root=tmp_path,
            validate_intent=runner._validate_prediction_intent,
            validate_receipt=runner._validate_prediction_access_receipt,
        )
    assert intent_scans == 1


def test_prediction_blocks_predating_access_intent_require_reconciliation(
    tmp_path, monkeypatch,
):
    """Prediction shards older than their access intent are unaccounted reads."""
    h, k = _decision_test_h_k()
    stray_block = {
        "schema": runner._DECISION_PREDICTION_BLOCK_SCHEMA, "block_ordinal": 0,
    }
    _, created = runner._write_decision_artifact_once(
        "decision_prediction_block", stray_block, artifact_root=tmp_path,
        ordinal=0, claim_name="decision-prediction-block-000",
    )
    assert created
    monkeypatch.setattr(
        runner, "_read_decision_projection",
        lambda *args, **kwargs: pytest.fail(
            "ambiguous fresh access opened the decision source"
        ),
    )
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="prediction blocks predate their access intent",
    ):
        runner._ensure_prediction_seal(
            h=h, k=k, schedule=(),
            scaler=sh.FeatureScaler((0, 0, 0, 0), (1, 1, 1, 1), 1520,
                                    sh.TRAINING_SEASONS),
            beta=np.zeros(8), moments_record={"sha256": "2" * 64},
            coefficients_record={"sha256": "3" * 64}, artifact_root=tmp_path,
        )


def test_prediction_resume_without_all_shards_requires_reconciliation(
    tmp_path, monkeypatch,
):
    """A completed access receipt with missing shards cannot reopen source."""
    h, k = _decision_test_h_k()
    intent = runner._make_prediction_intent(
        h=h, k=k, moments_record={"sha256": "2" * 64},
        coefficients_record={"sha256": "3" * 64},
    )
    intent_record, created = runner._write_decision_artifact_once(
        "decision_prediction_intent", intent, artifact_root=tmp_path,
    )
    assert created
    receipt = runner._make_prediction_access_receipt(
        intent_record=intent_record, intent=intent,
        projection_sha256="4" * 64,
    )
    runner._write_decision_artifact_once(
        "prediction_access_receipt", receipt, artifact_root=tmp_path,
    )
    monkeypatch.setattr(
        runner, "_read_decision_projection",
        lambda *args, **kwargs: pytest.fail(
            "completed prediction access reopened the decision source"
        ),
    )
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="prediction access completed without all 212 shards",
    ):
        runner._ensure_prediction_seal(
            h=h, k=k, schedule=(),
            scaler=sh.FeatureScaler((0, 0, 0, 0), (1, 1, 1, 1), 1520,
                                    sh.TRAINING_SEASONS),
            beta=np.zeros(8), moments_record={"sha256": "2" * 64},
            coefficients_record={"sha256": "3" * 64}, artifact_root=tmp_path,
        )


def test_decision_scores_without_access_closure_require_reconciliation(
    tmp_path, monkeypatch,
):
    """Durable scores without their exactly-once access closure are orphans."""
    h, k = _decision_test_h_k()
    predictions, scoring = _small_prediction_and_scoring_rows()
    seal_record = {"sha256": "8" * 64}
    projection_sha256 = runner._digest_rows(
        runner._DECISION_SCORING_PROJECTION_SCHEMA, scoring,
    )
    scores = runner._decision_score_payload(
        prediction_rows=predictions, scoring_projection=scoring,
        prediction_seal_record=seal_record,
        scoring_access_record={"sha256": "6" * 64},
        scoring_projection_sha256=projection_sha256,
    )
    _, created = runner._write_decision_artifact_once(
        "decision_scores", scores, artifact_root=tmp_path,
    )
    assert created
    monkeypatch.setattr(
        runner, "_read_scoring_projection_after_seal",
        lambda **kwargs: pytest.fail(
            "closure-less durable scores reopened outcomes/market"
        ),
    )
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="decision scores lack a complete scoring-access closure",
    ):
        runner._ensure_decision_scores(
            h=h, k=k, schedule=(),
            scaler=sh.FeatureScaler((0, 0, 0, 0), (1, 1, 1, 1), 1520,
                                    sh.TRAINING_SEASONS),
            beta=np.zeros(8), prediction_seal_record=seal_record,
            prediction_rows=predictions, artifact_root=tmp_path,
        )


def test_opened_scoring_source_without_durable_score_requires_reconciliation(
    tmp_path, monkeypatch,
):
    """An opened exactly-once scoring source with no durable score is terminal."""
    h, k = _decision_test_h_k()
    predictions, scoring = _small_prediction_and_scoring_rows()
    seal_record = {"sha256": "8" * 64}
    intent = runner._make_scoring_access_intent(
        h=h, k=k, prediction_seal_record=seal_record,
    )
    intent_record, created = runner._write_decision_artifact_once(
        "scoring_access_intent", intent, artifact_root=tmp_path,
    )
    assert created
    projection_sha256 = runner._digest_rows(
        runner._DECISION_SCORING_PROJECTION_SCHEMA, scoring,
    )
    receipt = runner._make_scoring_access_receipt(
        intent_record=intent_record, intent=intent,
        projection_sha256=projection_sha256,
    )
    runner._write_decision_artifact_once(
        "scoring_access_receipt", receipt, artifact_root=tmp_path,
    )
    monkeypatch.setattr(
        runner, "_read_scoring_projection_after_seal",
        lambda **kwargs: pytest.fail(
            "exactly-once scoring source was reopened"
        ),
    )
    with pytest.raises(
        runner.ManualReconciliationRequired,
        match="scoring source was already opened but no durable score exists",
    ):
        runner._ensure_decision_scores(
            h=h, k=k, schedule=(),
            scaler=sh.FeatureScaler((0, 0, 0, 0), (1, 1, 1, 1), 1520,
                                    sh.TRAINING_SEASONS),
            beta=np.zeros(8), prediction_seal_record=seal_record,
            prediction_rows=predictions, artifact_root=tmp_path,
        )


# ==========================================================================
# Amendment 3: the sandbox feeds its prisoner — capability grants, monitor
# rewrite, smoke gate, disposition, and the H''-parent re-binding.
# ==========================================================================
_A3_PLIST = "/System/Library/CoreServices/SystemVersion.plist"
_A3_SIBLING = "/System/Library/CoreServices/iOSSystemVersion.plist"
_A3_LD_CLASSIC = "/Library/Developer/CommandLineTools/usr/bin/ld-classic"
_A3_DSYMUTIL = "/Library/Developer/CommandLineTools/usr/bin/dsymutil"


def test_amendment_3_bindings_are_frozen_into_both_modules():
    assert sh.AMENDMENT_3_COMMIT == "ca169ef4490059a2672ae38f08aff157eeff3717"
    assert sh.AMENDMENT_3_TREE == "dbb6b5bf5d8ccfe0b9387bc95ef6d527da321234"
    assert sh.AMENDMENT_3_PATH == "reports/epl_shots_prereg_amendment_3.md"
    assert sh.AMENDMENT_3_SHA256 == (
        "015ad8d08d08fb4e361d1e0c1252190da673b8a1fbd0b1f21d8683ecc8293fca"
    )
    on_disk = (paths.REPO_ROOT / sh.AMENDMENT_3_PATH).read_bytes()
    assert hashlib.sha256(on_disk).hexdigest() == sh.AMENDMENT_3_SHA256
    subject = sh._expected_receipt_subject({
        "files": {}, "freeze_parent_commit": "0" * 40,
        "freeze_parent_tree": "0" * 40, "native_contract": {},
    })
    assert subject["amendment_3_commit"] == sh.AMENDMENT_3_COMMIT
    assert subject["amendment_3_sha256"] == sh.AMENDMENT_3_SHA256
    assert subject["schema"] == "epl-shots-pre-h-subject-4"


def test_h_freeze_parent_gates_bind_amendment_3():
    status = sh.harness_manifest_status(
        {"freeze_parent_commit": sh.AMENDMENT_2_COMMIT,
         "freeze_parent_tree": sh.AMENDMENT_2_TREE},
        repo_root=paths.REPO_ROOT,
    )
    assert "freeze_parent_commit is not the Amendment 3 governance commit" \
        in status["issues"]
    assert "freeze_parent_tree is not the Amendment 3 governance tree" \
        in status["issues"]
    with pytest.raises(sh.LockMismatch, match="Amendment 3"):
        sh.make_harness_manifest(
            repo_root=paths.REPO_ROOT,
            freeze_parent_commit=sh.AMENDMENT_2_COMMIT,
            freeze_parent_tree=sh.AMENDMENT_2_TREE,
            canary_receipts={}, audit_receipt={}, smoke_receipt={},
        )


def test_h_prime_record_is_pinned_and_parent_gate_reads_it():
    assert sh.H_PRIME_COMMIT == "3bcc893e8cef73a2e43abd43d3c48f9091e911c5"
    assert sh.H_PRIME_MANIFEST_SHA256 == (
        "0e907e61e2135e36195f902c65b220ae465bb186a06dc2b9dcdc62e195f60c16"
    )
    # The Amendment 3 governance commit lawfully carries exactly the H'-era
    # freeze record and passes.
    assert sh._pre_h_parent_issues(
        paths.REPO_ROOT, sh.AMENDMENT_3_COMMIT,
    ) == []
    # A parent without the H' record (Amendment 1's artifact-free tree) is
    # not a lawful H'' parent under the Amendment 3 geometry.
    issues = sh._pre_h_parent_issues(paths.REPO_ROOT, sh.AMENDMENT_1_COMMIT)
    assert issues, "artifact-free parent must now fail the H'-record gate"
    assert any("H'" in issue for issue in issues)


def test_native_contract_grants_exact_system_read_literals():
    contract = runner._native_sandbox_contract()
    assert contract["system_read_literals"] == [_A3_PLIST]
    lock_records = contract["runtime_closure"]["system_read_literals"]
    assert [record["logical_path"] for record in lock_records] == [_A3_PLIST]
    record = lock_records[0]
    assert record["link_chain"] == []
    assert record["resolved_path"] == _A3_PLIST
    assert len(record["sha256"]) == 64
    assert record["bytes"] > 0
    profile = runner._native_sandbox_profile(
        contract=contract, temporary_root=Path("/private/tmp/a3-job"),
        parent_root=Path("/private/tmp/a3-job/parent"),
        request_path=Path("/private/tmp/a3-job/request.json"),
        runtime_root=Path("/private/tmp/a3-job/runtime"),
        resolve_live_paths=False,
    )
    assert f'(literal "{_A3_PLIST}")' in profile
    assert '(subpath "/System")' not in profile
    assert '(subpath "/System/Library")' not in profile
    assert f'(subpath "{_A3_PLIST}")' not in profile
    read_block = profile.split("(allow file-read-data", 1)[1]
    assert f'(literal "{_A3_PLIST}")' in read_block


def test_native_contract_selects_hash_bound_ld_classic_and_dsymutil():
    contract = runner._native_sandbox_contract()
    tools = contract["compiler_paths"]
    assert tools["ld-classic"] == _A3_LD_CLASSIC
    assert tools["dsymutil"] == _A3_DSYMUTIL
    assert _A3_LD_CLASSIC in contract["process_exec_paths"]
    assert _A3_DSYMUTIL in contract["process_exec_paths"]
    executables = {
        record["logical_path"]: record
        for record in contract["runtime_closure"]["executables"]
    }
    for path in (_A3_LD_CLASSIC, _A3_DSYMUTIL):
        assert path in executables
        assert len(executables[path]["sha256"]) == 64
    profile = runner._native_sandbox_profile(
        contract=contract, temporary_root=Path("/private/tmp/a3-job"),
        parent_root=Path("/private/tmp/a3-job/parent"),
        request_path=Path("/private/tmp/a3-job/request.json"),
        runtime_root=Path("/private/tmp/a3-job/runtime"),
        resolve_live_paths=False,
    )
    exec_block = profile.split("(allow process-exec", 1)[1].split("\n)\n", 1)[0]
    assert f'(literal "{_A3_LD_CLASSIC}")' in exec_block
    assert f'(literal "{_A3_DSYMUTIL}")' in exec_block


def test_native_profile_confines_generated_exec_to_runtime_tmp():
    contract = runner._native_sandbox_contract()
    assert contract["generated_process_exec_subtree"] == "runtime_tmp"
    profile = runner._native_sandbox_profile(
        contract=contract, temporary_root=Path("/private/tmp/a3-job"),
        parent_root=Path("/private/tmp/a3-job/parent"),
        request_path=Path("/private/tmp/a3-job/request.json"),
        runtime_root=Path("/private/tmp/a3-job/runtime"),
        resolve_live_paths=False,
    )
    exec_block = profile.split("(allow process-exec", 1)[1].split("\n)\n", 1)[0]
    assert '(subpath "/private/tmp/a3-job/runtime/tmp")' in exec_block
    assert '(subpath "/private/tmp/a3-job/runtime")' not in exec_block
    assert '(subpath "/private/tmp/a3-job")' not in exec_block


def test_native_profile_grants_exact_dev_null_write_only():
    contract = runner._native_sandbox_contract()
    profile = runner._native_sandbox_profile(
        contract=contract, temporary_root=Path("/private/tmp/a3-job"),
        parent_root=Path("/private/tmp/a3-job/parent"),
        request_path=Path("/private/tmp/a3-job/request.json"),
        runtime_root=Path("/private/tmp/a3-job/runtime"),
        resolve_live_paths=False,
    )
    assert '(allow file-write-data\n  (literal "/dev/null")\n)' in profile
    write_rules = [
        line for line in profile.splitlines()
        if line.startswith("(allow file-write* ")
    ]
    assert write_rules == [
        '(allow file-write* (subpath "/private/tmp/a3-job/runtime"))',
    ]


def test_native_environment_pins_both_compiledirs():
    contract = runner._native_sandbox_contract()
    runtime_root = Path("/private/tmp/a3-job/runtime")
    environment = runner._native_environment_values(
        contract=contract, parent_root=Path("/private/tmp/a3-job/parent"),
        request_path=Path("/private/tmp/a3-job/request.json"),
        runtime_root=runtime_root,
    )
    assert environment["PYTENSOR_FLAGS"] == (
        f"base_compiledir={runtime_root / 'pytensor'},"
        f"compiledir={runtime_root / 'pytensor' / 'compiled'},"
        f"cxx={contract['compiler_paths']['clang++']}"
    )


def test_native_worker_sources_assert_cold_compiledir():
    for source in (runner._NATIVE_WORKER_SOURCE,
                   runner._SMOKE_WORKER_SOURCE):
        assert "pytensor/compiled" in source
        assert "compiledir is not cold" in source


def _a3_monitor_process(pid=123):
    class Process:
        def __init__(self):
            self.pid = pid
            self.returncode = None

        def poll(self):
            pytest.fail("poll would reap the process-group leader")

    return Process()


def _a3_monitor_run(monkeypatch, outputs, *, returncodes=None):
    """Feed successive group-scoped ps snapshots to the rewritten monitor."""
    calls = []
    codes = list(returncodes or [0] * len(outputs))

    def fake_run(*args, **kwargs):
        ordinal = len(calls)
        calls.append((args, kwargs))

        class Completed:
            returncode = codes[min(ordinal, len(codes) - 1)]
            stdout = outputs[min(ordinal, len(outputs) - 1)]
            stderr = b""

        return Completed()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: None)
    return calls


def test_native_process_group_monitor_takes_one_group_scoped_snapshot(
    monkeypatch,
):
    calls = _a3_monitor_run(
        monkeypatch, [b" 123  123 Ss   3040\n 200  123 R     512\n"],
    )
    state = runner._native_process_group_state(_a3_monitor_process())
    assert calls[0][0][0] == (
        "/bin/ps", "-o", "pid=,pgid=,stat=,rss=", "-g", "123",
    )
    assert len(calls) == 1
    assert state.leader_exited is False
    assert state.nonleader_pids == (200,)
    assert state.rss_bytes == (3040 + 512) * 1_024
    # ownership and RSS come from the same single snapshot
    assert runner._native_process_group_rss_bytes(
        _a3_monitor_process()
    ) == (3040 + 512) * 1_024


def test_native_process_group_monitor_rejects_a_foreign_pgid_row(monkeypatch):
    _a3_monitor_run(
        monkeypatch, [b" 123  123 Ss   3040\n 999  998 R     512\n"] * 4,
    )
    with pytest.raises(
        runner.NativeWorkerIOFailure, match="foreign process-group row",
    ):
        runner._native_process_group_state(_a3_monitor_process())


def test_native_process_group_monitor_treats_halted_as_live(monkeypatch):
    _a3_monitor_run(monkeypatch, [b" 123  123 H    3040\n"])
    state = runner._native_process_group_state(_a3_monitor_process())
    assert state.leader_exited is False
    assert state.nonleader_pids == ()


def test_native_process_group_monitor_retries_indeterminate_then_fails(
    monkeypatch,
):
    calls = _a3_monitor_run(
        monkeypatch, [b" 123  123 ?    0\n"] * 8,
    )
    with pytest.raises(
        runner.NativeWorkerIOFailure, match="indeterminate",
    ):
        runner._native_process_group_state(_a3_monitor_process())
    assert len(calls) == runner._NATIVE_MONITOR_STATE_RETRIES + 1

    recovered = _a3_monitor_run(monkeypatch, [
        b" 123  123 ?    0\n",
        b" 123  123 Ss   3040\n",
    ])
    state = runner._native_process_group_state(_a3_monitor_process())
    assert state.leader_exited is False and state.rss_bytes == 3040 * 1_024
    assert len(recovered) == 2


def test_native_process_group_monitor_treats_suffixed_unknown_as_indeterminate(
    monkeypatch,
):
    """Apple's ps prints '?' with ordinary flag suffixes (observed '?Es').

    The first live smoke qualification hit exactly this row mid-exec; a
    suffixed unknown state is the same indeterminate reading as a bare '?',
    so it retries and then fails closed rather than failing as malformed.
    """
    recovered = _a3_monitor_run(monkeypatch, [
        b" 123  123 ?Es  0\n 200  123 R    512\n",
        b" 123  123 Ss   3040\n 200  123 R    512\n",
    ])
    state = runner._native_process_group_state(_a3_monitor_process())
    assert state.leader_exited is False
    assert state.rss_bytes == (3040 + 512) * 1_024
    assert len(recovered) == 2

    exhausted = _a3_monitor_run(monkeypatch, [b" 123  123 ?E   0\n"] * 8)
    with pytest.raises(
        runner.NativeWorkerIOFailure, match="indeterminate",
    ):
        runner._native_process_group_state(_a3_monitor_process())
    assert len(exhausted) == runner._NATIVE_MONITOR_STATE_RETRIES + 1
    # a genuinely foreign spelling is still malformed, with no retry
    malformed = _a3_monitor_run(monkeypatch, [b" 123  123 ZOMBIE 0\n"] * 4)
    with pytest.raises(
        runner.NativeWorkerIOFailure, match="malformed",
    ):
        runner._native_process_group_state(_a3_monitor_process())
    assert len(malformed) == 1


def test_native_process_group_monitor_retries_live_zero_rss_then_fails(
    monkeypatch,
):
    calls = _a3_monitor_run(monkeypatch, [b" 123  123 R    0\n"] * 8)
    with pytest.raises(
        runner.NativeWorkerIOFailure, match="indeterminate",
    ):
        runner._native_process_group_state(_a3_monitor_process())
    assert len(calls) == runner._NATIVE_MONITOR_STATE_RETRIES + 1
    # a zombie leader with zero RSS is determinate, not a retry case
    _a3_monitor_run(monkeypatch, [b" 123  123 Z    0\n"])
    state = runner._native_process_group_state(_a3_monitor_process())
    assert state.leader_exited is True and state.rss_bytes == 0


def test_native_process_group_monitor_diagnostics_are_bounded(monkeypatch):
    noise = b" 123  123 Ss   3040\n" + b"x" * 100_000 + b"\n"
    _a3_monitor_run(monkeypatch, [noise] * 4)
    with pytest.raises(runner.NativeWorkerIOFailure) as failure:
        runner._native_process_group_state(_a3_monitor_process())
    assert len(str(failure.value)) < 4_096


def test_native_process_group_monitor_launch_validates_own_group_selector(
    monkeypatch,
):
    runner._require_native_process_group_monitor()

    class Completed:
        returncode = 0
        stdout = b" 1  2 Ss   10\n"
        stderr = b""

    monkeypatch.setattr(
        runner.subprocess, "run", lambda *args, **kwargs: Completed(),
    )
    with pytest.raises(
        runner.NativeWorkerIOFailure,
        match="ownership monitor",
    ):
        runner._require_native_process_group_monitor()


def test_native_wait_uses_one_snapshot_per_poll_for_state_and_rss(monkeypatch):
    process = _a3_monitor_process()
    states = iter((
        runner._NativeProcessGroupState(123, 123, False, (), 2_048),
        runner._NativeProcessGroupState(123, 123, True, (), 1_024),
    ))
    snapshots = []

    def state(_process):
        value = next(states)
        snapshots.append(value)
        return value

    monkeypatch.setattr(runner, "_native_process_group_state", state)
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: None)
    observed = {"rss_bytes": 0}
    runner._wait_native_process_with_rss_limit(
        process, timeout_seconds=5, observed=observed,
    )
    assert len(snapshots) == 2
    assert observed["rss_bytes"] == 2_048

    process = _a3_monitor_process()
    monkeypatch.setattr(
        runner, "_native_process_group_state",
        lambda _process: runner._NativeProcessGroupState(
            123, 123, False, (), runner._NATIVE_RSS_LIMIT_BYTES + 1,
        ),
    )
    with pytest.raises(
        runner.NativeWorkerIOFailure, match="resident-memory limit",
    ):
        runner._wait_native_process_with_rss_limit(process, timeout_seconds=5)


def test_experiment_transaction_lock_refuses_foreign_h_without_touching_it(
    tmp_path,
):
    foreign = (
        "epl-shots-experiment-transaction-lock-1\n"
        + sh.H_PRIME_COMMIT + "\n" + sh.H_PRIME_MANIFEST_SHA256 + "\n"
    ).encode("ascii")
    lock_path = tmp_path / ".experiment-transaction.lock"
    lock_path.write_bytes(foreign)
    os.chmod(lock_path, 0o444)
    h = runner._VerifiedH("a" * 40, "b" * 64, "c" * 64, "d" * 64)
    with pytest.raises(
        sh.LockMismatch, match="experiment transaction lock bytes differ",
    ):
        with runner._experiment_transaction_lock(
            h=h, artifact_root=tmp_path,
        ):
            pytest.fail("a foreign H'-era transaction claim must refuse")
    assert lock_path.read_bytes() == foreign


def test_smoke_receipt_validator_binds_candidates_amendment_and_lock():
    receipt = runner._make_example_smoke_receipt_for_tests()
    files = {
        relative: {"sha256": record["sha256"], "bytes": 1, "lines": 1}
        for relative, record in receipt["candidate_files"].items()
    }
    lock_sha256 = receipt["native_runtime_lock_sha256"]
    sh._validate_smoke_receipt(
        receipt, files=files, native_runtime_lock_sha256=lock_sha256,
    )
    for corruption, note in (
        ({"passed": False}, "did not pass"),
        ({"amendment_3_commit": "f" * 40}, "Amendment 3"),
        ({"amendment_3_sha256": "f" * 64}, "Amendment 3"),
        ({"native_runtime_lock_sha256": "f" * 64}, "runtime lock"),
        ({"schema": "epl-shots-h-candidate-smoke-receipt-0"}, "schema"),
    ):
        broken = {**receipt, **corruption}
        with pytest.raises(sh.LockMismatch, match=note):
            sh._validate_smoke_receipt(
                broken, files=files,
                native_runtime_lock_sha256=lock_sha256,
            )
    stale = json.loads(json.dumps(receipt))
    stale["candidate_files"]["epl/shots.py"]["sha256"] = "f" * 64
    with pytest.raises(sh.LockMismatch, match="stale"):
        sh._validate_smoke_receipt(
            stale, files=files, native_runtime_lock_sha256=lock_sha256,
        )
    with pytest.raises(sh.LockMismatch, match="negative"):
        sabotaged = json.loads(json.dumps(receipt))
        sabotaged["containment_negatives"]["checkout_read"] = "allowed"
        sh._validate_smoke_receipt(
            sabotaged, files=files, native_runtime_lock_sha256=lock_sha256,
        )


def test_harness_manifest_machinery_requires_the_smoke_receipt():
    assert "smoke_receipt" in inspect.signature(
        sh.make_harness_manifest
    ).parameters
    required = inspect.signature(sh.make_harness_manifest).parameters[
        "smoke_receipt"
    ]
    assert required.default is inspect.Parameter.empty
    assert sh.H_MANIFEST_SCHEMA == "epl-shots-harness-manifest-5"
    status = sh.harness_manifest_status(
        {"freeze_parent_commit": sh.AMENDMENT_3_COMMIT,
         "freeze_parent_tree": sh.AMENDMENT_3_TREE},
        repo_root=paths.REPO_ROOT,
    )
    assert any("smoke_receipt" in issue for issue in status["issues"])


def test_run_smoke_qualification_is_wired_as_a_public_entry():
    assert callable(runner.run_smoke_qualification)
    parameters = inspect.signature(runner.run_smoke_qualification).parameters
    assert "receipt_path" in parameters
