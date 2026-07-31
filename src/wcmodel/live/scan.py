"""The live scanner (Phase-5 §2.4) — ``scan(cutoff=now, …) -> Ranked``.

Ranks live opportunities by EDGE x LIQUIDITY (the north-star headline deliverable).
Edge comes from the live decision (``decide_live``, Task 3); liquidity from the feed
where available (thin/illiquid markets are down-ranked, and an absent-odds surface is
a COVERAGE GAP, never a number).

BOTH SURFACES (L4):
  * 1X2 (``h2h``) — PRIMARY / authoritative. Each bettable event yields an opportunity
    {event_key, staked, edge, liquidity, stake-signal, entry/close odds}, ranked by
    edge x liquidity descending. Non-bet filters (sign-flip/stale) exclude an event
    from the ranking (counted in ``non_bets``).
  * tournament-progression / outright (``SimResult`` columns) — SECONDARY,
    COVERAGE-GATED. Outright odds keys are unverified, so without supplied outright
    odds the surface renders as an explicit COVERAGE GAP ("insufficient coverage …"),
    NEVER a CLV/edge number. (The model progression probability is available from
    ``simulate(now)`` but is only an OPPORTUNITY when matched to a real outright price.)

BATCH GUARD (T3's deferred concern, now T5's job). The scanner iterates MANY fixtures;
a malformed / odds-less / ``decide_live``-RAISING single fixture must be a COUNTED
non-bet (caught, reason recorded, the fixture skipped), NEVER a run-aborting crash.
This is the live analog of the Phase-4 ``walkforward`` Stage-1 try/except batch loop
(``_bump("no_odds"); continue``): one bad fixture in a batch is counted and the GOOD
fixtures still rank.

Output: a structured ``Ranked`` artifact + a written report (``render_scan_report`` —
NO UI). DRY-RUN: every artifact + report is labelled non-real (the synthetic taint
propagates), mirroring the Phase-4 synthetic discipline.

SIGNAL-ONLY (L2): the ranked stake is a RECOMMENDATION; nothing is placed.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from wcmodel.config import load_config
from wcmodel.backtest.walkforward import _sample_is_synthetic
from wcmodel.data.sources.odds import event_list
from wcmodel.live.decide import decide_live

_DRY_RUN_BANNER = (
    "DRY-RUN — NOT REAL ODDS / NOT AN EDGE CLAIM (Phase-5 synthetic/fixture harness; "
    "no real number until the feed is funded + flipped on)"
)


@dataclass
class Ranked:
    """The structured scan artifact. ``opportunities`` is the edge x liquidity-ranked
    1X2 list (PRIMARY); ``progression_surface`` is the SECONDARY coverage-gated
    outright surface; ``non_bets`` counts each filter reason; ``is_synthetic`` taints
    the whole artifact if any input was non-real (dry-run)."""

    cutoff: str
    primary_surface: str = "1x2"
    opportunities: list = field(default_factory=list)
    progression_surface: dict = field(default_factory=dict)
    non_bets: dict = field(default_factory=dict)
    #: The batch-guard exception SIDECAR (diagnostics). The ``non_bets["malformed"]``
    #: counter says HOW MANY fixtures the broad guard caught; this list says WHAT
    #: killed each — ``{"event": <id|event_key|None>, "error": repr(exception)}`` per
    #: caught fixture, in input order. A SYSTEMIC bug (every fixture dying on the same
    #: error) is thereby VISIBLE instead of masquerading as generic "malformed" input.
    errors: list = field(default_factory=list)
    is_synthetic: bool = False
    signal_only: bool = True

    def to_dict(self) -> dict:
        return {"cutoff": self.cutoff, "primary_surface": self.primary_surface,
                "opportunities": self.opportunities,
                "progression_surface": self.progression_surface,
                "non_bets": self.non_bets, "errors": self.errors,
                "is_synthetic": self.is_synthetic,
                "signal_only": self.signal_only}


def rank_key(opportunity: dict) -> float:
    """The ranking score: ``edge x liquidity`` (higher = a better opportunity)."""
    return float(opportunity["edge"]) * float(opportunity["liquidity"])


def _event_id(item: dict):
    """Best-effort event IDENTIFIER for the batch-guard error sidecar — NEVER raises.

    A malformed fixture is, by definition, one the parse path chokes on, so this is a
    defensive scan: it tries the Odds-API ``id`` nested in the first snapshot's first
    event (``data`` a LIST of events or ONE bare event dict — the per-event historical
    route — normalized via ``odds.event_list``), then a top-level ``event_id``/``id``
    on the sample, then the ``(home, away, commence)`` identity triple — and returns
    ``None`` if nothing is legible. Used ONLY to LOCATE a systemic failure, so a
    missing id degrades to ``None`` rather than masking the recorded exception.
    """
    try:
        sample = item.get("sample", item)
        if not isinstance(sample, dict):
            return None
        for v in sample.values():
            if isinstance(v, dict) and isinstance(v.get("data"), (dict, list)) and v["data"]:
                ev = event_list(v["data"])[0]
                if isinstance(ev, dict):
                    if ev.get("id") is not None:
                        return ev["id"]
                    h, a, c = ev.get("home_team"), ev.get("away_team"), ev.get("commence_time")
                    if h is not None and a is not None:
                        return f"{h} vs {a} @ {c}"
        for k in ("event_id", "id"):
            if sample.get(k) is not None:
                return sample[k]
    except Exception:
        return None
    return None


def scan(store, items: list[dict], *, cutoff, config: dict | None = None,
         fit_kwargs: dict | None = None) -> Ranked:
    """Rank live opportunities at ``cutoff = now`` by edge x liquidity -> ``Ranked``.

    ``items`` is a list of ``{"sample": <snapshot mapping>, "liquidity": float}`` (the
    fixture / synthetic harness + a per-event liquidity from the feed). Each is run
    through ``decide_live``; bettable events become ranked opportunities; non-bets are
    counted. The progression surface is coverage-gated (no outright odds in dry-run).

    BATCH GUARD: a single malformed / odds-less / ``decide_live``-raising ``item`` is
    caught, counted as a ``"malformed"`` non-bet, and skipped — the run COMPLETES and
    the good fixtures still rank (the live analog of the Phase-4 ``walkforward``
    Stage-1 guarded batch loop). One bad apple never aborts the scan.
    """
    cfg = config or load_config()
    live = cfg["live"]
    min_liq = float(live["scan"]["min_liquidity"])

    opportunities: list[dict] = []
    non_bets: dict[str, int] = {}
    errors: list[dict] = []
    any_synth = False

    def _bump(reason: str) -> None:
        non_bets[reason] = non_bets.get(reason, 0) + 1

    for item in items:
        # MONEY-SAFETY (rider #1, Codex HIGH): detect the synthetic taint PER-SAMPLE
        # BEFORE the guarded `decide_live`. `decide_live` only stamps `is_synthetic`
        # on a SUCCESSFUL decision, so an ALL-MALFORMED synthetic batch (every
        # `decide_live` raises) would otherwise return `is_synthetic=False` with NO
        # dry-run banner — a synthetic/dry-run scan mistakable for real. Reusing the
        # Phase-4 `_sample_is_synthetic` (the wrapper `is_synthetic`/`_is_synthetic`
        # flag OR a nested snapshot's `_is_synthetic`), even a malformed synthetic
        # fixture taints the whole run non-real. Pure dict inspection, never raises.
        try:
            if _sample_is_synthetic(item):
                any_synth = True
        except Exception:
            pass

        # --- Stage 1: per-fixture decision (GUARDED). ---
        # `decide_live` parses the snapshot, fits the as-of model, and prices the edge;
        # a malformed item (missing "sample", a sample with no snapshots, an odds-less
        # snapshot, a fit/sim that raises) MUST be a COUNTED non-bet, never a crash that
        # aborts the whole batch. Mirrors walkforward Stage-1 (`_bump("no_odds")`).
        try:
            sample = item["sample"]
            liquidity = float(item.get("liquidity", 0.0))
            d = decide_live(store, sample, cutoff=cutoff, config=cfg,
                            fit_kwargs=fit_kwargs)
        except Exception as e:
            # One bad fixture is counted + skipped; the run continues and good ones rank.
            # DIAGNOSTICS: RECORD the actual exception (not swallow it opaquely) so a
            # SYSTEMIC bug — every fixture dying on the SAME error — is VISIBLE in the
            # artifact rather than masquerading as generic "malformed" input. The
            # `malformed` COUNTER is kept intact; the sidecar adds {event id, repr}.
            _bump("malformed")
            errors.append({"event": _event_id(item), "error": repr(e)})
            continue

        any_synth = any_synth or d.is_synthetic
        if d.non_bet_reason is not None:
            _bump(d.non_bet_reason)
            continue
        # Thin/illiquid markets below the floor are a coverage gap, not an opportunity.
        if liquidity < min_liq:
            _bump("thin_liquidity")
            continue
        opportunities.append({
            "event_key": d.event_key, "staked": d.staked, "edge": d.edge[d.staked],
            "liquidity": liquidity, "stake_signal": d.stake,
            "entry_odds": d.entry_odds[d.staked], "close_odds": d.close_odds[d.staked],
            "model": d.model,
            # The de-vigged ENTRY market 1X2 the LiveDecision already computed
            # (`market_fair_1x2(ENTRY odds)`) — the SAME de-vigged ENTRY that DROVE the edge
            # (`edge = model_fair - market_entry`). Carried so the dashboard can ghost the
            # sharp line into the win-bar (a DERIVED comparison, leakage-safe: the ENTRY is
            # <= cutoff, NEVER the close). The dashboard edge node re-gates + emits it.
            "market_1x2": dict(d.market_entry),
            "is_synthetic": d.is_synthetic,
        })

    opportunities.sort(key=rank_key, reverse=True)

    # SECONDARY surface: progression/outright is coverage-gated. Without supplied
    # outright odds (the dry-run norm), it is an explicit COVERAGE GAP, never a number.
    progression_surface = {
        "coverage_gap": True,
        "render": "insufficient coverage (no outright odds supplied — progression "
                  "surface is secondary + coverage-gated; outright keys unverified)",
        "is_synthetic": any_synth,
    }

    return Ranked(
        cutoff=str(cutoff), primary_surface="1x2", opportunities=opportunities,
        progression_surface=progression_surface, non_bets=non_bets, errors=errors,
        is_synthetic=any_synth, signal_only=bool(live["signal_only"]),
    )


def render_scan_report(ranked: Ranked) -> str:
    """Render the ranked scan as a written report (NO UI), leading with the non-real
    banner when synthetic/dry-run. Lists each 1X2 opportunity (edge, liquidity, the
    edge x liquidity score, the stake SIGNAL) + the coverage-gapped progression surface."""
    lines: list[str] = []
    if ranked.is_synthetic:
        lines.append(f"# {_DRY_RUN_BANNER}")
        lines.append("")
    lines.append(f"# Live scan @ cutoff={ranked.cutoff} (PRIMARY surface: {ranked.primary_surface})")
    lines.append("SIGNAL-ONLY / PAPER — no bet is placed; the stake is a recommendation.")
    lines.append("")
    lines.append("## 1X2 opportunities (ranked by edge x liquidity)")
    if not ranked.opportunities:
        lines.append("(no bettable 1X2 opportunities at this cutoff)")
    for i, o in enumerate(ranked.opportunities, 1):
        lines.append(
            f"{i}. {o['event_key']} stake={o['staked']} edge={o['edge']:+.4f} "
            f"liquidity={o['liquidity']:.2f} score(edge x liquidity)={rank_key(o):+.4f} "
            f"stake_signal={o['stake_signal']:.4f} entry={o['entry_odds']} close={o['close_odds']}"
        )
    lines.append("")
    lines.append("## Tournament-progression / outright (SECONDARY, coverage-gated)")
    lines.append(ranked.progression_surface["render"])
    lines.append("")
    lines.append("## Non-bets (filtered, counted — never silently dropped)")
    lines.append(str(ranked.non_bets) if ranked.non_bets else "(none)")
    return "\n".join(lines)
