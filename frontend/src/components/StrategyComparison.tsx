import React, { useState } from 'react';
import { Columns3, CheckCircle2, XCircle, AlertCircle, Info, ChevronDown, ChevronUp } from 'lucide-react';
import type { StrategyHypothesis, StrategyType, ComparisonRow } from '../api/types';

export interface StrategyComparisonProps {
  hypotheses?: StrategyHypothesis[];
  selectedStrategy?: StrategyType | null;
  comparisonRows?: ComparisonRow[];
  isLoading?: boolean;
  error?: Error | null;
  className?: string;
}

export const StrategyComparison: React.FC<StrategyComparisonProps> = ({
  hypotheses = [],
  selectedStrategy,
  comparisonRows = [],
  isLoading = false,
  error = null,
  className = '',
}) => {
  const [expandedRejection, setExpandedRejection] = useState<Record<string, boolean>>({});

  const toggleRejection = (stratKey: string) => {
    setExpandedRejection((prev) => ({
      ...prev,
      [stratKey]: !prev[stratKey],
    }));
  };

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

  if (isLoading && hypotheses.length === 0) {
    return (
      <div
        className={`border border-[var(--border-color)] bg-[var(--bg-card)] p-5 space-y-4 ${className}`}
        data-testid="strategy-comparison-loading"
      >
        <div className="h-5 w-48 bg-[var(--bg-subtle)] animate-pulse" />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-64 bg-[var(--bg-subtle)] animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div
        className={`border border-[var(--status-danger)] bg-[var(--status-danger)]/5 p-5 space-y-2 ${className}`}
        data-testid="strategy-comparison-error"
      >
        <h2 className="text-sm font-serif font-bold text-[var(--status-danger)] flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          Strategy Hypotheses Unavailable
        </h2>
        <p className="text-xs font-mono text-[var(--text-muted)]">{error.message}</p>
      </div>
    );
  }

  return (
    <div
      className={`border border-[var(--border-color)] bg-[var(--bg-card)] p-5 space-y-4 ${className}`}
      data-testid="strategy-comparison"
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[var(--border-color)] pb-3">
        <div>
          <h2 className="text-sm font-serif font-bold text-[var(--text-main)] flex items-center gap-2">
            <Columns3 className="w-4 h-4 text-[var(--brand-spruce)]" />
            Strategy Hypotheses Comparison
          </h2>
          <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase">
            Side-by-Side Model Architectures & Quantitative Trade-Offs
          </span>
        </div>
        <span className="text-[10px] font-mono text-[var(--text-muted)]">
          {hypotheses.length} CANDIDATE STRUCTURES
        </span>
      </div>

      {hypotheses.length === 0 ? (
        <div
          className="flex flex-col items-center justify-center py-8 border border-dashed border-[var(--border-color)] bg-[var(--bg-subtle)]/40 text-center text-xs font-mono text-[var(--text-muted)]"
          data-testid="strategy-comparison-empty"
        >
          <Info className="w-6 h-6 text-[var(--text-muted)] mb-2 opacity-60" />
          <span className="font-bold text-[var(--text-main)]">No Hypotheses Evaluated</span>
          <span>Generate candidate strategies to compare multi-leg payoff profiles.</span>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4" data-testid="hypotheses-grid">
          {hypotheses.map((hypo, idx) => {
            const isSelected = selectedStrategy === hypo.strategy;
            const isViable = hypo.viable;
            const compRow = comparisonRows.find((r) => r.strategy === hypo.strategy);
            const isRejectionExpanded = expandedRejection[hypo.strategy] ?? false;

            return (
              <div
                key={hypo.strategy || idx}
                className={`border p-4 flex flex-col justify-between transition-all relative ${
                  isSelected
                    ? 'border-[var(--brand-spruce)] bg-[var(--bg-subtle)]/50 shadow-sm ring-1 ring-[var(--brand-spruce)]'
                    : isViable
                    ? 'border-[var(--border-color)] bg-[var(--bg-card)]'
                    : 'border-[var(--border-color)] bg-[var(--bg-subtle)]/20 opacity-80'
                }`}
                data-testid={`hypothesis-card-${hypo.strategy}`}
              >
                {/* Card Header & Badges */}
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-2 border-b border-[var(--border-color)] pb-2">
                    <div>
                      <h3
                        className="text-xs font-mono font-bold text-[var(--text-main)] uppercase"
                        data-testid={`strategy-title-${hypo.strategy}`}
                      >
                        {hypo.strategy.replace(/_/g, ' ')}
                      </h3>
                      <span className="text-[10px] font-mono text-[var(--text-muted)] block">
                        {hypo.action}
                      </span>
                    </div>

                    {isSelected ? (
                      <span
                        className="px-2 py-0.5 bg-[var(--brand-spruce)] text-white text-[9px] font-mono font-bold flex items-center gap-1"
                        data-testid="selected-badge"
                      >
                        <CheckCircle2 className="w-3 h-3" /> SELECTED
                      </span>
                    ) : isViable ? (
                      <span
                        className="px-2 py-0.5 bg-[var(--status-safe)]/10 border border-[var(--status-safe)] text-[var(--status-safe)] text-[9px] font-mono font-bold"
                        data-testid="viable-badge"
                      >
                        VIABLE
                      </span>
                    ) : (
                      <span
                        className="px-2 py-0.5 bg-[var(--status-danger)]/10 border border-[var(--status-danger)] text-[var(--status-danger)] text-[9px] font-mono font-bold flex items-center gap-0.5"
                        data-testid="not-viable-badge"
                      >
                        <XCircle className="w-3 h-3" /> NOT VIABLE
                      </span>
                    )}
                  </div>

                  {/* Quantitative Metrics Matrix */}
                  <div className="space-y-1.5 font-mono text-xs pt-1">
                    <div className="flex justify-between">
                      <span className="text-[var(--text-muted)] text-[11px]">Premium Cost:</span>
                      <span className="font-bold text-[var(--text-main)]" data-testid={`cost-${hypo.strategy}`}>
                        {formatCurrency(hypo.cost)}
                      </span>
                    </div>

                    <div className="flex justify-between">
                      <span className="text-[var(--text-muted)] text-[11px]">Downside Protection:</span>
                      <span
                        className={`font-bold ${
                          (hypo.hedge_metrics?.downside_protection_pct ?? 0) > 0.7
                            ? 'text-[var(--status-safe)]'
                            : 'text-[var(--text-main)]'
                        }`}
                        data-testid={`protection-${hypo.strategy}`}
                      >
                        {formatPercent(hypo.hedge_metrics?.downside_protection_pct)}
                      </span>
                    </div>

                    <div className="flex justify-between">
                      <span className="text-[var(--text-muted)] text-[11px]">Max Loss:</span>
                      <span className="font-bold text-[var(--text-muted)]">
                        {hypo.hedge_metrics?.max_loss !== undefined
                          ? formatCurrency(hypo.hedge_metrics.max_loss)
                          : '—'}
                      </span>
                    </div>

                    <div className="flex justify-between">
                      <span className="text-[var(--text-muted)] text-[11px]">Net Delta (Δ):</span>
                      <span className="font-bold text-[var(--brand-teal)]">
                        {hypo.hedge_metrics?.net_delta != null
                          ? hypo.hedge_metrics.net_delta.toFixed(1)
                          : '—'}
                      </span>
                    </div>

                    {compRow?.score !== undefined && compRow.score !== null && (
                      <div className="flex justify-between pt-1 border-t border-dashed border-[var(--border-color)]">
                        <span className="text-[var(--text-muted)] text-[11px]">Score:</span>
                        <span className="font-bold text-[var(--brand-gold)]">
                          {(compRow.score * 100).toFixed(0)} / 100
                        </span>
                      </div>
                    )}
                  </div>

                  <p className="text-[11px] text-[var(--text-muted)] pt-2 leading-relaxed">
                    {hypo.rationale}
                  </p>
                </div>

                {/* Rejected Reason Expander / Disclosure (P4-FE-5) */}
                {!isViable && (hypo.rejection_reason || hypo.rejection_conditions?.length > 0) && (
                  <div
                    className="mt-3 pt-2 border-t border-[var(--border-color)] text-xs font-mono"
                    data-testid={`rejection-section-${hypo.strategy}`}
                  >
                    <button
                      onClick={() => toggleRejection(hypo.strategy)}
                      className="w-full flex items-center justify-between text-[10px] text-[var(--status-danger)] font-bold hover:underline py-1"
                      data-testid={`toggle-rejection-${hypo.strategy}`}
                    >
                      <span className="flex items-center gap-1">
                        <AlertCircle className="w-3 h-3" />
                        Rejection Reason
                      </span>
                      {isRejectionExpanded ? (
                        <ChevronUp className="w-3 h-3" />
                      ) : (
                        <ChevronDown className="w-3 h-3" />
                      )}
                    </button>

                    {isRejectionExpanded && (
                      <div
                        className="p-2 bg-[var(--status-danger)]/10 border border-[var(--status-danger)]/30 text-[10px] text-[var(--status-danger)] space-y-1 mt-1"
                        data-testid={`rejection-reason-${hypo.strategy}`}
                      >
                        {hypo.rejection_reason && (
                          <p>
                            <strong>Constraint Breach:</strong> {hypo.rejection_reason}
                          </p>
                        )}
                        {hypo.rejection_conditions && hypo.rejection_conditions.length > 0 && (
                          <p className="text-[9px] opacity-90">
                            <strong>Triggers:</strong> {hypo.rejection_conditions.join('; ')}
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
