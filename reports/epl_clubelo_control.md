# The clubelo control: measuring the free prior before buying anything

**Written:** 2026-09-01 · **Repo:** `/Users/likerun/Desktop/worldcup` at `ce80325` (a concurrent workflow owns the tree; HEAD moved during the session), **read-only**
(nothing in the tree was written, staged or committed by this work; all artefacts live in
the session scratchpad) · **Scope:** step 1 of the squad-value memo's ladder — *"measure the
free control first."*

**Headline, numbers first.** Over the **30 promotion cohorts** with a point-in-time clubelo
rating at entry *and* a point-in-time clubelo reference at the end of the club's first EPL
season (2015/16–2024/25), clubelo-at-entry scores **MAE 57.7 Elo** against **64.3** for our
flat `division_mean − 75` seed — an apparent **6.6-point** improvement whose 95% paired
bootstrap CI is **[−8.6, +22.1]** and which wins in only **15 of 30** cohorts. Against the
steelman flat rule (−93, the same *z*-displacement in clubelo's wider units) the margin falls
to **3.5** points, CI **[−8.7, +16.2]**. Clubelo does buy real **spread** the flat seed cannot
express — mean within-cohort range **70.3 Elo**, max **182.5** — but on the one arbiter that
belongs to neither system, **that spread does not pay**: within-cohort clubelo entry rating
correlates with first-season EPL points at **r = +0.14 (n = 33, p = 0.43)**, and it orders the
three promoted clubs correctly in **17 of 33** pairwise comparisons — a coin flip.

---

## 1. What actually happened to the source

**The premise the squad-value memo relied on has expired.** That memo's step 1 rests on
clubelo being *"already point-in-time by construction via its dated route."* As of this
session the dated route does not exist.

| Route | Result |
|---|---|
| `http://api.clubelo.com/2015-08-01` | **502**, `Server: Microsoft-IIS/10.0` — 25 attempts over ~20 min |
| `http://api.clubelo.com/Burnley` (club history) | **502** |
| `http://api.clubelo.com/ENG` | **502** |
| `http://api.clubelo.com/Fixtures` | **200**, body: `Fixtures API deactivated` |
| `http://clubelo.com/API` (the docs) | **301 → the homepage** |
| `https://clubelo.com/2015-08-01` (site dated route) | **302 → `/`** |

The 502 carries clubelo's own IIS/ASP.NET headers, so this is their origin failing, not our
proxy: `/Fixtures` answers from the same host with a deliberate deactivation notice. **The
free by-date API named in `SOURCES.md` is, right now, not fetchable.** Whatever the bridge
prereg says about clubelo must survive that fact.

What *is* still reachable is the website, whose club pages embed a dated Elo series in a
Vega spec — but only a rolling **four-year** window (2022-08-31 → 2026-08-31), and, as §2
shows, a **restated** one.

### The data this memo actually used

Because the live route is gone, every clubelo number here comes from a **contemporaneous
capture** — an observation made at the time and preserved — never from today's rendering:

1. **Our own three committed verbatim API snapshots**, `config/squads/clubelo_{20221120,20240614,20260610}.csv`
   (`Rank,Club,Country,Level,Elo,From,To`), read-only from the repo.
2. **A 1st-and-15th archive**, 2000-07-01 → 2025-06-01, 245,033 rows, 26,410 English
   ([xgabora/Club-Football-Match-Data-2000-2025](https://github.com/xgabora/Club-Football-Match-Data-2000-2025), `data/EloRatings.csv`).
3. **A daily scrape with `From`/`To` and the retrieval instant**, 2023-03-27 → 2026-01-14,
   40,385 English rows ([tonyelhabr/club-rankings](https://github.com/tonyelhabr/club-rankings), release `clubelo-club-rankings.csv`).

Both mirrors are third parties' copies. Neither is trusted on its own — §2 is the audit that
earns them.

---

## 2. PIT honesty: the answer is split, and the split is the finding

**(a) Contemporaneous clubelo captures agree with each other, exactly.** Using the `From`/`To`
interval in our own committed snapshots to identify ratings that were *provably static* across
a mirror's capture date, and comparing the two:

| Our verbatim capture | Mirror date | Clubs compared | max abs diff |
|---|---|---:|---:|
| `clubelo_20221120.csv` | 2022-11-15 | 362 | **0.005** |
| `clubelo_20221120.csv` | 2022-12-01 | 329 | **0.005** |
| `clubelo_20240614.csv` | 2024-06-15 | 370 | **0.005** |
| `clubelo_20240614.csv` | 2024-06-01 | 256 | **0.005** |

**1,317 club-date comparisons, zero mismatches**; 0.005 is exactly half the mirror's 2-decimal
rounding. The mirror is a faithful copy, and two independent observers of clubelo's past agree.

**(b) Clubelo did not quietly revise its own history while the API was up.** A revision audit
over the 2.8-year daily archive asks whether a rating for a fixed `(Club, From)` interval ever
changes across retrieval dates:

| Interval settled for ≥ | intervals | ever changed | median spread | > 5 Elo | max |
|---:|---:|---:|---:|---:|---:|
| 1 day | 5,088 | 49.1% | 0.0027 | 623 | 74.53 |
| 3 days | 2,328 | 44.2% | 0.0001 | 24 | 20.87 |
| **7 days** | **1,017** | 44.5% | **0.0001** | **0** | **2.97** |
| 14 days | 291 | 63.6% | 0.0002 | 0 | 2.97 |

The large one-day spreads are **not** revisions: they come in pairs of equal magnitude between
the two clubs of a single match (Man City / Tottenham both 28.607 on `From = 2024-11-24`;
Luton / Brighton both 24.027 on 2024-01-31) — a scrape landing between a result and its Elo
update. Once an interval has been settled a week, **the maximum restatement anywhere in 2.8
years is 2.97 Elo and the median is 0.0001.**

**(c) The causality spot-check the task asked for — a promotion window.** Sunderland, promoted
to 2025/26 via the playoff final on 2025-05-24, first EPL match 2025-08-16:

```
2025-05-13  1572.83     2025-07-01  1580.09      2025-08-16  1594.19   <- first EPL match
2025-05-24  1580.09     2025-08-01  1580.09      2025-08-23  1590.79
2025-06-01  1580.09     2025-08-15  1580.09      2025-08-30  1594.76
```

The rating moves on match days and on no others; a date in the promotion summer contains
nothing from the season that followed. **Clubelo's dated response was causal by construction,
exactly as claimed.**

**(d) But today's clubelo restates history, and by a lot.** The decisive test needs a date on
which nothing could have changed. On **2024-08-01** every one of the 44 English rows in the
daily archive has `From < 2024-08-01 < To` — English football's off-season, every rating
provably static. Comparing what clubelo published that day with what clubelo says about that
day *now*:

| Club | clubelo, then | clubelo, today | Δ |
|---|---:|---:|---:|
| Sunderland | 1434.67 | 1537.74 | **+103.08** |
| Leeds | 1606.80 | 1681.15 | +74.35 |
| Brighton | 1713.14 | 1774.70 | +61.56 |
| Man United | 1779.01 | 1838.97 | +59.96 |
| Liverpool | 1900.66 | 1952.12 | +51.46 |
| Burnley | 1611.23 | 1661.55 | +50.32 |
| … | | | |
| Arsenal | 1946.88 | 1945.11 | −1.77 |

**n = 19, mean Δ +37.7, mean \|Δ\| 37.8, max 103.1.** The field's SD compresses from **132.3 to
115.9** — the signature of a recalibration that shrinks the spread, hitting lower-division
clubs hardest (Sunderland was in League One). Repeating at 2025-08-01: mean \|Δ\| 14.8, max 33.0.

**The verdict on item 4 is therefore two-sided, and the second side is the one that matters:**

> Clubelo's by-date route **was** point-in-time honest — verified by two independent
> contemporaneous observers agreeing to 0.005, by a 2.8-year revision audit bounded at 2.97
> Elo, and by a clean promotion-window trajectory. But clubelo's **current** account of the
> same past dates has been restated by up to 103 Elo, and the by-date route that would let
> anyone check is returning 502. **The PIT property lived in the capture, not in the source,
> and it is no longer recoverable from clubelo.** This is — in weaker form, and without the
> licence problem — the same failure mode the squad-value memo disqualified Transfermarkt for:
> *dated history that is the publisher's account of history, restatable without notice.*

That is a correction to `SOURCES.md`, which records the `/<date>` route as a live PIT
capability. Two smaller corrections: the by-date dump carries English **levels 1–2 only**
(44 clubs), not levels 3–5; and the Championship count in that response is **24**, not 26.

---

## 3. Cohorts

Promotion cohorts are derived read-only from `data/epl/matches.parquet` season membership —
a club in season *S* that was not in *S−1*. That yields exactly **33** cohorts across
2015/16–2025/26, three per season.

**2014/15 is not derivable.** Neither `matches.parquet` nor `matches_e1.parquet` contains
2013/14, so the archive cannot name that season's promoted trio. The task's example pairing
of *Burnley-2014* with *Leeds-2020* therefore reads here as **Burnley-2016/17 vs Leeds-2020/21**;
Burnley does appear, three times (2016/17, 2023/24, 2025/26).

**Of the 33: 30 are measured, 3 are refused.** The 2025/26 trio (Burnley, Leeds, Sunderland)
has a clean PIT entry rating at 2025-08-01 but **no** PIT end-of-season reference: that season
ended 2026-05-24 and the last contemporaneous capture anywhere is 2026-01-14. Per the roadmap's
own rule — *a refusal is an outcome in the ledger, not permission to score an easier subset* —
those three are excluded from the headline MAE and reported separately. Using today's restated
site to fill them would import exactly the error §2 documents.

---

## 4. The table

`ce entry` = clubelo at 1 August. `flat` = clubelo-units analogue of our rule: the mean over
the **20 clubs that just completed a season** (`epl/elo.py:361`, relegated clubs included),
minus 75. `ce end` = clubelo at the first capture after the season's last match. `our seed` /
`our end` = the frozen ladder (`k=20, carryover=1, home_advantage=40, promoted_offset=−75`)
run read-only over the archive.

| season | club | ce entry | flat seed | ce end | closer | our seed | our end | finish |
|---|---|---:|---:|---:|:--:|---:|---:|---:|
| 2015/16 | Bournemouth | 1597 | 1611 | 1622 | flat | 1425.0 | 1430.8 | 15 |
| 2015/16 | Norwich | 1618 | 1611 | 1582 | flat | 1425.0 | 1385.5 | 19 |
| 2015/16 | Watford | 1577 | 1611 | 1626 | flat | 1425.0 | 1430.5 | 13 |
| 2016/17 | Burnley | 1638 | 1633 | 1629 | flat | 1425.7 | 1419.9 | 16 |
| 2016/17 | Hull | 1590 | 1633 | 1570 | **clubelo** | 1425.7 | 1398.9 | 18 |
| 2016/17 | Middlesbrough | 1596 | 1633 | 1562 | **clubelo** | 1425.7 | 1374.7 | 19 |
| 2017/18 | Brighton | 1583 | 1636 | 1634 | flat | 1433.0 | 1445.9 | 15 |
| 2017/18 | Huddersfield | 1475 | 1636 | 1568 | flat | 1433.0 | 1419.4 | 16 |
| 2017/18 | Newcastle | 1623 | 1636 | 1672 | flat | 1433.0 | 1457.2 | 12 |
| 2018/19 | Cardiff | 1575 | 1649 | 1611 | **clubelo** | 1441.2 | 1406.0 | 18 |
| 2018/19 | Fulham | 1632 | 1649 | 1589 | **clubelo** | 1441.2 | 1374.3 | 19 |
| 2018/19 | Wolves | 1592 | 1649 | 1724 | flat | 1441.2 | 1514.1 | 7 |
| 2019/20 | Aston Villa | 1616 | 1681 | 1627 | **clubelo** | 1444.9 | 1431.7 | 17 |
| 2019/20 | Norwich | 1635 | 1681 | 1543 | **clubelo** | 1444.9 | 1347.7 | 20 |
| 2019/20 | Sheffield United | 1624 | 1681 | 1703 | flat | 1444.9 | 1507.3 | 10 |
| 2020/21 | Fulham | 1592 | 1673 | 1627 | **clubelo** | 1456.8 | 1414.2 | 18 |
| 2020/21 | Leeds | 1634 | 1673 | 1784 | flat | 1456.8 | 1545.5 | 10 |
| 2020/21 | West Brom | 1603 | 1673 | 1618 | **clubelo** | 1456.8 | 1406.2 | 19 |
| 2021/22 | Brentford | 1672 | 1704 | 1714 | flat | 1465.4 | 1491.4 | 13 |
| 2021/22 | Norwich | 1655 | 1704 | 1576 | **clubelo** | 1465.4 | 1382.2 | 20 |
| 2021/22 | Watford | 1673 | 1704 | 1583 | **clubelo** | 1465.4 | 1375.4 | 19 |
| 2022/23 | Bournemouth | 1630 | 1696 | 1666 | flat | 1474.1 | 1462.1 | 15 |
| 2022/23 | Fulham | 1636 | 1696 | 1740 | flat | 1474.1 | 1516.4 | 10 |
| 2022/23 | Nottingham Forest | 1612 | 1696 | 1670 | flat | 1474.1 | 1478.5 | 16 |
| 2023/24 | Burnley | 1726 | 1716 | 1620 | flat | 1484.2 | 1420.4 | 19 |
| 2023/24 | Luton | 1607 | 1716 | 1572 | **clubelo** | 1484.2 | 1418.0 | 18 |
| 2023/24 | Sheffield United | 1644 | 1716 | 1523 | **clubelo** | 1484.2 | 1373.2 | 20 |
| 2024/25 | Ipswich | 1568 | 1670 | 1597 | **clubelo** | 1491.0 | 1411.1 | 19 |
| 2024/25 | Leicester | 1644 | 1670 | 1620 | **clubelo** | 1491.0 | 1422.0 | 18 |
| 2024/25 | Southampton | 1600 | 1670 | 1554 | **clubelo** | 1491.0 | 1368.7 | 20 |
| *2025/26* | *Burnley* | *1730* | *1729* | *refused* | — | *1504.1* | *1431.7* | *19* |
| *2025/26* | *Leeds* | *1722* | *1729* | *refused* | — | *1504.1* | *1563.4* | *14* |
| *2025/26* | *Sunderland* | *1547* | *1729* | *refused* | — | *1504.1* | *1572.4* | *7* |

---

## 5. The headline measurement

**Reference = clubelo Elo at the end of the club's first EPL season. 30 cohorts. Clubelo
units throughout — no mapping, no fitting.** The `−75` transfers literally because both
systems are the standard 400-point base-10 logistic (`epl/elo.py:14`, `_ELO_SCALE = 400`), so
75 rating points denote the same expected score in either.

| prior | MAE | bias |
|---|---:|---:|
| **clubelo at 1 August** | **57.66** | −8.59 |
| flat: prev-season 20-club mean − 75 *(faithful to `elo.py:361`)* | **64.27** | +42.63 |
| flat: incoming 20-club mean − 75 *(variant)* | 65.45 | +45.33 |
| flat: faithful, scale-matched −93 *(steelman)* | 61.12 | +24.78 |

| comparison | mean(\|flat\| − \|clubelo\|) | 95% CI | P(clubelo better) | cohorts won |
|---|---:|---|---:|---:|
| vs faithful −75 | **+6.62** | [−8.55, +22.06] | 0.803 | 15/30 |
| vs steelman −93 | +3.46 | [−8.71, +16.18] | 0.708 | 16/30 |

**Both intervals cross zero.** On its own this is "clubelo is somewhat better, not
distinguishably so."

### Why this comparison flatters clubelo, and why the obvious alternative is worse

The reference is clubelo's own end-of-season rating, which is **autocorrelated with clubelo's
entry rating** — the same system carrying the club forward. The natural fix, scoring both
priors against **our** end-of-first-season Elo, has the mirror-image defect, and it is far more
severe. Re-running the frozen ladder at three offsets:

| `promoted_offset` | MAE flat | MAE clubelo | gap |
|---:|---:|---:|---:|
| 0 | 72.57 | 103.38 | −30.81 |
| **−75 (frozen)** | **51.06** | **59.94** | **−8.88** |
| −150 | 49.42 | 86.93 | −37.51 |

Our end-of-season rating moves **~1.1 Elo for every 1 Elo of seed change** — the seed does not
wash out over 38 matches. The clubelo arm is being scored against a target the flat arm
defines, and its measured MAE swings from 60 to 103 on an arbitrary configuration choice.
**That comparison cannot arbitrate and is not used as the headline.** (For the record it
returns MAE 59.94 clubelo vs 51.06 flat at the frozen setting, 33 cohorts.)

So both Elo-unit comparisons are captured by their own reference, in opposite directions:
**[flat better by 8.9] … [clubelo better by 6.6]**. The honest reading is that the bracket
contains zero and neither endpoint is trustworthy. The question has to be settled outside
both rating systems.

---

## 6. The spread, and whether it pays

**It exists, and it is large.** The flat seed prices every promoted club in a season
identically; clubelo does not:

| season | clubelo entry, three promoted clubs | range | flat |
|---|---|---:|---:|
| 2015/16 | Watford 1577 / Bournemouth 1597 / Norwich 1618 | 41.1 | 0 |
| 2016/17 | Hull 1590 / Middlesbrough 1596 / Burnley 1638 | 47.9 | 0 |
| 2017/18 | **Huddersfield 1475** / Brighton 1583 / Newcastle 1623 | **147.4** | 0 |
| 2018/19 | Cardiff 1575 / Wolves 1592 / Fulham 1632 | 57.3 | 0 |
| 2019/20 | Aston Villa 1616 / Sheffield Utd 1624 / Norwich 1635 | 18.5 | 0 |
| 2020/21 | Fulham 1592 / West Brom 1603 / Leeds 1634 | 41.8 | 0 |
| 2021/22 | Norwich 1655 / Brentford 1672 / Watford 1673 | 18.1 | 0 |
| 2022/23 | Nott'm Forest 1612 / Bournemouth 1630 / Fulham 1636 | 23.9 | 0 |
| 2023/24 | Luton 1607 / Sheffield Utd 1644 / Burnley 1726 | 119.9 | 0 |
| 2024/25 | Ipswich 1568 / Southampton 1600 / Leicester 1644 | 75.3 | 0 |
| 2025/26 | **Sunderland 1547** / Leeds 1722 / **Burnley 1730** | **182.5** | 0 |

Mean within-cohort range **70.3 Elo**, median 47.9, max 182.5. Pooled SD across all 33 is
**50.5 Elo**; the flat seed's within-season SD is **0.0** by construction. Across the archive
clubelo's promoted-club ratings run from **1475** (Huddersfield 2017/18) to **1730** (Burnley
2025/26) — a **255-point** span the flat rule collapses to a point.

**It does not pay.** The cleanest illustration is the widest cohort. In 2025/26 clubelo
separated the three promoted clubs by **182.5 Elo** — its most confident promotion call in the
archive — ranking them Burnley 1730, Leeds 1722, **Sunderland 1547**. They finished **19th,
14th and 7th**: Sunderland, the club clubelo rated 183 points *below* Burnley, took 54 points
to Burnley's 22 and finished twelve places above it. The flat seed, saying nothing, was not
wrong about this; clubelo was, and confidently.

Three arbiters that belong to neither rating system:

| test | clubelo | flat |
|---|---|---|
| within-cohort entry rating vs first-season EPL points | **r = +0.143** (n = 33, p = 0.43) | undefined (constant) |
| pairwise ordering of the three promoted clubs | **17/33 correct (52%)** | 0/33 resolvable |
| mean \|predicted finishing rank − actual\| | **3.67** | **3.30** |
| mean entry rating: survived vs relegated | 1611.2 vs **1628.7** (−17.5, *wrong sign*, p = 0.33) | — |

### The positive control that makes this interpretable

A null result is worthless unless the instrument works. Running the identical statistic on the
**187 continuing club-seasons** — clubs whose prior our model takes from carried-over Elo, not
from a flat seed:

| | clubelo at 1 Aug vs season points | our carried Elo vs season points |
|---|---:|---:|
| **continuing clubs** (n = 187) | **r = +0.746** (p = 1.6 × 10⁻³⁴) | r = +0.726 (p = 7.3 × 10⁻³²) |
| **promoted clubs** (n = 33) | **r = +0.143** (p = 0.43) | — |

Clubelo is an *excellent* strength signal — as good as our own ladder — **for clubs it has
Premier League history on.** For clubs whose rating was earned in the Championship, at the
one moment the bridge needs it, that signal is not measurable. The instrument is fine; the
promoted-club case is genuinely different.

**Power, stated honestly.** With n = 33 a correlation is distinguishable from zero at 95% only
if |r| > **0.343**. The observed +0.143 means **"no measurable signal," not "proven zero"** — a
true correlation up to ~0.34 would be invisible in this archive, and 33 cohorts is all the
Premier League has produced since 2015. This is a low-power null and should be labelled one
wherever it is cited.

---

## 7. A level finding that costs nothing and may be worth more

Both systems independently say the flat seed sits at the wrong **depth**, whatever one thinks
of its lack of spread:

- **Our ladder:** promoted clubs finish their first EPL season **−106.0 Elo** below the 20-club
  mean (n = 33, median −109.1, SD 57.2). The seed asserts −75.
- **Clubelo:** promoted clubs enter **−126.2** below the previous-season division mean and end
  their first season **−117.6** below it. Clubelo's field is 1.24× wider than ours, so −117.6
  clubelo points ≈ **−95** of ours.

The our-ladder number is partly circular — it moves ~0.33 Elo per Elo of offset — but not
wholly: sweeping the offset gives realized gaps of −82.6 (at 0), −106.0 (−75), −114.2 (−100),
−131.3 (−150), a **self-consistent fixed point near −120**. Clubelo's −95 is not circular at all.

**State this as a hypothesis, not a finding.** The frozen −75 was tuned to minimise RPS, not to
match an end-of-season level, and `epl/fit.py` records that seed as worth 0.0030 RPS — the
largest single configuration effect measured on this data. A seed that is "too shallow" in
level terms can still be RPS-optimal because it hedges early-season uncertainty. But the
hypothesis *"−75 is 20–45 Elo too shallow"* is testable **entirely inside the existing archive,
with no new source, no licence question and no amendment** — and on this evidence it is a
better use of the bridge's first experiment than a clubelo arm.

---

## 8. Verdict for the E1-bridge draft

**No. Clubelo-at-entry is not a stronger prior than −75, and the fixed-bridge secondary arm
should stay −75-based.** The measured margin is +6.6 Elo MAE against a clubelo-defined
reference (95% CI [−8.6, +22.1], 15/30 cohorts), collapsing to +3.5 against the scale-matched
steelman and reversing to −8.9 against our own ladder's reference; the bracket contains zero
and each endpoint is an artefact of whose rating system supplied the target. The spread clubelo
offers is real and large — 70 Elo mean within-cohort range, 182 in 2025/26, against exactly
zero for the flat seed — but on the three arbiters external to both systems it buys nothing:
r = +0.14 with first-season points, 52% pairwise ordering, and a rank error slightly *worse*
than the flat rule, while the same statistic on 187 continuing club-seasons returns r = +0.75,
so the instrument demonstrably works and the promoted-club null is a property of the case, not
the method. Two further facts settle it operationally: clubelo's free by-date API is **returning
502 from its own origin**, and today's site **restates** the very history a backtest would read
by up to **103 Elo** on a date when no English club played — so a clubelo arm would now have to
be built on third-party mirrors of a route that no longer answers, which is precisely the
posture the squad-value memo refused for Transfermarkt. **Keep clubelo where it is — a
documented, attributed source of record for the WC squad-z anchor — do not promote it to the
bridge's secondary arm, and spend the bridge's first experiment instead on the level question
in §7, which needs no new source at all.** The one clubelo-shaped thing worth doing is cheap
and defensive: if the by-date API ever returns, **capture and commit the August-1 dumps for
2015–2025 immediately**, because §2 shows that what clubelo will tell you tomorrow about 2024
is not what it told you in 2024, and the three snapshots already in `config/squads/` are the
only reason any of this was checkable.

---

## Provenance

Every figure above is reproducible from the session scratchpad
(`/private/tmp/claude-502/…/502f349a-2ba8-4bc8-8097-14d3fb7edc63/scratchpad/`):
`ladder.py` (frozen-config Elo ladder, read-only), `scale.py` (dispersion ratios),
`measure.py` → `cohorts.csv`, `final.py` → `cohorts_final.csv` (headline),
`analyse.py` (spread, rank tests), `supp.py` (contamination, scale-free tests),
`control.py` (positive control), `pitcheck.py` / `threeway.py` / `audit2.py` (PIT audit).

**Sources.** [clubelo.com](http://clubelo.com/) — free to use, attribution appreciated;
`SOURCES.md` line 17 · [xgabora/Club-Football-Match-Data-2000-2025](https://github.com/xgabora/Club-Football-Match-Data-2000-2025) ·
[tonyelhabr/club-rankings](https://github.com/tonyelhabr/club-rankings) ·
in-repo, read-only: `config/squads/clubelo_{20221120,20240614,20260610}.csv`,
`data/epl/matches.parquet`, `data/epl/matches_e1.parquet`, `epl/config_frozen.json`,
`epl/elo.py`, `epl/season.py`.

---

## Dated corrections — 2026-09-02 (appended, not edited; revision 4)

**Appended, not edited.** The text above is preserved byte-for-byte as written
on 2026-09-01 — no table, no interval, no verdict sentence has been altered —
and this note corrects it by addition, in the house pattern
(`reports/epl_anchoring_result.md:44-49`, `reports/epl_freshness_result.md:38-41`).
**Preservation is not ratification.** Three of the preserved text's
*recommendations and candidate constants* are superseded **by name** below:
§1 withdraws §7's −120 candidate, §8 supersedes §8's recommendation for the
bridge's first experiment, and §9 supersedes §7's "no amendment" clause.
Everything the preserved text says that is not named in §§1–9 below stands as
written. Written at HEAD `9cc8ef8`, read-only; no archive was opened, no
network request was made, and no number below is a new measurement. Several
are arithmetic on constants the sources already print — §2's two fixed points
and its three Elo gaps, §4's −101.774, and the counts in §5 and §10 — and each
is labelled as arithmetic where it appears.

**Repair note (revision 2).** Revision 1 of this corrected memo (sha256
`1edbbc8d268a7b64bdd20b503e4e7a2e41b8f20c3d846f3b6c1feace6466a8c2`) was
checked against its sources on 2026-09-02 and **REFUTED**
(`a4-groundwork/memos/check.md`, sha256
`b50694ed3ca121921ec00d1ee8eef03a2b99b36cbd5f91d666e429c698fd8f98`). This
revision repairs every issue that check raised and changes no verdict and no
measured number: the sizing script's abbreviated digest was transcribed
`…ba425` for `…b4425` (all digests are now printed in full and were recomputed
with `shasum -a 256`); "≈ 22 Elo" was a loose rounding of 22.6; "Three
caveats" described four review bullets; a §5 provenance-table "quote" was a
reconstruction of a row plus its column header; `epl/fit.py:90` is a line of
the `ARCHITECTURE_NOTES` string tuple, not a docstring;
`reports/epl_lowerdiv_prereg.md:829-834` → `:829-835` and
`reports/epl_baseline.md:148-150` → `:148-149`; §7's "no amendment" clause was
not superseded by name and now is (§9); the network observations of §§1–2 are
now tagged UNVERIFIED-as-of-today; and §10 replaces the previous §9.

**Repair note (revision 3).** Revision 2 of this corrected memo (sha256
`be10843b18305d0fc26d9d41fe5f47502d2269e1b4e3cf49e60c24922cb833b1`) was
checked against its sources on 2026-09-02 and found **REFUTED** by one issue
in the companion seed-depth memo, plus six residual findings, four of them
concerning this memo (`shots-v2/memos/check2.md`, sha256
`e55e3469dc691b2c272123bfeb56cbdbee0326490be2659ef8ea247aa3e34b67`). Three of
those four are repaired below; the fourth is out of this round's scope and is
named at the end of this note, unrepaired. No verdict and no measured number
changes: the `ARCHITECTURE_NOTES` string tuple's extent was given as
`epl/fit.py:86-92` (the declaration plus its first two entries); verified
against HEAD `9cc8ef8` (`git show 9cc8ef8:epl/fit.py`) that the tuple opens at
`:86` and closes at `:104` — corrected to `:86-104` (`check2.md:162-169`; same
fix in the companion memo's revision 3). §2's rounding caveat named only 22.6
as rounding to 23 at whole-Elo precision; 22.7 does too and was omitted — both
now named (`check2.md:179-185`; same fix in the companion memo's revision 3).
§10's "the six figures named in §§1–4" was not a derivable count — recounted
by re-reading §§1–4 directly (not merely assumed from the check) at seven:
−120 and −106.0 (§1), the "20–45" Elo range and −97.6 (§2), 0.0030 and
+0.000174 (§3), and ≈ −95 (§4) — replaced with the explicit list
(`check2.md:187-194`). The refuting issue this round (`check2.md:103-146`) is
in the companion seed-depth refusal memo only — this memo's §8 already states
the design's non-detection finding without the false "named point" claims the
seed memo had introduced, so no equivalent defect existed here to repair. Not
addressed here, out of this round's scope: `check2.md:196-205`'s finding that
this note's §1 misplaces the word "airtight" by one line-citation (the
substance — the review calling the −120 refusal airtight — is right; only the
colon's attribution point is off).

**Repair note (revision 4) — 2026-09-03.** Revision 3 of this corrected memo
(sha256 `5a8e31f695d1c07319fc9af7f18be03f9f2d77582a866d61d2a2b9bb1865cc43`) was
checked against its sources on 2026-09-02 and found **REFUTED**
(`memos-r3/check3.md`, sha256
`f0e0c0bf6d95ad7b7806a6a09cfc09c2d1d9b140a877fd386bf4d745a158ea37`) on a defect
the revision-3 repair note had itself introduced. No verdict and no measured
number changes, and the preserved text above is again untouched — `cmp` against
`scratchpad/roadmap/clubelo_control_memo.md` exits 0 on its 391 lines.

* **(the refuting issue, `check3.md:99-120`) — and the rule adopted so the
  species cannot recur.** Revision 3's note cited *this document* at revision
  **2**'s line numbers: it said "this memo's `:459-461` misplaces the word
  'airtight'", and under revision 3's own numbering `:459-461` is the middle of
  the SHA-256 sources block. The reference was inherited verbatim from
  `check2.md`, which was describing revision 2, and it had the further effect
  that this note's disclosure of its own unrepaired defect pointed the reader at
  the wrong lines of itself. **The rule adopted here, binding on every successor
  of this document: a reference to a place inside it is made by anchor — a
  §-number or the exact heading text in quotes — never by line number. Line
  numbers cite external files only, and only files pinned by digest or commit.**
  That reference is now an anchor, and **no internal `:NNN` citation remains
  anywhere in this note** — the two just above stand inside a quotation of the
  stale text, and cite nothing.
* **(`check2.md:196-205`, carried as unrepaired by `check3.md:122-126`) the
  displaced "airtight" is repaired**, not deferred a third time. §1 read "the
  review called the consequent refusal airtight:" and then quoted
  `research_review_answer.md:135`. But the word sits at
  `research_review_answer.md:129` and attaches to the quote at `:131` — the
  *draft's* sentence, which the review sources to
  `seed_depth_prereg_draft.md:293` — and not to the review's `:135`. §1 now
  attributes each to its own line, and presents the review's `:135` as the
  consequence it drew, which is what it is. The substance never changed: the
  review did call the −120 refusal airtight.
* **A quotation restored to verbatim** — this round's own finding, not the
  check's. §1 rendered §7's ladder figure as *"−106.0 Elo below the 20-club mean
  (n = 33)"*, but the preserved text's parenthesis reads "(n = 33, median
  −109.1, SD 57.2)", so the quotation was a reconstruction. The sentence is now
  quoted as §7 wrote it.
* (`check3.md:145-152`) §2's heading rendered the review's ruling as
  `"≈ −97, method-sensitive and uncertain"`, with a space after `≈`, while
  `research_review_answer.md:186` reads `“≈−97, method-sensitive and
  uncertain.”` — the heading now carries the review's own bytes, as §2's body
  quotation of `:150` already did.
* (`check3.md:128-136`) §10's scope sentence placed the disclosures and
  supersessions "in §§6–9", omitting §5, which adds one of its own (the 33 rows
  are 23 distinct clubs, so the n = 33 p-value is descriptive, not inferential)
  — corrected to §§5–9. The seven-figure enumeration beside it is unchanged.
* (`check3.md:154-158`) one 83-character line rewrapped to the note's ~76.
  Presentation only — and safe to do at all only because, after the first item,
  no reference into this file is by line.

**Disclosure — `9cc8ef8` is no longer HEAD.** Revisions 1–3 of this note were
written on 2026-09-02, when `9cc8ef8` was the tip; by 2026-09-03 the repo has
moved on to `28ea652`. Every repo reference in this note is to the **commit**
`9cc8ef8`, read with `git show 9cc8ef8:`, and the sentences that call it HEAD
are true of the date they were written. Checked for this revision: every repo
file this note cites is byte-identical at `9cc8ef8` and at `28ea652`, so
nothing cited here has drifted.

**Every external citation in this note was re-opened for this revision and its
quoted bytes re-read**, not carried from the prior checks: the four hashed
sources below, the preserved text above, `e1_bridge_prereg_v3_draft.md`,
`shots-v2/memos/check2.md`, `a4-groundwork/memos/check.md`, and — through
`git show 9cc8ef8:` — `epl/fit.py`, `epl/config_frozen.json`,
`reports/epl_prereg.md`, `reports/epl_baseline.md`,
`reports/epl_lowerdiv_prereg.md`, `reports/epl_anchoring_result.md`,
`reports/epl_freshness_result.md`, `reports/squad_z_2026-06-11.md`,
`reports/phase0_data_acquisition.md` and `SOURCES.md`. All hold; the "airtight"
attribution and the −106.0 quotation above are the only two that did not.

Nothing was re-measured for this revision: no fit, no harness, no sizing pass,
no data file, no archive, **no network request**. The only computation is
arithmetic on constants the sources already print, `shasum -a 256`, `cmp`, and
`git show` (read). Nothing in this note authorises anything — see §9.

**Sources, pinned by SHA-256** (recomputed with `shasum -a 256` on
2026-09-02): the seed-depth draft that took §7 through the house drill
(`scratchpad/roadmap/seed_depth_prereg_draft.md`,
`85e46b3023adaaae7097df4f71218e68ef75fcc45c41a7c15903ec44e4e6867e`), its
sizing output (`seed_power_out.txt`,
`207a7a6bcebf70a7bcc4e82fa0d61d3a5f9e27c0456dd35b8b39640877f935c7`) and script
(`seed_sizing.py`,
`562957c3a561436e5bd3816a061fe771090d363b51f7735aaaeba9ca12fb4425`), and the
cross-model review (`scratchpad/codex-rev/research_review_answer.md`,
`ad0473c0a9d17f69d7062418f575de985385c5914c3c10c2c36126dc79d423c7`). The
companion record is the seed-depth refusal memo of the same date (revision 4).

**UNVERIFIED — the review's date.** `research_review_answer.md` carries no
in-document date line; it is dated 2026-09-01 here from its filesystem mtime
— **2026-09-01 15:29:32 UTC**, the instant the earlier revisions printed
un-zoned as "23:29", its rendering at UTC+8 — and from the draft it answers.
Not verifiable from the
file's own bytes.

### 1. §7's "self-consistent fixed point near −120" is contaminated, and is withdrawn as a candidate

§7 sweeps the frozen ladder over **all 33 cohorts** and reads *"realized gaps
of −82.6 (at 0), −106.0 (−75), −114.2 (−100), −131.3 (−150), a self-consistent
fixed point near −120"* (§7, above). Those 33 cohorts include the six seasons
`epl/config_frozen.json:19-26` names `score_seasons_NOT_LOOKED_AT`
(2019/20–2024/25) and 2025/26 besides. The seed-depth draft's candidate audit
put it in one row of its provenance table
(`seed_depth_prereg_draft.md:275-281`) —

```
| self-consistent fixed point, all cohorts | ≈ **−120** | **yes** |
```

(`:281`), under the column header *"reads scoring-window outcomes?"* (`:275`).
The review called that ruling airtight — *"The argument is airtight:"*
(`research_review_answer.md:129`), introducing the draft's own sentence, which
the review quotes at `:131` and sources to `seed_depth_prereg_draft.md:293` —
and stated the consequence separately: *"The all-33 −120 candidate reads the
same 2019/20–2024/25 outcomes on which it would be evaluated. Under the house
law, it is inadmissible as confirmatory."* (`research_review_answer.md:135`).
The same applies to §7's *"promoted clubs finish their first EPL season −106.0
Elo below the 20-club mean (n = 33, median −109.1, SD 57.2)"*: it is the
all-cohort realized gap at −75, and it reads the same seasons. Both numbers
stay above as what they are — descriptions of the whole archive — and neither
may seed a treatment constant on the 2019/20–2024/25 corpus.

### 2. The clean pre-2019 fixed point is −97.6 — to be read as "≈−97, method-sensitive and uncertain"

Computed by the seed draft's read-only sizing pass on the **12 cohorts
promoted into 2015/16–2018/19**, ladder on seasons ≤ 2018/19 only, frozen
config; this note recomputes nothing but the two fixed points below. The
sweep is (`seed_power_out.txt:38-43`, verbatim):

```
offset=    0.0: realized gap mean=-67.2 (n=12)
offset=  -75.0: realized gap mean=-89.8 (n=12)
offset= -100.0: realized gap mean=-97.6 (n=12)
offset= -120.0: realized gap mean=-104.0 (n=12)
offset= -150.0: realized gap mean=-114.0 (n=12)
linear fit gap(o) = -67.2 + 0.312*o  ->  pre-2019 fixed point = -97.6
```

**Four points the review attached** (`research_review_answer.md:145-148`,
under its heading at `:139`), all carried: (a) the −97.6 is an **endpoint
secant** through the 0 and −150 points (`seed_sizing.py:194-200`), not a
regression over all five; (b) local interpolation between −75 and −100 gives
approximately **−96.5**; (c) there are only **12 rows across four promotion
seasons**; (d) **clustering and fixed-point amplification are omitted**. Both
fixed points were rechecked by arithmetic on the printed constants for this
note — secant −97.674, local −96.512 — and both inherit the sweep's
1-decimal printing. The defensible statement, in the review's words:
*"approximately −97, with substantial uncertainty; nearest frozen grid
candidate −100."* (`research_review_answer.md:150`).

Consequently §7's hypothesis *"−75 is 20–45 Elo too shallow"* narrows. On
uncontaminated evidence the gap is **22.6 Elo** against the printed secant
fixed point (−97.6 − (−75)), **22.7** against the unrounded secant (−97.674),
and **21.5** against the local reading (−96.512) — ≈ 22 on all three, and ≈ 23
if 22.6 or 22.7 is rounded to a whole Elo. The 45 end belonged to the
contaminated branch. It remains a hypothesis, as §7 says, and it remains
unconsumed.

### 3. §7's "worth 0.0030 RPS" is the wrong quantity: the committed contrast is +0.001309

§7 says *"`epl/fit.py` records that seed as worth 0.0030 RPS — the largest
single configuration effect measured on this data."* That sentence sits at
`epl/fit.py:90`, one line of the `ARCHITECTURE_NOTES` string tuple at
`epl/fit.py:86-104` — **not a docstring**, as
`reports/epl_lowerdiv_prereg.md:181` correctly puts it (*"`epl/fit.py:88-91`
records"*) — and it is not the tuning result. The committed same-config tuning
contrast of −75 against 0 is **+0.001309** RPS (`epl/config_frozen.json:330`,
`"delta_vs_chosen": 0.001309`; `seed_power_out.txt:18`;
`reports/epl_prereg.md:336`, *"the defect costs 0.00131"*). The 0.0030 is
`reports/epl_baseline.md:148-149`'s sensitivity, 0.2011 → 0.2041, measured on
the already-observed **scoring** window — a different quantity. This is not a
discovery of this note: the distinction is committed law at
`reports/epl_lowerdiv_prereg.md:181-185` and `:829-835` (*"The `0.0030` figure
is a different quantity and v1 cited it as this one"*), and the review asked
that it be cross-referenced rather than re-found
(`research_review_answer.md:186`). One further committed number §7 should have
carried: on the same tuning slice, −100 is **+0.000174** RPS *worse* than −75
(`epl/config_frozen.json:342`; `reports/epl_prereg.md:437`). The RPS-vertex
caveat §7 states — a level-true seed need not be RPS-optimal — is therefore
not a caveat but the measured state of the record.

### 4. Clubelo's ≈ −95 is not an independent clean confirmation

§7 converts clubelo's end-of-first-season gap, −117.6 in its units, to
≈ −95 in ours by the 1.24× dispersion ratio, and the seed-depth draft leaned
on it as *"clubelo's independent ≈ −95"*. The review's correction
(`research_review_answer.md:152`): the end-of-first-season series spans the
scoring-window cohorts, so it is not fully independent of the outcomes at
issue; the cleaner **entry-side** conversion, −126.2 / 1.24 = −101.774
(§7's own figures; arithmetic for this note), points nearer **−102**, and
carries its own scale assumption. Both conversions stay above; neither is a
confirmation of a specific constant.

### 5. §6's correlations stand — with the dependence caveat added

The headline arbiters are unchanged: within-cohort clubelo entry rating
against first-season EPL points, **r = +0.143 (n = 33, p = 0.43)**; the
positive control on **187 continuing club-seasons, r = +0.746**
(§6, above). §6's own power sentence — at n = 33 only |r| > 0.343 is
distinguishable from zero, so +0.143 is *"no measurable signal," not "proven
zero"* — is the reading this note keeps: **uninformative at this n, not
refuted**. One caveat is added. The 33 cohort rows are **23 distinct clubs**
(Norwich, Fulham and Burnley three times each; Watford, Sheffield United,
Leeds and Bournemouth twice; sixteen once — counted from §4's table), so the
n = 33 p-value is descriptive under row independence, not an inferential one
(the review makes the identical point about the same population at
`research_review_answer.md:77`). Nothing in §6 turns on that p-value.

### 6. §1–§2 stand as observed on 2026-09-01 — and are UNVERIFIED as of today

**UNVERIFIED as of 2026-09-02.** Everything in this section is §1–§2's
observation of 2026-09-01, carried by citation. This note is read-only and
made **no network request**: it neither re-checked the route nor re-fetched
the site, so none of it is re-observed today.

As observed on 2026-09-01: the by-date API returned **502** from clubelo's own
IIS origin on 25 attempts over ~20 minutes (§1 table, above); `/Fixtures`
answered `Fixtures API deactivated` from the same host. This note claims no
more than the memo did — the route was **not fetchable on 2026-09-01**, and
permanence was unverifiable then and remains unverifiable now. The restatement
finding likewise stands as observed: on 2024-08-01, a date on which every
English rating was provably static, the site as fetched on 2026-09-01 differed
from the contemporaneous capture by **+103.08** for Sunderland, mean Δ +37.7
over n = 19, field SD compressed 132.3 → 115.9 (§2(d), above).

Two consequences already stated above are repeated because they are
operational, and both are statements of what is owed, not authorisations to
act: `SOURCES.md:17` still records `http://api.clubelo.com/<YYYY-MM-DD>` as a
live point-in-time route, and that correction is owed (this note, being
read-only on the tree, does not make it and does not authorise anyone else to
make it unasked); and the three committed snapshots
`config/squads/clubelo_{20221120,20240614,20260610}.csv` must never be
refreshed from today's site — `reports/squad_z_2026-06-11.md` is built from
those captures (`:165`) and stays correct only for as long as they are the
ones on disk. `reports/phase0_data_acquisition.md:185` had already flagged
clubelo as *"Still recomputed → as-published revision risk"* on 2026-06-03;
§2(d) is the measurement of that risk.

### 7. Governance disclosure: §4 and §7 are bridge-relevant statistics published before the bridge seal

The E1-bridge v3 draft (`scratchpad/roadmap/e1_bridge_prereg_v3_draft.md:481`)
forbids computing any cohort outcome statistic before its freeze, and its
invalidation clause (`:1202`) covers a value published anywhere else before
the seal. §4's `our end` column and §7's all-cohort fixed point are such
statistics — the review names this memo at
`research_review_answer.md:31` as one of the two documents that triggered the
clause. This note does not decide what standing the bridge retains; that is
the owner's question (`research_review_answer.md:36-41`, `:123`, `:187`). It
records the fact so it is found here and not only there.

### 8. §8's recommendation for the bridge's first experiment is superseded

§8 recommends spending *"the bridge's first experiment instead on the level
question in §7, which needs no new source at all."* That question was taken
through the full drill on 2026-09-01 and **REFUSED** — on the pinned corpus
and as a prospective shadow arm alike — for the reasons the seed-depth
refusal memo records: the deep candidate is contaminated (§1 above); the
clean candidate's measured tuning contrast is +0.000174 in the wrong
direction and its hypothesised benefit sits below the −0.0010 bar; the design
cannot detect anything it is allowed to test (the best joint MDE80 is
−0.001608, and even the contaminated −0.001534 point falls short of it at
0.762 power); and the shadow arm is neither zero-cost nor startable at
2026/27 MW1 nor adoptable under the materiality law it would run under
(`research_review_answer.md:166-178`, `:185`, `:209`).

§8's other verdicts stand unchanged: clubelo is **not** a stronger prior than
−75; the fixed-bridge secondary arm stays −75-based; clubelo stays a
documented, attributed source of record for the WC squad-z anchor. §8's
August-1 capture recommendation also stands **as a recommendation to the
owner, and only that**: it is conditional on the by-date API returning (which,
per §6, it had not as of 2026-09-01), and neither §8 nor this note authorises
or performs any fetch, capture, commit or refresh — see §9.

One clarification the review adds to *"−75-based"*: the bridge's −75 is the
historical v2 comparator on its actual 187-fixture diagnostic surface, **not a
bracket**, and no absolute seed level (−100 included) is an estimate of the
bridge's cross-ladder offset `mean(y − x)`
(`research_review_answer.md:194-200`).

### 9. §7's "with no amendment" clause is superseded — nothing in this document authorises a run

§7 closes with the sentence this note must name, because it is the one
sentence above that a reader could take as a licence:

> the hypothesis *"−75 is 20–45 Elo too shallow"* is testable **entirely inside
> the existing archive, with no new source, no licence question and no
> amendment** — and on this evidence it is a better use of the bridge's first
> experiment than a clubelo arm.
> (§7, above, preserved verbatim)

**Both halves are superseded by name.**

* **"with … no amendment" is withdrawn.** It was written before the hypothesis
  went through the drill. The same-corpus test it describes is **REFUSED**
  (§8 above; the seed-depth refusal memo of this date), and the house rule it
  presumed away now binds explicitly: any test of this hypothesis — corpus,
  shadow or successor — requires its own **new preregistration**, a fresh
  candidate audit, and owner adjudication of the pre-seal exposure recorded in
  §7 of this note (`research_review_answer.md:185`, `:187`, `:188`). The
  sentence may not be read as licence to run the seed experiment, or anything
  descended from it, without one.
* **"a better use of the bridge's first experiment"** is superseded by §8 of
  this note, which records that the level question was taken through the drill
  and refused.

**The general rule, stated once for the whole document.** No sentence in the
preserved text above, and no sentence in this note, authorises a fit, a
harness run, a sizing pass, a shadow issuance, a network fetch, a data
capture, a commit, or an amendment. Where the text recommends something —
§8's August-1 dumps included — it recommends it *to the owner*, who decides.
Read-only is the standing posture of both documents.

### 10. What this note does not change

The headline MAE comparison (57.66 vs 64.27, CI [−8.55, +22.06], 15/30), the
steelman (61.12; CI [−8.71, +16.18]), the PIT audit (1,317 comparisons at
0.005; 2.97 Elo maximum settled restatement), the 33-cohort table, the spread
figures (mean range 70.3, max 182.5), the three refused 2025/26 references,
and the Provenance section. No number above is moved; the corrections are
the figures named in §§1–4 — −120 and −106.0 (§1), the "20–45" Elo range and
−97.6 (§2), 0.0030 and +0.000174 (§3), and ≈ −95 (§4), seven in total — and
the disclosures and supersessions in §§5–9.

*Corrections revision 4 written 2026-09-03 against the commit `9cc8ef8`,
read-only; revision 3 of 2026-09-02 is superseded in full by this file, and
the preserved text above is byte-identical to
`scratchpad/roadmap/clubelo_control_memo.md`
(sha256 `350c74290b6624f419bdcd6c231c7fae30f462ababf84e0fae260025b2c03fc1`).
Proposed destination when promoted: `reports/epl_clubelo_control.md` (the
`epl_<topic>_<kind>` pattern of `epl_e1_acquisition.md` and
`epl_recal_grounding.md` — a measurement memo, no `_memo` suffix), carrying
this section as its first dated note.*
