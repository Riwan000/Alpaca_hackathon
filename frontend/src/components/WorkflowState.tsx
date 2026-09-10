import React from 'react';
import {
  GitCommit,
  CheckCircle2,
  XCircle,
  AlertOctagon,
  RefreshCw,
  Zap,
  AlertCircle,
} from 'lucide-react';
import type { WorkflowState as WorkflowStateType, WorkflowNode } from '../api/types';

export interface WorkflowStateProps {
  workflow?: WorkflowStateType | null;
  isLoading?: boolean;
  error?: Error | null;
  className?: string;
}

const WORKFLOW_NODES: { id: WorkflowNode; label: string; stage: string }[] = [
  { id: 'INIT', label: 'Init', stage: 'Pipeline Setup' },
  { id: 'PORTFOLIO_ANALYSIS', label: 'Portfolio', stage: 'Analysis' },
  { id: 'STOCK_ANALYSIS', label: 'Stock Risk', stage: 'Analysis' },
  { id: 'MARKET_ANALYSIS', label: 'Market Regime', stage: 'Analysis' },
  { id: 'OPTIONS_ANALYSIS', label: 'Option Chain', stage: 'Analysis' },
  { id: 'STRATEGY_HYPOTHESES', label: 'Hypotheses', stage: 'Strategy' },
  { id: 'STRATEGY_DECISION', label: 'Manager Selection', stage: 'Strategy' },
  { id: 'RISK_GATE', label: 'Risk Gate', stage: 'Risk & Safety' },
  { id: 'EXECUTION', label: 'Execution', stage: 'Execution' },
  { id: 'MONITORING', label: 'Monitoring', stage: 'Autonomous Loop' },
];

