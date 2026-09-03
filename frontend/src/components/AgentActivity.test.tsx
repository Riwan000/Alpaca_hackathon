import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AgentActivity } from './AgentActivity';
import { STUB_AGENT_RUNS } from '../test/server';

describe('AgentActivity Component (P3-FE-3, P3-FE-4)', () => {
  it('renders runs in started_at chronological order', () => {
    // Pass in reverse order to test sorting
    const reversed = [...STUB_AGENT_RUNS].reverse();
    render(<AgentActivity runs={reversed} />);

    expect(screen.getByTestId('agent-activity')).toBeInTheDocument();
    expect(screen.getByTestId('agent-runs-count')).toHaveTextContent('6 AGENT PASSES');

    const timeline = screen.getByTestId('agent-runs-timeline');
    expect(timeline).toBeInTheDocument();

    // Verify first chronological agent is Portfolio Analysis Agent
    expect(screen.getByTestId('agent-run-item-run-001')).toHaveTextContent(/Portfolio Analysis Agent/i);
    expect(screen.getByTestId('agent-run-item-run-006')).toHaveTextContent(/Strategy Manager Agent/i);
  });

  it('styles running vs done vs error states distinctly', () => {
    const mixedRuns = [
      {
        id: 'r1',
        cycle_id: 'cyc-001',
        agent_name: 'Done Agent',
        status: 'completed' as const,
        started_at: '2026-09-03T14:30:00.000Z',
        finished_at: '2026-09-03T14:30:00.100Z',
        duration_ms: 100,
      },
      {
        id: 'r2',
        cycle_id: 'cyc-001',
        agent_name: 'Running Agent',
        status: 'running' as const,
        started_at: '2026-09-03T14:30:00.100Z',
      },
      {
        id: 'r3',
        cycle_id: 'cyc-001',
        agent_name: 'Failing Agent',
        status: 'error' as const,
        error: 'API Rate limit exceeded',
        started_at: '2026-09-03T14:30:00.200Z',
      },
    ];

    render(<AgentActivity runs={mixedRuns} />);

    expect(screen.getByTestId('status-completed')).toBeInTheDocument();
    expect(screen.getByTestId('status-running')).toBeInTheDocument();
    expect(screen.getByTestId('status-error')).toBeInTheDocument();
  });

  it('expands run details when clicked to reveal outputs and duration', () => {
    render(<AgentActivity runs={STUB_AGENT_RUNS} />);

    const runCard = screen.getByTestId('agent-run-item-run-001');
    fireEvent.click(runCard.querySelector('div')!);

    expect(screen.getByText(/Outputs:/i)).toBeInTheDocument();
  });

  it('renders loading and error states cleanly (P3-FE-4)', () => {
    const { rerender } = render(<AgentActivity isLoading={true} />);
    expect(screen.getByTestId('agent-activity-loading')).toBeInTheDocument();

    rerender(<AgentActivity error={new Error('Failed to stream agent telemetry')} />);
    expect(screen.getByTestId('agent-activity-error')).toBeInTheDocument();
    expect(screen.getByText(/Failed to stream agent telemetry/i)).toBeInTheDocument();
  });
});
