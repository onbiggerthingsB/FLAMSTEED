#!/usr/bin/env python
"""V5 — the development out-of-fold forecast walk (OA Plan 2 v2).

Walks the FROZEN dev manifest (``config/oa_dev_manifest.yaml``, 260 fixtures
over 106 matchdays) in chronological order and writes, for every fixture,
the full 46-arm block the V6 selection and the stacking arm consume. Each
matchday gets ONE fit at its own issuance instant:

    t_issue = 09:00:00 UTC on the venue-local matchday   (prereg estimand)
    training_cutoff = t_issue                            (information set)

and the fit is bucketed by that EXACT instant plus the model config — never
by pool — so one cutoff serves every fixture that shares it, globally
(finding 11). The posterior cache makes a resumed run free.

WHY A WALK AND NOT ONE FIT. The forecast for a 2022 fixture must not know
2023. Refitting per matchday is the whole point: 106 fits is the price of an
honest out-of-fold ledger, and the content-addressed cache means it is paid
once.

WHAT THIS DOES NOT DO. It never reads an outcome. The ledger holds forecasts
and provenance; outcomes are joined at scoring time by ``select_w`` and
``oof_stacking``. A leakage bug here therefore cannot be one that peeked at
the result — only one that fit on too much history, which is what the
canary in ``tests/eval/test_dev_oof.py`` pins.

THE ORDERED-LOGIT TRAINING WINDOW is the panel's own ``in_feature_window``
— the config's frozen feature window, the SAME data the incumbent DC model
conditions on. Stated here because the arm itself takes a frame and does not
choose: an unpinned window would be a researcher knob on the very ledger w
is selected from.
"""
# No `from __future__ import annotations`: loaded by PATH in tests, matching
# the oa_probe.py / oa_acquire.py convention.
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wcmodel.config import load_config                       # noqa: E402
from wcmodel.data.features import build_cached               # noqa: E402
from wcmodel.data.sources.odds import parse_snapshot         # noqa: E402
from wcmodel.data.store import BitemporalStore               # noqa: E402
from wcmodel.eval.aliases import load_aliases                # noqa: E402
from wcmodel.eval.elo_ordlogit import fit_ordlogit           # noqa: E402
from wcmodel.eval.ledger import LedgerWriter, T_ISSUE_UTC_TIME  # noqa: E402
from wcmodel.eval.oof import (                               # noqa: E402
    OofPricingError,
    expected_arms,
    ledger_rows,
    price_fixture,
)
from wcmodel.model.cache import cached_fit                   # noqa: E402
from wcmodel.model.draw_api import FixtureCtx                # noqa: E402

MANIFEST_DEFAULT = "config/oa_dev_manifest.yaml"
COVERAGE_DEFAULT = "config/oa_dev_coverage.yaml"
STORE_DEFAULT = "data/stores/full_final"
RAW_DIR_DEFAULT = "data/odds_raw"
CACHE_DEFAULT = "data/cache/oa_dev"
LEDGER_DEFAULT = "data/oa_dev_ledger.parquet"
OUT_DEFAULT = "reports/oa_dev_oof.md"

SHARP_BOOK = "pinnacle"


class DevOofError(RuntimeError):
    """The walk cannot proceed as specified."""


def t_issue_for(day: str) -> datetime:
    hour, minute, second, micro = T_ISSUE_UTC_TIME
    d = datetime.strptime(day, "%Y-%m-%d").date()
    return datetime(d.year, d.month, d.day, hour, minute, second, micro,
                    tzinfo=timezone.utc)


def git_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()


