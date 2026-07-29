import { BarChart, HeatmapChart, LineChart, PieChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import { type ECharts, init, use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import type { DimensionMetric, Metric, TenderIndexRow } from "./types";
import { formatRupees, label } from "./format";

use([
  BarChart,
  HeatmapChart,
  LineChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
]);

const instances = new Map<HTMLElement, ECharts>();

function chart(element: HTMLElement): ECharts {
  let instance = instances.get(element);
  if (!instance) {
    instance = init(element, undefined, { renderer: "canvas" });
    instances.set(element, instance);
  }
  return instance;
}

const text = "#20332f";
const muted = "#677a75";
const primary = "#2f665d";
const accent = "#bd6d45";
const grid = "#dce5e1";

export function renderStatusChart(
  element: HTMLElement,
  values: Record<string, number>,
  onSelect: (status: string) => void,
): void {
  const rows = Object.entries(values).sort((a, b) => b[1] - a[1]);
  const instance = chart(element);
  instance.setOption({
    animationDuration: 350,
    grid: { left: 150, right: 32, top: 14, bottom: 28 },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: {
      type: "value",
      axisLabel: { color: muted },
      splitLine: { lineStyle: { color: grid } },
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: rows.map(([key]) => key),
      axisLabel: { color: text, width: 135, overflow: "truncate" },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        type: "bar",
        data: rows.map(([, value]) => value),
        itemStyle: { color: primary, borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: "right", color: text },
      },
    ],
  });
  instance.off("click");
  instance.on("click", (event) => onSelect(String(event.name)));
}

export function renderTrendChart(
  element: HTMLElement,
  rows: Array<Metric & { period: string }>,
): void {
  const yearly = new Map<string, Metric>();
  for (const row of rows) {
    const year = row.period.slice(0, 4);
    const current = yearly.get(year) ?? {
      tenders: 0,
      awarded: 0,
      contractValue: 0,
      cancelled: 0,
      retendered: 0,
    };
    current.tenders += row.tenders;
    current.awarded += row.awarded;
    current.contractValue += row.contractValue;
    current.cancelled += row.cancelled;
    current.retendered += row.retendered;
    yearly.set(year, current);
  }
  const values = [...yearly.entries()].sort();
  chart(element).setOption({
    animationDuration: 350,
    color: [primary, accent],
    grid: { left: 52, right: 18, top: 24, bottom: 34 },
    tooltip: { trigger: "axis" },
    legend: { top: 0, textStyle: { color: muted } },
    xAxis: {
      type: "category",
      data: values.map(([year]) => year),
      axisLabel: { color: muted },
      axisLine: { lineStyle: { color: grid } },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: muted },
      splitLine: { lineStyle: { color: grid } },
    },
    series: [
      {
        name: "Published tenders",
        type: "line",
        smooth: true,
        symbolSize: 7,
        data: values.map(([, metric]) => metric.tenders),
      },
      {
        name: "Awarded",
        type: "line",
        smooth: true,
        symbolSize: 7,
        data: values.map(([, metric]) => metric.awarded),
      },
    ],
  });
}

export function renderDepartmentChart(
  element: HTMLElement,
  rows: DimensionMetric[],
  onSelect: (department: string) => void,
): void {
  const top = rows.slice(0, 14).reverse();
  const instance = chart(element);
  instance.setOption({
    grid: { left: 190, right: 32, top: 12, bottom: 30 },
    tooltip: {
      trigger: "axis",
      formatter: (items: unknown) => {
        const item = (items as Array<{ name: string; value: number }>)[0];
        const metric = top.find((row) => row.key === item.name);
        return metric
          ? `<b>${item.name}</b><br>${metric.tenders.toLocaleString("en-IN")} tenders<br>${metric.awarded.toLocaleString("en-IN")} awarded<br>${formatRupees(metric.contractValue)} contract value`
          : "";
      },
    },
    xAxis: {
      type: "value",
      axisLabel: { color: muted },
      splitLine: { lineStyle: { color: grid } },
    },
    yAxis: {
      type: "category",
      data: top.map((row) => row.key),
      axisLabel: { color: text, width: 178, overflow: "truncate" },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        type: "bar",
        data: top.map((row) => row.tenders),
        itemStyle: { color: primary, borderRadius: [0, 4, 4, 0] },
      },
    ],
  });
  instance.off("click");
  instance.on("click", (event) => onSelect(String(event.name)));
}

