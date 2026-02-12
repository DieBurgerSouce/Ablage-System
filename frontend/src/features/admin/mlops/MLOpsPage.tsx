/**
 * MLOps Dashboard Page
 *
 * Hauptseite für das Machine Learning Operations Dashboard.
 * Zeigt Modell-Registry, Retraining-Jobs, A/B Tests und Performance-Statistiken.
 *
 * Vision 2.0 Phase 3: Erweitert um A/B Test Vergleiche und Rollback-Historie.
 */

import { Brain } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  MLOpsStatsCards,
  ModelRegistryTable,
  RetrainingJobsPanel,
  RetrainingConfigPanel,
  PerformanceChart,
  ABTestComparison,
  RollbackTimeline,
} from './components';

export function MLOpsPage() {
  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-2 bg-primary/10 rounded-lg">
          <Brain className="h-8 w-8 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold">MLOps Dashboard</h1>
          <p className="text-muted-foreground">
            Modell-Verwaltung, Retraining und Performance-Monitoring
          </p>
        </div>
      </div>

      {/* Statistics Cards */}
      <MLOpsStatsCards />

      {/* Main Content with Tabs */}
      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList>
          <TabsTrigger value="overview">Übersicht</TabsTrigger>
          <TabsTrigger value="ab-tests">A/B Tests</TabsTrigger>
          <TabsTrigger value="retraining">Retraining</TabsTrigger>
          <TabsTrigger value="history">Historie</TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            {/* Left Column */}
            <div className="space-y-6">
              <ModelRegistryTable />
              <RetrainingConfigPanel />
            </div>

            {/* Right Column */}
            <div className="space-y-6">
              <PerformanceChart />
              <RetrainingJobsPanel />
            </div>
          </div>
        </TabsContent>

        {/* A/B Tests Tab */}
        <TabsContent value="ab-tests" className="space-y-6">
          <ABTestComparison />
        </TabsContent>

        {/* Retraining Tab */}
        <TabsContent value="retraining" className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <RetrainingJobsPanel />
            <RetrainingConfigPanel />
          </div>
        </TabsContent>

        {/* History Tab */}
        <TabsContent value="history" className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <RollbackTimeline />
            <PerformanceChart />
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
