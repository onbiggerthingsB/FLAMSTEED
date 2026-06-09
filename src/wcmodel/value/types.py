from __future__ import annotations
from dataclasses import dataclass, field, asdict

@dataclass(frozen=True)
class ValueConfig:
    sports: list[str]; markets: list[str]; regions: str; sharp_book: str
    edge_min: float; too_good: float; longshot_odds: float; stale_seconds: int
    kelly_fraction: float; soft_books: frozenset[str]; max_calls_per_scan: int; ledger_path: str

    @classmethod
    def from_config(cls, cfg: dict) -> "ValueConfig":
        v = cfg["value"]
        return cls(sports=list(v["sports"]), markets=list(v["markets"]), regions=v["regions"],
                   sharp_book=v["sharp_book"], edge_min=float(v["edge_min"]),
                   too_good=float(v["too_good"]), longshot_odds=float(v["longshot_odds"]),
                   stale_seconds=int(v["stale_seconds"]), kelly_fraction=float(v["kelly_fraction"]),
                   soft_books=frozenset(v["soft_books"]), max_calls_per_scan=int(v["max_calls_per_scan"]),
                   ledger_path=v["ledger_path"])

@dataclass(frozen=True)
class ValueBet:
    event: str; commence_time: str; market: str; line: float | None; side: str
    sharp_book: str; sharp_fair_prob: float; soft_book: str; soft_odds: float
    edge: float; suggested_stake: float; book_tier: str; last_update: str | None
    flags: list[str] = field(default_factory=list); bettable: bool = False
    def to_dict(self) -> dict: return asdict(self)
