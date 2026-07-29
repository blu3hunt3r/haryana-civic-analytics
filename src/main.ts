import "./style.css";
import {
  renderChainChart,
  renderCompetitionChart,
  renderComponentDonut,
  renderDepartmentComponentHeatmap,
  renderDepartmentChart,
  renderFilteredValueChart,
  renderStatusChart,
  renderTrendChart,
  resizeCharts,
} from "./charts";
import {
  loadOverview,
  loadPlaces,
  loadSearchIndex,
  loadTenderDetail,
  loadTenders,
} from "./data";
import { escapeHtml, formatCount, formatRupees, label, shortHash } from "./format";
import { EvidenceMap } from "./map";
import type {
  Filters,
  Metric,
  Overview,
  PlaceRecord,
  Scope,
  TenderDetail,
  TenderIndexRow,
} from "./types";

const root = document.querySelector<HTMLElement>("#app");
if (!root) throw new Error("Application root is missing.");
const app: HTMLElement = root;

const filters: Filters = {
  scopes: new Set<Scope>(["confirmed_gurugram"]),
  year: "",
  status: "",
  department: "",
  component: "",
  contractor: "",
  competition: "",
  chain: "",
  repeatGroup: "",
  place: "",
  areaLevel: "",
  areaValue: "",
  query: "",
};

let overview: Overview;
let allRows: TenderIndexRow[] = [];
let filteredRows: TenderIndexRow[] = [];
let fullDescriptionSearch = new Map<string, string>();
let allPlaces: PlaceRecord[] = [];
let selectedPlaceTenderIds = new Set<string>();
let evidenceMap: EvidenceMap;
let indexReady = false;
let currentPage = 0;
function pageSize(): number {
  return window.matchMedia("(max-width: 760px)").matches ? 10 : 25;
}

function metric(): Metric {
  return { tenders: 0, awarded: 0, contractValue: 0, cancelled: 0, retendered: 0 };
}

function summarize(rows: TenderIndexRow[]): Metric {
  const result = metric();
  for (const row of rows) {
    result.tenders += 1;
    if (row.isAwarded) result.awarded += 1;
    if (row.isControllingAward && row.contractValue !== null) {
      result.contractValue += row.contractValue;
    }
    if (row.status === "Cancelled") result.cancelled += 1;
    if (row.status === "Retender") result.retendered += 1;
  }
  return result;
}

function normalizeArea(value: string): string {
  return value
    .toLowerCase()
    .replace(/\b(ward|sector|zone|no|number)\b/g, "")
    .replace(/[^a-z0-9]+/g, "");
}

function matches(row: TenderIndexRow): boolean {
  if (!filters.scopes.has(row.scope as Scope)) return false;
  if (filters.year && row.year !== filters.year) return false;
  if (filters.status && row.status !== filters.status) return false;
  if (filters.department && row.department !== filters.department) return false;
  if (filters.component && row.component !== filters.component) return false;
  if (filters.contractor && row.contractorKey !== filters.contractor) return false;
  if (filters.competition) {
    if (!row.isAwarded) return false;
    if (filters.competition === "one_bid" && row.awardedBidCount !== 1) return false;
    if (
      filters.competition === "multi_bid" &&
      (row.awardedBidCount === null || row.awardedBidCount < 2)
    ) {
      return false;
    }
    if (
      filters.competition === "not_published" &&
      row.awardedBidCount !== null
    ) {
      return false;
    }
  }
  if (
    filters.chain === "single" &&
    (row.chainHasCancelOrRetender || row.chainAmbiguous)
  ) {
    return false;
  }
  if (filters.chain === "reworked" && !row.chainHasCancelOrRetender) return false;
  if (filters.chain === "ambiguous" && !row.chainAmbiguous) return false;
  if (filters.repeatGroup && row.titleKey !== filters.repeatGroup) return false;
  if (filters.place && !selectedPlaceTenderIds.has(row.id)) return false;
  if (filters.areaValue) {
    const target = normalizeArea(filters.areaValue);
    const found = row.areas.some(
      (area) =>
        (!filters.areaLevel || area.level.toLowerCase().includes(filters.areaLevel)) &&
        normalizeArea(area.value) === target,
    );
    if (!found) return false;
  }
  if (filters.query) {
    const needle = filters.query.toLowerCase();
    const haystack = [
      row.id,
      row.title,
      row.description ?? fullDescriptionSearch.get(row.id) ?? "",
      row.department,
      row.component,
      row.contractor,
      ...row.areas.map((area) => area.value),
    ]
      .join(" ")
      .toLowerCase();
    if (!haystack.includes(needle)) return false;
  }
  return true;
}

function dimension(rows: TenderIndexRow[], key: "status" | "department" | "component") {
  const values = new Map<string, Metric>();
  for (const row of rows) {
    const name = row[key] || "Unclassified";
    const entry = values.get(name) ?? metric();
    entry.tenders += 1;
    if (row.isAwarded) entry.awarded += 1;
    if (row.isControllingAward && row.contractValue !== null) {
      entry.contractValue += row.contractValue;
    }
    if (row.status === "Cancelled") entry.cancelled += 1;
    if (row.status === "Retender") entry.retendered += 1;
    values.set(name, entry);
  }
  return [...values.entries()]
    .map(([keyValue, value]) => ({ key: keyValue, ...value }))
    .sort((a, b) => b.tenders - a.tenders || a.key.localeCompare(b.key));
}