export function renderComponentDonut(
  element: HTMLElement,
  rows: DimensionMetric[],
  onSelect: (component: string) => void,
): void {
  const instance = chart(element);
  instance.setOption({
    tooltip: { trigger: "item" },
    legend: {
      type: "scroll",
      orient: "vertical",
      right: 0,
      top: 20,
      bottom: 20,
      textStyle: { color: muted },
    },
    series: [
      {
        type: "pie",
        radius: ["48%", "76%"],
        center: ["34%", "50%"],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: "#ffffff", borderWidth: 2 },
        label: { show: false },
        data: rows.map((row) => ({ name: label(row.key), value: row.tenders, key: row.key })),
      },
    ],
  });
  instance.off("click");
  instance.on("click", (event) => {
    const data = event.data as { key?: string } | undefined;
    if (data?.key) onSelect(data.key);
  });
}

export function renderFilteredValueChart(
  element: HTMLElement,
  rows: TenderIndexRow[],
): void {
  const years = new Map<string, number>();
  for (const row of rows) {
    if (!row.year || !row.isControllingAward || row.contractValue === null) continue;
    years.set(row.year, (years.get(row.year) ?? 0) + row.contractValue);
  }
  const values = [...years.entries()].sort();
  chart(element).setOption({
    grid: { left: 70, right: 18, top: 20, bottom: 34 },
    tooltip: {
      trigger: "axis",
      formatter: (items: unknown) => {
        const item = (items as Array<{ name: string; value: number }>)[0];
        return `<b>${item.name}</b><br>${formatRupees(item.value)} published contract value`;
      },
    },
    xAxis: {
      type: "category",
      data: values.map(([year]) => year),
      axisLabel: { color: muted },
    },
    yAxis: {
      type: "value",
      axisLabel: {
        color: muted,
        formatter: (value: number) => `${Math.round(value / 10_000_000)}cr`,
      },
      splitLine: { lineStyle: { color: grid } },
    },
    series: [
      {
        type: "bar",
        data: values.map(([, value]) => value),
        itemStyle: { color: accent, borderRadius: [4, 4, 0, 0] },
      },
    ],
  });
}

export function renderDepartmentComponentHeatmap(
  element: HTMLElement,
  rows: TenderIndexRow[],
  onSelect: (department: string, component: string) => void,
): void {
  const departmentCounts = new Map<string, number>();
  const componentCounts = new Map<string, number>();
  const cells = new Map<string, number>();
  for (const row of rows) {
    departmentCounts.set(
      row.department,
      (departmentCounts.get(row.department) ?? 0) + 1,
    );
    componentCounts.set(
      row.component,
      (componentCounts.get(row.component) ?? 0) + 1,
    );
    const key = `${row.department}\u0000${row.component}`;
    cells.set(key, (cells.get(key) ?? 0) + 1);
  }
  const departments = [...departmentCounts]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 12)
    .map(([name]) => name);
  const components = [...componentCounts]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 12)
    .map(([name]) => name);
  const values: Array<[number, number, number]> = [];
  let maximum = 1;
  components.forEach((component, y) => {
    departments.forEach((department, x) => {
      const value = cells.get(`${department}\u0000${component}`) ?? 0;
      maximum = Math.max(maximum, value);
      values.push([x, y, value]);
    });
  });
  const instance = chart(element);
  instance.setOption({
    animationDuration: 250,
    grid: { left: 120, right: 30, top: 88, bottom: 42 },
    tooltip: {
      formatter: (item: unknown) => {
        const data = (item as { data: [number, number, number] }).data;
        return `<b>${departments[data[0]]}</b><br>${label(components[data[1]])}<br>${data[2].toLocaleString("en-IN")} tenders`;
      },
    },
    xAxis: {
      type: "category",
      data: departments,
      position: "top",
      axisLabel: {
        color: text,
        rotate: 42,
        width: 112,
        overflow: "truncate",
        fontSize: 10,
      },
      splitArea: { show: true },
    },
    yAxis: {
      type: "category",
      data: components.map(label),
      axisLabel: { color: text, width: 108, overflow: "truncate" },
      splitArea: { show: true },
    },
    visualMap: {
      min: 0,
      max: maximum,
      calculable: false,
      orient: "horizontal",
      left: "center",
      top: 4,
      text: ["More", "Fewer"],
      inRange: { color: ["#edf1ee", "#8fb2a7", "#24594f"] },
      textStyle: { color: muted },
    },
    series: [
      {
        type: "heatmap",
        data: values,
        emphasis: { itemStyle: { borderColor: "#bd6d45", borderWidth: 2 } },
      },
    ],
  });
  instance.off("click");
  instance.on("click", (event) => {
    const data = event.data as [number, number, number] | undefined;
    if (data) onSelect(departments[data[0]], components[data[1]]);
  });
}

