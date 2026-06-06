"""The snapshot orchestrator: runs read(cutoff)->cached_fit->simulate->scan, assembles the
artifacts, GATES each on the schema guards (a violating artifact is never written), stamps
provenance on EVERY file, NaN-sanitizes + stringifies tuple keys, and writes JSON with
allow_nan=False (a stray NaN fails loud, never invalid JSON). A snapshot IS a read(cutoff)
-> leakage-safe by construction; nothing is recomputed at render time.

THE GATE (the discipline made executable). ``build_snapshot`` is the one place every
dashboard artifact passes through before it lands on disk, so the spec's serializer-side
rules are ENFORCED here, never trusted to hold upstream:

  * ``gate_artifact`` is a true STOP — a naked (no uncertainty companion) or incoherent
    (non-monotone progression ladder) team-progression table RAISES before any write, so
    a violating artifact is never persisted (T2 Codex).
  * ``_write`` stamps provenance on EVERY file (T1 Codex), NaN/inf-sanitizes to JSON
    ``null`` (no imputation), and writes with ``allow_nan=False`` so a residual NaN raises
    rather than emitting an invalid ``NaN`` token (T7 review).
  * ``stringify_keys`` makes any event-tuple-keyed dict (e.g. edges) JSON-safe (T4 review).

LEAKAGE-SAFE BY CONSTRUCTION. The heavy compute is delegated to the already-leakage-gated
producers: ``cached_fit``/``simulate`` read ONLY ``store.read(cutoff)`` (the strict
``date < cutoff`` set), so a result observed AFTER the cutoff cannot touch the bundle — the
dashboard-layer analog of the P2-P5 leakage canaries (``test_leakage_dashboard.py``).
``build.py`` itself never reads a raw result or recomputes a number; it only assembles,
GATES, stamps, and writes.

REPRODUCIBLE. ``cached_fit`` is content-addressed + seeded and ``simulate`` is seeded, so
the same ``cutoff`` + ``seed`` yields a byte-identical bundle. The fit cache defaults to a
directory UNDER ``out_root`` (never inside the bundle dir), so two builds into distinct
``out_root``s each run a genuine fresh fit — which is what keeps the leakage canary
NON-VACUOUS (the post-cutoff-mutation build re-fits against the mutated store rather than
short-circuiting on a shared cache hit)."""
from __future__ import annotations

import json
import math
from pathlib import Path

from wcmodel.backtest.walkforward import _sample_is_synthetic
from wcmodel.dashboard.provenance import Provenance, _git_rev, stamp
from wcmodel.dashboard.schema import assert_uncertainty_companion, validate_progression_coherence


def _bundle_is_synthetic(items) -> bool:
    """Fail-safe bundle taint (C2): NON-REAL unless EVERY item is explicitly real.

    A NON-REAL bundle must NEVER read as real (the banner must never be dropped on
    synthetic data), so the taint is the producer-side ANY, not an ``all(...)``: a MIXED
    batch (some synthetic, some not) taints the WHOLE bundle. ``items is None`` (no real
    feed wired) OR an EMPTY batch is synthetic-by-default — there is no explicitly-real
    sample to clear the taint, and the leakage/repro canaries build synthetic brackets
    with ``items=[]`` that must stay stamped NON-REAL. The per-item detector is the
    canonical ``walkforward._sample_is_synthetic`` (handles the wrapper flag AND a
    nested ``_is_synthetic`` marker), reused — never re-implemented."""
    if not items:                       # None OR empty -> no real feed -> synthetic
        return True
    return any(_sample_is_synthetic(it.get("sample", {})) for it in items)


def gate_artifact(team_markets: dict) -> None:
    """Hard gate before writing a team-progression artifact: every probability node carries
    an uncertainty companion AND the coherence ladder holds. Raises on any violation.

    A true STOP (T2 Codex): a naked or incoherent table RAISES here, so ``build_snapshot``
    never reaches ``_write`` for it — a violating artifact is never persisted."""
    for team, node in team_markets.items():
        for market, cell in node.items():
            if isinstance(cell, dict) and "value" in cell:
                assert_uncertainty_companion(cell)
        validate_progression_coherence(
            {m: c["value"] for m, c in node.items()
             if isinstance(c, dict) and c.get("value") is not None}
        )


