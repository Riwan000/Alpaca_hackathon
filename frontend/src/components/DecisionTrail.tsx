import React, { useState } from 'react';

export interface DecisionTrailData {
  order_id?: string | number;
  trade?: {
    symbol: string;
    action: string;
    qty: number;
    price: number;
    status: string;
    filled_at?: string;
  };
  risk?: {
    verdict: string;
    checks_passed: number;
    checks_total: number;
    rationale?: string;
  };
  strategy?: {
    strategy_type: string;
    action: string;
    rationale: string;
  };
  hypotheses?: Array<{
    strategy_type: string;
    verdict: string;
    rejection_reason?: string;
  }>;
  context?: {
    regime: string;
    vix?: number;
    drawdown?: number;
  };
  trigger?: {
    trigger_type: string;
    observed?: any;
    threshold?: any;
    fired_at?: string;
  };
}

export interface DecisionTrailProps {
  data?: DecisionTrailData | null;
  isLoading?: boolean;
}

export const DecisionTrail: React.FC<DecisionTrailProps> = ({
  data,
  isLoading = false,
}) => {
  const [expandedHop, setExpandedHop] = useState<string | null>(null);

  const toggleHop = (hopName: string) => {
    setExpandedHop((prev) => (prev === hopName ? null : hopName));
  };

  if (isLoading) {
    return (
      <div data-testid="decision-trail-loading" className="p-5 bg-slate-900 border border-slate-800 rounded-lg animate-pulse">
        <div className="h-6 bg-slate-800 rounded w-1/3 mb-4"></div>
        <div className="space-y-3">
          <div className="h-12 bg-slate-800 rounded"></div>
          <div className="h-12 bg-slate-800 rounded"></div>
          <div className="h-12 bg-slate-800 rounded"></div>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div data-testid="decision-trail-empty" className="p-6 bg-slate-900 border border-slate-800 rounded-lg text-center text-slate-500 text-sm">
        Select a trade from history or trigger a cycle to inspect the full lineage decision trail.
      </div>
    );
  }

  return (
    <div data-testid="decision-trail" className="bg-slate-900 border border-slate-800 rounded-lg p-5">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-5">
        <div>
          <h2 className="text-lg font-semibold text-white tracking-wide">Autonomous Decision Trail (Audit Drill-Down)</h2>
          <p className="text-xs text-slate-400">Complete provenance chain from market trigger to executed broker fill (BRD §18)</p>
        </div>
        {data.order_id && (
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-indigo-300 border border-indigo-900/60">
            Order #{data.order_id}
          </span>
        )}
      </div>

      <div className="space-y-4">
        {/* Hop 1: Trigger */}
        <div
          data-testid="hop-trigger"
          onClick={() => toggleHop('trigger')}
          className="p-3.5 rounded-lg bg-slate-950/70 border border-slate-800 hover:border-slate-700 cursor-pointer transition-colors"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2.5">
              <span className="w-5 h-5 rounded-full bg-amber-950 border border-amber-500 text-amber-400 flex items-center justify-center text-[10px] font-bold font-mono">
                1
              </span>
              <span className="text-sm font-semibold text-white">Originating Trigger</span>
              {data.trigger ? (
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-amber-950/60 text-amber-400 border border-amber-900">
                  {data.trigger.trigger_type}
                </span>
              ) : (
                <span className="text-xs text-slate-500 italic">No explicit trigger (scheduled/manual)</span>
              )}
            </div>
            <span className="text-xs text-slate-400 font-mono">{expandedHop === 'trigger' ? '▲' : '▼'}</span>
          </div>
          {expandedHop === 'trigger' && data.trigger && (
            <div className="mt-3 pt-3 border-t border-slate-800/80 text-xs text-slate-300 font-mono space-y-1">
              <div>Observed: {JSON.stringify(data.trigger.observed)}</div>
              <div>Threshold: {JSON.stringify(data.trigger.threshold)}</div>
              {data.trigger.fired_at && <div>Fired At: {data.trigger.fired_at}</div>}
            </div>
          )}
        </div>

        {/* Hop 2: Market Context */}
        <div
          data-testid="hop-context"
          onClick={() => toggleHop('context')}
          className="p-3.5 rounded-lg bg-slate-950/70 border border-slate-800 hover:border-slate-700 cursor-pointer transition-colors"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2.5">
              <span className="w-5 h-5 rounded-full bg-blue-950 border border-blue-500 text-blue-400 flex items-center justify-center text-[10px] font-bold font-mono">
                2
              </span>
              <span className="text-sm font-semibold text-white">Analysis & Market Context</span>
              {data.context && (
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-blue-950/60 text-blue-400 border border-blue-900">
                  Regime: {data.context.regime}
                </span>
              )}
            </div>
            <span className="text-xs text-slate-400 font-mono">{expandedHop === 'context' ? '▲' : '▼'}</span>
          </div>
          {expandedHop === 'context' && data.context && (
            <div className="mt-3 pt-3 border-t border-slate-800/80 text-xs text-slate-300 font-mono space-y-1">
              <div>VIX: {data.context.vix ?? '—'}</div>
              <div>Drawdown: {data.context.drawdown !== undefined ? `${(data.context.drawdown * 100).toFixed(2)}%` : '—'}</div>
            </div>
          )}
        </div>

        {/* Hop 3: Hypotheses */}
        <div
          data-testid="hop-hypotheses"
          onClick={() => toggleHop('hypotheses')}
          className="p-3.5 rounded-lg bg-slate-950/70 border border-slate-800 hover:border-slate-700 cursor-pointer transition-colors"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2.5">
              <span className="w-5 h-5 rounded-full bg-indigo-950 border border-indigo-500 text-indigo-400 flex items-center justify-center text-[10px] font-bold font-mono">
                3
              </span>
              <span className="text-sm font-semibold text-white">Strategy Hypotheses Generated</span>
              <span className="text-xs font-mono text-slate-400">({data.hypotheses?.length || 0} evaluated)</span>
            </div>
            <span className="text-xs text-slate-400 font-mono">{expandedHop === 'hypotheses' ? '▲' : '▼'}</span>
          </div>
          {expandedHop === 'hypotheses' && data.hypotheses && (
            <div className="mt-3 pt-3 border-t border-slate-800/80 space-y-2">
              {data.hypotheses.map((hyp, idx) => (
                <div key={idx} className="p-2 rounded bg-slate-900/60 border border-slate-800 flex items-center justify-between text-xs">
                  <div className="font-mono text-indigo-300">{hyp.strategy_type}</div>
                  <span className={`px-2 py-0.5 rounded font-mono text-[10px] ${
                    hyp.verdict === 'SELECTED' || hyp.verdict === 'ACCEPTED'
                      ? 'bg-emerald-950 text-emerald-400'
                      : 'bg-slate-800 text-slate-400'
                  }`}>
                    {hyp.verdict}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Hop 4: Strategy Decision */}
        <div
          data-testid="hop-strategy"
          onClick={() => toggleHop('strategy')}
          className="p-3.5 rounded-lg bg-slate-950/70 border border-slate-800 hover:border-slate-700 cursor-pointer transition-colors"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2.5">
              <span className="w-5 h-5 rounded-full bg-purple-950 border border-purple-500 text-purple-400 flex items-center justify-center text-[10px] font-bold font-mono">
                4
              </span>
              <span className="text-sm font-semibold text-white">Strategy Manager Decision</span>
              {data.strategy && (
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-purple-950/60 text-purple-300 border border-purple-900">
                  {data.strategy.strategy_type} ({data.strategy.action})
                </span>
              )}
            </div>
            <span className="text-xs text-slate-400 font-mono">{expandedHop === 'strategy' ? '▲' : '▼'}</span>
          </div>
          {expandedHop === 'strategy' && data.strategy && (
            <div className="mt-3 pt-3 border-t border-slate-800/80 text-xs text-slate-300">
              <p className="font-medium text-slate-400 mb-1">Rationale:</p>
              <p className="bg-slate-900 p-2.5 rounded border border-slate-800 font-mono text-[11px] text-slate-200">
                {data.strategy.rationale}
              </p>
            </div>
          )}
        </div>

        {/* Hop 5: Risk Gate Approval */}
        <div
          data-testid="hop-risk"
          onClick={() => toggleHop('risk')}
          className="p-3.5 rounded-lg bg-slate-950/70 border border-slate-800 hover:border-slate-700 cursor-pointer transition-colors"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2.5">
              <span className="w-5 h-5 rounded-full bg-emerald-950 border border-emerald-500 text-emerald-400 flex items-center justify-center text-[10px] font-bold font-mono">
                5
              </span>
              <span className="text-sm font-semibold text-white">Deterministic Risk Gate</span>
              {data.risk && (
                <span className={`text-xs font-mono px-2 py-0.5 rounded border ${
                  data.risk.verdict === 'APPROVE'
                    ? 'bg-emerald-950/60 text-emerald-400 border-emerald-900'
                    : 'bg-rose-950/60 text-rose-400 border-rose-900'
                }`}>
                  Verdict: {data.risk.verdict} ({data.risk.checks_passed}/{data.risk.checks_total} checks passed)
                </span>
              )}
            </div>
            <span className="text-xs text-slate-400 font-mono">{expandedHop === 'risk' ? '▲' : '▼'}</span>
          </div>
          {expandedHop === 'risk' && data.risk && (
            <div className="mt-3 pt-3 border-t border-slate-800/80 text-xs text-slate-300 font-mono space-y-1">
              {data.risk.rationale && <div>Rationale: {data.risk.rationale}</div>}
            </div>
          )}
        </div>

        {/* Hop 6: Executed Trade */}
        <div
          data-testid="hop-trade"
          onClick={() => toggleHop('trade')}
          className="p-3.5 rounded-lg bg-slate-950/70 border border-slate-800 hover:border-slate-700 cursor-pointer transition-colors"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2.5">
              <span className="w-5 h-5 rounded-full bg-cyan-950 border border-cyan-500 text-cyan-400 flex items-center justify-center text-[10px] font-bold font-mono">
                6
              </span>
              <span className="text-sm font-semibold text-white">Broker Order Execution</span>
              {data.trade && (
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-cyan-950/60 text-cyan-400 border border-cyan-900">
                  {data.trade.symbol} — {data.trade.status}
                </span>
              )}
            </div>
            <span className="text-xs text-slate-400 font-mono">{expandedHop === 'trade' ? '▲' : '▼'}</span>
          </div>
          {expandedHop === 'trade' && data.trade && (
            <div className="mt-3 pt-3 border-t border-slate-800/80 text-xs text-slate-300 font-mono space-y-1">
              <div>Action: {data.trade.action} {data.trade.qty} @ ${data.trade.price.toFixed(2)}</div>
              {data.trade.filled_at && <div>Filled At: {data.trade.filled_at}</div>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
