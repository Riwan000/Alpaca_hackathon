# Autonomous Adaptive Portfolio Hedge Agent
## Technology Stack & Technical Architecture

### Version 1.0 — Hackathon MVP

---

# 1. Architecture Overview

The system is a multi-agent application built around a stateful orchestration layer.

```text
                         FRONTEND
                     React + TypeScript
                              │
                              ↓
                         FastAPI API
                              │
                              ↓
                        ORCHESTRATOR
                         LangGraph
                               │
          ┌───────────────────┼───────────────────┐
          ↓                   ↓                   ↓
     Portfolio Agent      Market Agent        News Agent
          │                   │                   │
          └───────────────────┼───────────────────┘
                              ↓
                       Stock Analysis Agent
                              ↓
                       Options Analysis Agent
                              ↓
                         HedgeContext
                              ↓
                    Strategy Manager
                              │
              ┌───────────────┼───────────────┐
              ↓               ↓               ↓
       Protective Put    Put Spread          Collar
              │               │               │
              └───────────────┼───────────────┘
                              ↓
                         No-Hedge Agent
                              ↓
                         Risk Agent
                              ↓
                      Execution Agent
                              ↓
                          Alpaca MCP
                              ↓
                       Alpaca Trading
                              ↓
                         Monitoring
                              ↓
                       State / Database
                              ↺
```

---

# 2. Frontend

## React

Used for the primary application interface.

Responsibilities:

- Portfolio dashboard
- Risk visualization
- Hedge status
- Strategy comparison
- Agent activity
- Trade history
- P&L
- Configuration

## TypeScript

Used for:

- Typed frontend state
- API contracts
- Component interfaces
- Reliable handling of agent outputs

---

# 3. Backend

## Python

Primary backend and agent implementation language.

Used for:

- Agent logic
- Quantitative calculations
- Risk calculations
- Options calculations
- Portfolio analysis
- Strategy evaluation
- Orchestration integration
- Alpaca integration

## FastAPI

Provides the application API layer.

Responsibilities:

- Frontend API
- Portfolio endpoints
- Agent status endpoints
- Strategy endpoints
- Risk endpoints
- Execution status
- Monitoring state
- P&L data
- Configuration

Conceptually:

```text
React
  ↓
FastAPI
  ↓
Application / Orchestrator
  ↓
Agents + Tools + Database
```

---

# 4. Agent Orchestration

## LangGraph

Used for stateful multi-agent orchestration.

Responsibilities:

- Workflow state
- Agent routing
- Delegation
- Conditional transitions
- Retries
- Error handling
- Strategy → Risk → Execution workflow
- Monitoring → Reassessment loop

The orchestrator should own workflow state rather than allowing agents to directly control the entire workflow.

Conceptually:

```text
                  ORCHESTRATOR
                       │
          ┌────────────┼────────────┐
          ↓            ↓            ↓
        Agent        Agent        Agent
          │            │            │
          └────────────┼────────────┘
                       ↓
                  Next State
```

---

# 5. AI / LLM Layer

The system uses a modular, provider-agnostic LLM interface supporting OpenAI-compatible completion endpoints:

## OpenRouter (Development & Active Testing)

Used during development, unit testing, and iterative refinement.

- High model flexibility (Claude 3.5 Sonnet, GPT-4o, Llama 3, DeepSeek, etc.)
- Fast iteration and cost-effective development testing

## Featherless AI (Final Evaluation & Submission Benchmark)

Used as the target model infrastructure for final submission, end-to-end verification, and judge evaluation.

- Serverless inference on open-weight models for autonomous reasoning
- Verified and benchmarked prior to final submission

## Unified Provider Abstraction

Both providers adhere to standard OpenAI-compatible API schemas (`base_url`, `api_key`, `model`). Swapping providers requires only an environment configuration toggle (`LLM_PROVIDER=openrouter` vs `LLM_PROVIDER=featherless`).

LLMs are primarily responsible for:

- Contextual reasoning
- Market-regime interpretation
- Strategy thesis generation
- Qualitative trade-off analysis
- Decision explanation
- Agent communication

