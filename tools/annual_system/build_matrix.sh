#!/usr/bin/env bash
# Assemble the design-system hand test at /tmp/fonts/matrix.html, plus a
# script-free twin at /tmp/fonts/matrix-nojs.html.
#
# The template is committed without the font bytes so the repo does not
# carry 26 KB of base64 twice; the embed is spliced in at build time from
# /tmp/fonts/bm.css (tools/build_fonts.sh). Run this, then screenshot the
# three states: with script, script-free, and at 390px.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-/tmp/fonts/matrix.html}"

python3 - "$HERE" "$OUT" <<'PY'
import pathlib, sys

here, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
bm = pathlib.Path("/tmp/fonts/bm.css")
if not bm.exists():
    sys.exit("missing /tmp/fonts/bm.css — run tools/build_fonts.sh first")

js = (here / "system.js").read_text()
mark = "/* ===== BLOCK B"
if mark not in js:
    sys.exit("system.js has no BLOCK B banner — cannot split the two snippets")
head, body = js[: js.index(mark)], js[js.index(mark) :]

template = (here / "matrix.template.html").read_text()
common = (
    ("@@BM_CSS@@", bm.read_text().strip()),
    ("@@SYSTEM_CSS@@", (here / "system.css").read_text().strip()),
)
for token, _ in common + (("@@JS_HEAD@@", ""), ("@@JS_BODY@@", "")):
    if token not in template:
        sys.exit(f"template is missing {token}")


def render(js_head, js_body):
    # The script-free twin is cut from the TEMPLATE, where the two script
    # elements are still single unsplit tokens. Never strip them out of the
    # rendered page with a regex: prose inside the CSS and the JS mentions
    # script elements, and a lazy <script>.*?</script> match will start on
    # one of those and swallow the rest of the document.
    page = template
    if js_head is None:
        page = page.replace("<script>@@JS_HEAD@@</script>\n", "")
        page = page.replace("<script>@@JS_BODY@@</script>\n", "")
    else:
        page = page.replace("@@JS_HEAD@@", js_head).replace("@@JS_BODY@@", js_body)
    for token, value in common:
        page = page.replace(token, value)
    return page


out.parent.mkdir(parents=True, exist_ok=True)
page = render(head.strip(), body.strip())
out.write_text(page)

nojs = render(None, None)
twin = out.with_name(out.stem + "-nojs" + out.suffix)
twin.write_text(nojs)

assert "<script" not in nojs, "no-JS twin still contains a script element"
assert "@@" not in page and "@@" not in nojs, "unreplaced token left in output"
# The twin must differ from the page ONLY by the two script elements.
assert len(page) - len(nojs) == len(head.strip()) + len(body.strip()) + len(
    "<script></script>\n"
) * 2, "no-JS twin lost more than the scripts"
print(f"{out} — {len(page)} bytes")
print(f"{twin} — {len(nojs)} bytes (scripts removed)")
PY
