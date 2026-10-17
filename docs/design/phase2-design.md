# Phase 2: real binary prediction markets (historical replay)

**DRAFT, 2026-10-11. Nothing in this file is decided.** Every choice below is a
proposal awaiting project-owner sign-off. The open decisions are listed in
Section 9.

- **Venue.** Kalshi is blocked pending written permission
  ([`open-decisions.md`](open-decisions.md), item 6, revision 2026-10-11).
  **Update 2026-10-12:** Polymarket is *planned* as primary under the conditions
  in Section 1, with Manifold as backup (item 6, revision 2026-10-12). It is not
  final, because the support reply behind it is not definitive. On 2026-10-12
  the owner chose option (i): CLOB `/prices-history` is allowed alongside Gamma
  under the same conditions, pending Polymarket's confirmation (Section 1). The
  rest of the design stays venue-neutral.
- **Update 2026-10-14.** Polymarket support answered the follow-up (item 6,
  revision 2026-10-14). Condition 7 (publication and reviewer sharing on hold)
  is cleared. Condition 6 stands. CLOB `/prices-history` remains unpermitted
  pending an answer to a question sent 2026-10-14 (Section 1).
- **Update 2026-10-12 (later).** Decisions on signal, comparator, liquidity and
  size, a draft Polymarket loader, and three proposals awaiting confirmation are
  in Section 10. Section 10 governs where it differs from earlier sections.
- **Update 2026-10-16.** The Gamma metadata count is done: 40,893 qualifying
  markets, one per event, at ≥ $10,000 (Section 10.10). Proposals for the
  cutoff, the sample and the threshold, **not adopted**, are in Section 10.11.
- **What was done.** No market data has been downloaded and no simulation was
  run. (Update 2026-10-16: Gamma market **metadata** only has now been
  downloaded, under the Section 10.9 permission. No price history has been
  downloaded, and no simulation has been run.)
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
| Polymarket (polymarket.com) | real (USDC) | yes | 2020– | **usable with conditions**; planned primary 2026-10-12 (see conditions below); support reply not definitive |
| Iowa Electronic Markets | real (small stakes) | yes, but few (winner-takes-all markets) | 1988– | **unclear**: no data terms found |
| PredictIt | real (USD, $3,500 cap per contract) | yes (each contract is binary) | 2014– | **blocked** without written permission |
| Metaculus | none (not a market) | resolved binary questions, community forecasts, no prices | 2015– | **blocked** without written permission; poor fit |
| Manifold Markets | play money (mana) | yes, many | Dec 2021– | **usable with conditions** (non-commercial; written confirmation advised); backup |

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

#### Polymarket support reply and binding conditions (2026-10-12)

**The support reply.** On 2026-10-11, a human member of Polymarket support
answered after the AI agent "Polybot" handed the request over. The transcript is
recorded verbatim in [`open-decisions.md`](open-decisions.md), item 6, revision
2026-10-12. The reply supports the planned use:

- the Gamma API is public, unauthenticated, and intended for read-only use,
  including non-profit research;
- the documentation states no restriction on bulk retrieval within rate limits,
  on private storage, or on use with learning models.

The reply is **not a definitive written confirmation**. It does not address
attribution, publication or sharing with reviewers. The owner sent a follow-up
on 2026-10-12. It asks about publication and reviewer sharing.

**Update 2026-10-14.** The text above earlier said the 2026-10-12 follow-up also
asked about CLOB `/prices-history`. The verbatim message shows that it did not.
Roni, the same human support agent, answered on 2026-10-13 (transcript in
[`open-decisions.md`](open-decisions.md), item 6, revision 2026-10-14):

- publishing aggregate results crediting Polymarket: no objection, and credit
  is encouraged;
- sharing market IDs and other reproducibility metadata with peer reviewers and
  editors: "completely fine";
- stated limit: no re-distributing or reselling the raw API bulk dataset as
  one's own commercial product.

A one-line question about `GET clob.polymarket.com/prices-history` was sent on
2026-10-14. It is **PENDING**.

**Conditions on any Polymarket use (project owner, 2026-10-12).** Each is
binding on the data-retrieval code and its run log:

