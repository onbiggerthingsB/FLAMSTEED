from __future__ import annotations
from wcmodel.dashboard.provenance import _git_rev

VALUE_SCHEMA_VERSION = 1
_NOT_REAL_BANNER = ("NOT REAL — signal-only +EV scan. No bet is placed by this system; "
                    "you execute manually. Edges are point-in-time; soft books move/limit fast.")
_REQUIRED = {"event", "market", "side", "sharp_fair_prob", "soft_book", "soft_odds",
             "edge", "bettable", "flags"}

def build_value_bundle(scan_result: dict, *, scan_ts: str, sharp: str, regions: str,
                       credits_used: int, credits_remaining: int) -> dict:
    prov = {"scan_ts": scan_ts, "sharp_book": sharp, "regions": regions,
            "credits_used": int(credits_used), "credits_remaining": int(credits_remaining),
            "git": _git_rev(), "schema_version": VALUE_SCHEMA_VERSION,
            "signal_only": True, "is_synthetic": True, "banner": _NOT_REAL_BANNER}
    return {"provenance": prov, "data": scan_result}

def gate_value(bundle: dict) -> None:
    p = bundle.get("provenance", {})
    if not (p.get("signal_only") is True and p.get("is_synthetic") is True and p.get("banner")):
        raise ValueError("value bundle: missing signal_only / NON-REAL provenance stamp")
    data = bundle.get("data", {})
    for key in ("bettable", "filtered", "coverage_gaps"):
        if not isinstance(data.get(key), list):
            raise ValueError(f"value bundle: data.{key} must be a list")
    for node in data["bettable"] + data["filtered"]:
        missing = _REQUIRED - set(node)
        if missing:
            raise ValueError(f"value bundle: ValueBet node missing {sorted(missing)}: {node!r}")
