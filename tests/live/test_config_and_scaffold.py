import importlib

from wcmodel.config import load_config


def test_live_config_block_present_and_typed():
    live = load_config()["live"]
    # The spend/safety gate defaults SAFE: dry-run + signal-only.
    assert live["dry_run"] is True
    assert live["signal_only"] is True
    # Feed-agnostic config (L1 rider b): both keys present, configurable.
    assert live["bookmaker"] == "pinnacle"
    assert live["sharp_benchmark"] == "pinnacle"
    assert live["sport_key"] == "soccer_fifa_world_cup"
    assert live["market"] == "h2h"
    # L4 cadence.
    assert live["refresh"]["matchday"] is True
    assert live["refresh"]["pre_kickoff_minutes"] == 60
    # L1 rider c: a pinned call budget.
    assert live["call_budget"]["max_calls_per_day"] == 480
    assert live["call_budget"]["max_retries"] == 4
    # Scanner config.
    assert live["scan"]["progression_coverage_gated"] is True
    assert live["ledger_path"].endswith(".jsonl")


def test_live_package_imports():
    # The package scaffold exists and imports cleanly (empty marker is enough here).
    mod = importlib.import_module("wcmodel.live")
    assert mod is not None
