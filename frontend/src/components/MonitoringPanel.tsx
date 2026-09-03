import React from 'react';
import type { MonitoringEvent } from '../api/types';

export interface MonitoringPanelProps {
  events?: MonitoringEvent[];
  activeTriggers?: string[];
  isLoading?: boolean;
}

export const MonitoringPanel: React.FC<MonitoringPanelProps> = ({
  events = [],
  activeTriggers = [],
  isLoading = false,
}) => {
  if (isLoading) {
    return (
      <div data-testid="monitoring-panel-loading" className="p-4 bg-slate-900 border border-slate-800 rounded-lg animate-pulse">
        <div className="h-6 bg-slate-800 rounded w-1/3 mb-4"></div>
        <div className="h-16 bg-slate-800 rounded mb-4"></div>
        <div className="h-32 bg-slate-800 rounded"></div>
      </div>
    );
  }

  const sortedEvents = [...events].sort(
    (a, b) => new Date(b.fired_at).getTime() - new Date(a.fired_at).getTime()
  );

  return (
    <div data-testid="monitoring-panel" className="bg-slate-900 border border-slate-800 rounded-lg p-5">
      <div className="flex items-center justify-between pb-4 border-b border-slate-800 mb-4">
        <div>
          <h2 className="text-lg font-semibold text-white tracking-wide">Monitoring & Triggers</h2>
          <p className="text-xs text-slate-400">Deterministic Level-1 trigger telemetry and event logs</p>
        </div>
        <div>
          {activeTriggers.length === 0 ? (
            <span
              data-testid="all-clear-badge"
              className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-950 text-emerald-400 border border-emerald-800"
            >
              <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-emerald-400"></span>
              All Clear
            </span>
          ) : (
            <span
              data-testid="active-alert-badge"
              className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-amber-950 text-amber-400 border border-amber-800 animate-pulse"
            >
              <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-amber-400"></span>
              {activeTriggers.length} Active Trigger{activeTriggers.length > 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>

      {/* Active Triggers section */}
      <div className="mb-5">
        <h3 className="text-xs uppercase font-semibold text-slate-400 tracking-wider mb-2">Active Triggers</h3>
        {activeTriggers.length === 0 ? (
          <div data-testid="all-clear-message" className="p-3 bg-slate-950/60 border border-slate-800/80 rounded-md text-slate-400 text-sm flex items-center">
            <svg className="w-4 h-4 text-emerald-400 mr-2 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            No active triggers tripped. Portfolio operating within standard risk parameters.
          </div>
        ) : (
          <div className="space-y-2">
            {activeTriggers.map((trigger, idx) => (
              <div
                key={idx}
                data-testid="active-trigger-item"
                className="p-3 bg-amber-950/30 border border-amber-800/60 rounded-md text-amber-200 text-sm flex items-center justify-between"
              >
                <div className="flex items-center">
                  <span className="w-2 h-2 rounded-full bg-amber-400 mr-2.5"></span>
                  <span className="font-mono font-medium">{trigger}</span>
                </div>
                <span className="text-xs text-amber-400 uppercase tracking-wider font-semibold">Tripped</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Event History section */}
      <div>
        <h3 className="text-xs uppercase font-semibold text-slate-400 tracking-wider mb-2">Trigger Event History</h3>
        {sortedEvents.length === 0 ? (
          <div data-testid="empty-history" className="p-4 text-center text-slate-500 text-sm border border-dashed border-slate-800 rounded-md">
            No historical monitoring events recorded.
          </div>
        ) : (
          <div className="divide-y divide-slate-800/80 border border-slate-800 rounded-md overflow-hidden bg-slate-950/40">
            {sortedEvents.map((event) => (
              <div
                key={event.id}
                data-testid="event-row"
                className="p-3.5 hover:bg-slate-800/40 transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-2"
              >
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="font-mono text-sm font-semibold text-indigo-400">{event.trigger_type}</span>
                    <span className="text-xs text-slate-500">Cycle: {event.cycle_id}</span>
                  </div>
                  {event.observed && (
                    <div className="text-xs text-slate-400 mt-1 font-mono">
                      Observed: {JSON.stringify(event.observed)}
                      {event.threshold !== undefined && event.threshold !== null && (
                        <span className="ml-2 text-slate-500">| Threshold: {event.threshold}</span>
                      )}
                    </div>
                  )}
                </div>
                <div className="text-xs text-slate-400 shrink-0 font-mono">
                  {new Date(event.fired_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
