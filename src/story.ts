import type { Overview, StoryData, StoryScope } from "./types";
import { escapeHtml, formatCount, formatRupees, label } from "./format";

type Action =
  | { type: "department"; value: string }
  | { type: "component"; value: string }
  | { type: "contractor"; value: string }
  | { type: "outcome"; value: string }
  | { type: "repeat"; value: string };

interface Node {
  id: string;
  title: string;
  detail: string;
  x: number;
  y: number;
  size?: number;
  kind?: "root" | "published" | "awarded" | "missing" | "review" | "entity";
  action?: Action;
}

interface Edge {
  from: string;
  to: string;
  width?: number;
  kind?: string;
}

interface Scene {
  kicker: string;
  title: string;
  explanation: string;
  footnote: string;
  nodes: Node[];
  edges: Edge[];
  particles: Array<{ key: string; count: number; kind: string }>;
}

interface StoryCallbacks {
  investigate: (action?: Action) => void;
}

const VIEW_WIDTH = 1200;
const VIEW_HEIGHT = 690;

function radialNodes(
  root: Node,
  children: Array<Omit<Node, "x" | "y">>,
  radiusX = 390,
  radiusY = 235,
): Node[] {
  return [
    root,
    ...children.map((node, index) => {
      const angle = (index / children.length) * Math.PI * 2 - Math.PI / 2;
      return {
        ...node,
        x: root.x + Math.cos(angle) * radiusX,
        y: root.y + Math.sin(angle) * radiusY,
      };
    }),
  ];
}

function sceneUniverse(data: StoryData, overview: Overview): Scene {
  const scopes = [
    {
      id: "scope-confirmed",
      title: "Confirmed Gurugram",
      detail: formatCount(overview.scopeMetrics.confirmed_gurugram.tenders),
      kind: "awarded" as const,
    },
    {
      id: "scope-likely",
      title: "Likely Gurugram",
      detail: formatCount(overview.scopeMetrics.likely_gurugram.tenders),
      kind: "review" as const,
    },
    {
      id: "scope-statewide",
      title: "Statewide / multi-location",
      detail: formatCount(overview.scopeMetrics.statewide_multi_location.tenders),
      kind: "entity" as const,
    },
    {
      id: "scope-outside",
      title: "Outside Gurugram",
      detail: formatCount(overview.scopeMetrics.not_gurugram.tenders),
      kind: "missing" as const,
    },
  ];
  return {
    kicker: "01 · The published universe",
    title: `${formatCount(data.all.records)} tenders are not ${formatCount(data.all.records)} completed works.`,
    explanation:
      "Each point is one published procurement record. Geography is evidence-graded before any value is attributed to Gurugram.",
    footnote:
      "Tender = invitation to bid. The four geographic classes are mutually exclusive.",
    nodes: radialNodes(
      {
        id: "corpus",
        title: formatCount(data.all.records),
        detail: "published tenders",
        x: 600,
        y: 345,
        size: 1.55,
        kind: "root",
      },
      scopes,
    ),
    edges: scopes.map((scope) => ({ from: "corpus", to: scope.id })),
    particles: [
      {
        key: "confirmed",
        count: overview.scopeMetrics.confirmed_gurugram.tenders,
        kind: "awarded",
      },
      {
        key: "likely",
        count: overview.scopeMetrics.likely_gurugram.tenders,
        kind: "review",
      },
      {
        key: "statewide",
        count: overview.scopeMetrics.statewide_multi_location.tenders,
        kind: "entity",
      },
      {
        key: "outside",
        count: overview.scopeMetrics.not_gurugram.tenders,
        kind: "missing",
      },
    ],
  };
}

