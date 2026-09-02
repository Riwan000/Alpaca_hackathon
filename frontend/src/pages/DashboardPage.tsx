import React from 'react';
import { Link } from 'react-router-dom';
import { TrendingUp, Cpu, ArrowUpRight, BarChart3 } from 'lucide-react';

export const DashboardPage: React.FC = () => {
  return (
    <div className="space-y-6" data-testid="dashboard-page">
      {/* Page Title / Metric Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[var(--border-color)] pb-4">
        <div>
          <h1 className="text-2xl font-bold font-serif text-[var(--text-main)]">
            Portfolio Risk & Strategy Dashboard
          </h1>
          <p className="text-xs text-[var(--text-muted)] font-mono mt-1">
            REAL-TIME HEDGE METRICS • CONTINUOUS ADAPTIVE PROTECTION
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to="/strategy/strat-001"
            className="px-3 py-2 bg-[var(--brand-spruce)] text-white text-xs font-mono font-medium flex items-center gap-1 hover:bg-[#143225] transition-colors"
          >
            Inspect Strategy Details
            <ArrowUpRight className="w-3.5 h-3.5 text-[#A67C37]" />
          </Link>
        </div>
      </div>

      {/* 3-Column Terminal Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column (3 cols): Portfolio Vitals */}
        <section className="lg:col-span-3 border border-[var(--border-color)] bg-[var(--bg-card)] p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-2">
            <h2 className="text-sm font-serif font-bold text-[var(--text-main)] flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-[var(--brand-spruce)]" />
              Portfolio Vitals
            </h2>
            <span className="text-[10px] font-mono text-[var(--text-muted)]">AUM $250,000</span>
          </div>

          <div className="space-y-3">
            <div className="p-3 bg-[var(--bg-subtle)] border border-[var(--border-color)]">
              <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block">
                Target Protection Level
              </span>
              <span className="text-lg font-mono font-bold text-[var(--text-main)]">85.0%</span>
            </div>

            <div className="p-3 bg-[var(--bg-subtle)] border border-[var(--border-color)]">
              <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block">
                95% 1-Day VaR
              </span>
              <span className="text-lg font-mono font-bold text-[var(--status-warning)]">-2.65%</span>
            </div>

            <div className="p-3 bg-[var(--bg-subtle)] border border-[var(--border-color)]">
              <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase block">
                Portfolio Beta
              </span>
              <span className="text-lg font-mono font-bold text-[var(--text-main)]">1.12</span>
            </div>
          </div>
        </section>

        {/* Center Column (6 cols): Strategy Decision Room */}
        <section className="lg:col-span-6 border-t-gold-accent border border-[var(--border-color)] bg-[var(--bg-card)] p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-2">
            <div>
              <h2 className="text-base font-serif font-bold text-[var(--text-main)] flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-[var(--brand-gold)]" />
                Strategy Recommendation
              </h2>
              <span className="text-xs text-[var(--text-muted)] font-mono">
                Optimal Multi-Leg Options Structure
              </span>
            </div>
            <span className="px-2 py-1 bg-[var(--brand-spruce)] text-white text-[10px] font-mono font-bold">
              RECOMMENDED
            </span>
          </div>

          <div className="p-4 border border-[var(--brand-spruce)] bg-[var(--bg-subtle)]/60">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-xs font-mono font-bold text-[var(--brand-spruce)]">
                  PROTECTIVE COLLAR (SPY 540P / 565C)
                </span>
                <p className="text-xs text-[var(--text-muted)] mt-1">
                  Synthetic downside collar providing 85% downside protection while funding put premium via upside cap.
                </p>
              </div>
              <span className="text-xs font-mono font-bold text-[var(--status-safe)] bg-[var(--status-safe)]/10 px-2 py-0.5 border border-[var(--status-safe)]">
                +$140 Credit
              </span>
            </div>
          </div>

          <div className="grid grid-cols-4 gap-2 pt-2">
            <div className="p-2 border border-[var(--border-color)] text-center bg-[var(--bg-card)]">
              <span className="text-[10px] font-mono text-[var(--text-muted)] block">Delta (Δ)</span>
              <span className="text-xs font-mono font-bold text-[var(--brand-teal)]">-0.32</span>
            </div>
            <div className="p-2 border border-[var(--border-color)] text-center bg-[var(--bg-card)]">
              <span className="text-[10px] font-mono text-[var(--text-muted)] block">Gamma (Γ)</span>
              <span className="text-xs font-mono font-bold text-[var(--text-main)]">+0.014</span>
            </div>
            <div className="p-2 border border-[var(--border-color)] text-center bg-[var(--bg-card)]">
              <span className="text-[10px] font-mono text-[var(--text-muted)] block">Theta (Θ)</span>
              <span className="text-xs font-mono font-bold text-[var(--status-safe)]">+$18/d</span>
            </div>
            <div className="p-2 border border-[var(--border-color)] text-center bg-[var(--bg-card)]">
              <span className="text-[10px] font-mono text-[var(--text-muted)] block">Vega (ν)</span>
              <span className="text-xs font-mono font-bold text-[var(--text-main)]">-0.08</span>
            </div>
          </div>
        </section>

        {/* Right Column (3 cols): Multi-Agent Stream */}
        <section className="lg:col-span-3 border border-[var(--border-color)] bg-[var(--bg-card)] p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-2">
            <h2 className="text-sm font-serif font-bold text-[var(--text-main)] flex items-center gap-2">
              <Cpu className="w-4 h-4 text-[var(--brand-teal)]" />
              Agent Activity
            </h2>
            <span className="text-[10px] font-mono text-[var(--status-safe)] font-semibold">
              ● IDLE (CYCLE #1)
            </span>
          </div>

          <div className="space-y-2 text-xs font-mono">
            <div className="p-2 border-l-2 border-[var(--brand-spruce)] bg-[var(--bg-subtle)]">
              <span className="text-[10px] text-[var(--text-muted)] block">03:30:00 • Risk Agent</span>
              <span className="text-[var(--status-safe)] font-bold">APPROVED</span>
              <p className="text-[11px] text-[var(--text-muted)]">Margin requirement $0 within limits.</p>
            </div>

            <div className="p-2 border-l-2 border-[var(--brand-gold)] bg-[var(--bg-subtle)]">
              <span className="text-[10px] text-[var(--text-muted)] block">03:29:58 • Strategy Manager</span>
              <span className="text-[var(--text-main)] font-bold">SELECTED COLLAR</span>
              <p className="text-[11px] text-[var(--text-muted)]">Evaluated 3 competing hypotheses.</p>
            </div>

            <div className="p-2 border-l-2 border-[var(--brand-teal)] bg-[var(--bg-subtle)]">
              <span className="text-[10px] text-[var(--text-muted)] block">03:29:55 • Options Agent</span>
              <span className="text-[var(--text-main)]">Greeks Calculated</span>
              <p className="text-[11px] text-[var(--text-muted)]">Black-Scholes IV percentile 68%.</p>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};