1. **Allowed endpoints** (amended 2026-10-12, option (i)):
   - the Gamma API (`gamma-api.polymarket.com`);
   - **and** the CLOB price-history endpoint `GET
     clob.polymarket.com/prices-history`, nothing else on the CLOB host.

   This is *pending Polymarket's confirmation* that the support reply also
   covers `/prices-history`. That was asked on 2026-10-14 (not in the
   2026-10-12 follow-up, as first written here). Until it is answered,
   `/prices-history` is unpermitted and no permission file for it is written. If
   Polymarket says no, `/prices-history` is dropped and the owner revisits
   option (ii).

   Not allowed: any other Polymarket API (Data API, other CLOB endpoints,
   including the POST `/batch-prices-history`), website scraping, or chain
   indexing. Conditions 2–8 apply to both endpoints.
2. **Read-only.** Only GET requests, except where a read-only endpoint is
   documented as POST, such as a batch read. Nothing is created, changed or
   submitted.
3. **Unauthenticated.** No account, no API key, no wallet, no signature, no
   cookies or session.
4. **Within published rate limits.** A pre-stated request rate below the limit,
   backoff on HTTP 429, and a request log kept with the run record.
5. **No interaction with the platform or contracts.** No orders, no trading, no
   transactions, no on-chain calls.
6. **No public redistribution of raw data.** Raw responses stay in private
   storage. The repository and any public release contain only code, the frozen
   hashed market-ID list and aggregate results. Public release of market IDs
   and derived per-market features waits for the follow-up answer.
   **Stands (2026-10-14).** The 2026-10-13 reply did not address public release
   of market IDs or derived features; it cleared sharing with reviewers and
   editors only (condition 7). Polymarket's own stated limit, no commercial
   redistribution or resale of the raw bulk dataset, is narrower than this
   condition.
7. **Publication and reviewer sharing are on hold** until Polymarket answers the
   follow-up. No manuscript or preprint naming Polymarket data, and no reviewer
   data package, goes out before then. If the answer is no or never comes,
   this is an open decision for the owner.
   **Cleared 2026-10-14** by Roni's reply of 2026-10-13: publication of
   aggregate results crediting Polymarket, and sharing market IDs and
   reproducibility metadata with peer reviewers and editors, may go ahead.
8. **Re-check before download.** Reread the Terms of Use, compare the SHA-256
   checksum with the 2026-10-11 value above, and record the result.

**Conflict: Gamma-only versus price history. Resolved 2026-10-12 by option
(i); the record is kept below.** This was checked against
Polymarket's own API specifications, `docs.polymarket.com/api-spec/`, read
2026-10-12. The checksums are in open-decisions item 6.

- **Gamma** serves market and event metadata and resolution status. It also
  serves current snapshot fields: `outcomePrices`, `lastTradePrice`,
  `bestBid`/`bestAsk`, `oneDayPriceChange`, `volume` and `liquidity`.
- **Historical price series** come only from the **CLOB API**:
  `GET clob.polymarket.com/prices-history`, with `security: []`, so no
  authentication.

Under condition 1, the features that need history at `t_d` cannot be built:
`price`, `recent_change`, and `liquidity` at `t_d` (Section 3). Gamma can
supply only outcomes, timing and final or snapshot values.

The owner was asked to choose one of two options before any download:

- **(i)** extend condition 1 to read-only, unauthenticated CLOB
  `/prices-history`, with the same rate-limit rule, and ask support to confirm
  that the reply covers it. *Recommended*, because the design depends on it.
  **Chosen by the project owner, 2026-10-12**, pending confirmation.
- **(ii)** keep Gamma only, which leaves Polymarket unable to support this
  design. In that case Manifold, the backup, becomes primary.

**Still open after option (i).** `/prices-history` returns prices only.
`price` and `recent_change` at `t_d` can now be built. **Liquidity at `t_d`
cannot**, because Gamma's `liquidity` and `volume` are snapshots and no trade
endpoint is allowed. Open decision 4 must therefore define liquidity from what
is allowed, or drop it. Two candidates:

- the count or density of price-history points before `t_d`;
- final volume as a *selection* filter only, never as a feature, because it is
  measured after `t_d` and would leak the future.

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

1. **Venue:** *planned 2026-10-12: Polymarket primary under the Section 1
   conditions, Manifold backup.* Still open:
   - Polymarket's confirmation that the reply covers CLOB `/prices-history`
     (option (i), chosen 2026-10-12; asked 2026-10-14, pending; Section 1);
   - a liquidity measure built only from allowed data (open decision 4).

   Publication and reviewer sharing were cleared on 2026-10-14 (condition 7).

   The options originally listed were:
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

