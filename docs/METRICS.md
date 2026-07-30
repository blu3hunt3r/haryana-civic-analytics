# Metric definitions

Dataset version: `2026-07-28.1`

The portal keeps four facts separate:

| Term | What it means | What it does not mean |
| --- | --- | --- |
| Published tender | An authority invited bids | Work started or finished |
| Awarded contract | The current portal status is AOC and the award is verified | Money was paid |
| Scheduled completion | The contract publishes an intended duration | Actual or certified completion |
| Reviewed actual completion record | A local evidence review found wording that establishes an actual completion date for the named work | Complete execution evidence for other contracts, payment, quality acceptance, or an active warranty |

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
- The HEWP place index exposes 435 village/town names and their exact Tender-ID
  links. The local archive has no usable village-boundary geometry, so places
  are searchable but are not drawn as made-up polygons.

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

## Evidence funnel

The default confirmed-Gurugram story deliberately narrows rather than treating
all records as equivalent:

| Evidence stage | Records |
| --- | ---: |
| Current status is awarded | 13,398 |
| Published award value is present | 13,398 |
| Contractor name is published | 13,379 |
| An AOC/LOA-stage document was downloaded | 13,367 |
| Exact HEWP Tender-ID link exists | 4,622 |
| Reviewed actual completion record exists | 3 |

The funnel measures evidence availability. It does not mean the other works
were not completed; it means the local public record does not establish their
actual completion.

## Per-tender intelligence

Every Tender ID resolves to an intelligence shard containing:

- its typed relationships to department, work component, contractor, place,
  document, bidder, procurement chain, HEWP/MCG work, and validated asset where
  present;
- every published bid-stage row;
- every extracted lifecycle event;
- deterministic procurement review flags;
- an evidence ladder that marks each stage present or missing;
- reviewed actual-completion evidence, for the three records where it exists.

Relationships encode published association, not causal proof. A bidder row is
not automatically a losing bid; a place reference is not proof of exact
geographic coverage; a review flag is not an allegation.

## Cross-portal links

- HEWP links are contractual identity only when the public HEWP row and GePNIC
  row share the exact Tender ID.
- MCG links labelled `exact` carry the Tender ID in the MCG work name.
- Normalized MCG title matches remain candidates even when their amounts agree.
- Contract-to-road links render only when the offline route validator returned
  `CONFIRMED` / proof grade B. Refuted and weak links stay out of public claims.

## Evidence and provenance

Every tender detail includes source-page SHA-256 hashes. Document rows include
the published filename, portal section, retrieval outcome, hash when downloaded,
and the official link when available. The 75 GB raw blob archive is retained
outside this public repository.
