/**
 * Smart OCR Queue Page
 *
 * Intelligente Warteschlangen-Verwaltung mit automatischer Priorisierung
 * basierend auf Skonto-Fristen, Mahnungen und benutzerdefinierten Regeln.
 */

import { ListOrdered, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { QueueStatsCards } from './components/QueueStatsCards';
import { QueueItemsTable } from './components/QueueItemsTable';
import { PriorityRulesPanel } from './components/PriorityRulesPanel';
import { useQueryClient } from '@tanstack/react-query';
import { smartQueueKeys } from './hooks/useSmartQueue';
import { toast } from 'sonner';

export function SmartQueuePage() {
  const queryClient = useQueryClient();

  const handleRefreshAll = () => {
    queryClient.invalidateQueries({ queryKey: smartQueueKeys.all });
    toast.success('Warteschlange aktualisiert');
  };

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <ListOrdered className="h-8 w-8 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Smart OCR Queue</h1>
            <p className="text-muted-foreground">
              Intelligente Priorisierung von Dokumenten nach Dringlichkeit
            </p>
          </div>
        </div>
        <Button variant="outline" onClick={handleRefreshAll}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Aktualisieren
        </Button>
      </div>

      {/* Statistics Cards */}
      <QueueStatsCards />

      {/* Main Content Grid */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Queue Table - 2 columns */}
        <div className="lg:col-span-2">
          <QueueItemsTable />
        </div>

        {/* Priority Rules Panel - 1 column */}
        <div>
          <PriorityRulesPanel />
        </div>
      </div>
    </div>
  );
}