LLMs should not independently perform critical financial calculations or bypass deterministic controls.

---

# 6. Deterministic Quantitative Layer

A dedicated deterministic layer should handle calculations that need to be reliable and reproducible.

Responsibilities:

- Portfolio value
- Position exposure
- Concentration
- Drawdown
- High-water mark
- Portfolio volatility
- Beta
- Correlation
- Hedge ratio
- Option Greeks
- Premium
- Payoff calculations
- Maximum loss
- Hedge cost
- Liquidity checks
- Position sizing
- Risk limits

Architecture principle:

```text
LLM
 ↓
Reason about calculated facts

Deterministic Engine
 ↓
Calculate the facts
```

The LLM should not replace the quantitative engine.

---

# 7. Trading Infrastructure

## Alpaca Trading API

Primary trading infrastructure for the hackathon paper-trading environment.

Used for:

- Account information
- Portfolio positions
- Market/trading state
- Order submission
- Order status
- Position updates
- Trade history

---

# 8. Alpaca MCP

Used as the tool interface between the agentic application and Alpaca capabilities.

Conceptually:

```text
Agent
  ↓
MCP Client
  ↓
Alpaca MCP
  ↓
Alpaca Trading Infrastructure
```

Potential capabilities include:

- Portfolio retrieval
- Position retrieval
- Market data access
- Options data access
- Order placement
- Order monitoring
- Order cancellation

The exact Alpaca MCP tool names and schemas should be determined from the actual MCP implementation.

---

# 9. Alpaca CLI

The Alpaca CLI can be used where useful for:

- Development
- Account inspection
- Testing
- Debugging
- Operational workflows

It complements the application/API/MCP architecture rather than replacing the application layer.

---

# 10. Options Data Layer

The Options Analysis Agent needs access to option-chain information.

Important fields include:

```text
Underlying
Strike
Expiration
DTE
Bid
Ask
Mid
Volume
Open Interest
Implied Volatility
Delta
Gamma
Theta
Vega
```

The system should transform raw option-chain data into structured candidates for the Strategy Agents.

```text
Raw Option Chain
       ↓
Options Analysis
       ↓
Candidate Contracts
       ↓
Strategy Agents
```

---

# 11. Market Data Layer

The system needs market information for:

- Portfolio assets
- Relevant benchmarks
- Market volatility
- Sector conditions
- Market regime
- Price trends
- Correlations

The exact data providers should remain implementation-configurable.

---

# 12. News Data Layer

The News Agent requires relevant market/company news.

The system should prioritize:

- Portfolio-relevant events
- Earnings
- Regulatory events
- Macro events
- Major company announcements
- Market-moving events

Rather than passing all available news to the LLM:

```text
News Sources
    ↓
Filtering / Relevance
    ↓
Relevant Events
    ↓
News Agent
```

---

# 13. Database

## PostgreSQL / Supabase

Used for persistent state.

### Portfolio data

- Portfolio snapshots
- Holdings
- Exposure
- Risk metrics

### Agent data

- Agent runs
- Agent outputs
- Agent errors
- Execution state

### Strategy data

- Strategy hypotheses
- Strategy decisions
- Rejected strategies
- Decision rationale

### Risk data

- Risk checks
- Approvals
- Rejections
- Modifications

### Execution data

- Orders
- Fills
- Slippage
- Execution failures

### Monitoring data

- Trigger events
- Reassessment events
- Hedge changes
- Monitoring state

### Performance data

- Portfolio P&L
- Hedge P&L
- Net P&L
- Drawdown
- Hedge cost
- Benchmark performance

---

# 14. Core Data Contracts

The system should use structured objects between agents.

## HedgeContext

```text
HedgeContext
├── portfolio_state
├── market_state
├── stock_state
├── news_context
├── option_candidates
├── current_hedge
├── user/project_objective
└── timestamp
```

## StrategyHypothesis

