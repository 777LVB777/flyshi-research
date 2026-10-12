# Phase 2: real binary prediction markets (historical replay)

**DRAFT, 2026-10-11. Nothing in this file is decided.** Every choice below is a
proposal awaiting project-owner sign-off. The open decisions are listed in
Section 9.

- **Venue.** The design is venue-neutral. Kalshi is blocked pending written
  permission ([`open-decisions.md`](open-decisions.md), item 6, revision
  2026-10-11). No venue is chosen.
- **What was done.** No market data has been downloaded, no simulation was run,
  and nothing is committed.
- **Unverified figures.** Every figure marked **unverified** comes from
  documentation or arithmetic. None comes from data or from a model run.

**Fixed, from the synthetic sweep and not reopened here:**

- the ACCEPTED encoder (left-only mirrored graded encoding, rates 30–150 Hz,
  `pool_size` 100, `pool_seed` 20260401);
- the CIRCUIT-80 per-type-mean readout with no mitigation;
- the locked learning-rule and reward parameters;
- the profit reward;
- 1000 ms × 5 trials per framing;
- YES and NO framings per decision. A decision is therefore 2 simulation runs.

**Scope.** This is a historical replay only. There is no live trading and no
money, and no order is ever placed on any venue.

**Budget.** About $100 of compute on one Hetzner CCX33. The measured throughput
is 213 runs/h at 4 processes, and the price is $0.266/h. So $100 buys at most
about 80,000 runs, or 40,000 decisions, with no contingency left.

## 1. Venue terms review (2026-10-11)

Each venue was checked for the same eight questions:

- bulk download;
- storage;
- analysis;
- use with a learning model;
- publication;
- sharing data with reviewers;
- redistribution;
- whether an account or key is needed.

Terms were read from the venues' own pages on 2026-10-11. Clause summaries are
paraphrases, and the venue's wording governs. "Unclear" means the text does not
settle the question. Those items need the venue's written answer, not an
interpretation.

| venue | money | binary markets with resolved outcomes | history (rough, **unverified**) | verdict |
|---|---|---|---|---|
| Kalshi | real (USD, CFTC-regulated) | yes | 2021– | **blocked** pending written permission (open-decisions item 6) |
| Polymarket (polymarket.com) | real (USDC) | yes | 2020– | **usable with conditions**; written confirmation advised |
| Iowa Electronic Markets | real (small stakes) | yes, but few (winner-takes-all markets) | 1988– | **unclear**: no data terms found |
| PredictIt | real (USD, $3,500 cap per contract) | yes (each contract is binary) | 2014– | **blocked** without written permission |
| Metaculus | none (not a market) | resolved binary questions, community forecasts, no prices | 2015– | **blocked** without written permission; poor fit |
| Manifold Markets | play money (mana) | yes, many | Dec 2021– | **usable with conditions** (non-commercial; written confirmation advised) |

### Polymarket: usable with conditions

**Source.** Polymarket.com Terms of Use, effective 11 August 2026. The text is
served from a Google Doc embedded at `polymarket.com/tos`. The SHA-256 of the
plain-text export is
`0506de1ebf824b1827dfef90828f0e78f45d9defa63241ac91f1ed2c0ee2847d`.

- **Bulk download.** The prohibited-use list in §4 bans data-mining tools,
  robots, crawlers and scrapers that remove data from the Site, an Interface or
  the Features. It also bans harvesting information "for any unauthorized
  purpose". The opening notice counts connecting via an API as use of the
  Features. Whether bulk retrieval through the official public API counts as
  scraping is **unclear**.
- **Storage, analysis and use with a learning model.** No clause addresses these.
  There is no machine-learning or AI clause.
- **Publication.** No clause restricts it.
- **Redistribution and sharing with reviewers.** §4 prohibits two things unless
  Polymarket agrees in writing:
  - any access to or use of the data, including on-chain data, by "Capital Market
    Clients" or market-data distributors;
  - reselling or redistributing the data to such parties.

  A research project is neither. Ordinary sharing with reviewers is not
  addressed. §5.1 grants only a personal, limited licence to the Site and
  Features. That leaves redistributing a dataset **unclear**.
- **Account or key.** Read-only market data reportedly needs no key. That comes
  from third-party guides and is **unverified** against the official docs.
- **Location.** Trading is blocked for U.S. persons. People in restricted
  jurisdictions may use only the "Content Features", meaning information. A
  replay does not trade. The browser used for this review was shown the U.S.
  notice.
