# The seed-depth refusal — 2026-09-02 (revision 4, repaired)

**VERDICT: REFUSED. Not deferred, not shadowed, not re-sized. Nothing runs.**
The promoted-offset ("seed depth") experiment drafted on 2026-09-01 as
`seed_depth_prereg_draft.md` (v1 DRAFT, schema `epl-seeddepth-1`, marked
NEEDS-REPAIR by the cross-model review of 2026-09-01) is refused as a
confirmatory experiment on the pinned corpus, and its constructive remainder —
a prospective shadow arm at `promoted_offset = −100` — is refused with it.
This record replaces the draft's own ruling, which was right in its verdict
and wrong in three of the numbers and one of the proposals published beside
it. Written at HEAD `9cc8ef8` (child of `428c4cc`, the REFUSED shots result;
lineage `428c4cc` ← `0f9ff9b` H′′ ← `ca169ef` Amendment 3), read-only: no fit,
no harness, no archive opened, no scoring-corpus outcome read. The draft and
every artifact behind it remain in the session scratchpad; nothing named
below is committed law until the owner promotes it.

## Repair note (revision 2)

Revision 1 of this memo (sha256
`68fa6f5979951b91cc8a3423454f408995c642a1614e23db400524c1570348fc`) was
checked against its sources on 2026-09-02 and **REFUTED**
(`a4-groundwork/memos/check.md`, sha256
`b50694ed3ca121921ec00d1ee8eef03a2b99b36cbd5f91d666e429c698fd8f98`). This
revision repairs every issue that check raised. **No verdict, ruling or
measured number changes.** What changed:

1. the sizing script's abbreviated digest was transcribed `…ba425` for
   `…b4425`; all five digests are now printed in full and were recomputed
   with `shasum -a 256` for this revision;
2. ground 3's MDE80 sentence contradicted the two numbers beside it
   (−0.001534 is *short of* the −0.001608 MDE80, not "inside" it) — rewritten;
3. "the gap is ≈ 22" was a loose rounding of 22.6 — now stated with both
   readings and their arithmetic;
4. *"zero-marginal-cost"* was cited to §6.5; it occurs once in the draft, in
   the §0 headline at `seed_depth_prereg_draft.md:43` — relocated;
5. the §5 provenance-table "quote" was a reconstruction of a row plus its
   column header — now presented as the row and the header they are;
6. *"brackets"* was attributed through the seed draft's §11; it is the bridge
   draft's word only — attribution split;
7. `reports/epl_lowerdiv_prereg.md:829-834` → `:829-835`,
   `reports/epl_baseline.md:148-150` → `:148-149`, and `epl/fit.py:90` is a
   line of the `ARCHITECTURE_NOTES` string tuple, not a docstring;
8. the shadow-arm reopening condition is now tied explicitly to
   **owner-only, separately funded**, and the closing section states in terms
   that no sentence here authorises anything.

Nothing was re-measured for this revision: no fit, no harness, no data file,
no network. The only computation is arithmetic on constants the sources
already print.

## Repair note (revision 3)

Revision 2 of this memo (sha256
`0d408b579d5aa4bb26761cf3598d7dbeacec6e7b2e062dcf96b8df486c7d3bd1`) was
checked against its sources on 2026-09-02 and found **REFUTED** by one issue,
plus six residual findings, four of them applicable here — the other two
(`check2.md:187-205`) concern only the clubelo control memo
(`shots-v2/memos/check2.md`, sha256
`e55e3469dc691b2c272123bfeb56cbdbee0326490be2659ef8ea247aa3e34b67`). **No
verdict, ruling or measured number changes.** What changed:

1. **(the refuting issue, `check2.md:103-146`).** Ground 3 over-quantified
   two sentences onto the technical NAMED list (`seed_sizing.py:263-266`,
   bound in ground 3 of §"Why it is refused — four grounds, each sufficient"
   below), which also contains `2x_bar` = −0.0020 and the historic
   predecessor contrast = −0.00412976353895183 (`seed_sizing.py:149`,
   `:152`). "The deepest named point … is −0.001534" was false — the
   predecessor is deeper; "the only named point that does clear the best
   MDE80 is −0.00200" was false and contradicted by the very line it cited,
   `seed_power_out.txt:54` (`-0.00413->1.000`), which also clears the
   −0.001608 MDE80. Both sentences are rescoped to the candidate-effect
   points of §5's audit, and the predecessor's power-1.000 clearance is now
   named rather than omitted;
