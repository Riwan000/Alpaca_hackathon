import React from 'react';
import { ShieldAlert, Activity, TrendingDown, PieChart, AlertCircle } from 'lucide-react';
import type { PortfolioState } from '../api/types';

export interface RiskOverviewProps {
  portfolio?: PortfolioState | null;
  isLoading?: boolean;
  error?: Error | null;
  className?: string;
}

export const RiskOverview: React.FC<RiskOverviewProps> = ({
  portfolio,
  isLoading = false,
  error = null,
  className = '',
}) => {
  const formatPercent = (val?: number | null, decimals = 1) => {
    if (val === undefined || val === null || Number.isNaN(val)) return '—';
    return `${(val * 100).toFixed(decimals)}%`;
  };

  const formatNumber = (val?: number | null, decimals = 2) => {
    if (val === undefined || val === null || Number.isNaN(val)) return '—';
    return Number(val).toFixed(decimals);
  };

  if (isLoading && !portfolio) {
    return (
      <div
        className={`border border-[var(--border-color)] bg-[var(--bg-card)] p-5 space-y-4 ${className}`}
        data-testid="risk-overview-loading"
      >
        <div className="h-5 w-32 bg-[var(--bg-subtle)] animate-pulse" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-20 bg-[var(--bg-subtle)] animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div
        className={`border border-[var(--status-danger)] bg-[var(--status-danger)]/5 p-5 space-y-2 ${className}`}
        data-testid="risk-overview-error"
      >
        <h2 className="text-sm font-serif font-bold text-[var(--status-danger)] flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          Risk Analytics Unavailable
        </h2>
        <p className="text-xs font-mono text-[var(--text-muted)]">{error.message}</p>
      </div>
    );
  }

  const tiles = [
    {
      id: 'volatility',
      label: 'Annualized Volatility (σ)',
      description: 'Historical Realized 30-Day Volatility',
      value: formatPercent(portfolio?.volatility),
      color: (portfolio?.volatility ?? 0) > 0.25 ? 'text-[var(--status-warning)]' : 'text-[var(--text-main)]',
      icon: Activity,
    },
    {
      id: 'beta',
      label: 'Portfolio Beta (β)',
      description: 'Sensitivity vs S&P 500 Benchmark',
      value: formatNumber(portfolio?.beta, 2),
      color: 'text-[var(--brand-teal)]',
      icon: Activity,
    },
    {
      id: 'drawdown',
      label: 'Current Drawdown',
      description: 'Peak-to-Trough Unrealized Drawdown',
      value: formatPercent(portfolio?.drawdown),
      color: (portfolio?.drawdown ?? 0) < -0.05 ? 'text-[var(--status-warning)]' : 'text-[var(--status-safe)]',
      icon: TrendingDown,
    },
    {
      id: 'max_drawdown',
      label: 'Historical Max Drawdown',
      description: 'Worst Historical Peak Loss',
      value: formatPercent(portfolio?.max_drawdown),
      color: 'text-[var(--status-danger)]',
      icon: TrendingDown,
    },
    {
      id: 'concentration',
      label: 'Concentration (HHI)',
      description: 'Herfindahl-Hirschman Index Ratio',
      value: formatNumber(portfolio?.concentration_hhi, 3),
      color: (portfolio?.concentration_hhi ?? 0) > 0.4 ? 'text-[var(--brand-gold)]' : 'text-[var(--text-main)]',
      icon: PieChart,
    },
  ];

  return (
    <div
      className={`border border-[var(--border-color)] bg-[var(--bg-card)] p-5 space-y-4 ${className}`}
      data-testid="risk-overview"
    >
      <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-3">
        <div>
          <h2 className="text-sm font-serif font-bold text-[var(--text-main)] flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-[var(--brand-spruce)]" />
            Portfolio Risk Overview
          </h2>
          <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase">
            Deterministic Greek & Statistical Risk Sensitivities
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {tiles.map((tile) => (
          <div
            key={tile.id}
            className="p-3.5 bg-[var(--bg-subtle)] border border-[var(--border-color)] flex flex-col justify-between"
            data-testid={`risk-tile-${tile.id}`}
          >
            <div>
              <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block leading-tight">
                {tile.label}
              </span>
              <span className={`text-lg font-mono font-bold block mt-1 ${tile.color}`} data-testid={`metric-${tile.id}`}>
                {tile.value}
              </span>
            </div>
            <span className="text-[9px] font-mono text-[var(--text-muted)] mt-2 line-clamp-1">
              {tile.description}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
