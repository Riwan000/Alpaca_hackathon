import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { ConfigurationPage } from '../pages/ConfigurationPage';
import { AppProviders } from '../providers';

describe('Configuration Page Component (P8-FE-4)', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders default configuration inputs and allows editing and saving to localStorage', () => {
    render(
      <AppProviders>
        <ConfigurationPage />
      </AppProviders>
    );

    expect(screen.getByTestId('configuration-page')).toBeInTheDocument();

    const ddInput = screen.getByTestId('input-drawdown-tolerance');
    const targetHedgeInput = screen.getByTestId('input-target-hedge');
    const saveBtn = screen.getByTestId('save-config-btn');

    // Change drawdown tolerance to 15%
    fireEvent.change(ddInput, { target: { value: '15' } });
    fireEvent.change(targetHedgeInput, { target: { value: '35' } });

    fireEvent.click(saveBtn);

    expect(screen.getByTestId('save-success-badge')).toHaveTextContent(/Saved Successfully/i);

    // Verify localStorage
    const saved = JSON.parse(localStorage.getItem('aegis_user_configuration') || '{}');
    expect(saved.drawdownTolerance).toBe(15);
    expect(saved.targetHedgeRatio).toBe(35);
  });

  it('validates invalid inputs and blocks saving', () => {
    render(
      <AppProviders>
        <ConfigurationPage />
      </AppProviders>
    );

    const ddInput = screen.getByTestId('input-drawdown-tolerance');
    const saveBtn = screen.getByTestId('save-config-btn');

    // Set invalid drawdown tolerance (e.g. -5% or 99%)
    fireEvent.change(ddInput, { target: { value: '99' } });
    fireEvent.click(saveBtn);

    expect(screen.getByTestId('validation-error')).toHaveTextContent(/Drawdown tolerance must be between 1% and 50%/i);
  });
});
