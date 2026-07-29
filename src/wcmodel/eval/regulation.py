"""Regulation-time (90') results for knockout fixtures (OA finding 3).

1X2 odds settle at 90 minutes; ET-inclusive finals must never be scored
against them. Any KO fixture ABSENT from this table is EXCLUDED from
odds-scored evaluation — never inferred."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from wcmodel.model.calibration import outcome_1x2

# regulation.py lives at src/wcmodel/eval/ -> the repo root (which holds config/)
# is parents[3] (eval -> wcmodel -> src -> repo); the consumers are a script and
# a WSGI app, neither of which owns the cwd.
_PATH = Path(__file__).resolve().parents[3] / "config" / "regulation_time_results.yaml"

_REQUIRED = ("pool", "date", "home", "away", "score_90", "went_et", "source")


def _score_90(value) -> tuple[int, int]:
    """Exactly two non-negative integers. A third element, a missing one or a
    float are all hand-edit errors: refuse them rather than read the first two
    or truncate (``int(2.9) == 2`` would pass off a typo as a real scoreline)."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"score_90 must be [home, away]; got {value!r}")
    for goals in value:
        if isinstance(goals, bool) or not isinstance(goals, int):
            raise ValueError(f"score_90 entries must be integers; got {value!r}")
        if goals < 0:
            raise ValueError(f"negative 90' score: {value!r}")
    return int(value[0]), int(value[1])


def load_regulation_table(path: Path = _PATH) -> pd.DataFrame:
    rows = yaml.safe_load(path.read_text())
    df = pd.DataFrame(rows)
    missing = [c for c in _REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"missing column(s) {missing} in {path}")
    scores = df["score_90"].map(_score_90)
    df["h90"] = scores.map(lambda s: s[0])
    df["a90"] = scores.map(lambda s: s[1])
    # Unquoted YAML dates arrive as datetime.date, quoted ones as str: parse
    # both to one padded ISO form, the same expression the store cross-check
    # applies on its side. astype(str) alone left "2022-12-3" un-padded, and a
    # date that misses the join key is only visible to that store-gated check.
    df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
    if df["went_et"].dtype != bool:
        raise ValueError("went_et must be true/false on every row")
    dupes = df.duplicated(["pool", "date", "home", "away"])
    if dupes.any():
        raise ValueError(f"duplicate fixtures:\n{df[dupes]}")
    # Every row is a KNOCKOUT fixture, so the two invariants are exact
    # complements: ET happened IFF the 90' was level. Neither is visible to the
    # store cross-check — an ET match recorded with a 90' winner still joins.
    drew = df["h90"] == df["a90"]
    if (df["went_et"] & ~drew).any():
        raise ValueError(f"went_et but not level at 90':\n{df[df['went_et'] & ~drew]}")
    if (~df["went_et"] & drew).any():
        raise ValueError(f"level at 90' but went_et false:\n{df[~df['went_et'] & drew]}")
    return df.drop(columns=["score_90"])


def regulation_outcome(h90: int, a90: int) -> str:
    """1X2 label of a 90' score — delegates to the canonical mapper so this
    package adds no second score->outcome convention (finding 16)."""
    return outcome_1x2(h90, a90)
