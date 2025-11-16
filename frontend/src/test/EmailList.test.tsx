import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import EmailList from '../components/EmailList';

describe('EmailList Component', () => {
  // Render smoke test: ensures the component renders the expected number
  // of email list items (from the example fixture) without runtime errors.
  it('renders email list with correct number of items', async () => {
    render(<EmailList />);
    const emailItems = await screen.findAllByRole('listitem');
    expect(emailItems).toHaveLength(3);
  });

  // Interaction test: clicking an email expands/shows its details/body.
  it('shows email details when clicked', async () => {
    render(<EmailList />);
    const firstEmail = await screen.findByText('Project Update Meeting');
    fireEvent.click(firstEmail);

    expect(await screen.findByText(/Dear team/)).toBeInTheDocument();
  });

  // Action test: clicking the delete button removes the item from the list.
  it('deletes email when delete button is clicked', async () => {
    render(<EmailList />);
    const deleteButtons = await screen.findAllByLabelText('delete');
    const initialEmails = await screen.findAllByRole('listitem');

    fireEvent.click(deleteButtons[0]);

    await screen.findAllByRole('listitem');
    // wait for the list to update and assert the count decreased by one
    await screen.findByText; // ensure async boundaries
    await (async () => {
      const remaining = screen.getAllByRole('listitem');
      expect(remaining.length).toBe(initialEmails.length - 1);
    })();
  });

  // Visual assertion: each priority label renders as an MUI Chip with the
  // expected color class (High -> error, Normal -> warning, Low -> success).
  it('displays priority chips with correct colors', async () => {
    render(<EmailList />);
    const highPriority = await screen.findByText('High');
    const normalPriority = await screen.findByText('Normal');
    const lowPriority = await screen.findByText('Low');

    // The text node returned by getByText is the inner span of the MUI Chip.
    // Assert against the Chip wrapper (closest element with the MuiChip-root class)
    expect(highPriority.closest('.MuiChip-root')).toHaveClass('MuiChip-colorError');
    expect(normalPriority.closest('.MuiChip-root')).toHaveClass('MuiChip-colorWarning');
    expect(lowPriority.closest('.MuiChip-root')).toHaveClass('MuiChip-colorSuccess');
  });
});