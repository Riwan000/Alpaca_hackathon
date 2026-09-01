# Business Requirements Document
## Autonomous Adaptive Portfolio Hedge Agent

### Version 1.0 — Hackathon MVP

---

## 1. Product Overview

### Product Name

**Autonomous Adaptive Portfolio Hedge Agent**

### One-line description

> An autonomous multi-agent system that continuously analyzes a portfolio's risk, evaluates multiple options-based hedging strategies, selects the best-fit protection, executes approved trades through Alpaca, and dynamically rebalances the hedge as market conditions change.

The system combines **drawdown defense** and **adaptive hedge rebalancing** into a closed-loop portfolio protection system.

---

# 2. Problem

Traditional portfolio hedging is generally:

- manually managed
- static
- expensive to maintain
- difficult to adjust quickly
- dependent on predefined rules

A simple rule such as:

> "If the portfolio falls 10%, buy puts."

doesn't consider:

- why the portfolio is falling
- volatility regime
- option pricing
- hedge cost
- portfolio exposure
- liquidity
- alternative hedge structures
- whether the existing hedge is still appropriate

The product aims to solve this by continuously evaluating the portfolio and dynamically selecting an appropriate hedge.

---

# 3. Product Objective

The system should continuously answer five questions:

1. **What risks currently exist in the portfolio?**
2. **How much protection is currently required?**
3. **Which available options-based strategies can provide that protection?**
4. **Which strategy offers the best protection/cost/portfolio-fit trade-off?**
5. **Should the current hedge be increased, reduced, replaced, rolled, or removed?**

The objective is **not market prediction**.

The objective is **adaptive risk management**.

---

# 4. Hackathon Objective

The system should demonstrate a complete autonomous trading loop:

```text
Portfolio
   ↓
Risk Detection
   ↓
Market / Stock / News Analysis
   ↓
Options Analysis
   ↓
Multiple Strategy Hypotheses
   ↓
Strategy Selection
   ↓
Risk Validation
   ↓
Alpaca Execution
   ↓
Monitoring
   ↓
Portfolio Changes
   ↓
Reassessment
   ↺
```

The hackathon particularly evaluates:

- P&L performance
- Alpaca technology implementation
- creativity/originality
- presentation and execution

Therefore, the MVP should prioritize **actual paper-trading behavior, autonomous adaptation, explainability, and reliable Alpaca integration**.

---

# 5. Product Scope

## In Scope

- Alpaca paper-trading portfolio
- Portfolio risk analysis
- Stock analysis
- Market analysis
- Relevant news analysis
- Options-chain analysis
- Options strategy generation
- Strategy Manager
- Risk Agent
- Execution Agent
- Alpaca MCP integration
- Monitoring
- Hedge rebalancing
- Trade history
- P&L tracking
- Agent activity visualization
- Strategy reasoning/explanation

## Out of Scope for MVP

- Multi-user SaaS authentication
- User account creation
- User-specific Alpaca API onboarding
- User-specific Alpaca API onboarding
- Payments
- Production brokerage management
- Advanced institutional derivatives
- High-frequency trading
- Complex tax optimization

The hackathon submission uses a **dedicated Alpaca paper-trading account**, so the primary experience should open directly into the project portfolio rather than forcing judges through onboarding.

---

# 6. User Experience

## Primary User

For the hackathon:

> **Judge / evaluator viewing and interacting with the project portfolio.**

The system should also be architected so that it can later become a multi-user product.

---

# 7. Initial Experience

When the application opens:

```text
Project Alpaca Account
        ↓
Load Portfolio
        ↓
Calculate Initial Risk
        ↓
Run Initial Analysis
        ↓
Generate Hedge Recommendation
        ↓
Dashboard
```

There should be **no mandatory signup flow** in the MVP.

---

# 8. Dashboard

The dashboard should answer:

> **"What is happening to my portfolio, what hedge do I have, and what is the agent doing about it?"**

### Primary dashboard sections

#### Portfolio

- Total portfolio value
- Cash
- Holdings
- Concentration
- Portfolio performance
- Drawdown

#### Risk

- Current risk level
- Current drawdown
- Portfolio volatility
- Portfolio beta
- Current hedge ratio
- Target hedge ratio

#### Hedge

- Current strategy
- Hedge cost
- Protection level
- Hedge P&L
- Expiration
- Hedge effectiveness

#### Recommendation

```text
Current Risk: HIGH

Current Hedge: 15%
Target Hedge: 30%

Recommendation:
INCREASE HEDGE

Selected Strategy:
PUT SPREAD
```

#### Agent Activity

Show a live/chronological view:

