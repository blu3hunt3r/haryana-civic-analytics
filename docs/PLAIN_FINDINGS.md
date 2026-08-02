# What this data says, in plain language

No jargon. Every number here was counted from the records, and where I have not checked
something I say so.

---

## First, honestly: how much have I actually read?

The archive holds **118,079 separate documents, about 61 GB**. I have now read the text
of **112,223 of them — 95%, covering 89.7% of the bytes.**

The remaining **5,856 have no text layer at all** — they are photographs of paper. They
cannot be read without OCR, and I have not run OCR. That is the honest remainder.

An earlier version of this page said I had read a third. That was true when written, and
the gap mattered, because the three biggest groups had only been sampled at 60-100
documents each. Those are now read in full, and the sample turned out to be accurate:

| Group | predicted from sample | true, all read |
|---|---|---|
| Technical Evaluation | 304 characters | **289** (29,826 docs) |
| Financial Evaluation | 396 | **377** (22,210) |
| Technical Bid Opening | 385 | **356** (19,313) |

**But reading everything found something the sample could not.** Buried in those three
groups are **6,133 documents (8.4%) that are not stamps at all** — including 416
bid-comparison tables showing every bidder and their rates, 193 bills of quantity, and
64 award letters filed in the wrong place. Sampling would have missed all of them,
because they are the rare exception in a pile of near-identical filler.

---

## The right way to do this, which I got wrong at first

I started by averaging everything together. That was a mistake, and here is why in one
example.

Across all Gurugram tenders, **8.3%** attract only a single bidder. That sounds
unremarkable. Split it by the department running the tender:

| Department | single-bidder rate |
|---|---|
| Sohana PHED | **36.8%** |
| Gurugram PHED | **36.4%** |
| XEN Panchayati Raj | **32.4%** |
| MC Sohna | 1.6% |
| Industrial Area | 0.8% |
| XEN TS Gurugram | **0.0%** |

The 8.3% average is the one number in that table that tells you nothing. So the corpus is
now cut into **376 groups — 48 departments crossed with 21 kinds of work** — and each is
read on its own. (An earlier cut had 314 groups and left 43.7% of tenders without a work
category; the classifier has since been taught the vocabulary Haryana public works
actually use, and the uncategorised share is now 11.1%. The section near the end records
that repair honestly.)

*(A single bid is lawful and often innocent — a small village job may simply not interest
many firms. It is a reason to look, not a finding.)*

---

## The clearest thing in the data

One group stands out from all 376.

**Development & Panchayats — the department that builds village paths, retaining walls
and community halls.**

They published **4,134 tenders**. Here is what happened to them:

| Outcome | tenders | share |
|---|---|---|
| **Sent back out to retender** | **2,582** | **62.5%** |
| Actually awarded | 1,080 | 26.1% |
| Still open / being evaluated | 398 | 9.6% |
| Cancelled | 74 | 1.8% |

**Nearly two-thirds of everything this department puts out has to be run again.**

What are they trying to build? The words in their own descriptions: *rasta* (village
path) 584 times, *wall* 500, *brick* 435, *street* 359, *chaupal* (village meeting hall),
*ghat*, *shed*. Real examples:

> "const.of retaining wall at village silani"
> "MOHMEDPUR SAIDPUR VANGY — CONST OF HALL IN GEN.CHAUPAL"

Small rural works. And they keep failing to get bought.

### Which of their works fail worst

When the classifier finally understood this department's vocabulary, its one big
"general" pile split apart, and the failure is not evenly spread:

| Kind of work | tenders | re-run | only one bidder |
|---|---|---|---|
| **buildings** (chaupals, halls, sheds) | 1,247 | **69.0%** | **40.0%** |
| village paths and paving | 1,408 | 57.2% | 19.6% |
| water works | 233 | 64.8% | 23.7% |
| **fencing and boundary walls** | 140 | **80.7%** | **61.5%** |
| drainage | 119 | 72.3% | 44.1% |
| sanitation | 63 | 73.0% | 69.2% |

