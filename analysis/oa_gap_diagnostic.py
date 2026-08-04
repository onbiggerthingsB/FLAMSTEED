#!/usr/bin/env python
"""Where does the model lose to the market? — EXPLORATORY, not preregistered.

V10 reported one number: the market beats the incumbent model by ~0.010 RPS
across 217 fixtures. That number says the gap exists; it does not say where.
This script cuts the same fixtures by favourite strength, realised outcome,
stage, pool, and model-vs-market disagreement, so the gap becomes a list of
places to go and fix the model.

WHAT THIS IS NOT
----------------
This lives outside ``CODE_PATHS`` deliberately. It is post-hoc, chosen after
the outcomes were known, with no preregistered gate and no multiplicity
control. Nothing here can adopt anything or move a prereg'd decision. Any
stratum that looks interesting is a HYPOTHESIS to test properly later, never
a finding — with 217 fixtures split many ways, some cell will look dramatic
by chance alone, and the per-cell counts are printed so that stays visible.

The market comparator is the TRUE de-vigged book, reconstructed from the
archived cut snapshots through the same helpers the issuance priced with —
not the E' arm, which is 95% book and 5% model and would quietly flatter the
model in exactly the calibration comparison this is for.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "analysis"))

from wcmodel.data.tiers import confederation             # noqa: E402
from wcmodel.eval.aliases import load_aliases            # noqa: E402
from wcmodel.eval.ledger import load_ledger              # noqa: E402
from wcmodel.eval.oof import book_1x2                    # noqa: E402
from wcmodel.eval.regulation import load_regulation_table  # noqa: E402
from wcmodel.model.calibration import rps                # noqa: E402

from oa_dev_oof import book_prices_from_archive, DevOofError  # noqa: E402

LEDGER = _ROOT / "data" / "oa_scored_ledger.parquet"
RAW_DIR = _ROOT / "data" / "odds_raw"
OUT = _ROOT / "reports" / "oa_gap_diagnostic.md"
DEVIG = "multiplicative"          # the method V6 selected
OUTCOMES = ("home", "draw", "away")


def _verdict_module():
    spec = importlib.util.spec_from_file_location(
        "oa_verdict", _ROOT / "scripts" / "oa_verdict.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["oa_verdict"] = mod
    spec.loader.exec_module(mod)
    return mod


def build_frame() -> pd.DataFrame:
    """One row per fixture: model probs, book probs, outcome, and context."""
    ledger = load_ledger(LEDGER)
    outcomes = _verdict_module().load_outcomes(ledger)
    aliases = load_aliases()

    ko = {(r.pool, r.date, r.home, r.away)
          for r in load_regulation_table().itertuples(index=False)}

    wide = ledger.pivot_table(
        index=["fixture_id", "pool", "date", "home", "away"], columns="arm",
        values=["p_home", "p_draw", "p_away"], aggfunc="first")
    digest = (ledger.loc[ledger["odds_snapshot_hash"].notna()]
              .drop_duplicates("fixture_id")
              .set_index("fixture_id")["odds_snapshot_hash"].to_dict())

    rows = []
    for (fid, pool, date, home, away) in wide.index:
        model = {k: float(wide.loc[(fid, pool, date, home, away),
                                   (f"p_{k}", "incumbent")])
                 for k in OUTCOMES}
        sha = digest.get(fid)
        if sha is None:
            continue                      # no cut snapshot -> no comparator
        try:
            book = book_1x2(book_prices_from_archive(
                sha, home=home, away=away, aliases=aliases,
                raw_dir=RAW_DIR), method=DEVIG)
        except (DevOofError, Exception) as exc:   # noqa: BLE001 - reported
            print(f"  skip {home} v {away}: {str(exc)[:80]}")
            continue

        actual = outcomes[str(fid)]
        fav = max(book, key=book.get)     # the MARKET's favourite
        rows.append({
            "fixture_id": fid, "pool": pool, "date": date,
            "home": home, "away": away, "outcome": actual,
            "stage": "knockout" if (pool, date, home, away) in ko else "group",
            "rps_model": rps(model, actual), "rps_book": rps(book, actual),
            # The worst-10 table is dominated by teams outside the European /
            # South American core, where the model's rating history is
            # thinnest. Cut it explicitly so that stays a number rather than
            # an impression drawn from ten hand-read rows.
            "core_only": (confederation(home) in ("UEFA", "CONMEBOL")
                          and confederation(away) in ("UEFA", "CONMEBOL")),
            "confeds": "/".join(sorted({confederation(home),
                                        confederation(away)})),
            "fav_side": fav, "fav_p_book": book[fav],
            "fav_p_model": model[fav],
            # signed: how much MORE confident the model is on the market's
            # pick. Positive = model more bullish on the favourite.
            "disagree": model[fav] - book[fav],
            "p_draw_model": model["draw"], "p_draw_book": book["draw"],
            **{f"m_{k}": model[k] for k in OUTCOMES},
            **{f"b_{k}": book[k] for k in OUTCOMES},
        })
    frame = pd.DataFrame(rows)
    # delta < 0 means the BOOK scored better (lower RPS is better)
    frame["delta"] = frame["rps_book"] - frame["rps_model"]
    return frame


def _table(frame, by, label) -> list[str]:
    out = [f"### by {label}", "",
           "| stratum | n | RPS model | RPS book | book − model | model wins |",
           "|---|---|---|---|---|---|"]
    for key, grp in frame.groupby(by, observed=True):
        wins = (grp["delta"] > 0).mean()
        out.append(f"| {key} | {len(grp)} | {grp['rps_model'].mean():.4f} | "
                   f"{grp['rps_book'].mean():.4f} | "
                   f"{grp['delta'].mean():+.5f} | {wins:.0%} |")
    return out + [""]


def _calibration(frame) -> list[str]:
    """Do stated probabilities happen that often? Model vs book, side by side.

    Pooled over all three outcomes: each fixture contributes three
    (probability, hit) pairs, so a systematic over- or under-statement shows
    up as a column that drifts away from the bin it sits in.
    """
    edges = [0.0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.65, 1.01]
    recs = []
    for src, pre in (("model", "m_"), ("book", "b_")):
        for _, row in frame.iterrows():
            for k in OUTCOMES:
                recs.append({"src": src, "p": row[f"{pre}{k}"],
                             "hit": float(row["outcome"] == k)})
    cal = pd.DataFrame(recs)
    cal["bin"] = pd.cut(cal["p"], edges, right=False)
    out = ["### Calibration (all three outcomes pooled)", "",
           "NOT LOAD-BEARING. Model and book are binned separately, so the "
           "two columns rest on DIFFERENT observations (both counts shown — "
           "an earlier version printed only the model's count for both, "
           "which was factually wrong). The bands also pool all three "
           "outcome classes and carry no intervals, so this table cannot "
           "separate calibration from sharpness and supports no claim "
           "either way about miscalibration.", "",
           "| predicted band | model n | model: stated → actual | "
           "book n | book: stated → actual |", "|---|---|---|---|---|"]
    for b, grp in cal.groupby("bin", observed=True):
        m, bk = grp[grp["src"] == "model"], grp[grp["src"] == "book"]
        if not len(m) or not len(bk):
            continue
        out.append(
            f"| {b} | {len(m)} | {m['p'].mean():.3f} → {m['hit'].mean():.3f} | "
            f"{len(bk)} | {bk['p'].mean():.3f} → {bk['hit'].mean():.3f} |")
    return out + [""]


def _scrutinise_core_split(frame) -> list[str]:
    """Attack the confederation split before anyone quotes it.

    It is the most quotable cut in this file — "the model is level with the
    market in Europe" — so it gets the hardest look. Two ways it could be an
    artifact: the cells could be too small to separate, and confederation
    could be favourite-strength wearing a disguise (lopsided fixtures are
    more common outside the core, and lopsided fixtures score differently).

    Uses the tested block machinery from ``oa_stats`` — an earlier version
    resampled individual fixtures here, the same defect that was later
    repaired in the H1/H2 tests, and its narrower intervals are withdrawn.
    The exploratory difference test is TWO-SIDED: no direction was committed
    when this file was written (that happened later, for the out-of-sample
    test, whose result supersedes this section — see oa_confed_test.md).
    """
    from oa_stats import block_ci, two_group_gap

    core = frame[frame["core_only"]]
    non = frame[~frame["core_only"]]
    out = ["### Does the confederation split survive scrutiny?", "",
           "Superseded for inference by the out-of-sample test in "
           "`oa_confed_test.md` (verdict there: fails to replicate). Kept "
           "here as the exploratory cut that generated the hypothesis.", "",
           "| group | n | mean | 90% block CI |", "|---|---|---|---|"]
    for label, sub in (("both UEFA/CONMEBOL", core),
                       ("at least one outside", non)):
        mean, lo, hi = block_ci(sub)
        out.append(f"| {label} | {len(sub)} | {mean:+.5f} | "
                   f"[{lo:+.5f}, {hi:+.5f}] |")
    diff = two_group_gap(non, core, alternative="two_sided")
    out += ["", f"Difference (non-core − core): {diff.gap:+.5f}, two-sided "
            f"p {diff.p:.3f} over {diff.n_blocks} pool × matchday blocks."]

    out += ["", "Same split held at fixed favourite strength — if the effect "
            "were real and not a proxy for lopsidedness, the core column "
            "should beat the non-core column in EVERY band:", "",
            "| favourite band | non-core mean (n) | core mean (n) |",
            "|---|---|---|"]
    frame = frame.assign(band=pd.cut(
        frame["fav_p_book"], [0, 0.40, 0.50, 0.60, 0.75, 1.01],
        labels=["<40%", "40-50%", "50-60%", "60-75%", ">75%"], right=False))
    for band, grp in frame.groupby("band", observed=True):
        a, b = grp[~grp["core_only"]]["delta"], grp[grp["core_only"]]["delta"]
        out.append(f"| {band} | {a.mean():+.5f} ({len(a)}) | "
                   f"{b.mean():+.5f} ({len(b)}) |")
    return out + [""]


def main() -> int:
    frame = build_frame()
    print(f"fixtures with a book comparator: {len(frame)}")

    frame["fav_band"] = pd.cut(
        frame["fav_p_book"], [0, 0.40, 0.50, 0.60, 0.75, 1.01],
        labels=["<40%", "40-50%", "50-60%", "60-75%", ">75%"], right=False)
    frame["disagree_band"] = pd.cut(
        frame["disagree"], [-1.01, -0.10, -0.04, 0.04, 0.10, 1.01],
        labels=["model much lower", "model lower", "agree (±4pp)",
                "model higher", "model much higher"], right=False)

    lines = [
        "# Where the model loses to the market — exploratory diagnostic", "",
        "**Not preregistered.** Post-hoc strata chosen after outcomes were "
        "known, no gate, no multiplicity control. Anything striking here is a "
        "hypothesis for a future prereg'd test, not a finding. Cell counts "
        "are shown because with "
        f"{len(frame)} fixtures cut this many ways, some cell will look "
        "dramatic by chance.", "",
        "Comparator is the TRUE de-vigged book "
        f"(`{DEVIG}`) from the archived cut snapshots, not the E' arm. "
        "Lower RPS is better, so a NEGATIVE `book − model` means the market "
        "won that stratum.", "",
        f"Overall: model {frame['rps_model'].mean():.4f}, "
        f"book {frame['rps_book'].mean():.4f}, "
        f"difference {frame['delta'].mean():+.5f}, "
        f"model wins {(frame['delta'] > 0).mean():.0%} of fixtures.", "",
        "That win rate is the first thing worth noticing: the model is not "
        "uniformly worse. It takes nearly half the individual fixtures and "
        "loses the aggregate through a fat tail of catastrophic misses — so "
        "the question is which fixtures blow up, not whether the model is "
        "broadly miscalibrated.", "",
    ]
    frame["core_label"] = np.where(
        frame["core_only"], "both UEFA/CONMEBOL", "at least one outside")
    lines += _table(frame, "core_label",
                    "confederation (rating-history depth)")
    lines += _table(frame, "fav_band", "market favourite strength")
    lines += _table(frame, "outcome", "realised outcome")
    lines += _table(frame, "stage", "stage")
    lines += _table(frame, "pool", "pool")
    lines += _table(frame, "disagree_band",
                    "model-vs-market disagreement on the market's favourite")
    lines += _calibration(frame)
    lines += _scrutinise_core_split(frame)

    worst = frame.nsmallest(10, "delta")
    lines += ["### The 10 fixtures the model lost worst", "",
              "| fixture | pool | outcome | model | book | book − model |",
              "|---|---|---|---|---|---|"]
    for r in worst.itertuples(index=False):
        lines.append(f"| {r.home} v {r.away} | {r.pool} | {r.outcome} | "
                     f"{r.rps_model:.4f} | {r.rps_book:.4f} | {r.delta:+.5f} |")
    lines.append("")

    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
