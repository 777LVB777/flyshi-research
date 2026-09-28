# The drive confound in the mirrored, unbalanced encoder

**Status: ANALYSIS, 2026-09-28. Findings only; no mitigation is selected or
implemented.** Written while the 60-simulation validation
([`graded-encoding-left-only-mirrored.md`](graded-encoding-left-only-mirrored.md))
was running, and before its verdict was seen. That validation's spec is not
modified. Its encoder is validated as pre-stated: pattern plus drive, with the
confound recorded there in §2.3.

**Sources.** Every number comes from saved result files in
`repro/mushroom_body/results/`: the left-only realistic-drive diagnostic's summary
and per-seed MBON vectors, and the left-only ladder's summary. No simulation was
run and the connectome was not loaded. Each claim below is marked **measured**
(read or computed directly from saved rates) or **inferred** (it depends on a
model or an assumption, which is named).

---

## 1. What the confound is, in this encoder

Under mirroring with shared, unbalanced pools and a midpoint background, YES and
NO present **the same 500 KCs**. They differ only in the price pool's rate:
`r(v)` against `r(1−v)`, with `r(v) = 30 + 120 v` Hz. Hence

```text
x_YES(v) − x_NO(v) = 120 (2v − 1) Hz on each of the 100 price-pool KCs, 0 elsewhere
D_YES(v) − D_NO(v) = 12,000 (2v − 1) Hz
```

In this encoder, "total drive" and "price-pool rate" are therefore **not two
things the stimulus varies separately**. The drive difference *is* the price-pool
rate difference. The confound is not "pool identity versus drive" within a given
stimulus. It is a counterfactual question:

> **Would the same rate change applied to some other 100 KCs produce the same
> S(v)?**

If it would, the CIRCUIT score is reading total drive and the price pool's
identity contributes nothing to the scalar. If it would not, part of `S(v)` is
specific to which KCs carry the value.

## 2. What existing data can and cannot say

### 2.1 The price sweep is one-dimensional (measured)

The five unbalanced stimuli fix 500 KCs and change only the price pool's rate,
so for all of them `D = 36,000 + 100 · r_price` Hz exactly. The `left_ladder_500`
condition (price at 90 Hz on the same 500 KCs) is a sixth point on the same line:
it is the encoder at `v` = 0.50.

| stimulus | total drive (Hz) | price (Hz) | score mean (Hz) | SE over 6 seeds | APL (Hz) |
|---|---:|---:|---:|---:|---:|
| unbalanced `v` = 0.05 | 39,600 | 36.0 | −146.38 | 0.64 | 173.6 |
| unbalanced `v` = 0.22 | 41,640 | 56.4 | −154.58 | 0.87 | 175.6 |
| unbalanced `v` = 0.41 | 43,920 | 79.2 | −159.27 | 0.38 | 177.0 |
| `left_ladder_500` (`v` = 0.50) | 45,000 | 90.0 | −163.32 | 0.50 | 177.5 |
| unbalanced `v` = 0.63 | 46,560 | 105.6 | −167.86 | 0.70 | 179.1 |
| unbalanced `v` = 0.88 | 49,560 | 135.6 | −176.27 | 0.65 | 180.7 |

- **Slope.** Fitting a line gives **−2.94 Hz of score per kHz of drive**. The
  per-seed fits give −2.94 ± 0.06 (SE).
- **Linearity.** Residuals from the line are at most 1.36 Hz, so the sweep is
  close to linear over its span.
- **Why this can't separate the two.** Along this sweep a price effect and a
  drive effect are the **same regression**. No analysis of these six points can
  split them, however done.

### 2.2 Drive through *other* KCs lands on the same curve (measured scores; inferred model)

Two stimuli add drive through a 300-KC pool that the price sweep never touches.
These are the balanced encoder's `v` = 0.00 and `v` = 0.25 YES stimuli, drawn
left-only: the same five feature pools, plus the balance pool at 70 or 50 Hz, with
the price pool at 30 or 60 Hz.

| stimulus | drive (Hz) | observed score | linear-in-drive prediction | quadratic-in-drive prediction |
|---|---:|---:|---:|---:|
| balanced `v` = 0.25 | 57,000 | −195.00 (SE 0.83) | −198.29 | **−195.11** |
| balanced `v` = 0.00 | 60,000 | −201.72 (SE 0.55) | −207.10 | **−202.04** |

