import json
from pathlib import Path
from wcmodel.value.types import ValueConfig
from wcmodel.config import load_config
import importlib.util
spec = importlib.util.spec_from_file_location("scan_value", "scripts/scan_value.py")
sv = importlib.util.module_from_spec(spec); spec.loader.exec_module(sv)


def test_run_scan_writes_gated_signal_only_bundle(tmp_path):
    events = json.loads(Path("tests/value/fixtures/wc_odds_snapshot.json").read_text())
    out = sv.run_scan(events, cfg=ValueConfig.from_config(load_config()),
                      now="2026-06-08T23:10:00Z", credits_used=6, credits_remaining=19000,
                      out_dir=tmp_path, ledger_path=tmp_path / "ledger.jsonl")
    bundle = json.loads(Path(out).read_text())
    assert bundle["provenance"]["signal_only"] is True and bundle["provenance"]["banner"]
    assert len(bundle["data"]["bettable"]) == 1
    # paper ledger got the one bettable spot, append-only
    lines = (tmp_path / "ledger.jsonl").read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["soft_book"] == "betmgm"
