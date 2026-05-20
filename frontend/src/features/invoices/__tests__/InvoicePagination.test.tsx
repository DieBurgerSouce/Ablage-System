/**
 * InvoicePagination Unit Tests
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { InvoicePagination } from '../components/InvoicePagination';
import type { InvoiceFilter } from '../types/invoice-types';

describe('InvoicePagination', () => {
  const defaultFilter: Partial<InvoiceFilter> = {
    page: 1,
    perPage: 20,
  };

  it('rendert Paginierung mit korrekter Seitenzahl', () => {
    render(
      <InvoicePagination
        filter={defaultFilter}
        onFilterChange={vi.fn()}
        totalItems={100}
      />
    );

    expect(screen.getByText('Seite 1 von 5')).toBeInTheDocument();
  });

  it('zeigt korrekte Item-Anzeige', () => {
    render(
      <InvoicePagination
        filter={defaultFilter}
        onFilterChange={vi.fn()}
        totalItems={100}
      />
    );

    expect(screen.getByText(/1–20 von 100 Einträgen/)).toBeInTheDocument();
  });

  it('zeigt "Keine Einträge" bei leerer Liste', () => {
    render(
      <InvoicePagination
        filter={defaultFilter}
        onFilterChange={vi.fn()}
        totalItems={0}
      />
    );

    expect(screen.getByText('Keine Einträge')).toBeInTheDocument();
  });

  it('deaktiviert Zurück-Buttons auf erster Seite', () => {
    render(
      <InvoicePagination
        filter={{ page: 1, perPage: 20 }}
        onFilterChange={vi.fn()}
        totalItems={100}
      />
    );

    expect(screen.getByLabelText('Erste Seite')).toBeDisabled();
    expect(screen.getByLabelText('Vorherige Seite')).toBeDisabled();
  });

  it('deaktiviert Vor-Buttons auf letzter Seite', () => {
    render(
      <InvoicePagination
        filter={{ page: 5, perPage: 20 }}
        onFilterChange={vi.fn()}
        totalItems={100}
      />
    );

    expect(screen.getByLabelText('Nächste Seite')).toBeDisabled();
    expect(screen.getByLabelText('Letzte Seite')).toBeDisabled();
  });

  it('aktiviert Navigation-Buttons auf mittlerer Seite', () => {
    render(
      <InvoicePagination
        filter={{ page: 3, perPage: 20 }}
        onFilterChange={vi.fn()}
        totalItems={100}
      />
    );

    expect(screen.getByLabelText('Erste Seite')).not.toBeDisabled();
    expect(screen.getByLabelText('Vorherige Seite')).not.toBeDisabled();
    expect(screen.getByLabelText('Nächste Seite')).not.toBeDisabled();
    expect(screen.getByLabelText('Letzte Seite')).not.toBeDisabled();
  });

  it('ruft onFilterChange mit nächster Seite auf', () => {
    const onFilterChange = vi.fn();
    render(
      <InvoicePagination
        filter={{ page: 2, perPage: 20 }}
        onFilterChange={onFilterChange}
        totalItems={100}
      />
    );

    fireEvent.click(screen.getByLabelText('Nächste Seite'));

    expect(onFilterChange).toHaveBeenCalledWith({ page: 3, perPage: 20 });
  });

  it('ruft onFilterChange mit vorheriger Seite auf', () => {
    const onFilterChange = vi.fn();
    render(
      <InvoicePagination
        filter={{ page: 3, perPage: 20 }}
        onFilterChange={onFilterChange}
        totalItems={100}
      />
    );

    fireEvent.click(screen.getByLabelText('Vorherige Seite'));

    expect(onFilterChange).toHaveBeenCalledWith({ page: 2, perPage: 20 });
  });

  it('ruft onFilterChange mit erster Seite auf', () => {
    const onFilterChange = vi.fn();
    render(
      <InvoicePagination
        filter={{ page: 3, perPage: 20 }}
        onFilterChange={onFilterChange}
        totalItems={100}
      />
    );

    fireEvent.click(screen.getByLabelText('Erste Seite'));

    expect(onFilterChange).toHaveBeenCalledWith({ page: 1, perPage: 20 });
  });

  it('ruft onFilterChange mit letzter Seite auf', () => {
    const onFilterChange = vi.fn();
    render(
      <InvoicePagination
        filter={{ page: 1, perPage: 20 }}
        onFilterChange={onFilterChange}
        totalItems={100}
      />
    );

    fireEvent.click(screen.getByLabelText('Letzte Seite'));

    expect(onFilterChange).toHaveBeenCalledWith({ page: 5, perPage: 20 });
  });

  it('deaktiviert alle Buttons während Laden', () => {
    render(
      <InvoicePagination
        filter={{ page: 3, perPage: 20 }}
        onFilterChange={vi.fn()}
        totalItems={100}
        isLoading={true}
      />
    );

    expect(screen.getByLabelText('Erste Seite')).toBeDisabled();
    expect(screen.getByLabelText('Vorherige Seite')).toBeDisabled();
    expect(screen.getByLabelText('Nächste Seite')).toBeDisabled();
    expect(screen.getByLabelText('Letzte Seite')).toBeDisabled();
  });

  it('rendert Per-Page-Selector mit allen Optionen', () => {
    render(
      <InvoicePagination
        filter={defaultFilter}
        onFilterChange={vi.fn()}
        totalItems={100}
      />
    );

    expect(screen.getByText('Pro Seite:')).toBeInTheDocument();
    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });

  it('setzt Seite auf 1 bei Per-Page-Änderung', () => {
    const onFilterChange = vi.fn();
    render(
      <InvoicePagination
        filter={{ page: 3, perPage: 20 }}
        onFilterChange={onFilterChange}
        totalItems={100}
      />
    );

    // Open select and change value
    fireEvent.click(screen.getByRole('combobox'));
    fireEvent.click(screen.getByText('50'));

    expect(onFilterChange).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, perPage: 50 })
    );
  });

  it('behandelt einzelne Seite korrekt', () => {
    render(
      <InvoicePagination
        filter={{ page: 1, perPage: 20 }}
        onFilterChange={vi.fn()}
        totalItems={15}
      />
    );

    expect(screen.getByText('Seite 1 von 1')).toBeInTheDocument();
    expect(screen.getByLabelText('Nächste Seite')).toBeDisabled();
  });
});
