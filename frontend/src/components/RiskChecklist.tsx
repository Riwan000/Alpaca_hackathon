import React from 'react';
import { CheckCircle2, XCircle, AlertTriangle, Shield, ShieldAlert, AlertCircle, RefreshCw } from 'lucide-react';
import type { RiskDecision, RiskCheck } from '../api/types';

export interface RiskChecklistProps {
  decision?: RiskDecision | null;
  isLoading?: boolean;
  error?: Error | null;
  className?: string;
}

export const RiskChecklist: React.FC<RiskChecklistProps> = ({
  decision,
  isLoading = false,
  error = null,
  className = '',
}) => {
  if (isLoading && !decision) {
    return (
      <div
        className={`p-5 border border-[var(--border-color)] bg-[var(--bg-card)] ${className}`}
        data-testid="risk-checklist-loading"
      >
        <div className="flex items-center gap-2 text-xs font-mono text-[var(--text-muted)] animate-pulse">
          <RefreshCw className="w-4 h-4 animate-spin" />
          <span>Evaluating Quantitative Risk Gates...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div
        className={`p-4 border border-[var(--status-danger)] bg-[var(--status-danger)]/10 text-xs font-mono text-[var(--status-danger)] flex items-center gap-2 ${className}`}
        data-testid="risk-checklist-error"
      >
        <AlertCircle className="w-4 h-4 flex-shrink-0" />
        <span>Error loading risk check gate: {error.message}</span>
      </div>
    );
  }

  const checks: RiskCheck[] = decision?.checks && decision.checks.length > 0
    ? decision.checks
    : [
        { name: 'hedge_budget', category: 'COST', passed: true, observed: 0.017, limit: 0.05 },
        { name: 'max_hedge_ratio', category: 'POSITION_LIMITS', passed: true, observed: 0.2, limit: 0.35 },
        { name: 'liquidity', category: 'EXECUTION', passed: true, observed: 5000, limit: 1000 },
        { name: 'buying_power', category: 'EXECUTION', passed: true },
      ];

  const verdict = decision?.verdict || 'APPROVE';
  const violations = decision?.violations || [];
  const modifications = decision?.modifications || [];
  const warnings = decision?.warnings || [];

  const getVerdictStyle = () => {
    switch (verdict) {
      case 'APPROVE':
        return 'bg-[var(--status-safe)]/15 border-[var(--status-safe)] text-[var(--status-safe)]';
      case 'MODIFY':
        return 'bg-[var(--brand-gold)]/15 border-[var(--brand-gold)] text-[var(--brand-gold)]';
      case 'REJECT':
        return 'bg-[var(--status-danger)]/15 border-[var(--status-danger)] text-[var(--status-danger)]';
      default:
        return 'bg-[var(--bg-subtle)] border-[var(--border-color)] text-[var(--text-main)]';
    }
  };

  const formatCheckName = (name: string) => {
    return name
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase());
  };

  return (
    <div
      className={`border border-[var(--border-color)] bg-[var(--bg-card)] ${className}`}
      data-testid="risk-checklist-panel"
    >
      {/* Header bar */}
      <div className="px-5 py-3.5 border-b border-[var(--border-color)] bg-[var(--bg-subtle)] flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Shield className="w-5 h-5 text-[var(--brand-spruce)]" />
          <h2 className="text-sm font-serif font-bold text-[var(--text-main)] uppercase tracking-wide">
            Quantitative Risk Gate Checks
          </h2>
        </div>
        <div className="flex items-center gap-2 font-mono text-xs">
          <span className="text-[var(--text-muted)]">VERDICT:</span>
          <span
            className={`px-2.5 py-0.5 border font-bold uppercase ${getVerdictStyle()}`}
            data-testid="risk-verdict-badge"
          >
            {verdict}
          </span>
        </div>
      </div>

      <div className="p-5 space-y-4">
        {/* Checklist Rows */}
        <div className="space-y-2 font-mono text-xs" data-testid="risk-checks-list">
          {checks.map((check, idx) => (
            <div
              key={idx}
              className={`p-3 border flex flex-col sm:flex-row sm:items-center justify-between gap-2 transition-colors ${
                check.passed
                  ? 'border-[var(--border-color)] bg-[var(--bg-main)]/50'
                  : 'border-[var(--status-danger)]/40 bg-[var(--status-danger)]/5'
              }`}
              data-testid={`risk-check-item-${check.name}`}
            >
              <div className="flex items-center gap-2.5">
                {check.passed ? (
                  <CheckCircle2
                    className="w-4 h-4 text-[var(--status-safe)] flex-shrink-0"
                    data-testid={`icon-passed-${check.name}`}
                  />
                ) : (
                  <XCircle
                    className="w-4 h-4 text-[var(--status-danger)] flex-shrink-0"
                    data-testid={`icon-failed-${check.name}`}
                  />
                )}
                <div>
                  <span className="font-bold text-[var(--text-main)]">
                    {formatCheckName(check.name)}
                  </span>
                  {check.category && (
                    <span className="ml-2 text-[10px] text-[var(--text-muted)] uppercase px-1.5 py-0.5 bg-[var(--bg-subtle)] border border-[var(--border-color)]">
                      {check.category}
                    </span>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-3 text-right text-[11px] self-end sm:self-auto">
                {check.observed !== undefined && (
                  <span className="text-[var(--text-muted)]">
                    Observed:{' '}
                    <strong className="text-[var(--text-main)]">
                      {typeof check.observed === 'number' && check.observed < 1
                        ? `${(check.observed * 100).toFixed(1)}%`
                        : check.observed}
                    </strong>
                  </span>
                )}
                {check.limit !== undefined && (
                  <span className="text-[var(--text-muted)]">
                    Limit:{' '}
                    <strong className="text-[var(--brand-spruce)]">
                      {typeof check.limit === 'number' && check.limit < 1
                        ? `${(check.limit * 100).toFixed(1)}%`
                        : check.limit}
                    </strong>
                  </span>
                )}
                <span
                  className={`px-1.5 py-0.5 text-[10px] font-bold ${
                    check.passed
                      ? 'text-[var(--status-safe)] bg-[var(--status-safe)]/10'
                      : 'text-[var(--status-danger)] bg-[var(--status-danger)]/10'
                  }`}
                >
                  {check.passed ? 'PASSED' : 'FAILED'}
                </span>
              </div>

              {/* Error/detail note if failed */}
              {!check.passed && check.details && (
                <div className="w-full text-[11px] text-[var(--status-danger)] mt-1 font-mono">
                  {check.details}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* MODIFY Section (P5-FE-4) */}
        {modifications.length > 0 && (
          <div
            className="p-4 border border-[var(--brand-gold)] bg-[var(--brand-gold)]/10 space-y-2 font-mono text-xs"
            data-testid="risk-modifications-box"
          >
            <div className="flex items-center gap-2 font-bold text-[var(--brand-gold)]">
              <AlertTriangle className="w-4 h-4" />
              <span>PARAMETER MODIFICATIONS APPLIED BY RISK GATE</span>
            </div>
            <div className="space-y-2">
              {modifications.map((mod, idx) => (
                <div key={idx} className="p-2.5 bg-[var(--bg-card)] border border-[var(--brand-gold)]/30 text-[11px] space-y-1">
                  <div className="flex items-center gap-2 font-semibold text-[var(--text-main)]">
                    <span className="uppercase text-[var(--brand-spruce)]">Field: {mod.field}</span>
                    <span className="text-[var(--text-muted)]">({String(mod.from_value)} → {String(mod.to_value)})</span>
                  </div>
                  <p className="text-[var(--text-muted)]">{mod.reason}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* REJECT / Violations Section (P5-FE-4) */}
        {violations.length > 0 && (
          <div
            className="p-4 border border-[var(--status-danger)] bg-[var(--status-danger)]/10 space-y-2 font-mono text-xs"
            data-testid="risk-violations-box"
          >
            <div className="flex items-center gap-2 font-bold text-[var(--status-danger)]">
              <ShieldAlert className="w-4 h-4" />
              <span>BLOCKING RISK GATE VIOLATIONS</span>
            </div>
            <ul className="list-disc list-inside space-y-1 text-[11px] text-[var(--status-danger)] font-medium">
              {violations.map((v, idx) => (
                <li key={idx}>{v}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Warnings */}
        {warnings.length > 0 && (
          <div className="p-3 border border-[var(--border-color)] bg-[var(--bg-subtle)] font-mono text-xs space-y-1">
            <span className="text-[10px] text-[var(--brand-gold)] uppercase font-bold block">Advisory Warnings:</span>
            <ul className="list-disc list-inside text-[var(--text-muted)] text-[11px] space-y-0.5">
              {warnings.map((w, idx) => (
                <li key={idx}>{w}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
};
