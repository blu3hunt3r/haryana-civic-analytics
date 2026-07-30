# Haryana Civic Analytics

Evidence-backed public procurement analytics for Civic Voice of India.

The site is intentionally separate from NagarSaakshi and is designed for
`haryana.civicvoiceofindia.org`.

## Evidence boundary

The 75 GB Haryana portal archive is not committed. `scripts/build_analytics.py`
reads the verified local corpus and emits compact, public, versioned JSON under
`public/data/`. Every published metric records the source dataset hashes used to
derive it.

```bash
CIVIC_DATA_ROOT=/path/to/civic-stuff npm run data:build
npm run data:intelligence
npm run data:validate
npm test
npm run dev
```

The generated evidence snapshot is committed because GitHub Pages has no access
to the private local archive during deployment. Rebuilds remain reproducible on a
machine that has the verified source corpus.

For unattended refreshes, the resumable orchestrator fingerprints the
heterogeneous source tables, rebuilds only after a change, and records each
completed stage in `build/pipeline-state.json`:

```bash
CIVIC_DATA_ROOT=/path/to/civic-stuff npm run pipeline
CIVIC_DATA_ROOT=/path/to/civic-stuff npm run pipeline:watch
```

An interrupted run resumes at the first incomplete stage as long as its source
fingerprints have not changed. A changed source invalidates the derived stages
and triggers a clean deterministic rebuild.

## Product surface

- A guided, full-corpus narrative showing how 49,121 published tender records
  narrow through award, evidence, competition, repeat-work, and contractor
  relationships.
- Zoomable Haryana district map with a Gurugram ward/sector/road drill-down.
- Linked lifecycle, time, value, department and work-family views.
- Department-by-work-family heatmap.
- Competition, contractor-concentration and procurement-chain views.
- Repeated-work review signals.
- Searchable HEWP village/town index without invented boundary geometry.
- Exact Tender-ID HEWP links, graded MCG links, and validated road-asset links
  on the tender evidence page.
- Full tender search and an on-demand intelligence record for every Tender ID:
  bid-stage rows, lifecycle events, review flags, linked evidence, and
  document/source SHA-256 values.
- Dataset freshness, confidence labels and explicit missing-evidence states.

See [metric definitions](docs/METRICS.md) and the
[validation report](docs/VALIDATION.md).

## Relationship model

The local builder materialises a typed knowledge graph in
`build/knowledge-graph.sqlite`. Its current snapshot contains 336,539 entities
and 658,194 relationships spanning tenders, departments, work components,
contractors, bidders, places, documents, procurement chains, HEWP works, MCG
works, and validated assets.

The SQLite graph is an uncommitted build artifact. The public site receives
compact narrative aggregates plus 64 deterministic, on-demand tender
intelligence shards. A tender and its associated records therefore remain
inspectable without loading the entire relationship graph into the browser.

## Deployment

The GitHub Pages workflow publishes this repository independently to
`haryana.civicvoiceofindia.org`. `public/CNAME` owns the custom-domain setting.
The DNS zone must point `haryana` to `blu3hunt3r.github.io` with a CNAME record.

## Language rules

- A **published tender** is an invitation to bid.
- An **awarded contract** is a verified AOC result.
- **Contract value** is not money paid.
- **Scheduled completion** is not actual completion.
- Cancelled and retendered records are never summed as expenditure.
- Statewide contracts are never assigned in full to Gurugram.
- Automated indicators are labelled review flags, not allegations.
