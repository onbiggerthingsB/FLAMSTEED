"""Free citable forecast releases (product spec 2026-07-25, Phase 1, rev 2).

Provenance-stamped, CC-licensed forecast artifacts. NO betting content of any
kind — enforced by BETTING_FIELD_DENYLIST at build (releases) and projection
(archive) time, with scan tests over real output.
"""
MODEL_NAME = "Flamsteed"          # first Astronomer Royal; decided 2026-08-10
                                  # (replaces Antecast); tests ban tournament marks
LICENSE_STAMP = "CC BY 4.0 — free to republish with attribution and link"
# Points at the site because the site is the thing a reader should land on;
# it went live 2026-08-11 and is verified serving over https. The rule that
# held this back is unchanged: a released artifact must never cite a domain
# that does not resolve, so this moved only AFTER the domain answered.
METHODOLOGY_URL = "https://flamsteed.io/methodology.html"
# Deliberately NOT flamsteed.io: reports/ is not published to the site, and
# the canonical citable archive is the DOI below. Pointing this at the domain
# would be pointing it at nothing.
ARCHIVE_URL = "https://github.com/onbiggerthingsB/FLAMSTEED/tree/main/reports"
DATA_SOURCE_NAME = "martj42/international_results (community dataset)"
# Canonical citable copy of the WC-2026 forecast archive (Zenodo, CC BY 4.0,
# published 2026-07-28). Scoped by tournament on purpose: a future tournament's
# archive gets its own DOI, never a reuse of this one.
WC2026_ARCHIVE_DOI = "10.5281/zenodo.21641225"
WC2026_ARCHIVE_DOI_URL = "https://doi.org/" + WC2026_ARCHIVE_DOI

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
