"""No-fit adversarial tests for EPL walk-forward evidence integrity."""

from __future__ import annotations

import hashlib
import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from epl import freeze, holdout, walkforward as wf


HASHES = {
    "code_sha256": "1" * 64,
    "data_sha256": "2" * 64,
    "store_sha256": "3" * 64,
    "config_sha256": "4" * 64,
    "dependencies_sha256": "5" * 64,
}


@pytest.fixture(autouse=True)
def _cheap_computed_identity(monkeypatch):
    """Avoid scanning the repo; sources still identify as computed, not supplied."""
    monkeypatch.setattr(
        wf, "_identity_hashes",
        lambda **kwargs: (dict(HASHES), {k: "computed" for k in HASHES}))


def _matches(n: int = 2) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append({
            "match_id": f"m{i + 1}", "season": "2019/20",
            "date": pd.Timestamp("2019-08-10") + pd.Timedelta(days=7 * i),
            "kickoff": pd.NaT, "home_key": f"home_{i}",
            "away_key": f"away_{i}", "played": True,
        })
    return pd.DataFrame(rows)


def _cut(i: int = 0) -> wf.Cutoff:
    date = pd.Timestamp("2019-08-10") + pd.Timedelta(days=7 * i)
    return wf.Cutoff(season="2019/20", matchweek=i, cutoff=date,
                     rows=np.array([i]), match_ids=(f"m{i + 1}",))


def _row(cut: wf.Cutoff, probs=None, **updates):
    row = {
        "key": cut.key, "season": cut.season,
        "matchweek": cut.matchweek, "cutoff": str(cut.cutoff.date()),
        "n_fixtures": len(cut.match_ids), "match_ids": list(cut.match_ids),
        "probs": probs or [[0.4, 0.3, 0.3]], "seconds": 0.0,
        "n_training_matches": 10, "n_teams": 2,
        "cold_start_teams": [], "cold_start_z": {},
        "provisional_teams": [], "anchor_spec": "test",
        "warnings": [], "unpriceable": [], "malformed": [],
        "health": {"all_finite": True, "sigma_positive": True,
                   "home_adv_sane": True},
        "cadence_weeks": 1, "off_protocol": False, "fast_panel": False,
        "record_type": "cutoff",
    }
    row.update(updates)
    return row


def _commit_schedule(tmp_path, monkeypatch, matches, cuts):
    schedule = wf._schedule_payload(cuts)
    source_matches = tmp_path / "source_matches.parquet"
    source_ledger = tmp_path / "source_ledger.jsonl"
    source_matches.write_bytes(b"fixed matches source")
    source_ledger.write_bytes(b"fixed ledger source")
    manifest = {
        "schema": wf.SCHEDULE_MANIFEST_SCHEMA,
        "n_cutoffs": len(schedule),
        "n_fixtures": sum(len(c.match_ids) for c in cuts),
        "schedule_sha256": wf._json_sha256(schedule),
        "source": {
            "played_frame_sha256": wf._frame_sha256(matches),
            "matches_parquet": {
                "path": str(source_matches),
                "sha256": hashlib.sha256(source_matches.read_bytes()).hexdigest(),
            },
            "source_ledger": {
                "path": str(source_ledger),
                "sha256": hashlib.sha256(source_ledger.read_bytes()).hexdigest(),
            },
        },
        "schedule": schedule,
    }
    path = tmp_path / "schedule.json"
    path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
    monkeypatch.setattr(wf, "SCHEDULE_MANIFEST_PATH", path)
    monkeypatch.setattr(
        wf, "EXPECTED_SCHEDULE_MANIFEST_SHA256", wf._file_sha256(path))
    monkeypatch.setattr(wf, "EXPECTED_PUBLISHABLE_CUTOFFS", len(cuts))
    monkeypatch.setattr(
        wf, "EXPECTED_PUBLISHABLE_FIXTURES",
        sum(len(c.match_ids) for c in cuts))
    return path


