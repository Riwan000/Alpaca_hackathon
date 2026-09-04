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
      <div data-testid="monitoring-panel-loading" className="p-4 bg-[var(--bg-card)] border border-[var(--border-color)] rounded-lg animate-pulse">
        <div className="h-6 bg-[var(--bg-subtle)] rounded w-1/3 mb-4"></div>
        <div className="h-16 bg-[var(--bg-subtle)] rounded mb-4"></div>
        <div className="h-32 bg-[var(--bg-subtle)] rounded"></div>
      </div>
    );
  }

  const sortedEvents = [...events].sort(
    (a, b) => new Date(b.fired_at).getTime() - new Date(a.fired_at).getTime()
  );

  return (
    <div data-testid="monitoring-panel" className="bg-[var(--bg-card)] border border-[var(--border-color)] rounded-lg p-5">
      <div className="flex items-center justify-between pb-4 border-b border-[var(--border-color)] mb-4">
        <div>
          <h2 className="text-lg font-semibold text-[var(--text-main)] tracking-wide">Monitoring & Triggers</h2>
          <p className="text-xs text-[var(--text-muted)]">Deterministic Level-1 trigger telemetry and event logs</p>
        </div>
        <div>
          {activeTriggers.length === 0 ? (
            <span
              data-testid="all-clear-badge"
              className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-[var(--status-safe)]/10 text-[var(--status-safe)] border border-[var(--status-safe)]/30"
            >
              <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-[var(--status-safe)]"></span>
              All Clear
            </span>
          ) : (
            <span
              data-testid="active-alert-badge"
              className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-[var(--status-warning)]/10 text-[var(--status-warning)] border border-[var(--status-warning)]/40 animate-pulse"
            >
              <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-[var(--status-warning)]"></span>
              {activeTriggers.length} Active Trigger{activeTriggers.length > 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>

      {/* Active Triggers section */}
      <div className="mb-5">
        <h3 className="text-xs uppercase font-semibold text-[var(--text-muted)] tracking-wider mb-2">Active Triggers</h3>
        {activeTriggers.length === 0 ? (
          <div data-testid="all-clear-message" className="p-3 bg-[var(--bg-subtle)]/60 border border-[var(--border-color)]/80 rounded-md text-[var(--text-muted)] text-sm flex items-center">
            <svg className="w-4 h-4 text-[var(--status-safe)] mr-2 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
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
                className="p-3 bg-[var(--status-warning)]/10 border border-[var(--status-warning)]/40 rounded-md text-[var(--text-main)] text-sm flex items-center justify-between"
              >
                <div className="flex items-center">
                  <span className="w-2 h-2 rounded-full bg-[var(--status-warning)] mr-2.5"></span>
                  <span className="font-mono font-medium">{trigger}</span>
                </div>
                <span className="text-xs text-[var(--status-warning)] uppercase tracking-wider font-semibold">Tripped</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Event History section */}
      <div>
        <h3 className="text-xs uppercase font-semibold text-[var(--text-muted)] tracking-wider mb-2">Trigger Event History</h3>
        {sortedEvents.length === 0 ? (
          <div data-testid="empty-history" className="p-4 text-center text-[var(--text-muted)] text-sm border border-dashed border-[var(--border-color)] rounded-md">
            No historical monitoring events recorded.
          </div>
        ) : (
          <div className="divide-y divide-[var(--border-color)]/80 border border-[var(--border-color)] rounded-md overflow-hidden bg-[var(--bg-subtle)]/40">
            {sortedEvents.map((event) => (
              <div
                key={event.id}
                data-testid="event-row"
                className="p-3.5 hover:bg-[var(--bg-subtle-hover)] transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-2"
              >
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="font-mono text-sm font-semibold text-[var(--brand-teal)]">{event.trigger_type}</span>
                    <span className="text-xs text-[var(--text-muted)]">Cycle: {event.cycle_id}</span>
                  </div>
                  {event.observed && (
                    <div className="text-xs text-[var(--text-muted)] mt-1 font-mono">
                      Observed: {JSON.stringify(event.observed)}
                      {event.threshold !== undefined && event.threshold !== null && (
                        <span className="ml-2 text-[var(--text-muted)]">| Threshold: {event.threshold}</span>
                      )}
                    </div>
                  )}
                </div>
                <div className="text-xs text-[var(--text-muted)] shrink-0 font-mono">
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
