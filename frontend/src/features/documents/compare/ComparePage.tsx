/**
 * ComparePage Component
 *
 * Hauptseite fuer den Dokumentenvergleich.
 */

import { useState } from 'react';
import { useSearchParams } from '@tanstack/react-router';
import { GitCompare, Loader2 } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import type { ComparisonType } from './types';
import { useDiffReport } from './hooks';
import { CompareSelector, DocumentCompareView } from './components';

interface DocumentSelection {
  id: string;
  filename: string;
  documentType?: string | null;
}

// Mock-Daten fuer verfuegbare Dokumente (in Production durch API ersetzen)
const mockDocuments: DocumentSelection[] = [
  { id: '1', filename: 'Rechnung_2026_001.pdf', documentType: 'invoice' },
  { id: '2', filename: 'Rechnung_2026_002.pdf', documentType: 'invoice' },
  { id: '3', filename: 'Lieferschein_A123.pdf', documentType: 'delivery_note' },
  { id: '4', filename: 'Angebot_XYZ.pdf', documentType: 'quote' },
];

export function ComparePage() {
  // URL-Parameter fuer Deep-Linking
  const searchParams = useSearchParams();
  const initialDoc1 = searchParams.doc1 as string | undefined;
  const initialDoc2 = searchParams.doc2 as string | undefined;

  const [document1, setDocument1] = useState<DocumentSelection | null>(
    initialDoc1 ? mockDocuments.find((d) => d.id === initialDoc1) ?? null : null
  );
  const [document2, setDocument2] = useState<DocumentSelection | null>(
    initialDoc2 ? mockDocuments.find((d) => d.id === initialDoc2) ?? null : null
  );
  const [comparisonType, setComparisonType] = useState<ComparisonType>('hybrid');
  const [shouldCompare, setShouldCompare] = useState(false);

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

      {/* Selector */}
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
          availableDocuments={mockDocuments}
        />
      </div>

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
          onExportPdf={() => {
            // TODO: PDF Export implementieren
            console.log('PDF Export');
          }}
        />
      )}

      {/* Empty State */}
      {!diffReport && !isLoading && !error && (
        <div className="text-center py-16 text-muted-foreground">
          <GitCompare className="h-12 w-12 mx-auto mb-4 opacity-30" />
          <p className="text-lg">Waehlen Sie zwei Dokumente aus und starten Sie den Vergleich</p>
          <p className="text-sm mt-2">
            Der Vergleich zeigt Ihnen alle Unterschiede zwischen den Dokumenten
          </p>
        </div>
      )}
    </div>
  );
}
