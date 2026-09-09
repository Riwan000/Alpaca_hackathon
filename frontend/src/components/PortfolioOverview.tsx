import React from 'react';
import { Briefcase, TrendingUp, TrendingDown, RefreshCw, AlertCircle, Inbox } from 'lucide-react';
import type { PortfolioState } from '../api/types';

export interface PortfolioOverviewProps {
  portfolio?: PortfolioState | null;
  accountId?: string | null;
  accountNumber?: string | null;
  accountStatus?: string | null;
  dayPnl?: number | null;
  totalUnrealizedPnl?: number | null;
  isLoading?: boolean;
  error?: Error | null;
  onRefresh?: () => void;
  className?: string;
}

export const PortfolioOverview: React.FC<PortfolioOverviewProps> = ({
  portfolio,
  accountId,
  accountNumber,
  accountStatus,
  dayPnl,
  totalUnrealizedPnl,
  isLoading = false,
  error = null,
  onRefresh,
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

  if (isLoading && !portfolio) {
    return (
      <div
        className={`border border-[var(--border-color)] bg-[var(--bg-card)] p-6 space-y-4 ${className}`}
        data-testid="portfolio-overview-loading"
      >
        <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-3">
          <div className="h-5 w-40 bg-[var(--bg-subtle)] animate-pulse" />
          <div className="h-4 w-24 bg-[var(--bg-subtle)] animate-pulse" />
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-16 bg-[var(--bg-subtle)] animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div
        className={`border border-[var(--status-danger)] bg-[var(--status-danger)]/5 p-6 space-y-3 ${className}`}
        data-testid="portfolio-overview-error"
      >
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-serif font-bold text-[var(--status-danger)] flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            Portfolio Feed Unavailable
          </h2>
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="text-xs font-mono text-[var(--status-danger)] hover:underline flex items-center gap-1"
            >
              <RefreshCw className="w-3 h-3" /> Retry
            </button>
          )}
        </div>
        <p className="text-xs font-mono text-[var(--text-muted)]">
          {error.message || 'Failed to load portfolio snapshot from Alpaca broker service.'}
        </p>
      </div>
    );
  }

  const positions = portfolio?.positions ?? [];

  return (
    <div
      className={`border border-[var(--border-color)] bg-[var(--bg-card)] p-5 space-y-4 ${className}`}
      data-testid="portfolio-overview"
    >
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[var(--border-color)] pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-serif font-bold text-[var(--text-main)] flex items-center gap-2">
              <Briefcase className="w-4 h-4 text-[var(--brand-spruce)]" />
              Portfolio Holdings & Liquidity
            </h2>
            {(accountNumber || portfolio?.account_number) && (
              <span
                data-testid="alpaca-account-badge"
                className="px-2 py-0.5 bg-[var(--brand-spruce)]/10 text-[var(--brand-spruce)] border border-[var(--brand-spruce)]/30 text-[10px] font-mono font-semibold rounded"
                title={`Alpaca Account ID: ${accountId || portfolio?.account_id || accountNumber}`}
              >
                ACCOUNT: {accountNumber || portfolio?.account_number}
              </span>
            )}
            {accountStatus && (
              <span className="px-1.5 py-0.5 bg-[var(--status-safe)]/10 text-[var(--status-safe)] border border-[var(--status-safe)]/30 text-[9px] font-mono font-semibold rounded uppercase">
                {accountStatus}
              </span>
            )}
          </div>
          <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block mt-0.5">
            Alpaca Account Summary & Active Positions
            {(accountId || portfolio?.account_id) && ` • ID: ${accountId || portfolio?.account_id}`}
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs font-mono">
          <span className="text-[var(--text-muted)]">Total AUM:</span>
          <span className="font-bold text-[var(--text-main)]" data-testid="portfolio-total-value">
            {formatCurrency(portfolio?.total_value)}
          </span>
        </div>
      </div>

      {/* Summary KPI Ribbon */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        <div className="p-2.5 bg-[var(--bg-subtle)] border border-[var(--border-color)]">
          <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block">Cash Balance</span>
          <span className="text-sm font-mono font-bold text-[var(--text-main)]" data-testid="portfolio-cash">
            {formatCurrency(portfolio?.cash)}
          </span>
        </div>
        <div className="p-2.5 bg-[var(--bg-subtle)] border border-[var(--border-color)]">
          <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block">Gross Exposure</span>
          <span className="text-sm font-mono font-bold text-[var(--text-main)]" data-testid="portfolio-gross-exposure">
            {formatCurrency(portfolio?.gross_exposure ?? portfolio?.equity)}
          </span>
        </div>
        <div className="p-2.5 bg-[var(--bg-subtle)] border border-[var(--border-color)]">
          <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block">Net Exposure</span>
          <span className="text-sm font-mono font-bold text-[var(--text-main)]" data-testid="portfolio-net-exposure">
            {formatCurrency(portfolio?.net_exposure ?? portfolio?.equity)}
          </span>
        </div>
        <div className="p-2.5 bg-[var(--bg-subtle)] border border-[var(--border-color)]">
          <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block">Buying Power</span>
          <span className="text-sm font-mono font-bold text-[var(--brand-spruce)]" data-testid="portfolio-buying-power">
            {formatCurrency(portfolio?.buying_power)}
          </span>
        </div>
        <div className="p-2.5 bg-[var(--bg-subtle)] border border-[var(--border-color)]">
          <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block">Today's P&L</span>
          <span
            className={`text-sm font-mono font-bold ${
              (dayPnl ?? 0) >= 0 ? 'text-[var(--status-safe)]' : 'text-[var(--status-danger)]'
            }`}
            data-testid="portfolio-day-pnl"
          >
            {dayPnl !== undefined && dayPnl !== null ? formatCurrency(dayPnl, true) : '—'}
          </span>
        </div>
        <div className="p-2.5 bg-[var(--bg-subtle)] border border-[var(--border-color)]">
          <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block">Total P&L</span>
          <span
            className={`text-sm font-mono font-bold ${
              (totalUnrealizedPnl ?? 0) >= 0 ? 'text-[var(--status-safe)]' : 'text-[var(--status-danger)]'
            }`}
            data-testid="portfolio-total-pnl"
          >
            {totalUnrealizedPnl !== undefined && totalUnrealizedPnl !== null ? formatCurrency(totalUnrealizedPnl, true) : '—'}
          </span>
        </div>
      </div>

      {/* Holdings Table */}
      {positions.length === 0 ? (
        <div
          className="flex flex-col items-center justify-center py-10 border border-dashed border-[var(--border-color)] bg-[var(--bg-subtle)]/40 text-center text-xs font-mono text-[var(--text-muted)]"
          data-testid="portfolio-empty-state"
        >
          <Inbox className="w-8 h-8 text-[var(--text-muted)] mb-2 opacity-60" />
          <span className="font-bold text-[var(--text-main)]">No Active Positions</span>
          <span>Your portfolio is 100% in cash or no positions were detected in this snapshot.</span>
        </div>
      ) : (
        <div className="overflow-x-auto border border-[var(--border-color)]">
          <table className="w-full text-left font-mono text-xs" data-testid="holdings-table">
            <thead>
              <tr className="border-b border-[var(--border-color)] bg-[var(--bg-subtle)] text-[10px] text-[var(--text-muted)] uppercase">
                <th className="p-2.5">Symbol</th>
                <th className="p-2.5">Side</th>
                <th className="p-2.5 text-right">Qty</th>
                <th className="p-2.5 text-right">Current Price</th>
                <th className="p-2.5 text-right">Avg Cost</th>
                <th className="p-2.5 text-right">Market Value</th>
                <th className="p-2.5 text-right">Unrealized P&L</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border-color)]">
              {positions.map((pos, idx) => {
                const pnl = pos.unrealized_pl ?? 0;
                const isProfitable = pnl >= 0;
                return (
                  <tr key={`${pos.symbol}-${idx}`} className="hover:bg-[var(--bg-subtle)]/40 transition-colors">
                    <td className="p-2.5 font-bold text-[var(--text-main)]">
                      <div className="flex items-center gap-1.5">
                        <span>{pos.symbol}</span>
                        <span className="px-1.5 py-0.2 bg-[var(--bg-subtle)] text-[9px] border border-[var(--border-color)] text-[var(--text-muted)]">
                          {pos.asset_class || 'EQUITY'}
                        </span>
                      </div>
                    </td>
                    <td className="p-2.5">
                      <span className={`px-1.5 py-0.5 text-[10px] font-bold ${pos.side === 'SELL' ? 'bg-[var(--status-danger)]/10 text-[var(--status-danger)]' : 'bg-[var(--brand-spruce)]/10 text-[var(--brand-spruce)]'}`}>
                        {pos.side || 'BUY'}
                      </span>
                    </td>
                    <td className="p-2.5 text-right font-bold text-[var(--text-main)]">
                      {pos.qty.toLocaleString()}
                    </td>
                    <td className="p-2.5 text-right font-mono">
                      {pos.current_price !== undefined && pos.current_price !== null ? (
                        <div>
                          <span className="font-bold text-[var(--text-main)]">${pos.current_price.toFixed(2)}</span>
                          {pos.change_today !== undefined && pos.change_today !== null && (
                            <span
                              className={`block text-[10px] ${
                                pos.change_today >= 0 ? 'text-[var(--status-safe)]' : 'text-[var(--status-danger)]'
                              }`}
                            >
                              {pos.change_today >= 0 ? '+' : ''}
                              {(pos.change_today * 100).toFixed(2)}%
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-[var(--text-muted)]">—</span>
                      )}
                    </td>
                    <td className="p-2.5 text-right text-[var(--text-muted)]">
                      ${pos.avg_price.toFixed(2)}
                    </td>
                    <td className="p-2.5 text-right font-bold text-[var(--text-main)]">
                      {formatCurrency(pos.market_value)}
                    </td>
                    <td className="p-2.5 text-right">
                      <span
                        className={`inline-flex items-center gap-1 font-bold ${
                          isProfitable ? 'text-[var(--status-safe)]' : 'text-[var(--status-danger)]'
                        }`}
                      >
                        {isProfitable ? (
                          <TrendingUp className="w-3 h-3" />
                        ) : (
                          <TrendingDown className="w-3 h-3" />
                        )}
                        {formatCurrency(pnl, true)}
                      </span>
                      {pos.unrealized_plpc !== undefined && pos.unrealized_plpc !== null && (
                        <span
                          className={`block text-[10px] ${
                            pos.unrealized_plpc >= 0 ? 'text-[var(--status-safe)]' : 'text-[var(--status-danger)]'
                          }`}
                        >
                          {pos.unrealized_plpc >= 0 ? '+' : ''}
                          {(pos.unrealized_plpc * 100).toFixed(2)}%
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
