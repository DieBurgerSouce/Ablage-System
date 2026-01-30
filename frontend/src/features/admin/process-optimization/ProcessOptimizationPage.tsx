/**
 * Process Optimization Page
 *
 * Admin-Dashboard fuer Process Mining und System-Optimierung.
 * Vision 2.0 Phase 3: Process Mining & Autonome Automatisierung
 *
 * Features:
 * - Prozessgesundheits-Metriken
 * - Bottleneck-Erkennung und Heatmap
 * - Automatisierungsvorschlaege mit Ein-Klick-Aktivierung
 * - ROI-Tracking und Impact-Metriken
 */

import { Activity, Settings, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  ProcessHealthStats,
  BottleneckHeatmap,
  BottleneckList,
  AutomationSuggestions,
  ImpactMetrics,
} from './components';

export function ProcessOptimizationPage() {
  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <Activity className="h-8 w-8 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Prozess-Optimierung</h1>
            <p className="text-muted-foreground">
              Process Mining und automatische Optimierungsvorschlaege
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm">
            <Settings className="h-4 w-4 mr-2" />
            Einstellungen
          </Button>
        </div>
      </div>

      {/* Health Stats Overview */}
      <ProcessHealthStats />

      {/* Main Content with Tabs */}
      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList>
          <TabsTrigger value="overview">Uebersicht</TabsTrigger>
          <TabsTrigger value="bottlenecks">Engpaesse</TabsTrigger>
          <TabsTrigger value="automation">Automatisierung</TabsTrigger>
          <TabsTrigger value="impact">Auswirkungen</TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <BottleneckHeatmap />
            <AutomationSuggestions />
          </div>
        </TabsContent>

        {/* Bottlenecks Tab */}
        <TabsContent value="bottlenecks" className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <BottleneckList />
            <BottleneckHeatmap />
          </div>
        </TabsContent>

        {/* Automation Tab */}
        <TabsContent value="automation" className="space-y-6">
          <AutomationSuggestions />
        </TabsContent>

        {/* Impact Tab */}
        <TabsContent value="impact" className="space-y-6">
          <ImpactMetrics />
        </TabsContent>
      </Tabs>
    </div>
  );
}
