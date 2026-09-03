import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Performance, type PerformanceSeriesPoint } from './Performance';

describe('Performance Component (P8-FE-1)', () => {
  it('renders P&L tiles and styles positive, negative, and cushion values appropriately', () => {
    render(
      <Performance
        current={{
          portfolio_pnl: -30000,
          hedge_pnl: 22000,
          net_pnl: -8000,
          drawdown: -0.008,
          hedge_cost: 1700,
          benchmark_pnl: -30000,
        }}
        series={[]}
      />
    );

    expect(screen.getByTestId('performance-panel')).toBeInTheDocument();
    expect(screen.getByTestId('net-pnl-tile')).toHaveTextContent('-$8,000.00');
    expect(screen.getByTestId('portfolio-pnl-tile')).toHaveTextContent('-$30,000.00');
    expect(screen.getByTestId('hedge-pnl-tile')).toHaveTextContent('+$22,000.00');
    expect(screen.getByTestId('benchmark-pnl-tile')).toHaveTextContent('-$30,000.00');
    expect(screen.getByTestId('cushion-tile')).toHaveTextContent('+$22,000.00');
    expect(screen.getByTestId('empty-chart')).toBeInTheDocument();
  });

  it('renders hedged vs unhedged series polylines on the performance chart', () => {
    const series: PerformanceSeriesPoint[] = [
      { cycle_id: 'c1', portfolio_pnl: 0, hedge_pnl: 0, net_pnl: 0, benchmark_pnl: 0 },
      { cycle_id: 'c2', portfolio_pnl: -20000, hedge_pnl: 15000, net_pnl: -5000, benchmark_pnl: -20000 },
      { cycle_id: 'c3', portfolio_pnl: -30000, hedge_pnl: 26000, net_pnl: -4000, benchmark_pnl: -30000 },
    ];

    render(
      <Performance
        current={{
          portfolio_pnl: -30000,
          hedge_pnl: 26000,
          net_pnl: -4000,
          drawdown: -0.004,
          hedge_cost: 1700,
          benchmark_pnl: -30000,
        }}
        series={series}
      />
    );

    expect(screen.getByTestId('performance-svg')).toBeInTheDocument();
    expect(screen.getByTestId('hedged-series-line')).toBeInTheDocument();
    expect(screen.getByTestId('unhedged-series-line')).toBeInTheDocument();
  });
});