```text
StrategyHypothesis
├── strategy
├── action
├── viable
├── legs[]
├── cost
├── hedge_metrics
├── payoff_profile
├── liquidity
├── risks
├── tradeoffs
├── rationale
└── rejection_conditions
```

## StrategyDecision

```text
StrategyDecision
├── decision
├── selected_strategy
├── selected_hypothesis
├── alternatives
├── comparison
├── rationale
└── reassessment_conditions
```

## RiskDecision

```text
RiskDecision
├── decision
├── checks[]
├── violations[]
├── warnings[]
├── modifications[]
├── risk_metrics
└── rationale
```

## ExecutionPlan

```text
ExecutionPlan
├── approval_id
├── strategy
├── legs[]
├── quantities
├── execution_constraints
└── expiry
```

## ExecutionResult

```text
ExecutionResult
├── status
├── order_ids
├── filled_legs
├── failed_legs
├── actual_cost
├── slippage
├── timestamps
└── error
```

## MonitoringState

```text
MonitoringState
├── last_analysis
├── last_trade
├── current_hedge
├── target_hedge
├── drawdown
├── volatility_regime
├── hedge_expiration
├── cooldown_until
├── trigger_history[]
└── monitoring_status
```

---

# 15. Strategy Architecture

The MVP contains four Strategy Agents:

```text
                    STRATEGY MANAGER
                           │
        ┌──────────────────┼──────────────────┐
        ↓                  ↓                  ↓
 Protective Put        Put Spread           Collar
        │                  │                  │
        └──────────────────┼──────────────────┘
                           ↓
                      No-Hedge Agent
                           ↓
                    Strategy Decision
```

Each Strategy Agent produces the same `StrategyHypothesis` structure.

This allows the Strategy Manager to compare fundamentally different approaches using a common interface.

---

# 16. Risk Architecture

The Risk Agent sits between strategy selection and execution.

```text
Strategy Manager
       ↓
StrategyDecision
       ↓
Risk Engine
       +
Risk Agent
       ↓
APPROVE / MODIFY / REJECT
       ↓
Execution
```

Deterministic risk checks should include:

- Hedge budget
- Position limits
- Maximum hedge ratio
- Maximum notional
- Buying power
- Liquidity
- Contract validity
- Expiration
- Greeks
- Multi-leg consistency
- Execution tolerance

---

# 17. Execution Architecture

```text
StrategyDecision
       ↓
RiskDecision
       ↓
ExecutionPlan
       ↓
Pre-flight validation
       ↓
Alpaca MCP
       ↓
Order
       ↓
Execution monitoring
       ↓
ExecutionResult
```

The Execution Agent must not:

- Invent a new strategy
- Modify an approved strategy silently
- Execute without Risk approval

---

# 18. Monitoring Architecture

Monitoring should use two levels.

## Level 1 — Lightweight Monitoring

Deterministic checks:

- Drawdown
- Hedge drift
- Volatility
- Exposure
- Expiration
- Major state changes

## Level 2 — Intelligent Reassessment

Triggered only when a meaningful event occurs.

```text
Light Monitoring
       ↓
Meaningful Change?
       ↓
      YES
       ↓
Orchestrator
       ↓
Analysis Agents
       ↓
Strategy Layer
       ↓
Risk
       ↓
Execution
```

This reduces unnecessary LLM calls and overtrading.

---

# 19. Frontend Architecture

Suggested component structure:

```text
App
├── Dashboard
│   ├── PortfolioOverview
│   ├── RiskOverview
│   ├── HedgeStatus
│   ├── Recommendation
│   ├── StrategyComparison
│   ├── AgentActivity
│   ├── TradeHistory
│   └── Performance
│
├── Configuration
│   ├── RiskPreferences
│   ├── HedgePreferences
│   └── AutonomySettings
│
└── StrategyDetails
    ├── PayoffChart
    ├── Greeks
    ├── Cost
    ├── Protection
    └── Tradeoffs
```

---

# 20. Backend Architecture

Suggested logical modules:

