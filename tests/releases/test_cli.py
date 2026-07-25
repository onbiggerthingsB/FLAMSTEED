"""CLI wiring: loaded by PATH (house pattern), heavy steps monkeypatched."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "build_release.py"


def _load():
    spec = importlib.util.spec_from_file_location("build_release", str(_MODULE_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakePost:
    _idx = {"Senegal": 0, "Mozambique": 1}
    idata = SimpleNamespace(posterior=SimpleNamespace(sizes={"chain": 4, "draw": 1000}))

    def predict_scoreline(self, home, away, neutral=False, max_goals=10, **kw):
        n = max_goals + 1
        return np.full((n, n), 1.0 / (n * n))


class EmptyStore:
    def read(self, name, *, cutoff):
        return pd.DataFrame({"date": []})


def test_latest_result_rejects_empty_store():
    """An empty store must not silently stamp NaT as the freshness date."""
    cli = _load()
    with pytest.raises(ValueError, match="store has no results before cutoff"):
        cli._latest_result(EmptyStore(), pd.Timestamp("2026-09-20T00:00:00Z"))


def test_cli_end_to_end(tmp_path, monkeypatch):
    cli = _load()
    fx = tmp_path / "fx.csv"
    fx.write_text("date,home,away\n2026-09-21,Senegal,Mozambique\n")
    out = tmp_path / "out"
    monkeypatch.setattr(cli, "cached_fit",
                        lambda **kw: (FakePost(), {"cache_hit": True, "key": "k123"}))
    monkeypatch.setattr(cli, "_latest_result", lambda store, cutoff: "2026-09-18")
    rc = cli.main(["--cutoff", "2026-09-20T00:00:00Z", "--fixtures", str(fx),
                   "--label", "Test window", "--store", str(tmp_path),
                   "--out", str(out)])
    assert rc == 0
    payload = json.loads((out / "release.json").read_text())
    assert payload["provenance"]["posterior_key"] == "k123"
    assert payload["n_draws"] == 4000                  # 4 chains x 1000 draws
    assert payload["data_source"]["latest_result"] == "2026-09-18"
    assert (out / "release.html").exists() and (out / "release.csv").exists()
