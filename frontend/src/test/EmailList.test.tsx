import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import EmailList from '../components/EmailList';

describe('EmailList Component', () => {
  it('renders email list with correct number of items', () => {
    render(<EmailList />);
    const emailItems = screen.getAllByRole('listitem');
    expect(emailItems).toHaveLength(3);
  });

  it('shows email details when clicked', () => {
    render(<EmailList />);
    const firstEmail = screen.getByText('Project Update Meeting');
    fireEvent.click(firstEmail);
    
    expect(screen.getByText(/Dear team/)).toBeInTheDocument();
  });

  it('deletes email when delete button is clicked', () => {
    render(<EmailList />);
    const deleteButtons = screen.getAllByLabelText('delete');
    const initialEmails = screen.getAllByRole('listitem');
    
    fireEvent.click(deleteButtons[0]);
    
    const remainingEmails = screen.getAllByRole('listitem');
    expect(remainingEmails.length).toBe(initialEmails.length - 1);
  });

  it('displays priority chips with correct colors', () => {
    render(<EmailList />);
    const highPriority = screen.getByText('High');
    const mediumPriority = screen.getByText('Medium');
    const lowPriority = screen.getByText('Low');

    // The text node returned by getByText is the inner span of the MUI Chip.
    // Assert against the Chip wrapper (closest element with the MuiChip-root class)
    expect(highPriority.closest('.MuiChip-root')).toHaveClass('MuiChip-colorError');
    expect(mediumPriority.closest('.MuiChip-root')).toHaveClass('MuiChip-colorWarning');
    expect(lowPriority.closest('.MuiChip-root')).toHaveClass('MuiChip-colorSuccess');
  });
});