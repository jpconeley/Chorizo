export const pct = (p: number | null | undefined, digits = 1) =>
  p == null ? "—" : `${(p * 100).toFixed(digits)}%`;

export const usd = (value: string | number | null) => {
  if (value == null) return "—";
  const n = Number(value);
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
};

const ACRONYMS: Record<string, string> = { rna: "RNA" };

export const label = (value: string) =>
  ACRONYMS[value] ?? value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export const FEATURE_LABEL: Record<string, string> = {
  browse_assets: "Browse the asset database",
  stage_benchmarks: "Headline success rates by stage",
  benchmark_drilldown: "Success rates by therapeutic area and modality",
  asset_pos: "Probability-of-success estimate for every asset",
  watchlists: "Watchlists",
  express_interest: "Contact owners about listings",
  gated_documents: "Owner data rooms and gated documents",
  data_export: "CSV data export",
  api_access: "API access",
  model_inputs: "Full model inputs behind each estimate",
  create_listings: "List your assets for funding",
  listing_analytics: "Investor interest analytics on your listings",
};
