"""Sidecars that make a bridge arm re-derivable from its own issuance (v1.1 R2).

WHAT THIS CLOSES. ``simcli check`` re-runs a written issuance and demands the
same numbers back. It could only ever do that for ``dc_native``, because the
particle book beside the issuance IS that arm: reload ``particles.npz``, re-run,
compare. The two bridge arms are not in the book. ``dc_wdl_bridge`` additionally
needs the fitted :class:`epl.bridge.EmpiricalBridge`; ``elo_wdl_bridge`` needs
neither the book nor the posterior but does need the rating table at the cutoff
and the ordered-logit head fitted on pre-cutoff history. None of that was
written down, so once the process that issued a bridge forecast exited, its
numbers could not be checked by anything — which makes them an assertion, not a
result.

WHAT IS PERSISTED, AND WHY IT IS NOT A CACHE OF THE ANSWER. Three JSON sidecars
land beside the issuance, never replacing or touching a file the forecast
already writes:

``bridge.json``
    the bridge's RAW COUNTS (the evidence), its cutoff, grid bound and row
    counts, its derived cdf, and its content hash.
``elo_arm.json``
    the Elo arm's rating table, its ordered-logit parameters, the fixture ids it
    priced, the 1X2 row it priced each with, and its content hash.
``arms.json``
    the book hash, the provisional and cold-start sets, and each bridge arm's
    provider content hash.

On the way back in, nothing is trusted. The bridge is REBUILT from its counts
through :class:`epl.bridge.EmpiricalBridge`'s own constructor — which recomputes
the pmf, the cdf and the hash — and the persisted cdf is then checked against
the rebuilt one. The Elo probabilities are RE-DERIVED from the ratings and the
head through :func:`epl.ordlogit.predict` and then checked against the persisted
row. So an edited cdf cell fails the cdf comparison, an edited count fails the
hash, an edited rating or head parameter fails the derivation — and the provider
that goes on to be simulated is the rebuilt one, not the persisted numbers.

WHAT THE REBUILD IS ANCHORED TO. A bundle checked only against ITSELF is not
evidence. Doubling every count in ``bridge.json`` leaves the cdf exactly where it
was — the pmf is counts divided by its own row total — so an editor who also
rewrites that file's ``hash`` field and the arm hashes in ``arms.json`` produces
a bundle that is internally coherent from end to end and describes a bridge that
was never fitted. Every rebuild is therefore held against the hashes
``issuance.json`` RECORDED when the forecast was issued: ``bridge_hash``,
``provider_hashes[arm]`` and ``arms_manifest_hash``. Those sit in a file the
sidecars do not write, and the doubled-count bundle fails on the first of them.
A caller with no issuance record — a unit test, an ad-hoc rebuild — passes no
anchors and gets the internal checks alone; ``simcli check``, which always has
the record, always passes them, and reports an anchor the record does not carry
as unanchored rather than as agreement.

NOTHING IS DECODED LENIENTLY. ``numpy`` reads 7.5 into an ``int64`` array by
truncating it, and NaN passes every ``|a - b| <= tol`` comparison because a
comparison against NaN is False — so a lenient decode turns two of the tampers
this module exists to catch into silent agreement. Counts must be non-negative
integers; every cdf entry, probability, rating and head parameter must be a
finite number; and a payload that is not a JSON object, or a rating that is not
a number, is a refusal naming the arm and the file rather than a traceback out
of the decoder.

FAIL CLOSED. A sidecar that is absent, carries the wrong schema version, or
describes a different fixture set is a refusal naming the file and the arm. An
issuance written before this module existed therefore cannot have its bridge
arms checked, and says so, rather than reporting a check that did not happen.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from epl import bridge as bridge_mod, ordlogit

__all__ = ["BundleError", "ARM_SIDECARS", "ARMS_SIDECAR", "BRIDGE_SIDECAR",
           "ELO_SIDECAR", "ISSUANCE_RECORD", "write_sidecars", "read_arms",
           "read_bridge", "rebuild_provider", "missing_sidecars",
           "manifest_hash", "arms_manifest_hash", "recorded_anchors"]

BRIDGE_SIDECAR = "bridge.json"
ELO_SIDECAR = "elo_arm.json"
ARMS_SIDECAR = "arms.json"

#: The file whose recorded hashes the rebuild is anchored to. Named here so the
#: refusals can say where the number they disagree with came from.
ISSUANCE_RECORD = "issuance.json"

BRIDGE_SCHEMA = "epl-bridge-sidecar-1"
ELO_SCHEMA = "epl-elo-sidecar-1"
ARMS_SCHEMA = "epl-arm-sidecar-1"

#: Which sidecars each arm needs to be rebuilt. ``dc_native`` needs none — the
#: particle book the issuance already writes is the whole of that arm — and that
#: emptiness is asserted by a test, so the native path cannot acquire a
#: dependency on this module without the test failing.
ARM_SIDECARS: dict[str, tuple[str, ...]] = {
    "dc_native": (),
    "dc_wdl_bridge": (ARMS_SIDECAR, BRIDGE_SIDECAR),
    "elo_wdl_bridge": (ARMS_SIDECAR, BRIDGE_SIDECAR, ELO_SIDECAR),
}

#: Comparison tolerance for a re-derived quantity against its persisted twin.
#: The derivation is deterministic and JSON round-trips a float64 exactly, so
#: the honest tolerance is zero; this is a hair above it so a future platform
#: difference in the last bit reads as agreement rather than as tampering, while
#: any perturbation a human could make is still caught by many orders of
#: magnitude.
DERIVED_ATOL = 1e-12


class BundleError(RuntimeError):
    """A sidecar is missing, malformed, or does not describe what it claims."""


# ==========================================================================
# 0. strict decoding — a malformed sidecar is a refusal, never a traceback
# ==========================================================================
def _mapping(payload, *, arm: str, name: str, what: str = "") -> dict:
    """``payload`` as a JSON object, or a refusal naming the arm and the file."""
    if not isinstance(payload, dict):
        raise BundleError(
            f"{arm}: {name}{what} is a {type(payload).__name__}, not a JSON "
            "object; a sidecar that is not a mapping does not describe an arm "
            "and nothing is rebuilt from it")
    return payload


def _field(payload: dict, key: str, *, arm: str, name: str):
    if key not in payload:
        raise BundleError(
            f"{arm}: {name} carries no {key!r}, so the arm cannot be re-derived "
            "from it; the sidecar is malformed or is not this arm's")
    return payload[key]


def _number(value, *, arm: str, name: str, field: str) -> float:
    """A FINITE real number.

    Finiteness is checked here rather than left to the comparison downstream:
    every comparison in this module is ``|persisted - derived| <= tol``, and any
    comparison against NaN is False, so a NaN cell would be read as agreement by
    the very check that exists to catch an edit.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BundleError(
            f"{arm}: {name}'s {field} is {value!r}, which is not a number")
    out = float(value)
    if not math.isfinite(out):
        raise BundleError(
            f"{arm}: {name}'s {field} is {value!r} — a non-finite value is never "
            "a probability, a cumulative mass, a rating or a head parameter, "
            "and it would pass every |a - b| <= tol comparison silently")
    return out


