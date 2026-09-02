import React, { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider, Theme } from '../theme/ThemeContext';

export interface AppProvidersProps {
  children: React.ReactNode;
  queryClient?: QueryClient;
  withRouter?: boolean;
  defaultTheme?: Theme;
}

export const createQueryClient = (): QueryClient => {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 1000 * 60 * 5, // 5 minutes
        retry: 1,
        refetchOnWindowFocus: false,
      },
    },
  });
};

export const AppProviders: React.FC<AppProvidersProps> = ({
  children,
  queryClient: customQueryClient,
  withRouter = false,
  defaultTheme = 'light',
}) => {
  // Use custom client if provided, or initialize stateful client
  const [queryClient] = useState(() => customQueryClient || createQueryClient());

  const content = (
    <QueryClientProvider client={customQueryClient || queryClient}>
      <ThemeProvider defaultTheme={defaultTheme}>{children}</ThemeProvider>
    </QueryClientProvider>
  );

  if (withRouter) {
    return <BrowserRouter>{content}</BrowserRouter>;
  }

  return content;
};
