"""The gated operator CLI for the v1 dashboard (spec §D5).

POSTURE: v1 is a SYNTHETIC DRY-RUN — a NON-REAL bundle built on synthetic odds. The
real-feed flip is GATED behind the funded pre-flip checklist (out of scope for v1). The #1
safety property enforced here: ``--no-dry-run`` can NEVER reach a real feed by accident — it
REFUSES (``SystemExit``). The tested library entry point ``run_build_dry`` FORCES
``dashboard.dry_run=True`` on a COPY of the caller's config, so the dry-run builder can never
emit a real-looking bundle even if handed a config that claims ``dry_run`` is False.
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

from wcmodel.dashboard.build import build_snapshot


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wc-dashboard-build",
                                description="Build a leakage-safe dashboard JSON snapshot (dry-run default)")
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True,
                   help="synthetic-odds posture, NON-REAL (default)")
    p.add_argument("--no-dry-run", dest="dry_run", action="store_false",
                   help="real feed (GATED — requires the funded pre-flip checklist)")
    p.add_argument("--cutoff", default=None, help="as-of ISO ts; defaults to now")
    return p


def run_build_dry(*, store, items, cutoff, config, fit_kwargs, out_root,
                  tournament=None) -> Path:
    """The tested library-level dry-run builder: build the FULL bundle, NON-REAL by force.

    FORCES ``config["dashboard"]["dry_run"]=True`` on a DEEP COPY of the caller's config (the
    caller's dict is NEVER mutated), then delegates to ``build_snapshot``. Because
    ``build_snapshot`` taints the whole bundle NON-REAL when ``dashboard.dry_run`` is set
    (``is_synth = cfg["dashboard"]["dry_run"] or ...``), this builder can NEVER emit a
    real-looking bundle — even if handed a config whose ``dry_run`` is somehow False. Returns
    the bundle ``Path``."""
    forced = copy.deepcopy(config)
    forced.setdefault("dashboard", {})
    forced["dashboard"]["dry_run"] = True            # FORCE NON-REAL (on the copy)
    return build_snapshot(cutoff, store=store, config=forced, fit_kwargs=fit_kwargs,
                          items=items, out_root=out_root, tournament=tournament)


# --- main's SELF-CONTAINED synthetic demo harness (no pytest fixtures imported) ----------
# A compact 1-group-of-4 synthetic tournament over a panel of real team NAMES, fit over a
# tiny seeded store, with ONE synthetic odds item. This is a NON-REAL demo — every artifact
# is stamped is_synthetic=True with the DRY-RUN banner. The harness mirrors the test
# conftest's shape but is rebuilt here so the runnable CLI depends on NO test code.
_PANEL_TEAMS = ["Brazil", "Argentina", "Mexico", "Malta"]
_FIXTURE_DATES = {
    ("Brazil", "Argentina"): "2024-05-01",
    ("Mexico", "Malta"): "2024-05-06",
    ("Brazil", "Mexico"): "2024-05-02",
    ("Argentina", "Malta"): "2024-05-03",
    ("Brazil", "Malta"): "2024-05-04",
    ("Argentina", "Mexico"): "2024-05-05",
}


def _demo_store(root: Path):
    """A tiny seeded BitemporalStore over the panel teams — enough played history for a
    compact posterior fit. Written through the REAL source policy (POINT_IN_TIME), so the
    demo exercises the same leakage-safe read path production uses."""
    import pandas as pd

    from wcmodel.data.sources.results import normalize_results
    from wcmodel.data.store import BitemporalStore, Policy

    # A small ladder of pre-2026 played results so each panel team has history < cutoff.
    rows = []
    d = pd.Timestamp("2023-01-01")
    pairs = [("Brazil", "Malta", 4, 0), ("Argentina", "Malta", 3, 0),
             ("Mexico", "Malta", 2, 0), ("Brazil", "Argentina", 1, 1),
             ("Brazil", "Mexico", 2, 1), ("Argentina", "Mexico", 1, 0)]
    for i in range(6):                               # repeat the ladder for a denser panel
        for (h, a, hs, as_) in pairs:
            rows.append((str((d).date()), h, a, hs, as_, "Friendly",
                         "London", "England", False))
            d += pd.Timedelta(days=1)
    raw = pd.DataFrame(rows, columns=["date", "home_team", "away_team", "home_score",
                                      "away_score", "tournament", "city", "country",
                                      "neutral"])
    store = BitemporalStore(root=root)
    store.write("results", normalize_results(raw), policy=Policy.POINT_IN_TIME,
                keys=["match_id"], source="martj42", source_version="demo")
    return store


def _demo_tournament() -> dict:
    """A 1-group-of-4 -> single-Final synthetic bracket over the panel teams (the
    ``build_snapshot(tournament=...)`` passthrough), so the full group-sim -> rank -> knockout
    path runs over the compact demo posterior without a 48-team KeyError."""
    fixtures = [{"home": h, "away": a, "date": _FIXTURE_DATES[(h, a)], "round": "Matchday 1"}
                for (h, a) in _FIXTURE_DATES]
    fixtures.append({"match": 104, "home": "1A", "away": "2A", "round": "Final"})
    return {"groups": [{"name": "A", "teams": list(_PANEL_TEAMS)}], "fixtures": fixtures}


def _run_demo_dry_run(cutoff, out_root) -> Path:
    """Assemble the self-contained synthetic harness and build the NON-REAL demo bundle.

    Builds a tmp store, a synthetic odds item matching one group fixture, and a compact-fit
    bundle. Clearly NON-REAL: ``run_build_dry`` forces ``dry_run`` on, so every artifact is
    stamped ``is_synthetic=True`` with the DRY-RUN banner."""
    import tempfile

    from wcmodel.backtest.odds_ingest import synthetic_odds_sample
    from wcmodel.config import load_config

    cfg = load_config()
    fit_root = Path(tempfile.mkdtemp(prefix="wc-dashboard-demo-fit-"))
    store = _demo_store(fit_root / "store")
    # A synthetic odds item whose UTC commence date matches the (Brazil, Mexico) group
    # fixture, so the demo shows a live edge actually attaching (NON-REAL, labelled).
    s = synthetic_odds_sample(home="Brazil", away="Mexico",
                              commence="2024-05-02T19:00:00Z",
                              entry=(2.5, 3.4, 3.0), close=(2.1, 3.5, 3.4), seed=0)
    return run_build_dry(
        store=store, items=[{"sample": s["sample"], "liquidity": 50.0}],
        cutoff=cutoff, config=cfg,
        fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0,
                    "cache_dir": str(fit_root / "fc")},
        out_root=out_root, tournament=_demo_tournament(),
    )


def main(argv=None):
    """CLI entry point (``wc-dashboard-build``).

    DRY-RUN (default): build a NON-REAL synthetic demo bundle and print its path to stdout.
    ``--no-dry-run``: REFUSE — the real feed is GATED behind the funded pre-flip checklist and
    can never be reached by accident. Prints a clear refusal to stderr and exits nonzero."""
    args = build_arg_parser().parse_args(argv)
    if not args.dry_run:
        print(
            "wc-dashboard-build: REFUSING --no-dry-run. The real odds feed is GATED behind "
            "the funded pre-flip checklist and is NOT available in v1 (synthetic dry-run "
            "only). No real feed can be reached by this CLI.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    from wcmodel.config import load_config

    cutoff = args.cutoff
    if cutoff is None:
        from datetime import datetime, timezone
        cutoff = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    out_root = Path(load_config()["dashboard"]["output_dir"])
    bundle = _run_demo_dry_run(cutoff, out_root)
    print(f"{bundle}  (DRY-RUN · SYNTHETIC ODDS · NOT REAL — demo bundle)")
    return 0


if __name__ == "__main__":          # pragma: no cover
    raise SystemExit(main())
