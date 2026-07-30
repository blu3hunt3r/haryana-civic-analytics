# Audit of commit `bccbb9e` — measured, not reviewed

Every number below was produced by running against the archive and against the live
deployment. Nothing here is taken from the brief or from the previous implementation's
own reports.

Method: counts recomputed directly from `/Users/ab/Downloads/civic-stuff` with
independent scripts; performance measured over the Chrome DevTools Protocol against
`https://haryana.civicvoiceofindia.org/` with the HTTP cache disabled.

---

## 1. The headline figures are correct

All ten claimed corpus figures reproduce **exactly**, once the correct definitions are
used. This is the strongest part of the existing work and it is being kept.

| Figure | Claimed | Recomputed | Source and definition |
|---|---|---|---|
| Tender IDs | 49,121 | **49,121** | `data/final/tenders.csv`, distinct `tender_id`; rows = ids, so no duplicates |
| Confirmed Gurugram | 31,241 | **31,241** | `gurugram_scope.csv`, `scope_classification = confirmed_gurugram` |
| Confirmed + awarded | 13,398 | **13,398** | joined to `procurement_chains.csv`, `award_state = AWARD_CONFIRMED` |
| Controlling awards | 9,306 | **9,306** | award confirmed **and** not chain-ambiguous **and** `terminal_tender_id` is itself or empty |
| Controlling contract value | ₹83,295,707,464.37 | **₹83,295,707,464.37** | sum of `aoc_total_contract_value_inr` over those 9,306 |
| Bid-stage records | 103,258 | **103,258** | `bid_history.csv` rows |
| Lifecycle events | 339,034 | **339,034** | `tender_lifecycle_events.csv` rows |
| Review flags | 10,112 | **10,112** | `procurement_flags.csv` rows |
| Graph entities | 336,539 | **336,539** | `build/knowledge-graph.sqlite`, `entity` |
| Graph relationships | 658,194 | **658,194** | same, `edge` |

Two definitional notes that matter and are **not** currently published anywhere in the UI:

- The full scope split is `confirmed_gurugram 31,241 / likely_gurugram 6,660 /
  statewide_multi_location 3,328 / not_gurugram 7,892`. It sums to 49,121 exactly.
- "Awarded" has three plausible definitions in the data that give **different answers**:
  `stage_aoc = complete` → 20,618; `current_status = 'AOC'` → 20,609;
  `award_state = AWARD_CONFIRMED` → 20,609 with a further 9 `AWARD_STATUS_CONFLICT`.
  The portal uses the third. That is the defensible choice, but the 9 conflicts are
  currently invisible to a reader, and my first attempt at the count was wrong by 5
  records precisely because the difference is undocumented.

### The three reviewed actual-completion records verify

`data/derived/completion_evidence_scan.csv` holds 1,671 rows, of which
`record_type = confirmed_actual_completion_record` is exactly **3**:

| Tender | Actual completion | Document | sha256 verified |
|---|---|---|---|
| `2021_HRY_175218_1` | 09 September 2022 | `175218WO.pdf` p1 | true |
| `2021_HRY_175485_1` | 31-Jan-22 | `completion175485.pdf` p1 | true |
| `2021_HRY_185859_1` | 28-02-2022 | `completion185859.pdf` p1 | true |

A fourth row carries all three dates joined by `|` under
`record_type = completion_gap_summary`; it is a summary, not a fourth record. A naive
"rows with an actual_completion_date" query returns 4 and would over-report.

The three dates arrive in **three different formats** (`09 September 2022`,
`31-Jan-22`, `28-02-2022`). They are not normalised anywhere in the pipeline.

The remaining 1,650 `phrase_hit` rows are labelled
`text_hit_only_not_proof_of_actual_completion`, and 4 documents are
`not_searchable_without_ocr`. That labelling is honest and worth keeping.

---

## 2. Production is broken

The live site does not start. It renders:

> The analytics portal could not start.
> Error: {"requestedAttributes":… "statusMessage":"Could not create a WebGL context…"}

**Cause.** `src/main.ts` wraps the entire bootstrap in one `try/catch` (line 1281) and
initialises the MapLibre map inside it. When a WebGL context cannot be created the
exception escapes map setup and destroys the **whole application** — story, charts,
tender index and search included, none of which need WebGL.

**Who this hits.** Anyone with WebGL disabled or blacklisted: hardened browser
profiles, privacy extensions, older Android WebViews, corporate policy, remote desktop
sessions, and every headless environment — which is why the previous visual QA did not
catch it. An optional decorative dependency currently gates a public accountability
record.

This is the single most serious defect found and it is fixed first.

## 3. Cold load is 5.78 MB, not 0.72 MB

Measured at 1440×900, cache disabled, software WebGL enabled so the app actually runs:

| | measured |
|---|---|
| Cold-load requests | **45** |
| Cold-load transferred | **5.78 MB** (target: < 1.5 MB) |
| Total to reach one tender | **8.51 MB over 47 requests** |
| FCP | 996 ms |
| DCL | 1,016 ms |
| Console errors | 0 |

