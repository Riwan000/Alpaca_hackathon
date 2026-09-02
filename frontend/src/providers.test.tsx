import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { useQuery } from '@tanstack/react-query';
import { AppProviders, createQueryClient } from './providers';
import { useTheme } from './theme/ThemeContext';

const TestChildComponent: React.FC = () => {
  const { theme } = useTheme();
  const { data, isLoading } = useQuery({
    queryKey: ['test-query'],
    queryFn: async () => {
      return { status: 'ok', hedgeEngine: 'AEGIS' };
    },
  });

  return (
    <div>
      <div data-testid="child-mounted">Child Successfully Mounted</div>
      <div data-testid="theme-value">Active Theme: {theme}</div>
      {isLoading ? (
        <div data-testid="query-loading">Loading query...</div>
      ) : (
        <div data-testid="query-data">
          Query Result: {data?.hedgeEngine} ({data?.status})
        </div>
      )}
    </div>
  );
};

describe('AppProviders component', () => {
  it('mounts child component and provides React Query and Theme contexts', async () => {
    const queryClient = createQueryClient();

    render(
      <AppProviders queryClient={queryClient} defaultTheme="light">
        <TestChildComponent />
      </AppProviders>
    );

    // Verify child is mounted
    expect(screen.getByTestId('child-mounted')).toHaveTextContent('Child Successfully Mounted');
    expect(screen.getByTestId('theme-value')).toHaveTextContent('Active Theme: light');

    // Verify component successfully reads from React Query
    await waitFor(() => {
      expect(screen.getByTestId('query-data')).toHaveTextContent('Query Result: AEGIS (ok)');
    });
  });
});
