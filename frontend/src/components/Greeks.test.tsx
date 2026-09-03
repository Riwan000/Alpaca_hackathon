import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Greeks } from './Greeks';

describe('Greeks Component (P2-FE-2)', () => {
  it('renders a label and value per greek with mock data', () => {
    render(
      <Greeks
        metrics={{
          net_delta: -700.0,
          net_gamma: 0.014,
          net_theta: 18.0,
          net_vega: -0.08,
        }}
      />
    );

    expect(screen.getByText(/Delta \(Δ\)/i)).toBeInTheDocument();
    expect(screen.getByTestId('greek-delta')).toHaveTextContent('-700.0');

    expect(screen.getByText(/Gamma \(Γ\)/i)).toBeInTheDocument();
    expect(screen.getByTestId('greek-gamma')).toHaveTextContent('+0.0140');

    expect(screen.getByText(/Theta \(Θ\)/i)).toBeInTheDocument();
    expect(screen.getByTestId('greek-theta')).toHaveTextContent('+$18.0/d');

    expect(screen.getByText(/Vega \(ν\)/i)).toBeInTheDocument();
    expect(screen.getByTestId('greek-vega')).toHaveTextContent('-0.080');
  });

  it('renders a dash for missing or null greek values without NaN', () => {
    render(<Greeks metrics={{ net_delta: null, net_gamma: undefined }} />);

    expect(screen.getByTestId('greek-delta')).toHaveTextContent('—');
    expect(screen.getByTestId('greek-gamma')).toHaveTextContent('—');
    expect(screen.getByTestId('greek-theta')).toHaveTextContent('—');
    expect(screen.getByTestId('greek-vega')).toHaveTextContent('—');
    expect(screen.queryByText(/NaN/i)).not.toBeInTheDocument();
  });

  it('renders correctly in compact and table variants', () => {
    const { rerender } = render(
      <Greeks
        variant="compact"
        metrics={{
          delta: -0.35,
          gamma: 0.01,
          theta: -0.04,
          vega: 0.9,
        }}
      />
    );
    expect(screen.getByTestId('greeks-compact')).toBeInTheDocument();
    expect(screen.getByTestId('greek-delta')).toHaveTextContent('-0.350');

    rerender(
      <Greeks
        variant="table"
        metrics={{
          delta: -0.35,
          gamma: 0.01,
          theta: -0.04,
          vega: 0.9,
        }}
      />
    );
    expect(screen.getByTestId('greeks-table')).toBeInTheDocument();
    expect(screen.getByTestId('greek-delta')).toHaveTextContent('-0.350');
  });
});
