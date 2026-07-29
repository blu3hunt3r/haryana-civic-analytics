import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../public/data/", import.meta.url);
const overview = JSON.parse(await readFile(new URL("overview.json", root), "utf8"));
const validation = JSON.parse(await readFile(new URL("validation.json", root), "utf8"));
const places = JSON.parse(await readFile(new URL("places.json", root), "utf8"));
const tenderIndex = JSON.parse(await readFile(new URL("tenders.json", root), "utf8"));
const tenders = tenderIndex.rows.map((row) =>
  Object.fromEntries(tenderIndex.schema.map((field, index) => [field, row[index]])),
);

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
  assert.ok(validation.checksPassed >= 90);
  assert.ok(validation.checks.every((check) => check.passed));
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
