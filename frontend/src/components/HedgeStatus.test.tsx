import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HedgeStatus } from './HedgeStatus';
import type { CurrentHedge } from '../api/types';

describe('HedgeStatus Component (P5-FE-1)', () => {
  it('renders unhedged state when no active hedge is provided', () => {
    const unhedged: CurrentHedge = {
      active: false,
      legs: [],
    };

    render(<HedgeStatus currentHedge={unhedged} />);

    expect(screen.getByTestId('hedge-status-panel')).toBeInTheDocument();
    expect(screen.getByTestId('hedge-state-badge')).toHaveTextContent('UNHEDGED');
    expect(screen.getByTestId('unhedged-view')).toBeInTheDocument();
    expect(
      screen.getByText(/no active overlay position detected/i)
    ).toBeInTheDocument();
  });

  it('renders active hedge with KPIs, PnL, and legs table when hedged', () => {
    const hedged: CurrentHedge = {
      active: true,
      strategy_type: 'PROTECTIVE_PUT',
      cost: 17000.0,
      downside_protection_pct: 0.9,
      expiration: '2026-12-18',
      unrealized_pnl: 2500.0,
      legs: [
        {
          underlying: 'SPY',
          right: 'PUT',
          side: 'BUY',
          strike: 500.0,
          expiration: '2026-12-18',
          quantity: 20,
          limit_price: 8.5,
        },
      ],
    };

    render(<HedgeStatus currentHedge={hedged} />);

    expect(screen.getByTestId('hedge-state-badge')).toHaveTextContent('HEDGED');
    expect(screen.getByTestId('hedge-strategy')).toHaveTextContent('PROTECTIVE PUT');
    expect(screen.getByTestId('hedge-protection')).toHaveTextContent('90.0%');
    expect(screen.getByTestId('hedge-cost')).toHaveTextContent('$17,000');
    expect(screen.getByTestId('hedge-expiration')).toHaveTextContent('2026-12-18');
    expect(screen.getByTestId('hedge-pnl')).toHaveTextContent('+$2,500');
    expect(screen.getByTestId('hedge-legs-table')).toBeInTheDocument();
    expect(screen.getByText(/\$500\.00/)).toBeInTheDocument();
  });

  it('renders loading and error states properly', () => {
    const { rerender } = render(<HedgeStatus isLoading={true} />);
    expect(screen.getByTestId('hedge-status-loading')).toBeInTheDocument();

    rerender(
      <HedgeStatus
        isLoading={false}
        error={new Error('Failed to load portfolio hedge status')}
      />
    );
    expect(screen.getByTestId('hedge-status-error')).toHaveTextContent(
      /failed to load portfolio hedge status/i
    );
  });
});
