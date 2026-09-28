// Shapes of the API payloads (see src/gridsetu/api/engine.py).
export type Week = "stress" | "representative";
export type Variant = "baseline" | "gridsetu" | "gridsetu_coordinated";
export type CityScenario = "baseline" | "coordinated";
export type Series = (number | null)[];

export interface Axis { t0: string; n: number; dt_min: number }

export interface RunRecord {
  id: string; label: string; seeds: number; overrides: Record<string, unknown>;
  knobs: Record<string, unknown>; status: "queued" | "running" | "ready" | "failed";
  progress: number; message: string; created_at: number; finished_at: number | null; error: string | null;
}

export interface Generator {
  kind: "thermal" | "gas" | "hydro" | "solar" | "wind" | "import";
  region: string; pmax_mw: number; pmin_mw?: number; mc_inr_kwh?: number;
}

export interface Meta {
  engine: string; label: string; created_at: string; seeds: number;
  overrides: Record<string, unknown>; state_codes: string[];
  weeks: Record<Week, Axis & { label: string; outages: { unit: string; start: string; end: string }[] }>;
  config: {
    regions: Record<string, { name: string; peak_mw: Record<string, number>; rooftop_solar_mwp: number }>;
    generators: Record<string, Generator>;
    interties: { from: string; to: string; mw: number; km?: number }[];
    classes: Record<string, { priority: number; shed_cost_inr_kwh: number; demand_factor: number }>;
    feeder: {
      households: number; micro_enterprises: number; capacity_kw: number; target_peak_kw: number;
      battery: { energy_kwh: number; power_kw: number; soc_min: number; soc_max: number };
      critical_loads_kw: Record<string, number>; evening_window: [string, string];
      rooftop_solar_kwp: number; community_solar_kwp: number; tier1_island_hours: number;
      import_target_margin: number;
    };
    coordination: Record<string, number | boolean>;
    comm_slices: Record<string, { latency_ms: number; loss: number; retries: number }>;
    island: Record<string, number | string>;
    price_cap: number;
  };
}

export interface Stat { mean: number; min: number; max: number }
export type FeederMetrics = Record<string, number>;

export interface MarketStats {
  da_mcp_mean_inr_kwh: Record<string, number>; da_mcp_max_inr_kwh: Record<string, number>;
  rt_price_mean_inr_kwh: Record<string, number>; congestion_hours: number; scarcity_hours: number;
  energy_not_served_mwh: number; energy_not_served_pct: number; ens_by_class_mwh: Record<string, number>;
  shedding_hours: number; industrial_dr_mwh: number; renewable_share_pct: number;
  renewable_curtailed_mwh: number;
}

export interface WamsSummary {
  case: "A" | "B"; variant: string; lost_mw: number; system_load_mw: number; inertia_h_equiv_s: number;
  nadir_hz: number; rocof_500ms_hz_s: number; settling_hz: number; peak_tie_import_mw: number | null;
  load_shed_mw: number; ffr_peak_mw: number; events: { t_s: number; event: string; mw: number }[];
  pilot_feeder_tripped: boolean;
}

export interface Summary {
  monthly: Record<Variant, Record<string, Stat>>;
  weekly: Record<Week, Record<Variant, FeederMetrics>>;
  city: Record<Week, Record<CityScenario, MarketStats>>;
  system_factors: {
    city_peak_mw: number; city_peak_time: string; city_energy_mwh: number; city_load_factor: number;
    diversity_factor_regions: number; diversity_factor_classes_within_region: Record<string, number>;
    installed_capacity_mw: number; utilisation_factor: number; reserve_margin_at_peak_pct: number;
    region_load_factor: Record<string, number>;
  };
  feeder_factors: Record<string, number>;
  forecast_skill: { net_load: Record<string, number>; community_pv: Record<string, number> };
  fairness: Record<string, number>;
  comms: { slice: string; latency_ms: number; packet_loss: number; retries: number; messages: number;
           delivered_pct: number; transmissions: number }[];
  wams: Record<string, WamsSummary>;
  island: Record<Week, Record<"legacy" | "gridsetu", Record<string, number | string>>>;
  power_flow: { max_line_loading_pct: number; samples_over_100pct: number; mean_losses_mw: number };
  class_factors: {
    region: string; class: string; priority: number; max_demand_mw: number; avg_demand_mw: number;
    energy_mwh: number; load_factor: number; connected_load_mw: number; demand_factor: number;
    diversity_factor?: number;
  }[];
  plant_factors: {
    unit: string; kind: string; region: string; capacity_mw: number; energy_mwh: number;
    capacity_factor: number; plant_use_factor: number; operating_hours: number; curtailed_mwh: number;
  }[];
  runtime_s: number;
}