The quadratic model is fitted **only to the five price-sweep points** and
extrapolated 7–10 kHz beyond them. It predicts both stimuli to within 0.11 and
0.32 Hz, which is inside one standard error. The linear model misses by 3–5 Hz.
Paired by seed against the nearest price-sweep stimulus, the score moves 0.90×
and 0.92× as much per Hz as the linear price slope predicts. The shortfall is the
amount the curve flattens between 40 and 60 kHz: the quadratic's local slope runs
from −3.14 to −2.24 Hz/kHz.

**Inferred:** over 39.6–60 kHz, the CIRCUIT score of these left-only stimuli is
consistent with **a single function of total drive**, whichever KCs carry that
drive. The data show no scalar effect specific to KC identity. The residuals at
the balanced points are 0.1–0.3 Hz against standard errors of 0.6–0.8 Hz.

This rests on assumptions:

- a smooth curve in drive, fitted from five points with three parameters;
- a 10 kHz extrapolation;
- that the price-rate change and the added balance pool may be summarised by
  their total drive;
- a comparison that changes the **number** of driven KCs (500 → 800), which is a
  different manipulation from moving the same rate onto a different 100 KCs.

**Outside 39.6–60 kHz the single curve fails.** The ladder's low-drive rungs
(9–27 kHz, with 100–300 KCs) score −22.7, −50.3 and −82.0 Hz. The line predicts
−57.3, −83.8 and −110.2 Hz. Adding whole pools at 90 Hz moves the score −3.1 to
−4.5 Hz per kHz depending on the rung. The single-function description is
local, not general.

### 2.3 At the MBON-vector level, identity is visible (measured)

The mean MBON change over six seeds (96 instances) for each manipulation:

| change | ΔD (kHz) | ‖Δm‖ (Hz) | ‖Δm‖ per kHz | cosine with the price-sweep change |
|---|---:|---:|---:|---:|
| price 36 → 135.6 Hz (sweep endpoints) | 9.96 | 101.1 | 10.2 | 1 |
| balance pool 70 Hz added (vs `v` = 0.05) | 20.40 | 186.3 | 9.1 | **0.977** |
| balance pool 50 Hz added (vs `v` = 0.22) | 15.36 | 140.2 | 9.1 | **0.976** |
| ladder 300 → 500 (two pools added at 90 Hz) | 18.00 | 252.8 | 14.0 | 0.961 |

Reference values:

- **Noise ceiling.** Each of these changes estimated twice, from disjoint halves
  of the seeds, agrees with itself at cosine 0.997–0.999.
- **Rotation along the sweep.** The price sweep's low-half and high-half changes
  (`v` 0.05 → 0.41 and 0.41 → 0.88, similar norms 48 and 53 Hz) agree at cosine
  **0.995**. That is how much the direction rotates when only the operating point
  moves along the price sweep.
- **Size of the difference.** Adding the balance pool leaves an orthogonal
  component of about 21% of its change: 40 Hz of 186 Hz, against a per-seed
  change spread of about 12 Hz.

**Reading.**

- **The dominant direction is shared.** Driving any of these KC sets harder moves
  the MBON vector mostly along one direction.
- **A smaller component is specific to which KCs are driven.** It is above the
  noise ceiling and above the rotation the operating point alone produces.
- **The two measurements disagree only in appearance.** The scalar CIRCUIT
  readout does not register that component in §2.2. The vector does. Pool
  identity carries information the vector contains, but it is not visible in the
  scalar score in these data.

**Caveat (inferred).** The balance comparison also crosses a higher operating
range (40 → 60 kHz) and adds KCs rather than changing a rate. Part of the
orthogonal component may be operating-point nonlinearity, not identity. The 0.995
same-KC rotation is measured over 40–50 kHz only.

### 2.4 What existing data cannot do

- **Separate identity from drive for `S(v)` directly.** No saved stimulus moves a
  *non-price* 100-KC pool's rate on the same 500 KCs. That is the counterfactual
  of §1, and it was never run.
- **Show that identity is irrelevant to the scalar.** §2.2 shows agreement with a
  drive-only curve for a manipulation that also changes KC count. Agreement
  within noise is not evidence of absence at the rate-change level that matters
  for `S`.
- **Say anything outside 39.6–60 kHz**, or for backgrounds off the midpoint.

**Size of the innate drive term, if the drive-only model holds (inferred).**

```text
S_innate(v) ≈ −2.94 Hz/kHz × 12 (2v − 1) kHz ≈ −35 (2v − 1) Hz
```