def _envelope(matches, cuts, *, publishable=True, manifest_path=None):
    return wf._build_run_envelope(
        played=matches, cfg=freeze.frozen_wcmodel_config(),
        elo_cfg=freeze.frozen_elo_config(), eligible_cuts=cuts,
        run_cuts=cuts, cadence=1, seed=None, fast_panel=False,
        publishable=publishable, identity_hashes=None,
        schedule_manifest_sha256=(
            wf._file_sha256(manifest_path) if manifest_path else None))


def _write_ledger(path, envelope, rows, *, seal=True):
    digest = wf._json_sha256(envelope)
    header = wf._chain_record({
        "record_type": "run_envelope", "run_envelope": envelope,
        "run_envelope_sha256": digest})
    records = [header]
    previous = header["record_sha256"]
    for row in rows:
        chained = wf._chain_record(
            {**row, "record_type": "cutoff",
             "run_envelope_sha256": digest}, previous)
        records.append(chained)
        previous = chained["record_sha256"]
    if seal:
        records.append(wf._chain_record({
            "record_type": "terminal_seal",
            "run_envelope_sha256": digest,
            "n_cutoffs": len(rows),
            "n_fixtures": sum(len(r.get("match_ids", [])) for r in rows),
            "run_schedule_sha256": envelope["run_schedule_sha256"],
            "cutoff_chain_sha256": previous,
        }, previous))
    path.write_text("".join(wf._canonical_json(r) + "\n" for r in records))
    return wf.load_ledger(path)


def _baseline_frame(n=2):
    p = np.tile(np.array([[0.5, 0.25, 0.25]]), (n, 1))
    y = np.resize(np.array([0, 2]), n)
    rps = wf.score_mod.rps(p, y)
    frame = pd.DataFrame({
        "match_id": [f"m{i + 1}" for i in range(n)], "y": y,
        "block": [f"2019/20|2019W{32 + i}" for i in range(n)],
        "season": ["2019/20"] * n,
        "home_promoted": [False] * n, "away_promoted": [False] * n,
    })
    for name in ("elo", "market", "market_shin", "base"):
        frame[f"{name}_home"] = p[:, 0]
        frame[f"{name}_draw"] = p[:, 1]
        frame[f"{name}_away"] = p[:, 2]
        frame[f"{name}_rps"] = rps
    return frame


def test_publishable_entry_points_refuse_supplied_identity_hashes():
    matches, cut = _matches(1), _cut(0)
    with pytest.raises(wf.VerdictPublicationBlocked,
                       match="supplied_identity_hashes"):
        wf._build_run_envelope(
            played=matches, cfg={}, elo_cfg={}, eligible_cuts=[cut],
            run_cuts=[cut], cadence=1, seed=None, fast_panel=False,
            publishable=True, identity_hashes=HASHES)
    with pytest.raises(wf.VerdictPublicationBlocked,
                       match="supplied_identity_hashes"):
        wf.run_walk(matches=matches, identity_hashes=HASHES, verbose=False)
    with pytest.raises(wf.VerdictPublicationBlocked,
                       match="supplied_identity_hashes"):
        wf.score_run(ledger=[], matches=matches, identity_hashes=HASHES)


def test_resume_refuses_different_computed_identity_before_another_fit(
        tmp_path, monkeypatch):
    matches, cut = _matches(1), _cut(0)
    manifest = _commit_schedule(tmp_path, monkeypatch, matches, [cut])
    monkeypatch.setattr(wf, "matchweek_cutoffs", lambda *a, **k: [cut])
    current = dict(HASHES)
    monkeypatch.setattr(
        wf, "_identity_hashes",
        lambda **kwargs: (dict(current), {k: "computed" for k in current}))
    calls = {"store": 0, "fit": 0}
    logical = pd.DataFrame({"match_id": ["m1"]})
    monkeypatch.setattr(wf.epl_fit, "to_store_frame", lambda played: logical)

    def build_store(_played):
        calls["store"] += 1
        root = tmp_path / "store"
        root.mkdir(exist_ok=True)
        logical.to_parquet(root / "results.parquet")
        return SimpleNamespace(root=root)

    def one_cutoff(c, *args, **kwargs):
        calls["fit"] += 1
        return _row(c)

    monkeypatch.setattr(wf.epl_fit, "build_store", build_store)
    monkeypatch.setattr(wf.anchor_mod, "Anchor", lambda *a, **k: object())
    monkeypatch.setattr(wf, "_one_cutoff", one_cutoff)
    path = tmp_path / "walk.jsonl"

    first = wf.run_walk(matches=matches, ledger_path=path, fast_panel=False,
                        resume=True, verbose=False)
    assert first["n_run"] == 1
    assert calls == {"store": 1, "fit": 1}
    assert wf.load_ledger(path).run_envelope["identity_sources"] == {
        k: "computed" for k in HASHES}

    same = wf.run_walk(matches=matches, ledger_path=path, fast_panel=False,
                       resume=True, verbose=False)
    assert same["n_run"] == 0
    assert calls == {"store": 1, "fit": 1}

    current["code_sha256"] = "a" * 64
    with pytest.raises(wf.ResumeIdentityMismatch, match="code_sha256"):
        wf.run_walk(matches=matches, ledger_path=path, fast_panel=False,
                    resume=True, verbose=False)
    assert calls == {"store": 1, "fit": 1}
    assert manifest.is_file()


