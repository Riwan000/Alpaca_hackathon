import React from 'react';

export interface ReassessmentItem {
  id: number;
  cycle_id: string;
  trigger?: string;
  outcome: string;
  reason: string;
  created_at: string;
  delta?: number;
  before_hedge_ratio?: number;
  after_hedge_ratio?: number;
}

export interface ReassessmentHistoryProps {
  reassessments?: ReassessmentItem[];
  isLoading?: boolean;
}

const getOutcomeBadgeStyle = (outcome: string) => {
  switch (outcome.toUpperCase()) {
    case 'DECREASE':
    case 'REMOVE':
      return 'bg-[var(--status-safe)]/10 text-[var(--status-safe)] border-[var(--status-safe)]/30';
    case 'INCREASE':
    case 'NEW_HEDGE':
      return 'bg-blue-950 text-blue-400 border-blue-800';
    case 'REPLACE':
      return 'bg-amber-950 text-amber-400 border-[var(--status-warning)]/40';
    case 'MAINTAIN':
    case 'NO_TRADE':
    default:
      return 'bg-[var(--bg-subtle)] text-[var(--text-main)] border-[var(--border-dark)]';
  }
};

export const ReassessmentHistory: React.FC<ReassessmentHistoryProps> = ({
  reassessments = [],
  isLoading = false,
}) => {
  if (isLoading) {
    return (
      <div data-testid="reassessment-history-loading" className="p-4 bg-[var(--bg-card)] border border-[var(--border-color)] rounded-lg animate-pulse">
        <div className="h-6 bg-[var(--bg-subtle)] rounded w-1/3 mb-4"></div>
        <div className="space-y-3">
          <div className="h-14 bg-[var(--bg-subtle)] rounded"></div>
          <div className="h-14 bg-[var(--bg-subtle)] rounded"></div>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="reassessment-history" className="bg-[var(--bg-card)] border border-[var(--border-color)] rounded-lg p-5">
      <div className="flex items-center justify-between pb-3 border-b border-[var(--border-color)] mb-4">
        <div>
          <h3 className="text-base font-semibold text-[var(--text-main)]">Reassessment & Adaptation History</h3>
          <p className="text-xs text-[var(--text-muted)]">Level-2 intelligent reassessments linking triggers to hedge ratio adjustments</p>
        </div>
        <span className="text-xs font-mono text-[var(--text-muted)]">{reassessments.length} Record{reassessments.length === 1 ? '' : 's'}</span>
      </div>

      {reassessments.length === 0 ? (
        <div data-testid="empty-reassessments" className="p-6 text-center text-[var(--text-muted)] text-sm border border-dashed border-[var(--border-color)] rounded-md">
          No reassessment events recorded yet.
        </div>
      ) : (
        <div className="space-y-3">
          {reassessments.map((item) => (
            <div
              key={item.id}
              data-testid="reassessment-row"
              className="p-4 rounded-lg bg-[var(--bg-subtle)]/70 border border-[var(--border-color)] hover:border-[var(--border-dark)] transition-colors"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                <div className="flex items-center space-x-2">
                  <span
                    data-testid="outcome-badge"
                    className={`inline-flex items-center px-2.5 py-0.5 rounded text-xs font-mono font-semibold border ${getOutcomeBadgeStyle(
                      item.outcome
                    )}`}
                  >
                    {item.outcome}
                  </span>
                  {item.trigger && (
                    <span className="text-xs text-[var(--text-muted)] font-mono">
                      Trigger: <strong className="text-amber-400">{item.trigger}</strong>
                    </span>
                  )}
                  <span className="text-xs text-[var(--text-muted)] font-mono">({item.cycle_id})</span>
                </div>

                {item.delta !== undefined && item.delta !== null && (
                  <div
                    data-testid="delta-badge"
                    className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${
                      item.delta < 0
                        ? 'text-[var(--status-safe)] bg-[var(--status-safe)]/10 border border-emerald-900/60'
                        : item.delta > 0
                        ? 'text-blue-400 bg-blue-950/40 border border-blue-900/60'
                        : 'text-[var(--text-muted)] bg-[var(--bg-subtle)]'
                    }`}
                  >
                    Hedge Delta: {item.delta > 0 ? '+' : ''}
                    {(item.delta * 100).toFixed(1)}%
                    {item.before_hedge_ratio !== undefined && item.after_hedge_ratio !== undefined && (
                      <span className="text-[var(--text-muted)] font-normal ml-1">
                        {' '}({(item.before_hedge_ratio * 100).toFixed(0)}% â†’ {(item.after_hedge_ratio * 100).toFixed(0)}%)
                      </span>
                    )}
                  </div>
                )}
              </div>

              <p className="text-xs text-[var(--text-main)] mb-1">{item.reason}</p>

              <div className="text-[11px] text-[var(--text-muted)] font-mono text-right">
                {new Date(item.created_at).toLocaleString([], {
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
