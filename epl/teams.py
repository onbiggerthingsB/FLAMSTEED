"""Club name normalisation: raw source spelling -> canonical name -> stable key.

Promoted and relegated clubs recur across seasons, so the join key has to be
stable over the full 2014/15-2025/26 window. The registry below was built by
enumerating every distinct `HomeTeam`/`AwayTeam` value in the twelve cached
CSVs, not by guessing: 35 distinct spellings, whose per-season membership counts
sum to exactly 240 = 12 seasons x 20 clubs. Coventry is the one entry that is
not in that archive: it is promoted for 2026/27 and must be priceable, so it is
registered ahead of its first archived match (plan v2 D6).

The `FC`/`AFC` long forms are declared explicitly because openfootball prints
them and football-data.co.uk does not — 19 of the 20 spellings in the vendored
2026/27 fixture file failed `resolve` before they were added. They are aliases,
NOT a suffix-stripping heuristic: a rule that quietly drops a trailing "FC"
would also quietly accept "Manchester FC".

Resolution is STRICT. An unrecognised spelling is reported as an issue rather
than slugged into a new club. That is the whole point: a permissive slugger
would turn a future "Man Utd" into a second Manchester United with its own
attack and defence parameters, and the model would look fine while quietly
splitting one club's history in half.

Aliases are declared for plausible variants that football-data.co.uk uses in
other divisions or has used historically, so a future season's spelling change
resolves instead of failing. Unobserved aliases are harmless and are reported
separately from observed ones.

THE CHAMPIONSHIP (E1) ENTRIES, added 2026-08-30. The registry is the ONE source
of truth for club identity across divisions, so the second-tier archive's clubs
live here rather than in a second registry — a second registry would let the
same club carry two keys depending on which file resolved it. 22 clubs joined,
taking the registry from 36 to 58, and they were written against the enumeration
published FIRST in `reports/epl_e1_acquisition.md` §3, not against recollection.
That enumeration is DECLARED rather than measured (no E1 file has been fetched),
so the safety is carried by `_build_index`'s collision refusal below and by
`resolve`'s strictness, not by the list being right: a Championship spelling
whose fold lands on a registered club stops every import of this module, and one
that is simply absent fails to resolve. Four canonical names deliberately differ
from football-data's own spelling — Sheffield Wednesday, Peterborough, Burton
Albion, Milton Keynes Dons — and in each case the source's spelling is an alias,
so nothing in the ingest rewrites a name.
"""

from __future__ import annotations

import re
import unicodedata

