import { setupServer } from 'msw/node';
import { HttpResponse, http } from 'msw';
import type {
  HedgeContext,
  StrategyHypothesis,
  StrategyDecision,
  RiskDecision,
  ExecutionPlan,
  ExecutionResult,
  MonitoringState,
  HealthResponse,
  AgentRun,
} from '../api/types';

export const STUB_HEDGE_CONTEXT: HedgeContext = {
  cycle_id: 'cyc-001',
  timestamp: '2026-09-03T14:30:00Z',
  portfolio_state: {
    total_value: 1000000.0,
    cash: 200000.0,
    equity: 800000.0,
    buying_power: 400000.0,
    positions: [
      {
        symbol: 'AAPL',
        qty: 1000.0,
        avg_price: 150.0,
        market_value: 180000.0,
        asset_class: 'EQUITY',
        side: 'BUY',
        unrealized_pl: 30000.0,
      },
    ],
    gross_exposure: 800000.0,
    net_exposure: 760000.0,
    concentration_hhi: 0.42,
    drawdown: -0.07,
    max_drawdown: -0.12,
    volatility: 0.19,
    beta: 1.1,
  },
  objective: {
    max_hedge_budget_pct: 0.05,
    drawdown_tolerance_pct: 0.1,
    target_hedge_ratio: 0.2,
    notes: 'capital preservation into year end',
  },
  market_state: {
    regime: 'RISK_OFF',
    index_trend: 'DOWN',
    vix: 24.5,
    as_of: '2026-09-03T14:00:00Z',
  },
  stock_state: [
    {
      symbol: 'AAPL',
      risk_note: 'earnings in 3 weeks; elevated single-name risk',
      momentum: -0.3,
      key_levels: [140.0, 160.0],
    },
  ],
  news_context: [
    {
      headline: 'Fed holds rates, signals caution',
      ts: '2026-09-03T12:00:00Z',
      symbols: ['SPY'],
      source: 'reuters',
      sentiment: -0.2,
      is_event: true,
    },
  ],
  option_candidates: [
    {
      underlying: 'SPY',
      right: 'PUT',
      strike: 500.0,
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
    },
  ],
  current_hedge: {
    active: false,
    legs: [],
  },
  degraded_sections: [],
  schema_version: 1,
};

export const STUB_STRATEGY_HYPOTHESIS: StrategyHypothesis = {
  cycle_id: 'cyc-001',
  strategy: 'PROTECTIVE_PUT',
  action: 'NEW_HEDGE',
  viable: true,
  legs: [
    {
      underlying: 'SPY',
      right: 'PUT',
      side: 'BUY',
      strike: 500.0,
      expiration: '2026-12-18',
      quantity: 20,
      limit_price: 8.5,
    },
  ],
  cost: 17000.0,
  hedge_metrics: {
    hedge_ratio: 0.2,
    downside_protection_pct: 0.9,
    cost_pct_of_portfolio: 0.017,
    net_delta: -700.0,
    net_gamma: 0.014,
    net_theta: 18.0,
    net_vega: -0.08,
    max_loss: 17000.0,
    breakevens: [491.5],
  },
  payoff_profile: [
    { price: 400.0, pnl: -17000.0 },
    { price: 500.0, pnl: -17000.0 },
    { price: 600.0, pnl: 83000.0 },
  ],
  liquidity: 'OK',
  risks: ['negative carry'],
  tradeoffs: ['premium drag on flat tape'],
  rationale: 'Direct downside protection within the hedge budget.',
  rejection_conditions: ['premium exceeds 2% of portfolio value'],
};

