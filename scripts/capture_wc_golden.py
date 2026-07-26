"""Capture the WC-2026 byte-identity golden hash (Phase-2A Task 0).

Phase 2A makes the tournament pipeline format-configurable. The WC-2026 path is
FROZEN: suites staying green is *necessary but not sufficient* proof, because a
generalization refactor can keep every assertion true while silently perturbing
a probability in the 6th decimal. This script is the oracle that closes that
gap — it runs a seeded simulation of the REAL ``config/tournament_2026.yaml``
draw against a deterministic synthetic 48-team posterior and hashes the full
progression / SE frames.

The panel + fit setup MIRRORS ``tests/sim/test_conditioning_2026.py`` (the
existing real-bracket end-to-end harness) exactly: the same fake mid-groups
cutoff, the same all-1-1-draws pre-cutoff friendly history for every bracket
team, the same ``strength_prior``-off tiny config, and the same ADVI fit call
(``draws=120, seed=0, advi_iters=300``). Only the MC params differ, pinned here:
``n_sims=500, seed=3, max_goals=8``.

``tests/sim/test_wc_golden.py`` loads THIS module by file path and calls
:func:`run_reference_sim`, so the oracle setup exists in exactly one place: the
test cannot drift from the capture, and any change to either the setup or to
production sim behaviour moves the hash and FAILS the test.

Run (from the repo root, on the code whose behaviour you intend to freeze)::

    PYTHONPATH=src .venv/bin/python scripts/capture_wc_golden.py
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pandas as pd

from wcmodel.config import load_config
from wcmodel.data.sources.results import normalize_results
from wcmodel.data.store import BitemporalStore, Policy
from wcmodel.data.tournament import load_tournament
from wcmodel.model.scoreline import fit
from wcmodel.sim.run import SimConfig, simulate

#: Repo root (this file lives in ``scripts/``).
REPO_ROOT = Path(__file__).resolve().parents[1]
#: The REAL 48-team draw — the frozen structure whose output we pin.
REAL_DRAW = REPO_ROOT / "config" / "tournament_2026.yaml"
#: Fake mid-groups cutoff (identical to the conditioning test's).
CUTOFF = "2026-06-15T00:00:00Z"
#: MC params of the golden run (also recorded in the committed JSON).
PARAMS = {"n_sims": 500, "seed": 3, "max_goals": 8}
#: Where the captured hashes live.
GOLDEN_PATH = REPO_ROOT / "tests" / "golden" / "wc2026_sim_golden.json"


def _tiny_cfg() -> dict:
    """Production config with ``strength_prior`` pinned OFF (house pattern for tiny
    synthetic fits) — verbatim from ``tests/sim/test_conditioning_2026.py``."""
    cfg = load_config()
    sp = {**cfg["model"].get("strength_prior", {}), "enabled": False}
    return {**cfg, "model": {**cfg["model"], "strength_prior": sp}}


def _bracket_team_history(teams: list[str]) -> pd.DataFrame:
    """Minimal pre-cutoff friendly history giving EVERY bracket team a couple of
    played matches (all 1-1 draws on unique early-2025 dates) — verbatim from
    ``tests/sim/test_conditioning_2026.py``."""
    d0 = pd.Timestamp("2025-01-01")
    rows = []
    day = 0
    for i, tm in enumerate(teams):
        opp = teams[(i + 1) % len(teams)]
        for _ in range(2):
            day += 1
            rows.append((str((d0 + pd.Timedelta(days=day)).date()), tm, opp, 1, 1,
                         "Friendly", "London", "England", False))
    return pd.DataFrame(rows, columns=[
        "date", "home_team", "away_team", "home_score", "away_score",
        "tournament", "city", "country", "neutral"])


def _write_results(store: BitemporalStore, raw: pd.DataFrame) -> None:
    """Normalize + POINT_IN_TIME write keyed ``match_id`` (the canonical results path)."""
    norm = normalize_results(raw)
    norm["winner_override"] = pd.NA
    store.write("results", norm, policy=Policy.POINT_IN_TIME, keys=["match_id"],
                source="martj42", source_version="test")


def run_reference_sim(tmp_root: str | Path | None = None):
    """Fit the tiny synthetic posterior and sim the REAL bracket -> ``SimResult``.

    Deterministic end-to-end: fixed history, fixed ADVI seed, fixed MC seed. The
    store holds ONLY the synthetic friendlies, so NO bracket fixture is played as
    of the cutoff and nothing is conditioned/fixed — the pure structural path.
    """
    teams = list(load_tournament(REAL_DRAW)["teams"])
    root = Path(tempfile.mkdtemp(dir=tmp_root)) if tmp_root is not None \
        else Path(tempfile.mkdtemp())
    store = BitemporalStore(root=root)
    _write_results(store, _bracket_team_history(teams))

    cfg = _tiny_cfg()
    post = fit(CUTOFF, store, backend="advi", draws=120, seed=0, advi_iters=300,
               config=cfg)
    simcfg = SimConfig(tournament=None, n_sims=PARAMS["n_sims"], seed=PARAMS["seed"],
                       max_goals=PARAMS["max_goals"], et_scale=0.3333,
                       pen_home_prob=0.5, config=cfg)
    return simulate(CUTOFF, post, store, simcfg)


def _sha(df) -> str:
    """SHA-256 over the frame's 12-dp-rounded CSV bytes (index + column order included)."""
    return hashlib.sha256(df.round(12).to_csv().encode()).hexdigest()


def golden_payload(res) -> dict:
    """The committed oracle: both frame hashes, the market column order, the MC params."""
    return {"progression_sha256": _sha(res.progression), "se_sha256": _sha(res.se),
            "columns": list(res.progression.columns), "params": dict(PARAMS)}


def main() -> None:
    res = run_reference_sim()
    golden = golden_payload(res)
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(golden, indent=1) + "\n")
    print(json.dumps(golden["params"]), golden["progression_sha256"][:16])


if __name__ == "__main__":
    main()
