/**
 * ImportRunsPanel Unit Tests (F2 — Live-Status)
 *
 * Mockt den Daten-Hook, um Lade-, Leer- und Datenzustand isoliert zu prüfen.
 */

import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { ImportRunsPanel } from '../ImportRunsPanel';
import type { ImportRun } from '../../types/import-types';

const useImportRunsMock = vi.fn();

vi.mock('../../hooks/use-import-queries', () => ({
  useImportRuns: (...args: unknown[]) => useImportRunsMock(...args),
}));

function makeRun(overrides: Partial<ImportRun> = {}): ImportRun {
  return {
    batchId: 'batch-1',
    sourceType: 'email',
    configId: null,
    total: 12,
    completed: 10,
    failed: 2,
    skipped: 0,
    pending: 0,
    documentsCreated: 10,
    isRunning: false,
    startedAt: new Date('2026-06-10T14:32:00Z').toISOString(),
    lastUpdate: new Date('2026-06-10T14:35:00Z').toISOString(),
    ...overrides,
  };
}

describe('ImportRunsPanel', () => {
  beforeEach(() => {
    useImportRunsMock.mockReset();
  });

  it('zeigt das Aggregat eines Laufs (12 E-Mails, 10 OK, 2 Fehler)', () => {
    useImportRunsMock.mockReturnValue({
      data: [makeRun()],
      isLoading: false,
      isError: false,
    });

    render(<ImportRunsPanel sourceType="email" />);

    expect(screen.getByText(/12 E-Mails/)).toBeInTheDocument();
    expect(screen.getByText('10 OK')).toBeInTheDocument();
    expect(screen.getByText('2 Fehler')).toBeInTheDocument();
  });

  it('zeigt den Laufzustand bei aktivem Import', () => {
    useImportRunsMock.mockReturnValue({
      data: [makeRun({ isRunning: true, pending: 5, completed: 7, failed: 0 })],
      isLoading: false,
      isError: false,
    });

    render(<ImportRunsPanel sourceType="email" />);

    expect(screen.getByText(/wird verarbeitet/)).toBeInTheDocument();
    expect(screen.getByText('5 offen')).toBeInTheDocument();
  });

  it('zeigt einen Leerzustand ohne Läufe', () => {
    useImportRunsMock.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    });

    render(<ImportRunsPanel />);

    expect(screen.getByText('Noch keine Import-Läufe.')).toBeInTheDocument();
  });

  it('zeigt einen Fehlerzustand', () => {
    useImportRunsMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    });

    render(<ImportRunsPanel />);

    expect(
      screen.getByText('Import-Läufe konnten nicht geladen werden.')
    ).toBeInTheDocument();
  });
});