export const STUB_STRATEGY_DECISION: StrategyDecision = {
  cycle_id: 'cyc-001',
  decision: 'SELECT_STRATEGY',
  selected_strategy: 'PROTECTIVE_PUT',
  selected_hypothesis: STUB_STRATEGY_HYPOTHESIS,
  alternatives: [
    {
      cycle_id: 'cyc-001',
      strategy: 'COLLAR',
      action: 'NEW_HEDGE',
      viable: true,
      legs: [],
      cost: 0.0,
      hedge_metrics: {
        downside_protection_pct: 0.85,
        breakevens: [540.0],
      },
      payoff_profile: [],
      risks: [],
      tradeoffs: [],
      rationale: 'Synthetic downside collar funded via upside cap.',
      rejection_conditions: [],
    },
    {
      cycle_id: 'cyc-001',
      strategy: 'NO_HEDGE',
      action: 'NO_TRADE',
      viable: true,
      legs: [],
      cost: 0.0,
      hedge_metrics: {
        breakevens: [],
      },
      payoff_profile: [],
      risks: [],
      tradeoffs: [],
      rationale: 'Drawdown is inside tolerance; protection is not worth the carry.',
      rejection_conditions: [],
    },
  ],
  comparison: [
    {
      strategy: 'PROTECTIVE_PUT',
      cost: 17000.0,
      downside_protection_pct: 0.9,
      upside_giveup_pct: 0.0,
      liquidity: 'OK',
      verdict: 'SELECTED',
      score: 0.82,
    },
    {
      strategy: 'COLLAR',
      cost: 0.0,
      downside_protection_pct: 0.85,
      upside_giveup_pct: 0.08,
      liquidity: 'OK',
      verdict: 'VIABLE',
      score: 0.78,
    },
    {
      strategy: 'NO_HEDGE',
      cost: 0.0,
      downside_protection_pct: 0.0,
      verdict: 'REJECTED',
      score: 0.4,
    },
  ],
  rationale: 'Protective put gives the most protection per dollar within budget.',
  reassessment_conditions: ['drawdown recovers past -3%', 'VIX falls below 18'],
};

export const STUB_RISK_DECISION: RiskDecision = {
  cycle_id: 'cyc-001',
  verdict: 'APPROVE',
  checks: [
    { name: 'hedge_budget', category: 'COST', passed: true, observed: 0.017, limit: 0.05 },
    { name: 'max_hedge_ratio', category: 'POSITION_LIMITS', passed: true, observed: 0.2, limit: 0.35 },
    { name: 'buying_power', category: 'EXECUTION', passed: true },
  ],
  violations: [],
  warnings: ['IV is elevated vs its 30-day average'],
  modifications: [],
  rationale: 'Every deterministic check passes and the plan is inside budget.',
  approved_hypothesis: STUB_STRATEGY_HYPOTHESIS,
};

export const STUB_EXECUTION_PLAN: ExecutionPlan = {
  cycle_id: 'cyc-001',
  approval_id: 'risk-cyc-001',
  strategy: 'PUT_SPREAD',
  legs: [
    {
      underlying: 'SPY',
      right: 'PUT',
      side: 'BUY',
      strike: 500.0,
      expiration: '2026-12-18',
      quantity: 20,
      limit_price: 8.5,
    },
    {
      underlying: 'SPY',
      right: 'PUT',
      side: 'SELL',
      strike: 470.0,
      expiration: '2026-12-18',
      quantity: 20,
      limit_price: 3.2,
    },
  ],
  order_class: 'MLEG',
  constraints: {
    time_in_force: 'DAY',
    order_type: 'LIMIT',
    limit_price: 5.3,
    price_tolerance_pct: 0.05,
    allow_legging: false,
  },
  estimated_cost: 10600.0,
};

export const STUB_EXECUTION_RESULT: ExecutionResult = {
  cycle_id: 'cyc-001',
  status: 'FILLED',
  order_ids: ['abc-123'],
  broker_order_id: 'abc-123',
  filled_legs: [
    {
      leg_symbol: 'SPY261218P00500000',
      qty: 20,
      price: 8.55,
      filled_at: '2026-09-03T14:35:01Z',
      slippage: 0.05,
    },
  ],
  failed_legs: [],
  actual_cost: 10740.0,
  slippage: 0.03,
  submitted_at: '2026-09-03T14:35:00Z',
  completed_at: '2026-09-03T14:35:02Z',
};

export const STUB_MONITORING_STATE: MonitoringState = {
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
  trigger_history: [
    {
      trigger_type: 'DRAWDOWN_LIMIT',
      observed_at: '2026-09-03T14:00:00Z',
      observed_value: -0.07,
      threshold: -0.05,
      detail: 'drawdown exceeded the configured limit',
      breached: true,
    },
    {
      trigger_type: 'VOLATILITY_SPIKE',
      observed_at: '2026-09-03T14:30:00Z',
      observed_value: 0.2,
      threshold: 0.25,
      breached: false,
    },
  ],
  active_triggers: ['DRAWDOWN_LIMIT'],
  in_cooldown: false,
  reassessment_recommended: true,
};

