/**
 * InvoiceFilterBar Unit Tests
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { InvoiceFilterBar } from '../components/InvoiceFilterBar';
import type { InvoiceFilter } from '../types/invoice-types';

describe('InvoiceFilterBar', () => {
  const defaultFilter: Partial<InvoiceFilter> = {
    page: 1,
    perPage: 20,
  };

  it('rendert Status-Filter mit allen Optionen', () => {
    const onFilterChange = vi.fn();
    render(<InvoiceFilterBar filter={defaultFilter} onFilterChange={onFilterChange} />);

    // Click to open dropdown
    const statusTrigger = screen.getByRole('combobox');
    fireEvent.click(statusTrigger);

    // Should show all status options (using getAllByRole for multiple matching options)
    const options = screen.getAllByRole('option');
    const optionTexts = options.map((opt) => opt.textContent);

    expect(optionTexts).toContain('Alle Status');
    expect(optionTexts).toContain('Offen');
    expect(optionTexts).toContain('Bezahlt');
    expect(optionTexts).toContain('Überfällig');
  });

  it('rendert Überfällig-Checkbox', () => {
    const onFilterChange = vi.fn();
    render(<InvoiceFilterBar filter={defaultFilter} onFilterChange={onFilterChange} />);

    expect(screen.getByLabelText('Nur überfällige')).toBeInTheDocument();
  });

  it('ruft onFilterChange bei Status-Änderung auf', () => {
    const onFilterChange = vi.fn();
    render(<InvoiceFilterBar filter={defaultFilter} onFilterChange={onFilterChange} />);

    // Click to open dropdown
    const statusTrigger = screen.getByRole('combobox');
    fireEvent.click(statusTrigger);

    // Select "Bezahlt"
    fireEvent.click(screen.getByText('Bezahlt'));

    expect(onFilterChange).toHaveBeenCalledWith(
      expect.objectContaining({
        status: 'paid',
        page: 1,
      })
    );
  });

  it('ruft onFilterChange bei Überfällig-Checkbox Änderung auf', () => {
    const onFilterChange = vi.fn();
    render(<InvoiceFilterBar filter={defaultFilter} onFilterChange={onFilterChange} />);

    const checkbox = screen.getByLabelText('Nur überfällige');
    fireEvent.click(checkbox);

    expect(onFilterChange).toHaveBeenCalledWith(
      expect.objectContaining({
        overdueOnly: true,
        page: 1,
      })
    );
  });

  it('zeigt Reset-Button nur wenn Filter aktiv sind', () => {
    const onFilterChange = vi.fn();
    const { rerender } = render(
      <InvoiceFilterBar filter={defaultFilter} onFilterChange={onFilterChange} />
    );

    // Should not show reset button initially
    expect(screen.queryByText('Filter zurücksetzen')).not.toBeInTheDocument();

    // Rerender with active filter
    rerender(
      <InvoiceFilterBar
        filter={{ ...defaultFilter, status: 'paid' }}
        onFilterChange={onFilterChange}
      />
    );

    // Should now show reset button
    expect(screen.getByText('Filter zurücksetzen')).toBeInTheDocument();
  });

  it('setzt Filter auf Reset-Klick zurück', () => {
    const onFilterChange = vi.fn();
    render(
      <InvoiceFilterBar
        filter={{ ...defaultFilter, status: 'paid', overdueOnly: true }}
        onFilterChange={onFilterChange}
      />
    );

    const resetButton = screen.getByText('Filter zurücksetzen');
    fireEvent.click(resetButton);

    expect(onFilterChange).toHaveBeenCalledWith({
      page: 1,
      perPage: 20,
    });
  });

  it('setzt Page auf 1 bei Filter-Änderungen', () => {
    const onFilterChange = vi.fn();
    render(
      <InvoiceFilterBar
        filter={{ ...defaultFilter, page: 5 }}
        onFilterChange={onFilterChange}
      />
    );

    const checkbox = screen.getByLabelText('Nur überfällige');
    fireEvent.click(checkbox);

    expect(onFilterChange).toHaveBeenCalledWith(
      expect.objectContaining({
        page: 1,
      })
    );
  });

  it('hat Labels mit korrekten For-Attributen (A11y)', () => {
    const onFilterChange = vi.fn();
    render(<InvoiceFilterBar filter={defaultFilter} onFilterChange={onFilterChange} />);

    // Status label should be associated with select (UI_LABELS.filterStatus + ":")
    const statusLabel = screen.getByText(/Status:/);
    expect(statusLabel).toHaveAttribute('for', 'status-filter');

    // Overdue label should be associated with checkbox (UI_LABELS.filterOverdueOnly)
    const overdueLabel = screen.getByText(/Nur überfällige/);
    expect(overdueLabel).toHaveAttribute('for', 'overdue-filter');
  });
});