```text
✓ Portfolio Agent analyzed exposure
✓ Market Agent detected volatility increase
✓ News Agent found relevant event
✓ Options Agent refreshed candidates
✓ Strategy Agents generated hypotheses
✓ Strategy Manager selected Put Spread
✓ Risk Agent approved
✓ Execution Agent submitted order
✓ Order filled
```

The judge should be able to see:

> **What happened → what the agents concluded → what they did → why.**

This is a central presentation feature of the project.

---

# 9. System Architecture

```text
                         USER / JUDGE
                              │
                              ↓
                         DASHBOARD
                              │
                              ↓
                        ORCHESTRATOR
                              │
             ┌────────────────┼────────────────┐
             ↓                ↓                ↓
        PORTFOLIO           MARKET            NEWS
          AGENT              AGENT            AGENT
             └────────────────┼────────────────┘
                              ↓
                         STOCK AGENT
                              ↓
                        OPTIONS AGENT
                              ↓
                         HEDGE CONTEXT
                              ↓
                  ┌────────────────────────┐
                  │    STRATEGY LAYER     │
                  │                        │
                  │ Protective Put         │
                  │ Put Spread             │
                  │ Collar                 │
                  │ No-Hedge               │
                  │                        │
                  │ Strategy Manager       │
                  └───────────┬────────────┘
                              ↓
                         RISK AGENT
                              ↓
                      EXECUTION AGENT
                              ↓
                          ALPACA MCP
                              ↓
                           TRADE
                              ↓
                         MONITORING
                              ↓
                         ORCHESTRATOR
                              ↺
```

---

# 10. Core Architecture Principle

The system follows:

> **Agents reason. Tools provide. Deterministic code enforces.**

LLMs should not independently perform high-stakes financial calculations.

Deterministic systems should calculate:

- drawdown
- volatility
- beta
- exposure
- hedge ratio
- option Greeks
- premium
- payoff
- maximum loss
- liquidity
- position size
- risk limits

The LLM should primarily handle:

- contextual interpretation
- market-regime reasoning
- strategy thesis generation
- qualitative trade-offs
- explanation

This separation is explicitly supported by the project research.

---

# 11. Orchestrator

The Orchestrator is the central workflow controller.

### Responsibilities

- Maintain workflow state
- Determine which agents need to run
- Delegate analysis
- Manage dependencies
- Collect agent results
- Construct `HedgeContext`
- Trigger Strategy Manager
- Trigger Risk Agent
- Trigger Execution Agent
- Handle failures
- Trigger reassessment
- Maintain the feedback loop

Agents should **not directly control the entire workflow**.

---

# 12. Analysis Agents

## Portfolio Management Agent

Answers:

> **"What do we own and what is our current portfolio risk?"**

Analyzes:

- holdings
- portfolio value
- exposure
- concentration
- beta
- volatility
- drawdown
- existing hedge

---

## Stock Analysis Agent

Answers:

> **"What is happening with the assets in the portfolio?"**

Analyzes:

- price trends
- momentum
- volatility
- stock-specific risk
- portfolio contribution
- correlations

---

## Market Analysis Agent

Answers:

> **"What is happening in the broader market?"**

Analyzes:

- market trend
- volatility regime
- market risk
- sector conditions
- relevant macro conditions

---

## News Agent

Answers:

> **"Has anything happened that could materially change portfolio risk?"**

It prioritizes relevant events instead of simply collecting headlines.

Examples:

- earnings
- regulatory events
- macroeconomic releases
- major company announcements
- market shocks

---

# 13. Options Analysis Agent

Answers:

> **"What options are currently available for constructing a hedge?"**

It analyzes:

- strike
- expiration
- premium
- bid/ask
- volume
- open interest
- IV
- delta
- gamma
- theta
- vega
- liquidity

The Options Agent provides **candidate contracts/building blocks**.

It does not select the final strategy.

---

# 14. HedgeContext

All downstream strategy decisions operate from a standardized context.

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

The system should avoid passing unnecessary raw information into every LLM prompt.

A context builder should provide each agent with the information relevant to its task.

This addresses the research concern around context dilution.

---

# 15. Strategy Layer

The MVP contains four Strategy Agents.

## 15.1 Protective Put Agent

Philosophy:

> **Pay premium for direct downside protection.**

Structure:

```text
BUY PUT
```

Key characteristics:

- strong downside protection
- unlimited upside
- higher premium cost
- positive convexity
- negative theta/carry

The agent evaluates whether direct protection justifies the premium.

---

## 15.2 Put Spread Agent

Philosophy:

> **Reduce hedge cost by limiting downside protection.**

Structure:

