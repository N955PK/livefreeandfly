# WingRock coaching — plan for the next phase

Status: research and planning, 2026-09-16. Nothing here is built yet. Open questions are at the end; several of
them change the design, so they come before code.

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

### 2.3 Per-element criteria (the measurement list)

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

### 3.1 First library (Primary → Intermediate figures; what the MVP should recognise)

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
  restrictions — treat as reference design, not a dependency.
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
- **ZLA** per aircraft: measure it from the pilot's own best verticals (the attitude at which GPS flight-path
  angle is ±90° in calm air) or take a nominal value per type and let the pilot trim it.
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

## 7. Phases

| Phase | Deliverable | Exit criterion |
|---|---|---|
| **C0 Ground truth & labels** | Label the figures in the three real flights (data16/17/18) with start/end and figure type; collect any scores/judge sheets/ACROWRX–FCScore output for them (Q6) | A labelled set of ≥ 20 figures across ≥ 6 types |
| **C1 Element detector** | `web/coach/` detector over the replay; tuned on C0; browser debug view showing detected elements over the trail | Element boundaries within ~0.3 s of labels on ≥ 90 % of labelled figures; no false figures on a non-aerobatic log |
| **C2 Figure library & matcher** | Templates for §3.1 (Primary+Sportsman first); pick-a-figure UI; match flown elements to the armed figure | Every labelled figure of the armed type is matched; wrong-type figures are rejected |
| **C3 Measurements & scoring** | Per-element measurements and §2.3 downgrades; HUD score card after each figure | Scores within ~1 point of the reference scores from C0 on the labelled set (or Sean's own judgement where no reference exists) |
| **C4 Audio debrief** | Spoken critique in the app after each figure; headset routing; volume/verbosity settings | Sean can fly a practice session hands-off and get a useful call after each figure |
| **C5 In-figure cues** | Opt-in live cues for the low-risk criteria: heading drift on lines, wing-low on verticals, roll-rate change, pinching (pitch rate rising at the top) | Cue latency < 0.5 s, false cues rare enough that they are turned on and left on |
| **C6 Sequence mode** | OLAN input via OpenAero's parser; figure-by-figure coaching; K-weighted sequence score | The whole Known flown with the app calling each figure |

C0–C3 can be done on the ground with the logs and the replay; C4 onward needs flying.

## 8. Risks and unknowns

- Kinematic stall/autorotation detection without AoA (spins, flicks) — validate on real spins early (C1).
- ZLA and wind: both change what "vertical" and "round" mean; both need a calibration story (Q5, Q7).
- Rate low-pass (3 Hz) blunts hesitation-roll stop detection and flick onset; may need the raw-gyro path from the
  SD log for tuning and accept the loss live.
- Judge-like vs absolute: a judge takes quarter one as the radius standard and marks what they *see*; a coach could
  say "your radius grew 30 % over the top" absolutely. Deciding which voice to use matters (Q10).
- Cockpit workload and safety: audio must be short, low-frequency, and silent by default during manoeuvring.
- Public repo: keep sequences, scores and any judge sheets Sean shares out of git unless he says otherwise.

## 9. Decisions so far (Sean, 2026-09-16)

- **First library = Primary figures only**: competition turn (180°), 45° up line, loop, one-turn spin (n half-turns
  parameterised), half Cuban, slow roll. Templates and the detector are built and validated on these five/six first;
  Sportsman figures follow once the Primary set scores credibly.
- **Cue timing is a user setting**: after-figure debrief · during + after · on-demand only. Default to after-figure.
- **Audio goes over Bluetooth to the headset** (model to confirm); phone speaker kept as the ground-test fallback.
- **Validation data = data16 only**, graded against Sean's own judgement of the replay to start; real scores or
  judge sheets are added when they exist. The other logs stay out of the loop for now.

## 10. Open questions (answers change the design — none of these are assumed)

1. ~~Category and figure set~~ — answered: Primary. Still needed: the exact Primary Known you fly (OLAN string /
   Form B) so the templates match the sequence, not just the figure types.
2. **Judging standard.** IAC rulebook (which year) or CIVA Appendix B? The IAC site blocks downloads — can you
   share the current IAC Rule Book PDF so I can diff its judging chapter against Appendix B?
3. ~~When should the coach talk?~~ — answered: user setting (after / during + after / on demand). Still needed: how
   many items per figure is useful in the cockpit.
4. ~~Audio path~~ — answered: Bluetooth to the headset. Still needed: headset/intercom model (Bluetooth profile
   and latency differ; some panels duck music under intercom audio).
5. **Wind.** Enter winds aloft by hand before the flight, estimate from level lines, or ignore wind for the first
   version and coach on attitude only?
6. ~~Ground truth~~ — answered: data16 only, Sean's judgement first.
7. **Aircraft.** Eagle only for the coaching phase? Any known ZLA/incidence figure for the Eagle, or shall we
   calibrate from your verticals?
8. **Control-position sensing.** Is the OnFlight analog-input module (control positions) something you'd add? It
   turns "your inputs" from inference into measurement.
9. **Scope of "correction".** Should the coach say what the *aircraft* did ("pinched top") or attempt to say what
   the *hands* should do ("less back pressure over the top")? The second needs per-type tuning and your sign-off.
10. **Voice of the score.** Judge-like (quarter one sets the standard, marks what a judge would see) or absolute
    geometry (true radius, true heading), or both with the judge score as the headline?
11. **Sequence mode timing.** Is sequence mode wanted soon, or is single-figure coaching the whole of this phase?

## 11. Sources

- FAI Sporting Code Section 6 Part 1, version 2023-2, Rule 4.4 and Appendix B (civanews.com document store).
- British Aerobatics judging pages: downgrades summary, loops, slow rolls, flick rolls, spins, stall turns, humpty
  bumps (aerobatics.org.uk/judging).
- IAC: category descriptions (iac52.org, iacchapter26.org), "In the Loop" series by Gordon Penner (half Cuban,
  spin, Immelmann, humpty bump, hammerhead, competition roll, loop, 2024 Sportsman sequence).
- OpenAero: github.com/OpenAero/main — `data/figures/figures.js`, `data/rules/rules-iac.js` (GPL-3).
- Flight Coach: flightcoach.org (research, FCScore); PyFlightCoach on GitHub/PyPI (`flightanalysis`, `PyOlan`).
- ACROWRX: acrowrx.com, docs.acrowrx.com.
