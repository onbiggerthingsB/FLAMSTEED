# Releases operator guide (Phase 1, rev 2)

## One release window, end to end

1. Author the fixtures CSV from the official schedule (`date,home,away[,neutral]`;
   qualifiers are HOME games — omit `neutral`; extra columns like venue are
   allowed and ignored).
2. Cutoff = the UTC midnight before the window's first kickoff. The builder
   REJECTS non-midnight cutoffs by design.
3. Build:
   `PYTHONPATH=src .venv/bin/python scripts/build_release.py --cutoff <ISO-midnight> \
    --fixtures <csv> --label "<window name>" --store data/stores/full_final \
    --out releases/<date>/`
4. Gates that will stop you (by design): non-midnight cutoff; fixture dated
   before cutoff (PIT); unknown team names (fix CSV spelling — the error lists
   ALL unknowns); incoherent 1X2 (suspected bug — investigate, never override).
5. Publish `release.html` + `release.csv`; `release.json` is the archival payload.
6. Rebuild + republish the archive (EXPLICIT bundle list — never glob):
   `PYTHONPATH=src .venv/bin/python scripts/build_archive.py --out archive_site/ \
    --include <production cutoffs...> --releases releases/`
   The assembler strips all betting/edge fields (test-enforced) and excludes
   track.json wholesale; the index explains the is_synthetic odds-overlay scope.
   - Historical WC-2026 bundles carry their original provenance banner
     ('DRY-RUN · SYNTHETIC ODDS · NOT REAL...') inside every JSON — that
     banner's scope is the ODDS OVERLAY of the original dashboard, not the
     forecast probabilities; it is retained for archival fidelity and the
     archive index explains the scope. Expect the question from readers;
     answer with the index sentence.

## Operator-only steps (accounts/legal — NEVER automated)

- Zenodo DOI upload of `archive_site/`; Internet Archive snapshot of the hosted URL.
- CAP Copy Advice request (UK ad classification) — spec §5.
- Brand name + domain — replaces `MODEL_NAME` in `src/wcmodel/releases/__init__.py`
  (one line + the marks test keeps you honest); `ARCHIVE_URL`/`METHODOLOGY_URL`
  move to the real archive host when it exists.
- Data-rights & freshness review before first PAID outreach (spec §4 item 5):
  martj42 commercial-use audit, fallback source decision, buyer-facing latency
  terms. The artifacts already disclose per-release freshness (latest_result).

## Red lines (spec §6 — test-enforced where possible)

- No betting framing, odds, edges, or bookmaker links in any artifact
  (BETTING_FIELD_DENYLIST + scan tests).
- No tournament names/marks in branding (test-enforced).
- Every public performance claim links the timestamped archive.
