import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Recommendation } from './Recommendation';
import { STUB_STRATEGY_DECISION, STUB_HEDGE_CONTEXT } from '../test/server';

describe('Recommendation Component (P4-FE-2)', () => {
  it('shows action verb and calculated hedge gap matching payload', () => {
    render(
      <MemoryRouter>
        <Recommendation
          decision={STUB_STRATEGY_DECISION}
          currentHedge={STUB_HEDGE_CONTEXT.current_hedge}
          objective={STUB_HEDGE_CONTEXT.objective}
        />
      </MemoryRouter>
    );

    expect(screen.getByTestId('recommendation-panel')).toBeInTheDocument();
    expect(screen.getByTestId('recommendation-action-badge')).toHaveTextContent('SELECT_STRATEGY');
    expect(screen.getByTestId('selected-strategy-title')).toHaveTextContent(/PROTECTIVE PUT/i);
    expect(screen.getByTestId('selected-strategy-cost')).toHaveTextContent('$17,000');
    expect(screen.getByTestId('recommendation-rationale')).toHaveTextContent(
      /Protective put gives the most protection per dollar/i
    );

    // Current hedge 0%, Target hedge 20% -> Hedge Gap +20.0%
    expect(screen.getByTestId('current-hedge-ratio')).toHaveTextContent('0.0%');
    expect(screen.getByTestId('target-hedge-ratio')).toHaveTextContent('20.0%');
    expect(screen.getByTestId('hedge-gap')).toHaveTextContent('+20.0%');
  });

  it('handles NO_TRADE action verb state cleanly', () => {
    const noTradeDecision = {
      ...STUB_STRATEGY_DECISION,
      decision: 'NO_TRADE' as const,
      selected_strategy: null,
      selected_hypothesis: null,
      rationale: 'Portfolio drawdown within acceptable variance bounds.',
    };

    render(
      <MemoryRouter>
        <Recommendation decision={noTradeDecision} />
      </MemoryRouter>
    );

    expect(screen.getByTestId('recommendation-action-badge')).toHaveTextContent('NO_TRADE');
    expect(screen.getByTestId('selected-strategy-title')).toHaveTextContent(/NO STRATEGY SELECTED/i);
    expect(screen.getByTestId('recommendation-rationale')).toHaveTextContent(
      /Portfolio drawdown within acceptable variance bounds/i
    );
  });
});