#: canonical display name -> (stable key, additional accepted spellings)
#: The canonical name itself is always an accepted spelling.
#: Premier League (E0) clubs first, then the Championship (E1) additions.
_REGISTRY: dict[str, tuple[str, tuple[str, ...]]] = {
    "Arsenal":           ("arsenal", ("Arsenal FC",)),
    "Aston Villa":       ("aston_villa", ("Villa", "Aston Villa FC")),
    "Bournemouth":       ("bournemouth", ("AFC Bournemouth", "Bournemouth FC")),
    "Brentford":         ("brentford", ("Brentford FC",)),
    "Brighton":          ("brighton", ("Brighton & Hove Albion", "Brighton and Hove Albion",
                                       "Brighton & Hove Albion FC", "Brighton and Hove Albion FC")),
    "Burnley":           ("burnley", ()),
    "Cardiff":           ("cardiff", ("Cardiff City",)),
    "Chelsea":           ("chelsea", ("Chelsea FC",)),
    "Coventry":          ("coventry", ("Coventry City", "Coventry City FC")),
    "Crystal Palace":    ("crystal_palace", ("Palace", "Crystal Palace FC")),
    "Everton":           ("everton", ("Everton FC",)),
    "Fulham":            ("fulham", ("Fulham FC",)),
    "Huddersfield":      ("huddersfield", ("Huddersfield Town",)),
    "Hull":              ("hull", ("Hull City", "Hull City AFC", "Hull City FC")),
    "Ipswich":           ("ipswich", ("Ipswich Town", "Ipswich Town FC")),
    "Leeds":             ("leeds", ("Leeds United", "Leeds Utd", "Leeds United FC")),
    "Leicester":         ("leicester", ("Leicester City",)),
    "Liverpool":         ("liverpool", ("Liverpool FC",)),
    "Luton":             ("luton", ("Luton Town",)),
    "Manchester City":   ("man_city", ("Man City", "Manchester C", "Manchester City FC")),
    "Manchester United": ("man_united", ("Man United", "Man Utd", "Manchester U",
                                         "Manchester United FC")),
    "Middlesbrough":     ("middlesbrough", ("Middlesboro",)),
    "Newcastle":         ("newcastle", ("Newcastle United", "Newcastle Utd",
                                        "Newcastle United FC")),
    "Norwich":           ("norwich", ("Norwich City",)),
    "Nottingham Forest": ("nottm_forest", ("Nott'm Forest", "Notts Forest", "Nottm Forest",
                                           "Nottingham Forest FC")),
    "QPR":               ("qpr", ("Queens Park Rangers", "Q.P.R.")),
    "Sheffield United":  ("sheffield_united", ("Sheffield Utd", "Sheff United", "Sheff Utd")),
    "Southampton":       ("southampton", ()),
    "Stoke":             ("stoke", ("Stoke City",)),
    "Sunderland":        ("sunderland", ("Sunderland AFC",)),
    "Swansea":           ("swansea", ("Swansea City",)),
    "Tottenham":         ("tottenham", ("Tottenham Hotspur", "Spurs", "Tottenham Hotspur FC")),
    "Watford":           ("watford", ()),
    "West Brom":         ("west_brom", ("West Bromwich Albion", "West Bromwich")),
    "West Ham":          ("west_ham", ("West Ham United", "West Ham Utd")),
    "Wolves":            ("wolves", ("Wolverhampton", "Wolverhampton Wanderers")),

    # --- Championship (E1) additions, 2026-08-30 -------------------------
    # Written against reports/epl_e1_acquisition.md §3. Clubs that appear in
    # BOTH divisions on this window (Cardiff, Norwich, Preston's opponents and
    # so on) are already above and are not duplicated here: one club, one key,
    # whichever division's file resolved it.
    "Barnsley":          ("barnsley", ("Barnsley FC",)),
    "Birmingham":        ("birmingham", ("Birmingham City", "Birmingham City FC")),
    "Blackburn":         ("blackburn", ("Blackburn Rovers", "Blackburn Rovers FC")),
    "Blackpool":         ("blackpool", ("Blackpool FC",)),
    "Bolton":            ("bolton", ("Bolton Wanderers", "Bolton Wanderers FC")),
    "Bristol City":      ("bristol_city", ("Bristol City FC",)),
    "Burton Albion":     ("burton", ("Burton", "Burton Albion FC")),
    "Charlton":          ("charlton", ("Charlton Athletic", "Charlton Athletic FC")),
    "Derby":             ("derby", ("Derby County", "Derby County FC")),
    "Millwall":          ("millwall", ("Millwall FC",)),
    "Milton Keynes Dons": ("mk_dons", ("MK Dons", "Milton Keynes Dons FC")),
    "Oxford":            ("oxford", ("Oxford United", "Oxford Utd", "Oxford United FC")),
    "Peterborough":      ("peterborough", ("Peterboro", "Peterborough United",
                                           "Peterborough Utd", "Peterborough United FC")),
    "Plymouth":          ("plymouth", ("Plymouth Argyle", "Plymouth Argyle FC")),
    "Portsmouth":        ("portsmouth", ("Portsmouth FC",)),
    "Preston":           ("preston", ("Preston North End", "Preston NE",
                                      "Preston North End FC")),
    "Reading":           ("reading", ("Reading FC",)),
    "Rotherham":         ("rotherham", ("Rotherham United", "Rotherham Utd",
                                        "Rotherham United FC")),
    "Sheffield Wednesday": ("sheffield_wednesday", ("Sheffield Weds", "Sheff Wed",
                                                    "Sheffield Wed",
                                                    "Sheffield Wednesday FC")),
    "Wigan":             ("wigan", ("Wigan Athletic", "Wigan Athletic FC")),
    "Wrexham":           ("wrexham", ("Wrexham AFC", "Wrexham FC")),
    "Wycombe":           ("wycombe", ("Wycombe Wanderers", "Wycombe Wanderers FC")),
}

