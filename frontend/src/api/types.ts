/**
 * Agent-State Contracts & Shared Types — Task P1-FE-6 (Git Issue #40).
 *
 * Mirrors the 7 core contracts and enums defined in `backend/models/`:
 * 1. HedgeContext (BRD §14)
 * 2. StrategyHypothesis (BRD §16)
 * 3. StrategyDecision (BRD §18)
 * 4. RiskDecision (BRD §20)
 * 5. ExecutionPlan (BRD §21)
 * 6. ExecutionResult (BRD §23)
 * 7. MonitoringState (BRD §24)
 */

// ============================================================================
// Shared Enumerations
// ============================================================================

export type StrategyType =
  | 'PROTECTIVE_PUT'
  | 'PUT_SPREAD'
  | 'COLLAR'
  | 'NO_HEDGE';

export const StrategyType = {
  PROTECTIVE_PUT: 'PROTECTIVE_PUT' as StrategyType,
  PUT_SPREAD: 'PUT_SPREAD' as StrategyType,
  COLLAR: 'COLLAR' as StrategyType,
  NO_HEDGE: 'NO_HEDGE' as StrategyType,
} as const;

export type HedgeAction =
  | 'NEW_HEDGE'
  | 'INCREASE'
  | 'DECREASE'
  | 'MAINTAIN'
  | 'REMOVE'
  | 'REPLACE'
  | 'NO_TRADE';

export const HedgeAction = {
  NEW_HEDGE: 'NEW_HEDGE' as HedgeAction,
  INCREASE: 'INCREASE' as HedgeAction,
  DECREASE: 'DECREASE' as HedgeAction,
  MAINTAIN: 'MAINTAIN' as HedgeAction,
  REMOVE: 'REMOVE' as HedgeAction,
  REPLACE: 'REPLACE' as HedgeAction,
  NO_TRADE: 'NO_TRADE' as HedgeAction,
} as const;

export type DecisionType =
  | 'SELECT_STRATEGY'
  | 'NO_TRADE'
  | 'REASSESS';

export const DecisionType = {
  SELECT_STRATEGY: 'SELECT_STRATEGY' as DecisionType,
  NO_TRADE: 'NO_TRADE' as DecisionType,
  REASSESS: 'REASSESS' as DecisionType,
} as const;

export type RiskVerdict =
  | 'APPROVE'
  | 'MODIFY'
  | 'REJECT';

export const RiskVerdict = {
  APPROVE: 'APPROVE' as RiskVerdict,
  MODIFY: 'MODIFY' as RiskVerdict,
  REJECT: 'REJECT' as RiskVerdict,
} as const;

export type OrderStatus =
  | 'PENDING'
  | 'SUBMITTED'
  | 'FILLED'
  | 'PARTIALLY_FILLED'
  | 'CANCELLED'
  | 'EXPIRED'
  | 'REJECTED';

export const OrderStatus = {
  PENDING: 'PENDING' as OrderStatus,
  SUBMITTED: 'SUBMITTED' as OrderStatus,
  FILLED: 'FILLED' as OrderStatus,
  PARTIALLY_FILLED: 'PARTIALLY_FILLED' as OrderStatus,
  CANCELLED: 'CANCELLED' as OrderStatus,
  EXPIRED: 'EXPIRED' as OrderStatus,
  REJECTED: 'REJECTED' as OrderStatus,
} as const;

export type ExecutionStatus =
  | 'FILLED'
  | 'PARTIALLY_FILLED'
  | 'FAILED'
  | 'CANCELLED';

export const ExecutionStatus = {
  FILLED: 'FILLED' as ExecutionStatus,
  PARTIALLY_FILLED: 'PARTIALLY_FILLED' as ExecutionStatus,
  FAILED: 'FAILED' as ExecutionStatus,
  CANCELLED: 'CANCELLED' as ExecutionStatus,
} as const;

export type TriggerType =
  | 'PORTFOLIO_DELTA'
  | 'VOLATILITY_SPIKE'
  | 'CORRELATION_BREAKDOWN'
  | 'DRAWDOWN_LIMIT'
  | 'TIME_ELAPSED'
  | 'MANUAL';

export const TriggerType = {
  PORTFOLIO_DELTA: 'PORTFOLIO_DELTA' as TriggerType,
  VOLATILITY_SPIKE: 'VOLATILITY_SPIKE' as TriggerType,
  CORRELATION_BREAKDOWN: 'CORRELATION_BREAKDOWN' as TriggerType,
  DRAWDOWN_LIMIT: 'DRAWDOWN_LIMIT' as TriggerType,
  TIME_ELAPSED: 'TIME_ELAPSED' as TriggerType,
  MANUAL: 'MANUAL' as TriggerType,
} as const;

