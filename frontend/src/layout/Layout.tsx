import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { useTheme } from '../theme/ThemeContext';
import { Shield, Settings, LayoutDashboard, Sun, Moon, Activity } from 'lucide-react';

export interface LayoutProps {
  children?: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  const { theme, toggleTheme } = useTheme();

  return (
    <div className="min-h-screen flex flex-col bg-[var(--bg-main)] text-[var(--text-main)] transition-colors duration-150">
      {/* Top Hairline Gold Accent */}
      <div className="h-[3px] w-full bg-[var(--brand-gold)]" />

      {/* Main Header / Masthead */}
      <header className="border-b border-[var(--border-color)] bg-[var(--bg-card)] px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="p-2 bg-[var(--brand-spruce)] text-white">
              <Shield className="w-5 h-5 text-[#A67C37]" />
            </div>
            <div>
              <div className="flex items-center gap-3">
                <span className="font-serif text-xl font-bold tracking-tight text-[var(--text-main)]">
                  AEGIS // PRIVATE WEALTH
                </span>
                <span className="text-[10px] font-mono uppercase px-2 py-0.5 border border-[var(--brand-teal)] text-[var(--brand-teal)] bg-[var(--brand-teal)]/10 flex items-center gap-1.5 font-semibold">
                  <span className="w-1.5 h-1.5 bg-[var(--brand-teal)] animate-pulse inline-block" />
                  Alpaca Paper Active
                </span>
              </div>
              <p className="text-xs text-[var(--text-muted)] font-sans">
                Autonomous Adaptive Portfolio Hedge Agent — Institutional Closed-Loop Risk Engine
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Status Telemetry Pill */}
            <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 border border-[var(--border-color)] bg-[var(--bg-subtle)] text-xs font-mono">
              <Activity className="w-3.5 h-3.5 text-[var(--brand-teal)]" />
              <span className="text-[var(--text-muted)]">Engine:</span>
              <span className="text-[var(--status-safe)] font-semibold">ONLINE</span>
            </div>

            {/* Theme Toggle Button */}
            <button
              onClick={toggleTheme}
              aria-label="Toggle theme"
              className="p-2 border border-[var(--border-color)] bg-[var(--bg-card)] hover:bg-[var(--bg-subtle-hover)] text-[var(--text-main)] transition-colors cursor-pointer"
              title={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
            >
              {theme === 'light' ? (
                <Moon className="w-4 h-4 text-[var(--brand-spruce)]" />
              ) : (
                <Sun className="w-4 h-4 text-[var(--brand-gold)]" />
              )}
            </button>
          </div>
        </div>
      </header>

      {/* Navigation Sub-Bar */}
      <nav className="border-b border-[var(--border-color)] bg-[var(--bg-card)] px-6">
        <div className="max-w-7xl mx-auto flex items-center gap-1">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              `flex items-center gap-2 px-4 py-3 text-xs font-mono font-medium tracking-wide uppercase transition-colors border-b-2 ${
                isActive
                  ? 'border-[var(--brand-spruce)] text-[var(--brand-spruce)] font-bold bg-[var(--bg-subtle)]/50'
                  : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-subtle)]/30'
              }`
            }
          >
            <LayoutDashboard className="w-3.5 h-3.5" />
            Dashboard
          </NavLink>

          <NavLink
            to="/configuration"
            className={({ isActive }) =>
              `flex items-center gap-2 px-4 py-3 text-xs font-mono font-medium tracking-wide uppercase transition-colors border-b-2 ${
                isActive
                  ? 'border-[var(--brand-spruce)] text-[var(--brand-spruce)] font-bold bg-[var(--bg-subtle)]/50'
                  : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-subtle)]/30'
              }`
            }
          >
            <Settings className="w-3.5 h-3.5" />
            Configuration
          </NavLink>
        </div>
      </nav>

      {/* Content Frame */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6" data-testid="content-slot">
        {children || <Outlet />}
      </main>

      {/* Institutional Footer */}
      <footer className="border-t border-[var(--border-color)] bg-[var(--bg-card)] px-6 py-3 text-center text-xs font-mono text-[var(--text-muted)]">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2">
          <span>AEGIS BOTANICAL // INSTITUTIONAL HEDGE SYSTEM</span>
          <span>BLACK-SCHOLES QUANT • LANGGRAPH CLOSED LOOP • ALPACA MCP</span>
        </div>
      </footer>
    </div>
  );
};
