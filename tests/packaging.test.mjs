/* Acceptance tests for the per-tender delivery layout.
 *
 * These exist because the previous layout published the same 49,121 Tender IDs in two
 * identically-keyed 64-file shard sets, and nothing asserted that a reader could
 * actually reach a given tender. The requirements this file answers directly:
 *
 *   "Prove all 49,121 Tender IDs resolve to an evidence page."
 *   "Prove intelligence packaging has no duplicate or missing Tender IDs."
 *
 * Everything is checked against files on disk, so a build that forgot to write a
 * package fails here rather than 404-ing for a citizen.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import test from "node:test";

const dataDir = new URL("../public/data/", import.meta.url);
const read = async (name) => JSON.parse(await readFile(new URL(name, dataDir), "utf8"));

const manifest = await read("tender-manifest.json");
const index = await read("tender-index.json");
const overview = await read("overview.json");

/* The same derivation the client performs in data.ts packageUrl(). Duplicating the
   two lines here is deliberate: if the client's path scheme and the builder's ever
   diverge, every tender 404s, and this is the assertion that catches it. */
function packagePath(id) {
  const hex = createHash("sha1").update(id, "utf8").digest("hex");
  return new URL(`tender/${hex.slice(0, 2)}/${hex.slice(2, 4)}/${id}.json`, dataDir);
}

const EXPECTED_TENDERS = 49_121;

test("the index carries every tender exactly once", () => {
  assert.equal(index.count, EXPECTED_TENDERS, "index count");
  assert.equal(index.rows.length, EXPECTED_TENDERS, "index rows");
  const idColumn = index.schema.indexOf("id");
  assert.ok(idColumn >= 0, "index schema declares an id column");
  const ids = index.rows.map((row) => row[idColumn]);
  assert.equal(new Set(ids).size, EXPECTED_TENDERS, "no duplicate Tender ID in the index");
  assert.ok(
    ids.every((id) => typeof id === "string" && id.length > 0),
    "every index row has a non-empty Tender ID",
  );
});

test("the manifest agrees with the index and with the archive", () => {
  assert.equal(manifest.tenderCount, EXPECTED_TENDERS);
  assert.equal(manifest.packageVersion, 2);
  assert.equal(overview.headline.publishedTendersAllScopes, EXPECTED_TENDERS);
});

test("every Tender ID resolves to an evidence package on disk", async () => {
  const idColumn = index.schema.indexOf("id");
  const ids = index.rows.map((row) => row[idColumn]);
  const missing = [];
  const empty = [];
  /* Batched so 49,121 stats do not open 49,121 descriptors at once. */
  const BATCH = 512;
  for (let start = 0; start < ids.length; start += BATCH) {
    const slice = ids.slice(start, start + BATCH);
    const results = await Promise.all(
      slice.map(async (id) => {
        try {
          const info = await stat(packagePath(id));
          return { id, size: info.size };
        } catch {
          return { id, size: null };
        }
      }),
    );
    for (const result of results) {
      if (result.size === null) missing.push(result.id);
      else if (result.size < 200) empty.push(result.id);
    }
  }
  assert.deepEqual(missing.slice(0, 5), [], `${missing.length} Tender IDs have no package`);
  assert.equal(missing.length, 0);
  assert.equal(empty.length, 0, `${empty.length} packages are implausibly small`);
});

test("no package exists for a Tender ID the index does not list", async () => {
  /* The reverse direction. A stale package left behind by an earlier build would be
     reachable by URL while being absent from every filter and count — a record the
     portal serves but does not admit to having. */
  const { readdir } = await import("node:fs/promises");
  const root = fileURLToPath(new URL("tender/", dataDir));
  const idColumn = index.schema.indexOf("id");
  const known = new Set(index.rows.map((row) => row[idColumn]));
  let found = 0;
  const orphans = [];
  for (const outer of await readdir(root)) {
    for (const inner of await readdir(`${root}${outer}`)) {
      for (const file of await readdir(`${root}${outer}/${inner}`)) {
        if (!file.endsWith(".json")) continue;
        found += 1;
        const id = file.slice(0, -5);
        if (!known.has(id)) orphans.push(id);
      }
    }
  }
  assert.equal(found, EXPECTED_TENDERS, "package file count");
  assert.deepEqual(orphans.slice(0, 5), [], `${orphans.length} orphaned packages`);
});

test("the dictionary encoding round-trips to real values", async () => {
  for (const field of index.dictionaryFields) {
    assert.ok(Array.isArray(index.dictionaries[field]), `${field} has a dictionary`);
    assert.ok(index.dictionaries[field].length > 0, `${field} dictionary is populated`);
    /* An index must never point past its table, and a table must not hold nulls: null
       is carried in the ROW to mean "absent", which is a different fact. */
    assert.ok(
      index.dictionaries[field].every((value) => value !== null && value !== ""),
      `${field} dictionary holds no null or empty entries`,
    );
  }
  const column = {};
  index.schema.forEach((field, position) => { column[field] = position; });
  for (const field of index.dictionaryFields) {
    const size = index.dictionaries[field].length;
    const bad = index.rows.find((row) => {
      const value = row[column[field]];
      return value !== null && (typeof value !== "number" || value < 0 || value >= size);
    });
    assert.equal(bad, undefined, `${field} has an out-of-range dictionary index`);
  }
  /* The four scope classifications are a published fact, not an implementation detail. */
  assert.deepEqual(
    [...index.dictionaries.scope].sort(),
    ["confirmed_gurugram", "likely_gurugram", "not_gurugram", "statewide_multi_location"],
  );
});