- **On-chain data.** Trades and resolutions settle on the Polygon blockchain,
  which is public. The terms mention on-chain data only in the Capital Market
  Client clause.
- **Conditions:**
  - use the official public API, or public chain data, within the published
    rate limits;
  - no trading;
  - no redistribution to commercial or market-data parties;
  - ask for written confirmation that bulk research retrieval through the API is
    not "scraping".
- **Not reviewed.** Polymarket US (`polymarket.us`, the CFTC-regulated U.S.
  exchange) has separate terms, which were not reviewed.

### Iowa Electronic Markets (IEM): unclear

- **What exists.** The University of Iowa (Tippie College) runs the IEM as a
  real-money market for research and teaching. It publishes historical-data
  pages covering 1988–1996 and 1998 onward.
- **Terms.** No data terms of use, licence or citation rule was found on the
  About, Research, FAQ or historical-data pages. The FAQ points questions to
  `iem@uiowa.edu`.
- **Fit.** Few markets qualify. The winner-takes-all binary markets are
  presidential, congressional control and Federal Reserve policy markets, so a
  few hundred contracts at most (**unverified**). That is far short of 40,000
  decisions, unless one contract is sampled on many days, which gives correlated
  decisions.
- **Verdict.** Unclear. The best use is a small out-of-sample replication, and
  only after the IEM answers in writing.

### PredictIt: blocked

**Source.** Terms and Conditions read at `predictit.org/terms-and-conditions`;
no date shown.

- **Bulk download and scraping.** The impermissible-conduct clause forbids manual
  or automated processes that scrape or extract data from the website.
- **Other uses.** The same clause forbids using the site's data for any
  commercial purpose, "or any use other than its intended use as a way to
  participate in the Services".
- **Copying and distribution.** The intellectual-property clause forbids copying,
  reproducing, transmitting or distributing the data.
- **Account.** Trading needs an account, and participation is limited to U.S.
  persons.
- **Research route.** PredictIt describes itself as a research facility of an
  academic consortium (PMRC). Asking for data access is the only route.

### Metaculus: blocked, and a poor fit

**Source.** Terms of Use, last modified 21 September 2026.

- **What the terms forbid:**
  - automated retrieval, except through a Metaculus API under its terms;
  - copying, downloading, republishing or distributing content without written
    permission;
  - using the Service, its content or user content to train or develop any AI or
    machine-learning model or algorithm without prior written permission.
- **Fit.** Metaculus questions have community forecasts and points, not traded
  prices or money. "Beating the market price" has no direct analogue.

### Manifold Markets: usable with conditions

**Sources.** Terms of Service, last updated 31 January 2026; the API
documentation; the Data page.

- **Bulk download.**
  - The API documentation says academic research, personal projects and
    non-commercial use are permitted.
  - Official dumps exist for personal and non-commercial use:
    - markets, about 87 MB;
    - bets/trades, about 967 MB;
    - comments.

    They cover December 2021 to July 2024. Later data would come through the API.
  - Automated access is allowed only through the public API, with a rate limit of
    500 requests per minute per IP. Read endpoints need no key.
- **Conflict in the terms.** §8 forbids systematically retrieving data to build a
  database without written permission. That conflicts with the API statement and
  the published dumps. **Unclear**; ask `data@manifold.markets` for written
  confirmation.
- **Learning model.** §8 restricts AI/ML training only for commercial purposes,
  and states that academic research and non-commercial use are permitted.
- **Publication.** No clause forbids publishing results.
- **Redistribution and sharing with reviewers.** §2 forbids reproducing or
  redistributing content for commercial purposes. Non-commercial sharing of a
  derived dataset with reviewers is **unclear**.
- **Fit.** Play money. Results would show what the circuit does on a play-money
  market. They could not be claimed for real-money markets.

## 2. The decision unit

- **One decision per market.** Each selected market is presented once, at one
  pre-stated decision time `t_d`, as a YES and a NO framing. That mirrors the
  synthetic sweep. Several snapshots of one market would be strongly correlated,
  and the bootstrap would have to cluster them.
- **When `t_d` falls (open decision D3):**
  - *(a) Fixed horizon:* `t_d` = scheduled close minus H days, for example
    H = 7. This is simple and comparable, but `time_to_resolution` is then
    almost constant and carries no information.
  - *(b) Seeded random time:* `t_d` drawn uniformly over the market's tradable
    life, excluding the first 24 h and the last 24 h before scheduled close. The
    draw is seeded from the market ID and fixed before any outcome is looked up.
    The time feature then varies. **Recommended.**
