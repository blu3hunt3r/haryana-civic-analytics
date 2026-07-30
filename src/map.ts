import maplibregl, { type Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

const HARYANA_BOUNDS: [[number, number], [number, number]] = [
  [74.42, 27.64],
  [77.62, 30.93],
];
const GURUGRAM_BOUNDS: [[number, number], [number, number]] = [
  [76.69, 28.18],
  [77.24, 28.58],
];

type GeographyHandler = (level: string, value: string) => void;

/* ── THE MAP IS OPTIONAL, AND THAT IS A CORRECTNESS REQUIREMENT ──────────────────
   `new maplibregl.Map()` throws SYNCHRONOUSLY when a WebGL context cannot be created.
   That call used to sit inside main.ts's single bootstrap try/catch, so on any browser
   without WebGL the whole portal rendered "The analytics portal could not start." —
   measured on the live deployment, which was down for exactly this reason. Story,
   charts, the 49,121-record index and search need no WebGL at all, and a public
   accountability record must not be gated on a graphics context.

   So `map` is nullable, construction is guarded, and every method is a no-op when it is
   absent. `available()` lets the caller say so honestly in the UI rather than showing an
   empty grey panel. */
export class EvidenceMap {
  private map: MapLibreMap | null = null;
  private handler: GeographyHandler;
  private container: HTMLElement;
  private districtCounts = new Map<string, number>();
  private failure: string | null = null;

  constructor(container: HTMLElement, handler: GeographyHandler) {
    this.handler = handler;
    this.container = container;
    try {
      this.map = new maplibregl.Map({
        container,
        style: "https://tiles.openfreemap.org/styles/liberty",
        center: [76.3, 29.25],
        zoom: 6.5,
        minZoom: 5.5,
        maxZoom: 18,
        attributionControl: false,
      });
      this.map.addControl(new maplibregl.NavigationControl(), "top-right");
      this.map.addControl(
        new maplibregl.AttributionControl({ compact: true }),
        "bottom-right",
      );
      this.map.on("load", () => void this.addEvidenceLayers());
      /* A later WebGL loss must also not be fatal: the context can be dropped by the
         driver or by a backgrounded tab, and MapLibre surfaces that as an error event. */
      this.map.on("error", (event: unknown) => {
        const message = String((event as { error?: { message?: string } })?.error?.message ?? "");
        if (/webgl|context/i.test(message)) this.degrade(message);
      });
    } catch (error) {
      this.degrade(String(error));
    }
  }

  /* Say what happened, in the panel where the map would have been. A citizen who cannot
     see the geography still needs to know the rest of the record is intact. */
  private degrade(reason: string): void {
    this.map = null;
    this.failure = reason;
    this.container.classList.add("map-unavailable");
    this.container.innerHTML =
      `<div class="map-fallback" role="status">` +
      `<p class="map-fallback-title">The map cannot be drawn in this browser.</p>` +
      `<p class="map-fallback-body">It needs WebGL, which is unavailable or blocked here. ` +
      `Every other part of this record — the outcome funnel, departments, the tender ` +
      `index and each tender's evidence page — works without it.</p></div>`;
  }

  available(): boolean {
    return this.map !== null;
  }

  unavailableReason(): string | null {
    return this.failure;
  }

  haryana(): void {
    this.map?.fitBounds(HARYANA_BOUNDS, { padding: 36, duration: 700 });
  }

  gurugram(): void {
    this.map?.fitBounds(GURUGRAM_BOUNDS, { padding: 28, duration: 700 });
  }

  toggleLayer(name: "wards" | "sectors" | "roads", visible: boolean): void {
    if (!this.map) return;
    for (const suffix of ["fill", "line", "label"]) {
      const id = `${name}-${suffix}`;
      if (this.map.getLayer(id)) {
        this.map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
      }
    }
  }

  resize(): void {
    this.map?.resize();
  }

  setDistrictMetrics(values: Map<string, number>): void {
    /* Retained even with no map: the numbers are still the truth, and a later successful
       init (or a non-map consumer) must see them. */
    this.districtCounts = values;
    if (!this.map || !this.map.getSource("districts")) return;
    const maximum = Math.max(1, ...values.values());
    for (const [district, count] of values) {
      this.map.setFeatureState(
        { source: "districts", id: district },
        { count, intensity: count / maximum },
      );
    }
  }

  private async addGeoJsonSource(
    id: string,
    url: string,
    promoteId?: string,
  ): Promise<void> {
    if (!this.map) return;
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Could not load ${id} geometry.`);
    const data = await response.json();
    this.map.addSource(id, { type: "geojson", data, ...(promoteId ? { promoteId } : {}) });
  }

  private async addEvidenceLayers(): Promise<void> {
    if (!this.map) return;
    try {
      await Promise.all([
        this.addGeoJsonSource(
          "districts",
          "/data/geo/haryana_districts.geojson",
          "dtname",
        ),
        this.addGeoJsonSource("boundary", "/data/geo/gurugram_boundary.geojson"),
        this.addGeoJsonSource("wards", "/data/geo/mcg_wards.geojson"),
        this.addGeoJsonSource("sectors", "/data/geo/gurugram_sectors.geojson"),
        this.addGeoJsonSource("roads", "/data/geo/mapped_roads.geojson"),
      ]);

      this.map.addLayer({
        id: "districts-fill",
        type: "fill",
        source: "districts",
        maxzoom: 9.5,
        paint: {
          "fill-color": [
            "interpolate",
            ["linear"],
            ["coalesce", ["feature-state", "intensity"], 0],
            0,
            "#d9e1dc",
            0.35,
            "#8eb4a8",
            1,
            "#24594f",
          ],
          "fill-opacity": [
            "case",
            [">", ["coalesce", ["feature-state", "count"], 0], 0],
            0.64,
            0.18,
          ],
        },
      });
      this.map.addLayer({
        id: "districts-line",
        type: "line",
        source: "districts",
        maxzoom: 9.5,
        paint: { "line-color": "#315d55", "line-width": 1 },
      });
      this.map.addLayer({
        id: "districts-label",
        type: "symbol",
        source: "districts",
        minzoom: 6,
        maxzoom: 9.5,
        layout: {
          "text-field": ["get", "dtname"],
          "text-font": ["Noto Sans Regular"],
          "text-size": 10,
        },
        paint: {
          "text-color": "#173c36",
          "text-halo-color": "#f7f6f0",
          "text-halo-width": 1.3,
        },
      });
      this.setDistrictMetrics(this.districtCounts);

      this.map.addLayer({
        id: "boundary-fill",
        type: "fill",
        source: "boundary",
        paint: { "fill-color": "#355f57", "fill-opacity": 0.08 },
      });
      this.map.addLayer({
        id: "boundary-line",
        type: "line",
        source: "boundary",
        paint: { "line-color": "#244d46", "line-width": 2 },
      });
      this.map.addLayer({
        id: "wards-fill",
        type: "fill",
        source: "wards",
        minzoom: 9,
        paint: {
          "fill-color": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            "#bb6a40",
            "#2e665e",
          ],
          "fill-opacity": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            0.28,
            0.1,
          ],
        },
      });
      this.map.addLayer({
        id: "wards-line",
        type: "line",
        source: "wards",
        minzoom: 9,
        paint: { "line-color": "#2e665e", "line-width": 1 },
      });
      this.map.addLayer({
        id: "wards-label",
        type: "symbol",
        source: "wards",
        minzoom: 10,
        layout: {
          "text-field": ["concat", "Ward ", ["to-string", ["get", "Ward_No"]]],
          "text-font": ["Noto Sans Regular"],
          "text-size": 11,
        },
        paint: {
          "text-color": "#173c36",
          "text-halo-color": "#ffffff",
          "text-halo-width": 1.5,
        },
      });
      this.map.addLayer({
        id: "sectors-fill",
        type: "fill",
        source: "sectors",
        minzoom: 10,
        layout: { visibility: "none" },
        paint: { "fill-color": "#c28443", "fill-opacity": 0.08 },
      });
      this.map.addLayer({
        id: "sectors-line",
        type: "line",
        source: "sectors",
        minzoom: 10,
        layout: { visibility: "none" },
        paint: { "line-color": "#9b5a31", "line-width": 1 },
      });
      this.map.addLayer({
        id: "sectors-label",
        type: "symbol",
        source: "sectors",
        minzoom: 11,
        layout: {
          visibility: "none",
          "text-field": ["concat", "Sector ", ["to-string", ["get", "Name"]]],
          "text-font": ["Noto Sans Regular"],
          "text-size": 10,
        },
        paint: {
          "text-color": "#633b23",
          "text-halo-color": "#ffffff",
          "text-halo-width": 1.4,
        },
      });
      this.map.addLayer({
        id: "roads-line",
        type: "line",
        source: "roads",
        minzoom: 11,
        filter: ["==", ["geometry-type"], "LineString"],
        layout: { visibility: "none" },
        paint: { "line-color": "#b14e35", "line-width": 2.2 },
      });

      this.map.on("click", "wards-fill", (event) => {
        const feature = event.features?.[0];
        const ward = feature?.properties?.Ward_No;
        if (ward !== undefined && ward !== null) this.handler("ward", String(ward));
      });
      this.map.on("click", "sectors-fill", (event) => {
        const feature = event.features?.[0];
        const sector = feature?.properties?.Name;
        if (sector) this.handler("sector", String(sector).trim());
      });
      this.map.on("click", "districts-fill", (event) => {
        const feature = event.features?.[0];
        const district = feature?.properties?.dtname;
        if (!district) return;
        this.handler("district", String(district));
        const bounds = new maplibregl.LngLatBounds();
        const geometry = feature?.geometry;
        if (geometry && "coordinates" in geometry) {
          extendBounds(bounds, geometry.coordinates);
          if (!bounds.isEmpty()) this.map?.fitBounds(bounds, { padding: 36, duration: 700 });
        }
      });
      for (const layer of ["districts-fill", "wards-fill", "sectors-fill"]) {
        this.map.on("mouseenter", layer, () => {
          const canvas = this.map?.getCanvas();
          if (canvas) canvas.style.cursor = "pointer";
        });
        this.map.on("mouseleave", layer, () => {
          const canvas = this.map?.getCanvas();
          if (canvas) canvas.style.cursor = "";
        });
      }
      this.map.once("idle", () => {
        this.container.dataset.mapReady = "true";
      });
    } catch (error) {
      /* Geometry failed to load, but the map itself is alive — say so in place rather
         than throwing into the caller, which is what used to reach the bootstrap. */
      const element = this.map?.getContainer().querySelector(".map-error");
      if (element) element.textContent = String(error);
    }
  }
}

function extendBounds(bounds: maplibregl.LngLatBounds, coordinates: unknown): void {
  if (
    Array.isArray(coordinates) &&
    coordinates.length >= 2 &&
    typeof coordinates[0] === "number" &&
    typeof coordinates[1] === "number"
  ) {
    bounds.extend([coordinates[0], coordinates[1]]);
    return;
  }
  if (Array.isArray(coordinates)) {
    for (const coordinate of coordinates) extendBounds(bounds, coordinate);
  }
}
