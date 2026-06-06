"""Dashboard data layer: provenance-stamped, leakage-safe JSON snapshots over the
Phase 1-5 model outputs (read-only; the frontend renders these). NON-REAL by default
(synthetic-odds posture, spec §D5)."""

DRY_RUN_BANNER = (
    "DRY-RUN · SYNTHETIC ODDS · NOT REAL — no real odds were sourced, "
    "no bet was placed, and no number here is a real CLV/ROI claim."
)
