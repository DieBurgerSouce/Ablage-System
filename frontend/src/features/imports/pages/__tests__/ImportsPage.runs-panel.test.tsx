/**
 * B13-Regression (W3-F2): ImportRunsPanel muss auf der ImportsPage haengen.
 *
 * Das Panel (Live-Status der Import-Laeufe, Original-Commit cc5f38ae9) war
 * nur in den verwaisten Routen /admin/imports/email + /folder eingebaut -
 * Sidebar und Dashboard verlinken aber ausschliesslich /admin/imports
 * (= ImportsPage). Damit war der Vertrauens-Loop unerreichbar.
 *
 * Dieser Test rendert die ImportsPage (schwere Geschwister gemockt, das
 * Panel selbst REAL) und stellt sicher, dass der Live-Status im
 * Uebersicht-Tab sichtbar ist.
 */

import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

import { ImportsPage } from '../ImportsPage';
import type { ImportRun } from '../../types/import-types';

// Schwere Geschwister-Komponenten stubben (eigene Tests vorhanden)
vi.mock('../../components/EmailConfigList', () => ({
  EmailConfigList: () => <div data-testid="email-config-list" />
}));
vi.mock('../../components/FolderConfigList', () => ({
  FolderConfigList: () => <div data-testid="folder-config-list" />
}));
vi.mock('../../components/ImportLogTable', () => ({
  ImportLogTable: () => <div data-testid="import-log-table" />
}));
vi.mock('../../components/ImportRuleBuilder', () => ({
  ImportRuleBuilder: () => <div />
}));
vi.mock('../../components/RuleTestingPanel', () => ({
  RuleTestingPanel: () => <div />
}));
vi.mock('../../components/EmailConfigForm', () => ({
  EmailConfigForm: () => <div />
}));
vi.mock('../../components/FolderConfigForm', () => ({
  FolderConfigForm: () => <div />
}));

const exampleRun: ImportRun = {
  batchId: 'batch-b13',
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
  lastUpdate: new Date('2026-06-10T14:35:00Z').toISOString()
};

vi.mock('../../hooks/use-import-queries', () => ({
  useImportStats: () => ({ data: undefined, isLoading: false }),
  useImportRules: () => ({ data: [], isLoading: false }),
  useImportRuns: () => ({
    data: [exampleRun],
    isLoading: false,
    isError: false
  })
}));

describe('ImportsPage x ImportRunsPanel (B13)', () => {
  it('zeigt den Live-Status der Import-Laeufe im Uebersicht-Tab', () => {
    render(<ImportsPage />);

    // Panel-Header + aggregierter Lauf sind sichtbar
    expect(screen.getByText('Letzte Import-Läufe')).toBeInTheDocument();
    expect(screen.getByText(/12 E-Mails/)).toBeInTheDocument();

    // und die Uebersicht selbst ist gerendert (kein Form-Modus)
    expect(screen.getByTestId('email-config-list')).toBeInTheDocument();
    expect(screen.getByTestId('folder-config-list')).toBeInTheDocument();
  });
});
