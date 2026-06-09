from wcmodel.config import load_config

def test_strength_prior_defaults():
    sp = load_config()["model"]["strength_prior"]
    assert sp["enabled"] is False          # OFF by default -> today's behavior preserved
    assert sp["source"] == "elo"
    assert sp["k_att"] == 0.30 and sp["k_def"] == 0.30
