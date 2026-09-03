import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { OrderStatus } from './OrderStatus';
import { STUB_EXECUTION_RESULT } from '../test/server';
import type { ExecutionResult } from '../api/types';

describe('OrderStatus Component (P5-FE-3)', () => {
  it('renders FILLED status badge and fill details from execution result', () => {
    render(<OrderStatus result={STUB_EXECUTION_RESULT} />);

    expect(screen.getByTestId('order-status-panel')).toBeInTheDocument();
    expect(screen.getByTestId('order-status-badge')).toHaveTextContent(/filled/i);
    expect(screen.getByTestId('order-broker-id')).toHaveTextContent(STUB_EXECUTION_RESULT.broker_order_id!);
    expect(screen.getByTestId('order-total-cost')).toHaveTextContent('$10,740.00');
    expect(screen.getByTestId('order-slippage')).toHaveTextContent('$0.03');
    expect(screen.getByTestId('order-fills-table')).toBeInTheDocument();
  });

  it('renders distinct badges for SUBMITTED, PARTIALLY_FILLED, and FAILED states', () => {
    const { rerender } = render(
      <OrderStatus
        result={STUB_EXECUTION_RESULT}
        statusOverride="SUBMITTED"
      />
    );
    expect(screen.getByTestId('order-status-badge')).toHaveTextContent(/submitted/i);

    rerender(
      <OrderStatus
        result={STUB_EXECUTION_RESULT}
        statusOverride="PARTIALLY_FILLED"
      />
    );
    expect(screen.getByTestId('order-status-badge')).toHaveTextContent(/partial fill/i);

    const failedResult: ExecutionResult = {
      ...STUB_EXECUTION_RESULT,
      status: 'FAILED',
      error: 'Insufficient option chain liquidity at limit price',
    };
    rerender(<OrderStatus result={failedResult} statusOverride="FAILED" />);
    expect(screen.getByTestId('order-status-badge')).toHaveTextContent(/failed/i);
    expect(screen.getByTestId('order-failure-message')).toHaveTextContent(
      /insufficient option chain liquidity/i
    );
  });

  it('renders loading and error states properly', () => {
    const { rerender } = render(<OrderStatus isLoading={true} />);
    expect(screen.getByTestId('order-status-loading')).toBeInTheDocument();

    rerender(
      <OrderStatus
        isLoading={false}
        error={new Error('Order stream disconnected')}
      />
    );
    expect(screen.getByTestId('order-status-error')).toHaveTextContent(
      /order stream disconnected/i
    );
  });
});