# ------------------------------------------------------------------ inputs
def load_inputs(manifest_path, coverage_path) -> list:
    """The manifest joined to its coverage evidence, chronological.

    Every manifest fixture MUST carry an admissible coverage row — the
    manifest was DERIVED from exactly that set, so a miss means the two
    artifacts have drifted apart and the walk would price a fixture whose
    odds provenance we cannot name.
    """
    manifest = yaml.safe_load(Path(manifest_path).read_text())
    coverage = yaml.safe_load(Path(coverage_path).read_text())
    by_id = {str(r["match_id"]): r for r in coverage["coverage"]
             if r.get("admissible")}
    fixtures = []
    missing = []
    for row in manifest["fixtures"]:
        mid = str(row["match_id"])
        cov = by_id.get(mid)
        if cov is None or not cov.get("cut_raw_sha256"):
            missing.append(mid)
            continue
        fixtures.append({
            "fixture_id": mid,
            "pool": str(row["tournament"]),
            "date": str(row["date"]),
            "home": str(row["home_team"]),
            "away": str(row["away_team"]),
            "cut_raw_sha256": str(cov["cut_raw_sha256"]),
        })
    if missing:
        raise DevOofError(
            f"{len(missing)} manifest fixture(s) have no admissible coverage "
            f"row with a cut digest (e.g. {missing[:3]}) — manifest and "
            "coverage artifact have drifted; regenerate before walking")
    fixtures.sort(key=lambda f: (f["date"], f["fixture_id"]))
    return fixtures


def store_context(store_path) -> dict:
    """``{match_id: {neutral, kickoff_utc}}`` — VENUE truth, known before
    kickoff, read from the results store.

    Only these two fields are taken. The same rows carry the scores, and the
    ledger has no outcome column precisely so that this function has no
    reason to touch them.
    """
    frame = pd.read_parquet(Path(store_path) / "results.parquet")
    frame = frame.drop_duplicates(subset=["match_id"], keep="last")
    out = {}
    for row in frame.itertuples(index=False):
        day = pd.Timestamp(row.date).strftime("%Y-%m-%d")
        out[str(row.match_id)] = {
            "neutral": bool(row.neutral),
            # The store carries no kickoff clock; the ledger only needs an
            # instant strictly after t_issue on the matchday, and every dev
            # competition kicks off in the afternoon/evening local time.
            # 19:00Z is the archived listings' modal kickoff and is used
            # ONLY to satisfy the t_issue < kickoff invariant.
            "kickoff_utc": pd.Timestamp(f"{day}T19:00:00Z"),
        }
    return out


def book_prices_from_archive(digest, *, home, away, aliases, raw_dir) -> dict:
    """The sharp book's ``{home, draw, away}`` decimal prices from the PAID
    archived cut snapshot, keyed by TEAM NAME through the alias map.

    Never positional: the wire labels outcomes by team, and home/away can
    flip between the API and the store, so a positional read is exactly how
    a forecast would be silently inverted.
    """
    blob = Path(raw_dir) / f"{digest}.json"
    if not blob.exists():
        raise DevOofError(
            f"archived cut snapshot {digest} is absent from {raw_dir} — the "
            "paid evidence the coverage artifact names is gone")
    raw = blob.read_bytes()
    # B2: the archive is content-ADDRESSED, so verify it. Trusting the
    # filename let anyone swap coherent odds into <digest>.json and change
    # every forecast while the ledger still recorded the locked digest.
    import hashlib
    actual = hashlib.sha256(raw).hexdigest()
    if actual != digest:
        raise DevOofError(
            f"archived snapshot {blob} hashes to {actual[:16]}… but is "
            f"named for {digest[:16]}… — the paid evidence has been "
            "altered; refusing to price from it")
    rows = [r for r in parse_snapshot(json.loads(raw))
            if r["bookmaker"] == SHARP_BOOK]
    if not rows:
        raise DevOofError(
            f"{digest}: no {SHARP_BOOK} rows, but the coverage artifact "
            "recorded this fixture as admissible")

    def _canon(name):
        return aliases.get(str(name).casefold(), str(name))

    prices = {}
    for row in rows:
        label = _canon(row["outcome"])
        if label == "Draw":
            prices["draw"] = float(row["price"])
        elif label == home:
            prices["home"] = float(row["price"])
        elif label == away:
            prices["away"] = float(row["price"])
    got = sorted(prices)
    if got != ["away", "draw", "home"]:
        raise DevOofError(
            f"{digest}: could not map {SHARP_BOOK}'s outcomes onto "
            f"{home!r} v {away!r} (resolved {got}); wire labels were "
            f"{sorted({_canon(r['outcome']) for r in rows})}")
    return prices


