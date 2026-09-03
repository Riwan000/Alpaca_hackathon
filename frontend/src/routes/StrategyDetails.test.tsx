import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AppProviders } from '../providers/AppProviders';
import { StrategyDetailsPage } from '../pages/StrategyDetailsPage';

describe('StrategyDetails Route & Page (P4-FE-3, P4-FE-4)', () => {
  it('loads hypothesis data for /strategy/:id and renders PayoffChart and Greeks', async () => {
    render(
      <AppProviders>
        <MemoryRouter initialEntries={['/strategy/cyc-001']}>
          <Routes>
            <Route path="/strategy/:id" element={<StrategyDetailsPage />} />
          </Routes>
        </MemoryRouter>
      </AppProviders>
    );

    expect(screen.getByTestId('strategy-details-page')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('strategy-cost')).toHaveTextContent('$17,000');
    });

    expect(screen.getByTestId('strategy-protection')).toHaveTextContent('90.0%');
    expect(screen.getByTestId('strategy-breakeven')).toHaveTextContent('$491.5');
    expect(screen.getByTestId('payoff-chart')).toBeInTheDocument();
    expect(screen.getByTestId('greeks-grid')).toBeInTheDocument();
    expect(screen.getByTestId('strategy-legs-table')).toBeInTheDocument();
  });
});
