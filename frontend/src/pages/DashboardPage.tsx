import React, { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { RefreshCw, ArrowUpRight, AlertCircle, BookOpen } from 'lucide-react';
import {
  useHedgeContext,
  useStrategyDecision,
  useStrategyHypotheses,
  useAgentRuns,
  useMonitoringState,
  usePortfolioLatest,
  useAlpacaAccount,
  useAlpacaHistory,
  useWorkflowState,
  useRiskChecks,
  useExecutionResult,
  usePnlCurrent,
  usePnlSeries,
  useMonitoringEvents,
} from '../api/queries';
import type { PortfolioState } from '../api/types';
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
import { Performance, type PerformanceSnapshot } from '../components/Performance';
import { MonitoringPanel } from '../components/MonitoringPanel';
import { HedgeDriftGauge } from '../components/HedgeDriftGauge';
import { ReassessmentHistory } from '../components/ReassessmentHistory';
import { TradeHistory, type TradeItem } from '../components/TradeHistory';
import { DecisionTrail, type DecisionTrailData } from '../components/DecisionTrail';
import { DemoWalkthrough } from '../components/DemoWalkthrough';
import { Tabs, type TabItem } from '../components/Tabs';
import { getUserConfiguration, type UserConfiguration } from './ConfigurationPage';

export const DashboardPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const providedId = searchParams.get('account_id') || searchParams.get('id') || undefined;
  const [selectedTrade, setSelectedTrade] = useState<TradeItem | null>(null);
  const [userConfig, setUserConfig] = useState<UserConfiguration>(getUserConfiguration);
  const [inputId, setInputId] = useState<string>('');
  const [isEditingId, setIsEditingId] = useState<boolean>(false);

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

  const activeId = providedId || (userConfig?.alpacaAccountId?.trim() ? userConfig.alpacaAccountId.trim() : undefined);
  const contextQuery = useHedgeContext();
  const portfolioQuery = usePortfolioLatest();
  const alpacaAccountQuery = useAlpacaAccount(activeId, { enabled: Boolean(activeId) });
  const alpacaHistoryQuery = useAlpacaHistory(activeId, '1W', '1H', { enabled: Boolean(activeId) });
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
    workflowQuery.error ||
    alpacaAccountQuery.error;

  const context = contextQuery.data;
  const alpacaAccount = alpacaAccountQuery.data;
  const rawPortfolio = portfolioQuery.data || context?.portfolio_state;

  // Live Alpaca balance & positions take priority for the provided ID
  const portfolio: PortfolioState | undefined = alpacaAccount
    ? {
        total_value: alpacaAccount.portfolio_value,
        cash: alpacaAccount.cash,
        equity: alpacaAccount.equity,
        buying_power: alpacaAccount.buying_power,
        gross_exposure: alpacaAccount.long_market_value,
        net_exposure: alpacaAccount.long_market_value - alpacaAccount.short_market_value,
        positions: alpacaAccount.positions,
        account_id: alpacaAccount.account_id,
        account_number: alpacaAccount.account_number,
        drawdown: alpacaAccount.drawdown ?? rawPortfolio?.drawdown,
        max_drawdown: rawPortfolio?.max_drawdown,
        volatility: rawPortfolio?.volatility,
        beta: rawPortfolio?.beta,
        concentration_hhi: rawPortfolio?.concentration_hhi,
      }
    : rawPortfolio;

  // Live Alpaca performance metrics feed Performance panel and trajectory chart
  const performanceCurrent: PerformanceSnapshot | undefined = alpacaAccount
    ? {
        portfolio_pnl: alpacaAccount.total_unrealized_pl ?? alpacaAccount.day_pnl ?? 0,
        hedge_pnl: 0,
        net_pnl: alpacaAccount.day_pnl ?? alpacaAccount.total_unrealized_pl ?? 0,
        drawdown: alpacaAccount.drawdown ?? 0,
        hedge_cost: 0,
        benchmark_pnl: alpacaAccount.day_pnl ?? 0,
      }
    : pnlCurrentQuery.data;

  const performanceSeries =
    activeId && alpacaHistoryQuery.data?.series && alpacaHistoryQuery.data.series.length > 0
      ? alpacaHistoryQuery.data.series.map((s, idx) => ({
          cycle_id: `alpaca-${idx}`,
          ts: s.ts,
          portfolio_pnl: s.portfolio_pnl,
          hedge_pnl: 0,
          net_pnl: s.net_pnl,
          benchmark_pnl: s.benchmark_pnl,
        }))
      : pnlSeriesQuery.data || [];
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
    alpacaAccountQuery.refetch();
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
            current={performanceCurrent}
            series={performanceSeries}
            isLoading={alpacaAccount ? alpacaAccountQuery.isLoading : pnlCurrentQuery.isLoading}
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
            accountId={alpacaAccount?.account_id}
            accountNumber={alpacaAccount?.account_number}
            accountStatus={alpacaAccount?.status}
            dayPnl={alpacaAccount?.day_pnl}
            totalUnrealizedPnl={alpacaAccount?.total_unrealized_pl}
            isLoading={alpacaAccountQuery.isLoading || portfolioQuery.isLoading || contextQuery.isLoading}
            error={alpacaAccountQuery.error || portfolioQuery.error || contextQuery.error}
            onRefresh={() => {
              alpacaAccountQuery.refetch();
              alpacaHistoryQuery.refetch();
              portfolioQuery.refetch();
            }}
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
          <div className="flex flex-wrap items-center gap-2 mt-1">
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

          {/* Alpaca Account Bar & ID Switcher */}
          <div className="flex flex-wrap items-center gap-2 mt-2" data-testid="alpaca-account-bar">
            <span
              data-testid="dashboard-account-id"
              className="inline-flex items-center gap-1.5 px-2.5 py-0.5 bg-[var(--brand-spruce)]/10 text-[var(--brand-spruce)] border border-[var(--brand-spruce)]/30 text-xs font-mono font-bold rounded"
              title={`Alpaca Account: ${alpacaAccount?.account_number || activeId || 'Default'}`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--brand-teal)] animate-pulse" />
              ALPACA: {alpacaAccount?.account_number || activeId || 'PA3C0P4T6AJE'}
            </span>

            {alpacaAccount && (
              <span
                data-testid="alpaca-live-balance"
                className="px-2 py-0.5 bg-[var(--bg-subtle)] text-[var(--text-main)] border border-[var(--border-color)] text-xs font-mono font-bold rounded"
              >
                Balance: {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(alpacaAccount.portfolio_value)}
              </span>
            )}

            {alpacaAccount?.day_pnl !== undefined && (
              <span
                data-testid="alpaca-day-pnl"
                className={`px-2 py-0.5 border text-xs font-mono font-bold rounded ${
                  alpacaAccount.day_pnl >= 0
                    ? 'bg-[var(--status-safe)]/10 text-[var(--status-safe)] border-[var(--status-safe)]/30'
                    : 'bg-[var(--status-danger)]/10 text-[var(--status-danger)] border-[var(--status-danger)]/30'
                }`}
                title="Intraday profit/loss change since market open / last close"
              >
                Today: {alpacaAccount.day_pnl >= 0 ? '+' : ''}
                {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(alpacaAccount.day_pnl)}
                {alpacaAccount.day_pnl_pct !== undefined && ` (${(alpacaAccount.day_pnl_pct * 100).toFixed(2)}%)`}
              </span>
            )}

            {alpacaAccount?.total_unrealized_pl !== undefined && (
              <span
                data-testid="alpaca-unrealized-pnl"
                className={`px-2 py-0.5 border text-xs font-mono font-bold rounded ${
                  alpacaAccount.total_unrealized_pl >= 0
                    ? 'bg-[var(--status-safe)]/10 text-[var(--status-safe)] border-[var(--status-safe)]/30'
                    : 'bg-[var(--status-danger)]/10 text-[var(--status-danger)] border-[var(--status-danger)]/30'
                }`}
                title="Cumulative unrealized profit/loss across all holdings"
              >
                Total P&L: {alpacaAccount.total_unrealized_pl >= 0 ? '+' : ''}
                {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(alpacaAccount.total_unrealized_pl)}
              </span>
            )}

            {alpacaAccount?.long_market_value !== undefined && (
              <span
                data-testid="alpaca-holdings-value"
                className="px-2 py-0.5 bg-[var(--bg-subtle)] text-[var(--text-main)] border border-[var(--border-color)] text-xs font-mono rounded"
                title="Long equity market value and active positions count"
              >
                Holdings: {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(alpacaAccount.long_market_value)}
                {alpacaAccount.positions_count !== undefined && ` (${alpacaAccount.positions_count})`}
              </span>
            )}

            {alpacaAccount && (
              <span
                data-testid="alpaca-live-cash"
                className="px-2 py-0.5 bg-[var(--bg-subtle)] text-[var(--text-muted)] border border-[var(--border-color)] text-xs font-mono rounded"
              >
                Cash: {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(alpacaAccount.cash)}
              </span>
            )}

            {alpacaAccount?.buying_power !== undefined && (
              <span
                data-testid="alpaca-live-bp"
                className="hidden md:inline-block px-2 py-0.5 bg-[var(--bg-subtle)] text-[var(--brand-spruce)] border border-[var(--border-color)] text-xs font-mono rounded"
              >
                BP: {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(alpacaAccount.buying_power)}
              </span>
            )}

            {alpacaAccount?.maintenance_margin !== undefined && alpacaAccount.maintenance_margin > 0 && (
              <span
                data-testid="alpaca-margin-info"
                className="hidden lg:inline-block px-2 py-0.5 bg-[var(--bg-subtle)] text-[var(--text-muted)] border border-[var(--border-color)] text-xs font-mono rounded"
                title="Maintenance margin and SMA"
              >
                Margin: {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(alpacaAccount.maintenance_margin)}
                {alpacaAccount.sma !== undefined && ` • SMA: ${new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(alpacaAccount.sma)}`}
              </span>
            )}

            {alpacaAccount?.multiplier && (
              <span
                data-testid="alpaca-account-type"
                className="hidden xl:inline-block px-1.5 py-0.5 text-[10px] font-mono text-[var(--brand-teal)] bg-[var(--bg-subtle)] border border-[var(--border-color)] rounded"
              >
                Margin {alpacaAccount.multiplier}x
              </span>
            )}

            {(alpacaAccount?.account_id || activeId) && (
              <span
                data-testid="alpaca-uuid-badge"
                className="hidden sm:inline-block px-2 py-0.5 text-[10px] font-mono text-[var(--text-muted)] bg-[var(--bg-subtle)] border border-[var(--border-color)] rounded truncate max-w-[160px]"
                title={alpacaAccount?.account_id || activeId}
              >
                ID: {alpacaAccount?.account_id || activeId}
              </span>
            )}

            {alpacaAccount?.status && (
              <span className="px-1.5 py-0.5 text-[10px] font-mono font-semibold bg-[var(--status-safe)]/10 text-[var(--status-safe)] border border-[var(--status-safe)]/30 rounded uppercase">
                {alpacaAccount.status}
              </span>
            )}

            {isEditingId ? (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (inputId.trim()) {
                    setSearchParams({ account_id: inputId.trim() });
                  } else {
                    setSearchParams({});
                  }
                  setIsEditingId(false);
                }}
                className="flex items-center gap-1"
              >
                <input
                  type="text"
                  value={inputId}
                  onChange={(e) => setInputId(e.target.value)}
                  placeholder="Enter Account ID / Number"
                  className="px-2 py-0.5 text-xs font-mono bg-[var(--bg-card)] border border-[var(--brand-spruce)] rounded text-[var(--text-main)] w-48 focus:outline-none"
                  autoFocus
                  data-testid="input-account-id-inline"
                />
                <button
                  type="submit"
                  data-testid="submit-account-id-btn"
                  className="px-2 py-0.5 text-xs font-mono bg-[var(--brand-spruce)] text-white rounded hover:bg-[#143225]"
                >
                  Set
                </button>
                <button
                  type="button"
                  onClick={() => setIsEditingId(false)}
                  className="px-2 py-0.5 text-xs font-mono text-[var(--text-muted)] hover:text-[var(--text-main)]"
                >
                  Cancel
                </button>
              </form>
            ) : (
              <button
                type="button"
                data-testid="switch-account-btn"
                onClick={() => {
                  setInputId(providedId || alpacaAccount?.account_number || '');
                  setIsEditingId(true);
                }}
                className="text-[11px] font-mono text-[var(--brand-teal)] hover:underline ml-1"
              >
                {activeId ? '[Change ID]' : '[Provide ID]'}
              </button>
            )}

            {!activeId && !isEditingId && (
              <button
                type="button"
                data-testid="quick-load-btn"
                onClick={() => setSearchParams({ account_id: 'PA3C0P4T6AJE' })}
                className="text-[11px] font-mono text-[var(--text-muted)] hover:text-[var(--brand-teal)] hover:underline"
                title="Load default paper account PA3C0P4T6AJE"
              >
                [Load PA3C0P4T6AJE]
              </button>
            )}

            {providedId && (
              <button
                type="button"
                data-testid="clear-account-btn"
                onClick={() => setSearchParams({})}
                className="text-[11px] font-mono text-[var(--text-muted)] hover:text-[var(--status-danger)]"
                title="Reset to default view"
              >
                [Reset]
              </button>
            )}
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
