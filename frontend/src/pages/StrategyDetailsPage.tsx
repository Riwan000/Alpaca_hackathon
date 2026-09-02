import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Layers, CheckCircle2, XCircle, ShieldCheck } from 'lucide-react';

export const StrategyDetailsPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();

  return (
    <div className="space-y-6" data-testid="strategy-details-page">
      {/* Back Link and Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[var(--border-color)] pb-4">
        <div>
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 text-xs font-mono text-[var(--brand-spruce)] hover:underline mb-2"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to Dashboard
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold font-serif text-[var(--text-main)]">
              Strategy Decision Details
            </h1>
            <span
              className="px-2.5 py-0.5 border border-[var(--border-color)] bg-[var(--bg-subtle)] font-mono text-xs font-bold text-[var(--text-main)]"
              data-testid="strategy-id-badge"
            >
              ID: {id || 'N/A'}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="px-3 py-1.5 bg-[var(--status-safe)]/15 border border-[var(--status-safe)] text-[var(--status-safe)] font-mono text-xs font-bold flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4" />
            RISK APPROVED
          </span>
        </div>
      </div>

      {/* Strategy Summary & Hypotheses Comparison */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Selected Hypothesis Card */}
        <section className="border-t-gold-accent border border-[var(--border-color)] bg-[var(--bg-card)] p-5 space-y-3">
          <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-2">
            <h2 className="text-sm font-serif font-bold text-[var(--text-main)] flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-[var(--status-safe)]" />
              Selected: Protective Collar
            </h2>
            <span className="text-[10px] font-mono text-[var(--brand-gold)] font-bold">RANK #1</span>
          </div>
          <p className="text-xs text-[var(--text-muted)]">
            Optimal cost/benefit payoff. Caps upside beyond $565 while guaranteeing floor at $540.
          </p>
          <div className="p-3 bg-[var(--bg-subtle)] space-y-1 font-mono text-xs">
            <div className="flex justify-between">
              <span className="text-[var(--text-muted)]">Net Premium:</span>
              <span className="text-[var(--status-safe)] font-bold">-$140 (Credit)</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[var(--text-muted)]">Max Downside:</span>
              <span className="font-bold text-[var(--text-main)]">-2.8%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[var(--text-muted)]">Delta:</span>
              <span className="font-bold text-[var(--brand-teal)]">-0.32</span>
            </div>
          </div>
        </section>

        {/* Alternative 1 */}
        <section className="border border-[var(--border-color)] bg-[var(--bg-card)] p-5 space-y-3 opacity-90">
          <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-2">
            <h2 className="text-sm font-serif font-bold text-[var(--text-main)] flex items-center gap-2">
              <XCircle className="w-4 h-4 text-[var(--text-muted)]" />
              Alternative: Bear Put Spread
            </h2>
            <span className="text-[10px] font-mono text-[var(--text-muted)]">RANK #2</span>
          </div>
          <p className="text-xs text-[var(--text-muted)]">
            Limited downside protection window ($540P / $510P). Fails tail risk criteria beyond $510.
          </p>
          <div className="p-3 bg-[var(--bg-subtle)] space-y-1 font-mono text-xs">
            <div className="flex justify-between">
              <span className="text-[var(--text-muted)]">Net Debit:</span>
              <span className="text-[var(--status-danger)] font-bold">+$320 (Debit)</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[var(--text-muted)]">Max Downside:</span>
              <span className="font-bold text-[var(--text-main)]">-5.4%</span>
            </div>
          </div>
        </section>

        {/* Alternative 2 */}
        <section className="border border-[var(--border-color)] bg-[var(--bg-card)] p-5 space-y-3 opacity-90">
          <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-2">
            <h2 className="text-sm font-serif font-bold text-[var(--text-main)] flex items-center gap-2">
              <XCircle className="w-4 h-4 text-[var(--text-muted)]" />
              Alternative: Outright Put
            </h2>
            <span className="text-[10px] font-mono text-[var(--text-muted)]">RANK #3</span>
          </div>
          <p className="text-xs text-[var(--text-muted)]">
            High theta decay and premium drag ($840 debit exceeds cycle budget threshold).
          </p>
          <div className="p-3 bg-[var(--bg-subtle)] space-y-1 font-mono text-xs">
            <div className="flex justify-between">
              <span className="text-[var(--text-muted)]">Net Debit:</span>
              <span className="text-[var(--status-danger)] font-bold">+$840 (Debit)</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[var(--text-muted)]">Max Downside:</span>
              <span className="font-bold text-[var(--text-main)]">-1.5%</span>
            </div>
          </div>
        </section>
      </div>

      {/* Decision Rationale Box */}
      <section className="border border-[var(--border-color)] bg-[var(--bg-card)] p-6 space-y-3">
        <h2 className="text-base font-serif font-bold text-[var(--text-main)] flex items-center gap-2">
          <Layers className="w-4 h-4 text-[var(--brand-spruce)]" />
          Multi-Agent Council Rationale & Quantitative Synthesis
        </h2>
        <div className="p-4 bg-[var(--bg-subtle)] border-l-2 border-[var(--brand-spruce)] text-xs leading-relaxed space-y-2">
          <p>
            <strong>Market Regime:</strong> Elevated Implied Volatility (IV Percentile 68%) makes outright option purchases expensive. Selling the OTM Call funds the downside put with a net credit of $140.
          </p>
          <p>
            <strong>Risk Evaluation:</strong> Collar structure complies with maximum drawdown target (85% floor) and zero margin strain. Execution route verified on Alpaca MCP.
          </p>
        </div>
      </section>
    </div>
  );
};
