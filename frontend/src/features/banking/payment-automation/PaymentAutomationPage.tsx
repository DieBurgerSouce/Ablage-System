/**
 * Payment Automation Page
 *
 * Dashboard fuer automatisierte Zahlungsvorschlaege und -batches.
 */

import { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { CreditCard, Calendar, AlertTriangle, Settings } from 'lucide-react';
import {
  SuggestionStatsCards,
  PaymentSuggestionsTable,
  PaymentScheduleView,
  SkontoAlertsPanel,
  AutomationConfigPanel,
} from './components';

export function PaymentAutomationPage() {
  const [activeTab, setActiveTab] = useState('suggestions');

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-2 bg-primary/10 rounded-lg">
          <CreditCard className="h-8 w-8 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold">Auto-Zahlungsvorschlaege</h1>
          <p className="text-muted-foreground">
            Intelligente Zahlungsplanung mit Skonto-Optimierung
          </p>
        </div>
      </div>

      {/* Statistics */}
      <SuggestionStatsCards />

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="suggestions" className="gap-2">
            <CreditCard className="h-4 w-4" />
            Vorschlaege
          </TabsTrigger>
          <TabsTrigger value="schedule" className="gap-2">
            <Calendar className="h-4 w-4" />
            Kalender
          </TabsTrigger>
          <TabsTrigger value="alerts" className="gap-2">
            <AlertTriangle className="h-4 w-4" />
            Skonto-Alerts
          </TabsTrigger>
          <TabsTrigger value="config" className="gap-2">
            <Settings className="h-4 w-4" />
            Einstellungen
          </TabsTrigger>
        </TabsList>

        <TabsContent value="suggestions" className="mt-6">
          <PaymentSuggestionsTable />
        </TabsContent>

        <TabsContent value="schedule" className="mt-6">
          <PaymentScheduleView />
        </TabsContent>

        <TabsContent value="alerts" className="mt-6">
          <SkontoAlertsPanel />
        </TabsContent>

        <TabsContent value="config" className="mt-6">
          <AutomationConfigPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}