## 10. Decisions of 2026-10-12 and the Polymarket loader

**Status.** The project owner decided items 1–4 below on 2026-10-12. Sections 2–9
above are kept as the record of what was weighed. Where they conflict with this
section, this section governs. The whole file remains DRAFT. Three items were
**PROPOSED** and awaited the owner's confirmation: the calibration method (10.2),
the decision-time rule (10.5) and the volume threshold (10.6).

> **CONFIRMED 2026-10-12 (project owner): 10.2, 10.5 and 10.6 are FINAL.**
>
> 1. **Calibration:** isotonic regression with pseudo-count-20 shrinkage and the
>    5-fold raw-versus-calibrated guard.
> 2. **Decision time:** a seeded random time over the scheduled life, excluding the
>    first and last 24 h. Markets closed by then are excluded and counted.
> 3. **Volume threshold:** $10,000, with $1,000 and $100,000 reported as
>    sensitivity.
>
> Still open: the 7-day gap, the cutoff `T_s` (chosen after the metadata count)
> and per-series caps.

### 10.1 Signal: none (decision 1)

- **No outside signal.** The `signal` pool is held at the encoder midpoint, 0.5
  (90 Hz in both framings), so total drive stays in the validated range
  (Section 3).
- **The question.** *Can the circuit beat the market using only market-internal
  features: price, recent_change and time_to_resolution?*
- **What the paper can claim.** This is option (a) of Section 4, with its claims
  and limits. The synthetic signal requirement does not transfer.
- **Deferred.** Cross-venue signal (option (b)) is deferred to a follow-up.

### 10.2 Comparator: the market price, calibrated on training markets only (decision 2)

**FINAL (confirmed 2026-10-12): isotonic calibration of the raw price, with
shrinkage, plus a training-only guard.**

1. **Fit.** Fit isotonic regression (pool-adjacent-violators) of the outcome on
   the raw price at `t_d`, **on the probability scale**, using training markets
   only. Tied prices are pooled.
2. **Shrinkage.** Shrink each isotonic block toward the block's own mean price
   with a pseudo-count m = 20: (Σy + m·p̄)/(n + m). A sparse block at an extreme
   price can then never output exactly 0 or 1.
3. **Prediction.** Interpolate linearly between block centres. Prices beyond the
   training range take the nearest end value.
4. **Guard, fixed before any test market is scored.** Run a 5-fold
   cross-validation on training markets, with folds assigned by a seeded hash of
   market ID, comparing the Brier score of the raw price with that of the
   calibrated price. The comparator is whichever is lower. Report both.

**Why this avoids the earlier artifact.**

- **What went wrong before.** Platt scaling fits a line on logit(price). In the
  synthetic sweep the clipped prices (0.01, 0.99) had extreme logits. They pulled
  the slope to about 0.6 and over-shrank the middle, so the "calibrated" price
  was worse than the raw price (Brier 0.2142 against 0.2093). A no-signal
  forecaster could then beat the comparator.
- **Isotonic does not have that problem.**
  - It works on the price itself, so an extreme price influences only its own
    block.
  - It is monotone, so it never reverses the market's ranking.
  - It can follow a favourite-longshot curve without assuming a shape.
- **Shrinkage** removes the remaining risk of 0/1 outputs from thin tails.
- **Precedent.** Isotonic calibration is generally as good as or better than
  Platt once about 1,000 or more calibration examples are available
  (Niculescu-Mizil & Caruana, 2005). Design A has thousands of training markets.
- **The guard.** A comparator weaker than the raw price makes the market
  comparison easier to pass, which was exactly the synthetic failure. Taking the
  better of raw and calibrated on training data keeps the comparator at least as
  strong as the raw price in expectation.

**Alternative:** 20 equal-count price bins with the same shrinkage. It is
simpler, but it is a step function and its edges are arbitrary.

### 10.3 Liquidity (decision 3)

- **As an input:** held at the encoder midpoint, 0.5.
- **Final volume** (Gamma `volumeNum`) is used **only as a selection criterion**,
  never as an input (10.6).

### 10.4 Size (decision 4)

- **Design A** (Section 7): `profit`, `learning_off`, and `null_permuted`, the
  shuffled-outcome null control.
