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
  description?: string;
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
  /* Removed from the published index: it pointed at the 64-way shard layout that
     public/data/tender/<aa>/<bb>/<ID>.json replaced. The path is now derived from the
     Tender ID itself (see packageUrl in data.ts), so nothing needs to carry it.
     Optional rather than deleted so an older cached index still typechecks. */
  detailShard?: number;
  /* Non-null only where the normalised work title occurs on more than one tender.
     Replaces `titleKey`, which cost 4.63 MB to publish 35,393 normalised strings when
     the repeated-work filter only ever needed a group identity. */
  repeatGroup?: number | null;
  /* HOW the work was bought — maintenance / hired_capacity / recalled — orthogonal to
     `component`, which says WHAT was bought. Ships as a 3-bit integer decoded against
     the index's `contractModeFlags` legend (see loadTenders). */
  contractModes: string[];
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
  hewpRecords: Array<{
    place: string;
    areaType: string;
    block: string;
    panchayat: string;
    department: string;
    division: string;
    estimateName: string;
    agreementName: string;
    estimateValue: number | null;
    contractStart: string;
    contractEnd: string;
    agency: string;
    sourceUrl: string;
    sourceSha256: string;
    linkMethod: string;
  }>;
  mcgLinks: Array<{
    workId: string;
    workName: string;
    contractor: string;
    sanctionedValue: number | null;
    workStart: string;
    progressPercent: number | null;
    physicalStatus: string;
    linkMethod: string;
    linkGrade: string;
    interpretation: string;
  }>;
  assetLinks: Array<{
    assetKey: string;
    component: string;
    coverage: string;
    proofGrade: string;
    validatorReason: string;
    evidenceSha256: string;
  }>;
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
  place: string;
  areaLevel: string;
  areaValue: string;
  outcome: string;
  query: string;
}

export interface PlaceRecord {
  name: string;
  variants: string[];
  block: string;
  panchayat: string;
  areaType: string;
  locationCode: string;
  workCount: number;
  awardedWorkCount: number;
  tenderIds: string[];
  boundaryGeometryAvailable: boolean;
  sourceSha256: string;
}

export interface StoryEvidence {
  awarded: number;
  contractValuePublished: number;
  contractorPublished: number;
  awardDocumentDownloaded: number;
  exactHewpLink: number;
  actualCompletionEvidence: number;
}

export interface StoryScope {
  records: number;
  outcomes: Record<string, number>;
  awarded: number;
  controllingAwards: number;
  contractValue: number;
  evidence: StoryEvidence;
  competition: Record<string, number>;
  awardVsEstimate: Record<string, number>;
  largestAwardEstimateDifferences: Array<{
    tenderId: string;
    differencePercent: number;
  }>;
  contractorCoverage: {
    publishedContractorAwards: number;
    publishedContractorValue: number;
    unattributedContractValue: number;
  };
  contractorConcentration: Array<{
    rank: number;
    key: string;
    name: string;
    awards: number;
    contractValue: number;
    shareOfAllPublishedValue: number;
    shareOfKnownContractorValue: number;
    cumulativeKnownValueShare: number;
  }>;
  departmentComponentEdges: Array<{
    department: string;
    component: string;
    tenders: number;
    awards: number;
    contractValue: number;
  }>;
  repeatGroups: Array<{
    key: string;
    title: string;
    records: number;
    awarded: number;
    contractValue: number;
    years: string[];
    departments: string[];
    components: string[];
    tenderIds: string[];
  }>;
  relationshipCounts: {
    department: number;
    component: number;
    contractor: number;
    placeReferences: number;
    documents: number;
    bidRecords: number;
    lifecycleEvents: number;
  };
}

export interface StoryData {
  datasetVersion: string;
  definitions: Record<string, string>;
  all: StoryScope;
  confirmedGurugram: StoryScope;
  confirmedPlusLikely: StoryScope;
}

export interface TenderIntelligence {
  understanding: {
    outcome: string;
    department: string;
    components: string[];
    scope: string;
    places: AreaRef[];
    chainRoot: string;
    evidence: {
      level: string;
      awardDocumentRecords: number;
      awardDocumentDownloaded: boolean;
      contractorPublished: boolean;
      contractValuePublished: boolean;
      exactHewpLinks: number;
      mcgLinks: number;
      confirmedAssetLinks: number;
      actualCompletionRecords: number;
    };
    bidMetrics: Record<string, number>;
    lifecycleEventCounts: Record<string, number>;
  };
  bids: Array<{
    number: string;
    bidder: string;
    status: string;
    submittedAt: string;
    rank: string;
    financialValue: number | null;
    isAwarded: boolean;
    sourceSha256: string;
  }>;
  lifecycle: Array<{
    sequence: string;
    at: string;
    type: string;
    status: string;
    detail: string;
    sourceType: string;
    sourceSha256: string;
  }>;
  reviewFlags: Array<{
    id: string;
    severity: string;
    message: string;
    observedValue: string;
    requiredEvidence: string;
    ruleSourceUrl: string;
    notAnAccusation: boolean;
  }>;
  actualCompletionEvidence: Array<{
    date: string;
    assessment: string;
    context: string;
    page: string;
    sha256: string;
    sourcePath: string;
  }>;
}

/* Attached by scripts/build_value_corrections.py to the 264 tenders whose published
   award value carries the lakh-denomination signature. `correctedValueInr` is present
   only where an award letter states an agreement amount; otherwise the value is flagged
   and nothing is substituted. */
export interface ValueCorrection {
  status: "corrected_from_award_letter" | "implausible_no_letter";
  publishedValueInr: number;
  correctedValueInr: number | null;
  estimateInr: number;
  estimateOverPublished: number;
  evidenceSha256: string | null;
  evidenceStage: string | null;
  evidenceLine: string | null;
}