def test_legacy_compatibility_is_read_only(tmp_path, monkeypatch):
    matches, cut = _matches(1), _cut(0)
    path = tmp_path / "legacy.jsonl"
    original = json.dumps(_row(cut)) + "\n"
    path.write_text(original)
    with pytest.raises(wf.EvidenceIntegrityError, match="allow_legacy=True"):
        wf.load_ledger(path)
    assert len(wf.load_ledger(path, allow_legacy=True)) == 1
    monkeypatch.setattr(wf, "matchweek_cutoffs", lambda *a, **k: [cut])
    with pytest.raises(wf.EvidenceIntegrityError, match="strictly read-only"):
        wf.run_walk(matches=matches, ledger_path=path, fast_panel=False,
                    publishable=False, identity_hashes=HASHES, verbose=False)
    assert path.read_text() == original


def test_load_refuses_duplicate_cutoff_or_fixture(tmp_path):
    matches, a, b = _matches(2), _cut(0), _cut(1)
    envelope = _envelope(matches, [a, b], publishable=False)
    path = tmp_path / "walk.jsonl"
    _write_ledger(path, envelope, [_row(a)], seal=False)
    records = [json.loads(x) for x in path.read_text().splitlines()]
    duplicate = wf._chain_record(
        {**_row(a), "run_envelope_sha256": wf._json_sha256(envelope)},
        records[-1]["record_sha256"])
    path.write_text(path.read_text() + wf._canonical_json(duplicate) + "\n")
    with pytest.raises(wf.EvidenceIntegrityError, match="duplicate cutoff key"):
        wf.load_ledger(path)

    second = _row(b, match_ids=[a.match_ids[0]])
    other = tmp_path / "fixture.jsonl"
    with pytest.raises(wf.EvidenceIntegrityError, match="priced exactly once"):
        _write_ledger(other, envelope, [_row(a), second], seal=False)


def test_valid_looking_row_mutation_breaks_hash_chain(tmp_path):
    matches, cut = _matches(1), _cut(0)
    envelope = _envelope(matches, [cut], publishable=False)
    path = tmp_path / "walk.jsonl"
    _write_ledger(path, envelope, [_row(cut)])
    records = [json.loads(x) for x in path.read_text().splitlines()]
    records[1]["probs"] = [[0.5, 0.25, 0.25]]
    path.write_text("".join(wf._canonical_json(r) + "\n" for r in records))
    with pytest.raises(wf.EvidenceIntegrityError, match="record digest mismatch"):
        wf.load_ledger(path)


def test_resume_rejects_a_wrong_persisted_row_before_store_or_fit(
        tmp_path, monkeypatch):
    matches, cut = _matches(1), _cut(0)
    manifest = _commit_schedule(tmp_path, monkeypatch, matches, [cut])
    monkeypatch.setattr(wf, "matchweek_cutoffs", lambda *a, **k: [cut])
    envelope = _envelope(matches, [cut], manifest_path=manifest)
    wrong = _row(cut, match_ids=["different-fixture"])
    path = tmp_path / "walk.jsonl"
    _write_ledger(path, envelope, [wrong], seal=False)
    monkeypatch.setattr(
        wf.epl_fit, "build_store",
        lambda *a, **k: pytest.fail("store built before resume schedule check"))
    with pytest.raises(wf.EvidenceIntegrityError,
                       match="persisted rows do not match"):
        wf.run_walk(matches=matches, ledger_path=path, fast_panel=False,
                    verbose=False)


