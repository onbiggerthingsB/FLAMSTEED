from pathlib import Path
import numpy as np
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_PATH = _REPO_ROOT / "config" / "config.yaml"


def load_config(path: Path | None = None) -> dict:
    with open(path or _CONFIG_PATH) as f:
        return yaml.safe_load(f)


def get_rng(spawn_key: int | None = None) -> np.random.Generator:
    """Seeded, parallel-safe RNG via SeedSequence spawning (north-star §4.4)."""
    seed = load_config()["seed"]
    ss = np.random.SeedSequence(seed)
    if spawn_key is not None:
        ss = ss.spawn(spawn_key + 1)[spawn_key]
    return np.random.default_rng(ss)