- **Shape:** 40 chains × 250 markets (70 training, 180 test), 60,000 runs, about
  282 h.
- **Cost:** about **$75** at the measured CCX33 rate ($0.266/h, 213 runs/h).
- **Budget:** Phase 1 about $100, plus about $75 here, leaves about **$25 buffer**
  within the $200 total.
- **Market count needed:** about 10,000 distinct qualifying markets, one per
  event. **Unverified until the metadata count (10.7).**

### 10.5 Decision time and features (FINAL, confirmed 2026-10-12)

- **Decision time `t_d`.** A seeded uniform draw over the market's
  **scheduled** life, [start + 24 h, scheduled end − 24 h].
  - The seed is the SHA-256 of `flyshi-phase2-td-20261012|<market id>`.
  - The draw uses only the market ID and the listed start and end dates. It
    never uses the outcome, any price, or the actual close time.
  - It is drawn at selection, so it is frozen in the market list (10.7).
- **Why not a fixed horizon.** A fixed horizon (for example close − 7 days)
  would make `time_to_resolution` nearly constant. The question in 10.1 names it
  as one of three features.
- **Open at `t_d`.** A market that had already closed at `t_d` was not available
  to a trader then. It is excluded and counted (`closed_before_decision`). This
  defines the sampling frame and is not look-ahead. It does under-represent
  markets that resolve early, which is reported as a limitation.
- **Features, all from data strictly before `t_d`**
  (`polymarket.decision_features`):
  - `price` = the last CLOB price-history point **strictly before** `t_d`, at
    most 24 h old. If there is none, or it is stale, the market is excluded and
    counted.
  - `recent_change` = `price` minus the last point at or before `t_d − 24 h`,
    clipped to ±1. If the market has no such point, it is excluded and counted.
  - `time_to_resolution` = days from `t_d` to the **scheduled** end date. It is
    never the actual close, which would leak early resolutions. The encoder clips
    values above 365 days and reports it.
  - `liquidity` = 0.5 and `signal` = 0.5.
- **Look-ahead guard.**
  - **At the source:** each history request ends at `t_d`, as
    [`t_d` − 3 days, `t_d`] at 60-min fidelity. Nothing after `t_d` is
    downloaded.
  - **In code:** `strictly_before` drops every point with t ≥ `t_d` before any
    feature is computed.
  - **Tested:** a property test changes, removes or adds every point at or after
    `t_d` in 300 random histories, and the features must not change. Breaking
    the guard (`<` to `<=`) makes it fail, which was checked on 2026-10-12.
- **Unverified, to check on the first permitted requests** (a handful of
  markets, before the bulk run):
  - whether the CLOB history `p` is a midpoint or a last trade (the docs do not
    say);
  - whether fine-grained history is still served for long-resolved markets;
  - whether Gamma's `endDate` was edited after listing. Only the current value is
    available.

### 10.6 Selection (threshold FINAL, confirmed 2026-10-12)

- **Universe.** Every closed market from Gamma `/markets/keyset`
  (`closed=true`), archived markets included. No server-side volume filter is
  used, so excluded markets can be counted.
- **Rules, each exclusion counted:**
  - binary only: outcomes exactly Yes/No with two CLOB token IDs;
  - resolved: `outcomePrices` exactly (1, 0) or (0, 1). A 50/50 resolution is
    counted as **void**, and anything else as unresolved or ambiguous;
  - start, end and close dates present;
  - a non-empty decision window;
  - open at `t_d`.
- **Final-volume threshold: ≥ $10,000 (USDC, `volumeNum`), FINAL.**
  - *Why.* It removes thin markets whose prices go stale.
  - *Sensitivity.* Counts at $1,000 and $100,000 are reported (counts only).
  - *Limitation.* Final volume is known only afterwards, and it selects markets
    that drew attention. That may correlate with surprising outcomes. This is
    accepted under decision 3 and reported as a limitation.
- **One market per event.** Within an event, keep the market with the lowest
  SHA-256 of `flyshi-phase2-event-20261012|<market id>`. The choice is blind to
  outcome and price. A market with no event is its own event.
- **Not yet decided.** Per-series caps (criterion 5 of Section 5).

### 10.7 Frozen list, split and output

