#!/usr/bin/env python3
"""Extract every numeric claim and every href from a page, for diffing.

Numbers: -?[0-9]+([.,][0-9]+)?%? including U+2212 minus. HTML comments,
<style> and <script> bodies are stripped first (CSS px values are not
claims). Output: 'NUM <token>' and 'HREF <value>' lines, sorted, unique.
"""
import re, sys, pathlib

text = pathlib.Path(sys.argv[1]).read_text()
text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
text = re.sub(r"<script.*?</script>", " ", text, flags=re.S | re.I)
hrefs = sorted(set(re.findall(r'href="([^"]+)"', text)))
body = re.sub(r"<[^>]+>", " ", text)
nums = sorted(set(re.findall(r"[−-]?\d+(?:[.,]\d+)?%?", body)))
for n in nums:
    print("NUM", n)
for h in hrefs:
    print("HREF", h)
