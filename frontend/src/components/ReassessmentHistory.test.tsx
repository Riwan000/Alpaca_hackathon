import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ReassessmentHistory, type ReassessmentItem } from './ReassessmentHistory';

describe('ReassessmentHistory Component (P7-FE-3)', () => {
  it('renders empty state when no reassessment events are present', () => {
    render(<ReassessmentHistory reassessments={[]} />);
    expect(screen.getByTestId('empty-reassessments')).toHaveTextContent(
      /No reassessment events recorded yet/i
    );
  });

  it('renders reassessment rows linking trigger, outcome, and hedge delta', () => {
    const items: ReassessmentItem[] = [
      {
        id: 1,
        cycle_id: 'cycle-200',
        trigger: 'VOLATILITY_FALL',
        outcome: 'DECREASE',
        reason: 'Market stabilized and IV dropped to 16. Reducing put coverage.',
        created_at: '2026-09-04T01:30:00Z',
        delta: -0.30,
        before_hedge_ratio: 0.80,
        after_hedge_ratio: 0.50,
      },
      {
        id: 2,
        cycle_id: 'cycle-201',
        trigger: 'DRAWDOWN_RECOVERED',
        outcome: 'MAINTAIN',
        reason: 'Drawdown recovery inside deadband. Keeping active collar.',
        created_at: '2026-09-04T02:00:00Z',
        delta: 0.0,
      },
    ];

    render(<ReassessmentHistory reassessments={items} />);

    const rows = screen.getAllByTestId('reassessment-row');
    expect(rows).toHaveLength(2);

    // Assert first row (DECREASE)
    expect(rows[0]).toHaveTextContent('DECREASE');
    expect(rows[0]).toHaveTextContent('VOLATILITY_FALL');
    expect(rows[0]).toHaveTextContent('Hedge Delta: -30.0% (80% → 50%)');
    expect(rows[0]).toHaveTextContent('Market stabilized and IV dropped to 16');

    // Assert second row (MAINTAIN)
    expect(rows[1]).toHaveTextContent('MAINTAIN');
    expect(rows[1]).toHaveTextContent('DRAWDOWN_RECOVERED');
  });
});
