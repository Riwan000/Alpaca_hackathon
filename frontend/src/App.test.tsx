import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import App from './App';

describe('App root component', () => {
  it('renders without crashing and displays the header and dashboard', () => {
    render(<App />);

    expect(screen.getByText(/AEGIS \/\/ PRIVATE WEALTH/i)).toBeInTheDocument();
    expect(screen.getByTestId('dashboard-page')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /portfolio risk & strategy dashboard/i })
    ).toBeInTheDocument();
  });
});
