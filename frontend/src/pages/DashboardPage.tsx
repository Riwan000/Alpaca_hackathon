import React, { useState, useEffect } from 'react';
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
import { Tabs, type TabItem } from '../components/Tabs';
import { getUserConfiguration, type UserConfiguration } from './ConfigurationPage';

export const DashboardPage: React.FC = () => {
  const [selectedTrade, setSelectedTrade] = useState<TradeItem | null>(null);
  const [userConfig, setUserConfig] = useState<UserConfiguration>(getUserConfiguration);

  useEffect(() => {
    const handleConfigUpdate = () => {
      setUserConfig(getUserConfiguration());
    };
    window.addEventListener('storage', handleConfigUpdate);
    window.addEventListener('aegis-config-updated', handleConfigUpdate);
    return () => {
      window.removeEventListener('storage', handleConfigUpdate);
      window.removeEventListener('aegis-config-updated', handleConfigUpdate);
    };
  }, []);

  const contextQuery = useHedgeContext();
  const portfolioQuery = usePortfolioLatest();
  const strategyQuery = useStrategyDecision();
  // Hypotheses are persisted across every cycle ever run; without a cycle_id filter
  // this returns the full history (e.g. 4 hedge-family hypotheses x N past cycles),
  // which duplicates strategy types in the comparison grid. Scope to the current cycle.
  const hypothesesQuery = useStrategyHypotheses(contextQuery.data?.cycle_id);
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
          cost: executionResult.actual_cost ?? 0,
          legs: (executionResult.filled_legs || []).map((l) => ({
            symbol: l.leg_symbol,
            qty: l.qty,
            price: l.price,
            slippage: l.slippage ?? undefined,
          })),
        },
      ]
    : [];

  // Build decision trail data. Each section is included only when the
  // corresponding query actually returned real data — a query that failed
  // or has not yet produced anything renders as "not available" inside
  // DecisionTrail rather than being backfilled with fabricated placeholder
  // values (see BUG: fake FILLED trade shown with zero real executions).
  const firstLeg = trades[0]?.legs?.[0];
  const latestTrigger = monitoringQuery.data?.trigger_history?.[0];

  const trailData: DecisionTrailData = {
    order_id: selectedTrade?.id || trades[0]?.id || undefined,
    trade: firstLeg
      ? {
          symbol: firstLeg.symbol,
          action: 'BUY',
          qty: firstLeg.qty,
          price: firstLeg.price,
          status: executionResult?.status || 'UNKNOWN',
          filled_at: executionResult?.completed_at ?? undefined,
        }
      : undefined,
    risk: riskDecision
      ? {
          verdict: riskDecision.verdict,
          checks_passed: riskDecision.checks?.filter((c) => c.passed).length ?? 0,
          checks_total: riskDecision.checks?.length ?? 0,
          rationale: riskDecision.rationale,
        }
      : undefined,
    strategy: strategy
      ? {
          strategy_type: strategy.selected_strategy || 'UNKNOWN',
          action: strategy.decision,
          rationale: strategy.rationale,
        }
      : undefined,
    hypotheses: (allHypotheses || []).map((h) => ({
      strategy_type: h.strategy,
      verdict: h.viable ? 'ACCEPTED' : 'REJECTED',
    })),
    context: context
      ? {
          regime: context.market_state?.regime || 'UNKNOWN',
          vix: context.market_state?.vix ?? undefined,
          drawdown: portfolio?.drawdown ?? undefined,
        }
      : undefined,
    trigger: latestTrigger
      ? {
          trigger_type: latestTrigger.trigger_type,
          observed: latestTrigger.observed_value,
          threshold: latestTrigger.threshold,
          fired_at: latestTrigger.observed_at,
        }
      : undefined,
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
    setUserConfig(getUserConfiguration());
  };

  // Hedge Drift Gauge inputs. The current ratio must come from live monitoring
  // state; the target may legitimately come from the user's own configuration.
  // When neither yields a real number we render an "unavailable" card rather
  // than a plausible-looking gauge backed by fabricated ratios.
  const gaugeCurrentRatio = monitoringQuery.data?.hedge_ratio;
  const gaugeTargetRatio =
    userConfig?.targetHedgeRatio !== undefined
      ? userConfig.targetHedgeRatio / 100
      : monitoringQuery.data?.target_hedge_ratio;
  const gaugeDeadband =
    userConfig?.deadbandBuffer !== undefined ? userConfig.deadbandBuffer / 100 : 0.05;
  const hasHedgeDriftData =
    typeof gaugeCurrentRatio === 'number' && typeof gaugeTargetRatio === 'number';

  const dashboardTabs: TabItem[] = [
    {
      id: 'overview',
      label: 'Overview',
      content: (
        <div className="space-y-6">
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

          {/* Hedge Drift Gauge & Recommendation */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-5">
              {hasHedgeDriftData ? (
                <HedgeDriftGauge
                  currentHedgeRatio={gaugeCurrentRatio}
                  targetHedgeRatio={gaugeTargetRatio}
                  deadband={gaugeDeadband}
                />
              ) : (
                <div
                  data-testid="hedge-drift-gauge-unavailable"
                  className="p-5 rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] h-full"
                >
                  <h3 className="text-base font-semibold text-[var(--text-main)]">Hedge Drift Gauge</h3>
                  <p className="text-xs text-[var(--text-muted)] mt-1">
                    Awaiting live monitoring data.
                  </p>
                </div>
              )}
            </div>
            <div className="lg:col-span-7">
              <Recommendation
                decision={strategy}
                currentHedge={context?.current_hedge}
                objective={
                  context?.objective
                    ? {
                        ...context.objective,
                        target_hedge_ratio:
                          userConfig?.targetHedgeRatio !== undefined
                            ? userConfig.targetHedgeRatio / 100
                            : context.objective.target_hedge_ratio,
                        max_hedge_budget_pct:
                          userConfig?.maxBudget !== undefined
                            ? userConfig.maxBudget / 100
                            : context.objective.max_hedge_budget_pct,
                        drawdown_tolerance_pct:
                          userConfig?.drawdownTolerance !== undefined
                            ? userConfig.drawdownTolerance / 100
                            : context.objective.drawdown_tolerance_pct,
                      }
                    : context?.objective
                }
                isLoading={strategyQuery.isLoading}
                error={strategyQuery.error}
              />
            </div>
          </div>

          {/* Risk Overview */}
          <RiskOverview
            portfolio={portfolio}
            isLoading={contextQuery.isLoading}
            error={contextQuery.error}
          />
        </div>
      ),
    },
    {
      id: 'risk',
      label: 'Risk',
      content: (
        <div className="space-y-6">
          {/* Hedge Status & Risk Checklist */}
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
              <RiskChecklist
                decision={riskDecision}
                isLoading={riskChecksQuery.isLoading}
                error={riskChecksQuery.error}
              />
            </div>
          </div>

          {/* Strategy Hypotheses Side-by-Side Comparison */}
          <StrategyComparison
            hypotheses={allHypotheses}
            selectedStrategy={strategy?.selected_strategy}
            comparisonRows={strategy?.comparison}
            isLoading={hypothesesQuery.isLoading}
            error={hypothesesQuery.error}
          />

          {/* Reassessment History. No read-back query is wired for Level-2
              reassessment events yet, so this renders its own empty state
              rather than a fabricated row. TODO: feed from a real
              useReassessmentEvents() hook once the endpoint is exposed. */}
          <ReassessmentHistory reassessments={[]} />
        </div>
      ),
    },
    {
      id: 'execution',
      label: 'Execution',
      content: (
        <div className="space-y-6">
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

          {/* Portfolio Overview */}
          <PortfolioOverview
            portfolio={portfolio}
            isLoading={portfolioQuery.isLoading || contextQuery.isLoading}
            error={portfolioQuery.error || contextQuery.error}
          />
        </div>
      ),
    },
    {
      id: 'agent-debug',
      label: 'Agent / Debug',
      content: (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-6">
            <AgentActivity
              runs={agentRuns}
              isLoading={agentRunsQuery.isLoading}
              error={agentRunsQuery.error}
            />
          </div>
          <div className="lg:col-span-6">
            <MonitoringPanel
              events={monitoringEventsQuery.data || []}
              activeTriggers={monitoringQuery.data?.active_triggers || []}
              isLoading={monitoringEventsQuery.isLoading}
            />
          </div>
        </div>
      ),
    },
  ];

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
              {portfolio?.total_value !== undefined
                ? `AUM ${new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(portfolio.total_value)}`
                : 'AUM unavailable'}
            </span>
          </div>
          {/* Telemetry metadata */}
          <div className="sr-only">
            <span data-testid="greek-delta">
              {strategy?.selected_hypothesis?.hedge_metrics?.net_delta ?? 'N/A'}
            </span>
            <span data-testid="monitoring-status">
              {monitoringQuery.data?.reassessment_recommended ? '● REASSESS RECOMMENDED' : '● IDLE'}
            </span>
            <span data-testid="active-trigger-item">
              {!monitoringQuery.data
                ? 'TRIGGER: UNAVAILABLE'
                : monitoringQuery.data.active_triggers && monitoringQuery.data.active_triggers.length > 0
                ? `TRIGGER: ${monitoringQuery.data.active_triggers.join(', ')}`
                : 'TRIGGER: NONE'}
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
            <BookOpen className="w-3.5 h-3.5 text-[var(--brand-teal)]" />
            Adaptation Story
          </Link>
          <Link
            to={`/strategy/${context?.cycle_id || 'cyc-001'}`}
            className="px-3 py-2 bg-[var(--bg-subtle)] text-[var(--text-main)] text-xs font-mono font-medium flex items-center gap-1 hover:bg-[var(--bg-subtle-hover)] rounded transition-colors border border-[var(--border-dark)]"
          >
            Strategy Details
            <ArrowUpRight className="w-3.5 h-3.5 text-amber-400" />
          </Link>
        </div>
      </div>

      {/* Global Error Banner */}
      {error && (
        <div
          className="p-4 border border-[var(--status-danger)]/30 bg-[var(--status-danger)]/10 text-xs font-mono text-[var(--status-danger)] flex items-center gap-2 rounded-lg"
          data-testid="dashboard-error"
        >
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>Error loading pipeline feed: {error.message}</span>
        </div>
      )}

      {/* Demo Script Walkthrough Banner with Reset Button */}
      <DemoWalkthrough onReset={handleReset} />

      {/* Tabbed panel groups: Overview is the default landing view; the rest
          (Risk, Execution, Agent/Debug) are reachable via the tab bar. */}
      <Tabs tabs={dashboardTabs} defaultActiveId="overview" />
    </div>
  );
};
