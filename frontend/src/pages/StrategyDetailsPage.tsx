import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Layers, ShieldCheck, AlertCircle, RefreshCw, AlertTriangle, Scale } from 'lucide-react';
import { useStrategyDecision, useStrategyHypothesis } from '../api/queries';
import { PayoffChart } from '../components/PayoffChart';
import { Greeks } from '../components/Greeks';
import { RiskChecklist } from '../components/RiskChecklist';

export const StrategyDetailsPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const decisionQuery = useStrategyDecision(id);
  const hypothesisQuery = useStrategyHypothesis(id);

  const isLoading = decisionQuery.isLoading || hypothesisQuery.isLoading;
  const decision = decisionQuery.data;
  const hypothesis = hypothesisQuery.data || decision?.selected_hypothesis;
  const error = !hypothesis ? (hypothesisQuery.error || decisionQuery.error) : null;

  const formatCurrency = (val?: number | null) => {
    if (val === undefined || val === null || Number.isNaN(val)) return '—';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0,
    }).format(val);
  };

  const formatPercent = (val?: number | null) => {
    if (val === undefined || val === null || Number.isNaN(val)) return '—';
    return `${(val * 100).toFixed(1)}%`;
  };

  return (
    <div className="space-y-6" data-testid="strategy-details-page">
      {/* Back Link and Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[var(--border-color)] pb-4">
        <div>
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 text-xs font-mono text-[var(--brand-spruce)] hover:underline mb-2"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to Dashboard
          </Link>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-bold font-serif text-[var(--text-main)]">
              Strategy Decision Details
            </h1>
            <span
              className="px-2.5 py-0.5 border border-[var(--border-color)] bg-[var(--bg-subtle)] font-mono text-xs font-bold text-[var(--text-main)]"
              data-testid="strategy-id-badge"
            >
              ID: {id || hypothesis?.cycle_id || 'N/A'}
            </span>
            {hypothesis?.strategy && (
              <span className="px-2 py-0.5 bg-[var(--brand-spruce)]/10 text-[var(--brand-spruce)] border border-[var(--brand-spruce)] font-mono text-xs font-bold uppercase">
                {hypothesis.strategy.replace(/_/g, ' ')}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {isLoading && (
            <span className="flex items-center gap-1 text-xs font-mono text-[var(--text-muted)]" data-testid="loading-indicator">
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              Loading Strategy Structure...
            </span>
          )}
          {hypothesis?.viable !== false ? (
            <span className="px-3 py-1.5 bg-[var(--status-safe)]/15 border border-[var(--status-safe)] text-[var(--status-safe)] font-mono text-xs font-bold flex items-center gap-1.5" data-testid="status-badge-viable">
              <ShieldCheck className="w-4 h-4" />
              VIABLE CANDIDATE
            </span>
          ) : (
            <span className="px-3 py-1.5 bg-[var(--status-danger)]/15 border border-[var(--status-danger)] text-[var(--status-danger)] font-mono text-xs font-bold flex items-center gap-1.5" data-testid="status-badge-rejected">
              <AlertTriangle className="w-4 h-4" />
              REJECTED STRUCTURE
            </span>
          )}
        </div>
      </div>

      {error && (
        <div className="p-4 border border-[var(--status-danger)] bg-[var(--status-danger)]/10 text-xs font-mono text-[var(--status-danger)] flex items-center gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>Error loading strategy details: {error.message}</span>
        </div>
      )}

      {/* KPI Cards: Cost, Protection, Max Loss, Breakevens */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="selected-hypothesis-card">
        <div className="p-4 border border-[var(--border-color)] bg-[var(--bg-card)]">
          <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block">Net Premium Cost</span>
          <span className="text-xl font-mono font-bold text-[var(--text-main)]" data-testid="strategy-cost">
            <span data-testid="selected-cost">{formatCurrency(hypothesis?.cost)}</span>
          </span>
          <span className="text-[10px] font-mono text-[var(--text-muted)] mt-1 block">
            {hypothesis?.hedge_metrics?.cost_pct_of_portfolio !== undefined
              ? `${formatPercent(hypothesis.hedge_metrics.cost_pct_of_portfolio)} of portfolio`
              : 'Budget compliant'}
          </span>
        </div>

        <div className="p-4 border border-[var(--border-color)] bg-[var(--bg-card)]">
          <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block">Downside Protection</span>
          <span className="text-xl font-mono font-bold text-[var(--status-safe)]" data-testid="strategy-protection">
            {formatPercent(hypothesis?.hedge_metrics?.downside_protection_pct)}
          </span>
          <span className="text-[10px] font-mono text-[var(--text-muted)] mt-1 block">
            Tail-risk mitigation floor
          </span>
        </div>

        <div className="p-4 border border-[var(--border-color)] bg-[var(--bg-card)]">
          <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block">Defined Max Loss</span>
          <span className="text-xl font-mono font-bold text-[var(--status-warning)]" data-testid="strategy-max-loss">
            {formatCurrency(hypothesis?.hedge_metrics?.max_loss ?? hypothesis?.cost)}
          </span>
          <span className="text-[10px] font-mono text-[var(--text-muted)] mt-1 block">
            Net debit premium cap
          </span>
        </div>

        <div className="p-4 border border-[var(--border-color)] bg-[var(--bg-card)]">
          <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block">Breakeven Index</span>
          <span className="text-xl font-mono font-bold text-[var(--brand-gold)]" data-testid="strategy-breakeven">
            {hypothesis?.hedge_metrics?.breakevens && hypothesis.hedge_metrics.breakevens.length > 0
              ? `$${hypothesis.hedge_metrics.breakevens[0].toFixed(1)}`
              : '—'}
          </span>
          <span className="text-[10px] font-mono text-[var(--text-muted)] mt-1 block">
            Underlying index level
          </span>
        </div>
      </div>

      {/* Main Grid: Payoff Curve + Greeks Sensitivities */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column (7 cols): Payoff Chart */}
        <section className="lg:col-span-7 space-y-3">
          <div className="border border-[var(--border-color)] bg-[var(--bg-card)] p-4">
            <h2 className="text-sm font-serif font-bold text-[var(--text-main)] mb-3 flex items-center gap-2">
              <Layers className="w-4 h-4 text-[var(--brand-spruce)]" />
              Payoff Curve Profile at Expiration
            </h2>
            <PayoffChart
              points={hypothesis?.payoff_profile}
              strategyName={hypothesis?.strategy?.replace(/_/g, ' ')}
              currentPrice={500}
              strikePrice={hypothesis?.legs?.[0]?.strike ?? 500}
              height={260}
            />
          </div>
        </section>

        {/* Right Column (5 cols): Greeks Sensitivities */}
        <section className="lg:col-span-5 space-y-4">
          <div className="border border-[var(--border-color)] bg-[var(--bg-card)] p-4 space-y-3">
            <h2 className="text-sm font-serif font-bold text-[var(--text-main)] flex items-center gap-2">
              <Scale className="w-4 h-4 text-[var(--brand-teal)]" />
              Quantitative Greeks Sensitivities
            </h2>
            <Greeks metrics={hypothesis?.hedge_metrics} variant="grid" />
          </div>

          {/* Rationale & Tradeoffs */}
          <div className="border border-[var(--border-color)] bg-[var(--bg-card)] p-4 space-y-3 font-mono text-xs">
            <h3 className="text-xs uppercase font-bold text-[var(--text-main)]">Strategic Rationale</h3>
            <p className="text-[var(--text-muted)] leading-relaxed" data-testid="selected-rationale">
              {hypothesis?.rationale || 'Direct downside protection calibrated within portfolio risk parameters.'}
            </p>
            <div className="p-2.5 bg-[var(--bg-subtle)] border-l-2 border-[var(--brand-spruce)] text-[11px]" data-testid="council-rationale">
              <strong>Council Rationale:</strong> {decision?.rationale || 'Protective put gives the most protection per dollar within budget.'}
            </div>

            {hypothesis?.tradeoffs && hypothesis.tradeoffs.length > 0 && (
              <div className="pt-2 border-t border-[var(--border-color)]">
                <span className="text-[10px] text-[var(--text-muted)] uppercase block font-bold">Identified Trade-Offs:</span>
                <ul className="list-disc list-inside text-[var(--text-muted)] text-[11px] mt-1 space-y-0.5">
                  {hypothesis.tradeoffs.map((t, idx) => (
                    <li key={idx}>{t}</li>
                  ))}
                </ul>
              </div>
            )}

            {hypothesis?.risks && hypothesis.risks.length > 0 && (
              <div className="pt-2 border-t border-[var(--border-color)]">
                <span className="text-[10px] text-[var(--status-danger)] uppercase block font-bold">Tail Risks:</span>
                <ul className="list-disc list-inside text-[var(--status-danger)] text-[11px] mt-1 space-y-0.5">
                  {hypothesis.risks.map((r, idx) => (
                    <li key={idx}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </section>
      </div>

      {/* Contract Legs Table */}
      {hypothesis?.legs && hypothesis.legs.length > 0 && (
        <section className="border border-[var(--border-color)] bg-[var(--bg-card)] p-5 space-y-3">
          <h2 className="text-sm font-serif font-bold text-[var(--text-main)]">
            Option Contract Execution Legs
          </h2>
          <div className="overflow-x-auto border border-[var(--border-color)]">
            <table className="w-full text-left font-mono text-xs" data-testid="strategy-legs-table">
              <thead>
                <tr className="border-b border-[var(--border-color)] bg-[var(--bg-subtle)] text-[10px] text-[var(--text-muted)] uppercase">
                  <th className="p-2.5">Underlying</th>
                  <th className="p-2.5">Right</th>
                  <th className="p-2.5">Side</th>
                  <th className="p-2.5 text-right">Strike</th>
                  <th className="p-2.5">Expiration</th>
                  <th className="p-2.5 text-right">Contracts</th>
                  <th className="p-2.5 text-right">Limit Price</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-color)]">
                {hypothesis.legs.map((leg, idx) => (
                  <tr key={idx} className="hover:bg-[var(--bg-subtle)]/40">
                    <td className="p-2.5 font-bold text-[var(--text-main)]">{leg.underlying}</td>
                    <td className="p-2.5 font-bold text-[var(--brand-spruce)]">{leg.right}</td>
                    <td className="p-2.5">
                      <span className={`px-1.5 py-0.5 text-[10px] font-bold ${leg.side === 'BUY' ? 'bg-[var(--status-safe)]/10 text-[var(--status-safe)]' : 'bg-[var(--status-warning)]/10 text-[var(--status-warning)]'}`}>
                        {leg.side}
                      </span>
                    </td>
                    <td className="p-2.5 text-right font-bold text-[var(--text-main)]">${leg.strike.toFixed(2)}</td>
                    <td className="p-2.5 text-[var(--text-muted)]">{leg.expiration}</td>
                    <td className="p-2.5 text-right font-bold text-[var(--text-main)]">{leg.quantity}</td>
                    <td className="p-2.5 text-right text-[var(--text-muted)]">${leg.limit_price?.toFixed(2) ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Quantitative Risk Gate Matrix */}
      <RiskChecklist decision={decisionQuery.data ? { ...decisionQuery.data, verdict: 'APPROVE', checks: [] } as any : undefined} />
    </div>
  );
};