function renderShell(): void {
  app.innerHTML = `
    <header class="site-header">
      <a class="brand" href="#" aria-label="Haryana Civic Analytics home">
        <span class="brand-mark" aria-hidden="true">हर</span>
        <span>
          <b>Haryana Civic Analytics</b>
          <small>Civic Voice of India</small>
        </span>
      </a>
      <nav aria-label="Dashboard sections">
        <a href="#overview">Overview</a>
        <a href="#departments">Departments</a>
        <a href="#evidence">Evidence</a>
        <a href="#tenders">Tender explorer</a>
      </nav>
      <span class="dataset-version">Evidence snapshot ${escapeHtml(overview.datasetVersion)}</span>
    </header>

    <main>
      <section class="hero" id="overview">
        <div>
          <p class="eyebrow">Public procurement, made inspectable</p>
          <h1>See what Haryana tendered, what was awarded, and what evidence is missing.</h1>
          <p class="lede">Start with the map. Zoom from Haryana into Gurugram, select a ward or sector, and every number below follows that geography. Contract value is never presented as money paid.</p>
        </div>
        <div class="truth-key" aria-label="Evidence definitions">
          <span><i class="dot published"></i> Published tender</span>
          <span><i class="dot awarded"></i> Awarded contract</span>
          <span><i class="dot missing"></i> Delivery evidence not located</span>
        </div>
      </section>

      <section class="filter-bar" aria-label="Analytics filters">
        <fieldset class="scope-filter">
          <legend>Geographic confidence</legend>
          <label><input type="checkbox" value="confirmed_gurugram" checked> Confirmed Gurugram</label>
          <label><input type="checkbox" value="likely_gurugram"> Likely Gurugram</label>
          <label><input type="checkbox" value="statewide_multi_location"> Statewide / multi-location</label>
          <label><input type="checkbox" value="not_gurugram"> Outside Gurugram</label>
        </fieldset>
        <label>Year<select id="year-filter"><option value="">All years</option></select></label>
        <label>Status<select id="status-filter"><option value="">All statuses</option></select></label>
        <label>Department<select id="department-filter"><option value="">All departments</option></select></label>
        <label>Work family<select id="component-filter"><option value="">All work</option></select></label>
        <button class="clear-button" id="clear-filters" type="button">Clear filters</button>
      </section>

      <section class="map-stage" aria-label="Interactive Haryana procurement map">
        <div class="map-toolbar">
          <div>
            <strong id="map-selection">Haryana overview</strong>
            <span id="map-selection-note">Zoom into Gurugram for ward, sector and mapped-road evidence.</span>
          </div>
          <div class="map-actions">
            <button type="button" id="haryana-view">Haryana</button>
            <button type="button" id="gurugram-view">Gurugram</button>
            <label><input type="checkbox" data-layer="wards" checked> Wards</label>
            <label><input type="checkbox" data-layer="sectors"> Sectors</label>
            <label><input type="checkbox" data-layer="roads"> Roads</label>
          </div>
        </div>
        <div id="evidence-map"><span class="map-error" role="status"></span></div>
        <div class="map-caption">
          <span>Map geometry proves boundaries and mapped assets—not that every tender covers every point inside them.</span>
          <button type="button" id="clear-area" hidden>Remove selected area</button>
        </div>
      </section>

      <section class="stats" aria-live="polite">
        <article><span>Published tender records</span><strong id="stat-tenders">—</strong><small>Invitations to bid, not completed works</small></article>
        <article><span>Awarded contracts</span><strong id="stat-awarded">—</strong><small>Verified AOC status</small></article>
        <article><span>Published contract value</span><strong id="stat-value">—</strong><small>Controlling awards only; not money paid</small></article>
        <article><span>Cancelled or retendered</span><strong id="stat-reworked">—</strong><small>Visible history, excluded from value</small></article>
      </section>

      <p class="load-state" id="index-state" role="status">Preparing cross-filtered tender evidence…</p>

      <section class="place-explorer" aria-label="Gurugram village and town works index">
        <header>
          <div>
            <p class="eyebrow">Rural and town coverage</p>
            <h2>HEWP village and town index</h2>
            <p>These are named places from Haryana's public works register. The archive contains names and codes, but no usable village-boundary geometry—so the map does not invent polygons.</p>
          </div>
          <label class="search-field">Find a village or town
            <input id="place-search" type="search" placeholder="e.g. Abheypur or Sohna">
          </label>
        </header>
        <div class="place-stats">
          <article><strong id="place-count">—</strong><span>named places</span></article>
          <article><strong id="place-work-count">—</strong><span>place-to-work references (a multi-place work can repeat)</span></article>
          <article><strong id="place-award-count">—</strong><span>references with an agreement name</span></article>
          <article><strong>0</strong><span>village boundaries in this archive</span></article>
        </div>
        <div id="place-list" class="place-list"><span>Loading the place index…</span></div>
      </section>

      <section class="analytics-grid">
        <article class="panel panel-wide">
          <header><div><p class="eyebrow">Lifecycle</p><h2>Tender status</h2></div><p>Click a bar to filter the entire portal.</p></header>
          <div class="chart chart-tall" id="status-chart" aria-label="Tender status chart"></div>
        </article>
        <article class="panel">
          <header><div><p class="eyebrow">Time</p><h2>Published versus awarded</h2></div></header>
          <div class="chart" id="trend-chart" aria-label="Tender trend chart"></div>
        </article>
        <article class="panel" id="departments">
          <header><div><p class="eyebrow">Responsibility</p><h2>Departments publishing work</h2></div><p>Similar work can belong to different asset owners.</p></header>
          <div class="chart chart-tall" id="department-chart" aria-label="Department tender chart"></div>
        </article>
        <article class="panel">
          <header><div><p class="eyebrow">Work mix</p><h2>What was procured</h2></div><p>Rules use the full work description; unmatched records remain unclassified.</p></header>
          <div class="chart" id="component-chart" aria-label="Work component chart"></div>
        </article>
        <article class="panel panel-wide">
          <header><div><p class="eyebrow">Contract value</p><h2>Awarded value over time</h2></div><p>This is the published contract value, not expenditure or payment.</p></header>
          <div class="chart" id="value-chart" aria-label="Published contract value chart"></div>
        </article>
      </section>

      <section class="deep-dive" aria-label="Accountability analytics">
        <header class="section-intro">
          <p class="eyebrow">Cross-examine the corpus</p>
          <h2>Who bought what, how bids resolved, and where work repeats</h2>
          <p>These views describe the published procurement record. Concentration and repetition are review signals—not findings of wrongdoing.</p>
        </header>
        <div class="analytics-grid">
          <article class="panel panel-wide">
            <header><div><p class="eyebrow">Department × work family</p><h2>Procurement heatmap</h2></div><p>Click a cell to inspect its exact tender rows.</p></header>
            <div class="chart chart-heatmap" id="department-component-heatmap" aria-label="Department by work family heatmap"></div>
          </article>
          <article class="panel">
            <header><div><p class="eyebrow">Competition evidence</p><h2>Published awarded-bid count</h2></div><p>This is the number of awarded bids published—not necessarily all bids received.</p></header>
            <div class="chart" id="competition-chart" aria-label="Published awarded bid count chart"></div>
          </article>
          <article class="panel">
            <header><div><p class="eyebrow">Procurement history</p><h2>Cancellation and retender chains</h2></div><p>Chain values count procurement groups, not individual tender rows.</p></header>
            <div class="chart" id="chain-chart" aria-label="Procurement chain chart"></div>
          </article>
        </div>
        <div class="accountability-lists">
          <article class="ranked-panel" id="contractors">
            <header><div><p class="eyebrow">Published awardees</p><h2>Contractor concentration</h2></div><p>Name matching only; no authoritative contractor ID is published.</p></header>
            <div id="contractor-profile" class="selection-profile" hidden></div>
            <div id="contractor-list" class="ranked-list"></div>
          </article>
          <article class="ranked-panel">
            <header><div><p class="eyebrow">Repeat signal</p><h2>Repeated work descriptions</h2></div><p>Same normalized description can reflect phases, annual maintenance, or retendering. Open the rows before drawing a conclusion.</p></header>
            <div id="repeat-timeline" class="selection-profile" hidden></div>
            <div id="repeat-list" class="ranked-list"></div>
          </article>
        </div>
      </section>

      <section class="evidence-section" id="evidence">
        <div>
          <p class="eyebrow">Publication quality</p>
          <h2>What the public record can and cannot prove</h2>
          <p>The archive is strong for notices and awards. It is much weaker for measurements, bills, quality tests and actual completion. Missing evidence is shown as a gap, never silently converted into a conclusion.</p>
        </div>
        <div class="evidence-grid">
          <article><strong id="flag-unclassified">—</strong><span>work descriptions not classified</span></article>
          <article><strong id="flag-no-area">—</strong><span>confirmed records without area evidence</span></article>
          <article><strong id="flag-no-doc">—</strong><span>awards without a downloaded document</span></article>
          <article><strong id="flag-date-conflict">—</strong><span>portal publication dates disagree with Tender ID year</span></article>
          <article><strong>Separate</strong><span>tender · award · schedule · completion</span></article>
        </div>
      </section>

      <section class="tender-explorer" id="tenders">
        <header>
          <div><p class="eyebrow">Drill down</p><h2>Underlying tender evidence</h2></div>
          <label class="search-field">Search ID, work, contractor or area
            <input id="search" type="search" placeholder="e.g. drainage Sector 56">
          </label>
        </header>
        <div class="table-summary"><span id="result-count">Loading…</span><span id="active-filter-summary"></span></div>
        <div class="tender-list" id="tender-list"></div>
        <div class="pagination">
          <button type="button" id="previous-page">Previous</button>
          <span id="page-label"></span>
          <button type="button" id="next-page">Next</button>
        </div>
      </section>

      <section class="method-note">
        <h2>How to read this portal</h2>
        <div>
          <p><strong>Tender</strong> means the authority invited bids.</p>
          <p><strong>Awarded</strong> means an AOC result was published.</p>
          <p><strong>Contract value</strong> is not money paid.</p>
          <p><strong>Scheduled completion</strong> is not actual completion.</p>
        </div>
      </section>
    </main>

    <footer>
      <span>Civic Voice of India · public evidence with reproducible source hashes</span>
      <a href="https://github.com/blu3hunt3r/haryana-civic-analytics">Method and source code</a>
    </footer>

    <dialog id="tender-dialog">
      <button class="dialog-close" type="button" aria-label="Close tender details">×</button>
      <div id="tender-detail"></div>
    </dialog>
  `;
}

