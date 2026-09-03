import React from 'react';

export interface HedgeDriftGaugeProps {
  currentHedgeRatio: number;
  targetHedgeRatio: number;
  deadband?: number; // e.g. 0.05 for 5% deadband
}

export const HedgeDriftGauge: React.FC<HedgeDriftGaugeProps> = ({
  currentHedgeRatio,
  targetHedgeRatio,
  deadband = 0.05,
}) => {
  const drift = currentHedgeRatio - targetHedgeRatio;
  const absDrift = Math.abs(drift);
  const isWithinDeadband = absDrift <= deadband;

  // Max scale from 0 to 1.0 (or 100%)
  const clampRatio = (val: number) => Math.min(Math.max(val, 0), 1);
  const currentPct = clampRatio(currentHedgeRatio) * 100;
  const targetPct = clampRatio(targetHedgeRatio) * 100;

  const deadbandLowerPct = clampRatio(targetHedgeRatio - deadband) * 100;
  const deadbandUpperPct = clampRatio(targetHedgeRatio + deadband) * 100;
  const deadbandWidthPct = deadbandUpperPct - deadbandLowerPct;

  return (
    <div
      data-testid="hedge-drift-gauge"
      className={`p-5 rounded-lg border bg-slate-900 ${
        isWithinDeadband ? 'border-slate-800' : 'border-amber-800/80'
      }`}
    >
      <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
        <div>
          <h3 className="text-base font-semibold text-white">Hedge Drift Gauge</h3>
          <p className="text-xs text-slate-400">Current coverage vs target hedge ratio & deadband</p>
        </div>
        <div>
          {isWithinDeadband ? (
            <span
              data-testid="drift-status-badge"
              className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-950 text-emerald-400 border border-emerald-800"
            >
              <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-emerald-400"></span>
              Calm (Within Deadband)
            </span>
          ) : (
            <span
              data-testid="drift-status-badge"
              className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-amber-950 text-amber-400 border border-amber-800 animate-pulse"
            >
              <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-amber-400"></span>
              Alert (Drift: {(drift > 0 ? '+' : '') + (drift * 100).toFixed(1)}%)
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-5 text-center">
        <div className="p-3 bg-slate-950/60 rounded border border-slate-800">
          <div className="text-xs text-slate-400 font-medium">Current Ratio</div>
          <div data-testid="current-hedge-value" className="text-lg font-mono font-bold text-cyan-400">
            {(currentHedgeRatio * 100).toFixed(1)}%
          </div>
        </div>
        <div className="p-3 bg-slate-950/60 rounded border border-slate-800">
          <div className="text-xs text-slate-400 font-medium">Target Ratio</div>
          <div data-testid="target-hedge-value" className="text-lg font-mono font-bold text-indigo-400">
            {(targetHedgeRatio * 100).toFixed(1)}%
          </div>
        </div>
        <div className="p-3 bg-slate-950/60 rounded border border-slate-800">
          <div className="text-xs text-slate-400 font-medium">Deadband Buffer</div>
          <div className="text-lg font-mono font-bold text-slate-300">
            ±{(deadband * 100).toFixed(0)}%
          </div>
        </div>
      </div>

      {/* Visual Gauge Bar */}
      <div className="relative pt-6 pb-2">
        {/* Scale labels */}
        <div className="flex justify-between text-[11px] font-mono text-slate-500 mb-1.5">
          <span>0%</span>
          <span>50%</span>
          <span>100%</span>
        </div>

        {/* Track */}
        <div className="h-4 bg-slate-950 border border-slate-800 rounded-full relative overflow-hidden">
          {/* Deadband corridor */}
          <div
            className="absolute top-0 bottom-0 bg-slate-800/70 border-x border-slate-700/50"
            style={{
              left: `${deadbandLowerPct}%`,
              width: `${deadbandWidthPct}%`,
            }}
          />
        </div>

        {/* Target marker */}
        <div
          data-testid="target-marker"
          className="absolute top-4 -translate-x-1/2 flex flex-col items-center"
          style={{ left: `${targetPct}%` }}
        >
          <div className="text-[10px] font-mono font-semibold text-indigo-400 bg-slate-900 px-1 rounded border border-indigo-800/80 mb-0.5">
            Target
          </div>
          <div className="w-1 h-5 bg-indigo-500 rounded-full shadow-sm shadow-indigo-500/50"></div>
        </div>

        {/* Current Needle */}
        <div
          data-testid="gauge-needle"
          className="absolute top-10 -translate-x-1/2 flex flex-col items-center"
          style={{ left: `${currentPct}%` }}
        >
          <div className={`w-3 h-3 rotate-45 ${isWithinDeadband ? 'bg-emerald-400 shadow-emerald-500/50' : 'bg-amber-400 shadow-amber-500/50'} shadow-sm`}></div>
          <div className={`text-[10px] font-mono font-bold ${isWithinDeadband ? 'text-emerald-400' : 'text-amber-400'} mt-1`}>
            Current ({(currentHedgeRatio * 100).toFixed(0)}%)
          </div>
        </div>
      </div>
    </div>
  );
};
