import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { StrategyComparison } from './StrategyComparison';
import { STUB_STRATEGY_HYPOTHESES, STUB_STRATEGY_DECISION } from '../test/server';

describe('StrategyComparison Component (P4-FE-1, P4-FE-5)', () => {
  it('renders one column per hypothesis with side-by-side metrics', () => {
    render(
      <StrategyComparison
        hypotheses={STUB_STRATEGY_HYPOTHESES}
        selectedStrategy="PROTECTIVE_PUT"
        comparisonRows={STUB_STRATEGY_DECISION.comparison}
      />
    );

    expect(screen.getByTestId('strategy-comparison')).toBeInTheDocument();
    expect(screen.getByTestId('hypotheses-grid')).toBeInTheDocument();

    // 4 Hypotheses
    expect(screen.getByTestId('hypothesis-card-PROTECTIVE_PUT')).toBeInTheDocument();
    expect(screen.getByTestId('hypothesis-card-PUT_SPREAD')).toBeInTheDocument();
    expect(screen.getByTestId('hypothesis-card-COLLAR')).toBeInTheDocument();
    expect(screen.getByTestId('hypothesis-card-NO_HEDGE')).toBeInTheDocument();

    // Cost checks
    expect(screen.getByTestId('cost-PROTECTIVE_PUT')).toHaveTextContent('$17,000');
    expect(screen.getByTestId('cost-PUT_SPREAD')).toHaveTextContent('$10,600');
    expect(screen.getByTestId('cost-COLLAR')).toHaveTextContent('$0');

    // Downside protection checks
    expect(screen.getByTestId('protection-PROTECTIVE_PUT')).toHaveTextContent('90.0%');
    expect(screen.getByTestId('protection-COLLAR')).toHaveTextContent('85.0%');
  });

  it('highlights the selected strategy with distinct active styling', () => {
    render(
      <StrategyComparison
        hypotheses={STUB_STRATEGY_HYPOTHESES}
        selectedStrategy="PROTECTIVE_PUT"
      />
    );

    expect(screen.getByTestId('selected-badge')).toHaveTextContent(/SELECTED/i);
    expect(screen.getByTestId('hypothesis-card-PROTECTIVE_PUT')).toHaveClass(
      'border-[var(--brand-spruce)]'
    );
  });

  it('styles NOT_VIABLE hypotheses distinctly with error badges', () => {
    render(
      <StrategyComparison
        hypotheses={STUB_STRATEGY_HYPOTHESES}
        selectedStrategy="PROTECTIVE_PUT"
      />
    );

    const notViableBadges = screen.getAllByTestId('not-viable-badge');
    expect(notViableBadges.length).toBeGreaterThanOrEqual(1);
    expect(notViableBadges[0]).toHaveTextContent(/NOT VIABLE/i);
  });

  it('shows rejected-hypothesis reasoning when expanded (P4-FE-5)', () => {
    render(
      <StrategyComparison
        hypotheses={STUB_STRATEGY_HYPOTHESES}
        selectedStrategy="PROTECTIVE_PUT"
      />
    );

    // Click to toggle rejection details for PUT_SPREAD
    const toggleButton = screen.getByTestId('toggle-rejection-PUT_SPREAD');
    fireEvent.click(toggleButton);

    const rejectionSection = screen.getByTestId('rejection-reason-PUT_SPREAD');
    expect(rejectionSection).toBeInTheDocument();
    expect(rejectionSection).toHaveTextContent(
      /Capped tail downside below \$470 breaches drawdown safety threshold/i
    );
  });
});