- **Frozen list** (`freeze_selection`). The selected markets are written with
  their IDs, YES token, dates, `t_d`, final volume and archived flag, plus the
  selection parameters and all counts. The file gets a SHA-256 checksum. It holds
  **no outcomes and no prices**; outcomes are stored apart and joined only at the
  build step. A different list can never overwrite a frozen one, and the build
  step refuses if the checksum does not match.
- **Train/test split** (`split_train_test`).
  - **Training:** markets **resolved** before the cutoff `T_s`, in resolution
    order.
  - **Test:** markets with `t_d` ≥ `T_s` + gap, in `t_d` order. The gap is
    **7 days** (proposed).
  - Markets in between are excluded and counted.
  - `T_s` is to be chosen after the metadata count, before any price history is
    fetched.
- **Output** (`write_market_file`). A JSON file in the `simulator.Market` fields
  the synthetic runner consumes: `quote`, `outcome`, `signal`, `recent_change`,
  `time_to_resolution`, `liquidity` and `sequence`.
  - `latent_probability` is unknown for real markets. It is `null` in the file
    and NaN once loaded; the runner never reads it.
  - Per-market metadata is kept beside the fields.
  - `load_market_file` returns the training and test lists of `Market` objects.
- **Not yet built:**
  - assembling 250-market chains (Section 7);
  - feeding a market file into the runner, whose `run_dataset` still generates
    synthetic markets;
  - the calibration comparator;
  - the shuffled-outcome arm.

### 10.8 Network rules (Section 1 conditions, enforced in code)

**Code.** `flyshi_research.realdata.polymarket` and the CLI
`repro/polymarket/load_polymarket.py` (steps `check`, `select`, `history` and
`build`).

- **Off by default.** A request needs **both** `--allow-network` **and**
  `--permission <file>` naming that exact endpoint. Otherwise it is refused
  before any transport runs. No permission file exists yet: creating one is the
  owner's act.
- **Only two endpoints exist in code:**
  - `GET https://gamma-api.polymarket.com/markets/keyset`;
  - `GET https://clob.polymarket.com/prices-history`.

  A permission file cannot add others.
- **Read-only and anonymous:** GET only, https only, no redirects, no cookies, no
  authentication headers, key or wallet.
- **Rate.**
  - The default pre-set rate is 0.5 requests per second.
  - It is refused if it exceeds 25% of the **published** limit recorded in the
    permission file. The API specs do not state the limits, so they must be taken
    from Polymarket's documentation when the file is written.
  - HTTP 429 gets exponential backoff, up to 5 retries.
- **Request log.** Every request is logged as JSON lines: UTC time, endpoint,
  URL, status, bytes, SHA-256 and attempt number.
- **Raw storage.** Raw responses are stored privately under `data/polymarket/`,
  which is git-ignored. They are never redistributed (condition 6).

**Permission file schema:**

```json
{"recorded_on": "YYYY-MM-DD", "recorded_by": "<owner>",
 "endpoints": [{"endpoint": "GET https://clob.polymarket.com/prices-history",
                "basis": "<e.g. Polymarket's written confirmation of DATE>",
                "published_limit": {"requests": N, "per_seconds": S, "source": "<URL, date checked>"}}]}
```

**Tests.** `tests/realdata/test_polymarket_loader.py` has 19 tests, using
recorded **fake** responses in `tests/fixtures/polymarket/`, hand-written to the
documented schemas. No test can build the real transport.

### 10.9 Gamma-only metadata count: preparation (2026-10-12; not run)

- **Permission file:**
  `repro/polymarket/permissions/gamma_markets_keyset_20261012.json`.
  - It covers **Gamma `/markets/keyset` only.** CLOB `/prices-history` stays
    unpermitted until Polymarket answers. (Update 2026-10-14: the question was
    sent on 2026-10-14, not in the 2026-10-12 follow-up; it is pending.)
  - Its basis is the 2026-10-11 human support reply ("Roni"), including that the
    reply is not definitive.
- **Published rate limit.** Recorded from
  `docs.polymarket.com/api-reference/rate-limits.md`, read 2026-10-12, SHA-256
  `1a238b502342564ff0afb087a725aad2bf16e5fa5978d19bcf414ea81d2a84a5`.
  - The Gamma figures are: general 4,000 per 10 s; `/markets` 300 per 10 s;
    `/events` 500 per 10 s; `/markets` + `/events` listing 900 per 10 s.
  - `/markets/keyset` is not listed, so the stricter `/markets` limit (30
    requests per second) applies.
  - **Our rate is 1 request per second**, 3.3% of that limit. The code caps it at
    25%.