The paths — the *rasta* work — actually fare the least badly. **It is the village
buildings that fail worst at scale**: 1,247 attempts to build community halls and
chaupals, of which seven in ten had to be re-run, and when bids came, four in ten
times only one firm bid.

One more thing the records show: **this department publishes no maintenance contracts
at all.** Every other big buyer runs annual-maintenance work alongside construction;
here every tender is new construction. Nothing in this data says who maintains a
chaupal once it is built — or whether anyone does.

### Does the second attempt work?

Following each job through every re-run — 1,853 job histories in total:

- **982 (53%)** eventually reached an award.
- **871 (47%) never did.** They were tendered, re-tendered, and quietly stopped.

Some were tried repeatedly: 44 jobs went round five times, 41 went six, 22 went seven or
more. **Nearly half the village paths and community halls this department tried to build
never got as far as a contract.**

### Why?

**I don't know, and the documents for this department don't say.** I searched their
paperwork for a stated reason and found **zero**. Elsewhere in the corpus 1,414
documents do give a reason (after excluding 518 boilerplate warnings to bidders that an
earlier count mistook for reasons). The commonest stated reason, now that the counting
is honest, is **"no bids, or too few" — 33.3%** — just ahead of "administrative
reasons" (32.0%), with "error in creation of tender" among the 2.2% of plain mistakes.
But none of those documents belong to this department.

That is an honest gap, not a conclusion. What can be said is that when bidders do turn up
here, **27.8% of the time only one bidder turns up.**

---

## A mistake in the published figures, now fixed

For **264 tenders** the government portal published a contract value that was wrong by a
factor of 100,000 — it stored a figure in *lakhs* in a column meant for *rupees*.

The clearest case: a hospital air-conditioning upgrade in Sector 10, Gurugram.

| | |
|---|---|
| What the portal published as the contract value | **₹685** |
| What the signed award letter actually says | **₹7,03,27,583** |

The portal was showing ₹685 for a seven-crore contract.

**What I did:** for **117** of them the award letter states the real amount, so the site
now shows both — the portal's figure struck through, the letter's figure beside it, and
the document's fingerprint so anyone can check. For the other **147 there is no letter in
the archive, so I changed nothing** and simply marked the figure as not believable. I did
not substitute the estimate, because an estimate is not what was paid or agreed — using
one to fill the gap would repeat the same kind of error.

Effect on the headline total: ₹83,295,707,464 → ₹83,578,763,198. A rise of 0.34%. **The
big total barely moves. The individual pages were badly wrong, and that was the point.**

---

## The groups that stand out

With the corpus cut into 376 groups, 51 of them have enough tenders (150+) to draw a
conclusion from. Across those, the normal rate is **31.3% rework** and **9.4%
single-bidder**. (These baselines barely moved when the classifier was repaired — from
31.4% and 9.5% — which is reassuring: the corpus-wide picture was right, it was the
group boundaries that were wrong.) Against that baseline:

**Worst for work having to be re-run:**

| Department | Work | Tenders | Re-run | Single bidder |
|---|---|---|---|---|
| Development & Panchayats | building | 1,247 | **69.0%** | **40.0%** |
| Development & Panchayats | water | 233 | 64.8% | 23.7% |
| Development & Panchayats | paths / paving | 1,408 | 57.2% | 19.6% |
| GMDA | water | 174 | 52.3% | 4.0% |
| GMDA | sewer | 187 | 47.6% | 7.9% |
| GMDA | landscape | 170 | 46.5% | 14.4% |

(Village fencing, at 140 tenders, sits just under the 150 cut-off — 80.7% re-run and
61.5% single-bidder, still the most extreme group in the corpus.)

**Worst for only one firm turning up:**

| Department | Work | Tenders | Single bidder |
|---|---|---|---|
| PWD (B&R) | street lighting | 237 | **53.3%** |
| Development & Panchayats | building | 1,247 | **40.0%** |
| PHED | water | 1,392 | 37.8% |
| Agricultural Marketing Board | link roads | 1,407 | 27.3% |

Two of these survived the classifier repair almost unchanged, which is what a real
pattern should do. PWD street lighting was 52.7% single-bidder before, 53.3% after.
PHED water was 37.4% on 726 tenders; the repaired classifier nearly doubled the group
to 1,392 tenders and the rate moved to 37.8% — twice the evidence, same answer.

