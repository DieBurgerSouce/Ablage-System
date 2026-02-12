/**
 * ComparePage Component
 *
 * Hauptseite für den Dokumentenvergleich.
 */

import { useState, useEffect } from 'react';
import { useSearch } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { GitCompare, Loader2 } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { apiClient } from '@/lib/api/client';
import type { ComparisonType } from './types';
import { useDiffReport } from './hooks';
import { CompareSelector, DocumentCompareView } from './components';

interface DocumentSelection {
  id: string;
  filename: string;
  documentType?: string | null;
}

interface DocumentListResponse {
  documents: Array<{
    id: string;
    filename: string;
    document_type: string | null;
  }>;
  total: number;
  page: number;
  per_page: number;
}

export function ComparePage() {
  // URL-Parameter für Deep-Linking
  const searchParams = useSearch({ strict: false }) as { doc1?: string; doc2?: string };
  const initialDoc1 = searchParams.doc1;
  const initialDoc2 = searchParams.doc2;

  // Dokumente von API laden
  const {
    data: documentsResponse,
    isLoading: isLoadingDocuments,
    isError: isDocumentsError,
  } = useQuery({
    queryKey: ['documents', 'compare'],
    queryFn: async () => {
      const response = await apiClient.get<DocumentListResponse>('/documents', {
        params: {
          page: 1,
          per_page: 100, // Genug Dokumente für Vergleich
        },
      });
      return response.data;
    },
  });

  // Dokumente in das erwartete Format konvertieren
  const availableDocuments: DocumentSelection[] =
    documentsResponse?.documents.map((doc) => ({
      id: doc.id,
      filename: doc.filename,
      documentType: doc.document_type,
    })) ?? [];

  const [document1, setDocument1] = useState<DocumentSelection | null>(null);
  const [document2, setDocument2] = useState<DocumentSelection | null>(null);
  const [comparisonType, setComparisonType] = useState<ComparisonType>('hybrid');
  const [shouldCompare, setShouldCompare] = useState(false);

  // Initialisiere ausgewählte Dokumente basierend auf URL-Parametern
  useEffect(() => {
    if (availableDocuments.length > 0) {
      if (initialDoc1 && !document1) {
        const doc = availableDocuments.find((d) => d.id === initialDoc1);
        if (doc) setDocument1(doc);
      }
      if (initialDoc2 && !document2) {
        const doc = availableDocuments.find((d) => d.id === initialDoc2);
        if (doc) setDocument2(doc);
      }
    }
  }, [availableDocuments, initialDoc1, initialDoc2, document1, document2]);

  // Diff Report Query
  const {
    data: diffReport,
    isLoading,
    error,
  } = useDiffReport(
    document1?.id ?? '',
    document2?.id ?? '',
    comparisonType,
    shouldCompare && !!document1 && !!document2
  );

  const handleCompare = () => {
    if (document1 && document2) {
      setShouldCompare(true);
    }
  };

  const handleDocument1Change = (doc: DocumentSelection | null) => {
    setDocument1(doc);
    setShouldCompare(false);
  };

  const handleDocument2Change = (doc: DocumentSelection | null) => {
    setDocument2(doc);
    setShouldCompare(false);
  };

  return (
    <ErrorBoundary
      errorTitle="Fehler beim Dokumentenvergleich"
      errorDescription="Der Dokumentenvergleich konnte nicht geladen werden. Bitte versuchen Sie es erneut."
    >
      <div className="container py-8 max-w-7xl">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <div className="p-2 bg-primary/10 rounded-lg">
            <GitCompare className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Dokumentenvergleich</h1>
            <p className="text-muted-foreground">
              Vergleichen Sie zwei Dokumente und finden Sie Unterschiede
            </p>
          </div>
        </div>

      {/* Loading State */}
      {isLoadingDocuments && (
        <div className="flex items-center justify-center py-16">
          <div className="text-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary mx-auto mb-4" />
            <p className="text-muted-foreground">Dokumente werden geladen...</p>
          </div>
        </div>
      )}

      {/* Error State */}
      {isDocumentsError && (
        <Alert variant="destructive" className="mb-8">
          <AlertTitle>Fehler beim Laden der Dokumente</AlertTitle>
          <AlertDescription>
            Die verfügbaren Dokumente konnten nicht geladen werden. Bitte versuchen Sie es später erneut.
          </AlertDescription>
        </Alert>
      )}

      {/* Selector */}
      {!isLoadingDocuments && !isDocumentsError && (
        <div className="mb-8">
          <CompareSelector
            document1={document1}
            document2={document2}
            comparisonType={comparisonType}
            onDocument1Change={handleDocument1Change}
            onDocument2Change={handleDocument2Change}
            onComparisonTypeChange={setComparisonType}
            onCompare={handleCompare}
            isComparing={isLoading}
            availableDocuments={availableDocuments}
          />
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-16">
          <div className="text-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary mx-auto mb-4" />
            <p className="text-muted-foreground">Dokumente werden verglichen...</p>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <Alert variant="destructive">
          <AlertTitle>Fehler beim Vergleich</AlertTitle>
          <AlertDescription>
            {error instanceof Error ? error.message : 'Ein unbekannter Fehler ist aufgetreten'}
          </AlertDescription>
        </Alert>
      )}

      {/* Results */}
      {diffReport && !isLoading && (
        <DocumentCompareView
          report={diffReport}
          text1=""
          text2=""
        />
      )}

      {/* Empty State */}
      {!diffReport && !isLoading && !error && (
        <div className="text-center py-16 text-muted-foreground">
          <GitCompare className="h-12 w-12 mx-auto mb-4 opacity-30" />
          <p className="text-lg">Wählen Sie zwei Dokumente aus und starten Sie den Vergleich</p>
          <p className="text-sm mt-2">
            Der Vergleich zeigt Ihnen alle Unterschiede zwischen den Dokumenten
          </p>
        </div>
      )}
      </div>
    </ErrorBoundary>
  );
}