def _count(value, *, arm: str, name: str, field: str) -> int:
    """A NON-NEGATIVE INTEGER count.

    Refused rather than rounded: ``np.asarray([7.5], np.int64)`` is 7, so a
    lenient decode would rebuild a bridge from evidence nobody wrote down and
    then hash it as if it were the fitted one.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise BundleError(
            f"{arm}: {name}'s {field} is {value!r}, which is not an integer; a "
            "count of matches is evidence and is refused rather than truncated "
            "on the way in")
    if value < 0:
        raise BundleError(
            f"{arm}: {name}'s {field} is {value!r}, and a count of matches is "
            "never negative")
    return int(value)


def _rows(value, *, arm: str, name: str, field: str) -> list[list]:
    """``value`` as a rectangular list of lists, or a refusal."""
    if not isinstance(value, list) or not value:
        raise BundleError(
            f"{arm}: {name}'s {field} is {type(value).__name__}, expected a "
            "non-empty list of rows")
    width: int | None = None
    for i, row in enumerate(value):
        if not isinstance(row, list):
            raise BundleError(
                f"{arm}: {name}'s {field}[{i}] is {type(row).__name__}, "
                "expected a list")
        if width is None:
            width = len(row)
        elif len(row) != width:
            raise BundleError(
                f"{arm}: {name}'s {field} is ragged — row {i} has {len(row)} "
                f"entries and row 0 has {width}")
    return value


def _int_grid(value, *, arm: str, name: str, field: str) -> np.ndarray:
    return np.asarray(
        [[_count(v, arm=arm, name=name, field=f"{field}[{i}][{j}]")
          for j, v in enumerate(row)]
         for i, row in enumerate(_rows(value, arm=arm, name=name, field=field))],
        dtype=np.int64)


def _float_grid(value, *, arm: str, name: str, field: str) -> np.ndarray:
    return np.asarray(
        [[_number(v, arm=arm, name=name, field=f"{field}[{i}][{j}]")
          for j, v in enumerate(row)]
         for i, row in enumerate(_rows(value, arm=arm, name=name, field=field))],
        dtype=float)


def _float_map(value, *, arm: str, name: str, field: str) -> dict[str, float]:
    mapping = _mapping(value, arm=arm, name=name, what=f"'s {field}")
    return {str(k): _number(v, arm=arm, name=name, field=f"{field}[{k!r}]")
            for k, v in mapping.items()}


def _checked_map(value, *, arm: str, name: str, field: str) -> dict[str, Any]:
    """Every value checked as a finite number, and left at the type it arrived as.

    The head parameters ride into the arm's content hash through
    ``OrdLogitParams.as_dict()``, where ``600`` and ``600.0`` are different
    canonical JSON. Validating in place rather than coercing is what keeps a
    rebuilt provider hashing to the published one.
    """
    mapping = _mapping(value, arm=arm, name=name, what=f"'s {field}")
    for key, entry in mapping.items():
        _number(entry, arm=arm, name=name, field=f"{field}[{key!r}]")
    return {str(k): v for k, v in mapping.items()}


# ==========================================================================
# 1. writing
# ==========================================================================
def write_sidecars(directory, *, arms: Sequence[str], bridge, book,
                   providers: dict[str, Any],
                   fit_info: dict | None = None) -> list[Path]:
    """Persist what the bridge arms need, and return the paths written.

    A forecast that ran ``dc_native`` alone writes nothing: the arm needs no
    sidecar, and inventing one would put a file in the issuance that no check
    ever reads.
    """
    directory = Path(directory)
    needed = {name for arm in arms for name in ARM_SIDECARS.get(arm, ())}
    if not needed:
        return []
    if bridge is None:
        raise BundleError(
            f"arms {sorted(set(arms) & set(ARM_SIDECARS) - {'dc_native'})} need "
            "the fitted bridge to be persisted, and none was supplied")

    written: list[Path] = []
    if BRIDGE_SIDECAR in needed:
        written.append(_write(directory / BRIDGE_SIDECAR, {
            "schema": BRIDGE_SCHEMA,
            "hash": bridge.content_hash(),
            "cutoff": str(bridge.cutoff),
            "max_goals": int(bridge.max_goals),
            "n_rows": int(bridge.n_rows),
            "n_excluded": int(bridge.n_excluded),
            "counts": np.asarray(bridge.counts, np.int64).tolist(),
            # derived, and checked against the rebuild rather than used by it
            "cdf": np.asarray(bridge.cdf, float).tolist(),
        }))

    if ELO_SIDECAR in needed:
        elo = providers.get("elo_wdl_bridge")
        if elo is None:
            raise BundleError(
                "elo_wdl_bridge was requested but its provider was not supplied; "
                "the rating table and the head cannot be persisted from nothing")
        written.append(_write(directory / ELO_SIDECAR, {
            "schema": ELO_SCHEMA,
            "content_hash": elo.content_hash(),
            "cutoff": str(elo.cutoff),
            "n_fit_rows": int(elo.n_fit_rows),
            "n_particles": int(elo.n_particles),
            "params": None if elo.params is None else elo.params.as_dict(),
            "ratings": {str(k): float(v) for k, v in sorted(elo.ratings.items())},
            "fixture_ids": list(elo.fixture_ids),
            "probs": np.asarray(elo.probs, float).tolist(),
        }))

    if ARMS_SIDECAR in needed:
        info = fit_info or {}
        written.append(_write(directory / ARMS_SIDECAR, {
            "schema": ARMS_SCHEMA,
            "book_hash": book.content_hash(),
            "provisional_teams": sorted(str(t) for t in book.provisional),
            "cold_start_teams": sorted(str(t) for t in
                                       info.get("cold_start_teams", ())),
            "arms": {arm: {"content_hash": providers[arm].content_hash()}
                     for arm in arms
                     if arm != "dc_native" and arm in providers},
        }))
    return written


def _write(path: Path, payload: dict) -> Path:
    from epl import leaguesim

    path.write_text(leaguesim.canonical_json(payload) + "\n")
    return path


def manifest_hash(payload) -> str:
    """sha256 over the arms manifest's canonical CONTENT.

    Content, not bytes: a reader that re-serialises the file gets the same hash,
    and only an edit to what the manifest SAYS moves it.
    """
    from epl import leaguesim

    try:
        canonical = leaguesim.canonical_json(payload)
    except (TypeError, ValueError) as exc:
        raise BundleError(
            f"{ARMS_SIDECAR} cannot be canonicalised, so it cannot be held "
            f"against a recorded hash ({exc})") from exc
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def arms_manifest_hash(directory) -> str | None:
    """The arms manifest's content hash beside an issuance, or ``None``.

    Recorded in ``issuance.json`` at issue time, so a later check can hold the
    manifest against the run that wrote it instead of only against itself.
    """
    path = Path(directory) / ARMS_SIDECAR
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise BundleError(
            f"{ARMS_SIDECAR} is not valid JSON ({exc})") from exc
    return manifest_hash(payload)


def recorded_anchors(record: dict) -> dict:
    """The hashes ``issuance.json`` recorded, shaped for :func:`rebuild_provider`.

    An anchor an older record does not carry comes back ``None``: it anchors
    nothing, and the caller reports it as unanchored rather than as agreement.
    """
    return {"bridge_hash": record.get("bridge_hash"),
            "arms_manifest_hash": record.get("arms_manifest_hash"),
            "provider_hashes": dict(record.get("provider_hashes") or {})}


# ==========================================================================
# 2. reading — nothing is trusted
# ==========================================================================
def missing_sidecars(arm: str, directory) -> list[str]:
    """Which of ``arm``'s sidecars are absent from ``directory``."""
    directory = Path(directory)
    return [name for name in ARM_SIDECARS.get(arm, ())
            if not (directory / name).exists()]


