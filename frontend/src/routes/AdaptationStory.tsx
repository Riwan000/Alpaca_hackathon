import React from 'react';
import { Link } from 'react-router-dom';

export interface AdaptationStoryProps {
  initialHedgeRatio?: number;
  finalHedgeRatio?: number;
  initialVix?: number;
  stabilizedVix?: number;
}

export const AdaptationStory: React.FC<AdaptationStoryProps> = ({
  initialHedgeRatio = 0.80,
  finalHedgeRatio = 0.30,
  initialVix = 28.5,
  stabilizedVix = 16.2,
}) => {
  const deltaPct = (finalHedgeRatio - initialHedgeRatio) * 100;

  return (
    <div data-testid="adaptation-story" className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center px-2.5 py-0.5 rounded text-xs font-mono font-medium bg-indigo-950 text-indigo-400 border border-indigo-800 mb-2">
              BRD §37 Demo Scene 8
            </div>
            <h1 className="text-2xl font-bold text-white tracking-tight">
              Adaptive Rebalancing: Market Stabilization Narrative
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              Deterministic Level-1 trigger telemetry and Level-2 intelligent reassessment reducing downside carry cost as risk abates.
            </p>
          </div>
          <div className="flex items-center space-x-3">
            <Link
              to="/"
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium rounded-lg border border-slate-700 transition-colors"
            >
              Back to Dashboard
            </Link>
          </div>
        </div>
      </div>

      {/* Metrics Summary Strip */}
      <div data-testid="reduction-summary" className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="p-4 bg-slate-900 border border-slate-800 rounded-lg">
          <div className="text-xs text-slate-400 font-medium">Initial Turbulence Hedge</div>
          <div className="text-2xl font-mono font-bold text-amber-400 mt-1">
            {(initialHedgeRatio * 100).toFixed(0)}%
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">VIX peak {initialVix.toFixed(1)}</div>
        </div>
        <div className="p-4 bg-slate-900 border border-slate-800 rounded-lg">
          <div className="text-xs text-slate-400 font-medium">Stabilized Residual Hedge</div>
          <div className="text-2xl font-mono font-bold text-emerald-400 mt-1">
            {(finalHedgeRatio * 100).toFixed(0)}%
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">VIX normalized {stabilizedVix.toFixed(1)}</div>
        </div>
        <div className="p-4 bg-slate-900 border border-slate-800 rounded-lg">
          <div className="text-xs text-slate-400 font-medium">Hedge Coverage Delta</div>
          <div className="text-2xl font-mono font-bold text-cyan-400 mt-1">
            {deltaPct.toFixed(0)}%
          </div>
          <div className="text-[11px] text-emerald-400 mt-0.5">Risk premium recycled</div>
        </div>
        <div className="p-4 bg-slate-900 border border-slate-800 rounded-lg">
          <div className="text-xs text-slate-400 font-medium">Reassessment Action</div>
          <div className="text-2xl font-mono font-bold text-indigo-400 mt-1">
            DECREASE
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">Autonomous transition</div>
        </div>
      </div>

      {/* Narrative Stepper Timeline */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-6 space-y-6">
        <h2 className="text-lg font-semibold text-white">Chronological Adaptation Timeline</h2>

        <div className="space-y-6 relative before:absolute before:inset-0 before:left-3.5 before:w-0.5 before:bg-slate-800">
          {/* Step 1 */}
          <div data-testid="story-step-1" className="relative flex items-start space-x-4">
            <div className="w-7 h-7 rounded-full bg-amber-950 border border-amber-500 flex items-center justify-center shrink-0 z-10 text-amber-400 text-xs font-bold font-mono">
              1
            </div>
            <div className="flex-1 bg-slate-950/70 border border-slate-800 rounded-lg p-4">
              <div className="flex items-center justify-between mb-1">
                <h3 className="text-sm font-semibold text-amber-300">Phase 1: Volatility Shock & Initial Protection</h3>
                <span className="text-xs font-mono text-slate-500">T-0 hrs</span>
              </div>
              <p className="text-xs text-slate-300">
                Market turbulence triggered a <span className="font-mono text-amber-400">VOLATILITY_SPIKE</span> trigger as VIX surged to {initialVix}. Strategy manager selected a <strong>Protective Put</strong> strategy covering <strong>{(initialHedgeRatio * 100).toFixed(0)}%</strong> of portfolio equity.
              </p>
            </div>
          </div>

          {/* Step 2 */}
          <div data-testid="story-step-2" className="relative flex items-start space-x-4">
            <div className="w-7 h-7 rounded-full bg-blue-950 border border-blue-500 flex items-center justify-center shrink-0 z-10 text-blue-400 text-xs font-bold font-mono">
              2
            </div>
            <div className="flex-1 bg-slate-950/70 border border-slate-800 rounded-lg p-4">
              <div className="flex items-center justify-between mb-1">
                <h3 className="text-sm font-semibold text-blue-300">Phase 2: Stabilization & Trigger Crossing</h3>
                <span className="text-xs font-mono text-slate-500">T+4 hrs</span>
              </div>
              <p className="text-xs text-slate-300">
                Deterministic Level-1 monitoring registered IV dropping below threshold (VIX normalized to {stabilizedVix}) and portfolio drawdown recovering within deadband. Tripped <span className="font-mono text-cyan-400">VOLATILITY_FALL</span> event.
              </p>
            </div>
          </div>

          {/* Step 3 */}
          <div data-testid="story-step-3" className="relative flex items-start space-x-4">
            <div className="w-7 h-7 rounded-full bg-emerald-950 border border-emerald-500 flex items-center justify-center shrink-0 z-10 text-emerald-400 text-xs font-bold font-mono">
              3
            </div>
            <div className="flex-1 bg-slate-950/70 border border-slate-800 rounded-lg p-4">
              <div className="flex items-center justify-between mb-1">
                <h3 className="text-sm font-semibold text-emerald-300">Phase 3: Level-2 Reassessment & Order Sizing</h3>
                <span className="text-xs font-mono text-slate-500">T+4.5 hrs</span>
              </div>
              <p className="text-xs text-slate-300">
                Agent issued a <span className="font-mono font-bold text-emerald-400">DECREASE</span> decision, unlocking unused capital by unwinding 50% of the long put contracts. Risk engine approved the reduction, passing all liquidity and execution gates.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
