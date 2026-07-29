import type {
  Overview,
  PlaceRecord,
  TenderDetail,
  TenderIndexRow,
} from "./types";

let tenderRowsPromise: Promise<TenderIndexRow[]> | null = null;
let searchRowsPromise: Promise<Map<string, string>> | null = null;
const detailCache = new Map<number, Promise<Record<string, TenderDetail>>>();

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Could not load ${path}: ${response.status}`);
  return response.json() as Promise<T>;
}

export function loadOverview(): Promise<Overview> {
  return getJson<Overview>("/data/overview.json");
}

export function loadTenders(): Promise<TenderIndexRow[]> {
  tenderRowsPromise ??= getJson<{ schema: string[]; rows: unknown[][] }>(
    "/data/tenders.json",
  ).then(({ schema, rows }) =>
    rows.map((values) =>
      Object.fromEntries(
        schema.map((field, index) => [field, values[index]]),
      ) as unknown as TenderIndexRow,
    ),
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

export async function loadTenderDetail(
  id: string,
  shard: number,
): Promise<TenderDetail> {
  let promise = detailCache.get(shard);
  if (!promise) {
    promise = getJson<Record<string, TenderDetail>>(
      `/data/tender-details/${String(shard).padStart(2, "0")}.json`,
    );
    detailCache.set(shard, promise);
  }
  const details = await promise;
  const tender = details[id];
  if (!tender) throw new Error(`Tender ${id} was not found in shard ${shard}.`);
  return tender;
}
