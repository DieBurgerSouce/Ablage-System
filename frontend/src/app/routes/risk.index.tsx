/**
 * Risk Scoring Index Route
 *
 * Hauptseite für das Risiko-Scoring Dashboard.
 */

import { createFileRoute } from '@tanstack/react-router';
import { AlertTriangle } from 'lucide-react';
import { RiskDashboard, UI_LABELS } from '@/features/risk-scoring';

export const Route = createFileRoute('/risk/')({
  component: RiskScoringPage,
});

function RiskScoringPage() {
  return (
    <div className="container mx-auto py-8">
      {/* Page Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
          <AlertTriangle className="h-8 w-8 text-destructive" />
          {UI_LABELS.pageTitle}
        </h1>
        <p className="text-muted-foreground mt-1">{UI_LABELS.pageSubtitle}</p>
      </div>

      {/* Dashboard */}
      <RiskDashboard />
    </div>
  );
}