2. (`check2.md:148-160`) the "≈ −97, method-sensitive and uncertain; nearest
   frozen grid candidate −100" quotation at the clean-fixed-point row stitched
   `research_review_answer.md:186` to `:150` and presented the join as one
   verbatim line — split into two quotes, each with its own citation;
3. (`check2.md:162-169`) the `ARCHITECTURE_NOTES` string tuple's extent was
   given as `epl/fit.py:86-92` (the declaration plus its first two entries);
   verified against HEAD `9cc8ef8` (`git show 9cc8ef8:epl/fit.py`) that the
   tuple opens at `:86` and closes at `:104` — corrected to `:86-104`. Also
   corrected in the clubelo memo's dated corrections (revision 3);
4. (`check2.md:171-177`) the clean-power-range citation `(:30)` covered only
   half the quoted sentence — `seed_depth_prereg_draft.md:30` ends at
   "0.09–0.19"; "in every scenario and regime" is `:31` — corrected to
   `(:30-31)`;
5. (`check2.md:179-185`) the hypothesis-range row's rounding caveat named
   only 22.6 as rounding to 23 at whole-Elo precision; 22.7 does too and was
   omitted — both now named. Also corrected in the clubelo memo's dated
   corrections (revision 3).

Not addressed here, out of this round's scope: `check2.md:187-194`'s finding
on the clubelo memo's "six figures" count (that memo only) and
`check2.md:196-205`'s finding on a displaced "airtight" attribution in the
clubelo memo (also that memo only; this memo already attributes it correctly
in ground 1 of §"Why it is refused — four grounds, each sufficient", per
`check2.md:204-205`). Nothing was re-measured for this revision either: no
fit, no harness, no data file, no network. The only computation is arithmetic
on constants the sources already print, and `shasum -a 256` on the touched
files.

## Repair note (revision 4) — 2026-09-03

Revision 3 of this memo (sha256
`f42b747463dcc987a9e5725360bb17e58621d86b8ee789db0fc4966ca54cc640`) was
checked against its sources on 2026-09-02 and found **REFUTED**
(`memos-r3/check3.md`, sha256
`f0e0c0bf6d95ad7b7806a6a09cfc09c2d1d9b140a877fd386bf4d745a158ea37`) on a
defect the revision-3 repair note had itself introduced. **No verdict, ruling
or measured number changes.** What changed:

1. **(the refuting issue, `check3.md:99-120`) — and the rule adopted so the
   species cannot recur.** Revision 3's repair note cited *this document* at
   revision **2**'s line numbers, twice: the NAMED list was said to be "bound
   at `:178-179` below" (under revision 3's numbering that is a block quote's
   closing citation line) and the "airtight" handling was placed "at
   `:124-129`" (under revision 3's numbering, the §"What was proposed"
   section). Both were inherited verbatim from `check2.md`, which was
   describing revision 2, and both went stale the moment revision 3 inserted
   its own note — the third round running in which a repair note carried a
   defect of the kind it was repairing. **The rule adopted here, binding on
   every successor of this memo: a reference to a place inside this document
   is made by anchor — a §-number, a named ground, or the exact heading text
   in quotes — never by line number. Line numbers cite external files only,
   and only files pinned by digest or commit.** Both references are now
   anchors, and **no internal `:NNN` citation remains anywhere in this memo**
   — the two just above stand inside quotation marks, as the stale text being
   described, and cite nothing;
2. (`check3.md:138-143`) the two `check2.md` ranges for its §§4.6–4.7 began
   one line early — `check2.md:186` is blank and §4.6's heading is `:187` —
   corrected to `:187-205` and `:187-194`;
3. (`check3.md:145-152`) §"The review, honoured" rendered the review's ruling
   as `"≈ −97, method-sensitive and uncertain"` with a space after `≈`, in two
   places, while `research_review_answer.md:186` reads `“≈−97,
   method-sensitive and uncertain.”` — both now carry the review's own bytes,
   as the corrections table already did;
