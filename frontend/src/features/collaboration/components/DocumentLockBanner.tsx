/**
 * DocumentLockBanner - Banner für gesperrte Dokumente
 *
 * Features:
 * - Zeigt an wer das Dokument gerade bearbeitet
 * - "Trotzdem bearbeiten" Button (nimmt Lock über)
 * - Auto-Hide wenn Sperre aufgehoben wird
 * - Verschiedene Varianten (Info, Warning)
 */

import { Lock, AlertCircle, Edit } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import type { DocumentLock } from '../hooks/useDocumentLock';

// ==================== Main Component ====================

interface DocumentLockBannerProps {
  /** Lock-Informationen */
  lock: DocumentLock;
  /** Eigene User-ID */
  currentUserId?: string;
  /** Callback für "Trotzdem bearbeiten" */
  onForceLock?: () => void;
  /** Force Lock wird gerade ausgeführt */
  isForcing?: boolean;
  /** Variante des Banners */
  variant?: 'info' | 'warning';
  className?: string;
}

export function DocumentLockBanner({
  lock,
  currentUserId,
  onForceLock,
  isForcing = false,
  variant = 'info',
  className,
}: DocumentLockBannerProps) {
  const isLockedByMe = lock.locked_by_user_id === currentUserId;

  // Wenn von mir gesperrt, kein Banner anzeigen
  if (isLockedByMe) {
    return null;
  }

  const timeAgo = formatDistanceToNow(new Date(lock.locked_at), {
    addSuffix: true,
    locale: de,
  });

  const alertVariant = variant === 'warning' ? 'destructive' : 'default';
  const Icon = variant === 'warning' ? AlertCircle : Lock;
  const iconColor = variant === 'warning' ? 'text-destructive' : 'text-blue-500';

  return (
    <Alert variant={alertVariant} className={cn('border-l-4', className)}>
      <Icon className={cn('h-4 w-4', iconColor)} />
      <AlertDescription className="flex items-center justify-between gap-4">
        <div className="flex-1">
          <p className="font-medium">
            <span className="font-semibold">{lock.locked_by_user_name}</span> bearbeitet dieses
            Dokument gerade
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Gesperrt {timeAgo}
            {lock.expires_at && (
              <span>
                {' '}
                • Läuft ab{' '}
                {formatDistanceToNow(new Date(lock.expires_at), {
                  addSuffix: true,
                  locale: de,
                })}
              </span>
            )}
          </p>
        </div>

        {onForceLock && (
          <Button
            variant="outline"
            size="sm"
            onClick={onForceLock}
            disabled={isForcing}
            className="shrink-0"
          >
            <Edit className="h-3.5 w-3.5 mr-1.5" />
            {isForcing ? 'Wird übernommen...' : 'Trotzdem bearbeiten'}
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}

export default DocumentLockBanner;