- **Terms re-check (condition 8), 2026-10-12.**
  - The plain-text export of the Google Doc embedded at `polymarket.com/tos` has
    SHA-256 `0506de1e…2847d`. That is **identical** to the 2026-10-11 record. The
    terms are effective 11 August 2026, and the page still embeds the same
    document.
  - The loader also enforces the check: every network step refuses unless a
    matching terms check was recorded within the last 24 h (the `terms` step).
- **Count mode.** `select --count-only` downloads metadata only. It saves a
  private, compact snapshot with a SHA-256 checksum and prints a blinded count
  report:
  - resolved binary markets and exclusions by reason;
  - one-per-event counts;
  - qualifying counts at $1,000, $10,000 and $100,000;
  - selected markets by month of close and by month of decision time.

  The report carries no outcome or price. A test checks that flipping every
  outcome and changing every price leaves the report identical. Count mode
  freezes nothing. Later, `select --from-metadata <snapshot>` freezes the list
  offline from the same snapshot.
- **What the snapshot contains.** Gamma's market metadata includes each market's
  final `outcomePrices`, which the selection needs in order to detect void and
  resolved markets. That field is stored in the private snapshot, but it is never
  printed or summarised.

### 10.10 Gamma metadata count: result (2026-10-16)

**Counts only. No outcome or price was printed, summarised or read.**

- **Run.** `select --count-only`, Gamma `/markets/keyset` only, under the 10.9
  permission file, finished 2026-10-16. All pages were fetched.
- **Snapshot (private, git-ignored).**
  `data/polymarket/metadata_closed_markets_20261016T213329Z.json`, 3.0 GB,
  SHA-256 `2b226bd69ed57736413b2688ebc78949ec581729db36af850b8c2a67ca679245`.
- **The report.** The in-memory report step stalled on the 8 GB Mac and was
  stopped. The report was produced offline from the snapshot by the streamed
  count, `select --count-only --from-metadata`. That check verifies the snapshot
  checksum first, and a test shows it gives exactly the in-memory report.
- **The report file in the repository.**
  [`repro/polymarket/count_report_20261016T213329Z.json`](../../repro/polymarket/count_report_20261016T213329Z.json).
  It holds counts only.

**Universe:**

| quantity | count |
|---|---:|
| raw closed markets | 4,227,473 |
| of which created in 2026 | 3,953,904 (93.5%) |
| of which created in 2025 | 248,608 |
| of which created before 2025 | 24,961 |
| archived, in raw | 0 |
| AMM market-maker address present | 26,198 |
| UMA resolution status "resolved" | 4,223,516 |
| resolved binary (Yes/No, two tokens, exact 0/1 settlement) | 1,438,961 |

**Exclusions at ≥ $10,000, in filter order:**

| reason | count |
|---|---:|
| duplicate ID | 0 |
| not closed | 0 |
| more than two outcomes | 40 |
| two named outcomes, not Yes/No (e.g. team against team) | 2,770,994 (65.5% of raw) |
| missing token IDs | 49 |
| void (50/50) | 14,025 |
| near 0/1 but not exact (AMM era) | 3,327 |
| interior final price | 71 |
| malformed prices | 6 |
| missing dates | 6,323 |
| below $10,000 final volume | 1,279,987 |
| no decision window | 14,791 |
| closed before the decision time | 10,098 |
| eligible before the event choice | 127,762 |
| dropped by one per event | 86,869 |
| **selected** | **40,893** |

**Qualifying, one per event, by threshold:**

| threshold | eligible | dropped (one per event) | **selected** |
|---|---:|---:|---:|
| ≥ $1,000 | 298,812 | 227,571 | 71,241 |
| **≥ $10,000 (FINAL)** | 127,762 | 86,869 | **40,893** |
| ≥ $100,000 | 34,097 | 21,421 | 12,676 |

**Time profile of the 40,893:**

- **By close month:**
  - 2023: 256;
  - 2024: 2,134;
  - 2025: 9,302;
  - 2026, January–October 16: **29,201 (71.4%)**.
- **By decision month:** the same pattern, from 2022-02 to 2026-10. The month
  tables are in the report file.
