import React from 'react';
import type { HedgeMetrics, OptionCandidate } from '../api/types';

export interface GreeksData {
  delta?: number | null;
  gamma?: number | null;
  theta?: number | null;
  vega?: number | null;
  rho?: number | null;
  net_delta?: number | null;
  net_gamma?: number | null;
  net_theta?: number | null;
  net_vega?: number | null;
}

export interface GreeksProps {
  metrics?: HedgeMetrics | OptionCandidate | GreeksData | null;
  variant?: 'grid' | 'compact' | 'table';
  className?: string;
}

export const Greeks: React.FC<GreeksProps> = ({
  metrics,
  variant = 'grid',
  className = '',
}) => {
  const delta = (metrics as HedgeMetrics | GreeksData)?.net_delta ?? (metrics as OptionCandidate | GreeksData)?.delta;
  const gamma = (metrics as HedgeMetrics | GreeksData)?.net_gamma ?? (metrics as OptionCandidate | GreeksData)?.gamma;
  const theta = (metrics as HedgeMetrics | GreeksData)?.net_theta ?? (metrics as OptionCandidate | GreeksData)?.theta;
  const vega = (metrics as HedgeMetrics | GreeksData)?.net_vega ?? (metrics as OptionCandidate | GreeksData)?.vega;
  const rho = (metrics as GreeksData)?.rho;

  const formatGreek = (val?: number | null, decimals = 3, prefixPlus = false): string => {
    if (val === undefined || val === null || Number.isNaN(val)) return '—';
    const num = Number(val);
    if (Math.abs(num) >= 100) {
      // Net portfolio dollar delta
      return `${num > 0 && prefixPlus ? '+' : ''}${num.toFixed(1)}`;
    }
    const formatted = num.toFixed(decimals);
    return num > 0 && prefixPlus ? `+${formatted}` : formatted;
  };

  const formatTheta = (val?: number | null): string => {
    if (val === undefined || val === null || Number.isNaN(val)) return '—';
    const num = Number(val);
    const sign = num > 0 ? '+$' : num < 0 ? '-$' : '$';
    return `${sign}${Math.abs(num).toFixed(1)}/d`;
  };

  const items = [
    {
      id: 'delta',
      name: 'Delta (Δ)',
      description: 'Price Sensitivity / Hedge Ratio',
      value: formatGreek(delta, 3, false),
      color: 'text-[var(--brand-teal)]',
    },
    {
      id: 'gamma',
      name: 'Gamma (Γ)',
      description: 'Delta Sensitivity to Spot',
      value: formatGreek(gamma, 4, true),
      color: 'text-[var(--text-main)]',
    },
    {
      id: 'theta',
      name: 'Theta (Θ)',
      description: 'Daily Time Decay',
      value: formatTheta(theta),
      color: (theta ?? 0) >= 0 ? 'text-[var(--status-safe)]' : 'text-[var(--status-danger)]',
    },
    {
      id: 'vega',
      name: 'Vega (ν)',
      description: 'Volatility Sensitivity',
      value: formatGreek(vega, 3, false),
      color: 'text-[var(--brand-gold)]',
    },
  ];

  if (rho !== undefined && rho !== null) {
    items.push({
      id: 'rho',
      name: 'Rho (ρ)',
      description: 'Interest Rate Sensitivity',
      value: formatGreek(rho, 4, true),
      color: 'text-[var(--text-muted)]',
    });
  }

  if (variant === 'compact') {
    return (
      <div className={`flex flex-wrap gap-2 ${className}`} data-testid="greeks-compact">
        {items.map((item) => (
          <div
            key={item.id}
            className="px-2 py-1 bg-[var(--bg-subtle)] border border-[var(--border-color)] text-xs font-mono flex items-center gap-1.5"
          >
            <span className="text-[var(--text-muted)] text-[10px]">{item.name}:</span>
            <span className={`font-bold ${item.color}`} data-testid={`greek-${item.id}`}>
              {item.value}
            </span>
          </div>
        ))}
      </div>
    );
  }

  if (variant === 'table') {
    return (
      <div className={`overflow-x-auto border border-[var(--border-color)] bg-[var(--bg-card)] ${className}`} data-testid="greeks-table">
        <table className="w-full text-left font-mono text-xs">
          <thead>
            <tr className="border-b border-[var(--border-color)] bg-[var(--bg-subtle)] text-[10px] text-[var(--text-muted)] uppercase">
              <th className="p-2">Greek</th>
              <th className="p-2">Interpretation</th>
              <th className="p-2 text-right">Value</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border-color)]">
            {items.map((item) => (
              <tr key={item.id} className="hover:bg-[var(--bg-subtle)]/50">
                <td className="p-2 font-bold text-[var(--text-main)]">{item.name}</td>
                <td className="p-2 text-[var(--text-muted)] text-[11px]">{item.description}</td>
                <td className={`p-2 text-right font-bold ${item.color}`} data-testid={`greek-${item.id}`}>
                  {item.value}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className={`grid grid-cols-2 sm:grid-cols-4 gap-2 ${className}`} data-testid="greeks-grid">
      {items.map((item) => (
        <div
          key={item.id}
          className="p-3 border border-[var(--border-color)] bg-[var(--bg-card)] text-center relative overflow-hidden"
        >
          <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block mb-1">
            {item.name}
          </span>
          <span className={`text-sm font-mono font-bold ${item.color}`} data-testid={`greek-${item.id}`}>
            {item.value}
          </span>
        </div>
      ))}
    </div>
  );
};