export const STUB_AGENT_RUNS: AgentRun[] = [
  {
    id: 'run-001',
    cycle_id: 'cyc-001',
    agent_name: 'Portfolio Analysis Agent',
    status: 'completed',
    inputs: { source: 'alpaca_snapshot', positions_count: 1 },
    outputs: { total_value: 1000000.0, beta: 1.1, drawdown: -0.07 },
    started_at: '2026-09-03T14:30:00.000Z',
    finished_at: '2026-09-03T14:30:00.120Z',
    duration_ms: 120,
  },
  {
    id: 'run-002',
    cycle_id: 'cyc-001',
    agent_name: 'Stock Analysis Agent',
    status: 'completed',
    inputs: { symbols: ['AAPL'] },
    outputs: { risk_notes: 'Earnings in 3 weeks; elevated single-name risk' },
    started_at: '2026-09-03T14:30:00.130Z',
    finished_at: '2026-09-03T14:30:00.315Z',
    duration_ms: 185,
  },
  {
    id: 'run-003',
    cycle_id: 'cyc-001',
    agent_name: 'Market Regime Agent',
    status: 'completed',
    inputs: { index: 'SPY', vix: 24.5 },
    outputs: { regime: 'RISK_OFF', trend: 'DOWN' },
    started_at: '2026-09-03T14:30:00.320Z',
    finished_at: '2026-09-03T14:30:00.530Z',
    duration_ms: 210,
  },
  {
    id: 'run-004',
    cycle_id: 'cyc-001',
    agent_name: 'News Analysis Agent',
    status: 'completed',
    inputs: { feed: 'reuters' },
    outputs: { sentiment: -0.2, headline: 'Fed holds rates, signals caution' },
    started_at: '2026-09-03T14:30:00.540Z',
    finished_at: '2026-09-03T14:30:00.635Z',
    duration_ms: 95,
  },
  {
    id: 'run-005',
    cycle_id: 'cyc-001',
    agent_name: 'Options Chain Agent',
    status: 'completed',
    inputs: { underlying: 'SPY' },
    outputs: { candidate_strikes: [500.0, 470.0], iv: 0.21 },
    started_at: '2026-09-03T14:30:00.640Z',
    finished_at: '2026-09-03T14:30:00.960Z',
    duration_ms: 320,
  },
  {
    id: 'run-006',
    cycle_id: 'cyc-001',
    agent_name: 'Strategy Manager Agent',
    status: 'completed',
    inputs: { candidate_count: 4 },
    outputs: { selected: 'PROTECTIVE_PUT', verdict: 'SELECT_STRATEGY' },
    started_at: '2026-09-03T14:30:00.970Z',
    finished_at: '2026-09-03T14:30:01.420Z',
    duration_ms: 450,
  },
];

