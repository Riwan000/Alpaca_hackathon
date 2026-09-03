import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RiskChecklist } from './RiskChecklist';
import {
  STUB_RISK_DECISION,
  STUB_RISK_DECISION_MODIFY,
  STUB_RISK_DECISION_REJECT,
} from '../test/server';

describe('RiskChecklist Component (P5-FE-2, P5-FE-4)', () => {
  it('renders one line per check with pass/fail icon on APPROVE verdict', () => {
    render(<RiskChecklist decision={STUB_RISK_DECISION} />);

    expect(screen.getByTestId('risk-checklist-panel')).toBeInTheDocument();
    expect(screen.getByTestId('risk-verdict-badge')).toHaveTextContent('APPROVE');
    expect(screen.getByTestId('risk-checks-list')).toBeInTheDocument();

    // Verify individual checks
    expect(screen.getByTestId('risk-check-item-hedge_budget')).toBeInTheDocument();
    expect(screen.getByTestId('icon-passed-hedge_budget')).toBeInTheDocument();
    expect(screen.getByTestId('risk-check-item-max_hedge_ratio')).toBeInTheDocument();
    expect(screen.getByTestId('icon-passed-max_hedge_ratio')).toBeInTheDocument();
    expect(screen.getByTestId('risk-check-item-liquidity')).toBeInTheDocument();
    expect(screen.getByTestId('icon-passed-liquidity')).toBeInTheDocument();
  });

  it('modify-reject: surfaces parameter adjustments on MODIFY and blocking violations on REJECT (P5-FE-4)', () => {
    // 1. MODIFY verdict
    const { rerender } = render(
      <RiskChecklist decision={STUB_RISK_DECISION_MODIFY} />
    );

    expect(screen.getByTestId('risk-verdict-badge')).toHaveTextContent('MODIFY');
    expect(screen.getByTestId('risk-modifications-box')).toBeInTheDocument();
    expect(
      screen.getByText(/downsized to 20 contracts/i)
    ).toBeInTheDocument();
    expect(screen.getByTestId('icon-failed-max_hedge_ratio')).toBeInTheDocument();

    // 2. REJECT verdict
    rerender(<RiskChecklist decision={STUB_RISK_DECISION_REJECT} />);

    expect(screen.getByTestId('risk-verdict-badge')).toHaveTextContent('REJECT');
    expect(screen.getByTestId('risk-violations-box')).toBeInTheDocument();
    expect(
      screen.getByText(/premium cost exceeds max allocated hedge budget/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/open interest below institutional liquidity threshold/i)
    ).toBeInTheDocument();
  });

  it('renders loading and error states properly', () => {
    const { rerender } = render(<RiskChecklist isLoading={true} />);
    expect(screen.getByTestId('risk-checklist-loading')).toBeInTheDocument();

    rerender(
      <RiskChecklist
        isLoading={false}
        error={new Error('Risk engine unreachable')}
      />
    );
    expect(screen.getByTestId('risk-checklist-error')).toHaveTextContent(
      /risk engine unreachable/i
    );
  });
});
