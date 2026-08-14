"""Cache-first ingest of football-data.co.uk Premier League CSVs.

Source pattern: https://www.football-data.co.uk/mmz4281/<SEASON>/E0.csv where
SEASON is the two-year code, e.g. `2425` for 2024/25.

The cache is authoritative. Once a season's CSV lands under `data/epl/raw/` it is
never re-downloaded — a later run reads the bytes off disk and re-verifies them
against the recorded SHA-256. Two reasons this matters more than saving traffic:

1.  Reproducibility. football-data.co.uk rewrites the current season's file as
    results come in, and quietly backfills older ones. A run six months from now
    should parse the same bytes this run parsed, or say loudly that it cannot.
2.  Point-in-time honesty. A cached file is a fixed observation. Silent refresh
    would let tomorrow's results appear inside a file we already reasoned about.

`refresh=True` is the explicit override for pulling newer data; it writes a fresh
provenance record so the change is visible in the manifest rather than implicit.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import requests

from epl import paths

BASE_URL = "https://www.football-data.co.uk/mmz4281/{season_code}/E0.csv"

#: 2014/15 through 2025/26 inclusive.
SEASON_CODES: tuple[str, ...] = (
    "1415", "1516", "1617", "1718", "1819", "1920",
    "2021", "2122", "2223", "2324", "2425", "2526",
)

_TIMEOUT_S = 60
_USER_AGENT = "worldcup-epl-probe/0.1 (research; contact via repo)"

#: A season CSV smaller than this is almost certainly an error page, not data.
_MIN_PLAUSIBLE_BYTES = 20_000


class FetchError(RuntimeError):
    """A season CSV could not be obtained or failed its integrity check."""


@dataclass(frozen=True)
class FetchRecord:
    """Provenance for one cached raw CSV."""

    season_code: str
    season: str
    url: str
    path: str
    fetched_at: str
    sha256: str
    bytes: int
    http_status: int | None
    from_cache: bool

    def to_json(self) -> dict:
        return asdict(self)


def season_label(season_code: str) -> str:
    """`'2425'` -> `'2024/25'`. Two-digit years, 20xx throughout our range."""
    if len(season_code) != 4 or not season_code.isdigit():
        raise ValueError(f"season code must be 4 digits, got {season_code!r}")
    start, end = season_code[:2], season_code[2:]
    return f"20{start}/{end}"


def season_start_year(season_code: str) -> int:
    """`'2425'` -> `2024`."""
    return 2000 + int(season_code[:2])


def raw_path(season_code: str):
    return paths.RAW_DIR / f"E0_{season_code}.csv"


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _load_provenance() -> dict[str, dict]:
    if not paths.PROVENANCE_PATH.exists():
        return {}
    with open(paths.PROVENANCE_PATH) as fh:
        return json.load(fh)


def _save_provenance(records: dict[str, dict]) -> None:
    paths.ensure_dirs()
    tmp = paths.PROVENANCE_PATH.with_suffix(".json.tmp")
    with open(tmp, "w") as fh:
        json.dump(records, fh, indent=2, sort_keys=True)
        fh.write("\n")
    tmp.replace(paths.PROVENANCE_PATH)


def _download(url: str) -> tuple[bytes, int]:
    resp = requests.get(url, timeout=_TIMEOUT_S, headers={"User-Agent": _USER_AGENT})
    resp.raise_for_status()
    return resp.content, resp.status_code


def fetch_season(season_code: str, *, refresh: bool = False) -> FetchRecord:
    """Return provenance for one season's raw CSV, downloading only if needed.

    On a cache hit the bytes on disk are re-hashed and compared against the
    recorded SHA-256. A mismatch raises rather than proceeding: a raw file that
    changed underneath us invalidates every artifact derived from it.
    """
    paths.ensure_dirs()
    url = BASE_URL.format(season_code=season_code)
    target = raw_path(season_code)
    provenance = _load_provenance()
    recorded = provenance.get(season_code)

    if target.exists() and not refresh:
        blob = target.read_bytes()
        digest = sha256_bytes(blob)
        if recorded is not None and recorded.get("sha256") != digest:
            raise FetchError(
                f"cached {target.name} changed on disk: recorded sha256 "
                f"{recorded.get('sha256')}, actual {digest}. Refusing to use it — "
                f"delete the file and re-fetch with refresh=True if that is intended."
            )
        if recorded is not None:
            return FetchRecord(**{**recorded, "from_cache": True})
        # File present but unrecorded (e.g. hand-placed). Record it now.
        record = FetchRecord(
            season_code=season_code,
            season=season_label(season_code),
            url=url,
            path=paths.rel(target),
            fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            sha256=digest,
            bytes=len(blob),
            http_status=None,
            from_cache=True,
        )
        provenance[season_code] = record.to_json()
        _save_provenance(provenance)
        return record

    try:
        blob, status = _download(url)
    except requests.RequestException as exc:
        raise FetchError(f"could not fetch {url}: {exc}") from exc

    if len(blob) < _MIN_PLAUSIBLE_BYTES:
        raise FetchError(
            f"{url} returned only {len(blob)} bytes — too small to be a season "
            f"of results; treating as a failed fetch rather than caching it."
        )

    target.write_bytes(blob)
    record = FetchRecord(
        season_code=season_code,
        season=season_label(season_code),
        url=url,
        path=paths.rel(target),
        fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        sha256=sha256_bytes(blob),
        bytes=len(blob),
        http_status=status,
        from_cache=False,
    )
    provenance[season_code] = record.to_json()
    _save_provenance(provenance)
    return record


def fetch_all(
    season_codes: tuple[str, ...] = SEASON_CODES, *, refresh: bool = False
) -> dict[str, FetchRecord]:
    """Fetch (or read from cache) every season. Raises on the first failure."""
    return {code: fetch_season(code, refresh=refresh) for code in season_codes}


def read_raw(season_code: str) -> str:
    """Decoded text of a cached season CSV.

    football-data files carry a UTF-8 BOM on recent seasons and occasional
    Windows-1252 bytes in referee/club names on older ones. `utf-8-sig` strips
    the BOM; cp1252 is the documented fallback and cannot fail on any byte
    sequence, so decoding never silently mangles a club name into a new team.
    """
    blob = raw_path(season_code).read_bytes()
    try:
        return blob.decode("utf-8-sig")
    except UnicodeDecodeError:
        return blob.decode("cp1252")
