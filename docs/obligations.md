# Obligations — the dated things nothing else tracks

Written 2026-08-12. This file exists because three hard dates lived only in
conversation, and a deadline that lives in a chat transcript is a deadline
that gets missed. One line per obligation, with its source and its owner.
Update in place; this is operational state, not a sealed record.

| Due | What | Owner | Source / notes |
|---|---|---|---|
| **by 2027-08-11** | Renew `flamsteed.io` (registered 2026-08-11 at Porkbun, standard 1-year term assumed). **Confirm auto-renew is ON in the Porkbun panel** — that turns this row from a deadline into a receipt check. | Owner | Registration completed 2026-08-11; exact expiry not independently verified (RDAP lookup returned nothing) — confirm the date shown in the Porkbun panel and correct this row if it differs. |
| **~2026-09-10** | Decision + staging deadline for the September qualifier-window release (window ≈ Sep 21 – Oct 6, standard FIFA calendar — confirm exact dates before staging). Only applies if the "ongoing product" path is chosen; if the archive path is chosen, strike this row and say so. | Owner decides; assistant stages | Product spec's first kill criterion is citations; this window is the only public cadence before AC2027 (Jan 2027). |
| **this month** (nice-to-have, no hard date) | Free trademark register screen for "Flamsteed": UKIPO, EUIPO, USPTO, WIPO Global Brand DB; classes 9/35/41/42. Engage an attorney only when a paid pilot approaches signature. | Owner | No register has been searched as of 2026-08-12. John Flamsteed d. 1719, but living institutions may hold marks. |
| **after the truth-batch settles** (unblocked since 2026-08-11) | Submit the CAP Copy Advice request against the corrected live copy. | Owner | Draft exists in docs/superpowers/ops/; its stated blocker (site not live) cleared 2026-08-11. |
| ~~standing~~ **DONE 2026-08-13** | Off-machine backup. Owner named the destination 2026-08-13: a **private GitHub repo, `onbiggerthingsB/flamsteed-vault`** (visibility confirmed PRIVATE). Holds the irreplaceable 45 MB — `data/{odds_raw,odds_raw_dry_run,stores,totals_store,clv_store}` + `~/Desktop/flamsteed-backups/` — with a SHA-256 per file in `MANIFEST.sha256`. **Restore-verified**: fresh clone from GitHub, 2,556/2,556 checksums OK, and the all-refs bundle re-cloned to 878 commits / 53 branches. Secret-scanned before push (positive-controlled): zero hits for the API key or any credential. | Assistant (done) | Scoping correction: `data/` is 6.1G but 6.0G of that is `cache/`, of which 3.6G is `cache/oa_dev` posterior fits — costly (~a day of compute) but reproducible and lock-attested. Owner ruled 2026-08-13 to exclude them. **Refresh when the stores change**; nothing automates this yet. |
| **operational caveat** | GitHub disables `schedule:` workflows (the uptime probe, `.github/workflows/uptime.yml`) after 60 days of repo inactivity. If the repo goes quiet for two months, re-enable from the Actions tab. | Whoever notices | Documented in the workflow itself. |

Retired obligations, kept so their absence is legible:

- ~~AC2027 T-30 paid probe (~2026-12-08)~~ — retired **unexecuted** with the
  confirmatory programme's closure, 2026-08-12; sealed in the lock-v10
  amendment of `reports/oa_prereg.md`. No further Odds-API spend under that
  programme.
