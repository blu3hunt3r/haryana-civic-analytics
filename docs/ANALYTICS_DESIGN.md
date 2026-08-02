# How this corpus should actually be worked

Written after profiling the tables rather than reading their names. Every number below
was measured; nothing is estimated.

---

## 1. The real diagnosis

The portal has a **reporting layer** and no **analytical layer**.

`build_analytics.py` walks raw CSVs and emits pre-aggregated counts. That is fine for
"how many tenders in Sector 56", and it is why the headline figures are correct. But it
means every question that was not anticipated at build time is unanswerable, and the
richest tables are barely touched:

| Table | Rows | What the portal currently exposes |
|---|---|---|
| `bid_history` | **103,258** over 31,283 tenders, **8,241** distinct bidders | one field: `awardedBidCount` |
| `tender_lifecycle_events` | **339,034**, 100% timestamped, 100% hash-verified | a count |
| `documents` | **248,056**, 124,961 with SHA-256, **64 GB** retrieved | a count and a download flag |
| `procurement_chains` | 30,089 roots, **6,198** multi-tender chains | chain length and a boolean |

The bid table is the crown jewel and it is spent on a single integer. It carries
`bidder_name` (100%), `financial_value_inr` (62.6%), `financial_rank` (62.9%),
`is_awarded` (100%) and a nine-value `bid_status` vocabulary. That supports competition
analysis, price dispersion, bidder networks and concentration — none of it published.

**So the work is not "add more charts". It is to build the missing layer in the right
order: normalise, resolve, model, measure, then present.**

---

## 2. Two blockers must be cleared first, and both are proven

### 2a. Dates are not normalised — this blocks every duration metric

One column, `tender_lifecycle_events.event_at`, carries **three formats**:

```
02-Apr-2011 06:00 PM      portal format
2012-11-02                ISO date
2026-07-27T12:00:54+05:30 ISO datetime with offset
```

339,034 events are 100% populated and 0% normalised. With a 12-line parser, all 339,034
parse and the analysis becomes available immediately:

> **Publication → award, confirmed Gurugram, n = 13,304**
> median **64 days**, p25 35, p75 122, p95 **350**, max **2,114**
> **612 tenders (4.6%) took more than a year to award**

The same defect appears in the three reviewed completion records
(`09 September 2022`, `31-Jan-22`, `28-02-2022` — three formats, three records).

### 2b. Contractor names are fragmented — this blocks every concentration metric

8,241 raw bidder names. Under conservative normalisation (strip honorifics, legal forms,
punctuation) they collapse to 7,112 groups, of which **635 groups hold 1,761 raw
spellings**:

```
14 spellings, 342 bids   KRISHNA CONSTRUCTION CO / Krishna Builders / KRISHNA CONSTRUCTIONS …
10 spellings, 312 bids   SATISH KUMAR / Satish Kumar Contractor / M/s Satish Kumar Contractor …
15 spellings, 148 bids   BALAJI ENTERPRISES / Bala Ji Builders / Balaji Construction And Company …
```

**These are candidates, not identities.** "Balaji Enterprises", "Bala Ji Builders" and
"Balaji Construction And Company" may be three unrelated firms, and my normalisation
reached that grouping only by deleting the words that distinguish them. Publishing an
auto-merge would manufacture a concentration finding out of a string operation.

A further **773 names are 44+ characters**, i.e. truncated by the portal, so some
identities are irrecoverable from this archive at all.

The correct output is therefore a **reviewed entity-resolution table with a decision per
group**, and every unreviewed group treated as distinct. Until that exists, concentration
must be published as *"at least N distinct winners"*, never *"exactly N"*.

---

## 3. The model to build

Stop recomputing from CSVs. Build a conformed star over the existing SQLite, with one
grain per table stated explicitly — most reconciliation bugs in this repo came from
mixing grains (a tender-grain count summed over a bid-grain table).

```
dim_tender          grain: one Tender ID                    49,121
dim_organisation    grain: one organisation-chain leaf      48 departments
dim_party           grain: one RESOLVED bidder/contractor   7,112 candidates, reviewed
dim_place           grain: one area token + level           district/ward/sector/village
dim_date            grain: one calendar day
dim_component       grain: one work component               16

fact_bid            grain: one bid on one tender          103,258
fact_lifecycle      grain: one event on one tender        339,034
fact_document       grain: one document attempt           248,056
fact_award          grain: one controlling award            9,306
fact_chain_link     grain: one tender's place in a chain   49,121
```

Two rules that are not negotiable, because both have already bitten:

