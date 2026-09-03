import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { HedgeDriftGauge } from './HedgeDriftGauge';

describe('HedgeDriftGauge Component (P7-FE-2)', () => {
  it('renders calm status when current hedge is within deadband of target', () => {
    render(
      <HedgeDriftGauge
        currentHedgeRatio={0.52}
        targetHedgeRatio={0.50}
        deadband={0.05}
      />
    );

    expect(screen.getByTestId('drift-status-badge')).toHaveTextContent(/Calm \(Within Deadband\)/i);
    expect(screen.getByTestId('current-hedge-value')).toHaveTextContent('52.0%');
    expect(screen.getByTestId('target-hedge-value')).toHaveTextContent('50.0%');
    expect(screen.getByTestId('gauge-needle')).toBeInTheDocument();
    expect(screen.getByTestId('target-marker')).toBeInTheDocument();
  });

  it('renders alert status when current hedge breaches deadband', () => {
    render(
      <HedgeDriftGauge
        currentHedgeRatio={0.70}
        targetHedgeRatio={0.50}
        deadband={0.05}
      />
    );

    expect(screen.getByTestId('drift-status-badge')).toHaveTextContent(/Alert \(Drift: \+20.0%\)/i);
    expect(screen.getByTestId('current-hedge-value')).toHaveTextContent('70.0%');
    expect(screen.getByTestId('target-hedge-value')).toHaveTextContent('50.0%');
  });

  it('renders negative drift alert appropriately', () => {
    render(
      <HedgeDriftGauge
        currentHedgeRatio={0.30}
        targetHedgeRatio={0.50}
        deadband={0.05}
      />
    );

    expect(screen.getByTestId('drift-status-badge')).toHaveTextContent(/Alert \(Drift: -20.0%\)/i);
  });
});
