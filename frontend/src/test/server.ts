import { setupServer } from 'msw/node';
import { HttpResponse, http } from 'msw';

export const handlers = [
  http.get('*/health', () => {
    return HttpResponse.json({ status: 'healthy', version: '0.1.0' });
  }),
];

export const server = setupServer(...handlers);