- **Every measure declares its grain and its denominator.** The award/estimate ratio has
  only **8,440 usable denominators of 9,306 controlling awards**; publishing a median
  without saying so is arithmetic on absent data.
- **Money is compared with a tolerance, never for equality.** Summing 9,306 rupee floats
  in a different order gave 65,865,653,414.11003 against 65,865,653,414.110115.

---

## 4. The analyses, ranked by public value × evidential strength

Ranked, because eighteen mediocre charts are worse than six that hold up.

### Tier 1 — strong evidence, high public value, buildable now

1. **Time to award.** Median 64d, p95 350d, 612 over a year. Per department and year.
   Evidence: hash-verified lifecycle events. Nothing inferred.
2. **Single-bidder rate by department.** Overall **8.3%** (1,679 of 20,210), but the
   spread between departments is two orders of magnitude:

   | Department | single-bidder |
   |---|---|
   | Sohana PHED | **36.8%** (95/258) |
   | Gurugram PHED | **36.4%** (115/316) |
   | XEN Panchayati Raj Gurugram | **32.4%** (236/728) |
   | EE PD-1 Gurugram | **31.3%** (150/479) |
   | … | |
   | MC Sohna | 1.6% (16/1,018) |
   | Industrial Area | 0.8% (6/773) |
   | XEN TS Gurugram | **0.0%** (0/146) |

   This is the single most useful thing in the corpus. It is a **review indicator**: a
   single bid is lawful and often innocent, and the framing must say so.
3. **Chain outcomes.** 6,198 multi-tender chains; **3,772 eventually awarded, 2,426 never
   awarded**. A cancelled-and-retendered procurement that never lands is a public fact
   currently invisible.
4. **Evidence-gap coverage by department.** Which bodies publish award documents and
   which do not — already computable from 248,056 document rows.

### Tier 2 — buildable, but must ship with its exclusions

5. **Estimate vs award.** Median ratio **0.9493** across 8,440 usable pairs — and a
   maximum of **126,331,980**, with 12 ratios over 100 and 266 under 0.01. Publishable
   only alongside the 866 excluded denominators and a stated outlier rule.
6. **Price dispersion (L1 vs L2).** 64,606 rows carry a financial value and 64,970 a
   rank. Real, and limited to the 62.6% that publish figures — which must be stated.
7. **Bid-rejection patterns.** 12,808 `Not Admitted-Fee/PreQual`, 21,579
   `Rejected-Finance`, 18,680 `Rejected-AOC`. A bidder repeatedly disqualified at
   pre-qualification is a pattern worth surfacing as an indicator.

### Tier 3 — needs entity resolution first

8. **Concentration.** Today: 13,582 awarded bids, 2,364 "distinct" winners, top 50 =
   21.8%, top winner 0.9%. The honest headline is that the market looks **unconcentrated
   at the top** — but the 635 fragmentation groups mean 2,364 is an overcount and the
   true figure is lower. Publish after review, with the reviewed count.
9. **Bidder co-occurrence and repeat pairings.** 8,241 nodes. Genuinely informative, and
   the most easily misread thing in the corpus — two firms bidding on the same roads
   repeatedly is what a functioning local market also looks like. Needs a null model
   (expected co-occurrence given each firm's bid volume) before any pair is called
   unusual.

### Not buildable from this archive — say so and stop

- **Money paid.** Nothing in 49,121 records evidences payment.
- **Physical completion at scale.** 3 reviewed records. Not 3%. Three.
- **Whether a single bid indicates anything wrong.** The data supports the rate, and the
  rate only.
- **Identity behind 773 truncated names.**

---

## 5. Order of work

1. `normalise.py` — dates, money, organisation leaves, party names. Emits a normalised
   layer plus a **rejects** file; nothing is silently dropped.
2. `resolve_parties.py` — candidate groups with scores, a decision column, and
   `unreviewed` as the default. Feeds a review queue, not a merge.
3. `model.py` — build the star above into the existing SQLite.
4. `metrics.py` — one registry entry per measure carrying definition, numerator,
   denominator, exclusions, source tables, source hashes, dataset version, limitations.
   The UI renders from the registry so a metric cannot reach a screen undefined.
5. Publish Tier 1, then Tier 2 with exclusions, then Tier 3 after review.

The presentation follows the analysis, not the other way round. Tier 1 alone —
time-to-award, the single-bidder spread, chain outcomes, evidence gaps — is a stronger
product than the eighteen-chart gallery, because every one of those four survives an
argument with the department it describes.
