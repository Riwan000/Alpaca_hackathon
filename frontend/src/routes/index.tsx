import React from 'react';
import { Routes, Route } from 'react-router-dom';
import { Layout } from '../layout/Layout';
import { DashboardPage } from '../pages/DashboardPage';
import { ConfigurationPage } from '../pages/ConfigurationPage';
import { StrategyDetailsPage } from '../pages/StrategyDetailsPage';
import { NotFoundPage } from '../pages/NotFoundPage';

export const AppRoutes: React.FC = () => {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="configuration" element={<ConfigurationPage />} />
        <Route path="strategy/:id" element={<StrategyDetailsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
};
