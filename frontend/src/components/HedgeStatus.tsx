import React from 'react';
import { Shield, ShieldAlert, ShieldCheck, RefreshCw, AlertCircle } from 'lucide-react';
import type { CurrentHedge, StrategyHypothesis } from '../api/types';

export interface HedgeStatusProps {
  currentHedge?: CurrentHedge | null;
  activeHypothesis?: StrategyHypothesis | null;
  isLoading?: boolean;
  error?: Error | null;
  className?: string;
}

export const HedgeStatus: React.FC<HedgeStatusProps> = ({
  currentHedge,
  activeHypothesis,
  isLoading = false,
  error = null,
  className = '',
}) => {
  const formatCurrency = (val?: number | null, prefixSign = false) => {
    if (val === undefined || val === null || Number.isNaN(val)) return '—';
    const sign = prefixSign && val > 0 ? '+' : '';
    const formatted = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0,
    }).format(val);
    return `${sign}${formatted}`;
  };

  const formatPercent = (val?: number | null) => {
    if (val === undefined || val === null || Number.isNaN(val)) return '—';
    return `${(val * 100).toFixed(1)}%`;
  };

  if (isLoading && !currentHedge && !activeHypothesis) {
    return (
      <div
        className={`p-6 border border-[var(--border-color)] bg-[var(--bg-card)] ${className}`}
        data-testid="hedge-status-loading"
      >
        <div className="flex items-center gap-2 text-xs font-mono text-[var(--text-muted)] animate-pulse">
          <RefreshCw className="w-4 h-4 animate-spin" />
          <span>Loading Active Hedge Status...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div
        className={`p-4 border border-[var(--status-danger)] bg-[var(--status-danger)]/10 text-xs font-mono text-[var(--status-danger)] flex items-center gap-2 ${className}`}
        data-testid="hedge-status-error"
      >
        <AlertCircle className="w-4 h-4 flex-shrink-0" />
        <span>Error loading hedge status: {error.message}</span>
      </div>
    );
  }

  const isHedged = currentHedge?.active || (currentHedge?.legs && currentHedge.legs.length > 0);
  const strategyName = currentHedge?.strategy_type || activeHypothesis?.strategy || (isHedged ? 'ACTIVE OVERLAY' : 'UNHEDGED');
  const protectionPct = currentHedge?.downside_protection_pct ?? activeHypothesis?.hedge_metrics?.downside_protection_pct;
  const cost = currentHedge?.cost ?? activeHypothesis?.cost ?? 0;
  const pnl = currentHedge?.unrealized_pnl;
  const expiration = currentHedge?.expiration || currentHedge?.legs?.[0]?.expiration || activeHypothesis?.legs?.[0]?.expiration;

  return (
    <div
      className={`border border-[var(--border-color)] bg-[var(--bg-card)] ${className}`}
      data-testid="hedge-status-panel"
    >
      {/* Header bar */}
      <div className="px-5 py-3.5 border-b border-[var(--border-color)] bg-[var(--bg-subtle)] flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {isHedged ? (
            <ShieldCheck className="w-5 h-5 text-[var(--status-safe)]" />
          ) : (
            <ShieldAlert className="w-5 h-5 text-[var(--status-warning)]" />
          )}
          <h2 className="text-sm font-serif font-bold text-[var(--text-main)] uppercase tracking-wide">
            Portfolio Overlay Status
          </h2>
        </div>
        <div className="flex items-center gap-2 font-mono text-xs">
          <span
            className={`px-2.5 py-0.5 border font-bold uppercase ${
              isHedged
                ? 'bg-[var(--status-safe)]/15 border-[var(--status-safe)] text-[var(--status-safe)]'
                : 'bg-[var(--status-warning)]/15 border-[var(--status-warning)] text-[var(--status-warning)]'
            }`}
            data-testid="hedge-state-badge"
          >
            {isHedged ? 'HEDGED' : 'UNHEDGED'}
          </span>
        </div>
      </div>

      {/* Main Content Body */}
      <div className="p-5">
        {!isHedged ? (
          <div className="space-y-3" data-testid="unhedged-view">
            <div className="flex items-start gap-3 p-4 bg-[var(--status-warning)]/10 border border-[var(--status-warning)]/30">
              <Shield className="w-5 h-5 text-[var(--status-warning)] flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-mono text-xs font-bold text-[var(--text-main)] uppercase">
                  No Active Overlay Position Detected
                </p>
                <p className="text-xs text-[var(--text-muted)] mt-1">
                  Portfolio is operating without options downside mitigation. Tail-risk events will reflect full delta market beta exposure.
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-4" data-testid="hedged-view">
            {/* KPI Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="p-3 border border-[var(--border-color)] bg-[var(--bg-main)]">
                <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block">Active Strategy</span>
                <span className="text-sm font-mono font-bold text-[var(--brand-spruce)]" data-testid="hedge-strategy">
                  {strategyName.replace(/_/g, ' ')}
                </span>
              </div>

              <div className="p-3 border border-[var(--border-color)] bg-[var(--bg-main)]">
                <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block">Downside Floor</span>
                <span className="text-sm font-mono font-bold text-[var(--status-safe)]" data-testid="hedge-protection">
                  {formatPercent(protectionPct)}
                </span>
              </div>

              <div className="p-3 border border-[var(--border-color)] bg-[var(--bg-main)]">
                <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block">Hedge Cost Basis</span>
                <span className="text-sm font-mono font-bold text-[var(--text-main)]" data-testid="hedge-cost">
                  {formatCurrency(cost)}
                </span>
              </div>

              <div className="p-3 border border-[var(--border-color)] bg-[var(--bg-main)]">
                <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block">Expiration Date</span>
                <span className="text-sm font-mono font-bold text-[var(--brand-gold)]" data-testid="hedge-expiration">
                  {expiration || '—'}
                </span>
              </div>
            </div>

            {/* PnL & Legs Details */}
            {pnl !== undefined && pnl !== null && (
              <div className="flex items-center justify-between p-3 bg-[var(--bg-subtle)] border border-[var(--border-color)] text-xs font-mono">
                <span className="text-[var(--text-muted)] uppercase">Overlay Unrealized P&L:</span>
                <span
                  className={`font-bold ${
                    pnl >= 0 ? 'text-[var(--status-safe)]' : 'text-[var(--status-danger)]'
                  }`}
                  data-testid="hedge-pnl"
                >
                  {formatCurrency(pnl, true)}
                </span>
              </div>
            )}

            {currentHedge?.legs && currentHedge.legs.length > 0 && (
              <div className="border border-[var(--border-color)] overflow-x-auto">
                <table className="w-full text-left font-mono text-xs" data-testid="hedge-legs-table">
                  <thead className="bg-[var(--bg-subtle)] border-b border-[var(--border-color)] text-[10px] text-[var(--text-muted)] uppercase">
                    <tr>
                      <th className="p-2">Underlying</th>
                      <th className="p-2">Side</th>
                      <th className="p-2">Right</th>
                      <th className="p-2 text-right">Strike</th>
                      <th className="p-2">Expiration</th>
                      <th className="p-2 text-right">Qty</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border-color)]">
                    {currentHedge.legs.map((leg, idx) => (
                      <tr key={idx} className="hover:bg-[var(--bg-subtle)]/30">
                        <td className="p-2 font-bold">{leg.underlying}</td>
                        <td className="p-2">
                          <span
                            className={`px-1.5 py-0.5 text-[10px] font-bold ${
                              leg.side === 'BUY'
                                ? 'bg-[var(--status-safe)]/10 text-[var(--status-safe)]'
                                : 'bg-[var(--status-warning)]/10 text-[var(--status-warning)]'
                            }`}
                          >
                            {leg.side}
                          </span>
                        </td>
                        <td className="p-2 text-[var(--brand-spruce)] font-bold">{leg.right}</td>
                        <td className="p-2 text-right font-bold">${leg.strike.toFixed(2)}</td>
                        <td className="p-2 text-[var(--text-muted)]">{leg.expiration}</td>
                        <td className="p-2 text-right font-bold">{leg.quantity}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