```text
BUY HIGHER-STRIKE PUT
+
SELL LOWER-STRIKE PUT
```

Key characteristics:

- lower cost
- bounded protection
- unlimited upside
- defined protection corridor

---

## 15.3 Collar Agent

Philosophy:

> **Reduce hedge cost by sacrificing some upside.**

Structure:

```text
BUY PUT
+
SELL CALL
```

Key characteristics:

- downside protection
- reduced premium cost
- upside capped by short call
- potentially attractive when protection is expensive

---

## 15.4 No-Hedge Agent

Philosophy:

> **Don't pay for protection when the risk/cost trade-off does not justify it.**

The agent evaluates whether:

```text
Cost of protection
>
Benefit of additional protection
```

and can propose:

```text
NO_TRADE
MAINTAIN
REMOVE
```

This prevents the system from developing a bias toward constantly trading.

---

# 16. Strategy Agent Contract

Each Strategy Agent produces a standardized:

`StrategyHypothesis`

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

The strategy agent may return:

```text
VIABLE
```

or:

```text
NOT_VIABLE
```

A Strategy Agent must be allowed to reject its own strategy family if no acceptable implementation exists.

---

# 17. Strategy Manager

The Strategy Manager receives:

```text
HedgeContext
+
StrategyHypothesis[]
```

It performs:

### Step 1 — Validation

Remove proposals violating hard constraints.

### Step 2 — Comparison

Compare valid strategies using:

- protection
- cost
- portfolio fit
- upside trade-off
- liquidity
- execution characteristics
- market context

The research identifies eight broad evaluation dimensions including basis risk, carry cost, Greeks, protection profile, volatility surface, transaction costs, liquidity, and opportunity cost.

### Step 3 — Contextual reasoning

The LLM evaluates qualitative trade-offs and the user's/project objective.

### Step 4 — Selection

Output:

```text
SELECT_STRATEGY
NO_TRADE
REASSESS
```

---

# 18. Strategy Manager Output

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

Example:

```text
Selected:
PUT_SPREAD

Reason:
Provides sufficient protection while remaining
within the hedge budget and preserving upside.

Protective Put:
Rejected — excessive cost.

Collar:
Rejected — excessive upside sacrifice.

No Hedge:
Rejected — insufficient protection.
```

---

# 19. Risk Agent

The Risk Agent is the **non-negotiable safety layer**.

It asks:

> **"Is this proposed hedge allowed and safe?"**

It validates:

### Portfolio risk

- projected drawdown
- exposure
- concentration
- existing hedge

### Position limits

- maximum hedge ratio
- maximum contracts
- maximum notional
- options exposure

### Cost

- preferred hedge budget
- hard maximum budget

### Options

- liquidity
- Greeks
- expiration
- contract validity
- multi-leg consistency

### Execution

- buying power
- order feasibility
- price tolerance

---

# 20. Risk Outcomes

```text
APPROVE
MODIFY
REJECT
```

### APPROVE

Send to Execution.

### MODIFY

Suggest a permitted modification such as reducing position size.

### REJECT

Return to Strategy Manager.

Risk cannot invent a completely new strategy.

The LLM cannot override deterministic risk constraints.

---

# 21. Execution Agent

The Execution Agent answers:

> **"How do I execute this already-approved strategy?"**

It receives:

```text
ExecutionPlan
```

containing:

- approval ID
- strategy
- contracts
- quantities
- order constraints
- price tolerance

It performs final pre-flight checks and sends the approved trade through the Alpaca integration.

The project architecture explicitly separates LLM reasoning, MCP tools, risk controls, and order execution.

---

# 22. Multi-Leg Execution

For:

### Put Spread

```text
BUY PUT
+
SELL PUT
```

### Collar

```text
BUY PUT
+
SELL CALL
```

the system should prefer strategy-level/multi-leg execution where supported rather than independently executing legs.

This reduces **legging risk**.

If one leg fails:

```text
Execution incomplete
      ↓
Record actual position
      ↓
Risk / Orchestrator
      ↓
Recovery decision
```

The system must never falsely report the strategy as successfully executed.

---

# 23. Execution Result

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

Possible statuses:

```text
FILLED
PARTIALLY_FILLED
FAILED
CANCELLED
```

---

# 24. Monitoring Agent

The Monitoring Agent does **not make trades**.

Its job is:

> **Detect whether the current portfolio/hedge has changed enough to warrant reassessment.**

It monitors:

- portfolio value
- drawdown
- volatility
- exposure
- hedge ratio
- target hedge
- hedge P&L
- option Greeks
- time to expiration
- liquidity
- relevant events

---

# 25. Trigger Types