test("dictionary decoding reproduces the published scope split", () => {
  const column = {};
  index.schema.forEach((field, position) => { column[field] = position; });
  const counts = new Map();
  for (const row of index.rows) {
    const scope = index.dictionaries.scope[row[column.scope]];
    counts.set(scope, (counts.get(scope) ?? 0) + 1);
  }
  assert.equal(counts.get("confirmed_gurugram"), 31_241);
  assert.equal(counts.get("likely_gurugram"), 6_660);
  assert.equal(counts.get("statewide_multi_location"), 3_328);
  assert.equal(counts.get("not_gurugram"), 7_892);
  assert.equal(
    [...counts.values()].reduce((sum, n) => sum + n, 0),
    EXPECTED_TENDERS,
    "the scope split sums to the corpus",
  );
});

test("controlling awards reproduce the published contract value", () => {
  const column = {};
  index.schema.forEach((field, position) => { column[field] = position; });
  let controlling = 0;
  let value = 0;
  for (const row of index.rows) {
    if (index.dictionaries.scope[row[column.scope]] !== "confirmed_gurugram") continue;
    if (!row[column.isControllingAward]) continue;
    controlling += 1;
    if (typeof row[column.contractValue] === "number") value += row[column.contractValue];
  }
  assert.equal(controlling, 9_306, "controlling awards in confirmed Gurugram");
  /* Float addition over 9,306 terms, so compare to the paisa rather than the bit. */
  assert.ok(
    Math.abs(value - 83_295_707_464.37) < 1,
    `controlling contract value ${value} should be 83,295,707,464.37`,
  );
});

test("the three reviewed actual-completion records are carried, and only those", async () => {
  /* The archive holds exactly three `confirmed_actual_completion_record` rows. A naive
     "has a completion date" query returns four, because one summary row joins all three
     dates with pipes — so this asserts the identities, not a count from a loose filter. */
  const reviewed = {
    "2021_HRY_175218_1": "09 September 2022",
    "2021_HRY_175485_1": "31-Jan-22",
    "2021_HRY_185859_1": "28-02-2022",
  };
  for (const [id, date] of Object.entries(reviewed)) {
    const pkg = JSON.parse(await readFile(packagePath(id), "utf8"));
    const records = pkg.intel?.actualCompletionEvidence ?? [];
    assert.ok(
      records.length >= 1,
      `${id} should carry reviewed completion evidence`,
    );
    assert.ok(
      records.some((record) => String(record.date ?? "").includes(date.slice(0, 6))),
      `${id} should carry the reviewed completion date ${date}, got ${JSON.stringify(records)}`,
    );
  }
});

test("a package never claims completion evidence it does not have", async () => {
  /* Sampled rather than exhaustive: reading 49,121 files in a unit test is minutes of
     wall clock. A deterministic stride covers every hash prefix and every year. */
  const idColumn = index.schema.indexOf("id");
  const ids = index.rows.map((row) => row[idColumn]);
  const sample = [];
  for (let i = 0; i < ids.length; i += Math.floor(ids.length / 400)) sample.push(ids[i]);
  let withEvidence = 0;
  for (const id of sample) {
    const pkg = JSON.parse(await readFile(packagePath(id), "utf8"));
    const records = pkg.intel?.actualCompletionEvidence ?? [];
    assert.ok(Array.isArray(records), `${id} actualCompletionEvidence is a list`);
    if (records.length) {
      withEvidence += 1;
      for (const record of records) {
        assert.ok(record.date, `${id} completion record must carry a date`);
      }
    }
    /* The distinctions the brief requires the record to keep. A package may not fold a
       schedule into a completion, or a contract value into a payment. */
    assert.ok(!("paidValue" in pkg), `${id} must not publish a paid value`);
    assert.ok(!("actualCompletion" in pkg), `${id} must not publish a bare actualCompletion`);
  }
  assert.ok(
    withEvidence <= 1,
    `at most one sampled tender should carry completion evidence, saw ${withEvidence}`,
  );
});

test("evidence language is published once, not per tender", async () => {
  const shared = await read("evidence-language.json");
  assert.ok(shared.contractValue, "the contract-value qualifier is published");
  assert.match(shared.contractValue, /not money paid/i);
  assert.match(shared.scheduledCompletion, /not evidence of actual completion/i);
  const idColumn = index.schema.indexOf("id");
  const pkg = JSON.parse(await readFile(packagePath(index.rows[0][idColumn]), "utf8"));
  assert.equal(
    pkg.evidenceLanguage,
    undefined,
    "a package must not repeat the shared evidence language",
  );
});

test("packages stay small enough to open one tender cheaply", () => {
  /* The requirement is "no 3 MB intelligence shard to open one tender". Asserting the
     measured distribution keeps a future field addition from quietly undoing it. */
  assert.ok(manifest.packageBytes.median < 16_000, `median ${manifest.packageBytes.median} B`);
  assert.ok(manifest.packageBytes.p95 < 24_000, `p95 ${manifest.packageBytes.p95} B`);
  assert.ok(manifest.packageBytes.max < 200_000, `max ${manifest.packageBytes.max} B`);
});
