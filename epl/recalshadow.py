"""A8 (c) and (d) — `dc_1x2_recal`'s shadow ledger: rows, scores, verification.

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_recal.py -q
    PYTHONPATH=src:. .venv/bin/python -m epl.recal verify

WHAT THIS LAYER IS, AND WHAT IT DELIBERATELY IS NOT
---------------------------------------------------
A8 authorises a **shadow layer beside the record**: a second set of per-fixture
numbers, scored against the same results, that **no published arm reads and no
gate consults**. `dc_native`'s published numbers never change, the issuance
schema stays `epl-issuance-5`, `check` gains no criterion, and nothing is
written into any bundle. The layer anchors itself instead — every row carries
the source run's digest and clocks, which is why the ruling calls the file
*self-contained*.

**No pass rule. None.** This ledger reports; it decides nothing, triggers
nothing, gates nothing. **No render is authorised** by A8 either: this is a
data surface, and a reader-facing page for a challenger that carries no
accuracy claim is a later amendment.

THE THINGS THIS MODULE REFUSES TO RE-IMPLEMENT
----------------------------------------------
Three of them, and each has one home in this codebase:

* **What was played** — :func:`epl.season.resolve_ledger`, reached through
  :func:`epl.matchboard.score`. A results file is a REQUEST to score rows the
  ledger already carries and never a second door a result can come through.
  The bitemporal conflict rules (a score withdrawn by a later ``abandoned``; a
  postponement corrected by the replayed match) live there.
* **A goal count** — :func:`epl.season.goal_count`, likewise reached through
  the matchboard.
* **The score** — :func:`epl.matchboard.rps`, this project's own literal, which
  A8 (b) pins by file and line.

So :func:`score` delegates the whole result half to :func:`epl.matchboard.score`
and copies its answers. That is what makes A8 item 6 an IDENTITY rather than an
approximation: ``rps_raw`` and the A7 scorecard's ``rps`` score the same
probabilities against the same outcome through the same function, so they are
the same double. A shadow layer that re-simulated, re-aggregated or merely
re-rounded the marginals would produce a number that is *nearly* the published
one, and "nearly" is not what the entry pre-states.

WHAT IT DOES OWN
----------------
The admissibility refusal, because A8 (c) requires it **typed and by name**:
:class:`RowInadmissible` fires before the delegation, naming the fixture and
the offending stamp. The matchboard's own A7 (e) check is the same rule and
would fire second; this one fires first so the operator gets the pre-stated
type rather than a differently-named refusal of the same fact.

NO CLOCK
--------
A row is a function of the bundle, the season ledger and the frozen rule.
Nothing here reads a wall clock — not for a `derived_at`, not for anything —
so the same bundle and the same ledger produce the same bytes tomorrow. A test
moves the clock and requires the bytes to be identical.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from epl import leaguesim, matchboard, paths, recalfit
from epl.recalfit import (ARM, RULE_VERSION, CorpusDigestMismatch,
                          CorpusMissing, ObjectiveInferior, RecalError,
                          RecalMismatch, RefitOutOfBounds, RowConflict,
                          RowInadmissible, SchemaMismatch)

#: A8 (c) — the shadow ledger's schema. It is carried ON EVERY ROW and not only
#: in this file's prose: a JSONL ledger has no header to put a version in, and
#: the same ruling requires every row to be checkable without opening anything
#: else. A row that cannot name its own schema is a row a later reader has to
#: guess about.
SCHEMA_VERSION = "epl-recal-shadow-1"

#: A8 (c) — in `reports/`, append-only, one JSON object per line, written per
#: matchweek AFTER the results have entered the season ledger and never before.
SHADOW_FILENAME = "epl_recal_shadow.jsonl"
SHADOW_PATH = paths.REPO_ROOT / "reports" / SHADOW_FILENAME

#: A8 (c)'s table, in order. `tuple(row) == ROW_FIELDS` is asserted by a test:
#: a field this ledger was not authorised to carry is as much a schema change
#: as a missing one, and A7 (f)'s narrowing is what makes that worth checking.
ROW_FIELDS = (
    "schema_version", "arm", "fixture_id", "date", "home", "away",
    "season", "cutoff", "observed_by", "run_digest", "source_bundle",
    "probs_raw", "probs_recal", "a", "rule_version", "corpus_sha256",
    "outcome", "rps_raw", "rps_recal", "rps_uniform", "matchweek", "ingest",
)

#: The half of a row that exists BEFORE a result does — what `--derive` can
#: honestly produce from a bundle alone. The rest is the season ledger's.
FORECAST_FIELDS = ROW_FIELDS[:ROW_FIELDS.index("outcome")]

#: A8 item 5 / (d) step 5 — the two tolerances, from :mod:`epl.recalfit` so
#: there is one definition of each.
RECAL_TOLERANCE = recalfit.RECAL_TOLERANCE
SUM_TOLERANCE = recalfit.SUM_TOLERANCE


# ==========================================================================
# 1. the source — the published matchboard, and nothing else
# ==========================================================================

def board_from(source, *, season_root=None) -> dict:
    """The matchboard document this layer copies ``probs_raw`` out of.

    A directory is an issuance bundle and is derived through
    :func:`epl.matchboard.derive` — which is where "this issuance carries no
    ``dc_native`` arm" is refused, so **a source with no matchboard is refused
    rather than priced here**. A file is a matchboard document already written
    (the derived artifact A7 (c) files outside the bundle), and it must say so
    by its own schema version.

    The bundle's repo-relative path is stamped on as ``source_bundle`` so every
    row can name where it came from without this module's prose.
    """
    path = Path(source)
    if path.is_dir():
        record = json.loads((path / "issuance.json").read_text())
        board = matchboard.derive(path, record=record, season_root=season_root)
        return {**board, "source_bundle": paths.rel(path)}
    document = json.loads(path.read_text())
    version = document.get("schema_version")
    if version != matchboard.SCHEMA_VERSION:
        raise RecalError(
            f"{path} declares schema {version!r} and this layer copies "
            f"`probs_raw` from a {matchboard.SCHEMA_VERSION!r} matchboard. A "
            "document of another shape may carry a `probs` object that means "
            "something else")
    if not document.get("rows"):
        raise RecalError(f"{path} carries no rows: there is nothing to copy")
    return document


# ==========================================================================
# 2. the rows
# ==========================================================================

def _required(board: Mapping[str, Any], field: str) -> Any:
    value = board.get(field)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise RecalError(
            f"the source matchboard records no {field!r}, and A8 (c) makes "
            "every shadow row self-contained — a row that cannot name the run "
            "it came from is a row nobody can check without this file's prose")
    return value


def _refuse_inadmissible(board: Mapping[str, Any],
                         results: Sequence[Mapping[str, Any]]) -> None:
    """A7 (e), restated by A8 (c) because this is a second surface reading it.

    A row is admissible only if the source issuance's ``cutoff`` AND
    ``observed_by`` are both at or before the fixture's kickoff **as the season
    knew it**. REFUSED, naming the fixture and the offending stamp — never
    dropped: in an append-only file a silent omission is invisible, and a
    ledger that quietly leaves out the row it cannot justify is a ledger nobody
    can audit.

    This runs BEFORE the delegation to :func:`epl.matchboard.score`, whose own
    A7 (e) check is the same rule under a different exception name. Same fact,
    the type A8 pre-stated.
    """
    by_id = {row["fixture_id"]: row for row in (board.get("rows") or [])}
    stamps = (("cutoff", pd.Timestamp(board["cutoff"])),
              ("observed_by", pd.Timestamp(board["observed_by"])))
    for result in results:
        row = by_id.get(result.get("fixture_id"))
        if row is None:
            continue            # matchboard.score refuses this, and says why
        _refuse_a_late_stamp(result.get("fixture_id"), row["date"], stamps)


def _refuse_a_late_stamp(fixture_id, kickoff, stamps) -> None:
    kick = pd.Timestamp(kickoff)
    for name, stamp in stamps:
        if pd.Timestamp(stamp) > kick:
            raise RowInadmissible(
                f"{fixture_id}: the issuance's {name} ({stamp}) is after the "
                f"kickoff the season knew ({kickoff}); the forecast did not "
                "precede the match, so the row is REFUSED rather than dropped "
                "— an append-only ledger cannot show what it silently omitted")


def forecast_rows(board: Mapping[str, Any], *, a: float = recalfit.A,
                  corpus_sha256: str = recalfit.CORPUS_SHA256) -> list[dict]:
    """The half of every A8 row that exists before a result does.

    ``probs_raw`` is the matchboard's own ``probs`` object, **copied and never
    re-priced**; ``probs_recal`` is that object through the frozen transform.
    """
    season = _required(board, "season")
    cutoff, observed_by = str(board["cutoff"]), str(board["observed_by"])
    run_digest = _required(board, "run_digest")
    source_bundle = _required(board, "source_bundle")
    out: list[dict] = []
    for row in (board.get("rows") or []):
        probs_raw = dict(row["probs"])
        out.append({
            "schema_version": SCHEMA_VERSION,
            "arm": ARM,
            "fixture_id": row["fixture_id"],
            "date": row["date"],
            "home": row["home"],
            "away": row["away"],
            "season": season,
            "cutoff": cutoff,
            "observed_by": observed_by,
            "run_digest": run_digest,
            "source_bundle": source_bundle,
            "probs_raw": probs_raw,
            "probs_recal": recalfit.transform(probs_raw, a),
            "a": float(a),
            "rule_version": RULE_VERSION,
            "corpus_sha256": corpus_sha256,
        })
    return out


def score(board: Mapping[str, Any], results: Iterable[Mapping[str, Any]], *,
          ledger=None, season_root=None, a: float = recalfit.A,
          corpus_sha256: str = recalfit.CORPUS_SHA256) -> list[dict]:
    """Complete A8 rows for results that have entered the SEASON LEDGER.

    The result half — which fixtures were played, with what scoreline, and
    therefore which outcome — is :func:`epl.matchboard.score`'s answer,
    unmodified. The forecast half is this layer's. Nothing about "what was
    played" is decided here.

    ``rps_raw`` is recomputed from the row's own ``probs_raw`` **and then held
    to the matchboard's own ``rps`` for the same fixture, exactly**. A8 item 6
    pre-states that the two are equal for the ten MW1 fixtures; making it an
    assertion in the code means a future edit that breaks the identity is
    refused rather than published as a second number under one name.
    """
    results = list(results)
    _refuse_inadmissible(board, results)
    scored = matchboard.score(board, results, ledger=ledger,
                              season_root=season_root)
    forecasts = {row["fixture_id"]: row for row in
                 forecast_rows(board, a=a, corpus_sha256=corpus_sha256)}

    out: list[dict] = []
    for row in scored:
        head = forecasts[row["fixture_id"]]
        outcome = row["outcome"]
        rps_raw = recalfit.rps(head["probs_raw"], outcome)
        if rps_raw != row["rps"]:
            raise RecalMismatch(
                f"{row['fixture_id']}: this layer scores the published "
                f"marginals at {rps_raw!r} and the matchboard scores the same "
                f"marginals against the same outcome at {row['rps']!r}. A8 "
                "item 6 pre-states that these are the SAME double because "
                "`probs_raw` is copied and not re-priced; a difference is a "
                "defect in the copy or in the score")
        out.append({**head,
                    "outcome": outcome,
                    "rps_raw": rps_raw,
                    "rps_recal": recalfit.rps(head["probs_recal"], outcome),
                    "rps_uniform": matchboard.uniform_rps(outcome),
                    "matchweek": row["matchweek"],
                    "ingest": row["ingest"]})
    return out


# ==========================================================================
# 3. the append-only file
# ==========================================================================

def shadow_key(row: Mapping[str, Any]) -> tuple[str, str]:
    """A8 (c): one row per ``(fixture_id, run_digest)``.

    ``run_digest`` is the source record's own ``digests["dc_native"]`` — WHICH
    RUN priced the forecast. Two issuances may legitimately both score one
    fixture (a re-issue at a later cutoff prices it again) and those are two
    rows; the same issuance scoring one fixture twice is one row filed twice.
    """
    return (str(row.get("fixture_id")), str(row.get("run_digest")))


def read_shadow(path=None) -> list[dict]:
    """Every row on file, in the order they were appended. Missing is empty."""
    target = Path(SHADOW_PATH if path is None else path)
    if not target.exists():
        return []
    return [json.loads(line) for line in
            target.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_shadow(path, rows: Sequence[Mapping[str, Any]]) -> dict:
    """Append ONCE per key. Idempotent; a disagreeing re-file REFUSES.

    The operator runs this weekly, by hand, so re-running the same command must
    not double every row. And an append-only ledger holding two DIFFERENT rows
    for one key is worse than one that refused the second: nothing downstream
    can say which of them the record means.

    **Nothing is written unless every row passes** — the file is opened once,
    after the whole batch has been checked, so a batch with one bad row appends
    none of them and the re-run after the fix is a clean run rather than a
    partial repair.
    """
    target = Path(SHADOW_PATH if path is None else path)
    existing: dict[tuple[str, str], str] = {}
    for row in read_shadow(target):
        existing[shadow_key(row)] = leaguesim.canonical_json(row)

    fresh: list[str] = []
    repeated = 0
    for row in rows:
        key = shadow_key(row)
        text = leaguesim.canonical_json(row)
        already = existing.get(key)
        if already is not None:
            if already == text:
                repeated += 1
                continue
            raise RowConflict(
                f"{key[0]}: this shadow ledger already carries a row for this "
                f"fixture under run digest {key[1]}, and the new row disagrees "
                "with it. The ledger is append-only and a fixture gets one row "
                "per issuance, so the conflicting row is refused rather than "
                f"filed beside the first one.\n  on file: {already}\n  "
                f"offered: {text}")
        existing[key] = text
        fresh.append(text)

    if fresh:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            for text in fresh:
                handle.write(text + "\n")
    return {"appended": len(fresh), "repeated": repeated}


# ==========================================================================
# 4. verification — A8 (d) steps 3, 4 and 5
# ==========================================================================

def check_sums(probs: Mapping[str, float], *, fixture_id: str) -> None:
    """A8 item 5: ``q_home + q_draw + q_away = 1`` within 1e-9.

    A BELT TO STEP 3'S BRACE, and this docstring says so rather than letting a
    later reader think it is independently load-bearing: step 3 holds each cell
    to 1e-12 against a transform that renormalises exactly, so three cells can
    be off by at most 3e-12 and still pass — never the 1e-9 this would need. It
    is implemented because A8 pre-states it on every row, and it is exercised
    directly by a test rather than through a vector that fails step 3 first.
    """
    total = sum(float(probs[k]) for k in matchboard.OUTCOMES)
    if abs(total - 1.0) > SUM_TOLERANCE:
        raise RecalMismatch(
            f"{fixture_id}: the recalibrated cells sum to {total!r}, which is "
            f"further than {SUM_TOLERANCE} from one. A8 item 5 makes this an "
            "invariant of every row in every matchweek")


def check_row(row: Mapping[str, Any], *, a_ledger: float,
              corpus_sha256: str) -> None:
    """A8 (d) steps 3, 4 and 5 on ONE row, in the order the ruling gives them.

    Step 3 uses the row's OWN ``a`` deliberately, before step 4 has established
    that it is the frozen rule's: a row that is internally consistent under
    some other constant passes step 3 and fails step 4, which is the
    discrimination the ruling is after. Reversing them would collapse two
    different defects into one message.
    """
    fixture_id = row.get("fixture_id")

    # --- step 3: the EXACT leg. Arithmetic on the row's own inputs, which is
    # why it is held twelve orders below the parameter's window.
    a_row = row.get("a")
    if not isinstance(a_row, (int, float)):
        raise SchemaMismatch(f"{fixture_id}: this row records no numeric 'a', "
                             "so its `probs_recal` cannot be re-derived at all")
    expected = recalfit.transform(row["probs_raw"], float(a_row))
    for key in matchboard.OUTCOMES:
        recorded = float(row["probs_recal"][key])
        if abs(recorded - expected[key]) > RECAL_TOLERANCE:
            raise RecalMismatch(
                f"{fixture_id}: probs_recal[{key!r}] is {recorded!r} and this "
                f"row's own probs_raw at a = {a_row!r} gives {expected[key]!r}, "
                f"a difference of {abs(recorded - expected[key]):.3e} against "
                f"{RECAL_TOLERANCE}. This comparison needs no optimiser and no "
                "corpus — it is arithmetic — so there is nothing here for two "
                "faithful implementations to disagree about")

    # --- step 4: the frozen-rule fields. A row fitted under one rule and filed
    # under another's name is exactly what this catches.
    for field, frozen in (("schema_version", SCHEMA_VERSION), ("arm", ARM),
                          ("rule_version", RULE_VERSION),
                          ("corpus_sha256", corpus_sha256)):
        if row.get(field) != frozen:
            raise SchemaMismatch(
                f"{fixture_id}: this row records {field} = "
                f"{row.get(field)!r} and the frozen rule's is {frozen!r}. A "
                "row filed under a name it was not fitted under cannot be read "
                "beside the rows that were")
    if float(a_row) != float(a_ledger):
        raise SchemaMismatch(
            f"{fixture_id}: this row records a = {a_row!r} and the frozen "
            f"rule's constant is {a_ledger!r}. The re-fit above verified THAT "
            "constant; a row carrying another one was not verified by it")

    # --- step 5: admissibility, the three scores, and the sum.
    _refuse_a_late_stamp(fixture_id, row["date"],
                         (("cutoff", row["cutoff"]),
                          ("observed_by", row["observed_by"])))
    outcome = row.get("outcome")
    for field, probs in (("rps_raw", row["probs_raw"]),
                         ("rps_recal", row["probs_recal"])):
        recomputed = recalfit.rps(probs, outcome)
        if float(row[field]) != recomputed:
            raise RecalMismatch(
                f"{fixture_id}: {field} is {row[field]!r} and scoring this "
                f"row's own probabilities against {outcome!r} by the project's "
                f"literal gives {recomputed!r}")
    uniform = matchboard.uniform_rps(outcome)
    if float(row["rps_uniform"]) != uniform:
        raise RecalMismatch(
            f"{fixture_id}: rps_uniform is {row['rps_uniform']!r} and a "
            f"{outcome!r} result scores {uniform!r} against (1/3, 1/3, 1/3) — "
            "exactly 5/18 for a home or away result and 1/9 for a draw")
    check_sums(row["probs_recal"], fixture_id=fixture_id)


def verify(path=None, *, corpus=None, a_ledger: float = recalfit.A,
           expect_sha256: str = recalfit.CORPUS_SHA256) -> dict:
    """A8 (d), in order, stopping at the first refusal.

    1. **The corpus, before any fit** — :func:`epl.recalfit.load_corpus` checks
       the digest before anything reads the file. Missing is
       :class:`CorpusMissing`, differing is :class:`CorpusDigestMismatch`.
       **A typed refusal, not a skip:** CI has no ``data/`` and this command
       refuses there, correctly and loudly. That is its job. A verification
       that quietly declines to verify is worse than one that was never run,
       because it prints something.
    2. **The re-fit, two legs** — :func:`epl.recalfit.verify_fit`.
    3-5. **Every row** — :func:`check_row`.

    Plus the file-level invariant :func:`append_shadow` enforces on the way in:
    one row per ``(fixture_id, run_digest)``. A ledger that already holds two
    is refused by the reader as well as by the writer, because the writer is
    not the only thing that can have written it.
    """
    fit = recalfit.verify_fit(corpus, a_ledger=a_ledger,
                              expect_sha256=expect_sha256)
    target = Path(SHADOW_PATH if path is None else path)
    rows = read_shadow(target)

    seen: dict[tuple[str, str], int] = {}
    for index, row in enumerate(rows):
        key = shadow_key(row)
        if key in seen:
            raise RowConflict(
                f"{key[0]}: this shadow ledger carries two rows for this "
                f"fixture under run digest {key[1]} (lines {seen[key] + 1} and "
                f"{index + 1}). A8 (c) gives a fixture one row per issuance, "
                "and a file holding two says nothing a reader can use")
        seen[key] = index
        check_row(row, a_ledger=a_ledger,
                  corpus_sha256=fit["sha256"] if expect_sha256 is None
                  else expect_sha256)

    return {"ledger": str(target), "exists": target.exists(),
            "n_rows": len(rows), "arm": ARM, "rule_version": RULE_VERSION,
            "schema_version": SCHEMA_VERSION, "fit": fit,
            "matchweeks": sorted({row.get("matchweek") for row in rows},
                                 key=lambda v: (v is None, v)),
            "fixtures": [row.get("fixture_id") for row in rows]}


# ==========================================================================
# 5. what a command needs: a document to write, and a whole scoring run
# ==========================================================================

def forecast_document(board: Mapping[str, Any], *, a: float = recalfit.A,
                      corpus_sha256: str = recalfit.CORPUS_SHA256) -> dict:
    """The `--derive` artifact: every priced fixture through the frozen rule.

    A PURE FUNCTION of the board and the rule — **no clock**, not even a
    `derived_at`. The matchboard's own derived artifact takes its stamp as an
    INPUT for exactly this reason (the boundary may read a clock, the library
    may not), and this document has no equivalent claim to make: it is
    reproducible from the bundle and the constant, and a timestamp inside it
    would be the one field that stopped it being so.

    It is a FORECAST document and carries no result and no score. Rows become
    ledger rows only when the season ledger has resolved the fixtures.
    """
    rows = forecast_rows(board, a=a, corpus_sha256=corpus_sha256)
    return {
        "schema_version": SCHEMA_VERSION,
        "arm": ARM,
        "derived": True,
        "season": _required(board, "season"),
        "cutoff": str(board["cutoff"]),
        "observed_by": str(board["observed_by"]),
        "run_digest": _required(board, "run_digest"),
        "source_bundle": _required(board, "source_bundle"),
        "source_schema_version": board.get("schema_version"),
        "a": float(a),
        "rule_version": RULE_VERSION,
        "corpus_sha256": corpus_sha256,
        "n_fixtures": len(rows),
        "rows": rows,
    }


def read_results(path) -> list[dict]:
    """A results file — a REQUEST to score rows the season ledger carries."""
    return [json.loads(line) for line in
            Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def score_bundle(source, results_file, *, ledger_path=None, season_root=None,
                 a: float = recalfit.A,
                 corpus_sha256: str = recalfit.CORPUS_SHA256) -> dict:
    """Derive, score and append in one pass, refusing before anything is written.

    The whole batch is scored first (which is where the season ledger, the
    admissibility ordering and the raw-score identity all refuse), and only
    then is the file opened. A request with one bad row appends none of them.
    """
    board = board_from(source, season_root=season_root)
    rows = score(board, read_results(results_file), season_root=season_root,
                 a=a, corpus_sha256=corpus_sha256)
    target = Path(SHADOW_PATH if ledger_path is None else ledger_path)
    tally = append_shadow(target, rows)
    return {"board": board, "rows": rows, "ledger": str(target), **tally}


__all__ = [
    "SCHEMA_VERSION", "SHADOW_FILENAME", "SHADOW_PATH", "ROW_FIELDS",
    "FORECAST_FIELDS", "RECAL_TOLERANCE", "SUM_TOLERANCE",
    "RecalError", "CorpusMissing", "CorpusDigestMismatch", "RefitOutOfBounds",
    "ObjectiveInferior", "RecalMismatch", "SchemaMismatch", "RowInadmissible",
    "RowConflict", "ARM", "RULE_VERSION",
    "board_from", "forecast_rows", "score", "shadow_key", "read_shadow",
    "append_shadow", "check_sums", "check_row", "verify",
    "forecast_document", "read_results", "score_bundle",
]
