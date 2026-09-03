/**
 * Vitest + React Testing Library + MSW Sanity Test — Task P1-FE-9 (Git Issue #43).
 *
 * Proves that:
 * 1. Testing Library `render` mounts components.
 * 2. MSW intercepts HTTP requests and returns mock JSON data.
 * 3. React Query async data fetching resolves within the DOM.
 */

import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { useQuery } from '@tanstack/react-query';
import { AppProviders } from '../providers/AppProviders';
import { apiClient } from '../api/client';
import type { HealthResponse } from '../api/types';

const HealthWidget: React.FC = () => {
  const { data, isLoading, error } = useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: () => apiClient.get<HealthResponse>('/health'),
  });

  if (isLoading) return <div data-testid="loading">Checking system health...</div>;
  if (error) return <div data-testid="error">Error loading health</div>;
  if (!data) return null;

  return (
    <div data-testid="health-card">
      <span data-testid="status">{data.status}</span>
      <span data-testid="version">{data.version}</span>
      <span data-testid="env">{data.build.environment}</span>
    </div>
  );
};

describe('Sanity Test Suite (P1-FE-9)', () => {
  it('renders component and resolves MSW mock handler for /health', async () => {
    render(
      <AppProviders>
        <HealthWidget />
      </AppProviders>
    );

    expect(screen.getByTestId('loading')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('health-card')).toBeInTheDocument();
    });

    expect(screen.getByTestId('status')).toHaveTextContent('healthy');
    expect(screen.getByTestId('version')).toHaveTextContent('0.1.0');
    expect(screen.getByTestId('env')).toHaveTextContent('development');
  });
});
