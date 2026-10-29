export type Stage =
  | "discovery"
  | "preclinical"
  | "phase1"
  | "phase2"
  | "phase3"
  | "regulatory"
  | "approved";

export const STAGES: Stage[] = [
  "discovery",
  "preclinical",
  "phase1",
  "phase2",
  "phase3",
  "regulatory",
  "approved",
];

export const STAGE_LABEL: Record<Stage, string> = {
  discovery: "Discovery",
  preclinical: "Preclinical",
  phase1: "Phase 1",
  phase2: "Phase 2",
  phase3: "Phase 3",
  regulatory: "Filed",
  approved: "Approved",
};

// Matches THERAPEUTIC_AREAS in backend/src/chorizo/ingest/programs.py.
export const AREAS = [
  "oncology",
  "infectious_disease",
  "cardiovascular",
  "metabolic",
  "psychiatry",
  "neurology",
  "immunology",
  "respiratory",
  "hematology",
  "gastroenterology",
  "ophthalmology",
  "dermatology",
  "renal",
  "other",
] as const;

export const MODALITIES = [
  "small_molecule",
  "antibody",
  "protein",
  "cell_therapy",
  "gene_therapy",
  "rna",
  "vaccine",
  "other",
] as const;

export type Organization = { id: number; name: string; type: string; verified: boolean };

export type AssetSummary = {
  id: number;
  name: string;
  modality: string;
  target: string | null;
  therapeutic_area: string;
  indication: string;
  stage: Stage;
  status: string;
  organization: Organization | null;
};

export type AssetDetail = AssetSummary & {
  mechanism: string | null;
  synonyms: string[];
  uses_biomarker_selection: boolean;
  orphan_designation: boolean;
  summary: string | null;
  stage_history: { stage: Stage; entered_on: string; source: string }[];
  trials: {
    nct_id: string;
    title: string;
    phase: Stage | null;
    overall_status: string;
    enrollment: number | null;
    start_date: string | null;
    completion_date: string | null;
  }[];
  trial_count: number;
  open_listing_ids: number[];
};

export type AssetPage = { items: AssetSummary[]; total: number; limit: number; offset: number };

export type Pos = {
  asset_id: number;
  model_version: string;
  next_stage_probability: number;
  likelihood_of_approval: number;
  computed_at: string;
  inputs: Record<string, { probability?: number; sample_size?: number; source?: string } | null> | null;
};

export type Benchmark = {
  stage: Stage;
  therapeutic_area: string | null;
  modality: string | null;
  transition_probability: number;
  likelihood_of_approval: number;
  sample_size: number;
  source: string;
  as_of: string;
};

export type Listing = {
  id: number;
  asset: AssetSummary;
  status: string;
  headline: string;
  amount_sought_usd: string | null;
  use_of_funds: string | null;
  deal_types: string[];
  pitch: string | null;
  created_at: string;
};

export type ListingDetail = Listing & {
  documents: { id: number; title: string; kind: string; url: string | null; locked: boolean }[];
};

export type PlanInfo = {
  plan: string;
  name: string;
  audience: string;
  per_seat: boolean;
  features: string[];
};

export type MarketStats = {
  programs: number;
  active: number;
  approved: number;
  trials: number;
  phase3_starts_12m: number;
  pipeline: { stage: Stage; count: number }[];
  approvals_by_year: { year: number; count: number }[];
};

export type FeedEvent = { asset_id: number; asset: string; stage: Stage; on: string; sponsor: string | null };

export type SearchHit = { id: number; name: string; stage: Stage; indication: string; sponsor: string | null };
