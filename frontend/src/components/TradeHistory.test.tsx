import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { TradeHistory, type TradeItem } from './TradeHistory';

describe('TradeHistory Component (P8-FE-5)', () => {
  it('renders empty state when no trades exist', () => {
    render(<TradeHistory trades={[]} />);
    expect(screen.getByTestId('empty-trades')).toHaveTextContent(/No historical trades executed yet/i);
  });

  it('renders trade rows with order status, class, and leg details', () => {
    const trades: TradeItem[] = [
      {
        id: 1,
        cycle_id: 'cycle-100',
        order_class: 'MLEG',
        status: 'FILLED',
        submitted_at: '2026-09-04T01:00:00Z',
        cost: 17100,
        legs: [
          { symbol: 'SPY261218P00500000', qty: 20, price: 8.55, slippage: 0.05 },
        ],
      },
      {
        id: 2,
        cycle_id: 'cycle-101',
        order_class: 'SINGLE',
        status: 'SUBMITTED',
        submitted_at: '2026-09-04T02:00:00Z',
        cost: 8550,
        legs: [
          { symbol: 'SPY261218P00500000', qty: 10, price: 8.55 },
        ],
      },
    ];

    const onSelect = vi.fn();
    render(<TradeHistory trades={trades} onSelectTrade={onSelect} />);

    const rows = screen.getAllByTestId('trade-row');
    expect(rows).toHaveLength(2);

    // Default sort is newest first (02:00:00Z first)
    expect(rows[0]).toHaveTextContent('cycle-101');
    expect(rows[0]).toHaveTextContent('SUBMITTED');
    expect(rows[1]).toHaveTextContent('cycle-100');
    expect(rows[1]).toHaveTextContent('FILLED');

    // Click trade row to trigger selection
    fireEvent.click(rows[0]);
    expect(onSelect).toHaveBeenCalledWith(trades[1]);

    // Click sort button to toggle to oldest first
    const sortBtn = screen.getByTestId('sort-date-btn');
    fireEvent.click(sortBtn);
    const sortedRows = screen.getAllByTestId('trade-row');
    expect(sortedRows[0]).toHaveTextContent('cycle-100');
    expect(sortedRows[1]).toHaveTextContent('cycle-101');
  });
});
