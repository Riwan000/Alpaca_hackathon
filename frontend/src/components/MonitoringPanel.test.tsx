import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { MonitoringPanel } from './MonitoringPanel';
import type { MonitoringEvent } from '../api/types';

describe('MonitoringPanel Component (P7-FE-1)', () => {
  it('renders "all clear" badge and message when no triggers are active', () => {
    render(<MonitoringPanel events={[]} activeTriggers={[]} />);

    expect(screen.getByTestId('all-clear-badge')).toBeInTheDocument();
    expect(screen.getByTestId('all-clear-message')).toHaveTextContent(/No active triggers tripped/i);
    expect(screen.getByTestId('empty-history')).toBeInTheDocument();
  });

  it('renders active triggers with alert badge when triggers are tripped', () => {
    render(
      <MonitoringPanel
        activeTriggers={['VOLATILITY_SPIKE', 'DRAWDOWN_LIMIT']}
        events={[]}
      />
    );

    expect(screen.getByTestId('active-alert-badge')).toHaveTextContent(/2 Active Triggers/i);
    const triggerItems = screen.getAllByTestId('active-trigger-item');
    expect(triggerItems).toHaveLength(2);
    expect(triggerItems[0]).toHaveTextContent('VOLATILITY_SPIKE');
    expect(triggerItems[1]).toHaveTextContent('DRAWDOWN_LIMIT');
  });

  it('renders event history ordered chronologically by fired_at', () => {
    const events: MonitoringEvent[] = [
      {
        id: 1,
        cycle_id: 'cycle-100',
        trigger_type: 'VOLATILITY_SPIKE',
        observed: { iv: 0.35 },
        threshold: 0.25,
        fired_at: '2026-09-04T01:00:00Z',
      },
      {
        id: 2,
        cycle_id: 'cycle-101',
        trigger_type: 'DRAWDOWN_LIMIT',
        observed: { drawdown: -0.08 },
        threshold: -0.05,
        fired_at: '2026-09-04T02:00:00Z',
      },
    ];

    render(<MonitoringPanel events={events} activeTriggers={[]} />);

    const rows = screen.getAllByTestId('event-row');
    expect(rows).toHaveLength(2);
    // Row 0 is the most recent (02:00:00Z)
    expect(rows[0]).toHaveTextContent('DRAWDOWN_LIMIT');
    expect(rows[1]).toHaveTextContent('VOLATILITY_SPIKE');
  });
});
