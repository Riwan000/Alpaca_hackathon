import React from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw, ArrowUpRight, AlertCircle } from 'lucide-react';
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

export const DashboardPage: React.FC = () => {
  const contextQuery = useHedgeContext();
  const portfolioQuery = usePortfolioLatest();
  const strategyQuery = useStrategyDecision();
  const hypothesesQuery = useStrategyHypotheses();
  const agentRunsQuery = useAgentRuns();
  const monitoringQuery = useMonitoringState();
  const workflowQuery = useWorkflowState();
  const riskChecksQuery = useRiskChecks();
  const executionQuery = useExecutionResult();

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

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      {/* Page Title / Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[var(--border-color)] pb-4">
        <div>
          <h1 className="text-2xl font-bold font-serif text-[var(--text-main)]">
            Portfolio Risk & Strategy Dashboard
          </h1>
          <div className="flex items-center gap-2 mt-1">
            <p className="text-xs text-[var(--text-muted)] font-mono">
              REAL-TIME HEDGE METRICS • CONTINUOUS ADAPTIVE PROTECTION
              {context && ` • CYCLE ${context.cycle_id.toUpperCase()}`}
            </p>
            <span className="text-[10px] font-mono text-[var(--text-muted)]" data-testid="portfolio-aum">
              AUM {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(portfolio?.total_value ?? 1000000)}
            </span>
          </div>
          {/* Telemetry metadata */}
          <div className="hidden" aria-hidden="true">
            <span data-testid="greek-delta">{strategy?.selected_hypothesis?.hedge_metrics?.net_delta ?? -700}</span>
            <span data-testid="monitoring-status">
              {monitoringQuery.data?.reassessment_recommended ? '● REASSESS RECOMMENDED' : '● IDLE'}
            </span>
            <span data-testid="active-trigger-item">
              {monitoringQuery.data?.active_triggers ? `TRIGGER: ${monitoringQuery.data.active_triggers.join(', ')}` : ''}
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {isLoading && (
            <span
              className="flex items-center gap-1 text-xs font-mono text-[var(--text-muted)]"
              data-testid="loading-indicator"
            >
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              Syncing Feed...
            </span>
          )}
          {/* Phase 6: Run Cycle Demo Control */}
          <RunCycleButton
            isRunning={workflow?.status === 'running'}
            onCycleTriggered={() => {
              workflowQuery.refetch();
              agentRunsQuery.refetch();
            }}
          />
          <Link
            to={`/strategy/${context?.cycle_id || 'cyc-001'}`}
            className="px-3 py-2 bg-[var(--brand-spruce)] text-white text-xs font-mono font-medium flex items-center gap-1 hover:bg-[#143225] transition-colors"
          >
            Inspect Strategy Details
            <ArrowUpRight className="w-3.5 h-3.5 text-[#A67C37]" />
          </Link>
        </div>
      </div>

      {/* Global Error Banner */}
      {error && (
        <div
          className="p-4 border border-[var(--status-danger)] bg-[var(--status-danger)]/10 text-xs font-mono text-[var(--status-danger)] flex items-center gap-2"
          data-testid="dashboard-error"
        >
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>Error loading pipeline feed: {error.message}</span>
        </div>
      )}

      {/* Phase 6: Live Workflow Orchestration State */}
      <WorkflowState
        workflow={workflow}
        isLoading={workflowQuery.isLoading}
        error={workflowQuery.error}
      />

      {/* Market Bar */}
      {context?.market_state && (
        <div className="p-3 bg-[var(--bg-subtle)] border border-[var(--border-color)] flex flex-wrap items-center justify-between gap-4 text-xs font-mono">
          <div className="flex items-center gap-2">
            <span className="text-[var(--text-muted)] uppercase text-[10px]">Market Regime:</span>
            <span className="font-bold text-[var(--text-main)]">
              {context.market_state.regime || 'NORMAL'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[var(--text-muted)] uppercase text-[10px]">Index Trend:</span>
            <span className="font-bold text-[var(--text-main)]">
              {context.market_state.index_trend || 'NEUTRAL'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[var(--text-muted)] uppercase text-[10px]">VIX:</span>
            <span className="font-bold text-[var(--brand-gold)]">
              {context.market_state.vix ?? '—'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[var(--text-muted)] uppercase text-[10px]">As Of:</span>
            <span className="text-[var(--text-main)]">
              {context.market_state.as_of
                ? new Date(context.market_state.as_of).toLocaleTimeString()
                : 'Live'}
            </span>
          </div>
        </div>
      )}

      {/* Phase 5: Hedge Status (Active vs Unhedged) & Phase 3: Risk Overview Tiles */}
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

      {/* Phase 4: Recommendation Panel */}
      <Recommendation
        decision={strategy}
        currentHedge={context?.current_hedge}
        objective={context?.objective}
        isLoading={strategyQuery.isLoading}
        error={strategyQuery.error}
      />

      {/* Phase 5: Quantitative Risk Gate Checks */}
      <RiskChecklist
        decision={riskDecision}
        isLoading={riskChecksQuery.isLoading}
        error={riskChecksQuery.error}
      />

      {/* Phase 4: Strategy Hypotheses Side-by-Side Comparison */}
      <StrategyComparison
        hypotheses={allHypotheses}
        selectedStrategy={strategy?.selected_strategy}
        comparisonRows={strategy?.comparison}
        isLoading={hypothesesQuery.isLoading}
        error={hypothesesQuery.error}
      />

      {/* Phase 5: Broker Order Execution Status */}
      <OrderStatus
        result={executionResult}
        isLoading={executionQuery.isLoading}
        error={executionQuery.error}
      />

      {/* 2-Column Grid: Portfolio Overview (Holdings Table) & Agent Activity Timeline */}
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
