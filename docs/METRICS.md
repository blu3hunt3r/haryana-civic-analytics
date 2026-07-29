# Metric definitions

Dataset version: `2026-07-28.1`

The portal keeps four facts separate:

| Term | What it means | What it does not mean |
| --- | --- | --- |
| Published tender | An authority invited bids | Work started or finished |
| Awarded contract | The current portal status is AOC and the award is verified | Money was paid |
| Scheduled completion | The contract publishes an intended duration | Actual or certified completion |
| Actual completion | A certified completion record establishes delivery | Not currently established by this tender archive |

## Headline metrics

- **Published tender records** counts unique `tender_id` rows in the selected
  geographic-confidence scope.
- **Awarded contracts** counts `award_state = AWARD_CONFIRMED`.
- **Published contract value** sums only the unique controlling award in each
  procurement chain. It is not expenditure or money paid.
- **Cancelled or retendered** counts tender records with those current statuses.
  Their estimates do not contribute to contract value.

## Geography

- The default scope is `confirmed_gurugram`.
- `likely_gurugram`, `statewide_multi_location`, and `not_gurugram` are separate,
  opt-in confidence classes.
- A district match requires an explicit district-name reference in a published
  location, work description, or organisation field.
- Multi-district contract values are not copied into every district.
- Ward and sector selections are text-evidence filters, not proof that every
  point inside the polygon is covered by the tender.
- Roads on the map are context until an exact, validated contract-to-asset link
  exists.

## Work families

Work families are deterministic rules applied first to the full
`work_description`. A truncated title is a lower-confidence fallback. Records
that do not match remain `unclassified`; they are never silently forced into a
category.

## Contractors and competition

- Contractor normalisation is name-only because a stable government contractor
  identifier is not consistently published.
- Concentration is calculated from controlling awards with a published
  contractor name and value in the current filtered view.
- Published awarded-bid count is not necessarily the number of all bids
  received. The portal uses the narrower official fact.
- Repeated descriptions and high concentration are review signals, not
  allegations.

## Evidence and provenance

Every tender detail includes source-page SHA-256 hashes. Document rows include
the published filename, portal section, retrieval outcome, hash when downloaded,
and the official link when available. The 75 GB raw blob archive is retained
outside this public repository.

