# WingRock coaching — plan for the next phase

Status 2026-09-16 (evening): first cut built and pushed — see §0. Research and decisions follow.

## 0. What exists now

| Piece | Where | State |
|---|---|---|
| Per-sample features (nose elevation/azimuth from the quaternion, bank, flight path) | `web/coach/features.js` | done |
| Element detector (level, 45°/vertical lines, looping, roll, turn, spin, hammerhead pivot) → figures | `web/coach/detector.js` | done; tuned on data16 — all three runs come out as the Primary Known: 45° line, 1½ spin, half Cuban, loop, 180° turn, slow roll. Spin turns = whole turns from rotation about the vertical + the exit-heading residual |
| Primary templates, IAC-2025 grading, ranked critique with rule refs and corrections | `web/coach/judge.js` | done for the 6 Primary figures; data16 is three flights of the Primary Known, so every figure incl. the 1½-turn spin is exercised |
| Correct-figure ghost + ribs | `web/coach/ghost.js` | done for all 6; shown live 20 s and in replay |
| Replay mode (scrub, speeds, markers, Last figure / Live), 20-min history ring | `web/app.js`, `web/records.js` | done |
| Flight files on the phone (`Documents/Flights`, Files app) and Flights list | `ios/WingRock/FlightRecorder.swift`, `WebView.swift` | done |
| Labelling list (type, grade, notes per detected figure) → `docs/private/labels_<flight>.json` via the bridge | Figures list in the replay bar | done; awaiting Sean's grades on data16 |
| Coach card + spoken critique (AVSpeechSynthesizer / Web Speech), voice and speak settings | `WebView.swift`, `app.js` | done |
| Coach figure setting: any / one armed figure / Primary Known sequence with K-weighted total | Box → Settings | done |
| In-figure live cues (C5) | — | not started |
| Deviation tint on the flown trail, tap-a-rib numbers | — | not started |

Bridge dev routes: `/flights/` lists `sessions/*.bin`, `/flights/<name>` serves one, `POST /dev/labels/<name>`
stores labels. Browser: `http://localhost:8645/?flight=data16_udp2000.bin` loads the flight into replay; `sessions/data16_primary1.bin` is the first sequence alone (87 s) for the fake Hub and quick tests.

## 1. What we are building

Today WingRock shows the flight. The next phase makes it *say something useful about it*: audio cues that tell the
pilot what the aircraft did on the figure just flown and how to correct it, grounded in how the figure would be
graded from the ground — because the grade is the thing that matters.

End state (not the first milestone): enter a routine as an Aresti/OLAN string, the app knows every figure, and it
coaches the whole sequence figure by figure. The links between figures aren't graded and vary flight to flight, so
the app must find figures inside free flying rather than expect a fixed script.

First milestone: the pilot picks **one figure from a library** (loop, half Cuban, Immelmann, split-S, hammerhead,
spin of n half-turns, slow roll, point rolls, …), flies it, and gets a critique of *that* figure — the same
downgrades a judge would take, plus the correction. Sequence mode comes after, built from the same pieces.

## 2. How figures are judged (what the coach must measure)

Authoritative source: FAI Sporting Code Section 6 Part 1, **Appendix B "Criteria for judging aerobatic figures"**
(CIVA, version 2023-2) — the IAC rulebook's judging chapter follows the same criteria with minor local
differences (to confirm, see Q2). Everything below is from Appendix B and Rule 4.4 unless marked otherwise.

### 2.1 The grading model

- Start at **10.0**, downgrade as faults appear (B.4.1.2). Below 0.5 → **0.0** (4.4.1.11).
- **Geometry: 1 point per 5° of deviation** (0.5 per 2.5°) — flight path, direction, bank, attitude (4.4.1.4).
  Applies to entry/exit lines (wings level, horizontal, aligned with the box axis), heading during loops, wing-low on
  verticals, steep/shallow 45s, roll under/over-rotation, spin exit heading, etc.
- **Over-rotate then correct back** still costs 1 pt/5° of the overshoot (4.4.1.5); same for pitching past a line and
  bringing the nose back.
- **Missing horizontal line** at the start or end of a figure: 1 pt per missing line, on *both* the preceding and the
  following figure (4.4.1.1, B.8.1.2).
- **Line lengths** when two lines must match (before/after a roll; all four in a square loop): the first line sets
  the standard; visible difference 1 pt, 2:1 → 2 pts, worse → 3 pts; **no line before OR after a roll → 4 pts**; no
  line on either side → 2 pts (B.8.1.5). Judge length, *not elapsed time* (B.8.1.4).
- **Unwanted line between a roll and a looping segment**: 1 / 2 / 3 / 4 pts as the line grows to ≥ the loop radius
  (B.9.8.2); roll starting before the loop finishes or vice versa: 1 pt per 5° of overlap.
- **Hard Zero (HZ)** = figure not as drawn, or any single geometry deviation reaching **90°**, wrong direction on the
  main axis, wrong roll count/type, flick without stall, hesitation not visible, spin never stalled (4.4.2, B.9.x).
- **Perception zero** (numerical 0.0): downgrades sum to below 0.5, or autorotation stops with >45° of a flick
  remaining (B.9.27.5).
- **Unjudgeable element** (too far/too high): 2 pts per element (B.4.1.3). Positioning is a separate mark.

### 2.2 Attitude vs flight path — the rule the software must get right

