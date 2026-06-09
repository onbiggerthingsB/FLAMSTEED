from wcmodel.config import load_config

def test_strength_prior_calibrated_on():
    sp = load_config()["model"]["strength_prior"]
    assert sp["enabled"] is True           # calibrated ON: beats old model + Elo on held-out 1X2 RPS
    assert sp["source"] == "elo"
    assert sp["k_att"] == 0.6 and sp["k_def"] == 0.6   # knee of the RPS plateau (scripts/sweep_strength_k.py)
