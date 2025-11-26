// Tests for EmailList network/error handling.
//
// Verifies the component shows an error UI when the backend returns a
// non-JSON (HTML) response. This protects against the case where the
// Vite dev server or a proxy serves index.html instead of the API JSON.

import { describe, it, beforeEach, afterEach, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import EmailList from '../../components/EmailList';

describe('EmailList network error handling', () => {
  let origFetch: typeof globalThis.fetch;

  beforeEach(() => {
    origFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = origFetch;
  });

  it('shows an error message when server returns HTML (non-JSON)', async () => {
    // Mock fetch to return HTML content-type so the component throws
    globalThis.fetch = async () => ({
      ok: true,
      status: 200,
      headers: { get: () => 'text/html; charset=utf-8' },
      text: async () => '<!doctype html><html><body>index</body></html>',
    }) as unknown as Response;

    render(<EmailList />);

    // The component sets an error string; wait for the error text to appear.
    const el = await screen.findByText(/Unexpected response from server/i);
    expect(el).toBeInTheDocument();
  });
});
