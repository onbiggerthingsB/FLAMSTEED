"""The common T_issue forecast ledger every OA arm writes to (OA F2/F9).

One row per (arm, fixture): the 1X2 forecast an arm issued at the
pre-registered issuance timestamp, plus the provenance needed to reproduce
it. The contrast in Plan 2 is a join over this table, so the invariants that
make two arms comparable are enforced HERE, at write time, not discovered
later in the analysis:

* ``t_issue`` is exactly 09:00 UTC on the fixture's matchday — the prereg
  default IS the estimand (F2/F9). A drifted config must fail loudly rather
  than quietly re-define what is being measured.
* ``training_cutoff <= t_issue`` — the information-set rule (F2). A fit may
  not have seen the future the forecast is scored against.
* probabilities are a distribution, and one (arm, fixture) appears once.

:func:`load_ledger` re-runs every one of those checks: the parquet is a
shared artifact that other sessions and (in Plan 2) other arms append to, so
parsing cleanly is not evidence that it is admissible.
"""
from __future__ import annotations

from datetime import date as _date, datetime, timezone
from pathlib import Path

import pandas as pd

# Column ORDER is part of the contract (load_ledger pins it) as much as the
# dtypes are: the ledger is read by eye at the prereg gate.
LEDGER_DTYPES: dict[str, str] = {
    "fixture_id": "str",
    "pool": "str",
    "date": "str",
    "home": "str",
    "away": "str",
    "t_issue": "datetime64[us, UTC]",
    "training_cutoff": "datetime64[us, UTC]",
    "arm": "str",
    "p_home": "float64",
    "p_draw": "float64",
    "p_away": "float64",
    "issued_git": "str",
    "odds_snapshot_hash": "str",
}

# Every column except the nullable odds hash must carry a real value.
_NON_NULL = tuple(c for c in LEDGER_DTYPES if c != "odds_snapshot_hash")

_PROBS = ("p_home", "p_draw", "p_away")

#: Prereg default (F2): 09:00 UTC on the matchday, matching the daily
#: production cadence.
T_ISSUE_UTC_TIME = (9, 0, 0, 0)

_SUM_TOL = 1e-9


def _norm_date(value) -> str:
    """Padded ISO ``YYYY-MM-DD`` — the same normalization the regulation
    table applies, so the two join on identical keys."""
    if isinstance(value, str):
        parsed = pd.to_datetime(value, format="%Y-%m-%d", errors="coerce")
        if pd.isna(parsed):
            raise ValueError(f"date must be ISO YYYY-MM-DD; got {value!r}")
        return parsed.date().isoformat()
    if isinstance(value, datetime):
        raise ValueError(
            f"date must be a calendar date, not a datetime; got {value!r}")
    if isinstance(value, _date):
        return value.isoformat()
    raise ValueError(f"date must be a date or ISO string; got {value!r}")


def _norm_ts(value, field: str) -> datetime:
    """Reject naive stamps and normalize to UTC.

    A naive stamp is the failure mode this contract exists to prevent: it
    compares fine against another naive stamp, drifts by the writer's local
    offset, and only surfaces as a silently different information set. The
    UTC normalization keeps an equivalent-offset stamp (same INSTANT, other
    wall clock) admissible while storing one canonical form.
    """
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if not isinstance(value, datetime):
        raise ValueError(f"{field} must be a datetime; got {value!r}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be tz-aware; got naive {value!r}")
    return value.astimezone(timezone.utc)


def _check_t_issue(t_issue: datetime, day: str) -> None:
    hms = (t_issue.hour, t_issue.minute, t_issue.second, t_issue.microsecond)
    if hms != T_ISSUE_UTC_TIME or t_issue.date().isoformat() != day:
        raise ValueError(
            f"t_issue must be exactly 09:00:00 UTC on the fixture date "
            f"{day}; got {t_issue.isoformat()} (OA F2 — the pre-registered "
            "issuance time is the estimand, not a tunable)")


