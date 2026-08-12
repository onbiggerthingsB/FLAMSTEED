#!/usr/bin/env python3
"""Extract every numeric claim and every href from a page, for diffing.

Numbers: -?[0-9]+([.,][0-9]+)?%? including U+2212 minus. HTML comments,
<style> and <script> bodies are stripped first (CSS px values are not
claims). Output: 'NUM <token>' and 'HREF <value>' lines, sorted, unique.

The two raw-text elements are stripped in ONE left-to-right pass, closed by
a backreference, because they are raw text: a browser tokenising this page
takes whichever opens first and reads to that same element's end tag. Two
separate passes get it wrong the moment either element's body mentions the
other's tag in prose — the head script of the redesigned index says "BLOCK A
goes in <head>, BEFORE <style>", and a style-first pass started matching
there, ran to the real </style> five hundred lines later, ate the script's
own end tag on the way, and left the following script pass to swallow the
entire body. The page extracted four numbers instead of fifty and the diff
read as a total wipe.

<title> elements are also dropped before the numeric pass. Inside an SVG a
<title> is the accessible name of one mark — PLATE I gives every one of its
104 marks a per-match provenance tooltip — and those are apparatus, not
claims the page makes to a reader. Dropping the element removes its text
entirely (never leaving the digits behind), and it is done AFTER the href
pass so no link can be lost with it. The document <title> goes the same way;
the three pages carry no figure in theirs.
"""
import re, sys, pathlib

text = pathlib.Path(sys.argv[1]).read_text()
text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
text = re.sub(r"<(script|style)\b[^>]*>.*?</\1\s*>", " ", text, flags=re.S | re.I)
hrefs = sorted(set(re.findall(r'href="([^"]+)"', text)))
text = re.sub(r"<title[^>]*>.*?</title>", " ", text, flags=re.S | re.I)
body = re.sub(r"<[^>]+>", " ", text)
nums = sorted(set(re.findall(r"[−-]?\d+(?:[.,]\d+)?%?", body)))
for n in nums:
    print("NUM", n)
for h in hrefs:
    print("HREF", h)
