/**
 * Admin Art.30 Verarbeitungsverzeichnis Route
 *
 * Zeigt das Verzeichnis von Verarbeitungstaetigkeiten (Art. 30 DSGVO) fuer
 * Administratoren (Rechenschaftspflicht, bei Audits vorzulegen). Der Zugriff
 * ist serverseitig superuser-gated (403 fuer Nicht-Admins).
 */

import { createFileRoute } from '@tanstack/react-router';
import { FileText } from 'lucide-react';
import { ProcessingActivitiesTable } from '@/features/admin/gdpr';

export const Route = createFileRoute('/admin/gdpr-processing')({
  component: AdminGdprProcessingPage,
});

function AdminGdprProcessingPage() {
  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <FileText className="h-8 w-8 text-primary" />
        <div>
          <h1 className="text-3xl font-bold">Art.30 Verarbeitungsverzeichnis</h1>
          <p className="text-muted-foreground">
            DSGVO-Rechenschaftspflicht: Verzeichnis aller Verarbeitungstätigkeiten.
            Subject-IDs sind pseudonymisiert (Art. 4(5) DSGVO).
          </p>
        </div>
      </div>

      <ProcessingActivitiesTable />
    </div>
  );
}
