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
now cut into **314 groups — 48 departments crossed with 16 kinds of work** — and each is
read on its own.

*(A single bid is lawful and often innocent — a small village job may simply not interest
many firms. It is a reason to look, not a finding.)*

---

## The clearest thing in the data

One group stands out from all 314.

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

### Does the second attempt work?

Following each job through every re-run — 1,853 job histories in total:

- **982 (53%)** eventually reached an award.
- **871 (47%) never did.** They were tendered, re-tendered, and quietly stopped.

Some were tried repeatedly: 44 jobs went round five times, 41 went six, 22 went seven or
more. **Nearly half the village paths and community halls this department tried to build
never got as far as a contract.**

### Why?

**I don't know, and the documents for this department don't say.** I searched their
paperwork for a stated reason and found **zero**. Elsewhere in the corpus 1,201 documents
do give a reason — most commonly "administrative reasons", "no bid received", or once
memorably "error in creation of tender" — but none of those documents belong to this
department.

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

With the corpus cut into 314 groups, 47 of them have enough tenders (150+) to draw a
conclusion from. Across those, the normal rate is **31.4% rework** and **9.5%
single-bidder**. Against that baseline:

**Worst for work having to be re-run:**

| Department | Work | Tenders | Re-run | Single bidder |
|---|---|---|---|---|
| Development & Panchayats | fencing | 167 | **77.2%** | **59.5%** |
| Development & Panchayats | drainage | 199 | 64.8% | 32.0% |
| Development & Panchayats | (general) | 3,328 | 64.2% | 27.8% |
| Development & Panchayats | building | 239 | 56.1% | 27.4% |
| GMDA | (general) | 495 | 48.9% | 8.4% |
| GMDA | sewer | 181 | 47.0% | 13.3% |

**Worst for only one firm turning up:**

| Department | Work | Tenders | Single bidder |
|---|---|---|---|
| Development & Panchayats | fencing | 167 | **59.5%** |
| PWD (B&R) | street lighting | 238 | **52.7%** |
| PHED | water | 726 | 37.4% |
| PHED | (general) | 1,013 | 35.4% |

Two different problems sit in that table.

**Village fencing is the most extreme thing in the entire corpus.** Three out of four
fencing jobs have to be re-run, and when a firm does bid, six times out of ten it is the
only one. The whole segment is worth ₹4 crore — small money, but these are boundary walls
and fencing for village facilities, and they are failing more than anything else.

**GMDA is the opposite shape.** Roughly half its work is re-run too, but on ₹402 crore
and ₹271 crore of sewer and general infrastructure — and competition there looks normal
(8-13% single-bidder). Big money being re-tendered is a different problem from small jobs
nobody bids for.

**Where you can check the least is often where the money is.** The groups with the worst
document coverage include GMDA general (62% coverage, ₹402 crore) and GMDA sewer (61%,
₹271 crore). PHED water is 55% and PWD street lighting 52% — so the group with the second
highest single-bidder rate is also one of the hardest to verify.

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

## Two things wrong with my own grouping

Someone looked at my tables and said four departments and a handful of work types cannot
be the whole picture. They were right about the cause.

### Nearly half the tenders have no work category at all

Of 49,121 tenders, **21,470 — 43.7% — are filed as "unclassified".** I built 314 groups
out of department × type of work and presented them as meaningful, without checking that
the second half of that pair is empty for nearly half the data. For those tenders a
"group" is really "department × unknown".

It is not that the descriptions are blank. **Every one of the 21,470 has a description.**
The classifier simply does not know the words Haryana public works actually use:

| In the records | What it means |
|---|---|
| IPB | interlocking paver block — a footpath or road surface |
| WBM | water bound macadam — road surface |
| CC locking, RMC M-40 | concrete road surface |
| AR OF LR | annual repair of link roads |
| PAV OF RASTA | paving a village path |
| brick work, CPLASTER | building work |

And three kinds of work are missing from the list of 16 altogether: **annual maintenance
contracts (836 tenders), animal control such as stray-dog sterilisation (70), and
air-conditioning maintenance (49).**

Adding that vocabulary classifies **9,663 of the 21,470 — 45% of them** — and takes the
unclassified share of the whole corpus from **43.7% down to 24%.**

What genuinely cannot be classified is a smaller, stranger set: descriptions with the
spaces stripped out ("operationandmaintenanceSohna", "Gadaipur784FHTC2nd"), and entries
that say only "As per DNIT", "COMPLITION" or "mlc".

### 189 real organisations are being reported as 48

The raw records name **189 separate bodies**, in chains three and four levels deep like
`Haryana Government || Urban Local Bodies || MC Gurgaon`. The build folds them into 48
canonical departments, so MC Gurgaon, MC Manesar, MC Sohna, MC Pataudi and ten others all
become one line reading "Municipal Corporation / Urban Local Bodies" — 18,991 tenders.

**How much that actually hides, honestly:** less than I first suggested. Across those
municipal bodies the re-run rate runs 27.3% to 37.0% against a combined 36.2% — a real
spread but not a dramatic one. Single-bidder rates vary more, from 0.3% at MC Pataudi
Mandi to 9.3% at MC Pataudi and MC Farukh Nagar.

The right structure is two levels — the parent for totals, the 189 individual bodies for
analysis — rather than a flat 48. Neither of these is fixed yet. They are measured and
written down instead of being left inside a table that looks finished.

---

## What I still cannot tell you

- **Whether any money was actually paid.** Nothing in 49,121 records evidences a payment.
- **Whether the work was actually done.** Out of 49,121 tenders there are exactly **three**
  documents confirming a completed work. Not three per cent. Three.
- **Why Development & Panchayats re-tenders two-thirds of its work.** The reason is not
  written down in what was retrieved.
- **What most of the 72,703 evaluation documents contain**, beyond a sample of about 60
  each.

---

## What I would do next

1. Finish reading the 77,020 documents I have not opened, so the "rubber stamp" claim
   becomes a fact rather than a sample.
2. Take the next three or four unusual groups from the 314 and read them the way
   Development & Panchayats was read here.
3. Find out why that department fails so often — it is the largest unexplained pattern
   in the data, and it concerns the works that matter most to villages.
