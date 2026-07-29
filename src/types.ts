export type Scope =
  | "confirmed_gurugram"
  | "likely_gurugram"
  | "statewide_multi_location"
  | "not_gurugram";

export interface Metric {
  tenders: number;
  awarded: number;
  contractValue: number;
  cancelled: number;
  retendered: number;
}

export interface DimensionMetric extends Metric {
  key: string;
}

export interface AreaRef {
  level: string;
  value: string;
  confidence: string;
  sourceField: string;
}

export interface TenderIndexRow {
  id: string;
  title: string;
  description: string;
  scope: Scope | "unclassified";
  status: string;
  awardState: string;
  isAwarded: boolean;
  isControllingAward: boolean;
  estimateValue: number | null;
  contractValue: number | null;
  year: string | null;
  month: string | null;
  yearBasis: string;
  publishedDateConflict: boolean;
  department: string;
  departmentBasis: string;
  component: string;
  components: string[];
  componentBasis: string;
  contractor: string;
  contractorKey: string;
  awardedBidCount: number | null;
  chainRoot: string;
  chainLength: number | null;
  chainAmbiguous: boolean;
  chainHasCancelOrRetender: boolean;
  titleKey: string;
  areas: AreaRef[];
  documentCount: number;
  downloadedDocumentCount: number;
  detailShard: number;
}

export interface Overview {
  datasetVersion: string;
  definitions: Record<string, string>;
  headline: {
    publishedTendersAllScopes: number;
    confirmedGurugram: number;
    confirmedPlusLikelyGurugram: number;
    confirmedAwarded: number;
    confirmedControllingContractValue: number;
  };
  scopeMetrics: Record<Scope, Metric>;
  status: Record<string, Record<string, number>>;
  components: Record<string, DimensionMetric[]>;
  departments: Record<string, DimensionMetric[]>;
  trends: Record<string, Array<Metric & { period: string }>>;
  areas: Array<Metric & { scope: Scope; level: string; value: string }>;
  contractors: ContractorMetric[];
  reviewFlags: Record<string, number>;
}

export interface ContractorMetric {
  key: string;
  name: string;
  normalizedName: string;
  awards: number;
  contractValue: number;
  departments: Record<string, number>;
  components: Record<string, number>;
  scopes: Record<string, number>;
  normalizationConfidence: string;
}

export interface DocumentEvidence {
  name: string;
  section: string;
  outcome: string;
  contentType: string;
  bytes: number | null;
  sha256: string;
  textStatus: string;
  officialUrl: string;
}

export interface TenderDetail extends TenderIndexRow {
  referenceNumber: string;
  organisationChain: string;
  tenderCategory: string;
  productCategory: string;
  contractType: string;
  formOfContract: string;
  workLocation: string;
  pincode: string;
  publishedAt: string;
  bidSubmissionEndAt: string;
  bidOpeningAt: string;
  awardDate: string;
  scheduledCompletionDays: number | null;
  awardedBidCount: number | null;
  contractorNormalized: string;
  contractorState: string;
  officialValueState: string;
  sourceHashes: Record<string, string>;
  officialStatusUrl: string;
  officialDetailUrl: string;
  chain: null | {
    root: string;
    position: number | null;
    successor: string;
    terminal: string;
    length: number | null;
    ambiguous: boolean;
    hasCancelOrRetender: boolean;
    ambiguityReasons: string;
  };
  documents: DocumentEvidence[];
}

export interface Filters {
  scopes: Set<Scope>;
  year: string;
  status: string;
  department: string;
  component: string;
  contractor: string;
  competition: string;
  chain: string;
  repeatGroup: string;
  areaLevel: string;
  areaValue: string;
  query: string;
}
