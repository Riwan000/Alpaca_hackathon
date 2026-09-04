import React from 'react';
import { RotateCcw, CheckCircle2 } from 'lucide-react';

export interface DemoWalkthroughProps {
  onReset?: () => void;
  activeStep?: number;
}

export const DemoWalkthrough: React.FC<DemoWalkthroughProps> = ({
  onReset,
  activeStep = 1,
}) => {
  const steps = [
    { title: 'Baseline State', desc: 'Equity portfolio monitored within standard risk bounds' },
    { title: 'Volatility Spike', desc: 'Market turbulence trips Level-1 trigger & initiates hedge' },
    { title: 'Protective Put Fill', desc: 'Downside coverage locked in via Alpaca paper execution' },
    { title: 'Stabilization Rebalance', desc: 'Risk abates; autonomous Level-2 reassessment reduces hedge' },
  ];

  return (
    <div data-testid="demo-walkthrough" className="p-4 bg-[var(--bg-card)] border border-[var(--border-color)] rounded-lg">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3 pb-3 border-b border-[var(--border-color)]">
        <div className="flex items-center space-x-2">
          <span className="w-2 h-2 rounded-full bg-indigo-400 animate-ping"></span>
          <h3 className="text-sm font-semibold text-[var(--text-main)]">Deterministic Demo Script & Narrative Flow</h3>
        </div>
        <button
          type="button"
          data-testid="reset-demo-btn"
          onClick={onReset}
          className="text-xs font-mono px-3 py-1 rounded bg-[var(--bg-subtle)] hover:bg-[var(--bg-subtle-hover)] text-[var(--text-main)] border border-[var(--border-dark)] transition-colors flex items-center space-x-1.5 self-start sm:self-auto"
        >
          <RotateCcw className="w-3.5 h-3.5 text-amber-400" />
          <span>Reset Demo State</span>
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
        {steps.map((step, idx) => {
          const stepNum = idx + 1;
          const isDone = stepNum < activeStep;
          const isCurrent = stepNum === activeStep;
          return (
            <div
              key={idx}
              className={`p-2.5 rounded border text-xs ${
                isCurrent
                  ? 'bg-indigo-950/40 border-indigo-700 text-indigo-200'
                  : isDone
                  ? 'bg-[var(--status-safe)]/10 border-[var(--status-safe)]/30 text-[var(--text-main)]'
                  : 'bg-[var(--bg-subtle)]/40 border-[var(--border-color)] text-[var(--text-muted)]'
              }`}
            >
              <div className="flex items-center justify-between mb-1 font-mono font-semibold">
                <span>Scene {stepNum}</span>
                {isDone && <CheckCircle2 className="w-3.5 h-3.5 text-[var(--status-safe)]" />}
                {isCurrent && <span className="w-1.5 h-1.5 rounded-full bg-indigo-400"></span>}
              </div>
              <div className="font-medium text-[var(--text-main)] mb-0.5">{step.title}</div>
              <div className="text-[11px] text-[var(--text-muted)] leading-tight">{step.desc}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
