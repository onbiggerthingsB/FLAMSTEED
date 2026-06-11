# P5 PRE-MERGE REQUIREMENT (logged 2026-06-11, user directive — do not lose)

Before `feat/p5-inference` merges to main:

1. **Cache-key canonicalization (the 2c pattern).** The new inference knobs
   (`chains`, `target_accept`, `nuts_sampler`) currently ride into the posterior
   cache key via `cfg["model"]` / explicit key params. They MUST adopt the same
   canonicalization `model/cache.py` gained in 2c (`_normalized_model_for_key`):
   **absent == advi defaults → IDENTICAL key**, so the off-state can never
   invalidate the production posterior cache (the silent-wrongness class: a
   default-config daily run must keep hitting the pre-P5 cached posterior).
   Any non-default knob value → a different key (real change, never stale-serve).

2. **Rebase over 2c's key change** (`feat/p2c-tier-weights` touches
   `model/cache.py` `_normalized_model_for_key`; 2c merges before P5) and
   **re-run the cache-related canaries on the rebased tree** at that point —
   key-equality both ways (absent == defaults; non-default != absent) plus the
   existing cache hit/miss tests.

Adoption gates (pre-registered, unchanged): held-out RPS lift beyond paired
bootstrap AND projected full daily_update <= ~60 min; RPS win + runtime blowout
=> DEEP-REFIT-ONLY CANDIDATE, recorded, not adopted for the nightly loop.