### Hedge drift

```text
Current hedge ≠ target hedge
```

### Drawdown change

Material increase/decrease in portfolio drawdown.

### Volatility change

Significant regime transition.

### Event trigger

Material market/company event.

### Expiration trigger

Hedge approaching expiration.

### Emergency trigger

Extreme risk event.

---

# 26. Deadband

The system should not trade because of tiny deviations.

Conceptually:

```text
Target hedge = 20%

Current = 19.8%
→ No action

Current = 14%
→ Reassess
```

The exact thresholds should be configurable and validated during implementation.

---

# 27. Cooldown

After a hedge adjustment:

```text
TRADE
 ↓
COOLDOWN
 ↓
Normal monitoring
```

Minor signals during the cooldown should not cause another trade.

However:

```text
Extreme risk event
       ↓
Bypass cooldown
```

This prevents overtrading while preserving emergency responsiveness.

---

# 28. Reassessment Outcomes

A reassessment does **not automatically mean a trade**.

Possible results:

```text
MAINTAIN
INCREASE
DECREASE
REMOVE
REPLACE
NO_TRADE
```

For example:

```text
Current hedge = 30%

Market stabilizes
       ↓
Strategy Manager
       ↓
Target hedge = 10%
       ↓
DECREASE
```

Or:

```text
Current hedge = 20%

Market changes
       ↓
Reassessment
       ↓
20% remains appropriate
       ↓
NO TRADE
```

---

# 29. Adaptive Hedge Lifecycle

```text
                 LOW RISK
                    │
                    ↓
                0% HEDGE
                    │
                    ↓
              RISK INCREASES
                    │
                    ↓
             SMALL HEDGE
                    │
                    ↓
             HIGHER RISK
                    │
                    ↓
            STRONGER HEDGE
                    │
                    ↓
               RECOVERY
                    │
                    ↓
             REDUCE HEDGE
                    │
                    ↓
                LOW RISK
                    ↺
```

The key differentiator is that the system can **increase, decrease, replace, or remove** protection rather than simply accumulating puts.

---

# 30. Agent State Contracts

The core implementation objects are:

```text
HedgeContext
StrategyHypothesis
StrategyDecision
RiskDecision
ExecutionPlan
ExecutionResult
MonitoringState
```

### Workflow

```text
HedgeContext
     ↓
StrategyHypothesis[]
     ↓
StrategyDecision
     ↓
RiskDecision
     ↓
ExecutionPlan
     ↓
ExecutionResult
     ↓
MonitoringState
```

These contracts provide the interface between agents and make the system easier to test and debug.

---

# 31. Failure Handling

The system must distinguish between:

### Critical failures

Examples:

- portfolio unavailable
- stale/invalid options data
- risk engine unavailable
- invalid execution state

→ **Do not trade.**

### Recoverable failures

Examples:

- news unavailable
- one enrichment source unavailable
- non-critical analysis failure

→ Continue with degraded context and clearly record the limitation.

---

# 32. Autonomous Safety Rules

The following principles are mandatory:

### Rule 1

**No Strategy Agent can execute trades.**

### Rule 2

**Strategy Manager cannot bypass Risk.**

### Rule 3

**Execution Agent cannot execute without valid Risk approval.**

### Rule 4

**LLM cannot override deterministic risk constraints.**

### Rule 5

**Execution Agent cannot silently modify an approved strategy.**

### Rule 6

**No-trade is always a valid outcome.**

### Rule 7

**Every trade must have an auditable decision trail.**

---

# 33. Database / State

The system should persist:

### Portfolio

- snapshots
- positions
- exposure

### Agent activity

- agent runs
- inputs
- outputs
- failures

### Strategy

- hypotheses
- selected strategies
- rejected strategies
- reasoning

### Risk

- risk checks
- approvals
- rejections
- modifications

### Execution

- orders
- fills
- slippage
- failures

### Monitoring

- triggers
- hedge changes
- reassessments

### Performance

- portfolio P&L
- hedge P&L
- drawdown
- hedge costs
- benchmark comparison

---

# 34. Technology Stack

## Frontend

- React
- TypeScript

## Backend

- Python
- FastAPI

## Agent orchestration
 
- LangGraph
 
## Model / LLM Layer
 
- OpenRouter (Development & Active Testing)
- Featherless AI (Final Evaluation & Submission)
- Unified OpenAI-compatible interface toggleable via `LLM_PROVIDER` environment variable

## Trading

- Alpaca Trading API
- Alpaca MCP
- Alpaca CLI where useful

## Database

- PostgreSQL / Supabase

## RAG

Not required for the MVP.

---

