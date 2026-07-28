"""Regulation-time (90') results for knockout fixtures (OA finding 3).

1X2 odds settle at 90 minutes; ET-inclusive finals must never be scored
against them. Any KO fixture ABSENT from this table is EXCLUDED from
odds-scored evaluation — never inferred."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

_PATH = Path("config/regulation_time_results.yaml")


def load_regulation_table(path: Path = _PATH) -> pd.DataFrame:
    rows = yaml.safe_load(path.read_text())
    df = pd.DataFrame(rows)
    df["h90"] = df["score_90"].map(lambda s: int(s[0]))
    df["a90"] = df["score_90"].map(lambda s: int(s[1]))
    df["date"] = df["date"].astype(str)
    if (df["h90"] < 0).any() or (df["a90"] < 0).any():
        raise ValueError("negative 90' score")
    dupes = df.duplicated(["pool", "date", "home", "away"])
    if dupes.any():
        raise ValueError(f"duplicate fixtures:\n{df[dupes]}")
    return df.drop(columns=["score_90"])


def regulation_outcome(h90: int, a90: int) -> str:
    return "home" if h90 > a90 else ("away" if a90 > h90 else "draw")
