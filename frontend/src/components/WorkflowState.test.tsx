import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorkflowState } from './WorkflowState';
import { STUB_WORKFLOW_STATE } from '../test/server';
import type { WorkflowState as WorkflowStateType } from '../api/types';

describe('WorkflowState Component (P6-FE-1, P6-FE-4)', () => {
  it('highlights the active node and renders progress', () => {
    const runningState: WorkflowStateType = {
      cycle_id: 'cyc-test-01',
      current_node: 'OPTIONS_ANALYSIS',
      progress_pct: 45,
      status: 'running',
      active_agent: 'Options Analysis Agent',
    };

    render(<WorkflowState workflow={runningState} />);

    expect(screen.getByTestId('workflow-state-panel')).toBeInTheDocument();
    expect(screen.getByTestId('workflow-status-badge')).toHaveTextContent(/running/i);
    expect(screen.getByTestId('workflow-progress-text')).toHaveTextContent('45%');
    expect(screen.getByTestId('workflow-node-OPTIONS_ANALYSIS')).toBeInTheDocument();
  });

  it('renders completed state when workflow reaches COMPLETE', () => {
    render(<WorkflowState workflow={STUB_WORKFLOW_STATE} />);

    expect(screen.getByTestId('workflow-status-badge')).toHaveTextContent(/completed/i);
    expect(screen.getByTestId('workflow-progress-text')).toHaveTextContent('100%');
  });

  it('critical: displays critical failure banner and safeguard note on halt (P6-FE-4)', () => {
    const haltedState: WorkflowStateType = {
      cycle_id: 'cyc-halt-01',
      current_node: 'RISK_GATE',
      progress_pct: 70,
      status: 'halted',
      halt_reason: 'Circuit breaker triggered: Max portfolio drawdown breach (-12.4%) exceeds tolerance limit.',
    };

    render(<WorkflowState workflow={haltedState} />);

    expect(screen.getByTestId('critical-failure-banner')).toBeInTheDocument();
    expect(
      screen.getByText(/cycle halted on critical gate failure/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/max portfolio drawdown breach/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/safeguard active: no automated order submitted/i)
    ).toBeInTheDocument();
    expect(screen.getByTestId('workflow-status-badge')).toHaveTextContent(/halted/i);
  });

  it('renders loading and error states properly', () => {
    const { rerender } = render(<WorkflowState isLoading={true} />);
    expect(screen.getByTestId('workflow-state-loading')).toBeInTheDocument();

    rerender(
      <WorkflowState
        isLoading={false}
        error={new Error('Workflow state endpoint offline')}
      />
    );
    expect(screen.getByTestId('workflow-state-error')).toHaveTextContent(
      /workflow state endpoint offline/i
    );
  });
});