export type OptionRight = 'CALL' | 'PUT';

export const OptionRight = {
  CALL: 'CALL' as OptionRight,
  PUT: 'PUT' as OptionRight,
} as const;

export type OrderSide = 'BUY' | 'SELL';

export const OrderSide = {
  BUY: 'BUY' as OrderSide,
  SELL: 'SELL' as OrderSide,
} as const;

export type AssetClass = 'EQUITY' | 'OPTION' | 'CASH';

export const AssetClass = {
  EQUITY: 'EQUITY' as AssetClass,
  OPTION: 'OPTION' as AssetClass,
  CASH: 'CASH' as AssetClass,
} as const;

// ============================================================================
// Common Building Blocks
// ============================================================================

export interface OptionLeg {
  underlying: string;
  right: OptionRight;
  side: OrderSide;
  strike: number;
  expiration: string; // ISO date format YYYY-MM-DD
  quantity: number;
  limit_price?: number | null;
  occ_symbol?: string | null;
}

export interface PortfolioPosition {
  symbol: string;
  qty: number;
  avg_price: number;
  market_value: number;
  asset_class?: AssetClass;
  side?: OrderSide;
  unrealized_pl?: number | null;
}

// ============================================================================
// 1. HedgeContext Contract (BRD §14)
// ============================================================================

export interface PortfolioState {
  total_value: number;
  cash: number;
  equity: number;
  buying_power: number;
  positions: PortfolioPosition[];
  gross_exposure?: number | null;
  net_exposure?: number | null;
  concentration_hhi?: number | null;
  drawdown?: number | null;
  max_drawdown?: number | null;
  volatility?: number | null;
  beta?: number | null;
}

export interface MarketState {
  regime?: string | null;
  index_trend?: string | null;
  vix?: number | null;
  as_of?: string | null; // ISO datetime
}

export interface StockView {
  symbol: string;
  risk_note?: string | null;
  momentum?: number | null;
  key_levels: number[];
}

export interface NewsItem {
  headline: string;
  ts: string; // ISO datetime
  symbols: string[];
  source?: string | null;
  sentiment?: number | null;
  is_event: boolean;
}

export interface OptionCandidate {
  underlying: string;
  right: OptionRight;
  strike: number;
  expiration: string;
  premium: number;
  bid?: number | null;
  ask?: number | null;
  volume?: number | null;
  open_interest?: number | null;
  iv?: number | null;
  delta?: number | null;
  gamma?: number | null;
  theta?: number | null;
  vega?: number | null;
  liquidity?: string | null;
}

export interface CurrentHedge {
  active: boolean;
  strategy_type?: StrategyType | null;
  legs: OptionLeg[];
  hedge_ratio?: number | null;
  target_hedge_ratio?: number | null;
  cost_basis?: number | null;
  hedge_pnl?: number | null;
  expiration?: string | null;
}

export interface HedgeObjective {
  max_hedge_budget_pct: number;
  drawdown_tolerance_pct: number;
  target_hedge_ratio?: number | null;
  notes?: string | null;
}

export interface HedgeContext {
  cycle_id: string;
  timestamp: string; // ISO datetime
  portfolio_state: PortfolioState;
  objective: HedgeObjective;
  market_state?: MarketState | null;
  stock_state: StockView[];
  news_context: NewsItem[];
  option_candidates: OptionCandidate[];
  current_hedge: CurrentHedge;
  degraded_sections: string[];
  schema_version: number;
}

// ============================================================================
// 2. StrategyHypothesis Contract (BRD §16)
// ============================================================================

export interface HedgeMetrics {
  hedge_ratio?: number | null;
  downside_protection_pct?: number | null;
  cost_pct_of_portfolio?: number | null;
  net_delta?: number | null;
  net_gamma?: number | null;
  net_theta?: number | null;
  net_vega?: number | null;
  max_loss?: number | null;
  breakevens: number[];
}

export interface PayoffPoint {
  price: number;
  pnl: number;
}

