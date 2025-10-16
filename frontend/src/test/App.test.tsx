import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import App from '../App';

describe('App Component', () => {
  it('renders header with correct title', () => {
    render(<App />);
    expect(screen.getByText('Organize Mail')).toBeInTheDocument();
  });

  it('renders email list component', () => {
    render(<App />);
    expect(screen.getByText('Project Update Meeting')).toBeInTheDocument();
  });
});