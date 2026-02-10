/**
 * Recurring Invoices (Abo-Rechnungen) Route
 *
 * Route: /recurring-invoices
 *
 * Features:
 * - Abo-Uebersicht mit Tabelle
 * - Soll/Ist-Vergleich
 * - Fehlende Rechnungen und Preisaenderungen (Alerts)
 * - Detailansicht mit Occurrence-History
 */

import { useState } from 'react';
import { createFileRoute } from '@tanstack/react-router';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Repeat,
  BarChart3,
  AlertTriangle,
} from 'lucide-react';
import {
  RecurringInvoiceList,
  RecurringInvoiceDetail,
  RecurringAlerts,
  RecurringSollIst,
} from '@/features/recurring-invoices/components';

// ==================== Route Search Params ====================

interface RecurringInvoicesSearch {
  detail?: string;
  tab?: string;
}

export const Route = createFileRoute('/recurring-invoices')({
  validateSearch: (search: Record<string, unknown>): RecurringInvoicesSearch => ({
    detail: search.detail as string | undefined,
    tab: search.tab as string | undefined,
  }),
  component: RecurringInvoicesPage,
});

// ==================== Page ====================

function RecurringInvoicesPage() {
  const { detail, tab } = Route.useSearch();
  const navigate = Route.useNavigate();
  const [activeTab, setActiveTab] = useState(tab || 'abos');

  // Detail-Ansicht
  if (detail) {
    return (
      <div className="p-8">
        <RecurringInvoiceDetail
          recurringId={detail}
          onBack={() => navigate({ search: { tab: activeTab } })}
        />
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Abo-Rechnungen</h1>
        <p className="text-muted-foreground">
          Verwaltung wiederkehrender Rechnungen und Abonnements
        </p>
      </div>

      <Tabs
        value={activeTab}
        onValueChange={(val) => {
          setActiveTab(val);
          navigate({ search: { tab: val } });
        }}
      >
        <TabsList>
          <TabsTrigger value="abos" className="gap-2">
            <Repeat className="h-4 w-4" />
            Abos
          </TabsTrigger>
          <TabsTrigger value="soll-ist" className="gap-2">
            <BarChart3 className="h-4 w-4" />
            Soll/Ist
          </TabsTrigger>
          <TabsTrigger value="alerts" className="gap-2">
            <AlertTriangle className="h-4 w-4" />
            Alerts
          </TabsTrigger>
        </TabsList>

        <TabsContent value="abos" className="mt-6">
          <RecurringInvoiceList />
        </TabsContent>

        <TabsContent value="soll-ist" className="mt-6">
          <RecurringSollIst />
        </TabsContent>

        <TabsContent value="alerts" className="mt-6">
          <RecurringAlerts />
        </TabsContent>
      </Tabs>
    </div>
  );
}
