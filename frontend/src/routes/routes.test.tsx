import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from './index';
import { ThemeProvider } from '../theme/ThemeContext';

const renderWithRouter = (initialPath: string) => {
  return render(
    <ThemeProvider defaultTheme="light">
      <MemoryRouter initialEntries={[initialPath]}>
        <AppRoutes />
      </MemoryRouter>
    </ThemeProvider>
  );
};

describe('AppRoutes suite', () => {
  it('renders DashboardPage shell at "/"', () => {
    renderWithRouter('/');
    expect(screen.getByTestId('dashboard-page')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /portfolio risk & strategy dashboard/i })
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /portfolio vitals/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /strategy recommendation/i })).toBeInTheDocument();
  });

  it('renders ConfigurationPage shell at "/configuration"', () => {
    renderWithRouter('/configuration');
    expect(screen.getByTestId('configuration-page')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /agent & risk configuration/i })
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /risk preferences/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /hedge preferences/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /autonomy & monitoring/i })).toBeInTheDocument();
  });

  it('renders StrategyDetailsPage shell at "/strategy/:id" with dynamic ID', () => {
    renderWithRouter('/strategy/strat-test-456');
    expect(screen.getByTestId('strategy-details-page')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /strategy decision details/i })
    ).toBeInTheDocument();
    expect(screen.getByTestId('strategy-id-badge')).toHaveTextContent('ID: strat-test-456');
    expect(screen.getByRole('heading', { name: /selected: protective collar/i })).toBeInTheDocument();
  });

  it('renders NotFoundPage (404 view) on unknown routes', () => {
    renderWithRouter('/unknown/route/does-not-exist');
    expect(screen.getByTestId('not-found-page')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /404 - page not found/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /return to dashboard/i })).toBeInTheDocument();
  });
});
