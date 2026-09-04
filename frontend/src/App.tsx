import React from 'react';
import { Analytics } from '@vercel/analytics/react';
import { AppProviders } from './providers/AppProviders';
import { AppRoutes } from './routes';

export const App: React.FC = () => {
  return (
    <AppProviders withRouter={true}>
      <AppRoutes />
      <Analytics />
    </AppProviders>
  );
};

export default App;
