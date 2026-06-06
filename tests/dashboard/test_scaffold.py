from wcmodel.dashboard import DRY_RUN_BANNER
from wcmodel.config import load_config


def test_dashboard_banner_is_unmistakably_non_real():
    assert "DRY-RUN" in DRY_RUN_BANNER and "NOT REAL" in DRY_RUN_BANNER.upper()


def test_dashboard_config_block_present():
    d = load_config()["dashboard"]
    assert d["dry_run"] is True
    assert isinstance(d["output_dir"], str) and d["output_dir"]