function sceneOutcomes(scope: StoryScope): Scene {
  const ordered = [
    ["awarded", "Awarded", "awarded"],
    ["under_evaluation", "Under evaluation", "review"],
    ["retendered", "Retendered", "published"],
    ["cancelled", "Cancelled", "missing"],
    ["other_published", "Other published status", "entity"],
  ] as const;
  const children = ordered.map(([key, title, kind]) => ({
    id: `outcome-${key}`,
    title,
    detail: formatCount(scope.outcomes[key] ?? 0),
    kind,
    action: { type: "outcome", value: key } as Action,
  }));
  return {
    kicker: "02 · What happened next",
    title: `Only ${formatCount(scope.awarded)} of ${formatCount(scope.records)} confirmed Gurugram tenders reached a published award.`,
    explanation:
      "Cancelled and retendered records remain visible as procurement history, but they contribute no contract value.",
    footnote:
      "Awarded means verified AOC status. A retender is linked history, not another obligation.",
    nodes: radialNodes(
      {
        id: "corpus",
        title: formatCount(scope.records),
        detail: "confirmed Gurugram",
        x: 600,
        y: 345,
        size: 1.45,
        kind: "root",
      },
      children,
      410,
      240,
    ),
    edges: children.map((child) => ({ from: "corpus", to: child.id })),
    particles: ordered.map(([key, , kind]) => ({
      key,
      count: scope.outcomes[key] ?? 0,
      kind,
    })),
  };
}

function sceneRelationships(scope: StoryScope): Scene {
  const entries = [
    ["rel-department", "Departments", scope.relationshipCounts.department, "entity"],
    ["rel-component", "Work families", scope.relationshipCounts.component, "published"],
    ["rel-contractor", "Published contractors", scope.relationshipCounts.contractor, "awarded"],
    ["rel-place", "Place references", scope.relationshipCounts.placeReferences, "review"],
    ["rel-document", "Document records", scope.relationshipCounts.documents, "entity"],
    ["rel-bid", "Bid-stage records", scope.relationshipCounts.bidRecords, "published"],
    ["rel-event", "Lifecycle events", scope.relationshipCounts.lifecycleEvents, "entity"],
  ] as const;
  const children = entries.map(([id, title, count, kind]) => ({
    id,
    title,
    detail: formatCount(count),
    kind,
  }));
  return {
    kicker: "03 · The system behind each row",
    title: "A tender is a junction—not a row.",
    explanation:
      "The knowledge layer preserves who published it, what it covers, where it points, who bid, what happened next and which official bytes support the claim.",
    footnote:
      "336,539 entities and 658,194 typed relationships are retained in the local analytical graph.",
    nodes: radialNodes(
      {
        id: "corpus",
        title: formatCount(scope.records),
        detail: "tender junctions",
        x: 600,
        y: 345,
        size: 1.4,
        kind: "root",
      },
      children,
      430,
      240,
    ),
    edges: children.map((child) => ({ from: "corpus", to: child.id })),
    particles: [
      { key: "relationships", count: scope.records, kind: "entity" },
    ],
  };
}

function sceneMoney(scope: StoryScope): Scene {
  const edges = scope.departmentComponentEdges.slice(0, 160);
  const departments = [
    ...new Set(edges.map((edge) => edge.department)),
  ].slice(0, 8);
  const components = [
    ...new Set(
      edges
        .filter((edge) => departments.includes(edge.department))
        .map((edge) => edge.component),
    ),
  ].slice(0, 8);
  const nodes: Node[] = [
    {
      id: "money-root",
      title: formatRupees(scope.contractValue),
      detail: "published controlling contract value",
      x: 600,
      y: 92,
      size: 1.35,
      kind: "root",
    },
    ...departments.map((department, index) => ({
      id: `department-${department}`,
      title: department,
      detail: "",
      x: 205,
      y: 150 + index * 64,
      kind: "published" as const,
      action: { type: "department", value: department } as Action,
    })),
    ...components.map((component, index) => ({
      id: `component-${component}`,
      title: label(component),
      detail: "",
      x: 995,
      y: 150 + index * 64,
      kind: "awarded" as const,
      action: { type: "component", value: component } as Action,
    })),
  ];
  const selected = edges.filter(
    (edge) =>
      departments.includes(edge.department) &&
      components.includes(edge.component) &&
      edge.contractValue > 0,
  );
  const maximum = Math.max(...selected.map((edge) => edge.contractValue), 1);
  const graphEdges: Edge[] = [
    ...departments.map((department) => ({
      from: "money-root",
      to: `department-${department}`,
      width: 1,
    })),
    ...selected.map((edge) => ({
      from: `department-${edge.department}`,
      to: `component-${edge.component}`,
      width: 1 + Math.sqrt(edge.contractValue / maximum) * 8,
      kind: "money",
    })),
  ];
  return {
    kicker: "04 · Where published contract value flows",
    title: `${formatRupees(scope.contractValue)} was committed through controlling awards.`,
    explanation:
      "Follow the strongest lines from department to work family. Click a node to open the exact tenders behind it.",
    footnote:
      "This is published contract value—not expenditure, payment or proof of delivery.",
    nodes,
    edges: graphEdges,
    particles: [
      { key: "controlling", count: scope.controllingAwards, kind: "awarded" },
      {
        key: "other",
        count: Math.max(0, scope.records - scope.controllingAwards),
        kind: "missing",
      },
    ],
  };
}