export const WorkflowState: React.FC<WorkflowStateProps> = ({
  workflow,
  isLoading = false,
  error = null,
  className = '',
}) => {
  if (isLoading && !workflow) {
    return (
      <div
        className={`p-5 border border-[var(--border-color)] bg-[var(--bg-card)] ${className}`}
        data-testid="workflow-state-loading"
      >
        <div className="flex items-center gap-2 text-xs font-mono text-[var(--text-muted)] animate-pulse">
          <RefreshCw className="w-4 h-4 animate-spin" />
          <span>Syncing LangGraph Orchestration State...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div
        className={`p-4 border border-[var(--status-danger)] bg-[var(--status-danger)]/10 text-xs font-mono text-[var(--status-danger)] flex items-center gap-2 ${className}`}
        data-testid="workflow-state-error"
      >
        <AlertCircle className="w-4 h-4 flex-shrink-0" />
        <span>Error syncing workflow state: {error.message}</span>
      </div>
    );
  }

  const currentNode: WorkflowNode = workflow?.current_node || 'IDLE';
  const status = workflow?.status || 'idle';

  const getCurrentNodeIndex = (): number => {
    if (currentNode === 'COMPLETE') return WORKFLOW_NODES.length;
    if (currentNode === 'IDLE' || currentNode === 'HALTED') return -1;
    return WORKFLOW_NODES.findIndex((n) => n.id === currentNode);
  };

  const currentIndex = getCurrentNodeIndex();
  const progressPct =
    workflow?.progress_pct ??
    (status === 'completed' || currentNode === 'COMPLETE'
      ? 100
      : currentIndex >= 0
      ? Math.round(((currentIndex + 1) / WORKFLOW_NODES.length) * 100)
      : 0);
  const isHalted = status === 'halted' || status === 'failed' || currentNode === 'HALTED' || Boolean(workflow?.halt_reason);

  return (
    <div
      className={`border border-[var(--border-color)] bg-[var(--bg-card)] ${className}`}
      data-testid="workflow-state-panel"
    >
      {/* Header bar */}
      <div className="px-5 py-3.5 border-b border-[var(--border-color)] bg-[var(--bg-subtle)] flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Zap className="w-5 h-5 text-[var(--brand-teal)]" />
          <h2 className="text-sm font-serif font-bold text-[var(--text-main)] uppercase tracking-wide">
            Autonomous Pipeline State (LangGraph)
          </h2>
        </div>
        <div className="flex items-center gap-3 font-mono text-xs">
          <span className="text-[var(--text-muted)]">
            CYCLE: <strong className="text-[var(--text-main)]">{workflow?.cycle_id || 'CYC-001'}</strong>
          </span>
          <span
            className={`px-2.5 py-0.5 border font-bold uppercase flex items-center gap-1.5 ${
              isHalted
                ? 'bg-[var(--status-danger)]/15 border-[var(--status-danger)] text-[var(--status-danger)]'
                : status === 'completed' || currentNode === 'COMPLETE'
                ? 'bg-[var(--status-safe)]/15 border-[var(--status-safe)] text-[var(--status-safe)]'
                : status === 'running'
                ? 'bg-[var(--brand-teal)]/15 border-[var(--brand-teal)] text-[var(--brand-teal)]'
                : 'bg-[var(--bg-subtle)] border-[var(--border-color)] text-[var(--text-muted)]'
            }`}
            data-testid="workflow-status-badge"
          >
            {status === 'running' && <span className="w-1.5 h-1.5 bg-[var(--brand-teal)] animate-pulse inline-block" />}
            {isHalted ? 'HALTED' : status.toUpperCase()}
          </span>
        </div>
      </div>

      {/* Critical Failure Banner (P6-FE-4) */}
      {isHalted && (
        <div
          className="p-4 bg-[var(--status-danger)]/15 border-b border-[var(--status-danger)] text-xs font-mono text-[var(--status-danger)] space-y-1.5"
          data-testid="critical-failure-banner"
        >
          <div className="flex items-center gap-2 font-bold uppercase">
            <AlertOctagon className="w-4 h-4 text-[var(--status-danger)] flex-shrink-0" />
            <span>Cycle Halted On Critical Gate Failure</span>
          </div>
          <p className="text-[var(--text-main)] font-sans">
            Reason: {workflow?.halt_reason || workflow?.error || 'A critical safety constraint violation halted automated execution.'}
          </p>
          <p className="text-[11px] text-[var(--status-danger)] font-bold">
            SAFEGUARD ACTIVE: No automated order submitted. Portfolio remains in last known safe posture.
          </p>
        </div>
      )}

      {/* Progress & Pipeline Step Track */}
      <div className="p-5 space-y-4">
        {/* Progress bar */}
        <div className="space-y-1 font-mono text-xs">
          <div className="flex justify-between text-[11px] text-[var(--text-muted)]">
            <span>PIPELINE PROGRESS</span>
            <span className="font-bold text-[var(--text-main)]" data-testid="workflow-progress-text">
              {progressPct.toFixed(0)}%
            </span>
          </div>
          <div className="w-full h-1.5 bg-[var(--bg-subtle)] border border-[var(--border-color)] overflow-hidden">
            <div
              className={`h-full transition-all duration-300 ${
                isHalted
                  ? 'bg-[var(--status-danger)]'
                  : status === 'completed' || currentNode === 'COMPLETE'
                  ? 'bg-[var(--status-safe)]'
                  : 'bg-[var(--brand-teal)]'
              }`}
              style={{ width: `${progressPct}%` }}
              data-testid="workflow-progress-bar"
            />
          </div>
        </div>

        {/* Pipeline Nodes Flow */}
        <div
          className="grid grid-cols-2 sm:grid-cols-5 gap-2 font-mono text-xs"
          data-testid="workflow-nodes-grid"
        >
          {WORKFLOW_NODES.map((node, idx) => {
            const isCompleted = currentIndex > idx || status === 'completed' || currentNode === 'COMPLETE';
            const isActive = currentIndex === idx && !isHalted;
            const isNodeHalted = isHalted && currentIndex === idx;

            return (
              <div
                key={node.id}
                className={`p-2.5 border transition-colors ${
                  isActive
                    ? 'border-[var(--brand-teal)] bg-[var(--brand-teal)]/10 shadow-sm'
                    : isNodeHalted
                    ? 'border-[var(--status-danger)] bg-[var(--status-danger)]/10'
                    : isCompleted
                    ? 'border-[var(--border-color)] bg-[var(--bg-subtle)]/60 text-[var(--text-muted)]'
                    : 'border-[var(--border-color)]/50 bg-[var(--bg-card)] text-[var(--text-muted)] opacity-60'
                }`}
                data-testid={`workflow-node-${node.id}`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[9px] text-[var(--text-muted)] uppercase">{node.stage}</span>
                  {isCompleted ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-[var(--status-safe)]" />
                  ) : isActive ? (
                    <RefreshCw className="w-3.5 h-3.5 text-[var(--brand-teal)] animate-spin" />
                  ) : isNodeHalted ? (
                    <XCircle className="w-3.5 h-3.5 text-[var(--status-danger)]" />
                  ) : (
                    <GitCommit className="w-3.5 h-3.5 text-[var(--border-color)]" />
                  )}
                </div>
                <div className="font-bold text-[11px] text-[var(--text-main)] truncate" title={node.label}>
                  {node.label}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
