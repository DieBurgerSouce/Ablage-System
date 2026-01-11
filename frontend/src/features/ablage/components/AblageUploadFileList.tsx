/**
 * AblageUploadFileList - Dateiliste mit Quick Classification Badges
 *
 * Zeigt alle hochgeladenen Dateien mit:
 * - DirectionBadge (Eingangs-/Ausgangsrechnung)
 * - EntityBadge (erkannter Geschaeftspartner)
 * - RenameSuggestionBadge (Umbenennungsvorschlag)
 * - Status-Icons und Progress
 * - Review-Button zum Oeffnen des OCRReviewModal
 *
 * Basiert auf dem Upload Wizard Pattern.
 */

import { motion, AnimatePresence } from 'framer-motion';
import {
  FileText,
  CheckCircle,
  XCircle,
  Loader2,
  Trash2,
  Eye,
  ArrowDownLeft,
  ArrowUpRight,
  AlertTriangle,
  Building2,
  Link2,
  FileEdit,
  Check,
  Image,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { AblageUploadingFile, InvoiceDirection } from '../types';

interface AblageUploadFileListProps {
  files: AblageUploadingFile[];
  onRemove: (id: string) => void;
  onReview: (id: string) => void;
  onConfirmDirection?: (id: string, direction: InvoiceDirection) => void;
  onConfirmRename?: (id: string) => void;
  renameLoadingIds?: string[];
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getStatusIcon(status: AblageUploadingFile['status'], ocrProgress?: number) {
  switch (status) {
    case 'pending':
      return <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />;
    case 'uploading':
      return <Loader2 className="w-5 h-5 animate-spin text-blue-500" />;
    case 'processing':
      return (
        <div className="relative w-5 h-5">
          <svg className="w-5 h-5 -rotate-90" viewBox="0 0 24 24">
            <circle
              cx="12"
              cy="12"
              r="10"
              strokeWidth="3"
              stroke="currentColor"
              fill="none"
              className="text-muted-foreground/20"
            />
            <circle
              cx="12"
              cy="12"
              r="10"
              strokeWidth="3"
              stroke="currentColor"
              fill="none"
              strokeDasharray={`${(ocrProgress || 0) * 0.628} 62.8`}
              className="text-amber-500 transition-all duration-300"
            />
          </svg>
        </div>
      );
    case 'review':
      return <CheckCircle className="w-5 h-5 text-amber-500" />;
    case 'completed':
      return <CheckCircle className="w-5 h-5 text-emerald-500" />;
    case 'error':
      return <XCircle className="w-5 h-5 text-destructive" />;
  }
}

function getStatusText(
  status: AblageUploadingFile['status'],
  progress: number,
  ocrProgress?: number
): string {
  switch (status) {
    case 'pending':
      return 'Warte auf Upload...';
    case 'uploading':
      return `Wird hochgeladen... ${progress}%`;
    case 'processing':
      if (ocrProgress !== undefined && ocrProgress > 0) return `OCR laeuft... ${ocrProgress}%`;
      return 'OCR laeuft...';
    case 'review':
      return 'Bereit zur Pruefung';
    case 'completed':
      return 'Gespeichert';
    case 'error':
      return 'Fehler';
  }
}

/**
 * DirectionBadge - Zeigt die erkannte Rechnungsrichtung mit Konfidenz-Warnung
 */
function DirectionBadge({
  direction,
  confidence,
  onConfirm,
}: {
  direction: InvoiceDirection;
  confidence?: number;
  onConfirm?: (direction: InvoiceDirection) => void;
}) {
  const isLowConfidence = confidence !== undefined && confidence < 0.8;

  // Unbekannt - zeige Auswahl-Buttons
  if (direction === null) {
    return (
      <div className="flex items-center gap-1">
        <Badge
          variant="outline"
          className="gap-1 bg-orange-500/10 text-orange-600 border-orange-500/30 dark:text-orange-400"
        >
          <AlertTriangle className="w-3 h-3" />
          Bitte waehlen
        </Badge>
        {onConfirm && (
          <div className="flex gap-1 ml-1">
            <Button
              variant="outline"
              size="sm"
              className="h-6 px-2 text-xs gap-1 hover:bg-blue-500/10 hover:text-blue-600 hover:border-blue-500/30"
              onClick={(e) => {
                e.stopPropagation();
                onConfirm('incoming');
              }}
            >
              <ArrowDownLeft className="w-3 h-3" />
              Eingang
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-6 px-2 text-xs gap-1 hover:bg-amber-500/10 hover:text-amber-600 hover:border-amber-500/30"
              onClick={(e) => {
                e.stopPropagation();
                onConfirm('outgoing');
              }}
            >
              <ArrowUpRight className="w-3 h-3" />
              Ausgang
            </Button>
          </div>
        )}
      </div>
    );
  }

  const isIncoming = direction === 'incoming';

  // Warnung bei niedriger Konfidenz (<80%)
  if (isLowConfidence) {
    return (
      <div className="flex items-center gap-1">
        <Badge className="gap-1 bg-orange-500/10 text-orange-600 border border-orange-500/30 dark:text-orange-400">
          <AlertTriangle className="w-3 h-3" />
          {isIncoming ? 'Eingangsrechnung' : 'Ausgangsrechnung'}?
          <span className="text-xs opacity-70">
            ({Math.round((confidence || 0) * 100)}%)
          </span>
        </Badge>
        {onConfirm && (
          <div className="flex gap-1 ml-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0"
              title="Bestaetigen"
              onClick={(e) => {
                e.stopPropagation();
                onConfirm(direction);
              }}
            >
              <Check className="w-3 h-3 text-emerald-500" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-xs"
              title={isIncoming ? 'Zu Ausgangsrechnung aendern' : 'Zu Eingangsrechnung aendern'}
              onClick={(e) => {
                e.stopPropagation();
                onConfirm(isIncoming ? 'outgoing' : 'incoming');
              }}
            >
              {isIncoming ? (
                <>
                  <ArrowUpRight className="w-3 h-3 mr-1" />
                  Ausgang
                </>
              ) : (
                <>
                  <ArrowDownLeft className="w-3 h-3 mr-1" />
                  Eingang
                </>
              )}
            </Button>
          </div>
        )}
      </div>
    );
  }

  // Normale Anzeige mit hoher Konfidenz
  return (
    <Badge
      variant="outline"
      className={cn(
        'gap-1',
        isIncoming
          ? 'bg-blue-500/10 text-blue-600 border-blue-500/30 dark:text-blue-400'
          : 'bg-amber-500/10 text-amber-600 border-amber-500/30 dark:text-amber-400'
      )}
    >
      {isIncoming ? (
        <ArrowDownLeft className="w-3 h-3" />
      ) : (
        <ArrowUpRight className="w-3 h-3" />
      )}
      {isIncoming ? 'Eingangsrechnung' : 'Ausgangsrechnung'}
    </Badge>
  );
}

/**
 * EntityBadge - Zeigt den erkannten Geschaeftspartner (Lieferant/Kunde)
 */
function EntityBadge({
  entityName,
  entityType,
  confidence,
  autoLinked,
}: {
  entityName: string;
  entityType?: 'supplier' | 'customer';
  confidence?: number;
  autoLinked?: boolean;
}) {
  const isLowConfidence = confidence !== undefined && confidence < 0.85;
  const typeLabel = entityType === 'supplier' ? 'Lieferant' : entityType === 'customer' ? 'Kunde' : 'Partner';

  return (
    <Badge
      variant="outline"
      className={cn(
        'gap-1 max-w-[200px]',
        autoLinked
          ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30 dark:text-emerald-400'
          : 'bg-slate-500/10 text-slate-600 border-slate-500/30 dark:text-slate-400',
        isLowConfidence && 'border-dashed'
      )}
      title={`${typeLabel}: ${entityName}${autoLinked ? ' (automatisch verknuepft)' : ''}${confidence ? ` - ${Math.round(confidence * 100)}% Konfidenz` : ''}`}
    >
      {autoLinked ? (
        <Link2 className="w-3 h-3 flex-shrink-0" />
      ) : (
        <Building2 className="w-3 h-3 flex-shrink-0" />
      )}
      <span className="truncate">{entityName}</span>
      {isLowConfidence && <span className="text-xs opacity-70 flex-shrink-0">?</span>}
    </Badge>
  );
}

/**
 * RenameSuggestionBadge - Zeigt Umbenennungsvorschlag mit Bestaetigen-Button
 */
function RenameSuggestionBadge({
  suggestion,
  confirmed,
  isLoading,
  onConfirm,
}: {
  suggestion: {
    suggestedFilename: string;
    confidence: number;
  };
  confirmed?: boolean;
  isLoading?: boolean;
  onConfirm?: () => void;
}) {
  if (confirmed) {
    return (
      <Badge
        variant="outline"
        className="gap-1 bg-emerald-500/10 text-emerald-600 border-emerald-500/30 dark:text-emerald-400"
      >
        <Check className="w-3 h-3" />
        Umbenannt
      </Badge>
    );
  }

  return (
    <div className="flex items-center gap-1">
      <Badge
        variant="outline"
        className="gap-1 bg-violet-500/10 text-violet-600 border-violet-500/30 dark:text-violet-400 max-w-[200px]"
        title={suggestion.suggestedFilename}
      >
        <FileEdit className="w-3 h-3 flex-shrink-0" />
        <span className="truncate">{suggestion.suggestedFilename}</span>
      </Badge>
      {onConfirm && (
        <Button
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0"
          disabled={isLoading}
          title="Umbenennung bestaetigen"
          onClick={(e) => {
            e.stopPropagation();
            onConfirm();
          }}
        >
          {isLoading ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <Check className="w-3 h-3 text-emerald-500" />
          )}
        </Button>
      )}
    </div>
  );
}

/**
 * FileItem - Einzelnes Datei-Item in der Liste
 */
function FileItem({
  file,
  onRemove,
  onReview,
  onConfirmDirection,
  onConfirmRename,
  isRenameLoading,
}: {
  file: AblageUploadingFile;
  onRemove: () => void;
  onReview: () => void;
  onConfirmDirection?: (direction: InvoiceDirection) => void;
  onConfirmRename?: () => void;
  isRenameLoading: boolean;
}) {
  const canReview = file.status === 'review';
  const isCompleted = file.status === 'completed';
  const hasError = file.status === 'error';
  const isProcessing = file.status === 'uploading' || file.status === 'processing';
  const isImage = file.file?.type?.startsWith('image/');

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -20 }}
      layout
      className={cn(
        'flex flex-col gap-3 p-4 rounded-lg border bg-card transition-all',
        hasError && 'border-destructive/50 bg-destructive/5',
        isCompleted && 'border-emerald-500/30 bg-emerald-500/5',
        canReview && 'border-amber-500/30 bg-amber-500/5 hover:border-amber-500/50',
        canReview && 'cursor-pointer'
      )}
      onClick={canReview ? onReview : undefined}
    >
      {/* Header: File Info + Actions */}
      <div className="flex items-center gap-4">
        {/* File Icon */}
        <div className="flex-shrink-0">
          <div
            className={cn(
              'w-10 h-10 rounded-lg flex items-center justify-center',
              isCompleted
                ? 'bg-emerald-500/10'
                : canReview
                  ? 'bg-amber-500/10'
                  : hasError
                    ? 'bg-destructive/10'
                    : 'bg-muted'
            )}
          >
            {isImage ? (
              <Image
                className={cn(
                  'w-5 h-5',
                  isCompleted
                    ? 'text-emerald-500'
                    : canReview
                      ? 'text-amber-500'
                      : hasError
                        ? 'text-destructive'
                        : 'text-muted-foreground'
                )}
              />
            ) : (
              <FileText
                className={cn(
                  'w-5 h-5',
                  isCompleted
                    ? 'text-emerald-500'
                    : canReview
                      ? 'text-amber-500'
                      : hasError
                        ? 'text-destructive'
                        : 'text-muted-foreground'
                )}
              />
            )}
          </div>
        </div>

        {/* File Name + Size */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">
            {file.renamedFilename || file.file?.name || file.originalFilename}
          </p>
          <p className="text-xs text-muted-foreground">
            {file.file ? formatFileSize(file.file.size) : ''} • {getStatusText(file.status, file.progress, file.ocrProgress)}
          </p>
        </div>

        {/* Status Icon */}
        <div className="flex-shrink-0">
          {getStatusIcon(file.status, file.ocrProgress)}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          {canReview && (
            <Button
              variant="outline"
              size="sm"
              className="h-8 gap-1"
              onClick={(e) => {
                e.stopPropagation();
                onReview();
              }}
            >
              <Eye className="w-4 h-4" />
              Pruefen
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            disabled={isProcessing}
            onClick={(e) => {
              e.stopPropagation();
              onRemove();
            }}
          >
            <Trash2 className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Progress Bar (nur bei Upload/Processing) */}
      {isProcessing && (
        <Progress value={file.progress} className="h-1.5" />
      )}

      {/* Classification Badges (nur bei Review/Completed) */}
      {(canReview || isCompleted) && file.quickClassification && (
        <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-border/50">
          {/* Direction Badge */}
          <DirectionBadge
            direction={file.confirmedDirection || file.quickClassification.direction || null}
            confidence={file.quickClassification.confidence}
            onConfirm={canReview ? onConfirmDirection : undefined}
          />

          {/* Entity Badge */}
          {file.quickClassification.matchedEntityName && (
            <EntityBadge
              entityName={file.quickClassification.matchedEntityName}
              entityType={file.quickClassification.matchedEntityType || undefined}
              confidence={file.quickClassification.matchedEntityConfidence}
              autoLinked={!!file.quickClassification.matchedEntityId}
            />
          )}

          {/* Rename Suggestion Badge */}
          {file.renameSuggestion && (
            <RenameSuggestionBadge
              suggestion={file.renameSuggestion}
              confirmed={file.renameConfirmed}
              isLoading={isRenameLoading}
              onConfirm={canReview ? onConfirmRename : undefined}
            />
          )}

          {/* Extracted Data Badges */}
          {file.quickClassification.extractedData?.totalAmount && (
            <Badge variant="secondary" className="gap-1">
              {new Intl.NumberFormat('de-DE', {
                style: 'currency',
                currency: file.quickClassification.extractedData.currency || 'EUR',
              }).format(file.quickClassification.extractedData.totalAmount)}
            </Badge>
          )}

          {file.quickClassification.extractedData?.documentNumber && (
            <Badge variant="secondary" className="gap-1">
              Nr. {file.quickClassification.extractedData.documentNumber}
            </Badge>
          )}

          {file.quickClassification.extractedData?.ibanFound && (
            <Badge
              variant="outline"
              className="gap-1 bg-blue-500/10 text-blue-600 border-blue-500/30"
              title={file.quickClassification.extractedData.ibanFound}
            >
              IBAN erkannt
            </Badge>
          )}

          {file.quickClassification.extractedData?.vatIdFound && (
            <Badge
              variant="outline"
              className="gap-1 bg-green-500/10 text-green-600 border-green-500/30"
              title={file.quickClassification.extractedData.vatIdFound}
            >
              USt-ID erkannt
            </Badge>
          )}
        </div>
      )}

      {/* Error Message */}
      {hasError && file.error && (
        <p className="text-xs text-destructive">{file.error}</p>
      )}
    </motion.div>
  );
}

/**
 * AblageUploadFileList - Hauptkomponente
 */
export function AblageUploadFileList({
  files,
  onRemove,
  onReview,
  onConfirmDirection,
  onConfirmRename,
  renameLoadingIds = [],
}: AblageUploadFileListProps) {
  if (files.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      <AnimatePresence mode="popLayout">
        {files.map((file) => (
          <FileItem
            key={file.id}
            file={file}
            onRemove={() => onRemove(file.id)}
            onReview={() => onReview(file.id)}
            onConfirmDirection={onConfirmDirection ? (dir) => onConfirmDirection(file.id, dir) : undefined}
            onConfirmRename={onConfirmRename ? () => onConfirmRename(file.id) : undefined}
            isRenameLoading={renameLoadingIds.includes(file.id)}
          />
        ))}
      </AnimatePresence>
    </div>
  );
}

export { DirectionBadge, EntityBadge, RenameSuggestionBadge };
