import React, { useState, useEffect } from 'react';
import { Sliders, Shield, Cpu, Save, Check } from 'lucide-react';
import { useHedgeContext } from '../api/queries';

export const CONFIG_STORAGE_KEY = 'aegis_user_configuration';

export interface UserConfiguration {
  alpacaAccountId?: string;
  drawdownTolerance: number;
  targetHedgeRatio: number;
  maxBudget: number;
  deadbandBuffer: number;
  autonomyMode: 'FULL_AUTONOMY' | 'HUMAN_IN_THE_LOOP' | 'ADVISORY';
  permittedStructures: {
    protectivePut: boolean;
    bearPutSpread: boolean;
    collar: boolean;
  };
}

export const DEFAULT_CONFIG: UserConfiguration = {
  alpacaAccountId: '',
  drawdownTolerance: 10,
  targetHedgeRatio: 20,
  maxBudget: 5,
  deadbandBuffer: 5,
  autonomyMode: 'FULL_AUTONOMY',
  permittedStructures: {
    protectivePut: true,
    bearPutSpread: true,
    collar: true,
  },
};

export function getUserConfiguration(): UserConfiguration {
  try {
    const saved = localStorage.getItem(CONFIG_STORAGE_KEY);
    if (saved) {
      return { ...DEFAULT_CONFIG, ...JSON.parse(saved) };
    }
  } catch {
    // ignore
  }
  return DEFAULT_CONFIG;
}

