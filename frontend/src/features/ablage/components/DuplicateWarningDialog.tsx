/**
 * DuplicateWarningDialog - Warnung bei erkannten Duplikaten vor dem Upload.
 *
 * Zeigt gefundene Duplikate/aehnliche Dokumente an und bietet dem User
 * drei Optionen: Trotzdem hochladen, Zum Dokument navigieren, Abbrechen.
 */

import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { FileText, ExternalLink, AlertTriangle } from 'lucide-react';
import type { DuplicateCandidate } from '../api/ablage-api';

interface DuplicateWarningDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  filename: string;
  candidates: DuplicateCandidate[];
  recommendation: 'skip' | 'proceed' | 'review';
  onProceed: () => void;
  onNavigate: (documentId: string) => void;
  onCancel: () => void;
}

export function DuplicateWarningDialog({
  open,
  onOpenChange,
  filename,
  candidates,
  recommendation,
  onProceed,
  onNavigate,
  onCancel,
}: DuplicateWarningDialogProps) {
  const hasExactMatch = candidates.some((c) => c.match_type === 'exact_hash');

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="max-w-lg">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-500" />
            {hasExactMatch ? 'Duplikat erkannt' : 'Aehnliches Dokument gefunden'}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {hasExactMatch
              ? `Die Datei "${filename}" existiert bereits im System.`
              : `Es wurden aehnliche Dokumente zu "${filename}" gefunden.`}
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-3 my-4">
          {candidates.map((candidate) => (
            <div
              key={candidate.document_id}
              className="flex items-center justify-between p-3 rounded-lg border bg-muted/30"
            >
              <div className="flex items-center gap-3 min-w-0">
                <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{candidate.filename}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <Badge
                      variant={candidate.match_type === 'exact_hash' ? 'destructive' : 'secondary'}
                      className="text-[10px]"
                    >
                      {candidate.match_type === 'exact_hash'
                        ? 'Identisch'
                        : 'Aehnlicher Name'}
                    </Badge>
                    {candidate.upload_date && (
                      <span className="text-xs text-muted-foreground">
                        {new Date(candidate.upload_date).toLocaleDateString('de-DE')}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="shrink-0 gap-1"
                onClick={() => onNavigate(candidate.document_id)}
              >
                <ExternalLink className="h-3.5 w-3.5" />
                Oeffnen
              </Button>
            </div>
          ))}
        </div>

        {recommendation === 'skip' && (
          <p className="text-sm text-muted-foreground">
            Empfehlung: Upload ueberspringen, da ein identisches Dokument existiert.
          </p>
        )}

        <AlertDialogFooter className="gap-2 sm:gap-0">
          <AlertDialogCancel onClick={onCancel}>Abbrechen</AlertDialogCancel>
          <AlertDialogAction onClick={onProceed}>
            Trotzdem hochladen
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
