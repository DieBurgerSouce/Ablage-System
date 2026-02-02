/**
 * DocumentLineagePage Component
 *
 * Vollstaendige Seite zur Anzeige der Dokumenten-Lineage.
 * Kann als eigenstaendige Route verwendet werden.
 */

import { useMemo } from 'react';
import { cn } from '@/lib/utils';
import { formatDateDE } from '@/lib/format';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import {
  ArrowLeft,
  FileText,
  GitBranch,
  Download,
  RefreshCw,
} from 'lucide-react';

import { LineageFlowchart } from '../LineageFlowchart';
import { LineageStatsCards } from '../components/LineageStatsCards';
import { useLineageData } from '../hooks/useLineageData';
import { lineageService } from '@/lib/api/services/lineage';

// =============================================================================
// Types
// =============================================================================

export interface DocumentLineagePageProps {
  /** Dokument-ID */
  documentId: string;
  /** Dokument-Name (optional, fuer Breadcrumb) */
  documentName?: string;
  /** Callback fuer Zurueck-Navigation */
  onBack?: () => void;
  /** Callback bei Klick auf Entity */
  onNavigateToEntity?: (entityId: string) => void;
  /** Callback bei Klick auf Dokument */
  onNavigateToDocument?: (documentId: string) => void;
  /** Zusaetzliche CSS-Klassen */
  className?: string;
}

// =============================================================================
// Component
// =============================================================================

export function DocumentLineagePage({
  documentId,
  documentName,
  onBack,
  onNavigateToEntity,
  onNavigateToDocument,
  className,
}: DocumentLineagePageProps) {
  const { timeline, stats, summary, isLoading, isError, refetch } =
    useLineageData(documentId);

  // Dokument-Info aus Summary
  const documentInfo = useMemo(() => {
    if (!summary) return null;

    return {
      importedAt: summary.importInfo.importedAt,
      sourceType: summary.importInfo.sourceType,
      ocrBackend: summary.ocr.backend,
      totalEvents: summary.statistics.totalEventCount,
    };
  }, [summary]);

  // Export Handler
  const handleExport = async () => {
    try {
      const blob = await lineageService.exportLineage(documentId, 'json');
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `lineage_${documentId}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Export fehlgeschlagen:', error);
    }
  };

  return (
    <div className={cn('flex flex-col min-h-full', className)}>
      {/* Header */}
      <header className="flex flex-col gap-4 p-4 border-b bg-background/95 backdrop-blur-sm sticky top-0 z-20">
        {/* Breadcrumb */}
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            {onBack && (
              <Button
                variant="ghost"
                size="icon"
                onClick={onBack}
                className="h-8 w-8"
              >
                <ArrowLeft className="h-4 w-4" />
              </Button>
            )}

            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/documents">Dokumente</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href={`/documents/${documentId}`}>
                    {documentName || documentId.slice(0, 8) + '...'}
                  </BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Lineage</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              disabled={isLoading}
            >
              <RefreshCw
                className={cn('h-4 w-4 mr-2', isLoading && 'animate-spin')}
              />
              Aktualisieren
            </Button>

            <Button variant="outline" size="sm" onClick={handleExport}>
              <Download className="h-4 w-4 mr-2" />
              Export
            </Button>
          </div>
        </div>

        {/* Title */}
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-primary/10">
            <GitBranch className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-semibold">Dokumenten-Lineage</h1>
            <p className="text-sm text-muted-foreground">
              {documentInfo ? (
                <>
                  Importiert am {formatDateDE(documentInfo.importedAt)}
                  {documentInfo.sourceType && (
                    <> via {documentInfo.sourceType.replace(/_/g, ' ')}</>
                  )}
                  {documentInfo.totalEvents > 0 && (
                    <> - {documentInfo.totalEvents} Events</>
                  )}
                </>
              ) : (
                'Vollstaendige Verarbeitungs-Timeline'
              )}
            </p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 p-4 space-y-4">
        {/* Stats Cards */}
        <LineageStatsCards stats={stats} summary={summary} isLoading={isLoading} />

        <Separator />

        {/* Flowchart */}
        <div className="flex-1 min-h-[600px]">
          <LineageFlowchart
            documentId={documentId}
            height="calc(100vh - 400px)"
            showMinimap={true}
            showControls={true}
            onNavigateToEntity={onNavigateToEntity}
            onNavigateToDocument={onNavigateToDocument}
            initialLayout="horizontal"
          />
        </div>
      </main>
    </div>
  );
}

// =============================================================================
// Standalone Wrapper (fuer Router)
// =============================================================================

interface DocumentLineagePageWrapperProps {
  params: {
    documentId: string;
  };
}

/**
 * Wrapper-Komponente fuer die Router-Integration.
 * Extrahiert die documentId aus den Route-Params.
 */
export function DocumentLineagePageWrapper({
  params,
}: DocumentLineagePageWrapperProps) {
  const { documentId } = params;

  // Hier koennen zusaetzliche Daten geladen werden (z.B. Dokument-Name)

  return (
    <DocumentLineagePage
      documentId={documentId}
      onBack={() => window.history.back()}
      onNavigateToEntity={(entityId) => {
        // Navigation zur Entity-Seite
        window.location.href = `/entities/${entityId}`;
      }}
      onNavigateToDocument={(docId) => {
        // Navigation zur Dokument-Seite
        window.location.href = `/documents/${docId}`;
      }}
    />
  );
}

export default DocumentLineagePage;
