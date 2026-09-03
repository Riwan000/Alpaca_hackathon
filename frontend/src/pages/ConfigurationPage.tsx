import React from 'react';
import { Sliders, Shield, Cpu, Save, RefreshCw } from 'lucide-react';
import { useHedgeContext, useMonitoringState } from '../api/queries';

export const ConfigurationPage: React.FC = () => {
  const contextQuery = useHedgeContext();
  const monitoringQuery = useMonitoringState();

  const isLoading = contextQuery.isLoading || monitoringQuery.isLoading;
  const objective = contextQuery.data?.objective;

  return (
    <div className="space-y-6" data-testid="configuration-page">
      {/* Page Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[var(--border-color)] pb-4">
        <div>
          <h1 className="text-2xl font-bold font-serif text-[var(--text-main)]">
            Agent & Risk Configuration
          </h1>
          <p className="text-xs text-[var(--text-muted)] font-mono mt-1">
            RISK LIMITS • HEDGE PREFERENCES • AUTONOMY POLICIES
            {objective?.notes && ` • ${objective.notes.toUpperCase()}`}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {isLoading && (
            <span className="flex items-center gap-1 text-xs font-mono text-[var(--text-muted)]" data-testid="loading-indicator">
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              Loading Configuration...
            </span>
          )}
          <button
            disabled
            className="px-4 py-2 bg-[var(--brand-spruce)] text-white text-xs font-mono font-medium flex items-center gap-1.5 opacity-80 cursor-not-allowed"
          >
            <Save className="w-3.5 h-3.5 text-[#A67C37]" />
            Save Configuration
          </button>
        </div>
      </div>

      {/* Grid of Configuration Panels */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Risk Preferences */}
        <section className="border border-[var(--border-color)] bg-[var(--bg-card)] p-5 space-y-4">
          <div className="flex items-center gap-2 border-b border-[var(--border-color)] pb-2">
            <Shield className="w-4 h-4 text-[var(--brand-spruce)]" />
            <h2 className="text-sm font-serif font-bold text-[var(--text-main)]">
              Risk Preferences
            </h2>
          </div>

          <div className="space-y-3 text-xs">
            <div>
              <label className="text-[10px] font-mono uppercase text-[var(--text-muted)] block mb-1">
                Max Allowable Drawdown (%)
              </label>
              <input
                type="number"
                key={`dd-${objective?.drawdown_tolerance_pct}`}
                defaultValue={objective?.drawdown_tolerance_pct ? objective.drawdown_tolerance_pct * 100 : 10}
                className="w-full p-2 border border-[var(--border-color)] bg-[var(--bg-subtle)] font-mono text-xs text-[var(--text-main)]"
                readOnly
                data-testid="input-drawdown-tolerance"
              />
            </div>

            <div>
              <label className="text-[10px] font-mono uppercase text-[var(--text-muted)] block mb-1">
                Target Protection Ratio (%)
              </label>
              <input
                type="number"
                key={`th-${objective?.target_hedge_ratio}`}
                defaultValue={objective?.target_hedge_ratio ? objective.target_hedge_ratio * 100 : 20}
                className="w-full p-2 border border-[var(--border-color)] bg-[var(--bg-subtle)] font-mono text-xs text-[var(--text-main)]"
                readOnly
                data-testid="input-target-hedge"
              />
            </div>

            <div>
              <label className="text-[10px] font-mono uppercase text-[var(--text-muted)] block mb-1">
                Max Hedge Cost (% of AUM / cycle)
              </label>
              <input
                type="number"
                key={`hb-${objective?.max_hedge_budget_pct}`}
                defaultValue={objective?.max_hedge_budget_pct ? objective.max_hedge_budget_pct * 100 : 5}
                step="0.05"
                className="w-full p-2 border border-[var(--border-color)] bg-[var(--bg-subtle)] font-mono text-xs text-[var(--text-main)]"
                readOnly
                data-testid="input-max-budget"
              />
            </div>
          </div>
        </section>

        {/* Hedge Preferences */}
        <section className="border-t-gold-accent border border-[var(--border-color)] bg-[var(--bg-card)] p-5 space-y-4">
          <div className="flex items-center gap-2 border-b border-[var(--border-color)] pb-2">
            <Sliders className="w-4 h-4 text-[var(--brand-gold)]" />
            <h2 className="text-sm font-serif font-bold text-[var(--text-main)]">
              Hedge Preferences
            </h2>
          </div>

          <div className="space-y-3 text-xs">
            <div>
              <span className="text-[10px] font-mono uppercase text-[var(--text-muted)] block mb-2">
                Permitted Option Structures
              </span>
              <div className="space-y-2">
                <label className="flex items-center gap-2 font-mono text-xs">
                  <input type="checkbox" defaultChecked disabled />
                  <span>Protective Put</span>
                </label>
                <label className="flex items-center gap-2 font-mono text-xs">
                  <input type="checkbox" defaultChecked disabled />
                  <span>Bear Put Spread</span>
                </label>
                <label className="flex items-center gap-2 font-mono text-xs">
                  <input type="checkbox" defaultChecked disabled />
                  <span>Collar Structure</span>
                </label>
              </div>
            </div>

            <div>
              <label className="text-[10px] font-mono uppercase text-[var(--text-muted)] block mb-1">
                Target Expiration (DTE Range)
              </label>
              <input
                type="text"
                defaultValue="30 - 45 Days"
                className="w-full p-2 border border-[var(--border-color)] bg-[var(--bg-subtle)] font-mono text-xs text-[var(--text-main)]"
                readOnly
              />
            </div>
          </div>
        </section>

        {/* Autonomy Settings */}
        <section className="border border-[var(--border-color)] bg-[var(--bg-card)] p-5 space-y-4">
          <div className="flex items-center gap-2 border-b border-[var(--border-color)] pb-2">
            <Cpu className="w-4 h-4 text-[var(--brand-teal)]" />
            <h2 className="text-sm font-serif font-bold text-[var(--text-main)]">
              Autonomy & Monitoring
            </h2>
          </div>

          <div className="space-y-3 text-xs">
            <div>
              <span className="text-[10px] font-mono uppercase text-[var(--text-muted)] block mb-2">
                Execution Autonomy Mode
              </span>
              <div className="p-2 border border-[var(--brand-teal)] bg-[var(--brand-teal)]/10 text-xs font-mono font-bold text-[var(--brand-teal)]">
                Autonomous Paper Trading (Closed-Loop)
              </div>
            </div>

            <div>
              <label className="text-[10px] font-mono uppercase text-[var(--text-muted)] block mb-1">
                Monitoring Drift Trigger (%)
              </label>
              <input
                type="number"
                defaultValue={15}
                className="w-full p-2 border border-[var(--border-color)] bg-[var(--bg-subtle)] font-mono text-xs text-[var(--text-main)]"
                readOnly
              />
            </div>

            <div>
              <label className="text-[10px] font-mono uppercase text-[var(--text-muted)] block mb-1">
                Reassessment Cooldown (minutes)
              </label>
              <input
                type="number"
                defaultValue={30}
                className="w-full p-2 border border-[var(--border-color)] bg-[var(--bg-subtle)] font-mono text-xs text-[var(--text-main)]"
                readOnly
              />
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};
