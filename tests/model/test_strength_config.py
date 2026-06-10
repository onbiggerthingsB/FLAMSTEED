from wcmodel.config import load_config

def test_strength_prior_calibrated_on():
    sp = load_config()["model"]["strength_prior"]
    assert sp["enabled"] is True           # calibrated ON: beats old model + Elo on held-out 1X2 RPS
    assert sp["source"] == "elo"
    assert sp["k_att"] == 0.6 and sp["k_def"] == 0.6   # knee of the RPS plateau (scripts/sweep_strength_k.py)


def test_k_squad_defaults_off():
    """P3 v0: the squad anchor weight ships at 0.0 (OFF == byte-identical to the
    pre-squad model) until the pre-registered sweep adopts >0 at the knee. No
    squad_tag is wired by default, so the squad path reads nothing."""
    sp = load_config()["model"]["strength_prior"]
    assert sp["k_squad"] == 0.0
    assert "squad_tag" not in sp or not sp.get("squad_tag")
