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

export class EvidenceMap {
  private map: MapLibreMap;
  private handler: GeographyHandler;
  private container: HTMLElement;
  private districtCounts = new Map<string, number>();

  constructor(container: HTMLElement, handler: GeographyHandler) {
    this.handler = handler;
    this.container = container;
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
  }

  haryana(): void {
    this.map.fitBounds(HARYANA_BOUNDS, { padding: 36, duration: 700 });
  }

  gurugram(): void {
    this.map.fitBounds(GURUGRAM_BOUNDS, { padding: 28, duration: 700 });
  }

  toggleLayer(name: "wards" | "sectors" | "roads", visible: boolean): void {
    for (const suffix of ["fill", "line", "label"]) {
      const id = `${name}-${suffix}`;
      if (this.map.getLayer(id)) {
        this.map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
      }
    }
  }

  resize(): void {
    this.map.resize();
  }

  setDistrictMetrics(values: Map<string, number>): void {
    this.districtCounts = values;
    if (!this.map.getSource("districts")) return;
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
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Could not load ${id} geometry.`);
    const data = await response.json();
    this.map.addSource(id, { type: "geojson", data, ...(promoteId ? { promoteId } : {}) });
  }

  private async addEvidenceLayers(): Promise<void> {
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
          if (!bounds.isEmpty()) this.map.fitBounds(bounds, { padding: 36, duration: 700 });
        }
      });
      for (const layer of ["districts-fill", "wards-fill", "sectors-fill"]) {
        this.map.on("mouseenter", layer, () => {
          this.map.getCanvas().style.cursor = "pointer";
        });
        this.map.on("mouseleave", layer, () => {
          this.map.getCanvas().style.cursor = "";
        });
      }
      this.map.once("idle", () => {
        this.container.dataset.mapReady = "true";
      });
    } catch (error) {
      const element = this.map.getContainer().querySelector(".map-error");
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