function sceneEvidence(scope: StoryScope): Scene {
  const evidence = scope.evidence;
  const stages = [
    ["evidence-award", "Award status", evidence.awarded, "awarded"],
    [
      "evidence-value",
      "Contract value published",
      evidence.contractValuePublished,
      "published",
    ],
    [
      "evidence-contractor",
      "Contractor published",
      evidence.contractorPublished,
      "published",
    ],
    [
      "evidence-document",
      "Award / LOA downloaded",
      evidence.awardDocumentDownloaded,
      "entity",
    ],
    ["evidence-hewp", "Exact HEWP link", evidence.exactHewpLink, "review"],
    [
      "evidence-completion",
      "Reviewed actual completion",
      evidence.actualCompletionEvidence,
      "missing",
    ],
  ] as const;
  const nodes = stages.map(([id, title, count, kind], index) => ({
    id,
    title,
    detail: formatCount(count),
    x: 110 + index * 196,
    y: 345,
    size: index === 0 ? 1.2 : 1,
    kind,
  }));
  return {
    kicker: "05 · The accountability cliff",
    title: `${formatCount(evidence.awarded)} awards narrow to just ${formatCount(evidence.actualCompletionEvidence)} reviewed completion records.`,
    explanation:
      "The award side is unusually complete. The public execution trail collapses after award, so the portal shows the missing link instead of inventing delivery.",
    footnote:
      "Three completion records were found by the newer archive scan; every other awarded work remains unconfirmed as actually complete.",
    nodes,
    edges: nodes.slice(1).map((node, index) => ({
      from: nodes[index].id,
      to: node.id,
      width: 3,
      kind: "funnel",
    })),
    particles: [
      {
        key: "completion",
        count: evidence.actualCompletionEvidence,
        kind: "awarded",
      },
      {
        key: "missing-completion",
        count: Math.max(0, evidence.awarded - evidence.actualCompletionEvidence),
        kind: "missing",
      },
    ],
  };
}

function sceneCompetition(scope: StoryScope): Scene {
  const entries = [
    ["one_awarded_bid", "1 published awarded bid", "review"],
    ["two_to_three_awarded_bids", "2–3 published awarded bids", "published"],
    ["four_plus_awarded_bids", "4+ published awarded bids", "awarded"],
    ["not_published", "Count not published", "missing"],
  ] as const;
  const children = entries.map(([key, title, kind]) => ({
    id: `competition-${key}`,
    title,
    detail: formatCount(scope.competition[key] ?? 0),
    kind,
  }));
  return {
    kicker: "06 · Published competition evidence",
    title: `${formatCount(scope.competition.one_awarded_bid ?? 0)} awarded tenders publish exactly one awarded bid.`,
    explanation:
      "That does not prove only one firm submitted. It proves the result page published one awarded bid, which is a narrower and auditable statement.",
    footnote:
      "Bid-stage histories remain available tender by tender; this scene does not infer unpublished participation.",
    nodes: radialNodes(
      {
        id: "competition-root",
        title: formatCount(scope.awarded),
        detail: "awarded tenders",
        x: 600,
        y: 345,
        size: 1.4,
        kind: "root",
      },
      children,
      400,
      225,
    ),
    edges: children.map((child) => ({
      from: "competition-root",
      to: child.id,
    })),
    particles: entries.map(([key, , kind]) => ({
      key,
      count: scope.competition[key] ?? 0,
      kind,
    })),
  };
}

