"""EPL probe — a Premier League scoreline model, built to answer one question.

The World Cup model tied naive Elo over the full 104-match replay (RPS 0.1561 vs
0.1557) and lost to de-vigged market prices by ~0.010 mean RPS over 217 fixtures.
Those two published negatives set the terms here. On EPL the honest bar is:

    de-vigged market   ~0.196 RPS
    walk-forward Elo   ~0.203 RPS
    base rate          ~0.234 RPS

The entire Elo-to-market gap is ~0.007. So the only question worth answering
first is whether this architecture beats naive Elo on EPL data. Everything in
this package exists to make that question answerable without self-deception.

Two rules run through the whole package:

POINT-IN-TIME DISCIPLINE. A forecast for match M may use only information
knowable before M kicked off. This layer is a static historical archive, so it
cannot leak on its own — but it is built to make the downstream cutoff cheap and
correct: rows carry `kickoff` where a kickoff time exists and `date` always, and
`epl.schema` documents the exact ordering rule (see `ORDERING_RULE`). Retrofitting
point-in-time discipline is how leakage gets in; it is here from the first line.

NO BETTING. The odds columns are an internal accuracy benchmark and nothing
else. They are never displayed publicly and never turned into a betting signal.
That rule is absolute. See `epl.parse` for how they are extracted and
`epl.schema.ODDS_COLUMNS` for which columns they are.

Layout
------
`epl.paths`     filesystem locations
`epl.fetch`     cache-first download of football-data.co.uk CSVs + provenance
`epl.teams`     raw club name -> canonical name -> stable key
`epl.parse`     raw CSV -> tidy match rows (dates, goals, benchmark odds)
`epl.validate`  per-season structural checks (380/20/no-dupes/...)
`epl.build`     orchestrator: fetch -> parse -> validate -> parquet + manifest
`epl.schema`    column contract and the point-in-time ordering rule
"""

__all__ = ["build", "fetch", "parse", "paths", "schema", "teams", "validate"]
