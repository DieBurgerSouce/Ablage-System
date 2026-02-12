/**
 * Letter Preview Dialog Component
 * Modal für Mahnbrief-Vorschau und PDF-Download
 */

import { useState } from 'react';
import { FileText, Download, Loader2, ExternalLink, X } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';
import { useLetterPreview, useDownloadLetterPdf } from '../hooks';
import type { DunningTemplate, DunningRecord } from '../types';

interface LetterPreviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  dunningRecord: DunningRecord | null;
  template: DunningTemplate | null;
}

export function LetterPreviewDialog({
  open,
  onOpenChange,
  dunningRecord,
  template,
}: LetterPreviewDialogProps) {
  const [isB2b, setIsB2b] = useState(true);

  const previewParams =
    dunningRecord && template
      ? {
          dunningId: dunningRecord.id,
          dunningLevel: template.level,
          isB2b,
        }
      : null;

  const { data: previewHtml, isLoading: isLoadingPreview } = useLetterPreview(
    previewParams,
    open
  );

  const downloadMutation = useDownloadLetterPdf();

  const handleDownload = () => {
    if (!previewParams) return;
    downloadMutation.mutate(previewParams);
  };

  const handleOpenInNewTab = () => {
    if (!previewHtml) return;
    const blob = new Blob([previewHtml], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <div className="flex items-center justify-between pr-8">
            <div>
              <DialogTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                Mahnbrief-Vorschau
              </DialogTitle>
              <DialogDescription>
                {dunningRecord
                  ? `${dunningRecord.entityName} - ${dunningRecord.invoiceNumber}`
                  : 'Vorschau laden...'}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {/* Controls */}
        <div className="flex items-center justify-between border-b pb-4">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <Switch
                id="b2b-switch"
                checked={isB2b}
                onCheckedChange={setIsB2b}
              />
              <Label htmlFor="b2b-switch" className="text-sm">
                {isB2b ? 'Geschäftskunde (B2B)' : 'Privatkunde (B2C)'}
              </Label>
            </div>
            {template && (
              <span className="text-sm text-muted-foreground">
                Mahnstufe {template.level}: {template.name}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleOpenInNewTab}
              disabled={!previewHtml || isLoadingPreview}
            >
              <ExternalLink className="h-4 w-4 mr-2" />
              Neues Fenster
            </Button>
            <Button
              size="sm"
              onClick={handleDownload}
              disabled={!previewParams || downloadMutation.isPending}
            >
              {downloadMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Download className="h-4 w-4 mr-2" />
              )}
              PDF herunterladen
            </Button>
          </div>
        </div>

        {/* Preview Area */}
        <div className="flex-1 overflow-auto rounded-lg border bg-white">
          {isLoadingPreview ? (
            <div className="p-8 space-y-4">
              <Skeleton className="h-8 w-48" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-32 w-full mt-8" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ) : previewHtml ? (
            <iframe
              srcDoc={previewHtml}
              title="Mahnbrief-Vorschau"
              className="w-full h-[600px] border-0"
              sandbox="allow-same-origin"
            />
          ) : (
            <div className="flex items-center justify-center h-64 text-muted-foreground">
              Keine Vorschau verfügbar
            </div>
          )}
        </div>

        {/* Footer Info */}
        {template && (
          <div className="text-xs text-muted-foreground pt-2 border-t">
            <div className="flex items-center justify-between">
              <span>
                Mahngebühr: {template.fee > 0 ? `${template.fee.toFixed(2).replace('.', ',')} EUR` : 'Keine'}
              </span>
              <span>Zahlungsfrist: {template.paymentDays} Tage</span>
              <span>Vorlage: {template.templateFile}</span>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