- The last month (2026-10) is partial, because the snapshot was taken on
  2026-10-16.

**What this settles, and what it raises:**

- **Size.** Design A needs about 10,000 distinct markets. The count is
  40,893, about 4×, so Design A is feasible on count. Attrition at the
  price-history step is still unknown (10.5, unverified items).
- **The universe is recent.** 93.5% of raw markets were created in 2026. The
  "2–3 year window" of Section 5, criterion 3, is in effect about one year of
  dense data plus a thin tail.
- **No archived markets.** `archived_in_raw` is 0. Either Polymarket has no
  archived closed markets, or `/markets/keyset` with `closed=true` does not
  return them by default. Survivorship safeguard 12 requires archived markets
  to be included. **This is an open check.** It needs either the Gamma
  documentation or one permitted request, and it cannot be settled offline.
- **Mostly non-Yes/No markets.** Two thirds of raw markets have two named
  outcomes that are not Yes/No. They are excluded by the binary rule (10.6), as
  designed.

### 10.11 Proposals after the count (2026-10-16): NOT ADOPTED

**Status.** Every item below is **PROPOSED** and awaits the owner's decision.
Each is based **only** on the counts in 10.10, with no outcome or price. The
month tables give the marginal close and decision months, not their joint
distribution, so pool sizes are **approximate**:

- months are counted whole;
- the 7-day gap is pro-rated within its month.

The exact sizes come from `split_train_test`'s counts after the freeze.

**What Design A needs.** 40 disjoint chains × (70 training + 180 test):

- **2,800 training markets** resolved before `T_s`;
- **7,200 test markets** with `t_d` ≥ `T_s` + gap.

So the test pool is the binding constraint.

#### (a) Cutoff `T_s` and gap

**Proposed: `T_s` = 2026-03-01 00:00 UTC, gap 7 days, test `t_d` in
[2026-03-08, 2026-09-01).**

| `T_s` | training pool (closed before `T_s`) | × 2,800 | test pool (`t_d` from `T_s` + 7 d to 2026-09-01) | × 7,200 |
|---|---:|---:|---:|---:|
| 2026-01-01 | 11,692 | 4.2 | ≈ 22,490 | 3.1 |
| **2026-03-01** | **16,992** | **6.1** | **≈ 17,780** | **2.5** |
| 2026-04-01 | 18,231 | 6.5 | ≈ 15,510 | 2.2 |
| 2026-05-01 | 21,990 | 7.9 | ≈ 11,960 | 1.7 |

- **Why 2026-03-01.**
  - Both pools exceed their need by at least 2.5×, leaving room for unknown
    history attrition.
  - Training stays close to the test period: 10,890 of the 16,992 training
    markets (64%) closed in 2025-09 to 2026-02.
  - Under an earlier cutoff, the frozen weights would also have to carry over
    a longer test horizon.
- **Alternative: 2026-01-01**, if more test margin is wanted (3.1×). Its cost is
  an older training pool and an 8-month test horizon.
- **Gap: keep 7 days.**
  - The look-ahead rule is already met by "resolved before `T_s`".
  - The gap guards the feature windows. A history request covers
    [`t_d` − 3 d, `t_d`] (10.5), so any gap of at least 3 days keeps every test
    feature window out of the training period. 7 days adds a margin.
  - Its cost is about 410 test markets: 7/31 of March's 1,819 decisions.
  - A 30-day gap would cost about one month (about 1,800) and buy little.
  - No practical gap addresses repeating series. That is what per-series caps
    are for.
- **Test upper end, 2026-09-01.**
  - The snapshot contains only markets closed by 2026-10-16. The later a
    market's `t_d`, the more the sample favours markets that closed quickly.
    That shifts `time_to_resolution` and the market mix at the end of the test
    window (right censoring).
  - Ending the window at 2026-09-01 gives every test market at least
    6.5 weeks to close. It gives up 4,870 decisions in 2026-09 and 2026-10,
    which are not needed.
  - The training pool is not affected: "closed before `T_s`" is complete in
    the snapshot.
  - **A stronger option, not yet countable:** also require the *scheduled* end
    to fall before a date. The scheduled end is known at `t_d` and is not an
    outcome. This needs a count by scheduled-end month, which the report lacks.
    That would be one more offline run of about 2 minutes on the same snapshot,
    with no network.

