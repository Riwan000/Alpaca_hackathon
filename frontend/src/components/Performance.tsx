import React from 'react';

export interface PerformanceSnapshot {
  portfolio_pnl: number;
  hedge_pnl: number;
  net_pnl: number;
  drawdown: number;
  hedge_cost: number;
  benchmark_pnl: number;
}

export interface PerformanceSeriesPoint {
  ts?: string;
  cycle_id: string;
  portfolio_pnl: number;
  hedge_pnl: number;
  net_pnl: number;
  benchmark_pnl: number;
}

export interface PerformanceProps {
  current?: PerformanceSnapshot;
  series?: PerformanceSeriesPoint[];
  isLoading?: boolean;
}

const formatCurrency = (val: number) => {
  const prefix = val > 0 ? '+$' : val < 0 ? '-$' : '$';
  return `${prefix}${Math.abs(val).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
};

export const Performance: React.FC<PerformanceProps> = ({
  current = {
    portfolio_pnl: 0,
    hedge_pnl: 0,
    net_pnl: 0,
    drawdown: 0,
    hedge_cost: 0,
    benchmark_pnl: 0,
  },
  series = [],
  isLoading = false,
}) => {
  if (isLoading) {
    return (
      <div data-testid="performance-loading" className="p-5 bg-slate-900 border border-slate-800 rounded-lg animate-pulse">
        <div className="h-6 bg-slate-800 rounded w-1/4 mb-4"></div>
        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className="h-20 bg-slate-800 rounded"></div>
          <div className="h-20 bg-slate-800 rounded"></div>
          <div className="h-20 bg-slate-800 rounded"></div>
          <div className="h-20 bg-slate-800 rounded"></div>
        </div>
        <div className="h-48 bg-slate-800 rounded"></div>
      </div>
    );
  }

  const cushion = current.net_pnl - current.benchmark_pnl;

  return (
    <div data-testid="performance-panel" className="bg-slate-900 border border-slate-800 rounded-lg p-5">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
        <div>
          <h2 className="text-lg font-semibold text-white tracking-wide">Portfolio Performance & Hedge Attribution</h2>
          <p className="text-xs text-slate-400">Live P&L decomposition vs unhedged baseline benchmark (BRD §36)</p>
        </div>
        <span className="text-xs font-mono px-2.5 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700">
          Drawdown: {(current.drawdown * 100).toFixed(2)}%
        </span>
      </div>

      {/* P&L Tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <div data-testid="net-pnl-tile" className="p-4 bg-slate-950/70 border border-slate-800 rounded-lg">
          <div className="text-xs text-slate-400 font-medium">Net Realized P&L</div>
          <div
            className={`text-xl font-mono font-bold mt-1 ${
              current.net_pnl > 0
                ? 'text-emerald-400'
                : current.net_pnl < 0
                ? 'text-rose-400'
                : 'text-slate-300'
            }`}
          >
            {formatCurrency(current.net_pnl)}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">Portfolio + Hedge</div>
        </div>

        <div data-testid="portfolio-pnl-tile" className="p-4 bg-slate-950/70 border border-slate-800 rounded-lg">
          <div className="text-xs text-slate-400 font-medium">Underlying Equity P&L</div>
          <div
            className={`text-xl font-mono font-bold mt-1 ${
              current.portfolio_pnl > 0
                ? 'text-emerald-400'
                : current.portfolio_pnl < 0
                ? 'text-rose-400'
                : 'text-slate-300'
            }`}
          >
            {formatCurrency(current.portfolio_pnl)}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">Core equity book</div>
        </div>

        <div data-testid="hedge-pnl-tile" className="p-4 bg-slate-950/70 border border-slate-800 rounded-lg">
          <div className="text-xs text-slate-400 font-medium">Hedge Options P&L</div>
          <div
            className={`text-xl font-mono font-bold mt-1 ${
              current.hedge_pnl > 0
                ? 'text-cyan-400'
                : current.hedge_pnl < 0
                ? 'text-amber-400'
                : 'text-slate-300'
            }`}
          >
            {formatCurrency(current.hedge_pnl)}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">Cost: {formatCurrency(current.hedge_cost)}</div>
        </div>

        <div data-testid="benchmark-pnl-tile" className="p-4 bg-slate-950/70 border border-slate-800 rounded-lg">
          <div className="text-xs text-slate-400 font-medium">Unhedged Benchmark</div>
          <div
            className={`text-xl font-mono font-bold mt-1 ${
              current.benchmark_pnl > 0
                ? 'text-emerald-400'
                : current.benchmark_pnl < 0
                ? 'text-rose-400'
                : 'text-slate-300'
            }`}
          >
            {formatCurrency(current.benchmark_pnl)}
          </div>
          <div data-testid="cushion-tile" className="text-[11px] text-cyan-400 font-mono mt-0.5">
            Cushion: {formatCurrency(cushion)}
          </div>
        </div>
      </div>

      {/* SVG Chart */}
      <div data-testid="performance-chart" className="p-4 bg-slate-950/50 border border-slate-800 rounded-lg">
        <div className="flex items-center justify-between mb-3 text-xs text-slate-400">
          <span className="font-semibold uppercase tracking-wider text-[11px]">P&L Trajectory: Hedged vs Unhedged Benchmark</span>
          <div className="flex items-center space-x-4">
            <span className="flex items-center text-cyan-400 font-mono text-[11px]">
              <span className="w-3 h-0.5 bg-cyan-400 mr-1.5 inline-block"></span> Hedged Net P&L
            </span>
            <span className="flex items-center text-rose-400 font-mono text-[11px]">
              <span className="w-3 h-0.5 bg-rose-400 border-b border-dashed mr-1.5 inline-block"></span> Unhedged Benchmark
            </span>
          </div>
        </div>

        <div className="relative h-44 w-full flex items-center justify-center">
          {series.length === 0 ? (
            <div data-testid="empty-chart" className="text-xs text-slate-500 font-mono">
              Insufficient time series points recorded yet.
            </div>
          ) : (
            <svg data-testid="performance-svg" className="w-full h-full" viewBox="0 0 500 120" preserveAspectRatio="none">
              {/* Zero line */}
              <line x1="0" y1="60" x2="500" y2="60" stroke="#334155" strokeWidth="1" strokeDasharray="3 3" />

              {/* Hedged Net Line */}
              <polyline
                data-testid="hedged-series-line"
                fill="none"
                stroke="#06b6d4"
                strokeWidth="2.5"
                points={series
                  .map((p, idx) => {
                    const x = (idx / Math.max(series.length - 1, 1)) * 480 + 10;
                    const y = 60 - Math.min(Math.max(p.net_pnl / 1000, -50), 50);
                    return `${x},${y}`;
                  })
                  .join(' ')}
              />

              {/* Unhedged Benchmark Line */}
              <polyline
                data-testid="unhedged-series-line"
                fill="none"
                stroke="#f43f5e"
                strokeWidth="2"
                strokeDasharray="4 3"
                points={series
                  .map((p, idx) => {
                    const x = (idx / Math.max(series.length - 1, 1)) * 480 + 10;
                    const y = 60 - Math.min(Math.max(p.benchmark_pnl / 1000, -50), 50);
                    return `${x},${y}`;
                  })
                  .join(' ')}
              />
            </svg>
          )}
        </div>
      </div>
    </div>
  );
};
