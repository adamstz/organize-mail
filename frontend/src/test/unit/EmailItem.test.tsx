import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import EmailItem from '../../components/EmailItem';
import { Email } from '../../types/email';

// Mock EmailBodyRenderer to avoid fetch calls on mount
vi.mock('../../components/EmailBodyRenderer', () => ({
  default: () => <div data-testid="email-body-renderer">Mock Body</div>,
}));

const mockEmail: Email = {
  id: '123',
  subject: 'Test Email',
  date: '2025-10-14',
  priority: 'High',
  summary: 'Test summary',
  body: 'Test body content',
  classificationLabels: ['work', 'urgent'],
  isClassified: true,
};

describe('EmailItem Component', () => {
  let mockOnDelete: ReturnType<typeof vi.fn>;
  let mockOnReclassify: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockOnDelete = vi.fn();
    mockOnReclassify = vi.fn();
    global.fetch = vi.fn() as unknown as typeof fetch;
  });

  it('renders email with subject and summary', () => {
    render(
      <EmailItem
        email={mockEmail}
        isExpanded={false}
        onExpand={() => { }}
        onDelete={mockOnDelete}
        onReclassify={mockOnReclassify}
        selectedModel="gemma:2b"
      />
    );

    expect(screen.getByText('Test Email')).toBeInTheDocument();
    expect(screen.getByText('Test summary')).toBeInTheDocument();
  });

  it('displays priority chip with correct color for High priority', () => {
    render(
      <EmailItem
        email={mockEmail}
        isExpanded={false}
        onExpand={() => { }}
        onDelete={mockOnDelete}
        onReclassify={mockOnReclassify}
        selectedModel="gemma:2b"
      />
    );

    const priorityChip = screen.getByText('High');
    expect(priorityChip.closest('.MuiChip-root')).toHaveClass('MuiChip-colorError');
  });

  it('displays priority chip with correct color for Normal priority', () => {
    const normalEmail = { ...mockEmail, priority: 'Normal' as const };
    render(
      <EmailItem
        email={normalEmail}
        isExpanded={false}
        onExpand={() => { }}
        onDelete={mockOnDelete}
        onReclassify={mockOnReclassify}
        selectedModel="gemma:2b"
      />
    );

    const priorityChip = screen.getByText('Normal');
    expect(priorityChip.closest('.MuiChip-root')).toHaveClass('MuiChip-colorWarning');
  });

  it('displays priority chip with correct color for Low priority', () => {
    const lowEmail = { ...mockEmail, priority: 'Low' as const };
    render(
      <EmailItem
        email={lowEmail}
        isExpanded={false}
        onExpand={() => { }}
        onDelete={mockOnDelete}
        onReclassify={mockOnReclassify}
        selectedModel="gemma:2b"
      />
    );

    const priorityChip = screen.getByText('Low');
    expect(priorityChip.closest('.MuiChip-root')).toHaveClass('MuiChip-colorSuccess');
  });

  it('shows reclassify button in collapsed state', () => {
    render(
      <EmailItem
        email={mockEmail}
        isExpanded={false}
        onExpand={() => { }}
        onDelete={mockOnDelete}
        onReclassify={mockOnReclassify}
        selectedModel="gemma:2b"
      />
    );

    const reclassifyButton = screen.getByLabelText('reclassify');
    expect(reclassifyButton).toBeInTheDocument();
  });

  it('calls onReclassify when reclassify button is clicked and API succeeds', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation(() => {
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, priority: 'high' }),
      });
    });

    render(
      <EmailItem
        email={mockEmail}
        isExpanded={false}
        onExpand={() => { }}
        onDelete={mockOnDelete}
        onReclassify={mockOnReclassify}
        selectedModel="gemma:7b"
      />
    );

    const reclassifyButton = screen.getByLabelText('reclassify');

    fireEvent.click(reclassifyButton);

    await waitFor(() => {
      expect(global.fetch as ReturnType<typeof vi.fn>).toHaveBeenCalledWith(
        '/messages/123/reclassify',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model: 'gemma:7b' }),
        })
      );
    });

    // Wait for the component's internal setTimeout(1000)
    await waitFor(() => {
      expect(mockOnReclassify).toHaveBeenCalledWith('123');
    }, { timeout: 3000 });
  });

  it('shows loading spinner while reclassifying', async () => {
    let resolvePromise: (value: unknown) => void;
    const fetchPromise = new Promise<Response>((resolve) => {
      resolvePromise = resolve as (value: unknown) => void;
    });

    (global.fetch as ReturnType<typeof vi.fn>).mockReturnValueOnce(fetchPromise);

    render(
      <EmailItem
        email={mockEmail}
        isExpanded={false}
        onExpand={() => { }}
        onDelete={mockOnDelete}
        onReclassify={mockOnReclassify}
        selectedModel="gemma:2b"
      />
    );

    const reclassifyButton = screen.getByLabelText('reclassify');
    fireEvent.click(reclassifyButton);

    // Should show spinner
    await waitFor(() => {
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });

    // Resolve the promise
    await act(async () => {
      resolvePromise!({
        ok: true,
        json: async () => ({ success: true }),
      } as unknown as Response);
    });

    // Spinner should disappear after the async operation completes
    await waitFor(() => {
      expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    });
  });

  it('does not call onReclassify when API fails', async () => {
    vi.useFakeTimers();

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 500,
    });

    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => { });

    render(
      <EmailItem
        email={mockEmail}
        isExpanded={false}
        onExpand={() => { }}
        onDelete={mockOnDelete}
        onReclassify={mockOnReclassify}
        selectedModel="gemma:2b"
      />
    );

    const reclassifyButton = screen.getByLabelText('reclassify');

    await act(async () => {
      fireEvent.click(reclassifyButton);
      await vi.runAllTimersAsync();
    });

    expect(global.fetch as ReturnType<typeof vi.fn>).toHaveBeenCalled();
    expect(mockOnReclassify).not.toHaveBeenCalled();
    expect(consoleErrorSpy).toHaveBeenCalled();

    consoleErrorSpy.mockRestore();
    vi.useRealTimers();
  });

  it('expands to show full body when clicked', () => {
    const mockOnExpand = vi.fn();

    render(
      <EmailItem
        email={mockEmail}
        isExpanded={false}
        onExpand={mockOnExpand}
        onDelete={mockOnDelete}
        onReclassify={mockOnReclassify}
        selectedModel="gemma:2b"
      />
    );

    // Click the header area (not the whole listitem, as buttons would intercept)
    const header = screen.getByText('Test Email');
    fireEvent.click(header);

    expect(mockOnExpand).toHaveBeenCalledWith('123');
  }); it('displays classification labels as chips', () => {
    render(
      <EmailItem
        email={mockEmail}
        isExpanded={false}
        onExpand={() => { }}
        onDelete={mockOnDelete}
        onReclassify={mockOnReclassify}
        selectedModel="gemma:2b"
      />
    );

    expect(screen.getByText('work')).toBeInTheDocument();
    expect(screen.getByText('urgent')).toBeInTheDocument();
  });

  it('calls onDelete when delete button is clicked', () => {
    render(
      <EmailItem
        email={mockEmail}
        isExpanded={false}
        onExpand={() => { }}
        onDelete={mockOnDelete}
        onReclassify={mockOnReclassify}
        selectedModel="gemma:2b"
      />
    );

    const deleteButton = screen.getByLabelText('delete');
    fireEvent.click(deleteButton);

    expect(mockOnDelete).toHaveBeenCalledWith('123');
  });
});