def test_publishable_score_requires_terminal_seal(tmp_path, monkeypatch):
    matches, cut = _matches(1), _cut(0)
    manifest = _commit_schedule(tmp_path, monkeypatch, matches, [cut])
    monkeypatch.setattr(wf, "matchweek_cutoffs", lambda *a, **k: [cut])
    monkeypatch.setattr(
        wf.baseline, "evaluate",
        lambda *a, **k: SimpleNamespace(frame=_baseline_frame(1)))
    envelope = _envelope(matches, [cut], manifest_path=manifest)
    ledger = _write_ledger(
        tmp_path / "walk.jsonl", envelope, [_row(cut)], seal=False)
    with pytest.raises(wf.VerdictPublicationBlocked) as exc:
        wf.score_run(ledger=ledger, matches=matches, n_boot=10_000)
    assert exc.value.blockers["terminal_seal"] == "missing"


def test_publishable_verdict_requires_committed_complete_schedule(
        tmp_path, monkeypatch):
    matches, cuts = _matches(2), [_cut(0), _cut(1)]
    manifest = _commit_schedule(tmp_path, monkeypatch, matches, cuts)
    monkeypatch.setattr(wf, "matchweek_cutoffs", lambda *a, **k: cuts)
    envelope = _envelope(matches, cuts, manifest_path=manifest)
    ledger = _write_ledger(
        tmp_path / "walk.jsonl", envelope, [_row(cuts[0])], seal=False)
    with pytest.raises(wf.VerdictPublicationBlocked) as exc:
        wf.score_run(ledger=ledger, matches=matches, n_boot=10_000)
    assert "missing_cutoffs" in exc.value.blockers
    assert "missing_forecasts" in exc.value.blockers


def test_publishable_verdict_keeps_bootstrap_count(tmp_path, monkeypatch):
    matches, cut = _matches(1), _cut(0)
    manifest = _commit_schedule(tmp_path, monkeypatch, matches, [cut])
    monkeypatch.setattr(wf, "matchweek_cutoffs", lambda *a, **k: [cut])
    envelope = _envelope(matches, [cut], manifest_path=manifest)
    ledger = _write_ledger(tmp_path / "walk.jsonl", envelope, [_row(cut)])
    with pytest.raises(wf.VerdictPublicationBlocked) as exc:
        wf.score_run(ledger=ledger, matches=matches, n_boot=999)
    assert exc.value.blockers["bootstrap_resamples"] == {
        "required": 10_000, "received": 999}


@pytest.mark.parametrize("row_update, blocker", [
    ({"probs": [[float("nan"), 0.5, 0.5]]}, "nonfinite_forecasts"),
    ({"unpriceable": [{"match_id": "m1", "why": "no club"}]},
     "unpriceable_fixtures"),
    ({"stops": {"fit_failed": True}}, "declared_stop_cutoffs"),
])
def test_any_forecast_stop_blocks_before_scoring(
        tmp_path, monkeypatch, row_update, blocker):
    matches, cut = _matches(1), _cut(0)
    manifest = _commit_schedule(tmp_path, monkeypatch, matches, [cut])
    monkeypatch.setattr(wf, "matchweek_cutoffs", lambda *a, **k: [cut])
    envelope = _envelope(matches, [cut], manifest_path=manifest)
    ledger = _write_ledger(
        tmp_path / "walk.jsonl", envelope, [_row(cut, **row_update)])
    with pytest.raises(wf.VerdictPublicationBlocked) as exc:
        wf.score_run(ledger=ledger, matches=matches, n_boot=10_000)
    assert blocker in exc.value.blockers


def test_false_stop_mapping_is_not_an_active_stop():
    _, blockers, _, _ = wf._collect_predictions([
        _row(_cut(0), stops={"fit_failed": False})])
    assert "declared_stop_cutoffs" not in blockers


