/**
 * EmlPreviewDialog - Vorschau-Dialog für geparste E-Mail-Dateien.
 *
 * Zeigt Absender, Betreff, Body-Vorschau und Anhänge mit Import-Optionen.
 */

import { useState, useMemo } from 'react';
import { FileText, Paperclip, Loader2 } from 'lucide-react';
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
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import type { EmlParseResponse, EmlImportRequest } from '../types/email-types';

interface EmlPreviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  parsedEmail: EmlParseResponse | null;
  onImport: (request: EmlImportRequest) => void;
  isImporting: boolean;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatGermanDate(dateStr: string | null): string {
  if (!dateStr) return 'Unbekannt';
  return new Date(dateStr).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function EmlPreviewDialog({
  open,
  onOpenChange,
  parsedEmail,
  onImport,
  isImporting,
}: EmlPreviewDialogProps) {
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());
  const [targetFolderId, setTargetFolderId] = useState('');
  const [autoOcr, setAutoOcr] = useState(true);
  const [autoClassify, setAutoClassify] = useState(true);

  const importableAttachments = useMemo(
    () => parsedEmail?.attachments.filter((a) => a.is_importable) ?? [],
    [parsedEmail],
  );

  const allSelected =
    importableAttachments.length > 0 &&
    importableAttachments.every((a) => selectedIndices.has(a.index));

  const toggleAll = () => {
    if (allSelected) {
      setSelectedIndices(new Set());
    } else {
      setSelectedIndices(new Set(importableAttachments.map((a) => a.index)));
    }
  };

  const toggleAttachment = (index: number) => {
    setSelectedIndices((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  const handleImport = () => {
    if (!parsedEmail || selectedIndices.size === 0) return;
    onImport({
      file_id: parsedEmail.file_id,
      selected_attachment_indices: Array.from(selectedIndices),
      target_folder_id: targetFolderId || undefined,
      auto_ocr: autoOcr,
      auto_classify: autoClassify,
    });
  };

  if (!parsedEmail) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            E-Mail Vorschau
          </DialogTitle>
          <DialogDescription>
            Wählen Sie die Anhänge aus, die importiert werden sollen.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Email header info */}
          <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
            <span className="font-medium text-muted-foreground">Von:</span>
            <span>
              {parsedEmail.sender_name
                ? `${parsedEmail.sender_name} <${parsedEmail.sender}>`
                : parsedEmail.sender}
            </span>
            <span className="font-medium text-muted-foreground">Betreff:</span>
            <span className="font-medium">{parsedEmail.subject}</span>
            <span className="font-medium text-muted-foreground">Datum:</span>
            <span>{formatGermanDate(parsedEmail.date)}</span>
          </div>

          <Separator />

          {/* Body preview */}
          {parsedEmail.body_preview && (
            <>
              <div>
                <Label className="text-sm font-medium">Nachricht</Label>
                <ScrollArea className="mt-1 max-h-40 rounded-md border p-3">
                  <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                    {parsedEmail.body_preview}
                  </p>
                </ScrollArea>
              </div>
              <Separator />
            </>
          )}

          {/* Attachments */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-sm font-medium flex items-center gap-2">
                <Paperclip className="h-4 w-4" />
                Anhänge ({parsedEmail.attachments.length})
              </Label>
              {importableAttachments.length > 0 && (
                <Button variant="ghost" size="sm" onClick={toggleAll}>
                  {allSelected ? 'Keine auswählen' : 'Alle auswählen'}
                </Button>
              )}
            </div>

            <div className="space-y-2 max-h-48 overflow-y-auto">
              {parsedEmail.attachments.map((att) => {
                const isImportable = att.is_importable;
                const isSelected = selectedIndices.has(att.index);

                return (
                  <label
                    key={att.index}
                    className={cn(
                      'flex items-center gap-3 rounded-md border p-3 transition-colors',
                      isImportable
                        ? 'cursor-pointer hover:bg-muted/50'
                        : 'opacity-50 cursor-not-allowed',
                      isSelected && 'border-primary bg-primary/5',
                    )}
                  >
                    <Checkbox
                      checked={isSelected}
                      onCheckedChange={() => isImportable && toggleAttachment(att.index)}
                      disabled={!isImportable}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{att.filename}</p>
                      <p className="text-xs text-muted-foreground">
                        {formatFileSize(att.size)}
                      </p>
                    </div>
                    <Badge variant={isImportable ? 'default' : 'secondary'}>
                      {isImportable ? 'Importierbar' : att.mime_type}
                    </Badge>
                  </label>
                );
              })}
            </div>
          </div>

          <Separator />

          {/* Import options */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">Import-Optionen</Label>

            <div className="space-y-2">
              <Label htmlFor="target-folder" className="text-sm">
                Zielordner (optional)
              </Label>
              <Input
                id="target-folder"
                value={targetFolderId}
                onChange={(e) => setTargetFolderId(e.target.value)}
                placeholder="Ordner-ID oder Pfad"
              />
            </div>

            <div className="flex items-center justify-between">
              <Label htmlFor="auto-ocr" className="text-sm">
                Automatische OCR-Verarbeitung
              </Label>
              <Switch
                id="auto-ocr"
                checked={autoOcr}
                onCheckedChange={setAutoOcr}
              />
            </div>

            <div className="flex items-center justify-between">
              <Label htmlFor="auto-classify" className="text-sm">
                Automatische Klassifizierung
              </Label>
              <Switch
                id="auto-classify"
                checked={autoClassify}
                onCheckedChange={setAutoClassify}
              />
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isImporting}
          >
            Abbrechen
          </Button>
          <Button
            onClick={handleImport}
            disabled={selectedIndices.size === 0 || isImporting}
          >
            {isImporting ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : null}
            Importieren ({selectedIndices.size}{' '}
            {selectedIndices.size === 1 ? 'Datei' : 'Dateien'})
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
