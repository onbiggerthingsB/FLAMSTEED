#!/usr/bin/env bash
# The consolidated site gate. Run from repo root: tools/site_check.sh [site_dir]
set -euo pipefail
D="${1:-site}"; fail=0
say(){ printf '%s\n' "$*"; }
bad(){ say "FAIL: $*"; fail=1; }

# G1 self-contained (tag-level, as in pages.yml)
grep -nE '<(script|link|img|iframe)[^>]+(src|href)="https?://' "$D"/*.html && bad "external tag src/href" || say "G1 tag-level: ok"

# G2 placeholders
grep -nEi 'href="[^"]*(example\.(com|org|net)|localhost|TODO|FIXME|XXX|your-|changeme|placeholder)' "$D"/*.html && bad "placeholder" || say "G2 placeholders: ok"

# G3 in-repo citations resolve
while IFS= read -r p; do [ -z "$p" ] && continue
  [ -e "$p" ] || bad "cited path missing: $p"
done < <(grep -ohE 'https://github\.com/onbiggerthingsB/FLAMSTEED/(blob|tree)/main/[^"#]+' "$D"/*.html | sed -E 's#.*/(blob|tree)/main/##' | sort -u)
say "G3 citations: checked"

# G4 whole-file external refs (CSS url(), @import, svg href, protocol-relative)
# allow: data:, mailto:, #, relative, and enumerated hosts
if grep -nEio '(url\(|@import[[:space:]]+|(xlink:href|href|src|content)[[:space:]]*=[[:space:]]*["'\''(]?)[[:space:]]*["'\'']?(https?:|//)[^"'\'')> ]*' "$D"/*.html \
  | grep -vE 'https://(github\.com/onbiggerthingsB/FLAMSTEED|doi\.org|flamsteed\.io)[/"'\'' ]?' ; then
  bad "off-origin reference outside allowlist"
else say "G4 whole-file externals: ok"; fi

# do-not-ship strings
grep -nEi 'provenance hash|ZERO LEAKAGE VIOLATIONS' "$D"/*.html && bad "do-not-ship string present" || say "do-not-ship: ok"

# folio typography: never N№ / Nº
grep -n 'N№\|Nº' "$D"/*.html && bad "bad folio numero" || say "folio: ok"

# no synthetic bold on the display face
grep -nE 'font-family:[^;}]*display[^;}]*;[^}]*font-weight:\s*[5-9]00' "$D"/*.html && bad "display face given weight >400" || say "display weight: ok"

# CNAME intact
{ test -f "$D/CNAME" && grep -qx 'flamsteed.io' "$D/CNAME"; } || bad "CNAME missing/changed"

# uptime sentinels
grep -q 'Flamsteed'   "$D/index.html"        || bad "sentinel Flamsteed missing (index)"
grep -q 'bitemporal'  "$D/methodology.html"  || bad "sentinel bitemporal missing (methodology)"
grep -q 'preregist'   "$D/market-test.html"  || bad "sentinel preregist missing (market-test)"

# weight budget ≤120KB/page
for f in "$D"/index.html "$D"/methodology.html "$D"/market-test.html; do
  sz=$(wc -c < "$f")
  [ "$sz" -le 122880 ] || bad "$f is ${sz}B > 120KB"
done

# SEALED marks carry the CURRENT lock version.
# The interpreter is resolved, not assumed: a clean CI checkout has no .venv,
# and hardcoding it made this branch exit 127 — a missing interpreter must
# never be able to masquerade as a passing check. wcmodel.eval.lock is
# stdlib-only, so the system python3 reads the chain just as well.
if grep -q 'SEALED' "$D"/*.html; then
  PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"
  V=$(PYTHONPATH=src "$PY" -c "from wcmodel.eval.lock import verify_chain; print(verify_chain('reports/oa_lock')['version'])")
  grep -l 'SEALED' "$D"/*.html | while read -r f; do
    grep -q "LOCK-V${V}\b" "$f" || { say "FAIL: $f has SEALED mark without LOCK-V${V}"; exit 9; }
  done || fail=1
fi

[ "$fail" -eq 0 ] && say "SITE CHECK: ALL GREEN" || { say "SITE CHECK: FAILURES ABOVE"; exit 1; }