def test_manifest_tampering_is_detected(tmp_path, monkeypatch):
    matches, cut = _matches(1), _cut(0)
    path = _commit_schedule(tmp_path, monkeypatch, matches, [cut])
    manifest = json.loads(path.read_text())
    manifest["schedule"][0]["match_ids"] = ["tampered"]
    path.write_text(json.dumps(manifest))
    with pytest.raises(wf.EvidenceIntegrityError,
                       match="pinned digest"):
        wf._load_schedule_manifest()


def test_committed_source_tampering_blocks_publication(tmp_path, monkeypatch):
    matches, cut = _matches(1), _cut(0)
    path = _commit_schedule(tmp_path, monkeypatch, matches, [cut])
    source = json.loads(path.read_text())["source"]["source_ledger"]["path"]
    source_path = Path(source)
    source_path.write_text(source_path.read_text() + "tampered\n")
    _, _, blockers = wf._publication_commitment(matches, [cut])
    assert "committed_source_ledger_mismatch" in blockers


def test_checked_in_commitment_is_exact():
    manifest, _ = wf._load_schedule_manifest(
        wf.paths.REPO_ROOT / "reports" / "epl_walkforward_schedule_v1.json")
    assert manifest["n_cutoffs"] == 212
    assert manifest["n_fixtures"] == 2_280
    assert len({m for r in manifest["schedule"] for m in r["match_ids"]}) == 2_280


def test_development_scoring_and_holdout_second_look_never_publish(monkeypatch):
    matches, cuts = _matches(2), [_cut(0), _cut(1)]
    monkeypatch.setattr(wf, "matchweek_cutoffs", lambda *a, **k: cuts)
    monkeypatch.setattr(
        wf.baseline, "evaluate",
        lambda *a, **k: SimpleNamespace(frame=_baseline_frame(2)))
    result = wf.score_run(ledger=[_row(c) for c in cuts], matches=matches,
                          n_boot=10, publishable=False)
    assert result["verdict"] is None
    assert result["diagnostic_classification"] is not None

    monkeypatch.setattr(
        holdout.walkforward, "load_ledger", lambda *a, **k: [_row(c) for c in cuts])
    monkeypatch.setattr(
        holdout.walkforward, "score_run",
        lambda **kwargs: {**result, "frame": result["frame"]})
    out = holdout.second_look_confirm(n_boot=10)
    assert out["verdict_publishable"] is False
    assert out["verdict_under_v1_rule"] is None
    assert out["diagnostic_classification_under_v1_rule"] is not None


@pytest.mark.skipif(
    not wf.LEDGER_PATH.is_file(),
    reason="the legacy walk-forward ledger lives under gitignored data/ on the "
           "machine that ran the walk; every other test in this module builds "
           "its own synthetic ledger and needs no archive")
def test_checked_in_legacy_artifact_remains_diagnostic_scoreable():
    """The one artifact-reading test in an otherwise synthetic module.

    "checked-in" names the ledger's status in the fit store, not in git: nothing
    under `data/epl/fit/` is tracked. Unguarded, it raised `FileNotFoundError`
    wherever the archive is absent — a test that cannot run reporting as a test
    that failed. The module is not excluded wholesale for it, because the other
    forty-odd tests here are the adversarial no-fit suite and they must keep
    running everywhere.
    """
    ledger = wf.load_ledger(wf.LEDGER_PATH, allow_legacy=True)
    result = wf.score_run(
        ledger=ledger, n_boot=10, publishable=False,
        strict_diagnostic=True)
    assert len(ledger) == 212
    assert result["n_matches"] == result["n_expected"] == 2_280
    assert result["scores"]["dc"]["rps"] == pytest.approx(
        0.20194241066255245, abs=1e-15)
    assert result["gaps"]["dc_minus_market"]["mean"] == pytest.approx(
        0.006524690900523155, abs=1e-15)
    assert result["verdict"] is None
    assert result["diagnostic_integrity_complete"] is True