Two different problems sit in these tables.

**Small village works nobody bids for.** Fencing (₹1.9 crore in total), sanitation,
drainage — tiny money, extreme failure rates, and one firm bidding when anyone bids
at all.

**GMDA is the opposite shape.** Its re-run rate is 41–52% across every kind of work it
buys — water (₹240 crore), sewer (₹289 crore), drainage (₹209 crore), surfacing (₹185
crore) — and competition there looks normal (4–14% single-bidder). Big money being
re-tendered is a different problem from small jobs nobody wants. One nuance the new
mode records add: 39% of GMDA's sewer tenders are annual maintenance contracts, so part
of its "rework" is maintenance work being re-bought, not construction failing.

**Where you can check the least is often where the money is.** GMDA's document coverage
runs 60–65% on its big-money groups; PHED water is 52% and PWD street lighting 51% — so
the group with the highest single-bidder rate is also one of the hardest to verify.

### A dimension the data was hiding: how the work is bought

The repaired records now separate *what* was bought from *how* it was bought. Three
buying patterns are recorded alongside the work type: **annual maintenance contracts
(6,464 tenders, 13.2%)**, **hired capacity — manpower, vehicles, machinery on rent
(1,344, 2.7%)** — and **re-called tenders (5,573, 11.3%)**. A fourth was found in the
residue afterwards: **131 tenders re-bought "at the risk and cost" of a firm that
defaulted** — the only place in 49,121 records where a contractor failing to deliver
leaves a trace.

That reveals department characters that the work-type view cannot see:

- **HSVP/HUDA is a maintenance organisation.** 46% of everything it buys — across
  lighting (79%), water (68%), drainage (59%), buildings (53%) — is upkeep of what
  already exists, not new construction.
- **PWD runs a big gardening operation.** 75% of its 2,091 landscape tenders are
  annual maintenance of plantations, parks and road verges — the hedges outside
  judicial complexes and rest houses, bought year after year as separate contracts.
- **Development & Panchayats buys no maintenance at all** — the only major buyer with
  a construction-only profile.

## Other things worth knowing

**Half the paperwork is missing, and it is the important half.** Every tender has a
"Notice Inviting Tender" and "Work Item Documents" — these say what was being bought and
at what rates. **All 123,089 of them failed to download**; the government portal closes
that window once a tender ends. What survives is the paperwork about the *process*: who
won, through which stages. You can see who got the job. You largely cannot see what the
job was.

**Most of what did survive says almost nothing.** A 98 KB file whose entire text is the
word *"approved"*. Another, 166 KB, reading *"As per tender term and condition"*. The
rest of each file is a digital signature image. The genuinely informative documents are
about **3,200 award letters** out of 118,079.

**Some contractors' names are the same but the firms are not.** "SURENDER KUMAR
CONTRACTOR" appears with two different government registration numbers — two separate
businesses sharing a name. This matters because any attempt to work out "which firms win
the most" by matching names would silently merge them into one. I found 757 registration
numbers in the letters; those are safe to match on, names are not.

**Village works can be looked up at all now.** 7,647 tender records name a village rather
than a sector or ward, and until recently nothing in the system could search by village —
rural Gurugram has no sector number and no municipal ward, so those residents had no way
in.

---

## Two things wrong with my own grouping — one now fixed, one not

Someone looked at my tables and said four departments and a handful of work types cannot
be the whole picture. They were right about the cause.

### Nearly half the tenders had no work category at all — FIXED

Of 49,121 tenders, **21,470 — 43.7% — were filed as "unclassified"** when the earlier
version of this page was written. I built 314 groups out of department × type of work
and presented them as meaningful, without checking that the second half of that pair was
empty for nearly half the data.

It was not that the descriptions were blank. **Every one of the 21,470 had a
description.** The classifier simply did not know the words Haryana public works
actually use:

