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
| Source-reconciliation assertions | 103 passed |
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

## Supported claims

- What an authority invited bids for.
- Which current-status tenders have a verified published award.
- The published controlling contract value, where present.
- The contractor name, where the authority publishes it.
- Published department, work description, location references and dates.
- Cancellation/retender history and document metadata.
- Exact source-page and downloaded-document hashes.

## Unsupported claims

- Money actually paid.
- Physical completion.
- Certified completion date.
- Measurement-book quantities.
- Quality test outcome.
- A live defect-liability/warranty obligation.
- Proof that a broad area-level tender covered the citizen's exact location.

The interface states these limits next to the relevant metrics rather than
burying them in a disclaimer.

