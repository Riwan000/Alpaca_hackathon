import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PortfolioOverview } from './PortfolioOverview';
import { STUB_HEDGE_CONTEXT } from '../test/server';

describe('PortfolioOverview Component (P3-FE-1, P3-FE-4)', () => {
  it('renders a row per holding and matches totals in payload', () => {
    render(<PortfolioOverview portfolio={STUB_HEDGE_CONTEXT.portfolio_state} />);

    expect(screen.getByTestId('portfolio-overview')).toBeInTheDocument();
    expect(screen.getByTestId('portfolio-total-value')).toHaveTextContent('$1,000,000');
    expect(screen.getByTestId('portfolio-cash')).toHaveTextContent('$200,000');
    expect(screen.getByTestId('portfolio-gross-exposure')).toHaveTextContent('$800,000');
    expect(screen.getByTestId('portfolio-net-exposure')).toHaveTextContent('$760,000');
    expect(screen.getByTestId('portfolio-buying-power')).toHaveTextContent('$400,000');

    // AAPL Position
    expect(screen.getByText('AAPL')).toBeInTheDocument();
    expect(screen.getByText('1,000')).toBeInTheDocument();
    expect(screen.getByText('$180,000')).toBeInTheDocument();
    expect(screen.getByText('+$30,000')).toBeInTheDocument();
  });

  it('renders an empty state when portfolio positions array is empty', () => {
    render(
      <PortfolioOverview
        portfolio={{
          total_value: 50000,
          cash: 50000,
          equity: 0,
          buying_power: 50000,
          positions: [],
        }}
      />
    );

    expect(screen.getByTestId('portfolio-empty-state')).toBeInTheDocument();
    expect(screen.getByText(/No Active Positions/i)).toBeInTheDocument();
  });

  it('renders loading and error states cleanly (P3-FE-4)', () => {
    const { rerender } = render(<PortfolioOverview isLoading={true} />);
    expect(screen.getByTestId('portfolio-overview-loading')).toBeInTheDocument();

    rerender(
      <PortfolioOverview error={new Error('Connection to Alpaca timed out')} />
    );
    expect(screen.getByTestId('portfolio-overview-error')).toBeInTheDocument();
    expect(
      screen.getByText(/Connection to Alpaca timed out/i)
    ).toBeInTheDocument();
  });
});