def _check_probs(row: dict) -> None:
    values = []
    for field in _PROBS:
        p = row[field]
        try:
            p = float(p)
        except (TypeError, ValueError):
            raise ValueError(f"{field} must be a float; got {row[field]!r}") from None
        # NaN fails every comparison below, so test it explicitly.
        if p != p or not (0.0 <= p <= 1.0):
            raise ValueError(f"{field} must be a probability in [0, 1]; got {p!r}")
        values.append(p)
    total = sum(values)
    if abs(total - 1.0) > _SUM_TOL:
        raise ValueError(
            f"p_home/p_draw/p_away must sum to 1 +/- {_SUM_TOL:g}; "
            f"got {total!r} for {row['arm']!r} on {row['fixture_id']!r}")


def _validate(row: dict, seen: set[tuple[str, str]]) -> dict:
    """Return the normalized row, or raise. Never mutates ``row`` or ``seen``."""
    keys = set(row)
    missing = [c for c in LEDGER_DTYPES if c not in keys]
    if missing:
        raise ValueError(f"missing ledger field(s): {missing}")
    unknown = sorted(keys - set(LEDGER_DTYPES))
    if unknown:
        raise ValueError(f"unknown ledger field(s): {unknown}")

    out = dict(row)
    for field in _NON_NULL:
        value = out[field]
        if value is None or (not isinstance(value, (datetime, _date))
                             and pd.isna(value)):
            raise ValueError(f"{field} must not be null")
        if isinstance(value, str) and not value.strip():
            raise ValueError(f"{field} must not be blank")

    out["date"] = _norm_date(out["date"])
    out["t_issue"] = _norm_ts(out["t_issue"], "t_issue")
    out["training_cutoff"] = _norm_ts(out["training_cutoff"], "training_cutoff")
    _check_t_issue(out["t_issue"], out["date"])
    if out["training_cutoff"] > out["t_issue"]:
        raise ValueError(
            f"training_cutoff {out['training_cutoff'].isoformat()} is after "
            f"t_issue {out['t_issue'].isoformat()} — the fit saw the future "
            "(OA F2)")
    _check_probs(out)
    for field in _PROBS:
        out[field] = float(out[field])

    key = (str(out["arm"]), str(out["fixture_id"]))
    if key in seen:
        raise ValueError(f"duplicate (arm, fixture_id) {key} in ledger")
    hash_ = out["odds_snapshot_hash"]
    out["odds_snapshot_hash"] = (
        None if hash_ is None or pd.isna(hash_) else str(hash_))
    return out


def _frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=list(LEDGER_DTYPES))
    return df.astype(LEDGER_DTYPES)


class LedgerWriter:
    """Append forecasts to one parquet ledger, validating each row.

    An existing file at ``path`` is loaded (and re-validated) on construction:
    arms issue over many sessions, so duplicate detection that only saw the
    current process would let a re-run double-weight a fixture in the
    contrast. ``flush`` rewrites the whole table.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._rows: list[dict] = []
        self._seen: set[tuple[str, str]] = set()
        if self.path.exists():
            for row in load_ledger(self.path).to_dict("records"):
                self._rows.append(row)
                self._seen.add((str(row["arm"]), str(row["fixture_id"])))

    def append(self, row: dict) -> None:
        validated = _validate(row, self._seen)
        self._rows.append(validated)
        self._seen.add((str(validated["arm"]), str(validated["fixture_id"])))

    def flush(self) -> Path:
        _frame(self._rows).to_parquet(self.path, engine="pyarrow", index=False)
        return self.path

    def __enter__(self) -> "LedgerWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # Only on the success path: a raising body means the caller's row set
        # is unknown, and half a ledger is worse than none.
        if exc_type is None:
            self.flush()


def load_ledger(path: Path | str) -> pd.DataFrame:
    df = pd.read_parquet(path, engine="pyarrow")
    missing = [c for c in LEDGER_DTYPES if c not in df.columns]
    if missing:
        raise ValueError(f"missing ledger column(s) {missing} in {path}")
    extra = [c for c in df.columns if c not in LEDGER_DTYPES]
    if extra:
        raise ValueError(f"unknown ledger column(s) {extra} in {path}")
    df = df[list(LEDGER_DTYPES)].astype(LEDGER_DTYPES)
    seen: set[tuple[str, str]] = set()
    rows = []
    for record in df.to_dict("records"):
        validated = _validate(record, seen)
        seen.add((str(validated["arm"]), str(validated["fixture_id"])))
        rows.append(validated)
    return _frame(rows)