4. **a quotation narrowed on re-verification** — this round's own finding, not
   the check's. The word *"brackets"* does indeed appear nowhere in the seed
   draft, but the draft uses the cognate verb once, of a different object:
   *"measured within-family contrasts bracket it"*
   (`seed_depth_prereg_draft.md:318`, of the scenario SDs). §"What −100 is,
   and what it is not — the bridge" now says so, instead of leaving a reader
   to find it and doubt the sentence;
5. (`check3.md:154-158`) one 105-character line rewrapped to the file's ~76.
   Presentation only — and safe to do at all only because, after item 1, no
   reference into this file is by line.

**Disclosure — `9cc8ef8` is no longer HEAD.** Revisions 1–3 were written on
2026-09-02, when `9cc8ef8` was the tip; by 2026-09-03 the repo has moved on to
`28ea652` ("epl(shots): the REFUSED result's receipts, committed so a clean
clone can check it"). Every repo reference in this memo is to the **commit**
`9cc8ef8`, read with `git show 9cc8ef8:`, and the sentences that call it HEAD
are true of the date they were written. Checked for this revision: all six
repo files this memo cites by line — `epl/fit.py`, `epl/config_frozen.json`,
`reports/epl_prereg.md`, `reports/epl_baseline.md`,
`reports/epl_lowerdiv_prereg.md`, `reports/epl_market_edge_roadmap.md` — are
byte-identical at `9cc8ef8` and at `28ea652`, and `epl/seeddepth.py` is absent
from both, so nothing cited here has drifted.

**Every external citation in this memo was re-opened for this revision and its
quoted bytes re-read**, not carried from the prior checks: the five hashed
sources above, `e1_bridge_prereg_v3_draft.md`, `shots-v2/memos/check2.md`,
`a4-groundwork/memos/check.md`, and — through `git show 9cc8ef8:` —
`epl/fit.py`, `epl/config_frozen.json`, `reports/epl_prereg.md`,
`reports/epl_baseline.md`, `reports/epl_lowerdiv_prereg.md`,
`reports/epl_market_edge_roadmap.md`, and the commit lineage
`9cc8ef8` ← `428c4cc` ← `0f9ff9b` ← `ca169ef` ← `06882d5`. All hold as cited;
items 2, 3 and 4 above are the only three that needed correcting.

`check3.md`'s second refuting item (`check3.md:122-126`) — that `check2.md`
§4.7's displaced "airtight" was still unrepaired — is **repaired this round in
the clubelo control memo** (its revision 4), so nothing raised by any of the
three checks is left open in either document.

Nothing was re-measured for this revision: no fit, no harness, no sizing pass,
no data file, no network. The only computation is arithmetic on constants the
sources already print, `shasum -a 256`, `cmp`, and `git show` (read).

## Sources, pinned by SHA-256

Recomputed with `shasum -a 256` on 2026-09-02 for this revision:

| file | sha256 |
|---|---|
| `scratchpad/roadmap/seed_depth_prereg_draft.md` (the draft) | `85e46b3023adaaae7097df4f71218e68ef75fcc45c41a7c15903ec44e4e6867e` |
| `scratchpad/roadmap/seed_power_out.txt` (its sizing output) | `207a7a6bcebf70a7bcc4e82fa0d61d3a5f9e27c0456dd35b8b39640877f935c7` |
| `scratchpad/roadmap/seed_sizing.py` (its sizing script) | `562957c3a561436e5bd3816a061fe771090d363b51f7735aaaeba9ca12fb4425` |
| `scratchpad/roadmap/clubelo_control_memo.md` (the motivating memo) | `350c74290b6624f419bdcd6c231c7fae30f462ababf84e0fae260025b2c03fc1` |
| `scratchpad/codex-rev/research_review_answer.md` (the review) | `ad0473c0a9d17f69d7062418f575de985385c5914c3c10c2c36126dc79d423c7` |

Line references below are to those files as hashed; repo references are to
HEAD `9cc8ef8`.

**UNVERIFIED — the review's date.** `research_review_answer.md` carries no
in-document date line. It is dated 2026-09-01 here from its filesystem mtime
— **2026-09-01 15:29:32 UTC**, the instant the earlier revisions printed
un-zoned as "23:29", its rendering at UTC+8 — and from the draft it answers
(drafted 2026-09-01 at `71439c5`, `seed_depth_prereg_draft.md:3`, `:598`).
The date is not verifiable from the file's own bytes.

## What was proposed

The clubelo control memo's §7 stated a hypothesis — *"−75 is 20–45 Elo too
shallow"* (`clubelo_control_memo.md:344`) — resting on a sweep of the frozen
ladder that found *"a self-consistent fixed point near −120"*
(`clubelo_control_memo.md:338`). The draft took that hypothesis through the
house drill (`seed_depth_prereg_draft.md:12-17`):

* **Arms** (`:135-142`): control = the published `dc_native` predictions of
  the pinned corpus, byte-identical; treated = `dc_native` refit at every one
  of the 212 block openings with exactly one change, the Elo layer's
  season-boundary seed using `promoted_offset = CANDIDATE` in place of −75,
  injected as `EloConfig(**{**chosen, "promoted_offset": CANDIDATE})`
  (`:180-187`) — no edit to `epl/config_frozen.json`, no edit to `src/`.
* **Estimand** (`:207-209`): mean matched-fixture RPS difference over the
  **648** promoted-class fixtures of E1 v3 §0.4 (digest `a41efa73…`, three
  routes agreeing at 648/648, `:60-61`); co-primary no-harm over all 2,280.
  Gates (i)/(iii)/(iv)/(v) of the refounded family (`:211-224`).
* **The candidate** (§5, `:268-303`): the memo's −120 was audited and refused
  (`:293-297`); the *"clean candidate is −100: the nearest point of the
  committed tuning grid … to both uncontaminated level estimates (−97.6,
  ≈ −95)"* (`:298-301`).
* **The draft's own ruling** (§6.4, `:397-415`): REFUSED as an adoption
  experiment on the pinned corpus — three grounds, each stated as sufficient.
* **The constructive remainder** (§6.5, `:433-444`; open question 2,
  `:585-587`): a prospective shadow arm at −100, A8 pattern. The draft's §0
  headline calls it *"a zero-marginal-cost **prospective shadow arm**"*
  (`seed_depth_prereg_draft.md:43` — the phrase "zero-marginal-cost" occurs
  exactly once in the draft, there, and **not** in §6.5). §6.5 itself states
  the substance: *"issued beside the incumbent from 2026/27 MW1 — costs ~57 s
  per issuance cycle, touches no frozen surface"* (`:437-438`).

The review's verdict on the whole (`research_review_answer.md:3`):

> Seed-depth is **NEEDS-REPAIR**, while its central ruling—**REFUSE the
> retrospective corpus experiment**—is correct. Do not build the −100 shadow
> arm now.

## Why it is refused — four grounds, each sufficient

**1. The motivating constant was read off the evaluation seasons.** The −120
fixed point is the frozen ladder run over all 33 promotion cohorts, which
include the six seasons `epl/config_frozen.json:19-26` names
`score_seasons_NOT_LOOKED_AT` (2019/20–2024/25) and 2025/26 besides
(`clubelo_control_memo.md:330-338`). The draft's own candidate audit records
it in the provenance table at `seed_depth_prereg_draft.md:275-281` — the row

```
| self-consistent fixed point, all cohorts | ≈ **−120** | **yes** |
```

(`:281`), under the column header *"reads scoring-window outcomes?"* (`:275`)
— and rules on it in words the review called airtight
(`research_review_answer.md:129`):

> setting the *treatment constant itself* to the value the scoring data
> suggests is tuning on the test set wearing a memo's authority.
> (`seed_depth_prereg_draft.md:295-296`)

The review closes the door the draft left ajar: replacing −120 with −100 does
not make a same-corpus run confirmatory, because *"the candidate family was
revived after seeing the scoring-window level anomaly. A clean numeric grid
point does not erase outcome-informed hypothesis selection. Any same-corpus
result would be exploratory."* (`research_review_answer.md:137`).

**2. The committed measurement puts the clean candidate on the wrong side of
zero, and the draft's "clean benefits" are not measurements.** On the tuning
window the offset was chosen on, the same-config slice records −100 as
**+0.000174 RPS worse** than −75 (`epl/config_frozen.json:342`
`"delta_vs_chosen": 0.000174`; `seed_power_out.txt:21`; the original table at
`reports/epl_prereg.md:437`, `+0.00017`). The draft's clean effect points
−0.00028 / −0.00038 (`seed_depth_prereg_draft.md:354`) are produced by
relocating the tuning curve's vertex from its measured −71.3 to the level
estimates −95 / −97.6 — an assumption that the RPS-optimal seed coincides with
the level fixed point, which the draft's own counter-hypothesis 1 (`:108-113`)
argues against. The review's words: *"a sensitivity scenario, not a measured
treatment effect"* (`research_review_answer.md:158`). And even granted, every
clean point sits below the −0.0010 materiality bar (`:354`;
`research_review_answer.md:164`).

**UNVERIFIED, and disclosed as such:** the draft's transmission caveat — that
these are Elo-layer responses and *"the DC response is damped by an unmeasured
factor ≤ 1"* (`seed_depth_prereg_draft.md:349-350`) — is unproved in the
direction it assumes. The review: *"plausible but unproved; the nonlinear
Bayesian fit could damp or amplify the perturbation"*
(`research_review_answer.md:160`). Nothing in this memo rests on the bound
holding; it is recorded so a successor does not inherit it as settled.

**3. The design cannot detect anything it is allowed to test.** At the
quietest measured scenario and the most favourable regime, the joint
{(i),(iii)} MDE80 is **−0.001608** (`seed_power_out.txt:53`). **No effect any
evidence route reaches clears it — the contaminated branch included.** The
deepest effect any vertex estimate in §5's audit reaches, the −120 candidate
at the −120 vertex, is **−0.001534**: smaller in magnitude than that MDE80 by
7.4 × 10⁻⁵, and its joint power is **0.762** — below 0.80, which is what
falling short of an MDE80 means — in exactly one scenario-regime cell,
0.30–0.52 across the plausible middle and 0.12–0.16 under the season shock
the mechanism itself predicts (`seed_depth_prereg_draft.md:368-376`,
`:412-415`; the draft rounds the 0.296 cell to 0.30). The nearest named
point that *does* clear the best MDE80 is −0.00200, at joint power 0.927
(`seed_power_out.txt:54`); named also contains the historic predecessor
contrast, −0.004130 (`seed_sizing.py:152`), which clears it too, at power
1.000 — neither is reached by any vertex estimate in §5's audit. The draft
states the same fact from the other side: *"The only effects inside any
scenario's MDE80 (−0.0016 at best) require the vertex at −118 or deeper with
full transmission"* (`seed_depth_prereg_draft.md:406-408`). The draft's
*"0.09–0.19"* for the clean effects (`:30`, `:403`) is not a demonstrated
range either: the sizing evaluates −0.000579 and prints upper bounds; the
−0.00028 and −0.00038 cells
were never evaluated (`seed_power_out.txt:52-61`, the NAMED points, whose
membership is fixed by `seed_sizing.py:263-266`; `research_review_answer.md:162`).
None of this rescues anything — it is the admissibility rule
(`seed_depth_prereg_draft.md:309-313`) firing as designed.

**4. The shadow arm is not zero-cost, cannot start where the draft says, and
could never adopt under the law it would run under.** Per
`research_review_answer.md:166-178`: it requires a fresh `dc_native` refit
each cycle (the draft's own measured rate, 57.24 s/fit,
`seed_depth_prereg_draft.md:459` — carried by citation, **UNVERIFIED by this
memo**, which measured nothing), an amendment, an immutable candidate and
purpose, a ledger, verification, storage and operational maintenance, and a
new decision law if it is merely sign-seeking; A8 is *"governance precedent,
not computational equivalence"* — a match-vector transformation, not a new
scoreline fit. The proposed 2026/27 MW1 start is already impossible without
backfill: MW1 and MW2 outcomes are in the committed scorecard (commit
`06882d5`, "epl(cycle): MW2 ingested — both sources agreeing, ten results, the
kickoff book, three arms"), so any lawful shadow would begin at the first
future unissued cutoff after its amendment. And decisively — *"if the clean
expected effect is below the materiality bar, accumulating more seasons does
not make it adoptable under that law. Do not pay a years-long governance cost
for a result the gate is designed to reject."*
(`research_review_answer.md:178`). Ruling on open question 2: **"No now."**
(`:185`); in the run order: *"do not start the −100 shadow"* (`:209`).

## The corrections, carried into the record

The draft's verdict survives; these numbers and labels do not.

| figure | as drafted / as motivated | corrected | evidence |
|---|---|---|---|
| The candidate −120 | *"self-consistent fixed point near −120"* (`clubelo_control_memo.md:338`; `seed_depth_prereg_draft.md:19-20`) | **Contaminated.** Reads 2019/20–2024/25 and 2025/26 outcomes. Not a candidate anywhere, ever, on this corpus. | `seed_depth_prereg_draft.md:275-281`; `research_review_answer.md:135` |
| The clean fixed point | *"the fixed point is −97.6 — within 3 Elo of clubelo's independent ≈ −95"* (`:23-24`) | **"≈−97, method-sensitive and uncertain."** (`research_review_answer.md:186`) More fully: **"approximately −97, with substantial uncertainty; nearest frozen grid candidate −100."** (`:150`) The −97.6 is an endpoint secant through the 0 and −150 sweep points (`seed_sizing.py:194-200`; `seed_power_out.txt:43`, quoted byte-for-byte, two spaces on each side of `->`: `linear fit gap(o) = -67.2 + 0.312*o  ->  pre-2019 fixed point = -97.6`); local interpolation between −75 and −100 gives ≈ −96.5; n = 12 cohorts across four promotion seasons; clustering and fixed-point amplification omitted. Rechecked by arithmetic on the five printed constants for this memo: secant −97.674, local −96.512 — both inheriting the sweep's 1-decimal printing. | `research_review_answer.md:139-150`, `:186`; `seed_power_out.txt:38-43` |
| Clubelo's ≈ −95 as independent confirmation | *"clubelo's independent ≈ −95"* (`:24`) | **Not fully independent.** Its end-of-first-season series spans scoring-window cohorts; the entry-side conversion, −126.2 / 1.24 = −101.774, points nearer **−102**, with its own scale assumption. | `research_review_answer.md:152`; `clubelo_control_memo.md:332-334` |
| The seed's worth | *"worth 0.0030 RPS"* (`clubelo_control_memo.md:341`, sourced there to `epl/fit.py`) | **+0.001309** — the committed same-config contrast of −75 against 0 on the tuning window (`epl/config_frozen.json:330` `"delta_vs_chosen": 0.001309`; `seed_power_out.txt:18`; `reports/epl_prereg.md:336` *"the defect costs 0.00131"*). The 0.0030 is `reports/epl_baseline.md:148-149`'s sensitivity on the **scoring** window (0.2011 → 0.2041), a different quantity. The 0.0030 sentence sits at `epl/fit.py:90`, one line of the `ARCHITECTURE_NOTES` string tuple at `epl/fit.py:86-104` — **not a docstring**; `reports/epl_lowerdiv_prereg.md:181` describes it correctly (*"`epl/fit.py:88-91` records"*). The distinction is already committed law at `reports/epl_lowerdiv_prereg.md:181-185` and `:829-835`; it is cross-referenced here, not discovered. | `research_review_answer.md:186` |
| The −100 shadow arm | *"zero-marginal-cost"* (`seed_depth_prereg_draft.md:43`, the §0 headline) … *"issued beside the incumbent from 2026/27 MW1"* (`:437-438`, §6.5) | **Refused** — ground 4 above. | `research_review_answer.md:166-178`, `:185`, `:209` |
| The clean power range | *"0.09–0.19 in every scenario and regime"* (`:30-31`) | Upper bounds at −0.000579; the clean cells were not evaluated. No lower bound of 0.09 is demonstrated. | `research_review_answer.md:162`; `seed_power_out.txt:52-61` |
| The hypothesis's range | *"−75 is 20–45 Elo too shallow"* (`clubelo_control_memo.md:344`) | On uncontaminated evidence the gap is **22.6 Elo** against the printed secant fixed point (−97.6 − (−75)), **22.7** against the unrounded secant (−97.674), and **21.5** against the local-interpolation reading (−96.512) — ≈ 22 on all three, ≈ 23 if 22.6 or 22.7 is rounded to a whole Elo. The 45 end is the contaminated branch. Still a hypothesis, still unconsumed. | arithmetic on the corrected fixed point (`seed_power_out.txt:38-43`) |

## What −100 is, and what it is not — the bridge

The review's §3 finding (`research_review_answer.md:194-198`), recorded so it
cannot be lost between two documents:

> The seed result does **not** justify replacing the bridge’s −75 fixed comparator with −100:
>
> - −100 is an **absolute promoted-E0 seed level**.
> - The bridge estimates a **cross-ladder offset**, `mean(y − x)`.
> - Because `x` is not zero, −100 is not an estimate of that bridge constant.
>
> (`research_review_answer.md:194-198`, verbatim)

The seed draft's §11 (`seed_depth_prereg_draft.md:530-536`) carries the bridge
draft's disclosure that residual seed error *"pulls delta_hat toward −75"*
(quoted at `seed_depth_prereg_draft.md:534`; the bridge draft's own wording is
*"its sign pulls `delta_hat` **toward** the incumbent −75"*,
`e1_bridge_prereg_v3_draft.md:498-500`). The word *"brackets"* appears nowhere
in the seed draft — its one cognate there, *"measured within-family contrasts
bracket it"* (`seed_depth_prereg_draft.md:318`), is about the scenario SDs and
not the bridge's −75 arm — so the bracketing claim at issue is the bridge
draft's alone: *"the fixed-bridge arm brackets it from the −75 side"*
(`e1_bridge_prereg_v3_draft.md:502`) and *"the fixed-bridge arm brackets it"*
(`:1249-1250`). The review shows the pull is
toward **−75 − x**, with `x` itself seeded on both sides, so "brackets" is
unsupported (`research_review_answer.md:47-60`). The ruling carried here:
**keep −75 solely as the historical v2 comparator on its actual 187-fixture
diagnostic surface; stop calling it a bracket; −100 may appear only in a
non-deciding contamination sensitivity, never as the fixed-bridge secondary
arm** (`research_review_answer.md:200`). Nothing in this memo changes a
bridge constant.

One consequence this memo does not decide but must disclose: the draft's §5
table (`seed_depth_prereg_draft.md:275-281`) and the clubelo memo's §4 and §7
published cohort outcome statistics — end-of-season Elo by cohort, an
all-cohort fixed point — before any bridge seal, which the bridge draft's own
rule (`e1_bridge_prereg_v3_draft.md:481`, `:1202`) names as invalidating
(`research_review_answer.md:29-34`, `:187`). What standing the bridge retains
is the owner's question, listed by the review as the decisive one it was not
asked (`:123`).

## What stands

* `promoted_offset = −75.0` — `epl/config_frozen.json` `chosen` (`:32-36`),
  digest `9f2e086d39ae4b855ba21604367109e8e9ce00f96010c5ec65c380d317986abc` —
  unchanged everywhere, Hull's forecast included
  (`seed_depth_prereg_draft.md:550-551`).
* The level finding stands as a **hypothesis-labelled level finding**,
  unconsumed (`:554-555`), with its numbers repaired per the table above and
  per the dated corrections appended to the clubelo control memo.
* No corpus harness (`epl/seeddepth.py` is not written and is not to be
  written under this record), no shadow ledger, no
  `reports/evidence/seeddepth.json`.
* The queue is untouched: the shots challenger (roadmap row 5) sits REFUSED at
  `428c4cc` in its own lane; then Order 6, the dynamic state-space
  challenger; then Order 7, the lower-division promotion bridge
  (`reports/epl_market_edge_roadmap.md:38-40`;
  `research_review_answer.md:207`).

## What would have to be true to reopen it

All of the following, none of which holds today. **This section states
conditions, not permissions: it authorises nothing, and satisfying every item
would still require the owner to act.**

1. **A fresh prospective outcome surface** — fixtures whose outcomes postdate
   every statistic that generated the hypothesis (2026/27 onward; even
   2025/26 is inside the memo's window, `seed_depth_prereg_draft.md:440-441`)
   — under a **new preregistration** with a fresh candidate audit in §5's
   discipline. Republishing old outcomes under a new config does not restore
   blindness (`research_review_answer.md:188`; `seed_depth_prereg_draft.md:592-594`).
2. **The bridge has run and been read.** Its published per-season
   `delta_hat`, cohort table and SEs are the sharpest uncontaminated level
   estimates the program will have, and its `dc_e1_fixed`-vs-`dc_e1` contrast
   is the first measured RPS response to a depth-like change
   (`seed_depth_prereg_draft.md:445-449`, `:537-542`;
   `research_review_answer.md:209`: *"Revisit a prospective shadow only if
   the bridge result materially changes its decision value."*).
3. **An effect mechanism that clears −0.0010**, not more seasons. Under the
   committed curvature, no candidate reachable from uncontaminated evidence
   is worth more than −0.0003…−0.0007 at class level, and the one committed
   measurement of −100 is +0.000174 worse. A reopening must show why the
   evaluation-window vertex should sit deeper than the tuning-window vertex
   (−71.3) by more than the tuning window's own shrinkage explains.
4. **A lawful power basis.** Either a measured treatment-contrast SD below
   N50 (0.014609 on the 648) or measured evidence of super-quadratic
   response — the only two bases the draft could name
   (`seed_depth_prereg_draft.md:582-584`).
5. **For any shadow arm specifically: an owner decision, separately funded.**
   The review's ruling is *"No now. Owner-only if separately funded later with
   a precise prospective purpose and no backfill."*
   (`research_review_answer.md:185`). On top of that: its own amendment, an
   immutable candidate and purpose, its own ledger and verify, a decision law
   that is not merely sign-seeking, and a start at the first future unissued
   cutoff after the amendment — no backfill
   (`research_review_answer.md:168-176`). This paragraph describes the lawful
   *shape* of a thing that is refused today; it is not a licence to build one,
   and no reader may treat it as one.
6. **Owner adjudication** of the pre-seal exposure and of the bridge's
   standing, since a reopened seed question re-pins the bridge's E0 ladder
   constant and cohort responses (`seed_depth_prereg_draft.md:530-536`;
   `research_review_answer.md:187`, `:205`).

## Run nothing

No fit. No harness. No `--power` pass. No shadow issuance. No read of
`data/epl/fit/walkforward_predictions.parquet` or `data/epl/matches.parquet`
in this question's name. **No sentence in this memo — including §"What would
have to be true to reopen it" — authorises a run, a capture, a commit, an
issuance or an amendment.** The refusal is the deliverable; the draft's own
closing sentence already said so (`seed_depth_prereg_draft.md:598-604`), and
the review's first item in the order it would run is *"Promote a repaired
seed-depth refusal memo. Run nothing from it."*
(`research_review_answer.md:204`). The only computation behind this memo is
the arithmetic in the corrections table and in ground 3, on constants copied
from `seed_power_out.txt:29`, `:38-43` and `:53-54` and from
`clubelo_control_memo.md:332-334` — no data file was opened.

## The review, honoured

The cross-model review's rulings on the draft's five open questions
(`research_review_answer.md:180-188`) are adopted in full: (1) refusal
ratified, after repairing the effect/power/precision language — done above;
(2) no −100 shadow now; (3) record "≈−97, method-sensitive and uncertain"
and cross-reference the committed +0.001309 rather than imply discovery —
done above and in the clubelo memo's dated corrections; (4) the bridge does
**not** proceed unaffected — owner adjudication required; (5) re-sizing only
on a genuinely fresh prospective surface under a new preregistration. Where
this memo keeps the computed −97.6 beside the review's "≈−97", it does so
with the derivation and its caveats printed, not as a claim of precision.

*Revision 4 written 2026-09-03 against the commit `9cc8ef8`, read-only, from
the hashed sources above; revision 3 of 2026-09-02 is superseded in full by
this file.
Proposed destination when promoted: `reports/epl_seeddepth_refusal.md`
(the `epl_<topic>_<kind>` convention; topic token from the draft's own schema
`epl-seeddepth-1` and its proposed write set `epl/seeddepth.py`).*
