"""Free citable forecast releases (product spec 2026-07-25, Phase 1, rev 2).

Provenance-stamped, CC-licensed forecast artifacts. NO betting content of any
kind — enforced by BETTING_FIELD_DENYLIST at build (releases) and projection
(archive) time, with scan tests over real output.
"""
MODEL_NAME = "Antecast"           # decided 2026-07-28; tests ban tournament marks
LICENSE_STAMP = "CC BY 4.0 — free to republish with attribution and link"
METHODOLOGY_URL = "https://github.com/onbiggerthingsB/worldcup#how-it-works"
ARCHIVE_URL = "https://github.com/onbiggerthingsB/worldcup/tree/main/reports"
DATA_SOURCE_NAME = "martj42/international_results (community dataset)"

# Every JSON key that marks betting/edge content in dashboard bundles
# (build.py attaches `edge` nodes to schedule + fixture surfaces; track/meta
# carry CLV/ROI). ONE definition; build gate (Task 3), renderer test (Task 4)
# and archive projection (Task 6) all consume THIS.
BETTING_FIELD_DENYLIST = frozenset({
    "edge", "edges", "staked", "stake", "stake_signal", "entry_odds",
    "close_odds", "odds", "clv", "roi", "kelly", "bankroll", "value_bets",
    "ev", "vig", "book", "bookmaker", "market_1x2", "beat_close_rate",
    "avg_clv",
})

# Words that must not appear in any publisher JSON string value. This is
# deliberately narrower than arbitrary substrings: team names such as Real
# Betis and ordinary words containing "roi" remain valid.
BETTING_VOCAB = frozenset({
    "odds", "bet", "bets", "betting", "stake", "staked", "kelly", "clv",
    "roi", "bookmaker", "wager", "vig", "edge",
})
