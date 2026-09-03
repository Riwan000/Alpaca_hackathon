import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw, ArrowUpRight, AlertCircle, BookOpen } from 'lucide-react';
import {
  useHedgeContext,
  useStrategyDecision,
  useStrategyHypotheses,
  useAgentRuns,
  useMonitoringState,
  usePortfolioLatest,
  useWorkflowState,
  useRiskChecks,
  useExecutionResult,
  usePnlCurrent,
  usePnlSeries,
  useMonitoringEvents,
} from '../api/queries';
import { PortfolioOverview } from '../components/PortfolioOverview';
import { RiskOverview } from '../components/RiskOverview';
import { Recommendation } from '../components/Recommendation';
import { StrategyComparison } from '../components/StrategyComparison';
import { AgentActivity } from '../components/AgentActivity';
import { HedgeStatus } from '../components/HedgeStatus';
import { RiskChecklist } from '../components/RiskChecklist';
import { OrderStatus } from '../components/OrderStatus';
import { WorkflowState } from '../components/WorkflowState';
import { RunCycleButton } from '../components/RunCycleButton';
import { Performance } from '../components/Performance';
import { MonitoringPanel } from '../components/MonitoringPanel';
import { HedgeDriftGauge } from '../components/HedgeDriftGauge';
import { ReassessmentHistory } from '../components/ReassessmentHistory';
import { TradeHistory, type TradeItem } from '../components/TradeHistory';
import { DecisionTrail, type DecisionTrailData } from '../components/DecisionTrail';
import { DemoWalkthrough } from '../components/DemoWalkthrough';