def _load(directory, name: str, schema: str, arm: str) -> dict:
    path = Path(directory) / name
    if not path.exists():
        raise BundleError(
            f"{arm}: {name} is not in {path.parent}, so this arm cannot be "
            "re-derived from its own bundle. An issuance written before the "
            "sidecars existed cannot be checked for this arm; re-issue it, or "
            "check the arms that carry what they need.")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise BundleError(f"{arm}: {name} is not valid JSON ({exc})") from exc
    payload = _mapping(payload, arm=arm, name=name)
    got = payload.get("schema")
    if got != schema:
        raise BundleError(
            f"{arm}: {name} carries schema {got!r}, expected {schema!r}; a "
            "sidecar of another version is not this one and is not read")
    return payload


def read_arms(directory, *, arm: str = "arms",
              expect_hash: str | None = None) -> dict:
    """The arms manifest: book hash, provisional/cold-start sets, arm hashes.

    ``expect_hash`` is the manifest hash ``issuance.json`` recorded. With it, an
    edit anywhere in the manifest — including to the arm hashes an editor would
    have to rewrite to make a doctored bridge look coherent — is refused.
    """
    payload = _load(directory, ARMS_SIDECAR, ARMS_SCHEMA, arm)
    if expect_hash is not None:
        got = manifest_hash(payload)
        if got != expect_hash:
            raise BundleError(
                f"{arm}: {ARMS_SIDECAR} hashes to {got}, not to the "
                f"{expect_hash} recorded in {ISSUANCE_RECORD} — the manifest "
                "beside this issuance is not the one the forecast wrote")
    return payload


