import React from 'react';
import { Link } from 'react-router-dom';
import { BarChart3, CheckCircle2, ArrowUpRight, AlertCircle } from 'lucide-react';
import type { StrategyDecision, CurrentHedge, HedgeObjective } from '../api/types';

export interface RecommendationProps {
  decision?: StrategyDecision | null;
  currentHedge?: CurrentHedge | null;
  objective?: HedgeObjective | null;
  isLoading?: boolean;
  error?: Error | null;
  className?: string;
}

export const Recommendation: React.FC<RecommendationProps> = ({
  decision,
  currentHedge,
  objective,
  isLoading = false,
  error = null,
  className = '',
}) => {
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

  if (isLoading && !decision) {
    return (
      <div
        className={`border border-[var(--border-color)] bg-[var(--bg-card)] p-5 space-y-4 ${className}`}
        data-testid="recommendation-loading"
      >
        <div className="h-5 w-48 bg-[var(--bg-subtle)] animate-pulse" />
        <div className="h-32 bg-[var(--bg-subtle)] animate-pulse" />
      </div>
    );
  }

  if (error) {
    return (
      <div
        className={`border border-[var(--status-danger)] bg-[var(--status-danger)]/5 p-5 space-y-2 ${className}`}
        data-testid="recommendation-error"
      >
        <h2 className="text-sm font-serif font-bold text-[var(--status-danger)] flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          Strategy Recommendation Unavailable
        </h2>
        <p className="text-xs font-mono text-[var(--text-muted)]">{error.message}</p>
      </div>
    );
  }

  const selectedHypo = decision?.selected_hypothesis;
  const currentRatio = currentHedge?.hedge_ratio ?? 0.0;
  const targetRatio = objective?.target_hedge_ratio ?? currentHedge?.target_hedge_ratio ?? 0.2;
  const hedgeGap = targetRatio - currentRatio;

  const actionVerb = decision?.decision || 'SELECT_STRATEGY';

  const getActionBadgeColor = (action: string) => {
    switch (action) {
      case 'SELECT_STRATEGY':
      case 'SELECT':
        return 'bg-[var(--brand-spruce)] text-white';
      case 'NO_TRADE':
        return 'bg-[var(--text-muted)] text-white';
      case 'REASSESS':
        return 'bg-[var(--status-warning)] text-white';
      default:
        return 'bg-[var(--brand-spruce)] text-white';
    }
  };

  return (
    <div
      className={`border-t-gold-accent border border-[var(--border-color)] bg-[var(--bg-card)] p-5 space-y-4 ${className}`}
      data-testid="recommendation-panel"
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[var(--border-color)] pb-3">
        <div>
          <h2 className="text-base font-serif font-bold text-[var(--text-main)] flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-[var(--brand-gold)]" />
            Strategy Recommendation
          </h2>
          <span className="text-xs font-mono text-[var(--text-muted)]">
            Optimal Multi-Leg Options Structure Selection
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`px-2.5 py-1 text-xs font-mono font-bold uppercase tracking-wider ${getActionBadgeColor(actionVerb)}`}
            data-testid="recommendation-action-badge"
          >
            {actionVerb}
          </span>
          <Link
            to={`/strategy/${decision?.cycle_id || 'selected'}`}
            className="px-2.5 py-1 bg-[var(--bg-subtle)] hover:bg-[var(--bg-subtle-hover)] border border-[var(--border-color)] text-xs font-mono text-[var(--text-main)] flex items-center gap-1 transition-colors"
            data-testid="inspect-strategy-link"
          >
            Inspect
            <ArrowUpRight className="w-3 h-3 text-[var(--brand-gold)]" />
          </Link>
        </div>
      </div>

      {/* Hedge Drift & Gap Gauge */}
      <div className="p-3 bg-[var(--bg-subtle)] border border-[var(--border-color)] grid grid-cols-3 gap-2 font-mono text-xs text-center">
        <div>
          <span className="text-[10px] text-[var(--text-muted)] uppercase block">Current Hedge</span>
          <span className="font-bold text-[var(--text-main)]" data-testid="current-hedge-ratio">
            {formatPercent(currentRatio)}
          </span>
        </div>
        <div>
          <span className="text-[10px] text-[var(--text-muted)] uppercase block">Target Hedge</span>
          <span className="font-bold text-[var(--brand-spruce)]" data-testid="target-hedge-ratio">
            {formatPercent(targetRatio)}
          </span>
        </div>
        <div>
          <span className="text-[10px] text-[var(--text-muted)] uppercase block">Hedge Gap / Drift</span>
          <span
            className={`font-bold ${Math.abs(hedgeGap) > 0.05 ? 'text-[var(--status-warning)]' : 'text-[var(--status-safe)]'}`}
            data-testid="hedge-gap"
          >
            {hedgeGap > 0 ? `+${formatPercent(hedgeGap)}` : formatPercent(hedgeGap)}
          </span>
        </div>
      </div>

      {/* Selected Strategy Details Card */}
      <div className="p-4 border border-[var(--brand-spruce)] bg-[var(--bg-subtle)]/60 space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-[var(--status-safe)] flex-shrink-0" />
            <span className="text-sm font-mono font-bold text-[var(--brand-spruce)]" data-testid="selected-strategy-title">
              <span data-testid="selected-strategy-name">
                {decision?.selected_strategy?.replace(/_/g, ' ') || 'NO STRATEGY SELECTED'}
              </span>
            </span>
          </div>
          {selectedHypo?.cost !== undefined && (
            <span
              className="text-xs font-mono font-bold text-[var(--status-safe)] bg-[var(--status-safe)]/10 px-2 py-0.5 border border-[var(--status-safe)] self-start sm:self-auto"
              data-testid="selected-strategy-cost"
            >
              Estimated Cost: <span data-testid="strategy-cost">{formatCurrency(selectedHypo.cost)}</span>
            </span>
          )}
        </div>

        <p className="text-xs text-[var(--text-muted)] leading-relaxed" data-testid="recommendation-rationale">
          {decision?.rationale || selectedHypo?.rationale || 'Quantitative evaluation complete across all strategy models.'}
        </p>

        {selectedHypo?.legs && selectedHypo.legs.length > 0 && (
          <div className="pt-2 border-t border-[var(--border-color)] space-y-1">
            <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block">Execution Legs:</span>
            {selectedHypo.legs.map((leg, idx) => (
              <div key={idx} className="flex justify-between font-mono text-xs text-[var(--text-main)]">
                <span>
                  <strong>{leg.side}</strong> {leg.quantity}x {leg.underlying} ${leg.strike} {leg.right}
                </span>
                <span className="text-[var(--text-muted)]">Exp: {leg.expiration}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
