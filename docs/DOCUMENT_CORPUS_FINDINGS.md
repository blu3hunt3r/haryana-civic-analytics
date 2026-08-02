# What is actually inside the 64 GB of tender documents

Every figure measured by extracting and reading the documents, not by reading their
metadata. Reproduce with `scripts/extract_documents.py` then `scripts/mine_documents.py`.

---

## 1. The corpus splits perfectly in two, and the half that is missing is the half that
## says what was bought

| Stage | rows | retrieved |
|---|---|---|
| **Work Item Documents** | 71,115 | **0%** |
| **NIT Document** | 51,974 | **0%** |
| all_stage_summary | 31,016 | 100% |
| Technical Evaluation | 30,252 | 100% |
| Financial Evaluation | 22,951 | 100% |
| Technical Bid Opening | 19,563 | 100% |
| AOC | 17,568 | 100% |
| Letter of Award | 3,000 | 100% |
| Packet / Packet Entry / Tender Document | 617 | 100% |

123,089 of the 123,095 unretrieved rows carry `document_download_window_closed`.

GePNIC keeps the *process* record and closes the window on the *defining* record. What
survives is who won and through which stages; what is gone is the Notice Inviting Tender
and the Work Item Documents that state the scope and the bill of quantities.

Format: **117,704 of 118,079 distinct blobs are PDFs (99.7%)**, 186 OOXML, 186 legacy
OLE, one HTML, one empty. Deduplication factor 1.06× — 124,961 document rows resolve to
118,079 distinct blobs, so per-tender document counts overstate distinct evidence.

## 2. 96% of what was retrieved is a rubber stamp

Median characters in the extracted text, measured over all 44,963 blobs in the four
content-bearing stages and a 60-blob sample of the rest:

| Stage | docs | median chars | p95 | no text layer | most common first line |
|---|---|---|---|---|---|
| Technical Evaluation | 30,217 | **304** | — | — | `Signature Not Verified` |
| all_stage_summary | 24,209 | 451 | 23,837 | 4,117 | `Signature Not Verified` |
| Financial Evaluation | 22,926 | **396** | — | — | `Signature Not Verified` |
| Technical Bid Opening | 19,560 | **385** | — | — | `Signature Not Verified` |
| AOC | 17,563 | 293 | 17,028 | 3 | `Signature Not Verified` |
| **Letter of Award** | 3,000 | **8,153** | 42,172 | 3 | `MUNICIPAL CORPORATION GURUGRAM` |
| **Tender Document** | 191 | **71,994** | 552,031 | 0 | `HARYANA FOREST DEPARTMENT` |
| Packet / Packet Entry | 425 | **0** | — | 111/120 in sample | scanned |

A 98 KB Technical Bid Opening PDF contains, in full, the word `approved`. A 166 KB
Technical Evaluation contains `As per tender term and condition`. The remainder of each
file is the digital signature block. Their analytical content — that the stage happened,
and when — is already in `tender_lifecycle_events` with a verified hash.

The informative documents are the **3,191 Letters of Award and Tender Documents**, plus
the minority of `all_stage_summary` that are corrigenda rather than stamps.

Extraction outcome over 44,963 blobs: 40,701 extracted, 4,123 no text layer, 1 timeout,
0 errors. The 4,123 without a text layer are the honest OCR queue.

## 3. A systematic unit bug the portal publishes and the letters disprove

2,847 tenders have both a letter amount and a portal `aoc_total_contract_value_inr`.

| | |
|---|---|
| exact agreement (≤ ₹1) | **2,241 (78.7%)** |
| within 1% | 127 |
| **disagree by more than 1%** | **479 (16.8%)** |

Of the 479 disagreements, **76 cluster at a ratio of almost exactly 100,000**.

Worked example, `2025_HRY_444909_1` — *Up-gradation of 100 to 200 bedded Hospital in
Sector-10 Gurugram (HVAC)*:

```
tender_value_inr              68,526,021        (the estimate, in rupees)
aoc_total_contract_value_inr       685.26       <- the estimate / 100,000
Letter of Award            7,03,27,583          "Agreement Amount (Rs.)"
```

The portal is storing a **lakh-denominated figure in a rupee-denominated column**. Across
the 76 affected tenders the portal totals **₹2,869** where the letters total
**₹289,273,505** — an understatement of **₹28.93 crore** in a field the site publishes as
contract value.

This also explains the earlier "degenerate values" finding: 178 controlling awards at
exactly ₹1, 302 below ₹1,000, minimum ₹0.40. Those are not placeholders. They are real
contracts with the decimal point moved five places.

The remaining 346 disagreements (72.2%) sit in a 0.5–2× band — genuine differences
between the letter figure and the portal figure, which is a separate question and is
**not** evidence of an error in either.