def read_bridge(directory, *, arm: str = "bridge",
                expect_hash: str | None = None) -> bridge_mod.EmpiricalBridge:
    """Rebuild the bridge from its COUNTS and check what it hashes to.

    The counts are the evidence and the cdf is a function of them, so the
    rebuild goes through the constructor and the persisted cdf is then compared
    with what came out. Perturb a count and the recomputed content hash moves;
    perturb a cdf cell and it disagrees with the rebuild. Neither survives.

    Neither, on its own, survives a COHERENT edit: doubling every count leaves
    the cdf identical, so an editor who also rewrites this file's ``hash`` passes
    both checks. ``expect_hash`` is the ``bridge_hash`` ``issuance.json``
    recorded at issue time, and that edit fails against it.
    """
    payload = _load(directory, BRIDGE_SIDECAR, BRIDGE_SCHEMA, arm)
    counts = _int_grid(_field(payload, "counts", arm=arm, name=BRIDGE_SIDECAR),
                       arm=arm, name=BRIDGE_SIDECAR, field="counts")
    try:
        rebuilt = bridge_mod.EmpiricalBridge(
            counts=counts,
            max_goals=_count(_field(payload, "max_goals", arm=arm,
                                    name=BRIDGE_SIDECAR),
                             arm=arm, name=BRIDGE_SIDECAR, field="max_goals"),
            cutoff=str(_field(payload, "cutoff", arm=arm, name=BRIDGE_SIDECAR)),
            n_rows=_count(_field(payload, "n_rows", arm=arm,
                                 name=BRIDGE_SIDECAR),
                          arm=arm, name=BRIDGE_SIDECAR, field="n_rows"),
            n_excluded=_count(_field(payload, "n_excluded", arm=arm,
                                     name=BRIDGE_SIDECAR),
                              arm=arm, name=BRIDGE_SIDECAR,
                              field="n_excluded"))
    except (KeyError, TypeError, ValueError, bridge_mod.BridgeError) as exc:
        raise BundleError(
            f"{arm}: {BRIDGE_SIDECAR} does not describe a bridge ({exc})") from exc

    if rebuilt.content_hash() != payload.get("hash"):
        raise BundleError(
            f"{arm}: the bridge rebuilt from {BRIDGE_SIDECAR}'s counts hashes to "
            f"{rebuilt.content_hash()}, not to the recorded "
            f"{payload.get('hash')} — the counts are not the ones that were "
            "fitted")

    if expect_hash is not None and rebuilt.content_hash() != expect_hash:
        raise BundleError(
            f"{arm}: the bridge rebuilt from {BRIDGE_SIDECAR}'s counts hashes to "
            f"{rebuilt.content_hash()}, not to the {expect_hash} recorded as "
            f"`bridge_hash` in {ISSUANCE_RECORD} — this bundle is coherent with "
            "itself and is not the bridge this issuance was priced with. "
            "Doubling every count leaves the cdf untouched and can be made to "
            "agree with a rewritten sidecar hash; it cannot be made to agree "
            "with the hash the forecast recorded.")

    persisted = _float_grid(_field(payload, "cdf", arm=arm, name=BRIDGE_SIDECAR),
                            arm=arm, name=BRIDGE_SIDECAR, field="cdf")
    if persisted.shape != rebuilt.cdf.shape:
        raise BundleError(
            f"{arm}: {BRIDGE_SIDECAR}'s cdf is {persisted.shape}, expected "
            f"{rebuilt.cdf.shape}")
    delta = np.abs(persisted - rebuilt.cdf)
    if delta.max(initial=0.0) > DERIVED_ATOL:
        outcome, cell = np.unravel_index(int(np.argmax(delta)), delta.shape)
        raise BundleError(
            f"{arm}: {BRIDGE_SIDECAR}'s cdf disagrees with the one rebuilt from "
            f"its counts — worst cell [{outcome}, {cell}] off by "
            f"{delta.max():.3g}. The persisted cdf was edited, or it is not this "
            "bridge's.")
    return rebuilt