# 35. MCP Architecture

MCP provides the interface between the AI system and external capabilities.

Conceptually:

```text
                   AI APPLICATION
                        │
                    MCP CLIENT
                        │
                    MCP SERVER
                  /      |       \
                 /       |        \
             Alpaca   Market     Other
               API      Data      Tools
```

MCP tools can expose capabilities such as:

```text
get_portfolio()
get_positions()
get_market_data()
get_option_chain()
get_news()
place_order()
cancel_order()
```

The exact Alpaca MCP tool names and schemas should be determined from the actual implementation rather than hardcoded into this BRD. MCP is an interface layer rather than a replacement for Alpaca's underlying APIs.

---

# 36. Performance & P&L

Because **P&L performance is explicitly part of judging**, performance must be a first-class product metric.

The dashboard should track:

```text
Portfolio P&L
Hedge P&L
Net P&L
Maximum Drawdown
Hedge Cost
Protection Achieved
```

Where possible, compare:

```text
Actual hedged portfolio
vs
Unhedged benchmark
```

This helps demonstrate whether the adaptive hedge actually improved downside behavior rather than merely generating trades.

---

# 37. Hackathon Demo Flow

The ideal demonstration should tell one continuous story.

### Scene 1 — Baseline

```text
Portfolio healthy
Risk low
No hedge
```

### Scene 2 — Risk develops

```text
Drawdown increases
Volatility increases
News/event changes
```

### Scene 3 — Agents investigate

```text
Portfolio ✓
Market ✓
News ✓
Stock ✓
Options ✓
```

### Scene 4 — Strategy competition

```text
Protective Put
Put Spread
Collar
No Hedge
```

### Scene 5 — Strategy Manager

```text
Selected:
Put Spread

Why:
Best current protection/cost/fit.
```

### Scene 6 — Risk

```text
Budget ✓
Liquidity ✓
Exposure ✓
Position size ✓
```

### Scene 7 — Execution

```text
Alpaca MCP
 ↓
Order
 ↓
Filled
```

### Scene 8 — Adaptation

Market changes again.

```text
Current hedge = 30%
Target hedge = 12%
```

Agent:

> **Reduce hedge.**

This is the moment that proves the project isn't merely an options trading bot.

---

# 38. MVP Success Criteria

The MVP is successful if it can demonstrate one complete autonomous cycle:

> **Portfolio becomes riskier → agents investigate → options candidates are identified → multiple strategies generate independent hypotheses → Strategy Manager selects a strategy → Risk Agent validates it → Execution Agent executes through Alpaca → monitoring observes the portfolio → conditions change → system reassesses and adapts the hedge.**

The primary success criteria are:

### Functional

- End-to-end autonomous workflow works.
- Strategies can be generated and compared.
- Risk controls can reject/modify proposals.
- Approved strategies can execute.
- Monitoring can trigger reassessment.

### Trading

- Orders execute correctly in Alpaca paper trading.
- Multi-leg strategies are handled safely.
- Trade and P&L history are recorded.

### Agentic

- Agents have clearly separated responsibilities.
- Orchestration is stateful.
- Decisions are explainable.
- No-trade is possible.
- System adapts rather than following a static rule.

### Presentation

- Judge understands the system quickly.
- Agent activity is visible.
- Every trade has an explanation.
- Actual Alpaca activity and P&L are visible.

---

# 39. Stretch Goals

Only after the MVP is stable.

The research identifies possible advanced additions such as:

- Put Calendar Spread
- VIX Call Overlay
- Ratio Put Backspread

These should remain **Tier-B/stretch strategies**, rather than expanding the MVP prematurely.

More complex strategies with naked-option exposure, institutional infrastructure requirements, or high-frequency delta hedging should remain outside the MVP.

---

# 40. Final Product Definition

> **Autonomous Adaptive Portfolio Hedge Agent is a multi-agent portfolio protection system that continuously observes portfolio and market risk, constructs competing options-based hedging hypotheses, selects the best-fit protection under user/project constraints, passes the decision through a deterministic risk gate, executes through Alpaca, and continuously monitors and rebalances the hedge as conditions change.**

The fundamental architecture is:

```text
       AGENTS REASON
            ↓
       TOOLS PROVIDE
            ↓
    DETERMINISTIC CODE
         ENFORCES
            ↓
       ALPACA EXECUTES
            ↓
        MONITORING
            ↓
          ADAPT
            ↺
```

That is the **BRD baseline I'd use for implementation**. The research supports the architecture and strategy framework, while the exact numerical thresholds, Alpaca tool schemas, and execution policies should be finalized during implementation/testing rather than invented prematurely.