function setOptions(
  element: HTMLSelectElement,
  values: string[],
  formatter: (value: string) => string = label,
): void {
  element.insertAdjacentHTML(
    "beforeend",
    values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(formatter(value))}</option>`).join(""),
  );
}

function selectedScopeLabel(): string {
  if (filters.scopes.size === 1 && filters.scopes.has("confirmed_gurugram")) {
    return "Confirmed Gurugram";
  }
  return [...filters.scopes].map(label).join(" + ") || "No scope selected";
}

function renderStats(rows: TenderIndexRow[]): void {
  const values = summarize(rows);
  document.querySelector("#stat-tenders")!.textContent = formatCount(values.tenders);
  document.querySelector("#stat-awarded")!.textContent = formatCount(values.awarded);
  document.querySelector("#stat-value")!.textContent = formatRupees(values.contractValue);
  document.querySelector("#stat-reworked")!.textContent = formatCount(
    values.cancelled + values.retendered,
  );
}

function applyFilters(): void {
  if (!indexReady) return;
  filteredRows = allRows.filter(matches);
  currentPage = 0;
  renderStats(filteredRows);
  renderDynamicCharts();
  renderMapMetrics(filteredRows);
  renderTenderList();
  renderActiveFilters();
}

function renderMapMetrics(rows: TenderIndexRow[]): void {
  if (!evidenceMap) return;
  const counts = new Map<string, number>();
  for (const row of rows) {
    const districts = new Set(
      row.areas
        .filter((area) => area.level === "district")
        .map((area) => area.value),
    );
    for (const district of districts) {
      counts.set(district, (counts.get(district) ?? 0) + 1);
    }
  }
  evidenceMap.setDistrictMetrics(counts);
}

function renderPlaces(query = ""): void {
  const list = document.querySelector<HTMLElement>("#place-list")!;
  const needle = query.trim().toLowerCase();
  const rows = allPlaces
    .filter((place) => {
      if (!needle) return true;
      return [
        place.name,
        place.block,
        place.panchayat,
        ...place.variants,
      ]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    })
    .sort(
      (a, b) =>
        b.awardedWorkCount - a.awardedWorkCount ||
        b.workCount - a.workCount ||
        a.name.localeCompare(b.name),
    )
    .slice(0, 18);
  list.innerHTML = rows.length
    ? rows
        .map(
          (place) => `
            <button type="button" data-place="${escapeHtml(place.name)}">
              <span><b>${escapeHtml(place.name)}</b><small>${escapeHtml(place.areaType)}${place.block ? ` · ${escapeHtml(place.block)}` : ""}${place.variants.length > 1 ? ` · variants: ${escapeHtml(place.variants.join(", "))}` : ""}</small></span>
              <strong>${formatCount(place.workCount)} works</strong>
              <small>${formatCount(place.awardedWorkCount)} with agreement name · ${formatCount(place.tenderIds.length)} exact Tender IDs</small>
            </button>`,
        )
        .join("")
    : `<div class="empty-state">No place name matches that search.</div>`;
  list.querySelectorAll<HTMLButtonElement>("[data-place]").forEach((button) => {
    button.addEventListener("click", () => {
      const place = allPlaces.find((row) => row.name === button.dataset.place);
      if (!place) return;
      filters.place = place.name;
      selectedPlaceTenderIds = new Set(place.tenderIds);
      applyFilters();
      document.querySelector("#tenders")?.scrollIntoView({ behavior: "smooth" });
    });
  });
}

async function hydratePlaces(): Promise<void> {
  try {
    allPlaces = await loadPlaces();
    document.querySelector("#place-count")!.textContent = formatCount(allPlaces.length);
    document.querySelector("#place-work-count")!.textContent = formatCount(
      allPlaces.reduce((sum, row) => sum + row.workCount, 0),
    );
    document.querySelector("#place-award-count")!.textContent = formatCount(
      allPlaces.reduce((sum, row) => sum + row.awardedWorkCount, 0),
    );
    renderPlaces();
    document
      .querySelector<HTMLInputElement>("#place-search")!
      .addEventListener("input", (event) => {
        renderPlaces((event.target as HTMLInputElement).value);
      });
  } catch (error) {
    document.querySelector("#place-list")!.textContent =
      `The place index could not be loaded: ${String(error)}`;
  }
}

function renderDynamicCharts(): void {
  const statuses = Object.fromEntries(
    dimension(filteredRows, "status").map((row) => [row.key, row.tenders]),
  );
  renderStatusChart(
    document.querySelector<HTMLElement>("#status-chart")!,
    statuses,
    (status) => {
      filters.status = status;
      (document.querySelector("#status-filter") as HTMLSelectElement).value = status;
      applyFilters();
    },
  );
  const departments = dimension(filteredRows, "department");
  renderDepartmentChart(
    document.querySelector<HTMLElement>("#department-chart")!,
    departments,
    (department) => {
      filters.department = department;
      (document.querySelector("#department-filter") as HTMLSelectElement).value =
        department;
      applyFilters();
    },
  );
  renderComponentDonut(
    document.querySelector<HTMLElement>("#component-chart")!,
    dimension(filteredRows, "component"),
    (component) => {
      filters.component = component;
      (document.querySelector("#component-filter") as HTMLSelectElement).value =
        component;
      applyFilters();
    },
  );
  renderFilteredValueChart(
    document.querySelector<HTMLElement>("#value-chart")!,
    filteredRows,
  );
  renderDepartmentComponentHeatmap(
    document.querySelector<HTMLElement>("#department-component-heatmap")!,
    filteredRows,
    (department, component) => {
      filters.department = department;
      filters.component = component;
      (document.querySelector("#department-filter") as HTMLSelectElement).value =
        department;
      (document.querySelector("#component-filter") as HTMLSelectElement).value =
        component;
      applyFilters();
      document.querySelector("#tenders")?.scrollIntoView({ behavior: "smooth" });
    },
  );
  renderCompetitionChart(
    document.querySelector<HTMLElement>("#competition-chart")!,
    filteredRows,
    (bucket) => {
      filters.competition = bucket;
      applyFilters();
      document.querySelector("#tenders")?.scrollIntoView({ behavior: "smooth" });
    },
  );
  renderChainChart(
    document.querySelector<HTMLElement>("#chain-chart")!,
    filteredRows,
    (bucket) => {
      filters.chain = bucket;
      applyFilters();
      document.querySelector("#tenders")?.scrollIntoView({ behavior: "smooth" });
    },
  );
  renderRankedLists(filteredRows);

  const periodMetrics = new Map<string, Metric>();
  for (const row of filteredRows) {
    const period = row.month ?? row.year;
    if (!period) continue;
    const value = periodMetrics.get(period) ?? metric();
    value.tenders += 1;
    if (row.isAwarded) value.awarded += 1;
    periodMetrics.set(period, value);
  }
  renderTrendChart(
    document.querySelector<HTMLElement>("#trend-chart")!,
    [...periodMetrics].sort().map(([period, value]) => ({ period, ...value })),
  );
}

function renderRankedLists(rows: TenderIndexRow[]): void {
  const contractorProfile =
    document.querySelector<HTMLElement>("#contractor-profile")!;
  if (filters.contractor) {
    const awarded = rows.filter((row) => row.isControllingAward);
    const departments = dimension(rows, "department")
      .slice(0, 4)
      .map((row) => row.key)
      .join(", ");
    const components = dimension(rows, "component")
      .slice(0, 4)
      .map((row) => label(row.key))
      .join(", ");
    contractorProfile.hidden = false;
    contractorProfile.innerHTML = `
      <b>${escapeHtml(rows[0]?.contractor || "Selected contractor")}</b>
      <span>${formatCount(awarded.length)} controlling awards · ${formatRupees(awarded.reduce((sum, row) => sum + (row.contractValue ?? 0), 0))}</span>
      <small>Departments: ${escapeHtml(departments || "not published")}<br>Work families: ${escapeHtml(components || "unclassified")}</small>`;
  } else {
    contractorProfile.hidden = true;
    contractorProfile.innerHTML = "";
  }
  const contractors = new Map<
    string,
    { name: string; awards: number; value: number }
  >();
  for (const row of rows) {
    if (!row.isControllingAward || !row.contractorKey) continue;
    const entry = contractors.get(row.contractorKey) ?? {
      name: row.contractor,
      awards: 0,
      value: 0,
    };
    entry.awards += 1;
    entry.value += row.contractValue ?? 0;
    contractors.set(row.contractorKey, entry);
  }
  const totalKnownValue = [...contractors.values()].reduce(
    (sum, row) => sum + row.value,
    0,
  );
  const contractorRows = [...contractors]
    .sort((a, b) => b[1].value - a[1].value || b[1].awards - a[1].awards)
    .slice(0, 12);
  const contractorList = document.querySelector<HTMLElement>("#contractor-list")!;
  contractorList.innerHTML = contractorRows.length
    ? contractorRows
        .map(
          ([key, row], index) => `
            <button type="button" data-contractor="${escapeHtml(key)}">
              <span class="rank">${index + 1}</span>
              <span><b>${escapeHtml(row.name)}</b><small>${formatCount(row.awards)} controlling awards · ${totalKnownValue ? ((row.value / totalKnownValue) * 100).toFixed(1) : "0.0"}% of known value in this view</small></span>
              <strong>${formatRupees(row.value)}</strong>
            </button>`,
        )
        .join("")
    : `<div class="empty-state">No published contractor names in this view.</div>`;
  contractorList
    .querySelectorAll<HTMLButtonElement>("[data-contractor]")
    .forEach((button) => {
      button.addEventListener("click", () => {
        filters.contractor = button.dataset.contractor ?? "";
        applyFilters();
        document.querySelector("#tenders")?.scrollIntoView({ behavior: "smooth" });
      });
    });

  const repeatGroups = new Map<
    string,
    { sample: string; rows: number; chains: Set<string>; awarded: number }
  >();
  for (const row of rows) {
    if (!row.titleKey) continue;
    const entry = repeatGroups.get(row.titleKey) ?? {
      sample: row.description ?? row.title,
      rows: 0,
      chains: new Set<string>(),
      awarded: 0,
    };
    entry.rows += 1;
    entry.chains.add(row.chainRoot);
    if (row.isAwarded) entry.awarded += 1;
    repeatGroups.set(row.titleKey, entry);
  }
  const repeats = [...repeatGroups]
    .filter(([, row]) => row.chains.size >= 2)
    .sort(
      (a, b) =>
        b[1].chains.size - a[1].chains.size ||
        b[1].rows - a[1].rows ||
        a[0].localeCompare(b[0]),
    )
    .slice(0, 12);
  const repeatList = document.querySelector<HTMLElement>("#repeat-list")!;
  const repeatTimeline =
    document.querySelector<HTMLElement>("#repeat-timeline")!;
  if (filters.repeatGroup) {
    repeatTimeline.hidden = false;
    repeatTimeline.innerHTML = `
      <b>Published timeline for this normalized description</b>
      <ol>${[...rows]
        .sort(
          (a, b) =>
            (a.year ?? "").localeCompare(b.year ?? "") || a.id.localeCompare(b.id),
        )
        .map(
          (row) =>
            `<li><span>${escapeHtml(row.year ?? "Year unavailable")} · ${escapeHtml(row.status)}</span><code>${escapeHtml(row.id)}</code><small>${row.isAwarded ? formatRupees(row.contractValue) : "No confirmed award"}</small></li>`,
        )
        .join("")}</ol>`;
  } else {
    repeatTimeline.hidden = true;
    repeatTimeline.innerHTML = "";
  }
  repeatList.innerHTML = repeats.length
    ? repeats
        .map(
          ([key, row], index) => `
            <button type="button" data-repeat="${escapeHtml(key)}">
              <span class="rank">${index + 1}</span>
              <span><b>${escapeHtml(row.sample.slice(0, 155))}</b><small>${formatCount(row.chains.size)} separate procurement chains · ${formatCount(row.awarded)} awarded tender rows</small></span>
            </button>`,
        )
        .join("")
    : `<div class="empty-state">No repeated normalized descriptions in this view.</div>`;
  repeatList
    .querySelectorAll<HTMLButtonElement>("[data-repeat]")
    .forEach((button) => {
      button.addEventListener("click", () => {
        filters.repeatGroup = button.dataset.repeat ?? "";
        applyFilters();
        document.querySelector("#tenders")?.scrollIntoView({ behavior: "smooth" });
      });
    });
}

function renderActiveFilters(): void {
  const parts = [selectedScopeLabel()];
  if (filters.year) parts.push(filters.year);
  if (filters.status) parts.push(filters.status);
  if (filters.department) parts.push(filters.department);
  if (filters.component) parts.push(label(filters.component));
  if (filters.contractor) parts.push("Selected contractor");
  if (filters.competition) parts.push(label(filters.competition));
  if (filters.chain) parts.push(`${label(filters.chain)} chains`);
  if (filters.repeatGroup) parts.push("Repeated work group");
  if (filters.place) parts.push(`HEWP place ${filters.place}`);
  if (filters.areaValue) parts.push(`${label(filters.areaLevel)} ${filters.areaValue}`);
  document.querySelector("#active-filter-summary")!.textContent = parts.join(" · ");
}

function renderTenderList(): void {
  const list = document.querySelector<HTMLElement>("#tender-list")!;
  const sorted = [...filteredRows].sort(
    (a, b) =>
      (b.year ?? "").localeCompare(a.year ?? "") ||
      Number(b.isAwarded) - Number(a.isAwarded) ||
      a.id.localeCompare(b.id),
  );
  const size = pageSize();
  const pages = Math.max(1, Math.ceil(sorted.length / size));
  currentPage = Math.min(currentPage, pages - 1);
  const page = sorted.slice(currentPage * size, (currentPage + 1) * size);
  document.querySelector("#result-count")!.textContent =
    `${formatCount(sorted.length)} matching tender records`;
  document.querySelector("#page-label")!.textContent = `Page ${currentPage + 1} of ${pages}`;
  (document.querySelector("#previous-page") as HTMLButtonElement).disabled =
    currentPage === 0;
  (document.querySelector("#next-page") as HTMLButtonElement).disabled =
    currentPage >= pages - 1;
  list.innerHTML = page.length
    ? page
        .map(
          (row) => `
            <button class="tender-row" type="button" data-tender="${escapeHtml(row.id)}">
              <span class="status-pill ${row.isAwarded ? "is-awarded" : ""}">${escapeHtml(row.status)}</span>
              <span class="tender-main">
                <b>${escapeHtml(row.title || row.id)}</b>
                <small>${escapeHtml(row.id)} · ${escapeHtml(row.department)} · ${escapeHtml(label(row.component))}</small>
              </span>
              <span class="tender-value">${row.isAwarded ? formatRupees(row.contractValue) : "Not awarded"}<small>${row.documentCount} documents</small></span>
            </button>`,
        )
        .join("")
    : `<div class="empty-state"><strong>No matching tender records</strong><span>Remove a filter or widen the geographic confidence.</span></div>`;

  list.querySelectorAll<HTMLButtonElement>("[data-tender]").forEach((button) => {
    button.addEventListener("click", () => {
      const row = allRows.find((item) => item.id === button.dataset.tender);
      if (row) void openTender(row);
    });
  });
}

function renderDetail(detail: TenderDetail): string {
  const documents = detail.documents.length
    ? detail.documents
        .map(
          (document) => `
            <li>
              <div><b>${escapeHtml(document.name || "Unnamed published document")}</b><span>${escapeHtml(document.section)} · ${escapeHtml(document.outcome)}</span></div>
              <code title="${escapeHtml(document.sha256)}">${shortHash(document.sha256)}</code>
              ${document.officialUrl ? `<a href="${escapeHtml(document.officialUrl)}" target="_blank" rel="noopener">Official link ↗</a>` : ""}
            </li>`,
        )
        .join("")
    : `<li class="empty-state">No document metadata was published for this tender.</li>`;
  const hashes = Object.entries(detail.sourceHashes)
    .filter(([, value]) => value)
    .map(
      ([name, value]) =>
        `<li><span>${escapeHtml(label(name))}</span><code>${escapeHtml(value)}</code></li>`,
    )
    .join("");
  const hewpRecords = detail.hewpRecords?.length
    ? detail.hewpRecords
        .map(
          (record) => `
            <li><div><b>${escapeHtml(record.place || record.estimateName)}</b><span>${escapeHtml(record.areaType)}${record.block ? ` · ${escapeHtml(record.block)}` : ""} · exact Tender ID link</span></div><div>${escapeHtml(record.agreementName || "Agreement name not published")}</div><div>${record.contractStart || record.contractEnd ? `Published schedule ${escapeHtml(record.contractStart || "?")} → ${escapeHtml(record.contractEnd || "?")}` : "Schedule not published"} · ${formatRupees(record.estimateValue)}</div><code>${shortHash(record.sourceSha256)}</code>${record.sourceUrl ? `<a href="${escapeHtml(record.sourceUrl)}" target="_blank" rel="noopener">HEWP source ↗</a>` : ""}</li>`,
        )
        .join("")
    : "";
  const mcgLinks = detail.mcgLinks?.length
    ? detail.mcgLinks
        .map(
          (record) => `
            <li><div><b>${escapeHtml(record.workName)}</b><span>${record.linkGrade === "exact" ? "Exact Tender ID in MCG work name" : "Candidate link—not contractual identity"}</span></div><div>MCG work ${escapeHtml(record.workId)} · ${formatRupees(record.sanctionedValue)}${record.progressPercent !== null ? ` · published progress ${record.progressPercent}%` : ""}</div><small>${escapeHtml(record.interpretation)}</small></li>`,
        )
        .join("")
    : "";
  const assetLinks = detail.assetLinks?.length
    ? detail.assetLinks
        .map(
          (record) => `
            <li><div><b>${escapeHtml(record.assetKey)}</b><span>Validated contract-to-asset link · proof grade ${escapeHtml(record.proofGrade)}</span></div><div>${escapeHtml(label(record.component))} · ${escapeHtml(record.coverage)}</div><small>${escapeHtml(record.validatorReason)}</small><code>${shortHash(record.evidenceSha256)}</code></li>`,
        )
        .join("")
    : "";

  return `
    <div class="detail-header">
      <p class="eyebrow">${escapeHtml(detail.id)}</p>
      <h2>${escapeHtml(detail.title || detail.description || detail.id)}</h2>
      <div class="detail-badges">
        <span>${escapeHtml(detail.status)}</span>
        <span>${escapeHtml(label(detail.scope))}</span>
        <span>${escapeHtml(label(detail.component))}</span>
      </div>
    </div>
    <div class="detail-warning"><strong>Evidence boundary:</strong> ${detail.isAwarded ? "An award is published." : "No confirmed award is recorded."} Contract value is not payment, and the schedule is not actual completion.</div>
    <dl class="detail-grid">
      <div><dt>Department</dt><dd>${escapeHtml(detail.department)}</dd></div>
      <div><dt>Published</dt><dd>${escapeHtml(detail.publishedAt || "Not published")}</dd></div>
      <div><dt>Estimate</dt><dd>${formatRupees(detail.estimateValue)}</dd></div>
      <div><dt>Contract value</dt><dd>${formatRupees(detail.contractValue)}</dd></div>
      <div><dt>Award date</dt><dd>${escapeHtml(detail.awardDate || "Not published")}</dd></div>
      <div><dt>Contractor</dt><dd>${escapeHtml(detail.contractor || "Not published by the authority")}</dd></div>
      <div><dt>Scheduled period</dt><dd>${detail.scheduledCompletionDays ? `${formatCount(detail.scheduledCompletionDays)} days` : "Not published"}</dd></div>
      <div><dt>Actual completion</dt><dd>Not established by the tender record</dd></div>
    </dl>
    <section class="detail-section"><h3>Published scope</h3><p>${escapeHtml(detail.description || "No full work description was published.")}</p><p><b>Location:</b> ${escapeHtml(detail.workLocation || "Not published")} ${detail.pincode ? `· ${escapeHtml(detail.pincode)}` : ""}</p></section>
    ${detail.chain ? `<section class="detail-section"><h3>Procurement chain</h3><p>Root ${escapeHtml(detail.chain.root)} · position ${detail.chain.position ?? "?"} of ${detail.chain.length ?? "?"} · terminal ${escapeHtml(detail.chain.terminal || "not resolved")}</p>${detail.chain.ambiguous ? `<p class="warning-text">The chain is ambiguous: ${escapeHtml(detail.chain.ambiguityReasons)}</p>` : ""}</section>` : ""}
    ${assetLinks ? `<section class="detail-section"><h3>Validated asset links</h3><ul class="record-link-list">${assetLinks}</ul></section>` : ""}
    ${hewpRecords ? `<section class="detail-section"><h3>HEWP public works register</h3><p>Linked by the shared government Tender ID. Schedule dates are not actual completion.</p><ul class="record-link-list">${hewpRecords}</ul></section>` : ""}
    ${mcgLinks ? `<section class="detail-section"><h3>MCG public works register</h3><p>Only rows labelled exact share a Tender ID. Title matches remain candidates.</p><ul class="record-link-list">${mcgLinks}</ul></section>` : ""}
    <section class="detail-section"><h3>Documents (${detail.documents.length})</h3><ul class="document-list">${documents}</ul></section>
    <section class="detail-section"><h3>Source-page hashes</h3><ul class="hash-list">${hashes}</ul></section>
    <div class="detail-actions">
      ${detail.officialStatusUrl ? `<a href="${escapeHtml(detail.officialStatusUrl)}" target="_blank" rel="noopener">Official tender status ↗</a>` : ""}
      ${detail.officialDetailUrl ? `<a href="${escapeHtml(detail.officialDetailUrl)}" target="_blank" rel="noopener">Official tender detail ↗</a>` : ""}
    </div>`;
}

async function openTender(row: TenderIndexRow): Promise<void> {
  const dialog = document.querySelector<HTMLDialogElement>("#tender-dialog")!;
  const detailElement = document.querySelector<HTMLElement>("#tender-detail")!;
  detailElement.innerHTML = `<div class="detail-loading" role="status">Loading tender evidence…</div>`;
  dialog.showModal();
  history.replaceState(null, "", `#/tenders/${encodeURIComponent(row.id)}`);
  try {
    const detail = await loadTenderDetail(row.id, row.detailShard);
    detailElement.innerHTML = renderDetail(detail);
  } catch (error) {
    detailElement.innerHTML = `<div class="empty-state"><strong>Could not load tender evidence.</strong><span>${escapeHtml(String(error))}</span></div>`;
  }
}

