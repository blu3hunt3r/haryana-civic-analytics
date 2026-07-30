# Validation report

Dataset version: `2026-07-28.1`

## Reconciled public snapshot

| Check | Result |
| --- | ---: |
| Unique tender records | 49,121 |
| Confirmed Gurugram | 31,241 |
| Confirmed + likely Gurugram | 37,901 |
| Confirmed awarded contracts | 13,398 |
| Confirmed controlling contract value | ₹8,329.57 crore |
| Source-reconciliation assertions | 195 passed |
| Invariant tests | 12 passed |
| Knowledge-graph entities | 336,539 |
| Typed relationships | 658,194 |
| Bid-stage records | 103,258 |
| Lifecycle events | 339,034 |
| Deterministic review flags | 10,112 |
| Reviewed actual completion records | 3 |
| HEWP exact Tender-ID links | 4,654 |
| MCG public-work links | 237 (52 exact; 185 candidate) |
| Validated contract-to-road links | 23 |
| Gurugram village/town names | 435 |
| Browser QA | Desktop and mobile passed |
| Browser console/page/request errors | 0 |
| Horizontal overflow | 0 |

The machine-readable report is
[`public/data/validation.json`](../public/data/validation.json). Source file
paths, SHA-256 values, byte counts, geometry provenance and known limitations are
in [`public/data/manifest.json`](../public/data/manifest.json).

## Automated misleading-claim protections

The test suite verifies that:

1. the public scope counts reconcile to all 49,121 unique Tender IDs;
2. the initial view is confirmed Gurugram only;
3. contract value is described as value, never as expenditure;
4. cancelled and retendered records cannot become controlling awards;
5. each procurement chain contributes at most one controlling award;
6. displayed tender year follows the stable Tender ID prefix;
7. a conflicting portal publication date cannot create a false month.
8. every place-linked Tender ID resolves to the public tender index;
9. HEWP, MCG and confirmed asset-link counts reconcile to their source tables;
10. no village polygon is invented when the archive only supplies names;
11. the guided story partitions all 49,121 records without loss;
12. its confirmed controlling-award value matches the primary analytics;
13. every intelligence shard is duplicate-free and all Tender IDs resolve;
14. actual completion is only exposed for the three reviewed evidence records;
15. the published graph summary matches the 336,539-entity,
    658,194-relationship local build.

## Supported claims

- What an authority invited bids for.
- Which current-status tenders have a verified published award.
- The published controlling contract value, where present.
- The contractor name, where the authority publishes it.
- Published department, work description, location references and dates.
- Cancellation/retender history and document metadata.
- Bid-stage and lifecycle records attached to the same Tender ID.
- Three reviewed records that establish an actual completion date for the
  named work, with their evidence references.
- Exact source-page and downloaded-document hashes.

## Unsupported claims

- Money actually paid.
- Physical completion for the remaining tender corpus.
- A complete certified-completion register.
- Measurement-book quantities.
- Quality test outcome.
- A live defect-liability/warranty obligation.
- Proof that a broad area-level tender covered the citizen's exact location.

The interface states these limits next to the relevant metrics rather than
burying them in a disclaimer.