export const STUB_STRATEGY_HYPOTHESES: StrategyHypothesis[] = [
  STUB_STRATEGY_HYPOTHESIS,
  {
    cycle_id: 'cyc-001',
    strategy: 'PUT_SPREAD',
    action: 'NEW_HEDGE',
    viable: false,
    legs: [
      {
        underlying: 'SPY',
        right: 'PUT',
        side: 'BUY',
        strike: 500.0,
        expiration: '2026-12-18',
        quantity: 20,
        limit_price: 8.5,
      },
      {
        underlying: 'SPY',
        right: 'PUT',
        side: 'SELL',
        strike: 470.0,
        expiration: '2026-12-18',
        quantity: 20,
        limit_price: 3.2,
      },
    ],
    cost: 10600.0,
    hedge_metrics: {
      hedge_ratio: 0.2,
      downside_protection_pct: 0.65,
      cost_pct_of_portfolio: 0.0106,
      net_delta: -350.0,
      net_gamma: 0.008,
      net_theta: 8.0,
      net_vega: -0.04,
      max_loss: 10600.0,
      breakevens: [494.7],
    },
    payoff_profile: [
      { price: 400.0, pnl: 49400.0 },
      { price: 470.0, pnl: 49400.0 },
      { price: 500.0, pnl: -10600.0 },
      { price: 600.0, pnl: -10600.0 },
    ],
    liquidity: 'OK',
    risks: ['capped tail protection below 470 strike'],
    tradeoffs: ['lower cost but exposure resumes below lower strike'],
    rationale: 'Defined-risk put vertical spread to minimize premium outlay.',
    rejection_conditions: ['tail risk protection insufficient for target drawdown limit'],
    rejection_reason: 'Capped tail downside below $470 breaches drawdown safety threshold under high volatility regime.',
  },
  {
    cycle_id: 'cyc-001',
    strategy: 'COLLAR',
    action: 'NEW_HEDGE',
    viable: true,
    legs: [
      {
        underlying: 'SPY',
        right: 'PUT',
        side: 'BUY',
        strike: 500.0,
        expiration: '2026-12-18',
        quantity: 20,
        limit_price: 8.5,
      },
      {
        underlying: 'SPY',
        right: 'CALL',
        side: 'SELL',
        strike: 550.0,
        expiration: '2026-12-18',
        quantity: 20,
        limit_price: 8.5,
      },
    ],
    cost: 0.0,
    hedge_metrics: {
      hedge_ratio: 0.2,
      downside_protection_pct: 0.85,
      cost_pct_of_portfolio: 0.0,
      net_delta: -500.0,
      net_gamma: 0.01,
      net_theta: 0.0,
      net_vega: 0.0,
      max_loss: 0.0,
      breakevens: [500.0, 550.0],
    },
    payoff_profile: [
      { price: 400.0, pnl: 0.0 },
      { price: 500.0, pnl: 0.0 },
      { price: 550.0, pnl: 50000.0 },
      { price: 600.0, pnl: 50000.0 },
    ],
    liquidity: 'OK',
    risks: ['upside capped at call strike 550'],
    tradeoffs: ['zero net premium in exchange for upside sacrifice'],
    rationale: 'Synthetic downside collar funded via upside call sale.',
    rejection_conditions: ['portfolio upside participation requires >10% headroom'],
  },
  {
    cycle_id: 'cyc-001',
    strategy: 'NO_HEDGE',
    action: 'NO_TRADE',
    viable: false,
    legs: [],
    cost: 0.0,
    hedge_metrics: {
      hedge_ratio: 0.0,
      downside_protection_pct: 0.0,
      cost_pct_of_portfolio: 0.0,
      net_delta: 0.0,
      net_gamma: 0.0,
      net_theta: 0.0,
      net_vega: 0.0,
      max_loss: 1000000.0,
      breakevens: [],
    },
    payoff_profile: [],
    liquidity: 'OK',
    risks: ['unhedged market beta exposure'],
    tradeoffs: ['no cost outlay, 100% loss exposure on adverse moves'],
    rationale: 'Drawdown is inside tolerance; protection is not worth the carry.',
    rejection_conditions: ['market regime is RISK_OFF and drawdown exceeds tolerance'],
    rejection_reason: 'Current portfolio drawdown (-7.0%) and elevated VIX (24.5) violate no-hedge parameters.',
  },
];

export const STUB_HEALTH: HealthResponse = {
  status: 'healthy',
  version: '0.1.0',
  build: {
    sha: '9c5f83b',
    time: '2026-09-03T00:00:00Z',
    environment: 'development',
  },
};

export const handlers = [
  http.get('*/health', () => {
    return HttpResponse.json(STUB_HEALTH);
  }),
  http.get('*/context', () => {
    return HttpResponse.json(STUB_HEDGE_CONTEXT);
  }),
  http.get('*/portfolio/latest', () => {
    return HttpResponse.json(STUB_HEDGE_CONTEXT.portfolio_state);
  }),
  http.get('*/agent-runs', () => {
    return HttpResponse.json(STUB_AGENT_RUNS);
  }),
  http.get('*/strategy/hypotheses', () => {
    return HttpResponse.json(STUB_STRATEGY_HYPOTHESES);
  }),
  http.get('*/strategy/hypotheses/:id', () => {
    return HttpResponse.json(STUB_STRATEGY_HYPOTHESIS);
  }),
  http.get('*/strategy/hypothesis', () => {
    return HttpResponse.json(STUB_STRATEGY_HYPOTHESIS);
  }),
  http.get('*/strategy/decision', () => {
    return HttpResponse.json(STUB_STRATEGY_DECISION);
  }),
  http.get('*/strategy', () => {
    return HttpResponse.json(STUB_STRATEGY_DECISION);
  }),
  http.get('*/risk', () => {
    return HttpResponse.json(STUB_RISK_DECISION);
  }),
  http.get('*/execution/plan', () => {
    return HttpResponse.json(STUB_EXECUTION_PLAN);
  }),
  http.get('*/execution', () => {
    return HttpResponse.json(STUB_EXECUTION_RESULT);
  }),
  http.get('*/monitoring', () => {
    return HttpResponse.json(STUB_MONITORING_STATE);
  }),
];

export const server = setupServer(...handlers);