export interface CityEvent { step: number; kind: "outage" | "restore" | "shedding" | "scarcity"; label: string }
export interface CityScenarioData {
  gen: Record<string, Series>; avail: Record<string, Series>; flow: Record<string, Series>;
  price_da: Record<string, Series>; price_rt: Record<string, Series>;
  load: Record<string, Record<string, Series>>; shed: Record<string, Record<string, Series>>;
  rooftop: Record<string, Series>; dr: Series; exchange_price: Series; events: CityEvent[];
}
export interface CityPayload extends Axis {
  weather: { csi: Series; ghi: Series; temp: Series; wind_cf: Series; cos_zenith: Series };
  tie_limit: Record<string, number>;
  scenarios: Record<CityScenario, CityScenarioData>;
}

export interface Reserve {
  feeder_id: string; stage: string; issued_at: string; window_start: string; window_end: string;
  reserve_kw: number; energy_kwh: number; duration_h: number; confidence_pct: number;
  cost_inr_kwh: number; battery_kw: number; tier3_kw: number; tier2_kw: number;
  delivered_kw: number | null; cim_profile: string;
}

export interface FeederVariantData {
  series: Record<string, Series>; state: number[]; metrics: FeederMetrics;
  fairness: Record<string, number>; reserves: Reserve[]; comms: Summary["comms"];
  hh_status_b64: string; hh_lit_pct: Series;
}
export interface FeederPayload extends Axis {
  state_codes: string[]; n_households: number; capacity_kw: number; target_kw: number;
  evening_window: [string, string]; critical: Record<string, Series>;
  forecast: { net: Record<"q10" | "q50" | "q90", Series>; pv: Record<"q10" | "q50" | "q90", Series> };
  actual_net: Series; variants: Record<Variant, FeederVariantData>;
}

export interface HouseholdsPayload extends Axis {
  households: {
    id: string[]; node: number[]; peak_kw: number[]; energy_kwh: number[]; tier3_kwh: number[];
    curtailed_h: number[]; events: number[]; dark_h_gridsetu: number[]; dark_h_baseline: number[];
    daily_kwh: number[][];
  };
  curtailment_log: { step: number[]; hh: number[]; kw: number[] };
  enterprises: { id: string[]; opt_in: boolean[]; peak_kw: number[]; shiftable_kw: number[] };
  fairness: Record<string, number>;
}

export interface WamsRun {
  summary: WamsSummary; t: number[]; f_city: number[]; f_nat: number[]; tie: number[];
  shed: number[]; ffr: number[]; gov: number[];
}
export interface WamsPayload { timestamp: string | null; fleet_ffr_mw: number; runs: Record<string, WamsRun> }

export interface IslandPayload extends Axis {
  strategies: Record<"legacy" | "gridsetu", {
    metrics: Record<string, number | string>; load_kw: Series; pv_kw: Series; pv_used_kw: Series;
    diesel_kw: Series; battery_kw: Series; soc_kwh: Series; unserved_kw: Series;
  }>;
}

export interface NetworkPayload {
  every: number; baseline: Record<string, Series>; gridsetu_feeder_v: Series;
}

export interface LabKnobs {
  battery_kwh: number; battery_kw: number; capacity_kw: number; tier1_island_hours: number;
  control_loss: number; forced_outage: boolean; irrigation_shift: boolean; industrial_dr_mw: number;
}
