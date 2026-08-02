#!/usr/bin/env python
"""V9 — issue the locked arms against the scored pools (OA Plan 2 v2).

Runs ONLY behind a valid lock chain. Everything it issues is determined by
``lock-vN.json`` and the artifacts that lock names — this script chooses
nothing:

===================== ==========================================
arm                   determined by
===================== ==========================================
``incumbent``         the frozen production map (w=0 by identity)
``Eprime``            the locked (w, de-vig) from the selection
                      trace — the PRIMARY contrast
``Eprime_other_devig``the other de-vig at its own w* argmin over
                      the locked trace's grid rows (spec §2.1)
``stacking``          the locked deployment params applied to
                      [DC, de-vigged odds, elo_ordlogit]
``elo_ordlogit``      the odds-free head, same information set
``elo_dc_5050``       0.5·elo + 0.5·incumbent, renormalized
===================== ==========================================

Same pricing path as V5 (``wcmodel.eval.oof.price_fixture``), which is what
makes the transfer of ``w`` from the dev slate to these pools meaningful at
all: if the two sides priced fixtures differently, a w tuned on one would
not mean the same thing on the other.

NO OUTCOME IS READ HERE. As in V5, the ledger holds forecasts and
provenance; V10 joins outcomes at scoring time. A fixture whose book is
absent or uninvertible falls back to the incumbent BITWISE with
``odds_snapshot_hash=None`` and belongs to the sensitivity population only.
"""
# No `from __future__ import annotations`: loaded by PATH in tests.
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wcmodel.config import load_config                        # noqa: E402
from wcmodel.data.features import build_cached                # noqa: E402
from wcmodel.data.store import BitemporalStore                # noqa: E402
from wcmodel.eval.aliases import load_aliases                 # noqa: E402
from wcmodel.eval.arms import StackParams, predict_stacked    # noqa: E402
from wcmodel.eval.blend import blend_arm                      # noqa: E402
from wcmodel.eval.elo_ordlogit import fit_ordlogit            # noqa: E402
from wcmodel.eval.ledger import LedgerWriter                  # noqa: E402
from wcmodel.eval.lock import require_lock                    # noqa: E402
from wcmodel.eval.oof import (                                # noqa: E402
    DC_ARM,
    ELO_ARM,
    OofPricingError,
    odds_arm,
    price_fixture,
)
from wcmodel.model.draw_api import FixtureCtx                 # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oa_dev_oof import (                                      # noqa: E402
    DevOofError,
    book_prices_from_archive,
    fixture_covariates,
    enabled_covariates,
    latest_elo,
    match_level_panel,
    t_issue_for,
)

MANIFEST_DEFAULT = "config/oa_eval_manifest.yaml"
JOURNAL_DEFAULT = "data/oa_acquisition_journal.jsonl"
STORE_DEFAULT = "data/stores/full_final"
RAW_DIR_DEFAULT = "data/odds_raw"
CACHE_DEFAULT = "data/cache/oa_dev"
LEDGER_DEFAULT = "data/oa_scored_ledger.parquet"
OUT_DEFAULT = "reports/oa_issue.md"

INCUMBENT = "incumbent"
EPRIME = "Eprime"
EPRIME_OTHER = "Eprime_other_devig"
STACKING = "stacking"
ELO = "elo_ordlogit"
ELO_DC = "elo_dc_5050"
ISSUED_ARMS = (INCUMBENT, EPRIME, EPRIME_OTHER, STACKING, ELO, ELO_DC)


def locked_choices(trace_path="reports/oa_selection_trace.json") -> dict:
    """The deployment choices, read from the LOCKED trace and nowhere else."""
    trace = json.loads(Path(trace_path).read_text())
    method = str(trace["selected"]["devig_method"])
    w = float(trace["selected"]["w"])
    other = "shin" if method == "multiplicative" else "multiplicative"
    rows = [r for r in trace["grid_mean_rps"]
            if r["devig_method"] == other]
    # V6's own tie rule: lowest mean RPS, ties to smaller w.
    best = min(rows, key=lambda r: (r["mean_rps"], r["w"]))
    p = trace["stacking"]["params"]
    return {
        "devig_method": method, "w": w,
        "other_devig": other, "other_w": float(best["w"]),
        "stack": StackParams(c1=p["c1"], s=p["s"], b_dc=p["b_dc"],
                             b_odds=p["b_odds"], b_elo=p["b_elo"]),
    }


