/**
 * Type-level tests for Agent-State contracts — Task P1-FE-6 (Git Issue #40).
 *
 * Verifies that the TypeScript definitions conform to the contract shapes
 * and that `tsc --noEmit` and Vitest typecheck exit 0.
 */

import { describe, it, assertType } from 'vitest';
import type {
  HedgeContext,
  StrategyHypothesis,
  StrategyDecision,
  RiskDecision,
  ExecutionPlan,
  ExecutionResult,
  MonitoringState,
  TriggerObservation,
  OptionLeg,
  HealthResponse,
  BuildInfo,
  PortfolioState,
  PortfolioPosition,
  MarketState,
  StockView,
  NewsItem,
  OptionCandidate,
  CurrentHedge,
  HedgeObjective,
  HedgeMetrics,
  PayoffPoint,
  ComparisonRow,
  RiskCheck,
  RiskModification,
  OrderConstraints,
  FilledLeg,
  FailedLeg,
} from './types';
import {
  StrategyType,
  HedgeAction,
  DecisionType,
  RiskVerdict,
  OrderStatus,
  ExecutionStatus,
  TriggerType,
  OptionRight,
  OrderSide,
  AssetClass,
} from './types';

describe('Contracts Type Definitions (P1-FE-6)', () => {
  it('verifies Enum values and constants', () => {
    assertType<StrategyType>(StrategyType.PROTECTIVE_PUT);
    assertType<StrategyType>(StrategyType.COLLAR);
    assertType<HedgeAction>(HedgeAction.NEW_HEDGE);
    assertType<DecisionType>(DecisionType.SELECT_STRATEGY);
    assertType<RiskVerdict>(RiskVerdict.APPROVE);
    assertType<OrderStatus>(OrderStatus.FILLED);
    assertType<ExecutionStatus>(ExecutionStatus.FILLED);
    assertType<TriggerType>(TriggerType.PORTFOLIO_DELTA);
    assertType<OptionRight>(OptionRight.CALL);
    assertType<OrderSide>(OrderSide.BUY);
    assertType<AssetClass>(AssetClass.EQUITY);
  });

  it('validates HedgeContext structure (Contract 1)', () => {
    const pos: PortfolioPosition = {
      symbol: 'AAPL',
      qty: 1000,
      avg_price: 150,
      market_value: 180000,
      asset_class: 'EQUITY',
      side: 'BUY',
      unrealized_pl: 30000,
    };

    const portState: PortfolioState = {
      total_value: 1000000,
      cash: 200000,
      equity: 800000,
      buying_power: 400000,
      positions: [pos],
      gross_exposure: 800000,
      net_exposure: 760000,
      concentration_hhi: 0.42,
      drawdown: -0.07,
      max_drawdown: -0.12,
      volatility: 0.19,
      beta: 1.1,
    };

    const obj: HedgeObjective = {
      max_hedge_budget_pct: 0.05,
      drawdown_tolerance_pct: 0.1,
      target_hedge_ratio: 0.2,
      notes: 'test note',
    };

    const mkt: MarketState = {
      regime: 'RISK_OFF',
      index_trend: 'DOWN',
      vix: 24.5,
      as_of: '2026-09-03T14:00:00Z',
    };

    const stock: StockView = {
      symbol: 'AAPL',
      risk_note: 'elevated single-name risk',
      momentum: -0.3,
      key_levels: [140.0, 160.0],
    };

    const news: NewsItem = {
      headline: 'Fed holds rates',
      ts: '2026-09-03T12:00:00Z',
      symbols: ['SPY'],
      source: 'reuters',
      sentiment: -0.2,
      is_event: true,
    };

    const cand: OptionCandidate = {
      underlying: 'SPY',
      right: 'PUT',
      strike: 500,
      expiration: '2026-12-18',
      premium: 8.5,
      bid: 8.4,
      ask: 8.6,
      volume: 1200,
      open_interest: 5000,
      iv: 0.21,
      delta: -0.35,
      gamma: 0.01,
      theta: -0.04,
      vega: 0.9,
      liquidity: 'OK',
    };

    const currHedge: CurrentHedge = {
      active: false,
      legs: [],
    };

    const context: HedgeContext = {
      cycle_id: 'cyc-001',
      timestamp: '2026-09-03T14:30:00Z',
      portfolio_state: portState,
      objective: obj,
      market_state: mkt,
      stock_state: [stock],
      news_context: [news],
      option_candidates: [cand],
      current_hedge: currHedge,
      degraded_sections: [],
      schema_version: 1,
    };

    assertType<HedgeContext>(context);
  });

  it('validates StrategyHypothesis structure (Contract 2)', () => {
    const leg: OptionLeg = {
      underlying: 'SPY',
      right: 'PUT',
      side: 'BUY',
      strike: 500.0,
      expiration: '2026-12-18',
      quantity: 20,
      limit_price: 8.5,
    };

    const metrics: HedgeMetrics = {
      hedge_ratio: 0.2,
      downside_protection_pct: 0.9,
      cost_pct_of_portfolio: 0.017,
      net_delta: -700.0,
      max_loss: 17000.0,
      breakevens: [491.5],
    };

    const payoff: PayoffPoint = { price: 500.0, pnl: -17000.0 };

    const hypothesis: StrategyHypothesis = {
      cycle_id: 'cyc-001',
      strategy: 'PROTECTIVE_PUT',
      action: 'NEW_HEDGE',
      viable: true,
      legs: [leg],
      cost: 17000.0,
      hedge_metrics: metrics,
      payoff_profile: [payoff],
      liquidity: 'OK',
      risks: ['negative carry'],
      tradeoffs: ['drag on flat tape'],
      rationale: 'Direct downside protection',
      rejection_conditions: [],
    };

    assertType<StrategyHypothesis>(hypothesis);
  });

  it('validates StrategyDecision structure (Contract 3)', () => {
    const row: ComparisonRow = {
      strategy: 'PROTECTIVE_PUT',
      cost: 17000.0,
      downside_protection_pct: 0.9,
      verdict: 'SELECTED',
      score: 0.82,
    };

    const decision: StrategyDecision = {
      cycle_id: 'cyc-001',
      decision: 'SELECT_STRATEGY',
      selected_strategy: 'PROTECTIVE_PUT',
      selected_hypothesis: null,
      alternatives: [],
      comparison: [row],
      rationale: 'Best protection per dollar',
      reassessment_conditions: ['drawdown recovers'],
    };

    assertType<StrategyDecision>(decision);
  });

  it('validates RiskDecision structure (Contract 4)', () => {
    const check: RiskCheck = {
      name: 'hedge_budget',
      category: 'COST',
      passed: true,
      observed: 0.017,
      limit: 0.05,
    };

    const mod: RiskModification = {
      field: 'strike',
      from_value: 500,
      to_value: 495,
      reason: 'budget optimization',
    };

    const decision: RiskDecision = {
      cycle_id: 'cyc-001',
      verdict: 'APPROVE',
      checks: [check],
      violations: [],
      warnings: ['IV elevated'],
      modifications: [mod],
      rationale: 'All checks passed',
      approved_hypothesis: null,
    };

    assertType<RiskDecision>(decision);
  });

  it('validates ExecutionPlan structure (Contract 5)', () => {
    const leg: OptionLeg = {
      underlying: 'SPY',
      right: 'PUT',
      side: 'BUY',
      strike: 500.0,
      expiration: '2026-12-18',
      quantity: 20,
    };

    const constraints: OrderConstraints = {
      time_in_force: 'DAY',
      order_type: 'LIMIT',
      limit_price: 5.3,
      price_tolerance_pct: 0.05,
      allow_legging: false,
    };

    const plan: ExecutionPlan = {
      cycle_id: 'cyc-001',
      approval_id: 'risk-cyc-001',
      strategy: 'PUT_SPREAD',
      legs: [leg],
      order_class: 'MLEG',
      constraints,
      estimated_cost: 10600.0,
    };

    assertType<ExecutionPlan>(plan);
  });

  it('validates ExecutionResult structure (Contract 6)', () => {
    const filled: FilledLeg = {
      leg_symbol: 'SPY261218P00500000',
      qty: 20,
      price: 8.55,
      filled_at: '2026-09-03T14:35:01Z',
      slippage: 0.05,
    };

    const failed: FailedLeg = {
      leg_symbol: 'SPY261218P00470000',
      reason: 'No liquidity at limit price',
    };

    const result: ExecutionResult = {
      cycle_id: 'cyc-001',
      status: 'FILLED',
      order_ids: ['abc-123'],
      broker_order_id: 'abc-123',
      filled_legs: [filled],
      failed_legs: [failed],
      actual_cost: 10740.0,
      slippage: 0.03,
      submitted_at: '2026-09-03T14:35:00Z',
      completed_at: '2026-09-03T14:35:02Z',
    };

    assertType<ExecutionResult>(result);
  });

  it('validates MonitoringState structure (Contract 7)', () => {
    const obs: TriggerObservation = {
      trigger_type: 'DRAWDOWN_LIMIT',
      observed_at: '2026-09-03T14:00:00Z',
      observed_value: -0.07,
      threshold: -0.05,
      detail: 'drawdown exceeded limit',
      breached: true,
    };

    const state: MonitoringState = {
      cycle_id: 'cyc-001',
      as_of: '2026-09-03T15:00:00Z',
      portfolio_value: 995000.0,
      drawdown: -0.065,
      volatility: 0.2,
      gross_exposure: 800000.0,
      hedge_ratio: 0.19,
      target_hedge_ratio: 0.2,
      hedge_pnl: 1200.0,
      time_to_expiration_days: 88.5,
      trigger_history: [obs],
      active_triggers: ['DRAWDOWN_LIMIT'],
      in_cooldown: false,
      reassessment_recommended: true,
    };

    assertType<MonitoringState>(state);
  });

  it('validates HealthResponse and BuildInfo structure', () => {
    const build: BuildInfo = {
      sha: 'abcd123',
      time: '2026-09-03T00:00:00Z',
      environment: 'development',
    };

    const health: HealthResponse = {
      status: 'healthy',
      version: '0.1.0',
      build,
    };

    assertType<HealthResponse>(health);
  });
});
