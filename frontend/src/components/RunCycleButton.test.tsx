import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { RunCycleButton } from './RunCycleButton';
import { AppProviders } from '../providers/AppProviders';

const renderWithProviders = (ui: React.ReactElement) => {
  return render(<AppProviders>{ui}</AppProviders>);
};

describe('RunCycleButton Component (P6-FE-3)', () => {
  it('renders active button when not running and triggers cycle mutation on click', async () => {
    const handleTriggered = vi.fn();
    renderWithProviders(<RunCycleButton onCycleTriggered={handleTriggered} />);

    const button = screen.getByTestId('run-cycle-button');
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent(/run autonomous cycle/i);
    expect(button).not.toBeDisabled();

    fireEvent.click(button);

    await waitFor(() => {
      expect(screen.getByTestId('cycle-success-feedback')).toBeInTheDocument();
      expect(handleTriggered).toHaveBeenCalledWith('cyc-002');
    });
  });

  it('locks and disables button when isRunning is true', () => {
    renderWithProviders(<RunCycleButton isRunning={true} />);

    const button = screen.getByTestId('run-cycle-button');
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent(/cycle executing/i);
  });
});