def _read_elo(directory, state, bridge, *, n_particles: int | None,
              arm: str = "elo_wdl_bridge") -> bridge_mod.EloOutcomeProvider:
    """Rebuild the Elo arm by RE-DERIVING every probability it priced with."""
    payload = _load(directory, ELO_SIDECAR, ELO_SCHEMA, arm)

    fixtures = [state.fixtures[fid] for fid in sorted(state.fixtures)]
    expected = [f.fixture_id for f in fixtures]
    recorded_ids = payload.get("fixture_ids")
    if not isinstance(recorded_ids, list):
        raise BundleError(
            f"{arm}: {ELO_SIDECAR}'s fixture_ids is "
            f"{type(recorded_ids).__name__}, expected a list")
    recorded = [str(f) for f in recorded_ids]
    if recorded != expected:
        extra = sorted(set(recorded) - set(expected))
        absent = sorted(set(expected) - set(recorded))
        raise BundleError(
            f"{arm}: {ELO_SIDECAR} priced a different fixture set — "
            f"{len(recorded)} recorded vs {len(expected)} in the season state"
            + (f"; not in the state: {extra[:5]}" if extra else "")
            + (f"; missing: {absent[:5]}" if absent else ""))

    head = _checked_map(payload.get("params") or {}, arm=arm, name=ELO_SIDECAR,
                        field="params")
    head.pop("c2", None)                       # a derived property, not a field
    try:
        params = ordlogit.OrdLogitParams(**head)
    except TypeError as exc:
        raise BundleError(
            f"{arm}: {ELO_SIDECAR}'s head parameters are not an "
            f"OrdLogitParams ({exc})") from exc

    ratings = _float_map(payload.get("ratings") or {}, arm=arm, name=ELO_SIDECAR,
                         field="ratings")
    unrated = sorted(({f.home_key for f in fixtures}
                      | {f.away_key for f in fixtures}) - set(ratings))
    if unrated:
        raise BundleError(
            f"{arm}: {ELO_SIDECAR} has no rating for {unrated}, so the arm "
            "cannot be re-derived; a default would be a modelling choice "
            "smuggled in as a fallback")

    edge = np.array([ratings[f.home_key] - ratings[f.away_key] for f in fixtures],
                    dtype=float)
    derived = ordlogit.predict(params, edge)
    persisted = _float_grid(_field(payload, "probs", arm=arm, name=ELO_SIDECAR),
                            arm=arm, name=ELO_SIDECAR, field="probs")
    if persisted.shape != derived.shape:
        raise BundleError(
            f"{arm}: {ELO_SIDECAR}'s probabilities are {persisted.shape}, "
            f"expected {derived.shape}")
    delta = np.abs(persisted - derived)
    if delta.max(initial=0.0) > DERIVED_ATOL:
        row = int(np.argmax(delta.max(axis=1)))
        raise BundleError(
            f"{arm}: the 1X2 row re-derived from {ELO_SIDECAR}'s ratings and "
            f"head does not reproduce the persisted one — worst fixture "
            f"{expected[row]} off by {delta.max():.3g}. A rating, a head "
            "parameter or a probability was edited.")

    try:
        provider = bridge_mod.EloOutcomeProvider(
            probs=derived, fixture_ids=expected, bridge=bridge, params=params,
            cutoff=payload.get("cutoff", state.cutoff),
            n_fit_rows=_count(payload.get("n_fit_rows", 0), arm=arm,
                              name=ELO_SIDECAR, field="n_fit_rows"),
            n_particles=_count(_field(payload, "n_particles", arm=arm,
                                      name=ELO_SIDECAR)
                               if n_particles is None else n_particles,
                               arm=arm, name=ELO_SIDECAR, field="n_particles"),
            ratings=ratings)
    except (TypeError, ValueError, bridge_mod.BridgeError) as exc:
        raise BundleError(
            f"{arm}: {ELO_SIDECAR} does not describe an Elo arm ({exc})") from exc
    _same_hash(arm, provider, payload.get("content_hash"), ELO_SIDECAR)
    return provider