- **Outcome.** The venue's final binary resolution.
- **Excluded.** Voided, cancelled and N/A markets are excluded and counted (see
  Section 5).

## 3. Feature mapping for a generic binary market

All features use only information timestamped at or before `t_d`.

| encoder feature | generic real-market definition | range in `FeatureSpec` | notes |
|---|---|---|---|
| `price` | mid of best YES bid and ask at `t_d`; fall back to last trade if no two-sided quote within a pre-stated staleness limit | [0, 1], mirrored | Kalshi quotes cents; Polymarket and Manifold quote probabilities. Record which source was used for each market. |
| `recent_change` | `price(t_d) − price(t_d − w)`, the within-market change over a fixed window w (for example 24 h or 7 d) | [−1, 1], mirrored | This is Proposal B, deferred from the synthetic sweep. If the market is younger than w, use its first price (open decision). |
| `time_to_resolution` | days from `t_d` to the **scheduled** close as known at `t_d` | [0, 365], not mirrored | Never the actual resolution time: an early resolution would leak the outcome. Markets longer than 365 days are clipped, and the encoder reports it. |
| `liquidity` | trailing volume (or open interest) over a fixed window before `t_d`, as log1p, then mapped to [0, 1] by quantiles fitted **on training markets only** | [0, 1], not mirrored | The normalisation is still a placeholder. Fitting it on all markets would leak test information. |
| `signal` | see Section 4 | [0, 1], mirrored | In the "no signal" option, hold it at 0.5, which is 90 Hz in both framings. Do not omit it. |

**Why hold the signal at 0.5 rather than omit it.** In the encoder, an omitted
optional feature leaves its pool undriven. That lowers total drive below every
validated stimulus, and no mitigation is in force. A constant 0.5 keeps the drive
in the validated regime. It carries no information, and it is identical under
YES and NO because 0.5 mirrors to itself.

**Pre-run drive check (arithmetic only, no simulation).** Before any run, encode
the training markets' features and compute per-framing total drive and the
YES−NO drive difference. Compare them with the synthetic sweep's range:
22.8–67.5 kHz, with 2.12% above 60 kHz. Real feature distributions differ, for
example many short-dated markets. If more presentations land in the high-drive
region, ignition will be more frequent than in any validated condition. Report
this, and get sign-off before running.

## 4. The signal: options and what each lets the paper claim

| option | what it is | pros | cons | the paper could claim | the paper could not claim |
|---|---|---|---|---|---|
| **(a) No signal** (price history only) | signal fixed at 0.5; the circuit sees price, recent change, time and liquidity | No second source or second set of terms. Simplest. Same features as any trader sees. | Real markets are close to efficient. Any edge comes only from price-history patterns, such as the favourite-longshot bias, so a null result is likely and expected. | "A connectome-constrained circuit with dopamine plasticity does / does not beat the venue's own price from price-history features" | Anything about integrating outside evidence. The synthetic signal requirement cannot be tested. |
| **(b) Cross-venue price** | the same event's price on a second venue at `t_d` | Real evidence that is outside the venue's own price. Directly tests whether the circuit uses a second opinion. | Needs event matching across venues: fewer markets (hundreds to low thousands, **unverified**) and two sets of terms (Kalshi is blocked). The two prices are highly correlated, so the edge is mostly cross-venue lag or arbitrage. Matching errors add noise, and matching must be done blind to outcomes. | "The circuit learns to weight a second venue's price beyond the first venue's price" | That it uses fundamental information. Any edge may be lead-lag. |
| **(c1) Public-domain external forecast** | for example U.S. National Weather Service forecasts for weather markets. U.S. federal works are generally public domain (**verify** for the product used). | Clean terms. Genuinely external evidence, released at known times. | Only one market family, so the result is narrow. Forecast archives must exist for `t_d`. Weather markets mostly resolve on numeric thresholds, which need mapping to a probability. | "The circuit integrates an external forecast with price in [category]" | Generality across categories. |
| **(c2) Same-venue order flow** | for example signed trade imbalance over a window before `t_d` | No extra source, so the same terms. | Not independent of price. Close to a second price-history feature. | Same as (a), plus "order flow adds / does not add" | Outside evidence. |
| **(d) Placebo signal** (control only) | another market's price at the same time, assigned by a seeded permutation | The real-data analogue of strength 0: a matched null with the same marginal distribution | Not a signal option on its own | Used only as a null control for (b) or (c) | — |

