import { describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../test/server';
import { apiClient, ApiError, request } from './client';

describe('apiClient and request wrapper', () => {
  it('parses 2xx JSON response successfully', async () => {
    server.use(
      http.get('*/api/test-success', () => {
        return HttpResponse.json({ success: true, count: 42 });
      })
    );

    const data = await apiClient.get<{ success: boolean; count: number }>('/api/test-success');
    expect(data).toEqual({ success: true, count: 42 });
  });

  it('handles 204 No Content gracefully', async () => {
    server.use(
      http.delete('*/api/items/123', () => {
        return new HttpResponse(null, { status: 204 });
      })
    );

    const data = await apiClient.delete('/api/items/123');
    expect(data).toBeNull();
  });

  it('sends POST request with JSON body', async () => {
    server.use(
      http.post('*/api/portfolio', async ({ request }) => {
        const body = (await request.json()) as { symbol: string; qty: number };
        return HttpResponse.json({ received: body, id: 'item-1' }, { status: 201 });
      })
    );

    const payload = { symbol: 'SPY', qty: 100 };
    const res = await apiClient.post<{ received: typeof payload; id: string }>(
      '/api/portfolio',
      payload
    );
    expect(res.id).toBe('item-1');
    expect(res.received.symbol).toBe('SPY');
  });

  it('normalizes 400 Bad Request with detail field', async () => {
    server.use(
      http.get('*/api/bad-request', () => {
        return HttpResponse.json(
          { detail: 'Invalid parameter: symbol SPY999 not found' },
          { status: 400 }
        );
      })
    );

    try {
      await apiClient.get('/api/bad-request');
      expect.fail('Should have thrown an ApiError');
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(400);
      expect(apiErr.code).toBe('BAD_REQUEST');
      expect(apiErr.message).toBe('Invalid parameter: symbol SPY999 not found');
    }
  });

  it('normalizes 404 Not Found error', async () => {
    server.use(
      http.get('*/api/nonexistent', () => {
        return HttpResponse.json({ detail: 'Strategy strat-999 not found' }, { status: 404 });
      })
    );

    await expect(apiClient.get('/api/nonexistent')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      code: 'NOT_FOUND',
      message: 'Strategy strat-999 not found',
    });
  });

  it('normalizes 500 Internal Server Error', async () => {
    server.use(
      http.get('*/api/server-error', () => {
        return HttpResponse.json({ message: 'Database connection timeout' }, { status: 500 });
      })
    );

    await expect(apiClient.get('/api/server-error')).rejects.toMatchObject({
      name: 'ApiError',
      status: 500,
      code: 'INTERNAL_SERVER_ERROR',
      message: 'Database connection timeout',
    });
  });

  it('normalizes network connection failure (dead port / unreachable server)', async () => {
    server.use(
      http.get('*/api/dead-endpoint', () => {
        return HttpResponse.error();
      })
    );

    try {
      await request('/api/dead-endpoint');
      expect.fail('Should have failed on network error');
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(0);
      expect(apiErr.code).toBe('NETWORK_ERROR');
      expect(apiErr.message).toContain('Unable to connect to server');
    }
  });
});
