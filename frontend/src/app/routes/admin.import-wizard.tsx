import { createFileRoute } from '@tanstack/react-router';
import { ImportWizard } from '@/features/import-wizard';
import { UnifiedErrorBoundary } from '@/components/errors/UnifiedErrorBoundary';

export const Route = createFileRoute('/admin/import-wizard')({
  component: ImportWizardRoute,
});

function ImportWizardRoute() {
  return (
    <div className="container mx-auto py-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Import-Assistent</h1>
        <p className="text-muted-foreground">
          Importieren Sie Dokumente mit einer geführten Schritt-für-Schritt-Anleitung
        </p>
      </div>

      <UnifiedErrorBoundary context="general" variant="card">
        <ImportWizard />
      </UnifiedErrorBoundary>
    </div>
  );
}
