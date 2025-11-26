// Tests for the top-level App component.
//
// Verifies basic render behavior and that the main UI pieces are present:
// - header text 'Organize Mail' is rendered
// - the EmailList component (sample email text) appears in the DOM
//
// These are lightweight smoke tests to ensure the app shell mounts
// and integrates the EmailList component.
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import App from '../../App';

describe('App Component', () => {
  it('renders header with correct title', async () => {
    render(<App />);
    expect(await screen.findByText('Organize Mail')).toBeInTheDocument();
  });

  // Smoke test: verifies the EmailList component mounts and renders a
  // sample email from the fixture so integration between App and
  // EmailList is validated.
  it('renders email list component', async () => {
    render(<App />);
    expect(await screen.findByText('Project Update Meeting')).toBeInTheDocument();
  });
});