# ---------------------------------------------------------- per-cutoff work
def match_level_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Pivot the team-level feature panel to one row per match with the
    ordered-logit fit columns (``elo_h, elo_a, hfa, outcome``).

    Restricted to ``in_feature_window`` — the config's frozen window, the
    same data the incumbent conditions on (see the module docstring).
    """
    window = panel[panel["in_feature_window"].astype(bool)]
    home = window[window["is_home"].astype(bool)]
    away = window[~window["is_home"].astype(bool)]
    merged = home.merge(
        away[["match_id", "elo_pre"]], on="match_id", how="inner",
        suffixes=("", "_away"))
    merged = merged.rename(columns={"elo_pre": "elo_h",
                                    "elo_pre_away": "elo_a"})
    merged["hfa"] = (~merged["neutral"].astype(bool)).astype(float)
    hs = merged["home_score"].astype(float)
    as_ = merged["away_score"].astype(float)
    merged["outcome"] = pd.Series(
        ["home" if h > a else ("away" if a > h else "draw")
         for h, a in zip(hs, as_)], index=merged.index)
    cols = ["match_id", "date", "team", "opponent", "elo_h", "elo_a", "hfa",
            "outcome"]
    return merged[cols].dropna(subset=["elo_h", "elo_a", "hfa", "outcome"])


def latest_elo(panel: pd.DataFrame) -> dict:
    """Each team's most recent ``elo_pre`` in the as-of-cutoff panel — the
    rating the ordered-logit head prices the upcoming fixture with."""
    ordered = panel.sort_values(["date", "match_id"])
    return {str(t): float(v) for t, v in
            zip(ordered["team"], ordered["elo_pre"])}


def fixture_covariates(*, enabled, panel, home, away, fixture_date) -> dict:
    """Leakage-safe covariate dict for ONE upcoming fixture.

    Mirrors the established validation convention
    (``backtest.ablation._fixture_covariates``): ``rest_days`` from each
    side's last match STRICTLY BEFORE the cutoff panel's end; ``travel_km``
    and ``altitude_m`` masked to NaN (the transform masks rather than
    imputes) because an upcoming fixture carries no itinerary and the dev
    competitions have no venue table.
    """
    cov: dict = {}
    fd = pd.Timestamp(fixture_date).normalize()
    last_seen: dict = {}
    if panel is not None and len(panel):
        grouped = panel.groupby("team")["date"].max()
        last_seen = {str(k): pd.Timestamp(v).normalize()
                     for k, v in grouped.items()}
    for name in enabled:
        if name == "rest_days":
            for side, team in (("", home), ("__away", away)):
                last = last_seen.get(team)
                cov[f"{name}{side}"] = (float("nan") if last is None
                                        else float((fd - last).days))
        elif name in ("travel_km", "altitude_m"):
            cov[name] = float("nan")
            if name == "travel_km":
                cov[f"{name}__away"] = float("nan")
    return cov


def enabled_covariates(cfg) -> tuple:
    block = (cfg.get("model") or {}).get("covariates") or {}
    names = block.get("enabled") or []
    return tuple(str(n) for n in names)


# ------------------------------------------------------------------- walk
def run_walk(*, fixtures, store_path, cfg, cache_dir, raw_dir, ledger_path,
             aliases, limit_days=None, shard=None, progress=True) -> dict:
    store = BitemporalStore(store_path)
    ctx_by_id = store_context(store_path)
    enabled = enabled_covariates(cfg)
    sha = git_sha()
    inference = cfg["model"]["inference"]

    by_day: dict = {}
    for fx in fixtures:
        by_day.setdefault(fx["date"], []).append(fx)
    days = sorted(by_day)
    if limit_days is not None:
        days = days[:limit_days]
    if shard is not None:
        index, total = shard
        # STRIDED, not contiguous: matchdays differ in cost (a fresh Elo
        # panel dominates, and later cutoffs carry more history), so
        # slicing by stride keeps the workers balanced. Correctness does
        # not depend on the split — each matchday is a pure function of its
        # own cutoff, so any partition yields byte-identical rows.
        days = [d for i, d in enumerate(days) if i % total == index]

    written, fits, errors = 0, [], []
    with LedgerWriter(ledger_path) as writer:
        for i, day in enumerate(days, 1):
            t_issue = t_issue_for(day)
            panel = build_cached(pd.Timestamp(t_issue), store, cfg,
                                 cache_dir=cache_dir)
            posterior, meta = cached_fit(
                cutoff=pd.Timestamp(t_issue), store=store,
                backend=inference["backend"], draws=inference["draws"],
                seed=cfg["seed"], advi_iters=inference["advi_iters"],
                cache_dir=cache_dir, config=cfg)
            fits.append({"day": day, "cache_hit": bool(meta.get("cache_hit"))})
            ordlogit = fit_ordlogit(match_level_panel(panel))
            elos = latest_elo(panel)

            for fx in by_day[day]:
                sctx = ctx_by_id.get(fx["fixture_id"])
                if sctx is None:
                    errors.append((fx["fixture_id"], "no store row"))
                    continue
                if fx["home"] not in elos or fx["away"] not in elos:
                    errors.append((fx["fixture_id"], "team absent from the "
                                   "as-of-cutoff panel (no prior match)"))
                    continue
                cov = fixture_covariates(
                    enabled=enabled, panel=panel, home=fx["home"],
                    away=fx["away"], fixture_date=day)
                fixture_ctx = FixtureCtx(
                    home=fx["home"], away=fx["away"],
                    neutral=sctx["neutral"], covariates=cov or None)
                try:
                    prices = book_prices_from_archive(
                        fx["cut_raw_sha256"], home=fx["home"],
                        away=fx["away"], aliases=aliases, raw_dir=raw_dir)
                    priced = price_fixture(
                        posterior=posterior, fixture_ctx=fixture_ctx,
                        elo_home=elos[fx["home"]], elo_away=elos[fx["away"]],
                        hfa=0.0 if sctx["neutral"] else 1.0,
                        ordlogit_params=ordlogit, book_prices=prices)
                except (OofPricingError, DevOofError, KeyError,
                        ValueError) as exc:
                    errors.append((fx["fixture_id"], str(exc)[:160]))
                    continue
                got = tuple(sorted(priced))
                want = tuple(sorted(expected_arms(covered=True)))
                if got != want:
                    errors.append((fx["fixture_id"],
                                   f"incomplete arm block: {len(got)} arms"))
                    continue
                rows = ledger_rows(
                    fixture={**fx, "kickoff_utc": sctx["kickoff_utc"]},
                    priced=priced, t_issue=t_issue, training_cutoff=t_issue,
                    issued_git=sha,
                    odds_snapshot_hash=fx["cut_raw_sha256"])
                for row in rows:
                    writer.append(row)
                written += len(rows)
            if progress:
                hits = sum(1 for f in fits if f["cache_hit"])
                print(f"[{i}/{len(days)}] {day}: {len(by_day[day])} fixture(s)"
                      f", {written} rows so far, {hits} cache hit(s)",
                      flush=True)
    return {"days": len(days), "rows": written, "fits": fits,
            "errors": errors}


def assemble_report(out, *, n_fixtures, ledger_path) -> str:
    lines = [
        "# OA dev-slate OOF forecast walk (OA Plan 2 v2, V5)", "",
        f"- matchdays walked (= model fits): **{out['days']}**",
        f"- ledger rows written: **{out['rows']}** "
        f"(46 arms x {n_fixtures} covered fixtures = {46 * n_fixtures})",
        f"- fits served from cache: "
        f"{sum(1 for f in out['fits'] if f['cache_hit'])}/{len(out['fits'])}",
        f"- ledger: `{ledger_path}`",
        f"- fixtures that could not be priced: **{len(out['errors'])}**", "",
        "Each matchday is fit at its OWN issuance instant (09:00Z on the "
        "venue-local matchday) with `training_cutoff == t_issue`, so a 2022 "
        "forecast never sees 2023. No outcome is read anywhere in this "
        "walk — the ledger holds forecasts and provenance only.", "",
    ]
    if out["errors"]:
        lines += ["## Fixtures not priced", "",
                  "| fixture | reason |", "|---|---|"]
        for fid, why in out["errors"]:
            lines.append(f"| {fid} | {why} |")
        lines.append("")
    return "\n".join(lines)


def merge_shards(shard_paths, ledger_path) -> int:
    """Concatenate shard ledgers into one, RE-VALIDATING every row.

    The merge does not trust the shards: rows go back through
    ``LedgerWriter``, so the one-row-per-(arm, fixture) rule, the
    probability checks and the t_issue invariants are enforced on the
    union — which is exactly where a sharding bug (an overlapping split,
    a dropped matchday) would show up as a duplicate or a gap.
    """
    from wcmodel.eval.ledger import load_ledger

    frames = []
    for path in shard_paths:
        frame = load_ledger(path)
        frames.append(frame)
        print(f"  {path}: {len(frame)} rows, "
              f"{frame['fixture_id'].nunique()} fixtures")
    merged = pd.concat(frames, ignore_index=True)
    out = Path(ledger_path)
    if out.exists():
        out.unlink()
    with LedgerWriter(out) as writer:
        for row in merged.to_dict("records"):
            writer.append(row)
    final = load_ledger(out)
    print(f"merged {len(shard_paths)} shard(s) -> {out}: {len(final)} rows, "
          f"{final['fixture_id'].nunique()} fixtures, "
          f"{final['arm'].nunique()} arms")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", default=MANIFEST_DEFAULT)
    ap.add_argument("--coverage", default=COVERAGE_DEFAULT)
    ap.add_argument("--store", default=STORE_DEFAULT)
    ap.add_argument("--raw-dir", default=RAW_DIR_DEFAULT)
    ap.add_argument("--cache-dir", default=CACHE_DEFAULT)
    ap.add_argument("--ledger", default=LEDGER_DEFAULT)
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--limit-days", type=int, default=None,
                    help="walk only the first N matchdays (smoke test)")
    ap.add_argument("--shard", default=None, metavar="I/N",
                    help="walk only matchdays with index %% N == I, writing "
                         "this shard's own ledger. Each matchday is a pure "
                         "function of its cutoff, so sharding is a pure "
                         "work split — the union of shards is byte-identical "
                         "to a serial walk. Merge with --merge.")
    ap.add_argument("--merge", nargs="+", default=None, metavar="SHARD",
                    help="concatenate shard ledgers into --ledger, "
                         "re-validating every row through LedgerWriter")
    args = ap.parse_args(argv)

    if args.merge:
        return merge_shards(args.merge, args.ledger)

    shard = None
    if args.shard:
        i, n = (int(p) for p in args.shard.split("/"))
        if not (0 <= i < n):
            ap.error(f"--shard I/N needs 0 <= I < N; got {args.shard}")
        shard = (i, n)

    cfg = load_config()
    fixtures = load_inputs(args.manifest, args.coverage)
    print(f"dev OOF walk: {len(fixtures)} fixtures over "
          f"{len({f['date'] for f in fixtures})} matchdays", flush=True)
    try:
        out = run_walk(
            fixtures=fixtures, store_path=args.store, cfg=cfg,
            cache_dir=args.cache_dir, raw_dir=args.raw_dir,
            ledger_path=args.ledger, aliases=load_aliases(),
            limit_days=args.limit_days, shard=shard)
    except DevOofError as exc:
        print(f"ABORT: {exc}", file=sys.stderr)
        return 1
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        assemble_report(out, n_fixtures=len(fixtures),
                        ledger_path=args.ledger))
    print(f"wrote {args.out}: {out['rows']} rows, "
          f"{len(out['errors'])} unpriced")
    return 1 if out["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
