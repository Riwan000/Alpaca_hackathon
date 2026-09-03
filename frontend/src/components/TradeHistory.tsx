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
      <div data-testid="trade-history-loading" className="p-5 bg-slate-900 border border-slate-800 rounded-lg animate-pulse">
        <div className="h-6 bg-slate-800 rounded w-1/4 mb-4"></div>
        <div className="space-y-3">
          <div className="h-16 bg-slate-800 rounded"></div>
          <div className="h-16 bg-slate-800 rounded"></div>
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
        return 'bg-emerald-950 text-emerald-400 border-emerald-800';
      case 'SUBMITTED':
      case 'PENDING':
        return 'bg-blue-950 text-blue-400 border-blue-800';
      case 'CANCELLED':
      case 'EXPIRED':
        return 'bg-slate-800 text-slate-400 border-slate-700';
      case 'REJECTED':
      case 'FAILED':
      default:
        return 'bg-rose-950 text-rose-400 border-rose-800';
    }
  };

  return (
    <div data-testid="trade-history" className="bg-slate-900 border border-slate-800 rounded-lg p-5">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
        <div>
          <h2 className="text-lg font-semibold text-white tracking-wide">Trade History & Fills</h2>
          <p className="text-xs text-slate-400">Chronological execution audit trail across option and equity orders</p>
        </div>
        <div className="flex items-center space-x-3">
          <button
            type="button"
            data-testid="sort-date-btn"
            onClick={() => setSortOrder((prev) => (prev === 'desc' ? 'asc' : 'desc'))}
            className="text-xs font-mono px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors flex items-center"
          >
            <span>Date: {sortOrder === 'desc' ? 'Newest ↓' : 'Oldest ↑'}</span>
          </button>
          <span className="text-xs font-mono text-slate-500">
            {trades.length} Trade{trades.length === 1 ? '' : 's'}
          </span>
        </div>
      </div>

      {sortedTrades.length === 0 ? (
        <div data-testid="empty-trades" className="p-8 text-center text-slate-500 text-sm border border-dashed border-slate-800 rounded-md">
          No historical trades executed yet.
        </div>
      ) : (
        <div className="divide-y divide-slate-800/80 border border-slate-800 rounded-lg overflow-hidden bg-slate-950/40">
          {sortedTrades.map((trade) => (
            <div
              key={trade.id}
              data-testid="trade-row"
              onClick={() => onSelectTrade?.(trade)}
              className={`p-4 hover:bg-slate-800/40 transition-colors ${
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
                  <span className="font-mono text-xs font-semibold text-slate-300">
                    Class: <strong className="text-cyan-400">{trade.order_class}</strong>
                  </span>
                  <span className="text-xs font-mono text-slate-500">Cycle: {trade.cycle_id}</span>
                </div>

                <div className="flex items-center space-x-3 text-xs font-mono">
                  <span className="text-slate-400">
                    Cost: <strong className="text-white">${trade.cost.toLocaleString(undefined, { minimumFractionDigits: 2 })}</strong>
                  </span>
                  <span className="text-slate-500">
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
                  <div key={idx} className="text-xs font-mono flex items-center justify-between p-2 rounded bg-slate-900/60 border border-slate-800/60">
                    <span className="text-indigo-300 font-semibold">{leg.symbol}</span>
                    <span className="text-slate-300">
                      Qty: {leg.qty} @ ${leg.price.toFixed(2)}
                    </span>
                    {leg.slippage !== undefined && (
                      <span className="text-[11px] text-slate-400">
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
