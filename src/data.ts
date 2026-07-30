import type {
  Overview,
  PlaceRecord,
  StoryData,
  TenderDetail,
  TenderIndexRow,
  TenderIntelligence,
} from "./types";

let tenderRowsPromise: Promise<TenderIndexRow[]> | null = null;
let searchRowsPromise: Promise<Map<string, string>> | null = null;
let languagePromise: Promise<Record<string, string>> | null = null;

/* One evidence package per Tender ID, cached by ID rather than by shard.
   The old cache was keyed on a 64-way shard, so the first tender a reader opened pulled
   ~824 unrelated records into memory, every later tender in that shard was free, and
   every tender outside it cost another megabyte. Caching per ID makes the cost
   proportional to what was actually read. */
const packageCache = new Map<string, Promise<TenderPackage>>();

export interface TenderPackage extends TenderDetail {
  intel?: TenderIntelligence;
  packageVersion?: number;
}

/* Raised when a path resolves to nothing we can read as a record. Two cases, and both
   mean the same thing to a reader: the host returned 404, or it returned an HTML page
   because a single-page fallback swallowed the missing file. The second is what GitHub
   Pages does for a directory and what any dev server with an index.html fallback does,
   so treating only the 404 as "absent" made an unknown Tender ID surface as an opaque
   JSON syntax error. */
export class NotPublishedError extends Error {
  constructor(readonly path: string, readonly status: number | null) {
    super(`Nothing published at ${path}${status === null ? "" : ` (HTTP ${status})`}`);
    this.name = "NotPublishedError";
  }
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (response.status === 404) throw new NotPublishedError(path, 404);
  if (!response.ok) throw new Error(`Could not load ${path}: ${response.status}`);
  const text = await response.text();
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new NotPublishedError(path, response.status);
  }
}

export function loadOverview(): Promise<Overview> {
  return getJson<Overview>("/data/overview.json");
}

export function loadStory(): Promise<StoryData> {
  return getJson<StoryData>("/data/story.json");
}

/* The sentences that qualify what a published figure does and does not prove. Exactly
   one distinct value across all 49,121 tenders — verified in build_tender_packages.py
   before it was hoisted — so it is fetched once instead of stored 49,121 times. */
export function loadEvidenceLanguage(): Promise<Record<string, string>> {
  languagePromise ??= getJson<Record<string, string>>("/data/evidence-language.json");
  return languagePromise;
}

/* ── WHERE A TENDER'S EVIDENCE LIVES ──────────────────────────────────────────────
   /data/tender/<sha1(id)[0:2]>/<sha1(id)[2:4]>/<TENDER_ID>.json

   Derived from the ID, so the index carries no shard pointer and a deep link needs no
   lookup table: given only the URL, the client can compute the one file it needs and
   fetch it before the index has even started loading. SubtleCrypto is available on
   every secure origin, which includes GitHub Pages and localhost. */
async function packageUrl(id: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(id));
  const hex = Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
  return `/data/tender/${hex.slice(0, 2)}/${hex.slice(2, 4)}/${encodeURIComponent(id)}.json`;
}

/* One request, measured 2,766 B compressed for a median tender. Replaces a 0.69 MB
   detail shard plus a 0.34 MB intelligence shard — 1.03 MB gzipped to read one record. */
export function loadTenderPackage(id: string): Promise<TenderPackage> {
  let promise = packageCache.get(id);
  if (!promise) {
    promise = packageUrl(id).then((url) => getJson<TenderPackage>(url));
    /* A failure must not stay cached, or one transient network error would make that
       tender permanently unopenable for the rest of the session. */
    promise.catch(() => packageCache.delete(id));
    packageCache.set(id, promise);
  }
  return promise;
}

/* ── THE BROWSING INDEX, DICTIONARY-DECODED ───────────────────────────────────────
   Columns arrive as [literal fields…, dictionary indices…, repeatGroup]. Low-cardinality
   strings — 48 departments, 4 scopes, 10 statuses, 16 components — are integer indices
   into a lookup table instead of 49,121 repeated strings, which took the file from
   19.26 MB to 9.40 MB raw and 3.42 MB to 2.08 MB compressed.

   `null` in a dictionary column means the value was ABSENT. It decodes to "" because
   that is what every filter in main.ts compares against, and `contractor === ""` already
   carries "not published" throughout the UI. */
interface IndexPayload {
  indexVersion: number;
  schema: string[];
  dictionaries: Record<string, string[]>;
  dictionaryFields: string[];
  rows: unknown[][];
  count: number;
}

export function loadTenders(): Promise<TenderIndexRow[]> {
  tenderRowsPromise ??= getJson<IndexPayload>("/data/tender-index.json").then(
    (payload) => {
      const dictionaryFields = new Set(payload.dictionaryFields ?? []);
      return payload.rows.map((values) => {
        const row: Record<string, unknown> = {};
        payload.schema.forEach((field, position) => {
          const value = values[position];
          if (dictionaryFields.has(field)) {
            const table = payload.dictionaries[field] ?? [];
            row[field] = typeof value === "number" ? (table[value] ?? "") : "";
          } else {
            row[field] = value;
          }
        });
        /* Fields the index no longer carries, reconstructed here so no consumer needs
           to special-case the new shape:
             contractorKey — was 1:1 with the contractor dictionary index.
             titleKey      — only the repeated-work filter read it, and only for titles
                             that actually recur; `repeatGroup` is that identity as an
                             integer, and "" means this work title is unique.
             areas         — the largest field in the old 32 MB index. The map and the
                             evidence page read geography from the tender's own package;
                             an empty list here is honest, because the index genuinely
                             does not carry it. */
        row.contractorKey = row.contractor || "";
        row.titleKey =
          row.repeatGroup === null || row.repeatGroup === undefined
            ? ""
            : `g${row.repeatGroup}`;
        row.areas ??= [];
        return row as unknown as TenderIndexRow;
      });
    },
  );
  return tenderRowsPromise;
}

export function loadSearchIndex(): Promise<Map<string, string>> {
  searchRowsPromise ??= getJson<Array<[string, string]>>(
    "/data/search-index.json",
  ).then((rows) => new Map(rows));
  return searchRowsPromise;
}

export function loadPlaces(): Promise<PlaceRecord[]> {
  return getJson<PlaceRecord[]>("/data/places.json");
}

/* Kept as the two call shapes main.ts already used, so the delivery change did not have
   to be threaded through every call site at once. Both now resolve from one per-tender
   request. The old `shard` argument is gone: it described a layout that no longer
   exists, and leaving it would invite a caller to trust a dead field. */
export async function loadTenderDetail(id: string): Promise<TenderDetail> {
  return (await loadTenderPackage(id)) as TenderDetail;
}

export async function loadTenderIntelligence(
  id: string,
): Promise<TenderIntelligence | null> {
  return (await loadTenderPackage(id)).intel ?? null;
}
