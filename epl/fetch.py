"""Cache-first ingest of football-data.co.uk season CSVs.

Source pattern: https://www.football-data.co.uk/mmz4281/<SEASON>/<DIV>.csv where
SEASON is the two-year code, e.g. `2425` for 2024/25, and DIV is the division
code — `E0` for the Premier League, `E1` for the EFL Championship. Every entry
point below defaults to E0, so a caller that names no division gets exactly the
behaviour it got before divisions existed: the same URL, the same cache file
name, the same provenance file and the same provenance keys.

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

from epl import paths, schema

URL_TEMPLATE = "https://www.football-data.co.uk/mmz4281/{season_code}/{division}.csv"

#: The E0 pattern, spelled out. Kept as a literal rather than derived, because
#: `epl.livecycle` composes its refetch URL from this exact string and the
#: archive manifest records it verbatim as `source.url_pattern`.
BASE_URL = "https://www.football-data.co.uk/mmz4281/{season_code}/E0.csv"

#: Divisions with a registered season shape are the divisions we will fetch.
#: Deliberately the same gate: a division we cannot validate is a division we
#: should not be caching bytes for.
DIVISIONS: tuple[str, ...] = tuple(sorted(schema.DIVISIONS))

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
    """Provenance for one cached raw CSV.

    `division` is last and defaults to E0 so a record read back out of the
    sidecar that was written before divisions existed still constructs.
    """

    season_code: str
    season: str
    url: str
    path: str
    fetched_at: str
    sha256: str
    bytes: int
    http_status: int | None
    from_cache: bool
    division: str = schema.DEFAULT_DIVISION

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


def url_for(season_code: str, division: str = schema.DEFAULT_DIVISION) -> str:
    """The source URL for one season of one division.

    Refuses a division with no registered shape rather than composing a URL for
    a file this ingest could not validate if it arrived.
    """
    schema.division_shape(division)
    return URL_TEMPLATE.format(season_code=season_code, division=division)


def raw_path(season_code: str, division: str = schema.DEFAULT_DIVISION):
    """Cache path for one season's raw CSV. E0 keeps `E0_{code}.csv`."""
    return paths.RAW_DIR / f"{division}_{season_code}.csv"


def provenance_key(season_code: str, division: str = schema.DEFAULT_DIVISION) -> str:
    """Sidecar key for one season's raw CSV.

    THE COLLISION THIS CLOSES. Both divisions publish a file for every season
    code, so a sidecar keyed by the bare code holds one record where two are
    needed: the second division recorded would replace the first, and the
    manifest would then attest the wrong URL, the wrong byte count and the wrong
    digest for a file that is still on disk and still being parsed.

    E0 keeps the bare code. Its sidecar already holds twelve records keyed that
    way; re-keying them would orphan every one of them, and the next E0 run
    would re-record all twelve with new timestamps — a change to the E0 path's
    behaviour bought for no safety, since E0 records live in their own file
    anyway. Every other division carries its code in the key, so the two key
    spaces are disjoint whether or not they ever share a file.
    """
    if division == schema.DEFAULT_DIVISION:
        return season_code
    return f"{division}_{season_code}"


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _load_provenance(division: str = schema.DEFAULT_DIVISION) -> dict[str, dict]:
    target = paths.provenance_path(division)
    if not target.exists():
        return {}
    with open(target) as fh:
        return json.load(fh)


def _save_provenance(
    records: dict[str, dict], division: str = schema.DEFAULT_DIVISION
) -> None:
    paths.ensure_dirs()
    target = paths.provenance_path(division)
    tmp = target.with_suffix(".json.tmp")
    with open(tmp, "w") as fh:
        json.dump(records, fh, indent=2, sort_keys=True)
        fh.write("\n")
    tmp.replace(target)


def _download(url: str) -> tuple[bytes, int]:
    resp = requests.get(url, timeout=_TIMEOUT_S, headers={"User-Agent": _USER_AGENT})
    resp.raise_for_status()
    return resp.content, resp.status_code


def fetch_season(
    season_code: str,
    *,
    refresh: bool = False,
    division: str = schema.DEFAULT_DIVISION,
) -> FetchRecord:
    """Return provenance for one season's raw CSV, downloading only if needed.

    On a cache hit the bytes on disk are re-hashed and compared against the
    recorded SHA-256. A mismatch raises rather than proceeding: a raw file that
    changed underneath us invalidates every artifact derived from it.

    Each division has its own cache file, its own sidecar and its own key space,
    so no division's fetch can disturb another's record.
    """
    paths.ensure_dirs()
    url = url_for(season_code, division)
    target = raw_path(season_code, division)
    key = provenance_key(season_code, division)
    provenance = _load_provenance(division)
    recorded = provenance.get(key)

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
            division=division,
        )
        provenance[key] = record.to_json()
        _save_provenance(provenance, division)
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
        division=division,
    )
    provenance[key] = record.to_json()
    _save_provenance(provenance, division)
    return record


def fetch_all(
    season_codes: tuple[str, ...] = SEASON_CODES,
    *,
    refresh: bool = False,
    division: str = schema.DEFAULT_DIVISION,
) -> dict[str, FetchRecord]:
    """Fetch (or read from cache) every season. Raises on the first failure.

    Keyed by SEASON CODE, not by provenance key: the caller asked for one
    division and reads the result back by the code it asked with.
    """
    return {
        code: fetch_season(code, refresh=refresh, division=division)
        for code in season_codes
    }


def read_raw(season_code: str, division: str = schema.DEFAULT_DIVISION) -> str:
    """Decoded text of a cached season CSV.

    football-data files carry a UTF-8 BOM on recent seasons and occasional
    Windows-1252 bytes in referee/club names on older ones. `utf-8-sig` strips
    the BOM; cp1252 is the documented fallback and cannot fail on any byte
    sequence, so decoding never silently mangles a club name into a new team.
    """
    blob = raw_path(season_code, division).read_bytes()
    try:
        return blob.decode("utf-8-sig")
    except UnicodeDecodeError:
        return blob.decode("cp1252")