This is −31 Hz at `v` = 0.94. It is the same figure the validation spec's
planning estimate arrived at (§8 there). On the drive-only reading, **essentially
all of the innate `S(v)` the validation measures would be generic intensity**,
not a price-pool-specific code. The framing that presents the higher price value
receives more drive and scores more negatively. Which decision that favours
depends on the market decision rule, which is not restated here.

## 3. Candidate mitigations (none recommended)

"Running validation" means the 60-simulation validation now in progress on the
unbalanced mirrored encoder. None of these options changes its verdict *as a
verdict about that encoder*. Where an option alters the encoder, that verdict no
longer covers the encoder the market experiment would use.

### 3.1 Innate-score subtraction

```text
s_mit(v; W) = S(v; W) − S(v; W₀)
```

That is, the decision score minus the same stimulus's score at baseline weights,
at the same seed.

- **Fixes:** it removes the whole baseline value-dependent score, drive term
  included, from every decision. Before learning, `s_mit ≡ 0`.
- **Leaves:**
  - a second-order drive term that re-enters through gain (§4.3);
  - noise from four presentations instead of two, where common-random-number
    cancellation between innate and learned runs is unverified because their
    weights differ;
  - an exact tie at every decision before learning, so the training-only
    exploration rule fires on essentially every early market (as recorded in
    `balanced-encoding-failure.md` §4c).
- **Simulation cost:** no new graded runs, because the running validation's data
  *are* the innate scores for set B. In the market experiment, each decision
  needs its innate YES and NO presentations. The job planner recorded 125 jobs /
  25,000 runs under innate subtraction, against 100 jobs / 20,000 runs under
  balancing (`balanced-encoding-failure.md` §4c). That was computed for the
  earlier design and is not re-derived here. If innate scores can be cached per
  distinct feature vector, the cost falls; continuous market features make exact
  reuse unlikely.
- **Invalidates the running validation?** No. The validation measures
  `S(v; W₀)`, which is exactly the innate term. §4 examines what it does and does
  not validate about `s_mit`.
- **Post-hoc or new runs:** trivially computable on the graded data, where it
  gives zero. Its use in the market experiment requires the market runs
  themselves: there is no learned data yet to apply it to.

### 3.2 Drive-matched balance pool within each framing

Give each framing its own balance pool at a rate set by **its own** presented
value, so every framing's total drive is constant. With the 300-KC balance pool:

```text
r_b(p) = 50 − (r(p) − 90) / 3  Hz           (30–70 Hz as r(p) runs 150–30 Hz)
D      = 400·90 + 100·r(p) + 300·r_b(p) = 60,000 Hz  for every p
```

Because each stimulus depends only on its own presented value, **the mirror
identity `NO(v) ≡ YES(1−v)` is preserved exactly.** This differs from the earlier
balancing rule, which set the pool from the *pair*: its recorded FAIL was on
bilateral pools and is not evidence about this rule either way.

**A leaner variant** uses a complementary 100-KC pool at `r(1−p)` (push–pull):

- It holds `D` = 54,000 Hz constant with 600 KCs.
- It preserves the mirror, because NO swaps the two pools' rates.
- It makes `x_YES − x_NO` antisymmetric across the two pools, not confined to
  the price pool.

Either way:

- **Fixes:** it removes the total-drive difference exactly, so `S(v)` can only
  reflect which KCs fire at what relative rate.
- **Leaves:**
  - an opposing pool whose own wiring enters the contrast, as the balance pool's
    did;
  - an operating point at 54,000–60,000 Hz and 600–800 KCs. That regime was
    contained left-only (realistic drive, balanced stimuli: 0/6 ignited, score SD
    1.3–2.0 Hz).
- **Risk, inferred from §2.** If the CIRCUIT scalar is close to a function of
  total drive alone, holding drive constant could leave little baseline value
  signal in `S(v)`. A graded validation of this encoder could then FAIL on
  signal, not noise. The vector-level identity component of §2.3 suggests the
  information exists in the MBON pattern. Whether the scalar readout registers it
  is unmeasured.
- **Simulation cost:**
  - a new graded validation of the new encoder: 60 simulations, the same shape
    as now, about 55 minutes at the measured 54.4 s per simulation;
  - no innate runs in the market experiment;
  - encoder code for the new rule.
- **Invalidates the running validation?** Not as a record. But it validates a
  different encoder, so the market experiment would need the new validation
  instead.