def test_strict_diagnostic_refuses_partial_evidence(tmp_path, monkeypatch):
    matches, cuts = _matches(2), [_cut(0), _cut(1)]
    _commit_schedule(tmp_path, monkeypatch, matches, cuts)
    monkeypatch.setattr(wf, "matchweek_cutoffs", lambda *a, **k: cuts)
    with pytest.raises(wf.EvidenceIntegrityError,
                       match="strict diagnostic scoring blocked"):
        wf.score_run(ledger=[_row(cuts[0])], matches=matches, n_boot=10,
                     publishable=False, strict_diagnostic=True)


def test_output_writer_refuses_any_clobber(tmp_path):
    result_path = tmp_path / "result.json"
    predictions_path = tmp_path / "predictions.parquet"
    result_path.write_text("historical evidence\n")
    with pytest.raises(wf.EvidenceIntegrityError, match="refusing to overwrite"):
        wf._write_scored_outputs_no_clobber(
            {"ledger_terminal_seal": {"record_sha256": "a" * 64}},
            pd.DataFrame({"x": [1]}), result_path=result_path,
            predictions_path=predictions_path)
    assert result_path.read_text() == "historical evidence\n"
    assert not predictions_path.exists()


def test_output_writer_refuses_resolved_path_aliases(tmp_path):
    target = tmp_path / "same-output"
    with pytest.raises(wf.EvidenceIntegrityError, match="must be distinct"):
        wf._write_scored_outputs_no_clobber(
            {"ledger_terminal_seal": {"record_sha256": "a" * 64}},
            pd.DataFrame({"x": [1]}), result_path=target,
            predictions_path=target)
    assert not target.exists()


def test_output_writer_publishes_two_files_then_external_seal(tmp_path):
    result_path = tmp_path / "result.json"
    predictions_path = tmp_path / "predictions.parquet"
    seal = wf._write_scored_outputs_no_clobber(
        {"ledger_terminal_seal": {"record_sha256": "a" * 64}},
        pd.DataFrame({"x": [1]}), result_path=result_path,
        predictions_path=predictions_path)
    assert seal["result"]["sha256"] == wf._file_sha256(result_path)
    assert seal["predictions"]["sha256"] == wf._file_sha256(predictions_path)
    assert Path(seal["seal_path"]).is_file()


def test_interrupted_output_pair_never_gets_a_terminal_seal(
        tmp_path, monkeypatch):
    result_path = tmp_path / "result.json"
    predictions_path = tmp_path / "predictions.parquet"
    real_link = wf.os.link
    calls = {"n": 0}

    def interrupt_second_link(source, target):
        calls["n"] += 1
        if calls["n"] == 2:
            raise FileExistsError("simulated concurrent publication")
        return real_link(source, target)

    monkeypatch.setattr(wf.os, "link", interrupt_second_link)
    with pytest.raises(wf.EvidenceIntegrityError, match="appeared concurrently"):
        wf._write_scored_outputs_no_clobber(
            {"ledger_terminal_seal": {"record_sha256": "a" * 64}},
            pd.DataFrame({"x": [1]}), result_path=result_path,
            predictions_path=predictions_path)
    assert result_path.is_file()
    assert not predictions_path.exists()
    assert not wf._default_score_seal_path(result_path).exists()


def test_ledger_lock_excludes_a_concurrent_writer(tmp_path):
    path = tmp_path / "walk.jsonl"
    first = wf._acquire_ledger_lock(path)
    try:
        with pytest.raises(wf.EvidenceIntegrityError,
                           match="another process holds"):
            wf._acquire_ledger_lock(path)
    finally:
        wf.fcntl.flock(first.fileno(), wf.fcntl.LOCK_UN)
        first.close()


def test_cli_publishable_walk_defaults_to_new_versioned_ledger(
        monkeypatch, capsys):
    assert inspect.signature(wf.run_walk).parameters["ledger_path"].default == (
        wf.NEXT_LEDGER_PATH)
    called = {}
    monkeypatch.setattr(
        wf, "run_walk", lambda **kwargs: called.update(kwargs) or {"ok": True})
    monkeypatch.setattr(sys, "argv", ["walkforward", "--walk"])
    wf._cli()
    assert called["ledger_path"] == wf.NEXT_LEDGER_PATH
    assert called["publishable"] is True
    assert wf.NEXT_LEDGER_PATH != wf.LEDGER_PATH
    assert "ok" in capsys.readouterr().out
