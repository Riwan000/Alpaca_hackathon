import React from 'react';
import { AppProviders } from './providers/AppProviders';
import { AppRoutes } from './routes';

export const App: React.FC = () => {
  return (
    <AppProviders withRouter={true}>
      <AppRoutes />
    </AppProviders>
  );
};

export default App;