function sceneRepeats(scope: StoryScope): Scene {
  const groups = scope.repeatGroups.slice(0, 9);
  const children = groups.map((group) => ({
    id: `repeat-${group.key}`,
    title: group.title,
    detail: `${formatCount(group.records)} records · ${group.years[0]}–${group.years.at(-1)}`,
    kind: "review" as const,
    action: { type: "repeat", value: group.key } as Action,
  }));
  return {
    kicker: "07 · Recurring procurement fingerprints",
    title: "The same work descriptions reappear across years.",
    explanation:
      "These links expose retenders, phases, annual maintenance and genuinely repeated work. They are questions for review—not allegations.",
    footnote:
      "Groups require the same normalized description in at least two different tender years. Open a node to inspect every member.",
    nodes: radialNodes(
      {
        id: "repeat-root",
        title: formatCount(scope.repeatGroups.length),
        detail: "top recurring groups indexed",
        x: 600,
        y: 345,
        size: 1.25,
        kind: "root",
      },
      children,
      450,
      250,
    ),
    edges: children.map((child) => ({ from: "repeat-root", to: child.id })),
    particles: [
      {
        key: "repeat",
        count: groups.reduce((sum, group) => sum + group.records, 0),
        kind: "review",
      },
      {
        key: "other",
        count: Math.max(
          0,
          scope.records -
            groups.reduce((sum, group) => sum + group.records, 0),
        ),
        kind: "entity",
      },
    ],
  };
}

function sceneContractors(scope: StoryScope): Scene {
  const contractors = scope.contractorConcentration.slice(0, 12);
  const children = contractors.map((contractor) => ({
    id: `contractor-${contractor.key}`,
    title: contractor.name,
    detail: `${formatRupees(contractor.contractValue)} · ${formatCount(contractor.awards)} awards`,
    size: 0.85 + Math.sqrt(contractor.shareOfKnownContractorValue) * 1.8,
    kind: "awarded" as const,
    action: { type: "contractor", value: contractor.key } as Action,
  }));
  return {
    kicker: "08 · Published contractor concentration",
    title: "Contractor influence becomes visible only after identities are normalized.",
    explanation:
      "Node size follows published controlling contract value. Click any contractor to inspect departments, work families and exact award records.",
    footnote:
      "Name normalization is not an authoritative contractor identity. Shares exclude no values; unattributed contract value remains a separate published gap.",
    nodes: radialNodes(
      {
        id: "contractor-root",
        title: formatRupees(scope.contractValue),
        detail: "controlling contract value",
        x: 600,
        y: 345,
        size: 1.35,
        kind: "root",
      },
      children,
      455,
      255,
    ),
    edges: children.map((child) => ({
      from: "contractor-root",
      to: child.id,
      width: 1 + (child.size ?? 1) * 2,
      kind: "money",
    })),
    particles: [
      {
        key: "known",
        count: scope.contractorCoverage.publishedContractorAwards,
        kind: "awarded",
      },
      {
        key: "unknown",
        count: Math.max(
          0,
          scope.controllingAwards -
            scope.contractorCoverage.publishedContractorAwards,
        ),
        kind: "missing",
      },
    ],
  };
}

function scenes(data: StoryData, overview: Overview): Scene[] {
  const scope = data.confirmedGurugram;
  return [
    sceneUniverse(data, overview),
    sceneOutcomes(scope),
    sceneRelationships(scope),
    sceneMoney(scope),
    sceneEvidence(scope),
    sceneCompetition(scope),
    sceneRepeats(scope),
    sceneContractors(scope),
  ];
}

function seeded(seed: number): () => number {
  let value = seed >>> 0;
  return () => {
    value = (value * 1664525 + 1013904223) >>> 0;
    return value / 4294967296;
  };
}

function hash(value: string): number {
  let result = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 16777619);
  }
  return result >>> 0;
}

