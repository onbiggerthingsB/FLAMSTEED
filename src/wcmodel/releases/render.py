"""Render a release payload: self-contained HTML one-pager + fully-enveloped CSV.

HTML: one decimal per probability (more digits = overclaimed precision);
provenance + freshness footer always on-page. CSV: machine-readable, full
precision, the SAME envelope as comment-header lines (F2)."""
from __future__ import annotations

import html as _html
import io


def _pct(x: float) -> str:
    return f"{100.0 * float(x):.1f}%"


def render_html(release: dict) -> str:
    p, ds = release["provenance"], release["data_source"]
    rows_html = []
    for r in release["rows"]:
        h, a = _html.escape(r["home"]), _html.escape(r["away"])
        venue = "neutral venue" if r["neutral"] else f"{h} at home"
        o = r["one_x_two"]
        rows_html.append(
            f"<tr><td>{r['date']}</td><td>{h} v {a}<br><small>{venue}</small></td>"
            f"<td>{_pct(o['home'])}</td><td>{_pct(o['draw'])}</td>"
            f"<td>{_pct(o['away'])}</td>"
            f"<td>{_pct(r['totals']['over_2_5'])}</td>"
            f"<td>{_html.escape(r['modal_score'])} ({_pct(r['modal_score_p'])})</td></tr>")
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>{_html.escape(release['model_name'])} — {_html.escape(release['window_label'])}</title>
<style>
 body{{font:15px/1.5 system-ui,sans-serif;max-width:720px;margin:2rem auto;padding:0 1rem}}
 table{{border-collapse:collapse;width:100%}} td,th{{border:1px solid #ccc;padding:.4rem .6rem;text-align:left}}
 footer{{margin-top:1.2rem;font-size:.82em;color:#444}}
</style></head><body>
<h1>{_html.escape(release['window_label'])}</h1>
<p>Forecasts by {_html.escape(release['model_name'])} — probabilities, not picks.
<a href="{release['methodology_url']}">Methodology</a> ·
<a href="{release['archive_url']}">Timestamped archive</a></p>
<table>
<tr><th>Date</th><th>Fixture</th><th>Home win</th><th>Draw</th><th>Away win</th>
<th>Over 2.5 goals</th><th>Most likely score</th></tr>
{''.join(rows_html)}
</table>
<footer>as-of (all data strictly before): {p['as_of']} · posterior {p['posterior_key']}
· code {p['git']} · {release['n_draws']:,} posterior draws ·
data: {_html.escape(ds['name'])}, latest result {ds['latest_result']} ·
{_html.escape(release['license'])}</footer>
</body></html>"""


def render_csv(release: dict) -> str:
    p, ds = release["provenance"], release["data_source"]
    buf = io.StringIO()
    buf.write(f"# model: {release['model_name']}\n")
    buf.write(f"# window: {release['window_label']}\n")
    buf.write(f"# license: {release['license']}\n")
    buf.write(f"# as_of: {p['as_of']} posterior: {p['posterior_key']} git: {p['git']}\n")
    buf.write(f"# n_draws: {release['n_draws']}\n")
    buf.write(f"# data_source: {ds['name']} latest_result: {ds['latest_result']}\n")
    buf.write(f"# methodology: {release['methodology_url']}\n")
    buf.write(f"# archive: {release['archive_url']}\n")
    buf.write("date,home,away,neutral,p_home,p_draw,p_away,"
              "over_1_5,over_2_5,over_3_5,modal_score,modal_score_p\n")
    for r in release["rows"]:
        o, t = r["one_x_two"], r["totals"]
        buf.write(",".join([
            r["date"], r["home"], r["away"], str(int(r["neutral"])),
            f"{o['home']}", f"{o['draw']}", f"{o['away']}",
            f"{t['over_1_5']}", f"{t['over_2_5']}", f"{t['over_3_5']}",
            r["modal_score"], f"{r['modal_score_p']}",
        ]) + "\n")
    return buf.getvalue()
