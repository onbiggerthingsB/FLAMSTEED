"""Resolve one knockout tie: regulation -> (if level) extra time at scaled rates
-> (if still level) penalties as a coin-flip. ``sample(phase, rng)`` returns a
scoreline for the requested phase ('regulation' or 'extra_time'); the caller wires
it to the per-draw RateBook (regulation rates for 'regulation', rates*et_scale for
'extra_time'). ET/penalty parameters are fixed config defaults (sim.extra_time_scale,
sim.penalty_home_prob; Phase-4-tunable), never hand-set per tie.

et_scale contract: the 30/90 ET rate-scaling is applied in the CALLER's ``sample``
(it scales the rates when ``phase == 'extra_time'``); ``resolve_tie`` only requests
the phase. ``et_scale`` stays in the signature to document that contract — the
caller (T5) passes ``cfg.sim.extra_time_scale`` here so the value lives with the tie
resolver even though the arithmetic happens in the sampler. Pure + seeded: the RNG
is passed in (used for the ET draw via ``sample`` and the shootout coin-flip); no
global state, no per-tie tilt."""
from __future__ import annotations


def resolve_tie(home, away, *, sample, rng, et_scale, pen_home_prob):
    hg, ag = sample("regulation", rng)
    if hg != ag:
        return home if hg > ag else away
    ehg, eag = sample("extra_time", rng)             # ET at scaled rates (caller applies et_scale)
    if ehg != eag:
        return home if ehg > eag else away
    return home if rng.random() < pen_home_prob else away   # shootout coin-flip
