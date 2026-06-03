from __future__ import annotations
import hashlib, json, subprocess
from pathlib import Path
from typing import Callable
import pandas as pd


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "nogit"


def content_key(name: str, params: dict) -> str:
    blob = json.dumps({"name": name, "params": params}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def cached_pull(name: str, params: dict, fetch: Callable[[], pd.DataFrame], *,
                cache_dir: str | Path) -> pd.DataFrame:
    cache_dir = Path(cache_dir); cache_dir.mkdir(parents=True, exist_ok=True)
    key = content_key(name, params)
    path = cache_dir / f"{name}-{key}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    df = fetch()
    df.to_parquet(path, index=False)
    meta = {"name": name, "params": params, "key": key, "git_commit": _git_commit(), "rows": len(df)}
    (cache_dir / f"{name}-{key}.meta.json").write_text(json.dumps(meta, indent=2))
    return df