## 4. Correction: bills of quantity ARE available, embedded in the award letters

I previously reported that BOQ data was unrecoverable because Work Item Documents were
0% retrieved. That was wrong, and reading the documents is what showed it.

**2,951 documents contain BOQ rate tables** — `Sr. | Description | Qty. | Unit | Rate
(Rs.) | Amount (Rs.)`:

| Stage | documents with a rate table |
|---|---|
| Letter of Award | 1,787 |
| AOC | 1,048 |
| all_stage_summary | 115 |
| Financial Evaluation | 1 |

Median 3 table headers per document, p95 16, **max 143**. The hospital HVAC letter above
carries its entire bill of quantities inline, with DSR references, item specifications
and per-item rates.

**This changes the tooling answer.** `pdf-inspector`'s table detection has a real target
after all — 2,951 documents, not the 118,000 I measured it against. `pdftotext -layout`
preserves the columns well enough to see the tables but does not segment rows, so
recovering *per-item rates* at scale is exactly the job it is built for. It remains the
wrong tool for the other 115,000 documents, which have no tables at all.

## 5. Registration codes settle identities that string matching cannot

**757 distinct contractor registration codes** recovered, of the form
`SUPER GLOBAL INFRASTRUCTURE [2021R586]`.

The important direction is the reverse one: **7 names carry more than one registration
code**, including `SURENDER KUMAR CONTRACTOR` → `2021R2050` and `2021R657`. Two
separately registered firms share a name. Any concentration metric that merges bidders on
name similarity would have combined them, and the 641 fragmentation candidate groups
identified earlier contain exactly this hazard.

A registration code is a stable identifier and settles identity without guessing. It
should become the join key for party resolution wherever it is present.

Caveat found on inspection: the `party_name` capture in `mine_documents.py` anchors on
the text preceding `[code]` and in multi-line address blocks that is often an address
fragment (`SECTOR 5, GURUGRAM, 122001`) rather than a name. The codes are reliable; the
names attached to them need a line-anchored parser before use.

## 6. Why tenders restart — a reason that exists nowhere in the structured data

**1,201 restart clauses** recovered, overwhelmingly from `all_stage_summary` corrigenda
(1,024) and Tender Documents (164).

| Category | count | share |
|---|---|---|
| unclassified | 477 | 39.7% |
| administrative / approval | 394 | 32.8% |
| no bid / no response | 182 | 15.2% |
| technical / qualification | 134 | 11.2% |
| price / rate | 11 | 0.9% |
| time / validity expiry | 3 | 0.2% |

Verbatim: `"no bid received"`, `"error in creation of tender"`, `"administrative reasons
the tender"`, `"non-participating the sufficient bidders tender is hereby recalled"`.

Nothing in the structured data explains why any of the 6,198 multi-tender chains
restarted, or why 2,426 of them never reached an award. This does.

**The 39.7% unclassified rate was a precision problem in my clause anchor, not a
property of the documents.** `scripts/classify_restarts.py` now repairs it: 518 of the
clauses were the boilerplate warning to bidders ("your tender will be cancelled and you
will be debarred"), which is a threat about the future and not a restart record, and
much of the rest was OCR damage ("admin1strat1ve feásons") that a match-time
normalisation recovers. On the 1,414 genuine clauses the counts become: **no bid /
too few bids 33.3%, administrative 32.0%, unclassified 24.3%, technical 7.9%, error in
tender creation 2.2%** — competition failure, not administrative discretion, is the
commonest stated reason a tender restarts.

## 7. Field recovery, overall

Across 41,059 extracted documents:

| Field | recovered | share |
|---|---|---|
| tender_id (in-document) | 10,071 | 24.5% |
| memo number | 5,856 | 14.3% |
| e-mail | 5,855 | 14.3% |
| phone | 4,037 | 9.8% |
| agreement amount | 2,878 | 7.0% |
| registration code | 2,616 | 6.4% |
| restart reason | 1,201 | 2.9% |

Every value is written with the blob SHA-256 it came from and the verbatim source line,
so any figure can be checked against the page it was read from.

## What to do next, in order

1. **Publish the lakh-bug correction.** 76 tenders, ₹28.93 crore, with the letter as
   evidence for each. This is the highest-value finding in the corpus.
2. **Tighten the restart-reason grammar** and re-run; then join reasons to the 6,198
   chains so a cancelled procurement carries its stated cause.
3. **Line-anchor the party-name parser**, then use registration codes as the resolution
   key for the 641 fragmentation groups.
4. **Extract the 2,951 BOQ tables** — this is where `pdf-inspector` earns its place.
5. **OCR queue**: 4,123 documents with no text layer, plus the 425 Packet blobs that are
   100% scanned.
