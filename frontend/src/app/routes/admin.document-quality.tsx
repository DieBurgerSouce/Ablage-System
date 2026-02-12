/**
 * Document Quality Admin Route
 *
 * Route für das Datenqualitäts-Dashboard im Admin-Bereich.
 */

import { createFileRoute } from '@tanstack/react-router';
import { QualityDashboard } from '@/features/document-quality/components';

export const Route = createFileRoute('/admin/document-quality')({
  component: DocumentQualityPage,
});

function DocumentQualityPage() {
  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Datenqualität</h1>
        <p className="text-muted-foreground">
          Qualitäts-Ampel und Übersicht aller bewerteten Dokumente
        </p>
      </div>
      <QualityDashboard />
    </div>
  );
}
