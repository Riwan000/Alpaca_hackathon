import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { Layout } from './Layout';
import { ThemeProvider } from '../theme/ThemeContext';

describe('Layout component', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.setAttribute('data-theme', 'light');
    document.documentElement.className = '';
  });

  it('renders brand masthead, navigation links, and content slot', () => {
    render(
      <ThemeProvider defaultTheme="light">
        <MemoryRouter initialEntries={['/']}>
          <Layout>
            <div data-testid="test-child">Child Content</div>
          </Layout>
        </MemoryRouter>
      </ThemeProvider>
    );

    expect(screen.getByText(/AEGIS \/\/ PRIVATE WEALTH/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /configuration/i })).toBeInTheDocument();
    expect(screen.getByTestId('test-child')).toHaveTextContent('Child Content');
    expect(screen.getByTestId('content-slot')).toBeInTheDocument();
  });

  it('theme toggle flips data-theme attribute and dark class on document root', async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider defaultTheme="light">
        <MemoryRouter>
          <Layout>
            <div>Dashboard Frame</div>
          </Layout>
        </MemoryRouter>
      </ThemeProvider>
    );

    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);

    const themeToggleBtn = screen.getByRole('button', { name: /toggle theme/i });
    expect(themeToggleBtn).toBeInTheDocument();

    // Click to toggle to dark
    await user.click(themeToggleBtn);
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);

    // Click again to toggle back to light
    await user.click(themeToggleBtn);
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });
});