export class StoryExperience {
  private readonly scenes: Scene[];
  private current = 0;
  private readonly canvas: HTMLCanvasElement;
  private readonly context: CanvasRenderingContext2D;
  private readonly svg: SVGSVGElement;
  private readonly callbacks: StoryCallbacks;
  private resizeObserver: ResizeObserver;

  constructor(
    private readonly root: HTMLElement,
    data: StoryData,
    overview: Overview,
    callbacks: StoryCallbacks,
  ) {
    this.scenes = scenes(data, overview);
    this.callbacks = callbacks;
    this.root.innerHTML = `
      <div class="story-copy">
        <p class="story-kicker"></p>
        <h1 class="story-title"></h1>
        <p class="story-explanation"></p>
      </div>
      <div class="story-world" aria-label="Interactive procurement relationship narrative">
        <canvas class="story-particles" aria-hidden="true"></canvas>
        <svg class="story-graph" viewBox="0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}" role="img"></svg>
        <div class="story-mobile-nodes"></div>
      </div>
      <div class="story-controls">
        <button type="button" data-story="previous" aria-label="Previous finding">←</button>
        <div class="story-dots" role="tablist" aria-label="Procurement findings"></div>
        <button type="button" data-story="next" aria-label="Next finding">→</button>
        <button class="story-investigate" type="button">Open investigation mode ↓</button>
      </div>
      <p class="story-footnote"></p>
    `;
    this.canvas = this.root.querySelector<HTMLCanvasElement>("canvas")!;
    this.context = this.canvas.getContext("2d")!;
    this.svg = this.root.querySelector<SVGSVGElement>("svg")!;
    this.root.querySelector("[data-story='previous']")!.addEventListener("click", () => {
      this.go(this.current - 1);
    });
    this.root.querySelector("[data-story='next']")!.addEventListener("click", () => {
      this.go(this.current + 1);
    });
    this.root.querySelector(".story-investigate")!.addEventListener("click", () => {
      this.callbacks.investigate();
    });
    const dots = this.root.querySelector(".story-dots")!;
    this.scenes.forEach((scene, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.setAttribute("role", "tab");
      button.setAttribute("aria-label", scene.kicker);
      button.addEventListener("click", () => this.go(index));
      dots.append(button);
    });
    this.resizeObserver = new ResizeObserver(() => this.drawParticles());
    this.resizeObserver.observe(this.canvas);
    this.go(0);
  }

  private go(index: number): void {
    this.current = (index + this.scenes.length) % this.scenes.length;
    const scene = this.scenes[this.current];
    this.root.querySelector(".story-kicker")!.textContent = scene.kicker;
    this.root.querySelector(".story-title")!.textContent = scene.title;
    this.root.querySelector(".story-explanation")!.textContent = scene.explanation;
    this.root.querySelector(".story-footnote")!.textContent = scene.footnote;
    this.root.querySelectorAll<HTMLButtonElement>(".story-dots button").forEach(
      (button, dotIndex) => {
        button.setAttribute(
          "aria-selected",
          dotIndex === this.current ? "true" : "false",
        );
      },
    );
    this.renderGraph(scene);
    this.drawParticles();
  }