def rebuild_provider(arm: str, directory, *, book, state,
                     n_particles: int | None = None,
                     anchors: dict | None = None):
    """The arm's provider, rebuilt from the issuance's own bundle.

    ``anchors`` is what ``issuance.json`` recorded — :func:`recorded_anchors`
    shapes it — and every one of them that is present must agree. Without it the
    internal checks still run, and they are the ones a coherent cross-file edit
    can be made to pass, which is why ``simcli check`` always passes anchors.

    ``dc_native`` is the book itself and is returned unchanged, so the native
    path is byte-for-byte what it was before this module existed.
    """
    if arm == "dc_native":
        return book
    if arm not in ARM_SIDECARS:
        raise BundleError(f"unknown arm {arm!r}; the arms are "
                          f"{sorted(ARM_SIDECARS)}")
    anchor = _anchor_for(anchors, arm=arm)

    # The EVIDENCE first: a bundle whose counts are not the fitted ones is not
    # this arm's bundle, whatever the rest of it says about itself.
    bridge = read_bridge(directory, arm=arm,
                         expect_hash=anchor["bridge_hash"])
    manifest = read_arms(directory, arm=arm,
                         expect_hash=anchor["arms_manifest_hash"])
    arms_entry = _mapping(manifest.get("arms") or {}, arm=arm,
                          name=ARMS_SIDECAR, what="'s arms")
    cell = _mapping(arms_entry.get(arm) or {}, arm=arm, name=ARMS_SIDECAR,
                    what=f"'s arms[{arm!r}]")
    recorded = cell.get("content_hash")

    if arm == "dc_wdl_bridge":
        if manifest.get("book_hash") != book.content_hash():
            raise BundleError(
                f"{arm}: the particle book beside this issuance hashes to "
                f"{book.content_hash()}, but {ARMS_SIDECAR} records "
                f"{manifest.get('book_hash')} — this arm was priced by a "
                "different book")
        persisted = manifest.get("provisional_teams")
        if persisted is not None and persisted != sorted(book.provisional):
            raise BundleError(
                f"{arm}: the book's provisional set {sorted(book.provisional)} "
                f"is not the recorded {persisted}; the widening branch this arm "
                "applies would not be the one that was published")
        provider = bridge_mod.DCWDLProvider(book, bridge)
    else:
        provider = _read_elo(directory, state, bridge, n_particles=n_particles,
                             arm=arm)

    _same_hash(arm, provider, recorded, ARMS_SIDECAR)
    if anchor["provider_hash"] is not None:
        _same_hash(arm, provider, anchor["provider_hash"], ISSUANCE_RECORD)
    return provider


