/**
 * AutoMatchDialog - Automatisches Dokument-Matching
 *
 * Dialog zum automatischen Finden und Verknuepfen passender Dokumente.
 * Zeigt Vorschlaege mit Confidence-Score und Match-Gruenden.
 */

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import {
  Link2,
  Loader2,
  Search,
  CheckCircle,
  ArrowRight,
  FileText,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  type ChainMatchResult,
  type ChainRelationshipType,
  CHAIN_UI_LABELS,
  DOCUMENT_TYPE_STYLES,
} from '../types/chain-types';
import { formatCurrency, formatDate } from '@/features/banking/utils/format';
import { useAutoMatch, useLinkDocuments } from '../hooks/use-chain-queries';
import { useToast } from '@/hooks/use-toast';

interface AutoMatchDialogProps {
  documentId: string;
  documentName: string;
  chainId?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

const RELATIONSHIP_LABELS: Record<ChainRelationshipType, string> = {
  quote_to_order: CHAIN_UI_LABELS.relQuoteToOrder,
  order_to_delivery: CHAIN_UI_LABELS.relOrderToDelivery,
  delivery_to_invoice: CHAIN_UI_LABELS.relDeliveryToInvoice,
  quote_to_invoice: CHAIN_UI_LABELS.relQuoteToInvoice,
};

export function AutoMatchDialog({
  documentId,
  documentName,
  chainId,
  open,
  onOpenChange,
  onSuccess,
}: AutoMatchDialogProps) {
  const { toast } = useToast();
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null);

  const autoMatchQuery = useAutoMatch(documentId, { enabled: open });
  const linkDocuments = useLinkDocuments();

  const matches = autoMatchQuery.data ?? [];
  const selectedMatch = matches.find((m) => m.candidateDocumentId === selectedMatchId);

  const handleLink = async () => {
    if (!selectedMatch) return;

    try {
      await linkDocuments.mutateAsync({
        sourceDocumentId: documentId,
        targetDocumentId: selectedMatch.candidateDocumentId,
        relationshipType: selectedMatch.suggestedRelationshipType,
        chainId,
      });
      toast({
        title: 'Erfolg',
        description: CHAIN_UI_LABELS.successLinkDocuments,
      });
      onOpenChange(false);
      onSuccess?.();
    } catch {
      toast({
        title: 'Fehler',
        description: CHAIN_UI_LABELS.errorLinkDocuments,
        variant: 'destructive',
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Search className="w-5 h-5" />
            {CHAIN_UI_LABELS.actionAutoMatch}
          </DialogTitle>
          <DialogDescription>
            Passende Dokumente fuer &quot;{documentName}&quot; werden gesucht.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Loading */}
          {autoMatchQuery.isLoading && (
            <div className="flex flex-col items-center justify-center py-8">
              <Loader2 className="w-8 h-8 animate-spin text-muted-foreground mb-2" />
              <p className="text-sm text-muted-foreground">Suche passende Dokumente...</p>
            </div>
          )}

          {/* No matches */}
          {!autoMatchQuery.isLoading && matches.length === 0 && (
            <div className="text-center py-8 text-muted-foreground">
              <FileText className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p>{CHAIN_UI_LABELS.emptyNoMatches}</p>
              <p className="text-xs mt-1">
                Versuchen Sie, das Dokument manuell zu verknuepfen.
              </p>
            </div>
          )}

          {/* Match results */}
          {!autoMatchQuery.isLoading && matches.length > 0 && (
            <RadioGroup
              value={selectedMatchId ?? ''}
              onValueChange={setSelectedMatchId}
              className="space-y-3"
            >
              {matches.map((match) => {
                const doc = match.candidateDocument;
                const style = DOCUMENT_TYPE_STYLES[doc.documentType];
                const confidenceColor =
                  match.confidence >= 0.9
                    ? 'text-green-600'
                    : match.confidence >= 0.7
                      ? 'text-yellow-600'
                      : 'text-orange-600';

                return (
                  <div
                    key={match.candidateDocumentId}
                    className={cn(
                      'flex items-start space-x-3 p-3 rounded-lg border cursor-pointer transition-colors',
                      selectedMatchId === match.candidateDocumentId
                        ? 'border-primary bg-primary/5'
                        : 'hover:bg-muted/50'
                    )}
                    onClick={() => setSelectedMatchId(match.candidateDocumentId)}
                  >
                    <RadioGroupItem
                      value={match.candidateDocumentId}
                      id={match.candidateDocumentId}
                      className="mt-1"
                    />
                    <Label
                      htmlFor={match.candidateDocumentId}
                      className="flex-1 cursor-pointer"
                    >
                      <div className="flex items-start justify-between">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <Badge
                              variant="outline"
                              className={cn(
                                'text-xs',
                                style.bgColor,
                                style.textColor,
                                style.borderColor
                              )}
                            >
                              {style.label}
                            </Badge>
                            <span className="font-medium text-sm">
                              {doc.displayName || doc.filename}
                            </span>
                          </div>
                          <div className="flex items-center gap-3 text-xs text-muted-foreground">
                            {doc.referenceNumber && (
                              <span>#{doc.referenceNumber}</span>
                            )}
                            {doc.documentDate && (
                              <span>{formatDate(doc.documentDate)}</span>
                            )}
                            {doc.totalAmount && (
                              <span>{formatCurrency(doc.totalAmount)}</span>
                            )}
                          </div>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {match.matchReasons.map((reason, idx) => (
                              <Badge
                                key={idx}
                                variant="secondary"
                                className="text-xs font-normal"
                              >
                                {reason}
                              </Badge>
                            ))}
                          </div>
                        </div>
                        <div className="text-right">
                          <div className={cn('text-sm font-semibold', confidenceColor)}>
                            {Math.round(match.confidence * 100)}%
                          </div>
                          <div className="text-xs text-muted-foreground">
                            Uebereinstimmung
                          </div>
                        </div>
                      </div>
                    </Label>
                  </div>
                );
              })}
            </RadioGroup>
          )}

          {/* Selected match preview */}
          {selectedMatch && (
            <>
              <Separator />
              <div className="p-3 bg-muted rounded-md">
                <div className="text-sm font-medium mb-2">Verknuepfung erstellen:</div>
                <div className="flex items-center gap-2 text-sm">
                  <span className="truncate max-w-[120px]">{documentName}</span>
                  <ArrowRight className="w-4 h-4 flex-shrink-0" />
                  <span className="truncate max-w-[120px]">
                    {selectedMatch.candidateDocument.displayName ||
                      selectedMatch.candidateDocument.filename}
                  </span>
                </div>
                <Badge variant="outline" className="mt-2 text-xs">
                  {RELATIONSHIP_LABELS[selectedMatch.suggestedRelationshipType]}
                </Badge>
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Abbrechen
          </Button>
          <Button
            onClick={handleLink}
            disabled={!selectedMatch || linkDocuments.isPending}
          >
            {linkDocuments.isPending ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Link2 className="w-4 h-4 mr-2" />
            )}
            {CHAIN_UI_LABELS.actionLinkDocuments}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