export interface StrategyHypothesis {
  cycle_id: string;
  strategy: StrategyType;
  action: HedgeAction;
  viable: boolean;
  legs: OptionLeg[];
  cost: number;
  hedge_metrics: HedgeMetrics;
  payoff_profile: PayoffPoint[];
  liquidity?: string | null;
  risks: string[];
  tradeoffs: string[];
  rationale: string;
  rejection_conditions: string[];
  rejection_reason?: string | null;
}

// ============================================================================
// 3. StrategyDecision Contract (BRD §18)
// ============================================================================

export interface ComparisonRow {
  strategy: StrategyType;
  cost: number;
  downside_protection_pct?: number | null;
  upside_giveup_pct?: number | null;
  liquidity?: string | null;
  verdict?: string | null;
  score?: number | null;
}

export interface StrategyDecision {
  cycle_id: string;
  decision: DecisionType;
  selected_strategy?: StrategyType | null;
  selected_hypothesis?: StrategyHypothesis | null;
  alternatives: StrategyHypothesis[];
  comparison: ComparisonRow[];
  rationale: string;
  reassessment_conditions: string[];
}

// ============================================================================
// 4. RiskDecision Contract (BRD §20)
// ============================================================================

export interface RiskCheck {
  name: string;
  category: string; // PORTFOLIO | POSITION_LIMITS | COST | OPTIONS | EXECUTION
  passed: boolean;
  detail?: string | null;
  observed?: number | null;
  limit?: number | null;
}

export interface RiskModification {
  field: string;
  from_value?: number | string | null;
  to_value?: number | string | null;
  reason: string;
}

export interface RiskDecision {
  cycle_id: string;
  verdict: RiskVerdict;
  checks: RiskCheck[];
  violations: string[];
  warnings: string[];
  modifications: RiskModification[];
  rationale: string;
  approved_hypothesis?: StrategyHypothesis | null;
}

// ============================================================================
// 5. ExecutionPlan Contract (BRD §21)
// ============================================================================

export interface OrderConstraints {
  time_in_force: string;
  order_type: string;
  limit_price?: number | null;
  price_tolerance_pct: number;
  allow_legging: boolean;
}

export interface ExecutionPlan {
  cycle_id: string;
  approval_id: string;
  strategy: StrategyType;
  legs: OptionLeg[];
  order_class: string;
  constraints: OrderConstraints;
  estimated_cost: number;
}

// ============================================================================
// 6. ExecutionResult Contract (BRD §23)
// ============================================================================

export interface FilledLeg {
  leg_symbol: string;
  qty: number;
  price: number;
  filled_at: string; // ISO datetime
  slippage?: number | null;
}

export interface FailedLeg {
  leg_symbol: string;
  reason: string;
}

export interface ExecutionResult {
  cycle_id: string;
  status: ExecutionStatus;
  order_ids: string[];
  broker_order_id?: string | null;
  filled_legs: FilledLeg[];
  failed_legs: FailedLeg[];
  actual_cost?: number | null;
  slippage?: number | null;
  submitted_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
}

// ============================================================================
// 7. MonitoringState Contract (BRD §24)
// ============================================================================

export interface TriggerObservation {
  trigger_type: TriggerType;
  observed_at: string; // ISO datetime
  observed_value?: number | null;
  threshold?: number | null;
  detail?: string | null;
  breached: boolean;
}

export interface MonitoringState {
  cycle_id: string;
  as_of: string; // ISO datetime
  portfolio_value?: number | null;
  drawdown?: number | null;
  volatility?: number | null;
  gross_exposure?: number | null;
  hedge_ratio?: number | null;
  target_hedge_ratio?: number | null;
  hedge_pnl?: number | null;
  time_to_expiration_days?: number | null;
  trigger_history: TriggerObservation[];
  active_triggers: TriggerType[];
  cooldown_until?: string | null;
  in_cooldown: boolean;
  reassessment_recommended: boolean;
}

// ============================================================================
// System / Health Info
// ============================================================================

export interface BuildInfo {
  sha: string;
  time: string;
  environment: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  build: BuildInfo;
}

// ============================================================================
// Agent Runs / Execution Timeline
// ============================================================================

export type AgentStatus = 'pending' | 'running' | 'completed' | 'done' | 'error' | 'failed';

export interface AgentRun {
  id: string;
  cycle_id: string;
  agent_name: string;
  status?: AgentStatus;
  inputs?: Record<string, unknown> | null;
  outputs?: Record<string, unknown> | null;
  error?: string | null;
  started_at: string; // ISO datetime
  finished_at?: string | null; // ISO datetime
  duration_ms?: number | null;
}