  private renderGraph(scene: Scene): void {
    const nodeById = new Map(scene.nodes.map((node) => [node.id, node]));
    const edges = scene.edges
      .map((edge) => {
        const from = nodeById.get(edge.from);
        const to = nodeById.get(edge.to);
        if (!from || !to) return "";
        const middle = (from.x + to.x) / 2;
        return `<path class="story-edge ${escapeHtml(edge.kind ?? "")}" d="M ${from.x} ${from.y} C ${middle} ${from.y}, ${middle} ${to.y}, ${to.x} ${to.y}" style="--edge-width:${edge.width ?? 1.5}"></path>`;
      })
      .join("");
    const nodes = scene.nodes
      .map((node) => {
        const width = Math.max(150, Math.min(260, 150 * (node.size ?? 1)));
        const height = Math.max(68, 68 * (node.size ?? 1));
        const action = node.action
          ? `data-action="${node.action.type}" data-value="${escapeHtml(node.action.value)}" role="button" aria-label="Investigate ${escapeHtml(node.title)}"`
          : "";
        return `
          <g class="story-node ${node.kind ?? "entity"} ${node.action ? "is-action" : ""}" transform="translate(${node.x - width / 2} ${node.y - height / 2})" ${action}>
            <rect width="${width}" height="${height}" rx="${Math.min(26, height / 2)}"></rect>
            <foreignObject width="${width}" height="${height}">
              <div class="story-node-copy">
                <strong>${escapeHtml(node.title)}</strong>
                ${node.detail ? `<span>${escapeHtml(node.detail)}</span>` : ""}
              </div>
            </foreignObject>
          </g>`;
      })
      .join("");
    this.svg.innerHTML = `<g class="story-edges">${edges}</g><g class="story-nodes">${nodes}</g>`;
    this.svg.querySelectorAll<SVGGElement>("[data-action]").forEach((element) => {
      element.addEventListener("click", () => {
        this.callbacks.investigate({
          type: element.dataset.action as Action["type"],
          value: element.dataset.value ?? "",
        } as Action);
      });
    });
    const mobile = this.root.querySelector<HTMLElement>(".story-mobile-nodes")!;
    mobile.innerHTML = scene.nodes
      .map(
        (node) =>
          `<button type="button" class="${node.kind ?? "entity"}" ${node.action ? `data-mobile-action="${node.action.type}" data-mobile-value="${escapeHtml(node.action.value)}"` : "disabled"}><strong>${escapeHtml(node.title)}</strong><span>${escapeHtml(node.detail)}</span></button>`,
      )
      .join("");
    mobile
      .querySelectorAll<HTMLButtonElement>("[data-mobile-action]")
      .forEach((button) => {
        button.addEventListener("click", () => {
          this.callbacks.investigate({
            type: button.dataset.mobileAction as Action["type"],
            value: button.dataset.mobileValue ?? "",
          } as Action);
        });
      });
  }

  private drawParticles(): void {
    const rect = this.canvas.getBoundingClientRect();
    const ratio = Math.min(devicePixelRatio || 1, 2);
    this.canvas.width = Math.max(1, Math.round(rect.width * ratio));
    this.canvas.height = Math.max(1, Math.round(rect.height * ratio));
    this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.context.clearRect(0, 0, rect.width, rect.height);
    const scene = this.scenes[this.current];
    const total = scene.particles.reduce((sum, group) => sum + group.count, 0);
    const maximumDots = 49_121;
    const scale = total > maximumDots ? maximumDots / total : 1;
    const clusters = scene.particles.length;
    const styles = getComputedStyle(this.root);
    const colors: Record<string, string> = {
      root: styles.getPropertyValue("--story-root").trim(),
      published: styles.getPropertyValue("--story-published").trim(),
      awarded: styles.getPropertyValue("--story-awarded").trim(),
      missing: styles.getPropertyValue("--story-missing").trim(),
      review: styles.getPropertyValue("--story-review").trim(),
      entity: styles.getPropertyValue("--story-entity").trim(),
    };
    scene.particles.forEach((group, groupIndex) => {
      const random = seeded(hash(`${this.current}:${group.key}`));
      const count = Math.round(group.count * scale);
      const columns = Math.ceil(Math.sqrt(clusters));
      const rows = Math.ceil(clusters / columns);
      const column = groupIndex % columns;
      const row = Math.floor(groupIndex / columns);
      const centerX = ((column + 0.5) / columns) * rect.width;
      const centerY = ((row + 0.5) / rows) * rect.height;
      const spreadX = rect.width / columns / 2.6;
      const spreadY = rect.height / rows / 2.6;
      this.context.fillStyle = colors[group.kind] || colors.entity;
      this.context.globalAlpha = group.kind === "missing" ? 0.16 : 0.28;
      for (let index = 0; index < count; index += 1) {
        const angle = random() * Math.PI * 2;
        const radius = Math.sqrt(random());
        const x = centerX + Math.cos(angle) * radius * spreadX;
        const y = centerY + Math.sin(angle) * radius * spreadY;
        this.context.fillRect(x, y, 1.25, 1.25);
      }
    });
    this.context.globalAlpha = 1;
  }
}
