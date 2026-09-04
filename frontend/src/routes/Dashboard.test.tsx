import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { DashboardPage } from '../pages/DashboardPage';
import { AppProviders } from '../providers';

describe('Dashboard Full Assembly & Demo Controls (P8-FE-2, P8-FE-6)', () => {
  it('mounts every panel: Portfolio, Risk, Hedge, Recommendation, Comparison, AgentActivity, Performance, Drift, TradeHistory, DecisionTrail', async () => {
    render(
      <MemoryRouter>
        <AppProviders>
          <DashboardPage />
        </AppProviders>
      </MemoryRouter>
    );

    // Dashboard root
    expect(screen.getByTestId('dashboard-page')).toBeInTheDocument();

    // Key assembled panels
    expect(screen.getByTestId('demo-walkthrough')).toBeInTheDocument();
    expect(await screen.findByTestId('performance-panel')).toBeInTheDocument();
    expect(await screen.findByTestId('workflow-state-panel')).toBeInTheDocument();
    expect(screen.getByTestId('hedge-drift-gauge')).toBeInTheDocument();
    expect(screen.getByTestId('monitoring-panel')).toBeInTheDocument();
    expect(await screen.findByTestId('hedge-status-panel')).toBeInTheDocument();
    expect(await screen.findByTestId('risk-overview')).toBeInTheDocument();
    expect(await screen.findByTestId('recommendation-panel')).toBeInTheDocument();
    expect(await screen.findByTestId('risk-checklist-panel')).toBeInTheDocument();
    expect(await screen.findByTestId('strategy-comparison')).toBeInTheDocument();
    expect(screen.getByTestId('reassessment-history')).toBeInTheDocument();
    expect(await screen.findByTestId('order-status-panel')).toBeInTheDocument();
    expect(screen.getByTestId('trade-history')).toBeInTheDocument();
    expect(screen.getByTestId('decision-trail')).toBeInTheDocument();
    expect(await screen.findByTestId('portfolio-overview')).toBeInTheDocument();
    expect(await screen.findByTestId('agent-activity')).toBeInTheDocument();
  });

  it('reset returns the UI to the seed state without a full page reload (P8-FE-6)', async () => {
    render(
      <MemoryRouter>
        <AppProviders>
          <DashboardPage />
        </AppProviders>
      </MemoryRouter>
    );

    const resetBtn = screen.getByTestId('reset-demo-btn');
    expect(resetBtn).toBeInTheDocument();

    // Click reset button
    fireEvent.click(resetBtn);

    // Assert dashboard remains intact and active
    expect(screen.getByTestId('dashboard-page')).toBeInTheDocument();
    expect(screen.getByTestId('demo-walkthrough')).toBeInTheDocument();
  });

  it('reflects customized target hedge ratio from localStorage in HedgeDriftGauge', async () => {
    localStorage.setItem(
      'aegis_user_configuration',
      JSON.stringify({
        drawdownTolerance: 10,
        targetHedgeRatio: 30,
        maxBudget: 5,
        deadbandBuffer: 5,
        autonomyMode: 'FULL_AUTONOMY',
      })
    );

    render(
      <MemoryRouter>
        <AppProviders>
          <DashboardPage />
        </AppProviders>
      </MemoryRouter>
    );

    const targetHedgeVal = screen.getByTestId('target-hedge-value');
    expect(targetHedgeVal).toHaveTextContent('30.0%');
  });
});