| In the records | What it means |
|---|---|
| IPB | interlocking paver block — a footpath or road surface |
| WBM | water bound macadam — road surface |
| CC locking, RMC M-40 | concrete road surface |
| AR OF LR | annual repair of link roads |
| PAV OF RASTA | paving a village path |
| brick work, CPLASTER | building work |

Teaching it that vocabulary — plus five missing kinds of work (IT equipment, traffic
infrastructure, animal control, air-conditioning, land) — and separating *how* work is
bought (maintenance, hired capacity, recalled) from *what* is bought, is now **live in
the published data**: the unclassified share is **11.1% (5,459 tenders)**, the groups
number 376, and every table on this page has been recomputed from the repaired records.
The verification suite and all 26 invariant tests pass on the rebuilt data.

The findings mostly survived, which is what real patterns should do — the baselines
moved by 0.1 point, PWD street lighting and PHED water held their single-bidder rates
on much larger evidence — but the Development & Panchayats picture sharpened
substantially (see above): its failure concentrates in village *buildings*, not paths.

What still cannot be classified is a smaller, stranger set: descriptions with the
spaces stripped out ("operationandmaintenanceSohna", "Gadaipur784FHTC2nd"), entries
that say only "As per DNIT", "COMPLITION" or "mlc", and the biggest remaining block —
2,185 municipal tenders reading "civil work in ward no. X", which name a place and a
budget head but genuinely not a kind of work. This classifier is treated as a live system: the residue is a
worklist, not a verdict.

### 189 real organisations were being reported as 48 — NOW FIXED

The raw records name **189 separate bodies**, in chains three and four levels deep like
`Haryana Government || Urban Local Bodies || MC Gurgaon`. The build folds them into 48
canonical departments, so MC Gurgaon, MC Manesar, MC Sohna, MC Pataudi and ten others all
become one line reading "Municipal Corporation / Urban Local Bodies" — 18,991 tenders.

**How much that actually hides, honestly:** less than I first suggested. Across those
municipal bodies the re-run rate runs 27.3% to 37.0% against a combined 36.2% — a real
spread but not a dramatic one. Single-bidder rates vary more, from 0.3% at MC Pataudi
Mandi to 9.3% at MC Pataudi and MC Farukh Nagar.

The right structure is two levels — the parent for totals, the 189 individual bodies
for analysis — and that is now what the data carries: every tender records both its
department and the leaf office that ran it, and the office is on the tender's page.

What the office-level cut shows immediately: **the Development & Panchayats failure has
an address.** XEN Panchayati Raj Gurugram ran 3,051 tenders with 65.0% re-run, and SDO
Panchayati Raj Pataudi ran 415 with 69.9% — the worst two large offices in the state.
GMDA's re-tendering concentrates in its two infrastructure divisions (INFRA I and
INFRA II: ₹1,148 crore between them, both at 47.5% re-run). The fourteen municipal
bodies, by contrast, really do behave alike — 31% to 37% re-run — so folding them
together was hiding less than it appeared, which is also worth knowing.

---

## What I still cannot tell you

- **Whether any money was actually paid.** Nothing in 49,121 records evidences a payment.
- **Whether the work was actually done.** Out of 49,121 tenders there are exactly **three**
  documents confirming a completed work. Not three per cent. Three.
- **Why Development & Panchayats re-tenders two-thirds of its work.** The reason is not
  written down in what was retrieved. The decomposition above narrows the question —
  why do village *buildings* fail worse than village *paths* run by the same
  department? — but does not answer it.
- **What is inside the 5,856 scanned documents** that have no text layer. They need
  OCR, which has not been run.

---

## What I would do next

1. Keep working the classifier residue down — 6,255 tenders remain, half of them
   municipal ward works whose descriptions may genuinely name no kind of work. Each
   pass so far has been measured before shipping: 43.7% → 15.9% → 12.7% → 12.4% → 11.1%.
2. Join the 1,414 stated restart reasons to their procurement chains, so a cancelled
   tender can carry its cause (611 of them name no tender ID in the document and
   need the chain resolved another way).
3. Dig into why Development & Panchayats' village buildings fail at 68.9% — compare
   its bid windows, estimate sizes and locations against the same work bought by
   departments whose buildings do get built.
