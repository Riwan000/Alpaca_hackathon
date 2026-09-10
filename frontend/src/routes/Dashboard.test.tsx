import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { DashboardPage } from '../pages/DashboardPage';
import { AppProviders } from '../providers';

describe('Dashboard Full Assembly & Demo Controls (P8-FE-2, P8-FE-6)', () => {
  it('shows the Overview tab panels by default: Performance, WorkflowState, HedgeDriftGauge, Recommendation, RiskOverview', async () => {
    render(
      <MemoryRouter>
        <AppProviders>
          <DashboardPage />
        </AppProviders>
      </MemoryRouter>
    );

    // Dashboard root
    expect(screen.getByTestId('dashboard-page')).toBeInTheDocument();
    expect(screen.getByTestId('demo-walkthrough')).toBeInTheDocument();

    // Overview tab is active by default
    expect(await screen.findByTestId('performance-panel')).toBeInTheDocument();
    expect(await screen.findByTestId('workflow-state-panel')).toBeInTheDocument();
    // The gauge renders once live monitoring state has loaded; before that it
    // shows an "unavailable" card rather than fabricated ratios.
    expect(await screen.findByTestId('hedge-drift-gauge')).toBeInTheDocument();
    expect(await screen.findByTestId('recommendation-panel')).toBeInTheDocument();
    expect(await screen.findByTestId('risk-overview')).toBeInTheDocument();

    // Panels that live on other tabs are not mounted yet
    expect(screen.queryByTestId('hedge-status-panel')).not.toBeInTheDocument();
    expect(screen.queryByTestId('order-status-panel')).not.toBeInTheDocument();
    expect(screen.queryByTestId('agent-activity')).not.toBeInTheDocument();
  });

  it('reveals the Risk tab panels after clicking the Risk tab', async () => {
    render(
      <MemoryRouter>
        <AppProviders>
          <DashboardPage />
        </AppProviders>
      </MemoryRouter>
    );

    fireEvent.click(screen.getByTestId('tab-risk'));

    expect(await screen.findByTestId('hedge-status-panel')).toBeInTheDocument();
    expect(await screen.findByTestId('risk-checklist-panel')).toBeInTheDocument();
    expect(await screen.findByTestId('strategy-comparison')).toBeInTheDocument();
    expect(screen.getByTestId('reassessment-history')).toBeInTheDocument();
  });

  it('reveals the Execution tab panels after clicking the Execution tab', async () => {
    render(
      <MemoryRouter>
        <AppProviders>
          <DashboardPage />
        </AppProviders>
      </MemoryRouter>
    );

    fireEvent.click(screen.getByTestId('tab-execution'));

    expect(await screen.findByTestId('order-status-panel')).toBeInTheDocument();
    expect(screen.getByTestId('trade-history')).toBeInTheDocument();
    expect(screen.getByTestId('decision-trail')).toBeInTheDocument();
    expect(await screen.findByTestId('portfolio-overview')).toBeInTheDocument();
  });

  it('reveals the Agent / Debug tab panels after clicking the Agent / Debug tab', async () => {
    render(
      <MemoryRouter>
        <AppProviders>
          <DashboardPage />
        </AppProviders>
      </MemoryRouter>
    );

    fireEvent.click(screen.getByTestId('tab-agent-debug'));

    expect(await screen.findByTestId('agent-activity')).toBeInTheDocument();
    expect(screen.getByTestId('monitoring-panel')).toBeInTheDocument();
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

    const targetHedgeVal = await screen.findByTestId('target-hedge-value');
    expect(targetHedgeVal).toHaveTextContent('30.0%');
  });

  it('displays Alpaca account balance, cash, buying power, and badge when account_id query param is provided', async () => {
    render(
      <MemoryRouter initialEntries={['/?account_id=PA3C0P4T6AJE']}>
        <AppProviders>
          <DashboardPage />
        </AppProviders>
      </MemoryRouter>
    );

    // Alpaca Account Bar with rich metrics
    expect(await screen.findByTestId('alpaca-account-bar')).toBeInTheDocument();
    expect(await screen.findByTestId('dashboard-account-id')).toHaveTextContent('PA3C0P4T6AJE');
    expect(await screen.findByTestId('alpaca-live-balance')).toHaveTextContent('$99,607.64');
    expect(await screen.findByTestId('alpaca-day-pnl')).toHaveTextContent('Today: -$315.40');
    expect(await screen.findByTestId('alpaca-unrealized-pnl')).toHaveTextContent('Total P&L: -$392.35');
    expect(await screen.findByTestId('alpaca-holdings-value')).toHaveTextContent('Holdings: $15,589 (4)');
    expect(await screen.findByTestId('alpaca-live-cash')).toHaveTextContent('$84,019.09');
    expect(await screen.findByTestId('alpaca-live-bp')).toHaveTextContent('$379,724');

    // Performance Panel on Overview tab reflects Alpaca P&L and Trajectory chart
    expect(await screen.findByTestId('portfolio-pnl-tile')).toHaveTextContent('-$315.40');
    expect(await screen.findByTestId('hedged-series-line')).toBeInTheDocument();

    // Switch to Execution tab and check PortfolioOverview shows Alpaca badge, KPI ribbon, and holdings table
    fireEvent.click(screen.getByTestId('tab-execution'));
    expect(await screen.findByTestId('alpaca-account-badge')).toHaveTextContent('PA3C0P4T6AJE');
    expect(await screen.findByTestId('portfolio-day-pnl')).toHaveTextContent('-$315');
    expect(await screen.findByTestId('holdings-table')).toBeInTheDocument();
  });

  it('allows switching Alpaca account ID dynamically via inline switcher or quick load', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <AppProviders>
          <DashboardPage />
        </AppProviders>
      </MemoryRouter>
    );

    // Initially quick load button is available
    const quickLoadBtn = screen.getByTestId('quick-load-btn');
    expect(quickLoadBtn).toBeInTheDocument();

    // Click quick load
    fireEvent.click(quickLoadBtn);

    // Alpaca balance and metrics become visible
    expect(await screen.findByTestId('alpaca-live-balance')).toHaveTextContent('$99,607.64');
    expect(await screen.findByTestId('alpaca-day-pnl')).toHaveTextContent('Today: -$315.40');

    // Inline switcher allows changing ID
    const switchBtn = screen.getByTestId('switch-account-btn');
    fireEvent.click(switchBtn);

    const input = screen.getByTestId('input-account-id-inline');
    expect(input).toBeInTheDocument();

    fireEvent.change(input, { target: { value: 'b78de2d5-d310-478f-a038-66f08a62b6c1' } });
    fireEvent.click(screen.getByTestId('submit-account-id-btn'));

    expect(await screen.findByTestId('alpaca-live-balance')).toHaveTextContent('$99,607.64');
  });
});

