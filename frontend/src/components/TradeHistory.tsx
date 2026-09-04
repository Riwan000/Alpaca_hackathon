import React, { useState } from 'react';

export interface TradeLeg {
  symbol: string;
  qty: number;
  price: number;
  side?: string;
  slippage?: number;
}

export interface TradeItem {
  id: number | string;
  cycle_id: string;
  broker_order_id?: string;
  order_class: string;
  status: string;
  submitted_at: string;
  cost: number;
  legs: TradeLeg[];
}

export interface TradeHistoryProps {
  trades?: TradeItem[];
  onSelectTrade?: (trade: TradeItem) => void;
  isLoading?: boolean;
}

export const TradeHistory: React.FC<TradeHistoryProps> = ({
  trades = [],
  onSelectTrade,
  isLoading = false,
}) => {
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc');

  if (isLoading) {
    return (
      <div data-testid="trade-history-loading" className="p-5 bg-[var(--bg-card)] border border-[var(--border-color)] rounded-lg animate-pulse">
        <div className="h-6 bg-[var(--bg-subtle)] rounded w-1/4 mb-4"></div>
        <div className="space-y-3">
          <div className="h-16 bg-[var(--bg-subtle)] rounded"></div>
          <div className="h-16 bg-[var(--bg-subtle)] rounded"></div>
        </div>
      </div>
    );
  }

  const sortedTrades = [...trades].sort((a, b) => {
    const timeA = new Date(a.submitted_at).getTime();
    const timeB = new Date(b.submitted_at).getTime();
    return sortOrder === 'desc' ? timeB - timeA : timeA - timeB;
  });

  const getStatusBadge = (status: string) => {
    switch (status.toUpperCase()) {
      case 'FILLED':
        return 'bg-[var(--status-safe)]/10 text-[var(--status-safe)] border-[var(--status-safe)]/30';
      case 'SUBMITTED':
      case 'PENDING':
        return 'bg-blue-950 text-blue-400 border-blue-800';
      case 'CANCELLED':
      case 'EXPIRED':
        return 'bg-[var(--bg-subtle)] text-[var(--text-muted)] border-[var(--border-dark)]';
      case 'REJECTED':
      case 'FAILED':
      default:
        return 'bg-[var(--status-danger)]/10 text-[var(--status-danger)] border-[var(--status-danger)]/30';
    }
  };

  return (
    <div data-testid="trade-history" className="bg-[var(--bg-card)] border border-[var(--border-color)] rounded-lg p-5">
      <div className="flex items-center justify-between pb-3 border-b border-[var(--border-color)] mb-4">
        <div>
          <h2 className="text-lg font-semibold text-[var(--text-main)] tracking-wide">Trade History & Fills</h2>
          <p className="text-xs text-[var(--text-muted)]">Chronological execution audit trail across option and equity orders</p>
        </div>
        <div className="flex items-center space-x-3">
          <button
            type="button"
            data-testid="sort-date-btn"
            onClick={() => setSortOrder((prev) => (prev === 'desc' ? 'asc' : 'desc'))}
            className="text-xs font-mono px-2.5 py-1 rounded bg-[var(--bg-subtle)] hover:bg-[var(--bg-subtle-hover)] text-[var(--text-main)] border border-[var(--border-dark)] transition-colors flex items-center"
          >
            <span>Date: {sortOrder === 'desc' ? 'Newest â†“' : 'Oldest â†‘'}</span>
          </button>
          <span className="text-xs font-mono text-[var(--text-muted)]">
            {trades.length} Trade{trades.length === 1 ? '' : 's'}
          </span>
        </div>
      </div>

      {sortedTrades.length === 0 ? (
        <div data-testid="empty-trades" className="p-8 text-center text-[var(--text-muted)] text-sm border border-dashed border-[var(--border-color)] rounded-md">
          No historical trades executed yet.
        </div>
      ) : (
        <div className="divide-y divide-[var(--border-color)]/80 border border-[var(--border-color)] rounded-lg overflow-hidden bg-[var(--bg-subtle)]/40">
          {sortedTrades.map((trade) => (
            <div
              key={trade.id}
              data-testid="trade-row"
              onClick={() => onSelectTrade?.(trade)}
              className={`p-4 hover:bg-[var(--bg-subtle-hover)] transition-colors ${
                onSelectTrade ? 'cursor-pointer' : ''
              }`}
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                <div className="flex items-center space-x-2.5">
                  <span
                    data-testid="trade-status-badge"
                    className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-semibold border ${getStatusBadge(
                      trade.status
                    )}`}
                  >
                    {trade.status}
                  </span>
                  <span className="font-mono text-xs font-semibold text-[var(--text-main)]">
                    Class: <strong className="text-cyan-400">{trade.order_class}</strong>
                  </span>
                  <span className="text-xs font-mono text-[var(--text-muted)]">Cycle: {trade.cycle_id}</span>
                </div>

                <div className="flex items-center space-x-3 text-xs font-mono">
                  <span className="text-[var(--text-muted)]">
                    Cost: <strong className="text-[var(--text-main)]">${trade.cost.toLocaleString(undefined, { minimumFractionDigits: 2 })}</strong>
                  </span>
                  <span className="text-[var(--text-muted)]">
                    {new Date(trade.submitted_at).toLocaleString([], {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                </div>
              </div>

              {/* Legs summary */}
              <div className="space-y-1 mt-2">
                {trade.legs.map((leg, idx) => (
                  <div key={idx} className="text-xs font-mono flex items-center justify-between p-2 rounded bg-[var(--bg-card)]/60 border border-[var(--border-color)]/60">
                    <span className="text-[var(--brand-teal)] font-semibold">{leg.symbol}</span>
                    <span className="text-[var(--text-main)]">
                      Qty: {leg.qty} @ ${leg.price.toFixed(2)}
                    </span>
                    {leg.slippage !== undefined && (
                      <span className="text-[11px] text-[var(--text-muted)]">
                        Slippage: {leg.slippage >= 0 ? '+' : ''}${leg.slippage.toFixed(2)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
