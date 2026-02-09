/**
 * LanguageOverrideDialog Component
 *
 * Dialog zum manuellen Ueberschreiben der erkannten Dokumentsprache.
 * Warnt, dass eine erneute OCR-Verarbeitung ausgeloest wird.
 */

import { useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { LanguageBadge } from './LanguageBadge';

interface LanguageOption {
  code: string;
  label: string;
}

const SUPPORTED_LANGUAGES: LanguageOption[] = [
  { code: 'de', label: 'Deutsch' },
  { code: 'en', label: 'Englisch' },
  { code: 'fr', label: 'Franzoesisch' },
  { code: 'pl', label: 'Polnisch' },
  { code: 'ru', label: 'Russisch' },
  { code: 'it', label: 'Italienisch' },
  { code: 'es', label: 'Spanisch' },
  { code: 'nl', label: 'Niederlaendisch' },
];

export interface LanguageOverrideDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentLanguage: string;
  currentConfidence?: number;
  documentId: string;
  onConfirm: (newLanguage: string, reason: string) => void;
  isLoading?: boolean;
}

export function LanguageOverrideDialog({
  open,
  onOpenChange,
  currentLanguage,
  currentConfidence,
  documentId: _documentId,
  onConfirm,
  isLoading = false,
}: LanguageOverrideDialogProps) {
  const [selectedLanguage, setSelectedLanguage] = useState<string>(currentLanguage);
  const [reason, setReason] = useState('');

  const handleConfirm = () => {
    if (selectedLanguage && selectedLanguage !== currentLanguage) {
      onConfirm(selectedLanguage, reason);
    }
  };

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      setSelectedLanguage(currentLanguage);
      setReason('');
    }
    onOpenChange(isOpen);
  };

  const hasChanged = selectedLanguage !== currentLanguage;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Sprache aendern</DialogTitle>
          <DialogDescription>
            Ueberschreiben Sie die automatisch erkannte Dokumentsprache.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Current Language */}
          <div className="space-y-2">
            <Label className="text-muted-foreground">Aktuell erkannte Sprache</Label>
            <div className="flex items-center gap-2">
              <LanguageBadge
                languageCode={currentLanguage}
                confidence={currentConfidence}
              />
            </div>
          </div>

          {/* New Language Selection */}
          <div className="space-y-2">
            <Label htmlFor="new-language">Neue Sprache</Label>
            <Select value={selectedLanguage} onValueChange={setSelectedLanguage}>
              <SelectTrigger id="new-language">
                <SelectValue placeholder="Sprache auswaehlen" />
              </SelectTrigger>
              <SelectContent>
                {SUPPORTED_LANGUAGES.map((lang) => (
                  <SelectItem key={lang.code} value={lang.code}>
                    {lang.label} ({lang.code.toUpperCase()})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Reason */}
          <div className="space-y-2">
            <Label htmlFor="override-reason">Grund (optional)</Label>
            <Input
              id="override-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="z.B. Dokument ist mehrsprachig"
            />
          </div>

          {/* Warning */}
          {hasChanged && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                Dies loest eine erneute OCR-Verarbeitung aus. Das Dokument wird
                mit den Sprachmodellen fuer die gewaehlte Sprache neu verarbeitet.
              </AlertDescription>
            </Alert>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={isLoading}
          >
            Abbrechen
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={!hasChanged || isLoading}
          >
            {isLoading ? 'Wird gespeichert...' : 'Sprache aendern'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default LanguageOverrideDialog;