**Recommendation (draft).**

- **Primary:** (a), on the venue chosen.
- **Secondary arm, if budget allows:** (c1) or (b), each with (d) as its null.

**What (a) cannot do.** The synthetic sweep's signal requirement cannot be
transferred to real markets under (a). The paper's claim would be about price
efficiency only.

## 5. Market selection, look-ahead and survivorship

### Selection criteria (proposed; every threshold is an open decision)

1. **Binary only.** One YES/NO contract per market. A multi-outcome event is
   included as **one** contract per event, chosen by a pre-stated rule decided
   at `t_d`, for example the contract nearest 0.5. That avoids several dependent
   markets per event.
2. **Resolved** with a final YES or NO. Voided, cancelled, N/A and disputed
   markets are excluded and counted, by category and period. Polymarket disputes
   are noted but use the final resolution.
3. **Date range.** Fixed in advance, for example markets whose `t_d` falls in a
   stated 2–3 year window. One global split time `T_s` separates training from
   test (rule 7).
4. **Liquidity at `t_d`.**
   - A two-sided quote within the staleness limit at `t_d`.
   - At least N trades or V volume in the trailing window before `t_d`.
   - Never lifetime volume: that is known only after the fact.
5. **Categories.** Either all categories, with category recorded and reported,
   or a pre-stated list. Very short-dated, repetitive series (for example
   15-minute crypto up/down markets) are capped per series, or excluded, so they
   cannot dominate the sample.
6. **Frozen list.** The selection script runs on metadata only, writes the market
   list with a SHA-256 hash and is committed before any price or outcome is fed
   to the circuit.

### Look-ahead safeguards

7. **Global time split with an embargo.**
   - Training markets are those **resolved** before `T_s`.
   - Test markets are those with `t_d` ≥ `T_s` + embargo, for example 7 days.
   - So no test decision is made before a training outcome the circuit has
     learned from. That is what a trader at `t_d` could know.
8. **Training order.** Training markets are presented in order of resolution
   time. Test markets are presented in order of `t_d`, with weights frozen.
9. **Only data from before `t_d`.** Every feature uses data timestamped at or
   before `t_d`, with the venue's own timestamps in UTC. The scheduled close used
   is the one known at `t_d`; if metadata history is unavailable, use the
   original listing value and flag any change. The liquidity quantiles, the
   calibrator and the comparator choice are fitted on training markets only.
10. **Signals.** Signal values are from before `t_d` too. Event matching for
    option (b) uses titles and rules only, is done blind to outcomes, and is
    frozen with the list.
11. **No outcome-derived selection.** No criterion may use the outcome, the final
    price or the resolution date.

### Survivorship safeguards

12. **Archived markets.** The universe must include delisted and archived
    markets. For Kalshi this meant the `/historical/` endpoints and the archive
    cutoff (open-decisions item 6). For Polymarket and Manifold, closed and
    archived markets must be queried explicitly.
13. **Counts at every step.** From the raw universe through each filter to the
    final list, by category and by period, in the results.
14. **Excluded voided markets.** Their count and categories are reported, because
    voiding can correlate with surprising events.

### How many usable markets exist

**Not estimated from data.** Counting needs at least a metadata query, which is
a download, and none is allowed yet. Rough, **unverified** orders of magnitude:

- **Polymarket:** tens of thousands of resolved markets. Many are short-dated
  crypto and sports series, so per-event and per-series caps will cut this
  substantially.
- **Manifold:** over 100,000 binary markets, many with very low play-money
  liquidity.
- **IEM:** hundreds of contracts at most.

**First step once terms are cleared:** a metadata-only count, with no prices,
reported against criteria 1–5, before sizing is fixed.

## 6. Arms, comparator, null control and gate

**Proposal.** The same structure as the synthetic gate, adapted to real data.

### Arms

| arm | role |
|---|---|
| `profit` | primary; plasticity on during training, frozen at test |
| `learning_off` | the learning control ("learning effect, any source") |
| `null_permuted` | null control: the profit arm trained on **outcomes permuted** across that chain's training markets with a fixed seed. Real data has no strength 0; this is its analogue. A pass here means a pipeline problem, not a finding. |
| (optional) `profit_placebo` | with signal options (b) or (c): the profit arm with signal replaced by the placebo (d) |

