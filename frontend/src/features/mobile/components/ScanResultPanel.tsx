/**
 * ScanResultPanel Component
 *
 * Shows OCR processing status and results after document upload.
 *
 * Features:
 * - Processing spinner with progress indication
 * - OCR result display (text preview, document type, confidence)
 * - Auto-detected metadata (Datum, Betrag, Absender)
 * - Action buttons for assignment and completion
 *
 * All user-facing text is in German.
 * Phase 3.2 der Feature-Roadmap (Februar 2026)
 */

import { useCallback } from 'react';
import {
  FileText,
  Loader2,
  CheckCircle2,
  AlertCircle,
  UserCheck,
  ArrowRight,
  Camera,
  Calendar,
  Euro,
  Building2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import type { OCRResultSummary } from '../hooks/use-scan-flow';

// ==================== Types ====================

interface ScanResultPanelProps {
  /** Current document ID */
  documentId: string;
  /** OCR processing phase: 'processing' or 'result' */
  phase: 'processing' | 'result';
  /** OCR result data (null while processing) */
  ocrResult: OCRResultSummary | null;
  /** Called when user wants to assign to entity */
  onAssign: (documentId: string) => void;
  /** Called when user taps "Fertig" */
  onComplete: () => void;
  /** Called when user wants to scan another document */
  onScanAnother: () => void;
  /** Additional CSS classes */
  className?: string;
}

// ==================== Helper ====================

function formatConfidence(confidence: number): string {
  return `${Math.round(confidence * 100)}%`;
}

function getConfidenceBadgeVariant(
  confidence: number
): 'default' | 'secondary' | 'destructive' {
  if (confidence >= 0.8) return 'default';
  if (confidence >= 0.5) return 'secondary';
  return 'destructive';
}

function getDocumentTypeLabel(type: string | null): string {
  if (!type) return 'Unbekannt';

  const typeMap: Record<string, string> = {
    invoice: 'Rechnung',
    receipt: 'Quittung',
    contract: 'Vertrag',
    letter: 'Brief',
    order: 'Bestellung',
    delivery_note: 'Lieferschein',
    credit_note: 'Gutschrift',
    offer: 'Angebot',
  };

  return typeMap[type] || type;
}

// ==================== Component ====================

export function ScanResultPanel({
  documentId,
  phase,
  ocrResult,
  onAssign,
  onComplete,
  onScanAnother,
  className,
}: ScanResultPanelProps) {
  const handleAssign = useCallback(() => {
    onAssign(documentId);
  }, [documentId, onAssign]);

  // ==================== Processing State ====================

  if (phase === 'processing') {
    return (
      <Card className={cn('max-w-lg mx-auto', className)}>
        <CardContent className="pt-6">
          <div className="flex flex-col items-center gap-4 py-6">
            <div className="relative">
              <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center">
                <Loader2 className="h-8 w-8 text-primary animate-spin" />
              </div>
            </div>

            <div className="text-center space-y-2">
              <p className="font-medium text-lg">OCR-Erkennung laeuft...</p>
              <p className="text-sm text-muted-foreground">
                Das Dokument wird analysiert. Dies kann einige Sekunden dauern.
              </p>
            </div>

            <Progress value={undefined} className="w-full max-w-xs" />

            <p className="text-xs text-muted-foreground">
              Text, Dokumenttyp und Metadaten werden erkannt
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  // ==================== Result State ====================

  const hasText = ocrResult && ocrResult.extractedText.length > 0;
  const hasMetadata =
    ocrResult?.metadata.datum ||
    ocrResult?.metadata.betrag ||
    ocrResult?.metadata.absender;
  const hasEntityMatch = ocrResult?.matchedEntityName;
  const isFailed = ocrResult && ocrResult.confidence === 0 && !hasText;

  return (
    <Card className={cn('max-w-lg mx-auto', className)}>
      <CardContent className="pt-6 space-y-4">
        {/* Status Header */}
        <div className="flex items-center gap-3">
          {isFailed ? (
            <div className="h-10 w-10 rounded-full bg-destructive/10 flex items-center justify-center shrink-0">
              <AlertCircle className="h-5 w-5 text-destructive" />
            </div>
          ) : (
            <div className="h-10 w-10 rounded-full bg-green-500/10 flex items-center justify-center shrink-0">
              <CheckCircle2 className="h-5 w-5 text-green-500" />
            </div>
          )}
          <div className="flex-1 min-w-0">
            <p className="font-medium">
              {isFailed ? 'Verarbeitung fehlgeschlagen' : 'Erkennung abgeschlossen'}
            </p>
            {ocrResult && !isFailed && (
              <div className="flex items-center gap-2 mt-0.5">
                <Badge variant={getConfidenceBadgeVariant(ocrResult.confidence)}>
                  {formatConfidence(ocrResult.confidence)} Konfidenz
                </Badge>
                {ocrResult.documentType && (
                  <Badge variant="outline">
                    {getDocumentTypeLabel(ocrResult.documentType)}
                  </Badge>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Extracted Text Preview */}
        {hasText && (
          <div className="space-y-1.5">
            <p className="text-sm font-medium text-muted-foreground flex items-center gap-1.5">
              <FileText className="h-3.5 w-3.5" />
              Erkannter Text
            </p>
            <div className="bg-muted/50 rounded-lg p-3 max-h-32 overflow-y-auto">
              <p className="text-sm whitespace-pre-line line-clamp-6">
                {ocrResult.extractedText}
              </p>
            </div>
          </div>
        )}

        {/* Extracted Metadata */}
        {hasMetadata && (
          <div className="space-y-1.5">
            <p className="text-sm font-medium text-muted-foreground">
              Erkannte Daten
            </p>
            <div className="grid grid-cols-1 gap-2">
              {ocrResult.metadata.datum && (
                <div className="flex items-center gap-2 bg-muted/30 rounded-lg px-3 py-2">
                  <Calendar className="h-4 w-4 text-muted-foreground shrink-0" />
                  <div className="min-w-0">
                    <p className="text-xs text-muted-foreground">Datum</p>
                    <p className="text-sm font-medium truncate">
                      {ocrResult.metadata.datum}
                    </p>
                  </div>
                </div>
              )}
              {ocrResult.metadata.betrag && (
                <div className="flex items-center gap-2 bg-muted/30 rounded-lg px-3 py-2">
                  <Euro className="h-4 w-4 text-muted-foreground shrink-0" />
                  <div className="min-w-0">
                    <p className="text-xs text-muted-foreground">Betrag</p>
                    <p className="text-sm font-medium truncate">
                      {ocrResult.metadata.betrag}
                    </p>
                  </div>
                </div>
              )}
              {ocrResult.metadata.absender && (
                <div className="flex items-center gap-2 bg-muted/30 rounded-lg px-3 py-2">
                  <Building2 className="h-4 w-4 text-muted-foreground shrink-0" />
                  <div className="min-w-0">
                    <p className="text-xs text-muted-foreground">Absender</p>
                    <p className="text-sm font-medium truncate">
                      {ocrResult.metadata.absender}
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Entity Match Hint */}
        {hasEntityMatch && (
          <div className="flex items-center gap-2 bg-primary/5 border border-primary/20 rounded-lg px-3 py-2">
            <UserCheck className="h-4 w-4 text-primary shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-xs text-muted-foreground">Erkannter Partner</p>
              <p className="text-sm font-medium text-primary truncate">
                {ocrResult.matchedEntityName}
              </p>
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex flex-col gap-2 pt-2">
          <Button
            onClick={handleAssign}
            className="w-full min-h-[44px] gap-2"
            variant="default"
          >
            <UserCheck className="h-4 w-4" />
            Zuordnen
          </Button>

          <div className="flex gap-2">
            <Button
              onClick={onComplete}
              variant="outline"
              className="flex-1 min-h-[44px] gap-2"
            >
              <ArrowRight className="h-4 w-4" />
              Fertig
            </Button>
            <Button
              onClick={onScanAnother}
              variant="outline"
              className="flex-1 min-h-[44px] gap-2"
            >
              <Camera className="h-4 w-4" />
              Weiterer Scan
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default ScanResultPanel;
