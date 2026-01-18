/**
 * ChainVisualization - Visuelle Kettenansicht
 *
 * Zeigt den Dokumentenfluss einer Auftragskette grafisch an:
 * Angebot → Auftrag → Lieferschein → Rechnung
 *
 * Mit Verbindungslinien und Abweichungs-Markierungen.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  FileText,
  ClipboardList,
  Truck,
  Receipt,
  ArrowRight,
  AlertTriangle,
  CheckCircle,
  ExternalLink,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  type DocumentChainInfo,
  type ChainDocument,
  type DocumentTypeInChain,
  type ChainDiscrepancy,
  CHAIN_UI_LABELS,
  DOCUMENT_TYPE_STYLES,
  DISCREPANCY_SEVERITY_STYLES,
} from '../types/chain-types';
import { formatCurrency, formatDate } from '@/features/banking/utils/format';

interface ChainVisualizationProps {
  chain: DocumentChainInfo;
  onDocumentClick?: (documentId: string) => void;
  onDiscrepancyClick?: (discrepancy: ChainDiscrepancy) => void;
  className?: string;
}

const DOCUMENT_ORDER: DocumentTypeInChain[] = [
  'quote',
  'order',
  'delivery_note',
  'invoice',
];

const DOCUMENT_ICONS: Record<DocumentTypeInChain, typeof FileText> = {
  quote: FileText,
  order: ClipboardList,
  delivery_note: Truck,
  invoice: Receipt,
};

export function ChainVisualization({
  chain,
  onDocumentClick,
  onDiscrepancyClick,
  className,
}: ChainVisualizationProps) {
  // Dokumente nach Typ gruppieren
  const documentsByType = new Map<DocumentTypeInChain, ChainDocument[]>();
  DOCUMENT_ORDER.forEach((type) => documentsByType.set(type, []));
  chain.documents.forEach((doc) => {
    const docs = documentsByType.get(doc.documentType) || [];
    docs.push(doc);
    documentsByType.set(doc.documentType, docs);
  });

  // Abweichungen nach Dokumentenpaar gruppieren
  const discrepanciesByPair = new Map<string, ChainDiscrepancy[]>();
  chain.discrepancies.forEach((disc) => {
    const key = `${disc.sourceDocumentId}-${disc.targetDocumentId}`;
    const existing = discrepanciesByPair.get(key) || [];
    existing.push(disc);
    discrepanciesByPair.set(key, existing);
  });

  // Check ob Verbindung zwischen zwei Dokumenttypen Abweichungen hat
  const getConnectionDiscrepancies = (
    sourceType: DocumentTypeInChain,
    targetType: DocumentTypeInChain
  ): ChainDiscrepancy[] => {
    const sourceDocs = documentsByType.get(sourceType) || [];
    const targetDocs = documentsByType.get(targetType) || [];
    const discrepancies: ChainDiscrepancy[] = [];

    sourceDocs.forEach((source) => {
      targetDocs.forEach((target) => {
        const key = `${source.id}-${target.id}`;
        const reverseKey = `${target.id}-${source.id}`;
        discrepancies.push(...(discrepanciesByPair.get(key) || []));
        discrepancies.push(...(discrepanciesByPair.get(reverseKey) || []));
      });
    });

    return discrepancies.filter((d) => !d.isResolved);
  };

  return (
    <Card className={cn('', className)}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          Dokumentenfluss
          {chain.status === 'complete' && (
            <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
              <CheckCircle className="w-3 h-3 mr-1" />
              Vollstaendig
            </Badge>
          )}
        </CardTitle>
      </CardHeader>

      <CardContent>
        <TooltipProvider>
          <div className="flex items-start justify-between gap-2 overflow-x-auto pb-4">
            {DOCUMENT_ORDER.map((type, index) => {
              const docs = documentsByType.get(type) || [];
              const style = DOCUMENT_TYPE_STYLES[type];
              const Icon = DOCUMENT_ICONS[type];
              const hasDoc = docs.length > 0;

              // Abweichungen zur naechsten Stufe
              const nextType = DOCUMENT_ORDER[index + 1];
              const connectionDiscrepancies = nextType
                ? getConnectionDiscrepancies(type, nextType)
                : [];

              return (
                <div key={type} className="flex items-start">
                  {/* Document Node */}
                  <div className="flex flex-col items-center min-w-[120px]">
                    <div
                      className={cn(
                        'w-16 h-16 rounded-lg flex items-center justify-center border-2',
                        hasDoc
                          ? `${style.bgColor} ${style.borderColor}`
                          : 'bg-muted border-dashed border-muted-foreground/30'
                      )}
                    >
                      <Icon
                        className={cn(
                          'w-8 h-8',
                          hasDoc ? style.textColor : 'text-muted-foreground/50'
                        )}
                      />
                    </div>
                    <div className="mt-2 text-center">
                      <div
                        className={cn(
                          'text-sm font-medium',
                          hasDoc ? '' : 'text-muted-foreground'
                        )}
                      >
                        {style.label}
                      </div>
                      {hasDoc ? (
                        <div className="space-y-1 mt-1">
                          {docs.map((doc) => (
                            <Tooltip key={doc.id}>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-auto py-1 px-2 text-xs"
                                  onClick={() => onDocumentClick?.(doc.id)}
                                >
                                  <span className="truncate max-w-[100px]">
                                    {doc.referenceNumber || doc.displayName || doc.filename}
                                  </span>
                                  <ExternalLink className="w-3 h-3 ml-1" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>
                                <div className="space-y-1">
                                  <div className="font-medium">{doc.filename}</div>
                                  {doc.totalAmount && (
                                    <div>Betrag: {formatCurrency(doc.totalAmount)}</div>
                                  )}
                                  {doc.documentDate && (
                                    <div>Datum: {formatDate(doc.documentDate)}</div>
                                  )}
                                </div>
                              </TooltipContent>
                            </Tooltip>
                          ))}
                        </div>
                      ) : (
                        <div className="text-xs text-muted-foreground mt-1">
                          Nicht vorhanden
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Connection Arrow */}
                  {index < DOCUMENT_ORDER.length - 1 && (
                    <div className="flex flex-col items-center justify-center h-16 mx-2">
                      <div className="relative">
                        <ArrowRight
                          className={cn(
                            'w-6 h-6',
                            connectionDiscrepancies.length > 0
                              ? 'text-yellow-500'
                              : 'text-muted-foreground'
                          )}
                        />
                        {connectionDiscrepancies.length > 0 && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <button
                                className="absolute -top-2 -right-2 w-5 h-5 bg-yellow-100 rounded-full flex items-center justify-center border border-yellow-300"
                                onClick={() =>
                                  onDiscrepancyClick?.(connectionDiscrepancies[0])
                                }
                              >
                                <AlertTriangle className="w-3 h-3 text-yellow-600" />
                              </button>
                            </TooltipTrigger>
                            <TooltipContent>
                              <div className="space-y-1">
                                <div className="font-medium">
                                  {connectionDiscrepancies.length} Abweichung(en)
                                </div>
                                {connectionDiscrepancies.slice(0, 3).map((disc) => {
                                  const severityStyle =
                                    DISCREPANCY_SEVERITY_STYLES[disc.severity];
                                  return (
                                    <div
                                      key={disc.id}
                                      className={cn(
                                        'text-xs px-2 py-1 rounded',
                                        severityStyle.bgColor,
                                        severityStyle.textColor
                                      )}
                                    >
                                      {disc.description}
                                    </div>
                                  );
                                })}
                              </div>
                            </TooltipContent>
                          </Tooltip>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </TooltipProvider>

        {/* Gesamtwert */}
        <div className="flex items-center justify-between pt-4 border-t mt-4">
          <div className="text-sm text-muted-foreground">Gesamtwert der Kette</div>
          <div className="text-lg font-semibold">{formatCurrency(chain.totalValue)}</div>
        </div>
      </CardContent>
    </Card>
  );
}
