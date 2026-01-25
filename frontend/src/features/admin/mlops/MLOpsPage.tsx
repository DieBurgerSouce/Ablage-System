/**
 * MLOps Dashboard Page
 *
 * Hauptseite fuer das Machine Learning Operations Dashboard.
 * Zeigt Modell-Registry, Retraining-Jobs und Performance-Statistiken.
 */

import { Brain } from 'lucide-react';
import {
  MLOpsStatsCards,
  ModelRegistryTable,
  RetrainingJobsPanel,
  RetrainingConfigPanel,
  PerformanceChart,
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

      {/* Main Grid */}
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
    </div>
  );
}