export const DashboardPage: React.FC = () => {
  const [selectedTrade, setSelectedTrade] = useState<TradeItem | null>(null);

  const contextQuery = useHedgeContext();
  const portfolioQuery = usePortfolioLatest();
  const strategyQuery = useStrategyDecision();
  const hypothesesQuery = useStrategyHypotheses();
  const agentRunsQuery = useAgentRuns();
  const monitoringQuery = useMonitoringState();
  const monitoringEventsQuery = useMonitoringEvents();
  const workflowQuery = useWorkflowState();
  const riskChecksQuery = useRiskChecks();
  const executionQuery = useExecutionResult();
  const pnlCurrentQuery = usePnlCurrent();
  const pnlSeriesQuery = usePnlSeries();

  const isLoading =
    contextQuery.isLoading ||
    strategyQuery.isLoading ||
    monitoringQuery.isLoading ||
    hypothesesQuery.isLoading ||
    agentRunsQuery.isLoading ||
    workflowQuery.isLoading;

  const error =
    contextQuery.error ||
    strategyQuery.error ||
    monitoringQuery.error ||
    workflowQuery.error;

  const context = contextQuery.data;
  const portfolio = portfolioQuery.data || context?.portfolio_state;
  const strategy = strategyQuery.data;
  const hypotheses = hypothesesQuery.data || strategy?.alternatives || [];
  const allHypotheses = strategy?.selected_hypothesis
    ? [
        strategy.selected_hypothesis,
        ...hypotheses.filter((h) => h.strategy !== strategy.selected_hypothesis?.strategy),
      ]
    : hypotheses;

  const agentRuns = agentRunsQuery.data || [];
  const workflow = workflowQuery.data;
  const riskDecision = riskChecksQuery.data;
  const executionResult = executionQuery.data;

  // Build trades from execution result if present
  const trades: TradeItem[] = executionResult
    ? [
        {
          id: executionResult.order_ids?.[0] || 'ord-100',
          cycle_id: executionResult.cycle_id,
          order_class: 'MLEG',
          status: executionResult.status,
          submitted_at: executionResult.submitted_at || '2026-09-04T01:00:00Z',
          cost: executionResult.actual_cost,
          legs: (executionResult.filled_legs || []).map((l) => ({
            symbol: l.leg_symbol,
            qty: l.qty,
            price: l.price,
            slippage: l.slippage,
          })),
        },
      ]
    : [];

  // Build decision trail data
  const trailData: DecisionTrailData = {
    order_id: selectedTrade?.id || trades[0]?.id || 'ord-100',
    trade: {
      symbol: trades[0]?.legs?.[0]?.symbol || 'SPY261218P00500000',
      action: 'BUY',
      qty: trades[0]?.legs?.[0]?.qty || 20,
      price: trades[0]?.legs?.[0]?.price || 8.55,
      status: executionResult?.status || 'FILLED',
      filled_at: executionResult?.completed_at,
    },
    risk: {
      verdict: riskDecision?.verdict || 'APPROVE',
      checks_passed: riskDecision?.checks?.filter((c) => c.passed).length || 4,
      checks_total: riskDecision?.checks?.length || 4,
      rationale: riskDecision?.rationale,
    },
    strategy: {
      strategy_type: strategy?.selected_strategy || 'PROTECTIVE_PUT',
      action: strategy?.action || 'NEW_HEDGE',
      rationale: strategy?.rationale || 'Protective Put provides maximum downside protection within budget.',
    },
    hypotheses: (allHypotheses || []).map((h) => ({
      strategy_type: h.strategy,
      verdict: h.viable ? 'ACCEPTED' : 'REJECTED',
    })),
    context: {
      regime: context?.market_state?.regime || 'NORMAL',
      vix: context?.market_state?.vix,
      drawdown: portfolio?.drawdown,
    },
    trigger: {
      trigger_type: monitoringQuery.data?.trigger_history?.[0]?.trigger_type || 'VOLATILITY_SPIKE',
      observed: monitoringQuery.data?.trigger_history?.[0]?.observed_value,
      threshold: monitoringQuery.data?.trigger_history?.[0]?.threshold,
      fired_at: monitoringQuery.data?.trigger_history?.[0]?.observed_at,
    },
  };

  const handleReset = () => {
    // Invalidate and refetch queries to return UI to seed state
    contextQuery.refetch();
    portfolioQuery.refetch();
    strategyQuery.refetch();
    hypothesesQuery.refetch();
    agentRunsQuery.refetch();
    monitoringQuery.refetch();
    workflowQuery.refetch();
    riskChecksQuery.refetch();
    executionQuery.refetch();
    pnlCurrentQuery.refetch();
    pnlSeriesQuery.refetch();
    setSelectedTrade(null);
  };

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      {/* Page Title / Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-2xl font-bold font-serif text-white">
            Portfolio Risk & Strategy Dashboard
          </h1>
          <div className="flex items-center gap-2 mt-1">
            <p className="text-xs text-slate-400 font-mono">
              REAL-TIME HEDGE METRICS • CONTINUOUS ADAPTIVE PROTECTION
              {context && ` • CYCLE ${context.cycle_id.toUpperCase()}`}
            </p>
            <span className="text-[10px] font-mono text-slate-400" data-testid="portfolio-aum">
              AUM {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(portfolio?.total_value ?? 1000000)}
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {isLoading && (
            <span
              className="flex items-center gap-1 text-xs font-mono text-slate-400"
              data-testid="loading-indicator"
            >
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              Syncing Feed...
            </span>
          )}
          <RunCycleButton
            isRunning={workflow?.status === 'running'}
            onCycleTriggered={() => {
              workflowQuery.refetch();
              agentRunsQuery.refetch();
            }}
          />
          <Link
            to="/adaptation"
            className="px-3 py-2 bg-indigo-900/60 hover:bg-indigo-800/80 text-indigo-200 text-xs font-mono font-medium flex items-center gap-1 border border-indigo-700/60 rounded transition-colors"
          >
            <BookOpen className="w-3.5 h-3.5 text-indigo-400" />
            Adaptation Story
          </Link>
          <Link
            to={`/strategy/${context?.cycle_id || 'cyc-001'}`}
            className="px-3 py-2 bg-slate-800 text-white text-xs font-mono font-medium flex items-center gap-1 hover:bg-slate-700 rounded transition-colors border border-slate-700"
          >
            Strategy Details
            <ArrowUpRight className="w-3.5 h-3.5 text-amber-400" />
          </Link>
        </div>
      </div>

      {/* Global Error Banner */}
      {error && (
        <div
          className="p-4 border border-rose-800 bg-rose-950/20 text-xs font-mono text-rose-400 flex items-center gap-2 rounded-lg"
          data-testid="dashboard-error"
        >
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>Error loading pipeline feed: {error.message}</span>
        </div>
      )}

      {/* Demo Script Walkthrough Banner with Reset Button */}
      <DemoWalkthrough onReset={handleReset} />

      {/* P&L and Attribution */}
      <Performance
        current={pnlCurrentQuery.data}
        series={pnlSeriesQuery.data || []}
        isLoading={pnlCurrentQuery.isLoading}
      />

      {/* Live Workflow Orchestration State */}
      <WorkflowState
        workflow={workflow}
        isLoading={workflowQuery.isLoading}
        error={workflowQuery.error}
      />

      {/* Hedge Drift Gauge & Monitoring Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-5">
          <HedgeDriftGauge
            currentHedgeRatio={monitoringQuery.data?.hedge_ratio ?? 0.19}
            targetHedgeRatio={monitoringQuery.data?.target_hedge_ratio ?? 0.20}
          />
        </div>
        <div className="lg:col-span-7">
          <MonitoringPanel
            events={monitoringEventsQuery.data || []}
            activeTriggers={monitoringQuery.data?.active_triggers || []}
            isLoading={monitoringEventsQuery.isLoading}
          />
        </div>
      </div>

      {/* Hedge Status & Risk Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-5">
          <HedgeStatus
            currentHedge={context?.current_hedge}
            activeHypothesis={strategy?.selected_hypothesis}
            isLoading={contextQuery.isLoading}
            error={contextQuery.error}
          />
        </div>
        <div className="lg:col-span-7">
          <RiskOverview
            portfolio={portfolio}
            isLoading={contextQuery.isLoading}
            error={contextQuery.error}
          />
        </div>
      </div>

      {/* Recommendation Panel */}
      <Recommendation
        decision={strategy}
        currentHedge={context?.current_hedge}
        objective={context?.objective}
        isLoading={strategyQuery.isLoading}
        error={strategyQuery.error}
      />

      {/* Quantitative Risk Gate Checks */}
      <RiskChecklist
        decision={riskDecision}
        isLoading={riskChecksQuery.isLoading}
        error={riskChecksQuery.error}
      />

      {/* Strategy Hypotheses Side-by-Side Comparison */}
      <StrategyComparison
        hypotheses={allHypotheses}
        selectedStrategy={strategy?.selected_strategy}
        comparisonRows={strategy?.comparison}
        isLoading={hypothesesQuery.isLoading}
        error={hypothesesQuery.error}
      />

      {/* Reassessment History */}
      <ReassessmentHistory
        reassessments={[
          {
            id: 1,
            cycle_id: context?.cycle_id || 'cyc-001',
            trigger: 'VOLATILITY_SPIKE',
            outcome: 'DECREASE',
            reason: 'Risk subsided with VIX falling below threshold. Trimming excess put coverage.',
            created_at: new Date().toISOString(),
            delta: -0.50,
            before_hedge_ratio: 0.80,
            after_hedge_ratio: 0.30,
          },
        ]}
      />

      {/* Broker Order Execution Status & Trade History */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-6">
          <OrderStatus
            result={executionResult}
            isLoading={executionQuery.isLoading}
            error={executionQuery.error}
          />
        </div>
        <div className="lg:col-span-6">
          <TradeHistory
            trades={trades}
            onSelectTrade={(t) => setSelectedTrade(t)}
            isLoading={executionQuery.isLoading}
          />
        </div>
      </div>

      {/* Decision Trail Drill-down */}
      <DecisionTrail data={trailData} />

      {/* Portfolio Overview & Agent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-7">
          <PortfolioOverview
            portfolio={portfolio}
            isLoading={portfolioQuery.isLoading || contextQuery.isLoading}
            error={portfolioQuery.error || contextQuery.error}
          />
        </div>
        <div className="lg:col-span-5">
          <AgentActivity
            runs={agentRuns}
            isLoading={agentRunsQuery.isLoading}
            error={agentRunsQuery.error}
          />
        </div>
      </div>
    </div>
  );
};
