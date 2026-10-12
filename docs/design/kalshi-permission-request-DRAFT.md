# DRAFT — permission request to Kalshi Research (NOT SENT)

**Status:** draft, 2026-10-11. It has not been sent, and must not be sent without
the project owner's explicit decision. The recipient address is unknown. No
public research-access contact was found on `kalshi.com/research`, so the owner
must find the right contact. Items in [brackets] are for the owner to fill in.
The context is in [`open-decisions.md`](open-decisions.md), item 6, revision
2026-10-11.

---

**Subject:** Request for written permission: non-commercial research use of
Kalshi historical market data

Dear Kalshi Research team,

I am [name], [role / affiliation, or "an independent researcher"]. I am writing
to ask for written permission to use Kalshi historical market data in a
non-commercial research project. Your Developer Agreement (v1.1) and Kalshi Data
Terms of Use require that permission, so I have not downloaded any Kalshi data
and will not do so without it.

**The project.** I am studying whether a computational model of the fruit-fly
mushroom body can learn from experience to forecast binary outcomes. The model is
built from the published *Drosophila* connectome and uses a dopamine-like
learning rule. It has been tested on synthetic markets. The next step is a
historical replay on real, settled binary markets:

- for each market, the model sees the price, the recent price change, the time
  remaining and the liquidity at one past moment;
- its forecast is compared with the market price and with the eventual
  settlement.

There is no live trading, no order placement and no money involved. The work is
not commercial and is not used to build any product or financial instrument.

**What I am asking permission for:**

1. **Retrieval and storage.** Retrieve, through the official API at a modest
   rate and within the published limits, metadata, price or candlestick history
   and settlement results for about [10,000–20,000] settled binary markets
   between [start] and [end]. Then store that data privately for the project.
   This needs a waiver of Developer Agreement §3 and §3.1 and of Data Terms §I–II.
2. **Analysis with a learning model.** Analyse the data and present it to the
   learning model described above. This needs a waiver of the Data Terms
   machine-learning clauses (§I and the final paragraph of §II). The model is a
   small biological simulation, not a language model or a commercial AI system.
3. **Publication.** Publish the results in a scientific paper and preprint
   naming Kalshi as the data source. The results would include aggregate
   statistics, figures and market identifiers such as tickers. This needs
   approval under Developer Agreement §6.4. I am happy to share the manuscript
   with you before submission.
4. **Reviewer access.** Give journal reviewers and editors confidential access
   to the derived dataset (per-market features and settlements) and the analysis
   code, for verification only. That access would end after review. No public
   redistribution of Kalshi data is requested. [Optional: or ask whether a
   public release of derived per-market features would be acceptable.]

I can provide the pre-registered design, the code and any other details you need,
and I will accept any conditions on attribution, data handling, rate limits or
deletion after the project.

Thank you for considering this.

[Name]
[Affiliation]
[Contact email]