function bindControls(): void {
  const years = [...new Set(allRows.map((row) => row.year).filter(Boolean) as string[])].sort().reverse();
  const statuses = [...new Set(allRows.map((row) => row.status))].sort();
  const departments = [...new Set(allRows.map((row) => row.department))].sort();
  const components = [...new Set(allRows.map((row) => row.component))].sort();
  setOptions(document.querySelector("#year-filter")!, years, (value) => value);
  setOptions(document.querySelector("#status-filter")!, statuses, (value) => value);
  setOptions(document.querySelector("#department-filter")!, departments, (value) => value);
  setOptions(document.querySelector("#component-filter")!, components);

  document.querySelectorAll<HTMLInputElement>(".scope-filter input").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.checked) filters.scopes.add(input.value as Scope);
      else filters.scopes.delete(input.value as Scope);
      applyFilters();
    });
  });
  for (const [id, key] of [
    ["year-filter", "year"],
    ["status-filter", "status"],
    ["department-filter", "department"],
    ["component-filter", "component"],
  ] as const) {
    document.querySelector<HTMLSelectElement>(`#${id}`)!.addEventListener("change", (event) => {
      filters[key] = (event.target as HTMLSelectElement).value;
      applyFilters();
    });
  }
  let searchTimer = 0;
  document.querySelector<HTMLInputElement>("#search")!.addEventListener("input", (event) => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(async () => {
      const input = event.target as HTMLInputElement;
      const query = input.value.trim();
      input.dataset.searchState = "loading";
      if (query && fullDescriptionSearch.size === 0) {
        document.querySelector("#result-count")!.textContent =
          "Loading the full work-description index…";
        fullDescriptionSearch = await loadSearchIndex();
      }
      filters.query = input.value.trim();
      applyFilters();
      input.dataset.searchState = "ready";
    }, 180);
  });
  document.querySelector("#previous-page")!.addEventListener("click", () => {
    currentPage -= 1;
    renderTenderList();
  });
  document.querySelector("#next-page")!.addEventListener("click", () => {
    currentPage += 1;
    renderTenderList();
  });
  document.querySelector("#clear-filters")!.addEventListener("click", () => {
    filters.scopes = new Set(["confirmed_gurugram"]);
    filters.year = "";
    filters.status = "";
    filters.department = "";
    filters.component = "";
    filters.contractor = "";
    filters.competition = "";
    filters.chain = "";
    filters.repeatGroup = "";
    filters.place = "";
    selectedPlaceTenderIds = new Set();
    filters.areaLevel = "";
    filters.areaValue = "";
    filters.query = "";
    document.querySelectorAll<HTMLInputElement>(".scope-filter input").forEach((input) => {
      input.checked = input.value === "confirmed_gurugram";
    });
    document.querySelectorAll<HTMLSelectElement>(".filter-bar select").forEach((select) => {
      select.value = "";
    });
    document.querySelector<HTMLInputElement>("#search")!.value = "";
    document.querySelector<HTMLElement>("#clear-area")!.hidden = true;
    document.querySelector("#map-selection")!.textContent = "Haryana overview";
    applyFilters();
  });
  document.querySelector(".dialog-close")!.addEventListener("click", () => {
    document.querySelector<HTMLDialogElement>("#tender-dialog")!.close();
  });
  document.querySelector<HTMLDialogElement>("#tender-dialog")!.addEventListener("close", () => {
    history.replaceState(null, "", location.pathname + location.search);
  });
}