- **Post-hoc or new runs:** new runs. The stimuli differ.

### 3.3 Accept the confound and report the drive term as a covariate

- **Fixes:** nothing. It documents the confound: `D_YES − D_NO` is recorded with
  every decision.
- **Limit:** the covariate is a **deterministic function of the mirrored feature
  values**:

  ```text
  D_YES − D_NO = Σ over mirrored features of 100 · [r_f(x) − r_f(mirror of x)]
  ```

  Only price varies in the graded sweep, so there it is perfectly collinear with
  the value. In the market experiment it is collinear with the mirrored features'
  values. It **cannot be regressed out** without removing the value signal it
  co-varies with. Reporting it is transparency, not adjustment.
- **Consequence:** an innate, value-dependent term of about −35(2v−1) Hz
  (inferred, §2.4) is present at every decision. Learning has to be read against
  it.
- **Simulation cost:** none.
- **Invalidates the running validation?** No. It is the running validation's own
  encoder.
- **Post-hoc or new runs:** post-hoc. The drive term is computable exactly from
  saved stimuli.

### 3.4 Model-based drive adjustment of the readout

```text
S_adj(v) = S(v) − [ĝ(D_YES) − ĝ(D_NO)]
```

Here `ĝ` is a drive-to-score calibration curve estimated from stimuli that change
drive **through non-price KCs**.

- **Fixes:** it removes the modelled generic-intensity part of `S`. The residual
  is the part specific to which KCs carry the value.
- **Leaves or risks:**
  - `ĝ` estimated from the price sweep itself makes `S_adj ≡ 0` by construction,
    so it must come from elsewhere;
  - existing non-price calibration rests on two balanced points and a ladder
    whose slopes vary from −3.1 to −4.5 Hz/kHz with manipulation and operating
    point, so the adjustment would be uncertain by tens of percent;
  - if §2.2's reading holds, `S_adj` would be near zero at baseline, as in §3.2.
- **Simulation cost:** none using existing points. A proper calibration curve
  (non-price pools swept across 40–60 kHz) would take roughly 20–30 simulations,
  as a planning figure, not derived.
- **Invalidates the running validation?** No. It is the **only option that can be
  applied to the running validation's saved data**, since `D_YES` and `D_NO` are
  known exactly. A verdict on `S_adj` would be a new test, analysis-only with no
  simulations, and would have to be pre-stated **before** the running
  validation's verdict is seen. Otherwise it is post-hoc.

### 3.5 Pool-identity control (a measurement, not a mitigation)

Run the §1 counterfactual directly:

- present the same five rate changes on a **non-price** 100-KC pool of the same
  500, with price held at 90 Hz;
- or swap which pool carries the price value.

- **Fixes:** nothing directly. It answers the question existing data cannot
  (§2.4): whether `S` is generic intensity or pool-specific. That also predicts
  whether §3.2 or §3.4 would leave any signal.
- **Simulation cost:** 30 simulations YES-only (5 values × 6 seeds, like the
  realistic-drive diagnostic), about 27 minutes; or 60 for a mirrored pair.
- **Invalidates the running validation?** No.
- **Post-hoc or new runs:** new runs.

### Summary

| option | removes drive term | sims (graded) | market-experiment cost | running validation still covers the market encoder | on saved data |
|---|---|---:|---|---|---|
| 3.1 innate subtraction | at baseline; 2nd-order term remains | 0 | + innate runs per decision | yes | graded: trivially 0; market: needs runs |
| 3.2 per-framing drive match | exactly | 60 | none extra | no, needs new validation | no |
| 3.3 accept + covariate | no | 0 | none | yes | yes |
| 3.4 model-based adjustment | modelled part | 0 (or ~20–30 to calibrate) | none | yes, if pre-stated before verdict | yes |
| 3.5 identity control | n/a (measurement) | 30–60 | none | yes | no |

## 4. Re-examining the objection to innate-score subtraction

**The recorded objection** (`balanced-encoding-failure.md` §4c): at baseline
weights the innate-subtracted score is identically zero for every value, so a
graded test cannot be run on it. It follows that the graded test validates the
raw contrast while the market experiment reads the mitigated one.

### 4.1 The identity still holds

For weights `W`, seed `s` and CIRCUIT readout `C_W`:

```text
S(v; W)     = C_W(m(x_YES(v); W)) − C_W(m(x_NO(v); W))
s_mit(v; W) = S(v; W) − S(v; W₀)
at W = W₀:  s_mit(v; W₀) = S(v; W₀) − S(v; W₀) = 0      for every v
```

This is an identity. It holds for any encoder, mirrored or not, shared pools or
not, as long as the innate and decision presentations share the seed. **The
objection's arithmetic is still correct:** a graded test on `s_mit` at baseline
weights would return zero at every value. The exploration-rule consequence (an
exact tie at every decision before learning) also still holds.

### 4.2 What mirroring with shared, unbalanced pools adds

Two exact properties, and one first-order property:

1. **Exact antisymmetry at any `W`.** `NO(v) ≡ YES(1−v)` holds for the stimulus,
   independently of `W`. So at a shared seed, `S(1−v; W) = −S(v; W)` for all `W`,
   and therefore

   ```text
   s_mit(1−v; W) = −s_mit(v; W)     and     s_mit(0.5; W) = 0      for every W
   ```

   `s_mit` is exactly odd in `(2v − 1)`.
2. **The input difference is confined to the price pool.** With a midpoint
   background and no balance pool:

   ```text
   x_YES(v) − x_NO(v) = 120 (2v − 1) · 1_price
   ```

   Here `1_price` is 1 on the price pool's 100 KCs and 0 elsewhere. (In the
   balanced encoder this difference also had balance-pool entries. With mirrored
   features off their midpoints, every mirrored feature's pool has entries.)
3. **First order in learning.** Write the MBON response as
   `m(x; W) ≈ m(x; W₀) + J(x) ΔW x`, where `ΔW` is the change in KC→MBON weights
   and `J(x)` is the MBON gain at operating point `x`. Then

   ```text
   s_mit(v; W) ≈ C[ J(x_YES) ΔW x_YES − J(x_NO) ΔW x_NO ]
   ```

   If the two framings share a gain, `J(x_YES) ≈ J(x_NO) = J̄`:

   ```text
   s_mit(v; W) ≈ C J̄ ΔW (x_YES − x_NO) = (2v − 1) · K,
   K = 120 · C J̄ ΔW 1_price
   ```

   `K` is a single value-independent scalar, set by what learning did to the
   **price-pool** KC→MBON synapses only.

### 4.3 Where the drive confound re-enters

The framings do not share a gain exactly, because their drives differ by
`12,000 (2v − 1)` Hz. The residual term is

```text
C[ (J(x_YES) − J(x_NO)) ΔW x̄ ]
```

where `x̄` includes the shared background pools. It couples learning on
**non-price** synapses to the drive difference. It is also odd in `(2v − 1)`, so
it preserves the antisymmetry, but it is not specific to the price pool.

**Size (inferred, crude proxy).** Using the local score slope as a stand-in for
gain, the slopes at the two framings' drives at `v` = 0.94 (39.7 and 50.3 kHz) are
−3.14 and −2.66 Hz/kHz: about a **15% gain difference**. The score slope is not
`J`, so this gives the order of magnitude only.

### 4.4 Verdict on the objection

- **Its arithmetic stands** (§4.1). The graded test cannot be run on `s_mit`, and
  before learning every decision is a tie.
- **Its conclusion can be narrowed** under mirroring with shared, unbalanced
  pools:
  - The mitigated score's value structure is fixed by the encoder, not by
    learning. It is exactly odd, and to first order it is `(2v − 1)` times a
    learned scalar `K`.
  - The input difference that `K` multiplies, `x_YES − x_NO`, is exactly the one
    whose transmission to an above-noise, monotone MBON contrast the running
    graded test checks. So the gap is not "a different quantity". It is **the
    same input difference passed through a learned gain the test cannot see**.
  - Because `K` depends only on the price pool's KC→MBON weights, the learned
    term is price-pool-specific **even if** the innate scalar is dominated by
    generic drive (§2).
- **What the graded test still does not validate:**
  - the size or sign of `K`;
  - linearity beyond first order;
  - the gain-coupling term (§4.3);
  - the four-presentation noise of `s_mit`.

The objection is **correct but weaker than recorded**. It remains a validation
gap. It is not grounds for treating the graded test as irrelevant to the
mitigated readout.

## 5. Ordering constraint

Any mitigation is applied **after** the running validation. §3.4 is the one
option that could be tested on that validation's saved data. It must be
pre-stated before that validation's verdict is inspected, or it becomes a
post-hoc analysis and must be labelled as one. No option here is recommended.