def sanitize_nans(obj):
    """Recursively replace NaN/inf floats with None so json.dumps(allow_nan=False) is valid
    (no imputation to 0 — a missing value becomes JSON null)."""
    if isinstance(obj, float):
        return None if not math.isfinite(obj) else obj
    if isinstance(obj, dict):
        return {k: sanitize_nans(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_nans(v) for v in obj]
    return obj


def stringify_keys(d: dict) -> dict:
    """JSON-safe tuple keys: an event-key tuple (home, away, date) -> 'home|away|date'."""
    return {("|".join(map(str, k)) if isinstance(k, tuple) else k): v for k, v in d.items()}


def _write(bundle: Path, name: str, payload: dict, prov: Provenance) -> None:
    """Stamp provenance on EVERY file, stringify tuple keys, NaN-sanitize, write with
    allow_nan=False (fail loud on a residual NaN rather than emitting invalid JSON).

    ``stringify_keys`` runs on the payload FIRST so an event-tuple-keyed artifact (e.g.
    ``edges_by_event`` -> ``(home, away, date) -> node``) is JSON-safe before ``json.dumps``
    — without it ``json.dumps`` raises ``TypeError: keys must be str...`` on the tuple key
    (T4 review: ``stringify_keys`` was unit-tested but never wired in here)."""
    env = sanitize_nans(stamp(stringify_keys(payload), prov))
    (bundle / name).write_text(json.dumps(env, indent=2, allow_nan=False))


def build_snapshot(cutoff, *, store, config=None, fit_kwargs=None, items=None,
                   out_root=None, tournament=None) -> Path:
    """Build + write one snapshot bundle for ``cutoff``. Returns the bundle dir. Heavy compute
    is delegated to cached_fit/simulate/scan; build.py only assembles, GATES, stamps, writes.

    ``tournament`` (default ``None`` -> the verified ``config/tournament_2026.yaml``) is
    threaded straight to ``SimConfig`` so a minimal synthetic bracket can be simulated over a
    compact posterior (the leakage/repro canaries pass one; production passes nothing and
    gets the real 48-team draw). Without this hook ``RateBook(posterior)`` would ``KeyError``
    whenever the posterior does not cover every team in the real bracket."""
    from wcmodel.config import load_config
    from wcmodel.model.cache import cached_fit
    from wcmodel.sim.run import SimConfig, simulate

    cfg = config or load_config()
    fk = fit_kwargs or {}
    out_root = Path(out_root or cfg["dashboard"]["output_dir"])
    # The fit cache defaults UNDER out_root (never inside the per-cutoff bundle dir, so the
    # cache files never pollute the JSON bundle). Routing it to out_root means two builds
    # into distinct out_roots each run a fresh fit -> the leakage canary's post-cutoff-
    # mutation build genuinely re-fits against the mutated store instead of short-circuiting
    # on a shared cache hit (non-vacuity). An explicit fit_kwargs["cache_dir"] still wins.
    fit_cache = fk.get("cache_dir", str(out_root / "_fit_cache"))
    posterior, meta = cached_fit(
        cutoff=cutoff, store=store, backend=fk.get("backend", "advi"),
        draws=fk.get("draws", 200), seed=fk.get("seed", cfg["seed"]),
        advi_iters=fk.get("advi_iters", 2000),
        cache_dir=fit_cache, config=cfg,
    )
    sim = simulate(cutoff, posterior, store,
                   SimConfig.from_config(cfg, n_sims=cfg["dashboard"]["n_sims"],
                                         tournament=tournament))

    from wcmodel.dashboard.tournament_view import team_progression
    tournament_view = team_progression(sim)
    gate_artifact(tournament_view)                  # STOP: never write a naked/incoherent table

    # C2: fail-safe taint — NON-REAL unless EVERY item is explicitly real (ANY synthetic
    # or nested-synthetic item taints the whole bundle; items None/empty -> synthetic).
    is_synth = _bundle_is_synthetic(items)
    prov = Provenance(cutoff=str(cutoff), posterior_key=meta["key"], git=_git_rev(),
                      is_synthetic=is_synth, n_sims=sim.n_sims)
    bundle = out_root / str(cutoff).replace(":", "").replace(" ", "T")
    bundle.mkdir(parents=True, exist_ok=True)
    _write(bundle, "tournament.json", tournament_view, prov)
    _write(bundle, "meta.json",
           {"markets": list(next(iter(tournament_view.values())).keys())}
           if tournament_view else {}, prov)
    return bundle