def cut_digests(journal_path, *, gate="ga") -> dict:
    out = {}
    for line in Path(journal_path).read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if (rec.get("type") != "receipt" or rec.get("gate") != gate
                or rec.get("kind") != "snapshot" or rec.get("tag") != "cut"):
            continue
        if rec.get("error") or not rec.get("raw_sha256"):
            continue
        out[str(rec["fixture_id"])] = rec["raw_sha256"]
    return out


def _renorm(p) -> dict:
    total = sum(p.values())
    return {k: v / total for k, v in p.items()}


def issued_arms_for(priced, *, choices) -> dict:
    """The six locked arms from one fixture's priced block.

    ``priced`` is ``oof.price_fixture``'s output. When the book was absent
    or uninvertible it holds only the two odds-free arms, and the three
    odds-derived arms fall back to the incumbent BITWISE — the V7
    convention that keeps such rows in the sensitivity population without
    inventing a price.
    """
    incumbent = priced[DC_ARM]
    elo = priced[ELO_ARM]
    out = {
        INCUMBENT: incumbent,
        ELO: elo,
        ELO_DC: _renorm({k: 0.5 * elo[k] + 0.5 * incumbent[k]
                         for k in ("home", "draw", "away")}),
    }
    selected_arm = blend_arm(choices["devig_method"], choices["w"])
    if selected_arm not in priced:                     # odds-absent fixture
        out[EPRIME] = incumbent
        out[EPRIME_OTHER] = incumbent
        out[STACKING] = incumbent
        return out
    out[EPRIME] = priced[selected_arm]
    out[EPRIME_OTHER] = priced[
        blend_arm(choices["other_devig"], choices["other_w"])]
    out[STACKING] = predict_stacked(choices["stack"], {
        "dc": incumbent,
        "odds": priced[odds_arm(choices["devig_method"])],
        "elo_ordlogit": elo,
    })
    return out


