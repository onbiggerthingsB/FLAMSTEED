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
"""

from __future__ import annotations

import re
import unicodedata

#: canonical display name -> (stable key, additional accepted spellings)
#: The canonical name itself is always an accepted spelling.
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


def _build_index() -> dict[str, tuple[str, str]]:
    """index-key -> (canonical name, stable key), rejecting collisions."""
    index: dict[str, tuple[str, str]] = {}
    for canonical, (key, aliases) in _REGISTRY.items():
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
