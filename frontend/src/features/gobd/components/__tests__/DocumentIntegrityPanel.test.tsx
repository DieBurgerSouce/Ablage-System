/**
 * DocumentIntegrityPanel Unit Tests (Trust-Theater K1, 2026-07-12)
 *
 * Mockt die GoBD-Hooks, um Badge- und Beweis-Zustände isoliert zu prüfen:
 * versiegelt/nicht versiegelt, grüner Beweis, roter Manipulations-Befund,
 * ehrlicher „keine Baseline"-Zustand.
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { DocumentIntegrityPanel } from '../DocumentIntegrityPanel';
import type { DocumentProof } from '../../types';

const useArchiveEntryMock = vi.fn();
const useProveDocumentMock = vi.fn();

vi.mock('../../hooks/use-gobd', () => ({
  useArchiveEntry: (...args: unknown[]) => useArchiveEntryMock(...args),
  useProveDocument: (...args: unknown[]) => useProveDocumentMock(...args),
}));

const DOC_ID = 'a24af4ff-cb5c-4eea-99b1-80e07e399520';

function makeProof(overrides: Partial<DocumentProof> = {}): DocumentProof {
  return {
    document_id: DOC_ID,
    verdict: 'verified',
    file_hash_matches: true,
    baseline_source: 'archiv',
    stored_hash: '5b24928acf74bc08697dc6a5e9c92455',
    computed_hash: '5b24928acf74bc08697dc6a5e9c92455',
    hash_algorithm: 'sha256',
    archived_at: '2026-07-12T19:40:00Z',
    archive_id: 'a83f1060-af61-4b64-8a01-8b35f6e29a4f',
    chain: {
      entries_total: 1,
      entries_verified: 1,
      valid: true,
      broken_at_sequence: null,
      first_entry_at: '2026-07-12T19:40:00Z',
      last_entry_at: '2026-07-12T19:40:00Z',
      message: '1 Protokoll-Einträge geprüft — Verkettung lückenlos intakt.',
    },
    tsa: {
      present: false,
      valid: null,
      message:
        'Kein qualifizierter RFC-3161-Zeitstempel vorhanden — die Versiegelung basiert auf der internen Hash-Beweiskette.',
    },
    verified_at: '2026-07-12T19:45:00Z',
    message_de:
      'Dieses Dokument ist seit dem 12.07.2026 nachweislich unverändert. Der aktuelle Dateiinhalt stimmt Bit für Bit mit dem versiegelten SHA-256-Hash überein.',
    ...overrides,
  };
}

function mockArchiveEntry(state: 'archived' | 'not-archived' | 'loading') {
  if (state === 'archived') {
    useArchiveEntryMock.mockReturnValue({
      isPending: false,
      isSuccess: true,
      isError: false,
      data: { archived_at: '2026-07-12T19:40:00Z' },
    });
  } else if (state === 'not-archived') {
    useArchiveEntryMock.mockReturnValue({
      isPending: false,
      isSuccess: false,
      isError: true,
      data: undefined,
    });
  } else {
    useArchiveEntryMock.mockReturnValue({
      isPending: true,
      isSuccess: false,
      isError: false,
      data: undefined,
    });
  }
}

function mockProve(
  state: 'idle' | 'pending' | 'error' | 'success',
  proof?: DocumentProof
) {
  const mutate = vi.fn();
  useProveDocumentMock.mockReturnValue({
    mutate,
    isPending: state === 'pending',
    isError: state === 'error',
    isSuccess: state === 'success',
    data: state === 'success' ? proof : undefined,
  });
  return mutate;
}

describe('DocumentIntegrityPanel', () => {
  beforeEach(() => {
    useArchiveEntryMock.mockReset();
    useProveDocumentMock.mockReset();
  });

  it('zeigt die Versiegelungs-Badge mit Datum und SHA-256', () => {
    mockArchiveEntry('archived');
    mockProve('idle');

    render(<DocumentIntegrityPanel documentId={DOC_ID} />);

    expect(screen.getByText(/GoBD-versiegelt seit 12\.07\.2026/)).toBeInTheDocument();
    expect(screen.getByText(/SHA-256/)).toBeInTheDocument();
  });

  it('zeigt ehrlich „Noch nicht versiegelt" bei fehlendem Archiv (404)', () => {
    mockArchiveEntry('not-archived');
    mockProve('idle');

    render(<DocumentIntegrityPanel documentId={DOC_ID} />);

    expect(screen.getByText('Noch nicht versiegelt')).toBeInTheDocument();
  });

  it('startet die Beweisführung beim Klick auf den Button', () => {
    mockArchiveEntry('archived');
    const mutate = mockProve('idle');

    render(<DocumentIntegrityPanel documentId={DOC_ID} />);
    fireEvent.click(screen.getByTestId('prove-integrity-button'));

    expect(mutate).toHaveBeenCalledWith(DOC_ID);
  });

  it('rendert den grünen Beweis mit deutscher Erklärung und Details', () => {
    mockArchiveEntry('archived');
    mockProve('success', makeProof());

    render(<DocumentIntegrityPanel documentId={DOC_ID} />);
    fireEvent.click(screen.getByTestId('prove-integrity-button'));

    expect(screen.getByTestId('integrity-result')).toHaveAttribute(
      'data-verdict',
      'verified'
    );
    expect(screen.getByText('Mathematisch bewiesen: unverändert')).toBeInTheDocument();
    expect(screen.getByText(/nachweislich unverändert/)).toBeInTheDocument();
  });

  it('rendert den roten Manipulations-Befund mit Handlungsanweisung', () => {
    mockArchiveEntry('archived');
    mockProve(
      'success',
      makeProof({
        verdict: 'tampered',
        file_hash_matches: false,
        computed_hash: 'deadbeef',
        message_de:
          'Integritätsprüfung FEHLGESCHLAGEN: Der aktuelle Dateiinhalt stimmt NICHT mit dem versiegelten Archiv-Hash überein — mögliche Manipulation! Dokument nicht weiterverwenden, umgehend den Administrator informieren und das Original aus dem Backup wiederherstellen.',
      })
    );

    render(<DocumentIntegrityPanel documentId={DOC_ID} />);
    fireEvent.click(screen.getByTestId('prove-integrity-button'));

    expect(screen.getByTestId('integrity-result')).toHaveAttribute(
      'data-verdict',
      'tampered'
    );
    expect(screen.getByText('Integrität verletzt')).toBeInTheDocument();
    expect(screen.getByText(/Administrator informieren/)).toBeInTheDocument();
    // Bei Manipulation sind die technischen Details standardmäßig aufgeklappt
    expect(screen.getByTestId('integrity-technical-details')).toBeInTheDocument();
  });

  it('rendert den ehrlichen „keine Baseline"-Zustand', () => {
    mockArchiveEntry('not-archived');
    mockProve(
      'success',
      makeProof({
        verdict: 'no_baseline',
        file_hash_matches: null,
        baseline_source: null,
        stored_hash: null,
        computed_hash: null,
        archived_at: null,
        message_de:
          'Für dieses Dokument existiert noch keine versiegelte Archiv-Baseline.',
      })
    );

    render(<DocumentIntegrityPanel documentId={DOC_ID} />);
    fireEvent.click(screen.getByTestId('prove-integrity-button'));

    expect(screen.getByTestId('integrity-result')).toHaveAttribute(
      'data-verdict',
      'no_baseline'
    );
    expect(screen.getByText('Noch keine versiegelte Baseline')).toBeInTheDocument();
  });

  it('zeigt einen ehrlichen Fehlerzustand, wenn die Prüfung selbst scheitert', () => {
    mockArchiveEntry('archived');
    mockProve('error');

    render(<DocumentIntegrityPanel documentId={DOC_ID} />);
    fireEvent.click(screen.getByTestId('prove-integrity-button'));

    expect(screen.getByTestId('integrity-error')).toBeInTheDocument();
    expect(screen.getByText('Beweisführung nicht möglich')).toBeInTheDocument();
  });
});