def _anchor_for(anchors: dict | None, *, arm: str) -> dict:
    """The three recorded hashes this arm is held against, or ``None``s."""
    if anchors is None:
        return {"bridge_hash": None, "arms_manifest_hash": None,
                "provider_hash": None}
    anchors = _mapping(anchors, arm=arm, name=ISSUANCE_RECORD, what="'s anchors")
    provider_hashes = _mapping(anchors.get("provider_hashes") or {}, arm=arm,
                               name=ISSUANCE_RECORD, what="'s provider_hashes")
    return {"bridge_hash": anchors.get("bridge_hash"),
            "arms_manifest_hash": anchors.get("arms_manifest_hash"),
            "provider_hash": provider_hashes.get(arm)}


def _same_hash(arm: str, provider, recorded: str | None, where: str) -> None:
    if recorded is None:
        raise BundleError(
            f"{arm}: {where} records no content hash for this arm, so the "
            "rebuilt provider cannot be shown to be the one that was published")
    got = provider.content_hash()
    if got != recorded:
        raise BundleError(
            f"{arm}: the provider rebuilt from the bundle hashes to {got}, not "
            f"to the {recorded} recorded in {where}")


# ==========================================================================
# 3. what a caller needs to know before it tries
# ==========================================================================
def refusal(arm: str, directory) -> str | None:
    """The reason ``arm`` cannot be rebuilt here, or ``None`` if it can be tried.

    Cheap and side-effect free: it looks only at which files exist. Everything
    that needs the files' CONTENTS to be judged is decided in
    :func:`rebuild_provider`, which raises.
    """
    if arm not in ARM_SIDECARS:
        return f"unknown arm {arm!r}"
    absent = missing_sidecars(arm, directory)
    if not absent:
        return None
    return (f"{arm} cannot be re-derived from this issuance: "
            f"{', '.join(absent)} " + ("is" if len(absent) == 1 else "are")
            + " missing. An issuance written before the arm sidecars existed "
              "carries no record of the fitted bridge or the Elo head, and a "
              "check that cannot rebuild the arm is not a passing check.")
