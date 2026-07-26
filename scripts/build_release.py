"""Build one citable forecast release (product spec Phase 1, rev 2).

Usage:
  PYTHONPATH=src .venv/bin/python scripts/build_release.py \
      --cutoff 2026-09-20T00:00:00Z --fixtures afcon_q_md1.csv \
      --label "September qualifiers, matchday 1" \
      --store data/stores/full_final --out releases/2026-09-20/
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from wcmodel.config import load_config
from wcmodel.data.store import BitemporalStore
from wcmodel.model.cache import cached_fit
from wcmodel.releases.build import build_release
from wcmodel.releases.fixtures import load_fixtures
from wcmodel.releases.render import render_csv, render_html


def _latest_result(store, cutoff) -> str:
    """Freshness stamp — the latest result date STRICTLY before the cutoff day.

    Mirrors the TRAINING boundary (features.build filters `date < cutoff_day`,
    features.py:203), not store.read's visibility: the store's point-in-time
    read is `<= cutoff`, so at an exactly-midnight cutoff a result dated ON the
    cutoff day is visible to the read while the fit never saw it. Stamping that
    date would overstate freshness and contradict the artifact's own
    "all data strictly before" line (acceptance-run finding: the 2026-07-19
    final surfaced as its own release's latest_result). An empty strictly-before
    slice is a wrong store or a wrong cutoff — never a release with a NaT
    freshness line, so fail loud instead of stamping garbage."""
    df = store.read("results", cutoff=cutoff)
    ts = pd.Timestamp(cutoff)
    cutoff_day = (ts.tz_localize(None) if ts.tzinfo else ts).normalize()
    dates = pd.to_datetime(df["date"]) if len(df) else pd.Series([], dtype="datetime64[ns]")
    dates = dates[dates < cutoff_day]
    latest = dates.max() if len(dates) else pd.NaT
    if pd.isna(latest):
        raise ValueError(f"store has no results before cutoff {cutoff}")
    return latest.strftime("%Y-%m-%d")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cutoff", required=True)
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--store", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    cfg = load_config()
    inf = cfg["model"]["inference"]
    fixtures = load_fixtures(args.fixtures)
    store = BitemporalStore(root=Path(args.store))
    # ONE parse of the cutoff, shared by the fit and the freshness read, so the two
    # can never disagree about the leakage boundary.
    cutoff_ts = pd.Timestamp(args.cutoff)
    post, meta = cached_fit(cutoff=cutoff_ts, store=store,
                            backend=inf["backend"], draws=inf["draws"],
                            seed=int(cfg["seed"]), advi_iters=inf["advi_iters"],
                            cache_dir="data/cache", config=cfg)
    print(f"[fit] {'HIT' if meta['cache_hit'] else 'FIT'} key={meta['key']}")

    sizes = post.idata.posterior.sizes
    n_draws = int(sizes["chain"] * sizes["draw"])
    release = build_release(cutoff=args.cutoff, fixtures=fixtures, post=post,
                            posterior_key=meta["key"], window_label=args.label,
                            n_draws=n_draws,
                            latest_result=_latest_result(store, cutoff_ts))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "release.json").write_text(json.dumps(release, indent=1))
    (out / "release.html").write_text(render_html(release))
    (out / "release.csv").write_text(render_csv(release))
    print(f"[release] {len(release['rows'])} fixtures -> {out}/release.{{json,html,csv}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
