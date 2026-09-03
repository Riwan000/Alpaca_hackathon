import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from './index';
import { AppProviders } from '../providers/AppProviders';

const renderWithRouter = (initialPath: string) => {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={[initialPath]}>
        <AppRoutes />
      </MemoryRouter>
    </AppProviders>
  );
};

describe('AppRoutes suite (P1-FE-7)', () => {
  it('renders DashboardPage at "/" and displays fetched stub payload data', async () => {
    renderWithRouter('/');
    expect(screen.getByTestId('dashboard-page')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /portfolio risk & strategy dashboard/i })
    ).toBeInTheDocument();

    // Verify fetched stub data is rendered once all async queries resolve
    await waitFor(() => {
      expect(screen.getByTestId('portfolio-aum')).toHaveTextContent('AUM $1,000,000');
      expect(screen.getByTestId('selected-strategy-name')).toHaveTextContent(/PROTECTIVE PUT/i);
      expect(screen.getByTestId('strategy-cost')).toHaveTextContent('$17,000');
      expect(screen.getByTestId('greek-delta')).toHaveTextContent('-700');
      expect(screen.getByTestId('active-trigger-item')).toHaveTextContent(/TRIGGER: DRAWDOWN_LIMIT/i);
      expect(screen.getByTestId('monitoring-status')).toHaveTextContent(/REASSESS RECOMMENDED/i);
    });
  });

  it('renders ConfigurationPage at "/configuration" and displays live objective parameters', async () => {
    renderWithRouter('/configuration');
    expect(screen.getByTestId('configuration-page')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /agent & risk configuration/i })
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('input-drawdown-tolerance')).toHaveValue(10);
      expect(screen.getByTestId('input-target-hedge')).toHaveValue(20);
      expect(screen.getByTestId('input-max-budget')).toHaveValue(5);
    });
  });

  it('renders StrategyDetailsPage at "/strategy/:id" with dynamic ID and fetched hypothesis data', async () => {
    renderWithRouter('/strategy/strat-test-456');
    expect(screen.getByTestId('strategy-details-page')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /strategy decision details/i })
    ).toBeInTheDocument();
    expect(screen.getByTestId('strategy-id-badge')).toHaveTextContent('ID: strat-test-456');

    await waitFor(() => {
      expect(screen.getByTestId('selected-hypothesis-card')).toBeInTheDocument();
      expect(screen.getByTestId('selected-cost')).toHaveTextContent('$17,000');
      expect(screen.getByTestId('selected-rationale')).toHaveTextContent(/direct downside protection/i);
      expect(screen.getByTestId('council-rationale')).toHaveTextContent(/most protection per dollar/i);
    });
  });

  it('renders NotFoundPage (404 view) on unknown routes', () => {
    renderWithRouter('/unknown/route/does-not-exist');
    expect(screen.getByTestId('not-found-page')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /404 - page not found/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /return to dashboard/i })).toBeInTheDocument();
  });
});