export const ConfigurationPage: React.FC = () => {
  const contextQuery = useHedgeContext();

  const [config, setConfig] = useState<UserConfiguration>(getUserConfiguration);

  const [savedSuccess, setSavedSuccess] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  // Sync initial defaults from backend query if not yet customized in localStorage
  useEffect(() => {
    if (contextQuery.data?.objective && !localStorage.getItem(CONFIG_STORAGE_KEY)) {
      const obj = contextQuery.data.objective;
      setConfig((prev) => ({
        ...prev,
        drawdownTolerance: obj.drawdown_tolerance_pct ? obj.drawdown_tolerance_pct * 100 : prev.drawdownTolerance,
        targetHedgeRatio: obj.target_hedge_ratio ? obj.target_hedge_ratio * 100 : prev.targetHedgeRatio,
        maxBudget: obj.max_hedge_budget_pct ? obj.max_hedge_budget_pct * 100 : prev.maxBudget,
      }));
    }
  }, [contextQuery.data]);

  const handleSave = () => {
    // Validate
    if (config.drawdownTolerance <= 0 || config.drawdownTolerance > 50) {
      setValidationError('Drawdown tolerance must be between 1% and 50%.');
      return;
    }
    if (config.targetHedgeRatio < 0 || config.targetHedgeRatio > 100) {
      setValidationError('Target hedge ratio must be between 0% and 100%.');
      return;
    }
    if (config.maxBudget <= 0 || config.maxBudget > 25) {
      setValidationError('Max hedge budget must be between 0.1% and 25%.');
      return;
    }
    if (config.deadbandBuffer < 1 || config.deadbandBuffer > 20) {
      setValidationError('Deadband buffer must be between 1% and 20%.');
      return;
    }

    setValidationError(null);
    localStorage.setItem(CONFIG_STORAGE_KEY, JSON.stringify(config));
    window.dispatchEvent(new CustomEvent('aegis-config-updated', { detail: config }));
    window.dispatchEvent(new Event('storage'));
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 3000);
  };

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
          </p>
        </div>
        <div className="flex items-center gap-3">
          {savedSuccess && (
            <span data-testid="save-success-badge" className="inline-flex items-center gap-1.5 px-3 py-1 rounded bg-[var(--status-safe)]/10 text-[var(--status-safe)] border border-[var(--status-safe)]/30 text-xs font-mono">
              <Check className="w-3.5 h-3.5" />
              Saved Successfully!
            </span>
          )}
          <button
            type="button"
            data-testid="save-config-btn"
            onClick={handleSave}
            className="px-4 py-2 bg-[var(--brand-spruce)] hover:bg-[#143225] text-white text-xs font-mono font-medium flex items-center gap-1.5 rounded transition-colors shadow-sm"
          >
            <Save className="w-3.5 h-3.5 text-white" />
            Save Configuration
          </button>
        </div>
      </div>

      {validationError && (
        <div data-testid="validation-error" className="p-3 bg-[var(--status-danger)]/10 border border-[var(--status-danger)]/30 rounded text-rose-300 text-xs font-mono">
          {validationError}
        </div>
      )}

      {/* Grid of Configuration Panels */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Risk Preferences */}
        <section className="border border-[var(--border-color)] bg-[var(--bg-card)] rounded-lg p-5 space-y-4">
          <div className="flex items-center gap-2 border-b border-[var(--border-color)] pb-2">
            <Shield className="w-4 h-4 text-[var(--status-safe)]" />
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
                value={config.drawdownTolerance}
                onChange={(e) => setConfig({ ...config, drawdownTolerance: parseFloat(e.target.value) || 0 })}
                className="w-full p-2 border border-[var(--border-color)] bg-[var(--bg-subtle)] rounded font-mono text-xs text-[var(--text-main)] focus:outline-none focus:border-indigo-500"
                data-testid="input-drawdown-tolerance"
              />
            </div>

            <div>
              <label className="text-[10px] font-mono uppercase text-[var(--text-muted)] block mb-1">
                Target Protection Ratio (%)
              </label>
              <input
                type="number"
                value={config.targetHedgeRatio}
                onChange={(e) => setConfig({ ...config, targetHedgeRatio: parseFloat(e.target.value) || 0 })}
                className="w-full p-2 border border-[var(--border-color)] bg-[var(--bg-subtle)] rounded font-mono text-xs text-[var(--text-main)] focus:outline-none focus:border-indigo-500"
                data-testid="input-target-hedge"
              />
            </div>

            <div>
              <label className="text-[10px] font-mono uppercase text-[var(--text-muted)] block mb-1">
                Max Hedge Cost (% of AUM / cycle)
              </label>
              <input
                type="number"
                step="0.5"
                value={config.maxBudget}
                onChange={(e) => setConfig({ ...config, maxBudget: parseFloat(e.target.value) || 0 })}
                className="w-full p-2 border border-[var(--border-color)] bg-[var(--bg-subtle)] rounded font-mono text-xs text-[var(--text-main)] focus:outline-none focus:border-indigo-500"
                data-testid="input-max-budget"
              />
            </div>
          </div>
        </section>

        {/* Hedge Preferences */}
        <section className="border border-[var(--border-color)] bg-[var(--bg-card)] rounded-lg p-5 space-y-4">
          <div className="flex items-center gap-2 border-b border-[var(--border-color)] pb-2">
            <Sliders className="w-4 h-4 text-amber-400" />
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
                <label className="flex items-center gap-2 font-mono text-xs text-[var(--text-main)]">
                  <input
                    type="checkbox"
                    checked={config.permittedStructures.protectivePut}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        permittedStructures: { ...config.permittedStructures, protectivePut: e.target.checked },
                      })
                    }
                    data-testid="checkbox-protective-put"
                  />
                  <span>Protective Put</span>
                </label>
                <label className="flex items-center gap-2 font-mono text-xs text-[var(--text-main)]">
                  <input
                    type="checkbox"
                    checked={config.permittedStructures.bearPutSpread}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        permittedStructures: { ...config.permittedStructures, bearPutSpread: e.target.checked },
                      })
                    }
                    data-testid="checkbox-put-spread"
                  />
                  <span>Bear Put Spread</span>
                </label>
                <label className="flex items-center gap-2 font-mono text-xs text-[var(--text-main)]">
                  <input
                    type="checkbox"
                    checked={config.permittedStructures.collar}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        permittedStructures: { ...config.permittedStructures, collar: e.target.checked },
                      })
                    }
                    data-testid="checkbox-collar"
                  />
                  <span>Collar Structure</span>
                </label>
              </div>
            </div>

            <div>
              <label className="text-[10px] font-mono uppercase text-[var(--text-muted)] block mb-1">
                Deadband Buffer (%)
              </label>
              <input
                type="number"
                value={config.deadbandBuffer}
                onChange={(e) => setConfig({ ...config, deadbandBuffer: parseFloat(e.target.value) || 0 })}
                className="w-full p-2 border border-[var(--border-color)] bg-[var(--bg-subtle)] rounded font-mono text-xs text-[var(--text-main)] focus:outline-none focus:border-indigo-500"
                data-testid="input-deadband"
              />
            </div>
          </div>
        </section>

        {/* Autonomy Settings */}
        <section className="border border-[var(--border-color)] bg-[var(--bg-card)] rounded-lg p-5 space-y-4">
          <div className="flex items-center gap-2 border-b border-[var(--border-color)] pb-2">
            <Cpu className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-serif font-bold text-[var(--text-main)]">
              Autonomy & Policies
            </h2>
          </div>

          <div className="space-y-3 text-xs">
            <div>
              <label className="text-[10px] font-mono uppercase text-[var(--text-muted)] block mb-1">
                Alpaca Account ID / Number (Optional)
              </label>
              <input
                type="text"
                placeholder="e.g. PA3C0P4T6AJE or b78de2d5-..."
                value={config.alpacaAccountId || ''}
                onChange={(e) => setConfig({ ...config, alpacaAccountId: e.target.value.trim() })}
                className="w-full p-2 border border-[var(--border-color)] bg-[var(--bg-subtle)] rounded font-mono text-xs text-[var(--text-main)] focus:outline-none focus:border-indigo-500"
                data-testid="input-alpaca-account-id"
              />
              <span className="text-[10px] text-[var(--text-muted)] font-mono block mt-0.5">
                Leave blank to use default account from server credentials.
              </span>
            </div>

            <div>
              <label className="text-[10px] font-mono uppercase text-[var(--text-muted)] block mb-2">
                Execution Autonomy Mode
              </label>
              <select
                data-testid="select-autonomy-mode"
                value={config.autonomyMode}
                onChange={(e) =>
                  setConfig({
                    ...config,
                    autonomyMode: e.target.value as UserConfiguration['autonomyMode'],
                  })
                }
                className="w-full p-2 border border-[var(--border-color)] bg-[var(--bg-subtle)] rounded font-mono text-xs text-[var(--text-main)] focus:outline-none focus:border-indigo-500"
              >
                <option value="FULL_AUTONOMY">Full Autonomy (Execute on Approval)</option>
                <option value="HUMAN_IN_THE_LOOP">Human in the Loop (Require Confirmation)</option>
                <option value="ADVISORY">Advisory Only (No Trade Execution)</option>
              </select>
            </div>

            <div className="p-3 bg-[var(--bg-subtle)]/70 border border-[var(--border-color)]/80 rounded text-xs text-[var(--text-muted)]">
              <span className="font-semibold text-[var(--text-main)]">Policy: </span>
              {config.autonomyMode === 'FULL_AUTONOMY'
                ? 'Autonomous paper trading enabled. Agent executes approved hedges directly via Alpaca broker.'
                : config.autonomyMode === 'HUMAN_IN_THE_LOOP'
                ? 'Trades are prepared and validated, but require manual confirmation before sending.'
                : 'Agent provides analysis and recommendations without order placement.'}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};
