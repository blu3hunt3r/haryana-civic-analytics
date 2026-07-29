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
npm run data:validate
npm test
npm run dev
```

The generated evidence snapshot is committed because GitHub Pages has no access
to the private local archive during deployment. Rebuilds remain reproducible on a
machine that has the verified source corpus.

## Product surface

- Zoomable Haryana district map with a Gurugram ward/sector/road drill-down.
- Linked lifecycle, time, value, department and work-family views.
- Department-by-work-family heatmap.
- Competition, contractor-concentration and procurement-chain views.
- Repeated-work review signals.
- Full tender search and evidence detail with document/source SHA-256 values.
- Dataset freshness, confidence labels and explicit missing-evidence states.

See [metric definitions](docs/METRICS.md) and the
[validation report](docs/VALIDATION.md).

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
