#!/usr/bin/env bash
# Reproducible display-font embed. Output: /tmp/fonts/bm.css
set -euo pipefail
# fontTools stamps head.created/modified with "now" unless SOURCE_DATE_EPOCH is
# set; without this pin the woff2 (and therefore the ~26KB base64 inlined into
# all three pages) changes bytes on every run. Pinned to 2026-08-12T00:00:00Z.
export SOURCE_DATE_EPOCH=1786492800
W=/tmp/fonts; mkdir -p "$W"; cd "$W"
BASE=https://raw.githubusercontent.com/google/fonts/main/ofl/bodonimoda
curl -fsSLo bm.ttf     "$BASE/BodoniModa%5Bopsz%2Cwght%5D.ttf"
curl -fsSLo bm-it.ttf  "$BASE/BodoniModa-Italic%5Bopsz%2Cwght%5D.ttf"
curl -fsSLo OFL.txt    "$BASE/OFL.txt"
UNI="U+0020-007E,U+00A0,U+00B7,U+200A,U+2013,U+2014,U+2018-201D,U+2026,U+2116,U+2212"
VENV=/Users/likerun/Desktop/worldcup/.venv/bin
"$VENV/fonttools" varLib.instancer -q -o bm400.ttf    bm.ttf    "opsz=96" "wght=400"
"$VENV/fonttools" varLib.instancer -q -o bm400it.ttf  bm-it.ttf "opsz=96" "wght=400"
"$VENV/pyftsubset" bm400.ttf   --unicodes="$UNI" --layout-features="kern,liga,onum,tnum" --flavor=woff2 --output-file=bm.woff2
"$VENV/pyftsubset" bm400it.ttf --unicodes="$UNI" --layout-features="kern,liga"           --flavor=woff2 --output-file=bm-it.woff2
for f in bm bm-it; do base64 -i "$f.woff2" | tr -d '\n' > "$f.b64"; done
{
  printf '/* Bodoni Moda (OFL) — display subset, opsz=96 wght=400; see site/fonts/OFL.txt */\n'
  printf '@font-face{font-family:"Bodoni Moda Disp";font-style:normal;font-weight:400;font-display:block;src:url(data:font/woff2;base64,%s) format("woff2")}\n' "$(cat bm.b64)"
  printf '@font-face{font-family:"Bodoni Moda Disp";font-style:italic;font-weight:400;font-display:block;src:url(data:font/woff2;base64,%s) format("woff2")}\n' "$(cat bm-it.b64)"
} > bm.css
ls -la bm.woff2 bm-it.woff2 bm.css
