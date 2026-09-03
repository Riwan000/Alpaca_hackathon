import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PayoffChart } from './PayoffChart';
import { STUB_STRATEGY_HYPOTHESIS } from '../test/server';

describe('PayoffChart Component (P2-FE-1, P2-FE-3, P4-FE-4)', () => {
  it('renders a skeleton / curve spanning data points from {x, y}[] mock data', () => {
    const mockPoints = [
      { x: 400, y: -17000 },
      { x: 500, y: -17000 },
      { x: 600, y: 83000 },
    ];

    render(<PayoffChart points={mockPoints} strategyName="Protective Put" />);

    expect(screen.getByTestId('payoff-chart')).toBeInTheDocument();
    expect(screen.getByTestId('payoff-curve-path')).toBeInTheDocument();
    expect(screen.getByText(/Protective Put Payoff Profile/i)).toBeInTheDocument();
  });

  it('renders a placeholder when points array is empty without crashing', () => {
    render(<PayoffChart points={[]} />);

    expect(screen.getByTestId('payoff-chart-placeholder')).toBeInTheDocument();
    expect(
      screen.getByText(/No payoff data available for this strategy structure/i)
    ).toBeInTheDocument();
  });

  it('binds PayoffChart to real hypothesis payoff data (P4-FE-4)', () => {
    render(
      <PayoffChart
        points={STUB_STRATEGY_HYPOTHESIS.payoff_profile}
        currentPrice={500}
        strikePrice={500}
      />
    );

    expect(screen.getByTestId('payoff-chart')).toBeInTheDocument();
    expect(screen.getByTestId('payoff-curve-path')).toBeInTheDocument();
    expect(screen.getByTestId('current-price-indicator')).toBeInTheDocument();
  });
});
