/**
 * B1-Regression: WidgetSyncStatus ausserhalb eines TooltipProvider
 *
 * DashboardGridEnhanced.tsx renderte <WidgetSyncStatus> OHNE umgebenden
 * TooltipProvider. Radix' Tooltip.Root wirft dann
 * "`Tooltip` must be used within `TooltipProvider`" -> das Admin-Dashboard
 * ('/') landete deterministisch im Root-ErrorBoundary ("Anwendungsfehler").
 *
 * Fix: WidgetSyncStatus bringt seinen eigenen TooltipProvider mit und ist
 * damit selbsttragend - dieser Test rendert die Komponente bewusst OHNE
 * aeusseren Provider (exakt das Crash-Szenario).
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WidgetSyncStatus } from '../components/WidgetSyncStatus';

describe('WidgetSyncStatus (B1)', () => {
  it('rendert ohne aeusseren TooltipProvider ohne zu werfen', () => {
    expect(() =>
      render(
        <WidgetSyncStatus
          isLoading={false}
          isSyncing={false}
          lastSynced={null}
          error={null}
          onSync={() => {}}
        />
      )
    ).not.toThrow();

    expect(screen.getByText('Nicht synchronisiert')).toBeInTheDocument();
    expect(screen.getByText('Jetzt synchronisieren')).toBeInTheDocument();
  });

  it('zeigt Sync-Fehlerstatus an', () => {
    render(
      <WidgetSyncStatus
        error={new Error('kaputt')}
        onSync={() => {}}
      />
    );

    expect(screen.getByText('Sync fehlgeschlagen')).toBeInTheDocument();
  });

  it('zeigt die letzte Synchronisierung relativ an', () => {
    const fuenfMinuten = new Date(Date.now() - 5 * 60 * 1000);
    render(<WidgetSyncStatus lastSynced={fuenfMinuten} />);

    expect(screen.getByText('Zuletzt: Vor 5 Min.')).toBeInTheDocument();
  });

  it('Sync-Button ist waehrend laufender Synchronisierung deaktiviert', () => {
    const onSync = vi.fn();
    render(<WidgetSyncStatus isSyncing onSync={onSync} />);

    const button = screen.getByRole('button', {
      name: 'Jetzt synchronisieren'
    });
    expect(button).toBeDisabled();
  });
});
