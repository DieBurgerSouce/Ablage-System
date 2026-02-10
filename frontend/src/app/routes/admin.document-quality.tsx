/**
 * Document Quality Admin Route
 *
 * Route fuer das Datenqualitaets-Dashboard im Admin-Bereich.
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
        <h1 className="text-2xl font-bold tracking-tight">Datenqualitaet</h1>
        <p className="text-muted-foreground">
          Qualitaets-Ampel und Uebersicht aller bewerteten Dokumente
        </p>
      </div>
      <QualityDashboard />
    </div>
  );
}