#### (b) Choosing about 10,000 of the 40,893

**Proposed: freeze all qualifying markets, then fill each pool in a
pre-stated hash order.**

1. **Freeze.** The freeze covers the full list (what `select --from-metadata`
   already does: metadata only, no outcomes, no prices).
2. **Pools.** Split by the (a) rule into a training pool and a test pool.
3. **Rank.** Within each pool, rank markets by the SHA-256 of
   `flyshi-phase2-sample-<date>|<market id>`. The seed is stated before any
   history is fetched.
4. **Fetch and build.** Fetch price history and build in rank order, until the
   pool holds its requirement plus a pre-stated reserve, for example 10%:
   3,080 training and 7,920 test built markets.
5. **Assign chains.** Assign chains by built rank (Section 7: disjoint, seeded).

Properties:

- **Blind.** The order uses only the market ID. The stopping rule depends only
  on whether usable history exists (10.5's exclusions), never on a price value
  or an outcome.
- **Representative.** It is a simple random sample within each pool, so the
  month mix matches the pool in expectation.
- **Handles attrition.** Unknown attrition is absorbed without re-selecting.
- **Downloads only what is needed.** About (requirement ÷ build rate) requests
  instead of both whole pools (about 34,800 markets at the proposed cutoff). That matters while
  CLOB `/prices-history` is unpermitted (Section 1).
- **New code.** The current `history` step fetches every frozen market, so
  "fill in rank order" is new code. It is not written yet.

**Alternatives considered:**

- **Stratified by month, proportional allocation.**
  - It forces exact month proportions.
  - The gain is small at these pool sizes (thousands per pool), and it adds a
    parameter.
- **Stratified by month, equal allocation.** It over-weights the thin 2023–24
  months. Not recommended.
- **All markets in a narrow date window.**
  - Example: test `t_d` in 2026-04 to 2026-06, about 9,170 markets.
  - It needs no sampling, but the window becomes a free choice made after
    seeing the month counts.
  - It concentrates the test on one quarter.
  - Its margin (1.27×) may not survive attrition.
- **Fetch history for every market in both pools.** It is the most robust to
  attrition, but downloads about 3× more than needed.

**Still open, and not decidable from this snapshot:** per-series caps (10.6).
The snapshot keeps only the event ID and the question text, with no series or
category. Caps need either pre-stated rules on the question text or more Gamma
fields, which would mean another permitted download. This is the owner's
decision.

#### (c) Threshold: keep $10,000, or move to $100,000?

**Proposed: keep $10,000 (FINAL since 2026-10-12). Pre-state ≥ $100,000 as
a reported, non-gating subset of the test markets.**

**$100,000. Pros:**

- More actively traded markets, so fewer stale prices and fewer build-step
  exclusions.
- A cleaner and harder comparator: "beat liquid markets".
- Fewer history requests.

**$100,000. Cons:**

- **Too few markets.**
  - 12,676 in total against about 10,000 needed is 1.27×, before the split,
    straddling markets and attrition.
  - Month tables exist only at $10,000. If the ≥ $100,000 markets have the
    same time profile (31% of each month; **unverified**), the 2026-03-01
    cutoff gives about 5,270 training and 5,510 test markets. The test pool is
    then below 7,200.
  - No cutoff fits Design A's test need with any margin.
- **Stronger selection on attention.** Final volume is known only afterwards.
  The 10.6 limitation, that heavily traded markets may resolve more
  surprisingly, grows.
- **Re-opens a FINAL decision.** Doing so after seeing counts is
  outcome-blind, but it should be recorded as such.

**The middle course.** Keep $10,000 for selection and gating. Report the
≥ $100,000 test markets as a secondary analysis, stated now:

- about 31% of 7,200 is about 2,230 markets;
- its MDE is about 1.8× Design A's (√(7,200 / 2,230)).

**$1,000** (71,241) is not needed. It would only add thinner, staler markets.

**Streamed freeze (2026-10-16).**

- `select --from-metadata <snapshot>` now streams the snapshot: hash first,
  then one pass. It never loads the snapshot whole.
- `select_markets` keeps only compact state:
  - seen IDs in a bitmap;
  - volume-sensitivity counters;
  - the current choice per event.
- A test shows it gives the same frozen list and the same hash as the earlier
  in-memory version.
- **Nothing has been frozen yet.**
