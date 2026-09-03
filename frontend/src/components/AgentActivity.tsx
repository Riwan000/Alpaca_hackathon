import React, { useState } from 'react';
import { Cpu, CheckCircle2, AlertTriangle, Clock, RefreshCw, ChevronDown, ChevronRight, Play } from 'lucide-react';
import type { AgentRun } from '../api/types';

export interface AgentActivityProps {
  runs?: AgentRun[];
  isLoading?: boolean;
  error?: Error | null;
  onRefresh?: () => void;
  className?: string;
}

export const AgentActivity: React.FC<AgentActivityProps> = ({
  runs = [],
  isLoading = false,
  error = null,
  onRefresh,
  className = '',
}) => {
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);

  // Sort runs in ascending started_at order
  const sortedRuns = [...runs].sort((a, b) => {
    return new Date(a.started_at).getTime() - new Date(b.started_at).getTime();
  });

  const toggleExpand = (id: string) => {
    setExpandedRunId(expandedRunId === id ? null : id);
  };

  const formatDuration = (ms?: number | null) => {
    if (ms === undefined || ms === null) return '—';
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  const getStatusBadge = (run: AgentRun) => {
    const status = run.status || (run.error ? 'error' : run.finished_at ? 'completed' : 'running');

    if (status === 'error' || status === 'failed') {
      return (
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 bg-[var(--status-danger)]/15 border border-[var(--status-danger)] text-[var(--status-danger)] font-mono text-[10px] font-bold"
          data-testid="status-error"
        >
          <AlertTriangle className="w-3 h-3" /> FAILED
        </span>
      );
    }

    if (status === 'running' || status === 'pending') {
      return (
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 bg-[var(--brand-teal)]/15 border border-[var(--brand-teal)] text-[var(--brand-teal)] font-mono text-[10px] font-bold"
          data-testid="status-running"
        >
          <RefreshCw className="w-3 h-3 animate-spin" /> RUNNING
        </span>
      );
    }

    return (
      <span
        className="inline-flex items-center gap-1 px-2 py-0.5 bg-[var(--status-safe)]/15 border border-[var(--status-safe)] text-[var(--status-safe)] font-mono text-[10px] font-bold"
        data-testid="status-completed"
      >
        <CheckCircle2 className="w-3 h-3" /> DONE
      </span>
    );
  };

  if (isLoading && runs.length === 0) {
    return (
      <div
        className={`border border-[var(--border-color)] bg-[var(--bg-card)] p-5 space-y-4 ${className}`}
        data-testid="agent-activity-loading"
      >
        <div className="h-5 w-40 bg-[var(--bg-subtle)] animate-pulse" />
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 bg-[var(--bg-subtle)] animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div
        className={`border border-[var(--status-danger)] bg-[var(--status-danger)]/5 p-5 space-y-3 ${className}`}
        data-testid="agent-activity-error"
      >
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-serif font-bold text-[var(--status-danger)] flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" />
            Agent Activity Stream Error
          </h2>
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="text-xs font-mono text-[var(--status-danger)] hover:underline flex items-center gap-1"
            >
              <RefreshCw className="w-3 h-3" /> Retry
            </button>
          )}
        </div>
        <p className="text-xs font-mono text-[var(--text-muted)]">{error.message}</p>
      </div>
    );
  }

  return (
    <div
      className={`border border-[var(--border-color)] bg-[var(--bg-card)] p-5 space-y-4 ${className}`}
      data-testid="agent-activity"
    >
      <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-3">
        <div>
          <h2 className="text-sm font-serif font-bold text-[var(--text-main)] flex items-center gap-2">
            <Cpu className="w-4 h-4 text-[var(--brand-teal)]" />
            Autonomous Agent Activity Timeline
          </h2>
          <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase">
            LangGraph Multi-Agent Orchestration & Audit Log
          </span>
        </div>
        {runs.length > 0 && (
          <span className="text-[10px] font-mono text-[var(--text-muted)]" data-testid="agent-runs-count">
            {runs.length} AGENT PASSES
          </span>
        )}
      </div>

      {sortedRuns.length === 0 ? (
        <div
          className="flex flex-col items-center justify-center py-8 border border-dashed border-[var(--border-color)] bg-[var(--bg-subtle)]/40 text-center text-xs font-mono text-[var(--text-muted)]"
          data-testid="agent-activity-empty"
        >
          <Play className="w-6 h-6 text-[var(--text-muted)] mb-2 opacity-60" />
          <span className="font-bold text-[var(--text-main)]">No Recent Agent Runs</span>
          <span>Initiate a hedge evaluation cycle to observe agent executions in real time.</span>
        </div>
      ) : (
        <div className="space-y-2.5 font-mono text-xs" data-testid="agent-runs-timeline">
          {sortedRuns.map((run, index) => {
            const isExpanded = expandedRunId === run.id;
            return (
              <div
                key={run.id || index}
                className="border border-[var(--border-color)] bg-[var(--bg-card)] transition-colors hover:border-[var(--brand-spruce)]/60"
                data-testid={`agent-run-item-${run.id || index}`}
              >
                <div
                  onClick={() => toggleExpand(run.id || String(index))}
                  className="p-3 flex flex-wrap items-center justify-between gap-3 cursor-pointer bg-[var(--bg-subtle)]/40 hover:bg-[var(--bg-subtle)]/80"
                >
                  <div className="flex items-center gap-2.5">
                    {isExpanded ? (
                      <ChevronDown className="w-3.5 h-3.5 text-[var(--brand-spruce)]" />
                    ) : (
                      <ChevronRight className="w-3.5 h-3.5 text-[var(--text-muted)]" />
                    )}
                    <span className="w-5 h-5 flex items-center justify-center bg-[var(--bg-card)] border border-[var(--border-color)] text-[10px] font-bold text-[var(--text-muted)]">
                      {index + 1}
                    </span>
                    <span className="font-bold text-[var(--text-main)]">{run.agent_name}</span>
                  </div>

                  <div className="flex items-center gap-3">
                    <span className="text-[10px] text-[var(--text-muted)] flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {formatDuration(run.duration_ms)}
                    </span>
                    {getStatusBadge(run)}
                  </div>
                </div>

                {isExpanded && (
                  <div className="p-3 border-t border-[var(--border-color)] bg-[var(--bg-card)] text-[11px] space-y-2">
                    <div className="flex justify-between text-[10px] text-[var(--text-muted)]">
                      <span>Started: {new Date(run.started_at).toLocaleTimeString()}</span>
                      {run.finished_at && <span>Finished: {new Date(run.finished_at).toLocaleTimeString()}</span>}
                    </div>

                    {run.error && (
                      <div className="p-2 border border-[var(--status-danger)] bg-[var(--status-danger)]/10 text-[var(--status-danger)]">
                        <strong>Error:</strong> {run.error}
                      </div>
                    )}

                    {run.outputs && (
                      <div className="space-y-1">
                        <span className="text-[10px] uppercase text-[var(--text-muted)] font-bold">Outputs:</span>
                        <pre className="p-2 bg-[var(--bg-subtle)] border border-[var(--border-color)] overflow-x-auto text-[10px]">
                          {JSON.stringify(run.outputs, null, 2)}
                        </pre>
                      </div>
                    )}

                    {run.inputs && (
                      <div className="space-y-1">
                        <span className="text-[10px] uppercase text-[var(--text-muted)] font-bold">Inputs:</span>
                        <pre className="p-2 bg-[var(--bg-subtle)] border border-[var(--border-color)] overflow-x-auto text-[10px]">
                          {JSON.stringify(run.inputs, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
