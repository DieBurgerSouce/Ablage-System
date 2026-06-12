/**
 * GraphDetailPanel - Seitenpanel fuer Dokument-Details bei Node-Klick
 */

import { X, ExternalLink, FileText, Calendar, Euro, Link2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Link } from '@tanstack/react-router';
import type { ChainDocument } from '../types/document-graph-types';

interface GraphDetailPanelProps {
  document: ChainDocument | null;
  chainId: string | null;
  onClose: () => void;
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '\u2014';
  return new Date(dateStr).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

function formatAmount(amount: number | null): string {
  if (amount == null) return '\u2014';
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
}

const DOCUMENT_TYPE_LABELS: Record<string, string> = {
  quote: 'Angebot',
  order: 'Auftrag',
  delivery_note: 'Lieferschein',
  invoice: 'Rechnung',
  credit_note: 'Gutschrift',
  reminder: 'Mahnung',
  dunning: 'Inkasso',
  receipt: 'Beleg',
};

export function GraphDetailPanel({ document, chainId: _chainId, onClose }: GraphDetailPanelProps) {
  if (!document) return null;

  const typeLabel = DOCUMENT_TYPE_LABELS[document.documentType] || document.documentType;

  return (
    <Card className="w-80 shrink-0 border-l-0 rounded-l-none">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Dokument-Details</CardTitle>
          <Button variant="ghost" size="icon" onClick={onClose} className="h-7 w-7">
            <X className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <Separator />
      <ScrollArea className="h-[calc(100%-60px)]">
        <CardContent className="pt-4 space-y-4">
          {/* Typ */}
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
            <div>
              <p className="text-xs text-muted-foreground">Typ</p>
              <Badge variant="outline">{typeLabel}</Badge>
            </div>
          </div>

          {/* Dateiname */}
          <div>
            <p className="text-xs text-muted-foreground mb-1">Dateiname</p>
            <p className="text-sm font-medium truncate" title={document.filename}>
              {document.filename}
            </p>
          </div>

          {/* Datum */}
          <div className="flex items-center gap-2">
            <Calendar className="h-4 w-4 text-muted-foreground shrink-0" />
            <div>
              <p className="text-xs text-muted-foreground">Dokumentdatum</p>
              <p className="text-sm">{formatDate(document.documentDate)}</p>
            </div>
          </div>

          {/* Betrag */}
          {document.amount != null && (
            <div className="flex items-center gap-2">
              <Euro className="h-4 w-4 text-muted-foreground shrink-0" />
              <div>
                <p className="text-xs text-muted-foreground">Betrag</p>
                <p className="text-sm font-medium">{formatAmount(document.amount)}</p>
              </div>
            </div>
          )}

          {/* Ketten-Position */}
          <div className="flex items-center gap-2">
            <Link2 className="h-4 w-4 text-muted-foreground shrink-0" />
            <div>
              <p className="text-xs text-muted-foreground">Ketten-Position</p>
              <p className="text-sm">Position {document.chainPosition}</p>
            </div>
          </div>

          {/* Referenznummern */}
          {document.referenceNumbers && Object.keys(document.referenceNumbers).length > 0 && (
            <div>
              <p className="text-xs text-muted-foreground mb-1">Referenznummern</p>
              <div className="space-y-1">
                {Object.entries(document.referenceNumbers).map(([key, value]) => (
                  <div key={key} className="flex justify-between text-xs">
                    <span className="text-muted-foreground">{key}</span>
                    <span className="font-mono">{value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Erstellt am */}
          <div>
            <p className="text-xs text-muted-foreground">Erstellt am</p>
            <p className="text-sm">{formatDate(document.createdAt)}</p>
          </div>

          <Separator />

          {/* Aktionen */}
          <div className="flex flex-col gap-2">
            <Link
              to="/documents/$documentId/relationships"
              params={{ documentId: document.id }}
            >
              <Button variant="outline" size="sm" className="w-full gap-2">
                <ExternalLink className="h-3.5 w-3.5" />
                Zum Dokument
              </Button>
            </Link>
          </div>
        </CardContent>
      </ScrollArea>
    </Card>
  );
}
