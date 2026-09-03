import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DecisionTrail, type DecisionTrailData } from './DecisionTrail';

describe('DecisionTrail Component (P8-FE-3)', () => {
  it('renders empty prompt when no data is selected', () => {
    render(<DecisionTrail data={null} />);
    expect(screen.getByTestId('decision-trail-empty')).toBeInTheDocument();
  });

  it('renders full provenance chain: trade -> risk -> strategy -> hypotheses -> context -> trigger', () => {
    const data: DecisionTrailData = {
      order_id: 'alpaca-1234',
      trade: {
        symbol: 'SPY261218P00500000',
        action: 'BUY',
        qty: 20,
        price: 8.55,
        status: 'FILLED',
        filled_at: '2026-09-04T01:35:00Z',
      },
      risk: {
        verdict: 'APPROVE',
        checks_passed: 4,
        checks_total: 4,
        rationale: 'All constraints pass within safety thresholds.',
      },
      strategy: {
        strategy_type: 'PROTECTIVE_PUT',
        action: 'NEW_HEDGE',
        rationale: 'Maximizes tail risk protection within budget.',
      },
      hypotheses: [
        { strategy_type: 'PROTECTIVE_PUT', verdict: 'SELECTED' },
        { strategy_type: 'COLLAR', verdict: 'VIABLE' },
        { strategy_type: 'NO_HEDGE', verdict: 'NOT_VIABLE', rejection_reason: 'Drawdown breached' },
      ],
      context: {
        regime: 'RISK_OFF',
        vix: 28.5,
        drawdown: -0.07,
      },
      trigger: {
        trigger_type: 'VOLATILITY_SPIKE',
        observed: { vix: 28.5 },
        threshold: 22.0,
        fired_at: '2026-09-04T01:00:00Z',
      },
    };

    render(<DecisionTrail data={data} />);

    expect(screen.getByTestId('decision-trail')).toBeInTheDocument();
    expect(screen.getByTestId('hop-trigger')).toHaveTextContent('VOLATILITY_SPIKE');
    expect(screen.getByTestId('hop-context')).toHaveTextContent('RISK_OFF');
    expect(screen.getByTestId('hop-hypotheses')).toHaveTextContent('3 evaluated');
    expect(screen.getByTestId('hop-strategy')).toHaveTextContent('PROTECTIVE_PUT');
    expect(screen.getByTestId('hop-risk')).toHaveTextContent('APPROVE');
    expect(screen.getByTestId('hop-trade')).toHaveTextContent('FILLED');

    // Expand strategy hop
    fireEvent.click(screen.getByTestId('hop-strategy'));
    expect(screen.getByText(/Maximizes tail risk protection within budget/i)).toBeInTheDocument();
  });
});