function handleMapSelection(level: string, value: string): void {
  if (level === "district") {
    filters.scopes = new Set([
      "confirmed_gurugram",
      "likely_gurugram",
      "statewide_multi_location",
      "not_gurugram",
    ]);
    document.querySelectorAll<HTMLInputElement>(".scope-filter input").forEach((input) => {
      input.checked = true;
    });
  }
  filters.areaLevel = level;
  filters.areaValue = value;
  document.querySelector("#map-selection")!.textContent = `${label(level)} ${value}`;
  document.querySelector("#map-selection-note")!.textContent =
    "Showing tenders whose published text contains this area reference. This is not an exact asset match.";
  document.querySelector<HTMLElement>("#clear-area")!.hidden = false;
  applyFilters();
  document.querySelector(".stats")?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function bindMap(): void {
  evidenceMap = new EvidenceMap(
    document.querySelector<HTMLElement>("#evidence-map")!,
    handleMapSelection,
  );
  document.querySelector("#haryana-view")!.addEventListener("click", () => {
    evidenceMap.haryana();
    document.querySelector("#map-selection")!.textContent = "Haryana overview";
  });
  document.querySelector("#gurugram-view")!.addEventListener("click", () => {
    evidenceMap.gurugram();
    document.querySelector("#map-selection")!.textContent = "Gurugram detail";
  });
  document.querySelectorAll<HTMLInputElement>("[data-layer]").forEach((input) => {
    input.addEventListener("change", () => {
      evidenceMap.toggleLayer(
        input.dataset.layer as "wards" | "sectors" | "roads",
        input.checked,
      );
    });
  });
  document.querySelector("#clear-area")!.addEventListener("click", () => {
    filters.areaLevel = "";
    filters.areaValue = "";
    document.querySelector("#map-selection")!.textContent = "Gurugram detail";
    document.querySelector("#map-selection-note")!.textContent =
      "Click a ward or sector to filter its published tender references.";
    document.querySelector<HTMLElement>("#clear-area")!.hidden = true;
    applyFilters();
  });
}

async function hydrateIndex(): Promise<void> {
  const status = document.querySelector<HTMLElement>("#index-state")!;
  try {
    allRows = await loadTenders();
    indexReady = true;
    status.textContent = `${formatCount(allRows.length)} tender records ready for linked filtering.`;
    status.classList.add("is-ready");
    bindControls();
    applyFilters();
    const route = location.hash.match(/^#\/tenders\/(.+)$/);
    if (route) {
      const id = decodeURIComponent(route[1]);
      const row = allRows.find((item) => item.id === id);
      if (row) await openTender(row);
    }
  } catch (error) {
    status.textContent = `The tender index could not be loaded: ${String(error)}`;
    status.classList.add("is-error");
  }
}

async function bootstrap(): Promise<void> {
  try {
    overview = await loadOverview();
    renderShell();
    renderStats(
      Array.from({ length: overview.headline.confirmedGurugram }, () => ({
        isAwarded: false,
        isControllingAward: false,
        contractValue: null,
        status: "",
      })) as TenderIndexRow[],
    );
    document.querySelector("#stat-tenders")!.textContent = formatCount(
      overview.headline.confirmedGurugram,
    );
    document.querySelector("#stat-awarded")!.textContent = formatCount(
      overview.headline.confirmedAwarded,
    );
    document.querySelector("#stat-value")!.textContent = formatRupees(
      overview.headline.confirmedControllingContractValue,
    );
    const initial = overview.scopeMetrics.confirmed_gurugram;
    document.querySelector("#stat-reworked")!.textContent = formatCount(
      initial.cancelled + initial.retendered,
    );
    document.querySelector("#flag-unclassified")!.textContent = formatCount(
      overview.reviewFlags.componentUnclassified,
    );
    document.querySelector("#flag-no-area")!.textContent = formatCount(
      overview.reviewFlags.areaEvidenceMissing,
    );
    document.querySelector("#flag-no-doc")!.textContent = formatCount(
      overview.reviewFlags.awardedWithoutDownloadedDocument,
    );
    document.querySelector("#flag-date-conflict")!.textContent = formatCount(
      overview.reviewFlags.portalPublishedDateConflictsWithTenderIdYear,
    );
    renderStatusChart(
      document.querySelector<HTMLElement>("#status-chart")!,
      overview.status.confirmed_gurugram,
      () => undefined,
    );
    renderTrendChart(
      document.querySelector<HTMLElement>("#trend-chart")!,
      overview.trends.confirmed_gurugram,
    );
    renderDepartmentChart(
      document.querySelector<HTMLElement>("#department-chart")!,
      overview.departments.confirmed_gurugram,
      () => undefined,
    );
    renderComponentDonut(
      document.querySelector<HTMLElement>("#component-chart")!,
      overview.components.confirmed_gurugram,
      () => undefined,
    );
    bindMap();
    void hydratePlaces();
    evidenceMap.setDistrictMetrics(
      new Map(
        overview.areas
          .filter(
            (area) =>
              area.scope === "confirmed_gurugram" && area.level === "district",
          )
          .map((area) => [area.value, area.tenders]),
      ),
    );
    window.addEventListener("resize", () => {
      resizeCharts();
      evidenceMap.resize();
    });
    void hydrateIndex();
  } catch (error) {
    app.innerHTML = `<div class="fatal-error"><h1>The analytics portal could not start.</h1><p>${escapeHtml(String(error))}</p></div>`;
  }
}

void bootstrap();
