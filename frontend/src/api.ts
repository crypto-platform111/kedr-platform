export type Locale = "ru" | "en";
export type User = {
  id: string;
  email: string;
  name: string;
  level: string;
  locale: Locale;
  timezone: string;
  theme: string;
  is_demo: boolean;
};
export type SpecNode = {
  id: string;
  type: string;
  params: Record<string, unknown>;
  position: { x: number; y: number };
};
export type Spec = {
  schema_version: 1 | 2;
  symbol: string;
  timeframe: string;
  nodes: SpecNode[];
  edges: {
    id: string;
    source: string;
    target: string;
    sourceHandle?: string | null;
    targetHandle?: string | null;
  }[];
  risk: {
    max_exposure: number;
    stop_loss_pct: number | null;
    take_profit_pct: number | null;
    [key: string]: unknown;
  };
};
export type Strategy = {
  id: string;
  name: string;
  description: string;
  tags: string[];
  spec: Spec;
  latest_version_id?: string;
  version_number: number;
  created_at: string;
  updated_at: string;
};
export type Template = {
  id: string;
  name: { ru: string; en: string };
  description: { ru: string; en: string };
  spec: Spec;
};
export type Dataset = {
  id: string;
  name: string;
  symbol: string;
  timeframe: string;
  start: string;
  end: string;
  bars: number;
  source_type: string;
  sha256: string;
  description: string | { ru: string; en: string };
  gaps: unknown[] | number;
  verified: boolean;
  status?: string;
  error?: string;
};
export type Run = {
  id: string;
  strategy_id: string;
  version_id: string;
  strategy_name?: string;
  dataset: Dataset;
  config: Record<string, unknown>;
  status: string;
  created_at: string;
  metrics: Record<string, number | null>;
  equity: {
    time: string;
    equity: number;
    cash: number;
    holdings: number;
    drawdown_pct: number;
    benchmark_equity: number;
    price: number;
  }[];
  trades: {
    entry_time: string;
    exit_time?: string;
    entry_price: number;
    exit_price?: number;
    quantity: number;
    net_pnl?: number;
    fees: number;
    status: string;
    exit_reason?: string;
  }[];
  monthly: { period: string; return_pct: number }[];
  annual: { period: string; return_pct: number }[];
  quality: {
    warnings: string[];
    source_type: string;
    data_coverage_pct: number;
    independent_evaluation: boolean;
    assumptions: string[];
  };
  provenance: Record<string, unknown>;
  traces?: DecisionTraces;
};
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}
let csrf = "";
export async function api<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {}),
  };
  if (options.method && options.method !== "GET" && csrf)
    headers["X-CSRF-Token"] = csrf;
  const response = await fetch(`/api${path}`, {
    credentials: "same-origin",
    ...options,
    headers,
  });
  const data =
    response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok)
    throw new ApiError(
      typeof data?.detail === "string"
        ? data.detail
        : data?.detail
          ? JSON.stringify(data.detail)
          : `HTTP ${response.status}`,
      response.status,
    );
  if (data?.csrf_token) csrf = data.csrf_token;
  return data as T;
}
export const post = <T = any>(path: string, body: unknown = {}) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
export const put = <T = any>(path: string, body: unknown) =>
  api<T>(path, { method: "PUT", body: JSON.stringify(body) });
export const patch = <T = any>(path: string, body: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(body) });
export const brand = {
  name: { ru: "КЕДР", en: "KEDR" },
  tagline: { ru: "Лаборатория стратегий", en: "Strategy workspace" },
  version: "LOCAL / 0.2",
};

export type DecisionTraces = {
 schema_version: number; truncated: boolean; dropped: Record<string, number>; limits: Record<string, number>;
 decisions: {id:string;bar_index:number;bar_time:string;signal_completed_at:string;assumed_available_at:string;decision_time:string;node_values:Record<string,number|boolean|string|null>;true_conditions:string[];false_conditions:string[];action:string|null;state:Record<string,number|string|null>}[];
 orders: {id:string;event_id?:string;decision_id:string|null;trade_id:string|null;action:string;status:string;reason:string;signal_time?:string;decision_time?:string;eligible_at?:string;execution_time?:string;reference_price?:number;fill_price?:number;quantity?:number;fee?:number;slippage_cost?:number;account_after?:{cash:number;quantity:number};time_precision?:string;interval_end?:string}[];
 account:{time:string;cash:number;quantity:number;equity:number;unrealized_pnl:number;stop_price:number|null;take_profit_price:number|null;trailing_stop_price:number|null}[];
};
export type CatalogNode = {type:string;category:string;output:string;inputs:Record<string,string>;name:{ru:string;en:string};params:Record<string,unknown>;available:boolean;status?:'executable'|'provider_required'|'preview'|'unsupported';availability_message?:{ru:string;en:string}};
export const blankSpec = (): Spec => ({schema_version:2,symbol:'BTCUSDT',timeframe:'4h',nodes:[],edges:[],risk:{max_exposure:1,stop_loss_pct:null,take_profit_pct:null}});

/** Display-only sum of the engine's actual modeled cash costs, without changing saved results. */
export function measuredCosts(metrics: Run['metrics']): number | null {
  return typeof metrics.fees === 'number' && Number.isFinite(metrics.fees) &&
    typeof metrics.slippage_cost === 'number' && Number.isFinite(metrics.slippage_cost)
    ? metrics.fees + metrics.slippage_cost : null;
}