Largest single responses on the boot path:

| Bytes (compressed) | Path |
|---|---|
| 3.69 MB | `/data/tenders.json` — the full 49,121-row index, fetched on boot |
| 1.24 MB | `/data/geo/haryana_districts.geojson` |
| 0.69 MB | `/data/tender-details/60.json` |
| 0.34 MB | `/data/intelligence/60.json` |
| 0.31 MB | `natural_earth/…/26.png` — third-party raster tile |

Measuring against the *dead* app reports a misleading 0.72 MB / 11 requests. Any
performance claim made without confirming the app rendered is meaningless, which is
probably how "approximately 8.5 seconds" was arrived at.

## 4. Tender delivery is duplicated end to end

`public/data/intelligence/` (64 files, 177 MB) and `public/data/tender-details/`
(64 files, 233 MB) are **identically keyed**: both contain exactly the same 49,121
Tender IDs, verified set-equal.

Worse, the payloads overlap:

- `understanding.places` in the intelligence shard is **byte-identical** to `areas` in
  the details shard — in **49,121 of 49,121 records**, zero exceptions. It is the
  largest field in both (5,237 B in the worst record).
- `evidenceLanguage` has exactly **one distinct value** across all 49,121 records. The
  same three sentences are stored 49,121 times.

Opening one tender therefore costs two shard fetches — measured **+1.03 MB
compressed**, ~7 MB raw — of which the reader wants one record.

A merged, deduplicated per-tender package measures:

| | bytes |
|---|---|
| min | 4,694 |
| **median** | **8,358** |
| p95 | 11,800 |
| max | 35,000 |
| total | 385.8 MB (from 438 MB) |

So the tender-open path can drop from ~1 MB compressed to **~8.4 KB raw** — a ~100×
reduction — with no loss of any published field.

## 5. `/tenders/<id>` does not work

Navigating directly to `https://haryana.civicvoiceofindia.org/#/tenders/2025_HBC_481661_1`
loads the shell and then clears the hash (`location.hash` reads `""` afterwards, no
detail element is rendered). The route is only consulted after boot completes, and boot
writes the URL back (`main.ts:1123`). Acceptance test 16 fails today.

## 6. What to keep and what to replace

**Keep — it is correct and expensive to rebuild**

- `scripts/build_analytics.py` aggregate definitions, including `controlling_award()`,
  which is a careful and defensible rule and reproduces exactly.
- The scope classification and its four-way split.
- The evidence labelling vocabulary: `text_hit_only_not_proof_of_actual_completion`,
  `not_searchable_without_ocr`, `contractor_withheld`, `not_an_accusation` on flags.
- Source hashes carried per tender (`status`, `summary`, `detail`, `frontTender`).
- `docs/METRICS.md` and `docs/VALIDATION.md` as a starting shape.

**Replace**

- The two shard sets → one deduplicated package per Tender ID.
- Boot-time fetch of the 3.69 MB index → lazy, and slimmer.
- One bootstrap `try/catch` → per-subsystem isolation, so no optional visual
  dependency can take down the record.
- Hash-only routing that the app erases → real, restorable tender URLs.

**Add**

- A published definition for every metric: numerator, denominator, exclusions, source
  table, source hash, dataset version, limitation.
- Explicit exclusion rules for the estimate-to-award comparison (see §7), which the
  current builder does not apply.

## 7. Known data hazards found while auditing

- **Degenerate contract values.** `aoc_total_contract_value_inr = 1` appears on **283**
  tenders overall, of which **178 are controlling awards** and so currently contribute
  to the published ₹83.3 bn. Among the 9,306 controlling awards, **302** are below
  ₹1,000 and **213** are below ₹10; the minimum is **₹0.40**. These are placeholder or
  unit artefacts, not contracts of that size. They are individually tiny so they do not
  distort the total, but they must be excluded from any *ratio*.
- **Estimate-to-award is unusable without exclusions.** Only **8,440 of 9,306**
  controlling awards have a non-zero `tender_value_inr` denominator. Across those the
  median award/estimate ratio is a plausible **0.9493**, but the maximum is
  **126,331,980** — 12 ratios exceed 100 and 266 fall below 0.01. Any published
  estimate-to-award figure must state the 866 excluded for an unusable denominator and
  the outlier rule applied, or it is arithmetic on unit errors.
- `stage_aoc` is populated for all 49,121 rows with the literal strings
  `complete` / `not_complete`; it is not a date and must not be treated as one.
- `contractor_withheld` is `false` for all 20,575 rows where it is present and empty
  otherwise, so it currently distinguishes nothing. Absence of a contractor is carried
  by `winning_contractor` being empty, which happens for 28,546 tenders.
- Titles are truncated in the corpus; `work_description` is the classification field.
  The existing builder already respects this.
