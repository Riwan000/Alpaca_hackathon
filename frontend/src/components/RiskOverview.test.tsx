import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RiskOverview } from './RiskOverview';
import { STUB_HEDGE_CONTEXT } from '../test/server';

describe('RiskOverview Component (P3-FE-2, P3-FE-4)', () => {
  it('renders one tile per metric with formatted values', () => {
    render(<RiskOverview portfolio={STUB_HEDGE_CONTEXT.portfolio_state} />);

    expect(screen.getByTestId('risk-overview')).toBeInTheDocument();
    expect(screen.getByTestId('metric-volatility')).toHaveTextContent('19.0%');
    expect(screen.getByTestId('metric-beta')).toHaveTextContent('1.10');
    expect(screen.getByTestId('metric-drawdown')).toHaveTextContent('-7.0%');
    expect(screen.getByTestId('metric-max_drawdown')).toHaveTextContent('-12.0%');
    expect(screen.getByTestId('metric-concentration')).toHaveTextContent('0.420');
  });

  it('renders a dash for null metrics without NaN (P3-FE-2 spec)', () => {
    render(
      <RiskOverview
        portfolio={{
          total_value: 100000,
          cash: 100000,
          equity: 0,
          buying_power: 100000,
          positions: [],
          volatility: null,
          beta: null,
          drawdown: null,
          max_drawdown: null,
          concentration_hhi: null,
        }}
      />
    );

    expect(screen.getByTestId('metric-volatility')).toHaveTextContent('—');
    expect(screen.getByTestId('metric-beta')).toHaveTextContent('—');
    expect(screen.getByTestId('metric-drawdown')).toHaveTextContent('—');
    expect(screen.getByTestId('metric-max_drawdown')).toHaveTextContent('—');
    expect(screen.getByTestId('metric-concentration')).toHaveTextContent('—');
    expect(screen.queryByText(/NaN/i)).not.toBeInTheDocument();
  });

  it('renders loading and error states cleanly (P3-FE-4)', () => {
    const { rerender } = render(<RiskOverview isLoading={true} />);
    expect(screen.getByTestId('risk-overview-loading')).toBeInTheDocument();

    rerender(<RiskOverview error={new Error('Risk calculations unavailable')} />);
    expect(screen.getByTestId('risk-overview-error')).toBeInTheDocument();
    expect(screen.getByText(/Risk calculations unavailable/i)).toBeInTheDocument();
  });
});
