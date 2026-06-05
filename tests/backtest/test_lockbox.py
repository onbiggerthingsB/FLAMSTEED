import json
import shutil
from pathlib import Path

import pytest

from wcmodel.backtest.lockbox import (
    LockboxRegistry, LockboxUsedError, REGISTRY_PATH,
)

PREREGISTERED_DOF = [
    "elo_k", "elo_volatility_threshold_T", "widening_mechanism",
    "widening_strength", "decay_half_life", "prior_strength",
    "devig_method", "likelihood_dc_vs_bp", "kelly_fraction",
]


@pytest.fixture
def temp_registry(tmp_path):
    """An ISOLATED temp-dir copy of the committed registry, so test evals NEVER
    burn the real single-use flag (synthetic/test evals must not consume it)."""
    dst = tmp_path / "lockbox.json"
    shutil.copy(REGISTRY_PATH, dst)
    return dst


def test_committed_registry_loads_and_boundary_is_frozen():
    """The committed registry loads; the boundary is a pre-registered frozen rule
    (final 18% by date), not a runtime-recomputed convenience."""
    reg = LockboxRegistry.load()                  # the committed config/lockbox.json
    assert reg.lockbox_fraction == 0.18
    assert reg.boundary_rule == "final 18% by date of the odds-covered backtest_window universe"
    # Until the real universe is materialized the cutoff is unresolved (D1: gated).
    assert reg.resolved is False
    assert reg.resolved_cutoff_date is None


def test_preregistered_config_count_is_nine_and_matches_listed_dof():
    """The pre-registered config count is present, equals 9, and matches the 9 DOF
    written down in the registry — the budget the lockbox is judged against."""
    reg = LockboxRegistry.load()
    assert reg.preregistered_config_count == 9
    assert reg.preregistered_dof == PREREGISTERED_DOF
    assert len(reg.preregistered_dof) == reg.preregistered_config_count


def test_single_use_is_physically_enforced_on_disk(temp_registry):
    """First evaluate_on_lockbox(...) succeeds + persists used=true ON DISK; a SECOND
    call — even via a FRESHLY RE-LOADED registry (a new process would see the same
    disk state) — RAISES LockboxUsedError. Enforcement is persisted disk state, not
    an in-memory convention. Uses an isolated temp registry so the committed real
    flag is never consumed."""
    reg = LockboxRegistry.load(path=temp_registry)
    assert reg.used is False

    # First real evaluation succeeds and BURNS the flag on disk.
    result = reg.evaluate_on_lockbox(lambda: {"roi_roi": 0.01, "n_bets": 42})
    assert result["roi_roi"] == 0.01
    assert json.loads(temp_registry.read_text())["used"] is True   # persisted, not just in-memory

    # Second evaluation on the SAME registry object is refused.
    with pytest.raises(LockboxUsedError):
        reg.evaluate_on_lockbox(lambda: {"roi_roi": 0.99})

    # And a freshly RE-LOADED registry (≈ a new process reading the same file) is
    # ALSO refused — proving the refusal is backed by disk state, not memory.
    reg2 = LockboxRegistry.load(path=temp_registry)
    assert reg2.used is True
    with pytest.raises(LockboxUsedError):
        reg2.evaluate_on_lockbox(lambda: {"roi_roi": 0.99})


def test_synthetic_eval_does_not_burn_the_committed_real_flag(temp_registry):
    """Teeth: a test/synthetic eval runs against the ISOLATED temp registry, so the
    committed config/lockbox.json `used` flag stays false (the real single-use shot
    is preserved for the one gated real run)."""
    reg = LockboxRegistry.load(path=temp_registry)
    reg.evaluate_on_lockbox(lambda: {"roi_roi": 0.0})
    committed = json.loads(REGISTRY_PATH.read_text())
    assert committed["used"] is False             # the REAL flag was never consumed