export function renderCompetitionChart(
  element: HTMLElement,
  rows: TenderIndexRow[],
  onSelect: (bucket: string) => void,
): void {
  const awarded = rows.filter((row) => row.isAwarded);
  const values = [
    {
      key: "one_bid",
      name: "One awarded bid published",
      value: awarded.filter((row) => row.awardedBidCount === 1).length,
    },
    {
      key: "multi_bid",
      name: "Two or more awarded bids",
      value: awarded.filter((row) => (row.awardedBidCount ?? 0) >= 2).length,
    },
    {
      key: "not_published",
      name: "Bid count not published",
      value: awarded.filter((row) => row.awardedBidCount === null).length,
    },
  ];
  const instance = chart(element);
  instance.setOption({
    color: [accent, primary, "#b9c7c2"],
    tooltip: { trigger: "item" },
    legend: {
      orient: "vertical",
      right: 0,
      top: 40,
      textStyle: { color: muted },
    },
    series: [
      {
        type: "pie",
        radius: ["45%", "72%"],
        center: ["30%", "50%"],
        label: { show: false },
        itemStyle: { borderColor: "#fff", borderWidth: 2 },
        data: values,
      },
    ],
  });
  instance.off("click");
  instance.on("click", (event) => {
    const data = event.data as { key?: string };
    if (data.key) onSelect(data.key);
  });
}

export function renderChainChart(
  element: HTMLElement,
  rows: TenderIndexRow[],
  onSelect: (bucket: string) => void,
): void {
  const roots = new Map<string, TenderIndexRow[]>();
  for (const row of rows) {
    const group = roots.get(row.chainRoot) ?? [];
    group.push(row);
    roots.set(row.chainRoot, group);
  }
  const buckets = [
    {
      key: "single",
      name: "Single-stage records",
      value: [...roots.values()].filter(
        (group) =>
          !group.some((row) => row.chainHasCancelOrRetender) &&
          !group.some((row) => row.chainAmbiguous),
      ).length,
    },
    {
      key: "reworked",
      name: "Cancel / retender history",
      value: [...roots.values()].filter((group) =>
        group.some((row) => row.chainHasCancelOrRetender),
      ).length,
    },
    {
      key: "ambiguous",
      name: "Ambiguous chains",
      value: [...roots.values()].filter((group) =>
        group.some((row) => row.chainAmbiguous),
      ).length,
    },
  ];
  const instance = chart(element);
  instance.setOption({
    grid: { left: 165, right: 28, top: 20, bottom: 30 },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: {
      type: "value",
      axisLabel: { color: muted },
      splitLine: { lineStyle: { color: grid } },
    },
    yAxis: {
      type: "category",
      data: buckets.map((bucket) => bucket.name),
      axisLabel: { color: text },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        type: "bar",
        data: buckets.map((bucket) => ({
          value: bucket.value,
          key: bucket.key,
          itemStyle: {
            color:
              bucket.key === "single"
                ? primary
                : bucket.key === "ambiguous"
                  ? "#9b3d2d"
                  : accent,
          },
        })),
        label: { show: true, position: "right", color: text },
      },
    ],
  });
  instance.off("click");
  instance.on("click", (event) => {
    const data = event.data as { key?: string };
    if (data.key) onSelect(data.key);
  });
}

export function resizeCharts(): void {
  for (const instance of instances.values()) instance.resize();
}