```text
backend/
├── api/
├── agents/
│   ├── orchestrator/
│   ├── portfolio/
│   ├── stock/
│   ├── market/
│   ├── news/
│   ├── options/
│   ├── strategies/
│   ├── risk/
│   ├── execution/
│   └── monitoring/
│
├── quant/
│   ├── portfolio/
│   ├── risk/
│   ├── options/
│   ├── greeks/
│   └── payoff/
│
├── integrations/
│   ├── alpaca/
│   ├── market_data/
│   └── news/
│
├── state/
├── models/
├── services/
└── config/
```

The exact repository structure can change during implementation.

---

# 21. State Management

The orchestration layer should maintain state across the workflow.

Example:

```text
INITIAL
   ↓
ANALYZING
   ↓
STRATEGY_EVALUATION
   ↓
RISK_CHECK
   ↓
EXECUTION
   ↓
MONITORING
   ↓
TRIGGER
   ↓
REASSESSMENT
   ↺
```

The system should persist important state so that a restart does not lose the portfolio's decision history.

---

# 22. Observability

The system should log:

- Agent invocation
- Agent input summary
- Agent output
- Decision
- Tool call
- Risk check
- Order
- Fill
- Error
- Reassessment trigger

Every trade should be traceable:

```text
Trade
 ↓
Risk Approval
 ↓
Strategy Decision
 ↓
Strategy Hypotheses
 ↓
Analysis Context
 ↓
Trigger
```

This creates an auditable decision trail.

---

# 23. Testing Architecture

Testing should happen at multiple levels.

## Unit tests

For deterministic calculations:

- Drawdown
- Beta
- Volatility
- Greeks
- Hedge ratio
- Payoff
- Position sizing
- Risk limits

## Agent tests

Test whether each agent:

- follows its role
- returns the correct schema
- handles missing information
- rejects invalid proposals

## Workflow tests

Test:

```text
Analysis
→ Strategy
→ Risk
→ Execution
→ Monitoring
```

## Trading tests

Use Alpaca paper trading to test:

- Order submission
- Multi-leg execution
- Partial fills
- Failed orders
- Cancellation
- State synchronization

---

# 24. Deployment

## Frontend

Potential deployment:

- Vercel or equivalent

## Backend

Potential deployment:

- Railway
- Render
- Cloud VM
- Equivalent containerized environment

## Database

- Supabase PostgreSQL

## Trading

- Alpaca paper trading

The final deployment platform can be chosen based on reliability, cost, and hackathon requirements.

---

# 25. Security

The system should:

- Keep Alpaca credentials server-side
- Never expose secrets to the frontend
- Use environment variables/secrets management
- Validate tool inputs
- Enforce risk limits server-side
- Log execution actions
- Separate read and trade permissions where possible
- Never allow frontend requests to bypass Risk Agent validation

---

# 26. Hackathon-Specific Technical Priorities

The implementation should prioritize:

### Priority 1 — Alpaca Integration

Reliable:

```text
Portfolio → Options → Orders → Fills → P&L
```

### Priority 2 — Autonomous Loop

```text
Observe
→ Reason
→ Decide
→ Risk
→ Execute
→ Monitor
→ Adapt
```

### Priority 3 — Agent Explainability

Every important decision should have:

- Reason
- Evidence
- Alternatives
- Risk checks
- Action

### Priority 4 — Trading Performance

Track:

- P&L
- Drawdown
- Hedge cost
- Hedge effectiveness
- Benchmark comparison

### Priority 5 — Presentation

Make the agent's behavior visible in the dashboard.

---

# 27. Core Technical Principle

The architecture should follow:

```text
                    LLM
                     │
              REASON / EXPLAIN
                     │
                     ↓
              AGENT WORKFLOW
                     │
              ┌──────┴──────┐
              ↓             ↓
            TOOLS       QUANT ENGINE
              │             │
              └──────┬──────┘
                     ↓
                RISK ENGINE
                     ↓
                 ALPACA
                     ↓
                 TRADING
                     ↓
               MONITORING
                     ↺
```

The system is therefore **agentic without making the LLM the source of truth for critical financial calculations or safety constraints**.
