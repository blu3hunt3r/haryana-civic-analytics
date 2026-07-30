import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../public/data/", import.meta.url);
const overview = JSON.parse(await readFile(new URL("overview.json", root), "utf8"));
const validation = JSON.parse(await readFile(new URL("validation.json", root), "utf8"));
const places = JSON.parse(await readFile(new URL("places.json", root), "utf8"));
const story = JSON.parse(await readFile(new URL("story.json", root), "utf8"));
const intelligenceManifest = JSON.parse(
  await readFile(new URL("intelligence-manifest.json", root), "utf8"),
);
/* The browsing index is now dictionary-encoded and lives in tender-index.json;
   tenders.json (32 MB raw, fetched on boot) was retired with the shard sets. Decoding
   here mirrors loadTenders() in src/data.ts so these invariants keep testing the values
   a reader actually sees rather than the storage form. */
const tenderIndex = JSON.parse(await readFile(new URL("tender-index.json", root), "utf8"));
const dictionaryFields = new Set(tenderIndex.dictionaryFields ?? []);
const tenders = tenderIndex.rows.map((row) => {
  const record = {};
  tenderIndex.schema.forEach((field, index) => {
    const value = row[index];
    record[field] = dictionaryFields.has(field)
      ? (typeof value === "number" ? (tenderIndex.dictionaries[field][value] ?? "") : "")
      : value;
  });
  record.contractorKey = record.contractor || "";
  record.titleKey = record.repeatGroup == null ? "" : `g${record.repeatGroup}`;
  record.areas ??= [];
  return record;
});

test("public headline uses the full verified tender corpus", () => {
  assert.equal(overview.headline.publishedTendersAllScopes, 49_121);
  assert.equal(
    Object.values(overview.scopeMetrics).reduce((sum, row) => sum + row.tenders, 0),
    49_121,
  );
});

test("default view is confirmed Gurugram only", () => {
  assert.equal(overview.headline.confirmedGurugram, 31_241);
  assert.equal(
    overview.headline.confirmedPlusLikelyGurugram,
    overview.scopeMetrics.confirmed_gurugram.tenders +
      overview.scopeMetrics.likely_gurugram.tenders,
  );
});

test("contract value is described as value, never expenditure", () => {
  assert.match(overview.definitions.contractValue, /not money paid/i);
  assert.doesNotMatch(overview.definitions.contractValue, /expenditure/i);
});

test("source reconciliation report passes", () => {
  assert.equal(validation.ok, true);
  assert.ok(validation.checks.every((check) => check.passed));
  /* NAMED COVERAGE, NOT A COUNT. This used to assert checksPassed >= 90, a threshold
     calibrated to the 64-shard layout: 64 `detail_shard_no_duplicate_NN` plus 64
     `intelligence_shard_no_duplicate_NN` checks existed only because there were 64
     files, and they collapsed into two corpus-wide checks that are strictly stronger —
     they compare the whole published ID set at once rather than 64 pairwise
     disjointness tests. The honest total fell to 67, so a raw floor would either fail
     on a correct build or have to be lowered on every refactor. Asserting that the
     invariants that MATTER are present cannot be satisfied by adding filler checks. */
  const names = new Set(validation.checks.map((check) => check.name));
  for (const required of [
    "source_tender_ids_unique",
    "public_tender_ids_unique",
    "public_tender_count",
    "public_tender_id_set",
    "package_count",
    "package_tender_coverage",
    "package_document_coverage",
    "district_contract_values_exclude_multi_district_duplication",
    "place_index_contains_no_invented_boundaries",
  ]) {
    assert.ok(names.has(required), `validation must still cover ${required}`);
  }
  assert.ok(validation.checksPassed >= 60, `only ${validation.checksPassed} checks ran`);
});

test("cancelled and retendered history cannot become controlling contract value", () => {
  for (const row of tenders) {
    if (row.isControllingAward) {
      assert.equal(row.isAwarded, true, row.id);
      assert.notEqual(row.status, "Cancelled", row.id);
      assert.notEqual(row.status, "Retender", row.id);
    }
  }
});

test("one procurement chain contributes at most one controlling award", () => {
  const counts = new Map();
  for (const row of tenders) {
    if (!row.isControllingAward) continue;
    counts.set(row.chainRoot, (counts.get(row.chainRoot) ?? 0) + 1);
  }
  const duplicated = [...counts].filter(([, count]) => count > 1);
  assert.deepEqual(duplicated, []);
});

test("public tender year is derived from the stable Tender ID prefix", () => {
  for (const row of tenders) {
    const match = row.id.match(/^(\d{4})_/);
    if (match) assert.equal(row.year, match[1], row.id);
    if (row.publishedDateConflict) assert.equal(row.month, null, row.id);
  }
});

test("place index is name evidence and never invented boundary geometry", () => {
  assert.equal(places.length, 435);
  assert.equal(
    places.filter((place) => place.boundaryGeometryAvailable).length,
    0,
  );
  const ids = new Set(tenders.map((row) => row.id));
  for (const place of places) {
    for (const id of place.tenderIds) assert.ok(ids.has(id), `${place.name}: ${id}`);
  }
});

test("narrative outcomes partition the confirmed Gurugram corpus", () => {
  assert.equal(
    Object.values(story.confirmedGurugram.outcomes).reduce(
      (sum, value) => sum + value,
      0,
    ),
    story.confirmedGurugram.records,
  );
  assert.equal(story.confirmedGurugram.records, 31_241);
});

test("narrative contract value uses controlling awards only", () => {
  const expected = tenders
    .filter(
      (row) =>
        row.scope === "confirmed_gurugram" && row.isControllingAward,
    )
    .reduce((sum, row) => sum + (row.contractValue ?? 0), 0);
  assert.ok(
    Math.abs(story.confirmedGurugram.contractValue - expected) < 0.01,
  );
  assert.match(story.definitions.contractValue, /not money paid/i);
});

test("completion evidence is preserved as a narrow reviewed subset", () => {
  assert.equal(story.confirmedGurugram.evidence.actualCompletionEvidence, 3);
  assert.ok(
    story.confirmedGurugram.evidence.actualCompletionEvidence <
      story.confirmedGurugram.evidence.awarded,
  );
});

test("knowledge graph retains substantially more relationships than tenders", () => {
  assert.equal(intelligenceManifest.sourceRows.tenders, 49_121);
  assert.ok(intelligenceManifest.knowledgeGraph.entities > 300_000);
  assert.ok(intelligenceManifest.knowledgeGraph.edges > 600_000);
});
