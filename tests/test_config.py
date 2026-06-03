from wcmodel.config import load_config, get_rng


def test_config_loads_seed_and_paths():
    cfg = load_config()
    assert cfg["seed"] == 20260611
    assert cfg["paths"]["raw"] == "data/raw"
    assert cfg["elo"]["home_advantage"] == 100.0


def test_rng_is_seeded_and_reproducible():
    a = get_rng().random(3)
    b = get_rng().random(3)
    assert (a == b).all()        # same seed -> identical draws


def test_rng_spawn_is_independent():
    r1 = get_rng(spawn_key=1).random(3)
    r2 = get_rng(spawn_key=2).random(3)
    assert not (r1 == r2).all()  # different streams