def run_issue(*, fixtures, digests, choices, store_path, cfg, cache_dir,
              raw_dir, ledger_path, aliases, shard=None, progress=True):
    store = BitemporalStore(store_path)
    neutral_by_id = {}
    frame = pd.read_parquet(Path(store_path) / "results.parquet")
    frame = frame.drop_duplicates(subset=["match_id"], keep="last")
    for row in frame.itertuples(index=False):
        neutral_by_id[str(row.match_id)] = bool(row.neutral)
    enabled = enabled_covariates(cfg)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                         text=True, check=True).stdout.strip()
    inference = cfg["model"]["inference"]

    by_day = {}
    for fx in fixtures:
        by_day.setdefault(fx["date"], []).append(fx)
    days = sorted(by_day)
    if shard is not None:
        i, n = shard
        days = [d for k, d in enumerate(days) if k % n == i]

    from wcmodel.model.cache import cached_fit
    written, errors, fallbacks = 0, [], 0
    with LedgerWriter(ledger_path) as writer:
        for idx, day in enumerate(days, 1):
            t_issue = t_issue_for(day)
            panel = build_cached(pd.Timestamp(t_issue), store, cfg,
                                 cache_dir=cache_dir)
            posterior, _ = cached_fit(
                cutoff=pd.Timestamp(t_issue), store=store,
                backend=inference["backend"], draws=inference["draws"],
                seed=cfg["seed"], advi_iters=inference["advi_iters"],
                cache_dir=cache_dir, config=cfg)
            ordlogit = fit_ordlogit(match_level_panel(panel))
            elos = latest_elo(panel)

            for fx in by_day[day]:
                fid = fx["fixture_id"]
                if fx["home"] not in elos or fx["away"] not in elos:
                    errors.append((fid, "team absent from the as-of-cutoff "
                                        "panel"))
                    continue
                neutral = neutral_by_id.get(fid, True)
                ctx = FixtureCtx(
                    home=fx["home"], away=fx["away"], neutral=neutral,
                    covariates=fixture_covariates(
                        enabled=enabled, panel=panel, home=fx["home"],
                        away=fx["away"], fixture_date=day) or None)
                digest = digests.get(fid)
                prices = None
                if digest:
                    try:
                        prices = book_prices_from_archive(
                            digest, home=fx["home"], away=fx["away"],
                            aliases=aliases, raw_dir=raw_dir)
                    except DevOofError as exc:
                        errors.append((fid, f"book: {str(exc)[:120]}"))
                try:
                    priced = price_fixture(
                        posterior=posterior, fixture_ctx=ctx,
                        elo_home=elos[fx["home"]], elo_away=elos[fx["away"]],
                        hfa=0.0 if neutral else 1.0,
                        ordlogit_params=ordlogit, book_prices=prices)
                except OofPricingError as exc:
                    # uninvertible book -> incumbent fallback, sensitivity
                    # population only (never an invented price)
                    errors.append((fid, f"uninvertible: {str(exc)[:100]}"))
                    priced = price_fixture(
                        posterior=posterior, fixture_ctx=ctx,
                        elo_home=elos[fx["home"]], elo_away=elos[fx["away"]],
                        hfa=0.0 if neutral else 1.0,
                        ordlogit_params=ordlogit, book_prices=None)
                except (KeyError, ValueError) as exc:
                    errors.append((fid, str(exc)[:140]))
                    continue

                arms = issued_arms_for(priced, choices=choices)
                covered = blend_arm(choices["devig_method"],
                                    choices["w"]) in priced
                if not covered:
                    fallbacks += 1
                for arm, probs in arms.items():
                    odds_derived = arm in (EPRIME, EPRIME_OTHER, STACKING)
                    writer.append({
                        "fixture_id": fid, "pool": fx["pool"],
                        "date": fx["date"], "home": fx["home"],
                        "away": fx["away"],
                        "kickoff_utc": pd.Timestamp(fx["kickoff_utc"]),
                        "t_issue": t_issue, "training_cutoff": t_issue,
                        "arm": arm, "p_home": probs["home"],
                        "p_draw": probs["draw"], "p_away": probs["away"],
                        "issued_git": sha,
                        "odds_snapshot_hash": (digest if odds_derived
                                               and covered else None),
                    })
                    written += 1
            if progress:
                print(f"[{idx}/{len(days)}] {day}: {written} rows",
                      flush=True)
    return {"days": len(days), "rows": written, "errors": errors,
            "fallbacks": fallbacks}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", default=MANIFEST_DEFAULT)
    ap.add_argument("--journal", default=JOURNAL_DEFAULT)
    ap.add_argument("--store", default=STORE_DEFAULT)
    ap.add_argument("--raw-dir", default=RAW_DIR_DEFAULT)
    ap.add_argument("--cache-dir", default=CACHE_DEFAULT)
    ap.add_argument("--ledger", default=LEDGER_DEFAULT)
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--shard", default=None, metavar="I/N")
    args = ap.parse_args(argv)

    # THE GATE: no issuance without a verified lock chain.
    head = require_lock()
    print(f"lock v{head['version']} verified (commit "
          f"{head['code_commit'][:12]})")

    choices = locked_choices()
    print(f"locked: w={choices['w']:.2f} {choices['devig_method']}; "
          f"other {choices['other_devig']} w*={choices['other_w']:.2f}")

    manifest = yaml.safe_load(Path(args.manifest).read_text())
    fixtures = sorted(manifest["fixtures"],
                      key=lambda f: (str(f["date"]), str(f["fixture_id"])))
    shard = None
    if args.shard:
        i, n = (int(p) for p in args.shard.split("/"))
        shard = (i, n)

    out = run_issue(
        fixtures=fixtures, digests=cut_digests(args.journal),
        choices=choices, store_path=args.store, cfg=load_config(),
        cache_dir=args.cache_dir, raw_dir=args.raw_dir,
        ledger_path=args.ledger, aliases=load_aliases(), shard=shard)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join([
        "# OA scored-pool issuance (OA Plan 2 v2, V9)", "",
        f"- lock: v{head['version']} ({head['code_commit'][:12]})",
        f"- locked choice: **w={choices['w']:.2f}, "
        f"{choices['devig_method']}**",
        f"- matchdays: {out['days']}",
        f"- rows: **{out['rows']}** ({len(ISSUED_ARMS)} arms x fixtures)",
        f"- incumbent-fallback (odds absent/uninvertible): "
        f"{out['fallbacks']}",
        f"- errors: {len(out['errors'])}", "",
        "No outcome is read in this step; V10 joins them at scoring time.",
        "",
    ] + ([f"| {f} | {w} |" for f, w in out["errors"]] if out["errors"]
         else [])))
    print(f"wrote {args.out}: {out['rows']} rows, "
          f"{out['fallbacks']} fallback, {len(out['errors'])} error(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