### Comparator

Real markets have no "exact price-only posterior", so the comparator is one of:

- **(i)** the raw price at `t_d`;
- **(ii)** the training-fitted Platt calibration of price;
- **(iii)** whichever of (i) and (ii) has the lower Brier score on **training**
  markets, chosen before any test market is scored. **Recommended.**

The synthetic sweep showed that Platt calibration can be worse than the raw
price at clipped extremes. Hence option (iii) rather than always (ii).

### Gate (unchanged in form)

Paired Brier improvements of `profit` over the comparator, and of `profit` over
`learning_off`, on held-out markets. Both use 95% percentile bootstrap intervals
with 2,000 resamples. Resampling is **by event**: by market if criterion 1
leaves one market per event. Both lower bounds must be strictly above zero.

- **If `null_permuted` passes the market comparison,** the verdict is
  `NULL CONTROL FAILED`.
- **Reported, never gating:**
  - profit by price region;
  - P&L after the venue's real fee schedule and the spread observed at `t_d`;
  - the ignited-market exclusion sensitivity, as in the synthetic sweep;
  - all baselines (Section 5 of the synthetic spec).
- **Not gating.** The synthetic result is never pooled with the real result.

## 7. Sizing and power (~80,000 runs at most)

### Chain shape

Keep the synthetic chain shape: **250 markets per chain, 70 training and 180
test.** The training length then equals the length at which learning was
demonstrated.

- **Training markets:** each chain draws its 70 from the pre-`T_s` pool.
- **Test markets:** each chain draws its 180 from the post-`T_s` pool.
- **Assignment:** a seeded hash of market ID. Chains are disjoint, so every
  market appears in exactly one chain, in every arm.
- **Jobs:** one job = one (chain, arm) = 500 runs, about 9.4 h at 4 processes.
  That matches the launcher's current job size.

### Run count, time and cost

At 213 runs/h and $0.266/h, server time only:

| design | arms | chains | distinct markets | test markets | runs | hours | days | cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| P (pilot) | 2 | 10 | 2,500 | 1,800 | 10,000 | 47 | 2.0 | $12.49 |
| **A (recommended)** | 3 (`profit`, `learning_off`, `null_permuted`) | 40 | 10,000 | 7,200 | 60,000 | 282 | 11.7 | **$74.93** |
| B | 2 | 70 | 17,500 | 12,600 | 70,000 | 329 | 13.7 | $87.42 |
| C (ceiling) | 2 | 80 | 20,000 | 14,400 | 80,000 | 376 | 15.6 | $99.91 |

- **Why A.** It leaves about $25 for setup, calibration, idle hours and one
  restart. Phase 1 showed there is otherwise no contingency.
- **What C costs.** C spends the whole budget and has no null control.
- **Constraint.** A and B need 10,000–17,500 distinct qualifying markets, one per
  event, which is plausible only on Polymarket or Manifold (**unverified**).
- **Signal options (b) or (c).** These yield fewer markets. A then becomes, for
  example, 12 chains × 4 arms (`profit`, `learning_off`, `null_permuted`,
  `profit_placebo`) = 24,000 runs, about $30. Its power is in the 3,600 row of
  the table below, scaled down to 2,160 test markets.

### Power (same method as the synthetic power design)

- **Formula.** For a paired Brier difference with per-market standard deviation
  σ_d, the minimum detectable effect at 80% power and two-sided α = 0.05 is
  **MDE = 2.80 · σ_d / √n_test**. The gate's lower bound above zero is
  approximately a one-sided test at 0.025.
- **What σ_d depends on.** It is set by how far the learner moves from the
  comparator: d = (p − q)(p + q − 2y), so σ_d ≈ 0.9 × RMS(p − q).
- **Anchors from the synthetic power figures** (ground-truth arithmetic,
  synthetic spec Section 1 revision):
  - the ideal forecaster at strength 0.4 implies σ_d ≈ 0.034, a forecast moving
    about 0.04 from price;
  - at strength 1.0 it implies σ_d ≈ 0.090, about 0.10 from price.