**Direction reference (Sean's mental model, 2026-09-16, reconciled with the rules).** Every figure is set out along
the box's main axis: the pilot flies line figures *parallel to the box, back and forth*, reversing 180° each pass, and
the intended direction of travel is that axis (B.6.1.1 — entry and exit longitudinal axis must lie on the main or
secondary box axis). "Measured by direction of travel, which aligns with the aircraft heading where appropriate" is
right with two caveats the software has to respect:

- **Azimuth is graded on the nose, not the ground track.** A crab off the axis is 1 pt/5° (B.7.1.5); drifting
  *sideways* with the nose on the axis is free (B.7.1.6). Heading and ground track only coincide with no crosswind, so
  for level/line figures the coach charges the aircraft heading against the box axis, and treats pure wind drift as
  free — it does not penalise ground-track drift.
- **Near the vertical the nose azimuth is meaningless, so direction of travel is read from the ground track** of the
  settled entry/exit lines (spins, hammerheads, up/down verticals). The figure's rotation is then graded as the
  aircraft heading swinging relative to that travel direction — e.g. a 1½-turn spin flies out on a track reversed 180°
  from entry, and the turn count is the heading's rotation about the vertical (28.24.6). Implemented: the spin grader
  takes entry/exit direction from `trk`, the turn count from the integrated yaw rate.

The vertical/45 *attitude* criterion below (ZLA) is the pitch component and is judged separately from this azimuth
reference.


- **Horizontal lines and all looping segments are judged on the flight path** (the CG track, "CGT"), never on
  attitude (B.3.1, B.8.1.1, B.8.2.1).
- **Vertical and 45° lines are judged on attitude**, specifically the **zero-lift axis (ZLA)**: the body attitude at
  which the wing makes no lift, so the flight path would be exactly vertical in still air (B.3.2, B.3.3, B.8.1.6).
  The ZLA offset from the fuselage datum is aircraft-specific → **one calibration constant per model** (Eagle,
  Extra, RV). Wind drift on verticals/45s is *ignored* by the judge (B.3.2.2, B.3.3.1).
- **Loops must be wind-corrected**: the judge marks the flight path as a constant-radius circle over the ground, so
  the pilot varies pitch rate to hold the radius (B.7.1.2, B.9.10.1). Cross-track displacement is not penalised,
  but the loop must **start and end at the same altitude** (B.9.10.1).
- **Turns and rolling turns are NOT wind-corrected** (constant rate of turn; B.9.2.3, B.9.3.5f).
- **Crabbing** to hold position costs 1 pt/5° of nose-off-axis, but drifting sideways with the nose on axis is free
  (B.7.1.5–6). Entry and exit of every figure must have the longitudinal axis on the main or secondary box axis
  (B.6.1.1).

Consequence for us: we need (a) attitude in the box frame, (b) the CG flight path in the box frame, wind-blown as
the judge sees it, and (c) a per-aircraft ZLA constant. The Hub gives us (a) and (b) directly (attitude, GPS track
and groundspeed, lat/lon at 50 Hz); (c) is a calibration.

### 2.3 IAC Official Contest Rules 2025 — what differs from CIVA

The IAC Rule Book 2025 (obtained via the Internet Archive; kept in `docs/private/`, not in git) restates
Appendix B as chapters 26–28 plus a "Judge's Quick Reference". Same 10.0 start, 1 pt/5°, HZ at 90°, ZLA for
verticals/45s, flight path for horizontals and loops, wind-corrected looping lines, crab 1 pt/5°. The differences
that matter for a scorer:

- **Grades move in 0.5 steps** (26.1.4); unspecified deductions are proportional but never less than 0.5.
- **Errors are downgraded, corrections aren't** (26.6): an over-rotation is charged once; a misaligned *entry* to
  the next manoeuvre inside the same figure is not charged again (e.g. first point of a 4-point stops at 100°, the
  second stops exactly at 180° — no second deduction).
- **Line-length variation** thresholds are explicit: < 2:1 → 1 pt, 2:1–3:1 → 2 pts, ≥ 3:1 → 3 pts, no line on one
  side → 4, none on either side → 2 (27.9.4).
- **Loop radius has no standardised deduction** (27.10.4); two accepted methods are given — (1) 1 pt per
  just-visible change, 2 per major; (2) quarter one is the basis, each other quarter 1 / 2 / 3 pts for visible /
  1:2 / worse. Method (2) is what the coach should implement, exposed as the "judge-like" standard.
- **Competition turn**: a pause is permitted between the roll and the heading change and between the stop and the
  roll-out (28.5.2, 28.5.4); altitude 1 pt per 5° *or per 100 ft* (28.4.5); mismatched entry/exit roll rates 1 pt.
- **Slow roll**: a *stop* mid-roll is graded as the full angular error to that point (28.20.2 example: stop at 130°
  of a 180° roll then correct → 10-point downgrade), a *slow-down* is 1 pt plus the final angle error.
- **Hesitation rolls**: every roll-rate segment differing from the first → 1 pt each; every pause duration differing
  from the first → 1 pt each; an unseen pause → HZ (28.21).
- **Snap rolls**: yaw may not lead pitch (1 pt/5° if it does); autorotation ceasing early → 1 pt/5° remaining
  (28.22.3, 28.22.7). No CIVA-style 0.0 at >45° remaining.
- **Spins**: stall must produce simultaneous pitch-down, yaw and roll — lag on any axis is 1 pt/5° (28.24.2, the
  example gives 4 pts for 10° pitch + 10° roll before any yaw); autorotation stopping early → 1 pt/5° remaining;
  downline established "at the same time as, or shortly after" rotation stops (28.24.8); spins need not be centred.
- **Hammerhead pivot**: CG may displace up to ½ wingspan free, then 1 pt per additional half wingspan (28.8.3);
  wind drift during the pivot is not a deduction (28.8.5). Tailslide shorter than ½ fuselage → **HZ** (CIVA: 4 pts).
- **IAC-only figures**: Family 0 wingover (K 8) and quarter-clovers (K 16 / 13) with their own criteria (28.2–3).
- **Presentation** is a separate grade weighted 5K in Primary, 10K Sportsman (29.2).
- Primary competitors fly the Primary Known for every program (23.1a).

The **IAC Rule Book 2025 is the judging standard for this phase** (Sean, 2026-09-16). The 2026 edition exists but
isn't reachable; its changes are assumed minor and are not tracked.

### 2.4 Per-element criteria (the measurement list)

| Element | What is measured | Downgrade | Source |
|---|---|---|---|
| Horizontal line | flight-path climb/dive; nose off box axis; bank | 1 pt/5° each | B.8.1.1 |
| 45° / vertical line | ZLA attitude vs 45°/90°; wing-low (yaw axis not level); heading | 1 pt/5°; attitude change along a line ≥1 pt | B.3.2–3, B.8.1.3 |
| Line pairs around a roll | lengths equal (first sets standard) | 1 / 2 / 3 pts; 4 pts if one side missing | B.8.1.5 |
| Loop / part-loop | constant radius (judge by quadrant; higher angular velocity at the top ⇒ pinched); wings level; heading; same entry/exit altitude | radius: up to 2 pts per quadrant; others 1 pt/5° | B.8.2.1, B.9.10 |
| Roll at loop apex | centred on the arc, flown on the arc not on a line | off-centre 1 pt/5°; on a line ≥2 pts | B.9.10.3 |
| Slow roll | constant rate; crisp stop; "bumping the point" (past and back) 0.5–1 pt; flight path and heading held | rate change 1 pt each; stop → HZ if it looks like a hesitation | B.9.25, B.9.24.3 |
| Hesitation roll (2/4/8 pt) | equal segments; every pause visible and of equal duration; stops on 180/90/45° | angle error at a stop 1 pt/5° (counted once if corrected at the next stop, twice if carried); invisible pause → HZ | B.9.26 |
| Flick (snap) roll | rapid pitch break then rudder-driven autorotation (conical tail motion); stops on heading | pre-autorotation roll 1 pt/5°; autorotation stops early 1 pt/5° remaining, >45° remaining → 0.0; no stall or wrong pitch sense → HZ | B.9.27–28 |
| Spin | clean stall from a horizontal line (nose drops with the wing, CG doesn't rise); full autorotation; stop exactly on heading; vertical wings-level down line; constant quarter-loop out | forced entry 1 pt/5°; "aileroning" to heading 1 pt/5°; never stalled → HZ | B.9.29 |
| Hammerhead (stall turn) | vertical up/down on ZLA; wings level (no dragged wing); pivot in the vertical plane about a point within ½ span of the CG; no pitch/roll ("torqueing") in the pivot; rolls centred; line lengths free; pivot rate not judged | 1 pt/5°; fly-over 1 pt per ½ span beyond the limit | B.9.5 |
| Tail slide | as hammerhead plus slide ≥ ½ fuselage backwards; falls the right way | no slide 4 pts; wrong way HZ | B.9.6, 4.4.1.7 |
| Competition turn | roll to 60–90° bank on heading; constant bank, altitude and turn rate; matching entry/exit roll rates; exit on heading | 1 pt/5°; 1 pt/100 ft; rate change 1 pt | B.9.2.5 |
| Rolling turn | constant turn rate and roll rate; wings vertical/horizontal exactly at the intermediate points; short pause at reversals | rate change 1 pt, stoppage 2 pts; residual roll after the turn 1–3 pts, >45° HZ | B.9.3.6 |
| Humpty bump | verticals on ZLA; constant-radius half loop (radii may differ from each other); rolls centred; line lengths free | 1 pt/5°; radius 1–3 pts | B.9.19 |
| Half Cuban, P/Q loops, teardrops | part-loop radii need not match; rolls on 45/verticals centred; horizontal rolls next to loops follow the 7.2 no-line rule | as above | B.9.20–22 |
| Immelmann / split-S (7.2) | half loop constant radius, wind-corrected; half roll immediately after/before with **no line**; half roll not started before the loop ends | line 1–4 pts; overlap 1 pt/5° | B.9.8 |
| Square/diamond/octagon loops | equal lines, equal radii, driven by wind (not closed); overshoot-and-correct at corners 1 pt/5° | B.9.11 |
| Horizontal / vertical S and 8s | matching radii of the big loops; 45s at exactly 45°; extremities at entry altitude | B.9.13–17 |

Worked grades for each Primary figure, the rulebook's own examples and the IAC judges' exam scenarios are in
[SCORING_EXAMPLES.md](SCORING_EXAMPLES.md).

Practical notes from judges' training material (British Aerobatics judging pages, IAC "In the Loop" series):
"pinched" tops, "L-shaped" loops (vertical diameter > horizontal), egg-shaped, "e-shaped" last quadrant; shallow
45s are the most common Sportsman error and look far steeper from the cockpit than they are; half-Cuban roll
placement is a length ratio, not a time ratio; spins on 1¼/1¾ turns typically exit with a low wing.

## 3. Figure library

Aresti families (CIVA catalogue): 1 lines & angles · 2 turns & rolling turns · 3 line combinations · 5 stall
turns · 6 tail slides · 7 loops & eights · 8 combinations of lines, angles & loops · 9 rolls & spins (added onto
1–8). A figure = base figure + rolls; every figure starts and ends on a horizontal line. Machine-readable catalogue
with Aresti numbers, K factors and drawing instructions: **OpenAero** `data/figures/figures.js` (GPL-3) — K values
below are OpenAero's base-figure K for power. OLAN letters in the third column are what the sequence editor uses.

### 3.0 The IAC Primary Known (the first target)

The IAC Primary Known has been the same sequence every year since at least 2021 (positioning notes differ only).
OLAN, from OpenAero's sequence library (2026 IAC Primary Known, rules IAC 2025.1.11):

```
d iv`6s..'' .c.'2`+`` (-15,13) o 5% 2j+ 1
```

| # | Figure | OLAN | Aresti | K |
|---|---|---|---|---|
| 1 | 45° up line | `d` | 1.1.2.1 | 7 |
| 2 | 1½-turn upright spin from level flight, vertical down line | `iv6s` | 1.1.6.3 + 9.11.1.6 | 10 + 3 |
| 3 | Half Cuban with a half roll centred on the 45° down line | `c2` | 8.5.2.1 + 9.1.3.2 | 10 + 4 |
| 4 | Loop | `o` | 7.4.1.1 | 10 |
| 5 | 180° competition turn | `2j` | 2.2.1.1 | 4 |
| 6 | Slow roll (one full roll) on a horizontal line | `1` | 1.1.1.1 + 9.1.3.4 | 2 + 8 |
| | Total figure K | | | **58** (+ Presentation 5K) |

Form B: https://openaero.net/?s=hFByaW1hcnmGMjAyNodwb3dlcmVkiEtub3duiUlBQ4o1izCNZCBpdmA2c66nIC5jLicyYCvgICgtMTUsMTMpIG8gNSUgMmorIDGPSUFDkDIwMjUuMS4xMZFC
(OLAN roll digits are counts of *rolls*, not quarters: `1` = one roll, `2` = half, `3` = ¾, `4` = ¼, `5` = 1¼,
`6` = 1½, `8` = two; `Ns` = spin of the same fraction of turns.)

Element grammar for these six (what the detector must find, in order):

1. `d`: LEVEL → ⅛ LOOP(+) → LINE(45 up) → ⅛ LOOP(−, push) → LEVEL. Criteria: 45° on ZLA, wings level, heading,
   entry/exit lines present.
2. `iv6s`: LEVEL (decelerating, CG not rising) → stall break (pitch down + yaw + roll together) → SPIN(1.5 turns)
   → stop on heading → LINE(vertical down, ZLA) → ¼ LOOP(+) → LEVEL. Criteria: 28.24 / B.9.29.
3. `c2`: LEVEL → ⅝ LOOP(+, constant radius) → LINE(45 down) with ROLL(½) centred (equal line before/after) →
   ⅛ LOOP(+) → LEVEL. Criteria: radius by quarters, 45° on ZLA, roll centring 1/2/3/4-pt scale, exit heading.
4. `o`: LEVEL → LOOP(360°, wind-corrected constant radius, wings level, on heading, same entry/exit altitude) → LEVEL.
5. `2j`: LEVEL → ROLL(to ≥60° bank on heading) → TURN(180°, constant bank, altitude, rate) → ROLL(out, same
   rate) → LEVEL on the reciprocal box axis.
6. `1`: LEVEL → ROLL(360°, constant rate, crisp stop, flight path and heading held) → LEVEL.

### 3.1 Wider library (Primary → Intermediate figures; what the library grows into)

| Figure | Aresti | OLAN | Elements (grammar) | Category |
|---|---|---|---|---|
| Competition turn 90/180/270/360 | 2.1.1.1 / 2.2.1.1 / 2.3.1.1 / 2.4.1.1 (K3+) | `j`, `2j`, `3j`, `4j` | roll to bank · level turn · roll out | Primary+ |
| 45° up line (± roll) | 1.1.2.x | `d` | ⅛ loop · 45 line · ⅛ loop | Primary+ |
| 45° down line (± roll) | 1.1.3.x | `id` | ⅛ · 45 down · ⅛ | Primary+ |
| Vertical up / down line (± roll) | 1.1.6.x / 1.1.7.x | `v`, `iv` | ¼ · vertical · ¼ | Sportsman+ |
| Shark's tooth / wedge family | 1.2.x, 1.3.x | `t`, `k`, `z` combos | 45 and vertical lines with ⅛/⅜ loops | Sportsman+ |
| Loop | 7.4.1.1 (K10) | `o` | 4 quadrants | Primary+ |
| Inverted loop (push) | 7.4.1.2 | `io` | as loop, negative | Intermediate+ |
| Immelmann | 7.2.1.1 (K6) | `m` | ½ loop up · immediate ½ roll | Sportsman+ |
| Split-S | 7.2.2.1 (K6) | `a` | ½ roll · immediate ½ loop down | Sportsman+ |
| Goldfish | 7.3.x | `g` | 45 up · ¾ loop · 45 down | Sportsman+ |
| Half Cuban (and reverse) | 8.5.1.x / 8.5.2.x (K12) | `c`, `rc` | ⅝ loop · 45 down with centred ½ roll · ⅛ (reverse: 45 up first) | Primary+ |
| Cuban eight / reverse | 7.8.1–7.8.8 | `cc`, `rcc` | two ⅝ loops, 45 lines with rolls | Sportsman+ |
| Humpty bump (pull/push) | 8.4.1.x–8.4.4.x (K13) | `b`, `pb` | ¼ · vertical up · ½ loop · vertical down · ¼ | Sportsman+ |
| P-loop / reverse P | 8.6.1.x (K11) / 8.6.9.x | `p`, `rp` | vertical · ¾ loop · horizontal | Sportsman+ |
| Hammerhead (± rolls up/down) | 5.2.1.x (K17) | `h` | ¼ · vertical up · pivot · vertical down · ¼ | Sportsman+ |
| Slow roll ¼ ½ ¾ 1 1½ 2 | 9.1.x.y (full horizontal K8) | `1`, `2`(½), `3`(¾), `4`(1) … | constant-rate roll on a line | Primary+ |
| Point rolls 2/4/8 | 9.2 / 9.4 (K11) / 9.8 | `22`, `44`, `88`, `24` … | equal segments with visible stops | Sportsman+ |
| Spin n turns (upright) | 9.11.1.4–9.11.1.8 (1 turn K5) | `s`, `1s`, `is`… | stall from level · autorotation · stop on heading · vertical down | Primary+ |
| Inverted spin | 9.12.x | `is` | as above, negative | Intermediate+ |
| Positive / negative flick | 9.9.x / 9.10.x | `f`, `if` | pitch break · autorotation · stop | Intermediate+ |
| Avalanche | 7.4.1.1 + 9.9.x at apex | `o` with `f` | loop with flick centred at the top | Intermediate+ |
| Square / diamond / octagon loop | 7.4.3–7.4.6 | `q`, `dq`, `oq` | equal lines and radii | Intermediate+ |
| Horizontal / vertical S, vertical 8 | 7.5.x, 7.8.17+ | `ac`, `s8` … | joined half loops | Intermediate+ |
| Rolling turn | 2.x.y.z | `jo`, `joi` … | integrated roll + turn | Advanced |
| Tail slide | 6.x | `ta`, `ita` | vertical up · slide · fall-through · vertical down | Unlimited |

Category placement is from the IAC categories description (Primary: spin, half Cuban, loop, competition turn,
roll; Sportsman adds hammerhead, humpty, goldfish, shark's tooth, split-S, Immelmann; Intermediate adds snaps and
inverted figures; Advanced adds rolling turns). Example of a real Sportsman Known (2024): 1¼ spin, ¼ roll on a
downline, 45° down with slow roll, Immelmann, split-S with 2-of-4 point roll, half Cuban, level slow roll.

### 3.2 Element grammar

Every figure in 3.1 decomposes into a handful of element types, which is what the detector actually has to find:

`LEVEL(heading, attitude ±)` · `LINE(angle ∈ {45, 90, -45, -90}, roll spec)` · `LOOP(fraction, sense ±, radius)` ·
`ROLL(extent, kind ∈ {slow, n-point, flick±}, on ∈ {line, arc})` · `PIVOT` (hammerhead) · `SPIN(turns, sense)` ·
`SLIDE` · `TURN(angle, bank, roll spec)`.

A figure template = ordered list of elements with constraints (equal lengths, equal radii, "no line between",
"centred on the line"). This is the same decomposition Appendix B uses, and the same one Flight Coach uses
for its automated judging, so it is the right unit for scoring.

## 4. Prior art (and where WingRock is different)

- **ACROWRX** (Iscold): post-flight 3D review, Aresti code per figure, human scoring tools; now partnered with
  **FCScore** for automated scores. Not in-cockpit, not real time, no audio.
- **Flight Coach / PyFlightCoach** (RC aerobatics, F3A/IMAC): open-source Python (`flightdata`, `pfc-geometry`,
  `flightanalysis` on PyPI, `PyOlan` OLAN parser). Pipeline: log → state → split flight into manoeuvres →
  generate an ideal template for the schedule → align flown data to the template (dynamic time warping; their
  repo shows DTW alignment plots) → measure each element → deterministic downgrades → score. Paper: "Enabling the
  Automated Assessment of Precision Aerobatic Manoeuvres" (AIAA SciTech 2022). Licence has business-use
  restrictions — treat as reference design, not a dependency. Their FCScore documentation publishes the
  **IAC downgrade table** (per element: LINE, LOOP, SPIN, SNAP, STALLTURN, TAILSLIDE — which quantity is measured,
  over which part of the element, with which criterion class), a ready checklist for §2.4.
- **OpenAero** (GPL-3, JS): Aresti catalogue, OLAN parser, per-federation rules files (`data/rules/rules-iac.js`
  encodes IAC Sportsman Free K ≤ 128 with ≤ 12 base figures, etc.). Use it for the catalogue/OLAN parsing in
  sequence mode, isolated so the GPL stays contained.
- Nothing found that does **in-cockpit, real-time audio coaching**. That is the gap this phase fills; automated
  post-flight scoring exists and is the obvious ground truth to validate against (see Q6).

## 5. What the data can and cannot tell us

From the Hub's 50 Hz INS frame (docs/PROTOCOL.md): attitude (pitch/roll/true heading, 0.01°), body rates p/q/r
(0.1°/s, **low-passed at 3 Hz — peaks read ~10 % low**), body accelerations and load factor, GPS lat/lon,
groundspeed and track, flight-path angle, climb rate, MSL/WGS-84 altitude, 1 ms system time. INS-healthy can drop
for a few frames under aggressive rotation. SD log adds raw gyro/accel, NED velocity and magnetometer.

**Not available:** airspeed, angle of attack, control positions (these exist in the Hub's WebSocket status frame
only with the optional air-data / analog-input modules), wind. So:

- "What the controls did" must be *inferred* from motion: roll rate history (slow roll rate constancy, rudder-vs-
  aileron in a flick from the yaw/roll/pitch signature), pitch rate vs speed for loop radius, yaw rate during a
  hammerhead pivot, load factor drop and yaw-rate spike for the stall break. Feasible for the criteria in §2.3;
  true control-position coaching would need the analog-input module (Q9).
- **ZLA**: by Sean's ruling (2026-09-16) the wing's zero-lift line is taken as coincident with the IMU axis on
  every aircraft — ZLA offset = 0°, so vertical and 45° lines are graded straight from the Hub's pitch. No
  calibration flight. Revisit only if verticals graded from the replay look systematically off.
- **No control-position data** and none coming: control-input coaching is inference from motion only.
- **Wind** for judge-perspective flight paths: estimate from wings-level horizontal lines (heading vs track and
  groundspeed give the crosswind and a TAS estimate), or let the pilot enter winds aloft (Q5).
- **Stall detection** for spins/flicks: no AoA, so use the kinematic signature (nz falling through ~0.5–0.8 g at
  low groundspeed, nose drop, yaw rate onset). Needs validation on real spins from the logs.

## 6. Architecture

One coaching engine, in JavaScript, in `web/coach/`, so it runs identically in the phone app and in the browser
replay, on the same sample stream the display uses. Python stays for offline analysis and test fixtures.

```
50 Hz samples ──► features (box-frame attitude, CG track, wind-corrected path, ZLA-corrected angles,
                  rates, nz) ──► element detector (state machine: LEVEL/LINE/LOOP/ROLL/PIVOT/SPIN, with
                  hysteresis and minimum durations) ──► figure matcher (selected template, or library
                  search in sequence mode; Appendix-B constraints) ──► element measurements ──►
                  downgrades (§2.3 rules, points) ──► score + ranked critique ──► speech / HUD card
```

- **Trigger and timing.** The figure ends when the aircraft is back on a horizontal line for ~2 s (the detector's
  LEVEL state); the critique follows within ~1 s. That lands inside the 10–20 s repositioning leg. In-figure cues
  (during the manoeuvre) are a later, opt-in layer with a much stricter false-alarm budget.
- **Critique content.** Ranked by points lost, capped at 2–3 items, each phrased as observation + correction
  ("Loop pinched at the top, about 2 points — ease the pull over the top", "Exit heading 12° right — 2 points").
  Score shown on the HUD as the judge would give it (x.x of 10, and K-weighted in sequence mode).
- **Audio.** iOS `AVSpeechSynthesizer` from the native shell, routed wherever the phone's audio goes (headset
  Bluetooth or speaker — Q4). Short earcons for in-figure cues later.
- **Judge perspective.** The box is already defined (judges' position + axis). Loop roundness and line geometry are
  evaluated in the box frame from the judges' side, so a loop flown crosswind is scored the way it looks from the
  ground.
- **Figure selection UI.** A "Coach" panel: category filter → figure list (name, Aresti drawing from OpenAero,
  K) → arm. Sequence mode later: paste an OLAN string, the app shows the figure list and coaches the next one.

### 6.1 The "correct figure" overlay

Once the flown figure has been matched to its template, the app builds the **ideal version of that figure, fitted
to how it was actually entered**, and draws it in 3D next to the flown trail:

- Anchored on the flown entry: same entry point, entry heading (snapped to the box axis) and entry altitude; the
  ideal figure is what a 10.0 would have looked like *from there*.
- Sized from the flight: loop radius from quarter one (judge‑like standard) or the best‑fit radius (absolute
  standard), whichever standard is selected; line lengths from the first line flown; roll placed at the exact
  centre; spin exit on the exact heading; vertical/45° lines at exactly 90°/45°.
- Drawn as a translucent ghost line (white) alongside the flown trail (orange). Differences are made visible
  two ways: the flown trail is tinted by local deviation (green → amber → red), and short "rib" lines connect
  the flown path to the ideal at regular intervals so the gap reads at a glance. Tapping a rib shows the number
  (metres / degrees / points).
- Per‑element annotations along the ghost: "−1 pinched", "45° line 38°", "exit 10° R", the same items the
  audio speaks.
- This is the template‑and‑align idea Flight Coach uses for post‑flight scoring, done in the box frame, live.

### 6.2 Replay: go back and watch it again

- **Sample ring buffer** in the app: the full 50 Hz sample (pose, rates, g, position) for the last 20 minutes
  (~60k samples, a few MB), replacing today's 2 s interpolation buffer as the source of truth. Live reception
  keeps filling it during replay.
- **Replay mode** (a fourth camera‑bar state next to Judge/Orbit/Chase): scrub bar with figure markers,
  play/pause, 0.25× / 0.5× / 1×, step by element, "Last figure" and "Last routine" buttons, and a "Live" button
  to return. All cameras work in replay; the judge camera is the default because that is what the score is about.
- **Compare**: the ideal overlay is shown in replay by default; the score card and per‑element annotations follow
  the scrubber; in sequence mode the scrub bar is chaptered per figure with each figure's grade and K.
- **Auto‑replay** (optional setting): right after a figure ends, the view replays it once at the judge camera
  while the critique is spoken — the original phase‑3 idea from PLAN.md, now with the overlay.
- Replay works on the ground too: after landing, with no Hub data, the app parks the aircraft in the hangar but
  the buffer is still there, so the whole routine can be replayed and compared as a debrief.
- **Flights are saved on the phone** (Sean, 2026-09-16). The native shell writes every received frame to
  `Documents/Flights/<date>_<time>.bin` in the same record format the bridge already uses for `sessions/*.bin`
  (`<dH` wall‑clock + length header, 67‑byte payload), so the Python decoders and converters work on phone
  files unchanged. A new file starts at each launch and whenever the INS re‑initialises; empty files are deleted.
  Storage is trivial: 50 Hz × 77 bytes ≈ 14 MB per flying hour. The Flights folder is exposed to the iOS Files app
  (file sharing enabled) for export and for pulling logs onto the Mac. A "Flights" list in the app opens any saved
  flight in Replay mode, chaptered by detected figures.
- Later: compare two attempts of the same figure (this loop vs the previous one, or vs the best one this
  session) by drawing both trails against one ideal.

## 7. Phases

| Phase | Deliverable | Exit criterion |
|---|---|---|
| **C0 Ground truth & labels** | Label the figures in the three real flights (data16/17/18) with start/end and figure type; collect any scores/judge sheets/ACROWRX–FCScore output for them (Q6) | A labelled set of ≥ 20 figures across ≥ 6 types |
| **C1 Element detector** | `web/coach/` detector over the replay; tuned on C0; browser debug view showing detected elements over the trail | Element boundaries within ~0.3 s of labels on ≥ 90 % of labelled figures; no false figures on a non-aerobatic log |
| **C1b Replay & flight files** | 20‑min sample ring buffer; Replay mode with scrub bar, speeds, "Last figure" (from the detector's figure boundaries), "Live" return; works parked on the ground; frames saved to `Documents/Flights/` and a Flights list that opens a saved flight in replay | Any figure from the last 20 minutes can be replayed at the judge camera within two taps, live data uninterrupted; yesterday's flight replays from the Flights list and its file opens with the Python tools |
| **C2 Figure library & matcher** | Templates for §3.1 (Primary+Sportsman first); pick-a-figure UI; match flown elements to the armed figure | Every labelled figure of the armed type is matched; wrong-type figures are rejected |
| **C3 Measurements, scoring & overlay** | Per-element measurements and §2.4 downgrades; HUD score card after each figure; the ideal‑figure ghost with deviation tint, ribs and annotations (§6.1), shown in replay and optionally live | Scores within ~1 point of Sean's grades on the labelled set; the ghost visibly explains every deduction the card lists |
| **C4 Audio debrief** | Spoken critique in the app after each figure; headset routing; volume/verbosity settings | Sean can fly a practice session hands-off and get a useful call after each figure |
| **C5 In-figure cues** | Opt-in live cues for the low-risk criteria: heading drift on lines, wing-low on verticals, roll-rate change, pinching (pitch rate rising at the top) | Cue latency < 0.5 s, false cues rare enough that they are turned on and left on |
| **C6 Sequence mode** | OLAN input via OpenAero's parser (the Primary Known preloaded); figure-by-figure coaching; K-weighted sequence score; "Last routine" replay with a chaptered scrub bar | The whole Known flown with the app calling each figure, then replayed figure by figure with grades |

C0–C3 can be done on the ground with the logs and the replay; C4 onward needs flying.

## 8. Risks and unknowns

- Kinematic stall/autorotation detection without AoA (spins, flicks) — validate on real spins early (C1).
- Wind changes what "round" means for loops; it is estimated from level lines (Q5). ZLA is fixed at zero by ruling.
- Rate low-pass (3 Hz) blunts hesitation-roll stop detection and flick onset; may need the raw-gyro path from the
  SD log for tuning and accept the loss live.
- Judge-like vs absolute: a judge takes quarter one as the radius standard and marks what they *see*; a coach could
  say "your radius grew 30 % over the top" absolutely. Deciding which voice to use matters (Q10).
- Cockpit workload and safety: audio must be short, low-frequency, and silent by default during manoeuvring.
- Public repo: keep sequences, scores and any judge sheets Sean shares out of git unless he says otherwise.

## 9. Decisions so far (Sean, 2026-09-16)

- **First library = the six figures of the IAC Primary Known** (§3.0): 45° up line, 1½-turn spin (turns
  parameterised), half Cuban with half roll, loop, 180° competition turn, slow roll. Sportsman figures follow once
  these score credibly.
- **Both modes in this phase, both Primary-based**: single-figure coaching (arm one figure) and sequence mode (the
  Primary Known as a whole, figure by figure, K-weighted total).
- **Audio**: just play it through the phone's current audio route; if a headset is connected, that is where it goes.
  No headset-specific handling.
- **Critique length**: coach's call — the top two or three downgrades by points lost, then the score.
- **ZLA offset is zero for all aircraft** (wing zero-lift line assumed in line with the IMU axis); no per-type
  constant, no calibration. **No control-stick inputs** exist or are planned.
- **Ideal‑figure overlay and replay are in scope** (Sean, 2026-09-16): after a figure, show the correct figure
  fitted to the flown entry as a ghost over the flown trail; let the pilot scrub back and replay the last figure
  or the whole routine and compare (§6.1–6.2, phases C1b/C3/C6).
- **Cue timing is a user setting**: after-figure debrief · during + after · on-demand only. Default to after-figure.
- **Audio goes over Bluetooth to the headset** (model to confirm); phone speaker kept as the ground-test fallback.
- **Validation data = data16 only**, graded against Sean's own judgement of the replay to start; real scores or
  judge sheets are added when they exist. The other logs stay out of the loop for now.
- **Wind is estimated from wings-level horizontal lines** (heading vs GPS track and groundspeed) before each
  figure; no pilot entry. Loops and horizontal paths are judged wind-corrected, verticals/45s on attitude.
- **Critique voice is a user setting**: what the aircraft did + points · aircraft + control correction (per-type,
  signed off by Sean) · score only.
- **Score standard is a user setting, both present**: judge-like (quarter one sets the radius, 1 pt/5°, marks what a
  judge could see) and absolute geometry (true radius change, degrees). Judge-like is the default headline.
- **Judging standard = IAC Rule Book 2025**, with CIVA Appendix B filling anything the IAC text leaves open;
  both PDFs are in `docs/private/` (gitignored). The 2026 edition is not tracked.

## 10. Open questions (answers change the design — none of these are assumed)

1. ~~Category and figure set~~ — answered: Primary; the Known is in §3.0 (from OpenAero's library, unchanged
   since 2021).
2. ~~Judging standard~~ — answered: IAC Rule Book 2025 (§2.3), CIVA Appendix B where the IAC text is silent.
3. ~~When should the coach talk?~~ — answered: user setting (after / during + after / on demand); 2–3 items.
4. ~~Audio path~~ — answered: play through whatever the phone is connected to; nothing headset-specific.
5. ~~Wind~~ — answered: estimate from level lines.
6. ~~Ground truth~~ — answered: data16 only, Sean's judgement first.
7. ~~Aircraft / ZLA~~ — answered: assume the zero-lift line is in line with the IMU axis on all aircraft.
8. ~~Control-position sensing~~ — answered: none available; control inputs are inferred from motion.
9. ~~Scope of "correction"~~ — answered: user-selectable voice (aircraft-only / with control corrections / score
   only). Still needed: Sean's sign-off on the correction phrasing per figure before it ships.
10. ~~Voice of the score~~ — answered: user-selectable, both present.
11. ~~Sequence mode timing~~ — answered: both single-figure and sequence mode in this phase, Primary-based.
12. ~~Replay persistence~~ — answered: save flights on the phone (§6.2).

## 12. Phase 2 — real-time evaluation in the cockpit (next batch)

The goal for this batch: a display that is trivial to use at 6 G with gloves on, gives useful spoken feedback the
instant a figure ends, and lets the pilot review the figure they just flew before the next one. Three things to
build: a **run lifecycle** (start/stop that scopes a scored routine), **audio-first real-time polish**, and
**between-figure replay** (the app's original reason to exist). What exists today is always-on ambient grading —
`liveDetector` grades every figure the moment it closes; there is no scoped run and no start/stop.

### 12.1 The run lifecycle (start/stop)

The interaction budget in the airplane is near zero during a figure, so the design leans on automatic detection with
a single large manual override, rather than asking the pilot to tap between figures.

- **Individual figures — ambient, no run.** Coach figure = Any (or a specific figure). Fly anything; each figure is
  graded and spoken as it completes. This is today's behaviour and needs no start/stop. Best for practising one
  figure over and over.
- **Full sequence — an armed run.** Coach figure = Primary Known. The pilot **arms** the run once (one big tap, or
  it auto-arms on box entry). The run **starts** on the first recognised figure, tracks the Known in order, speaks a
  per-figure score, and **ends automatically** after the last Known figure (or after sustained wings-level flight /
  box exit), announcing the total. Nothing is touched mid-routine.
- **Partial sequence — stop early.** The same armed run, ended by a **Stop** tap (or by levelling off). It grades the
  figures actually flown, reports a partial total, and says which Known figures were not attempted.

Recommended control: one prominent **Start / Stop** button (glove-sized, in the control dock), plus **auto-arm on
box entry** and **auto-end on level-off / box exit** so the hands-free path needs no taps at all. A **Redo** action
discards the last figure when the entry was flubbed. During a run, a persistent glanceable chip shows state and
running total, e.g. `▶ 3/6 · 62%`. Every run is saved as a flight (already supported) with its run boundaries and
total, so it drops straight into replay.

Open decision for Sean: **auto-detected runs with a manual override** (recommended, most hands-free) vs a **plain
manual Start/End toggle** (simpler, more predictable) vs **keep it always-on ambient** and only add a "save this run"
marker. This choice drives the rest of the build.

### 12.2 Audio-first real-time polish

The pilot cannot look at the screen during the figure, so the spoken channel is primary and must be tight.

- **Timing:** speak the critique the moment the figure closes, not during it; never overlap two figures' speech
  (queue, and drop stale ones if the pilot is already into the next figure).
- **Brevity and priority:** one sentence, the biggest deduction first, in the pilot's chosen voice (aircraft / +fix /
  score). A hard zero is called immediately and plainly.
- **Non-verbal cues:** a short chime for a clean figure, a low buzz for a hard zero, so the pilot gets a glanceless
  read without parsing words. Optional, user-toggle.
- **Running total:** at sequence end, speak the percentage and the weakest figure ("Sequence 62 percent, the loop
  cost you the most"). A mid-run total is on the chip, not spoken.
- **Graceful disorder:** if a figure comes out of order or is the wrong type for the Known slot, say so once
  ("expected a spin here") and let the pilot continue or Redo, without derailing the run.

### 12.3 Between-figure replay in real time

This is the original vision: seconds after a figure, while repositioning, the pilot glances down and sees what they
just flew against the ideal.

- **Auto-surface the last figure.** When a figure closes during a run, the coach card already shows; extend it to
  optionally show the just-flown trace with the ideal ghost, fitted and box-aligned (the replay ghost work is done),
  sized for a two-second glance.
- **One-tap loop.** "Last figure" already replays the most recent figure; make it one big tap (or a voice word) and
  have it loop with the ghost until dismissed, so the pilot can study the difference between figures.
- **Non-intrusive:** the live HUD stays primary; the replay is a glance, not a takeover, and clears itself when the
  next figure starts.

### 12.4 Robustness for live use

- Suppress false figures during climb-out, positioning and wind-correction (gentle turns already fall to OTHER; tune
  the dwell and level thresholds against real box time).
- Keep the frame pipeline low-latency end to end so the spoken critique lands within a second of the figure ending.
- Wind and box awareness apply live, not just in replay (the box already travels in the file).

### 12.5 Suggested build order

1. Run lifecycle: arm / run / stop (manual first, then auto-arm/auto-end), partial-sequence scoring, save the run.
2. Audio-first polish: speech timing and queueing, priority phrasing, non-verbal cues, spoken end total.
3. Between-figure replay: auto-surface the last figure with the ghost, one-tap loop, auto-clear.
4. Robustness pass on live false-detection and latency, tuned against real flight data.

## 11. Sources

- FAI Sporting Code Section 6 Part 1, version 2023-2, Rule 4.4 and Appendix B (civanews.com document store).
- IAC Official Contest Rules 2025, chapters 22–23 and 26–29 plus the Judge's Quick Reference (iac.org, via the Internet Archive).
- British Aerobatics judging pages: downgrades summary, loops, slow rolls, flick rolls, spins, stall turns, humpty
  bumps (aerobatics.org.uk/judging).
- IAC: category descriptions (iac52.org, iacchapter26.org), "In the Loop" series by Gordon Penner (half Cuban,
  spin, Immelmann, humpty bump, hammerhead, competition roll, loop, 2024 Sportsman sequence).
- OpenAero: github.com/OpenAero/main — `data/figures/figures.js`, `data/rules/rules-iac.js` (GPL-3).
- Flight Coach: flightcoach.org (research, FCScore); PyFlightCoach on GitHub/PyPI (`flightanalysis`, `PyOlan`).
- ACROWRX: acrowrx.com, docs.acrowrx.com.
