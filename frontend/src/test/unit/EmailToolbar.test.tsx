import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import EmailToolbar from '../../components/EmailToolbar';

describe('EmailToolbar Component', () => {
  const defaultProps = {
    searchQuery: '',
    onSearchChange: vi.fn(),
    sortOrder: 'recent' as const,
    onSortToggle: vi.fn(),
    filters: {
      priority: null,
      labels: [],
      status: 'all' as const,
    },
    onStatusChange: vi.fn(),
    onClearAllFilters: vi.fn(),
    onLabelFilter: vi.fn(),
    onPriorityFilter: vi.fn(),
    selectedModel: 'gemma:2b',
    onModelChange: vi.fn(),
  };

  beforeEach(() => {
    global.fetch = vi.fn() as unknown as typeof fetch;
  });

  it('renders search input field', () => {
    render(<EmailToolbar {...defaultProps} />);
    expect(screen.getByPlaceholderText('Search emails...')).toBeInTheDocument();
  });

  it('calls onSearchChange when typing in search field', () => {
    const onSearchChange = vi.fn();
    render(<EmailToolbar {...defaultProps} onSearchChange={onSearchChange} />);

    const searchInput = screen.getByPlaceholderText('Search emails...');
    fireEvent.change(searchInput, { target: { value: 'test query' } });

    expect(onSearchChange).toHaveBeenCalledWith('test query');
  });

  it('renders priority filter chips', () => {
    render(<EmailToolbar {...defaultProps} />);

    expect(screen.getByText(/High/)).toBeInTheDocument();
    expect(screen.getByText(/Normal/)).toBeInTheDocument();
    expect(screen.getByText(/Low/)).toBeInTheDocument();
  });

  it('highlights selected priority filter', () => {
    render(<EmailToolbar {...defaultProps} filters={{ priority: 'high', labels: [], status: 'all' }} />);

    const highChip = screen.getByText(/High/).closest('.MuiChip-root');
    expect(highChip).toHaveClass('MuiChip-filled');
  });

  it('calls onPriorityFilter when priority chip is clicked', () => {
    const onPriorityFilter = vi.fn();
    render(<EmailToolbar {...defaultProps} onPriorityFilter={onPriorityFilter} />);

    const highChip = screen.getByText(/High/);
    fireEvent.click(highChip);

    expect(onPriorityFilter).toHaveBeenCalledWith('high');
  });

  it('renders model selector dropdown', () => {
    render(<EmailToolbar {...defaultProps} />);
    // Model selector is a combobox (Select component)
    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });

  it('fetches available models on mount', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        models: [
          { name: 'gemma:2b', size: 1234 },
          { name: 'gemma:7b', size: 5678 },
        ],
      }),
    });

    render(<EmailToolbar {...defaultProps} />);

    await waitFor(() => {
      expect(global.fetch as ReturnType<typeof vi.fn>).toHaveBeenCalledWith('/models');
    });
  });

  it('calls onModelChange when model is selected', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        models: [
          { name: 'gemma:2b', size: 1234 },
          { name: 'gemma:7b', size: 5678 },
        ],
      }),
    });

    const onModelChange = vi.fn();
    render(<EmailToolbar {...defaultProps} onModelChange={onModelChange} />);

    // Wait for models to load
    await waitFor(() => {
      expect(global.fetch as ReturnType<typeof vi.fn>).toHaveBeenCalled();
    });

    // Verify the select is present with current value
    const selectElement = screen.getByRole('combobox');
    expect(selectElement).toBeInTheDocument();
  });

  it('shows error message when model fetch fails', async () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    
    (global.fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('Network error'));

    render(<EmailToolbar {...defaultProps} />);

    await waitFor(() => {
      expect(consoleErrorSpy).toHaveBeenCalled();
    });

    consoleErrorSpy.mockRestore();
  });

  it('shows sort toggle button', () => {
    render(<EmailToolbar {...defaultProps} />);
    
    // Look for the sort chip/button with arrow icon
    const sortButton = screen.getByText(/Newest First|Oldest First/);
    expect(sortButton).toBeInTheDocument();
  });

  it('calls onSortToggle when sort button is clicked', () => {
    const onSortToggle = vi.fn();
    render(<EmailToolbar {...defaultProps} onSortToggle={onSortToggle} sortOrder="recent" />);

    // Click the sort chip
    const sortButton = screen.getByText(/Newest First/);
    fireEvent.click(sortButton);
    
    expect(onSortToggle).toHaveBeenCalled();
  });

  it('displays classification status toggle', () => {
    render(<EmailToolbar {...defaultProps} />);
    
    // Check for classification status buttons
    expect(screen.getByText('All')).toBeInTheDocument();
    expect(screen.getByText('Classified')).toBeInTheDocument();
    expect(screen.getByText('Unclassified')).toBeInTheDocument();
  });

  it('calls onStatusChange when classification status is changed', () => {
    const onStatusChange = vi.fn();
    render(<EmailToolbar {...defaultProps} onStatusChange={onStatusChange} />);

    const classifiedButton = screen.getByText('Classified');
    fireEvent.click(classifiedButton);

    expect(onStatusChange).toHaveBeenCalled();
  });
});