| n_test | MDE, σ_d = 0.02 | σ_d = 0.034 | σ_d = 0.06 | σ_d = 0.09 |
|---:|---:|---:|---:|---:|
| 1,800 (P) | 0.0013 | 0.0023 | 0.0040 | 0.0059 |
| 3,600 | 0.0009 | 0.0016 | 0.0028 | 0.0042 |
| 7,200 (A) | 0.0007 | 0.0011 | 0.0020 | 0.0030 |
| 12,600 (B) | 0.0005 | 0.0009 | 0.0015 | 0.0023 |
| 14,400 (C) | 0.0005 | 0.0008 | 0.0014 | 0.0021 |

**Reading the table:**

- **A circuit that moves far from the price needs a large edge.** At σ_d of
  0.06–0.09, design A can detect a Brier edge of 0.002–0.003. Real-market edges
  over the price are probably smaller than that (**unverified**).
- **One that stays close to the price is cheaper to detect.** At σ_d ≈ 0.034, A
  detects 0.0011.
- **Real markets offer no known edge.** No ground truth gives an "ideal edge", so
  only MDEs can be pre-stated.
- **Pre-stated interpretation.** A non-pass under any design means "no edge
  larger than the MDE at the realised σ_d". It does not mean "no edge". Report
  the realised σ_d next to the verdict.
- **Clustering.** Clustered resampling (by event or by series) inflates σ_d.
  Criterion 1 is there to keep the clusters at size 1.

## 8. Schedule and operations

- **Runner.** Same as the synthetic sweep: `launch_*_parallel.py` style, 4
  processes, `--gb-per-proc 3.6`, job-granular restart, and a pre-launch
  `server_eta.py`-style estimate.
- **New code needed** (not written):
  - a data loader for the chosen venue;
  - feature construction (Section 3);
  - market selection and freezing (Section 5);
  - a replay job runner taking a frozen market list;
  - comparator and gate code for real data;
  - fake-verdict tests, as in the synthetic spec.
- **Order of work:**
  1. terms cleared in writing;
  2. metadata count;
  3. frozen list;
  4. drive check;
  5. sizing fixed;
  6. pre-statement committed;
  7. runs.
- **Budget.** Phase 1 runs until about 2026-10-27, so Phase 2 compute would
  start after that. The $100 total cannot absorb a second server running in
  parallel.

## 9. Open decisions for the project owner

1. **Venue:**
   - Polymarket (real money; terms usable with conditions);
   - Manifold (play money; non-commercial use permitted, conflict in §8);
   - wait for Kalshi's answer;
   - or IEM as a small replication only.
2. **Written confirmations.** Whether to request them from Polymarket and
   Manifold before any download, and whether to send the drafted Kalshi request
   ([`kalshi-permission-request-DRAFT.md`](kalshi-permission-request-DRAFT.md)).
3. **Decision time `t_d`:** fixed horizon H, or seeded random time within the
   market's life (recommended).
4. **Feature parameters:**
   - price source (mid or last trade) and the staleness limit;
   - the `recent_change` window w;
   - the liquidity measure and window;
   - the clip for markets longer than 365 days.
5. **Signal option:** (a), (b), (c1) or (c2), and whether the placebo arm runs.
6. **Selection thresholds:**
   - date range and split time `T_s`;
   - embargo length;
   - minimum liquidity at `t_d`;
   - category list and per-series caps;
   - the one-contract-per-event rule.
7. **Comparator:** raw price, Platt price, or the training-chosen better of the
   two (recommended).
8. **Null control:** the `null_permuted` arm (recommended), the placebo, or
   neither.
9. **Design size:** P, A (recommended), B or C, and the contingency kept.
10. **Data handling:**
    - whether derived features, the market list and IDs may be published or
      shared with reviewers. That depends on the venue's answer;
    - where raw data is stored;
    - and that it is never committed to the repository.
11. **Fees and spread** for the reported P&L: the venue's real schedule and the
    spread observed at `t_d`, or the synthetic placeholders.
12. **Reporting.** Whether the play-money result (if Manifold) is reported as a
    separate claim. The recommendation is yes, and never pooled with real-money
    results.

*Sources read for Section 1, all on 2026-10-11:*

- `polymarket.com/tos` (Google Doc export);
- `predictit.org/terms-and-conditions`;
- `metaculus.com/terms-of-use/`;
- `docs.manifold.markets/terms`, `/api` and `/data`;
- `iemweb.biz.uiowa.edu`: About, Research, FAQ, Historical Data and Recent
  Markets;
- the Kalshi documents as listed in open-decisions item 6.
