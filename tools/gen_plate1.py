#!/usr/bin/env python3
"""PLATE I — all 104 forecasts, one mark per match. Deterministic."""
import json, pathlib

R = json.load(open("reports/live_scorecard_final.json"))["rows"]
assert len(R) == 104, len(R)
W, H, L, T, B = 1040, 360, 46, 26, 330
def x(i): return L + i * (W - L - 18) / 103
def y(p): return B - p * (B - T)
marks, seps = [], []
prev = None
hits = 0
for i, r in enumerate(R):
    p = r["probs"][r["outcome"]]
    modal = max(r["probs"], key=r["probs"].get)
    hit = modal == r["outcome"]
    hits += hit
    cx, cy = round(x(i), 1), round(y(p), 1)
    title = f'{r["home"]} v {r["away"]} — P({r["outcome"]})={p:.2f}'
    if hit:
        marks.append(f'<circle cx="{cx}" cy="{cy}" r="3.5" fill="var(--ink)"><title>{title}</title></circle>')
    else:
        marks.append(f'<circle cx="{cx}" cy="{cy}" r="3.5" fill="none" stroke="var(--oxblood)" stroke-width="1.2"><title>{title}</title></circle>')
    if prev and r["stage"] != prev:
        sx = round(x(i) - 4.5, 1)
        seps.append(f'<line x1="{sx}" y1="{T}" x2="{sx}" y2="{B}" stroke="var(--frame)" stroke-width=".5" stroke-dasharray="1 4"/>')
    prev = r["stage"]
grid = "".join(
    f'<line x1="{L}" y1="{y(g)}" x2="{W-18}" y2="{y(g)}" stroke="var(--frame)" stroke-width=".4" opacity=".45"/>'
    f'<text x="{L-8}" y="{y(g)+3}" text-anchor="end" font-size="10" fill="var(--ink-dim)" font-family="ui-monospace,monospace">.{int(g*100)}</text>'
    for g in (0.25, 0.5, 0.75)
)
svg = (
    f'<svg role="img" aria-labelledby="p1t p1d" viewBox="0 0 {W} {H}">'
    f'<title id="p1t">Plate I — every 2026 forecast, one mark per match</title>'
    f'<desc id="p1d">104 marks in tournament order; vertical position is the probability issued to the outcome that happened; hollow marks are matches where the modal forecast missed.</desc>'
    f'{grid}{"".join(seps)}<g>{"".join(marks)}</g>'
    f'<line x1="{L}" y1="{B}" x2="{W-18}" y2="{B}" stroke="var(--ink)" stroke-width="1"/></svg>'
)
out = pathlib.Path("/tmp/fonts"); out.mkdir(exist_ok=True)
(out / "plate1.svg").write_text(svg)
(out / "plate1_caption.txt").write_text(
    f"One mark per match, in the order they were played: the height of each mark is the probability this system published, before kick-off, for the outcome that then happened. Filled marks are matches where the most likely outcome arrived ({hits} of 104); hollow marks are the misses, printed at the same size."
)
print("hits:", hits, "| bytes:", len(svg))