#: Apostrophe-like and dash-like codepoints the source has been known to emit.
_APOSTROPHES = "‘’ʼ´`"
_DASHES = "‐‑‒–—―"


class UnknownTeamError(KeyError):
    """A club spelling that is not in the registry."""


def normalise_spelling(raw: str) -> str:
    """Fold the cosmetic variation the source introduces, and nothing else.

    Unicode-normalises, maps curly apostrophes and long dashes to ASCII, and
    collapses whitespace. Deliberately does NOT lowercase or strip punctuation —
    that happens only inside the lookup index, so the reported raw spelling
    stays faithful to the file.
    """
    text = unicodedata.normalize("NFC", str(raw)).strip()
    for ch in _APOSTROPHES:
        text = text.replace(ch, "'")
    for ch in _DASHES:
        text = text.replace(ch, "-")
    return re.sub(r"\s+", " ", text)


def _index_key(text: str) -> str:
    """Lookup-only fold: lowercase, drop non-alphanumerics."""
    return re.sub(r"[^a-z0-9]+", "", normalise_spelling(text).lower())


def _build_index(
    registry: dict[str, tuple[str, tuple[str, ...]]] | None = None
) -> dict[str, tuple[str, str]]:
    """index-key -> (canonical name, stable key), rejecting collisions.

    Takes the registry as an argument so the collision refusal can be exercised
    by a test on a poisoned copy. That refusal is what makes adding a division's
    worth of clubs safe: two spellings that fold to the same string would be one
    club silently absorbing another, and this raises at import instead.
    """
    if registry is None:
        registry = _REGISTRY
    index: dict[str, tuple[str, str]] = {}
    for canonical, (key, aliases) in registry.items():
        for spelling in (canonical, *aliases):
            idx = _index_key(spelling)
            if idx in index and index[idx] != (canonical, key):
                raise ValueError(
                    f"registry collision: {spelling!r} maps to both "
                    f"{index[idx]} and {(canonical, key)}"
                )
            index[idx] = (canonical, key)
    return index


_INDEX = _build_index()

# Two clubs must never share a key.
if len({k for k, _ in _REGISTRY.values()}) != len(_REGISTRY):
    raise ValueError("duplicate stable key in team registry")


def resolve(raw: str) -> tuple[str, str]:
    """`"Nott'm Forest"` -> `("Nottingham Forest", "nottm_forest")`.

    Raises UnknownTeamError for an unregistered spelling. Callers that need to
    survive one bad name should catch it and record the failure — never fall
    back to slugging the raw string.
    """
    try:
        return _INDEX[_index_key(raw)]
    except KeyError as exc:
        raise UnknownTeamError(
            f"unregistered club spelling {raw!r}. Add it to _REGISTRY in "
            f"epl/teams.py as a canonical name or an alias of an existing club — "
            f"do not let it through as a new team."
        ) from exc


def canonical_name(raw: str) -> str:
    return resolve(raw)[0]


def team_key(raw: str) -> str:
    return resolve(raw)[1]


def known_spellings() -> dict[str, tuple[str, str]]:
    """Every accepted spelling -> (canonical, key). For the mapping report."""
    out: dict[str, tuple[str, str]] = {}
    for canonical, (key, aliases) in _REGISTRY.items():
        for spelling in (canonical, *aliases):
            out[spelling] = (canonical, key)
    return out


def registry_size() -> int:
    return len(_REGISTRY)
